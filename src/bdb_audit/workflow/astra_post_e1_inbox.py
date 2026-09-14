"""Astra post-E1 inbox with authoritative E2 semantics and honest manual E3 policy handling."""
from __future__ import annotations

import hashlib
from typing import Any

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import deterministic_id
from ..history.objects import CanonicalObject, CommandEnvelope
from ..stop.models import LaneCompletion, StageCompletion
from .e2_semantics import (
    build_e2_predecessor_view,
    materialize_e2,
    semantic_objects,
    validate_e2_lane_records,
)
from .post_e1_inbox import PostE1ResultInbox
from .inbox import _command_id, _current_cut, _external_ref, _with_ref_class, _same_ref

_MANUAL_E3_PROFILE = "ASTRA_V21_MANUAL_DECLARED_E3"
_MANUAL_E3_LIMITATION = "BDB_DOES_NOT_ENFORCE_EXTERNAL_CHAT_BOUNDARIES"


class AstraPostE1ResultInbox(PostE1ResultInbox):
    """Keep generic E4-E6 ingestion while making E2/E3 semantically explicit."""

    def _accept_result(
        self,
        job,
        proposal_body: dict[str, Any],
        findings: list[dict[str, Any]],
        raw_digest: str,
    ) -> None:
        if self.stage_id == "E2":
            predecessor_view = build_e2_predecessor_view(self.store, self.batch.frozen_history_cut)
            validate_e2_lane_records(
                job.lane_slot,
                proposal_body.get("e2_records"),
                predecessor_view,
            )
            super()._accept_result(job, proposal_body, findings, raw_digest)
            return
        if self.stage_id == "E3":
            self._accept_manual_e3_result(job, proposal_body, findings, raw_digest)
            return
        super()._accept_result(job, proposal_body, findings, raw_digest)

    def _accept_manual_e3_result(
        self,
        job,
        proposal_body: dict[str, Any],
        findings: list[dict[str, Any]],
        raw_digest: str,
    ) -> None:
        """Accept one manual blind E3 lane only under Astra's explicit v2.1 DECLARED profile.

        The normative lane requirement remains ENFORCED.  This branch-local profile
        does not upgrade manual ChatGPT transport.  Instead the accepted isolation
        qualification remains DECLARED and every discovery therefore remains
        ineligible for blind-origin assurance.  The limitation is carried into the
        E3 StageCompletion and final assurance surface.
        """
        cut, prior_commit = _current_cut(self.store)
        assignment_record = self.store.resolve_accepted(job.assignment_ref, cut)
        assignment = assignment_record["body"]
        if not _same_ref(assignment.get("attempt_ref"), job.attempt_ref):
            raise ValidationError("ASSIGNMENT_ATTEMPT_BINDING_MISMATCH")

        attempt_record = self.store.resolve_accepted(assignment["attempt_ref"], cut)
        lane_run_record = self.store.resolve_accepted(attempt_record["body"]["lane_run_ref"], cut)
        knowledge_record = self.store.resolve_accepted(assignment["knowledge_state_ref"], cut)
        isolation_record = self.store.resolve_accepted(knowledge_record["body"]["isolation_qualification_ref"], cut)
        lane_spec_record = self.store.resolve_accepted(assignment["lane_spec_ref"], cut)
        source_record = self.store.resolve_accepted(assignment["source_generation_ref"], cut)

        required_assurance = lane_spec_record["body"].get("required_isolation_assurance", "UNKNOWN")
        actual_assurance = isolation_record["body"].get("result", "UNKNOWN")
        limitations = set(isolation_record["body"].get("limitations") or ())
        allowed_manual_exception = (
            job.executor_profile == "ChatGPT / GitHub"
            and required_assurance == "ENFORCED"
            and actual_assurance == "DECLARED"
            and _MANUAL_E3_LIMITATION in limitations
            and job.actual_isolation == "DECLARED"
        )
        if not allowed_manual_exception:
            raise ValidationError(
                "E3_MANUAL_DECLARED_POLICY_NOT_SATISFIED",
                f"required={required_assurance},actual={actual_assurance},executor={job.executor_profile}",
            )

        proposal = CanonicalObject("bdb_audit_lane_result", proposal_body)
        objects: list[CanonicalObject] = [proposal]
        discoveries: list[CanonicalObject] = []
        for index, _finding in enumerate(findings):
            discovery = CanonicalObject(
                "discovery_record",
                {
                    "discovery_id": f"disc_{self.stage_id}_{job.lane_slot}_{proposal.digest[:12]}_{index + 1}",
                    "lane_run_ref": _with_ref_class(lane_run_record["ref"], "PRIOR_ACCEPTED_ONLY"),
                    "attempt_ref": _with_ref_class(attempt_record["ref"], "PRIOR_ACCEPTED_ONLY"),
                    "source_generation_ref": _with_ref_class(source_record["ref"], "PRIOR_ACCEPTED_ONLY"),
                    "discovery_input_history_cut": cut,
                    "knowledge_state_ref": _with_ref_class(knowledge_record["ref"], "PRIOR_ACCEPTED_ONLY"),
                    "method_ref": _external_ref(
                        "external_profile_ref",
                        "astra_v21_manual_declared_e3",
                        "HISTORY_CONTEXT_BINDING",
                    ),
                    "producer_ref": _external_ref(
                        "actor_or_authority_ref",
                        f"external_auditor_E3_{job.lane_slot}",
                        "PRIOR_ACCEPTED_ONLY",
                    ),
                    "surface_location_refs": [],
                    "own_observation_refs": [],
                },
            )
            discoveries.append(discovery)
            objects.append(discovery)

        lane_completion = LaneCompletion(
            lane_completion_id=deterministic_id(
                "lane_completion",
                f"manual-e3:{assignment_record['ref']['revision_digest']}:{proposal.digest}",
            ),
            lane_run_ref=_with_ref_class(lane_run_record["ref"], "CONTENT_OR_PRIOR"),
            lane_spec_ref=_with_ref_class(lane_spec_record["ref"], "HISTORY_CONTEXT_BINDING"),
            input_history_cut=cut,
            final_knowledge_state_ref=_with_ref_class(knowledge_record["ref"], "CONTENT_OR_PRIOR"),
            isolation_qualification_ref=_with_ref_class(isolation_record["ref"], "CONTENT_OR_PRIOR"),
            attempt_refs=[_with_ref_class(attempt_record["ref"], "CONTENT_OR_PRIOR")],
            required_output_refs=[proposal.as_ref().as_dict(), *[d.as_ref().as_dict() for d in discoveries]],
            completion_predicate_result="LANE_COMPLETED",
        )
        objects.append(lane_completion.as_object())

        head = self.store.head()
        if head is None:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        command = CommandEnvelope(
            command_id=_command_id(f"manual_e3_result:{assignment_record['ref']['revision_digest']}:{raw_digest}"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit["governing_policy_ref"],
            governing_spec_refs=tuple(prior_commit.get("governing_spec_refs", ())),
            idempotency_scope=f"manual_e3_result:{assignment_record['ref']['revision_digest']}:{raw_digest}",
            campaign_ref=head.campaign_id,
        )
        self.coordinator.accept(command, immutable_objects=objects, expected_head=head)

    def _finalize_stage_completion(self) -> None:
        if self.stage_id == "E2":
            self._finalize_e2_stage_completion()
            return
        if self.stage_id == "E3":
            self._finalize_manual_e3_stage_completion()
            return
        super()._finalize_stage_completion()

    def _collect_completed_stage_inputs(
        self,
    ) -> tuple[
        dict[str, Any],
        dict[str, Any],
        list[dict[str, Any]],
        list[dict[str, Any]],
        dict[str, dict[str, Any]],
    ]:
        cut, _ = _current_cut(self.store)
        required_completion_refs: list[dict[str, Any]] = []
        proposal_refs: list[dict[str, Any]] = []
        stage_run_digests: set[str] = set()
        stage_run_ref: dict[str, Any] | None = None
        stage_spec_ref: dict[str, Any] | None = None
        proposals_by_slot: dict[str, dict[str, Any]] = {}

        lane_completions = tuple(self.store.accepted_records("lane_completion", cut))
        for slot, job in self.batch.jobs.items():
            proposal = self._accepted_result_for_job(job, cut)
            if proposal is None:
                raise ValidationError("STAGE_COMPLETION_BLOCKED", f"Missing accepted result {slot}")
            completion = next(
                (
                    row
                    for row in lane_completions
                    if any(
                        isinstance(ref, dict)
                        and ref.get("revision_digest") == proposal["ref"]["revision_digest"]
                        for ref in row["body"].get("required_output_refs", [])
                    )
                ),
                None,
            )
            if completion is None or completion["body"].get("completion_predicate_result") != "LANE_COMPLETED":
                raise ValidationError("STAGE_COMPLETION_BLOCKED", f"Lane {slot} is not qualified complete")
            required_completion_refs.append(_with_ref_class(completion["ref"], "CONTENT_OR_PRIOR"))
            proposal_refs.append(_with_ref_class(proposal["ref"], "CONTENT_OR_PRIOR"))
            proposals_by_slot[slot] = proposal

            assignment = self.store.resolve_accepted(job.assignment_ref, cut)["body"]
            attempt = self.store.resolve_accepted(assignment["attempt_ref"], cut)["body"]
            lane_run = self.store.resolve_accepted(attempt["lane_run_ref"], cut)["body"]
            current_stage_run_ref = lane_run["stage_run_ref"]
            stage_run_digests.add(current_stage_run_ref["revision_digest"])
            stage_run_ref = _with_ref_class(current_stage_run_ref, "CONTENT_OR_PRIOR")
            stage_spec_ref = _with_ref_class(assignment["stage_spec_ref"], "HISTORY_CONTEXT_BINDING")

        if len(stage_run_digests) != 1 or stage_run_ref is None or stage_spec_ref is None:
            raise ValidationError("STAGE_RUN_BINDING_CONFLICT", self.stage_id)
        return stage_run_ref, stage_spec_ref, required_completion_refs, proposal_refs, proposals_by_slot

    def _finalize_e2_stage_completion(self) -> None:
        cut, prior_commit = _current_cut(self.store)
        (
            stage_run_ref,
            stage_spec_ref,
            required_completion_refs,
            proposal_refs,
            proposals_by_slot,
        ) = self._collect_completed_stage_inputs()

        if set(proposals_by_slot) != {"E2-CONVERGENCE", "E2-ADJUDICATION"}:
            raise ValidationError("E2_REQUIRED_LANE_SET_INVALID")

        convergence_records = proposals_by_slot["E2-CONVERGENCE"]["body"].get("e2_records")
        adjudication_records = proposals_by_slot["E2-ADJUDICATION"]["body"].get("e2_records")

        frozen_result = materialize_e2(
            self.store,
            frozen_cut=self.batch.frozen_history_cut,
            convergence_records=convergence_records,
            adjudication_records=adjudication_records,
        )
        result = materialize_e2(
            self.store,
            frozen_cut=cut,
            convergence_records=convergence_records,
            adjudication_records=adjudication_records,
        )
        frozen_claim_digests = tuple(sorted(claim.digest for claim in frozen_result.finding_claim_revisions))
        current_claim_digests = tuple(sorted(claim.digest for claim in result.finding_claim_revisions))
        if current_claim_digests != frozen_claim_digests:
            raise ValidationError("E2_MATERIALIZATION_VIEW_DRIFT")

        semantic = semantic_objects(result)
        semantic_refs = [obj.as_ref(ref_class="CONTENT_OR_PRIOR").as_dict() for obj in semantic]
        open_findings_count = sum(
            1
            for decision in result.adjudicated_decisions
            if decision.finding_lifecycle_status in {"OPEN", "REOPENED"}
        )
        open_contradictions_count = sum(
            1
            for contradiction in result.contradiction_revisions
            if contradiction.status in {"OPEN", "TESTING", "REOPENED", "BLOCKED"}
        )

        stage_completion = StageCompletion(
            stage_completion_id=deterministic_id(
                "stage_completion",
                (
                    "E2:"
                    + result.completion_digest
                    + ":"
                    + ":".join(sorted(ref["revision_digest"] for ref in required_completion_refs))
                ).encode("utf-8"),
            ),
            stage_run_ref=stage_run_ref,
            stage_spec_ref=stage_spec_ref,
            input_history_cut=cut,
            required_lane_slot_results=required_completion_refs,
            required_output_refs=[*proposal_refs, *semantic_refs],
            mandatory_obligation_summary={
                "required_lanes": len(self.batch.lane_slots),
                "completed_lanes": len(required_completion_refs),
                "finding_claim_revisions": len(result.finding_claim_revisions),
                "finding_axis_assessments": len(result.axis_assessments),
                "finding_adjudication_decisions": len(result.adjudicated_decisions),
                "root_cause_revisions": len(result.root_cause_revisions),
                "contradiction_revisions": len(result.contradiction_revisions),
                "open_findings_count": open_findings_count,
                "open_contradictions_count": open_contradictions_count,
                "semantic_completion_digest": result.completion_digest,
            },
            unresolved_material_refs=[],
            unknown_blocked_summary={
                "unknown_surfaces_count": 0,
                "open_findings_count": open_findings_count,
                "open_contradictions_count": open_contradictions_count,
            },
            completion_predicate_result="STAGE_COMPLETED",
        )
        self._accept_atomic_stage_objects([*semantic, stage_completion.as_object()], prior_commit)

    def _finalize_manual_e3_stage_completion(self) -> None:
        cut, prior_commit = _current_cut(self.store)
        (
            stage_run_ref,
            stage_spec_ref,
            required_completion_refs,
            proposal_refs,
            proposals_by_slot,
        ) = self._collect_completed_stage_inputs()

        expected_slots = {"E3-X", "E3-Y", "E3-Z"}
        if set(proposals_by_slot) != expected_slots:
            raise ValidationError("E3_REQUIRED_LANE_SET_INVALID")

        discovery_refs: list[dict[str, Any]] = []
        declared_isolation_refs: list[dict[str, Any]] = []
        lane_completions = tuple(self.store.accepted_records("lane_completion", cut))
        for slot, job in self.batch.jobs.items():
            assignment = self.store.resolve_accepted(job.assignment_ref, cut)["body"]
            knowledge = self.store.resolve_accepted(assignment["knowledge_state_ref"], cut)["body"]
            isolation = self.store.resolve_accepted(knowledge["isolation_qualification_ref"], cut)
            lane_spec = self.store.resolve_accepted(assignment["lane_spec_ref"], cut)
            if lane_spec["body"].get("required_isolation_assurance") != "ENFORCED":
                raise ValidationError("E3_REQUIRED_ISOLATION_POLICY_DRIFT", slot)
            if isolation["body"].get("result") != "DECLARED":
                raise ValidationError("E3_MANUAL_PROFILE_REQUIRES_DECLARED", slot)
            if _MANUAL_E3_LIMITATION not in set(isolation["body"].get("limitations") or ()):
                raise ValidationError("E3_MANUAL_LIMITATION_MISSING", slot)
            declared_isolation_refs.append(_with_ref_class(isolation["ref"], "CONTENT_OR_PRIOR"))

            proposal = proposals_by_slot[slot]
            completion = next(
                row
                for row in lane_completions
                if any(
                    isinstance(ref, dict)
                    and ref.get("revision_digest") == proposal["ref"]["revision_digest"]
                    for ref in row["body"].get("required_output_refs", [])
                )
            )
            for ref in completion["body"].get("required_output_refs", []):
                if isinstance(ref, dict) and ref.get("kind") == "discovery_record":
                    discovery_refs.append(_with_ref_class(ref, "CONTENT_OR_PRIOR"))

        discovery_refs.sort(key=lambda ref: canonical_bytes(ref))
        blind_body = {
            "profile": _MANUAL_E3_PROFILE,
            "required_isolation_assurance": "ENFORCED",
            "observed_isolation_assurance": "DECLARED",
            "blind_origin_eligible": False,
            "lane_slots": sorted(expected_slots),
            "discovery_refs": discovery_refs,
            "input_history_cut": cut,
        }
        blind_digest = hashlib.sha256(
            b"BDB2/ASTRA_MANUAL_E3_CHECKPOINT/1\0" + canonical_bytes(blind_body)
        ).hexdigest()
        checkpoint = CanonicalObject(
            "checkpoint",
            {
                "checkpoint_id": f"chk_e3_manual_{blind_digest[:16]}",
                "accepted_history_cut": cut,
                "blind_completion_digest": blind_digest,
                "sealed_findings_count": len(discovery_refs),
                "lane_slots": sorted(expected_slots),
            },
        )
        checkpoint_ref = checkpoint.as_ref(ref_class="CONTENT_OR_PRIOR").as_dict()

        stage_completion = StageCompletion(
            stage_completion_id=deterministic_id(
                "stage_completion",
                (
                    "E3:manual-declared:"
                    + blind_digest
                    + ":"
                    + ":".join(sorted(ref["revision_digest"] for ref in required_completion_refs))
                ).encode("utf-8"),
            ),
            stage_run_ref=stage_run_ref,
            stage_spec_ref=stage_spec_ref,
            input_history_cut=cut,
            required_lane_slot_results=required_completion_refs,
            required_output_refs=[*proposal_refs, *discovery_refs, checkpoint_ref],
            mandatory_obligation_summary={
                "required_lanes": len(expected_slots),
                "completed_lanes": len(required_completion_refs),
                "manual_executor_profile": _MANUAL_E3_PROFILE,
                "required_isolation_assurance": "ENFORCED",
                "observed_isolation_assurance": "DECLARED",
                "blind_origin_eligible_count": 0,
                "unknown_isolation_discoveries_count": len(discovery_refs),
                "checkpoint_digest": checkpoint.digest,
                "assurance_limitation_codes": [_MANUAL_E3_LIMITATION],
                "isolation_qualification_refs": declared_isolation_refs,
            },
            unresolved_material_refs=[],
            unknown_blocked_summary={
                "unknown_surfaces_count": 0,
                "unknown_isolation_discoveries_count": len(discovery_refs),
                "assurance_profile": "BOUNDED_MANUAL_DECLARED",
            },
            completion_predicate_result="STAGE_COMPLETED",
        )
        self._accept_atomic_stage_objects([checkpoint, stage_completion.as_object()], prior_commit)

    def _accept_atomic_stage_objects(
        self,
        objects: list[CanonicalObject],
        prior_commit: dict[str, Any],
    ) -> None:
        stage_obj = objects[-1]
        head = self.store.head()
        if head is None:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        command = CommandEnvelope(
            command_id=_command_id("stage_completion:" + stage_obj.digest),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit["governing_policy_ref"],
            governing_spec_refs=tuple(prior_commit.get("governing_spec_refs", ())),
            idempotency_scope="stage_completion:" + stage_obj.digest,
            campaign_ref=head.campaign_id,
        )
        self.coordinator.accept(command, immutable_objects=objects, expected_head=head)
        self.stage_complete = True
        self.stage_completion_digest = stage_obj.digest
        self._load_accepted_state_from_store()


__all__ = ["AstraPostE1ResultInbox"]

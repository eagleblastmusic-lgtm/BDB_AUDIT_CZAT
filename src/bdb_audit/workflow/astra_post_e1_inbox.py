"""Astra post-E1 inbox with atomic R5.3 semantic materialization for E2."""
from __future__ import annotations

from typing import Any

from ..core.errors import ValidationError
from ..core.ids import deterministic_id
from ..history.objects import CommandEnvelope
from ..stop.models import StageCompletion
from .e2_semantics import (
    build_e2_predecessor_view,
    materialize_e2,
    semantic_objects,
    validate_e2_lane_records,
)
from .post_e1_inbox import PostE1ResultInbox
from .inbox import _command_id, _current_cut, _with_ref_class, _same_ref


class AstraPostE1ResultInbox(PostE1ResultInbox):
    """Keep generic E3-E6 ingestion, but make E2 semantically authoritative."""

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

    def _finalize_stage_completion(self) -> None:
        if self.stage_id != "E2":
            super()._finalize_stage_completion()
            return

        cut, prior_commit = _current_cut(self.store)
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
        if set(proposals_by_slot) != {"E2-CONVERGENCE", "E2-ADJUDICATION"}:
            raise ValidationError("E2_REQUIRED_LANE_SET_INVALID")

        result = materialize_e2(
            self.store,
            frozen_cut=self.batch.frozen_history_cut,
            convergence_records=proposals_by_slot["E2-CONVERGENCE"]["body"].get("e2_records"),
            adjudication_records=proposals_by_slot["E2-ADJUDICATION"]["body"].get("e2_records"),
        )
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

        # E2 StageCompletion proves that the convergence/adjudication stage
        # produced its required authoritative outputs.  OPEN findings and
        # contradictions are legitimate carry-forward outputs for later
        # stages/STOP; treating every such object as a stage-local unresolved
        # material blocker would make ordinary E2 completion impossible and
        # collapse StageCompletion into campaign-level assurance.  They remain
        # exact required_output_refs and are counted explicitly below.
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
        stage_obj = stage_completion.as_object()

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
        self.coordinator.accept(
            command,
            immutable_objects=[*semantic, stage_obj],
            expected_head=head,
        )
        self.stage_complete = True
        self.stage_completion_digest = stage_obj.digest
        self._load_accepted_state_from_store()


__all__ = ["AstraPostE1ResultInbox"]

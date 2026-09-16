"""Post-E5 Finalization Service (B02 / §105).

Coordinates:
StopInput -> StopEvaluation -> CampaignConclusion -> FinalAssuranceCase -> ReleaseQualification
strictly through transactional accepted history.

R5.3 temporal rule: each finalization consumer binds only objects that were
already accepted at its command-input history cut.  CampaignConclusion,
FinalAssuranceCase, and ReleaseQualification are therefore three distinct
acceptance boundaries, never one same-commit self-certifying closure.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable, Sequence

from ..history.objects import CommandEnvelope
from ..coordinator import Coordinator
from ..core.errors import ValidationError
from ..core.ids import new_id
from ..history.objects import CanonicalObject
from ..history.store import TransactionalHistoryStore
from ..stop.evaluator import evaluate_stop
from ..stop.input_builder import StopInputBuilder
from ..stop.predicates import validate_stop_evaluation_invariants
from ..workflow.read_models import current_accepted_cut
from .conclusion import CampaignConclusion, FinalAssuranceCase
from .release import ReleaseQualification


class FinalizationService:
    """Post-E5 finalization with explicit prior-accepted temporal boundaries."""

    def __init__(self, store: TransactionalHistoryStore):
        self.store = store
        self.coordinator = Coordinator(store)

    @staticmethod
    def _latest(records: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
        if not records:
            return None
        return max(records, key=lambda record: int(record.get("accepted_seq", 0)))

    @staticmethod
    def _policy_ref_from_cut(cut: dict[str, Any]) -> dict[str, Any]:
        """Derive the exact typed release-policy context binding from a history cut."""
        token = cut.get("governing_policy_ref")
        if not isinstance(token, str) or not token:
            raise ValidationError(
                "RELEASE_POLICY_CONTEXT_REQUIRED",
                "Release qualification requires governing_policy_ref on its assessment cut",
            )
        normalized = token.lower()
        digest = (
            normalized
            if len(normalized) == 64 and all(ch in "0123456789abcdef" for ch in normalized)
            else hashlib.sha256(token.encode("utf-8")).hexdigest()
        )
        return {
            "kind": "policy_revision",
            "revision_digest": digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::policy_revision/1",
            "ref_class": "HISTORY_CONTEXT_BINDING",
        }

    def _prior_commit(self) -> tuple[Any, dict[str, Any]]:
        head = self.store.head()
        if head is None:
            raise ValidationError("EMPTY_STORE", "Finalization requires an accepted campaign head")
        conn = self.store._connect()
        try:
            row = con.execute("SELECT body FROM commits WHERE commit_hash=?", (head.commit_hash,)).fetchone()
            if row is None:
                raise ValidationError("ACCEPTED_HEAD_COMMIT_MISSING")
            return head, json.loads(row[0])
        finally:
            con.close()

    def _accept_one(self, obj: CanonicalObject, scope: str):
        """Accept exactly one finalization artifact against the current head."""
        head, prior_commit = self._prior_commit()
        h = hashlib.sha256(
            f"{head.campaign_id}_{scope}_{head.commit_seq}_{obj.digest}".encode("utf-8")
        ).hexdigest()
        command_id = f"command_{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"
        cmd = CommandEnvelope(
            command_id=command_id,
            command_kind="RECORD_ASSURANCE_DECISION",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit.get(
                "governing_policy_ref", "pin:initial_governing_policy_ref"
            ),
            governing_spec_refs=tuple(
                prior_commit.get("governing_spec_refs", ("pin:initial_transition_profile_ref",))
            ),
            idempotency_scope=f"{scope}_{obj.digest[:16]}",
            campaign_ref=head.campaign_id,
        )
        return self.coordinator.accept(cmd, immutable_objects=[obj])

    def _matching_record(
        self,
        kind: str,
        cut: dict[str, Any],
        predicate: Callable[[dict[str, Any]], bool],
    ) -> dict[str, Any] | None:
        records = self.store.accepted_records(kind, cut)
        return self._latest([record for record in records if predicate(record["body"])])

    def evaluate_stop_gate(
        self,
        evaluation_context: str = "FINAL_POST_E5",
        candidate_assurance_case_ref: dict[str, Any] | None = None,
        challenger_refs: Sequence[dict[str, Any]] = (),
        unknown_blocked_summary: dict[str, Any] | None = None,
        e6_plan_approved: bool = False,
    ) -> dict[str, Any]:
        """Build exact StopInput from history cut, evaluate, and accept StopEvaluation."""
        head = self.store.head()
        if head is None:
            raise ValidationError("EMPTY_STORE", "Cannot evaluate STOP on empty store")

        stop_input = StopInputBuilder.build_from_store(
            self.store,
            evaluation_context=evaluation_context,
            candidate_assurance_case_ref=candidate_assurance_case_ref,
            challenger_refs=challenger_refs,
            unknown_blocked_summary=unknown_blocked_summary,
            e6_plan_approved=e6_plan_approved,
        )

        evaluation = evaluate_stop(
            stop_input,
            e6_plan_approved=e6_plan_approved,
        )
        validate_stop_evaluation_invariants(stop_input, evaluation)

        eval_obj = evaluation.as_object()

        h = hashlib.sha256(
            f"{head.campaign_id}_stop_eval_{head.commit_seq}_{int(time.time())}".encode("utf-8")
        ).hexdigest()
        command_id = f"command_{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"

        conn = self.store._connect()
        try:
            row = conn.execute("SELECT body FROM commits WHERE commit_hash=?", (head.commit_hash,)).fetchone()
            prior_commit = json.loads(row[0]) if row else {}
        finally:
            conn.close()

        stop_input_obj = stop_input.as_object()

        # StopInput and its derived StopEvaluation belong to one evaluation
        # command.  The temporal split starts after the accepted STOP decision.
        cmd = CommandEnvelope(
            command_id=command_id,
            command_kind="RECORD_ASSURANCE_DECISION",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit.get(
                "governing_policy_ref", "pin:initial_governing_policy_ref"
            ),
            governing_spec_refs=tuple(
                prior_commit.get("governing_spec_refs", ("pin:initial_transition_profile_ref",))
            ),
            idempotency_scope=f"stop_eval_{eval_obj.digest[:16]}",
            campaign_ref=head.campaign_id,
        )
        snap_obj = getattr(stop_input, "_snapshot_obj", None)
        objs = [stop_input_obj, eval_obj]
        if snap_obj is not None:
            objs.insert(0, snap_obj)

        res = self.coordinator.accept(cmd, immutable_objects=objs)

        return {
            "status": "SUCCESS",
            "continuation_decision": evaluation.continuation_decision,
            "assurance_level": evaluation.assurance_level,
            "release_readiness": evaluation.release_readiness,
            "stop_evaluation_digest": eval_obj.digest,
            "commit_seq": res.head.commit_seq,
            "commit_hash": res.head.commit_hash,
        }

    def conclude_campaign(
        self,
        termination_state: str | None = None,
        bounded_statement: str = "Campaign concluded via post-E5 finalization",
    ) -> dict[str, Any]:
        """Conclude and qualify through three resumable prior-accepted boundaries."""
        head = self.store.head()
        if head is None:
            raise ValidationError("EMPTY_STORE", "Cannot conclude an empty store")
        cut = current_accepted_cut(self.store)

        stop_eval_record = self._latest(self.store.accepted_records("stop_evaluation", cut))
        if stop_eval_record is None:
            if termination_state == "COMPLETED":
                raise ValidationError(
                    "STOP_EVALUATION_REQUIRED",
                    "Cannot conclude campaign without prior accepted stop_evaluation",
                )
            self.evaluate_stop_gate(evaluation_context="FINAL_POST_E5")
            cut = current_accepted_cut(self.store)
            stop_eval_record = self._latest(self.store.accepted_records("stop_evaluation", cut))
            if stop_eval_record is None:
                raise ValidationError(
                    "STOP_EVALUATION_REQUIRED",
                    "Cannot conclude campaign without prior accepted stop_evaluation",
                )

        stop_eval_body = stop_eval_record["body"]
        stop_eval_ref = dict(stop_eval_record["ref"], ref_class="PRIOR_ACCEPTED_ONLY")
        stop_digest = stop_eval_ref["revision_digest"]

        stop_input_ref = stop_eval_body.get("stop_input_ref")
        if not isinstance(stop_input_ref, dict):
            raise ValidationError(
                "STOP_INPUT_REFERENCE_REQUIRED",
                "Accepted StopEvaluation must bind an accepted StopInput",
            )
        stop_input_record = self.store.resolve_accepted(stop_input_ref, cut)
        stop_release_policy_ref = stop_input_record["body"].get("release_policy_ref")
        if not isinstance(stop_release_policy_ref, dict):
            raise ValidationError(
                "RELEASE_POLICY_CONTEXT_REQUIRED",
                "Accepted StopInput must carry release_policy_ref",
            )

        decision = stop_eval_body.get("continuation_decision")
        assurance = stop_eval_body.get("assurance_level")
        readiness = stop_eval_body.get("release_readiness")

        if termination_state is None:
            if decision == "PASS" and assurance == "ADEQUATE_FOR_DECLARED_SCOPE":
                termination_state = "COMPLETED"
            else:
                termination_state = "COMPLETED_LIMITED"

        if termination_state == "COMPLETED":
            if decision != "PASS":
                raise ValidationError(
                    "COMPLETED_REQUIRES_STOP_PASS",
                    f"Cannot conclude as COMPLETED when STOP decision is {decision}",
                )
            if assurance != "ADEQUATE_FOR_DECLARED_SCOPE":
                raise ValidationError(
                    "COMPLETED_REQUIRES_ADEQUATE_ASSURANCE",
                    f"Cannot conclude as COMPLETED when assurance is {assurance}",
                )

        # All basis refs below are resolved from the same pre-conclusion cut.
        cut = current_accepted_cut(self.store)
        head = self.store.head()
        assert head is not None
        camp_ref = {
            "kind": "campaign_ref",
            "revision_digest": hashlib.sha256(head.campaign_id.encode("utf-8")).hexdigest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_TARGET/campaign_ref",
            "ref_class": "PRIOR_ACCEPTED_ONLY",
        }

        sg_record = self._latest(self.store.accepted_records("source_generation", cut))
        if sg_record is None:
            si_record = self._latest(self.store.accepted_records("source_identity", cut))
            if si_record is None:
                raise ValidationError(
                    "SOURCE_GENERATION_REQUIRED",
                    "Finalization requires a prior accepted source generation",
                )
            sg_ref = dict(si_record["ref"], ref_class="PRIOR_ACCEPTED_ONLY")
        else:
            sg_ref = dict(sg_record["ref"], ref_class="PRIOR_ACCEPTED_ONLY")

        cac_record = self._latest(self.store.accepted_records("candidate_assurance_case", cut))
        cac_ref = (
            dict(cac_record["ref"], ref_class="PRIOR_ACCEPTED_ONLY")
            if cac_record is not None
            else None
        )

        basis_refs: tuple[dict[str, Any], ...] = ()
        if termination_state == "COMPLETED_LIMITED":
            basis_refs = (stop_eval_ref,)

        # Boundary 1: CampaignConclusion consumes only the already accepted STOP
        # and pre-existing basis visible on conclusion_command_input_history_cut.
        existing_conclusion = self._matching_record(
            "campaign_conclusion",
            cut,
            lambda body: body.get("stop_evaluation_ref", {}).get("revision_digest") == stop_digest,
        )
        if existing_conclusion is not None:
            concl_body = existing_conclusion["body"]
            if (
                concl_body.get("termination_state") != termination_state
                or concl_body.get("bounded_conclusion_statement") != bounded_statement
            ):
                raise ValidationError(
                    "FINALIZATION_REPLAY_CONFLICT",
                    "An accepted conclusion already exists for this STOP with different semantics",
                )
            concl_ref = dict(existing_conclusion["ref"], ref_class="PRIOR_ACCEPTED_ONLY")
            concl_digest = concl_ref["revision_digest"]
            conclusion_commit_seq = int(existing_conclusion["accepted_seq"])
        else:
            conclusion = CampaignConclusion(
                campaign_conclusion_id=new_id("campaign_conclusion"),
                campaign_ref=camp_ref,
                source_generation_ref=sg_ref,
                stop_evaluation_ref=stop_eval_ref,
                termination_state=termination_state,
                assurance_level=assurance,
                bounded_conclusion_statement=bounded_statement,
                conclusion_command_input_history_cut=cut,
                candidate_assurance_case_ref=cac_ref,
                limited_conclusion_basis_refs=basis_refs,
            )
            concl_obj = CanonicalObject(
                "campaign_conclusion",
                conclusion.body(),
                logical_id=conclusion.campaign_conclusion_id,
            )
            conclusion_res = self._accept_one(concl_obj, "campaign_conclusion")
            concl_ref = dict(concl_obj.as_ref().as_dict(), ref_class="PRIOR_ACCEPTED_ONLY")
            concl_digest = concl_obj.digest
            conclusion_commit_seq = conclusion_res.head.commit_seq

        # Boundary 2: refresh history; CampaignConclusion must now be accepted.
        final_case_cut = current_accepted_cut(self.store)
        existing_final = self._matching_record(
            "final_assurance_case",
            final_case_cut,
            lambda body: (
                body.get("campaign_conclusion_ref", {}).get("revision_digest") == concl_digest
                and body.get("stop_evaluation_ref", {}).get("revision_digest") == stop_digest
            ),
        )
        stmt_ref = {
            "kind": "public_conclusion_statement_ref",
            "revision_digest": hashlib.sha256(bounded_statement.encode("utf-8")).hexdigest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_TARGET/public_conclusion_statement_ref",
            "ref_class": "PRIOR_ACCEPTED_ONLY",
        }
        if existing_final is not None:
            final_body = existing_final["body"]
            if final_body.get("public_conclusion_statement_ref", {}).get("revision_digest") != stmt_ref["revision_digest"]:
                raise ValidationError(
                    "FINALIZATION_REPLAY_CONFLICT",
                    "An accepted final assurance case exists with a different public conclusion statement",
                )
            final_ref = dict(existing_final["ref"], ref_class="PRIOR_ACCEPTED_ONLY")
            final_digest = final_ref["revision_digest"]
            final_case_commit_seq = int(existing_final["accepted_seq"])
        else:
            final_case = FinalAssuranceCase(
                final_assurance_case_id=new_id("final_assurance_case"),
                campaign_conclusion_ref=concl_ref,
                stop_evaluation_ref=stop_eval_ref,
                public_conclusion_statement_ref=stmt_ref,
                final_case_input_history_cut=final_case_cut,
                candidate_assurance_case_ref=cac_ref,
            )
            final_obj = CanonicalObject(
                "final_assurance_case",
                final_case.body(),
                logical_id=final_case.final_assurance_case_id,
            )
            final_res = self._accept_one(final_obj, "final_assurance_case")
            final_ref = dict(final_obj.as_ref().as_dict(), ref_class="PRIOR_ACCEPTED_ONLY")
            final_digest = final_obj.digest
            final_case_commit_seq = final_res.head.commit_seq

        # Boundary 3: refresh again; ReleaseQualification can only consume an
        # already accepted FinalAssuranceCase and CampaignConclusion.
        qualification_cut = current_accepted_cut(self.store)
        qualification_policy_ref = self._policy_ref_from_cut(qualification_cut)
        if stop_release_policy_ref != qualification_policy_ref:
            raise ValidationError(
                "DRIFT_DETECTED_MATERIALIZATION_INVALID",
                "STOP_AXIS_MATERIALIZATION cannot cross a release-policy context change",
            )

        existing_qualification = self._matching_record(
            "release_qualification",
            qualification_cut,
            lambda body: (
                body.get("campaign_conclusion_ref", {}).get("revision_digest") == concl_digest
                and body.get("final_assurance_case_ref", {}).get("revision_digest") == final_digest
                and body.get("stop_evaluation_ref", {}).get("revision_digest") == stop_digest
                and body.get("assessment_basis") == "STOP_AXIS_MATERIALIZATION"
            ),
        )
        rel_result = readiness if termination_state == "COMPLETED" else "QUALIFICATION_BLOCKED"
        if existing_qualification is not None:
            existing_body = existing_qualification["body"]
            if existing_body.get("result") != rel_result:
                raise ValidationError(
                    "FINALIZATION_REPLAY_CONFLICT",
                    "An accepted release qualification exists with a different result",
                )
            if existing_body.get("release_policy_ref") != qualification_policy_ref:
                raise ValidationError(
                    "RELEASE_POLICY_BINDING_MISMATCH",
                    "Accepted release qualification does not bind the governing release policy",
                )
            rel_digest = existing_qualification["ref"]["revision_digest"]
            qualification_commit_seq = int(existing_qualification["accepted_seq"])
            final_head = self.store.head()
            assert final_head is not None
        else:
            rel_qual = ReleaseQualification(
                release_qualification_id=new_id("release_qualification"),
                campaign_conclusion_ref=concl_ref,
                final_assurance_case_ref=final_ref,
                stop_evaluation_ref=stop_eval_ref,
                source_generation_ref=sg_ref,
                release_policy_ref=qualification_policy_ref,
                release_assessment_basis_cut=qualification_cut,
                qualification_command_input_history_cut=qualification_cut,
                assessment_basis="STOP_AXIS_MATERIALIZATION",
                result=rel_result,
            )
            rel_obj = CanonicalObject(
                "release_qualification",
                rel_qual.body(),
                logical_id=rel_qual.release_qualification_id,
            )
            qualification_res = self._accept_one(rel_obj, "release_qualification")
            rel_digest = rel_obj.digest
            qualification_commit_seq = qualification_res.head.commit_seq
            final_head = qualification_res.head

        return {
            "status": "SUCCESS",
            "termination_state": termination_state,
            "assurance_level": assurance,
            "release_readiness": rel_result,
            "campaign_conclusion_digest": concl_digest,
            "final_assurance_case_digest": final_digest,
            "release_qualification_digest": rel_digest,
            "campaign_conclusion_commit_seq": conclusion_commit_seq,
            "final_assurance_case_commit_seq": final_case_commit_seq,
            "release_qualification_commit_seq": qualification_commit_seq,
            "commit_seq": final_head.commit_seq,
            "commit_hash": final_head.commit_hash,
        }

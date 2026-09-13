"""Post-E5 Finalization Service (B02 / §105).

Coordinates:
StopInput -> StopEvaluation -> CampaignConclusion -> FinalAssuranceCase -> ReleaseQualification
strictly through transactional accepted history.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any, Sequence

from ..history.objects import CommandEnvelope
from ..coordinator import Coordinator
from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id
from ..history.objects import CanonicalObject
from ..history.store import TransactionalHistoryStore
from ..stop.evaluator import evaluate_stop
from ..stop.input_builder import StopInputBuilder
from ..stop.models import StopEvaluation, StopInput
from ..stop.predicates import validate_stop_evaluation_invariants
from ..workflow.read_models import current_accepted_cut
from .conclusion import CampaignConclusion, FinalAssuranceCase
from .release import ReleaseLifecycleManager, ReleaseQualification


class FinalizationService:
    """Transactional post-E5 finalization and release assessment."""

    def __init__(self, store: TransactionalHistoryStore):
        self.store = store
        self.coordinator = Coordinator(store)

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

        h = hashlib.sha256(f"{head.campaign_id}_stop_eval_{head.commit_seq}_{int(time.time())}".encode("utf-8")).hexdigest()
        command_id = f"command_{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"

        conn = self.store._connect()
        try:
            row = conn.execute("SELECT body FROM commits WHERE commit_hash=?", (head.commit_hash,)).fetchone()
            prior_commit = json.loads(row[0]) if row else {}
        finally:
            conn.close()

        stop_input_obj = stop_input.as_object()

        # Commit StopInput and StopEvaluation into history
        cmd = CommandEnvelope(
            command_id=command_id,
            command_kind="RECORD_ASSURANCE_DECISION",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit.get("governing_policy_ref", "pin:initial_governing_policy_ref"),
            governing_spec_refs=tuple(prior_commit.get("governing_spec_refs", ("pin:initial_transition_profile_ref",))),
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
        """Conclude campaign based on accepted StopEvaluation and evaluate release qualification."""
        head = self.store.head()
        if head is None:
            raise ValidationError("EMPTY_STORE", "Cannot conclude an empty store")
        cut = current_accepted_cut(self.store)

        stop_eval_records = self.store.accepted_records("stop_evaluation", cut)
        if not stop_eval_records:
            if termination_state == "COMPLETED":
                raise ValidationError(
                    "STOP_EVALUATION_REQUIRED",
                    "Cannot conclude campaign without prior accepted stop_evaluation",
                )
            self.evaluate_stop_gate(evaluation_context="FINAL_POST_E5")
            head = self.store.head()
            cut = current_accepted_cut(self.store)
            stop_eval_records = self.store.accepted_records("stop_evaluation", cut)
            if not stop_eval_records:
                raise ValidationError(
                    "STOP_EVALUATION_REQUIRED",
                    "Cannot conclude campaign without prior accepted stop_evaluation",
                )
        latest_stop_row = stop_eval_records[-1]
        stop_eval_body = latest_stop_row["body"]
        stop_eval_ref = dict(latest_stop_row["ref"], ref_class="PRIOR_ACCEPTED_ONLY")

        decision = stop_eval_body.get("continuation_decision")
        assurance = stop_eval_body.get("assurance_level")
        readiness = stop_eval_body.get("release_readiness")

        # Resolve termination state
        if termination_state is None:
            if decision == "PASS" and assurance == "ADEQUATE_FOR_DECLARED_SCOPE":
                termination_state = "COMPLETED"
            else:
                termination_state = "COMPLETED_LIMITED"

        # Anti-false-PASS: COMPLETED requires PASS and ADEQUATE_FOR_DECLARED_SCOPE
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

        camp_ref = {
            "kind": "campaign_ref",
            "revision_digest": hashlib.sha256(head.campaign_id.encode("utf-8")).hexdigest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_TARGET/campaign_ref",
            "ref_class": "PRIOR_ACCEPTED_ONLY",
        }

        sg_records = self.store.accepted_records("source_generation", cut)
        if not sg_records:
            si_records = self.store.accepted_records("source_identity", cut)
            sg_ref = dict(si_records[-1]["ref"], ref_class="PRIOR_ACCEPTED_ONLY") if si_records else {
                "kind": "source_generation",
                "revision_digest": "0" * 64,
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_generation/1",
                "ref_class": "PRIOR_ACCEPTED_ONLY",
            }
        else:
            sg_ref = dict(sg_records[-1]["ref"], ref_class="PRIOR_ACCEPTED_ONLY")

        cac_records = self.store.accepted_records("candidate_assurance_case", cut)
        cac_ref = dict(cac_records[-1]["ref"], ref_class="PRIOR_ACCEPTED_ONLY") if cac_records else None

        basis_refs: tuple[dict[str, Any], ...] = ()
        if termination_state == "COMPLETED_LIMITED":
            basis_refs = (stop_eval_ref,)

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
        concl_obj = CanonicalObject("campaign_conclusion", conclusion.body(), logical_id=conclusion.campaign_conclusion_id)
        concl_prior_ref = dict(concl_obj.as_ref().as_dict(), ref_class="PRIOR_ACCEPTED_ONLY")

        # Build FinalAssuranceCase
        stmt_ref = {
            "kind": "public_conclusion_statement_ref",
            "revision_digest": hashlib.sha256(bounded_statement.encode("utf-8")).hexdigest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_TARGET/public_conclusion_statement_ref",
            "ref_class": "PRIOR_ACCEPTED_ONLY",
        }
        final_case = FinalAssuranceCase(
            final_assurance_case_id=new_id("final_assurance_case"),
            campaign_conclusion_ref=concl_prior_ref,
            stop_evaluation_ref=stop_eval_ref,
            public_conclusion_statement_ref=stmt_ref,
            final_case_input_history_cut=cut,
            candidate_assurance_case_ref=cac_ref,
        )
        final_obj = CanonicalObject("final_assurance_case", final_case.body(), logical_id=final_case.final_assurance_case_id)
        final_prior_ref = dict(final_obj.as_ref().as_dict(), ref_class="PRIOR_ACCEPTED_ONLY")

        # Build ReleaseQualification
        pol_ref = {
            "kind": "policy_revision",
            "revision_digest": "1" * 64,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_TARGET/policy_revision",
            "ref_class": "HISTORY_CONTEXT_BINDING",
        }
        rel_result = readiness if termination_state == "COMPLETED" else "QUALIFICATION_BLOCKED"
        rel_qual = ReleaseQualification(
            release_qualification_id=new_id("release_qualification"),
            campaign_conclusion_ref=concl_prior_ref,
            final_assurance_case_ref=final_prior_ref,
            stop_evaluation_ref=stop_eval_ref,
            source_generation_ref=sg_ref,
            release_policy_ref=pol_ref,
            release_assessment_basis_cut=cut,
            qualification_command_input_history_cut=cut,
            assessment_basis="STOP_AXIS_MATERIALIZATION",
            result=rel_result,
        )
        rel_obj = CanonicalObject("release_qualification", rel_qual.body(), logical_id=rel_qual.release_qualification_id)

        h = hashlib.sha256(f"{head.campaign_id}_conclude_{head.commit_seq}_{int(time.time())}".encode("utf-8")).hexdigest()
        command_id = f"command_{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"

        conn = self.store._connect()
        try:
            row = conn.execute("SELECT body FROM commits WHERE commit_hash=?", (head.commit_hash,)).fetchone()
            prior_commit = json.loads(row[0]) if row else {}
        finally:
            conn.close()

        # Commit conclusion, final case, and release qualification atomically
        cmd = CommandEnvelope(
            command_id=command_id,
            command_kind="RECORD_ASSURANCE_DECISION",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit.get("governing_policy_ref", "pin:initial_governing_policy_ref"),
            governing_spec_refs=tuple(prior_commit.get("governing_spec_refs", ("pin:initial_transition_profile_ref",))),
            idempotency_scope=f"conclude_{concl_obj.digest[:16]}",
            campaign_ref=head.campaign_id,
        )
        res = self.coordinator.accept(cmd, immutable_objects=[concl_obj, final_obj, rel_obj])

        return {
            "status": "SUCCESS",
            "termination_state": termination_state,
            "assurance_level": assurance,
            "release_readiness": rel_result,
            "campaign_conclusion_digest": concl_obj.digest,
            "final_assurance_case_digest": final_obj.digest,
            "release_qualification_digest": rel_obj.digest,
            "commit_seq": res.head.commit_seq,
            "commit_hash": res.head.commit_hash,
        }

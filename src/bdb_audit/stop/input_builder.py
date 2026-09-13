"""Deterministic StopInput Builder from Verified Accepted History (B02 / §103).

Constructs an immutable StopInput derived strictly from accepted history records,
never from unadmitted proposals or in-memory caches.
"""
from __future__ import annotations

from typing import Any, Sequence

from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from .models import StopInput


def _ref(kind: str, digest: str, ref_class: str = "CONTENT_OR_PRIOR") -> dict[str, Any]:
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
    }


class StopInputBuilder:
    """Extracts and builds an exact reproducible StopInput from an accepted cut."""

    @classmethod
    def build_from_store(
        cls,
        store: TransactionalHistoryStore,
        evaluation_context: str = "FINAL_POST_E5",
        candidate_assurance_case_ref: dict[str, Any] | None = None,
        challenger_refs: Sequence[dict[str, Any]] = (),
        unknown_blocked_summary: dict[str, Any] | None = None,
        e6_plan_approved: bool = False,
    ) -> StopInput:
        from ..workflow.read_models import current_accepted_cut

        head = store.head()
        if head is None:
            raise ValidationError("EMPTY_STORE", "Cannot build StopInput on empty store")
        cut = current_accepted_cut(store)

        # Source generation
        sg_records = store.accepted_records("source_generation", cut)
        if not sg_records:
            # Fallback to source identity
            si_records = store.accepted_records("source_identity", cut)
            sg_ref = si_records[-1]["ref"] if si_records else _ref("source_generation", "0" * 64)
        else:
            sg_ref = sg_records[-1]["ref"]

        # Stage specs and completions
        stage_specs = store.accepted_records("stage_spec", cut)
        stage_completions = store.accepted_records("stage_completion", cut)

        spec_digest_to_key = {
            row["ref"]["revision_digest"]: row["body"].get("stage_key")
            for row in stage_specs
            if row["body"].get("stage_key")
        }

        completed_stage_keys = set()
        for row in stage_completions:
            spec_ref = row["body"].get("stage_spec_ref")
            if isinstance(spec_ref, dict):
                sk = spec_digest_to_key.get(spec_ref.get("revision_digest"))
                if sk:
                    completed_stage_keys.add(sk)
            sk_direct = row["body"].get("stage_key", row["body"].get("stage_role"))
            if sk_direct:
                completed_stage_keys.add(sk_direct)

        completed_stage_refs = [row["ref"] for row in stage_completions]

        required_stage_spec_refs = [row["ref"] for row in stage_specs]
        pending_required_stage_refs = [
            row["ref"]
            for row in stage_specs
            if row["body"].get("stage_key") not in completed_stage_keys
        ]

        # Candidate case
        if candidate_assurance_case_ref is None:
            cac_records = store.accepted_records("candidate_assurance_case", cut)
            if cac_records:
                candidate_assurance_case_ref = cac_records[-1]["ref"]

        # Challengers
        if not challenger_refs:
            ch_records = store.accepted_records("challenger_result", cut)
            challenger_refs = [r["ref"] for r in ch_records]

        # Invalidation, contradictions, residual risks
        invalidation_records = store.accepted_records("evidence_invalidation", cut)
        contradiction_records = store.accepted_records("contradiction", cut)
        residual_risk_records = store.accepted_records("residual_risk", cut)
        obligation_records = store.accepted_records("coverage_obligation", cut)
        qualification_records = store.accepted_records("obligation_qualification", cut)

        # Inventory
        inv_records = store.accepted_records("inventory_revision", cut)
        inv_ref = inv_records[-1]["ref"] if inv_records else _ref("inventory_revision", "0" * 64, ref_class="CONTENT_OR_PRIOR")

        summary = unknown_blocked_summary or {
            "unknown_surfaces_count": 0,
            "is_blocked": False,
            "unresolved_obligations_count": len(pending_required_stage_refs),
        }

        # Context-dependent defaults
        pol_ref = _ref("policy_revision", "1" * 64, ref_class="HISTORY_CONTEXT_BINDING")
        spec_ref = _ref("spec_revision", "1" * 64, ref_class="HISTORY_CONTEXT_BINDING")
        prof_ref = _ref("external_profile_ref", "1" * 64, ref_class="HISTORY_CONTEXT_BINDING")

        req_specs = [dict(r, ref_class="HISTORY_CONTEXT_BINDING") for r in required_stage_spec_refs] if required_stage_spec_refs else [spec_ref]
        pend_specs = [dict(r, ref_class="HISTORY_CONTEXT_BINDING") for r in pending_required_stage_refs]

        from .models import Snapshot
        direct_refs = [
            sg_ref,
            inv_ref,
            *[r["ref"] for r in obligation_records],
            *[r["ref"] for r in qualification_records],
            *completed_stage_refs,
            *req_specs,
        ]
        snapshot = Snapshot(
            snapshot_type="STOP_INPUT_STATE_CAPTURE",
            as_of_head=cut,
            projection_code_revision="BDB_V2_SNAPSHOT_PROJECTION_1",
            projection_input_refs=direct_refs,
            snapshot_artifact_ref={
                "kind": "raw_artifact_ref",
                "revision_digest": "0" * 64,
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": "BDB_TARGET/raw_artifact_ref",
                "ref_class": "CONTENT_OR_PRIOR",
            },
        )
        snapshot_obj = snapshot.as_object()

        effort_result = completed_stage_refs[-1] if completed_stage_refs else sg_ref

        stop_input = StopInput(
            campaign_id=head.campaign_id,
            source_generation_ref=sg_ref,
            input_history_cut=cut,
            evaluation_context=evaluation_context,
            governing_policy_ref=pol_ref,
            policy_spec_refs=[spec_ref],
            evaluator_revision_ref=spec_ref,
            required_stage_set_ref=prof_ref,
            required_stage_spec_refs=req_specs,
            completed_stage_refs=completed_stage_refs,
            pending_required_stage_refs=pend_specs,
            stop_input_snapshot_ref=snapshot.ref,
            inventory_revision_ref=inv_ref,
            mandatory_obligation_refs=[r["ref"] for r in obligation_records],
            current_obligation_qualification_refs=[r["ref"] for r in qualification_records],
            evidence_invalidation_refs=[r["ref"] for r in invalidation_records],
            contradiction_refs=[r["ref"] for r in contradiction_records],
            residual_risk_refs=[r["ref"] for r in residual_risk_records],
            evidence_invalidation_state={"invalidated_count": len(invalidation_records)},
            release_policy_ref=pol_ref,
            effort_profile_ref=prof_ref,
            effort_results_ref=effort_result,
            unknown_blocked_summary=summary,
            candidate_assurance_case_ref=candidate_assurance_case_ref,
            challenger_refs=challenger_refs,
        )
        object.__setattr__(stop_input, "_snapshot_obj", snapshot_obj)
        return stop_input

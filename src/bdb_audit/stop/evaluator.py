"""Pure STOP evaluator over immutable StopInput (M24 / PR-027 / M44 / §103 / Data Contracts §76).

Normative decision axes:
- continuation_decision: PASS | CONTINUE_REQUIRED | E6_REQUIRED | BLOCKED
- assurance_level: ADEQUATE_FOR_DECLARED_SCOPE | BOUNDED | INSUFFICIENT
- release_readiness: READY | READY_WITH_RESIDUAL_RISK | TECHNICALLY_NOT_READY | QUALIFICATION_BLOCKED

Input model distinguishes:
- UNKNOWN / UNKNOWN_SURFACE_SCOPE
- BLOCKED
- INSUFFICIENT_DATA
- NOT_APPLICABLE
- WAIVED
- ACCEPTED_RESIDUAL_RISK
- OPEN_CONTRADICTION / TESTING_CONTRADICTION
- INVALIDATED_EVIDENCE

Normative invariants:
- UNKNOWN cannot silently become PASS
- BLOCKED cannot silently become PASS
- Insufficient data cannot be treated as success
- Invalidated evidence cannot be ignored
- Open contradictions cannot be ignored
- Unknown surface scope cannot be removed from denominator
- Campaign termination (termination_state) is a separate decision in CampaignConclusion
- COMPLETED_LIMITED is NOT a 5th STOP outcome and does NOT turn BLOCKED into PASS
"""
from __future__ import annotations

from typing import Any, Sequence

from ..core.errors import ValidationError
from .models import StopInput, StopEvaluation


def evaluate_stop(
    stop_input: StopInput,
    *,
    force_blocked: bool = False,
    blocker_reason: str | None = None,
    insufficient_data: bool | None = None,
    e6_plan_approved: bool = False,
    stop_evaluation_id: str | None = None,
) -> StopEvaluation:
    """Evaluate pure StopInput deterministically according to normative precedence rules.

    Precedence:
    1. Authority / admission / cut failure -> BLOCKED + INSUFFICIENT + QUALIFICATION_BLOCKED
    2. Invalidated evidence / contradictions -> BLOCKED + INSUFFICIENT + QUALIFICATION_BLOCKED
    3. INTERMEDIATE context -> CONTINUE_REQUIRED (PASS / E6_REQUIRED strictly forbidden)
    4. Pending required stages E1-E5 -> CONTINUE_REQUIRED + REQUIRED_STAGES_PENDING
    5. Post-E5 material gaps with approved plan -> E6_REQUIRED + BOUNDED
    6. Complete satisfaction -> PASS + ADEQUATE_FOR_DECLARED_SCOPE
    """
    ctx = stop_input.evaluation_context
    if insufficient_data is None:
        insufficient_data = (ctx == "INTERMEDIATE")
    input_ref = stop_input.ref
    ub_summary = dict(stop_input.unknown_blocked_summary or {})

    # 1. Authority / blocker failure
    if force_blocked or ub_summary.get("is_blocked", False):
        code = blocker_reason or "AUTHORITY_OR_ADMISSION_BLOCKED"
        return StopEvaluation(
            stop_evaluation_id=stop_evaluation_id,
            stop_input_ref=input_ref,
            continuation_decision="BLOCKED",
            assurance_level="INSUFFICIENT",
            release_readiness="QUALIFICATION_BLOCKED",
            reason_codes=(code,),
            blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
        )

    # 2. Unknown surface scope / unknown mandatory conditions cannot be PASS
    has_unknown_scope = ub_summary.get("unknown_surfaces_count", 0) > 0 or ub_summary.get("has_unknown_scope", False)
    if has_unknown_scope and ctx in ("FINAL_POST_E5", "POST_E6"):
        if e6_plan_approved:
            return StopEvaluation(
                stop_evaluation_id=stop_evaluation_id,
                stop_input_ref=input_ref,
                continuation_decision="E6_REQUIRED",
                assurance_level="BOUNDED",
                release_readiness="QUALIFICATION_BLOCKED",
                reason_codes=("UNKNOWN_SURFACE_SCOPE", "E6_REQUIRED_TO_RESOLVE_SCOPE"),
                blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )
        return StopEvaluation(
            stop_evaluation_id=stop_evaluation_id,
            stop_input_ref=input_ref,
            continuation_decision="BLOCKED",
            assurance_level="INSUFFICIENT",
            release_readiness="QUALIFICATION_BLOCKED",
            reason_codes=("UNKNOWN_SURFACE_SCOPE",),
            blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
        )

    # 3. INTERMEDIATE context: used before completion of ordinary E1–E5.
    # PASS and E6_REQUIRED are forbidden.
    if ctx == "INTERMEDIATE":
        reasons = []
        if stop_input.pending_required_stage_refs:
            reasons.append("REQUIRED_STAGES_PENDING")
        if insufficient_data or ub_summary.get("insufficient_data", False):
            reasons.append("INSUFFICIENT_DATA")
        if stop_input.evidence_invalidation_refs:
            reasons.append("INVALIDATED_EVIDENCE_PENDING")
        if not reasons:
            reasons.append("INTERMEDIATE_STAGE_EVALUATION")

        return StopEvaluation(
            stop_evaluation_id=stop_evaluation_id,
            stop_input_ref=input_ref,
            continuation_decision="CONTINUE_REQUIRED",
            assurance_level="INSUFFICIENT",
            release_readiness="TECHNICALLY_NOT_READY",
            reason_codes=tuple(reasons),
            blocking_obligation_refs=(),
            remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
        )

    # 4. FINAL_POST_E5 context
    if ctx == "FINAL_POST_E5":
        # Check pending stages
        if stop_input.pending_required_stage_refs:
            reasons = ["REQUIRED_STAGES_PENDING"]
            if insufficient_data:
                reasons.append("INSUFFICIENT_DATA")
            return StopEvaluation(
                stop_evaluation_id=stop_evaluation_id,
                stop_input_ref=input_ref,
                continuation_decision="CONTINUE_REQUIRED",
                assurance_level="INSUFFICIENT",
                release_readiness="TECHNICALLY_NOT_READY",
                reason_codes=tuple(reasons),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )

        # Unresolved evidence invalidation -> BLOCKED
        if stop_input.evidence_invalidation_refs:
            return StopEvaluation(
                stop_evaluation_id=stop_evaluation_id,
                stop_input_ref=input_ref,
                continuation_decision="BLOCKED",
                assurance_level="INSUFFICIENT",
                release_readiness="QUALIFICATION_BLOCKED",
                reason_codes=("UNRESOLVED_EVIDENCE_INVALIDATION", "INVALIDATED_EVIDENCE"),
                blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )

        # Open contradictions -> BLOCKED
        if stop_input.contradiction_refs:
            return StopEvaluation(
                stop_evaluation_id=stop_evaluation_id,
                stop_input_ref=input_ref,
                continuation_decision="BLOCKED",
                assurance_level="INSUFFICIENT",
                release_readiness="QUALIFICATION_BLOCKED",
                reason_codes=("OPEN_CONTRADICTION",),
                blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )

        # Missing CandidateAssuranceCase ref
        if not stop_input.candidate_assurance_case_ref:
            return StopEvaluation(
                stop_evaluation_id=stop_evaluation_id,
                stop_input_ref=input_ref,
                continuation_decision="BLOCKED",
                assurance_level="INSUFFICIENT",
                release_readiness="QUALIFICATION_BLOCKED",
                reason_codes=("MISSING_CANDIDATE_ASSURANCE_CASE",),
                blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )

        # Missing required challengers
        if not stop_input.challenger_refs or len(stop_input.challenger_refs) < 2:
            return StopEvaluation(
                stop_evaluation_id=stop_evaluation_id,
                stop_input_ref=input_ref,
                continuation_decision="BLOCKED",
                assurance_level="INSUFFICIENT",
                release_readiness="QUALIFICATION_BLOCKED",
                reason_codes=("MISSING_REQUIRED_CHALLENGERS",),
                blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )

        # Insufficient data in post-E5
        if insufficient_data:
            if e6_plan_approved:
                return StopEvaluation(
                    stop_evaluation_id=stop_evaluation_id,
                    stop_input_ref=input_ref,
                    continuation_decision="E6_REQUIRED",
                    assurance_level="BOUNDED",
                    release_readiness="QUALIFICATION_BLOCKED",
                    reason_codes=("INSUFFICIENT_DATA", "E6_REQUIRED_TO_ACQUIRE_DATA"),
                    blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                    remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                )
            return StopEvaluation(
                stop_evaluation_id=stop_evaluation_id,
                stop_input_ref=input_ref,
                continuation_decision="BLOCKED",
                assurance_level="INSUFFICIENT",
                release_readiness="QUALIFICATION_BLOCKED",
                reason_codes=("INSUFFICIENT_DATA",),
                blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )

        # Check if there are material gaps that need E6
        if e6_plan_approved and stop_input.mandatory_obligation_refs:
            # If obligations are pending and approved bounded E6 exists
            return StopEvaluation(
                stop_evaluation_id=stop_evaluation_id,
                stop_input_ref=input_ref,
                continuation_decision="E6_REQUIRED",
                assurance_level="BOUNDED",
                release_readiness="QUALIFICATION_BLOCKED",
                reason_codes=("E6_REQUIRED", "BOUNDED_ADDITIONAL_PLAN_APPROVED"),
                blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )

        # Complete satisfaction -> PASS
        release_readiness = (
            "READY_WITH_RESIDUAL_RISK"
            if stop_input.residual_risk_refs
            else "READY"
        )
        return StopEvaluation(
            stop_evaluation_id=stop_evaluation_id,
            stop_input_ref=input_ref,
            continuation_decision="PASS",
            assurance_level="ADEQUATE_FOR_DECLARED_SCOPE",
            release_readiness=release_readiness,
            reason_codes=("ALL_REQUIREMENTS_SATISFIED",),
            blocking_obligation_refs=(),
            remaining_obligation_refs=(),
        )

    # 5. POST_E6 context
    if ctx == "POST_E6":
        if e6_plan_approved and stop_input.mandatory_obligation_refs:
            return StopEvaluation(
                stop_evaluation_id=stop_evaluation_id,
                stop_input_ref=input_ref,
                continuation_decision="E6_REQUIRED",
                assurance_level="BOUNDED",
                release_readiness="QUALIFICATION_BLOCKED",
                reason_codes=("POST_E6_ADDITIONAL_ROUND_REQUIRED",),
                blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )
        release_readiness = (
            "READY_WITH_RESIDUAL_RISK"
            if stop_input.residual_risk_refs
            else "READY"
        )
        return StopEvaluation(
            stop_evaluation_id=stop_evaluation_id,
            stop_input_ref=input_ref,
            continuation_decision="PASS",
            assurance_level="ADEQUATE_FOR_DECLARED_SCOPE",
            release_readiness=release_readiness,
            reason_codes=("POST_E6_SATISFIED",),
            blocking_obligation_refs=(),
            remaining_obligation_refs=(),
        )

    raise ValidationError(f"UNKNOWN_EVALUATION_CONTEXT: {ctx}")


def validate_intermediate_stop(evaluation: StopEvaluation, context: str) -> None:
    """Enforce fail-closed invariant: INTERMEDIATE context can never produce PASS or release readiness."""
    if context == "INTERMEDIATE":
        if evaluation.continuation_decision in ("PASS", "E6_REQUIRED"):
            raise ValidationError(
                f"INTERMEDIATE_CANNOT_PRODUCE_PASS: continuation_decision '{evaluation.continuation_decision}' is forbidden in INTERMEDIATE context."
            )
        if evaluation.release_readiness in ("READY", "READY_WITH_RESIDUAL_RISK"):
            raise ValidationError(
                f"INTERMEDIATE_CANNOT_PRODUCE_RELEASE_READINESS: release_readiness '{evaluation.release_readiness}' is forbidden in INTERMEDIATE context."
            )


def validate_stop_snapshot_binding(
    stop_input: Any,
    snapshot: Any,
) -> None:
    """Validate mechanical binding between StopInput and its backing Snapshot."""
    input_body = stop_input.body() if hasattr(stop_input, "body") and callable(stop_input.body) else (stop_input if isinstance(stop_input, dict) else stop_input.body)
    snap_body = snapshot.body() if hasattr(snapshot, "body") and callable(snapshot.body) else (snapshot if isinstance(snapshot, dict) else snapshot.body)

    cut = input_body.get("input_history_cut", {})
    snap_head = snap_body.get("as_of_head", {})

    cut_camp = cut.get("campaign_id")
    cut_seq = cut.get("accepted_head_seq") if cut.get("accepted_head_seq") is not None else cut.get("commit_seq")
    cut_hash = cut.get("accepted_head_hash") or cut.get("commit_hash")

    snap_camp = snap_head.get("campaign_id")
    snap_seq = snap_head.get("accepted_head_seq") if snap_head.get("accepted_head_seq") is not None else snap_head.get("commit_seq")
    snap_hash = snap_head.get("accepted_head_hash") or snap_head.get("commit_hash")

    if not cut_hash or not snap_hash or cut_camp != snap_camp or cut_seq != snap_seq or cut_hash != snap_hash:
        raise ValidationError("STOP_SNAPSHOT_BINDING_CONFLICT", "as_of_head mismatch")

    direct_digests = set()
    for field in (
        "source_generation_ref",
        "inventory_revision_ref",
        "mandatory_obligation_refs",
        "current_obligation_qualification_refs",
        "completed_stage_refs",
        "required_stage_spec_refs",
    ):
        val = input_body.get(field)
        if isinstance(val, dict) and "revision_digest" in val:
            direct_digests.add(val["revision_digest"])
        elif isinstance(val, (list, tuple)):
            for item in val:
                if isinstance(item, dict) and "revision_digest" in item:
                    direct_digests.add(item["revision_digest"])

    snap_digests = {
        r["revision_digest"]
        for r in snap_body.get("projection_input_refs", ())
        if isinstance(r, dict) and "revision_digest" in r
    }

    if snap_digests != direct_digests:
        raise ValidationError("STOP_SNAPSHOT_BINDING_CONFLICT", "projection_input_refs mismatch")

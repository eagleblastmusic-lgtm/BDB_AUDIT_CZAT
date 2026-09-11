"""Pure STOP evaluator over immutable StopInput (M24 / PR-027)."""
from __future__ import annotations

from typing import Sequence

from ..core.errors import ValidationError
from .models import StopInput, StopEvaluation


def evaluate_stop(
    stop_input: StopInput,
    *,
    force_blocked: bool = False,
    blocker_reason: str | None = None,
    insufficient_data: bool = True,
) -> StopEvaluation:
    """Evaluate pure StopInput deterministically according to normative precedence rules.
    
    Precedence:
    1. Authority / admission / cut failure -> BLOCKED + INSUFFICIENT + QUALIFICATION_BLOCKED
    2. INTERMEDIATE context -> CONTINUE_REQUIRED (PASS / E6_REQUIRED strictly forbidden)
    3. Pending required stages -> CONTINUE_REQUIRED + REQUIRED_STAGES_PENDING
    4. Insufficient data -> CONTINUE_REQUIRED + INSUFFICIENT_DATA
    """
    ctx = stop_input.evaluation_context
    input_ref = stop_input.ref

    # 1. Authority / blocker failure
    if force_blocked or stop_input.unknown_blocked_summary.get("is_blocked", False):
        code = blocker_reason or "AUTHORITY_OR_ADMISSION_BLOCKED"
        return StopEvaluation(
            stop_input_ref=input_ref,
            continuation_decision="BLOCKED",
            assurance_level="INSUFFICIENT",
            release_readiness="QUALIFICATION_BLOCKED",
            reason_codes=(code,),
            blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
        )

    # 2. INTERMEDIATE context: used before completion of ordinary E1–E5.
    # PASS and E6_REQUIRED are forbidden.
    if ctx == "INTERMEDIATE":
        reasons = []
        if stop_input.pending_required_stage_refs:
            reasons.append("REQUIRED_STAGES_PENDING")
        if insufficient_data:
            reasons.append("INSUFFICIENT_DATA")
        if not reasons:
            reasons.append("INTERMEDIATE_STAGE_EVALUATION")

        # Determine remaining obligations
        remaining = list(stop_input.mandatory_obligation_refs)
        blocking = []
        if stop_input.evidence_invalidation_refs:
            reasons.append("INVALIDATED_EVIDENCE_PENDING")

        return StopEvaluation(
            stop_input_ref=input_ref,
            continuation_decision="CONTINUE_REQUIRED",
            assurance_level="INSUFFICIENT",
            release_readiness="TECHNICALLY_NOT_READY",
            reason_codes=tuple(reasons),
            blocking_obligation_refs=tuple(blocking),
            remaining_obligation_refs=tuple(remaining),
        )

    # 3. FINAL_POST_E5 context
    if ctx == "FINAL_POST_E5":
        if stop_input.pending_required_stage_refs:
            return StopEvaluation(
                stop_input_ref=input_ref,
                continuation_decision="CONTINUE_REQUIRED",
                assurance_level="INSUFFICIENT",
                release_readiness="TECHNICALLY_NOT_READY",
                reason_codes=("REQUIRED_STAGES_PENDING",),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )
        # Check if any unresolved contradictions or invalidations
        if stop_input.evidence_invalidation_refs:
            return StopEvaluation(
                stop_input_ref=input_ref,
                continuation_decision="BLOCKED",
                assurance_level="INSUFFICIENT",
                release_readiness="QUALIFICATION_BLOCKED",
                reason_codes=("UNRESOLVED_EVIDENCE_INVALIDATION",),
                blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )
        # All satisfied -> PASS
        return StopEvaluation(
            stop_input_ref=input_ref,
            continuation_decision="PASS",
            assurance_level="ADEQUATE_FOR_DECLARED_SCOPE",
            release_readiness="READY",
            reason_codes=("ALL_REQUIREMENTS_SATISFIED",),
            blocking_obligation_refs=(),
            remaining_obligation_refs=(),
        )

    # 4. POST_E6 context
    return StopEvaluation(
        stop_input_ref=input_ref,
        continuation_decision="CONTINUE_REQUIRED",
        assurance_level="BOUNDED",
        release_readiness="TECHNICALLY_NOT_READY",
        reason_codes=("POST_E6_EVALUATION",),
    )


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

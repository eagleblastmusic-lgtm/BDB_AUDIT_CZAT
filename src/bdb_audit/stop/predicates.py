"""Pure predicates and validation helpers for STOP and StageCompletion decisions (B02 / §103)."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..core.errors import ValidationError
from .models import StopEvaluation, StopInput


def validate_stop_evaluation_invariants(
    stop_input: StopInput,
    stop_evaluation: StopEvaluation,
) -> None:
    """Enforce strict anti-false-PASS invariants between input and outcome."""
    # 1. UNKNOWN surface scope cannot silently become PASS
    unknown_summary = stop_input.unknown_blocked_summary or {}
    if unknown_summary.get("unknown_surfaces_count", 0) > 0:
        if stop_evaluation.continuation_decision == "PASS":
            raise ValidationError(
                "UNKNOWN_SURFACE_CANNOT_PASS",
                "STOP cannot evaluate to PASS when unknown surface scope exists",
            )

    # 2. BLOCKED status cannot silently become PASS
    if unknown_summary.get("is_blocked", False):
        if stop_evaluation.continuation_decision == "PASS":
            raise ValidationError(
                "BLOCKED_CANNOT_PASS",
                "STOP cannot evaluate to PASS when blocked conditions exist",
            )

    # 3. Pending required stages forbid PASS
    if stop_input.pending_required_stage_refs:
        if stop_evaluation.continuation_decision == "PASS":
            raise ValidationError(
                "REQUIRED_STAGES_PENDING_FORBIDS_PASS",
                f"{len(stop_input.pending_required_stage_refs)} required stages are still pending",
            )

    # 4. PASS requires ADEQUATE_FOR_DECLARED_SCOPE assurance
    if stop_evaluation.continuation_decision == "PASS":
        if stop_evaluation.assurance_level != "ADEQUATE_FOR_DECLARED_SCOPE":
            raise ValidationError(
                "PASS_REQUIRES_ADEQUATE_ASSURANCE",
                f"PASS continuation decision requires ADEQUATE_FOR_DECLARED_SCOPE, got {stop_evaluation.assurance_level}",
            )


def check_stage_completion_eligibility(
    stage_key: str,
    required_lanes: Sequence[str],
    completed_lanes: Sequence[str],
    unresolved_refs: Sequence[Mapping[str, Any]] = (),
) -> tuple[bool, str, list[str]]:
    """Determine whether a stage is eligible for completion."""
    missing_lanes = [lane for lane in required_lanes if lane not in completed_lanes]
    reasons: list[str] = []

    if missing_lanes:
        reasons.append(f"MISSING_REQUIRED_LANES: {missing_lanes}")
    if unresolved_refs:
        reasons.append(f"UNRESOLVED_REFS: {len(unresolved_refs)} references pending")

    if reasons:
        return False, "STAGE_COMPLETION_BLOCKED", reasons
    return True, "STAGE_COMPLETED", []

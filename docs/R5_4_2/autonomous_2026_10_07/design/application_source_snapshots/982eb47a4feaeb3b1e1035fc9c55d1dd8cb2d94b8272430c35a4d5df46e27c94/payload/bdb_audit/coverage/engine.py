"""M15/M16 Coverage engine: qualification evaluation, invalidation propagation, derived depth."""
from typing import Any, Mapping, Sequence, Set

from ..core.errors import ValidationError
from .models import (
    CoverageObligation,
    CoverageObligationQualification,
    ObligationApplicabilityDecision,
    ApprovalDecision,
)


def evaluate_coverage_qualification(
    obligation: CoverageObligation,
    qualification: CoverageObligationQualification,
    applicability_decision: ObligationApplicabilityDecision | None = None,
    waiver_decision: ApprovalDecision | None = None,
    invalidated_evidence_digests: Set[str] | None = None,
) -> dict:
    """Evaluate obligation qualification status ensuring fail-closed semantics:

    - No auto-N/A without explicit accepted applicability decision.
    - No auto-waiver without explicit accepted approval decision.
    - Invalidation propagates and degrades QUALIFIED to STALE.
    - BLOCKED and WAIVED do not count as substantive PASS.
    """
    invalidated = invalidated_evidence_digests or set()
    status = qualification.qualification_status
    substantive = qualification.substantive_outcome
    degraded = False

    # Check evidence invalidation propagation
    evidence_digests = {
        r.get("revision_digest") for r in qualification.evidence_qualification_refs if isinstance(r, dict)
    }
    if evidence_digests & invalidated:
        status = "STALE"
        degraded = True

    # No auto-N/A: if applicability decision ref is provided, must verify
    if qualification.applicability_decision_ref is not None:
        if applicability_decision is None:
            raise ValidationError("AUTO_NA_FORBIDDEN", "Applicability ref claimed without accepted decision")
        if applicability_decision.result != "NOT_APPLICABLE":
            raise ValidationError("APPLICABILITY_RESULT_MISMATCH")

    # No auto-waiver: if waiver decision ref is provided, must verify
    if qualification.waiver_decision_ref is not None:
        if waiver_decision is None:
            raise ValidationError("AUTO_WAIVER_FORBIDDEN", "Waiver ref claimed without accepted approval")
        if waiver_decision.decision_type != "COVERAGE_OBLIGATION_WAIVER" or waiver_decision.decision != "APPROVED":
            raise ValidationError("WAIVER_DECISION_MISMATCH")

    # Substantive completion satisfaction:
    # Only QUALIFIED with NO_VIOLATION_OBSERVED satisfies coverage completion.
    satisfies_completion = (status == "QUALIFIED" and substantive == "NO_VIOLATION_OBSERVED")

    return {
        "obligation_id": obligation.obligation_id,
        "effective_status": status,
        "substantive_outcome": substantive,
        "satisfies_completion": satisfies_completion,
        "is_waived": waiver_decision is not None and waiver_decision.decision == "APPROVED",
        "is_not_applicable": applicability_decision is not None and applicability_decision.result == "NOT_APPLICABLE",
        "degraded_by_invalidation": degraded,
    }


def derive_presentation_depth(
    evaluations: Sequence[dict],
    has_active_mutation: bool = False,
    concurrency_obligations_satisfied: bool = False,
) -> dict:
    """Derive conservative presentation depth (D0–D5).

    Roadmap §54: D0–D5 is derived only; never authority.
    - Single concurrency test cannot lift entire surface to D4.
    - Inactive mutation cannot grant D5.
    """
    total = len(evaluations)
    if total == 0:
        return {"derived_depth": "D0", "satisfied_ratio": 0.0}

    satisfied = sum(1 for e in evaluations if e.get("satisfies_completion"))
    ratio = satisfied / total

    if satisfied == 0:
        depth = "D0"
    elif ratio < 0.5:
        depth = "D1"
    elif ratio < 0.8:
        depth = "D2"
    elif ratio < 1.0:
        depth = "D3"
    else:
        # 100% satisfied
        if concurrency_obligations_satisfied and has_active_mutation:
            depth = "D5"
        elif concurrency_obligations_satisfied:
            depth = "D4"
        else:
            depth = "D3"

    return {
        "derived_depth": depth,
        "satisfied_ratio": ratio,
        "total_obligations": total,
        "satisfied_obligations": satisfied,
    }

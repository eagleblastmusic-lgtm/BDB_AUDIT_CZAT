"""BDB Audit v2 Invariant and Coverage Obligation module (M15/M16)."""
from .models import (
    InvariantRevision,
    MaterialityAssessment,
    CoverageObligationKey,
    CoverageObligation,
    CoverageObligationQualification,
    ObligationApplicabilityDecision,
    ApprovalDecision,
    INVARIANT_STATUSES,
    INVARIANT_CATEGORIES,
    MATERIALITY_RESULTS,
    QUALIFICATION_STATUSES,
    SUBSTANTIVE_OUTCOMES,
    APPLICABILITY_RESULTS,
)
from .engine import (
    evaluate_coverage_qualification,
    derive_presentation_depth,
)
from .invariants import (
    InvariantRegistryEngine,
)

__all__ = [
    "InvariantRevision",
    "MaterialityAssessment",
    "CoverageObligationKey",
    "CoverageObligation",
    "CoverageObligationQualification",
    "ObligationApplicabilityDecision",
    "ApprovalDecision",
    "INVARIANT_STATUSES",
    "INVARIANT_CATEGORIES",
    "MATERIALITY_RESULTS",
    "QUALIFICATION_STATUSES",
    "SUBSTANTIVE_OUTCOMES",
    "APPLICABILITY_RESULTS",
    "evaluate_coverage_qualification",
    "derive_presentation_depth",
    "InvariantRegistryEngine",
]

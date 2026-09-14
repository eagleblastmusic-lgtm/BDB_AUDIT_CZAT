"""BDB Audit v2 Finding, Root Cause, and Contradiction module (M21/M22)."""
from __future__ import annotations

from typing import Any

from . import models as _models


_LEGACY_INTERNAL_SEVERITY_METHODS = {
    "DEFAULT_CRASH_SEVERITY": "INFO",
    "DIFFERENTIAL_SEVERITY_ESTIMATE": "INFO",
    "METAMORPHIC_SEVERITY_ESTIMATE": "INFO",
}


class FindingClaimRevision(_models.FindingClaimRevision):
    """Canonical finding claim with source-compatible pre-R5.3.1 constructor aliases.

    The aliases affect only the Python call surface. ``body()`` and therefore
    canonical serialization continue to use the current R5.3 field names.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        aliases = {
            "statement": "claim_statement",
            "claim_id": "finding_id",
            "claim_revision": "finding_claim_revision",
        }
        normalized = dict(kwargs)
        for legacy_name, canonical_name in aliases.items():
            if legacy_name not in normalized:
                continue
            legacy_value = normalized.pop(legacy_name)
            if canonical_name in normalized and normalized[canonical_name] != legacy_value:
                raise TypeError(
                    f"Conflicting constructor values for {legacy_name!r} and {canonical_name!r}"
                )
            normalized[canonical_name] = legacy_value
        super().__init__(*args, **normalized)

    @property
    def statement(self) -> str:
        return self.claim_statement

    @property
    def claim_id(self) -> str | None:
        return self.finding_id

    @property
    def claim_revision(self) -> str:
        return self.finding_claim_revision


class FindingAxisAssessment(_models.FindingAxisAssessment):
    """Current four-axis assessment with conservative legacy-call translation.

    Pre-R5.3.1 ``assessment_id`` is a name-only alias. Legacy free-text
    ``method`` is retained only as a limitation and is never promoted to a
    typed method/evidence reference.

    Three known internal F5 adapters historically expressed Severity as an
    epistemic ``SUPPORTED`` vote because the pre-R5.3 model had no independent
    severity value. For those exact internal method markers only, the wrapper
    migrates the legacy call to conservative ``INFO`` characterization and
    records an explicit limitation/reason code. All other epistemic Severity
    input remains forbidden and is rejected by the canonical model.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        normalized = dict(kwargs)
        if "assessment_id" in normalized:
            legacy_value = normalized.pop("assessment_id")
            if (
                "finding_axis_assessment_id" in normalized
                and normalized["finding_axis_assessment_id"] != legacy_value
            ):
                raise TypeError(
                    "Conflicting constructor values for 'assessment_id' and "
                    "'finding_axis_assessment_id'"
                )
            normalized["finding_axis_assessment_id"] = legacy_value

        legacy_method = normalized.pop("method", None)
        legacy_internal_severity_migrated = False
        if (
            normalized.get("axis") == "SEVERITY"
            and "severity_value" not in normalized
            and "epistemic_outcome" in normalized
            and legacy_method in _LEGACY_INTERNAL_SEVERITY_METHODS
        ):
            normalized.pop("epistemic_outcome")
            normalized["severity_value"] = _LEGACY_INTERNAL_SEVERITY_METHODS[str(legacy_method)]
            limitations = list(normalized.get("limitations", ()))
            limitations.append(f"LEGACY_INTERNAL_SEVERITY_MIGRATED:{legacy_method}")
            normalized["limitations"] = limitations
            reason_codes = list(normalized.get("reason_codes", ()))
            reason_codes.append("LEGACY_INTERNAL_SEVERITY_MIGRATED_TO_INFO")
            normalized["reason_codes"] = reason_codes
            legacy_internal_severity_migrated = True

        if legacy_method is not None:
            limitations = list(normalized.get("limitations", ()))
            limitations.append(f"LEGACY_UNTYPED_METHOD:{legacy_method}")
            normalized["limitations"] = limitations

        super().__init__(*args, **normalized)
        object.__setattr__(self, "_legacy_method", legacy_method)
        object.__setattr__(self, "_legacy_internal_severity_migrated", legacy_internal_severity_migrated)

    @property
    def assessment_id(self) -> str | None:
        return self.finding_axis_assessment_id

    @property
    def method(self) -> str | None:
        value = getattr(self, "_legacy_method", None)
        return None if value is None else str(value)


class FindingAdjudicationDecision(_models.FindingAdjudicationDecision):
    """Current decision with the pre-R5.3.1 lifecycle-status call alias."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        normalized = dict(kwargs)
        if "lifecycle_status" in normalized:
            legacy_value = normalized.pop("lifecycle_status")
            if (
                "finding_lifecycle_status" in normalized
                and normalized["finding_lifecycle_status"] != legacy_value
            ):
                raise TypeError(
                    "Conflicting constructor values for 'lifecycle_status' and "
                    "'finding_lifecycle_status'"
                )
            normalized["finding_lifecycle_status"] = legacy_value
        super().__init__(*args, **normalized)

    @property
    def lifecycle_status(self) -> str:
        return self.finding_lifecycle_status


# Direct imports from ``bdb_audit.adjudication.models`` occur throughout the
# implementation. Install compatibility subclasses before importing engine
# modules so every later direct import receives the same classes.
setattr(_models, "FindingClaimRevision", FindingClaimRevision)
setattr(_models, "FindingAxisAssessment", FindingAxisAssessment)
setattr(_models, "FindingAdjudicationDecision", FindingAdjudicationDecision)

RootCauseRevision = _models.RootCauseRevision
ContradictionRevision = _models.ContradictionRevision
ContradictionResolutionDecision = _models.ContradictionResolutionDecision
AXIS_DOMAINS = _models.AXIS_DOMAINS
EPISTEMIC_OUTCOMES = _models.EPISTEMIC_OUTCOMES
SEVERITY_VALUES = _models.SEVERITY_VALUES
CONFIDENCE_VALUES = _models.CONFIDENCE_VALUES
FINDING_CATEGORIES = _models.FINDING_CATEGORIES
FINDING_LIFECYCLE_STATUSES = _models.FINDING_LIFECYCLE_STATUSES
ROOT_CAUSE_STATUSES = _models.ROOT_CAUSE_STATUSES
CONTRADICTION_STATUSES = _models.CONTRADICTION_STATUSES
CONTRADICTION_RESOLUTION_KINDS = _models.CONTRADICTION_RESOLUTION_KINDS
CONTRADICTION_RESOLUTION_RESULTS = _models.CONTRADICTION_RESOLUTION_RESULTS
sort_membership_edges = _models.sort_membership_edges

from .engine import (
    validate_root_cause_authority,
    validate_finding_adjudication_rules,
    adjudicate_finding,
    transition_finding_lifecycle,
    resolve_contradiction,
    apply_contradiction_resolution,
    reopen_contradiction,
    cluster_findings_into_root_cause,
    ALLOWED_LIFECYCLE_TRANSITIONS,
)
from .contribution import (
    ProducerContribution,
    ContributionProjection,
    build_contribution_projection,
    validate_contribution_authority,
)

__all__ = [
    "FindingClaimRevision",
    "FindingAxisAssessment",
    "FindingAdjudicationDecision",
    "RootCauseRevision",
    "ContradictionRevision",
    "ContradictionResolutionDecision",
    "AXIS_DOMAINS",
    "EPISTEMIC_OUTCOMES",
    "SEVERITY_VALUES",
    "CONFIDENCE_VALUES",
    "FINDING_CATEGORIES",
    "FINDING_LIFECYCLE_STATUSES",
    "ROOT_CAUSE_STATUSES",
    "CONTRADICTION_STATUSES",
    "CONTRADICTION_RESOLUTION_KINDS",
    "CONTRADICTION_RESOLUTION_RESULTS",
    "sort_membership_edges",
    "validate_root_cause_authority",
    "validate_finding_adjudication_rules",
    "adjudicate_finding",
    "transition_finding_lifecycle",
    "resolve_contradiction",
    "apply_contradiction_resolution",
    "reopen_contradiction",
    "cluster_findings_into_root_cause",
    "ALLOWED_LIFECYCLE_TRANSITIONS",
    "ProducerContribution",
    "ContributionProjection",
    "build_contribution_projection",
    "validate_contribution_authority",
]

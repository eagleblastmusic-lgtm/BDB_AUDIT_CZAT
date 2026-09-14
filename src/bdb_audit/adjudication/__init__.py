"""BDB Audit v2 Finding, Root Cause, and Contradiction module (M21/M22)."""
from __future__ import annotations

from typing import Any

from . import models as _models


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


# Direct imports from ``bdb_audit.adjudication.models`` occur throughout the
# implementation. Install the compatibility subclass before importing engine
# modules so every later direct import receives the same class.
setattr(_models, "FindingClaimRevision", FindingClaimRevision)

FindingAxisAssessment = _models.FindingAxisAssessment
FindingAdjudicationDecision = _models.FindingAdjudicationDecision
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

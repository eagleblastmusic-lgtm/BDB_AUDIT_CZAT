"""Adjudication, Root Cause authority, and contradiction resolution engine (M21/M22)."""
from typing import Any, Mapping, Sequence

from ..core.errors import ValidationError
from .models import (
    FindingClaimRevision,
    FindingAxisAssessment,
    FindingAdjudicationDecision,
    RootCauseRevision,
    ContradictionRevision,
    ContradictionResolutionDecision,
    sort_membership_edges,
)


def validate_root_cause_authority(accepted_kind: str) -> None:
    """Ensure no separate Root Cause membership authority is introduced (FR-07).

    Only RootCauseRevision.membership_edges is authority.
    """
    if accepted_kind in ("RootCauseMembershipRevision", "root_cause_membership_revision"):
        raise ValidationError("SECOND_AUTHORITY_FOR_ROOT_CAUSE_MEMBERSHIP", "Separate Root Cause membership authority rejected")


def adjudicate_finding(
    claim: FindingClaimRevision,
    mechanism: FindingAxisAssessment,
    reachability: FindingAxisAssessment,
    impact: FindingAxisAssessment,
    severity: FindingAxisAssessment,
    adjudicator_ref: Any,
    input_history_cut: dict,
    evidence_refs: Sequence[Any] = (),
) -> FindingAdjudicationDecision:
    """Create a validated FindingAdjudicationDecision from 3-axis assessments."""
    # Determine lifecycle status based on epistemic outcomes of the 3 axes
    outcomes = {mechanism.epistemic_outcome, reachability.epistemic_outcome, impact.epistemic_outcome}
    if "REFUTED" in outcomes:
        status = "REJECTED"
    elif outcomes == {"SUPPORTED"}:
        status = "CONFIRMED_CURRENT"
    else:
        status = "OPEN"

    return FindingAdjudicationDecision(
        claim_revision_ref=claim.as_object().as_ref().as_dict(),
        input_history_cut=input_history_cut,
        adjudicator_ref=adjudicator_ref,
        mechanism_assessment_ref=mechanism.as_object().as_ref().as_dict(),
        reachability_assessment_ref=reachability.as_object().as_ref().as_dict(),
        impact_assessment_ref=impact.as_object().as_ref().as_dict(),
        severity_assessment_ref=severity.as_object().as_ref().as_dict(),
        lifecycle_status=status,
        evidence_qualification_refs=evidence_refs,
    )

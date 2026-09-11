"""Adjudication, Root Cause authority, and contradiction resolution engine (M21/M22/WP-F4-08)."""
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
    _ref_dict,
)

# Valid transitions in FindingAdjudicationDecision lifecycle (R5.3 §62)
ALLOWED_LIFECYCLE_TRANSITIONS: dict[str, set[str]] = {
    "OPEN": {"CONFIRMED_CURRENT", "REJECTED", "OPEN", "SUPERSEDED"},
    "CONFIRMED_CURRENT": {
        "REMEDIATION_PENDING",
        "STALE_FOR_CURRENT_SOURCE",
        "SUPERSEDED",
        "REJECTED",
        "PARTIALLY_FIXED",
    },
    "REMEDIATION_PENDING": {"FIXED_ON_NEW_SOURCE", "PARTIALLY_FIXED", "REOPENED", "CONFIRMED_CURRENT"},
    "FIXED_ON_NEW_SOURCE": {"REOPENED", "CONFIRMED_CURRENT"},
    "PARTIALLY_FIXED": {"CONFIRMED_CURRENT", "FIXED_ON_NEW_SOURCE", "REOPENED", "REMEDIATION_PENDING"},
    "REOPENED": {"CONFIRMED_CURRENT", "REJECTED", "REMEDIATION_PENDING", "OPEN"},
    "STALE_FOR_CURRENT_SOURCE": {"CONFIRMED_CURRENT", "REJECTED", "REOPENED", "SUPERSEDED"},
    "SUPERSEDED": {"REOPENED"},
    "REJECTED": {"REOPENED"},
}


def validate_root_cause_authority(accepted_kind: str) -> None:
    """Ensure no separate Root Cause membership authority is introduced (FR-07).

    Only RootCauseRevision.membership_edges is authority.
    """
    if accepted_kind in ("RootCauseMembershipRevision", "root_cause_membership_revision"):
        raise ValidationError(
            "SECOND_AUTHORITY_FOR_ROOT_CAUSE_MEMBERSHIP",
            "Separate Root Cause membership authority rejected",
        )


def validate_finding_adjudication_rules(
    mechanism: FindingAxisAssessment,
    reachability: FindingAxisAssessment,
    impact: FindingAxisAssessment,
    severity: FindingAxisAssessment,
    lifecycle_status: str | None = None,
) -> str:
    """Validate 4-axis finding assessment rules and deduce or enforce lifecycle status.

    Adversarial rule (FR-10, R5.3 §62):
    - If any operational axis (MECHANISM, REACHABILITY, IMPACT) is REFUTED,
      the finding CANNOT be confirmed (must be REJECTED).
    - If any operational axis is INCONCLUSIVE or BLOCKED, it cannot be confirmed (remains OPEN).
    """
    axes = [mechanism, reachability, impact]
    axis_outcomes = {ax.epistemic_outcome for ax in axes}

    if "REFUTED" in axis_outcomes:
        computed_status = "REJECTED"
        if lifecycle_status == "CONFIRMED_CURRENT":
            raise ValidationError(
                "REFUTED_AXIS_CANNOT_BE_CONFIRMED",
                f"Finding cannot be confirmed when an axis is REFUTED: mechanism={mechanism.epistemic_outcome}, reachability={reachability.epistemic_outcome}, impact={impact.epistemic_outcome}",
            )
    elif axis_outcomes == {"SUPPORTED"}:
        computed_status = "CONFIRMED_CURRENT"
    else:
        computed_status = "OPEN"
        if lifecycle_status == "CONFIRMED_CURRENT":
            raise ValidationError(
                "UNCONFIRMED_AXIS_CANNOT_BE_CONFIRMED",
                f"Finding cannot be confirmed when axes are inconclusive or blocked: outcomes={axis_outcomes}",
            )

    return lifecycle_status if lifecycle_status is not None else computed_status


def adjudicate_finding(
    claim: FindingClaimRevision,
    mechanism: FindingAxisAssessment,
    reachability: FindingAxisAssessment,
    impact: FindingAxisAssessment,
    severity: FindingAxisAssessment,
    adjudicator_ref: Any,
    input_history_cut: dict,
    evidence_refs: Sequence[Any] = (),
    lifecycle_status: str | None = None,
    previous_adjudication_decision_ref: Any = None,
) -> FindingAdjudicationDecision:
    """Create a validated FindingAdjudicationDecision from 4-axis assessments."""
    final_status = validate_finding_adjudication_rules(
        mechanism=mechanism,
        reachability=reachability,
        impact=impact,
        severity=severity,
        lifecycle_status=lifecycle_status,
    )

    return FindingAdjudicationDecision(
        claim_revision_ref=claim.as_object().as_ref().as_dict(),
        input_history_cut=input_history_cut,
        adjudicator_ref=adjudicator_ref,
        mechanism_assessment_ref=mechanism.as_object().as_ref().as_dict(),
        reachability_assessment_ref=reachability.as_object().as_ref().as_dict(),
        impact_assessment_ref=impact.as_object().as_ref().as_dict(),
        severity_assessment_ref=severity.as_object().as_ref().as_dict(),
        lifecycle_status=final_status,
        evidence_qualification_refs=evidence_refs,
        previous_adjudication_decision_ref=previous_adjudication_decision_ref,
    )


def transition_finding_lifecycle(
    current_decision: FindingAdjudicationDecision,
    target_status: str,
    adjudicator_ref: Any,
    input_history_cut: dict,
    mechanism: FindingAxisAssessment | None = None,
    reachability: FindingAxisAssessment | None = None,
    impact: FindingAxisAssessment | None = None,
    severity: FindingAxisAssessment | None = None,
    evidence_refs: Sequence[Any] = (),
) -> FindingAdjudicationDecision:
    """Execute an append-only lifecycle transition on a FindingAdjudicationDecision.

    Validates transition graph and chains backward to prior decision.
    """
    curr = current_decision.lifecycle_status
    allowed = ALLOWED_LIFECYCLE_TRANSITIONS.get(curr, set())
    if target_status not in allowed:
        raise ValidationError(
            "INVALID_LIFECYCLE_TRANSITION",
            f"Invalid transition from {curr} to {target_status}. Allowed: {sorted(allowed)}",
        )

    mech_ref = mechanism.as_object().as_ref().as_dict() if mechanism else current_decision.mechanism_assessment_ref
    reach_ref = reachability.as_object().as_ref().as_dict() if reachability else current_decision.reachability_assessment_ref
    impact_ref = impact.as_object().as_ref().as_dict() if impact else current_decision.impact_assessment_ref
    sev_ref = severity.as_object().as_ref().as_dict() if severity else current_decision.severity_assessment_ref

    return FindingAdjudicationDecision(
        claim_revision_ref=current_decision.claim_revision_ref,
        input_history_cut=input_history_cut,
        adjudicator_ref=adjudicator_ref,
        mechanism_assessment_ref=mech_ref,
        reachability_assessment_ref=reach_ref,
        impact_assessment_ref=impact_ref,
        severity_assessment_ref=sev_ref,
        lifecycle_status=target_status,
        evidence_qualification_refs=evidence_refs or current_decision.evidence_qualification_refs,
        previous_adjudication_decision_ref=current_decision.as_object().as_ref().as_dict(),
    )


def resolve_contradiction(
    contradiction: ContradictionRevision,
    adjudicator_ref: Any,
    resolution_status: str,
    rationale: str,
    input_history_cut: dict,
    resolved_by_majority_vote: bool = False,
) -> ContradictionResolutionDecision:
    """Resolve a contradiction with explicit adjudicator authority.

    Fail closed: majority voting is forbidden (R5.3 §61, Roadmap §67).
    """
    if resolved_by_majority_vote:
        raise ValidationError("MAJORITY_VOTE_FORBIDDEN", "Contradiction cannot be resolved by majority voting")

    return ContradictionResolutionDecision(
        contradiction_revision_ref=contradiction.as_object().as_ref().as_dict(),
        adjudicator_ref=adjudicator_ref,
        resolution_status=resolution_status,
        rationale=rationale,
        input_history_cut=input_history_cut,
        resolved_by_majority_vote=False,
    )


def reopen_contradiction(
    prior_resolution: ContradictionResolutionDecision,
    new_evidence_refs: Sequence[Any],
    claim_revision_ref: Any,
    input_history_cut: dict,
) -> ContradictionRevision:
    """Reopen a contradiction upon discovery of new material counterevidence (R5.3 §61)."""
    return ContradictionRevision(
        claim_revision_ref=_ref_dict(claim_revision_ref),
        contradicting_evidence_refs=list(new_evidence_refs),
        input_history_cut=dict(input_history_cut),
        status="REOPENED",
    )


def cluster_findings_into_root_cause(
    source_generation_ref: Any,
    membership_edges: Sequence[dict],
    predecessor_root_cause_refs: Sequence[Any] = (),
) -> RootCauseRevision:
    """Cluster finding claim revisions into an authoritative RootCauseRevision."""
    # sort_membership_edges enforces determinism and rejects duplicates
    sorted_edges = sort_membership_edges(membership_edges)
    return RootCauseRevision(
        source_generation_ref=_ref_dict(source_generation_ref),
        membership_edges=sorted_edges,
        predecessor_root_cause_refs=list(predecessor_root_cause_refs),
    )

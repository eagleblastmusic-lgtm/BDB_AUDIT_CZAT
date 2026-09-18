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
    *,
    resolved_scope: Mapping[str, Any],
    resolution_kind: str,
    basis_refs: Sequence[Any],
    input_history_cut: dict,
    resulting_status: str,
    resolved_by_majority_vote: bool = False,
) -> ContradictionResolutionDecision:
    """Create the canonical resolution decision for one prior contradiction.

    The decision points backward to the prior contradiction revision.  It does
    not point to a future successor revision and majority/support counts never
    establish truth.
    """
    if resolved_by_majority_vote:
        raise ValidationError(
            "MAJORITY_VOTE_FORBIDDEN",
            "Contradiction cannot be resolved by majority voting",
        )

    return ContradictionResolutionDecision(
        contradiction_prior_revision_ref=(
            contradiction.as_object().as_ref(
                ref_class="PRIOR_ACCEPTED_ONLY"
            ).as_dict()
        ),
        resolution_input_history_cut=dict(input_history_cut),
        resolved_scope=dict(resolved_scope),
        resolution_kind=resolution_kind,
        basis_refs=list(basis_refs),
        resulting_status=resulting_status,
        resolved_by_majority_vote=False,
    )


def apply_contradiction_resolution(
    prior_revision: ContradictionRevision,
    resolution: ContradictionResolutionDecision,
) -> ContradictionRevision:
    """Build the successor contradiction revision after a prior decision.

    Acceptance order is enforced by the history layer through
    PRIOR_ACCEPTED_ONLY refs.  This pure constructor preserves the prior case
    and adds the already-decided resolution as a backward reference.
    """
    if resolution.resulting_status not in {
        "RESOLVED_SCOPED",
        "RESOLVED_FULL",
        "BLOCKED",
    }:
        raise ValidationError(
            "INVALID_CONTRADICTION_RESOLUTION_STATUS",
            resolution.resulting_status,
        )
    if (
        resolution.contradiction_prior_revision_ref[
            "revision_digest"
        ]
        != prior_revision.digest
    ):
        raise ValidationError(
            "CONTRADICTION_RESOLUTION_PREDECESSOR_MISMATCH"
        )

    return ContradictionRevision(
        claim_revision_refs=prior_revision.claim_revision_refs,
        scope=prior_revision.scope,
        positions=prior_revision.positions,
        supporting_evidence_qualification_refs=(
            prior_revision.supporting_evidence_qualification_refs
        ),
        opposing_evidence_qualification_refs=(
            prior_revision.opposing_evidence_qualification_refs
        ),
        failure_assumption_differences=(
            prior_revision.failure_assumption_differences
        ),
        environment_input_model_differences=(
            prior_revision.environment_input_model_differences
        ),
        required_falsifier=prior_revision.required_falsifier,
        status=resolution.resulting_status,
        predecessor_contradiction_revision_ref=(
            prior_revision.as_object().as_ref(
                ref_class="PRIOR_ACCEPTED_ONLY"
            ).as_dict()
        ),
        resolution_decision_ref=(
            resolution.as_object().as_ref(
                ref_class="PRIOR_ACCEPTED_ONLY"
            ).as_dict()
        ),
        contradiction_id=prior_revision.contradiction_id,
        contradiction_revision=str(
            int(prior_revision.contradiction_revision) + 1
        ),
    )


def reopen_contradiction(
    prior_revision: ContradictionRevision,
    *,
    new_supporting_evidence_refs: Sequence[Any] = (),
    new_opposing_evidence_refs: Sequence[Any] = (),
    required_falsifier: Any | None = None,
) -> ContradictionRevision:
    """Create a backward-linked REOPENED successor on new counterevidence."""
    if (
        not new_supporting_evidence_refs
        and not new_opposing_evidence_refs
    ):
        raise ValidationError(
            "CONTRADICTION_REOPEN_EVIDENCE_REQUIRED"
        )

    supporting = [
        *prior_revision.supporting_evidence_qualification_refs,
        *new_supporting_evidence_refs,
    ]
    opposing = [
        *prior_revision.opposing_evidence_qualification_refs,
        *new_opposing_evidence_refs,
    ]
    return ContradictionRevision(
        claim_revision_refs=prior_revision.claim_revision_refs,
        scope=prior_revision.scope,
        positions=prior_revision.positions,
        supporting_evidence_qualification_refs=supporting,
        opposing_evidence_qualification_refs=opposing,
        failure_assumption_differences=(
            prior_revision.failure_assumption_differences
        ),
        environment_input_model_differences=(
            prior_revision.environment_input_model_differences
        ),
        required_falsifier=(
            prior_revision.required_falsifier
            if required_falsifier is None
            else required_falsifier
        ),
        status="REOPENED",
        predecessor_contradiction_revision_ref=(
            prior_revision.as_object().as_ref(
                ref_class="PRIOR_ACCEPTED_ONLY"
            ).as_dict()
        ),
        contradiction_id=prior_revision.contradiction_id,
        contradiction_revision=str(
            int(prior_revision.contradiction_revision) + 1
        ),
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

"""R5.3 Finding adjudication, Root Cause authority, and contradiction engine (M21/M22)."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
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

# Valid append-only Finding lifecycle transitions (R5.3 §56/§62).
ALLOWED_LIFECYCLE_TRANSITIONS: dict[str, set[str]] = {
    "OPEN": {"CONFIRMED_CURRENT", "REJECTED", "OPEN", "SUPERSEDED"},
    "CONFIRMED_CURRENT": {
        "REMEDIATION_PENDING", "STALE_FOR_CURRENT_SOURCE", "SUPERSEDED",
        "REJECTED", "PARTIALLY_FIXED",
    },
    "REMEDIATION_PENDING": {
        "FIXED_ON_NEW_SOURCE", "PARTIALLY_FIXED", "REOPENED", "CONFIRMED_CURRENT",
    },
    "FIXED_ON_NEW_SOURCE": {"REOPENED", "CONFIRMED_CURRENT"},
    "PARTIALLY_FIXED": {
        "CONFIRMED_CURRENT", "FIXED_ON_NEW_SOURCE", "REOPENED", "REMEDIATION_PENDING",
    },
    "REOPENED": {"CONFIRMED_CURRENT", "REJECTED", "REMEDIATION_PENDING", "OPEN"},
    "STALE_FOR_CURRENT_SOURCE": {"CONFIRMED_CURRENT", "REJECTED", "REOPENED", "SUPERSEDED"},
    "SUPERSEDED": {"REOPENED"},
    "REJECTED": {"REOPENED"},
}


def _same_ref(left: Any, right: Any) -> bool:
    return canonical_bytes(_ref_dict(left)) == canonical_bytes(_ref_dict(right))


def _next_revision(value: str) -> str:
    try:
        return str(int(value) + 1)
    except (TypeError, ValueError):
        raise ValidationError("NON_NUMERIC_REVISION_CANNOT_AUTO_ADVANCE", str(value)) from None


def validate_root_cause_authority(accepted_kind: str) -> None:
    """RootCauseRevision.membership_edges is the only Root Cause membership authority."""
    if accepted_kind in ("RootCauseMembershipRevision", "root_cause_membership_revision"):
        raise ValidationError(
            "SECOND_AUTHORITY_FOR_ROOT_CAUSE_MEMBERSHIP",
            "Separate Root Cause membership authority rejected",
        )


def _validate_axis_binding(
    assessment: FindingAxisAssessment,
    *,
    expected_axis: str,
    claim_ref: Any,
) -> None:
    if assessment.axis != expected_axis:
        raise ValidationError(
            "FINDING_AXIS_ROLE_MISMATCH",
            f"Expected {expected_axis}, received {assessment.axis}",
        )
    if not _same_ref(assessment.claim_revision_ref, claim_ref):
        raise ValidationError(
            "FINDING_AXIS_CLAIM_MISMATCH",
            f"{expected_axis} assessment is not bound to the adjudicated claim revision",
        )


def validate_finding_adjudication_rules(
    claim: FindingClaimRevision,
    mechanism: FindingAxisAssessment,
    reachability: FindingAxisAssessment,
    impact: FindingAxisAssessment,
    severity: FindingAxisAssessment,
    finding_lifecycle_status: str | None = None,
) -> str:
    """Validate exact claim/axis bindings and deduce the Finding lifecycle.

    Severity is a characterization axis, not a truth vote. Confirmation is
    driven by the three operational epistemic axes (M/R/I): any REFUTED axis
    rejects the claim; all three SUPPORTED confirms it; every other mixture is
    fail-closed OPEN. A caller cannot force CONFIRMED_CURRENT against those
    outcomes.
    """
    claim_ref = claim.as_object().as_ref().as_dict()
    _validate_axis_binding(mechanism, expected_axis="MECHANISM", claim_ref=claim_ref)
    _validate_axis_binding(reachability, expected_axis="REACHABILITY", claim_ref=claim_ref)
    _validate_axis_binding(impact, expected_axis="IMPACT", claim_ref=claim_ref)
    _validate_axis_binding(severity, expected_axis="SEVERITY", claim_ref=claim_ref)

    operational = [mechanism.epistemic_outcome, reachability.epistemic_outcome, impact.epistemic_outcome]
    if "REFUTED" in operational:
        computed_status = "REJECTED"
        if finding_lifecycle_status == "CONFIRMED_CURRENT":
            raise ValidationError(
                "REFUTED_AXIS_CANNOT_BE_CONFIRMED",
                f"Operational outcomes are {operational}",
            )
    elif operational == ["SUPPORTED", "SUPPORTED", "SUPPORTED"]:
        computed_status = "CONFIRMED_CURRENT"
    else:
        computed_status = "OPEN"
        if finding_lifecycle_status == "CONFIRMED_CURRENT":
            raise ValidationError(
                "UNCONFIRMED_AXIS_CANNOT_BE_CONFIRMED",
                f"Operational outcomes are {operational}",
            )

    return finding_lifecycle_status if finding_lifecycle_status is not None else computed_status


def adjudicate_finding(
    claim: FindingClaimRevision,
    mechanism: FindingAxisAssessment,
    reachability: FindingAxisAssessment,
    impact: FindingAxisAssessment,
    severity: FindingAxisAssessment,
    adjudicator_ref: Any,
    input_history_cut: Mapping[str, Any],
    evidence_refs: Sequence[Any] = (),
    finding_lifecycle_status: str | None = None,
    previous_adjudication_decision_ref: Any = None,
    scope: Mapping[str, Any] | None = None,
    knowledge_state_refs: Sequence[Any] = (),
    corpus_snapshot_refs: Sequence[Any] = (),
    reason_codes: Sequence[str] = (),
) -> FindingAdjudicationDecision:
    """Create one R5.3 FindingAdjudicationDecision from four exact assessments."""
    final_status = validate_finding_adjudication_rules(
        claim=claim,
        mechanism=mechanism,
        reachability=reachability,
        impact=impact,
        severity=severity,
        finding_lifecycle_status=finding_lifecycle_status,
    )
    return FindingAdjudicationDecision(
        claim_revision_ref=claim.as_object().as_ref().as_dict(),
        input_history_cut=dict(input_history_cut),
        adjudicator_ref=adjudicator_ref,
        mechanism_assessment_ref=mechanism.as_object().as_ref().as_dict(),
        reachability_assessment_ref=reachability.as_object().as_ref().as_dict(),
        impact_assessment_ref=impact.as_object().as_ref().as_dict(),
        severity_assessment_ref=severity.as_object().as_ref().as_dict(),
        finding_lifecycle_status=final_status,
        scope=dict(scope or {}),
        evidence_qualification_refs=evidence_refs,
        knowledge_state_refs=knowledge_state_refs,
        corpus_snapshot_refs=corpus_snapshot_refs,
        reason_codes=reason_codes,
        previous_adjudication_decision_ref=previous_adjudication_decision_ref,
    )


def transition_finding_lifecycle(
    current_decision: FindingAdjudicationDecision,
    target_status: str,
    adjudicator_ref: Any,
    input_history_cut: Mapping[str, Any],
    mechanism: FindingAxisAssessment | None = None,
    reachability: FindingAxisAssessment | None = None,
    impact: FindingAxisAssessment | None = None,
    severity: FindingAxisAssessment | None = None,
    evidence_refs: Sequence[Any] = (),
    scope: Mapping[str, Any] | None = None,
    knowledge_state_refs: Sequence[Any] = (),
    corpus_snapshot_refs: Sequence[Any] = (),
    reason_codes: Sequence[str] = (),
) -> FindingAdjudicationDecision:
    """Append a lifecycle decision while retaining exact backward provenance."""
    current_status = current_decision.finding_lifecycle_status
    allowed = ALLOWED_LIFECYCLE_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise ValidationError(
            "INVALID_LIFECYCLE_TRANSITION",
            f"Invalid transition from {current_status} to {target_status}. Allowed: {sorted(allowed)}",
        )

    claim_ref = current_decision.claim_revision_ref
    supplied = {
        "MECHANISM": mechanism,
        "REACHABILITY": reachability,
        "IMPACT": impact,
        "SEVERITY": severity,
    }
    for expected_axis, assessment in supplied.items():
        if assessment is not None:
            _validate_axis_binding(assessment, expected_axis=expected_axis, claim_ref=claim_ref)

    return FindingAdjudicationDecision(
        claim_revision_ref=claim_ref,
        input_history_cut=dict(input_history_cut),
        adjudicator_ref=adjudicator_ref,
        mechanism_assessment_ref=(
            mechanism.as_object().as_ref().as_dict() if mechanism else current_decision.mechanism_assessment_ref
        ),
        reachability_assessment_ref=(
            reachability.as_object().as_ref().as_dict() if reachability else current_decision.reachability_assessment_ref
        ),
        impact_assessment_ref=(
            impact.as_object().as_ref().as_dict() if impact else current_decision.impact_assessment_ref
        ),
        severity_assessment_ref=(
            severity.as_object().as_ref().as_dict() if severity else current_decision.severity_assessment_ref
        ),
        finding_lifecycle_status=target_status,
        scope=dict(scope if scope is not None else current_decision.scope),
        evidence_qualification_refs=evidence_refs or current_decision.evidence_qualification_refs,
        knowledge_state_refs=knowledge_state_refs or current_decision.knowledge_state_refs,
        corpus_snapshot_refs=corpus_snapshot_refs or current_decision.corpus_snapshot_refs,
        reason_codes=reason_codes,
        previous_adjudication_decision_ref=current_decision.as_object().as_ref().as_dict(),
    )


def resolve_contradiction(
    contradiction: ContradictionRevision,
    *,
    resolution_kind: str,
    resolved_scope: Mapping[str, Any],
    basis_refs: Sequence[Any],
    input_history_cut: Mapping[str, Any],
    resulting_status: str,
    resolved_by_majority_vote: bool = False,
) -> ContradictionResolutionDecision:
    """Create a prior-bound resolution decision; voting is never truth authority."""
    if resolved_by_majority_vote:
        raise ValidationError("MAJORITY_VOTE_FORBIDDEN", "Contradiction cannot be resolved by majority voting")
    if contradiction.status not in {"OPEN", "TESTING", "REOPENED", "BLOCKED"}:
        raise ValidationError(
            "CONTRADICTION_ALREADY_RESOLVED",
            f"Cannot resolve contradiction in status {contradiction.status}",
        )
    if resolution_kind == "BLOCKED" and resulting_status != "BLOCKED":
        raise ValidationError("BLOCKED_RESOLUTION_MUST_REMAIN_BLOCKED")
    return ContradictionResolutionDecision(
        contradiction_prior_revision_ref=contradiction.as_object().as_ref().as_dict(),
        resolution_input_history_cut=dict(input_history_cut),
        resolved_scope=dict(resolved_scope),
        resolution_kind=resolution_kind,
        basis_refs=basis_refs,
        resulting_status=resulting_status,
    )


def apply_contradiction_resolution(
    contradiction: ContradictionRevision,
    decision: ContradictionResolutionDecision,
) -> ContradictionRevision:
    """Materialize the N+1 contradiction revision in the normative resolution DAG."""
    if not _same_ref(decision.contradiction_prior_revision_ref, contradiction.as_object().as_ref().as_dict()):
        raise ValidationError("CONTRADICTION_RESOLUTION_PRIOR_MISMATCH")
    return ContradictionRevision(
        contradiction_id=contradiction.contradiction_id,
        contradiction_revision=_next_revision(contradiction.contradiction_revision),
        predecessor_contradiction_revision_ref=contradiction.as_object().as_ref().as_dict(),
        claim_revision_refs=contradiction.claim_revision_refs,
        scope=contradiction.scope,
        positions=contradiction.positions,
        supporting_evidence_qualification_refs=contradiction.supporting_evidence_qualification_refs,
        opposing_evidence_qualification_refs=contradiction.opposing_evidence_qualification_refs,
        failure_assumption_differences=contradiction.failure_assumption_differences,
        environment_input_model_differences=contradiction.environment_input_model_differences,
        required_falsifier=contradiction.required_falsifier,
        status=decision.resulting_status,
        resolution_decision_ref=decision.as_object().as_ref().as_dict(),
    )


def reopen_contradiction(
    prior_revision: ContradictionRevision,
    *,
    new_claim_revision_refs: Sequence[Any] = (),
    new_positions: Sequence[Any] = (),
    new_supporting_evidence_refs: Sequence[Any] = (),
    new_opposing_evidence_refs: Sequence[Any] = (),
    required_falsifier: Any | None = None,
    scope: Mapping[str, Any] | None = None,
    failure_assumption_differences: Sequence[Any] = (),
    environment_input_model_differences: Sequence[Any] = (),
) -> ContradictionRevision:
    """Append REOPENED successor state after material counterevidence."""
    claims = [*prior_revision.claim_revision_refs, *new_claim_revision_refs]
    positions = [*prior_revision.positions, *new_positions]
    supporting = [*prior_revision.supporting_evidence_qualification_refs, *new_supporting_evidence_refs]
    opposing = [*prior_revision.opposing_evidence_qualification_refs, *new_opposing_evidence_refs]
    failure_diffs = [*prior_revision.failure_assumption_differences, *failure_assumption_differences]
    environment_diffs = [
        *prior_revision.environment_input_model_differences,
        *environment_input_model_differences,
    ]
    if not new_claim_revision_refs and not new_positions and not new_supporting_evidence_refs and not new_opposing_evidence_refs:
        raise ValidationError("CONTRADICTION_REOPEN_REQUIRES_NEW_COUNTEREVIDENCE")
    return ContradictionRevision(
        contradiction_id=prior_revision.contradiction_id,
        contradiction_revision=_next_revision(prior_revision.contradiction_revision),
        predecessor_contradiction_revision_ref=prior_revision.as_object().as_ref().as_dict(),
        claim_revision_refs=claims,
        scope=dict(scope if scope is not None else prior_revision.scope),
        positions=positions,
        supporting_evidence_qualification_refs=supporting,
        opposing_evidence_qualification_refs=opposing,
        failure_assumption_differences=failure_diffs,
        environment_input_model_differences=environment_diffs,
        required_falsifier=(
            required_falsifier if required_falsifier is not None else prior_revision.required_falsifier
        ),
        status="REOPENED",
    )


def cluster_findings_into_root_cause(
    source_generation_ref: Any,
    membership_edges: Sequence[dict[str, Any]],
    *,
    mechanism_statement: str,
    scope: Mapping[str, Any] | None = None,
    status: str = "ACTIVE",
    predecessor_root_cause_refs: Sequence[Any] = (),
    multi_causal_condition: Any = None,
) -> RootCauseRevision:
    """Create an authoritative RootCauseRevision only after finding adjudication."""
    return RootCauseRevision(
        source_generation_ref=_ref_dict(source_generation_ref),
        mechanism_statement=mechanism_statement,
        membership_edges=sort_membership_edges(membership_edges),
        predecessor_root_cause_refs=predecessor_root_cause_refs,
        multi_causal_condition=multi_causal_condition,
        scope=dict(scope or {}),
        status=status,
    )

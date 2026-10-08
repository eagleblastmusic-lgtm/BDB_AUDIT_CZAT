"""M17/M18 Discovery Opportunity Map and Hypothesis lifecycle engine."""
from typing import Any, Mapping, Sequence

from ..core.errors import ValidationError
from .models import HypothesisRevision, DiscoveryOpportunity

LEGAL_TRANSITIONS = {
    "PROPOSED": {"PREREGISTERED", "TESTING", "REJECTED", "BLOCKED"},
    "PREREGISTERED": {"TESTING", "REJECTED", "BLOCKED"},
    "TESTING": {"CONFIRMED", "REJECTED", "UNRESOLVED", "BLOCKED"},
    "UNRESOLVED": {"TESTING", "REJECTED", "BLOCKED"},
    "BLOCKED": {"TESTING", "REJECTED", "UNRESOLVED"},
    # Terminal-like states that can create a new revision but cannot be retroactively changed
    "CONFIRMED": {"CONFIRMED", "REJECTED"},
    "REJECTED": {"REJECTED"},
}


def build_opportunity_map(
    surfaces: Sequence[Any],
    unsatisfied_obligations: Sequence[Any],
    unknown_scopes: Sequence[Any] = (),
    current_history_cut: dict | None = None,
) -> list[DiscoveryOpportunity]:
    """Build discovery opportunities (Gap logic) based on uncovered surfaces and unsatisfied obligations."""
    cut = current_history_cut or {"tag": "EMPTY_HISTORY"}
    opportunities = []

    for idx, surf in enumerate(surfaces):
        # Calculate priority score based on risk attributes and missing coverage
        priority = 10.0 + len(unsatisfied_obligations) * 2.0 + len(unknown_scopes) * 1.5
        opp = DiscoveryOpportunity(
            gap_id=f"gap_{idx + 1}",
            target_scope_ref=surf,
            missing_or_unsatisfied_obligation_refs=list(unsatisfied_obligations),
            unknown_scope_refs=list(unknown_scopes),
            materiality="MATERIAL",
            priority_score=priority,
            current_history_cut=cut,
        )
        opportunities.append(opp)

    return opportunities


def transition_hypothesis(
    hypothesis: HypothesisRevision,
    new_status: str,
    new_revision: str | None = None,
    new_statement: str | None = None,
    origin_discovery_ref: Any = None,
) -> HypothesisRevision:
    """Transition hypothesis through lifecycle, enforcing fail-closed rules:

    - No retroactive preregistration.
    - Rejected hypotheses remain in accepted history and can produce new revisions.
    - Valid state transition graph.
    """
    current_status = hypothesis.status

    # Retroactive preregistration check
    if new_status == "PREREGISTERED" and current_status in ("TESTING", "CONFIRMED", "REJECTED"):
        raise ValidationError("RETROACTIVE_PREREGISTRATION_FORBIDDEN", "Cannot retroactively preregister an active or completed hypothesis")

    allowed = LEGAL_TRANSITIONS.get(current_status, set())
    if new_status not in allowed and new_status != current_status:
        raise ValidationError("ILLEGAL_HYPOTHESIS_TRANSITION", f"Cannot transition from {current_status} to {new_status}")

    next_rev = new_revision or str(int(hypothesis.hypothesis_revision) + 1 if hypothesis.hypothesis_revision.isdigit() else hypothesis.hypothesis_revision + ".1")

    return HypothesisRevision(
        hypothesis_id=hypothesis.hypothesis_id,
        hypothesis_revision=next_rev,
        source_generation_ref=hypothesis.source_generation_ref,
        statement=new_statement or hypothesis.statement,
        scope_refs=hypothesis.scope_refs,
        invariant_refs=hypothesis.invariant_refs,
        obligation_refs=hypothesis.obligation_refs,
        origin_discovery_ref=origin_discovery_ref or hypothesis.origin_discovery_ref,
        planning_mode=hypothesis.planning_mode,
        status=new_status,
        input_history_cut=hypothesis.input_history_cut,
    )

"""RU15 skeptical review for product opportunities."""
from __future__ import annotations

from typing import Sequence

from .models import OpportunityAssessment, OpportunityProposal


def skeptic_review(proposal: OpportunityProposal, *, contradiction_codes: Sequence[str] = (), minimum_evidence_refs: int = 1) -> OpportunityAssessment:
    contradictions = tuple(sorted(set(contradiction_codes)))
    if contradictions:
        decision = "REVISE"
        rationale = "Contradictory or unresolved evidence requires revision before reporting."
    elif len(proposal.evidence_refs) < minimum_evidence_refs or proposal.basis == "INFERRED":
        decision = "REVISE"
        rationale = "Evidence basis is insufficient for an unqualified report recommendation."
    else:
        decision = "ACCEPT_FOR_REPORT"
        rationale = "Proposal is bounded by explicit evidence and remains non-mandatory."
    return OpportunityAssessment(
        proposal_id=proposal.proposal_id,
        decision=decision,
        evidence_refs=proposal.evidence_refs,
        rationale=rationale,
        uncertainty_codes=contradictions,
    )


def reject_opportunity(proposal: OpportunityProposal, reason: str) -> OpportunityAssessment:
    return OpportunityAssessment(proposal.proposal_id, "REJECT", proposal.evidence_refs, reason)


__all__ = ["skeptic_review", "reject_opportunity"]

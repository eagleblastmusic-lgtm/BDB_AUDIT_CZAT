"""RU15 deterministic opportunity ranking with explicit integer factors."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..core.errors import ValidationError
from .models import OpportunityAssessment, OpportunityProposal


def rank_opportunities(proposals: Sequence[OpportunityProposal], assessments: Sequence[OpportunityAssessment], impact: Mapping[str, int] | None = None) -> list[dict[str, Any]]:
    by_id = {item.proposal_id: item for item in assessments}
    impact = impact or {}
    rows: list[dict[str, Any]] = []
    for proposal in proposals:
        assessment = by_id.get(proposal.proposal_id)
        if assessment is None:
            raise ValidationError("OPPORTUNITY_ASSESSMENT_MISSING", proposal.proposal_id)
        evidence_score = min(len(proposal.evidence_refs), 5)
        impact_score = int(impact.get(proposal.proposal_id, 1))
        if not 0 <= impact_score <= 5:
            raise ValidationError("OPPORTUNITY_IMPACT_SCORE_INVALID", proposal.proposal_id)
        decision_score = {"ACCEPT_FOR_REPORT": 3, "REVISE": 1, "REJECT": 0}[assessment.decision]
        basis_score = {"OBSERVED": 2, "DECLARED": 1, "INFERRED": 0}[proposal.basis]
        score = evidence_score + impact_score + decision_score + basis_score
        rows.append({"proposal_id": proposal.proposal_id, "score": score, "decision": assessment.decision, "basis": proposal.basis, "mandatory_obligation": False})
    rows.sort(key=lambda item: (-item["score"], item["proposal_id"]))
    return rows


__all__ = ["rank_opportunities"]

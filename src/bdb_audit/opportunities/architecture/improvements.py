"""RU15 architecture improvement proposals remain optional opportunities."""
from __future__ import annotations

from typing import Sequence

from ..models import OpportunityProposal


def architecture_improvement(*, proposal_id: str, title: str, evidence_refs: Sequence[str], benefit_hypothesis: str, basis: str = "INFERRED") -> OpportunityProposal:
    return OpportunityProposal(
        proposal_id=proposal_id,
        title=title,
        opportunity_type="ARCHITECTURE",
        source_candidate_ids=(),
        evidence_refs=tuple(evidence_refs),
        benefit_hypothesis=benefit_hypothesis,
        basis=basis,
        mandatory_obligation=False,
    )


__all__ = ["architecture_improvement"]

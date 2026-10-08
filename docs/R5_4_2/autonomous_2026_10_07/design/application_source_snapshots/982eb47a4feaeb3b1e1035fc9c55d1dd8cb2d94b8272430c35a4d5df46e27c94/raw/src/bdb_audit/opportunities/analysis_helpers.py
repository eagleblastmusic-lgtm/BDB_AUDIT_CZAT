"""RU15 opportunity proposal synthesis from explicit friction candidates."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..core.errors import ValidationError
from .models import FrictionCandidate, OpportunityProposal


def propose_opportunities(candidates: Sequence[FrictionCandidate], proposals: Sequence[Mapping[str, Any]]) -> tuple[OpportunityProposal, ...]:
    by_id = {item.candidate_id: item for item in candidates}
    result: list[OpportunityProposal] = []
    for body in proposals:
        source_ids = tuple(str(item) for item in body.get("source_candidate_ids", ()))
        missing = [item for item in source_ids if item not in by_id]
        if missing:
            raise ValidationError("OPPORTUNITY_SOURCE_CANDIDATE_MISSING", ",".join(missing))
        sources = [by_id[item] for item in source_ids]
        evidence = tuple(sorted({ref for source in sources for ref in source.evidence_refs}))
        bases = {source.basis for source in sources}
        basis = "OBSERVED" if bases == {"OBSERVED"} and sources else "DECLARED" if bases == {"DECLARED"} and sources else "INFERRED"
        result.append(OpportunityProposal(
            proposal_id=str(body.get("proposal_id", "")),
            title=str(body.get("title", "")),
            opportunity_type=str(body.get("opportunity_type", "UX")),
            source_candidate_ids=source_ids,
            evidence_refs=evidence,
            benefit_hypothesis=str(body.get("benefit_hypothesis", "")),
            basis=basis,
            mandatory_obligation=False,
        ))
    return tuple(result)


__all__ = ["propose_opportunities"]

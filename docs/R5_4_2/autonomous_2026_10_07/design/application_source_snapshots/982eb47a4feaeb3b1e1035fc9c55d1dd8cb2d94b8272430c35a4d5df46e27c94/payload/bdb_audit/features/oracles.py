"""RU11 oracle qualification helpers."""
from __future__ import annotations

from typing import Sequence

from .models import BehaviorCase, OracleAssessment


def qualify_oracle(
    case: BehaviorCase,
    requirement_refs: Sequence[str],
    *,
    independence: str = "INDEPENDENT",
    rationale: str = "",
) -> OracleAssessment:
    refs = tuple(requirement_refs)
    if not refs:
        return OracleAssessment(
            case_id=case.case_id,
            status="UNQUALIFIED",
            independence=independence,
            requirement_refs=(),
            rationale=rationale or "No requirement/oracle basis supplied",
        )
    if independence != "INDEPENDENT":
        return OracleAssessment(
            case_id=case.case_id,
            status="UNQUALIFIED",
            independence=independence,
            requirement_refs=refs,
            rationale=rationale or "Oracle independence is not established",
        )
    return OracleAssessment(
        case_id=case.case_id,
        status="QUALIFIED",
        independence="INDEPENDENT",
        requirement_refs=refs,
        rationale=rationale,
    )


__all__ = ["qualify_oracle"]

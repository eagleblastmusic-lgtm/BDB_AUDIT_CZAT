"""RU15 friction extraction from explicit task traces."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..core.errors import ValidationError
from .models import FrictionCandidate, UserTaskTrace


def friction_from_input(trace: UserTaskTrace, body: Mapping[str, Any]) -> FrictionCandidate:
    basis = str(body.get("basis", trace.observation_mode))
    refs = tuple(body.get("evidence_refs", trace.evidence_refs))
    if basis == "OBSERVED" and trace.observation_mode != "OBSERVED":
        raise ValidationError("FRICTION_OBSERVED_WITHOUT_OBSERVED_TRACE")
    return FrictionCandidate(
        candidate_id=str(body.get("candidate_id", "")),
        trace_id=trace.trace_id,
        description=str(body.get("description", "")),
        evidence_refs=refs,
        basis=basis,
        severity=str(body.get("severity", "MEDIUM")),
    )


def extract_friction(traces: Sequence[UserTaskTrace], items: Sequence[Mapping[str, Any]]) -> tuple[FrictionCandidate, ...]:
    by_id = {trace.trace_id: trace for trace in traces}
    output: list[FrictionCandidate] = []
    for body in items:
        trace_id = str(body.get("trace_id", ""))
        trace = by_id.get(trace_id)
        if trace is None:
            raise ValidationError("FRICTION_TRACE_NOT_FOUND", trace_id)
        output.append(friction_from_input(trace, body))
    return tuple(output)


__all__ = ["friction_from_input", "extract_friction"]

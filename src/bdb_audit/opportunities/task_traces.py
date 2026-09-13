"""RU15 task-trace ingestion. No synthetic runtime walkthroughs are created."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..core.errors import ValidationError
from .models import ProductContext, UserTaskTrace


def task_trace_from_input(context: ProductContext, body: Mapping[str, Any]) -> UserTaskTrace:
    mode = str(body.get("observation_mode", "INFERRED"))
    runtime_observed = bool(body.get("runtime_observed", False))
    if runtime_observed and not context.runtime_available:
        raise ValidationError("TASK_TRACE_RUNTIME_NOT_AVAILABLE")
    return UserTaskTrace(
        trace_id=str(body.get("trace_id", "")),
        target_id=context.target_id,
        actor=str(body.get("actor", "")),
        steps=tuple(body.get("steps", ())),
        evidence_refs=tuple(body.get("evidence_refs", ())),
        observation_mode=mode,
        runtime_observed=runtime_observed,
    )


def ingest_task_traces(context: ProductContext, items: Sequence[Mapping[str, Any]]) -> tuple[UserTaskTrace, ...]:
    # Empty input stays empty. The product layer must not fabricate a default
    # user journey merely because runtime evidence is unavailable.
    return tuple(task_trace_from_input(context, item) for item in items)


__all__ = ["task_trace_from_input", "ingest_task_traces"]

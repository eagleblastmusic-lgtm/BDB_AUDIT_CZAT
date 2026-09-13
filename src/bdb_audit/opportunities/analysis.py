"""RU15 end-to-end derived opportunity analysis."""
from __future__ import annotations

from typing import Any, Mapping

from ..core.errors import ValidationError
from .friction import extract_friction
from .models import ProductContext
from .product_context import build_product_context
from .task_traces import ingest_task_traces
from .analysis_helpers import propose_opportunities


def analyze_opportunities(request: Mapping[str, Any]) -> dict[str, Any]:
    source_identity = request.get("source_identity")
    if not isinstance(source_identity, dict):
        raise ValidationError("PRODUCT_CONTEXT_SOURCE_IDENTITY_REQUIRED")
    context: ProductContext = build_product_context(
        target_id=str(request.get("target_id", "")),
        source_identity=source_identity,
        declared_goals=tuple(request.get("declared_goals", ())),
        personas=tuple(request.get("personas", ())),
        runtime_available=bool(request.get("runtime_available", False)),
    )
    traces_raw = request.get("task_traces", ())
    friction_raw = request.get("friction_candidates", ())
    proposals_raw = request.get("proposals", ())
    if not isinstance(traces_raw, list) or not isinstance(friction_raw, list) or not isinstance(proposals_raw, list):
        raise ValidationError("OPPORTUNITY_INPUT_COLLECTION_INVALID")
    traces = ingest_task_traces(context, [item for item in traces_raw if isinstance(item, dict)])
    friction = extract_friction(traces, [item for item in friction_raw if isinstance(item, dict)])
    proposals = propose_opportunities(friction, [item for item in proposals_raw if isinstance(item, dict)])
    return {
        "schema_version": "RU15-OPPORTUNITY-ANALYSIS-1",
        "authority": "DERIVED_PROPOSAL_ONLY",
        "context": context.as_dict(),
        "task_traces": [item.as_dict() for item in traces],
        "friction_candidates": [item.as_dict() for item in friction],
        "opportunities": [item.as_dict() for item in proposals],
        "no_runtime_trace_fabrication": not context.runtime_available and not any(item.runtime_observed for item in traces),
    }


__all__ = ["analyze_opportunities"]

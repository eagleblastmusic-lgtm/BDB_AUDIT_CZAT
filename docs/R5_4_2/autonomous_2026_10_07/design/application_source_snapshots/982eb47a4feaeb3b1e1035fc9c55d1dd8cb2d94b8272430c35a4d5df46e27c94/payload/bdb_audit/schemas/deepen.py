"""Schemas for E4 DEEPEN artifacts (Data Contracts §71, §72)."""
from typing import Any, Mapping


def deepen_schema(kind: str) -> Mapping[str, Any] | None:
    if kind == "model_fidelity_assessment":
        return {
            "required": [
                "fidelity_assessment_id",
                "model_revision_ref",
                "source_generation_ref",
                "implementation_anchor_refs",
                "abstraction_mapping_refs",
                "abstraction_assumptions",
                "omitted_states",
                "bounds",
                "fairness_time_assumptions",
                "execution_conformance_evidence_refs",
                "scope",
                "assessment_input_history_cut",
                "result",
                "reason_codes",
            ],
            "properties": {
                "fidelity_assessment_id": {"type": "string"},
                "model_revision_ref": {"type": "object"},
                "source_generation_ref": {"type": "object"},
                "implementation_anchor_refs": {"type": "array"},
                "abstraction_mapping_refs": {"type": "array"},
                "abstraction_assumptions": {"type": "array"},
                "omitted_states": {"type": "array"},
                "bounds": {"type": "array"},
                "fairness_time_assumptions": {"type": "array"},
                "execution_conformance_evidence_refs": {"type": "array"},
                "scope": {"type": "string"},
                "assessment_input_history_cut": {"type": "object"},
                "result": {
                    "type": "string",
                    "enum": ["QUALIFIED", "BOUNDED", "INSUFFICIENT", "INVALIDATED"],
                },
                "reason_codes": {"type": "array"},
            },
        }
    return None

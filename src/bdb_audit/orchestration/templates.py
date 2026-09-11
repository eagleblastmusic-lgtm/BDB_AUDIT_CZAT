"""Canonical prompt and report templates for BDB Audit v2 (R5.3 §18).

Provides immutable, byte-pinned template definitions, schema/boundary
validation, and deterministic rendering.
"""
from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError


@dataclass(frozen=True)
class PromptTemplate:
    template_id: str
    version: str
    target_stage: str
    required_variables: tuple[str, ...]
    body_pattern: str

    def render(self, variables: Mapping[str, Any]) -> str:
        # Check required variables
        for var in self.required_variables:
            if var not in variables or variables[var] is None:
                raise ValidationError("MALFORMED_TEMPLATE", f"Missing required variable: {var}")

        # Guard against injection across authority boundary:
        # Template inputs cannot contain instruction injection or bypass directives
        for k, v in variables.items():
            if isinstance(v, str):
                for forbidden in ("IGNORE_PROTOCOL", "SKIP_GATE", "BYPASS_VALIDATION", "READ_HIDDEN_REPORT"):
                    if forbidden in v.upper():
                        raise ValidationError("INJECTION_ACROSS_AUTHORITY_BOUNDARY", f"Forbidden directive: {forbidden}")

        # Deterministic substitution
        result = self.body_pattern
        for k in sorted(self.required_variables):
            placeholder = f"{{{k}}}"
            if placeholder in result:
                val_str = str(variables[k])
                result = result.replace(placeholder, val_str)
        return result


# Canonical template registry definitions
CANONICAL_PROMPT_TEMPLATES: dict[str, PromptTemplate] = {
    "foundation": PromptTemplate(
        template_id="foundation",
        version="1.0.0",
        target_stage="F2_FOUNDATION",
        required_variables=("ordinal", "stage_spec_revision", "lane_spec_revision"),
        body_pattern="BDB Foundation Stage {ordinal} | StageSpec: {stage_spec_revision} | LaneSpec: {lane_spec_revision}",
    ),
    "e1_ensemble": PromptTemplate(
        template_id="e1_ensemble",
        version="1.0.0",
        target_stage="E1_ENSEMBLE",
        required_variables=("slot", "stage_spec_revision", "lane_spec_revision"),
        body_pattern="BDB E1 Native Ensemble Lane {slot} | StageSpec: {stage_spec_revision} | LaneSpec: {lane_spec_revision}",
    ),
    "e2_cross_review": PromptTemplate(
        template_id="e2_cross_review",
        version="1.0.0",
        target_stage="E2_CROSS_REVIEW",
        required_variables=("slot", "predecessor_cut"),
        body_pattern="BDB E2 Cross Review Lane {slot} | Prior Head: {predecessor_cut}",
    ),
    "e3_blind": PromptTemplate(
        template_id="e3_blind",
        version="1.0.0",
        target_stage="E3_BLIND_GAP",
        required_variables=("slot", "holdout_id"),
        body_pattern="BDB E3 Blind Gap Exploration Lane {slot} | Holdout Partition: {holdout_id}",
    ),
    "e4_deepen": PromptTemplate(
        template_id="e4_deepen",
        version="1.0.0",
        target_stage="E4_DEEPEN",
        required_variables=("focus_area", "depth_level"),
        body_pattern="BDB E4 Deepen Exploration Focus: {focus_area} | Depth: {depth_level}",
    ),
    "e5_attack": PromptTemplate(
        template_id="e5_attack",
        version="1.0.0",
        target_stage="E5_ATTACK",
        required_variables=("candidate_id", "challenger_profile"),
        body_pattern="BDB E5 Adversarial Challenge Candidate: {candidate_id} | Profile: {challenger_profile}",
    ),
    "e6_adaptive": PromptTemplate(
        template_id="e6_adaptive",
        version="1.0.0",
        target_stage="E6_ADAPTIVE",
        required_variables=("stop_evaluation_ref", "budget"),
        body_pattern="BDB E6 Adaptive Extension Evaluator: {stop_evaluation_ref} | Budget: {budget}",
    ),
}


class TemplateRegistry:
    """Registry and compiler validator for prompt and report templates."""

    def __init__(self, templates: Mapping[str, PromptTemplate] | None = None):
        self._templates = dict(templates or CANONICAL_PROMPT_TEMPLATES)

    def get(self, template_id: str) -> PromptTemplate:
        if template_id not in self._templates:
            raise ValidationError("MALFORMED_TEMPLATE", f"Unknown template ID: {template_id}")
        return self._templates[template_id]

    def render(self, template_id: str, variables: Mapping[str, Any]) -> str:
        template = self.get(template_id)
        return template.render(variables)

    def validate_inputs(self, template_id: str, variables: Mapping[str, Any]) -> None:
        template = self.get(template_id)
        for var in template.required_variables:
            if var not in variables:
                raise ValidationError("MALFORMED_TEMPLATE", f"Missing required variable: {var}")

        # Guard against injection across authority boundary
        for k, v in variables.items():
            if isinstance(v, str):
                for forbidden in ("IGNORE_PROTOCOL", "SKIP_GATE", "BYPASS_VALIDATION", "READ_HIDDEN_REPORT"):
                    if forbidden in v.upper():
                        raise ValidationError("INJECTION_ACROSS_AUTHORITY_BOUNDARY", f"Forbidden directive in {k}: {forbidden}")

        # Check staleness if history cut or revision is provided
        if "history_cut" in variables and isinstance(variables["history_cut"], dict):
            cut = variables["history_cut"]
            if cut.get("stale"):
                raise ValidationError("STALE_INPUTS", "History cut is marked stale")

    def list_templates(self) -> dict[str, dict[str, Any]]:
        return {
            tid: {
                "template_id": t.template_id,
                "version": t.version,
                "target_stage": t.target_stage,
                "required_variables": list(t.required_variables),
                "digest": hashlib.sha256(canonical_bytes({
                    "template_id": t.template_id,
                    "version": t.version,
                    "target_stage": t.target_stage,
                    "required_variables": list(t.required_variables),
                    "body_pattern": t.body_pattern,
                })).hexdigest(),
            }
            for tid, t in sorted(self._templates.items())
        }


__all__ = ["PromptTemplate", "CANONICAL_PROMPT_TEMPLATES", "TemplateRegistry"]

"""Executable field contracts and schemas for Assurance & Finalization (F7 / M42-M45A)."""
from __future__ import annotations

FIELDS = {
    "residual_risk": (
        "risk_id risk_revision scope description materiality uncertainty_class reason_unresolved "
        "disposition blocking_effect history_cut related_obligation_refs related_hypothesis_refs "
        "evidence_refs status"
    ),
    "candidate_assurance_case": (
        "candidate_assurance_case_id campaign_ref source_generation_ref candidate_input_history_cut "
        "scope_inventory_ref coverage_obligation_refs coverage_obligation_qualification_refs "
        "finding_claim_revision_refs finding_adjudication_refs contradiction_refs "
        "evidence_qualification_refs residual_risk_refs assurance_claim_set_ref"
    ),
    "challenger_assignment": (
        "challenge_assignment_id candidate_assurance_case_ref challenger_type challenge_scope "
        "challenge_policy_ref executor_profile_ref assignment_input_history_cut"
    ),
    "challenger_result": (
        "challenger_result_id challenge_assignment_ref candidate_assurance_case_ref "
        "result_input_history_cut challenged_claim_or_scope_refs counterclaim_refs "
        "evidence_qualification_refs status reason_codes"
    ),
    "campaign_conclusion": (
        "campaign_conclusion_id campaign_ref source_generation_ref stop_evaluation_ref "
        "termination_state assurance_level bounded_conclusion_statement residual_risk_refs "
        "conclusion_command_input_history_cut"
    ),
    "final_assurance_case": (
        "final_assurance_case_id campaign_conclusion_ref stop_evaluation_ref residual_risk_refs "
        "public_conclusion_statement_ref final_case_input_history_cut"
    ),
    "release_qualification": (
        "release_qualification_id campaign_conclusion_ref final_assurance_case_ref stop_evaluation_ref "
        "source_generation_ref release_policy_ref release_assessment_basis_cut "
        "qualification_command_input_history_cut assessment_basis result "
        "blocking_finding_or_risk_refs accepted_residual_risk_refs reason_codes"
    ),
    "successor_campaign_genesis": (
        "campaign_id predecessor_campaign_ref predecessor_conclusion_ref successor_trigger_ref "
        "source_generation_ref successor_input_history_cut carried_forward_qualification_refs "
        "newly_required_obligation_refs challenge_freshness_policy_ref governing_policy_ref "
        "governing_spec_refs"
    ),
    "successor_campaign_selection_decision": (
        "selection_decision_id predecessor_conclusion_ref candidate_successor_campaign_refs "
        "selected_successor_campaign_ref resolution_basis_refs governing_policy_ref input_history_cut"
    ),
}

OPTIONAL = {
    "residual_risk": ("owner_approval_ref", "waiver_ref"),
    "candidate_assurance_case": ("coverage_obligation_summary_ref",),
    "challenger_assignment": ("forbidden_prior_result_refs",),
    "campaign_conclusion": ("candidate_assurance_case_ref", "limited_conclusion_basis_refs"),
    "final_assurance_case": ("candidate_assurance_case_ref", "challenger_result_refs", "limited_conclusion_basis_refs"),
    "release_qualification": ("previous_release_qualification_ref", "release_reassessment_input_refs"),
}

ARRAYS = {
    "related_obligation_refs", "related_hypothesis_refs", "evidence_refs",
    "coverage_obligation_refs", "coverage_obligation_qualification_refs",
    "finding_claim_revision_refs", "finding_adjudication_refs", "contradiction_refs",
    "evidence_qualification_refs", "residual_risk_refs", "forbidden_prior_result_refs",
    "challenged_claim_or_scope_refs", "counterclaim_refs", "reason_codes",
    "limited_conclusion_basis_refs", "challenger_result_refs", "blocking_finding_or_risk_refs",
    "accepted_residual_risk_refs", "release_reassessment_input_refs",
    "carried_forward_qualification_refs", "newly_required_obligation_refs",
    "governing_spec_refs", "candidate_successor_campaign_refs", "resolution_basis_refs",
}

OBJECTS = {
    "history_cut",
    "candidate_input_history_cut", "assignment_input_history_cut", "result_input_history_cut",
    "conclusion_command_input_history_cut", "final_case_input_history_cut",
    "release_assessment_basis_cut", "qualification_command_input_history_cut",
    "successor_input_history_cut", "input_history_cut",
}


def assurance_schema(kind: str):
    if kind not in FIELDS:
        return None
    fields = FIELDS[kind].split()
    properties = {}
    for name in fields + list(OPTIONAL.get(kind, ())):
        if name in ARRAYS:
            properties[name] = {"type": "array"}
        elif name in OBJECTS:
            properties[name] = {"type": "object"}
        elif name.endswith("_ref"):
            properties[name] = {
                "type": "object",
                "required": ["kind", "revision_digest", "digest_profile", "schema_revision_ref", "ref_class"],
            }
        else:
            properties[name] = {"type": ["string", "number", "object"]}

    if kind == "residual_risk":
        for name in (
            "risk_id", "risk_revision", "scope", "description", "uncertainty_class",
            "reason_unresolved",
        ):
            properties[name] = {"type": "string", "minLength": 1}
        properties["materiality"] = {"enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]}
        properties["disposition"] = {
            "enum": ["OPEN", "BOUNDED", "ACCEPTED_RESIDUAL_RISK", "BLOCKED", "UNKNOWN", "SUPERSEDED"]
        }
        properties["blocking_effect"] = {"type": "boolean"}
        properties["status"] = {"enum": ["VALID", "INVALIDATED", "CONTRADICTED", "STALE"]}
    elif kind == "challenger_assignment":
        properties["challenger_type"] = {
            "enum": ["FALSE_POSITIVE_SKEPTIC", "FALSE_NEGATIVE_HUNTER", "OTHER_POLICY_DEFINED"]
        }
    elif kind == "challenger_result":
        properties["status"] = {
            "enum": [
                "NO_MATERIAL_COUNTEREVIDENCE",
                "MATERIAL_COUNTEREVIDENCE_FOUND",
                "INCONCLUSIVE",
                "BLOCKED",
            ]
        }
    elif kind == "campaign_conclusion":
        properties["termination_state"] = {
            "enum": ["OPEN", "COMPLETED", "COMPLETED_LIMITED"]
        }
        properties["assurance_level"] = {
            "enum": ["ADEQUATE_FOR_DECLARED_SCOPE", "BOUNDED", "INSUFFICIENT"]
        }
    elif kind == "release_qualification":
        properties["assessment_basis"] = {
            "enum": ["STOP_AXIS_MATERIALIZATION", "FRESH_RELEASE_QUALIFICATION", "RELEASE_REASSESSMENT"]
        }
        properties["result"] = {
            "enum": ["READY", "READY_WITH_RESIDUAL_RISK", "TECHNICALLY_NOT_READY", "QUALIFICATION_BLOCKED"]
        }

    return {
        "type": "object",
        "required": fields,
        "properties": properties,
        "additionalProperties": False,
    }

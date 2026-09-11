"""Executable field contracts for Stage/Lane Completion and STOP Gate (M24 / PR-027)."""

FIELDS = {
    "stage_completion": (
        "stage_completion_id stage_run_ref stage_spec_ref input_history_cut "
        "required_lane_slot_results required_output_refs mandatory_obligation_summary "
        "unresolved_material_refs unknown_blocked_summary completion_predicate_result"
    ),
    "lane_completion": (
        "lane_completion_id lane_run_ref lane_spec_ref input_history_cut "
        "attempt_refs final_knowledge_state_ref required_output_refs "
        "isolation_qualification_ref contamination_assessment_refs completion_predicate_result"
    ),
    "stop_input": (
        "stop_input_id campaign_id source_generation_ref input_history_cut evaluation_context "
        "governing_policy_ref policy_spec_refs evaluator_revision_ref required_stage_set_ref "
        "required_stage_spec_refs completed_stage_refs pending_required_stage_refs "
        "stop_input_snapshot_ref inventory_revision_ref mandatory_obligation_refs "
        "current_obligation_qualification_refs evidence_invalidation_refs contradiction_refs "
        "residual_risk_refs evidence_invalidation_state release_policy_ref effort_profile_ref "
        "effort_results_ref unknown_blocked_summary"
    ),
    "stop_evaluation": (
        "stop_evaluation_id stop_input_ref continuation_decision assurance_level "
        "release_readiness reason_codes blocking_obligation_refs remaining_obligation_refs"
    ),
}

OPTIONAL = {
    "stop_input": (
        "candidate_assurance_case_ref",
        "challenger_refs",
        "challenger_freshness_profile_ref",
        "release_basis_refs",
        "continuation_budget_authorization_ref",
    ),
}

ARRAYS = {
    "required_lane_slot_results", "required_output_refs", "unresolved_material_refs",
    "attempt_refs", "contamination_assessment_refs", "policy_spec_refs",
    "required_stage_spec_refs", "completed_stage_refs", "pending_required_stage_refs",
    "mandatory_obligation_refs", "current_obligation_qualification_refs",
    "evidence_invalidation_refs", "contradiction_refs", "residual_risk_refs",
    "challenger_refs", "release_basis_refs", "reason_codes",
    "blocking_obligation_refs", "remaining_obligation_refs",
}

OBJECTS = {
    "input_history_cut", "mandatory_obligation_summary", "unknown_blocked_summary",
}


def stop_schema(kind):
    if kind == "snapshot":
        return snapshot_schema()
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

    if kind == "stage_completion":
        properties["completion_predicate_result"] = {
            "enum": ["STAGE_COMPLETED", "STAGE_COMPLETION_BLOCKED"]
        }
    elif kind == "lane_completion":
        properties["completion_predicate_result"] = {
            "enum": ["LANE_COMPLETED", "LANE_COMPLETION_BLOCKED"]
        }
    elif kind == "stop_input":
        properties["evaluation_context"] = {
            "enum": ["INTERMEDIATE", "FINAL_POST_E5", "POST_E6"]
        }
    elif kind == "stop_evaluation":
        properties["continuation_decision"] = {
            "enum": ["PASS", "CONTINUE_REQUIRED", "E6_REQUIRED", "BLOCKED"]
        }
        properties["assurance_level"] = {
            "enum": ["ADEQUATE_FOR_DECLARED_SCOPE", "BOUNDED", "INSUFFICIENT"]
        }
        properties["release_readiness"] = {
            "enum": [
                "READY", "READY_WITH_RESIDUAL_RISK",
                "TECHNICALLY_NOT_READY", "QUALIFICATION_BLOCKED"
            ]
        }

    return {
        "type": "object",
        "required": fields,
        "properties": properties,
        "additionalProperties": False,
    }


def snapshot_schema():
    return {
        "type": "object",
        "required": [
            "snapshot_id",
            "snapshot_type",
            "as_of_head",
            "projection_code_revision",
            "projection_input_refs",
            "snapshot_artifact_ref",
        ],
        "properties": {
            "snapshot_id": {"type": "string"},
            "snapshot_type": {"type": "string"},
            "as_of_head": {"type": "object"},
            "projection_code_revision": {"type": "string"},
            "projection_input_refs": {
                "type": "array",
                "items": {"type": "object"},
            },
            "snapshot_artifact_ref": {"type": "object"},
        },
        "additionalProperties": False,
    }


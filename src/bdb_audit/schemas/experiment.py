"""Executable field contracts for Experiment and Execution artifacts (M19)."""

FIELDS = {
    "experiment_spec": "experiment_id experiment_revision hypothesis_revision_ref invariant_revision_ref coverage_obligation_refs subject_baseline_ref target_execution_variant_ref environment_profile_ref dependency_set_ref harness_ref fixture_refs trigger expected_safe_behavior expected_buggy_behavior observation_path_requirements falsification_condition positive_controls negative_controls input_history_cut",
    "execution_descriptor": "execution_descriptor_id experiment_spec_ref executor_profile_ref attempt_ref input_history_cut environment_actuals execution_nonce",
    "fault_run_record": "fault_run_record_id execution_descriptor_ref fault_ref activation_status",
    "cleanup_result": "cleanup_result_id execution_descriptor_ref cleanup_status residual_artifacts_cleared",
    "execution_result": "execution_result_id execution_descriptor_ref exit_code status observation_refs",
    "tool_execution_record": "tool_execution_id execution_descriptor_ref tool_name exit_code",
}

OPTIONAL = {
    "experiment_spec": ("fault_ref",),
    "execution_result": ("fault_activation_record_ref", "cleanup_result_ref"),
    "fault_run_record": ("evidence_refs",),
}

ARRAYS = {
    "coverage_obligation_refs", "fixture_refs", "observation_path_requirements",
    "positive_controls", "negative_controls", "observation_refs", "evidence_refs",
}

OBJECTS = {
    "input_history_cut", "environment_actuals",
}


def experiment_schema(kind):
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
            properties[name] = {"type": ["string", "number", "object", "boolean"]}

    if kind == "cleanup_result":
        properties["cleanup_status"] = {"enum": ["CLEAN", "DIRTY", "FAILED"]}
        properties["residual_artifacts_cleared"] = {"type": "boolean"}
    elif kind == "execution_result":
        properties["status"] = {"enum": ["SUCCESS", "FAILED", "CRASHED", "TIMED_OUT"]}

    return {
        "type": "object",
        "required": fields,
        "properties": properties,
        "additionalProperties": False,
    }

"""Executable field contracts for Evidence artifacts (M20)."""

FIELDS = {
    "observation": "observation_id execution_descriptor_ref raw_observation_ref observation_channel observed_at",
    "dependency_independence_assessment": "assessment_id claim_revision_ref assessment_input_history_cut dependency_graph_ref observer_path_refs shared_dependency_refs independent_dependency_refs independence_policy_ref result reason_codes",
    "evidence_applicability_assessment": "assessment_id claim_revision_ref assessment_input_history_cut dependency_set_ref environment_ref execution_variant_ref harness_ref subject_baseline_ref status reason_codes",
    "evidence_qualification_assessment": "assessment_id claim_revision_ref assessment_input_history_cut dependency_graph_ref independence_assessment_ref applicability_assessment_ref observation_refs result reason_codes",
    "evidence_invalidation": "invalidation_id affected_evidence_or_qualification_refs dependency_ref invalidation_input_history_cut propagation_policy_ref reason_codes",
}

OPTIONAL = {
    "evidence_applicability_assessment": ("previous_assessment_ref", "fixture_refs"),
    "evidence_qualification_assessment": ("controls_refs",),
}

ARRAYS = {
    "observer_path_refs", "shared_dependency_refs", "independent_dependency_refs",
    "reason_codes", "fixture_refs", "controls_refs", "observation_refs",
    "affected_evidence_or_qualification_refs",
}

OBJECTS = {
    "assessment_input_history_cut", "invalidation_input_history_cut",
}


def evidence_schema(kind):
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

    if kind == "dependency_independence_assessment":
        properties["result"] = {"enum": ["INDEPENDENT", "SHARED_DEPENDENCY", "CONFLICTED", "REJECTED"]}
    elif kind == "evidence_applicability_assessment":
        properties["status"] = {"enum": ["ACTIVE", "SCOPED", "STALE", "INVALIDATED", "BLOCKED", "CONFLICTED"]}
    elif kind == "evidence_qualification_assessment":
        properties["result"] = {"enum": ["SUPPORTS", "REFUTES", "INCONCLUSIVE", "INVALID"]}

    return {
        "type": "object",
        "required": fields,
        "properties": properties,
        "additionalProperties": False,
    }

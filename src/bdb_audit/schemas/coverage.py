"""Executable field contracts for Invariant and Coverage Obligation artifacts (M15/M16)."""

FIELDS = {
    "invariant_revision": "invariant_id invariant_revision invariant_input_history_cut source_generation_ref statement target_scope_refs category origin activation_policy_ref status",
    "materiality_assessment": "materiality_assessment_id subject_ref assessment_input_history_cut materiality_policy_ref scope supporting_fact_refs result rationale reason_codes",
    "coverage_obligation_key": "source_generation_ref target_scope_or_surface_ref invariant_logical_id scenario_class environment_profile_ref policy_obligation_key",
    "coverage_obligation": "obligation_id obligation_revision obligation_input_history_cut source_generation_ref target_scope_or_surface_ref invariant_revision_ref scenario_class environment_profile_ref materiality_assessment_ref required_technique_or_capability_refs required_oracle_independence_predicate_ref acceptance_predicate_ref falsifier_or_control_requirements applicability_predicate_ref policy_obligation_key governing_policy_ref origin_ref",
    "coverage_obligation_qualification": "qualification_id obligation_revision_ref input_history_cut qualification_status evidence_qualification_refs contradiction_refs reason_codes",
    "obligation_applicability_decision": "applicability_decision_id obligation_revision_ref assessment_input_history_cut applicability_policy_ref scope supporting_evidence_refs result reason_codes",
    "approval_decision": "decision_id decision_type decision actor_ref actor_authority_ref input_history_cut related_refs reason_codes",
}

OPTIONAL = {
    "coverage_obligation_qualification": ("substantive_outcome", "applicability_decision_ref", "waiver_decision_ref"),
    "approval_decision": ("rationale",),
}

ARRAYS = {
    "target_scope_refs", "supporting_fact_refs", "reason_codes",
    "required_technique_or_capability_refs", "falsifier_or_control_requirements",
    "evidence_qualification_refs", "contradiction_refs", "supporting_evidence_refs",
    "related_refs",
}

OBJECTS = {
    "invariant_input_history_cut", "assessment_input_history_cut",
    "obligation_input_history_cut", "input_history_cut",
}


def coverage_schema(kind):
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

    if kind == "invariant_revision":
        properties["status"] = {"enum": ["ACTIVE", "SUPERSEDED", "RETIRED", "INVALIDATED"]}
    elif kind == "materiality_assessment":
        properties["result"] = {"enum": ["MATERIAL", "NON_MATERIAL", "UNKNOWN", "CONFLICTED"]}
    elif kind == "coverage_obligation_qualification":
        properties["qualification_status"] = {
            "enum": ["UNASSESSED", "IN_PROGRESS", "QUALIFIED", "BLOCKED", "STALE"]
        }
        properties["substantive_outcome"] = {
            "enum": ["NO_VIOLATION_OBSERVED", "VIOLATION_CONFIRMED", "INCONCLUSIVE"]
        }
    elif kind == "obligation_applicability_decision":
        properties["result"] = {"enum": ["APPLICABLE", "NOT_APPLICABLE", "UNKNOWN", "CONFLICTED"]}
    elif kind == "approval_decision":
        properties["decision"] = {"enum": ["APPROVED", "REJECTED"]}

    return {
        "type": "object",
        "required": fields,
        "properties": properties,
        "additionalProperties": False,
    }

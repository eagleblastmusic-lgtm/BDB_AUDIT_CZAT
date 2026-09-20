"""Executable field contracts transcribed from Data Contracts 10, 11, 14.1."""

FIELDS = {
    "stage_spec": "stage_key stage_spec_revision stage_role stage_ordinal purpose predecessor_requirements required_lane_slots optional_lane_slots blind_reveal_phase_model allowed_corpus_roles forbidden_corpus_roles coverage_obligation_policy_ref required_stage_completion_outputs transition_policy_ref stop_e6_relationship",
    "lane_spec": "lane_key lane_spec_revision stage_spec_revision purpose primary_strategy scope_selectors exploration_policy_ref allowed_view_classes forbidden_knowledge_classes required_isolation_assurance required_outputs executor_capability_requirements budget_effort_profile_ref completion_predicate_ref",
    "stage_run": "stage_run_id campaign_ref stage_spec_ref source_generation_ref creation_input_history_cut assigned_history_cut predecessor_stage_completion_refs required_lane_slot_contract_refs",
    "lane_run": "lane_run_id stage_run_ref lane_spec_ref source_generation_ref creation_input_history_cut required_result_slots",
    "attempt": "attempt_id lane_run_ref attempt_nonce executor_profile_ref delivery_profile_ref assigned_history_cut result_slot_contracts",
    "isolation_qualification": "isolation_qualification_id attempt_ref assessment_input_history_cut executor_profile_ref delivery_profile_ref channel_inventory_ref enforcement_receipt_refs filesystem_boundary_evidence_refs network_boundary_evidence_refs tool_boundary_evidence_refs session_boundary_evidence_refs contamination_assessment_refs required_isolation_assurance result scope limitations reason_codes",
    "bdb_audit_lane_result": "kind version campaign_id stage_id lane_slot source_commit_sha history_cut input_package_digest executor_profile executor_model findings",
}
OPTIONAL = {
    "stage_run": ("successor_of_stage_run_ref",), "lane_run": ("successor_of_lane_run_ref",),
    "attempt": ("retry_of_attempt_ref", "retry_reason_ref"),
    "bdb_audit_lane_result": (
        "phase_id", "outputs", "findings_count", "notes", "evidence_files",
        "assignment_ref", "attempt_ref", "raw_result_digest",
        "raw_result_byte_length",
    ),
}
ARRAYS = set("predecessor_requirements required_lane_slots optional_lane_slots allowed_corpus_roles forbidden_corpus_roles required_stage_completion_outputs scope_selectors allowed_view_classes forbidden_knowledge_classes required_outputs executor_capability_requirements predecessor_stage_completion_refs required_lane_slot_contract_refs required_result_slots result_slot_contracts findings evidence_files".split())
ARRAYS.update("enforcement_receipt_refs filesystem_boundary_evidence_refs network_boundary_evidence_refs tool_boundary_evidence_refs session_boundary_evidence_refs contamination_assessment_refs limitations reason_codes".split())


def orchestration_schema(kind):
    if kind not in FIELDS:
        return None
    fields = FIELDS[kind].split()
    properties = {}
    for name in fields + list(OPTIONAL.get(kind, ())):
        if name in ARRAYS:
            properties[name] = {"type": "array", "uniqueItems": True}
        elif name.endswith("history_cut"):
            properties[name] = {"type": "object"}
        elif name.endswith("_ref") and (
            kind in {"stage_run", "lane_run", "attempt", "isolation_qualification"}
            or kind == "bdb_audit_lane_result"
        ) and name != "campaign_ref":
            properties[name] = {"type": "object", "required": ["kind", "revision_digest", "digest_profile", "schema_revision_ref", "ref_class"]}
        elif name in {"stage_ordinal", "raw_result_byte_length", "findings_count"}:
            properties[name] = {"type": "integer", "minimum": 0 if name != "stage_ordinal" else 1}
        else:
            properties[name] = {"type": "string"}
    if kind == "attempt":
        properties["result_slot_contracts"]["minItems"] = 1
    if kind == "lane_spec":
        properties["required_isolation_assurance"] = {"enum": ["ENFORCED", "DECLARED", "UNKNOWN"]}
    if kind == "isolation_qualification":
        properties["result"] = {"enum": ["ENFORCED", "DECLARED", "UNKNOWN"]}
        properties["required_isolation_assurance"] = {"enum": ["ENFORCED", "DECLARED", "UNKNOWN"]}
    if kind == "bdb_audit_lane_result":
        properties["findings"] = {"type": "array"}
        properties["history_cut"] = {"type": "object"}
        properties["lane_slot"] = {"type": "string", "minLength": 1}
        properties["stage_id"] = {"enum": ["E1", "E2", "E3", "E4", "E5", "E6"]}
        properties["phase_id"] = {"type": "string", "minLength": 1}
        properties["outputs"] = {"type": "object"}
        properties["kind"] = {"const": "bdb_audit_lane_result"}
        properties["version"] = {"const": "1"}
        properties["raw_result_digest"] = {"type": "string", "format": "bdb-sha256"}
    return {"type": "object", "required": fields, "properties": properties, "additionalProperties": False}

"""Executable bootstrap data fields from Data Contracts §§8, 9, 90–91.

Reference shapes are supplied separately from the exact Registry contract.
These required data fields are not inferred from reference names.
"""

REQUIRED = {
    "source_generation": "source_generation_id source_identity_ref source_identity_profile_ref materialized_source_manifest_ref representation_refs",
    "source_identity": "profile_ref authority_mode authorized_repository_or_snapshot_ref materialized_source_manifest_ref completeness_state",
    "source_manifest": "entries",
    "legacy_raw_ref": "legacy_ref_id raw_digest byte_length media_type import_input_history_cut",
    "legacy_mechanical_validation_assessment": "assessment_id legacy_ref assessment_input_history_cut legacy_schema_ref legacy_profile_ref mechanical_validation_policy_ref parsed_legacy_variant_stage_facts integrity_check_results result reason_codes",
    "source_reconciliation_assessment": "assessment_id legacy_ref assessment_input_history_cut target_source_generation_ref identity_profile_ref reconciliation_policy_ref raw_identifiers normalized_identity_body_ref result reason_codes",
    "lineage_admission_assessment": "assessment_id legacy_ref assessment_input_history_cut admission_policy_ref mechanical_validation_assessment_ref source_reconciliation_assessment_ref requested_role validation_level freshness_binding_refs result reason_codes",
    "legacy_exposure_reconstruction_assessment": "assessment_id legacy_ref assessment_input_history_cut reconstruction_policy_ref declared_scope controlled_exposure_fact_refs known_missing_channel_classes confidence supporting_history_refs blind_origin_claim_scope limitations",
    "trusted_predecessor_selection_decision": "trusted_predecessor_selection_decision_id selection_input_history_cut candidate_legacy_refs source_reconciliation_assessment_ref lineage_admission_assessment_ref selection_policy_ref predecessor_pin_ref decision reason_codes",
    "bootstrap_admission_decision": "bootstrap_admission_decision_id legacy_ref requested_role mechanical_validation_assessment_ref source_reconciliation_assessment_ref lineage_admission_assessment_ref admission_policy_ref admission_input_history_cut result limitations reason_codes",
    "campaign_genesis": "campaign_id input_history_cut bootstrap_admission_decision_ref source_generation_ref application_generation_ref protocol_policy_bundle_ref schema_set_ref owner_operator_authority_ref trust_profile_ref legacy_origin_refs",
}
OPTIONAL = {
    "source_generation": "repository_authority_ref snapshot_authority_ref parent_source_generation_ref",
    "source_identity": "git_commit_object_id git_tree_object_id",
    "legacy_raw_ref": "legacy_contract_hint original_path",
    "lineage_admission_assessment": "predecessor_pin_ref",
    "trusted_predecessor_selection_decision": "selected_legacy_ref",
    "bootstrap_admission_decision": "trusted_predecessor_selection_ref exposure_reconstruction_assessment_ref",
}
ENUMS = {
    "legacy_mechanical_validation_assessment": ("result", "VALID INVALID INSUFFICIENT_DATA"),
    "source_reconciliation_assessment": ("result", "EXACT_MATCH CONFLICT INSUFFICIENT_DATA"),
    "lineage_admission_assessment": ("result", "ADMITTED ADMITTED_WITH_LIMIT BLOCKED"),
    "legacy_exposure_reconstruction_assessment": ("confidence", "EXACT STRONG PARTIAL UNKNOWN"),
    "trusted_predecessor_selection_decision": ("decision", "SELECTED REJECTED CONFLICTED INSUFFICIENT_DATA"),
    "bootstrap_admission_decision": ("result", "CANONICAL_BOOTSTRAP_ADMITTED CANONICAL_BOOTSTRAP_ADMITTED_WITH_EXPOSURE_LIMIT BLOCKED_CANONICAL_ADMISSION"),
}
ARRAYS = set("representation_refs entries integrity_check_results reason_codes freshness_binding_refs controlled_exposure_fact_refs known_missing_channel_classes supporting_history_refs limitations candidate_legacy_refs legacy_origin_refs".split())


def bootstrap_schema(kind):
    if kind not in REQUIRED:
        return None
    required = REQUIRED[kind].split()
    properties = {}
    for name in required + OPTIONAL.get(kind, "").split():
        if name in ARRAYS:
            properties[name] = {"type": "array"}
        elif name.endswith("_ref") or name.endswith("_history_cut"):
            properties[name] = {"type": "object"}
        elif name in {"parsed_legacy_variant_stage_facts", "raw_identifiers"}:
            properties[name] = {"type": "object"}
        elif name == "byte_length":
            properties[name] = {"type": "integer", "minimum": 0}
        else:
            properties[name] = {"type": "string", "minLength": 1}
    if kind in ENUMS:
        name, values = ENUMS[kind]
        properties[name] = {"enum": values.split()}
    schema = {"type": "object", "properties": properties, "required": required,
              "additionalProperties": False}
    if kind == "legacy_raw_ref":
        properties["raw_digest"] = {"type": "string", "format": "bdb-sha256"}
    if kind == "source_generation":
        schema["oneOf"] = [{"required": ["repository_authority_ref"], "not": {"required": ["snapshot_authority_ref"]}},
                           {"required": ["snapshot_authority_ref"], "not": {"required": ["repository_authority_ref"]}}]
    if kind == "source_identity":
        properties["authority_mode"] = {"enum": ["AUTHORIZED_GIT", "AUTHORIZED_SNAPSHOT"]}
        schema.update({"if": {"properties": {"authority_mode": {"const": "AUTHORIZED_GIT"}}},
                       "then": {"required": ["git_commit_object_id", "git_tree_object_id"]}})
    if kind == "trusted_predecessor_selection_decision":
        schema.update({"if": {"properties": {"decision": {"const": "SELECTED"}}},
                       "then": {"required": ["selected_legacy_ref"], "properties": {"candidate_legacy_refs": {"minItems": 1}}}})
    if kind == "bootstrap_admission_decision":
        schema.update({"if": {"properties": {"requested_role": {"const": "CANONICAL_PREDECESSOR"}}},
                       "then": {"required": ["trusted_predecessor_selection_ref"]}})
    return schema

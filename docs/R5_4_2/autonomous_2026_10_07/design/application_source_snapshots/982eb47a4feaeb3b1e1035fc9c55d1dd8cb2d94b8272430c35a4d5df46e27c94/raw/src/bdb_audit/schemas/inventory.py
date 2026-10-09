"""Executable field contracts for Surface and Inventory artifacts (M14)."""

FIELDS = {
    "surface_key": "source_identity_ref canonical_surface_category normalized_anchor_descriptor",
    "surface_record": "surface_key source_identity_ref surface_category anchor_descriptor provenance_refs identity_state",
    "input_disposition_record": "input_disposition_record_id assigned_input_ref disposition disposition_input_history_cut reason_codes",
    "scope_state_record": "scope_state_record_id scope_key state basis_refs scope_state_input_history_cut reason_codes",
    "inventory_revision": "inventory_id inventory_revision source_generation_ref collector_profile_refs assigned_input_refs input_disposition_refs surface_refs scope_state_record_refs manual_runtime_additions unresolved_scope_refs basis_history_cut",
    "surface_collector_record": "collection_run_id collector_profile_ref assigned_input_manifest_ref assigned_inputs terminal_input_dispositions emitted_surface_refs runtime_manual_additions parse_errors unsupported_capabilities resource_limit_events completion_status",
}

OPTIONAL = {
    "surface_record": ("surface_record_id",),
    "scope_state_record": ("scope_ref", "scope_decision_ref"),
}

ARRAYS = {
    "provenance_refs", "reason_codes", "basis_refs", "collector_profile_refs",
    "assigned_input_refs", "input_disposition_refs", "surface_refs",
    "scope_state_record_refs", "manual_runtime_additions", "unresolved_scope_refs",
    "assigned_inputs", "terminal_input_dispositions", "emitted_surface_refs",
    "runtime_manual_additions", "parse_errors", "unsupported_capabilities",
    "resource_limit_events",
}

OBJECTS = {
    "normalized_anchor_descriptor", "anchor_descriptor",
    "disposition_input_history_cut", "scope_state_input_history_cut",
    "basis_history_cut",
}


def inventory_schema(kind):
    if kind not in FIELDS:
        return None
    fields = FIELDS[kind].split()
    properties = {}
    for name in fields + list(OPTIONAL.get(kind, ())):
        if name in ARRAYS:
            properties[name] = {"type": "array"}
        elif name in OBJECTS:
            properties[name] = {"type": "object"}
        elif name.endswith("_ref") and name not in ("collector_profile_ref", "assigned_input_manifest_ref"):
            properties[name] = {
                "type": "object",
                "required": ["kind", "revision_digest", "digest_profile", "schema_revision_ref", "ref_class"],
            }
        else:
            properties[name] = {"type": ["string", "number", "object"]}

    if kind == "surface_record":
        properties["identity_state"] = {"enum": ["STABLE", "PROVISIONAL"]}
        properties["surface_key"] = {
            "type": "object",
            "required": ["kind", "revision_digest", "digest_profile", "schema_revision_ref", "ref_class"],
        }
        properties["source_identity_ref"] = {
            "type": "object",
            "required": ["kind", "revision_digest", "digest_profile", "schema_revision_ref", "ref_class"],
        }
    elif kind == "input_disposition_record":
        properties["disposition"] = {
            "enum": ["COLLECTED", "UNSUPPORTED", "EXCLUDED", "COLLECTION_FAILED", "PARSING_FAILED", "PROVISIONAL"]
        }
    elif kind == "scope_state_record":
        properties["state"] = {
            "enum": [
                "KNOWN_SURFACE", "KNOWN_UNOBSERVED_SCOPE", "UNSUPPORTED_SCOPE",
                "EXCLUDED_SCOPE", "COLLECTION_FAILED", "PARSING_FAILED",
                "PROVISIONAL_SCOPE", "UNKNOWN_SCOPE"
            ]
        }

    return {
        "type": "object",
        "required": fields,
        "properties": properties,
        "additionalProperties": False,
    }

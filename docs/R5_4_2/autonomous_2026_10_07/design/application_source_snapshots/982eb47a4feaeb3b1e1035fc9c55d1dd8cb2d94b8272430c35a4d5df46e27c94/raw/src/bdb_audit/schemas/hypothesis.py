"""Executable field contracts for Hypothesis artifacts (M18)."""

FIELDS = {
    "hypothesis_revision": "hypothesis_id hypothesis_revision source_generation_ref statement scope_refs invariant_refs obligation_refs planning_mode status input_history_cut",
}

OPTIONAL = {
    "hypothesis_revision": ("origin_discovery_ref",),
}

ARRAYS = {
    "scope_refs", "invariant_refs", "obligation_refs",
}

OBJECTS = {
    "input_history_cut",
}


def hypothesis_schema(kind):
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

    properties["status"] = {
        "enum": ["PROPOSED", "PREREGISTERED", "TESTING", "CONFIRMED", "REJECTED", "UNRESOLVED", "BLOCKED"]
    }
    properties["planning_mode"] = {
        "enum": ["PREREGISTERED", "EXPLORATORY", "LEGACY"]
    }

    return {
        "type": "object",
        "required": fields,
        "properties": properties,
        "additionalProperties": False,
    }

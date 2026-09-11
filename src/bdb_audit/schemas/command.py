"""Executable CommandEnvelope contract: Data Contracts 15.1."""


def command_schema():
    text = {"type": "string", "minLength": 1}
    head = {
        "type": "object", "additionalProperties": False,
        "required": ["tag", "campaign_id", "commit_seq", "commit_hash"],
        "properties": {"tag": {"const": "ACCEPTED_HEAD_REF"},
                       "campaign_id": text, "commit_seq": {"type": "integer", "minimum": 1},
                       "commit_hash": {"type": "string", "format": "bdb-sha256"}},
    }
    properties = {name: text for name in (
        "command_kind", "actor_ref", "governing_policy_ref", "idempotency_scope",
        "campaign_ref", "proposed_campaign_id", "history_namespace_ref", "bootstrap_profile_ref")}
    properties.update({
        "command_id": {"type": "string", "pattern": "^command_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"},
        "governing_spec_refs": {"type": "array", "minItems": 1, "uniqueItems": True, "items": text},
        "expected_parent_head": {"oneOf": [{"const": {"tag": "EMPTY_HISTORY"}}, head]},
        "command_payload": {"type": "object"},
        "command_payload_ref": {"type": "object", "required": ["kind", "revision_digest", "digest_profile", "schema_revision_ref", "ref_class"],
                                "properties": {"ref_class": {"const": "CONTENT_OBJECT"}}},
    })
    return {
        "type": "object", "additionalProperties": False, "properties": properties,
        "required": ["command_id", "command_kind", "actor_ref", "expected_parent_head",
                     "governing_policy_ref", "governing_spec_refs", "idempotency_scope"],
        "not": {"required": ["command_payload", "command_payload_ref"]},
        "if": {"properties": {"command_kind": {"const": "INITIALIZE_CAMPAIGN_FROM_LEGACY"}}, "required": ["command_kind"]},
        "then": {"required": ["proposed_campaign_id", "history_namespace_ref", "bootstrap_profile_ref"],
                 "properties": {"expected_parent_head": {"const": {"tag": "EMPTY_HISTORY"}},
                                "bootstrap_profile_ref": {"const": "INSTALLATION_BOOTSTRAP_PROFILE_V1"}},
                 "not": {"required": ["campaign_ref"]}},
        "else": {"required": ["campaign_ref"], "properties": {"expected_parent_head": head},
                 "not": {"anyOf": [{"required": [name]} for name in
                                    ("proposed_campaign_id", "history_namespace_ref", "bootstrap_profile_ref")]}},
    }

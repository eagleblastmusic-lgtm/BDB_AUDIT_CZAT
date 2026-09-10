from copy import deepcopy
import hashlib
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.registry import ContractRegistry, load_vectors, canonical_reference_set
from bdb_audit.schemas.binding import SchemaBindings, DIALECT, backend_identity

ROOT = Path(__file__).resolve().parents[2]
VECTORS = load_vectors(ROOT / "F1_QUALIFICATION/inputs/BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json")
BY_ID = {v["id"]: v for v in VECTORS["vectors"]}


def schema_fixture(kind="command_envelope"):
    """Substrate-only test schema, never installed in an accepted history."""
    row = ContractRegistry().contract(kind)
    return {"$schema": DIALECT, "$id": row["schema_ref"], "type": "object",
            "properties": {"value": {"type": "integer", "minimum": 1}},
            "required": ["value"], "additionalProperties": False,
            "x-bdb-material-refs": row["material_refs"]}


def bound(schema, kind="command_envelope"):
    raw = canonical_bytes(schema)
    return SchemaBindings([(kind, "1", raw, hashlib.sha256(raw).hexdigest())])


def test_exact_loader_and_unknown_kind_version(tmp_path):
    registry = ContractRegistry()
    assert registry.document["registry_version"] == 3
    assert len(VECTORS["vectors"]) == len(BY_ID)
    for kind, version in [("command", "1"), ("commit", "1"), ("command_envelope", "2"),
                          ("milestone_acceptance", "1")]:
        with pytest.raises(ValidationError, match="UNREGISTERED_CONTRACT_KIND"):
            registry.contract(kind, version)
    raw = (ROOT / "src/bdb_audit/core/artifact_contract_registry_r5_3.json").read_bytes()
    with pytest.raises(ValidationError, match="REGISTRY_PIN_MISMATCH"):
        ContractRegistry(raw + b" ")
    copy = tmp_path / "vectors.json"
    copy.write_bytes((ROOT / "F1_QUALIFICATION/inputs/BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json").read_bytes() + b" ")
    with pytest.raises(ValidationError, match="GOLDEN_VECTOR_PIN_MISMATCH"):
        load_vectors(copy)


@pytest.mark.parametrize("field,value,error", [
    ("ordering_rules", {"alternate_order": True}, "ORDERING_RULE_DEFECT"),
    ("reference_contract_mode", "SCHEMA_BOUND_BEFORE_FIRST_ACCEPTANCE", "EXPLICIT_COMPLETE"),
    ("material_refs", [], "EXPLICIT_COMPLETE"),
    ("canonical_role", "OTHER", "UNKNOWN_CANONICAL_ROLE"),
])
def test_contract_mutations(field, value, error):
    registry = ContractRegistry()
    doc = registry.document
    row = next(c for c in doc["contracts"] if c["kind"] == "command_envelope")
    row[field] = value
    with pytest.raises(ValidationError, match=error):
        registry.validate_definition(doc)


def test_ref_classes_and_top_level_semantics_cannot_be_overridden():
    registry = ContractRegistry()
    doc = registry.document
    doc["contracts"][0]["material_refs"][0]["ref_class"] = "CONTENT_INSTEAD_OF_HISTORY"
    with pytest.raises(ValidationError, match="UNREGISTERED_REFERENCE_CLASS"):
        registry.validate_definition(doc)
    doc = registry.document
    doc["reference_class_semantics"]["HISTORY_INPUT"] = "permit current commit"
    with pytest.raises(ValidationError, match="REGISTRY_SEMANTICS_MISMATCH"):
        registry.validate_definition(doc)
    doc = registry.document
    doc["contracts"].pop()
    with pytest.raises(ValidationError, match="REGISTRY_INCOMPLETE"):
        registry.validate_definition(doc)


@pytest.mark.parametrize("vector_id", [
    "R5N01_CRITICAL_REGISTRY_REF_COMPLETENESS", "R5N02_CANONICAL_ROLE_DOMAIN_REJECT",
    "R5N04_DANGLING_REF_TARGET_REJECT", "R5N25_EXPLICIT_COMPLETE_BODY_REGISTRY_PARITY",
    "R5N42_REFERENCE_ARRAY_DEFAULT_ORDERING", "R5N70_INVENTORY_INVARIANT_MATERIALITY_EXPLICIT",
])
def test_registry_concrete_golden(vector_id):
    vector = BY_ID[vector_id]
    data, expected = vector["input"], vector["expected"]
    registry = ContractRegistry()
    if "canonical_role" in data:
        with pytest.raises(ValidationError, match=expected["error"]):
            registry.role(data["canonical_role"])
    elif "allowed_target" in data:
        with pytest.raises(ValidationError, match=expected["error"]):
            registry.target(data["allowed_target"])
    elif "registry_field_missing" in data:
        assert data["registry_field_missing"] and data["contract_mode"] == "EXPLICIT_COMPLETE"
        refs = registry.contract("command_envelope")["material_refs"]
        assert any(r["field"] == data["body_ref_field"] for r in refs)
        refs = [r for r in refs if r["field"] != data["body_ref_field"]]
        with pytest.raises(ValidationError, match=expected["error"]):
            registry.reference_parity("command_envelope", refs)
    elif "refs" in data:
        assert data["local_ordering_override"] is None
        assert canonical_reference_set(data["refs"]) == expected["canonical_order"]
        with pytest.raises(ValidationError, match="DUPLICATE_REFERENCE"):
            canonical_reference_set(data["refs"] + data["refs"][:1])
        assert expected["duplicates"] == "REJECT"
    elif "kinds" in data:
        for kind in data["kinds"]:
            assert registry.contract(kind)["reference_contract_mode"] == data["required_mode"]
        registry.validate_definition(registry.document)
        assert expected == {"result": "ACCEPT"}
    else:
        row = registry.contract(data["kind"])
        assert row["reference_contract_mode"] == data["reference_contract_mode"]
        assert bool(row["material_refs"]) == data["material_refs_complete"]
        registry.reference_parity(data["kind"], row["material_refs"])
        assert expected == {"result": "ACCEPT"}


def test_r5n06_exact_missing_binding():
    data = BY_ID["R5N06_SCHEMA_BINDING_FAIL_CLOSED"]["input"]
    expected = BY_ID["R5N06_SCHEMA_BINDING_FAIL_CLOSED"]["expected"]
    assert data["exact_schema_digest"] is None
    assert data["registry_mode"] == "SCHEMA_BOUND_BEFORE_FIRST_ACCEPTANCE"
    # The vector's symbolic future kind is not added to the production Registry.
    with pytest.raises(ValidationError, match=expected["error"]):
        SchemaBindings().require_bound("BDB_SCHEMA_REGISTRY::" + data["kind"] + "/1")
    assert expected["result"] == "REJECT_RUNTIME_ACCEPTANCE"


def test_r5n77_implementation_exists_without_acceptance():
    vector = BY_ID["R5N77_SCHEMA_BINDING_BOUNDARY"]
    data = vector["input"]
    assert data["semantic_contract_frozen"] and data["implementation_started"]
    assert not data["executable_schema_bound"] and not data["first_runtime_acceptance_attempted"]
    substrate = SchemaBindings()
    assert substrate.identities == {}
    assert not hasattr(substrate, "accept")
    # A real validation boundary also rejects an EXPLICIT_COMPLETE object.
    with pytest.raises(ValidationError, match="SCHEMA_BYTES_NOT_BOUND"):
        substrate.validate_schema("command_envelope", b"{}")
    assert vector["expected"] == {"result": "IMPLEMENTATION_ALLOWED_ACCEPTANCE_FORBIDDEN"}


def test_bound_exact_bytes_no_rebinding_and_reference_parity():
    schema = schema_fixture()
    binding = bound(schema)
    assert binding.validate_schema("command_envelope", b'{"value":1}') == {"value": 1}
    raw = canonical_bytes(schema)
    digest = hashlib.sha256(raw).hexdigest()
    assert binding.require_bound(schema["$id"]) == (raw, digest)
    with pytest.raises(ValidationError, match="SCHEMA_REBIND_FORBIDDEN"):
        SchemaBindings([("command_envelope", "1", raw, digest)] * 2)
    with pytest.raises(ValidationError, match="SCHEMA_DIGEST_MISMATCH"):
        SchemaBindings([("command_envelope", "1", raw + b" ", digest)])
    schema["x-bdb-material-refs"] = []
    with pytest.raises(ValidationError, match="EXPLICIT_COMPLETE"):
        bound(schema)


@pytest.mark.parametrize("body", [{"value": 0}, {"value": True}, {}, {"value": 1, "extra": 1}])
def test_structural_failures_match_reference(body):
    schema = schema_fixture()
    assert not Draft202012Validator(schema).is_valid(body)
    with pytest.raises(ValidationError, match="SCHEMA_VALIDATION_FAILED"):
        bound(schema).validate_schema("command_envelope", canonical_bytes(body))


def test_duplicates_rejected_before_unbound_schema():
    with pytest.raises(ValidationError, match="CJSON_DUPLICATE_KEY"):
        SchemaBindings().validate_schema("command_envelope", b'{"a":1,"a":2}')


@pytest.mark.parametrize("patch,error", [
    ({"$schema": "https://json-schema.org/draft-07/schema"}, "DIALECT"),
    ({"$ref": "https://example.invalid/schema.json"}, "EXTERNAL_RESOLUTION"),
    ({"$ref": "file:///secret"}, "EXTERNAL_RESOLUTION"),
    ({"format": "unknown-format"}, "FORMAT_NOT_PINNED"),
    ({"$dynamicRef": "#other"}, "DYNAMIC_RESOLUTION"),
])
def test_offline_pinned_behavior(patch, error):
    schema = schema_fixture()
    schema.update(patch)
    with pytest.raises(ValidationError, match=error):
        bound(schema)


def test_local_resolution_and_missing_target_fail_closed():
    schema = schema_fixture()
    schema["$defs"] = {"positive": {"type": "integer", "minimum": 2}}
    schema["properties"]["value"] = {"$ref": "#/$defs/positive"}
    assert bound(schema).validate_schema("command_envelope", b'{"value":2}') == {"value": 2}
    schema["properties"]["value"] = {"$ref": "#/$defs/missing"}
    with pytest.raises(ValidationError, match="SCHEMA_RESOLUTION_FAILED"):
        bound(schema).validate_schema("command_envelope", b'{"value":2}')


def test_backend_identity_and_format_behavior():
    assert backend_identity()["packages"]["jsonschema"] == "4.25.1"
    for fmt, valid, invalid in [("uuid", "00000000-0000-4000-8000-000000000000", "00000000-0000-0000-0000-000000000000"),
                                ("date-time", "2026-09-10T12:00:00Z", "2026-02-30T12:00:00Z"),
                                ("bdb-sha256", "a" * 64, "A" * 64)]:
        schema = schema_fixture()
        schema["properties"]["value"] = {"type": "string", "format": fmt}
        binding = bound(schema)
        binding.validate_schema("command_envelope", canonical_bytes({"value": valid}))
        with pytest.raises(ValidationError, match="SCHEMA_VALIDATION_FAILED"):
            binding.validate_schema("command_envelope", canonical_bytes({"value": invalid}))


def test_typed_reference_set_identity_includes_schema():
    a = {"kind": "stage_run", "logical_id": "stage_run_a", "revision_digest": "a" * 64,
         "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "a" * 64}
    b = dict(a, schema_revision_ref="b" * 64)
    assert canonical_reference_set([b, a]) == [a, b]
    with pytest.raises(ValidationError, match="DUPLICATE_REFERENCE"):
        canonical_reference_set([a, a])

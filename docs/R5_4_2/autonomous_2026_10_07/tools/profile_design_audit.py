"""Independent draft grammar KATs and exact dependency-cycle diagnostics."""

from __future__ import annotations

import copy
import json
import re
from collections import deque

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from execution import BASE, OUT, digest, preserve, read, write


def catalog_source_parity(actual, expected):
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(name for name in set(actual) & set(expected) if actual[name] != expected[name])
    assert not (missing or extra or changed), ("GENERATED_PROFILE_CATALOG_DRIFT", missing, extra, changed)


def catalog_source_regressions(contracts):
    controls = []
    purpose_contracts = read(OUT / "design/PURPOSE_CONTRACT_GRAMMARS.json")
    assessor = purpose_contracts["ASSESSOR"]
    assessor_name = assessor.get("analysis_profile_key", assessor["algorithm_id"])
    expected_domains = assessor["output_domain_by_context"]
    assert contracts[assessor_name]["output_domain_by_context"] == expected_domains
    for label, domains in (
        ("OMITTED_ASSESSOR_CONTEXT", {key: value for key, value in expected_domains.items() if key != "materiality_assessment"}),
        ("ASSESSOR_UNION_DOMAIN_SUBSTITUTION", {key: assessor["output_domain"] for key in expected_domains}),
        ("CROSS_CONTEXT_NON_MATERIAL_LEAK", {**expected_domains, "clean_control_assessment": [*expected_domains["clean_control_assessment"], "NON_MATERIAL"]}),
    ):
        changed = {**contracts, assessor_name: {**contracts[assessor_name], "output_domain_by_context": domains}}
        try:
            catalog_source_parity(changed, contracts)
        except AssertionError as error:
            assert error.args[0][0] == "GENERATED_PROFILE_CATALOG_DRIFT"
        else:
            raise AssertionError(label)
        controls.append({"case": label, "result": "PASS", "expected_reject": "GENERATED_PROFILE_CATALOG_DRIFT"})
    for name, changed in (
        ("OMITTED_PROFILE", {key: value for key, value in contracts.items() if key != "SOURCE_ZIP_TRANSPORT_V1"}),
        ("UNDECLARED_PROFILE", {**contracts, "UNDECLARED_OVERLAY": contracts["SOURCE_ZIP_TRANSPORT_V1"]}),
    ):
        try:
            catalog_source_parity(changed, contracts)
        except AssertionError as error:
            assert error.args[0][0] == "GENERATED_PROFILE_CATALOG_DRIFT"
        else:
            raise AssertionError(name)
        controls.append({"case": name, "result": "PASS", "expected_reject": "GENERATED_PROFILE_CATALOG_DRIFT"})
    source = contracts["SOURCE_ZIP_TRANSPORT_V1"]
    for field in ("parser_code_ref", "parser_dependency_code_refs", "max_central_bytes", "max_ratio"):
        stale = {**source, "grammar": {**source["grammar"],
                 "properties": {key: value for key, value in source["grammar"]["properties"].items() if key != field},
                 "required": [key for key in source["grammar"]["required"] if key != field]}}
        try:
            catalog_source_parity({**contracts, "SOURCE_ZIP_TRANSPORT_V1": stale}, contracts)
        except AssertionError as error:
            assert error.args[0][-1] == ["SOURCE_ZIP_TRANSPORT_V1"]
        else:
            raise AssertionError(field)
        controls.append({"case": "STALE_TRANSPORT_" + field, "result": "PASS", "expected_reject": "GENERATED_PROFILE_CATALOG_DRIFT"})
    return controls


def wire_identities(contracts):
    """Metadata cannot silently alias a grammar to an unrelated wire profile."""
    identities = {}
    for name, contract in contracts.items():
        literal = contract["grammar"]["properties"]["profile_id"].get("const")
        declared = contract.get("wire_profile_id", name)
        assert literal is not None and literal == declared, ("PROFILE_WIRE_IDENTITY_MISMATCH", name, declared, literal)
        assert declared not in identities.values(), ("DUPLICATE_PROFILE_WIRE_IDENTITY", name, declared)
        identities[name] = declared
    return identities


def wire_regressions(contracts):
    identities = wire_identities(contracts)
    expected = {"TOOL_CAPTURE_V2": "TOOL_CAPTURE_V3", "SOURCE_IDENTITY_V2": "SOURCE_IDENTITY_V3",
                "METHOD_QUALIFICATION_V1": "METHOD_QUALIFICATION_V2", "OBSERVED_EFFORT_V1": "OBSERVED_EFFORT_V2",
                "PRINCIPAL_AUTHORIZATION_V1": "PRINCIPAL_AUTHORIZATION_V2",
                "NF02_PACKAGE_TRANSPORT_V2": "NF02_INPUT_PACKAGE_TRANSPORT_V2",
                "NF02_EXTERNAL_LANE_SLOT_V2": "NF02_EXTERNAL_LANE_SLOT_V3",
                "NF02_PROTOCOL_PROFILE_V2": "NF02_PROTOCOL_PROFILE_V3"}
    expected["INSTALLATION_FULL_PATH_PROFILE_V1"] = "INSTALLATION_FULL_PATH_PROFILE_V2"
    expected["BUILD_PROVENANCE_RECEIPT_V1"] = "BUILD_PROVENANCE_RECEIPT_V2"
    expected["FULL_PATH_CONTEXT_PARAMETERS_V1"] = "FULL_PATH_CONTEXT_PARAMETERS_V2"
    expected["LANE_COMPLETION_V1"] = "LANE_COMPLETION_V2"
    assert {n: w for n, w in identities.items() if n != w} == expected
    controls = [{"case": "EXACT_DECLARED_SUCCESSOR_WIRE_SET", "result": "PASS"}]

    def rejected(case, changed, reason):
        try:
            wire_identities(changed)
        except AssertionError as error:
            assert error.args[0][0] == reason, (case, error)
        else:
            raise AssertionError(case)
        controls.append({"case": case, "result": "PASS", "expected_reject": reason})

    leaked = {**contracts, "SOURCE_AUTHORITY_V1": {**contracts["SOURCE_AUTHORITY_V1"], "wire_profile_id": "EXACT_DURABLE_RECOVERY_V1"}}
    rejected("RECOVERY_ID_LEAK_IN_NONPURPOSE_PROFILE", leaked, "PROFILE_WIRE_IDENTITY_MISMATCH")
    missing = dict(contracts["METHOD_QUALIFICATION_V1"])
    missing.pop("wire_profile_id")
    rejected("IMPLICIT_SUCCESSOR_ALIAS", {**contracts, "METHOD_QUALIFICATION_V1": missing}, "PROFILE_WIRE_IDENTITY_MISMATCH")
    source = contracts["SOURCE_AUTHORITY_V1"]
    duplicate = {**source, "wire_profile_id": identities["BOOTSTRAP_NAMESPACE_V2"],
                 "grammar": {**source["grammar"], "properties": {**source["grammar"]["properties"], "profile_id": {"const": identities["BOOTSTRAP_NAMESPACE_V2"]}}}}
    rejected("DUPLICATE_ID_WITH_MATCHING_GRAMMAR", {**contracts, "SOURCE_AUTHORITY_V1": duplicate}, "DUPLICATE_PROFILE_WIRE_IDENTITY")
    return identities, controls


def fixture(schema, defs, ordinal=0, external=None):
    if "$ref" in schema:
        name = schema["$ref"].removeprefix("#/$defs/")
        if name not in defs:
            if external is not None and name in external:
                selected = external[name]
                return fixture(selected, selected.get("$defs", {}), ordinal, external)
            # Report bodies select exact canonical schemas externally; they are
            # not guessed by this transport-grammar fixture generator.
            raise ValueError("EXTERNAL_BODY_REQUIRES_EXACT_BOUND_FIXTURE: " + name)
        return fixture(defs[name], defs, ordinal, external)
    if "const" in schema:
        return copy.deepcopy(schema["const"])
    if "enum" in schema:
        return copy.deepcopy(schema["enum"][ordinal % len(schema["enum"])])
    for keyword in ("oneOf", "anyOf"):
        if keyword in schema and schema.get("type") != "object":
            return fixture(schema[keyword][0], defs, ordinal, external)
    if "allOf" in schema and schema.get("type") != "object":
        value = fixture(schema["allOf"][0], defs, ordinal, external)
        for constraint in schema["allOf"][1:]:
            for key, rule in constraint.get("properties", {}).items():
                value[key] = fixture(rule, defs, ordinal, external)
        return value
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next(k for k in kind if k != "null")
    if kind == "object":
        value = {key: fixture(schema["properties"][key], defs, ordinal, external) for key in schema.get("required", [])}
        if "kind" in value and "logical_id" in value:
            value["logical_id"] = value["kind"] + "_00000000-0000-4000-8000-000000000001"
        return value
    if kind == "array":
        count = max(schema.get("minItems", 0), schema.get("minContains", 1) if "contains" in schema else 0)
        values = [fixture(schema["items"], defs, ordinal + i, external) for i in range(count)]
        if "contains" in schema:
            for i in range(schema.get("minContains", 1)):
                values[i] = fixture(schema["contains"], defs, ordinal + i, external)
        return values
    if kind == "integer":
        return schema.get("minimum", 0)
    if kind == "boolean":
        return True
    if kind == "null":
        return None
    if kind == "string":
        pattern = schema.get("pattern", "")
        if "64}" in pattern:
            return format(ordinal + 1, "064x")
        if "history_namespace_" in pattern:
            return "history_namespace_00000000-0000-4000-8000-000000000001"
        if "[0-9a-f]{8}" in pattern:
            prefix = re.match(r"\^([a-z_]+)_", pattern)
            return (prefix[1] if prefix else "test") + "_00000000-0000-4000-8000-000000000001"
        if "BDB_SCHEMA_REGISTRY" in pattern:
            return "BDB_SCHEMA_REGISTRY::source_manifest/1"
        if "~0" in pattern or "~1" in pattern or "~[01]" in pattern:
            return ""
        if "(?:/" in pattern or "A-Za-z0-9" in pattern:
            return "src/main.py" if "/" in pattern else "TEST_" + str(ordinal)
        return "TEST_" + str(ordinal)
    raise ValueError(schema)


def main():
    preserve()
    contracts = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
    from profile_contracts import resolved_catalog
    mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
    expected = resolved_catalog(sorted("BDB_SCHEMA_REGISTRY::" + key for key in mapping.values()))
    catalog_source_parity(contracts, expected)
    catalog_controls = catalog_source_regressions(expected)
    wire_map, wire_controls = wire_regressions(contracts)
    # Explicit draft catalog only. It is intentionally not a SchemaRegistry
    # installation and cannot be used by runtime or as qualification evidence.
    external = {}
    resources = []
    for old, active in read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"].items():
        path = OUT / "design/body_grammars" / (active.replace("/", "__") + ".json")
        if not path.exists():
            path = BASE / "candidate/schemas" / (old.replace("/", "__") + ".schema.json")
        schema = read(path)
        key = "BDB_SCHEMA_REGISTRY::" + active
        external[key] = schema
        resource = Resource.from_contents(schema)
        resources.append((key, resource))
        resources.append((schema["$id"], resource))
    registry = Registry().with_resources(resources)
    reverse = {name: [] for name in contracts}
    degree = {}
    for name, contract in contracts.items():
        assert set(contract["dependencies"]) <= set(contracts), name
        degree[name] = len(contract["dependencies"])
        for dependency in contract["dependencies"]:
            reverse[dependency].append(name)
    queue = deque(sorted(name for name, count in degree.items() if count == 0))
    order = []
    while queue:
        name = queue.popleft()
        order.append(name)
        for parent in sorted(reverse[name]):
            degree[parent] -= 1
            if degree[parent] == 0:
                queue.append(parent)
    cyclic = sorted(name for name, count in degree.items() if count)
    vectors = []
    fixture_pending = []
    for name, contract in contracts.items():
        schema = contract["grammar"]
        valid = fixture(schema, schema.get("$defs", {}))
        validator = Draft202012Validator(schema)
        errors = [error.message for error in validator.iter_errors(valid)]
        assert not errors, (name, errors)
        vectors.append({"profile": name, "case": "EXACT_DRAFT_PROFILE_GRAMMAR", "grammar_result": "ACCEPT", "canonical_runtime": "NOT_RUN"})
        mutations = [("CALLER_TRUST_FLAG", {**valid, "trusted": True})]
        if "profile_id" in valid:
            mutations.append(("WRONG_WIRE_PROFILE_ID", {**valid, "profile_id": "UNQUALIFIED_RUNTIME_OVERLAY"}))
        elif "algorithm_id" in valid:
            mutations.append(("WRONG_PURPOSE_ALGORITHM", {**valid, "algorithm_id": "UNQUALIFIED_RUNTIME_OVERLAY"}))
        for field in schema["required"]:
            missing = copy.deepcopy(valid)
            del missing[field]
            mutations.append(("MISSING_REQUIRED_" + field, missing))
        for case, mutation in mutations:
            assert not validator.is_valid(mutation), (name, case)
            vectors.append({"profile": name, "case": case, "grammar_result": "REJECT", "canonical_runtime": "NOT_RUN"})
        if "payload_grammar" in contract:
            try:
                payload = fixture(contract["payload_grammar"], contract["payload_grammar"].get("$defs", {}), external=external)
            except ValueError as exc:
                fixture_pending.append({"profile": name, "reason": str(exc), "status": "OPEN"})
            else:
                payload_validator = Draft202012Validator(contract["payload_grammar"], registry=registry)
                errors = [error.message for error in payload_validator.iter_errors(payload)]
                assert not errors, (name, errors)
                assert not payload_validator.is_valid({**payload, "trusted": True}), name
                vectors.append({"profile": name, "case": "RAW_PAYLOAD_EXTRA_AUTHORITY_FIELD", "grammar_result": "REJECT", "canonical_runtime": "NOT_RUN"})
                if name == "EXECUTION_COMMAND_JSON_V1":
                    for label, path, expected in (
                        ("EXACT_ROOT", "", True), ("HIDDEN_SOURCE_DIRECTORY", ".github", True),
                        ("UNICODE_SOURCE_DIRECTORY", "src/żółć", True),
                        ("TRAVERSAL", "../src", False), ("DOT_ALIAS", "src/./nested", False),
                        ("BACKSLASH", "src\\nested", False), ("NUL", "src/\0nested", False),
                    ):
                        changed = copy.deepcopy(payload)
                        changed["working_directory"]["directory_path"] = path
                        assert payload_validator.is_valid(changed) == expected, (name, label)
                        vectors.append({"profile": name, "case": "WORKING_DIRECTORY_" + label,
                                        "input": changed, "grammar_result": "ACCEPT" if expected else "REJECT",
                                        "canonical_runtime": "NOT_RUN"})
                    changed = copy.deepcopy(payload)
                    changed["working_directory"]["source_manifest_ref"]["kind"] = "approval_decision"
                    assert not payload_validator.is_valid(changed), name
                    vectors.append({"profile": name, "case": "WORKING_DIRECTORY_WRONG_MANIFEST_KIND",
                                    "input": changed, "grammar_result": "REJECT", "canonical_runtime": "NOT_RUN"})
                if name == "FINAL_TECHNICAL_REPORT_JSON_V1":
                    changed = copy.deepcopy(payload)
                    changed["machine_objects"][0]["body"]["trusted"] = True
                    assert not payload_validator.is_valid(changed), name
                    vectors.append({"profile": name, "case": "REPORT_CANONICAL_BODY_EXTRA_AUTHORITY_FIELD", "grammar_result": "REJECT", "canonical_runtime": "NOT_RUN"})
                    missing_registry = Registry()
                    try:
                        list(Draft202012Validator(contract["payload_grammar"], registry=missing_registry).iter_errors(payload))
                    except Exception as exc:
                        # Unresolvable exact schema references are an error,
                        # not permission to fall back to a looser body grammar.
                        from referencing.exceptions import Unresolvable
                        if not isinstance(exc, Unresolvable) and not isinstance(exc.__cause__, Unresolvable):
                            raise
                    else:
                        raise AssertionError("Missing draft offline dependency did not fail closed")
                    vectors.append({"profile": name, "case": "REPORT_MISSING_OFFLINE_SCHEMA", "grammar_result": "REJECT", "canonical_runtime": "NOT_RUN"})
    write("design/PROFILE_DESIGN_AUDIT.json", {
        "catalog_raw_digest": digest(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json"),
        "generator_source_parity": "PASS", "catalog_source_controls": catalog_controls,
        "wire_identities": wire_map, "wire_identity_controls": wire_controls,
        "profile_count": len(contracts), "dependency_topological_order": order, "cyclic_profiles": cyclic,
        "vectors": vectors, "fixture_pending": fixture_pending,
        "cross_object_semantic_review": "NOT_COMPLETED", "canonical_runtime": "NOT_RUN", "fixed_point_reached": False,
        "fixture_schema_context": "FINITE_EXPLICIT_DRAFT_CATALOG_ONLY_NOT_QUALIFIED_SCHEMAS",
        "scope": "Draft grammar and declared profile dependency graph only, not accepted instance DAG, qualification, authority or atomicity",
    })
    assert not cyclic, cyclic
    print(json.dumps({"profiles": len(contracts), "declared_profile_dependency_cycles": len(cyclic), "grammar_vectors_passed": len(vectors), "draft_fixture_pending": len(fixture_pending), "qualified_fixture_execution": "NOT_RUN", "fixed_point_reached": False}))


if __name__ == "__main__":
    main()

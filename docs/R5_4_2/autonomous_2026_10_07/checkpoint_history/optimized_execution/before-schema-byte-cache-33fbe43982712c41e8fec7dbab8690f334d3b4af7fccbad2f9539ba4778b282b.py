"""Materialize exact build-time schema inputs, without freezing or installation.

Data 192.D.3 distinguishes candidate production from qualified schema authority.
Every unresolved semantic obligation remains explicit in the external report.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from execution import BASE, OUT, ROOT, canonical, digest, preserve, read, write


DEST = OUT / "build_time_candidate"


def references(value):
    if isinstance(value, dict):
        if "$ref" in value:
            yield value["$ref"]
        for child in value.values():
            yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


INHERITED_TRANSPORT_SCHEMAS = ("NF02_INPUT_PACKAGE_TRANSPORT_V2", "NF02_RESULT_TRANSPORT_V2")


def inherited_transport_files():
    result = {}
    for name in INHERITED_TRANSPORT_SCHEMAS:
        path = BASE / "candidate/schemas" / (name + ".schema.json")
        schema = read(path)
        if schema.get("$id") != "BDB_PROFILE_SCHEMA::" + name:
            raise ValueError("INHERITED_TRANSPORT_SCHEMA_IDENTITY")
        # Preserve whole executable bytes, including their original identity.
        # This builder serializes canonical files; never normalize inherited raw.
        if path.read_bytes() != canonical(schema) + b"\n":
            raise ValueError("INHERITED_TRANSPORT_RAW_SERIALIZATION_DRIFT")
        result["payload_schemas/" + name + ".schema.json"] = schema
    return result


def selected_schema_ids(schema, known_ids):
    canonical_keys = {schema_id.split("::", 1)[1]: schema_id for schema_id in known_ids
                      if schema_id.startswith("BDB_SCHEMA_REGISTRY::")}
    result = set()
    for field in ("schema_key", "result_schema_key"):
        selection = schema.get("properties", {}).get(field, {}).get("const")
        if selection is None:
            continue
        # The source profile declares a canonical kind/version key; transport
        # and slot profiles declare a full schema ID. Both resolve exactly.
        target = selection if selection in known_ids else canonical_keys.get(selection)
        if target is None:
            raise ValueError("UNBOUND_PROFILE_PAYLOAD_SCHEMA: " + field + " -> " + selection)
        result.add(target)
    return result


def verify_profile_schema_keys(files, profiles):
    ids = {schema["$id"] for schema in files.values()}
    for contract in profiles.values():
        selected_schema_ids(contract["grammar"], ids)


def compile_files():
    frontier = read(OUT / "design/BODY_GRAMMAR_FRONTIER.json")
    if frontier["pending"]:
        raise ValueError("UNRESOLVED_BODY_GRAMMAR")
    mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
    if len(mapping) != len(set(mapping.values())):
        raise ValueError("DUPLICATE_SUCCESSOR_KEY")
    files = {}
    inherited = {item["design_key"] for item in frontier["compiled"]
                 if item["mode"] == "EXACT_INHERITED_BYTES_PENDING_PARITY"}
    for source_key, target_key in sorted(mapping.items()):
        path = OUT / "design/body_grammars" / (target_key.replace("/", "__") + ".json")
        if target_key in inherited:
            if target_key != source_key:
                raise ValueError("INHERITED_SUCCESSOR_VERSION_MISMATCH")
            path = BASE / "candidate/schemas" / (source_key.replace("/", "__") + ".schema.json")
        schema = copy.deepcopy(read(path))
        expected_id = ("BDB_SCHEMA_REGISTRY::" if target_key in inherited else "BDB_DESIGN_SCHEMA::") + target_key
        if schema["$id"] != expected_id:
            raise ValueError("BODY_SCHEMA_IDENTITY_MISMATCH: " + source_key)
        schema["$id"] = "BDB_SCHEMA_REGISTRY::" + target_key
        if target_key == "artifact_contract_registry/1":
            registry_input = read(OUT / "REGISTRY_BUILD_CANDIDATE_READBACK.json")
            registry_path = OUT / registry_input["file"]
            if registry_input["pending_fields"] or digest(registry_path) != registry_input["raw_digest"]:
                raise ValueError("REGISTRY_BUILD_INPUT_NOT_READY_OR_DRIFTED")
            schema["const"] = read(registry_path)
            schema["x-bdb-normative-source"] = {
                "predecessor": "Data 192.D.3", "successor_registry_build_raw_digest": registry_input["raw_digest"],
                "status": "BUILD_TIME_NOT_FROZEN_NOT_QUALIFIED"}
        files["schemas/" + target_key.replace("/", "__") + ".schema.json"] = schema
    profiles = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
    for name, contract in sorted(profiles.items()):
        wire = contract.get("wire_profile_id", name)
        for field, directory, prefix in (("grammar", "profile_schemas", "BDB_EXTERNAL_PROFILE_SCHEMA::"),
                                         ("payload_grammar", "payload_schemas", "BDB_RAW_PAYLOAD_SCHEMA::")):
            if field in contract:
                schema = copy.deepcopy(contract[field])
                schema["$id"] = prefix + wire
                files[directory + "/" + wire + ".schema.json"] = schema
    files.update(inherited_transport_files())
    verify_profile_schema_keys(files, profiles)
    catalog = {schema["$id"]: schema for schema in files.values()}
    if len(catalog) != len(files):
        raise ValueError("DUPLICATE_EXECUTABLE_SCHEMA_ID")
    validated_definitions = set()
    for name, schema in files.items():
        # Meta-schema validation of each independent keyword remains complete.
        # Identical embedded definitions are checked once by exact CJSON bytes,
        # while every own root and every local/external reference is checked.
        definitions = schema.get("$defs", {})
        definitions_digest = hashlib.sha256(canonical(definitions)).hexdigest()
        if definitions_digest not in validated_definitions:
            Draft202012Validator.check_schema({"$defs": definitions})
            validated_definitions.add(definitions_digest)
        Draft202012Validator.check_schema({key: value for key, value in schema.items() if key != "$defs"})
        for reference in references(schema):
            if reference.startswith("#/"):
                cursor = schema
                for token in reference[2:].split("/"):
                    cursor = cursor[token.replace("~1", "/").replace("~0", "~")]
            elif reference not in catalog:
                raise ValueError("UNBOUND_OFFLINE_SCHEMA_DEPENDENCY: " + name + " -> " + reference)
    return files


def descriptors(files):
    by_id = {schema["$id"]: name for name, schema in files.items()}
    # Enumerate exact schema edges once per invocation. Repeated transitive
    # traversal must not repeatedly scan identical 100KB definition catalogs.
    edges = {schema_id: sorted({ref for ref in references(files[name]) if not ref.startswith("#/")}
                              | selected_schema_ids(files[name], set(by_id)))
             for schema_id, name in by_id.items()}
    result = []
    for name, schema in sorted(files.items()):
        raw = canonical(schema) + b"\n"
        pending = list(edges[schema["$id"]])
        closure = set()
        while pending:
            reference = pending.pop()
            if reference in closure:
                continue
            if reference not in by_id:
                raise ValueError("UNBOUND_OFFLINE_SCHEMA_DEPENDENCY: " + reference)
            closure.add(reference)
            pending.extend(edges[reference])
        result.append({"file": name, "raw_digest": hashlib.sha256(raw).hexdigest(),
                       "byte_length": len(raw), "media_type": "application/schema+json",
                       "$id": schema["$id"], "dialect": schema["$schema"],
                       "dependency_closure": [{"$id": reference, "file": by_id[reference],
                           "raw_digest": hashlib.sha256(canonical(files[by_id[reference]]) + b"\n").hexdigest()}
                           for reference in sorted(closure)]})
    return result


def verify_readback(directory: Path, entries):
    expected = {entry["file"] for entry in entries}
    if len(expected) != len(entries):
        raise ValueError("DUPLICATE_BUILD_CANDIDATE_ENTRY")
    actual = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
    if actual != expected:
        raise ValueError("BUILD_CANDIDATE_INVENTORY_DRIFT")
    root = directory.resolve()
    for entry in entries:
        path = directory / entry["file"]
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError("BUILD_CANDIDATE_PATH_ESCAPE")
        if path.stat().st_size != entry["byte_length"] or digest(path) != entry["raw_digest"]:
            raise ValueError("BUILD_CANDIDATE_RAW_DRIFT: " + entry["file"])
        schema = read(path)
        if schema.get("$id") != entry["$id"] or schema.get("$schema") != entry["dialect"]:
            raise ValueError("BUILD_CANDIDATE_SCHEMA_IDENTITY_DRIFT")
    return len(entries)


def source_paths():
    source_inputs = [OUT / "design/VERSION_IMPACT_PLAN.json", OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json",
                     ROOT / "docs/R5_4_2/OWNER_DELEGATED_DECISION_REGISTER.md", Path(__file__),
                     OUT / "design/BODY_GRAMMAR_FRONTIER.json", OUT / "REGISTRY_BUILD_CANDIDATE_READBACK.json",
                     OUT / "tools/execution.py",
                     OUT / read(OUT / "REGISTRY_BUILD_CANDIDATE_READBACK.json")["file"]]
    source_inputs.extend(sorted((OUT / "design/body_grammars").glob("*.json")))
    source_inputs.extend(BASE / "candidate/schemas" / (name + ".schema.json") for name in INHERITED_TRANSPORT_SCHEMAS)
    inherited = [item["design_key"] for item in read(OUT / "design/BODY_GRAMMAR_FRONTIER.json")["compiled"]
                 if item["mode"] == "EXACT_INHERITED_BYTES_PENDING_PARITY"]
    source_inputs.extend(BASE / "candidate/schemas" / (key.replace("/", "__") + ".schema.json") for key in inherited)
    return source_inputs


def main():
    preserve()
    before = {path.relative_to(ROOT).as_posix(): digest(path) for path in source_paths()}
    files = compile_files()
    entries = descriptors(files)
    # An existing draft is immutable unless it is byte-identical. A later model
    # change must produce a separately retained build, never overwrite evidence.
    build_digest = hashlib.sha256(canonical(entries)).hexdigest()
    directory = DEST / build_digest
    for name, schema in sorted(files.items()):
        path = directory / name
        raw = canonical(schema) + b"\n"
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("EXISTING_BUILD_CANDIDATE_DRIFT: " + name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(raw)
    verified = verify_readback(directory, entries)
    preserve()
    after = {path.relative_to(ROOT).as_posix(): digest(path) for path in source_paths()}
    if before != after:
        raise ValueError("BUILD_CANDIDATE_INPUT_DRIFT_DURING_EXECUTION")
    queue = read(OUT / "design/SEMANTIC_OBLIGATION_QUEUE.json")
    inherited = [item["design_key"] for item in read(OUT / "design/BODY_GRAMMAR_FRONTIER.json")["compiled"]
                 if item["mode"] == "EXACT_INHERITED_BYTES_PENDING_PARITY"]
    write("BUILD_TIME_CANDIDATE_READBACK.json", {
        "status": "BUILD_TIME_INPUTS_MATERIALIZED_AND_READ_BACK_NOT_FROZEN",
        "build_digest": build_digest, "directory": directory.relative_to(ROOT).as_posix(),
        "source_inputs": [{"file": name, "raw_digest": raw_digest} for name, raw_digest in before.items()],
        "input_drift": [],
        "entries": entries, "verified_files": verified, "mismatch_count": 0,
        "canonical_body_schemas": sum(name.startswith("schemas/") for name in files),
        "profile_schemas": sum(name.startswith("profile_schemas/") for name in files),
        "payload_schemas": sum(name.startswith("payload_schemas/") for name in files),
        "semantic_pending_nodes": queue["pending_nodes"], "full_successor_candidate_materialized": False,
        "inherited_schema_parity_pending": inherited,
        "registry_frozen": False, "schemas_frozen": False, "qualification": False,
        "Q1": "NOT_STARTED", "Q2": "NOT_STARTED", "NF02": "OPEN",
        "next": "Complete normative/Registry and per-kind predicate parity, execute required fixtures, freeze exact inputs, construct SchemaRegistry and prepare fresh Q1. These files supply no installed authority."})
    print(json.dumps({"materialized_and_read_back": verified, "build_digest": build_digest,
                      "qualification": False, "semantic_pending_nodes": len(queue["pending_nodes"])}))


if __name__ == "__main__":
    main()

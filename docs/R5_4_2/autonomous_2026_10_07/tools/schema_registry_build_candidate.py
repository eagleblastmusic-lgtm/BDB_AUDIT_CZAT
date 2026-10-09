"""Construct a raw-backed SchemaRegistry build input, without installation."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from build_time_candidates import verify_readback
from execution import BASE, OUT, ROOT, canonical, digest, preserve, read, write

sys.path.insert(0, str(ROOT / "src"))
from bdb_audit.core.hashing import _domain_digest  # noqa: E402


def constant_profile(contract, supplied=None):
    schema = contract["grammar"]
    supplied = supplied or {}
    body = {}
    for name, definition in schema["properties"].items():
        if "const" in definition:
            if name in supplied and supplied[name] != definition["const"]:
                raise ValueError("PROFILE_CONSTANT_PARAMETER_CONFLICT: " + name)
            body[name] = copy.deepcopy(definition["const"])
        elif name in supplied:
            body[name] = copy.deepcopy(supplied[name])
        else:
            raise ValueError("UNSUPPLIED_PROFILE_PARAMETER: " + name)
    if set(supplied) - set(body):
        raise ValueError("UNDECLARED_PROFILE_PARAMETER")
    Draft202012Validator(schema).validate(body)
    return body


def profile_ref(body):
    return {"profile_id": body["profile_id"], "revision_digest": hashlib.sha256(canonical(body) + b"\n").hexdigest()}


def candidate_object(kind, version, body, schema_raw_digest, logical_id=None):
    # Same unchanged mathematical ObjectDigest preimage as ADR006. This is
    # build identity only, never acceptance or producer authorization.
    if (kind, version) not in (("artifact_contract_registry", "1"), ("schema_registry", "2")):
        raise ValueError("UNDECLARED_BUILD_ROOT_KIND")
    object_digest = _domain_digest(kind, version, body, registry_kind=kind)
    reference = {"kind": kind, "revision_digest": object_digest,
                 "schema_revision_ref": {"kind": "schema", "revision_digest": schema_raw_digest},
                 "digest_profile": "BDB-OBJECT-DIGEST-1"}
    if logical_id is not None:
        reference["logical_id"] = logical_id
    return {"kind": kind, "version": version, "body": body, "ref": reference}


def construct():
    report = read(OUT / "BUILD_TIME_CANDIDATE_READBACK.json")
    for source in report["source_inputs"]:
        if digest(ROOT / source["file"]) != source["raw_digest"]:
            raise ValueError("STALE_BUILD_CANDIDATE_INPUT: " + source["file"])
    directory = ROOT / report["directory"]
    verify_readback(directory, report["entries"])
    by_id = {entry["$id"]: entry for entry in report["entries"]}
    contracts = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
    normalizer = constant_profile(contracts["BDB_CJSON_1"])
    compatibility = constant_profile(contracts["EXACT_COMPATIBILITY_V2"])
    validator = constant_profile(contracts["QUALIFIED_VALIDATOR_V2"], {"canonical_profile_ref": profile_ref(normalizer)})
    for package, expected in validator["backend"].items():
        if importlib.metadata.version(package) != expected:
            raise ValueError("VALIDATOR_BACKEND_VERSION_DRIFT: " + package)
    raw_path = BASE / "candidate" / contracts["BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1"]["inherited_exact_file"]
    raw_contract = read(raw_path)
    if canonical(raw_contract) + b"\n" != raw_path.read_bytes():
        raise ValueError("INHERITED_RAW_PROFILE_BYTE_PARITY")
    registry_input = read(OUT / "REGISTRY_BUILD_CANDIDATE_READBACK.json")
    registry = read(OUT / registry_input["file"])
    if digest(OUT / registry_input["file"]) != registry_input["raw_digest"]:
        raise ValueError("REGISTRY_BUILD_RAW_DRIFT")
    ar_schema = by_id["BDB_SCHEMA_REGISTRY::artifact_contract_registry/1"]
    schema = read(directory / ar_schema["file"])
    Draft202012Validator(schema).validate(registry)
    artifact_registry = candidate_object("artifact_contract_registry", "1", registry, ar_schema["raw_digest"])
    bindings = []
    for row in registry["contracts"]:
        entry = by_id[row["schema_ref"]]
        bindings.append({"schema_key": row["schema_ref"], "status": "ACTIVE", "schema_raw_ref": {
            "raw_digest": entry["raw_digest"], "byte_length": entry["byte_length"], "media_type": entry["media_type"],
            "artifact_contract_ref": profile_ref(raw_contract)}})
    bindings.sort(key=lambda binding: binding["schema_key"].encode("utf-8"))
    if len(bindings) != len({binding["schema_key"] for binding in bindings}):
        raise ValueError("DUPLICATE_SCHEMA_BINDING")
    identifier = "schema_registry_00000000-0000-4000-8000-000000000002"
    body = {"schema_registry_id": identifier, "artifact_contract_registry_ref": artifact_registry["ref"],
            "serialization_profile_ref": profile_ref(normalizer), "validator_profile_ref": profile_ref(validator),
            "compatibility_rules_ref": profile_ref(compatibility), "bindings": bindings}
    sr_schema = by_id["BDB_SCHEMA_REGISTRY::schema_registry/2"]
    # External retained executable root is selected before evaluating the body;
    # its availability does not claim that an installation authorized that pin.
    external_root = read(directory / sr_schema["file"])
    Draft202012Validator(external_root).validate(body)
    schema_registry = candidate_object("schema_registry", "2", body, sr_schema["raw_digest"], identifier)
    future_digest = schema_registry["ref"]["revision_digest"].encode("ascii")
    for entry in report["entries"]:
        if future_digest in (directory / entry["file"]).read_bytes():
            raise ValueError("SCHEMA_CONTAINS_FUTURE_OWNING_REGISTRY_DIGEST")
    files = {"objects/artifact_contract_registry__1.json": artifact_registry,
             "objects/schema_registry__2.json": schema_registry,
             "profiles/BDB_CJSON_1.json": normalizer, "profiles/EXACT_COMPATIBILITY_V2.json": compatibility,
             "profiles/QUALIFIED_VALIDATOR_V2.json": validator,
             "profiles/BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1.json": raw_contract}
    return files, sr_schema, report


def main():
    preserve()
    sources = [OUT / "BUILD_TIME_CANDIDATE_READBACK.json", OUT / "REGISTRY_BUILD_CANDIDATE_READBACK.json",
               OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json", OUT / "tools/build_time_candidates.py",
               OUT / "tools/execution.py", Path(__file__), ROOT / "src/bdb_audit/core/hashing.py",
               ROOT / "src/bdb_audit/core/canonical_json.py", ROOT / "src/bdb_audit/core/errors.py"]
    before = {path.relative_to(ROOT).as_posix(): digest(path) for path in sources}
    files, root_schema, report = construct()
    entries = [{"file": name, "raw_digest": hashlib.sha256(canonical(body) + b"\n").hexdigest(),
                "byte_length": len(canonical(body) + b"\n")} for name, body in sorted(files.items())]
    build_digest = hashlib.sha256(canonical(entries)).hexdigest()
    directory = OUT / "schema_registry_build_candidate" / build_digest
    for name, body in files.items():
        path = directory / name
        raw = canonical(body) + b"\n"
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("EXISTING_SCHEMA_REGISTRY_BUILD_DRIFT")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(raw)
    for entry in entries:
        path = directory / entry["file"]
        if digest(path) != entry["raw_digest"] or path.stat().st_size != entry["byte_length"]:
            raise ValueError("SCHEMA_REGISTRY_BUILD_READBACK_DRIFT")
    after = {path.relative_to(ROOT).as_posix(): digest(path) for path in sources}
    if before != after:
        raise ValueError("SCHEMA_REGISTRY_BUILD_INPUT_DRIFT")
    preserve()
    write("SCHEMA_REGISTRY_BUILD_READBACK.json", {
        "status": "RAW_BACKED_SCHEMA_REGISTRY_BUILD_READ_BACK_NOT_FROZEN_NOT_INSTALLED",
        "directory": directory.relative_to(ROOT).as_posix(), "build_digest": build_digest, "entries": entries,
        "sources": [{"file": name, "raw_digest": raw_digest} for name, raw_digest in before.items()],
        "bound_semantic_keys": len(files["objects/schema_registry__2.json"]["body"]["bindings"]),
        "schema_registry_ref": files["objects/schema_registry__2.json"]["ref"],
        "artifact_contract_registry_ref": files["objects/artifact_contract_registry__1.json"]["ref"],
        "external_schema_root": root_schema, "schema_build_digest": report["build_digest"], "input_drift": [],
        "qualification": False, "installed": False, "frozen": False, "Q1": "NOT_STARTED", "Q2": "NOT_STARTED", "NF02": "OPEN"})
    print(json.dumps({"schema_registry_build_readback": "PASS", "bound_keys": len(files["objects/schema_registry__2.json"]["body"]["bindings"]),
                      "build_digest": build_digest, "qualification": False}))


if __name__ == "__main__":
    main()

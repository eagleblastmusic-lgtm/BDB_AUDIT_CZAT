"""Materialize independent protocol/Spec build inputs, without qualification."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

from build_time_candidates import verify_readback
from execution import OUT, ROOT, canonical, digest, preserve, read, write
from schema_registry_build_candidate import constant_profile, profile_ref

sys.path.insert(0, str(ROOT / "src"))
from bdb_audit.core.hashing import _domain_digest  # noqa: E402


SELECTIONS = {
    "NF02_EXTERNAL_LANE_SLOT_V2": {
        "normalizer_ref": "NF02_RESULT_NORMALIZER_V2", "transport_ref": "NF02_RESULT_TRANSPORT_V2"},
    "NF02_PROTOCOL_PROFILE_V2": {
        "input_transport_ref": "NF02_PACKAGE_TRANSPORT_V2", "result_transport_ref": "NF02_RESULT_TRANSPORT_V2",
        "normalizer_ref": "NF02_RESULT_NORMALIZER_V2", "result_slot_ref": "NF02_EXTERNAL_LANE_SLOT_V2",
        "package_semantic_profile_ref": "NF02_PACKAGE_SEMANTIC_PROFILE_V1"},
}
LEAVES = ("NF02_PACKAGE_TRANSPORT_V2", "NF02_RESULT_TRANSPORT_V2", "NF02_RESULT_NORMALIZER_V2",
          "NF02_PACKAGE_SEMANTIC_PROFILE_V1", "FULL_PATH_TRANSITION_TABLE_V2")


def construct():
    report = read(OUT / "BUILD_TIME_CANDIDATE_READBACK.json")
    for source in report["source_inputs"]:
        if digest(ROOT / source["file"]) != source["raw_digest"]:
            raise ValueError("INITIAL_PROTOCOL_STALE_BUILD_INPUT")
    directory = ROOT / report["directory"]
    verify_readback(directory, report["entries"])
    catalog = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
    rules = {(row["owner"], row["field"]): row for row in
             read(OUT / "design/PROFILE_REFERENCE_CONTRACTS.json")["material_refs"]}
    profiles = {name: constant_profile(catalog[name]) for name in LEAVES}
    for name, fields in SELECTIONS.items():
        supplied = {}
        for field, target in fields.items():
            rule = rules[name, field]
            if (rule["representation"], rule["targets"], rule["ref_class"], rule["same_commit"]) != (
                    "ExternalProfileRef", [target], "PINNED_PROFILE_REF", False):
                raise ValueError("INITIAL_PROTOCOL_REFERENCE_CONTRACT_MISMATCH")
            supplied[field] = profile_ref(profiles[target])
        profiles[name] = constant_profile(catalog[name], supplied)
    by_id = {entry["$id"]: entry for entry in report["entries"]}
    for name, body in profiles.items():
        wire = catalog[name].get("wire_profile_id", name)
        schema = read(directory / by_id["BDB_EXTERNAL_PROFILE_SCHEMA::" + wire]["file"])
        Draft202012Validator(schema).validate(body)
    entry = by_id["BDB_SCHEMA_REGISTRY::spec_revision/2"]
    schema = read(directory / entry["file"])
    body = {}
    supplied = {"protocol_profile_ref": profile_ref(profiles["NF02_PROTOCOL_PROFILE_V2"]),
                "transition_contract_ref": profile_ref(profiles["FULL_PATH_TRANSITION_TABLE_V2"])}
    for name, definition in schema["properties"].items():
        if "const" in definition:
            body[name] = definition["const"]
        elif name in supplied:
            body[name] = supplied[name]
        else:
            raise ValueError("INITIAL_SPEC_UNSUPPLIED_FIELD: " + name)
    if body["initialization"] != "INITIALIZE_CAMPAIGN_FROM_LEGACY; EMPTY_HISTORY; one union-Kahn; BDB_BOOTSTRAP_PRECEDENCE_V2 exact scope only":
        raise ValueError("INITIAL_SPEC_WRONG_BOOTSTRAP_PRECEDENCE")
    Draft202012Validator(schema).validate(body)
    reference = {"kind": "spec_revision", "revision_digest": _domain_digest(
        "spec_revision", "2", body, registry_kind="spec_revision"),
        "schema_revision_ref": {"kind": "schema", "revision_digest": entry["raw_digest"]},
        "digest_profile": "BDB-OBJECT-DIGEST-1", "logical_id": body["spec_id"]}
    files = {"profiles/" + body["profile_id"] + ".json": body for body in profiles.values()}
    files["objects/spec_revision__2.json"] = {"kind": "spec_revision", "version": "2", "body": body, "ref": reference}
    if len(files) != 8:
        raise ValueError("INITIAL_PROTOCOL_DUPLICATE_WIRE_IDENTITY")
    verify_files(files, report)
    return files, reference, report


def verify_files(files, report):
    catalog = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
    expected = {"profiles/" + catalog[name].get("wire_profile_id", name) + ".json"
                for name in (*LEAVES, *SELECTIONS)} | {"objects/spec_revision__2.json"}
    if set(files) != expected:
        raise ValueError("INITIAL_PROTOCOL_CLOSURE_MEMBERSHIP")
    schemas = {entry["$id"]: entry for entry in report["entries"]}
    directory = ROOT / report["directory"]
    profile_bodies = {}
    for name in (*LEAVES, *SELECTIONS):
        wire = catalog[name].get("wire_profile_id", name)
        body = files["profiles/" + wire + ".json"]
        entry = schemas["BDB_EXTERNAL_PROFILE_SCHEMA::" + wire]
        Draft202012Validator(read(directory / entry["file"])).validate(body)
        profile_bodies[name] = body
    edges = []
    for owner, fields in SELECTIONS.items():
        for field, target in fields.items():
            if profile_bodies[owner][field] != profile_ref(profile_bodies[target]):
                raise ValueError("INITIAL_PROTOCOL_EXACT_PIN_MISMATCH")
            edges.append((target, owner))
    obj = files["objects/spec_revision__2.json"]
    entry = schemas["BDB_SCHEMA_REGISTRY::spec_revision/2"]
    Draft202012Validator(read(directory / entry["file"])).validate(obj["body"])
    if set(obj) != {"kind", "version", "body", "ref"} or (obj["kind"], obj["version"]) != ("spec_revision", "2"):
        raise ValueError("INITIAL_SPEC_ENVELOPE_IDENTITY")
    expected_ref = {"kind": "spec_revision", "revision_digest": _domain_digest(
        "spec_revision", "2", obj["body"], registry_kind="spec_revision"),
        "schema_revision_ref": {"kind": "schema", "revision_digest": entry["raw_digest"]},
        "digest_profile": "BDB-OBJECT-DIGEST-1", "logical_id": obj["body"]["spec_id"]}
    if obj["ref"] != expected_ref:
        raise ValueError("INITIAL_SPEC_EXACT_IDENTITY_MISMATCH")
    for field, target in (("protocol_profile_ref", "NF02_PROTOCOL_PROFILE_V2"),
                          ("transition_contract_ref", "FULL_PATH_TRANSITION_TABLE_V2")):
        if obj["body"][field] != profile_ref(profile_bodies[target]):
            raise ValueError("INITIAL_SPEC_EXACT_PIN_MISMATCH")
        edges.append((target, "spec_revision/2"))
    remaining = set(profile_bodies) | {"spec_revision/2"}
    order = []
    while remaining:
        ready = sorted(node for node in remaining if not any(
            target == node and source in remaining for source, target in edges))
        if not ready:
            raise ValueError("INITIAL_PROTOCOL_DEPENDENCY_CYCLE")
        order.extend(ready)
        remaining.difference_update(ready)
    return {"nodes": len(order), "edges": [list(edge) for edge in edges], "topological_order": order,
            "scope": "Actual protocol/Spec build inputs only; no installed trust or campaign facts"}


def main():
    preserve()
    sources = [Path(__file__), OUT / "tools/execution.py", OUT / "tools/schema_registry_build_candidate.py",
               OUT / "tools/build_time_candidates.py", OUT / "BUILD_TIME_CANDIDATE_READBACK.json",
               OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json", OUT / "design/PROFILE_REFERENCE_CONTRACTS.json",
               ROOT / "src/bdb_audit/core/hashing.py", ROOT / "src/bdb_audit/core/canonical_json.py",
               ROOT / "docs/R5_4_2/OWNER_DELEGATED_DECISION_REGISTER.md"]
    before = {p.relative_to(ROOT).as_posix(): digest(p) for p in sources}
    files, reference, schemas = construct()
    entries = [{"file": name, "raw_digest": hashlib.sha256(canonical(value) + b"\n").hexdigest(),
                "byte_length": len(canonical(value) + b"\n")} for name, value in sorted(files.items())]
    build_digest = hashlib.sha256(canonical(entries)).hexdigest()
    directory = OUT / "initial_protocol_build_candidate" / build_digest
    for name, value in files.items():
        path = directory / name
        raw = canonical(value) + b"\n"
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("INITIAL_PROTOCOL_EXISTING_BYTES_DRIFT")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(raw)
    if {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()} != set(files):
        raise ValueError("INITIAL_PROTOCOL_INVENTORY_DRIFT")
    for entry in entries:
        path = directory / entry["file"]
        if digest(path) != entry["raw_digest"] or path.stat().st_size != entry["byte_length"]:
            raise ValueError("INITIAL_PROTOCOL_READBACK_DRIFT")
    verify_readback(ROOT / schemas["directory"], schemas["entries"])
    if before != {p.relative_to(ROOT).as_posix(): digest(p) for p in sources}:
        raise ValueError("INITIAL_PROTOCOL_EXECUTION_INPUT_DRIFT")
    preserve()
    write("INITIAL_PROTOCOL_BUILD_READBACK.json", {
        "status": "BUILD_INPUTS_READ_BACK_NOT_FROZEN_NOT_INSTALLED_NOT_QUALIFIED",
        "directory": directory.relative_to(ROOT).as_posix(), "build_digest": build_digest,
        "entries": entries, "spec_revision_ref": reference, "schema_build_digest": schemas["build_digest"],
        "source_inputs": before, "input_drift": [], "qualification": False, "installed": False,
        "actual_build_dependency_closure": verify_files(files, schemas),
        "remaining": ["independent trusted installation qualification", "exact policy purpose parameters",
                      "complete bootstrap roots and namespace", "legal durable genesis", "Q1", "Q2", "N5-N11"]})
    print("PASS initial protocol build readback:", len(entries), "files; no qualification")


if __name__ == "__main__":
    main()

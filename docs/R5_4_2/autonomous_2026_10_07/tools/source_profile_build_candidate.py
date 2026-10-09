"""Build exact source/trust inputs, retaining historical trust without activation."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

from build_time_candidates import verify_readback
from execution import BASE, OUT, ROOT, canonical, digest, preserve, read, write
from schema_registry_build_candidate import constant_profile, profile_ref

sys.path.insert(0, str(ROOT / "src"))
from bdb_audit.core.hashing import _domain_digest  # noqa: E402


PARAMETERS = OUT / "design/SOURCE_TRUST_BUILD_PARAMETERS.json"


def source_trust_files(report, source_path, source_entry):
    """Concrete candidate declarations; their pins never self-authorize installation."""
    catalog = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
    supplied = read(PARAMETERS)
    if supplied["scope"] != "UNQUALIFIED_CANDIDATE_INPUTS; no authentication, installation or campaign creation":
        raise ValueError("SOURCE_TRUST_PARAMETER_SCOPE")
    if supplied["history_anchor_mode"] != "LOCAL_PINNED":
        raise ValueError("SOURCE_TRUST_UNSUPPORTED_ANCHOR_CONFIGURATION")
    profiles = {}

    def add(name, contract, parameters):
        profiles[name] = constant_profile(catalog[contract], parameters)
        return profile_ref(profiles[name])

    namespace = add("BOOTSTRAP_NAMESPACE_V2", "BOOTSTRAP_NAMESPACE_V2",
                    {"history_namespace_id": supplied["namespace_id"]})
    common = {"namespace_profile_ref": namespace, "permitted_approval_purposes": []}
    coordinator = add("COORDINATOR", "PRINCIPAL_AUTHORIZATION_V1", {
        **common, "principal_id": supplied["coordinator_principal_id"], "role": "COORDINATOR",
        "permitted_operations": ["INITIALIZE", "ACCEPT", "TRANSITION", "INGEST"]})
    owner = add("SOURCE_OWNER", "PRINCIPAL_AUTHORIZATION_V1", {
        **common, "principal_id": supplied["source_authorizer_principal_id"], "role": "OWNER",
        "permitted_operations": ["INITIALIZE"]})
    authority = add("SOURCE_AUTHORITY_V1", "SOURCE_AUTHORITY_V1", {
        "authority_id": "BDB_QUALIFICATION_SOURCE", "authority_mode": "AUTHORIZED_GIT",
        "repository_or_snapshot_identity": supplied["repository_identity"],
        "authorizing_principal_ref": owner})
    add("SOURCE_IDENTITY_V3", "SOURCE_IDENTITY_V2", {
        "authority_profile_refs": [authority], "surface_key_profile_refs": [],
        "path_profile_ref": profile_ref(source_path), "manifest_entry_profile_ref": profile_ref(source_entry),
        "authority_parameters": [{"authority_ref": authority, "authority_mode": "AUTHORIZED_GIT",
                                  "git_object_algorithm": "SHA1"}]})
    recovery = add("EXACT_DURABLE_RECOVERY_V1", "EXACT_DURABLE_RECOVERY_V1", {"parameters": {
        "receipt_policy": "RECONSTRUCT_FROM_ACCEPTED_COMMIT", "raw_policy": "READBACK_ALL_ACCEPTED_REFS",
        "head_policy": "EXACT_CHAIN", "anchor_policy": "LOCAL"}})
    recovery_pin = add("RECOVERY_REFERENCE_PROFILE_V1", "RECOVERY_REFERENCE_PROFILE_V1",
                       {"recovery_contract_ref": recovery})
    trust_body = {key: supplied[key] for key in (
        "trust_profile_id", "vault_protection_class", "executor_write_boundary", "history_anchor_mode",
        "guarantees", "explicit_non_guarantees")}
    trust_body.update(trust_profile_revision=1, coordinator_authority_ref=coordinator,
                      recovery_pin_policy_ref=recovery_pin)
    entry = next(row for row in report["entries"] if row["$id"] == "BDB_SCHEMA_REGISTRY::trust_profile/2")
    reference = {"kind": "trust_profile", "revision_digest": _domain_digest(
        "trust_profile", "2", trust_body, registry_kind="trust_profile"),
        "schema_revision_ref": {"kind": "schema", "revision_digest": entry["raw_digest"]},
        "digest_profile": "BDB-OBJECT-DIGEST-1", "logical_id": trust_body["trust_profile_id"]}
    files = {"profiles/" + name + ".json": canonical(body) + b"\n" for name, body in profiles.items()}
    files["objects/trust_profile__2.json"] = canonical({
        "kind": "trust_profile", "version": "2", "body": trust_body, "ref": reference}) + b"\n"
    return files


def verify_files(files, report):
    """Verify actual candidate body pins/DAG; never return installed authority."""
    catalog = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
    schemas = {row["$id"]: row for row in report["entries"]}
    directory = ROOT / report["directory"]
    profile_files = {"SOURCE_PATH_PROFILE_V1", "SOURCE_MANIFEST_ENTRY_PROFILE_V1",
                     "BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1", "BOOTSTRAP_NAMESPACE_V2", "COORDINATOR",
                     "SOURCE_OWNER", "SOURCE_AUTHORITY_V1", "SOURCE_IDENTITY_V3",
                     "EXACT_DURABLE_RECOVERY_V1", "RECOVERY_REFERENCE_PROFILE_V1"}
    expected_files = {"profiles/" + name + ".json" for name in profile_files} | {
        "objects/trust_profile__2.json", "historical/objects/trust_profile__1.json",
        "historical/schemas/trust_profile__1.schema.json"}
    if set(files) != expected_files:
        raise ValueError("SOURCE_TRUST_CLOSURE_MEMBERSHIP")
    profiles = {name: json.loads(raw) for name, raw in files.items() if name.startswith("profiles/")}
    by_pin = {}
    edges = []
    for name, body in profiles.items():
        entry = schemas["BDB_EXTERNAL_PROFILE_SCHEMA::" + body["profile_id"]]
        Draft202012Validator(read(directory / entry["file"])).validate(body)
        pin = canonical(profile_ref(body))
        if pin in by_pin:
            raise ValueError("SOURCE_TRUST_DUPLICATE_PROFILE_PIN")
        by_pin[pin] = name

    rules = read(OUT / "design/PROFILE_REFERENCE_CONTRACTS.json")["material_refs"]
    from bootstrap_instance_design import values
    for name, body in profiles.items():
        owners = [key for key, contract in catalog.items()
                  if contract.get("wire_profile_id", key) == body["profile_id"]]
        if len(owners) != 1:
            raise ValueError("SOURCE_TRUST_PROFILE_OWNER_AMBIGUOUS")
        for rule in rules:
            if rule["owner"] != owners[0] or rule["representation"] != "ExternalProfileRef":
                continue
            targets = {catalog[key].get("wire_profile_id", key) for key in rule["targets"]}
            for pin in values(body, rule["field"].replace("[]", "").split(".")):
                source = by_pin.get(canonical(pin))
                if source is None or pin["profile_id"] not in targets:
                    raise ValueError("SOURCE_TRUST_EXACT_PROFILE_PIN_MISMATCH")
                edges.append((source, name))
    identity = profiles["profiles/SOURCE_IDENTITY_V3.json"]
    parameters = identity["authority_parameters"]
    if ([row["authority_ref"] for row in parameters] != identity["authority_profile_refs"]
            or any(row["authority_mode"] != "AUTHORIZED_GIT" or row["git_object_algorithm"] != "SHA1"
                   for row in parameters)):
        raise ValueError("SOURCE_TRUST_AUTHORITY_PARAMETER_COVERAGE")
    obj = json.loads(files["objects/trust_profile__2.json"])
    entry = schemas["BDB_SCHEMA_REGISTRY::trust_profile/2"]
    Draft202012Validator(read(directory / entry["file"])).validate(obj["body"])
    body = obj["body"]
    expected = {"kind": "trust_profile", "revision_digest": _domain_digest(
        "trust_profile", "2", body, registry_kind="trust_profile"),
        "schema_revision_ref": {"kind": "schema", "revision_digest": entry["raw_digest"]},
        "digest_profile": "BDB-OBJECT-DIGEST-1", "logical_id": body["trust_profile_id"]}
    if set(obj) != {"kind", "version", "body", "ref"} or (obj["kind"], obj["version"]) != ("trust_profile", "2") or obj["ref"] != expected:
        raise ValueError("SOURCE_TRUST_OBJECT_IDENTITY")
    for field, target in (("coordinator_authority_ref", "profiles/COORDINATOR.json"),
                          ("recovery_pin_policy_ref", "profiles/RECOVERY_REFERENCE_PROFILE_V1.json")):
        if body[field] != profile_ref(profiles[target]):
            raise ValueError("SOURCE_TRUST_ROOT_PIN_MISMATCH")
        edges.append((target, "objects/trust_profile__2.json"))
    if (body["history_anchor_mode"] != "LOCAL_PINNED" or "external_anchor_profile_ref" in body
            or profiles["profiles/EXACT_DURABLE_RECOVERY_V1.json"]["parameters"]["anchor_policy"] != "LOCAL"):
        raise ValueError("SOURCE_TRUST_ANCHOR_RECOVERY_MISMATCH")
    if (profiles["profiles/COORDINATOR.json"]["role"] != "COORDINATOR"
            or profiles["profiles/SOURCE_OWNER.json"]["role"] != "OWNER"):
        raise ValueError("SOURCE_TRUST_PRINCIPAL_ROLE_MISMATCH")
    remaining = set(profiles) | {"objects/trust_profile__2.json"}
    order = []
    while remaining:
        ready = sorted(node for node in remaining if not any(
            target == node and source in remaining for source, target in edges))
        if not ready:
            raise ValueError("SOURCE_TRUST_DEPENDENCY_CYCLE")
        order.extend(ready)
        remaining.difference_update(ready)
    return {"nodes": len(order), "edges": [list(edge) for edge in sorted(edges)], "topological_order": order,
            "scope": "Actual unqualified source/trust build declarations only; no installed principal or vault guarantee"}


def construct():
    report = read(OUT / "BUILD_TIME_CANDIDATE_READBACK.json")
    verify_readback(ROOT / report["directory"], report["entries"])
    for source in report["source_inputs"]:
        if digest(ROOT / source["file"]) != source["raw_digest"]:
            raise ValueError("SOURCE_PROFILE_STALE_SCHEMA_INPUT")
    sr = read(OUT / "SCHEMA_REGISTRY_BUILD_READBACK.json")
    if sr["schema_build_digest"] != report["build_digest"]:
        raise ValueError("SOURCE_PROFILE_SCHEMA_REGISTRY_MISMATCH")
    raw_entry = next(row for row in sr["entries"] if row["file"] == "profiles/BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1.json")
    raw_path = ROOT / sr["directory"] / raw_entry["file"]
    if digest(raw_path) != raw_entry["raw_digest"] or raw_path.stat().st_size != raw_entry["byte_length"]:
        raise ValueError("SOURCE_PROFILE_RAW_CONTRACT_DRIFT")
    raw_contract = read(raw_path)
    catalog = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
    schemas = {row["$id"]: row for row in report["entries"]}
    manifest = schemas["BDB_SCHEMA_REGISTRY::source_manifest/2"]
    source_path = constant_profile(catalog["SOURCE_PATH_PROFILE_V1"])
    source_entry = constant_profile(catalog["SOURCE_MANIFEST_ENTRY_PROFILE_V1"], {
        "source_manifest_schema_raw_ref": {"raw_digest": manifest["raw_digest"],
            "byte_length": manifest["byte_length"], "media_type": manifest["media_type"],
            "artifact_contract_ref": profile_ref(raw_contract)}})
    for profile in (source_path, source_entry):
        schema = schemas["BDB_EXTERNAL_PROFILE_SCHEMA::" + profile["profile_id"]]
        Draft202012Validator(read(ROOT / report["directory"] / schema["file"])).validate(profile)
    trust_path = BASE / "candidate/objects/trust_profile__1.json"
    predecessor = read(BASE / "R5_4_1_CANDIDATE_MANIFEST.json")
    pin = next(row for row in predecessor["machine_candidate_files"] if row["file"] == "objects/trust_profile__1.json")
    if digest(trust_path) != pin["sha256"] or trust_path.stat().st_size != pin["bytes"]:
        raise ValueError("SOURCE_PROFILE_PREDECESSOR_TRUST_DRIFT")
    trust = read(trust_path)
    trust_schema_path = BASE / "candidate/schemas/trust_profile__1.schema.json"
    schema_pin = next(row for row in predecessor["machine_candidate_files"] if row["file"] == "schemas/trust_profile__1.schema.json")
    if digest(trust_schema_path) != schema_pin["sha256"] or trust_schema_path.stat().st_size != schema_pin["bytes"]:
        raise ValueError("SOURCE_PROFILE_PREDECESSOR_TRUST_SCHEMA_DRIFT")
    Draft202012Validator(read(trust_schema_path)).validate(trust["body"])
    active_trust_schema = schemas["BDB_SCHEMA_REGISTRY::trust_profile/2"]
    if "BDB_SCHEMA_REGISTRY::trust_profile/1" in schemas or Draft202012Validator(
            read(ROOT / report["directory"] / active_trust_schema["file"])).is_valid(trust["body"]):
        raise ValueError("SOURCE_PROFILE_HISTORICAL_TRUST_LAUNDERING")
    if (trust["kind"], trust["version"]) != ("trust_profile", "1") or trust["ref"]["revision_digest"] != _domain_digest(
            "trust_profile", "1", trust["body"], registry_kind="trust_profile"):
        raise ValueError("SOURCE_PROFILE_TRUST_OBJECT_IDENTITY")
    if trust["ref"]["schema_revision_ref"]["revision_digest"] != digest(trust_schema_path):
        raise ValueError("SOURCE_PROFILE_TRUST_SCHEMA_PIN")
    files = {"profiles/SOURCE_PATH_PROFILE_V1.json": canonical(source_path) + b"\n",
            "profiles/SOURCE_MANIFEST_ENTRY_PROFILE_V1.json": canonical(source_entry) + b"\n",
            "profiles/BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1.json": raw_path.read_bytes(),
            "historical/objects/trust_profile__1.json": trust_path.read_bytes(),
            "historical/schemas/trust_profile__1.schema.json": trust_schema_path.read_bytes()}
    files.update(source_trust_files(report, source_path, source_entry))
    verify_files(files, report)
    return files, report


def main():
    preserve()
    sources = [Path(__file__), PARAMETERS, OUT / "tools/execution.py", OUT / "tools/build_time_candidates.py",
               OUT / "tools/schema_registry_build_candidate.py", OUT / "BUILD_TIME_CANDIDATE_READBACK.json",
               OUT / "SCHEMA_REGISTRY_BUILD_READBACK.json", OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json",
               OUT / "design/PROFILE_REFERENCE_CONTRACTS.json", OUT / "tools/bootstrap_instance_design.py",
               BASE / "R5_4_1_CANDIDATE_MANIFEST.json", BASE / "candidate/objects/trust_profile__1.json",
               BASE / "candidate/schemas/trust_profile__1.schema.json",
               ROOT / "src/bdb_audit/core/hashing.py", ROOT / "src/bdb_audit/core/canonical_json.py"]
    before = {p.relative_to(ROOT).as_posix(): digest(p) for p in sources}
    files, report = construct()
    entries = [{"file": name, "raw_digest": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw)}
               for name, raw in sorted(files.items())]
    build_digest = hashlib.sha256(canonical(entries)).hexdigest()
    directory = OUT / "source_profile_build_candidate" / build_digest
    for name, raw in files.items():
        path = directory / name
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("SOURCE_PROFILE_EXISTING_BYTES_DRIFT")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(raw)
    if {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()} != set(files):
        raise ValueError("SOURCE_PROFILE_INVENTORY_DRIFT")
    for entry in entries:
        path = directory / entry["file"]
        if digest(path) != entry["raw_digest"] or path.stat().st_size != entry["byte_length"]:
            raise ValueError("SOURCE_PROFILE_READBACK_DRIFT")
    verify_readback(ROOT / report["directory"], report["entries"])
    if before != {p.relative_to(ROOT).as_posix(): digest(p) for p in sources}:
        raise ValueError("SOURCE_PROFILE_EXECUTION_INPUT_DRIFT")
    preserve()
    write("SOURCE_PROFILE_BUILD_READBACK.json", {
        "directory": directory.relative_to(ROOT).as_posix(), "build_digest": build_digest,
        "entries": entries, "schema_build_digest": report["build_digest"], "source_inputs": before,
        "input_drift": [], "qualification": False, "installed": False,
        "status": "EXACT_SOURCE_TRUST_BUILD_INPUTS_AND_ISOLATED_HISTORY_READ_BACK_NOT_QUALIFIED",
        "actual_build_dependency_closure": verify_files(files, report),
        "remaining": ["independently authenticated principal and source authority", "independently authorized namespace",
                      "independently authorized successor trust_profile/2 installation; historical /1 is never active",
                      "actual vault/executor isolation enforcement and readback", "surface-key normalizer instances",
                      "complete source identity profile", "complete policy and bootstrap roots", "Q1", "Q2", "N5-N11"]})
    print("PASS source-profile build readback:", len(entries), "files; no qualification")


if __name__ == "__main__":
    main()

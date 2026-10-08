"""Retain actual source-profile leaves and exact inherited trust build input."""
from __future__ import annotations
import hashlib
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

from build_time_candidates import verify_readback
from execution import BASE, OUT, ROOT, canonical, digest, preserve, read, write
from schema_registry_build_candidate import constant_profile, profile_ref

sys.path.insert(0, str(ROOT / "src"))
from bdb_audit.core.hashing import _domain_digest  # noqa: E402


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
    trust_schema = schemas["BDB_SCHEMA_REGISTRY::trust_profile/1"]
    Draft202012Validator(read(ROOT / report["directory"] / trust_schema["file"])).validate(trust["body"])
    if (trust["kind"], trust["version"]) != ("trust_profile", "1") or trust["ref"]["revision_digest"] != _domain_digest(
            "trust_profile", "1", trust["body"], registry_kind="trust_profile"):
        raise ValueError("SOURCE_PROFILE_TRUST_OBJECT_IDENTITY")
    if trust["ref"]["schema_revision_ref"]["revision_digest"] != trust_schema["raw_digest"]:
        raise ValueError("SOURCE_PROFILE_TRUST_SCHEMA_PIN")
    return {"profiles/SOURCE_PATH_PROFILE_V1.json": canonical(source_path) + b"\n",
            "profiles/SOURCE_MANIFEST_ENTRY_PROFILE_V1.json": canonical(source_entry) + b"\n",
            "profiles/BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1.json": raw_path.read_bytes(),
            "objects/trust_profile__1.json": trust_path.read_bytes()}, report


def main():
    preserve()
    sources = [Path(__file__), OUT / "tools/execution.py", OUT / "tools/build_time_candidates.py",
               OUT / "tools/schema_registry_build_candidate.py", OUT / "BUILD_TIME_CANDIDATE_READBACK.json",
               OUT / "SCHEMA_REGISTRY_BUILD_READBACK.json", OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json",
               BASE / "R5_4_1_CANDIDATE_MANIFEST.json", BASE / "candidate/objects/trust_profile__1.json",
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
        "status": "SOURCE_LEAVES_AND_EXACT_INHERITED_TRUST_READ_BACK_NOT_FROZEN_NOT_QUALIFIED",
        "remaining": ["independently authenticated principal and source authority", "exact namespace",
                      "complete source identity profile", "complete policy and bootstrap roots", "Q1", "Q2", "N5-N11"]})
    print("PASS source-profile build readback:", len(entries), "files; no qualification")


if __name__ == "__main__":
    main()

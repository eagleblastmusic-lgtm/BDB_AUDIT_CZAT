"""Fresh execution evidence; never treats diagnostic claims as qualification."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

if sys.flags.optimize:
    raise RuntimeError("DESIGN_VERIFICATION_ASSERTIONS_DISABLED")

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/R5_4_1"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def write(name: str, value) -> None:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, encoding="utf-8", check=True)
    return result.stdout.strip()


def predecessor_readback():
    manifest = read(BASE / "R5_4_1_CANDIDATE_MANIFEST.json")
    record_path = BASE / "AUTHOR_BASELINE_QUALIFICATION_R5_4_1.json"
    record = read(record_path)
    mismatches = []
    results = []
    identities = {}
    for category in ("normative", "machine"):
        entries = manifest[category + "_candidate_files"]
        for entry in entries:
            path = BASE / "candidate" / entry["file"]
            actual = {"file": entry["file"], "bytes": path.stat().st_size, "sha256": digest(path)}
            expected = {k: entry[k] for k in actual}
            results.append({"category": category, **actual, "matches": actual == expected})
            if actual != expected:
                mismatches.append(entry["file"])
        preimage = sorted([{k: e[k] for k in ("file", "bytes", "sha256")} for e in entries], key=lambda e: e["file"])
        identity = hashlib.sha256(canonical(preimage)).hexdigest()
        assert identity == manifest[category + "_candidate_set_sha256"] == record[category + "_candidate_set_digest"], "CANDIDATE_DRIFT"
        identities[category + "_candidate_set_digest"] = identity
    for label, path, field in (
        ("manifest_raw_digest", BASE / "R5_4_1_CANDIDATE_MANIFEST.json", "candidate_manifest_raw_digest"),
        ("registry_raw_digest", BASE / "candidate/BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json", "registry_raw_digest"),
        ("golden_raw_digest", BASE / "candidate/BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json", "golden_vector_set_raw_digest"),
    ):
        actual = digest(path)
        assert actual == record[field], "CANDIDATE_DRIFT " + label
        identities[label] = actual
    schema = read(BASE / "candidate/objects/schema_registry__2.json")
    identities["schema_registry_object_digest"] = hashlib.sha256(b"BDB2/schema_registry/2\0" + canonical(schema["body"])).hexdigest()
    assert identities["schema_registry_object_digest"] == schema["ref"]["revision_digest"] == record["schema_registry_ref"]["revision_digest"], "CANDIDATE_DRIFT SchemaRegistry"
    registry = read(BASE / "candidate/objects/artifact_contract_registry__1.json")
    registry_digest = hashlib.sha256(b"BDB2/artifact_contract_registry/1\0" + canonical(registry["body"])).hexdigest()
    assert registry_digest == registry["ref"]["revision_digest"] == record["artifact_contract_registry_ref"]["revision_digest"], "CANDIDATE_DRIFT Registry"
    registry_document = read(BASE / "candidate/BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json")
    assert registry["body"] == registry_document and registry_document["registry_id"] == record["registry_id"], "CANDIDATE_DRIFT Registry body"
    golden = read(BASE / "candidate/BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json")
    assert golden["vector_set_id"] == record["golden_vector_set_id"], "CANDIDATE_DRIFT Golden identity"
    identities["registry_object_digest"] = registry_digest
    identities["qualification_record_raw_digest"] = digest(record_path)
    identities["qualification_record_id"] = record["author_baseline_qualification_id"]
    assert not mismatches, "CANDIDATE_DRIFT " + repr(mismatches)
    return {"count": len(results), "mismatches": len(mismatches), "entries": results, "identities": identities}


def preserve():
    path = OUT / "PRESERVATION_BASELINE.json"
    if not path.exists():
        historical = {}
        for directory in (ROOT / "docs/R5_4", BASE, ROOT / "docs/R5_4_2"):
            for p in directory.rglob("*"):
                if p.is_file() and OUT not in p.parents and "__pycache__" not in p.parts:
                    historical[p.relative_to(ROOT).as_posix()] = digest(p)
        previous = read(ROOT / "docs/R5_4_2/surface_collector_resolution_v2/PRESERVATION_BASELINE.json")
        for name, expected in previous["protected_files"].items():
            assert digest(ROOT / name) == expected, "CANDIDATE_DRIFT " + name
            if not name.startswith(("src/", "tests/", "build/")):
                historical[name] = expected
        implementation = {p.relative_to(ROOT).as_posix(): digest(p) for directory in ("src", "tests", "build") for p in (ROOT / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        write("PRESERVATION_BASELINE.json", {
            "source_HEAD": git("rev-parse", "HEAD"), "source_tree": git("rev-parse", "HEAD^{tree}"),
            "branch": git("branch", "--show-current"), "main": git("rev-parse", "main"),
            "status": git("status", "--short"), "log": git("log", "-n", "10", "--oneline"),
            "protected_historical_files": historical, "initial_implementation_files": implementation,
            "authority": "Direct owner delegation 2026-10-07; predecessor and pre-existing design bytes remain immutable",
        })
    baseline = read(path)
    mismatches = [name for name, expected in baseline["protected_historical_files"].items() if digest(ROOT / name) != expected]
    assert not mismatches, "CANDIDATE_DRIFT " + repr(mismatches)
    assert git("rev-parse", "main") == baseline["main"], "Frozen main changed"
    return {"protected_files": len(baseline["protected_historical_files"]), "mismatches": len(mismatches)}


def main():
    protection = preserve()
    readback = predecessor_readback()
    write("PREDECESSOR_READBACK.json", readback)
    state_path = OUT / "EXECUTION_STATE.json"
    state = read(state_path) if state_path.exists() else {
        "Q1": "NOT_STARTED", "Q2": "NOT_STARTED", "N5_N11": "NOT_STARTED", "NF02": "OPEN",
    }
    state.update({
        "goal_status": "ACTIVE", "historical_preservation": protection,
        "predecessor_readback": {"count": readback["count"], "mismatches": readback["mismatches"]},
        "semantic_closure": "IN_PROGRESS; diagnostic fixed-point assertions are not accepted as evidence",
    })
    write("EXECUTION_STATE.json", state)
    print(json.dumps({"historical_preservation": protection, "predecessor_readback_count": readback["count"], "mismatches": readback["mismatches"]}))


if __name__ == "__main__":
    main()

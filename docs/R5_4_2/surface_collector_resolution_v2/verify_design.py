"""Read-only static design verification. Does not qualify schemas or runtime."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TASK = ROOT / "docs/R5_4_2"
OUT = TASK / "surface_collector_resolution_v2"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    before = read(OUT / "PRESERVATION_BASELINE.json")
    for name, digest in before["protected_files"].items():
        assert sha(ROOT / name) == digest, "CANDIDATE_DRIFT " + name
    manifest = read(ROOT / "docs/R5_4_1/R5_4_1_CANDIDATE_MANIFEST.json")
    entries = manifest["normative_candidate_files"] + manifest["machine_candidate_files"]
    for e in entries:
        path = ROOT / "docs/R5_4_1/candidate" / e["file"]
        assert path.stat().st_size == e["bytes"] and sha(path) == e["sha256"], e["file"]
    graph = read(TASK / "R5_4_2_SEMANTIC_CLOSURE_GRAPH_V2.json")
    proposals = read(OUT / "SUCCESSOR_CONTRACT_PROPOSALS.json")
    keys = {n["key"] for n in graph["nodes"]}
    assert len(keys) == len(graph["nodes"])
    assert all(e["from"] in keys and e["to"] in keys for e in graph["edges"])
    assert graph["V2_graph_reachability_fixed_point"] and graph["queue"] == []
    assert graph["fixed_point_reached"] is False
    assert graph["semantic_queue"] and graph["gate"] == "SEMANTIC_CLOSURE_INCOMPLETE"
    assert len(graph["unresolved"]) == graph["counts"]["unresolved_Class_D_purpose_contract_families"]
    for key, proposal in proposals.items():
        assert key in keys
        assert proposal["reference_contract_mode"] == "EXPLICIT_COMPLETE"
        assert proposal["body"] and proposal["cross_object_predicates"]
        for material in proposal["material_refs"]:
            assert set(material["allowed_keys"]) <= keys
            assert material["allowed_keys"] or material.get("representation")
            assert material["cardinality"] and material["ref_class"]
    collector = proposals["surface_collector_record/2"]
    assert collector["canonical_role"] == "FACT"
    assert [f.split(":")[0] for f in collector["body"]] == [
        "collector_raw_ref", "collector_record_profile_ref", "collector_execution_ref",
        "collection_run", "collector_record_input_history_cut",
    ]
    emitted = next(r for r in collector["material_refs"] if r["field"] == "collection_run.emitted_surface_refs")
    assert emitted["allowed_keys"] == ["surface_key/1"]
    assert all(e["to"] != "surface_record/1" for e in graph["edges"] if e["from"] == "surface_collector_record/2")
    assert len(graph["V2_vector_designs"]) == 18
    assert all(v["runtime_status"] == "NOT_RUN" for v in graph["V2_vector_designs"])
    assert not (TASK / "candidate").exists()
    assert not (TASK / "AUTHOR_BASELINE_QUALIFICATION_R5_4_2.json").exists()
    commands = [
        ["python", "-m", "ruff", "check", str(OUT / "build_design.py"), str(OUT / "verify_design.py")],
        ["git", "diff", "--check"], ["git", "status", "--short"],
        ["git", "branch", "--show-current"], ["git", "rev-parse", "HEAD"],
        ["git", "rev-parse", "HEAD^{tree}"], ["git", "rev-parse", "main"],
    ]
    runs = []
    for command in commands:
        start = time.monotonic()
        run = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8")
        assert run.returncode == 0, (command, run.stderr)
        runs.append({"command": subprocess.list2cmdline(command), "exit_code": run.returncode,
                     "duration_seconds": round(time.monotonic() - start, 3), "stdout": run.stdout,
                     "warnings": run.stderr})
    assert runs[-3]["stdout"].strip() == before["source_HEAD"]
    assert runs[-2]["stdout"].strip() == before["source_tree"]
    assert runs[-1]["stdout"].strip() == before["main"]
    files = [TASK / "R5_4_2_SURFACE_COLLECTOR_CONTRACT_PROPOSAL.md",
             TASK / "R5_4_2_OWNER_DECISION_PACKAGE_V2.md",
             TASK / "R5_4_2_FULL_SEMANTIC_CLOSURE_REPORT_V2.md",
             TASK / "R5_4_2_SEMANTIC_CLOSURE_GRAPH_V2.json",
             OUT / "ADDITIONAL_PROFILE_CONTRACT_PROPOSALS.md", OUT / "SUCCESSOR_CONTRACT_PROPOSALS.json",
             OUT / "build_design.py", OUT / "verify_design.py", OUT / "PRESERVATION_BASELINE.json"]
    result = {
        "schema": "BDB_R5_4_2_RAW_BOUNDARY_DESIGN_VERIFICATION/1",
        "static_verification": "PASS", "final_gate": graph["gate"],
        "semantic_readiness": "INCOMPLETE; static PASS is not semantic closure",
        "predecessor_readback": {"count": len(entries), "mismatches": 0},
        "protected_files_checked": len(before["protected_files"]), "preservation_mismatches": 0,
        "counts": graph["counts"], "runtime_vector_status": "NOT_RUN",
        "candidate_materialized": False, "qualification_record_emitted": False,
        "production_runtime_modified": False, "Q1_Q2_N5_N11": "NOT_EXECUTED",
        "commands": runs,
        "output_raw_pins": {p.relative_to(ROOT).as_posix(): sha(p) for p in files},
    }
    (OUT / "VERIFICATION.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ["static_verification", "final_gate", "predecessor_readback", "protected_files_checked", "preservation_mismatches"]}, indent=2))


if __name__ == "__main__":
    main()

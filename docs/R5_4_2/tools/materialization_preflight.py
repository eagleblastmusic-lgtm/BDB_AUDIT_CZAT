"""Read-only materialization prerequisite check. Never emits qualification.

The owner-approved graph stays immutable. A graph assertion of completeness
cannot substitute for a complete raw/typed representation contract.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TASK = ROOT / "docs/R5_4_2"
BASE = ROOT / "docs/R5_4_1"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect():
    approval = read(TASK / "OWNER_R5_4_2_SEMANTIC_CLOSURE_APPROVAL.json")
    graph = read(TASK / "R5_4_2_SEMANTIC_CLOSURE_GRAPH.json")
    for entry in approval["approved_artifacts"]:
        path = ROOT / entry["file"]
        if sha(path) != entry["raw_digest"] or path.stat().st_size != entry["bytes"]:
            return {"gate": "CANDIDATE_DRIFT", "file": entry["file"]}
    manifest = read(BASE / "R5_4_1_CANDIDATE_MANIFEST.json")
    entries = manifest["normative_candidate_files"] + manifest["machine_candidate_files"]
    for entry in entries:
        path = BASE / "candidate" / entry["file"]
        if sha(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]:
            return {"gate": "CANDIDATE_DRIFT", "file": entry["file"]}

    key = "surface_collector_record/1"
    node = next(n for n in graph["nodes"] if n["key"] == key)
    body_source = node["normative_semantic_source"]["complete_section_text"]
    collector_body = body_source.split("```text", 1)[1].split("```", 1)[0]
    completion = graph["schema_deferred_body_completion_decisions"].get(key)
    owner = (TASK / "R5_4_2_OWNER_DECISION_PACKAGE.md").read_text(encoding="utf-8")
    wrapper_rule = "an accepted wrapper must have an explicit closed body/schema and raw reference"
    if wrapper_rule not in owner:
        return {"gate": "R5_4_2_SEMANTIC_CLOSURE_MISMATCH", "issue": "Approved wrapper rule unavailable"}
    refs = node["qualified_registry_row"]["material_refs"] + node["proposed_material_ref_completion"]
    explicit_raw_body = completion and any("RawRef" in f for f in completion.get("body", []))
    if node["qualified_registry_row"]["canonical_role"] == "RAW_EVIDENCE" and not explicit_raw_body:
        inbound = [e for e in graph["edges"] if e["to"] == key and not e["source"].startswith("FINITE_ACTIVE_CLOSURE")]
        return {
            "gate": "SPEC_CONFLICT",
            "issue_id": "MATERIALIZATION_C01_COLLECTOR_RAW_TYPED_REPRESENTATION_UNSPECIFIED",
            "kind": key,
            "approved_owner_package_raw_digest": sha(TASK / "R5_4_2_OWNER_DECISION_PACKAGE.md"),
            "approved_graph_raw_digest": sha(TASK / "R5_4_2_SEMANTIC_CLOSURE_GRAPH.json"),
            "owner_wrapper_rule": wrapper_rule,
            "collector_body_source": collector_body.strip(),
            "explicit_body_completion": completion,
            "explicit_material_refs": refs,
            "inbound_typed_reference_edges": inbound,
            "new_decision_required": "Exact raw-backed collector wrapper body/RawRef and reference contract, or an explicitly approved alternative consumer representation with its identity/target-map changes. Neither is chosen by this check.",
            "predecessor_readback": {"count": len(entries), "mismatches": 0},
            "qualification_eligible": False,
            "qualification_record_emitted": False,
            "candidate_materialized": False,
        }
    return {
        "gate": "R5_4_2_QUALIFICATION_FAILED",
        "issue": "This preflight is not a full Q1 qualifier; semantic check alone cannot emit PASS",
        "qualification_record_emitted": False,
    }


if __name__ == "__main__":
    result = inspect()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(2 if result["gate"] == "SPEC_CONFLICT" else 3)

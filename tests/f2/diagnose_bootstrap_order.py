"""Read-only contract reconciliation, NOT an acceptance or qualification gate.

Exit 2 identifies the unresolved normative ordering conflict. The witness uses
only type-order constraints, not fabricated accepted objects or a synthetic H0.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINS = {
    "src/bdb_audit/core/artifact_contract_registry_r5_3.json":
        "5a89cfe26d927c9bf2638ad1e656b4ed810544f8d35e3e0ddf1365cd54b7343c",
    "F1_QUALIFICATION/inputs/BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json":
        "7bee0013d179adc8eba14d07c2c3ea159de0b8e37be9a9f6dcd55969550b7772",
    "F1_QUALIFICATION/inputs/BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS.md":
        "658f8866ca1a1330db9be582b13b47e87381de2208c53ee64ed9e47a8d3e15ee",
}


def diagnose():
    raw = {}
    for path, expected in PINS.items():
        raw[path] = (ROOT / path).read_bytes()
        if hashlib.sha256(raw[path]).hexdigest() != expected:
            raise RuntimeError("SOURCE_IDENTITY_DRIFT: " + path)
    registry = json.loads(raw[next(iter(PINS))])
    vectors = json.loads(raw[list(PINS)[1]])
    contracts = {c["kind"]: c for c in registry["contracts"]}
    legacy = contracts["legacy_raw_ref"]
    assert legacy["reference_contract_mode"] == "EXPLICIT_COMPLETE"
    assert legacy["material_refs"] == [{
        "allowed": ["history_cut"], "cardinality": "1", "field": "import_input_history_cut",
        "ref_class": "HISTORY_INPUT",
    }]
    content_fields = [r["field"] for r in legacy["material_refs"]
                      if r["ref_class"] in {"CONTENT_OBJECT", "CONTENT_OR_PRIOR"}]
    assert content_fields == []
    # No new-content prerequisite means the legacy node is zero-indegree from
    # the outset. Kahn's first key component dominates EVERY logical ID/digest.
    assert "legacy_raw_ref" < "source_generation"
    vector = next(v for v in vectors["vectors"] if v["id"] == "FR03_BOOTSTRAP_SINGLE_COMMIT_ACCEPT")
    required_order = vector["input"]["closure"]
    assert required_order.index("source_generation") < required_order.index("legacy_raw_ref")
    assert vector["expected"]["result"] == "ACCEPT"
    global_order = registry["global_invariants"]["initialization_bootstrap"]
    assert global_order.index("SourceGeneration") < global_order.index("legacy raw")
    contracts_text = raw[list(PINS)[2]].decode("utf-8")
    assert "buduje edges z typed content refs między nowymi objectami" in contracts_text
    assert "(kind, logical_id_or_empty, revision_digest)" in contracts_text
    return {
        "diagnostic_id": "F2-BOOTSTRAP-ORDER-002",
        "result": "SPEC_CONFLICT",
        "source_raw_sha256": PINS,
        "registered_kind": legacy["kind"],
        "reference_contract_mode": legacy["reference_contract_mode"],
        "legacy_material_refs": legacy["material_refs"],
        "legacy_same_commit_content_dependency_fields": content_fields,
        "kahn_forced_relative_order": ["legacy_raw_ref", "source_generation"],
        "bootstrap_required_relative_order": ["source_generation", "legacy_raw_ref"],
        "pinned_vector_id": vector["id"],
        "pinned_vector_input": vector["input"],
        "pinned_vector_expected": vector["expected"],
        "registry_initialization_invariant": global_order,
        "proof_scope": "Relative-order contradiction; not a fabricated executable bootstrap or golden runtime PASS",
        "runtime_acceptance_attempted": False,
        "M5_GATE": "NOT_RUN",
    }


if __name__ == "__main__":
    print(json.dumps(diagnose(), ensure_ascii=True, sort_keys=True, indent=2))
    raise SystemExit(2)

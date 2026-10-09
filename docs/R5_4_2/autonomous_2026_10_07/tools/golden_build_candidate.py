"""Construct versioned Golden build inputs without promoting design to runtime.

All predecessor vectors remain identical. Executable syntax answers reference
retained exact fixtures; approved canonical attack designs remain unexecuted.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from execution import BASE, OUT, ROOT, canonical, digest, preserve, read, write


def construct(predecessor, fixtures, fixture_report, designs, mapping):
    identifiers = [vector["id"] for vector in predecessor["vectors"]]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("DUPLICATE_PREDECESSOR_GOLDEN_ID")
    fixture_ids = [vector["id"] for vector in fixtures["vectors"]]
    if len(fixture_ids) != len(set(fixture_ids)) or len(fixture_ids) != fixture_report["vectors_replayed"]:
        raise ValueError("BUILD_GOLDEN_FIXTURE_DENOMINATOR_DRIFT")
    if fixtures["schema_build_digest"] != fixture_report["schema_build_digest"]:
        raise ValueError("BUILD_GOLDEN_SCHEMA_BUILD_DRIFT")
    vectors = copy.deepcopy(predecessor["vectors"])
    for ordinal, vector in enumerate(fixtures["vectors"]):
        vectors.append({"id": "R542_SCHEMA_" + format(ordinal, "06d"),
                        "domain": "successor_executable_schema_syntax",
                        "input": {"schema_id": vector["schema_id"], "schema_raw_digest": vector["schema_raw_digest"],
                                  "dependency_closure": vector["dependency_closure"],
                                  "fixture_file": "fixtures/BUILD_SCHEMA_KNOWN_ANSWERS.json",
                                  "fixture_file_raw_digest": fixture_report["raw_digest"],
                                  "fixture_id": vector["id"],
                                  "fixture_input_cjson_sha256": hashlib.sha256(canonical(vector["input"])).hexdigest()},
                        "expected": {"schema_result": vector["expected"]},
                        "why": vector["expectation_basis"], "canonical_runtime": "NOT_RUN"})
    ids = [vector["id"] for vector in vectors]
    if len(ids) != len(set(ids)):
        raise ValueError("SUCCESSOR_GOLDEN_ID_CONFLICT")
    future = []
    design_ids = set()
    for design in designs:
        if design["kind"] not in mapping:
            raise ValueError("GOLDEN_DESIGN_TARGET_NOT_IN_ACTIVE_CLOSURE")
        if design["id"] in design_ids:
            raise ValueError("DUPLICATE_CANONICAL_DESIGN_ID")
        design_ids.add(design["id"])
        item = copy.deepcopy(design)
        item["predecessor_design_key"] = design["kind"]
        item["kind"] = mapping[design["kind"]]
        item["execution_status"] = "DESIGN_ONLY_NOT_EXECUTED"
        future.append(item)
    return {"vector_set_id": "BDB-AUDIT-V2-FOUNDATION-GOLDEN-VECTORS-R5-4-2",
            "status": "BUILD_TIME_SUCCESSOR_NOT_FROZEN_NOT_QUALIFIED",
            "purpose": "Exact inherited answers and raw-bound successor schema syntax; no canonical runtime qualification",
            "inherited_vector_count": len(predecessor["vectors"]), "schema_vector_count": len(fixtures["vectors"]),
            "inherited_current_label_scope": "All inherited current-set labels concern their exact predecessor only",
            "vectors": vectors, "canonical_acceptance_designs": future,
            "canonical_acceptance_design_count": len(future), "canonical_runtime_execution_status": "NOT_RUN",
            "qualification": False, "frozen": False}


def verify_structure(body, predecessor, fixtures, fixture_report):
    count = len(predecessor["vectors"])
    if body["vectors"][:count] != predecessor["vectors"] or body["inherited_vector_count"] != count:
        raise ValueError("INHERITED_GOLDEN_EXPECTATIONS_CHANGED")
    ids = [vector["id"] for vector in body["vectors"]]
    if len(ids) != len(set(ids)):
        raise ValueError("SUCCESSOR_GOLDEN_ID_CONFLICT")
    if body["schema_vector_count"] != len(fixtures["vectors"]):
        raise ValueError("GOLDEN_FIXTURE_DENOMINATOR_DRIFT")
    if body["qualification"] is not False or body["frozen"] is not False or body["canonical_runtime_execution_status"] != "NOT_RUN":
        raise ValueError("GOLDEN_BUILD_QUALIFICATION_LAUNDERING")
    by_id = {vector["id"]: vector for vector in fixtures["vectors"]}
    selected = set()
    for vector in body["vectors"][count:]:
        context = vector["input"]
        if context["fixture_file_raw_digest"] != fixture_report["raw_digest"]:
            raise ValueError("GOLDEN_FIXTURE_RAW_PIN_DRIFT")
        fixture = by_id.get(context["fixture_id"])
        if fixture is None or context["fixture_id"] in selected:
            raise ValueError("GOLDEN_FIXTURE_MEMBERSHIP_CONFLICT")
        selected.add(context["fixture_id"])
        if context["fixture_input_cjson_sha256"] != hashlib.sha256(canonical(fixture["input"])).hexdigest():
            raise ValueError("GOLDEN_FIXTURE_INPUT_DRIFT")
        if context["schema_id"] != fixture["schema_id"] or context["schema_raw_digest"] != fixture["schema_raw_digest"]:
            raise ValueError("GOLDEN_FIXTURE_SCHEMA_DRIFT")
        if context["dependency_closure"] != fixture["dependency_closure"]:
            raise ValueError("GOLDEN_FIXTURE_DEPENDENCY_DRIFT")
        if vector["expected"] != {"schema_result": fixture["expected"]}:
            raise ValueError("GOLDEN_FIXTURE_EXPECTATION_DRIFT")
    if selected != set(by_id):
        raise ValueError("GOLDEN_FIXTURE_OMISSION")


def main():
    preserve()
    predecessor_path = BASE / "candidate/BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json"
    fixture_report_path = OUT / "BUILD_SCHEMA_FIXTURE_READBACK.json"
    fixture_report = read(fixture_report_path)
    fixture_path = ROOT / fixture_report["file"]
    paths = [predecessor_path, fixture_report_path, fixture_path, OUT / "BUILD_TIME_CANDIDATE_READBACK.json",
             OUT / "design/VERSION_IMPACT_PLAN.json", ROOT / "docs/R5_4_2/R5_4_2_SEMANTIC_CLOSURE_GRAPH.json",
             ROOT / "docs/R5_4_2/OWNER_R5_4_2_SEMANTIC_CLOSURE_APPROVAL.json",
             OUT / "tools/build_schema_fixtures.py", OUT / "tools/execution.py", Path(__file__)]
    before = {path.relative_to(ROOT).as_posix(): digest(path) for path in paths}
    if digest(fixture_path) != fixture_report["raw_digest"] or fixture_path.stat().st_size != fixture_report["byte_length"]:
        raise ValueError("GOLDEN_BUILD_FIXTURE_READBACK_DRIFT")
    for name, expected in fixture_report["sources"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("STALE_GOLDEN_BUILD_FIXTURE_SOURCE: " + name)
    approval = read(paths[6])
    graph_entry = next(entry for entry in approval["approved_artifacts"] if entry["file"] == paths[5].relative_to(ROOT).as_posix())
    if digest(paths[5]) != graph_entry["raw_digest"] or paths[5].stat().st_size != graph_entry["bytes"]:
        raise ValueError("APPROVED_GOLDEN_DESIGN_SOURCE_DRIFT")
    predecessor, fixtures = read(predecessor_path), read(fixture_path)
    mapping = read(paths[4])["mapping"]
    body = construct(predecessor, fixtures, fixture_report, read(paths[5])["vector_designs"], mapping)
    body["predecessor_vector_raw_digest"] = digest(predecessor_path)
    raw = canonical(body) + b"\n"
    raw_digest = hashlib.sha256(raw).hexdigest()
    path = OUT / "golden_build_candidate" / raw_digest / "BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4_2.json"
    if path.exists() and path.read_bytes() != raw:
        raise ValueError("EXISTING_GOLDEN_BUILD_CANDIDATE_DRIFT")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(raw)
    if digest(path) != raw_digest or path.stat().st_size != len(raw):
        raise ValueError("GOLDEN_BUILD_READBACK_DRIFT")
    verify_structure(read(path), predecessor, fixtures, fixture_report)
    after = {input_path.relative_to(ROOT).as_posix(): digest(input_path) for input_path in paths}
    if before != after:
        raise ValueError("GOLDEN_BUILD_INPUT_DRIFT")
    preserve()
    write("GOLDEN_BUILD_CANDIDATE_READBACK.json", {
        "file": path.relative_to(ROOT).as_posix(), "raw_digest": raw_digest, "byte_length": len(raw),
        "sources": before, "input_drift": [], "status": body["status"],
        "inherited_vectors": len(predecessor["vectors"]), "exact_schema_vectors": len(fixtures["vectors"]),
        "unexecuted_canonical_designs": len(body["canonical_acceptance_designs"]),
        "qualification": False, "frozen": False, "canonical_runtime": "NOT_RUN", "NF02": "OPEN"})
    print(json.dumps({"golden_build_readback": "PASS", "inherited_vectors": len(predecessor["vectors"]),
                      "schema_vectors": len(fixtures["vectors"]), "unexecuted_canonical_designs": len(body["canonical_acceptance_designs"])}))


if __name__ == "__main__":
    main()

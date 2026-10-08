"""Retain and replay exact offline build-schema fixtures; never qualify runtime.

Generated structural controls are separated from source-authored branch answers.
Every fixture carries its schema and transitive dependency raw identities.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from build_time_candidates import verify_readback
from execution import OUT, ROOT, canonical, digest, preserve, read, write
from profile_design_audit import fixture


def offline_catalog(report):
    directory = ROOT / report["directory"]
    verify_readback(directory, report["entries"])
    schemas = {entry["$id"]: read(directory / entry["file"]) for entry in report["entries"]}
    registry = Registry().with_resources((key, Resource.from_contents(schema)) for key, schema in schemas.items())
    return schemas, registry


def replay(vector, schema, entry, registry):
    if vector["schema_id"] != entry["$id"] or vector["schema_raw_digest"] != entry["raw_digest"]:
        raise ValueError("FIXTURE_SCHEMA_BINDING_DRIFT")
    if vector["dependency_closure"] != entry["dependency_closure"]:
        raise ValueError("FIXTURE_DEPENDENCY_BINDING_DRIFT")
    if vector["expected"] not in ("ACCEPT", "REJECT"):
        raise ValueError("FIXTURE_EXPECTATION_UNKNOWN")
    actual = Draft202012Validator(schema, registry=registry).is_valid(vector["input"])
    if actual != (vector["expected"] == "ACCEPT"):
        raise ValueError("BUILD_SCHEMA_FIXTURE_MISMATCH: " + vector["id"])


def construct(report, branches):
    schemas, registry = offline_catalog(report)
    branch_ids = [(answer["schema_key"], answer["case"]) for answer in branches]
    if len(branch_ids) != len(set(branch_ids)):
        raise ValueError("DUPLICATE_SOURCE_BRANCH_ANSWER")
    for answer in branches:
        if "BDB_SCHEMA_REGISTRY::" + answer["schema_key"] not in schemas:
            raise ValueError("SOURCE_BRANCH_SCHEMA_NOT_BOUND")
    vectors = []
    for entry in report["entries"]:
        schema = schemas[entry["$id"]]
        validator = Draft202012Validator(schema, registry=registry)
        valid = fixture(schema, schema.get("$defs", {}), external=schemas)
        answers = [answer for answer in branches
                   if "BDB_SCHEMA_REGISTRY::" + answer["schema_key"] == entry["$id"]]
        if not validator.is_valid(valid):
            valid = next((copy.deepcopy(answer["input"]) for answer in answers
                          if answer["expected"] == "ACCEPT" and validator.is_valid(answer["input"])), None)
            if valid is None:
                raise ValueError("NO_VALID_BUILD_SCHEMA_FIXTURE: " + entry["$id"])

        def add(label, body, expected, basis):
            vector = {"id": entry["$id"] + "::" + label, "schema_id": entry["$id"],
                      "schema_raw_digest": entry["raw_digest"], "dependency_closure": entry["dependency_closure"],
                      "input": copy.deepcopy(body), "expected": expected, "expectation_basis": basis,
                      "canonical_runtime": "NOT_RUN"}
            replay(vector, schema, entry, registry)
            vectors.append(vector)

        add("EXACT_STRUCTURAL_INSTANCE", valid, "ACCEPT", "GENERATED_FROM_DECLARED_SCHEMA_ONLY")
        if isinstance(valid, dict):
            add("UNDECLARED_AUTHORITY_FIELD", {**valid, "unqualified_caller_trusted": True}, "REJECT",
                "CLOSED_OBJECT_OR_EXACT_CONST")
            for field in schema.get("required", []):
                missing = copy.deepcopy(valid)
                del missing[field]
                add("MISSING_REQUIRED_" + field, missing, "REJECT", "DECLARED_REQUIRED_FIELD")
        for answer in answers:
            add("SOURCE_BRANCH_" + answer["case"], answer["input"], answer["expected"],
                "RETAINED_CONDITIONAL_GRAMMAR_KNOWN_ANSWER")
    identifiers = [vector["id"] for vector in vectors]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("DUPLICATE_BUILD_FIXTURE_ID")
    return vectors


def main():
    preserve()
    paths = [OUT / "BUILD_TIME_CANDIDATE_READBACK.json",
             OUT / "design/CONDITIONAL_GRAMMAR_KNOWN_ANSWERS.json", Path(__file__),
             OUT / "tools/build_time_candidates.py", OUT / "tools/profile_design_audit.py", OUT / "tools/execution.py"]
    before = {path.relative_to(ROOT).as_posix(): digest(path) for path in paths}
    report = read(paths[0])
    branches = read(paths[1])["vectors"]
    vectors = construct(report, branches)
    body = {"vector_set_id": "BDB-R5-4-2-BUILD-SCHEMA-STRUCTURAL-VECTORS",
            "schema_build_digest": report["build_digest"], "schema_count": len(report["entries"]),
            "sources": before, "vectors": vectors, "qualification": False,
            "scope": "Exact offline executable schema syntax only; no producer authority, accepted DAG or substantive truth"}
    raw = canonical(body) + b"\n"
    raw_digest = hashlib.sha256(raw).hexdigest()
    directory = OUT / "build_schema_fixtures" / raw_digest
    path = directory / "BUILD_SCHEMA_KNOWN_ANSWERS.json"
    if path.exists() and path.read_bytes() != raw:
        raise ValueError("RETAINED_BUILD_FIXTURES_DRIFT")
    directory.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(raw)
    if digest(path) != raw_digest or path.stat().st_size != len(raw):
        raise ValueError("BUILD_FIXTURE_READBACK_DRIFT")
    retained = read(path)
    schemas, registry = offline_catalog(report)
    entries = {entry["$id"]: entry for entry in report["entries"]}
    for vector in retained["vectors"]:
        replay(vector, schemas[vector["schema_id"]], entries[vector["schema_id"]], registry)
    if digest(path) != raw_digest:
        raise ValueError("BUILD_FIXTURE_DRIFT_DURING_REPLAY")
    offline_catalog(report)
    after = {input_path.relative_to(ROOT).as_posix(): digest(input_path) for input_path in paths}
    if before != after:
        raise ValueError("BUILD_FIXTURE_INPUT_DRIFT")
    preserve()
    write("BUILD_SCHEMA_FIXTURE_READBACK.json", {
        "file": path.relative_to(ROOT).as_posix(), "raw_digest": raw_digest, "byte_length": len(raw),
        "schema_build_digest": report["build_digest"], "schemas_checked": len(entries),
        "vectors_replayed": len(vectors), "source_branches": len(branches), "sources": before,
        "status": "EXACT_OFFLINE_SCHEMA_FIXTURES_PASS_NOT_QUALIFIED", "input_drift": [],
        "qualification": False, "frozen": False, "canonical_runtime": "NOT_RUN", "NF02": "OPEN"})
    print(json.dumps({"build_schema_fixtures": "PASS", "schemas": len(entries), "vectors": len(vectors),
                      "qualification": False}))


if __name__ == "__main__":
    main()

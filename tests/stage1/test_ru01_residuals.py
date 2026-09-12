"""RU01 residual anti-bypass and producer-inventory controls.

These tests inspect producer call-sites, not just Registry rows or the central
CanonicalObject implementation. A future helper that emits a
BDB-OBJECT-DIGEST-1 ref while hashing bare CJSON must fail qualification.
"""
from __future__ import annotations

import ast
from pathlib import Path

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.orchestration.stages import initial_stage_specs


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "bdb_audit"
PROFILE = "BDB-OBJECT-DIGEST-1"


def test_d09_empty_or_self_asserted_context_never_qualifies_authority_layers() -> None:
    api = AuditOperationApi()
    spec = initial_stage_specs()[0]
    artifact = {"kind": "stage_spec", "version": "1", **spec.body()}
    contexts = (
        {},
        {"unrelated": "value"},
        {"qualified_layers": ["L5"]},
        {"qualified_layers": ["L5", "L6", "L7"]},
        {"stage_key": "E1", "qualified_layers": ["L5"]},
    )
    for context in contexts:
        result = api.validate_artifact(artifact, context=context)
        assert result["admission_status"] == "NOT_ADMITTED"
        assert result["admissible"] is False
        assert "L5" in result["missing_validation_layers"]
        assert not ({"L5", "L6", "L7"} & set(result["executed_validation_layers"]))


def _identity_bearing_scopes(tree: ast.AST, source: str):
    for node in ast.walk(tree):
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        segment = ast.get_source_segment(source, node) or ""
        if PROFILE in segment:
            yield node, segment


def test_d12_actual_producer_call_sites_do_not_use_bare_cjson_sha256() -> None:
    inspected: list[str] = []
    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node, segment in _identity_bearing_scopes(tree, source):
            location = f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', '?')}:{getattr(node, 'name', type(node).__name__)}"
            inspected.append(location)
            uses_sha = "hashlib.sha256" in segment or "sha256(" in segment
            uses_cjson = "canonical_bytes" in segment
            if not (uses_sha and uses_cjson):
                continue
            canonical_delegate = (
                "BDB2/" in segment
                or "CanonicalObject(" in segment
                or "object_digest(" in segment
            )
            if not canonical_delegate:
                violations.append(location)
    assert inspected, "Producer inventory found no BDB-OBJECT-DIGEST-1 call-sites"
    assert not violations, (
        "Authority-bearing producers advertise BDB-OBJECT-DIGEST-1 while using "
        "bare SHA256(CJSON): " + ", ".join(violations)
    )

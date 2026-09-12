"""RU01 residual anti-bypass and producer-inventory controls.

The D12 inventory is intentionally scoped to canonical kinds frozen in the
ContractRegistry. Proposal/test DTOs with implementation-local identities are
not silently promoted to foundation authority by this control.
"""
from __future__ import annotations

import ast
from pathlib import Path

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.registry import ContractRegistry
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


def _literal_ref_kinds(node: ast.AST) -> set[str]:
    """Return literal kind values from dicts advertising the canonical profile."""
    kinds: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Dict):
            continue
        pairs: dict[str, object] = {}
        for key, value in zip(child.keys, child.values):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if isinstance(value, ast.Constant):
                    pairs[key.value] = value.value
        if pairs.get("digest_profile") == PROFILE and isinstance(pairs.get("kind"), str):
            kinds.add(str(pairs["kind"]))
    return kinds


def test_d12_registered_canonical_producer_scopes_do_not_use_bare_cjson_sha256() -> None:
    """Mechanically inspect call-sites that advertise a registered canonical kind."""
    reg = ContractRegistry()
    registered = {kind for kind, _version in reg._contracts}
    inspected: list[str] = []
    violations: list[str] = []

    for path in sorted(SRC.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        # A class is the useful scope because the ref property and digest property
        # are usually separate methods. Free functions are checked independently.
        for node in ast.walk(tree):
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            ref_kinds = _literal_ref_kinds(node) & registered
            if not ref_kinds:
                continue
            segment = ast.get_source_segment(source, node) or ""
            location = f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', '?')}:{getattr(node, 'name', type(node).__name__)}"
            inspected.append(location + ":" + ",".join(sorted(ref_kinds)))
            uses_sha_cjson = ("hashlib.sha256" in segment or "sha256(" in segment) and "canonical_bytes" in segment
            if not uses_sha_cjson:
                continue
            canonical_delegate = "BDB2/" in segment or "CanonicalObject(" in segment or "object_digest(" in segment
            if not canonical_delegate:
                violations.append(location + ":" + ",".join(sorted(ref_kinds)))

    assert inspected, "Producer inventory found no registered BDB-OBJECT-DIGEST-1 call-sites"
    assert not violations, (
        "Registered canonical producers advertise BDB-OBJECT-DIGEST-1 while using "
        "bare SHA256(CJSON): " + ", ".join(violations)
    )

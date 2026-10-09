"""Detect current runtime divergence; never report it as a qualification PASS."""

import sys

from execution import OUT, ROOT, digest, write

sys.path.insert(0, str(ROOT / "src"))

from bdb_audit.core.errors import ValidationError  # noqa: E402
from bdb_audit.history import closure  # noqa: E402


def main():
    assert ROOT / "src/bdb_audit/history/closure.py" == __import__("pathlib").Path(closure.__file__)
    nodes = [closure.ClosureNode("cmd", "command_envelope", "c", "a" * 64),
             closure.ClosureNode("approval", "approval_decision", "a", "b" * 64)]
    expected = [n.node_id for n in sorted(nodes, key=lambda n: (n.kind, n.logical_id, n.revision_digest))]
    observed = closure.canonical_order(nodes)
    assert expected == ["approval", "cmd"]
    fixed = observed == expected
    assert fixed or observed == ["cmd", "approval"], "Unexpected ordering"
    try:
        closure.canonical_order(nodes, expected=expected)
    except ValidationError as exc:
        code = exc.code
    else:
        assert fixed
        code = None
    assert fixed or code == "FUTURE_CONTENT_REF_OR_NON_TOPOLOGICAL_CLOSURE"
    source = ROOT / "F1_QUALIFICATION/inputs/BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS.md"
    write("design/CLOSURE_TIEBREAK_RUNTIME_CURRENT.json" if fixed else "design/CLOSURE_TIEBREAK_RUNTIME_DIVERGENCE.json", {
        "status": "TARGETED_RUNTIME_CORRECTION_PASS" if fixed else "CURRENT_IMPLEMENTATION_NONCOMPLIANT", "normative_sections": ["2", "15.2"],
        "normative_source_raw_digest": digest(source), "implementation_raw_digest": digest(ROOT / "src/bdb_audit/history/closure.py"),
        "normative_tie_break": ["kind", "logical_id_or_empty", "revision_digest"],
        "expected": expected, "observed": observed, "rejected_normative_sequence_code": code,
        "scope": "Actual canonical_order on two prepared independent nodes; no accepted instance or qualification proof",
        "required_fix": "Remove command-envelope priority from Kahn ready-node key in successor implementation; preserve typed/order-only edges",
        "qualification": False, "NF02": "OPEN"})
    print("Targeted runtime correction PASS; qualification NOT_PROVEN" if fixed else "DETECTED current runtime tie-break divergence; qualification NOT_PROVEN")


if __name__ == "__main__":
    main()

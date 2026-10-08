"""Source-bound successor delta and regression proof, before activation."""

import difflib
import sys
import types

from execution import OUT, ROOT, digest, write

sys.path.insert(0, str(ROOT / "src"))

from bdb_audit.core.errors import ValidationError  # noqa: E402
from bdb_audit.history import closure  # noqa: E402


def main():
    source_path = ROOT / "src/bdb_audit/history/closure.py"
    source = source_path.read_bytes().decode("utf-8")
    old = ('        is_cmd = 0 if n.kind == "command_envelope" else 1\n'
           '        return (is_cmd, n.kind, n.logical_id or "", n.revision_digest or "", node_id)')
    new = '        return (n.kind, n.logical_id or "", n.revision_digest or "", node_id)'
    if "\r\n" in source:
        old = old.replace("\n", "\r\n")
    applied = source.count(old) == 0 and source.count(new) == 1
    assert applied or source.count(old) == 1
    modified = source if applied else source.replace(old, new)
    patch = "".join(difflib.unified_diff(source.splitlines(True), modified.splitlines(True),
                                       fromfile="a/src/bdb_audit/history/closure.py",
                                       tofile="b/src/bdb_audit/history/closure.py"))
    patch_path = OUT / "design/CLOSURE_TIEBREAK_SUCCESSOR.patch"
    if not applied:
        patch_path.write_text(patch, encoding="utf-8", newline="")
    module = types.ModuleType("bdb_audit.history._successor_closure_probe")
    module.__package__ = "bdb_audit.history"
    sys.modules[module.__name__] = module
    try:
        exec(compile(modified, str(patch_path), "exec"), module.__dict__)
        Node = module.ClosureNode
        nodes = [Node("cmd", "command_envelope", "c", "a" * 64),
                 Node("approval", "approval_decision", "a", "b" * 64)]
        controls = []
        for ordered in (nodes, list(reversed(nodes))):
            assert module.canonical_order(ordered, expected=["approval", "cmd"]) == ["approval", "cmd"]
            controls.append("independent-kind-tie-break-input-order-invariant")
        tied = [Node("later", "approval_decision", "b", "a" * 64),
                Node("first", "approval_decision", "a", "b" * 64),
                Node("first-digest", "approval_decision", "a", "a" * 64)]
        assert module.canonical_order(tied) == ["first-digest", "first", "later"]
        controls.append("logical-id-then-digest")
        linked = [Node("cmd", "command_envelope", "c", "a" * 64),
                  Node("approval", "approval_decision", "a", "b" * 64, depends_on=("cmd",))]
        assert module.canonical_order(linked) == ["cmd", "approval"]
        controls.append("typed-dependency-outranks-tie-break")
        for bad, code in ((["cmd", "approval"], "FUTURE_CONTENT_REF_OR_NON_TOPOLOGICAL_CLOSURE"),):
            try:
                module.canonical_order(nodes, expected=bad)
            except ValidationError as exc:
                assert exc.code == code
            else:
                raise AssertionError("Noncanonical sequence accepted")
            controls.append("command-first-independent-sequence-rejected")
        cyclic = [Node("cmd", "command_envelope", depends_on=("approval",)),
                  Node("approval", "approval_decision", depends_on=("cmd",))]
        try:
            module.canonical_order(cyclic)
        except ValidationError as exc:
            assert exc.code == "CONTENT_REFERENCE_CYCLE"
        else:
            raise AssertionError("Cycle accepted")
        controls.append("cycle-remains-rejected")
        original_nodes = [closure.ClosureNode(n.node_id, n.kind, n.logical_id, n.revision_digest) for n in nodes]
        assert closure.canonical_order(original_nodes) == (["approval", "cmd"] if applied else ["cmd", "approval"])
        write("design/CLOSURE_TIEBREAK_SUCCESSOR_CONTROLS.json", {
            "status": "SOURCE_BOUND_SUCCESSOR_DELTA_CONTROLS_PASS", "controls": controls,
            "source_raw_digest": digest(source_path), "patch_raw_digest": digest(patch_path),
            "implementation_edited": applied, "current_runtime": "TARGETED_CORRECTION_PASS" if applied else "NONCOMPLIANT",
            "qualification": False, "full_accepted_instance_DAG": "NOT_PROVEN",
            "remaining": "Apply in successor implementation phase, run affected history/bootstrap/Golden/build checks and fresh qualification; no historical proof reuse"})
    finally:
        del sys.modules[module.__name__]
    print(f"PASS {len(controls)} source-bound successor ordering regressions; current runtime unchanged")


if __name__ == "__main__":
    main()

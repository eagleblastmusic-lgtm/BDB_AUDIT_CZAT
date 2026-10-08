"""Data 15.2: ready-node tie-break cannot introduce command-first edges."""

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.history.closure import ClosureNode, canonical_order


@pytest.mark.parametrize("reverse", [False, True])
def test_independent_command_uses_normative_kind_order(reverse):
    nodes = [ClosureNode("cmd", "command_envelope", "c", "a" * 64),
             ClosureNode("approval", "approval_decision", "a", "b" * 64)]
    if reverse:
        nodes.reverse()
    assert canonical_order(nodes, expected=["approval", "cmd"]) == ["approval", "cmd"]
    with pytest.raises(ValidationError, match="FUTURE_CONTENT_REF_OR_NON_TOPOLOGICAL_CLOSURE"):
        canonical_order(nodes, expected=["cmd", "approval"])


def test_typed_dependency_still_precedes_kind_order():
    nodes = [ClosureNode("cmd", "command_envelope", "c", "a" * 64),
             ClosureNode("approval", "approval_decision", "a", "b" * 64, depends_on=("cmd",))]
    assert canonical_order(nodes) == ["cmd", "approval"]

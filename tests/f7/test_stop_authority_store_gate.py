"""Authority-boundary regressions for canonical STOP acceptance.

The pure evaluator may inspect non-authoritative preview inputs.  A StopInput
that enters canonical accepted history is stricter: its derived proof summary
must equal the projection of the parent accepted cut, and rejection must happen
before object durability.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bdb_audit.coordinator.reference_slice import run_foundation_reference_slice
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.objects import CanonicalObject
from bdb_audit.stop.input_builder import StopInputBuilder


def _prepared_final_stop(tmp_path: Path, name: str):
    ctx = run_foundation_reference_slice(tmp_path / f"{name}.sqlite", stop_at_seq=9)
    stop_input = StopInputBuilder.build_from_store(
        ctx["store"],
        evaluation_context="FINAL_POST_E5",
    )
    snapshot_obj = getattr(stop_input, "_snapshot_obj")
    return ctx, stop_input, snapshot_obj


def test_authority_accepts_builder_projected_stop_input(tmp_path: Path) -> None:
    ctx, stop_input, snapshot_obj = _prepared_final_stop(tmp_path, "valid")
    command = ctx["next_cmd"](ctx["head_ref"])

    result = ctx["coordinator"].accept(
        command,
        immutable_objects=(snapshot_obj, stop_input.as_object()),
        expected_head=ctx["head"],
    )

    assert result.head.commit_seq == ctx["head"].commit_seq + 1
    assert ctx["store"].object_record(stop_input.as_object().digest) is not None


def test_authority_rejects_forged_stop_proof_before_durability(tmp_path: Path) -> None:
    ctx, stop_input, snapshot_obj = _prepared_final_stop(tmp_path, "forged")
    forged_body = stop_input.body()
    forged_summary = dict(forged_body["unknown_blocked_summary"])
    assert forged_summary["challenger_binding_verified"] is False
    forged_summary["challenger_binding_verified"] = True
    forged_body["unknown_blocked_summary"] = forged_summary

    forged = CanonicalObject(
        "stop_input",
        forged_body,
        logical_id=stop_input.stop_input_id,
    )
    command = ctx["next_cmd"](ctx["head_ref"])

    with pytest.raises(ValidationError, match="STOP_DERIVED_SUMMARY_MISMATCH"):
        ctx["coordinator"].accept(
            command,
            immutable_objects=(snapshot_obj, forged),
            expected_head=ctx["head"],
        )

    assert ctx["store"].head() == ctx["head"]
    assert ctx["store"].object_record(forged.digest) is None

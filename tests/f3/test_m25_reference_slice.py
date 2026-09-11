"""Tests for WP-F3-09 / PR-028: Full Foundation Reference Slice E2 legacy -> v2 E3."""
import sqlite3
from pathlib import Path

import pytest

from bdb_audit.coordinator import run_foundation_reference_slice

ROOT = Path(__file__).resolve().parents[2]


def _fresh_db(name):
    path = ROOT / name
    if path.exists():
        con = sqlite3.connect(path)
        con.executescript(
            "DROP TABLE IF EXISTS immutable_objects; "
            "DROP TABLE IF EXISTS commits; "
            "DROP TABLE IF EXISTS receipts; "
            "DROP TABLE IF EXISTS accepted_head; "
            "DROP TABLE IF EXISTS command_index;"
        )
        con.close()
    return path


def test_foundation_reference_slice_end_to_end():
    """Execute complete Foundation Reference Slice from empty history to intermediate STOP."""
    db_path = _fresh_db("F3_REFERENCE_SLICE_TEST.sqlite")
    result = run_foundation_reference_slice(db_path)

    # 1. 10 atomic commits executed
    assert result["commit_count"] == 10
    assert result["head_commit"].commit_seq == 10

    # 2. StageCompletion is recorded and valid
    sc = result["stage_completion"]
    assert sc.completion_predicate_result == "STAGE_COMPLETED"
    assert sc.stage_spec_ref["revision_digest"] is not None

    # 3. Intermediate STOP evaluation
    stop_eval = result["stop_evaluation"]
    assert stop_eval.continuation_decision == "CONTINUE_REQUIRED"
    assert stop_eval.release_readiness == "TECHNICALLY_NOT_READY"
    assert stop_eval.assurance_level == "INSUFFICIENT"
    assert "REQUIRED_STAGES_PENDING" in stop_eval.reason_codes
    assert "INSUFFICIENT_DATA" in stop_eval.reason_codes

    # 4. Must NOT produce global PASS or release readiness
    assert stop_eval.continuation_decision != "PASS"
    assert stop_eval.release_readiness != "READY"

    # 5. Derived contribution projection
    proj = result["contribution_projection"]
    assert proj.is_projection is True
    assert proj.reveal_order_marginal_contribution_is_not_objective_value is True
    assert len(proj.producer_contributions) == 1
    p = list(proj.producer_contributions.values())[0]
    assert p.producer_id == "attempt_e3_fixture"
    assert p.unique_contribution_count == 1
    assert p.leave_one_out_loss == 1


def test_foundation_reference_slice_determinism():
    """Verify that repeating reference slice on clean store yields exact byte-for-byte identical digests."""
    db_a = _fresh_db("F3_REF_SLICE_A.sqlite")
    db_b = _fresh_db("F3_REF_SLICE_B.sqlite")

    res_a = run_foundation_reference_slice(db_a)
    res_b = run_foundation_reference_slice(db_b)

    assert res_a["head_commit"].commit_digest == res_b["head_commit"].commit_digest
    assert res_a["stage_completion"].as_object().digest == res_b["stage_completion"].as_object().digest
    assert res_a["stop_evaluation"].as_object().digest == res_b["stop_evaluation"].as_object().digest
    assert res_a["contribution_projection"].to_bytes() == res_b["contribution_projection"].to_bytes()

"""Targeted regressions for PR-028 (Foundation Reference Slice & STOP Snapshot Binding).

Mechanically validates:
A. continuation_budget_authorization_ref:
   - None is legal and omitted from body;
   - real accepted approval_decision is legal;
   - dangling approval_decision is rejected;
   - wrong-kind ref is rejected.

B. stop_input_snapshot_ref:
   - valid same-commit Snapshot -> PASS;
   - dangling snapshot -> reject;
   - wrong kind -> reject;
   - stale/wrong as_of_head -> STOP_SNAPSHOT_BINDING_CONFLICT;
   - missing projection input -> STOP_SNAPSHOT_BINDING_CONFLICT;
   - extra projection input -> STOP_SNAPSHOT_BINDING_CONFLICT.

C. schema binding:
   - snapshot is bound before first acceptance;
   - continuation_budget_authorization_ref remains optional;
   - lack of snapshot binding cannot fail-open.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.core.registry import ContractRegistry
from bdb_audit.history.objects import CanonicalObject
from bdb_audit.schemas.foundation import foundation_schema_bindings, executable_schema
from bdb_audit.schemas.stop import stop_schema
from bdb_audit.stop import (
    StopInput,
    Snapshot,
    evaluate_stop,
    validate_stop_snapshot_binding,
)
from bdb_audit.coordinator import run_foundation_reference_slice
from bdb_audit.coordinator.reference_slice import _external_ref, _ref_for

ROOT = Path(__file__).resolve().parents[2]


def _fresh_db(name: str) -> Path:
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


def _build_seq10_elements(ctx: dict):
    """Build baseline valid seq10 objects given seq9 context."""
    source_gen = ctx["source_gen"]
    inv_rev = ctx["inv_rev"]
    cov_ob = ctx["cov_ob"]
    cov_qual = ctx["cov_qual"]
    stage_comp = ctx["stage_comp"]
    stage_spec_obj = ctx["stage_spec_obj"]
    head_cut = ctx["head_cut"]
    det_id = ctx["det_id"]
    campaign_id = ctx["campaign_id"]

    e4_spec = _external_ref("stage_spec", "stage_spec_e4", ref_class="HISTORY_CONTEXT_BINDING")
    e5_spec = _external_ref("stage_spec", "stage_spec_e5", ref_class="HISTORY_CONTEXT_BINDING")

    direct_refs = [
        _ref_for("stop_input", "source_generation_ref", source_gen),
        _ref_for("stop_input", "inventory_revision_ref", inv_rev),
        _ref_for("stop_input", "mandatory_obligation_refs", cov_ob),
        _ref_for("stop_input", "current_obligation_qualification_refs", cov_qual),
        _ref_for("stop_input", "completed_stage_refs", stage_comp),
        _ref_for("stop_input", "required_stage_spec_refs", stage_spec_obj),
        e4_spec,
        e5_spec,
    ]

    snapshot = Snapshot(
        snapshot_id=det_id("snapshot"),
        snapshot_type="STOP_INPUT_STATE_CAPTURE",
        as_of_head=head_cut,
        projection_code_revision="BDB_V2_SNAPSHOT_PROJECTION_1",
        projection_input_refs=direct_refs,
        snapshot_artifact_ref=_external_ref("raw_artifact_ref", "snap_artifact", ref_class="CONTENT_OR_PRIOR"),
    )

    stop_input = StopInput(
        stop_input_id=det_id("stop_input"),
        campaign_id=campaign_id,
        source_generation_ref=_ref_for("stop_input", "source_generation_ref", source_gen),
        input_history_cut=head_cut,
        evaluation_context="INTERMEDIATE",
        governing_policy_ref=_external_ref("policy_revision", "gov_policy", ref_class="HISTORY_CONTEXT_BINDING"),
        policy_spec_refs=[_external_ref("spec_revision", "stop_spec", ref_class="HISTORY_CONTEXT_BINDING")],
        evaluator_revision_ref=_external_ref("spec_revision", "eval_rev", ref_class="HISTORY_CONTEXT_BINDING"),
        required_stage_set_ref=_external_ref("external_profile_ref", "stg_set", ref_class="HISTORY_CONTEXT_BINDING"),
        required_stage_spec_refs=[_ref_for("stop_input", "required_stage_spec_refs", stage_spec_obj), e4_spec, e5_spec],
        completed_stage_refs=[_ref_for("stop_input", "completed_stage_refs", stage_comp)],
        pending_required_stage_refs=[e4_spec, e5_spec],
        stop_input_snapshot_ref=_ref_for("stop_input", "stop_input_snapshot_ref", snapshot),
        inventory_revision_ref=_ref_for("stop_input", "inventory_revision_ref", inv_rev),
        mandatory_obligation_refs=[_ref_for("stop_input", "mandatory_obligation_refs", cov_ob)],
        current_obligation_qualification_refs=[_ref_for("stop_input", "current_obligation_qualification_refs", cov_qual)],
        evidence_invalidation_refs=[],
        contradiction_refs=[],
        residual_risk_refs=[],
        evidence_invalidation_state={"invalidated_count": 0},
        release_policy_ref=_external_ref("policy_revision", "rel_policy", ref_class="HISTORY_CONTEXT_BINDING"),
        effort_profile_ref=_external_ref("external_profile_ref", "effort_profile", ref_class="HISTORY_CONTEXT_BINDING"),
        effort_results_ref=_external_ref("registered_immutable_object", "effort_results", ref_class="CONTENT_OR_PRIOR"),
        continuation_budget_authorization_ref=None,
        unknown_blocked_summary={"unknown_surfaces_count": 0, "is_blocked": False},
    )

    stop_eval = evaluate_stop(stop_input, stop_evaluation_id=det_id("stop_evaluation"))
    return snapshot, stop_input, stop_eval, direct_refs


# =============================================================================
# A. continuation_budget_authorization_ref
# =============================================================================

def test_continuation_budget_authorization_none_legal_and_omitted():
    """Verify that None is legal and omitted from serialized StopInput body."""
    db_path = _fresh_db("PR028_BUDGET_NONE.sqlite")
    ctx = run_foundation_reference_slice(db_path, stop_at_seq=9)
    snapshot, stop_input, stop_eval, _ = _build_seq10_elements(ctx)

    assert stop_input.continuation_budget_authorization_ref is None
    body = stop_input.body()
    assert "continuation_budget_authorization_ref" not in body

    # Acceptance in coordinator must succeed
    seq10_objects = (snapshot.as_object(), stop_input.as_object(), stop_eval.as_object())
    commit_10 = ctx["coordinator"].accept(
        ctx["next_cmd"](ctx["head_ref"]),
        immutable_objects=seq10_objects,
        expected_head=ctx["head"],
    )
    assert commit_10.commit.commit_seq == 10


def test_continuation_budget_authorization_real_accepted_legal():
    """Verify that a real accepted approval_decision in the closure is accepted."""
    db_path = _fresh_db("PR028_BUDGET_REAL.sqlite")
    ctx = run_foundation_reference_slice(db_path, stop_at_seq=9)
    snapshot, stop_input_base, _, _ = _build_seq10_elements(ctx)
    det_id = ctx["det_id"]

    actor_ref = _external_ref("actor_or_authority_ref", "actor1", ref_class="PRIOR_ACCEPTED_ONLY")
    actor_auth_ref = _external_ref("actor_or_authority_ref", "auth1", ref_class="PRIOR_ACCEPTED_ONLY")
    approval = CanonicalObject("approval_decision", {
        "decision_id": det_id("approval_decision"),
        "decision_type": "CONTINUATION_BUDGET",
        "decision": "APPROVED",
        "actor_ref": actor_ref,
        "actor_authority_ref": actor_auth_ref,
        "input_history_cut": ctx["head_cut"],
        "related_refs": [],
        "reason_codes": ["BUDGET_GRANTED"],
    }, logical_id=det_id("approval_decision"))

    approval_ref = _ref_for("stop_input", "continuation_budget_authorization_ref", approval)

    # Recreate stop_input with real approval_decision
    body_dict = stop_input_base.body()
    body_dict["continuation_budget_authorization_ref"] = approval_ref
    body_dict["stop_input_id"] = det_id("stop_input")

    # StopInput with approval ref
    stop_input = StopInput(
        **{k: v for k, v in body_dict.items() if k != "stop_input_id"},
        stop_input_id=body_dict["stop_input_id"],
    )
    stop_eval = evaluate_stop(stop_input, stop_evaluation_id=det_id("stop_evaluation"))

    seq10_objects = (approval, snapshot.as_object(), stop_input.as_object(), stop_eval.as_object())
    commit_10 = ctx["coordinator"].accept(
        ctx["next_cmd"](ctx["head_ref"]),
        immutable_objects=seq10_objects,
        expected_head=ctx["head"],
    )
    assert commit_10.commit.commit_seq == 10


def test_continuation_budget_authorization_dangling_rejected():
    """Verify that dangling approval_decision (not in closure, not in store) is rejected."""
    db_path = _fresh_db("PR028_BUDGET_DANGLING.sqlite")
    ctx = run_foundation_reference_slice(db_path, stop_at_seq=9)
    snapshot, stop_input_base, _, _ = _build_seq10_elements(ctx)
    det_id = ctx["det_id"]

    dangling_ref = _external_ref("approval_decision", "uncommitted_budget_approval", ref_class="CONTENT_OR_PRIOR")

    body_dict = stop_input_base.body()
    body_dict["continuation_budget_authorization_ref"] = dangling_ref
    body_dict["stop_input_id"] = det_id("stop_input")

    stop_input = StopInput(
        **{k: v for k, v in body_dict.items() if k != "stop_input_id"},
        stop_input_id=body_dict["stop_input_id"],
    )
    stop_eval = evaluate_stop(stop_input, stop_evaluation_id=det_id("stop_evaluation"))

    seq10_objects = (snapshot.as_object(), stop_input.as_object(), stop_eval.as_object())
    with pytest.raises(ValidationError, match="DANGLING_CONTENT_REF"):
        ctx["coordinator"].accept(
            ctx["next_cmd"](ctx["head_ref"]),
            immutable_objects=seq10_objects,
            expected_head=ctx["head"],
        )


def test_continuation_budget_authorization_wrong_kind_rejected():
    """Verify that wrong-kind ref in continuation_budget_authorization_ref is rejected."""
    db_path = _fresh_db("PR028_BUDGET_WRONG_KIND.sqlite")
    ctx = run_foundation_reference_slice(db_path, stop_at_seq=9)
    snapshot, stop_input_base, _, _ = _build_seq10_elements(ctx)
    det_id = ctx["det_id"]

    # stage_comp is already in store but has kind "stage_completion" instead of "approval_decision"
    wrong_kind_ref = _ref_for("stop_input", "completed_stage_refs", ctx["stage_comp"])

    body_dict = stop_input_base.body()
    body_dict["continuation_budget_authorization_ref"] = wrong_kind_ref
    body_dict["stop_input_id"] = det_id("stop_input")

    stop_input = StopInput(
        **{k: v for k, v in body_dict.items() if k != "stop_input_id"},
        stop_input_id=body_dict["stop_input_id"],
    )
    stop_eval = evaluate_stop(stop_input, stop_evaluation_id=det_id("stop_evaluation"))

    seq10_objects = (snapshot.as_object(), stop_input.as_object(), stop_eval.as_object())
    with pytest.raises(ValidationError, match="TYPED_REF_TARGET_MISMATCH"):
        ctx["coordinator"].accept(
            ctx["next_cmd"](ctx["head_ref"]),
            immutable_objects=seq10_objects,
            expected_head=ctx["head"],
        )


# =============================================================================
# B. stop_input_snapshot_ref
# =============================================================================

def test_stop_input_snapshot_valid_same_commit_pass():
    """Verify that valid same-commit Snapshot is accepted."""
    db_path = _fresh_db("PR028_SNAP_PASS.sqlite")
    ctx = run_foundation_reference_slice(db_path, stop_at_seq=9)
    snapshot, stop_input, stop_eval, _ = _build_seq10_elements(ctx)

    seq10_objects = (snapshot.as_object(), stop_input.as_object(), stop_eval.as_object())
    commit_10 = ctx["coordinator"].accept(
        ctx["next_cmd"](ctx["head_ref"]),
        immutable_objects=seq10_objects,
        expected_head=ctx["head"],
    )
    assert commit_10.commit.commit_seq == 10


def test_stop_input_snapshot_dangling_rejected():
    """Verify that dangling snapshot (omitted from closure) is rejected."""
    db_path = _fresh_db("PR028_SNAP_DANGLING.sqlite")
    ctx = run_foundation_reference_slice(db_path, stop_at_seq=9)
    snapshot, stop_input, stop_eval, _ = _build_seq10_elements(ctx)

    # Omit snapshot from seq10_objects
    seq10_objects = (stop_input.as_object(), stop_eval.as_object())
    with pytest.raises(ValidationError, match="DANGLING_CONTENT_REF"):
        ctx["coordinator"].accept(
            ctx["next_cmd"](ctx["head_ref"]),
            immutable_objects=seq10_objects,
            expected_head=ctx["head"],
        )


def test_stop_input_snapshot_wrong_kind_rejected():
    """Verify that wrong kind for stop_input_snapshot_ref is rejected."""
    db_path = _fresh_db("PR028_SNAP_WRONG_KIND.sqlite")
    ctx = run_foundation_reference_slice(db_path, stop_at_seq=9)
    snapshot, stop_input_base, _, _ = _build_seq10_elements(ctx)
    det_id = ctx["det_id"]

    # stage_comp is already in store but has kind "stage_completion" instead of "snapshot"
    wrong_snap_ref = _ref_for("stop_input", "completed_stage_refs", ctx["stage_comp"])

    body_dict = stop_input_base.body()
    body_dict["stop_input_snapshot_ref"] = wrong_snap_ref
    body_dict["stop_input_id"] = det_id("stop_input")

    stop_input = StopInput(
        **{k: v for k, v in body_dict.items() if k != "stop_input_id"},
        stop_input_id=body_dict["stop_input_id"],
    )
    stop_eval = evaluate_stop(stop_input, stop_evaluation_id=det_id("stop_evaluation"))

    seq10_objects = (snapshot.as_object(), stop_input.as_object(), stop_eval.as_object())
    with pytest.raises(ValidationError, match="TYPED_REF_TARGET_MISMATCH"):
        ctx["coordinator"].accept(
            ctx["next_cmd"](ctx["head_ref"]),
            immutable_objects=seq10_objects,
            expected_head=ctx["head"],
        )


def test_stop_input_snapshot_stale_head_conflict():
    """Verify that stale as_of_head raises STOP_SNAPSHOT_BINDING_CONFLICT."""
    db_path = _fresh_db("PR028_SNAP_STALE_HEAD.sqlite")
    ctx = run_foundation_reference_slice(db_path, stop_at_seq=9)
    det_id = ctx["det_id"]
    head_cut = ctx["head_cut"]

    # Stale cut: seq=8 instead of seq=9
    stale_head = dict(head_cut)
    stale_head["accepted_head_seq"] = 8
    stale_head["accepted_head_hash"] = "stale_hash"

    _, stop_input_base, _, direct_refs = _build_seq10_elements(ctx)

    stale_snapshot = Snapshot(
        snapshot_id=det_id("snapshot"),
        snapshot_type="STOP_INPUT_STATE_CAPTURE",
        as_of_head=stale_head,
        projection_code_revision="BDB_V2_SNAPSHOT_PROJECTION_1",
        projection_input_refs=direct_refs,
        snapshot_artifact_ref=_external_ref("raw_artifact_ref", "snap_artifact", ref_class="CONTENT_OR_PRIOR"),
    )

    body_dict = stop_input_base.body()
    body_dict["stop_input_snapshot_ref"] = _ref_for("stop_input", "stop_input_snapshot_ref", stale_snapshot)
    body_dict["stop_input_id"] = det_id("stop_input")

    stop_input = StopInput(
        **{k: v for k, v in body_dict.items() if k != "stop_input_id"},
        stop_input_id=body_dict["stop_input_id"],
    )
    stop_eval = evaluate_stop(stop_input, stop_evaluation_id=det_id("stop_evaluation"))

    seq10_objects = (stale_snapshot.as_object(), stop_input.as_object(), stop_eval.as_object())
    with pytest.raises(ValidationError, match="STOP_SNAPSHOT_BINDING_CONFLICT"):
        ctx["coordinator"].accept(
            ctx["next_cmd"](ctx["head_ref"]),
            immutable_objects=seq10_objects,
            expected_head=ctx["head"],
        )


def test_stop_input_snapshot_missing_projection_input_conflict():
    """Verify that missing a direct projection input raises STOP_SNAPSHOT_BINDING_CONFLICT."""
    db_path = _fresh_db("PR028_SNAP_MISSING_INPUT.sqlite")
    ctx = run_foundation_reference_slice(db_path, stop_at_seq=9)
    det_id = ctx["det_id"]
    head_cut = ctx["head_cut"]

    _, stop_input_base, _, direct_refs = _build_seq10_elements(ctx)

    # Omit one direct ref from snapshot's projection_input_refs
    missing_refs = direct_refs[:-1]

    bad_snapshot = Snapshot(
        snapshot_id=det_id("snapshot"),
        snapshot_type="STOP_INPUT_STATE_CAPTURE",
        as_of_head=head_cut,
        projection_code_revision="BDB_V2_SNAPSHOT_PROJECTION_1",
        projection_input_refs=missing_refs,
        snapshot_artifact_ref=_external_ref("raw_artifact_ref", "snap_artifact", ref_class="CONTENT_OR_PRIOR"),
    )

    body_dict = stop_input_base.body()
    body_dict["stop_input_snapshot_ref"] = _ref_for("stop_input", "stop_input_snapshot_ref", bad_snapshot)
    body_dict["stop_input_id"] = det_id("stop_input")

    stop_input = StopInput(
        **{k: v for k, v in body_dict.items() if k != "stop_input_id"},
        stop_input_id=body_dict["stop_input_id"],
    )
    stop_eval = evaluate_stop(stop_input, stop_evaluation_id=det_id("stop_evaluation"))

    seq10_objects = (bad_snapshot.as_object(), stop_input.as_object(), stop_eval.as_object())
    with pytest.raises(ValidationError, match="STOP_SNAPSHOT_BINDING_CONFLICT"):
        ctx["coordinator"].accept(
            ctx["next_cmd"](ctx["head_ref"]),
            immutable_objects=seq10_objects,
            expected_head=ctx["head"],
        )


def test_stop_input_snapshot_extra_projection_input_conflict():
    """Verify that extra projection input raises STOP_SNAPSHOT_BINDING_CONFLICT."""
    db_path = _fresh_db("PR028_SNAP_EXTRA_INPUT.sqlite")
    ctx = run_foundation_reference_slice(db_path, stop_at_seq=9)
    det_id = ctx["det_id"]
    head_cut = ctx["head_cut"]

    _, stop_input_base, _, direct_refs = _build_seq10_elements(ctx)

    actor_ref = _external_ref("actor_or_authority_ref", "actor1", ref_class="PRIOR_ACCEPTED_ONLY")
    actor_auth_ref = _external_ref("actor_or_authority_ref", "auth1", ref_class="PRIOR_ACCEPTED_ONLY")
    extra_approval = CanonicalObject("approval_decision", {
        "decision_id": det_id("approval_decision"),
        "decision_type": "CONTINUATION_BUDGET",
        "decision": "APPROVED",
        "actor_ref": actor_ref,
        "actor_authority_ref": actor_auth_ref,
        "input_history_cut": ctx["head_cut"],
        "related_refs": [],
        "reason_codes": ["BUDGET_GRANTED"],
    }, logical_id=det_id("approval_decision"))
    extra_ref = _ref_for("stop_input", "continuation_budget_authorization_ref", extra_approval)
    extra_refs = list(direct_refs) + [extra_ref]

    bad_snapshot = Snapshot(
        snapshot_id=det_id("snapshot"),
        snapshot_type="STOP_INPUT_STATE_CAPTURE",
        as_of_head=head_cut,
        projection_code_revision="BDB_V2_SNAPSHOT_PROJECTION_1",
        projection_input_refs=extra_refs,
        snapshot_artifact_ref=_external_ref("raw_artifact_ref", "snap_artifact", ref_class="CONTENT_OR_PRIOR"),
    )

    body_dict = stop_input_base.body()
    body_dict["stop_input_snapshot_ref"] = _ref_for("stop_input", "stop_input_snapshot_ref", bad_snapshot)
    body_dict["stop_input_id"] = det_id("stop_input")

    stop_input = StopInput(
        **{k: v for k, v in body_dict.items() if k != "stop_input_id"},
        stop_input_id=body_dict["stop_input_id"],
    )
    stop_eval = evaluate_stop(stop_input, stop_evaluation_id=det_id("stop_evaluation"))

    seq10_objects = (extra_approval, bad_snapshot.as_object(), stop_input.as_object(), stop_eval.as_object())
    with pytest.raises(ValidationError, match="STOP_SNAPSHOT_BINDING_CONFLICT"):
        ctx["coordinator"].accept(
            ctx["next_cmd"](ctx["head_ref"]),
            immutable_objects=seq10_objects,
            expected_head=ctx["head"],
        )


# =============================================================================
# C. schema binding
# =============================================================================

def test_schema_binding_snapshot_and_budget_optionality():
    """Verify schema binding contracts for snapshot and stop_input optionality."""
    reg = ContractRegistry()
    snap_contract = reg.contract("snapshot")
    assert snap_contract["kind"] == "snapshot"
    assert snap_contract["canonical_role"] == "DERIVED_PROJECTION"

    # Snapshot schema is executable and has required fields
    snap_schema = executable_schema("snapshot")
    assert snap_schema is not None
    assert "snapshot_id" in snap_schema["required"]
    assert "as_of_head" in snap_schema["required"]
    assert "projection_input_refs" in snap_schema["required"]

    # StopInput schema has continuation_budget_authorization_ref as optional
    stop_in_schema = stop_schema("stop_input")
    assert "continuation_budget_authorization_ref" not in stop_in_schema["required"]
    assert "continuation_budget_authorization_ref" in stop_in_schema["properties"]

    # Fail-closed: validate_stop_snapshot_binding cannot fail open on mismatched as_of_head
    fake_input = {"input_history_cut": {"campaign_id": "c1", "accepted_head_seq": 5, "accepted_head_hash": "h1"}}
    fake_snap = {"as_of_head": {"campaign_id": "c1", "accepted_head_seq": 4, "accepted_head_hash": "h0"}}
    with pytest.raises(ValidationError, match="STOP_SNAPSHOT_BINDING_CONFLICT"):
        validate_stop_snapshot_binding(fake_input, fake_snap)

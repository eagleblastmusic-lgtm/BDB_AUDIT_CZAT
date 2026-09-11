"""Tests for M24 / PR-027: StageCompletion and intermediate STOP Gate."""
import pytest
from jsonschema import Draft202012Validator

from bdb_audit.core.errors import ValidationError
from bdb_audit.schemas.foundation import executable_schema
from bdb_audit.stop import (
    StageCompletion,
    LaneCompletion,
    StopInput,
    StopEvaluation,
    evaluate_stop,
    validate_intermediate_stop,
)


def _mock_ref(kind, revision_digest):
    return {
        "kind": kind,
        "revision_digest": revision_digest,
        "digest_profile": "BDB-CANONICAL-SHA256-1",
        "schema_revision_ref": {"schema_id": f"schema_{kind}"},
        "ref_class": "RECORDED",
    }


def test_m24_schemas_validity():
    """Verify that stage_completion, lane_completion, stop_input, stop_evaluation schemas compile."""
    for kind in ("stage_completion", "lane_completion", "stop_input", "stop_evaluation"):
        schema = executable_schema(kind)
        assert schema is not None
        Draft202012Validator.check_schema(schema)


def test_m24_stage_completion_happy_and_blocked():
    """Verify StageCompletion creation and fail-closed blocking on unresolved/unknown surfaces."""
    history_cut = {"head_sequence": 15, "head_commit_digest": "cut123"}
    stage_run = _mock_ref("stage_run", "s_run1")
    stage_spec = _mock_ref("stage_spec", "s_spec1")
    lane_slot = _mock_ref("lane_completion", "l_comp1")

    # Happy path
    sc = StageCompletion(
        stage_run_ref=stage_run,
        stage_spec_ref=stage_spec,
        input_history_cut=history_cut,
        required_lane_slot_results=[lane_slot],
        completion_predicate_result="STAGE_COMPLETED",
    )
    assert sc.completion_predicate_result == "STAGE_COMPLETED"
    obj = sc.as_object()
    assert obj.kind == "stage_completion"

    # F2: missing/unknown material surface in denominator blocks stage completion
    with pytest.raises(ValidationError, match="STAGE_COMPLETION_BLOCKED"):
        StageCompletion(
            stage_run_ref=stage_run,
            stage_spec_ref=stage_spec,
            input_history_cut=history_cut,
            required_lane_slot_results=[lane_slot],
            unknown_blocked_summary={"unknown_surfaces_count": 2},
            completion_predicate_result="STAGE_COMPLETED",
        )

    # Legitimate STAGE_COMPLETION_BLOCKED record
    sc_blocked = StageCompletion(
        stage_run_ref=stage_run,
        stage_spec_ref=stage_spec,
        input_history_cut=history_cut,
        required_lane_slot_results=[lane_slot],
        unknown_blocked_summary={"unknown_surfaces_count": 2},
        completion_predicate_result="STAGE_COMPLETION_BLOCKED",
    )
    assert sc_blocked.completion_predicate_result == "STAGE_COMPLETION_BLOCKED"


def test_m24_intermediate_stop_happy_path_ends_continue_required():
    """Verify that foundation happy path ends with intermediate StopEvaluation = CONTINUE_REQUIRED."""
    history_cut = {"head_sequence": 20, "head_commit_digest": "cut_happy"}
    e3_spec = _mock_ref("stage_spec", "e3_spec_digest")
    e4_spec = _mock_ref("stage_spec", "e4_spec_digest")
    e5_spec = _mock_ref("stage_spec", "e5_spec_digest")
    e3_completion = _mock_ref("stage_completion", "e3_comp_digest")

    cov_ob1 = _mock_ref("coverage_obligation", "cov1")
    cov_qual1 = _mock_ref("coverage_obligation_qualification", "cov_q1")

    stop_input = StopInput(
        campaign_id="camp_1",
        source_generation_ref=_mock_ref("source_generation", "sg1"),
        input_history_cut=history_cut,
        evaluation_context="INTERMEDIATE",
        governing_policy_ref=_mock_ref("policy_revision", "p1"),
        policy_spec_refs=[_mock_ref("spec_revision", "sp1")],
        evaluator_revision_ref=_mock_ref("spec_revision", "eval1"),
        required_stage_set_ref=_mock_ref("external_profile_ref", "stg_set"),
        required_stage_spec_refs=[e3_spec, e4_spec, e5_spec],
        completed_stage_refs=[e3_completion],
        pending_required_stage_refs=[e4_spec, e5_spec],
        stop_input_snapshot_ref=_mock_ref("snapshot", "snap1"),
        inventory_revision_ref=_mock_ref("inventory_revision", "inv1"),
        mandatory_obligation_refs=[cov_ob1],
        current_obligation_qualification_refs=[cov_qual1],
        evidence_invalidation_refs=[],
        contradiction_refs=[],
        residual_risk_refs=[],
        evidence_invalidation_state={"invalidated_count": 0},
        release_policy_ref=_mock_ref("policy_revision", "rp1"),
        effort_profile_ref=_mock_ref("external_profile_ref", "eff1"),
        effort_results_ref={"rounds_executed": 1},
        continuation_budget_authorization_ref=_mock_ref("approval_decision", "app1"),
        unknown_blocked_summary={"unknown_surfaces_count": 0, "is_blocked": False},
    )

    eval_result = evaluate_stop(stop_input)

    # Must end in CONTINUE_REQUIRED, NOT global PASS
    assert eval_result.continuation_decision == "CONTINUE_REQUIRED"
    assert eval_result.release_readiness == "TECHNICALLY_NOT_READY"
    assert "REQUIRED_STAGES_PENDING" in eval_result.reason_codes
    assert "INSUFFICIENT_DATA" in eval_result.reason_codes
    assert len(eval_result.remaining_obligation_refs) == 1

    # Invariant: intermediate STOP cannot produce PASS
    validate_intermediate_stop(eval_result, "INTERMEDIATE")


def test_m24_intermediate_stop_forbids_pass_and_release_readiness():
    """Verify that any attempt to claim PASS or READY during INTERMEDIATE context fails closed."""
    fake_pass = StopEvaluation(
        stop_input_ref=_mock_ref("stop_input", "si1"),
        continuation_decision="PASS",
        assurance_level="ADEQUATE_FOR_DECLARED_SCOPE",
        release_readiness="READY",
        reason_codes=("ALL_SATISFIED",),
        blocking_obligation_refs=(),
        remaining_obligation_refs=(),
    )

    with pytest.raises(ValidationError, match="INTERMEDIATE_CANNOT_PRODUCE_PASS"):
        validate_intermediate_stop(fake_pass, "INTERMEDIATE")

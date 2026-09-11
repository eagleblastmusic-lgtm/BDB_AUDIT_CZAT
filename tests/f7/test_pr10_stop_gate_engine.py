"""Targeted tests for STOP Gate Engine (PR-E5-10 / M44)."""
import pytest
from jsonschema import Draft202012Validator

from bdb_audit.core.errors import ValidationError
from bdb_audit.stop.evaluator import evaluate_stop, validate_intermediate_stop
from bdb_audit.stop.models import StopInput, StopEvaluation
from bdb_audit.schemas.foundation import executable_schema


def _ref(kind: str, digest_suffix: str, ref_class: str = "CONTENT_OR_PRIOR") -> dict:
    dig = (digest_suffix * 64)[:64]
    return {
        "kind": kind,
        "revision_digest": dig,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
    }


@pytest.fixture
def base_stop_input_kwargs():
    hcut = {
        "campaign_id": "CAMP-001",
        "commit_seq": 20,
        "commit_hash": "a" * 64,
    }
    src_ref = _ref("source_generation", "sg", "CONTENT_OR_PRIOR")
    p_ref = _ref("policy_revision", "p", "HISTORY_CONTEXT_BINDING")
    sp_ref = _ref("spec_revision", "sp", "HISTORY_CONTEXT_BINDING")
    stg_ref = _ref("external_profile_ref", "st", "HISTORY_CONTEXT_BINDING")
    snap_ref = _ref("snapshot", "sn", "CONTENT_OR_PRIOR")
    inv_ref = _ref("inventory_revision", "inv", "CONTENT_OR_PRIOR")
    eff_ref = _ref("external_profile_ref", "eff", "HISTORY_CONTEXT_BINDING")

    cac_ref = _ref("candidate_assurance_case", "cac", "CONTENT_OR_PRIOR")
    ch1 = _ref("challenger_result", "cr1", "CONTENT_OR_PRIOR")
    ch2 = _ref("challenger_result", "cr2", "CONTENT_OR_PRIOR")

    return {
        "campaign_id": "CAMP-001",
        "source_generation_ref": src_ref,
        "input_history_cut": hcut,
        "governing_policy_ref": p_ref,
        "policy_spec_refs": [sp_ref],
        "evaluator_revision_ref": sp_ref,
        "required_stage_set_ref": stg_ref,
        "required_stage_spec_refs": [sp_ref],
        "completed_stage_refs": [sp_ref],
        "pending_required_stage_refs": [],
        "stop_input_snapshot_ref": snap_ref,
        "inventory_revision_ref": inv_ref,
        "mandatory_obligation_refs": [],
        "current_obligation_qualification_refs": [],
        "evidence_invalidation_refs": [],
        "contradiction_refs": [],
        "residual_risk_refs": [],
        "evidence_invalidation_state": {"invalidated_count": 0},
        "release_policy_ref": p_ref,
        "effort_profile_ref": eff_ref,
        "effort_results_ref": {"rounds_executed": 5},
        "unknown_blocked_summary": {"unknown_surfaces_count": 0, "is_blocked": False},
        "candidate_assurance_case_ref": cac_ref,
        "challenger_refs": [ch1, ch2],
    }


def test_stop_pass_happy_path(base_stop_input_kwargs):
    kwargs = dict(base_stop_input_kwargs)
    kwargs["evaluation_context"] = "FINAL_POST_E5"
    si = StopInput(**kwargs)

    ev = evaluate_stop(si, insufficient_data=False)
    assert ev.continuation_decision == "PASS"
    assert ev.assurance_level == "ADEQUATE_FOR_DECLARED_SCOPE"
    assert ev.release_readiness == "READY"
    assert len(ev.blocking_obligation_refs) == 0
    assert len(ev.remaining_obligation_refs) == 0

    Draft202012Validator(executable_schema("stop_evaluation")).validate(ev.body())


def test_stop_pass_with_residual_risk(base_stop_input_kwargs):
    kwargs = dict(base_stop_input_kwargs)
    kwargs["evaluation_context"] = "FINAL_POST_E5"
    kwargs["residual_risk_refs"] = [_ref("residual_risk_ref", "rr", "CONTENT_OR_PRIOR")]
    si = StopInput(**kwargs)

    ev = evaluate_stop(si, insufficient_data=False)
    assert ev.continuation_decision == "PASS"
    assert ev.assurance_level == "ADEQUATE_FOR_DECLARED_SCOPE"
    assert ev.release_readiness == "READY_WITH_RESIDUAL_RISK"


def test_stop_rejects_unknown_scope_as_pass(base_stop_input_kwargs):
    """UNKNOWN surface scope cannot silently become PASS."""
    kwargs = dict(base_stop_input_kwargs)
    kwargs["evaluation_context"] = "FINAL_POST_E5"
    kwargs["unknown_blocked_summary"] = {"unknown_surfaces_count": 2, "is_blocked": False}
    si = StopInput(**kwargs)

    ev = evaluate_stop(si, insufficient_data=False)
    assert ev.continuation_decision == "BLOCKED"
    assert "UNKNOWN_SURFACE_SCOPE" in ev.reason_codes
    assert ev.release_readiness == "QUALIFICATION_BLOCKED"


def test_stop_rejects_blocked_as_pass(base_stop_input_kwargs):
    kwargs = dict(base_stop_input_kwargs)
    kwargs["evaluation_context"] = "FINAL_POST_E5"
    kwargs["unknown_blocked_summary"] = {"unknown_surfaces_count": 0, "is_blocked": True}
    si = StopInput(**kwargs)

    ev = evaluate_stop(si, insufficient_data=False)
    assert ev.continuation_decision == "BLOCKED"
    assert ev.assurance_level == "INSUFFICIENT"
    assert ev.release_readiness == "QUALIFICATION_BLOCKED"


def test_stop_unresolved_evidence_invalidation(base_stop_input_kwargs):
    kwargs = dict(base_stop_input_kwargs)
    kwargs["evaluation_context"] = "FINAL_POST_E5"
    kwargs["evidence_invalidation_refs"] = [_ref("evidence_invalidation", "inv1", "CONTENT_OR_PRIOR")]
    si = StopInput(**kwargs)

    ev = evaluate_stop(si, insufficient_data=False)
    assert ev.continuation_decision == "BLOCKED"
    assert "UNRESOLVED_EVIDENCE_INVALIDATION" in ev.reason_codes
    assert ev.release_readiness == "QUALIFICATION_BLOCKED"


def test_stop_open_contradiction_blocks(base_stop_input_kwargs):
    kwargs = dict(base_stop_input_kwargs)
    kwargs["evaluation_context"] = "FINAL_POST_E5"
    kwargs["contradiction_refs"] = [_ref("contradiction_revision", "contra1", "CONTENT_OR_PRIOR")]
    si = StopInput(**kwargs)

    ev = evaluate_stop(si, insufficient_data=False)
    assert ev.continuation_decision == "BLOCKED"
    assert "OPEN_CONTRADICTION" in ev.reason_codes
    assert ev.release_readiness == "QUALIFICATION_BLOCKED"


def test_stop_missing_candidate_or_challengers_in_final_post_e5(base_stop_input_kwargs):
    # Missing candidate
    kwargs_no_cac = dict(base_stop_input_kwargs)
    kwargs_no_cac["evaluation_context"] = "FINAL_POST_E5"
    kwargs_no_cac["candidate_assurance_case_ref"] = None
    si1 = StopInput(**kwargs_no_cac)
    ev1 = evaluate_stop(si1, insufficient_data=False)
    assert ev1.continuation_decision == "BLOCKED"
    assert "MISSING_CANDIDATE_ASSURANCE_CASE" in ev1.reason_codes

    # Missing challengers
    kwargs_no_ch = dict(base_stop_input_kwargs)
    kwargs_no_ch["evaluation_context"] = "FINAL_POST_E5"
    kwargs_no_ch["challenger_refs"] = []
    si2 = StopInput(**kwargs_no_ch)
    ev2 = evaluate_stop(si2, insufficient_data=False)
    assert ev2.continuation_decision == "BLOCKED"
    assert "MISSING_REQUIRED_CHALLENGERS" in ev2.reason_codes


def test_stop_e6_required_when_bounded_plan_approved(base_stop_input_kwargs):
    kwargs = dict(base_stop_input_kwargs)
    kwargs["evaluation_context"] = "FINAL_POST_E5"
    kwargs["mandatory_obligation_refs"] = [_ref("coverage_obligation", "ob_deep", "CONTENT_OR_PRIOR")]
    si = StopInput(**kwargs)

    ev = evaluate_stop(si, insufficient_data=False, e6_plan_approved=True)
    assert ev.continuation_decision == "E6_REQUIRED"
    assert ev.assurance_level == "BOUNDED"
    assert ev.release_readiness == "QUALIFICATION_BLOCKED"
    assert "E6_REQUIRED" in ev.reason_codes

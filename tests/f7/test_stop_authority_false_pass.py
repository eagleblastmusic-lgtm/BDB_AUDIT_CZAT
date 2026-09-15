"""Adversarial STOP regressions for exact accepted authority and false-PASS prevention."""
from __future__ import annotations

import copy

from bdb_audit.stop.evaluator import evaluate_stop
from bdb_audit.stop.models import StopInput


def _ref(kind: str, char: str, ref_class: str = "CONTENT_OR_PRIOR") -> dict:
    return {
        "kind": kind,
        "revision_digest": char * 64,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
    }


def _base() -> dict:
    cut = {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": "campaign-stop-authority",
        "accepted_head_seq": 20,
        "accepted_head_hash": "a" * 64,
        "governing_policy_ref": "pin:policy",
        "governing_spec_refs": ["pin:spec"],
    }
    return {
        "campaign_id": "campaign-stop-authority",
        "source_generation_ref": _ref("source_generation", "1"),
        "input_history_cut": cut,
        "evaluation_context": "FINAL_POST_E5",
        "governing_policy_ref": _ref("policy_revision", "2", "HISTORY_CONTEXT_BINDING"),
        "policy_spec_refs": [_ref("spec_revision", "3", "HISTORY_CONTEXT_BINDING")],
        "evaluator_revision_ref": _ref("spec_revision", "3", "HISTORY_CONTEXT_BINDING"),
        "required_stage_set_ref": _ref("external_profile_ref", "4", "HISTORY_CONTEXT_BINDING"),
        "required_stage_spec_refs": [_ref("stage_spec", "5", "HISTORY_CONTEXT_BINDING")],
        "completed_stage_refs": [_ref("stage_completion", "6")],
        "pending_required_stage_refs": [],
        "stop_input_snapshot_ref": _ref("snapshot", "7"),
        "inventory_revision_ref": _ref("inventory_revision", "8"),
        "mandatory_obligation_refs": [],
        "current_obligation_qualification_refs": [],
        "evidence_invalidation_refs": [],
        "contradiction_refs": [],
        "residual_risk_refs": [],
        "evidence_invalidation_state": {"invalidated_count": 0},
        "release_policy_ref": _ref("policy_revision", "2", "HISTORY_CONTEXT_BINDING"),
        "effort_profile_ref": _ref("external_profile_ref", "9", "HISTORY_CONTEXT_BINDING"),
        "effort_results_ref": _ref("registered_immutable_object", "b"),
        "unknown_blocked_summary": {
            "unknown_surfaces_count": 0,
            "is_blocked": False,
            "qualification_binding_verified": True,
            "challenger_binding_verified": True,
            "unqualified_mandatory_obligations_count": 0,
            "blocked_qualification_count": 0,
            "stale_qualification_count": 0,
            "in_progress_qualification_count": 0,
            "inconclusive_qualification_count": 0,
            "violation_confirmed_count": 0,
            "challenger_blocked_count": 0,
            "challenger_inconclusive_count": 0,
            "challenger_material_counterevidence_count": 0,
        },
        "candidate_assurance_case_ref": _ref("candidate_assurance_case", "c"),
        "challenger_refs": [_ref("challenger_result", "d"), _ref("challenger_result", "e")],
    }


def test_final_stop_happy_path_requires_verified_bindings() -> None:
    stop_input = StopInput(**_base())
    result = evaluate_stop(stop_input, insufficient_data=False)
    assert result.continuation_decision == "PASS"


def test_equal_number_of_unrelated_qualification_refs_cannot_pass() -> None:
    data = _base()
    data["mandatory_obligation_refs"] = [
        _ref("coverage_obligation", "1"),
        _ref("coverage_obligation", "2"),
    ]
    data["current_obligation_qualification_refs"] = [
        _ref("coverage_obligation_qualification", "3"),
        _ref("coverage_obligation_qualification", "4"),
    ]
    data["unknown_blocked_summary"]["qualification_binding_verified"] = False
    data["unknown_blocked_summary"]["unqualified_mandatory_obligations_count"] = 2

    result = evaluate_stop(StopInput(**data), insufficient_data=False)
    assert result.continuation_decision == "BLOCKED"
    assert "QUALIFICATION_BINDING_UNVERIFIED" in result.reason_codes


def test_confirmed_violation_is_hard_stop_blocker() -> None:
    data = _base()
    data["mandatory_obligation_refs"] = [_ref("coverage_obligation", "1")]
    data["current_obligation_qualification_refs"] = [_ref("coverage_obligation_qualification", "2")]
    data["unknown_blocked_summary"]["violation_confirmed_count"] = 1

    result = evaluate_stop(StopInput(**data), insufficient_data=False)
    assert result.continuation_decision == "BLOCKED"
    assert "MANDATORY_OBLIGATION_VIOLATION_CONFIRMED" in result.reason_codes


def test_stale_or_blocked_qualification_cannot_pass() -> None:
    for field, expected_reason in (
        ("stale_qualification_count", "STALE_MANDATORY_QUALIFICATION"),
        ("blocked_qualification_count", "BLOCKED_MANDATORY_QUALIFICATION"),
    ):
        data = _base()
        data["mandatory_obligation_refs"] = [_ref("coverage_obligation", "1")]
        data["current_obligation_qualification_refs"] = [_ref("coverage_obligation_qualification", "2")]
        data["unknown_blocked_summary"][field] = 1
        result = evaluate_stop(StopInput(**data), insufficient_data=False)
        assert result.continuation_decision == "BLOCKED"
        assert expected_reason in result.reason_codes


def test_material_challenger_counterevidence_cannot_pass() -> None:
    data = _base()
    data["unknown_blocked_summary"]["challenger_material_counterevidence_count"] = 1
    result = evaluate_stop(StopInput(**data), insufficient_data=False)
    assert result.continuation_decision == "BLOCKED"
    assert "MATERIAL_CHALLENGER_COUNTEREVIDENCE" in result.reason_codes


def test_inconclusive_qualification_requires_more_work_not_pass() -> None:
    data = _base()
    data["mandatory_obligation_refs"] = [_ref("coverage_obligation", "1")]
    data["current_obligation_qualification_refs"] = [_ref("coverage_obligation_qualification", "2")]
    data["unknown_blocked_summary"]["inconclusive_qualification_count"] = 1
    result = evaluate_stop(StopInput(**data), insufficient_data=False, e6_plan_approved=True)
    assert result.continuation_decision == "E6_REQUIRED"

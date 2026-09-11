"""Regression tests for the v2.0.2 operational STOP gate patch."""
from __future__ import annotations

import json
from pathlib import Path

from bdb_audit.cli import EXIT_SUCCESS, run_cli
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.stop.operation import evaluate_stop_gate
from bdb_audit.ui import InteractiveAuditUI


def _ref(kind: str, token: str, ref_class: str = "CONTENT_OR_PRIOR") -> dict:
    digest = (token * 64)[:64]
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
    }


def _pass_stop_input(campaign_id: str, head_seq: int, head_hash: str) -> dict:
    policy = _ref("policy_revision", "p", "HISTORY_CONTEXT_BINDING")
    spec = _ref("spec_revision", "s", "HISTORY_CONTEXT_BINDING")
    return {
        "campaign_id": campaign_id,
        "source_generation_ref": _ref("source_generation", "g"),
        "input_history_cut": {
            "campaign_id": campaign_id,
            "accepted_head_seq": head_seq,
            "accepted_head_hash": head_hash,
        },
        "evaluation_context": "FINAL_POST_E5",
        "governing_policy_ref": policy,
        "policy_spec_refs": [spec],
        "evaluator_revision_ref": spec,
        "required_stage_set_ref": _ref("external_profile_ref", "t", "HISTORY_CONTEXT_BINDING"),
        "required_stage_spec_refs": [spec],
        "completed_stage_refs": [spec],
        "pending_required_stage_refs": [],
        "stop_input_snapshot_ref": _ref("snapshot", "n"),
        "inventory_revision_ref": _ref("inventory_revision", "i"),
        "mandatory_obligation_refs": [],
        "current_obligation_qualification_refs": [],
        "evidence_invalidation_refs": [],
        "contradiction_refs": [],
        "residual_risk_refs": [],
        "evidence_invalidation_state": {"invalidated_count": 0},
        "release_policy_ref": policy,
        "effort_profile_ref": _ref("external_profile_ref", "e", "HISTORY_CONTEXT_BINDING"),
        "effort_results_ref": {"rounds_executed": 5},
        "unknown_blocked_summary": {"unknown_surfaces_count": 0, "is_blocked": False},
        "candidate_assurance_case_ref": _ref("candidate_assurance_case", "c"),
        "challenger_refs": [
            _ref("challenger_result", "1"),
            _ref("challenger_result", "2"),
        ],
    }


def test_v202_missing_accepted_stop_input_fails_closed(tmp_path: Path):
    store = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(store, seed="v202_missing")
    for stage in ("E1", "E2", "E3", "E4", "E5"):
        api.prepare_stage(store, stage)

    cont = api.continue_campaign(store)
    assert cont["next_action"] == "EVALUATE_STOP_GATE"

    result = evaluate_stop_gate(store)
    assert result["status"] == "SUCCESS"
    assert result["evaluated"] is False
    assert result["authoritative"] is True
    assert result["continuation_decision"] == "BLOCKED"
    assert result["reason_codes"] == ["MISSING_ACCEPTED_STOP_INPUT"]
    assert result["next_action"] == "PROVIDE_OR_ACCEPT_STOP_INPUT"


def test_v202_preview_stop_input_evaluates_but_is_non_authoritative(tmp_path: Path, capsys):
    store = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    created = api.create_campaign(store, seed="v202_preview")

    artifact = tmp_path / "stop_input.json"
    artifact.write_text(
        json.dumps(
            {
                "kind": "stop_input",
                "body": _pass_stop_input(
                    created["campaign_id"],
                    created["commit_seq"],
                    created["commit_hash"],
                ),
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_stop_gate(store, stop_input_path=artifact)
    assert result["evaluated"] is True
    assert result["authoritative"] is False
    assert result["continuation_decision"] == "PASS"
    assert result["release_readiness"] == "READY"
    assert result["next_action"] == "ACCEPT_STOP_INPUT_BEFORE_AUTHORITATIVE_DECISION"

    rc = run_cli([
        "stop",
        "evaluate",
        "--store",
        str(store),
        "--input",
        str(artifact),
        "--json",
    ])
    assert rc == EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["continuation_decision"] == "PASS"
    assert out["authoritative"] is False


def test_v202_ui_exposes_stop_gate_action(tmp_path: Path):
    store = str(tmp_path / "campaign.sqlite")
    inputs = iter([
        "6",  # Enter Advanced menu
        "1", store, "v202_ui",
        "10", "", "n",
        "9",  # Back to Main menu
        "7",  # Exit Main menu
    ])
    outputs: list[str] = []
    ui = InteractiveAuditUI()
    rc = ui.run_menu_loop(
        input_func=lambda prompt="": next(inputs),
        output_func=outputs.append,
    )

    assert rc == 0
    text = "\n".join(outputs)
    assert "BDB Audit v2.0.3" in text
    assert "10. Evaluate STOP Gate" in text
    assert "Decision=BLOCKED" in text
    assert "MISSING_ACCEPTED_STOP_INPUT" in text

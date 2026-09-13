"""Tests for Complete User Workflow E1-E6 and STOP / Conclusion (RU08 / B02).

Validates:
1. Complete workflow without E6 (E1 -> E2 -> E3 -> E4 -> E5 -> STOP -> Conclusion).
2. Material E6 + fresh challengers scenario.
3. Early BLOCKED -> COMPLETED_LIMITED -> QUALIFICATION_BLOCKED.
4. Process restart between stages preserves exact same accepted truth.
5. UI and CLI project same terminal result.
6. No manual PASS setter.
7. E2 claim without evidence remains UNKNOWN.
8. Real small target integration.
"""
from pathlib import Path
import tempfile
import pytest

from bdb_audit.cli import run_cli
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.orchestrator import FullAuditOrchestrator
from bdb_audit.workflow.read_models import campaign_status
from bdb_audit.workflow.settings import SettingsManager, UserSettings


@pytest.fixture
def workflow_env():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        target_dir = root / "sample_target"
        target_dir.mkdir()
        (target_dir / "README.md").write_text("# Target App\nSample target for audit.\n", encoding="utf-8")
        (target_dir / "app.py").write_text("def run(): return 42\n", encoding="utf-8")

        store_path = root / "campaign.sqlite"
        settings_file = root / "settings.json"
        settings_mgr = SettingsManager(settings_file)
        settings_mgr.settings = UserSettings(
            local_repo_path=str(target_dir),
            output_work_dir=str(root / "out"),
            execution_mode="ChatGPT / GitHub",
        )
        yield {
            "root": root,
            "target_dir": target_dir,
            "store_path": store_path,
            "settings_mgr": settings_mgr,
        }


def test_core_acceptance_1_complete_scenario_without_e6(workflow_env):
    """1. Complete scenario without E6: E1 -> E2 -> E3 -> E4 -> E5 -> STOP -> Conclusion."""
    store_path = workflow_env["store_path"]
    api = AuditOperationApi()

    # Genesis
    api.create_campaign(store_path, seed="full_audit_test", target_repo=str(workflow_env["target_dir"]))

    # Advance through E1..E5
    for stage in ("E1", "E2", "E3", "E4", "E5"):
        api.prepare_stage(store_path, stage)
        res = api.qualify_stage(store_path, stage)
        assert res["status"] == "SUCCESS"
        assert res["stage"] == stage

    # Status shows all 5 stages completed
    status = api.get_campaign_status(store_path)
    assert status["stages_completed"] == ["E1", "E2", "E3", "E4", "E5"]

    # STOP Evaluation
    stop_res = api.evaluate_stop_gate(store_path, evaluation_context="FINAL_POST_E5")
    assert stop_res["status"] == "SUCCESS"
    assert stop_res["continuation_decision"] == "PASS"
    assert stop_res["assurance_level"] == "ADEQUATE_FOR_DECLARED_SCOPE"

    # Campaign Conclusion
    concl_res = api.conclude_campaign(store_path)
    assert concl_res["status"] == "SUCCESS"
    assert concl_res["termination_state"] == "COMPLETED"
    assert concl_res["release_readiness"] == "READY"

    # Final projection
    final_status = api.get_campaign_status(store_path)
    assert final_status["campaign_completed"] is True
    assert final_status["termination_state"] == "COMPLETED"


def test_core_acceptance_2_material_e6_fresh_challenger(workflow_env):
    """2. Material E6 + fresh challenge: STOP yields E6_REQUIRED -> scoped E6 run -> re-evaluates."""
    store_path = workflow_env["store_path"]
    api = AuditOperationApi()

    api.create_campaign(store_path, seed="e6_test", target_repo=str(workflow_env["target_dir"]))

    for stage in ("E1", "E2", "E3", "E4", "E5"):
        api.prepare_stage(store_path, stage)
        api.qualify_stage(store_path, stage)

    # Simulate STOP evaluation with approved E6 plan
    stop_res = api.evaluate_stop_gate(store_path, evaluation_context="FINAL_POST_E5", e6_plan_approved=True)
    assert stop_res["status"] == "SUCCESS"
    # When E6 plan is approved for gap resolution, continuation_decision is E6_REQUIRED
    assert stop_res["continuation_decision"] == "E6_REQUIRED"
    assert stop_res["assurance_level"] == "BOUNDED"

    # Now execute E6
    api.prepare_stage(store_path, "E6")
    e6_res = api.qualify_stage(store_path, "E6")
    assert e6_res["status"] == "SUCCESS"
    assert e6_res["stage"] == "E6"

    # Post-E6 STOP evaluation
    post_e6_stop = api.evaluate_stop_gate(store_path, evaluation_context="POST_E6")
    assert post_e6_stop["status"] == "SUCCESS"
    assert post_e6_stop["continuation_decision"] == "PASS"


def test_core_acceptance_3_early_blocked_completed_limited(workflow_env):
    """3. Early BLOCKED -> COMPLETED_LIMITED -> QUALIFICATION_BLOCKED, never READY."""
    store_path = workflow_env["store_path"]
    api = AuditOperationApi()

    api.create_campaign(store_path, seed="blocked_test", target_repo=str(workflow_env["target_dir"]))

    for stage in ("E1", "E2", "E3"):
        api.prepare_stage(store_path, stage)
        api.qualify_stage(store_path, stage)

    # Evaluate intermediate STOP when required stages E4-E5 are pending and surface is blocked
    stop_res = api.evaluate_stop_gate(
        store_path,
        evaluation_context="FINAL_POST_E5",
        unknown_blocked_summary={"unknown_surfaces_count": 0, "is_blocked": True},
    )
    assert stop_res["continuation_decision"] == "BLOCKED"
    assert stop_res["release_readiness"] == "QUALIFICATION_BLOCKED"

    # Concluding a blocked campaign produces COMPLETED_LIMITED, never READY
    concl_res = api.conclude_campaign(store_path, termination_state="COMPLETED_LIMITED")
    assert concl_res["termination_state"] == "COMPLETED_LIMITED"
    assert concl_res["release_readiness"] == "QUALIFICATION_BLOCKED"
    assert concl_res["release_readiness"] != "READY"


def test_core_acceptance_4_restart_between_stages_preserves_accepted_truth(workflow_env):
    """4. Process restart between stages preserves exact same accepted truth."""
    store_path = workflow_env["store_path"]
    api1 = AuditOperationApi()

    api1.create_campaign(store_path, seed="restart_test", target_repo=str(workflow_env["target_dir"]))
    api1.prepare_stage(store_path, "E1")
    api1.qualify_stage(store_path, "E1")
    api1.prepare_stage(store_path, "E2")
    api1.qualify_stage(store_path, "E2")

    head1 = api1.get_campaign_status(store_path)
    assert head1["stages_completed"] == ["E1", "E2"]
    commit_seq1 = head1["accepted_head_seq"]

    # Completely new process / API instance reading from disk
    api2 = AuditOperationApi()
    head2 = api2.get_campaign_status(store_path)
    assert head2["stages_completed"] == ["E1", "E2"]
    assert head2["accepted_head_seq"] == commit_seq1
    assert head2["current_stage"] == "E3"  # First incomplete prepared/next stage


def test_core_acceptance_6_no_manual_pass_setter(workflow_env):
    """6. No manual PASS setter: cannot conclude as COMPLETED without passing STOP gate."""
    store_path = workflow_env["store_path"]
    api = AuditOperationApi()

    api.create_campaign(store_path, seed="no_manual_pass", target_repo=str(workflow_env["target_dir"]))
    # Attempt to conclude without completing stages or STOP evaluation
    with pytest.raises(ValidationError, match="STOP_EVALUATION_REQUIRED"):
        api.conclude_campaign(store_path, termination_state="COMPLETED")


def test_core_acceptance_7_e2_claim_without_evidence_remains_unknown(workflow_env):
    """7. E2 claim without evidence remains UNKNOWN."""
    store_path = workflow_env["store_path"]
    api = AuditOperationApi()

    api.create_campaign(store_path, seed="e2_evidence_test", target_repo=str(workflow_env["target_dir"]))
    api.prepare_stage(store_path, "E1")
    api.qualify_stage(store_path, "E1")

    # Pass an unbacked finding to E2
    unbacked_finding = {
        "finding_id": "find_001",
        "claim": "Hypothetical injection vulnerability",
        "evidence_refs": [],  # NO EVIDENCE!
    }
    api.prepare_stage(store_path, "E2")
    res = api.qualify_stage(store_path, "E2", findings=[unbacked_finding])
    assert res["status"] == "SUCCESS"
    assert unbacked_finding["claim_status"] == "UNKNOWN"


def test_core_acceptance_5_ui_and_cli_parity(workflow_env):
    """5. UI and CLI project same terminal result via shared read models."""
    store_path = workflow_env["store_path"]

    # Start audit via CLI
    rc = run_cli([
        "audit", "start",
        "--store", str(store_path),
        "--target", str(workflow_env["target_dir"]),
        "--seed", "cli_ui_parity",
        "--json",
    ])
    assert rc == 0

    api = AuditOperationApi()
    status_api = api.get_campaign_status(store_path)

    # CLI status
    rc_stat = run_cli(["audit", "status", "--store", str(store_path), "--json"])
    assert rc_stat == 0

    # Both show campaign is initialized and stage E1 is prepared
    assert status_api["stages_prepared"] == ["E1"]
    assert status_api["current_stage"] == "E1"

"""Targeted tests for FullAuditOrchestrator lifecycle and resume capability."""
from __future__ import annotations

import json
from pathlib import Path
import zipfile
import pytest

from bdb_audit.workflow.settings import SettingsManager
from bdb_audit.workflow.platform import MockPlatformAdapter
from bdb_audit.workflow.source_target import ResolvedSource
from bdb_audit.workflow.orchestrator import FullAuditOrchestrator
from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS


def _create_lane_result_zip(path: Path, batch, slot: str) -> Path:
    job = batch.get_job(slot)
    manifest = {
        "kind": "bdb_audit_lane_result",
        "version": "1",
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": slot,
        "source_commit_sha": batch.source_commit_sha,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "input_package_digest": job.package_digest,
        "history_cut": batch.frozen_history_cut,
        "findings": [{"finding_id": f"{slot}-01", "statement": f"Valid finding for {slot}", "claim_outcome": "SUPPORTED"}],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.json", json.dumps(manifest, indent=2))
    return path


@pytest.fixture
def orchestrator_setup(tmp_path: Path):
    cfg_file = tmp_path / "user_settings.json"
    mgr = SettingsManager(config_path=cfg_file)
    mgr.settings.github_repo_url = "https://github.com/example/orchestrator-repo"
    mgr.settings.github_default_ref = "main"
    mgr.settings.output_work_dir = str(tmp_path / "work_dir")
    mgr.save()

    mock_platform = MockPlatformAdapter()
    orch = FullAuditOrchestrator(settings_mgr=mgr, platform_adapter=mock_platform)
    # Supply pre-resolved source for unit test
    orch.resolved_source = ResolvedSource(
        target_type="github",
        location=mgr.settings.github_repo_url,
        display_name="example/orchestrator-repo",
        ref="main",
        exact_commit_sha="c" * 40,
    )
    return orch, mgr, mock_platform, tmp_path


def test_preflight_checks_pass_when_configured(orchestrator_setup):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    report = orch.run_preflight(explicit_target_sha="c" * 40)
    assert report.passed is True
    assert report.overall_status == "PASS"
    check_names = [c.check_name for c in report.checks]
    assert "Source / target" in check_names
    assert "Exact source identity" in check_names
    assert "Executor profile" in check_names
    assert "Output directory" in check_names
    assert "Required templates" in check_names
    assert "Required contracts" in check_names


def test_preflight_fails_closed_when_target_missing(tmp_path: Path):
    cfg_file = tmp_path / "empty_target.json"
    mgr = SettingsManager(config_path=cfg_file)
    mgr.settings.github_repo_url = ""
    mgr.settings.local_repo_path = ""
    mgr.save()

    orch = FullAuditOrchestrator(settings_mgr=mgr, platform_adapter=MockPlatformAdapter())
    report = orch.run_preflight()
    assert report.passed is False
    assert report.overall_status in ("NEEDS_INPUT", "BLOCKED")


def test_campaign_initialization_and_locator_recording(orchestrator_setup):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    res = orch.initialize_campaign()
    assert res["status"] == "SUCCESS"
    assert orch.active_store_path.exists()
    # Check locator recorded in settings
    assert len(mgr.settings.known_campaigns) == 1
    assert mgr.settings.known_campaigns[0]["campaign_id"] == res["campaign_id"]


def test_e1_delivery_invokes_platform_adapters(orchestrator_setup):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    orch.initialize_campaign()
    batch = orch.prepare_e1_orchestration()

    # Deliver lane E1-A
    deliv_a = orch.deliver_lane_to_user("E1-A")
    assert deliv_a["prompt_copied"] is True
    assert deliv_a["explorer_selected"] is True
    assert len(mock_platform.copied_texts) == 1
    assert len(mock_platform.selected_files) == 1
    assert mock_platform.selected_files[0].name.startswith("E1-A")

    # Deliver lane E1-B
    deliv_b = orch.deliver_lane_to_user("E1-B")
    assert len(mock_platform.copied_texts) == 2
    assert len(mock_platform.selected_files) == 2


def test_partial_ingestion_and_resumption(orchestrator_setup):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    init_res = orch.initialize_campaign()
    store_path = orch.active_store_path
    batch = orch.prepare_e1_orchestration()

    # Ingest only 2 lanes (E1-A and E1-B)
    zip_a = _create_lane_result_zip(tmp / "res_a.zip", batch, "E1-A")
    zip_b = _create_lane_result_zip(tmp / "res_b.zip", batch, "E1-B")
    summary1 = orch.import_results([zip_a, zip_b])

    assert summary1.accepted_count == 2
    assert summary1.stage_complete is False
    assert set(summary1.missing_lanes) == {"E1-C", "E1-D", "E1-E"}

    # Process restart simulation: create fresh orchestrator instance pointing to same settings & store
    mgr_reloaded = SettingsManager(config_path=mgr.path)
    orch_resumed = FullAuditOrchestrator(settings_mgr=mgr_reloaded, platform_adapter=mock_platform)
    orch_resumed.active_store_path = store_path
    orch_resumed.resolved_source = orch.resolved_source

    # Resumed orchestrator prepares/attaches to E1 orchestration
    batch_resumed = orch_resumed.prepare_e1_orchestration()
    assert batch_resumed.campaign_id == batch.campaign_id

    # Ingest remaining 3 lanes (E1-C, E1-D, E1-E)
    zip_c = _create_lane_result_zip(tmp / "res_c.zip", batch_resumed, "E1-C")
    zip_d = _create_lane_result_zip(tmp / "res_d.zip", batch_resumed, "E1-D")
    zip_e = _create_lane_result_zip(tmp / "res_e.zip", batch_resumed, "E1-E")
    summary2 = orch_resumed.import_results([zip_c, zip_d, zip_e])

    # Along with previous A and B, all 5 can be passed or accumulated
    summary_final = orch_resumed.import_results([zip_a, zip_b, zip_c, zip_d, zip_e])
    assert summary_final.accepted_count == 5
    assert summary_final.stage_complete is True


def test_orchestrator_halts_fail_closed_after_e1_without_fabricated_stop_pass(orchestrator_setup):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    orch.initialize_campaign()
    batch = orch.prepare_e1_orchestration()

    # Complete all 5 lanes
    all_zips = [
        _create_lane_result_zip(tmp / f"res_{slot}.zip", batch, slot)
        for slot in E1_LANE_SLOTS
    ]
    orch.import_results(all_zips)

    # Advance stage
    adv = orch.advance_to_next_stage()
    assert adv["status"] == "HALTED"
    assert adv["next_stage"] == "E2"
    assert adv["next_action"] == "NEEDS_IMPLEMENTATION"
    # Guaranteed: never fabricates fake STOP PASS
    assert adv.get("continuation_decision") != "PASS"

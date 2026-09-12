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
    # Supply pre-resolved source for unit test paths that do not exercise the
    # network resolver itself.
    orch.resolved_source = ResolvedSource(
        target_type="github",
        location=mgr.settings.github_repo_url,
        display_name="example/orchestrator-repo",
        ref="main",
        exact_commit_sha="c" * 40,
    )
    return orch, mgr, mock_platform, tmp_path


def test_preflight_checks_pass_when_configured(orchestrator_setup, monkeypatch):
    orch, mgr, mock_platform, tmp = orchestrator_setup

    # RU02 now proves explicit SHAs against the authorized remote instead of
    # trusting a caller-supplied hex string.  This unit test is about preflight
    # aggregation, not Git transport, so provide a verified resolver result at
    # the boundary rather than relying on a fictitious github.com/example repo.
    verified = ResolvedSource(
        target_type="github",
        location=mgr.settings.github_repo_url,
        display_name="example/orchestrator-repo",
        ref="main",
        exact_commit_sha="c" * 40,
        exact_tree_sha="d" * 40,
    )
    monkeypatch.setattr(
        "bdb_audit.workflow.orchestrator.resolve_source_identity",
        lambda **kwargs: verified,
    )

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
    res = orch.deliver_e1_lane("E1-A")
    assert res["status"] == "SUCCESS"
    assert res["lane_slot"] == "E1-A"
    assert len(mock_platform.copied_texts) == 1
    assert len(mock_platform.selected_files) == 1
    assert batch.get_job("E1-A").prompt_text == mock_platform.copied_texts[0]


def test_import_partial_results_returns_missing_lanes(orchestrator_setup):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    orch.initialize_campaign()
    batch = orch.prepare_e1_orchestration()

    zip_a = _create_lane_result_zip(tmp / "result_a.zip", batch, "E1-A")
    zip_c = _create_lane_result_zip(tmp / "result_c.zip", batch, "E1-C")

    summary = orch.import_results([zip_a, zip_c])
    assert summary.accepted_count == 2
    assert set(summary.missing_lanes) == {"E1-B", "E1-D", "E1-E"}
    assert summary.stage_complete is False


def test_import_all_5_results_completes_e1(orchestrator_setup):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    orch.initialize_campaign()
    batch = orch.prepare_e1_orchestration()

    paths = [
        _create_lane_result_zip(tmp / f"result_{slot}.zip", batch, slot)
        for slot in E1_LANE_SLOTS
    ]
    summary = orch.import_results(paths)
    assert summary.accepted_count == 5
    assert summary.missing_lanes == []
    assert summary.stage_complete is True


def test_advance_after_e1_is_fail_closed_needs_implementation(orchestrator_setup):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    orch.initialize_campaign()
    batch = orch.prepare_e1_orchestration()

    paths = [
        _create_lane_result_zip(tmp / f"result_{slot}.zip", batch, slot)
        for slot in E1_LANE_SLOTS
    ]
    orch.import_results(paths)

    res = orch.advance_after_e1()
    assert res["status"] == "NEEDS_IMPLEMENTATION"
    assert res["next_stage"] == "E2"


def test_advance_before_e1_complete_is_blocked(orchestrator_setup):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    orch.initialize_campaign()
    orch.prepare_e1_orchestration()

    res = orch.advance_after_e1()
    assert res["status"] == "BLOCKED"


def test_resume_campaign_reconstructs_partial_state(orchestrator_setup):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    init = orch.initialize_campaign()
    batch = orch.prepare_e1_orchestration()

    zip_b = _create_lane_result_zip(tmp / "result_b.zip", batch, "E1-B")
    orch.import_results([zip_b])

    # Simulate restart with new orchestrator
    orch2 = FullAuditOrchestrator(settings_mgr=mgr, platform_adapter=MockPlatformAdapter())
    result = orch2.resume_campaign(init["store_path"])
    assert result["status"] == "SUCCESS"
    assert result["accepted_lanes_count"] == 1
    assert "E1-B" not in result["missing_lanes"]
    assert set(result["missing_lanes"]) == {"E1-A", "E1-C", "E1-D", "E1-E"}


def test_resume_nonexistent_store_fails_closed(orchestrator_setup):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    result = orch.resume_campaign(tmp / "missing.sqlite")
    assert result["status"] == "ERROR"


def test_status_without_active_campaign(orchestrator_setup):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    result = orch.get_status()
    assert result["status"] == "NO_ACTIVE_CAMPAIGN"


def test_status_after_initialization(orchestrator_setup):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    orch.initialize_campaign()
    result = orch.get_status()
    assert result["status"] == "ACTIVE"
    assert result["stage"] in ("E0", "E1")

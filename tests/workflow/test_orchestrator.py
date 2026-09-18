"""Targeted tests for FullAuditOrchestrator lifecycle and resume capability."""
from __future__ import annotations

import json
from pathlib import Path
import zipfile
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.workflow.settings import SettingsManager
from bdb_audit.workflow.platform import MockPlatformAdapter
from bdb_audit.workflow.source_target import ResolvedSource
from bdb_audit.workflow.orchestrator import FullAuditOrchestrator
from bdb_audit.workflow.executors import EXECUTION_MODES
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


def test_advance_after_e1_prepares_real_e2_blind_phase(orchestrator_setup):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    orch.initialize_campaign()
    batch = orch.prepare_e1_orchestration()

    paths = [
        _create_lane_result_zip(tmp / f"result_{slot}.zip", batch, slot)
        for slot in E1_LANE_SLOTS
    ]
    orch.import_results(paths)

    res = orch.advance_after_e1()
    assert res["status"] == "WAITING_EXTERNAL_RESULTS"
    assert res["current_stage"] == "E2"
    assert res["current_phase"] == "E2-BLIND"
    assert set(res["missing_lanes"]) == {
        "E2-CONVERGENCE",
        "E2-ADJUDICATION",
    }
    assert res["next_action"] == "DELIVER_OR_IMPORT_E2_BLIND_RESULTS"
    assert orch.stage_batch is not None
    assert orch.stage_batch.phase_id == "E2-BLIND"


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
    assert result["stage"] in ("GENESIS", "E0", "E1")


def test_advance_does_not_reset_existing_e2_phase_to_blind(
    orchestrator_setup,
    monkeypatch,
):
    """Regression: an active E2 phase must never be silently regenerated as BLIND."""
    orch, mgr, mock_platform, tmp = orchestrator_setup
    orch.initialize_campaign()
    e1_batch = orch.prepare_e1_orchestration()
    orch.import_results(
        [
            _create_lane_result_zip(
                tmp / f"result_{slot}.zip",
                e1_batch,
                slot,
            )
            for slot in E1_LANE_SLOTS
        ]
    )
    first = orch.advance_to_next_stage()
    assert first["current_phase"] == "E2-BLIND"

    # Use the already accepted E2 batch as a state carrier and relabel only the
    # in-memory phase for this guard regression. The call must inspect current
    # phase state rather than invoking prepare_e2_blind_orchestration.
    assert orch.stage_batch is not None
    original_batch = orch.stage_batch
    from dataclasses import replace
    orch.stage_batch = replace(
        original_batch,
        phase_id="E2-REVEAL",
    )

    called = {"blind": False}
    def forbidden_blind_prepare():
        called["blind"] = True
        raise AssertionError("active E2 phase was reset to blind")

    monkeypatch.setattr(
        orch,
        "prepare_e2_blind_orchestration",
        forbidden_blind_prepare,
    )
    # Existing inbox still has missing lanes, so the orchestrator should return
    # the current phase as waiting rather than replace it with E2-BLIND.
    result = orch.advance_to_next_stage()
    assert called["blind"] is False
    assert result["status"] == "WAITING_EXTERNAL_RESULTS"
    assert result["current_phase"] == "E2-REVEAL"
    assert result["next_action"] == "DELIVER_OR_IMPORT_E2_REVEAL_RESULTS"


def test_advance_stage_never_uses_synthetic_qualify_stage(
    orchestrator_setup,
    monkeypatch,
):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    orch.initialize_campaign()
    orch.prepare_e1_orchestration()

    called = {"qualify": False}

    def forbidden_qualify(*args, **kwargs):
        called["qualify"] = True
        raise AssertionError("synthetic StageCompletion backdoor used")

    monkeypatch.setattr(
        orch.api,
        "qualify_stage",
        forbidden_qualify,
    )
    result = orch.advance_stage("E1")
    assert called["qualify"] is False
    assert result["status"] == "WAITING_EXTERNAL_RESULTS"
    assert result["current_stage"] == "E1"


def test_current_executor_profiles_do_not_overclaim_enforced_isolation():
    assert EXECUTION_MODES
    for profile in EXECUTION_MODES.values():
        assert profile.max_isolation_assurance in {
            "UNKNOWN",
            "DECLARED",
            "ENFORCED",
        }
        # No current transport adapter records the material boundary receipts
        # required to truthfully claim ENFORCED isolation.
        assert profile.max_isolation_assurance != "ENFORCED"


def test_e3_blind_preparation_fails_before_package_publication_without_enforced_backend(
    orchestrator_setup,
):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    orch.initialize_campaign()
    assert orch.active_store_path is not None
    # Build only the predecessor acceptance needed to reach the capability
    # check. This test is not exercising the user workflow itself.
    orch.api.prepare_stage(orch.active_store_path, "E1")
    orch.api.qualify_stage(orch.active_store_path, "E1")
    orch.api.prepare_stage(orch.active_store_path, "E2")
    orch.api.qualify_stage(orch.active_store_path, "E2")
    artifacts = orch._artifact_root()

    with pytest.raises(
        ValidationError,
        match="E3_ENFORCED_ISOLATION_BACKEND_REQUIRED",
    ):
        orch.prepare_e3_blind_orchestration()

    # Capability refusal happens before E3 assignment/package publication.
    campaign_id = orch.api.get_campaign_status(
        orch.active_store_path
    )["campaign_id"]
    e3_root = artifacts / campaign_id / "E3"
    assert not e3_root.exists()

def test_resume_does_not_resurrect_completed_e2_phase(
    orchestrator_setup,
    monkeypatch,
):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    init = orch.initialize_campaign()
    e1 = orch.prepare_e1_orchestration()
    orch.import_results(
        [
            _create_lane_result_zip(
                tmp / f"resume_{slot}.zip",
                e1,
                slot,
            )
            for slot in E1_LANE_SLOTS
        ]
    )
    # Prepare E2 via real workflow so durable E2 packages exist, then mark E2
    # complete only for this resume authority regression.
    orch.advance_to_next_stage()
    assert orch.active_store_path is not None
    orch.api.qualify_stage(orch.active_store_path, "E2")

    resumed = FullAuditOrchestrator(
        settings_mgr=mgr,
        platform_adapter=MockPlatformAdapter(),
    )
    result = resumed.resume_campaign(init["store_path"])
    assert result["status"] == "SUCCESS"
    assert result["current_stage"] == "E3"
    assert result["current_phase"] is None
    assert resumed.stage_batch is None

def test_advance_surfaces_e3_isolation_backend_blocker(
    orchestrator_setup,
):
    orch, mgr, mock_platform, tmp = orchestrator_setup
    orch.initialize_campaign()
    assert orch.active_store_path is not None
    orch.api.prepare_stage(orch.active_store_path, "E1")
    orch.api.qualify_stage(orch.active_store_path, "E1")
    orch.api.prepare_stage(orch.active_store_path, "E2")
    orch.api.qualify_stage(orch.active_store_path, "E2")

    result = orch.advance_to_next_stage()
    assert result["status"] == "BLOCKED"
    assert result["current_stage"] == "E3"
    assert result["current_phase"] == "E3-BLIND"
    assert (
        result["next_action"]
        == "CONFIGURE_ENFORCED_ISOLATION_BACKEND"
    )
    assert "E3_ENFORCED_ISOLATION_BACKEND_REQUIRED" in result["reason"]
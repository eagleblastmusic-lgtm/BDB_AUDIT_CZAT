from __future__ import annotations

import json
import zipfile
from pathlib import Path

from bdb_audit.astra_flow_cli import run_flow_cli
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.workflow.astra_orchestrator import AstraContinuationOrchestrator
from bdb_audit.workflow.platform import MockPlatformAdapter
from bdb_audit.workflow.settings import SettingsManager
from bdb_audit.workflow.source_target import ResolvedSource


COMMIT = "3" * 40
TREE = "4" * 40


def _orchestrator(tmp_path: Path) -> AstraContinuationOrchestrator:
    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.settings.execution_mode = "ChatGPT / GitHub"
    mgr.settings.model = "Sol 5.6"
    mgr.settings.github_repo_url = "https://github.com/example/cli-target"
    mgr.settings.github_default_ref = "main"
    mgr.settings.output_work_dir = str(tmp_path / "work")
    mgr.settings.auto_copy_clipboard = False
    mgr.settings.auto_open_explorer = False
    mgr.settings.auto_open_zip_selector = False
    mgr.save()
    orch = AstraContinuationOrchestrator(
        settings_mgr=mgr,
        platform_adapter=MockPlatformAdapter(),
        api=AuditOperationApi(),
    )
    orch.resolved_source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/cli-target",
        display_name="example/cli-target",
        ref="main",
        exact_commit_sha=COMMIT,
        exact_tree_sha=TREE,
    )
    orch.initialize_campaign()
    return orch


def _e1_result(path: Path, job) -> Path:
    manifest = {
        "kind": "bdb_audit_lane_result",
        "version": "1",
        "campaign_id": job.campaign_id,
        "stage_id": "E1",
        "lane_slot": job.lane_slot,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "input_package_digest": job.package_digest,
        "source_commit_sha": job.source_commit_sha,
        "history_cut": job.input_history_cut,
        "assignment_ref": job.assignment_ref,
        "attempt_ref": job.attempt_ref,
        "findings_count": 0,
        "findings": [],
    }
    out = path / f"{job.lane_slot}_cli_result.zip"
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.json", canonical_bytes(manifest))
    return out


def test_flow_cli_resumes_same_store_and_prepares_real_e2_packages(tmp_path: Path, capsys) -> None:
    orch = _orchestrator(tmp_path)
    e1 = orch.prepare_e1_orchestration()
    summary = orch.import_results([_e1_result(tmp_path, job) for job in e1.jobs.values()])
    assert summary.stage_complete is True
    assert orch.active_store_path is not None

    rc = run_flow_cli(["advance", "--store", str(orch.active_store_path)])
    assert rc == 0
    advance = json.loads(capsys.readouterr().out)
    assert advance["status"] == "STAGE_READY"
    assert advance["current_stage"] == "E2"
    assert advance["lane_slots"] == ["E2-CONVERGENCE", "E2-ADJUDICATION"]

    rc = run_flow_cli(["status", "--store", str(orch.active_store_path)])
    assert rc == 0
    status = json.loads(capsys.readouterr().out)
    assert status["resume"]["current_stage"] == "E2"
    assert status["resume"]["post_e1_batch_loaded"] is True
    assert status["dashboard"]["stages"]["E1"] == "COMPLETE"
    assert status["dashboard"]["stages"]["E2"] == "IN_PROGRESS"

    rc = run_flow_cli(["packages", "--store", str(orch.active_store_path)])
    assert rc == 0
    packages = json.loads(capsys.readouterr().out)
    assert packages["stage_id"] == "E2"
    assert set(packages["packages"]) == {"E2-CONVERGENCE", "E2-ADJUDICATION"}
    assert all(Path(row["path"]).is_file() for row in packages["packages"].values())

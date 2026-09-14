from __future__ import annotations

import zipfile
from pathlib import Path

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.workflow.astra_orchestrator import AstraContinuationOrchestrator
from bdb_audit.workflow.platform import MockPlatformAdapter
from bdb_audit.workflow.settings import SettingsManager
from bdb_audit.workflow.source_target import ResolvedSource


COMMIT = "1" * 40
TREE = "2" * 40


def _settings(tmp_path: Path) -> SettingsManager:
    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.settings.execution_mode = "ChatGPT / GitHub"
    mgr.settings.model = "Sol 5.6"
    mgr.settings.github_repo_url = "https://github.com/example/target"
    mgr.settings.github_default_ref = "main"
    mgr.settings.output_work_dir = str(tmp_path / "work")
    mgr.settings.auto_copy_clipboard = False
    mgr.settings.auto_open_explorer = False
    mgr.settings.auto_open_zip_selector = False
    mgr.save()
    return mgr


def _source() -> ResolvedSource:
    return ResolvedSource(
        target_type="github",
        location="https://github.com/example/target",
        display_name="example/target",
        ref="main",
        exact_commit_sha=COMMIT,
        exact_tree_sha=TREE,
    )


def _result_zip(tmp_path: Path, job, *, suffix: str = "", findings: list[dict] | None = None, package_digest: str | None = None) -> Path:
    findings = [] if findings is None else findings
    manifest = {
        "kind": "bdb_audit_lane_result",
        "version": "1",
        "campaign_id": job.campaign_id,
        "stage_id": job.stage_id,
        "lane_slot": job.lane_slot,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "input_package_digest": package_digest or job.package_digest,
        "source_commit_sha": job.source_commit_sha,
        "history_cut": dict(job.input_history_cut),
        "assignment_ref": dict(job.assignment_ref),
        "attempt_ref": dict(job.attempt_ref),
        "findings_count": len(findings),
        "findings": findings,
    }
    path = tmp_path / f"{job.stage_id}_{job.lane_slot}{suffix}_RESULT.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.json", canonical_bytes(manifest))
    return path


def _start_real_e1(tmp_path: Path) -> tuple[AstraContinuationOrchestrator, SettingsManager]:
    settings = _settings(tmp_path)
    api = AuditOperationApi()
    orch = AstraContinuationOrchestrator(
        settings_mgr=settings,
        platform_adapter=MockPlatformAdapter(),
        api=api,
    )
    orch.resolved_source = _source()
    init = orch.initialize_campaign()
    assert init["status"] == "SUCCESS"
    batch = orch.prepare_e1_orchestration()
    assert tuple(batch.jobs) == ("E1-A", "E1-B", "E1-C", "E1-D", "E1-E")

    result_paths = [_result_zip(tmp_path, batch.get_job(slot)) for slot in batch.jobs]
    summary = orch.import_results(result_paths)
    assert summary.error is None
    assert summary.accepted_count == 5
    assert summary.stage_complete is True
    assert "E1" in api.get_campaign_status(init["store_path"])["stages_completed"]
    return orch, settings


def test_real_e1_to_e2_packages_partial_import_restart_and_completion(tmp_path: Path) -> None:
    orch, settings = _start_real_e1(tmp_path)

    transition = orch.advance_to_next_stage()
    assert transition["status"] == "STAGE_READY"
    assert transition["current_stage"] == "E2"
    assert transition["next_action"] == "DELIVER_STAGE_PACKAGES"
    assert transition["lane_slots"] == ["E2-CONVERGENCE", "E2-ADJUDICATION"]

    batch = orch.stage_batch
    assert batch is not None
    assert tuple(batch.jobs) == ("E2-CONVERGENCE", "E2-ADJUDICATION")
    for job in batch.jobs.values():
        assert job.package_zip_path.is_file()
        assert job.package_zip_path.with_suffix(".zip.sha256").is_file()
        assert job.required_isolation == "DECLARED"
        assert job.actual_isolation == "DECLARED"

    first = batch.get_job("E2-CONVERGENCE")
    first_zip = _result_zip(
        tmp_path,
        first,
        findings=[{
            "finding_id": "E2-CONVERGENCE-F01",
            "statement": "Evidence cross-review remains inconclusive without typed evidence refs",
            "severity": "MEDIUM",
            "affected_component": "workflow",
            "description": "Fixture finding bound to the exact durable E2 assignment.",
            "evidence_refs": [],
        }],
    )
    partial = orch.import_post_e1_results([first_zip])
    assert partial.accepted_count == 1
    assert partial.stage_complete is False
    assert partial.missing_lanes == ["E2-ADJUDICATION"]

    # Process restart: no in-memory batch/inbox survives.  Resume must derive
    # state from accepted history plus the exact package bytes on disk.
    resumed = AstraContinuationOrchestrator(
        settings_mgr=SettingsManager(settings.path),
        platform_adapter=MockPlatformAdapter(),
        api=AuditOperationApi(),
    )
    info = resumed.resume_campaign(orch.active_store_path)
    assert info["status"] == "SUCCESS"
    assert info["current_stage"] == "E2"
    assert info["post_e1_batch_loaded"] is True
    assert info["post_e1_accepted_lanes_count"] == 1
    assert info["post_e1_total_required_lanes"] == 2
    assert info["post_e1_missing_lanes"] == ["E2-ADJUDICATION"]

    resumed_batch = resumed.stage_batch
    assert resumed_batch is not None
    second = resumed_batch.get_job("E2-ADJUDICATION")
    second_zip = _result_zip(tmp_path, second)
    complete = resumed.import_post_e1_results([second_zip])
    assert complete.error is None
    assert complete.accepted_count == 2
    assert complete.stage_complete is True
    assert complete.completion_digest

    status = resumed.api.get_campaign_status(resumed.active_store_path)
    assert "E2" in status["stages_completed"]

    # Manual ChatGPT transport cannot be mislabeled as ENFORCED.  The next
    # normative blind stage therefore stops rather than silently weakening E3.
    next_transition = resumed.advance_to_next_stage()
    assert next_transition["status"] == "BLOCKED"
    assert next_transition["current_stage"] == "E3"
    assert next_transition["next_action"] == "CONFIGURE_ENFORCED_E3_EXECUTOR"
    assert "ENFORCED" in next_transition["reason"]


def test_post_e1_rejects_wrong_package_digest_without_stage_completion(tmp_path: Path) -> None:
    orch, _ = _start_real_e1(tmp_path)
    transition = orch.advance_to_next_stage()
    assert transition["status"] == "STAGE_READY"
    batch = orch.stage_batch
    assert batch is not None

    job = batch.get_job("E2-CONVERGENCE")
    bad_zip = _result_zip(tmp_path, job, suffix="_BAD", package_digest="0" * 64)
    result = orch.import_post_e1_results([bad_zip])
    assert result.accepted_count == 0
    assert result.stage_complete is False
    assert result.file_results[0].status == "REJECTED"
    assert result.file_results[0].code == "PACKAGE_DIGEST_MISMATCH"

    status = orch.api.get_campaign_status(orch.active_store_path)
    assert "E2" not in status["stages_completed"]


def test_e2_assignments_share_one_frozen_pre_delivery_cut(tmp_path: Path) -> None:
    orch, _ = _start_real_e1(tmp_path)
    transition = orch.advance_to_next_stage()
    assert transition["status"] == "STAGE_READY"
    batch = orch.stage_batch
    assert batch is not None

    cuts = [canonical_bytes(job.input_history_cut) for job in batch.jobs.values()]
    assert len(cuts) == 2
    assert cuts[0] == cuts[1]
    assert canonical_bytes(batch.frozen_history_cut) == cuts[0]
    assignment_digests = {job.assignment_ref["revision_digest"] for job in batch.jobs.values()}
    attempt_digests = {job.attempt_ref["revision_digest"] for job in batch.jobs.values()}
    assert len(assignment_digests) == 2
    assert len(attempt_digests) == 2

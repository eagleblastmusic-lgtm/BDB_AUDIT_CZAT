from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.canonical_json import canonical_bytes, parse
from bdb_audit.core.errors import ValidationError
from bdb_audit.workflow.astra_orchestrator import AstraContinuationOrchestrator
from bdb_audit.workflow.packaging import _deterministic_zip
from bdb_audit.workflow.platform import MockPlatformAdapter
from bdb_audit.workflow.settings import SettingsManager
from bdb_audit.workflow.source_target import ResolvedSource


COMMIT = "1" * 40
TREE = "2" * 40
E1_SLOTS = ("E1-A", "E1-B", "E1-C", "E1-D", "E1-E")


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


def _e1_result(tmp_path: Path, job) -> Path:
    finding = {
        "finding_id": f"{job.lane_slot}-F01",
        "statement": f"Observed finding from {job.lane_slot}",
        "severity": "MEDIUM",
        "affected_component": f"component/{job.lane_slot}",
        "description": "Accepted E1 fixture evidence for E2 context transport.",
        "evidence_refs": [],
    }
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
        "history_cut": dict(job.input_history_cut),
        "assignment_ref": dict(job.assignment_ref),
        "attempt_ref": dict(job.attempt_ref),
        "findings_count": 1,
        "findings": [finding],
    }
    path = tmp_path / f"{job.lane_slot}_RESULT.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.json", canonical_bytes(manifest))
    return path


def _start_e2(tmp_path: Path) -> tuple[AstraContinuationOrchestrator, SettingsManager]:
    settings = _settings(tmp_path)
    orch = AstraContinuationOrchestrator(
        settings_mgr=settings,
        platform_adapter=MockPlatformAdapter(),
        api=AuditOperationApi(),
    )
    orch.resolved_source = _source()
    assert orch.initialize_campaign()["status"] == "SUCCESS"
    e1 = orch.prepare_e1_orchestration()
    summary = orch.import_results([_e1_result(tmp_path, job) for job in e1.jobs.values()])
    assert summary.error is None
    assert summary.stage_complete is True
    transition = orch.advance_to_next_stage()
    assert transition["status"] == "STAGE_READY"
    assert transition["current_stage"] == "E2"
    return orch, settings


def _members(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path, "r") as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def test_e2_packages_bind_identical_accepted_e1_context(tmp_path: Path) -> None:
    orch, _ = _start_e2(tmp_path)
    assert orch.stage_batch is not None
    assert tuple(orch.stage_batch.jobs) == ("E2-CONVERGENCE", "E2-ADJUDICATION")

    contexts: list[bytes] = []
    for job in orch.stage_batch.jobs.values():
        members = _members(job.package_zip_path)
        assert set(members) == {
            "MANIFEST.json",
            "PACKAGE.json",
            "PROMPT.txt",
            "README.md",
            "CONTEXT.json",
        }
        manifest = parse(members["MANIFEST.json"])
        context = parse(members["CONTEXT.json"])
        assert manifest["format"] == "BDB-ASTRA-STAGE-PACKAGE-2"
        context_sha = hashlib.sha256(members["CONTEXT.json"]).hexdigest()
        assert manifest["context_sha256"] == context_sha
        assert context_sha.encode("ascii") in members["PROMPT.txt"]
        assert context["stage_id"] == "E2"
        assert context["predecessor_stage_id"] == "E1"
        assert context["blind"] is False
        assert context["knowledge_policy"] == "PREDECESSOR_ACCEPTED_RESULTS_ONLY"
        assert tuple(row["lane_slot"] for row in context["predecessor_results"]) == E1_SLOTS
        assert len(context["predecessor_results"]) == 5
        assert all(len(row["findings"]) == 1 for row in context["predecessor_results"])
        contexts.append(members["CONTEXT.json"])

    assert contexts[0] == contexts[1]


def test_resume_rejects_context_tamper_even_with_recomputed_zip_sidecar(tmp_path: Path) -> None:
    orch, settings = _start_e2(tmp_path)
    assert orch.stage_batch is not None
    job = orch.stage_batch.get_job("E2-CONVERGENCE")
    members = _members(job.package_zip_path)
    context = parse(members["CONTEXT.json"])
    context["predecessor_results"][0]["findings"][0]["statement"] = "TAMPERED"
    members["CONTEXT.json"] = canonical_bytes(context)
    tampered = _deterministic_zip(members)
    job.package_zip_path.write_bytes(tampered)
    raw_sha = hashlib.sha256(tampered).hexdigest()
    job.package_zip_path.with_suffix(".zip.sha256").write_text(
        f"{raw_sha}  {job.package_zip_path.name}\n",
        encoding="ascii",
    )

    resumed = AstraContinuationOrchestrator(
        settings_mgr=SettingsManager(settings.path),
        platform_adapter=MockPlatformAdapter(),
        api=AuditOperationApi(),
    )
    with pytest.raises(ValidationError, match="RESUME_CONTEXT_DIGEST_MISMATCH"):
        resumed.resume_campaign(orch.active_store_path)

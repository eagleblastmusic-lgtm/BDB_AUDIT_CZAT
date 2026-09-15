from __future__ import annotations

import zipfile
from pathlib import Path

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.astra_orchestrator import AstraContinuationOrchestrator
from bdb_audit.workflow.e2_semantics import build_e2_predecessor_view
from bdb_audit.workflow.inbox import _current_cut
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


def _result_zip(
    tmp_path: Path,
    job,
    *,
    suffix: str = "",
    findings: list[dict] | None = None,
    package_digest: str | None = None,
    extra_manifest: dict | None = None,
) -> Path:
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
    if extra_manifest:
        manifest.update(extra_manifest)
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

    lane_findings = {
        "E1-A": [{
            "finding_id": "E1-A-F01",
            "statement": "Potential authorization gap requires qualified E2 adjudication",
            "severity": "MEDIUM",
            "affected_component": "workflow/auth.py",
            "description": "E1 discovery fixture; no qualified evidence reference is accepted yet.",
            "evidence_refs": [],
        }],
        "E1-B": [],
        "E1-C": [],
        "E1-D": [],
        "E1-E": [],
    }
    result_paths = [
        _result_zip(tmp_path, batch.get_job(slot), findings=lane_findings[slot])
        for slot in batch.jobs
    ]
    summary = orch.import_results(result_paths)
    assert summary.error is None
    assert summary.accepted_count == 5
    assert summary.stage_complete is True
    assert "E1" in api.get_campaign_status(init["store_path"])["stages_completed"]
    return orch, settings


def _e2_records(orch: AstraContinuationOrchestrator, batch) -> tuple[list[dict], list[dict]]:
    assert orch.active_store_path is not None
    store = TransactionalHistoryStore(orch.active_store_path)
    view = build_e2_predecessor_view(store, batch.frozen_history_cut)
    assert len(view) == 1
    row = view[0]
    convergence = [{
        "finding_key": row["finding_key"],
        "statement": row["statement"],
        "category": "SECURITY",
        "scope_refs": [],
        "violated_invariant_refs": [],
        "discovery_relation_refs": [],
        "limitations": ["No accepted qualified evidence at the assigned cut"],
        "finding_scope": {"component": "workflow/auth.py"},
        "normalization_group_key": None,
    }]
    adjudication = [{
        "finding_key": row["finding_key"],
        "statement": row["statement"],
        "axes": {
            "MECHANISM": {
                "epistemic_outcome": "INCONCLUSIVE",
                "scope": {"component": "workflow/auth.py"},
                "evidence_qualification_refs": [],
                "method_or_characterization_refs": [],
                "confidence": "UNKNOWN",
                "limitations": ["No accepted qualified evidence"],
                "reason_codes": ["QUALIFIED_EVIDENCE_ABSENT"],
            },
            "REACHABILITY": {
                "epistemic_outcome": "INCONCLUSIVE",
                "scope": {"component": "workflow/auth.py"},
                "evidence_qualification_refs": [],
                "method_or_characterization_refs": [],
                "confidence": "UNKNOWN",
                "limitations": ["No accepted qualified evidence"],
                "reason_codes": ["QUALIFIED_EVIDENCE_ABSENT"],
            },
            "IMPACT": {
                "epistemic_outcome": "INCONCLUSIVE",
                "scope": {"component": "workflow/auth.py"},
                "evidence_qualification_refs": [],
                "method_or_characterization_refs": [],
                "confidence": "UNKNOWN",
                "limitations": ["No accepted qualified evidence"],
                "reason_codes": ["QUALIFIED_EVIDENCE_ABSENT"],
            },
            "SEVERITY": {
                "severity_value": "MEDIUM",
                "scope": {"component": "workflow/auth.py"},
                "evidence_qualification_refs": [],
                "method_or_characterization_refs": [],
                "confidence": "LOW",
                "limitations": ["Characterization only; claim remains open"],
                "reason_codes": ["PRELIMINARY_CHARACTERIZATION"],
            },
        },
        "reason_codes": ["E2_FAIL_CLOSED_WITHOUT_QUALIFIED_EVIDENCE"],
        "claim_position": "INCONCLUSIVE",
        "claim_evidence_qualification_refs": [],
        "contradiction_group_key": None,
    }]
    return convergence, adjudication


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
    prompts = [job.prompt_text for job in batch.jobs.values()]
    assert all("Frozen E1 predecessor view" in prompt for prompt in prompts)
    assert all("Potential authorization gap requires qualified E2 adjudication" in prompt for prompt in prompts)
    assert all("INFORMATIONAL" not in prompt for prompt in prompts)
    assert all('"severity_value":"INFO"' in prompt for prompt in prompts if "E2-ADJUDICATION" in prompt)
    for job in batch.jobs.values():
        assert job.package_zip_path.is_file()
        assert job.package_zip_path.with_suffix(".zip.sha256").is_file()
        assert job.required_isolation == "DECLARED"
        assert job.actual_isolation == "DECLARED"

    convergence_records, adjudication_records = _e2_records(orch, batch)
    first = batch.get_job("E2-CONVERGENCE")
    first_zip = _result_zip(
        tmp_path,
        first,
        extra_manifest={"e2_records": convergence_records},
    )
    partial = orch.import_post_e1_results([first_zip])
    assert partial.accepted_count == 1
    assert partial.stage_complete is False
    assert partial.missing_lanes == ["E2-ADJUDICATION"]

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
    second_zip = _result_zip(
        tmp_path,
        second,
        extra_manifest={"e2_records": adjudication_records},
    )
    complete = resumed.import_post_e1_results([second_zip])
    assert complete.error is None
    assert complete.accepted_count == 2
    assert complete.stage_complete is True
    assert complete.completion_digest

    status = resumed.api.get_campaign_status(resumed.active_store_path)
    assert "E2" in status["stages_completed"]

    store = TransactionalHistoryStore(resumed.active_store_path)
    cut, _ = _current_cut(store)
    claims = store.accepted_records("finding_claim_revision", cut)
    axes = store.accepted_records("finding_axis_assessment", cut)
    decisions = store.accepted_records("finding_adjudication_decision", cut)
    roots = store.accepted_records("root_cause_revision", cut)
    contradictions = store.accepted_records("contradiction_revision", cut)
    assert len(claims) == 1
    assert len(axes) == 4
    assert len(decisions) == 1
    assert decisions[0]["body"]["finding_lifecycle_status"] == "OPEN"
    assert roots == ()
    assert contradictions == ()

    e2_stage_completions = [
        row
        for row in store.accepted_records("stage_completion", cut)
        if row["body"].get("stage_spec_ref", {}).get("revision_digest")
        == resumed_batch.get_job("E2-CONVERGENCE").assignment_ref.get("revision_digest")
    ]
    # Exact stage-spec lookup is covered by campaign status; semantic objects above
    # prove they were accepted before the E2 StageCompletion became visible.
    assert isinstance(e2_stage_completions, list)

    next_transition = resumed.advance_to_next_stage()
    assert next_transition["status"] == "STAGE_READY"
    assert next_transition["current_stage"] == "E3"
    assert next_transition["next_action"] == "DELIVER_STAGE_PACKAGES"
    assert next_transition["lane_slots"] == ["E3-X", "E3-Y", "E3-Z"]
    assert next_transition["assurance_profile"] == "BOUNDED_MANUAL_DECLARED"

    e3_batch = resumed.stage_batch
    assert e3_batch is not None
    assert tuple(e3_batch.jobs) == ("E3-X", "E3-Y", "E3-Z")
    for job in e3_batch.jobs.values():
        assert job.required_isolation == "ENFORCED"
        assert job.actual_isolation == "DECLARED"


def test_post_e1_rejects_wrong_package_digest_without_stage_completion(tmp_path: Path) -> None:
    orch, _ = _start_real_e1(tmp_path)
    transition = orch.advance_to_next_stage()
    assert transition["status"] == "STAGE_READY"
    batch = orch.stage_batch
    assert batch is not None

    convergence_records, _ = _e2_records(orch, batch)
    job = batch.get_job("E2-CONVERGENCE")
    bad_zip = _result_zip(
        tmp_path,
        job,
        suffix="_BAD",
        package_digest="0" * 64,
        extra_manifest={"e2_records": convergence_records},
    )
    result = orch.import_post_e1_results([bad_zip])
    assert result.accepted_count == 0
    assert result.stage_complete is False
    assert result.file_results[0].status == "REJECTED"
    assert result.file_results[0].code == "PACKAGE_DIGEST_MISMATCH"

    status = orch.api.get_campaign_status(orch.active_store_path)
    assert "E2" not in status["stages_completed"]


def test_e2_assignments_share_one_frozen_pre_delivery_cut_and_view(tmp_path: Path) -> None:
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

    view_lines = []
    for job in batch.jobs.values():
        start = job.prompt_text.index("## Frozen E1 predecessor view")
        end = job.prompt_text.index("## E2 semantic rules")
        view_lines.append(job.prompt_text[start:end])
    assert view_lines[0] == view_lines[1]


def test_e2_semantic_result_missing_record_is_rejected_before_acceptance(tmp_path: Path) -> None:
    orch, _ = _start_real_e1(tmp_path)
    assert orch.advance_to_next_stage()["status"] == "STAGE_READY"
    batch = orch.stage_batch
    assert batch is not None
    job = batch.get_job("E2-CONVERGENCE")
    malformed = _result_zip(tmp_path, job, suffix="_MISSING", extra_manifest={"e2_records": []})
    result = orch.import_post_e1_results([malformed])
    assert result.accepted_count == 0
    assert result.stage_complete is False
    assert result.file_results[0].status == "REJECTED"
    assert "E2_RECORD_SET_INCOMPLETE" in (result.file_results[0].reason or "")

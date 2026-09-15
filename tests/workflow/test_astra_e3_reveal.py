from __future__ import annotations

import zipfile
from pathlib import Path

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.canonical_json import canonical_bytes, parse
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.astra_orchestrator import AstraContinuationOrchestrator
from bdb_audit.workflow.e2_semantics import build_e2_predecessor_view
from bdb_audit.workflow.platform import MockPlatformAdapter
from bdb_audit.workflow.settings import SettingsManager
from bdb_audit.workflow.source_target import ResolvedSource


COMMIT = "1" * 40
TREE = "2" * 40
E1_SLOTS = ("E1-A", "E1-B", "E1-C", "E1-D", "E1-E")
E3_SLOTS = ("E3-X", "E3-Y", "E3-Z")


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
    findings: list[dict] | None = None,
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
        "input_package_digest": job.package_digest,
        "source_commit_sha": job.source_commit_sha,
        "history_cut": dict(job.input_history_cut),
        "assignment_ref": dict(job.assignment_ref),
        "attempt_ref": dict(job.attempt_ref),
        "findings_count": len(findings),
        "findings": findings,
    }
    if extra_manifest:
        manifest.update(extra_manifest)
    path = tmp_path / f"{job.stage_id}_{job.lane_slot}_RESULT.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.json", canonical_bytes(manifest))
    return path


def _members(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path, "r") as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _start_e2(tmp_path: Path) -> AstraContinuationOrchestrator:
    orch = AstraContinuationOrchestrator(
        settings_mgr=_settings(tmp_path),
        platform_adapter=MockPlatformAdapter(),
        api=AuditOperationApi(),
    )
    orch.resolved_source = _source()
    init = orch.initialize_campaign()
    assert init["status"] == "SUCCESS"

    e1 = orch.prepare_e1_orchestration()
    assert tuple(e1.jobs) == E1_SLOTS
    result_paths = []
    for slot, job in e1.jobs.items():
        findings = []
        if slot == "E1-A":
            findings = [{
                "finding_id": "E1-A-F01",
                "statement": "Potential authorization gap requires qualified E2 adjudication",
                "severity": "MEDIUM",
                "affected_component": "workflow/auth.py",
                "description": "E1 discovery fixture for E3 reveal qualification.",
                "evidence_refs": [],
            }]
        result_paths.append(_result_zip(tmp_path, job, findings=findings))

    e1_summary = orch.import_results(result_paths)
    assert e1_summary.error is None
    assert e1_summary.stage_complete is True

    transition = orch.advance_to_next_stage()
    assert transition["status"] == "STAGE_READY"
    assert transition["current_stage"] == "E2"
    return orch


def _e2_records(orch: AstraContinuationOrchestrator) -> tuple[list[dict], list[dict]]:
    assert orch.active_store_path is not None
    assert orch.stage_batch is not None
    store = TransactionalHistoryStore(orch.active_store_path)
    view = build_e2_predecessor_view(store, orch.stage_batch.frozen_history_cut)
    assert len(view) == 1
    row = view[0]
    scope = {"component": "workflow/auth.py"}

    convergence = [{
        "finding_key": row["finding_key"],
        "statement": row["statement"],
        "category": "SECURITY",
        "scope_refs": [],
        "violated_invariant_refs": [],
        "discovery_relation_refs": [],
        "limitations": ["No accepted qualified evidence at the assigned cut"],
        "finding_scope": scope,
        "normalization_group_key": None,
    }]
    adjudication = [{
        "finding_key": row["finding_key"],
        "statement": row["statement"],
        "axes": {
            "MECHANISM": {
                "epistemic_outcome": "INCONCLUSIVE",
                "scope": scope,
                "evidence_qualification_refs": [],
                "method_or_characterization_refs": [],
                "confidence": "UNKNOWN",
                "limitations": ["No accepted qualified evidence"],
                "reason_codes": ["QUALIFIED_EVIDENCE_ABSENT"],
            },
            "REACHABILITY": {
                "epistemic_outcome": "INCONCLUSIVE",
                "scope": scope,
                "evidence_qualification_refs": [],
                "method_or_characterization_refs": [],
                "confidence": "UNKNOWN",
                "limitations": ["No accepted qualified evidence"],
                "reason_codes": ["QUALIFIED_EVIDENCE_ABSENT"],
            },
            "IMPACT": {
                "epistemic_outcome": "INCONCLUSIVE",
                "scope": scope,
                "evidence_qualification_refs": [],
                "method_or_characterization_refs": [],
                "confidence": "UNKNOWN",
                "limitations": ["No accepted qualified evidence"],
                "reason_codes": ["QUALIFIED_EVIDENCE_ABSENT"],
            },
            "SEVERITY": {
                "severity_value": "MEDIUM",
                "scope": scope,
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


def _complete_e2_and_prepare_e3(
    tmp_path: Path,
    orch: AstraContinuationOrchestrator,
) -> None:
    assert orch.stage_batch is not None
    convergence, adjudication = _e2_records(orch)
    e2_paths = []
    for slot, job in orch.stage_batch.jobs.items():
        records = convergence if slot == "E2-CONVERGENCE" else adjudication
        e2_paths.append(_result_zip(tmp_path, job, extra_manifest={"e2_records": records}))

    e2_summary = orch.import_post_e1_results(e2_paths)
    assert e2_summary.error is None
    assert e2_summary.stage_complete is True

    transition = orch.advance_to_next_stage()
    assert transition["status"] == "STAGE_READY"
    assert transition["current_stage"] == "E3"
    assert transition["lane_slots"] == list(E3_SLOTS)
    assert transition["assurance_profile"] == "BOUNDED_MANUAL_DECLARED"


def _stage_completion_for(
    store: TransactionalHistoryStore,
    cut: dict,
    stage_key: str,
) -> dict:
    stage_specs = {
        row["ref"]["revision_digest"]: row["body"].get("stage_key")
        for row in store.accepted_records("stage_spec", cut)
    }
    matches = [
        row
        for row in store.accepted_records("stage_completion", cut)
        if stage_specs.get(row["body"].get("stage_spec_ref", {}).get("revision_digest")) == stage_key
    ]
    assert len(matches) == 1
    return matches[0]


def test_e3_results_are_sealed_before_controlled_e4_reveal(tmp_path: Path) -> None:
    orch = _start_e2(tmp_path)
    _complete_e2_and_prepare_e3(tmp_path, orch)

    e3_batch = orch.stage_batch
    assert e3_batch is not None
    assert tuple(e3_batch.jobs) == E3_SLOTS

    # E3 receives only predecessor completion identity.  No E2 finding/result
    # body is exposed before the independent E3 work is returned and sealed.
    for job in e3_batch.jobs.values():
        assert job.required_isolation == "ENFORCED"
        assert job.actual_isolation == "DECLARED"
        context = parse(_members(job.package_zip_path)["CONTEXT.json"])
        assert context["stage_id"] == "E3"
        assert context["predecessor_stage_id"] == "E2"
        assert context["blind"] is True
        assert context["knowledge_policy"] == "BLIND_NO_PRIOR_RESULT_CONTENT"
        assert context["predecessor_results"] == []

    expected_statements: dict[str, str] = {}
    e3_paths = []
    for slot, job in e3_batch.jobs.items():
        statement = f"Blind E3 discovery from {slot}"
        expected_statements[slot] = statement
        findings = [{
            "finding_id": f"{slot}-F01",
            "statement": statement,
            "severity": "MEDIUM",
            "affected_component": f"component/{slot}",
            "description": "Independent E3 discovery fixture sealed before reveal.",
            "evidence_refs": [],
        }]
        e3_paths.append(_result_zip(tmp_path, job, findings=findings))

    e3_summary = orch.import_post_e1_results(e3_paths)
    assert e3_summary.error is None
    assert e3_summary.accepted_count == 3
    assert e3_summary.stage_complete is True
    assert e3_summary.completion_digest

    assert orch.active_store_path is not None
    store = TransactionalHistoryStore(orch.active_store_path)
    head = store.head()
    assert head is not None
    cut = {
        "campaign_id": head.campaign_id,
        "accepted_head_seq": head.commit_seq,
        "accepted_head_hash": head.commit_hash,
    }
    e3_completion = _stage_completion_for(store, cut, "E3")
    completion_body = e3_completion["body"]
    summary = completion_body["mandatory_obligation_summary"]
    assert summary["required_lanes"] == 3
    assert summary["completed_lanes"] == 3
    assert summary["required_isolation_assurance"] == "ENFORCED"
    assert summary["observed_isolation_assurance"] == "DECLARED"
    assert summary["blind_origin_eligible_count"] == 0
    assert summary["unknown_isolation_discoveries_count"] == 3
    assert summary["assurance_limitation_codes"] == [
        "BDB_DOES_NOT_ENFORCE_EXTERNAL_CHAT_BOUNDARIES"
    ]
    assert completion_body["unknown_blocked_summary"]["assurance_profile"] == "BOUNDED_MANUAL_DECLARED"

    discovery_refs = [
        ref
        for ref in completion_body["required_output_refs"]
        if isinstance(ref, dict) and ref.get("kind") == "discovery_record"
    ]
    checkpoint_refs = [
        ref
        for ref in completion_body["required_output_refs"]
        if isinstance(ref, dict) and ref.get("kind") == "checkpoint"
    ]
    assert len(discovery_refs) == 3
    assert len(checkpoint_refs) == 1
    checkpoint = store.resolve_accepted(checkpoint_refs[0], cut)
    assert checkpoint["body"]["sealed_findings_count"] == 3
    assert tuple(checkpoint["body"]["lane_slots"]) == E3_SLOTS

    transition = orch.advance_to_next_stage()
    assert transition["status"] == "STAGE_READY"
    assert transition["current_stage"] == "E4"
    assert transition["lane_slots"] == ["E4-DEEPEN"]

    e4_batch = orch.stage_batch
    assert e4_batch is not None
    e4_job = e4_batch.get_job("E4-DEEPEN")
    e4_context = parse(_members(e4_job.package_zip_path)["CONTEXT.json"])
    assert e4_context["stage_id"] == "E4"
    assert e4_context["predecessor_stage_id"] == "E3"
    assert e4_context["blind"] is False
    assert e4_context["knowledge_policy"] == "PREDECESSOR_ACCEPTED_RESULTS_ONLY"
    assert e4_context["predecessor_stage_completion_ref"]["revision_digest"] == e3_completion["ref"]["revision_digest"]

    revealed = e4_context["predecessor_results"]
    assert tuple(row["lane_slot"] for row in revealed) == E3_SLOTS
    assert {
        row["lane_slot"]: row["findings"][0]["statement"]
        for row in revealed
    } == expected_statements

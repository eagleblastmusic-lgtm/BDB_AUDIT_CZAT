from __future__ import annotations

import json
from pathlib import Path
import zipfile

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.registry import canonical_reference_set
from bdb_audit.history.objects import HistoryCut
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS
from bdb_audit.schemas.orchestration import orchestration_schema
from bdb_audit.workflow.assignments import AssignmentService
from bdb_audit.workflow.inbox import E1ResultInbox
from bdb_audit.workflow.packaging import prepare_e1_batch
from bdb_audit.workflow.source_target import ResolvedSource


def _campaign(tmp_path: Path, seed: str) -> TransactionalHistoryStore:
    db = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(db, seed=seed)
    api.prepare_stage(db, "E1")
    for slot in E1_LANE_SLOTS:
        api.prepare_lane(db, "E1", slot=slot)
    return TransactionalHistoryStore(db)


def _prepared_batch(tmp_path: Path):
    store = _campaign(tmp_path, "ru03-authority-bindings")
    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/ru03-bindings",
        display_name="example/ru03-bindings",
        ref="main",
        exact_commit_sha="c" * 40,
    )
    batch = prepare_e1_batch(store, tmp_path / "audit_work", source)
    return store, batch


def _manifest(batch, slot: str) -> dict:
    job = batch.get_job(slot)
    return {
        "kind": "bdb_audit_lane_result",
        "version": "1",
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": slot,
        "source_commit_sha": batch.source_commit_sha,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "input_package_digest": job.package_digest,
        "history_cut": dict(batch.frozen_history_cut),
        "findings": [
            {
                "finding_id": f"{slot}-authority-01",
                "statement": "Authority binding regression probe",
                "claim_outcome": "SUPPORTED",
            }
        ],
    }


def _write_result(path: Path, manifest: dict) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("MANIFEST.json", json.dumps(manifest))
    return path


def test_lane_result_findings_count_contract_is_nonnegative_integer() -> None:
    schema = orchestration_schema("bdb_audit_lane_result")
    assert schema is not None
    assert schema["properties"]["findings_count"] == {"type": "integer", "minimum": 0}


def test_assignment_producers_use_consumer_specific_reference_classes(tmp_path: Path) -> None:
    store = _campaign(tmp_path, "ru03-ref-classes")
    prepared = AssignmentService(store).prepare_e1_assignments(
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    )
    cut = prepared.accepted_history_cut

    stage_runs = store.accepted_records("stage_run", cut)
    assert len(stage_runs) == 1
    stage_run = stage_runs[0]["body"]
    assert stage_run["source_generation_ref"]["ref_class"] == "PRIOR_ACCEPTED_ONLY"
    stage_slot_refs = stage_run["required_lane_slot_contract_refs"]
    assert stage_slot_refs == canonical_reference_set(stage_slot_refs)
    assert {ref["ref_class"] for ref in stage_slot_refs} == {"HISTORY_CONTEXT_BINDING"}

    lane_runs = store.accepted_records("lane_run", cut)
    assert len(lane_runs) == len(E1_LANE_SLOTS)
    assert all(
        row["body"]["source_generation_ref"]["ref_class"] == "PRIOR_ACCEPTED_ONLY"
        for row in lane_runs
    )
    assert all(
        {ref["ref_class"] for ref in row["body"]["required_result_slots"]}
        == {"HISTORY_CONTEXT_BINDING"}
        for row in lane_runs
    )

    attempts = store.accepted_records("attempt", cut)
    assert len(attempts) == len(E1_LANE_SLOTS)
    assert all(
        {ref["ref_class"] for ref in row["body"]["result_slot_contracts"]}
        == {"HISTORY_CONTEXT_BINDING"}
        for row in attempts
    )

    assignments = store.accepted_records("assignment_manifest", cut)
    assert len(assignments) == len(E1_LANE_SLOTS)
    assert all(
        row["body"]["source_generation_ref"]["ref_class"] == "CONTENT_OR_PRIOR"
        for row in assignments
    )
    assert all(
        {ref["ref_class"] for ref in row["body"]["result_slot_contract_refs"]}
        == {"CONTENT_OR_PRIOR"}
        for row in assignments
    )


def test_import_canonicalizes_partial_matching_history_cut_to_assignment_cut(tmp_path: Path) -> None:
    store, batch = _prepared_batch(tmp_path)
    inbox = E1ResultInbox(store, batch)
    manifest = _manifest(batch, "E1-A")
    full_cut = dict(batch.frozen_history_cut)
    manifest["history_cut"] = {
        "campaign_id": full_cut["campaign_id"],
        "accepted_head_seq": full_cut["accepted_head_seq"],
        "accepted_head_hash": full_cut["accepted_head_hash"],
    }
    result_path = _write_result(tmp_path / "partial_cut.zip", manifest)

    slot, status, reason = inbox.ingest_zip(result_path)
    assert slot == "E1-A"
    assert status == "ACCEPTED", reason

    head = store.head()
    assert head is not None
    commit = store.commits()[-1]
    accepted_cut = HistoryCut.accepted(
        head,
        commit["governing_policy_ref"],
        commit["governing_spec_refs"],
    ).as_dict()
    rows = store.accepted_records("bdb_audit_lane_result", accepted_cut)
    assert len(rows) == 1
    assert rows[0]["body"]["history_cut"] == full_cut
    assert rows[0]["body"]["findings_count"] == 1

    completions = store.accepted_records("lane_completion", accepted_cut)
    assert len(completions) == 1
    completion = completions[0]["body"]
    assert completion["lane_run_ref"]["ref_class"] == "CONTENT_OR_PRIOR"
    assert completion["final_knowledge_state_ref"]["ref_class"] == "CONTENT_OR_PRIOR"
    assert completion["isolation_qualification_ref"]["ref_class"] == "CONTENT_OR_PRIOR"
    assert {ref["ref_class"] for ref in completion["attempt_refs"]} == {"CONTENT_OR_PRIOR"}
    assert completion["lane_spec_ref"]["ref_class"] == "HISTORY_CONTEXT_BINDING"
    assert {ref["ref_class"] for ref in completion["required_output_refs"]} == {"CONTENT_OR_PRIOR"}


def test_import_rejects_conflicting_non_identity_history_cut_field(tmp_path: Path) -> None:
    store, batch = _prepared_batch(tmp_path)
    inbox = E1ResultInbox(store, batch)
    manifest = _manifest(batch, "E1-A")
    bad_cut = dict(batch.frozen_history_cut)
    bad_cut["governing_policy_ref"] = {"tampered": True}
    manifest["history_cut"] = bad_cut
    result_path = _write_result(tmp_path / "conflicting_cut.zip", manifest)

    slot, status, reason = inbox.ingest_zip(result_path)
    assert slot == "E1-A"
    assert status == "REJECTED"
    assert reason is not None and "STALE_CUT" in reason

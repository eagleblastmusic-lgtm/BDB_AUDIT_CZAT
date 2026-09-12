from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.history.objects import HistoryCut
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS
from bdb_audit.workflow.inbox import E1ResultInbox
from bdb_audit.workflow.packaging import prepare_e1_batch
from bdb_audit.workflow.source_target import ResolvedSource


def _prepared(tmp_path: Path):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(store_path, seed="ru03-result-roundtrip")
    api.prepare_stage(store_path, "E1")
    for slot in E1_LANE_SLOTS:
        api.prepare_lane(store_path, "E1", slot=slot)
    store = TransactionalHistoryStore(store_path)
    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/ru03-roundtrip",
        display_name="example/ru03-roundtrip",
        ref="main",
        exact_commit_sha="d" * 40,
    )
    batch = prepare_e1_batch(store, tmp_path / "work", source)
    return store, batch


def _accepted_cut(store: TransactionalHistoryStore) -> dict:
    head = store.head()
    assert head is not None
    commit = store.commits()[-1]
    return HistoryCut.accepted(
        head,
        commit["governing_policy_ref"],
        commit["governing_spec_refs"],
    ).as_dict()


def _manifest(batch, slot: str, *, statement: str = "Durable finding") -> dict:
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
        "assignment_ref": dict(job.assignment_ref),
        "attempt_ref": dict(job.attempt_ref),
        "findings_count": 1,
        "findings": [
            {
                "finding_id": f"{slot}-D02",
                "statement": statement,
                "severity": "HIGH",
                "affected_component": "src/example.py",
                "description": "Unique D02 persistence evidence marker",
            }
        ],
    }


def _write_result(path: Path, manifest: dict, evidence: bytes = b"evidence-marker\n") -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("MANIFEST.json", json.dumps(manifest, separators=(",", ":")))
        archive.writestr("EVIDENCE.txt", evidence)
    return path


def test_d02_full_finding_and_evidence_roundtrip_survives_reopen(tmp_path: Path) -> None:
    store, batch = _prepared(tmp_path)
    inbox = E1ResultInbox(store, batch)
    evidence = b"exact durable evidence bytes\x00\x01\n"
    result_path = _write_result(tmp_path / "result.zip", _manifest(batch, "E1-A"), evidence)
    raw_zip = result_path.read_bytes()

    slot, status, reason = inbox.ingest_zip(result_path)
    assert (slot, status, reason) == ("E1-A", "ACCEPTED", None)

    reopened_store = TransactionalHistoryStore(store.path)
    rows = reopened_store.accepted_records("bdb_audit_lane_result", _accepted_cut(reopened_store))
    assert len(rows) == 1
    body = rows[0]["body"]
    finding = body["findings"][0]
    assert finding["statement"] == "Durable finding"
    assert finding["severity"] == "HIGH"
    assert finding["affected_component"] == "src/example.py"
    assert finding["description"] == "Unique D02 persistence evidence marker"
    assert body["raw_result_digest"] == hashlib.sha256(raw_zip).hexdigest()
    assert body["raw_result_byte_length"] == len(raw_zip)

    evidence_entry = next(item for item in body["evidence_files"] if item["path"] == "EVIDENCE.txt")
    assert evidence_entry["raw_digest"] == hashlib.sha256(evidence).hexdigest()
    reopened_inbox = E1ResultInbox(reopened_store, batch)
    assert reopened_inbox.vault.read_bytes(evidence_entry["raw_digest"]) == evidence
    assert reopened_inbox.lane_statuses["E1-A"].findings[0]["statement"] == "Durable finding"


def test_d19_batch_import_preserves_foreign_file_rejection_diagnostic(tmp_path: Path) -> None:
    store, batch = _prepared(tmp_path)
    inbox = E1ResultInbox(store, batch)
    manifest = _manifest(batch, "E1-A")
    manifest["campaign_id"] = "campaign_FOREIGN"
    result_path = _write_result(tmp_path / "foreign.zip", manifest)

    summary = inbox.ingest_multiple_zips([result_path])
    assert summary.accepted_count == 0
    assert len(summary.file_results) == 1
    report = summary.file_results[0]
    assert report.path == str(result_path.resolve())
    assert report.status == "REJECTED"
    assert report.code == "FOREIGN_CAMPAIGN"
    assert report.reason is not None and batch.campaign_id in report.reason
    assert report.raw_digest == hashlib.sha256(result_path.read_bytes()).hexdigest()
    assert report.next_action == "SELECT_CORRECT_CAMPAIGN"


def test_d06_fresh_inbox_exact_retry_and_conflicting_payload_are_persisted(tmp_path: Path) -> None:
    store, batch = _prepared(tmp_path)
    first_inbox = E1ResultInbox(store, batch)
    stale_peer = E1ResultInbox(TransactionalHistoryStore(store.path), batch)
    first_path = _write_result(tmp_path / "first.zip", _manifest(batch, "E1-A", statement="First accepted result"))
    conflicting_path = _write_result(
        tmp_path / "conflicting.zip",
        _manifest(batch, "E1-A", statement="Different result for same assignment"),
        b"different evidence\n",
    )

    assert first_inbox.ingest_zip(first_path)[1] == "ACCEPTED"

    fresh_retry = E1ResultInbox(TransactionalHistoryStore(store.path), batch)
    retry_slot, retry_status, retry_reason = fresh_retry.ingest_zip(first_path)
    assert (retry_slot, retry_status, retry_reason) == ("E1-A", "ACCEPTED", None)
    assert fresh_retry._last_file_result is not None
    assert fresh_retry._last_file_result.code == "EXACT_RETRY"

    conflict_slot, conflict_status, conflict_reason = stale_peer.ingest_zip(conflicting_path)
    assert conflict_slot == "E1-A"
    assert conflict_status == "REJECTED"
    assert conflict_reason is not None and "CONFLICTING_RESULT_REJECTED" in conflict_reason

    rows = TransactionalHistoryStore(store.path).accepted_records(
        "bdb_audit_lane_result",
        _accepted_cut(TransactionalHistoryStore(store.path)),
    )
    assert len(rows) == 1
    assert rows[0]["body"]["findings"][0]["statement"] == "First accepted result"

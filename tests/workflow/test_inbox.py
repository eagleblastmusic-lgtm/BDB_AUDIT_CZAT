"""Targeted tests for E1ResultInbox and multi-ZIP ingestion security."""
from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile
import pytest

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS
from bdb_audit.workflow.source_target import ResolvedSource
from bdb_audit.workflow.packaging import prepare_e1_batch
from bdb_audit.workflow.inbox import E1ResultInbox


@pytest.fixture
def inbox_setup(tmp_path: Path):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(store_path, seed="inbox_test_seed")
    api.prepare_stage(store_path, "E1")
    for slot in E1_LANE_SLOTS:
        api.prepare_lane(store_path, "E1", slot=slot)

    store = TransactionalHistoryStore(store_path)
    out_dir = tmp_path / "audit_work"
    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/inbox-repo",
        display_name="example/inbox-repo",
        ref="main",
        exact_commit_sha="b" * 40,
    )
    batch = prepare_e1_batch(store, out_dir, source)
    inbox = E1ResultInbox(store, batch)
    return store, batch, inbox, tmp_path


def _create_result_zip(
    out_path: Path,
    manifest_data: dict,
    extra_files: dict[str, str] | None = None,
) -> Path:
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.json", json.dumps(manifest_data, indent=2))
        if extra_files:
            for fname, content in extra_files.items():
                zf.writestr(fname, content)
    return out_path


def _valid_manifest_for_lane(batch, slot: str) -> dict:
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
        "history_cut": batch.frozen_history_cut,
        "findings": [
            {
                "finding_id": f"{slot}-01",
                "statement": f"Valid finding for {slot}",
                "claim_outcome": "SUPPORTED",
            }
        ],
    }


def test_multi_zips_order_independent_matching(inbox_setup):
    store, batch, inbox, tmp = inbox_setup

    # Create all 5 valid result ZIPs in arbitrary order (E1-C, E1-A, E1-E, E1-B, E1-D)
    order = ["E1-C", "E1-A", "E1-E", "E1-B", "E1-D"]
    zip_paths = []
    for slot in order:
        p = tmp / f"result_{slot}.zip"
        _create_result_zip(p, _valid_manifest_for_lane(batch, slot))
        zip_paths.append(p)

    summary = inbox.ingest_multiple_zips(zip_paths)
    assert summary.accepted_count == 5
    assert len(summary.missing_lanes) == 0
    assert summary.stage_complete is True
    assert summary.completion_digest is not None
    assert len(summary.completion_digest) == 64


def test_missing_lane_reports_waiting(inbox_setup):
    store, batch, inbox, tmp = inbox_setup

    # Provide only 4 of 5 lanes (omit E1-C)
    zip_paths = []
    for slot in ("E1-A", "E1-B", "E1-D", "E1-E"):
        p = tmp / f"partial_{slot}.zip"
        _create_result_zip(p, _valid_manifest_for_lane(batch, slot))
        zip_paths.append(p)

    summary = inbox.ingest_multiple_zips(zip_paths)
    assert summary.accepted_count == 4
    assert summary.missing_lanes == ["E1-C"]
    assert summary.stage_complete is False


def test_foreign_campaign_rejected(inbox_setup):
    store, batch, inbox, tmp = inbox_setup
    p = tmp / "foreign.zip"
    bad_manifest = _valid_manifest_for_lane(batch, "E1-A")
    bad_manifest["campaign_id"] = "campaign_FOREIGN_12345"
    _create_result_zip(p, bad_manifest)

    slot, status, reason = inbox.ingest_zip(p)
    assert status == "REJECTED"
    assert "FOREIGN_CAMPAIGN" in reason


def test_wrong_stage_rejected(inbox_setup):
    store, batch, inbox, tmp = inbox_setup
    p = tmp / "wrong_stage.zip"
    bad_manifest = _valid_manifest_for_lane(batch, "E1-A")
    bad_manifest["stage_id"] = "E2"
    _create_result_zip(p, bad_manifest)

    slot, status, reason = inbox.ingest_zip(p)
    assert status == "REJECTED"
    assert "WRONG_STAGE" in reason


def test_wrong_lane_slot_rejected(inbox_setup):
    store, batch, inbox, tmp = inbox_setup
    p = tmp / "wrong_lane.zip"
    bad_manifest = _valid_manifest_for_lane(batch, "E1-A")
    bad_manifest["lane_slot"] = "E1-Z"
    _create_result_zip(p, bad_manifest)

    slot, status, reason = inbox.ingest_zip(p)
    assert status == "REJECTED"
    assert "UNKNOWN_LANE" in reason


def test_stale_history_cut_rejected(inbox_setup):
    store, batch, inbox, tmp = inbox_setup
    p = tmp / "stale_cut.zip"
    bad_manifest = _valid_manifest_for_lane(batch, "E1-A")
    bad_manifest["history_cut"] = {
        "campaign_id": batch.campaign_id,
        "accepted_head_seq": 9999,
        "accepted_head_hash": "deadbeef" * 8,
    }
    _create_result_zip(p, bad_manifest)

    slot, status, reason = inbox.ingest_zip(p)
    assert status == "REJECTED"
    assert "STALE_CUT" in reason


def test_package_digest_mismatch_rejected(inbox_setup):
    store, batch, inbox, tmp = inbox_setup
    p = tmp / "bad_pkg_digest.zip"
    bad_manifest = _valid_manifest_for_lane(batch, "E1-A")
    bad_manifest["input_package_digest"] = "f" * 64
    _create_result_zip(p, bad_manifest)

    slot, status, reason = inbox.ingest_zip(p)
    assert status == "REJECTED"
    assert "PACKAGE_DIGEST_MISMATCH" in reason


def test_duplicate_result_is_idempotent(inbox_setup):
    store, batch, inbox, tmp = inbox_setup
    p = tmp / "idempotent.zip"
    _create_result_zip(p, _valid_manifest_for_lane(batch, "E1-A"))

    # First ingestion: ACCEPTED
    slot1, status1, reason1 = inbox.ingest_zip(p)
    assert status1 == "ACCEPTED"

    # Second ingestion of the exact same result: ACCEPTED idempotently
    slot2, status2, reason2 = inbox.ingest_zip(p)
    assert status2 == "ACCEPTED"
    assert inbox.lane_statuses["E1-A"].status == "ACCEPTED"


def test_malformed_manifest_rejected(tmp_path: Path, inbox_setup):
    store, batch, inbox, tmp = inbox_setup
    p = tmp / "bad_json.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("MANIFEST.json", "Not JSON at all")

    slot, status, reason = inbox.ingest_zip(p)
    assert status == "REJECTED"
    assert "Corrupted MANIFEST.json" in reason


def test_traversal_archive_rejected(tmp_path: Path, inbox_setup):
    store, batch, inbox, tmp = inbox_setup
    p = tmp / "traversal.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("MANIFEST.json", json.dumps(_valid_manifest_for_lane(batch, "E1-A")))
        # Zip slip entry
        zf.writestr("../evil.txt", "exploit")
    p.write_bytes(buf.getvalue())

    slot, status, reason = inbox.ingest_zip(p)
    assert status == "REJECTED"
    assert "ZIP_PATH_TRAVERSAL" in reason


def test_duplicate_path_archive_rejected(tmp_path: Path, inbox_setup):
    store, batch, inbox, tmp = inbox_setup
    p = tmp / "dup_paths.zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("MANIFEST.json", json.dumps(_valid_manifest_for_lane(batch, "E1-A")))
        # Write two entries with the exact same name
        zinfo1 = zipfile.ZipInfo("report.txt")
        zinfo2 = zipfile.ZipInfo("report.txt")
        zf.writestr(zinfo1, "first")
        zf.writestr(zinfo2, "second")
    p.write_bytes(buf.getvalue())

    slot, status, reason = inbox.ingest_zip(p)
    assert status == "REJECTED"
    assert "ZIP_DUPLICATE_PATH" in reason


def test_corrupted_zip_file_rejected(tmp_path: Path, inbox_setup):
    store, batch, inbox, tmp = inbox_setup
    p = tmp / "corrupted.zip"
    p.write_bytes(b"This is not a zip file at all")

    slot, status, reason = inbox.ingest_zip(p)
    assert status == "REJECTED"
    assert "not a valid ZIP" in reason

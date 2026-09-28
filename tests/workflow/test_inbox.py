"""Targeted tests for E1ResultInbox and multi-ZIP ingestion security."""
from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile
from uuid import uuid4
import pytest

from bdb_audit.coordinator import Coordinator
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id
from bdb_audit.history.objects import CanonicalObject, CommandEnvelope
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS
from bdb_audit.workflow.source_target import ResolvedSource
from bdb_audit.workflow.packaging import prepare_e1_batch
from bdb_audit.workflow.inbox import E1ResultInbox
from bdb_audit.workflow.read_models import current_accepted_cut


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
    cut = current_accepted_cut(store)
    completion = next(
        row
        for row in store.accepted_records("stage_completion", cut)
        if row["body"].get("stage_spec_ref", {}).get("revision_digest")
        == store.accepted_records("stage_spec", cut)[0]["ref"]["revision_digest"]
    )
    output_digests = {
        ref["revision_digest"]
        for ref in completion["body"]["required_output_refs"]
    }
    accepted_discoveries = {
        row["ref"]["revision_digest"]
        for row in store.accepted_records("discovery_record", cut)
    }
    assert accepted_discoveries <= output_digests
    assert summary.completion_digest == completion["ref"]["revision_digest"]

    results_by_slot = {
        row["body"]["lane_slot"]: row
        for row in store.accepted_records("bdb_audit_lane_result", cut)
        if row["body"].get("stage_id") == "E1"
    }
    lane_completions = store.accepted_records("lane_completion", cut)
    assert len(results_by_slot) == len(E1_LANE_SLOTS)
    assert len(lane_completions) == len(E1_LANE_SLOTS)
    for lane_completion in lane_completions:
        result = next(
            store.resolve_accepted(ref, cut)
            for ref in lane_completion["body"]["required_output_refs"]
            if ref.get("kind") == "bdb_audit_lane_result"
        )
        slot = result["body"]["lane_slot"]
        assert result["ref"]["revision_digest"] == results_by_slot[slot]["ref"]["revision_digest"]
        assert result["body"]["assignment_ref"]["revision_digest"] == batch.get_job(slot).assignment_ref["revision_digest"]


def test_e1_direct_lane_completion_rejects_foreign_execution_outputs(inbox_setup):
    store, batch, inbox, tmp = inbox_setup
    result_path = _create_result_zip(
        tmp / "only-e1-a.zip", _valid_manifest_for_lane(batch, "E1-A")
    )
    imported = inbox.ingest_multiple_zips([result_path])
    assert imported.accepted_count == 1
    assert imported.stage_complete is False

    cut = current_accepted_cut(store)
    accepted_results = store.accepted_records("bdb_audit_lane_result", cut)
    assert len(accepted_results) == 1
    result = accepted_results[0]
    result_ref = result["ref"]
    lane_a_completion = next(
        row
        for row in store.accepted_records("lane_completion", cut)
        if any(
            ref.get("revision_digest") == result_ref["revision_digest"]
            for ref in row["body"].get("required_output_refs", ())
        )
    )
    foreign_outputs = lane_a_completion["body"]["required_output_refs"]

    fake_completions = []
    for slot, job in batch.jobs.items():
        if slot == "E1-A":
            continue
        assignment = store.resolve_accepted(job.assignment_ref, cut)
        attempt = store.resolve_accepted(job.attempt_ref, cut)
        lane_run = store.resolve_accepted(attempt["body"]["lane_run_ref"], cut)
        knowledge = store.resolve_accepted(assignment["body"]["knowledge_state_ref"], cut)
        fake_completions.append(
            CanonicalObject(
                "lane_completion",
                {
                    "lane_completion_id": new_id("lane_completion"),
                    "lane_run_ref": {
                        **lane_run["ref"],
                        "ref_class": lane_a_completion["body"]["lane_run_ref"]["ref_class"],
                    },
                    "lane_spec_ref": {
                        **assignment["body"]["lane_spec_ref"],
                        "ref_class": lane_a_completion["body"]["lane_spec_ref"]["ref_class"],
                    },
                    "input_history_cut": cut,
                    "attempt_refs": [
                        {
                            **job.attempt_ref,
                            "ref_class": lane_a_completion["body"]["attempt_refs"][0]["ref_class"],
                        }
                    ],
                    "final_knowledge_state_ref": {
                        **assignment["body"]["knowledge_state_ref"],
                        "ref_class": lane_a_completion["body"]["final_knowledge_state_ref"]["ref_class"],
                    },
                    "required_output_refs": foreign_outputs,
                    "isolation_qualification_ref": {
                        **knowledge["body"]["isolation_qualification_ref"],
                        "ref_class": lane_a_completion["body"]["isolation_qualification_ref"]["ref_class"],
                    },
                    "contamination_assessment_refs": [],
                    "completion_predicate_result": "LANE_COMPLETED",
                },
            )
        )

    stage_run = next(
        row
        for row in store.accepted_records("stage_run", cut)
        if store.resolve_accepted(row["body"]["stage_spec_ref"], cut)["body"].get("stage_key") == "E1"
    )
    stage_spec = store.resolve_accepted(stage_run["body"]["stage_spec_ref"], cut)
    lane_refs = [obj.as_ref().as_dict() for obj in fake_completions]
    stage_completion = CanonicalObject(
        "stage_completion",
        {
            "stage_completion_id": new_id("stage_completion"),
            "stage_run_ref": stage_run["ref"],
            "stage_spec_ref": stage_spec["ref"],
            "input_history_cut": cut,
            "required_lane_slot_results": lane_refs,
            "required_output_refs": foreign_outputs,
            "mandatory_obligation_summary": {
                "required_stage_completion_outputs": stage_spec["body"][
                    "required_stage_completion_outputs"
                ]
            },
            "unresolved_material_refs": [],
            "unknown_blocked_summary": {"unknown_surfaces_count": 0},
            "completion_predicate_result": "STAGE_COMPLETED",
        },
    )

    head_before = store.head()
    commit_count_before = len(store.commits())
    con = store._connect()
    try:
        object_count_before = con.execute("SELECT COUNT(*) FROM immutable_objects").fetchone()[0]
        receipt_count_before = con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    finally:
        con.close()
    prior_commit = store.commits()[-1]
    command = CommandEnvelope(
        command_id=f"command_{uuid4()}",
        command_kind="RECORD_FOUNDATION_FACT",
        actor_ref=prior_commit["actor_ref"],
        expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head_before.as_dict()},
        governing_policy_ref=prior_commit["governing_policy_ref"],
        governing_spec_refs=tuple(prior_commit["governing_spec_refs"]),
        idempotency_scope=f"foreign-e1-completion:{uuid4().hex}",
        campaign_ref=head_before.campaign_id,
    )

    with pytest.raises(ValidationError, match="LANE_COMPLETION_RESULT_PROVENANCE_MISMATCH"):
        Coordinator(store).accept(
            command,
            immutable_objects=[*fake_completions, stage_completion],
            expected_head=head_before,
        )

    assert store.head() == head_before
    assert len(store.commits()) == commit_count_before
    con = store._connect()
    try:
        assert con.execute("SELECT COUNT(*) FROM immutable_objects").fetchone()[0] == object_count_before
        assert con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == receipt_count_before
    finally:
        con.close()
    assert all(store.object_record(obj.digest) is None for obj in (*fake_completions, stage_completion))
    assert "E1" not in AuditOperationApi().get_campaign_status(store.path)["stages_completed"]


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

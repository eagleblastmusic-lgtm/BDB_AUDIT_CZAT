"""Tests for E1 batch freeze, knowledge isolation, and deterministic packaging."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile
import pytest

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS
from bdb_audit.workflow.source_target import ResolvedSource
from bdb_audit.workflow.packaging import prepare_e1_batch


@pytest.fixture
def test_setup(tmp_path: Path):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    created = api.create_campaign(store_path, seed="e1_freeze_test")
    api.prepare_stage(store_path, "E1")
    for slot in E1_LANE_SLOTS:
        api.prepare_lane(store_path, "E1", slot=slot)

    store = TransactionalHistoryStore(store_path)
    out_dir = tmp_path / "audit_work"
    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/test-repo",
        display_name="example/test-repo",
        ref="main",
        exact_commit_sha="a" * 40,
    )
    return store, out_dir, source


def test_all_5_e1_packages_share_exact_same_frozen_cut(test_setup):
    store, out_dir, source = test_setup
    head = store.head()

    batch = prepare_e1_batch(store, out_dir, source)

    assert batch.stage_id == "E1"
    assert set(batch.lane_slots) == set(E1_LANE_SLOTS)
    assert len(batch.jobs) == 5

    frozen_cut = batch.frozen_history_cut
    assert frozen_cut["accepted_head_seq"] == head.commit_seq
    assert frozen_cut["accepted_head_hash"] == head.commit_hash

    # Verify that EVERY package is bound to this exact same cut
    for slot in E1_LANE_SLOTS:
        job = batch.get_job(slot)
        assert job.input_history_cut == frozen_cut
        assert job.package_zip_path.exists()

        # Check manifest inside ZIP
        with zipfile.ZipFile(job.package_zip_path, "r") as zf:
            manifest = json.loads(zf.read("MANIFEST.json").decode("utf-8"))
            assert manifest["input_history_cut"] == frozen_cut
            assert manifest["lane_slot"] == slot
            assert manifest["package_digest"] == job.package_digest


def test_sequential_inspection_does_not_mutate_frozen_cut(test_setup):
    store, out_dir, source = test_setup
    batch = prepare_e1_batch(store, out_dir, source)

    initial_cut = batch.frozen_history_cut
    initial_digests = {slot: batch.get_job(slot).package_digest for slot in E1_LANE_SLOTS}

    # Simulate sequential viewing of all 5 lanes
    viewed = []
    for slot in E1_LANE_SLOTS:
        job = batch.get_job(slot)
        viewed.append(job.lane_slot)
        # Verify cut hasn't drifted
        assert job.input_history_cut == initial_cut
        assert job.package_digest == initial_digests[slot]

    assert viewed == list(E1_LANE_SLOTS)


def test_packages_have_external_checksum_and_no_self_referential_digest(test_setup):
    store, out_dir, source = test_setup
    batch = prepare_e1_batch(store, out_dir, source)

    for slot in E1_LANE_SLOTS:
        job = batch.get_job(slot)
        receipt_path = job.package_zip_path.with_suffix(".zip.sha256")
        assert receipt_path.exists()

        # Verify checksum matches actual ZIP bytes
        actual_sha = hashlib.sha256(job.package_zip_path.read_bytes()).hexdigest()
        assert actual_sha == job.package_zip_sha256
        assert actual_sha in receipt_path.read_text(encoding="utf-8")

        # Confirm ZIP manifest does NOT contain self-referential zip sha
        with zipfile.ZipFile(job.package_zip_path, "r") as zf:
            manifest = json.loads(zf.read("MANIFEST.json").decode("utf-8"))
            assert "package_zip_sha256" not in manifest


def test_e1_prompt_contains_exact_commit_sha_and_lane_strategy(test_setup):
    store, out_dir, source = test_setup
    batch = prepare_e1_batch(store, out_dir, source)

    for slot in E1_LANE_SLOTS:
        job = batch.get_job(slot)
        assert source.exact_commit_sha in job.prompt_text
        assert job.lane_title.upper() in job.prompt_text
        assert job.strategy in job.prompt_text
        assert "MANIFEST.json" in job.prompt_text

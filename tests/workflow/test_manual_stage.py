"""Targeted tests for durable external E2+ phase transport."""
from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.manual_stage import (
    StageLaneDefinition,
    StageResultInbox,
    prepare_stage_phase_batch,
)
from bdb_audit.workflow.source_target import ResolvedSource


LANES = (
    StageLaneDefinition(
        "E2-F1",
        "Blind verification",
        "BLIND_VERIFY",
    ),
    StageLaneDefinition(
        "E2-F2",
        "Blind falsification",
        "BLIND_FALSIFY",
    ),
)


@pytest.fixture
def e2_phase(tmp_path: Path):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(
        store_path,
        seed="manual_stage_transport",
    )
    api.prepare_stage(store_path, "E1")
    api.qualify_stage(store_path, "E1")
    api.prepare_stage(store_path, "E2")
    for lane in LANES:
        api.prepare_lane(
            store_path,
            "E2",
            lane.lane_slot,
        )

    source = ResolvedSource(
        target_type="github",
        location=(
            "https://github.com/example/manual-stage"
        ),
        display_name="example/manual-stage",
        ref="main",
        exact_commit_sha="c" * 40,
    )
    store = TransactionalHistoryStore(store_path)
    batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp_path / "work",
        source_info=source,
        stage_id="E2",
        phase_id="E2-BLIND",
        lane_definitions=LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in LANES
        ],
    )
    inbox = StageResultInbox(store, batch)
    return store, batch, inbox, tmp_path


def _write_result(
    path: Path,
    batch,
    slot: str,
    **overrides,
) -> Path:
    job = batch.get_job(slot)
    body = {
        "kind": "bdb_audit_lane_result",
        "version": "1",
        "campaign_id": batch.campaign_id,
        "stage_id": batch.stage_id,
        "phase_id": batch.phase_id,
        "lane_slot": slot,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "input_package_digest": job.package_digest,
        "source_commit_sha": job.source_commit_sha,
        "history_cut": batch.frozen_history_cut,
        "assignment_ref": job.assignment_ref,
        "attempt_ref": job.attempt_ref,
        "findings": [],
        "outputs": {
            "verdict": "INCONCLUSIVE"
        },
    }
    body.update(overrides)
    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            "MANIFEST.json",
            json.dumps(body),
        )
        archive.writestr(
            "REPORT.md",
            "bounded external result",
        )
    return path


def test_phase_packages_share_exact_input_cut_and_distinct_assignments(
    e2_phase,
):
    _, batch, _, _ = e2_phase
    assert batch.stage_id == "E2"
    assert batch.phase_id == "E2-BLIND"
    assert set(batch.jobs) == {
        "E2-F1",
        "E2-F2",
    }
    cuts = {
        json.dumps(
            job.input_history_cut,
            sort_keys=True,
        )
        for job in batch.jobs.values()
    }
    assert len(cuts) == 1
    assignment_digests = {
        job.assignment_ref["revision_digest"]
        for job in batch.jobs.values()
    }
    assert len(assignment_digests) == 2
    for job in batch.jobs.values():
        assert job.package_zip_path.is_file()
        assert job.package_zip_path.with_suffix(
            ".zip.sha256"
        ).is_file()


def test_phase_inbox_accepts_order_independent_results_without_stage_completion(
    e2_phase,
):
    store, batch, inbox, tmp = e2_phase
    preexisting = len(
        store.accepted_records(
            "stage_completion",
            {
                "tag": "ACCEPTED_HISTORY_CUT",
                "campaign_id": store.head().campaign_id,
                "accepted_head_seq": store.head().commit_seq,
                "accepted_head_hash": store.head().commit_hash,
                "governing_policy_ref": (
                    store.commits()[-1][
                        "governing_policy_ref"
                    ]
                ),
                "governing_spec_refs": (
                    store.commits()[-1][
                        "governing_spec_refs"
                    ]
                ),
            },
        )
    )
    paths = [
        _write_result(
            tmp / "f2.zip",
            batch,
            "E2-F2",
        ),
        _write_result(
            tmp / "f1.zip",
            batch,
            "E2-F1",
        ),
    ]
    summary = inbox.ingest_multiple_zips(paths)
    assert summary.accepted_count == 2
    assert summary.phase_complete is True
    assert (
        summary.ready_for_stage_synthesis
        is True
    )
    assert summary.missing_lanes == []
    # Phase transport does not itself accept E2 StageCompletion.
    from bdb_audit.workflow.read_models import (
        current_accepted_cut,
    )
    current = current_accepted_cut(store)
    assert len(
        store.accepted_records(
            "stage_completion", current
        )
    ) == preexisting


def test_wrong_phase_rejected(e2_phase):
    _, batch, inbox, tmp = e2_phase
    path = _write_result(
        tmp / "wrong-phase.zip",
        batch,
        "E2-F1",
        phase_id="E2-REVEAL",
    )
    _, status, reason = inbox.ingest_zip(path)
    assert status == "REJECTED"
    assert "WRONG_PHASE" in (reason or "")


def test_exact_retry_is_idempotent(e2_phase):
    store, batch, inbox, tmp = e2_phase
    path = _write_result(
        tmp / "retry.zip",
        batch,
        "E2-F1",
    )
    before = store.head().commit_seq
    assert inbox.ingest_zip(path)[1] == "ACCEPTED"
    after_first = store.head().commit_seq
    assert after_first > before
    assert inbox.ingest_zip(path)[1] == "ACCEPTED"
    assert store.head().commit_seq == after_first


def test_manual_e3_enforced_lane_blocks_phase_completion(
    tmp_path: Path,
):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(
        store_path,
        seed="manual_e3_isolation",
    )
    for stage in ("E1", "E2"):
        api.prepare_stage(store_path, stage)
        api.qualify_stage(store_path, stage)
    api.prepare_stage(store_path, "E3")
    api.prepare_lane(
        store_path,
        "E3",
        "E3-X",
    )

    store = TransactionalHistoryStore(store_path)
    source = ResolvedSource(
        target_type="github",
        location=(
            "https://github.com/example/manual-e3"
        ),
        display_name="example/manual-e3",
        ref="main",
        exact_commit_sha="d" * 40,
    )
    lane = StageLaneDefinition(
        "E3-X",
        "Security / authority / trust",
        "BLIND_NOVELTY",
    )
    batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp_path / "work",
        source_info=source,
        stage_id="E3",
        phase_id="E3-BLIND",
        lane_definitions=(lane,),
        all_stage_lane_slots=("E3-X",),
    )
    inbox = StageResultInbox(store, batch)
    path = _write_result(
        tmp_path / "e3.zip",
        batch,
        "E3-X",
    )
    summary = inbox.ingest_multiple_zips([path])
    assert summary.accepted_count == 1
    assert summary.phase_complete is False
    assert "PHASE_COMPLETION_BLOCKED" in (
        summary.error or ""
    )

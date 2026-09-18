"""Targeted tests for durable external E2+ phase transport."""
from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.e2_checkpoint import E2BlindCheckpointService
from bdb_audit.workflow.e2_reveal import E2ControlledRevealService
from bdb_audit.workflow.manual_stage import (
    StageAssignmentService,
    StageLaneDefinition,
    StageResultInbox,
    prepare_stage_phase_batch,
)
from bdb_audit.workflow.source_target import ResolvedSource
from bdb_audit.workflow.read_models import current_accepted_cut
from bdb_audit.workflow.inbox import E1ResultInbox
from bdb_audit.workflow.packaging import prepare_e1_batch
from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS


LANES = (
    StageLaneDefinition(
        "E2-CONVERGENCE",
        "Blind verification",
        "BLIND_VERIFY",
    ),
    StageLaneDefinition(
        "E2-ADJUDICATION",
        "Blind falsification",
        "BLIND_FALSIFY",
    ),
)

REVEAL_LANES = (
    StageLaneDefinition(
        "E2-CONVERGENCE",
        "Controlled claim convergence",
        "CONTROLLED_REVEAL_CONVERGENCE",
    ),
    StageLaneDefinition(
        "E2-ADJUDICATION",
        "Controlled claim adjudication",
        "CONTROLLED_REVEAL_ADJUDICATION",
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
        "E2-CONVERGENCE",
        "E2-ADJUDICATION",
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
            current_accepted_cut(store),
        )
    )
    paths = [
        _write_result(
            tmp / "adjudication.zip",
            batch,
            "E2-ADJUDICATION",
        ),
        _write_result(
            tmp / "convergence.zip",
            batch,
            "E2-CONVERGENCE",
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
        "E2-CONVERGENCE",
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
        "E2-CONVERGENCE",
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


def test_unbound_context_members_fail_closed(e2_phase):
    store, _, _, tmp = e2_phase
    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/manual-stage",
        display_name="example/manual-stage",
        ref="main",
        exact_commit_sha="c" * 40,
    )
    with pytest.raises(
        ValidationError,
        match="UNBOUND_STAGE_CONTEXT_FORBIDDEN",
    ):
        prepare_stage_phase_batch(
            store=store,
            output_dir=tmp / "work2",
            source_info=source,
            stage_id="E2",
            phase_id="E2-REVEAL",
            lane_definitions=LANES,
            all_stage_lane_slots=[
                lane.lane_slot for lane in LANES
            ],
            context_members={
                "prior_claims.json": b"{}"
            },
        )


def test_distinct_phase_does_not_reuse_blind_assignments(e2_phase):
    store, blind_batch, _, _ = e2_phase
    reveal_lanes = (
        StageLaneDefinition(
            "E2-CONVERGENCE",
            "Re-adjudication after controlled reveal",
            "REVEALED_REVIEW",
        ),
        StageLaneDefinition(
            "E2-ADJUDICATION",
            "Falsification after controlled reveal",
            "REVEALED_FALSIFY",
        ),
    )
    reveal = StageAssignmentService(
        store
    ).prepare_phase_assignments(
        stage_id="E2",
        phase_id="E2-REVEAL",
        lane_definitions=reveal_lanes,
        all_stage_lane_slots=[
            lane.lane_slot for lane in LANES
        ],
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    )
    assert reveal.phase_id == "E2-REVEAL"
    for slot, assignment in reveal.assignments.items():
        assert (
            assignment.assignment_ref["revision_digest"]
            != blind_batch.get_job(slot).assignment_ref["revision_digest"]
        )


def test_e2_blind_checkpoint_seals_both_lanes_on_one_cut(e2_phase):
    store, batch, inbox, tmp = e2_phase
    paths = [
        _write_result(
            tmp / "convergence-checkpoint.zip",
            batch,
            "E2-CONVERGENCE",
            findings=[
                {
                    "finding_id": "e2-conv-1",
                    "statement": "Independent blind precursor finding",
                }
            ],
        ),
        _write_result(
            tmp / "adjudication-checkpoint.zip",
            batch,
            "E2-ADJUDICATION",
            findings=[],
        ),
    ]
    imported = inbox.ingest_multiple_zips(paths)
    assert imported.phase_complete is True

    before = store.head().commit_seq
    summary = E2BlindCheckpointService(
        store,
        batch,
        inbox,
    ).seal()
    assert summary.already_sealed is False
    assert set(summary.checkpoint_refs) == {
        "E2-CONVERGENCE",
        "E2-ADJUDICATION",
    }
    assert summary.accepted_commit_seq == before + 1

    cut = current_accepted_cut(store)
    rows = [
        row
        for row in store.accepted_records("checkpoint", cut)
        if row["body"].get("phase_id") == "E2-BLIND"
    ]
    assert len(rows) == 2
    assert {row["accepted_seq"] for row in rows} == {
        summary.accepted_commit_seq
    }
    convergence = next(
        row
        for row in rows
        if row["body"].get("lane_slot") == "E2-CONVERGENCE"
    )
    kinds = {
        ref["kind"]
        for ref in convergence["body"]["sealed_output_refs"]
    }
    assert "bdb_audit_lane_result" in kinds
    assert "discovery_record" in kinds


def test_e2_blind_checkpoint_retry_is_idempotent(e2_phase):
    store, batch, inbox, tmp = e2_phase
    inbox.ingest_multiple_zips(
        [
            _write_result(
                tmp / "convergence-retry.zip",
                batch,
                "E2-CONVERGENCE",
            ),
            _write_result(
                tmp / "adjudication-retry.zip",
                batch,
                "E2-ADJUDICATION",
            ),
        ]
    )
    service = E2BlindCheckpointService(store, batch, inbox)
    first = service.seal()
    seq = store.head().commit_seq
    second = service.seal()
    assert second.already_sealed is True
    assert store.head().commit_seq == seq
    assert second.checkpoint_refs == first.checkpoint_refs


def test_e2_blind_checkpoint_rejects_incomplete_phase(e2_phase):
    store, batch, inbox, tmp = e2_phase
    inbox.ingest_zip(
        _write_result(
            tmp / "only-convergence.zip",
            batch,
            "E2-CONVERGENCE",
        )
    )
    with pytest.raises(
        ValidationError,
        match="E2_BLIND_PHASE_NOT_COMPLETE",
    ):
        E2BlindCheckpointService(
            store,
            batch,
            inbox,
        ).seal()


def _write_e1_result(path: Path, batch, slot: str) -> Path:
    job = batch.get_job(slot)
    body = {
        "kind": "bdb_audit_lane_result",
        "version": "1",
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": slot,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "input_package_digest": job.package_digest,
        "source_commit_sha": job.source_commit_sha,
        "history_cut": batch.frozen_history_cut,
        "assignment_ref": job.assignment_ref,
        "attempt_ref": job.attempt_ref,
        "findings": [
            {
                "finding_id": f"{slot}-finding",
                "statement": f"Claim discovered by {slot}",
                "mechanism": "bounded mechanism",
                "location": "src/example.py",
                "severity": "CRITICAL",
                "support_count": 99,
                "producer_identity": "SHOULD_NOT_REVEAL",
                "raw_report_path": "/secret/report.md",
            }
        ],
    }
    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr("MANIFEST.json", json.dumps(body))
    return path


@pytest.fixture
def e2_reveal_flow(tmp_path: Path):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(
        store_path,
        seed="e2_reveal_flow",
    )
    api.prepare_stage(store_path, "E1")
    for slot in E1_LANE_SLOTS:
        api.prepare_lane(store_path, "E1", slot)

    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/e2-reveal",
        display_name="example/e2-reveal",
        ref="main",
        exact_commit_sha="e" * 40,
    )
    store = TransactionalHistoryStore(store_path)
    e1_batch = prepare_e1_batch(
        store=store,
        output_dir=tmp_path / "work",
        source_info=source,
    )
    e1_inbox = E1ResultInbox(store, e1_batch)
    e1_summary = e1_inbox.ingest_multiple_zips(
        [
            _write_e1_result(
                tmp_path / f"{slot}.zip",
                e1_batch,
                slot,
            )
            for slot in E1_LANE_SLOTS
        ]
    )
    assert e1_summary.stage_complete is True

    api.prepare_stage(store_path, "E2")
    for lane in LANES:
        api.prepare_lane(
            store_path,
            "E2",
            lane.lane_slot,
        )

    blind_batch = prepare_stage_phase_batch(
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
    blind_inbox = StageResultInbox(
        store,
        blind_batch,
    )
    blind_summary = blind_inbox.ingest_multiple_zips(
        [
            _write_result(
                tmp_path / "blind-convergence.zip",
                blind_batch,
                "E2-CONVERGENCE",
                findings=[
                    {
                        "finding_id": "blind-c1",
                        "statement": "blind independent discovery",
                    }
                ],
            ),
            _write_result(
                tmp_path / "blind-adjudication.zip",
                blind_batch,
                "E2-ADJUDICATION",
            ),
        ]
    )
    assert blind_summary.phase_complete is True
    checkpoint = E2BlindCheckpointService(
        store,
        blind_batch,
        blind_inbox,
    ).seal()
    return {
        "store": store,
        "source": source,
        "blind_batch": blind_batch,
        "blind_inbox": blind_inbox,
        "checkpoint": checkpoint,
        "tmp": tmp_path,
    }


def test_e2_controlled_reveal_authorized_before_package_delivery(
    e2_reveal_flow,
):
    store = e2_reveal_flow["store"]
    source = e2_reveal_flow["source"]
    tmp = e2_reveal_flow["tmp"]

    authorization = E2ControlledRevealService(
        store,
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    ).authorize()

    assert authorization.phase_id == "E2-REVEAL"
    assert set(authorization.grant_refs_by_slot) == {
        "E2-CONVERGENCE",
        "E2-ADJUDICATION",
    }
    payload = json.loads(
        authorization.context_members[
            "E1_CLAIM_VIEW.json"
        ].decode("utf-8")
    )
    assert payload["format"] == "BDB-E2-POSITIVE-CLAIM-VIEW-1"
    assert payload["claims"]
    encoded = json.dumps(payload)
    assert "severity" not in encoded
    assert "support_count" not in encoded
    assert "producer_identity" not in encoded
    assert "raw_report_path" not in encoded

    seq_before_publish = store.head().commit_seq
    reveal_batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp / "work",
        source_info=source,
        stage_id="E2",
        phase_id="E2-REVEAL",
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        authorized_context=authorization,
    )
    # Package publication is a transport write only; accepted grant/history
    # existed first and publication does not advance canonical history.
    assert store.head().commit_seq == seq_before_publish

    for slot, job in reveal_batch.jobs.items():
        assert job.grant_ref == authorization.grant_refs_by_slot[slot]
        assert (
            job.authorized_knowledge_state_ref
            == authorization.knowledge_state_refs_by_slot[slot]
        )
        with zipfile.ZipFile(job.package_zip_path, "r") as archive:
            names = set(archive.namelist())
            assert "CONTEXT/E1_CLAIM_VIEW.json" in names
            manifest = json.loads(
                archive.read("MANIFEST.json")
            )
        assert manifest["context_authorization"]["grant_ref"] == job.grant_ref
        assert manifest["context_manifest"] == authorization.context_manifest


def test_e2_reveal_result_completion_uses_authorized_knowledge_state(
    e2_reveal_flow,
):
    store = e2_reveal_flow["store"]
    source = e2_reveal_flow["source"]
    tmp = e2_reveal_flow["tmp"]
    authorization = E2ControlledRevealService(
        store,
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    ).authorize()
    reveal_batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp / "work",
        source_info=source,
        stage_id="E2",
        phase_id="E2-REVEAL",
        lane_definitions=REVEAL_LANES,
        all_stage_lane_slots=[
            lane.lane_slot for lane in REVEAL_LANES
        ],
        authorized_context=authorization,
    )
    inbox = StageResultInbox(store, reveal_batch)
    path = _write_result(
        tmp / "reveal-convergence.zip",
        reveal_batch,
        "E2-CONVERGENCE",
    )
    assert inbox.ingest_zip(path)[1] == "ACCEPTED"

    cut = current_accepted_cut(store)
    result = next(
        row
        for row in store.accepted_records(
            "bdb_audit_lane_result",
            cut,
        )
        if row["body"].get("phase_id") == "E2-REVEAL"
        and row["body"].get("lane_slot") == "E2-CONVERGENCE"
    )
    completion = next(
        row
        for row in store.accepted_records(
            "lane_completion",
            cut,
        )
        if any(
            ref.get("revision_digest")
            == result["ref"]["revision_digest"]
            for ref in row["body"].get(
                "required_output_refs", []
            )
        )
    )
    assert (
        completion["body"][
            "final_knowledge_state_ref"
        ]["revision_digest"]
        == authorization.knowledge_state_refs_by_slot[
            "E2-CONVERGENCE"
        ]["revision_digest"]
    )


def test_e2_reveal_authorization_retry_is_idempotent(
    e2_reveal_flow,
):
    store = e2_reveal_flow["store"]
    kwargs = {
        "lane_definitions": REVEAL_LANES,
        "all_stage_lane_slots": [
            lane.lane_slot for lane in REVEAL_LANES
        ],
        "executor_profile": "ChatGPT / GitHub",
        "model": "Sol 5.6",
    }
    first = E2ControlledRevealService(
        store,
        **kwargs,
    ).authorize()
    seq = store.head().commit_seq
    second = E2ControlledRevealService(
        store,
        **kwargs,
    ).authorize()
    assert second.already_authorized is True
    assert store.head().commit_seq == seq
    assert second.view_manifest_ref == first.view_manifest_ref
    assert second.grant_refs_by_slot == first.grant_refs_by_slot


def test_reveal_package_without_authorization_fails_closed(e2_phase):
    store, _, _, tmp = e2_phase
    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/manual-stage",
        display_name="example/manual-stage",
        ref="main",
        exact_commit_sha="c" * 40,
    )
    with pytest.raises(
        ValidationError,
        match="STAGE_REVEAL_AUTHORIZATION_REQUIRED",
    ):
        prepare_stage_phase_batch(
            store=store,
            output_dir=tmp / "work-reveal-denied",
            source_info=source,
            stage_id="E2",
            phase_id="E2-REVEAL",
            lane_definitions=REVEAL_LANES,
            all_stage_lane_slots=[
                lane.lane_slot for lane in REVEAL_LANES
            ],
        )

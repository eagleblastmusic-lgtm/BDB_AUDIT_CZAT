"""End-to-end regressions for real E5A -> candidate -> E5B runtime."""
from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.e5_runtime import (
    CandidateAssuranceCaseService,
    E5A_LANES,
    E5B_LANES,
    E5_ALL_LANE_SLOTS,
    E5ChallengeAuthorizationService,
    E5ChallengerResultService,
    E5FinalizationService,
)
from bdb_audit.workflow.manual_stage import (
    StageResultInbox,
    prepare_stage_phase_batch,
)
from bdb_audit.workflow.source_target import ResolvedSource
from bdb_audit.workflow.read_models import current_accepted_cut


def _source() -> ResolvedSource:
    return ResolvedSource(
        target_type="github",
        location="https://github.com/example/e5",
        display_name="example/e5",
        ref="main",
        exact_commit_sha="e" * 40,
    )


def _base_campaign(tmp_path: Path):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(store_path, seed="e5_real_runtime")
    for stage in ("E1", "E2", "E3", "E4"):
        api.prepare_stage(store_path, stage)
        api.qualify_stage(store_path, stage)
    api.prepare_stage(store_path, "E5")
    for lane in (*E5A_LANES, *E5B_LANES):
        api.prepare_lane(store_path, "E5", lane.lane_slot)
    return store_path, TransactionalHistoryStore(store_path)


def _write_stage_result(
    path: Path,
    batch,
    slot: str,
    outputs: dict,
    *,
    findings: list[dict] | None = None,
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
        "findings": findings or [],
        "outputs": outputs,
    }
    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr("MANIFEST.json", json.dumps(body))
    return path


def _e5a_outputs(slot: str) -> dict:
    if slot == "E5-A-INTERACTION":
        return {
            "e5a_interaction_results": [
                {
                    "combination": ["state", "retry"],
                    "status": "PASS",
                    "rationale": "bounded pairwise interaction held",
                }
            ]
        }
    if slot == "E5-A-MUTATION":
        return {
            "e5a_mutation_results": [
                {
                    "mutation_class": mutation_class,
                    "status": "MUTANT_KILLED",
                    "activation_witness": (
                        f"activated-{mutation_class.lower()}"
                    ),
                    "rationale": (
                        f"qualified oracle killed {mutation_class}"
                    ),
                }
                for mutation_class in (
                    "IMPLEMENTATION",
                    "ORACLE",
                    "SPECIFICATION",
                )
            ]
        }
    if slot == "E5-A-CALIBRATION":
        return {
            "e5a_calibration": {
                "status": "QUALIFIED",
                "profile_ref": {
                    "kind": "external_profile_ref",
                    "revision_digest": "7" * 64,
                    "digest_profile": "BDB-OBJECT-DIGEST-1",
                    "schema_revision_ref": (
                        "BDB_TARGET/external_profile_ref"
                    ),
                    "ref_class": "HISTORY_CONTEXT_BINDING",
                },
                "per_class_metrics": {"seeded": {"detected": 1}},
                "unknown_count": 0,
                "rationale": "qualified bounded calibration profile",
            }
        }
    raise AssertionError(slot)


def _prepare_e5a(tmp_path: Path, store):
    batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp_path / "work",
        source_info=_source(),
        stage_id="E5",
        phase_id="E5A-ATTACK",
        lane_definitions=E5A_LANES,
        all_stage_lane_slots=E5_ALL_LANE_SLOTS,
    )
    inbox = StageResultInbox(store, batch)
    paths = [
        _write_stage_result(
            tmp_path / f"{slot}.zip",
            batch,
            slot,
            _e5a_outputs(slot),
        )
        for slot in batch.lane_slots
    ]
    assert inbox.ingest_multiple_zips(paths).phase_complete is True
    return batch, inbox


def _prepare_e5b(
    tmp_path: Path,
    store,
    candidate,
    *,
    skeptic_status: str = "NO_MATERIAL_COUNTEREVIDENCE",
    hunter_status: str = "NO_MATERIAL_COUNTEREVIDENCE",
):
    auth = E5ChallengeAuthorizationService(
        store,
        candidate=candidate,
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    ).authorize()
    batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp_path / "work",
        source_info=_source(),
        stage_id="E5",
        phase_id="E5B-CHALLENGE",
        lane_definitions=E5B_LANES,
        all_stage_lane_slots=E5_ALL_LANE_SLOTS,
        authorized_context=auth,
    )
    inbox = StageResultInbox(store, batch)
    cut = current_accepted_cut(store)
    assignments = {
        row["body"]["challenger_type"]: row
        for row in store.accepted_records(
            "challenger_assignment", cut
        )
        if row["body"].get(
            "candidate_assurance_case_ref", {}
        ).get("revision_digest") == candidate.digest()
    }
    paths = []
    for slot, status in (
        ("E5-B1", skeptic_status),
        ("E5-B2", hunter_status),
    ):
        role = (
            "FALSE_POSITIVE_SKEPTIC"
            if slot == "E5-B1"
            else "FALSE_NEGATIVE_HUNTER"
        )
        assignment = assignments[role]
        findings = (
            [
                {
                    "statement": (
                        "material challenger counterevidence"
                    )
                }
            ]
            if status == "MATERIAL_COUNTEREVIDENCE_FOUND"
            else []
        )
        paths.append(
            _write_stage_result(
                tmp_path / f"{slot}.zip",
                batch,
                slot,
                {
                    "challenger_result": {
                        "status": status,
                        "candidate_revision_digest": (
                            candidate.digest()
                        ),
                        "challenge_assignment_revision_digest": (
                            assignment["ref"]["revision_digest"]
                        ),
                        "challenged_revision_digests": [],
                        "reason_codes": [],
                    }
                },
                findings=findings,
            )
        )
    assert inbox.ingest_multiple_zips(paths).phase_complete is True
    return batch, inbox


def test_real_e5_runtime_preserves_temporal_boundaries(
    tmp_path: Path,
) -> None:
    _, store = _base_campaign(tmp_path)
    e5a, e5a_inbox = _prepare_e5a(tmp_path, store)
    frozen = CandidateAssuranceCaseService(store).freeze(
        e5a, e5a_inbox
    )
    e5b, e5b_inbox = _prepare_e5b(
        tmp_path, store, frozen.candidate
    )
    result_summary = E5ChallengerResultService(
        store, e5b, e5b_inbox
    ).materialize()
    completion = E5FinalizationService(store).finalize()

    cut = current_accepted_cut(store)
    candidate_record = max(
        store.accepted_records(
            "candidate_assurance_case", cut
        ),
        key=lambda row: int(row["accepted_seq"]),
    )
    assignment_rows = [
        row
        for row in store.accepted_records(
            "challenger_assignment", cut
        )
        if row["body"].get(
            "candidate_assurance_case_ref", {}
        ).get("revision_digest")
        == candidate_record["ref"]["revision_digest"]
    ]
    assignment_digests = {
        row["ref"]["revision_digest"]
        for row in assignment_rows
    }
    result_rows = [
        row
        for row in store.accepted_records(
            "challenger_result", cut
        )
        if row["body"].get(
            "challenge_assignment_ref", {}
        ).get("revision_digest") in assignment_digests
    ]
    completion_record = store.resolve_accepted(
        completion.stage_completion_ref, cut
    )

    candidate_seq = int(candidate_record["accepted_seq"])
    assignment_seq = {
        int(row["accepted_seq"]) for row in assignment_rows
    }
    result_seq = {
        int(row["accepted_seq"]) for row in result_rows
    }
    assert len(assignment_seq) == 1
    assert len(result_seq) == 1
    assert (
        candidate_seq
        < next(iter(assignment_seq))
        < next(iter(result_seq))
        < int(completion_record["accepted_seq"])
    )
    assert len(result_summary.challenger_result_refs) == 2
    assert completion.stage_id == "E5"
    assert completion.next_action == "EVALUATE_FINAL_POST_E5_STOP"


def test_material_challenger_counterevidence_blocks_e5_completion(
    tmp_path: Path,
) -> None:
    _, store = _base_campaign(tmp_path)
    e5a, e5a_inbox = _prepare_e5a(tmp_path, store)
    frozen = CandidateAssuranceCaseService(store).freeze(
        e5a, e5a_inbox
    )
    e5b, e5b_inbox = _prepare_e5b(
        tmp_path,
        store,
        frozen.candidate,
        skeptic_status="MATERIAL_COUNTEREVIDENCE_FOUND",
    )
    E5ChallengerResultService(
        store, e5b, e5b_inbox
    ).materialize()
    with pytest.raises(
        ValidationError,
        match="E5_CHALLENGER_ADJUDICATION_REQUIRED",
    ):
        E5FinalizationService(store).finalize()


def test_e5a_pending_findings_block_candidate_freeze(
    tmp_path: Path,
) -> None:
    _, store = _base_campaign(tmp_path)
    batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp_path / "work",
        source_info=_source(),
        stage_id="E5",
        phase_id="E5A-ATTACK",
        lane_definitions=E5A_LANES,
        all_stage_lane_slots=E5_ALL_LANE_SLOTS,
    )
    inbox = StageResultInbox(store, batch)
    paths = []
    for slot in batch.lane_slots:
        outputs = _e5a_outputs(slot)
        findings = (
            [{"statement": "pending E5A finding"}]
            if slot == "E5-A-INTERACTION"
            else []
        )
        paths.append(
            _write_stage_result(
                tmp_path / f"pending_{slot}.zip",
                batch,
                slot,
                outputs,
                findings=findings,
            )
        )
    assert inbox.ingest_multiple_zips(paths).phase_complete is True
    with pytest.raises(
        ValidationError,
        match="E5A_FINDINGS_REQUIRE_ADJUDICATION",
    ):
        CandidateAssuranceCaseService(store).freeze(
            batch, inbox
        )

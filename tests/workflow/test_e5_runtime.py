"""End-to-end regressions for real E5A -> candidate -> E5B runtime."""
from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.stop.input_builder import StopInputBuilder
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
            "implementation_mutation_results": [
                {
                    "outcome": "MUTANT_KILLED",
                    "activation_witness": "implementation-mutant-activated",
                    "rationale": "activated implementation mutant was detected",
                }
            ],
            "oracle_challenge_results": [
                {
                    "outcome": "WEAKENING_DETECTED",
                    "activation_witness": "oracle-weakening-activated",
                    "contrast_2x2": {
                        "clean_strong_detected": False,
                        "clean_weakened_detected": False,
                        "defective_strong_detected": True,
                        "defective_weakened_detected": False,
                    },
                    "rationale": "2x2 contrast proves the weakened observer was material",
                }
            ],
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
    summary = E5ChallengerResultService(
        store, e5b, e5b_inbox
    ).materialize()
    cut = current_accepted_cut(store)
    canonical_results = [
        store.resolve_accepted(ref, cut)
        for ref in summary.challenger_result_refs
    ]
    material = [
        row
        for row in canonical_results
        if row["body"]["status"]
        == "MATERIAL_COUNTEREVIDENCE_FOUND"
    ]
    assert len(material) == 1
    assert material[0]["body"]["counterclaim_refs"]
    assert all(
        ref["kind"] == "finding_claim_revision"
        for ref in material[0]["body"]["counterclaim_refs"]
    )
    with pytest.raises(
        ValidationError,
        match="E5_CHALLENGER_ADJUDICATION_REQUIRED",
    ):
        E5FinalizationService(store).finalize()


def test_e5a_findings_are_open_adjudicated_before_candidate_freeze(
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
            [
                {
                    "title": "E5A finding",
                    "statement": "new material E5A observation",
                }
            ]
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

    frozen = CandidateAssuranceCaseService(store).freeze(
        batch, inbox
    )
    assert len(
        frozen.candidate.finding_claim_revision_refs
    ) >= 1
    assert len(
        frozen.candidate.finding_adjudication_refs
    ) >= 1

    cut = current_accepted_cut(store)
    claims = store.accepted_records(
        "finding_claim_revision", cut
    )
    decisions = store.accepted_records(
        "finding_adjudication_decision", cut
    )
    assert any(
        row["body"]["statement"]
        == "new material E5A observation"
        for row in claims
    )
    assert any(
        row["body"]["lifecycle_status"] == "OPEN"
        for row in decisions
    )


def test_e5a_rejects_oracle_implementation_status_alias(tmp_path: Path) -> None:
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
        if slot == "E5-A-MUTATION":
            outputs = dict(outputs)
            outputs["oracle_challenge_results"] = [
                {
                    "outcome": "MUTANT_KILLED",
                    "activation_witness": "oracle-activated",
                    "contrast_2x2": {
                        "clean_strong_detected": False,
                        "clean_weakened_detected": False,
                        "defective_strong_detected": True,
                        "defective_weakened_detected": False,
                    },
                    "rationale": "invalid alias",
                }
            ]
        paths.append(
            _write_stage_result(
                tmp_path / f"alias_{slot}.zip",
                batch,
                slot,
                outputs,
            )
        )
    assert inbox.ingest_multiple_zips(paths).phase_complete is True
    with pytest.raises(
        ValidationError,
        match="E5A_ORACLE_CHALLENGE_STATUS_INVALID",
    ):
        CandidateAssuranceCaseService(store).freeze(batch, inbox)


def test_candidate_pins_exact_current_adjudication_for_each_finding(
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
            [
                {
                    "title": "Candidate binding finding",
                    "statement": (
                        "candidate must pin exact current "
                        "adjudication"
                    ),
                }
            ]
            if slot == "E5-A-INTERACTION"
            else []
        )
        paths.append(
            _write_stage_result(
                tmp_path / f"binding_{slot}.zip",
                batch,
                slot,
                outputs,
                findings=findings,
            )
        )
    assert inbox.ingest_multiple_zips(paths).phase_complete is True
    frozen = CandidateAssuranceCaseService(store).freeze(
        batch, inbox
    )
    assert len(
        frozen.candidate.finding_claim_revision_refs
    ) == len(
        frozen.candidate.finding_adjudication_refs
    )

    claim_digests = {
        ref["revision_digest"]
        for ref in frozen.candidate.finding_claim_revision_refs
    }
    cut = current_accepted_cut(store)
    pinned_targets = {
        store.resolve_accepted(ref, cut)["body"][
            "claim_revision_ref"
        ]["revision_digest"]
        for ref in frozen.candidate.finding_adjudication_refs
    }
    assert pinned_targets == claim_digests

    e5b, e5b_inbox = _prepare_e5b(
        tmp_path, store, frozen.candidate
    )
    E5ChallengerResultService(
        store, e5b, e5b_inbox
    ).materialize()
    E5FinalizationService(store).finalize()

    stop_input = StopInputBuilder.build_from_store(
        store,
        evaluation_context="FINAL_POST_E5",
    )
    assert (
        stop_input.candidate_assurance_case_ref[
            "revision_digest"
        ]
        == frozen.candidate.digest()
    )


def test_material_counterevidence_forces_new_candidate_and_new_challengers(
    tmp_path: Path,
) -> None:
    _, store = _base_campaign(tmp_path)
    e5a, e5a_inbox = _prepare_e5a(tmp_path, store)
    first = CandidateAssuranceCaseService(store).freeze(
        e5a, e5a_inbox
    )
    e5b, e5b_inbox = _prepare_e5b(
        tmp_path,
        store,
        first.candidate,
        skeptic_status="MATERIAL_COUNTEREVIDENCE_FOUND",
    )
    E5ChallengerResultService(
        store, e5b, e5b_inbox
    ).materialize()

    second = CandidateAssuranceCaseService(store).freeze(
        e5a, e5a_inbox
    )
    assert (
        second.candidate.digest()
        != first.candidate.digest()
    )
    assert len(
        second.candidate.finding_claim_revision_refs
    ) > len(
        first.candidate.finding_claim_revision_refs
    )

    E5ChallengeAuthorizationService(
        store,
        candidate=second.candidate,
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    ).authorize()
    cut = current_accepted_cut(store)
    second_assignments = [
        row
        for row in store.accepted_records(
            "challenger_assignment", cut
        )
        if row["body"].get(
            "candidate_assurance_case_ref", {}
        ).get("revision_digest")
        == second.candidate.digest()
    ]
    assert {
        row["body"]["challenger_type"]
        for row in second_assignments
    } == {
        "FALSE_POSITIVE_SKEPTIC",
        "FALSE_NEGATIVE_HUNTER",
    }

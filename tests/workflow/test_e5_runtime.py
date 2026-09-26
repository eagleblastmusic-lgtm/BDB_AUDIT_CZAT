"""Focused transactional E5A -> candidate -> E5B regressions.

Earlier E1-E4 records are synthetic accepted-history prerequisites for these
E5-only service tests; they do not qualify a complete campaign.
"""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import uuid
import zipfile

import pytest

from bdb_audit.coordinator import Coordinator
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.objects import CanonicalObject, CommandEnvelope
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.orchestration.stages import initial_stage_specs
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
from bdb_audit.workflow.scope_baseline import ensure_pre_e3_scope_baseline
from tests.f7.test_adaptive_e6_canonical_authority import (
    _append_raw_commit,
    _stage_execution_objects,
)


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
    store = TransactionalHistoryStore(store_path)
    cut = current_accepted_cut(store)
    source_generation_ref = store.accepted_records("source_generation", cut)[0]["ref"]

    # These narrow fixtures keep E5 service tests independent of E1-E4 runtime
    # behavior.  The raw accepted history helper is deliberately test-only.
    for stage_spec in initial_stage_specs()[:4]:
        _append_raw_commit(
            store,
            _stage_execution_objects(
                stage_spec,
                source_generation_ref=source_generation_ref,
                label=f"e5-prerequisite-{stage_spec.stage_key}",
                required_isolation_assurance="DECLARED",
                include_stage_spec=True,
            ),
            index=store.head().commit_seq + 1,
        )
    ensure_pre_e3_scope_baseline(store)
    api.prepare_stage(store_path, "E5")
    for lane in (*E5A_LANES, *E5B_LANES):
        api.prepare_lane(store_path, "E5", lane.lane_slot)
    return store_path, store


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


def test_direct_coordinator_stage_completion_requires_exact_e5_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Canonical admission rejects incomplete or non-governing E5 completion."""
    _, store = _base_campaign(tmp_path)
    e5a, e5a_inbox = _prepare_e5a(tmp_path, store)
    frozen = CandidateAssuranceCaseService(store).freeze(e5a, e5a_inbox)
    e5b, e5b_inbox = _prepare_e5b(tmp_path, store, frozen.candidate)
    E5ChallengerResultService(store, e5b, e5b_inbox).materialize()

    captured: dict[str, object] = {}
    original_accept = Coordinator.accept

    class _CapturedCompletion(Exception):
        pass

    def capture_completion(self, command, expected_head=None, **kwargs):
        objects = tuple(kwargs.get("immutable_objects", ()))
        completion = next(
            (obj for obj in objects if obj.kind == "stage_completion"),
            None,
        )
        if completion is not None:
            captured.update(
                command=command,
                expected_head=expected_head,
                completion=completion,
            )
            raise _CapturedCompletion
        return original_accept(self, command, expected_head, **kwargs)

    monkeypatch.setattr(Coordinator, "accept", capture_completion)
    with pytest.raises(_CapturedCompletion):
        E5FinalizationService(store).finalize()
    monkeypatch.setattr(Coordinator, "accept", original_accept)

    command = captured["command"]
    expected_head = captured["expected_head"]
    exact_completion = captured["completion"]
    assert isinstance(exact_completion, CanonicalObject)
    assert expected_head == store.head()

    def direct_accept(obj: CanonicalObject, *, label: str, extras=()) -> None:
        head_before = store.head()
        count_before = len(store.commits())
        assert head_before == expected_head
        direct_command = replace(
            command,
            command_id=f"command_{uuid.uuid4()}",
            idempotency_scope=f"direct-e5-completion:{label}:{obj.digest}",
        )
        with pytest.raises(ValidationError):
            Coordinator(store).accept(
                direct_command,
                immutable_objects=[*extras, obj],
                expected_head=head_before,
            )
        assert store.head() == head_before
        assert len(store.commits()) == count_before
        assert store.object_record(obj.digest) is None

    base = deepcopy(exact_completion.body)

    duplicate_lane = deepcopy(base)
    duplicate_lane["required_lane_slot_results"].append(
        deepcopy(duplicate_lane["required_lane_slot_results"][0])
    )
    direct_accept(
        CanonicalObject("stage_completion", duplicate_lane, logical_id=exact_completion.logical_id),
        label="duplicate-lane",
    )

    missing_lane = deepcopy(base)
    missing_lane["required_lane_slot_results"].pop()
    direct_accept(
        CanonicalObject("stage_completion", missing_lane, logical_id=exact_completion.logical_id),
        label="missing-lane",
    )

    missing_output = deepcopy(base)
    missing_output["required_output_refs"] = [
        ref
        for ref in missing_output["required_output_refs"]
        if ref.get("kind") != "candidate_assurance_case"
    ]
    direct_accept(
        CanonicalObject("stage_completion", missing_output, logical_id=exact_completion.logical_id),
        label="missing-output",
    )

    wrong_output_kind = deepcopy(base)
    candidate_ref = next(
        ref
        for ref in wrong_output_kind["required_output_refs"]
        if ref.get("kind") == "candidate_assurance_case"
    )
    candidate_ref["kind"] = "bdb_audit_lane_result"
    direct_accept(
        CanonicalObject("stage_completion", wrong_output_kind, logical_id=exact_completion.logical_id),
        label="wrong-output-kind",
    )

    from bdb_audit.orchestration.stages import native_stage_spec

    weakened_spec = native_stage_spec("E5", "2").as_object()
    weakened_completion = deepcopy(base)
    weakened_completion["stage_spec_ref"] = weakened_spec.as_ref(
        ref_class="HISTORY_CONTEXT_BINDING"
    ).as_dict()
    direct_accept(
        CanonicalObject("stage_completion", weakened_completion, logical_id=exact_completion.logical_id),
        label="non-governing-spec",
        extras=(weakened_spec,),
    )

    head_before = store.head()
    count_before = len(store.commits())
    positive_command = replace(
        command,
        command_id=f"command_{uuid.uuid4()}",
        idempotency_scope=f"direct-e5-completion:exact:{exact_completion.digest}",
    )
    accepted = Coordinator(store).accept(
        positive_command,
        immutable_objects=[exact_completion],
        expected_head=head_before,
    )
    assert accepted.head.commit_seq == head_before.commit_seq + 1
    assert len(store.commits()) == count_before + 1


def test_native_stage_spec_admission_guard_is_mutation_sensitive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _, store = _base_campaign(tmp_path)
    from bdb_audit.history import authority_hooks
    from bdb_audit.orchestration.stages import native_stage_spec

    weakened_spec = native_stage_spec("E5", "2").as_object()

    def command(label: str) -> CommandEnvelope:
        head = store.head()
        assert head is not None
        prior = store.commits()[-1]
        return CommandEnvelope(
            command_id=f"command_{uuid.uuid4()}",
            command_kind="RECORD_ASSURANCE_DECISION",
            actor_ref=prior["actor_ref"],
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior["governing_policy_ref"],
            governing_spec_refs=tuple(prior["governing_spec_refs"]),
            idempotency_scope=f"native-stage-spec-mutation:{label}:{uuid.uuid4()}",
            campaign_ref=head.campaign_id,
        )

    head_before = store.head()
    count_before = len(store.commits())
    with pytest.raises(ValidationError, match="STAGE_SPEC_NOT_GOVERNING_NATIVE_REVISION"):
        Coordinator(store).accept(
            command("guard-enabled"),
            immutable_objects=[weakened_spec],
            expected_head=head_before,
        )
    assert store.head() == head_before
    assert len(store.commits()) == count_before

    # Controlled guard deletion: the weakened revision is mechanically
    # admissible, proving the canonical negative regression depends on this
    # authority hook rather than an unrelated schema error.
    monkeypatch.setattr(
        authority_hooks,
        "_validate_native_stage_spec_authority",
        lambda _obj: None,
    )
    accepted = Coordinator(store).accept(
        command("guard-bypassed"),
        immutable_objects=[weakened_spec],
        expected_head=head_before,
    )
    assert accepted.head.commit_seq == head_before.commit_seq + 1


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

    cut = current_accepted_cut(store)
    accepted_candidates = store.accepted_records(
        "candidate_assurance_case",
        cut,
    )
    latest_candidate = max(
        accepted_candidates,
        key=lambda row: int(row["accepted_seq"]),
    )
    assert latest_candidate["ref"]["revision_digest"] == frozen.candidate.digest()


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

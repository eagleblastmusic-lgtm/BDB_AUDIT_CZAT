"""Regression tests for evidence-backed E4 stage finalization."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from uuid import uuid4
import zipfile

import pytest

from bdb_audit.coordinator import Coordinator
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.objects import CanonicalObject
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.orchestration.stages import initial_stage_specs
from bdb_audit.workflow.manual_stage import (
    StageLaneDefinition,
    StageResultInbox,
    prepare_stage_phase_batch,
)
from bdb_audit.workflow.source_target import ResolvedSource
from bdb_audit.workflow.read_models import current_accepted_cut
from bdb_audit.workflow.stage_finalize import (
    E4FinalizationService,
    E4_REQUIRED_ASSESSMENTS,
)
from tests.f7.test_adaptive_e6_canonical_authority import (
    _append_raw_commit,
    _stage_execution_objects,
)

E4_LANES = (
    StageLaneDefinition("E4-MODEL", "State, temporal and bounded model deepening", "STATE_TEMPORAL_MODEL_DEEPENING"),
    StageLaneDefinition("E4-RESILIENCE", "Fault, concurrency, crash and endurance deepening", "RESILIENCE_FAILURE_LAB"),
    StageLaneDefinition("E4-CAUSAL", "Causal-chain and sibling mechanism deepening", "CAUSAL_CHAIN_DEEPENING"),
)

def _write_result(
    path: Path,
    batch,
    slot: str,
    *,
    unresolved_kind: str | None = None,
    omit_fidelity: bool = False,
) -> Path:
    job = batch.get_job(slot)
    assessments = [
        {
            "assessment_kind": kind,
            "status": "INCONCLUSIVE" if kind == unresolved_kind else "PASS",
            "rationale": f"bounded assessment for {kind}",
        }
        for kind in sorted(E4_REQUIRED_ASSESSMENTS[slot])
    ]
    outputs = {"e4_assessments": assessments}
    if slot == "E4-MODEL" and not omit_fidelity:
        outputs["model_fidelity_assessment"] = {
            "model_revision_ref": {
                "model_id": "state_model_e4_runtime",
                "revision": 1,
                "digest": "a" * 64,
            },
            "implementation_anchor_refs": [
                {"path": "src/runtime.py", "symbol": "Runtime"}
            ],
            "abstraction_mapping_refs": [
                {"model_state": "READY", "source_anchor": "Runtime.ready"}
            ],
            "abstraction_assumptions": [],
            "omitted_states": [],
            "bounds": ["max_states=128"],
            "fairness_time_assumptions": [],
            "execution_conformance_evidence_refs": [
                {"observation_id": "obs-e4-conformance"}
            ],
            "scope": "RUNTIME_STATE_MACHINE",
            "result": "BOUNDED",
            "reason_codes": ["MODEL_BOUNDED_OR_ABSTRACTION_PRESENT"],
        }
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
        "outputs": outputs,
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("MANIFEST.json", json.dumps(body))
    return path

@pytest.fixture
def e4_phase(tmp_path: Path):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(store_path, seed="e4_external_final")
    store = TransactionalHistoryStore(store_path)
    cut = current_accepted_cut(store)
    source_generation_ref = store.accepted_records("source_generation", cut)[0]["ref"]
    # Narrow E4 service fixture: seed prerequisite-stage history directly so
    # these tests exercise E4 result validation/finalization only.
    for stage_spec in initial_stage_specs()[:3]:
        _append_raw_commit(
            store,
            _stage_execution_objects(
                stage_spec,
                source_generation_ref=source_generation_ref,
                label=f"e4-prerequisite-{stage_spec.stage_key}",
                required_isolation_assurance="DECLARED",
                include_stage_spec=True,
            ),
            index=store.head().commit_seq + 1,
        )
    api.prepare_stage(store_path, "E4")
    for lane in E4_LANES:
        api.prepare_lane(store_path, "E4", lane.lane_slot)
    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/e4",
        display_name="example/e4",
        ref="main",
        exact_commit_sha="d" * 40,
    )
    batch = prepare_stage_phase_batch(
        store=store,
        output_dir=tmp_path / "work",
        source_info=source,
        stage_id="E4",
        phase_id="E4-DEEPEN",
        lane_definitions=E4_LANES,
        all_stage_lane_slots=tuple(lane.lane_slot for lane in E4_LANES),
    )
    return store, batch, StageResultInbox(store, batch), tmp_path

def test_e4_external_results_finalize_stage(e4_phase):
    store, batch, inbox, tmp_path = e4_phase
    imported = inbox.ingest_multiple_zips([
        _write_result(tmp_path / f"{slot}.zip", batch, slot)
        for slot in batch.lane_slots
    ])
    assert imported.phase_complete is True
    summary = E4FinalizationService(
        store,
        stage_id="E4",
        required_phase_slots={"E4-DEEPEN": batch.lane_slots},
        next_action="PREPARE_E5A_ATTACK",
    ).finalize()
    assert summary.stage_id == "E4"
    assert summary.already_finalized is False
    assert summary.required_lane_completions == 3
    accepted_cut = current_accepted_cut(store)
    fidelity_rows = store.accepted_records(
        "model_fidelity_assessment", accepted_cut
    )
    assert len(fidelity_rows) == 1
    completion_record = store.resolve_accepted(
        summary.stage_completion_ref, accepted_cut
    )
    assert any(
        ref.get("kind") == "model_fidelity_assessment"
        for ref in completion_record["body"]["required_output_refs"]
    )
    retry = E4FinalizationService(
        store,
        stage_id="E4",
        required_phase_slots={"E4-DEEPEN": batch.lane_slots},
        next_action="PREPARE_E5A_ATTACK",
    ).finalize()
    assert retry.already_finalized is True
    assert retry.stage_completion_ref["revision_digest"] == summary.stage_completion_ref["revision_digest"]

def test_e4_inconclusive_required_assessment_blocks_completion(e4_phase):
    store, batch, inbox, tmp_path = e4_phase
    paths = []
    for slot in batch.lane_slots:
        unresolved = next(iter(E4_REQUIRED_ASSESSMENTS[slot])) if slot == "E4-MODEL" else None
        paths.append(_write_result(tmp_path / f"blocked_{slot}.zip", batch, slot, unresolved_kind=unresolved))
    assert inbox.ingest_multiple_zips(paths).phase_complete is True
    with pytest.raises(ValidationError, match="E4_STAGE_UNRESOLVED"):
        E4FinalizationService(
            store,
            stage_id="E4",
            required_phase_slots={"E4-DEEPEN": batch.lane_slots},
            next_action="PREPARE_E5A_ATTACK",
        ).finalize()

def test_e4_missing_model_fidelity_blocks_completion(e4_phase):
    store, batch, inbox, tmp_path = e4_phase
    paths = [
        _write_result(
            tmp_path / f"missing_fidelity_{slot}.zip",
            batch,
            slot,
            omit_fidelity=(slot == "E4-MODEL"),
        )
        for slot in batch.lane_slots
    ]
    assert inbox.ingest_multiple_zips(paths).phase_complete is True
    with pytest.raises(
        ValidationError,
        match="E4_MODEL_FIDELITY_REQUIRED",
    ):
        E4FinalizationService(
            store,
            stage_id="E4",
            required_phase_slots={
                "E4-DEEPEN": batch.lane_slots
            },
            next_action="PREPARE_E5A_ATTACK",
        ).finalize()


def test_e4_stage_completion_direct_admission_requires_exact_accepted_evidence(
    e4_phase,
    monkeypatch,
):
    store, batch, inbox, tmp_path = e4_phase
    assert inbox.ingest_multiple_zips(
        [
            _write_result(tmp_path / f"direct_{slot}.zip", batch, slot)
            for slot in batch.lane_slots
        ]
    ).phase_complete

    class CapturedAdmission(Exception):
        def __init__(self, command, expected_head, immutable_objects):
            self.command = command
            self.expected_head = expected_head
            self.immutable_objects = immutable_objects

    original_accept = Coordinator.accept

    def capture_accept(
        _coordinator, command, expected_head=None, **kwargs
    ):
        immutable_objects = kwargs["immutable_objects"]
        if not any(
            obj.kind == "stage_completion"
            for obj in immutable_objects
        ):
            return original_accept(
                _coordinator,
                command,
                expected_head,
                **kwargs,
            )
        raise CapturedAdmission(
            command,
            expected_head,
            immutable_objects,
        )

    with monkeypatch.context() as patcher:
        patcher.setattr(Coordinator, "accept", capture_accept)
        with pytest.raises(CapturedAdmission) as captured:
            E4FinalizationService(
                store,
                stage_id="E4",
                required_phase_slots={
                    "E4-DEEPEN": batch.lane_slots
                },
                next_action="PREPARE_E5A_ATTACK",
            ).finalize()

    accepted_objects = captured.value.immutable_objects
    completion = next(
        obj for obj in accepted_objects if obj.kind == "stage_completion"
    )
    before = store.head()
    assert before is not None

    def mutated_completion(**changes):
        body = dict(completion.body)
        body.update(changes)
        return CanonicalObject(
            "stage_completion",
            body,
            completion.schema_revision_ref,
            completion.logical_id,
            completion.version,
        )

    valid_lane_refs = list(
        completion.body["required_lane_slot_results"]
    )
    duplicate_lane_refs = [*valid_lane_refs, valid_lane_refs[0]]
    missing_lane_refs = valid_lane_refs[:-1]
    valid_outputs = list(completion.body["required_output_refs"])
    missing_fidelity_outputs = [
        ref
        for ref in valid_outputs
        if ref["kind"] != "model_fidelity_assessment"
    ]
    fidelity_ref = next(
        ref
        for ref in valid_outputs
        if ref["kind"] == "model_fidelity_assessment"
    )
    wrong_kind_outputs = [
        ({**ref, "kind": "checkpoint"} if ref is fidelity_ref else ref)
        for ref in valid_outputs
    ]
    cut = current_accepted_cut(store)
    non_governing_spec = next(
        row
        for row in store.accepted_records("stage_spec", cut)
        if row["body"].get("stage_key") == "E3"
    )["ref"]
    non_governing_spec = {
        **non_governing_spec,
        "ref_class": completion.body["stage_spec_ref"]["ref_class"],
    }

    rejected = (
        mutated_completion(
            required_lane_slot_results=duplicate_lane_refs
        ),
        mutated_completion(
            required_lane_slot_results=missing_lane_refs
        ),
        mutated_completion(
            required_output_refs=missing_fidelity_outputs
        ),
        mutated_completion(
            required_output_refs=wrong_kind_outputs
        ),
        mutated_completion(stage_spec_ref=non_governing_spec),
    )
    for candidate in rejected:
        with pytest.raises(ValidationError):
            Coordinator(store).accept(
                captured.value.command,
                immutable_objects=(candidate,),
                expected_head=captured.value.expected_head,
            )
        assert store.head() == before
        assert store.object_record(candidate.digest) is None

    accepted = Coordinator(store).accept(
        captured.value.command,
        immutable_objects=(completion,),
        expected_head=captured.value.expected_head,
    )
    assert accepted.head.commit_seq == before.commit_seq + 1
    assert store.object_record(completion.digest) is not None

    # Prove that the direct-admission assertion depends on the canonical
    # StageCompletion guard, rather than a shared test-side assumption.
    mutation_head = store.head()
    assert mutation_head is not None
    mutation_command = replace(
        captured.value.command,
        command_id=f"command_{uuid4()}",
        expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **mutation_head.as_dict()},
        idempotency_scope=f"stage-completion-mutation:{uuid4().hex}",
    )
    invalid_completion = mutated_completion(
        stage_spec_ref=non_governing_spec,
        input_history_cut=current_accepted_cut(store),
    )

    def direct_admission_error() -> str | None:
        try:
            Coordinator(store).accept(
                mutation_command,
                immutable_objects=(invalid_completion,),
                expected_head=mutation_head,
            )
        except ValidationError as exc:
            return exc.code
        return None

    assert direct_admission_error() is not None
    from bdb_audit.history import authority_hooks

    with monkeypatch.context() as patcher:
        patcher.setattr(
            authority_hooks,
            "_validate_stage_completion",
            lambda *_args, **_kwargs: None,
        )
        assert direct_admission_error() is None, "StageCompletion guard mutation did not expose the bad admission"


def test_e4_prompt_contains_structured_output_contract(e4_phase):
    _, batch, _, _ = e4_phase
    prompt = batch.get_job("E4-MODEL").prompt_text
    assert "E4 DEEPEN OUTPUT CONTRACT" in prompt
    assert "outputs.e4_assessments" in prompt
    assert "MODEL_IMPLEMENTATION_CONFORMANCE" in prompt
    assert "outputs.model_fidelity_assessment" in prompt

"""Regression tests for evidence-backed E4 stage finalization."""
from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.manual_stage import (
    StageLaneDefinition,
    StageResultInbox,
    prepare_stage_phase_batch,
)
from bdb_audit.workflow.source_target import ResolvedSource
from bdb_audit.workflow.stage_finalize import (
    E4FinalizationService,
    E4_REQUIRED_ASSESSMENTS,
)

E4_LANES = (
    StageLaneDefinition("E4-MODEL", "State, temporal and bounded model deepening", "STATE_TEMPORAL_MODEL_DEEPENING"),
    StageLaneDefinition("E4-RESILIENCE", "Fault, concurrency, crash and endurance deepening", "RESILIENCE_FAILURE_LAB"),
    StageLaneDefinition("E4-CAUSAL", "Causal-chain and sibling mechanism deepening", "CAUSAL_CHAIN_DEEPENING"),
)

def _write_result(path: Path, batch, slot: str, *, unresolved_kind: str | None = None) -> Path:
    job = batch.get_job(slot)
    assessments = [
        {
            "assessment_kind": kind,
            "status": "INCONCLUSIVE" if kind == unresolved_kind else "PASS",
            "rationale": f"bounded assessment for {kind}",
        }
        for kind in sorted(E4_REQUIRED_ASSESSMENTS[slot])
    ]
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
        "outputs": {"e4_assessments": assessments},
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("MANIFEST.json", json.dumps(body))
    return path

@pytest.fixture
def e4_phase(tmp_path: Path):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(store_path, seed="e4_external_final")
    for stage in ("E1", "E2", "E3"):
        api.prepare_stage(store_path, stage)
        api.qualify_stage(store_path, stage)
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
    store = TransactionalHistoryStore(store_path)
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

def test_e4_prompt_contains_structured_output_contract(e4_phase):
    _, batch, _, _ = e4_phase
    prompt = batch.get_job("E4-MODEL").prompt_text
    assert "E4 DEEPEN OUTPUT CONTRACT" in prompt
    assert "outputs.e4_assessments" in prompt
    assert "MODEL_IMPLEMENTATION_CONFORMANCE" in prompt

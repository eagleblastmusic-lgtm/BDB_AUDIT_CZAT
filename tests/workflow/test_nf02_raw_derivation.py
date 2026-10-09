"""Regressions for the independent, contract-preserving NF02 repairs.

These checks do not qualify the still-missing normative activation/package pin.
E3/E4 fixtures seed prerequisite history explicitly.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
from typing import get_type_hints

import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import deterministic_id
from bdb_audit.history.objects import CanonicalObject, CommandEnvelope
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.vault.raw_store import RawArtifactVault
from bdb_audit.workflow.manual_stage import StageResultInbox, prepare_stage_phase_batch
from bdb_audit.workflow.stage_resume import load_stage_phase_batch
from tests.workflow.test_manual_stage import e2_phase, _prepare_e3_isolation_fixture, _write_result
from tests.workflow.test_stage_finalize import e4_phase, _write_result as _write_e4_result
from tests.workflow.test_nf02_synthetic_lane_result_authority import (
    e1_setup, _assert_atomicity, _snapshot_store, _create_zip, _legitimate_manifest,
    _raw_proposal, _current_cut, _command_id,
)


@pytest.fixture
def admission(e1_setup):
    store, batch, inbox, tmp = e1_setup
    job = batch.get_job("E1-A")
    manifest = _legitimate_manifest(batch, "E1-A")
    raw = _create_zip(tmp / "raw.zip", manifest).read_bytes()
    proposal = _raw_proposal(manifest, job, raw)
    vault = RawArtifactVault(Path(store.path).resolve().parent / "raw_vault")
    vault.put_bytes(raw, media_type="application/zip")
    vault.put_bytes(job.package_zip_path.read_bytes(), media_type="application/zip")
    assignment = store.resolve_accepted(job.assignment_ref, _current_cut(store))
    source = store.resolve_accepted(assignment["body"]["source_generation_ref"], _current_cut(store))
    body = {
        "kind": "lane_result_admission_evidence", "version": "1",
        "admission_evidence_id": deterministic_id("lane_result_admission_evidence", "raw-derivation"),
        "campaign_id": batch.campaign_id, "stage_id": "E1", "lane_slot": "E1-A",
        "assignment_ref": dict(job.assignment_ref), "attempt_ref": dict(job.attempt_ref),
        "source_generation_ref": {**source["ref"], "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "source_commit_sha": job.source_commit_sha, "history_cut": dict(batch.frozen_history_cut),
        "input_package_digest": job.package_digest, "package_zip_sha256": job.package_zip_sha256,
        "raw_result_digest": hashlib.sha256(raw).hexdigest(), "raw_result_byte_length": len(raw),
        "result_proposal_digest": hashlib.sha256(canonical_bytes(proposal)).hexdigest(),
        "executor_profile": job.executor_profile, "executor_model": job.model,
        "evidence_files": proposal["evidence_files"],
    }
    return store, batch, body, proposal


def test_fresh_public_ticket_does_not_sign_caller_selected_finding(admission):
    store, batch, body, proposal = admission
    snapshot = _snapshot_store(store)
    # A fresh ticket must not turn a chosen digest into byte provenance.
    ticket = store.issue_batch_ticket(campaign_id=batch.campaign_id, stage_id="E1", cut=batch.frozen_history_cut)
    proposal["findings"][0]["statement"] = "Not present in raw MANIFEST.json"
    body["result_proposal_digest"] = hashlib.sha256(canonical_bytes(proposal)).hexdigest()
    with pytest.raises(ValidationError, match="RESULT_PROPOSAL_DIGEST_MISMATCH"):
        store.issue_ingestion_capability(body, batch_ticket=ticket)
    _assert_atomicity(store, snapshot)


def test_well_formed_forged_signature_cannot_bypass_consumer_raw_check(admission):
    from bdb_audit.history.authority_hooks import compute_ingestion_capability
    from bdb_audit.history.store import _get_or_create_ingestion_authority_key
    store, batch, body, proposal = admission
    body["result_proposal_digest"] = "a" * 64
    con = store._connect()
    try:
        # Deliberately stronger than the public attack: emulate a wrong producer
        # with the real secret. Acceptance must independently prove byte equality.
        body["ingestion_capability"] = compute_ingestion_capability(_get_or_create_ingestion_authority_key(con), body)
    finally:
        con.close()
    head = store.head()
    prior = store.commits()[-1]
    cmd = CommandEnvelope(
        command_id=_command_id("raw-derivation-forged-signature"), command_kind="INGEST_EXTERNAL_LANE_RESULT",
        actor_ref=prior["actor_ref"], expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
        governing_policy_ref=prior["governing_policy_ref"], governing_spec_refs=tuple(prior["governing_spec_refs"]),
        idempotency_scope="raw-derivation-forged-signature", campaign_ref=head.campaign_id,
    )
    snapshot = _snapshot_store(store)
    with pytest.raises(ValidationError, match="RESULT_PROPOSAL_DIGEST_MISMATCH"):
        store.accept(cmd, expected_head=head, immutable_objects=[CanonicalObject("lane_result_admission_evidence", body)])
    _assert_atomicity(store, snapshot)


@pytest.mark.parametrize("mutation", ["raw_package_hash", "foreign_package", "member_digest", "member_length", "member_path", "phase"])
def test_material_byte_and_context_claims_checked_before_signing(admission, mutation):
    store, batch, body, proposal = admission
    snapshot = _snapshot_store(store)
    if mutation == "raw_package_hash":
        body["package_zip_sha256"] = "0" * 64
        expected = "RAW_ARTIFACT_NOT_FOUND"
    elif mutation == "foreign_package":
        other = batch.get_job("E1-B")
        RawArtifactVault(Path(store.path).resolve().parent / "raw_vault").put_bytes(other.package_zip_path.read_bytes())
        body["package_zip_sha256"] = other.package_zip_sha256
        expected = "PACKAGE_CONTEXT_MISMATCH"
    elif mutation == "phase":
        body["phase_id"] = "foreign-phase"
        expected = "PHASE_BINDING_MISMATCH"
    else:
        key, value = {
            "member_digest": ("raw_digest", "0" * 64),
            "member_length": ("byte_length", 999999), "member_path": ("path", "OTHER.json"),
        }[mutation]
        body["evidence_files"] = deepcopy(body["evidence_files"])
        body["evidence_files"][0][key] = value
        expected = "RESULT_MEMBER_EVIDENCE_MISMATCH"
    with pytest.raises(ValidationError, match=expected):
        store.issue_ingestion_capability(body, batch_ticket=batch.batch_ticket)
    _assert_atomicity(store, snapshot)


@pytest.mark.parametrize("mutation", ["campaign", "seq", "policy", "spec", "namespace", "stage"])
def test_ticket_requires_full_accepted_context(e1_setup, mutation):
    store, batch, _, _ = e1_setup
    snapshot = _snapshot_store(store)
    cut = deepcopy(batch.frozen_history_cut)
    campaign = batch.campaign_id
    stage = "E1"
    if mutation == "campaign":
        campaign = "foreign-campaign"
    elif mutation == "stage":
        stage = "E99"
    else:
        key, value = {
            "seq": ("accepted_head_seq", 999999), "policy": ("governing_policy_ref", "foreign-policy"),
            "spec": ("governing_spec_refs", ["foreign-spec"]), "namespace": ("history_namespace_ref", "foreign-namespace"),
        }[mutation]
        cut[key] = value
    with pytest.raises(ValidationError):
        store.issue_batch_ticket(campaign_id=campaign, stage_id=stage, cut=cut)
    _assert_atomicity(store, snapshot)


def test_valid_raw_proposal_can_still_be_signed(admission):
    store, batch, body, _ = admission
    assert len(store.issue_ingestion_capability(body, batch_ticket=batch.batch_ticket)) == 64
    assert get_type_hints(TransactionalHistoryStore.issue_batch_ticket)
    assert get_type_hints(TransactionalHistoryStore.issue_ingestion_capability)


def test_result_source_must_match_actual_package_bytes(admission):
    store, batch, body, _ = admission
    snapshot = _snapshot_store(store)
    job = batch.get_job("E1-A")
    manifest = _legitimate_manifest(batch, "E1-A")
    manifest["source_commit_sha"] = "e" * 40
    raw = _create_zip(Path(store.path).parent / "foreign-source.zip", manifest).read_bytes()
    proposal = _raw_proposal(manifest, job, raw)
    RawArtifactVault(Path(store.path).parent / "raw_vault").put_bytes(raw)
    body.update(
        source_commit_sha=manifest["source_commit_sha"], raw_result_digest=proposal["raw_result_digest"],
        raw_result_byte_length=len(raw), evidence_files=proposal["evidence_files"],
        result_proposal_digest=hashlib.sha256(canonical_bytes(proposal)).hexdigest(),
    )
    with pytest.raises(ValidationError, match="PACKAGE_SOURCE_COMMIT_MISMATCH"):
        store.issue_ingestion_capability(body, batch_ticket=batch.batch_ticket)
    _assert_atomicity(store, snapshot)


def test_e1_findings_member_is_preserved_by_shared_raw_transform(e1_setup):
    import json
    store, batch, inbox, tmp = e1_setup
    manifest = _legitimate_manifest(batch, "E1-A")
    findings = manifest.pop("findings")
    path = _create_zip(tmp / "findings-member.zip", manifest, {"FINDINGS.json": json.dumps(findings)})
    result = inbox.ingest_zip(path)
    assert result[1] == "ACCEPTED", result
    accepted = store.accepted_records("bdb_audit_lane_result", _current_cut(store))
    assert accepted[0]["body"]["findings"] == findings


def _restart_and_import(store, batch, root, result_path):
    restarted = TransactionalHistoryStore(store.path)
    snapshot = _snapshot_store(restarted)
    resumed, source = load_stage_phase_batch(restarted, root, stage_id=batch.stage_id, phase_id=batch.phase_id)
    _assert_atomicity(restarted, snapshot)
    assert resumed.batch_ticket
    assert resumed.frozen_history_cut == batch.frozen_history_cut
    for slot in batch.lane_slots:
        assert resumed.get_job(slot).assignment_ref == batch.get_job(slot).assignment_ref
        assert resumed.get_job(slot).package_zip_sha256 == batch.get_job(slot).package_zip_sha256
    inbox = StageResultInbox(restarted, resumed)
    result = inbox.ingest_zip(result_path)
    assert result[1] == "ACCEPTED", result
    head = restarted.head()
    assert StageResultInbox(TransactionalHistoryStore(store.path), resumed).ingest_zip(result_path)[1] == "ACCEPTED"
    assert restarted.head() == head


def test_e2_valid_result_imports_after_store_and_batch_restart(e2_phase):
    store, batch, _, tmp = e2_phase
    path = _write_result(tmp / "restart-e2.zip", batch, "E2-CONVERGENCE")
    _restart_and_import(store, batch, tmp / "work", path)


@pytest.mark.parametrize("delete", [False, True])
def test_manual_restart_rejects_missing_or_tampered_package_atomically(e2_phase, delete):
    store, batch, _, tmp = e2_phase
    snapshot = _snapshot_store(store)
    path = batch.get_job("E2-CONVERGENCE").package_zip_path
    if delete:
        path.unlink()
    else:
        path.write_bytes(b"tampered")
    with pytest.raises(ValidationError):
        load_stage_phase_batch(TransactionalHistoryStore(store.path), tmp / "work", stage_id="E2", phase_id=batch.phase_id)
    _assert_atomicity(store, snapshot)


def test_e3_valid_result_imports_after_store_and_batch_restart(tmp_path):
    store, source, lane, _ = _prepare_e3_isolation_fixture(tmp_path, seed="nf02-e3-restart")
    root = tmp_path / "work"
    batch = prepare_stage_phase_batch(
        store=store, output_dir=root, source_info=source, stage_id="E3", phase_id="E3-BLIND",
        lane_definitions=(lane,), all_stage_lane_slots=(lane.lane_slot,),
    )
    path = _write_result(tmp_path / "restart-e3.zip", batch, lane.lane_slot)
    _restart_and_import(store, batch, root, path)


def test_e4_valid_result_imports_after_store_and_batch_restart(e4_phase):
    store, batch, _, tmp = e4_phase
    path = _write_e4_result(tmp / "restart-e4.zip", batch, "E4-RESILIENCE")
    _restart_and_import(store, batch, tmp / "work", path)

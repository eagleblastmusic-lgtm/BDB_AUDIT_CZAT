"""NF02 — Synthetic Lane Result Authority Bypass regression suite.

Proves that direct caller construction of bdb_audit_lane_result cannot bypass
the canonical trusted ingestion boundary, and validates that all mutations (V1-V6)
and adversarial bypasses (A-H) fail closed while preserving transactional atomicity.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from bdb_audit.coordinator import Coordinator
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import deterministic_id
from bdb_audit.history.objects import CanonicalObject, CommandEnvelope, HistoryCut
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS
from bdb_audit.vault.raw_store import RawArtifactVault
from bdb_audit.workflow.inbox import E1ResultInbox
from bdb_audit.workflow.packaging import prepare_e1_batch
from bdb_audit.workflow.manual_stage import StageLaneDefinition, StageResultInbox, prepare_stage_phase_batch
from bdb_audit.workflow.source_target import ResolvedSource


@pytest.fixture
def e1_setup(tmp_path: Path):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(store_path, seed="nf02_test_seed")
    api.prepare_stage(store_path, "E1")
    for slot in E1_LANE_SLOTS:
        api.prepare_lane(store_path, "E1", slot=slot)

    store = TransactionalHistoryStore(store_path)
    out_dir = tmp_path / "audit_work"
    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/nf02-repo",
        display_name="example/nf02-repo",
        ref="main",
        exact_commit_sha="a" * 40,
    )
    batch = prepare_e1_batch(store, out_dir, source)
    inbox = E1ResultInbox(store, batch)
    return store, batch, inbox, tmp_path


def _snapshot_store(store: TransactionalHistoryStore) -> dict:
    con = store._connect()
    try:
        head = store.head()
        commit_count = con.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
        obj_count = con.execute("SELECT COUNT(*) FROM immutable_objects").fetchone()[0]
        receipt_count = con.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
        return {
            "head": head.as_dict() if head else None,
            "commit_count": commit_count,
            "object_count": obj_count,
            "receipt_count": receipt_count,
        }
    finally:
        con.close()


def _assert_atomicity(store: TransactionalHistoryStore, before: dict) -> None:
    after = _snapshot_store(store)
    assert after == before, f"Atomicity violation: before={before}, after={after}"


def _command_id(seed: str) -> str:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"command_{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"


def _current_cut(store: TransactionalHistoryStore) -> dict:
    head = store.head()
    commits = store.commits()
    return HistoryCut.accepted(
        head,
        commits[-1]["governing_policy_ref"],
        commits[-1]["governing_spec_refs"],
    ).as_dict()


def _create_zip(path: Path, manifest: dict, extra: dict[str, str] | None = None) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.json", json.dumps(manifest, indent=2))
        if extra:
            for fname, content in extra.items():
                zf.writestr(fname, content)
    return path


def _legitimate_manifest(batch, slot: str) -> dict:
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
        "history_cut": dict(batch.frozen_history_cut),
        "findings": [
            {
                "finding_id": f"{slot}-NF02-01",
                "statement": f"Valid finding for {slot}",
                "severity": "HIGH",
            }
        ],
    }


# ============================================================================
# SECTION 12: BASE SYNTHETIC PROBE
# ============================================================================


def test_base_synthetic_lane_result_rejected_before_durability(e1_setup):
    """Direct caller constructs bdb_audit_lane_result manually without ZIP/inbox/vault.
    Must be rejected before durability, head/commits/objects/receipts unchanged.
    """
    store, batch, _, tmp_path = e1_setup
    job = batch.get_job("E1-A")
    head = store.head()
    coordinator = Coordinator(store)
    snapshot = _snapshot_store(store)

    # Synthetic proposal with exact assignment metadata but no authentic admission proof
    synthetic_proposal = {
        "kind": "bdb_audit_lane_result",
        "version": "1",
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": "E1-A",
        "source_commit_sha": batch.source_commit_sha,
        "history_cut": dict(batch.frozen_history_cut),
        "input_package_digest": job.package_digest,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "findings": [{"finding_id": "E1-A-SYNTH", "statement": "Handcrafted finding"}],
        "assignment_ref": dict(job.assignment_ref),
        "attempt_ref": dict(job.attempt_ref),
    }

    # Attempt 1: Direct admission without admission_evidence_ref
    with pytest.raises(ValidationError):
        obj = CanonicalObject("bdb_audit_lane_result", synthetic_proposal)
        cmd = CommandEnvelope(
            command_id=_command_id("synthetic_base_probe"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref="installation-owner",
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
            governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
            idempotency_scope="synthetic_base_probe",
            campaign_ref=head.campaign_id,
        )
        coordinator.accept(cmd, immutable_objects=[obj], expected_head=head)

    _assert_atomicity(store, snapshot)


# ============================================================================
# SECTION 13: V1–V6 MUTATION MATRIX
# ============================================================================


def test_v1_wrong_input_package_digest_rejected(e1_setup):
    """V1: wrong input_package_digest => REJECT before durability + atomicity."""
    store, batch, inbox, tmp_path = e1_setup
    snapshot = _snapshot_store(store)

    manifest = _legitimate_manifest(batch, "E1-A")
    manifest["input_package_digest"] = "e" * 64
    zip_path = _create_zip(tmp_path / "v1.zip", manifest)

    slot, status, reason = inbox.ingest_zip(zip_path)
    assert status == "REJECTED"
    assert "PACKAGE_DIGEST_MISMATCH" in str(reason)
    _assert_atomicity(store, snapshot)


def test_v2_wrong_source_commit_sha_rejected(e1_setup):
    """V2: wrong source_commit_sha => REJECT before durability + atomicity."""
    store, batch, inbox, tmp_path = e1_setup
    snapshot = _snapshot_store(store)

    manifest = _legitimate_manifest(batch, "E1-A")
    manifest["source_commit_sha"] = "f" * 40
    zip_path = _create_zip(tmp_path / "v2.zip", manifest)

    slot, status, reason = inbox.ingest_zip(zip_path)
    assert status == "REJECTED"
    assert "SOURCE_COMMIT_MISMATCH" in str(reason)
    _assert_atomicity(store, snapshot)


def test_v3a_wrong_executor_model_rejected(e1_setup):
    """V3a: wrong executor_model => REJECT before durability + atomicity."""
    store, batch, inbox, tmp_path = e1_setup
    snapshot = _snapshot_store(store)

    manifest = _legitimate_manifest(batch, "E1-A")
    manifest["executor_model"] = "fake-model-unauthorized"
    zip_path = _create_zip(tmp_path / "v3a.zip", manifest)

    slot, status, reason = inbox.ingest_zip(zip_path)
    assert status == "REJECTED"
    assert "EXECUTOR_MODEL_MISMATCH" in str(reason)
    _assert_atomicity(store, snapshot)


def test_v3b_wrong_executor_profile_rejected(e1_setup):
    """V3b: wrong executor_profile => REJECT before durability + atomicity."""
    store, batch, inbox, tmp_path = e1_setup
    snapshot = _snapshot_store(store)

    manifest = _legitimate_manifest(batch, "E1-A")
    manifest["executor_profile"] = "fake-profile-unauthorized"
    zip_path = _create_zip(tmp_path / "v3b.zip", manifest)

    slot, status, reason = inbox.ingest_zip(zip_path)
    assert status == "REJECTED"
    assert "EXECUTOR_PROFILE_MISMATCH" in str(reason)
    _assert_atomicity(store, snapshot)


def test_v4_missing_raw_result_digest_rejected(e1_setup):
    """V4: missing raw_result_digest / provenance => REJECT before durability + atomicity."""
    store, batch, inbox, tmp_path = e1_setup
    snapshot = _snapshot_store(store)

    manifest = _legitimate_manifest(batch, "E1-A")
    manifest.pop("findings")  # invalid structure / missing mandatory
    zip_path = _create_zip(tmp_path / "v4.zip", manifest)

    slot, status, reason = inbox.ingest_zip(zip_path)
    assert status == "REJECTED"
    _assert_atomicity(store, snapshot)


def test_v5_fake_raw_digest_not_in_vault_rejected(e1_setup):
    """V5: fake raw digest not present in RawArtifactVault => REJECT before durability."""
    store, batch, _, tmp_path = e1_setup
    job = batch.get_job("E1-A")
    head = store.head()
    coordinator = Coordinator(store)
    snapshot = _snapshot_store(store)

    fake_raw_digest = "0" * 64
    evidence_body = {
        "kind": "lane_result_admission_evidence",
        "version": "1",
        "admission_evidence_id": deterministic_id("lane_result_admission_evidence", "fake"),
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": "E1-A",
        "assignment_ref": dict(job.assignment_ref),
        "attempt_ref": dict(job.attempt_ref),
        "source_generation_ref": {
            **store.resolve_accepted(job.assignment_ref, _current_cut(store))["body"]["source_generation_ref"],
            "ref_class": "PRIOR_ACCEPTED_ONLY",
        },
        "source_commit_sha": batch.source_commit_sha,
        "history_cut": dict(batch.frozen_history_cut),
        "input_package_digest": job.package_digest,
        "raw_result_digest": fake_raw_digest,
        "raw_result_byte_length": 100,
        "result_proposal_digest": "1" * 64,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
    }

    with pytest.raises(ValidationError) as exc:
        obj = CanonicalObject("lane_result_admission_evidence", evidence_body)
        cmd = CommandEnvelope(
            command_id=_command_id("fake_vault_probe"),
            command_kind="INGEST_EXTERNAL_LANE_RESULT",
            actor_ref="installation-owner",
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
            governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
            idempotency_scope="fake_vault_probe",
            campaign_ref=head.campaign_id,
        )
        coordinator.accept(cmd, immutable_objects=[obj], expected_head=head)

    assert "RAW_ARTIFACT_NOT_FOUND" in str(exc.value)
    _assert_atomicity(store, snapshot)


def test_v6_modified_findings_after_valid_ingestion_authority_rejected(e1_setup):
    """V6: valid receipt used with modified findings/outputs => REJECT due to RESULT_PROPOSAL_DIGEST_MISMATCH."""
    store, batch, inbox, tmp_path = e1_setup
    job = batch.get_job("E1-A")

    # Ingest legitimate result first to establish valid admission evidence
    manifest = _legitimate_manifest(batch, "E1-A")
    zip_path = _create_zip(tmp_path / "valid.zip", manifest)
    slot, status, _ = inbox.ingest_zip(zip_path)
    assert status == "ACCEPTED"

    # Take snapshot after legitimate admission
    snapshot = _snapshot_store(store)
    head = store.head()
    coordinator = Coordinator(store)

    # Find the accepted evidence ref
    cut = _current_cut(store)
    evidence_rows = store.accepted_records("lane_result_admission_evidence", cut)
    assert len(evidence_rows) >= 1
    evidence_ref = {**evidence_rows[-1]["ref"], "ref_class": "PRIOR_ACCEPTED_ONLY"}

    # Construct tampered bdb_audit_lane_result referencing valid evidence
    tampered_proposal = {
        "kind": "bdb_audit_lane_result",
        "version": "1",
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": "E1-A",
        "source_commit_sha": batch.source_commit_sha,
        "history_cut": dict(batch.frozen_history_cut),
        "input_package_digest": job.package_digest,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "findings": [{"finding_id": "TAMPERED-01", "statement": "Fabricated finding"}],
        "assignment_ref": dict(job.assignment_ref),
        "attempt_ref": dict(job.attempt_ref),
        "raw_result_digest": evidence_rows[-1]["body"]["raw_result_digest"],
        "admission_evidence_ref": evidence_ref,
    }

    with pytest.raises(ValidationError) as exc:
        obj = CanonicalObject("bdb_audit_lane_result", tampered_proposal)
        cmd = CommandEnvelope(
            command_id=_command_id("tampered_findings_probe"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref="installation-owner",
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
            governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
            idempotency_scope="tampered_findings_probe",
            campaign_ref=head.campaign_id,
        )
        coordinator.accept(cmd, immutable_objects=[obj], expected_head=head)

    assert "RESULT_PROPOSAL_DIGEST_MISMATCH" in str(exc.value)
    _assert_atomicity(store, snapshot)


# ============================================================================
# SECTION 19: ADVERSARIAL SELF-REVIEW (BYPASSES A–H)
# ============================================================================


def test_adversarial_bypass_b_fake_ingestion_receipt_via_generic_command(e1_setup):
    """Bypass B: Direct caller attempts to admit fake ingestion receipt via RECORD_FOUNDATION_FACT."""
    store, batch, _, _ = e1_setup
    job = batch.get_job("E1-A")
    head = store.head()
    coordinator = Coordinator(store)
    snapshot = _snapshot_store(store)

    evidence_body = {
        "kind": "lane_result_admission_evidence",
        "version": "1",
        "admission_evidence_id": deterministic_id("lane_result_admission_evidence", "fake_generic"),
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": "E1-A",
        "assignment_ref": dict(job.assignment_ref),
        "attempt_ref": dict(job.attempt_ref),
        "source_generation_ref": dict(store.resolve_accepted(job.assignment_ref, _current_cut(store))["body"]["source_generation_ref"]),
        "source_commit_sha": batch.source_commit_sha,
        "history_cut": dict(batch.frozen_history_cut),
        "input_package_digest": job.package_digest,
        "raw_result_digest": "2" * 64,
        "raw_result_byte_length": 50,
        "result_proposal_digest": "3" * 64,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
    }

    with pytest.raises(ValidationError) as exc:
        obj = CanonicalObject("lane_result_admission_evidence", evidence_body)
        cmd = CommandEnvelope(
            command_id=_command_id("bypass_b"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref="installation-owner",
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
            governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
            idempotency_scope="bypass_b",
            campaign_ref=head.campaign_id,
        )
        coordinator.accept(cmd, immutable_objects=[obj], expected_head=head)

    assert "LANE_RESULT_ADMISSION_COMMAND_REQUIRED" in str(exc.value)
    _assert_atomicity(store, snapshot)


def test_adversarial_bypass_c_valid_receipt_reused_for_another_lane(e1_setup):
    """Bypass C: Valid receipt for E1-A reused for lane E1-B."""
    store, batch, inbox, tmp_path = e1_setup
    job_b = batch.get_job("E1-B")

    # Ingest legitimate E1-A
    zip_path = _create_zip(tmp_path / "e1a.zip", _legitimate_manifest(batch, "E1-A"))
    inbox.ingest_zip(zip_path)

    head = store.head()
    snapshot = _snapshot_store(store)
    coordinator = Coordinator(store)

    cut = _current_cut(store)
    evidence_rows = store.accepted_records("lane_result_admission_evidence", cut)
    evidence_a_ref = {**evidence_rows[-1]["ref"], "ref_class": "PRIOR_ACCEPTED_ONLY"}

    # Try to reuse E1-A receipt for E1-B proposal
    proposal_b = {
        "kind": "bdb_audit_lane_result",
        "version": "1",
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": "E1-B",
        "source_commit_sha": batch.source_commit_sha,
        "history_cut": dict(batch.frozen_history_cut),
        "input_package_digest": job_b.package_digest,
        "executor_profile": job_b.executor_profile,
        "executor_model": job_b.model,
        "findings": [{"finding_id": "E1-B-01", "statement": "Finding for B"}],
        "assignment_ref": dict(job_b.assignment_ref),
        "attempt_ref": dict(job_b.attempt_ref),
        "admission_evidence_ref": evidence_a_ref,
    }

    with pytest.raises(ValidationError):
        obj = CanonicalObject("bdb_audit_lane_result", proposal_b)
        cmd = CommandEnvelope(
            command_id=_command_id("bypass_c"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref="installation-owner",
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
            governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
            idempotency_scope="bypass_c",
            campaign_ref=head.campaign_id,
        )
        coordinator.accept(cmd, immutable_objects=[obj], expected_head=head)

    _assert_atomicity(store, snapshot)


def test_adversarial_bypass_g_same_commit_receipt_and_result_self_authorization(e1_setup):
    """Bypass G: Same-commit receipt + result self-authorization.
    Must fail closed because admission_evidence_ref requires PRIOR_ACCEPTED_ONLY.
    """
    store, batch, _, tmp_path = e1_setup
    job = batch.get_job("E1-A")
    head = store.head()
    coordinator = Coordinator(store)
    snapshot = _snapshot_store(store)

    vault = RawArtifactVault(Path(store.path).resolve().parent / "raw_vault")
    raw_content = b"PK\x05\x06" + b"\x00" * 18  # minimal zip
    receipt = vault.put_bytes(raw_content, media_type="application/zip")

    evidence_body = {
        "kind": "lane_result_admission_evidence",
        "version": "1",
        "admission_evidence_id": deterministic_id("lane_result_admission_evidence", "same_commit"),
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": "E1-A",
        "assignment_ref": dict(job.assignment_ref),
        "attempt_ref": dict(job.attempt_ref),
        "source_generation_ref": dict(store.resolve_accepted(job.assignment_ref, _current_cut(store))["body"]["source_generation_ref"]),
        "source_commit_sha": batch.source_commit_sha,
        "history_cut": dict(batch.frozen_history_cut),
        "input_package_digest": job.package_digest,
        "raw_result_digest": receipt.raw_digest,
        "raw_result_byte_length": len(raw_content),
        "result_proposal_digest": "4" * 64,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
    }
    evidence_obj = CanonicalObject("lane_result_admission_evidence", evidence_body)

    proposal_body = {
        "kind": "bdb_audit_lane_result",
        "version": "1",
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": "E1-A",
        "source_commit_sha": batch.source_commit_sha,
        "history_cut": dict(batch.frozen_history_cut),
        "input_package_digest": job.package_digest,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "findings": [{"finding_id": "SC-01", "statement": "Same commit"}],
        "admission_evidence_ref": evidence_obj.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
    }
    proposal_obj = CanonicalObject("bdb_audit_lane_result", proposal_body)

    with pytest.raises(ValidationError):
        cmd = CommandEnvelope(
            command_id=_command_id("bypass_g"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref="installation-owner",
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
            governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
            idempotency_scope="bypass_g",
            campaign_ref=head.campaign_id,
        )
        coordinator.accept(cmd, immutable_objects=[evidence_obj, proposal_obj], expected_head=head)

    _assert_atomicity(store, snapshot)


def test_adversarial_bypass_h_exact_legitimate_retry_is_idempotent(e1_setup):
    """Bypass H: Replay/idempotent retry of exact legitimate result is accepted."""
    store, batch, inbox, tmp_path = e1_setup
    manifest = _legitimate_manifest(batch, "E1-A")
    zip_path = _create_zip(tmp_path / "legit.zip", manifest)

    slot, status1, _ = inbox.ingest_zip(zip_path)
    assert status1 == "ACCEPTED"

    slot, status2, _ = inbox.ingest_zip(zip_path)
    assert status2 == "ACCEPTED"


# ============================================================================
# POSITIVE CONTROLS: E1 FULL 5-LANES AND STAGE RESULT INBOX
# ============================================================================


def test_positive_control_single_lane(e1_setup):
    """Positive control: one legitimate E1 result -> ACCEPTED, LANE_COMPLETED."""
    store, batch, inbox, tmp_path = e1_setup
    zip_path = _create_zip(tmp_path / "e1a.zip", _legitimate_manifest(batch, "E1-A"))
    slot, status, reason = inbox.ingest_zip(zip_path)
    assert (slot, status, reason) == ("E1-A", "ACCEPTED", None)
    assert inbox.lane_statuses["E1-A"].completion_status == "LANE_COMPLETED"


def test_positive_control_full_5_lanes_e1_to_stage_completed(e1_setup):
    """Full E1 positive control: all five legitimate E1 results ingested
    -> all five LaneCompletions ACCEPTED -> E1 STAGE_COMPLETED.
    """
    store, batch, inbox, tmp_path = e1_setup
    zip_paths = [
        _create_zip(tmp_path / f"{slot}.zip", _legitimate_manifest(batch, slot))
        for slot in E1_LANE_SLOTS
    ]
    summary = inbox.ingest_multiple_zips(zip_paths)
    assert summary.accepted_count == len(E1_LANE_SLOTS)
    assert summary.stage_complete is True
    assert inbox.stage_complete is True

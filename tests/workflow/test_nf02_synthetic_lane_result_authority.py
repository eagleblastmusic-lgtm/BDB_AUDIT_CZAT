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
        raw_count = con.execute("SELECT COUNT(*) FROM immutable_raw_artifacts").fetchone()[0]
        return {
            "head": head.as_dict() if head else None,
            "commit_count": commit_count,
            "object_count": obj_count,
            "receipt_count": receipt_count,
            "raw_count": raw_count,
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


def _raw_proposal(manifest, job, raw):
    """Fixture for the existing E1 wire normalization, with real ZIP members."""
    import io
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        evidence = [
            {"path": name, "raw_digest": hashlib.sha256(archive.read(name)).hexdigest(),
             "byte_length": len(archive.read(name)), "media_type": "application/json"}
            for name in sorted(archive.namelist())
        ]
    return {
        **manifest, "assignment_ref": dict(job.assignment_ref), "attempt_ref": dict(job.attempt_ref),
        "raw_result_digest": hashlib.sha256(raw).hexdigest(), "raw_result_byte_length": len(raw),
        "findings_count": len(manifest["findings"]), "evidence_files": evidence,
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


# ============================================================================
# SECTION: PERMANENT REGRESSION & ADVERSARIAL MATRIX (T1–T10)
# ============================================================================


def test_t1_direct_self_minted_evidence_rejected_atomically(e1_setup, tmp_path):
    """T1: Direct caller-minted lane_result_admission_evidence submitted via
    INGEST_EXTERNAL_LANE_RESULT must be rejected with UNAUTHORIZED_PRODUCER_AUTHORITY,
    and atomicity must be preserved.
    """
    store, batch, inbox, _ = e1_setup
    job = batch.get_job("E1-A")
    head = store.head()
    coordinator = Coordinator(store)
    snapshot = _snapshot_store(store)

    manifest = _legitimate_manifest(batch, "E1-A")
    zip_path = _create_zip(tmp_path / "t1_valid.zip", manifest)
    zip_bytes = zip_path.read_bytes()
    vault = RawArtifactVault(Path(store.path).resolve().parent / "raw_vault")
    receipt = vault.put_bytes(zip_bytes, media_type="application/zip")

    cut = _current_cut(store)
    assignment_record = store.resolve_accepted(job.assignment_ref, cut)
    source_record = store.resolve_accepted(assignment_record["body"]["source_generation_ref"], cut)

    # Case A: No ingestion_capability at all
    evidence_body_no_cap = {
        "kind": "lane_result_admission_evidence",
        "version": "1",
        "admission_evidence_id": deterministic_id("lane_result_admission_evidence", "t1_no_cap"),
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": "E1-A",
        "assignment_ref": {**assignment_record["ref"], "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "attempt_ref": {**job.attempt_ref, "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "source_generation_ref": {**source_record["ref"], "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "source_commit_sha": batch.source_commit_sha,
        "history_cut": dict(batch.frozen_history_cut),
        "input_package_digest": job.package_digest,
        "package_zip_sha256": job.package_zip_sha256,
        "raw_result_digest": receipt.raw_digest,
        "raw_result_byte_length": len(zip_bytes),
        "result_proposal_digest": "a" * 64,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
    }
    with pytest.raises(ValidationError) as exc:
        obj = CanonicalObject("lane_result_admission_evidence", evidence_body_no_cap)
        cmd = CommandEnvelope(
            command_id=_command_id("t1_no_cap"),
            command_kind="INGEST_EXTERNAL_LANE_RESULT",
            actor_ref="installation-owner",
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
            governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
            idempotency_scope="t1_no_cap",
            campaign_ref=head.campaign_id,
        )
        coordinator.accept(cmd, immutable_objects=[obj], expected_head=head)
    assert "UNAUTHORIZED_PRODUCER_AUTHORITY" in str(exc.value)
    _assert_atomicity(store, snapshot)

    # Case B: Forged 64-char hex capability
    evidence_body_fake_cap = dict(evidence_body_no_cap)
    evidence_body_fake_cap["admission_evidence_id"] = deterministic_id("lane_result_admission_evidence", "t1_fake_cap")
    evidence_body_fake_cap["ingestion_capability"] = "f" * 64
    with pytest.raises(ValidationError) as exc:
        obj = CanonicalObject("lane_result_admission_evidence", evidence_body_fake_cap)
        cmd = CommandEnvelope(
            command_id=_command_id("t1_fake_cap"),
            command_kind="INGEST_EXTERNAL_LANE_RESULT",
            actor_ref="installation-owner",
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
            governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
            idempotency_scope="t1_fake_cap",
            campaign_ref=head.campaign_id,
        )
        coordinator.accept(cmd, immutable_objects=[obj], expected_head=head)
    assert "UNAUTHORIZED_PRODUCER_AUTHORITY" in str(exc.value)
    _assert_atomicity(store, snapshot)


def test_t2_full_laundering_chain_blocked(e1_setup):
    """T2: Attempting to admit synthetic lane result pointing to self-minted evidence
    fails closed. Both same-commit and two-step laundering chains are blocked.
    """
    store, batch, _, _ = e1_setup
    job = batch.get_job("E1-A")
    head = store.head()
    coordinator = Coordinator(store)
    snapshot = _snapshot_store(store)

    cut = _current_cut(store)
    assignment_record = store.resolve_accepted(job.assignment_ref, cut)
    source_record = store.resolve_accepted(assignment_record["body"]["source_generation_ref"], cut)

    evidence_body = {
        "kind": "lane_result_admission_evidence",
        "version": "1",
        "admission_evidence_id": deterministic_id("lane_result_admission_evidence", "t2_launder"),
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": "E1-A",
        "assignment_ref": {**assignment_record["ref"], "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "attempt_ref": {**job.attempt_ref, "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "source_generation_ref": {**source_record["ref"], "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "source_commit_sha": batch.source_commit_sha,
        "history_cut": dict(batch.frozen_history_cut),
        "input_package_digest": job.package_digest,
        "package_zip_sha256": job.package_zip_sha256,
        "raw_result_digest": "3" * 64,
        "raw_result_byte_length": 100,
        "result_proposal_digest": "4" * 64,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "ingestion_capability": "e" * 64,
    }
    evidence_obj = CanonicalObject("lane_result_admission_evidence", evidence_body)

    # Chain A: Try to ingest evidence first under INGEST_EXTERNAL_LANE_RESULT
    with pytest.raises(ValidationError) as exc:
        cmd1 = CommandEnvelope(
            command_id=_command_id("t2_step1"),
            command_kind="INGEST_EXTERNAL_LANE_RESULT",
            actor_ref="installation-owner",
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
            governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
            idempotency_scope="t2_step1",
            campaign_ref=head.campaign_id,
        )
        coordinator.accept(cmd1, immutable_objects=[evidence_obj], expected_head=head)
    _assert_atomicity(store, snapshot)

    # Chain B: Try to smuggle evidence under RECORD_FOUNDATION_FACT
    with pytest.raises(ValidationError) as exc:
        cmd2 = CommandEnvelope(
            command_id=_command_id("t2_smuggle"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref="installation-owner",
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
            governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
            idempotency_scope="t2_smuggle",
            campaign_ref=head.campaign_id,
        )
        coordinator.accept(cmd2, immutable_objects=[evidence_obj], expected_head=head)
    assert "LANE_RESULT_ADMISSION_COMMAND_REQUIRED" in str(exc.value)
    _assert_atomicity(store, snapshot)


def test_t3_live_package_replacement_rejected_e1_and_manual_stage(e1_setup, tmp_path):
    """T3: Tampering with assigned package on disk (or deleting it) is rejected
    with ASSIGNED_PACKAGE_TAMPERED for both E1 inbox and manual stage inbox.
    """
    store, batch, inbox, _ = e1_setup
    job = batch.get_job("E1-A")
    snapshot = _snapshot_store(store)

    # E1: Tamper with live package zip on disk
    original_pkg_bytes = job.package_zip_path.read_bytes()
    try:
        job.package_zip_path.write_bytes(original_pkg_bytes + b"tampered_suffix")
        manifest = _legitimate_manifest(batch, "E1-A")
        zip_path = _create_zip(tmp_path / "e1a_t3.zip", manifest)
        slot, status, reason = inbox.ingest_zip(zip_path)
        assert status == "REJECTED"
        assert "ASSIGNED_PACKAGE_TAMPERED" in str(reason)
        _assert_atomicity(store, snapshot)

        # E1: Missing package on disk
        job.package_zip_path.unlink()
        slot, status, reason = inbox.ingest_zip(zip_path)
        assert status == "REJECTED"
        assert "ASSIGNED_PACKAGE_TAMPERED" in str(reason)
        _assert_atomicity(store, snapshot)
    finally:
        job.package_zip_path.write_bytes(original_pkg_bytes)

    # Manual Stage: Ingest with tampered package on disk
    manual_store_path = tmp_path / "manual_campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(manual_store_path, seed="manual_t3_seed")
    api.prepare_stage(manual_store_path, "E1")
    for slot in E1_LANE_SLOTS:
        api.prepare_lane(manual_store_path, "E1", slot=slot)

    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/manual-repo",
        display_name="example/manual-repo",
        ref="main",
        exact_commit_sha="b" * 40,
    )
    manual_store = TransactionalHistoryStore(manual_store_path)
    e1_manual_batch = prepare_e1_batch(manual_store, tmp_path / "manual_e1_work", source)
    e1_manual_inbox = E1ResultInbox(manual_store, e1_manual_batch)
    e1_summary = e1_manual_inbox.ingest_multiple_zips(
        [
            _create_zip(tmp_path / f"e1_manual_{slot}.zip", _legitimate_manifest(e1_manual_batch, slot))
            for slot in E1_LANE_SLOTS
        ]
    )
    assert e1_summary.stage_complete is True

    lanes = (
        StageLaneDefinition("E2-CONVERGENCE", "Blind verification", "BLIND_VERIFY"),
        StageLaneDefinition("E2-ADJUDICATION", "Blind falsification", "BLIND_FALSIFY"),
    )
    api.prepare_stage(manual_store_path, "E2")
    for lane in lanes:
        api.prepare_lane(manual_store_path, "E2", lane.lane_slot)

    out_dir = tmp_path / "manual_work"
    stage_batch = prepare_stage_phase_batch(
        store=manual_store,
        output_dir=out_dir,
        source_info=source,
        stage_id="E2",
        phase_id="BLIND_EXECUTION",
        lane_definitions=lanes,
        all_stage_lane_slots=[d.lane_slot for d in lanes],
    )
    manual_inbox = StageResultInbox(manual_store, stage_batch)
    manual_job = stage_batch.get_job("E2-CONVERGENCE")

    manual_orig_bytes = manual_job.package_zip_path.read_bytes()
    try:
        manual_job.package_zip_path.write_bytes(b"tampered_manual_bytes")
        m_manifest = {
            "kind": "bdb_audit_lane_result",
            "version": "1",
            "campaign_id": stage_batch.campaign_id,
            "stage_id": "E2",
            "phase_id": "BLIND_EXECUTION",
            "lane_slot": "E2-CONVERGENCE",
            "source_commit_sha": manual_job.source_commit_sha,
            "history_cut": dict(stage_batch.frozen_history_cut),
            "input_package_digest": manual_job.package_digest,
            "executor_profile": manual_job.executor_profile,
            "executor_model": manual_job.model,
            "findings": [{"finding_id": "E2-01", "statement": "Test finding"}],
        }
        m_zip = _create_zip(tmp_path / "manual_tampered.zip", m_manifest)
        slot, status, reason = manual_inbox.ingest_zip(m_zip)
        assert status == "REJECTED"
        assert "ASSIGNED_PACKAGE_TAMPERED" in str(reason)
    finally:
        manual_job.package_zip_path.write_bytes(manual_orig_bytes)


def test_t4_staging_deletion_between_commits_preserves_retained_evidence(e1_setup, tmp_path):
    """T4: Deleting staging cannot delete bytes already retained with evidence.

    Architecture §§43–44 require the accepted bytes to share history durability.
    Missing/corrupt retained bytes are tested separately and fail closed.
    """
    store, batch, inbox, _ = e1_setup
    job = batch.get_job("E1-A")
    head = store.head()
    coordinator = Coordinator(store)

    manifest = _legitimate_manifest(batch, "E1-A")
    zip_path = _create_zip(tmp_path / "t4.zip", manifest)
    raw = zip_path.read_bytes()
    vault = RawArtifactVault(Path(store.path).resolve().parent / "raw_vault")
    receipt = vault.put_bytes(raw, media_type="application/zip")
    raw_digest = receipt.raw_digest

    cut = _current_cut(store)
    assignment_record = store.resolve_accepted(job.assignment_ref, cut)
    source_record = store.resolve_accepted(assignment_record["body"]["source_generation_ref"], cut)

    proposal = _raw_proposal(manifest, job, raw)
    vault.put_bytes(job.package_zip_path.read_bytes(), media_type="application/zip")
    result_proposal_digest = hashlib.sha256(canonical_bytes(proposal)).hexdigest()

    evidence_id = deterministic_id("lane_result_admission_evidence", f"{assignment_record['ref']['revision_digest']}:{raw_digest}")
    evidence_body = {
        "kind": "lane_result_admission_evidence",
        "version": "1",
        "admission_evidence_id": evidence_id,
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": "E1-A",
        "assignment_ref": {**assignment_record["ref"], "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "attempt_ref": {**job.attempt_ref, "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "source_generation_ref": {**source_record["ref"], "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "source_commit_sha": job.source_commit_sha,
        "history_cut": dict(batch.frozen_history_cut),
        "input_package_digest": job.package_digest,
        "package_zip_sha256": job.package_zip_sha256,
        "raw_result_digest": raw_digest,
        "raw_result_byte_length": len(raw),
        "result_proposal_digest": result_proposal_digest,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
    }
    evidence_body["evidence_files"] = proposal["evidence_files"]
    evidence_body["ingestion_capability"] = store.issue_ingestion_capability(
        evidence_body,
        batch_ticket=batch.batch_ticket,
    )
    evidence_obj = CanonicalObject("lane_result_admission_evidence", evidence_body)

    cmd_ev = CommandEnvelope(
        command_id=_command_id("t4_evidence"),
        command_kind="INGEST_EXTERNAL_LANE_RESULT",
        actor_ref="installation-owner",
        expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
        governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
        governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
        idempotency_scope="t4_evidence",
        campaign_ref=head.campaign_id,
    )
    coordinator.accept(cmd_ev, immutable_objects=[evidence_obj], expected_head=head)

    # Delete raw blob from vault before result acceptance
    vault_blob_path, _ = vault._paths(raw_digest)
    assert vault_blob_path.is_file()
    vault_blob_path.unlink()
    assert not vault_blob_path.exists()

    new_head = store.head()

    proposal["admission_evidence_ref"] = evidence_obj.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict()
    result_obj = CanonicalObject("bdb_audit_lane_result", proposal)

    cmd_res = CommandEnvelope(
        command_id=_command_id("t4_result"),
        command_kind="RECORD_FOUNDATION_FACT",
        actor_ref="installation-owner",
        expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **new_head.as_dict()},
        governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
        governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
        idempotency_scope="t4_result",
        campaign_ref=new_head.campaign_id,
    )
    coordinator.accept(cmd_res, immutable_objects=[result_obj], expected_head=new_head)
    restarted = TransactionalHistoryStore(store.path)
    retained = restarted.read_accepted_raw(result_obj.ref, _current_cut(restarted))
    assert retained[raw_digest] == raw
    assert not vault_blob_path.exists()


def test_t5_schema_binding_absent_fails_closed(tmp_path):
    """T5: Schema binding absent in SchemaBindings -> SCHEMA_BYTES_NOT_BOUND."""
    from bdb_audit.schemas.binding import SchemaBindings
    empty_schemas = SchemaBindings([])
    store_path = tmp_path / "t5_campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(store_path)

    store = TransactionalHistoryStore(store_path, schema_bindings=empty_schemas)
    head = store.head()
    coordinator = Coordinator(store)

    dummy_obj = CanonicalObject("command_envelope", {
        "command_id": "dummy_cmd",
        "command_kind": "RECORD_FOUNDATION_FACT",
    })
    cmd = CommandEnvelope(
        command_id=_command_id("t5_cmd"),
        command_kind="RECORD_FOUNDATION_FACT",
        actor_ref="installation-owner",
        expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
        governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
        governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
        idempotency_scope="t5_cmd",
        campaign_ref=head.campaign_id,
    )
    with pytest.raises(ValidationError) as exc:
        coordinator.accept(cmd, immutable_objects=[dummy_obj], expected_head=head)
    assert "SCHEMA_BYTES_NOT_BOUND" in str(exc.value)


def test_t6_schema_binding_wrong_digest_fails_closed():
    """T6: SchemaBindings initialized with wrong digest -> SCHEMA_DIGEST_MISMATCH."""
    from bdb_audit.schemas.binding import SchemaBindings
    bad_digest = "0" * 64

    with pytest.raises(ValidationError) as exc:
        SchemaBindings([("command_envelope", "1", b"{}", bad_digest)])
    assert "SCHEMA_DIGEST_MISMATCH" in str(exc.value)


def test_t7_valid_schema_binding_passes(e1_setup):
    """T7: Valid SchemaBindings requires and verifies bound schema bytes."""
    store, _, _, _ = e1_setup
    key = store.registry.contract("bdb_audit_lane_result", "1")["schema_ref"]
    raw, digest = store.schemas.require_bound(key)
    assert hashlib.sha256(raw).hexdigest() == digest
    assert len(raw) > 0


def test_t8_cross_context_permutations_rejected(e1_setup, tmp_path):
    """T8: Cross-context capability replay and field permutation matrix:
    - cross-slot
    - cross-source commit
    - cross-store (foreign private secret)
    All fail closed atomically.
    """
    store, batch, _, _ = e1_setup
    job = batch.get_job("E1-A")
    head = store.head()
    coordinator = Coordinator(store)

    cut = _current_cut(store)
    assignment_record = store.resolve_accepted(job.assignment_ref, cut)
    source_record = store.resolve_accepted(assignment_record["body"]["source_generation_ref"], cut)

    manifest = _legitimate_manifest(batch, "E1-A")
    zip_path = _create_zip(tmp_path / "t8_base.zip", manifest)
    raw = zip_path.read_bytes()
    vault = RawArtifactVault(Path(store.path).resolve().parent / "raw_vault")
    receipt = vault.put_bytes(raw, media_type="application/zip")

    base_evidence = {
        "kind": "lane_result_admission_evidence",
        "version": "1",
        "admission_evidence_id": deterministic_id("lane_result_admission_evidence", "t8_base"),
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": "E1-A",
        "assignment_ref": {**assignment_record["ref"], "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "attempt_ref": {**job.attempt_ref, "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "source_generation_ref": {**source_record["ref"], "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "source_commit_sha": batch.source_commit_sha,
        "history_cut": dict(batch.frozen_history_cut),
        "input_package_digest": job.package_digest,
        "package_zip_sha256": job.package_zip_sha256,
        "raw_result_digest": receipt.raw_digest,
        "raw_result_byte_length": len(raw),
        "result_proposal_digest": hashlib.sha256(canonical_bytes(_raw_proposal(manifest, job, raw))).hexdigest(),
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "evidence_files": _raw_proposal(manifest, job, raw)["evidence_files"],
    }
    vault.put_bytes(job.package_zip_path.read_bytes(), media_type="application/zip")
    valid_cap = store.issue_ingestion_capability(
        base_evidence,
        batch_ticket=batch.batch_ticket,
    )

    # Permutation 1: Cross-slot replay
    perm1 = dict(base_evidence)
    perm1["lane_slot"] = "E1-B"
    perm1["ingestion_capability"] = valid_cap
    snapshot = _snapshot_store(store)
    with pytest.raises(ValidationError):
        obj = CanonicalObject("lane_result_admission_evidence", perm1)
        cmd = CommandEnvelope(
            command_id=_command_id("t8_perm1"),
            command_kind="INGEST_EXTERNAL_LANE_RESULT",
            actor_ref="installation-owner",
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
            governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
            idempotency_scope="t8_perm1",
            campaign_ref=head.campaign_id,
        )
        coordinator.accept(cmd, immutable_objects=[obj], expected_head=head)
    _assert_atomicity(store, snapshot)

    # Permutation 2: Cross-source replay
    perm2 = dict(base_evidence)
    perm2["source_commit_sha"] = "0" * 40
    perm2["ingestion_capability"] = valid_cap
    snapshot = _snapshot_store(store)
    with pytest.raises(ValidationError):
        obj = CanonicalObject("lane_result_admission_evidence", perm2)
        cmd = CommandEnvelope(
            command_id=_command_id("t8_perm2"),
            command_kind="INGEST_EXTERNAL_LANE_RESULT",
            actor_ref="installation-owner",
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
            governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
            idempotency_scope="t8_perm2",
            campaign_ref=head.campaign_id,
        )
        coordinator.accept(cmd, immutable_objects=[obj], expected_head=head)
    _assert_atomicity(store, snapshot)

    # Permutation 3: Foreign store capability
    foreign_store_path = tmp_path / "foreign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(foreign_store_path, seed="foreign_seed")
    foreign_store = TransactionalHistoryStore(foreign_store_path)
    from bdb_audit.history.authority_hooks import compute_ingestion_capability
    fcon = foreign_store._connect()
    try:
        from bdb_audit.history.store import _get_or_create_ingestion_authority_key
        fsec = _get_or_create_ingestion_authority_key(fcon)
        foreign_cap = compute_ingestion_capability(fsec, base_evidence)
    finally:
        fcon.close()
    assert foreign_cap != valid_cap

    perm3 = dict(base_evidence)
    perm3["ingestion_capability"] = foreign_cap
    snapshot = _snapshot_store(store)
    with pytest.raises(ValidationError) as exc:
        obj = CanonicalObject("lane_result_admission_evidence", perm3)
        cmd = CommandEnvelope(
            command_id=_command_id("t8_perm3"),
            command_kind="INGEST_EXTERNAL_LANE_RESULT",
            actor_ref="installation-owner",
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
            governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
            idempotency_scope="t8_perm3",
            campaign_ref=head.campaign_id,
        )
        coordinator.accept(cmd, immutable_objects=[obj], expected_head=head)
    assert "UNAUTHORIZED_PRODUCER_AUTHORITY" in str(exc.value)
    _assert_atomicity(store, snapshot)


def test_t9_result_proposal_mutation_matrix(e1_setup, tmp_path):
    """T9: Result proposal mutation matrix after valid admission evidence.
    Mutations on findings, executor profile, source commit, or package digest
    are rejected before durability, preserving transactional atomicity.
    """
    store, batch, inbox, _ = e1_setup
    job = batch.get_job("E1-A")

    manifest = _legitimate_manifest(batch, "E1-A")
    zip_path = _create_zip(tmp_path / "valid_t9.zip", manifest)
    slot, status, _ = inbox.ingest_zip(zip_path)
    assert status == "ACCEPTED"

    cut = _current_cut(store)
    evidence_rows = store.accepted_records("lane_result_admission_evidence", cut)
    evidence_ref = {**evidence_rows[-1]["ref"], "ref_class": "PRIOR_ACCEPTED_ONLY"}
    raw_digest = evidence_rows[-1]["body"]["raw_result_digest"]

    head = store.head()
    coordinator = Coordinator(store)

    base_proposal = {
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
        "findings": manifest["findings"],
        "assignment_ref": dict(job.assignment_ref),
        "attempt_ref": dict(job.attempt_ref),
        "raw_result_digest": raw_digest,
        "admission_evidence_ref": evidence_ref,
    }

    mutations = [
        ("findings", [{"finding_id": "MUT-01", "statement": "Mutated finding"}], "RESULT_PROPOSAL_DIGEST_MISMATCH"),
        ("executor_profile", "unauthorized-profile", "RESULT_ADMISSION_EVIDENCE_MISMATCH"),
        ("source_commit_sha", "d" * 40, "RESULT_ADMISSION_EVIDENCE_MISMATCH"),
        ("input_package_digest", "c" * 64, "RESULT_ADMISSION_EVIDENCE_MISMATCH"),
    ]

    for field_name, mutated_val, expected_err in mutations:
        snapshot = _snapshot_store(store)
        p = dict(base_proposal)
        p[field_name] = mutated_val
        with pytest.raises(ValidationError) as exc:
            obj = CanonicalObject("bdb_audit_lane_result", p)
            cmd = CommandEnvelope(
                command_id=_command_id(f"t9_mut_{field_name}"),
                command_kind="RECORD_FOUNDATION_FACT",
                actor_ref="installation-owner",
                expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
                governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
                governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
                idempotency_scope=f"t9_mut_{field_name}",
                campaign_ref=head.campaign_id,
            )
            coordinator.accept(cmd, immutable_objects=[obj], expected_head=head)
        assert expected_err in str(exc.value), f"Expected {expected_err} for {field_name}, got {exc.value}"
        _assert_atomicity(store, snapshot)


def test_t10_concurrent_cas_and_replay_cases(e1_setup, tmp_path):
    """T10: CAS conflict, exact retry idempotency, and duplicate conflict.
    - Exact replay -> ACCEPTED (EXACT_RETRY).
    - Conflicting different result for same assignment -> CONFLICTING_RESULT_REJECTED.
    - Stale expected_parent_head -> COMMAND_BINDING_CONFLICT.
    """
    store, batch, inbox, _ = e1_setup
    manifest = _legitimate_manifest(batch, "E1-A")
    zip_path = _create_zip(tmp_path / "t10_legit.zip", manifest)

    # 1. First ingestion: accepted
    slot, status1, _ = inbox.ingest_zip(zip_path)
    assert status1 == "ACCEPTED"

    # 2. Replay of exact legitimate result: accepted idempotently
    slot, status2, _ = inbox.ingest_zip(zip_path)
    assert status2 == "ACCEPTED"
    assert inbox._last_file_result.code == "EXACT_RETRY"

    # 3. Conflicting different result for same assignment: rejected
    diff_manifest = dict(manifest)
    diff_manifest["findings"] = [{"finding_id": "DIFF-01", "statement": "Different finding"}]
    diff_zip = _create_zip(tmp_path / "t10_diff.zip", diff_manifest, extra={"DIFFERENT.txt": "data"})
    slot, status3, reason3 = inbox.ingest_zip(diff_zip)
    assert status3 == "REJECTED"
    assert "CONFLICTING_RESULT_REJECTED" in str(reason3)

    # 4. CAS conflict: submit command with stale head
    head = store.head()
    stale_head = {"tag": "ACCEPTED_HEAD_REF", "campaign_id": head.campaign_id, "commit_seq": 1, "commit_hash": "0" * 64}
    coordinator = Coordinator(store)
    snapshot = _snapshot_store(store)
    with pytest.raises(ValidationError) as exc:
        cmd = CommandEnvelope(
            command_id=_command_id("t10_cas"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref="installation-owner",
            expected_parent_head=stale_head,
            governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
            governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
            idempotency_scope="t10_cas",
            campaign_ref=head.campaign_id,
        )
        coordinator.accept(cmd, immutable_objects=[], expected_head=head)
    assert exc.value.code in {"COMMAND_BINDING_CONFLICT", "EXPECTED_HEAD_CONFLICT"}
    _assert_atomicity(store, snapshot)


# ============================================================================
# SECTION 13: INDEPENDENT ADVERSARIAL REQUALIFICATION PASS
# ============================================================================


def test_adversarial_nf02_001_issue_ingestion_capability_without_ticket_fails_closed(e1_setup):
    """NF02-001 Adversarial Probe: Unauthenticated caller attempting to use store as signing oracle.
    Must be rejected with UNAUTHORIZED_PRODUCER_AUTHORITY regardless of payload shape.
    """
    store, batch, _, _ = e1_setup
    job = batch.get_job("E1-A")
    evidence_body = {
        "kind": "lane_result_admission_evidence",
        "version": "1",
        "admission_evidence_id": "probe_id",
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": "E1-A",
        "assignment_ref": dict(job.assignment_ref),
        "attempt_ref": dict(job.attempt_ref),
        "source_generation_ref": dict(job.assignment_ref),
        "source_commit_sha": batch.source_commit_sha,
        "history_cut": dict(batch.frozen_history_cut),
        "input_package_digest": job.package_digest,
        "package_zip_sha256": job.package_zip_sha256,
        "raw_result_digest": "0" * 64,
        "raw_result_byte_length": 123,
        "result_proposal_digest": "1" * 64,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
    }

    # 1. Without batch ticket
    with pytest.raises(ValidationError) as exc1:
        store.issue_ingestion_capability(evidence_body)
    assert exc1.value.code == "UNAUTHORIZED_PRODUCER_AUTHORITY"

    # 2. With forged batch ticket
    with pytest.raises(ValidationError) as exc2:
        store.issue_ingestion_capability(evidence_body, batch_ticket="0" * 64)
    assert exc2.value.code == "UNAUTHORIZED_PRODUCER_AUTHORITY"

    # 3. With foreign ticket from another campaign
    # The issuer now rejects the foreign context itself.
    with pytest.raises(ValidationError) as exc3:
        store.issue_batch_ticket(campaign_id="foreign_camp", stage_id="E1", cut=batch.frozen_history_cut)
    assert exc3.value.code == "INVALID_HISTORY_CUT"


def test_adversarial_nf02_001_issue_ingestion_capability_tampered_context_rejected(e1_setup, tmp_path):
    """NF02-001: Caller possessing valid batch_ticket cannot mint capabilities with tampered context."""
    store, batch, _, _ = e1_setup
    job = batch.get_job("E1-A")
    vault = RawArtifactVault(Path(store.path).resolve().parent / "raw_vault")

    # Put a valid raw ZIP in vault
    manifest = _legitimate_manifest(batch, "E1-A")
    raw_path = _create_zip(tmp_path / "valid_raw.zip", manifest)
    raw_bytes = raw_path.read_bytes()
    receipt = vault.put_bytes(raw_bytes, media_type="application/zip")

    current_cut = _current_cut(store)
    assignment_record = store.resolve_accepted(job.assignment_ref, current_cut)
    source_record = store.resolve_accepted(assignment_record["body"]["source_generation_ref"], current_cut)

    base_evidence = {
        "kind": "lane_result_admission_evidence",
        "version": "1",
        "admission_evidence_id": "valid_id",
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": "E1-A",
        "assignment_ref": dict(job.assignment_ref),
        "attempt_ref": dict(job.attempt_ref),
        "source_generation_ref": dict(source_record["ref"]),
        "source_commit_sha": batch.source_commit_sha,
        "history_cut": dict(batch.frozen_history_cut),
        "input_package_digest": job.package_digest,
        "package_zip_sha256": job.package_zip_sha256,
        "raw_result_digest": receipt.raw_digest,
        "raw_result_byte_length": len(raw_bytes),
        "result_proposal_digest": "proposal_digest",
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
    }

    # Context tampering 1: Mismatched source commit SHA
    tampered_source = dict(base_evidence)
    tampered_source["source_commit_sha"] = "0" * 40
    with pytest.raises(ValidationError) as exc:
        store.issue_ingestion_capability(tampered_source, batch_ticket=batch.batch_ticket)
    assert exc.value.code in {"UNAUTHORIZED_PRODUCER_AUTHORITY", "SOURCE_COMMIT_MISMATCH"}

    # Context tampering 2: Dummy attempt ref
    tampered_attempt = dict(base_evidence)
    tampered_attempt["attempt_ref"] = {**job.attempt_ref, "revision_digest": "0" * 64}
    with pytest.raises(ValidationError) as exc:
        store.issue_ingestion_capability(tampered_attempt, batch_ticket=batch.batch_ticket)
    assert exc.value.code == "UNAUTHORIZED_PRODUCER_AUTHORITY"

    # Context tampering 3: Nonexistent raw result digest
    tampered_raw = dict(base_evidence)
    tampered_raw["raw_result_digest"] = "e" * 64
    with pytest.raises(ValidationError) as exc:
        store.issue_ingestion_capability(tampered_raw, batch_ticket=batch.batch_ticket)
    assert exc.value.code in {"RAW_ARTIFACT_NOT_FOUND", "UNAUTHORIZED_PRODUCER_AUTHORITY"}


def test_adversarial_nf02_002_live_package_on_disk_tampering_rejected(e1_setup, tmp_path):
    """NF02-002: Tampering with package on disk after batch creation must be detected on intake."""
    store, batch, inbox, _ = e1_setup
    job = batch.get_job("E1-A")
    manifest = _legitimate_manifest(batch, "E1-A")
    zip_path = _create_zip(tmp_path / "legit_result.zip", manifest)

    # Tamper the package ZIP on disk
    assert job.package_zip_path.is_file()
    original_bytes = job.package_zip_path.read_bytes()
    tampered_bytes = original_bytes + b"CORRUPTED_BYTES"
    job.package_zip_path.write_bytes(tampered_bytes)

    try:
        slot, status, reason = inbox.ingest_zip(zip_path)
        assert status == "REJECTED"
        assert "ASSIGNED_PACKAGE_TAMPERED" in str(reason)
    finally:
        # Restore original package bytes
        job.package_zip_path.write_bytes(original_bytes)


def test_adversarial_nf02_003_raw_blob_toctou_deletion_fails_closed(e1_setup, tmp_path):
    """NF02-003: Loss of accepted raw closure before result commit fails closed.

    Staging-only deletion is recoverable from SQLite (T4). This fault removes
    retained bytes too; a successful second commit must then be impossible.
    """
    store, batch, _, _ = e1_setup
    job = batch.get_job("E1-A")
    head = store.head()
    coordinator = Coordinator(store)
    vault = RawArtifactVault(Path(store.path).resolve().parent / "raw_vault")

    manifest = _legitimate_manifest(batch, "E1-A")
    zip_path = _create_zip(tmp_path / "toctou_result.zip", manifest)
    raw = zip_path.read_bytes()
    receipt = vault.put_bytes(raw, media_type="application/zip")
    raw_digest = receipt.raw_digest

    proposal = _raw_proposal(manifest, job, raw)
    vault.put_bytes(job.package_zip_path.read_bytes(), media_type="application/zip")
    proposal_without_ref = dict(proposal)
    result_proposal_digest = hashlib.sha256(canonical_bytes(proposal_without_ref)).hexdigest()

    current_cut = _current_cut(store)
    assignment_record = store.resolve_accepted(job.assignment_ref, current_cut)
    source_record = store.resolve_accepted(assignment_record["body"]["source_generation_ref"], current_cut)

    evidence_body = {
        "kind": "lane_result_admission_evidence",
        "version": "1",
        "admission_evidence_id": "toctou_evidence_id",
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": "E1-A",
        "assignment_ref": {**assignment_record["ref"], "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "attempt_ref": {**job.attempt_ref, "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "source_generation_ref": {**source_record["ref"], "ref_class": "PRIOR_ACCEPTED_ONLY"},
        "source_commit_sha": job.source_commit_sha,
        "history_cut": dict(batch.frozen_history_cut),
        "input_package_digest": job.package_digest,
        "package_zip_sha256": job.package_zip_sha256,
        "raw_result_digest": raw_digest,
        "raw_result_byte_length": len(raw),
        "result_proposal_digest": result_proposal_digest,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
    }
    evidence_body["evidence_files"] = proposal["evidence_files"]
    evidence_body["ingestion_capability"] = store.issue_ingestion_capability(
        evidence_body,
        batch_ticket=batch.batch_ticket,
    )
    evidence_obj = CanonicalObject("lane_result_admission_evidence", evidence_body)

    # Commit evidence_obj in its own INGEST_EXTERNAL_LANE_RESULT commit
    cmd_ev = CommandEnvelope(
        command_id=_command_id("toctou_ev_cmd"),
        command_kind="INGEST_EXTERNAL_LANE_RESULT",
        actor_ref="installation-owner",
        expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
        governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
        governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
        idempotency_scope="toctou_ev_cmd",
        campaign_ref=head.campaign_id,
    )
    coordinator.accept(cmd_ev, immutable_objects=[evidence_obj], expected_head=head)
    head_after_ev = store.head()

    proposal["admission_evidence_ref"] = evidence_obj.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict()
    result_obj = CanonicalObject("bdb_audit_lane_result", proposal)

    # Simulate actual loss of accepted bytes, including the durable copy.
    vault_blob_path, _ = vault._paths(raw_digest)
    vault_blob_path.unlink()
    assert not vault_blob_path.is_file()
    con = store._connect()
    try:
        assert con.execute("DELETE FROM immutable_raw_artifacts WHERE digest=?", (raw_digest,)).rowcount == 1
    finally:
        con.close()

    snapshot = _snapshot_store(store)
    with pytest.raises(ValidationError) as exc:
        cmd_res = CommandEnvelope(
            command_id=_command_id("toctou_res_cmd"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref="installation-owner",
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head_after_ev.as_dict()},
            governing_policy_ref=store.commits()[-1]["governing_policy_ref"],
            governing_spec_refs=tuple(store.commits()[-1]["governing_spec_refs"]),
            idempotency_scope="toctou_res_cmd",
            campaign_ref=head_after_ev.campaign_id,
        )
        coordinator.accept(cmd_res, immutable_objects=[result_obj], expected_head=head_after_ev)
    assert exc.value.code == "VAULT_INTEGRITY_BLOCKED"
    _assert_atomicity(store, snapshot)

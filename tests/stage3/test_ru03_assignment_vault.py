from __future__ import annotations

from pathlib import Path

import pytest

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS
from bdb_audit.vault.raw_store import RawArtifactVault
from bdb_audit.workflow.assignments import AssignmentService


def _campaign(tmp_path: Path) -> TransactionalHistoryStore:
    db = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(db, seed="ru03-assignment-fixture")
    api.prepare_stage(db, "E1")
    for slot in E1_LANE_SLOTS:
        api.prepare_lane(db, "E1", slot=slot)
    return TransactionalHistoryStore(db)


def test_raw_vault_round_trip_and_exact_retry(tmp_path: Path) -> None:
    vault = RawArtifactVault(tmp_path / "vault")
    raw = b"exact result zip bytes\x00\x01"
    first = vault.put_bytes(raw, media_type="application/zip")
    second = vault.put_bytes(raw, media_type="application/zip")
    assert first.raw_digest == second.raw_digest
    assert second.already_present is True
    assert vault.read_bytes(first.raw_digest) == raw
    assert first.blob_path.name != "result.zip"


def test_raw_vault_detects_corruption(tmp_path: Path) -> None:
    vault = RawArtifactVault(tmp_path / "vault")
    receipt = vault.put_bytes(b"original")
    receipt.blob_path.write_bytes(b"tampered")
    with pytest.raises(ValidationError) as exc_info:
        vault.read_bytes(receipt.raw_digest)
    assert exc_info.value.code == "RAW_VAULT_READBACK_FAILED"


def test_assignments_are_accepted_before_delivery_and_resume_exactly(tmp_path: Path) -> None:
    store = _campaign(tmp_path)
    service = AssignmentService(store)
    before = store.head()
    prepared = service.prepare_e1_assignments(executor_profile="ChatGPT / GitHub", model="Sol 5.6")
    after = store.head()
    assert after.commit_seq == before.commit_seq + 1
    assert set(prepared.assignments) == set(E1_LANE_SLOTS)
    assert all(a.assignment_input_history_cut == prepared.assignment_input_history_cut for a in prepared.assignments.values())

    records = store.accepted_records("assignment_manifest", prepared.accepted_history_cut)
    assert len(records) == len(E1_LANE_SLOTS)
    isolations = store.accepted_records("isolation_qualification", prepared.accepted_history_cut)
    e1_isolations = [r for r in isolations if r["body"].get("scope") == "MANUAL_EXTERNAL_SESSION"]
    assert len(e1_isolations) == len(E1_LANE_SLOTS)
    assert all(r["body"]["result"] == "DECLARED" for r in e1_isolations)
    assert all(r["body"]["enforcement_receipt_refs"] == [] for r in e1_isolations)

    # A restart/resume at the later head reuses accepted AssignmentManifest facts;
    # it must not create a new attempt or shift the assignment input cut.
    resumed_store = TransactionalHistoryStore(store.path)
    resumed = AssignmentService(resumed_store).prepare_e1_assignments(
        executor_profile="ChatGPT / GitHub", model="Sol 5.6"
    )
    assert resumed.assignment_input_history_cut == prepared.assignment_input_history_cut
    for slot in E1_LANE_SLOTS:
        original = prepared.assignments[slot]
        restored = resumed.assignments[slot]
        assert restored.assignment_ref == original.assignment_ref
        assert restored.attempt_ref == original.attempt_ref
        assert restored.knowledge_state_ref == original.knowledge_state_ref
        assert restored.isolation_qualification_ref == original.isolation_qualification_ref
    assert resumed_store.head().commit_hash == after.commit_hash

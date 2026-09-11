"""Targeted tests for PR-E4-06 / M33: Crash / Recovery Engine."""
import sqlite3
import pytest
from bdb_audit.core.errors import ValidationError
from bdb_audit.evidence.models import Observation
from bdb_audit.deepen.crash import (
    CrashPoint,
    RecoveryInvariant,
    DurableStoreHarness,
    CrashRecoveryEngine,
)


def test_crash_before_durable_acceptance(tmp_path):
    db_file = str(tmp_path / "test_crash_before.sqlite")
    harness = DurableStoreHarness(db_file)
    engine = CrashRecoveryEngine()

    cp = CrashPoint(
        point_id="cp_01",
        boundary="BEFORE_DURABLE_ACCEPTANCE",
        operation_id="op_rec_01",
    )

    res = engine.run_crash_test(harness, "rec_01", "payload_data_01", cp)

    assert res.recovery_status == "RECOVERED_ROLLEDBACK"
    assert res.accepted_before_crash is False
    assert res.retry_successful is True
    assert res.idempotent_result["already_accepted"] is False


def test_crash_during_boundary_partial_write(tmp_path):
    db_file = str(tmp_path / "test_crash_during.sqlite")
    harness = DurableStoreHarness(db_file)
    engine = CrashRecoveryEngine()

    cp = CrashPoint(
        point_id="cp_02",
        boundary="DURING_BOUNDARY",
        operation_id="op_rec_02",
    )

    res = engine.run_crash_test(harness, "rec_02", "payload_data_02", cp)

    # Partial write in uncommitted transaction was rolled back by WAL
    assert res.recovery_status == "RECOVERED_ROLLEDBACK"
    assert res.accepted_before_crash is False
    assert res.retry_successful is True
    assert len(res.invariants_failed) == 0


def test_crash_after_durable_acceptance_idempotent_retry(tmp_path):
    db_file = str(tmp_path / "test_crash_after.sqlite")
    harness = DurableStoreHarness(db_file)
    engine = CrashRecoveryEngine()

    cp = CrashPoint(
        point_id="cp_03",
        boundary="AFTER_DURABLE_ACCEPTANCE",
        operation_id="op_rec_03",
    )

    res = engine.run_crash_test(harness, "rec_03", "payload_data_03", cp)

    assert res.recovery_status == "RECOVERED_CLEAN"
    assert res.accepted_before_crash is True
    assert res.retry_successful is True
    # Idempotent retry returns already_accepted=True without double-insert
    assert res.idempotent_result["already_accepted"] is True


def test_duplicate_retry_idempotent(tmp_path):
    db_file = str(tmp_path / "test_dup_retry.sqlite")
    harness = DurableStoreHarness(db_file)

    # Normal first accept
    res1 = harness.accept_record("rec_dup", "hello_world")
    assert res1["already_accepted"] is False

    # Second retry
    res2 = harness.accept_record("rec_dup", "hello_world")
    assert res2["already_accepted"] is True
    assert res2["payload_hash"] == res1["payload_hash"]


def test_conflicting_retry_fails_closed(tmp_path):
    db_file = str(tmp_path / "test_conflict_retry.sqlite")
    harness = DurableStoreHarness(db_file)

    # First accept
    harness.accept_record("rec_c", "original_payload")

    # Mismatched retry
    with pytest.raises(ValidationError) as exc:
        harness.accept_record("rec_c", "DIFFERENT_PAYLOAD")
    assert "CONFLICTING_RETRY" in str(exc.value)


def test_corruption_triggers_recovery_invariant_failure(tmp_path):
    db_file = str(tmp_path / "test_corrupt.sqlite")
    harness = DurableStoreHarness(db_file)
    engine = CrashRecoveryEngine()

    # Create a valid record first
    harness.accept_record("rec_valid", "payload_123")

    # Artificially corrupt payload_hash in the database directly
    con = sqlite3.connect(db_file)
    con.execute("UPDATE durable_records SET payload_hash = 'corrupted_hash' WHERE record_id = 'rec_valid'")
    con.commit()
    con.close()

    cp = CrashPoint(
        point_id="cp_check",
        boundary="BEFORE_DURABLE_ACCEPTANCE",
        operation_id="op_check",
    )

    res = engine.run_crash_test(harness, "rec_check", "new_payload", cp)
    assert res.recovery_status == "INVARIANT_FAILED"
    assert any("NO_TORN_RECORD" in f for f in res.invariants_failed)


def test_crash_recovery_observation_conversion(tmp_path):
    db_file = str(tmp_path / "test_obs.sqlite")
    harness = DurableStoreHarness(db_file)
    engine = CrashRecoveryEngine()

    cp = CrashPoint(
        point_id="cp_obs",
        boundary="AFTER_DURABLE_ACCEPTANCE",
        operation_id="op_obs",
    )
    res = engine.run_crash_test(harness, "rec_obs", "payload_obs", cp)

    obs = engine.to_observation(res)
    assert isinstance(obs, Observation)
    assert obs.observation_channel == "CRASH_RECOVERY_ENGINE"
    assert obs.raw_observation_ref["recovery_status"] == "RECOVERED_CLEAN"
    # No finding shortcut
    assert not hasattr(obs, "finding_id")
    assert not hasattr(obs, "lifecycle_status")

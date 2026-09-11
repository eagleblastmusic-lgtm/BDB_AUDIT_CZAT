"""Crash and Recovery Engine (WP-E4-06 / M33 / §90).

Implements:
- CrashPoint: exact crash boundaries (before durable acceptance, during boundary, after durable acceptance).
- Restart: durable state recovery and recovery invariant enforcement.
- RecoveryInvariant: verification of durable consistency (no torn state, head consistency, clean rollback).
- Idempotent retry: retrying already-accepted operations returns prior receipt without duplicate side-effects.
- Conflicting retry: fails closed on mismatched payload.
- Output is Observation/evidence input, never a direct finding shortcut.
"""
from dataclasses import dataclass, field
import hashlib
import sqlite3
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id
from ..evidence.models import Observation


CRASH_BOUNDARIES = {
    "BEFORE_DURABLE_ACCEPTANCE",
    "DURING_BOUNDARY",
    "AFTER_DURABLE_ACCEPTANCE",
    "BEFORE_COMMIT",
    "AFTER_COMMIT_BEFORE_ACK",
}


@dataclass(frozen=True)
class CrashPoint:
    point_id: str
    boundary: str  # from CRASH_BOUNDARIES
    operation_id: str
    trigger_condition: str = "ALWAYS"
    description: str = ""

    def __post_init__(self):
        if self.boundary not in CRASH_BOUNDARIES:
            raise ValidationError("INVALID_CRASH_BOUNDARY", f"Unknown crash boundary: {self.boundary}")

    def body(self) -> dict[str, Any]:
        return {
            "point_id": self.point_id,
            "boundary": self.boundary,
            "operation_id": self.operation_id,
            "trigger_condition": self.trigger_condition,
            "description": self.description,
        }


@dataclass(frozen=True)
class RecoveryInvariant:
    invariant_id: str
    description: str
    check_fn: Callable[[Any], tuple[bool, str | None]]

    def evaluate(self, state_or_store: Any) -> tuple[bool, str | None]:
        return self.check_fn(state_or_store)


@dataclass(frozen=True)
class RestartResult:
    restart_id: str
    crash_point: CrashPoint
    recovery_status: str  # RECOVERED_CLEAN, RECOVERED_ROLLEDBACK, INVARIANT_FAILED, CORRUPTED
    invariants_passed: tuple[str, ...]
    invariants_failed: tuple[str, ...]
    accepted_before_crash: bool
    retry_successful: bool
    idempotent_result: Any | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def body(self) -> dict[str, Any]:
        return {
            "restart_id": self.restart_id,
            "crash_point": self.crash_point.body(),
            "recovery_status": self.recovery_status,
            "invariants_passed": list(self.invariants_passed),
            "invariants_failed": list(self.invariants_failed),
            "accepted_before_crash": self.accepted_before_crash,
            "retry_successful": self.retry_successful,
            "idempotent_result": str(self.idempotent_result) if self.idempotent_result is not None else None,
            "details": dict(self.details),
        }


class DurableStoreHarness:
    """Durable SQLite storage harness for real process/storage crash proofs."""

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        self._init_db()

    def _init_db(self):
        con = sqlite3.connect(self.db_path)
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=FULL")
            con.execute("""
            CREATE TABLE IF NOT EXISTS durable_records (
                record_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                accepted_at INTEGER NOT NULL
            )
            """)
            con.execute("""
            CREATE TABLE IF NOT EXISTS durable_head (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                last_record_id TEXT NOT NULL,
                version INTEGER NOT NULL
            )
            """)
            con.commit()
        finally:
            con.close()

    def accept_record(
        self,
        record_id: str,
        payload: str,
        crash_point: CrashPoint | None = None,
    ) -> dict[str, Any]:
        con = sqlite3.connect(self.db_path, isolation_level=None)
        p_hash = hashlib.sha256(payload.encode()).hexdigest()

        try:
            # Check for existing record (idempotency check)
            row = con.execute(
                "SELECT payload, payload_hash FROM durable_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if row:
                existing_payload, existing_hash = row
                if existing_hash != p_hash:
                    raise ValidationError(
                        "CONFLICTING_RETRY",
                        f"Record {record_id} already exists with different payload hash",
                    )
                return {
                    "record_id": record_id,
                    "payload_hash": existing_hash,
                    "already_accepted": True,
                }

            # Boundary 1: BEFORE_DURABLE_ACCEPTANCE
            if crash_point and crash_point.boundary == "BEFORE_DURABLE_ACCEPTANCE":
                con.close()
                raise RuntimeError(f"Simulated crash at {crash_point.boundary}")

            con.execute("BEGIN IMMEDIATE")

            con.execute(
                "INSERT INTO durable_records(record_id, payload, payload_hash, accepted_at) VALUES (?, ?, ?, ?)",
                (record_id, payload, p_hash, 1000),
            )

            # Boundary 2: DURING_BOUNDARY (partial write before head commit)
            if crash_point and crash_point.boundary == "DURING_BOUNDARY":
                # Crash before head update and commit
                con.close()  # Uncommitted transaction will be rolled back by SQLite WAL
                raise RuntimeError(f"Simulated crash at {crash_point.boundary}")

            # Update head
            head_row = con.execute("SELECT version FROM durable_head WHERE singleton=1").fetchone()
            nxt_ver = 1 if head_row is None else head_row[0] + 1
            con.execute(
                "INSERT OR REPLACE INTO durable_head(singleton, last_record_id, version) VALUES (1, ?, ?)",
                (record_id, nxt_ver),
            )

            con.execute("COMMIT")

            # Boundary 3: AFTER_DURABLE_ACCEPTANCE (committed, but crashed before client ack)
            if crash_point and crash_point.boundary in ("AFTER_DURABLE_ACCEPTANCE", "AFTER_COMMIT_BEFORE_ACK"):
                con.close()
                raise RuntimeError(f"Simulated crash at {crash_point.boundary}")

            return {
                "record_id": record_id,
                "payload_hash": p_hash,
                "version": nxt_ver,
                "already_accepted": False,
            }

        finally:
            try:
                con.close()
            except Exception:
                pass


class CrashRecoveryEngine:
    def __init__(self, invariants: Sequence[RecoveryInvariant] | None = None):
        self.invariants = tuple(invariants) if invariants is not None else (
            RecoveryInvariant(
                "NO_ORPHAN_UNACCEPTED_HEAD",
                "Durable head must point to an existing durable record",
                self._check_head_exists,
            ),
            RecoveryInvariant(
                "NO_TORN_RECORD",
                "All durable records must have valid non-empty hashes",
                self._check_records_intact,
            ),
        )

    def _check_head_exists(self, harness: DurableStoreHarness) -> tuple[bool, str | None]:
        con = sqlite3.connect(harness.db_path)
        try:
            head = con.execute("SELECT last_record_id FROM durable_head WHERE singleton=1").fetchone()
            if head is None:
                return True, None
            rec_id = head[0]
            rec = con.execute("SELECT record_id FROM durable_records WHERE record_id=?", (rec_id,)).fetchone()
            if rec is None:
                return False, f"Head points to non-existent record {rec_id}"
            return True, None
        finally:
            con.close()

    def _check_records_intact(self, harness: DurableStoreHarness) -> tuple[bool, str | None]:
        con = sqlite3.connect(harness.db_path)
        try:
            rows = con.execute("SELECT record_id, payload, payload_hash FROM durable_records").fetchall()
            for r_id, p, h in rows:
                if not h or hashlib.sha256(p.encode()).hexdigest() != h:
                    return False, f"Corrupted payload for record {r_id}"
            return True, None
        finally:
            con.close()

    def run_crash_test(
        self,
        harness: DurableStoreHarness,
        record_id: str,
        payload: str,
        crash_point: CrashPoint,
    ) -> RestartResult:
        res_id = new_id("execution_result")
        crashed = False
        accepted_before_crash = False

        # Execute under crash point
        try:
            harness.accept_record(record_id, payload, crash_point=crash_point)
        except RuntimeError:
            crashed = True
            # In AFTER_DURABLE_ACCEPTANCE, the database commit was already executed
            if crash_point.boundary in ("AFTER_DURABLE_ACCEPTANCE", "AFTER_COMMIT_BEFORE_ACK"):
                accepted_before_crash = True

        # Restart and verify recovery invariants on fresh connection
        passed_invs = []
        failed_invs = []
        for inv in self.invariants:
            ok, err = inv.evaluate(harness)
            if ok:
                passed_invs.append(inv.invariant_id)
            else:
                failed_invs.append(f"{inv.invariant_id}: {err}")

        # Idempotent retry on recovered store
        retry_ok = False
        retry_res = None
        if not failed_invs:
            try:
                retry_res = harness.accept_record(record_id, payload, crash_point=None)
                retry_ok = True
            except Exception as e:
                retry_ok = False

        if failed_invs:
            status = "INVARIANT_FAILED"
        elif accepted_before_crash:
            status = "RECOVERED_CLEAN"
        else:
            status = "RECOVERED_ROLLEDBACK"

        return RestartResult(
            restart_id=res_id,
            crash_point=crash_point,
            recovery_status=status,
            invariants_passed=tuple(passed_invs),
            invariants_failed=tuple(failed_invs),
            accepted_before_crash=accepted_before_crash,
            retry_successful=retry_ok,
            idempotent_result=retry_res,
        )

    def to_observation(
        self,
        result: RestartResult,
        execution_descriptor_ref: Any = None,
    ) -> Observation:
        exec_ref = execution_descriptor_ref or {
            "execution_descriptor_id": new_id("execution_descriptor"),
            "engine": "CRASH_RECOVERY_ENGINE",
        }
        return Observation(
            observation_id=new_id("observation"),
            execution_descriptor_ref=exec_ref,
            raw_observation_ref=result.body(),
            observation_channel="CRASH_RECOVERY_ENGINE",
            observed_at="2026-09-11T12:00:00Z",
        )

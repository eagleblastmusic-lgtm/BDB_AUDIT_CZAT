from pathlib import Path
import sqlite3

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.core.registry import load_vectors
from bdb_audit.history.closure import canonical_order
from bdb_audit.history.store import TransactionalHistoryStore
from .helpers import bootstrap_fixture

ROOT = Path(__file__).resolve().parents[2]


def history_path(name):
    # The managed Windows host denies ACL operations in its Temp tree; these
    # ignored repo-local databases still exercise the durable SQLite profile.
    return ROOT / name


def fresh(path):
    if path.exists():
        con = sqlite3.connect(path)
        con.executescript("DROP TABLE IF EXISTS immutable_objects; DROP TABLE IF EXISTS commits; DROP TABLE IF EXISTS receipts; DROP TABLE IF EXISTS accepted_head; DROP TABLE IF EXISTS command_index;")
        con.close()
    return path


def test_r5n80_union_precedence_vectors():
    vectors = {v["id"]: v for v in load_vectors()["vectors"]}
    accepted = vectors["R5N80_BOOTSTRAP_ORDER_ONLY_PRECEDENCE_ACCEPT"]
    data = accepted["input"]
    assert canonical_order(data["nodes"], command_kind=data["scope"]["command_kind"],
                           commit_seq=data["scope"]["commit_seq"],
                           expected_parent=data["scope"]["expected_parent"],
                           profile_name=data["order_only_precedence_profile"]) == accepted["expected"]["canonical_order"]
    ordinary = vectors["R5N80_BOOTSTRAP_PRECEDENCE_NOT_GLOBAL"]
    data = ordinary["input"]
    assert canonical_order(data["nodes"], command_kind=data["scope"]["command_kind"],
                           commit_seq=data["scope"]["commit_seq"],
                           expected_parent=data["scope"]["expected_parent"]) == ordinary["expected"]["canonical_order"]
    cycle = vectors["R5N80_BOOTSTRAP_PRECEDENCE_CYCLE_REJECT"]
    data = cycle["input"]
    with pytest.raises(ValidationError, match=cycle["expected"]["error"]):
        canonical_order(data["nodes"], command_kind=data["scope"]["command_kind"],
                        commit_seq=data["scope"]["commit_seq"],
                        expected_parent=data["scope"]["expected_parent"],
                        profile_name=data["order_only_precedence_profile"])


def test_bootstrap_accepts_one_head_and_retry():
    profile, command, objects, _ = bootstrap_fixture()
    store = TransactionalHistoryStore(fresh(history_path("F2_GATE_TEST.sqlite")))
    result = store.accept(command, immutable_objects=objects, bootstrap_profile=profile)
    assert result.head.commit_seq == 1
    assert store.head() == result.head
    retry = store.accept(command, immutable_objects=objects, bootstrap_profile=profile)
    assert retry.already_accepted
    assert retry.receipt.digest == result.receipt.digest
    assert len(store.commits()) == 1
    assert store.rebuild_projection() == store.rebuild_projection()


def test_empty_history_after_seq1_and_blocked_admission_rejected():
    profile, command, objects, parts = bootstrap_fixture()
    store = TransactionalHistoryStore(fresh(history_path("F2_EMPTY_HISTORY_TEST.sqlite")))
    result = store.accept(command, immutable_objects=objects, bootstrap_profile=profile)
    from dataclasses import replace
    command2 = replace(command, command_id="command_223e4567-e89b-42d3-a456-426614174000")
    with pytest.raises(ValidationError, match="EMPTY_HISTORY_AFTER_INITIALIZATION"):
        store.accept(command2, expected_head={"tag": "EMPTY_HISTORY"}, immutable_objects=objects,
                     bootstrap_profile=profile)
    blocked = dict(parts["admission"].body, result="BLOCKED_CANONICAL_ADMISSION")
    from bdb_audit.history.objects import CanonicalObject
    blocked_obj = CanonicalObject("bootstrap_admission_decision", blocked)
    bad = tuple(blocked_obj if obj.digest == parts["admission"].digest else obj for obj in objects)
    store = TransactionalHistoryStore(fresh(history_path("F2_BLOCKED_TEST.sqlite")))
    with pytest.raises(ValidationError, match="BLOCKED_ADMISSION_CANNOT_EMIT_GENESIS"):
        store.accept(command, immutable_objects=bad, bootstrap_profile=profile)

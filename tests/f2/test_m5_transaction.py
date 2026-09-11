from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.history.store import InjectedCrash, TransactionalHistoryStore
from .helpers import bootstrap_fixture

ROOT = Path(__file__).resolve().parents[2]


def fresh(path):
    if path.exists():
        con = sqlite3.connect(path)
        con.executescript("DROP TABLE IF EXISTS immutable_objects; DROP TABLE IF EXISTS commits; DROP TABLE IF EXISTS receipts; DROP TABLE IF EXISTS accepted_head; DROP TABLE IF EXISTS command_index;")
        con.close()
    return path


@pytest.mark.parametrize("hook", TransactionalHistoryStore.HOOKS)
def test_each_persistence_boundary_recovers_old_or_new(hook):
    profile, command, objects, _ = bootstrap_fixture()
    path = fresh(ROOT / ("F2_CRASH_" + hook + ".sqlite"))
    store = TransactionalHistoryStore(path, crash_hook=lambda name: name == hook)
    with pytest.raises(InjectedCrash):
        store.accept(command, immutable_objects=objects, bootstrap_profile=profile)
    if hook == "after_commit_durability_before_ack":
        assert store.head().commit_seq == 1
        assert len(store.commits()) == 1
        assert store.receipt(command.command_id) is not None
    else:
        assert store.head() is None
        assert store.commits() == []
        assert store.receipt(command.command_id) is None
    recovered = TransactionalHistoryStore(path)
    result = recovered.accept(command, immutable_objects=objects, bootstrap_profile=profile)
    assert result.head.commit_seq == 1
    assert recovered.receipt(command.command_id).digest == result.receipt.digest


def test_expected_head_compare_and_id_reuse_conflict():
    profile, command, objects, _ = bootstrap_fixture()
    path = fresh(ROOT / "F2_CONCURRENCY_TEST.sqlite")
    store = TransactionalHistoryStore(path)
    first = store.accept(command, immutable_objects=objects, bootstrap_profile=profile)
    expected = {"tag": "ACCEPTED_HEAD_REF", **first.head.as_dict()}
    follow = replace(command, command_id="command_323e4567-e89b-42d3-a456-426614174000",
                     command_kind="RECORD_FOUNDATION_FACT", campaign_ref="campaign_fixture",
                     expected_parent_head=expected, proposed_campaign_id=None,
                     history_namespace_ref=None, bootstrap_profile_ref=None)
    second = store.accept(follow, expected_head=first.head)
    assert second.head.commit_seq == 2
    stale = replace(command, command_id="command_423e4567-e89b-42d3-a456-426614174000",
                    command_kind="RECORD_FOUNDATION_FACT", campaign_ref="campaign_fixture",
                    expected_parent_head=expected, proposed_campaign_id=None,
                    history_namespace_ref=None, bootstrap_profile_ref=None)
    with pytest.raises(ValidationError, match="EXPECTED_HEAD_CONFLICT"):
        store.accept(stale, expected_head=first.head)
    reused = replace(follow, command_payload={"different": True})
    with pytest.raises(ValidationError, match="ID_REUSE_CONFLICT"):
        store.accept(reused, expected_head=second.head)

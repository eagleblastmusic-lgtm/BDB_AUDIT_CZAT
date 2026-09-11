import subprocess
import sys
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.history.store import TransactionalHistoryStore
from .helpers import bootstrap_fixture
from .test_m5_transaction import fresh, ROOT


@pytest.mark.parametrize("boundary", TransactionalHistoryStore.HOOKS)
def test_process_death_is_old_or_new_complete(boundary):
    path = fresh(ROOT / ("F2_PROCESS_" + boundary + ".sqlite"))
    run = subprocess.run([sys.executable, "-B", str(ROOT / "tests/f2/crash_worker.py"), str(path), boundary], capture_output=True, text=True)
    assert run.returncode == 73, run.stderr
    profile, command, objects, _ = bootstrap_fixture()
    recovered = TransactionalHistoryStore(path)
    expected_new = boundary == "after_commit_durability_before_ack"
    assert bool(recovered.head()) == expected_new
    assert bool(recovered.receipt(command.command_id)) == expected_new
    with sqlite3.connect(path) as con:
        counts = [con.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                  for table in ("immutable_objects", "commits", "receipts", "accepted_head", "command_index")]
    assert all(count > 0 for count in counts) if expected_new else counts == [0] * 5
    result = recovered.accept(command, immutable_objects=objects, bootstrap_profile=profile)
    assert result.already_accepted == expected_new
    assert len(recovered.commits()) == 1


def test_real_concurrent_expected_head_conflict():
    path = fresh(ROOT / "F2_REAL_CONCURRENCY.sqlite")
    profile, command, objects, _ = bootstrap_fixture()
    first = TransactionalHistoryStore(path).accept(command, immutable_objects=objects, bootstrap_profile=profile)
    stores = [TransactionalHistoryStore(path), TransactionalHistoryStore(path)]
    barrier = Barrier(2)
    def submit(i):
        candidate = replace(command, command_id=f"command_{i + 5}23e4567-e89b-42d3-a456-426614174000",
                            command_kind="RECORD_FOUNDATION_FACT", campaign_ref=first.head.campaign_id,
                            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **first.head.as_dict()},
                            proposed_campaign_id=None, history_namespace_ref=None, bootstrap_profile_ref=None)
        barrier.wait()
        try:
            return stores[i].accept(candidate, expected_head=first.head).head.commit_seq
        except ValidationError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, (0, 1)))
    assert sorted(map(str, results)) == ["2", "EXPECTED_HEAD_CONFLICT"]
    assert len(stores[0].commits()) == 2

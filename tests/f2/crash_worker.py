"""Actual process-death worker: no exception rollback or finally cleanup."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from tests.f2.helpers import bootstrap_fixture
from bdb_audit.history.store import TransactionalHistoryStore

path, boundary = sys.argv[1:]
profile, command, objects, _ = bootstrap_fixture()


def crash(name):
    if name == boundary:
        os._exit(73)


TransactionalHistoryStore(path, crash_hook=crash).accept(
    command, immutable_objects=objects, bootstrap_profile=profile)
raise SystemExit("Boundary not reached")

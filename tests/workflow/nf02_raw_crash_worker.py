"""NF02 fault worker: terminate the process without rollback/finally cleanup."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from bdb_audit.history.objects import CanonicalObject, CommandEnvelope
from bdb_audit.history.store import TransactionalHistoryStore

path, packet_path, boundary = sys.argv[1:]
packet = json.loads(Path(packet_path).read_bytes())
command = CommandEnvelope(**packet["command"])
obj = CanonicalObject(**packet["object"])


def crash(name):
    if name == boundary:
        os._exit(73)


TransactionalHistoryStore(path, crash_hook=crash).accept(
    command, expected_head=packet["expected_head"], immutable_objects=[obj],
)
raise SystemExit("Boundary not reached")

"""Small allowlisted dispatcher for vNext product command modules."""
from __future__ import annotations

import importlib
from typing import Sequence

_COMMANDS = {
    "features": ("bdb_audit.features.cli", "run_cli"),
    "workbench": ("bdb_audit.workbench.cli", "run_cli"),
    "qualification": ("bdb_audit.qualification.cli", "run_cli"),
}


def dispatch_vnext(argv: Sequence[str]) -> int | None:
    if not argv or argv[0] not in _COMMANDS:
        return None
    module_name, handler_name = _COMMANDS[argv[0]]
    module = importlib.import_module(module_name)
    handler = getattr(module, handler_name)
    return int(handler(argv[1:]))


__all__ = ["dispatch_vnext"]

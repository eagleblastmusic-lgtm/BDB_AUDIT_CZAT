"""Small allowlisted dispatcher for vNext product command modules."""
from __future__ import annotations

import importlib
from typing import Sequence

_COMMANDS = {
    "features": ("bdb_audit.features.cli", "run_features_cli"),
    "workbench": ("bdb_audit.workbench.cli", "run_cli"),
    "qualification": ("bdb_audit.qualification.cli", "run_cli"),
    "strategy": ("bdb_audit.strategy.cli", "run_cli"),
    "lanes": ("bdb_audit.strategy.entrypoints", "run_lanes_cli"),
    "budget": ("bdb_audit.strategy.entrypoints", "run_budget_cli"),
    "exposure": ("bdb_audit.strategy.entrypoints", "run_exposure_cli"),
    "opportunities": ("bdb_audit.opportunities.cli", "run_cli"),
    "audit": ("bdb_audit.incremental.cli", "run_audit_cli"),
    "evidence": ("bdb_audit.incremental.cli", "run_evidence_cli"),
    "regression": ("bdb_audit.incremental.cli", "run_regression_cli"),
    "history": ("bdb_audit.history_view.cli", "run_history_cli"),
    "share": ("bdb_audit.history_view.cli", "run_share_cli"),
}


def dispatch_vnext(argv: Sequence[str]) -> int | None:
    if not argv or argv[0] not in _COMMANDS:
        return None
    module_name, handler_name = _COMMANDS[argv[0]]
    module = importlib.import_module(module_name)
    handler = getattr(module, handler_name)
    return int(handler(argv[1:]))


__all__ = ["dispatch_vnext"]

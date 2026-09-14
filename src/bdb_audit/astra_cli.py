"""CLI shim that exposes Astra continuation without changing legacy commands."""
from __future__ import annotations

import sys
from typing import Sequence

from . import cli as _base
from .astra_flow_cli import run_flow_cli
from .astra_ui import run_ui


def run_cli(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values and values[0] == "ui":
        return run_ui()
    if values and values[0] == "flow":
        return run_flow_cli(values[1:])
    return _base.run_cli(values)


def main() -> None:
    sys.exit(run_cli())


__all__ = ["run_cli", "main"]

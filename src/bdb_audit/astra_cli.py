"""CLI shim that exposes the Astra continuation UI without changing legacy commands."""
from __future__ import annotations

import sys
from typing import Sequence

from . import cli as _base
from .astra_ui import run_ui


def run_cli(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values and values[0] == "ui":
        return run_ui()
    return _base.run_cli(values)


def main() -> None:
    sys.exit(run_cli())


__all__ = ["run_cli", "main"]

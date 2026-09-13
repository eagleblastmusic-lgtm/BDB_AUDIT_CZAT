"""RU10 exact-argv adapters. No commands are inferred from target documentation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

from .specs import ToolRunSpec


@dataclass(frozen=True)
class PytestAdapter:
    test_ids: tuple[str, ...]

    def build(self, *, run_id: str, source_root: str | Path, evidence_dir: str | Path, timeout_seconds: int = 300) -> ToolRunSpec:
        return ToolRunSpec(
            run_id=run_id,
            source_root=str(source_root),
            evidence_dir=str(evidence_dir),
            argv=(sys.executable, "-m", "pytest", "-q", *self.test_ids),
            timeout_seconds=timeout_seconds,
        )


@dataclass(frozen=True)
class PythonModuleAdapter:
    module: str
    args: tuple[str, ...] = ()

    def build(self, *, run_id: str, source_root: str | Path, evidence_dir: str | Path, timeout_seconds: int = 120) -> ToolRunSpec:
        return ToolRunSpec(
            run_id=run_id,
            source_root=str(source_root),
            evidence_dir=str(evidence_dir),
            argv=(sys.executable, "-m", self.module, *self.args),
            timeout_seconds=timeout_seconds,
        )


@dataclass(frozen=True)
class ExactArgvAdapter:
    argv: tuple[str, ...]

    def build(self, *, run_id: str, source_root: str | Path, evidence_dir: str | Path, timeout_seconds: int = 120) -> ToolRunSpec:
        return ToolRunSpec(
            run_id=run_id,
            source_root=str(source_root),
            evidence_dir=str(evidence_dir),
            argv=self.argv,
            timeout_seconds=timeout_seconds,
        )


__all__ = ["PytestAdapter", "PythonModuleAdapter", "ExactArgvAdapter"]

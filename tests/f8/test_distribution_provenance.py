"""Repository distribution/provenance regression guards (FRESH-03)."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_STANDALONE_PATHSPEC = "dist/BDB_AUDIT_ASSISTANT_v*.py"
IGNORE_RULE = "/dist/BDB_AUDIT_ASSISTANT_v*.py"


def _tracked_generated_standalones() -> tuple[str, ...]:
    """Return generated standalone paths tracked by the repository index.

    The provenance property is a repository property, so source archives without
    Git metadata cannot prove or disprove it and are outside this check's scope.
    """
    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("repository provenance check requires Git metadata")

    proc = subprocess.run(
        ["git", "ls-files", "--", GENERATED_STANDALONE_PATHSPEC],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return tuple(line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip())


def test_generated_versioned_standalones_are_not_tracked() -> None:
    """A source checkout must not publish a second tracked artifact identity."""
    assert _tracked_generated_standalones() == ()


def test_generated_versioned_standalones_are_ignored() -> None:
    """Local/CI builds may write to dist without becoming repository authority."""
    rules = {
        line.strip()
        for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert IGNORE_RULE in rules


def test_dist_readme_declares_release_authority_boundary() -> None:
    """The source tree must state where authoritative release bytes live."""
    text = (REPO_ROOT / "dist" / "README.md").read_text(encoding="utf-8")
    assert "not release authority" in text
    assert "qualified assets attached to the corresponding immutable GitHub Release" in text
    assert "must not be committed to the source tree" in text

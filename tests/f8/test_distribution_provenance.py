"""Repository distribution/provenance regression guards (FRESH-03)."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_STANDALONE_PATHSPEC = "dist/BDB_AUDIT_ASSISTANT_v*.py"
IGNORE_RULE = "/dist/BDB_AUDIT_ASSISTANT_v*.py"


def _tracked_generated_standalones() -> tuple[str, ...]:
    """Return generated standalone paths tracked by the repository index.

    The provenance property is a repository property. Outside a Git checkout it
    may be skipped for developer/source-archive test runs, but the authoritative
    GitHub Actions qualification must fail closed if Git/index inspection is not
    available.
    """
    git = shutil.which("git")
    in_github_actions = os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
    if git is None:
        if in_github_actions:
            pytest.fail("Git executable is required for the repository provenance gate")
        pytest.skip("repository provenance check requires Git")

    proc = subprocess.run(
        [git, "ls-files", "--", GENERATED_STANDALONE_PATHSPEC],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"git exit {proc.returncode}"
        if in_github_actions:
            pytest.fail(f"repository provenance gate cannot inspect Git index: {detail}")
        pytest.skip(f"repository provenance check requires a Git checkout: {detail}")

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

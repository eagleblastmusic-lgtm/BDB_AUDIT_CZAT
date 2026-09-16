"""Repository-wide GitHub Actions supply-chain guards (FRESH-04)."""
from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
USES_RE = re.compile(r"^\s*uses:\s*['\"]?([^'\"#\s]+)", re.MULTILINE)
IMMUTABLE_ACTION_RE = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-fA-F]{40}$"
)


def _external_action_refs() -> tuple[tuple[str, str], ...]:
    refs: list[tuple[str, str]] = []
    workflow_files = sorted((*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")))
    assert workflow_files, "No GitHub Actions workflows found"

    for workflow in workflow_files:
        text = workflow.read_text(encoding="utf-8")
        for match in USES_RE.finditer(text):
            ref = match.group(1)
            if ref.startswith("./") or ref.startswith("docker://"):
                continue
            refs.append((workflow.name, ref))

    assert refs, "No external GitHub Actions references found"
    return tuple(refs)


def test_all_external_github_actions_are_pinned_to_commit_sha() -> None:
    """Every external action must use an immutable 40-hex commit SHA."""
    mutable = [
        f"{workflow}: {ref}"
        for workflow, ref in _external_action_refs()
        if IMMUTABLE_ACTION_RE.fullmatch(ref) is None
    ]
    assert not mutable, (
        "Mutable or non-commit GitHub Action references are forbidden:\n"
        + "\n".join(mutable)
    )

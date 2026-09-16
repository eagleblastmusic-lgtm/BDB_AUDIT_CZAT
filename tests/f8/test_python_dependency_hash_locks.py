from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
SEMANTIC_RUNTIME_LOCK = REPO_ROOT / "requirements-f2.lock"
HASHED_RUNTIME_LOCK = REPO_ROOT / "requirements-f2-win-py314-hashes.lock"
HASHED_BOOTSTRAP_LOCK = REPO_ROOT / "requirements-ci-bootstrap-win-py314-hashes.lock"
HASHED_TOOLS_LOCK = REPO_ROOT / "requirements-ci-tools-win-py314-hashes.lock"
HASHED_LOCKS = (HASHED_RUNTIME_LOCK, HASHED_BOOTSTRAP_LOCK, HASHED_TOOLS_LOCK)

_REQUIREMENT_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)(?:\s+\\)?$")
_HASH_RE = re.compile(r"^--hash=sha256:([0-9a-f]{64})$")


def _canonical_name(name: str) -> str:
    return name.lower().replace("_", "-")


def _parse_semantic_lock(path: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _REQUIREMENT_RE.fullmatch(line)
        assert match is not None, f"Malformed semantic lock entry: {line}"
        parsed[_canonical_name(match.group(1))] = match.group(2)
    assert parsed
    return parsed


def _parse_hashed_lock(path: Path) -> dict[str, tuple[str, str]]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    parsed: dict[str, tuple[str, str]] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line or line.startswith("#"):
            continue
        requirement = _REQUIREMENT_RE.fullmatch(line)
        assert requirement is not None, f"Malformed hashed lock requirement in {path.name}: {line}"
        assert index < len(lines), f"Missing hash after {line} in {path.name}"
        hash_line = lines[index]
        index += 1
        hash_match = _HASH_RE.fullmatch(hash_line)
        assert hash_match is not None, f"Missing exact sha256 after {line} in {path.name}: {hash_line}"
        name = _canonical_name(requirement.group(1))
        assert name not in parsed, f"Duplicate package {name} in {path.name}"
        parsed[name] = (requirement.group(2), hash_match.group(1))
    assert parsed, f"Hashed lock is empty: {path.name}"
    return parsed


def test_all_dependency_lock_entries_have_exact_sha256() -> None:
    for lock_path in HASHED_LOCKS:
        parsed = _parse_hashed_lock(lock_path)
        assert all(len(sha256) == 64 for _version, sha256 in parsed.values())


def test_hashed_runtime_lock_matches_semantic_runtime_lock_exactly() -> None:
    semantic = _parse_semantic_lock(SEMANTIC_RUNTIME_LOCK)
    hashed = {name: version for name, (version, _hash) in _parse_hashed_lock(HASHED_RUNTIME_LOCK).items()}
    assert hashed == semantic


def test_workflow_pip_network_installs_are_hash_locked() -> None:
    violations: list[str] = []
    for workflow in sorted((*WORKFLOWS_DIR.glob("*.yml"), *WORKFLOWS_DIR.glob("*.yaml"))):
        for line_number, raw in enumerate(workflow.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw.strip()
            if "python -m pip install" not in line:
                continue
            if "-e ." in line:
                if "--no-deps" not in line or "--no-build-isolation" not in line:
                    violations.append(f"{workflow.name}:{line_number}: editable install may reach the network: {line}")
                continue
            required = ("--require-hashes", "--only-binary=:all:", "-r ")
            if any(token not in line for token in required) or "hashes.lock" not in line:
                violations.append(f"{workflow.name}:{line_number}: unhashed network install: {line}")
    assert not violations, "\n".join(violations)

"""Verified Git source identity helpers for RU02.

No 40-hex string is accepted merely because it looks like a SHA.  Resolution
always proves that the selected object exists as a commit in the authorized
repository and records its exact tree object.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Iterator
from urllib.parse import parse_qsl, urlsplit

from ..core.errors import ValidationError

_HEX_OBJECT = re.compile(r"^[0-9a-fA-F]{40,64}$")
_SENSITIVE_QUERY_KEYS = {
    "access_token", "token", "auth", "authorization", "password", "passwd",
    "secret", "key", "api_key", "apikey", "credential", "credentials",
}


@dataclass(frozen=True)
class VerifiedGitIdentity:
    repository: str
    requested_ref: str
    commit_object_id: str
    tree_object_id: str
    object_format: str = "sha1"


def validate_repository_location(location: str) -> str:
    """Reject credential-bearing/export-unsafe repository locations."""
    value = location.strip()
    if not value:
        raise ValidationError("EMPTY_SOURCE_LOCATION")
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"}:
        if parsed.username is not None or parsed.password is not None:
            raise ValidationError("CREDENTIALS_IN_SOURCE_URL", "Repository URL must not contain userinfo credentials")
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
            if key.lower() in _SENSITIVE_QUERY_KEYS:
                raise ValidationError("CREDENTIALS_IN_SOURCE_URL", "Repository URL contains a sensitive query parameter")
    return value


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_CONFIG_NOSYSTEM"] = env.get("GIT_CONFIG_NOSYSTEM", "0")
    return env


def _run_git(repo: Path | None, args: list[str], *, timeout: int = 30) -> str:
    cmd = ["git"]
    if repo is not None:
        cmd += ["-C", str(repo)]
    cmd += args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_git_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError("GIT_SOURCE_UNAVAILABLE", type(exc).__name__) from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "git command failed").strip().splitlines()[-1]
        raise ValidationError("GIT_SOURCE_VERIFICATION_FAILED", detail[:400])
    return proc.stdout.strip()


def _verify_commit(repo: Path, requested: str) -> tuple[str, str]:
    commit = _run_git(repo, ["rev-parse", "--verify", f"{requested}^{{commit}}"]).lower()
    if not _HEX_OBJECT.fullmatch(commit):
        raise ValidationError("INVALID_GIT_OBJECT_ID", "Resolved commit has unsupported object-id syntax")
    obj_type = _run_git(repo, ["cat-file", "-t", commit])
    if obj_type != "commit":
        raise ValidationError("GIT_OBJECT_NOT_COMMIT", obj_type)
    tree = _run_git(repo, ["rev-parse", "--verify", f"{commit}^{{tree}}"]).lower()
    if not _HEX_OBJECT.fullmatch(tree):
        raise ValidationError("INVALID_GIT_TREE_OBJECT_ID")
    object_format = "sha1" if len(commit) == 40 else "sha256"
    return commit, tree


def resolve_local_repository(location: str | Path, ref: str = "HEAD", explicit_sha: str | None = None) -> VerifiedGitIdentity:
    repo = Path(location).resolve()
    if not repo.exists():
        raise ValidationError("SOURCE_REPOSITORY_NOT_FOUND", str(repo))
    _run_git(repo, ["rev-parse", "--git-dir"])
    requested = explicit_sha.strip() if explicit_sha else ref
    if explicit_sha and not _HEX_OBJECT.fullmatch(requested):
        raise ValidationError("INVALID_EXPLICIT_COMMIT_ID")
    commit, tree = _verify_commit(repo, requested)
    return VerifiedGitIdentity(str(repo), ref, commit, tree, "sha1" if len(commit) == 40 else "sha256")


def _select_remote_ref(repo_url: str, ref: str) -> str:
    if ref.startswith("refs/"):
        return ref
    output = _run_git(None, ["ls-remote", "--heads", "--tags", repo_url, f"refs/heads/{ref}", f"refs/tags/{ref}", f"refs/tags/{ref}^{{}}"], timeout=30)
    names = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            names[parts[1]] = parts[0]
    head = f"refs/heads/{ref}"
    tag = f"refs/tags/{ref}"
    if head in names and tag in names:
        raise ValidationError("AMBIGUOUS_GIT_REF", f"'{ref}' exists as both branch and tag; use an explicit refs/... namespace")
    if head in names:
        return head
    if tag in names or f"{tag}^{{}}" in names:
        return tag
    raise ValidationError("GIT_REF_NOT_FOUND", f"Cannot resolve requested ref '{ref}'")


@contextmanager
def fetched_remote_repository(repo_url: str, ref: str = "main", explicit_sha: str | None = None) -> Iterator[tuple[Path, VerifiedGitIdentity]]:
    safe_url = validate_repository_location(repo_url)
    with tempfile.TemporaryDirectory(prefix="bdb_source_git_") as td:
        repo = Path(td) / "repo.git"
        _run_git(None, ["init", "--bare", str(repo)])
        _run_git(repo, ["remote", "add", "origin", safe_url])
        if explicit_sha:
            requested = explicit_sha.strip()
            if not _HEX_OBJECT.fullmatch(requested):
                raise ValidationError("INVALID_EXPLICIT_COMMIT_ID")
            fetch_target = requested
        else:
            fetch_target = _select_remote_ref(safe_url, ref)
            requested = "FETCH_HEAD"
        _run_git(repo, ["fetch", "--no-tags", "--depth=1", "origin", fetch_target], timeout=90)
        commit, tree = _verify_commit(repo, requested)
        if explicit_sha and commit != explicit_sha.lower():
            raise ValidationError("EXPLICIT_COMMIT_MISMATCH")
        identity = VerifiedGitIdentity(safe_url, ref, commit, tree, "sha1" if len(commit) == 40 else "sha256")
        yield repo, identity


def resolve_remote_repository(repo_url: str, ref: str = "main", explicit_sha: str | None = None) -> VerifiedGitIdentity:
    with fetched_remote_repository(repo_url, ref, explicit_sha) as (_, identity):
        return identity


__all__ = [
    "VerifiedGitIdentity",
    "validate_repository_location",
    "resolve_local_repository",
    "resolve_remote_repository",
    "fetched_remote_repository",
]

"""Audit target and verified source identity resolution.

Floating refs are resolved only by proving an actual Git commit object in the
authorized repository.  Commit and tree identities are kept distinct.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from ..core.errors import ValidationError
from ..source.git_resolver import (
    resolve_local_repository,
    resolve_remote_repository,
    validate_repository_location,
)

GIT_OBJECT_HEX_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")
# Backward-compatible exported name; SHA-1 repositories remain the baseline.
SHA1_HEX_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")


@dataclass(frozen=True)
class ResolvedSource:
    """Exact, immutable source identity binding for a campaign."""
    target_type: str
    location: str
    display_name: str
    ref: str
    exact_commit_sha: str
    resolved: bool = True
    exact_tree_sha: str | None = None
    object_format: str = "sha1"

    def __post_init__(self):
        if not GIT_OBJECT_HEX_PATTERN.fullmatch(self.exact_commit_sha):
            raise ValueError(f"Invalid Git commit object ID: {self.exact_commit_sha}")
        if self.exact_tree_sha is not None and not GIT_OBJECT_HEX_PATTERN.fullmatch(self.exact_tree_sha):
            raise ValueError(f"Invalid Git tree object ID: {self.exact_tree_sha}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_type": self.target_type,
            "location": self.location,
            "display_name": self.display_name,
            "ref": self.ref,
            "exact_commit_sha": self.exact_commit_sha,
            "exact_tree_sha": self.exact_tree_sha,
            "object_format": self.object_format,
            "resolved": self.resolved,
        }


def _clean_github_display_name(url_or_slug: str) -> str:
    s = url_or_slug.strip().rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if s.startswith(prefix):
            return s[len(prefix):]
    return s


def resolve_github_source(repo_url: str, ref: str, explicit_sha: str | None = None) -> ResolvedSource:
    """Resolve a remote repository to a proved commit+tree identity."""
    safe_url = validate_repository_location(repo_url)
    display = _clean_github_display_name(safe_url)
    try:
        identity = resolve_remote_repository(safe_url, ref, explicit_sha)
    except ValidationError as exc:
        if exc.code in {
            "CREDENTIALS_IN_SOURCE_URL", "AMBIGUOUS_GIT_REF", "INVALID_EXPLICIT_COMMIT_ID",
            "EXPLICIT_COMMIT_MISMATCH", "GIT_OBJECT_NOT_COMMIT", "INVALID_GIT_OBJECT_ID",
            "INVALID_GIT_TREE_OBJECT_ID",
        }:
            raise
        raise ValidationError(
            "COULD_NOT_RESOLVE_EXACT_SHA",
            f"Remote ref '{ref}' could not be verified as a commit object ({exc.code})",
        ) from exc
    return ResolvedSource(
        target_type="github",
        location=safe_url,
        display_name=display,
        ref=ref,
        exact_commit_sha=identity.commit_object_id,
        exact_tree_sha=identity.tree_object_id,
        object_format=identity.object_format,
    )


def resolve_local_source(local_path: str | Path, ref: str = "HEAD", explicit_sha: str | None = None) -> ResolvedSource:
    """Resolve a local repository to a proved commit+tree identity."""
    p = Path(local_path).resolve()
    try:
        identity = resolve_local_repository(p, ref, explicit_sha)
    except ValidationError as exc:
        raise ValidationError("COULD_NOT_RESOLVE_LOCAL_SHA", f"{p}: {exc.code}") from exc
    return ResolvedSource(
        target_type="local",
        location=str(p),
        display_name=p.name,
        ref=ref,
        exact_commit_sha=identity.commit_object_id,
        exact_tree_sha=identity.tree_object_id,
        object_format=identity.object_format,
    )


def resolve_source_identity(
    target_type: str,
    location: str,
    ref: str = "main",
    explicit_sha: str | None = None,
) -> ResolvedSource:
    if target_type.lower() in ("github", "git", "remote"):
        return resolve_github_source(location, ref, explicit_sha=explicit_sha)
    return resolve_local_source(location, ref, explicit_sha=explicit_sha)


__all__ = [
    "SHA1_HEX_PATTERN",
    "GIT_OBJECT_HEX_PATTERN",
    "ResolvedSource",
    "resolve_github_source",
    "resolve_local_source",
    "resolve_source_identity",
]

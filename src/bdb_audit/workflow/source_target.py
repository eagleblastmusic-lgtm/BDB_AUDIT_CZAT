"""Audit target and exact source identity resolution for BDB Audit v2.0.3.

Binds user-configured repository targets and branch references to an exact,
immutable 40-character commit SHA. Floating branch references (such as 'main')
are never treated as exact source identity; if unresolvable, resolution fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Any

SHA1_HEX_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")


@dataclass(frozen=True)
class ResolvedSource:
    """Exact, immutable source identity binding for a campaign."""
    target_type: str  # "github" | "local"
    location: str     # URL or filesystem path
    display_name: str # e.g. "eagleblastmusic-lgtm/Archive"
    ref: str          # e.g. "main"
    exact_commit_sha: str
    resolved: bool = True

    def __post_init__(self):
        if not SHA1_HEX_PATTERN.match(self.exact_commit_sha):
            raise ValueError(f"Invalid 40-character commit SHA: {self.exact_commit_sha}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_type": self.target_type,
            "location": self.location,
            "display_name": self.display_name,
            "ref": self.ref,
            "exact_commit_sha": self.exact_commit_sha,
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
    """Resolve GitHub repository and ref to an exact 40-character commit SHA."""
    display = _clean_github_display_name(repo_url)

    # 1. If user supplied an exact 40-character commit SHA explicitly
    if explicit_sha and SHA1_HEX_PATTERN.match(explicit_sha.strip()):
        return ResolvedSource(
            target_type="github",
            location=repo_url,
            display_name=display,
            ref=ref,
            exact_commit_sha=explicit_sha.strip(),
        )

    # 2. Query remote repository via git ls-remote
    try:
        proc = subprocess.run(
            ["git", "ls-remote", repo_url, ref],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode == 0 and proc.stdout:
            for line in proc.stdout.splitlines():
                parts = line.strip().split()
                if parts and SHA1_HEX_PATTERN.match(parts[0]):
                    return ResolvedSource(
                        target_type="github",
                        location=repo_url,
                        display_name=display,
                        ref=ref,
                        exact_commit_sha=parts[0],
                    )
    except Exception:
        pass

    # 3. Check if local git clone of this repository exists and knows the remote
    try:
        proc = subprocess.run(
            ["git", "rev-parse", ref],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            sha = proc.stdout.strip()
            if SHA1_HEX_PATTERN.match(sha):
                return ResolvedSource(
                    target_type="github",
                    location=repo_url,
                    display_name=display,
                    ref=ref,
                    exact_commit_sha=sha,
                )
    except Exception:
        pass

    raise ValueError(
        f"COULD_NOT_RESOLVE_EXACT_SHA: Cannot resolve '{ref}' for '{repo_url}' to an exact 40-character commit SHA. "
        "Please provide the exact commit SHA or check network connectivity."
    )


def resolve_local_source(local_path: str | Path, ref: str = "HEAD", explicit_sha: str | None = None) -> ResolvedSource:
    """Resolve local git directory and ref to an exact 40-character commit SHA."""
    p = Path(local_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Local repository directory does not exist: {p}")

    if explicit_sha and SHA1_HEX_PATTERN.match(explicit_sha.strip()):
        return ResolvedSource(
            target_type="local",
            location=str(p),
            display_name=p.name,
            ref=ref,
            exact_commit_sha=explicit_sha.strip(),
        )

    try:
        proc = subprocess.run(
            ["git", "-C", str(p), "rev-parse", ref],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            sha = proc.stdout.strip()
            if SHA1_HEX_PATTERN.match(sha):
                return ResolvedSource(
                    target_type="local",
                    location=str(p),
                    display_name=p.name,
                    ref=ref,
                    exact_commit_sha=sha,
                )
    except Exception as exc:
        raise ValueError(f"COULD_NOT_RESOLVE_LOCAL_SHA: git rev-parse failed in {p}: {exc}") from exc

    raise ValueError(f"COULD_NOT_RESOLVE_LOCAL_SHA: Ref '{ref}' in {p} did not produce a 40-character SHA")


def resolve_source_identity(
    target_type: str,
    location: str,
    ref: str = "main",
    explicit_sha: str | None = None,
) -> ResolvedSource:
    """Universal resolver for audit source target."""
    if target_type.lower() in ("github", "git", "remote"):
        return resolve_github_source(location, ref, explicit_sha=explicit_sha)
    return resolve_local_source(location, ref, explicit_sha=explicit_sha)


__all__ = [
    "SHA1_HEX_PATTERN",
    "ResolvedSource",
    "resolve_github_source",
    "resolve_local_source",
    "resolve_source_identity",
]

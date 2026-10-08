"""Deterministic source materialization from verified Git objects (RU02)."""
from __future__ import annotations

from dataclasses import dataclass
import base64
import os
from pathlib import Path
import subprocess
from typing import Any

from ..core.errors import ValidationError
from ..core.hashing import raw_digest
from .git_resolver import (
    VerifiedGitIdentity,
    fetched_remote_repository,
    resolve_local_repository,
)


@dataclass(frozen=True)
class SourceMaterialization:
    identity: VerifiedGitIdentity
    entries: tuple[dict[str, Any], ...]
    completeness_state: str
    limitations: tuple[str, ...] = ()

    def manifest_body(self) -> dict[str, Any]:
        return {"entries": [dict(entry) for entry in self.entries]}


def _git_bytes(repo: Path, args: list[str], *, timeout: int = 30) -> bytes:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            timeout=timeout,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError("GIT_SOURCE_UNAVAILABLE", type(exc).__name__) from exc
    if proc.returncode != 0:
        raise ValidationError("SOURCE_MATERIALIZATION_FAILED", proc.stderr.decode("utf-8", "replace")[-400:])
    return proc.stdout


def _canonical_path(raw_path: bytes) -> str:
    try:
        path = raw_path.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ValidationError("SOURCE_PROFILE_UNSUPPORTED", "Git path is not valid UTF-8") from exc
    if not path or path.startswith("/") or "\\" in path or "\x00" in path:
        raise ValidationError("NONCANONICAL_SOURCE_PATH", path)
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValidationError("NONCANONICAL_SOURCE_PATH", path)
    return path


def _blob(repo: Path, object_id: str) -> bytes:
    return _git_bytes(repo, ["cat-file", "blob", object_id])


def _manifest_from_repo(repo: Path, identity: VerifiedGitIdentity) -> SourceMaterialization:
    raw = _git_bytes(repo, ["ls-tree", "-r", "-z", "--full-tree", identity.commit_object_id])
    entries: list[dict[str, Any]] = []
    limitations: list[str] = []
    seen: set[str] = set()

    for record in raw.split(b"\x00"):
        if not record:
            continue
        try:
            meta, raw_path = record.split(b"\t", 1)
            mode_b, type_b, oid_b = meta.split(b" ", 2)
        except ValueError as exc:
            raise ValidationError("MALFORMED_GIT_TREE_ENTRY") from exc
        mode = mode_b.decode("ascii")
        obj_type = type_b.decode("ascii")
        object_id = oid_b.decode("ascii").lower()
        path = _canonical_path(raw_path)
        if path in seen:
            raise ValidationError("DUPLICATE_SOURCE_PATH", path)
        seen.add(path)

        if mode == "160000" or obj_type == "commit":
            entries.append({
                "repo_relative_posix_path": path,
                "entry_type": "SUBMODULE",
                "relevant_mode": mode,
                "submodule_object_id": object_id,
            })
            limitations.append(f"UNMATERIALIZED_SUBMODULE:{path}")
            continue

        data = _blob(repo, object_id)
        if mode == "120000":
            entries.append({
                "repo_relative_posix_path": path,
                "entry_type": "SYMLINK",
                "relevant_mode": mode,
                "byte_length": len(data),
                "content_raw_digest": raw_digest(data).value,
                "symlink_target": base64.b64encode(data).decode("ascii"),
                "symlink_target_encoding": "base64",
            })
            continue

        if obj_type != "blob" or mode not in {"100644", "100755"}:
            entries.append({
                "repo_relative_posix_path": path,
                "entry_type": "OTHER_ALLOWED",
                "relevant_mode": mode,
                "byte_length": len(data),
                "content_raw_digest": raw_digest(data).value,
            })
            limitations.append(f"OTHER_GIT_ENTRY:{path}:{mode}:{obj_type}")
            continue

        lfs_pointer = data.startswith(b"version https://git-lfs.github.com/spec/v1\n")
        entry = {
            "repo_relative_posix_path": path,
            "entry_type": "REGULAR_FILE",
            "relevant_mode": mode,
            "byte_length": len(data),
            "content_raw_digest": raw_digest(data).value,
        }
        if lfs_pointer:
            entry["lfs_pointer_state"] = "POINTER_UNMATERIALIZED"
            limitations.append(f"UNMATERIALIZED_LFS:{path}")
        entries.append(entry)

    entries.sort(key=lambda e: e["repo_relative_posix_path"].encode("utf-8"))
    completeness = "COMPLETE_SOURCE" if not limitations else "BOUNDED_SOURCE"
    return SourceMaterialization(identity, tuple(entries), completeness, tuple(sorted(limitations)))


def materialize_local_source(location: str | Path, ref: str = "HEAD", explicit_sha: str | None = None) -> SourceMaterialization:
    identity = resolve_local_repository(location, ref, explicit_sha)
    return _manifest_from_repo(Path(identity.repository), identity)


def materialize_remote_source(repo_url: str, ref: str = "main", explicit_sha: str | None = None) -> SourceMaterialization:
    with fetched_remote_repository(repo_url, ref, explicit_sha) as (repo, identity):
        return _manifest_from_repo(repo, identity)


__all__ = ["SourceMaterialization", "materialize_local_source", "materialize_remote_source"]

"""RU10 source/environment identity for controlled tool execution."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import sys
from typing import Any

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from .specs import CapabilityProfile

_IGNORED_DIRS = frozenset({".git", ".pytest_cache", "__pycache__"})


def source_manifest(root: str | Path) -> dict[str, Any]:
    source = Path(root).resolve()
    if not source.is_dir():
        raise ValidationError("TOOL_RUN_SOURCE_NOT_FOUND", str(source))
    members: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(source):
        dirnames[:] = sorted(name for name in dirnames if name not in _IGNORED_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.is_symlink():
                raise ValidationError("TOOL_RUN_SOURCE_SYMLINK_UNSUPPORTED", str(path))
            rel = path.relative_to(source).as_posix()
            digest = hashlib.sha256()
            size = 0
            try:
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                        size += len(chunk)
            except OSError as exc:
                raise ValidationError("TOOL_RUN_SOURCE_READ_FAILED", rel) from exc
            members.append({"path": rel, "sha256": digest.hexdigest(), "size": size})
    body = {
        "profile": "BDB_TOOL_SOURCE_MANIFEST_V1",
        "ignored_directories": sorted(_IGNORED_DIRS),
        "members": members,
    }
    body["manifest_digest"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
    return body


def environment_manifest(root: str | Path, profile: CapabilityProfile) -> dict[str, Any]:
    source = source_manifest(root)
    body: dict[str, Any] = {
        "profile": "BDB_TOOL_ENVIRONMENT_MANIFEST_V1",
        "source_manifest_digest": source["manifest_digest"],
        "source_member_count": len(source["members"]),
        "capability_profile_digest": profile.digest,
        "implementation": sys.implementation.name,
        "python_version": platform.python_version(),
        "executable_name": Path(sys.executable).name,
        "system": platform.system().lower(),
        "machine": platform.machine().lower(),
    }
    body["manifest_digest"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
    return body


__all__ = ["source_manifest", "environment_manifest"]

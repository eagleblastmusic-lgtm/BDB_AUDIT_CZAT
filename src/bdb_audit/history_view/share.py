"""RU17 privacy-aware, digest-verifiable share bundles.

No cryptographic signing authority is invented here. Without an explicit
key-governance contract, BDB can bind an optional external attestation reference
but cannot claim to verify its signature.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from .models import PrivacyPolicy

_MANIFEST = "SHARE_MANIFEST.json"


def _sha(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256(); size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk); size += len(chunk)
    return digest.hexdigest(), size


def _safe_rel(value: str) -> str:
    normalized = value.replace("\\", "/").strip("/")
    parts = tuple(item for item in normalized.split("/") if item and item != ".")
    if not parts or any(item == ".." for item in parts):
        raise ValidationError("SHARE_PATH_INVALID", value)
    return "/".join(parts)


def _excluded(rel: str, policy: PrivacyPolicy) -> bool:
    return any(rel == prefix or rel.startswith(prefix + "/") for prefix in policy.excluded_path_prefixes)


def export_share_bundle(
    source_root: str | Path,
    output_dir: str | Path,
    *,
    include_paths: Sequence[str],
    privacy_policy: PrivacyPolicy,
    source_identity: Mapping[str, Any],
    history_cut: Mapping[str, Any] | None = None,
    attestation_ref: str | None = None,
) -> dict[str, Any]:
    source = Path(source_root).resolve(); output = Path(output_dir).resolve()
    if not source.is_dir(): raise ValidationError("SHARE_SOURCE_NOT_FOUND", str(source))
    if output == source or source in output.parents:
        raise ValidationError("SHARE_OUTPUT_INVALID")
    if output.exists(): shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=False)
    files: list[dict[str, Any]] = []; excluded: list[str] = []
    try:
        for raw in sorted(set(include_paths)):
            rel = _safe_rel(raw)
            if _excluded(rel, privacy_policy):
                excluded.append(rel); continue
            src = (source / rel).resolve()
            try: src.relative_to(source)
            except ValueError as exc: raise ValidationError("SHARE_PATH_ESCAPE", rel) from exc
            if not src.is_file(): raise ValidationError("SHARE_FILE_NOT_FOUND", rel)
            if src.is_symlink(): raise ValidationError("SHARE_SYMLINK_UNSUPPORTED", rel)
            digest, size = _sha(src)
            if size > privacy_policy.max_file_bytes: raise ValidationError("SHARE_FILE_TOO_LARGE", rel)
            dest = output / rel; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dest)
            copied_digest, copied_size = _sha(dest)
            if copied_digest != digest or copied_size != size: raise ValidationError("SHARE_COPY_IDENTITY_MISMATCH", rel)
            files.append({"path": rel, "sha256": digest, "size": size})
        body: dict[str, Any] = {
            "schema_version": "RU17-SHARE-BUNDLE-1",
            "source_identity": dict(source_identity),
            "history_cut": dict(history_cut) if history_cut is not None else None,
            "privacy_policy": privacy_policy.as_dict(),
            "files": files,
            "excluded_paths": sorted(excluded),
            "attestation": {
                "status": "EXTERNAL_REFERENCE_UNVERIFIED" if attestation_ref else "NOT_PROVIDED",
                "reference": attestation_ref,
                "key_governance": "NOT_DEFINED_BY_THIS_BUNDLE",
            },
        }
        body["manifest_digest"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
        (output / _MANIFEST).write_text(json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
        return {"status": "PASS", "bundle": str(output), "manifest_digest": body["manifest_digest"], "file_count": len(files), "excluded_count": len(excluded), "attestation_status": body["attestation"]["status"]}
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def verify_share_bundle(bundle_dir: str | Path) -> dict[str, Any]:
    root = Path(bundle_dir).resolve(); manifest_path = root / _MANIFEST
    if not manifest_path.is_file(): raise ValidationError("SHARE_MANIFEST_MISSING")
    try: manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValidationError("SHARE_MANIFEST_PARSE_FAILED") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "RU17-SHARE-BUNDLE-1": raise ValidationError("SHARE_MANIFEST_SCHEMA_INVALID")
    supplied = manifest.get("manifest_digest"); body = dict(manifest); body.pop("manifest_digest", None)
    calculated = hashlib.sha256(canonical_bytes(body)).hexdigest()
    if supplied != calculated: raise ValidationError("SHARE_MANIFEST_DIGEST_MISMATCH")
    files = body.get("files")
    if not isinstance(files, list): raise ValidationError("SHARE_FILES_INVALID")
    expected = set()
    for item in files:
        if not isinstance(item, dict): raise ValidationError("SHARE_FILE_ENTRY_INVALID")
        rel = _safe_rel(str(item.get("path", ""))); expected.add(rel)
        path = (root / rel).resolve()
        try: path.relative_to(root)
        except ValueError as exc: raise ValidationError("SHARE_PATH_ESCAPE", rel) from exc
        if not path.is_file(): raise ValidationError("SHARE_FILE_MISSING", rel)
        digest, size = _sha(path)
        if digest != item.get("sha256") or size != item.get("size"): raise ValidationError("SHARE_FILE_IDENTITY_MISMATCH", rel)
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.name != _MANIFEST}
    if actual != expected: raise ValidationError("SHARE_UNMANIFESTED_FILE", ",".join(sorted(actual ^ expected)))
    attestation = body.get("attestation", {})
    return {"status": "PASS", "manifest_digest": calculated, "file_count": len(files), "attestation_status": attestation.get("status", "NOT_PROVIDED"), "cryptographic_signature_verified": False}


__all__ = ["export_share_bundle", "verify_share_bundle"]

#!/usr/bin/env python3
"""Canonicalize installed runtime RECORD metadata before standalone builds.

The standalone payload intentionally excludes files outside site-packages (for
example generated console launchers under ``Scripts/``) and ``__pycache__``.
Wheel ``RECORD`` files can nevertheless contain rows for those excluded files.
On Windows the generated launcher bytes are installation-instance-specific, so
keeping their hashes inside an otherwise deterministic embedded ``RECORD``
would make independent raw builds differ even though the packaged runtime is
identical.

This build-preparation step rewrites only RECORD rows for the exactly pinned
runtime distributions. It retains rows that describe files eligible for the
standalone payload and removes rows for paths the payload itself excludes.
Import metadata, package code, licensing files, METADATA, WHEEL, entry points,
and retained RECORD rows are preserved.
"""
from __future__ import annotations

import csv
import importlib.metadata
import io
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_LOCK_PATH = REPO_ROOT / "requirements-f2.lock"


def parse_runtime_lock(lock_path: Path = RUNTIME_LOCK_PATH) -> dict[str, str]:
    requirements: dict[str, str] = {}
    for raw_line in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise RuntimeError(f"Runtime lock entry is not exactly pinned: {line}")
        name, version = (part.strip() for part in line.split("==", 1))
        if not name or not version:
            raise RuntimeError(f"Malformed runtime lock entry: {line}")
        requirements[name.lower().replace("_", "-")] = version
    if not requirements:
        raise RuntimeError("Runtime lock contains no packages")
    return dict(sorted(requirements.items()))


def _safe_payload_path(value: str) -> str | None:
    normalized = value.replace("\\", "/")
    parts = tuple(part for part in normalized.split("/") if part not in ("", "."))
    if not parts or normalized.startswith("/") or any(part == ".." for part in parts):
        return None
    rel = "/".join(parts)
    if rel.endswith((".pyc", ".pyo")) or "/__pycache__/" in f"/{rel}/":
        return None
    return rel


def normalize_record_bytes(raw_bytes: bytes) -> bytes:
    """Return deterministic RECORD bytes for the payload-eligible file set."""
    text = raw_bytes.decode("utf-8")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    kept: list[list[str]] = []
    for row in rows:
        if not row:
            continue
        if len(row) != 3:
            raise RuntimeError(f"Malformed RECORD row: {row!r}")
        if _safe_payload_path(row[0]) is None:
            continue
        kept.append(row)

    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerows(kept)
    return out.getvalue().encode("utf-8")


def normalize_installed_runtime_records() -> dict[str, object]:
    """Normalize RECORD for every exactly pinned installed runtime package."""
    requirements = parse_runtime_lock()
    changed: list[str] = []
    verified: list[str] = []

    for dist_name, expected_version in requirements.items():
        try:
            dist = importlib.metadata.distribution(dist_name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(f"Pinned runtime distribution missing: {dist_name}=={expected_version}") from exc
        if dist.version != expected_version:
            raise RuntimeError(
                f"Runtime distribution drift for {dist_name}: expected {expected_version}, got {dist.version}"
            )
        files = dist.files
        if not files:
            raise RuntimeError(f"Distribution {dist_name} exposes no installed file manifest")

        record_entries = [p for p in files if str(p).replace("\\", "/").endswith(".dist-info/RECORD")]
        if len(record_entries) != 1:
            raise RuntimeError(f"Expected exactly one RECORD for {dist_name}, found {len(record_entries)}")
        record_path = Path(str(dist.locate_file(record_entries[0])))
        if not record_path.is_file():
            raise RuntimeError(f"RECORD missing on disk for {dist_name}: {record_path}")

        original = record_path.read_bytes()
        normalized = normalize_record_bytes(original)
        if normalized != original:
            record_path.write_bytes(normalized)
            changed.append(dist_name)
        verified.append(dist_name)

    return {
        "status": "PASS",
        "policy": "BDB_RUNTIME_RECORD_PAYLOAD_ELIGIBLE_PATHS_V1",
        "verified_distributions": verified,
        "normalized_distributions": changed,
    }


def main() -> int:
    try:
        result = normalize_installed_runtime_records()
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

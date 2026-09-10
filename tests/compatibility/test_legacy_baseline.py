from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_legacy_baseline_bytes_match_manifest() -> None:
    root = _repo_root()
    manifest = json.loads((root / "legacy/v1_4_4/LEGACY_BASELINE_MANIFEST.json").read_text(encoding="utf-8"))
    frozen = root / manifest["source"]["frozen_copy_path"]
    raw = frozen.read_bytes()
    assert len(raw) == manifest["source"]["size_bytes"]
    assert hashlib.sha256(raw).hexdigest() == manifest["source"]["sha256"]


def test_reference_copy_is_not_working_implementation_path() -> None:
    root = _repo_root()
    manifest = json.loads((root / "legacy/v1_4_4/LEGACY_BASELINE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["source"]["root_path"] != manifest["source"]["frozen_copy_path"]


def test_legacy_pin_matches_frozen_source_identity() -> None:
    root = _repo_root()
    manifest = json.loads((root / "legacy/v1_4_4/LEGACY_BASELINE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["exact_legacy_pin"]["value"] == manifest["source"]["git_commit_sha1"]
    assert manifest["source"]["git_blob_sha1"] == "37adeefe3bf91bb00f9ffa2d5c3d92aebce33bc2"


def test_retained_self_test_is_bound_to_exact_legacy_bytes() -> None:
    root = _repo_root()
    manifest = json.loads((root / "legacy/v1_4_4/LEGACY_BASELINE_MANIFEST.json").read_text(encoding="utf-8"))
    output_path = root / manifest["self_test"]["retained_output_path"]
    output_raw = output_path.read_bytes()
    assert hashlib.sha256(output_raw).hexdigest() == manifest["self_test"]["retained_output_sha256"]
    record = json.loads(output_raw)
    assert record["source_sha256"] == manifest["source"]["sha256"]
    assert record["exit_code"] == 0
    assert record["result"]["status"] == "PASS"
    assert record["result"]["errors"] == []

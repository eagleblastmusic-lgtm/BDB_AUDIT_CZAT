from __future__ import annotations

import json
from pathlib import Path

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.history_view.models import HistoricalAuditPoint, PrivacyPolicy
from bdb_audit.history_view.share import export_share_bundle, verify_share_bundle
from bdb_audit.history_view.trends import build_trends


def test_ru17_trends_require_explicit_denominator() -> None:
    with pytest.raises(ValidationError, match="HISTORICAL_DENOMINATOR_REQUIRED"):
        HistoricalAuditPoint("a1", {"sha": "a"}, "scope", "policy", finding_count=2, denominator=0)


def test_ru17_raw_count_delta_is_not_primary_metric() -> None:
    points = (
        HistoricalAuditPoint("a1", {"sha": "a"}, "scope", "policy", finding_count=2, denominator=10),
        HistoricalAuditPoint("a2", {"sha": "b"}, "scope", "policy", finding_count=3, denominator=30),
    )
    result = build_trends(points)
    comparison = result["series"][0]["comparisons"][0]
    assert comparison["raw_count_delta"] == 1
    assert comparison["raw_count_delta_is_not_primary_metric"] is True
    assert comparison["finding_rate_delta_basis_points"] < 0


def test_ru17_share_bundle_respects_privacy_and_verifies(tmp_path: Path) -> None:
    source = tmp_path / "source"; source.mkdir()
    (source / "report.json").write_text('{"ok":true}', encoding="utf-8")
    private = source / "private"; private.mkdir(); (private / "secret.txt").write_text("secret", encoding="utf-8")
    bundle = tmp_path / "bundle"
    result = export_share_bundle(
        source, bundle,
        include_paths=("report.json", "private/secret.txt"),
        privacy_policy=PrivacyPolicy(mode="REDACTED", excluded_path_prefixes=("private",)),
        source_identity={"git_commit_object_id": "a" * 40},
        history_cut={"accepted_head_seq": 1, "accepted_head_hash": "h"},
    )
    assert result["file_count"] == 1
    assert result["excluded_count"] == 1
    assert not (bundle / "private" / "secret.txt").exists()
    assert verify_share_bundle(bundle)["status"] == "PASS"


def test_ru17_external_attestation_is_never_claimed_as_verified_signature(tmp_path: Path) -> None:
    source = tmp_path / "source"; source.mkdir(); (source / "r.txt").write_text("x", encoding="utf-8")
    bundle = tmp_path / "bundle"
    export_share_bundle(
        source, bundle, include_paths=("r.txt",), privacy_policy=PrivacyPolicy(mode="PUBLIC"),
        source_identity={"git_commit_object_id": "a" * 40}, attestation_ref="external://attestation/123",
    )
    verified = verify_share_bundle(bundle)
    assert verified["attestation_status"] == "EXTERNAL_REFERENCE_UNVERIFIED"
    assert verified["cryptographic_signature_verified"] is False


def test_ru17_tampered_shared_file_fails_verification(tmp_path: Path) -> None:
    source = tmp_path / "source"; source.mkdir(); (source / "r.txt").write_text("x", encoding="utf-8")
    bundle = tmp_path / "bundle"
    export_share_bundle(source, bundle, include_paths=("r.txt",), privacy_policy=PrivacyPolicy(mode="PUBLIC"), source_identity={"sha": "a"})
    (bundle / "r.txt").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValidationError, match="SHARE_FILE_IDENTITY_MISMATCH"):
        verify_share_bundle(bundle)


def test_ru17_export_rejects_symlink_before_resolution(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    candidate = source / "link.txt"
    candidate.write_text("target", encoding="utf-8")
    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        if path == candidate:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    with pytest.raises(ValidationError, match="SHARE_SYMLINK_UNSUPPORTED"):
        export_share_bundle(
            source,
            tmp_path / "bundle",
            include_paths=("link.txt",),
            privacy_policy=PrivacyPolicy(mode="PUBLIC"),
            source_identity={"sha": "a"},
        )

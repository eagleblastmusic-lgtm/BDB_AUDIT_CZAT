from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.runner.environments import environment_manifest, source_manifest
from bdb_audit.runner.specs import CapabilityProfile, ToolRunSpec
from bdb_audit.runner.supervisor import ToolSupervisor
from bdb_audit.runner.verification import verify_run_evidence


def test_ru10_source_manifest_is_content_bound_and_ignores_vcs_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("alpha", encoding="utf-8")
    (source / ".git").mkdir()
    (source / ".git" / "noise").write_text("one", encoding="utf-8")
    first = source_manifest(source)
    (source / ".git" / "noise").write_text("two", encoding="utf-8")
    second = source_manifest(source)
    assert first["manifest_digest"] == second["manifest_digest"]
    (source / "a.txt").write_text("beta", encoding="utf-8")
    assert source_manifest(source)["manifest_digest"] != first["manifest_digest"]


def test_ru10_environment_manifest_binds_source_and_capability(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "x.py").write_text("print('x')", encoding="utf-8")
    profile = CapabilityProfile()
    manifest = environment_manifest(source, profile)
    assert manifest["capability_profile_digest"] == profile.digest
    assert manifest["source_member_count"] == 1
    assert len(manifest["source_manifest_digest"]) == 64
    assert len(manifest["manifest_digest"]) == 64


def test_ru10_evidence_verifier_detects_raw_output_tamper(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "x.txt").write_text("x", encoding="utf-8")
    evidence = tmp_path / "evidence"
    result = ToolSupervisor().run(ToolRunSpec(
        run_id="verify-tamper",
        source_root=str(source),
        evidence_dir=str(evidence),
        argv=(sys.executable, "-c", "print('verified')"),
    ))
    assert result.supervisor_status == "SUCCESS"
    assert verify_run_evidence(evidence)["status"] == "PASS"
    (evidence / "stdout.bin").write_bytes(b"tampered")
    with pytest.raises(ValidationError, match="TOOL_RUN_STDOUT_IDENTITY_MISMATCH"):
        verify_run_evidence(evidence)


def test_ru10_evidence_verifier_detects_receipt_tamper(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    evidence = tmp_path / "evidence"
    ToolSupervisor().run(ToolRunSpec(
        run_id="verify-receipt",
        source_root=str(source),
        evidence_dir=str(evidence),
        argv=(sys.executable, "-c", "print('ok')"),
    ))
    receipt_path = evidence / "RUN_RECEIPT.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["supervisor_status"] = "TIMEOUT"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValidationError, match="TOOL_RUN_RECEIPT_DIGEST_MISMATCH"):
        verify_run_evidence(evidence)

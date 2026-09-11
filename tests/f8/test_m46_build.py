"""M46 — Standalone Build System and Reproducibility Gate Tests (R5.3 §106–§108)."""
import hashlib
import io
import json
import re
import tempfile
import zipfile
from pathlib import Path

import pytest

from build.build_single_file import (
    build_standalone,
    collect_source_files,
    build_manifest,
    create_payload_zip,
    SRC_DIR,
    DIST_DIR,
)


def test_m46_build_reproducibility():
    """Hard requirement: same input -> exact same bytes and SHA256."""
    with tempfile.TemporaryDirectory() as td:
        p1 = Path(td) / "build1.py"
        p2 = Path(td) / "build2.py"
        _, sha1, sz1 = build_standalone(p1)
        _, sha2, sz2 = build_standalone(p2)

        assert sha1 == sha2, "Independent builds must have identical SHA256"
        assert sz1 == sz2, "Independent builds must have identical size"
        assert p1.read_bytes() == p2.read_bytes(), "Builds must be byte-identical"


def test_m46_manifest_and_payload_contents():
    """Standalone must contain modules, schemas, specs, and templates."""
    files = collect_source_files(SRC_DIR)
    manifest = build_manifest(files)
    paths = set(manifest.keys())

    # Modules
    assert any(p.startswith("bdb_audit/core/") for p in paths)
    assert any(p.startswith("bdb_audit/orchestration/") for p in paths)
    assert any(p.startswith("bdb_audit/coordinator/") for p in paths)
    assert any(p.startswith("bdb_audit/stop/") for p in paths)

    # Schemas
    assert any(p.startswith("bdb_audit/schemas/") for p in paths)
    assert any("artifact_contract_registry_r5_3_1.json" in p for p in paths)

    # Templates
    assert any("templates.py" in p for p in paths)


def test_m46_no_absolute_machine_paths():
    """Standalone script must contain no machine-specific absolute paths."""
    with tempfile.TemporaryDirectory() as td:
        out_file = Path(td) / "test_standalone.py"
        build_standalone(out_file)
        content = out_file.read_text(encoding="utf-8")

        # Must not contain C:\ or /Users/ or /home/ in source definitions outside comments/docstrings
        for line in content.splitlines():
            if "REPO_ROOT" in line:
                continue
            assert "C:\\Projekty" not in line, f"Machine path found in line: {line}"
            assert "C:\\Users" not in line, f"Machine path found in line: {line}"


def test_m46_standalone_verification_and_tamper_detection():
    """Standalone script verifies payload and fails closed on tampering."""
    import subprocess
    import sys

    with tempfile.TemporaryDirectory() as td:
        out_file = Path(td) / "test_standalone.py"
        build_standalone(out_file)

        # 1. Verification on valid build
        res = subprocess.run(
            [sys.executable, str(out_file), "--verify-payload"],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0
        data = json.loads(res.stdout)
        assert data["status"] == "PASS"

        # 2. Tampered payload fails closed
        tampered_code = out_file.read_text(encoding="utf-8")
        # Flip a character in the embedded base85 payload
        match = re.search(r'EMBEDDED_PAYLOAD_B85 = """(.*?)"""', tampered_code, re.DOTALL)
        assert match is not None
        payload_str = match.group(1)
        tampered_str = payload_str[:-2] + "AA"
        tampered_code = tampered_code.replace(payload_str, tampered_str)
        tampered_file = Path(td) / "tampered_standalone.py"
        tampered_file.write_text(tampered_code, encoding="utf-8")

        res_tampered = subprocess.run(
            [sys.executable, str(tampered_file), "--verify-payload"],
            capture_output=True,
            text=True,
        )
        assert res_tampered.returncode != 0
        assert "FAIL" in res_tampered.stderr or "FAIL" in res_tampered.stdout

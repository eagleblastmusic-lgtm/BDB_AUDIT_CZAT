"""M49 — Release Validator Tests with Comprehensive Negative Fixtures (R5.3 §111)."""
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import zipfile

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.release_validator import ReleaseValidator, validate_release_artifact
from build.build_single_file import build_standalone, collect_source_files, build_manifest, create_payload_zip, SRC_DIR


@pytest.fixture
def valid_standalone():
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "test_assistant.py"
        build_standalone(out_path)
        yield out_path


def test_m49_valid_standalone_passes_all_checks(valid_standalone):
    """Untampered standalone must pass all 10 release validator checks."""
    res = validate_release_artifact(valid_standalone)
    assert res["status"] == "PASS"
    for check_name, status in res["checks"].items():
        assert status == "PASS", f"Check {check_name} failed"


def test_m49_negative_wrong_sha(valid_standalone):
    """Wrong declared SHA in header must fail closed."""
    text = valid_standalone.read_text(encoding="utf-8")
    tampered_text = re.sub(r'PAYLOAD_RAW_DIGEST = ".*?"', 'PAYLOAD_RAW_DIGEST = "' + "0" * 64 + '"', text)
    with tempfile.TemporaryDirectory() as td:
        tampered_file = Path(td) / "bad_sha.py"
        tampered_file.write_text(tampered_text, encoding="utf-8")
        validator = ReleaseValidator(tampered_file)
        with pytest.raises(ValidationError, match="PAYLOAD_RAW_DIGEST_MISMATCH"):
            validator.validate_all(check_reproducibility=False)


def test_m49_negative_changed_manifest(valid_standalone):
    """Changed manifest entry must fail closed."""
    text = valid_standalone.read_text(encoding="utf-8")
    # Change sha of a file in manifest JSON
    tampered_text = text.replace('"sha256": "', '"sha256": "f' * 64)
    with tempfile.TemporaryDirectory() as td:
        tampered_file = Path(td) / "bad_manifest.py"
        tampered_file.write_text(tampered_text, encoding="utf-8")
        validator = ReleaseValidator(tampered_file)
        with pytest.raises(ValidationError):
            validator.validate_all(check_reproducibility=False)


def test_m49_negative_truncated_build(valid_standalone):
    """Truncated standalone build must fail closed."""
    raw = valid_standalone.read_bytes()
    truncated_raw = raw[: len(raw) // 2]
    with tempfile.TemporaryDirectory() as td:
        truncated_file = Path(td) / "truncated.py"
        truncated_file.write_bytes(truncated_raw)
        validator = ReleaseValidator(truncated_file)
        with pytest.raises(ValidationError):
            validator.validate_all(check_reproducibility=False)


def test_m49_negative_incompatible_payload(valid_standalone):
    """Corrupted Base85 payload must fail closed."""
    text = valid_standalone.read_text(encoding="utf-8")
    tampered_text = re.sub(r'EMBEDDED_PAYLOAD_B85 = """.*?"""', 'EMBEDDED_PAYLOAD_B85 = """!!!NOT_VALID_BASE85!!!"""', text, flags=re.DOTALL)
    with tempfile.TemporaryDirectory() as td:
        bad_b85_file = Path(td) / "bad_b85.py"
        bad_b85_file.write_text(tampered_text, encoding="utf-8")
        validator = ReleaseValidator(bad_b85_file)
        with pytest.raises(ValidationError):
            validator.validate_all(check_reproducibility=False)


def _rebuild_with_modified_file(rel_path: str, new_content: bytes, out_path: Path):
    files = collect_source_files(SRC_DIR)
    modified_files = []
    for p, data in files:
        if p == rel_path:
            modified_files.append((p, new_content))
        else:
            modified_files.append((p, data))
    
    manifest = build_manifest(modified_files)
    manifest_bytes = json.dumps(manifest, sort_keys=True, indent=2).replace("\r\n", "\n").encode("utf-8")
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    zip_data = create_payload_zip(modified_files)
    payload_digest = hashlib.sha256(zip_data).hexdigest()
    b85_str = base64.b85encode(zip_data).decode("ascii")
    manifest_json_str = json.dumps(manifest, sort_keys=True, indent=4).replace("\r\n", "\n")

    from build.build_single_file import STANDALONE_STUB_TEMPLATE, APP_VERSION, BUILD_ID
    rendered = STANDALONE_STUB_TEMPLATE.format(
        APP_VERSION=APP_VERSION,
        BUILD_ID=BUILD_ID,
        PAYLOAD_MANIFEST_DIGEST=manifest_digest,
        PAYLOAD_RAW_DIGEST=payload_digest,
        PAYLOAD_SIZE=len(zip_data),
        PAYLOAD_MANIFEST_JSON=manifest_json_str,
        EMBEDDED_PAYLOAD_B85=b85_str,
    )
    out_path.write_text(rendered.replace("\r\n", "\n"), encoding="utf-8")


def test_m49_negative_tampered_module():
    """Tampering with a core python module must fail closed during reproducibility / validation."""
    with tempfile.TemporaryDirectory() as td:
        out_p = Path(td) / "tampered_module.py"
        _rebuild_with_modified_file("bdb_audit/core/canonical_json.py", b"# TAMPERED CANONICAL MODULE\n", out_p)
        validator = ReleaseValidator(out_p)
        with pytest.raises(ValidationError):
            validator.validate_all(check_reproducibility=True)


def test_m49_negative_tampered_schema():
    """Tampering with active schema registry must fail closed."""
    with tempfile.TemporaryDirectory() as td:
        out_p = Path(td) / "tampered_schema.py"
        _rebuild_with_modified_file("bdb_audit/core/artifact_contract_registry_r5_3_1.json", b'{"registry_id": "TAMPERED"}', out_p)
        validator = ReleaseValidator(out_p)
        with pytest.raises(ValidationError):
            validator.validate_all(check_reproducibility=False)


def test_m49_negative_tampered_stagespec():
    """Tampering with StageSpec definition must fail closed."""
    with tempfile.TemporaryDirectory() as td:
        out_p = Path(td) / "tampered_stagespec.py"
        _rebuild_with_modified_file("bdb_audit/orchestration/stages.py", b"# NO STAGESPEC CLASS HERE\n", out_p)
        validator = ReleaseValidator(out_p)
        with pytest.raises(ValidationError, match="STAGESPEC_DEFINITION_MISSING"):
            validator.validate_all(check_reproducibility=False)


def test_m49_negative_tampered_lanespec():
    """Tampering with LaneSpec definition must fail closed."""
    with tempfile.TemporaryDirectory() as td:
        out_p = Path(td) / "tampered_lanespec.py"
        _rebuild_with_modified_file("bdb_audit/orchestration/runs.py", b"# NO LANESPEC CLASS HERE\n", out_p)
        validator = ReleaseValidator(out_p)
        with pytest.raises(ValidationError, match="LANESPEC_DEFINITION_MISSING"):
            validator.validate_all(check_reproducibility=False)


def test_m49_negative_tampered_template():
    """Tampering with template definitions must fail closed."""
    with tempfile.TemporaryDirectory() as td:
        out_p = Path(td) / "tampered_template.py"
        _rebuild_with_modified_file("bdb_audit/orchestration/templates.py", b"# NO CANONICAL TEMPLATES\n", out_p)
        validator = ReleaseValidator(out_p)
        with pytest.raises(ValidationError, match="TEMPLATES_DEFINITION_MISSING"):
            validator.validate_all(check_reproducibility=False)

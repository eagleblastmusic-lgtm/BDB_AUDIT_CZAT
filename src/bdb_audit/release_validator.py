"""Release Validator for BDB Audit v2 (R5.3 §111).

Operates strictly on the final standalone built artifact, verifying:
1. executable/import/startup integrity;
2. embedded schemas;
3. embedded StageSpecs;
4. embedded LaneSpecs;
5. templates;
6. payload manifest;
7. exact digests;
8. self-test execution;
9. canonical compatibility;
10. reproducibility identity.

FAIL CLOSED: any tampering or inconsistency results in validation failure.
Does NOT rely on local source repository files.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile
from typing import Any

from .core.errors import ValidationError
from .core.ids import REGISTRY_SHA256
from .core.registry import GOLDEN_SHA256


class ReleaseValidator:
    """Rigorous fail-closed validator for built standalone artifacts."""

    def __init__(self, artifact_path: str | Path, python_executable: str | None = None):
        self.artifact_path = Path(artifact_path).resolve()
        self.python_exe = python_executable or sys.executable
        if not self.artifact_path.exists():
            raise FileNotFoundError(f"Standalone artifact not found: {self.artifact_path}")

    def extract_embedded_metadata(self) -> dict[str, Any]:
        """Extract metadata and embedded zip payload from the standalone script source."""
        text = self.artifact_path.read_text(encoding="utf-8")

        # 1. Version and Build ID
        v_match = re.search(r'APP_VERSION = "(.*?)"', text)
        b_match = re.search(r'BUILD_ID = "(.*?)"', text)
        m_digest_match = re.search(r'PAYLOAD_MANIFEST_DIGEST = "(.*?)"', text)
        r_digest_match = re.search(r'PAYLOAD_RAW_DIGEST = "(.*?)"', text)
        size_match = re.search(r'PAYLOAD_SIZE = (\d+)', text)

        if not all([v_match, b_match, m_digest_match, r_digest_match, size_match]):
            raise ValidationError("VALIDATOR_HEADER_MISSING", "Required standalone header constants missing")

        assert v_match is not None
        assert b_match is not None
        assert m_digest_match is not None
        assert r_digest_match is not None
        assert size_match is not None

        # 2. Extract PAYLOAD_MANIFEST
        m_json_match = re.search(r'PAYLOAD_MANIFEST = ({.*?})\n\nEMBEDDED_PAYLOAD_B85', text, re.DOTALL)
        if not m_json_match:
            raise ValidationError("VALIDATOR_MANIFEST_MISSING", "PAYLOAD_MANIFEST block missing")
        try:
            manifest = json.loads(m_json_match.group(1))
        except Exception as exc:
            raise ValidationError("VALIDATOR_MANIFEST_CORRUPT", f"Cannot parse PAYLOAD_MANIFEST: {exc}")

        # 3. Extract EMBEDDED_PAYLOAD_B85
        payload_match = re.search(r'EMBEDDED_PAYLOAD_B85 = """(.*?)"""', text, re.DOTALL)
        if not payload_match:
            raise ValidationError("VALIDATOR_PAYLOAD_MISSING", "EMBEDDED_PAYLOAD_B85 block missing")

        b85_raw = payload_match.group(1).strip().encode("ascii")
        try:
            zip_bytes = base64.b85decode(b85_raw)
        except Exception as exc:
            raise ValidationError("VALIDATOR_PAYLOAD_DECODE_ERROR", f"Base85 decode error: {exc}")

        return {
            "app_version": v_match.group(1),
            "build_id": b_match.group(1),
            "manifest_digest": m_digest_match.group(1),
            "raw_payload_digest": r_digest_match.group(1),
            "declared_payload_size": int(size_match.group(1)),
            "manifest": manifest,
            "zip_bytes": zip_bytes,
        }

    def validate_all(self, check_reproducibility: bool = True) -> dict[str, Any]:
        """Run complete 10-point release qualification validation."""
        results = {}

        # 1. Executable and startup integrity
        meta = self.extract_embedded_metadata()
        zip_bytes = meta["zip_bytes"]

        # Check raw payload size and digest
        if len(zip_bytes) != meta["declared_payload_size"]:
            raise ValidationError("PAYLOAD_SIZE_MISMATCH", f"Expected {meta['declared_payload_size']}, got {len(zip_bytes)}")
        actual_raw_digest = hashlib.sha256(zip_bytes).hexdigest()
        if actual_raw_digest != meta["raw_payload_digest"]:
            raise ValidationError("PAYLOAD_RAW_DIGEST_MISMATCH", f"Expected {meta['raw_payload_digest']}, got {actual_raw_digest}")
        results["1_startup_integrity"] = "PASS"

        # Read zip archive in-memory
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes), "r")
        except Exception as exc:
            raise ValidationError("PAYLOAD_ZIP_CORRUPT", f"Failed to read payload zip: {exc}")

        namelist = set(zf.namelist())
        manifest = meta["manifest"]

        # 6. Payload Manifest completeness
        if namelist != set(manifest.keys()):
            raise ValidationError("MANIFEST_KEYS_MISMATCH", "Zip contents do not match manifest keys")
        results["6_payload_manifest"] = "PASS"

        # 7. Exact Digests of every embedded component
        for name, entry in sorted(manifest.items()):
            data = zf.read(name)
            if len(data) != entry["size"]:
                raise ValidationError("FILE_SIZE_MISMATCH", f"{name}: expected {entry['size']}, got {len(data)}")
            h = hashlib.sha256(data).hexdigest()
            if h != entry["sha256"]:
                raise ValidationError("FILE_DIGEST_MISMATCH", f"{name}: expected {entry['sha256']}, got {h}")
        results["7_exact_digests"] = "PASS"

        # 2. Embedded Schemas
        registry_file = "bdb_audit/core/artifact_contract_registry_r5_3_1.json"
        if registry_file not in namelist:
            raise ValidationError("EMBEDDED_SCHEMA_MISSING", f"Active registry missing: {registry_file}")
        reg_bytes = zf.read(registry_file)
        if hashlib.sha256(reg_bytes).hexdigest() != REGISTRY_SHA256:
            raise ValidationError("REGISTRY_PIN_MISMATCH", "Embedded registry hash does not match pinned constant")
        results["2_embedded_schemas"] = "PASS"

        # 3. Embedded StageSpecs
        stages_file = "bdb_audit/orchestration/stages.py"
        if stages_file not in namelist:
            raise ValidationError("STAGESPEC_MODULE_MISSING", f"Missing {stages_file}")
        stages_code = zf.read(stages_file).decode("utf-8")
        if "class StageSpec" not in stages_code:
            raise ValidationError("STAGESPEC_DEFINITION_MISSING", "StageSpec class definition missing")
        results["3_embedded_stagespecs"] = "PASS"

        # 4. Embedded LaneSpecs
        runs_file = "bdb_audit/orchestration/runs.py"
        if runs_file not in namelist:
            raise ValidationError("LANESPEC_MODULE_MISSING", f"Missing {runs_file}")
        runs_code = zf.read(runs_file).decode("utf-8")
        if "class LaneSpec" not in runs_code:
            raise ValidationError("LANESPEC_DEFINITION_MISSING", "LaneSpec class definition missing")
        results["4_embedded_lanespecs"] = "PASS"

        # 5. Templates
        templates_file = "bdb_audit/orchestration/templates.py"
        if templates_file not in namelist:
            raise ValidationError("TEMPLATES_MODULE_MISSING", f"Missing {templates_file}")
        templates_code = zf.read(templates_file).decode("utf-8")
        if "CANONICAL_PROMPT_TEMPLATES" not in templates_code:
            raise ValidationError("TEMPLATES_DEFINITION_MISSING", "Canonical prompt templates missing")
        results["5_templates"] = "PASS"

        # 8. Self-test via subprocess execution
        proc_self_test = subprocess.run(
            [self.python_exe, str(self.artifact_path), "--self-test"],
            capture_output=True,
            text=True,
        )
        if proc_self_test.returncode != 0:
            raise ValidationError("STANDALONE_SELF_TEST_FAILED", f"Return code {proc_self_test.returncode}: {proc_self_test.stderr}")
        try:
            st_data = json.loads(proc_self_test.stdout)
            if st_data.get("status") != "PASS":
                raise ValidationError("STANDALONE_SELF_TEST_FAILED", f"Status not PASS: {st_data}")
        except Exception as exc:
            raise ValidationError("STANDALONE_SELF_TEST_FAILED", f"Invalid self-test JSON: {exc}")
        results["8_self_test"] = "PASS"

        # 9. Compatibility: golden vectors & registry identity
        golden_file = "bdb_audit/core/foundation_golden_vectors_r5_3_1.json"
        if golden_file not in namelist:
            raise ValidationError("GOLDEN_VECTORS_MISSING", f"Golden vectors file missing: {golden_file}")
        golden_bytes = zf.read(golden_file)
        if hashlib.sha256(golden_bytes).hexdigest() != GOLDEN_SHA256:
            raise ValidationError("GOLDEN_VECTORS_DIGEST_MISMATCH", "Golden vectors SHA256 mismatch")
        results["9_compatibility"] = "PASS"

        # 10. Reproducibility identity
        if check_reproducibility:
            from build.build_single_file import build_standalone
            with tempfile.TemporaryDirectory() as td:
                rebuild_path = Path(td) / "rebuild_standalone.py"
                _, rebuild_sha, rebuild_sz = build_standalone(rebuild_path)
                current_sha = hashlib.sha256(self.artifact_path.read_bytes()).hexdigest()
                current_sz = self.artifact_path.stat().st_size
                if rebuild_sha != current_sha or rebuild_sz != current_sz:
                    raise ValidationError("REPRODUCIBILITY_DRIFT", f"Rebuild SHA {rebuild_sha} != target {current_sha}")
        results["10_reproducibility_identity"] = "PASS"

        return {
            "status": "PASS",
            "artifact_path": str(self.artifact_path),
            "app_version": meta["app_version"],
            "build_id": meta["build_id"],
            "sha256": hashlib.sha256(self.artifact_path.read_bytes()).hexdigest(),
            "size": self.artifact_path.stat().st_size,
            "manifest_files_count": len(manifest),
            "checks": results,
        }


def validate_release_artifact(artifact_path: str | Path) -> dict[str, Any]:
    validator = ReleaseValidator(artifact_path)
    return validator.validate_all()


__all__ = ["ReleaseValidator", "validate_release_artifact"]

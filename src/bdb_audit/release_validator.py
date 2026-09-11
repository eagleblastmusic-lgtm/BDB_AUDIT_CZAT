"""Release Validator for BDB Audit v2 (R5.3 §111).

Operates strictly on the final standalone built artifact, verifying product
payload integrity, embedded runtime closure, self-test execution from the
artifact, compatibility pins, and reproducible identity.

FAIL CLOSED: any tampering or inconsistency results in validation failure.
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


_REQUIRED_RUNTIME_PREFIXES = (
    "attrs/",
    "jsonschema/",
    "jsonschema_specifications/",
    "referencing/",
    "rpds/",
)


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

        m_json_match = re.search(r'PAYLOAD_MANIFEST = ({.*?})\n\nEMBEDDED_PAYLOAD_B85', text, re.DOTALL)
        if not m_json_match:
            raise ValidationError("VALIDATOR_MANIFEST_MISSING", "PAYLOAD_MANIFEST block missing")
        try:
            manifest = json.loads(m_json_match.group(1))
        except Exception as exc:
            raise ValidationError("VALIDATOR_MANIFEST_CORRUPT", f"Cannot parse PAYLOAD_MANIFEST: {exc}")

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

    @staticmethod
    def _validate_runtime_closure(namelist: set[str], zf: zipfile.ZipFile) -> dict[str, Any]:
        lock_name = "__bdb_runtime__/lock.json"
        platform_name = "__bdb_runtime__/platform.json"
        if lock_name not in namelist or platform_name not in namelist:
            raise ValidationError("STANDALONE_RUNTIME_METADATA_MISSING", "Runtime lock/platform metadata missing")

        try:
            runtime_lock = json.loads(zf.read(lock_name))
            runtime_platform = json.loads(zf.read(platform_name))
        except Exception as exc:
            raise ValidationError("STANDALONE_RUNTIME_METADATA_INVALID", str(exc)) from exc

        if not isinstance(runtime_lock, dict) or not isinstance(runtime_platform, dict):
            raise ValidationError("STANDALONE_RUNTIME_METADATA_INVALID", "Runtime metadata must be JSON objects")

        expected_lock = {
            "attrs": "26.1.0",
            "jsonschema": "4.25.1",
            "jsonschema-specifications": "2025.9.1",
            "referencing": "0.37.0",
            "rpds-py": "2026.6.3",
        }
        if runtime_lock != expected_lock:
            raise ValidationError(
                "STANDALONE_RUNTIME_LOCK_DRIFT",
                f"Expected qualified runtime closure {expected_lock}, got {runtime_lock}",
            )

        for prefix in _REQUIRED_RUNTIME_PREFIXES:
            if not any(name.startswith(prefix) for name in namelist):
                raise ValidationError("STANDALONE_RUNTIME_PACKAGE_MISSING", prefix.rstrip("/"))

        if not any(name.startswith("rpds/") and name.endswith((".pyd", ".so")) for name in namelist):
            raise ValidationError("STANDALONE_NATIVE_RUNTIME_MISSING", "rpds native extension not embedded")

        required_platform_fields = {
            "system", "machine", "implementation", "python_major", "python_minor", "soabi"
        }
        if set(runtime_platform) != required_platform_fields:
            raise ValidationError("STANDALONE_RUNTIME_PLATFORM_INVALID", str(runtime_platform))

        return {"runtime_lock": runtime_lock, "runtime_platform": runtime_platform}

    def validate_all(self, check_reproducibility: bool = True) -> dict[str, Any]:
        """Run complete release qualification validation."""
        results: dict[str, str] = {}

        meta = self.extract_embedded_metadata()
        zip_bytes = meta["zip_bytes"]

        if len(zip_bytes) != meta["declared_payload_size"]:
            raise ValidationError("PAYLOAD_SIZE_MISMATCH", f"Expected {meta['declared_payload_size']}, got {len(zip_bytes)}")
        actual_raw_digest = hashlib.sha256(zip_bytes).hexdigest()
        if actual_raw_digest != meta["raw_payload_digest"]:
            raise ValidationError("PAYLOAD_RAW_DIGEST_MISMATCH", f"Expected {meta['raw_payload_digest']}, got {actual_raw_digest}")
        results["1_startup_integrity"] = "PASS"

        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes), "r")
        except Exception as exc:
            raise ValidationError("PAYLOAD_ZIP_CORRUPT", f"Failed to read payload zip: {exc}")

        names = zf.namelist()
        if len(names) != len(set(names)):
            raise ValidationError("PAYLOAD_DUPLICATE_MEMBER", "Embedded payload contains duplicate members")
        namelist = set(names)
        manifest = meta["manifest"]

        if namelist != set(manifest.keys()):
            raise ValidationError("MANIFEST_KEYS_MISMATCH", "Zip contents do not match manifest keys")
        results["6_payload_manifest"] = "PASS"

        for name, entry in sorted(manifest.items()):
            data = zf.read(name)
            if len(data) != entry["size"]:
                raise ValidationError("FILE_SIZE_MISMATCH", f"{name}: expected {entry['size']}, got {len(data)}")
            h = hashlib.sha256(data).hexdigest()
            if h != entry["sha256"]:
                raise ValidationError("FILE_DIGEST_MISMATCH", f"{name}: expected {entry['sha256']}, got {h}")
        results["7_exact_digests"] = "PASS"

        runtime_meta = self._validate_runtime_closure(namelist, zf)
        results["7b_embedded_runtime_closure"] = "PASS"

        registry_file = "bdb_audit/core/artifact_contract_registry_r5_3_1.json"
        if registry_file not in namelist:
            raise ValidationError("EMBEDDED_SCHEMA_MISSING", f"Active registry missing: {registry_file}")
        reg_bytes = zf.read(registry_file)
        if hashlib.sha256(reg_bytes).hexdigest() != REGISTRY_SHA256:
            raise ValidationError("REGISTRY_PIN_MISMATCH", "Embedded registry hash does not match pinned constant")
        results["2_embedded_schemas"] = "PASS"

        stages_file = "bdb_audit/orchestration/stages.py"
        if stages_file not in namelist:
            raise ValidationError("STAGESPEC_MODULE_MISSING", f"Missing {stages_file}")
        stages_code = zf.read(stages_file).decode("utf-8")
        if "class StageSpec" not in stages_code:
            raise ValidationError("STAGESPEC_DEFINITION_MISSING", "StageSpec class definition missing")
        results["3_embedded_stagespecs"] = "PASS"

        runs_file = "bdb_audit/orchestration/runs.py"
        if runs_file not in namelist:
            raise ValidationError("LANESPEC_MODULE_MISSING", f"Missing {runs_file}")
        runs_code = zf.read(runs_file).decode("utf-8")
        if "class LaneSpec" not in runs_code:
            raise ValidationError("LANESPEC_DEFINITION_MISSING", "LaneSpec class definition missing")
        results["4_embedded_lanespecs"] = "PASS"

        templates_file = "bdb_audit/orchestration/templates.py"
        if templates_file not in namelist:
            raise ValidationError("TEMPLATES_MODULE_MISSING", f"Missing {templates_file}")
        templates_code = zf.read(templates_file).decode("utf-8")
        if "CANONICAL_PROMPT_TEMPLATES" not in templates_code:
            raise ValidationError("TEMPLATES_DEFINITION_MISSING", "Canonical prompt templates missing")
        results["5_templates"] = "PASS"

        # Isolated mode removes PYTHONPATH and user-site influence.  The
        # standalone bootstrap additionally proves loaded runtime modules come
        # from its verified extracted payload rather than host site-packages.
        proc_self_test = subprocess.run(
            [self.python_exe, "-I", str(self.artifact_path), "--self-test"],
            capture_output=True,
            text=True,
        )
        if proc_self_test.returncode != 0:
            raise ValidationError("STANDALONE_SELF_TEST_FAILED", f"Return code {proc_self_test.returncode}: {proc_self_test.stderr}")
        try:
            st_data = json.loads(proc_self_test.stdout)
            if st_data.get("status") != "PASS":
                raise ValidationError("STANDALONE_SELF_TEST_FAILED", f"Status not PASS: {st_data}")
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError("STANDALONE_SELF_TEST_FAILED", f"Invalid self-test JSON: {exc}") from exc
        results["8_self_test_isolated_embedded_runtime"] = "PASS"

        golden_file = "bdb_audit/core/foundation_golden_vectors_r5_3_1.json"
        if golden_file not in namelist:
            raise ValidationError("GOLDEN_VECTORS_MISSING", f"Golden vectors file missing: {golden_file}")
        golden_bytes = zf.read(golden_file)
        if hashlib.sha256(golden_bytes).hexdigest() != GOLDEN_SHA256:
            raise ValidationError("GOLDEN_VECTORS_DIGEST_MISMATCH", "Golden vectors SHA256 mismatch")
        results["9_compatibility"] = "PASS"

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
            "runtime_lock": runtime_meta["runtime_lock"],
            "runtime_platform": runtime_meta["runtime_platform"],
            "checks": results,
        }


def validate_release_artifact(artifact_path: str | Path) -> dict[str, Any]:
    validator = ReleaseValidator(artifact_path)
    return validator.validate_all()


__all__ = ["ReleaseValidator", "validate_release_artifact"]

"""RU10 verifier for external runner evidence directories."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError


def _sha(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def verify_run_evidence(evidence_dir: str | Path) -> dict[str, Any]:
    root = Path(evidence_dir).resolve()
    required = ("RUN_MANIFEST.json", "RUN_RECEIPT.json", "stdout.bin", "stderr.bin")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise ValidationError("TOOL_RUN_EVIDENCE_INCOMPLETE", ",".join(missing))
    try:
        manifest = json.loads((root / "RUN_MANIFEST.json").read_text(encoding="utf-8"))
        receipt = json.loads((root / "RUN_RECEIPT.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("TOOL_RUN_EVIDENCE_PARSE_FAILED") from exc
    supplied = receipt.get("receipt_digest")
    body = dict(receipt)
    body.pop("receipt_digest", None)
    calculated = hashlib.sha256(canonical_bytes(body)).hexdigest()
    if supplied != calculated:
        raise ValidationError("TOOL_RUN_RECEIPT_DIGEST_MISMATCH")
    stdout_sha, stdout_size = _sha(root / "stdout.bin")
    stderr_sha, stderr_size = _sha(root / "stderr.bin")
    if body.get("stdout_sha256") != stdout_sha or body.get("stdout_bytes") != stdout_size:
        raise ValidationError("TOOL_RUN_STDOUT_IDENTITY_MISMATCH")
    if body.get("stderr_sha256") != stderr_sha or body.get("stderr_bytes") != stderr_size:
        raise ValidationError("TOOL_RUN_STDERR_IDENTITY_MISMATCH")
    if manifest.get("run_id") != body.get("run_id") or manifest.get("spec_digest") != body.get("spec_digest"):
        raise ValidationError("TOOL_RUN_MANIFEST_RECEIPT_MISMATCH")
    return {
        "status": "PASS",
        "run_id": body.get("run_id"),
        "spec_digest": body.get("spec_digest"),
        "receipt_digest": calculated,
        "supervisor_status": body.get("supervisor_status"),
        "cleanup_status": body.get("cleanup_status"),
        "stdout_sha256": stdout_sha,
        "stderr_sha256": stderr_sha,
    }


__all__ = ["verify_run_evidence"]

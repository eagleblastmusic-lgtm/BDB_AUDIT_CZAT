#!/usr/bin/env python3
"""Deterministic Standalone Build System for BDB Audit v2 (R5.3 §106–§108).

Assembles the single-file distribution:
    dist/BDB_AUDIT_ASSISTANT_v2.0.0.py

Embeds:
- modules (all bdb_audit packages)
- schemas (registry + schema definitions)
- StageSpecs (canonical stage definitions)
- LaneSpecs (canonical lane definitions)
- templates (prompt/report templates)
- manifest of exact file digests

Guarantees:
- deterministic file ordering (sorted POSIX paths);
- deterministic serialization (canonical JSON & normalized line endings LF);
- deterministic timestamps in archive;
- no absolute machine paths in output;
- no nondeterministic temp names;
- fail-closed digest verification.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
DIST_DIR = REPO_ROOT / "dist"
DEFAULT_OUTPUT_NAME = "BDB_AUDIT_ASSISTANT_v2.0.0.py"
APP_VERSION = "2.0.0"
BUILD_ID = "BDB-V2-STANDALONE-2.0.0"
FIXED_ZIP_DATETIME = (2026, 9, 11, 0, 0, 0)


def collect_source_files(src_root: Path) -> list[tuple[str, bytes]]:
    """Collect all source and data files under src_root in deterministic order."""
    collected: list[tuple[str, bytes]] = []
    base_path = src_root.resolve()
    
    # Walk and collect
    all_files: list[Path] = []
    for root, dirs, files in os.walk(base_path):
        dirs.sort()  # deterministic traversal
        for f in sorted(files):
            if f.endswith(".pyc") or f == "__pycache__":
                continue
            all_files.append(Path(root) / f)

    all_files.sort(key=lambda p: str(p.relative_to(base_path)).replace("\\", "/"))

    for file_path in all_files:
        rel_posix = str(file_path.relative_to(base_path)).replace("\\", "/")
        raw_bytes = file_path.read_bytes()
        # Normalize text line endings to LF for byte-identical determinism
        if file_path.suffix in (".py", ".json", ".txt", ".md"):
            try:
                text = raw_bytes.decode("utf-8")
                text = text.replace("\r\n", "\n").replace("\r", "\n")
                raw_bytes = text.encode("utf-8")
            except UnicodeDecodeError:
                pass
        collected.append((rel_posix, raw_bytes))

    return collected


def build_manifest(files: list[tuple[str, bytes]]) -> dict[str, dict[str, int | str]]:
    """Construct deterministic manifest of embedded files."""
    manifest = {}
    for rel_path, data in sorted(files, key=lambda x: x[0]):
        manifest[rel_path] = {
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return manifest


def create_payload_zip(files: list[tuple[str, bytes]]) -> bytes:
    """Create reproducible zip archive in-memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel_path, data in sorted(files, key=lambda x: x[0]):
            zinfo = zipfile.ZipInfo(rel_path, date_time=FIXED_ZIP_DATETIME)
            zinfo.external_attr = 0o644 << 16
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zinfo, data)
    return buf.getvalue()


STANDALONE_STUB_TEMPLATE = '''#!/usr/bin/env python3
"""BDB Audit Assistant v2.0.0 — Standalone Distribution (R5.3 §106–§111).

Single-file launcher containing the complete BDB Audit v2 engine, schemas,
specs, and templates with self-verifying embedded payload integrity.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
import zipfile

APP_VERSION = "{APP_VERSION}"
BUILD_ID = "{BUILD_ID}"
PAYLOAD_MANIFEST_DIGEST = "{PAYLOAD_MANIFEST_DIGEST}"
PAYLOAD_RAW_DIGEST = "{PAYLOAD_RAW_DIGEST}"
PAYLOAD_SIZE = {PAYLOAD_SIZE}

PAYLOAD_MANIFEST = {PAYLOAD_MANIFEST_JSON}

EMBEDDED_PAYLOAD_B85 = """{EMBEDDED_PAYLOAD_B85}"""


class PayloadIntegrityError(Exception):
    """Raised when embedded payload or components fail digest verification."""
    pass


def get_payload_bytes() -> bytes:
    """Decode embedded payload and verify raw payload SHA-256."""
    raw = base64.b85decode(EMBEDDED_PAYLOAD_B85.strip().encode("ascii"))
    if len(raw) != PAYLOAD_SIZE:
        raise PayloadIntegrityError(f"Payload size mismatch: expected {{PAYLOAD_SIZE}}, got {{len(raw)}}")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PAYLOAD_RAW_DIGEST:
        raise PayloadIntegrityError(f"Payload digest mismatch: expected {{PAYLOAD_RAW_DIGEST}}, got {{digest}}")
    return raw


def verify_embedded_payload(verbose: bool = False) -> dict[str, str]:
    """Verify all embedded components against PAYLOAD_MANIFEST."""
    raw = get_payload_bytes()
    verified: dict[str, str] = {{}}
    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
        namelist = set(zf.namelist())
        manifest_keys = set(PAYLOAD_MANIFEST.keys())
        if namelist != manifest_keys:
            diff = namelist.symmetric_difference(manifest_keys)
            raise PayloadIntegrityError(f"Payload manifest key mismatch: {{diff}}")
        
        for name in sorted(manifest_keys):
            entry = PAYLOAD_MANIFEST[name]
            data = zf.read(name)
            if len(data) != entry["size"]:
                raise PayloadIntegrityError(f"File {{name}} size mismatch: expected {{entry['size']}}, got {{len(data)}}")
            digest = hashlib.sha256(data).hexdigest()
            if digest != entry["sha256"]:
                raise PayloadIntegrityError(f"File {{name}} digest mismatch: expected {{entry['sha256']}}, got {{digest}}")
            verified[name] = digest
            if verbose:
                print(f"VERIFIED: {{name}} -> {{digest[:16]}}...")
    return verified


def get_embedded_resource(rel_path: str) -> bytes:
    """Retrieve raw bytes of an embedded resource directly from payload."""
    posix_path = str(PurePosixPath(rel_path)).replace("\\\\", "/")
    if posix_path not in PAYLOAD_MANIFEST:
        raise KeyError(f"Resource not found in embedded payload: {{posix_path}}")
    raw = get_payload_bytes()
    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
        return zf.read(posix_path)


def unpack_payload(target_dir: Path | None = None) -> Path:
    """Unpack payload to deterministic content-addressed directory."""
    if target_dir is None:
        target_dir = Path(tempfile.gettempdir()) / f"bdb_audit_v2_{{PAYLOAD_MANIFEST_DIGEST[:16]}}"
    
    target_dir = Path(target_dir).resolve()
    marker_file = target_dir / ".bdb_payload_verified"
    
    if marker_file.exists():
        try:
            if marker_file.read_text().strip() == PAYLOAD_MANIFEST_DIGEST:
                return target_dir
        except Exception:
            pass

    raw = get_payload_bytes()
    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
        for name in zf.namelist():
            entry = PAYLOAD_MANIFEST[name]
            out_file = target_dir / name
            out_file.parent.mkdir(parents=True, exist_ok=True)
            data = zf.read(name)
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise PayloadIntegrityError(f"Integrity check failed during unpack for {{name}}")
            out_file.write_bytes(data)

    marker_file.write_text(PAYLOAD_MANIFEST_DIGEST)
    return target_dir


def bootstrap_environment() -> None:
    """Ensure bdb_audit package is importable."""
    try:
        import bdb_audit
        return
    except ImportError:
        pass

    extracted_dir = unpack_payload()
    if str(extracted_dir) not in sys.path:
        sys.path.insert(0, str(extracted_dir))
    import bdb_audit


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point for standalone executable."""
    if argv is None:
        argv = sys.argv[1:]

    # Early flags that do not require unpacking
    if "--version" in argv:
        print(f"BDB Audit v{{APP_VERSION}} (Standalone {{BUILD_ID}})")
        return 0

    if "--verify-payload" in argv:
        try:
            verified = verify_embedded_payload(verbose="-v" in argv or "--verbose" in argv)
            print(json.dumps({{
                "status": "PASS",
                "app_version": APP_VERSION,
                "build_id": BUILD_ID,
                "payload_manifest_digest": PAYLOAD_MANIFEST_DIGEST,
                "verified_files_count": len(verified),
            }}, indent=2))
            return 0
        except Exception as exc:
            print(json.dumps({{
                "status": "FAIL",
                "error": str(exc),
            }}, indent=2), file=sys.stderr)
            return 1

    if "--self-test" in argv or "self-test" in argv:
        try:
            bootstrap_environment()
            from bdb_audit.coordinator.operations import AuditOperationApi
            api = AuditOperationApi()
            result = api.run_self_test()
            print(json.dumps(result, indent=2))
            return 0 if result.get("status") == "PASS" else 1
        except Exception as exc:
            print(f"SELF_TEST_FAILED: {{exc}}", file=sys.stderr)
            return 1

    # Standard CLI invocation
    bootstrap_environment()
    from bdb_audit.cli import run_cli
    return run_cli(argv)


if __name__ == "__main__":
    sys.exit(main())
'''


def build_standalone(output_path: Path | None = None) -> tuple[Path, str, int]:
    """Execute deterministic standalone build and return (path, sha256, size)."""
    if output_path is None:
        DIST_DIR.mkdir(parents=True, exist_ok=True)
        output_path = DIST_DIR / DEFAULT_OUTPUT_NAME
    else:
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

    files = collect_source_files(SRC_DIR)
    manifest = build_manifest(files)
    
    # Canonical manifest digest
    manifest_bytes = json.dumps(manifest, sort_keys=True, indent=2).replace("\r\n", "\n").encode("utf-8")
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()

    # Create deterministic zip
    zip_data = create_payload_zip(files)
    payload_digest = hashlib.sha256(zip_data).hexdigest()
    payload_size = len(zip_data)

    # Encode to base85
    b85_str = base64.b85encode(zip_data).decode("ascii")

    # Generate output script
    manifest_json_str = json.dumps(manifest, sort_keys=True, indent=4)
    manifest_json_str = manifest_json_str.replace("\r\n", "\n")

    rendered = STANDALONE_STUB_TEMPLATE.format(
        APP_VERSION=APP_VERSION,
        BUILD_ID=BUILD_ID,
        PAYLOAD_MANIFEST_DIGEST=manifest_digest,
        PAYLOAD_RAW_DIGEST=payload_digest,
        PAYLOAD_SIZE=payload_size,
        PAYLOAD_MANIFEST_JSON=manifest_json_str,
        EMBEDDED_PAYLOAD_B85=b85_str,
    )

    # Ensure strictly LF line endings in generated script
    rendered_clean = rendered.replace("\r\n", "\n")
    script_bytes = rendered_clean.encode("utf-8")

    output_path.write_bytes(script_bytes)
    script_sha256 = hashlib.sha256(script_bytes).hexdigest()
    script_size = len(script_bytes)

    return output_path, script_sha256, script_size


def main() -> int:
    out_path, sha, sz = build_standalone()
    print(f"BUILD_SUCCESS: {out_path} ({sz} bytes, SHA256: {sha})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

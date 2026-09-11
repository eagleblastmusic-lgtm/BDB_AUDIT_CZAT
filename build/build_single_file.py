#!/usr/bin/env python3
"""Deterministic standalone build system for BDB Audit v2.

The v2.0.1 patch artifact embeds both the BDB Audit source payload and the
qualified third-party runtime closure from ``requirements-f2.lock``.  The
resulting single-file script must therefore start on a clean compatible Python
installation without using repository ``src/``, a project virtualenv, user
site-packages, or a prior ``pip install`` of the validator dependencies.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import sys
import sysconfig
import zipfile

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
DIST_DIR = REPO_ROOT / "dist"
RUNTIME_LOCK_PATH = REPO_ROOT / "requirements-f2.lock"
DEFAULT_OUTPUT_NAME = "BDB_AUDIT_ASSISTANT_v2.0.1.py"
APP_VERSION = "2.0.1"
BUILD_ID = "BDB-V2-STANDALONE-2.0.1"
FIXED_ZIP_DATETIME = (2026, 9, 11, 0, 0, 0)
_RUNTIME_META_PREFIX = "__bdb_runtime__"


def _normalized_arch(value: str) -> str:
    arch = value.strip().lower()
    if arch in {"amd64", "x86_64", "x64"}:
        return "x86_64"
    if arch in {"aarch64", "arm64"}:
        return "arm64"
    return arch


def runtime_platform_identity() -> dict[str, object]:
    """Return the exact interpreter/platform identity bound to native wheels."""
    return {
        "system": platform.system().strip().lower(),
        "machine": _normalized_arch(platform.machine()),
        "implementation": sys.implementation.name,
        "python_major": sys.version_info.major,
        "python_minor": sys.version_info.minor,
        "soabi": sysconfig.get_config_var("SOABI") or "",
    }


def parse_runtime_lock(lock_path: Path = RUNTIME_LOCK_PATH) -> dict[str, str]:
    """Parse the exact qualified runtime closure from the pinned lock file."""
    if not lock_path.exists():
        raise RuntimeError(f"Runtime lock missing: {lock_path}")
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
        key = name.lower().replace("_", "-")
        if key in requirements and requirements[key] != version:
            raise RuntimeError(f"Conflicting runtime lock pins for {name}")
        requirements[key] = version
    if not requirements:
        raise RuntimeError("Runtime lock contains no packages")
    return dict(sorted(requirements.items()))


def _safe_relative_path(value: str) -> str | None:
    """Return a normalized site-packages-relative path, excluding outer scripts."""
    normalized = value.replace("\\", "/")
    parts = tuple(part for part in normalized.split("/") if part not in ("", "."))
    if not parts or normalized.startswith("/") or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def _normalize_source_bytes(path: Path, raw_bytes: bytes) -> bytes:
    if path.suffix in (".py", ".json", ".txt", ".md"):
        try:
            text = raw_bytes.decode("utf-8")
            return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        except UnicodeDecodeError:
            pass
    return raw_bytes


def collect_source_files(src_root: Path) -> list[tuple[str, bytes]]:
    """Collect all BDB source/data files in deterministic order."""
    collected: list[tuple[str, bytes]] = []
    base_path = src_root.resolve()
    all_files: list[Path] = []
    for root, dirs, files in os.walk(base_path):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for filename in sorted(files):
            if filename.endswith((".pyc", ".pyo")):
                continue
            all_files.append(Path(root) / filename)

    all_files.sort(key=lambda p: str(p.relative_to(base_path)).replace("\\", "/"))
    for file_path in all_files:
        rel_posix = str(file_path.relative_to(base_path)).replace("\\", "/")
        raw_bytes = _normalize_source_bytes(file_path, file_path.read_bytes())
        collected.append((rel_posix, raw_bytes))
    return collected


def collect_runtime_files(requirements: dict[str, str] | None = None) -> list[tuple[str, bytes]]:
    """Collect exact installed files for every pinned runtime distribution.

    Native extension modules (for example rpds ``.pyd``/``.so`` files) are
    intentionally retained.  Console scripts installed outside site-packages
    are excluded because they are not import-time runtime dependencies.
    """
    requirements = requirements or parse_runtime_lock()
    collected: dict[str, bytes] = {}

    for dist_name, expected_version in sorted(requirements.items()):
        try:
            dist = importlib.metadata.distribution(dist_name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                f"Required runtime distribution {dist_name}=={expected_version} is not installed in the build interpreter"
            ) from exc
        if dist.version != expected_version:
            raise RuntimeError(
                f"Runtime distribution drift for {dist_name}: expected {expected_version}, got {dist.version}"
            )
        dist_files = dist.files
        if not dist_files:
            raise RuntimeError(f"Distribution {dist_name} exposes no installed file manifest")

        retained = 0
        for package_path in sorted(dist_files, key=lambda p: str(p).replace("\\", "/")):
            rel = _safe_relative_path(str(package_path))
            if rel is None:
                # RECORD may list ../../../Scripts/* console entry points.  They
                # are outside the import runtime and must never escape payload root.
                continue
            if rel.endswith((".pyc", ".pyo")) or "/__pycache__/" in f"/{rel}/":
                continue
            located = Path(dist.locate_file(package_path))
            if not located.is_file():
                continue
            data = located.read_bytes()
            previous = collected.get(rel)
            if previous is not None and previous != data:
                raise RuntimeError(f"Conflicting runtime payload path: {rel}")
            collected[rel] = data
            retained += 1
        if retained == 0:
            raise RuntimeError(f"Distribution {dist_name} contributed no safe runtime files")

    return sorted(collected.items(), key=lambda item: item[0])


def _runtime_metadata_files(requirements: dict[str, str]) -> list[tuple[str, bytes]]:
    lock_doc = json.dumps(requirements, sort_keys=True, separators=(",", ":")).encode("utf-8")
    platform_doc = json.dumps(runtime_platform_identity(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return [
        (f"{_RUNTIME_META_PREFIX}/lock.json", lock_doc),
        (f"{_RUNTIME_META_PREFIX}/platform.json", platform_doc),
    ]


def collect_build_files(src_root: Path = SRC_DIR) -> list[tuple[str, bytes]]:
    """Collect the complete standalone payload: product + exact runtime closure."""
    requirements = parse_runtime_lock()
    files = collect_source_files(src_root)
    files.extend(collect_runtime_files(requirements))
    files.extend(_runtime_metadata_files(requirements))

    deduped: dict[str, bytes] = {}
    for rel_path, data in files:
        previous = deduped.get(rel_path)
        if previous is not None and previous != data:
            raise RuntimeError(f"Duplicate standalone payload path with different bytes: {rel_path}")
        deduped[rel_path] = data
    return sorted(deduped.items(), key=lambda item: item[0])


def build_manifest(files: list[tuple[str, bytes]]) -> dict[str, dict[str, int | str]]:
    """Construct deterministic manifest of embedded files."""
    manifest: dict[str, dict[str, int | str]] = {}
    for rel_path, data in sorted(files, key=lambda x: x[0]):
        if rel_path in manifest:
            raise RuntimeError(f"Duplicate manifest path: {rel_path}")
        manifest[rel_path] = {
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return manifest


def create_payload_zip(files: list[tuple[str, bytes]]) -> bytes:
    """Create reproducible ZIP bytes from an already deterministic payload."""
    buf = io.BytesIO()
    seen: set[str] = set()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel_path, data in sorted(files, key=lambda x: x[0]):
            if rel_path in seen:
                raise RuntimeError(f"Duplicate ZIP payload path: {rel_path}")
            seen.add(rel_path)
            zinfo = zipfile.ZipInfo(rel_path, date_time=FIXED_ZIP_DATETIME)
            zinfo.external_attr = 0o644 << 16
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zinfo, data)
    return buf.getvalue()


STANDALONE_STUB_TEMPLATE = '''#!/usr/bin/env python3
"""BDB Audit Assistant v2.0.1 — self-contained standalone distribution."""
from __future__ import annotations

import base64
import hashlib
import importlib
import io
import json
import platform
from pathlib import Path, PurePosixPath
import sys
import sysconfig
import tempfile
import zipfile

APP_VERSION = "{APP_VERSION}"
BUILD_ID = "{BUILD_ID}"
PAYLOAD_MANIFEST_DIGEST = "{PAYLOAD_MANIFEST_DIGEST}"
PAYLOAD_RAW_DIGEST = "{PAYLOAD_RAW_DIGEST}"
PAYLOAD_SIZE = {PAYLOAD_SIZE}
RUNTIME_META_PREFIX = "__bdb_runtime__"

PAYLOAD_MANIFEST = {PAYLOAD_MANIFEST_JSON}

EMBEDDED_PAYLOAD_B85 = """{EMBEDDED_PAYLOAD_B85}"""


class PayloadIntegrityError(Exception):
    pass


def _normalized_arch(value: str) -> str:
    arch = value.strip().lower()
    if arch in {{"amd64", "x86_64", "x64"}}:
        return "x86_64"
    if arch in {{"aarch64", "arm64"}}:
        return "arm64"
    return arch


def _current_runtime_platform() -> dict[str, object]:
    return {{
        "system": platform.system().strip().lower(),
        "machine": _normalized_arch(platform.machine()),
        "implementation": sys.implementation.name,
        "python_major": sys.version_info.major,
        "python_minor": sys.version_info.minor,
        "soabi": sysconfig.get_config_var("SOABI") or "",
    }}


def get_payload_bytes() -> bytes:
    raw = base64.b85decode(EMBEDDED_PAYLOAD_B85.strip().encode("ascii"))
    if len(raw) != PAYLOAD_SIZE:
        raise PayloadIntegrityError(f"Payload size mismatch: expected {{PAYLOAD_SIZE}}, got {{len(raw)}}")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PAYLOAD_RAW_DIGEST:
        raise PayloadIntegrityError(f"Payload digest mismatch: expected {{PAYLOAD_RAW_DIGEST}}, got {{digest}}")
    return raw


def verify_embedded_payload(verbose: bool = False) -> dict[str, str]:
    raw = get_payload_bytes()
    verified: dict[str, str] = {{}}
    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            raise PayloadIntegrityError("Payload contains duplicate archive members")
        namelist = set(names)
        manifest_keys = set(PAYLOAD_MANIFEST.keys())
        if namelist != manifest_keys:
            diff = namelist.symmetric_difference(manifest_keys)
            raise PayloadIntegrityError(f"Payload manifest key mismatch: {{sorted(diff)}}")
        for name in sorted(manifest_keys):
            entry = PAYLOAD_MANIFEST[name]
            data = zf.read(name)
            if len(data) != entry["size"]:
                raise PayloadIntegrityError(f"File {{name}} size mismatch")
            digest = hashlib.sha256(data).hexdigest()
            if digest != entry["sha256"]:
                raise PayloadIntegrityError(f"File {{name}} digest mismatch")
            verified[name] = digest
            if verbose:
                print(f"VERIFIED: {{name}} -> {{digest[:16]}}...")
    return verified


def get_embedded_resource(rel_path: str) -> bytes:
    posix_path = str(PurePosixPath(rel_path)).replace("\\\\", "/")
    if posix_path not in PAYLOAD_MANIFEST:
        raise KeyError(f"Resource not found in embedded payload: {{posix_path}}")
    raw = get_payload_bytes()
    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
        return zf.read(posix_path)


def _runtime_metadata() -> tuple[dict[str, str], dict[str, object]]:
    try:
        lock = json.loads(get_embedded_resource(f"{{RUNTIME_META_PREFIX}}/lock.json"))
        expected_platform = json.loads(get_embedded_resource(f"{{RUNTIME_META_PREFIX}}/platform.json"))
    except Exception as exc:
        raise PayloadIntegrityError(f"Runtime metadata missing or corrupt: {{exc}}") from exc
    if not isinstance(lock, dict) or not isinstance(expected_platform, dict):
        raise PayloadIntegrityError("Runtime metadata has invalid shape")
    return lock, expected_platform


def verify_runtime_platform() -> dict[str, object]:
    _lock, expected = _runtime_metadata()
    actual = _current_runtime_platform()
    if actual != expected:
        raise PayloadIntegrityError(
            "Unsupported runtime platform/ABI for this standalone artifact: "
            f"expected={{expected}}, actual={{actual}}"
        )
    return actual


def _safe_output_path(root: Path, archive_name: str) -> Path:
    posix = PurePosixPath(archive_name)
    if posix.is_absolute() or not posix.parts or any(part in ("", ".", "..") for part in posix.parts):
        raise PayloadIntegrityError(f"Unsafe embedded path: {{archive_name}}")
    out_file = root.joinpath(*posix.parts)
    try:
        out_file.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise PayloadIntegrityError(f"Embedded path escapes runtime root: {{archive_name}}") from exc
    return out_file


def _verify_extracted_tree(target_dir: Path) -> bool:
    try:
        for name, entry in PAYLOAD_MANIFEST.items():
            out_file = _safe_output_path(target_dir, name)
            if not out_file.is_file():
                return False
            data = out_file.read_bytes()
            if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                return False
        return True
    except Exception:
        return False


def unpack_payload(target_dir: Path | None = None) -> Path:
    """Verify and extract to a content-addressed runtime directory."""
    if target_dir is None:
        target_dir = Path(tempfile.gettempdir()) / f"bdb_audit_v2_{{PAYLOAD_MANIFEST_DIGEST[:16]}}"
    target_dir = Path(target_dir).resolve()
    marker_file = target_dir / ".bdb_payload_verified"

    if marker_file.is_file():
        try:
            if marker_file.read_text(encoding="utf-8").strip() == PAYLOAD_MANIFEST_DIGEST and _verify_extracted_tree(target_dir):
                return target_dir
        except Exception:
            pass

    raw = get_payload_bytes()
    verify_embedded_payload()
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
        for name in sorted(PAYLOAD_MANIFEST):
            entry = PAYLOAD_MANIFEST[name]
            out_file = _safe_output_path(target_dir, name)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            data = zf.read(name)
            if len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise PayloadIntegrityError(f"Integrity check failed during unpack for {{name}}")
            out_file.write_bytes(data)

    if not _verify_extracted_tree(target_dir):
        raise PayloadIntegrityError("Extracted runtime tree failed post-write verification")
    marker_file.write_text(PAYLOAD_MANIFEST_DIGEST, encoding="utf-8")
    return target_dir


def _module_inside(root: Path, module) -> bool:
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return False
    try:
        Path(module_file).resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _assert_no_external_preloads(root: Path) -> None:
    runtime_roots = ("attr", "attrs", "jsonschema", "jsonschema_specifications", "referencing", "rpds", "bdb_audit")
    for name, module in tuple(sys.modules.items()):
        if not any(name == top or name.startswith(top + ".") for top in runtime_roots):
            continue
        if module is None or not _module_inside(root, module):
            raise PayloadIntegrityError(f"External runtime module was preloaded before standalone bootstrap: {{name}}")


def bootstrap_environment() -> Path:
    """Bootstrap exclusively from the verified embedded runtime payload."""
    verify_runtime_platform()
    extracted_dir = unpack_payload()
    _assert_no_external_preloads(extracted_dir)
    root_str = str(extracted_dir)
    sys.path[:] = [p for p in sys.path if p != root_str]
    sys.path.insert(0, root_str)

    for module_name in ("attrs", "jsonschema", "jsonschema_specifications", "referencing", "rpds", "bdb_audit"):
        module = importlib.import_module(module_name)
        if not _module_inside(extracted_dir, module):
            raise PayloadIntegrityError(f"Host dependency leakage detected for {{module_name}}: {{getattr(module, '__file__', None)}}")
    return extracted_dir


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if "--version" in argv:
        print(f"BDB Audit v{{APP_VERSION}} (Standalone {{BUILD_ID}})")
        return 0

    if "--verify-payload" in argv:
        try:
            verified = verify_embedded_payload(verbose="-v" in argv or "--verbose" in argv)
            runtime_platform = verify_runtime_platform()
            lock, _expected = _runtime_metadata()
            print(json.dumps({{
                "status": "PASS",
                "app_version": APP_VERSION,
                "build_id": BUILD_ID,
                "payload_manifest_digest": PAYLOAD_MANIFEST_DIGEST,
                "verified_files_count": len(verified),
                "runtime_lock": lock,
                "runtime_platform": runtime_platform,
            }}, indent=2, sort_keys=True))
            return 0
        except Exception as exc:
            print(json.dumps({{"status": "FAIL", "error": str(exc)}}, indent=2), file=sys.stderr)
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

    bootstrap_environment()
    from bdb_audit.cli import run_cli
    return run_cli(argv)


if __name__ == "__main__":
    sys.exit(main())
'''


def build_standalone(output_path: Path | None = None) -> tuple[Path, str, int]:
    """Build the deterministic self-contained artifact and return path/hash/size."""
    if output_path is None:
        DIST_DIR.mkdir(parents=True, exist_ok=True)
        output_path = DIST_DIR / DEFAULT_OUTPUT_NAME
    else:
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

    files = collect_build_files(SRC_DIR)
    manifest = build_manifest(files)

    manifest_bytes = json.dumps(manifest, sort_keys=True, indent=2).replace("\r\n", "\n").encode("utf-8")
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    zip_data = create_payload_zip(files)
    payload_digest = hashlib.sha256(zip_data).hexdigest()
    payload_size = len(zip_data)
    b85_str = base64.b85encode(zip_data).decode("ascii")

    manifest_json_str = json.dumps(manifest, sort_keys=True, indent=4).replace("\r\n", "\n")
    rendered = STANDALONE_STUB_TEMPLATE.format(
        APP_VERSION=APP_VERSION,
        BUILD_ID=BUILD_ID,
        PAYLOAD_MANIFEST_DIGEST=manifest_digest,
        PAYLOAD_RAW_DIGEST=payload_digest,
        PAYLOAD_SIZE=payload_size,
        PAYLOAD_MANIFEST_JSON=manifest_json_str,
        EMBEDDED_PAYLOAD_B85=b85_str,
    )
    script_bytes = rendered.replace("\r\n", "\n").encode("utf-8")
    output_path.write_bytes(script_bytes)
    return output_path, hashlib.sha256(script_bytes).hexdigest(), len(script_bytes)


def main() -> int:
    out_path, sha, sz = build_standalone()
    print(f"BUILD_SUCCESS: {out_path} ({sz} bytes, SHA256: {sha})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

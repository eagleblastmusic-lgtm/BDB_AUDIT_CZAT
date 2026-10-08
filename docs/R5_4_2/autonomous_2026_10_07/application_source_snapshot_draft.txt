"""Exact dirty application bytes, distinct from audited Git target or authority."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import stat

from execution import OUT, ROOT, canonical, digest, preserve, write


def sha(data):
    return hashlib.sha256(data).hexdigest()


def regular(root, path):
    if not path.is_relative_to(root) or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("APPLICATION_SOURCE_PATH_ESCAPE")
    for parent in (path, *path.parents):
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise ValueError("APPLICATION_SOURCE_SYMLINK")
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode):
        raise ValueError("APPLICATION_SOURCE_NOT_REGULAR")
    data = path.read_bytes()
    if data.replace(b"\r\n", b"\n").startswith(b"version https://git-lfs.github.com/spec/v1\n"):
        raise ValueError("APPLICATION_SOURCE_UNRESOLVED_LFS")
    return data, stat.S_IMODE(mode)


def inventory(root):
    root = Path(root).absolute()
    src = root / "src"
    if not src.is_dir() or src.is_symlink():
        raise ValueError("APPLICATION_SOURCE_ROOT")
    paths = []
    def walk_error(error):
        raise error
    for directory, dirs, files in os.walk(src, onerror=walk_error):
        dirs[:] = sorted(name for name in dirs if name != "__pycache__"
                         and not name.endswith((".egg-info", ".dist-info")))
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                raise ValueError("APPLICATION_SOURCE_SYMLINK")
        paths.extend(Path(directory) / name for name in sorted(files)
                     if not name.endswith((".pyc", ".pyo")))
    if not paths:
        raise ValueError("APPLICATION_SOURCE_EMPTY")
    paths.extend(root / name for name in ("build/build_single_file.py", "requirements-f2.lock"))
    paths.extend(root / name for name in ("pyproject.toml", "setup.cfg") if (root / name).exists())
    result = {}
    for path in sorted(paths):
        data, mode = regular(root, path)
        result[path.relative_to(root).as_posix()] = (data, mode)
    return result


def builder_module(root):
    spec = importlib.util.spec_from_file_location("nf02_exact_application_builder", root / "build/build_single_file.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def construct(root=ROOT, collector=None):
    before = inventory(root)
    module = builder_module(root) if collector is None else None
    collect = module.collect_source_files if collector is None else collector
    payload_rows = collect(root / "src")
    payload = dict(payload_rows)
    if len(payload) != len(payload_rows):
        raise ValueError("APPLICATION_SOURCE_DUPLICATE_PAYLOAD")
    expected = {name.removeprefix("src/"): data for name, (data, _) in before.items() if name.startswith("src/")}
    if set(payload) != set(expected):
        raise ValueError("APPLICATION_SOURCE_PAYLOAD_INVENTORY")
    entries, retained = [], {}
    for name, (data, mode) in before.items():
        entry = {"file": name, "raw_digest": sha(data), "byte_length": len(data),
                 "captured_stat_mode": mode, "mode_semantics": "HOST_STAT_NOT_GIT_TREE_MODE"}
        retained["raw/" + name] = data
        if name.startswith("src/"):
            rel = name.removeprefix("src/")
            normalized = data
            if Path(name).suffix in (".py", ".json", ".txt", ".md"):
                try:
                    normalized = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
                except UnicodeDecodeError:
                    pass
            if payload[rel] != normalized:
                raise ValueError("APPLICATION_SOURCE_PAYLOAD_BYTES")
            entry["payload"] = {"file": rel, "raw_digest": sha(normalized), "byte_length": len(normalized)}
            retained["payload/" + rel] = normalized
        entries.append(entry)
    if inventory(root) != before:
        raise ValueError("APPLICATION_SOURCE_INPUT_DRIFT")
    manifest = {"representation": "EXACT_WORKING_TREE_RAW_AND_COLLECTED_PAYLOAD_V1", "entries": entries,
                "identity_mode": "WORKING_TREE_SNAPSHOT; NO_GIT_HEAD_OR_TREE_IDENTITY",
                "trust": "RETAINED_BYTES_ONLY; INDEPENDENT_SOURCE_AUTHORIZATION_PENDING",
                "scope": "CURRENT_PRE_ACTIVATION_PRODUCT; FUTURE_SUCCESSOR_RESOURCES_AND_RUNTIME_CLOSURE_SEPARATE",
                "normalization": "EXISTING_STANDALONE_COLLECTOR_UTF8_TEXT_LF_OTHER_EXACT"}
    retained["manifest.json"] = canonical(manifest) + b"\n"
    return retained, manifest


def verify(directory, files):
    actual = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
    if actual != set(files):
        raise ValueError("APPLICATION_SOURCE_READBACK_INVENTORY")
    for name, expected in files.items():
        path = directory / name
        data, _ = regular(directory, path)
        if data != expected:
            raise ValueError("APPLICATION_SOURCE_READBACK_BYTES")


def main():
    preserve()
    tool_paths = (Path(__file__).resolve(), OUT / "tools/execution.py", ROOT / "build/build_single_file.py")
    tool_before = {path.relative_to(ROOT).as_posix(): digest(path) for path in tool_paths}
    inputs_before = inventory(ROOT)
    files, manifest = construct()
    snapshot = sha(files["manifest.json"])
    directory = OUT / "design/application_source_snapshots" / snapshot
    if not directory.exists():
        directory.mkdir(parents=True)
        for name, data in files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    verify(directory, files)
    if inventory(ROOT) != inputs_before:
        raise ValueError("APPLICATION_SOURCE_INPUT_DRIFT")
    if tool_before != {path.relative_to(ROOT).as_posix(): digest(path) for path in tool_paths}:
        raise ValueError("APPLICATION_SOURCE_TOOL_DRIFT")
    write("APPLICATION_SOURCE_SNAPSHOT_READBACK.json", {
        "snapshot_manifest_raw_digest": snapshot, "directory": directory.relative_to(ROOT).as_posix(),
        "source_files": len(manifest["entries"]), "retained_files": len(files),
        "builder_raw_digest": digest(ROOT / "build/build_single_file.py"),
        "source_inventory_and_bytes_drift": [], "readback": "PASS", "source_authorization": "NOT_ESTABLISHED",
        "qualification": False, "successor_application_identity": False,
        "source_inputs": [{"file": name, "raw_digest": raw_digest} for name, raw_digest in tool_before.items()]})
    print("PASS exact application raw/payload snapshot", len(manifest["entries"]), snapshot)


if __name__ == "__main__":
    main()

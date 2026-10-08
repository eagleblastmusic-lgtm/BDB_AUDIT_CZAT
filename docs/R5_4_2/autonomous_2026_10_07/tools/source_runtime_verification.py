"""Run existing source regressions without changing the working repository."""

import sys
import time
import hashlib
import contextlib
import os
import tempfile
import uuid
from pathlib import Path

from execution import ROOT, digest, git, write


def main():
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "._nf02_current_audit"))
    import audit_tmp
    import pytest
    from bdb_audit.source import git_resolver

    assert Path(git_resolver.__file__) == ROOT / "src/bdb_audit/source/git_resolver.py"
    head = git("rev-parse", "HEAD")
    tool_before = digest(Path(__file__))
    harness_inputs = {"._nf02_current_audit/audit_tmp.py": digest(ROOT / "._nf02_current_audit/audit_tmp.py")}
    for name in ("pyproject.toml", "pytest.ini", "setup.cfg", "conftest.py"):
        if (ROOT / name).is_file():
            harness_inputs[name] = digest(ROOT / name)
    targets = sys.argv[1:]
    local_temp = bool(targets and targets[0] == "--repo-temp")
    if local_temp:
        targets = targets[1:]
    targets = targets or ["tests/stage2/test_ru02_source_identity.py", "tests/stage2/test_source_object_format_regression.py"]
    argv = [*targets, "-q", "--tb=short"]
    test_inputs = {p.relative_to(ROOT).as_posix(): digest(p) for target in targets
                   for p in ([ROOT / target] if (ROOT / target).is_file() else sorted((ROOT / target).rglob("*.py")))}
    # Imported helpers and fixtures can lie outside the selected test targets.
    test_dependency_inputs = {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted((ROOT / "tests").rglob("*.py"))}
    implementation_inputs = {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted((ROOT / "src").rglob("*.py"))}
    implementation_inputs.update({p.relative_to(ROOT).as_posix(): digest(p) for p in sorted((ROOT / "build").rglob("*.py"))})
    implementation_inputs["requirements-f2.lock"] = digest(ROOT / "requirements-f2.lock")
    build_runtime_inputs = None
    if any(target.startswith("tests/f8/test_m46") for target in targets):
        from build import build_single_file
        assert Path(build_single_file.__file__) == ROOT / "build/build_single_file.py"

        def runtime_snapshot():
            return {name: {"byte_length": len(raw), "raw_digest": hashlib.sha256(raw).hexdigest()}
                    for name, raw in build_single_file.collect_runtime_files()}

        build_runtime_inputs = runtime_snapshot()
    start = time.monotonic()
    old_temp = tempfile.TemporaryDirectory
    old_env = {key: os.environ.get(key) for key in ("TEMP", "TMP")}
    temp_root = None
    if local_temp:
        temp_root = ROOT / "._nf02_current_audit/data" / ("runtime-" + uuid.uuid4().hex)
        temp_root.mkdir(parents=True)

        @contextlib.contextmanager
        def safe_temp(*args, **kwargs):
            path = temp_root / uuid.uuid4().hex
            path.mkdir()
            # Retain diagnostics; never recursively delete a computed tree.
            yield str(path)

        tempfile.TemporaryDirectory = safe_temp
        for key in old_env:
            os.environ[key] = str(temp_root)
    try:
        result = pytest.main(argv, plugins=[audit_tmp])
    finally:
        tempfile.TemporaryDirectory = old_temp
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    assert git("rev-parse", "HEAD") == head
    input_inventory_after = {p.relative_to(ROOT).as_posix() for base in ("src", "build", "tests") for p in (ROOT / base).rglob("*.py")}
    input_inventory_before = {name for name in {**implementation_inputs, **test_dependency_inputs} if name.endswith(".py")}
    result_name = "design/source_instance_readback/runtime_runs/" + str(time.time_ns()) + ".json"
    record = {
        "argv": argv, "exit_code": int(result), "duration_seconds": time.monotonic() - start,
        "source_HEAD": head, "repository_HEAD_unchanged": True,
        "test_inputs": test_inputs,
        "tool_raw_digest": tool_before,
        "tool_drift": digest(Path(__file__)) != tool_before,
        "harness_inputs": harness_inputs,
        "test_dependency_inputs": test_dependency_inputs,
        "input_inventory_drift": sorted(input_inventory_after ^ input_inventory_before),
        "implementation_inputs": implementation_inputs,
        "python": sys.version,
        "build_runtime_inputs": build_runtime_inputs,
        "build_runtime_input_drift": build_runtime_inputs is not None and runtime_snapshot() != build_runtime_inputs,
        "input_drift": [name for name, before in {**test_inputs, **test_dependency_inputs, **implementation_inputs, **harness_inputs}.items() if not (ROOT / name).is_file() or digest(ROOT / name) != before],
        "environment": "Existing repo-local tmp fixtures; real Git operations in isolated fixture repos",
        "temporary_directory_acl_retry": local_temp,
        "retained_temporary_root": str(temp_root) if temp_root else None,
        "qualification": False, "trusted_profile_selection": "NOT_PROVEN", "NF02": "OPEN"}
    write(result_name, record)
    artifact = ROOT / "docs/R5_4_2/autonomous_2026_10_07" / result_name
    write("design/source_instance_readback/CURRENT_RUNTIME_RUN.json", {
        "file": result_name, "raw_digest": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "qualification": False, "role": "Diagnostic latest-run locator, never source or acceptance authority"})
    assert not record["tool_drift"], "Runtime verifier changed during execution"
    assert not record["input_inventory_drift"], "Implementation/test file set changed during execution"
    assert not record["input_drift"], "Inputs changed during runtime verification; retained result is not terminal evidence"
    assert not record["build_runtime_input_drift"], "Runtime dependency bytes changed during build verification"
    raise SystemExit(result)


if __name__ == "__main__":
    main()

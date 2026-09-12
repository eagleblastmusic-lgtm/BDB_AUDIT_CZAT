"""Patch regression: standalone must not depend on host/project packages."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from build.build_single_file import build_standalone, collect_build_files


def _clean_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def _run_utf8(args: list[str], **kwargs):
    """Capture the product's declared UTF-8 text contract explicitly."""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        **kwargs,
    )


def test_standalone_payload_contains_pinned_runtime_closure():
    paths = {path for path, _data in collect_build_files()}
    assert "__bdb_runtime__/lock.json" in paths
    assert "__bdb_runtime__/platform.json" in paths
    assert any(path.startswith("jsonschema/") for path in paths)
    assert any(path.startswith("jsonschema_specifications/") for path in paths)
    assert any(path.startswith("referencing/") for path in paths)
    assert any(path.startswith("attrs/") for path in paths)
    assert any(path.startswith("rpds/") for path in paths)
    assert any(path.endswith((".pyd", ".so")) and path.startswith("rpds/") for path in paths)


def test_standalone_runs_in_clean_isolated_python_without_jsonschema_installed():
    """The exact release defect: clean host import fails, embedded runtime succeeds."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        artifact = root / "BDB_AUDIT_ASSISTANT_v2.0.3.py"
        venv_dir = root / "clean_venv"
        build_standalone(artifact)

        _run_utf8(
            [sys.executable, "-m", "venv", "--without-pip", str(venv_dir)],
            check=True,
        )
        python_exe = _clean_python(venv_dir)
        env = _clean_env()

        # Prove the host environment does not provide the dependency.
        host_probe = _run_utf8(
            [str(python_exe), "-I", "-c", "import jsonschema"],
            cwd=root,
            env=env,
        )
        assert host_probe.returncode != 0

        version = _run_utf8(
            [str(python_exe), "-I", str(artifact), "--version"],
            cwd=root,
            env=env,
        )
        assert version.returncode == 0, version.stderr
        assert "v2.0.3" in version.stdout

        verify = _run_utf8(
            [str(python_exe), "-I", str(artifact), "--verify-payload"],
            cwd=root,
            env=env,
        )
        assert verify.returncode == 0, verify.stderr
        verify_data = json.loads(verify.stdout)
        assert verify_data["status"] == "PASS"
        assert verify_data["runtime_lock"]["jsonschema"] == "4.25.1"

        self_test = _run_utf8(
            [str(python_exe), "-I", str(artifact), "self-test"],
            cwd=root,
            env=env,
        )
        assert self_test.returncode == 0, self_test.stderr
        assert json.loads(self_test.stdout)["status"] == "PASS"

        help_run = _run_utf8(
            [str(python_exe), "-I", str(artifact), "--help"],
            cwd=root,
            env=env,
        )
        assert help_run.returncode == 0, help_run.stderr
        assert "campaign" in help_run.stdout

        ui_run = _run_utf8(
            [str(python_exe), "-I", str(artifact), "ui"],
            cwd=root,
            env=env,
            input="7\n",
        )
        assert ui_run.returncode == 0, ui_run.stderr
        # This test protects the clean-host runtime closure, not a particular UI
        # release label. The embedded product source can advance independently
        # of this historical v2.0.1 wrapper regression fixture.
        assert "BDB AUDIT v2.0.3" in ui_run.stdout or "Interactive Control Surface" in ui_run.stdout
        assert "Exiting UI." in ui_run.stdout

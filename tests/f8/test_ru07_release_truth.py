"""RU07 — release truth, distribution capability, and CI anti-bypass proofs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from bdb_audit import cli
from bdb_audit.release_validator_cli import run_release_validator_cli
from bdb_audit.version import APP_VERSION, BUILD_ID
from build import build_single_file


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ru07_single_version_source_and_source_capabilities(capsys):
    assert APP_VERSION == "2.0.3"
    assert BUILD_ID == "BDB-V2-STANDALONE-2.0.3"
    assert cli.APP_VERSION == APP_VERSION
    assert cli.BUILD_ID == BUILD_ID
    assert build_single_file.APP_VERSION == APP_VERSION
    assert build_single_file.BUILD_ID == BUILD_ID

    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in pyproject
    assert 'version = {attr = "bdb_audit.version.__version__"}' in pyproject
    assert 'version = "2.0.0.dev0"' not in pyproject

    assert cli.run_cli(["capabilities", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["distribution"] == "source"
    assert payload["capabilities"]["build"] == "SUPPORTED"


def test_ru07_release_validator_cli_missing_artifact_fails_closed(capsys):
    rc = run_release_validator_cli(["definitely-missing-ru07-artifact.py"])
    assert rc != 0
    report = json.loads(capsys.readouterr().err)
    assert report["status"] == "FAIL"
    assert report["error"] == "ARTIFACT_NOT_FOUND"
    assert report["checks"]["clean_room_rebuild_identity"] == "NOT_RUN"


def test_ru07_release_validator_cli_valid_and_tampered_artifacts(capsys):
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        artifact = td_path / "candidate.py"
        receipt = td_path / "receipt.json"
        build_single_file.build_standalone(artifact)

        rc = run_release_validator_cli([
            str(artifact),
            "--output",
            str(receipt),
            "--no-same-environment-rebuild",
        ])
        assert rc == 0
        stdout_report = json.loads(capsys.readouterr().out)
        file_report = json.loads(receipt.read_text(encoding="utf-8"))
        assert stdout_report["status"] == file_report["status"] == "PASS"
        assert file_report["checks"]["10_same_environment_rebuild_identity"] == "NOT_RUN"
        assert file_report["checks"]["10b_clean_room_rebuild_identity"] == "NOT_RUN"

        text = artifact.read_text(encoding="utf-8")
        artifact.write_text(text.replace('PAYLOAD_RAW_DIGEST = "', 'PAYLOAD_RAW_DIGEST = "0', 1), encoding="utf-8")
        rc = run_release_validator_cli([str(artifact), "--no-same-environment-rebuild"])
        assert rc != 0
        fail_report = json.loads(capsys.readouterr().err)
        assert fail_report["status"] == "FAIL"


def test_ru07_standalone_capabilities_and_build_rejection_are_controlled():
    with tempfile.TemporaryDirectory() as td:
        artifact = Path(td) / "standalone.py"
        build_single_file.build_standalone(artifact)

        capabilities = subprocess.run(
            [sys.executable, "-I", str(artifact), "capabilities"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )
        assert capabilities.returncode == 0
        cap_doc = json.loads(capabilities.stdout)
        assert cap_doc["distribution"] == "standalone"
        assert cap_doc["capabilities"]["build"] == "UNSUPPORTED"

        rejected = subprocess.run(
            [sys.executable, "-I", str(artifact), "build", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )
        assert rejected.returncode != 0
        error_doc = json.loads(rejected.stderr)
        assert error_doc["error"] == "DISTRIBUTION_CAPABILITY_UNAVAILABLE"
        assert "Traceback" not in rejected.stderr


def test_ru07_validator_module_entrypoint_missing_artifact_is_nonzero():
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else src_path + os.pathsep + env["PYTHONPATH"]
    proc = subprocess.run(
        [sys.executable, "-m", "bdb_audit.release_validator_cli", "definitely-missing-ru07-artifact.py"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    assert proc.returncode != 0
    doc = json.loads(proc.stderr)
    assert doc["error"] == "ARTIFACT_NOT_FOUND"


def test_ru07_source_collection_excludes_generated_install_metadata():
    with tempfile.TemporaryDirectory() as td:
        src_root = Path(td) / "src"
        package = src_root / "bdb_audit"
        egg_info = src_root / "bdb_audit.egg-info"
        dist_info = src_root / "bdb_audit-2.0.3.dist-info"
        package.mkdir(parents=True)
        egg_info.mkdir()
        dist_info.mkdir()
        (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
        (egg_info / "SOURCES.txt").write_text("volatile\n", encoding="utf-8")
        (dist_info / "RECORD").write_text("volatile\n", encoding="utf-8")

        paths = {path for path, _data in build_single_file.collect_source_files(src_root)}
        assert paths == {"bdb_audit/__init__.py"}


def test_ru07_current_workflow_binds_exact_candidate_and_separates_python_gates():
    workflow = (REPO_ROOT / ".github" / "workflows" / "v2-0-3-qualification.yml").read_text(encoding="utf-8")
    assert "github.event.pull_request.head.sha" in workflow
    assert "ref: ${{ env.CANDIDATE_SHA }}" in workflow
    assert "Checked-out HEAD does not equal declared candidate SHA" in workflow
    assert "clean-room-rebuild:" in workflow
    assert "Clean-room raw artifact identity mismatch" in workflow
    assert "CANDIDATE_GATE_RECEIPT.json" in workflow
    assert 'pip install --upgrade pip' not in workflow

    # D25: known release gate categories are represented as distinct workflow steps,
    # not one PowerShell block whose last native command can mask an earlier failure.
    required_step_names = (
        "Full pytest suite",
        "Ruff release lane",
        "Mypy release lane",
        "Build candidate standalone",
        "Release validator CLI",
        "Standalone version",
        "Standalone payload verification",
        "Standalone self-test",
        "Standalone deep self-test",
        "Standalone capability matrix",
        "Standalone help",
    )
    for name in required_step_names:
        assert f"- name: {name}" in workflow


def test_ru07_legacy_publish_workflows_have_no_grouped_release_native_gates():
    for filename in ("publish-v2-0-1.yml", "publish-v2-0-2.yml"):
        text = (REPO_ROOT / ".github" / "workflows" / filename).read_text(encoding="utf-8")
        assert "Final pytest qualification" in text
        assert "Final Ruff qualification" in text
        assert "Final Mypy qualification" in text
        assert "Standalone version smoke" in text
        assert "Standalone payload smoke" in text
        assert "Standalone self-test smoke" in text
        assert "Standalone help smoke" in text
        assert 'pytest = "PASS"' not in text
        assert 'ruff = "PASS"' not in text
        assert 'mypy = "PASS"' not in text
        assert 'standalone_smoke = "PASS"' not in text

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

from bdb_audit.cli import run_cli
from bdb_audit.runner.specs import CapabilityProfile, ToolRunSpec
from bdb_audit.runner.supervisor import ToolSupervisor


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "target.txt").write_text("source", encoding="utf-8")
    return source


def test_ru10_vnext_cli_preserves_legacy_command_surface(capsys) -> None:
    assert run_cli(["capabilities", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "SUCCESS"
    assert payload["distribution"] == "source"


def test_ru10_tools_plan_and_run_and_results_cli(tmp_path: Path, capsys) -> None:
    source = _source(tmp_path)
    evidence = tmp_path / "evidence"
    base = [
        "--run-id", "cli-run",
        "--source", str(source),
        "--evidence", str(evidence),
        "--json",
        "--",
        sys.executable, "-c", "print('runner-cli-ok')",
    ]
    assert run_cli(["tools", "plan", *base]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "PASS"
    assert plan["spec"]["argv"][0] == sys.executable

    assert run_cli(["tools", "run", *base]) == 0
    executed = json.loads(capsys.readouterr().out)
    assert executed["supervisor_status"] == "SUCCESS"
    assert "NETWORK_EGRESS_NOT_ENFORCED" in executed["limitations"]
    assert "HOST_FILESYSTEM_ISOLATION_NOT_ENFORCED" in executed["limitations"]

    assert run_cli(["tools", "results", "--evidence", str(evidence), "--json"]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["status"] == "PASS"
    assert verified["run_id"] == "cli-run"


def test_ru10_environment_verify_exposes_real_limitations(tmp_path: Path, capsys) -> None:
    source = _source(tmp_path)
    assert run_cli(["environment", "verify", "--source", str(source), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert payload["capability_profile"]["network_isolation"] == "NOT_ENFORCED"
    assert payload["capability_profile"]["host_filesystem_isolation"] == "NOT_ENFORCED"
    assert "HOST_FILESYSTEM_ISOLATION_NOT_ENFORCED" in payload["limitations"]


def test_ru10_required_host_filesystem_isolation_fails_closed(tmp_path: Path) -> None:
    source = _source(tmp_path)
    result = ToolSupervisor(CapabilityProfile(host_filesystem_isolation="NOT_ENFORCED")).run(
        ToolRunSpec(
            run_id="fs-isolation-required",
            source_root=str(source),
            evidence_dir=str(tmp_path / "evidence"),
            argv=(sys.executable, "-c", "print('must not run')"),
            require_host_filesystem_isolation=True,
        )
    )
    assert result.supervisor_status == "BLOCKED"
    assert result.cleanup_status == "NOT_STARTED"
    assert "HOST_FILESYSTEM_ISOLATION_UNAVAILABLE" in result.limitations


def test_ru10_timeout_terminates_spawned_child_process_tree(tmp_path: Path) -> None:
    source = _source(tmp_path)
    marker = tmp_path / "child-survived.txt"
    child = f"import time; from pathlib import Path; time.sleep(3); Path({str(marker)!r}).write_text('survived')"
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
        "time.sleep(30)"
    )
    result = ToolSupervisor().run(
        ToolRunSpec(
            run_id="child-tree-timeout",
            source_root=str(source),
            evidence_dir=str(tmp_path / "evidence"),
            argv=(sys.executable, "-c", parent),
            timeout_seconds=1,
        )
    )
    assert result.supervisor_status == "TIMEOUT"
    time.sleep(4)
    assert not marker.exists()

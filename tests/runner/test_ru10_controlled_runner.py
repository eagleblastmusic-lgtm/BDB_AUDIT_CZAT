from __future__ import annotations

import json
from pathlib import Path
import sys

from bdb_audit.runner import CapabilityProfile, ToolRunSpec, ToolSupervisor
from bdb_audit.runner.adapters import ExactArgvAdapter


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "seed.txt").write_text("original", encoding="utf-8")
    return source


def test_ru10_executes_exact_argv_only_in_disposable_copy(tmp_path: Path) -> None:
    source = _source(tmp_path)
    evidence = tmp_path / "evidence"
    code = "from pathlib import Path; Path('mutated.txt').write_text('worker'); print('ok')"
    spec = ToolRunSpec(
        run_id="run-disposable",
        source_root=str(source),
        evidence_dir=str(evidence),
        argv=(sys.executable, "-c", code),
    )
    result = ToolSupervisor().run(spec)
    assert result.supervisor_status == "SUCCESS"
    assert result.target_exit_code == 0
    assert result.cleanup_status == "CLEAN"
    assert not (source / "mutated.txt").exists()
    assert (evidence / "stdout.bin").read_text(encoding="utf-8").strip() == "ok"
    receipt = json.loads((evidence / "RUN_RECEIPT.json").read_text(encoding="utf-8"))
    assert receipt["receipt_digest"] == result.receipt_digest
    assert "NETWORK_EGRESS_NOT_ENFORCED" in result.limitations


def test_ru10_shell_tokens_are_plain_arguments_not_shell_programs(tmp_path: Path) -> None:
    source = _source(tmp_path)
    outside = tmp_path / "pwned.txt"
    payload = f"; echo pwned > {outside}"
    spec = ExactArgvAdapter((sys.executable, "-c", "import sys; print(sys.argv[1])", payload)).build(
        run_id="run-no-shell",
        source_root=source,
        evidence_dir=tmp_path / "evidence",
    )
    result = ToolSupervisor().run(spec)
    assert result.supervisor_status == "SUCCESS"
    assert not outside.exists()


def test_ru10_timeout_is_not_success(tmp_path: Path) -> None:
    source = _source(tmp_path)
    spec = ToolRunSpec(
        run_id="run-timeout",
        source_root=str(source),
        evidence_dir=str(tmp_path / "evidence"),
        argv=(sys.executable, "-c", "import time; time.sleep(30)"),
        timeout_seconds=1,
    )
    result = ToolSupervisor().run(spec)
    assert result.supervisor_status == "TIMEOUT"
    assert result.timed_out is True


def test_ru10_output_limit_is_not_success(tmp_path: Path) -> None:
    source = _source(tmp_path)
    spec = ToolRunSpec(
        run_id="run-output-limit",
        source_root=str(source),
        evidence_dir=str(tmp_path / "evidence"),
        argv=(sys.executable, "-c", "import sys,time; sys.stdout.write('x'*200000); sys.stdout.flush(); time.sleep(2)"),
        max_output_bytes=4096,
        timeout_seconds=10,
    )
    result = ToolSupervisor().run(spec)
    assert result.supervisor_status == "OUTPUT_LIMIT"
    assert result.output_limit_exceeded is True


def test_ru10_network_isolation_requirement_fails_closed_when_unavailable(tmp_path: Path) -> None:
    source = _source(tmp_path)
    spec = ToolRunSpec(
        run_id="run-network",
        source_root=str(source),
        evidence_dir=str(tmp_path / "evidence"),
        argv=(sys.executable, "-c", "print('must not execute')"),
        require_network_isolation=True,
    )
    result = ToolSupervisor(CapabilityProfile(network_isolation="NOT_ENFORCED")).run(spec)
    assert result.supervisor_status == "BLOCKED"
    assert result.target_exit_code is None
    assert result.cleanup_status == "NOT_STARTED"
    assert "NETWORK_ISOLATION_UNAVAILABLE" in result.limitations


def test_ru10_sensitive_environment_is_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path)
    spec = ToolRunSpec(
        run_id="run-secret-env",
        source_root=str(source),
        evidence_dir=str(tmp_path / "evidence"),
        argv=(sys.executable, "-c", "print('must not execute')"),
        environment={"API_TOKEN": "secret"},
    )
    result = ToolSupervisor().run(spec)
    assert result.supervisor_status == "BLOCKED"
    assert "TOOL_RUN_SECRET_ENV_FORBIDDEN" in result.limitations


def test_ru10_evidence_cannot_be_written_inside_target(tmp_path: Path) -> None:
    source = _source(tmp_path)
    spec = ToolRunSpec(
        run_id="run-evidence-boundary",
        source_root=str(source),
        evidence_dir=str(source / "evidence"),
        argv=(sys.executable, "-c", "print('must not execute')"),
    )
    result = ToolSupervisor().run(spec)
    assert result.supervisor_status == "BLOCKED"
    assert "TOOL_RUN_EVIDENCE_INSIDE_TARGET" in result.limitations

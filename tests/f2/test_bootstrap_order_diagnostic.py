"""Diagnostic reproducibility, not successful M5 acceptance evidence."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import json

SCRIPT = Path(__file__).with_name("diagnose_bootstrap_order.py")


def test_order_conflict_reproduces_from_exact_sources():
    spec = importlib.util.spec_from_file_location("bootstrap_order_diagnostic", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.diagnose()
    assert result["result"] == "SPEC_CONFLICT"
    assert result["kahn_forced_relative_order"] == list(reversed(result["bootstrap_required_relative_order"]))
    assert result["legacy_same_commit_content_dependency_fields"] == []
    assert result["runtime_acceptance_attempted"] is False


def test_diagnostic_command_is_not_reported_as_gate_pass():
    run = subprocess.run([sys.executable, "-B", str(SCRIPT)], capture_output=True, text=True)
    assert run.returncode == 2
    assert json.loads(run.stdout)["M5_GATE"] == "NOT_RUN"

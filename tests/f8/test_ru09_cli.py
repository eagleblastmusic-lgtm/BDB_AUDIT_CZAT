"""RU09 CLI integration tests for report/remediation export and verification."""
from __future__ import annotations

import json

from bdb_audit.cli import EXIT_SUCCESS, run_cli
from bdb_audit.coordinator.operations import AuditOperationApi


def _campaign(tmp_path):
    store = tmp_path / "campaign.sqlite"
    AuditOperationApi().create_campaign(store, seed="ru09_cli", target_repo=str(tmp_path / "target"))
    return store


def test_report_bundle_cli_export_and_verify(tmp_path):
    store = _campaign(tmp_path)
    bundle = tmp_path / "bundle"
    assert run_cli(["report", "export", "--store", str(store), "--output", str(bundle), "--format", "bundle", "--json"]) == EXIT_SUCCESS
    assert (bundle / "REPORT.json").is_file()
    assert (bundle / "REMEDIATION_PLAN.json").is_file()
    assert run_cli(["report", "verify", "--bundle", str(bundle), "--json"]) == EXIT_SUCCESS


def test_single_report_formats_are_available(tmp_path):
    store = _campaign(tmp_path)
    outputs = {
        "json": tmp_path / "report.json",
        "markdown": tmp_path / "report.md",
        "html": tmp_path / "report.html",
    }
    for format_name, path in outputs.items():
        assert run_cli(["report", "export", "--store", str(store), "--output", str(path), "--format", format_name]) == EXIT_SUCCESS
        assert path.is_file()
        assert path.stat().st_size > 0


def test_remediation_cli_exports_only_proposed_plan_and_validates_it(tmp_path):
    store = _campaign(tmp_path)
    plan_path = tmp_path / "REMEDIATION_PLAN.json"
    assert run_cli(["remediation", "export", "--store", str(store), "--output", str(plan_path), "--json"]) == EXIT_SUCCESS
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert payload["status"] == "PROPOSED"
    assert "plan_sha256" in payload
    assert run_cli(["remediation", "validate", "--plan", str(plan_path), "--json"]) == EXIT_SUCCESS


def test_full_assurance_cli_refuses_incomplete_campaign(tmp_path):
    store = _campaign(tmp_path)
    rc = run_cli([
        "report", "export", "--store", str(store), "--output", str(tmp_path / "full"),
        "--format", "bundle", "--full-assurance", "--json",
    ])
    assert rc != EXIT_SUCCESS

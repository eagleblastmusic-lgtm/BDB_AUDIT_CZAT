from __future__ import annotations

import json
from pathlib import Path

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workbench import build_workbench_snapshot, verify_workbench_snapshot
from bdb_audit.workbench.cli import run_cli


def _campaign(tmp_path: Path) -> tuple[Path, TransactionalHistoryStore]:
    path = tmp_path / "campaign.sqlite"
    AuditOperationApi().create_campaign(
        path,
        seed="ru12b",
        target_repo="https://qualification.invalid/ru12b",
        commit_sha="a" * 40,
    )
    return path, TransactionalHistoryStore(path)


def test_ru12b_workbench_is_exact_cut_derived_and_progress_is_separate(tmp_path: Path) -> None:
    _path, store = _campaign(tmp_path)
    snapshot = build_workbench_snapshot(store).as_dict()
    assert snapshot["authority"] == "DERIVED_ONLY"
    assert snapshot["freshness"] == "ACTIVE"
    assert snapshot["history_cut"]["accepted_head_seq"] >= 1
    assert snapshot["progress"]["planned_units"] >= 0
    assert "started_runs" in snapshot["progress"]
    assert "completed_units" in snapshot["progress"]
    assert "qualified_evidence_items" in snapshot["progress"]
    assert isinstance(snapshot["findings"]["claims"], list)
    assert isinstance(snapshot["contradictions"]["revisions"], list)
    assert isinstance(snapshot["scope_unknowns"], list)


def test_ru12b_old_snapshot_becomes_stale_after_accepted_progress(tmp_path: Path) -> None:
    path, store = _campaign(tmp_path)
    snapshot = build_workbench_snapshot(store).as_dict()
    assert verify_workbench_snapshot(snapshot, store)["freshness"] == "ACTIVE"
    AuditOperationApi().prepare_stage(path, "E1")
    assert verify_workbench_snapshot(snapshot, TransactionalHistoryStore(path))["freshness"] == "STALE"


def test_ru12b_feature_matrix_attachment_never_becomes_authority(tmp_path: Path) -> None:
    _path, store = _campaign(tmp_path)
    matrix = {"schema_version": "BDB-DERIVED-FEATURE-STATUS-MATRIX-1", "entries": []}
    snapshot = build_workbench_snapshot(store, feature_matrix=matrix).as_dict()
    assert snapshot["feature_matrix_state"] == "ATTACHED_DERIVED"
    assert snapshot["feature_matrix"] == matrix
    assert snapshot["authority"] == "DERIVED_ONLY"


def test_ru12b_cli_snapshot_and_navigation_share_history_cut(tmp_path: Path, capsys) -> None:
    path, _store = _campaign(tmp_path)
    output = tmp_path / "workbench.json"
    assert run_cli(["snapshot", "--store", str(path), "--output", str(output), "--json"]) == 0
    snapshot_response = json.loads(capsys.readouterr().out)
    snapshot = json.loads(output.read_text(encoding="utf-8"))
    assert snapshot_response["history_cut"] == snapshot["history_cut"]

    assert run_cli(["contradictions", "--store", str(path), "--json"]) == 0
    contradictions = json.loads(capsys.readouterr().out)
    assert contradictions["history_cut"] == snapshot["history_cut"]

    assert run_cli(["findings", "--store", str(path), "--json"]) == 0
    findings = json.loads(capsys.readouterr().out)
    assert findings["history_cut"] == snapshot["history_cut"]

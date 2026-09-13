from __future__ import annotations

import json
from pathlib import Path

import pytest

from bdb_audit.cli import EXIT_SUCCESS, run_cli
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.assurance_projection import (
    audit_blockers,
    build_verified_assurance_snapshot,
    coverage_matrix,
    inspect_evidence,
    verify_evidence,
    verify_projection_snapshot,
)
from bdb_audit.workflow.read_models import campaign_source_identity


def _insert_orphan_coverage(store: TransactionalHistoryStore, digest: str) -> None:
    con = store._connect()
    try:
        con.execute(
            "INSERT INTO immutable_objects(digest,kind,version,schema_ref,logical_id,body) VALUES(?,?,?,?,?,?)",
            (
                digest,
                "coverage_obligation",
                "1",
                "BDB_SCHEMA_REGISTRY::coverage_obligation/1",
                "coverage_obligation_orphan",
                canonical_bytes({
                    "obligation_id": "coverage_obligation_orphan",
                    "scenario_class": "ORPHAN",
                    "policy_obligation_key": "ORPHAN",
                }),
            ),
        )
    finally:
        con.close()


def test_ru12a_snapshot_is_exact_cut_and_becomes_stale_after_head_advance(tmp_path: Path) -> None:
    db = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(db, seed="ru12a-stale")
    store = TransactionalHistoryStore(db)

    snapshot = build_verified_assurance_snapshot(store).as_dict()
    assert snapshot["authority"] == "DERIVED_ONLY"
    assert snapshot["freshness"] == "ACTIVE"
    assert snapshot["campaign_status"]["accepted_head_seq"] == snapshot["history_cut"]["accepted_head_seq"]
    assert verify_projection_snapshot(snapshot, store)["freshness"] == "ACTIVE"

    api.prepare_stage(db, "E1")
    verification = verify_projection_snapshot(snapshot, store)
    assert verification["status"] == "PASS"
    assert verification["freshness"] == "STALE"
    assert verification["current_history_cut"]["accepted_head_seq"] > snapshot["history_cut"]["accepted_head_seq"]


def test_ru12a_orphan_coverage_storage_is_not_projection_authority(tmp_path: Path) -> None:
    db = tmp_path / "campaign.sqlite"
    AuditOperationApi().create_campaign(db, seed="ru12a-orphan")
    store = TransactionalHistoryStore(db)
    _insert_orphan_coverage(store, "a" * 64)

    matrix = coverage_matrix(store)
    assert matrix["coverage_summary"]["denominator"] == 0
    assert matrix["coverage_rows"] == []


def test_ru12a_evidence_browser_accepts_only_exact_accepted_refs(tmp_path: Path) -> None:
    db = tmp_path / "campaign.sqlite"
    AuditOperationApi().create_campaign(db, seed="ru12a-evidence", commit_sha="1" * 40)
    store = TransactionalHistoryStore(db)
    source = campaign_source_identity(store)
    source_ref = source["source_identity_ref"]

    inspected = inspect_evidence(store, source_ref["revision_digest"], kind="source_identity")
    assert inspected["status"] == "SUCCESS"
    assert inspected["freshness"] == "ACTIVE"
    assert inspected["ref"] == source_ref

    verified = verify_evidence(store, source_ref["revision_digest"], kind="source_identity")
    assert verified["status"] == "PASS"
    assert verified["current_applicable"] is True

    with pytest.raises(ValidationError, match="OBJECT_NOT_ACCEPTED_AT_CUT"):
        inspect_evidence(store, "f" * 64)


def test_ru12a_blockers_exposes_verified_workflow_next_action(tmp_path: Path) -> None:
    db = tmp_path / "campaign.sqlite"
    AuditOperationApi().create_campaign(db, seed="ru12a-blockers")
    store = TransactionalHistoryStore(db)

    result = audit_blockers(store)
    assert result["status"] == "SUCCESS"
    assert result["freshness"] == "ACTIVE"
    assert result["workflow"]["continuation_state"] == "NOT_PREPARED"
    assert result["workflow"]["next_action"] == "PREPARE_STAGE_E1"
    assert result["blockers"] == []


def test_ru12a_cli_matrix_blockers_and_evidence_verify(tmp_path: Path, capsys) -> None:
    db = tmp_path / "campaign.sqlite"
    AuditOperationApi().create_campaign(db, seed="ru12a-cli", commit_sha="2" * 40)
    store = TransactionalHistoryStore(db)
    source_ref = campaign_source_identity(store)["source_identity_ref"]

    assert run_cli(["coverage", "matrix", "--store", str(db), "--json"]) == EXIT_SUCCESS
    matrix = json.loads(capsys.readouterr().out)
    assert matrix["coverage_summary"]["denominator"] == 0

    assert run_cli(["audit", "blockers", "--store", str(db), "--json"]) == EXIT_SUCCESS
    blockers = json.loads(capsys.readouterr().out)
    assert blockers["workflow"]["next_action"] == "PREPARE_STAGE_E1"

    assert run_cli([
        "evidence", "verify", "--store", str(db),
        "--digest", source_ref["revision_digest"], "--kind", "source_identity", "--json",
    ]) == EXIT_SUCCESS
    evidence = json.loads(capsys.readouterr().out)
    assert evidence["status"] == "PASS"
    assert evidence["freshness"] == "ACTIVE"

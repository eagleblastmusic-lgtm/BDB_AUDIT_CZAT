from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.history_projection import CampaignHistoryService


def _insert_orphan(
    store: TransactionalHistoryStore,
    *,
    digest: str,
    kind: str,
    body: dict,
    schema_ref: str | None = None,
) -> None:
    con = store._connect()
    try:
        con.execute(
            "INSERT INTO immutable_objects(digest,kind,version,schema_ref,logical_id,body) VALUES(?,?,?,?,?,?)",
            (
                digest,
                kind,
                "1",
                schema_ref or f"BDB_SCHEMA_REGISTRY::{kind}/1",
                None,
                canonical_bytes(body),
            ),
        )
    finally:
        con.close()


def test_orphan_stage_lane_and_completion_rows_cannot_advance_status(tmp_path: Path) -> None:
    db = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(db, seed="ru04-orphan-status")
    store = TransactionalHistoryStore(db)

    _insert_orphan(
        store,
        digest="1" * 64,
        kind="stage_spec",
        body={"stage_key": "E5", "stage_ordinal": 5},
    )
    _insert_orphan(
        store,
        digest="2" * 64,
        kind="lane_spec",
        body={"lane_key": "lane_E5_ORPHAN"},
    )
    _insert_orphan(
        store,
        digest="3" * 64,
        kind="stage_completion",
        body={"completion_predicate_result": "STAGE_COMPLETED"},
    )

    status = api.get_campaign_status(db)
    assert status["current_stage"] == "GENESIS"
    assert status["stages_prepared"] == []
    assert status["lanes_prepared"] == []
    assert status["stage_completions_count"] == 0
    assert status["termination_state"] == "OPEN"


def test_orphan_source_identity_cannot_override_genesis_authority(tmp_path: Path) -> None:
    db = tmp_path / "campaign.sqlite"
    store = TransactionalHistoryStore(db)
    _insert_orphan(
        store,
        digest="4" * 64,
        kind="source_identity",
        body={
            "authority_mode": "AUTHORIZED_GIT",
            "git_commit_object_id": "f" * 40,
            "git_tree_object_id": "f" * 40,
            "authorized_repository_or_snapshot_ref": {"poison": True},
        },
    )

    api = AuditOperationApi()
    api.create_campaign(
        db,
        seed="ru04-source-authority",
        target_repo="https://github.com/example/authoritative",
        commit_sha="a" * 40,
    )
    source = api.get_campaign_source_identity(db)
    assert source["git_commit_object_id"] == "a" * 40
    assert source["git_tree_object_id"] == "a" * 40
    assert source["repository_authority_ref"] != {"poison": True}


def test_corrupted_commit_chain_fails_status_projection_closed(tmp_path: Path) -> None:
    db = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(db, seed="ru04-corrupt-chain")
    store = TransactionalHistoryStore(db)

    con = store._connect()
    try:
        row = con.execute("SELECT body FROM commits WHERE seq=1").fetchone()
        assert row is not None
        body = json.loads(row[0])
        body["actor_ref"] = "tampered-actor"
        con.execute("UPDATE commits SET body=? WHERE seq=1", (canonical_bytes(body),))
    finally:
        con.close()

    with pytest.raises(ValidationError, match="ACCEPTED_HISTORY_INTEGRITY_FAILURE"):
        api.get_campaign_status(db)


def test_stage_completion_count_never_implies_campaign_finished(tmp_path: Path) -> None:
    locator = tmp_path / "locator.sqlite"
    locator.touch()
    settings_mgr = SimpleNamespace(
        settings=SimpleNamespace(
            known_campaigns=[{
                "store_path": str(locator),
                "target": "example/target",
                "campaign_id": "campaign_test",
            }]
        )
    )

    class StubApi:
        @staticmethod
        def get_campaign_status(_path):
            return {
                "campaign_id": "campaign_test",
                "current_stage": "E5",
                "stages_prepared": ["E1", "E2", "E3", "E4", "E5"],
                "lanes_prepared": [],
                "stage_completions_count": 5,
                "accepted_head_seq": 99,
                "accepted_head_hash": "a" * 64,
                "termination_state": "OPEN",
                "source_generation_id": "source_gen_test",
            }

    projection = CampaignHistoryService(settings_mgr, api=StubApi()).get_known_campaigns()[0]
    assert projection.is_finished is False
    assert projection.status_label == "IN_PROGRESS"

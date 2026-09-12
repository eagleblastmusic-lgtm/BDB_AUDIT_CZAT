from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.coordinator.reference_slice import run_foundation_reference_slice, _ref_for
from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.objects import CommandEnvelope
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.history_projection import CampaignHistoryService
from bdb_audit.workflow.read_models import VerifiedCampaignReadModel, campaign_status, current_accepted_cut


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
    assert status["stages_completed"] == []
    assert status["lanes_prepared"] == []
    assert status["stage_completions_count"] == 0
    assert status["termination_state"] == "OPEN"
    assert status["campaign_completed"] is False


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


# =========================================================================
# ADVERSARIAL RU04 TESTS (A - J)
# =========================================================================

def test_adversarial_orphan_stage_completion_counterexample(tmp_path: Path) -> None:
    """A. ORPHAN STAGE COMPLETION: Main D07 counterexample.

    Injecting a validly formatted stage_completion = STAGE_COMPLETED directly into
    immutable_objects without accepted commit closure must never advance stage
    or mark it completed.
    """
    db = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(db, seed="ru04-adv-orphan-comp")
    api.prepare_stage(db, "E1")
    store = TransactionalHistoryStore(db)

    # Confirm E1 is prepared but not completed
    status_before = api.get_campaign_status(db)
    assert status_before["stages_prepared"] == ["E1"]
    assert status_before["stages_completed"] == []
    assert status_before["current_stage"] == "E1"

    # Inject orphan stage_completion purporting that E1 is complete
    _insert_orphan(
        store,
        digest="c" * 64,
        kind="stage_completion",
        body={
            "stage_completion_id": "stage_completion_orphan",
            "completion_predicate_result": "STAGE_COMPLETED",
            "stage_spec_ref": {"kind": "stage_spec", "revision_digest": "dummy"},
        },
    )

    status_after = api.get_campaign_status(db)
    assert status_after["stages_completed"] == []
    assert status_after["current_stage"] == "E1"
    assert status_after["stage_completions_count"] == 0


def test_adversarial_orphan_result_does_not_advance_closure(tmp_path: Path) -> None:
    """B. ORPHAN RESULT: Unaccepted lane/result object cannot increase accepted count."""
    db = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(db, seed="ru04-adv-orphan-res")
    store = TransactionalHistoryStore(db)

    status_init = api.get_campaign_status(db)
    initial_objects_count = status_init["total_objects_count"]

    # Insert 10 orphan objects of various kinds
    for i in range(10):
        _insert_orphan(
            store,
            digest=f"{i:02x}" + "0" * 62,
            kind="bdb_audit_lane_result",
            body={"lane_slot": "E1-A", "statement": f"Fake finding {i}"},
        )

    status_post = api.get_campaign_status(db)
    # total_objects_count in verified read model is strictly accepted closure
    assert status_post["total_objects_count"] == initial_objects_count


def test_adversarial_wrong_campaign_binding(tmp_path: Path) -> None:
    """C. WRONG CAMPAIGN: Read model with wrong campaign fails closed."""
    db1 = tmp_path / "c1.sqlite"
    db2 = tmp_path / "c2.sqlite"
    api = AuditOperationApi()
    api.create_campaign(db1, seed="campaign-alpha")
    api.create_campaign(db2, seed="campaign-beta")

    store1 = TransactionalHistoryStore(db1)
    store2 = TransactionalHistoryStore(db2)

    cut2 = current_accepted_cut(store2)

    # Attempting to query store1 with cut2 (wrong campaign_id) must fail closed
    with pytest.raises(ValidationError, match="HISTORY_CUT_INPUT_MISMATCH"):
        model = VerifiedCampaignReadModel(store1, cut=cut2)
        model.project_status()


def test_adversarial_wrong_run_binding(tmp_path: Path) -> None:
    """D. WRONG RUN / STAGE BINDING: stage_completion pointing to unaccepted stage_spec fails closed."""
    slice_data = run_foundation_reference_slice(tmp_path / "ref.sqlite", stop_at_seq=9)
    store = slice_data["store"]
    coord = slice_data["coordinator"]
    head = slice_data["head"]
    head_ref = slice_data["head_ref"]
    next_cmd = slice_data["next_cmd"]
    head_cut = slice_data["head_cut"]
    stage_run_obj = slice_data["stage_comp"].stage_run_ref

    # Prepare an unaccepted stage_spec
    from bdb_audit.orchestration.stages import StageSpec
    foreign_spec = StageSpec(
        stage_key="E1",
        stage_spec_revision="99",
        stage_role="E1",
        stage_ordinal=1,
        purpose="Foreign unaccepted stage spec",
    )
    foreign_obj = foreign_spec.as_object()

    # Create a stage_completion referencing foreign_obj (not accepted in history)
    from bdb_audit.stop.models import StageCompletion
    bad_completion = StageCompletion(
        stage_completion_id=f"stage_completion_{uuid4()}",
        stage_run_ref=stage_run_obj,
        stage_spec_ref=_ref_for("stage_completion", "stage_spec_ref", foreign_obj),
        input_history_cut=head_cut,
        required_lane_slot_results=list(slice_data["stage_comp"].required_lane_slot_results),
        completion_predicate_result="STAGE_COMPLETED",
    )

    # Accept the bad stage_completion into history, but WITHOUT accepting foreign_obj
    cmd = next_cmd(head_ref)
    coord.accept(cmd, immutable_objects=[bad_completion.as_object()], expected_head=head)

    # VerifiedCampaignReadModel must fail closed when projecting status because foreign stage_spec is not in accepted closure
    with pytest.raises(ValidationError, match="OBJECT_NOT_ACCEPTED_AT_CUT"):
        model = VerifiedCampaignReadModel(store)
        model.project_status()


def test_adversarial_wrong_or_stale_cut(tmp_path: Path) -> None:
    """E. WRONG CUT / STALE CUT: Read model on cut N cannot see objects accepted at N+1."""
    db = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(db, seed="ru04-stale-cut")
    store = TransactionalHistoryStore(db)

    cut_at_seq1 = current_accepted_cut(store)

    # Now prepare E1 (moves head to seq 2)
    api.prepare_stage(db, "E1")

    # Read model evaluated specifically at cut_at_seq1 must NOT see E1
    model_seq1 = VerifiedCampaignReadModel(store, cut=cut_at_seq1)
    status_seq1 = model_seq1.project_status()
    assert status_seq1["stages_prepared"] == []
    assert status_seq1["current_stage"] == "GENESIS"

    # Read model evaluated at current cut sees E1
    cut_at_seq2 = current_accepted_cut(store)
    model_seq2 = VerifiedCampaignReadModel(store, cut=cut_at_seq2)
    status_seq2 = model_seq2.project_status()
    assert status_seq2["stages_prepared"] == ["E1"]
    assert status_seq2["current_stage"] == "E1"


def test_adversarial_corrupted_object_digest(tmp_path: Path) -> None:
    """F. CORRUPTED OBJECT: Digest mismatch in immutable_objects fails closed."""
    db = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(db, seed="ru04-corrupt-obj")
    api.prepare_stage(db, "E1")
    store = TransactionalHistoryStore(db)

    # Tamper with the accepted stage_spec object body in SQLite
    con = store._connect()
    try:
        row = con.execute("SELECT digest, body FROM immutable_objects WHERE kind='stage_spec'").fetchone()
        assert row is not None
        spec_digest, raw_body = row
        body = json.loads(raw_body)
        body["purpose"] = "TAMPERED PURPOSE"
        con.execute("UPDATE immutable_objects SET body=? WHERE digest=?", (canonical_bytes(body), spec_digest))
    finally:
        con.close()

    # Projecting status must fail closed with ACCEPTED_HISTORY_INTEGRITY_FAILURE
    with pytest.raises(ValidationError, match="ACCEPTED_HISTORY_INTEGRITY_FAILURE"):
        api.get_campaign_status(db)


def test_adversarial_duplicate_conflicting_stage_completions(tmp_path: Path) -> None:
    """G. DUPLICATE / AMBIGUOUS AUTHORITY: Conflicting stage completions fail closed."""
    slice_data = run_foundation_reference_slice(tmp_path / "ref.sqlite", stop_at_seq=9)
    store = slice_data["store"]
    coord = slice_data["coordinator"]
    head = slice_data["head"]
    head_ref = slice_data["head_ref"]
    next_cmd = slice_data["next_cmd"]
    head_cut = slice_data["head_cut"]
    stage_spec_obj = slice_data["stage_spec_obj"]
    stage_run_obj = slice_data["stage_comp"].stage_run_ref

    # seq 9 already contains a stage_completion for E3.
    # Accept a SECOND, conflicting stage_completion for E3 with a different ID and summary.
    from bdb_audit.stop.models import StageCompletion
    second_comp = StageCompletion(
        stage_completion_id=f"stage_completion_{uuid4()}",
        stage_run_ref=stage_run_obj,
        stage_spec_ref=_ref_for("stage_completion", "stage_spec_ref", stage_spec_obj),
        input_history_cut=head_cut,
        required_lane_slot_results=list(slice_data["stage_comp"].required_lane_slot_results),
        mandatory_obligation_summary={"total_mandatory": 2, "qualified": 2},
        completion_predicate_result="STAGE_COMPLETED",
    )

    cmd = next_cmd(head_ref)
    coord.accept(cmd, immutable_objects=[second_comp.as_object()], expected_head=head)

    # Must fail closed with MULTIPLE_STAGE_COMPLETIONS
    with pytest.raises(ValidationError, match="MULTIPLE_STAGE_COMPLETIONS"):
        model = VerifiedCampaignReadModel(store)
        model.project_status()


def test_adversarial_prepared_not_equal_completed(tmp_path: Path) -> None:
    """H. PREPARED != COMPLETED: Preparation of stage & lane never marks them completed."""
    db = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(db, seed="ru04-prep-not-comp")
    api.prepare_stage(db, "E1")
    api.prepare_lane(db, "E1", slot="E1-A")
    api.prepare_lane(db, "E1", slot="E1-B")

    status = api.get_campaign_status(db)
    assert status["stages_prepared"] == ["E1"]
    assert status["stages_completed"] == []
    assert len(status["lanes_prepared"]) == 2
    assert status["stage_completions_count"] == 0
    assert status["campaign_completed"] is False
    assert status["termination_state"] == "OPEN"
    assert status["current_stage"] == "E1"


def test_adversarial_restart_determinism(tmp_path: Path) -> None:
    """I & J. RESTART & DETERMINISM: Re-opening the DB yields identical projection."""
    db = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(db, seed="ru04-restart-test")
    api.prepare_stage(db, "E1")
    api.prepare_lane(db, "E1", slot="E1-A")

    store1 = TransactionalHistoryStore(db)
    model1 = VerifiedCampaignReadModel(store1)
    status1 = model1.project_status()

    # Re-open completely fresh store instance
    store2 = TransactionalHistoryStore(db)
    model2 = VerifiedCampaignReadModel(store2)
    status2 = model2.project_status()

    assert status1 == status2
    assert status1["campaign_id"] == status2["campaign_id"]
    assert status1["accepted_head_hash"] == status2["accepted_head_hash"]

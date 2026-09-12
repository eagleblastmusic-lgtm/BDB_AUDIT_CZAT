"""Residual RU06 closure tests for D22 stage/continuation semantics."""
from pathlib import Path

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.read_models import current_accepted_cut


def test_prepared_stages_do_not_make_campaign_ready_for_stop(tmp_path: Path):
    store_path = tmp_path / "prepared_not_completed.sqlite"
    api = AuditOperationApi()
    api.create_campaign(store_path, seed="ru06-d22-prepared")

    for stage in ("E1", "E2", "E3", "E4", "E5"):
        api.prepare_stage(store_path, stage)

    status = api.get_campaign_status(store_path)
    assert status["stages_prepared"] == ["E1", "E2", "E3", "E4", "E5"]
    assert status["stages_completed"] == []
    assert status["campaign_completed"] is False

    continuation = api.continue_campaign(store_path)
    assert continuation["current_stage"] == "E1"
    assert continuation["continuation_state"] == "AWAITING_STAGE_COMPLETION"
    assert continuation["next_action"] == "AWAITING_STAGE_COMPLETION"


def test_prepared_stage_specs_preserve_normative_predecessor_requirements(tmp_path: Path):
    store_path = tmp_path / "stage_predecessors.sqlite"
    api = AuditOperationApi()
    api.create_campaign(store_path, seed="ru06-d22-predecessors")
    api.prepare_stage(store_path, "E1")
    api.prepare_stage(store_path, "E2")

    store = TransactionalHistoryStore(store_path)
    cut = current_accepted_cut(store)
    stage_rows = store.accepted_records("stage_spec", cut)
    by_key = {row["body"]["stage_key"]: row["body"] for row in stage_rows}

    assert by_key["E1"]["predecessor_requirements"] == []
    assert by_key["E2"]["predecessor_requirements"] == ["E1"]
    assert by_key["E1"]["transition_policy_ref"] == "TRANSITION_PROFILE_V1"
    assert by_key["E2"]["transition_policy_ref"] == "TRANSITION_PROFILE_V1"

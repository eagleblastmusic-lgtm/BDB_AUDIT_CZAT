"""M47 — Core Operation API and CLI Tests (R5.3 §109)."""
import json
from pathlib import Path
import tempfile

import pytest

from bdb_audit.cli import (
    run_cli,
    EXIT_SUCCESS,
    EXIT_DOMAIN_ERROR,
    EXIT_MALFORMED_ARGS,
    EXIT_CAMPAIGN_NOT_FOUND,
    EXIT_CONFLICT_ERROR,
)
from bdb_audit.coordinator.operations import AuditOperationApi


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td) / "test_campaign.sqlite"


def test_m47_happy_path_workflow(temp_store, capsys):
    """Test create -> projection -> stage -> lane -> continuation -> validation -> self-test -> build."""
    store_str = str(temp_store)

    # 1. campaign create
    rc = run_cli(["campaign", "create", "--store", store_str, "--seed", "test_seed", "--json"])
    assert rc == EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "SUCCESS"
    assert out["commit_seq"] == 1
    assert "campaign_" in out["campaign_id"]

    # 2. genesis projection and continuation
    rc = run_cli(["campaign", "status", "--store", store_str, "--json"])
    assert rc == EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "SUCCESS"
    assert out["accepted_head_seq"] == 1
    assert out["current_stage"] == "GENESIS"
    assert out["stages_prepared"] == []
    assert out["lanes_prepared"] == []

    rc = run_cli(["continue", "--store", store_str, "--json"])
    assert rc == EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["continuation_state"] == "READY_FOR_NEXT_STAGE"
    assert out["next_action"] == "PREPARE_STAGE_E1"

    # 3. stage prepare must persist/project the canonical StageSpec key
    rc = run_cli(["stage", "prepare", "--store", store_str, "--stage", "E1", "--json"])
    assert rc == EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "SUCCESS"
    assert out["stage_id"] == "E1"
    assert out["stage_key"] == "E1"
    assert out["commit_seq"] == 2

    rc = run_cli(["campaign", "status", "--store", store_str, "--json"])
    assert rc == EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["current_stage"] == "E1"
    assert out["stages_prepared"] == ["E1"]
    assert out["lanes_prepared"] == []

    # 4. lane prepare must persist/project lane_key, not UNKNOWN
    rc = run_cli(["lane", "prepare", "--store", store_str, "--stage", "E1", "--slot", "L1", "--json"])
    assert rc == EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "SUCCESS"
    assert out["stage_key"] == "E1"
    assert out["slot"] == "L1"
    assert out["lane_id"] == "lane_E1_L1"
    assert out["isolation_status"] == "QUALIFIED"
    assert out["commit_seq"] == 3

    rc = run_cli(["campaign", "status", "--store", store_str, "--json"])
    assert rc == EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["current_stage"] == "E1"
    assert out["stages_prepared"] == ["E1"]
    assert out["lanes_prepared"] == ["lane_E1_L1"]

    # 5. continuation follows the same canonical stage key domain
    rc = run_cli(["continue", "--store", store_str, "--json"])
    assert rc == EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "SUCCESS"
    assert out["current_stage"] == "E1"
    assert out["continuation_state"] == "READY_FOR_NEXT_STAGE"
    assert out["next_action"] == "PREPARE_STAGE_E2"

    # 6. validate valid artifact
    with tempfile.TemporaryDirectory() as td:
        art_path = Path(td) / "test_artifact.json"
        art_path.write_text(json.dumps({
            "kind": "stage_spec",
            "version": "1",
            "key": "E1",
            "revision": "1",
            "policy_ref": "policy:test",
            "ordinal": 1,
            "description": "test stage",
        }))
        rc = run_cli(["validate", "--artifact", str(art_path), "--kind", "stage_spec", "--json"])
        assert rc == EXIT_SUCCESS
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "PASS"
        assert out["contract_registered"] is True

    # 7. self-test
    rc = run_cli(["self-test", "--json"])
    assert rc == EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "PASS"
    assert len(out["checks"]) >= 4

    # 8. build
    with tempfile.TemporaryDirectory() as td:
        build_out = Path(td) / "custom_assistant.py"
        rc = run_cli(["build", "--output", str(build_out), "--json"])
        assert rc == EXIT_SUCCESS
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "SUCCESS"
        assert build_out.exists()


def test_m47_legacy_descriptive_stage_alias_projects_canonical_key(temp_store, capsys):
    """v2.0.0 descriptive F2 label remains accepted, but projection is canonical E1."""
    store_str = str(temp_store)
    assert run_cli(["campaign", "create", "--store", store_str, "--json"]) == EXIT_SUCCESS
    capsys.readouterr()

    assert run_cli(["stage", "prepare", "--store", store_str, "--stage", "F2_FOUNDATION", "--json"]) == EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["stage_id"] == "F2_FOUNDATION"
    assert out["stage_key"] == "E1"

    assert run_cli(["campaign", "status", "--store", store_str, "--json"]) == EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["current_stage"] == "E1"
    assert out["stages_prepared"] == ["E1"]

    assert run_cli(["continue", "--store", store_str, "--json"]) == EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["next_action"] == "PREPARE_STAGE_E2"


def test_m47_stage_order_and_lane_parent_fail_closed(temp_store, capsys):
    """Out-of-order stages and lanes for an unprepared stage must be rejected."""
    store_str = str(temp_store)
    assert run_cli(["campaign", "create", "--store", store_str, "--json"]) == EXIT_SUCCESS
    capsys.readouterr()

    rc = run_cli(["stage", "prepare", "--store", store_str, "--stage", "E2", "--json"])
    assert rc == EXIT_DOMAIN_ERROR
    err = json.loads(capsys.readouterr().err)
    assert err["error"] == "INVALID_STAGE_TRANSITION"

    rc = run_cli(["lane", "prepare", "--store", store_str, "--stage", "E1", "--slot", "L1", "--json"])
    assert rc == EXIT_DOMAIN_ERROR
    err = json.loads(capsys.readouterr().err)
    assert err["error"] == "STAGE_NOT_PREPARED"


def test_m47_malformed_arguments(capsys):
    """Missing required arguments must exit with code 2."""
    rc = run_cli(["campaign", "create"])
    assert rc == EXIT_MALFORMED_ARGS

    rc = run_cli(["stage", "prepare", "--store", "dummy.sqlite"])
    assert rc == EXIT_MALFORMED_ARGS

    rc = run_cli(["validate"])
    assert rc == EXIT_MALFORMED_ARGS


def test_m47_missing_campaign(capsys):
    """Operating on a non-existent campaign database must return EXIT_CAMPAIGN_NOT_FOUND (3)."""
    with tempfile.TemporaryDirectory() as td:
        non_existent = str(Path(td) / "non_existent.sqlite")
        rc = run_cli(["campaign", "status", "--store", non_existent, "--json"])
        assert rc == EXIT_CAMPAIGN_NOT_FOUND

        rc = run_cli(["stage", "prepare", "--store", non_existent, "--stage", "E1", "--json"])
        assert rc == EXIT_CAMPAIGN_NOT_FOUND


def test_m47_conflict_duplicate_campaign(temp_store, capsys):
    """Creating campaign over an already-initialized store must return EXIT_CONFLICT_ERROR (4)."""
    store_str = str(temp_store)
    rc1 = run_cli(["campaign", "create", "--store", store_str, "--json"])
    assert rc1 == EXIT_SUCCESS

    rc2 = run_cli(["campaign", "create", "--store", store_str, "--json"])
    assert rc2 == EXIT_CONFLICT_ERROR


def test_m47_invalid_artifact_validation(capsys):
    """Invalid artifacts must fail closed with EXIT_DOMAIN_ERROR (1)."""
    with tempfile.TemporaryDirectory() as td:
        bad_json = Path(td) / "bad.json"
        bad_json.write_text("{ unquoted_key: 123 ")
        rc = run_cli(["validate", "--artifact", str(bad_json), "--json"])
        assert rc == EXIT_DOMAIN_ERROR

        no_kind = Path(td) / "no_kind.json"
        no_kind.write_text(json.dumps({"some_data": 42}))
        rc = run_cli(["validate", "--artifact", str(no_kind), "--json"])
        assert rc == EXIT_DOMAIN_ERROR

        unreg = Path(td) / "unreg.json"
        unreg.write_text(json.dumps({"kind": "totally_unregistered_kind", "version": "1"}))
        rc = run_cli(["validate", "--artifact", str(unreg), "--json"])
        assert rc == EXIT_DOMAIN_ERROR

        mismatch = Path(td) / "mismatch.json"
        mismatch.write_text(json.dumps({"kind": "stage_spec", "version": "1"}))
        rc = run_cli(["validate", "--artifact", str(mismatch), "--kind", "lane_spec", "--json"])
        assert rc == EXIT_DOMAIN_ERROR

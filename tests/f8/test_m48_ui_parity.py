"""M48 — Interactive UI and CLI/API/UI Parity Tests (R5.3 §110)."""
import json
from pathlib import Path
import tempfile

import pytest

from bdb_audit.cli import run_cli, EXIT_SUCCESS
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.ui import InteractiveAuditUI


def test_m48_ui_and_api_and_cli_parity():
    """Verify that API, CLI, and UI operations invoke identical semantics and state."""
    with tempfile.TemporaryDirectory() as td:
        store_api = Path(td) / "store_api.sqlite"
        store_cli = Path(td) / "store_cli.sqlite"
        store_ui = Path(td) / "store_ui.sqlite"

        api = AuditOperationApi()
        ui = InteractiveAuditUI(api=api)

        # 1. Campaign creation parity
        res_api = api.create_campaign(store_api, seed="parity_seed", campaign_id="campaign_parity")
        res_ui = ui.handle_create_campaign(str(store_ui), seed="parity_seed", campaign_id="campaign_parity")
        rc_cli = run_cli(["campaign", "create", "--store", str(store_cli), "--seed", "parity_seed", "--campaign-id", "campaign_parity", "--json"])
        assert rc_cli == EXIT_SUCCESS

        assert res_api["status"] == "SUCCESS"
        assert res_ui["status"] == "SUCCESS"
        assert res_api["commit_seq"] == 1
        assert res_ui["commit_seq"] == 1

        # Check commit hash equality across deterministic setups
        assert res_api["commit_hash"] == res_ui["commit_hash"]

        # 2. Campaign status parity
        stat_api = api.get_campaign_status(store_api)
        stat_ui = ui.handle_campaign_status(str(store_ui))
        assert stat_api["current_stage"] == stat_ui["current_stage"]
        assert stat_api["accepted_head_seq"] == stat_ui["accepted_head_seq"]
        assert stat_api["accepted_head_hash"] == stat_ui["accepted_head_hash"]

        # 3. Stage prepare parity
        stage_api = api.prepare_stage(store_api, stage_id="E1", stage_spec_revision="1")
        stage_ui = ui.handle_prepare_stage("E1", store_path=str(store_ui), stage_spec_revision="1")
        assert stage_api["commit_seq"] == stage_ui["commit_seq"] == 2
        assert stage_api["stage_spec_digest"] == stage_ui["stage_spec_digest"]
        assert stage_api["commit_hash"] == stage_ui["commit_hash"]

        # 4. Lane prepare parity
        lane_api = api.prepare_lane(store_api, stage_id="E1", slot="L1", lane_spec_revision="1")
        lane_ui = ui.handle_prepare_lane("E1", "L1", store_path=str(store_ui), lane_spec_revision="1")
        assert lane_api["commit_seq"] == lane_ui["commit_seq"] == 3
        assert lane_api["lane_spec_digest"] == lane_ui["lane_spec_digest"]
        assert lane_api["commit_hash"] == lane_ui["commit_hash"]

        # 5. Validation parity
        from bdb_audit.orchestration.stages import initial_stage_specs
        e1_spec = initial_stage_specs()[0]
        art = {
            "kind": "stage_spec",
            "version": "1",
            **e1_spec.body(),
        }
        art_path = Path(td) / "test_stage.json"
        art_path.write_text(json.dumps(art))

        val_api = api.validate_artifact(art_path)
        val_ui = ui.handle_validate(str(art_path))
        assert val_api["status"] == val_ui["status"] == "PASS"
        assert val_api["digest"] == val_ui["digest"]

        # 6. Self-test parity
        st_api = api.run_self_test(deep=False)
        st_ui = ui.handle_self_test(deep=False)
        assert st_api["status"] == st_ui["status"] == "PASS"
        assert len(st_api["checks"]) == len(st_ui["checks"])


def test_m48_ui_scripted_menu_loop():
    """Test interactive menu driven by scripted inputs (create, status, self-test, exit)."""
    with tempfile.TemporaryDirectory() as td:
        store_path = str(Path(td) / "scripted_ui.sqlite")

        # Scripted inputs sequence:
        # 1. Create campaign: choice 1, store_path, seed
        # 2. Check status: choice 2, store_path
        # 3. Prepare stage: choice 3, stage E1
        # 4. Run self-test: choice 7, n
        # 5. Invalid choice: choice 99
        # 6. Exit: choice 9
        inputs = iter([
            "1", store_path, "scripted_seed",
            "2", store_path,
            "3", "E1",
            "7", "n",
            "99",
            "9",
        ])

        outputs = []
        ui = InteractiveAuditUI()
        ret = ui.run_advanced_menu_loop(input_func=lambda prompt="": next(inputs), output_func=lambda msg: outputs.append(msg))

        assert ret == 0
        all_output = "\n".join(outputs)
        assert "Campaign created ID=" in all_output
        assert "STATUS: Stage=" in all_output
        assert "Stage E1 prepared" in all_output
        assert "SELF-TEST: PASS" in all_output
        assert "Invalid option '99'" in all_output
        assert "Returning to main menu." in all_output


def test_m48_ui_error_handling():
    """UI captures and formats domain errors without crashing."""
    ui = InteractiveAuditUI()

    # 1. Operating without store
    with pytest.raises(ValueError):
        ui.handle_campaign_status(None)

    # 2. Operating on missing file
    with pytest.raises(Exception):
        ui.handle_campaign_status("non_existent_file.sqlite")
    assert ui.last_error is not None
    assert ui.last_result["status"] == "FAIL"

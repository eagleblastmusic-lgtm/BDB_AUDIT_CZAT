"""Targeted tests for BDB Audit v2.0.3 UI menus and workflow interaction."""
from __future__ import annotations

from pathlib import Path
import pytest

from bdb_audit.ui import InteractiveAuditUI
from bdb_audit.workflow.settings import SettingsManager
from bdb_audit.workflow.platform import MockPlatformAdapter


@pytest.fixture
def ui_test_env(tmp_path: Path):
    cfg_file = tmp_path / "ui_settings.json"
    mgr = SettingsManager(config_path=cfg_file)
    mgr.settings.github_repo_url = "https://github.com/example/ui-repo"
    mgr.settings.github_default_ref = "main"
    mgr.settings.output_work_dir = str(tmp_path / "ui_work")
    mgr.save()

    mock_platform = MockPlatformAdapter()
    ui = InteractiveAuditUI(settings_mgr=mgr, platform_adapter=mock_platform)
    return ui, mgr, mock_platform, tmp_path


def test_main_menu_renders_simplified_v2_0_3_options(ui_test_env):
    ui, mgr, mock_platform, tmp = ui_test_env
    inputs = iter(["7"])  # Exit
    outputs = []

    rc = ui.run_menu_loop(input_func=lambda prompt="": next(inputs), output_func=outputs.append)
    assert rc == 0
    text = "\n".join(outputs)
    assert "BDB AUDIT v2.0.3" in text
    assert "1. Run Full Audit" in text
    assert "2. Continue Audit" in text
    assert "3. Audit Status & Results" in text
    assert "4. Settings" in text
    assert "5. Audit History" in text
    assert "6. Advanced" in text
    assert "7. Exit" in text


def test_settings_menu_interaction_and_toggles(ui_test_env):
    ui, mgr, mock_platform, tmp = ui_test_env
    # 4 (Settings), 6 (Toggle clipboard), 9 (Back), 7 (Exit)
    inputs = iter([
        "4",
        "6",
        "9",
        "7",
    ])
    outputs = []
    rc = ui.run_menu_loop(input_func=lambda prompt="": next(inputs), output_func=outputs.append)
    assert rc == 0
    assert mgr.settings.auto_copy_clipboard is False  # Was toggled from default True


def test_audit_status_dashboard_renders(ui_test_env):
    ui, mgr, mock_platform, tmp = ui_test_env
    # 3 (Audit Status), 7 (Exit)
    inputs = iter([
        "3",
        "7",
    ])
    outputs = []
    rc = ui.run_menu_loop(input_func=lambda prompt="": next(inputs), output_func=outputs.append)
    assert rc == 0
    text = "\n".join(outputs)
    assert "AUDIT STATUS & RESULTS" in text
    assert "Stage progress:" in text
    assert "E1     .... NOT_STARTED" in text


def test_audit_history_menu_renders(ui_test_env):
    ui, mgr, mock_platform, tmp = ui_test_env
    # 5 (Audit History), ENTER to return, 7 (Exit)
    inputs = iter([
        "5",
        "",
        "7",
    ])
    outputs = []
    rc = ui.run_menu_loop(input_func=lambda prompt="": next(inputs), output_func=outputs.append)
    assert rc == 0
    text = "\n".join(outputs)
    assert "AUDIT HISTORY" in text


def test_advanced_menu_contains_all_legacy_technical_operations(ui_test_env):
    ui, mgr, mock_platform, tmp = ui_test_env
    # 6 (Enter Advanced), 9 (Back to main), 7 (Exit main)
    inputs = iter([
        "6",
        "9",
        "7",
    ])
    outputs = []
    rc = ui.run_menu_loop(input_func=lambda prompt="": next(inputs), output_func=outputs.append)
    assert rc == 0
    text = "\n".join(outputs)
    assert "BDB Audit v2.0.3 — Advanced Control Surface" in text
    assert "1. Create Campaign" in text
    assert "2. Campaign Status" in text
    assert "3. Prepare Stage" in text
    assert "4. Prepare Lane" in text
    assert "5. Validate Artifact" in text
    assert "6. Continue Campaign / Check STOP State" in text
    assert "7. Run Self-Test" in text
    assert "8. Build Standalone Assistant" in text
    assert "9. Back to Main Menu" in text
    assert "10. Evaluate STOP Gate" in text


def test_continue_audit_detects_unfinished_campaign(ui_test_env):
    ui, mgr, mock_platform, tmp = ui_test_env
    # Create campaign first to create unfinished campaign in index
    store = tmp / "unfinished.sqlite"
    ui.handle_create_campaign(str(store), seed="unfinished_seed")

    # 2 (Continue Audit), 'n' (Back to menu), 7 (Exit)
    inputs = iter([
        "2",
        "n",
        "7",
    ])
    outputs = []
    rc = ui.run_menu_loop(input_func=lambda prompt="": next(inputs), output_func=outputs.append)
    assert rc == 0
    text = "\n".join(outputs)
    assert "UNFINISHED AUDIT DETECTED" in text
    assert "unfinished.sqlite" in text

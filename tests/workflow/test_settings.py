"""Unit tests for BDB Audit v2.0.3 persistent user settings."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import pytest

from bdb_audit.workflow.settings import (
    UserSettings,
    SettingsManager,
    get_default_settings_path,
    SCHEMA_VERSION,
)


def test_settings_default_values():
    settings = UserSettings()
    assert settings.schema_version == SCHEMA_VERSION
    assert settings.execution_mode == "ChatGPT / GitHub"
    assert settings.model == "Sol 5.6"
    assert settings.github_repo_url == "https://github.com/eagleblastmusic-lgtm/Archive"
    assert settings.github_default_ref == "main"
    assert settings.auto_copy_clipboard is True
    assert settings.auto_open_explorer is True
    assert settings.auto_open_zip_selector is True


def test_settings_persistence_across_reloads(tmp_path: Path):
    cfg_file = tmp_path / "user_settings.json"
    mgr1 = SettingsManager(config_path=cfg_file)
    mgr1.settings.github_repo_url = "https://github.com/my-org/custom-repo"
    mgr1.settings.github_default_ref = "develop"
    mgr1.settings.execution_mode = "Codex"
    mgr1.settings.model = "Sol 5.6 ultra"
    mgr1.settings.auto_copy_clipboard = False
    mgr1.save()

    assert cfg_file.exists()

    # Process restart simulation: load from fresh manager
    mgr2 = SettingsManager(config_path=cfg_file)
    assert mgr2.settings.github_repo_url == "https://github.com/my-org/custom-repo"
    assert mgr2.settings.github_default_ref == "develop"
    assert mgr2.settings.execution_mode == "Codex"
    assert mgr2.settings.model == "Sol 5.6 ultra"
    assert mgr2.settings.auto_copy_clipboard is False


def test_github_repo_remembered_until_explicitly_changed(tmp_path: Path):
    cfg_file = tmp_path / "target_memory.json"
    mgr = SettingsManager(config_path=cfg_file)
    mgr.settings.github_repo_url = "https://github.com/remembered-org/repo-alpha"
    mgr.save()

    # Multiple reloads simulate separate CLI/UI runs
    for _ in range(3):
        reloaded = SettingsManager(config_path=cfg_file)
        assert reloaded.settings.github_repo_url == "https://github.com/remembered-org/repo-alpha"

    # Explicit change
    mgr.settings.github_repo_url = "https://github.com/remembered-org/repo-beta"
    mgr.save()

    reloaded = SettingsManager(config_path=cfg_file)
    assert reloaded.settings.github_repo_url == "https://github.com/remembered-org/repo-beta"


def test_invalid_corrupted_config_fails_safe_to_defaults(tmp_path: Path):
    cfg_file = tmp_path / "corrupted_settings.json"
    cfg_file.write_text("{ this is definitely not valid JSON ::: }}}", encoding="utf-8")

    mgr = SettingsManager(config_path=cfg_file)
    # Must recover safely to default settings without crashing
    assert mgr.settings.schema_version == SCHEMA_VERSION
    assert mgr.settings.execution_mode == "ChatGPT / GitHub"
    assert mgr.settings.github_repo_url == "https://github.com/eagleblastmusic-lgtm/Archive"


def test_atomic_save_leaves_no_temporary_garbage(tmp_path: Path):
    cfg_file = tmp_path / "atomic_settings.json"
    mgr = SettingsManager(config_path=cfg_file)
    mgr.settings.model = "Sol 5.6 high"
    mgr.save()

    assert cfg_file.exists()
    # Ensure no leftover .tmp files
    tmp_files = list(tmp_path.glob("*.tmp*"))
    assert len(tmp_files) == 0


def test_no_credential_fields_in_persisted_settings(tmp_path: Path):
    cfg_file = tmp_path / "security_settings.json"
    mgr = SettingsManager(config_path=cfg_file)

    # Attempt to inject credentials into raw dictionary representation
    raw = mgr.settings.to_dict()
    raw["api_token"] = "ghp_super_secret_token_12345"
    raw["user_password"] = "hunter2"
    raw["secret_key"] = "my_private_key"

    loaded = UserSettings.from_dict(raw)
    out_dict = loaded.to_dict()

    for forbidden in ("api_token", "user_password", "secret_key"):
        assert forbidden not in out_dict
        assert not hasattr(loaded, forbidden)


def test_campaign_locator_recording(tmp_path: Path):
    cfg_file = tmp_path / "history_settings.json"
    mgr = SettingsManager(config_path=cfg_file)
    db1 = tmp_path / "camp1.sqlite"
    db2 = tmp_path / "camp2.sqlite"

    mgr.record_campaign(db1, "campaign_001", "my-target-1")
    mgr.record_campaign(db2, "campaign_002", "my-target-2")

    assert len(mgr.settings.known_campaigns) == 2
    assert mgr.settings.known_campaigns[0]["campaign_id"] == "campaign_002"
    assert mgr.settings.known_campaigns[1]["campaign_id"] == "campaign_001"
    assert mgr.settings.last_campaign_store == str(db2.resolve())

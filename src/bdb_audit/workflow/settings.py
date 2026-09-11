"""Persistent User Settings for BDB Audit v2.0.3.

Provides local preferences and configuration preserved across process restarts.
Settings are NOT canonical campaign authority and are never recorded as accepted
campaign facts.

Settings are saved in a per-user, OS-appropriate application directory (e.g.
%LOCALAPPDATA%\\BDBAudit\\settings.json on Windows) using atomic write operations
and versioned schema. Never saves tokens, passwords, or credentials.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

SCHEMA_VERSION = 1
SETTINGS_ENV_VAR = "BDB_AUDIT_SETTINGS_PATH"
FORBIDDEN_CREDENTIAL_KEYWORDS = ("TOKEN", "PASSWORD", "SECRET", "CREDENTIAL", "API_KEY", "PRIVATE_KEY")


def get_default_settings_path() -> Path:
    """Resolve the default persistent settings file path for the active OS."""
    override = os.environ.get(SETTINGS_ENV_VAR)
    if override:
        return Path(override).resolve()

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "BDBAudit" / "settings.json"

    # Unix / Linux / macOS or Windows fallback
    home = Path.home()
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "bdb-audit" / "settings.json"
    return home / ".config" / "bdb-audit" / "settings.json"


@dataclass
class UserSettings:
    """Schema-versioned user preferences dataclass."""
    schema_version: int = SCHEMA_VERSION
    execution_mode: str = "ChatGPT / GitHub"
    model: str = "Sol 5.6"
    github_repo_url: str = "https://github.com/eagleblastmusic-lgtm/Archive"
    github_default_ref: str = "main"
    local_repo_path: str = ""
    local_default_ref: str = "main"
    output_work_dir: str = field(default_factory=lambda: str(Path.home() / "BDBAuditWork"))
    auto_copy_clipboard: bool = True
    auto_open_explorer: bool = True
    auto_open_zip_selector: bool = True
    known_campaigns: list[dict[str, str]] = field(default_factory=list)
    last_campaign_store: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Security filter: ensure no credential fields exist
        sanitized = {}
        for k, v in data.items():
            upper = k.upper()
            if any(forbidden in upper for forbidden in FORBIDDEN_CREDENTIAL_KEYWORDS):
                continue
            sanitized[k] = v
        return sanitized

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> UserSettings:
        if not isinstance(raw, dict):
            return cls()

        # Reject/ignore forbidden credential fields
        safe_kwargs = {}
        for k, v in raw.items():
            upper = str(k).upper()
            if any(forbidden in upper for forbidden in FORBIDDEN_CREDENTIAL_KEYWORDS):
                continue
            if hasattr(cls, k):
                safe_kwargs[k] = v

        try:
            return cls(**safe_kwargs)
        except Exception:
            return cls()


class SettingsManager:
    """Manages persistent loading and atomic saving of UserSettings."""

    def __init__(self, config_path: str | Path | None = None):
        self.path = Path(config_path).resolve() if config_path else get_default_settings_path()
        self.settings: UserSettings = self.load()

    def load(self) -> UserSettings:
        """Load settings from disk with fail-safe recovery to defaults."""
        if not self.path.exists():
            return UserSettings()

        try:
            text = self.path.read_text(encoding="utf-8")
            data = json.loads(text)
            if not isinstance(data, dict):
                return UserSettings()
            return UserSettings.from_dict(data)
        except Exception:
            # Corrupted file: return defaults rather than crashing
            return UserSettings()

    def save(self) -> None:
        """Atomically persist current settings to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = self.settings.to_dict()
        data["schema_version"] = SCHEMA_VERSION
        content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"

        # Atomic write: write to temp file in same directory, then rename/replace
        temp_file = self.path.with_suffix(f".tmp.{os.getpid()}")
        try:
            temp_file.write_text(content, encoding="utf-8")
            temp_file.replace(self.path)
        except Exception:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            raise

    def record_campaign(self, store_path: str | Path, campaign_id: str, target: str) -> None:
        """Record a campaign locator in the history index."""
        resolved = str(Path(store_path).resolve())
        # Avoid duplicate locators
        self.settings.known_campaigns = [
            c for c in self.settings.known_campaigns if c.get("store_path") != resolved
        ]
        import datetime
        self.settings.known_campaigns.insert(0, {
            "campaign_id": campaign_id,
            "store_path": resolved,
            "target": target,
            "recorded_at": datetime.datetime.now().isoformat(),
        })
        # Keep maximum 50 most recent campaigns in index
        self.settings.known_campaigns = self.settings.known_campaigns[:50]
        self.settings.last_campaign_store = resolved
        self.save()


def get_default_settings_manager() -> SettingsManager:
    return SettingsManager()


__all__ = [
    "SCHEMA_VERSION",
    "SETTINGS_ENV_VAR",
    "UserSettings",
    "SettingsManager",
    "get_default_settings_path",
    "get_default_settings_manager",
]

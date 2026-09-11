"""Campaign Locator and History Projection service for BDB Audit v2.0.3.

Provides lightweight projection and discovery over persistent campaign databases.
The local history index stores only LOCATORS (filesystem paths and targets), NEVER
accepted campaign authority. True status, stage, and completion are always
reconstructed dynamically from the SQLite campaign store.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..coordinator.operations import AuditOperationApi
from ..history.store import TransactionalHistoryStore
from .settings import SettingsManager


@dataclass(frozen=True)
class CampaignProjection:
    """Read-only operational projection reconstructed directly from campaign store."""
    campaign_id: str
    store_path: Path
    target_display: str
    source_identity: str
    current_stage: str
    stages_prepared: list[str]
    lanes_prepared: list[str]
    stage_completions_count: int
    accepted_head_seq: int
    accepted_head_hash: str
    is_finished: bool
    status_label: str  # "IN_PROGRESS" | "COMPLETED" | "NOT_FOUND"
    error: str | None = None


class CampaignHistoryService:
    """Projects status and details for campaigns registered in user settings."""

    def __init__(self, settings_mgr: SettingsManager, api: AuditOperationApi | None = None):
        self.settings_mgr = settings_mgr
        self.api = api or AuditOperationApi()

    def get_known_campaigns(self) -> list[CampaignProjection]:
        """Reconstruct projections for all known campaign stores."""
        projections = []
        for entry in self.settings_mgr.settings.known_campaigns:
            store_str = entry.get("store_path")
            target = entry.get("target", "Unknown Target")
            cid = entry.get("campaign_id", "Unknown ID")
            if not store_str:
                continue

            p = Path(store_str)
            if not p.exists():
                projections.append(CampaignProjection(
                    campaign_id=cid,
                    store_path=p,
                    target_display=target,
                    source_identity="STORE_FILE_MISSING",
                    current_stage="UNKNOWN",
                    stages_prepared=[],
                    lanes_prepared=[],
                    stage_completions_count=0,
                    accepted_head_seq=0,
                    accepted_head_hash="",
                    is_finished=False,
                    status_label="NOT_FOUND",
                    error="Store file does not exist on disk",
                ))
                continue

            try:
                status = self.api.get_campaign_status(p)
                current_stage = status.get("current_stage", "GENESIS")
                stages_prep = status.get("stages_prepared", [])
                lanes_prep = status.get("lanes_prepared", [])
                completions = status.get("stage_completions_count", 0)
                is_completed = current_stage == "STOP" or completions >= 5
                status_label = "COMPLETED" if is_completed else "IN_PROGRESS"

                projections.append(CampaignProjection(
                    campaign_id=status.get("campaign_id", cid),
                    store_path=p,
                    target_display=target,
                    source_identity=status.get("source_generation_id", target),
                    current_stage=current_stage,
                    stages_prepared=stages_prep,
                    lanes_prepared=lanes_prep,
                    stage_completions_count=completions,
                    accepted_head_seq=status.get("accepted_head_seq", 0),
                    accepted_head_hash=status.get("accepted_head_hash", ""),
                    is_finished=is_completed,
                    status_label=status_label,
                    error=None,
                ))
            except Exception as exc:
                projections.append(CampaignProjection(
                    campaign_id=cid,
                    store_path=p,
                    target_display=target,
                    source_identity="CORRUPTED_STORE",
                    current_stage="UNKNOWN",
                    stages_prepared=[],
                    lanes_prepared=[],
                    stage_completions_count=0,
                    accepted_head_seq=0,
                    accepted_head_hash="",
                    is_finished=False,
                    status_label="ERROR",
                    error=str(exc),
                ))

        return projections

    def get_latest_unfinished_campaign(self) -> CampaignProjection | None:
        """Find the most recent unfinished campaign eligible for resume."""
        for proj in self.get_known_campaigns():
            if proj.status_label == "IN_PROGRESS":
                return proj
        return None


__all__ = [
    "CampaignProjection",
    "CampaignHistoryService",
]

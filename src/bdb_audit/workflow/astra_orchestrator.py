"""Astra continuation orchestration for the real external user workflow.

This adapter extends the qualified v2.0.3 E1 workflow without weakening its
accepted-history authority.  It prepares durable post-E1 assignments/packages,
restores them after restart, imports result ZIPs through the raw-first inbox,
and advances only after an accepted StageCompletion exists.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from .astra_stage_profiles import apply_astra_stage_profiles
from .inbox import ImportedResultSummary
from .orchestrator import FullAuditOrchestrator
from .post_e1_inbox import PostE1ResultInbox
from .stage_transport import StageBatch, load_stage_batch, prepare_stage_batch, stage_slots


_BASELINE_STAGES = ("E1", "E2", "E3", "E4", "E5")


class AstraContinuationOrchestrator(FullAuditOrchestrator):
    """Real external E1->E5 continuation over durable packages/results."""

    def __init__(self, *args: Any, **kwargs: Any):
        apply_astra_stage_profiles()
        super().__init__(*args, **kwargs)
        self.stage_batch: StageBatch | None = None
        self.stage_inbox: PostE1ResultInbox | None = None

    def _status(self) -> dict[str, Any]:
        if not self.active_store_path:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        return self.api.get_campaign_status(self.active_store_path)

    def _next_incomplete_stage(self) -> str | None:
        status = self._status()
        completed = set(status.get("stages_completed", []))
        return next((stage for stage in _BASELINE_STAGES if stage not in completed), None)

    def _ensure_post_e1_lane_specs(self, stage_id: str) -> None:
        if not self.active_store_path:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        stage = stage_id.upper()
        status = self.api.get_campaign_status(self.active_store_path)
        if stage not in status.get("stages_prepared", []):
            self.api.prepare_stage(self.active_store_path, stage)
            status = self.api.get_campaign_status(self.active_store_path)
        prepared = set(status.get("lanes_prepared", []))
        for slot in stage_slots(stage):
            lane_key = f"lane_{stage}_{slot}"
            if lane_key not in prepared:
                self.api.prepare_lane(self.active_store_path, stage, slot=slot)
                prepared.add(lane_key)

    def prepare_post_e1_stage(self, stage_id: str) -> StageBatch:
        """Prepare and persist the next real external stage package batch."""
        if not self.active_store_path or not self.active_store_path.exists():
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        if not self.resolved_source:
            raise ValidationError("SOURCE_IDENTITY_REQUIRED")
        stage = stage_id.upper()
        if stage not in {"E2", "E3", "E4", "E5", "E6"}:
            raise ValidationError("POST_E1_STAGE_UNSUPPORTED", stage)

        status = self.api.get_campaign_status(self.active_store_path)
        completed = set(status.get("stages_completed", []))
        predecessor = {"E2": "E1", "E3": "E2", "E4": "E3", "E5": "E4", "E6": "E5"}[stage]
        if predecessor not in completed:
            raise ValidationError("PREDECESSOR_STAGE_NOT_COMPLETED", predecessor)

        self._ensure_post_e1_lane_specs(stage)
        store = TransactionalHistoryStore(self.active_store_path)
        batch = prepare_stage_batch(
            store=store,
            output_dir=self._artifact_root(),
            source_info=self.resolved_source,
            execution_mode=self.settings.execution_mode,
            model=self.settings.model,
            stage_id=stage,
            slots=stage_slots(stage),
        )
        self.stage_batch = batch
        self.stage_inbox = PostE1ResultInbox(store, batch)
        return batch

    def deliver_post_e1_lane(self, slot: str) -> dict[str, Any]:
        if not self.stage_batch:
            raise ValidationError("POST_E1_BATCH_NOT_PREPARED")
        job = self.stage_batch.get_job(slot)
        clipboard_ok = False
        explorer_ok = False
        if self.settings.auto_copy_clipboard:
            clipboard_ok = self.platform.copy_to_clipboard(job.prompt_text)
        if self.settings.auto_open_explorer:
            explorer_ok = self.platform.open_and_select(job.package_zip_path)
        return {
            "stage_id": self.stage_batch.stage_id,
            "lane_slot": slot,
            "package_zip_path": str(job.package_zip_path),
            "package_zip_name": job.package_zip_path.name,
            "assignment_ref": dict(job.assignment_ref),
            "attempt_ref": dict(job.attempt_ref),
            "prompt_copied": clipboard_ok if self.settings.auto_copy_clipboard else None,
            "explorer_selected": explorer_ok if self.settings.auto_open_explorer else None,
            "required_isolation": job.required_isolation,
            "actual_isolation": job.actual_isolation,
        }

    def import_post_e1_results(self, zip_paths: Sequence[Path | str]) -> ImportedResultSummary:
        if not self.stage_inbox:
            raise ValidationError("POST_E1_RESULT_INBOX_NOT_INITIALIZED")
        return self.stage_inbox.ingest_multiple_zips(zip_paths)

    def _load_current_post_e1_batch(self, stage_id: str) -> bool:
        if not self.active_store_path:
            return False
        store = TransactionalHistoryStore(self.active_store_path)
        try:
            batch, source = load_stage_batch(store, self._artifact_root(), stage_id)
        except ValidationError as exc:
            if exc.code == "RESUME_PACKAGE_STATE_MISSING":
                return False
            raise
        self.resolved_source = source
        self.stage_batch = batch
        self.stage_inbox = PostE1ResultInbox(store, batch)
        return True

    def resume_campaign(self, store_path: Path | str) -> dict[str, Any]:
        base = super().resume_campaign(store_path)
        if base.get("status") != "SUCCESS":
            return base

        status = self.api.get_campaign_status(Path(store_path).resolve())
        completed = set(status.get("stages_completed", []))
        next_stage = next((stage for stage in _BASELINE_STAGES if stage not in completed), None)
        post_stage_loaded = False
        post_missing: list[str] = []
        post_accepted = 0
        post_required = 0
        post_complete = False
        if next_stage and next_stage != "E1":
            post_stage_loaded = self._load_current_post_e1_batch(next_stage)
            if post_stage_loaded and self.stage_inbox is not None:
                post_required = len(self.stage_inbox.lane_statuses)
                post_accepted = sum(1 for row in self.stage_inbox.lane_statuses.values() if row.status == "ACCEPTED")
                post_missing = [slot for slot, row in self.stage_inbox.lane_statuses.items() if row.status != "ACCEPTED"]
                post_complete = self.stage_inbox.stage_complete

        return {
            **base,
            "current_stage": next_stage or "STOP",
            "post_e1_batch_loaded": post_stage_loaded,
            "post_e1_accepted_lanes_count": post_accepted,
            "post_e1_total_required_lanes": post_required,
            "post_e1_missing_lanes": post_missing,
            "post_e1_stage_complete": post_complete,
            "next_action": (
                "EVALUATE_STOP_GATE"
                if next_stage is None
                else "IMPORT_STAGE_RESULTS"
                if post_stage_loaded and not post_complete
                else "PREPARE_STAGE_PACKAGES"
                if next_stage != "E1"
                else "IMPORT_MISSING_E1_RESULTS"
            ),
        }

    def advance_to_next_stage(self) -> dict[str, Any]:
        """Prepare the next real stage instead of synthetic qualification."""
        if not self.active_store_path:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        status = self.api.get_campaign_status(self.active_store_path)
        completed = set(status.get("stages_completed", []))
        next_stage = next((stage for stage in _BASELINE_STAGES if stage not in completed), None)

        if next_stage == "E1":
            if not self.e1_inbox or not self.e1_inbox.stage_complete:
                return {
                    "status": "BLOCKED",
                    "current_stage": "E1",
                    "reason": "E1 is not yet complete",
                    "next_action": "IMPORT_MISSING_E1_RESULTS",
                }
            status = self.api.get_campaign_status(self.active_store_path)
            completed = set(status.get("stages_completed", []))
            next_stage = next((stage for stage in _BASELINE_STAGES if stage not in completed), None)

        if next_stage is None:
            return {
                "status": "READY_FOR_STOP_EVALUATION",
                "current_stage": "E5",
                "next_action": "EVALUATE_STOP_GATE",
            }

        if next_stage == "E3" and self.settings.execution_mode == "ChatGPT / GitHub":
            # Manual chat transport is DECLARED.  R5.3 blind E3 lanes require
            # ENFORCED isolation, so do not manufacture packages that could
            # never qualify their LaneCompletion.
            return {
                "status": "BLOCKED",
                "current_stage": "E3",
                "reason": "E3 requires ENFORCED isolation; ChatGPT / GitHub manual transport provides DECLARED only",
                "next_action": "CONFIGURE_ENFORCED_E3_EXECUTOR",
            }

        batch = self.prepare_post_e1_stage(next_stage)
        return {
            "status": "STAGE_READY",
            "current_stage": next_stage,
            "next_action": "DELIVER_STAGE_PACKAGES",
            "lane_slots": list(batch.lane_slots),
            "frozen_history_cut": dict(batch.frozen_history_cut),
            "package_paths": {slot: str(job.package_zip_path) for slot, job in batch.jobs.items()},
        }

    def get_dashboard_summary(self) -> dict[str, Any]:
        summary = super().get_dashboard_summary()
        if not self.active_store_path:
            return summary
        status = self.api.get_campaign_status(self.active_store_path)
        completed = set(status.get("stages_completed", []))
        prepared = set(status.get("stages_prepared", []))
        stages: dict[str, str] = {}
        for stage in _BASELINE_STAGES:
            if stage in completed:
                stages[stage] = "COMPLETE"
            elif self.stage_batch and self.stage_batch.stage_id == stage and self.stage_inbox:
                stages[stage] = "COMPLETE" if self.stage_inbox.stage_complete else "IN_PROGRESS"
            elif stage in prepared:
                stages[stage] = "PREPARED"
            else:
                stages[stage] = "NOT_STARTED"
        stages["STOP"] = "READY" if all(stage in completed for stage in _BASELINE_STAGES) else "PENDING"
        summary["stages"] = stages
        if self.stage_batch and self.stage_inbox:
            summary["current_stage_lanes"] = {
                slot: row.status for slot, row in self.stage_inbox.lane_statuses.items()
            }
            summary["current_external_stage"] = self.stage_batch.stage_id
        else:
            summary["current_stage_lanes"] = {}
            summary["current_external_stage"] = None
        return summary


__all__ = ["AstraContinuationOrchestrator"]

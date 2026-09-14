"""Astra continuation terminal UI over the qualified v2.0.3 base UI."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .coordinator.operations import AuditOperationApi
from .ui import InteractiveAuditUI
from .workflow.astra_orchestrator import AstraContinuationOrchestrator
from .workflow.platform import DefaultPlatformAdapter, PlatformAdapter
from .workflow.settings import SettingsManager, get_default_settings_manager


class AstraInteractiveAuditUI(InteractiveAuditUI):
    """Interactive UI with durable post-E1 Astra continuation."""

    def __init__(
        self,
        api: AuditOperationApi | None = None,
        settings_mgr: SettingsManager | None = None,
        platform_adapter: PlatformAdapter | None = None,
    ) -> None:
        super().__init__(api=api, settings_mgr=settings_mgr, platform_adapter=platform_adapter)
        self.astra_orchestrator = AstraContinuationOrchestrator(
            settings_mgr=self.settings_mgr,
            platform_adapter=self.platform,
            api=self.api,
        )
        # Inherited base handlers still use ``self.orchestrator``.  The Astra
        # instance is a FullAuditOrchestrator subtype, so both surfaces share
        # exactly one workflow state while Astra-only handlers keep a narrowed
        # static type through ``self.astra_orchestrator``.
        self.orchestrator = self.astra_orchestrator

    def _collect_result_files(
        self,
        input_func: Callable[[str], str],
        output_func: Callable[[str], None],
    ) -> list[Path]:
        files: list[Path] = []
        settings = self.settings_mgr.settings
        if settings.auto_open_zip_selector:
            files = self.platform.select_multiple_zips(initial_dir=Path(settings.output_work_dir))
        if files:
            return files
        output_func("\nEnter result ZIP paths (comma-separated):")
        raw = input_func("ZIP files: ").strip()
        if not raw:
            return []
        return [Path(part.strip().strip('"').strip("'")) for part in raw.split(",") if part.strip()]

    def _render_import_summary(self, summary: Any, output_func: Callable[[str], None]) -> None:
        output_func(f"\n{summary.stage_id} RESULT INBOX")
        for slot, state in summary.lane_statuses.items():
            reason = f" ({state.rejection_reason})" if state.rejection_reason else ""
            output_func(f"{slot:<24} {state.status}{reason}")
        output_func(f"{summary.accepted_count} / {summary.total_required_lanes} required results accepted.")
        if summary.error:
            output_func(f"Stage qualification: BLOCKED ({summary.error})")
        elif summary.stage_complete:
            output_func(f"{summary.stage_id} COMPLETE")
        elif summary.missing_lanes:
            output_func(f"Waiting for: {', '.join(summary.missing_lanes)}")

    def _deliver_post_e1_batch(self, output_func: Callable[[str], None]) -> None:
        batch = self.astra_orchestrator.stage_batch
        inbox = self.astra_orchestrator.stage_inbox
        if batch is None:
            output_func("No post-E1 stage batch is loaded.")
            return
        output_func(f"\n{batch.stage_id} — EXTERNAL JOBS READY")
        for slot in batch.lane_slots:
            state = inbox.lane_statuses.get(slot) if inbox is not None else None
            if state is not None and state.status == "ACCEPTED":
                continue
            job = batch.get_job(slot)
            delivered = self.astra_orchestrator.deliver_post_e1_lane(slot)
            output_func(f"{slot}: {job.lane_title}")
            output_func(f"Package: {delivered['package_zip_name']}")
            output_func(
                f"Isolation: required={delivered['required_isolation']} actual={delivered['actual_isolation']}"
            )

    def _import_post_e1(
        self,
        input_func: Callable[[str], str],
        output_func: Callable[[str], None],
    ) -> None:
        files = self._collect_result_files(input_func, output_func)
        if not files:
            output_func("No result files provided.")
            return
        summary = self.astra_orchestrator.import_post_e1_results(files)
        self._render_import_summary(summary, output_func)
        if not summary.stage_complete:
            return
        transition = self.astra_orchestrator.advance_to_next_stage()
        output_func(f"Stage Transition: {transition['status']}")
        output_func(f"Next Action: {transition.get('next_action')}")
        if transition.get("reason"):
            output_func(f"Reason: {transition['reason']}")
        if transition.get("status") == "STAGE_READY":
            self._deliver_post_e1_batch(output_func)

    def handle_continue_audit(
        self,
        input_func: Callable[[str], str],
        output_func: Callable[[str], None],
    ) -> None:
        unfinished = self.history_service.get_latest_unfinished_campaign()
        if not unfinished:
            output_func("\nNo unfinished audits detected. Start a new audit with 'Run Full Audit'.")
            return

        self.active_store = str(unfinished.store_path)
        res = self.astra_orchestrator.resume_campaign(unfinished.store_path)
        if res.get("status") != "SUCCESS":
            output_func(f"\nResume failed: {res.get('error')} ({res.get('details', '')})")
            return

        output_func(f"\nCampaign ID: {res['campaign_id']}")
        output_func(f"Store Path:  {res['store_path']}")
        output_func(f"Current Stage: {res['current_stage']}")

        if res["current_stage"] == "E1":
            output_func(f"Accepted E1: {res['accepted_lanes_count']}/{res['total_required_lanes']}")
            if res["missing_lanes"]:
                output_func(f"Waiting for: {', '.join(res['missing_lanes'])}")
                action = input_func("[I]mport / [D]eliver / [N]back: ").strip().lower()
                if action == "d":
                    for slot in res["missing_lanes"]:
                        self.astra_orchestrator.deliver_lane_to_user(slot)
                elif action == "i":
                    self._execute_result_import(input_func, output_func)
                return
            transition = self.astra_orchestrator.advance_to_next_stage()
            output_func(f"Stage Transition: {transition['status']}")
            if transition.get("status") == "STAGE_READY":
                self._deliver_post_e1_batch(output_func)
            return

        if res["current_stage"] == "STOP":
            output_func("All baseline stages are complete. STOP evaluation is ready.")
            return

        if not res.get("post_e1_batch_loaded"):
            transition = self.astra_orchestrator.advance_to_next_stage()
            output_func(f"Stage Transition: {transition['status']}")
            output_func(f"Next Action: {transition.get('next_action')}")
            if transition.get("reason"):
                output_func(f"Reason: {transition['reason']}")
            if transition.get("status") != "STAGE_READY":
                return

        batch = self.astra_orchestrator.stage_batch
        inbox = self.astra_orchestrator.stage_inbox
        if batch is None or inbox is None:
            output_func("Post-E1 stage state could not be reconstructed.")
            return

        accepted = sum(row.status == "ACCEPTED" for row in inbox.lane_statuses.values())
        missing = [slot for slot, row in inbox.lane_statuses.items() if row.status != "ACCEPTED"]
        output_func(f"Accepted {batch.stage_id}: {accepted}/{len(batch.lane_slots)}")
        if missing:
            output_func(f"Waiting for: {', '.join(missing)}")
        action = input_func("[D]eliver / [I]mport / [N]back: ").strip().lower()
        if action == "d":
            self._deliver_post_e1_batch(output_func)
        elif action == "i":
            self._import_post_e1(input_func, output_func)

    def handle_audit_status(self, output_func: Callable[[str], None]) -> None:
        super().handle_audit_status(output_func)
        dashboard = self.astra_orchestrator.get_dashboard_summary()
        current_stage = dashboard.get("current_external_stage")
        lane_status = dashboard.get("current_stage_lanes", {})
        if current_stage and lane_status:
            output_func(f"\n{current_stage} Lane Statuses:")
            for lane, status in lane_status.items():
                output_func(f"  {lane:<20} .... {status}")


def run_ui() -> int:
    ui = AstraInteractiveAuditUI(
        api=AuditOperationApi(),
        settings_mgr=get_default_settings_manager(),
        platform_adapter=DefaultPlatformAdapter(),
    )
    return ui.run_menu_loop()


__all__ = ["AstraInteractiveAuditUI", "run_ui"]

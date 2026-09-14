"""Astra continuation terminal UI.

The qualified v2.0.3 UI remains available as the base class.  This surface
replaces only the unfinished-campaign continuation path so real post-E1 stage
packages/results are visible to the operator instead of returning
NEEDS_IMPLEMENTATION at E2.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .coordinator.operations import AuditOperationApi
from .ui import InteractiveAuditUI
from .workflow.astra_orchestrator import AstraContinuationOrchestrator
from .workflow.platform import DefaultPlatformAdapter, PlatformAdapter
from .workflow.settings import SettingsManager, get_default_settings_manager


class AstraInteractiveAuditUI(InteractiveAuditUI):
    """Interactive UI with durable Astra post-E1 continuation."""

    def __init__(
        self,
        api: AuditOperationApi | None = None,
        settings_mgr: SettingsManager | None = None,
        platform_adapter: PlatformAdapter | None = None,
    ):
        super().__init__(api=api, settings_mgr=settings_mgr, platform_adapter=platform_adapter)
        self.orchestrator = AstraContinuationOrchestrator(
            settings_mgr=self.settings_mgr,
            platform_adapter=self.platform,
            api=self.api,
        )

    def _collect_result_files(
        self,
        input_func: Callable[[str], str],
        output_func: Callable[[str], None],
    ) -> list[Path]:
        files: list[Path] = []
        settings = self.settings_mgr.settings
        if settings.auto_open_zip_selector:
            output_func("\nOpening file selector for result ZIPs...")
            files = self.platform.select_multiple_zips(initial_dir=Path(settings.output_work_dir))
        if not files:
            output_func("\nEnter result ZIP paths (comma-separated, or drag-and-drop):")
            raw_paths = input_func("ZIP files: ").strip()
            if raw_paths:
                parts = [part.strip().strip('"').strip("'") for part in raw_paths.split(",") if part.strip()]
                files = [Path(part) for part in parts]
        return files

    def _render_import_summary(self, summary: Any, output_func: Callable[[str], None]) -> None:
        output_func("\n==================================================")
        output_func(f"{summary.stage_id} RESULT INBOX")
        output_func("==================================================")
        for slot, state in summary.lane_statuses.items():
            reason = f" ({state.rejection_reason})" if state.rejection_reason else ""
            output_func(f"{slot:<24} {state.status}{reason}")
        if summary.file_results:
            output_func("\nPer-file import report:")
            for item in summary.file_results:
                name = Path(item.path).name
                digest = f" raw={item.raw_digest[:12]}..." if item.raw_digest else ""
                reason = f" | {item.reason}" if item.reason else ""
                next_action = f" | next={item.next_action}" if item.next_action else ""
                output_func(
                    f"- {name}: {item.status} [{item.code}] lane={item.lane_slot}{digest}{reason}{next_action}"
                )
        output_func(f"\n{summary.accepted_count} / {summary.total_required_lanes} required results accepted.")
        if summary.error:
            output_func(f"Stage qualification: BLOCKED ({summary.error})")
        elif summary.stage_complete:
            output_func(f"{summary.stage_id} COMPLETE")
            if summary.completion_digest:
                output_func(f"Completion Digest: {summary.completion_digest[:16]}...")
        elif summary.missing_lanes:
            output_func(f"Waiting for: {', '.join(summary.missing_lanes)}")

    def _deliver_post_e1_batch(self, output_func: Callable[[str], None]) -> None:
        batch = self.orchestrator.stage_batch
        inbox = self.orchestrator.stage_inbox
        if batch is None:
            output_func("No post-E1 stage batch is loaded.")
            return
        output_func("\n--------------------------------------------------")
        output_func(f"{batch.stage_id} — EXTERNAL JOBS READY")
        output_func("--------------------------------------------------")
        for slot in batch.lane_slots:
            if inbox is not None and inbox.lane_statuses.get(slot) and inbox.lane_statuses[slot].status == "ACCEPTED":
                continue
            job = batch.get_job(slot)
            delivered = self.orchestrator.deliver_post_e1_lane(slot)
            output_func(f"\n{batch.stage_id}-{slot}: {job.lane_title}")
            output_func(f"Package: {delivered['package_zip_name']}")
            output_func(f"Required isolation: {delivered['required_isolation']}")
            output_func(f"Actual transport isolation: {delivered['actual_isolation']}")
            output_func(f"Prompt copied: {'YES' if delivered['prompt_copied'] else 'NO'}")
            output_func(f"Explorer selected: {'YES' if delivered['explorer_selected'] else 'NO'}")
        output_func("\nRun each displayed assignment in its required independent execution context, then return here to import result ZIPs.")

    def _import_post_e1(
        self,
        input_func: Callable[[str], str],
        output_func: Callable[[str], None],
    ) -> None:
        files = self._collect_result_files(input_func, output_func)
        if not files:
            output_func("No result files provided.")
            return
        summary = self.orchestrator.import_post_e1_results(files)
        self._render_import_summary(summary, output_func)
        if not summary.stage_complete:
            return
        transition = self.orchestrator.advance_to_next_stage()
        output_func(f"\nStage Transition: {transition['status']}")
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
        res = self.orchestrator.resume_campaign(unfinished.store_path)
        if res.get("status") != "SUCCESS":
            output_func(f"\nResume failed: {res.get('error')} ({res.get('details', '')})")
            return

        output_func("\n--------------------------------------------------")
        output_func("RESUMED AUDIT CAMPAIGN")
        output_func("--------------------------------------------------")
        output_func(f"Campaign ID: {res['campaign_id']}")
        output_func(f"Store Path:  {res['store_path']}")
        output_func(f"Current Stage: {res['current_stage']}")

        if res["current_stage"] == "E1":
            output_func(f"Accepted E1: {res['accepted_lanes_count']}/{res['total_required_lanes']}")
            if res["missing_lanes"]:
                output_func(f"Waiting for: {', '.join(res['missing_lanes'])}")
                output_func("\n[I] Import E1 results")
                output_func("[D] Deliver/show missing E1 lanes")
                output_func("[N] Back")
                action = input_func("Choice [I/d/n]: ").strip().lower()
                if action == "d":
                    for slot in res["missing_lanes"]:
                        self.orchestrator.deliver_lane_to_user(slot)
                        output_func(f"Lane {slot} delivered.")
                elif action != "n":
                    self._execute_result_import(input_func, output_func)
                return

            transition = self.orchestrator.advance_to_next_stage()
            output_func(f"Stage Transition: {transition['status']}")
            if transition.get("reason"):
                output_func(f"Reason: {transition['reason']}")
            if transition.get("status") == "STAGE_READY":
                self._deliver_post_e1_batch(output_func)
            return

        if res["current_stage"] == "STOP":
            output_func("All baseline stages are complete. STOP evaluation is ready in Advanced -> STOP Gate.")
            return

        if not res.get("post_e1_batch_loaded"):
            transition = self.orchestrator.advance_to_next_stage()
            output_func(f"Stage Transition: {transition['status']}")
            output_func(f"Next Action: {transition.get('next_action')}")
            if transition.get("reason"):
                output_func(f"Reason: {transition['reason']}")
            if transition.get("status") != "STAGE_READY":
                return

        batch = self.orchestrator.stage_batch
        inbox = self.orchestrator.stage_inbox
        if batch is None or inbox is None:
            output_func("Post-E1 stage state could not be reconstructed.")
            return

        accepted = sum(1 for row in inbox.lane_statuses.values() if row.status == "ACCEPTED")
        missing = [slot for slot, row in inbox.lane_statuses.items() if row.status != "ACCEPTED"]
        output_func(f"Accepted {batch.stage_id}: {accepted}/{len(batch.lane_slots)}")
        if missing:
            output_func(f"Waiting for: {', '.join(missing)}")
        output_func("\n[D] Deliver/show pending stage packages")
        output_func("[I] Import stage result ZIPs")
        output_func("[N] Back")
        action = input_func("Choice [D/i/n]: ").strip().lower()
        if action == "d":
            self._deliver_post_e1_batch(output_func)
        elif action == "i":
            self._import_post_e1(input_func, output_func)

    def handle_audit_status(self, output_func: Callable[[str], None]) -> None:
        super().handle_audit_status(output_func)
        dashboard = self.orchestrator.get_dashboard_summary()
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

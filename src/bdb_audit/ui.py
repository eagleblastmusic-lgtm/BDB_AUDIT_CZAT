"""Interactive Terminal UI for BDB Audit v2.0.3 (R5.3 §110).

Thin projection and operation surface over FullAuditOrchestrator and AuditOperationApi.
Contains ZERO business logic, does not calculate gates or STOP decisions,
and never writes unauthoritative state.
"""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Callable, Any

from .coordinator.operations import AuditOperationApi
from .stop.operation import evaluate_stop_gate
from .workflow.settings import SettingsManager, get_default_settings_manager
from .workflow.platform import PlatformAdapter, DefaultPlatformAdapter
from .workflow.executors import EXECUTION_MODES, get_executor_profile
from .workflow.history_projection import CampaignHistoryService
from .workflow.orchestrator import FullAuditOrchestrator
from .orchestration.native_ensemble import E1_LANE_SLOTS


class InteractiveAuditUI:
    """Interactive Console UI driving BDB Audit with full semantic parity."""

    def __init__(
        self,
        api: AuditOperationApi | None = None,
        settings_mgr: SettingsManager | None = None,
        platform_adapter: PlatformAdapter | None = None,
    ):
        self.api = api or AuditOperationApi()
        self.settings_mgr = settings_mgr or get_default_settings_manager()
        self.platform = platform_adapter or DefaultPlatformAdapter()
        self.orchestrator = FullAuditOrchestrator(
            settings_mgr=self.settings_mgr,
            platform_adapter=self.platform,
            api=self.api,
        )
        self.history_service = CampaignHistoryService(self.settings_mgr, api=self.api)
        self.active_store: str | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None

    # =========================================================================
    # V2.0.3 SIMPLIFIED MAIN WORKFLOW HANDLERS
    # =========================================================================

    def handle_run_full_audit(
        self,
        input_func: Callable[[str], str],
        output_func: Callable[[str], None],
    ) -> None:
        """Run Full Audit: target confirmation, preflight, parallel E1 packaging, delivery & inbox."""
        settings = self.settings_mgr.settings
        output_func("\n--------------------------------------------------")
        output_func("RUN FULL AUDIT — TARGET CONFIRMATION")
        output_func("--------------------------------------------------")
        mode = settings.execution_mode
        if mode == "ChatGPT / GitHub":
            output_func(f"Target: {settings.github_repo_url}")
            output_func(f"Ref:    {settings.github_default_ref}")
        else:
            output_func(f"Target: {settings.local_repo_path or '<none>'}")
            output_func(f"Ref:    {settings.local_default_ref}")
        output_func(f"Mode:   {mode} ({settings.model})")
        output_func("")
        output_func("[ENTER] Start")
        output_func("[C] Change target")

        choice = input_func("Select: ").strip().lower()
        if choice == "c":
            if mode == "ChatGPT / GitHub":
                new_url = input_func(f"Enter GitHub repo URL [{settings.github_repo_url}]: ").strip()
                if new_url:
                    settings.github_repo_url = new_url
                new_ref = input_func(f"Enter branch/ref [{settings.github_default_ref}]: ").strip()
                if new_ref:
                    settings.github_default_ref = new_ref
            else:
                new_path = input_func(f"Enter local repo path [{settings.local_repo_path}]: ").strip()
                if new_path:
                    settings.local_repo_path = new_path
                new_ref = input_func(f"Enter branch/ref [{settings.local_default_ref}]: ").strip()
                if new_ref:
                    settings.local_default_ref = new_ref
            self.settings_mgr.save()
            output_func("Target updated.")

        # 1. Automatic Preflight Checks
        output_func("\nRunning Preflight Checks...")
        report = self.orchestrator.run_preflight()
        for c in report.checks:
            dots = "." * max(2, 30 - len(c.check_name))
            output_func(f"{c.check_name} {dots} {c.status} ({c.details})")

        if not report.passed:
            output_func(f"\nPREFLIGHT HALTED: status is {report.overall_status}. Please resolve prerequisites before running lanes.")
            return

        # 2. Campaign Setup
        output_func("\nInitializing Campaign Store...")
        init_res = self.orchestrator.initialize_campaign()
        self.active_store = init_res["store_path"]
        output_func(f"Campaign ID: {init_res['campaign_id']}")
        output_func(f"Store Path:  {init_res['store_path']}")

        # 3. Parallel E1 Batch Preparation (All 5 lanes frozen to same cut)
        output_func("\nPreparing E1 Parallel Audit Batch...")
        batch = self.orchestrator.prepare_e1_orchestration()
        output_func(f"Frozen E1 Input Cut: Seq {batch.frozen_history_cut.get('accepted_head_seq')} ({batch.frozen_history_cut.get('accepted_head_hash', '')[:12]}...)")
        output_func("All 5 lane packages generated against exact same cut.")

        # 4. Sequential Lane Delivery UX
        for slot in E1_LANE_SLOTS:
            job = batch.get_job(slot)
            delivery = self.orchestrator.deliver_lane_to_user(slot)

            output_func("\n--------------------------------------------------")
            output_func(f"{slot} {job.lane_title.upper()} — READY")
            output_func("--------------------------------------------------")
            output_func(f"Package generated: {delivery['package_zip_name']}")
            output_func(f"Prompt copied to clipboard: {'YES' if delivery['prompt_copied'] else 'NO'}")
            output_func(f"Package selected in Explorer: {'YES' if delivery['explorer_selected'] else 'NO'}")
            output_func("")
            output_func("Teraz:")
            output_func(f"1. Otwórz NOWY czat {settings.execution_mode}.")
            output_func("2. Dodaj wskazany ZIP.")
            output_func("3. Ctrl+V.")
            output_func("4. Uruchom audyt.")
            output_func("")
            output_func("[ENTER] Prepare/show next lane")
            output_func("[S] Save and exit")

            step_choice = input_func("Choice: ").strip().lower()
            if step_choice == "s":
                output_func("Work saved. You can resume at any time via 'Continue Audit'.")
                return

        # 5. After all lanes prepared: prompt for import
        output_func("\n--------------------------------------------------")
        output_func("E1 — ALL JOBS PREPARED")
        output_func("--------------------------------------------------")
        output_func(f"{len(E1_LANE_SLOTS)} audit jobs prepared.")
        output_func("You can run them in parallel in separate chats.")
        output_func("")
        output_func("Are all results ready?")
        output_func("[Y] Import results")
        output_func("[N] Save and exit")
        output_func("[S] Show status")

        ready_choice = input_func("Choice [Y/n/s]: ").strip().lower()
        if ready_choice == "s":
            self.handle_audit_status(output_func)
            return
        if ready_choice == "n":
            output_func("Exiting. You can import results anytime via 'Continue Audit'.")
            return

        # 6. Import Multi-ZIP Results
        self._execute_result_import(input_func, output_func)

    def _execute_result_import(
        self,
        input_func: Callable[[str], str],
        output_func: Callable[[str], None],
    ) -> None:
        """Collect ZIP files and process via E1ResultInbox."""
        settings = self.settings_mgr.settings
        files: list[Path] = []

        if settings.auto_open_zip_selector:
            output_func("\nOpening file selector for result ZIPs...")
            initial_dir = Path(settings.output_work_dir)
            files = self.platform.select_multiple_zips(initial_dir=initial_dir)

        if not files:
            output_func("\nEnter paths to result ZIP files (comma-separated, or drag-and-drop):")
            raw_paths = input_func("ZIP files: ").strip()
            if raw_paths:
                parts = [p.strip().strip('"').strip("'") for p in raw_paths.split(",") if p.strip()]
                files = [Path(p) for p in parts]

        if not files:
            output_func("No result files provided.")
            return

        output_func(f"\nProcessing {len(files)} result file(s)...")
        summary = self.orchestrator.import_results(files)

        output_func("\n==================================================")
        output_func("E1 RESULT INBOX")
        output_func("==================================================")
        for slot in E1_LANE_SLOTS:
            st = summary.lane_statuses.get(slot)
            status_text = st.status if st else "MISSING"
            dots = "." * max(2, 30 - len(slot))
            reason = f" ({st.rejection_reason})" if st and st.rejection_reason else ""
            output_func(f"{slot} {dots} {status_text}{reason}")

        output_func(f"\n{summary.accepted_count} / {summary.total_required_lanes} required results accepted.")
        if summary.missing_lanes:
            output_func(f"Waiting for: {', '.join(summary.missing_lanes)}")
        else:
            output_func("\nE1 COMPLETE")
            output_func(f"Required lanes ........ {summary.total_required_lanes}/{summary.total_required_lanes}")
            output_func(f"Accepted results ....... {summary.accepted_count}/{summary.total_required_lanes}")
            output_func("Blocked lanes .......... 0")
            output_func(f"Completion Digest ...... {summary.completion_digest[:16]}..." if summary.completion_digest else "")
            output_func("\nNext: E2")
            output_func("[ENTER] Continue")
            output_func("[S] Save and exit")
            c = input_func("Choice: ").strip().lower()
            if c != "s":
                adv = self.orchestrator.advance_to_next_stage()
                output_func(f"\nStage Transition: {adv['status']}")
                output_func(f"Next Action: {adv['next_action']} ({adv.get('reason', '')})")

    def handle_continue_audit(
        self,
        input_func: Callable[[str], str],
        output_func: Callable[[str], None],
    ) -> None:
        """Continue Audit: detects unfinished audits from known locators and resumes."""
        unfinished = self.history_service.get_latest_unfinished_campaign()
        if not unfinished:
            output_func("\nNo unfinished audits detected. Start a new audit with 'Run Full Audit'.")
            return

        output_func("\n--------------------------------------------------")
        output_func("UNFINISHED AUDIT DETECTED")
        output_func("--------------------------------------------------")
        output_func(f"Target:   {unfinished.target_display}")
        output_func(f"Campaign: {unfinished.campaign_id}")
        output_func(f"Store:    {unfinished.store_path}")
        output_func(f"Stage:    {unfinished.current_stage}")
        output_func(f"Prepared Stages: {unfinished.stages_prepared}")
        output_func(f"Prepared Lanes:  {unfinished.lanes_prepared}")
        output_func("")
        output_func("[R] Resume")
        output_func("[I] Import results now")
        output_func("[N] Back to menu")

        choice = input_func("Choice [R/i/n]: ").strip().lower()
        if choice in ("r", "i"):
            self.active_store = str(unfinished.store_path)
            res_info = self.orchestrator.resume_campaign(unfinished.store_path)
            output_func("\n--------------------------------------------------")
            output_func("RESUMED AUDIT CAMPAIGN")
            output_func("--------------------------------------------------")
            output_func(f"Campaign ID: {res_info['campaign_id']}")
            output_func(f"Store Path:  {res_info['store_path']}")
            output_func(f"Accepted:    {res_info['accepted_lanes_count']}/{res_info['total_required_lanes']} lanes accepted")
            if res_info["missing_lanes"]:
                output_func(f"Waiting for: {', '.join(res_info['missing_lanes'])}")
            else:
                output_func("All E1 lanes completed.")

            if res_info["stage_complete"]:
                output_func("\nE1 stage is already completed.")
                return

            output_func("\n[I] Import results now")
            output_func("[D] Deliver/show missing lane")
            output_func("[N] Back to menu")
            action = input_func("Choice [I/d/n]: ").strip().lower()
            if action == "d":
                for slot in res_info["missing_lanes"]:
                    self.orchestrator.deliver_lane_to_user(slot)
                    output_func(f"Lane {slot} prompt delivered.")
            elif action != "n":
                self._execute_result_import(input_func, output_func)

    def handle_audit_status(self, output_func: Callable[[str], None]) -> None:
        """Render clear, non-technical text dashboard of audit status and progress."""
        dashboard = self.orchestrator.get_dashboard_summary()
        output_func("\n==================================================")
        output_func("AUDIT STATUS & RESULTS")
        output_func("==================================================")
        output_func(f"Project:            {dashboard['project']}")
        output_func(f"Source:             {dashboard['source_type']}")
        output_func(f"Pinned revision:    {dashboard['pinned_revision']}")
        output_func(f"Execution profile:  {dashboard['execution_profile']}")
        output_func("")
        output_func(f"Campaign ID:        {dashboard['campaign_id']}")
        output_func(f"Store:              {dashboard['campaign_store']}")
        output_func("")
        output_func("Stage progress:")
        for stg, stat in dashboard["stages"].items():
            output_func(f"  {stg:<6} .... {stat}")

        if dashboard["e1_lanes"]:
            output_func("\nE1 Lane Statuses:")
            for lane, lst in dashboard["e1_lanes"].items():
                output_func(f"  {lane:<6} .... {lst}")

    def handle_settings_menu(
        self,
        input_func: Callable[[str], str],
        output_func: Callable[[str], None],
    ) -> None:
        """Manage persistent user settings."""
        settings = self.settings_mgr.settings
        while True:
            output_func("\n==================================================")
            output_func("SETTINGS — PERSISTENT CONFIGURATION")
            output_func("==================================================")
            output_func(f"Config path: {self.settings_mgr.path}")
            output_func("")
            output_func(f"1. Execution Mode:        {settings.execution_mode}")
            output_func(f"2. Model:                 {settings.model}")
            output_func(f"3. GitHub Target:         {settings.github_repo_url} (ref: {settings.github_default_ref})")
            output_func(f"4. Local Target:          {settings.local_repo_path or '<none>'} (ref: {settings.local_default_ref})")
            output_func(f"5. Work Directory:        {settings.output_work_dir}")
            output_func(f"6. Auto Copy Clipboard:   {settings.auto_copy_clipboard}")
            output_func(f"7. Auto Open Explorer:    {settings.auto_open_explorer}")
            output_func(f"8. Auto Open ZIP Dialog:  {settings.auto_open_zip_selector}")
            output_func("9. Back to Main Menu")

            choice = input_func("Select setting to change [1-9]: ").strip()
            if choice == "1":
                output_func("\nAvailable Execution Modes:")
                modes = list(EXECUTION_MODES.keys())
                for i, m in enumerate(modes, 1):
                    output_func(f"{i}. {m}")
                m_choice = input_func(f"Select mode [1-{len(modes)}]: ").strip()
                try:
                    idx = int(m_choice) - 1
                    if 0 <= idx < len(modes):
                        settings.execution_mode = modes[idx]
                        profile = get_executor_profile(settings.execution_mode)
                        settings.model = profile.default_model
                        self.settings_mgr.save()
                        output_func(f"Mode set to: {settings.execution_mode}")
                except ValueError:
                    pass

            elif choice == "2":
                profile = get_executor_profile(settings.execution_mode)
                output_func(f"\nAvailable Models for {settings.execution_mode}:")
                for i, m in enumerate(profile.available_models, 1):
                    output_func(f"{i}. {m}")
                m_choice = input_func(f"Select model [1-{len(profile.available_models)}]: ").strip()
                try:
                    idx = int(m_choice) - 1
                    if 0 <= idx < len(profile.available_models):
                        settings.model = profile.available_models[idx]
                        self.settings_mgr.save()
                        output_func(f"Model set to: {settings.model}")
                except ValueError:
                    pass

            elif choice == "3":
                url = input_func(f"Enter GitHub repo URL [{settings.github_repo_url}]: ").strip()
                if url:
                    settings.github_repo_url = url
                ref = input_func(f"Enter default branch/ref [{settings.github_default_ref}]: ").strip()
                if ref:
                    settings.github_default_ref = ref
                self.settings_mgr.save()
                output_func("GitHub target updated.")

            elif choice == "4":
                p = input_func(f"Enter local repo path [{settings.local_repo_path}]: ").strip()
                if p:
                    settings.local_repo_path = p
                ref = input_func(f"Enter default branch/ref [{settings.local_default_ref}]: ").strip()
                if ref:
                    settings.local_default_ref = ref
                self.settings_mgr.save()
                output_func("Local target updated.")

            elif choice == "5":
                w = input_func(f"Enter output work directory [{settings.output_work_dir}]: ").strip()
                if w:
                    settings.output_work_dir = w
                    self.settings_mgr.save()
                    output_func("Work directory updated.")

            elif choice == "6":
                settings.auto_copy_clipboard = not settings.auto_copy_clipboard
                self.settings_mgr.save()
                output_func(f"Auto copy clipboard: {settings.auto_copy_clipboard}")

            elif choice == "7":
                settings.auto_open_explorer = not settings.auto_open_explorer
                self.settings_mgr.save()
                output_func(f"Auto open Explorer: {settings.auto_open_explorer}")

            elif choice == "8":
                settings.auto_open_zip_selector = not settings.auto_open_zip_selector
                self.settings_mgr.save()
                output_func(f"Auto open ZIP selector: {settings.auto_open_zip_selector}")

            elif choice in ("9", "q", "exit", "back"):
                return

    def handle_audit_history(
        self,
        input_func: Callable[[str], str],
        output_func: Callable[[str], None],
    ) -> None:
        """Display known campaigns from persistent history index."""
        campaigns = self.history_service.get_known_campaigns()
        output_func("\n==================================================")
        output_func("AUDIT HISTORY")
        output_func("==================================================")
        if not campaigns:
            output_func("No prior campaigns recorded.")
            return

        for i, c in enumerate(campaigns, 1):
            sha_part = f" @ {c.accepted_head_hash[:10]}" if c.accepted_head_hash else ""
            output_func(f"{i}. {c.target_display}")
            output_func(f"   Store:  {c.store_path}")
            output_func(f"   Stage:  {c.current_stage} | Status: {c.status_label}{sha_part}")
            if c.error:
                output_func(f"   Note:   {c.error}")
            output_func("")

        c_choice = input_func("Select campaign to inspect [number, or ENTER to return]: ").strip()
        try:
            idx = int(c_choice) - 1
            if 0 <= idx < len(campaigns):
                selected = campaigns[idx]
                output_func(f"\nSelected Campaign: {selected.campaign_id}")
                output_func(f"Store Path:        {selected.store_path}")
                output_func(f"Current Stage:     {selected.current_stage}")
                output_func(f"Stages Prepared:   {selected.stages_prepared}")
                output_func(f"Lanes Prepared:    {selected.lanes_prepared}")
                output_func(f"Completions Count: {selected.stage_completions_count}")
                output_func(f"Status:            {selected.status_label}")
        except ValueError:
            pass

    # =========================================================================
    # ADVANCED TECHNICAL CONTROL SURFACE (V2.0.2 PARITY)
    # =========================================================================

    def run_advanced_menu_loop(
        self,
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print,
    ) -> int:
        """Interactive loop for Advanced mode (preserving exact v2.0.2 technical commands)."""
        output_func("==================================================")
        output_func("   BDB Audit v2.0.3 — Advanced Control Surface")
        output_func("==================================================")

        while True:
            output_func("")
            output_func(f"Active Store: {self.active_store or '<none>'}")
            output_func("1. Create Campaign")
            output_func("2. Campaign Status")
            output_func("3. Prepare Stage")
            output_func("4. Prepare Lane")
            output_func("5. Validate Artifact")
            output_func("6. Continue Campaign / Check STOP State")
            output_func("7. Run Self-Test")
            output_func("8. Build Standalone Assistant")
            output_func("9. Back to Main Menu")
            output_func("10. Evaluate STOP Gate")

            try:
                choice = input_func("Select action [1-10]: ").strip()
            except (EOFError, KeyboardInterrupt):
                output_func("\nReturning to main menu.")
                return 0

            if choice == "1":
                store = input_func("Enter store path: ").strip()
                seed = input_func("Enter seed (default: interactive): ").strip() or "interactive"
                try:
                    res = self.handle_create_campaign(store, seed=seed)
                    output_func(f"SUCCESS: Campaign created ID={res['campaign_id']}, seq={res['commit_seq']}")
                except Exception as exc:
                    output_func(f"ERROR: {exc}")

            elif choice == "2":
                store = input_func(f"Enter store path [{self.active_store or ''}]: ").strip() or self.active_store  # type: ignore[assignment]
                if not store:
                    output_func("ERROR: Store path required")
                    continue
                try:
                    res = self.handle_campaign_status(store)
                    output_func(f"STATUS: Stage={res['current_stage']}, Head Seq={res['accepted_head_seq']}")
                    output_func(f"Prepared Stages: {res['stages_prepared']}")
                    output_func(f"Prepared Lanes: {res['lanes_prepared']}")
                except Exception as exc:
                    output_func(f"ERROR: {exc}")

            elif choice == "3":
                stage = input_func("Enter Stage ID (e.g. E1, E2, E3, E4, E5): ").strip()
                try:
                    res = self.handle_prepare_stage(stage)
                    output_func(f"SUCCESS: Stage {stage} prepared at seq {res['commit_seq']}")
                except Exception as exc:
                    output_func(f"ERROR: {exc}")

            elif choice == "4":
                stage = input_func("Enter Stage ID (e.g. E1, E3): ").strip()
                slot = input_func("Enter Lane slot (e.g. L1, L2): ").strip()
                try:
                    res = self.handle_prepare_lane(stage, slot)
                    output_func(f"SUCCESS: Lane {slot} prepared (Isolation: {res['isolation_status']}) at seq {res['commit_seq']}")
                except Exception as exc:
                    output_func(f"ERROR: {exc}")

            elif choice == "5":
                art = input_func("Enter artifact path: ").strip()
                try:
                    res = self.handle_validate(art)
                    output_func(f"VALID: Kind={res['kind']}, Digest={res['digest'][:16]}...")
                except Exception as exc:
                    output_func(f"INVALID: {exc}")

            elif choice == "6":
                try:
                    res = self.handle_continue()
                    output_func(f"CONTINUATION: State={res['continuation_state']}, Next Action={res['next_action']}")
                    if res.get("next_action") == "EVALUATE_STOP_GATE":
                        output_func("STOP Gate is available as action 10.")
                except Exception as exc:
                    output_func(f"ERROR: {exc}")

            elif choice == "7":
                deep_choice = input_func("Include deep checks? (y/N): ").strip().lower()
                try:
                    res = self.handle_self_test(deep=(deep_choice == "y"))
                    output_func(f"SELF-TEST: {res['status']} in {res['duration_ms']}ms ({len(res['checks'])} checks passed)")
                except Exception as exc:
                    output_func(f"SELF-TEST FAILED: {exc}")

            elif choice == "8":
                out_p = input_func("Enter custom output path (optional): ").strip() or None
                try:
                    res = self.handle_build(output_path=out_p)
                    output_func(f"BUILD SUCCESS: {res['output_path']} ({res['size']} bytes, SHA256: {res['sha256'][:16]}...)")
                except Exception as exc:
                    output_func(f"BUILD FAILED: {exc}")

            elif choice == "9" or choice.lower() in ("q", "quit", "exit", "back"):
                output_func("Returning to main menu.")
                return 0

            elif choice == "10":
                stop_input = input_func(
                    "Enter STOP input artifact path (blank = latest accepted STOP input): "
                ).strip() or None
                e6_choice = input_func("Approved E6 plan? (y/N): ").strip().lower()
                try:
                    res = self.handle_evaluate_stop(
                        stop_input_path=stop_input,
                        e6_plan_approved=(e6_choice == "y"),
                    )
                    output_func(
                        "STOP: "
                        f"Decision={res['continuation_decision']}, "
                        f"Assurance={res['assurance_level']}, "
                        f"Readiness={res['release_readiness']}"
                    )
                    output_func(f"Evaluated: {res['evaluated']}, Authoritative: {res['authoritative']}")
                    output_func(f"Reason Codes: {res['reason_codes']}")
                    output_func(f"Next Action: {res['next_action']}")
                except Exception as exc:
                    output_func(f"STOP EVALUATION FAILED: {exc}")

            else:
                output_func(f"Invalid option '{choice}'. Please select 1-10.")

    # =========================================================================
    # V2.0.3 SIMPLIFIED MAIN MENU LOOP
    # =========================================================================

    def run_menu_loop(
        self,
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print,
    ) -> int:
        """Run simplified interactive text UI loop for BDB Audit v2.0.3."""
        output_func("==================================================")
        output_func("              BDB AUDIT v2.0.3")
        output_func("==================================================")

        while True:
            output_func("")
            output_func("1. Run Full Audit")
            output_func("2. Continue Audit")
            output_func("3. Audit Status & Results")
            output_func("4. Settings")
            output_func("5. Audit History")
            output_func("6. Advanced")
            output_func("7. Exit")

            try:
                choice = input_func("Select action [1-7]: ").strip()
            except (EOFError, KeyboardInterrupt):
                output_func("\nExiting UI.")
                return 0

            if choice == "1":
                try:
                    self.handle_run_full_audit(input_func, output_func)
                except Exception as exc:
                    output_func(f"ERROR: {exc}")

            elif choice == "2":
                try:
                    self.handle_continue_audit(input_func, output_func)
                except Exception as exc:
                    output_func(f"ERROR: {exc}")

            elif choice == "3":
                try:
                    self.handle_audit_status(output_func)
                except Exception as exc:
                    output_func(f"ERROR: {exc}")

            elif choice == "4":
                try:
                    self.handle_settings_menu(input_func, output_func)
                except Exception as exc:
                    output_func(f"ERROR: {exc}")

            elif choice == "5":
                try:
                    self.handle_audit_history(input_func, output_func)
                except Exception as exc:
                    output_func(f"ERROR: {exc}")

            elif choice == "6":
                self.run_advanced_menu_loop(input_func, output_func)

            elif choice == "7" or choice.lower() in ("q", "quit", "exit"):
                output_func("Exiting UI.")
                return 0

            else:
                output_func(f"Invalid option '{choice}'. Please select 1-7.")

    # =========================================================================
    # CORE DOMAIN HANDLERS (EXACT V2.0.2 INTERFACE PRESERVED)
    # =========================================================================

    def handle_create_campaign(self, store_path: str, seed: str = "interactive_seed", campaign_id: str | None = None) -> dict[str, Any]:
        try:
            res = self.api.create_campaign(store_path, seed=seed, campaign_id=campaign_id)
            self.active_store = str(Path(store_path).resolve())
            self.last_result = res
            self.last_error = None
            self.settings_mgr.record_campaign(self.active_store, res["campaign_id"], self.settings_mgr.settings.github_repo_url)
            return res
        except Exception as exc:
            self.last_error = str(exc)
            self.last_result = {"status": "FAIL", "error": str(exc)}
            raise

    def handle_campaign_status(self, store_path: str | None = None) -> dict[str, Any]:
        target = store_path or self.active_store
        if not target:
            raise ValueError("No store selected or specified")
        try:
            res = self.api.get_campaign_status(target)
            self.active_store = str(Path(target).resolve())
            self.last_result = res
            self.last_error = None
            return res
        except Exception as exc:
            self.last_error = str(exc)
            self.last_result = {"status": "FAIL", "error": str(exc)}
            raise

    def handle_prepare_stage(self, stage_id: str, store_path: str | None = None, stage_spec_revision: str = "1") -> dict[str, Any]:
        target = store_path or self.active_store
        if not target:
            raise ValueError("No store selected or specified")
        try:
            res = self.api.prepare_stage(target, stage_id=stage_id, stage_spec_revision=stage_spec_revision)
            self.last_result = res
            self.last_error = None
            return res
        except Exception as exc:
            self.last_error = str(exc)
            self.last_result = {"status": "FAIL", "error": str(exc)}
            raise

    def handle_prepare_lane(self, stage_id: str, slot: str, store_path: str | None = None, lane_spec_revision: str = "1") -> dict[str, Any]:
        target = store_path or self.active_store
        if not target:
            raise ValueError("No store selected or specified")
        try:
            res = self.api.prepare_lane(target, stage_id=stage_id, slot=slot, lane_spec_revision=lane_spec_revision)
            self.last_result = res
            self.last_error = None
            return res
        except Exception as exc:
            self.last_error = str(exc)
            self.last_result = {"status": "FAIL", "error": str(exc)}
            raise

    def handle_validate(self, artifact_path: str, expected_kind: str | None = None) -> dict[str, Any]:
        try:
            res = self.api.validate_artifact(artifact_path, expected_kind=expected_kind)
            self.last_result = res
            self.last_error = None
            return res
        except Exception as exc:
            self.last_error = str(exc)
            self.last_result = {"status": "FAIL", "error": str(exc)}
            raise

    def handle_continue(self, store_path: str | None = None) -> dict[str, Any]:
        target = store_path or self.active_store
        if not target:
            raise ValueError("No store selected or specified")
        try:
            res = self.api.continue_campaign(target)
            self.last_result = res
            self.last_error = None
            return res
        except Exception as exc:
            self.last_error = str(exc)
            self.last_result = {"status": "FAIL", "error": str(exc)}
            raise

    def handle_evaluate_stop(
        self,
        store_path: str | None = None,
        stop_input_path: str | None = None,
        e6_plan_approved: bool = False,
    ) -> dict[str, Any]:
        target = store_path or self.active_store
        if not target:
            raise ValueError("No store selected or specified")
        try:
            res = evaluate_stop_gate(
                target,
                stop_input_path=stop_input_path,
                e6_plan_approved=e6_plan_approved,
            )
            self.last_result = res
            self.last_error = None
            return res
        except Exception as exc:
            self.last_error = str(exc)
            self.last_result = {"status": "FAIL", "error": str(exc)}
            raise

    def handle_self_test(self, deep: bool = False) -> dict[str, Any]:
        try:
            res = self.api.run_self_test(deep=deep)
            self.last_result = res
            self.last_error = None
            return res
        except Exception as exc:
            self.last_error = str(exc)
            self.last_result = {"status": "FAIL", "error": str(exc)}
            raise

    def handle_build(self, output_path: str | None = None) -> dict[str, Any]:
        try:
            res = self.api.run_build(output_path=output_path)
            self.last_result = res
            self.last_error = None
            return res
        except Exception as exc:
            self.last_error = str(exc)
            self.last_result = {"status": "FAIL", "error": str(exc)}
            raise


def run_ui() -> int:
    ui = InteractiveAuditUI()
    return ui.run_menu_loop()


__all__ = ["InteractiveAuditUI", "run_ui"]

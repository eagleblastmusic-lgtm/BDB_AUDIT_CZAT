"""Interactive Terminal UI for BDB Audit v2 (R5.3 §110).

Thin projection and operation surface over AuditOperationApi.
Contains ZERO business logic, does not calculate gates or STOP decisions,
and never writes unauthoritative state.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Any

from .coordinator.operations import AuditOperationApi


class InteractiveAuditUI:
    """Interactive Console UI driving AuditOperationApi with full semantic parity."""

    def __init__(self, api: AuditOperationApi | None = None):
        self.api = api or AuditOperationApi()
        self.active_store: str | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None

    def handle_create_campaign(self, store_path: str, seed: str = "interactive_seed", campaign_id: str | None = None) -> dict[str, Any]:
        try:
            res = self.api.create_campaign(store_path, seed=seed, campaign_id=campaign_id)
            self.active_store = str(Path(store_path).resolve())
            self.last_result = res
            self.last_error = None
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

    def run_menu_loop(
        self,
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print,
    ) -> int:
        """Run interactive text UI loop."""
        output_func("==================================================")
        output_func("   BDB Audit v2.0.0 — Interactive Control Surface")
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
            output_func("9. Exit")

            try:
                choice = input_func("Select action [1-9]: ").strip()
            except (EOFError, KeyboardInterrupt):
                output_func("\nExiting UI.")
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

            elif choice == "9" or choice.lower() in ("q", "quit", "exit"):
                output_func("Exiting UI.")
                return 0

            else:
                output_func(f"Invalid option '{choice}'. Please select 1-9.")


def run_ui() -> int:
    ui = InteractiveAuditUI()
    return ui.run_menu_loop()


__all__ = ["InteractiveAuditUI", "run_ui"]

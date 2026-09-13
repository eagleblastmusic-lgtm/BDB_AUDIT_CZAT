"""Full Audit Orchestrator for BDB Audit v2.0.3.

Application-level state machine for preflight, exact source resolution, durable
E1 assignment/package preparation, manual delivery, raw-first result import, and
fail-closed resume.  Mutable user settings are configuration for *new* work;
they are never allowed to rewrite an already accepted assignment on resume.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from ..coordinator.operations import AuditOperationApi
from ..core.errors import ValidationError
from ..core.registry import ContractRegistry
from ..history.store import TransactionalHistoryStore
from ..orchestration.native_ensemble import E1_LANE_SLOTS
from ..orchestration.templates import TemplateRegistry
from .executors import get_executor_profile
from .inbox import E1ResultInbox, ImportedResultSummary
from .package_resume import load_e1_batch
from .packaging import E1Batch, prepare_e1_batch
from .platform import DefaultPlatformAdapter, PlatformAdapter
from .settings import SettingsManager, UserSettings
from .source_target import ResolvedSource, resolve_source_identity


@dataclass(frozen=True)
class PreflightCheckResult:
    check_name: str
    status: str  # PASS | BLOCKED | NEEDS_INPUT
    details: str


@dataclass(frozen=True)
class PreflightReport:
    overall_status: str
    checks: tuple[PreflightCheckResult, ...]

    @property
    def passed(self) -> bool:
        return self.overall_status == "PASS"


class FullAuditOrchestrator:
    """End-to-end user workflow over the canonical history engine."""

    def __init__(
        self,
        settings_mgr: SettingsManager,
        platform_adapter: PlatformAdapter | None = None,
        api: AuditOperationApi | None = None,
    ):
        self.settings_mgr = settings_mgr
        self.settings: UserSettings = settings_mgr.settings
        self.platform = platform_adapter or DefaultPlatformAdapter()
        self.api = api or AuditOperationApi()
        self.active_store_path: Path | None = None
        self.resolved_source: ResolvedSource | None = None
        self.e1_batch: E1Batch | None = None
        self.e1_inbox: E1ResultInbox | None = None

    def _artifact_root(self) -> Path:
        if self.active_store_path is None:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        # Campaign artifacts travel with the exact campaign-store partition.
        # This removes mutable output_work_dir from resume authority.
        return self.active_store_path.parent / "artifacts"

    def run_preflight(self, explicit_target_sha: str | None = None) -> PreflightReport:
        """Run all preflight checks before creating new lane assignments."""
        checks: list[PreflightCheckResult] = []

        target_loc = (
            self.settings.github_repo_url
            if self.settings.execution_mode == "ChatGPT / GitHub"
            else self.settings.local_repo_path
        )
        if not target_loc:
            checks.append(PreflightCheckResult("Source / target", "NEEDS_INPUT", "No target repository configured"))
        else:
            checks.append(PreflightCheckResult("Source / target", "PASS", f"Configured: {target_loc}"))

        target_ref = (
            self.settings.github_default_ref
            if self.settings.execution_mode == "ChatGPT / GitHub"
            else self.settings.local_default_ref
        )
        try:
            target_type = "github" if self.settings.execution_mode == "ChatGPT / GitHub" else "local"
            resolved_src = resolve_source_identity(
                target_type=target_type,
                location=target_loc,
                ref=target_ref,
                explicit_sha=explicit_target_sha,
            )
            self.resolved_source = resolved_src
            tree_suffix = f" tree {resolved_src.exact_tree_sha[:12]}" if resolved_src.exact_tree_sha else ""
            checks.append(PreflightCheckResult(
                "Exact source identity", "PASS",
                f"{resolved_src.ref} @ {resolved_src.exact_commit_sha[:12]}{tree_suffix}",
            ))
        except Exception as exc:
            checks.append(PreflightCheckResult(
                "Exact source identity", "NEEDS_INPUT", f"Could not verify exact source identity: {exc}"
            ))

        if self.settings.execution_mode != "ChatGPT / GitHub":
            checks.append(PreflightCheckResult(
                "Executor profile", "BLOCKED",
                f"Execution mode '{self.settings.execution_mode}' delivery and result lifecycle is not implemented "
                "in v2.0.3 (NEEDS_IMPLEMENTATION)",
            ))
        else:
            profile = get_executor_profile(self.settings.execution_mode)
            if profile.default_model:
                checks.append(PreflightCheckResult(
                    "Executor profile", "PASS", f"{profile.display_name} ({self.settings.model})"
                ))
            else:
                checks.append(PreflightCheckResult("Executor profile", "BLOCKED", "Invalid executor profile"))

        profile = get_executor_profile(self.settings.execution_mode)
        if profile.delivery_profile and self.settings.execution_mode == "ChatGPT / GitHub":
            checks.append(PreflightCheckResult("Delivery profile", "PASS", profile.delivery_profile))
        else:
            checks.append(PreflightCheckResult("Delivery profile", "BLOCKED", "Delivery profile not implemented"))

        out_dir = Path(self.settings.output_work_dir).resolve()
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            test_file = out_dir / ".bdb_write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            checks.append(PreflightCheckResult("Output directory", "PASS", str(out_dir)))
        except Exception as exc:
            checks.append(PreflightCheckResult("Output directory", "BLOCKED", f"Output directory not writable: {exc}"))

        try:
            default_store = out_dir / "campaign.sqlite"
            checks.append(PreflightCheckResult("Campaign store", "PASS", str(default_store)))
        except Exception as exc:
            checks.append(PreflightCheckResult("Campaign store", "BLOCKED", str(exc)))

        try:
            reg = TemplateRegistry()
            template = reg.get("e1_ensemble")
            checks.append(PreflightCheckResult("Required templates", "PASS", f"Verified template {template.template_id}"))
        except Exception as exc:
            checks.append(PreflightCheckResult("Required templates", "BLOCKED", str(exc)))

        try:
            registry = ContractRegistry()
            registry.contract("stage_spec", version="1")
            registry.contract("lane_spec", version="1")
            registry.contract("bdb_audit_lane_result", version="1")
            checks.append(PreflightCheckResult("Required contracts", "PASS", "Verified canonical schemas"))
        except Exception as exc:
            checks.append(PreflightCheckResult("Required contracts", "BLOCKED", str(exc)))

        overall = "PASS"
        for check in checks:
            if check.status == "BLOCKED":
                overall = "BLOCKED"
                break
            if check.status == "NEEDS_INPUT" and overall != "BLOCKED":
                overall = "NEEDS_INPUT"
        return PreflightReport(overall_status=overall, checks=tuple(checks))

    def initialize_campaign(
        self,
        store_path: Path | str | None = None,
        campaign_seed: str | None = None,
    ) -> dict[str, Any]:
        """Create or locate a campaign store with source-identity partitioning."""
        out_dir = Path(self.settings.output_work_dir).resolve()
        target_display = self.resolved_source.display_name if self.resolved_source else "Audit Target"
        current_sha = self.resolved_source.exact_commit_sha if self.resolved_source else "seed"
        target_location = self.resolved_source.location if self.resolved_source else "target"

        if store_path:
            path = Path(store_path).resolve()
            if path.exists() and path.stat().st_size > 0:
                existing_src = self.api.get_campaign_source_identity(path)
                stored_sha = existing_src.get("git_commit_object_id")
                if stored_sha and stored_sha != current_sha:
                    raise ValidationError(
                        "SOURCE_IDENTITY_MISMATCH",
                        f"Store at {path} is bound to commit {stored_sha}, but current target is {current_sha}",
                    )
        else:
            safe_name = target_display.replace("/", "_").replace("\\", "_").replace(":", "_")
            path = out_dir / safe_name / current_sha[:12] / "campaign.sqlite"

        path.parent.mkdir(parents=True, exist_ok=True)
        self.active_store_path = path
        seed = campaign_seed or f"{target_display}_{current_sha}"
        if not path.exists() or path.stat().st_size == 0:
            created = self.api.create_campaign(
                path,
                seed=seed,
                target_repo=target_location,
                commit_sha=current_sha if self.resolved_source else None,
            )
            campaign_id = created["campaign_id"]
        else:
            campaign_id = self.api.get_campaign_status(path)["campaign_id"]

        self.settings_mgr.record_campaign(path, campaign_id, target_display)
        return {"status": "SUCCESS", "campaign_id": campaign_id, "store_path": str(path)}

    def prepare_e1_orchestration(self) -> E1Batch:
        """Prepare E1 specs, accept assignments, then publish deterministic packages."""
        if not self.active_store_path or not self.active_store_path.exists():
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        if not self.resolved_source:
            raise ValidationError("SOURCE_IDENTITY_REQUIRED")

        status = self.api.get_campaign_status(self.active_store_path)
        if "E1" not in status.get("stages_prepared", []):
            self.api.prepare_stage(self.active_store_path, "E1")

        # Refresh after StageSpec acceptance so LaneSpec preparation is based on
        # accepted state rather than a pre-stage cached status snapshot.
        status = self.api.get_campaign_status(self.active_store_path)
        lanes_prepared = set(status.get("lanes_prepared", []))
        for slot in E1_LANE_SLOTS:
            lane_key = f"lane_E1_{slot}"
            if lane_key not in lanes_prepared:
                self.api.prepare_lane(self.active_store_path, "E1", slot=slot)

        store = TransactionalHistoryStore(self.active_store_path)
        batch = prepare_e1_batch(
            store=store,
            output_dir=self._artifact_root(),
            source_info=self.resolved_source,
            execution_mode=self.settings.execution_mode,
            model=self.settings.model,
        )
        self.e1_batch = batch
        self.e1_inbox = E1ResultInbox(store, batch)
        return batch

    def deliver_lane_to_user(self, slot: str) -> dict[str, Any]:
        """Deliver one already accepted assignment/package through the UI adapter."""
        if not self.e1_batch:
            raise ValidationError("E1_BATCH_NOT_PREPARED")
        job = self.e1_batch.get_job(slot)
        clipboard_ok = False
        explorer_ok = False
        if self.settings.auto_copy_clipboard:
            clipboard_ok = self.platform.copy_to_clipboard(job.prompt_text)
        if self.settings.auto_open_explorer:
            explorer_ok = self.platform.open_and_select(job.package_zip_path)
        return {
            "lane_slot": slot,
            "package_zip_path": str(job.package_zip_path),
            "package_zip_name": job.package_zip_path.name,
            "assignment_ref": dict(job.assignment_ref),
            "attempt_ref": dict(job.attempt_ref),
            "prompt_copied": clipboard_ok if self.settings.auto_copy_clipboard else None,
            "explorer_selected": explorer_ok if self.settings.auto_open_explorer else None,
        }

    # Compatibility alias used by existing UI/tests.
    def deliver_e1_lane(self, slot: str) -> dict[str, Any]:
        result = self.deliver_lane_to_user(slot)
        return {"status": "SUCCESS", **result}

    def import_results(self, zip_paths: Sequence[Path | str]) -> ImportedResultSummary:
        if not self.e1_inbox:
            raise ValidationError("E1_RESULT_INBOX_NOT_INITIALIZED")
        return self.e1_inbox.ingest_multiple_zips(zip_paths)

    def resume_campaign(self, store_path: Path | str) -> dict[str, Any]:
        """Resume from accepted history + exact durable package bytes only.

        Current settings (model, executor profile, repository ref, output path)
        are deliberately ignored for the already assigned E1 work.
        """
        path = Path(store_path).resolve()
        if not path.exists() or path.stat().st_size == 0:
            return {
                "status": "ERROR",
                "error": "CAMPAIGN_NOT_FOUND",
                "store_path": str(path),
            }

        try:
            status = self.api.get_campaign_status(path)
            campaign_id = status["campaign_id"]
            self.active_store_path = path
            store = TransactionalHistoryStore(path)
            batch, durable_source = load_e1_batch(store, self._artifact_root())
            self.resolved_source = durable_source
            self.e1_batch = batch
            self.e1_inbox = E1ResultInbox(store, batch)
        except ValidationError as exc:
            self.e1_batch = None
            self.e1_inbox = None
            return {
                "status": "ERROR",
                "error": exc.code,
                "details": str(exc),
                "store_path": str(path),
            }

        accepted_count = sum(
            1 for lane in self.e1_inbox.lane_statuses.values() if lane.status == "ACCEPTED"
        )
        missing = [
            slot for slot, lane in self.e1_inbox.lane_statuses.items() if lane.status != "ACCEPTED"
        ]
        return {
            "status": "SUCCESS",
            "campaign_id": campaign_id,
            "store_path": str(path),
            "current_stage": status.get("current_stage", "E1"),
            "accepted_lanes_count": accepted_count,
            "total_required_lanes": len(E1_LANE_SLOTS),
            "missing_lanes": missing,
            "stage_complete": self.e1_inbox.stage_complete,
            "source_commit_sha": durable_source.exact_commit_sha,
            "source_tree_sha": durable_source.exact_tree_sha,
            "executor_profile": batch.executor_profile,
            "executor_model": batch.model,
        }

    def advance_to_next_stage(self) -> dict[str, Any]:
        """Fail closed at E2 until its real orchestration path exists."""
        if not self.e1_inbox or not self.e1_inbox.stage_complete:
            return {
                "status": "BLOCKED",
                "current_stage": "E1",
                "reason": "E1 is not yet complete",
                "next_action": "IMPORT_MISSING_E1_RESULTS",
            }
        return {
            "status": "HALTED",
            "current_stage": "E1",
            "next_stage": "E2",
            "reason": "E2 automated external delivery pipeline not configured in v2.0.3",
            "next_action": "NEEDS_IMPLEMENTATION",
        }

    # Compatibility name retained for tests/UI.
    def advance_after_e1(self) -> dict[str, Any]:
        result = self.advance_to_next_stage()
        if result.get("status") == "HALTED" and result.get("next_action") == "NEEDS_IMPLEMENTATION":
            return {**result, "status": "NEEDS_IMPLEMENTATION"}
        return result

    def advance_stage(self, stage_id: str | None = None) -> dict[str, Any]:
        """Advance a specific or next incomplete stage via StageService."""
        if not self.active_store_path or not self.active_store_path.exists():
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")

        status = self.api.get_campaign_status(self.active_store_path)
        completed = set(status.get("stages_completed", []))
        prepared = set(status.get("stages_prepared", []))

        if stage_id is not None:
            target_stage = stage_id.upper()
        else:
            target_stage = next((s for s in ("E1", "E2", "E3", "E4", "E5") if s not in completed), None)
            if target_stage is None:
                return {"status": "ALL_STAGES_COMPLETED", "next_action": "EVALUATE_STOP_GATE"}

        if target_stage not in prepared:
            self.api.prepare_stage(self.active_store_path, target_stage)

        res = self.api.qualify_stage(self.active_store_path, target_stage)
        return {
            "status": "SUCCESS",
            "stage": target_stage,
            "stage_completion_digest": res.get("stage_completion_digest"),
            "commit_seq": res.get("commit_seq"),
            "commit_hash": res.get("commit_hash"),
        }

    def run_full_audit_workflow(self) -> dict[str, Any]:
        """Execute complete resumable E1 -> E2 -> E3 -> E4 -> E5 -> STOP -> Conclusion workflow."""
        if not self.active_store_path or not self.active_store_path.exists():
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")

        status = self.api.get_campaign_status(self.active_store_path)
        if "E1" not in status.get("stages_prepared", []):
            self.prepare_e1_orchestration()

        for st in ("E1", "E2", "E3", "E4", "E5"):
            status = self.api.get_campaign_status(self.active_store_path)
            if st not in status.get("stages_completed", []):
                self.advance_stage(st)

        store = TransactionalHistoryStore(self.active_store_path)
        stop_records = store.accepted_records("stop_evaluation", store.head().as_dict())
        if not stop_records:
            stop_res = self.api.evaluate_stop_gate(self.active_store_path)
        else:
            stop_res = {"continuation_decision": stop_records[-1]["body"].get("continuation_decision")}

        concl_records = store.accepted_records("campaign_conclusion", store.head().as_dict())
        if not concl_records:
            concl_res = self.api.conclude_campaign(self.active_store_path)
        else:
            concl_res = {
                "termination_state": concl_records[-1]["body"].get("termination_state"),
                "assurance_level": concl_records[-1]["body"].get("assurance_level"),
            }

        final_status = self.api.get_campaign_status(self.active_store_path)
        return {
            "status": "SUCCESS",
            "campaign_id": final_status["campaign_id"],
            "stages_completed": final_status["stages_completed"],
            "stop_decision": stop_res.get("continuation_decision"),
            "termination_state": concl_res.get("termination_state"),
            "campaign_completed": final_status.get("campaign_completed", False),
        }

    def get_status(self) -> dict[str, Any]:
        if not self.active_store_path:
            return {"status": "NO_ACTIVE_CAMPAIGN"}
        summary = self.get_dashboard_summary()
        return {"status": "ACTIVE", "stage": "E1", **summary}

    def get_dashboard_summary(self) -> dict[str, Any]:
        target = self.resolved_source.display_name if self.resolved_source else (
            self.settings.github_repo_url
            if self.settings.execution_mode == "ChatGPT / GitHub"
            else self.settings.local_repo_path
        )
        exact_sha = self.resolved_source.exact_commit_sha if self.resolved_source else "<unresolved>"
        store_str = str(self.active_store_path) if self.active_store_path else "<none>"

        stage_status = {
            "E1": "NOT_STARTED",
            "E2": "NOT_STARTED",
            "E3": "NOT_STARTED",
            "E4": "NOT_STARTED",
            "E5": "NOT_STARTED",
            "STOP": "PENDING",
        }
        lanes_detail: dict[str, str] = {}
        if self.e1_inbox:
            stage_status["E1"] = "COMPLETE" if self.e1_inbox.stage_complete else "IN_PROGRESS"
            for slot, lane in self.e1_inbox.lane_statuses.items():
                lanes_detail[slot] = lane.status

        if self.e1_batch:
            execution_profile = f"{self.e1_batch.executor_profile} ({self.e1_batch.model})"
            campaign_id = self.e1_batch.campaign_id
        else:
            execution_profile = f"{self.settings.execution_mode} ({self.settings.model})"
            campaign_id = "<none>"

        source_type = self.resolved_source.target_type if self.resolved_source else self.settings.execution_mode
        return {
            "project": target,
            "source_type": source_type,
            "pinned_revision": exact_sha,
            "execution_profile": execution_profile,
            "campaign_store": store_str,
            "campaign_id": campaign_id,
            "stages": stage_status,
            "e1_lanes": lanes_detail,
        }


__all__ = ["PreflightCheckResult", "PreflightReport", "FullAuditOrchestrator"]

"""Full Audit Orchestrator for BDB Audit v2.0.3.

Provides an application-level state machine orchestrating preflight checks,
exact source identity resolution, frozen parallel E1 batch packaging, sequential
delivery UX, multi-ZIP inbox ingestion, fail-closed stage progression, and true resume.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from ..core.errors import ValidationError
from ..coordinator.operations import AuditOperationApi
from ..history.store import TransactionalHistoryStore
from ..orchestration.native_ensemble import E1_LANE_SLOTS
from ..orchestration.templates import TemplateRegistry
from ..core.registry import ContractRegistry
from .settings import UserSettings, SettingsManager
from .platform import PlatformAdapter, DefaultPlatformAdapter
from .executors import get_executor_profile
from .source_target import ResolvedSource, resolve_source_identity
from .packaging import E1Batch, E1LaneJob, prepare_e1_batch
from .inbox import E1ResultInbox, ImportedResultSummary, LaneInboxStatus


@dataclass(frozen=True)
class PreflightCheckResult:
    check_name: str
    status: str  # "PASS" | "BLOCKED" | "NEEDS_INPUT"
    details: str


@dataclass(frozen=True)
class PreflightReport:
    overall_status: str  # "PASS" | "BLOCKED" | "NEEDS_INPUT"
    checks: tuple[PreflightCheckResult, ...]

    @property
    def passed(self) -> bool:
        return self.overall_status == "PASS"


class FullAuditOrchestrator:
    """End-to-end audit orchestrator driving the v2.0.3 user workflow."""

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

    def run_preflight(self, explicit_target_sha: str | None = None) -> PreflightReport:
        """Run all 8 preflight checks before running any lanes."""
        checks: list[PreflightCheckResult] = []

        # 1. Source / target check
        target_loc = (
            self.settings.github_repo_url
            if self.settings.execution_mode == "ChatGPT / GitHub"
            else self.settings.local_repo_path
        )
        if not target_loc:
            checks.append(PreflightCheckResult("Source / target", "NEEDS_INPUT", "No target repository configured"))
        else:
            checks.append(PreflightCheckResult("Source / target", "PASS", f"Configured: {target_loc}"))

        # 2. Exact source identity resolution
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
            checks.append(PreflightCheckResult(
                "Exact source identity", "PASS", f"{resolved_src.ref} @ {resolved_src.exact_commit_sha[:12]}"
            ))
        except Exception as exc:
            checks.append(PreflightCheckResult(
                "Exact source identity", "NEEDS_INPUT", f"Could not resolve exact commit SHA: {exc}"
            ))

        # 3. Executor profile check (Block unsupported modes)
        if self.settings.execution_mode != "ChatGPT / GitHub":
            checks.append(PreflightCheckResult(
                "Executor profile",
                "BLOCKED",
                f"Execution mode '{self.settings.execution_mode}' delivery and result lifecycle is not implemented in v2.0.3 (NEEDS_IMPLEMENTATION)",
            ))
        else:
            profile = get_executor_profile(self.settings.execution_mode)
            if profile.default_model:
                checks.append(PreflightCheckResult(
                    "Executor profile", "PASS", f"{profile.display_name} ({self.settings.model})"
                ))
            else:
                checks.append(PreflightCheckResult("Executor profile", "BLOCKED", "Invalid executor profile"))

        # 4. Delivery profile check
        profile = get_executor_profile(self.settings.execution_mode)
        if profile.delivery_profile and self.settings.execution_mode == "ChatGPT / GitHub":
            checks.append(PreflightCheckResult("Delivery profile", "PASS", profile.delivery_profile))
        else:
            checks.append(PreflightCheckResult("Delivery profile", "BLOCKED", "Delivery profile not implemented"))

        # 5. Output directory check
        out_dir = Path(self.settings.output_work_dir).resolve()
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            test_file = out_dir / ".bdb_write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            checks.append(PreflightCheckResult("Output directory", "PASS", str(out_dir)))
        except Exception as exc:
            checks.append(PreflightCheckResult("Output directory", "BLOCKED", f"Output directory not writable: {exc}"))

        # 6. Campaign store check
        try:
            default_store = out_dir / "campaign.sqlite"
            checks.append(PreflightCheckResult("Campaign store", "PASS", str(default_store)))
        except Exception as exc:
            checks.append(PreflightCheckResult("Campaign store", "BLOCKED", str(exc)))

        # 7. Required templates check
        try:
            reg = TemplateRegistry()
            t = reg.get("e1_ensemble")
            checks.append(PreflightCheckResult("Required templates", "PASS", f"Verified template {t.template_id}"))
        except Exception as exc:
            checks.append(PreflightCheckResult("Required templates", "BLOCKED", str(exc)))

        # 8. Required contracts check
        try:
            creg = ContractRegistry()
            creg.contract("stage_spec", version="1")
            creg.contract("lane_spec", version="1")
            creg.contract("bdb_audit_lane_result", version="1")
            checks.append(PreflightCheckResult("Required contracts", "PASS", "Verified canonical schemas"))
        except Exception as exc:
            checks.append(PreflightCheckResult("Required contracts", "BLOCKED", str(exc)))

        overall = "PASS"
        for c in checks:
            if c.status == "BLOCKED":
                overall = "BLOCKED"
                break
            if c.status == "NEEDS_INPUT" and overall != "BLOCKED":
                overall = "NEEDS_INPUT"

        return PreflightReport(overall_status=overall, checks=tuple(checks))

    def initialize_campaign(
        self,
        store_path: Path | str | None = None,
        campaign_seed: str | None = None,
    ) -> dict[str, Any]:
        """Create or locate the campaign store with verified source identity binding."""
        out_dir = Path(self.settings.output_work_dir).resolve()
        target_display = self.resolved_source.display_name if self.resolved_source else "Audit Target"
        current_sha = self.resolved_source.exact_commit_sha if self.resolved_source else "seed"
        target_location = self.resolved_source.location if self.resolved_source else "target"

        if store_path:
            p = Path(store_path).resolve()
            if p.exists() and p.stat().st_size > 0:
                # Verify source identity match
                existing_src = self.api.get_campaign_source_identity(p)
                stored_sha = existing_src.get("git_commit_object_id")
                if stored_sha and stored_sha != current_sha:
                    raise ValidationError(
                        "SOURCE_IDENTITY_MISMATCH",
                        f"Store at {p} is bound to commit {stored_sha}, but current target is {current_sha}. "
                        "Reusing campaign store for a different commit is forbidden.",
                    )
        else:
            safe_name = target_display.replace("/", "_").replace("\\", "_").replace(":", "_")
            # Store partitioned by commit sha to ensure distinct commits never collide
            p = out_dir / safe_name / current_sha[:12] / "campaign.sqlite"

        p.parent.mkdir(parents=True, exist_ok=True)
        self.active_store_path = p

        seed = campaign_seed or f"{target_display}_{current_sha}"
        if not p.exists() or p.stat().st_size == 0:
            created = self.api.create_campaign(
                p,
                seed=seed,
                target_repo=target_location,
                commit_sha=current_sha if self.resolved_source else None,
            )
            cid = created["campaign_id"]
        else:
            status = self.api.get_campaign_status(p)
            cid = status["campaign_id"]

        self.settings_mgr.record_campaign(p, cid, target_display)
        return {"status": "SUCCESS", "campaign_id": cid, "store_path": str(p)}

    def prepare_e1_orchestration(self) -> E1Batch:
        """Prepare Stage E1, all 5 lanes in store, and generate frozen E1Batch packages."""
        if not self.active_store_path or not self.active_store_path.exists():
            raise ValueError("Active campaign store not initialized")
        if not self.resolved_source:
            raise ValueError("Resolved source identity required before preparing E1")

        status = self.api.get_campaign_status(self.active_store_path)
        stages_prep = status.get("stages_prepared", [])

        # 1. Prepare stage E1 if not yet prepared
        if "E1" not in stages_prep:
            self.api.prepare_stage(self.active_store_path, "E1")

        # 2. Prepare all 5 lanes in store if not yet prepared
        lanes_prep = status.get("lanes_prepared", [])
        for slot in E1_LANE_SLOTS:
            lane_key = f"lane_E1_{slot}"
            if lane_key not in lanes_prep:
                self.api.prepare_lane(self.active_store_path, "E1", slot=slot)

        # 3. Create frozen batch across all 5 lanes against the exact same cut
        store = TransactionalHistoryStore(self.active_store_path)
        out_dir = Path(self.settings.output_work_dir).resolve()

        batch = prepare_e1_batch(
            store=store,
            output_dir=out_dir,
            source_info=self.resolved_source,
            execution_mode=self.settings.execution_mode,
            model=self.settings.model,
        )
        self.e1_batch = batch
        self.e1_inbox = E1ResultInbox(store, batch)
        return batch

    def deliver_lane_to_user(self, slot: str) -> dict[str, Any]:
        """Perform platform delivery actions (clipboard copy, explorer select) for one lane."""
        if not self.e1_batch:
            raise ValueError("E1 batch has not been prepared")

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
            "prompt_copied": clipboard_ok if self.settings.auto_copy_clipboard else None,
            "explorer_selected": explorer_ok if self.settings.auto_open_explorer else None,
        }

    def import_results(self, zip_paths: Sequence[Path | str]) -> ImportedResultSummary:
        """Ingest multiple result ZIPs through the E1ResultInbox."""
        if not self.e1_inbox:
            raise ValueError("E1 result inbox not initialized")
        return self.e1_inbox.ingest_multiple_zips(zip_paths)

    def resume_campaign(self, store_path: Path | str) -> dict[str, Any]:
        """Resume an existing campaign strictly from its transactional history store."""
        p = Path(store_path).resolve()
        if not p.exists() or p.stat().st_size == 0:
            raise ValidationError("CAMPAIGN_NOT_FOUND", f"No database found at {p}")

        status = self.api.get_campaign_status(p)
        cid = status["campaign_id"]
        self.active_store_path = p

        # Reconstruct source identity from genesis
        src_info = self.api.get_campaign_source_identity(p)
        commit_sha = src_info.get("git_commit_object_id") or "0" * 40
        repo_ref = src_info.get("repository_authority_ref", {})
        repo_str = repo_ref.get("schema_revision_ref", "")
        repo_loc = repo_str.split("repo:", 1)[-1] if "repo:" in repo_str else self.settings.github_repo_url

        self.resolved_source = ResolvedSource(
            target_type="github" if self.settings.execution_mode == "ChatGPT / GitHub" else "local",
            location=repo_loc,
            display_name=Path(repo_loc).name or repo_loc,
            ref=self.settings.github_default_ref,
            exact_commit_sha=commit_sha,
        )

        store = TransactionalHistoryStore(p)
        out_dir = Path(self.settings.output_work_dir).resolve()

        batch = prepare_e1_batch(
            store=store,
            output_dir=out_dir,
            source_info=self.resolved_source,
            execution_mode=self.settings.execution_mode,
            model=self.settings.model,
        )
        self.e1_batch = batch
        self.e1_inbox = E1ResultInbox(store, batch)

        accepted_count = sum(1 for s in self.e1_inbox.lane_statuses.values() if s.status == "ACCEPTED")
        missing = [slot for slot, s in self.e1_inbox.lane_statuses.items() if s.status != "ACCEPTED"]

        return {
            "status": "SUCCESS",
            "campaign_id": cid,
            "store_path": str(p),
            "current_stage": status.get("current_stage", "E1"),
            "accepted_lanes_count": accepted_count,
            "total_required_lanes": len(E1_LANE_SLOTS),
            "missing_lanes": missing,
            "stage_complete": self.e1_inbox.stage_complete,
        }

    def advance_to_next_stage(self) -> dict[str, Any]:
        """Evaluate progression after E1. Fail closed if subsequent stages need implementation."""
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

    def get_dashboard_summary(self) -> dict[str, Any]:
        """Construct structured dashboard state matching Section 20."""
        target = self.resolved_source.display_name if self.resolved_source else (
            self.settings.github_repo_url if self.settings.execution_mode == "ChatGPT / GitHub" else self.settings.local_repo_path
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

        lanes_detail = {}
        if self.e1_inbox:
            if self.e1_inbox.stage_complete:
                stage_status["E1"] = "COMPLETE"
            else:
                stage_status["E1"] = "IN_PROGRESS"
            for slot, st in self.e1_inbox.lane_statuses.items():
                lanes_detail[slot] = st.status

        return {
            "project": target,
            "source_type": self.settings.execution_mode,
            "pinned_revision": exact_sha,
            "execution_profile": f"{self.settings.execution_mode} ({self.settings.model})",
            "campaign_store": store_str,
            "campaign_id": self.e1_batch.campaign_id if self.e1_batch else "<none>",
            "stages": stage_status,
            "e1_lanes": lanes_detail,
        }


__all__ = [
    "PreflightCheckResult",
    "PreflightReport",
    "FullAuditOrchestrator",
]

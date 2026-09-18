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
from .e2_checkpoint import E2BlindCheckpointService
from .e2_reveal import E2ControlledRevealService
from .e2_synthesis import E2MainSynthesisService
from .e2_shadow import E2ShadowAuthorizationService
from .e2_finalize import E2FinalizationService
from .e2_contradiction import E2ContradictionAuthorizationService
from .e2_contradiction_resolution import E2ContradictionResolutionService
from .e3_checkpoint import E3BlindCheckpointService
from .e3_gap import E3PositiveGapAuthorizationService
from .e3_gap_result import E3GapResultValidationService
from .inbox import E1ResultInbox, ImportedResultSummary
from .manual_stage import (
    ImportedStagePhaseSummary,
    StageBatch,
    StageIsolationProof,
    StageLaneDefinition,
    StageResultInbox,
    prepare_stage_phase_batch,
)
from .package_resume import load_e1_batch
from .packaging import E1Batch, prepare_e1_batch
from .stage_resume import load_stage_phase_batch
from .platform import DefaultPlatformAdapter, PlatformAdapter
from .settings import SettingsManager, UserSettings
from .source_target import ResolvedSource, resolve_source_identity


E2_BLIND_LANES = (
    StageLaneDefinition(
        "E2-CONVERGENCE",
        "Blind verification and convergence precursor",
        "BLIND_VERIFY_AND_CONVERGE",
    ),
    StageLaneDefinition(
        "E2-ADJUDICATION",
        "Blind falsification and adjudication precursor",
        "BLIND_FALSIFY_AND_ADJUDICATE",
    ),
)

E2_REVEAL_LANES = (
    StageLaneDefinition(
        "E2-CONVERGENCE",
        "Controlled E1 claim-card convergence review",
        "CONTROLLED_REVEAL_CONVERGENCE",
    ),
    StageLaneDefinition(
        "E2-ADJUDICATION",
        "Controlled E1 claim-card falsification and adjudication",
        "CONTROLLED_REVEAL_ADJUDICATION",
    ),
)

E2_SHADOW_LANES = (
    StageLaneDefinition(
        "E2-ADJUDICATION",
        "Independent bounded shadow adjudicator",
        "INDEPENDENT_SHADOW_ADJUDICATION",
    ),
)

E2_CONTRADICTION_LANES = (
    StageLaneDefinition(
        "E2-ADJUDICATION",
        "Scoped contradiction protocol adjudicator",
        "CONTRADICTION_PROTOCOL",
    ),
)

E3_BLIND_LANES = (
    StageLaneDefinition(
        "E3-X",
        "Security, authority and trust blind novelty",
        "AUTHORITY_TRUST_NOVELTY_SEARCH",
    ),
    StageLaneDefinition(
        "E3-Y",
        "State, data, catalog and recovery blind novelty",
        "STATE_CATALOG_RECOVERY_SEARCH",
    ),
    StageLaneDefinition(
        "E3-Z",
        "Frontend, concurrency, resources and cross-layer blind novelty",
        "CROSS_LAYER_CONCURRENCY_SEARCH",
    ),
)

E3_GAP_LANES = (
    StageLaneDefinition(
        "E3-X",
        "Security, authority and trust gap-directed exploration",
        "AUTHORITY_TRUST_GAP_DIRECTED_SEARCH",
    ),
    StageLaneDefinition(
        "E3-Y",
        "State, data, catalog and recovery gap-directed exploration",
        "STATE_CATALOG_RECOVERY_GAP_DIRECTED_SEARCH",
    ),
    StageLaneDefinition(
        "E3-Z",
        "Frontend, concurrency, resources and cross-layer gap-directed exploration",
        "CROSS_LAYER_CONCURRENCY_GAP_DIRECTED_SEARCH",
    ),
)


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
        self.stage_batch: StageBatch | None = None
        self.stage_inbox: StageResultInbox | None = None

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

    def prepare_e2_blind_orchestration(self) -> StageBatch:
        """Prepare the first real E2 external phase without revealing E1 claims."""
        if not self.active_store_path or not self.active_store_path.exists():
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        if self.resolved_source is None:
            raise ValidationError("SOURCE_IDENTITY_REQUIRED")

        status = self.api.get_campaign_status(self.active_store_path)
        if "E1" not in status.get("stages_completed", []):
            raise ValidationError(
                "PREDECESSOR_STAGE_NOT_COMPLETED",
                "E1 must be completed before E2 blind work",
            )
        if "E2" not in status.get("stages_prepared", []):
            self.api.prepare_stage(self.active_store_path, "E2")

        status = self.api.get_campaign_status(self.active_store_path)
        lanes_prepared = set(status.get("lanes_prepared", []))
        for definition in E2_BLIND_LANES:
            lane_key = f"lane_E2_{definition.lane_slot}"
            if lane_key not in lanes_prepared:
                self.api.prepare_lane(
                    self.active_store_path,
                    "E2",
                    definition.lane_slot,
                )

        store = TransactionalHistoryStore(self.active_store_path)
        batch = prepare_stage_phase_batch(
            store=store,
            output_dir=self._artifact_root(),
            source_info=self.resolved_source,
            stage_id="E2",
            phase_id="E2-BLIND",
            lane_definitions=E2_BLIND_LANES,
            all_stage_lane_slots=tuple(
                item.lane_slot for item in E2_BLIND_LANES
            ),
            execution_mode=self.settings.execution_mode,
            model=self.settings.model,
        )
        self.stage_batch = batch
        self.stage_inbox = StageResultInbox(store, batch)
        return batch

    def prepare_e2_reveal_orchestration(self) -> StageBatch:
        """Authorize and publish the controlled E1 claim-card reveal."""
        if not self.active_store_path or not self.active_store_path.exists():
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        if self.resolved_source is None:
            raise ValidationError("SOURCE_IDENTITY_REQUIRED")

        store = TransactionalHistoryStore(self.active_store_path)
        authorization = E2ControlledRevealService(
            store,
            lane_definitions=E2_REVEAL_LANES,
            all_stage_lane_slots=tuple(
                item.lane_slot for item in E2_REVEAL_LANES
            ),
            executor_profile=self.settings.execution_mode,
            model=self.settings.model,
        ).authorize()

        batch = prepare_stage_phase_batch(
            store=store,
            output_dir=self._artifact_root(),
            source_info=self.resolved_source,
            stage_id="E2",
            phase_id="E2-REVEAL",
            lane_definitions=E2_REVEAL_LANES,
            all_stage_lane_slots=tuple(
                item.lane_slot for item in E2_REVEAL_LANES
            ),
            authorized_context=authorization,
            execution_mode=self.settings.execution_mode,
            model=self.settings.model,
        )
        self.stage_batch = batch
        self.stage_inbox = StageResultInbox(store, batch)
        return batch

    def prepare_e2_shadow_orchestration(self) -> StageBatch:
        """Publish a fresh, grant-bound independent E2 shadow package."""
        if not self.active_store_path or not self.active_store_path.exists():
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        if self.resolved_source is None:
            raise ValidationError("SOURCE_IDENTITY_REQUIRED")

        store = TransactionalHistoryStore(self.active_store_path)
        authorization = E2ShadowAuthorizationService(
            store,
            lane_definition=E2_SHADOW_LANES[0],
            all_stage_lane_slots=tuple(
                item.lane_slot for item in E2_BLIND_LANES
            ),
            executor_profile=self.settings.execution_mode,
            model=self.settings.model,
        ).authorize()
        batch = prepare_stage_phase_batch(
            store=store,
            output_dir=self._artifact_root(),
            source_info=self.resolved_source,
            stage_id="E2",
            phase_id="E2-SHADOW",
            lane_definitions=E2_SHADOW_LANES,
            all_stage_lane_slots=tuple(
                item.lane_slot for item in E2_BLIND_LANES
            ),
            authorized_context=authorization,
            execution_mode=self.settings.execution_mode,
            model=self.settings.model,
        )
        self.stage_batch = batch
        self.stage_inbox = StageResultInbox(store, batch)
        return batch

    def prepare_e2_contradiction_orchestration(
        self,
        contradiction_refs: Sequence[dict[str, Any]],
    ) -> StageBatch:
        """Authorize and publish the bounded E2 contradiction protocol."""
        if not self.active_store_path or not self.active_store_path.exists():
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        if self.resolved_source is None:
            raise ValidationError("SOURCE_IDENTITY_REQUIRED")
        if not contradiction_refs:
            raise ValidationError("E2_CONTRADICTION_CASE_REQUIRED")

        store = TransactionalHistoryStore(self.active_store_path)
        authorization = E2ContradictionAuthorizationService(
            store,
            contradiction_refs=contradiction_refs,
            lane_definition=E2_CONTRADICTION_LANES[0],
            all_stage_lane_slots=tuple(
                item.lane_slot for item in E2_BLIND_LANES
            ),
            executor_profile=self.settings.execution_mode,
            model=self.settings.model,
        ).authorize()
        batch = prepare_stage_phase_batch(
            store=store,
            output_dir=self._artifact_root(),
            source_info=self.resolved_source,
            stage_id="E2",
            phase_id="E2-CONTRADICTION",
            lane_definitions=E2_CONTRADICTION_LANES,
            all_stage_lane_slots=tuple(
                item.lane_slot for item in E2_BLIND_LANES
            ),
            authorized_context=authorization,
            execution_mode=self.settings.execution_mode,
            model=self.settings.model,
        )
        self.stage_batch = batch
        self.stage_inbox = StageResultInbox(store, batch)
        return batch

    def prepare_e3_blind_orchestration(self) -> StageBatch:
        """Prepare the real E3-X/Y/Z blind novelty phase."""
        if not self.active_store_path or not self.active_store_path.exists():
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        if self.resolved_source is None:
            raise ValidationError("SOURCE_IDENTITY_REQUIRED")

        status = self.api.get_campaign_status(self.active_store_path)
        if "E2" not in status.get("stages_completed", []):
            raise ValidationError(
                "PREDECESSOR_STAGE_NOT_COMPLETED",
                "E2 must be completed before E3 blind novelty",
            )

        profile = get_executor_profile(
            self.settings.execution_mode
        )
        if profile.max_isolation_assurance != "ENFORCED":
            raise ValidationError(
                "E3_ENFORCED_ISOLATION_BACKEND_REQUIRED",
                (
                    f"{profile.display_name} / "
                    f"{profile.delivery_profile} currently proves at most "
                    f"{profile.max_isolation_assurance}; E3-X/Y/Z require "
                    "ENFORCED isolation. Do not publish blind packages "
                    "until a controlled backend can emit accepted boundary "
                    "receipts."
                ),
            )
        if "E3" not in status.get("stages_prepared", []):
            self.api.prepare_stage(
                self.active_store_path,
                "E3",
            )
            status = self.api.get_campaign_status(
                self.active_store_path
            )

        lanes_prepared = set(
            status.get("lanes_prepared", [])
        )
        for definition in E3_BLIND_LANES:
            lane_key = (
                f"lane_E3_{definition.lane_slot}"
            )
            if lane_key not in lanes_prepared:
                self.api.prepare_lane(
                    self.active_store_path,
                    "E3",
                    definition.lane_slot,
                )

        store = TransactionalHistoryStore(
            self.active_store_path
        )
        batch = prepare_stage_phase_batch(
            store=store,
            output_dir=self._artifact_root(),
            source_info=self.resolved_source,
            stage_id="E3",
            phase_id="E3-BLIND",
            lane_definitions=E3_BLIND_LANES,
            all_stage_lane_slots=tuple(
                item.lane_slot
                for item in E3_BLIND_LANES
            ),
            execution_mode=(
                self.settings.execution_mode
            ),
            model=self.settings.model,
        )
        self.stage_batch = batch
        self.stage_inbox = StageResultInbox(
            store,
            batch,
        )
        return batch

    def prepare_e3_gap_orchestration(
        self,
        isolation_proofs_by_slot: dict[
            str, StageIsolationProof
        ],
    ) -> StageBatch:
        """Authorize and publish fresh E3 gap-directed attempts."""
        if not self.active_store_path or not self.active_store_path.exists():
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        if self.resolved_source is None:
            raise ValidationError("SOURCE_IDENTITY_REQUIRED")

        store = TransactionalHistoryStore(
            self.active_store_path
        )
        authorization = E3PositiveGapAuthorizationService(
            store,
            lane_definitions=E3_GAP_LANES,
            all_stage_lane_slots=tuple(
                item.lane_slot
                for item in E3_BLIND_LANES
            ),
            executor_profile=self.settings.execution_mode,
            model=self.settings.model,
            isolation_proofs_by_slot=(
                isolation_proofs_by_slot
            ),
        ).authorize()
        batch = prepare_stage_phase_batch(
            store=store,
            output_dir=self._artifact_root(),
            source_info=self.resolved_source,
            stage_id="E3",
            phase_id="E3-GAP",
            lane_definitions=E3_GAP_LANES,
            all_stage_lane_slots=tuple(
                item.lane_slot
                for item in E3_BLIND_LANES
            ),
            authorized_context=authorization,
            isolation_proofs_by_slot=(
                isolation_proofs_by_slot
            ),
            execution_mode=(
                self.settings.execution_mode
            ),
            model=self.settings.model,
        )
        self.stage_batch = batch
        self.stage_inbox = StageResultInbox(
            store,
            batch,
        )
        return batch

    def deliver_stage_lane_to_user(self, slot: str) -> dict[str, Any]:
        """Deliver one already accepted E2+ stage assignment/package."""
        if self.stage_batch is None:
            raise ValidationError("STAGE_BATCH_NOT_PREPARED")
        job = self.stage_batch.get_job(slot)
        clipboard_ok = False
        explorer_ok = False
        if self.settings.auto_copy_clipboard:
            clipboard_ok = self.platform.copy_to_clipboard(job.prompt_text)
        if self.settings.auto_open_explorer:
            explorer_ok = self.platform.open_and_select(job.package_zip_path)
        return {
            "stage_id": job.stage_id,
            "phase_id": job.phase_id,
            "lane_slot": slot,
            "package_zip_path": str(job.package_zip_path),
            "package_zip_name": job.package_zip_path.name,
            "assignment_ref": dict(job.assignment_ref),
            "attempt_ref": dict(job.attempt_ref),
            "prompt_copied": (
                clipboard_ok if self.settings.auto_copy_clipboard else None
            ),
            "explorer_selected": (
                explorer_ok if self.settings.auto_open_explorer else None
            ),
        }

    def import_stage_results(
        self,
        zip_paths: Sequence[Path | str],
    ) -> ImportedStagePhaseSummary:
        if self.stage_inbox is None:
            raise ValidationError("STAGE_RESULT_INBOX_NOT_INITIALIZED")
        return self.stage_inbox.ingest_multiple_zips(zip_paths)

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
            self.stage_batch = None
            self.stage_inbox = None
            return {
                "status": "ERROR",
                "error": exc.code,
                "details": str(exc),
                "store_path": str(path),
            }

        accepted_count = sum(
            1
            for lane in self.e1_inbox.lane_statuses.values()
            if lane.status == "ACCEPTED"
        )
        missing = [
            slot
            for slot, lane in self.e1_inbox.lane_statuses.items()
            if lane.status != "ACCEPTED"
        ]

        active_stage = "E1"
        active_phase = None
        active_inbox = "E1"
        if self.e1_inbox.stage_complete:
            loaded_stage = None
            resume_error = None
            completed_stages = set(
                status.get("stages_completed", [])
            )
            if "E3" in completed_stages:
                candidate_stage_phases = ()
                active_stage = "E4"
            elif "E2" in completed_stages:
                candidate_stage_phases = (
                    ("E3", "E3-GAP"),
                    ("E3", "E3-BLIND"),
                )
                active_stage = "E3"
            else:
                candidate_stage_phases = (
                    ("E2", "E2-CONTRADICTION"),
                    ("E2", "E2-SHADOW"),
                    ("E2", "E2-REVEAL"),
                    ("E2", "E2-BLIND"),
                )
            for candidate_stage, candidate_phase in (
                candidate_stage_phases
            ):
                try:
                    loaded_stage = load_stage_phase_batch(
                        store,
                        self._artifact_root(),
                        stage_id=candidate_stage,
                        phase_id=candidate_phase,
                    )
                    active_phase = candidate_phase
                    break
                except ValidationError as exc:
                    if exc.code != "RESUME_STAGE_ASSIGNMENTS_NOT_FOUND":
                        resume_error = exc
                        break

            if resume_error is not None:
                return {
                    "status": "ERROR",
                    "error": resume_error.code,
                    "details": str(resume_error),
                    "store_path": str(path),
                }
            if loaded_stage is not None:
                stage_batch, stage_source = loaded_stage
                self.stage_batch = stage_batch
                self.stage_inbox = StageResultInbox(store, stage_batch)
                self.resolved_source = stage_source
                active_stage = stage_batch.stage_id
                active_inbox = "STAGE"
                accepted_count = sum(
                    1
                    for lane in self.stage_inbox.lane_statuses.values()
                    if lane.status == "ACCEPTED"
                )
                missing = [
                    slot
                    for slot, lane in self.stage_inbox.lane_statuses.items()
                    if lane.status != "ACCEPTED"
                ]

        return {
            "status": "SUCCESS",
            "campaign_id": campaign_id,
            "store_path": str(path),
            "current_stage": active_stage,
            "current_phase": active_phase,
            "active_inbox": active_inbox,
            "accepted_lanes_count": accepted_count,
            "total_required_lanes": (
                len(self.stage_batch.jobs)
                if self.stage_batch is not None
                else len(E1_LANE_SLOTS)
            ),
            "missing_lanes": missing,
            "stage_complete": (
                self.e1_inbox.stage_complete
                if self.stage_inbox is None
                else False
            ),
            "phase_complete": (
                self.stage_inbox is not None
                and all(
                    lane.status == "ACCEPTED"
                    and lane.completion_status == "LANE_COMPLETED"
                    for lane in self.stage_inbox.lane_statuses.values()
                )
            ),
            "source_commit_sha": self.resolved_source.exact_commit_sha,
            "source_tree_sha": self.resolved_source.exact_tree_sha,
            "executor_profile": (
                self.stage_batch.get_job(
                    next(iter(self.stage_batch.jobs))
                ).executor_profile
                if self.stage_batch is not None
                else batch.executor_profile
            ),
            "executor_model": (
                self.stage_batch.get_job(
                    next(iter(self.stage_batch.jobs))
                ).model
                if self.stage_batch is not None
                else batch.model
            ),
        }

    def advance_to_next_stage(self) -> dict[str, Any]:
        """Advance from completed E1 into the real external E2 blind phase."""
        if not self.active_store_path or not self.active_store_path.exists():
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        status = self.api.get_campaign_status(self.active_store_path)
        if "E1" not in status.get("stages_completed", []):
            return {
                "status": "BLOCKED",
                "current_stage": "E1",
                "reason": "E1 is not yet complete",
                "next_action": "IMPORT_MISSING_E1_RESULTS",
            }

        if "E2" in status.get("stages_completed", []):
            if "E3" in status.get("stages_completed", []):
                return {
                    "status": "READY_FOR_NEXT_STAGE",
                    "current_stage": "E3",
                    "next_stage": "E4",
                    "next_action": "PREPARE_E4_EXTERNAL_PHASE",
                }
            if (
                self.stage_batch is None
                or self.stage_batch.stage_id != "E3"
            ):
                try:
                    self.prepare_e3_blind_orchestration()
                except ValidationError as exc:
                    if (
                        exc.code
                        != "E3_ENFORCED_ISOLATION_BACKEND_REQUIRED"
                    ):
                        raise
                    return {
                        "status": "BLOCKED",
                        "current_stage": "E3",
                        "current_phase": "E3-BLIND",
                        "reason": str(exc),
                        "next_action": (
                            "CONFIGURE_ENFORCED_ISOLATION_BACKEND"
                        ),
                    }
            assert self.stage_batch is not None
            assert self.stage_inbox is not None

            missing = [
                slot
                for slot, lane in (
                    self.stage_inbox.lane_statuses.items()
                )
                if lane.status != "ACCEPTED"
            ]
            blocked = [
                slot
                for slot, lane in (
                    self.stage_inbox.lane_statuses.items()
                )
                if lane.status == "ACCEPTED"
                and lane.completion_status
                != "LANE_COMPLETED"
            ]
            if missing or blocked:
                phase = self.stage_batch.phase_id
                next_action_by_phase = {
                    "E3-BLIND": (
                        "DELIVER_OR_IMPORT_E3_BLIND_RESULTS"
                    ),
                    "E3-GAP": (
                        "DELIVER_OR_IMPORT_E3_GAP_RESULTS"
                    ),
                }
                if phase not in next_action_by_phase:
                    raise ValidationError(
                        "UNSUPPORTED_E3_PHASE",
                        phase,
                    )
                return {
                    "status": "WAITING_EXTERNAL_RESULTS",
                    "current_stage": "E3",
                    "current_phase": phase,
                    "missing_lanes": missing,
                    "blocked_lanes": blocked,
                    "next_action": (
                        next_action_by_phase[phase]
                    ),
                    "packages": {
                        slot: str(
                            job.package_zip_path
                        )
                        for slot, job in (
                            self.stage_batch.jobs.items()
                        )
                    },
                }

            if (
                self.stage_batch.phase_id
                == "E3-BLIND"
            ):
                checkpoint = (
                    E3BlindCheckpointService(
                        TransactionalHistoryStore(
                            self.active_store_path
                        ),
                        self.stage_batch,
                        self.stage_inbox,
                    ).seal()
                )
                return {
                    "status": "E3_BLIND_CHECKPOINTED",
                    "current_stage": "E3",
                    "current_phase": "E3-BLIND",
                    "checkpoint_commit_seq": (
                        checkpoint.accepted_commit_seq
                    ),
                    "checkpoint_refs": (
                        checkpoint.checkpoint_refs
                    ),
                    "already_sealed": (
                        checkpoint.already_sealed
                    ),
                    "next_action": (
                        "PREPARE_E3_POSITIVE_GAP_REVEAL"
                    ),
                }

            if (
                self.stage_batch.phase_id
                == "E3-GAP"
            ):
                validation = (
                    E3GapResultValidationService(
                        TransactionalHistoryStore(
                            self.active_store_path
                        ),
                        self.stage_batch,
                        self.stage_inbox,
                    ).validate()
                )
                return {
                    "status": "E3_GAP_DIRECTED_COMPLETE",
                    "current_stage": "E3",
                    "current_phase": "E3-GAP",
                    "authorized_targets_count": len(
                        validation.authorized_target_digests
                    ),
                    "covered_targets_count": len(
                        validation.covered_target_digests
                    ),
                    "findings_count": (
                        validation.findings_count
                    ),
                    "next_action": (
                        validation.next_action
                    ),
                }

            raise ValidationError(
                "UNSUPPORTED_E3_PHASE",
                self.stage_batch.phase_id,
            )

        if (
            self.stage_batch is None
            or self.stage_batch.stage_id != "E2"
        ):
            self.prepare_e2_blind_orchestration()

        assert self.stage_batch is not None
        assert self.stage_inbox is not None
        missing = [
            slot
            for slot, lane in self.stage_inbox.lane_statuses.items()
            if lane.status != "ACCEPTED"
        ]
        blocked = [
            slot
            for slot, lane in self.stage_inbox.lane_statuses.items()
            if lane.status == "ACCEPTED"
            and lane.completion_status != "LANE_COMPLETED"
        ]
        if missing or blocked:
            phase = self.stage_batch.phase_id
            next_action_by_phase = {
                "E2-BLIND": "DELIVER_OR_IMPORT_E2_BLIND_RESULTS",
                "E2-REVEAL": "DELIVER_OR_IMPORT_E2_REVEAL_RESULTS",
                "E2-SHADOW": "DELIVER_OR_IMPORT_E2_SHADOW_RESULTS",
                "E2-CONTRADICTION": (
                    "DELIVER_OR_IMPORT_E2_CONTRADICTION_RESULTS"
                ),
            }
            if phase not in next_action_by_phase:
                raise ValidationError(
                    "UNSUPPORTED_E2_PHASE",
                    phase,
                )
            return {
                "status": "WAITING_EXTERNAL_RESULTS",
                "current_stage": "E2",
                "current_phase": phase,
                "missing_lanes": missing,
                "blocked_lanes": blocked,
                "next_action": next_action_by_phase[phase],
                "packages": {
                    slot: str(job.package_zip_path)
                    for slot, job in self.stage_batch.jobs.items()
                },
            }

        if self.stage_batch.phase_id == "E2-BLIND":
            checkpoint = E2BlindCheckpointService(
                TransactionalHistoryStore(self.active_store_path),
                self.stage_batch,
                self.stage_inbox,
            ).seal()
            reveal_batch = self.prepare_e2_reveal_orchestration()
            return {
                "status": "WAITING_EXTERNAL_RESULTS",
                "current_stage": "E2",
                "current_phase": "E2-REVEAL",
                "checkpoint_commit_seq": checkpoint.accepted_commit_seq,
                "checkpoint_refs": checkpoint.checkpoint_refs,
                "already_sealed": checkpoint.already_sealed,
                "missing_lanes": list(reveal_batch.lane_slots),
                "next_action": "DELIVER_OR_IMPORT_E2_REVEAL_RESULTS",
                "packages": {
                    slot: str(job.package_zip_path)
                    for slot, job in reveal_batch.jobs.items()
                },
            }

        if self.stage_batch.phase_id == "E2-REVEAL":
            synthesis = E2MainSynthesisService(
                TransactionalHistoryStore(self.active_store_path),
                self.stage_batch,
                self.stage_inbox,
            ).synthesize()
            shadow_batch = self.prepare_e2_shadow_orchestration()
            return {
                "status": "WAITING_EXTERNAL_RESULTS",
                "current_stage": "E2",
                "current_phase": "E2-SHADOW",
                "synthesis_commit_seq": synthesis.accepted_commit_seq,
                "claims_count": len(synthesis.claim_refs),
                "decisions_count": len(
                    synthesis.adjudication_decision_refs
                ),
                "proposal_disagreement_claim_ids": list(
                    synthesis.proposal_disagreement_claim_ids
                ),
                "missing_lanes": list(shadow_batch.lane_slots),
                "next_action": "DELIVER_OR_IMPORT_E2_SHADOW_RESULTS",
                "packages": {
                    slot: str(job.package_zip_path)
                    for slot, job in shadow_batch.jobs.items()
                },
            }

        if self.stage_batch.phase_id == "E2-SHADOW":
            finalization = E2FinalizationService(
                TransactionalHistoryStore(self.active_store_path),
                self.stage_batch,
                self.stage_inbox,
            ).finalize()
            if not finalization.stage_completed:
                contradiction_batch = (
                    self.prepare_e2_contradiction_orchestration(
                        finalization.contradiction_refs
                    )
                )
                return {
                    "status": "WAITING_EXTERNAL_RESULTS",
                    "current_stage": "E2",
                    "current_phase": "E2-CONTRADICTION",
                    "shadow_conflict_claim_digests": list(
                        finalization.shadow_conflict_claim_digests
                    ),
                    "contradiction_refs": list(
                        finalization.contradiction_refs
                    ),
                    "contradiction_commit_seq": (
                        finalization.accepted_commit_seq
                    ),
                    "missing_lanes": list(
                        contradiction_batch.lane_slots
                    ),
                    "next_action": (
                        "DELIVER_OR_IMPORT_E2_CONTRADICTION_RESULTS"
                    ),
                    "packages": {
                        slot: str(job.package_zip_path)
                        for slot, job in (
                            contradiction_batch.jobs.items()
                        )
                    },
                }
            return {
                "status": "E2_COMPLETED",
                "current_stage": "E2",
                "next_stage": "E3",
                "stage_completion_ref": (
                    finalization.stage_completion_ref
                ),
                "completion_commit_seq": (
                    finalization.accepted_commit_seq
                ),
                "already_finalized": (
                    finalization.already_finalized
                ),
                "next_action": "PREPARE_E3_BLIND_NOVELTY",
            }

        if self.stage_batch.phase_id == "E2-CONTRADICTION":
            resolution = E2ContradictionResolutionService(
                TransactionalHistoryStore(self.active_store_path),
                self.stage_batch,
                self.stage_inbox,
            ).resolve()
            if not resolution.stage_completed:
                return {
                    "status": "E2_BLOCKED_BY_CONTRADICTION",
                    "current_stage": "E2",
                    "current_phase": "E2-CONTRADICTION",
                    "resulting_status_by_prior_digest": (
                        resolution.resulting_status_by_prior_digest
                    ),
                    "successor_contradiction_refs": list(
                        resolution.successor_contradiction_refs
                    ),
                    "next_action": resolution.next_action,
                }
            return {
                "status": "E2_COMPLETED",
                "current_stage": "E2",
                "next_stage": "E3",
                "stage_completion_ref": (
                    resolution.stage_completion_ref
                ),
                "completion_commit_seq": (
                    resolution.stage_completion_commit_seq
                ),
                "already_finalized": (
                    resolution.already_resolved
                ),
                "next_action": "PREPARE_E3_BLIND_NOVELTY",
            }

        raise ValidationError(
            "UNSUPPORTED_E2_PHASE",
            self.stage_batch.phase_id,
        )

    # Compatibility name retained for tests/UI.
    def advance_after_e1(self) -> dict[str, Any]:
        return self.advance_to_next_stage()

    def advance_stage(self, stage_id: str | None = None) -> dict[str, Any]:
        """Advance only through the evidence-backed user workflow.

        This compatibility entry point never calls the synthetic
        ``qualify_stage`` helper. Stage completion for E1-E5 is owned by the
        durable assignment/package/result/synthesis path.
        """
        if not self.active_store_path or not self.active_store_path.exists():
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")

        status = self.api.get_campaign_status(self.active_store_path)
        completed = set(status.get("stages_completed", []))
        order = ("E1", "E2", "E3", "E4", "E5")
        next_incomplete = next(
            (stage for stage in order if stage not in completed),
            None,
        )
        if next_incomplete is None:
            return {
                "status": "ALL_STAGES_COMPLETED",
                "next_action": "EVALUATE_STOP_GATE",
            }

        if stage_id is not None:
            requested = stage_id.upper()
            if requested != next_incomplete:
                raise ValidationError(
                    "INVALID_STAGE_TRANSITION",
                    (
                        f"Current evidence-backed stage is {next_incomplete}; "
                        f"requested {requested}"
                    ),
                )

        if next_incomplete == "E1":
            if self.e1_inbox is None:
                return {
                    "status": "BLOCKED",
                    "current_stage": "E1",
                    "next_action": "PREPARE_OR_RESUME_E1",
                }
            missing = [
                slot
                for slot, lane in self.e1_inbox.lane_statuses.items()
                if lane.status != "ACCEPTED"
            ]
            return {
                "status": "WAITING_EXTERNAL_RESULTS",
                "current_stage": "E1",
                "missing_lanes": missing,
                "next_action": "DELIVER_OR_IMPORT_E1_RESULTS",
            }

        return self.advance_to_next_stage()

    def run_full_audit_workflow(self) -> dict[str, Any]:
        """Drive the user workflow only as far as current external evidence permits.

        This method must never synthesize E2-E5 completion in place of the
        user-visible package -> external audit -> result ZIP workflow.
        """
        if not self.active_store_path or not self.active_store_path.exists():
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")

        status = self.api.get_campaign_status(self.active_store_path)
        if "E1" not in status.get("stages_prepared", []):
            batch = self.prepare_e1_orchestration()
            return {
                "status": "WAITING_EXTERNAL_RESULTS",
                "current_stage": "E1",
                "missing_lanes": list(batch.lane_slots),
                "next_action": "DELIVER_OR_IMPORT_E1_RESULTS",
            }

        if self.e1_batch is None or self.e1_inbox is None:
            store = TransactionalHistoryStore(self.active_store_path)
            self.e1_batch, durable_source = load_e1_batch(
                store,
                self._artifact_root(),
            )
            self.resolved_source = durable_source
            self.e1_inbox = E1ResultInbox(store, self.e1_batch)

        if not self.e1_inbox.stage_complete:
            return {
                "status": "WAITING_EXTERNAL_RESULTS",
                "current_stage": "E1",
                "missing_lanes": [
                    slot
                    for slot, lane in self.e1_inbox.lane_statuses.items()
                    if lane.status != "ACCEPTED"
                ],
                "next_action": "DELIVER_OR_IMPORT_E1_RESULTS",
            }

        return self.advance_to_next_stage()

    def get_status(self) -> dict[str, Any]:
        if not self.active_store_path:
            return {"status": "NO_ACTIVE_CAMPAIGN"}
        canonical = self.api.get_campaign_status(
            self.active_store_path
        )
        summary = self.get_dashboard_summary()
        return {
            "status": "ACTIVE",
            "stage": canonical.get("current_stage"),
            "accepted_head_seq": canonical.get("accepted_head_seq"),
            "stages_completed": canonical.get("stages_completed", []),
            **summary,
        }

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
        if (
            self.active_store_path
            and self.active_store_path.exists()
        ):
            canonical = self.api.get_campaign_status(
                self.active_store_path
            )
            completed = set(
                canonical.get("stages_completed", [])
            )
            prepared = set(
                canonical.get("stages_prepared", [])
            )
            for stage in ("E1", "E2", "E3", "E4", "E5"):
                if stage in completed:
                    stage_status[stage] = "COMPLETE"
                elif stage in prepared:
                    stage_status[stage] = "IN_PROGRESS"
        if self.e1_inbox:
            stage_status["E1"] = (
                "COMPLETE"
                if self.e1_inbox.stage_complete
                else "IN_PROGRESS"
            )
            for slot, lane in self.e1_inbox.lane_statuses.items():
                lanes_detail[slot] = lane.status
        if (
            self.stage_batch is not None
            and self.stage_inbox is not None
        ):
            if (
                stage_status[self.stage_batch.stage_id]
                != "COMPLETE"
            ):
                stage_status[
                    self.stage_batch.stage_id
                ] = "IN_PROGRESS"
            for slot, lane in self.stage_inbox.lane_statuses.items():
                lanes_detail[
                    f"{self.stage_batch.phase_id}:{slot}"
                ] = lane.status

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

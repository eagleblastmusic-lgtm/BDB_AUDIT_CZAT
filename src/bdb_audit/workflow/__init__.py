"""BDB Audit v2.0.3 User Workflow, Full Audit Orchestration, and Persistent Settings."""
from __future__ import annotations

from .settings import UserSettings, SettingsManager, get_default_settings_manager
from .platform import PlatformAdapter, DefaultPlatformAdapter, MockPlatformAdapter
from .executors import (
    ExecutorProfileDefinition,
    EXECUTION_MODES,
    DEFAULT_EXECUTION_MODE,
    get_executor_profile,
    list_execution_modes,
)
from .source_target import ResolvedSource, resolve_source_identity
from .packaging import E1LaneJob, E1Batch, prepare_e1_batch
from .inbox import E1ResultInbox, ImportedResultSummary, LaneInboxStatus
from .history_projection import CampaignProjection, CampaignHistoryService
from .orchestrator import FullAuditOrchestrator, PreflightCheckResult, PreflightReport
from .e6_runtime_hook import install_recursive_e6_runtime_support

# POST_E6 may request another immutable E6 revision.  Install the read-model and
# completion projection rules before application services begin making stage
# decisions from accepted history.
install_recursive_e6_runtime_support()

__all__ = [
    "UserSettings",
    "SettingsManager",
    "get_default_settings_manager",
    "PlatformAdapter",
    "DefaultPlatformAdapter",
    "MockPlatformAdapter",
    "ExecutorProfileDefinition",
    "EXECUTION_MODES",
    "DEFAULT_EXECUTION_MODE",
    "get_executor_profile",
    "list_execution_modes",
    "ResolvedSource",
    "resolve_source_identity",
    "E1LaneJob",
    "E1Batch",
    "prepare_e1_batch",
    "E1ResultInbox",
    "ImportedResultSummary",
    "LaneInboxStatus",
    "CampaignProjection",
    "CampaignHistoryService",
    "FullAuditOrchestrator",
    "PreflightCheckResult",
    "PreflightReport",
]

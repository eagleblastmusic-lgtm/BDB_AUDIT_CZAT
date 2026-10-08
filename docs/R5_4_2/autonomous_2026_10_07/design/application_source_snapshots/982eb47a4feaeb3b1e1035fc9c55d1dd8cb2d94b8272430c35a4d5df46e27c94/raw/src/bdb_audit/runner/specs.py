"""RU10 explicit tool-run contracts and capability declarations."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any, Mapping

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError


@dataclass(frozen=True)
class CapabilityProfile:
    profile_id: str = "LOCAL_DISPOSABLE_SUBPROCESS_V1"
    disposable_workspace: bool = True
    shell_disabled: bool = True
    process_tree_termination: bool = True
    environment_sanitized: bool = True
    output_limit_enforced: bool = True
    network_isolation: str = "NOT_ENFORCED"
    host_filesystem_isolation: str = "NOT_ENFORCED"

    def __post_init__(self) -> None:
        if self.network_isolation not in {"ENFORCED", "NOT_ENFORCED"}:
            raise ValidationError("RUNNER_NETWORK_ISOLATION_INVALID")
        if self.host_filesystem_isolation not in {"ENFORCED", "NOT_ENFORCED"}:
            raise ValidationError("RUNNER_FILESYSTEM_ISOLATION_INVALID")

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "disposable_workspace": self.disposable_workspace,
            "shell_disabled": self.shell_disabled,
            "process_tree_termination": self.process_tree_termination,
            "environment_sanitized": self.environment_sanitized,
            "output_limit_enforced": self.output_limit_enforced,
            "network_isolation": self.network_isolation,
            "host_filesystem_isolation": self.host_filesystem_isolation,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_bytes(self.as_dict())).hexdigest()


@dataclass(frozen=True)
class ToolRunSpec:
    run_id: str
    source_root: str
    evidence_dir: str
    argv: tuple[str, ...]
    timeout_seconds: int = 60
    max_output_bytes: int = 4 * 1024 * 1024
    environment: Mapping[str, str] = field(default_factory=dict)
    require_network_isolation: bool = False
    require_host_filesystem_isolation: bool = False
    working_subdir: str = "."

    def __post_init__(self) -> None:
        if not self.run_id or not self.argv:
            raise ValidationError("TOOL_RUN_SPEC_INCOMPLETE")
        if any(type(arg) is not str or not arg or "\x00" in arg for arg in self.argv):
            raise ValidationError("TOOL_RUN_ARGV_INVALID")
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 3600:
            raise ValidationError("TOOL_RUN_TIMEOUT_INVALID")
        if type(self.max_output_bytes) is not int or not 1024 <= self.max_output_bytes <= 64 * 1024 * 1024:
            raise ValidationError("TOOL_RUN_OUTPUT_LIMIT_INVALID")
        if Path(self.working_subdir).is_absolute() or ".." in Path(self.working_subdir).parts:
            raise ValidationError("TOOL_RUN_WORKDIR_ESCAPE")
        for key, value in self.environment.items():
            if type(key) is not str or type(value) is not str or not key:
                raise ValidationError("TOOL_RUN_ENV_INVALID")

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source_root": str(Path(self.source_root).resolve()),
            "evidence_dir": str(Path(self.evidence_dir).resolve()),
            "argv": list(self.argv),
            "timeout_seconds": self.timeout_seconds,
            "max_output_bytes": self.max_output_bytes,
            "environment": dict(sorted(self.environment.items())),
            "require_network_isolation": self.require_network_isolation,
            "require_host_filesystem_isolation": self.require_host_filesystem_isolation,
            "working_subdir": self.working_subdir,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_bytes(self.as_dict())).hexdigest()


@dataclass(frozen=True)
class ToolRunResult:
    run_id: str
    spec_digest: str
    capability_profile_digest: str
    supervisor_status: str
    target_exit_code: int | None
    timed_out: bool
    output_limit_exceeded: bool
    cleanup_status: str
    stdout_sha256: str | None
    stderr_sha256: str | None
    stdout_bytes: int
    stderr_bytes: int
    evidence_files: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    detail: str | None = None

    def __post_init__(self) -> None:
        allowed = {"SUCCESS", "TARGET_NONZERO", "TIMEOUT", "OUTPUT_LIMIT", "BLOCKED", "EXECUTION_ERROR", "CLEANUP_FAILED"}
        if self.supervisor_status not in allowed:
            raise ValidationError("TOOL_RUN_RESULT_STATUS_INVALID", self.supervisor_status)
        if self.cleanup_status not in {"CLEAN", "FAILED", "NOT_STARTED"}:
            raise ValidationError("TOOL_RUN_CLEANUP_STATUS_INVALID")
        if self.supervisor_status == "SUCCESS" and self.target_exit_code != 0:
            raise ValidationError("TOOL_RUN_FALSE_SUCCESS")

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "spec_digest": self.spec_digest,
            "capability_profile_digest": self.capability_profile_digest,
            "supervisor_status": self.supervisor_status,
            "target_exit_code": self.target_exit_code,
            "timed_out": self.timed_out,
            "output_limit_exceeded": self.output_limit_exceeded,
            "cleanup_status": self.cleanup_status,
            "stdout_sha256": self.stdout_sha256,
            "stderr_sha256": self.stderr_sha256,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "evidence_files": list(self.evidence_files),
            "limitations": list(self.limitations),
            "detail": self.detail,
        }

    @property
    def receipt_digest(self) -> str:
        return hashlib.sha256(canonical_bytes(self.as_dict())).hexdigest()

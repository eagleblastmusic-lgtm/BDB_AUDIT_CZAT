"""RU10 runner permission and path validation."""
from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Mapping

from ..core.errors import ValidationError
from .specs import CapabilityProfile, ToolRunSpec

_SENSITIVE = re.compile(r"(?:TOKEN|SECRET|PASSWORD|CREDENTIAL|API[_-]?KEY|PRIVATE[_-]?KEY)", re.I)
_INHERITED_ENV = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "HOME", "USERPROFILE")


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_run_spec(spec: ToolRunSpec, profile: CapabilityProfile) -> tuple[Path, Path]:
    source = Path(spec.source_root).resolve()
    evidence = Path(spec.evidence_dir).resolve()
    if not source.is_dir():
        raise ValidationError("TOOL_RUN_SOURCE_NOT_FOUND", str(source))
    if evidence == source or _inside(evidence, source):
        raise ValidationError("TOOL_RUN_EVIDENCE_INSIDE_TARGET")
    if spec.require_network_isolation and profile.network_isolation != "ENFORCED":
        raise ValidationError("NETWORK_ISOLATION_UNAVAILABLE")
    if not all((profile.disposable_workspace, profile.shell_disabled, profile.process_tree_termination, profile.environment_sanitized, profile.output_limit_enforced)):
        raise ValidationError("RUNNER_REQUIRED_CONTROL_UNAVAILABLE")
    for root, dirs, files in os.walk(source):
        for name in [*dirs, *files]:
            if (Path(root) / name).is_symlink():
                raise ValidationError("TOOL_RUN_SOURCE_SYMLINK_UNSUPPORTED", str(Path(root) / name))
    for key in spec.environment:
        if _SENSITIVE.search(key):
            raise ValidationError("TOOL_RUN_SECRET_ENV_FORBIDDEN", key)
    return source, evidence


def sanitized_environment(extra: Mapping[str, str]) -> dict[str, str]:
    env = {key: os.environ[key] for key in _INHERITED_ENV if key in os.environ}
    env.update(extra)
    env["BDB_TOOL_RUNNER"] = "1"
    return env


__all__ = ["validate_run_spec", "sanitized_environment"]

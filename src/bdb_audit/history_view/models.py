"""RU17 historical trend and share-bundle contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..core.errors import ValidationError


@dataclass(frozen=True)
class HistoricalAuditPoint:
    audit_id: str
    source_identity: Mapping[str, Any]
    scope_identity: str
    policy_identity: str
    finding_count: int
    denominator: int
    unknown_count: int = 0

    def __post_init__(self) -> None:
        if not self.audit_id or not self.source_identity or not self.scope_identity or not self.policy_identity:
            raise ValidationError("HISTORICAL_POINT_IDENTITY_REQUIRED")
        if type(self.finding_count) is not int or self.finding_count < 0:
            raise ValidationError("HISTORICAL_FINDING_COUNT_INVALID")
        if type(self.denominator) is not int or self.denominator <= 0:
            raise ValidationError("HISTORICAL_DENOMINATOR_REQUIRED")
        if type(self.unknown_count) is not int or self.unknown_count < 0:
            raise ValidationError("HISTORICAL_UNKNOWN_COUNT_INVALID")

    def as_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "source_identity": dict(self.source_identity),
            "scope_identity": self.scope_identity,
            "policy_identity": self.policy_identity,
            "finding_count": self.finding_count,
            "denominator": self.denominator,
            "unknown_count": self.unknown_count,
        }


@dataclass(frozen=True)
class PrivacyPolicy:
    mode: str = "REDACTED"
    excluded_path_prefixes: Sequence[str] = field(default_factory=tuple)
    max_file_bytes: int = 16 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.mode not in {"PUBLIC", "REDACTED"}:
            raise ValidationError("SHARE_PRIVACY_MODE_INVALID")
        if type(self.max_file_bytes) is not int or self.max_file_bytes <= 0:
            raise ValidationError("SHARE_MAX_FILE_BYTES_INVALID")
        object.__setattr__(self, "excluded_path_prefixes", tuple(sorted(set(str(item).replace("\\", "/").strip("/") for item in self.excluded_path_prefixes if str(item).strip("/")))))

    def as_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "excluded_path_prefixes": list(self.excluded_path_prefixes), "max_file_bytes": self.max_file_bytes}


__all__ = ["HistoricalAuditPoint", "PrivacyPolicy"]

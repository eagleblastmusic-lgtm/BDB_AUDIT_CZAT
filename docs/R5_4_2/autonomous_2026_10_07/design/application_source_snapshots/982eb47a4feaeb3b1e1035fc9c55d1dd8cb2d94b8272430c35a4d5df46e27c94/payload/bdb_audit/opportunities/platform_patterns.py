"""RU15 platform-pattern references. Patterns are hypotheses, never target facts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.errors import ValidationError


@dataclass(frozen=True)
class PlatformPattern:
    pattern_id: str
    title: str
    applicability_basis: str
    source_ref: str

    def __post_init__(self) -> None:
        if not self.pattern_id or not self.title or not self.source_ref:
            raise ValidationError("PLATFORM_PATTERN_INVALID")
        if self.applicability_basis not in {"REFERENCE_ONLY", "TARGET_EVIDENCED"}:
            raise ValidationError("PLATFORM_PATTERN_BASIS_INVALID")

    def as_dict(self) -> dict[str, Any]:
        return {"pattern_id": self.pattern_id, "title": self.title, "applicability_basis": self.applicability_basis, "source_ref": self.source_ref, "authority": "REFERENCE_NOT_TARGET_FACT"}


__all__ = ["PlatformPattern"]

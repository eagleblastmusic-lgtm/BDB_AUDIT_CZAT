"""Immutable-style per-file import diagnostics for RU03/D19."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass(frozen=True)
class ImportItemResult:
    input_name: str
    status: str  # ACCEPTED | DUPLICATE | REJECTED
    reason_code: str | None = None
    raw_digest: str | None = None
    lane_slot: str | None = None
    expected_identity: dict[str, Any] = field(default_factory=dict)
    actual_identity: dict[str, Any] = field(default_factory=dict)
    next_action: str | None = None


@dataclass(frozen=True)
class ImportReport:
    campaign_id: str
    stage_id: str
    items: tuple[ImportItemResult, ...]

    @classmethod
    def build(cls, campaign_id: str, stage_id: str, items: Sequence[ImportItemResult]) -> "ImportReport":
        return cls(campaign_id, stage_id, tuple(items))

    @property
    def accepted_count(self) -> int:
        return sum(i.status == "ACCEPTED" for i in self.items)

    @property
    def rejected_count(self) -> int:
        return sum(i.status == "REJECTED" for i in self.items)

    @property
    def duplicate_count(self) -> int:
        return sum(i.status == "DUPLICATE" for i in self.items)

    def as_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "stage_id": self.stage_id,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "duplicate_count": self.duplicate_count,
            "items": [
                {
                    "input_name": i.input_name,
                    "status": i.status,
                    "reason_code": i.reason_code,
                    "raw_digest": i.raw_digest,
                    "lane_slot": i.lane_slot,
                    "expected_identity": dict(i.expected_identity),
                    "actual_identity": dict(i.actual_identity),
                    "next_action": i.next_action,
                }
                for i in self.items
            ],
        }


__all__ = ["ImportItemResult", "ImportReport"]

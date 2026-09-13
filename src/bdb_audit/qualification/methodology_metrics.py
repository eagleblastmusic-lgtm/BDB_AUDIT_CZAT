"""Methodology Qualification Metrics with Explicit Denominator (R5.3 §111 / B08).

Metrics must have an explicit denominator and scope. Never claim '99% audit completeness'
or global unmeasured coverage. Evaluated cases must derive from actual executions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.errors import ValidationError


@dataclass(frozen=True)
class MethodologyMetrics:
    total_targets: int
    evaluated_targets: int
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0
    unsupported_cases: int = 0
    unknown_cases: int = 0
    anti_bypass_total: int = 0
    anti_bypass_passed: int = 0
    denominator: int = 0
    scope_details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.total_targets < 0 or self.evaluated_targets < 0:
            raise ValidationError("NEGATIVE_TARGETS_FORBIDDEN", "Target counts cannot be negative")
        if self.evaluated_targets > self.total_targets:
            raise ValidationError("EVALUATED_EXCEEDS_TOTAL", "Evaluated targets cannot exceed total targets")
        if self.denominator < 0:
            raise ValidationError("NEGATIVE_DENOMINATOR_FORBIDDEN", "Denominator cannot be negative")
        if self.anti_bypass_passed > self.anti_bypass_total:
            raise ValidationError("ANTI_BYPASS_COUNT_INVALID", "Passed anti-bypass checks cannot exceed total")

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return round(self.true_positives / denom, 4) if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return round(self.true_positives / denom, 4) if denom > 0 else 0.0

    @property
    def anti_bypass_rate(self) -> float:
        return (
            round(self.anti_bypass_passed / self.anti_bypass_total, 4)
            if self.anti_bypass_total > 0
            else 0.0
        )

    @property
    def is_methodology_qualified(self) -> bool:
        """Strict qualification predicate.

        Returns True ONLY if:
        1. Explicit positive denominator.
        2. All targets evaluated (no unexecuted targets).
        3. Zero false negatives on mandatory defect controls.
        4. Zero false positives on clean controls.
        5. 100% anti-bypass pass rate (all negative controls passed).
        6. Zero unknown cases on mandatory properties.
        """
        if self.denominator <= 0:
            return False
        if self.evaluated_targets != self.total_targets or self.total_targets == 0:
            return False
        if self.false_negatives > 0:
            return False
        if self.false_positives > 0:
            return False
        if self.anti_bypass_total == 0 or self.anti_bypass_passed != self.anti_bypass_total:
            return False
        if self.unknown_cases > 0:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_targets": self.total_targets,
            "evaluated_targets": self.evaluated_targets,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "false_negatives": self.false_negatives,
            "unsupported_cases": self.unsupported_cases,
            "unknown_cases": self.unknown_cases,
            "anti_bypass_total": self.anti_bypass_total,
            "anti_bypass_passed": self.anti_bypass_passed,
            "denominator": self.denominator,
            "precision": self.precision,
            "recall": self.recall,
            "anti_bypass_rate": self.anti_bypass_rate,
            "is_methodology_qualified": self.is_methodology_qualified,
            "scope_details": self.scope_details,
        }

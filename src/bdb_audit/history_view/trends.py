"""RU17 scope-normalized historical trend projections."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

from ..core.errors import ValidationError
from .models import HistoricalAuditPoint


def _rate_basis_points(findings: int, denominator: int) -> int:
    # Integer basis points avoid floating-point canonicalization and preserve the
    # denominator explicitly. 10000 == 100%.
    return findings * 10000 // denominator


def build_trends(points: Sequence[HistoricalAuditPoint]) -> dict[str, Any]:
    if not points:
        raise ValidationError("HISTORICAL_POINTS_REQUIRED")
    grouped: dict[tuple[str, str], list[HistoricalAuditPoint]] = defaultdict(list)
    for point in points:
        grouped[(point.scope_identity, point.policy_identity)].append(point)

    series: list[dict[str, Any]] = []
    for (scope, policy), members in sorted(grouped.items()):
        rows = []
        for point in sorted(members, key=lambda item: item.audit_id):
            rows.append({
                **point.as_dict(),
                "finding_rate_basis_points": _rate_basis_points(point.finding_count, point.denominator),
                "unknown_rate_basis_points": _rate_basis_points(point.unknown_count, point.denominator),
            })
        comparisons: list[dict[str, Any]] = []
        for previous, current in zip(rows, rows[1:]):
            comparisons.append({
                "from_audit_id": previous["audit_id"],
                "to_audit_id": current["audit_id"],
                "finding_rate_delta_basis_points": current["finding_rate_basis_points"] - previous["finding_rate_basis_points"],
                "raw_count_delta": current["finding_count"] - previous["finding_count"],
                "raw_count_delta_is_not_primary_metric": True,
            })
        series.append({
            "scope_identity": scope,
            "policy_identity": policy,
            "points": rows,
            "comparisons": comparisons,
            "normalization": "FINDINGS_PER_EXPLICIT_DENOMINATOR_BASIS_POINTS",
        })
    return {
        "schema_version": "RU17-HISTORICAL-TRENDS-1",
        "status": "PASS",
        "series": series,
        "series_count": len(series),
        "raw_finding_counts_never_compared_without_denominator": True,
    }


def points_from_dict(items: Sequence[dict[str, Any]]) -> tuple[HistoricalAuditPoint, ...]:
    return tuple(HistoricalAuditPoint(
        audit_id=str(item.get("audit_id", "")),
        source_identity=dict(item.get("source_identity", {})),
        scope_identity=str(item.get("scope_identity", "")),
        policy_identity=str(item.get("policy_identity", "")),
        finding_count=int(item.get("finding_count", -1)),
        denominator=int(item.get("denominator", 0)),
        unknown_count=int(item.get("unknown_count", 0)),
    ) for item in items)


__all__ = ["build_trends", "points_from_dict"]

"""RU14 risk-to-obligation lane planner and fail-closed DAG scheduler."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from ..core.errors import ValidationError
from .models import ExposureManifest, LanePlan, LaneProposal, RiskObligation, StrategyProfile

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def topological_lane_order(lanes: Sequence[LaneProposal]) -> tuple[str, ...]:
    by_id = {item.lane_id: item for item in lanes}
    incoming: dict[str, set[str]] = {lane_id: set() for lane_id in by_id}
    outgoing: dict[str, set[str]] = defaultdict(set)
    for lane in lanes:
        for dependency in lane.depends_on:
            if dependency == lane.lane_id:
                raise ValidationError("LANE_DEPENDENCY_SELF_CYCLE", lane.lane_id)
            if dependency not in by_id:
                raise ValidationError("LANE_DEPENDENCY_DANGLING", dependency)
            incoming[lane.lane_id].add(dependency)
            outgoing[dependency].add(lane.lane_id)
    ready = sorted(lane_id for lane_id, deps in incoming.items() if not deps)
    order: list[str] = []
    while ready:
        lane_id = ready.pop(0)
        order.append(lane_id)
        for dependent in sorted(outgoing.get(lane_id, ())):
            incoming[dependent].discard(lane_id)
            if not incoming[dependent] and dependent not in order and dependent not in ready:
                ready.append(dependent)
        ready.sort()
    if len(order) != len(by_id):
        raise ValidationError("LANE_DEPENDENCY_CYCLE")
    return tuple(order)


def plan_lanes(
    profile: StrategyProfile,
    risks: Sequence[RiskObligation],
    exposure: ExposureManifest,
    *,
    reserve_released: bool = False,
) -> LanePlan:
    if not risks:
        raise ValidationError("RISK_MAP_EMPTY")
    usable = profile.total_budget_units if reserve_released else profile.total_budget_units - profile.reserve_budget_units
    selected: list[LaneProposal] = []
    spent = 0
    ordered = sorted(risks, key=lambda item: (_SEVERITY_ORDER[item.severity], item.risk_id))
    for risk in ordered:
        method = risk.method_candidates[0]
        # Cost is deliberately transparent and integer-only: severity weight +
        # obligation breadth. It is a planning heuristic, not evidence authority.
        base = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2}[risk.severity]
        cost = base + len(risk.obligation_keys)
        if spent + cost > usable:
            continue
        evaluator = exposure.evaluator_profile
        if risk.required_independent and not profile.independence_required:
            raise ValidationError("LANE_INDEPENDENCE_REQUIREMENT_UNSATISFIED", risk.risk_id)
        lane = LaneProposal(
            lane_id=f"lane_{risk.risk_id}",
            risk_id=risk.risk_id,
            method=method,
            obligation_keys=risk.obligation_keys,
            cost_units=cost,
            evaluator_profile=evaluator,
        )
        selected.append(lane)
        spent += cost
    if not selected:
        raise ValidationError("LANE_PLAN_BUDGET_EXHAUSTED")
    limitations = []
    if len(selected) < len(risks):
        limitations.append("BUDGET_LEFT_RISKS_UNPLANNED")
    if not reserve_released and profile.reserve_budget_units:
        limitations.append("RESERVE_BUDGET_EMBARGO_ACTIVE")
    plan = LanePlan(
        plan_id=f"plan_{profile.profile_id}",
        strategy_profile=profile,
        lanes=tuple(selected),
        reserve_released=reserve_released,
        exposure_manifest=exposure,
        limitations=tuple(limitations),
    )
    topological_lane_order(plan.lanes)
    return plan


def validate_lane_plan(plan: LanePlan) -> dict[str, Any]:
    order = topological_lane_order(plan.lanes)
    spent = sum(item.cost_units for item in plan.lanes)
    available = plan.strategy_profile.total_budget_units
    if not plan.reserve_released:
        available -= plan.strategy_profile.reserve_budget_units
    if spent > available:
        raise ValidationError("LANE_PLAN_BUDGET_OVERRUN")
    prohibited = set(plan.exposure_manifest.prohibited_artifact_ids)
    exposed = set(plan.exposure_manifest.exposed_artifact_ids)
    if exposed & prohibited:
        raise ValidationError("LANE_PLAN_EXPOSURE_CONFLICT")
    return {
        "status": "PASS",
        "plan_digest": plan.as_dict()["plan_digest"],
        "topological_order": list(order),
        "spent_budget_units": spent,
        "available_budget_units": available,
        "reserve_budget_units": plan.strategy_profile.reserve_budget_units,
        "reserve_released": plan.reserve_released,
    }


def compare_yield_efficiency(
    *, candidate_unique_root_causes: int, candidate_cost_units: int,
    baseline_unique_root_causes: int, baseline_cost_units: int,
) -> dict[str, Any]:
    values = (candidate_unique_root_causes, candidate_cost_units, baseline_unique_root_causes, baseline_cost_units)
    if any(type(item) is not int or item < 0 for item in values) or candidate_cost_units == 0 or baseline_cost_units == 0:
        raise ValidationError("YIELD_COMPARISON_INVALID")
    left = candidate_unique_root_causes * baseline_cost_units
    right = baseline_unique_root_causes * candidate_cost_units
    outcome = "BETTER" if left > right else "EQUAL" if left == right else "WORSE"
    return {
        "status": "PASS",
        "outcome": outcome,
        "candidate_unique_root_causes": candidate_unique_root_causes,
        "candidate_cost_units": candidate_cost_units,
        "baseline_unique_root_causes": baseline_unique_root_causes,
        "baseline_cost_units": baseline_cost_units,
        "comparison_cross_product": {"candidate": left, "baseline": right},
    }


def risk_map_from_dict(items: Sequence[Mapping[str, Any]]) -> tuple[RiskObligation, ...]:
    return tuple(RiskObligation(
        risk_id=str(item.get("risk_id", "")),
        severity=str(item.get("severity", "")),
        obligation_keys=tuple(item.get("obligation_keys", ())),
        method_candidates=tuple(item.get("method_candidates", ())),
        required_independent=bool(item.get("required_independent", False)),
    ) for item in items)


__all__ = ["topological_lane_order", "plan_lanes", "validate_lane_plan", "compare_yield_efficiency", "risk_map_from_dict"]

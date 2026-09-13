from __future__ import annotations

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.strategy import ExposureManifest, LanePlan, LaneProposal, RiskObligation, StrategyProfile
from bdb_audit.strategy.planner import compare_yield_efficiency, plan_lanes, topological_lane_order, validate_lane_plan


def _profile() -> StrategyProfile:
    return StrategyProfile("adaptive-v1", total_budget_units=20, reserve_budget_units=5)


def _exposure() -> ExposureManifest:
    return ExposureManifest("independent-evaluator")


def test_ru14_reserve_budget_is_unavailable_before_release() -> None:
    risks = (
        RiskObligation("critical", "CRITICAL", ("O1",), ("STATIC",), True),
        RiskObligation("high", "HIGH", ("O2", "O3"), ("TEST",)),
        RiskObligation("medium", "MEDIUM", ("O4", "O5", "O6"), ("REPLAY",)),
    )
    plan = plan_lanes(_profile(), risks, _exposure(), reserve_released=False)
    spent = sum(item.cost_units for item in plan.lanes)
    assert spent <= 15
    assert "RESERVE_BUDGET_EMBARGO_ACTIVE" in plan.limitations
    released = plan_lanes(_profile(), risks, _exposure(), reserve_released=True)
    assert sum(item.cost_units for item in released.lanes) >= spent


def test_ru14_scheduler_rejects_cycles_and_dangling_dependencies() -> None:
    a = LaneProposal("a", "r1", "STATIC", ("O1",), 2, depends_on=("b",))
    b = LaneProposal("b", "r2", "TEST", ("O2",), 2, depends_on=("a",))
    with pytest.raises(ValidationError, match="LANE_DEPENDENCY_CYCLE"):
        topological_lane_order((a, b))
    dangling = LaneProposal("a", "r1", "STATIC", ("O1",), 2, depends_on=("missing",))
    with pytest.raises(ValidationError, match="LANE_DEPENDENCY_DANGLING"):
        topological_lane_order((dangling,))


def test_ru14_plan_is_derived_and_does_not_mutate_authority() -> None:
    risk = RiskObligation("r1", "HIGH", ("O1",), ("STATIC",), True)
    plan = plan_lanes(_profile(), (risk,), _exposure())
    assert plan.authority == "DERIVED_PROPOSAL_ONLY"
    verified = validate_lane_plan(plan)
    assert verified["status"] == "PASS"
    assert plan.as_dict()["artifact_class"] == "DERIVED_LANE_PLAN"


def test_ru14_exposure_policy_conflict_fails_closed() -> None:
    with pytest.raises(ValidationError, match="EXPOSURE_POLICY_CONFLICT"):
        ExposureManifest("eval", exposed_artifact_ids=("oracle",), prohibited_artifact_ids=("oracle",))


def test_ru14_yield_efficiency_is_integer_cross_product_not_float_claim() -> None:
    result = compare_yield_efficiency(candidate_unique_root_causes=4, candidate_cost_units=10, baseline_unique_root_causes=2, baseline_cost_units=10)
    assert result["outcome"] == "BETTER"
    assert result["comparison_cross_product"] == {"candidate": 40, "baseline": 20}

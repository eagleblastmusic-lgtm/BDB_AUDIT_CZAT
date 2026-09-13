"""RU14 adaptive strategy and lane planning contracts (derived-only)."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError


def _digest(body: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(body))).hexdigest()


@dataclass(frozen=True)
class StrategyProfile:
    profile_id: str
    total_budget_units: int
    reserve_budget_units: int
    max_parallel_lanes: int = 4
    independence_required: bool = True

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValidationError("STRATEGY_PROFILE_ID_REQUIRED")
        if type(self.total_budget_units) is not int or self.total_budget_units <= 0:
            raise ValidationError("STRATEGY_BUDGET_INVALID")
        if type(self.reserve_budget_units) is not int or not 0 <= self.reserve_budget_units < self.total_budget_units:
            raise ValidationError("STRATEGY_RESERVE_INVALID")
        if type(self.max_parallel_lanes) is not int or self.max_parallel_lanes < 1:
            raise ValidationError("STRATEGY_PARALLELISM_INVALID")

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_class": "DERIVED_STRATEGY_PROFILE",
            "profile_id": self.profile_id,
            "total_budget_units": self.total_budget_units,
            "reserve_budget_units": self.reserve_budget_units,
            "max_parallel_lanes": self.max_parallel_lanes,
            "independence_required": self.independence_required,
        }


@dataclass(frozen=True)
class RiskObligation:
    risk_id: str
    severity: str
    obligation_keys: Sequence[str]
    method_candidates: Sequence[str]
    required_independent: bool = False

    def __post_init__(self) -> None:
        if not self.risk_id or self.severity not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            raise ValidationError("RISK_OBLIGATION_INVALID")
        if not self.obligation_keys or not self.method_candidates:
            raise ValidationError("RISK_OBLIGATION_MAPPING_REQUIRED")
        object.__setattr__(self, "obligation_keys", tuple(sorted(set(self.obligation_keys))))
        object.__setattr__(self, "method_candidates", tuple(sorted(set(self.method_candidates))))

    def as_dict(self) -> dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "severity": self.severity,
            "obligation_keys": list(self.obligation_keys),
            "method_candidates": list(self.method_candidates),
            "required_independent": self.required_independent,
        }


@dataclass(frozen=True)
class ExposureManifest:
    evaluator_profile: str
    exposed_artifact_ids: Sequence[str] = ()
    prohibited_artifact_ids: Sequence[str] = ()

    def __post_init__(self) -> None:
        if not self.evaluator_profile:
            raise ValidationError("EXPOSURE_PROFILE_REQUIRED")
        exposed = tuple(sorted(set(self.exposed_artifact_ids)))
        prohibited = tuple(sorted(set(self.prohibited_artifact_ids)))
        if set(exposed) & set(prohibited):
            raise ValidationError("EXPOSURE_POLICY_CONFLICT")
        object.__setattr__(self, "exposed_artifact_ids", exposed)
        object.__setattr__(self, "prohibited_artifact_ids", prohibited)

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluator_profile": self.evaluator_profile,
            "exposed_artifact_ids": list(self.exposed_artifact_ids),
            "prohibited_artifact_ids": list(self.prohibited_artifact_ids),
        }


@dataclass(frozen=True)
class LaneProposal:
    lane_id: str
    risk_id: str
    method: str
    obligation_keys: Sequence[str]
    cost_units: int
    depends_on: Sequence[str] = ()
    evaluator_profile: str = "DEFAULT"
    unique_root_cause_yield: int = 0

    def __post_init__(self) -> None:
        if not self.lane_id or not self.risk_id or not self.method:
            raise ValidationError("LANE_PROPOSAL_IDENTITY_REQUIRED")
        if type(self.cost_units) is not int or self.cost_units <= 0:
            raise ValidationError("LANE_COST_INVALID")
        if type(self.unique_root_cause_yield) is not int or self.unique_root_cause_yield < 0:
            raise ValidationError("LANE_YIELD_INVALID")
        object.__setattr__(self, "obligation_keys", tuple(sorted(set(self.obligation_keys))))
        object.__setattr__(self, "depends_on", tuple(sorted(set(self.depends_on))))

    def as_dict(self) -> dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "risk_id": self.risk_id,
            "method": self.method,
            "obligation_keys": list(self.obligation_keys),
            "cost_units": self.cost_units,
            "depends_on": list(self.depends_on),
            "evaluator_profile": self.evaluator_profile,
            "unique_root_cause_yield": self.unique_root_cause_yield,
        }


@dataclass(frozen=True)
class LanePlan:
    plan_id: str
    strategy_profile: StrategyProfile
    lanes: Sequence[LaneProposal]
    reserve_released: bool
    exposure_manifest: ExposureManifest
    authority: str = "DERIVED_PROPOSAL_ONLY"
    limitations: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        lanes = tuple(sorted(self.lanes, key=lambda item: item.lane_id))
        if not self.plan_id or not lanes:
            raise ValidationError("LANE_PLAN_EMPTY")
        ids = [item.lane_id for item in lanes]
        if len(ids) != len(set(ids)):
            raise ValidationError("LANE_PLAN_DUPLICATE_ID")
        if self.authority != "DERIVED_PROPOSAL_ONLY":
            raise ValidationError("LANE_PLAN_AUTHORITY_INVALID")
        object.__setattr__(self, "lanes", lanes)
        object.__setattr__(self, "limitations", tuple(sorted(set(self.limitations))))

    def as_dict(self) -> dict[str, Any]:
        body = {
            "artifact_class": "DERIVED_LANE_PLAN",
            "authority": self.authority,
            "plan_id": self.plan_id,
            "strategy_profile": self.strategy_profile.as_dict(),
            "lanes": [item.as_dict() for item in self.lanes],
            "reserve_released": self.reserve_released,
            "exposure_manifest": self.exposure_manifest.as_dict(),
            "limitations": list(self.limitations),
        }
        body["plan_digest"] = _digest(body)
        return body


__all__ = ["StrategyProfile", "RiskObligation", "ExposureManifest", "LaneProposal", "LanePlan"]

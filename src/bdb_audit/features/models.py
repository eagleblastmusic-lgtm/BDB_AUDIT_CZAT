"""RU11 derived feature/behavior verification models.

These objects are deliberately DERIVED. The current R5.3 artifact registry does
not define feature_* authority kinds, so this layer must not manufacture
accepted-history authority under ad-hoc kind names.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError

FEATURE_INTERFACES = {"CLI", "API", "BROWSER", "WORKER", "DATABASE", "DESKTOP", "MANUAL"}
BEHAVIOR_KINDS = {"POSITIVE", "NEGATIVE", "RECOVERY"}
ORACLE_STATUSES = {"QUALIFIED", "UNQUALIFIED", "BLOCKED"}
ORACLE_INDEPENDENCE = {"INDEPENDENT", "SHARED_DEPENDENCY", "UNKNOWN"}
FEATURE_STATUSES = {"PASS", "FAIL", "BLOCKED", "INSUFFICIENT", "UNSUPPORTED", "NOT_APPLICABLE", "NOT_RUN"}
FRESHNESS = {"ACTIVE", "STALE"}


def _digest(body: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(body))).hexdigest()


def _strings(values: Sequence[str]) -> tuple[str, ...]:
    result = tuple(sorted(str(v) for v in values))
    if len(result) != len(set(result)):
        raise ValidationError("FEATURE_DUPLICATE_VALUE")
    return result


@dataclass(frozen=True)
class FeatureRevision:
    feature_id: str
    name: str
    interface: str
    source_anchor: Mapping[str, Any]
    source_manifest_digest: str
    criticality: str = "MEDIUM"
    roles: Sequence[str] = ()
    environment_classes: Sequence[str] = ()
    reconciliation_status: str = "RECONCILED"

    def __post_init__(self) -> None:
        if not self.feature_id or not self.name or self.interface not in FEATURE_INTERFACES:
            raise ValidationError("FEATURE_REVISION_INVALID")
        if len(self.source_manifest_digest) != 64:
            raise ValidationError("FEATURE_SOURCE_DIGEST_INVALID")
        if self.criticality not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            raise ValidationError("FEATURE_CRITICALITY_INVALID")
        if self.reconciliation_status not in {"PROVISIONAL", "RECONCILED"}:
            raise ValidationError("FEATURE_RECONCILIATION_INVALID")
        object.__setattr__(self, "roles", _strings(self.roles))
        object.__setattr__(self, "environment_classes", _strings(self.environment_classes))

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_class": "DERIVED_FEATURE_REVISION",
            "feature_id": self.feature_id,
            "name": self.name,
            "interface": self.interface,
            "source_anchor": dict(self.source_anchor),
            "source_manifest_digest": self.source_manifest_digest,
            "criticality": self.criticality,
            "roles": list(self.roles),
            "environment_classes": list(self.environment_classes),
            "reconciliation_status": self.reconciliation_status,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True)
class BehaviorCase:
    case_id: str
    feature_id: str
    behavior_kind: str
    argv: Sequence[str] = ()
    expected_exit_code: int | None = None
    stdout_contains: str | None = None
    stderr_contains: str | None = None
    expected_json_subset: Mapping[str, Any] | None = None
    mock_only: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if not self.case_id or not self.feature_id or self.behavior_kind not in BEHAVIOR_KINDS:
            raise ValidationError("BEHAVIOR_CASE_INVALID")
        if any(type(item) is not str or not item or "\x00" in item for item in self.argv):
            raise ValidationError("BEHAVIOR_ARGV_INVALID")
        if self.expected_exit_code is None and self.stdout_contains is None and self.stderr_contains is None and self.expected_json_subset is None:
            raise ValidationError("BEHAVIOR_PREDICATE_REQUIRED")
        object.__setattr__(self, "argv", tuple(self.argv))

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_class": "DERIVED_BEHAVIOR_CASE",
            "case_id": self.case_id,
            "feature_id": self.feature_id,
            "behavior_kind": self.behavior_kind,
            "argv": list(self.argv),
            "expected_exit_code": self.expected_exit_code,
            "stdout_contains": self.stdout_contains,
            "stderr_contains": self.stderr_contains,
            "expected_json_subset": dict(self.expected_json_subset) if self.expected_json_subset is not None else None,
            "mock_only": self.mock_only,
            "description": self.description,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True)
class OracleAssessment:
    case_id: str
    status: str
    independence: str
    requirement_refs: Sequence[str] = ()
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.status not in ORACLE_STATUSES or self.independence not in ORACLE_INDEPENDENCE:
            raise ValidationError("ORACLE_ASSESSMENT_INVALID")
        refs = _strings(self.requirement_refs)
        object.__setattr__(self, "requirement_refs", refs)
        if self.status == "QUALIFIED" and (self.independence != "INDEPENDENT" or not refs):
            raise ValidationError("ORACLE_FALSE_QUALIFICATION")

    @property
    def can_qualify(self) -> bool:
        return self.status == "QUALIFIED" and self.independence == "INDEPENDENT" and bool(self.requirement_refs)

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_class": "DERIVED_ORACLE_ASSESSMENT",
            "case_id": self.case_id,
            "status": self.status,
            "independence": self.independence,
            "requirement_refs": list(self.requirement_refs),
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class TestabilityAssessment:
    feature_id: str
    status: str
    adapter: str | None = None
    reason_codes: Sequence[str] = ()

    def __post_init__(self) -> None:
        if self.status not in {"TESTABLE", "BLOCKED", "UNSUPPORTED"}:
            raise ValidationError("TESTABILITY_STATUS_INVALID")
        object.__setattr__(self, "reason_codes", _strings(self.reason_codes))
        if self.status == "TESTABLE" and not self.adapter:
            raise ValidationError("TESTABILITY_ADAPTER_REQUIRED")

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_class": "DERIVED_TESTABILITY_ASSESSMENT",
            "feature_id": self.feature_id,
            "status": self.status,
            "adapter": self.adapter,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class VerificationPlan:
    feature: FeatureRevision
    cases: Sequence[BehaviorCase]
    oracles: Sequence[OracleAssessment]
    testability: TestabilityAssessment
    source_manifest_digest: str
    environment_manifest_digest: str

    def __post_init__(self) -> None:
        cases = tuple(sorted(self.cases, key=lambda item: item.case_id))
        oracles = tuple(sorted(self.oracles, key=lambda item: item.case_id))
        if not cases:
            raise ValidationError("VERIFICATION_PLAN_ZERO_CASES")
        if any(case.feature_id != self.feature.feature_id for case in cases):
            raise ValidationError("VERIFICATION_PLAN_FEATURE_MISMATCH")
        if {case.case_id for case in cases} != {item.case_id for item in oracles}:
            raise ValidationError("VERIFICATION_PLAN_ORACLE_CLOSURE_MISSING")
        if len({case.case_id for case in cases}) != len(cases):
            raise ValidationError("VERIFICATION_PLAN_DUPLICATE_CASE")
        if self.source_manifest_digest != self.feature.source_manifest_digest:
            raise ValidationError("VERIFICATION_PLAN_SOURCE_MISMATCH")
        if len(self.environment_manifest_digest) != 64:
            raise ValidationError("VERIFICATION_PLAN_ENVIRONMENT_INVALID")
        object.__setattr__(self, "cases", cases)
        object.__setattr__(self, "oracles", oracles)

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_class": "DERIVED_VERIFICATION_PLAN",
            "feature": self.feature.as_dict(),
            "cases": [item.as_dict() for item in self.cases],
            "oracles": [item.as_dict() for item in self.oracles],
            "testability": self.testability.as_dict(),
            "source_manifest_digest": self.source_manifest_digest,
            "environment_manifest_digest": self.environment_manifest_digest,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True)
class BehaviorAssessment:
    case_id: str
    feature_id: str
    status: str
    freshness: str
    source_manifest_digest: str
    environment_manifest_digest: str
    run_receipt_digest: str | None = None
    reason_codes: Sequence[str] = ()
    predicate_results: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in FEATURE_STATUSES or self.freshness not in FRESHNESS:
            raise ValidationError("BEHAVIOR_ASSESSMENT_INVALID")
        if self.status == "PASS" and (self.freshness != "ACTIVE" or not self.run_receipt_digest):
            raise ValidationError("BEHAVIOR_FALSE_PASS")
        object.__setattr__(self, "reason_codes", _strings(self.reason_codes))

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_class": "DERIVED_BEHAVIOR_ASSESSMENT",
            "case_id": self.case_id,
            "feature_id": self.feature_id,
            "status": self.status,
            "freshness": self.freshness,
            "source_manifest_digest": self.source_manifest_digest,
            "environment_manifest_digest": self.environment_manifest_digest,
            "run_receipt_digest": self.run_receipt_digest,
            "reason_codes": list(self.reason_codes),
            "predicate_results": dict(sorted(self.predicate_results.items())),
        }


__all__ = [
    "FeatureRevision", "BehaviorCase", "OracleAssessment", "TestabilityAssessment",
    "VerificationPlan", "BehaviorAssessment", "FEATURE_STATUSES",
]

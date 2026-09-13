"""RU11 strict serialization for derived verification artifacts."""
from __future__ import annotations

from typing import Any, Mapping

from ..core.errors import ValidationError
from .models import (
    BehaviorAssessment,
    BehaviorCase,
    FeatureRevision,
    OracleAssessment,
    TestabilityAssessment,
    VerificationPlan,
)


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(code)
    return value


def feature_from_dict(value: Mapping[str, Any]) -> FeatureRevision:
    return FeatureRevision(
        feature_id=str(value.get("feature_id", "")),
        name=str(value.get("name", "")),
        interface=str(value.get("interface", "")),
        source_anchor=dict(_mapping(value.get("source_anchor"), "FEATURE_SOURCE_ANCHOR_REQUIRED")),
        source_manifest_digest=str(value.get("source_manifest_digest", "")),
        criticality=str(value.get("criticality", "MEDIUM")),
        roles=tuple(value.get("roles", ())),
        environment_classes=tuple(value.get("environment_classes", ())),
        reconciliation_status=str(value.get("reconciliation_status", "RECONCILED")),
    )


def case_from_dict(value: Mapping[str, Any]) -> BehaviorCase:
    subset = value.get("expected_json_subset")
    if subset is not None and not isinstance(subset, dict):
        raise ValidationError("BEHAVIOR_JSON_SUBSET_INVALID")
    return BehaviorCase(
        case_id=str(value.get("case_id", "")),
        feature_id=str(value.get("feature_id", "")),
        behavior_kind=str(value.get("behavior_kind", "")),
        argv=tuple(value.get("argv", ())),
        expected_exit_code=value.get("expected_exit_code"),
        stdout_contains=value.get("stdout_contains"),
        stderr_contains=value.get("stderr_contains"),
        expected_json_subset=subset,
        mock_only=bool(value.get("mock_only", False)),
        description=str(value.get("description", "")),
    )


def oracle_from_dict(value: Mapping[str, Any]) -> OracleAssessment:
    return OracleAssessment(
        case_id=str(value.get("case_id", "")),
        status=str(value.get("status", "UNQUALIFIED")),
        independence=str(value.get("independence", "UNKNOWN")),
        requirement_refs=tuple(value.get("requirement_refs", ())),
        rationale=str(value.get("rationale", "")),
    )


def testability_from_dict(value: Mapping[str, Any]) -> TestabilityAssessment:
    adapter = value.get("adapter")
    return TestabilityAssessment(
        feature_id=str(value.get("feature_id", "")),
        status=str(value.get("status", "UNSUPPORTED")),
        adapter=str(adapter) if adapter is not None else None,
        reason_codes=tuple(value.get("reason_codes", ())),
    )


def plan_from_dict(value: Mapping[str, Any]) -> VerificationPlan:
    return VerificationPlan(
        feature=feature_from_dict(_mapping(value.get("feature"), "VERIFICATION_PLAN_FEATURE_REQUIRED")),
        cases=tuple(case_from_dict(_mapping(item, "BEHAVIOR_CASE_INVALID")) for item in value.get("cases", ())),
        oracles=tuple(oracle_from_dict(_mapping(item, "ORACLE_ASSESSMENT_INVALID")) for item in value.get("oracles", ())),
        testability=testability_from_dict(_mapping(value.get("testability"), "TESTABILITY_ASSESSMENT_REQUIRED")),
        source_manifest_digest=str(value.get("source_manifest_digest", "")),
        environment_manifest_digest=str(value.get("environment_manifest_digest", "")),
    )


def assessment_from_dict(value: Mapping[str, Any]) -> BehaviorAssessment:
    predicates = value.get("predicate_results", {})
    if not isinstance(predicates, dict):
        raise ValidationError("BEHAVIOR_PREDICATES_INVALID")
    return BehaviorAssessment(
        case_id=str(value.get("case_id", "")),
        feature_id=str(value.get("feature_id", "")),
        status=str(value.get("status", "")),
        freshness=str(value.get("freshness", "")),
        source_manifest_digest=str(value.get("source_manifest_digest", "")),
        environment_manifest_digest=str(value.get("environment_manifest_digest", "")),
        run_receipt_digest=str(value["run_receipt_digest"]) if value.get("run_receipt_digest") is not None else None,
        reason_codes=tuple(value.get("reason_codes", ())),
        predicate_results={str(k): bool(v) for k, v in predicates.items()},
    )


__all__ = [
    "feature_from_dict", "case_from_dict", "oracle_from_dict", "testability_from_dict",
    "plan_from_dict", "assessment_from_dict",
]

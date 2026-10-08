"""RU11 explicit feature testability classification."""
from __future__ import annotations

from typing import Iterable

from .models import FeatureRevision, TestabilityAssessment


def assess_testability(feature: FeatureRevision, supported_adapters: Iterable[str] = ("CLI",)) -> TestabilityAssessment:
    supported = set(supported_adapters)
    if feature.reconciliation_status != "RECONCILED":
        return TestabilityAssessment(
            feature_id=feature.feature_id,
            status="BLOCKED",
            reason_codes=("FEATURE_NOT_RECONCILED",),
        )
    if feature.interface not in supported:
        return TestabilityAssessment(
            feature_id=feature.feature_id,
            status="UNSUPPORTED",
            reason_codes=(f"ADAPTER_{feature.interface}_UNAVAILABLE",),
        )
    return TestabilityAssessment(
        feature_id=feature.feature_id,
        status="TESTABLE",
        adapter=feature.interface,
    )


__all__ = ["assess_testability"]

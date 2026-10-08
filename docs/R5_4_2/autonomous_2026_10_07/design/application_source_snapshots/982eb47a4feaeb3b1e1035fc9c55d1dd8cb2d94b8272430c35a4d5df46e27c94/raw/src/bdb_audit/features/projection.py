"""RU11 feature-status matrix projection.

The matrix is a rebuildable read model. It never writes finding/feature status
into accepted history and it downgrades stale evidence rather than promoting an
old PASS into current truth.
"""
from __future__ import annotations

from typing import Any, Sequence

from .models import BehaviorAssessment, FeatureRevision


def project_feature_status(
    feature: FeatureRevision,
    assessments: Sequence[BehaviorAssessment],
    *,
    current_source_manifest_digest: str,
    current_environment_manifest_digest: str,
) -> dict[str, Any]:
    scoped = tuple(item for item in assessments if item.feature_id == feature.feature_id)
    stale = any(
        item.source_manifest_digest != current_source_manifest_digest
        or item.environment_manifest_digest != current_environment_manifest_digest
        or item.freshness != "ACTIVE"
        for item in scoped
    )
    if stale:
        status = "INSUFFICIENT"
        freshness = "STALE"
        reason = "STALE_BEHAVIOR_EVIDENCE"
    elif not scoped:
        status = "NOT_RUN"
        freshness = "ACTIVE"
        reason = "NO_BEHAVIOR_ASSESSMENTS"
    else:
        statuses = {item.status for item in scoped}
        freshness = "ACTIVE"
        if "FAIL" in statuses:
            status, reason = "FAIL", "AT_LEAST_ONE_BEHAVIOR_FAILED"
        elif "BLOCKED" in statuses:
            status, reason = "BLOCKED", "AT_LEAST_ONE_REQUIRED_BEHAVIOR_BLOCKED"
        elif "INSUFFICIENT" in statuses:
            status, reason = "INSUFFICIENT", "AT_LEAST_ONE_REQUIRED_BEHAVIOR_INSUFFICIENT"
        elif "UNSUPPORTED" in statuses:
            status, reason = "UNSUPPORTED", "AT_LEAST_ONE_REQUIRED_BEHAVIOR_UNSUPPORTED"
        elif statuses == {"NOT_APPLICABLE"}:
            status, reason = "NOT_APPLICABLE", "ALL_BEHAVIORS_NOT_APPLICABLE"
        elif statuses == {"PASS"}:
            status, reason = "PASS", "ALL_ASSESSED_BEHAVIORS_PASS"
        else:
            status, reason = "INSUFFICIENT", "MIXED_OR_INCOMPLETE_BEHAVIOR_STATUS"
    return {
        "feature_id": feature.feature_id,
        "feature_digest": feature.digest,
        "interface": feature.interface,
        "name": feature.name,
        "status": status,
        "freshness": freshness,
        "reason": reason,
        "source_manifest_digest": current_source_manifest_digest,
        "environment_manifest_digest": current_environment_manifest_digest,
        "behavior_count": len(scoped),
        "run_receipt_digests": sorted({item.run_receipt_digest for item in scoped if item.run_receipt_digest}),
        "assessment_refs": [item.as_dict() for item in sorted(scoped, key=lambda value: value.case_id)],
    }


def feature_status_matrix(
    features: Sequence[FeatureRevision],
    assessments: Sequence[BehaviorAssessment],
    *,
    current_source_manifest_digest: str,
    current_environment_manifest_digest: str,
) -> dict[str, Any]:
    entries = [
        project_feature_status(
            feature,
            assessments,
            current_source_manifest_digest=current_source_manifest_digest,
            current_environment_manifest_digest=current_environment_manifest_digest,
        )
        for feature in sorted(features, key=lambda item: item.feature_id)
    ]
    return {
        "schema_version": "BDB-DERIVED-FEATURE-STATUS-MATRIX-1",
        "authority": "DERIVED_NOT_ACCEPTED_HISTORY",
        "source_manifest_digest": current_source_manifest_digest,
        "environment_manifest_digest": current_environment_manifest_digest,
        "entries": entries,
    }


__all__ = ["project_feature_status", "feature_status_matrix"]

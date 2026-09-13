"""RU16 incremental audit, evidence reuse, and regression contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError

INCREMENTAL_LIFECYCLE = {
    "PREDECESSOR_CONCLUDED", "SUCCESSOR_CREATED", "IMPACT_ASSESSED", "REUSE_QUALIFIED",
    "REUSE_PENDING", "TARGETED_AUDIT", "NEW_CONCLUSION",
}


def _digest(body: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(body))).hexdigest()


def _strings(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(str(item) for item in values)))


@dataclass(frozen=True)
class RevisionSnapshot:
    revision_id: str
    source_identity: Mapping[str, Any]
    members: Mapping[str, str]
    dependencies: Mapping[str, Sequence[str]] = field(default_factory=dict)
    runtime_dependencies_digest: str = ""
    schema_digest: str = ""
    environment_digest: str = ""
    policy_digest: str = ""
    template_digest: str = ""

    def __post_init__(self) -> None:
        if not self.revision_id or not self.source_identity:
            raise ValidationError("REVISION_SNAPSHOT_INVALID")
        if any(not path or len(digest) != 64 for path, digest in self.members.items()):
            raise ValidationError("REVISION_MEMBER_INVALID")
        for source, targets in self.dependencies.items():
            if source not in self.members:
                raise ValidationError("DEPENDENCY_SOURCE_UNKNOWN", source)
            if any(target not in self.members for target in targets):
                raise ValidationError("DEPENDENCY_TARGET_UNKNOWN", source)

    def as_dict(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "source_identity": dict(self.source_identity),
            "members": dict(sorted(self.members.items())),
            "dependencies": {key: sorted(set(value)) for key, value in sorted(self.dependencies.items())},
            "runtime_dependencies_digest": self.runtime_dependencies_digest,
            "schema_digest": self.schema_digest,
            "environment_digest": self.environment_digest,
            "policy_digest": self.policy_digest,
            "template_digest": self.template_digest,
        }


@dataclass(frozen=True)
class SuccessorSelection:
    predecessor_revision_id: str
    successor_revision_id: str
    successor_ref: Mapping[str, Any]
    competing_successor_ids: Sequence[str] = ()
    state: str = "SUCCESSOR_CREATED"

    def __post_init__(self) -> None:
        if not self.predecessor_revision_id or not self.successor_revision_id or not self.successor_ref:
            raise ValidationError("SUCCESSOR_SELECTION_INVALID")
        if self.state != "SUCCESSOR_CREATED":
            raise ValidationError("SUCCESSOR_STATE_INVALID")
        competitors = _strings(self.competing_successor_ids)
        if self.successor_revision_id in competitors:
            competitors = tuple(item for item in competitors if item != self.successor_revision_id)
        object.__setattr__(self, "competing_successor_ids", competitors)

    def as_dict(self) -> dict[str, Any]:
        return {
            "predecessor_revision_id": self.predecessor_revision_id,
            "successor_revision_id": self.successor_revision_id,
            "successor_ref": dict(self.successor_ref),
            "competing_successor_ids": list(self.competing_successor_ids),
            "selection_rule": "EXPLICIT_NOT_LATEST_TIMESTAMP",
            "state": self.state,
        }


@dataclass(frozen=True)
class ChangeImpactMap:
    predecessor_revision_id: str
    successor_revision_id: str
    direct_changes: Sequence[str]
    propagated_impacts: Sequence[str]
    uncertain_impacts: Sequence[str]
    change_dimensions: Sequence[str]
    state: str = "IMPACT_ASSESSED"

    def __post_init__(self) -> None:
        if self.state != "IMPACT_ASSESSED":
            raise ValidationError("IMPACT_STATE_INVALID")
        object.__setattr__(self, "direct_changes", _strings(self.direct_changes))
        object.__setattr__(self, "propagated_impacts", _strings(self.propagated_impacts))
        object.__setattr__(self, "uncertain_impacts", _strings(self.uncertain_impacts))
        object.__setattr__(self, "change_dimensions", _strings(self.change_dimensions))

    def as_dict(self) -> dict[str, Any]:
        body = {
            "artifact_class": "DERIVED_CHANGE_IMPACT_MAP",
            "predecessor_revision_id": self.predecessor_revision_id,
            "successor_revision_id": self.successor_revision_id,
            "direct_changes": list(self.direct_changes),
            "propagated_impacts": list(self.propagated_impacts),
            "uncertain_impacts": list(self.uncertain_impacts),
            "change_dimensions": list(self.change_dimensions),
            "state": self.state,
        }
        body["impact_digest"] = _digest(body)
        return body


@dataclass(frozen=True)
class EvidenceReuseAssessment:
    evidence_id: str
    predecessor_revision_id: str
    successor_revision_id: str
    scope_paths: Sequence[str]
    environment_profile: str
    evidence_refs: Sequence[str]
    status: str
    reason_codes: Sequence[str] = ()

    def __post_init__(self) -> None:
        if not self.evidence_id or not self.environment_profile or not self.scope_paths or not self.evidence_refs:
            raise ValidationError("EVIDENCE_REUSE_CONTEXT_REQUIRED")
        if self.status not in {"REUSABLE", "STALE", "PENDING", "REJECTED"}:
            raise ValidationError("EVIDENCE_REUSE_STATUS_INVALID")
        object.__setattr__(self, "scope_paths", _strings(self.scope_paths))
        object.__setattr__(self, "evidence_refs", _strings(self.evidence_refs))
        object.__setattr__(self, "reason_codes", _strings(self.reason_codes))

    @property
    def current_pass_eligible(self) -> bool:
        return self.status == "REUSABLE"

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_class": "DERIVED_EVIDENCE_REUSE_ASSESSMENT",
            "evidence_id": self.evidence_id,
            "predecessor_revision_id": self.predecessor_revision_id,
            "successor_revision_id": self.successor_revision_id,
            "scope_paths": list(self.scope_paths),
            "environment_profile": self.environment_profile,
            "evidence_refs": list(self.evidence_refs),
            "status": self.status,
            "current_pass_eligible": self.current_pass_eligible,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class RequalificationPlan:
    plan_id: str
    impact_digest: str
    required_paths: Sequence[str]
    reusable_evidence_ids: Sequence[str]
    pending_evidence_ids: Sequence[str]
    coverage_denominator: int
    state: str

    def __post_init__(self) -> None:
        if not self.plan_id or len(self.impact_digest) != 64 or self.coverage_denominator <= 0:
            raise ValidationError("REQUALIFICATION_PLAN_INVALID")
        if self.state not in {"REUSE_QUALIFIED", "REUSE_PENDING"}:
            raise ValidationError("REQUALIFICATION_STATE_INVALID")
        object.__setattr__(self, "required_paths", _strings(self.required_paths))
        object.__setattr__(self, "reusable_evidence_ids", _strings(self.reusable_evidence_ids))
        object.__setattr__(self, "pending_evidence_ids", _strings(self.pending_evidence_ids))

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_class": "DERIVED_REQUALIFICATION_PLAN",
            "plan_id": self.plan_id,
            "impact_digest": self.impact_digest,
            "required_paths": list(self.required_paths),
            "reusable_evidence_ids": list(self.reusable_evidence_ids),
            "pending_evidence_ids": list(self.pending_evidence_ids),
            "coverage_denominator": self.coverage_denominator,
            "state": self.state,
        }


@dataclass(frozen=True)
class ReplayRun:
    replay_id: str
    plan_id: str
    executed_paths: Sequence[str]
    failed_paths: Sequence[str]
    state: str = "TARGETED_AUDIT"

    def __post_init__(self) -> None:
        if not self.replay_id or not self.plan_id or self.state != "TARGETED_AUDIT":
            raise ValidationError("REPLAY_RUN_INVALID")
        object.__setattr__(self, "executed_paths", _strings(self.executed_paths))
        object.__setattr__(self, "failed_paths", _strings(self.failed_paths))

    def as_dict(self) -> dict[str, Any]:
        return {"artifact_class": "DERIVED_REPLAY_RUN", "replay_id": self.replay_id, "plan_id": self.plan_id, "executed_paths": list(self.executed_paths), "failed_paths": list(self.failed_paths), "state": self.state, "status": "FAIL" if self.failed_paths else "PASS"}


@dataclass(frozen=True)
class AuditDelta:
    predecessor_revision_id: str
    successor_revision_id: str
    impacted_paths: Sequence[str]
    requalified_paths: Sequence[str]
    failed_paths: Sequence[str]
    previous_cost_units: int
    current_cost_units: int
    coverage_denominator: int
    state: str = "NEW_CONCLUSION"

    def __post_init__(self) -> None:
        if self.coverage_denominator <= 0 or min(self.previous_cost_units, self.current_cost_units) < 0:
            raise ValidationError("AUDIT_DELTA_INVALID")
        object.__setattr__(self, "impacted_paths", _strings(self.impacted_paths))
        object.__setattr__(self, "requalified_paths", _strings(self.requalified_paths))
        object.__setattr__(self, "failed_paths", _strings(self.failed_paths))

    def as_dict(self) -> dict[str, Any]:
        saved = self.previous_cost_units - self.current_cost_units
        return {
            "artifact_class": "DERIVED_AUDIT_DELTA",
            "predecessor_revision_id": self.predecessor_revision_id,
            "successor_revision_id": self.successor_revision_id,
            "impacted_paths": list(self.impacted_paths),
            "requalified_paths": list(self.requalified_paths),
            "failed_paths": list(self.failed_paths),
            "coverage_denominator": self.coverage_denominator,
            "previous_cost_units": self.previous_cost_units,
            "current_cost_units": self.current_cost_units,
            "cost_units_saved": saved,
            "state": self.state,
        }


__all__ = ["RevisionSnapshot", "SuccessorSelection", "ChangeImpactMap", "EvidenceReuseAssessment", "RequalificationPlan", "ReplayRun", "AuditDelta", "INCREMENTAL_LIFECYCLE"]

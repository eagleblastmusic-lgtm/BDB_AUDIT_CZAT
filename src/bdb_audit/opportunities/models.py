"""RU15 product/UX/architecture opportunity contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError

OPPORTUNITY_LIFECYCLE = {
    "CONTEXT_READY", "WALKTHROUGH_RECORDED", "FRICTION_CANDIDATE", "PROPOSED",
    "SKEPTIC_REVIEW", "ACCEPT_FOR_REPORT", "REVISE", "REJECT",
}


def _digest(body: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(body))).hexdigest()


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(str(item) for item in values)))


@dataclass(frozen=True)
class ProductContext:
    target_id: str
    source_identity: Mapping[str, Any]
    declared_goals: Sequence[str]
    personas: Sequence[str]
    runtime_available: bool
    state: str = "CONTEXT_READY"

    def __post_init__(self) -> None:
        if not self.target_id or not self.source_identity or self.state != "CONTEXT_READY":
            raise ValidationError("PRODUCT_CONTEXT_INVALID")
        object.__setattr__(self, "declared_goals", _unique(self.declared_goals))
        object.__setattr__(self, "personas", _unique(self.personas))

    def as_dict(self) -> dict[str, Any]:
        return {"artifact_class": "DERIVED_PRODUCT_CONTEXT", "target_id": self.target_id, "source_identity": dict(self.source_identity), "declared_goals": list(self.declared_goals), "personas": list(self.personas), "runtime_available": self.runtime_available, "state": self.state}


@dataclass(frozen=True)
class UserTaskTrace:
    trace_id: str
    target_id: str
    actor: str
    steps: Sequence[str]
    evidence_refs: Sequence[str]
    observation_mode: str
    runtime_observed: bool
    state: str = "WALKTHROUGH_RECORDED"

    def __post_init__(self) -> None:
        if not self.trace_id or not self.target_id or not self.actor or not self.steps:
            raise ValidationError("TASK_TRACE_INVALID")
        if self.observation_mode not in {"OBSERVED", "DECLARED", "INFERRED"}:
            raise ValidationError("TASK_TRACE_OBSERVATION_MODE_INVALID")
        if self.observation_mode == "OBSERVED" and (not self.runtime_observed or not self.evidence_refs):
            raise ValidationError("TASK_TRACE_OBSERVED_WITHOUT_RUNTIME_EVIDENCE")
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "evidence_refs", _unique(self.evidence_refs))

    def as_dict(self) -> dict[str, Any]:
        return {"artifact_class": "DERIVED_USER_TASK_TRACE", "trace_id": self.trace_id, "target_id": self.target_id, "actor": self.actor, "steps": list(self.steps), "evidence_refs": list(self.evidence_refs), "observation_mode": self.observation_mode, "runtime_observed": self.runtime_observed, "state": self.state}


@dataclass(frozen=True)
class FrictionCandidate:
    candidate_id: str
    trace_id: str
    description: str
    evidence_refs: Sequence[str]
    basis: str
    severity: str = "MEDIUM"
    state: str = "FRICTION_CANDIDATE"

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.trace_id or not self.description:
            raise ValidationError("FRICTION_CANDIDATE_INVALID")
        if self.basis not in {"OBSERVED", "INFERRED", "DECLARED"} or self.severity not in {"LOW", "MEDIUM", "HIGH"}:
            raise ValidationError("FRICTION_BASIS_INVALID")
        refs = _unique(self.evidence_refs)
        if self.basis == "OBSERVED" and not refs:
            raise ValidationError("FRICTION_OBSERVED_EVIDENCE_REQUIRED")
        object.__setattr__(self, "evidence_refs", refs)

    def as_dict(self) -> dict[str, Any]:
        return {"artifact_class": "DERIVED_UX_FRICTION_CANDIDATE", "candidate_id": self.candidate_id, "trace_id": self.trace_id, "description": self.description, "evidence_refs": list(self.evidence_refs), "basis": self.basis, "severity": self.severity, "state": self.state}


@dataclass(frozen=True)
class OpportunityProposal:
    proposal_id: str
    title: str
    opportunity_type: str
    source_candidate_ids: Sequence[str]
    evidence_refs: Sequence[str]
    benefit_hypothesis: str
    basis: str
    state: str = "PROPOSED"
    mandatory_obligation: bool = False

    def __post_init__(self) -> None:
        if not self.proposal_id or not self.title or self.opportunity_type not in {"UX", "PRODUCT", "ARCHITECTURE"}:
            raise ValidationError("OPPORTUNITY_PROPOSAL_INVALID")
        if self.basis not in {"OBSERVED", "INFERRED", "DECLARED"}:
            raise ValidationError("OPPORTUNITY_BASIS_INVALID")
        if self.state != "PROPOSED" or self.mandatory_obligation:
            raise ValidationError("OPPORTUNITY_CANNOT_BECOME_MANDATORY")
        object.__setattr__(self, "source_candidate_ids", _unique(self.source_candidate_ids))
        object.__setattr__(self, "evidence_refs", _unique(self.evidence_refs))

    def as_dict(self) -> dict[str, Any]:
        body = {"artifact_class": "DERIVED_OPPORTUNITY_PROPOSAL", "proposal_id": self.proposal_id, "title": self.title, "opportunity_type": self.opportunity_type, "source_candidate_ids": list(self.source_candidate_ids), "evidence_refs": list(self.evidence_refs), "benefit_hypothesis": self.benefit_hypothesis, "basis": self.basis, "state": self.state, "mandatory_obligation": False}
        body["proposal_digest"] = _digest(body)
        return body


@dataclass(frozen=True)
class OpportunityAssessment:
    proposal_id: str
    decision: str
    evidence_refs: Sequence[str]
    rationale: str
    uncertainty_codes: Sequence[str] = field(default_factory=tuple)
    state: str = "SKEPTIC_REVIEW"

    def __post_init__(self) -> None:
        if not self.proposal_id or self.decision not in {"ACCEPT_FOR_REPORT", "REVISE", "REJECT"}:
            raise ValidationError("OPPORTUNITY_ASSESSMENT_INVALID")
        if self.state != "SKEPTIC_REVIEW":
            raise ValidationError("OPPORTUNITY_REVIEW_STATE_INVALID")
        object.__setattr__(self, "evidence_refs", _unique(self.evidence_refs))
        object.__setattr__(self, "uncertainty_codes", _unique(self.uncertainty_codes))

    def as_dict(self) -> dict[str, Any]:
        return {"artifact_class": "DERIVED_OPPORTUNITY_ASSESSMENT", "proposal_id": self.proposal_id, "decision": self.decision, "evidence_refs": list(self.evidence_refs), "rationale": self.rationale, "uncertainty_codes": list(self.uncertainty_codes), "state": self.state, "resulting_state": self.decision}


__all__ = ["ProductContext", "UserTaskTrace", "FrictionCandidate", "OpportunityProposal", "OpportunityAssessment", "OPPORTUNITY_LIFECYCLE"]

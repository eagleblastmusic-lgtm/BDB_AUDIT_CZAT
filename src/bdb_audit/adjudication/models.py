"""R5.3 Finding, Root Cause, and Contradiction canonical domain models (M21/M22)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id, validate_id
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, ObjectRef

AXIS_DOMAINS = {"MECHANISM", "REACHABILITY", "IMPACT", "SEVERITY"}
EPISTEMIC_OUTCOMES = {"SUPPORTED", "REFUTED", "INCONCLUSIVE", "BLOCKED", "NOT_APPLICABLE"}
SEVERITY_VALUES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
CONFIDENCE_VALUES = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
FINDING_CATEGORIES = {
    "SECURITY", "RELIABILITY", "DATA_INTEGRITY", "AVAILABILITY", "PRIVACY",
    "RELEASE_ASSURANCE", "EVIDENCE_QUALITY", "OTHER",
}
FINDING_LIFECYCLE_STATUSES = {
    "OPEN", "CONFIRMED_CURRENT", "REJECTED", "SUPERSEDED",
    "REMEDIATION_PENDING", "STALE_FOR_CURRENT_SOURCE",
    "FIXED_ON_NEW_SOURCE", "PARTIALLY_FIXED", "REOPENED",
}
ROOT_CAUSE_STATUSES = {"ACTIVE", "SUPERSEDED", "RETIRED"}
CONTRADICTION_STATUSES = {
    "OPEN", "TESTING", "RESOLVED_SCOPED", "RESOLVED_FULL", "REOPENED", "BLOCKED",
}
CONTRADICTION_RESOLUTION_KINDS = {
    "REFUTED", "SCOPES_SEPARATED", "HARNESS_INVALIDATED", "CONTRACT_CHANGED", "BLOCKED",
}
CONTRADICTION_RESOLUTION_RESULTS = {"RESOLVED_SCOPED", "RESOLVED_FULL", "BLOCKED"}


def _canonical_strings(values: Sequence[str], name: str = "strings") -> tuple[str, ...]:
    vals = [str(value) for value in values]
    if len(vals) != len(set(vals)):
        raise ValidationError(f"DUPLICATE_{name.upper()}")
    return tuple(sorted(vals, key=lambda value: value.encode("utf-8")))


def _ref_dict(ref_or_obj: Any) -> dict[str, Any]:
    if isinstance(ref_or_obj, ObjectRef):
        return ref_or_obj.as_dict()
    if isinstance(ref_or_obj, CanonicalObject):
        return ref_or_obj.as_ref().as_dict()
    if isinstance(ref_or_obj, Mapping):
        return dict(ref_or_obj)
    raise ValidationError("INVALID_REFERENCE")


def _canonical_refs(values: Sequence[Any]) -> tuple[dict[str, Any], ...]:
    return tuple(canonical_reference_set([_ref_dict(value) for value in values]))


def _canonical_values(values: Sequence[Any], name: str) -> tuple[Any, ...]:
    keyed: dict[bytes, Any] = {}
    for value in values:
        key = canonical_bytes(value)
        if key in keyed:
            raise ValidationError(f"DUPLICATE_{name.upper()}")
        keyed[key] = value
    return tuple(keyed[key] for key in sorted(keyed))


def sort_membership_edges(edges: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Canonical RootCause membership order from R5.3 §58.

    Ordering is the tuple (finding claim revision digest, relation role,
    BDB-CJSON-1(scope)). Exact duplicate tuples are rejected. Repeating a
    finding under a different role/scope is retained; whether that is allowed
    for a particular campaign remains a pinned policy decision.
    """

    def edge_key(edge: Mapping[str, Any]) -> tuple[str, str, bytes]:
        finding_ref = edge.get("finding_claim_revision_ref")
        if isinstance(finding_ref, Mapping):
            finding_digest = str(finding_ref.get("revision_digest", ""))
        else:
            finding_digest = str(finding_ref or "")
        return (
            finding_digest,
            str(edge.get("relation_role", "")),
            canonical_bytes(edge.get("scope", {})),
        )

    normalized = [dict(edge) for edge in edges]
    seen: set[tuple[str, str, bytes]] = set()
    for edge in normalized:
        key = edge_key(edge)
        if key in seen:
            raise ValidationError(
                "ROOT_CAUSE_MEMBERSHIP_DUPLICATE_OR_AMBIGUOUS",
                f"Duplicate membership edge: {edge}",
            )
        seen.add(key)
    return sorted(normalized, key=edge_key)


@dataclass(frozen=True)
class FindingClaimRevision:
    """Evidence-free versioned finding claim (R5.3 §50)."""

    claim_statement: str
    source_generation_ref: Any
    category: str = "OTHER"
    scope_refs: Sequence[Any] = ()
    violated_invariant_refs: Sequence[Any] = ()
    discovery_relation_refs: Sequence[Any] = ()
    limitations: Sequence[str] = ()
    previous_finding_claim_revision_ref: Any = None
    finding_id: str | None = None
    finding_claim_revision: str = "1"

    def __post_init__(self) -> None:
        if not self.claim_statement.strip():
            raise ValidationError("FINDING_CLAIM_STATEMENT_REQUIRED")
        if self.category not in FINDING_CATEGORIES:
            raise ValidationError("INVALID_FINDING_CATEGORY", self.category)
        if self.finding_id is None:
            object.__setattr__(self, "finding_id", new_id("finding_claim_revision"))
        elif self.finding_id.startswith("finding_claim_revision_"):
            validate_id(self.finding_id, "finding_claim_revision")
        object.__setattr__(self, "scope_refs", _canonical_refs(self.scope_refs))
        object.__setattr__(self, "violated_invariant_refs", _canonical_refs(self.violated_invariant_refs))
        object.__setattr__(self, "discovery_relation_refs", _canonical_refs(self.discovery_relation_refs))
        object.__setattr__(self, "limitations", _canonical_strings(self.limitations, "finding_limitations"))

    def body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "finding_id": self.finding_id,
            "finding_claim_revision": str(self.finding_claim_revision),
            "source_generation_ref": _ref_dict(self.source_generation_ref),
            "claim_statement": self.claim_statement,
            "scope_refs": list(self.scope_refs),
            "category": self.category,
            "violated_invariant_refs": list(self.violated_invariant_refs),
            "discovery_relation_refs": list(self.discovery_relation_refs),
            "limitations": list(self.limitations),
        }
        if self.previous_finding_claim_revision_ref is not None:
            body["previous_finding_claim_revision_ref"] = _ref_dict(self.previous_finding_claim_revision_ref)
        return body

    def as_object(self) -> CanonicalObject:
        logical_id = self.finding_id if self.finding_id and self.finding_id.startswith("finding_claim_revision_") else None
        return CanonicalObject("finding_claim_revision", self.body(), logical_id=logical_id)

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class FindingAxisAssessment:
    """One immutable Severity/Mechanism/Reachability/Impact assessment (R5.3 §52)."""

    claim_revision_ref: Any
    assessment_input_history_cut: Mapping[str, Any]
    assessment_policy_ref: Any
    axis: str
    scope: Mapping[str, Any] = field(default_factory=dict)
    evidence_qualification_refs: Sequence[Any] = ()
    epistemic_outcome: str | None = None
    method_or_characterization_refs: Sequence[Any] = ()
    severity_value: str | None = None
    confidence: str = "UNKNOWN"
    limitations: Sequence[str] = ()
    reason_codes: Sequence[str] = ()
    finding_axis_assessment_id: str | None = None

    def __post_init__(self) -> None:
        if self.finding_axis_assessment_id is None:
            object.__setattr__(self, "finding_axis_assessment_id", new_id("finding_axis_assessment"))
        elif self.finding_axis_assessment_id.startswith("finding_axis_assessment_"):
            validate_id(self.finding_axis_assessment_id, "finding_axis_assessment")
        if self.axis not in AXIS_DOMAINS:
            raise ValidationError("INVALID_AXIS", self.axis)
        if self.confidence not in CONFIDENCE_VALUES:
            raise ValidationError("INVALID_AXIS_CONFIDENCE", self.confidence)
        if self.axis == "SEVERITY":
            if self.severity_value not in SEVERITY_VALUES:
                raise ValidationError("SEVERITY_VALUE_REQUIRED")
            if self.epistemic_outcome is not None:
                raise ValidationError("SEVERITY_EPISTEMIC_OUTCOME_FORBIDDEN")
        else:
            if self.epistemic_outcome not in EPISTEMIC_OUTCOMES:
                raise ValidationError("INVALID_EPISTEMIC_OUTCOME", str(self.epistemic_outcome))
            if self.severity_value is not None:
                raise ValidationError("NON_SEVERITY_VALUE_FORBIDDEN")
        object.__setattr__(self, "scope", dict(self.scope))
        object.__setattr__(self, "evidence_qualification_refs", _canonical_refs(self.evidence_qualification_refs))
        object.__setattr__(self, "method_or_characterization_refs", _canonical_refs(self.method_or_characterization_refs))
        object.__setattr__(self, "limitations", _canonical_strings(self.limitations, "axis_limitations"))
        object.__setattr__(self, "reason_codes", _canonical_strings(self.reason_codes, "axis_reason_codes"))

    def body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "finding_axis_assessment_id": self.finding_axis_assessment_id,
            "claim_revision_ref": _ref_dict(self.claim_revision_ref),
            "axis": self.axis,
            "assessment_input_history_cut": dict(self.assessment_input_history_cut),
            "assessment_policy_ref": _ref_dict(self.assessment_policy_ref),
            "scope": dict(self.scope),
            "evidence_qualification_refs": list(self.evidence_qualification_refs),
            "method_or_characterization_refs": list(self.method_or_characterization_refs),
            "confidence": self.confidence,
            "limitations": list(self.limitations),
            "reason_codes": list(self.reason_codes),
        }
        if self.axis == "SEVERITY":
            body["severity_value"] = self.severity_value
        else:
            body["epistemic_outcome"] = self.epistemic_outcome
        return body

    def as_object(self) -> CanonicalObject:
        logical_id = (
            self.finding_axis_assessment_id
            if self.finding_axis_assessment_id and self.finding_axis_assessment_id.startswith("finding_axis_assessment_")
            else None
        )
        return CanonicalObject("finding_axis_assessment", self.body(), logical_id=logical_id)

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class FindingAdjudicationDecision:
    """Current decision over one exact claim revision and four exact axes."""

    claim_revision_ref: Any
    input_history_cut: Mapping[str, Any]
    adjudicator_ref: Any
    mechanism_assessment_ref: Any
    reachability_assessment_ref: Any
    impact_assessment_ref: Any
    severity_assessment_ref: Any
    finding_lifecycle_status: str = "OPEN"
    scope: Mapping[str, Any] = field(default_factory=dict)
    evidence_qualification_refs: Sequence[Any] = ()
    knowledge_state_refs: Sequence[Any] = ()
    corpus_snapshot_refs: Sequence[Any] = ()
    reason_codes: Sequence[str] = ()
    previous_adjudication_decision_ref: Any = None
    decision_id: str | None = None

    def __post_init__(self) -> None:
        if self.decision_id is None:
            object.__setattr__(self, "decision_id", new_id("finding_adjudication_decision"))
        elif self.decision_id.startswith("finding_adjudication_decision_"):
            validate_id(self.decision_id, "finding_adjudication_decision")
        if self.finding_lifecycle_status not in FINDING_LIFECYCLE_STATUSES:
            raise ValidationError("INVALID_LIFECYCLE_STATUS", self.finding_lifecycle_status)
        object.__setattr__(self, "scope", dict(self.scope))
        object.__setattr__(self, "evidence_qualification_refs", _canonical_refs(self.evidence_qualification_refs))
        object.__setattr__(self, "knowledge_state_refs", _canonical_refs(self.knowledge_state_refs))
        object.__setattr__(self, "corpus_snapshot_refs", _canonical_refs(self.corpus_snapshot_refs))
        object.__setattr__(self, "reason_codes", _canonical_strings(self.reason_codes, "adjudication_reason_codes"))

    def body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "decision_id": self.decision_id,
            "claim_revision_ref": _ref_dict(self.claim_revision_ref),
            "scope": dict(self.scope),
            "mechanism_assessment_ref": _ref_dict(self.mechanism_assessment_ref),
            "reachability_assessment_ref": _ref_dict(self.reachability_assessment_ref),
            "impact_assessment_ref": _ref_dict(self.impact_assessment_ref),
            "severity_assessment_ref": _ref_dict(self.severity_assessment_ref),
            "finding_lifecycle_status": self.finding_lifecycle_status,
            "evidence_qualification_refs": list(self.evidence_qualification_refs),
            "knowledge_state_refs": list(self.knowledge_state_refs),
            "corpus_snapshot_refs": list(self.corpus_snapshot_refs),
            "adjudicator_ref": _ref_dict(self.adjudicator_ref),
            "input_history_cut": dict(self.input_history_cut),
            "reason_codes": list(self.reason_codes),
        }
        if self.previous_adjudication_decision_ref is not None:
            body["previous_adjudication_decision_ref"] = _ref_dict(self.previous_adjudication_decision_ref)
        return body

    def as_object(self) -> CanonicalObject:
        logical_id = self.decision_id if self.decision_id and self.decision_id.startswith("finding_adjudication_decision_") else None
        return CanonicalObject("finding_adjudication_decision", self.body(), logical_id=logical_id)

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class RootCauseRevision:
    """Versioned Root Cause with authoritative membership edges (R5.3 §58)."""

    source_generation_ref: Any
    mechanism_statement: str
    membership_edges: Sequence[dict[str, Any]]
    scope: Mapping[str, Any] = field(default_factory=dict)
    status: str = "ACTIVE"
    predecessor_root_cause_refs: Sequence[Any] = ()
    multi_causal_condition: Any = None
    root_cause_id: str | None = None
    root_cause_revision: str = "1"

    def __post_init__(self) -> None:
        if not self.mechanism_statement.strip():
            raise ValidationError("ROOT_CAUSE_MECHANISM_REQUIRED")
        if self.status not in ROOT_CAUSE_STATUSES:
            raise ValidationError("INVALID_ROOT_CAUSE_STATUS", self.status)
        if self.root_cause_id is None:
            object.__setattr__(self, "root_cause_id", new_id("root_cause_revision"))
        elif self.root_cause_id.startswith("root_cause_revision_"):
            validate_id(self.root_cause_id, "root_cause_revision")
        object.__setattr__(self, "membership_edges", tuple(sort_membership_edges(self.membership_edges)))
        object.__setattr__(self, "predecessor_root_cause_refs", _canonical_refs(self.predecessor_root_cause_refs))
        object.__setattr__(self, "scope", dict(self.scope))

    def body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "root_cause_id": self.root_cause_id,
            "root_cause_revision": str(self.root_cause_revision),
            "source_generation_ref": _ref_dict(self.source_generation_ref),
            "mechanism_statement": self.mechanism_statement,
            "membership_edges": list(self.membership_edges),
            "predecessor_root_cause_refs": list(self.predecessor_root_cause_refs),
            "scope": dict(self.scope),
            "status": self.status,
        }
        if self.multi_causal_condition is not None:
            body["multi_causal_condition"] = self.multi_causal_condition
        return body

    def as_object(self) -> CanonicalObject:
        logical_id = self.root_cause_id if self.root_cause_id and self.root_cause_id.startswith("root_cause_revision_") else None
        return CanonicalObject("root_cause_revision", self.body(), logical_id=logical_id)

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class ContradictionRevision:
    """Scoped, versioned contradiction case over two or more exact claims."""

    claim_revision_refs: Sequence[Any]
    scope: Mapping[str, Any]
    positions: Sequence[Any]
    required_falsifier: Any
    supporting_evidence_qualification_refs: Sequence[Any] = ()
    opposing_evidence_qualification_refs: Sequence[Any] = ()
    failure_assumption_differences: Sequence[Any] = ()
    environment_input_model_differences: Sequence[Any] = ()
    status: str = "OPEN"
    predecessor_contradiction_revision_ref: Any = None
    resolution_decision_ref: Any = None
    contradiction_id: str | None = None
    contradiction_revision: str = "1"

    def __post_init__(self) -> None:
        if self.contradiction_id is None:
            object.__setattr__(self, "contradiction_id", new_id("contradiction_revision"))
        elif self.contradiction_id.startswith("contradiction_revision_"):
            validate_id(self.contradiction_id, "contradiction_revision")
        if self.status not in CONTRADICTION_STATUSES:
            raise ValidationError("INVALID_CONTRADICTION_STATUS", self.status)
        claim_refs = _canonical_refs(self.claim_revision_refs)
        if len(claim_refs) < 2:
            raise ValidationError("CONTRADICTION_REQUIRES_MULTIPLE_CLAIMS")
        if self.resolution_decision_ref is not None and self.predecessor_contradiction_revision_ref is None:
            raise ValidationError("CONTRADICTION_RESOLUTION_REQUIRES_PREDECESSOR")
        object.__setattr__(self, "claim_revision_refs", claim_refs)
        object.__setattr__(self, "scope", dict(self.scope))
        object.__setattr__(self, "positions", _canonical_values(self.positions, "contradiction_positions"))
        object.__setattr__(
            self,
            "supporting_evidence_qualification_refs",
            _canonical_refs(self.supporting_evidence_qualification_refs),
        )
        object.__setattr__(
            self,
            "opposing_evidence_qualification_refs",
            _canonical_refs(self.opposing_evidence_qualification_refs),
        )
        object.__setattr__(
            self,
            "failure_assumption_differences",
            _canonical_values(self.failure_assumption_differences, "failure_assumption_differences"),
        )
        object.__setattr__(
            self,
            "environment_input_model_differences",
            _canonical_values(self.environment_input_model_differences, "environment_input_model_differences"),
        )

    def body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "contradiction_id": self.contradiction_id,
            "contradiction_revision": str(self.contradiction_revision),
            "claim_revision_refs": list(self.claim_revision_refs),
            "scope": dict(self.scope),
            "positions": list(self.positions),
            "supporting_evidence_qualification_refs": list(self.supporting_evidence_qualification_refs),
            "opposing_evidence_qualification_refs": list(self.opposing_evidence_qualification_refs),
            "failure_assumption_differences": list(self.failure_assumption_differences),
            "environment_input_model_differences": list(self.environment_input_model_differences),
            "required_falsifier": self.required_falsifier,
            "status": self.status,
        }
        if self.predecessor_contradiction_revision_ref is not None:
            body["predecessor_contradiction_revision_ref"] = _ref_dict(self.predecessor_contradiction_revision_ref)
        if self.resolution_decision_ref is not None:
            body["resolution_decision_ref"] = _ref_dict(self.resolution_decision_ref)
        return body

    def as_object(self) -> CanonicalObject:
        logical_id = self.contradiction_id if self.contradiction_id and self.contradiction_id.startswith("contradiction_revision_") else None
        return CanonicalObject("contradiction_revision", self.body(), logical_id=logical_id)

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class ContradictionResolutionDecision:
    """Prior-bound contradiction resolution decision (R5.3 §60)."""

    contradiction_prior_revision_ref: Any
    resolution_input_history_cut: Mapping[str, Any]
    resolved_scope: Mapping[str, Any]
    resolution_kind: str
    basis_refs: Sequence[Any]
    resulting_status: str
    resolution_decision_id: str | None = None

    def __post_init__(self) -> None:
        if self.resolution_decision_id is None:
            object.__setattr__(self, "resolution_decision_id", new_id("contradiction_resolution_decision"))
        elif self.resolution_decision_id.startswith("contradiction_resolution_decision_"):
            validate_id(self.resolution_decision_id, "contradiction_resolution_decision")
        if self.resolution_kind not in CONTRADICTION_RESOLUTION_KINDS:
            raise ValidationError("INVALID_CONTRADICTION_RESOLUTION_KIND", self.resolution_kind)
        if self.resulting_status not in CONTRADICTION_RESOLUTION_RESULTS:
            raise ValidationError("INVALID_CONTRADICTION_RESOLUTION_STATUS", self.resulting_status)
        basis = _canonical_refs(self.basis_refs)
        if not basis:
            raise ValidationError("CONTRADICTION_RESOLUTION_BASIS_REQUIRED")
        object.__setattr__(self, "basis_refs", basis)
        object.__setattr__(self, "resolved_scope", dict(self.resolved_scope))

    def body(self) -> dict[str, Any]:
        return {
            "resolution_decision_id": self.resolution_decision_id,
            "contradiction_prior_revision_ref": _ref_dict(self.contradiction_prior_revision_ref),
            "resolution_input_history_cut": dict(self.resolution_input_history_cut),
            "resolved_scope": dict(self.resolved_scope),
            "resolution_kind": self.resolution_kind,
            "basis_refs": list(self.basis_refs),
            "resulting_status": self.resulting_status,
        }

    def as_object(self) -> CanonicalObject:
        logical_id = (
            self.resolution_decision_id
            if self.resolution_decision_id and self.resolution_decision_id.startswith("contradiction_resolution_decision_")
            else None
        )
        return CanonicalObject("contradiction_resolution_decision", self.body(), logical_id=logical_id)

    @property
    def digest(self) -> str:
        return self.as_object().digest

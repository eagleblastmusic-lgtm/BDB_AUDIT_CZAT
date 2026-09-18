"""R5.3.1 Finding, Root Cause, and Contradiction domain models (M21/M22)."""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.hashing import DIGEST_PROFILE, object_digest
from ..core.ids import new_id, validate_id
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, ObjectRef

AXIS_DOMAINS = {"MECHANISM", "REACHABILITY", "IMPACT", "SEVERITY"}
EPISTEMIC_OUTCOMES = {"SUPPORTED", "REFUTED", "INCONCLUSIVE", "BLOCKED", "NOT_APPLICABLE"}
FINDING_LIFECYCLE_STATUSES = {
    "OPEN", "CONFIRMED_CURRENT", "REJECTED", "SUPERSEDED",
    "REMEDIATION_PENDING", "STALE_FOR_CURRENT_SOURCE",
    "FIXED_ON_NEW_SOURCE", "PARTIALLY_FIXED", "REOPENED"
}
CONTRADICTION_STATUSES = {
    "OPEN", "TESTING", "RESOLVED_SCOPED", "RESOLVED_FULL", "REOPENED", "BLOCKED"
}
CONTRADICTION_RESOLUTION_KINDS = {
    "REFUTED", "SCOPES_SEPARATED", "HARNESS_INVALIDATED",
    "CONTRACT_CHANGED", "BLOCKED"
}
CONTRADICTION_RESOLUTION_RESULTS = {
    "RESOLVED_SCOPED", "RESOLVED_FULL", "BLOCKED"
}


def _canonical_strings(values: Sequence[str], name: str = "strings") -> list[str]:
    vals = list(values)
    if len(vals) != len(set(vals)):
        raise ValidationError(f"DUPLICATE_{name.upper()}")
    return sorted(vals)


def _ref_dict(ref_or_obj: Any) -> dict:
    if isinstance(ref_or_obj, ObjectRef):
        return ref_or_obj.as_dict()
    if isinstance(ref_or_obj, CanonicalObject):
        return ref_or_obj.as_ref().as_dict()
    if isinstance(ref_or_obj, dict):
        return ref_or_obj
    raise ValidationError("INVALID_REFERENCE")


def sort_membership_edges(edges: Sequence[dict]) -> list[dict]:
    """Sort membership edges deterministically: (finding_claim_revision_ref, relation_role, BDB-CJSON-1(scope)).

    R5N74:
    - Canonical ascending tuple
    - Reject exact duplicate tuples: ROOT_CAUSE_MEMBERSHIP_DUPLICATE_OR_AMBIGUOUS
    """
    def edge_key(e: dict):
        f_ref = e.get("finding_claim_revision_ref")
        f_str = f_ref if isinstance(f_ref, str) else (f_ref.get("revision_digest", "") if isinstance(f_ref, dict) else "")
        role = e.get("relation_role", "")
        scope = e.get("scope", {})
        scope_bytes = canonical_bytes(scope)
        return (f_str, role, scope_bytes)

    seen = set()
    for e in edges:
        k = edge_key(e)
        if k in seen:
            raise ValidationError(
                "ROOT_CAUSE_MEMBERSHIP_DUPLICATE_OR_AMBIGUOUS",
                f"Duplicate or ambiguous membership edge: {e}",
            )
        seen.add(k)

    return sorted(list(edges), key=edge_key)


@dataclass(frozen=True)
class FindingClaimRevision:
    statement: str
    source_generation_ref: Any
    scope_refs: Sequence[Any] = ()
    violated_invariant_refs: Sequence[Any] = ()
    discovery_relation_refs: Sequence[Any] = ()
    previous_finding_claim_revision_ref: Any = None
    claim_id: str | None = None
    claim_revision: str = "1"

    def __post_init__(self):
        if self.claim_id is None:
            object.__setattr__(self, "claim_id", new_id("finding_claim_revision"))
        elif self.claim_id.startswith("finding_claim_revision_"):
            validate_id(self.claim_id, "finding_claim_revision")

        object.__setattr__(
            self, "scope_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.scope_refs]))
        )
        object.__setattr__(
            self, "violated_invariant_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.violated_invariant_refs]))
        )
        object.__setattr__(
            self, "discovery_relation_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.discovery_relation_refs]))
        )

    def body(self) -> dict:
        data = {
            "claim_id": self.claim_id or "claim_default",
            "claim_revision": str(self.claim_revision),
            "source_generation_ref": _ref_dict(self.source_generation_ref),
            "statement": self.statement,
            "scope_refs": list(self.scope_refs),
            "violated_invariant_refs": list(self.violated_invariant_refs),
            "discovery_relation_refs": list(self.discovery_relation_refs),
        }
        if self.previous_finding_claim_revision_ref is not None:
            data["previous_finding_claim_revision_ref"] = _ref_dict(self.previous_finding_claim_revision_ref)
        return data

    def as_object(self) -> CanonicalObject:
        lid = self.claim_id if (self.claim_id and self.claim_id.startswith("finding_claim_revision_")) else None
        return CanonicalObject(
            "finding_claim_revision", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class FindingAxisAssessment:
    claim_revision_ref: Any
    assessment_input_history_cut: dict
    assessment_policy_ref: Any
    axis: str
    epistemic_outcome: str
    method: str
    evidence_qualification_refs: Sequence[Any] = ()
    method_or_characterization_refs: Sequence[Any] = ()
    assessment_id: str | None = None

    def __post_init__(self):
        if self.assessment_id is None:
            object.__setattr__(self, "assessment_id", new_id("finding_axis_assessment"))
        elif self.assessment_id.startswith("finding_axis_assessment_"):
            validate_id(self.assessment_id, "finding_axis_assessment")

        if self.axis not in AXIS_DOMAINS:
            raise ValidationError("INVALID_AXIS", str(self.axis))
        if self.epistemic_outcome not in EPISTEMIC_OUTCOMES:
            raise ValidationError("INVALID_EPISTEMIC_OUTCOME", str(self.epistemic_outcome))

        object.__setattr__(
            self, "evidence_qualification_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.evidence_qualification_refs]))
        )

    def body(self) -> dict:
        data = {
            "assessment_id": self.assessment_id or "axis_default",
            "claim_revision_ref": _ref_dict(self.claim_revision_ref),
            "assessment_input_history_cut": dict(self.assessment_input_history_cut),
            "assessment_policy_ref": _ref_dict(self.assessment_policy_ref),
            "axis": self.axis,
            "epistemic_outcome": self.epistemic_outcome,
            "method": self.method,
            "evidence_qualification_refs": list(self.evidence_qualification_refs),
        }
        if self.method_or_characterization_refs:
            data["method_or_characterization_refs"] = [_ref_dict(r) for r in self.method_or_characterization_refs]
        return data

    def as_object(self) -> CanonicalObject:
        lid = self.assessment_id if (self.assessment_id and self.assessment_id.startswith("finding_axis_assessment_")) else None
        return CanonicalObject(
            "finding_axis_assessment", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class FindingAdjudicationDecision:
    claim_revision_ref: Any
    input_history_cut: dict
    adjudicator_ref: Any
    mechanism_assessment_ref: Any
    reachability_assessment_ref: Any
    impact_assessment_ref: Any
    severity_assessment_ref: Any
    lifecycle_status: str = "CONFIRMED_CURRENT"
    evidence_qualification_refs: Sequence[Any] = ()
    previous_adjudication_decision_ref: Any = None
    corpus_snapshot_refs: Sequence[Any] = ()
    knowledge_state_refs: Sequence[Any] = ()
    decision_id: str | None = None

    def __post_init__(self):
        if self.decision_id is None:
            object.__setattr__(self, "decision_id", new_id("finding_adjudication_decision"))
        elif self.decision_id.startswith("finding_adjudication_decision_"):
            validate_id(self.decision_id, "finding_adjudication_decision")

        if self.lifecycle_status not in FINDING_LIFECYCLE_STATUSES:
            raise ValidationError("INVALID_LIFECYCLE_STATUS", str(self.lifecycle_status))

        object.__setattr__(
            self, "evidence_qualification_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.evidence_qualification_refs]))
        )

    def body(self) -> dict:
        data = {
            "decision_id": self.decision_id or "decision_default",
            "claim_revision_ref": _ref_dict(self.claim_revision_ref),
            "input_history_cut": dict(self.input_history_cut),
            "adjudicator_ref": _ref_dict(self.adjudicator_ref),
            "mechanism_assessment_ref": _ref_dict(self.mechanism_assessment_ref),
            "reachability_assessment_ref": _ref_dict(self.reachability_assessment_ref),
            "impact_assessment_ref": _ref_dict(self.impact_assessment_ref),
            "severity_assessment_ref": _ref_dict(self.severity_assessment_ref),
            "lifecycle_status": self.lifecycle_status,
            "evidence_qualification_refs": list(self.evidence_qualification_refs),
        }
        if self.previous_adjudication_decision_ref is not None:
            data["previous_adjudication_decision_ref"] = _ref_dict(self.previous_adjudication_decision_ref)
        if self.corpus_snapshot_refs:
            data["corpus_snapshot_refs"] = [_ref_dict(r) for r in self.corpus_snapshot_refs]
        if self.knowledge_state_refs:
            data["knowledge_state_refs"] = [_ref_dict(r) for r in self.knowledge_state_refs]
        return data

    def as_object(self) -> CanonicalObject:
        lid = self.decision_id if (self.decision_id and self.decision_id.startswith("finding_adjudication_decision_")) else None
        return CanonicalObject(
            "finding_adjudication_decision", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class RootCauseRevision:
    source_generation_ref: Any
    membership_edges: Sequence[dict] = ()
    predecessor_root_cause_refs: Sequence[Any] = ()
    root_cause_id: str | None = None
    root_cause_revision: str = "1"

    def __post_init__(self):
        if self.root_cause_id is None:
            object.__setattr__(self, "root_cause_id", new_id("root_cause_revision"))
        elif self.root_cause_id.startswith("root_cause_revision_"):
            validate_id(self.root_cause_id, "root_cause_revision")

        sorted_edges = sort_membership_edges(self.membership_edges)
        object.__setattr__(self, "membership_edges", tuple(sorted_edges))
        object.__setattr__(
            self, "predecessor_root_cause_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.predecessor_root_cause_refs]))
        )

    def body(self) -> dict:
        return {
            "root_cause_id": self.root_cause_id or "root_cause_default",
            "root_cause_revision": str(self.root_cause_revision),
            "source_generation_ref": _ref_dict(self.source_generation_ref),
            "membership_edges": list(self.membership_edges),
            "predecessor_root_cause_refs": list(self.predecessor_root_cause_refs),
        }

    def as_object(self) -> CanonicalObject:
        lid = self.root_cause_id if (self.root_cause_id and self.root_cause_id.startswith("root_cause_revision_")) else None
        return CanonicalObject(
            "root_cause_revision", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class ContradictionRevision:
    """Versioned, scope-aware contradiction state.

    R5.3 canonical contract:
    - exact claim revisions on both/all sides (2..N);
    - supporting/opposing qualified evidence kept separate;
    - predecessor and resolution references are backward-only;
    - resolution_decision_ref is legal only on a successor revision.
    """
    claim_revision_refs: Sequence[Any]
    scope: Mapping[str, Any]
    positions: Sequence[Any]
    supporting_evidence_qualification_refs: Sequence[Any]
    opposing_evidence_qualification_refs: Sequence[Any]
    failure_assumption_differences: Sequence[Any]
    environment_input_model_differences: Sequence[Any]
    required_falsifier: Any
    status: str = "OPEN"
    predecessor_contradiction_revision_ref: Any = None
    resolution_decision_ref: Any = None
    contradiction_id: str | None = None
    contradiction_revision: str = "1"

    def __post_init__(self):
        if self.contradiction_id is None:
            object.__setattr__(
                self,
                "contradiction_id",
                new_id("contradiction_revision"),
            )
        elif self.contradiction_id.startswith("contradiction_revision_"):
            validate_id(
                self.contradiction_id,
                "contradiction_revision",
            )

        if self.status not in CONTRADICTION_STATUSES:
            raise ValidationError(
                "INVALID_CONTRADICTION_STATUS",
                str(self.status),
            )
        if not isinstance(self.scope, Mapping):
            raise ValidationError("CONTRADICTION_SCOPE_REQUIRED")
        if not isinstance(self.positions, (list, tuple)):
            raise ValidationError("CONTRADICTION_POSITIONS_REQUIRED")
        if not isinstance(
            self.failure_assumption_differences,
            (list, tuple),
        ):
            raise ValidationError(
                "CONTRADICTION_FAILURE_ASSUMPTIONS_REQUIRED"
            )
        if not isinstance(
            self.environment_input_model_differences,
            (list, tuple),
        ):
            raise ValidationError(
                "CONTRADICTION_ENVIRONMENT_DIFFERENCES_REQUIRED"
            )
        if self.required_falsifier is None:
            raise ValidationError(
                "CONTRADICTION_REQUIRED_FALSIFIER_REQUIRED"
            )

        claims = tuple(
            canonical_reference_set(
                [_ref_dict(r) for r in self.claim_revision_refs]
            )
        )
        if len(claims) < 2:
            raise ValidationError(
                "CONTRADICTION_REQUIRES_TWO_CLAIMS"
            )
        if any(
            ref.get("kind") != "finding_claim_revision"
            for ref in claims
        ):
            raise ValidationError(
                "CONTRADICTION_CLAIM_REF_KIND_INVALID"
            )
        object.__setattr__(
            self,
            "claim_revision_refs",
            claims,
        )
        object.__setattr__(
            self,
            "supporting_evidence_qualification_refs",
            tuple(
                canonical_reference_set(
                    [
                        _ref_dict(r)
                        for r in self.supporting_evidence_qualification_refs
                    ]
                )
            ),
        )
        object.__setattr__(
            self,
            "opposing_evidence_qualification_refs",
            tuple(
                canonical_reference_set(
                    [
                        _ref_dict(r)
                        for r in self.opposing_evidence_qualification_refs
                    ]
                )
            ),
        )

        if self.resolution_decision_ref is not None:
            if self.predecessor_contradiction_revision_ref is None:
                raise ValidationError(
                    "CONTRADICTION_RESOLUTION_SUCCESSOR_REQUIRED"
                )
            if self.status not in {
                "RESOLVED_SCOPED",
                "RESOLVED_FULL",
                "BLOCKED",
            }:
                raise ValidationError(
                    "CONTRADICTION_RESOLUTION_STATUS_INVALID"
                )

    def body(self) -> dict:
        data = {
            "contradiction_id": (
                self.contradiction_id
                or "contradiction_default"
            ),
            "contradiction_revision": str(
                self.contradiction_revision
            ),
            "claim_revision_refs": list(
                self.claim_revision_refs
            ),
            "scope": dict(self.scope),
            "positions": list(self.positions),
            "supporting_evidence_qualification_refs": list(
                self.supporting_evidence_qualification_refs
            ),
            "opposing_evidence_qualification_refs": list(
                self.opposing_evidence_qualification_refs
            ),
            "failure_assumption_differences": list(
                self.failure_assumption_differences
            ),
            "environment_input_model_differences": list(
                self.environment_input_model_differences
            ),
            "required_falsifier": self.required_falsifier,
            "status": self.status,
        }
        if self.predecessor_contradiction_revision_ref is not None:
            data[
                "predecessor_contradiction_revision_ref"
            ] = _ref_dict(
                self.predecessor_contradiction_revision_ref
            )
        if self.resolution_decision_ref is not None:
            data["resolution_decision_ref"] = _ref_dict(
                self.resolution_decision_ref
            )
        return data

    def as_object(self) -> CanonicalObject:
        lid = (
            self.contradiction_id
            if (
                self.contradiction_id
                and self.contradiction_id.startswith(
                    "contradiction_revision_"
                )
            )
            else None
        )
        return CanonicalObject(
            "contradiction_revision",
            self.body(),
            logical_id=lid,
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class ContradictionResolutionDecision:
    """Resolution decision over one already-accepted contradiction revision."""
    contradiction_prior_revision_ref: Any
    resolution_input_history_cut: dict
    resolved_scope: Mapping[str, Any]
    resolution_kind: str
    basis_refs: Sequence[Any]
    resulting_status: str
    resolution_decision_id: str | None = None
    resolved_by_majority_vote: bool = False

    def __post_init__(self):
        if self.resolved_by_majority_vote:
            raise ValidationError(
                "MAJORITY_VOTE_FORBIDDEN",
                "Contradiction cannot be resolved by majority voting",
            )
        if self.resolution_decision_id is None:
            object.__setattr__(
                self,
                "resolution_decision_id",
                new_id(
                    "contradiction_resolution_decision"
                ),
            )
        elif self.resolution_decision_id.startswith(
            "contradiction_resolution_decision_"
        ):
            validate_id(
                self.resolution_decision_id,
                "contradiction_resolution_decision",
            )
        if self.resolution_kind not in (
            CONTRADICTION_RESOLUTION_KINDS
        ):
            raise ValidationError(
                "INVALID_CONTRADICTION_RESOLUTION_KIND",
                self.resolution_kind,
            )
        if self.resulting_status not in (
            CONTRADICTION_RESOLUTION_RESULTS
        ):
            raise ValidationError(
                "INVALID_CONTRADICTION_RESOLUTION_STATUS",
                self.resulting_status,
            )
        if not isinstance(
            self.resolution_input_history_cut,
            dict,
        ):
            raise ValidationError(
                "CONTRADICTION_RESOLUTION_CUT_REQUIRED"
            )
        if not isinstance(self.resolved_scope, Mapping):
            raise ValidationError(
                "CONTRADICTION_RESOLVED_SCOPE_REQUIRED"
            )

        basis = tuple(
            canonical_reference_set(
                [_ref_dict(r) for r in self.basis_refs]
            )
        )
        if not basis:
            raise ValidationError(
                "CONTRADICTION_RESOLUTION_BASIS_REQUIRED"
            )
        object.__setattr__(self, "basis_refs", basis)

    def body(self) -> dict:
        return {
            "resolution_decision_id": (
                self.resolution_decision_id
                or "resolution_default"
            ),
            "contradiction_prior_revision_ref": _ref_dict(
                self.contradiction_prior_revision_ref
            ),
            "resolution_input_history_cut": dict(
                self.resolution_input_history_cut
            ),
            "resolved_scope": dict(self.resolved_scope),
            "resolution_kind": self.resolution_kind,
            "basis_refs": list(self.basis_refs),
            "resulting_status": self.resulting_status,
        }

    def as_object(self) -> CanonicalObject:
        lid = (
            self.resolution_decision_id
            if (
                self.resolution_decision_id
                and self.resolution_decision_id.startswith(
                    "contradiction_resolution_decision_"
                )
            )
            else None
        )
        return CanonicalObject(
            "contradiction_resolution_decision",
            self.body(),
            logical_id=lid,
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


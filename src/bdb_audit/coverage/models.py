"""R5.3.1 Invariant and Coverage Obligation domain models (M15/M16)."""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.hashing import DIGEST_PROFILE, object_digest
from ..core.ids import new_id, validate_id
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, ObjectRef

INVARIANT_STATUSES = {"ACTIVE", "SUPERSEDED", "RETIRED", "INVALIDATED"}
INVARIANT_CATEGORIES = {
    "AUTHORITY", "DURABILITY", "ATOMICITY", "CONSISTENCY", "COMPLETENESS",
    "PARSING", "RECOVERY", "CONCURRENCY", "RESOURCE_OWNERSHIP", "SECURITY_BOUNDARY",
    "PRIVACY", "SUPPLY_CHAIN", "RELEASE_ASSURANCE", "STATE_CONSISTENCY",
}
MATERIALITY_RESULTS = {"MATERIAL", "NON_MATERIAL", "UNKNOWN", "CONFLICTED"}
QUALIFICATION_STATUSES = {"UNASSESSED", "IN_PROGRESS", "QUALIFIED", "BLOCKED", "STALE"}
SUBSTANTIVE_OUTCOMES = {"NO_VIOLATION_OBSERVED", "VIOLATION_CONFIRMED", "INCONCLUSIVE"}
APPLICABILITY_RESULTS = {"APPLICABLE", "NOT_APPLICABLE", "UNKNOWN", "CONFLICTED"}


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


def _ref_kind(ref_or_obj: Any) -> str:
    if isinstance(ref_or_obj, (ObjectRef, CanonicalObject)):
        return ref_or_obj.kind
    if isinstance(ref_or_obj, dict):
        return ref_or_obj.get("kind", "")
    if isinstance(ref_or_obj, str) and ":" in ref_or_obj:
        return ref_or_obj.split(":", 1)[0]
    return ""


@dataclass(frozen=True)
class InvariantRevision:
    invariant_id: str | None = None
    invariant_revision: str = "1"
    invariant_input_history_cut: dict = field(default_factory=lambda: {"tag": "EMPTY_HISTORY"})
    source_generation_ref: Any = None
    statement: str = ""
    activation_policy_ref: Any = None
    target_scope_refs: Sequence[Any] = ()
    category: str = "STATE_CONSISTENCY"
    origin: str = "SPECIFICATION"
    status: str = "ACTIVE"
    materiality_assessment_ref: Any = None

    def __post_init__(self):
        # R5N67: Invariant cannot point forward to MaterialityAssessment
        if self.materiality_assessment_ref is not None:
            raise ValidationError("MATERIALITY_BACKLINK_CYCLE_FORBIDDEN", "Invariant cannot point to materiality assessment")
        for ref_item in self.target_scope_refs:
            if _ref_kind(ref_item) == "materiality_assessment":
                raise ValidationError("MATERIALITY_BACKLINK_CYCLE_FORBIDDEN", "Target scope cannot be materiality assessment")

        if self.status not in INVARIANT_STATUSES:
            raise ValidationError("INVALID_INVARIANT_STATUS", str(self.status))

        if self.category not in INVARIANT_CATEGORIES and not self.category.startswith("CUSTOM_"):
            raise ValidationError("INVALID_INVARIANT_CATEGORY", str(self.category))

        object.__setattr__(
            self,
            "target_scope_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.target_scope_refs])),
        )

    def body(self) -> dict:
        return {
            "invariant_id": self.invariant_id or "invariant_default",
            "invariant_revision": str(self.invariant_revision),
            "invariant_input_history_cut": dict(self.invariant_input_history_cut),
            "source_generation_ref": _ref_dict(self.source_generation_ref),
            "statement": self.statement,
            "target_scope_refs": list(self.target_scope_refs),
            "category": self.category,
            "origin": self.origin,
            "activation_policy_ref": _ref_dict(self.activation_policy_ref),
            "status": self.status,
        }

    def as_object(self) -> CanonicalObject:
        lid = self.invariant_id if (self.invariant_id and self.invariant_id.startswith("invariant_revision_")) else None
        return CanonicalObject(
            "invariant_revision", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class MaterialityAssessment:
    materiality_assessment_id: str
    subject_ref: Any
    assessment_input_history_cut: dict
    materiality_policy_ref: Any
    scope: str | dict
    result: str
    rationale: str
    supporting_fact_refs: Sequence[Any] = ()
    reason_codes: Sequence[str] = ()

    def __post_init__(self):
        validate_id(self.materiality_assessment_id, "materiality_assessment")
        if self.result not in MATERIALITY_RESULTS:
            raise ValidationError("INVALID_MATERIALITY_RESULT", str(self.result))

        object.__setattr__(
            self,
            "supporting_fact_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.supporting_fact_refs])),
        )
        object.__setattr__(
            self,
            "reason_codes",
            tuple(_canonical_strings(self.reason_codes, "reason_codes")),
        )

    def body(self) -> dict:
        return {
            "materiality_assessment_id": self.materiality_assessment_id,
            "subject_ref": _ref_dict(self.subject_ref),
            "assessment_input_history_cut": dict(self.assessment_input_history_cut),
            "materiality_policy_ref": _ref_dict(self.materiality_policy_ref),
            "scope": self.scope if isinstance(self.scope, str) else dict(self.scope),
            "supporting_fact_refs": list(self.supporting_fact_refs),
            "result": self.result,
            "rationale": self.rationale,
            "reason_codes": list(self.reason_codes),
        }

    def as_object(self) -> CanonicalObject:
        return CanonicalObject(
            "materiality_assessment", self.body(), logical_id=self.materiality_assessment_id
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class CoverageObligationKey:
    source_generation_ref: Any
    target_scope_or_surface_ref: Any
    invariant_logical_id: str
    scenario_class: str
    environment_profile_ref: Any
    policy_obligation_key: str

    def body(self) -> dict:
        return {
            "source_generation_ref": _ref_dict(self.source_generation_ref),
            "target_scope_or_surface_ref": _ref_dict(self.target_scope_or_surface_ref),
            "invariant_logical_id": self.invariant_logical_id,
            "scenario_class": self.scenario_class,
            "environment_profile_ref": _ref_dict(self.environment_profile_ref),
            "policy_obligation_key": self.policy_obligation_key,
        }

    def as_object(self) -> CanonicalObject:
        return CanonicalObject("coverage_obligation_key", self.body())

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class CoverageObligation:
    obligation_id: str
    obligation_revision: str
    obligation_input_history_cut: dict | None
    source_generation_ref: Any
    target_scope_or_surface_ref: Any
    invariant_revision_ref: Any
    scenario_class: str
    environment_profile_ref: Any
    materiality_assessment_ref: Any
    required_oracle_independence_predicate_ref: Any
    acceptance_predicate_ref: Any
    applicability_predicate_ref: Any
    policy_obligation_key: str
    governing_policy_ref: Any
    origin_ref: Any
    required_technique_or_capability_refs: Sequence[Any] = ()
    falsifier_or_control_requirements: Sequence[Any] = ()
    materiality: str | None = None  # Diagnostic parameter only; forbidden in canonical body (R5N69)

    def __post_init__(self):
        validate_id(self.obligation_id, "coverage_obligation")

        # R5N54: Coverage obligation requires exact input history cut
        if self.obligation_input_history_cut is None:
            raise ValidationError("COVERAGE_OBLIGATION_HISTORY_CONTEXT_UNBOUND", "obligation_input_history_cut cannot be null")

        # R5N69: Materiality must bind exact assessment ref; no scalar duplicate in body
        if self.materiality is not None:
            raise ValidationError("COVERAGE_SCALAR_MATERIALITY_FORBIDDEN", "Coverage obligation cannot carry scalar materiality")
        if self.materiality_assessment_ref is None:
            raise ValidationError("MATERIALITY_ASSESSMENT_REF_REQUIRED")

        object.__setattr__(
            self,
            "required_technique_or_capability_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.required_technique_or_capability_refs])),
        )
        object.__setattr__(
            self,
            "falsifier_or_control_requirements",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.falsifier_or_control_requirements])),
        )

    def body(self) -> dict:
        return {
            "obligation_id": self.obligation_id,
            "obligation_revision": str(self.obligation_revision),
            "obligation_input_history_cut": dict(self.obligation_input_history_cut),
            "source_generation_ref": _ref_dict(self.source_generation_ref),
            "target_scope_or_surface_ref": _ref_dict(self.target_scope_or_surface_ref),
            "invariant_revision_ref": _ref_dict(self.invariant_revision_ref),
            "scenario_class": self.scenario_class,
            "environment_profile_ref": _ref_dict(self.environment_profile_ref),
            "materiality_assessment_ref": _ref_dict(self.materiality_assessment_ref),
            "required_technique_or_capability_refs": list(self.required_technique_or_capability_refs),
            "required_oracle_independence_predicate_ref": _ref_dict(self.required_oracle_independence_predicate_ref),
            "acceptance_predicate_ref": _ref_dict(self.acceptance_predicate_ref),
            "falsifier_or_control_requirements": list(self.falsifier_or_control_requirements),
            "applicability_predicate_ref": _ref_dict(self.applicability_predicate_ref),
            "policy_obligation_key": self.policy_obligation_key,
            "governing_policy_ref": _ref_dict(self.governing_policy_ref),
            "origin_ref": _ref_dict(self.origin_ref),
        }

    def as_object(self) -> CanonicalObject:
        return CanonicalObject(
            "coverage_obligation", self.body(), logical_id=self.obligation_id
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class CoverageObligationQualification:
    qualification_id: str
    obligation_revision_ref: Any
    input_history_cut: dict
    qualification_status: str
    substantive_outcome: str | None = None
    evidence_qualification_refs: Sequence[Any] = ()
    applicability_decision_ref: Any = None
    waiver_decision_ref: Any = None
    contradiction_refs: Sequence[Any] = ()
    reason_codes: Sequence[str] = ()

    def __post_init__(self):
        validate_id(self.qualification_id, "coverage_obligation_qualification")
        if self.qualification_status not in QUALIFICATION_STATUSES:
            raise ValidationError("INVALID_QUALIFICATION_STATUS", str(self.qualification_status))
        if self.substantive_outcome is not None and self.substantive_outcome not in SUBSTANTIVE_OUTCOMES:
            raise ValidationError("INVALID_SUBSTANTIVE_OUTCOME", str(self.substantive_outcome))

        # R5N55: Waiver must be approval_decision
        if self.waiver_decision_ref is not None:
            kind = _ref_kind(self.waiver_decision_ref)
            if kind != "approval_decision":
                raise ValidationError("SECOND_COVERAGE_WAIVER_AUTHORITY", f"Waiver ref must be approval_decision, got {kind}")

        object.__setattr__(
            self,
            "evidence_qualification_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.evidence_qualification_refs])),
        )
        object.__setattr__(
            self,
            "contradiction_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.contradiction_refs])),
        )
        object.__setattr__(
            self,
            "reason_codes",
            tuple(_canonical_strings(self.reason_codes, "reason_codes")),
        )

    def body(self) -> dict:
        data = {
            "qualification_id": self.qualification_id,
            "obligation_revision_ref": _ref_dict(self.obligation_revision_ref),
            "input_history_cut": dict(self.input_history_cut),
            "qualification_status": self.qualification_status,
            "evidence_qualification_refs": list(self.evidence_qualification_refs),
            "contradiction_refs": list(self.contradiction_refs),
            "reason_codes": list(self.reason_codes),
        }
        if self.substantive_outcome is not None:
            data["substantive_outcome"] = self.substantive_outcome
        if self.applicability_decision_ref is not None:
            data["applicability_decision_ref"] = _ref_dict(self.applicability_decision_ref)
        if self.waiver_decision_ref is not None:
            data["waiver_decision_ref"] = _ref_dict(self.waiver_decision_ref)
        return data

    def as_object(self) -> CanonicalObject:
        return CanonicalObject(
            "coverage_obligation_qualification", self.body(), logical_id=self.qualification_id
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class ObligationApplicabilityDecision:
    applicability_decision_id: str
    obligation_revision_ref: Any
    assessment_input_history_cut: dict
    applicability_policy_ref: Any
    scope: str | dict
    result: str
    supporting_evidence_refs: Sequence[Any] = ()
    reason_codes: Sequence[str] = ()

    def __post_init__(self):
        validate_id(self.applicability_decision_id, "obligation_applicability_decision")
        if self.result not in APPLICABILITY_RESULTS:
            raise ValidationError("INVALID_APPLICABILITY_RESULT", str(self.result))

        object.__setattr__(
            self,
            "supporting_evidence_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.supporting_evidence_refs])),
        )
        object.__setattr__(
            self,
            "reason_codes",
            tuple(_canonical_strings(self.reason_codes, "reason_codes")),
        )

    def body(self) -> dict:
        return {
            "applicability_decision_id": self.applicability_decision_id,
            "obligation_revision_ref": _ref_dict(self.obligation_revision_ref),
            "assessment_input_history_cut": dict(self.assessment_input_history_cut),
            "applicability_policy_ref": _ref_dict(self.applicability_policy_ref),
            "scope": self.scope if isinstance(self.scope, str) else dict(self.scope),
            "supporting_evidence_refs": list(self.supporting_evidence_refs),
            "result": self.result,
            "reason_codes": list(self.reason_codes),
        }

    def as_object(self) -> CanonicalObject:
        return CanonicalObject(
            "obligation_applicability_decision", self.body(), logical_id=self.applicability_decision_id
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class ApprovalDecision:
    decision_id: str
    decision_type: str
    decision: str
    actor_ref: Any
    actor_authority_ref: Any
    input_history_cut: dict
    related_refs: Sequence[Any] = ()
    rationale: str = ""
    reason_codes: Sequence[str] = ()

    def __post_init__(self):
        validate_id(self.decision_id, "approval_decision")
        if self.decision not in ("APPROVED", "REJECTED"):
            raise ValidationError("INVALID_APPROVAL_DECISION", str(self.decision))

        object.__setattr__(
            self,
            "related_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.related_refs])),
        )
        object.__setattr__(
            self,
            "reason_codes",
            tuple(_canonical_strings(self.reason_codes, "reason_codes")),
        )

    def body(self) -> dict:
        data = {
            "decision_id": self.decision_id,
            "decision_type": self.decision_type,
            "decision": self.decision,
            "actor_ref": _ref_dict(self.actor_ref),
            "actor_authority_ref": _ref_dict(self.actor_authority_ref),
            "input_history_cut": dict(self.input_history_cut),
            "related_refs": list(self.related_refs),
            "reason_codes": list(self.reason_codes),
        }
        if self.rationale:
            data["rationale"] = self.rationale
        return data

    def as_object(self) -> CanonicalObject:
        return CanonicalObject(
            "approval_decision", self.body(), logical_id=self.decision_id
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest

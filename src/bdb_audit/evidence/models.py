"""R5.3.1 Evidence domain models (M20)."""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.hashing import DIGEST_PROFILE, object_digest
from ..core.ids import new_id, validate_id
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, ObjectRef

INDEPENDENCE_RESULTS = {"INDEPENDENT", "SHARED_DEPENDENCY", "CONFLICTED", "REJECTED"}
APPLICABILITY_STATUSES = {"ACTIVE", "SCOPED", "STALE", "INVALIDATED", "BLOCKED", "CONFLICTED"}
QUALIFICATION_RESULTS = {"SUPPORTS", "REFUTES", "INCONCLUSIVE", "INVALID"}


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


@dataclass(frozen=True)
class Observation:
    execution_descriptor_ref: Any
    raw_observation_ref: Any
    observation_channel: str
    observed_at: str
    observation_id: str | None = None

    def __post_init__(self):
        if self.observation_id is None:
            object.__setattr__(self, "observation_id", new_id("observation"))
        elif self.observation_id.startswith("observation_"):
            validate_id(self.observation_id, "observation")

    def body(self) -> dict:
        return {
            "observation_id": self.observation_id or "obs_default",
            "execution_descriptor_ref": _ref_dict(self.execution_descriptor_ref),
            "raw_observation_ref": _ref_dict(self.raw_observation_ref) if isinstance(self.raw_observation_ref, (dict, ObjectRef, CanonicalObject)) else str(self.raw_observation_ref),
            "observation_channel": self.observation_channel,
            "observed_at": self.observed_at,
        }

    def as_object(self) -> CanonicalObject:
        lid = self.observation_id if (self.observation_id and self.observation_id.startswith("observation_")) else None
        return CanonicalObject(
            "observation", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class DependencyIndependenceAssessment:
    claim_revision_ref: Any
    assessment_input_history_cut: dict
    dependency_graph_ref: Any
    independence_policy_ref: Any
    result: str
    observer_path_refs: Sequence[Any] = ()
    shared_dependency_refs: Sequence[Any] = ()
    independent_dependency_refs: Sequence[Any] = ()
    reason_codes: Sequence[str] = ()
    assessment_id: str | None = None

    def __post_init__(self):
        if self.assessment_id is None:
            object.__setattr__(self, "assessment_id", new_id("dependency_independence_assessment"))
        elif self.assessment_id.startswith("dependency_independence_assessment_"):
            validate_id(self.assessment_id, "dependency_independence_assessment")

        if self.result not in INDEPENDENCE_RESULTS:
            raise ValidationError("INVALID_INDEPENDENCE_RESULT", str(self.result))

        # Adversarial rule: shared oracle/dependency cannot masquerade as independent
        shared_keys = {
            r.get("revision_digest") or r.get("logical_id") or str(r)
            for r in self.shared_dependency_refs if isinstance(r, dict)
        }
        independent_keys = {
            r.get("revision_digest") or r.get("logical_id") or str(r)
            for r in self.independent_dependency_refs if isinstance(r, dict)
        }
        if shared_keys & independent_keys and self.result == "INDEPENDENT":
            raise ValidationError("SHARED_ORACLE_INDEPENDENCE_REJECTED", "Shared dependency cannot be declared independent")

        object.__setattr__(
            self, "observer_path_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.observer_path_refs]))
        )
        object.__setattr__(
            self, "shared_dependency_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.shared_dependency_refs]))
        )
        object.__setattr__(
            self, "independent_dependency_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.independent_dependency_refs]))
        )
        object.__setattr__(
            self, "reason_codes",
            tuple(_canonical_strings(self.reason_codes, "reason_codes"))
        )

    def body(self) -> dict:
        return {
            "assessment_id": self.assessment_id or "assessment_default",
            "claim_revision_ref": _ref_dict(self.claim_revision_ref),
            "assessment_input_history_cut": dict(self.assessment_input_history_cut),
            "dependency_graph_ref": _ref_dict(self.dependency_graph_ref),
            "observer_path_refs": list(self.observer_path_refs),
            "shared_dependency_refs": list(self.shared_dependency_refs),
            "independent_dependency_refs": list(self.independent_dependency_refs),
            "independence_policy_ref": _ref_dict(self.independence_policy_ref),
            "result": self.result,
            "reason_codes": list(self.reason_codes),
        }

    def as_object(self) -> CanonicalObject:
        lid = self.assessment_id if (self.assessment_id and self.assessment_id.startswith("dependency_independence_assessment_")) else None
        return CanonicalObject(
            "dependency_independence_assessment", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class EvidenceApplicabilityAssessment:
    claim_revision_ref: Any
    assessment_input_history_cut: dict
    dependency_set_ref: Any
    environment_ref: Any
    execution_variant_ref: Any
    harness_ref: Any
    subject_baseline_ref: Any
    status: str = "ACTIVE"
    previous_assessment_ref: Any = None
    fixture_refs: Sequence[Any] = ()
    reason_codes: Sequence[str] = ()
    assessment_id: str | None = None

    def __post_init__(self):
        if self.assessment_id is None:
            object.__setattr__(self, "assessment_id", new_id("evidence_applicability_assessment"))
        elif self.assessment_id.startswith("evidence_applicability_assessment_"):
            validate_id(self.assessment_id, "evidence_applicability_assessment")

        if self.status not in APPLICABILITY_STATUSES:
            raise ValidationError("INVALID_APPLICABILITY_STATUS", str(self.status))

        object.__setattr__(
            self, "fixture_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.fixture_refs]))
        )
        object.__setattr__(
            self, "reason_codes",
            tuple(_canonical_strings(self.reason_codes, "reason_codes"))
        )

    def body(self) -> dict:
        data = {
            "assessment_id": self.assessment_id or "assessment_default",
            "claim_revision_ref": _ref_dict(self.claim_revision_ref),
            "assessment_input_history_cut": dict(self.assessment_input_history_cut),
            "dependency_set_ref": _ref_dict(self.dependency_set_ref),
            "environment_ref": _ref_dict(self.environment_ref),
            "execution_variant_ref": _ref_dict(self.execution_variant_ref),
            "harness_ref": _ref_dict(self.harness_ref),
            "subject_baseline_ref": _ref_dict(self.subject_baseline_ref),
            "status": self.status,
            "reason_codes": list(self.reason_codes),
        }
        if self.previous_assessment_ref is not None:
            data["previous_assessment_ref"] = _ref_dict(self.previous_assessment_ref)
        if self.fixture_refs:
            data["fixture_refs"] = list(self.fixture_refs)
        return data

    def as_object(self) -> CanonicalObject:
        lid = self.assessment_id if (self.assessment_id and self.assessment_id.startswith("evidence_applicability_assessment_")) else None
        return CanonicalObject(
            "evidence_applicability_assessment", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class EvidenceQualificationAssessment:
    claim_revision_ref: Any
    dependency_graph_ref: Any
    independence_assessment_ref: Any
    applicability_assessment_ref: Any
    observation_refs: Sequence[Any]
    input_history_cut: dict | None = None
    assessment_input_history_cut: dict | None = None
    result: str = "SUPPORTS"
    controls_refs: Sequence[Any] = ()
    reason_codes: Sequence[str] = ()
    assessment_id: str | None = None

    def __post_init__(self):
        cut = self.input_history_cut or self.assessment_input_history_cut
        if cut is None:
            raise ValidationError("HISTORY_CUT_REQUIRED")
        object.__setattr__(self, "input_history_cut", cut)
        object.__setattr__(self, "assessment_input_history_cut", cut)

        if self.assessment_id is None:
            object.__setattr__(self, "assessment_id", new_id("evidence_qualification_assessment"))
        elif self.assessment_id.startswith("evidence_qualification_assessment_"):
            validate_id(self.assessment_id, "evidence_qualification_assessment")

        if self.result not in QUALIFICATION_RESULTS:
            raise ValidationError("INVALID_QUALIFICATION_RESULT", str(self.result))

        object.__setattr__(
            self, "observation_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.observation_refs]))
        )
        object.__setattr__(
            self, "controls_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.controls_refs]))
        )
        object.__setattr__(
            self, "reason_codes",
            tuple(_canonical_strings(self.reason_codes, "reason_codes"))
        )

    def body(self) -> dict:
        data = {
            "assessment_id": self.assessment_id or "qualification_default",
            "claim_revision_ref": _ref_dict(self.claim_revision_ref),
            "input_history_cut": dict(self.input_history_cut),
            "dependency_graph_ref": _ref_dict(self.dependency_graph_ref),
            "independence_assessment_ref": _ref_dict(self.independence_assessment_ref),
            "applicability_assessment_ref": _ref_dict(self.applicability_assessment_ref),
            "observation_refs": list(self.observation_refs),
            "result": self.result,
            "reason_codes": list(self.reason_codes),
        }
        if self.controls_refs:
            data["controls_refs"] = list(self.controls_refs)
        return data

    def as_object(self) -> CanonicalObject:
        lid = self.assessment_id if (self.assessment_id and self.assessment_id.startswith("evidence_qualification_assessment_")) else None
        return CanonicalObject(
            "evidence_qualification_assessment", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class EvidenceInvalidation:
    affected_evidence_or_qualification_refs: Sequence[Any]
    dependency_ref: Any
    invalidation_input_history_cut: dict
    propagation_policy_ref: Any
    reason_codes: Sequence[str] = ()
    invalidation_id: str | None = None

    def __post_init__(self):
        if self.invalidation_id is None:
            object.__setattr__(self, "invalidation_id", new_id("evidence_invalidation"))
        elif self.invalidation_id.startswith("evidence_invalidation_"):
            validate_id(self.invalidation_id, "evidence_invalidation")

        object.__setattr__(
            self, "affected_evidence_or_qualification_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.affected_evidence_or_qualification_refs]))
        )
        object.__setattr__(
            self, "reason_codes",
            tuple(_canonical_strings(self.reason_codes, "reason_codes"))
        )

    def body(self) -> dict:
        return {
            "invalidation_id": self.invalidation_id or "invalidation_default",
            "affected_evidence_or_qualification_refs": list(self.affected_evidence_or_qualification_refs),
            "dependency_ref": _ref_dict(self.dependency_ref),
            "invalidation_input_history_cut": dict(self.invalidation_input_history_cut),
            "propagation_policy_ref": _ref_dict(self.propagation_policy_ref),
            "reason_codes": list(self.reason_codes),
        }

    def as_object(self) -> CanonicalObject:
        lid = self.invalidation_id if (self.invalidation_id and self.invalidation_id.startswith("evidence_invalidation_")) else None
        return CanonicalObject(
            "evidence_invalidation", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest

"""R5.3.1 Hypothesis and Discovery Gap domain models (M17/M18)."""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.hashing import DIGEST_PROFILE, object_digest
from ..core.ids import new_id, validate_id
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, ObjectRef

HYPOTHESIS_STATUSES = {
    "PROPOSED", "PREREGISTERED", "TESTING", "CONFIRMED", "REJECTED", "UNRESOLVED", "BLOCKED"
}
PLANNING_MODES = {"PREREGISTERED", "EXPLORATORY", "LEGACY"}


def _ref_dict(ref_or_obj: Any) -> dict:
    if isinstance(ref_or_obj, ObjectRef):
        return ref_or_obj.as_dict()
    if isinstance(ref_or_obj, CanonicalObject):
        return ref_or_obj.as_ref().as_dict()
    if isinstance(ref_or_obj, dict):
        return ref_or_obj
    raise ValidationError("INVALID_REFERENCE")


@dataclass(frozen=True)
class HypothesisRevision:
    source_generation_ref: Any
    statement: str
    input_history_cut: dict
    hypothesis_id: str | None = None
    hypothesis_revision: str = "1"
    scope_refs: Sequence[Any] = ()
    invariant_refs: Sequence[Any] = ()
    obligation_refs: Sequence[Any] = ()
    origin_discovery_ref: Any = None
    planning_mode: str = "PREREGISTERED"
    status: str = "PROPOSED"

    def __post_init__(self):
        if self.hypothesis_id is None:
            object.__setattr__(self, "hypothesis_id", new_id("hypothesis_revision"))
        elif self.hypothesis_id.startswith("hypothesis_revision_"):
            validate_id(self.hypothesis_id, "hypothesis_revision")

        if self.status not in HYPOTHESIS_STATUSES:
            raise ValidationError("INVALID_HYPOTHESIS_STATUS", str(self.status))
        if self.planning_mode not in PLANNING_MODES:
            raise ValidationError("INVALID_PLANNING_MODE", str(self.planning_mode))

        object.__setattr__(
            self, "scope_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.scope_refs]))
        )
        object.__setattr__(
            self, "invariant_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.invariant_refs]))
        )
        object.__setattr__(
            self, "obligation_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.obligation_refs]))
        )

    def body(self) -> dict:
        data = {
            "hypothesis_id": self.hypothesis_id or "hypothesis_default",
            "hypothesis_revision": str(self.hypothesis_revision),
            "source_generation_ref": _ref_dict(self.source_generation_ref),
            "statement": self.statement,
            "scope_refs": list(self.scope_refs),
            "invariant_refs": list(self.invariant_refs),
            "obligation_refs": list(self.obligation_refs),
            "planning_mode": self.planning_mode,
            "status": self.status,
            "input_history_cut": dict(self.input_history_cut),
        }
        if self.origin_discovery_ref is not None:
            data["origin_discovery_ref"] = _ref_dict(self.origin_discovery_ref)
        return data

    def as_object(self) -> CanonicalObject:
        lid = self.hypothesis_id if (self.hypothesis_id and self.hypothesis_id.startswith("hypothesis_revision_")) else None
        return CanonicalObject(
            "hypothesis_revision", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class DiscoveryOpportunity:
    gap_id: str
    target_scope_ref: Any
    missing_or_unsatisfied_obligation_refs: Sequence[Any]
    unknown_scope_refs: Sequence[Any]
    materiality: str
    priority_score: float
    current_history_cut: dict

    def to_dict(self) -> dict:
        return {
            "gap_id": self.gap_id,
            "target_scope_ref": _ref_dict(self.target_scope_ref),
            "missing_or_unsatisfied_obligation_refs": [_ref_dict(r) for r in self.missing_or_unsatisfied_obligation_refs],
            "unknown_scope_refs": [_ref_dict(r) for r in self.unknown_scope_refs],
            "materiality": self.materiality,
            "priority_score": self.priority_score,
            "current_history_cut": dict(self.current_history_cut),
        }

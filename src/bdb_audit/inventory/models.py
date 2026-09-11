"""R5.3.1 Surface and Inventory domain models (M14)."""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.hashing import DIGEST_PROFILE, object_digest
from ..core.ids import new_id, validate_id
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, ObjectRef

INPUT_DISPOSITION_TERMINAL = {
    "COLLECTED", "UNSUPPORTED", "EXCLUDED", "COLLECTION_FAILED", "PARSING_FAILED"
}
INPUT_DISPOSITION_INTERMEDIATE = {"PROVISIONAL"}
INPUT_DISPOSITIONS = INPUT_DISPOSITION_TERMINAL | INPUT_DISPOSITION_INTERMEDIATE

SCOPE_STATES = {
    "KNOWN_SURFACE", "KNOWN_UNOBSERVED_SCOPE", "UNSUPPORTED_SCOPE",
    "EXCLUDED_SCOPE", "COLLECTION_FAILED", "PARSING_FAILED",
    "PROVISIONAL_SCOPE", "UNKNOWN_SCOPE",
}

SURFACE_CATEGORIES = {
    "HTTP_ROUTE", "STATE_MUTATION", "NETWORK_EGRESS", "PARSER",
    "FILE_IO", "PERSISTENCE", "CACHE", "SUBPROCESS", "CONCURRENCY",
    "TIMER_RETRY_WORKER", "AUTHORITY", "SECRET_CONFIG", "DOM_SINK",
    "EXTERNAL_CONTENT", "CI_SUPPLY_CHAIN", "TEST_ORACLE",
    "ARTIFACT_PRODUCER", "OTHER",
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


def _ref_kind(ref_or_obj: Any) -> str:
    if isinstance(ref_or_obj, (ObjectRef, CanonicalObject)):
        return ref_or_obj.kind
    if isinstance(ref_or_obj, dict):
        return ref_or_obj.get("kind", "")
    if isinstance(ref_or_obj, str) and ":" in ref_or_obj:
        return ref_or_obj.split(":", 1)[0]
    return ""


@dataclass(frozen=True)
class SurfaceKey:
    source_identity_ref: Any
    canonical_surface_category: str
    normalized_anchor_descriptor: dict

    def __post_init__(self):
        if not self.canonical_surface_category:
            raise ValidationError("SURFACE_CATEGORY_REQUIRED")
        if not isinstance(self.normalized_anchor_descriptor, dict):
            raise ValidationError("ANCHOR_DESCRIPTOR_REQUIRED")

    def body(self) -> dict:
        return {
            "source_identity_ref": _ref_dict(self.source_identity_ref),
            "canonical_surface_category": self.canonical_surface_category,
            "normalized_anchor_descriptor": dict(self.normalized_anchor_descriptor),
        }

    def as_object(self) -> CanonicalObject:
        return CanonicalObject("surface_key", self.body())

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class SurfaceRecord:
    surface_key: Any
    source_identity_ref: Any
    surface_category: str
    anchor_descriptor: dict
    provenance_refs: Sequence[Any] = ()
    identity_state: str = "STABLE"
    surface_record_id: str | None = None

    def __post_init__(self):
        if self.identity_state not in ("STABLE", "PROVISIONAL"):
            raise ValidationError("INVALID_IDENTITY_STATE")
        if self.surface_record_id is not None:
            validate_id(self.surface_record_id, "surface_record")
        object.__setattr__(
            self,
            "provenance_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.provenance_refs])),
        )

    def body(self) -> dict:
        data = {
            "surface_key": _ref_dict(self.surface_key),
            "source_identity_ref": _ref_dict(self.source_identity_ref),
            "surface_category": self.surface_category,
            "anchor_descriptor": dict(self.anchor_descriptor),
            "provenance_refs": list(self.provenance_refs),
            "identity_state": self.identity_state,
        }
        if self.surface_record_id is not None:
            data["surface_record_id"] = self.surface_record_id
        return data

    def as_object(self) -> CanonicalObject:
        return CanonicalObject(
            "surface_record", self.body(), logical_id=self.surface_record_id
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class InputDispositionRecord:
    assigned_input_ref: Any
    disposition: str
    disposition_input_history_cut: dict
    reason_codes: Sequence[str] = ()
    input_disposition_record_id: str | None = None

    def __post_init__(self):
        if self.input_disposition_record_id is None:
            object.__setattr__(self, "input_disposition_record_id", new_id("input_disposition_record"))
        else:
            validate_id(self.input_disposition_record_id, "input_disposition_record")

        # Strict separation: ScopeState values in InputDisposition are rejected
        if self.disposition in (SCOPE_STATES - INPUT_DISPOSITIONS):
            raise ValidationError("ENUM_DOMAIN_MISMATCH", f"ScopeState {self.disposition} in InputDisposition")
        if self.disposition not in INPUT_DISPOSITIONS:
            raise ValidationError("INVALID_INPUT_DISPOSITION", str(self.disposition))

        object.__setattr__(
            self,
            "reason_codes",
            tuple(_canonical_strings(self.reason_codes, "reason_codes")),
        )

    def body(self) -> dict:
        return {
            "input_disposition_record_id": self.input_disposition_record_id,
            "assigned_input_ref": _ref_dict(self.assigned_input_ref),
            "disposition": self.disposition,
            "disposition_input_history_cut": dict(self.disposition_input_history_cut),
            "reason_codes": list(self.reason_codes),
        }

    def as_object(self) -> CanonicalObject:
        return CanonicalObject(
            "input_disposition_record", self.body(), logical_id=self.input_disposition_record_id
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class ScopeStateRecord:
    scope_key: str
    state: str
    scope_state_input_history_cut: dict
    basis_refs: Sequence[Any] = ()
    scope_ref: Any = None
    scope_decision_ref: Any = None
    reason_codes: Sequence[str] = ()
    scope_state_record_id: str | None = None

    def __post_init__(self):
        if self.scope_state_record_id is None:
            object.__setattr__(self, "scope_state_record_id", new_id("scope_state_record"))
        else:
            validate_id(self.scope_state_record_id, "scope_state_record")

        # Strict separation: InputDisposition values in ScopeState are rejected
        if self.state in (INPUT_DISPOSITIONS - SCOPE_STATES):
            raise ValidationError("ENUM_DOMAIN_MISMATCH", f"InputDisposition {self.state} in ScopeState")
        if self.state not in SCOPE_STATES:
            raise ValidationError("INVALID_SCOPE_STATE", str(self.state))

        if self.state == "EXCLUDED_SCOPE" and self.scope_decision_ref is None:
            raise ValidationError("EXCLUDED_SCOPE_REQUIRES_DECISION")

        object.__setattr__(
            self,
            "basis_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.basis_refs])),
        )
        object.__setattr__(
            self,
            "reason_codes",
            tuple(_canonical_strings(self.reason_codes, "reason_codes")),
        )

    def body(self) -> dict:
        data = {
            "scope_state_record_id": self.scope_state_record_id,
            "scope_key": self.scope_key,
            "state": self.state,
            "basis_refs": list(self.basis_refs),
            "scope_state_input_history_cut": dict(self.scope_state_input_history_cut),
            "reason_codes": list(self.reason_codes),
        }
        if self.scope_ref is not None:
            data["scope_ref"] = _ref_dict(self.scope_ref)
        if self.scope_decision_ref is not None:
            data["scope_decision_ref"] = _ref_dict(self.scope_decision_ref)
        return data

    def as_object(self) -> CanonicalObject:
        return CanonicalObject(
            "scope_state_record", self.body(), logical_id=self.scope_state_record_id
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class InventoryRevision:
    inventory_id: str
    inventory_revision: str
    source_generation_ref: Any
    basis_history_cut: dict
    collector_profile_refs: Sequence[Any] = ()
    assigned_input_refs: Sequence[Any] = ()
    input_disposition_refs: Sequence[Any] = ()
    surface_refs: Sequence[Any] = ()
    scope_state_record_refs: Sequence[Any] = ()
    manual_runtime_additions: Sequence[Any] = ()
    unresolved_scope_refs: Sequence[Any] = ()

    def __post_init__(self):
        # Validate typed accounting domain separation
        for r in self.assigned_input_refs:
            kind = _ref_kind(r)
            if kind in ("input_disposition_record", "scope_state_record"):
                raise ValidationError("REFERENCE_TARGET_KIND_MISMATCH", f"assigned_input_ref cannot be {kind}")

        for r in self.input_disposition_refs:
            kind = _ref_kind(r)
            if kind != "input_disposition_record":
                raise ValidationError("REFERENCE_TARGET_KIND_MISMATCH", f"input_disposition_refs must be input_disposition_record, got {kind}")

        for r in self.scope_state_record_refs:
            kind = _ref_kind(r)
            if kind != "scope_state_record":
                raise ValidationError("REFERENCE_TARGET_KIND_MISMATCH", f"scope_state_record_refs must be scope_state_record, got {kind}")

        # Canonical sorted ref sets with duplicate rejection
        for name in (
            "collector_profile_refs", "assigned_input_refs", "input_disposition_refs",
            "surface_refs", "scope_state_record_refs", "manual_runtime_additions",
            "unresolved_scope_refs"
        ):
            raw_list = [_ref_dict(x) for x in getattr(self, name)]
            object.__setattr__(self, name, tuple(canonical_reference_set(raw_list)))

    def body(self) -> dict:
        return {
            "inventory_id": self.inventory_id,
            "inventory_revision": str(self.inventory_revision),
            "source_generation_ref": _ref_dict(self.source_generation_ref),
            "collector_profile_refs": list(self.collector_profile_refs),
            "assigned_input_refs": list(self.assigned_input_refs),
            "input_disposition_refs": list(self.input_disposition_refs),
            "surface_refs": list(self.surface_refs),
            "scope_state_record_refs": list(self.scope_state_record_refs),
            "manual_runtime_additions": list(self.manual_runtime_additions),
            "unresolved_scope_refs": list(self.unresolved_scope_refs),
            "basis_history_cut": dict(self.basis_history_cut),
        }

    def as_object(self) -> CanonicalObject:
        return CanonicalObject(
            "inventory_revision", self.body(), logical_id=self.inventory_id
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class CollectionRun:
    collection_run_id: str
    collector_profile_ref: Any
    assigned_input_manifest_ref: Any
    assigned_inputs: Sequence[str] = ()
    terminal_input_dispositions: Sequence[dict] = ()
    emitted_surface_refs: Sequence[Any] = ()
    runtime_manual_additions: Sequence[Any] = ()
    parse_errors: Sequence[str] = ()
    unsupported_capabilities: Sequence[str] = ()
    resource_limit_events: Sequence[str] = ()
    completion_status: str = "COMPLETED"

    def body(self) -> dict:
        return {
            "collection_run_id": self.collection_run_id,
            "collector_profile_ref": _ref_dict(self.collector_profile_ref) if isinstance(self.collector_profile_ref, (dict, ObjectRef, CanonicalObject)) else str(self.collector_profile_ref),
            "assigned_input_manifest_ref": _ref_dict(self.assigned_input_manifest_ref) if isinstance(self.assigned_input_manifest_ref, (dict, ObjectRef, CanonicalObject)) else str(self.assigned_input_manifest_ref),
            "assigned_inputs": list(self.assigned_inputs),
            "terminal_input_dispositions": list(self.terminal_input_dispositions),
            "emitted_surface_refs": [_ref_dict(r) for r in self.emitted_surface_refs],
            "runtime_manual_additions": [_ref_dict(r) for r in self.runtime_manual_additions],
            "parse_errors": list(self.parse_errors),
            "unsupported_capabilities": list(self.unsupported_capabilities),
            "resource_limit_events": list(self.resource_limit_events),
            "completion_status": self.completion_status,
        }

    def as_object(self) -> CanonicalObject:
        return CanonicalObject(
            "surface_collector_record", self.body(), logical_id=self.collection_run_id
        )

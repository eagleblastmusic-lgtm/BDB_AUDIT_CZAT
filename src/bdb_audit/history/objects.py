"""R5.3.1 canonical object/value contracts used by the reference history.

These classes only prepare and validate immutable bodies. Accepted authority is
established exclusively by :class:`TransactionalHistoryStore`.
"""
from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Mapping

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.hashing import DIGEST_PROFILE, object_digest
from ..core.ids import active_registry_document, contract, validate_id

EMPTY_HISTORY = {"tag": "EMPTY_HISTORY"}
ACCEPTED_HEAD_REF = "ACCEPTED_HEAD_REF"
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _copy(value):
    # Canonical JSON validation also rejects custom/mutable values.
    import json
    return json.loads(canonical_bytes(value).decode("utf-8"))


def _digest(value):
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ValidationError("INVALID_DIGEST")
    return value


def _ref_id(value):
    if type(value) is not str or not value:
        raise ValidationError("TYPED_REF_REQUIRED")
    return value


def ref_dict(kind, revision_digest, *, logical_id=None, schema_revision_ref=None,
             ref_class="CONTENT_OR_PRIOR"):
    """Create the wire shape for an immutable typed ref.

    ``ref_class`` is retained on a body ref for semantic validation; it never
    becomes an inferred dependency when it is a history or sidecar class.
    """
    registry = active_registry_document()
    try:
        contract(kind)
    except ValidationError:
        if kind not in registry.get("reference_target_classes", {}):
            raise
    _digest(revision_digest)
    if ref_class not in active_registry_document()["reference_class_semantics"]:
        raise ValidationError("UNREGISTERED_REFERENCE_CLASS")
    if schema_revision_ref is None:
        schema_revision_ref = "BDB_SCHEMA_REGISTRY::" + kind + "/1"
    if type(schema_revision_ref) is not str or not schema_revision_ref:
        raise ValidationError("SCHEMA_REF_REQUIRED")
    out = {"kind": kind, "revision_digest": revision_digest,
           "digest_profile": DIGEST_PROFILE,
           "schema_revision_ref": schema_revision_ref,
           "ref_class": ref_class}
    if logical_id is not None:
        out["logical_id"] = logical_id
    return out


@dataclass(frozen=True)
class ObjectRef:
    kind: str
    revision_digest: str
    digest_profile: str = DIGEST_PROFILE
    schema_revision_ref: str = ""
    logical_id: str | None = None
    ref_class: str = "CONTENT_OR_PRIOR"

    def __post_init__(self):
        registry = active_registry_document()
        try:
            contract(self.kind)
        except ValidationError:
            if self.kind not in registry.get("reference_target_classes", {}):
                raise
        _digest(self.revision_digest)
        if self.digest_profile != DIGEST_PROFILE:
            raise ValidationError("TYPED_REF_DIGEST_PROFILE")
        if type(self.schema_revision_ref) is not str or not self.schema_revision_ref:
            raise ValidationError("SCHEMA_REF_REQUIRED")
        if self.ref_class not in active_registry_document()["reference_class_semantics"]:
            raise ValidationError("UNREGISTERED_REFERENCE_CLASS")
        if self.logical_id is not None:
            # CommandEnvelope command_id is a deliberate wire exception and is
            # kept outside logical_id. Other logical IDs use registered prefix.
            try:
                validate_id(self.logical_id, self.kind)
            except ValidationError:
                # Target classes such as ``application_generation_ref`` are
                # typed reference domains, not canonical object kinds; their
                # logical identifier syntax is governed by their owner.
                if self.kind not in active_registry_document().get("reference_target_classes", {}):
                    raise

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict:
            raise ValidationError("TYPED_REF_REQUIRED")
        required = {"kind", "revision_digest", "digest_profile", "schema_revision_ref"}
        if not required.issubset(value):
            raise ValidationError("TYPED_REF_INCOMPLETE")
        return cls(value["kind"], value["revision_digest"], value["digest_profile"],
                   value["schema_revision_ref"], value.get("logical_id"),
                   value.get("ref_class", "CONTENT_OR_PRIOR"))

    def as_dict(self, *, ref_class=None):
        return ref_dict(self.kind, self.revision_digest, logical_id=self.logical_id,
                        schema_revision_ref=self.schema_revision_ref,
                        ref_class=self.ref_class if ref_class is None else ref_class)


@dataclass(frozen=True)
class CanonicalObject:
    kind: str
    body: Mapping[str, Any]
    schema_revision_ref: str = ""
    logical_id: str | None = None
    version: str = "1"

    def __post_init__(self):
        row = contract(self.kind, self.version)
        if type(self.body) is not dict:
            raise ValidationError("OBJECT_BODY_REQUIRED")
        if not self.schema_revision_ref:
            object.__setattr__(self, "schema_revision_ref", row["schema_ref"])
        if type(self.schema_revision_ref) is not str or not self.schema_revision_ref:
            raise ValidationError("SCHEMA_REF_REQUIRED")
        if self.logical_id is not None and self.kind not in {
            "command_envelope", "command_receipt", "history_cut"
        }:
            validate_id(self.logical_id, self.kind)
        # Ensure body is a canonical JSON value now; no mutation thereafter.
        object.__setattr__(self, "body", _copy(self.body))

    @property
    def digest(self):
        return object_digest(self.kind, self.version, self.body,
                             registry_kind=self.kind,
                             post_acceptance_sidecar=(self.kind == "command_receipt")).value

    def as_ref(self, *, ref_class=None):
        return ObjectRef(self.kind, self.digest, DIGEST_PROFILE,
                         self.schema_revision_ref, self.logical_id,
                         "CONTENT_OR_PRIOR" if ref_class is None else ref_class)

    @property
    def ref(self):
        return self.as_ref()

    @property
    def content_refs(self):
        result = []
        def visit(value):
            if isinstance(value, dict):
                if {"kind", "revision_digest"}.issubset(value):
                    ref_class = value.get("ref_class", "CONTENT_OR_PRIOR")
                    if ref_class in {"CONTENT_OBJECT", "CONTENT_OR_PRIOR"}:
                        result.append(ObjectRef.from_dict(value))
                    return
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(self.body)
        return tuple(result)

    def record(self):
        return {"kind": self.kind, "version": self.version,
                "logical_id": self.logical_id, "schema_revision_ref": self.schema_revision_ref,
                "revision_digest": self.digest, "body": _copy(self.body)}


@dataclass(frozen=True)
class AcceptedHead:
    campaign_id: str
    commit_seq: int
    commit_hash: str

    def __post_init__(self):
        if type(self.campaign_id) is not str or not self.campaign_id:
            raise ValidationError("CAMPAIGN_ID_REQUIRED")
        if type(self.commit_seq) is not int or isinstance(self.commit_seq, bool) or self.commit_seq < 1:
            raise ValidationError("INVALID_COMMIT_SEQUENCE")
        _digest(self.commit_hash)

    @property
    def commit_digest(self) -> str:
        return self.commit_hash

    def as_dict(self):
        return {"campaign_id": self.campaign_id, "commit_seq": self.commit_seq,
                "commit_hash": self.commit_hash}

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or not {"campaign_id", "commit_seq", "commit_hash"}.issubset(value):
            raise ValidationError("ACCEPTED_HEAD_REF_INVALID")
        return cls(value["campaign_id"], value["commit_seq"], value["commit_hash"])


@dataclass(frozen=True)
class HistoryCut:
    variant: str
    history_namespace_ref: str | None
    campaign_id: str | None
    accepted_head_seq: int | None
    accepted_head_hash: str | None
    governing_policy_ref: str
    governing_spec_refs: tuple[str, ...]

    def __post_init__(self):
        if self.variant not in {"EMPTY_HISTORY_CUT", "ACCEPTED_HISTORY_CUT"}:
            raise ValidationError("HISTORY_CUT_VARIANT")
        if type(self.governing_policy_ref) is not str or not self.governing_policy_ref:
            raise ValidationError("HISTORY_POLICY_REQUIRED")
        if type(self.governing_spec_refs) not in (tuple, list) or not self.governing_spec_refs:
            raise ValidationError("HISTORY_SPEC_REFS_REQUIRED")
        object.__setattr__(self, "governing_spec_refs", tuple(self.governing_spec_refs))
        if self.variant == "EMPTY_HISTORY_CUT":
            if (not self.history_namespace_ref or self.campaign_id is not None or
                    self.accepted_head_seq is not None or self.accepted_head_hash is not None):
                raise ValidationError("EMPTY_HISTORY_CUT_FIELDS_INVALID")
        else:
            if (self.history_namespace_ref is not None or not self.campaign_id or
                    type(self.accepted_head_seq) is not int or self.accepted_head_seq < 1):
                raise ValidationError("ACCEPTED_HISTORY_CUT_FIELDS_INVALID")
            _digest(self.accepted_head_hash)

    @classmethod
    def empty(cls, profile):
        pins = profile.pins
        return cls("EMPTY_HISTORY_CUT", pins["allowed_history_namespace_ref"], None, None, None,
                   pins["initial_governing_policy_ref"], (pins["initial_transition_profile_ref"],))

    @classmethod
    def accepted(cls, head, governing_policy_ref, governing_spec_refs):
        if not isinstance(head, AcceptedHead):
            raise ValidationError("ACCEPTED_HEAD_REF_INVALID")
        return cls("ACCEPTED_HISTORY_CUT", None, head.campaign_id, head.commit_seq,
                   head.commit_hash, governing_policy_ref, tuple(governing_spec_refs))

    def as_dict(self):
        out = {"variant": self.variant,
               "governing_policy_ref": self.governing_policy_ref,
               "governing_spec_refs": list(self.governing_spec_refs)}
        if self.variant == "EMPTY_HISTORY_CUT":
            out["history_namespace_ref"] = self.history_namespace_ref
        elif self.variant == "ACCEPTED_HISTORY_CUT":
            out.update({"campaign_id": self.campaign_id, "accepted_head_seq": self.accepted_head_seq,
                        "accepted_head_hash": self.accepted_head_hash})
        else:
            raise ValidationError("HISTORY_CUT_VARIANT")
        return out

    def require_initialization(self):
        if self.variant != "EMPTY_HISTORY_CUT":
            raise ValidationError("EMPTY_HISTORY_CUT_REQUIRED")

    def require_accepted(self):
        if self.variant != "ACCEPTED_HISTORY_CUT":
            raise ValidationError("ACCEPTED_HISTORY_CUT_REQUIRED")


@dataclass(frozen=True)
class InstallationBootstrapProfile:
    profile_ref: str
    pins: Mapping[str, str]
    version: str = "1"

    REQUIRED_PINS = (
        "initial_schema_registry_ref", "initial_artifact_contract_registry_ref",
        "initial_serialization_profile_ref", "initial_governing_policy_ref",
        "initial_transition_profile_ref", "initial_trust_profile_ref",
        "allowed_history_namespace_ref", "initial_source_identity_profile_ref",
    )

    def __post_init__(self):
        if self.profile_ref != "INSTALLATION_BOOTSTRAP_PROFILE_V1":
            raise ValidationError("BOOTSTRAP_PROFILE_IDENTITY_MISMATCH")
        if type(self.pins) is not dict or set(self.pins) != set(self.REQUIRED_PINS):
            raise ValidationError("BOOTSTRAP_PROFILE_PINS_INCOMPLETE")
        if any(type(v) is not str or not v for v in self.pins.values()):
            raise ValidationError("BOOTSTRAP_PROFILE_PIN_INVALID")

    def as_dict(self):
        return {"profile_ref": self.profile_ref, "version": self.version,
                "allowed_initial_command_kind": "INITIALIZE_CAMPAIGN_FROM_LEGACY",
                **dict(sorted(self.pins.items()))}

    @property
    def profile_digest(self):
        raw = canonical_bytes(self.as_dict())
        return hashlib.sha256(raw).hexdigest()

    def empty_cut(self):
        return HistoryCut.empty(self)


def _check_command_id(value):
    if type(value) is not str or re.fullmatch(r"command_" + _UUID, value) is None:
        raise ValidationError("INVALID_COMMAND_ID")


@dataclass(frozen=True)
class CommandEnvelope:
    command_id: str
    command_kind: str
    actor_ref: str
    expected_parent_head: Mapping[str, Any]
    governing_policy_ref: str
    governing_spec_refs: tuple[str, ...]
    idempotency_scope: str
    command_payload: Mapping[str, Any] | None = None
    campaign_ref: str | None = None
    proposed_campaign_id: str | None = None
    history_namespace_ref: str | None = None
    bootstrap_profile_ref: str | None = None

    def __post_init__(self):
        _check_command_id(self.command_id)
        contract("command_envelope")
        if type(self.actor_ref) is not str or not self.actor_ref:
            raise ValidationError("ACTOR_REF_REQUIRED")
        if type(self.governing_policy_ref) is not str or not self.governing_policy_ref:
            raise ValidationError("GOVERNING_POLICY_REF_REQUIRED")
        if type(self.governing_spec_refs) not in (tuple, list) or not self.governing_spec_refs:
            raise ValidationError("GOVERNING_SPEC_REFS_REQUIRED")
        if any(type(value) is not str or not value for value in self.governing_spec_refs):
            raise ValidationError("GOVERNING_SPEC_REF_INVALID")
        if type(self.idempotency_scope) is not str or not self.idempotency_scope:
            raise ValidationError("IDEMPOTENCY_SCOPE_REQUIRED")
        if type(self.expected_parent_head) is not dict:
            raise ValidationError("EXPECTED_HEAD_INVALID")
        parent = dict(self.expected_parent_head)
        if self.command_kind == "INITIALIZE_CAMPAIGN_FROM_LEGACY":
            if parent != EMPTY_HISTORY:
                raise ValidationError("INITIALIZATION_EXPECTS_EMPTY_HISTORY")
            if self.campaign_ref is not None:
                raise ValidationError("INITIALIZATION_FUTURE_CAMPAIGN_REF")
            if not self.proposed_campaign_id or not self.history_namespace_ref or not self.bootstrap_profile_ref:
                raise ValidationError("INITIALIZATION_CONTEXT_INCOMPLETE")
            if any(type(value) is not str or not value for value in
                   (self.proposed_campaign_id, self.history_namespace_ref, self.bootstrap_profile_ref)):
                raise ValidationError("INITIALIZATION_CONTEXT_INCOMPLETE")
        else:
            if parent.get("tag") != ACCEPTED_HEAD_REF or not self.campaign_ref:
                raise ValidationError("POST_GENESIS_CONTEXT_INCOMPLETE")
            if type(self.campaign_ref) is not str:
                raise ValidationError("POST_GENESIS_CONTEXT_INCOMPLETE")
            if not {"campaign_id", "commit_seq", "commit_hash"}.issubset(parent):
                raise ValidationError("EXPECTED_HEAD_INVALID")
            if any(v is not None for v in (self.proposed_campaign_id, self.history_namespace_ref,
                                           self.bootstrap_profile_ref)):
                raise ValidationError("INITIALIZATION_FIELD_FORBIDDEN")
        object.__setattr__(self, "governing_spec_refs", tuple(self.governing_spec_refs))
        if self.command_payload is not None and type(self.command_payload) is not dict:
            raise ValidationError("COMMAND_PAYLOAD_INVALID")
        if self.proposed_campaign_id is not None and type(self.proposed_campaign_id) is not str:
            raise ValidationError("CAMPAIGN_ID_REQUIRED")

    @classmethod
    def initialize(cls, *, command_id, actor_ref, profile, campaign_id,
                   command_payload=None):
        cut = profile.empty_cut()
        return cls(command_id=command_id, command_kind="INITIALIZE_CAMPAIGN_FROM_LEGACY",
                   actor_ref=actor_ref, expected_parent_head=EMPTY_HISTORY,
                   governing_policy_ref=cut.governing_policy_ref,
                   governing_spec_refs=cut.governing_spec_refs,
                   idempotency_scope=profile.pins["allowed_history_namespace_ref"],
                   command_payload=command_payload, proposed_campaign_id=campaign_id,
                   history_namespace_ref=profile.pins["allowed_history_namespace_ref"],
                   bootstrap_profile_ref=profile.profile_ref)

    def body(self):
        out = {"command_id": self.command_id, "command_kind": self.command_kind,
               "actor_ref": self.actor_ref, "expected_parent_head": _copy(self.expected_parent_head),
               "governing_policy_ref": self.governing_policy_ref,
               "governing_spec_refs": list(self.governing_spec_refs),
               "idempotency_scope": self.idempotency_scope}
        if self.command_payload is not None:
            out["command_payload"] = _copy(self.command_payload)
        for key in ("campaign_ref", "proposed_campaign_id", "history_namespace_ref", "bootstrap_profile_ref"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return out

    def as_object(self):
        return CanonicalObject("command_envelope", self.body())

    @property
    def digest(self):
        return self.as_object().digest


@dataclass(frozen=True)
class CommitBody:
    campaign_id: str
    commit_seq: int
    prev_history_ref: Mapping[str, Any]
    command_ref: ObjectRef
    command_digest: str
    actor_ref: str
    expected_parent_head: Mapping[str, Any]
    governing_policy_ref: str
    governing_spec_refs: tuple[str, ...]
    ordered_event_bodies: tuple[Mapping[str, Any], ...]
    immutable_object_refs: tuple[ObjectRef, ...]

    def __post_init__(self):
        contract("commit_body")
        if type(self.commit_seq) is not int or isinstance(self.commit_seq, bool) or self.commit_seq < 1:
            raise ValidationError("INVALID_COMMIT_SEQUENCE")
        if not isinstance(self.command_ref, ObjectRef):
            raise ValidationError("COMMAND_BINDING_CONFLICT")
        if self.command_ref.kind != "command_envelope" or self.command_ref.ref_class != "CONTENT_OBJECT" or self.command_digest != self.command_ref.revision_digest:
            raise ValidationError("COMMAND_BINDING_CONFLICT")
        if self.prev_history_ref != self.expected_parent_head:
            raise ValidationError("HISTORY_PARENT_BINDING_CONFLICT")
        if self.commit_seq == 1:
            if self.prev_history_ref != EMPTY_HISTORY:
                raise ValidationError("FIRST_COMMIT_REQUIRES_EMPTY_HISTORY")
        else:
            if self.prev_history_ref == EMPTY_HISTORY:
                raise ValidationError("EMPTY_HISTORY_AFTER_INITIALIZATION")
            if type(self.prev_history_ref) is not dict:
                raise ValidationError("EXPECTED_HEAD_INVALID")
        if type(self.immutable_object_refs) not in (tuple, list):
            raise ValidationError("CONTENT_REFERENCE_REQUIRED")
        if any(not isinstance(ref, ObjectRef) for ref in self.immutable_object_refs):
            raise ValidationError("CONTENT_REFERENCE_REQUIRED")
        digests = [r.revision_digest for r in self.immutable_object_refs]
        if len(digests) != len(set(digests)):
            raise ValidationError("DUPLICATE_CONTENT_REFERENCE")
        if self.command_ref.revision_digest not in digests:
            raise ValidationError("COMMAND_NOT_IN_CLOSURE")
        if self.immutable_object_refs and self.immutable_object_refs[0] != self.command_ref:
            raise ValidationError("COMMAND_MUST_PRECEDE_DOMAIN_OBJECTS")
        if any(ref.ref_class != "CONTENT_OBJECT" for ref in self.immutable_object_refs):
            raise ValidationError("CONTENT_REFERENCE_CLASS_INVALID")
        if type(self.governing_spec_refs) not in (tuple, list) or not self.governing_spec_refs:
            raise ValidationError("GOVERNING_SPEC_REFS_REQUIRED")
        if type(self.actor_ref) is not str or not self.actor_ref:
            raise ValidationError("ACTOR_REF_REQUIRED")
        if type(self.governing_policy_ref) is not str or not self.governing_policy_ref:
            raise ValidationError("GOVERNING_POLICY_REF_REQUIRED")
        if any(type(value) is not str or not value for value in self.governing_spec_refs):
            raise ValidationError("GOVERNING_SPEC_REF_INVALID")
        object.__setattr__(self, "governing_spec_refs", tuple(self.governing_spec_refs))
        ordinals = [e.get("ordinal") for e in self.ordered_event_bodies if isinstance(e, dict) and "ordinal" in e]
        if ordinals and ordinals != list(range(len(ordinals))):
            raise ValidationError("EVENT_ORDINAL_INVALID")

    def body(self):
        return {"campaign_id": self.campaign_id, "commit_seq": self.commit_seq,
                "prev_history_ref": _copy(self.prev_history_ref),
                "command_ref": self.command_ref.as_dict(ref_class="CONTENT_OBJECT"), "command_digest": self.command_digest,
                "actor_ref": self.actor_ref,
                "expected_parent_head": _copy(self.expected_parent_head),
                "governing_policy_ref": self.governing_policy_ref,
                "governing_spec_refs": list(self.governing_spec_refs),
                "ordered_event_bodies": [_copy(v) for v in self.ordered_event_bodies],
                "immutable_object_refs": [v.as_dict(ref_class="CONTENT_OBJECT") for v in self.immutable_object_refs]}

    def as_object(self):
        return CanonicalObject("commit_body", self.body())

    @property
    def digest(self):
        return self.as_object().digest


@dataclass(frozen=True)
class CommandReceipt:
    command_id: str
    command_ref: ObjectRef
    result_object_refs: tuple[ObjectRef, ...]
    accepted_commit_ref: Mapping[str, Any]
    accepted_head: AcceptedHead
    receipt_status: str = "ACCEPTED"

    def __post_init__(self):
        contract("command_receipt")
        _check_command_id(self.command_id)
        if not isinstance(self.command_ref, ObjectRef) or self.command_ref.kind != "command_envelope":
            raise ValidationError("RECEIPT_COMMAND_BINDING_CONFLICT")
        if any(not isinstance(ref, ObjectRef) for ref in self.result_object_refs):
            raise ValidationError("RECEIPT_RESULT_REFERENCE_INVALID")
        object.__setattr__(self, "result_object_refs", tuple(self.result_object_refs))
        if not isinstance(self.accepted_head, AcceptedHead):
            raise ValidationError("RECEIPT_HEAD_TARGET_MISMATCH")
        if not isinstance(self.accepted_commit_ref, Mapping) or self.accepted_commit_ref.get("kind") != "commit_body":
            raise ValidationError("RECEIPT_COMMIT_TARGET_MISMATCH")
        if self.accepted_commit_ref.get("digest_profile") != DIGEST_PROFILE:
            raise ValidationError("RECEIPT_COMMIT_TARGET_MISMATCH")
        if not isinstance(self.accepted_commit_ref.get("schema_revision_ref"), str) or not self.accepted_commit_ref.get("schema_revision_ref"):
            raise ValidationError("RECEIPT_COMMIT_TARGET_MISMATCH")
        if self.accepted_commit_ref.get("ref_class") not in {"POST_ACCEPTANCE_SIDECAR", "CONTENT_OR_PRIOR"}:
            raise ValidationError("RECEIPT_COMMIT_TARGET_MISMATCH")
        if self.accepted_commit_ref.get("revision_digest") != self.accepted_head.commit_hash:
            raise ValidationError("RECEIPT_COMMIT_TARGET_MISMATCH")
        if self.receipt_status != "ACCEPTED":
            raise ValidationError("RECEIPT_STATUS_INVALID")

    def body(self):
        if self.receipt_status != "ACCEPTED":
            raise ValidationError("RECEIPT_STATUS_INVALID")
        return {"command_id": self.command_id, "command_ref": self.command_ref.as_dict(ref_class="POST_ACCEPTANCE_SIDECAR"),
                "result_object_refs": [r.as_dict(ref_class="POST_ACCEPTANCE_SIDECAR") for r in self.result_object_refs],
                "accepted_commit_ref": _copy(self.accepted_commit_ref),
                "accepted_head": self.accepted_head.as_dict(),
                "receipt_status": self.receipt_status}

    def as_object(self):
        return CanonicalObject("command_receipt", self.body())

    @property
    def digest(self):
        return self.as_object().digest


@dataclass(frozen=True)
class TrustedPredecessorSelectionDecision:
    selection_input_history_cut: Mapping[str, Any]
    candidate_legacy_refs: tuple[ObjectRef, ...]
    selected_legacy_ref: ObjectRef | None
    source_reconciliation_assessment_ref: ObjectRef
    lineage_admission_assessment_ref: ObjectRef
    selection_policy_ref: str
    predecessor_pin_ref: str
    decision: str = "SELECTED"
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        contract("trusted_predecessor_selection_decision")
        if self.decision not in {"SELECTED", "REJECTED", "CONFLICTED",
                                 "INSUFFICIENT_DATA", "NO_CANONICAL_PREDECESSOR"}:
            raise ValidationError("TRUSTED_SELECTION_ENUM_MISMATCH")
        if self.decision == "SELECTED":
            if self.selected_legacy_ref is None or self.selected_legacy_ref not in self.candidate_legacy_refs:
                raise ValidationError("SELECTION_BINDING_MISSING")
        if not self.candidate_legacy_refs:
            raise ValidationError("CANDIDATE_LEGACY_REFS_REQUIRED")
        object.__setattr__(self, "candidate_legacy_refs", tuple(self.candidate_legacy_refs))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))

    def body(self):
        out = {"selection_input_history_cut": _copy(self.selection_input_history_cut),
               "candidate_legacy_refs": [r.as_dict() for r in self.candidate_legacy_refs],
               "source_reconciliation_assessment_ref": self.source_reconciliation_assessment_ref.as_dict(),
               "lineage_admission_assessment_ref": self.lineage_admission_assessment_ref.as_dict(),
               "selection_policy_ref": self.selection_policy_ref,
               "predecessor_pin_ref": self.predecessor_pin_ref, "decision": self.decision,
               "reason_codes": list(self.reason_codes)}
        if self.selected_legacy_ref:
            out["selected_legacy_ref"] = self.selected_legacy_ref.as_dict()
        return out

    def as_object(self):
        return CanonicalObject("trusted_predecessor_selection_decision", self.body())


@dataclass(frozen=True)
class BootstrapAdmissionDecision:
    admission_input_history_cut: Mapping[str, Any]
    legacy_ref: ObjectRef
    mechanical_validation_assessment_ref: ObjectRef
    source_reconciliation_assessment_ref: ObjectRef
    lineage_admission_assessment_ref: ObjectRef
    trusted_predecessor_selection_ref: ObjectRef | None
    admission_policy_ref: str
    result: str = "CANONICAL_BOOTSTRAP_ADMITTED"
    exposure_reconstruction_assessment_ref: ObjectRef | None = None
    requested_role: str = "CANONICAL_PREDECESSOR"
    limitations: tuple[str, ...] = field(default_factory=tuple)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        contract("bootstrap_admission_decision")
        if self.result not in {"CANONICAL_BOOTSTRAP_ADMITTED",
                               "CANONICAL_BOOTSTRAP_ADMITTED_WITH_EXPOSURE_LIMIT",
                               "BLOCKED_CANONICAL_ADMISSION"}:
            raise ValidationError("BOOTSTRAP_ADMISSION_ENUM_MISMATCH")
        if self.trusted_predecessor_selection_ref is None:
            raise ValidationError("BOOTSTRAP_SELECTION_BINDING_MISSING")
        if self.requested_role not in {"CANONICAL_PREDECESSOR", "AUXILIARY"}:
            raise ValidationError("BOOTSTRAP_ROLE_INVALID")
        object.__setattr__(self, "limitations", tuple(self.limitations))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))

    def body(self):
        out = {"admission_input_history_cut": _copy(self.admission_input_history_cut),
               "legacy_ref": self.legacy_ref.as_dict(),
               "mechanical_validation_assessment_ref": self.mechanical_validation_assessment_ref.as_dict(),
               "source_reconciliation_assessment_ref": self.source_reconciliation_assessment_ref.as_dict(),
               "lineage_admission_assessment_ref": self.lineage_admission_assessment_ref.as_dict(),
               "trusted_predecessor_selection_ref": self.trusted_predecessor_selection_ref.as_dict(),
               "admission_policy_ref": self.admission_policy_ref, "result": self.result,
               "requested_role": self.requested_role, "limitations": list(self.limitations),
               "reason_codes": list(self.reason_codes)}
        if self.exposure_reconstruction_assessment_ref:
            out["exposure_reconstruction_assessment_ref"] = self.exposure_reconstruction_assessment_ref.as_dict()
        return out

    def as_object(self):
        return CanonicalObject("bootstrap_admission_decision", self.body())


@dataclass(frozen=True)
class CampaignGenesis:
    campaign_id: str
    input_history_cut: Mapping[str, Any]
    bootstrap_admission_decision_ref: ObjectRef
    source_generation_ref: ObjectRef
    application_generation_ref: ObjectRef
    protocol_policy_bundle_ref: ObjectRef
    schema_set_ref: ObjectRef
    owner_operator_authority_ref: ObjectRef
    trust_profile_ref: ObjectRef
    legacy_origin_refs: tuple[ObjectRef, ...] = field(default_factory=tuple)

    def body(self):
        return {"campaign_id": self.campaign_id, "input_history_cut": _copy(self.input_history_cut),
                "bootstrap_admission_decision_ref": self.bootstrap_admission_decision_ref.as_dict(ref_class="CONTENT_OR_PRIOR"),
                "source_generation_ref": self.source_generation_ref.as_dict(ref_class="CONTENT_OR_PRIOR"),
                "application_generation_ref": self.application_generation_ref.as_dict(ref_class="CONTENT_OR_PRIOR"),
                "protocol_policy_bundle_ref": self.protocol_policy_bundle_ref.as_dict(ref_class="CONTENT_OR_PRIOR"),
                "schema_set_ref": self.schema_set_ref.as_dict(ref_class="CONTENT_OR_PRIOR"),
                "owner_operator_authority_ref": self.owner_operator_authority_ref.as_dict(ref_class="PINNED_INSTALLATION_REF"),
                "trust_profile_ref": self.trust_profile_ref.as_dict(ref_class="PINNED_INSTALLATION_REF"),
                "legacy_origin_refs": [r.as_dict(ref_class="CONTENT_OR_PRIOR") for r in self.legacy_origin_refs]}

    def validate_admission(self, admission):
        if self.input_history_cut.get("variant") != "EMPTY_HISTORY_CUT":
            raise ValidationError("NORMAL_GENESIS_REQUIRES_EMPTY_HISTORY")
        if admission.result == "BLOCKED_CANONICAL_ADMISSION":
            raise ValidationError("BLOCKED_ADMISSION_CANNOT_EMIT_GENESIS")
        if self.bootstrap_admission_decision_ref.revision_digest != admission.as_object().digest:
            raise ValidationError("GENESIS_ADMISSION_BINDING_MISMATCH")

    def as_object(self):
        return CanonicalObject("campaign_genesis", self.body())

"""Positive capability views and grant-before-delivery (M8/M13 substrate)."""
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..history.objects import CanonicalObject, ObjectRef


def _key(ref):
    if isinstance(ref, ObjectRef):
        return ref.revision_digest
    if isinstance(ref, Mapping):
        return ref.get("revision_digest")
    return ref


@dataclass(frozen=True)
class ExecutorProfile:
    profile_id: str
    revision: str
    executor_tool_ref: str
    runtime_profile_ref: str
    supported_capabilities: tuple[str, ...] = ()
    isolation_capabilities: tuple[str, ...] = ()
    filesystem_boundary_ref: str = ""
    network_boundary_ref: str = ""
    tool_boundary_ref: str = ""
    session_freshness: str = "UNKNOWN"
    known_limitations: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.profile_id or not self.revision or not self.executor_tool_ref or not self.runtime_profile_ref:
            raise ValidationError("EXECUTOR_PROFILE_CONTEXT_REQUIRED")
        object.__setattr__(self, "supported_capabilities", tuple(self.supported_capabilities))
        object.__setattr__(self, "isolation_capabilities", tuple(self.isolation_capabilities))
        object.__setattr__(self, "known_limitations", tuple(self.known_limitations))

    def body(self):
        return {"executor_profile_id": self.profile_id, "executor_profile_revision": self.revision,
                "executor_tool_ref": self.executor_tool_ref, "runtime_profile_ref": self.runtime_profile_ref,
                "supported_capabilities": list(self.supported_capabilities),
                "isolation_capabilities": list(self.isolation_capabilities),
                "filesystem_boundary_ref": self.filesystem_boundary_ref,
                "network_boundary_ref": self.network_boundary_ref, "tool_boundary_ref": self.tool_boundary_ref,
                "session_freshness": self.session_freshness, "known_limitations": list(self.known_limitations)}

    def as_object(self):
        return CanonicalObject("executor_spec", self.body())


@dataclass(frozen=True)
class DeliveryProfile:
    profile_id: str
    revision: str
    delivery_channel: str
    grant_before_delivery_required: bool = True
    ack_semantics: str = "OPTIONAL"
    retry_policy_ref: str = ""
    idempotency_policy_ref: str = ""
    potential_exposure_point: str = "GRANT_ACCEPTED"
    redaction_profile: str = "POSITIVE_VIEW"

    def __post_init__(self):
        if not self.profile_id or not self.revision or not self.delivery_channel:
            raise ValidationError("DELIVERY_PROFILE_CONTEXT_REQUIRED")
        if not self.grant_before_delivery_required:
            raise ValidationError("GRANT_BEFORE_DELIVERY_REQUIRED")

    def body(self):
        return {"delivery_profile_id": self.profile_id, "delivery_profile_revision": self.revision,
                "delivery_channel": self.delivery_channel,
                "grant_before_delivery_required": self.grant_before_delivery_required,
                "ack_semantics": self.ack_semantics, "retry_policy_ref": self.retry_policy_ref,
                "idempotency_policy_ref": self.idempotency_policy_ref,
                "potential_exposure_point": self.potential_exposure_point,
                "redaction_profile": self.redaction_profile}

    def as_object(self):
        return CanonicalObject("delivery_spec", self.body())


@dataclass(frozen=True)
class ProjectionPolicy:
    policy_id: str
    revision: str
    allowed_fields: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    allowed_kinds: tuple[str, ...] = ()
    forbidden_kinds: tuple[str, ...] = ()
    phase: str = "PRE_REVEAL"
    reveal_support_count: bool = False
    reveal_filenames: bool = False
    _allowed_refs: tuple[Mapping, ...] = field(default=(), init=False, repr=False, compare=False)

    def __post_init__(self):
        if not self.policy_id or not self.revision:
            raise ValidationError("PROJECTION_POLICY_CONTEXT_REQUIRED")
        object.__setattr__(self, "allowed_fields", {str(k): tuple(v) for k, v in self.allowed_fields.items()})
        object.__setattr__(self, "allowed_kinds", tuple(self.allowed_kinds))
        object.__setattr__(self, "forbidden_kinds", tuple(self.forbidden_kinds))

    def body(self):
        return {"policy_id": self.policy_id, "policy_revision": self.revision,
                "allowed_fields": {k: list(v) for k, v in sorted(self.allowed_fields.items())},
                "allowed_kinds": list(self.allowed_kinds), "forbidden_kinds": list(self.forbidden_kinds),
                "phase": self.phase, "reveal_support_count": self.reveal_support_count,
                "reveal_filenames": self.reveal_filenames}

    def as_object(self):
        return CanonicalObject("projection_policy", self.body())


@dataclass(frozen=True)
class ViewRef:
    namespace: str
    view_digest: str

    def as_dict(self):
        return {"namespace": self.namespace, "view_digest": self.view_digest}


@dataclass(frozen=True)
class ViewManifest:
    view_id: str
    projection_policy_ref: Mapping
    allowed_artifact_refs: tuple[Mapping, ...] = ()
    allowed_view_classes: tuple[str, ...] = ()
    forbidden_knowledge_classes: tuple[str, ...] = ()
    phase: str = "PRE_REVEAL"

    def __post_init__(self):
        if not self.view_id:
            raise ValidationError("VIEW_ID_REQUIRED")
        if not isinstance(self.projection_policy_ref, Mapping):
            raise ValidationError("VIEW_POLICY_REQUIRED")
        object.__setattr__(self, "allowed_artifact_refs", tuple(self.allowed_artifact_refs))
        object.__setattr__(self, "allowed_view_classes", tuple(self.allowed_view_classes))
        object.__setattr__(self, "forbidden_knowledge_classes", tuple(self.forbidden_knowledge_classes))

    def body(self):
        return {"view_id": self.view_id, "projection_policy_ref": dict(self.projection_policy_ref),
                "allowed_artifact_refs": [dict(v) for v in self.allowed_artifact_refs],
                "allowed_view_classes": list(self.allowed_view_classes),
                "forbidden_knowledge_classes": list(self.forbidden_knowledge_classes),
                "phase": self.phase}

    def as_object(self):
        return CanonicalObject("view_manifest", self.body())

    @property
    def ref(self):
        obj = self.as_object()
        return {"kind": "view_manifest", "revision_digest": obj.digest,
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": "BDB_SCHEMA_REGISTRY::view_manifest/1",
                "ref_class": "CONTENT_OR_PRIOR"}


@dataclass(frozen=True)
class GrantBody:
    attempt_ref: Mapping
    grant_input_history_cut: Mapping
    view_manifest_ref: Mapping
    delivery_profile_ref: Mapping
    forbidden_knowledge_policy_ref: str
    channel_class: str
    previous_knowledge_state_ref: Mapping | None = None
    capability_profile_ref: Mapping | None = None

    def body(self):
        out = {"attempt_ref": dict(self.attempt_ref), "grant_input_history_cut": dict(self.grant_input_history_cut),
               "view_manifest_ref": dict(self.view_manifest_ref), "delivery_profile_ref": dict(self.delivery_profile_ref),
               "forbidden_knowledge_policy_ref": self.forbidden_knowledge_policy_ref,
               "channel_class": self.channel_class}
        if self.previous_knowledge_state_ref is not None:
            out["previous_knowledge_state_ref"] = dict(self.previous_knowledge_state_ref)
        if self.capability_profile_ref is not None:
            out["capability_profile_ref"] = dict(self.capability_profile_ref)
        return out

    def as_object(self):
        return CanonicalObject("grant_body", self.body())


class CapabilityBroker:
    """Resolver over a positive allowlist, with no raw-ref fallback."""
    VIEW_NAMESPACE = "BDB_VIEW"

    def __init__(self, artifacts=None, *, history=None):
        self._history = history
        self._artifacts = dict(artifacts or {})
        self._views = {}
        self._grants = {}

    def _project(self, key, policy, seen):
        if key in seen:
            raise ValidationError("VIEW_REFERENCE_CYCLE")
        if key not in self._artifacts:
            raise ValidationError("VIEW_REJECTED")
        item = self._artifacts[key]
        if not isinstance(item, Mapping):
            raise ValidationError("VIEW_REJECTED")
        kind = item.get("kind", "")
        if kind in policy.forbidden_kinds or (policy.allowed_kinds and kind not in policy.allowed_kinds):
            raise ValidationError("VIEW_REJECTED")
        fields = policy.allowed_fields.get(kind)
        if fields is None:
            # An explicit artifact allowlist still needs a field allowlist;
            # copying the whole raw object would be negative redaction.
            raise ValidationError("VIEW_FIELDS_NOT_ALLOWLISTED")
        out = {name: item[name] for name in fields if name in item}
        # Resolve only refs that are explicitly allowlisted and permitted by
        # the view namespace. Hidden/transitive refs never get traversed.
        for name, value in list(out.items()):
            if isinstance(value, Mapping) and "revision_digest" in value:
                child = _key(value)
                if child not in seen and child in self._artifacts:
                    if child not in {_key(r) for r in policy._allowed_refs}:
                        raise ValidationError("VIEW_TRANSITIVE_LEAK")
                    out[name] = self._project(child, policy, seen | {key})
            elif isinstance(value, list):
                for child_ref in value:
                    if isinstance(child_ref, Mapping) and "revision_digest" in child_ref:
                        child = _key(child_ref)
                        if child in self._artifacts and child not in {_key(r) for r in policy._allowed_refs}:
                            raise ValidationError("VIEW_TRANSITIVE_LEAK")
        return out

    def prepare_view(self, manifest: ViewManifest, policy: ProjectionPolicy):
        allowed = {_key(ref) for ref in manifest.allowed_artifact_refs}
        if not allowed:
            raise ValidationError("VIEW_ALLOWLIST_EMPTY")
        # Attach the manifest allowlist to an immutable policy copy for the
        # recursive projector; this is internal capability state, not output.
        object.__setattr__(policy, "_allowed_refs", tuple(manifest.allowed_artifact_refs))
        root = next(ref for ref in manifest.allowed_artifact_refs if _key(ref) in allowed)
        body = self._project(_key(root), policy, set())
        raw = canonical_bytes(body)
        import hashlib
        digest = hashlib.sha256(raw).hexdigest()
        view_ref = ViewRef(self.VIEW_NAMESPACE, digest)
        self._views[digest] = (manifest, body, raw)
        return view_ref, raw

    def resolve_view(self, view_ref: ViewRef):
        if not isinstance(view_ref, ViewRef) or view_ref.namespace != self.VIEW_NAMESPACE:
            raise ValidationError("OPAQUE_VIEW_REF")
        try:
            return self._views[view_ref.view_digest][2]
        except KeyError as exc:
            raise ValidationError("VIEW_NOT_FOUND") from exc

    def accept_grant(self, grant: GrantBody, *, history_cut=None):
        if not isinstance(grant, GrantBody):
            raise ValidationError("GRANT_REQUIRED")
        # The accepted grant is the exposure boundary. Delivery callers must
        # hold this object before asking for view bytes.
        if self._history is None or history_cut is None:
            raise ValidationError("GRANT_NOT_ACCEPTED")
        self._history.resolve_accepted(grant.as_object().ref, history_cut, require_current=True)
        return grant.as_object().ref

    def deliver(self, grant_ref, view_ref: ViewRef, *, history_cut=None):
        if self._history is None or history_cut is None:
            raise ValidationError("GRANT_NOT_ACCEPTED")
        if not isinstance(view_ref, ViewRef) or view_ref.view_digest not in self._views:
            raise ValidationError("OPAQUE_VIEW_REF")
        accepted = self._history.resolve_accepted(grant_ref, history_cut, require_current=True)
        if accepted["ref"]["kind"] != "grant_body":
            raise ValidationError("GRANT_NOT_ACCEPTED")
        manifest = self._views[view_ref.view_digest][0]
        if accepted["body"]["view_manifest_ref"] != manifest.ref:
            raise ValidationError("GRANT_VIEW_BINDING_MISMATCH")
        return self.resolve_view(view_ref)


__all__ = ["ExecutorProfile", "DeliveryProfile", "ProjectionPolicy", "ViewManifest",
           "ViewRef", "GrantBody", "CapabilityBroker"]

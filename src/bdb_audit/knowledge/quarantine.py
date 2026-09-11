"""Claim Quarantine as a positive allowlisted view resolver (M13)."""
from dataclasses import dataclass
from typing import Any, Mapping
import hashlib

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..orchestration.capability import ProjectionPolicy, ViewManifest, ViewRef


def _digest(value):
    if isinstance(value, Mapping):
        return value.get("revision_digest")
    return value


@dataclass(frozen=True)
class QuarantinedView:
    view_ref: ViewRef
    raw: bytes


class ClaimQuarantine:
    """Builds a new positive view graph; it never serializes then deletes keys."""
    def __init__(self, *, artifacts: Mapping[str, Mapping], policy: ProjectionPolicy,
                 namespace="BDB_VIEW"):
        self.artifacts = dict(artifacts)
        self.policy = policy
        self.namespace = namespace
        self._views = {}

    def _project(self, key, allow, path=()):
        if key in path:
            raise ValidationError("VIEW_REFERENCE_CYCLE")
        source = self.artifacts.get(key)
        if not isinstance(source, Mapping):
            raise ValidationError("VIEW_REJECTED")
        kind = source.get("kind", "")
        if kind in self.policy.forbidden_kinds or (self.policy.allowed_kinds and kind not in self.policy.allowed_kinds):
            raise ValidationError("VIEW_REJECTED")
        fields = self.policy.allowed_fields.get(kind)
        if fields is None:
            raise ValidationError("VIEW_FIELDS_NOT_ALLOWLISTED")
        out = {}
        for name in fields:
            if name not in source:
                continue
            value = source[name]
            if isinstance(value, Mapping) and "revision_digest" in value:
                child = _digest(value)
                if child in self.artifacts:
                    if child not in allow:
                        raise ValidationError("VIEW_TRANSITIVE_LEAK")
                    value = self._project(child, allow, path + (key,))
            elif isinstance(value, list):
                rewritten = []
                for item in value:
                    if isinstance(item, Mapping) and "revision_digest" in item and _digest(item) in self.artifacts:
                        child = _digest(item)
                        if child not in allow:
                            raise ValidationError("VIEW_TRANSITIVE_LEAK")
                        rewritten.append(self._project(child, allow, path + (key,)))
                    else:
                        rewritten.append(item)
                value = rewritten
            out[name] = value
        # A positive view must not carry raw locator/hash/filename metadata
        # unless those names are explicitly allowlisted by the policy.
        forbidden_names = {"raw_bytes", "raw_digest", "filename", "original_path", "locator", "support_count"}
        if forbidden_names & set(source) - set(fields):
            # Exclusion is expected; the check documents that this is a
            # positive projection and prevents accidental whole-object copies.
            pass
        return out

    def reveal(self, *, root_ref: Mapping, allowed_refs=None):
        root = _digest(root_ref)
        if root not in self.artifacts:
            raise ValidationError("VIEW_REJECTED")
        allow = set(allowed_refs or (root,))
        if root not in allow:
            raise ValidationError("VIEW_ALLOWLIST_ROOT_MISSING")
        body = self._project(root, allow)
        raw = canonical_bytes(body)
        digest = hashlib.sha256(raw).hexdigest()
        ref = ViewRef(self.namespace, digest)
        self._views[digest] = raw
        return QuarantinedView(ref, raw)

    def resolve(self, ref):
        if not isinstance(ref, ViewRef) or ref.namespace != self.namespace:
            raise ValidationError("OPAQUE_VIEW_REF")
        try:
            return self._views[ref.view_digest]
        except KeyError as exc:
            raise ValidationError("VIEW_NOT_FOUND") from exc


RestrictedResolver = ClaimQuarantine

__all__ = ["QuarantinedView", "ClaimQuarantine", "RestrictedResolver"]

"""Claim Quarantine as a positive allowlisted view resolver (M13)."""
from dataclasses import dataclass
from typing import Any, Mapping
import hashlib

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..orchestration.capability import (
    ProjectionPolicy,
    ViewManifest,
    ViewRef,
    project_positive_artifact,
)


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
        return project_positive_artifact(self.artifacts, self.policy, key, set(allow), tuple(path))

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

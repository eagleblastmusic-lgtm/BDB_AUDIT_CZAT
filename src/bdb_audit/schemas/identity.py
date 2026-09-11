"""Layered offline schema/identity validator and qualification manifest (M10)."""
from dataclasses import dataclass
from typing import Mapping
import hashlib

from ..core.canonical_json import canonical_bytes, parse
from ..core.errors import ValidationError
from ..core.hashing import object_digest
from ..core.registry import ContractRegistry
from ..history.objects import CanonicalObject
from .foundation import F2_KINDS, foundation_schema_bindings, schema_identity_manifest


@dataclass(frozen=True)
class ValidatedIdentity:
    kind: str
    version: str
    body: Mapping
    revision_digest: str
    schema_revision_ref: str


class LayeredValidator:
    """Parse → schema → digest → typed refs → context, fail-closed."""
    def __init__(self, *, bindings=None, registry=None):
        self.registry = registry or ContractRegistry()
        self.bindings = bindings or foundation_schema_bindings(kinds=tuple(F2_KINDS))

    def validate(self, kind, raw, *, version="1", expected_digest=None,
                 expected_schema_ref=None, context=None):
        # Layer 1 and 2 happen in validate_schema: parse rejects duplicate
        # keys before jsonschema sees the object.
        body = self.bindings.validate_schema(kind, raw, version)
        row = self.registry.contract(kind, version)
        if expected_schema_ref is not None and expected_schema_ref != row["schema_ref"]:
            raise ValidationError("TYPED_REF_TARGET_MISMATCH")
        # Layer 3 canonical bytes/digest is computed from the parsed body; the
        # body itself never carries its own revision digest.
        canonical = canonical_bytes(body)
        digest = object_digest(kind, version, body, registry_kind=kind).value
        if expected_digest is not None and digest != expected_digest:
            raise ValidationError("OBJECT_DIGEST_MISMATCH")
        # Layer 4: every typed ref carries the exact profile/schema key and a
        # registered target kind. History/context classes are intentionally
        # left for their owning domain validators.
        self._typed_refs(body)
        # Layers 5–8 are explicit context predicates, never inferred from a
        # latest-by-logical-ID lookup.
        if context is not None and callable(context):
            context(kind, body)
        return ValidatedIdentity(kind, version, body, digest, row["schema_ref"])

    def _typed_refs(self, value):
        if isinstance(value, Mapping):
            if {"kind", "revision_digest", "digest_profile", "schema_revision_ref"}.issubset(value):
                if value["kind"] not in self.registry.document["reference_target_classes"]:
                    # Registered canonical kinds are also valid targets.
                    self.registry.contract(value["kind"])
                if value["digest_profile"] != "BDB-OBJECT-DIGEST-1":
                    raise ValidationError("TYPED_REF_DIGEST_PROFILE")
                if type(value["revision_digest"]) is not str or len(value["revision_digest"]) != 64:
                    raise ValidationError("INVALID_DIGEST")
                if value.get("ref_class") not in self.registry.document["reference_class_semantics"]:
                    raise ValidationError("UNREGISTERED_REFERENCE_CLASS")
                return
            for child in value.values():
                self._typed_refs(child)
        elif isinstance(value, list):
            for child in value:
                self._typed_refs(child)


def foundation_qualification():
    """Return deterministic identity evidence for all F2-bound kinds."""
    manifest = schema_identity_manifest(kinds=tuple(F2_KINDS))
    manifest["validator_order"] = ["parse", "schema", "canonicalization", "typed_refs",
                                    "source_campaign_scope", "policy_spec", "history_cut", "evidence_applicability"]
    return manifest


__all__ = ["ValidatedIdentity", "LayeredValidator", "foundation_qualification"]

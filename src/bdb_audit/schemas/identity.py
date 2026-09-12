"""Layered offline schema/identity validator and qualification manifest (M10)."""
from dataclasses import dataclass
from typing import Mapping
import hashlib

import re

from ..core.canonical_json import canonical_bytes, parse
from ..core.errors import ValidationError
from ..core.hashing import object_digest
from ..core.registry import ContractRegistry
from ..history.objects import CanonicalObject
from .foundation import (
    F2_KINDS,
    ALL_EXECUTABLE_KINDS,
    foundation_schema_bindings,
    schema_identity_manifest,
)


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
        self.bindings = bindings or foundation_schema_bindings(kinds=tuple(ALL_EXECUTABLE_KINDS))

    def validate(self, kind, raw, *, version="1", expected_digest=None,
                 expected_schema_ref=None, context=None):
        row = self.registry.contract(kind, version)
        schema_ref = row.get("schema_ref")
        if not schema_ref or not isinstance(schema_ref, str):
            raise ValidationError("MISSING_SCHEMA_REF")
        self.bindings.require_bound(schema_ref)

        # Layer 1 and 2 happen in validate_schema: parse rejects duplicate
        # keys before jsonschema sees the object.
        body = self.bindings.validate_schema(kind, raw, version)
        if expected_schema_ref is not None and expected_schema_ref != row["schema_ref"]:
            raise ValidationError("TYPED_REF_TARGET_MISMATCH")
        # Layer 3 canonical bytes/digest is computed from the parsed body; the
        # body itself never carries its own revision digest.
        canonical = canonical_bytes(body)
        digest = object_digest(kind, version, body, registry_kind=kind, registry=self.registry).value
        if expected_digest is not None and digest != expected_digest:
            raise ValidationError("OBJECT_DIGEST_MISMATCH")
        # Layer 4: every typed ref carries the exact profile/schema key and a
        # registered target kind. History/context classes are intentionally
        # left for their owning domain validators.
        self._typed_refs(body)
        # Layers 5–8 are explicit context predicates, never inferred from a
        # latest-by-logical-ID lookup.
        if context is not None:
            if callable(context):
                context(kind, body)
            elif isinstance(context, Mapping):
                self._validate_context_mapping(kind, body, context)
            else:
                raise ValidationError("INVALID_CONTEXT_TYPE", "Context must be a callable or mapping")
        return ValidatedIdentity(kind, version, body, digest, row["schema_ref"])

    def _typed_refs(self, value):
        if isinstance(value, Mapping):
            if {"kind", "revision_digest", "digest_profile", "schema_revision_ref"}.issubset(value):
                target_kind = self.registry.target(value["kind"])
                if value["digest_profile"] != "BDB-OBJECT-DIGEST-1":
                    raise ValidationError("TYPED_REF_DIGEST_PROFILE")
                if type(value["revision_digest"]) is not str or re.fullmatch(r"[0-9a-f]{64}", value["revision_digest"]) is None:
                    raise ValidationError("INVALID_DIGEST")
                if value.get("ref_class") not in self.registry.document["reference_class_semantics"]:
                    raise ValidationError("UNREGISTERED_REFERENCE_CLASS")
                schema_ref = value["schema_revision_ref"]
                if not isinstance(schema_ref, str) or not schema_ref.strip():
                    raise ValidationError("INVALID_SCHEMA_REFERENCE")
                # If target kind is a registered canonical contract, schema_ref must match contract's schema_ref or target profile ref
                if (target_kind, "1") in self.registry._contracts:
                    expected_schema_ref = self.registry.contract(target_kind, "1")["schema_ref"]
                    if schema_ref != expected_schema_ref and schema_ref != f"BDB_TARGET/{target_kind}":
                        raise ValidationError(
                            "TYPED_REF_TARGET_MISMATCH",
                            f"Expected schema_revision_ref '{expected_schema_ref}' or 'BDB_TARGET/{target_kind}', got '{schema_ref}'",
                        )
                return
            for child in value.values():
                self._typed_refs(child)
        elif isinstance(value, list):
            for child in value:
                self._typed_refs(child)

    def _validate_context_mapping(self, kind: str, body: Mapping, context: Mapping) -> None:
        # 1. Campaign ID / campaign_ref check
        if "campaign_id" in context:
            body_cid = body.get("campaign_id")
            if body_cid is not None and body_cid != context["campaign_id"]:
                raise ValidationError(
                    "CAMPAIGN_BINDING_MISMATCH",
                    f"Artifact campaign_id '{body_cid}' does not match context '{context['campaign_id']}'",
                )
            body_cref = body.get("campaign_ref")
            if isinstance(body_cref, str) and body_cref != context["campaign_id"]:
                raise ValidationError(
                    "CAMPAIGN_BINDING_MISMATCH",
                    f"Artifact campaign_ref '{body_cref}' does not match context '{context['campaign_id']}'",
                )
            elif isinstance(body_cref, Mapping) and "campaign_id" in body_cref:
                if body_cref["campaign_id"] != context["campaign_id"]:
                    raise ValidationError(
                        "CAMPAIGN_BINDING_MISMATCH",
                        f"Artifact campaign_ref campaign_id '{body_cref['campaign_id']}' does not match context '{context['campaign_id']}'",
                    )

        # 2. Source generation check
        if "source_generation_ref" in context:
            ctx_sg = context["source_generation_ref"]
            ctx_sg_dig = ctx_sg.get("revision_digest") if isinstance(ctx_sg, Mapping) else str(ctx_sg)
            body_sg = body.get("source_generation_ref")
            if body_sg is not None:
                body_sg_dig = body_sg.get("revision_digest") if isinstance(body_sg, Mapping) else str(body_sg)
                if body_sg_dig != ctx_sg_dig:
                    raise ValidationError(
                        "SOURCE_BINDING_MISMATCH",
                        f"Artifact source_generation_ref '{body_sg_dig}' does not match context '{ctx_sg_dig}'",
                    )

        # 3. History cut check
        if "history_cut" in context:
            ctx_cut = context["history_cut"]
            cut_fields = (
                "input_history_cut", "assigned_history_cut", "creation_input_history_cut",
                "assessment_input_history_cut", "selection_input_history_cut",
                "admission_input_history_cut", "history_cut"
            )
            for f in cut_fields:
                if f in body and isinstance(body[f], Mapping):
                    body_cut = body[f]
                    for key in ("campaign_id", "accepted_head_seq", "accepted_head_hash", "commit_seq", "commit_hash"):
                        if key in ctx_cut and key in body_cut and ctx_cut[key] != body_cut[key]:
                            raise ValidationError(
                                "STALE_HISTORY_CUT",
                                f"Artifact {f} {key} '{body_cut[key]}' does not match context '{ctx_cut[key]}'",
                            )

        # 4. Governing policy ref check
        if "governing_policy_ref" in context:
            ctx_pol = context["governing_policy_ref"]
            ctx_pol_str = ctx_pol.get("revision_digest") if isinstance(ctx_pol, Mapping) else str(ctx_pol)
            for pol_field, body_pol in body.items():
                if pol_field.endswith("_policy_ref") or pol_field in ("governing_policy_ref", "policy_ref", "admission_policy_ref", "selection_policy_ref", "challenge_policy_ref", "challenge_freshness_policy_ref", "relationship_policy_ref"):
                    body_pol_str = body_pol.get("revision_digest") if isinstance(body_pol, Mapping) else str(body_pol)
                    if body_pol_str != ctx_pol_str:
                        raise ValidationError(
                            "POLICY_BINDING_MISMATCH",
                            f"Artifact {pol_field} '{body_pol_str}' does not match context '{ctx_pol_str}'",
                        )


def foundation_qualification():
    """Return deterministic identity evidence for all F2-bound kinds."""
    manifest = schema_identity_manifest(kinds=tuple(F2_KINDS))
    manifest["validator_order"] = ["parse", "schema", "canonicalization", "typed_refs",
                                    "source_campaign_scope", "policy_spec", "history_cut", "evidence_applicability"]
    return manifest


__all__ = ["ValidatedIdentity", "LayeredValidator", "foundation_qualification"]

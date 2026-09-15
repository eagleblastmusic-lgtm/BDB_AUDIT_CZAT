"""Byte-pinned canonical contract overlay for post-R5.3.1 remediation kinds.

The historical active Registry remains byte-for-byte pinned.  This module adds
small canonical contracts only when their overlay bytes, identity, base-registry
binding and reference semantics all verify.  Runtime callers cannot replace or
shadow these contracts.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

from .canonical_json import parse
from .errors import ValidationError

OVERLAY_FILENAME = "artifact_contract_overlay_r5_3_3.json"
OVERLAY_SHA256 = "b419042b283a6fd28a55f2e44d4ae97698c92b48211a5c846ea184f3933aad46"
OVERLAY_ID = "BDB-AUDIT-V2-CANONICAL-CONTRACT-OVERLAY-R5-3-3"
OVERLAY_VERSION = 1


def _load_overlay(registry) -> dict:
    raw = Path(__file__).with_name(OVERLAY_FILENAME).read_bytes()
    if hashlib.sha256(raw).hexdigest() != OVERLAY_SHA256:
        raise ValidationError("CANONICAL_OVERLAY_PIN_MISMATCH")
    doc = parse(raw)
    if (
        doc.get("overlay_id") != OVERLAY_ID
        or doc.get("overlay_version") != OVERLAY_VERSION
        or doc.get("base_registry_id") != registry.registry_id
    ):
        raise ValidationError("CANONICAL_OVERLAY_IDENTITY_MISMATCH")
    if set(doc) != {"overlay_id", "overlay_version", "base_registry_id", "contracts"}:
        raise ValidationError("CANONICAL_OVERLAY_SEMANTICS_MISMATCH")
    contracts = doc.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        raise ValidationError("CANONICAL_OVERLAY_EMPTY")
    return doc


def _validate_contract(registry, row: dict) -> tuple[str, str]:
    if not isinstance(row, dict):
        raise ValidationError("INVALID_CONTRACT_ENTRY")
    kind = row.get("kind")
    version = str(row.get("version", "1"))
    if not isinstance(kind, str) or not kind:
        raise ValidationError("MISSING_CONTRACT_KIND")
    if any(c.get("kind") == kind and str(c.get("version")) == version for c in registry.document.get("contracts", ())):
        raise ValidationError("CANONICAL_CONTRACT_COLLISION", kind)
    registry.role(row.get("canonical_role"))
    if row.get("reference_contract_mode") != "EXPLICIT_COMPLETE":
        raise ValidationError("EXPLICIT_COMPLETE_REFERENCE_CONTRACT_MISMATCH")
    schema_ref = row.get("schema_ref")
    if schema_ref != f"BDB_SCHEMA_REGISTRY::{kind}/{version}":
        raise ValidationError("CANONICAL_OVERLAY_SCHEMA_MISMATCH", kind)
    semantics = registry.document.get("reference_class_semantics", {})
    for ref in row.get("material_refs", ()):
        if not isinstance(ref, dict):
            raise ValidationError("INVALID_CONTRACT_ENTRY")
        if ref.get("ref_class") not in semantics:
            raise ValidationError("UNREGISTERED_REFERENCE_CLASS")
        for target in ref.get("allowed", ()):
            registry.target(target)
    return kind, version


def install_canonical_contract_overlay(registry_cls) -> None:
    """Install the pinned overlay exactly once on ContractRegistry."""
    if getattr(registry_cls, "_bdb_canonical_overlay_installed", False):
        return

    original_init = registry_cls.__init__

    def init_with_overlay(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        doc = _load_overlay(self)
        keys: set[tuple[str, str]] = set()
        for row in doc["contracts"]:
            key = _validate_contract(self, row)
            if key in keys:
                raise ValidationError("DUPLICATE_CONTRACT_KIND")
            keys.add(key)
            self.register_extension_contract(deepcopy(row))
        self._canonical_overlay_keys = frozenset(keys)
        self._canonical_overlay_digest = OVERLAY_SHA256

    def canonical_contract_kinds(self):
        baseline = {
            row["kind"]
            for row in self.document.get("contracts", ())
            if isinstance(row, dict) and isinstance(row.get("kind"), str)
        }
        overlay = {kind for kind, _version in getattr(self, "_canonical_overlay_keys", ())}
        return frozenset(baseline | overlay)

    def canonical_overlay_digest(self):
        return getattr(self, "_canonical_overlay_digest", "")

    registry_cls.__init__ = init_with_overlay
    registry_cls.canonical_contract_kinds = property(canonical_contract_kinds)
    registry_cls.canonical_overlay_digest = property(canonical_overlay_digest)
    registry_cls._bdb_canonical_overlay_installed = True


__all__ = [
    "OVERLAY_FILENAME",
    "OVERLAY_SHA256",
    "OVERLAY_ID",
    "install_canonical_contract_overlay",
]

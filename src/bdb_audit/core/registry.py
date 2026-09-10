"""R5.3 Data Contracts §§184–187: pinned contracts, never accepted state.

Semantic validation of candidate definitions compares complete contract rows
against the byte-pinned authority. Ref/cardinality/order prose is not guessed
from a subset of convenient field names.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

from .canonical_json import parse, canonical_bytes
from .errors import ValidationError
from .ids import REGISTRY_SHA256

GOLDEN_SHA256 = "7bee0013d179adc8eba14d07c2c3ea159de0b8e37be9a9f6dcd55969550b7772"
REGISTRY_ID = "BDB-AUDIT-V2-ARTIFACT-CONTRACT-REGISTRY-R5-3-1"
GOLDEN_ID = "BDB-AUDIT-V2-FOUNDATION-GOLDEN-VECTORS-R5-3-1"


def _pinned(raw, digest, code):
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != digest:
        raise ValidationError(code)
    return parse(raw)


class ContractRegistry:
    def __init__(self, raw=None):
        if raw is None:
            raw = Path(__file__).with_name("artifact_contract_registry_r5_3.json").read_bytes()
        doc = _pinned(raw, REGISTRY_SHA256, "REGISTRY_PIN_MISMATCH")
        if doc["registry_id"] != REGISTRY_ID or doc["registry_version"] != 3:
            raise ValidationError("REGISTRY_IDENTITY_MISMATCH")
        self._raw = raw
        self._doc = doc
        self._contracts = {(r["kind"], r["version"]): r for r in doc["contracts"]}
        self.validate_definition(doc)

    @property
    def document(self):
        return deepcopy(self._doc)

    def contract(self, kind, version="1"):
        try:
            return deepcopy(self._contracts[(kind, version)])
        except (KeyError, TypeError) as exc:
            raise ValidationError("UNREGISTERED_CONTRACT_KIND", str(kind)) from exc

    def role(self, role):
        if role not in self._doc["canonical_role_domain"]:
            raise ValidationError("UNKNOWN_CANONICAL_ROLE")
        return role

    def target(self, kind):
        if kind not in self._doc["reference_target_classes"] and (kind, "1") not in self._contracts:
            raise ValidationError("UNRESOLVED_REFERENCE_TARGET", str(kind))
        return kind

    def reference_parity(self, kind, material_refs, version="1"):
        row = self.contract(kind, version)
        if row["reference_contract_mode"] == "EXPLICIT_COMPLETE":
            if canonical_bytes(material_refs) != canonical_bytes(row["material_refs"]):
                raise ValidationError("EXPLICIT_COMPLETE_REFERENCE_CONTRACT_MISMATCH")

    def validate_definition(self, candidate):
        seen = set()
        for row in candidate.get("contracts", []):
            kind, version = row.get("kind"), row.get("version")
            expected = self.contract(kind, version)
            if (kind, version) in seen:
                raise ValidationError("DUPLICATE_CONTRACT_KIND")
            seen.add((kind, version))
            self.role(row.get("canonical_role"))
            if kind in self._doc["foundation_inline_reference_contract_kinds"]:
                if row.get("reference_contract_mode") != "EXPLICIT_COMPLETE":
                    raise ValidationError("EXPLICIT_COMPLETE_REFERENCE_CONTRACT_MISMATCH")
            for ref in row.get("material_refs", []):
                if ref.get("ref_class") not in self._doc["reference_class_semantics"]:
                    raise ValidationError("UNREGISTERED_REFERENCE_CLASS")
                for target in ref.get("allowed", []):
                    self.target(target)
            self.reference_parity(kind, row.get("material_refs"), version)
            if row.get("ordering_rules") != expected["ordering_rules"]:
                raise ValidationError("ORDERING_RULE_DEFECT")
            if row != expected:
                raise ValidationError("REGISTRY_CONTRACT_SEMANTICS_MISMATCH")
        if seen != set(self._contracts):
            raise ValidationError("REGISTRY_INCOMPLETE")
        for key, value in self._doc.items():
            if key != "contracts" and candidate.get(key) != value:
                raise ValidationError("REGISTRY_SEMANTICS_MISMATCH", key)
        if set(candidate) != set(self._doc):
            raise ValidationError("REGISTRY_SEMANTICS_MISMATCH")


def load_vectors(path):
    doc = _pinned(Path(path).read_bytes(), GOLDEN_SHA256, "GOLDEN_VECTOR_PIN_MISMATCH")
    if doc.get("vector_set_id") != GOLDEN_ID:
        raise ValidationError("GOLDEN_VECTOR_IDENTITY_MISMATCH")
    ids = [v["id"] for v in doc["vectors"]]
    if len(ids) != len(set(ids)):
        raise ValidationError("DUPLICATE_GOLDEN_VECTOR")
    return doc


def canonical_reference_set(refs):
    """Schema-prepared typed refs: full typed value provides the set sort key.

    Callers with field-specific sequence/tuple overrides must use those rules.
    Full typed identities participate, including schema and digest profile.
    Symbolic string refs are usable only by contract/vector-level checks.
    """
    def key(ref):
        if type(ref) is str:
            return (ref, "", "")
        return (ref["kind"], ref.get("logical_id", ""), ref["revision_digest"],
                ref["digest_profile"], canonical_bytes(ref["schema_revision_ref"]))
    ordered = sorted(refs, key=key)
    keys = [key(r) for r in ordered]
    if len(keys) != len(set(keys)):
        raise ValidationError("DUPLICATE_REFERENCE")
    return deepcopy(ordered)

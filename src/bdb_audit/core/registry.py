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
from .ids import ACTIVE_REGISTRY_FILENAME, REGISTRY_SHA256

GOLDEN_FILENAME = "foundation_golden_vectors_r5_3_1.json"
GOLDEN_SHA256 = "1beeedd979c06816480cc5adc144fd3470a7379630e6ed8d4a4770c5448c48e7"
REGISTRY_ID = "BDB-AUDIT-V2-ARTIFACT-CONTRACT-REGISTRY-R5-3-2"
REGISTRY_VERSION = 4
GOLDEN_ID = "BDB-AUDIT-V2-FOUNDATION-GOLDEN-VECTORS-R5-3-2"


def _pinned(raw, digest, code):
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != digest:
        raise ValidationError(code)
    return parse(raw)


class ContractRegistry:
    def __init__(self, raw=None):
        if raw is None:
            raw = Path(__file__).with_name(ACTIVE_REGISTRY_FILENAME).read_bytes()
        doc = _pinned(raw, REGISTRY_SHA256, "REGISTRY_PIN_MISMATCH")
        if doc["registry_id"] != REGISTRY_ID or doc["registry_version"] != REGISTRY_VERSION:
            raise ValidationError("REGISTRY_IDENTITY_MISMATCH")
        self._raw = raw
        self._doc = doc
        self._contracts = {(r["kind"], r["version"]): r for r in doc["contracts"]}
        self.validate_definition(doc)
        # R5.3 extension contracts for orchestrator / auditor submission artifacts (v2.0.3)
        self._extension_contracts: dict[tuple[str, str], dict] = {
            ("bdb_audit_lane_result", "1"): {
                "authoritative_for": "auditor lane result submission package",
                "canonical_role": "PROPOSAL",
                "consumer_roles": ["COORDINATOR", "VALIDATOR"],
                "identity_semantics": "BDB-CJSON-1 + BDB-OBJECT-DIGEST-1 unless RAW/EXPORT",
                "kind": "bdb_audit_lane_result",
                "lifecycle": "IMMUTABLE",
                "material_refs": [],
                "ordering_rules": {},
                "producer_authority": "AUDITOR_EXTERNAL",
                "reference_contract_mode": "SCHEMA_BOUND_BEFORE_FIRST_ACCEPTANCE",
                "required_validation_layers": ["L1", "L2", "L4", "L5"],
                "schema_ref": "BDB_SCHEMA_REGISTRY::bdb_audit_lane_result/1",
                "validation_profile": "DERIVED",
                "version": "1",
            }
        }

    @property
    def document(self):
        return deepcopy(self._doc)

    def register_extension_contract(self, contract_entry: dict) -> None:
        """Register a versioned artifact contract dynamically."""
        kind = contract_entry["kind"]
        version = contract_entry.get("version", "1")
        self._extension_contracts[(kind, version)] = deepcopy(contract_entry)

    def contract(self, kind, version="1"):
        if hasattr(self, "_extension_contracts") and (kind, version) in self._extension_contracts:
            return deepcopy(self._extension_contracts[(kind, version)])
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

    def precedence_profile(self, profile_name):
        """Return an exact machine profile; prose and kind-name inference are forbidden."""
        profiles = self._doc.get("order_only_precedence_profiles", {})
        try:
            return deepcopy(profiles[profile_name])
        except KeyError as exc:
            raise ValidationError("UNKNOWN_PRECEDENCE_PROFILE", str(profile_name)) from exc

    def active_precedence_profile(self, *, command_kind, commit_seq, expected_parent,
                                  profile_name="BDB_BOOTSTRAP_PRECEDENCE_V1"):
        profile = self.precedence_profile(profile_name)
        scope = profile["scope"]
        if (command_kind, commit_seq, expected_parent) != (
                scope["command_kind"], scope["commit_seq"], scope["expected_parent"]):
            return None
        return profile

    def order_only_edges(self, nodes, *, command_kind, commit_seq, expected_parent,
                         profile_name="BDB_BOOTSTRAP_PRECEDENCE_V1"):
        """Build only exact profile edges; no prose/kind-name inference."""
        profile = self.active_precedence_profile(
            command_kind=command_kind, commit_seq=commit_seq,
            expected_parent=expected_parent, profile_name=profile_name)
        if profile is None:
            return set()
        by_kind = {}
        for node in nodes:
            kind = node.get("kind") if isinstance(node, dict) else getattr(node, "kind", None)
            by_kind.setdefault(kind, []).append(node)
        groups = profile["ordered_kind_groups"]
        # A group may be absent. Pair every present group with every later
        # present group, preserving the exact profile relation without
        # inferring edges from prose or kind-name conventions.
        edges = set()
        def node_id(node):
            return node.get("id") if isinstance(node, dict) else getattr(node, "node_id")
        for i, group in enumerate(groups):
            left_nodes = [n for kind in group for n in by_kind.get(kind, ())]
            if not left_nodes:
                continue
            for later_group in groups[i + 1:]:
                right_nodes = [n for kind in later_group for n in by_kind.get(kind, ())]
                edges.update(
                    (node_id(left), node_id(right))
                    for left in left_nodes for right in right_nodes
                    if node_id(left) != node_id(right)
                )
        return edges

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


def load_vectors(path=None):
    if path is None:
        path = Path(__file__).with_name(GOLDEN_FILENAME)
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

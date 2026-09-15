"""One deterministic Kahn ordering for typed plus order-only bootstrap edges."""
from dataclasses import dataclass, field
import heapq
from typing import Any

from ..core.errors import ValidationError
from ..core.registry import ContractRegistry
from .objects import CanonicalObject, ObjectRef


@dataclass(frozen=True)
class ClosureNode:
    """A prepared same-commit content node.

    ``depends_on`` is the already schema-resolved typed dependency identity for
    tests/builders. Production object nodes derive it from body refs instead of
    guessing from prose or kind names.
    """
    node_id: str
    kind: str
    logical_id: str = ""
    revision_digest: str = ""
    depends_on: tuple[str, ...] = field(default_factory=tuple)
    content_refs: tuple[ObjectRef, ...] = field(default_factory=tuple)
    value: Any = None

    @classmethod
    def from_object(cls, obj: CanonicalObject, node_id=None):
        ref = obj.ref
        node_id = node_id or ref.revision_digest
        return cls(node_id=node_id, kind=obj.kind, logical_id=obj.logical_id or "",
                   revision_digest=ref.revision_digest, content_refs=obj.content_refs, value=obj)


def _node(value):
    if isinstance(value, ClosureNode):
        return value
    if isinstance(value, CanonicalObject):
        return ClosureNode.from_object(value)
    if isinstance(value, dict):
        node_id = value.get("id", value.get("node_id"))
        if not isinstance(node_id, str) or not node_id:
            raise ValidationError("CLOSURE_NODE_ID_REQUIRED")
        deps = tuple(value.get("depends_on", ()))
        if any(not isinstance(dep, str) for dep in deps):
            raise ValidationError("TYPED_REF_INCOMPLETE")
        return ClosureNode(node_id=node_id, kind=value.get("kind", ""),
                           logical_id=value.get("logical_id", ""),
                           revision_digest=value.get("revision_digest", value.get("digest", "")),
                           depends_on=deps, value=value)
    raise ValidationError("CLOSURE_NODE_INVALID")


def _prior_accepted_refs(value):
    """Yield typed PRIOR_ACCEPTED_ONLY refs embedded in a prepared body."""
    if isinstance(value, dict):
        if {"kind", "revision_digest", "digest_profile", "schema_revision_ref"}.issubset(value):
            if value.get("ref_class") == "PRIOR_ACCEPTED_ONLY":
                yield ObjectRef.from_dict(value)
            return
        for child in value.values():
            yield from _prior_accepted_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _prior_accepted_refs(child)


def typed_dependencies(nodes):
    """Return dependency edges (dependency, consumer) from complete refs.

    ``PRIOR_ACCEPTED_ONLY`` is a global temporal reference class in the pinned
    R5.3 registry: its target must already be accepted before the current
    command input cut. Therefore no object using that class may consume a
    target materialized in the same prepared closure, regardless of kind.
    """
    prepared = [_node(n) for n in nodes]
    by_ref = {(n.kind, n.revision_digest): n.node_id for n in prepared if n.revision_digest}
    by_id = {n.node_id: n for n in prepared}
    edges = set()
    for n in prepared:
        for dep in n.depends_on:
            if dep not in by_id:
                raise ValidationError("DANGLING_CONTENT_REF", dep)
            if dep == n.node_id:
                raise ValidationError("SELF_CONTENT_REF")
            edges.add((dep, n.node_id))
        for ref in n.content_refs:
            target = by_ref.get((ref.kind, ref.revision_digest))
            if target is None:
                # CONTENT_OR_PRIOR is allowed to point to already accepted
                # immutable content; CONTENT_OBJECT requires current closure.
                if ref.ref_class == "CONTENT_OBJECT":
                    raise ValidationError("DANGLING_CONTENT_REF", ref.revision_digest)
                continue
            if target == n.node_id:
                raise ValidationError("SELF_CONTENT_REF")
            edges.add((target, n.node_id))

        body = n.value.body if isinstance(n.value, CanonicalObject) else None
        if body is None:
            continue
        for ref in _prior_accepted_refs(body):
            target = by_ref.get((ref.kind, ref.revision_digest))
            if target is None:
                continue
            raise ValidationError(
                "PRIOR_ACCEPTED_REFERENCE_REQUIRED",
                f"{n.kind} consumes same-commit {ref.kind} through PRIOR_ACCEPTED_ONLY",
            )
    return prepared, edges


def canonical_order(nodes, *, command_kind=None, commit_seq=None,
                    expected_parent=None, profile_name="BDB_BOOTSTRAP_PRECEDENCE_V1",
                    expected=None, registry=None):
    """Run exactly one Kahn sort over typed-edge union order-only profile edges."""
    registry = registry or ContractRegistry()
    prepared, edges = typed_dependencies(nodes)
    by_id = {}
    for n in prepared:
        if n.node_id in by_id:
            raise ValidationError("DUPLICATE_CONTENT_REFERENCE", n.node_id)
        if not n.kind:
            raise ValidationError("UNREGISTERED_CONTRACT_KIND")
        registry.contract(n.kind)
        by_id[n.node_id] = n
    if command_kind is not None:
        if commit_seq is None or expected_parent is None:
            raise ValidationError("PRECEDENCE_SCOPE_INCOMPLETE")
        order_edges = registry.order_only_edges(
            prepared, command_kind=command_kind, commit_seq=commit_seq,
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
            if key not in candidate:
                raise ValidationError("REGISTRY_INCOMPLETE", key)
            if key != "contracts" and candidate[key] != value:
                raise ValidationError("REGISTRY_CONTRACT_SEMANTICS_MISMATCH", key)


def canonical_reference_set(refs):
    """Canonical deterministic set ordering for typed immutable refs."""
    def key(ref):
        return (ref.get("kind", ""), ref.get("logical_id", ""),
                ref.get("revision_digest", ""), ref.get("schema_revision_ref", ""))
    ordered = sorted(refs, key=key)
    if len({(r.get("kind"), r.get("revision_digest")) for r in ordered}) != len(ordered):
        raise ValidationError("DUPLICATE_CONTENT_REFERENCE")
    return ordered
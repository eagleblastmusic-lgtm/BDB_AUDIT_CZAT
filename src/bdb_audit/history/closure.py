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
    """Yield typed PRIOR_ACCEPTED_ONLY refs embedded in a prepared body.

    A PRIOR_ACCEPTED_ONLY edge is deliberately excluded from the ordinary
    content dependency graph: it must already exist in the parent accepted
    history and therefore can never be satisfied by another object prepared in
    the same closure.  Walking it separately lets the closure gate reject the
    temporal self-certification pattern before persistence.
    """
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
    """Return dependency edges (dependency, consumer) from complete refs."""
    prepared = [_node(n) for n in nodes]
    by_ref = {(n.kind, n.revision_digest): n.node_id for n in prepared if n.revision_digest}
    by_id = {n.node_id: n for n in prepared}
    edges = set()
    finalization_kinds = {"campaign_conclusion", "final_assurance_case", "release_qualification"}
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
        if body is not None:
            for ref in _prior_accepted_refs(body):
                target = by_ref.get((ref.kind, ref.revision_digest))
                if target is None:
                    continue
                if n.kind in finalization_kinds or ref.kind in finalization_kinds | {"stop_evaluation"}:
                    raise ValidationError(
                        "FINALIZATION_TEMPORAL_BINDING_CONFLICT",
                        f"{n.kind} consumes same-commit {ref.kind} through PRIOR_ACCEPTED_ONLY",
                    )
                raise ValidationError(
                    "HISTORY_INPUT_SAME_COMMIT_FORBIDDEN",
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
        edges.update(order_edges)
    adjacency = {n.node_id: set() for n in prepared}
    indegree = {n.node_id: 0 for n in prepared}
    for dep, consumer in edges:
        if dep not in by_id or consumer not in by_id:
            raise ValidationError("DANGLING_CONTENT_REF")
        if consumer not in adjacency[dep]:
            adjacency[dep].add(consumer)
            indegree[consumer] += 1

    def key(node_id):
        n = by_id[node_id]
        is_cmd = 0 if n.kind == "command_envelope" else 1
        return (is_cmd, n.kind, n.logical_id or "", n.revision_digest or "", node_id)

    heap = [(key(n.node_id), n.node_id) for n in prepared if indegree[n.node_id] == 0]
    heapq.heapify(heap)
    ordered = []
    while heap:
        _, node_id = heapq.heappop(heap)
        ordered.append(node_id)
        for child in sorted(adjacency[node_id], key=key):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(heap, (key(child), child))
    if len(ordered) != len(prepared):
        raise ValidationError("CONTENT_REFERENCE_CYCLE")
    if expected is not None and list(expected) != ordered:
        raise ValidationError("FUTURE_CONTENT_REF_OR_NON_TOPOLOGICAL_CLOSURE")
    return ordered


def order_nodes(nodes, **kwargs):
    by_id = {_node(n).node_id: _node(n) for n in nodes}
    return [by_id[node_id] for node_id in canonical_order(nodes, **kwargs)]

"""Evidence Graph, multidimensional independence assessment, and invalidation propagation (WP-F4-07)."""
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence, Set
import hashlib

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id, validate_id
from ..history.objects import CanonicalObject, ObjectRef
from .models import (
    Observation,
    DependencyIndependenceAssessment,
    EvidenceApplicabilityAssessment,
    EvidenceQualificationAssessment,
    EvidenceInvalidation,
    _ref_dict,
)

# 8 Normative Independence Dimensions (R5.3 §48)
INDEPENDENCE_DIMENSIONS = (
    "PROCESS_INDEPENDENCE",
    "INSTANCE_INDEPENDENCE",
    "IMPLEMENTATION_INDEPENDENCE",
    "STORAGE_READ_PATH_INDEPENDENCE",
    "EXTERNAL_BOUNDARY_INDEPENDENCE",
    "ORACLE_INDEPENDENCE",
    "MODEL_AGENT_INDEPENDENCE",
    "HARNESS_INDEPENDENCE",
)

NODE_TYPES = {
    "OBSERVATION",
    "PROCESS",
    "INSTANCE",
    "IMPLEMENTATION",
    "STORAGE",
    "PARSER",
    "CACHE",
    "HARNESS",
    "FIXTURE",
    "ORACLE",
    "ENVIRONMENT",
    "DEPENDENCY",
    "EXTERNAL_BOUNDARY",
    "HYPOTHESIS",
    "EXPERIMENT",
    "EXECUTION",
    "CLAIM",
    "APPLICABILITY_ASSESSMENT",
    "INDEPENDENCE_ASSESSMENT",
    "QUALIFICATION_ASSESSMENT",
    "INVALIDATION",
}

EDGE_RELATIONS = {
    "DEPENDS_ON",
    "OBSERVES",
    "EXECUTES",
    "TESTS",
    "ASSESSES",
    "INVALIDATES",
    "SUPPORTS",
    "REFUTES",
    "EVALUATES",
}


def _extract_id(item: Any) -> str:
    if isinstance(item, dict):
        return item.get("revision_digest") or item.get("logical_id") or item.get("id") or str(item)
    if isinstance(item, (ObjectRef, CanonicalObject)):
        return item.digest
    return str(item)


def assess_multidimensional_independence(
    claim_ref: Any,
    lane_a_deps: Mapping[str, Sequence[Any]],
    lane_b_deps: Mapping[str, Sequence[Any]],
    required_dimensions: Sequence[str] = INDEPENDENCE_DIMENSIONS,
) -> dict:
    """Assess independence between two observation lanes across 8 dimensions.

    Adversarial rule (R5.3 §48, Roadmap §62-63):
    Fresh process or fresh instance does NOT establish independence if both lanes
    share the same parser, cache, storage read path, or oracle.
    """
    dimension_results = {}
    shared_deps: dict[str, list[str]] = {}
    independent_deps: dict[str, list[str]] = {}
    failed_dimensions = []

    for dim in required_dimensions:
        deps_a = {_extract_id(x) for x in lane_a_deps.get(dim, [])}
        deps_b = {_extract_id(x) for x in lane_b_deps.get(dim, [])}

        overlap = deps_a & deps_b
        if overlap:
            dimension_results[dim] = "SHARED_DEPENDENCY"
            shared_deps[dim] = sorted(overlap)
            failed_dimensions.append(dim)
        else:
            dimension_results[dim] = "INDEPENDENT"
            independent_deps[dim] = sorted(deps_a | deps_b)

    all_shared = []
    for s_list in shared_deps.values():
        all_shared.extend(s_list)
    all_shared = sorted(set(all_shared))

    overall_result = "INDEPENDENT" if not failed_dimensions else "SHARED_DEPENDENCY"

    return {
        "claim_ref": _ref_dict(claim_ref),
        "overall_result": overall_result,
        "is_independent": overall_result == "INDEPENDENT",
        "dimension_results": dimension_results,
        "failed_dimensions": sorted(failed_dimensions),
        "shared_dependencies": all_shared,
        "shared_by_dimension": shared_deps,
        "independent_by_dimension": independent_deps,
    }


@dataclass
class EvidenceNode:
    node_id: str
    node_type: str
    data: dict = field(default_factory=dict)
    ref: dict | None = None
    status: str = "ACTIVE"
    satisfies_completion: bool = True

    def __post_init__(self):
        if self.node_type not in NODE_TYPES:
            raise ValidationError("INVALID_NODE_TYPE", f"Unknown node type: {self.node_type}")


@dataclass(frozen=True)
class EvidenceEdge:
    source: str
    target: str
    relation: str = "DEPENDS_ON"

    def __post_init__(self):
        if self.relation not in EDGE_RELATIONS:
            raise ValidationError("INVALID_EDGE_RELATION", f"Unknown relation: {self.relation}")


class EvidenceGraph:
    """Directed Acyclic Graph of evidence entities, dependencies, and qualifications.

    Supports cycle detection, invalidation traversal, and current support evaluation.
    """

    def __init__(self):
        self._nodes: dict[str, EvidenceNode] = {}
        self._outgoing: dict[str, list[EvidenceEdge]] = {}  # source -> [edges]
        self._incoming: dict[str, list[EvidenceEdge]] = {}  # target -> [edges]

    def add_node(
        self,
        node_id: str,
        node_type: str,
        data: dict | None = None,
        ref: Any = None,
        status: str = "ACTIVE",
        satisfies_completion: bool = True,
    ) -> EvidenceNode:
        if node_id in self._nodes:
            raise ValidationError("DUPLICATE_NODE_ID", f"Node already exists: {node_id}")
        node = EvidenceNode(
            node_id=node_id,
            node_type=node_type,
            data=dict(data or {}),
            ref=_ref_dict(ref) if ref is not None else None,
            status=status,
            satisfies_completion=satisfies_completion,
        )
        self._nodes[node_id] = node
        self._outgoing[node_id] = []
        self._incoming[node_id] = []
        return node

    def get_node(self, node_id: str) -> EvidenceNode | None:
        return self._nodes.get(node_id)

    @property
    def nodes(self) -> Mapping[str, EvidenceNode]:
        return self._nodes

    def add_edge(self, source: str, target: str, relation: str = "DEPENDS_ON") -> EvidenceEdge:
        if source not in self._nodes:
            raise ValidationError("MISSING_SOURCE_NODE", f"Source node {source} not in graph")
        if target not in self._nodes:
            raise ValidationError("MISSING_TARGET_NODE", f"Target node {target} not in graph")

        edge = EvidenceEdge(source=source, target=target, relation=relation)
        self._outgoing[source].append(edge)
        self._incoming[target].append(edge)

        # Validate acyclicity on every edge addition to fail-closed immediately
        self.validate_acyclic()
        return edge

    def detect_cycles(self) -> list[list[str]]:
        """Detect all cycles using DFS recursion-stack tracking."""
        visited: set[str] = set()
        rec_stack: list[str] = []
        cycles: list[list[str]] = []

        def dfs(curr: str):
            visited.add(curr)
            rec_stack.append(curr)

            for edge in self._outgoing.get(curr, []):
                nxt = edge.target
                if nxt in rec_stack:
                    idx = rec_stack.index(nxt)
                    cycles.append(rec_stack[idx:] + [nxt])
                elif nxt not in visited:
                    dfs(nxt)

            rec_stack.pop()

        for node_id in sorted(self._nodes.keys()):
            if node_id not in visited:
                dfs(node_id)

        return cycles

    def validate_acyclic(self) -> None:
        """Raise ValidationError if the graph contains any cycle."""
        cycles = self.detect_cycles()
        if cycles:
            cycle_repr = " -> ".join(cycles[0])
            raise ValidationError("EVIDENCE_GRAPH_CYCLE", f"Cycle detected in evidence graph: {cycle_repr}")

    def get_dependencies(self, node_id: str) -> list[str]:
        """Return nodes that node_id directly depends on (source -> target)."""
        return [edge.target for edge in self._outgoing.get(node_id, [])]

    def get_dependents(self, node_id: str) -> list[str]:
        """Return nodes that directly depend on node_id (target <- source)."""
        return [edge.source for edge in self._incoming.get(node_id, [])]

    def propagate_invalidation(
        self,
        invalidated_ids: Sequence[str] | str,
        reason: str = "DEPENDENCY_INVALIDATION",
    ) -> dict:
        """Propagate invalidation downstream to all dependent qualifications and assessments.

        If node X is invalidated, any node Y where Y depends on X (directly or transitively)
        is degraded to STALE or INVALIDATED, and satisfies_completion becomes False.
        """
        if isinstance(invalidated_ids, str):
            roots = [invalidated_ids]
        else:
            roots = list(invalidated_ids)

        for r in roots:
            if r not in self._nodes:
                raise ValidationError("INVALIDATION_NODE_NOT_FOUND", f"Node {r} not in graph")

        # BFS / queue to find full downstream transitive closure
        queue = list(roots)
        visited: set[str] = set(roots)
        transitive_affected: set[str] = set()
        degraded_qualifications: list[str] = []

        # Mark roots as INVALIDATED
        for r in roots:
            node = self._nodes[r]
            node.status = "INVALIDATED"
            node.satisfies_completion = False
            node.data["invalidation_reason"] = reason

        while queue:
            curr = queue.pop(0)
            # Find everything that depends on curr (incoming edges source -> curr)
            for dependent_id in self.get_dependents(curr):
                if dependent_id not in visited:
                    visited.add(dependent_id)
                    transitive_affected.add(dependent_id)
                    queue.append(dependent_id)

                    dep_node = self._nodes[dependent_id]
                    if dep_node.node_type == "QUALIFICATION_ASSESSMENT":
                        dep_node.status = "STALE"
                        dep_node.satisfies_completion = False
                        dep_node.data["degraded_by_invalidation"] = True
                        dep_node.data["invalidation_source"] = curr
                        degraded_qualifications.append(dependent_id)
                    else:
                        dep_node.status = "INVALIDATED"
                        dep_node.satisfies_completion = False
                        dep_node.data["degraded_by_invalidation"] = True

        return {
            "root_invalidations": sorted(roots),
            "transitive_invalidations": sorted(transitive_affected),
            "degraded_qualifications": sorted(degraded_qualifications),
            "total_affected": len(roots) + len(transitive_affected),
        }

    def calculate_current_support(self, claim_id: str) -> dict:
        """Calculate current active evidence support for a claim.

        Inspects all QUALIFICATION_ASSESSMENT nodes connected to this claim.
        Only ACTIVE qualifications with satisfies_completion=True count toward support.
        """
        supporting_quals = []
        refuting_quals = []
        stale_or_invalid_quals = []

        for node_id, node in sorted(self._nodes.items()):
            if node.node_type == "QUALIFICATION_ASSESSMENT":
                # Check if this qualification assesses or is linked to the claim
                deps = self.get_dependencies(node_id)
                claim_linked = (claim_id in deps) or (node.data.get("claim_id") == claim_id)
                if not claim_linked:
                    continue

                if node.status in ("STALE", "INVALIDATED") or not node.satisfies_completion:
                    stale_or_invalid_quals.append(node_id)
                else:
                    result = node.data.get("result", "SUPPORTS")
                    if result == "SUPPORTS":
                        supporting_quals.append(node_id)
                    elif result == "REFUTES":
                        refuting_quals.append(node_id)
                    else:
                        stale_or_invalid_quals.append(node_id)

        if supporting_quals and refuting_quals:
            effective_status = "CONTRADICTED"
        elif supporting_quals:
            effective_status = "SUPPORTED"
        elif refuting_quals:
            effective_status = "REFUTED"
        elif stale_or_invalid_quals:
            effective_status = "EVIDENCE_INVALIDATED"
        else:
            effective_status = "NO_EVIDENCE"

        return {
            "claim_id": claim_id,
            "effective_status": effective_status,
            "supporting_qualifications": supporting_quals,
            "refuting_qualifications": refuting_quals,
            "stale_or_invalid_qualifications": stale_or_invalid_quals,
            "active_support_count": len(supporting_quals),
            "active_refute_count": len(refuting_quals),
        }

    def to_dict(self) -> dict:
        """Export graph to deterministic dictionary representation."""
        nodes_dict = {
            nid: {
                "node_type": n.node_type,
                "data": n.data,
                "status": n.status,
                "satisfies_completion": n.satisfies_completion,
                "ref": n.ref,
            }
            for nid, n in sorted(self._nodes.items())
        }
        edges_list = [
            {"source": e.source, "target": e.target, "relation": e.relation}
            for source, edges in sorted(self._outgoing.items())
            for e in sorted(edges, key=lambda x: (x.target, x.relation))
        ]
        return {
            "nodes": nodes_dict,
            "edges": edges_list,
        }

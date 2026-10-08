"""Failure Interaction Graph Engine (WP-E5-01 / M36 / §94 / Data Contracts §69).

Represents interactions between failure modes, root-cause families, obligations, and surfaces.
Normative constraints:
- Graph is an analysis/planning input, NOT a second RootCause or Finding authority.
- Correlation != causation: all edges require explicit supporting refs and provenance.
- Strict accepted-history binding via HistoryCut.
- Handles invalidated support, contradicted edges, stale graph inputs, and bounded combinatorics.
- Deterministic reconstruction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import itertools
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id


NODE_KINDS = {
    "FAILURE_MODE",
    "ROOT_CAUSE_FAMILY",
    "OBLIGATION",
    "SURFACE",
}

EDGE_RELATIONS = {
    "COMPOUND_TRIGGER",
    "SHARED_SURFACE",
    "CASCADE",
    "AMPLIFIES",
    "EXACERBATES",
    "INHIBITS",
}

VALID_STATUSES = {"VALID", "INVALIDATED", "CONTRADICTED", "STALE"}
VALID_MATERIALITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"}


@dataclass(frozen=True)
class InteractionNode:
    node_id: str
    node_kind: str
    provenance_ref: dict[str, Any]
    accepted_history_binding: dict[str, Any]
    supporting_refs: tuple[dict[str, Any], ...]
    history_cut: dict[str, Any]
    materiality: str = "MEDIUM"
    applicability: bool = True
    status: str = "VALID"

    def __post_init__(self):
        if self.node_kind not in NODE_KINDS:
            raise ValidationError(
                "INVALID_NODE_KIND",
                f"Unknown node_kind {self.node_kind}, must be one of {sorted(NODE_KINDS)}",
            )
        if not self.provenance_ref:
            raise ValidationError("MISSING_PROVENANCE", f"Node {self.node_id} must have provenance_ref")
        if not self.history_cut:
            raise ValidationError("MISSING_HISTORY_CUT", f"Node {self.node_id} must have history_cut")
        if self.materiality not in VALID_MATERIALITIES:
            raise ValidationError(
                "INVALID_MATERIALITY",
                f"Invalid materiality {self.materiality}, must be one of {sorted(VALID_MATERIALITIES)}",
            )
        if self.status not in VALID_STATUSES:
            raise ValidationError("INVALID_STATUS", f"Invalid status {self.status}")

    def body(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_kind": self.node_kind,
            "provenance_ref": dict(self.provenance_ref),
            "accepted_history_binding": dict(self.accepted_history_binding),
            "supporting_refs": [dict(r) for r in self.supporting_refs],
            "history_cut": dict(self.history_cut),
            "materiality": self.materiality,
            "applicability": self.applicability,
            "status": self.status,
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()


@dataclass(frozen=True)
class InteractionEdge:
    edge_id: str
    source_nodes: tuple[str, ...]
    target_node: str
    relation: str
    supporting_refs: tuple[dict[str, Any], ...]
    provenance_ref: dict[str, Any]
    history_cut: dict[str, Any]
    is_contradicted: bool = False
    contradiction_reason: str = ""
    is_invalidated: bool = False
    invalidation_reason: str = ""
    status: str = "VALID"

    def __post_init__(self):
        if not self.source_nodes:
            raise ValidationError("EMPTY_SOURCES", "Interaction edge must have at least one source node")
        if not self.target_node:
            raise ValidationError("EMPTY_TARGET", "Interaction edge must have a target node")
        if self.relation not in EDGE_RELATIONS:
            raise ValidationError(
                "INVALID_RELATION",
                f"Relation {self.relation} must be one of {sorted(EDGE_RELATIONS)}",
            )
        # Correlation != causation: edge requires supporting refs unless contradicted
        if not self.supporting_refs and not self.is_contradicted:
            raise ValidationError(
                "UNSUPPORTED_INTERACTION_EDGE",
                f"Edge {self.edge_id} has no supporting refs; correlation != causation",
            )
        if not self.provenance_ref:
            raise ValidationError("MISSING_PROVENANCE", f"Edge {self.edge_id} must have provenance_ref")
        if not self.history_cut:
            raise ValidationError("MISSING_HISTORY_CUT", f"Edge {self.edge_id} must have history_cut")
        if self.status not in VALID_STATUSES:
            raise ValidationError("INVALID_STATUS", f"Invalid status {self.status}")

    @property
    def order(self) -> int:
        """Order of interaction: 1 for single failure, 2 for pair, >2 for higher-order."""
        all_nodes = set(self.source_nodes) | {self.target_node}
        return len(all_nodes)

    def body(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_nodes": list(self.source_nodes),
            "target_node": self.target_node,
            "relation": self.relation,
            "supporting_refs": [dict(r) for r in self.supporting_refs],
            "provenance_ref": dict(self.provenance_ref),
            "history_cut": dict(self.history_cut),
            "is_contradicted": self.is_contradicted,
            "contradiction_reason": self.contradiction_reason,
            "is_invalidated": self.is_invalidated,
            "invalidation_reason": self.invalidation_reason,
            "status": self.status,
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()


class FailureInteractionGraph:
    """Deterministic failure interaction graph engine."""

    def __init__(
        self,
        history_cut: dict[str, Any],
        max_interaction_order: int = 4,
        max_combinations_bound: int = 1000,
    ):
        if not history_cut:
            raise ValidationError("MISSING_HISTORY_CUT", "Graph must have a valid history_cut")
        self.history_cut = dict(history_cut)
        self.max_interaction_order = max_interaction_order
        self.max_combinations_bound = max_combinations_bound
        self._nodes: dict[str, InteractionNode] = {}
        self._edges: dict[str, InteractionEdge] = {}

    @property
    def nodes(self) -> Mapping[str, InteractionNode]:
        return self._nodes

    @property
    def edges(self) -> Mapping[str, InteractionEdge]:
        return self._edges

    def add_node(self, node: InteractionNode) -> None:
        # History cut consistency check
        if node.history_cut != self.history_cut:
            raise ValidationError(
                "STALE_GRAPH_INPUT",
                f"Node {node.node_id} history cut does not match graph history cut",
            )
        self._nodes[node.node_id] = node

    def add_edge(self, edge: InteractionEdge) -> None:
        if edge.history_cut != self.history_cut:
            raise ValidationError(
                "STALE_GRAPH_INPUT",
                f"Edge {edge.edge_id} history cut does not match graph history cut",
            )
        # Verify all nodes exist
        for s in edge.source_nodes:
            if s not in self._nodes:
                raise ValidationError("UNKNOWN_NODE", f"Source node {s} not found in graph")
        if edge.target_node not in self._nodes:
            raise ValidationError("UNKNOWN_NODE", f"Target node {edge.target_node} not found in graph")

        # Check bounds
        if edge.order > self.max_interaction_order:
            raise ValidationError(
                "INTERACTION_EXPLOSION_EXCEEDED",
                f"Edge order {edge.order} exceeds max_interaction_order {self.max_interaction_order}",
            )

        self._edges[edge.edge_id] = edge

    def apply_invalidations(self, invalidated_ref_ids: Set[str]) -> int:
        """Mark nodes and edges as INVALIDATED if any supporting ref is invalidated."""
        affected = 0
        new_nodes = {}
        for nid, node in self._nodes.items():
            has_invalid = any(
                r.get("revision_digest") in invalidated_ref_ids
                or r.get("id") in invalidated_ref_ids
                or r.get("ref_id") in invalidated_ref_ids
                for r in node.supporting_refs
            )
            if has_invalid and node.status != "INVALIDATED":
                new_nodes[nid] = InteractionNode(
                    node_id=node.node_id,
                    node_kind=node.node_kind,
                    provenance_ref=node.provenance_ref,
                    accepted_history_binding=node.accepted_history_binding,
                    supporting_refs=node.supporting_refs,
                    history_cut=node.history_cut,
                    materiality=node.materiality,
                    applicability=False,
                    status="INVALIDATED",
                )
                affected += 1
            else:
                new_nodes[nid] = node
        self._nodes = new_nodes

        new_edges = {}
        for eid, edge in self._edges.items():
            has_invalid_support = any(
                r.get("revision_digest") in invalidated_ref_ids
                or r.get("id") in invalidated_ref_ids
                or r.get("ref_id") in invalidated_ref_ids
                for r in edge.supporting_refs
            )
            sources_invalid = any(
                self._nodes[s].status == "INVALIDATED" for s in edge.source_nodes
            )
            target_invalid = self._nodes[edge.target_node].status == "INVALIDATED"

            if (has_invalid_support or sources_invalid or target_invalid) and edge.status != "INVALIDATED":
                new_edges[eid] = InteractionEdge(
                    edge_id=edge.edge_id,
                    source_nodes=edge.source_nodes,
                    target_node=edge.target_node,
                    relation=edge.relation,
                    supporting_refs=edge.supporting_refs,
                    provenance_ref=edge.provenance_ref,
                    history_cut=edge.history_cut,
                    is_contradicted=edge.is_contradicted,
                    contradiction_reason=edge.contradiction_reason,
                    is_invalidated=True,
                    invalidation_reason="Supporting evidence or connected node was invalidated",
                    status="INVALIDATED",
                )
                affected += 1
            else:
                new_edges[eid] = edge
        self._edges = new_edges
        return affected

    def apply_contradiction(self, edge_id: str, contradiction_reason: str) -> None:
        """Mark an edge as contradicted."""
        if edge_id not in self._edges:
            raise ValidationError("UNKNOWN_EDGE", f"Edge {edge_id} not found")
        e = self._edges[edge_id]
        self._edges[edge_id] = InteractionEdge(
            edge_id=e.edge_id,
            source_nodes=e.source_nodes,
            target_node=e.target_node,
            relation=e.relation,
            supporting_refs=e.supporting_refs,
            provenance_ref=e.provenance_ref,
            history_cut=e.history_cut,
            is_contradicted=True,
            contradiction_reason=contradiction_reason,
            is_invalidated=e.is_invalidated,
            invalidation_reason=e.invalidation_reason,
            status="CONTRADICTED",
        )

    def check_stale(self, current_cut: dict[str, Any]) -> bool:
        """Check if graph is stale with respect to current accepted history cut."""
        curr_seq = current_cut.get("accepted_head_seq") or current_cut.get("commit_seq") or 0
        curr_hash = current_cut.get("accepted_head_hash") or current_cut.get("commit_hash") or ""
        graph_seq = self.history_cut.get("accepted_head_seq") or self.history_cut.get("commit_seq") or 0
        graph_hash = self.history_cut.get("accepted_head_hash") or self.history_cut.get("commit_hash") or ""

        if curr_hash != graph_hash or curr_seq != graph_seq:
            return True
        return False

    def query_interactions(
        self,
        order: int | None = None,
        only_valid: bool = True,
    ) -> list[InteractionEdge]:
        """Query interactions by order (1=single, 2=pairwise, 3=3-way, etc.)."""
        results = []
        for edge in sorted(self._edges.values(), key=lambda e: e.edge_id):
            if only_valid and edge.status != "VALID":
                continue
            if order is not None and edge.order != order:
                continue
            results.append(edge)
        return results

    def generate_candidate_combinations(
        self,
        target_order: int = 2,
        node_kind: str | None = None,
    ) -> list[tuple[str, ...]]:
        """Generate bounded candidate node combinations for testing/scheduling.
        
        Enforces combinatorics boundedness to prevent interaction explosion.
        """
        if target_order > self.max_interaction_order:
            raise ValidationError(
                "INTERACTION_EXPLOSION_EXCEEDED",
                f"Requested order {target_order} exceeds max {self.max_interaction_order}",
            )
        eligible_nodes = [
            nid
            for nid, node in sorted(self._nodes.items())
            if node.status == "VALID" and (node_kind is None or node.node_kind == node_kind)
        ]
        combos = []
        for c in itertools.combinations(eligible_nodes, target_order):
            combos.append(c)
            if len(combos) >= self.max_combinations_bound:
                break
        return combos

    def export_canonical(self) -> dict[str, Any]:
        """Deterministic export of the graph."""
        sorted_nodes = [
            self._nodes[k].body() for k in sorted(self._nodes.keys())
        ]
        sorted_edges = [
            self._edges[k].body() for k in sorted(self._edges.keys())
        ]
        return {
            "history_cut": dict(self.history_cut),
            "max_interaction_order": self.max_interaction_order,
            "max_combinations_bound": self.max_combinations_bound,
            "nodes": sorted_nodes,
            "edges": sorted_edges,
        }

    def digest(self) -> str:
        b = canonical_bytes(self.export_canonical())
        return hashlib.sha256(b).hexdigest()

    @classmethod
    def rebuild(cls, canonical_data: dict[str, Any]) -> FailureInteractionGraph:
        """Deterministic rebuild from canonical export."""
        graph = cls(
            history_cut=canonical_data["history_cut"],
            max_interaction_order=canonical_data.get("max_interaction_order", 4),
            max_combinations_bound=canonical_data.get("max_combinations_bound", 1000),
        )
        for nb in canonical_data.get("nodes", []):
            node = InteractionNode(
                node_id=nb["node_id"],
                node_kind=nb["node_kind"],
                provenance_ref=nb["provenance_ref"],
                accepted_history_binding=nb["accepted_history_binding"],
                supporting_refs=tuple(nb.get("supporting_refs", ())),
                history_cut=nb["history_cut"],
                materiality=nb.get("materiality", "MEDIUM"),
                applicability=nb.get("applicability", True),
                status=nb.get("status", "VALID"),
            )
            graph.add_node(node)

        for eb in canonical_data.get("edges", []):
            edge = InteractionEdge(
                edge_id=eb["edge_id"],
                source_nodes=tuple(eb["source_nodes"]),
                target_node=eb["target_node"],
                relation=eb["relation"],
                supporting_refs=tuple(eb.get("supporting_refs", ())),
                provenance_ref=eb["provenance_ref"],
                history_cut=eb["history_cut"],
                is_contradicted=eb.get("is_contradicted", False),
                contradiction_reason=eb.get("contradiction_reason", ""),
                is_invalidated=eb.get("is_invalidated", False),
                invalidation_reason=eb.get("invalidation_reason", ""),
                status=eb.get("status", "VALID"),
            )
            graph.add_edge(edge)
        return graph

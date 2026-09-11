"""Risk-Ranked Interaction Scheduler (WP-E5-02 / M37 / §95 / Data Contracts §70).

Implements bounded, risk-ranked scheduling for:
- Pairwise (2-way)
- Selected 3-way
- Selected 4-way

Constraints:
- Scheduler is a derived test-generation aid, NOT an authority.
- Strictly avoids unconstrained combinatorial explosion.
- Deterministic ranking based on materiality, risk, obligations, failure families, and coverage gaps.
- Deterministic tie-handling.
- Rejection of stale projection inputs and unsupported candidate interactions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import itertools
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from .interaction_graph import FailureInteractionGraph, InteractionNode


MATERIALITY_WEIGHTS = {
    "CRITICAL": 10.0,
    "HIGH": 5.0,
    "MEDIUM": 2.0,
    "LOW": 1.0,
    "INFORMATIONAL": 0.5,
}


@dataclass(frozen=True)
class InteractionCandidate:
    candidate_id: str
    node_ids: tuple[str, ...]
    order: int
    materiality_score: float
    risk_score: float
    coverage_gap_weight: float
    rank_score: float
    obligation_refs: tuple[dict[str, Any], ...] = ()
    evidence_refs: tuple[dict[str, Any], ...] = ()
    tie_breaker_key: str = ""

    def __post_init__(self):
        if self.order not in (2, 3, 4):
            raise ValidationError(
                "UNSUPPORTED_INTERACTION_ORDER",
                f"Scheduler strictly bounds orders to 2, 3, or 4; got {self.order}",
            )
        if len(self.node_ids) != self.order:
            raise ValidationError(
                "NODE_COUNT_MISMATCH",
                f"Candidate order {self.order} requires {self.order} nodes, got {len(self.node_ids)}",
            )
        expected_tie = "_".join(sorted(self.node_ids))
        if not self.tie_breaker_key:
            object.__setattr__(self, "tie_breaker_key", expected_tie)

    def body(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "node_ids": list(self.node_ids),
            "order": self.order,
            "materiality_score": self.materiality_score,
            "risk_score": self.risk_score,
            "coverage_gap_weight": self.coverage_gap_weight,
            "rank_score": self.rank_score,
            "obligation_refs": [dict(r) for r in self.obligation_refs],
            "evidence_refs": [dict(r) for r in self.evidence_refs],
            "tie_breaker_key": self.tie_breaker_key,
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()


class InteractionScheduler:
    """Risk-ranked, bounded scheduler for pairwise, selected 3-way, and selected 4-way interactions."""

    def __init__(
        self,
        graph: FailureInteractionGraph,
        history_cut: dict[str, Any],
        max_pairwise_budget: int = 50,
        max_3way_budget: int = 20,
        max_4way_budget: int = 10,
    ):
        if not history_cut:
            raise ValidationError("MISSING_HISTORY_CUT", "Scheduler requires valid history_cut")
        # Check stale projection input
        if graph.check_stale(history_cut):
            raise ValidationError(
                "STALE_PROJECTION_INPUT",
                "Graph history_cut does not match scheduler history_cut",
            )
        self.graph = graph
        self.history_cut = dict(history_cut)
        self.max_pairwise_budget = max_pairwise_budget
        self.max_3way_budget = max_3way_budget
        self.max_4way_budget = max_4way_budget

    def _score_candidate(
        self,
        node_ids: tuple[str, ...],
        covered_node_pairs: Set[tuple[str, str]],
        uncovered_obligations: Mapping[str, Sequence[dict[str, Any]]],
    ) -> InteractionCandidate:
        nodes = [self.graph.nodes[nid] for nid in node_ids]

        # Materiality score: sum of weights
        mat_score = sum(MATERIALITY_WEIGHTS.get(n.materiality, 1.0) for n in nodes)

        # Risk score: boosted if ROOT_CAUSE_FAMILY or critical FAILURE_MODE is present
        risk_score = 1.0
        for n in nodes:
            if n.node_kind == "ROOT_CAUSE_FAMILY":
                risk_score += 1.5
            if n.materiality == "CRITICAL":
                risk_score += 2.0

        # Coverage gap weight
        # If any pair in candidate is uncovered, weight is high (2.0), otherwise lower (0.5)
        pairs = list(itertools.combinations(sorted(node_ids), 2))
        is_uncovered = any(p not in covered_node_pairs for p in pairs)
        gap_weight = 2.0 if is_uncovered else 0.5

        # Gather relevant obligations
        candidate_obligations = []
        for nid in node_ids:
            if nid in uncovered_obligations:
                candidate_obligations.extend(uncovered_obligations[nid])

        rank_score = round(mat_score * risk_score * gap_weight, 4)
        order = len(node_ids)
        sorted_ids = tuple(sorted(node_ids))
        cand_id = f"cand_{order}w_{'_'.join(sorted_ids)}"

        return InteractionCandidate(
            candidate_id=cand_id,
            node_ids=sorted_ids,
            order=order,
            materiality_score=mat_score,
            risk_score=risk_score,
            coverage_gap_weight=gap_weight,
            rank_score=rank_score,
            obligation_refs=tuple(candidate_obligations),
            tie_breaker_key="_".join(sorted_ids),
        )

    def schedule_pairwise(
        self,
        covered_pairs: Set[tuple[str, str]] | None = None,
        uncovered_obligations: Mapping[str, Sequence[dict[str, Any]]] | None = None,
        budget: int | None = None,
    ) -> list[InteractionCandidate]:
        """Generate deterministically ranked pairwise interaction candidates."""
        covered = covered_pairs or set()
        uncovered_obs = uncovered_obligations or {}
        limit = budget if budget is not None else self.max_pairwise_budget

        valid_nodes = [
            nid for nid, node in sorted(self.graph.nodes.items())
            if node.status == "VALID"
        ]

        candidates: list[InteractionCandidate] = []
        for pair in itertools.combinations(valid_nodes, 2):
            candidates.append(self._score_candidate(pair, covered, uncovered_obs))

        # Sort: descending by rank_score, then ascending by tie_breaker_key (deterministic tie-break)
        candidates.sort(key=lambda c: (-c.rank_score, c.tie_breaker_key))
        return candidates[:limit]

    def schedule_selected_3way(
        self,
        covered_pairs: Set[tuple[str, str]] | None = None,
        uncovered_obligations: Mapping[str, Sequence[dict[str, Any]]] | None = None,
        budget: int | None = None,
    ) -> list[InteractionCandidate]:
        """Generate selected 3-way interactions based on high-risk pairs/families."""
        covered = covered_pairs or set()
        uncovered_obs = uncovered_obligations or {}
        limit = budget if budget is not None else self.max_3way_budget

        # Select top high-materiality nodes first to avoid cubic explosion
        valid_nodes = [
            nid for nid, node in sorted(self.graph.nodes.items())
            if node.status == "VALID"
        ]
        # Only consider nodes with materiality >= MEDIUM or ROOT_CAUSE_FAMILY
        focal_nodes = [
            nid for nid in valid_nodes
            if self.graph.nodes[nid].materiality in ("CRITICAL", "HIGH", "MEDIUM")
            or self.graph.nodes[nid].node_kind == "ROOT_CAUSE_FAMILY"
        ]

        candidates: list[InteractionCandidate] = []
        for triplet in itertools.combinations(focal_nodes, 3):
            candidates.append(self._score_candidate(triplet, covered, uncovered_obs))

        candidates.sort(key=lambda c: (-c.rank_score, c.tie_breaker_key))
        return candidates[:limit]

    def schedule_selected_4way(
        self,
        covered_pairs: Set[tuple[str, str]] | None = None,
        uncovered_obligations: Mapping[str, Sequence[dict[str, Any]]] | None = None,
        budget: int | None = None,
    ) -> list[InteractionCandidate]:
        """Generate selected 4-way interactions strictly bounded to top critical combinations."""
        covered = covered_pairs or set()
        uncovered_obs = uncovered_obligations or {}
        limit = budget if budget is not None else self.max_4way_budget

        # Strict selection: only CRITICAL and HIGH materiality nodes
        focal_nodes = [
            nid for nid, node in sorted(self.graph.nodes.items())
            if node.status == "VALID" and node.materiality in ("CRITICAL", "HIGH")
        ]

        candidates: list[InteractionCandidate] = []
        for quad in itertools.combinations(focal_nodes, 4):
            candidates.append(self._score_candidate(quad, covered, uncovered_obs))

        candidates.sort(key=lambda c: (-c.rank_score, c.tie_breaker_key))
        return candidates[:limit]

    def schedule_all(
        self,
        covered_pairs: Set[tuple[str, str]] | None = None,
        uncovered_obligations: Mapping[str, Sequence[dict[str, Any]]] | None = None,
    ) -> dict[str, list[InteractionCandidate]]:
        """Run complete bounded schedule."""
        return {
            "pairwise": self.schedule_pairwise(covered_pairs, uncovered_obligations),
            "selected_3way": self.schedule_selected_3way(covered_pairs, uncovered_obligations),
            "selected_4way": self.schedule_selected_4way(covered_pairs, uncovered_obligations),
        }

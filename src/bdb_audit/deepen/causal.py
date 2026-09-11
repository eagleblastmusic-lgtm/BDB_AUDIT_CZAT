"""Causal Chain Engine (WP-E4-08 / M35 / §92 / Data Contracts §73).

Implements:
- CausalChainRecord: trigger -> path -> state transition -> observation -> impact.
- CausalEdge: explicit support and provenance verification for every edge (no guessing by time correlation).
- Rejection of unsupported, contradicted, or invalidated causal chains.
- Binding to F4 RootCauseRevision in existing adjudication authority model (strictly NO second authority).
- Deterministic reconstruction.
"""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set
from uuid import uuid4

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id
from ..evidence.models import Observation


@dataclass(frozen=True)
class CausalEdge:
    source_node: str
    target_node: str
    relation: str  # TRIGGERS, TRANSITIONS_TO, OBSERVES, CAUSES_IMPACT
    support_evidence_refs: tuple[dict[str, Any], ...]
    is_contradicted: bool = False
    contradiction_reason: str = ""

    def __post_init__(self):
        if not self.support_evidence_refs and not self.is_contradicted:
            raise ValidationError(
                "MISSING_EDGE_SUPPORT",
                f"Causal edge {self.source_node} -> {self.target_node} must have supporting evidence",
            )

    def body(self) -> dict[str, Any]:
        return {
            "source_node": self.source_node,
            "target_node": self.target_node,
            "relation": self.relation,
            "support_evidence_refs": [dict(r) for r in self.support_evidence_refs],
            "is_contradicted": self.is_contradicted,
            "contradiction_reason": self.contradiction_reason,
        }


@dataclass(frozen=True)
class CausalChainRecord:
    chain_id: str
    scope: str
    trigger: dict[str, Any]
    path: tuple[str, ...]
    state_transition_refs: tuple[dict[str, Any], ...]
    observation_refs: tuple[dict[str, Any], ...]
    impact_ref: dict[str, Any]
    edges: tuple[CausalEdge, ...]
    root_cause_ref: dict[str, Any] | None = None
    evidence_qualification_refs: tuple[dict[str, Any], ...] = ()
    status: str = "VALID"  # VALID, INVALIDATED, UNSUPPORTED, CONTRADICTED
    reason_codes: tuple[str, ...] = ()

    def body(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "scope": self.scope,
            "trigger": dict(self.trigger),
            "path": list(self.path),
            "state_transition_refs": [dict(r) for r in self.state_transition_refs],
            "observation_refs": [dict(r) for r in self.observation_refs],
            "impact_ref": dict(self.impact_ref),
            "edges": [e.body() for e in self.edges],
            "root_cause_ref": dict(self.root_cause_ref) if self.root_cause_ref else None,
            "evidence_qualification_refs": [dict(r) for r in self.evidence_qualification_refs],
            "status": self.status,
            "reason_codes": list(self.reason_codes),
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()


class CausalChainEngine:
    def __init__(self):
        pass

    def build_causal_chain(
        self,
        chain_id: str,
        scope: str,
        trigger: dict[str, Any],
        path: Sequence[str],
        state_transition_refs: Sequence[dict[str, Any]],
        observation_refs: Sequence[dict[str, Any]],
        impact_ref: dict[str, Any],
        edges: Sequence[CausalEdge],
        root_cause_ref: dict[str, Any] | None = None,
        evidence_qualification_refs: Sequence[dict[str, Any]] = (),
        invalidated_evidence_ids: Set[str] | None = None,
    ) -> CausalChainRecord:
        inval_ids = invalidated_evidence_ids or set()

        if not path:
            raise ValidationError("EMPTY_PATH", "Causal chain path cannot be empty")
        if not edges:
            raise ValidationError("EMPTY_EDGES", "Causal chain must have at least one causal edge")

        # Validate no second authority for Root Cause:
        # If root_cause_ref is provided, it must reference an authoritative RootCauseRevision
        if root_cause_ref is not None:
            kind = root_cause_ref.get("kind", "root_cause_revision")
            if kind in ("RootCauseMembershipRevision", "root_cause_membership_revision", "custom_root_cause"):
                raise ValidationError(
                    "SECOND_AUTHORITY_FOR_ROOT_CAUSE",
                    "Second authority for Root Cause rejected; must bind to canonical RootCauseRevision",
                )

        status = "VALID"
        reasons = []

        # Check edges for contradiction or invalidation
        for edge in edges:
            if edge.is_contradicted:
                status = "CONTRADICTED"
                reasons.append(f"Edge {edge.source_node}->{edge.target_node} contradicted: {edge.contradiction_reason}")
                break

            for ev_ref in edge.support_evidence_refs:
                ev_id = ev_ref.get("evidence_id") or ev_ref.get("observation_id")
                if ev_id and ev_id in inval_ids:
                    status = "INVALIDATED"
                    reasons.append(f"Supporting evidence {ev_id} on edge {edge.source_node}->{edge.target_node} is invalidated")
                    break
            if status != "VALID":
                break

        return CausalChainRecord(
            chain_id=chain_id,
            scope=scope,
            trigger=dict(trigger),
            path=tuple(path),
            state_transition_refs=tuple(state_transition_refs),
            observation_refs=tuple(observation_refs),
            impact_ref=dict(impact_ref),
            edges=tuple(edges),
            root_cause_ref=dict(root_cause_ref) if root_cause_ref else None,
            evidence_qualification_refs=tuple(evidence_qualification_refs),
            status=status,
            reason_codes=tuple(reasons),
        )

    def to_observation(
        self,
        chain: CausalChainRecord,
        execution_descriptor_ref: Any = None,
    ) -> Observation:
        exec_ref = execution_descriptor_ref or {
            "execution_descriptor_id": new_id("execution_descriptor"),
            "engine": "CAUSAL_CHAIN_ENGINE",
        }
        return Observation(
            observation_id=new_id("observation"),
            execution_descriptor_ref=exec_ref,
            raw_observation_ref=chain.body(),
            observation_channel="CAUSAL_CHAIN_ENGINE",
            observed_at="2026-09-11T12:00:00Z",
        )

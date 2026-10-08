"""Derived Contribution Projection (M23).

Contribution is a derived view over accepted discovery, adjudication,
root-cause, and evidence qualification facts as-of an accepted history cut.
It is NEVER an independent canonical authority or mutable ledger.
Rebuilding or deleting the projection does not alter canonical facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError


@dataclass(frozen=True)
class ProducerContribution:
    """Derived contribution metrics for a single producer (auditor, lane, or attempt)."""
    producer_id: str
    producer_ref: Mapping[str, Any]
    producer_lane_ref: Mapping[str, Any] | None = None
    discovery_refs: tuple[Mapping[str, Any], ...] = ()
    unique_discoveries: tuple[Mapping[str, Any], ...] = ()
    unique_contribution_count: int = 0
    support_count: int = 0
    leave_one_out_loss: int = 0
    coverage_obligation_delta: int = 0
    root_cause_family_refs: tuple[Mapping[str, Any], ...] = ()
    sound_contribution_count: int = 0
    rejected_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "producer_id": self.producer_id,
            "producer_ref": dict(self.producer_ref),
            "producer_lane_ref": dict(self.producer_lane_ref) if self.producer_lane_ref else None,
            "discovery_refs": [dict(r) for r in self.discovery_refs],
            "unique_discoveries": [dict(r) for r in self.unique_discoveries],
            "unique_contribution_count": self.unique_contribution_count,
            "support_count": self.support_count,
            "leave_one_out_loss": self.leave_one_out_loss,
            "coverage_obligation_delta": self.coverage_obligation_delta,
            "root_cause_family_refs": [dict(r) for r in self.root_cause_family_refs],
            "sound_contribution_count": self.sound_contribution_count,
            "rejected_count": self.rejected_count,
        }


@dataclass(frozen=True)
class ContributionProjection:
    """Derived projection of contributions as of a specific history cut.
    
    Not a canonical authority. Pure derived view.
    """
    history_cut: Mapping[str, Any]
    producer_contributions: Mapping[str, ProducerContribution]
    total_findings: int
    total_unique_findings: int
    total_root_causes: int
    is_projection: bool = True
    reveal_order_marginal_contribution_is_not_objective_value: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_projection": True,
            "reveal_order_marginal_contribution_is_not_objective_value": True,
            "history_cut": dict(self.history_cut),
            "total_findings": self.total_findings,
            "total_unique_findings": self.total_unique_findings,
            "total_root_causes": self.total_root_causes,
            "producer_contributions": {
                k: v.to_dict() for k, v in sorted(self.producer_contributions.items())
            },
        }

    def to_json(self) -> str:
        return canonical_bytes(self.to_dict()).decode("utf-8")

    def to_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())


def validate_contribution_authority(candidate_kind: str) -> None:
    """Reject any attempt to treat contribution as a canonical ledger authority."""
    forbidden = {
        "contribution_ledger",
        "contribution_authority",
        "mutable_contribution_ledger",
        "contribution_record",
    }
    if candidate_kind.lower() in forbidden:
        raise ValidationError(
            f"SECOND_AUTHORITY_FOR_CONTRIBUTION: kind '{candidate_kind}' cannot be a canonical authority."
        )


def _ref_digest(ref: Any) -> str:
    if isinstance(ref, dict):
        return ref.get("revision_digest") or ref.get("digest") or str(sorted(ref.items()))
    if hasattr(ref, "revision_digest"):
        return str(ref.revision_digest)
    return str(ref)


def _to_dict(item: Any) -> dict:
    if isinstance(item, dict):
        return item
    if hasattr(item, "body"):
        b = item.body
        return b() if callable(b) else dict(b)
    if hasattr(item, "as_dict"):
        ad = item.as_dict
        return ad() if callable(ad) else dict(ad)
    if hasattr(item, "__dict__"):
        return item.__dict__
    return dict(item)


def build_contribution_projection(
    *,
    history_cut: Mapping[str, Any],
    discoveries: Sequence[Any] = (),
    finding_claims: Sequence[Any] = (),
    adjudications: Sequence[Any] = (),
    root_causes: Sequence[Any] = (),
    coverage_qualifications: Sequence[Any] = (),
    producer_attributions: Mapping[str, Mapping[str, Any]] | None = None,
) -> ContributionProjection:
    """Build a deterministic derived ContributionProjection from canonical facts.
    
    Computes UNIQUE_CONTRIBUTION, SUPPORT_COUNT, and LEAVE_ONE_OUT_CONTRIBUTION.
    """
    attributions = dict(producer_attributions or {})
    
    # Map finding claims to status (confirmed, rejected, etc.)
    finding_status: dict[str, str] = {}
    for adj in adjudications:
        adj_dict = _to_dict(adj)
        claim_ref = getattr(adj, "claim_revision_ref", None) or adj_dict.get("claim_revision_ref")
        status = getattr(adj, "lifecycle_status", None) or adj_dict.get("lifecycle_status")
        if claim_ref and status:
            finding_status[_ref_digest(claim_ref)] = status

    # Map finding to producers who contributed to it
    finding_producers: dict[str, set[str]] = {}
    finding_refs_map: dict[str, Any] = {}
    producer_refs_map: dict[str, dict[str, Any]] = {}
    producer_lanes_map: dict[str, dict[str, Any] | None] = {}

    # Gather producers from discoveries / findings
    for disc in discoveries:
        disc_dict = _to_dict(disc)
        disc_ref = disc.as_object().ref.as_dict() if hasattr(disc, "as_object") else (disc.ref.as_dict() if hasattr(disc, "ref") and hasattr(disc.ref, "as_dict") else (disc.ref if hasattr(disc, "ref") else disc_dict.get("ref", disc_dict)))
        disc_digest = disc.digest if hasattr(disc, "digest") else _ref_digest(disc_ref)
        finding_refs_map[disc_digest] = disc_ref
        
        prod = attributions.get(disc_digest) or disc_dict.get("producer_ref") or disc_dict.get("attempt_ref")
        if prod:
            prod_dict = _to_dict(prod)
            prod_id = prod_dict.get("producer_id") or prod_dict.get("attempt_id") or _ref_digest(prod)
            producer_refs_map[prod_id] = prod_dict
            producer_lanes_map[prod_id] = disc_dict.get("lane_ref")
            finding_producers.setdefault(disc_digest, set()).add(prod_id)

    for claim in finding_claims:
        claim_dict = _to_dict(claim)
        claim_ref = claim.as_object().ref.as_dict() if hasattr(claim, "as_object") else (claim.ref.as_dict() if hasattr(claim, "ref") and hasattr(claim.ref, "as_dict") else (claim.ref if hasattr(claim, "ref") else claim_dict.get("ref", claim_dict)))
        claim_digest = claim.digest if hasattr(claim, "digest") else _ref_digest(claim_ref)
        finding_refs_map[claim_digest] = claim_ref
        
        prod = attributions.get(claim_digest) or claim_dict.get("producer_ref")
        if prod:
            prod_dict = _to_dict(prod)
            prod_id = prod_dict.get("producer_id") or prod_dict.get("attempt_id") or _ref_digest(prod)
            producer_refs_map[prod_id] = prod_dict
            finding_producers.setdefault(claim_digest, set()).add(prod_id)

    # All producers seen
    all_producers = sorted(producer_refs_map.keys())

    # Map root causes to findings and producers
    root_cause_producers: dict[str, set[str]] = {}
    root_cause_refs_map: dict[str, Any] = {}
    for rc in root_causes:
        rc_dict = _to_dict(rc)
        rc_ref = rc.as_object().ref.as_dict() if hasattr(rc, "as_object") else rc_dict.get("ref", rc_dict)
        rc_digest = _ref_digest(rc_ref)
        root_cause_refs_map[rc_digest] = rc_ref
        edges = rc_dict.get("membership_edges", ())
        rc_prods = set()
        for edge in edges:
            edge_dict = _to_dict(edge)
            f_ref = edge_dict.get("finding_claim_revision_ref")
            f_digest = _ref_digest(f_ref)
            for p in finding_producers.get(f_digest, ()):
                rc_prods.add(p)
        root_cause_producers[rc_digest] = rc_prods

    # Coverage obligations mapped to producers
    coverage_producers: dict[str, set[str]] = {}
    for cov in coverage_qualifications:
        cov_dict = _to_dict(cov)
        cov_key = str(cov_dict.get("obligation_key", cov_dict.get("coverage_obligation_ref", "")))
        ev_refs = cov_dict.get("evidence_qualification_refs", ())
        # Attribute coverage to producers of those evidences if known
        for ev in ev_refs:
            ev_digest = _ref_digest(ev)
            for p in finding_producers.get(ev_digest, ()):
                coverage_producers.setdefault(cov_key, set()).add(p)

    # Compute metrics per producer
    producer_contributions: dict[str, ProducerContribution] = {}

    for prod_id in all_producers:
        p_ref = producer_refs_map[prod_id]
        p_lane = producer_lanes_map.get(prod_id)
        
        p_findings = [f for f, prods in finding_producers.items() if prod_id in prods]
        unique_findings = [f for f in p_findings if finding_producers[f] == {prod_id}]
        
        # Support count: findings where this producer collaborated with others
        # i.e. finding has >1 producer and prod_id is one of them
        support_findings = [f for f in p_findings if len(finding_producers[f]) > 1]
        
        # Leave-one-out: if prod_id is removed, how many findings are lost completely?
        # That is exactly unique_findings!
        # Plus any root causes that only prod_id contributed to
        lost_findings_count = len(unique_findings)
        lost_rc_count = sum(1 for rc, prods in root_cause_producers.items() if prods == {prod_id})
        leave_one_out_loss = lost_findings_count + lost_rc_count

        # Coverage delta: obligations that only prod_id qualified
        coverage_delta = sum(1 for cov_key, prods in coverage_producers.items() if prods == {prod_id})

        # Sound vs rejected
        sound_count = sum(
            1 for f in p_findings
            if finding_status.get(f) in ("CONFIRMED_CURRENT", "OPEN", None)
        )
        rejected_count = sum(
            1 for f in p_findings
            if finding_status.get(f) == "REJECTED"
        )

        # Root cause families touched
        p_rc_refs = [
            root_cause_refs_map[rc]
            for rc, prods in root_cause_producers.items()
            if prod_id in prods
        ]

        producer_contributions[prod_id] = ProducerContribution(
            producer_id=prod_id,
            producer_ref=p_ref,
            producer_lane_ref=p_lane,
            discovery_refs=tuple(finding_refs_map[f] for f in sorted(p_findings)),
            unique_discoveries=tuple(finding_refs_map[f] for f in sorted(unique_findings)),
            unique_contribution_count=len(unique_findings),
            support_count=len(support_findings),
            leave_one_out_loss=leave_one_out_loss,
            coverage_obligation_delta=coverage_delta,
            root_cause_family_refs=tuple(p_rc_refs),
            sound_contribution_count=sound_count,
            rejected_count=rejected_count,
        )

    # Global unique findings count
    global_unique = sum(1 for f, prods in finding_producers.items() if len(prods) == 1)

    return ContributionProjection(
        history_cut=history_cut,
        producer_contributions=producer_contributions,
        total_findings=len(finding_producers),
        total_unique_findings=global_unique,
        total_root_causes=len(root_cause_producers),
        is_projection=True,
        reveal_order_marginal_contribution_is_not_objective_value=True,
    )

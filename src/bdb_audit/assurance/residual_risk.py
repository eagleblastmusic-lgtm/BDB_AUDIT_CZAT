"""Residual Risk Register and Projection (WP-E5-07 / M42 / §101 / Data Contracts §79).

Canonical versioned assessment for residual risk:
- Binds exact obligations, blockers, waivers, unknown scope, evidence applicability,
  and accepted residual-risk decisions.
- Material acceptance/waiver decisions belong to canonical history.
- Fail-closed rules:
  - UNKNOWN cannot become ACCEPTED_RESIDUAL_RISK without explicit owner approval.
  - BLOCKED cannot become ACCEPTED_RESIDUAL_RISK without authority.
  - Invalidated supporting evidence or open contradictions invalidate/block the risk.
  - Stale evidence is detected and rejected.
  - Deterministic rebuild.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError


RISK_DISPOSITIONS = {
    "OPEN",
    "BOUNDED",
    "ACCEPTED_RESIDUAL_RISK",
    "BLOCKED",
    "UNKNOWN",
    "SUPERSEDED",
}

RISK_MATERIALITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
RECORD_STATUSES = {"VALID", "INVALIDATED", "CONTRADICTED", "STALE"}


@dataclass(frozen=True)
class ResidualRiskRecord:
    risk_id: str
    risk_revision: str
    scope: str
    description: str
    materiality: str
    uncertainty_class: str
    reason_unresolved: str
    disposition: str
    blocking_effect: bool
    history_cut: dict[str, Any]
    related_obligation_refs: tuple[dict[str, Any], ...] = ()
    related_hypothesis_refs: tuple[dict[str, Any], ...] = ()
    evidence_refs: tuple[dict[str, Any], ...] = ()
    owner_approval_ref: dict[str, Any] | None = None
    waiver_ref: dict[str, Any] | None = None
    status: str = "VALID"

    def __post_init__(self):
        if self.disposition not in RISK_DISPOSITIONS:
            raise ValidationError(
                "INVALID_RISK_DISPOSITION",
                f"disposition {self.disposition} must be one of {sorted(RISK_DISPOSITIONS)}",
            )
        if self.materiality not in RISK_MATERIALITIES:
            raise ValidationError(
                "INVALID_RISK_MATERIALITY",
                f"materiality {self.materiality} must be one of {sorted(RISK_MATERIALITIES)}",
            )
        if self.status not in RECORD_STATUSES:
            raise ValidationError("INVALID_RECORD_STATUS", f"status {self.status} invalid")
        if not self.history_cut:
            raise ValidationError("MISSING_HISTORY_CUT", "Residual risk requires history_cut")

        # Invariant 1: ACCEPTED_RESIDUAL_RISK requires explicit owner_approval_ref
        if self.disposition == "ACCEPTED_RESIDUAL_RISK" and not self.owner_approval_ref:
            raise ValidationError(
                "RESIDUAL_RISK_REQUIRES_APPROVAL",
                f"Risk {self.risk_id} cannot have disposition ACCEPTED_RESIDUAL_RISK without explicit owner_approval_ref",
            )

        # Invariant 2: UNKNOWN cannot silently become ACCEPTED_RESIDUAL_RISK without explicit approval and resolved scope
        if self.uncertainty_class == "UNKNOWN_SCOPE" and self.disposition == "ACCEPTED_RESIDUAL_RISK":
            if not self.waiver_ref and not self.owner_approval_ref:
                raise ValidationError(
                    "UNKNOWN_CANNOT_BE_IMPLICIT_RESIDUAL_RISK",
                    "UNKNOWN_SCOPE requires explicit waiver or approval authority to be accepted",
                )

    def body(self) -> dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "risk_revision": self.risk_revision,
            "scope": self.scope,
            "description": self.description,
            "materiality": self.materiality,
            "uncertainty_class": self.uncertainty_class,
            "reason_unresolved": self.reason_unresolved,
            "disposition": self.disposition,
            "blocking_effect": self.blocking_effect,
            "history_cut": dict(self.history_cut),
            "related_obligation_refs": [dict(r) for r in self.related_obligation_refs],
            "related_hypothesis_refs": [dict(r) for r in self.related_hypothesis_refs],
            "evidence_refs": [dict(r) for r in self.evidence_refs],
            "owner_approval_ref": dict(self.owner_approval_ref) if self.owner_approval_ref else None,
            "waiver_ref": dict(self.waiver_ref) if self.waiver_ref else None,
            "status": self.status,
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()


class ResidualRiskRegister:
    """Canonical registry and projector for residual risk assessments."""

    def __init__(self, history_cut: dict[str, Any]):
        if not history_cut:
            raise ValidationError("MISSING_HISTORY_CUT", "Register requires history_cut")
        self.history_cut = dict(history_cut)
        self._records: dict[str, ResidualRiskRecord] = {}

    @property
    def records(self) -> Mapping[str, ResidualRiskRecord]:
        return self._records

    def add_record(self, record: ResidualRiskRecord) -> None:
        if record.history_cut != self.history_cut:
            raise ValidationError(
                "STALE_RESIDUAL_RISK_INPUT",
                f"Record {record.risk_id} history cut does not match register history cut",
            )
        self._records[record.risk_id] = record

    def check_stale(self, current_cut: dict[str, Any]) -> bool:
        curr_seq = current_cut.get("accepted_head_seq") or current_cut.get("commit_seq") or 0
        curr_hash = current_cut.get("accepted_head_hash") or current_cut.get("commit_hash") or ""
        reg_seq = self.history_cut.get("accepted_head_seq") or self.history_cut.get("commit_seq") or 0
        reg_hash = self.history_cut.get("accepted_head_hash") or self.history_cut.get("commit_hash") or ""
        return curr_hash != reg_hash or curr_seq != reg_seq

    def apply_invalidations(self, invalidated_ref_ids: Set[str]) -> int:
        """Invalidate risks whose supporting evidence or waivers are invalidated."""
        affected = 0
        new_records = {}
        for rid, rec in self._records.items():
            evidence_invalid = any(
                r.get("revision_digest") in invalidated_ref_ids
                or r.get("id") in invalidated_ref_ids
                for r in rec.evidence_refs
            )
            waiver_invalid = (
                rec.waiver_ref is not None
                and (
                    rec.waiver_ref.get("revision_digest") in invalidated_ref_ids
                    or rec.waiver_ref.get("id") in invalidated_ref_ids
                )
            )
            if (evidence_invalid or waiver_invalid) and rec.status != "INVALIDATED":
                # Demote disposition and mark status INVALIDATED
                new_records[rid] = ResidualRiskRecord(
                    risk_id=rec.risk_id,
                    risk_revision=rec.risk_revision,
                    scope=rec.scope,
                    description=rec.description,
                    materiality=rec.materiality,
                    uncertainty_class=rec.uncertainty_class,
                    reason_unresolved=f"{rec.reason_unresolved}; Evidence or waiver was invalidated",
                    disposition="BLOCKED",
                    blocking_effect=True,
                    history_cut=rec.history_cut,
                    related_obligation_refs=rec.related_obligation_refs,
                    related_hypothesis_refs=rec.related_hypothesis_refs,
                    evidence_refs=rec.evidence_refs,
                    owner_approval_ref=None,
                    waiver_ref=None,
                    status="INVALIDATED",
                )
                affected += 1
            else:
                new_records[rid] = rec
        self._records = new_records
        return affected

    def apply_contradiction(self, risk_id: str, contradiction_ref: dict[str, Any]) -> None:
        """Mark risk as CONTRADICTED and block disposition upon open contradiction."""
        if risk_id not in self._records:
            raise ValidationError("UNKNOWN_RISK", f"Risk {risk_id} not found in register")
        rec = self._records[risk_id]
        self._records[risk_id] = ResidualRiskRecord(
            risk_id=rec.risk_id,
            risk_revision=rec.risk_revision,
            scope=rec.scope,
            description=rec.description,
            materiality=rec.materiality,
            uncertainty_class=rec.uncertainty_class,
            reason_unresolved=f"{rec.reason_unresolved}; Open contradiction encountered: {contradiction_ref.get('reason', '')}",
            disposition="BLOCKED",
            blocking_effect=True,
            history_cut=rec.history_cut,
            related_obligation_refs=rec.related_obligation_refs,
            related_hypothesis_refs=rec.related_hypothesis_refs,
            evidence_refs=rec.evidence_refs,
            owner_approval_ref=None,
            waiver_ref=rec.waiver_ref,
            status="CONTRADICTED",
        )

    def export_canonical(self) -> dict[str, Any]:
        return {
            "history_cut": dict(self.history_cut),
            "records": [self._records[k].body() for k in sorted(self._records.keys())],
        }

    def digest(self) -> str:
        b = canonical_bytes(self.export_canonical())
        return hashlib.sha256(b).hexdigest()

    @classmethod
    def rebuild(cls, canonical_data: dict[str, Any]) -> ResidualRiskRegister:
        reg = cls(history_cut=canonical_data["history_cut"])
        for rb in canonical_data.get("records", []):
            rec = ResidualRiskRecord(
                risk_id=rb["risk_id"],
                risk_revision=rb["risk_revision"],
                scope=rb["scope"],
                description=rb["description"],
                materiality=rb["materiality"],
                uncertainty_class=rb["uncertainty_class"],
                reason_unresolved=rb["reason_unresolved"],
                disposition=rb["disposition"],
                blocking_effect=rb["blocking_effect"],
                history_cut=rb["history_cut"],
                related_obligation_refs=tuple(rb.get("related_obligation_refs", ())),
                related_hypothesis_refs=tuple(rb.get("related_hypothesis_refs", ())),
                evidence_refs=tuple(rb.get("evidence_refs", ())),
                owner_approval_ref=rb.get("owner_approval_ref"),
                waiver_ref=rb.get("waiver_ref"),
                status=rb.get("status", "VALID"),
            )
            reg.add_record(rec)
        return reg

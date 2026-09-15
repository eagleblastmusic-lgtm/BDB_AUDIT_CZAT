"""Residual Risk Register and canonical accepted-history producer (M42 / §101).

Residual risk is a versioned canonical assessment, not a narrative ledger.
Material owner acceptance/waiver authority must pre-exist the risk revision;
release readiness is derived later by STOP/release policy and is never granted by
constructing this model alone.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Set

from ..core.errors import ValidationError
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject


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
_REQUIRED_REF_FIELDS = {
    "kind", "revision_digest", "digest_profile", "schema_revision_ref", "ref_class"
}


def _accepted_cut(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("variant") != "ACCEPTED_HISTORY_CUT":
        raise ValidationError("ACCEPTED_HISTORY_CUT_REQUIRED")
    if not isinstance(value.get("campaign_id"), str) or not value["campaign_id"]:
        raise ValidationError("ACCEPTED_HISTORY_CUT_REQUIRED")
    seq = value.get("accepted_head_seq")
    digest = value.get("accepted_head_hash")
    if type(seq) is not int or seq < 1:
        raise ValidationError("ACCEPTED_HISTORY_CUT_REQUIRED")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(ch not in "0123456789abcdef" for ch in digest)
    ):
        raise ValidationError("ACCEPTED_HISTORY_CUT_REQUIRED")
    if not isinstance(value.get("governing_policy_ref"), str) or not value["governing_policy_ref"]:
        raise ValidationError("ACCEPTED_HISTORY_CUT_REQUIRED")
    specs = value.get("governing_spec_refs")
    if not isinstance(specs, list) or not specs or not all(isinstance(item, str) and item for item in specs):
        raise ValidationError("ACCEPTED_HISTORY_CUT_REQUIRED")
    return dict(value)


def _typed_ref(
    value: dict[str, Any],
    field: str,
    *,
    kind: str | None = None,
    ref_class: str | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict) or not _REQUIRED_REF_FIELDS.issubset(value):
        raise ValidationError("TYPED_REF_INCOMPLETE", field)
    if kind is not None and value.get("kind") != kind:
        raise ValidationError("TYPED_REF_TARGET_MISMATCH", field)
    if ref_class is not None and value.get("ref_class") != ref_class:
        raise ValidationError("REFERENCE_CLASS_MISMATCH", field)
    return dict(value)


def _typed_refs(values, field: str) -> tuple[dict[str, Any], ...]:
    refs = [_typed_ref(value, field) for value in values]
    return tuple(canonical_reference_set(refs))


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
        for field_name in (
            "risk_id", "risk_revision", "scope", "description",
            "uncertainty_class", "reason_unresolved",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValidationError("RESIDUAL_RISK_FIELD_REQUIRED", field_name)
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
        if type(self.blocking_effect) is not bool:
            raise ValidationError("INVALID_BLOCKING_EFFECT")

        object.__setattr__(self, "history_cut", _accepted_cut(self.history_cut))
        object.__setattr__(
            self,
            "related_obligation_refs",
            _typed_refs(self.related_obligation_refs, "related_obligation_refs"),
        )
        object.__setattr__(
            self,
            "related_hypothesis_refs",
            _typed_refs(self.related_hypothesis_refs, "related_hypothesis_refs"),
        )
        object.__setattr__(self, "evidence_refs", _typed_refs(self.evidence_refs, "evidence_refs"))

        if self.owner_approval_ref is not None:
            object.__setattr__(
                self,
                "owner_approval_ref",
                _typed_ref(
                    self.owner_approval_ref,
                    "owner_approval_ref",
                    kind="approval_decision",
                    ref_class="PRIOR_ACCEPTED_ONLY",
                ),
            )
        if self.waiver_ref is not None:
            object.__setattr__(
                self,
                "waiver_ref",
                _typed_ref(
                    self.waiver_ref,
                    "waiver_ref",
                    kind="approval_decision",
                    ref_class="PRIOR_ACCEPTED_ONLY",
                ),
            )

        if self.disposition == "ACCEPTED_RESIDUAL_RISK" and not self.owner_approval_ref:
            raise ValidationError(
                "RESIDUAL_RISK_REQUIRES_APPROVAL",
                f"Risk {self.risk_id} cannot have disposition ACCEPTED_RESIDUAL_RISK without explicit owner_approval_ref",
            )

    def body(self) -> dict[str, Any]:
        data: dict[str, Any] = {
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
            "status": self.status,
        }
        if self.owner_approval_ref is not None:
            data["owner_approval_ref"] = dict(self.owner_approval_ref)
        if self.waiver_ref is not None:
            data["waiver_ref"] = dict(self.waiver_ref)
        return data

    def as_object(self) -> CanonicalObject:
        return CanonicalObject("residual_risk", self.body())

    def digest(self) -> str:
        return self.as_object().digest

    @property
    def ref(self) -> dict[str, Any]:
        return self.as_object().as_ref(ref_class="CONTENT_OR_PRIOR").as_dict()


class ResidualRiskRegister:
    """Deterministic current-revision projector for residual-risk assessments."""

    def __init__(self, history_cut: dict[str, Any]):
        self.history_cut = _accepted_cut(history_cut)
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
        current = _accepted_cut(current_cut)
        return (
            current["campaign_id"] != self.history_cut["campaign_id"]
            or current["accepted_head_seq"] != self.history_cut["accepted_head_seq"]
            or current["accepted_head_hash"] != self.history_cut["accepted_head_hash"]
        )

    def apply_invalidations(self, invalidated_ref_ids: Set[str]) -> int:
        """Invalidate risks whose supporting evidence or waiver authority was invalidated."""
        affected = 0
        new_records: dict[str, ResidualRiskRecord] = {}
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
        """Mark a projected risk as contradicted and blocking."""
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
        from ..core.canonical_json import canonical_bytes

        return hashlib.sha256(canonical_bytes(self.export_canonical())).hexdigest()

    @classmethod
    def rebuild(cls, canonical_data: dict[str, Any]) -> "ResidualRiskRegister":
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


class ResidualRiskService:
    """Accept residual-risk revisions through the Coordinator authority boundary."""

    @staticmethod
    def accept_record(store, record: ResidualRiskRecord) -> dict[str, Any]:
        from ..coordinator import Coordinator
        from ..history.objects import ACCEPTED_HEAD_REF, CommandEnvelope
        from ..workflow.read_models import current_accepted_cut

        head = store.head()
        if head is None:
            raise ValidationError("EMPTY_STORE", "Residual risk requires an accepted campaign")
        cut = current_accepted_cut(store)
        obj = record.as_object()

        for row in store.accepted_records("residual_risk", cut):
            if row["ref"]["revision_digest"] == obj.digest:
                return {
                    "status": "ALREADY_ACCEPTED",
                    "residual_risk_digest": obj.digest,
                    "commit_seq": row["accepted_seq"],
                }

        if record.history_cut != cut:
            raise ValidationError("STALE_RESIDUAL_RISK_INPUT")

        prior = store.commits()[-1]
        seed = hashlib.sha256(
            f"{head.campaign_id}_residual_risk_{head.commit_seq}_{obj.digest}".encode("utf-8")
        ).hexdigest()
        command_id = f"command_{seed[:8]}-{seed[8:12]}-4{seed[13:16]}-8{seed[17:20]}-{seed[20:32]}"
        command = CommandEnvelope(
            command_id=command_id,
            command_kind="RECORD_ASSURANCE_DECISION",
            actor_ref=prior.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": ACCEPTED_HEAD_REF, **head.as_dict()},
            governing_policy_ref=prior.get(
                "governing_policy_ref", "pin:initial_governing_policy_ref"
            ),
            governing_spec_refs=tuple(
                prior.get("governing_spec_refs", ("pin:initial_transition_profile_ref",))
            ),
            idempotency_scope=f"residual_risk_{obj.digest[:16]}",
            campaign_ref=head.campaign_id,
        )
        result = Coordinator(store).accept(command, immutable_objects=[obj])
        return {
            "status": "SUCCESS",
            "residual_risk_digest": obj.digest,
            "commit_seq": result.head.commit_seq,
            "commit_hash": result.head.commit_hash,
        }


__all__ = [
    "ResidualRiskRecord",
    "ResidualRiskRegister",
    "ResidualRiskService",
    "RISK_DISPOSITIONS",
    "RISK_MATERIALITIES",
    "RECORD_STATUSES",
]

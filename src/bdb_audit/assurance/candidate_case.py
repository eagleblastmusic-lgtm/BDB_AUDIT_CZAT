"""Candidate Assurance Case at End of E5A (WP-E5-08 / M43 / §102 / Data Contracts §80).

Formed after E1-E4 and required E5A attack/synthesis outputs on an exact accepted HistoryCut.
Normative invariants:
- Strictly does NOT contain challenger results or future STOP/conclusion refs.
- Gathers exact sorted typed sets of findings, adjudications, evidence qualifications,
  obligations, contradictions, and residual risks.
- Direct obligation and qualification refs are authoritative; optional summary is
  strictly derived.
- Candidate revision identity is frozen for baseline challenger execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError


def sort_refs_by_digest(refs: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    return tuple(
        sorted(
            refs,
            key=lambda r: (r.get("kind", ""), r.get("revision_digest") or r.get("id") or ""),
        )
    )


@dataclass(frozen=True)
class CandidateAssuranceCase:
    candidate_assurance_case_id: str
    campaign_ref: dict[str, Any]
    source_generation_ref: dict[str, Any]
    candidate_input_history_cut: dict[str, Any]
    scope_inventory_ref: dict[str, Any]
    coverage_obligation_refs: tuple[dict[str, Any], ...]
    coverage_obligation_qualification_refs: tuple[dict[str, Any], ...]
    finding_claim_revision_refs: tuple[dict[str, Any], ...]
    finding_adjudication_refs: tuple[dict[str, Any], ...]
    contradiction_refs: tuple[dict[str, Any], ...]
    evidence_qualification_refs: tuple[dict[str, Any], ...]
    residual_risk_refs: tuple[dict[str, Any], ...]
    assurance_claim_set_ref: dict[str, Any]
    coverage_obligation_summary_ref: dict[str, Any] | None = None

    def __post_init__(self):
        if not self.candidate_assurance_case_id:
            raise ValidationError("MISSING_CASE_ID", "CandidateAssuranceCase requires candidate_assurance_case_id")
        if not self.candidate_input_history_cut:
            raise ValidationError("MISSING_HISTORY_CUT", "CandidateAssuranceCase requires candidate_input_history_cut")
        if not self.campaign_ref or not self.source_generation_ref or not self.scope_inventory_ref:
            raise ValidationError("MISSING_FOUNDATION_REF", "Missing required campaign, source, or scope ref")

        # Invariant: Strictly NO challenger results or future STOP refs inside CandidateAssuranceCase
        for field_name, refs in (
            ("finding_claim_revision_refs", self.finding_claim_revision_refs),
            ("contradiction_refs", self.contradiction_refs),
            ("evidence_qualification_refs", self.evidence_qualification_refs),
            ("residual_risk_refs", self.residual_risk_refs),
        ):
            for r in refs:
                kind = r.get("kind", "")
                if kind in ("challenger_result", "challenger_assignment", "stop_evaluation", "campaign_conclusion"):
                    raise ValidationError(
                        "PREMATURE_FUTURE_REF",
                        f"CandidateAssuranceCase cannot reference future artifact kind '{kind}' in {field_name}",
                    )

    def body(self) -> dict[str, Any]:
        data = {
            "candidate_assurance_case_id": self.candidate_assurance_case_id,
            "campaign_ref": dict(self.campaign_ref),
            "source_generation_ref": dict(self.source_generation_ref),
            "candidate_input_history_cut": dict(self.candidate_input_history_cut),
            "scope_inventory_ref": dict(self.scope_inventory_ref),
            "coverage_obligation_refs": [dict(r) for r in self.coverage_obligation_refs],
            "coverage_obligation_qualification_refs": [dict(r) for r in self.coverage_obligation_qualification_refs],
            "finding_claim_revision_refs": [dict(r) for r in self.finding_claim_revision_refs],
            "finding_adjudication_refs": [dict(r) for r in self.finding_adjudication_refs],
            "contradiction_refs": [dict(r) for r in self.contradiction_refs],
            "evidence_qualification_refs": [dict(r) for r in self.evidence_qualification_refs],
            "residual_risk_refs": [dict(r) for r in self.residual_risk_refs],
            "assurance_claim_set_ref": dict(self.assurance_claim_set_ref),
        }
        if self.coverage_obligation_summary_ref is not None:
            data["coverage_obligation_summary_ref"] = dict(self.coverage_obligation_summary_ref)
        return data

    def digest(self) -> str:
        from ..history.objects import CanonicalObject
        return CanonicalObject("candidate_assurance_case", self.body()).digest

    @property
    def ref(self) -> dict[str, Any]:
        return {
            "kind": "candidate_assurance_case",
            "revision_digest": self.digest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::candidate_assurance_case/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


class CandidateAssuranceCaseBuilder:
    """Deterministic builder for immutable CandidateAssuranceCase at end of E5A."""

    def __init__(
        self,
        case_id: str,
        campaign_ref: dict[str, Any],
        source_generation_ref: dict[str, Any],
        candidate_input_history_cut: dict[str, Any],
        scope_inventory_ref: dict[str, Any],
        assurance_claim_set_ref: dict[str, Any],
    ):
        self.case_id = case_id
        self.campaign_ref = campaign_ref
        self.source_generation_ref = source_generation_ref
        self.candidate_input_history_cut = candidate_input_history_cut
        self.scope_inventory_ref = scope_inventory_ref
        self.assurance_claim_set_ref = assurance_claim_set_ref

        self.coverage_obligations: list[dict[str, Any]] = []
        self.coverage_qualifications: list[dict[str, Any]] = []
        self.finding_claims: list[dict[str, Any]] = []
        self.finding_adjudications: list[dict[str, Any]] = []
        self.contradictions: list[dict[str, Any]] = []
        self.evidence_qualifications: list[dict[str, Any]] = []
        self.residual_risks: list[dict[str, Any]] = []
        self.coverage_summary_ref: dict[str, Any] | None = None

    def add_coverage_obligation(self, obligation_ref: dict[str, Any], qualification_ref: dict[str, Any] | None = None) -> None:
        self.coverage_obligations.append(obligation_ref)
        if qualification_ref:
            self.coverage_qualifications.append(qualification_ref)

    def add_finding(self, claim_ref: dict[str, Any], adjudication_ref: dict[str, Any]) -> None:
        self.finding_claims.append(claim_ref)
        self.finding_adjudications.append(adjudication_ref)

    def add_contradiction(self, contradiction_ref: dict[str, Any]) -> None:
        self.contradictions.append(contradiction_ref)

    def add_evidence_qualification(self, qual_ref: dict[str, Any]) -> None:
        self.evidence_qualifications.append(qual_ref)

    def add_residual_risk(self, risk_ref: dict[str, Any]) -> None:
        self.residual_risks.append(risk_ref)

    def set_coverage_summary(self, summary_ref: dict[str, Any]) -> None:
        self.coverage_summary_ref = summary_ref

    def build(self) -> CandidateAssuranceCase:
        return CandidateAssuranceCase(
            candidate_assurance_case_id=self.case_id,
            campaign_ref=self.campaign_ref,
            source_generation_ref=self.source_generation_ref,
            candidate_input_history_cut=self.candidate_input_history_cut,
            scope_inventory_ref=self.scope_inventory_ref,
            coverage_obligation_refs=sort_refs_by_digest(self.coverage_obligations),
            coverage_obligation_qualification_refs=sort_refs_by_digest(self.coverage_qualifications),
            finding_claim_revision_refs=sort_refs_by_digest(self.finding_claims),
            finding_adjudication_refs=sort_refs_by_digest(self.finding_adjudications),
            contradiction_refs=sort_refs_by_digest(self.contradictions),
            evidence_qualification_refs=sort_refs_by_digest(self.evidence_qualifications),
            residual_risk_refs=sort_refs_by_digest(self.residual_risks),
            assurance_claim_set_ref=self.assurance_claim_set_ref,
            coverage_obligation_summary_ref=self.coverage_summary_ref,
        )

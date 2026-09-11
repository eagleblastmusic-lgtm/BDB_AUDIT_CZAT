"""Campaign Conclusion and Final Assurance Case (WP-E5-12 / M45A / §105.1 / Data Contracts §80).

Normative sequence:
CandidateAssuranceCase -> ChallengerResults -> StopEvaluation -> CampaignConclusion -> FinalAssuranceCase -> ReleaseQualification

Invariants:
- CampaignConclusion is an immutable accepted decision; sets termination_state (OPEN, COMPLETED, COMPLETED_LIMITED).
- COMPLETED requires StopEvaluation.continuation_decision == PASS and assurance_level == ADEQUATE_FOR_DECLARED_SCOPE.
- FinalAssuranceCase is an immutable public envelope over CampaignConclusion and StopEvaluation.
- Strictly NO assurance-case / STOP cycle: FinalAssuranceCase is created AFTER CampaignConclusion, never as an input to STOP.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from .candidate_case import CandidateAssuranceCase
from .challenger import ChallengerResult
from ..stop.models import StopEvaluation


TERMINATION_STATES = {"OPEN", "COMPLETED", "COMPLETED_LIMITED"}
ASSURANCE_LEVELS = {"ADEQUATE_FOR_DECLARED_SCOPE", "BOUNDED", "INSUFFICIENT"}


@dataclass(frozen=True)
class CampaignConclusion:
    campaign_conclusion_id: str
    campaign_ref: dict[str, Any]
    source_generation_ref: dict[str, Any]
    stop_evaluation_ref: dict[str, Any]
    termination_state: str
    assurance_level: str
    bounded_conclusion_statement: str
    conclusion_command_input_history_cut: dict[str, Any]
    residual_risk_refs: tuple[dict[str, Any], ...] = ()
    candidate_assurance_case_ref: dict[str, Any] | None = None
    limited_conclusion_basis_refs: tuple[dict[str, Any], ...] = ()

    def __post_init__(self):
        if not self.campaign_conclusion_id:
            raise ValidationError("MISSING_CONCLUSION_ID", "Conclusion requires campaign_conclusion_id")
        if self.termination_state not in TERMINATION_STATES:
            raise ValidationError("INVALID_TERMINATION_STATE", f"Unknown termination_state {self.termination_state}")
        if self.assurance_level not in ASSURANCE_LEVELS:
            raise ValidationError("INVALID_ASSURANCE_LEVEL", f"Unknown assurance_level {self.assurance_level}")
        if not self.conclusion_command_input_history_cut:
            raise ValidationError("MISSING_HISTORY_CUT", "Conclusion requires conclusion_command_input_history_cut")

        # Invariant: COMPLETED requires candidate_assurance_case_ref and adequate assurance
        if self.termination_state == "COMPLETED":
            if not self.candidate_assurance_case_ref:
                raise ValidationError("COMPLETED_REQUIRES_CANDIDATE_CASE", "Full COMPLETED requires candidate_assurance_case_ref")
            if self.assurance_level != "ADEQUATE_FOR_DECLARED_SCOPE":
                raise ValidationError("COMPLETED_REQUIRES_ADEQUATE_ASSURANCE", "Full COMPLETED requires ADEQUATE_FOR_DECLARED_SCOPE")

        # Invariant: COMPLETED_LIMITED requires limited_conclusion_basis_refs
        if self.termination_state == "COMPLETED_LIMITED":
            if not self.limited_conclusion_basis_refs and not self.residual_risk_refs:
                raise ValidationError(
                    "LIMITED_REQUIRES_BASIS_REFS",
                    "COMPLETED_LIMITED requires limited_conclusion_basis_refs or residual_risk_refs",
                )

    def body(self) -> dict[str, Any]:
        data = {
            "campaign_conclusion_id": self.campaign_conclusion_id,
            "campaign_ref": dict(self.campaign_ref),
            "source_generation_ref": dict(self.source_generation_ref),
            "stop_evaluation_ref": dict(self.stop_evaluation_ref),
            "termination_state": self.termination_state,
            "assurance_level": self.assurance_level,
            "bounded_conclusion_statement": self.bounded_conclusion_statement,
            "residual_risk_refs": [dict(r) for r in self.residual_risk_refs],
            "conclusion_command_input_history_cut": dict(self.conclusion_command_input_history_cut),
        }
        if self.candidate_assurance_case_ref is not None:
            data["candidate_assurance_case_ref"] = dict(self.candidate_assurance_case_ref)
        if self.limited_conclusion_basis_refs:
            data["limited_conclusion_basis_refs"] = [dict(r) for r in self.limited_conclusion_basis_refs]
        return data

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()

    @property
    def ref(self) -> dict[str, Any]:
        return {
            "kind": "campaign_conclusion",
            "revision_digest": self.digest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::campaign_conclusion/1",
            "ref_class": "PRIOR_ACCEPTED_ONLY",
        }


@dataclass(frozen=True)
class FinalAssuranceCase:
    final_assurance_case_id: str
    campaign_conclusion_ref: dict[str, Any]
    stop_evaluation_ref: dict[str, Any]
    public_conclusion_statement_ref: dict[str, Any]
    final_case_input_history_cut: dict[str, Any]
    residual_risk_refs: tuple[dict[str, Any], ...] = ()
    candidate_assurance_case_ref: dict[str, Any] | None = None
    challenger_result_refs: tuple[dict[str, Any], ...] = ()
    limited_conclusion_basis_refs: tuple[dict[str, Any], ...] = ()

    def __post_init__(self):
        if not self.final_assurance_case_id:
            raise ValidationError("MISSING_FINAL_CASE_ID", "FinalAssuranceCase requires final_assurance_case_id")
        if not self.campaign_conclusion_ref:
            raise ValidationError("MISSING_CONCLUSION_REF", "FinalAssuranceCase requires campaign_conclusion_ref")
        if not self.stop_evaluation_ref:
            raise ValidationError("MISSING_STOP_REF", "FinalAssuranceCase requires stop_evaluation_ref")
        if not self.final_case_input_history_cut:
            raise ValidationError("MISSING_HISTORY_CUT", "FinalAssuranceCase requires final_case_input_history_cut")

    def body(self) -> dict[str, Any]:
        data = {
            "final_assurance_case_id": self.final_assurance_case_id,
            "campaign_conclusion_ref": dict(self.campaign_conclusion_ref),
            "stop_evaluation_ref": dict(self.stop_evaluation_ref),
            "residual_risk_refs": [dict(r) for r in self.residual_risk_refs],
            "public_conclusion_statement_ref": dict(self.public_conclusion_statement_ref),
            "final_case_input_history_cut": dict(self.final_case_input_history_cut),
        }
        if self.candidate_assurance_case_ref is not None:
            data["candidate_assurance_case_ref"] = dict(self.candidate_assurance_case_ref)
        if self.challenger_result_refs:
            data["challenger_result_refs"] = [dict(r) for r in self.challenger_result_refs]
        if self.limited_conclusion_basis_refs:
            data["limited_conclusion_basis_refs"] = [dict(r) for r in self.limited_conclusion_basis_refs]
        return data

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()

    @property
    def ref(self) -> dict[str, Any]:
        return {
            "kind": "final_assurance_case",
            "revision_digest": self.digest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::final_assurance_case/1",
            "ref_class": "PRIOR_ACCEPTED_ONLY",
        }

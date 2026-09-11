"""Final Skeptic Capability (WP-E5-05 / M40 / §99 / Data Contracts §80).

Implements Lane E5-B1: FALSE_POSITIVE_SKEPTIC.

Separates capability / lane specification from baseline final challenger execution
(which occurs only in M43B after CandidateAssuranceCase is frozen).

Capabilities:
- Question finding evidence and identify unsupported causal leaps.
- Formulate alternative explanations (e.g., harness artifacts, environment noise).
- Challenge finding applicability.
- Detect weak or non-contrasting oracles.
- Surface direct contradictions.
- Strictly non-mutating: produces immutable counterclaims without retroactively
  modifying CandidateAssuranceCase.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError


LANE_NAME = "E5-B1"
CHALLENGER_TYPE = "FALSE_POSITIVE_SKEPTIC"

CHALLENGE_TYPES = {
    "ALTERNATIVE_EXPLANATION",
    "QUESTION_APPLICABILITY",
    "WEAK_ORACLE",
    "CONTRADICTION",
    "UNSUPPORTED_CAUSAL_LEAP",
}

CHALLENGE_STATUSES = {
    "MATERIAL_COUNTEREVIDENCE_FOUND",
    "NO_MATERIAL_COUNTEREVIDENCE",
    "INCONCLUSIVE",
    "BLOCKED",
}


@dataclass(frozen=True)
class SkepticCounterclaim:
    counterclaim_id: str
    target_claim_ref: dict[str, Any]
    candidate_assurance_case_ref: dict[str, Any]
    challenge_type: str
    status: str
    counter_evidence_refs: tuple[dict[str, Any], ...]
    explanation: str
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self):
        if self.challenge_type not in CHALLENGE_TYPES:
            raise ValidationError(
                "INVALID_CHALLENGE_TYPE",
                f"challenge_type {self.challenge_type} must be one of {sorted(CHALLENGE_TYPES)}",
            )
        if self.status not in CHALLENGE_STATUSES:
            raise ValidationError(
                "INVALID_CHALLENGE_STATUS",
                f"status {self.status} must be one of {sorted(CHALLENGE_STATUSES)}",
            )
        if not self.candidate_assurance_case_ref:
            raise ValidationError("MISSING_CANDIDATE_REF", "Counterclaim must reference candidate_assurance_case")

    def body(self) -> dict[str, Any]:
        return {
            "counterclaim_id": self.counterclaim_id,
            "target_claim_ref": dict(self.target_claim_ref),
            "candidate_assurance_case_ref": dict(self.candidate_assurance_case_ref),
            "challenge_type": self.challenge_type,
            "status": self.status,
            "counter_evidence_refs": [dict(r) for r in self.counter_evidence_refs],
            "explanation": self.explanation,
            "reason_codes": list(self.reason_codes),
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()


class FalsePositiveSkepticCapability:
    """Lane E5-B1 FALSE_POSITIVE_SKEPTIC audit engine."""

    LANE = LANE_NAME
    TYPE = CHALLENGER_TYPE

    @staticmethod
    def audit_for_unsupported_causal_leap(
        counterclaim_id: str,
        target_claim_ref: dict[str, Any],
        candidate_ref: dict[str, Any],
        causal_chain_ref: dict[str, Any] | None,
    ) -> SkepticCounterclaim:
        """Challenge finding whose causal chain lacks supporting evidence on transitions."""
        if not causal_chain_ref or not causal_chain_ref.get("supporting_edges"):
            return SkepticCounterclaim(
                counterclaim_id=counterclaim_id,
                target_claim_ref=target_claim_ref,
                candidate_assurance_case_ref=candidate_ref,
                challenge_type="UNSUPPORTED_CAUSAL_LEAP",
                status="MATERIAL_COUNTEREVIDENCE_FOUND",
                counter_evidence_refs=(),
                explanation="Finding asserts causality without qualified supporting transition edges",
                reason_codes=("UNSUPPORTED_CAUSAL_LEAP_DETECTED",),
            )
        return SkepticCounterclaim(
            counterclaim_id=counterclaim_id,
            target_claim_ref=target_claim_ref,
            candidate_assurance_case_ref=candidate_ref,
            challenge_type="UNSUPPORTED_CAUSAL_LEAP",
            status="NO_MATERIAL_COUNTEREVIDENCE",
            counter_evidence_refs=(),
            explanation="Causal chain transitions are adequately supported",
            reason_codes=("CAUSAL_CHAIN_SUPPORT_VERIFIED",),
        )

    @staticmethod
    def audit_for_alternative_explanation(
        counterclaim_id: str,
        target_claim_ref: dict[str, Any],
        candidate_ref: dict[str, Any],
        environment_noise_evidence_ref: dict[str, Any] | None,
    ) -> SkepticCounterclaim:
        """Challenge finding when failure can be explained by harness or environment artifacts."""
        if environment_noise_evidence_ref:
            return SkepticCounterclaim(
                counterclaim_id=counterclaim_id,
                target_claim_ref=target_claim_ref,
                candidate_assurance_case_ref=candidate_ref,
                challenge_type="ALTERNATIVE_EXPLANATION",
                status="MATERIAL_COUNTEREVIDENCE_FOUND",
                counter_evidence_refs=(environment_noise_evidence_ref,),
                explanation="Observed failure accounted for by verified environmental noise/harness artifact",
                reason_codes=("ALTERNATIVE_EXPLANATION_SUBSTANTIATED",),
            )
        return SkepticCounterclaim(
            counterclaim_id=counterclaim_id,
            target_claim_ref=target_claim_ref,
            candidate_assurance_case_ref=candidate_ref,
            challenge_type="ALTERNATIVE_EXPLANATION",
            status="NO_MATERIAL_COUNTEREVIDENCE",
            counter_evidence_refs=(),
            explanation="No plausible alternative explanation found",
            reason_codes=("NO_ALTERNATIVE_EXPLANATION",),
        )

    @staticmethod
    def audit_for_weak_oracle(
        counterclaim_id: str,
        target_claim_ref: dict[str, Any],
        candidate_ref: dict[str, Any],
        oracle_qualification_ref: dict[str, Any] | None,
    ) -> SkepticCounterclaim:
        """Detect finding supported only by uncalibrated or weakened oracle."""
        if not oracle_qualification_ref or not oracle_qualification_ref.get("is_qualified"):
            return SkepticCounterclaim(
                counterclaim_id=counterclaim_id,
                target_claim_ref=target_claim_ref,
                candidate_assurance_case_ref=candidate_ref,
                challenge_type="WEAK_ORACLE",
                status="MATERIAL_COUNTEREVIDENCE_FOUND",
                counter_evidence_refs=(),
                explanation="Underlying detector lacks verified oracle qualification / activation contrast",
                reason_codes=("WEAK_ORACLE_DETECTED",),
            )
        return SkepticCounterclaim(
            counterclaim_id=counterclaim_id,
            target_claim_ref=target_claim_ref,
            candidate_assurance_case_ref=candidate_ref,
            challenge_type="WEAK_ORACLE",
            status="NO_MATERIAL_COUNTEREVIDENCE",
            counter_evidence_refs=(),
            explanation="Oracle has verified activation and 2x2 contrast qualification",
            reason_codes=("ORACLE_QUALIFIED",),
        )

    @staticmethod
    def audit_for_contradiction(
        counterclaim_id: str,
        target_claim_ref: dict[str, Any],
        candidate_ref: dict[str, Any],
        contradicting_observation_ref: dict[str, Any] | None,
    ) -> SkepticCounterclaim:
        """Identify open contradictions directly conflicting with the claim."""
        if contradicting_observation_ref:
            return SkepticCounterclaim(
                counterclaim_id=counterclaim_id,
                target_claim_ref=target_claim_ref,
                candidate_assurance_case_ref=candidate_ref,
                challenge_type="CONTRADICTION",
                status="MATERIAL_COUNTEREVIDENCE_FOUND",
                counter_evidence_refs=(contradicting_observation_ref,),
                explanation="Direct contradicting observation recorded against finding claim",
                reason_codes=("DIRECT_CONTRADICTION_FOUND",),
            )
        return SkepticCounterclaim(
            counterclaim_id=counterclaim_id,
            target_claim_ref=target_claim_ref,
            candidate_assurance_case_ref=candidate_ref,
            challenge_type="CONTRADICTION",
            status="NO_MATERIAL_COUNTEREVIDENCE",
            counter_evidence_refs=(),
            explanation="No contradicting observations found",
            reason_codes=("NO_CONTRADICTION",),
        )

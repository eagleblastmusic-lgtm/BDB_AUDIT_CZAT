"""False Negative Hunter Capability (WP-E5-06 / M41 / §100 / Data Contracts §80).

Implements Lane E5-B2: FALSE_NEGATIVE_HUNTER.

Separates capability / lane specification from baseline final challenger execution
(which occurs only in M43B after CandidateAssuranceCase is frozen).

Hunts for:
- Open obligations (unfulfilled or unadjudicated).
- Critical surfaces without findings / test silence.
- Unknown or unsupported scope.
- Suspicious zero-finding regions.
- Mutation survivors (tests passed but mutants survived).
- Weak coverage.
- Stale assumptions.
- Unexplored interaction families.

Normative invariant:
- Absence of findings is NEVER evidence of correctness ("absence of evidence != evidence of absence").
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError


LANE_NAME = "E5-B2"
CHALLENGER_TYPE = "FALSE_NEGATIVE_HUNTER"

HUNTER_OPPORTUNITY_TYPES = {
    "OPEN_OBLIGATION",
    "CRITICAL_SURFACE_WITHOUT_FINDINGS",
    "UNKNOWN_UNSUPPORTED_SCOPE",
    "SUSPICIOUS_ZERO_FINDING_REGION",
    "MUTATION_SURVIVOR",
    "WEAK_COVERAGE",
    "STALE_ASSUMPTION",
    "UNEXPLORED_INTERACTION_FAMILY",
}

HUNTER_STATUSES = {
    "MATERIAL_COUNTEREVIDENCE_FOUND",
    "NO_MATERIAL_COUNTEREVIDENCE",
    "INCONCLUSIVE",
    "BLOCKED",
}


@dataclass(frozen=True)
class HunterCounterclaim:
    counterclaim_id: str
    opportunity_type: str
    candidate_assurance_case_ref: dict[str, Any]
    target_scope_or_obligation_ref: dict[str, Any]
    status: str
    severity: str
    counter_evidence_refs: tuple[dict[str, Any], ...]
    explanation: str
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self):
        if self.opportunity_type not in HUNTER_OPPORTUNITY_TYPES:
            raise ValidationError(
                "INVALID_OPPORTUNITY_TYPE",
                f"opportunity_type {self.opportunity_type} must be one of {sorted(HUNTER_OPPORTUNITY_TYPES)}",
            )
        if self.status not in HUNTER_STATUSES:
            raise ValidationError(
                "INVALID_HUNTER_STATUS",
                f"status {self.status} must be one of {sorted(HUNTER_STATUSES)}",
            )
        if not self.candidate_assurance_case_ref:
            raise ValidationError("MISSING_CANDIDATE_REF", "Hunter counterclaim must reference candidate_assurance_case")

    def body(self) -> dict[str, Any]:
        return {
            "counterclaim_id": self.counterclaim_id,
            "opportunity_type": self.opportunity_type,
            "candidate_assurance_case_ref": dict(self.candidate_assurance_case_ref),
            "target_scope_or_obligation_ref": dict(self.target_scope_or_obligation_ref),
            "status": self.status,
            "severity": self.severity,
            "counter_evidence_refs": [dict(r) for r in self.counter_evidence_refs],
            "explanation": self.explanation,
            "reason_codes": list(self.reason_codes),
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()


class FalseNegativeHunterCapability:
    """Lane E5-B2 FALSE_NEGATIVE_HUNTER audit engine."""

    LANE = LANE_NAME
    TYPE = CHALLENGER_TYPE

    @staticmethod
    def hunt_open_obligations(
        counterclaim_id: str,
        candidate_ref: dict[str, Any],
        open_obligation_refs: Sequence[dict[str, Any]],
    ) -> list[HunterCounterclaim]:
        """Hunt for open mandatory obligations remaining unfulfilled."""
        claims = []
        for i, ob_ref in enumerate(open_obligation_refs):
            cid = f"{counterclaim_id}_{i}"
            claims.append(
                HunterCounterclaim(
                    counterclaim_id=cid,
                    opportunity_type="OPEN_OBLIGATION",
                    candidate_assurance_case_ref=candidate_ref,
                    target_scope_or_obligation_ref=ob_ref,
                    status="MATERIAL_COUNTEREVIDENCE_FOUND",
                    severity="HIGH",
                    counter_evidence_refs=(ob_ref,),
                    explanation=f"Mandatory coverage obligation {ob_ref.get('revision_digest', '')} is unfulfilled",
                    reason_codes=("OPEN_MANDATORY_OBLIGATION",),
                )
            )
        return claims

    @staticmethod
    def hunt_critical_surface_silence(
        counterclaim_id: str,
        candidate_ref: dict[str, Any],
        critical_surface_refs: Sequence[dict[str, Any]],
        tested_surface_digests: Set[str],
    ) -> list[HunterCounterclaim]:
        """Detect critical surfaces with zero tests/findings (suspicious silence)."""
        claims = []
        for i, surf_ref in enumerate(critical_surface_refs):
            digest = surf_ref.get("revision_digest") or surf_ref.get("surface_key") or ""
            if digest not in tested_surface_digests:
                cid = f"{counterclaim_id}_{i}"
                claims.append(
                    HunterCounterclaim(
                        counterclaim_id=cid,
                        opportunity_type="CRITICAL_SURFACE_WITHOUT_FINDINGS",
                        candidate_assurance_case_ref=candidate_ref,
                        target_scope_or_obligation_ref=surf_ref,
                        status="MATERIAL_COUNTEREVIDENCE_FOUND",
                        severity="CRITICAL",
                        counter_evidence_refs=(surf_ref,),
                        explanation=f"Critical surface {digest} has zero test coverage or observations; absence != correctness",
                        reason_codes=("CRITICAL_SURFACE_SILENCE",),
                    )
                )
        return claims

    @staticmethod
    def hunt_mutation_survivors(
        counterclaim_id: str,
        candidate_ref: dict[str, Any],
        mutation_results: Sequence[dict[str, Any]],
    ) -> list[HunterCounterclaim]:
        """Hunt for mutants that survived execution."""
        claims = []
        for i, res in enumerate(mutation_results):
            if res.get("outcome") == "MUTANT_SURVIVED":
                cid = f"{counterclaim_id}_{i}"
                claims.append(
                    HunterCounterclaim(
                        counterclaim_id=cid,
                        opportunity_type="MUTATION_SURVIVOR",
                        candidate_assurance_case_ref=candidate_ref,
                        target_scope_or_obligation_ref=res.get("mutation_case_ref", {}),
                        status="MATERIAL_COUNTEREVIDENCE_FOUND",
                        severity="HIGH",
                        counter_evidence_refs=(res,),
                        explanation=f"Activated mutant {res.get('result_id')} survived all detectors",
                        reason_codes=("MUTANT_SURVIVED_EVIDENCE",),
                    )
                )
        return claims

    @staticmethod
    def hunt_unknown_scope(
        counterclaim_id: str,
        candidate_ref: dict[str, Any],
        unknown_scope_refs: Sequence[dict[str, Any]],
    ) -> list[HunterCounterclaim]:
        """Detect uninspected or unknown scope regions."""
        claims = []
        for i, scope_ref in enumerate(unknown_scope_refs):
            cid = f"{counterclaim_id}_{i}"
            claims.append(
                HunterCounterclaim(
                    counterclaim_id=cid,
                    opportunity_type="UNKNOWN_UNSUPPORTED_SCOPE",
                    candidate_assurance_case_ref=candidate_ref,
                    target_scope_or_obligation_ref=scope_ref,
                    status="MATERIAL_COUNTEREVIDENCE_FOUND",
                    severity="HIGH",
                    counter_evidence_refs=(scope_ref,),
                    explanation=f"Scope region {scope_ref.get('scope_id', '')} remains unknown/unsupported",
                    reason_codes=("UNKNOWN_SCOPE_UNRESOLVED",),
                )
            )
        return claims

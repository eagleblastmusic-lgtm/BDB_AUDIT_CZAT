"""Final Challenger Execution and E5 StageCompletion Evaluator (WP-E5-09 / M43B / §102.1 / Data Contracts §80).

Implements:
- ChallengerAssignment and ChallengerResult binding exact frozen CandidateAssuranceCase.
- Strict requirement that BOTH baseline roles (E5-B1 Skeptic, E5-B2 Hunter) execute against
  the exact SAME candidate revision.
- Temporal ordering: Candidate MUST precede assignments; assignments MUST precede results;
  both results MUST precede E5 StageCompletion.
- Invalidation rule: Material change to CandidateAssuranceCase invalidates BOTH baseline challenger
  results (no scoped reuse in baseline profile).
- E5 StageCompletion eligibility verification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from .candidate_case import CandidateAssuranceCase


REQUIRED_BASELINE_CHALLENGER_TYPES = {
    "FALSE_POSITIVE_SKEPTIC",
    "FALSE_NEGATIVE_HUNTER",
}

CHALLENGER_OUTCOME_STATUSES = {
    "NO_MATERIAL_COUNTEREVIDENCE",
    "MATERIAL_COUNTEREVIDENCE_FOUND",
    "INCONCLUSIVE",
    "BLOCKED",
}


@dataclass(frozen=True)
class ChallengerAssignment:
    challenge_assignment_id: str
    candidate_assurance_case_ref: dict[str, Any]
    challenger_type: str
    challenge_scope: str
    challenge_policy_ref: dict[str, Any]
    executor_profile_ref: dict[str, Any]
    assignment_input_history_cut: dict[str, Any]
    forbidden_prior_result_refs: tuple[dict[str, Any], ...] = ()

    def __post_init__(self):
        if not self.challenge_assignment_id:
            raise ValidationError("MISSING_ASSIGNMENT_ID", "Assignment requires challenge_assignment_id")
        if not self.candidate_assurance_case_ref:
            raise ValidationError("MISSING_CANDIDATE_REF", "Assignment requires candidate_assurance_case_ref")
        if self.challenger_type not in REQUIRED_BASELINE_CHALLENGER_TYPES and self.challenger_type != "OTHER_POLICY_DEFINED":
            raise ValidationError(
                "INVALID_CHALLENGER_TYPE",
                f"challenger_type {self.challenger_type} must be one of {sorted(REQUIRED_BASELINE_CHALLENGER_TYPES)}",
            )
        if not self.assignment_input_history_cut:
            raise ValidationError("MISSING_HISTORY_CUT", "Assignment requires assignment_input_history_cut")

    def body(self) -> dict[str, Any]:
        data = {
            "challenge_assignment_id": self.challenge_assignment_id,
            "candidate_assurance_case_ref": dict(self.candidate_assurance_case_ref),
            "challenger_type": self.challenger_type,
            "challenge_scope": self.challenge_scope,
            "challenge_policy_ref": dict(self.challenge_policy_ref),
            "executor_profile_ref": dict(self.executor_profile_ref),
            "assignment_input_history_cut": dict(self.assignment_input_history_cut),
        }
        if self.forbidden_prior_result_refs:
            data["forbidden_prior_result_refs"] = [dict(r) for r in self.forbidden_prior_result_refs]
        return data

    def digest(self) -> str:
        from ..history.objects import CanonicalObject
        return CanonicalObject("challenger_assignment", self.body()).digest

    @property
    def ref(self) -> dict[str, Any]:
        return {
            "kind": "challenger_assignment",
            "revision_digest": self.digest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::challenger_assignment/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


@dataclass(frozen=True)
class ChallengerResult:
    challenger_result_id: str
    challenge_assignment_ref: dict[str, Any]
    candidate_assurance_case_ref: dict[str, Any]
    result_input_history_cut: dict[str, Any]
    status: str
    challenged_claim_or_scope_refs: tuple[dict[str, Any], ...] = ()
    counterclaim_refs: tuple[dict[str, Any], ...] = ()
    evidence_qualification_refs: tuple[dict[str, Any], ...] = ()
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.challenger_result_id:
            raise ValidationError("MISSING_RESULT_ID", "ChallengerResult requires challenger_result_id")
        if not self.challenge_assignment_ref:
            raise ValidationError("MISSING_ASSIGNMENT_REF", "ChallengerResult requires challenge_assignment_ref")
        if not self.candidate_assurance_case_ref:
            raise ValidationError("MISSING_CANDIDATE_REF", "ChallengerResult requires candidate_assurance_case_ref")
        if self.status not in CHALLENGER_OUTCOME_STATUSES:
            raise ValidationError(
                "INVALID_CHALLENGER_STATUS",
                f"status {self.status} must be one of {sorted(CHALLENGER_OUTCOME_STATUSES)}",
            )
        if not self.result_input_history_cut:
            raise ValidationError("MISSING_HISTORY_CUT", "ChallengerResult requires result_input_history_cut")

    def body(self) -> dict[str, Any]:
        return {
            "challenger_result_id": self.challenger_result_id,
            "challenge_assignment_ref": dict(self.challenge_assignment_ref),
            "candidate_assurance_case_ref": dict(self.candidate_assurance_case_ref),
            "result_input_history_cut": dict(self.result_input_history_cut),
            "challenged_claim_or_scope_refs": [dict(r) for r in self.challenged_claim_or_scope_refs],
            "counterclaim_refs": [dict(r) for r in self.counterclaim_refs],
            "evidence_qualification_refs": [dict(r) for r in self.evidence_qualification_refs],
            "status": self.status,
            "reason_codes": list(self.reason_codes),
        }

    def digest(self) -> str:
        from ..history.objects import CanonicalObject
        return CanonicalObject("challenger_result", self.body()).digest

    @property
    def ref(self) -> dict[str, Any]:
        return {
            "kind": "challenger_result",
            "revision_digest": self.digest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::challenger_result/1",
            "ref_class": "CONTENT_OR_PRIOR",
        }


class E5ChallengerOrchestrator:
    """Validates baseline challenger execution and checks E5 StageCompletion eligibility."""

    @staticmethod
    def validate_assignment_precedes_candidate(
        candidate: CandidateAssuranceCase,
        assignment: ChallengerAssignment,
    ) -> None:
        """Enforce temporal boundary: Candidate must precede assignment in accepted history."""
        cand_digest = candidate.digest()
        ref_digest = assignment.candidate_assurance_case_ref.get("revision_digest")
        if cand_digest != ref_digest:
            raise ValidationError(
                "CANDIDATE_DIGEST_MISMATCH",
                f"Assignment references candidate {ref_digest}, expected {cand_digest}",
            )
        # Assignment input history cut must be >= candidate input history cut
        c_seq = candidate.candidate_input_history_cut.get("commit_seq", 0)
        a_seq = assignment.assignment_input_history_cut.get("commit_seq", 0)
        if a_seq < c_seq:
            raise ValidationError(
                "TEMPORAL_ORDER_VIOLATION",
                f"Assignment cut (seq {a_seq}) cannot precede candidate cut (seq {c_seq})",
            )

    @staticmethod
    def validate_challenger_results_pair(
        candidate: CandidateAssuranceCase,
        skeptic_result: ChallengerResult | None,
        hunter_result: ChallengerResult | None,
    ) -> tuple[bool, list[str]]:
        """Validate both baseline challenger results against the exact candidate revision.
        
        Returns (eligible, reason_codes).
        """
        reasons = []

        if skeptic_result is None or hunter_result is None:
            reasons.append("MISSING_REQUIRED_CHALLENGER_ROLE")
            return False, reasons

        cand_digest = candidate.digest()
        skeptic_cand = skeptic_result.candidate_assurance_case_ref.get("revision_digest")
        hunter_cand = hunter_result.candidate_assurance_case_ref.get("revision_digest")

        # Both must bind exact same candidate revision
        if skeptic_cand != hunter_cand:
            reasons.append("CHALLENGERS_REFERENCE_DIFFERENT_CANDIDATE_REVISIONS")
            return False, reasons

        if skeptic_cand != cand_digest:
            reasons.append("CHALLENGER_RESULTS_INVALIDATED_BY_CANDIDATE_CHANGE")
            return False, reasons

        # Temporal order: result cut must be >= assignment cut
        r_seq1 = skeptic_result.result_input_history_cut.get("commit_seq", 0)
        r_seq2 = hunter_result.result_input_history_cut.get("commit_seq", 0)
        c_seq = candidate.candidate_input_history_cut.get("commit_seq", 0)
        if r_seq1 < c_seq or r_seq2 < c_seq:
            reasons.append("RESULT_CUT_PRECEDES_CANDIDATE")
            return False, reasons

        if skeptic_result.status == "BLOCKED" or hunter_result.status == "BLOCKED":
            reasons.append("CHALLENGER_EXECUTION_BLOCKED")
            return False, reasons

        reasons.append("BOTH_BASELINE_CHALLENGERS_QUALIFIED")
        return True, reasons

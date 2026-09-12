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
    def _cut_info(cut: Mapping[str, Any]) -> tuple[str, int, str]:
        """Return canonical HistoryCut identity; legacy commit_seq fallbacks are forbidden."""
        camp = cut.get("campaign_id")
        seq = cut.get("accepted_head_seq")
        accepted_hash = cut.get("accepted_head_hash")
        if not isinstance(camp, str) or not camp:
            raise ValidationError("NONCANONICAL_HISTORY_CUT", "HistoryCut requires campaign_id")
        if type(seq) is not int or seq < 0:
            raise ValidationError(
                "NONCANONICAL_HISTORY_CUT",
                "HistoryCut requires accepted_head_seq; commit_seq fallback is forbidden",
            )
        if not isinstance(accepted_hash, str) or not accepted_hash:
            raise ValidationError(
                "NONCANONICAL_HISTORY_CUT",
                "HistoryCut requires accepted_head_hash; commit_hash fallback is forbidden",
            )
        return camp, seq, accepted_hash

    @classmethod
    def validate_assignment_precedes_candidate(
        cls,
        candidate: CandidateAssuranceCase,
        assignment: ChallengerAssignment,
    ) -> None:
        """Enforce candidate binding and canonical temporal ordering."""
        cand_digest = candidate.digest()
        ref_digest = assignment.candidate_assurance_case_ref.get("revision_digest")
        if cand_digest != ref_digest:
            raise ValidationError(
                "CANDIDATE_DIGEST_MISMATCH",
                f"Assignment references candidate {ref_digest}, expected {cand_digest}",
            )
        cand_camp, c_seq, _ = cls._cut_info(candidate.candidate_input_history_cut)
        asgn_camp, a_seq, _ = cls._cut_info(assignment.assignment_input_history_cut)
        if cand_camp != asgn_camp:
            raise ValidationError("CAMPAIGN_MISMATCH", f"Candidate campaign {cand_camp} != assignment {asgn_camp}")
        if a_seq < c_seq:
            raise ValidationError(
                "TEMPORAL_ORDER_VIOLATION",
                f"Assignment cut (seq {a_seq}) cannot precede candidate cut (seq {c_seq})",
            )

    @classmethod
    def validate_challenger_results_pair(
        cls,
        candidate: CandidateAssuranceCase,
        skeptic_result: ChallengerResult | None,
        hunter_result: ChallengerResult | None,
        skeptic_assignment: ChallengerAssignment | None = None,
        hunter_assignment: ChallengerAssignment | None = None,
    ) -> tuple[bool, list[str]]:
        """Validate both baseline challenger roles against one exact candidate revision.

        A qualifying PASS requires the exact assignment objects.  Results alone cannot prove
        challenger role, candidate binding, or assignment-before-result ordering.
        """
        reasons: list[str] = []

        if skeptic_result is None or hunter_result is None:
            return False, ["MISSING_REQUIRED_CHALLENGER_ROLE"]

        is_blocked = False

        if skeptic_result.challenger_result_id == hunter_result.challenger_result_id:
            reasons.append("DUPLICATE_CHALLENGER_RESULT")
            is_blocked = True
        if skeptic_result.digest() == hunter_result.digest():
            if "DUPLICATE_CHALLENGER_RESULT" not in reasons:
                reasons.append("DUPLICATE_CHALLENGER_RESULT")
            is_blocked = True

        sk_asgn_ref = skeptic_result.challenge_assignment_ref.get("revision_digest")
        hu_asgn_ref = hunter_result.challenge_assignment_ref.get("revision_digest")
        if sk_asgn_ref and hu_asgn_ref and sk_asgn_ref == hu_asgn_ref:
            reasons.append("SAME_CHALLENGE_ASSIGNMENT")
            is_blocked = True

        if skeptic_assignment is None or hunter_assignment is None:
            reasons.append("MISSING_CHALLENGER_ASSIGNMENT_CONTEXT")
            is_blocked = True
        else:
            if skeptic_assignment.digest() == hunter_assignment.digest():
                if "SAME_CHALLENGE_ASSIGNMENT" not in reasons:
                    reasons.append("SAME_CHALLENGE_ASSIGNMENT")
                is_blocked = True

            if skeptic_assignment.challenger_type != "FALSE_POSITIVE_SKEPTIC":
                reasons.append("INVALID_SKEPTIC_ROLE")
                is_blocked = True
            if hunter_assignment.challenger_type != "FALSE_NEGATIVE_HUNTER":
                reasons.append("INVALID_HUNTER_ROLE")
                is_blocked = True

            cls.validate_assignment_precedes_candidate(candidate, skeptic_assignment)
            cls.validate_assignment_precedes_candidate(candidate, hunter_assignment)

            if sk_asgn_ref != skeptic_assignment.digest():
                reasons.append("RESULT_ASSIGNMENT_MISMATCH")
                is_blocked = True
            if hu_asgn_ref != hunter_assignment.digest():
                reasons.append("RESULT_ASSIGNMENT_MISMATCH")
                is_blocked = True

            sk_asgn_camp, sk_asgn_seq, _ = cls._cut_info(skeptic_assignment.assignment_input_history_cut)
            hu_asgn_camp, hu_asgn_seq, _ = cls._cut_info(hunter_assignment.assignment_input_history_cut)
            sk_res_camp, sk_res_seq, _ = cls._cut_info(skeptic_result.result_input_history_cut)
            hu_res_camp, hu_res_seq, _ = cls._cut_info(hunter_result.result_input_history_cut)

            if sk_res_camp != sk_asgn_camp or hu_res_camp != hu_asgn_camp:
                reasons.append("CAMPAIGN_MISMATCH")
                is_blocked = True
            if sk_res_seq < sk_asgn_seq or hu_res_seq < hu_asgn_seq:
                reasons.append("RESULT_PRECEDES_ASSIGNMENT")
                is_blocked = True

        cand_digest = candidate.digest()
        skeptic_cand = skeptic_result.candidate_assurance_case_ref.get("revision_digest")
        hunter_cand = hunter_result.candidate_assurance_case_ref.get("revision_digest")

        if skeptic_cand != hunter_cand:
            reasons.append("CHALLENGERS_REFERENCE_DIFFERENT_CANDIDATE_REVISIONS")
            is_blocked = True
        if skeptic_cand != cand_digest:
            reasons.append("CHALLENGER_RESULTS_INVALIDATED_BY_CANDIDATE_CHANGE")
            is_blocked = True

        cand_camp, c_seq, _ = cls._cut_info(candidate.candidate_input_history_cut)
        r_camp1, r_seq1, _ = cls._cut_info(skeptic_result.result_input_history_cut)
        r_camp2, r_seq2, _ = cls._cut_info(hunter_result.result_input_history_cut)
        if cand_camp != r_camp1 or cand_camp != r_camp2:
            reasons.append("CAMPAIGN_MISMATCH")
            is_blocked = True
        if r_seq1 < c_seq or r_seq2 < c_seq:
            reasons.append("RESULT_CUT_PRECEDES_CANDIDATE")
            is_blocked = True

        if skeptic_result.status == "BLOCKED" or hunter_result.status == "BLOCKED":
            reasons.append("CHALLENGER_EXECUTION_BLOCKED")
            is_blocked = True

        if is_blocked:
            return False, list(dict.fromkeys(reasons))

        reasons.append("BOTH_BASELINE_CHALLENGERS_QUALIFIED")
        return True, reasons

"""Mutation Framework (WP-E5-03 / M38 / §§96-97 / Data Contracts §§67-68).

Distinguishes exact mutation classes:
- IMPLEMENTATION_MUTATION
- ORACLE_MUTATION
- SPEC_ASSUMPTION_MUTATION

Normative requirements:
- Every mutation MUST have an activation proof.
- A test/detector PASS without activation proof NEVER means MUTANT_KILLED (fail-closed).
- Oracle mutation requires a 2x2 contrast experiment with known-defective target / control.
  Weakening observer on a clean target alone CANNOT prove oracle efficacy.
- Implementation mutation and oracle challenge use distinct normative outcome sets.
- Oracle challenge never aliases WEAKENING_DETECTED to MUTANT_KILLED.
- D5 depth accounts only for applicable, activated, and policy-relevant mutation obligations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError


MUTATION_CLASSES = {
    "IMPLEMENTATION_MUTATION",
    "ORACLE_MUTATION",
    "SPEC_ASSUMPTION_MUTATION",
}

IMPLEMENTATION_MUTATION_OUTCOMES = {
    "MUTANT_KILLED",
    "MUTANT_SURVIVED",
    "MUTATION_NOT_ACTIVATED",
    "INVALID_MUTATION",
    "HARNESS_FAILURE",
    "BLOCKED",
}

ORACLE_CHALLENGE_OUTCOMES = {
    "WEAKENING_DETECTED",
    "REDUNDANT_OBSERVER_FOR_CASE",
    "MUTATION_NOT_ACTIVATED",
    "INVALID_MUTATION",
    "HARNESS_FAILURE",
    "INCONCLUSIVE",
    "BASELINE_ORACLE_MISSED_DEFECT",
}

SPEC_MUTATION_OUTCOMES = IMPLEMENTATION_MUTATION_OUTCOMES

MUTATION_OUTCOMES = (
    IMPLEMENTATION_MUTATION_OUTCOMES
    | ORACLE_CHALLENGE_OUTCOMES
)


@dataclass(frozen=True)
class ActivationProof:
    """Proof of mutation activation during execution."""
    proof_id: str
    reached_location: str
    mutated_state_observed: bool
    witness_trace: tuple[str, ...] = ()

    def is_activated(self) -> bool:
        return bool(self.reached_location and self.mutated_state_observed)

    def body(self) -> dict[str, Any]:
        return {
            "proof_id": self.proof_id,
            "reached_location": self.reached_location,
            "mutated_state_observed": self.mutated_state_observed,
            "witness_trace": list(self.witness_trace),
        }


@dataclass(frozen=True)
class MutationCase:
    mutation_id: str
    mutation_revision: str
    mutation_class: str
    target_claim_or_invariant_ref: dict[str, Any]
    target_location: str
    activation_predicate: dict[str, Any]
    expected_detector_or_observer: str
    positive_control_ref: dict[str, Any]
    negative_control_ref: dict[str, Any]
    clean_target_ref: dict[str, Any]
    known_defective_target_ref: dict[str, Any] | None = None

    def __post_init__(self):
        if self.mutation_class not in MUTATION_CLASSES:
            raise ValidationError(
                "INVALID_MUTATION_CLASS",
                f"mutation_class {self.mutation_class} must be one of {sorted(MUTATION_CLASSES)}",
            )
        if not self.target_location:
            raise ValidationError("MISSING_TARGET_LOCATION", "Mutation requires target_location")
        if not self.expected_detector_or_observer:
            raise ValidationError("MISSING_OBSERVER", "Mutation requires expected_detector_or_observer")

    def body(self) -> dict[str, Any]:
        return {
            "mutation_id": self.mutation_id,
            "mutation_revision": self.mutation_revision,
            "mutation_class": self.mutation_class,
            "target_claim_or_invariant_ref": dict(self.target_claim_or_invariant_ref),
            "target_location": self.target_location,
            "activation_predicate": dict(self.activation_predicate),
            "expected_detector_or_observer": self.expected_detector_or_observer,
            "positive_control_ref": dict(self.positive_control_ref),
            "negative_control_ref": dict(self.negative_control_ref),
            "clean_target_ref": dict(self.clean_target_ref),
            "known_defective_target_ref": dict(self.known_defective_target_ref) if self.known_defective_target_ref else None,
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()


@dataclass(frozen=True)
class MutationResult:
    result_id: str
    mutation_case_ref: dict[str, Any]
    mutation_class: str
    outcome: str
    activation_proven: bool
    activation_proof: ActivationProof | None = None
    contrast_2x2_results: dict[str, Any] | None = None
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self):
        if self.mutation_class == "ORACLE_MUTATION":
            allowed = ORACLE_CHALLENGE_OUTCOMES
        elif self.mutation_class == "IMPLEMENTATION_MUTATION":
            allowed = IMPLEMENTATION_MUTATION_OUTCOMES
        elif self.mutation_class == "SPEC_ASSUMPTION_MUTATION":
            allowed = SPEC_MUTATION_OUTCOMES
        else:
            raise ValidationError(
                "INVALID_MUTATION_CLASS",
                self.mutation_class,
            )
        if self.outcome not in allowed:
            raise ValidationError(
                "INVALID_MUTATION_OUTCOME",
                (
                    f"{self.mutation_class} outcome {self.outcome} "
                    f"must be one of {sorted(allowed)}"
                ),
            )
        activation_required = {
            "MUTANT_KILLED",
            "MUTANT_SURVIVED",
            "WEAKENING_DETECTED",
            "REDUNDANT_OBSERVER_FOR_CASE",
            "BASELINE_ORACLE_MISSED_DEFECT",
        }
        if self.outcome in activation_required and not self.activation_proven:
            code = (
                "MUTANT_KILLED_WITHOUT_ACTIVATION"
                if self.outcome == "MUTANT_KILLED"
                else "MUTATION_OUTCOME_WITHOUT_ACTIVATION"
            )
            detail = (
                f"Cannot classify {self.outcome} without "
                "verified activation proof"
            )
            if code == "MUTANT_KILLED_WITHOUT_ACTIVATION":
                detail = (
                    "MUTATION_OUTCOME_WITHOUT_ACTIVATION: "
                    + detail
                )
            raise ValidationError(code, detail)

    def body(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "mutation_case_ref": dict(self.mutation_case_ref),
            "mutation_class": self.mutation_class,
            "outcome": self.outcome,
            "activation_proven": self.activation_proven,
            "activation_proof": self.activation_proof.body() if self.activation_proof else None,
            "contrast_2x2_results": dict(self.contrast_2x2_results) if self.contrast_2x2_results else None,
            "reason_codes": list(self.reason_codes),
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()


class MutationEngine:
    """Evaluates implementation mutations, oracle challenges, and specification mutations."""

    @staticmethod
    def evaluate_implementation_mutation(
        result_id: str,
        case: MutationCase,
        activation_proof: ActivationProof | None,
        detector_triggered: bool,
        harness_error: bool = False,
    ) -> MutationResult:
        """Evaluate an IMPLEMENTATION_MUTATION case."""
        case_ref = {
            "mutation_id": case.mutation_id,
            "mutation_revision": case.mutation_revision,
            "mutation_class": case.mutation_class,
        }

        if harness_error:
            return MutationResult(
                result_id=result_id,
                mutation_case_ref=case_ref,
                mutation_class=case.mutation_class,
                outcome="HARNESS_FAILURE",
                activation_proven=False,
                activation_proof=activation_proof,
                reason_codes=("HARNESS_EXECUTION_ERROR",),
            )

        # Check activation proof
        is_active = activation_proof is not None and activation_proof.is_activated()
        if not is_active:
            return MutationResult(
                result_id=result_id,
                mutation_case_ref=case_ref,
                mutation_class=case.mutation_class,
                outcome="MUTATION_NOT_ACTIVATED",
                activation_proven=False,
                activation_proof=activation_proof,
                reason_codes=("NO_ACTIVATION_PROOF",),
            )

        if detector_triggered:
            return MutationResult(
                result_id=result_id,
                mutation_case_ref=case_ref,
                mutation_class=case.mutation_class,
                outcome="MUTANT_KILLED",
                activation_proven=True,
                activation_proof=activation_proof,
                reason_codes=("DETECTOR_TRIGGERED_ON_ACTIVATED_MUTANT",),
            )
        else:
            return MutationResult(
                result_id=result_id,
                mutation_case_ref=case_ref,
                mutation_class=case.mutation_class,
                outcome="MUTANT_SURVIVED",
                activation_proven=True,
                activation_proof=activation_proof,
                reason_codes=("MUTANT_SURVIVED_DETECTION",),
            )

    @staticmethod
    def evaluate_oracle_mutation(
        result_id: str,
        case: MutationCase,
        activation_proof: ActivationProof | None,
        clean_strong_detected: bool,
        clean_weak_detected: bool,
        defective_strong_detected: bool,
        defective_weak_detected: bool,
        harness_error: bool = False,
    ) -> MutationResult:
        """Evaluate an ORACLE_MUTATION using a 2x2 contrast experiment."""
        case_ref = {
            "mutation_id": case.mutation_id,
            "mutation_revision": case.mutation_revision,
            "mutation_class": case.mutation_class,
        }

        if harness_error:
            return MutationResult(
                result_id=result_id,
                mutation_case_ref=case_ref,
                mutation_class=case.mutation_class,
                outcome="HARNESS_FAILURE",
                activation_proven=False,
                activation_proof=activation_proof,
                reason_codes=("HARNESS_EXECUTION_ERROR",),
            )

        # Fail-closed: Oracle mutation REQUIRES a known-defective target ref
        if not case.known_defective_target_ref:
            return MutationResult(
                result_id=result_id,
                mutation_case_ref=case_ref,
                mutation_class=case.mutation_class,
                outcome="INVALID_MUTATION",
                activation_proven=False,
                activation_proof=activation_proof,
                reason_codes=("ORACLE_MUTATION_MISSING_KNOWN_DEFECTIVE_TARGET",),
            )

        is_active = activation_proof is not None and activation_proof.is_activated()
        if not is_active:
            return MutationResult(
                result_id=result_id,
                mutation_case_ref=case_ref,
                mutation_class=case.mutation_class,
                outcome="MUTATION_NOT_ACTIVATED",
                activation_proven=False,
                activation_proof=activation_proof,
                reason_codes=("NO_ACTIVATION_PROOF",),
            )

        contrast = {
            "clean_strong_detected": clean_strong_detected,
            "clean_weak_detected": clean_weak_detected,
            "defective_strong_detected": defective_strong_detected,
            "defective_weak_detected": defective_weak_detected,
        }

        # A detector firing on the clean control makes the contrast inconclusive.
        if clean_strong_detected or clean_weak_detected:
            return MutationResult(
                result_id=result_id,
                mutation_case_ref=case_ref,
                mutation_class=case.mutation_class,
                outcome="INCONCLUSIVE",
                activation_proven=True,
                activation_proof=activation_proof,
                contrast_2x2_results=contrast,
                reason_codes=("CLEAN_TARGET_TRIGGERED_ORACLE",),
            )

        # Strong oracle missing the known defect is its own normative outcome.
        if not defective_strong_detected:
            return MutationResult(
                result_id=result_id,
                mutation_case_ref=case_ref,
                mutation_class=case.mutation_class,
                outcome="BASELINE_ORACLE_MISSED_DEFECT",
                activation_proven=True,
                activation_proof=activation_proof,
                contrast_2x2_results=contrast,
                reason_codes=("BASELINE_ORACLE_MISSED_DEFECT",),
            )

        # Strong detects and weakened misses: weakening was materially detected.
        if not defective_weak_detected:
            return MutationResult(
                result_id=result_id,
                mutation_case_ref=case_ref,
                mutation_class=case.mutation_class,
                outcome="WEAKENING_DETECTED",
                activation_proven=True,
                activation_proof=activation_proof,
                contrast_2x2_results=contrast,
                reason_codes=("WEAKENING_DETECTED",),
            )

        # Both detect the known defect after confirmed activation.
        return MutationResult(
            result_id=result_id,
            mutation_case_ref=case_ref,
            mutation_class=case.mutation_class,
            outcome="REDUNDANT_OBSERVER_FOR_CASE",
            activation_proven=True,
            activation_proof=activation_proof,
            contrast_2x2_results=contrast,
            reason_codes=("REDUNDANT_OBSERVER_FOR_CASE",),
        )

    @staticmethod
    def evaluate_spec_mutation(
        result_id: str,
        case: MutationCase,
        activation_proof: ActivationProof | None,
        spec_violation_caught: bool,
        harness_error: bool = False,
    ) -> MutationResult:
        """Evaluate SPEC_ASSUMPTION_MUTATION without conflating with implementation defects."""
        case_ref = {
            "mutation_id": case.mutation_id,
            "mutation_revision": case.mutation_revision,
            "mutation_class": case.mutation_class,
        }
        if harness_error:
            return MutationResult(
                result_id=result_id,
                mutation_case_ref=case_ref,
                mutation_class=case.mutation_class,
                outcome="HARNESS_FAILURE",
                activation_proven=False,
                activation_proof=activation_proof,
                reason_codes=("HARNESS_EXECUTION_ERROR",),
            )

        is_active = activation_proof is not None and activation_proof.is_activated()
        if not is_active:
            return MutationResult(
                result_id=result_id,
                mutation_case_ref=case_ref,
                mutation_class=case.mutation_class,
                outcome="MUTATION_NOT_ACTIVATED",
                activation_proven=False,
                activation_proof=activation_proof,
                reason_codes=("NO_ACTIVATION_PROOF",),
            )

        if spec_violation_caught:
            return MutationResult(
                result_id=result_id,
                mutation_case_ref=case_ref,
                mutation_class=case.mutation_class,
                outcome="MUTANT_KILLED",
                activation_proven=True,
                activation_proof=activation_proof,
                reason_codes=("SPEC_ASSUMPTION_MUTANT_KILLED",),
            )
        else:
            return MutationResult(
                result_id=result_id,
                mutation_case_ref=case_ref,
                mutation_class=case.mutation_class,
                outcome="MUTANT_SURVIVED",
                activation_proven=True,
                activation_proof=activation_proof,
                reason_codes=("SPEC_ASSUMPTION_MUTANT_SURVIVED",),
            )

    @staticmethod
    def filter_d5_depth_obligations(
        results: Sequence[MutationResult],
        policy_relevant_ids: Set[str] | None = None,
    ) -> list[MutationResult]:
        """Filter results to only applicable, activated, and policy-relevant obligations for D5 depth."""
        filtered = []
        for r in results:
            if not r.activation_proven:
                continue
            if r.outcome not in (
                "MUTANT_KILLED",
                "MUTANT_SURVIVED",
                "WEAKENING_DETECTED",
                "REDUNDANT_OBSERVER_FOR_CASE",
            ):
                continue
            case_id = r.mutation_case_ref.get("mutation_id", "")
            if policy_relevant_ids is not None and case_id not in policy_relevant_ids:
                continue
            filtered.append(r)
        return filtered

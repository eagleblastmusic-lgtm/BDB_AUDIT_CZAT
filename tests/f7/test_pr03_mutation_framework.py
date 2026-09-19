"""Targeted tests for Mutation Framework (PR-E5-03 / M38)."""
import pytest
from bdb_audit.attack.mutation import (
    ActivationProof,
    MutationCase,
    MutationResult,
    MutationEngine,
    MUTATION_CLASSES,
    MUTATION_OUTCOMES,
    IMPLEMENTATION_MUTATION_OUTCOMES,
    ORACLE_CHALLENGE_OUTCOMES,
)
from bdb_audit.core.errors import ValidationError


@pytest.fixture
def mock_refs():
    ref = {
        "kind": "mock",
        "revision_digest": "r" * 64,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::mock/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    return {
        "target_claim": ref,
        "pos_ctrl": ref,
        "neg_ctrl": ref,
        "clean_target": ref,
        "defective_target": ref,
    }


def test_killed_activated_implementation_mutant(mock_refs):
    case = MutationCase(
        mutation_id="mut_001",
        mutation_revision="rev_1",
        mutation_class="IMPLEMENTATION_MUTATION",
        target_claim_or_invariant_ref=mock_refs["target_claim"],
        target_location="module.func:L42",
        activation_predicate={"condition": "call_count > 0"},
        expected_detector_or_observer="test_invariant_holds",
        positive_control_ref=mock_refs["pos_ctrl"],
        negative_control_ref=mock_refs["neg_ctrl"],
        clean_target_ref=mock_refs["clean_target"],
    )

    proof = ActivationProof(
        proof_id="proof_001",
        reached_location="module.func:L42",
        mutated_state_observed=True,
    )
    assert proof.is_activated() is True

    result = MutationEngine.evaluate_implementation_mutation(
        result_id="res_001",
        case=case,
        activation_proof=proof,
        detector_triggered=True,
    )
    assert result.outcome == "MUTANT_KILLED"
    assert result.activation_proven is True


def test_mutant_survived(mock_refs):
    case = MutationCase(
        mutation_id="mut_002",
        mutation_revision="rev_1",
        mutation_class="IMPLEMENTATION_MUTATION",
        target_claim_or_invariant_ref=mock_refs["target_claim"],
        target_location="module.func:L50",
        activation_predicate={"condition": "call_count > 0"},
        expected_detector_or_observer="test_detector",
        positive_control_ref=mock_refs["pos_ctrl"],
        negative_control_ref=mock_refs["neg_ctrl"],
        clean_target_ref=mock_refs["clean_target"],
    )

    proof = ActivationProof(
        proof_id="proof_002",
        reached_location="module.func:L50",
        mutated_state_observed=True,
    )

    result = MutationEngine.evaluate_implementation_mutation(
        result_id="res_002",
        case=case,
        activation_proof=proof,
        detector_triggered=False,  # detector did NOT catch it -> survived!
    )
    assert result.outcome == "MUTANT_SURVIVED"
    assert result.activation_proven is True


def test_mutation_not_activated(mock_refs):
    case = MutationCase(
        mutation_id="mut_003",
        mutation_revision="rev_1",
        mutation_class="IMPLEMENTATION_MUTATION",
        target_claim_or_invariant_ref=mock_refs["target_claim"],
        target_location="module.func:L60",
        activation_predicate={"condition": "call_count > 0"},
        expected_detector_or_observer="test_detector",
        positive_control_ref=mock_refs["pos_ctrl"],
        negative_control_ref=mock_refs["neg_ctrl"],
        clean_target_ref=mock_refs["clean_target"],
    )

    # Mutation location not reached / state not observed
    proof = ActivationProof(
        proof_id="proof_003",
        reached_location="",
        mutated_state_observed=False,
    )
    assert proof.is_activated() is False

    result = MutationEngine.evaluate_implementation_mutation(
        result_id="res_003",
        case=case,
        activation_proof=proof,
        detector_triggered=True,  # Even if detector passes/triggers, no activation means NOT ACTIVATED!
    )
    assert result.outcome == "MUTATION_NOT_ACTIVATED"
    assert result.activation_proven is False


def test_mutation_without_activation_proof_fail_closed(mock_refs):
    """Direct invariant check: constructing MUTANT_KILLED without activation_proven=True must fail closed."""
    with pytest.raises(ValidationError, match="MUTATION_OUTCOME_WITHOUT_ACTIVATION"):
        MutationResult(
            result_id="res_illegal",
            mutation_case_ref={"mutation_id": "m1"},
            mutation_class="IMPLEMENTATION_MUTATION",
            outcome="MUTANT_KILLED",
            activation_proven=False,  # ILLEGAL!
        )


def test_harness_failure(mock_refs):
    case = MutationCase(
        mutation_id="mut_004",
        mutation_revision="rev_1",
        mutation_class="IMPLEMENTATION_MUTATION",
        target_claim_or_invariant_ref=mock_refs["target_claim"],
        target_location="module.func:L70",
        activation_predicate={"condition": "call_count > 0"},
        expected_detector_or_observer="test_detector",
        positive_control_ref=mock_refs["pos_ctrl"],
        negative_control_ref=mock_refs["neg_ctrl"],
        clean_target_ref=mock_refs["clean_target"],
    )

    result = MutationEngine.evaluate_implementation_mutation(
        result_id="res_004",
        case=case,
        activation_proof=None,
        detector_triggered=False,
        harness_error=True,
    )
    assert result.outcome == "HARNESS_FAILURE"
    assert result.activation_proven is False


def test_oracle_mutation_clean_target_insufficient_and_2x2_contrast(mock_refs):
    # Without known_defective_target_ref -> INVALID_MUTATION
    invalid_case = MutationCase(
        mutation_id="oracle_mut_01",
        mutation_revision="rev_1",
        mutation_class="ORACLE_MUTATION",
        target_claim_or_invariant_ref=mock_refs["target_claim"],
        target_location="oracle.verify:L10",
        activation_predicate={"condition": "oracle_called"},
        expected_detector_or_observer="weakened_oracle",
        positive_control_ref=mock_refs["pos_ctrl"],
        negative_control_ref=mock_refs["neg_ctrl"],
        clean_target_ref=mock_refs["clean_target"],
        known_defective_target_ref=None,  # Missing!
    )
    proof = ActivationProof("p_oracle", "oracle.verify:L10", True)
    res_invalid = MutationEngine.evaluate_oracle_mutation(
        "res_inv", invalid_case, proof, False, False, True, False
    )
    assert res_invalid.outcome == "INVALID_MUTATION"

    # Valid case with known_defective_target_ref
    valid_case = MutationCase(
        mutation_id="oracle_mut_02",
        mutation_revision="rev_1",
        mutation_class="ORACLE_MUTATION",
        target_claim_or_invariant_ref=mock_refs["target_claim"],
        target_location="oracle.verify:L10",
        activation_predicate={"condition": "oracle_called"},
        expected_detector_or_observer="weakened_oracle",
        positive_control_ref=mock_refs["pos_ctrl"],
        negative_control_ref=mock_refs["neg_ctrl"],
        clean_target_ref=mock_refs["clean_target"],
        known_defective_target_ref=mock_refs["defective_target"],
    )

    # 1. Baseline oracle missed defect -> defective_strong_detected is False
    res_miss = MutationEngine.evaluate_oracle_mutation(
        "res_miss", valid_case, proof,
        clean_strong_detected=False, clean_weak_detected=False,
        defective_strong_detected=False, defective_weak_detected=False,
    )
    assert res_miss.outcome == "BASELINE_ORACLE_MISSED_DEFECT"
    assert "BASELINE_ORACLE_MISSED_DEFECT" in res_miss.reason_codes

    # 2. Strong oracle caught it, weakened oracle missed it -> WEAKENING_DETECTED
    res_killed = MutationEngine.evaluate_oracle_mutation(
        "res_killed", valid_case, proof,
        clean_strong_detected=False, clean_weak_detected=False,
        defective_strong_detected=True, defective_weak_detected=False,
    )
    assert res_killed.outcome == "WEAKENING_DETECTED"
    assert "WEAKENING_DETECTED" in res_killed.reason_codes

    # 3. Strong caught it, weakened STILL caught it -> REDUNDANT_OBSERVER_FOR_CASE
    res_redundant = MutationEngine.evaluate_oracle_mutation(
        "res_red", valid_case, proof,
        clean_strong_detected=False, clean_weak_detected=False,
        defective_strong_detected=True, defective_weak_detected=True,
    )
    assert res_redundant.outcome == "REDUNDANT_OBSERVER_FOR_CASE"
    assert "REDUNDANT_OBSERVER_FOR_CASE" in res_redundant.reason_codes

    # Oracle outcomes must never be silently aliased to implementation mutation.
    with pytest.raises(ValidationError, match="INVALID_MUTATION_OUTCOME"):
        MutationResult(
            "oracle_bad",
            {"mutation_id": "oracle_mut_02"},
            "ORACLE_MUTATION",
            "MUTANT_KILLED",
            activation_proven=True,
        )

    assert "MUTANT_KILLED" in IMPLEMENTATION_MUTATION_OUTCOMES
    assert "MUTANT_KILLED" not in ORACLE_CHALLENGE_OUTCOMES
    assert "WEAKENING_DETECTED" in ORACLE_CHALLENGE_OUTCOMES


def test_d5_depth_filtering():
    """D5 depth accounts only for applicable, activated, and policy-relevant mutation obligations."""
    case_ref1 = {"mutation_id": "m1"}
    case_ref2 = {"mutation_id": "m2"}
    case_ref3 = {"mutation_id": "m3"}

    r1 = MutationResult("r1", case_ref1, "IMPLEMENTATION_MUTATION", "MUTANT_KILLED", activation_proven=True)
    r2 = MutationResult("r2", case_ref2, "IMPLEMENTATION_MUTATION", "MUTATION_NOT_ACTIVATED", activation_proven=False)
    r3 = MutationResult("r3", case_ref3, "IMPLEMENTATION_MUTATION", "MUTANT_SURVIVED", activation_proven=True)

    # Policy relevant set: {"m1", "m2"}
    filtered = MutationEngine.filter_d5_depth_obligations([r1, r2, r3], policy_relevant_ids={"m1", "m2"})
    # r2 is not activated -> excluded. r3 is not in policy_relevant_ids -> excluded.
    assert len(filtered) == 1
    assert filtered[0].result_id == "r1"

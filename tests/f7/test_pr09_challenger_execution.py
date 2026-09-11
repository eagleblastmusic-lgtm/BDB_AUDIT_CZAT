"""Targeted tests for Final Challenger Execution & StageCompletion Eligibility (PR-E5-09 / M43B)."""
import pytest
from jsonschema import Draft202012Validator

from bdb_audit.assurance.candidate_case import (
    CandidateAssuranceCase,
    CandidateAssuranceCaseBuilder,
)
from bdb_audit.assurance.challenger import (
    ChallengerAssignment,
    ChallengerResult,
    E5ChallengerOrchestrator,
)
from bdb_audit.core.errors import ValidationError
from bdb_audit.schemas.foundation import executable_schema


@pytest.fixture
def candidate_and_context():
    hcut = {
        "campaign_id": "CAMP-001",
        "commit_seq": 15,
        "commit_hash": "a" * 64,
    }
    camp_ref = {
        "kind": "campaign_genesis",
        "revision_digest": "cg" * 32,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::campaign_genesis/1",
        "ref_class": "PRIOR_ACCEPTED_ONLY",
    }
    src_ref = {
        "kind": "source_generation",
        "revision_digest": "sg" * 32,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_generation/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    scope_ref = {
        "kind": "inventory_revision",
        "revision_digest": "inv" * 21 + "0",
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::inventory_revision/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    claim_set_ref = {
        "kind": "claim_set",
        "revision_digest": "cs" * 32,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::claim_set/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }

    builder = CandidateAssuranceCaseBuilder(
        case_id="cac_001",
        campaign_ref=camp_ref,
        source_generation_ref=src_ref,
        candidate_input_history_cut=hcut,
        scope_inventory_ref=scope_ref,
        assurance_claim_set_ref=claim_set_ref,
    )
    cac = builder.build()
    return cac, hcut


def test_valid_challenger_assignments_and_results_schema(candidate_and_context):
    cac, hcut = candidate_and_context
    assign_cut = {"campaign_id": "CAMP-001", "commit_seq": 16, "commit_hash": "b" * 64}
    res_cut = {"campaign_id": "CAMP-001", "commit_seq": 17, "commit_hash": "c" * 64}

    pol_ref = {
        "kind": "policy_revision",
        "revision_digest": "pol" * 21 + "0",
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::policy_revision/1",
        "ref_class": "HISTORY_CONTEXT_BINDING",
    }
    exec_ref = {
        "kind": "executor_spec",
        "revision_digest": "ex" * 32,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::executor_spec/1",
        "ref_class": "HISTORY_CONTEXT_BINDING",
    }

    # E5-B1 Skeptic Assignment
    asgn_skeptic = ChallengerAssignment(
        challenge_assignment_id="asgn_sk_01",
        candidate_assurance_case_ref=cac.ref,
        challenger_type="FALSE_POSITIVE_SKEPTIC",
        challenge_scope="ALL_FINDINGS",
        challenge_policy_ref=pol_ref,
        executor_profile_ref=exec_ref,
        assignment_input_history_cut=assign_cut,
    )
    Draft202012Validator(executable_schema("challenger_assignment")).validate(asgn_skeptic.body())

    # E5-B1 Skeptic Result
    res_skeptic = ChallengerResult(
        challenger_result_id="res_sk_01",
        challenge_assignment_ref=asgn_skeptic.ref,
        candidate_assurance_case_ref=cac.ref,
        result_input_history_cut=res_cut,
        status="NO_MATERIAL_COUNTEREVIDENCE",
        reason_codes=("ALL_FINDINGS_ROBUST",),
    )
    Draft202012Validator(executable_schema("challenger_result")).validate(res_skeptic.body())

    # E5-B2 Hunter Assignment
    asgn_hunter = ChallengerAssignment(
        challenge_assignment_id="asgn_hu_01",
        candidate_assurance_case_ref=cac.ref,
        challenger_type="FALSE_NEGATIVE_HUNTER",
        challenge_scope="ALL_OBLIGATIONS",
        challenge_policy_ref=pol_ref,
        executor_profile_ref=exec_ref,
        assignment_input_history_cut=assign_cut,
    )
    Draft202012Validator(executable_schema("challenger_assignment")).validate(asgn_hunter.body())

    # E5-B2 Hunter Result
    res_hunter = ChallengerResult(
        challenger_result_id="res_hu_01",
        challenge_assignment_ref=asgn_hunter.ref,
        candidate_assurance_case_ref=cac.ref,
        result_input_history_cut=res_cut,
        status="NO_MATERIAL_COUNTEREVIDENCE",
        reason_codes=("NO_OPEN_OBLIGATIONS",),
    )
    Draft202012Validator(executable_schema("challenger_result")).validate(res_hunter.body())

    # Both valid -> StageCompletion eligible!
    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(
        cac, res_skeptic, res_hunter
    )
    assert eligible is True
    assert "BOTH_BASELINE_CHALLENGERS_QUALIFIED" in reasons


def test_different_candidate_revision_rejected(candidate_and_context):
    cac, hcut = candidate_and_context
    res_cut = {"campaign_id": "CAMP-001", "commit_seq": 17, "commit_hash": "c" * 64}
    asgn_ref = {"kind": "challenger_assignment", "revision_digest": "asgn"}

    res_skeptic = ChallengerResult(
        challenger_result_id="res_sk",
        challenge_assignment_ref=asgn_ref,
        candidate_assurance_case_ref=cac.ref,
        result_input_history_cut=res_cut,
        status="NO_MATERIAL_COUNTEREVIDENCE",
    )

    other_cac_ref = dict(cac.ref)
    other_cac_ref["revision_digest"] = "different_candidate_digest"

    res_hunter = ChallengerResult(
        challenger_result_id="res_hu",
        challenge_assignment_ref=asgn_ref,
        candidate_assurance_case_ref=other_cac_ref,  # Different!
        result_input_history_cut=res_cut,
        status="NO_MATERIAL_COUNTEREVIDENCE",
    )

    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(
        cac, res_skeptic, res_hunter
    )
    assert eligible is False
    assert "CHALLENGERS_REFERENCE_DIFFERENT_CANDIDATE_REVISIONS" in reasons


def test_candidate_revision_change_invalidates_both(candidate_and_context):
    cac, hcut = candidate_and_context
    res_cut = {"campaign_id": "CAMP-001", "commit_seq": 17, "commit_hash": "c" * 64}
    asgn_ref = {"kind": "challenger_assignment", "revision_digest": "asgn"}

    # Results referencing old candidate
    old_ref = dict(cac.ref)
    old_ref["revision_digest"] = "old_candidate_digest"

    res_skeptic = ChallengerResult(
        challenger_result_id="res_sk",
        challenge_assignment_ref=asgn_ref,
        candidate_assurance_case_ref=old_ref,
        result_input_history_cut=res_cut,
        status="NO_MATERIAL_COUNTEREVIDENCE",
    )
    res_hunter = ChallengerResult(
        challenger_result_id="res_hu",
        challenge_assignment_ref=asgn_ref,
        candidate_assurance_case_ref=old_ref,
        result_input_history_cut=res_cut,
        status="NO_MATERIAL_COUNTEREVIDENCE",
    )

    # Now evaluate against new current candidate
    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(
        cac, res_skeptic, res_hunter
    )
    assert eligible is False
    assert "CHALLENGER_RESULTS_INVALIDATED_BY_CANDIDATE_CHANGE" in reasons


def test_only_one_challenger_blocks_stage_completion(candidate_and_context):
    cac, hcut = candidate_and_context
    res_cut = {"campaign_id": "CAMP-001", "commit_seq": 17, "commit_hash": "c" * 64}
    asgn_ref = {"kind": "challenger_assignment", "revision_digest": "asgn"}

    res_skeptic = ChallengerResult(
        challenger_result_id="res_sk",
        challenge_assignment_ref=asgn_ref,
        candidate_assurance_case_ref=cac.ref,
        result_input_history_cut=res_cut,
        status="NO_MATERIAL_COUNTEREVIDENCE",
    )

    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(
        cac, res_skeptic, None  # Hunter missing!
    )
    assert eligible is False
    assert "MISSING_REQUIRED_CHALLENGER_ROLE" in reasons


def test_temporal_boundary_assignment_before_candidate(candidate_and_context):
    cac, hcut = candidate_and_context
    # Assignment with earlier cut than candidate
    early_cut = {"campaign_id": "CAMP-001", "commit_seq": 10, "commit_hash": "early"}
    pol_ref = {"kind": "policy_revision", "revision_digest": "pol"}
    exec_ref = {"kind": "executor_spec", "revision_digest": "ex"}

    assignment = ChallengerAssignment(
        challenge_assignment_id="asgn_early",
        candidate_assurance_case_ref=cac.ref,
        challenger_type="FALSE_POSITIVE_SKEPTIC",
        challenge_scope="ALL",
        challenge_policy_ref=pol_ref,
        executor_profile_ref=exec_ref,
        assignment_input_history_cut=early_cut,
    )

    with pytest.raises(ValidationError, match="TEMPORAL_ORDER_VIOLATION"):
        E5ChallengerOrchestrator.validate_assignment_precedes_candidate(cac, assignment)

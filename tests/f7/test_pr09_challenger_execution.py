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
        "accepted_head_seq": 15,
        "accepted_head_hash": "a" * 64,
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
    assign_cut = {"campaign_id": "CAMP-001", "accepted_head_seq": 16, "accepted_head_hash": "b" * 64}
    res_cut = {"campaign_id": "CAMP-001", "accepted_head_seq": 17, "accepted_head_hash": "c" * 64}

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

    res_skeptic = ChallengerResult(
        challenger_result_id="res_sk_01",
        challenge_assignment_ref=asgn_skeptic.ref,
        candidate_assurance_case_ref=cac.ref,
        result_input_history_cut=res_cut,
        status="NO_MATERIAL_COUNTEREVIDENCE",
        reason_codes=("ALL_FINDINGS_ROBUST",),
    )
    Draft202012Validator(executable_schema("challenger_result")).validate(res_skeptic.body())

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

    res_hunter = ChallengerResult(
        challenger_result_id="res_hu_01",
        challenge_assignment_ref=asgn_hunter.ref,
        candidate_assurance_case_ref=cac.ref,
        result_input_history_cut=res_cut,
        status="NO_MATERIAL_COUNTEREVIDENCE",
        reason_codes=("NO_OPEN_OBLIGATIONS",),
    )
    Draft202012Validator(executable_schema("challenger_result")).validate(res_hunter.body())

    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(
        cac,
        res_skeptic,
        res_hunter,
        skeptic_assignment=asgn_skeptic,
        hunter_assignment=asgn_hunter,
    )
    assert eligible is True
    assert "BOTH_BASELINE_CHALLENGERS_QUALIFIED" in reasons


def test_result_only_pair_cannot_self_qualify(candidate_and_context):
    cac, _ = candidate_and_context
    assign_cut = {"campaign_id": "CAMP-001", "accepted_head_seq": 16, "accepted_head_hash": "b" * 64}
    res_cut = {"campaign_id": "CAMP-001", "accepted_head_seq": 17, "accepted_head_hash": "c" * 64}
    pol_ref = {"kind": "policy_revision", "revision_digest": "p" * 64}
    exec_ref = {"kind": "executor_spec", "revision_digest": "e" * 64}
    sk = ChallengerAssignment("asgn_sk", cac.ref, "FALSE_POSITIVE_SKEPTIC", "ALL", pol_ref, exec_ref, assign_cut)
    hu = ChallengerAssignment("asgn_hu", cac.ref, "FALSE_NEGATIVE_HUNTER", "ALL", pol_ref, exec_ref, assign_cut)
    sk_result = ChallengerResult("res_sk", sk.ref, cac.ref, res_cut, "NO_MATERIAL_COUNTEREVIDENCE")
    hu_result = ChallengerResult("res_hu", hu.ref, cac.ref, res_cut, "NO_MATERIAL_COUNTEREVIDENCE")

    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(cac, sk_result, hu_result)
    assert eligible is False
    assert "MISSING_CHALLENGER_ASSIGNMENT_CONTEXT" in reasons


def test_different_candidate_revision_rejected(candidate_and_context):
    cac, hcut = candidate_and_context
    res_cut = {"campaign_id": "CAMP-001", "accepted_head_seq": 17, "accepted_head_hash": "c" * 64}
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
        candidate_assurance_case_ref=other_cac_ref,
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
    res_cut = {"campaign_id": "CAMP-001", "accepted_head_seq": 17, "accepted_head_hash": "c" * 64}
    asgn_ref = {"kind": "challenger_assignment", "revision_digest": "asgn"}

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

    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(
        cac, res_skeptic, res_hunter
    )
    assert eligible is False
    assert "CHALLENGER_RESULTS_INVALIDATED_BY_CANDIDATE_CHANGE" in reasons


def test_only_one_challenger_blocks_stage_completion(candidate_and_context):
    cac, hcut = candidate_and_context
    res_cut = {"campaign_id": "CAMP-001", "accepted_head_seq": 17, "accepted_head_hash": "c" * 64}
    asgn_ref = {"kind": "challenger_assignment", "revision_digest": "asgn"}

    res_skeptic = ChallengerResult(
        challenger_result_id="res_sk",
        challenge_assignment_ref=asgn_ref,
        candidate_assurance_case_ref=cac.ref,
        result_input_history_cut=res_cut,
        status="NO_MATERIAL_COUNTEREVIDENCE",
    )

    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(
        cac, res_skeptic, None
    )
    assert eligible is False
    assert "MISSING_REQUIRED_CHALLENGER_ROLE" in reasons


def test_temporal_boundary_assignment_before_candidate(candidate_and_context):
    cac, hcut = candidate_and_context
    early_cut = {"campaign_id": "CAMP-001", "accepted_head_seq": 10, "accepted_head_hash": "e" * 64}
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


def test_legacy_commit_seq_cut_cannot_qualify_challenger_order(candidate_and_context):
    cac, _ = candidate_and_context
    legacy_cut = {"campaign_id": "CAMP-001", "commit_seq": 16, "commit_hash": "b" * 64}
    pol_ref = {"kind": "policy_revision", "revision_digest": "pol"}
    exec_ref = {"kind": "executor_spec", "revision_digest": "ex"}
    assignment = ChallengerAssignment(
        challenge_assignment_id="asgn_legacy",
        candidate_assurance_case_ref=cac.ref,
        challenger_type="FALSE_POSITIVE_SKEPTIC",
        challenge_scope="ALL",
        challenge_policy_ref=pol_ref,
        executor_profile_ref=exec_ref,
        assignment_input_history_cut=legacy_cut,
    )

    with pytest.raises(ValidationError, match="NONCANONICAL_HISTORY_CUT"):
        E5ChallengerOrchestrator.validate_assignment_precedes_candidate(cac, assignment)

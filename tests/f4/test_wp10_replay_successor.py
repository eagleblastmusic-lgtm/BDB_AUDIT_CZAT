"""Targeted unit and adversarial tests for WP-F4-10 / PR-F4-10.

Tests:
1. ReplayCapsule creation and deterministic object digest.
2. IndependentReplayRecord verification matching expected observables.
3. Replay verification on mismatch and harness failure.
4. Adversarial rule: Replayability does not imply independence (independence assessment required).
5. Successor campaign genesis: backward binding and empty history rejection.
6. Successor campaign branch selection: strict candidate set membership enforcement.
"""
import hashlib
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.history import (
    ReplayCapsule,
    IndependentReplayRecord,
    execute_replay_verification,
    SuccessorCampaignGenesis,
    SuccessorCampaignSelectionDecision,
    create_successor_campaign,
    select_successor_campaign,
)


def make_ref(kind: str, seed: str) -> dict:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }


def test_replay_capsule_creation():
    capsule = ReplayCapsule(
        finding_or_claim_revision_ref=make_ref("finding_claim_revision", "f1"),
        subject_baseline_ref=make_ref("source_generation", "gen_1"),
        environment_profile_ref=make_ref("environment_profile", "env_1"),
        dependency_set_ref=make_ref("dependency_set", "deps_1"),
        harness_ref=make_ref("harness_profile", "harn_1"),
        generator_profile_ref=make_ref("generator_profile", "gen_prof_1"),
        command_spec={"command": "run_test", "args": ["--fuzz", "payload.bin"]},
        expected_invariant_ref=make_ref("invariant_revision", "inv_no_panic"),
        expected_observable={"exit_code": 139, "signal": "SIGSEGV"},
        producer_ref=make_ref("actor_or_authority_ref", "lane_e1_c"),
        fixture_refs=[make_ref("fixture_ref", "payload.bin")],
        observer_requirements=["RECORD_STDERR", "RECORD_CORE"],
    )
    assert len(capsule.digest) == 64
    ref = capsule.as_ref()
    assert ref["kind"] == "replay_capsule"


def test_replay_verification_matching_observable():
    capsule = ReplayCapsule(
        finding_or_claim_revision_ref=make_ref("finding_claim_revision", "f1"),
        subject_baseline_ref=make_ref("source_generation", "gen_1"),
        environment_profile_ref=make_ref("environment_profile", "env_1"),
        dependency_set_ref=make_ref("dependency_set", "deps_1"),
        harness_ref=make_ref("harness_profile", "harn_1"),
        generator_profile_ref=make_ref("generator_profile", "gen_prof_1"),
        command_spec={"command": "run_test"},
        expected_invariant_ref=make_ref("invariant_revision", "inv_1"),
        expected_observable={"status": "CRASH", "error_code": 42},
        producer_ref=make_ref("actor_or_authority_ref", "lane_e1_c"),
    )

    observed = {"status": "CRASH", "error_code": 42}
    record = execute_replay_verification(
        capsule=capsule,
        replay_executor_ref=make_ref("executor_profile", "independent_runner"),
        actual_subject_ref=make_ref("source_generation", "gen_1"),
        actual_environment_ref=make_ref("environment_profile", "env_isolated"),
        actual_harness_ref=make_ref("harness_profile", "harn_v2"),
        actual_dependencies_ref=make_ref("dependency_set", "deps_1"),
        independence_assessment_ref=make_ref("dependency_independence_assessment", "ind_1"),
        observed_result=observed,
    )

    assert record.status == "REPRODUCED"
    assert record.match_expected is True
    assert len(record.digest) == 64


def test_replay_verification_mismatch_and_harness_failure():
    capsule = ReplayCapsule(
        finding_or_claim_revision_ref=make_ref("finding_claim_revision", "f1"),
        subject_baseline_ref=make_ref("source_generation", "gen_1"),
        environment_profile_ref=make_ref("environment_profile", "env_1"),
        dependency_set_ref=make_ref("dependency_set", "deps_1"),
        harness_ref=make_ref("harness_profile", "harn_1"),
        generator_profile_ref=make_ref("generator_profile", "gen_prof_1"),
        command_spec={"command": "run_test"},
        expected_invariant_ref=make_ref("invariant_revision", "inv_1"),
        expected_observable={"status": "CRASH"},
        producer_ref=make_ref("actor_or_authority_ref", "lane_e1_c"),
    )

    # 1. Mismatch
    mismatch_record = execute_replay_verification(
        capsule=capsule,
        replay_executor_ref=make_ref("executor_profile", "runner_2"),
        actual_subject_ref=make_ref("source_generation", "gen_1"),
        actual_environment_ref=make_ref("environment_profile", "env_1"),
        actual_harness_ref=make_ref("harness_profile", "harn_1"),
        actual_dependencies_ref=make_ref("dependency_set", "deps_1"),
        independence_assessment_ref=make_ref("dependency_independence_assessment", "ind_1"),
        observed_result={"status": "OK"},  # Expected CRASH
    )
    assert mismatch_record.status == "NOT_REPRODUCED"
    assert mismatch_record.match_expected is False

    # 2. Harness Failure
    failure_record = execute_replay_verification(
        capsule=capsule,
        replay_executor_ref=make_ref("executor_profile", "runner_3"),
        actual_subject_ref=make_ref("source_generation", "gen_1"),
        actual_environment_ref=make_ref("environment_profile", "env_1"),
        actual_harness_ref=make_ref("harness_profile", "harn_1"),
        actual_dependencies_ref=make_ref("dependency_set", "deps_1"),
        independence_assessment_ref=make_ref("dependency_independence_assessment", "ind_1"),
        observed_result={},
        harness_succeeded=False,
    )
    assert failure_record.status == "HARNESS_FAILURE"
    assert failure_record.match_expected is False


def test_adversarial_replay_without_independence_assessment():
    with pytest.raises(ValidationError, match="INDEPENDENCE_ASSESSMENT_REQUIRED"):
        IndependentReplayRecord(
            repro_capsule_ref=make_ref("replay_capsule", "cap_1"),
            replay_executor_ref=make_ref("executor_profile", "exec_1"),
            actual_subject_ref=make_ref("source_generation", "gen_1"),
            actual_environment_ref=make_ref("environment_profile", "env_1"),
            actual_harness_ref=make_ref("harness_profile", "harn_1"),
            actual_dependencies_ref=make_ref("dependency_set", "deps_1"),
            dependency_independence_assessment_ref=None,  # Forbidden: cannot claim replay without independence assessment!
            status="REPRODUCED",
            match_expected=True,
        )


def test_successor_campaign_genesis():
    pred_campaign = make_ref("campaign_genesis", "camp_001")
    pred_conclusion = make_ref("campaign_conclusion", "concl_001")
    trigger = make_ref("source_generation", "gen_2_patched")
    src_gen_2 = make_ref("source_generation", "gen_2")
    cut = {"prior_commit_digest": "a" * 64, "head_ordinal": 12}
    policy = make_ref("policy_revision", "gov_pol_2")
    freshness = make_ref("policy_revision", "freshness_pol_1")

    # Happy path: non-empty history
    successor = create_successor_campaign(
        predecessor_campaign_ref=pred_campaign,
        predecessor_conclusion_ref=pred_conclusion,
        successor_trigger_ref=trigger,
        source_generation_ref=src_gen_2,
        successor_input_history_cut=cut,
        challenge_freshness_policy_ref=freshness,
        governing_policy_ref=policy,
    )
    assert len(successor.digest) == 64
    assert successor.as_object().kind == "successor_campaign_genesis"

    # Adversarial test: attempting to pass EMPTY_HISTORY to successor campaign
    with pytest.raises(ValidationError, match="SUCCESSOR_REQUIRES_NON_EMPTY_HISTORY"):
        create_successor_campaign(
            predecessor_campaign_ref=pred_campaign,
            predecessor_conclusion_ref=pred_conclusion,
            successor_trigger_ref=trigger,
            source_generation_ref=src_gen_2,
            successor_input_history_cut={"tag": "EMPTY_HISTORY"},
            challenge_freshness_policy_ref=freshness,
            governing_policy_ref=policy,
        )


def test_successor_campaign_selection_decision():
    pred_conclusion = make_ref("campaign_conclusion", "concl_001")
    branch_a = make_ref("successor_campaign_genesis", "branch_a")
    branch_b = make_ref("successor_campaign_genesis", "branch_b")
    branch_rogue = make_ref("successor_campaign_genesis", "branch_rogue_unrelated")
    basis = [make_ref("arbitration_record", "arb_1")]
    pol = make_ref("policy_revision", "pol_branch")
    cut = {"head_ordinal": 15}

    # Happy path: selecting branch_a which is in [branch_a, branch_b]
    decision = select_successor_campaign(
        predecessor_conclusion_ref=pred_conclusion,
        candidate_campaign_refs=[branch_a, branch_b],
        selected_campaign_ref=branch_a,
        resolution_basis_refs=basis,
        governing_policy_ref=pol,
        input_history_cut=cut,
    )
    assert len(decision.digest) == 64
    assert decision.selected_successor_campaign_ref["revision_digest"] == branch_a["revision_digest"]

    # Adversarial test: selecting a branch not present in candidates must fail closed
    with pytest.raises(ValidationError, match="SELECTED_SUCCESSOR_NOT_IN_CANDIDATES"):
        select_successor_campaign(
            predecessor_conclusion_ref=pred_conclusion,
            candidate_campaign_refs=[branch_a, branch_b],
            selected_campaign_ref=branch_rogue,
            resolution_basis_refs=basis,
            governing_policy_ref=pol,
            input_history_cut=cut,
        )

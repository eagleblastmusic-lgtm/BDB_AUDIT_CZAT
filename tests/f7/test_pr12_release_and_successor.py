"""Targeted tests for Release Lifecycle & Successor Assurance (PR-E5-12 / M45A)."""
import pytest
from jsonschema import Draft202012Validator

from bdb_audit.assurance.conclusion import CampaignConclusion, FinalAssuranceCase
from bdb_audit.assurance.release import (
    ReleaseQualification,
    SuccessorCampaignGenesis,
    SuccessorCampaignSelectionDecision,
    ReleaseLifecycleManager,
)
from bdb_audit.core.errors import ValidationError
from bdb_audit.schemas.foundation import executable_schema
from bdb_audit.stop.models import StopEvaluation


def _ref(kind: str, digest_suffix: str, ref_class: str = "CONTENT_OR_PRIOR") -> dict:
    dig = (digest_suffix * 64)[:64]
    return {
        "kind": kind,
        "revision_digest": dig,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
    }


@pytest.fixture
def finalization_fixtures():
    hcut_stop = {"campaign_id": "CAMP-001", "commit_seq": 20, "commit_hash": "a" * 64}
    hcut_concl = {"campaign_id": "CAMP-001", "commit_seq": 21, "commit_hash": "b" * 64}
    hcut_fac = {"campaign_id": "CAMP-001", "commit_seq": 22, "commit_hash": "c" * 64}
    hcut_rel = {"campaign_id": "CAMP-001", "commit_seq": 23, "commit_hash": "d" * 64}

    stop_input_ref = _ref("stop_input", "si_01")
    stop_eval = StopEvaluation(
        stop_input_ref=stop_input_ref,
        continuation_decision="PASS",
        assurance_level="ADEQUATE_FOR_DECLARED_SCOPE",
        release_readiness="READY",
        reason_codes=("ALL_SATISFIED",),
    )

    camp_ref = _ref("campaign_genesis", "camp_01", "PRIOR_ACCEPTED_ONLY")
    src_ref = _ref("source_generation", "src_01", "PRIOR_ACCEPTED_ONLY")
    cac_ref = _ref("candidate_assurance_case", "cac_01", "PRIOR_ACCEPTED_ONLY")
    pub_stmt = _ref("public_conclusion_statement", "pub_stmt", "PRIOR_ACCEPTED_ONLY")
    rel_pol = _ref("policy_revision", "rel_pol", "HISTORY_CONTEXT_BINDING")

    conclusion = CampaignConclusion(
        campaign_conclusion_id="concl_01",
        campaign_ref=camp_ref,
        source_generation_ref=src_ref,
        stop_evaluation_ref=dict(stop_eval.ref),
        termination_state="COMPLETED",
        assurance_level="ADEQUATE_FOR_DECLARED_SCOPE",
        bounded_conclusion_statement="All objectives verified",
        conclusion_command_input_history_cut=hcut_concl,
        candidate_assurance_case_ref=cac_ref,
    )

    fac = FinalAssuranceCase(
        final_assurance_case_id="fac_01",
        campaign_conclusion_ref=dict(conclusion.ref),
        stop_evaluation_ref=dict(stop_eval.ref),
        public_conclusion_statement_ref=pub_stmt,
        final_case_input_history_cut=hcut_fac,
        candidate_assurance_case_ref=cac_ref,
    )

    return {
        "stop_eval": stop_eval,
        "conclusion": conclusion,
        "fac": fac,
        "src_ref": src_ref,
        "camp_ref": camp_ref,
        "rel_pol": rel_pol,
        "hcut_stop": hcut_stop,
        "hcut_rel": hcut_rel,
    }


def test_schemas_for_finalization_and_release(finalization_fixtures):
    ctx = finalization_fixtures
    Draft202012Validator(executable_schema("campaign_conclusion")).validate(ctx["conclusion"].body())
    Draft202012Validator(executable_schema("final_assurance_case")).validate(ctx["fac"].body())


def test_release_basis_stop_axis_materialization(finalization_fixtures):
    ctx = finalization_fixtures
    rq = ReleaseLifecycleManager.evaluate_release_qualification(
        qualification_id="rq_01",
        conclusion=ctx["conclusion"],
        final_case=ctx["fac"],
        stop_eval=ctx["stop_eval"],
        source_generation_ref=ctx["src_ref"],
        release_policy_ref=ctx["rel_pol"],
        release_assessment_basis_cut=ctx["hcut_stop"],
        qualification_command_cut=ctx["hcut_rel"],
        assessment_basis="STOP_AXIS_MATERIALIZATION",
        has_release_drift=False,
    )
    assert rq.result == "READY"
    assert rq.assessment_basis == "STOP_AXIS_MATERIALIZATION"
    assert rq.previous_release_qualification_ref is None
    Draft202012Validator(executable_schema("release_qualification")).validate(rq.body())

    # If drift occurred, STOP_AXIS_MATERIALIZATION fails closed
    with pytest.raises(ValidationError, match="DRIFT_DETECTED_MATERIALIZATION_INVALID"):
        ReleaseLifecycleManager.evaluate_release_qualification(
            qualification_id="rq_bad",
            conclusion=ctx["conclusion"],
            final_case=ctx["fac"],
            stop_eval=ctx["stop_eval"],
            source_generation_ref=ctx["src_ref"],
            release_policy_ref=ctx["rel_pol"],
            release_assessment_basis_cut=ctx["hcut_stop"],
            qualification_command_cut=ctx["hcut_rel"],
            assessment_basis="STOP_AXIS_MATERIALIZATION",
            has_release_drift=True,  # Drift!
        )


def test_release_basis_fresh_and_reassessment(finalization_fixtures):
    ctx = finalization_fixtures

    # 1. First qualification after release drift: FRESH_RELEASE_QUALIFICATION
    rq_fresh = ReleaseLifecycleManager.evaluate_release_qualification(
        qualification_id="rq_fresh",
        conclusion=ctx["conclusion"],
        final_case=ctx["fac"],
        stop_eval=ctx["stop_eval"],
        source_generation_ref=ctx["src_ref"],
        release_policy_ref=ctx["rel_pol"],
        release_assessment_basis_cut=ctx["hcut_stop"],
        qualification_command_cut=ctx["hcut_rel"],
        assessment_basis="FRESH_RELEASE_QUALIFICATION",
        has_release_drift=True,
    )
    assert rq_fresh.assessment_basis == "FRESH_RELEASE_QUALIFICATION"
    assert rq_fresh.previous_release_qualification_ref is None

    # 2. Subsequent qualification: RELEASE_REASSESSMENT requires previous_release_qualification_ref
    reassess_input = _ref("release_input", "reassess_input", "PRIOR_ACCEPTED_ONLY")
    rq_reassess = ReleaseLifecycleManager.evaluate_release_qualification(
        qualification_id="rq_reassess",
        conclusion=ctx["conclusion"],
        final_case=ctx["fac"],
        stop_eval=ctx["stop_eval"],
        source_generation_ref=ctx["src_ref"],
        release_policy_ref=ctx["rel_pol"],
        release_assessment_basis_cut=ctx["hcut_stop"],
        qualification_command_cut=ctx["hcut_rel"],
        assessment_basis="RELEASE_REASSESSMENT",
        previous_qualification_ref=dict(rq_fresh.ref),
        reassessment_input_refs=[reassess_input],
    )
    assert rq_reassess.assessment_basis == "RELEASE_REASSESSMENT"
    assert rq_reassess.previous_release_qualification_ref is not None


def test_audit_basis_invalidation_requires_successor_campaign(finalization_fixtures):
    """Audit basis invalidation CANNOT be treated as release-only drift."""
    ctx = finalization_fixtures
    with pytest.raises(ValidationError, match="AUDIT_BASIS_INVALIDATED_REQUIRES_SUCCESSOR"):
        ReleaseLifecycleManager.evaluate_release_qualification(
            qualification_id="rq_invalid",
            conclusion=ctx["conclusion"],
            final_case=ctx["fac"],
            stop_eval=ctx["stop_eval"],
            source_generation_ref=ctx["src_ref"],
            release_policy_ref=ctx["rel_pol"],
            release_assessment_basis_cut=ctx["hcut_stop"],
            qualification_command_cut=ctx["hcut_rel"],
            assessment_basis="RELEASE_REASSESSMENT",
            audit_basis_invalidated=True,  # Invalidates audit basis!
        )


def test_successor_campaign_genesis_and_competing_branches(finalization_fixtures):
    ctx = finalization_fixtures
    trigger_ref = _ref("evidence_invalidation", "inv_decisive", "CONTENT_OR_PRIOR")
    pol_ref = _ref("policy_revision", "pol_succ", "HISTORY_CONTEXT_BINDING")
    fresh_pol = _ref("policy_revision", "fresh_pol", "HISTORY_CONTEXT_BINDING")
    spec_ref = _ref("spec_revision", "spec_succ", "HISTORY_CONTEXT_BINDING")

    # Successor branch 1
    succ1 = SuccessorCampaignGenesis(
        campaign_id="CAMP-002-branchA",
        predecessor_campaign_ref=ctx["camp_ref"],
        predecessor_conclusion_ref=dict(ctx["conclusion"].ref),
        successor_trigger_ref=trigger_ref,
        source_generation_ref=ctx["src_ref"],
        successor_input_history_cut={"commit_seq": 25},
        governing_policy_ref=pol_ref,
        challenge_freshness_policy_ref=fresh_pol,
        governing_spec_refs=(spec_ref,),
    )
    Draft202012Validator(executable_schema("successor_campaign_genesis")).validate(succ1.body())

    # Successor branch 2 (competing)
    succ2 = SuccessorCampaignGenesis(
        campaign_id="CAMP-002-branchB",
        predecessor_campaign_ref=ctx["camp_ref"],
        predecessor_conclusion_ref=dict(ctx["conclusion"].ref),
        successor_trigger_ref=trigger_ref,
        source_generation_ref=ctx["src_ref"],
        successor_input_history_cut={"commit_seq": 26},
        governing_policy_ref=pol_ref,
        challenge_freshness_policy_ref=fresh_pol,
        governing_spec_refs=(spec_ref,),
    )

    # 1. Two competing branches without selection decision -> fail closed ASSURANCE_SUCCESSOR_CONFLICT
    with pytest.raises(ValidationError, match="ASSURANCE_SUCCESSOR_CONFLICT"):
        ReleaseLifecycleManager.resolve_successor_branches(
            predecessor_conclusion_ref=dict(ctx["conclusion"].ref),
            candidate_successor_campaigns=[succ1, succ2],
            selection_decision=None,
        )

    # 2. With valid SuccessorCampaignSelectionDecision -> succeeds
    basis_ref = _ref("approval_decision", "appr_branchA", "CONTENT_OR_PRIOR")
    selection = SuccessorCampaignSelectionDecision(
        selection_decision_id="sel_01",
        predecessor_conclusion_ref=dict(ctx["conclusion"].ref),
        candidate_successor_campaign_refs=(dict(succ1.ref), dict(succ2.ref)),
        selected_successor_campaign_ref=dict(succ1.ref),
        resolution_basis_refs=(basis_ref,),
        governing_policy_ref=pol_ref,
        input_history_cut={"commit_seq": 27},
    )
    Draft202012Validator(executable_schema("successor_campaign_selection_decision")).validate(selection.body())

    chosen = ReleaseLifecycleManager.resolve_successor_branches(
        predecessor_conclusion_ref=dict(ctx["conclusion"].ref),
        candidate_successor_campaigns=[succ1, succ2],
        selection_decision=selection,
    )
    assert chosen.campaign_id == "CAMP-002-branchA"

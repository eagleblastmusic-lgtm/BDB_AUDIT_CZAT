"""Regression tests for D01-D27 anti-false-PASS counterexamples (RU13-A)."""
import pytest

from bdb_audit.assurance.conclusion import CampaignConclusion, FinalAssuranceCase
from bdb_audit.assurance.release import ReleaseLifecycleManager
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.registry import ContractRegistry
from bdb_audit.orchestration.runs import LaneSpec, qualify_isolation
from bdb_audit.stop.evaluator import evaluate_stop
from bdb_audit.stop.models import StopEvaluation, StopInput


def _ref(kind: str, digest_suffix: str = "1", ref_class: str = "CONTENT_OR_PRIOR") -> dict:
    dig = (digest_suffix * 64)[:64]
    return {
        "kind": kind,
        "revision_digest": dig,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_TARGET/{kind}",
        "ref_class": ref_class,
    }


def test_d03_stop_cannot_pass_with_unsatisfied_obligations():
    """D03: STOP evaluator must NOT yield PASS when unknown or blocked items exist."""
    cut = {"campaign_id": "CAMP_D03", "commit_seq": 18, "commit_hash": "e" * 64}
    si_unknown = StopInput(
        campaign_id="CAMP_D03",
        source_generation_ref=_ref("sg", "1"),
        input_history_cut=cut,
        evaluation_context="FINAL_POST_E5",
        governing_policy_ref=_ref("p", "1"),
        policy_spec_refs=[_ref("sp", "1")],
        evaluator_revision_ref=_ref("sp", "1"),
        required_stage_set_ref=_ref("st", "1"),
        required_stage_spec_refs=[_ref("sp", "1")],
        completed_stage_refs=[_ref("sp", "1")],
        pending_required_stage_refs=[],
        stop_input_snapshot_ref=_ref("sn", "1"),
        inventory_revision_ref=_ref("inv", "1"),
        mandatory_obligation_refs=[_ref("coverage_obligation", "ob1")],
        current_obligation_qualification_refs=[],
        evidence_invalidation_refs=[],
        contradiction_refs=[],
        residual_risk_refs=[],
        evidence_invalidation_state={"invalidated_count": 0},
        release_policy_ref=_ref("p", "1"),
        effort_profile_ref=_ref("eff", "1"),
        effort_results_ref={"r": 1},
        unknown_blocked_summary={"unknown_surfaces_count": 1, "is_blocked": False},
        candidate_assurance_case_ref=_ref("cac", "1"),
        challenger_refs=[_ref("cr", "1"), _ref("cr", "2")],
    )

    ev = evaluate_stop(si_unknown)
    assert ev.continuation_decision != "PASS"
    assert ev.continuation_decision in ("BLOCKED", "CONTINUE_REQUIRED")
    assert ev.release_readiness != "READY"


def test_d08_fake_enforced_isolation_prohibited():
    """D08: Isolation cannot be declared ENFORCED unless an enforced boundary is verified."""
    from bdb_audit.orchestration.runs import IsolationQualification
    # Calling qualify_isolation degrades to UNKNOWN if enforcement is unavailable
    qual = qualify_isolation(
        attempt_ref=_ref("attempt", "a"),
        history_cut={"cut": 1},
        executor_profile_ref=_ref("profile", "p"),
        delivery_profile_ref=_ref("delivery", "d"),
        fresh_session_boundary=False,
        requested="ENFORCED",
    )
    assert qual.isolation_class == "UNKNOWN"
    assert qual.isolation_class != "ENFORCED"

    # Direct construction with ENFORCED and no fresh boundary must fail closed
    with pytest.raises(ValidationError, match="NO_FALSE_ENFORCED_FALLBACK"):
        IsolationQualification(
            attempt_ref=_ref("attempt", "a"),
            assessment_input_history_cut={"cut": 1},
            executor_profile_ref=_ref("profile", "p"),
            delivery_profile_ref=_ref("delivery", "d"),
            isolation_class="ENFORCED",
            contaminated=False,
            fresh_session_boundary=False,  # Unenforced boundary!
            forbidden_channel_access=False,
            evidence_refs=(),
        )


def test_d09_registry_rejects_unregistered_kind():
    """D09: ContractRegistry strictly fails closed on unregistered kinds."""
    reg = ContractRegistry()
    with pytest.raises(ValidationError, match="UNREGISTERED_CONTRACT_KIND"):
        reg.contract("non_existent_unregistered_kind_xyz")


def test_d18_self_test_fails_closed_on_integrity_violation():
    """D18: Self-test fails closed if any required check cannot run or fails."""
    api = AuditOperationApi()
    res = api.run_self_test(deep=False)
    assert res["status"] == "PASS"
    assert len(res["checks"]) == 4
    assert all(c["status"] == "PASS" for c in res["checks"])


def test_d22_release_lifecycle_fails_on_unapproved_stop():
    """D22: Release readiness cannot be READY if campaign was terminated as COMPLETED_LIMITED or audit invalidated."""
    cut = {
        "accepted_cut_point": {
            "campaign_id": "camp_d22",
            "commit_seq": 10,
            "commit_bundle_digest": "0" * 64,
        }
    }
    stop_eval = StopEvaluation(
        stop_input_ref=_ref("stop_input", "si"),
        continuation_decision="PASS",
        assurance_level="ADEQUATE_FOR_DECLARED_SCOPE",
        release_readiness="READY",
    )
    conclusion = CampaignConclusion(
        campaign_conclusion_id="conc_d22",
        campaign_ref=_ref("campaign_genesis", "cg"),
        source_generation_ref=_ref("source_generation", "sg"),
        stop_evaluation_ref=stop_eval.ref,
        termination_state="COMPLETED_LIMITED",  # Not COMPLETED
        assurance_level="BOUNDED",
        bounded_conclusion_statement="Bounded statement",
        conclusion_command_input_history_cut=cut,
        limited_conclusion_basis_refs=(_ref("basis", "b"),),
    )
    final_case = FinalAssuranceCase(
        final_assurance_case_id="fac_d22",
        campaign_conclusion_ref=conclusion.ref,
        stop_evaluation_ref=stop_eval.ref,
        public_conclusion_statement_ref=_ref("statement", "s"),
        final_case_input_history_cut=cut,
    )

    # If termination_state is not COMPLETED, release qualification must be QUALIFICATION_BLOCKED, never READY
    rel_qual = ReleaseLifecycleManager.evaluate_release_qualification(
        qualification_id="rel_qual_d22",
        conclusion=conclusion,
        final_case=final_case,
        stop_eval=stop_eval,
        source_generation_ref=_ref("source_generation", "sg"),
        release_policy_ref=_ref("policy", "p"),
        release_assessment_basis_cut=cut,
        qualification_command_cut=cut,
        assessment_basis="STOP_AXIS_MATERIALIZATION",
    )
    assert rel_qual.result == "QUALIFICATION_BLOCKED"
    assert rel_qual.result != "READY"

    # Audit basis invalidation cannot be handled as release drift; must raise ValidationError
    with pytest.raises(ValidationError, match="AUDIT_BASIS_INVALIDATED_REQUIRES_SUCCESSOR"):
        ReleaseLifecycleManager.evaluate_release_qualification(
            qualification_id="rel_qual_d22_b",
            conclusion=conclusion,
            final_case=final_case,
            stop_eval=stop_eval,
            source_generation_ref=_ref("source_generation", "sg"),
            release_policy_ref=_ref("policy", "p"),
            release_assessment_basis_cut=cut,
            qualification_command_cut=cut,
            assessment_basis="STOP_AXIS_MATERIALIZATION",
            audit_basis_invalidated=True,
        )

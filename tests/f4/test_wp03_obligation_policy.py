"""Targeted tests for Work Package 3 (PR-F4-03): Obligation Policy Library & Strict Qualification Semantics."""
import hashlib
import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id, deterministic_id
from bdb_audit.coverage import (
    CoverageObligationKey,
    CoverageObligation,
    CoverageObligationQualification,
    ObligationApplicabilityDecision,
    ApprovalDecision,
    MaterialityAssessment,
    ObligationPolicyLibrary,
    evaluate_coverage_qualification,
    derive_presentation_depth,
    compute_breadth_summary,
)


def make_ref(kind: str, seed: str, logical_id: str | None = None) -> dict:
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": "CONTENT_OR_PRIOR",
        **({"logical_id": logical_id} if logical_id else {}),
    }


def test_obligation_policy_library_generation():
    """Policy library generates domain obligations with stable keys and registered contracts."""
    lib = ObligationPolicyLibrary()
    surf_ref = make_ref("surface_record", "surf_route_1", logical_id="surf_route_1")
    inv_ref = make_ref("invariant_revision", "inv_auth_1")
    mat_ref = make_ref("materiality_assessment", "mat_auth_1")
    src_ref = make_ref("source_identity", "src_v1")
    env_ref = make_ref("environment_profile", "env_linux")
    pol_ref = make_ref("policy_revision", "pol_m16")
    cut = {"tag": "CUT_001", "commit_seq": 10}

    obs = lib.generate_obligations(
        surface_ref=surf_ref,
        surface_category="HTTP_ROUTE",
        invariant_ref=inv_ref,
        invariant_logical_id="inv_auth_1",
        materiality_assessment_ref=mat_ref,
        source_generation_ref=src_ref,
        history_cut=cut,
        environment_profile_ref=env_ref,
        governing_policy_ref=pol_ref,
    )

    # HTTP_ROUTE defines 3 standard rules: STATIC_SCHEMA, FUZZ_INPUT, AUTHORIZATION_BYPASS
    assert len(obs) == 3
    scenarios = [o.scenario_class for o in obs]
    assert "STATIC_SCHEMA" in scenarios
    assert "FUZZ_INPUT" in scenarios
    assert "AUTHORIZATION_BYPASS" in scenarios

    for o in obs:
        assert o.as_object().kind == "coverage_obligation"
        assert len(o.digest) == 64
        # Verify deterministic ID format
        assert o.obligation_id.startswith("coverage_obligation_")


def test_hard_rule_no_auto_na():
    """Hard rule: NO auto-N/A without accepted ObligationApplicabilityDecision."""
    ob_id = new_id("coverage_obligation")
    ob = CoverageObligation(
        obligation_id=ob_id,
        obligation_revision="1",
        obligation_input_history_cut={"tag": "CUT_001"},
        source_generation_ref=make_ref("source_identity", "src_1"),
        target_scope_or_surface_ref=make_ref("surface_record", "s1"),
        invariant_revision_ref=make_ref("invariant_revision", "i1"),
        scenario_class="FUZZ_INPUT",
        environment_profile_ref=make_ref("environment_profile", "e1"),
        materiality_assessment_ref=make_ref("materiality_assessment", "m1"),
        required_oracle_independence_predicate_ref=make_ref("predicate", "p1"),
        acceptance_predicate_ref=make_ref("predicate", "p2"),
        applicability_predicate_ref=make_ref("predicate", "p3"),
        policy_obligation_key="key_1",
        governing_policy_ref=make_ref("policy_revision", "pol_1"),
        origin_ref=make_ref("surface_record", "s1"),
    )

    app_dec_ref = make_ref("obligation_applicability_decision", "dec_na_1")
    qual = CoverageObligationQualification(
        qualification_id=new_id("coverage_obligation_qualification"),
        obligation_revision_ref=ob.as_object().as_ref(),
        input_history_cut={"tag": "CUT_001"},
        qualification_status="QUALIFIED",
        applicability_decision_ref=app_dec_ref,
    )

    # Missing applicability decision body when ref is claimed -> AUTO_NA_FORBIDDEN
    with pytest.raises(ValidationError, match="AUTO_NA_FORBIDDEN"):
        evaluate_coverage_qualification(ob, qual, applicability_decision=None)

    # Mismatched result (e.g. decision is APPLICABLE, not NOT_APPLICABLE) -> APPLICABILITY_RESULT_MISMATCH
    dec_applicable = ObligationApplicabilityDecision(
        applicability_decision_id=new_id("obligation_applicability_decision"),
        obligation_revision_ref=ob.as_object().as_ref(),
        assessment_input_history_cut={"tag": "CUT_001"},
        applicability_policy_ref=make_ref("policy_revision", "pol_1"),
        scope="s1",
        result="APPLICABLE",
    )
    with pytest.raises(ValidationError, match="APPLICABILITY_RESULT_MISMATCH"):
        evaluate_coverage_qualification(ob, qual, applicability_decision=dec_applicable)

    # Proper NOT_APPLICABLE decision -> succeeds
    dec_not_applicable = ObligationApplicabilityDecision(
        applicability_decision_id=new_id("obligation_applicability_decision"),
        obligation_revision_ref=ob.as_object().as_ref(),
        assessment_input_history_cut={"tag": "CUT_001"},
        applicability_policy_ref=make_ref("policy_revision", "pol_1"),
        scope="s1",
        result="NOT_APPLICABLE",
    )
    res = evaluate_coverage_qualification(ob, qual, applicability_decision=dec_not_applicable)
    assert res["is_not_applicable"] is True
    assert res["satisfies_completion"] is False


def test_hard_rule_no_auto_waiver_and_waiver_does_not_satisfy_completion():
    """Hard rule: NO auto-waiver without accepted ApprovalDecision; waiver never satisfies completion."""
    ob_id = new_id("coverage_obligation")
    ob = CoverageObligation(
        obligation_id=ob_id,
        obligation_revision="1",
        obligation_input_history_cut={"tag": "CUT_001"},
        source_generation_ref=make_ref("source_identity", "src_1"),
        target_scope_or_surface_ref=make_ref("surface_record", "s1"),
        invariant_revision_ref=make_ref("invariant_revision", "i1"),
        scenario_class="CONCURRENCY_TEST",
        environment_profile_ref=make_ref("environment_profile", "e1"),
        materiality_assessment_ref=make_ref("materiality_assessment", "m1"),
        required_oracle_independence_predicate_ref=make_ref("predicate", "p1"),
        acceptance_predicate_ref=make_ref("predicate", "p2"),
        applicability_predicate_ref=make_ref("predicate", "p3"),
        policy_obligation_key="key_conc",
        governing_policy_ref=make_ref("policy_revision", "pol_1"),
        origin_ref=make_ref("surface_record", "s1"),
    )

    waiver_ref = make_ref("approval_decision", "app_waiver_1")
    qual = CoverageObligationQualification(
        qualification_id=new_id("coverage_obligation_qualification"),
        obligation_revision_ref=ob.as_object().as_ref(),
        input_history_cut={"tag": "CUT_001"},
        qualification_status="QUALIFIED",
        waiver_decision_ref=waiver_ref,
    )

    # Claiming waiver without accepted decision -> AUTO_WAIVER_FORBIDDEN
    with pytest.raises(ValidationError, match="AUTO_WAIVER_FORBIDDEN"):
        evaluate_coverage_qualification(ob, qual, waiver_decision=None)

    # Wrong decision type or rejected waiver -> WAIVER_DECISION_MISMATCH
    bad_waiver = ApprovalDecision(
        decision_id=new_id("approval_decision"),
        decision_type="GENERIC_APPROVAL",
        decision="APPROVED",
        actor_ref=make_ref("actor", "auditor_1"),
        actor_authority_ref=make_ref("authority", "lead"),
        input_history_cut={"tag": "CUT_001"},
        related_refs=[ob.as_object().as_ref()],
    )
    with pytest.raises(ValidationError, match="WAIVER_DECISION_MISMATCH"):
        evaluate_coverage_qualification(ob, qual, waiver_decision=bad_waiver)

    # Proper waiver: approved COVERAGE_OBLIGATION_WAIVER
    valid_waiver = ApprovalDecision(
        decision_id=new_id("approval_decision"),
        decision_type="COVERAGE_OBLIGATION_WAIVER",
        decision="APPROVED",
        actor_ref=make_ref("actor", "auditor_1"),
        actor_authority_ref=make_ref("authority", "lead"),
        input_history_cut={"tag": "CUT_001"},
        related_refs=[ob.as_object().as_ref()],
    )
    res = evaluate_coverage_qualification(ob, qual, waiver_decision=valid_waiver)
    assert res["is_waived"] is True
    # Critical: waiver does NOT satisfy completion
    assert res["satisfies_completion"] is False


def test_substantive_outcome_violation_confirmed():
    """VIOLATION_CONFIRMED qualifies the investigation obligation but does not count as NO_VIOLATION_OBSERVED."""
    ob_id = new_id("coverage_obligation")
    ob = CoverageObligation(
        obligation_id=ob_id,
        obligation_revision="1",
        obligation_input_history_cut={"tag": "CUT_001"},
        source_generation_ref=make_ref("source_identity", "src_1"),
        target_scope_or_surface_ref=make_ref("surface_record", "s1"),
        invariant_revision_ref=make_ref("invariant_revision", "i1"),
        scenario_class="SECURITY_PROBE",
        environment_profile_ref=make_ref("environment_profile", "e1"),
        materiality_assessment_ref=make_ref("materiality_assessment", "m1"),
        required_oracle_independence_predicate_ref=make_ref("predicate", "p1"),
        acceptance_predicate_ref=make_ref("predicate", "p2"),
        applicability_predicate_ref=make_ref("predicate", "p3"),
        policy_obligation_key="key_sec",
        governing_policy_ref=make_ref("policy_revision", "pol_1"),
        origin_ref=make_ref("surface_record", "s1"),
    )

    qual = CoverageObligationQualification(
        qualification_id=new_id("coverage_obligation_qualification"),
        obligation_revision_ref=ob.as_object().as_ref(),
        input_history_cut={"tag": "CUT_001"},
        qualification_status="QUALIFIED",
        substantive_outcome="VIOLATION_CONFIRMED",
    )

    res = evaluate_coverage_qualification(ob, qual)
    assert res["effective_status"] == "QUALIFIED"
    assert res["substantive_outcome"] == "VIOLATION_CONFIRMED"
    # Does NOT satisfy clean completion
    assert res["satisfies_completion"] is False


def test_invalidation_propagation_degrades_qualification():
    """Invalidated evidence degrades qualification from QUALIFIED to STALE and blocks completion."""
    ob_id = new_id("coverage_obligation")
    ob = CoverageObligation(
        obligation_id=ob_id,
        obligation_revision="1",
        obligation_input_history_cut={"tag": "CUT_001"},
        source_generation_ref=make_ref("source_identity", "src_1"),
        target_scope_or_surface_ref=make_ref("surface_record", "s1"),
        invariant_revision_ref=make_ref("invariant_revision", "i1"),
        scenario_class="DYNAMIC_TEST",
        environment_profile_ref=make_ref("environment_profile", "e1"),
        materiality_assessment_ref=make_ref("materiality_assessment", "m1"),
        required_oracle_independence_predicate_ref=make_ref("predicate", "p1"),
        acceptance_predicate_ref=make_ref("predicate", "p2"),
        applicability_predicate_ref=make_ref("predicate", "p3"),
        policy_obligation_key="key_dyn",
        governing_policy_ref=make_ref("policy_revision", "pol_1"),
        origin_ref=make_ref("surface_record", "s1"),
    )

    ev_ref = make_ref("evidence_qualification_assessment", "ev_1")
    qual = CoverageObligationQualification(
        qualification_id=new_id("coverage_obligation_qualification"),
        obligation_revision_ref=ob.as_object().as_ref(),
        input_history_cut={"tag": "CUT_001"},
        qualification_status="QUALIFIED",
        substantive_outcome="NO_VIOLATION_OBSERVED",
        evidence_qualification_refs=[ev_ref],
    )

    # Without invalidation: QUALIFIED and satisfies completion
    res_clean = evaluate_coverage_qualification(ob, qual)
    assert res_clean["effective_status"] == "QUALIFIED"
    assert res_clean["satisfies_completion"] is True

    # With evidence invalidated: degraded to STALE
    res_invalid = evaluate_coverage_qualification(
        ob, qual, invalidated_evidence_digests={ev_ref["revision_digest"]}
    )
    assert res_invalid["effective_status"] == "STALE"
    assert res_invalid["degraded_by_invalidation"] is True
    assert res_invalid["satisfies_completion"] is False


def test_breadth_summary_computation():
    """Breadth summary accurately preserves all denominator counts and depth distribution."""
    inv_ref = make_ref("inventory_revision", "inv_1")
    evals = [
        {"effective_status": "QUALIFIED", "substantive_outcome": "NO_VIOLATION_OBSERVED", "satisfies_completion": True, "target_ref": "surf_1"},
        {"effective_status": "QUALIFIED", "substantive_outcome": "VIOLATION_CONFIRMED", "satisfies_completion": False, "target_ref": "surf_1"},
        {"effective_status": "BLOCKED", "substantive_outcome": None, "satisfies_completion": False, "target_ref": "surf_2"},
        {"effective_status": "STALE", "substantive_outcome": None, "satisfies_completion": False, "target_ref": "surf_2"},
        {"effective_status": "UNASSESSED", "is_waived": True, "satisfies_completion": False, "target_ref": "surf_3"},
        {"effective_status": "UNASSESSED", "is_not_applicable": True, "satisfies_completion": False, "target_ref": "surf_3"},
    ]
    scope_states = [
        {"state": "KNOWN_UNOBSERVED_SCOPE"},
        {"state": "UNSUPPORTED_SCOPE"},
        {"state": "UNKNOWN_SCOPE"},
    ]

    summary = compute_breadth_summary(
        inventory_revision_ref=inv_ref,
        obligation_set_revision="rev_1",
        evaluations=evals,
        scope_states=scope_states,
    )

    assert summary["mandatory_count"] == 6
    assert summary["qualified_count"] == 2
    assert summary["qualified_no_violation_observed_count"] == 1
    assert summary["qualified_substantive_violation_count"] == 1
    assert summary["blocked_count"] == 1
    assert summary["stale_count"] == 1
    assert summary["waived_count"] == 1
    assert summary["not_applicable_count"] == 1
    assert summary["known_unobserved_scope_count"] == 1
    assert summary["unsupported_scope_count"] == 1
    assert summary["unknown_scope_count"] == 1
    assert "D0" in summary["derived_depth_distribution"]

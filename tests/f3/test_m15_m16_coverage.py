"""Targeted unit and negative tests for PR-021 / M15/M16 invariant and coverage minimum."""
import hashlib
import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id, validate_id
from bdb_audit.core.registry import ContractRegistry, load_vectors
from bdb_audit.history.objects import CanonicalObject, ObjectRef
from bdb_audit.coverage import (
    InvariantRevision, MaterialityAssessment, CoverageObligationKey,
    CoverageObligation, CoverageObligationQualification,
    ObligationApplicabilityDecision, ApprovalDecision,
    evaluate_coverage_qualification, derive_presentation_depth,
)
from bdb_audit.schemas.foundation import F3_KINDS, foundation_schema_bindings
from bdb_audit.schemas.identity import LayeredValidator


def ref(kind, seed, ref_class="CONTENT_OR_PRIOR", logical_id=None):
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
        **({"logical_id": logical_id} if logical_id else {}),
    }


def test_invariant_and_no_backlink_cycle():
    cut = {"tag": "EMPTY_HISTORY"}
    src_gen = ref("source_generation", "gen_1")
    policy = ref("policy_revision", "pol_1")

    # Valid invariant
    inv = InvariantRevision(
        invariant_id=new_id("invariant_revision"),
        invariant_revision="1",
        invariant_input_history_cut=cut,
        source_generation_ref=src_gen,
        statement="Token must not be logged",
        activation_policy_ref=policy,
        category="SECURITY_BOUNDARY",
    )
    assert len(inv.digest) == 64
    assert inv.as_object().kind == "invariant_revision"

    # R5N67: Invariant pointing to materiality assessment must be rejected
    with pytest.raises(ValidationError, match="MATERIALITY_BACKLINK_CYCLE_FORBIDDEN"):
        InvariantRevision(
            invariant_id=new_id("invariant_revision"),
            invariant_revision="1",
            invariant_input_history_cut=cut,
            source_generation_ref=src_gen,
            statement="Bad invariant",
            activation_policy_ref=policy,
            materiality_assessment_ref=ref("materiality_assessment", "mat_1"),
        )


def test_materiality_assessment():
    cut = {"tag": "EMPTY_HISTORY"}
    mat = MaterialityAssessment(
        materiality_assessment_id=new_id("materiality_assessment"),
        subject_ref=ref("invariant_revision", "inv_1"),
        assessment_input_history_cut=cut,
        materiality_policy_ref=ref("policy_revision", "pol_1"),
        scope="GLOBAL",
        result="MATERIAL",
        rationale="Critical token handling",
    )
    assert len(mat.digest) == 64
    assert mat.as_object().kind == "materiality_assessment"

    with pytest.raises(ValidationError, match="INVALID_MATERIALITY_RESULT"):
        MaterialityAssessment(
            materiality_assessment_id=new_id("materiality_assessment"),
            subject_ref=ref("invariant_revision", "inv_1"),
            assessment_input_history_cut=cut,
            materiality_policy_ref=ref("policy_revision", "pol_1"),
            scope="GLOBAL",
            result="INVALID_RESULT",
            rationale="Bad result",
        )


def test_coverage_obligation_and_input_history_requirement():
    cut = {"tag": "EMPTY_HISTORY"}
    src_gen = ref("source_generation", "gen_1")
    surface = ref("surface_record", "surf_1")
    inv = ref("invariant_revision", "inv_1")
    mat = ref("materiality_assessment", "mat_1")
    env = ref("external_profile_ref", "env_1")
    oracle = ref("external_profile_ref", "oracle_1")
    pred = ref("external_profile_ref", "pred_1")
    app_pred = ref("external_profile_ref", "app_pred_1")
    policy = ref("policy_revision", "pol_1")
    origin = ref("registered_immutable_object", "orig_1")

    # Valid coverage obligation
    ob = CoverageObligation(
        obligation_id=new_id("coverage_obligation"),
        obligation_revision="1",
        obligation_input_history_cut=cut,
        source_generation_ref=src_gen,
        target_scope_or_surface_ref=surface,
        invariant_revision_ref=inv,
        scenario_class="POSITIVE_NORMAL",
        environment_profile_ref=env,
        materiality_assessment_ref=mat,
        required_oracle_independence_predicate_ref=oracle,
        acceptance_predicate_ref=pred,
        applicability_predicate_ref=app_pred,
        policy_obligation_key="POL_KEY_1",
        governing_policy_ref=policy,
        origin_ref=origin,
    )
    assert len(ob.digest) == 64

    # R5N54: Null input history cut must be rejected
    with pytest.raises(ValidationError, match="COVERAGE_OBLIGATION_HISTORY_CONTEXT_UNBOUND"):
        CoverageObligation(
            obligation_id=new_id("coverage_obligation"),
            obligation_revision="1",
            obligation_input_history_cut=None,  # Unbound context
            source_generation_ref=src_gen,
            target_scope_or_surface_ref=surface,
            invariant_revision_ref=inv,
            scenario_class="POSITIVE_NORMAL",
            environment_profile_ref=env,
            materiality_assessment_ref=mat,
            required_oracle_independence_predicate_ref=oracle,
            acceptance_predicate_ref=pred,
            applicability_predicate_ref=app_pred,
            policy_obligation_key="POL_KEY_1",
            governing_policy_ref=policy,
            origin_ref=origin,
        )

    # R5N69: Scalar materiality forbidden
    with pytest.raises(ValidationError, match="COVERAGE_SCALAR_MATERIALITY_FORBIDDEN"):
        CoverageObligation(
            obligation_id=new_id("coverage_obligation"),
            obligation_revision="1",
            obligation_input_history_cut=cut,
            source_generation_ref=src_gen,
            target_scope_or_surface_ref=surface,
            invariant_revision_ref=inv,
            scenario_class="POSITIVE_NORMAL",
            environment_profile_ref=env,
            materiality_assessment_ref=mat,
            required_oracle_independence_predicate_ref=oracle,
            acceptance_predicate_ref=pred,
            applicability_predicate_ref=app_pred,
            policy_obligation_key="POL_KEY_1",
            governing_policy_ref=policy,
            origin_ref=origin,
            materiality="MATERIAL",  # Forbidden scalar!
        )


def test_coverage_obligation_qualification_and_single_waiver_authority():
    cut = {"tag": "EMPTY_HISTORY"}
    ob_ref = ref("coverage_obligation", "ob_1")
    ev_ref = ref("evidence_qualification_assessment", "ev_1")

    # Valid qualification
    q = CoverageObligationQualification(
        qualification_id=new_id("coverage_obligation_qualification"),
        obligation_revision_ref=ob_ref,
        input_history_cut=cut,
        qualification_status="QUALIFIED",
        substantive_outcome="NO_VIOLATION_OBSERVED",
        evidence_qualification_refs=[ev_ref],
    )
    assert q.qualification_status == "QUALIFIED"

    # R5N55: Waiver must be approval_decision; second kind rejected
    with pytest.raises(ValidationError, match="SECOND_COVERAGE_WAIVER_AUTHORITY"):
        CoverageObligationQualification(
            qualification_id=new_id("coverage_obligation_qualification"),
            obligation_revision_ref=ob_ref,
            input_history_cut=cut,
            qualification_status="QUALIFIED",
            substantive_outcome="NO_VIOLATION_OBSERVED",
            waiver_decision_ref=ref("coverage_waiver_decision", "waiver_1"),
        )


def test_coverage_golden_vectors():
    vectors = load_vectors()["vectors"]
    by_id = {v["id"]: v for v in vectors}
    reg = ContractRegistry()

    # R5N29_COVERAGE_OBLIGATION_KEY_REGISTERED
    v_r5n29 = by_id["R5N29_COVERAGE_OBLIGATION_KEY_REGISTERED"]
    assert reg.contract("coverage_obligation_key")["kind"] == "coverage_obligation_key"

    # R5N54_COVERAGE_OBLIGATION_REQUIRES_INPUT_HISTORY_CUT
    v_r5n54 = by_id["R5N54_COVERAGE_OBLIGATION_REQUIRES_INPUT_HISTORY_CUT"]
    cut = v_r5n54["input"]["obligation_input_history_cut"]
    with pytest.raises(ValidationError, match=v_r5n54["expected"]["error"]):
        CoverageObligation(
            obligation_id=new_id("coverage_obligation"),
            obligation_revision="1",
            obligation_input_history_cut=cut,
            source_generation_ref=ref("source_generation", "gen_1"),
            target_scope_or_surface_ref=ref("surface_record", "s_1"),
            invariant_revision_ref=ref("invariant_revision", "i_1"),
            scenario_class="NORMAL",
            environment_profile_ref=ref("external_profile_ref", "env_1"),
            materiality_assessment_ref=ref("materiality_assessment", "m_1"),
            required_oracle_independence_predicate_ref=ref("external_profile_ref", "o_1"),
            acceptance_predicate_ref=ref("external_profile_ref", "a_1"),
            applicability_predicate_ref=ref("external_profile_ref", "app_1"),
            policy_obligation_key="KEY_1",
            governing_policy_ref=ref("policy_revision", "p_1"),
            origin_ref=ref("registered_immutable_object", "orig_1"),
        )

    # R5N55_SINGLE_COVERAGE_WAIVER_AUTHORITY
    v_r5n55 = by_id["R5N55_SINGLE_COVERAGE_WAIVER_AUTHORITY"]
    with pytest.raises(ValidationError, match=v_r5n55["expected"]["error"]):
        CoverageObligationQualification(
            qualification_id=new_id("coverage_obligation_qualification"),
            obligation_revision_ref=ref("coverage_obligation", "o_1"),
            input_history_cut={"tag": "EMPTY_HISTORY"},
            qualification_status="QUALIFIED",
            waiver_decision_ref=ref(v_r5n55["input"]["waiver_decision_ref_kind"], "w_1"),
        )

    # R5N61_CENTRAL_DECISIONS_EXPLICIT_COMPLETE
    v_r5n61 = by_id["R5N61_CENTRAL_DECISIONS_EXPLICIT_COMPLETE"]
    for k in v_r5n61["expected"]["required_kinds"]:
        assert reg.contract(k)["reference_contract_mode"] == v_r5n61["expected"]["required_mode"]

    # R5N67_INVARIANT_MATERIALITY_NO_BACKLINK_CYCLE
    v_r5n67 = by_id["R5N67_INVARIANT_MATERIALITY_NO_BACKLINK_CYCLE"]
    with pytest.raises(ValidationError, match=v_r5n67["expected"]["error"]):
        InvariantRevision(
            invariant_id="inv_cycle",
            invariant_revision="1",
            invariant_input_history_cut={"tag": "EMPTY_HISTORY"},
            source_generation_ref=ref("source_generation", "g_1"),
            statement="test",
            activation_policy_ref=ref("policy_revision", "p_1"),
            materiality_assessment_ref=ref("materiality_assessment", "m_1"),
        )

    # R5N69_COVERAGE_MATERIALITY_EXACT_ASSESSMENT
    v_r5n69 = by_id["R5N69_COVERAGE_MATERIALITY_EXACT_ASSESSMENT"]
    assert v_r5n69["expected"]["result"] == "ACCEPT"


def test_adversarial_coverage_engine():
    cut = {"tag": "EMPTY_HISTORY"}
    ev_digest = hashlib.sha256(b"evidence_1").hexdigest()
    ev_ref = ref("evidence_qualification_assessment", "evidence_1")

    ob = CoverageObligation(
        obligation_id=new_id("coverage_obligation"),
        obligation_revision="1",
        obligation_input_history_cut=cut,
        source_generation_ref=ref("source_generation", "g_1"),
        target_scope_or_surface_ref=ref("surface_record", "s_1"),
        invariant_revision_ref=ref("invariant_revision", "i_1"),
        scenario_class="NORMAL",
        environment_profile_ref=ref("external_profile_ref", "env_1"),
        materiality_assessment_ref=ref("materiality_assessment", "m_1"),
        required_oracle_independence_predicate_ref=ref("external_profile_ref", "o_1"),
        acceptance_predicate_ref=ref("external_profile_ref", "a_1"),
        applicability_predicate_ref=ref("external_profile_ref", "app_1"),
        policy_obligation_key="KEY_1",
        governing_policy_ref=ref("policy_revision", "p_1"),
        origin_ref=ref("registered_immutable_object", "orig_1"),
    )

    q = CoverageObligationQualification(
        qualification_id=new_id("coverage_obligation_qualification"),
        obligation_revision_ref=ob.as_object().as_ref().as_dict(),
        input_history_cut=cut,
        qualification_status="QUALIFIED",
        substantive_outcome="NO_VIOLATION_OBSERVED",
        evidence_qualification_refs=[ev_ref],
    )

    # Happy path: QUALIFIED + NO_VIOLATION_OBSERVED
    res = evaluate_coverage_qualification(ob, q)
    assert res["satisfies_completion"] is True
    assert res["effective_status"] == "QUALIFIED"

    # Invalidation degrades obligation to STALE
    res_inval = evaluate_coverage_qualification(ob, q, invalidated_evidence_digests={ev_digest})
    assert res_inval["satisfies_completion"] is False
    assert res_inval["effective_status"] == "STALE"
    assert res_inval["degraded_by_invalidation"] is True

    # No auto-N/A without decision
    q_na = CoverageObligationQualification(
        qualification_id=new_id("coverage_obligation_qualification"),
        obligation_revision_ref=ob.as_object().as_ref().as_dict(),
        input_history_cut=cut,
        qualification_status="QUALIFIED",
        applicability_decision_ref=ref("obligation_applicability_decision", "app_1"),
    )
    with pytest.raises(ValidationError, match="AUTO_NA_FORBIDDEN"):
        evaluate_coverage_qualification(ob, q_na, applicability_decision=None)

    # No auto-waiver without approval
    q_waiver = CoverageObligationQualification(
        qualification_id=new_id("coverage_obligation_qualification"),
        obligation_revision_ref=ob.as_object().as_ref().as_dict(),
        input_history_cut=cut,
        qualification_status="QUALIFIED",
        waiver_decision_ref=ref("approval_decision", "appr_1"),
    )
    with pytest.raises(ValidationError, match="AUTO_WAIVER_FORBIDDEN"):
        evaluate_coverage_qualification(ob, q_waiver, waiver_decision=None)

    # Derived depth rules
    depth_res = derive_presentation_depth([res], has_active_mutation=False, concurrency_obligations_satisfied=False)
    assert depth_res["derived_depth"] == "D3"

    # Single concurrency cannot lift to D4 without satisfying concurrency obligations
    depth_res2 = derive_presentation_depth([res], has_active_mutation=False, concurrency_obligations_satisfied=True)
    assert depth_res2["derived_depth"] == "D4"

    # Inactive mutation cannot grant D5
    depth_res3 = derive_presentation_depth([res], has_active_mutation=False, concurrency_obligations_satisfied=True)
    assert depth_res3["derived_depth"] != "D5"


def test_coverage_schemas_with_layered_validator():
    bindings = foundation_schema_bindings(kinds=F3_KINDS)
    validator = LayeredValidator(bindings=bindings)

    cut = {"tag": "EMPTY_HISTORY"}
    mat = MaterialityAssessment(
        materiality_assessment_id=new_id("materiality_assessment"),
        subject_ref=ref("invariant_revision", "inv_1"),
        assessment_input_history_cut=cut,
        materiality_policy_ref=ref("policy_revision", "pol_1"),
        scope="GLOBAL",
        result="MATERIAL",
        rationale="Token secrecy",
    )
    val_mat = validator.validate("materiality_assessment", canonical_bytes(mat.body()))
    assert val_mat.revision_digest == mat.digest

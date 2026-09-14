"""Targeted unit and negative tests for R5.3 M21/M22 adjudication and contradiction."""
import hashlib

import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id
from bdb_audit.core.registry import load_vectors
from bdb_audit.adjudication import (
    FindingClaimRevision,
    FindingAxisAssessment,
    ContradictionRevision,
    sort_membership_edges,
    validate_root_cause_authority,
    adjudicate_finding,
    transition_finding_lifecycle,
    resolve_contradiction,
    apply_contradiction_resolution,
    reopen_contradiction,
    cluster_findings_into_root_cause,
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


def make_axes(claim, cut, policy, *, mech="SUPPORTED", reach="SUPPORTED", impact="SUPPORTED"):
    claim_ref = claim.as_object().as_ref().as_dict()
    evidence = ref("evidence_qualification_assessment", "axis_evidence")
    method = ref("experiment_spec", "controlled_method")
    operational = {}
    for axis, outcome in (("MECHANISM", mech), ("REACHABILITY", reach), ("IMPACT", impact)):
        operational[axis] = FindingAxisAssessment(
            finding_axis_assessment_id=new_id("finding_axis_assessment"),
            claim_revision_ref=claim_ref,
            assessment_input_history_cut=cut,
            assessment_policy_ref=policy,
            axis=axis,
            scope={"surface": "auth"},
            evidence_qualification_refs=[evidence],
            epistemic_outcome=outcome,
            method_or_characterization_refs=[method],
            confidence="HIGH",
        )
    severity = FindingAxisAssessment(
        finding_axis_assessment_id=new_id("finding_axis_assessment"),
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=cut,
        assessment_policy_ref=policy,
        axis="SEVERITY",
        scope={"surface": "auth"},
        evidence_qualification_refs=[evidence],
        severity_value="HIGH",
        method_or_characterization_refs=[method],
        confidence="HIGH",
    )
    return operational["MECHANISM"], operational["REACHABILITY"], operational["IMPACT"], severity


def test_m21_golden_vectors():
    vectors = load_vectors()["vectors"]
    by_id = {v["id"]: v for v in vectors}

    v_fr07 = by_id["FR07_SEPARATE_MEMBERSHIP_AUTHORITY_REJECT"]
    with pytest.raises(ValidationError, match=v_fr07["expected"]["error"]):
        validate_root_cause_authority(v_fr07["input"]["accepted_kind"])

    v_fr10 = by_id["FR10_REFUTED_CONTROLLED_DYNAMIC"]
    axis_ass = FindingAxisAssessment(
        finding_axis_assessment_id=new_id("finding_axis_assessment"),
        claim_revision_ref=ref("finding_claim_revision", "c1"),
        assessment_input_history_cut={"tag": "EMPTY_HISTORY"},
        assessment_policy_ref=ref("policy_revision", "p1"),
        axis=v_fr10["input"]["axis"],
        epistemic_outcome=v_fr10["input"]["epistemic_outcome"],
        method_or_characterization_refs=[ref("experiment_spec", v_fr10["input"]["method"])],
        confidence="HIGH",
    )
    assert axis_ass.axis == "REACHABILITY"
    assert axis_ass.epistemic_outcome == "REFUTED"
    assert len(axis_ass.method_or_characterization_refs) == 1

    v_dup = by_id["R5N74_ROOT_CAUSE_MEMBERSHIP_EXACT_DUPLICATE_REJECT"]
    edge = {
        "finding_claim_revision_ref": "f1",
        "relation_role": "PRIMARY",
        "scope": {"surface": "a"},
    }
    with pytest.raises(ValidationError, match=v_dup["expected"]["error"]):
        sort_membership_edges([edge, edge])

    v_order = by_id["R5N74_ROOT_CAUSE_MEMBERSHIP_TUPLE_ORDER"]
    sorted_edges = sort_membership_edges(v_order["input"]["edges"])
    assert sorted_edges[0]["finding_claim_revision_ref"] == "f1"
    assert sorted_edges[1]["finding_claim_revision_ref"] == "f2"


def test_finding_claim_is_evidence_free_and_four_axis_adjudication_confirms():
    cut = {"tag": "EMPTY_HISTORY"}
    policy = ref("policy_revision", "pol_1")
    claim = FindingClaimRevision(
        finding_id=new_id("finding_claim_revision"),
        claim_statement="Improper access control in user deletion",
        source_generation_ref=ref("source_generation", "gen_1"),
        category="SECURITY",
        scope_refs=[ref("surface_record", "surf_1")],
        violated_invariant_refs=[ref("invariant_revision", "inv_1")],
        limitations=["production replay not yet performed"],
    )
    body = claim.body()
    assert "evidence_qualification_refs" not in body
    assert "severity_assessment_ref" not in body
    assert "finding_lifecycle_status" not in body

    mech, reach, impact, severity = make_axes(claim, cut, policy)
    decision = adjudicate_finding(
        claim=claim,
        mechanism=mech,
        reachability=reach,
        impact=impact,
        severity=severity,
        adjudicator_ref=ref("actor_or_authority_ref", "auditor_1"),
        input_history_cut=cut,
        scope={"surface": "auth"},
    )
    assert decision.finding_lifecycle_status == "CONFIRMED_CURRENT"
    assert len(decision.digest) == 64


def test_severity_is_not_epistemic_truth_and_operational_axis_binding_is_exact():
    cut = {"tag": "EMPTY_HISTORY"}
    policy = ref("policy_revision", "pol_axis")
    claim = FindingClaimRevision(
        claim_statement="Race in session revocation",
        source_generation_ref=ref("source_generation", "gen_axis"),
        category="RELIABILITY",
    )
    with pytest.raises(ValidationError, match="SEVERITY_EPISTEMIC_OUTCOME_FORBIDDEN"):
        FindingAxisAssessment(
            claim_revision_ref=claim.as_object().as_ref().as_dict(),
            assessment_input_history_cut=cut,
            assessment_policy_ref=policy,
            axis="SEVERITY",
            severity_value="HIGH",
            epistemic_outcome="SUPPORTED",
        )

    mech, reach, impact, severity = make_axes(claim, cut, policy)
    other_claim = FindingClaimRevision(
        claim_statement="Different claim",
        source_generation_ref=ref("source_generation", "gen_axis"),
    )
    wrong_reach = FindingAxisAssessment(
        claim_revision_ref=other_claim.as_object().as_ref().as_dict(),
        assessment_input_history_cut=cut,
        assessment_policy_ref=policy,
        axis="REACHABILITY",
        epistemic_outcome="SUPPORTED",
        evidence_qualification_refs=[ref("evidence_qualification_assessment", "wrong")],
    )
    with pytest.raises(ValidationError, match="FINDING_AXIS_CLAIM_MISMATCH"):
        adjudicate_finding(
            claim=claim,
            mechanism=mech,
            reachability=wrong_reach,
            impact=impact,
            severity=severity,
            adjudicator_ref=ref("actor_or_authority_ref", "auditor_axis"),
            input_history_cut=cut,
        )


def test_refuted_axis_rejects_and_lifecycle_is_backward_chained():
    cut = {"tag": "EMPTY_HISTORY"}
    policy = ref("policy_revision", "pol_refuted")
    claim = FindingClaimRevision(
        claim_statement="Unreachable administrative code path",
        source_generation_ref=ref("source_generation", "gen_refuted"),
    )
    mech, reach, impact, severity = make_axes(claim, cut, policy, reach="REFUTED")
    decision = adjudicate_finding(
        claim=claim,
        mechanism=mech,
        reachability=reach,
        impact=impact,
        severity=severity,
        adjudicator_ref=ref("actor_or_authority_ref", "auditor_refuted"),
        input_history_cut=cut,
    )
    assert decision.finding_lifecycle_status == "REJECTED"

    reopened = transition_finding_lifecycle(
        decision,
        "REOPENED",
        ref("actor_or_authority_ref", "auditor_refuted"),
        {"tag": "LATER_CUT"},
    )
    assert reopened.finding_lifecycle_status == "REOPENED"
    assert reopened.previous_adjudication_decision_ref["revision_digest"] == decision.digest


def test_root_cause_membership_is_one_way_authority():
    claim_a = ref("finding_claim_revision", "a")
    claim_b = ref("finding_claim_revision", "b")
    root = cluster_findings_into_root_cause(
        source_generation_ref=ref("source_generation", "gen_root"),
        mechanism_statement="Shared unchecked authorization boundary",
        membership_edges=[
            {"finding_claim_revision_ref": claim_b, "relation_role": "CONTRIBUTING", "scope": {"surface": "b"}},
            {"finding_claim_revision_ref": claim_a, "relation_role": "PRIMARY", "scope": {"surface": "a"}},
        ],
        scope={"subsystem": "auth"},
    )
    assert root.status == "ACTIVE"
    assert len(root.membership_edges) == 2
    assert "root_cause_ref" not in FindingClaimRevision(
        claim_statement="Evidence-free member",
        source_generation_ref=ref("source_generation", "gen_root"),
    ).body()


def test_contradiction_resolution_dag_and_majority_vote_forbidden():
    cut = {"tag": "EMPTY_HISTORY"}
    claim_a = ref("finding_claim_revision", "c_support")
    claim_b = ref("finding_claim_revision", "c_refute")
    ev_support = ref("evidence_qualification_assessment", "ev_support")
    ev_refute = ref("evidence_qualification_assessment", "ev_refute")
    contra = ContradictionRevision(
        contradiction_id=new_id("contradiction_revision"),
        contradiction_revision="1",
        claim_revision_refs=[claim_a, claim_b],
        scope={"environment": "production"},
        positions=[
            {"claim_revision_ref": claim_a, "position": "SUPPORTED"},
            {"claim_revision_ref": claim_b, "position": "REFUTED"},
        ],
        supporting_evidence_qualification_refs=[ev_support],
        opposing_evidence_qualification_refs=[ev_refute],
        required_falsifier={"experiment": "controlled production-equivalent replay"},
        status="OPEN",
    )

    with pytest.raises(ValidationError, match="MAJORITY_VOTE_FORBIDDEN"):
        resolve_contradiction(
            contra,
            resolution_kind="REFUTED",
            resolved_scope={"environment": "production"},
            basis_refs=[ev_refute],
            input_history_cut=cut,
            resulting_status="RESOLVED_FULL",
            resolved_by_majority_vote=True,
        )

    resolution = resolve_contradiction(
        contra,
        resolution_kind="SCOPES_SEPARATED",
        resolved_scope={"environment": "production"},
        basis_refs=[ev_support, ev_refute],
        input_history_cut=cut,
        resulting_status="RESOLVED_SCOPED",
    )
    successor = apply_contradiction_resolution(contra, resolution)
    assert successor.status == "RESOLVED_SCOPED"
    assert successor.contradiction_revision == "2"
    assert successor.predecessor_contradiction_revision_ref["revision_digest"] == contra.digest
    assert successor.resolution_decision_ref["revision_digest"] == resolution.digest

    reopened = reopen_contradiction(
        successor,
        new_opposing_evidence_refs=[ref("evidence_qualification_assessment", "late_counterevidence")],
    )
    assert reopened.status == "REOPENED"
    assert reopened.contradiction_revision == "3"
    assert reopened.predecessor_contradiction_revision_ref["revision_digest"] == successor.digest
    assert "resolution_decision_ref" not in reopened.body()


def test_m21_schemas_with_layered_validator():
    bindings = foundation_schema_bindings(kinds=F3_KINDS)
    validator = LayeredValidator(bindings=bindings)
    claim = FindingClaimRevision(
        claim_statement="Missing authorization header check",
        source_generation_ref=ref("source_generation", "gen_schema"),
        category="SECURITY",
    )
    validated = validator.validate("finding_claim_revision", canonical_bytes(claim.body()))
    assert validated.revision_digest == claim.digest

    severity = FindingAxisAssessment(
        claim_revision_ref=claim.as_object().as_ref().as_dict(),
        assessment_input_history_cut={"tag": "EMPTY_HISTORY"},
        assessment_policy_ref=ref("policy_revision", "schema_policy"),
        axis="SEVERITY",
        severity_value="MEDIUM",
    )
    validated_severity = validator.validate("finding_axis_assessment", canonical_bytes(severity.body()))
    assert validated_severity.revision_digest == severity.digest

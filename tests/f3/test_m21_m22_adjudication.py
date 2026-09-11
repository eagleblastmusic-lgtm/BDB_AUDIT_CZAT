"""Targeted unit and negative tests for PR-025 / M21/M22 adjudication and contradiction."""
import hashlib
import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id
from bdb_audit.core.registry import load_vectors
from bdb_audit.adjudication import (
    FindingClaimRevision, FindingAxisAssessment,
    FindingAdjudicationDecision, RootCauseRevision,
    ContradictionRevision, ContradictionResolutionDecision,
    sort_membership_edges, validate_root_cause_authority,
    adjudicate_finding,
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


def test_m21_golden_vectors():
    vectors = load_vectors()["vectors"]
    by_id = {v["id"]: v for v in vectors}

    # FR07_SEPARATE_MEMBERSHIP_AUTHORITY_REJECT
    v_fr07 = by_id["FR07_SEPARATE_MEMBERSHIP_AUTHORITY_REJECT"]
    with pytest.raises(ValidationError, match=v_fr07["expected"]["error"]):
        validate_root_cause_authority(v_fr07["input"]["accepted_kind"])

    # FR10_REFUTED_CONTROLLED_DYNAMIC
    v_fr10 = by_id["FR10_REFUTED_CONTROLLED_DYNAMIC"]
    axis_ass = FindingAxisAssessment(
        assessment_id=new_id("finding_axis_assessment"),
        claim_revision_ref=ref("finding_claim_revision", "c1"),
        assessment_input_history_cut={"tag": "EMPTY_HISTORY"},
        assessment_policy_ref=ref("policy_revision", "p1"),
        axis=v_fr10["input"]["axis"],
        epistemic_outcome=v_fr10["input"]["epistemic_outcome"],
        method=v_fr10["input"]["method"],
    )
    assert axis_ass.axis == "REACHABILITY"
    assert axis_ass.epistemic_outcome == "REFUTED"
    assert axis_ass.method == "CONTROLLED_DYNAMIC"

    # R5N74_ROOT_CAUSE_MEMBERSHIP_EXACT_DUPLICATE_REJECT
    v_dup = by_id["R5N74_ROOT_CAUSE_MEMBERSHIP_EXACT_DUPLICATE_REJECT"]
    edge = {
        "finding_claim_revision_ref": "f1",
        "relation_role": "PRIMARY",
        "scope": {"surface": "a"},
    }
    with pytest.raises(ValidationError, match=v_dup["expected"]["error"]):
        sort_membership_edges([edge, edge])

    # R5N74_ROOT_CAUSE_MEMBERSHIP_TUPLE_ORDER
    v_order = by_id["R5N74_ROOT_CAUSE_MEMBERSHIP_TUPLE_ORDER"]
    sorted_edges = sort_membership_edges(v_order["input"]["edges"])
    # In canonical order: f1 (PRIMARY, surface a) comes before f2 (CONTRIBUTING, surface b)
    assert sorted_edges[0]["finding_claim_revision_ref"] == "f1"
    assert sorted_edges[1]["finding_claim_revision_ref"] == "f2"


def test_finding_adjudication_flow():
    cut = {"tag": "EMPTY_HISTORY"}
    src_gen = ref("source_generation", "gen_1")
    adjudicator = ref("actor_or_authority_ref", "auditor_1")

    # Claim revision (evidence-free)
    claim = FindingClaimRevision(
        statement="Improper access control in user deletion",
        source_generation_ref=src_gen,
        scope_refs=[ref("surface_record", "surf_1")],
        violated_invariant_refs=[ref("invariant_revision", "inv_1")],
    )
    assert len(claim.digest) == 64

    # 3-axis assessments
    pol = ref("policy_revision", "pol_1")
    mech = FindingAxisAssessment(
        assessment_id=new_id("finding_axis_assessment"),
        claim_revision_ref=claim.as_object().as_ref().as_dict(),
        assessment_input_history_cut=cut,
        assessment_policy_ref=pol,
        axis="MECHANISM",
        epistemic_outcome="SUPPORTED",
        method="UNIT_AND_FUZZ",
    )
    reach = FindingAxisAssessment(
        assessment_id=new_id("finding_axis_assessment"),
        claim_revision_ref=claim.as_object().as_ref().as_dict(),
        assessment_input_history_cut=cut,
        assessment_policy_ref=pol,
        axis="REACHABILITY",
        epistemic_outcome="SUPPORTED",
        method="CONTROLLED_DYNAMIC",
    )
    impact = FindingAxisAssessment(
        assessment_id=new_id("finding_axis_assessment"),
        claim_revision_ref=claim.as_object().as_ref().as_dict(),
        assessment_input_history_cut=cut,
        assessment_policy_ref=pol,
        axis="IMPACT",
        epistemic_outcome="SUPPORTED",
        method="PRIVILEGE_ANALYSIS",
    )
    sev = FindingAxisAssessment(
        assessment_id=new_id("finding_axis_assessment"),
        claim_revision_ref=claim.as_object().as_ref().as_dict(),
        assessment_input_history_cut=cut,
        assessment_policy_ref=pol,
        axis="SEVERITY",
        epistemic_outcome="SUPPORTED",
        method="CVSS_MAPPING",
    )

    # Full adjudication
    adj = adjudicate_finding(
        claim=claim,
        mechanism=mech,
        reachability=reach,
        impact=impact,
        severity=sev,
        adjudicator_ref=adjudicator,
        input_history_cut=cut,
    )
    assert adj.lifecycle_status == "CONFIRMED_CURRENT"
    assert len(adj.digest) == 64


def test_contradiction_and_majority_vote_forbidden():
    cut = {"tag": "EMPTY_HISTORY"}
    claim_ref = ref("finding_claim_revision", "c1")
    ev1 = ref("evidence_qualification_assessment", "e1")
    ev2 = ref("evidence_qualification_assessment", "e2")

    contra = ContradictionRevision(
        contradiction_id=new_id("contradiction_revision"),
        claim_revision_ref=claim_ref,
        contradicting_evidence_refs=[ev1, ev2],
        input_history_cut=cut,
        status="UNRESOLVED",
    )
    assert len(contra.digest) == 64

    # Majority vote resolution is strictly forbidden
    with pytest.raises(ValidationError, match="MAJORITY_VOTE_FORBIDDEN"):
        ContradictionResolutionDecision(
            resolution_id=new_id("contradiction_resolution_decision"),
            contradiction_revision_ref=contra.as_object().as_ref().as_dict(),
            adjudicator_ref=ref("actor_or_authority_ref", "lead_auditor"),
            resolution_status="RESOLVED",
            rationale="3 support votes beat 1 refute vote",
            input_history_cut=cut,
            support_count=3,
            refute_count=1,
            resolved_by_majority_vote=True,  # Forbidden!
        )


def test_m21_schemas_with_layered_validator():
    bindings = foundation_schema_bindings(kinds=F3_KINDS)
    validator = LayeredValidator(bindings=bindings)

    cut = {"tag": "EMPTY_HISTORY"}
    claim = FindingClaimRevision(
        statement="Missing authorization header check",
        source_generation_ref=ref("source_generation", "gen_1"),
    )
    val = validator.validate("finding_claim_revision", canonical_bytes(claim.body()))
    assert val.revision_digest == claim.digest

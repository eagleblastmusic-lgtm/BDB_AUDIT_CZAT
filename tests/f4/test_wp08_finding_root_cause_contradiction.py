"""Targeted unit and adversarial tests for WP-F4-08 on the R5.3 M21/M22 contract."""
import hashlib

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.adjudication import (
    FindingClaimRevision,
    FindingAxisAssessment,
    ContradictionRevision,
    adjudicate_finding,
    transition_finding_lifecycle,
    resolve_contradiction,
    apply_contradiction_resolution,
    reopen_contradiction,
    cluster_findings_into_root_cause,
    validate_root_cause_authority,
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


def make_axes(claim, mech="SUPPORTED", reach="SUPPORTED", imp="SUPPORTED", severity="HIGH"):
    cut = {"tag": "TEST_CUT"}
    policy = make_ref("policy_revision", "p1")
    evidence = make_ref("evidence_qualification_assessment", "axis_ev")
    claim_ref = claim.as_object().as_ref().as_dict()

    def operational(axis, outcome):
        return FindingAxisAssessment(
            claim_revision_ref=claim_ref,
            assessment_input_history_cut=cut,
            assessment_policy_ref=policy,
            axis=axis,
            epistemic_outcome=outcome,
            evidence_qualification_refs=[evidence],
            confidence="HIGH",
        )

    sev = FindingAxisAssessment(
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=cut,
        assessment_policy_ref=policy,
        axis="SEVERITY",
        severity_value=severity,
        evidence_qualification_refs=[evidence],
        confidence="HIGH",
    )
    return operational("MECHANISM", mech), operational("REACHABILITY", reach), operational("IMPACT", imp), sev


def test_4_axis_finding_adjudication_confirmed():
    cut = {"tag": "TEST_CUT"}
    claim = FindingClaimRevision(
        claim_statement="Arbitrary file write via path traversal in unpacker",
        source_generation_ref=make_ref("source_generation", "gen_1"),
        category="SECURITY",
    )
    m, r, i, s = make_axes(claim)
    decision = adjudicate_finding(
        claim=claim,
        mechanism=m,
        reachability=r,
        impact=i,
        severity=s,
        adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
        input_history_cut=cut,
    )
    assert decision.finding_lifecycle_status == "CONFIRMED_CURRENT"
    assert len(decision.digest) == 64


def test_refuted_axis_cannot_be_forced_confirmed():
    cut = {"tag": "TEST_CUT"}
    claim = FindingClaimRevision(
        claim_statement="Theoretical timing attack in MAC verification",
        source_generation_ref=make_ref("source_generation", "gen_1"),
    )
    m, r, i, s = make_axes(claim, reach="REFUTED")
    decision = adjudicate_finding(
        claim=claim,
        mechanism=m,
        reachability=r,
        impact=i,
        severity=s,
        adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
        input_history_cut=cut,
    )
    assert decision.finding_lifecycle_status == "REJECTED"

    with pytest.raises(ValidationError, match="REFUTED_AXIS_CANNOT_BE_CONFIRMED"):
        adjudicate_finding(
            claim=claim,
            mechanism=m,
            reachability=r,
            impact=i,
            severity=s,
            adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
            input_history_cut=cut,
            finding_lifecycle_status="CONFIRMED_CURRENT",
        )


def test_inconclusive_axis_cannot_be_forced_confirmed():
    cut = {"tag": "TEST_CUT"}
    claim = FindingClaimRevision(
        claim_statement="Possible use-after-free",
        source_generation_ref=make_ref("source_generation", "gen_1"),
    )
    m, r, i, s = make_axes(claim, reach="INCONCLUSIVE")
    decision = adjudicate_finding(
        claim=claim,
        mechanism=m,
        reachability=r,
        impact=i,
        severity=s,
        adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
        input_history_cut=cut,
    )
    assert decision.finding_lifecycle_status == "OPEN"

    with pytest.raises(ValidationError, match="UNCONFIRMED_AXIS_CANNOT_BE_CONFIRMED"):
        adjudicate_finding(
            claim=claim,
            mechanism=m,
            reachability=r,
            impact=i,
            severity=s,
            adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
            input_history_cut=cut,
            finding_lifecycle_status="CONFIRMED_CURRENT",
        )


def test_append_only_lifecycle_transitions():
    cut = {"tag": "TEST_CUT"}
    claim = FindingClaimRevision(
        claim_statement="Privilege escalation via sudo helper",
        source_generation_ref=make_ref("source_generation", "gen_1"),
    )
    m, r, i, s = make_axes(claim)
    decision_0 = adjudicate_finding(
        claim=claim,
        mechanism=m,
        reachability=r,
        impact=i,
        severity=s,
        adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
        input_history_cut=cut,
    )
    decision_1 = transition_finding_lifecycle(
        current_decision=decision_0,
        target_status="REMEDIATION_PENDING",
        adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
        input_history_cut=cut,
    )
    decision_2 = transition_finding_lifecycle(
        current_decision=decision_1,
        target_status="FIXED_ON_NEW_SOURCE",
        adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
        input_history_cut=cut,
    )
    assert decision_1.previous_adjudication_decision_ref["revision_digest"] == decision_0.digest
    assert decision_2.previous_adjudication_decision_ref["revision_digest"] == decision_1.digest

    with pytest.raises(ValidationError, match="INVALID_LIFECYCLE_TRANSITION"):
        transition_finding_lifecycle(
            current_decision=decision_2,
            target_status="REMEDIATION_PENDING",
            adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
            input_history_cut=cut,
        )


def test_root_cause_clustering_and_duplicate_rejection():
    src_gen = make_ref("source_generation", "gen_1")
    f1 = make_ref("finding_claim_revision", "f1")
    f2 = make_ref("finding_claim_revision", "f2")
    edge1 = {"finding_claim_revision_ref": f1, "relation_role": "PRIMARY", "scope": {"subsystem": "auth"}}
    edge2 = {"finding_claim_revision_ref": f2, "relation_role": "CONTRIBUTING", "scope": {"subsystem": "session"}}

    root = cluster_findings_into_root_cause(
        source_generation_ref=src_gen,
        mechanism_statement="Shared authorization-state invalidation defect",
        membership_edges=[edge2, edge1],
        scope={"subsystem": "auth"},
    )
    assert root.status == "ACTIVE"
    assert len(root.membership_edges) == 2

    with pytest.raises(ValidationError, match="ROOT_CAUSE_MEMBERSHIP_DUPLICATE_OR_AMBIGUOUS"):
        cluster_findings_into_root_cause(
            source_generation_ref=src_gen,
            mechanism_statement="Shared authorization-state invalidation defect",
            membership_edges=[edge1, edge1],
        )

    with pytest.raises(ValidationError, match="SECOND_AUTHORITY_FOR_ROOT_CAUSE_MEMBERSHIP"):
        validate_root_cause_authority("RootCauseMembershipRevision")


def test_contradiction_resolution_and_reopen_are_versioned():
    cut = {"tag": "TEST_CUT"}
    claim_a = make_ref("finding_claim_revision", "c_support")
    claim_b = make_ref("finding_claim_revision", "c_refute")
    ev_support = make_ref("evidence_qualification_assessment", "ev_supports")
    ev_refute = make_ref("evidence_qualification_assessment", "ev_refutes")
    contradiction = ContradictionRevision(
        claim_revision_refs=[claim_a, claim_b],
        scope={"environment": "prod"},
        positions=[
            {"claim_revision_ref": claim_a, "position": "SUPPORTED"},
            {"claim_revision_ref": claim_b, "position": "REFUTED"},
        ],
        supporting_evidence_qualification_refs=[ev_support],
        opposing_evidence_qualification_refs=[ev_refute],
        required_falsifier={"experiment": "controlled replay"},
        status="OPEN",
    )

    with pytest.raises(ValidationError, match="MAJORITY_VOTE_FORBIDDEN"):
        resolve_contradiction(
            contradiction,
            resolution_kind="REFUTED",
            resolved_scope={"environment": "prod"},
            basis_refs=[ev_refute],
            input_history_cut=cut,
            resulting_status="RESOLVED_FULL",
            resolved_by_majority_vote=True,
        )

    resolution = resolve_contradiction(
        contradiction,
        resolution_kind="SCOPES_SEPARATED",
        resolved_scope={"environment": "prod"},
        basis_refs=[ev_support, ev_refute],
        input_history_cut=cut,
        resulting_status="RESOLVED_SCOPED",
    )
    resolved = apply_contradiction_resolution(contradiction, resolution)
    assert resolved.status == "RESOLVED_SCOPED"
    assert resolved.contradiction_revision == "2"

    reopened = reopen_contradiction(
        resolved,
        new_opposing_evidence_refs=[make_ref("evidence_qualification_assessment", "ev_new_exploit")],
    )
    assert reopened.status == "REOPENED"
    assert reopened.contradiction_revision == "3"
    assert reopened.predecessor_contradiction_revision_ref["revision_digest"] == resolved.digest

"""Targeted unit and negative tests for WP-F4-08 / PR-F4-08.

Tests:
1. 4-axis finding assessment (MECHANISM, REACHABILITY, IMPACT, SEVERITY) and adjudication.
2. Adversarial rule: Refuted axis cannot be confirmed (fails closed).
3. Adversarial rule: Inconclusive axis cannot be confirmed.
4. Append-only finding lifecycle transitions and backward-chaining.
5. Root cause clustering, canonical edge ordering, and duplicate rejection.
6. Contradiction resolution authority and majority voting prohibition.
7. Contradiction reopening upon counterevidence discovery.
"""
import hashlib
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id
from bdb_audit.adjudication import (
    FindingClaimRevision,
    FindingAxisAssessment,
    FindingAdjudicationDecision,
    RootCauseRevision,
    ContradictionRevision,
    ContradictionResolutionDecision,
    adjudicate_finding,
    transition_finding_lifecycle,
    resolve_contradiction,
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


def make_axes(mech="SUPPORTED", reach="SUPPORTED", imp="SUPPORTED", sev="SUPPORTED"):
    cut = {"tag": "TEST_CUT"}
    pol = make_ref("policy_revision", "p1")
    claim_ref = make_ref("finding_claim_revision", "c1")

    m = FindingAxisAssessment(
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=cut,
        assessment_policy_ref=pol,
        axis="MECHANISM",
        epistemic_outcome=mech,
        method="FUZZING",
    )
    r = FindingAxisAssessment(
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=cut,
        assessment_policy_ref=pol,
        axis="REACHABILITY",
        epistemic_outcome=reach,
        method="DYNAMIC_TRACE",
    )
    i = FindingAxisAssessment(
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=cut,
        assessment_policy_ref=pol,
        axis="IMPACT",
        epistemic_outcome=imp,
        method="EXPLOITATION_ANALYSIS",
    )
    s = FindingAxisAssessment(
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=cut,
        assessment_policy_ref=pol,
        axis="SEVERITY",
        epistemic_outcome=sev,
        method="CVSS",
    )
    return m, r, i, s


def test_4_axis_finding_adjudication_confirmed():
    cut = {"tag": "TEST_CUT"}
    claim = FindingClaimRevision(
        statement="Arbitrary file write via path traversal in unpacker",
        source_generation_ref=make_ref("source_generation", "gen_1"),
    )
    m, r, i, s = make_axes("SUPPORTED", "SUPPORTED", "SUPPORTED", "SUPPORTED")
    adj = adjudicate_finding(
        claim=claim,
        mechanism=m,
        reachability=r,
        impact=i,
        severity=s,
        adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
        input_history_cut=cut,
    )
    assert adj.lifecycle_status == "CONFIRMED_CURRENT"
    assert len(adj.digest) == 64


def test_refuted_axis_cannot_be_confirmed_fail_closed():
    cut = {"tag": "TEST_CUT"}
    claim = FindingClaimRevision(
        statement="Theoretical timing attack in MAC verification",
        source_generation_ref=make_ref("source_generation", "gen_1"),
    )
    # Reachability is REFUTED
    m, r, i, s = make_axes("SUPPORTED", "REFUTED", "SUPPORTED", "SUPPORTED")

    # Automatic evaluation assigns REJECTED
    adj = adjudicate_finding(
        claim=claim,
        mechanism=m,
        reachability=r,
        impact=i,
        severity=s,
        adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
        input_history_cut=cut,
    )
    assert adj.lifecycle_status == "REJECTED"

    # Forcing CONFIRMED_CURRENT when REFUTED must fail closed
    with pytest.raises(ValidationError, match="REFUTED_AXIS_CANNOT_BE_CONFIRMED"):
        adjudicate_finding(
            claim=claim,
            mechanism=m,
            reachability=r,
            impact=i,
            severity=s,
            adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
            input_history_cut=cut,
            lifecycle_status="CONFIRMED_CURRENT",
        )


def test_inconclusive_axis_cannot_be_confirmed():
    cut = {"tag": "TEST_CUT"}
    claim = FindingClaimRevision(
        statement="Possible use-after-free",
        source_generation_ref=make_ref("source_generation", "gen_1"),
    )
    m, r, i, s = make_axes("SUPPORTED", "INCONCLUSIVE", "SUPPORTED", "SUPPORTED")

    adj = adjudicate_finding(
        claim=claim,
        mechanism=m,
        reachability=r,
        impact=i,
        severity=s,
        adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
        input_history_cut=cut,
    )
    assert adj.lifecycle_status == "OPEN"

    with pytest.raises(ValidationError, match="UNCONFIRMED_AXIS_CANNOT_BE_CONFIRMED"):
        adjudicate_finding(
            claim=claim,
            mechanism=m,
            reachability=r,
            impact=i,
            severity=s,
            adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
            input_history_cut=cut,
            lifecycle_status="CONFIRMED_CURRENT",
        )


def test_append_only_lifecycle_transitions():
    cut = {"tag": "TEST_CUT"}
    claim = FindingClaimRevision(
        statement="Privilege escalation via sudo helper",
        source_generation_ref=make_ref("source_generation", "gen_1"),
    )
    m, r, i, s = make_axes("SUPPORTED", "SUPPORTED", "SUPPORTED", "SUPPORTED")
    adj_0 = adjudicate_finding(
        claim=claim,
        mechanism=m,
        reachability=r,
        impact=i,
        severity=s,
        adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
        input_history_cut=cut,
    )
    assert adj_0.lifecycle_status == "CONFIRMED_CURRENT"

    # CONFIRMED_CURRENT -> REMEDIATION_PENDING
    adj_1 = transition_finding_lifecycle(
        current_decision=adj_0,
        target_status="REMEDIATION_PENDING",
        adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
        input_history_cut=cut,
    )
    assert adj_1.lifecycle_status == "REMEDIATION_PENDING"
    assert adj_1.previous_adjudication_decision_ref["revision_digest"] == adj_0.digest

    # REMEDIATION_PENDING -> FIXED_ON_NEW_SOURCE
    adj_2 = transition_finding_lifecycle(
        current_decision=adj_1,
        target_status="FIXED_ON_NEW_SOURCE",
        adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
        input_history_cut=cut,
    )
    assert adj_2.lifecycle_status == "FIXED_ON_NEW_SOURCE"
    assert adj_2.previous_adjudication_decision_ref["revision_digest"] == adj_1.digest

    # Invalid transition: FIXED_ON_NEW_SOURCE directly to REMEDIATION_PENDING
    with pytest.raises(ValidationError, match="INVALID_LIFECYCLE_TRANSITION"):
        transition_finding_lifecycle(
            current_decision=adj_2,
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

    rc = cluster_findings_into_root_cause(
        source_generation_ref=src_gen,
        membership_edges=[edge2, edge1],
    )
    assert len(rc.membership_edges) == 2
    assert len(rc.digest) == 64

    # Duplicate edge rejection
    with pytest.raises(ValidationError, match="ROOT_CAUSE_MEMBERSHIP_DUPLICATE_OR_AMBIGUOUS"):
        cluster_findings_into_root_cause(
            source_generation_ref=src_gen,
            membership_edges=[edge1, edge1],
        )

    # Authority validation rejection
    with pytest.raises(ValidationError, match="SECOND_AUTHORITY_FOR_ROOT_CAUSE_MEMBERSHIP"):
        validate_root_cause_authority("RootCauseMembershipRevision")


def test_contradiction_resolution_and_majority_vote_forbidden():
    cut = {"tag": "TEST_CUT"}
    claim_ref = make_ref("finding_claim_revision", "c_contra")
    ev1 = make_ref("evidence_qualification_assessment", "ev_supports")
    ev2 = make_ref("evidence_qualification_assessment", "ev_refutes")

    contra = ContradictionRevision(
        claim_revision_ref=claim_ref,
        contradicting_evidence_refs=[ev1, ev2],
        input_history_cut=cut,
        status="OPEN",
    )
    assert contra.status == "OPEN"

    # Majority vote must fail closed
    with pytest.raises(ValidationError, match="MAJORITY_VOTE_FORBIDDEN"):
        resolve_contradiction(
            contradiction=contra,
            adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
            resolution_status="RESOLVED_FULL",
            rationale="2 votes against 1",
            input_history_cut=cut,
            resolved_by_majority_vote=True,
        )

    # Proper resolution
    res = resolve_contradiction(
        contradiction=contra,
        adjudicator_ref=make_ref("actor_or_authority_ref", "adjudicator_1"),
        resolution_status="RESOLVED_FULL",
        rationale="Controlled isolation proof verified vulnerability is unreproducible in production config",
        input_history_cut=cut,
    )
    assert res.resolution_status == "RESOLVED_FULL"
    assert len(res.digest) == 64

    # Reopening upon new counterevidence
    ev3 = make_ref("evidence_qualification_assessment", "ev_new_exploit")
    reopened = reopen_contradiction(
        prior_resolution=res,
        new_evidence_refs=[ev3],
        claim_revision_ref=claim_ref,
        input_history_cut=cut,
    )
    assert reopened.status == "REOPENED"
    assert len(reopened.digest) == 64

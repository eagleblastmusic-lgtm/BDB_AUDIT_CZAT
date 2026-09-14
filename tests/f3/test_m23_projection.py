"""Tests for M23 Derived Contribution Projection."""
import pytest
from bdb_audit.adjudication import (
    ProducerContribution,
    ContributionProjection,
    build_contribution_projection,
    validate_contribution_authority,
    RootCauseRevision,
)
from bdb_audit.core.errors import ValidationError


def _mock_ref(kind, revision_digest):
    return {
        "kind": kind,
        "revision_digest": revision_digest,
        "digest_profile": "BDB-CANONICAL-SHA256-1",
        "schema_revision_ref": {"schema_id": f"schema_{kind}"},
        "ref_class": "RECORDED",
    }


def test_m23_derived_contribution_unique_support_leave_one_out():
    """Test calculation of unique, support, and leave-one-out metrics."""
    history_cut = {"head_sequence": 10, "head_commit_digest": "commithash123"}

    # Producer 1 found f1, f2
    # Producer 2 found f2, f3
    # f1 is unique to P1 -> P1 unique=1, P1 leave_one_out_loss=1
    # f3 is unique to P2 -> P2 unique=1, P2 leave_one_out_loss=1
    # f2 is shared (P1 & P2) -> P1 support=1, P2 support=1

    f1 = _mock_ref("finding_claim_revision", "f1_digest")
    f2 = _mock_ref("finding_claim_revision", "f2_digest")
    f3 = _mock_ref("finding_claim_revision", "f3_digest")

    p1 = {"producer_id": "auditor_1", "kind": "attempt"}
    p2 = {"producer_id": "auditor_2", "kind": "attempt"}

    findings = [
        {"ref": f1, "producer_ref": p1},
        {"ref": f2, "producer_ref": p1},
        {"ref": f2, "producer_ref": p2},
        {"ref": f3, "producer_ref": p2},
    ]

    adj_confirmed = [
        {"claim_revision_ref": f1, "lifecycle_status": "CONFIRMED_CURRENT"},
        {"claim_revision_ref": f2, "lifecycle_status": "CONFIRMED_CURRENT"},
        {"claim_revision_ref": f3, "lifecycle_status": "CONFIRMED_CURRENT"},
    ]

    # Root cause covering f1 and f2
    rc1 = RootCauseRevision(
        root_cause_id="rc_1",
        root_cause_revision=1,
        source_generation_ref=_mock_ref("source_generation", "sg1"),
        mechanism_statement="Shared root-cause mechanism for f1 and f2",
        membership_edges=(
            {"finding_claim_revision_ref": f1, "relation_role": "PRIMARY", "scope": {"sub": "core"}},
            {"finding_claim_revision_ref": f2, "relation_role": "PRIMARY", "scope": {"sub": "core"}},
        ),
    )

    proj1 = build_contribution_projection(
        history_cut=history_cut,
        finding_claims=findings,
        adjudications=adj_confirmed,
        root_causes=[rc1],
    )

    assert proj1.is_projection is True
    assert proj1.reveal_order_marginal_contribution_is_not_objective_value is True
    assert proj1.total_findings == 3
    assert proj1.total_unique_findings == 2  # f1 and f3 are unique
    assert proj1.total_root_causes == 1

    c1 = proj1.producer_contributions["auditor_1"]
    c2 = proj1.producer_contributions["auditor_2"]

    assert c1.unique_contribution_count == 1
    assert c1.support_count == 1
    # rc1 is contributed to by both P1 (f1, f2) and P2 (f2). So removing P1 does NOT lose rc1 because P2 covers f2 in rc1.
    # Therefore P1 leave_one_out_loss is just f1 = 1.
    assert c1.leave_one_out_loss == 1
    assert c1.sound_contribution_count == 2

    assert c2.unique_contribution_count == 1
    assert c2.support_count == 1
    assert c2.leave_one_out_loss == 1
    assert c2.sound_contribution_count == 2


def test_m23_projection_rebuild_determinism_and_no_canonical_mutation():
    """Prove that rebuilding or deleting a projection yields identical results and does not mutate facts."""
    history_cut = {"head_sequence": 5, "head_commit_digest": "commithash999"}
    f1 = _mock_ref("finding_claim_revision", "f1_digest")
    p1 = {"producer_id": "auditor_1", "kind": "attempt"}
    findings = [{"ref": f1, "producer_ref": p1}]

    proj_a = build_contribution_projection(
        history_cut=history_cut,
        finding_claims=findings,
    )
    bytes_a = proj_a.to_bytes()

    # Rebuild
    proj_b = build_contribution_projection(
        history_cut=history_cut,
        finding_claims=findings,
    )
    bytes_b = proj_b.to_bytes()

    assert bytes_a == bytes_b
    assert proj_a.to_dict() == proj_b.to_dict()

    # Findings were not modified
    assert findings[0]["ref"]["revision_digest"] == "f1_digest"


def test_m23_reject_contribution_as_canonical_authority():
    """Reject attempts to introduce contribution as a canonical ledger authority."""
    with pytest.raises(ValidationError, match="SECOND_AUTHORITY_FOR_CONTRIBUTION"):
        validate_contribution_authority("contribution_ledger")

    with pytest.raises(ValidationError, match="SECOND_AUTHORITY_FOR_CONTRIBUTION"):
        validate_contribution_authority("mutable_contribution_ledger")

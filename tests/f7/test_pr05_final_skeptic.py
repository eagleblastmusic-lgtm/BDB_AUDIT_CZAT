"""Targeted tests for Final Skeptic Capability (PR-E5-05 / M40)."""
import pytest
from bdb_audit.attack.skeptic import (
    FalsePositiveSkepticCapability,
    SkepticCounterclaim,
)
from bdb_audit.core.errors import ValidationError


@pytest.fixture
def mock_candidate_ref():
    return {
        "kind": "candidate_assurance_case",
        "revision_digest": "c" * 64,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::candidate_assurance_case/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }


@pytest.fixture
def mock_finding_ref():
    return {
        "kind": "finding_claim_revision",
        "revision_digest": "f" * 64,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::finding_claim_revision/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }


def test_unsupported_causal_leap_challenge(mock_candidate_ref, mock_finding_ref):
    # Finding with empty/unsupported causal chain
    unsupported_chain = {"chain_id": "c1", "supporting_edges": []}
    res = FalsePositiveSkepticCapability.audit_for_unsupported_causal_leap(
        "cc_01", mock_finding_ref, mock_candidate_ref, unsupported_chain
    )
    assert res.status == "MATERIAL_COUNTEREVIDENCE_FOUND"
    assert res.challenge_type == "UNSUPPORTED_CAUSAL_LEAP"
    assert "UNSUPPORTED_CAUSAL_LEAP_DETECTED" in res.reason_codes

    # Supported causal chain
    supported_chain = {"chain_id": "c2", "supporting_edges": [{"edge_id": "e1"}]}
    res_ok = FalsePositiveSkepticCapability.audit_for_unsupported_causal_leap(
        "cc_02", mock_finding_ref, mock_candidate_ref, supported_chain
    )
    assert res_ok.status == "NO_MATERIAL_COUNTEREVIDENCE"


def test_alternative_explanation_challenge(mock_candidate_ref, mock_finding_ref):
    # Alternative explanation exists (e.g. environment jitter)
    env_evidence = {
        "kind": "environment_record",
        "revision_digest": "env_jitter",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    res = FalsePositiveSkepticCapability.audit_for_alternative_explanation(
        "cc_alt", mock_finding_ref, mock_candidate_ref, env_evidence
    )
    assert res.status == "MATERIAL_COUNTEREVIDENCE_FOUND"
    assert res.challenge_type == "ALTERNATIVE_EXPLANATION"
    assert len(res.counter_evidence_refs) == 1

    # No alternative explanation
    res_clean = FalsePositiveSkepticCapability.audit_for_alternative_explanation(
        "cc_clean", mock_finding_ref, mock_candidate_ref, None
    )
    assert res_clean.status == "NO_MATERIAL_COUNTEREVIDENCE"


def test_weak_oracle_detection(mock_candidate_ref, mock_finding_ref):
    # Oracle lacking qualification
    unqualified_oracle = {"is_qualified": False}
    res = FalsePositiveSkepticCapability.audit_for_weak_oracle(
        "cc_weak", mock_finding_ref, mock_candidate_ref, unqualified_oracle
    )
    assert res.status == "MATERIAL_COUNTEREVIDENCE_FOUND"
    assert res.challenge_type == "WEAK_ORACLE"

    # Qualified oracle
    qualified_oracle = {"is_qualified": True}
    res_ok = FalsePositiveSkepticCapability.audit_for_weak_oracle(
        "cc_qual", mock_finding_ref, mock_candidate_ref, qualified_oracle
    )
    assert res_ok.status == "NO_MATERIAL_COUNTEREVIDENCE"


def test_contradiction_detection(mock_candidate_ref, mock_finding_ref):
    contradicting_obs = {
        "kind": "observation",
        "revision_digest": "obs_contradic",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    res = FalsePositiveSkepticCapability.audit_for_contradiction(
        "cc_contra", mock_finding_ref, mock_candidate_ref, contradicting_obs
    )
    assert res.status == "MATERIAL_COUNTEREVIDENCE_FOUND"
    assert res.challenge_type == "CONTRADICTION"

    res_none = FalsePositiveSkepticCapability.audit_for_contradiction(
        "cc_no_contra", mock_finding_ref, mock_candidate_ref, None
    )
    assert res_none.status == "NO_MATERIAL_COUNTEREVIDENCE"


def test_skeptic_immutability_and_validation(mock_finding_ref):
    """Skeptic counterclaim must strictly bind candidate_assurance_case_ref and valid challenge types."""
    with pytest.raises(ValidationError, match="MISSING_CANDIDATE_REF"):
        SkepticCounterclaim(
            counterclaim_id="bad_cc",
            target_claim_ref=mock_finding_ref,
            candidate_assurance_case_ref={},  # Empty -> illegal!
            challenge_type="WEAK_ORACLE",
            status="NO_MATERIAL_COUNTEREVIDENCE",
            counter_evidence_refs=(),
            explanation="Invalid",
        )

    with pytest.raises(ValidationError, match="INVALID_CHALLENGE_TYPE"):
        SkepticCounterclaim(
            counterclaim_id="bad_type",
            target_claim_ref=mock_finding_ref,
            candidate_assurance_case_ref={"kind": "candidate_assurance_case"},
            challenge_type="BOGUS_CHALLENGE",
            status="NO_MATERIAL_COUNTEREVIDENCE",
            counter_evidence_refs=(),
            explanation="Invalid",
        )

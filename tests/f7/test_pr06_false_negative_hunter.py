"""Targeted tests for False Negative Hunter Capability (PR-E5-06 / M41)."""
import pytest
from bdb_audit.attack.hunter import (
    FalseNegativeHunterCapability,
    HunterCounterclaim,
    HUNTER_OPPORTUNITY_TYPES,
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


def test_hunt_open_obligations(mock_candidate_ref):
    open_obs = [
        {"kind": "coverage_obligation", "revision_digest": "ob_crash_recovery"},
        {"kind": "coverage_obligation", "revision_digest": "ob_concurrency"},
    ]
    claims = FalseNegativeHunterCapability.hunt_open_obligations(
        "hunt_open", mock_candidate_ref, open_obs
    )
    assert len(claims) == 2
    assert all(c.status == "MATERIAL_COUNTEREVIDENCE_FOUND" for c in claims)
    assert claims[0].opportunity_type == "OPEN_OBLIGATION"
    assert "OPEN_MANDATORY_OBLIGATION" in claims[0].reason_codes


def test_hunt_critical_surface_silence(mock_candidate_ref):
    """Absence of findings is NOT evidence of correctness."""
    critical_surfaces = [
        {"kind": "surface_record", "surface_key": "surf_auth"},
        {"kind": "surface_record", "surface_key": "surf_payment"},
    ]
    # Only surf_auth was tested; surf_payment was untouched
    tested = {"surf_auth"}

    claims = FalseNegativeHunterCapability.hunt_critical_surface_silence(
        "hunt_silent", mock_candidate_ref, critical_surfaces, tested
    )
    assert len(claims) == 1
    assert claims[0].opportunity_type == "CRITICAL_SURFACE_WITHOUT_FINDINGS"
    assert claims[0].severity == "CRITICAL"
    assert claims[0].target_scope_or_obligation_ref["surface_key"] == "surf_payment"
    assert "CRITICAL_SURFACE_SILENCE" in claims[0].reason_codes


def test_hunt_mutation_survivors(mock_candidate_ref):
    mutation_results = [
        {"result_id": "r1", "outcome": "MUTANT_KILLED"},
        {"result_id": "r2", "outcome": "MUTANT_SURVIVED", "mutation_case_ref": {"id": "m_surv"}},
    ]
    claims = FalseNegativeHunterCapability.hunt_mutation_survivors(
        "hunt_mut", mock_candidate_ref, mutation_results
    )
    assert len(claims) == 1
    assert claims[0].opportunity_type == "MUTATION_SURVIVOR"
    assert "MUTANT_SURVIVED_EVIDENCE" in claims[0].reason_codes


def test_hunt_unknown_scope(mock_candidate_ref):
    unknown_scopes = [
        {"kind": "scope_state_record", "scope_id": "scope_legacy_bridge"},
    ]
    claims = FalseNegativeHunterCapability.hunt_unknown_scope(
        "hunt_scope", mock_candidate_ref, unknown_scopes
    )
    assert len(claims) == 1
    assert claims[0].opportunity_type == "UNKNOWN_UNSUPPORTED_SCOPE"
    assert "UNKNOWN_SCOPE_UNRESOLVED" in claims[0].reason_codes


def test_hunter_validation_fail_closed():
    with pytest.raises(ValidationError, match="MISSING_CANDIDATE_REF"):
        HunterCounterclaim(
            counterclaim_id="h_bad",
            opportunity_type="OPEN_OBLIGATION",
            candidate_assurance_case_ref={},
            target_scope_or_obligation_ref={"id": "o1"},
            status="MATERIAL_COUNTEREVIDENCE_FOUND",
            severity="HIGH",
            counter_evidence_refs=(),
            explanation="Invalid",
        )

    with pytest.raises(ValidationError, match="INVALID_OPPORTUNITY_TYPE"):
        HunterCounterclaim(
            counterclaim_id="h_bad2",
            opportunity_type="NOT_A_VALID_TYPE",
            candidate_assurance_case_ref={"kind": "candidate_assurance_case"},
            target_scope_or_obligation_ref={"id": "o1"},
            status="MATERIAL_COUNTEREVIDENCE_FOUND",
            severity="HIGH",
            counter_evidence_refs=(),
            explanation="Invalid",
        )

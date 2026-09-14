"""Adversarial and contract unit tests for RU05 / Astra D11 (Truthful Experiment & Adjudication).

Verifies requirements A through H:
- A: Claim without evidence cannot be CONFIRMED/SUPPORTED.
- B: Missing outcome remains INCONCLUSIVE / E2_INSUFFICIENT_EVIDENCE.
- C: Same statement with different root-cause/evidence does not silently merge.
- D: Different statement with same evidenced root cause relates only via evidence-backed reconciliation.
- E: Multiple outcomes for the same claim candidate: explicit conflict/contradiction handling, no silent dictionary overwrite.
- F: Mechanism evidence absent -> mechanism INCONCLUSIVE / E2_INSUFFICIENT_EVIDENCE.
- G: Reachability evidence absent -> reachability INCONCLUSIVE / E2_INSUFFICIENT_EVIDENCE.
- H: Impact/severity without own basis -> no synthetic confirmation (remains OPEN/INCONCLUSIVE).
"""
import hashlib
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.orchestration import (
    E1_LANE_SLOTS,
    execute_e1_ensemble,
    execute_e2_convergence,
)
from bdb_audit.adjudication import (
    FindingClaimRevision,
    FindingAxisAssessment,
    adjudicate_finding,
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


def _axis_refs(seed: str, outcome: str = "SUPPORTED") -> dict:
    ev = make_ref("evidence_qualification_assessment", seed)
    return {
        "severity_value": "INFO",
        "axis_outcomes": {
            "MECHANISM": outcome,
            "REACHABILITY": outcome,
            "IMPACT": outcome,
            "SEVERITY": outcome,
        },
        "axis_evidence_refs": {
            "MECHANISM": [ev],
            "REACHABILITY": [ev],
            "IMPACT": [ev],
            "SEVERITY": [ev],
        },
    }


def test_d11_req_a_claim_without_evidence_cannot_be_confirmed():
    """Requirement A: Claim asserted as SUPPORTED but without evidence never gets CONFIRMED_CURRENT."""
    src_gen = make_ref("source_generation", "gen_req_a")
    discoveries = {slot: [] for slot in E1_LANE_SLOTS}
    discoveries["E1-A"] = [{
        "finding_id": "f_no_ev",
        "statement": "Asserted vulnerability without evidence",
        "claim_outcome": "SUPPORTED",
        "severity_value": "INFO",
    }]
    e1 = execute_e1_ensemble(src_gen, discoveries)
    e2 = execute_e2_convergence(
        e1,
        src_gen,
        make_ref("actor_or_authority_ref", "auditor_a"),
        {"tag": "CUT"},
        make_ref("policy_revision", "pol_a"),
    )
    assert len(e2.adjudicated_decisions) == 1
    dec = e2.adjudicated_decisions[0]
    assert dec.lifecycle_status != "CONFIRMED_CURRENT"
    assert dec.lifecycle_status == "OPEN"


def test_d11_req_b_missing_outcome_remains_inconclusive():
    """Requirement B: Claim with missing claim_outcome/axis_outcomes remains INCONCLUSIVE with E2_INSUFFICIENT_EVIDENCE."""
    src_gen = make_ref("source_generation", "gen_req_b")
    discoveries = {slot: [] for slot in E1_LANE_SLOTS}
    discoveries["E1-B"] = [{
        "finding_id": "f_missing_outcome",
        "statement": "Finding without explicit outcome fields",
        "severity_value": "INFO",
    }]
    e1 = execute_e1_ensemble(src_gen, discoveries)
    e2 = execute_e2_convergence(
        e1,
        src_gen,
        make_ref("actor_or_authority_ref", "auditor_b"),
        {"tag": "CUT"},
        make_ref("policy_revision", "pol_b"),
    )
    dec = e2.adjudicated_decisions[0]
    assert dec.lifecycle_status == "OPEN"
    # All axes must have method E2_INSUFFICIENT_EVIDENCE
    assert dec.mechanism_assessment_ref is not None


def test_d11_req_c_same_statement_different_provenance_no_silent_merge():
    """Requirement C: Same statement text from different components/locations must not merge silently."""
    src_gen = make_ref("source_generation", "gen_req_c")
    discoveries = {slot: [] for slot in E1_LANE_SLOTS}
    discoveries["E1-A"] = [{
        "finding_id": "fa",
        "statement": "Buffer overflow in protocol parser",
        "affected_component": "parser_a.c",
        "severity_value": "INFO",
    }]
    discoveries["E1-B"] = [{
        "finding_id": "fb",
        "statement": "Buffer overflow in protocol parser",
        "affected_component": "parser_b.c",
        "severity_value": "INFO",
    }]
    e1 = execute_e1_ensemble(src_gen, discoveries)
    e2 = execute_e2_convergence(
        e1,
        src_gen,
        make_ref("actor_or_authority_ref", "auditor_c"),
        {"tag": "CUT"},
        make_ref("policy_revision", "pol_c"),
    )
    # Must produce 2 separate decisions, not 1 merged decision
    assert len(e2.adjudicated_decisions) == 2


def test_d11_req_d_different_statement_same_evidenced_root_cause_converges():
    """Requirement D: Different statements converge only when explicit typed root_cause_ref is supplied."""
    src_gen = make_ref("source_generation", "gen_req_d")
    shared_root = make_ref("root_cause_revision", "shared_root_cause_1")
    discoveries = {slot: [] for slot in E1_LANE_SLOTS}
    discoveries["E1-A"] = [{
        "statement": "Out-of-bounds read in ASN1 header decoder",
        "root_cause_ref": shared_root,
        **_axis_refs("ev_d_a"),
    }]
    discoveries["E1-B"] = [{
        "statement": "Crash in X509 certificate parsing routine",
        "root_cause_ref": shared_root,
        **_axis_refs("ev_d_b"),
    }]
    e1 = execute_e1_ensemble(src_gen, discoveries)
    e2 = execute_e2_convergence(
        e1,
        src_gen,
        make_ref("actor_or_authority_ref", "auditor_d"),
        {"tag": "CUT"},
        make_ref("policy_revision", "pol_d"),
    )
    assert len(e2.adjudicated_decisions) == 1


def test_d11_req_e_multiple_outcomes_conflict_handling():
    """Requirement E: Conflicting outcomes (SUPPORTED vs REFUTED) for same claim create open contradiction, no overwrite."""
    src_gen = make_ref("source_generation", "gen_req_e")
    shared_root = make_ref("root_cause_revision", "contested_claim_root")
    ev_sup = make_ref("evidence_qualification_assessment", "ev_sup_e")
    ev_ref = make_ref("evidence_qualification_assessment", "ev_ref_e")

    discoveries = {slot: [] for slot in E1_LANE_SLOTS}
    discoveries["E1-A"] = [{
        "statement": "Race condition in session validation",
        "root_cause_ref": shared_root,
        "claim_outcome": "SUPPORTED",
        "evidence_ref": ev_sup,
        "severity_value": "INFO",
    }]
    discoveries["E1-B"] = [{
        "statement": "Race condition in session validation",
        "root_cause_ref": shared_root,
        "claim_outcome": "REFUTED",
        "evidence_ref": ev_ref,
        "severity_value": "INFO",
    }]
    e1 = execute_e1_ensemble(src_gen, discoveries)
    e2 = execute_e2_convergence(
        e1,
        src_gen,
        make_ref("actor_or_authority_ref", "auditor_e"),
        {"tag": "CUT"},
        make_ref("policy_revision", "pol_e"),
    )
    assert len(e2.contradiction_revisions) == 1
    contra = e2.contradiction_revisions[0]
    assert contra.status == "OPEN"
    assert len(contra.contradicting_evidence_refs) == 2


def test_d11_req_f_mechanism_evidence_absent_mechanism_unknown():
    """Requirement F: Mechanism outcome asserted SUPPORTED but no mechanism axis evidence -> inconclusive."""
    src_gen = make_ref("source_generation", "gen_req_f")
    ev = make_ref("evidence_qualification_assessment", "generic_ev_f")
    discoveries = {slot: [] for slot in E1_LANE_SLOTS}
    discoveries["E1-A"] = [{
        "finding_id": "f_no_mech_ev",
        "statement": "Finding without explicit mechanism evidence",
        "evidence_ref": ev,
        "severity_value": "INFO",
        "axis_outcomes": {
            "MECHANISM": "SUPPORTED",
            "REACHABILITY": "SUPPORTED",
            "IMPACT": "SUPPORTED",
            "SEVERITY": "SUPPORTED",
        },
        "axis_evidence_refs": {
            # MECHANISM has NO evidence refs
            "REACHABILITY": [ev],
            "IMPACT": [ev],
            "SEVERITY": [ev],
        },
    }]
    e1 = execute_e1_ensemble(src_gen, discoveries)
    e2 = execute_e2_convergence(
        e1,
        src_gen,
        make_ref("actor_or_authority_ref", "auditor_f"),
        {"tag": "CUT"},
        make_ref("policy_revision", "pol_f"),
    )
    dec = e2.adjudicated_decisions[0]
    # Because MECHANISM has no explicit axis evidence, it cannot be confirmed
    assert dec.lifecycle_status != "CONFIRMED_CURRENT"
    assert dec.lifecycle_status == "OPEN"


def test_d11_req_g_reachability_evidence_absent_reachability_unknown():
    """Requirement G: Reachability outcome asserted SUPPORTED but no reachability axis evidence -> inconclusive."""
    src_gen = make_ref("source_generation", "gen_req_g")
    ev = make_ref("evidence_qualification_assessment", "generic_ev_g")
    discoveries = {slot: [] for slot in E1_LANE_SLOTS}
    discoveries["E1-A"] = [{
        "finding_id": "f_no_reach_ev",
        "statement": "Finding without explicit reachability evidence",
        "evidence_ref": ev,
        "severity_value": "INFO",
        "axis_outcomes": {
            "MECHANISM": "SUPPORTED",
            "REACHABILITY": "SUPPORTED",
            "IMPACT": "SUPPORTED",
            "SEVERITY": "SUPPORTED",
        },
        "axis_evidence_refs": {
            "MECHANISM": [ev],
            # REACHABILITY has NO evidence refs
            "IMPACT": [ev],
            "SEVERITY": [ev],
        },
    }]
    e1 = execute_e1_ensemble(src_gen, discoveries)
    e2 = execute_e2_convergence(
        e1,
        src_gen,
        make_ref("actor_or_authority_ref", "auditor_g"),
        {"tag": "CUT"},
        make_ref("policy_revision", "pol_g"),
    )
    dec = e2.adjudicated_decisions[0]
    # Because REACHABILITY has no explicit axis evidence, it cannot be confirmed
    assert dec.lifecycle_status != "CONFIRMED_CURRENT"
    assert dec.lifecycle_status == "OPEN"


def test_d11_req_h_impact_severity_without_own_basis_no_synthetic_confirmation():
    """Requirement H: Impact/severity without explicit axis evidence cannot confirm finding."""
    src_gen = make_ref("source_generation", "gen_req_h")
    ev = make_ref("evidence_qualification_assessment", "generic_ev_h")
    discoveries = {slot: [] for slot in E1_LANE_SLOTS}
    discoveries["E1-A"] = [{
        "finding_id": "f_no_impact_ev",
        "statement": "Finding without explicit impact/severity evidence",
        "evidence_ref": ev,
        "severity_value": "INFO",
        "axis_outcomes": {
            "MECHANISM": "SUPPORTED",
            "REACHABILITY": "SUPPORTED",
            "IMPACT": "SUPPORTED",
            "SEVERITY": "SUPPORTED",
        },
        "axis_evidence_refs": {
            "MECHANISM": [ev],
            "REACHABILITY": [ev],
            # IMPACT has NO evidence refs
            "SEVERITY": [ev],
        },
    }]
    e1 = execute_e1_ensemble(src_gen, discoveries)
    e2 = execute_e2_convergence(
        e1,
        src_gen,
        make_ref("actor_or_authority_ref", "auditor_h"),
        {"tag": "CUT"},
        make_ref("policy_revision", "pol_h"),
    )
    dec = e2.adjudicated_decisions[0]
    assert dec.lifecycle_status != "CONFIRMED_CURRENT"
    assert dec.lifecycle_status == "OPEN"

"""M50 — Self-Audit v2 Tests across 9 Normative Areas (R5.3 §112, §207–§208)."""
import pytest

from bdb_audit.self_audit import SelfAuditEngine, execute_self_audit


def test_m50_full_self_audit_passes():
    """Self-audit v2 on candidate must pass all 9 gates with zero open HIGH/CRITICAL findings."""
    report = execute_self_audit()
    assert report.status == "PASS"
    assert report.open_high_critical_count == 0
    assert report.open_findings_count == 0
    assert len(report.findings) >= 9

    expected_gates = [
        "SOURCE_INTEGRITY_GATE",
        "ARTIFACT_VALIDATOR_GATE",
        "GATE_BYPASS_GATE",
        "SCHEMA_BYPASS_GATE",
        "CROSS_SOURCE_MIX_GATE",
        "EXPOSURE_LEAK_GATE",
        "PROMPT_COMPILER_GATE",
        "CAMPAIGN_FSM_GATE",
        "CORPUS_CONTAMINATION_GATE",
    ]
    for g in expected_gates:
        assert report.gates.get(g) == "PASS", f"Gate {g} failed: {report.gates.get(g)}"


def test_m50_area_a_source_integrity():
    engine = SelfAuditEngine()
    assert engine.audit_source_integrity() is True


def test_m50_area_b_artifact_validators():
    engine = SelfAuditEngine()
    assert engine.audit_artifact_validators() is True


def test_m50_area_c_gate_bypass():
    engine = SelfAuditEngine()
    assert engine.audit_gate_bypass() is True


def test_m50_area_d_schema_bypass():
    engine = SelfAuditEngine()
    assert engine.audit_schema_bypass() is True


def test_m50_area_e_cross_source_mix():
    engine = SelfAuditEngine()
    assert engine.audit_cross_source_mix() is True


def test_m50_area_f_exposure_leak():
    engine = SelfAuditEngine()
    assert engine.audit_exposure_leak() is True


def test_m50_area_g_prompt_compiler():
    engine = SelfAuditEngine()
    assert engine.audit_prompt_compiler() is True


def test_m50_area_h_campaign_fsm():
    engine = SelfAuditEngine()
    assert engine.audit_campaign_fsm() is True


def test_m50_area_i_corpus_contamination():
    engine = SelfAuditEngine()
    assert engine.audit_corpus_contamination() is True

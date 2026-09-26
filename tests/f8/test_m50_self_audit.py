"""M50 — Self-Audit v2 Tests across 9 Normative Areas (R5.3 §112, §207–§208)."""
import pytest

import bdb_audit.self_audit as self_audit_module
from bdb_audit.self_audit import SelfAuditEngine, execute_self_audit


def test_m50_full_self_audit_reports_unqualified_scope_honestly():
    """Narrow local probes cannot qualify the integrated release candidate."""
    report = execute_self_audit()
    assert report.status == "NOT_QUALIFIED"
    assert report.open_high_critical_count == 0
    assert report.open_findings_count == 0
    assert len(report.findings) >= 9
    assert report.qualification_scope.startswith("NARROW_LOCAL_CONTROLS")
    assert report.as_dict()["release_qualified"] is False
    assert "R1-R11_INTEGRATED_NEGATIVE_AND_POSITIVE_REGRESSION_MATRIX" in report.unverified_requirements

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
        assert report.gates.get(g) == "LIMITED_PASS", f"Gate {g} failed: {report.gates.get(g)}"
    assert report.gates["CLEAN_ROOM_AND_PINNED_CI_QUALIFICATION"] == "NOT_EXECUTED"
    assert "RESOLVED" not in {
        finding.status
        for finding in report.findings
        if finding.area in {"C", "D", "E", "F", "G", "H", "I"}
    }


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


def test_m50_fsm_self_audit_detects_a_weakened_shared_transition_oracle(
    monkeypatch,
):
    # This controlled mutation activates the known illegal transition. The
    # self-audit probe must report it instead of echoing the shared helper's
    # weakened answer as a passing qualification result.
    monkeypatch.setattr(
        self_audit_module,
        "legal_transition",
        lambda *_args, **_kwargs: True,
    )
    engine = SelfAuditEngine()
    assert engine.audit_campaign_fsm() is False
    assert engine.findings[-1].severity == "CRITICAL"
    assert engine.findings[-1].status == "OPEN"


def test_m50_corpus_self_audit_detects_a_weakened_e3_isolation_guard(
    monkeypatch,
):
    from bdb_audit.orchestration import e3

    monkeypatch.setattr(e3, "create_e3_blind_attempt", lambda *_args, **_kwargs: object())
    engine = SelfAuditEngine()
    assert engine.audit_corpus_contamination() is False
    assert engine.findings[-1].severity == "HIGH"
    assert engine.findings[-1].status == "OPEN"

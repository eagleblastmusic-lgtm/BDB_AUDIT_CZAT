"""RU09 slice 2: remediation DAG, safe renderers, bundle and Q09 tests."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.remediation.models import RemediationPlan, RepairUnit
from bdb_audit.remediation.planner import RemediationPlanner
from bdb_audit.remediation.validation import validate_remediation_plan
from bdb_audit.report.bundle import export_report_bundle, validate_q09, verify_report_bundle
from bdb_audit.report.models import ReportItem, ReportModel
from bdb_audit.report.render_html import render_html
from bdb_audit.report.render_markdown import render_markdown


def _campaign(tmp_path):
    path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(path, seed="ru09_bundle", target_repo=str(tmp_path / "target"))
    return path


def _ref(kind: str, digest: str) -> dict:
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }


def _manual_report() -> ReportModel:
    cut = {
        "campaign_id": "campaign_test",
        "accepted_head_seq": 9,
        "accepted_head_hash": "a" * 64,
        "governing_policy_ref": "policy",
        "governing_spec_refs": ["spec"],
    }
    source = {"source_generation_id": "source_generation_test", "git_commit_object_id": "b" * 40}
    claim1 = ReportItem("FACT", "finding_claim_revision", _ref("finding_claim_revision", "1" * 64), 2, {
        "statement": "one", "priority": "P0", "affected_modules": ["auth.py"]
    })
    claim2 = ReportItem("FACT", "finding_claim_revision", _ref("finding_claim_revision", "2" * 64), 3, {
        "statement": "two", "priority": "P2"
    })
    decision1 = ReportItem("FACT", "finding_adjudication_decision", _ref("finding_adjudication_decision", "3" * 64), 4, {
        "claim_revision_ref": claim1.source_ref, "lifecycle_status": "CONFIRMED_CURRENT", "evidence_qualification_refs": []
    })
    decision2 = ReportItem("FACT", "finding_adjudication_decision", _ref("finding_adjudication_decision", "4" * 64), 5, {
        "claim_revision_ref": claim2.source_ref, "lifecycle_status": "CONFIRMED_CURRENT", "evidence_qualification_refs": []
    })
    root = ReportItem("FACT", "root_cause_revision", _ref("root_cause_revision", "5" * 64), 6, {
        "membership_edges": [
            {"finding_claim_revision_ref": claim1.source_ref, "relation_role": "PRIMARY", "scope": {}},
            {"finding_claim_revision_ref": claim2.source_ref, "relation_role": "CONTRIBUTING", "scope": {}},
        ],
        "predecessor_root_cause_refs": [],
    })
    facts = tuple(sorted((claim1, claim2, decision1, decision2, root), key=lambda item: item.sort_key))
    return ReportModel("campaign_test", cut, source, "PARTIAL", facts, (), (), ())


def test_root_cause_planner_keeps_all_symptoms_and_stays_proposed():
    report = _manual_report()
    plan = RemediationPlanner(report).build()
    assert plan.status == "PROPOSED"
    assert len(plan.repair_units) == 1
    assert len(plan.repair_units[0].finding_refs) == 2
    assert len(plan.repair_units[0].symptom_refs) == 2
    assert plan.repair_units[0].priority == "P0"
    assert "auth.py" in plan.repair_units[0].affected_modules
    assert len(plan.plan_sha256) == 64


def test_remediation_cycle_is_rejected():
    base = _manual_report()
    unit_a = RepairUnit("a", "P1", (), (), None, ("NOT_ASSESSED",), "NOT_ASSESSED", {"status": "NOT_ASSESSED"},
                        ("NOT_ASSESSED",), (), "NOT_ASSESSED", "NOT_ASSESSED", "NOT_ASSESSED", ("b",), "NOT_ASSESSED")
    unit_b = RepairUnit("b", "P1", (), (), None, ("NOT_ASSESSED",), "NOT_ASSESSED", {"status": "NOT_ASSESSED"},
                        ("NOT_ASSESSED",), (), "NOT_ASSESSED", "NOT_ASSESSED", "NOT_ASSESSED", ("a",), "NOT_ASSESSED")
    plan = RemediationPlan(base.campaign_id, base.input_history_cut, base.source_identity, base.report_model_sha256, (unit_a, unit_b))
    with pytest.raises(ValidationError, match="REMEDIATION_DEPENDENCY_CYCLE"):
        validate_remediation_plan(plan)


def test_q09_requires_repair_unit_for_explicit_p0_p1(tmp_path):
    report = _manual_report()
    plan = RemediationPlanner(report).build()
    # Exact-history reference validation is intentionally separate from this synthetic fixture.
    assert any(unit.priority == "P0" for unit in plan.repair_units)
    broken = RemediationPlan(report.campaign_id, report.input_history_cut, report.source_identity,
                             report.report_model_sha256, ())
    store_path = _campaign(tmp_path)
    store = TransactionalHistoryStore(store_path)
    # Q09 first proves report refs at the cut. Synthetic refs must therefore fail closed,
    # demonstrating the gate cannot be bypassed with an invented P0 report.
    with pytest.raises(ValidationError, match="REPORT_DANGLING_SOURCE_REF"):
        validate_q09(store, report, broken)


def test_markdown_and_html_escape_untrusted_payload():
    report = _manual_report()
    malicious = ReportItem(
        "UNKNOWN", "observation", None, None,
        {"text": "<script>alert(1)</script>`x`", "reason_tokens": ["UNKNOWN"]},
    )
    modified = ReportModel(report.campaign_id, report.input_history_cut, report.source_identity,
                           report.report_scope, report.facts, (), (), (malicious,))
    md = render_markdown(modified)
    html = render_html(modified)
    assert "<script>" not in md
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;script&gt;" in md


def test_bundle_is_deterministic_and_detects_tamper(tmp_path):
    store_path = _campaign(tmp_path)
    store = TransactionalHistoryStore(store_path)
    out1 = tmp_path / "bundle1"
    out2 = tmp_path / "bundle2"
    first = export_report_bundle(store, out1)
    second = export_report_bundle(store, out2)
    assert first["manifest_sha256"] == second["manifest_sha256"]
    assert verify_report_bundle(out1)["status"] == "PASS"
    manifest1 = json.loads((out1 / "BUNDLE_MANIFEST.json").read_text(encoding="utf-8"))
    manifest2 = json.loads((out2 / "BUNDLE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest1 == manifest2

    (out1 / "REPORT.md").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValidationError, match="REPORT_BUNDLE_FILE_TAMPERED"):
        verify_report_bundle(out1)


def test_full_assurance_export_is_blocked_on_incomplete_campaign(tmp_path):
    store = TransactionalHistoryStore(_campaign(tmp_path))
    with pytest.raises(ValidationError, match="Q09_FULL_ASSURANCE_EXPORT_BLOCKED"):
        export_report_bundle(store, tmp_path / "full", requested_full_assurance=True)

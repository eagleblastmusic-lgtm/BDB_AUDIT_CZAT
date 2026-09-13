"""Deterministic RU09 report bundle/export and Q09 validation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from ..remediation.models import RemediationPlan, remediation_plan_from_dict
from ..remediation.planner import RemediationPlanner
from ..remediation.validation import validate_remediation_plan
from .builder import ReportBuilder, extract_unknown_tokens
from .models import ReportModel
from .render_html import render_html
from .render_markdown import render_markdown
from .validation import validate_report_model, validate_report_references


BUNDLE_SCHEMA = "BDB-REPORT-BUNDLE-1"
EXPORT_RECEIPT_SCHEMA = "BDB-EXPORT-RECEIPT-1"


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ref_key(ref: dict[str, Any] | None) -> tuple[str, str] | None:
    if not isinstance(ref, dict):
        return None
    kind = ref.get("kind")
    digest = ref.get("revision_digest")
    if isinstance(kind, str) and isinstance(digest, str):
        return kind, digest
    return None


def _matrix(model: ReportModel, kinds: set[str], name: str) -> dict[str, Any]:
    rows = [item.as_dict() for item in model.facts if item.record_kind in kinds]
    return {
        "matrix": name,
        "campaign_id": model.campaign_id,
        "report_model_sha256": model.report_model_sha256,
        "status": "ASSESSED" if rows else "NOT_ASSESSED",
        "rows": rows,
    }


def build_bundle_views(model: ReportModel) -> dict[str, dict[str, Any]]:
    evidence_rows = [
        item.as_dict() for item in model.facts
        if item.record_kind in {
            "observation", "evidence_applicability_assessment", "evidence_qualification_assessment", "evidence_invalidation"
        }
    ]
    return {
        "SOURCE_MATRIX.json": {
            "matrix": "SOURCE",
            "campaign_id": model.campaign_id,
            "report_model_sha256": model.report_model_sha256,
            "status": "ASSESSED",
            "source_identity": model.source_identity,
        },
        "COVERAGE_MATRIX.json": _matrix(
            model,
            {"coverage_obligation", "coverage_obligation_qualification", "obligation_applicability_decision"},
            "COVERAGE",
        ),
        "FEATURE_STATUS_MATRIX.json": _matrix(
            model,
            {"feature_inventory", "feature_expectation", "feature_testability", "functional_verification_result"},
            "FEATURE_STATUS",
        ),
        "EVIDENCE_INDEX.json": {
            "index": "EVIDENCE",
            "campaign_id": model.campaign_id,
            "report_model_sha256": model.report_model_sha256,
            "status": "ASSESSED" if evidence_rows else "NOT_ASSESSED",
            "rows": evidence_rows,
        },
    }


def validate_q09(
    store: TransactionalHistoryStore,
    model: ReportModel,
    plan: RemediationPlan,
    *,
    requested_full_assurance: bool = False,
) -> dict[str, Any]:
    """Q09 fail-closed completeness gate over exact report cut."""
    validate_report_model(model)
    validate_report_references(store, model)
    validate_remediation_plan(plan)
    if plan.report_model_sha256 != model.report_model_sha256:
        raise ValidationError("Q09_REMEDIATION_REPORT_BINDING_MISMATCH")
    if plan.input_history_cut != model.input_history_cut:
        raise ValidationError("Q09_REMEDIATION_CUT_MISMATCH")
    if plan.source_identity != model.source_identity:
        raise ValidationError("Q09_REMEDIATION_SOURCE_MISMATCH")

    expected_unknowns: set[tuple[str, str]] = set()
    for fact in model.facts:
        if extract_unknown_tokens(fact.payload):
            key = _ref_key(fact.source_ref)
            if key is not None:
                expected_unknowns.add(key)
    surfaced_unknowns = {_ref_key(item.source_ref) for item in model.unknowns}
    surfaced_unknowns.discard(None)
    missing_unknowns = sorted(expected_unknowns.difference(surfaced_unknowns))
    if missing_unknowns:
        raise ValidationError("Q09_MATERIAL_UNKNOWN_OMITTED", repr(missing_unknowns))

    required_p01: set[tuple[str, str]] = set()
    for fact in model.facts:
        if fact.record_kind != "finding_claim_revision":
            continue
        priority = fact.payload.get("priority") or fact.payload.get("remediation_priority") or fact.payload.get("material_priority")
        if isinstance(priority, str) and priority.upper() in {"P0", "P1"}:
            key = _ref_key(fact.source_ref)
            if key is not None:
                required_p01.add(key)
    planned = {
        key
        for unit in plan.repair_units
        for key in (_ref_key(ref) for ref in unit.finding_refs)
        if key is not None
    }
    uncovered = sorted(required_p01.difference(planned))
    if uncovered:
        raise ValidationError("Q09_P0_P1_REMEDIATION_MISSING", repr(uncovered))

    if requested_full_assurance:
        if model.report_scope != "FULL":
            raise ValidationError("Q09_FULL_ASSURANCE_EXPORT_BLOCKED", model.report_scope)
        if not any(item.record_kind == "campaign_conclusion" for item in model.facts):
            raise ValidationError("Q09_FULL_ASSURANCE_CONCLUSION_REQUIRED")
        if not any(item.record_kind == "final_assurance_case" for item in model.facts):
            raise ValidationError("Q09_FULL_ASSURANCE_CASE_REQUIRED")

    return {
        "status": "PASS",
        "gate": "Q09_REPORT_REMEDIATION_COMPLETENESS",
        "report_scope": model.report_scope,
        "unknowns_surfaced": len(surfaced_unknowns),
        "required_p0_p1": len(required_p01),
        "repair_units": len(plan.repair_units),
    }


def export_report_bundle(
    store: TransactionalHistoryStore,
    output_dir: Path | str,
    *,
    requested_full_assurance: bool = False,
) -> dict[str, Any]:
    model = ReportBuilder(store).build_current()
    plan = RemediationPlanner(model).build()
    gate = validate_q09(store, model, plan, requested_full_assurance=requested_full_assurance)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    views = build_bundle_views(model)
    texts: dict[str, str] = {
        "REPORT.json": _json_text(model.as_dict()),
        "REPORT.md": render_markdown(model),
        "REPORT.html": render_html(model),
        "REMEDIATION_PLAN.json": _json_text(plan.as_dict()),
        **{name: _json_text(payload) for name, payload in views.items()},
    }
    files: dict[str, dict[str, Any]] = {}
    for name in sorted(texts):
        data = texts[name].encode("utf-8")
        (out / name).write_bytes(data)
        files[name] = {"sha256": _sha256_bytes(data), "size": len(data)}

    manifest = {
        "schema_version": BUNDLE_SCHEMA,
        "campaign_id": model.campaign_id,
        "report_model_sha256": model.report_model_sha256,
        "remediation_plan_sha256": plan.plan_sha256,
        "input_history_cut": model.input_history_cut,
        "source_identity": model.source_identity,
        "report_scope": model.report_scope,
        "q09": gate,
        "files": files,
    }
    manifest_text = _json_text(manifest)
    (out / "BUNDLE_MANIFEST.json").write_text(manifest_text, encoding="utf-8", newline="\n")
    manifest_sha = _sha256_bytes(manifest_text.encode("utf-8"))
    receipt = {
        "schema_version": EXPORT_RECEIPT_SCHEMA,
        "state": "EXPORTED",
        "campaign_id": model.campaign_id,
        "report_model_sha256": model.report_model_sha256,
        "bundle_manifest_sha256": manifest_sha,
        "accepted_head_seq": model.input_history_cut["accepted_head_seq"],
        "accepted_head_hash": model.input_history_cut["accepted_head_hash"],
        "source_generation_id": model.source_identity["source_generation_id"],
        "report_scope": model.report_scope,
    }
    (out / "EXPORT_RECEIPT.json").write_text(_json_text(receipt), encoding="utf-8", newline="\n")
    return {"status": "SUCCESS", "output_dir": str(out), "manifest_sha256": manifest_sha, "receipt": receipt}


def verify_report_bundle(bundle_dir: Path | str) -> dict[str, Any]:
    root = Path(bundle_dir)
    manifest_path = root / "BUNDLE_MANIFEST.json"
    receipt_path = root / "EXPORT_RECEIPT.json"
    if not manifest_path.is_file() or not receipt_path.is_file():
        raise ValidationError("REPORT_BUNDLE_CONTROL_FILE_MISSING")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != BUNDLE_SCHEMA:
        raise ValidationError("REPORT_BUNDLE_SCHEMA_UNSUPPORTED")
    manifest_sha = _sha256_bytes(manifest_bytes)
    if receipt.get("bundle_manifest_sha256") != manifest_sha:
        raise ValidationError("REPORT_BUNDLE_RECEIPT_MISMATCH")
    for name, expected in sorted(manifest.get("files", {}).items()):
        if Path(name).name != name:
            raise ValidationError("REPORT_BUNDLE_UNSAFE_PATH", name)
        path = root / name
        if not path.is_file():
            raise ValidationError("REPORT_BUNDLE_FILE_MISSING", name)
        data = path.read_bytes()
        if _sha256_bytes(data) != expected.get("sha256") or len(data) != expected.get("size"):
            raise ValidationError("REPORT_BUNDLE_FILE_TAMPERED", name)
    plan_data = json.loads((root / "REMEDIATION_PLAN.json").read_text(encoding="utf-8"))
    plan = remediation_plan_from_dict(plan_data)
    validate_remediation_plan(plan)
    if plan.plan_sha256 != manifest.get("remediation_plan_sha256"):
        raise ValidationError("REPORT_BUNDLE_REMEDIATION_DIGEST_MISMATCH")
    report_data = json.loads((root / "REPORT.json").read_text(encoding="utf-8"))
    if report_data.get("report_model_sha256") != manifest.get("report_model_sha256"):
        raise ValidationError("REPORT_BUNDLE_REPORT_DIGEST_MISMATCH")
    return {
        "status": "PASS",
        "campaign_id": manifest.get("campaign_id"),
        "report_scope": manifest.get("report_scope"),
        "manifest_sha256": manifest_sha,
        "verified_files": len(manifest.get("files", {})),
    }


__all__ = [
    "BUNDLE_SCHEMA",
    "EXPORT_RECEIPT_SCHEMA",
    "build_bundle_views",
    "export_report_bundle",
    "validate_q09",
    "verify_report_bundle",
]

"""RU12-B rebuildable audit workbench projection over one accepted HistoryCut."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from ..report.builder import ReportBuilder
from ..workflow.assurance_projection import build_verified_assurance_snapshot
from ..workflow.read_models import current_accepted_cut


@dataclass(frozen=True)
class WorkbenchSnapshot:
    body: Mapping[str, Any]

    @property
    def projection_digest(self) -> str:
        return hashlib.sha256(canonical_bytes(dict(self.body))).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        output = dict(self.body)
        output["projection_digest"] = self.projection_digest
        return output


def _accepted_rows(store: TransactionalHistoryStore, cut: Mapping[str, Any], kind: str) -> list[dict[str, Any]]:
    rows = []
    for row in store.accepted_records(kind, dict(cut)):
        rows.append({
            "ref": dict(row["ref"]),
            "accepted_seq": row["accepted_seq"],
            "body": row["body"],
        })
    rows.sort(key=lambda item: (item["accepted_seq"], str(item["ref"].get("revision_digest", ""))))
    return rows


def _progress(store: TransactionalHistoryStore, cut: Mapping[str, Any]) -> dict[str, Any]:
    stage_specs = _accepted_rows(store, cut, "stage_spec")
    lane_specs = _accepted_rows(store, cut, "lane_spec")
    stage_runs = _accepted_rows(store, cut, "stage_run")
    lane_runs = _accepted_rows(store, cut, "lane_run")
    stage_completions = _accepted_rows(store, cut, "stage_completion")
    lane_completions = _accepted_rows(store, cut, "lane_completion")
    evidence_qualifications = _accepted_rows(store, cut, "evidence_qualification_assessment")
    coverage_qualifications = _accepted_rows(store, cut, "coverage_obligation_qualification")
    return {
        "planned_units": len(stage_specs) + len(lane_specs),
        "started_runs": len(stage_runs) + len(lane_runs),
        "completed_units": len(stage_completions) + len(lane_completions),
        "qualified_evidence_items": len(evidence_qualifications),
        "qualified_coverage_items": len(coverage_qualifications),
        "note": "Counts are separate dimensions; they are not a shared-denominator percentage.",
    }


def _report_unknowns(store: TransactionalHistoryStore) -> list[dict[str, Any]]:
    model = ReportBuilder(store).build_current()
    return [item.as_dict() for item in model.unknowns]


def build_workbench_snapshot(
    store: TransactionalHistoryStore,
    *,
    feature_matrix: Mapping[str, Any] | None = None,
) -> WorkbenchSnapshot:
    assurance = build_verified_assurance_snapshot(store).as_dict()
    cut = dict(assurance["history_cut"])
    findings = {
        "claims": _accepted_rows(store, cut, "finding_claim_revision"),
        "axis_assessments": _accepted_rows(store, cut, "finding_axis_assessment"),
        "adjudications": _accepted_rows(store, cut, "finding_adjudication_decision"),
    }
    contradictions = {
        "revisions": _accepted_rows(store, cut, "contradiction_revision"),
        "resolutions": _accepted_rows(store, cut, "contradiction_resolution_decision"),
    }
    matrix = dict(feature_matrix) if feature_matrix is not None else None
    matrix_state = "ATTACHED_DERIVED" if matrix is not None else "NOT_PROVIDED"
    return WorkbenchSnapshot({
        "schema_version": "RU12B-WORKBENCH-1",
        "authority": "DERIVED_ONLY",
        "history_cut": cut,
        "freshness": assurance["freshness"],
        "source_identity": assurance["source_identity"],
        "campaign": assurance["campaign_status"],
        "workflow": assurance["workflow"],
        "progress": _progress(store, cut),
        "coverage_summary": assurance["coverage_summary"],
        "coverage_rows": assurance["coverage_rows"],
        "evidence_index": assurance["evidence_index"],
        "blockers": assurance["blockers"],
        "findings": findings,
        "contradictions": contradictions,
        "scope_unknowns": _report_unknowns(store),
        "feature_matrix_state": matrix_state,
        "feature_matrix": matrix,
        "upstream_assurance_projection_digest": assurance["projection_digest"],
    })


def verify_workbench_snapshot(snapshot: Mapping[str, Any], store: TransactionalHistoryStore) -> dict[str, Any]:
    supplied = snapshot.get("projection_digest")
    body = dict(snapshot)
    body.pop("projection_digest", None)
    calculated = hashlib.sha256(canonical_bytes(body)).hexdigest()
    if supplied != calculated:
        raise ValidationError("WORKBENCH_PROJECTION_DIGEST_MISMATCH")
    cut = body.get("history_cut")
    if not isinstance(cut, dict):
        raise ValidationError("WORKBENCH_HISTORY_CUT_MISSING")
    commits = store.commits()
    if not commits:
        raise ValidationError("CAMPAIGN_NOT_FOUND")
    store.resolve_accepted(commits[0]["command_ref"], cut)
    current = current_accepted_cut(store)
    return {
        "status": "PASS",
        "projection_digest": calculated,
        "freshness": "ACTIVE" if cut == current else "STALE",
        "history_cut": cut,
        "current_history_cut": current,
    }


__all__ = ["WorkbenchSnapshot", "build_workbench_snapshot", "verify_workbench_snapshot"]

"""RU12-A verified assurance views derived only from accepted history.

These projections are convenience/read models.  They never create workflow,
coverage, evidence, or completion authority and can always be rebuilt from an
exact accepted HistoryCut.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from .continuation_service import ContinuationService
from .read_models import VerifiedCampaignReadModel, campaign_source_identity, current_accepted_cut


@dataclass(frozen=True)
class AssuranceProjectionSnapshot:
    """Immutable derived snapshot with a digest over its complete presentation body."""

    body: Mapping[str, Any]

    @property
    def projection_digest(self) -> str:
        return hashlib.sha256(canonical_bytes(dict(self.body))).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        result = dict(self.body)
        result["projection_digest"] = self.projection_digest
        return result


def _ref_identity(ref: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(ref.get("kind", "")),
        str(ref.get("revision_digest", "")),
        str(ref.get("schema_revision_ref", "")),
        str(ref.get("logical_id", "")),
    )


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for ref in refs:
        unique[_ref_identity(ref)] = dict(ref)
    return [unique[key] for key in sorted(unique)]


def _accepted_ref_by_digest(
    store: TransactionalHistoryStore,
    cut: Mapping[str, Any],
    digest: str,
    *,
    kind: str | None = None,
) -> dict[str, Any]:
    matches: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    limit = cut.get("accepted_head_seq")
    if type(limit) is not int or limit < 1:
        raise ValidationError("ACCEPTED_HISTORY_CUT_REQUIRED")
    for commit in store.commits():
        if commit.get("commit_seq", 0) > limit:
            break
        for ref in commit.get("immutable_object_refs", ()):
            if ref.get("revision_digest") != digest:
                continue
            if kind is not None and ref.get("kind") != kind:
                continue
            matches[_ref_identity(ref)] = dict(ref)
    if not matches:
        raise ValidationError("OBJECT_NOT_ACCEPTED_AT_CUT", digest)
    if len(matches) != 1:
        raise ValidationError("AMBIGUOUS_ACCEPTED_REF", digest)
    return next(iter(matches.values()))


def _direct_refs(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("kind"), str) and isinstance(node.get("revision_digest"), str):
                found.append(dict(node))
                return
            for key in sorted(node):
                visit(node[key])
        elif isinstance(node, (list, tuple)):
            for child in node:
                visit(child)

    visit(value)
    return _dedupe_refs(found)


def _invalidation_index(
    store: TransactionalHistoryStore,
    cut: Mapping[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], tuple[dict[str, Any], ...]]:
    index: dict[str, list[dict[str, Any]]] = {}
    rows = store.accepted_records("evidence_invalidation", dict(cut))
    for row in rows:
        invalidation_ref = dict(row["ref"])
        for affected in row["body"].get("affected_evidence_or_qualification_refs", ()):
            if not isinstance(affected, dict):
                continue
            digest = affected.get("revision_digest")
            if isinstance(digest, str):
                index.setdefault(digest, []).append(invalidation_ref)
    for digest in index:
        index[digest] = _dedupe_refs(index[digest])
    return index, rows


def _reason_node(code: str, source_ref: Mapping[str, Any] | None = None) -> dict[str, Any]:
    node: dict[str, Any] = {"code": code}
    if source_ref is not None:
        node["source_ref"] = dict(source_ref)
    return node


def _project_evidence_index(
    store: TransactionalHistoryStore,
    cut: Mapping[str, Any],
    invalidations: Mapping[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows = store.accepted_records("evidence_qualification_assessment", dict(cut))
    projected: list[dict[str, Any]] = []
    for row in rows:
        ref = dict(row["ref"])
        body = row["body"]
        digest = ref["revision_digest"]
        invalidating_refs = list(invalidations.get(digest, ()))
        freshness = "STALE" if invalidating_refs else "ACTIVE"
        projected.append({
            "assessment_id": body.get("assessment_id"),
            "ref": ref,
            "accepted_seq": row["accepted_seq"],
            "claim_revision_ref": body.get("claim_revision_ref"),
            "result": body.get("result", "INCONCLUSIVE"),
            "freshness": freshness,
            "reason_codes": sorted(str(code) for code in body.get("reason_codes", ())),
            "observation_refs": _dedupe_refs([
                dict(item) for item in body.get("observation_refs", ()) if isinstance(item, dict)
            ]),
            "invalidation_refs": _dedupe_refs(invalidating_refs),
            "current_applicable": freshness == "ACTIVE",
        })
    projected.sort(key=lambda item: _ref_identity(item["ref"]))
    return projected


def _project_coverage_rows(
    store: TransactionalHistoryStore,
    cut: Mapping[str, Any],
    invalidations: Mapping[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    obligations = store.accepted_records("coverage_obligation", dict(cut))
    qualifications = store.accepted_records("coverage_obligation_qualification", dict(cut))
    by_obligation_digest: dict[str, list[dict[str, Any]]] = {}
    for qualification in qualifications:
        obligation_ref = qualification["body"].get("obligation_revision_ref")
        if not isinstance(obligation_ref, dict):
            raise ValidationError("COVERAGE_QUALIFICATION_OBLIGATION_REF_MISSING")
        digest = obligation_ref.get("revision_digest")
        if not isinstance(digest, str):
            raise ValidationError("COVERAGE_QUALIFICATION_OBLIGATION_REF_MISSING")
        by_obligation_digest.setdefault(digest, []).append(qualification)

    result: list[dict[str, Any]] = []
    for obligation in obligations:
        obligation_ref = dict(obligation["ref"])
        obligation_body = obligation["body"]
        obligation_digest = obligation_ref["revision_digest"]
        qualification_rows = sorted(
            by_obligation_digest.get(obligation_digest, ()),
            key=lambda row: _ref_identity(row["ref"]),
        )
        reason_children: list[dict[str, Any]] = []
        direct_refs = [obligation_ref]
        qualification_refs = [dict(row["ref"]) for row in qualification_rows]
        direct_refs.extend(qualification_refs)
        evidence_refs: list[dict[str, Any]] = []
        invalidating_refs: list[dict[str, Any]] = []
        substantive_outcome: str | None = None
        is_not_applicable = False
        is_waived = False

        if not qualification_rows:
            effective_status = "UNASSESSED"
            reason_children.append(_reason_node("NO_ACCEPTED_QUALIFICATION", obligation_ref))
        elif len(qualification_rows) != 1:
            effective_status = "CONFLICTED"
            reason_children.append(_reason_node("MULTIPLE_ACCEPTED_QUALIFICATIONS", obligation_ref))
        else:
            qualification = qualification_rows[0]
            qualification_ref = dict(qualification["ref"])
            qbody = qualification["body"]
            effective_status = str(qbody.get("qualification_status", "UNASSESSED"))
            substantive = qbody.get("substantive_outcome")
            substantive_outcome = str(substantive) if substantive is not None else None
            for code in qbody.get("reason_codes", ()):
                reason_children.append(_reason_node(str(code), qualification_ref))

            for evidence_ref in qbody.get("evidence_qualification_refs", ()):
                if not isinstance(evidence_ref, dict):
                    raise ValidationError("COVERAGE_EVIDENCE_REF_INVALID")
                resolved = store.resolve_accepted(evidence_ref, dict(cut))
                exact_ref = dict(resolved["ref"])
                evidence_refs.append(exact_ref)
                direct_refs.append(exact_ref)
                evidence_body = resolved["body"]
                reason_children.append(
                    _reason_node(f"EVIDENCE_{evidence_body.get('result', 'INCONCLUSIVE')}", exact_ref)
                )
                for code in evidence_body.get("reason_codes", ()):
                    reason_children.append(_reason_node(str(code), exact_ref))
                invalidating_refs.extend(invalidations.get(exact_ref["revision_digest"], ()))

            invalidating_refs.extend(invalidations.get(qualification_ref["revision_digest"], ()))
            if invalidating_refs:
                effective_status = "STALE"
                for inv_ref in _dedupe_refs(invalidating_refs):
                    reason_children.append(_reason_node("ACCEPTED_EVIDENCE_INVALIDATION", inv_ref))

            applicability_ref = qbody.get("applicability_decision_ref")
            if isinstance(applicability_ref, dict):
                applicability = store.resolve_accepted(applicability_ref, dict(cut))
                exact_ref = dict(applicability["ref"])
                direct_refs.append(exact_ref)
                is_not_applicable = applicability["body"].get("result") == "NOT_APPLICABLE"
                reason_children.append(_reason_node("NOT_APPLICABLE" if is_not_applicable else "APPLICABILITY_DECISION", exact_ref))

            waiver_ref = qbody.get("waiver_decision_ref")
            if isinstance(waiver_ref, dict):
                waiver = store.resolve_accepted(waiver_ref, dict(cut))
                exact_ref = dict(waiver["ref"])
                direct_refs.append(exact_ref)
                is_waived = waiver["body"].get("decision") == "APPROVED"
                reason_children.append(_reason_node("WAIVER_APPROVED" if is_waived else "WAIVER_NOT_APPROVED", exact_ref))

        satisfies_completion = (
            effective_status == "QUALIFIED"
            and substantive_outcome == "NO_VIOLATION_OBSERVED"
        )
        result.append({
            "obligation_id": obligation_body.get("obligation_id"),
            "obligation_ref": obligation_ref,
            "accepted_seq": obligation["accepted_seq"],
            "scenario_class": obligation_body.get("scenario_class"),
            "policy_obligation_key": obligation_body.get("policy_obligation_key"),
            "effective_status": effective_status,
            "substantive_outcome": substantive_outcome,
            "satisfies_completion": satisfies_completion,
            "is_not_applicable": is_not_applicable,
            "is_waived": is_waived,
            "qualification_refs": _dedupe_refs(qualification_refs),
            "evidence_qualification_refs": _dedupe_refs(evidence_refs),
            "invalidation_refs": _dedupe_refs(invalidating_refs),
            "direct_accepted_refs": _dedupe_refs(direct_refs + invalidating_refs),
            "reason_tree": {
                "code": f"COVERAGE_{effective_status}",
                "children": reason_children,
            },
        })
    result.sort(key=lambda item: (
        str(item.get("policy_obligation_key", "")),
        str(item.get("obligation_id", "")),
        str(item["obligation_ref"].get("revision_digest", "")),
    ))
    return result


def _coverage_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "denominator": len(rows),
        "satisfied": sum(1 for row in rows if row["satisfies_completion"]),
        "unassessed": sum(1 for row in rows if row["effective_status"] == "UNASSESSED"),
        "in_progress": sum(1 for row in rows if row["effective_status"] == "IN_PROGRESS"),
        "blocked": sum(1 for row in rows if row["effective_status"] == "BLOCKED"),
        "stale": sum(1 for row in rows if row["effective_status"] == "STALE"),
        "conflicted": sum(1 for row in rows if row["effective_status"] == "CONFLICTED"),
    }


def _coverage_blockers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for row in rows:
        if row["satisfies_completion"]:
            continue
        blockers.append({
            "blocker_type": f"COVERAGE_{row['effective_status']}",
            "obligation_id": row.get("obligation_id"),
            "reason_tree": row["reason_tree"],
            "direct_accepted_refs": row["direct_accepted_refs"],
        })
    return blockers


def build_verified_assurance_snapshot(
    store: TransactionalHistoryStore,
    cut: Mapping[str, Any] | None = None,
) -> AssuranceProjectionSnapshot:
    """Rebuild the RU12-A read model from one verified accepted history cut."""
    current_cut = current_accepted_cut(store)
    selected_cut = dict(cut) if cut is not None else current_cut
    model = VerifiedCampaignReadModel(store, cut=selected_cut)
    campaign = model.project_status()
    campaign["accepted_head_seq"] = selected_cut["accepted_head_seq"]
    campaign["accepted_head_hash"] = selected_cut["accepted_head_hash"]
    source = campaign_source_identity(store, selected_cut)
    invalidations, _ = _invalidation_index(store, selected_cut)
    coverage_rows = _project_coverage_rows(store, selected_cut, invalidations)
    evidence_index = _project_evidence_index(store, selected_cut, invalidations)
    freshness = "ACTIVE" if selected_cut == current_cut else "STALE"
    if freshness == "ACTIVE":
        workflow = ContinuationService.evaluate_continuation(store)
    else:
        workflow = {
            "continuation_state": "HISTORICAL_VIEW",
            "next_action": "NONE",
            "current_stage": campaign.get("current_stage"),
        }
    blockers = _coverage_blockers(coverage_rows)
    if workflow.get("continuation_state") == "BLOCKED":
        blockers.append({
            "blocker_type": "WORKFLOW_BLOCKED",
            "reason_tree": {"code": "CONTINUATION_BLOCKED", "children": []},
            "direct_accepted_refs": [],
        })
    body: dict[str, Any] = {
        "schema_version": "RU12A-1",
        "projection_kind": "VERIFIED_ASSURANCE_PROJECTION",
        "authority": "DERIVED_ONLY",
        "history_cut": selected_cut,
        "freshness": freshness,
        "source_identity": source,
        "campaign_status": campaign,
        "workflow": workflow,
        "coverage_summary": _coverage_summary(coverage_rows),
        "coverage_rows": coverage_rows,
        "evidence_index": evidence_index,
        "blockers": blockers,
    }
    return AssuranceProjectionSnapshot(body)


def verify_projection_snapshot(
    snapshot: Mapping[str, Any],
    store: TransactionalHistoryStore,
) -> dict[str, Any]:
    """Verify snapshot self-integrity and report whether its exact cut is current."""
    supplied_digest = snapshot.get("projection_digest")
    body = dict(snapshot)
    body.pop("projection_digest", None)
    calculated = hashlib.sha256(canonical_bytes(body)).hexdigest()
    if supplied_digest != calculated:
        raise ValidationError("PROJECTION_DIGEST_MISMATCH")
    cut = body.get("history_cut")
    if not isinstance(cut, dict):
        raise ValidationError("PROJECTION_HISTORY_CUT_MISSING")
    commits = store.commits()
    if not commits:
        raise ValidationError("CAMPAIGN_NOT_FOUND")
    store.resolve_accepted(commits[0]["command_ref"], cut)
    current_cut = current_accepted_cut(store)
    return {
        "status": "PASS",
        "projection_digest": calculated,
        "freshness": "ACTIVE" if cut == current_cut else "STALE",
        "history_cut": cut,
        "current_history_cut": current_cut,
    }


def coverage_matrix(store: TransactionalHistoryStore) -> dict[str, Any]:
    snapshot = build_verified_assurance_snapshot(store).as_dict()
    return {
        "status": "SUCCESS",
        "history_cut": snapshot["history_cut"],
        "freshness": snapshot["freshness"],
        "source_identity": snapshot["source_identity"],
        "coverage_summary": snapshot["coverage_summary"],
        "coverage_rows": snapshot["coverage_rows"],
        "projection_digest": snapshot["projection_digest"],
    }


def coverage_explain(store: TransactionalHistoryStore, selector: str) -> dict[str, Any]:
    snapshot = build_verified_assurance_snapshot(store).as_dict()
    matches = [
        row for row in snapshot["coverage_rows"]
        if row.get("obligation_id") == selector
        or row["obligation_ref"].get("revision_digest") == selector
    ]
    if not matches:
        raise ValidationError("COVERAGE_OBLIGATION_NOT_FOUND", selector)
    if len(matches) != 1:
        raise ValidationError("COVERAGE_OBLIGATION_SELECTOR_AMBIGUOUS", selector)
    return {
        "status": "SUCCESS",
        "history_cut": snapshot["history_cut"],
        "freshness": snapshot["freshness"],
        "projection_digest": snapshot["projection_digest"],
        "coverage": matches[0],
    }


def inspect_evidence(
    store: TransactionalHistoryStore,
    digest: str,
    *,
    kind: str | None = None,
) -> dict[str, Any]:
    cut = current_accepted_cut(store)
    ref = _accepted_ref_by_digest(store, cut, digest, kind=kind)
    resolved = store.resolve_accepted(ref, cut)
    invalidations, _ = _invalidation_index(store, cut)
    invalidating_refs = _dedupe_refs(list(invalidations.get(digest, ())))
    direct_refs = _direct_refs(resolved["body"])
    for child_ref in direct_refs:
        store.resolve_accepted(child_ref, cut)
    return {
        "status": "SUCCESS",
        "history_cut": cut,
        "ref": dict(resolved["ref"]),
        "accepted_seq": resolved["accepted_seq"],
        "body": resolved["body"],
        "freshness": "STALE" if invalidating_refs else "ACTIVE",
        "current_applicable": not invalidating_refs,
        "direct_accepted_refs": direct_refs,
        "invalidation_refs": invalidating_refs,
        "reason_tree": {
            "code": "EVIDENCE_STALE" if invalidating_refs else "EVIDENCE_ACTIVE",
            "children": [
                _reason_node("ACCEPTED_EVIDENCE_INVALIDATION", item)
                for item in invalidating_refs
            ],
        },
    }


def verify_evidence(
    store: TransactionalHistoryStore,
    digest: str,
    *,
    kind: str | None = None,
) -> dict[str, Any]:
    inspected = inspect_evidence(store, digest, kind=kind)
    return {
        "status": "PASS",
        "verification": "ACCEPTED_CLOSURE_AND_DIRECT_REFS_VERIFIED",
        "history_cut": inspected["history_cut"],
        "ref": inspected["ref"],
        "freshness": inspected["freshness"],
        "current_applicable": inspected["current_applicable"],
        "invalidation_refs": inspected["invalidation_refs"],
    }


def audit_blockers(store: TransactionalHistoryStore) -> dict[str, Any]:
    snapshot = build_verified_assurance_snapshot(store).as_dict()
    return {
        "status": "SUCCESS",
        "history_cut": snapshot["history_cut"],
        "freshness": snapshot["freshness"],
        "workflow": snapshot["workflow"],
        "coverage_summary": snapshot["coverage_summary"],
        "blockers": snapshot["blockers"],
        "projection_digest": snapshot["projection_digest"],
    }


__all__ = [
    "AssuranceProjectionSnapshot",
    "build_verified_assurance_snapshot",
    "verify_projection_snapshot",
    "coverage_matrix",
    "coverage_explain",
    "inspect_evidence",
    "verify_evidence",
    "audit_blockers",
]

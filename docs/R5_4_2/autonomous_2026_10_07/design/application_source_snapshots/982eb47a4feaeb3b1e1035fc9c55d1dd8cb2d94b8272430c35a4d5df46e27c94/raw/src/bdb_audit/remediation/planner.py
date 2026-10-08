"""Deterministic root-cause-aware remediation planner for RU09."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any, Iterable

from ..report.models import ReportItem, ReportModel
from .models import Priority, RemediationPlan, RepairUnit
from .validation import validate_remediation_plan


_CURRENT_FINDING_STATES = {"CONFIRMED_CURRENT", "REMEDIATION_PENDING", "PARTIALLY_FIXED", "REOPENED"}
_PRIORITIES = {"P0", "P1", "P2", "P3"}


def _ref_identity(ref: dict[str, Any] | None) -> tuple[str, str] | None:
    if not isinstance(ref, dict):
        return None
    kind = ref.get("kind")
    digest = ref.get("revision_digest")
    if isinstance(kind, str) and isinstance(digest, str):
        return kind, digest
    return None


def _dedupe_refs(refs: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for ref in refs:
        key = _ref_identity(ref)
        if key is not None:
            by_key[key] = deepcopy(ref)
    return tuple(by_key[key] for key in sorted(by_key))


def _explicit_priority(*payloads: dict[str, Any]) -> Priority:
    """Use only an explicit audit priority; never infer a priority from prose."""
    for payload in payloads:
        for key in ("priority", "remediation_priority", "material_priority"):
            value = payload.get(key)
            if isinstance(value, str) and value.upper() in _PRIORITIES:
                return value.upper()  # type: ignore[return-value]
    return "UNRANKED"


def _explicit_strings(payload: dict[str, Any], *keys: str) -> tuple[str, ...]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return (value,)
        if isinstance(value, list) and all(isinstance(x, str) for x in value):
            return tuple(sorted(set(value)))
    return ()


def _unit_id(root_ref: dict[str, Any] | None, finding_refs: tuple[dict[str, Any], ...]) -> str:
    parts: list[str] = []
    if root_ref is not None:
        parts.append(str(root_ref.get("revision_digest", "")))
    parts.extend(str(ref.get("revision_digest", "")) for ref in finding_refs)
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"repair_{digest[:16]}"


class RemediationPlanner:
    """Build a proposed remediation DAG without executing or accepting repairs."""

    def __init__(self, report: ReportModel):
        self.report = report

    def build(self) -> RemediationPlan:
        claims: dict[str, ReportItem] = {}
        decisions_by_claim: dict[str, ReportItem] = {}
        roots: list[ReportItem] = []

        for item in self.report.facts:
            if item.record_kind == "finding_claim_revision" and item.source_ref:
                digest = item.source_ref.get("revision_digest")
                if isinstance(digest, str):
                    claims[digest] = item
            elif item.record_kind == "finding_adjudication_decision":
                lifecycle = item.payload.get("lifecycle_status")
                claim_ref = item.payload.get("claim_revision_ref")
                if lifecycle in _CURRENT_FINDING_STATES and isinstance(claim_ref, dict):
                    digest = claim_ref.get("revision_digest")
                    if isinstance(digest, str):
                        decisions_by_claim[digest] = item
            elif item.record_kind == "root_cause_revision":
                roots.append(item)

        current_claim_digests = sorted(d for d in decisions_by_claim if d in claims)
        claimed_by_root: set[str] = set()
        units: list[RepairUnit] = []
        root_to_unit: dict[str, str] = {}
        pending_dependencies: dict[str, tuple[str, ...]] = {}

        for root in sorted(roots, key=lambda item: item.sort_key):
            if not root.source_ref:
                continue
            member_digests: list[str] = []
            for edge in root.payload.get("membership_edges", []):
                if not isinstance(edge, dict):
                    continue
                finding_ref = edge.get("finding_claim_revision_ref")
                if isinstance(finding_ref, dict):
                    digest = finding_ref.get("revision_digest")
                    if isinstance(digest, str) and digest in current_claim_digests:
                        member_digests.append(digest)
            member_digests = sorted(set(member_digests))
            if not member_digests:
                continue
            finding_refs = _dedupe_refs(
                claims[d].source_ref for d in member_digests if claims[d].source_ref is not None
            )
            claimed_by_root.update(member_digests)
            decision_payloads = [decisions_by_claim[d].payload for d in member_digests]
            claim_payloads = [claims[d].payload for d in member_digests]
            priority = _explicit_priority(*(claim_payloads + decision_payloads))
            evidence = _dedupe_refs(
                ref
                for d in member_digests
                for ref in decisions_by_claim[d].payload.get("evidence_qualification_refs", [])
                if isinstance(ref, dict)
            )
            modules = tuple(sorted(set(
                value
                for payload in claim_payloads
                for value in _explicit_strings(payload, "affected_modules", "modules")
            ))) or ("NOT_ASSESSED",)
            alternatives = tuple(sorted(set(
                value
                for payload in claim_payloads
                for value in _explicit_strings(payload, "fix_alternatives")
            ))) or ("NOT_ASSESSED",)
            root_ref = deepcopy(root.source_ref)
            uid = _unit_id(root_ref, finding_refs)
            predecessor_digests = tuple(
                sorted(
                    str(ref.get("revision_digest"))
                    for ref in root.payload.get("predecessor_root_cause_refs", [])
                    if isinstance(ref, dict) and isinstance(ref.get("revision_digest"), str)
                )
            )
            pending_dependencies[uid] = predecessor_digests
            root_digest = str(root_ref.get("revision_digest", ""))
            root_to_unit[root_digest] = uid
            units.append(
                RepairUnit(
                    unit_id=uid,
                    priority=priority,
                    finding_refs=finding_refs,
                    symptom_refs=finding_refs,
                    root_cause_ref=root_ref,
                    affected_modules=modules,
                    expected_fixed_property="NOT_ASSESSED",
                    reproduction_protocol={"status": "NOT_ASSESSED"},
                    fix_alternatives=alternatives,
                    evidence_refs=evidence,
                    negative_test="NOT_ASSESSED",
                    sibling_test="NOT_ASSESSED",
                    holdout_test="NOT_ASSESSED",
                    dependency_unit_ids=(),
                    migration_strategy="NOT_ASSESSED",
                )
            )

        for digest in current_claim_digests:
            if digest in claimed_by_root:
                continue
            claim = claims[digest]
            decision = decisions_by_claim[digest]
            finding_refs = _dedupe_refs((claim.source_ref,)) if claim.source_ref is not None else ()
            evidence = _dedupe_refs(
                ref for ref in decision.payload.get("evidence_qualification_refs", []) if isinstance(ref, dict)
            )
            modules = _explicit_strings(claim.payload, "affected_modules", "modules") or ("NOT_ASSESSED",)
            alternatives = _explicit_strings(claim.payload, "fix_alternatives") or ("NOT_ASSESSED",)
            units.append(
                RepairUnit(
                    unit_id=_unit_id(None, finding_refs),
                    priority=_explicit_priority(claim.payload, decision.payload),
                    finding_refs=finding_refs,
                    symptom_refs=finding_refs,
                    root_cause_ref=None,
                    affected_modules=modules,
                    expected_fixed_property="NOT_ASSESSED",
                    reproduction_protocol={"status": "NOT_ASSESSED"},
                    fix_alternatives=alternatives,
                    evidence_refs=evidence,
                    negative_test="NOT_ASSESSED",
                    sibling_test="NOT_ASSESSED",
                    holdout_test="NOT_ASSESSED",
                    dependency_unit_ids=(),
                    migration_strategy="NOT_ASSESSED",
                )
            )

        resolved_units: list[RepairUnit] = []
        for unit in units:
            dependencies = tuple(
                sorted(
                    root_to_unit[digest]
                    for digest in pending_dependencies.get(unit.unit_id, ())
                    if digest in root_to_unit and root_to_unit[digest] != unit.unit_id
                )
            )
            resolved_units.append(
                RepairUnit(
                    **{**unit.as_dict(), "finding_refs": unit.finding_refs, "symptom_refs": unit.symptom_refs,
                       "root_cause_ref": unit.root_cause_ref, "affected_modules": unit.affected_modules,
                       "fix_alternatives": unit.fix_alternatives, "evidence_refs": unit.evidence_refs,
                       "dependency_unit_ids": dependencies}
                )
            )

        resolved_units.sort(key=lambda unit: unit.unit_id)
        plan = RemediationPlan(
            campaign_id=self.report.campaign_id,
            input_history_cut=deepcopy(self.report.input_history_cut),
            source_identity=deepcopy(self.report.source_identity),
            report_model_sha256=self.report.report_model_sha256,
            repair_units=tuple(resolved_units),
        )
        validate_remediation_plan(plan)
        return plan


__all__ = ["RemediationPlanner"]

"""Typed RU09 remediation-plan models.

A remediation plan is always a PROPOSED derived artifact.  It can describe work
for an implementer but it never mutates accepted audit history or executes fixes.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Literal


REMEDIATION_PLAN_SCHEMA = "BDB-REMEDIATION-PLAN-1"
Priority = Literal["P0", "P1", "P2", "P3", "UNRANKED"]


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class RepairUnit:
    unit_id: str
    priority: Priority
    finding_refs: tuple[dict[str, Any], ...]
    symptom_refs: tuple[dict[str, Any], ...]
    root_cause_ref: dict[str, Any] | None
    affected_modules: tuple[str, ...]
    expected_fixed_property: str
    reproduction_protocol: dict[str, Any]
    fix_alternatives: tuple[str, ...]
    evidence_refs: tuple[dict[str, Any], ...]
    negative_test: str
    sibling_test: str
    holdout_test: str
    dependency_unit_ids: tuple[str, ...]
    migration_strategy: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "priority": self.priority,
            "finding_refs": [deepcopy(ref) for ref in self.finding_refs],
            "symptom_refs": [deepcopy(ref) for ref in self.symptom_refs],
            "root_cause_ref": deepcopy(self.root_cause_ref),
            "affected_modules": list(self.affected_modules),
            "expected_fixed_property": self.expected_fixed_property,
            "reproduction_protocol": deepcopy(self.reproduction_protocol),
            "fix_alternatives": list(self.fix_alternatives),
            "evidence_refs": [deepcopy(ref) for ref in self.evidence_refs],
            "negative_test": self.negative_test,
            "sibling_test": self.sibling_test,
            "holdout_test": self.holdout_test,
            "dependency_unit_ids": list(self.dependency_unit_ids),
            "migration_strategy": self.migration_strategy,
        }


@dataclass(frozen=True)
class RemediationPlan:
    campaign_id: str
    input_history_cut: dict[str, Any]
    source_identity: dict[str, Any]
    report_model_sha256: str
    repair_units: tuple[RepairUnit, ...]
    status: Literal["PROPOSED"] = "PROPOSED"
    schema_version: str = REMEDIATION_PLAN_SCHEMA

    def digest_preimage(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "campaign_id": self.campaign_id,
            "input_history_cut": deepcopy(self.input_history_cut),
            "source_identity": deepcopy(self.source_identity),
            "report_model_sha256": self.report_model_sha256,
            "repair_units": [unit.as_dict() for unit in self.repair_units],
        }

    @property
    def plan_sha256(self) -> str:
        return hashlib.sha256(_canonical_json_bytes(self.digest_preimage())).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        body = self.digest_preimage()
        body["plan_sha256"] = self.plan_sha256
        return body


def repair_unit_from_dict(data: dict[str, Any]) -> RepairUnit:
    priority = str(data.get("priority", "UNRANKED"))
    if priority not in {"P0", "P1", "P2", "P3", "UNRANKED"}:
        priority = "UNRANKED"
    return RepairUnit(
        unit_id=str(data["unit_id"]),
        priority=priority,  # type: ignore[arg-type]
        finding_refs=tuple(dict(x) for x in data.get("finding_refs", [])),
        symptom_refs=tuple(dict(x) for x in data.get("symptom_refs", [])),
        root_cause_ref=dict(data["root_cause_ref"]) if isinstance(data.get("root_cause_ref"), dict) else None,
        affected_modules=tuple(str(x) for x in data.get("affected_modules", [])),
        expected_fixed_property=str(data.get("expected_fixed_property", "NOT_ASSESSED")),
        reproduction_protocol=dict(data.get("reproduction_protocol", {"status": "NOT_ASSESSED"})),
        fix_alternatives=tuple(str(x) for x in data.get("fix_alternatives", [])),
        evidence_refs=tuple(dict(x) for x in data.get("evidence_refs", [])),
        negative_test=str(data.get("negative_test", "NOT_ASSESSED")),
        sibling_test=str(data.get("sibling_test", "NOT_ASSESSED")),
        holdout_test=str(data.get("holdout_test", "NOT_ASSESSED")),
        dependency_unit_ids=tuple(str(x) for x in data.get("dependency_unit_ids", [])),
        migration_strategy=str(data.get("migration_strategy", "NOT_ASSESSED")),
    )


def remediation_plan_from_dict(data: dict[str, Any]) -> RemediationPlan:
    return RemediationPlan(
        campaign_id=str(data["campaign_id"]),
        input_history_cut=dict(data["input_history_cut"]),
        source_identity=dict(data["source_identity"]),
        report_model_sha256=str(data["report_model_sha256"]),
        repair_units=tuple(repair_unit_from_dict(x) for x in data.get("repair_units", [])),
        status="PROPOSED",
        schema_version=str(data.get("schema_version", REMEDIATION_PLAN_SCHEMA)),
    )


__all__ = [
    "REMEDIATION_PLAN_SCHEMA",
    "Priority",
    "RepairUnit",
    "RemediationPlan",
    "repair_unit_from_dict",
    "remediation_plan_from_dict",
]

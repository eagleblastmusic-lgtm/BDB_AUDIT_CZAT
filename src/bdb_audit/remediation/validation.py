"""Fail-closed validation for proposed remediation DAGs."""
from __future__ import annotations

from ..core.errors import ValidationError
from .models import REMEDIATION_PLAN_SCHEMA, RemediationPlan


def validate_remediation_plan(plan: RemediationPlan) -> None:
    if plan.schema_version != REMEDIATION_PLAN_SCHEMA:
        raise ValidationError("REMEDIATION_SCHEMA_VERSION_UNSUPPORTED", plan.schema_version)
    if plan.status != "PROPOSED":
        raise ValidationError("REMEDIATION_PLAN_MUST_REMAIN_PROPOSED")
    if plan.input_history_cut.get("campaign_id") != plan.campaign_id:
        raise ValidationError("REMEDIATION_CAMPAIGN_CUT_MISMATCH")
    if not plan.source_identity.get("source_generation_id"):
        raise ValidationError("REMEDIATION_SOURCE_IDENTITY_INCOMPLETE")
    if len(plan.report_model_sha256) != 64:
        raise ValidationError("REMEDIATION_REPORT_DIGEST_INVALID")

    ids = [unit.unit_id for unit in plan.repair_units]
    if len(ids) != len(set(ids)):
        raise ValidationError("REMEDIATION_DUPLICATE_UNIT_ID")
    id_set = set(ids)
    for unit in plan.repair_units:
        if unit.priority not in {"P0", "P1", "P2", "P3", "UNRANKED"}:
            raise ValidationError("REMEDIATION_PRIORITY_INVALID", unit.priority)
        if unit.unit_id in unit.dependency_unit_ids:
            raise ValidationError("REMEDIATION_SELF_DEPENDENCY", unit.unit_id)
        missing = sorted(set(unit.dependency_unit_ids).difference(id_set))
        if missing:
            raise ValidationError("REMEDIATION_DANGLING_DEPENDENCY", ",".join(missing))
        finding_ids = [
            (ref.get("kind"), ref.get("revision_digest")) for ref in unit.finding_refs
        ]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValidationError("REMEDIATION_DUPLICATE_FINDING_REF", unit.unit_id)

    graph = {unit.unit_id: tuple(unit.dependency_unit_ids) for unit in plan.repair_units}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            raise ValidationError("REMEDIATION_DEPENDENCY_CYCLE", node)
        visiting.add(node)
        for dep in graph[node]:
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        visit(node)


__all__ = ["validate_remediation_plan"]

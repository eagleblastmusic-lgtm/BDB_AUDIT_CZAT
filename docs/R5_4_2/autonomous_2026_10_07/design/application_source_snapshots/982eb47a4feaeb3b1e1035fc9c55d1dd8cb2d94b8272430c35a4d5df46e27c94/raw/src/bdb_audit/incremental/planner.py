"""RU16 change impact, evidence reuse, and targeted regression planning."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Mapping, Sequence

from ..core.errors import ValidationError
from .models import AuditDelta, ChangeImpactMap, EvidenceReuseAssessment, ReplayRun, RequalificationPlan, RevisionSnapshot, SuccessorSelection

_DIMENSIONS = (
    ("runtime_dependencies_digest", "RUNTIME_DEPENDENCIES"),
    ("schema_digest", "SCHEMA"),
    ("environment_digest", "ENVIRONMENT"),
    ("policy_digest", "POLICY"),
    ("template_digest", "TEMPLATE"),
)


def select_successor(predecessor: RevisionSnapshot, successors: Sequence[RevisionSnapshot], selected_revision_id: str) -> SuccessorSelection:
    by_id = {item.revision_id: item for item in successors}
    selected = by_id.get(selected_revision_id)
    if selected is None:
        raise ValidationError("SUCCESSOR_EXPLICIT_SELECTION_REQUIRED", selected_revision_id)
    if selected_revision_id == predecessor.revision_id:
        raise ValidationError("SUCCESSOR_EQUALS_PREDECESSOR")
    return SuccessorSelection(
        predecessor_revision_id=predecessor.revision_id,
        successor_revision_id=selected.revision_id,
        successor_ref=dict(selected.source_identity),
        competing_successor_ids=tuple(item for item in by_id if item != selected_revision_id),
    )


def _reverse_dependency_graph(snapshot: RevisionSnapshot) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = defaultdict(set)
    for source, dependencies in snapshot.dependencies.items():
        for dependency in dependencies:
            reverse[dependency].add(source)
    return reverse


def build_change_impact(predecessor: RevisionSnapshot, successor: RevisionSnapshot, *, uncertain_paths: Sequence[str] = ()) -> ChangeImpactMap:
    all_paths = set(predecessor.members) | set(successor.members)
    direct = {path for path in all_paths if predecessor.members.get(path) != successor.members.get(path)}
    dimensions = [label for attr, label in _DIMENSIONS if getattr(predecessor, attr) != getattr(successor, attr)]

    # Propagate through both old and new dependency graphs. This catches known
    # regressions outside the textual diff when dependents are affected by a
    # changed provider or schema/runtime dependency boundary.
    reverse_old = _reverse_dependency_graph(predecessor)
    reverse_new = _reverse_dependency_graph(successor)
    queue: deque[str] = deque(sorted(direct))
    impacted = set(direct)
    while queue:
        current = queue.popleft()
        for dependent in sorted(reverse_old.get(current, set()) | reverse_new.get(current, set())):
            if dependent not in impacted:
                impacted.add(dependent)
                queue.append(dependent)

    if dimensions:
        # Non-file execution dimensions can invalidate every test/evidence path;
        # make this explicit rather than silently reusing old evidence.
        impacted.update(successor.members)
    uncertain = set(str(item) for item in uncertain_paths)
    if not uncertain.issubset(all_paths):
        raise ValidationError("IMPACT_UNCERTAIN_PATH_UNKNOWN")
    return ChangeImpactMap(
        predecessor_revision_id=predecessor.revision_id,
        successor_revision_id=successor.revision_id,
        direct_changes=tuple(direct),
        propagated_impacts=tuple(impacted - direct),
        uncertain_impacts=tuple(uncertain),
        change_dimensions=tuple(dimensions),
    )


def assess_evidence_reuse(
    evidence_id: str,
    predecessor: RevisionSnapshot,
    successor: RevisionSnapshot,
    impact: ChangeImpactMap,
    *,
    scope_paths: Sequence[str],
    environment_profile: str,
    evidence_refs: Sequence[str],
    evidence_environment_digest: str,
) -> EvidenceReuseAssessment:
    scoped = set(scope_paths)
    if not scoped:
        raise ValidationError("EVIDENCE_REUSE_SCOPE_REQUIRED")
    impacted = set(impact.direct_changes) | set(impact.propagated_impacts) | set(impact.uncertain_impacts)
    reasons: list[str] = []
    status = "REUSABLE"
    if scoped & impacted:
        status = "STALE"
        reasons.append("SCOPE_INTERSECTS_CHANGE_IMPACT")
    if evidence_environment_digest != successor.environment_digest:
        status = "STALE"
        reasons.append("ENVIRONMENT_DIGEST_CHANGED")
    if impact.uncertain_impacts and scoped & set(impact.uncertain_impacts):
        status = "PENDING"
        reasons.append("UNCERTAIN_DEPENDENCY_REQUIRES_REQUALIFICATION")
    return EvidenceReuseAssessment(
        evidence_id=evidence_id,
        predecessor_revision_id=predecessor.revision_id,
        successor_revision_id=successor.revision_id,
        scope_paths=tuple(scope_paths),
        environment_profile=environment_profile,
        evidence_refs=tuple(evidence_refs),
        status=status,
        reason_codes=tuple(reasons),
    )


def build_requalification_plan(impact: ChangeImpactMap, reuse: Sequence[EvidenceReuseAssessment]) -> RequalificationPlan:
    impacted = set(impact.direct_changes) | set(impact.propagated_impacts) | set(impact.uncertain_impacts)
    reusable = [item.evidence_id for item in reuse if item.status == "REUSABLE"]
    pending = [item.evidence_id for item in reuse if item.status != "REUSABLE"]
    state = "REUSE_QUALIFIED" if not pending else "REUSE_PENDING"
    denominator = max(1, len(impacted))
    return RequalificationPlan(
        plan_id=f"requal_{impact.predecessor_revision_id}_to_{impact.successor_revision_id}",
        impact_digest=impact.as_dict()["impact_digest"],
        required_paths=tuple(sorted(impacted)),
        reusable_evidence_ids=tuple(reusable),
        pending_evidence_ids=tuple(pending),
        coverage_denominator=denominator,
        state=state,
    )


def run_regression_plan(plan: RequalificationPlan, actual_results: Mapping[str, bool]) -> ReplayRun:
    required = set(plan.required_paths)
    missing = required - set(actual_results)
    if missing:
        raise ValidationError("REGRESSION_REQUIRED_PATH_NOT_RUN", ",".join(sorted(missing)))
    failed = tuple(path for path in sorted(required) if not bool(actual_results[path]))
    return ReplayRun(
        replay_id=f"replay_{plan.plan_id}",
        plan_id=plan.plan_id,
        executed_paths=tuple(sorted(required)),
        failed_paths=failed,
    )


def build_audit_delta(
    predecessor: RevisionSnapshot,
    successor: RevisionSnapshot,
    impact: ChangeImpactMap,
    replay: ReplayRun,
    *,
    previous_cost_units: int,
    current_cost_units: int,
    coverage_denominator: int,
) -> AuditDelta:
    return AuditDelta(
        predecessor_revision_id=predecessor.revision_id,
        successor_revision_id=successor.revision_id,
        impacted_paths=tuple(sorted(set(impact.direct_changes) | set(impact.propagated_impacts) | set(impact.uncertain_impacts))),
        requalified_paths=replay.executed_paths,
        failed_paths=replay.failed_paths,
        previous_cost_units=previous_cost_units,
        current_cost_units=current_cost_units,
        coverage_denominator=coverage_denominator,
    )


def revision_from_dict(body: Mapping[str, Any]) -> RevisionSnapshot:
    return RevisionSnapshot(
        revision_id=str(body.get("revision_id", "")),
        source_identity=dict(body.get("source_identity", {})),
        members=dict(body.get("members", {})),
        dependencies={str(k): tuple(v) for k, v in dict(body.get("dependencies", {})).items()},
        runtime_dependencies_digest=str(body.get("runtime_dependencies_digest", "")),
        schema_digest=str(body.get("schema_digest", "")),
        environment_digest=str(body.get("environment_digest", "")),
        policy_digest=str(body.get("policy_digest", "")),
        template_digest=str(body.get("template_digest", "")),
    )


__all__ = ["select_successor", "build_change_impact", "assess_evidence_reuse", "build_requalification_plan", "run_regression_plan", "build_audit_delta", "revision_from_dict"]

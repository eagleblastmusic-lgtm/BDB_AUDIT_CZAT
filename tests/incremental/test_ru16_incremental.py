from __future__ import annotations

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.incremental import EvidenceReuseAssessment, RevisionSnapshot
from bdb_audit.incremental.planner import (
    assess_evidence_reuse, build_change_impact, build_requalification_plan,
    run_regression_plan, select_successor,
)


def _sha(ch: str) -> str:
    return ch * 64


def _revision(revision_id: str, members: dict[str, str], dependencies: dict[str, tuple[str, ...]], *, env: str = "e") -> RevisionSnapshot:
    return RevisionSnapshot(
        revision_id=revision_id,
        source_identity={"git_commit_object_id": revision_id},
        members=members,
        dependencies=dependencies,
        runtime_dependencies_digest=_sha("r"),
        schema_digest=_sha("s"),
        environment_digest=_sha(env),
        policy_digest=_sha("p"),
        template_digest=_sha("t"),
    )


def test_ru16_dependency_propagation_catches_regression_outside_textual_diff() -> None:
    old = _revision("old", {"core.py": _sha("a"), "feature.py": _sha("b"), "test_feature.py": _sha("c")}, {"feature.py": ("core.py",), "test_feature.py": ("feature.py",)})
    new = _revision("new", {"core.py": _sha("d"), "feature.py": _sha("b"), "test_feature.py": _sha("c")}, {"feature.py": ("core.py",), "test_feature.py": ("feature.py",)})
    impact = build_change_impact(old, new)
    assert impact.direct_changes == ("core.py",)
    assert "feature.py" in impact.propagated_impacts
    assert "test_feature.py" in impact.propagated_impacts


def test_ru16_stale_evidence_never_current_pass_eligible() -> None:
    old = _revision("old", {"core.py": _sha("a")}, {})
    new = _revision("new", {"core.py": _sha("b")}, {})
    impact = build_change_impact(old, new)
    assessment = assess_evidence_reuse(
        "ev1", old, new, impact, scope_paths=("core.py",), environment_profile="win-py314",
        evidence_refs=("evidence:1",), evidence_environment_digest=new.environment_digest,
    )
    assert assessment.status == "STALE"
    assert assessment.current_pass_eligible is False


def test_ru16_environment_change_invalidates_unrelated_evidence() -> None:
    old = _revision("old", {"a.py": _sha("a"), "b.py": _sha("b")}, {}, env="e")
    new = _revision("new", {"a.py": _sha("a"), "b.py": _sha("b")}, {}, env="f")
    impact = build_change_impact(old, new)
    assert set(impact.propagated_impacts) == {"a.py", "b.py"}
    assert "ENVIRONMENT" in impact.change_dimensions


def test_ru16_successor_selection_is_explicit_not_latest_timestamp() -> None:
    predecessor = _revision("old", {"a.py": _sha("a")}, {})
    first = _revision("successor-a", {"a.py": _sha("b")}, {})
    second = _revision("successor-b", {"a.py": _sha("c")}, {})
    selection = select_successor(predecessor, (first, second), "successor-a")
    assert selection.successor_revision_id == "successor-a"
    assert selection.competing_successor_ids == ("successor-b",)
    with pytest.raises(ValidationError, match="SUCCESSOR_EXPLICIT_SELECTION_REQUIRED"):
        select_successor(predecessor, (first, second), "missing")


def test_ru16_requalification_requires_all_impacted_paths_to_run() -> None:
    old = _revision("old", {"a.py": _sha("a"), "b.py": _sha("b")}, {"b.py": ("a.py",)})
    new = _revision("new", {"a.py": _sha("c"), "b.py": _sha("b")}, {"b.py": ("a.py",)})
    impact = build_change_impact(old, new)
    reuse = (EvidenceReuseAssessment("ev", "old", "new", ("a.py",), "profile", ("e:1",), "STALE"),)
    plan = build_requalification_plan(impact, reuse)
    assert plan.coverage_denominator == 2
    with pytest.raises(ValidationError, match="REGRESSION_REQUIRED_PATH_NOT_RUN"):
        run_regression_plan(plan, {"a.py": True})
    replay = run_regression_plan(plan, {"a.py": True, "b.py": False})
    assert replay.failed_paths == ("b.py",)

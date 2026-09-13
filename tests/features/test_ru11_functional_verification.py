from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.features import (
    BehaviorCase,
    build_verification_plan,
    discover_api_features,
    discover_cli_features,
    execute_verification_plan,
    feature_status_matrix,
    qualify_oracle,
)
from bdb_audit.features.models import VerificationPlan
from bdb_audit.runner.environments import environment_manifest, source_manifest
from bdb_audit.runner.specs import CapabilityProfile


def _target(tmp_path: Path) -> Path:
    root = tmp_path / "target"
    (root / "src" / "demo").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[project]\nname='demo'\nversion='1.0'\n[project.scripts]\ndemo='demo.cli:main'\n",
        encoding="utf-8",
    )
    (root / "src" / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "demo" / "cli.py").write_text(
        "import json,sys\n"
        "def public_api(value): return value + 1\n"
        "def main():\n"
        "    mode = sys.argv[1] if len(sys.argv) > 1 else 'ok'\n"
        "    if mode == 'fail':\n"
        "        print(json.dumps({'status':'bad'})); return 7\n"
        "    print(json.dumps({'status':'ok','value':public_api(1)})); return 0\n"
        "if __name__ == '__main__': raise SystemExit(main())\n",
        encoding="utf-8",
    )
    return root


def _cli_feature(root: Path):
    features = discover_cli_features(root)
    assert len(features) == 1
    assert features[0].name == "demo"
    assert features[0].reconciliation_status == "RECONCILED"
    return features[0]


def test_ru11_source_backed_discovery_reconciles_cli_and_api(tmp_path: Path) -> None:
    root = _target(tmp_path)
    cli = discover_cli_features(root)
    api = discover_api_features(root)
    assert cli[0].source_anchor["path"] == "src/demo/cli.py"
    assert any(item.name.endswith(":public_api") for item in api)
    assert all(item.source_manifest_digest == cli[0].source_manifest_digest for item in api)


def test_ru11_real_cli_behavior_can_pass_only_with_qualified_oracle(tmp_path: Path) -> None:
    root = _target(tmp_path)
    feature = _cli_feature(root)
    case = BehaviorCase(
        case_id="ok",
        feature_id=feature.feature_id,
        behavior_kind="POSITIVE",
        argv=(sys.executable, "-m", "demo.cli", "ok"),
        expected_exit_code=0,
        expected_json_subset={"status": "ok", "value": 2},
    )
    oracle = qualify_oracle(case, ("REQ-DEMO-OK",))
    plan = build_verification_plan(feature, (case,), (oracle,), root)
    assessment = execute_verification_plan(plan, root, tmp_path / "evidence")[0]
    assert assessment.status == "PASS"
    assert assessment.run_receipt_digest
    assert assessment.predicate_results == {"exit_code": True, "json_subset": True}


def test_ru11_real_target_failure_is_fail_not_tool_error(tmp_path: Path) -> None:
    root = _target(tmp_path)
    feature = _cli_feature(root)
    case = BehaviorCase(
        case_id="bad-body",
        feature_id=feature.feature_id,
        behavior_kind="NEGATIVE",
        argv=(sys.executable, "-m", "demo.cli", "fail"),
        expected_exit_code=0,
        expected_json_subset={"status": "ok"},
    )
    oracle = qualify_oracle(case, ("REQ-DEMO-SAFE",))
    plan = build_verification_plan(feature, (case,), (oracle,), root)
    assessment = execute_verification_plan(plan, root, tmp_path / "evidence")[0]
    assert assessment.status == "FAIL"
    assert assessment.run_receipt_digest
    assert assessment.predicate_results["exit_code"] is False
    assert assessment.predicate_results["json_subset"] is False


def test_ru11_unknown_oracle_and_mock_only_can_never_pass(tmp_path: Path) -> None:
    root = _target(tmp_path)
    feature = _cli_feature(root)
    unknown_case = BehaviorCase(
        case_id="unknown-oracle",
        feature_id=feature.feature_id,
        behavior_kind="POSITIVE",
        argv=(sys.executable, "-m", "demo.cli", "ok"),
        expected_exit_code=0,
    )
    mock_case = BehaviorCase(
        case_id="mock-only",
        feature_id=feature.feature_id,
        behavior_kind="POSITIVE",
        argv=(sys.executable, "-m", "demo.cli", "ok"),
        expected_exit_code=0,
        mock_only=True,
    )
    plan = build_verification_plan(
        feature,
        (unknown_case, mock_case),
        (qualify_oracle(unknown_case, ()), qualify_oracle(mock_case, ("REQ-MOCK",))),
        root,
    )
    assessments = execute_verification_plan(plan, root, tmp_path / "evidence")
    assert [item.status for item in assessments] == ["INSUFFICIENT", "INSUFFICIENT"]
    assert all(item.run_receipt_digest is None for item in assessments)


def test_ru11_zero_cases_and_source_drift_fail_closed(tmp_path: Path) -> None:
    root = _target(tmp_path)
    feature = _cli_feature(root)
    profile = CapabilityProfile()
    with pytest.raises(ValidationError, match="VERIFICATION_PLAN_ZERO_CASES"):
        VerificationPlan(
            feature=feature,
            cases=(),
            oracles=(),
            testability=__import__("bdb_audit.features", fromlist=["assess_testability"]).assess_testability(feature),
            source_manifest_digest=source_manifest(root)["manifest_digest"],
            environment_manifest_digest=environment_manifest(root, profile)["manifest_digest"],
        )

    case = BehaviorCase(
        case_id="drift",
        feature_id=feature.feature_id,
        behavior_kind="POSITIVE",
        argv=(sys.executable, "-m", "demo.cli", "ok"),
        expected_exit_code=0,
    )
    plan = build_verification_plan(feature, (case,), (qualify_oracle(case, ("REQ-DRIFT",)),), root)
    (root / "src" / "demo" / "cli.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="FEATURE_PLAN_SOURCE_DRIFT"):
        execute_verification_plan(plan, root, tmp_path / "evidence")


def test_ru11_stale_pass_is_not_current_pass(tmp_path: Path) -> None:
    root = _target(tmp_path)
    feature = _cli_feature(root)
    case = BehaviorCase(
        case_id="ok",
        feature_id=feature.feature_id,
        behavior_kind="POSITIVE",
        argv=(sys.executable, "-m", "demo.cli", "ok"),
        expected_exit_code=0,
        stdout_contains='"status": "ok"',
    )
    plan = build_verification_plan(feature, (case,), (qualify_oracle(case, ("REQ-OK",)),), root)
    assessment = execute_verification_plan(plan, root, tmp_path / "evidence")[0]
    matrix = feature_status_matrix(
        (feature,),
        (assessment,),
        current_source_manifest_digest="f" * 64,
        current_environment_manifest_digest=plan.environment_manifest_digest,
    )
    assert matrix["entries"][0]["freshness"] == "STALE"
    assert matrix["entries"][0]["status"] == "INSUFFICIENT"

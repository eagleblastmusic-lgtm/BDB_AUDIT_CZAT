"""RU11 real CLI behavior execution and qualification over RU10 receipts."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..core.errors import ValidationError
from ..runner.environments import environment_manifest, source_manifest
from ..runner.specs import CapabilityProfile, ToolRunSpec
from ..runner.supervisor import ToolSupervisor
from ..runner.verification import verify_run_evidence
from .models import BehaviorAssessment, BehaviorCase, OracleAssessment, VerificationPlan


def _json_subset(expected: Any, observed: Any) -> bool:
    if isinstance(expected, dict):
        if not isinstance(observed, dict):
            return False
        return all(key in observed and _json_subset(value, observed[key]) for key, value in expected.items())
    if isinstance(expected, list):
        if not isinstance(observed, list) or len(expected) > len(observed):
            return False
        return all(_json_subset(value, observed[index]) for index, value in enumerate(expected))
    return expected == observed


def _predicate_results(case: BehaviorCase, exit_code: int | None, stdout: str, stderr: str) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    if case.expected_exit_code is not None:
        checks["exit_code"] = exit_code == case.expected_exit_code
    if case.stdout_contains is not None:
        checks["stdout_contains"] = case.stdout_contains in stdout
    if case.stderr_contains is not None:
        checks["stderr_contains"] = case.stderr_contains in stderr
    if case.expected_json_subset is not None:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            checks["json_subset"] = False
        else:
            checks["json_subset"] = _json_subset(dict(case.expected_json_subset), parsed)
    return checks


def _non_run_assessment(case: BehaviorCase, plan: VerificationPlan, status: str, reason: str) -> BehaviorAssessment:
    return BehaviorAssessment(
        case_id=case.case_id,
        feature_id=case.feature_id,
        status=status,
        freshness="ACTIVE",
        source_manifest_digest=plan.source_manifest_digest,
        environment_manifest_digest=plan.environment_manifest_digest,
        reason_codes=(reason,),
    )


def execute_verification_plan(
    plan: VerificationPlan,
    source_root: str | Path,
    evidence_root: str | Path,
    *,
    profile: CapabilityProfile | None = None,
) -> tuple[BehaviorAssessment, ...]:
    """Execute a plan; never infer PASS from an unqualified oracle or missing run."""
    runner_profile = profile or CapabilityProfile()
    current_source = source_manifest(source_root)
    current_env = environment_manifest(source_root, runner_profile)
    if current_source["manifest_digest"] != plan.source_manifest_digest:
        raise ValidationError("FEATURE_PLAN_SOURCE_DRIFT")
    if current_env["manifest_digest"] != plan.environment_manifest_digest:
        raise ValidationError("FEATURE_PLAN_ENVIRONMENT_DRIFT")

    oracle_by_case: dict[str, OracleAssessment] = {item.case_id: item for item in plan.oracles}
    if plan.testability.status == "BLOCKED":
        return tuple(_non_run_assessment(case, plan, "BLOCKED", "FEATURE_TESTABILITY_BLOCKED") for case in plan.cases)
    if plan.testability.status != "TESTABLE":
        return tuple(_non_run_assessment(case, plan, "UNSUPPORTED", "FEATURE_ADAPTER_UNSUPPORTED") for case in plan.cases)

    root = Path(evidence_root).resolve()
    assessments: list[BehaviorAssessment] = []
    for case in plan.cases:
        oracle = oracle_by_case[case.case_id]
        if not oracle.can_qualify:
            assessments.append(_non_run_assessment(case, plan, "INSUFFICIENT", "ORACLE_UNQUALIFIED"))
            continue
        if case.mock_only:
            assessments.append(_non_run_assessment(case, plan, "INSUFFICIENT", "MOCK_ONLY_NOT_PRODUCT_EVIDENCE"))
            continue
        if not case.argv:
            assessments.append(_non_run_assessment(case, plan, "BLOCKED", "BEHAVIOR_EXECUTION_ARGV_MISSING"))
            continue

        case_evidence = root / case.case_id
        spec = ToolRunSpec(
            run_id=f"feature-{plan.digest[:12]}-{case.case_id}",
            source_root=str(source_root),
            evidence_dir=str(case_evidence),
            argv=tuple(case.argv),
            timeout_seconds=120,
            environment={"PYTHONPATH": os.pathsep.join(("src", "."))},
        )
        result = ToolSupervisor(runner_profile).run(spec)
        if result.supervisor_status == "BLOCKED":
            assessments.append(_non_run_assessment(case, plan, "BLOCKED", "RUNNER_BLOCKED"))
            continue
        if result.supervisor_status in {"TIMEOUT", "OUTPUT_LIMIT", "EXECUTION_ERROR", "CLEANUP_FAILED"}:
            assessments.append(BehaviorAssessment(
                case_id=case.case_id,
                feature_id=case.feature_id,
                status="INSUFFICIENT",
                freshness="ACTIVE",
                source_manifest_digest=plan.source_manifest_digest,
                environment_manifest_digest=plan.environment_manifest_digest,
                run_receipt_digest=result.receipt_digest if (case_evidence / "RUN_RECEIPT.json").is_file() else None,
                reason_codes=(f"RUN_{result.supervisor_status}",),
            ))
            continue

        verified = verify_run_evidence(case_evidence)
        try:
            stdout = (case_evidence / "stdout.bin").read_text(encoding="utf-8")
            stderr = (case_evidence / "stderr.bin").read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValidationError("FEATURE_RAW_OUTPUT_UNREADABLE", case.case_id) from exc
        checks = _predicate_results(case, result.target_exit_code, stdout, stderr)
        passed = bool(checks) and all(checks.values())
        assessments.append(BehaviorAssessment(
            case_id=case.case_id,
            feature_id=case.feature_id,
            status="PASS" if passed else "FAIL",
            freshness="ACTIVE",
            source_manifest_digest=plan.source_manifest_digest,
            environment_manifest_digest=plan.environment_manifest_digest,
            run_receipt_digest=str(verified["receipt_digest"]),
            reason_codes=("QUALIFIED_PREDICATE_SATISFIED",) if passed else ("QUALIFIED_PREDICATE_FAILED",),
            predicate_results=checks,
        ))
    return tuple(assessments)


__all__ = ["execute_verification_plan"]

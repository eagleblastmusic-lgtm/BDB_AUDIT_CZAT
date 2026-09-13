"""RU11 public CLI handlers for functional verification."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Sequence

from ..core.errors import ValidationError
from ..runner.environments import environment_manifest, source_manifest
from ..runner.specs import CapabilityProfile
from .discovery import discover_features
from .models import BehaviorCase
from .oracles import qualify_oracle
from .planner import build_verification_plan
from .projection import feature_status_matrix
from .serialization import assessment_from_dict, feature_from_dict, plan_from_dict
from .verification import execute_verification_plan


def _read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise ValidationError("FEATURE_ARTIFACT_NOT_FOUND", str(source))
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("FEATURE_ARTIFACT_PARSE_FAILED", str(source)) from exc
    if not isinstance(data, dict):
        raise ValidationError("FEATURE_ARTIFACT_OBJECT_REQUIRED", str(source))
    return data


def _write_json(path: str | Path, data: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temp, target)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bdb_audit features", description="Source-backed functional verification")
    subs = parser.add_subparsers(dest="subcommand")

    discover = subs.add_parser("discover")
    discover.add_argument("--source", required=True)
    discover.add_argument("--output", required=True)
    discover.add_argument("--json", action="store_true")

    plan = subs.add_parser("plan")
    plan.add_argument("--source", required=True)
    plan.add_argument("--input", required=True, help="JSON with feature_id, cases and oracle bases")
    plan.add_argument("--output", required=True)
    plan.add_argument("--json", action="store_true")

    verify = subs.add_parser("verify")
    verify.add_argument("--source", required=True)
    verify.add_argument("--plan", required=True)
    verify.add_argument("--evidence", required=True)
    verify.add_argument("--output", required=True)
    verify.add_argument("--json", action="store_true")

    matrix = subs.add_parser("matrix")
    matrix.add_argument("--source", required=True)
    matrix.add_argument("--inventory", required=True)
    matrix.add_argument("--assessments", required=True)
    matrix.add_argument("--output", required=True)
    matrix.add_argument("--json", action="store_true")
    return parser


def _emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(f"[{data.get('status', 'INFO')}] {data.get('action', 'features')}")
        for key, value in data.items():
            if key not in {"status", "action"}:
                print(f"  {key}: {value}")


def _case_with_feature(value: Any, feature_id: str) -> BehaviorCase:
    if not isinstance(value, dict):
        raise ValidationError("BEHAVIOR_CASE_INVALID")
    body = dict(value)
    supplied = body.get("feature_id")
    if supplied is not None and supplied != feature_id:
        raise ValidationError("BEHAVIOR_CASE_FEATURE_MISMATCH")
    body["feature_id"] = feature_id
    subset = body.get("expected_json_subset")
    if subset is not None and not isinstance(subset, dict):
        raise ValidationError("BEHAVIOR_JSON_SUBSET_INVALID")
    return BehaviorCase(
        case_id=str(body.get("case_id", "")),
        feature_id=feature_id,
        behavior_kind=str(body.get("behavior_kind", "")),
        argv=tuple(body.get("argv", ())),
        expected_exit_code=body.get("expected_exit_code"),
        stdout_contains=body.get("stdout_contains"),
        stderr_contains=body.get("stderr_contains"),
        expected_json_subset=subset,
        mock_only=bool(body.get("mock_only", False)),
        description=str(body.get("description", "")),
    )


def _plan(source: str, plan_input_path: str) -> dict[str, Any]:
    inventory = discover_features(source)
    request = _read_json(plan_input_path)
    feature_id = str(request.get("feature_id", ""))
    feature_body = next((item for item in inventory["features"] if item.get("feature_id") == feature_id), None)
    if feature_body is None:
        raise ValidationError("FEATURE_ID_NOT_DISCOVERED", feature_id)
    feature = feature_from_dict(feature_body)
    cases = tuple(_case_with_feature(item, feature_id) for item in request.get("cases", ()))
    oracle_bases = request.get("oracles", ())
    if not isinstance(oracle_bases, list):
        raise ValidationError("FEATURE_ORACLE_INPUT_INVALID")
    basis_by_case = {str(item.get("case_id")): item for item in oracle_bases if isinstance(item, dict)}
    oracles = []
    for case in cases:
        basis = basis_by_case.get(case.case_id, {})
        oracles.append(qualify_oracle(
            case,
            tuple(basis.get("requirement_refs", ())),
            independence=str(basis.get("independence", "UNKNOWN")),
            rationale=str(basis.get("rationale", "")),
        ))
    plan = build_verification_plan(feature, cases, tuple(oracles), source)
    return plan.as_dict() | {"plan_digest": plan.digest}


def run_features_cli(argv: Sequence[str]) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    if not args.subcommand:
        parser.print_help()
        return 2
    as_json = bool(getattr(args, "json", False))
    try:
        if args.subcommand == "discover":
            artifact = discover_features(args.source)
            _write_json(args.output, artifact)
            response = {"status": "PASS", "action": "features.discover", "output": str(Path(args.output)), "feature_count": artifact["feature_count"], "source_manifest_digest": artifact["source_manifest_digest"]}
        elif args.subcommand == "plan":
            artifact = _plan(args.source, args.input)
            _write_json(args.output, artifact)
            response = {"status": "PASS", "action": "features.plan", "output": str(Path(args.output)), "plan_digest": artifact["plan_digest"], "case_count": len(artifact["cases"])}
        elif args.subcommand == "verify":
            raw_plan = _read_json(args.plan)
            plan = plan_from_dict(raw_plan)
            if raw_plan.get("plan_digest") != plan.digest:
                raise ValidationError("VERIFICATION_PLAN_DIGEST_MISMATCH")
            assessments = execute_verification_plan(plan, args.source, args.evidence)
            artifact = {
                "schema_version": "BDB-DERIVED-VERIFICATION-RUN-1",
                "authority": "DERIVED_NOT_ACCEPTED_HISTORY",
                "plan_digest": plan.digest,
                "source_manifest_digest": plan.source_manifest_digest,
                "environment_manifest_digest": plan.environment_manifest_digest,
                "assessments": [item.as_dict() for item in assessments],
            }
            _write_json(args.output, artifact)
            response = {"status": "PASS", "action": "features.verify", "output": str(Path(args.output)), "assessment_count": len(assessments), "case_statuses": {item.case_id: item.status for item in assessments}}
        elif args.subcommand == "matrix":
            inventory = _read_json(args.inventory)
            run = _read_json(args.assessments)
            features_raw = inventory.get("features", ())
            assessments_raw = run.get("assessments", ())
            if not isinstance(features_raw, list) or not isinstance(assessments_raw, list):
                raise ValidationError("FEATURE_MATRIX_INPUT_INVALID")
            features = tuple(feature_from_dict(item) for item in features_raw if isinstance(item, dict))
            assessments = tuple(assessment_from_dict(item) for item in assessments_raw if isinstance(item, dict))
            profile = CapabilityProfile()
            current_source = source_manifest(args.source)["manifest_digest"]
            current_env = environment_manifest(args.source, profile)["manifest_digest"]
            artifact = feature_status_matrix(
                features,
                assessments,
                current_source_manifest_digest=current_source,
                current_environment_manifest_digest=current_env,
            )
            _write_json(args.output, artifact)
            response = {"status": "PASS", "action": "features.matrix", "output": str(Path(args.output)), "entry_count": len(artifact["entries"]), "statuses": {item["feature_id"]: item["status"] for item in artifact["entries"]}}
        else:
            raise ValidationError("FEATURE_SUBCOMMAND_INVALID", str(args.subcommand))
        _emit(response, as_json)
        return 0
    except ValidationError as exc:
        response = {"status": "FAIL", "error": exc.code, "detail": exc.detail}
        if as_json:
            print(json.dumps(response, indent=2, sort_keys=True), file=__import__("sys").stderr)
        else:
            print(f"[FAIL] {exc.code}: {exc.detail}", file=__import__("sys").stderr)
        return 1


__all__ = ["run_features_cli"]

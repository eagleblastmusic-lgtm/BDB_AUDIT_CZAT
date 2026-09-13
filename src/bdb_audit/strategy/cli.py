"""RU14 strategy/lane CLI."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from ..core.errors import ValidationError
from .models import ExposureManifest, LanePlan, LaneProposal, StrategyProfile
from .planner import compare_yield_efficiency, plan_lanes, risk_map_from_dict, validate_lane_plan


def _read(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise ValidationError("STRATEGY_INPUT_NOT_FOUND", str(source))
    try:
        body = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("STRATEGY_INPUT_PARSE_FAILED", str(source)) from exc
    if not isinstance(body, dict):
        raise ValidationError("STRATEGY_INPUT_OBJECT_REQUIRED")
    return body


def _write(path: str | Path, body: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temp, target)


def _profile(body: dict[str, Any]) -> StrategyProfile:
    return StrategyProfile(
        profile_id=str(body.get("profile_id", "")),
        total_budget_units=int(body.get("total_budget_units", 0)),
        reserve_budget_units=int(body.get("reserve_budget_units", 0)),
        max_parallel_lanes=int(body.get("max_parallel_lanes", 4)),
        independence_required=bool(body.get("independence_required", True)),
    )


def _exposure(body: dict[str, Any]) -> ExposureManifest:
    return ExposureManifest(
        evaluator_profile=str(body.get("evaluator_profile", "")),
        exposed_artifact_ids=tuple(body.get("exposed_artifact_ids", ())),
        prohibited_artifact_ids=tuple(body.get("prohibited_artifact_ids", ())),
    )


def _lane_plan(body: dict[str, Any]) -> LanePlan:
    profile = _profile(dict(body.get("strategy_profile", {})))
    exposure = _exposure(dict(body.get("exposure_manifest", {})))
    lanes = tuple(LaneProposal(
        lane_id=str(item.get("lane_id", "")), risk_id=str(item.get("risk_id", "")),
        method=str(item.get("method", "")), obligation_keys=tuple(item.get("obligation_keys", ())),
        cost_units=int(item.get("cost_units", 0)), depends_on=tuple(item.get("depends_on", ())),
        evaluator_profile=str(item.get("evaluator_profile", "DEFAULT")),
        unique_root_cause_yield=int(item.get("unique_root_cause_yield", 0)),
    ) for item in body.get("lanes", ()) if isinstance(item, dict))
    return LanePlan(
        plan_id=str(body.get("plan_id", "")), strategy_profile=profile, lanes=lanes,
        reserve_released=bool(body.get("reserve_released", False)), exposure_manifest=exposure,
        authority=str(body.get("authority", "DERIVED_PROPOSAL_ONLY")), limitations=tuple(body.get("limitations", ())),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bdb_audit strategy", description="Adaptive risk/lane planning")
    subs = parser.add_subparsers(dest="subcommand")
    explain = subs.add_parser("explain")
    explain.add_argument("--input", required=True); explain.add_argument("--json", action="store_true")
    validate = subs.add_parser("validate")
    validate.add_argument("--plan", required=True); validate.add_argument("--json", action="store_true")
    plan = subs.add_parser("plan")
    plan.add_argument("--input", required=True); plan.add_argument("--output", required=True)
    plan.add_argument("--release-reserve", action="store_true"); plan.add_argument("--json", action="store_true")
    yield_p = subs.add_parser("yield-compare")
    yield_p.add_argument("--candidate-unique", type=int, required=True); yield_p.add_argument("--candidate-cost", type=int, required=True)
    yield_p.add_argument("--baseline-unique", type=int, required=True); yield_p.add_argument("--baseline-cost", type=int, required=True)
    yield_p.add_argument("--json", action="store_true")
    return parser


def run_cli(argv: Sequence[str]) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    if not args.subcommand:
        parser.print_help(); return 2
    as_json = bool(getattr(args, "json", False))
    try:
        if args.subcommand in {"explain", "plan"}:
            request = _read(args.input)
            profile = _profile(dict(request.get("strategy_profile", {})))
            exposure = _exposure(dict(request.get("exposure_manifest", {})))
            risks_raw = request.get("risks", ())
            if not isinstance(risks_raw, list):
                raise ValidationError("RISK_MAP_INVALID")
            risks = risk_map_from_dict([item for item in risks_raw if isinstance(item, dict)])
            if args.subcommand == "explain":
                response = {"status": "PASS", "action": "strategy.explain", "profile": profile.as_dict(), "risk_map": [item.as_dict() for item in risks], "exposure_manifest": exposure.as_dict(), "authority": "DERIVED_ONLY"}
            else:
                plan = plan_lanes(profile, risks, exposure, reserve_released=args.release_reserve)
                artifact = plan.as_dict(); _write(args.output, artifact)
                response = {"status": "PASS", "action": "strategy.plan", "output": str(Path(args.output)), "plan_digest": artifact["plan_digest"], "lane_count": len(plan.lanes), "limitations": list(plan.limitations)}
        elif args.subcommand == "validate":
            raw = _read(args.plan); plan = _lane_plan(raw); regenerated = plan.as_dict()
            if raw.get("plan_digest") != regenerated["plan_digest"]:
                raise ValidationError("LANE_PLAN_DIGEST_MISMATCH")
            response = validate_lane_plan(plan); response["action"] = "strategy.validate"
        elif args.subcommand == "yield-compare":
            response = compare_yield_efficiency(candidate_unique_root_causes=args.candidate_unique, candidate_cost_units=args.candidate_cost, baseline_unique_root_causes=args.baseline_unique, baseline_cost_units=args.baseline_cost); response["action"] = "strategy.yield-compare"
        else:
            raise ValidationError("STRATEGY_SUBCOMMAND_INVALID", str(args.subcommand))
        if as_json: print(json.dumps(response, indent=2, sort_keys=True))
        else: print(f"[{response.get('status', 'INFO')}] {response.get('action', 'strategy')}")
        return 0
    except ValidationError as exc:
        response = {"status": "FAIL", "error": exc.code, "detail": exc.detail}
        if as_json: print(json.dumps(response, indent=2, sort_keys=True), file=sys.stderr)
        else: print(f"[FAIL] {exc.code}: {exc.detail}", file=sys.stderr)
        return 1


__all__ = ["run_cli"]

"""RU14 command aliases for lane, budget, and exposure views."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from ..core.errors import ValidationError
from .cli import _lane_plan, _read, run_cli as run_strategy_cli
from .planner import validate_lane_plan


def run_lanes_cli(argv: Sequence[str]) -> int:
    if not argv or argv[0] not in {"plan", "explain"}:
        print("usage: bdb_audit lanes {plan|explain} ...", file=sys.stderr)
        return 2
    return run_strategy_cli(argv)


def _status_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog)
    subs = parser.add_subparsers(dest="subcommand")
    status = subs.add_parser("status")
    status.add_argument("--plan", required=True)
    status.add_argument("--json", action="store_true")
    return parser


def run_budget_cli(argv: Sequence[str]) -> int:
    parser = _status_parser("bdb_audit budget")
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    if args.subcommand != "status":
        parser.print_help(); return 2
    try:
        plan = _lane_plan(_read(args.plan)); verified = validate_lane_plan(plan)
        response = {"status": "PASS", "action": "budget.status", "spent_budget_units": verified["spent_budget_units"], "available_budget_units": verified["available_budget_units"], "reserve_budget_units": verified["reserve_budget_units"], "reserve_released": verified["reserve_released"]}
        print(json.dumps(response, indent=2, sort_keys=True) if args.json else response)
        return 0
    except ValidationError as exc:
        response = {"status": "FAIL", "error": exc.code, "detail": exc.detail}
        print(json.dumps(response, indent=2, sort_keys=True) if args.json else response, file=sys.stderr); return 1


def run_exposure_cli(argv: Sequence[str]) -> int:
    parser = _status_parser("bdb_audit exposure")
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    if args.subcommand != "status":
        parser.print_help(); return 2
    try:
        plan = _lane_plan(_read(args.plan)); validate_lane_plan(plan)
        response = {"status": "PASS", "action": "exposure.status", "exposure_manifest": plan.exposure_manifest.as_dict(), "authority": plan.authority}
        print(json.dumps(response, indent=2, sort_keys=True) if args.json else response)
        return 0
    except ValidationError as exc:
        response = {"status": "FAIL", "error": exc.code, "detail": exc.detail}
        print(json.dumps(response, indent=2, sort_keys=True) if args.json else response, file=sys.stderr); return 1


__all__ = ["run_lanes_cli", "run_budget_cli", "run_exposure_cli"]

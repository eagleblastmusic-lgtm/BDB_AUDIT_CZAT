"""Normative Command-Line Interface for BDB Audit v2 (R5.3 §109).

Commands:
  campaign create   Initialize a new campaign with genesis objects
  campaign status   Display status projection of an active campaign
  stage prepare     Prepare and validate an operational stage
  lane prepare      Prepare and qualify an operational lane
  validate          Validate an artifact against contract schemas
  continue          Evaluate campaign continuation and next required action
  stop evaluate     Evaluate the STOP gate from accepted history or preview input
  self-test         Execute offline-critical self-test suite
  build             Trigger deterministic standalone single-file build
  capabilities      Report distribution capability matrix
  ui                Launch interactive terminal interface
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .coordinator.operations import AuditOperationApi
from .core.errors import ValidationError
from .stop.operation import evaluate_stop_gate
from .version import APP_VERSION, BUILD_ID

# Explicit Exit Codes
EXIT_SUCCESS = 0
EXIT_DOMAIN_ERROR = 1
EXIT_MALFORMED_ARGS = 2
EXIT_CAMPAIGN_NOT_FOUND = 3
EXIT_CONFLICT_ERROR = 4

SOURCE_CAPABILITIES = {
    "build": "SUPPORTED",
    "self_test": "SUPPORTED",
    "audit_cli": "SUPPORTED",
}


def _ensure_utf8_stdio() -> None:
    """Make CLI bytes deterministic on Windows pipes/consoles when possible."""
    for stream in (sys.stdout, sys.stderr):
        encoding = str(getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if encoding == "utf8":
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="strict")
            except (AttributeError, ValueError):
                # Some in-memory/captured streams intentionally cannot be reconfigured.
                pass


def _emit_output(data: dict, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        status = data.get("status", "INFO")
        print(f"[{status}] {data.get('action', data.get('command', 'OK'))}")
        for k, v in data.items():
            if k not in ("status", "action", "command"):
                print(f"  {k}: {v}")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bdb_audit",
        description="BDB Audit v2 — Canonical Audit Automation Engine",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"BDB Audit v{APP_VERSION} ({BUILD_ID})")

    subparsers = parser.add_subparsers(dest="command", help="Operational commands")

    audit_p = subparsers.add_parser("audit", help="Audit user workflow")
    audit_subs = audit_p.add_subparsers(dest="subcommand", help="Audit operations")
    a_start_p = audit_subs.add_parser("start", help="Start new audit campaign")
    a_start_p.add_argument("--store", required=True, help="Path to SQLite history store")
    a_start_p.add_argument("--target", help="Target repository URL or path")
    a_start_p.add_argument("--commit-sha", help="Target commit SHA")
    a_start_p.add_argument("--seed", default="audit_campaign", help="Campaign seed string")
    a_start_p.add_argument("--campaign-id", help="Explicit campaign ID")
    a_start_p.add_argument("--json", action="store_true", help="Machine-readable output")

    a_res_p = audit_subs.add_parser("resume", help="Resume active audit campaign")
    a_res_p.add_argument("--store", required=True, help="Path to SQLite history store")
    a_res_p.add_argument("--json", action="store_true", help="Machine-readable output")

    a_stat_p = audit_subs.add_parser("status", help="Get audit campaign status")
    a_stat_p.add_argument("--store", required=True, help="Path to SQLite history store")
    a_stat_p.add_argument("--json", action="store_true", help="Machine-readable output")

    campaign_p = subparsers.add_parser("campaign", help="Campaign lifecycle management")
    campaign_subs = campaign_p.add_subparsers(dest="subcommand", help="Campaign operations")

    create_p = campaign_subs.add_parser("create", help="Create new campaign")
    create_p.add_argument("--store", required=True, help="Path to SQLite history store")
    create_p.add_argument("--seed", default="default_campaign", help="Campaign seed string")
    create_p.add_argument("--campaign-id", help="Explicit campaign ID")
    create_p.add_argument("--json", action="store_true", help="Machine-readable output")

    status_p = campaign_subs.add_parser("status", help="Get campaign status")
    status_p.add_argument("--store", required=True, help="Path to SQLite history store")
    status_p.add_argument("--json", action="store_true", help="Machine-readable output")

    concl_p = campaign_subs.add_parser("conclude", help="Conclude campaign")
    concl_p.add_argument("--store", required=True, help="Path to SQLite history store")
    concl_p.add_argument("--termination-state", choices=["COMPLETED", "COMPLETED_LIMITED"], help="Termination state")
    concl_p.add_argument("--statement", default="Campaign concluded via post-E5 finalization", help="Conclusion statement")
    concl_p.add_argument("--json", action="store_true", help="Machine-readable output")

    stage_p = subparsers.add_parser("stage", help="Stage lifecycle management")
    stage_subs = stage_p.add_subparsers(dest="subcommand", help="Stage operations")
    st_prep_p = stage_subs.add_parser("prepare", help="Prepare an operational stage")
    st_prep_p.add_argument("--store", required=True, help="Path to SQLite history store")
    st_prep_p.add_argument("--stage", required=True, help="Canonical StageSpec key E1..E5")
    st_prep_p.add_argument("--stage-spec-revision", default="1", help="StageSpec revision")
    st_prep_p.add_argument("--json", action="store_true", help="Machine-readable output")

    st_qual_p = stage_subs.add_parser("qualify", help="Qualify and complete an operational stage")
    st_qual_p.add_argument("--store", required=True, help="Path to SQLite history store")
    st_qual_p.add_argument("--stage", required=True, help="Canonical StageSpec key E1..E5")
    st_qual_p.add_argument("--json", action="store_true", help="Machine-readable output")

    lane_p = subparsers.add_parser("lane", help="Lane lifecycle management")
    lane_subs = lane_p.add_subparsers(dest="subcommand", help="Lane operations")
    ln_prep_p = lane_subs.add_parser("prepare", help="Prepare an operational lane")
    ln_prep_p.add_argument("--store", required=True, help="Path to SQLite history store")
    ln_prep_p.add_argument("--stage", required=True, help="Parent canonical StageSpec key E1..E5")
    ln_prep_p.add_argument("--slot", required=True, help="Lane slot identifier")
    ln_prep_p.add_argument("--lane-spec-revision", default="1", help="LaneSpec revision")
    ln_prep_p.add_argument("--json", action="store_true", help="Machine-readable output")

    val_p = subparsers.add_parser("validate", help="Validate an artifact against contract schemas")
    val_p.add_argument("--artifact", required=True, help="Path to JSON artifact file")
    val_p.add_argument("--kind", help="Expected registered contract kind")
    val_p.add_argument("--json", action="store_true", help="Machine-readable output")

    cont_p = subparsers.add_parser("continue", help="Evaluate campaign continuation")
    cont_p.add_argument("--store", required=True, help="Path to SQLite history store")
    cont_p.add_argument("--json", action="store_true", help="Machine-readable output")

    stop_p = subparsers.add_parser("stop", help="STOP gate operations")
    stop_subs = stop_p.add_subparsers(dest="subcommand", help="STOP gate operations")
    stop_eval_p = stop_subs.add_parser("evaluate", help="Evaluate the STOP gate")
    stop_eval_p.add_argument("--store", required=True, help="Path to SQLite history store")
    stop_eval_p.add_argument(
        "--input",
        help="Optional STOP input JSON file. File inputs are preview-only and never become accepted authority.",
    )
    stop_eval_p.add_argument(
        "--e6-plan-approved",
        action="store_true",
        help="Evaluate with an already-approved bounded E6 plan",
    )
    stop_eval_p.add_argument("--json", action="store_true", help="Machine-readable output")

    st_p = subparsers.add_parser("self-test", help="Execute offline-critical self-test suite")
    st_p.add_argument("--deep", action="store_true", help="Include deep mutation and property checks")
    st_p.add_argument("--json", action="store_true", help="Machine-readable output")

    bld_p = subparsers.add_parser("build", help="Trigger deterministic standalone build")
    bld_p.add_argument("--output", help="Custom output path for standalone file")
    bld_p.add_argument("--json", action="store_true", help="Machine-readable output")

    cap_p = subparsers.add_parser("capabilities", help="Report capabilities of this distribution")
    cap_p.add_argument("--json", action="store_true", help="Machine-readable output")

    subparsers.add_parser("ui", help="Launch interactive UI")

    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    _ensure_utf8_stdio()
    parser = create_parser()

    if argv is not None and len(argv) == 0:
        parser.print_help()
        return EXIT_SUCCESS

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else EXIT_MALFORMED_ARGS

    if not args.command:
        parser.print_help()
        return EXIT_SUCCESS

    api = AuditOperationApi()
    is_json = getattr(args, "json", False)

    try:
        if args.command == "audit":
            if args.subcommand == "start":
                res = api.create_campaign(args.store, seed=args.seed, campaign_id=args.campaign_id, target_repo=args.target, commit_sha=args.commit_sha)
                prep_e1 = api.prepare_stage(args.store, "E1")
                res["stage_e1_prepared"] = prep_e1["status"] == "SUCCESS"
                _emit_output(res, is_json)
                return EXIT_SUCCESS
            elif args.subcommand == "resume":
                res = api.continue_campaign(args.store)
                _emit_output(res, is_json)
                return EXIT_SUCCESS
            elif args.subcommand == "status":
                res = api.get_campaign_status(args.store)
                _emit_output(res, is_json)
                return EXIT_SUCCESS
            else:
                parser.parse_args(["audit", "--help"])
                return EXIT_MALFORMED_ARGS

        elif args.command == "campaign":
            if args.subcommand == "create":
                res = api.create_campaign(args.store, seed=args.seed, campaign_id=args.campaign_id)
                _emit_output(res, is_json)
                return EXIT_SUCCESS
            elif args.subcommand == "status":
                res = api.get_campaign_status(args.store)
                _emit_output(res, is_json)
                return EXIT_SUCCESS
            elif args.subcommand == "conclude":
                res = api.conclude_campaign(args.store, termination_state=args.termination_state, bounded_statement=args.statement)
                _emit_output(res, is_json)
                return EXIT_SUCCESS
            else:
                parser.parse_args(["campaign", "--help"])
                return EXIT_MALFORMED_ARGS

        elif args.command == "stage":
            if args.subcommand == "prepare":
                res = api.prepare_stage(args.store, stage_id=args.stage, stage_spec_revision=args.stage_spec_revision)
                _emit_output(res, is_json)
                return EXIT_SUCCESS
            elif args.subcommand == "qualify":
                res = api.qualify_stage(args.store, stage_id=args.stage)
                _emit_output(res, is_json)
                return EXIT_SUCCESS
            else:
                parser.parse_args(["stage", "--help"])
                return EXIT_MALFORMED_ARGS

        elif args.command == "lane":
            if args.subcommand == "prepare":
                res = api.prepare_lane(args.store, stage_id=args.stage, slot=args.slot, lane_spec_revision=args.lane_spec_revision)
                _emit_output(res, is_json)
                return EXIT_SUCCESS
            else:
                parser.parse_args(["lane", "--help"])
                return EXIT_MALFORMED_ARGS

        elif args.command == "validate":
            res = api.validate_artifact(args.artifact, expected_kind=args.kind)
            _emit_output(res, is_json)
            return EXIT_SUCCESS

        elif args.command == "continue":
            res = api.continue_campaign(args.store)
            _emit_output(res, is_json)
            return EXIT_SUCCESS

        elif args.command == "stop":
            if args.subcommand == "evaluate":
                if args.input:
                    res = evaluate_stop_gate(
                        args.store,
                        stop_input_path=args.input,
                        e6_plan_approved=args.e6_plan_approved,
                    )
                else:
                    res = api.evaluate_stop_gate(
                        args.store,
                        e6_plan_approved=args.e6_plan_approved,
                    )
                _emit_output(res, is_json)
                return EXIT_SUCCESS
            parser.parse_args(["stop", "--help"])
            return EXIT_MALFORMED_ARGS

        elif args.command == "self-test":
            res = api.run_self_test(deep=args.deep)
            _emit_output(res, is_json)
            return EXIT_SUCCESS if res.get("status") == "PASS" else EXIT_DOMAIN_ERROR

        elif args.command == "build":
            res = api.run_build(output_path=args.output)
            _emit_output(res, is_json)
            return EXIT_SUCCESS

        elif args.command == "capabilities":
            res = {
                "status": "SUCCESS",
                "distribution": "source",
                "app_version": APP_VERSION,
                "build_id": BUILD_ID,
                "capabilities": SOURCE_CAPABILITIES,
            }
            _emit_output(res, is_json)
            return EXIT_SUCCESS

        elif args.command == "ui":
            from .ui import run_ui
            return run_ui()

        else:
            parser.print_help()
            return EXIT_MALFORMED_ARGS

    except ValidationError as exc:
        err_code = getattr(exc, "code", exc.args[0] if exc.args else "")
        err_detail = getattr(exc, "detail", str(exc))
        err_data = {"status": "FAIL", "error": err_code, "detail": err_detail}
        if is_json:
            print(json.dumps(err_data, indent=2, sort_keys=True), file=sys.stderr)
        else:
            print(f"[FAIL] {err_code}: {err_detail}", file=sys.stderr)

        if err_code in ("CAMPAIGN_NOT_FOUND", "ARTIFACT_FILE_NOT_FOUND", "STOP_INPUT_FILE_NOT_FOUND"):
            return EXIT_CAMPAIGN_NOT_FOUND
        elif err_code in ("CAMPAIGN_ALREADY_EXISTS", "STALE_REF"):
            return EXIT_CONFLICT_ERROR
        return EXIT_DOMAIN_ERROR

    except Exception as exc:
        err_data = {"status": "ERROR", "error": "INTERNAL_ERROR", "detail": str(exc)}
        if is_json:
            print(json.dumps(err_data, indent=2, sort_keys=True), file=sys.stderr)
        else:
            print(f"[ERROR] INTERNAL_ERROR: {exc}", file=sys.stderr)
        return EXIT_DOMAIN_ERROR


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()

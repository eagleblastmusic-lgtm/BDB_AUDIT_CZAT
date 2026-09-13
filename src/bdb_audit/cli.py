"""Normative Command-Line Interface for BDB Audit v2 (R5.3 §109)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .coordinator.operations import AuditOperationApi
from .core.errors import ValidationError
from .history.store import TransactionalHistoryStore
from .remediation.models import remediation_plan_from_dict
from .remediation.planner import RemediationPlanner
from .remediation.validation import validate_remediation_plan
from .report import (
    ReportBuilder,
    export_report_bundle,
    render_html,
    render_markdown,
    validate_q09,
    verify_report_bundle,
)
from .stop.operation import evaluate_stop_gate
from .version import APP_VERSION, BUILD_ID

EXIT_SUCCESS = 0
EXIT_DOMAIN_ERROR = 1
EXIT_MALFORMED_ARGS = 2
EXIT_CAMPAIGN_NOT_FOUND = 3
EXIT_CONFLICT_ERROR = 4

SOURCE_CAPABILITIES = {
    "build": "SUPPORTED",
    "self_test": "SUPPORTED",
    "audit_cli": "SUPPORTED",
    "report_export": "SUPPORTED",
    "remediation_plan": "SUPPORTED",
}


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        encoding = str(getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if encoding == "utf8":
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="strict")
            except (AttributeError, ValueError):
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


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


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
    a_start_p.add_argument("--store", required=True)
    a_start_p.add_argument("--target")
    a_start_p.add_argument("--commit-sha")
    a_start_p.add_argument("--seed", default="audit_campaign")
    a_start_p.add_argument("--campaign-id")
    a_start_p.add_argument("--json", action="store_true")
    a_res_p = audit_subs.add_parser("resume", help="Resume active audit campaign")
    a_res_p.add_argument("--store", required=True)
    a_res_p.add_argument("--json", action="store_true")
    a_stat_p = audit_subs.add_parser("status", help="Get audit campaign status")
    a_stat_p.add_argument("--store", required=True)
    a_stat_p.add_argument("--json", action="store_true")

    campaign_p = subparsers.add_parser("campaign", help="Campaign lifecycle management")
    campaign_subs = campaign_p.add_subparsers(dest="subcommand", help="Campaign operations")
    create_p = campaign_subs.add_parser("create", help="Create new campaign")
    create_p.add_argument("--store", required=True)
    create_p.add_argument("--seed", default="default_campaign")
    create_p.add_argument("--campaign-id")
    create_p.add_argument("--json", action="store_true")
    status_p = campaign_subs.add_parser("status", help="Get campaign status")
    status_p.add_argument("--store", required=True)
    status_p.add_argument("--json", action="store_true")
    concl_p = campaign_subs.add_parser("conclude", help="Conclude campaign")
    concl_p.add_argument("--store", required=True)
    concl_p.add_argument("--termination-state", choices=["COMPLETED", "COMPLETED_LIMITED"])
    concl_p.add_argument("--statement", default="Campaign concluded via post-E5 finalization")
    concl_p.add_argument("--json", action="store_true")

    stage_p = subparsers.add_parser("stage", help="Stage lifecycle management")
    stage_subs = stage_p.add_subparsers(dest="subcommand", help="Stage operations")
    st_prep_p = stage_subs.add_parser("prepare", help="Prepare an operational stage")
    st_prep_p.add_argument("--store", required=True)
    st_prep_p.add_argument("--stage", required=True)
    st_prep_p.add_argument("--stage-spec-revision", default="1")
    st_prep_p.add_argument("--json", action="store_true")
    st_qual_p = stage_subs.add_parser("qualify", help="Qualify and complete an operational stage")
    st_qual_p.add_argument("--store", required=True)
    st_qual_p.add_argument("--stage", required=True)
    st_qual_p.add_argument("--json", action="store_true")

    lane_p = subparsers.add_parser("lane", help="Lane lifecycle management")
    lane_subs = lane_p.add_subparsers(dest="subcommand", help="Lane operations")
    ln_prep_p = lane_subs.add_parser("prepare", help="Prepare an operational lane")
    ln_prep_p.add_argument("--store", required=True)
    ln_prep_p.add_argument("--stage", required=True)
    ln_prep_p.add_argument("--slot", required=True)
    ln_prep_p.add_argument("--lane-spec-revision", default="1")
    ln_prep_p.add_argument("--json", action="store_true")

    val_p = subparsers.add_parser("validate", help="Validate an artifact against contract schemas")
    val_p.add_argument("--artifact", required=True)
    val_p.add_argument("--kind")
    val_p.add_argument("--json", action="store_true")

    cont_p = subparsers.add_parser("continue", help="Evaluate campaign continuation")
    cont_p.add_argument("--store", required=True)
    cont_p.add_argument("--json", action="store_true")

    stop_p = subparsers.add_parser("stop", help="STOP gate operations")
    stop_subs = stop_p.add_subparsers(dest="subcommand", help="STOP gate operations")
    stop_eval_p = stop_subs.add_parser("evaluate", help="Evaluate the STOP gate")
    stop_eval_p.add_argument("--store", required=True)
    stop_eval_p.add_argument("--input", help="Optional STOP input JSON file; preview-only")
    stop_eval_p.add_argument("--e6-plan-approved", action="store_true")
    stop_eval_p.add_argument("--json", action="store_true")

    report_p = subparsers.add_parser("report", help="Evidence-backed report operations")
    report_subs = report_p.add_subparsers(dest="subcommand", help="Report operations")
    report_export = report_subs.add_parser("export", help="Export report or verified bundle")
    report_export.add_argument("--store", required=True)
    report_export.add_argument("--output", required=True)
    report_export.add_argument("--format", choices=["bundle", "json", "markdown", "html"], default="bundle")
    report_export.add_argument("--full-assurance", action="store_true", help="Require Q09 FULL assurance")
    report_export.add_argument("--json", action="store_true")
    report_verify = report_subs.add_parser("verify", help="Verify a report bundle")
    report_verify.add_argument("--bundle", required=True)
    report_verify.add_argument("--json", action="store_true")

    remediation_p = subparsers.add_parser("remediation", help="Proposed remediation-plan operations")
    remediation_subs = remediation_p.add_subparsers(dest="subcommand", help="Remediation operations")
    remediation_export = remediation_subs.add_parser("export", help="Export proposed remediation plan")
    remediation_export.add_argument("--store", required=True)
    remediation_export.add_argument("--output", required=True)
    remediation_export.add_argument("--json", action="store_true")
    remediation_validate = remediation_subs.add_parser("validate", help="Validate proposed remediation plan")
    remediation_validate.add_argument("--plan", required=True)
    remediation_validate.add_argument("--json", action="store_true")

    st_p = subparsers.add_parser("self-test", help="Execute offline-critical self-test suite")
    st_p.add_argument("--deep", action="store_true")
    st_p.add_argument("--json", action="store_true")
    bld_p = subparsers.add_parser("build", help="Trigger deterministic standalone build")
    bld_p.add_argument("--output")
    bld_p.add_argument("--json", action="store_true")
    cap_p = subparsers.add_parser("capabilities", help="Report distribution capability matrix")
    cap_p.add_argument("--json", action="store_true")
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
            elif args.subcommand == "resume":
                res = api.continue_campaign(args.store)
            elif args.subcommand == "status":
                res = api.get_campaign_status(args.store)
            else:
                parser.parse_args(["audit", "--help"])
                return EXIT_MALFORMED_ARGS
            _emit_output(res, is_json)
            return EXIT_SUCCESS

        if args.command == "campaign":
            if args.subcommand == "create":
                res = api.create_campaign(args.store, seed=args.seed, campaign_id=args.campaign_id)
            elif args.subcommand == "status":
                res = api.get_campaign_status(args.store)
            elif args.subcommand == "conclude":
                res = api.conclude_campaign(args.store, termination_state=args.termination_state, bounded_statement=args.statement)
            else:
                parser.parse_args(["campaign", "--help"])
                return EXIT_MALFORMED_ARGS
            _emit_output(res, is_json)
            return EXIT_SUCCESS

        if args.command == "stage":
            if args.subcommand == "prepare":
                res = api.prepare_stage(args.store, stage_id=args.stage, stage_spec_revision=args.stage_spec_revision)
            elif args.subcommand == "qualify":
                res = api.qualify_stage(args.store, stage_id=args.stage)
            else:
                parser.parse_args(["stage", "--help"])
                return EXIT_MALFORMED_ARGS
            _emit_output(res, is_json)
            return EXIT_SUCCESS

        if args.command == "lane":
            if args.subcommand != "prepare":
                parser.parse_args(["lane", "--help"])
                return EXIT_MALFORMED_ARGS
            res = api.prepare_lane(args.store, stage_id=args.stage, slot=args.slot, lane_spec_revision=args.lane_spec_revision)
            _emit_output(res, is_json)
            return EXIT_SUCCESS

        if args.command == "validate":
            res = api.validate_artifact(args.artifact, expected_kind=args.kind)
            _emit_output(res, is_json)
            return EXIT_SUCCESS

        if args.command == "continue":
            res = api.continue_campaign(args.store)
            _emit_output(res, is_json)
            return EXIT_SUCCESS

        if args.command == "stop":
            if args.subcommand != "evaluate":
                parser.parse_args(["stop", "--help"])
                return EXIT_MALFORMED_ARGS
            if args.input:
                res = evaluate_stop_gate(args.store, stop_input_path=args.input, e6_plan_approved=args.e6_plan_approved)
            else:
                res = api.evaluate_stop_gate(args.store, e6_plan_approved=args.e6_plan_approved)
            _emit_output(res, is_json)
            return EXIT_SUCCESS

        if args.command == "report":
            if args.subcommand == "verify":
                res = verify_report_bundle(args.bundle)
                _emit_output(res, is_json)
                return EXIT_SUCCESS
            if args.subcommand != "export":
                parser.parse_args(["report", "--help"])
                return EXIT_MALFORMED_ARGS
            store = TransactionalHistoryStore(args.store)
            if args.format == "bundle":
                res = export_report_bundle(store, args.output, requested_full_assurance=args.full_assurance)
            else:
                model = ReportBuilder(store).build_current()
                plan = RemediationPlanner(model).build()
                validate_q09(store, model, plan, requested_full_assurance=args.full_assurance)
                output = Path(args.output)
                if args.format == "json":
                    text = json.dumps(model.as_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
                elif args.format == "markdown":
                    text = render_markdown(model)
                else:
                    text = render_html(model)
                _write_text(output, text)
                res = {
                    "status": "SUCCESS",
                    "format": args.format,
                    "output": str(output),
                    "report_model_sha256": model.report_model_sha256,
                    "report_scope": model.report_scope,
                }
            _emit_output(res, is_json)
            return EXIT_SUCCESS

        if args.command == "remediation":
            if args.subcommand == "export":
                store = TransactionalHistoryStore(args.store)
                model = ReportBuilder(store).build_current()
                plan = RemediationPlanner(model).build()
                validate_q09(store, model, plan)
                output = Path(args.output)
                _write_text(output, json.dumps(plan.as_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n")
                res = {"status": "SUCCESS", "output": str(output), "plan_sha256": plan.plan_sha256, "state": "PROPOSED"}
            elif args.subcommand == "validate":
                path = Path(args.plan)
                if not path.is_file():
                    raise ValidationError("REMEDIATION_PLAN_FILE_NOT_FOUND", str(path))
                plan = remediation_plan_from_dict(json.loads(path.read_text(encoding="utf-8")))
                validate_remediation_plan(plan)
                res = {"status": "PASS", "plan_sha256": plan.plan_sha256, "state": plan.status}
            else:
                parser.parse_args(["remediation", "--help"])
                return EXIT_MALFORMED_ARGS
            _emit_output(res, is_json)
            return EXIT_SUCCESS

        if args.command == "self-test":
            res = api.run_self_test(deep=args.deep)
            _emit_output(res, is_json)
            return EXIT_SUCCESS if res.get("status") == "PASS" else EXIT_DOMAIN_ERROR

        if args.command == "build":
            res = api.run_build(output_path=args.output)
            _emit_output(res, is_json)
            return EXIT_SUCCESS

        if args.command == "capabilities":
            res = {
                "status": "SUCCESS",
                "distribution": "source",
                "app_version": APP_VERSION,
                "build_id": BUILD_ID,
                "capabilities": SOURCE_CAPABILITIES,
            }
            _emit_output(res, is_json)
            return EXIT_SUCCESS

        if args.command == "ui":
            from .ui import run_ui
            return run_ui()

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
        if err_code in (
            "CAMPAIGN_NOT_FOUND", "ARTIFACT_FILE_NOT_FOUND", "STOP_INPUT_FILE_NOT_FOUND",
            "REMEDIATION_PLAN_FILE_NOT_FOUND", "REPORT_BUNDLE_CONTROL_FILE_MISSING",
        ):
            return EXIT_CAMPAIGN_NOT_FOUND
        if err_code in ("CAMPAIGN_ALREADY_EXISTS", "STALE_REF"):
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

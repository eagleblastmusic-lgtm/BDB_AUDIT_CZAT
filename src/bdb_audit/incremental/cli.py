"""RU16 incremental/regression CLI surfaces."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from .. import legacy_cli
from ..core.errors import ValidationError
from .models import ChangeImpactMap, EvidenceReuseAssessment, RequalificationPlan
from .planner import assess_evidence_reuse, build_change_impact, build_requalification_plan, revision_from_dict, run_regression_plan, select_successor


def _read(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise ValidationError("INCREMENTAL_ARTIFACT_NOT_FOUND", str(source))
    try:
        body = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("INCREMENTAL_ARTIFACT_PARSE_FAILED", str(source)) from exc
    if not isinstance(body, dict):
        raise ValidationError("INCREMENTAL_ARTIFACT_OBJECT_REQUIRED")
    return body


def _write(path: str | Path, body: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temp, target)


def run_audit_cli(argv: Sequence[str]) -> int:
    if not argv or argv[0] not in {"diff", "successor"}:
        return legacy_cli.run_cli(["audit", *argv])
    parser = argparse.ArgumentParser(prog="bdb_audit audit")
    subs = parser.add_subparsers(dest="subcommand")
    diff = subs.add_parser("diff")
    diff.add_argument("--from", dest="from_path", required=True)
    diff.add_argument("--to", dest="to_path", required=True)
    diff.add_argument("--output")
    diff.add_argument("--json", action="store_true")
    succ = subs.add_parser("successor")
    succ.add_argument("--predecessor", required=True)
    succ.add_argument("--successors", required=True)
    succ.add_argument("--select", required=True)
    succ.add_argument("--output")
    succ.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(list(argv))
        if args.subcommand == "diff":
            predecessor = revision_from_dict(_read(args.from_path))
            successor = revision_from_dict(_read(args.to_path))
            result = build_change_impact(predecessor, successor).as_dict()
            result["status"] = "PASS"
            result["action"] = "audit.diff"
        else:
            predecessor = revision_from_dict(_read(args.predecessor))
            raw = _read(args.successors)
            successors_raw = raw.get("successors", ())
            if not isinstance(successors_raw, list):
                raise ValidationError("SUCCESSOR_LIST_INVALID")
            successors = tuple(revision_from_dict(item) for item in successors_raw if isinstance(item, dict))
            selection = select_successor(predecessor, successors, args.select)
            result = {"status": "PASS", "action": "audit.successor", "selection": selection.as_dict()}
        if getattr(args, "output", None):
            _write(args.output, result)
        print(json.dumps(result, indent=2, sort_keys=True) if args.json else result)
        return 0
    except ValidationError as exc:
        result = {"status": "FAIL", "error": exc.code, "detail": exc.detail}
        print(json.dumps(result, indent=2, sort_keys=True), file=sys.stderr)
        return 1


def run_evidence_cli(argv: Sequence[str]) -> int:
    if not argv or argv[0] != "reuse-explain":
        return legacy_cli.run_cli(["evidence", *argv])
    parser = argparse.ArgumentParser(prog="bdb_audit evidence reuse-explain")
    parser.add_argument("reuse-explain", nargs="?")
    parser.add_argument("--predecessor", required=True)
    parser.add_argument("--successor", required=True)
    parser.add_argument("--impact", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    parser.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(list(argv))
        predecessor = revision_from_dict(_read(args.predecessor))
        successor = revision_from_dict(_read(args.successor))
        impact_raw = _read(args.impact)
        impact = build_change_impact(predecessor, successor, uncertain_paths=tuple(impact_raw.get("uncertain_impacts", ())))
        request = _read(args.input)
        assessment = assess_evidence_reuse(
            str(request.get("evidence_id", "")),
            predecessor,
            successor,
            impact,
            scope_paths=tuple(request.get("scope_paths", ())),
            environment_profile=str(request.get("environment_profile", "")),
            evidence_refs=tuple(request.get("evidence_refs", ())),
            evidence_environment_digest=str(request.get("evidence_environment_digest", "")),
        )
        result = {"status": "PASS", "action": "evidence.reuse-explain", "assessment": assessment.as_dict()}
        if args.output:
            _write(args.output, result)
        print(json.dumps(result, indent=2, sort_keys=True) if args.json else result)
        return 0
    except ValidationError as exc:
        result = {"status": "FAIL", "error": exc.code, "detail": exc.detail}
        print(json.dumps(result, indent=2, sort_keys=True), file=sys.stderr)
        return 1


def _plan_from_dict(body: dict[str, Any]) -> RequalificationPlan:
    return RequalificationPlan(
        plan_id=str(body.get("plan_id", "")),
        impact_digest=str(body.get("impact_digest", "")),
        required_paths=tuple(body.get("required_paths", ())),
        reusable_evidence_ids=tuple(body.get("reusable_evidence_ids", ())),
        pending_evidence_ids=tuple(body.get("pending_evidence_ids", ())),
        coverage_denominator=int(body.get("coverage_denominator", 0)),
        state=str(body.get("state", "REUSE_PENDING")),
    )


def run_regression_cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="bdb_audit regression")
    subs = parser.add_subparsers(dest="subcommand")
    plan_p = subs.add_parser("plan")
    plan_p.add_argument("--impact", required=True)
    plan_p.add_argument("--reuse", required=True)
    plan_p.add_argument("--output", required=True)
    plan_p.add_argument("--json", action="store_true")
    run_p = subs.add_parser("run")
    run_p.add_argument("--plan", required=True)
    run_p.add_argument("--results", required=True)
    run_p.add_argument("--output")
    run_p.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(list(argv))
        if not args.subcommand:
            parser.print_help()
            return 2
        if args.subcommand == "plan":
            impact_raw = _read(args.impact)
            reuse_raw = _read(args.reuse)
            impact = ChangeImpactMap(
                str(impact_raw.get("predecessor_revision_id", "")),
                str(impact_raw.get("successor_revision_id", "")),
                tuple(impact_raw.get("direct_changes", ())),
                tuple(impact_raw.get("propagated_impacts", ())),
                tuple(impact_raw.get("uncertain_impacts", ())),
                tuple(impact_raw.get("change_dimensions", ())),
            )
            assessments = tuple(
                EvidenceReuseAssessment(
                    str(item.get("evidence_id", "")),
                    str(item.get("predecessor_revision_id", "")),
                    str(item.get("successor_revision_id", "")),
                    tuple(item.get("scope_paths", ())),
                    str(item.get("environment_profile", "")),
                    tuple(item.get("evidence_refs", ())),
                    str(item.get("status", "PENDING")),
                    tuple(item.get("reason_codes", ())),
                )
                for item in reuse_raw.get("assessments", ())
                if isinstance(item, dict)
            )
            plan = build_requalification_plan(impact, assessments)
            artifact = plan.as_dict()
            _write(args.output, artifact)
            result = {"status": "PASS", "action": "regression.plan", "output": str(Path(args.output)), "state": plan.state, "coverage_denominator": plan.coverage_denominator}
        else:
            plan = _plan_from_dict(_read(args.plan))
            results = _read(args.results).get("results", {})
            if not isinstance(results, dict):
                raise ValidationError("REGRESSION_RESULTS_INVALID")
            replay = run_regression_plan(plan, {str(k): bool(v) for k, v in results.items()})
            result = {"status": "FAIL" if replay.failed_paths else "PASS", "action": "regression.run", "replay": replay.as_dict()}
            if args.output:
                _write(args.output, result)
        stream = sys.stdout if result["status"] == "PASS" else sys.stderr
        print(json.dumps(result, indent=2, sort_keys=True) if getattr(args, "json", False) else result, file=stream)
        return 0 if result["status"] == "PASS" else 1
    except ValidationError as exc:
        result = {"status": "FAIL", "error": exc.code, "detail": exc.detail}
        print(json.dumps(result, indent=2, sort_keys=True), file=sys.stderr)
        return 1


__all__ = ["run_audit_cli", "run_evidence_cli", "run_regression_cli"]

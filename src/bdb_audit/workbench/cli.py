"""RU12-B workbench CLI handlers."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from .projection import build_workbench_snapshot, verify_workbench_snapshot


def _read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise ValidationError("WORKBENCH_ARTIFACT_NOT_FOUND", str(source))
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("WORKBENCH_ARTIFACT_PARSE_FAILED", str(source)) from exc
    if not isinstance(data, dict):
        raise ValidationError("WORKBENCH_ARTIFACT_OBJECT_REQUIRED")
    return data


def _write_json(path: str | Path, data: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temp, target)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bdb_audit workbench", description="Exact-cut audit workbench projections")
    subs = parser.add_subparsers(dest="subcommand")
    snap = subs.add_parser("snapshot")
    snap.add_argument("--store", required=True)
    snap.add_argument("--output", required=True)
    snap.add_argument("--feature-matrix")
    snap.add_argument("--json", action="store_true")
    verify = subs.add_parser("verify")
    verify.add_argument("--store", required=True)
    verify.add_argument("--snapshot", required=True)
    verify.add_argument("--json", action="store_true")
    for name in ("summary", "blockers", "findings", "contradictions"):
        item = subs.add_parser(name)
        item.add_argument("--store", required=True)
        item.add_argument("--json", action="store_true")
    return parser


def _emit(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(f"[{data.get('status', 'INFO')}] {data.get('action', 'workbench')}")
        for key, value in data.items():
            if key not in {"status", "action"}:
                print(f"  {key}: {value}")


def run_cli(argv: Sequence[str]) -> int:
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
        store = TransactionalHistoryStore(args.store)
        if args.subcommand == "verify":
            response = verify_workbench_snapshot(_read_json(args.snapshot), store)
            response["action"] = "workbench.verify"
        else:
            feature_matrix = _read_json(args.feature_matrix) if getattr(args, "feature_matrix", None) else None
            snapshot = build_workbench_snapshot(store, feature_matrix=feature_matrix).as_dict()
            if args.subcommand == "snapshot":
                _write_json(args.output, snapshot)
                response = {"status": "PASS", "action": "workbench.snapshot", "output": str(Path(args.output)), "projection_digest": snapshot["projection_digest"], "history_cut": snapshot["history_cut"], "freshness": snapshot["freshness"]}
            elif args.subcommand == "summary":
                response = {"status": "PASS", "action": "workbench.summary", "history_cut": snapshot["history_cut"], "freshness": snapshot["freshness"], "source_identity": snapshot["source_identity"], "campaign": snapshot["campaign"], "workflow": snapshot["workflow"], "progress": snapshot["progress"], "coverage_summary": snapshot["coverage_summary"], "unknown_count": len(snapshot["scope_unknowns"])}
            elif args.subcommand == "blockers":
                response = {"status": "PASS", "action": "workbench.blockers", "history_cut": snapshot["history_cut"], "blockers": snapshot["blockers"]}
            elif args.subcommand == "findings":
                response = {"status": "PASS", "action": "workbench.findings", "history_cut": snapshot["history_cut"], "findings": snapshot["findings"]}
            elif args.subcommand == "contradictions":
                response = {"status": "PASS", "action": "workbench.contradictions", "history_cut": snapshot["history_cut"], "contradictions": snapshot["contradictions"]}
            else:
                raise ValidationError("WORKBENCH_SUBCOMMAND_INVALID", str(args.subcommand))
        _emit(response, as_json)
        return 0
    except ValidationError as exc:
        response = {"status": "FAIL", "error": exc.code, "detail": exc.detail}
        if as_json:
            print(json.dumps(response, indent=2, sort_keys=True), file=sys.stderr)
        else:
            print(f"[FAIL] {exc.code}: {exc.detail}", file=sys.stderr)
        return 1


__all__ = ["run_cli"]

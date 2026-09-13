"""RU13-B/C public CLI for independent methodology qualification."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from ..core.errors import ValidationError
from .continuous import run_continuous_qualification, verify_continuous_qualification
from .real_target_harness import run_v21_reference_corpus, verify_v21_reference_result


def _read(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise ValidationError("QUALIFICATION_RESULT_NOT_FOUND", str(source))
    try:
        body = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("QUALIFICATION_RESULT_PARSE_FAILED", str(source)) from exc
    if not isinstance(body, dict):
        raise ValidationError("QUALIFICATION_RESULT_OBJECT_REQUIRED")
    return body


def _write(path: str | Path, body: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temp, target)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bdb_audit qualification", description="Independent methodology qualification")
    subs = parser.add_subparsers(dest="subcommand")
    run = subs.add_parser("run")
    run.add_argument("--suite", choices=["validation", "holdout"], default="validation")
    run.add_argument("--workspace", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--evaluator-profile", default="BDB-INDEPENDENT-EVALUATOR-V1")
    run.add_argument("--json", action="store_true")
    verify = subs.add_parser("verify")
    verify.add_argument("--suite", choices=["validation", "holdout"], default="validation")
    verify.add_argument("--result", required=True)
    verify.add_argument("--json", action="store_true")
    return parser


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
        if args.subcommand == "run":
            result = (
                run_v21_reference_corpus(args.workspace)
                if args.suite == "validation"
                else run_continuous_qualification(args.workspace, args.evaluator_profile)
            )
            _write(args.output, result)
            response = {
                "status": result["status"],
                "action": "qualification.run",
                "suite": args.suite,
                "output": str(Path(args.output)),
                "result_digest": result["result_digest"],
            }
        elif args.subcommand == "verify":
            body = _read(args.result)
            verified = (
                verify_v21_reference_result(body)
                if args.suite == "validation"
                else verify_continuous_qualification(body)
            )
            response = dict(verified)
            response["action"] = "qualification.verify"
            response["suite"] = args.suite
        else:
            raise ValidationError("QUALIFICATION_SUBCOMMAND_INVALID", str(args.subcommand))
        stream = sys.stdout if response.get("status") in {"PASS", "QUALIFIED"} else sys.stderr
        if as_json:
            print(json.dumps(response, indent=2, sort_keys=True), file=stream)
        else:
            print(f"[{response.get('status', 'INFO')}] {response['action']}", file=stream)
        return 0 if response.get("status") in {"PASS", "QUALIFIED"} else 1
    except ValidationError as exc:
        response = {"status": "FAIL", "error": exc.code, "detail": exc.detail}
        if as_json:
            print(json.dumps(response, indent=2, sort_keys=True), file=sys.stderr)
        else:
            print(f"[FAIL] {exc.code}: {exc.detail}", file=sys.stderr)
        return 1


__all__ = ["run_cli"]

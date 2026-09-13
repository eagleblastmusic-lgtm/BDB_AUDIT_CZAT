"""RU17 normalized history and share-bundle CLI."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from ..core.errors import ValidationError
from .models import PrivacyPolicy
from .share import export_share_bundle, verify_share_bundle
from .trends import build_trends, points_from_dict


def _read(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise ValidationError("HISTORY_ARTIFACT_NOT_FOUND", str(source))
    try:
        body = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("HISTORY_ARTIFACT_PARSE_FAILED", str(source)) from exc
    if not isinstance(body, dict):
        raise ValidationError("HISTORY_ARTIFACT_OBJECT_REQUIRED")
    return body


def _write(path: str | Path, body: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(
        json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temp, target)


def run_history_cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="bdb_audit history")
    subs = parser.add_subparsers(dest="subcommand")
    trends = subs.add_parser("trends")
    trends.add_argument("--input", required=True)
    trends.add_argument("--output")
    trends.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(list(argv))
        if args.subcommand != "trends":
            parser.print_help()
            return 2
        raw = _read(args.input)
        points = raw.get("points")
        if not isinstance(points, list):
            raise ValidationError("HISTORICAL_POINTS_REQUIRED")
        result = build_trends(
            points_from_dict([item for item in points if isinstance(item, dict)])
        )
        result["action"] = "history.trends"
        if args.output:
            _write(args.output, result)
        print(json.dumps(result, indent=2, sort_keys=True) if args.json else result)
        return 0
    except ValidationError as exc:
        result = {"status": "FAIL", "error": exc.code, "detail": exc.detail}
        print(json.dumps(result, indent=2, sort_keys=True), file=sys.stderr)
        return 1


def run_share_cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="bdb_audit share")
    subs = parser.add_subparsers(dest="subcommand")

    export = subs.add_parser("export")
    export.add_argument("--source", required=True)
    export.add_argument("--input", required=True)
    export.add_argument("--output", required=True)
    export.add_argument("--json", action="store_true")

    verify = subs.add_parser("verify")
    verify.add_argument("--bundle", required=True)
    verify.add_argument("--json", action="store_true")

    try:
        args = parser.parse_args(list(argv))
        as_json = bool(getattr(args, "json", False))
        if args.subcommand == "verify":
            result = verify_share_bundle(args.bundle)
            result["action"] = "share.verify"
        elif args.subcommand == "export":
            request = _read(args.input)
            privacy_raw = request.get("privacy_policy", {})
            if not isinstance(privacy_raw, dict):
                raise ValidationError("SHARE_PRIVACY_POLICY_INVALID")
            policy = PrivacyPolicy(
                mode=str(privacy_raw.get("mode", "REDACTED")),
                excluded_path_prefixes=tuple(
                    privacy_raw.get("excluded_path_prefixes", ())
                ),
                max_file_bytes=int(
                    privacy_raw.get("max_file_bytes", 16 * 1024 * 1024)
                ),
            )
            source_identity = request.get("source_identity")
            if not isinstance(source_identity, dict):
                raise ValidationError("SHARE_SOURCE_IDENTITY_REQUIRED")
            include = request.get("include_paths")
            if not isinstance(include, list):
                raise ValidationError("SHARE_INCLUDE_PATHS_REQUIRED")
            history_cut = request.get("history_cut")
            if history_cut is not None and not isinstance(history_cut, dict):
                raise ValidationError("SHARE_HISTORY_CUT_INVALID")
            result = export_share_bundle(
                args.source,
                args.output,
                include_paths=tuple(str(item) for item in include),
                privacy_policy=policy,
                source_identity=source_identity,
                history_cut=history_cut,
                attestation_ref=request.get("attestation_ref"),
            )
            result["action"] = "share.export"
        else:
            parser.print_help()
            return 2
        print(json.dumps(result, indent=2, sort_keys=True) if as_json else result)
        return 0
    except ValidationError as exc:
        result = {"status": "FAIL", "error": exc.code, "detail": exc.detail}
        print(json.dumps(result, indent=2, sort_keys=True), file=sys.stderr)
        return 1


__all__ = ["run_history_cli", "run_share_cli"]

"""Executable release-validator interface for BDB Audit v2."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .core.errors import ValidationError
from .release_validator import ReleaseValidator

EXIT_SUCCESS = 0
EXIT_VALIDATION_FAILURE = 1
EXIT_USAGE = 2


def _error_code(exc: BaseException) -> str:
    if isinstance(exc, FileNotFoundError):
        return "ARTIFACT_NOT_FOUND"
    if isinstance(exc, ValidationError):
        return str(getattr(exc, "code", exc.args[0] if exc.args else "VALIDATION_ERROR"))
    return "VALIDATOR_INTERNAL_ERROR"


def _error_detail(exc: BaseException) -> str:
    return str(getattr(exc, "detail", str(exc)))


def _write_report(report: dict[str, Any], output_path: str | None) -> None:
    rendered = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if output_path:
        path = Path(output_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8", newline="\n")
    stream = sys.stdout if report.get("status") == "PASS" else sys.stderr
    stream.write(rendered)
    stream.flush()


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bdb-audit-release-validator",
        description="Fail-closed validation of a BDB Audit standalone artifact.",
    )
    parser.add_argument("artifact", help="Standalone artifact to validate")
    parser.add_argument("--output", help="Optional UTF-8 JSON receipt path")
    parser.add_argument(
        "--no-same-environment-rebuild",
        action="store_true",
        help="Skip only the local same-environment rebuild check; report it as NOT_RUN.",
    )
    return parser


def run_release_validator_cli(argv: Sequence[str] | None = None) -> int:
    parser = create_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else EXIT_USAGE
        return code

    try:
        validator = ReleaseValidator(args.artifact)
        report = validator.validate_all(
            check_reproducibility=not args.no_same_environment_rebuild,
        )
        report["validator_cli"] = "bdb_audit.release_validator_cli"
        _write_report(report, args.output)
        return EXIT_SUCCESS
    except Exception as exc:
        report = {
            "status": "FAIL",
            "validator_cli": "bdb_audit.release_validator_cli",
            "artifact_path": str(Path(args.artifact).resolve()),
            "error": _error_code(exc),
            "detail": _error_detail(exc),
            "checks": {
                "same_environment_rebuild_identity": "NOT_RUN"
                if args.no_same_environment_rebuild
                else "INCOMPLETE",
                "clean_room_rebuild_identity": "NOT_RUN",
            },
        }
        _write_report(report, args.output)
        return EXIT_VALIDATION_FAILURE


def main() -> None:
    raise SystemExit(run_release_validator_cli())


if __name__ == "__main__":
    main()

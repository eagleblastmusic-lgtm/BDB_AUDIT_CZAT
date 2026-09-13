"""BDB Audit vNext CLI router.

The qualified v2.0.3 command surface remains byte-for-byte available in
``legacy_cli``. New product capabilities are routed here and delegate to the
legacy router for all previously supported commands.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from . import legacy_cli as _legacy
from .core.errors import ValidationError
from .runner.environments import environment_manifest, source_manifest
from .runner.permissions import validate_run_spec
from .runner.specs import CapabilityProfile, ToolRunSpec
from .runner.supervisor import ToolSupervisor
from .runner.verification import verify_run_evidence

EXIT_SUCCESS = _legacy.EXIT_SUCCESS
EXIT_DOMAIN_ERROR = _legacy.EXIT_DOMAIN_ERROR
EXIT_MALFORMED_ARGS = _legacy.EXIT_MALFORMED_ARGS
EXIT_CAMPAIGN_NOT_FOUND = _legacy.EXIT_CAMPAIGN_NOT_FOUND
EXIT_CONFLICT_ERROR = _legacy.EXIT_CONFLICT_ERROR
APP_VERSION = _legacy.APP_VERSION
BUILD_ID = _legacy.BUILD_ID
SOURCE_CAPABILITIES = dict(_legacy.SOURCE_CAPABILITIES)
SOURCE_CAPABILITIES["controlled_tool_runner"] = "SUPPORTED_LOCAL_PROFILE"
create_parser = _legacy.create_parser


def _emit(data: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return
    status = data.get("status", "INFO")
    action = data.get("action", data.get("command", "OK"))
    print(f"[{status}] {action}")
    for key, value in data.items():
        if key not in {"status", "action", "command"}:
            print(f"  {key}: {value}")


def _parse_env(values: Sequence[str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValidationError("TOOL_RUN_ENV_ASSIGNMENT_INVALID", value)
        key, item = value.split("=", 1)
        if not key or key in env:
            raise ValidationError("TOOL_RUN_ENV_ASSIGNMENT_INVALID", value)
        env[key] = item
    return env


def _strip_separator(argv: Sequence[str]) -> tuple[str, ...]:
    values = tuple(argv)
    if values and values[0] == "--":
        values = values[1:]
    if not values:
        raise ValidationError("TOOL_RUN_ARGV_REQUIRED")
    return values


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-output-bytes", type=int, default=4 * 1024 * 1024)
    parser.add_argument("--working-subdir", default=".")
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("--require-network-isolation", action="store_true")
    parser.add_argument("--require-host-filesystem-isolation", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("argv", nargs=argparse.REMAINDER)


def _tool_spec(args: argparse.Namespace) -> ToolRunSpec:
    return ToolRunSpec(
        run_id=args.run_id,
        source_root=args.source,
        evidence_dir=args.evidence,
        argv=_strip_separator(args.argv),
        timeout_seconds=args.timeout,
        max_output_bytes=args.max_output_bytes,
        environment=_parse_env(args.env),
        require_network_isolation=args.require_network_isolation,
        require_host_filesystem_isolation=args.require_host_filesystem_isolation,
        working_subdir=args.working_subdir,
    )


def _tools_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bdb_audit tools", description="Controlled tool-runner operations")
    subs = parser.add_subparsers(dest="subcommand")

    inspect_p = subs.add_parser("inspect", help="Inspect local runner capability and source identity")
    inspect_p.add_argument("--source", required=True)
    inspect_p.add_argument("--json", action="store_true")

    plan_p = subs.add_parser("plan", help="Validate and preview an exact-argv tool run")
    _add_run_arguments(plan_p)

    run_p = subs.add_parser("run", help="Execute an authorized exact-argv run in a disposable workspace")
    _add_run_arguments(run_p)

    results_p = subs.add_parser("results", help="Verify collected tool-run evidence and receipt binding")
    results_p.add_argument("--evidence", required=True)
    results_p.add_argument("--json", action="store_true")
    return parser


def _environment_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bdb_audit environment", description="Runner environment verification")
    subs = parser.add_subparsers(dest="subcommand")
    verify_p = subs.add_parser("verify", help="Verify source and runtime identity for the local runner profile")
    verify_p.add_argument("--source", required=True)
    verify_p.add_argument("--json", action="store_true")
    return parser


def _run_tools(argv: Sequence[str]) -> int:
    parser = _tools_parser()
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_MALFORMED_ARGS
    if not args.subcommand:
        parser.print_help()
        return EXIT_MALFORMED_ARGS
    as_json = bool(getattr(args, "json", False))
    try:
        profile = CapabilityProfile()
        if args.subcommand == "inspect":
            source_info = source_manifest(args.source)
            data = {
                "status": "PASS",
                "action": "tools.inspect",
                "capability_profile": profile.as_dict(),
                "capability_profile_digest": profile.digest,
                "source_manifest_digest": source_info["manifest_digest"],
                "source_member_count": len(source_info["members"]),
                "limitations": [
                    name
                    for name, enforced in (
                        ("NETWORK_EGRESS_NOT_ENFORCED", profile.network_isolation == "ENFORCED"),
                        ("HOST_FILESYSTEM_ISOLATION_NOT_ENFORCED", profile.host_filesystem_isolation == "ENFORCED"),
                    )
                    if not enforced
                ],
            }
            _emit(data, as_json=as_json)
            return EXIT_SUCCESS
        if args.subcommand == "results":
            data = verify_run_evidence(args.evidence)
            data["action"] = "tools.results"
            _emit(data, as_json=as_json)
            return EXIT_SUCCESS

        spec = _tool_spec(args)
        if args.subcommand == "plan":
            source_path, evidence_path = validate_run_spec(spec, profile)
            data = {
                "status": "PASS",
                "action": "tools.plan",
                "spec": spec.as_dict(),
                "spec_digest": spec.digest,
                "source": str(source_path),
                "evidence": str(evidence_path),
                "capability_profile": profile.as_dict(),
                "capability_profile_digest": profile.digest,
            }
            _emit(data, as_json=as_json)
            return EXIT_SUCCESS
        if args.subcommand == "run":
            result = ToolSupervisor(profile).run(spec)
            data = result.as_dict()
            data["action"] = "tools.run"
            data["receipt_digest"] = result.receipt_digest
            _emit(data, as_json=as_json)
            return EXIT_SUCCESS if result.supervisor_status in {"SUCCESS", "TARGET_NONZERO"} else EXIT_DOMAIN_ERROR
        raise ValidationError("TOOLS_SUBCOMMAND_INVALID", str(args.subcommand))
    except ValidationError as exc:
        data = {"status": "FAIL", "error": exc.code, "detail": exc.detail}
        if as_json:
            print(json.dumps(data, indent=2, sort_keys=True), file=sys.stderr)
        else:
            print(f"[FAIL] {exc.code}: {exc.detail}", file=sys.stderr)
        return EXIT_DOMAIN_ERROR


def _run_environment(argv: Sequence[str]) -> int:
    parser = _environment_parser()
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_MALFORMED_ARGS
    if args.subcommand != "verify":
        parser.print_help()
        return EXIT_MALFORMED_ARGS
    as_json = bool(args.json)
    try:
        profile = CapabilityProfile()
        data = environment_manifest(args.source, profile)
        response = {
            "status": "PASS",
            "action": "environment.verify",
            "environment_manifest": data,
            "capability_profile": profile.as_dict(),
            "limitations": [
                "NETWORK_EGRESS_NOT_ENFORCED" if profile.network_isolation != "ENFORCED" else "",
                "HOST_FILESYSTEM_ISOLATION_NOT_ENFORCED" if profile.host_filesystem_isolation != "ENFORCED" else "",
            ],
        }
        response["limitations"] = [item for item in response["limitations"] if item]
        _emit(response, as_json=as_json)
        return EXIT_SUCCESS
    except ValidationError as exc:
        data = {"status": "FAIL", "error": exc.code, "detail": exc.detail}
        if as_json:
            print(json.dumps(data, indent=2, sort_keys=True), file=sys.stderr)
        else:
            print(f"[FAIL] {exc.code}: {exc.detail}", file=sys.stderr)
        return EXIT_DOMAIN_ERROR


def run_cli(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values and values[0] == "tools":
        return _run_tools(values[1:])
    if values and values[0] == "environment":
        return _run_environment(values[1:])
    return _legacy.run_cli(values)


def main() -> None:
    sys.exit(run_cli())


__all__ = [
    "run_cli", "main", "create_parser", "SOURCE_CAPABILITIES", "APP_VERSION", "BUILD_ID",
    "EXIT_SUCCESS", "EXIT_DOMAIN_ERROR", "EXIT_MALFORMED_ARGS",
    "EXIT_CAMPAIGN_NOT_FOUND", "EXIT_CONFLICT_ERROR",
]


if __name__ == "__main__":
    main()

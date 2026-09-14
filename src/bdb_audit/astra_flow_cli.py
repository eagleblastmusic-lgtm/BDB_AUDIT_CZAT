"""CLI operations for the real Astra external audit workflow."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .coordinator.operations import AuditOperationApi
from .core.errors import ValidationError
from .workflow.astra_orchestrator import AstraContinuationOrchestrator
from .workflow.platform import DefaultPlatformAdapter
from .workflow.settings import get_default_settings_manager


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bdb-audit flow", description="Durable real external audit workflow")
    sub = parser.add_subparsers(dest="action")
    for name in ("status", "advance", "packages"):
        p = sub.add_parser(name)
        p.add_argument("--store", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--store", required=True)
    imp.add_argument("zip_paths", nargs="+")
    return parser


def _orchestrator(store: str | Path) -> tuple[AstraContinuationOrchestrator, dict[str, Any]]:
    orch = AstraContinuationOrchestrator(
        settings_mgr=get_default_settings_manager(),
        platform_adapter=DefaultPlatformAdapter(),
        api=AuditOperationApi(),
    )
    info = orch.resume_campaign(Path(store).resolve())
    if info.get("status") != "SUCCESS":
        raise ValidationError("CAMPAIGN_RESUME_FAILED", str(info.get("error") or info.get("details") or "unknown"))
    return orch, info


def _summary_dict(summary: Any) -> dict[str, Any]:
    return {
        "status": "SUCCESS" if not summary.error else "BLOCKED",
        "campaign_id": summary.campaign_id,
        "stage_id": summary.stage_id,
        "accepted_count": summary.accepted_count,
        "total_required_lanes": summary.total_required_lanes,
        "missing_lanes": list(summary.missing_lanes),
        "stage_complete": bool(summary.stage_complete),
        "completion_digest": summary.completion_digest,
        "error": summary.error,
        "lane_statuses": {
            slot: {
                "status": state.status,
                "findings_count": state.findings_count,
                "completion_status": state.completion_status,
                "result_digest": state.result_digest,
            }
            for slot, state in summary.lane_statuses.items()
        },
        "file_results": [
            {
                "path": item.path,
                "lane_slot": item.lane_slot,
                "status": item.status,
                "code": item.code,
                "reason": item.reason,
                "raw_digest": item.raw_digest,
                "next_action": item.next_action,
            }
            for item in summary.file_results
        ],
    }


def run_flow_cli(argv: Sequence[str]) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:
        return int(exc.code or 2)
    if not args.action:
        parser.print_help()
        return 2

    try:
        orch, info = _orchestrator(args.store)
        if args.action == "status":
            data = {
                "status": "SUCCESS",
                "resume": info,
                "dashboard": orch.get_dashboard_summary(),
            }
        elif args.action == "advance":
            data = orch.advance_to_next_stage()
        elif args.action == "packages":
            batch = orch.stage_batch
            inbox = orch.stage_inbox
            if batch is None:
                transition = orch.advance_to_next_stage()
                if transition.get("status") != "STAGE_READY":
                    data = transition
                    print(json.dumps(data, indent=2, sort_keys=True))
                    return 0 if data.get("status") != "BLOCKED" else 3
                batch = orch.stage_batch
                inbox = orch.stage_inbox
            assert batch is not None
            data = {
                "status": "SUCCESS",
                "stage_id": batch.stage_id,
                "frozen_history_cut": batch.frozen_history_cut,
                "packages": {
                    slot: {
                        "path": str(job.package_zip_path),
                        "package_digest": job.package_digest,
                        "assignment_ref": job.assignment_ref,
                        "attempt_ref": job.attempt_ref,
                        "required_isolation": job.required_isolation,
                        "accepted": bool(inbox and inbox.lane_statuses[slot].status == "ACCEPTED"),
                    }
                    for slot, job in batch.jobs.items()
                },
            }
        elif args.action == "import":
            paths = [Path(value) for value in args.zip_paths]
            if info.get("current_stage") == "E1":
                summary = orch.import_results(paths)
            else:
                if orch.stage_inbox is None:
                    transition = orch.advance_to_next_stage()
                    if transition.get("status") != "STAGE_READY":
                        print(json.dumps(transition, indent=2, sort_keys=True))
                        return 3
                summary = orch.import_post_e1_results(paths)
            data = _summary_dict(summary)
        else:
            raise ValidationError("FLOW_ACTION_INVALID", str(args.action))
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0 if data.get("status") not in {"FAIL", "BLOCKED"} else 3
    except (ValidationError, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, ValidationError) else type(exc).__name__
        detail = exc.detail if isinstance(exc, ValidationError) else str(exc)
        print(json.dumps({"status": "FAIL", "error": code, "detail": detail}, indent=2, sort_keys=True))
        return 3


__all__ = ["run_flow_cli"]

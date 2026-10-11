"""PRODUCT-V1 surface over the existing workflow and report services."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .core.errors import ValidationError
from .history.store import TransactionalHistoryStore
from .product_safety import NF02_BLOCK_CODE, NF02_BLOCK_DETAIL
from .report import ReportBuilder, render_markdown
from .runner.verification import verify_run_evidence
from .workflow.orchestrator import FullAuditOrchestrator
from .workflow.read_models import current_accepted_cut
from .workflow.settings import SettingsManager


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bdb-audit product", description="PRODUCT-V1: kampania, paczki E1, wznowienie i raport częściowy. NF02 OPEN.")
    subs = parser.add_subparsers(dest="action", required=True)
    for action in ("preflight", "start"):
        sub = subs.add_parser(action, help="Sprawdź źródło" if action == "preflight" else "Przygotuj kampanię i pięć paczek E1")
        sub.add_argument("--repo", required=True)
        sub.add_argument("--ref", default="HEAD")
        sub.add_argument("--target-type", choices=("local", "github"), default="local")
        sub.add_argument("--store", required=True)
        sub.add_argument("--json", action="store_true")
    for action in ("status", "resume", "import", "report"):
        sub = subs.add_parser(action, help={"status": "Zweryfikuj utrwalony stan", "resume": "Odtwórz istniejące paczki i stan", "import": "Pokaż blokadę przyjmowania wyników NF02", "report": "Eksportuj raport częściowy"}[action])
        sub.add_argument("--store", required=True)
        sub.add_argument("--json", action="store_true")
        if action == "import":
            sub.add_argument("--zip", required=True)
        if action == "report":
            sub.add_argument("--output", required=True)
            sub.add_argument("--run-evidence", action="append", default=[])
    return parser


def _orchestrator(store: Path) -> FullAuditOrchestrator:
    settings = SettingsManager(store.parent / "product-settings.json")
    settings.settings.output_work_dir = str(store.parent)
    settings.settings.execution_mode = "ChatGPT / GitHub"
    settings.settings.auto_copy_clipboard = False
    settings.settings.auto_open_explorer = False
    return FullAuditOrchestrator(settings_mgr=settings)


def _scope() -> dict[str, Any]:
    return {"profile": "PRODUCT-V1_PREPARATION_AND_LOCAL_CHECKS", "external_ingestion": "BLOCKED", "nf02": "OPEN", "audit_completion": "NOT_COMPLETED", "qualification": "NO_NEW_Q1_Q2_CLAIM", "isolation": "DECLARED; host/network runner NOT_ENFORCED", "next_action": NF02_BLOCK_DETAIL}


def _status(store: Path, *, resume: bool) -> dict[str, Any]:
    if not store.is_file() or store.stat().st_size == 0:
        raise ValidationError("CAMPAIGN_NOT_FOUND", str(store))
    workflow = _orchestrator(store)
    result = workflow.resume_campaign(store)
    if result.get("status") in {"ERROR", "BLOCKED"}:
        raise ValidationError(result.get("error", "RESUME_BLOCKED"), result.get("details", ""))
    history = TransactionalHistoryStore(store)
    cut = current_accepted_cut(history)
    data: dict[str, Any] = {"status": "READY_FOR_REVIEW", "store_path": str(store), "campaign_id": cut["campaign_id"], "accepted_history_cut": cut, "workflow": result, **_scope()}
    if workflow.e1_batch:
        data["packages"] = [job.as_dict() for job in workflow.e1_batch.jobs.values()]
    data["action"] = "product.resume" if resume else "product.status"
    return data


def _execute(args: argparse.Namespace) -> dict[str, Any]:
    # Disabled import must not initialize a DB, read ZIPs or create a vault.
    if args.action == "import":
        raise ValidationError(NF02_BLOCK_CODE, NF02_BLOCK_DETAIL)
    store = Path(args.store).resolve()
    if args.action in {"preflight", "start"}:
        if args.action == "start" and store.exists():
            raise ValidationError("CAMPAIGN_ALREADY_EXISTS", "Użyj product resume --store zamiast nadpisywać kampanię.")
        workflow = _orchestrator(store)
        report = workflow.run_preflight(target_type=args.target_type, target_location=args.repo, target_ref=args.ref)
        data = {"status": "READY_FOR_PREPARATION" if report.passed else report.overall_status, "action": f"product.{args.action}", "preflight": [vars(check) for check in report.checks], "source": workflow.resolved_source.as_dict() if workflow.resolved_source else None, **_scope()}
        if args.action == "start" and report.passed:
            created = workflow.initialize_campaign(store)
            batch = workflow.prepare_e1_orchestration()
            data.update(created)
            data["status"] = "READY_FOR_REVIEW"
            data["packages"] = [job.as_dict() for job in batch.jobs.values()]
            data["assignment_input_history_cut"] = batch.frozen_history_cut
        return data
    data = _status(store, resume=args.action == "resume")
    if args.action != "report":
        return data
    runs = [{"path": str(Path(path).resolve()), "verification": verify_run_evidence(path), "authority": "LOCAL_RECEIPT_INTEGRITY_ONLY; NOT_ACCEPTED_AUDITOR_RESULT"} for path in args.run_evidence]
    model = ReportBuilder(TransactionalHistoryStore(store)).build_current()
    text = ("# BDB Audit PRODUCT-V1 — raport częściowy\n\nAudyt E1-E6: **NOT_COMPLETED**. NF02: **OPEN**. Import wyników: **BLOCKED**.\n\n" + NF02_BLOCK_DETAIL + "\n\nLokalne komendy dowodzą wyłącznie wykonania wskazanych kontroli. Integralność receipt nie ustanawia autoryzacji producenta ani związania z kampanią. Nie są kwalifikacją ani wynikiem zewnętrznego audytora.\n\n```json\n" + json.dumps({"campaign": data, "local_runs": runs}, ensure_ascii=False, indent=2) + "\n```\n\n" + render_markdown(model))
    output = Path(args.output).resolve()
    # Refuse overwriting a campaign, package, raw evidence or existing export.
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return {"status": "EXPORTED_PARTIAL", "action": "product.report", "output": str(output), "report_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "campaign_id": data["campaign_id"], "local_run_count": len(runs), **_scope()}


def run_product(argv: Sequence[str]) -> int:
    try:
        args = _parser().parse_args(list(argv))
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        data = _execute(args)
        code = 2 if data["status"] in {"BLOCKED", "NEEDS_INPUT"} else 0
    except (ValidationError, OSError) as exc:
        data = {"status": "BLOCKED", "error": getattr(exc, "code", "PRODUCT_IO_ERROR"), "detail": str(exc), **_scope()}
        code = 2
    output = sys.stderr if code else sys.stdout
    if not args.json:
        print(f"[{data['status']}] {data.get('action', data.get('error'))}", file=output)
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), file=output)
    return code

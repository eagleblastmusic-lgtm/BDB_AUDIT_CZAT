"""RU15 opportunities CLI."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from ..core.errors import ValidationError
from .analysis import analyze_opportunities
from .models import OpportunityProposal
from .ranking import rank_opportunities
from .skeptic import skeptic_review


def _read(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise ValidationError("OPPORTUNITY_ARTIFACT_NOT_FOUND", str(source))
    try:
        body = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("OPPORTUNITY_ARTIFACT_PARSE_FAILED", str(source)) from exc
    if not isinstance(body, dict):
        raise ValidationError("OPPORTUNITY_ARTIFACT_OBJECT_REQUIRED")
    return body


def _write(path: str | Path, body: dict[str, Any]) -> None:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temp, target)


def _proposal(body: dict[str, Any]) -> OpportunityProposal:
    return OpportunityProposal(
        proposal_id=str(body.get("proposal_id", "")), title=str(body.get("title", "")),
        opportunity_type=str(body.get("opportunity_type", "")), source_candidate_ids=tuple(body.get("source_candidate_ids", ())),
        evidence_refs=tuple(body.get("evidence_refs", ())), benefit_hypothesis=str(body.get("benefit_hypothesis", "")),
        basis=str(body.get("basis", "INFERRED")), state="PROPOSED", mandatory_obligation=bool(body.get("mandatory_obligation", False)),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bdb_audit opportunities")
    subs = parser.add_subparsers(dest="subcommand")
    analyze = subs.add_parser("analyze"); analyze.add_argument("--input", required=True); analyze.add_argument("--output", required=True); analyze.add_argument("--json", action="store_true")
    review = subs.add_parser("review"); review.add_argument("--analysis", required=True); review.add_argument("--output", required=True); review.add_argument("--json", action="store_true")
    export = subs.add_parser("export"); export.add_argument("--analysis", required=True); export.add_argument("--reviews", required=True); export.add_argument("--output", required=True); export.add_argument("--json", action="store_true")
    return parser


def run_cli(argv: Sequence[str]) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    if not args.subcommand:
        parser.print_help(); return 2
    as_json = bool(getattr(args, "json", False))
    try:
        if args.subcommand == "analyze":
            artifact = analyze_opportunities(_read(args.input)); _write(args.output, artifact)
            response = {"status": "PASS", "action": "opportunities.analyze", "output": str(Path(args.output)), "opportunity_count": len(artifact["opportunities"]), "runtime_trace_fabrication_absent": artifact["no_runtime_trace_fabrication"]}
        elif args.subcommand == "review":
            analysis = _read(args.analysis)
            proposals = tuple(_proposal(item) for item in analysis.get("opportunities", ()) if isinstance(item, dict))
            assessments = tuple(skeptic_review(item) for item in proposals)
            artifact = {"schema_version": "RU15-OPPORTUNITY-REVIEWS-1", "authority": "DERIVED_ONLY", "assessments": [item.as_dict() for item in assessments], "ranking": rank_opportunities(proposals, assessments)}
            _write(args.output, artifact)
            response = {"status": "PASS", "action": "opportunities.review", "output": str(Path(args.output)), "review_count": len(assessments)}
        elif args.subcommand == "export":
            analysis = _read(args.analysis); reviews = _read(args.reviews)
            decisions = {str(item.get("proposal_id")): str(item.get("decision")) for item in reviews.get("assessments", ()) if isinstance(item, dict)}
            accepted = [item for item in analysis.get("opportunities", ()) if isinstance(item, dict) and decisions.get(str(item.get("proposal_id"))) == "ACCEPT_FOR_REPORT"]
            if any(bool(item.get("mandatory_obligation", False)) for item in accepted):
                raise ValidationError("OPPORTUNITY_EXPORT_MANDATORY_PROMOTION_FORBIDDEN")
            artifact = {"schema_version": "RU15-OPPORTUNITY-EXPORT-1", "authority": "REPORT_PROPOSALS_ONLY", "accepted_opportunities": accepted, "unknowns_preserved": True}
            _write(args.output, artifact)
            response = {"status": "PASS", "action": "opportunities.export", "output": str(Path(args.output)), "accepted_count": len(accepted)}
        else:
            raise ValidationError("OPPORTUNITY_SUBCOMMAND_INVALID", str(args.subcommand))
        if as_json: print(json.dumps(response, indent=2, sort_keys=True))
        else: print(f"[{response['status']}] {response['action']}")
        return 0
    except ValidationError as exc:
        response = {"status": "FAIL", "error": exc.code, "detail": exc.detail}
        if as_json: print(json.dumps(response, indent=2, sort_keys=True), file=sys.stderr)
        else: print(f"[FAIL] {exc.code}: {exc.detail}", file=sys.stderr)
        return 1


__all__ = ["run_cli"]

"""Deterministic safe Markdown renderer for RU09."""
from __future__ import annotations

import json

from .models import ReportItem, ReportModel


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("<", "&lt;").replace(">", "&gt;")


def _render_items(title: str, items: tuple[ReportItem, ...]) -> list[str]:
    lines = [f"## {title}", ""]
    if not items:
        lines.extend(["NOT_ASSESSED", ""])
        return lines
    for item in items:
        ref = item.source_ref or {}
        digest = str(ref.get("revision_digest", "NO_REF"))
        lines.append(f"### {_escape(item.record_kind)} — {_escape(digest)}")
        lines.append("")
        lines.append(f"Classification: **{item.classification}**  ")
        lines.append(f"Accepted seq: `{item.accepted_seq}`")
        lines.append("")
        payload = json.dumps(item.payload, ensure_ascii=False, sort_keys=True, indent=2)
        lines.extend(["```json", payload.replace("```", "` ` `"), "```", ""])
    return lines


def render_markdown(model: ReportModel) -> str:
    source = json.dumps(model.source_identity, ensure_ascii=False, sort_keys=True)
    lines = [
        "# BDB Audit Report",
        "",
        f"Campaign: `{_escape(model.campaign_id)}`  ",
        f"Scope: **{model.report_scope}**  ",
        f"Report model SHA-256: `{model.report_model_sha256}`  ",
        f"Accepted head: `{_escape(str(model.input_history_cut.get('accepted_head_hash', '')))}`  ",
        f"Source identity: `{_escape(source)}`",
        "",
        "All entries below are explicitly classified as accepted FACT, derived INTERPRETATION, PROPOSAL, or UNKNOWN.",
        "",
    ]
    lines.extend(_render_items("Accepted facts", model.facts))
    lines.extend(_render_items("Interpretations", model.interpretations))
    lines.extend(_render_items("Proposals", model.proposals))
    lines.extend(_render_items("Unknowns / blockers", model.unknowns))
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["render_markdown"]

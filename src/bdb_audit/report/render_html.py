"""Deterministic escaped HTML renderer for RU09."""
from __future__ import annotations

import html
import json

from .models import ReportItem, ReportModel


def _section(title: str, items: tuple[ReportItem, ...]) -> str:
    chunks = [f"<section><h2>{html.escape(title)}</h2>"]
    if not items:
        chunks.append("<p>NOT_ASSESSED</p></section>")
        return "".join(chunks)
    for item in items:
        ref = item.source_ref or {}
        digest = str(ref.get("revision_digest", "NO_REF"))
        payload = json.dumps(item.payload, ensure_ascii=False, sort_keys=True, indent=2)
        chunks.append(
            "<article>"
            f"<h3>{html.escape(item.record_kind)} — {html.escape(digest)}</h3>"
            f"<p>Classification: <strong>{html.escape(item.classification)}</strong>; "
            f"accepted seq: {html.escape(str(item.accepted_seq))}</p>"
            f"<pre>{html.escape(payload)}</pre>"
            "</article>"
        )
    chunks.append("</section>")
    return "".join(chunks)


def render_html(model: ReportModel) -> str:
    source = json.dumps(model.source_identity, ensure_ascii=False, sort_keys=True)
    body = [
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>BDB Audit Report</title></head><body>",
        "<h1>BDB Audit Report</h1>",
        f"<p>Campaign: <code>{html.escape(model.campaign_id)}</code></p>",
        f"<p>Scope: <strong>{html.escape(model.report_scope)}</strong></p>",
        f"<p>Report model SHA-256: <code>{model.report_model_sha256}</code></p>",
        f"<p>Accepted head: <code>{html.escape(str(model.input_history_cut.get('accepted_head_hash', '')))}</code></p>",
        f"<p>Source identity: <code>{html.escape(source)}</code></p>",
        _section("Accepted facts", model.facts),
        _section("Interpretations", model.interpretations),
        _section("Proposals", model.proposals),
        _section("Unknowns / blockers", model.unknowns),
        "</body></html>\n",
    ]
    return "".join(body)


__all__ = ["render_html"]

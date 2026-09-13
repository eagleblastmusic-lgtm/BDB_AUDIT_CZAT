"""Derived, evidence-backed report projections for BDB Audit.

The package façade keeps core report models/builders eager and loads bundle/
renderer helpers lazily. This prevents the intentional report↔remediation
relationship from becoming a Python import cycle while preserving the public
``bdb_audit.report`` convenience API.
"""
from __future__ import annotations

from typing import Any

from .builder import REPORT_RECORD_KINDS, ReportBuilder, extract_unknown_tokens
from .models import ReportItem, ReportModel
from .validation import validate_report_model, validate_report_references

_LAZY_EXPORTS = {
    "build_bundle_views": (".bundle", "build_bundle_views"),
    "export_report_bundle": (".bundle", "export_report_bundle"),
    "validate_q09": (".bundle", "validate_q09"),
    "verify_report_bundle": (".bundle", "verify_report_bundle"),
    "render_html": (".render_html", "render_html"),
    "render_markdown": (".render_markdown", "render_markdown"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attr_name = target
    from importlib import import_module

    value = getattr(import_module(module_name, __name__), attr_name)
    globals()[name] = value
    return value


__all__ = [
    "REPORT_RECORD_KINDS",
    "ReportBuilder",
    "ReportItem",
    "ReportModel",
    "build_bundle_views",
    "export_report_bundle",
    "extract_unknown_tokens",
    "render_html",
    "render_markdown",
    "validate_q09",
    "validate_report_model",
    "validate_report_references",
    "verify_report_bundle",
]

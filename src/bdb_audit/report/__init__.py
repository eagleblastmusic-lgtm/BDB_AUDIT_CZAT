"""Derived, evidence-backed report projections for BDB Audit.

Report artifacts are views over accepted history.  They never become a second
runtime authority and cannot advance campaign state.
"""

from .builder import REPORT_RECORD_KINDS, ReportBuilder, extract_unknown_tokens
from .models import ReportItem, ReportModel
from .validation import validate_report_model, validate_report_references

__all__ = [
    "REPORT_RECORD_KINDS",
    "ReportBuilder",
    "ReportItem",
    "ReportModel",
    "extract_unknown_tokens",
    "validate_report_model",
    "validate_report_references",
]

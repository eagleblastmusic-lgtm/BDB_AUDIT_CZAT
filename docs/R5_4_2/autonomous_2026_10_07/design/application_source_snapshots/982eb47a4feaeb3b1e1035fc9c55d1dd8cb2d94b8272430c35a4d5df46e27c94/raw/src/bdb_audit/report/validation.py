"""Fail-closed validation for RU09 report projections."""
from __future__ import annotations

from typing import Any

from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from .models import REPORT_MODEL_SCHEMA, ReportItem, ReportModel


_REQUIRED_CUT_FIELDS = {
    "campaign_id",
    "accepted_head_seq",
    "accepted_head_hash",
    "governing_policy_ref",
    "governing_spec_refs",
}


def _validate_item_group(
    items: tuple[ReportItem, ...],
    expected_classification: str,
) -> None:
    previous_key: tuple[int, str, str, str] | None = None
    for item in items:
        if item.classification != expected_classification:
            raise ValidationError(
                "REPORT_CLASSIFICATION_MISMATCH",
                f"Expected {expected_classification}, got {item.classification}",
            )
        if not item.record_kind:
            raise ValidationError("REPORT_RECORD_KIND_REQUIRED")
        if item.accepted_seq is not None and item.accepted_seq < 1:
            raise ValidationError("REPORT_ACCEPTED_SEQ_INVALID")
        if previous_key is not None and item.sort_key < previous_key:
            raise ValidationError("REPORT_ORDER_NONDETERMINISTIC")
        previous_key = item.sort_key


def validate_report_model(model: ReportModel) -> None:
    """Validate deterministic structure without promoting the report to authority."""
    if model.schema_version != REPORT_MODEL_SCHEMA:
        raise ValidationError("REPORT_SCHEMA_VERSION_UNSUPPORTED", model.schema_version)
    if not model.campaign_id:
        raise ValidationError("REPORT_CAMPAIGN_ID_REQUIRED")
    if not _REQUIRED_CUT_FIELDS.issubset(model.input_history_cut):
        missing = sorted(_REQUIRED_CUT_FIELDS.difference(model.input_history_cut))
        raise ValidationError("REPORT_HISTORY_CUT_INCOMPLETE", ",".join(missing))
    if model.input_history_cut.get("campaign_id") != model.campaign_id:
        raise ValidationError("REPORT_CAMPAIGN_CUT_MISMATCH")
    if model.report_scope not in {"PARTIAL", "BOUNDED", "FULL"}:
        raise ValidationError("REPORT_SCOPE_INVALID", model.report_scope)
    if not model.source_identity.get("source_generation_id"):
        raise ValidationError("REPORT_SOURCE_IDENTITY_INCOMPLETE")

    _validate_item_group(model.facts, "FACT")
    _validate_item_group(model.interpretations, "INTERPRETATION")
    _validate_item_group(model.proposals, "PROPOSAL")
    _validate_item_group(model.unknowns, "UNKNOWN")

    seen_facts: set[tuple[str, str]] = set()
    for item in model.facts:
        ref = item.source_ref
        if not isinstance(ref, dict):
            raise ValidationError("REPORT_FACT_SOURCE_REF_REQUIRED", item.record_kind)
        kind = ref.get("kind")
        digest = ref.get("revision_digest")
        if not isinstance(kind, str) or not isinstance(digest, str):
            raise ValidationError("REPORT_FACT_SOURCE_REF_INVALID", item.record_kind)
        identity = (kind, digest)
        if identity in seen_facts:
            raise ValidationError("REPORT_DUPLICATE_ACCEPTED_FACT", f"{kind}:{digest}")
        seen_facts.add(identity)


def validate_report_references(
    store: TransactionalHistoryStore,
    model: ReportModel,
) -> None:
    """Prove every report source_ref resolves at the exact report HistoryCut.

    This deliberately validates report membership refs rather than recursively
    guessing semantics for every nested typed reference.  Q09 closure adds the
    contract-specific evidence/reference checks in a later RU09 slice.
    """
    for group in (model.facts, model.unknowns, model.interpretations):
        for item in group:
            if item.source_ref is None:
                continue
            try:
                store.resolve_accepted(item.source_ref, model.input_history_cut)
            except ValidationError as exc:
                raise ValidationError(
                    "REPORT_DANGLING_SOURCE_REF",
                    f"{item.record_kind}: {exc.code}",
                ) from exc


__all__ = ["validate_report_model", "validate_report_references"]

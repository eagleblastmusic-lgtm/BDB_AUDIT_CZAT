"""Evidence-backed report projection builder for RU09."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..history.store import TransactionalHistoryStore
from ..workflow.read_models import campaign_source_identity, current_accepted_cut
from .models import ReportItem, ReportModel
from .validation import validate_report_model, validate_report_references


REPORT_RECORD_KINDS: tuple[str, ...] = (
    "campaign_genesis",
    "successor_campaign_genesis",
    "source_generation",
    "source_identity",
    "stage_completion",
    "observation",
    "invariant_revision",
    "materiality_assessment",
    "coverage_obligation",
    "coverage_obligation_qualification",
    "obligation_applicability_decision",
    "dependency_independence_assessment",
    "evidence_applicability_assessment",
    "evidence_qualification_assessment",
    "evidence_invalidation",
    "finding_claim_revision",
    "finding_axis_assessment",
    "finding_adjudication_decision",
    "root_cause_revision",
    "contradiction_revision",
    "contradiction_resolution_decision",
    "feature_inventory",
    "feature_expectation",
    "feature_testability",
    "functional_verification_result",
    "stop_input",
    "stop_evaluation",
    "campaign_conclusion",
    "final_assurance_case",
    "release_qualification",
)

_UNKNOWN_TOKENS = frozenset(
    {
        "UNKNOWN",
        "INCONCLUSIVE",
        "BLOCKED",
        "UNSUPPORTED",
        "INSUFFICIENT_DATA",
        "NOT_EVALUATED",
        "OPEN",
    }
)


def extract_unknown_tokens(value: object) -> tuple[str, ...]:
    """Return explicit uncertainty/blocker tokens without inferring new claims."""
    found: set[str] = set()

    def visit(node: object) -> None:
        if isinstance(node, str):
            if node in _UNKNOWN_TOKENS:
                found.add(node)
            return
        if isinstance(node, dict):
            for key in sorted(node):
                visit(node[key])
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                visit(child)

    visit(value)
    return tuple(sorted(found))


class ReportBuilder:
    """Build a deterministic report projection from one verified current cut."""

    def __init__(self, store: TransactionalHistoryStore):
        self.store = store

    def build_current(self) -> ReportModel:
        cut = current_accepted_cut(self.store)
        source = campaign_source_identity(self.store, cut)
        campaign_id = str(cut["campaign_id"])

        facts: list[ReportItem] = []
        unknowns: list[ReportItem] = []
        for kind in REPORT_RECORD_KINDS:
            for row in self.store.accepted_records(kind, cut):
                body = deepcopy(row["body"])
                source_ref = deepcopy(row["ref"])
                accepted_seq = int(row["accepted_seq"])
                facts.append(
                    ReportItem(
                        classification="FACT",
                        record_kind=kind,
                        source_ref=source_ref,
                        accepted_seq=accepted_seq,
                        payload=body,
                    )
                )
                tokens = extract_unknown_tokens(body)
                if tokens:
                    unknowns.append(
                        ReportItem(
                            classification="UNKNOWN",
                            record_kind=kind,
                            source_ref=deepcopy(source_ref),
                            accepted_seq=accepted_seq,
                            payload={"reason_tokens": list(tokens)},
                        )
                    )

        facts.sort(key=lambda item: item.sort_key)
        unknowns.sort(key=lambda item: item.sort_key)

        conclusions = [item for item in facts if item.record_kind == "campaign_conclusion"]
        final_cases = [item for item in facts if item.record_kind == "final_assurance_case"]
        if conclusions and final_cases and conclusions[-1].payload.get("termination_state") == "COMPLETED":
            scope = "FULL"
        elif conclusions:
            scope = "BOUNDED"
        else:
            scope = "PARTIAL"

        model = ReportModel(
            campaign_id=campaign_id,
            input_history_cut=deepcopy(cut),
            source_identity=deepcopy(source),
            report_scope=scope,
            facts=tuple(facts),
            interpretations=(),
            proposals=(),
            unknowns=tuple(unknowns),
        )
        validate_report_model(model)
        validate_report_references(self.store, model)
        return model


__all__ = ["REPORT_RECORD_KINDS", "ReportBuilder", "extract_unknown_tokens"]

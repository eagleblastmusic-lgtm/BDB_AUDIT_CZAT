"""RU09 slice 1: exact-cut evidence-backed report projection tests."""
from __future__ import annotations

from copy import deepcopy

import pytest

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.report import (
    ReportBuilder,
    ReportItem,
    ReportModel,
    extract_unknown_tokens,
    validate_report_model,
    validate_report_references,
)
from bdb_audit.workflow.read_models import current_accepted_cut


def _campaign(tmp_path):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(store_path, seed="ru09_report", target_repo=str(tmp_path / "target"))
    return store_path, api


def test_report_is_deterministic_and_bound_to_exact_current_cut(tmp_path):
    store_path, _ = _campaign(tmp_path)
    store = TransactionalHistoryStore(store_path)

    first = ReportBuilder(store).build_current()
    second = ReportBuilder(store).build_current()

    assert first.as_dict() == second.as_dict()
    assert first.report_model_sha256 == second.report_model_sha256
    assert first.input_history_cut == current_accepted_cut(store)
    assert first.campaign_id == first.input_history_cut["campaign_id"]
    assert first.source_identity["source_generation_id"]
    assert first.report_scope == "PARTIAL"
    assert first.interpretations == ()
    assert first.proposals == ()
    assert len(first.report_model_sha256) == 64


def test_report_tracks_new_accepted_history_without_rewriting_prior_projection(tmp_path):
    store_path, api = _campaign(tmp_path)
    store = TransactionalHistoryStore(store_path)
    before = ReportBuilder(store).build_current()
    before_dict = before.as_dict()

    api.prepare_stage(store_path, "E1")
    api.qualify_stage(store_path, "E1")

    after = ReportBuilder(store).build_current()
    assert after.input_history_cut["accepted_head_seq"] > before.input_history_cut["accepted_head_seq"]
    assert after.report_model_sha256 != before.report_model_sha256
    assert before.as_dict() == before_dict
    assert any(item.record_kind == "stage_completion" for item in after.facts)


def test_unknown_extraction_is_explicit_and_deterministic():
    payload = {
        "z": ["SUPPORTED", "INCONCLUSIVE"],
        "a": {"state": "UNKNOWN", "other": "OPEN"},
        "not_a_token": "unknown",
    }
    assert extract_unknown_tokens(payload) == ("INCONCLUSIVE", "OPEN", "UNKNOWN")


def test_report_validation_rejects_duplicate_accepted_fact(tmp_path):
    store_path, _ = _campaign(tmp_path)
    model = ReportBuilder(TransactionalHistoryStore(store_path)).build_current()
    duplicate = model.facts[0]
    broken = ReportModel(
        campaign_id=model.campaign_id,
        input_history_cut=deepcopy(model.input_history_cut),
        source_identity=deepcopy(model.source_identity),
        report_scope="PARTIAL",
        facts=tuple(sorted((*model.facts, duplicate), key=lambda item: item.sort_key)),
        interpretations=(),
        proposals=(),
        unknowns=model.unknowns,
    )
    with pytest.raises(ValidationError, match="REPORT_DUPLICATE_ACCEPTED_FACT"):
        validate_report_model(broken)


def test_report_reference_validation_fails_closed_on_dangling_ref(tmp_path):
    store_path, _ = _campaign(tmp_path)
    store = TransactionalHistoryStore(store_path)
    model = ReportBuilder(store).build_current()
    original = model.facts[0]
    bad_ref = deepcopy(original.source_ref)
    assert bad_ref is not None
    bad_ref["revision_digest"] = "0" * 64
    dangling = ReportItem(
        classification="FACT",
        record_kind=original.record_kind,
        source_ref=bad_ref,
        accepted_seq=original.accepted_seq,
        payload=deepcopy(original.payload),
    )
    broken = ReportModel(
        campaign_id=model.campaign_id,
        input_history_cut=deepcopy(model.input_history_cut),
        source_identity=deepcopy(model.source_identity),
        report_scope="PARTIAL",
        facts=(dangling,),
        interpretations=(),
        proposals=(),
        unknowns=(),
    )
    validate_report_model(broken)
    with pytest.raises(ValidationError, match="REPORT_DANGLING_SOURCE_REF"):
        validate_report_references(store, broken)


def test_report_cannot_claim_full_assurance_by_default(tmp_path):
    store_path, _ = _campaign(tmp_path)
    model = ReportBuilder(TransactionalHistoryStore(store_path)).build_current()
    assert model.report_scope == "PARTIAL"

"""Residual-risk propagation through the three prior-accepted finalization boundaries."""
from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

import bdb_audit.assurance.finalization_service as finalization_module
import bdb_audit.assurance.residual_risk_finalization as risk_finalization_module
from bdb_audit.assurance.finalization_service import FinalizationService
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.objects import CanonicalObject
from tests.f7.test_finalization_temporal_boundaries import _FakeAcceptedStore, _ref


def _fake_cut(store: _FakeAcceptedStore) -> dict:
    return {
        "campaign_id": store.campaign_id,
        "accepted_head_seq": store.seq,
        "accepted_head_hash": store.hash,
    }


def _install_fake_accept(monkeypatch, store: _FakeAcceptedStore, service: FinalizationService) -> None:
    def fake_accept_one(obj: CanonicalObject, scope: str):
        store.seq += 1
        store.hash = hashlib.sha256(f"risk-finalization-{store.seq}".encode()).hexdigest()
        store.records.setdefault(obj.kind, []).append(
            {
                "accepted_seq": store.seq,
                "ref": obj.as_ref().as_dict(),
                "body": dict(obj.body),
            }
        )
        return SimpleNamespace(head=store.head())

    monkeypatch.setattr(finalization_module, "current_accepted_cut", _fake_cut)
    monkeypatch.setattr(risk_finalization_module, "current_accepted_cut", _fake_cut)
    monkeypatch.setattr(service, "_accept_one", fake_accept_one)


def _add_risk(store: _FakeAcceptedStore, token: str, *, seq: int, risk_id: str = "risk-1") -> dict:
    risk_ref = _ref("residual_risk", token)
    store.records.setdefault("residual_risk", []).append(
        {
            "accepted_seq": seq,
            "ref": risk_ref,
            "body": {
                "risk_id": risk_id,
                "risk_revision": token,
                "disposition": "ACCEPTED_RESIDUAL_RISK",
                "status": "VALID",
                "blocking_effect": False,
                "owner_approval_ref": _ref("approval_decision", f"approval-{token}"),
            },
        }
    )
    return risk_ref


def test_exact_residual_risk_set_propagates_through_finalization(monkeypatch) -> None:
    store = _FakeAcceptedStore()
    risk_ref = _add_risk(store, "risk-v1", seq=9)
    store.records["stop_input"][0]["body"]["residual_risk_refs"] = [risk_ref]
    store.records["stop_evaluation"][0]["body"]["release_readiness"] = "READY_WITH_RESIDUAL_RISK"
    service = FinalizationService(store)  # type: ignore[arg-type]
    _install_fake_accept(monkeypatch, store, service)

    result = service.conclude_campaign(
        termination_state="COMPLETED",
        bounded_statement="Residual risk is formally accepted and disclosed",
    )

    assert result["release_readiness"] == "READY_WITH_RESIDUAL_RISK"
    assert result["campaign_conclusion_commit_seq"] == 11
    assert result["final_assurance_case_commit_seq"] == 12
    assert result["release_qualification_commit_seq"] == 13

    conclusion = store.records["campaign_conclusion"][0]["body"]
    final_case = store.records["final_assurance_case"][0]["body"]
    qualification = store.records["release_qualification"][0]["body"]
    expected = risk_ref["revision_digest"]

    assert conclusion["residual_risk_refs"][0]["revision_digest"] == expected
    assert conclusion["residual_risk_refs"][0]["ref_class"] == "PRIOR_ACCEPTED_ONLY"
    assert final_case["residual_risk_refs"][0]["revision_digest"] == expected
    assert final_case["residual_risk_refs"][0]["ref_class"] == "PRIOR_ACCEPTED_ONLY"
    assert qualification["accepted_residual_risk_refs"][0]["revision_digest"] == expected
    assert qualification["accepted_residual_risk_refs"][0]["ref_class"] == "PRIOR_ACCEPTED_ONLY"
    assert qualification["result"] == "READY_WITH_RESIDUAL_RISK"


def test_residual_risk_revision_after_stop_requires_fresh_stop(monkeypatch) -> None:
    store = _FakeAcceptedStore()
    old_ref = _add_risk(store, "risk-v1", seq=8)
    _add_risk(store, "risk-v2", seq=10)
    store.records["stop_input"][0]["body"]["residual_risk_refs"] = [old_ref]
    store.records["stop_evaluation"][0]["body"]["release_readiness"] = "READY_WITH_RESIDUAL_RISK"
    service = FinalizationService(store)  # type: ignore[arg-type]
    _install_fake_accept(monkeypatch, store, service)

    with pytest.raises(ValidationError, match="RESIDUAL_RISK_DRIFT_AFTER_STOP"):
        service.conclude_campaign(
            termination_state="COMPLETED",
            bounded_statement="Must not finalize stale residual-risk authority",
        )

    assert store.seq == 10
    assert store.records["campaign_conclusion"] == []
    assert store.records["final_assurance_case"] == []
    assert store.records["release_qualification"] == []

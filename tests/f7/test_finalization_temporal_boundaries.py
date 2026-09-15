"""R5.3 finalization temporal-boundary regressions.

These tests close R5N-51: a PRIOR_ACCEPTED_ONLY decision may never be
manufactured and consumed in the same commit. The public finalization service
must materialize Conclusion -> FinalAssuranceCase -> ReleaseQualification as
three accepted-history boundaries and resume safely after partial completion.
"""
from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

import bdb_audit.assurance.finalization_service as finalization_module
from bdb_audit.assurance.finalization_service import FinalizationService
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.closure import canonical_order
from bdb_audit.history.objects import CanonicalObject


def _ref(kind: str, token: str) -> dict[str, str]:
    return {
        "kind": kind,
        "revision_digest": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }


def test_r5n51_same_commit_prior_accepted_finalization_is_rejected() -> None:
    conclusion = CanonicalObject("campaign_conclusion", {"marker": "conclusion"})
    conclusion_ref = conclusion.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict()
    final_case = CanonicalObject(
        "final_assurance_case",
        {"campaign_conclusion_ref": conclusion_ref},
    )

    with pytest.raises(ValidationError) as exc:
        canonical_order([conclusion, final_case])

    assert exc.value.code == "PRIOR_ACCEPTED_REFERENCE_REQUIRED"


class _FakeAcceptedStore:
    """Minimal accepted-history fake for service-boundary orchestration."""

    def __init__(self) -> None:
        self.campaign_id = "campaign_temporal-boundary-test"
        self.seq = 10
        self.hash = "a" * 64
        self.records: dict[str, list[dict]] = {
            "stop_evaluation": [
                {
                    "accepted_seq": 10,
                    "ref": _ref("stop_evaluation", "stop"),
                    "body": {
                        "continuation_decision": "PASS",
                        "assurance_level": "ADEQUATE_FOR_DECLARED_SCOPE",
                        "release_readiness": "READY",
                    },
                }
            ],
            "source_generation": [
                {
                    "accepted_seq": 2,
                    "ref": _ref("source_generation", "source"),
                    "body": {"marker": "source"},
                }
            ],
            "source_identity": [],
            "candidate_assurance_case": [
                {
                    "accepted_seq": 9,
                    "ref": _ref("candidate_assurance_case", "candidate"),
                    "body": {"marker": "candidate"},
                }
            ],
            "campaign_conclusion": [],
            "final_assurance_case": [],
            "release_qualification": [],
        }

    def head(self):
        return SimpleNamespace(
            campaign_id=self.campaign_id,
            commit_seq=self.seq,
            commit_hash=self.hash,
        )

    def accept(self, *args, **kwargs):
        raise AssertionError("Coordinator.accept is not expected in this service-unit fake")

    def accepted_records(self, kind: str, cut: dict) -> list[dict]:
        max_seq = int(cut["accepted_head_seq"])
        return [
            record
            for record in self.records.get(kind, [])
            if int(record["accepted_seq"]) <= max_seq
        ]


def test_finalization_service_uses_three_prior_accepted_boundaries_and_resumes(monkeypatch) -> None:
    store = _FakeAcceptedStore()
    service = FinalizationService(store)  # type: ignore[arg-type]

    def fake_cut(current_store: _FakeAcceptedStore) -> dict:
        return {
            "campaign_id": current_store.campaign_id,
            "accepted_head_seq": current_store.seq,
            "accepted_head_hash": current_store.hash,
        }

    def fake_accept_one(obj: CanonicalObject, scope: str):
        store.seq += 1
        store.hash = hashlib.sha256(f"commit-{store.seq}".encode("utf-8")).hexdigest()
        store.records.setdefault(obj.kind, []).append(
            {
                "accepted_seq": store.seq,
                "ref": obj.as_ref().as_dict(),
                "body": dict(obj.body),
            }
        )
        return SimpleNamespace(head=store.head())

    monkeypatch.setattr(finalization_module, "current_accepted_cut", fake_cut)
    monkeypatch.setattr(service, "_accept_one", fake_accept_one)

    result = service.conclude_campaign(
        termination_state="COMPLETED",
        bounded_statement="Temporal boundary regression",
    )

    assert result["campaign_conclusion_commit_seq"] == 11
    assert result["final_assurance_case_commit_seq"] == 12
    assert result["release_qualification_commit_seq"] == 13
    assert result["commit_seq"] == 13

    conclusion = store.records["campaign_conclusion"][0]["body"]
    final_case = store.records["final_assurance_case"][0]["body"]
    qualification = store.records["release_qualification"][0]["body"]

    assert conclusion["conclusion_command_input_history_cut"]["accepted_head_seq"] == 10
    assert final_case["final_case_input_history_cut"]["accepted_head_seq"] == 11
    assert qualification["qualification_command_input_history_cut"]["accepted_head_seq"] == 12
    assert qualification["release_assessment_basis_cut"]["accepted_head_seq"] == 12

    assert final_case["campaign_conclusion_ref"]["ref_class"] == "PRIOR_ACCEPTED_ONLY"
    assert qualification["campaign_conclusion_ref"]["ref_class"] == "PRIOR_ACCEPTED_ONLY"
    assert qualification["final_assurance_case_ref"]["ref_class"] == "PRIOR_ACCEPTED_ONLY"
    assert qualification["stop_evaluation_ref"]["ref_class"] == "PRIOR_ACCEPTED_ONLY"

    # A retry after all three boundaries were accepted must resume/reuse them,
    # not append a second finalization chain.
    retry = service.conclude_campaign(
        termination_state="COMPLETED",
        bounded_statement="Temporal boundary regression",
    )
    assert retry["commit_seq"] == 13
    assert store.seq == 13
    assert len(store.records["campaign_conclusion"]) == 1
    assert len(store.records["final_assurance_case"]) == 1
    assert len(store.records["release_qualification"]) == 1

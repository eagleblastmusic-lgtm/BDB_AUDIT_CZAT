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
import bdb_audit.assurance.residual_risk_finalization as risk_finalization_module
from bdb_audit.assurance.finalization_service import FinalizationService
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.closure import canonical_order
from bdb_audit.history.objects import CanonicalObject, CommitBody, ObjectRef
from bdb_audit.history.store import _commit_from_body
from bdb_audit.workflow.read_models import project_finalization_progress


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
        self.governing_policy_ref = "policy:temporal-boundary"
        command = CanonicalObject(
            "command_envelope",
            {"command_id": "fake-stop-basis-command"},
        )
        command_ref = command.as_ref(ref_class="CONTENT_OBJECT")
        parent = {
            "tag": "ACCEPTED_HEAD_REF",
            "campaign_id": self.campaign_id,
            "commit_seq": 8,
            "commit_hash": "8" * 64,
        }
        cut_commit = CommitBody(
            campaign_id=self.campaign_id,
            commit_seq=9,
            prev_history_ref=parent,
            command_ref=command_ref,
            command_digest=command.digest,
            actor_ref="test-actor",
            expected_parent_head=parent,
            governing_policy_ref=self.governing_policy_ref,
            governing_spec_refs=("spec:temporal-boundary",),
            ordered_event_bodies=(),
            immutable_object_refs=(command_ref,),
        )
        self.cut_commit = cut_commit.body()
        self.stop_cut_hash = cut_commit.digest
        stop_input_ref = _ref("stop_input", "stop-input")
        release_policy_ref = FinalizationService._policy_ref_from_cut(
            {"governing_policy_ref": self.governing_policy_ref}
        )
        self.records: dict[str, list[dict]] = {
            "stop_input": [
                {
                    "accepted_seq": 10,
                    "ref": stop_input_ref,
                    "body": {
                        "campaign_id": self.campaign_id,
                        "source_generation_ref": _ref("source_generation", "source"),
                        "input_history_cut": {
                            "variant": "ACCEPTED_HISTORY_CUT",
                            "campaign_id": self.campaign_id,
                            "accepted_head_seq": 9,
                            "accepted_head_hash": self.stop_cut_hash,
                        },
                        "candidate_assurance_case_ref": _ref("candidate_assurance_case", "candidate"),
                        "challenger_refs": [],
                        "residual_risk_refs": [],
                        "release_policy_ref": release_policy_ref,
                    },
                }
            ],
            "stop_evaluation": [
                {
                    "accepted_seq": 10,
                    "ref": _ref("stop_evaluation", "stop"),
                    "body": {
                        "stop_input_ref": stop_input_ref,
                        "continuation_decision": "PASS",
                        "assurance_level": "ADEQUATE_FOR_DECLARED_SCOPE",
                        "release_readiness": "READY",
                    },
                }
            ],
            "residual_risk": [],
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

    def resolve_accepted(self, ref: dict, cut: dict):
        for record in self.accepted_records(ref["kind"], cut):
            if record["ref"]["revision_digest"] == ref["revision_digest"]:
                return record
        raise ValidationError("OBJECT_NOT_ACCEPTED_AT_CUT")

    def commits(self):
        commits = [self.cut_commit]
        previous_hash = _commit_from_body(self.cut_commit).digest
        max_seq = max(
            [self.seq]
            + [
                int(record["accepted_seq"])
                for records in self.records.values()
                for record in records
            ]
        )
        for seq in range(10, max_seq + 1):
            command = CanonicalObject(
                "command_envelope", {"command_id": f"fake-commit-{seq}"}
            )
            command_ref = command.as_ref(ref_class="CONTENT_OBJECT")
            objects = [
                ObjectRef.from_dict(
                    {**record["ref"], "ref_class": "CONTENT_OBJECT"}
                )
                for records in self.records.values()
                for record in records
                if int(record["accepted_seq"]) == seq
            ]
            parent = {
                "tag": "ACCEPTED_HEAD_REF",
                "campaign_id": self.campaign_id,
                "commit_seq": seq - 1,
                "commit_hash": previous_hash,
            }
            commit = CommitBody(
                campaign_id=self.campaign_id,
                commit_seq=seq,
                prev_history_ref=parent,
                command_ref=command_ref,
                command_digest=command.digest,
                actor_ref="test-actor",
                expected_parent_head=parent,
                governing_policy_ref=self.governing_policy_ref,
                governing_spec_refs=("spec:temporal-boundary",),
                ordered_event_bodies=(),
                immutable_object_refs=(command_ref, *objects),
            )
            commits.append(commit.body())
            previous_hash = commit.digest
        return commits


def _install_fake_boundaries(monkeypatch, store: _FakeAcceptedStore, service: FinalizationService) -> None:
    def fake_cut(current_store: _FakeAcceptedStore) -> dict:
        return {
            "campaign_id": current_store.campaign_id,
            "accepted_head_seq": current_store.seq,
            "accepted_head_hash": current_store.hash,
            "governing_policy_ref": current_store.governing_policy_ref,
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
    monkeypatch.setattr(risk_finalization_module, "current_accepted_cut", fake_cut)
    monkeypatch.setattr(service, "_accept_one", fake_accept_one)


def test_finalization_service_uses_three_prior_accepted_boundaries_and_resumes(monkeypatch) -> None:
    store = _FakeAcceptedStore()
    service = FinalizationService(store)  # type: ignore[arg-type]
    _install_fake_boundaries(monkeypatch, store, service)

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
    assert qualification["release_policy_ref"] == store.records["stop_input"][0]["body"]["release_policy_ref"]

    retry = service.conclude_campaign(
        termination_state="COMPLETED",
        bounded_statement="Temporal boundary regression",
    )
    assert retry["commit_seq"] == 13
    assert store.seq == 13
    assert len(store.records["campaign_conclusion"]) == 1
    assert len(store.records["final_assurance_case"]) == 1
    assert len(store.records["release_qualification"]) == 1


def test_finalization_progress_requires_the_complete_exact_chain() -> None:
    store = _FakeAcceptedStore()
    conclusion_ref = _ref("campaign_conclusion", "progress-conclusion")
    stop_ref = store.records["stop_evaluation"][0]["ref"]
    store.records["campaign_conclusion"].append(
        {
            "accepted_seq": 11,
            "ref": conclusion_ref,
            "body": {
                "termination_state": "COMPLETED",
                "stop_evaluation_ref": stop_ref,
            },
        }
    )
    store.seq = 11
    cut = {
        "campaign_id": store.campaign_id,
        "accepted_head_seq": store.seq,
        "accepted_head_hash": store.hash,
    }
    assert project_finalization_progress(store, cut)["state"] == "FINAL_CASE_PENDING"

    final_ref = _ref("final_assurance_case", "progress-final")
    store.records["final_assurance_case"].append(
        {
            "accepted_seq": 12,
            "ref": final_ref,
            "body": {
                "campaign_conclusion_ref": conclusion_ref,
                "stop_evaluation_ref": stop_ref,
            },
        }
    )
    store.seq = 12
    cut["accepted_head_seq"] = store.seq
    assert project_finalization_progress(store, cut)["state"] == "RELEASE_QUALIFICATION_PENDING"

    store.records["release_qualification"].append(
        {
            "accepted_seq": 13,
            "ref": _ref("release_qualification", "progress-release"),
            "body": {
                "campaign_conclusion_ref": conclusion_ref,
                "final_assurance_case_ref": final_ref,
                "stop_evaluation_ref": stop_ref,
            },
        }
    )
    store.seq = 13
    cut["accepted_head_seq"] = store.seq
    progress = project_finalization_progress(store, cut)
    assert progress["state"] == "COMPLETE"
    assert progress["next_action"] == "CAMPAIGN_FINISHED"


def test_finalization_progress_blocks_a_conflicting_boundary() -> None:
    store = _FakeAcceptedStore()
    conclusion_ref = _ref("campaign_conclusion", "conflict-conclusion")
    store.records["campaign_conclusion"].append(
        {
            "accepted_seq": 11,
            "ref": conclusion_ref,
            "body": {
                "termination_state": "COMPLETED",
                "stop_evaluation_ref": store.records["stop_evaluation"][0]["ref"],
            },
        }
    )
    store.records["final_assurance_case"].append(
        {
            "accepted_seq": 12,
            "ref": _ref("final_assurance_case", "wrong-stop"),
            "body": {
                "campaign_conclusion_ref": conclusion_ref,
                "stop_evaluation_ref": _ref("stop_evaluation", "foreign-stop"),
            },
        }
    )
    store.seq = 12
    cut = {
        "campaign_id": store.campaign_id,
        "accepted_head_seq": store.seq,
        "accepted_head_hash": store.hash,
    }
    progress = project_finalization_progress(store, cut)
    assert progress["state"] == "BLOCKED"
    assert progress["next_action"] == "REVIEW_FINALIZATION_CHAIN"


def test_finalization_service_rejects_release_policy_drift_after_stop(monkeypatch) -> None:
    store = _FakeAcceptedStore()
    service = FinalizationService(store)  # type: ignore[arg-type]
    _install_fake_boundaries(monkeypatch, store, service)

    store.governing_policy_ref = "policy:changed-after-stop"

    with pytest.raises(ValidationError) as exc:
        service.conclude_campaign(
            termination_state="COMPLETED",
            bounded_statement="Policy drift must fail closed",
        )

    assert exc.value.code == "DRIFT_DETECTED_MATERIALIZATION_INVALID"
    assert len(store.records["campaign_conclusion"]) == 1
    assert len(store.records["final_assurance_case"]) == 1
    assert len(store.records["release_qualification"]) == 0


def test_finalization_rejects_candidate_added_after_stop(monkeypatch) -> None:
    store = _FakeAcceptedStore()
    store.seq = 11
    store.hash = "b" * 64
    store.records["candidate_assurance_case"].append(
        {
            "accepted_seq": 11,
            "ref": _ref("candidate_assurance_case", "new-candidate"),
            "body": {"marker": "candidate added after STOP"},
        }
    )
    service = FinalizationService(store)  # type: ignore[arg-type]
    _install_fake_boundaries(monkeypatch, store, service)

    with pytest.raises(ValidationError, match="STOP_INPUT_CUT_MISMATCH"):
        service.conclude_campaign(
            termination_state="COMPLETED",
            bounded_statement="Must require fresh challenger roles and STOP",
        )

    assert store.records["campaign_conclusion"] == []
    assert store.records["final_assurance_case"] == []
    assert store.records["release_qualification"] == []

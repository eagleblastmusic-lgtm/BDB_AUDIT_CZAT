"""R5.3 R5N-50 challenger temporal-boundary regressions."""
from __future__ import annotations

from pathlib import Path

import pytest

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.closure import canonical_order
from bdb_audit.history.objects import CanonicalObject
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.read_models import current_accepted_cut


def test_r5n50_candidate_and_assignment_same_commit_are_rejected() -> None:
    candidate = CanonicalObject("candidate_assurance_case", {"marker": "candidate"})
    assignment = CanonicalObject(
        "challenger_assignment",
        {
            "candidate_assurance_case_ref": candidate.as_ref(
                ref_class="PRIOR_ACCEPTED_ONLY"
            ).as_dict()
        },
    )

    with pytest.raises(ValidationError) as exc:
        canonical_order([candidate, assignment])

    assert exc.value.code == "PRIOR_ACCEPTED_REFERENCE_REQUIRED"


def test_r5n50_assignment_and_result_same_commit_are_rejected() -> None:
    assignment = CanonicalObject("challenger_assignment", {"marker": "assignment"})
    result = CanonicalObject(
        "challenger_result",
        {
            "challenge_assignment_ref": assignment.as_ref(
                ref_class="PRIOR_ACCEPTED_ONLY"
            ).as_dict()
        },
    )

    with pytest.raises(ValidationError) as exc:
        canonical_order([assignment, result])

    assert exc.value.code == "PRIOR_ACCEPTED_REFERENCE_REQUIRED"


def test_e5_service_materializes_candidate_assignments_results_and_completion_in_order(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("# R5N-50 target\n", encoding="utf-8")
    (target / "app.py").write_text("def run(): return 50\n", encoding="utf-8")
    store_path = tmp_path / "campaign.sqlite"

    api = AuditOperationApi()
    api.create_campaign(store_path, seed="r5n50", target_repo=str(target))

    for stage in ("E1", "E2", "E3", "E4"):
        api.prepare_stage(store_path, stage)
        result = api.qualify_stage(store_path, stage)
        assert result["status"] == "SUCCESS"

    api.prepare_stage(store_path, "E5")
    result = api.qualify_stage(store_path, "E5")
    assert result["status"] == "SUCCESS"

    store = TransactionalHistoryStore(store_path)
    cut = current_accepted_cut(store)

    candidate = store.accepted_records("candidate_assurance_case", cut)[-1]
    assignments = store.accepted_records("challenger_assignment", cut)[-2:]
    results = store.accepted_records("challenger_result", cut)[-2:]
    completion = store.accepted_records("stage_completion", cut)[-1]

    candidate_seq = int(candidate["accepted_seq"])
    assignment_seqs = {int(record["accepted_seq"]) for record in assignments}
    result_seqs = {int(record["accepted_seq"]) for record in results}
    completion_seq = int(completion["accepted_seq"])

    assert len(assignment_seqs) == 1
    assert len(result_seqs) == 1
    assignment_seq = next(iter(assignment_seqs))
    result_seq = next(iter(result_seqs))

    assert candidate_seq < assignment_seq < result_seq < completion_seq

    for assignment in assignments:
        body = assignment["body"]
        assert body["assignment_input_history_cut"]["accepted_head_seq"] == candidate_seq
        assert body["candidate_assurance_case_ref"]["revision_digest"] == candidate["ref"]["revision_digest"]
        assert body["candidate_assurance_case_ref"]["ref_class"] == "PRIOR_ACCEPTED_ONLY"

    assignment_digests = {record["ref"]["revision_digest"] for record in assignments}
    for challenger_result in results:
        body = challenger_result["body"]
        assert body["result_input_history_cut"]["accepted_head_seq"] == assignment_seq
        assert body["challenge_assignment_ref"]["revision_digest"] in assignment_digests
        assert body["challenge_assignment_ref"]["ref_class"] == "PRIOR_ACCEPTED_ONLY"
        assert body["candidate_assurance_case_ref"]["revision_digest"] == candidate["ref"]["revision_digest"]
        assert body["candidate_assurance_case_ref"]["ref_class"] == "PRIOR_ACCEPTED_ONLY"

    assert completion["body"]["input_history_cut"]["accepted_head_seq"] == result_seq

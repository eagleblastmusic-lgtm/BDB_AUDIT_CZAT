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


def test_e5_legacy_qualify_stage_fails_closed_without_external_challengers(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text(
        "# R5N-50 target\n", encoding="utf-8"
    )
    store_path = tmp_path / "campaign.sqlite"

    api = AuditOperationApi()
    api.create_campaign(
        store_path,
        seed="r5n50",
        target_repo=str(target),
    )
    for stage in ("E1", "E2", "E3", "E4"):
        api.prepare_stage(store_path, stage)
        result = api.qualify_stage(store_path, stage)
        assert result["status"] == "SUCCESS"

    api.prepare_stage(store_path, "E5")
    with pytest.raises(
        ValidationError,
        match="E5_EXTERNAL_CHALLENGER_RUNTIME_REQUIRED",
    ):
        api.qualify_stage(store_path, "E5")


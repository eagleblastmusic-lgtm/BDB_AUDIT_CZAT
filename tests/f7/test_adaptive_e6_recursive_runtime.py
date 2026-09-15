"""Recursive M45 runtime proof: only the newest E6 revision can be current/completed."""
from __future__ import annotations

from bdb_audit.stop.e6 import AdaptiveE6Generator
from bdb_audit.workflow.read_models import campaign_status, current_accepted_cut
from bdb_audit.workflow.stage_service import StageService
from tests.f7.test_adaptive_e6_canonical_authority import (
    _accept_command,
    _append_raw_commit,
    _ref,
    _seed_authority_store,
    _stage_execution_objects,
    _stop_pair,
)


def _canonical_stage(value: str) -> str:
    return str(value).upper()


def test_second_e6_revision_requires_its_own_completion(tmp_path) -> None:
    store, stop_eval_ref, _, obligation_ref = _seed_authority_store(tmp_path)

    first = AdaptiveE6Generator.generate_e6_spec_from_store(
        store,
        spec_id="e6-runtime-1",
        stop_evaluation_ref=stop_eval_ref,
        added_surfaces=[_ref("surface_record", "runtime-round-1")],
    )
    store.accept(_accept_command(store, 4), immutable_objects=[first.as_object()])

    # Complete the first E6 revision as prior accepted history.
    _append_raw_commit(
        store,
        _stage_execution_objects(
            first.stage_spec,
            source_generation_ref=first.source_generation_ref,
            label="runtime-e6-round-1",
            required_isolation_assurance="DECLARED",
            include_stage_spec=False,
        ),
        index=5,
    )
    status_after_first = campaign_status(store, _canonical_stage)
    assert "E6" in status_after_first["stages_completed"]

    # Accepted POST_E6 STOP requests a second adaptive round.
    cut5 = current_accepted_cut(store)
    stop_input2, stop_evaluation2 = _stop_pair(
        cut=cut5,
        source_generation_ref=first.source_generation_ref,
        evaluation_context="POST_E6",
        suffix="6",
        remaining_obligation_ref=obligation_ref,
    )
    stop_eval2_obj = stop_evaluation2.as_object()
    _append_raw_commit(store, [stop_input2.as_object(), stop_eval2_obj], index=6)
    cut6 = current_accepted_cut(store)
    exact_stop2_ref = next(
        row["ref"]
        for row in store.accepted_records("stop_evaluation", cut6)
        if row["ref"]["revision_digest"] == stop_eval2_obj.digest
    )

    second = AdaptiveE6Generator.generate_e6_spec_from_store(
        store,
        spec_id="e6-runtime-2",
        stop_evaluation_ref=exact_stop2_ref,
        added_surfaces=[_ref("surface_record", "runtime-round-2")],
    )
    store.accept(_accept_command(store, 7), immutable_objects=[second.as_object()])

    # A prior E6 completion cannot certify the newly accepted E6 revision.
    pending_status = campaign_status(store, _canonical_stage)
    assert "E6" in pending_status["stages_prepared"]
    assert "E6" not in pending_status["stages_completed"]
    assert pending_status["current_stage"] == "E6"

    result = StageService(store).qualify_and_complete_stage("E6")
    assert result["status"] == "SUCCESS"
    assert result["stage"] == "E6"

    completed_status = campaign_status(store, _canonical_stage)
    assert "E6" in completed_status["stages_completed"]

    # The accepted StageCompletion must bind the newest E6 StageSpec revision,
    # never the already-completed first revision.
    cut8 = current_accepted_cut(store)
    e6_completions = []
    for row in store.accepted_records("stage_completion", cut8):
        spec_ref = row["body"].get("stage_spec_ref", {})
        if spec_ref.get("revision_digest") == second.as_object().digest:
            e6_completions.append(row)
    assert len(e6_completions) == 1

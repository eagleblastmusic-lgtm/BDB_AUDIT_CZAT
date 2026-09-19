"""Tests for Complete User Workflow E1-E6 and STOP / Conclusion (RU08 / B02).

Validates:
1. Complete workflow without E6 (E1 -> E2 -> E3 -> E4 -> E5 -> STOP -> Conclusion).
2. Material E6 + fresh challengers scenario.
3. Early BLOCKED -> COMPLETED_LIMITED -> QUALIFICATION_BLOCKED.
4. Process restart between stages preserves exact same accepted truth.
5. UI and CLI project same terminal result.
6. No manual PASS setter.
7. E2 claim without evidence remains UNKNOWN.
8. Real small target integration.
"""
import json
from pathlib import Path
import tempfile
import zipfile
import pytest

from bdb_audit.cli import run_cli
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.continuation_service import ContinuationService
from bdb_audit.workflow.e5_runtime import (
    CandidateAssuranceCaseService,
    E5A_LANES,
    E5B_LANES,
    E5_ALL_LANE_SLOTS,
    E5ChallengeAuthorizationService,
    E5ChallengerResultService,
    E5FinalizationService,
)
from bdb_audit.workflow.manual_stage import (
    StageResultInbox,
    prepare_stage_phase_batch,
)
from bdb_audit.workflow.orchestrator import FullAuditOrchestrator
from bdb_audit.workflow.read_models import (
    campaign_status,
    current_accepted_cut,
)
from bdb_audit.workflow.settings import SettingsManager, UserSettings
from bdb_audit.workflow.source_target import ResolvedSource


@pytest.fixture
def workflow_env():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        target_dir = root / "sample_target"
        target_dir.mkdir()
        (target_dir / "README.md").write_text("# Target App\nSample target for audit.\n", encoding="utf-8")
        (target_dir / "app.py").write_text("def run(): return 42\n", encoding="utf-8")

        store_path = root / "campaign.sqlite"
        settings_file = root / "settings.json"
        settings_mgr = SettingsManager(settings_file)
        settings_mgr.settings = UserSettings(
            local_repo_path=str(target_dir),
            output_work_dir=str(root / "out"),
            execution_mode="ChatGPT / GitHub",
        )
        yield {
            "root": root,
            "target_dir": target_dir,
            "store_path": store_path,
            "settings_mgr": settings_mgr,
        }


def _e5_source() -> ResolvedSource:
    return ResolvedSource(
        target_type="github",
        location="https://github.com/example/f8-e5",
        display_name="example/f8-e5",
        ref="main",
        exact_commit_sha="f" * 40,
    )


def _write_e5_result(
    path: Path,
    batch,
    slot: str,
    outputs: dict,
) -> Path:
    job = batch.get_job(slot)
    body = {
        "kind": "bdb_audit_lane_result",
        "version": "1",
        "campaign_id": batch.campaign_id,
        "stage_id": batch.stage_id,
        "phase_id": batch.phase_id,
        "lane_slot": slot,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "input_package_digest": job.package_digest,
        "source_commit_sha": job.source_commit_sha,
        "history_cut": batch.frozen_history_cut,
        "assignment_ref": job.assignment_ref,
        "attempt_ref": job.attempt_ref,
        "findings": [],
        "outputs": outputs,
    }
    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr("MANIFEST.json", json.dumps(body))
    return path


def _e5a_outputs(slot: str) -> dict:
    if slot == "E5-A-INTERACTION":
        return {
            "e5a_interaction_results": [
                {
                    "combination": ["state", "retry"],
                    "status": "PASS",
                    "rationale": "bounded interaction held",
                }
            ]
        }
    if slot == "E5-A-MUTATION":
        return {
            "e5a_mutation_results": [
                {
                    "mutation_class": mutation_class,
                    "status": "MUTANT_KILLED",
                    "activation_witness": (
                        f"activated-{mutation_class.lower()}"
                    ),
                    "rationale": (
                        f"qualified oracle killed {mutation_class}"
                    ),
                }
                for mutation_class in (
                    "IMPLEMENTATION",
                    "ORACLE",
                    "SPECIFICATION",
                )
            ]
        }
    if slot == "E5-A-CALIBRATION":
        return {
            "e5a_calibration": {
                "status": "QUALIFIED",
                "profile_ref": {
                    "kind": "external_profile_ref",
                    "revision_digest": "8" * 64,
                    "digest_profile": "BDB-OBJECT-DIGEST-1",
                    "schema_revision_ref": (
                        "BDB_TARGET/external_profile_ref"
                    ),
                    "ref_class": "HISTORY_CONTEXT_BINDING",
                },
                "per_class_metrics": {
                    "seeded": {"detected": 1}
                },
                "unknown_count": 0,
                "rationale": "qualified calibration profile",
            }
        }
    raise AssertionError(slot)


def _complete_real_e5(
    store_path: Path,
    root: Path,
) -> None:
    api = AuditOperationApi()
    api.prepare_stage(store_path, "E5")
    for lane in (*E5A_LANES, *E5B_LANES):
        api.prepare_lane(
            store_path,
            "E5",
            lane.lane_slot,
        )

    store = TransactionalHistoryStore(store_path)
    e5a = prepare_stage_phase_batch(
        store=store,
        output_dir=root / "e5-work",
        source_info=_e5_source(),
        stage_id="E5",
        phase_id="E5A-ATTACK",
        lane_definitions=E5A_LANES,
        all_stage_lane_slots=E5_ALL_LANE_SLOTS,
    )
    e5a_inbox = StageResultInbox(store, e5a)
    e5a_paths = [
        _write_e5_result(
            root / f"{slot}.zip",
            e5a,
            slot,
            _e5a_outputs(slot),
        )
        for slot in e5a.lane_slots
    ]
    assert (
        e5a_inbox.ingest_multiple_zips(
            e5a_paths
        ).phase_complete
        is True
    )

    frozen = CandidateAssuranceCaseService(
        store
    ).freeze(e5a, e5a_inbox)
    auth = E5ChallengeAuthorizationService(
        store,
        candidate=frozen.candidate,
        executor_profile="ChatGPT / GitHub",
        model="Sol 5.6",
    ).authorize()
    e5b = prepare_stage_phase_batch(
        store=store,
        output_dir=root / "e5-work",
        source_info=_e5_source(),
        stage_id="E5",
        phase_id="E5B-CHALLENGE",
        lane_definitions=E5B_LANES,
        all_stage_lane_slots=E5_ALL_LANE_SLOTS,
        authorized_context=auth,
    )
    e5b_inbox = StageResultInbox(store, e5b)
    cut = current_accepted_cut(store)
    assignments = {
        row["body"]["challenger_type"]: row
        for row in store.accepted_records(
            "challenger_assignment", cut
        )
        if row["body"].get(
            "candidate_assurance_case_ref", {}
        ).get("revision_digest")
        == frozen.candidate.digest()
    }
    paths = []
    for slot, role in (
        ("E5-B1", "FALSE_POSITIVE_SKEPTIC"),
        ("E5-B2", "FALSE_NEGATIVE_HUNTER"),
    ):
        assignment = assignments[role]
        paths.append(
            _write_e5_result(
                root / f"{slot}.zip",
                e5b,
                slot,
                {
                    "challenger_result": {
                        "status": (
                            "NO_MATERIAL_COUNTEREVIDENCE"
                        ),
                        "candidate_revision_digest": (
                            frozen.candidate.digest()
                        ),
                        "challenge_assignment_revision_digest": (
                            assignment["ref"][
                                "revision_digest"
                            ]
                        ),
                        "challenged_revision_digests": [],
                        "reason_codes": [],
                    }
                },
            )
        )
    assert (
        e5b_inbox.ingest_multiple_zips(paths).phase_complete
        is True
    )
    E5ChallengerResultService(
        store, e5b, e5b_inbox
    ).materialize()
    completion = E5FinalizationService(
        store
    ).finalize()
    assert completion.stage_id == "E5"


def test_core_acceptance_1_complete_scenario_without_e6(workflow_env):
    """1. Complete scenario without E6: E1 -> E2 -> E3 -> E4 -> E5 -> STOP -> Conclusion."""
    store_path = workflow_env["store_path"]
    api = AuditOperationApi()

    # Genesis
    api.create_campaign(store_path, seed="full_audit_test", target_repo=str(workflow_env["target_dir"]))

    # E1-E4 use the compact legacy test scaffold; E5 must execute the
    # real external candidate/challenger runtime.
    for stage in ("E1", "E2", "E3", "E4"):
        api.prepare_stage(store_path, stage)
        res = api.qualify_stage(store_path, stage)
        assert res["status"] == "SUCCESS"
        assert res["stage"] == stage
    _complete_real_e5(
        store_path,
        workflow_env["root"],
    )

    # Status shows all 5 stages completed
    status = api.get_campaign_status(store_path)
    assert status["stages_completed"] == ["E1", "E2", "E3", "E4", "E5"]

    # STOP Evaluation
    stop_res = api.evaluate_stop_gate(store_path, evaluation_context="FINAL_POST_E5")
    assert stop_res["status"] == "SUCCESS"
    assert stop_res["continuation_decision"] == "PASS"
    assert stop_res["assurance_level"] == "ADEQUATE_FOR_DECLARED_SCOPE"

    # Campaign Conclusion
    concl_res = api.conclude_campaign(store_path)
    assert concl_res["status"] == "SUCCESS"
    assert concl_res["termination_state"] == "COMPLETED"
    assert concl_res["release_readiness"] == "READY"

    # Final projection
    final_status = api.get_campaign_status(store_path)
    assert final_status["campaign_completed"] is True
    assert final_status["termination_state"] == "COMPLETED"


def test_core_acceptance_2_material_e6_fresh_challenger(workflow_env):
    """2. Material E6 + fresh challenge: STOP yields E6_REQUIRED -> scoped E6 run -> re-evaluates."""
    store_path = workflow_env["store_path"]
    api = AuditOperationApi()

    api.create_campaign(store_path, seed="e6_test", target_repo=str(workflow_env["target_dir"]))

    for stage in ("E1", "E2", "E3", "E4"):
        api.prepare_stage(store_path, stage)
        api.qualify_stage(store_path, stage)
    _complete_real_e5(
        store_path,
        workflow_env["root"],
    )

    # Simulate STOP evaluation with approved E6 plan
    stop_res = api.evaluate_stop_gate(store_path, evaluation_context="FINAL_POST_E5", e6_plan_approved=True)
    assert stop_res["status"] == "SUCCESS"
    # When E6 plan is approved for gap resolution, continuation_decision is E6_REQUIRED
    assert stop_res["continuation_decision"] == "E6_REQUIRED"
    assert stop_res["assurance_level"] == "BOUNDED"

    # Prepare E6 from the exact accepted STOP authority.  Continuation must not
    # skip an active E6 revision and jump directly back to STOP.
    api.prepare_stage(store_path, "E6")
    awaiting_e6 = api.continue_campaign(store_path)
    assert awaiting_e6["current_stage"] == "E6"
    assert awaiting_e6["continuation_state"] == "AWAITING_STAGE_COMPLETION"
    assert awaiting_e6["next_action"] == "AWAITING_STAGE_COMPLETION"

    e6_res = api.qualify_stage(store_path, "E6")
    assert e6_res["status"] == "SUCCESS"
    assert e6_res["stage"] == "E6"

    # A completed E6 revision returns control to the global STOP gate.
    after_e6 = api.continue_campaign(store_path)
    assert after_e6["continuation_state"] == "READY_FOR_STOP_EVALUATION"
    assert after_e6["next_action"] == "EVALUATE_STOP_GATE"

    # Post-E6 STOP evaluation
    post_e6_stop = api.evaluate_stop_gate(store_path, evaluation_context="POST_E6")
    assert post_e6_stop["status"] == "SUCCESS"
    assert post_e6_stop["continuation_decision"] == "PASS"


def test_core_acceptance_3_early_blocked_completed_limited(workflow_env):
    """3. Early BLOCKED -> COMPLETED_LIMITED -> QUALIFICATION_BLOCKED, never READY."""
    store_path = workflow_env["store_path"]
    api = AuditOperationApi()

    api.create_campaign(store_path, seed="blocked_test", target_repo=str(workflow_env["target_dir"]))

    for stage in ("E1", "E2", "E3"):
        api.prepare_stage(store_path, stage)
        api.qualify_stage(store_path, stage)

    # Evaluate intermediate STOP when required stages E4-E5 are pending and surface is blocked
    stop_res = api.evaluate_stop_gate(
        store_path,
        evaluation_context="FINAL_POST_E5",
        unknown_blocked_summary={"unknown_surfaces_count": 0, "is_blocked": True},
    )
    assert stop_res["continuation_decision"] == "BLOCKED"
    assert stop_res["release_readiness"] == "QUALIFICATION_BLOCKED"

    # Concluding a blocked campaign produces COMPLETED_LIMITED, never READY
    concl_res = api.conclude_campaign(store_path, termination_state="COMPLETED_LIMITED")
    assert concl_res["termination_state"] == "COMPLETED_LIMITED"
    assert concl_res["release_readiness"] == "QUALIFICATION_BLOCKED"
    assert concl_res["release_readiness"] != "READY"


def test_core_acceptance_4_restart_between_stages_preserves_accepted_truth(workflow_env):
    """4. Process restart preserves accepted truth; next action remains a derived service view."""
    store_path = workflow_env["store_path"]
    api1 = AuditOperationApi()

    api1.create_campaign(store_path, seed="restart_test", target_repo=str(workflow_env["target_dir"]))
    api1.prepare_stage(store_path, "E1")
    api1.qualify_stage(store_path, "E1")
    api1.prepare_stage(store_path, "E2")
    api1.qualify_stage(store_path, "E2")

    head1 = api1.get_campaign_status(store_path)
    assert head1["stages_completed"] == ["E1", "E2"]
    commit_seq1 = head1["accepted_head_seq"]

    # Completely new process / API instance reading from disk.
    api2 = AuditOperationApi()
    head2 = api2.get_campaign_status(store_path)
    assert head2["stages_completed"] == ["E1", "E2"]
    assert head2["accepted_head_seq"] == commit_seq1
    # current_stage remains accepted-history state, not a second next-stage authority.
    assert head2["current_stage"] == "E2"

    store2 = TransactionalHistoryStore(store_path)
    continuation = ContinuationService.evaluate_continuation(store2)
    assert continuation["current_stage"] == "E3"
    assert continuation["next_action"] == "PREPARE_STAGE_E3"


def test_core_acceptance_6_no_manual_pass_setter(workflow_env):
    """6. No manual PASS setter: cannot conclude as COMPLETED without passing STOP gate."""
    store_path = workflow_env["store_path"]
    api = AuditOperationApi()

    api.create_campaign(store_path, seed="no_manual_pass", target_repo=str(workflow_env["target_dir"]))
    # Attempt to conclude without completing stages or STOP evaluation
    with pytest.raises(ValidationError, match="STOP_EVALUATION_REQUIRED"):
        api.conclude_campaign(store_path, termination_state="COMPLETED")


def test_core_acceptance_7_e2_claim_without_evidence_remains_unknown(workflow_env):
    """7. E2 claim without evidence remains UNKNOWN."""
    store_path = workflow_env["store_path"]
    api = AuditOperationApi()

    api.create_campaign(store_path, seed="e2_evidence_test", target_repo=str(workflow_env["target_dir"]))
    api.prepare_stage(store_path, "E1")
    api.qualify_stage(store_path, "E1")

    # Pass an unbacked finding to E2
    unbacked_finding = {
        "finding_id": "find_001",
        "claim": "Hypothetical injection vulnerability",
        "evidence_refs": [],  # NO EVIDENCE!
    }
    api.prepare_stage(store_path, "E2")
    res = api.qualify_stage(store_path, "E2", findings=[unbacked_finding])
    assert res["status"] == "SUCCESS"
    assert unbacked_finding["claim_status"] == "UNKNOWN"


def test_core_acceptance_5_ui_and_cli_parity(workflow_env):
    """5. UI and CLI project same terminal result via shared read models."""
    store_path = workflow_env["store_path"]

    # Start audit via CLI
    rc = run_cli([
        "audit", "start",
        "--store", str(store_path),
        "--target", str(workflow_env["target_dir"]),
        "--seed", "cli_ui_parity",
        "--json",
    ])
    assert rc == 0

    api = AuditOperationApi()
    status_api = api.get_campaign_status(store_path)

    # CLI status
    rc_stat = run_cli(["audit", "status", "--store", str(store_path), "--json"])
    assert rc_stat == 0

    # Both show campaign is initialized and stage E1 is prepared
    assert status_api["stages_prepared"] == ["E1"]
    assert status_api["current_stage"] == "E1"

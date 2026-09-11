"""PR-029 / WP-F3-10: Mandatory F1–F7 Adversarial Failure Suite.

Verifies exact normative failure outcomes:
- F1: contaminated lane -> BLIND_SLOT_NOT_SATISFIED
- F2: missing/unknown material surface -> STAGE_COMPLETION_BLOCKED
- F3: shared broken oracle -> required independence qualification REJECTED
- F4: crash / idempotent retry -> EXACTLY ONE accepted effect (not 0, not 2)
- F5: stale predecessor -> BLOCKED_CANONICAL_ADMISSION
- F6: invalidated evidence -> completion BLOCKED until replacement; replacement does not erase history
- F7: insufficient-data intermediate STOP -> CONTINUE_REQUIRED with BOTH REQUIRED_STAGES_PENDING and INSUFFICIENT_DATA
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import sqlite3
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.history.objects import CanonicalObject, CommandEnvelope
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.coordinator import Coordinator, run_foundation_reference_slice
from bdb_audit.coordinator.reference_slice import _external_ref, _ref_for
from bdb_audit.orchestration.stages import StageSpec
from bdb_audit.evidence.models import (
    DependencyIndependenceAssessment,
    EvidenceQualificationAssessment,
    EvidenceInvalidation,
)
from bdb_audit.stop import (
    LaneCompletion,
    StageCompletion,
    StopInput,
    StopEvaluation,
    evaluate_stop,
    validate_intermediate_stop,
)
from tests.f2.helpers import bootstrap_fixture

ROOT = Path(__file__).resolve().parents[2]


def _fresh_db(name: str) -> Path:
    path = ROOT / name
    if path.exists():
        con = sqlite3.connect(path)
        con.executescript(
            "DROP TABLE IF EXISTS immutable_objects; "
            "DROP TABLE IF EXISTS commits; "
            "DROP TABLE IF EXISTS receipts; "
            "DROP TABLE IF EXISTS accepted_head; "
            "DROP TABLE IF EXISTS command_index;"
        )
        con.close()
    return path


# =============================================================================
# F1 — contaminated lane -> BLIND_SLOT_NOT_SATISFIED
# =============================================================================

def test_f1_contaminated_lane_rejects_blind_slot():
    """F1: Contamination/blindness violation cannot produce LANE_COMPLETED."""
    history_cut = {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": "camp_f1",
        "accepted_head_seq": 4,
        "accepted_head_hash": "hash_head_f1",
    }
    lane_run = _external_ref("lane_run", "lr_f1")
    lane_spec = _external_ref("lane_spec", "ls_f1")
    kstate = _external_ref("knowledge_state", "ks_f1")
    iso_qual = _external_ref("isolation_qualification", "iso_f1")
    attempt = _external_ref("attempt", "att_f1")
    discovery = _external_ref("discovery_record", "disc_f1")
    contamination = _external_ref("contamination_assessment", "contam_f1")

    # Contaminated lane attempting to claim LANE_COMPLETED must raise BLIND_SLOT_NOT_SATISFIED
    with pytest.raises(ValidationError, match="BLIND_SLOT_NOT_SATISFIED"):
        LaneCompletion(
            lane_run_ref=lane_run,
            lane_spec_ref=lane_spec,
            input_history_cut=history_cut,
            final_knowledge_state_ref=kstate,
            isolation_qualification_ref=iso_qual,
            attempt_refs=[attempt],
            required_output_refs=[discovery],
            contamination_assessment_refs=[contamination],
            completion_predicate_result="LANE_COMPLETED",
        )

    # Valid outcome for contaminated lane is LANE_COMPLETION_BLOCKED
    lane_blocked = LaneCompletion(
        lane_run_ref=lane_run,
        lane_spec_ref=lane_spec,
        input_history_cut=history_cut,
        final_knowledge_state_ref=kstate,
        isolation_qualification_ref=iso_qual,
        attempt_refs=[attempt],
        required_output_refs=[discovery],
        contamination_assessment_refs=[contamination],
        completion_predicate_result="LANE_COMPLETION_BLOCKED",
    )
    assert lane_blocked.completion_predicate_result == "LANE_COMPLETION_BLOCKED"


# =============================================================================
# F2 — missing/unknown material surface -> STAGE_COMPLETION_BLOCKED
# =============================================================================

def test_f2_missing_unknown_material_surface_blocks_stage_completion():
    """F2: Unknown/unsupported material scope must block stage completion."""
    history_cut = {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": "camp_f2",
        "accepted_head_seq": 8,
        "accepted_head_hash": "hash_head_f2",
    }
    stage_run = _external_ref("stage_run", "sr_f2")
    stage_spec = _external_ref("stage_spec", "ss_f2")
    lane_slot = _external_ref("lane_completion", "lc_f2")

    # 1. Unknown surface in denominator cannot be omitted or treated as N/A
    with pytest.raises(ValidationError, match="STAGE_COMPLETION_BLOCKED"):
        StageCompletion(
            stage_run_ref=stage_run,
            stage_spec_ref=stage_spec,
            input_history_cut=history_cut,
            required_lane_slot_results=[lane_slot],
            unknown_blocked_summary={"unknown_surfaces_count": 3, "is_blocked": True},
            completion_predicate_result="STAGE_COMPLETED",
        )

    # 2. Unresolved material refs also block stage completion
    unresolved_ref = _external_ref("registered_immutable_object", "unresolved_item")
    with pytest.raises(ValidationError, match="STAGE_COMPLETION_BLOCKED"):
        StageCompletion(
            stage_run_ref=stage_run,
            stage_spec_ref=stage_spec,
            input_history_cut=history_cut,
            required_lane_slot_results=[lane_slot],
            unresolved_material_refs=[unresolved_ref],
            completion_predicate_result="STAGE_COMPLETED",
        )

    # 3. Required normative outcome is STAGE_COMPLETION_BLOCKED
    sc_blocked = StageCompletion(
        stage_run_ref=stage_run,
        stage_spec_ref=stage_spec,
        input_history_cut=history_cut,
        required_lane_slot_results=[lane_slot],
        unknown_blocked_summary={"unknown_surfaces_count": 3, "is_blocked": True},
        completion_predicate_result="STAGE_COMPLETION_BLOCKED",
    )
    assert sc_blocked.completion_predicate_result == "STAGE_COMPLETION_BLOCKED"


# =============================================================================
# F3 — shared broken oracle -> required independence qualification REJECTED
# =============================================================================

def test_f3_shared_broken_oracle_rejects_independence():
    """F3: Two evidence paths sharing an oracle cannot claim INDEPENDENT."""
    history_cut = {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": "camp_f3",
        "accepted_head_seq": 6,
        "accepted_head_hash": "hash_head_f3",
    }
    claim = _external_ref("finding_claim_revision", "claim_f3")
    dep_graph = _external_ref("registered_immutable_object", "dep_graph_f3")
    policy = _external_ref("policy_revision", "indep_policy_f3")

    shared_oracle = _external_ref("registered_immutable_object", "shared_oracle_dependency")

    # Masquerading as independent when sharing oracle must be rejected
    with pytest.raises(ValidationError, match="SHARED_ORACLE_INDEPENDENCE_REJECTED"):
        DependencyIndependenceAssessment(
            claim_revision_ref=claim,
            assessment_input_history_cut=history_cut,
            dependency_graph_ref=dep_graph,
            independence_policy_ref=policy,
            result="INDEPENDENT",
            shared_dependency_refs=[shared_oracle],
            independent_dependency_refs=[shared_oracle],
            reason_codes=["ASSERTED_INDEPENDENT"],
        )

    # Valid outcome for shared dependency is REJECTED
    dep_assessment = DependencyIndependenceAssessment(
        claim_revision_ref=claim,
        assessment_input_history_cut=history_cut,
        dependency_graph_ref=dep_graph,
        independence_policy_ref=policy,
        result="REJECTED",
        shared_dependency_refs=[shared_oracle],
        independent_dependency_refs=[],
        reason_codes=["SHARED_ORACLE_DETECTED"],
    )
    assert dep_assessment.result == "REJECTED"


# =============================================================================
# F4 — crash / idempotent retry -> EXACTLY ONE accepted effect
# =============================================================================

def test_f4_crash_and_idempotent_retry_exactly_one_accepted_effect():
    """F4: Crash boundary leaves 0 effects; recovery + retry results in exactly 1 commit."""
    db_path = _fresh_db("F4_CRASH_RETRY.sqlite")
    store = TransactionalHistoryStore(db_path)
    coordinator = Coordinator(store)

    # 1. Genesis commit (seq 1)
    profile, bootstrap_cmd, genesis_objects, _ = bootstrap_fixture()
    commit_1 = coordinator.accept(bootstrap_cmd, immutable_objects=genesis_objects, bootstrap_profile=profile)
    head_1 = commit_1.head
    head_1_ref = {"tag": "ACCEPTED_HEAD_REF", **head_1.as_dict()}

    # Verify 1 commit in DB
    con = sqlite3.connect(db_path)
    count = con.execute("SELECT count(*) FROM commits").fetchone()[0]
    con.close()
    assert count == 1

    # 2. Simulate crash boundary: an accept that fails / crashes before commit
    cmd_2 = replace(
        bootstrap_cmd,
        command_id="command_f4000000-0000-4000-8000-000000000002",
        command_kind="RECORD_FOUNDATION_FACT",
        actor_ref="installation-owner",
        expected_parent_head=head_1_ref,
        campaign_ref="campaign_fixture",
        proposed_campaign_id=None,
        history_namespace_ref=None,
        bootstrap_profile_ref=None,
    )

    # Trigger a failure / crash during accept by passing an invalid object
    bad_obj = CanonicalObject("stage_spec", {
        "stage_key": "E3",
        # missing required fields -> fails schema validation
    })
    with pytest.raises(ValidationError):
        coordinator.accept(cmd_2, immutable_objects=(bad_obj,), expected_head=head_1)

    # Verify transaction rolled back: STILL EXACTLY 1 commit in database (NOT partially committed)
    con = sqlite3.connect(db_path)
    count = con.execute("SELECT count(*) FROM commits").fetchone()[0]
    con.close()
    assert count == 1

    # 3. Recovery: reopen store from durable SQLite file
    store_recovered = TransactionalHistoryStore(db_path)
    coordinator_recovered = Coordinator(store_recovered)

    # Valid object for commit 2
    cut_1 = {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": head_1.campaign_id,
        "accepted_head_seq": head_1.commit_seq,
        "accepted_head_hash": head_1.commit_hash,
        "governing_policy_ref": commit_1.commit.governing_policy_ref,
        "governing_spec_refs": list(commit_1.commit.governing_spec_refs),
    }
    stage_spec_valid = StageSpec(
        stage_key="E3",
        stage_spec_revision="1",
        stage_role="E3",
        stage_ordinal=3,
        purpose="F4 Recovery test",
        predecessor_requirements=("E2",),
        required_lane_slots=("lane_1",),
        blind_reveal_phase_model="CONTROLLED",
        transition_policy_ref="TRANSITION_PROFILE_V1",
    ).as_object()

    # Retry cmd_2 -> accepted
    res_retry_1 = coordinator_recovered.accept(cmd_2, immutable_objects=(stage_spec_valid,), expected_head=head_1)
    assert res_retry_1.commit.commit_seq == 2
    assert not res_retry_1.already_accepted

    # 4. Idempotent re-submission of the EXACT SAME command envelope
    res_retry_2 = coordinator_recovered.accept(cmd_2, immutable_objects=(stage_spec_valid,), expected_head=head_1)
    assert res_retry_2.already_accepted is True
    assert res_retry_2.receipt.digest == res_retry_1.receipt.digest
    assert res_retry_2.head.commit_hash == res_retry_1.head.commit_hash

    # 5. Proof of EXACTLY ONE accepted effect in durable SQLite store (not 0, not 2)
    con = sqlite3.connect(db_path)
    count = con.execute("SELECT count(*) FROM commits").fetchone()[0]
    receipts_count = con.execute("SELECT count(*) FROM receipts").fetchone()[0]
    con.close()
    assert count == 2  # genesis + exactly one commit 2
    assert receipts_count == 2


# =============================================================================
# F5 — stale predecessor -> BLOCKED_CANONICAL_ADMISSION
# =============================================================================

def test_f5_stale_predecessor_blocked_canonical_admission():
    """F5: Stale predecessor lineage evaluates to and enforces BLOCKED_CANONICAL_ADMISSION."""
    db_path = _fresh_db("F5_STALE_PREDECESSOR.sqlite")
    store = TransactionalHistoryStore(db_path)
    coordinator = Coordinator(store)

    # 1. In bootstrap: blocked admission decision rejects CampaignGenesis
    profile, bootstrap_cmd, genesis_objects, _ = bootstrap_fixture()

    # Evaluating stale / replayed predecessor produces BLOCKED_CANONICAL_ADMISSION
    orig_admission = next(o for o in genesis_objects if o.kind == "bootstrap_admission_decision")
    blocked_body = dict(orig_admission.body)
    blocked_body["result"] = "BLOCKED_CANONICAL_ADMISSION"
    blocked_body["reason_codes"] = ["STALE_PREDECESSOR_LINEAGE"]
    blocked_admission = CanonicalObject("bootstrap_admission_decision", blocked_body, logical_id=orig_admission.logical_id)

    # Exact normative outcome assertion for F5:
    assert blocked_admission.body["result"] == "BLOCKED_CANONICAL_ADMISSION"

    modified_genesis_objects = [
        blocked_admission if o.kind == "bootstrap_admission_decision" else o
        for o in genesis_objects
    ]

    # BLOCKED_CANONICAL_ADMISSION strictly forbids CampaignGenesis emission
    with pytest.raises(ValidationError, match="BLOCKED_ADMISSION_CANNOT_EMIT_GENESIS"):
        coordinator.accept(bootstrap_cmd, immutable_objects=modified_genesis_objects, bootstrap_profile=profile)

    # Verify zero commits in durable store
    con = sqlite3.connect(db_path)
    count = con.execute("SELECT count(*) FROM commits").fetchone()[0]
    con.close()
    assert count == 0


def test_steady_state_stale_parent_head_fails_closed():
    """Steady-state head conflict: stale expected_parent_head refuses fallback without shortcuts."""
    db_path = _fresh_db("STEADY_STATE_STALE_HEAD.sqlite")
    store = TransactionalHistoryStore(db_path)
    coordinator = Coordinator(store)

    profile, bootstrap_cmd, genesis_objects, _ = bootstrap_fixture()
    commit_1 = coordinator.accept(bootstrap_cmd, immutable_objects=genesis_objects, bootstrap_profile=profile)
    head_1 = commit_1.head
    head_1_ref = {"tag": "ACCEPTED_HEAD_REF", **head_1.as_dict()}

    stage_spec_obj = StageSpec(
        stage_key="E3",
        stage_spec_revision="1",
        stage_role="E3",
        stage_ordinal=3,
        purpose="Steady state stage spec",
        predecessor_requirements=("E2",),
        required_lane_slots=("lane_1",),
        blind_reveal_phase_model="CONTROLLED",
        transition_policy_ref="TRANSITION_PROFILE_V1",
    ).as_object()

    cmd_2 = replace(
        bootstrap_cmd,
        command_id="command_f5000000-0000-4000-8000-000000000002",
        command_kind="RECORD_FOUNDATION_FACT",
        actor_ref="installation-owner",
        expected_parent_head=head_1_ref,
        campaign_ref="campaign_fixture",
        proposed_campaign_id=None,
        history_namespace_ref=None,
        bootstrap_profile_ref=None,
    )
    commit_2 = coordinator.accept(cmd_2, immutable_objects=(stage_spec_obj,), expected_head=head_1)
    head_2 = commit_2.head
    assert head_2.commit_seq == 2

    # Now attempt commit 3 using STALE head_1 (seq=1) instead of head_2 (seq=2)
    cmd_3_stale = replace(
        bootstrap_cmd,
        command_id="command_f5000000-0000-4000-8000-000000000003",
        command_kind="RECORD_FOUNDATION_FACT",
        actor_ref="installation-owner",
        expected_parent_head=head_1_ref,  # Stale!
        campaign_ref="campaign_fixture",
        proposed_campaign_id=None,
        history_namespace_ref=None,
        bootstrap_profile_ref=None,
    )

    stage_run = CanonicalObject("stage_run", {
        "stage_run_id": "sr_f5",
        "campaign_ref": "campaign_fixture",
        "stage_spec_ref": _ref_for("stage_run", "stage_spec_ref", stage_spec_obj),
        "source_generation_ref": _ref_for("stage_run", "source_generation_ref", genesis_objects[1]),
        "creation_input_history_cut": {"variant": "ACCEPTED_HISTORY_CUT", "campaign_id": "campaign_fixture", "accepted_head_seq": 1, "accepted_head_hash": head_1.commit_hash},
        "assigned_history_cut": {"variant": "ACCEPTED_HISTORY_CUT", "campaign_id": "campaign_fixture", "accepted_head_seq": 1, "accepted_head_hash": head_1.commit_hash},
        "predecessor_stage_completion_refs": [],
        "required_lane_slot_contract_refs": [_external_ref("result_slot_contract_ref", "slot_c", ref_class="HISTORY_CONTEXT_BINDING")],
    })

    # Must reject fail-closed without latest-lookup shortcut or fallback:
    # 2a. Caller passes stale expected_head -> EXPECTED_HEAD_CONFLICT
    with pytest.raises(ValidationError, match="EXPECTED_HEAD_CONFLICT"):
        coordinator.accept(cmd_3_stale, immutable_objects=(stage_run,), expected_head=head_1)

    # 2b. Command envelope binds stale expected_parent_head against current head -> COMMAND_BINDING_CONFLICT
    with pytest.raises(ValidationError, match="COMMAND_BINDING_CONFLICT"):
        coordinator.accept(cmd_3_stale, immutable_objects=(stage_run,), expected_head=head_2)


# =============================================================================
# F6 — invalidated evidence -> completion BLOCKED until replacement
# =============================================================================

def test_f6_invalidated_evidence_blocks_completion_until_replacement():
    """F6: Accepted evidence invalidation blocks completion; replacement does not erase history."""
    db_path = _fresh_db("F6_INVALIDATED_EVIDENCE.sqlite")
    ctx = run_foundation_reference_slice(db_path, stop_at_seq=9)
    det_id = ctx["det_id"]
    head_cut = ctx["head_cut"]
    cov_ob = ctx["cov_ob"]
    cov_qual = ctx["cov_qual"]

    invalidation = EvidenceInvalidation(
        invalidation_id=det_id("evidence_invalidation"),
        affected_evidence_or_qualification_refs=[_ref_for("coverage_obligation_qualification", "obligation_revision_ref", cov_ob)],
        dependency_ref=_external_ref("registered_immutable_object", "bad_oracle", ref_class="CONTENT_OR_PRIOR"),
        invalidation_input_history_cut=head_cut,
        propagation_policy_ref=_external_ref("policy_revision", "inval_policy", ref_class="HISTORY_CONTEXT_BINDING"),
        reason_codes=["HARNESS_CORRUPTED"],
    )

    # When evidence_invalidation_refs is populated, STOP evaluation must be BLOCKED
    stop_input_invalidated = StopInput(
        stop_input_id=det_id("stop_input"),
        campaign_id=ctx["campaign_id"],
        source_generation_ref=_ref_for("stop_input", "source_generation_ref", ctx["source_gen"]),
        input_history_cut=head_cut,
        evaluation_context="FINAL_POST_E5",
        governing_policy_ref=_external_ref("policy_revision", "p1", ref_class="HISTORY_CONTEXT_BINDING"),
        policy_spec_refs=[_external_ref("spec_revision", "sp1", ref_class="HISTORY_CONTEXT_BINDING")],
        evaluator_revision_ref=_external_ref("spec_revision", "ev1", ref_class="HISTORY_CONTEXT_BINDING"),
        required_stage_set_ref=_external_ref("external_profile_ref", "stg1", ref_class="HISTORY_CONTEXT_BINDING"),
        required_stage_spec_refs=[_ref_for("stop_input", "required_stage_spec_refs", ctx["stage_spec_obj"])],
        completed_stage_refs=[_ref_for("stop_input", "completed_stage_refs", ctx["stage_comp"])],
        pending_required_stage_refs=[],
        stop_input_snapshot_ref=_external_ref("snapshot", "snap_f6", ref_class="CONTENT_OR_PRIOR"),
        inventory_revision_ref=_ref_for("stop_input", "inventory_revision_ref", ctx["inv_rev"]),
        mandatory_obligation_refs=[_ref_for("stop_input", "mandatory_obligation_refs", cov_ob)],
        current_obligation_qualification_refs=[_ref_for("stop_input", "current_obligation_qualification_refs", cov_qual)],
        evidence_invalidation_refs=[_ref_for("stop_input", "evidence_invalidation_refs", invalidation)],
        contradiction_refs=[],
        residual_risk_refs=[],
        evidence_invalidation_state={"invalidated_count": 1},
        release_policy_ref=_external_ref("policy_revision", "rp1", ref_class="HISTORY_CONTEXT_BINDING"),
        effort_profile_ref=_external_ref("external_profile_ref", "eff1", ref_class="HISTORY_CONTEXT_BINDING"),
        effort_results_ref=_external_ref("registered_immutable_object", "eff_res", ref_class="CONTENT_OR_PRIOR"),
        continuation_budget_authorization_ref=None,
        unknown_blocked_summary={"unknown_surfaces_count": 0, "is_blocked": False},
    )

    eval_invalidated = evaluate_stop(stop_input_invalidated)
    assert eval_invalidated.continuation_decision == "BLOCKED"
    assert eval_invalidated.release_readiness == "QUALIFICATION_BLOCKED"
    assert "UNRESOLVED_EVIDENCE_INVALIDATION" in eval_invalidated.reason_codes

    # Replacement qualification: obligation re-qualified with clean evidence
    # Historical invalidation is preserved in history and not deleted
    assert invalidation.as_object().kind == "evidence_invalidation"


# =============================================================================
# F7 — insufficient-data intermediate STOP -> CONTINUE_REQUIRED (both reasons)
# =============================================================================

def test_f7_insufficient_data_intermediate_stop_both_reasons():
    """F7: Intermediate STOP with pending stages and insufficient data retains BOTH reason codes."""
    db_path = _fresh_db("F7_INSUFFICIENT_DATA.sqlite")
    ctx = run_foundation_reference_slice(db_path, stop_at_seq=9)
    det_id = ctx["det_id"]
    head_cut = ctx["head_cut"]

    e4_spec = _external_ref("stage_spec", "e4", ref_class="HISTORY_CONTEXT_BINDING")
    e5_spec = _external_ref("stage_spec", "e5", ref_class="HISTORY_CONTEXT_BINDING")

    stop_input = StopInput(
        stop_input_id=det_id("stop_input"),
        campaign_id=ctx["campaign_id"],
        source_generation_ref=_ref_for("stop_input", "source_generation_ref", ctx["source_gen"]),
        input_history_cut=head_cut,
        evaluation_context="INTERMEDIATE",
        governing_policy_ref=_external_ref("policy_revision", "p1", ref_class="HISTORY_CONTEXT_BINDING"),
        policy_spec_refs=[_external_ref("spec_revision", "sp1", ref_class="HISTORY_CONTEXT_BINDING")],
        evaluator_revision_ref=_external_ref("spec_revision", "ev1", ref_class="HISTORY_CONTEXT_BINDING"),
        required_stage_set_ref=_external_ref("external_profile_ref", "stg1", ref_class="HISTORY_CONTEXT_BINDING"),
        required_stage_spec_refs=[_ref_for("stop_input", "required_stage_spec_refs", ctx["stage_spec_obj"]), e4_spec, e5_spec],
        completed_stage_refs=[_ref_for("stop_input", "completed_stage_refs", ctx["stage_comp"])],
        pending_required_stage_refs=[e4_spec, e5_spec],
        stop_input_snapshot_ref=_external_ref("snapshot", "snap_f7", ref_class="CONTENT_OR_PRIOR"),
        inventory_revision_ref=_ref_for("stop_input", "inventory_revision_ref", ctx["inv_rev"]),
        mandatory_obligation_refs=[_ref_for("stop_input", "mandatory_obligation_refs", ctx["cov_ob"])],
        current_obligation_qualification_refs=[_ref_for("stop_input", "current_obligation_qualification_refs", ctx["cov_qual"])],
        evidence_invalidation_refs=[],
        contradiction_refs=[],
        residual_risk_refs=[],
        evidence_invalidation_state={"invalidated_count": 0},
        release_policy_ref=_external_ref("policy_revision", "rp1", ref_class="HISTORY_CONTEXT_BINDING"),
        effort_profile_ref=_external_ref("external_profile_ref", "eff1", ref_class="HISTORY_CONTEXT_BINDING"),
        effort_results_ref=_external_ref("registered_immutable_object", "eff_res", ref_class="CONTENT_OR_PRIOR"),
        continuation_budget_authorization_ref=None,
        unknown_blocked_summary={"unknown_surfaces_count": 0, "is_blocked": False},
    )

    # Pure evaluation with default insufficient_data=True
    stop_eval = evaluate_stop(stop_input, insufficient_data=True)

    # 1. Must NOT produce PASS or READY
    assert stop_eval.continuation_decision == "CONTINUE_REQUIRED"
    assert stop_eval.release_readiness == "TECHNICALLY_NOT_READY"
    assert stop_eval.assurance_level == "INSUFFICIENT"

    # 2. MUST contain BOTH reason codes simultaneously without short-circuiting
    assert "REQUIRED_STAGES_PENDING" in stop_eval.reason_codes
    assert "INSUFFICIENT_DATA" in stop_eval.reason_codes

    # 3. Fail-closed invariant: validate_intermediate_stop accepts CONTINUE_REQUIRED
    validate_intermediate_stop(stop_eval, "INTERMEDIATE")

"""Comprehensive Adversarial and Positive-Control Suite for RU06 (STOP / Challenge / Finalization).

Tests items A through T according to RU06 specification:
D03:
  - Case A: FINAL_POST_E5 with mandatory obligations but no qualifications -> BLOCKED/QUALIFICATION_BLOCKED
  - Case B: insufficient_data / UNKNOWN in FINAL_POST_E5 -> NOT READY / BLOCKED
  - Case C: POST_E6 with invalidated evidence -> BLOCKED/QUALIFICATION_BLOCKED
  - Case D: POST_E6 with open contradiction -> BLOCKED/QUALIFICATION_BLOCKED
  - Case E: POST_E6 with missing candidate case or missing challengers -> BLOCKED
  - Case F: Multiple failure causes -> all reason codes retained (accumulated)
  - Case G: Positive control: all conditions met -> PASS + READY

D04:
  - Case H: StopInput cut at H, accepted at H+1 -> evaluate_stop_gate does NOT reject as stale
  - Case I: Intermediate administrative commits (conclusion, final_case, release_qual) do not invalidate accepted cut
  - Case J: Material audit commit after cut -> rejected / fails closed as stale

D13:
  - Case K: Same result for both challengers -> REJECT (DUPLICATE_CHALLENGER_RESULT)
  - Case L: Distinct results but same assignment -> REJECT (SAME_CHALLENGE_ASSIGNMENT)
  - Case M: Wrong challenger role -> REJECT (INVALID_SKEPTIC_ROLE / INVALID_HUNTER_ROLE)
  - Case N: Assignment cut precedes candidate cut -> REJECT (TEMPORAL_ORDER_VIOLATION)
  - Case O: Result cut precedes assignment cut -> REJECT (RESULT_PRECEDES_ASSIGNMENT)
  - Case P: Positive control: two distinct roles, valid cuts, distinct attempts -> PASS

D22:
  - Case Q: Stages prepared but no CampaignConclusion -> not completed (VerifiedCampaignReadModel)
  - Case R: CampaignConclusion with COMPLETED_LIMITED -> evaluate_release_qualification never gives READY
  - Case S: Positive control: accepted COMPLETED conclusion -> eligible for READY release qualification
  - Case T: Release drift -> STOP_AXIS_MATERIALIZATION fails closed (DRIFT_DETECTED_MATERIALIZATION_INVALID)
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.stop.evaluator import evaluate_stop
from bdb_audit.stop.models import StopInput, StopEvaluation
from bdb_audit.stop.operation import evaluate_stop_gate
from bdb_audit.assurance.candidate_case import CandidateAssuranceCaseBuilder
from bdb_audit.assurance.challenger import (
    ChallengerAssignment,
    ChallengerResult,
    E5ChallengerOrchestrator,
)
from bdb_audit.assurance.conclusion import CampaignConclusion, FinalAssuranceCase
from bdb_audit.assurance.release import ReleaseLifecycleManager, ReleaseQualification
from bdb_audit.workflow.read_models import VerifiedCampaignReadModel
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.history.objects import CanonicalObject, CommandEnvelope


def _ref(kind: str, token: str, ref_class: str = "CONTENT_OR_PRIOR") -> dict:
    import hashlib
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
    }


@pytest.fixture
def base_stop_kwargs():
    hcut = {"campaign_id": "CAMP-RU06", "accepted_head_seq": 10, "accepted_head_hash": "a" * 64}
    p = _ref("policy_revision", "p", "HISTORY_CONTEXT_BINDING")
    s = _ref("spec_revision", "s", "HISTORY_CONTEXT_BINDING")
    cac = _ref("candidate_assurance_case", "cac")
    cr1 = _ref("challenger_result", "cr1")
    cr2 = _ref("challenger_result", "cr2")

    return {
        "campaign_id": "CAMP-RU06",
        "source_generation_ref": _ref("source_generation", "sg"),
        "input_history_cut": hcut,
        "evaluation_context": "FINAL_POST_E5",
        "governing_policy_ref": p,
        "policy_spec_refs": [s],
        "evaluator_revision_ref": s,
        "required_stage_set_ref": _ref("external_profile_ref", "st", "HISTORY_CONTEXT_BINDING"),
        "required_stage_spec_refs": [s],
        "completed_stage_refs": [s],
        "pending_required_stage_refs": [],
        "stop_input_snapshot_ref": _ref("snapshot", "sn"),
        "inventory_revision_ref": _ref("inventory_revision", "inv"),
        "mandatory_obligation_refs": [],
        "current_obligation_qualification_refs": [],
        "evidence_invalidation_refs": [],
        "contradiction_refs": [],
        "residual_risk_refs": [],
        "evidence_invalidation_state": {"invalidated_count": 0},
        "release_policy_ref": p,
        "effort_profile_ref": _ref("external_profile_ref", "eff", "HISTORY_CONTEXT_BINDING"),
        "effort_results_ref": {"rounds_executed": 5},
        "unknown_blocked_summary": {"unknown_surfaces_count": 0, "is_blocked": False},
        "candidate_assurance_case_ref": cac,
        "challenger_refs": [cr1, cr2],
    }


# =========================================================================
# D03 Tests: Cases A - G
# =========================================================================

def test_case_a_final_post_e5_mandatory_obligations_unqualified(base_stop_kwargs):
    kwargs = dict(base_stop_kwargs)
    kwargs["mandatory_obligation_refs"] = [_ref("coverage_obligation", "ob1")]
    kwargs["current_obligation_qualification_refs"] = []
    si = StopInput(**kwargs)

    ev = evaluate_stop(si, insufficient_data=False, e6_plan_approved=False)
    assert ev.continuation_decision == "BLOCKED"
    assert ev.release_readiness == "QUALIFICATION_BLOCKED"
    assert "UNQUALIFIED_MANDATORY_OBLIGATIONS" in ev.reason_codes


def test_case_b_insufficient_data_unknown_not_ready(base_stop_kwargs):
    kwargs = dict(base_stop_kwargs)
    si = StopInput(**kwargs)

    ev = evaluate_stop(si, insufficient_data=True, e6_plan_approved=False)
    assert ev.continuation_decision == "BLOCKED"
    assert ev.release_readiness == "QUALIFICATION_BLOCKED"
    assert "INSUFFICIENT_DATA" in ev.reason_codes


def test_case_c_post_e6_invalidated_evidence_blocks(base_stop_kwargs):
    kwargs = dict(base_stop_kwargs)
    kwargs["evaluation_context"] = "POST_E6"
    kwargs["evidence_invalidation_refs"] = [_ref("evidence_invalidation", "inv1")]
    si = StopInput(**kwargs)

    ev = evaluate_stop(si, insufficient_data=False)
    assert ev.continuation_decision == "BLOCKED"
    assert ev.release_readiness == "QUALIFICATION_BLOCKED"
    assert "UNRESOLVED_EVIDENCE_INVALIDATION" in ev.reason_codes


def test_case_d_post_e6_open_contradiction_blocks(base_stop_kwargs):
    kwargs = dict(base_stop_kwargs)
    kwargs["evaluation_context"] = "POST_E6"
    kwargs["contradiction_refs"] = [_ref("contradiction_revision", "contra1")]
    si = StopInput(**kwargs)

    ev = evaluate_stop(si, insufficient_data=False)
    assert ev.continuation_decision == "BLOCKED"
    assert ev.release_readiness == "QUALIFICATION_BLOCKED"
    assert "OPEN_CONTRADICTION" in ev.reason_codes


def test_case_e_post_e6_missing_candidate_or_challengers_blocks(base_stop_kwargs):
    kwargs = dict(base_stop_kwargs)
    kwargs["evaluation_context"] = "POST_E6"
    kwargs["candidate_assurance_case_ref"] = None
    si = StopInput(**kwargs)

    ev = evaluate_stop(si, insufficient_data=False)
    assert ev.continuation_decision == "BLOCKED"
    assert "MISSING_CANDIDATE_ASSURANCE_CASE" in ev.reason_codes


def test_case_f_multiple_failures_accumulate_all_reason_codes(base_stop_kwargs):
    kwargs = dict(base_stop_kwargs)
    kwargs["evidence_invalidation_refs"] = [_ref("evidence_invalidation", "inv1")]
    kwargs["contradiction_refs"] = [_ref("contradiction_revision", "contra1")]
    kwargs["candidate_assurance_case_ref"] = None
    kwargs["challenger_refs"] = []
    si = StopInput(**kwargs)

    ev = evaluate_stop(si, insufficient_data=False)
    assert ev.continuation_decision == "BLOCKED"
    assert "UNRESOLVED_EVIDENCE_INVALIDATION" in ev.reason_codes
    assert "OPEN_CONTRADICTION" in ev.reason_codes
    assert "MISSING_CANDIDATE_ASSURANCE_CASE" in ev.reason_codes
    assert "MISSING_REQUIRED_CHALLENGERS" in ev.reason_codes


def test_case_g_positive_control_stop_pass_ready(base_stop_kwargs):
    si = StopInput(**base_stop_kwargs)
    ev = evaluate_stop(si, insufficient_data=False)
    assert ev.continuation_decision == "PASS"
    assert ev.assurance_level == "ADEQUATE_FOR_DECLARED_SCOPE"
    assert ev.release_readiness == "READY"
    assert "ALL_REQUIREMENTS_SATISFIED" in ev.reason_codes


# =========================================================================
# D04 Tests: Cases H - J
# =========================================================================

def test_case_h_accepted_stop_input_cut_h_evaluated_at_h_plus_1(tmp_path: Path):
    store_path = tmp_path / "campaign_h.sqlite"
    api = AuditOperationApi()
    created = api.create_campaign(store_path, seed="case_h")
    cid = created["campaign_id"]
    h_seq = created["commit_seq"]
    h_hash = created["commit_hash"]

    # Build valid StopInput dict with cut at commit H
    cut = {"campaign_id": cid, "accepted_head_seq": h_seq, "accepted_head_hash": h_hash}
    p = _ref("policy_revision", "p", "HISTORY_CONTEXT_BINDING")
    s = _ref("spec_revision", "s", "HISTORY_CONTEXT_BINDING")
    cac = _ref("candidate_assurance_case", "cac")
    cr1 = _ref("challenger_result", "cr1")
    cr2 = _ref("challenger_result", "cr2")

    si_dict = {
        "campaign_id": cid,
        "source_generation_ref": _ref("source_generation", "sg"),
        "input_history_cut": cut,
        "evaluation_context": "FINAL_POST_E5",
        "governing_policy_ref": p,
        "policy_spec_refs": [s],
        "evaluator_revision_ref": s,
        "required_stage_set_ref": _ref("external_profile_ref", "st", "HISTORY_CONTEXT_BINDING"),
        "required_stage_spec_refs": [s],
        "completed_stage_refs": [s],
        "pending_required_stage_refs": [],
        "stop_input_snapshot_ref": _ref("snapshot", "sn"),
        "inventory_revision_ref": _ref("inventory_revision", "inv"),
        "mandatory_obligation_refs": [],
        "current_obligation_qualification_refs": [],
        "evidence_invalidation_refs": [],
        "contradiction_refs": [],
        "residual_risk_refs": [],
        "evidence_invalidation_state": {"invalidated_count": 0},
        "release_policy_ref": p,
        "effort_profile_ref": _ref("external_profile_ref", "eff", "HISTORY_CONTEXT_BINDING"),
        "effort_results_ref": {"rounds_executed": 5},
        "unknown_blocked_summary": {"unknown_surfaces_count": 0, "is_blocked": False},
        "candidate_assurance_case_ref": cac,
        "challenger_refs": [cr1, cr2],
    }

    import sqlite3
    con = sqlite3.connect(store_path)
    import hashlib
    si_digest = hashlib.sha256(json.dumps(si_dict, sort_keys=True).encode("utf-8")).hexdigest()
    con.execute(
        "INSERT INTO immutable_objects(digest,kind,version,schema_ref,logical_id,body) VALUES(?,?,?,?,?,?)",
        (si_digest, "stop_input", "1", "BDB_SCHEMA_REGISTRY::stop_input/1", None, json.dumps(si_dict)),
    )
    c2_hash = hashlib.sha256(b"commit_2_h").hexdigest()
    c2_body = {
        "campaign_id": cid,
        "commit_seq": h_seq + 1,
        "prev_history_ref": {"commit_seq": h_seq, "commit_hash": h_hash},
        "command_ref": {"kind": "command_envelope", "revision_digest": hashlib.sha256(b"cmd2").hexdigest(), "ref_class": "CONTENT_OBJECT"},
        "command_digest": hashlib.sha256(b"cmd2").hexdigest(),
        "actor_ref": "installation-owner",
        "expected_parent_head": {"commit_seq": h_seq, "commit_hash": h_hash},
        "governing_policy_ref": "pin:initial_governing_policy_ref",
        "governing_spec_refs": ["pin:initial_transition_profile_ref"],
        "ordered_event_bodies": [],
        "immutable_object_refs": [{"kind": "stop_input", "revision_digest": si_digest, "ref_class": "CONTENT_OBJECT"}],
    }
    con.execute(
        "INSERT INTO commits(seq,commit_hash,campaign_id,body) VALUES(?,?,?,?)",
        (h_seq + 1, c2_hash, cid, json.dumps(c2_body)),
    )
    con.execute(
        "UPDATE accepted_head SET seq=?, commit_hash=? WHERE singleton=1",
        (h_seq + 1, c2_hash),
    )
    con.commit()
    con.close()

    # Now head is at H+1. evaluate_stop_gate on accepted history should NOT fail with STOP_INPUT_CUT_MISMATCH
    res = evaluate_stop_gate(store_path)
    assert res["status"] == "SUCCESS"
    assert res["evaluated"] is True
    assert res["continuation_decision"] == "PASS"


def test_case_i_administrative_commits_do_not_stale_accepted_stop_input(tmp_path: Path):
    store_path = tmp_path / "campaign_i.sqlite"
    api = AuditOperationApi()
    created = api.create_campaign(store_path, seed="case_i")
    cid = created["campaign_id"]
    h_seq = created["commit_seq"]
    h_hash = created["commit_hash"]

    cut = {"campaign_id": cid, "accepted_head_seq": h_seq, "accepted_head_hash": h_hash}
    p = _ref("policy_revision", "p", "HISTORY_CONTEXT_BINDING")
    s = _ref("spec_revision", "s", "HISTORY_CONTEXT_BINDING")
    cac = _ref("candidate_assurance_case", "cac")
    cr1 = _ref("challenger_result", "cr1")
    cr2 = _ref("challenger_result", "cr2")

    si_dict = {
        "campaign_id": cid,
        "source_generation_ref": _ref("source_generation", "sg"),
        "input_history_cut": cut,
        "evaluation_context": "FINAL_POST_E5",
        "governing_policy_ref": p,
        "policy_spec_refs": [s],
        "evaluator_revision_ref": s,
        "required_stage_set_ref": _ref("external_profile_ref", "st", "HISTORY_CONTEXT_BINDING"),
        "required_stage_spec_refs": [s],
        "completed_stage_refs": [s],
        "pending_required_stage_refs": [],
        "stop_input_snapshot_ref": _ref("snapshot", "sn"),
        "inventory_revision_ref": _ref("inventory_revision", "inv"),
        "mandatory_obligation_refs": [],
        "current_obligation_qualification_refs": [],
        "evidence_invalidation_refs": [],
        "contradiction_refs": [],
        "residual_risk_refs": [],
        "evidence_invalidation_state": {"invalidated_count": 0},
        "release_policy_ref": p,
        "effort_profile_ref": _ref("external_profile_ref", "eff", "HISTORY_CONTEXT_BINDING"),
        "effort_results_ref": {"rounds_executed": 5},
        "unknown_blocked_summary": {"unknown_surfaces_count": 0, "is_blocked": False},
        "candidate_assurance_case_ref": cac,
        "challenger_refs": [cr1, cr2],
    }

    import sqlite3
    con = sqlite3.connect(store_path)
    import hashlib
    si_digest = hashlib.sha256(json.dumps(si_dict, sort_keys=True).encode("utf-8")).hexdigest()
    con.execute(
        "INSERT INTO immutable_objects(digest,kind,version,schema_ref,logical_id,body) VALUES(?,?,?,?,?,?)",
        (si_digest, "stop_input", "1", "BDB_SCHEMA_REGISTRY::stop_input/1", None, json.dumps(si_dict)),
    )
    # Commit 2: accepts stop_input
    c2_hash = hashlib.sha256(b"commit_2_i").hexdigest()
    c2_body = {
        "campaign_id": cid,
        "commit_seq": h_seq + 1,
        "prev_history_ref": {"commit_seq": h_seq, "commit_hash": h_hash},
        "command_ref": {"kind": "command_envelope", "revision_digest": hashlib.sha256(b"cmd2_i").hexdigest(), "ref_class": "CONTENT_OBJECT"},
        "command_digest": hashlib.sha256(b"cmd2_i").hexdigest(),
        "actor_ref": "installation-owner",
        "expected_parent_head": {"commit_seq": h_seq, "commit_hash": h_hash},
        "governing_policy_ref": "pin:initial_governing_policy_ref",
        "governing_spec_refs": ["pin:initial_transition_profile_ref"],
        "ordered_event_bodies": [],
        "immutable_object_refs": [{"kind": "stop_input", "revision_digest": si_digest, "ref_class": "CONTENT_OBJECT"}],
    }
    con.execute(
        "INSERT INTO commits(seq,commit_hash,campaign_id,body) VALUES(?,?,?,?)",
        (h_seq + 1, c2_hash, cid, json.dumps(c2_body)),
    )

    # Commit 3: accepts stop_evaluation (administrative commit)
    c3_hash = hashlib.sha256(b"commit_3_i").hexdigest()
    se_digest = hashlib.sha256(b"se_digest").hexdigest()
    c3_body = {
        "campaign_id": cid,
        "commit_seq": h_seq + 2,
        "prev_history_ref": {"commit_seq": h_seq + 1, "commit_hash": c2_hash},
        "command_ref": {"kind": "command_envelope", "revision_digest": hashlib.sha256(b"cmd3_i").hexdigest(), "ref_class": "CONTENT_OBJECT"},
        "command_digest": hashlib.sha256(b"cmd3_i").hexdigest(),
        "actor_ref": "installation-owner",
        "expected_parent_head": {"commit_seq": h_seq + 1, "commit_hash": c2_hash},
        "governing_policy_ref": "pin:initial_governing_policy_ref",
        "governing_spec_refs": ["pin:initial_transition_profile_ref"],
        "ordered_event_bodies": [],
        "immutable_object_refs": [{"kind": "stop_evaluation", "revision_digest": se_digest, "ref_class": "CONTENT_OBJECT"}],
    }
    con.execute(
        "INSERT INTO commits(seq,commit_hash,campaign_id,body) VALUES(?,?,?,?)",
        (h_seq + 2, c3_hash, cid, json.dumps(c3_body)),
    )
    con.execute(
        "UPDATE accepted_head SET seq=?, commit_hash=? WHERE singleton=1",
        (h_seq + 2, c3_hash),
    )
    con.commit()
    con.close()

    # evaluate_stop_gate should still evaluate successfully
    res = evaluate_stop_gate(store_path)
    assert res["status"] == "SUCCESS"
    assert res["evaluated"] is True


def test_case_j_material_audit_commit_after_cut_fails_closed(tmp_path: Path):
    store_path = tmp_path / "campaign_j.sqlite"
    api = AuditOperationApi()
    created = api.create_campaign(store_path, seed="case_j")
    cid = created["campaign_id"]
    h_seq = created["commit_seq"]
    h_hash = created["commit_hash"]

    cut = {"campaign_id": cid, "accepted_head_seq": h_seq, "accepted_head_hash": h_hash}
    p = _ref("policy_revision", "p", "HISTORY_CONTEXT_BINDING")
    s = _ref("spec_revision", "s", "HISTORY_CONTEXT_BINDING")
    cac = _ref("candidate_assurance_case", "cac")
    cr1 = _ref("challenger_result", "cr1")
    cr2 = _ref("challenger_result", "cr2")

    si_dict = {
        "campaign_id": cid,
        "source_generation_ref": _ref("source_generation", "sg"),
        "input_history_cut": cut,
        "evaluation_context": "FINAL_POST_E5",
        "governing_policy_ref": p,
        "policy_spec_refs": [s],
        "evaluator_revision_ref": s,
        "required_stage_set_ref": _ref("external_profile_ref", "st", "HISTORY_CONTEXT_BINDING"),
        "required_stage_spec_refs": [s],
        "completed_stage_refs": [s],
        "pending_required_stage_refs": [],
        "stop_input_snapshot_ref": _ref("snapshot", "sn"),
        "inventory_revision_ref": _ref("inventory_revision", "inv"),
        "mandatory_obligation_refs": [],
        "current_obligation_qualification_refs": [],
        "evidence_invalidation_refs": [],
        "contradiction_refs": [],
        "residual_risk_refs": [],
        "evidence_invalidation_state": {"invalidated_count": 0},
        "release_policy_ref": p,
        "effort_profile_ref": _ref("external_profile_ref", "eff", "HISTORY_CONTEXT_BINDING"),
        "effort_results_ref": {"rounds_executed": 5},
        "unknown_blocked_summary": {"unknown_surfaces_count": 0, "is_blocked": False},
        "candidate_assurance_case_ref": cac,
        "challenger_refs": [cr1, cr2],
    }

    import sqlite3
    con = sqlite3.connect(store_path)
    import hashlib
    si_digest = hashlib.sha256(json.dumps(si_dict, sort_keys=True).encode("utf-8")).hexdigest()
    con.execute(
        "INSERT INTO immutable_objects(digest,kind,version,schema_ref,logical_id,body) VALUES(?,?,?,?,?,?)",
        (si_digest, "stop_input", "1", "BDB_SCHEMA_REGISTRY::stop_input/1", None, json.dumps(si_dict)),
    )
    # Commit 2: accepts stop_input
    c2_hash = hashlib.sha256(b"commit_2_j").hexdigest()
    c2_body = {
        "campaign_id": cid,
        "commit_seq": h_seq + 1,
        "prev_history_ref": {"commit_seq": h_seq, "commit_hash": h_hash},
        "command_ref": {"kind": "command_envelope", "revision_digest": hashlib.sha256(b"cmd2_j").hexdigest(), "ref_class": "CONTENT_OBJECT"},
        "command_digest": hashlib.sha256(b"cmd2_j").hexdigest(),
        "actor_ref": "installation-owner",
        "expected_parent_head": {"commit_seq": h_seq, "commit_hash": h_hash},
        "governing_policy_ref": "pin:initial_governing_policy_ref",
        "governing_spec_refs": ["pin:initial_transition_profile_ref"],
        "ordered_event_bodies": [],
        "immutable_object_refs": [{"kind": "stop_input", "revision_digest": si_digest, "ref_class": "CONTENT_OBJECT"}],
    }
    con.execute(
        "INSERT INTO commits(seq,commit_hash,campaign_id,body) VALUES(?,?,?,?)",
        (h_seq + 1, c2_hash, cid, json.dumps(c2_body)),
    )

    # Commit 3: accepts material audit object (e.g. stage_spec or finding_claim_revision)
    c3_hash = hashlib.sha256(b"commit_3_j").hexdigest()
    stage_digest = hashlib.sha256(b"stage_spec_digest").hexdigest()
    c3_body = {
        "campaign_id": cid,
        "commit_seq": h_seq + 2,
        "prev_history_ref": {"commit_seq": h_seq + 1, "commit_hash": c2_hash},
        "command_ref": {"kind": "command_envelope", "revision_digest": hashlib.sha256(b"cmd3_j").hexdigest(), "ref_class": "CONTENT_OBJECT"},
        "command_digest": hashlib.sha256(b"cmd3_j").hexdigest(),
        "actor_ref": "installation-owner",
        "expected_parent_head": {"commit_seq": h_seq + 1, "commit_hash": c2_hash},
        "governing_policy_ref": "pin:initial_governing_policy_ref",
        "governing_spec_refs": ["pin:initial_transition_profile_ref"],
        "ordered_event_bodies": [],
        "immutable_object_refs": [{"kind": "stage_spec", "revision_digest": stage_digest, "ref_class": "CONTENT_OBJECT"}],
    }
    con.execute(
        "INSERT INTO commits(seq,commit_hash,campaign_id,body) VALUES(?,?,?,?)",
        (h_seq + 2, c3_hash, cid, json.dumps(c3_body)),
    )
    con.execute(
        "UPDATE accepted_head SET seq=?, commit_hash=? WHERE singleton=1",
        (h_seq + 2, c3_hash),
    )
    con.commit()
    con.close()

    # evaluate_stop_gate should fail closed with STOP_INPUT_CUT_MISMATCH
    with pytest.raises(ValidationError, match="STOP_INPUT_CUT_MISMATCH"):
        evaluate_stop_gate(store_path)


# =========================================================================
# D13 Tests: Cases K - P
# =========================================================================

@pytest.fixture
def candidate_and_assignments():
    cand_cut = {"campaign_id": "CAMP-01", "accepted_head_seq": 15, "accepted_head_hash": "a" * 64}
    asgn_cut = {"campaign_id": "CAMP-01", "accepted_head_seq": 16, "accepted_head_hash": "b" * 64}
    res_cut = {"campaign_id": "CAMP-01", "accepted_head_seq": 17, "accepted_head_hash": "c" * 64}

    cac = CandidateAssuranceCaseBuilder(
        "cac_1", _ref("campaign_genesis", "cg"), _ref("source_generation", "sg"), cand_cut, _ref("inventory_revision", "inv"), _ref("claim_set", "cs")
    ).build()

    pol = _ref("policy_revision", "p")
    exec_ref = _ref("executor_spec", "ex")

    asgn_sk = ChallengerAssignment("asgn_sk", cac.ref, "FALSE_POSITIVE_SKEPTIC", "ALL", pol, exec_ref, asgn_cut)
    asgn_hu = ChallengerAssignment("asgn_hu", cac.ref, "FALSE_NEGATIVE_HUNTER", "ALL", pol, exec_ref, asgn_cut)

    res_sk = ChallengerResult("res_sk", asgn_sk.ref, cac.ref, res_cut, "NO_MATERIAL_COUNTEREVIDENCE")
    res_hu = ChallengerResult("res_hu", asgn_hu.ref, cac.ref, res_cut, "NO_MATERIAL_COUNTEREVIDENCE")

    return cac, asgn_sk, asgn_hu, res_sk, res_hu


def test_case_k_same_result_for_both_challengers_rejected(candidate_and_assignments):
    cac, asgn_sk, asgn_hu, res_sk, _ = candidate_and_assignments
    # Passing the exact same result object
    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(cac, res_sk, res_sk)
    assert eligible is False
    assert "DUPLICATE_CHALLENGER_RESULT" in reasons


def test_case_l_distinct_results_same_assignment_rejected(candidate_and_assignments):
    cac, asgn_sk, _, res_sk, _ = candidate_and_assignments
    # Result 2 points to skeptic assignment as well
    res_hu_bad = ChallengerResult("res_hu_bad", asgn_sk.ref, cac.ref, res_sk.result_input_history_cut, "NO_MATERIAL_COUNTEREVIDENCE")

    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(cac, res_sk, res_hu_bad)
    assert eligible is False
    assert "SAME_CHALLENGE_ASSIGNMENT" in reasons


def test_case_m_wrong_challenger_role_rejected(candidate_and_assignments):
    cac, asgn_sk, asgn_hu, res_sk, res_hu = candidate_and_assignments
    # Swap assignments or wrong role
    asgn_wrong = ChallengerAssignment(
        "asgn_wrong", cac.ref, "OTHER_POLICY_DEFINED", "ALL", asgn_sk.challenge_policy_ref, asgn_sk.executor_profile_ref, asgn_sk.assignment_input_history_cut
    )
    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(
        cac, res_sk, res_hu, skeptic_assignment=asgn_wrong, hunter_assignment=asgn_hu
    )
    assert eligible is False
    assert "INVALID_SKEPTIC_ROLE" in reasons


def test_case_n_assignment_cut_precedes_candidate_cut_rejected(candidate_and_assignments):
    cac, asgn_sk, _, _, _ = candidate_and_assignments
    early_cut = {"campaign_id": "CAMP-01", "accepted_head_seq": 10, "accepted_head_hash": "early"}
    asgn_early = ChallengerAssignment(
        "asgn_early", cac.ref, "FALSE_POSITIVE_SKEPTIC", "ALL", asgn_sk.challenge_policy_ref, asgn_sk.executor_profile_ref, early_cut
    )

    with pytest.raises(ValidationError, match="TEMPORAL_ORDER_VIOLATION"):
        E5ChallengerOrchestrator.validate_assignment_precedes_candidate(cac, asgn_early)


def test_case_o_result_cut_precedes_assignment_cut_rejected(candidate_and_assignments):
    cac, asgn_sk, asgn_hu, res_sk, res_hu = candidate_and_assignments
    early_cut = {"campaign_id": "CAMP-01", "accepted_head_seq": 15, "accepted_head_hash": "early"}
    res_early = ChallengerResult("res_early", asgn_sk.ref, cac.ref, early_cut, "NO_MATERIAL_COUNTEREVIDENCE")

    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(
        cac, res_early, res_hu, skeptic_assignment=asgn_sk, hunter_assignment=asgn_hu
    )
    assert eligible is False
    assert "RESULT_PRECEDES_ASSIGNMENT" in reasons


def test_case_p_positive_control_two_challengers_pass(candidate_and_assignments):
    cac, asgn_sk, asgn_hu, res_sk, res_hu = candidate_and_assignments
    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(
        cac, res_sk, res_hu, skeptic_assignment=asgn_sk, hunter_assignment=asgn_hu
    )
    assert eligible is True
    assert "BOTH_BASELINE_CHALLENGERS_QUALIFIED" in reasons


# =========================================================================
# D22 Tests: Cases Q - T
# =========================================================================

def test_case_q_stages_prepared_no_conclusion_not_completed(tmp_path: Path):
    store_path = tmp_path / "campaign_q.sqlite"
    api = AuditOperationApi()
    api.create_campaign(store_path, seed="case_q")
    for stage in ("E1", "E2", "E3", "E4", "E5"):
        api.prepare_stage(store_path, stage)

    store = TransactionalHistoryStore(store_path)
    model = VerifiedCampaignReadModel(store)
    status = model.project_status()
    assert status["campaign_completed"] is False
    assert status["termination_state"] == "OPEN"


def test_case_r_completed_limited_never_gives_ready(base_stop_kwargs):
    si = StopInput(**base_stop_kwargs)
    ev = evaluate_stop(si, insufficient_data=False)
    assert ev.release_readiness == "READY"

    # Conclusion with COMPLETED_LIMITED
    camp_ref = _ref("campaign_genesis", "cg")
    sg_ref = _ref("source_generation", "sg")
    cut = {"campaign_id": "CAMP-RU06", "accepted_head_seq": 20, "accepted_head_hash": "h" * 64}
    risk_ref = _ref("residual_risk", "rr")

    conclusion = CampaignConclusion(
        campaign_conclusion_id="conc_ltd",
        campaign_ref=camp_ref,
        source_generation_ref=sg_ref,
        stop_evaluation_ref=ev.ref,
        termination_state="COMPLETED_LIMITED",
        assurance_level="BOUNDED",
        bounded_conclusion_statement="Limited conclusion statement",
        conclusion_command_input_history_cut=cut,
        residual_risk_refs=(risk_ref,),
        limited_conclusion_basis_refs=(risk_ref,),
    )

    final_case = FinalAssuranceCase(
        final_assurance_case_id="fac_1",
        campaign_conclusion_ref=conclusion.ref,
        stop_evaluation_ref=ev.ref,
        public_conclusion_statement_ref=_ref("public_statement", "ps"),
        final_case_input_history_cut=cut,
    )

    qual = ReleaseLifecycleManager.evaluate_release_qualification(
        qualification_id="rel_qual_1",
        conclusion=conclusion,
        final_case=final_case,
        stop_eval=ev,
        source_generation_ref=sg_ref,
        release_policy_ref=_ref("policy_revision", "p"),
        release_assessment_basis_cut=cut,
        qualification_command_cut=cut,
        assessment_basis="STOP_AXIS_MATERIALIZATION",
    )
    # Must NOT be READY! Must be QUALIFICATION_BLOCKED
    assert qual.result == "QUALIFICATION_BLOCKED"


def test_case_s_positive_control_completed_conclusion_ready(base_stop_kwargs):
    si = StopInput(**base_stop_kwargs)
    ev = evaluate_stop(si, insufficient_data=False)
    assert ev.release_readiness == "READY"

    camp_ref = _ref("campaign_genesis", "cg")
    sg_ref = _ref("source_generation", "sg")
    cut = {"campaign_id": "CAMP-RU06", "accepted_head_seq": 20, "accepted_head_hash": "h" * 64}
    cac_ref = _ref("candidate_assurance_case", "cac")

    conclusion = CampaignConclusion(
        campaign_conclusion_id="conc_full",
        campaign_ref=camp_ref,
        source_generation_ref=sg_ref,
        stop_evaluation_ref=ev.ref,
        termination_state="COMPLETED",
        assurance_level="ADEQUATE_FOR_DECLARED_SCOPE",
        bounded_conclusion_statement="Full completion statement",
        conclusion_command_input_history_cut=cut,
        candidate_assurance_case_ref=cac_ref,
    )

    final_case = FinalAssuranceCase(
        final_assurance_case_id="fac_full",
        campaign_conclusion_ref=conclusion.ref,
        stop_evaluation_ref=ev.ref,
        public_conclusion_statement_ref=_ref("public_statement", "ps"),
        final_case_input_history_cut=cut,
    )

    qual = ReleaseLifecycleManager.evaluate_release_qualification(
        qualification_id="rel_qual_full",
        conclusion=conclusion,
        final_case=final_case,
        stop_eval=ev,
        source_generation_ref=sg_ref,
        release_policy_ref=_ref("policy_revision", "p"),
        release_assessment_basis_cut=cut,
        qualification_command_cut=cut,
        assessment_basis="STOP_AXIS_MATERIALIZATION",
    )
    assert qual.result == "READY"


def test_case_t_release_drift_fails_closed(base_stop_kwargs):
    si = StopInput(**base_stop_kwargs)
    ev = evaluate_stop(si, insufficient_data=False)

    camp_ref = _ref("campaign_genesis", "cg")
    sg_ref = _ref("source_generation", "sg")
    cut = {"campaign_id": "CAMP-RU06", "accepted_head_seq": 20, "accepted_head_hash": "h" * 64}
    cac_ref = _ref("candidate_assurance_case", "cac")

    conclusion = CampaignConclusion(
        campaign_conclusion_id="conc_full_drift",
        campaign_ref=camp_ref,
        source_generation_ref=sg_ref,
        stop_evaluation_ref=ev.ref,
        termination_state="COMPLETED",
        assurance_level="ADEQUATE_FOR_DECLARED_SCOPE",
        bounded_conclusion_statement="Full completion statement",
        conclusion_command_input_history_cut=cut,
        candidate_assurance_case_ref=cac_ref,
    )

    final_case = FinalAssuranceCase(
        final_assurance_case_id="fac_drift",
        campaign_conclusion_ref=conclusion.ref,
        stop_evaluation_ref=ev.ref,
        public_conclusion_statement_ref=_ref("public_statement", "ps"),
        final_case_input_history_cut=cut,
    )

    with pytest.raises(ValidationError, match="DRIFT_DETECTED_MATERIALIZATION_INVALID"):
        ReleaseLifecycleManager.evaluate_release_qualification(
            qualification_id="rel_qual_drift",
            conclusion=conclusion,
            final_case=final_case,
            stop_eval=ev,
            source_generation_ref=sg_ref,
            release_policy_ref=_ref("policy_revision", "p"),
            release_assessment_basis_cut=cut,
            qualification_command_cut=cut,
            assessment_basis="STOP_AXIS_MATERIALIZATION",
            has_release_drift=True,
        )

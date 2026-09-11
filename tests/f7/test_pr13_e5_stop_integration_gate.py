"""E5 / STOP Integration Gate and Adversarial Proofs (PR-E5-13 / §105 / §21)."""
import pytest
from jsonschema import Draft202012Validator

from bdb_audit.attack.gate import E5StopGateVerdict, E5StopSyntheticBenchmark
from bdb_audit.attack.interaction_graph import FailureInteractionGraph, InteractionNode, InteractionEdge
from bdb_audit.attack.mutation import MutationCase, MutationResult, MutationEngine, ActivationProof
from bdb_audit.attack.calibration import CalibrationCase, CalibrationHarness
from bdb_audit.assurance.candidate_case import CandidateAssuranceCase, CandidateAssuranceCaseBuilder
from bdb_audit.assurance.challenger import ChallengerAssignment, ChallengerResult, E5ChallengerOrchestrator
from bdb_audit.assurance.residual_risk import ResidualRiskRecord, ResidualRiskRegister
from bdb_audit.assurance.conclusion import CampaignConclusion, FinalAssuranceCase
from bdb_audit.assurance.release import (
    ReleaseQualification,
    SuccessorCampaignGenesis,
    ReleaseLifecycleManager,
)
from bdb_audit.stop.evaluator import evaluate_stop, validate_intermediate_stop
from bdb_audit.stop.e6 import AdaptiveE6Generator
from bdb_audit.stop.models import StopInput, StopEvaluation
from bdb_audit.core.errors import ValidationError
from bdb_audit.schemas.foundation import executable_schema


def _ref(kind: str, digest_suffix: str, ref_class: str = "CONTENT_OR_PRIOR") -> dict:
    dig = (digest_suffix * 64)[:64]
    return {
        "kind": kind,
        "revision_digest": dig,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
    }


def test_e5_stop_synthetic_benchmark_all_pass():
    verdict = E5StopSyntheticBenchmark.run("v_synth_all_pass")
    assert verdict.is_all_pass() is True
    assert verdict.e5_stop_integration_gate == "PASS"
    assert verdict.no_assurance_case_stop_cycle == "PASS"
    assert verdict.unknown_blocked_cannot_become_pass == "PASS"
    assert verdict.invalidation_reopens_dependent_stop_inputs == "PASS"
    assert verdict.e6_preserves_or_strengthens_obligations == "PASS"


# =============================================================================
# Adversarial Proofs (§21)
# =============================================================================

def test_adv_interaction_explosion_boundedness():
    cut = {"campaign_id": "CAMP", "commit_seq": 1, "commit_hash": "a" * 64}
    graph = FailureInteractionGraph(cut, max_interaction_order=3, max_combinations_bound=5)
    prov = _ref("stage_run", "sr")
    for i in range(10):
        graph.add_node(InteractionNode(f"n_{i}", "FAILURE_MODE", prov, cut, (_ref("obs", "o"),), cut))
    combos = graph.generate_candidate_combinations(2)
    assert len(combos) == 5  # strictly bounded!


def test_adv_unsupported_interaction_edge():
    cut = {"campaign_id": "CAMP", "commit_seq": 1, "commit_hash": "a" * 64}
    prov = _ref("stage_run", "sr")
    with pytest.raises(ValidationError, match="UNSUPPORTED_INTERACTION_EDGE"):
        InteractionEdge("e_bad", ("n1",), "n2", "CASCADE", (), prov, cut)


def test_adv_mutation_without_activation_and_fake_killed():
    with pytest.raises(ValidationError, match="MUTANT_KILLED_WITHOUT_ACTIVATION"):
        MutationResult("r", {"id": "m"}, "IMPLEMENTATION_MUTATION", "MUTANT_KILLED", activation_proven=False)


def test_adv_oracle_mutation_without_defective_control():
    case = MutationCase(
        "m_orc", "r1", "ORACLE_MUTATION", _ref("cl", "c"), "loc:1",
        {"c": 1}, "det", _ref("p", "p"), _ref("n", "n"), _ref("cl", "cl"),
        known_defective_target_ref=None,
    )
    proof = ActivationProof("p", "loc:1", True)
    res = MutationEngine.evaluate_oracle_mutation("res", case, proof, False, False, True, False)
    assert res.outcome == "INVALID_MUTATION"


def test_adv_calibration_unseeded_finding_not_false_positive():
    harness = CalibrationHarness()
    harness.register_case(CalibrationCase("c_unseeded", "CALIBRATION", "UNSEEDED_REAL_OBSERVATION", _ref("t", "t"), ground_truth_defective=None))
    eval_res = harness.evaluate("ev", "CALIBRATION", {"c_unseeded": True})
    assert eval_res.false_positives == 0
    assert eval_res.unseeded_observations_flagged == 1


def test_adv_challenger_before_candidate_and_different_revisions():
    cand_cut = {"campaign_id": "CAMP", "commit_seq": 15, "commit_hash": "a" * 64}
    early_cut = {"campaign_id": "CAMP", "commit_seq": 10, "commit_hash": "e" * 64}
    cac = CandidateAssuranceCaseBuilder("cac1", _ref("cg", "1"), _ref("sg", "1"), cand_cut, _ref("inv", "1"), _ref("cs", "1")).build()

    asgn = ChallengerAssignment("a1", cac.ref, "FALSE_POSITIVE_SKEPTIC", "ALL", _ref("p", "1"), _ref("e", "1"), early_cut)
    with pytest.raises(ValidationError, match="TEMPORAL_ORDER_VIOLATION"):
        E5ChallengerOrchestrator.validate_assignment_precedes_candidate(cac, asgn)

    # Different candidate revisions
    r1 = ChallengerResult("r1", _ref("a", "1"), cac.ref, {"commit_seq": 16}, "NO_MATERIAL_COUNTEREVIDENCE")
    other_ref = dict(cac.ref)
    other_ref["revision_digest"] = "different" * 4 + "0" * 32
    r2 = ChallengerResult("r2", _ref("a", "1"), other_ref, {"commit_seq": 16}, "NO_MATERIAL_COUNTEREVIDENCE")

    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(cac, r1, r2)
    assert eligible is False
    assert "CHALLENGERS_REFERENCE_DIFFERENT_CANDIDATE_REVISIONS" in reasons


def test_adv_candidate_revision_changed_invalidates_both():
    cand_cut = {"campaign_id": "CAMP", "commit_seq": 15, "commit_hash": "a" * 64}
    cac = CandidateAssuranceCaseBuilder("cac1", _ref("cg", "1"), _ref("sg", "1"), cand_cut, _ref("inv", "1"), _ref("cs", "1")).build()
    stale_ref = {"kind": "candidate_assurance_case", "revision_digest": "stale" * 12 + "0000"}
    r1 = ChallengerResult("r1", _ref("a", "1"), stale_ref, {"commit_seq": 16}, "NO_MATERIAL_COUNTEREVIDENCE")
    r2 = ChallengerResult("r2", _ref("a", "1"), stale_ref, {"commit_seq": 16}, "NO_MATERIAL_COUNTEREVIDENCE")

    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(cac, r1, r2)
    assert eligible is False
    assert "CHALLENGER_RESULTS_INVALIDATED_BY_CANDIDATE_CHANGE" in reasons


def test_adv_stop_unknown_and_blocked_cannot_become_pass():
    cut = {"campaign_id": "CAMP", "commit_seq": 18, "commit_hash": "e" * 64}
    si_unknown = StopInput(
        campaign_id="CAMP", source_generation_ref=_ref("sg", "1"), input_history_cut=cut,
        evaluation_context="FINAL_POST_E5", governing_policy_ref=_ref("p", "1"), policy_spec_refs=[_ref("sp", "1")],
        evaluator_revision_ref=_ref("sp", "1"), required_stage_set_ref=_ref("st", "1"),
        required_stage_spec_refs=[_ref("sp", "1")], completed_stage_refs=[_ref("sp", "1")],
        pending_required_stage_refs=[], stop_input_snapshot_ref=_ref("sn", "1"), inventory_revision_ref=_ref("inv", "1"),
        mandatory_obligation_refs=[], current_obligation_qualification_refs=[], evidence_invalidation_refs=[],
        contradiction_refs=[], residual_risk_refs=[], evidence_invalidation_state={"invalidated_count": 0},
        release_policy_ref=_ref("p", "1"), effort_profile_ref=_ref("eff", "1"), effort_results_ref={"r": 1},
        unknown_blocked_summary={"unknown_surfaces_count": 1, "is_blocked": False},
        candidate_assurance_case_ref=_ref("cac", "1"), challenger_refs=[_ref("cr", "1"), _ref("cr", "2")],
    )
    ev_unknown = evaluate_stop(si_unknown)
    assert ev_unknown.continuation_decision != "PASS"
    assert ev_unknown.continuation_decision == "BLOCKED"

    si_blocked = StopInput(
        campaign_id="CAMP", source_generation_ref=_ref("sg", "1"), input_history_cut=cut,
        evaluation_context="FINAL_POST_E5", governing_policy_ref=_ref("p", "1"), policy_spec_refs=[_ref("sp", "1")],
        evaluator_revision_ref=_ref("sp", "1"), required_stage_set_ref=_ref("st", "1"),
        required_stage_spec_refs=[_ref("sp", "1")], completed_stage_refs=[_ref("sp", "1")],
        pending_required_stage_refs=[], stop_input_snapshot_ref=_ref("sn", "1"), inventory_revision_ref=_ref("inv", "1"),
        mandatory_obligation_refs=[], current_obligation_qualification_refs=[], evidence_invalidation_refs=[],
        contradiction_refs=[], residual_risk_refs=[], evidence_invalidation_state={"invalidated_count": 0},
        release_policy_ref=_ref("p", "1"), effort_profile_ref=_ref("eff", "1"), effort_results_ref={"r": 1},
        unknown_blocked_summary={"unknown_surfaces_count": 0, "is_blocked": True},
        candidate_assurance_case_ref=_ref("cac", "1"), challenger_refs=[_ref("cr", "1"), _ref("cr", "2")],
    )
    ev_blocked = evaluate_stop(si_blocked)
    assert ev_blocked.continuation_decision == "BLOCKED"


def test_adv_e6_weakens_or_rewrites_isolation_rejected():
    cut = {"campaign_id": "CAMP", "commit_seq": 18, "commit_hash": "e" * 64}
    si = StopInput(
        campaign_id="CAMP", source_generation_ref=_ref("sg", "1"), input_history_cut=cut,
        evaluation_context="FINAL_POST_E5", governing_policy_ref=_ref("p", "1"), policy_spec_refs=[_ref("sp", "1")],
        evaluator_revision_ref=_ref("sp", "1"), required_stage_set_ref=_ref("st", "1"),
        required_stage_spec_refs=[_ref("sp", "1")], completed_stage_refs=[_ref("sp", "1")],
        pending_required_stage_refs=[], stop_input_snapshot_ref=_ref("sn", "1"), inventory_revision_ref=_ref("inv", "1"),
        mandatory_obligation_refs=[_ref("coverage_obligation", "ob1")], current_obligation_qualification_refs=[],
        evidence_invalidation_refs=[], contradiction_refs=[], residual_risk_refs=[], evidence_invalidation_state={"invalidated_count": 0},
        release_policy_ref=_ref("p", "1"), effort_profile_ref=_ref("eff", "1"), effort_results_ref={"r": 1},
        unknown_blocked_summary={"unknown_surfaces_count": 0, "is_blocked": False},
        candidate_assurance_case_ref=_ref("cac", "1"), challenger_refs=[_ref("cr", "1"), _ref("cr", "2")],
    )
    ev_e6 = StopEvaluation(stop_input_ref=si.ref, continuation_decision="E6_REQUIRED", assurance_level="BOUNDED", release_readiness="QUALIFICATION_BLOCKED", reason_codes=("E6",))

    # Dropping obligations -> rejected
    with pytest.raises(ValidationError, match="DENOMINATOR_MANIPULATION_FORBIDDEN"):
        AdaptiveE6Generator.generate_e6_spec("e6_bad", ev_e6, si, _ref("tp", "1"), {"isolation_level": "STRICT"}, attempted_dropped_obligation_digests={(_ref("coverage_obligation", "ob1"))["revision_digest"]})

    # Weakening isolation -> rejected
    with pytest.raises(ValidationError, match="ISOLATION_REWRITE_FORBIDDEN"):
        AdaptiveE6Generator.generate_e6_spec("e6_bad2", ev_e6, si, _ref("tp", "1"), {"isolation_level": "STRICT"}, proposed_isolation_profile_ref={"isolation_level": "RELAXED"})


def test_adv_competing_successor_branches_without_decision():
    concl_ref = _ref("campaign_conclusion", "concl")
    succ1 = SuccessorCampaignGenesis("camp_A", _ref("cg", "1"), concl_ref, _ref("trig", "1"), _ref("sg", "1"), {"seq": 1}, _ref("p", "1"), _ref("p", "1"), (_ref("sp", "1"),))
    succ2 = SuccessorCampaignGenesis("camp_B", _ref("cg", "1"), concl_ref, _ref("trig", "1"), _ref("sg", "1"), {"seq": 1}, _ref("p", "1"), _ref("p", "1"), (_ref("sp", "1"),))

    with pytest.raises(ValidationError, match="ASSURANCE_SUCCESSOR_CONFLICT"):
        ReleaseLifecycleManager.resolve_successor_branches(concl_ref, [succ1, succ2], selection_decision=None)

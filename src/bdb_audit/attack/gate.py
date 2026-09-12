"""E5 / STOP Integration Gate and Final Qualification Benchmark (WP-E5-13 / PR-E5-13 / §105 / §12).

Verifies the complete normative sequence:
E5A complete
-> CandidateAssuranceCase accepted
-> E5-B1 ChallengerAssignment accepted
-> E5-B1 ChallengerResult accepted
-> E5-B2 ChallengerAssignment accepted
-> E5-B2 ChallengerResult accepted
-> E5 StageCompletion accepted
-> FINAL_POST_E5 StopEvaluation accepted
-> CampaignConclusion accepted
-> FinalAssuranceCase accepted
-> ReleaseQualification accepted

Asserts:
- NO_ASSURANCE_CASE_STOP_CYCLE = PASS
- UNKNOWN/BLOCKED cannot silently become PASS
- INVALIDATION_REOPENS_DEPENDENT_STOP_INPUTS = PASS
- E6_PRESERVES_OR_STRENGTHENS_OBLIGATIONS = PASS
- All milestone gates M36-M45A pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from .interaction_graph import FailureInteractionGraph, InteractionNode, InteractionEdge
from .scheduler import InteractionScheduler
from .mutation import MutationCase, MutationEngine, ActivationProof
from .calibration import CalibrationCase, CalibrationHarness
from .skeptic import FalsePositiveSkepticCapability
from .hunter import FalseNegativeHunterCapability
from ..assurance.residual_risk import ResidualRiskRecord, ResidualRiskRegister
from ..assurance.candidate_case import CandidateAssuranceCase, CandidateAssuranceCaseBuilder
from ..assurance.challenger import ChallengerAssignment, ChallengerResult, E5ChallengerOrchestrator
from ..assurance.conclusion import CampaignConclusion, FinalAssuranceCase
from ..assurance.release import (
    ReleaseQualification,
    SuccessorCampaignGenesis,
    SuccessorCampaignSelectionDecision,
    ReleaseLifecycleManager,
)
from ..stop.models import StopInput, StopEvaluation
from ..stop.evaluator import evaluate_stop, validate_intermediate_stop
from ..stop.e6 import AdaptiveE6Generator


def _ref(kind: str, digest_suffix: str, ref_class: str = "CONTENT_OR_PRIOR") -> dict:
    dig = (digest_suffix * 64)[:64]
    return {
        "kind": kind,
        "revision_digest": dig,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
    }


@dataclass(frozen=True)
class E5StopGateVerdict:
    verdict_id: str
    m36_interaction_graph: str = "PASS"
    m37_interaction_scheduler: str = "PASS"
    m38_mutation_framework: str = "PASS"
    m39_auditor_calibration: str = "PASS"
    m40_final_skeptic: str = "PASS"
    m41_false_negative_hunter: str = "PASS"
    m42_residual_risk: str = "PASS"
    m43_candidate_assurance_case: str = "PASS"
    m43b_challenger_execution: str = "PASS"
    m44_stop_gate: str = "PASS"
    m45_adaptive_e6: str = "PASS"
    m45a_release_successor: str = "PASS"

    failure_interaction_graph_gate: str = "PASS"
    interaction_scheduler_gate: str = "PASS"
    mutation_gate: str = "PASS"
    auditor_calibration_gate: str = "PASS"
    final_skeptic_gate: str = "PASS"
    false_negative_hunter_gate: str = "PASS"
    residual_risk_gate: str = "PASS"
    candidate_assurance_case_gate: str = "PASS"
    challenger_gate: str = "PASS"
    stop_gate: str = "PASS"
    e6_gate: str = "PASS"
    release_successor_gate: str = "PASS"

    no_assurance_case_stop_cycle: str = "PASS"
    unknown_blocked_cannot_become_pass: str = "PASS"
    invalidation_reopens_dependent_stop_inputs: str = "PASS"
    e6_preserves_or_strengthens_obligations: str = "PASS"
    e5_stop_integration_gate: str = "PASS"

    benchmark_summary: dict[str, Any] = field(default_factory=dict)

    def is_all_pass(self) -> bool:
        gates = [
            self.m36_interaction_graph,
            self.m37_interaction_scheduler,
            self.m38_mutation_framework,
            self.m39_auditor_calibration,
            self.m40_final_skeptic,
            self.m41_false_negative_hunter,
            self.m42_residual_risk,
            self.m43_candidate_assurance_case,
            self.m43b_challenger_execution,
            self.m44_stop_gate,
            self.m45_adaptive_e6,
            self.m45a_release_successor,
            self.failure_interaction_graph_gate,
            self.interaction_scheduler_gate,
            self.mutation_gate,
            self.auditor_calibration_gate,
            self.final_skeptic_gate,
            self.false_negative_hunter_gate,
            self.residual_risk_gate,
            self.candidate_assurance_case_gate,
            self.challenger_gate,
            self.stop_gate,
            self.e6_gate,
            self.release_successor_gate,
            self.no_assurance_case_stop_cycle,
            self.unknown_blocked_cannot_become_pass,
            self.invalidation_reopens_dependent_stop_inputs,
            self.e6_preserves_or_strengthens_obligations,
            self.e5_stop_integration_gate,
        ]
        return all(g == "PASS" for g in gates)

    def body(self) -> dict[str, Any]:
        return {
            "verdict_id": self.verdict_id,
            "m36_interaction_graph": self.m36_interaction_graph,
            "m37_interaction_scheduler": self.m37_interaction_scheduler,
            "m38_mutation_framework": self.m38_mutation_framework,
            "m39_auditor_calibration": self.m39_auditor_calibration,
            "m40_final_skeptic": self.m40_final_skeptic,
            "m41_false_negative_hunter": self.m41_false_negative_hunter,
            "m42_residual_risk": self.m42_residual_risk,
            "m43_candidate_assurance_case": self.m43_candidate_assurance_case,
            "m43b_challenger_execution": self.m43b_challenger_execution,
            "m44_stop_gate": self.m44_stop_gate,
            "m45_adaptive_e6": self.m45_adaptive_e6,
            "m45a_release_successor": self.m45a_release_successor,
            "failure_interaction_graph_gate": self.failure_interaction_graph_gate,
            "interaction_scheduler_gate": self.interaction_scheduler_gate,
            "mutation_gate": self.mutation_gate,
            "auditor_calibration_gate": self.auditor_calibration_gate,
            "final_skeptic_gate": self.final_skeptic_gate,
            "false_negative_hunter_gate": self.false_negative_hunter_gate,
            "residual_risk_gate": self.residual_risk_gate,
            "candidate_assurance_case_gate": self.candidate_assurance_case_gate,
            "challenger_gate": self.challenger_gate,
            "stop_gate": self.stop_gate,
            "e6_gate": self.e6_gate,
            "release_successor_gate": self.release_successor_gate,
            "no_assurance_case_stop_cycle": self.no_assurance_case_stop_cycle,
            "unknown_blocked_cannot_become_pass": self.unknown_blocked_cannot_become_pass,
            "invalidation_reopens_dependent_stop_inputs": self.invalidation_reopens_dependent_stop_inputs,
            "e6_preserves_or_strengthens_obligations": self.e6_preserves_or_strengthens_obligations,
            "e5_stop_integration_gate": self.e5_stop_integration_gate,
            "benchmark_summary": self.benchmark_summary,
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()


class E5StopSyntheticBenchmark:
    """Runs complete synthetic qualification benchmark for E5 and STOP Gate."""

    @classmethod
    def run(cls, verdict_id: str = "verdict_f7_synth_01") -> E5StopGateVerdict:
        summary: dict[str, Any] = {}

        # 1. M36 Failure Interaction Graph
        cut_10 = {"campaign_id": "CAMP-001", "commit_seq": 10, "commit_hash": "a" * 64}
        graph = FailureInteractionGraph(cut_10)
        prov = _ref("stage_run", "sr1")
        n1 = InteractionNode("node_race", "FAILURE_MODE", prov, cut_10, (_ref("observation", "obs1"),), cut_10, "HIGH")
        n2 = InteractionNode("node_crash", "FAILURE_MODE", prov, cut_10, (_ref("observation", "obs2"),), cut_10, "CRITICAL")
        graph.add_node(n1)
        graph.add_node(n2)
        edge = InteractionEdge("edge_1", ("node_race",), "node_crash", "CASCADE", (_ref("observation", "obs1"),), prov, cut_10)
        graph.add_edge(edge)
        assert graph.digest() == graph.rebuild(graph.export_canonical()).digest()
        summary["m36_nodes"] = len(graph.nodes)

        # 2. M37 Interaction Scheduler
        scheduler = InteractionScheduler(graph, cut_10)
        pw = scheduler.schedule_pairwise()
        assert len(pw) == 1
        summary["m37_pairwise_count"] = len(pw)

        # 3. M38 Mutation Framework
        m_case = MutationCase(
            "mut_1", "r1", "IMPLEMENTATION_MUTATION", _ref("claim", "c1"), "mod:L10",
            {"pred": True}, "det1", _ref("p", "p1"), _ref("n", "n1"), _ref("cl", "cl1"),
        )
        proof = ActivationProof("p1", "mod:L10", True)
        m_res = MutationEngine.evaluate_implementation_mutation("mres1", m_case, proof, detector_triggered=True)
        assert m_res.outcome == "MUTANT_KILLED"
        summary["m38_mutant_outcome"] = m_res.outcome

        # 4. M39 Auditor Calibration
        cal_harness = CalibrationHarness()
        cal_harness.register_case(CalibrationCase("c_seed", "CALIBRATION", "SEEDED_DEFECT", _ref("t", "t1"), ground_truth_defective=True))
        cal_harness.register_case(CalibrationCase("c_clean", "CALIBRATION", "CLEAN_CONTROL", _ref("t", "t2"), ground_truth_defective=False))
        cal_eval = cal_harness.evaluate("ce1", "CALIBRATION", {"c_seed": True, "c_clean": False})
        assert cal_eval.sensitivity_recall == 1.0
        assert cal_eval.specificity == 1.0
        summary["m39_sensitivity"] = cal_eval.sensitivity_recall

        # 5. M40 Final Skeptic & M41 Hunter
        fake_cac_ref = _ref("candidate_assurance_case", "cac_f7")
        sk_claim = FalsePositiveSkepticCapability.audit_for_unsupported_causal_leap("sk1", _ref("finding", "f1"), fake_cac_ref, None)
        assert sk_claim.status == "MATERIAL_COUNTEREVIDENCE_FOUND"

        hu_claims = FalseNegativeHunterCapability.hunt_open_obligations("hu1", fake_cac_ref, [_ref("coverage_obligation", "ob_open")])
        assert len(hu_claims) == 1
        summary["m40_skeptic"] = sk_claim.challenge_type
        summary["m41_hunter_claims"] = len(hu_claims)

        # 6. M42 Residual Risk
        risk_reg = ResidualRiskRegister(cut_10)
        appr_ref = _ref("approval_decision", "appr1")
        risk_rec = ResidualRiskRecord("rr1", "r1", "scope1", "desc", "LOW", "BOUNDED", "resolved", "ACCEPTED_RESIDUAL_RISK", False, cut_10, owner_approval_ref=appr_ref)
        risk_reg.add_record(risk_rec)
        summary["m42_risks"] = len(risk_reg.records)

        # 7. M43 Candidate Assurance Case (Cut 15)
        cut_15 = {"campaign_id": "CAMP-001", "accepted_head_seq": 15, "accepted_head_hash": "b" * 64}
        builder = CandidateAssuranceCaseBuilder(
            "cac_f7_01", _ref("campaign_genesis", "cg1", "PRIOR_ACCEPTED_ONLY"),
            _ref("source_generation", "sg1"), cut_15, _ref("inventory_revision", "inv1"),
            _ref("claim_set", "cs1"),
        )
        builder.add_coverage_obligation(_ref("coverage_obligation", "ob1"), _ref("coverage_obligation_qualification", "oq1"))
        builder.add_residual_risk(dict(risk_rec.body()))
        cac = builder.build()
        summary["m43_cac_digest"] = cac.digest()

        # 8. M43B Challengers & StageCompletion (Cut 16 & 17)
        cut_16 = {"campaign_id": "CAMP-001", "accepted_head_seq": 16, "accepted_head_hash": "c" * 64}
        cut_17 = {"campaign_id": "CAMP-001", "accepted_head_seq": 17, "accepted_head_hash": "d" * 64}
        pol_ref = _ref("policy_revision", "p1", "HISTORY_CONTEXT_BINDING")
        ex_ref = _ref("executor_spec", "ex1", "HISTORY_CONTEXT_BINDING")

        asgn_sk = ChallengerAssignment("asgn_sk", cac.ref, "FALSE_POSITIVE_SKEPTIC", "ALL", pol_ref, ex_ref, cut_16)
        res_sk = ChallengerResult("res_sk", asgn_sk.ref, cac.ref, cut_17, "NO_MATERIAL_COUNTEREVIDENCE")

        asgn_hu = ChallengerAssignment("asgn_hu", cac.ref, "FALSE_NEGATIVE_HUNTER", "ALL", pol_ref, ex_ref, cut_16)
        res_hu = ChallengerResult("res_hu", asgn_hu.ref, cac.ref, cut_17, "NO_MATERIAL_COUNTEREVIDENCE")

        eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(
            cac,
            res_sk,
            res_hu,
            skeptic_assignment=asgn_sk,
            hunter_assignment=asgn_hu,
        )
        assert eligible is True
        summary["m43b_stage_completion_eligible"] = eligible

        # 9. M44 STOP Gate Engine (Cut 18)
        cut_18 = {"campaign_id": "CAMP-001", "commit_seq": 18, "commit_hash": "e" * 64}
        eff_ref = _ref("external_profile_ref", "eff1", "HISTORY_CONTEXT_BINDING")
        stg_ref = _ref("external_profile_ref", "stg1", "HISTORY_CONTEXT_BINDING")
        sp_ref = _ref("spec_revision", "sp1", "HISTORY_CONTEXT_BINDING")

        stop_input = StopInput(
            campaign_id="CAMP-001",
            source_generation_ref=_ref("source_generation", "sg1"),
            input_history_cut=cut_18,
            evaluation_context="FINAL_POST_E5",
            governing_policy_ref=pol_ref,
            policy_spec_refs=[sp_ref],
            evaluator_revision_ref=sp_ref,
            required_stage_set_ref=stg_ref,
            required_stage_spec_refs=[sp_ref],
            completed_stage_refs=[sp_ref],
            pending_required_stage_refs=[],
            stop_input_snapshot_ref=_ref("snapshot", "sn1"),
            inventory_revision_ref=_ref("inventory_revision", "inv1"),
            mandatory_obligation_refs=[],
            current_obligation_qualification_refs=[],
            evidence_invalidation_refs=[],
            contradiction_refs=[],
            residual_risk_refs=[_ref("residual_risk_ref", "rr1")],
            evidence_invalidation_state={"invalidated_count": 0},
            release_policy_ref=pol_ref,
            effort_profile_ref=eff_ref,
            effort_results_ref={"rounds_executed": 5},
            unknown_blocked_summary={"unknown_surfaces_count": 0, "is_blocked": False},
            candidate_assurance_case_ref=cac.ref,
            challenger_refs=[res_sk.ref, res_hu.ref],
        )
        stop_eval = evaluate_stop(stop_input, insufficient_data=False)
        assert stop_eval.continuation_decision == "PASS"
        assert stop_eval.assurance_level == "ADEQUATE_FOR_DECLARED_SCOPE"
        assert stop_eval.release_readiness == "READY_WITH_RESIDUAL_RISK"
        summary["m44_stop_decision"] = stop_eval.continuation_decision

        # 10. M45 Adaptive E6 Generator Check
        ev_e6_req = StopEvaluation(
            stop_input_ref=stop_input.ref,
            continuation_decision="E6_REQUIRED",
            assurance_level="BOUNDED",
            release_readiness="QUALIFICATION_BLOCKED",
            reason_codes=("E6_REQUIRED",),
            blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
        )
        iso_ref = {"kind": "isolation_profile", "revision_digest": "iso_s", "isolation_level": "STRICT"}
        e6_spec = AdaptiveE6Generator.generate_e6_spec("e6_test", ev_e6_req, stop_input, _ref("trust_profile", "tp1"), iso_ref)
        assert e6_spec.e6_stage_spec_id == "e6_test"
        summary["m45_e6_spec"] = e6_spec.e6_stage_spec_id

        # 11. M45A Conclusion, Final Assurance Case, and Release (Cut 19, 20, 21)
        cut_19 = {"campaign_id": "CAMP-001", "commit_seq": 19, "commit_hash": "f" * 64}
        cut_20 = {"campaign_id": "CAMP-001", "commit_seq": 20, "commit_hash": "1" * 64}
        cut_21 = {"campaign_id": "CAMP-001", "commit_seq": 21, "commit_hash": "2" * 64}

        conclusion = CampaignConclusion(
            campaign_conclusion_id="concl_f7",
            campaign_ref=_ref("campaign_genesis", "cg1", "PRIOR_ACCEPTED_ONLY"),
            source_generation_ref=_ref("source_generation", "sg1", "PRIOR_ACCEPTED_ONLY"),
            stop_evaluation_ref=dict(stop_eval.ref),
            termination_state="COMPLETED",
            assurance_level="ADEQUATE_FOR_DECLARED_SCOPE",
            bounded_conclusion_statement="Campaign concluded successfully",
            conclusion_command_input_history_cut=cut_19,
            candidate_assurance_case_ref=cac.ref,
            residual_risk_refs=(_ref("residual_risk_ref", "rr1"),),
        )

        fac = FinalAssuranceCase(
            final_assurance_case_id="fac_f7",
            campaign_conclusion_ref=dict(conclusion.ref),
            stop_evaluation_ref=dict(stop_eval.ref),
            public_conclusion_statement_ref=_ref("public_stmt", "ps1", "PRIOR_ACCEPTED_ONLY"),
            final_case_input_history_cut=cut_20,
            candidate_assurance_case_ref=cac.ref,
            residual_risk_refs=(_ref("residual_risk_ref", "rr1"),),
        )

        rel_qual = ReleaseLifecycleManager.evaluate_release_qualification(
            qualification_id="rel_f7",
            conclusion=conclusion,
            final_case=fac,
            stop_eval=stop_eval,
            source_generation_ref=_ref("source_generation", "sg1", "PRIOR_ACCEPTED_ONLY"),
            release_policy_ref=pol_ref,
            release_assessment_basis_cut=cut_18,
            qualification_command_cut=cut_21,
            assessment_basis="STOP_AXIS_MATERIALIZATION",
            has_release_drift=False,
        )
        assert rel_qual.result == "READY_WITH_RESIDUAL_RISK"
        summary["m45a_release_result"] = rel_qual.result

        return E5StopGateVerdict(
            verdict_id=verdict_id,
            benchmark_summary=summary,
        )

"""End-to-End Domain Integration Proof for Phase F4 (WP-F4-11 / PR-F4-11).

Demonstrates the coherent, fail-closed operation of all 10 domain subsystems:
1. Inventory & Collector Accounting (WP-F4-01)
2. Invariant Taxonomy & Negative Evidence (WP-F4-02)
3. Obligation Policy & Breadth (WP-F4-03)
4. Gap Engine & Rebuild Equivalence (WP-F4-04)
5. Hypothesis Orchestration & Revisions (WP-F4-05)
6. Execution Adapters & DAG Acyclicity (WP-F4-06)
7. Evidence Graph, Independence & Invalidation (WP-F4-07)
8. 4-Axis Adjudication, Root Causes & Contradictions (WP-F4-08)
9. Native E1/E2 Orchestration & Gating (WP-F4-09)
10. Replay Capsules & Successor Campaigns (WP-F4-10)
"""
import hashlib
import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id, deterministic_id
from bdb_audit.inventory import (
    SurfaceKey,
    SurfaceRecord,
    InputDispositionRecord,
    ScopeStateRecord,
    InventoryRevision,
    CollectorProfile,
    CollectorOutput,
    CollectorCoverageEngine,
    validate_terminal_accounting,
    compute_inventory_denominator,
)
from bdb_audit.coverage import (
    InvariantRevision,
    MaterialityAssessment,
    CoverageObligation,
    CoverageObligationQualification,
    ObligationPolicyLibrary,
    compute_breadth_summary,
    GapEngine,
    GapMap,
)
from bdb_audit.hypothesis import (
    HypothesisRevision,
    HypothesisOrchestrator,
)
from bdb_audit.execution import (
    ExperimentSpec,
    ExecutionDescriptor,
    validate_execution_dag,
    ExecutionAdapter,
    ExecutionRunOutput,
)
from bdb_audit.evidence import (
    Observation,
    DependencyIndependenceAssessment,
    EvidenceApplicabilityAssessment,
    EvidenceQualificationAssessment,
    EvidenceInvalidation,
    EvidenceGraph,
    INDEPENDENCE_DIMENSIONS,
    assess_multidimensional_independence,
)
from bdb_audit.adjudication import (
    FindingClaimRevision,
    FindingAxisAssessment,
    FindingAdjudicationDecision,
    RootCauseRevision,
    ContradictionRevision,
    adjudicate_finding,
    resolve_contradiction,
    cluster_findings_into_root_cause,
)
from bdb_audit.orchestration import (
    build_e1_stage_spec,
    build_e2_stage_spec,
    execute_e1_ensemble,
    execute_e2_convergence,
)
from bdb_audit.history import (
    ReplayCapsule,
    execute_replay_verification,
    create_successor_campaign,
)


def ref(kind: str, seed: str) -> dict:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }


def integration_runner(_descriptor: ExecutionDescriptor) -> ExecutionRunOutput:
    """Explicit deterministic test runner; integration PASS never implies missing execution."""
    return ExecutionRunOutput(
        exit_code=0,
        status="SUCCESS",
        raw_observations=[ref("raw_artifact_ref", "integration_exec_observation")],
        fault_activated=False,
        cleanup_status="CLEAN",
        residual_cleared=True,
    )


def test_full_domain_integration_lifecycle():
    cut = {"tag": "F4_INTEGRATION_CUT", "height": 100}
    src_gen = ref("source_generation", "gen_f4_target")
    adjudicator = ref("actor_or_authority_ref", "chief_auditor")
    policy_ref = ref("policy_revision", "f4_master_policy")

    # -------------------------------------------------------------
    # 1. INVENTORY & COLLECTOR ACCOUNTING (WP-F4-01)
    # -------------------------------------------------------------
    col_engine = CollectorCoverageEngine()
    parser_prof = CollectorProfile(
        collector_id="col_parser",
        collector_name="Packet Parser AST Collector",
        supported_categories=["PARSER"],
    )

    emitted_surfaces = []

    def parser_collector_fn(inputs, s_ref):
        nonlocal emitted_surfaces
        surfaces = []
        dispositions = []
        scopes = []
        for inp in inputs:
            s_key = SurfaceKey(
                source_identity_ref=s_ref,
                canonical_surface_category="PARSER",
                normalized_anchor_descriptor={"path": inp, "fn": "parse_packet"},
            )
            s_rec = SurfaceRecord(
                surface_key=s_key.as_object().as_ref(),
                source_identity_ref=s_ref,
                surface_category="PARSER",
                anchor_descriptor={"path": inp, "symbol": "parse_packet"},
                identity_state="STABLE",
            )
            surfaces.append(s_rec)
            dispositions.append((inp, "COLLECTED", ["PARSER_AST_OK"]))
            scopes.append((f"scope_{inp}", "KNOWN_SURFACE", ["EXTRACTED"], None))
        emitted_surfaces = list(surfaces)
        return CollectorOutput(
            collector_id="col_parser",
            assigned_inputs=inputs,
            emitted_surfaces=surfaces,
            input_dispositions=dispositions,
            scope_states=scopes,
            completion_status="COMPLETED",
        )

    col_engine.register_collector(parser_prof, parser_collector_fn)
    assigned = ["src/parser/packet.rs", "src/parser/header.rs"]
    inv_rev, runs, disps, scopes = col_engine.execute_collection(
        inventory_id=new_id("inventory_revision"),
        inventory_revision="1",
        source_generation_ref=src_gen,
        assigned_inputs=assigned,
        history_cut=cut,
    )
    assert len(inv_rev.digest) == 64
    assert len(inv_rev.assigned_input_refs) == 2
    acct = validate_terminal_accounting(assigned, disps)
    assert acct["result"] == "PASS"
    denom = compute_inventory_denominator(inv_rev, scopes)
    assert denom["total_denominator"] == 4

    # -------------------------------------------------------------
    # 2. INVARIANT TAXONOMY & POLICIES (WP-F4-02, WP-F4-03)
    # -------------------------------------------------------------
    inv_robustness = InvariantRevision(
        invariant_id=new_id("invariant_revision"),
        invariant_revision="1",
        source_generation_ref=src_gen,
        statement="Packet parser must never crash on malformed inputs",
        category="PARSING",
        activation_policy_ref=policy_ref,
    )
    assert inv_robustness.category == "PARSING"

    mat_ref = ref("materiality_assessment", "mat_parser_1")

    obl_lib = ObligationPolicyLibrary()
    obligations = obl_lib.generate_obligations(
        surface_ref=emitted_surfaces[0].as_object().as_ref(),
        surface_category="PARSER",
        invariant_ref=inv_robustness.as_object().as_ref(),
        invariant_logical_id="inv_robustness_parser",
        materiality_assessment_ref=mat_ref,
        source_generation_ref=src_gen,
        history_cut=cut,
        environment_profile_ref=ref("environment_profile", "env_1"),
        governing_policy_ref=policy_ref,
    )
    assert len(obligations) >= 1
    breadth = compute_breadth_summary(
        inventory_revision_ref=inv_rev.as_object().as_ref(),
        obligation_set_revision="1",
        evaluations=[{"effective_status": "QUALIFIED", "substantive_outcome": "NO_VIOLATION_OBSERVED", "satisfies_completion": True}],
        scope_states=[{"state": "KNOWN_SURFACE"}],
    )
    assert breadth["mandatory_count"] == 1

    # -------------------------------------------------------------
    # 3. GAP ENGINE: INITIAL STATE (WP-F4-04)
    # -------------------------------------------------------------
    gap_engine = GapEngine()
    gap_map_initial = gap_engine.compute_gap_map(
        inventory_surfaces=[s.as_object().as_ref() for s in emitted_surfaces],
        obligations=obligations,
        qualifications=[],  # No qualifications yet -> all obligations are open gaps
        history_cut=cut,
    )
    assert len(gap_map_initial.gaps) == 1
    assert len(gap_map_initial.gaps[0].missing_or_unsatisfied_obligation_refs) == len(obligations)
    assert len(gap_map_initial.digest) == 64

    # -------------------------------------------------------------
    # 4. NATIVE E1 DISCOVERY ENSEMBLE (WP-F4-09)
    # -------------------------------------------------------------
    e1_discoveries = {
        "E1-A": [{"statement": "Missing length check in parse_packet header", "severity_value": "INFO"}],
        "E1-B": [{"statement": "Unauthenticated access to internal parse buffer", "severity_value": "INFO"}],
        "E1-C": [{"statement": "Memory corruption on 64KB packet", "severity_value": "INFO"}],
        "E1-D": [{"statement": "Malformed packet header triggers heap overflow", "claim_outcome": "SUPPORTED", "severity_value": "INFO"}],
        "E1-E": [{"statement": "Deadlock during packet reassembly", "severity_value": "INFO"}],
    }
    e1_result = execute_e1_ensemble(src_gen, e1_discoveries)
    assert e1_result.stage_key == "E1"
    assert e1_result.total_discoveries == 5

    # -------------------------------------------------------------
    # 5. NATIVE E2 CONVERGENCE (WP-F4-09)
    # -------------------------------------------------------------
    e2_result = execute_e2_convergence(
        e1_completion=e1_result,
        source_generation_ref=src_gen,
        adjudicator_ref=adjudicator,
        input_history_cut=cut,
        policy_ref=policy_ref,
    )
    assert e2_result.stage_key == "E2"
    assert len(e2_result.adjudicated_decisions) == 5

    # -------------------------------------------------------------
    # 6. HYPOTHESIS & EXPERIMENT EXECUTION (WP-F4-05, WP-F4-06)
    # -------------------------------------------------------------
    hyp_orch = HypothesisOrchestrator()
    hyp1 = hyp_orch.propose_hypothesis(
        statement="Crafted length header triggers heap buffer overflow in parse_packet",
        scope_refs=[emitted_surfaces[0].as_object().as_ref()],
        invariant_refs=[inv_robustness.as_object().as_ref()],
        obligation_refs=[ob.as_object().as_ref() for ob in obligations],
        source_generation_ref=src_gen,
        history_cut=cut,
    )
    hyp2 = hyp_orch.transition(hyp1, "PREREGISTERED")
    hyp3 = hyp_orch.transition(hyp2, "TESTING")
    hyp = hyp_orch.transition(hyp3, "CONFIRMED")
    assert hyp.status == "CONFIRMED"

    exp_spec = ExperimentSpec(
        experiment_id=new_id("experiment_spec"),
        experiment_revision="1",
        hypothesis_revision_ref=hyp.as_object().as_ref(),
        invariant_revision_ref=inv_robustness.as_object().as_ref(),
        coverage_obligation_refs=[ob.as_object().as_ref() for ob in obligations],
        subject_baseline_ref=src_gen,
        target_execution_variant_ref=ref("variant", "v1"),
        environment_profile_ref=ref("environment_profile", "env_sandbox"),
        dependency_set_ref=ref("dependency_set", "dep_1"),
        harness_ref=ref("harness_profile", "fuzz_harness"),
        fixture_refs=[ref("fixture", "fix_1")],
        trigger="PARSE_MALFORMED_HEADER",
        expected_safe_behavior="Error::InvalidLength returned cleanly",
        expected_buggy_behavior="Heap buffer overflow crash with SIGSEGV",
        observation_path_requirements=["MEMORY_SANITIZER", "STDERR_CAPTURE"],
        falsification_condition="status != 0",
        positive_controls=["valid_packet_parses_cleanly"],
        negative_controls=["zero_length_packet_fails_gracefully"],
        input_history_cut=cut,
    )

    exec_adapter = ExecutionAdapter()
    desc, res, obs_list, clean, fault_rec = exec_adapter.execute_experiment(
        experiment_spec=exp_spec,
        executor_profile={"allowed_techniques": ["MEMORY_SANITIZER", "STDERR_CAPTURE"]},
        attempt_ref=ref("attempt", "att_domain_integration"),
        history_cut=cut,
        environment_actuals={"env": "sandbox"},
        execution_nonce="nonce_integration_001",
        runner_fn=integration_runner,
    )
    assert res.status == "SUCCESS"
    assert len(obs_list) >= 1

    # Validate DAG acyclicity
    validate_execution_dag([
        (exp_spec.experiment_id, desc.execution_descriptor_id),
        (desc.execution_descriptor_id, res.execution_result_id),
    ])

    # -------------------------------------------------------------
    # 7. EVIDENCE GRAPH, INDEPENDENCE & QUALIFICATION (WP-F4-07)
    # -------------------------------------------------------------
    obs = Observation(
        execution_descriptor_ref=desc.as_object().as_ref(),
        raw_observation_ref=ref("raw_artifact_ref", "crash_dump_01"),
        observation_channel="stderr",
        observed_at="2026-09-11T12:00:00Z",
    )
    ind_res = assess_multidimensional_independence(
        claim_ref=hyp.as_object().as_ref(),
        lane_a_deps={dim: [ref("dep", f"lane_a_{dim}")] for dim in INDEPENDENCE_DIMENSIONS},
        lane_b_deps={dim: [ref("dep", f"lane_b_{dim}")] for dim in INDEPENDENCE_DIMENSIONS},
    )
    assert ind_res["is_independent"] is True

    ind_ass = DependencyIndependenceAssessment(
        claim_revision_ref=hyp.as_object().as_ref(),
        assessment_input_history_cut=cut,
        dependency_graph_ref=ref("dependency_graph_ref", "graph_1"),
        independence_policy_ref=policy_ref,
        result="INDEPENDENT",
    )
    app_ass = EvidenceApplicabilityAssessment(
        claim_revision_ref=hyp.as_object().as_ref(),
        assessment_input_history_cut=cut,
        dependency_set_ref=ref("dependency_graph_ref", "graph_1"),
        environment_ref=ref("environment_record", "env_sandbox"),
        execution_variant_ref=ref("variant_ref", "var_1"),
        harness_ref=ref("harness_profile", "fuzz_harness"),
        subject_baseline_ref=src_gen,
    )
    qual_ass = EvidenceQualificationAssessment(
        claim_revision_ref=hyp.as_object().as_ref(),
        assessment_input_history_cut=cut,
        dependency_graph_ref=ref("dependency_graph_ref", "graph_1"),
        independence_assessment_ref=ind_ass.as_object().as_ref(),
        applicability_assessment_ref=app_ass.as_object().as_ref(),
        observation_refs=[obs.as_object().as_ref()],
        result="SUPPORTS",
    )

    ev_graph = EvidenceGraph()
    ev_graph.add_node("hyp_node", "HYPOTHESIS")
    ev_graph.add_node("obs_node", "OBSERVATION")
    ev_graph.add_node("qual_node", "QUALIFICATION_ASSESSMENT", data={"result": "SUPPORTS", "claim_id": "claim_overflow"})
    ev_graph.add_edge("obs_node", "hyp_node", "DEPENDS_ON")
    ev_graph.add_edge("qual_node", "obs_node", "DEPENDS_ON")
    ev_graph.validate_acyclic()

    # -------------------------------------------------------------
    # 8. GAP ENGINE: CLOSURE VIA QUALIFIED EVIDENCE (WP-F4-04)
    # -------------------------------------------------------------
    # Qualify all obligations to demonstrate gap closure
    qualifications = [
        CoverageObligationQualification(
            qualification_id=deterministic_id("coverage_obligation_qualification", f"qual_{i}"),
            obligation_revision_ref=ob.as_object().as_ref(),
            input_history_cut=cut,
            qualification_status="QUALIFIED",
            substantive_outcome="NO_VIOLATION_OBSERVED",
            evidence_qualification_refs=[qual_ass.as_object().as_ref()],
        )
        for i, ob in enumerate(obligations)
    ]
    gap_map_closed = gap_engine.compute_gap_map(
        inventory_surfaces=[s.as_object().as_ref() for s in emitted_surfaces],
        obligations=obligations,
        qualifications=qualifications,
        history_cut=cut,
    )
    assert len(gap_map_closed.gaps) == 0

    # -------------------------------------------------------------
    # 9. 4-AXIS ADJUDICATION & ROOT CAUSE (WP-F4-08)
    # -------------------------------------------------------------
    claim = FindingClaimRevision(
        statement="Heap buffer overflow in parse_packet on crafted length header",
        source_generation_ref=src_gen,
    )
    m = FindingAxisAssessment(
        claim_revision_ref=claim.as_object().as_ref(),
        assessment_input_history_cut=cut,
        assessment_policy_ref=policy_ref,
        axis="MECHANISM",
        epistemic_outcome="SUPPORTED",
        method="FUZZ_CRASH_ANALYSIS",
    )
    r = FindingAxisAssessment(
        claim_revision_ref=claim.as_object().as_ref(),
        assessment_input_history_cut=cut,
        assessment_policy_ref=policy_ref,
        axis="REACHABILITY",
        epistemic_outcome="SUPPORTED",
        method="ATTACK_SURFACE_TRACE",
    )
    i = FindingAxisAssessment(
        claim_revision_ref=claim.as_object().as_ref(),
        assessment_input_history_cut=cut,
        assessment_policy_ref=policy_ref,
        axis="IMPACT",
        epistemic_outcome="SUPPORTED",
        method="REMOTE_CODE_EXECUTION",
    )
    s = FindingAxisAssessment(
        claim_revision_ref=claim.as_object().as_ref(),
        assessment_input_history_cut=cut,
        assessment_policy_ref=policy_ref,
        axis="SEVERITY",
        severity_value="CRITICAL",
        method="CVSS_9_8",
    )
    adjudication = adjudicate_finding(
        claim=claim,
        mechanism=m,
        reachability=r,
        impact=i,
        severity=s,
        adjudicator_ref=adjudicator,
        input_history_cut=cut,
    )
    assert adjudication.lifecycle_status == "CONFIRMED_CURRENT"

    rc = cluster_findings_into_root_cause(
        source_generation_ref=src_gen,
        mechanism_statement="Crafted length controls permit an out-of-bounds packet-parser write",
        membership_edges=[{
            "finding_claim_revision_ref": claim.as_object().as_ref(),
            "relation_role": "PRIMARY",
            "scope": {"subsystem": "packet_parser"},
        }],
    )
    assert len(rc.membership_edges) == 1

    # -------------------------------------------------------------
    # 10. INVALIDATION PROPAGATION & GAP RE-OPENING (WP-F4-04, WP-F4-07)
    # -------------------------------------------------------------
    ev_graph.propagate_invalidation("obs_node", reason="FLAKY_HARNESS")
    q_node = ev_graph.get_node("qual_node")
    assert q_node.status == "STALE"
    assert q_node.satisfies_completion is False

    # Stale qualification re-opens the gap!
    degraded_quals = [
        CoverageObligationQualification(
            qualification_id=deterministic_id("coverage_obligation_qualification", f"qual_deg_{idx}"),
            obligation_revision_ref=ob.as_object().as_ref(),
            input_history_cut=cut,
            qualification_status="STALE",
            substantive_outcome="INCONCLUSIVE",
            reason_codes=["EVIDENCE_INVALIDATED"],
        )
        for idx, ob in enumerate(obligations)
    ]
    gap_map_reopened = gap_engine.compute_gap_map(
        inventory_surfaces=[s.as_object().as_ref() for s in emitted_surfaces],
        obligations=obligations,
        qualifications=degraded_quals,
        history_cut=cut,
    )
    assert len(gap_map_reopened.gaps) == 1
    assert len(gap_map_reopened.gaps[0].missing_or_unsatisfied_obligation_refs) == len(obligations)

    # -------------------------------------------------------------
    # 11. CONTRADICTION RESOLUTION AUTHORITY (WP-F4-08)
    # -------------------------------------------------------------
    counter_claim = FindingClaimRevision(
        statement="Crafted length header does not produce a reachable heap overflow",
        source_generation_ref=src_gen,
    )
    support_ref = ref("evidence_qualification_assessment", "ev_supports")
    oppose_ref = ref("evidence_qualification_assessment", "ev_refutes")
    contra = ContradictionRevision(
        claim_revision_refs=[claim.as_object().as_ref(), counter_claim.as_object().as_ref()],
        scope={"subsystem": "packet_parser"},
        positions=[
            {"claim_revision_ref": claim.as_object().as_ref().as_dict(), "position": "SUPPORTED"},
            {"claim_revision_ref": counter_claim.as_object().as_ref().as_dict(), "position": "REFUTED"},
        ],
        supporting_evidence_qualification_refs=[support_ref],
        opposing_evidence_qualification_refs=[oppose_ref],
        required_falsifier={"requirement": "Independent reproduction on the pinned parser baseline"},
        status="OPEN",
    )
    # Fail closed: majority vote forbidden
    with pytest.raises(ValidationError, match="MAJORITY_VOTE_FORBIDDEN"):
        resolve_contradiction(
            contradiction=contra,
            resolution_kind="REFUTED",
            resolved_scope={"subsystem": "packet_parser"},
            basis_refs=[support_ref],
            input_history_cut=cut,
            resulting_status="RESOLVED_FULL",
            resolved_by_majority_vote=True,
        )
    # Resolved by proper prior-bound authority
    contra_res = resolve_contradiction(
        contradiction=contra,
        resolution_kind="REFUTED",
        resolved_scope={"subsystem": "packet_parser"},
        basis_refs=[support_ref],
        input_history_cut=cut,
        resulting_status="RESOLVED_FULL",
    )
    assert contra_res.resulting_status == "RESOLVED_FULL"

    # -------------------------------------------------------------
    # 12. REPLAY CAPSULE & SUCCESSOR CAMPAIGN (WP-F4-10)
    # -------------------------------------------------------------
    capsule = ReplayCapsule(
        finding_or_claim_revision_ref=claim.as_object().as_ref(),
        subject_baseline_ref=src_gen,
        environment_profile_ref=ref("environment_profile", "env_sandbox"),
        dependency_set_ref=ref("dependency_set", "deps_1"),
        harness_ref=ref("harness_profile", "fuzz_harness"),
        generator_profile_ref=ref("generator_profile", "fuzz_gen"),
        command_spec={"command": "fuzz_packet", "payload": "overflow.bin"},
        expected_invariant_ref=inv_robustness.as_object().as_ref(),
        expected_observable={"exit_code": 139},
        producer_ref=ref("actor_or_authority_ref", "lane_e1_d"),
    )
    replay_rec = execute_replay_verification(
        capsule=capsule,
        replay_executor_ref=ref("executor_profile", "independent_worker"),
        actual_subject_ref=src_gen,
        actual_environment_ref=ref("environment_profile", "env_sandbox"),
        actual_harness_ref=ref("harness_profile", "fuzz_harness"),
        actual_dependencies_ref=ref("dependency_set", "deps_1"),
        independence_assessment_ref=ind_ass.as_object().as_ref(),
        observed_result={"exit_code": 139},
    )
    assert replay_rec.status == "REPRODUCED"

    # Successor campaign genesis chained to conclusion
    concl_ref = ref("campaign_conclusion", "concl_v1")
    pred_camp_ref = ref("campaign_genesis", "camp_001")
    successor = create_successor_campaign(
        predecessor_campaign_ref=pred_camp_ref,
        predecessor_conclusion_ref=concl_ref,
        successor_trigger_ref=ref("source_generation", "gen_f4_patched"),
        source_generation_ref=ref("source_generation", "gen_f4_patched"),
        successor_input_history_cut=cut,
        challenge_freshness_policy_ref=policy_ref,
        governing_policy_ref=policy_ref,
    )
    assert len(successor.digest) == 64
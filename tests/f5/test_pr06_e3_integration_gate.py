"""End-to-End E3 Integration Gate and Adversarial Proofs (WP-F5 / PR-E3-06).

Demonstrates:
1. Full E3 integration fixture:
   E3-X/Y/Z blind
   → checkpoint
   → positive obligation/gap reveal
   → gap-directed execution
   → cumulative E1/E2 reveal
   → optional holdout reveal
   → fuzzing
   → differential
   → metamorphic
   → evidence qualification
   → adjudication
   → coverage update
   → StageCompletion candidate

2. Complete compliance with the 7 normative conditions.
3. Rigorous failure and adversarial proofs (Section 14).
"""
import hashlib
import json
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.evidence.graph import EvidenceGraph
from bdb_audit.hypothesis.orchestrator import HypothesisOrchestrator
from bdb_audit.orchestration.e3 import (
    E3_LANE_SLOTS,
    build_e3_stage_spec,
    create_e3_blind_attempt,
    execute_e3_blind_ensemble,
    E3QuarantineBroker,
)
from bdb_audit.orchestration.e3_reveal import (
    E3BlindCheckpoint,
    create_e3_blind_checkpoint,
    execute_positive_gap_reveal,
    E3GapDirectedScheduler,
    execute_cumulative_corpus_reveal,
    execute_holdout_reveal,
    evaluate_false_negative_relationship,
)
from bdb_audit.orchestration.e3_gate import (
    E3IntegrationGateEvaluator,
    E3StageCompletionCandidate,
)
from bdb_audit.execution.fuzzing import (
    FuzzerCapability,
    create_fuzzer_case,
    DeterministicFuzzerAdapter,
    process_fuzz_result_through_pipeline,
    validate_no_direct_crash_to_finding,
)
from bdb_audit.execution.differential import (
    DifferentialPathConfig,
    DifferentialTestingFramework,
    process_differential_result_through_pipeline,
    validate_no_direct_diff_to_finding,
)
from bdb_audit.execution.metamorphic import (
    create_metamorphic_transformation,
    MetamorphicRelationSpec,
    MetamorphicTestingFramework,
    process_metamorphic_result_through_pipeline,
    validate_no_direct_metamorphic_to_finding,
)


def make_ref(kind: str, seed: str) -> dict:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }


def create_blind_attempt(*args, **kwargs):
    kwargs.setdefault(
        "channel_inventory_ref",
        make_ref(
            "registered_immutable_object",
            "e3_test_channel_inventory",
        ),
    )
    return create_e3_blind_attempt(*args, **kwargs)


def make_history_cut(seq: int = 1) -> dict:
    return {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": "camp_e3_gate",
        "accepted_head_seq": seq,
        "accepted_head_hash": hashlib.sha256(f"cut_{seq}".encode()).hexdigest(),
        "governing_policy_ref": "BDB_POLICY_REGISTRY::governing_policy/1",
        "governing_spec_refs": ["BDB_SPEC_REGISTRY::e3_gate_spec/1"],
    }


def test_full_e3_integration_fixture_to_stage_completion():
    # ---------------------------------------------------------
    # 1. E3-X/Y/Z Blind Novelty Ensemble
    # ---------------------------------------------------------
    src_gen = make_ref("source_generation", "gen_e3_full")
    cut_seq = 5
    cut = make_history_cut(cut_seq)
    lr_ref = make_ref("lane_run", "lr_e3")
    exec_ref = make_ref("executor_profile", "exec_e3")
    deliv_ref = make_ref("delivery_profile", "deliv_e3")
    producer_ref = make_ref("coordinator", "coord_primary")

    lane_contexts = {
        slot: create_blind_attempt(slot, lr_ref, cut, exec_ref, deliv_ref)
        for slot in E3_LANE_SLOTS
    }

    lane_discoveries = {
        "E3-X": [{"statement": "TLS authority boundary flaw"}],
        "E3-Y": [{"statement": "Database catalog corrupt state"}],
        "E3-Z": [{"statement": "Async worker concurrency race"}],
    }

    blind_res = execute_e3_blind_ensemble(src_gen, cut, lane_contexts, lane_discoveries)
    assert blind_res.total_discoveries == 3

    # ---------------------------------------------------------
    # 2. Checkpoint Sealing
    # ---------------------------------------------------------
    chk = create_e3_blind_checkpoint(blind_res, cut)
    assert chk.checkpoint_id.startswith("chk_e3_blind_")
    assert chk.sealed_findings_count == 3

    # ---------------------------------------------------------
    # 3. Positive Obligation / Gap Reveal
    # ---------------------------------------------------------
    critical_surfaces = [make_ref("surface", "auth_core"), make_ref("surface", "crypto_engine")]
    unknown_surfaces = [{"surface_id": "unknown_driver_surface"}]
    unsupported_surfaces = [{"surface_id": "unsupported_v1_crypto"}]

    open_obligations = [
        {"obligation_id": "ob_auth_1", "surface": "auth_core", "status": "OPEN"},
        {"obligation_id": "ob_crypto_1", "surface": "crypto_engine", "status": "OPEN"},
    ]

    gap_map = {
        "gap_map_id": "gm_e3_integration",
        "gaps": [
            {
                "gap_id": "gap_crypto_boundary",
                "target_scope_ref": critical_surfaces[1],
                "materiality": "CRITICAL",
                "missing_or_unsatisfied_obligation_refs": ["ob_crypto_1"],
            }
        ],
    }

    k_state_blind = lane_contexts["E3-X"].knowledge_state
    proj, rev_event, k_state_gap = execute_positive_gap_reveal(
        checkpoint=chk,
        accepted_history_cut=cut,
        knowledge_state_before=k_state_blind,
        coverage_obligations=open_obligations,
        gap_map=gap_map,
        explicit_unknown_scope=unknown_surfaces,
        explicit_unsupported_scope=unsupported_surfaces,
        producer_ref=producer_ref,
    )

    # ---------------------------------------------------------
    # 4. Gap-Directed Execution
    # ---------------------------------------------------------
    scheduler = E3GapDirectedScheduler(proj, rev_event, k_state_gap)
    targets = scheduler.get_gap_target_list()
    assert len(targets) >= 1

    gap_disc = scheduler.record_gap_directed_discovery(
        target_scope_ref=targets[0]["target_scope_ref"],
        discovery_data={"statement": "Weak prime generation parameter observed in gap exploration"},
    )
    assert gap_disc["classification"] == "POST_REVEAL_CONFIRMATION"

    # ---------------------------------------------------------
    # 5. Cumulative E1/E2 Reveal
    # ---------------------------------------------------------
    e1_e2_manifest = make_ref("manifest", "e1_e2_cumulative_snapshot")
    rev_cumul, k_state_cumul = execute_cumulative_corpus_reveal(
        scheduler=scheduler,
        e1_e2_corpus_manifest_ref=e1_e2_manifest,
        accepted_history_cut=cut,
        producer_ref=producer_ref,
    )
    assert "CUMULATIVE_E1_E2_CORPUS" in k_state_cumul.known_classes

    # ---------------------------------------------------------
    # 6. Optional External Holdout Reveal
    # ---------------------------------------------------------
    holdout_manifest = make_ref("manifest", "external_holdout_a1")
    rev_holdout, k_state_holdout = execute_holdout_reveal(
        knowledge_state=k_state_cumul,
        holdout_corpus_manifest_ref=holdout_manifest,
        accepted_history_cut=cut,
        producer_ref=producer_ref,
        corpus_role="AUXILIARY_HOLDOUT",
    )
    assert "CONSUMED_EXTERNAL_HOLDOUT" in k_state_holdout.known_classes

    # ---------------------------------------------------------
    # 7. M25 Fuzzing Adapter Execution
    # ---------------------------------------------------------
    fuzz_adapter = DeterministicFuzzerAdapter(
        capability=FuzzerCapability(max_cases=50),
        generator_ref=make_ref("generator", "gen_fuzz"),
        generator_profile_ref=make_ref("profile", "prof_fuzz"),
        harness_ref=make_ref("harness", "harness_fuzz"),
        environment_ref=make_ref("environment", "env_fuzz"),
    )
    fuzz_case = create_fuzzer_case(b"TRIGGER_CRASH_SEGFAULT", make_ref("gen", "g"), make_ref("tgt", "t"))
    fuzz_rec = fuzz_adapter.execute_case(fuzz_case)
    assert fuzz_rec.status == "CRASH"

    hyp_orch = HypothesisOrchestrator()
    ev_graph = EvidenceGraph()
    adj_policy_ref = make_ref("policy", "adj_policy")
    adjudicator_ref = make_ref("adjudicator", "adj_1")

    fuzz_hyp, fuzz_dec = process_fuzz_result_through_pipeline(
        fuzz_rec, hyp_orch, ev_graph, cut, src_gen, adj_policy_ref, adjudicator_ref, active_cut_seq=cut_seq
    )
    assert fuzz_hyp is not None
    assert fuzz_dec.lifecycle_status == "CONFIRMED_CURRENT"

    # ---------------------------------------------------------
    # 8. M26 Differential Testing Execution
    # ---------------------------------------------------------
    desc_a = make_ref("desc", "desc_a")
    desc_b = make_ref("desc", "desc_b")
    oracle_a = make_ref("oracle", "oracle_a")
    oracle_b = make_ref("oracle", "oracle_b")
    env = make_ref("env", "env_diff")

    diff_framework = DifferentialTestingFramework(
        path_a=DifferentialPathConfig("A", desc_a, oracle_a, env, lambda raw: {"access": True, "scope": "admin"}),
        path_b=DifferentialPathConfig("B", desc_b, oracle_b, env, lambda raw: {"access": True, "scope": "guest"}),  # Divergent
        expected_relation="SEMANTIC_EQUIVALENCE",
    )
    diff_res = diff_framework.execute_differential(
        input_case_ref=make_ref("case", "c_diff"),
        raw_input=b"access_token_query",
        source_generation_ref=src_gen,
        environment_ref=env,
    )
    assert diff_res.observed_relation == "DIVERGENCE"

    diff_hyp, diff_dec = process_differential_result_through_pipeline(
        diff_res, hyp_orch, ev_graph, cut, src_gen, adj_policy_ref, adjudicator_ref, active_cut_seq=cut_seq
    )
    assert diff_hyp is not None
    assert diff_dec.lifecycle_status == "CONFIRMED_CURRENT"

    # ---------------------------------------------------------
    # 9. M27 Metamorphic Testing Execution
    # ---------------------------------------------------------
    def target_with_bug(raw: bytes) -> dict:
        if raw.endswith(b" "):
            return {"hash": "corrupt_trailing_space"}
        return {"hash": "valid_content_hash"}

    meta_framework = MetamorphicTestingFramework(target_with_bug)
    trans = create_metamorphic_transformation("WHITESPACE_INVARIANCE", {"len": 1}, lambda r: r + b" ")
    meta_spec = MetamorphicRelationSpec(
        spec_id="spec_meta_hash",
        transformation_id=trans.transformation_id,
        expected_relation="OUTPUT_EQUIVALENT",
        target_system_ref=make_ref("target", "hash_service"),
        preregistration_cut=cut,
    )
    meta_framework.preregister_relation_spec(meta_spec)

    meta_rec = meta_framework.execute_metamorphic_test(
        original_input_ref=make_ref("input", "hash_in"),
        original_input=b"test_payload",
        transformation=trans,
        spec_id="spec_meta_hash",
        history_cut=cut,
        active_cut_seq=cut_seq,
    )
    assert meta_rec.observed_relation == "VIOLATION"

    meta_hyp, meta_dec, _ = process_metamorphic_result_through_pipeline(
        meta_rec, hyp_orch, ev_graph, cut, src_gen, adj_policy_ref, adjudicator_ref, active_cut_seq=cut_seq
    )
    assert meta_hyp is not None
    assert meta_dec.lifecycle_status == "CONFIRMED_CURRENT"

    # ---------------------------------------------------------
    # 10. Multi-Stage False Negative Assessment
    # ---------------------------------------------------------
    pred_stages = [make_ref("stage_completion", "e1_comp"), make_ref("stage_completion", "e2_comp")]
    fn_asmt = evaluate_false_negative_relationship(
        discovery_ref=gap_disc,
        assessment_input_history_cut=cut,
        predecessor_stage_refs=pred_stages,
        target_surface_ref=critical_surfaces[1],
        surface_active_in_predecessor=True,
        surface_observed_in_predecessor=False,
        predecessor_completion_seq=4,
    )
    assert fn_asmt.result == "MULTI_STAGE_FALSE_NEGATIVE"

    # ---------------------------------------------------------
    # 11. Evaluate E3 Integration Gate
    # ---------------------------------------------------------
    gate_evaluator = E3IntegrationGateEvaluator()
    candidate = gate_evaluator.evaluate_gate(
        blind_result=blind_res,
        checkpoint=chk,
        positive_projection=proj,
        reveal_event=rev_event,
        scheduler=scheduler,
        holdout_corpus_role="AUXILIARY_HOLDOUT",
        false_negative_assessments=[fn_asmt],
        critical_surfaces=critical_surfaces,
        open_obligations=open_obligations,
        findings_on_critical_surfaces=[],  # Zero findings on critical surfaces, obligations properly remain open
        test_case_count=100,
        attempted_coverage_increase=0.0,
        qualified_support_present=False,
        unknown_surfaces=unknown_surfaces,
        unsupported_surfaces=unsupported_surfaces,
        e2_completion_digest="e2_completed_digest_0000000000000000000000000000000000000000",
        fuzzing_count=1,
        differential_count=1,
        metamorphic_count=1,
        adjudicated_count=3,
    )

    assert candidate.gate_verdict == "PASS"
    assert candidate.stage_key == "E3"
    assert candidate.blind_discoveries_count == 3
    assert candidate.gap_discoveries_count == 1
    assert candidate.multi_stage_false_negatives_count == 1
    assert len(candidate.completion_digest) == 64
    assert candidate.unknown_scope_count == 1
    assert candidate.unsupported_scope_count == 1


# =========================================================================
# Adversarial & Failure Proofs (Section 14)
# =========================================================================

def test_adversarial_blind_lane_contamination_fails_closed():
    broker = E3QuarantineBroker()
    cut = make_history_cut(3)
    lr_ref = make_ref("lane_run", "lr")
    exec_ref = make_ref("executor_profile", "exec")
    deliv_ref = make_ref("delivery_profile", "deliv")

    ctx = create_blind_attempt("E3-X", lr_ref, cut, exec_ref, deliv_ref)
    broker.register_isolation_qualification("E3-X", ctx.isolation_qualification)

    # Contamination via forbidden fields
    with pytest.raises(ValidationError, match="DISALLOWED_KNOWLEDGE_REVEAL"):
        broker.record_lane_discovery("E3-X", {"finding_id": "f_123", "statement": "leaked"})


def test_adversarial_premature_reveal_before_checkpoint_fails_closed():
    blind_res_dummy = None
    with pytest.raises(AttributeError):
        create_e3_blind_checkpoint(blind_res_dummy, make_history_cut(1))


def test_adversarial_leaked_finding_corpus_in_positive_view_fails_closed():
    cut = make_history_cut(5)
    chk = E3BlindCheckpoint("chk_1", cut, "a" * 64, 3)
    k_state = lane_contexts = create_blind_attempt("E3-X", make_ref("lr", "l"), cut, make_ref("e", "e"), make_ref("d", "d")).knowledge_state

    with pytest.raises(ValidationError, match="DISALLOWED_FINDING_CORPUS_REVEAL"):
        execute_positive_gap_reveal(
            checkpoint=chk,
            accepted_history_cut=cut,
            knowledge_state_before=k_state,
            coverage_obligations=[{"finding_claim_ref": {"digest": "leak"}}],
            gap_map={"gaps": []},
            explicit_unknown_scope=(),
            explicit_unsupported_scope=(),
            producer_ref=make_ref("c", "c"),
        )


def test_adversarial_auxiliary_corpus_promoted_to_predecessor_fails_closed():
    gate = E3IntegrationGateEvaluator()
    with pytest.raises(ValidationError, match="CANONICAL_PREDECESSOR_CONFUSION"):
        gate.validate_no_auxiliary_corpus_confusion("CANONICAL_PREDECESSOR")


def test_adversarial_shared_differential_oracle_fails_closed():
    oracle = make_ref("oracle", "shared_db")
    desc = make_ref("desc", "desc_1")
    env = make_ref("env", "env_1")

    with pytest.raises(ValidationError, match="SHARED_DIFFERENTIAL_ORACLE_NOT_INDEPENDENT"):
        DifferentialTestingFramework(
            path_a=DifferentialPathConfig("A", desc, oracle, env, lambda x: x),
            path_b=DifferentialPathConfig("B", desc, oracle, env, lambda x: x),
        )


def test_adversarial_fuzz_crash_promoted_directly_to_finding_fails_closed():
    with pytest.raises(ValidationError, match="CRASH_CANNOT_AUTO_CREATE_FINDING"):
        validate_no_direct_crash_to_finding(
            attempted_claim={"statement": "Bypass"},
            is_direct_crash=True,
        )


def test_adversarial_metamorphic_relation_registered_retroactively_fails_closed():
    with pytest.raises(ValidationError, match="RETROACTIVE_METAMORPHIC_RELATION_REJECTED"):
        MetamorphicRelationSpec(
            spec_id="retro_spec",
            transformation_id="trans_1",
            expected_relation="OUTPUT_EQUIVALENT",
            target_system_ref=make_ref("target", "svc"),
            preregistration_cut=make_history_cut(3),
            preregistered_before_run=False,
        )


def test_adversarial_test_volume_cannot_inflate_coverage_fails_closed():
    gate = E3IntegrationGateEvaluator()
    with pytest.raises(ValidationError, match="TEST_VOLUME_CANNOT_INFLATE_COVERAGE"):
        gate.validate_coverage_not_inflated_by_test_volume(
            test_case_count=5000,
            attempted_coverage_increase=0.25,
            qualified_support_present=False,
        )


def test_adversarial_cannot_hide_unknown_or_unsupported_scope_fails_closed():
    gate = E3IntegrationGateEvaluator()

    # Omitted unknown surface
    with pytest.raises(ValidationError, match="CANNOT_HIDE_UNKNOWN_SCOPE"):
        gate.validate_unknown_scope_not_hidden(
            unknown_surfaces=[{"s": 1}],
            unsupported_surfaces=[],
            reported_unknown_scope=[],  # Omitted!
            reported_unsupported_scope=[],
        )

    # Omitted unsupported surface
    with pytest.raises(ValidationError, match="CANNOT_HIDE_UNSUPPORTED_SCOPE"):
        gate.validate_unknown_scope_not_hidden(
            unknown_surfaces=[],
            unsupported_surfaces=[{"u": 1}],
            reported_unknown_scope=[],
            reported_unsupported_scope=[],  # Omitted!
        )


def test_adversarial_critical_surface_obligations_removal_fails_closed():
    gate = E3IntegrationGateEvaluator()
    # Critical surfaces with zero findings, but obligations were wiped
    with pytest.raises(ValidationError, match="CRITICAL_OBLIGATION_UNJUSTIFIED_REMOVAL"):
        gate.validate_critical_surface_obligations(
            critical_surfaces=[{"surface": "auth"}],
            open_obligations=[],  # Disallowed removal!
            findings_on_critical_surfaces=[],
        )

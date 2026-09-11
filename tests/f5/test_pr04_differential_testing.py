"""Targeted unit and adversarial tests for PR-E3-04: M26 Differential Testing Framework.

Tests:
1. Semantic relation comparison:
   - SEMANTIC_EQUIVALENCE matches equivalent JSON even when raw bytes / ordering differ.
   - STRICT_EQUAL_BYTES distinguishes byte-level variations.
   - PERMUTATION_INVARIANCE matches reordered collections.
   - Genuine divergence produces observed_relation="DIVERGENCE" and detailed diff.
2. Multi-path execution and oracle binding:
   - Exact input, SourceGeneration, environment, and descriptor binding.
3. Adversarial proof:
   - Shared oracle / shared descriptor attempting to pretend independence fails closed
     (SHARED_DIFFERENTIAL_ORACLE_NOT_INDEPENDENT).
4. Canonical pipeline (diff -> evidence -> hypothesis -> adjudication):
   - Direct diff to finding bypass fails closed (DIFF_CANNOT_AUTO_CREATE_FINDING).
   - Canonical pipeline creates active evidence node, hypothesis revision, and sound adjudication.
5. Idempotent handling of duplicate diff executions.
6. Stale history cut rejection in differential pipeline (STALE_HISTORY_CUT_REJECTED).
"""
import hashlib
import json
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.evidence.graph import EvidenceGraph
from bdb_audit.hypothesis.orchestrator import HypothesisOrchestrator
from bdb_audit.execution.differential import (
    DifferentialPathConfig,
    compare_semantic_relation,
    DifferentialTestingFramework,
    process_differential_result_through_pipeline,
    validate_no_direct_diff_to_finding,
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


def make_history_cut(seq: int = 1) -> dict:
    return {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": "camp_diff_test",
        "accepted_head_seq": seq,
        "accepted_head_hash": hashlib.sha256(f"cut_{seq}".encode()).hexdigest(),
        "governing_policy_ref": "BDB_POLICY_REGISTRY::governing_policy/1",
        "governing_spec_refs": ["BDB_SPEC_REGISTRY::diff_spec/1"],
    }


def test_semantic_relation_beyond_raw_bytes():
    # JSON with different key ordering and whitespace
    json_a = b'{"status": "OK", "code": 200}'
    json_b = b'{\n  "code": 200,\n  "status": "OK"\n}'

    # Under STRICT_EQUAL_BYTES, raw bytes differ
    rel_strict, diff_strict = compare_semantic_relation(json_a, json_b, "STRICT_EQUAL_BYTES")
    assert rel_strict == "DIVERGENCE"
    assert diff_strict["reason"] == "RAW_BYTES_MISMATCH"

    # Under SEMANTIC_EQUIVALENCE, they match
    rel_sem, diff_sem = compare_semantic_relation(json_a, json_b, "SEMANTIC_EQUIVALENCE")
    assert rel_sem == "MATCH"
    assert diff_sem is None

    # Genuine divergence
    json_c = b'{"status": "ERROR", "code": 500}'
    rel_div, diff_div = compare_semantic_relation(json_a, json_c, "SEMANTIC_EQUIVALENCE")
    assert rel_div == "DIVERGENCE"
    assert diff_div is not None


def test_permutation_invariance_and_monotonic():
    list_a = [3, 1, 4, 1, 5]
    list_b = [1, 1, 3, 4, 5]
    rel, _ = compare_semantic_relation(list_a, list_b, "PERMUTATION_INVARIANCE")
    assert rel == "MATCH"

    rel_mon, _ = compare_semantic_relation(10, 20, "MONOTONIC_LEQ")
    assert rel_mon == "MATCH"

    rel_mon_viol, diff_mon = compare_semantic_relation(50, 20, "MONOTONIC_LEQ")
    assert rel_mon_viol == "DIVERGENCE"
    assert diff_mon["reason"] == "MONOTONIC_ORDER_VIOLATION"


def test_adversarial_shared_oracle_pretending_independence_fails_closed():
    shared_oracle = make_ref("oracle", "shared_oracle_x")
    desc_a = make_ref("execution_descriptor", "desc_a")
    desc_b = make_ref("execution_descriptor", "desc_b")
    env = make_ref("environment", "env_1")

    path_a = DifferentialPathConfig(
        path_name="PathA_Service",
        execution_descriptor_ref=desc_a,
        oracle_or_dependency_ref=shared_oracle,
        environment_ref=env,
        runner_fn=lambda x: x,
    )
    path_b = DifferentialPathConfig(
        path_name="PathB_Service",
        execution_descriptor_ref=desc_b,
        oracle_or_dependency_ref=shared_oracle,  # Same oracle!
        environment_ref=env,
        runner_fn=lambda x: x,
    )

    # Must fail closed: shared oracle cannot pretend independence
    with pytest.raises(ValidationError, match="SHARED_DIFFERENTIAL_ORACLE_NOT_INDEPENDENT"):
        DifferentialTestingFramework(
            path_a=path_a,
            path_b=path_b,
            expected_relation="SEMANTIC_EQUIVALENCE",
            require_independent_oracle=True,
        )


def test_differential_execution_and_canonical_pipeline():
    oracle_a = make_ref("oracle", "oracle_engine_alpha")
    oracle_b = make_ref("oracle", "oracle_engine_beta")
    desc_a = make_ref("execution_descriptor", "desc_alpha")
    desc_b = make_ref("execution_descriptor", "desc_beta")
    env = make_ref("environment", "env_linux")

    # Path A normalizes, Path B buggy implementation drops a field
    path_a = DifferentialPathConfig(
        path_name="CanonicalPath",
        execution_descriptor_ref=desc_a,
        oracle_or_dependency_ref=oracle_a,
        environment_ref=env,
        runner_fn=lambda raw: {"user": "alice", "roles": ["admin", "viewer"]},
    )
    path_b = DifferentialPathConfig(
        path_name="AlternativePath",
        execution_descriptor_ref=desc_b,
        oracle_or_dependency_ref=oracle_b,
        environment_ref=env,
        runner_fn=lambda raw: {"user": "alice", "roles": ["viewer"]},  # Missing 'admin'!
    )

    framework = DifferentialTestingFramework(
        path_a=path_a,
        path_b=path_b,
        expected_relation="SEMANTIC_EQUIVALENCE",
    )

    case_ref = make_ref("case", "case_input_1")
    src_gen = make_ref("source_generation", "src_1")

    result = framework.execute_differential(
        input_case_ref=case_ref,
        raw_input=b"test_query",
        source_generation_ref=src_gen,
        environment_ref=env,
    )

    assert result.observed_relation == "DIVERGENCE"
    assert result.diff_details is not None
    assert result.is_independent is True

    # 1. Adversarial: direct bypass to finding rejected
    with pytest.raises(ValidationError, match="DIFF_CANNOT_AUTO_CREATE_FINDING"):
        validate_no_direct_diff_to_finding(
            attempted_claim={"statement": "Direct diff claim"},
            is_direct_diff=True,
        )

    # 2. Canonical pipeline: diff -> observation/evidence -> hypothesis -> adjudication
    hyp_orch = HypothesisOrchestrator()
    ev_graph = EvidenceGraph()
    cut = make_history_cut(5)
    policy_ref = make_ref("policy", "adj_policy")
    adjudicator_ref = make_ref("adjudicator", "adj_1")

    hyp, decision = process_differential_result_through_pipeline(
        diff_result=result,
        hypothesis_orchestrator=hyp_orch,
        evidence_graph=ev_graph,
        history_cut=cut,
        source_generation_ref=src_gen,
        policy_ref=policy_ref,
        adjudicator_ref=adjudicator_ref,
        active_cut_seq=5,
    )

    assert hyp is not None
    assert "Differential divergence" in hyp.statement
    assert decision is not None
    assert decision.lifecycle_status == "CONFIRMED_CURRENT"
    assert len(ev_graph.nodes) >= 1


def test_differential_idempotency_and_stale_cut_rejection():
    oracle_a = make_ref("oracle", "oracle_a")
    oracle_b = make_ref("oracle", "oracle_b")
    desc_a = make_ref("execution_descriptor", "desc_a")
    desc_b = make_ref("execution_descriptor", "desc_b")
    env = make_ref("environment", "env_1")

    framework = DifferentialTestingFramework(
        path_a=DifferentialPathConfig("A", desc_a, oracle_a, env, lambda x: "out_a"),
        path_b=DifferentialPathConfig("B", desc_b, oracle_b, env, lambda x: "out_b"),
        expected_relation="STRICT_EQUAL_BYTES",
    )

    case_ref = make_ref("case", "case_idemp")
    src_gen = make_ref("source_generation", "src_1")
    res = framework.execute_differential(case_ref, b"same_input", src_gen, env)

    hyp_orch = HypothesisOrchestrator()
    ev_graph = EvidenceGraph()
    cut = make_history_cut(5)
    policy_ref = make_ref("policy", "adj_policy")
    adjudicator_ref = make_ref("adjudicator", "adj_1")

    # Idempotent processing
    h1, d1 = process_differential_result_through_pipeline(
        res, hyp_orch, ev_graph, cut, src_gen, policy_ref, adjudicator_ref, active_cut_seq=5
    )
    h2, d2 = process_differential_result_through_pipeline(
        res, hyp_orch, ev_graph, cut, src_gen, policy_ref, adjudicator_ref, active_cut_seq=5
    )
    assert h1.hypothesis_id == h2.hypothesis_id

    # Stale cut rejection
    stale_cut = make_history_cut(2)
    with pytest.raises(ValidationError, match="STALE_HISTORY_CUT_REJECTED"):
        process_differential_result_through_pipeline(
            res, hyp_orch, ev_graph, stale_cut, src_gen, policy_ref, adjudicator_ref, active_cut_seq=5
        )

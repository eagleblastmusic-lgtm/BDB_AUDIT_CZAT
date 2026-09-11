"""Targeted unit and adversarial tests for PR-E3-03: M25 Fuzzing Adapter Framework.

Tests:
1. Deterministic case identity (same raw bytes -> exact same case hash and case id).
2. Adapter capability limits: exceeding max_cases fails closed (FUZZER_CAPABILITY_EXCEEDED).
3. Crash does NOT auto-create finding:
   - Direct crash to finding bypass rejected (CRASH_CANNOT_AUTO_CREATE_FINDING).
   - Canonical pipeline (case -> evidence -> hypothesis -> adjudication) succeeds.
4. Reproduction linkage: reproduction_command and seeds present in execution record.
5. Cleanup: temporary resources cleared after execution.
6. Timeout handling: simulation produces status="TIMEOUT".
7. Malformed fuzzer output fails closed (MALFORMED_FUZZER_OUTPUT).
8. Duplicate case / idempotency: identical crash case processed idempotently.
9. Stale history cut rejected (STALE_HISTORY_CUT_REJECTED).
"""
import hashlib
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.evidence.graph import EvidenceGraph
from bdb_audit.hypothesis.orchestrator import HypothesisOrchestrator
from bdb_audit.execution.fuzzing import (
    FuzzerCapability,
    create_fuzzer_case,
    DeterministicFuzzerAdapter,
    process_fuzz_result_through_pipeline,
    validate_no_direct_crash_to_finding,
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
        "campaign_id": "camp_fuzz_test",
        "accepted_head_seq": seq,
        "accepted_head_hash": hashlib.sha256(f"cut_{seq}".encode()).hexdigest(),
        "governing_policy_ref": "BDB_POLICY_REGISTRY::governing_policy/1",
        "governing_spec_refs": ["BDB_SPEC_REGISTRY::fuzz_spec/1"],
    }


def _create_adapter(max_cases: int = 100, timeout: float = 2.0) -> DeterministicFuzzerAdapter:
    cap = FuzzerCapability(max_cases=max_cases, timeout_seconds=timeout)
    return DeterministicFuzzerAdapter(
        capability=cap,
        generator_ref=make_ref("generator", "fuzz_gen_1"),
        generator_profile_ref=make_ref("generator_profile", "fuzz_profile_1"),
        harness_ref=make_ref("harness", "fuzz_harness_1"),
        environment_ref=make_ref("environment", "env_test_1"),
    )


def test_deterministic_case_identity():
    gen_ref = make_ref("generator", "gen")
    tgt_ref = make_ref("target", "tgt")
    payload = b"CRASH_TEST_PAYLOAD_12345"

    case1 = create_fuzzer_case(payload, gen_ref, tgt_ref)
    case2 = create_fuzzer_case(payload, gen_ref, tgt_ref)

    assert case1.case_hash == case2.case_hash
    assert case1.case_id == case2.case_id
    assert case1.digest == case2.digest
    assert len(case1.case_hash) == 64


def test_adapter_capability_limits():
    adapter = _create_adapter(max_cases=10)

    # Within capability
    cases = adapter.generate_cases([b"seed"], count=5)
    assert len(cases) == 5

    # Exceeding capability must fail closed
    with pytest.raises(ValidationError, match="FUZZER_CAPABILITY_EXCEEDED"):
        adapter.generate_cases([b"seed"], count=15)


def test_crash_does_not_auto_create_finding_and_pipeline_succeeds():
    adapter = _create_adapter()
    gen_ref = make_ref("generator", "gen")
    tgt_ref = make_ref("target", "tgt")

    # 1. Adversarial: direct bypass from crash to finding rejected
    with pytest.raises(ValidationError, match="CRASH_CANNOT_AUTO_CREATE_FINDING"):
        validate_no_direct_crash_to_finding(
            attempted_claim={"statement": "Direct crash finding"},
            is_direct_crash=True,
        )

    # 2. Canonical pipeline: case -> observation/evidence -> hypothesis -> adjudication
    crash_case = create_fuzzer_case(b"TRIGGER_CRASH_SEGFAULT", gen_ref, tgt_ref)
    record = adapter.execute_case(crash_case)
    assert record.status == "CRASH"
    assert record.crash_observation_ref is not None

    hyp_orch = HypothesisOrchestrator()
    ev_graph = EvidenceGraph()
    cut = make_history_cut(5)
    src_gen = make_ref("source_generation", "src_1")
    policy_ref = make_ref("policy", "adj_policy")
    adjudicator_ref = make_ref("adjudicator", "adj_1")

    hyp, decision = process_fuzz_result_through_pipeline(
        fuzz_record=record,
        hypothesis_orchestrator=hyp_orch,
        evidence_graph=ev_graph,
        history_cut=cut,
        source_generation_ref=src_gen,
        policy_ref=policy_ref,
        adjudicator_ref=adjudicator_ref,
        active_cut_seq=5,
    )

    assert hyp is not None
    assert hyp.planning_mode == "EXPLORATORY"
    assert decision is not None
    assert decision.lifecycle_status == "CONFIRMED_CURRENT"
    assert len(ev_graph.nodes) >= 1


def test_reproduction_linkage_and_cleanup():
    adapter = _create_adapter()
    gen_ref = make_ref("generator", "gen")
    tgt_ref = make_ref("target", "tgt")
    case = create_fuzzer_case(b"TRIGGER_CRASH_TEST", gen_ref, tgt_ref)

    record = adapter.execute_case(case)
    assert record.cleaned_up is True
    assert "fuzz_replay" in record.reproduction_command
    assert case.case_hash in record.reproduction_command
    assert len(adapter._temp_resources) == 0


def test_fuzzer_timeout_handling():
    adapter = _create_adapter(timeout=0.1)
    gen_ref = make_ref("generator", "gen")
    tgt_ref = make_ref("target", "tgt")
    timeout_case = create_fuzzer_case(b"TRIGGER_TIMEOUT", gen_ref, tgt_ref)

    record = adapter.execute_case(timeout_case)
    assert record.status == "TIMEOUT"
    assert record.exit_code == 124
    assert record.crash_observation_ref is None


def test_malformed_fuzzer_output_fails_closed():
    adapter = _create_adapter()
    gen_ref = make_ref("generator", "gen")
    tgt_ref = make_ref("target", "tgt")
    malformed_case = create_fuzzer_case(b"\x00\xff\xfe\xfdMALFORMED_OUTPUT", gen_ref, tgt_ref)

    with pytest.raises(ValidationError, match="MALFORMED_FUZZER_OUTPUT"):
        adapter.execute_case(malformed_case)


def test_duplicate_case_idempotency():
    adapter = _create_adapter()
    gen_ref = make_ref("generator", "gen")
    tgt_ref = make_ref("target", "tgt")
    case = create_fuzzer_case(b"CRASH_IDEMPOTENT_CASE", gen_ref, tgt_ref)

    record1 = adapter.execute_case(case)
    record2 = adapter.execute_case(case)
    assert record1.input_case_ref == record2.input_case_ref
    assert record1.digest == record2.digest

    hyp_orch = HypothesisOrchestrator()
    ev_graph = EvidenceGraph()
    cut = make_history_cut(5)
    src_gen = make_ref("source_generation", "src_1")
    policy_ref = make_ref("policy", "adj_policy")
    adjudicator_ref = make_ref("adjudicator", "adj_1")

    hyp1, dec1 = process_fuzz_result_through_pipeline(
        record1, hyp_orch, ev_graph, cut, src_gen, policy_ref, adjudicator_ref, active_cut_seq=5
    )
    assert hyp1 is not None
    assert dec1 is not None


def test_stale_history_cut_rejected():
    adapter = _create_adapter()
    gen_ref = make_ref("generator", "gen")
    tgt_ref = make_ref("target", "tgt")
    case = create_fuzzer_case(b"CRASH_STALE_TEST", gen_ref, tgt_ref)
    record = adapter.execute_case(case)

    hyp_orch = HypothesisOrchestrator()
    ev_graph = EvidenceGraph()
    stale_cut = make_history_cut(3)
    src_gen = make_ref("source_generation", "src_1")
    policy_ref = make_ref("policy", "adj_policy")
    adjudicator_ref = make_ref("adjudicator", "adj_1")

    # Cut 3 is older than active cut 5
    with pytest.raises(ValidationError, match="STALE_HISTORY_CUT_REJECTED"):
        process_fuzz_result_through_pipeline(
            fuzz_record=record,
            hypothesis_orchestrator=hyp_orch,
            evidence_graph=ev_graph,
            history_cut=stale_cut,
            source_generation_ref=src_gen,
            policy_ref=policy_ref,
            adjudicator_ref=adjudicator_ref,
            active_cut_seq=5,
        )

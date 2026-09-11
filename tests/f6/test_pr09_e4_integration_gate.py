"""Targeted integration tests and adversarial proofs for PR-E4-09: E4 Integration Gate."""
import pytest
from bdb_audit.core.errors import ValidationError
from bdb_audit.deepen.gate import (
    E4GateVerdict,
    E4SyntheticBenchmark,
    E4IntegrationGate,
)
from bdb_audit.deepen.state_model import State, Guard, Transition, ForbiddenState, StateModel
from bdb_audit.deepen.temporal import OrderingConstraint, TemporalInvariant
from bdb_audit.deepen.adapters import AdapterCapability, PropertyTestAdapter, StatefulTestAdapter
from bdb_audit.deepen.exploration import ExplorationBounds, BoundedModelExplorer
from bdb_audit.deepen.concurrency import InterleavingSeed, ScheduleReplayEngine, SchedulePoint, ConcurrencySchedule
from bdb_audit.deepen.crash import CrashPoint, DurableStoreHarness, CrashRecoveryEngine
from bdb_audit.deepen.endurance import MetricSnapshot, EnduranceProfile, EnduranceEngine
from bdb_audit.deepen.causal import CausalEdge, CausalChainEngine


def test_e4_synthetic_benchmark_and_gate_pass(tmp_path):
    bench = E4SyntheticBenchmark(work_dir=str(tmp_path))
    summary = bench.run()

    gate = E4IntegrationGate()
    verdict = gate.evaluate(summary)

    assert verdict.is_all_pass()
    assert verdict.e4_integration_gate == "PASS"
    assert verdict.state_model_gate == "PASS"
    assert verdict.temporal_invariant_gate == "PASS"
    assert verdict.property_stateful_gate == "PASS"
    assert verdict.bounded_model_exploration_gate == "PASS"
    assert verdict.concurrency_schedule_gate == "PASS"
    assert verdict.crash_recovery_gate == "PASS"
    assert verdict.endurance_gate == "PASS"
    assert verdict.causal_chain_gate == "PASS"
    assert verdict.no_second_state_authority == "PASS"
    assert verdict.no_second_evidence_oracle == "PASS"
    assert verdict.evidence_qualification_path == "PASS"
    assert verdict.deterministic_replay == "PASS"


# ==============================================================================
# 18 Targeted Adversarial Negative Proofs (§17)
# ==============================================================================

def test_adv_01_illegal_state_transition():
    s0 = State("S0")
    g = Guard("g", lambda v, c: True)
    sm = StateModel("sm1", 1, {}, {"cut_id": "c1"}, "TEST", {}, {"S0": s0}, ["S0"], [])
    with pytest.raises(ValidationError) as exc:
        sm.step("S0", "NON_EXISTENT_EVENT")
    assert "ILLEGAL_TRANSITION" in str(exc.value)


def test_adv_02_forbidden_state():
    s0 = State("S0")
    s_bad = State("BAD")
    g = Guard("g", lambda v, c: True)
    t = Transition("t", "S0", "BAD", "GO", guards=(g,))
    fs = ForbiddenState("fs1", state_name="BAD", reason="forbidden")
    sm = StateModel("sm2", 1, {}, {"cut_id": "c1"}, "TEST", {}, {"S0": s0, "BAD": s_bad}, ["S0"], [t], [fs])
    with pytest.raises(ValidationError) as exc:
        sm.step("S0", "GO")
    assert "FORBIDDEN_STATE_REACHED" in str(exc.value)


def test_adv_03_stale_state_model_revision():
    s0 = State("S0")
    sm = StateModel("sm3", 1, {}, {"cut_id": "c_head", "point": 10}, "TEST", {}, {"S0": s0}, ["S0"], [])
    with pytest.raises(ValidationError) as exc:
        sm.step("S0", "ANY", history_cut={"cut_id": "c_stale", "point": 5})
    assert "STALE_HISTORY_CUT" in str(exc.value)


def test_adv_04_temporal_order_violation():
    tc = OrderingConstraint("tc", "BEFORE", event_a="AUTH", event_b="EXECUTE")
    ti = TemporalInvariant("ti1", 1, "S", {}, [tc], {"cut_id": "c1"})
    status, violations = ti.evaluate_trace(["EXECUTE", "AUTH"])
    assert status == "VIOLATED"
    assert len(violations) == 1


def test_adv_05_retroactive_temporal_rule_stale_cut():
    ti = TemporalInvariant("ti2", 1, "S", {}, [], {"cut_id": "c_v1", "point": 5})
    with pytest.raises(ValidationError) as exc:
        ti.evaluate_trace(["ANY"], history_cut={"cut_id": "c_retro", "point": 1})
    assert "STALE_HISTORY_CUT" in str(exc.value)


def test_adv_06_property_adapter_capability_escape():
    cap = AdapterCapability(max_operations=5)
    adapter = PropertyTestAdapter("pa", {}, {}, capability=cap)
    with pytest.raises(ValidationError) as exc:
        adapter.run_property_test(1, 10, lambda r: 1, lambda x: True)
    assert "CAPABILITY_LIMIT_EXCEEDED" in str(exc.value)


def test_adv_07_stateful_adapter_wrong_model():
    s0 = State("S0")
    sm = StateModel("sm", 1, {}, {"cut_id": "c1"}, "T", {}, {"S0": s0}, ["S0"], [])
    adapter = StatefulTestAdapter("sa", {}, sm)
    # Event not defined on model triggers failure
    res = adapter.execute_stateful_test(1, "S0", [("UNDEFINED_EVENT", None)], object())
    assert res.passed is False
    assert res.failing_step == 0


def test_adv_08_bounded_explorer_nontermination_prevention():
    s = State("S")
    t = Transition("t", "S", "S", "CYCLE", guards=(Guard("g", lambda v, c: True),))
    sm = StateModel("sm_cycle", 1, {}, {"cut_id": "c1"}, "T", {}, {"S": s}, ["S"], [t])
    explorer = BoundedModelExplorer(bounds=ExplorationBounds(max_depth=5))
    res = explorer.explore(sm)
    # Terminates cleanly
    assert res.status in ("EXHAUSTED_WITHIN_BOUND", "BOUND_REACHED")


def test_adv_09_schedule_replay_mismatch():
    engine = ScheduleReplayEngine()
    sp1 = SchedulePoint("p1", "A", "BEFORE_READ", 0)
    sched1 = ConcurrencySchedule("s_dup", InterleavingSeed(1), {"cut_id": "c1"}, ("A",), (sp1,))
    engine.replay(sched1, lambda sp: (False, "OK"))

    # Attempt replay with same schedule_id but different point
    sp2 = SchedulePoint("p2", "A", "AFTER_READ", 1)
    sched2 = ConcurrencySchedule("s_dup", InterleavingSeed(1), {"cut_id": "c1"}, ("A",), (sp1, sp2))
    with pytest.raises(ValidationError) as exc:
        engine.replay(sched2, lambda sp: (False, "OK"))
    assert "CONFLICTING_SCHEDULE_DUPLICATE" in str(exc.value)


def test_adv_10_impossible_interleaving():
    # Schedule point referencing non-participating actor
    sp = SchedulePoint("p1", "GHOST", "BEFORE_LOCK", 0)
    with pytest.raises(ValidationError) as exc:
        ConcurrencySchedule("s1", InterleavingSeed(1), {"cut_id": "c1"}, ("REAL_ACTOR",), (sp,))
    assert "UNKNOWN_ACTOR_IN_SCHEDULE" in str(exc.value)


def test_adv_11_concurrent_duplicate_acceptance(tmp_path):
    h = DurableStoreHarness(str(tmp_path / "cdup.sqlite"))
    r1 = h.accept_record("rec1", "data")
    assert r1["already_accepted"] is False
    r2 = h.accept_record("rec1", "data")
    assert r2["already_accepted"] is True


def test_adv_12_crash_partial_write(tmp_path):
    h = DurableStoreHarness(str(tmp_path / "part.sqlite"))
    engine = CrashRecoveryEngine()
    cp = CrashPoint("cp", "DURING_BOUNDARY", "op")
    res = engine.run_crash_test(h, "rec", "data", cp)
    assert res.recovery_status == "RECOVERED_ROLLEDBACK"
    assert res.accepted_before_crash is False


def test_adv_13_restart_from_incomplete_state(tmp_path):
    h = DurableStoreHarness(str(tmp_path / "incomp.sqlite"))
    engine = CrashRecoveryEngine()
    cp = CrashPoint("cp", "BEFORE_DURABLE_ACCEPTANCE", "op")
    res = engine.run_crash_test(h, "rec", "data", cp)
    assert res.recovery_status == "RECOVERED_ROLLEDBACK"


def test_adv_14_duplicate_retry(tmp_path):
    h = DurableStoreHarness(str(tmp_path / "dup.sqlite"))
    h.accept_record("r1", "payload")
    r_dup = h.accept_record("r1", "payload")
    assert r_dup["already_accepted"] is True


def test_adv_15_endurance_false_positive_spike():
    engine = EnduranceEngine()
    res = engine.run_endurance_test(
        workload_fn=lambda r: None,
        sampler_fn=lambda s: MetricSnapshot(1000 + s, 2, 10 if s == 2 else 2, 0, {}, 0, 50_000),
        profile=EnduranceProfile("p", workload_rounds=3),
    )
    assert res.classification == "RECOVERED_SPIKE"


def test_adv_16_resource_leak():
    engine = EnduranceEngine()
    current_res = [10]

    def work(r):
        current_res[0] += 5

    res = engine.run_endurance_test(
        workload_fn=work,
        sampler_fn=lambda s: MetricSnapshot(1000 + s, 2, current_res[0], 0, {}, 0, 50_000),
        profile=EnduranceProfile("p", workload_rounds=3),
    )
    assert res.classification == "RESOURCE_LEAK"


def test_adv_17_unsupported_causal_edge():
    with pytest.raises(ValidationError) as exc:
        CausalEdge("A", "B", "CAUSES_IMPACT", support_evidence_refs=())
    assert "MISSING_EDGE_SUPPORT" in str(exc.value)


def test_adv_18_causal_chain_using_invalidated_evidence():
    engine = CausalChainEngine()
    ev = {"evidence_id": "ev_inval"}
    edge = CausalEdge("A", "B", "TRANSITIONS_TO", (ev,))
    chain = engine.build_causal_chain(
        chain_id="c_inval",
        scope="S",
        trigger={"t": 1},
        path=["A", "B"],
        state_transition_refs=[],
        observation_refs=[],
        impact_ref={},
        edges=[edge],
        invalidated_evidence_ids={"ev_inval"},
    )
    assert chain.status == "INVALIDATED"

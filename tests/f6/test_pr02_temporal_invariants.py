"""Targeted tests for PR-E4-02 / M29: Temporal Invariant Engine."""
import pytest
from bdb_audit.core.errors import ValidationError
from bdb_audit.evidence.models import Observation
from bdb_audit.deepen.temporal import (
    OrderingConstraint,
    TemporalInvariant,
)


def test_satisfied_ordering_relations():
    c_before = OrderingConstraint(
        constraint_id="c_commit_before_ack",
        relation="BEFORE",
        event_a="COMMIT",
        event_b="ACK",
    )
    c_after = OrderingConstraint(
        constraint_id="c_pub_after_comp",
        relation="AFTER",
        event_a="PUBLISH",
        event_b="COMPLETENESS",
    )
    c_eventual = OrderingConstraint(
        constraint_id="c_req_eventual_res",
        relation="MUST_EVENTUALLY_FOLLOW",
        event_a="REQUEST",
        event_b="RESPONSE",
    )
    c_never = OrderingConstraint(
        constraint_id="c_no_write_after_close",
        relation="MUST_NEVER_FOLLOW",
        event_a="CLOSE",
        event_b="WRITE",
    )
    c_strict = OrderingConstraint(
        constraint_id="c_boot_sequence",
        relation="STRICT_ORDER",
        sequence=("INIT", "BOOT", "READY"),
    )
    c_bounded = OrderingConstraint(
        constraint_id="c_ack_within_3",
        relation="BOUNDED_FOLLOW",
        event_a="PING",
        event_b="PONG",
        max_steps=2,
    )

    ti = TemporalInvariant(
        invariant_id="ti_protocol_001",
        revision=1,
        scope="PROTOCOL",
        state_model_ref={"model_id": "sm_01", "revision": 1},
        constraints=[c_before, c_after, c_eventual, c_never, c_strict, c_bounded],
        history_cut={"cut_id": "cut_01", "point": 10},
    )

    # Valid trace satisfying all constraints
    trace = [
        "INIT",
        "BOOT",
        "COMMIT",
        "ACK",
        "COMPLETENESS",
        "PUBLISH",
        "READY",
        "REQUEST",
        "PING",
        "PONG",
        "RESPONSE",
        "CLOSE",
        "CLEANUP",
    ]

    status, violations = ti.evaluate_trace(trace, history_cut={"cut_id": "cut_01", "point": 10})
    assert status == "SATISFIED"
    assert len(violations) == 0


def test_violated_before_ordering():
    c = OrderingConstraint(
        constraint_id="c_commit_before_ack",
        relation="BEFORE",
        event_a="COMMIT",
        event_b="ACK",
    )
    ti = TemporalInvariant(
        invariant_id="ti_01",
        revision=1,
        scope="S",
        state_model_ref={"model_id": "sm_01"},
        constraints=[c],
        history_cut={"cut_id": "cut_01"},
    )
    # ACK occurred without prior COMMIT
    bad_trace = ["START", "ACK", "COMMIT"]
    status, violations = ti.evaluate_trace(bad_trace, history_cut={"cut_id": "cut_01"})
    assert status == "VIOLATED"
    assert len(violations) == 1
    assert "required_prerequisite" in violations[0]["details"]


def test_violated_must_never_follow():
    c = OrderingConstraint(
        constraint_id="c_no_write_after_close",
        relation="MUST_NEVER_FOLLOW",
        event_a="CLOSE",
        event_b="WRITE",
    )
    ti = TemporalInvariant(
        invariant_id="ti_02",
        revision=1,
        scope="S",
        state_model_ref={"model_id": "sm_01"},
        constraints=[c],
        history_cut={"cut_id": "cut_01"},
    )
    bad_trace = ["OPEN", "WRITE", "CLOSE", "READ", "WRITE"]
    status, violations = ti.evaluate_trace(bad_trace)
    assert status == "VIOLATED"
    assert violations[0]["details"]["forbidden_event"] == "WRITE"


def test_violated_must_eventually_follow():
    c = OrderingConstraint(
        constraint_id="c_must_res",
        relation="MUST_EVENTUALLY_FOLLOW",
        event_a="REQUEST",
        event_b="RESPONSE",
    )
    ti = TemporalInvariant(
        invariant_id="ti_03",
        revision=1,
        scope="S",
        state_model_ref={"model_id": "sm_01"},
        constraints=[c],
        history_cut={"cut_id": "cut_01"},
    )
    bad_trace = ["REQUEST", "TIMEOUT", "DROP"]
    status, violations = ti.evaluate_trace(bad_trace)
    assert status == "VIOLATED"
    assert violations[0]["details"]["missing_followup"] == "RESPONSE"


def test_violated_bounded_follow():
    c = OrderingConstraint(
        constraint_id="c_bounded",
        relation="BOUNDED_FOLLOW",
        event_a="PING",
        event_b="PONG",
        max_steps=2,
    )
    ti = TemporalInvariant(
        invariant_id="ti_04",
        revision=1,
        scope="S",
        state_model_ref={"model_id": "sm_01"},
        constraints=[c],
        history_cut={"cut_id": "cut_01"},
    )
    # PONG arrives at step 4 after PING (greater than max_steps 2)
    bad_trace = ["PING", "A", "B", "C", "PONG"]
    status, violations = ti.evaluate_trace(bad_trace)
    assert status == "VIOLATED"


def test_violated_strict_order_and_duplicated_event():
    c = OrderingConstraint(
        constraint_id="c_seq",
        relation="STRICT_ORDER",
        sequence=("STEP_1", "STEP_2", "STEP_3"),
    )
    ti = TemporalInvariant(
        invariant_id="ti_05",
        revision=1,
        scope="S",
        state_model_ref={"model_id": "sm_01"},
        constraints=[c],
        history_cut={"cut_id": "cut_01"},
    )
    # STEP_3 occurs before STEP_2; duplicated STEP_1
    trace_wrong = ["STEP_1", "STEP_1", "STEP_3", "STEP_2"]
    status, violations = ti.evaluate_trace(trace_wrong)
    assert status == "VIOLATED"


def test_stale_history_cut_rejected():
    ti = TemporalInvariant(
        invariant_id="ti_06",
        revision=1,
        scope="S",
        state_model_ref={"model_id": "sm_01"},
        constraints=[],
        history_cut={"cut_id": "cut_valid", "point": 100},
    )
    with pytest.raises(ValidationError) as exc:
        ti.evaluate_trace(["ANY"], history_cut={"cut_id": "cut_stale", "point": 99})
    assert "STALE_HISTORY_CUT" in str(exc.value)


def test_deterministic_evaluation():
    c = OrderingConstraint(
        constraint_id="c_order",
        relation="BEFORE",
        event_a="A",
        event_b="B",
    )
    ti = TemporalInvariant(
        invariant_id="ti_07",
        revision=1,
        scope="S",
        state_model_ref={"model_id": "sm_01"},
        constraints=[c],
        history_cut={"cut_id": "cut_01"},
    )
    trace = ["B", "A"]
    res1 = ti.evaluate_trace(trace)
    res2 = ti.evaluate_trace(trace)
    assert res1 == res2
    assert res1[0] == "VIOLATED"


def test_observation_generated_on_violation_no_finding_shortcut():
    c = OrderingConstraint(
        constraint_id="c_order",
        relation="BEFORE",
        event_a="A",
        event_b="B",
    )
    ti = TemporalInvariant(
        invariant_id="ti_08",
        revision=1,
        scope="S",
        state_model_ref={"model_id": "sm_01", "revision": 1},
        constraints=[c],
        history_cut={"cut_id": "cut_01"},
    )
    status, violations = ti.evaluate_trace(["B"])
    assert status == "VIOLATED"

    # Generates Observation, strictly NOT a finding
    obs = ti.create_observation_on_violation(violations)
    assert isinstance(obs, Observation)
    assert obs.observation_channel == "TEMPORAL_INVARIANT_ENGINE"
    assert "violations" in obs.raw_observation_ref
    # Observation is an input to evidence qualification, not finding authority
    assert not hasattr(obs, "lifecycle_status")
    assert not hasattr(obs, "finding_id")

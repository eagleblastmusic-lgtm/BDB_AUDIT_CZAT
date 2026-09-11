"""Targeted tests for PR-E4-01 / M28: State Model Engine."""
import pytest
from bdb_audit.core.errors import ValidationError
from bdb_audit.deepen.state_model import (
    State,
    Guard,
    Transition,
    ForbiddenState,
    StateModel,
    evaluate_model_fidelity,
)
from bdb_audit.schemas.foundation import F6_KINDS, executable_schema
from bdb_audit.schemas.binding import SchemaBindings
from bdb_audit.core.registry import ContractRegistry
from jsonschema import validate as json_validate


def make_test_model(
    history_cut=None,
    forbidden_states=(),
    abstraction_assumptions=(),
    bounds=(),
):
    hcut = history_cut or {"point": 10, "cut_id": "cut_test_01"}
    s_init = State("INIT", "Initial idle state")
    s_running = State("RUNNING", "Running state")
    s_paused = State("PAUSED", "Paused state")
    s_error = State("ERROR", "Error state")

    g_can_run = Guard("can_run", lambda vars, ctx: vars.get("ready", False), "Must be ready")
    g_always = Guard("always_true", lambda vars, ctx: True, "Unconditional")

    t1 = Transition(
        transition_id="t_init_to_running",
        source_state="INIT",
        target_state="RUNNING",
        event="START",
        guards=(g_can_run,),
        effect=lambda vars, ctx: {**vars, "started_count": vars.get("started_count", 0) + 1},
    )
    t2 = Transition(
        transition_id="t_running_to_paused",
        source_state="RUNNING",
        target_state="PAUSED",
        event="PAUSE",
        guards=(g_always,),
    )
    t3 = Transition(
        transition_id="t_paused_to_running",
        source_state="PAUSED",
        target_state="RUNNING",
        event="RESUME",
        guards=(g_always,),
    )
    t4 = Transition(
        transition_id="t_running_to_error",
        source_state="RUNNING",
        target_state="ERROR",
        event="FAIL",
        guards=(g_always,),
    )

    states = {s.name: s for s in [s_init, s_running, s_paused, s_error]}
    transitions = [t1, t2, t3, t4]

    return StateModel(
        model_id="sm_test_001",
        model_revision=1,
        source_generation_ref={"generation_id": "gen_001"},
        history_cut=hcut,
        scope="SESSION_LIFECYCLE",
        state_variables={"ready": True, "started_count": 0},
        states=states,
        initial_states=["INIT"],
        transitions=transitions,
        forbidden_states=forbidden_states,
        abstraction_assumptions=abstraction_assumptions,
        bounds=bounds,
    )


def test_legal_transition():
    model = make_test_model()
    next_state, next_vars = model.step(
        "INIT",
        "START",
        current_vars={"ready": True, "started_count": 0},
        history_cut={"point": 10, "cut_id": "cut_test_01"},
    )
    assert next_state == "RUNNING"
    assert next_vars["started_count"] == 1


def test_illegal_transition():
    model = make_test_model()
    # No transition from INIT on PAUSE
    with pytest.raises(ValidationError) as exc:
        model.step(
            "INIT",
            "PAUSE",
            current_vars={"ready": True, "started_count": 0},
            history_cut={"point": 10, "cut_id": "cut_test_01"},
        )
    assert "ILLEGAL_TRANSITION" in str(exc.value)


def test_false_guard_rejects_transition():
    model = make_test_model()
    # ready is False, so guard fails closed
    with pytest.raises(ValidationError) as exc:
        model.step(
            "INIT",
            "START",
            current_vars={"ready": False, "started_count": 0},
            history_cut={"point": 10, "cut_id": "cut_test_01"},
        )
    assert "GUARD_EVALUATION_FAILED" in str(exc.value)


def test_forbidden_state_reached():
    fs = ForbiddenState(
        forbidden_id="fs_no_error",
        state_name="ERROR",
        reason="Error state is forbidden in production path",
    )
    model = make_test_model(forbidden_states=[fs])
    with pytest.raises(ValidationError) as exc:
        model.step(
            "RUNNING",
            "FAIL",
            current_vars={"ready": True, "started_count": 1},
            history_cut={"point": 10, "cut_id": "cut_test_01"},
        )
    assert "FORBIDDEN_STATE_REACHED" in str(exc.value)


def test_unreachable_forbidden_state():
    fs = ForbiddenState(
        forbidden_id="fs_unreachable",
        state_name="ERROR",
        reason="Unreachable in normal happy path",
    )
    model = make_test_model(forbidden_states=[fs])
    # Step to RUNNING, then PAUSED, then back to RUNNING: never hits ERROR
    s1, v1 = model.step("INIT", "START", current_vars={"ready": True, "started_count": 0})
    assert s1 == "RUNNING"
    s2, v2 = model.step(s1, "PAUSE", current_vars=v1)
    assert s2 == "PAUSED"
    s3, v3 = model.step(s2, "RESUME", current_vars=v2)
    assert s3 == "RUNNING"


def test_deterministic_replay():
    model = make_test_model()
    trace = [
        ("START", None),
        ("PAUSE", None),
        ("RESUME", None),
        ("PAUSE", None),
        ("RESUME", None),
    ]
    res1 = model.replay("INIT", trace, initial_vars={"ready": True, "started_count": 0})
    res2 = model.replay("INIT", trace, initial_vars={"ready": True, "started_count": 0})
    assert res1 == res2
    assert len(res1) == 6
    assert res1[-1] == ("RUNNING", {"ready": True, "started_count": 1})


def test_stale_history_cut_rejected():
    model = make_test_model(history_cut={"point": 10, "cut_id": "cut_test_01"})
    with pytest.raises(ValidationError) as exc:
        model.step(
            "INIT",
            "START",
            current_vars={"ready": True, "started_count": 0},
            history_cut={"point": 9, "cut_id": "stale_cut"},
        )
    assert "STALE_HISTORY_CUT" in str(exc.value)


def test_wrong_state_model_binding():
    # Initial state not present in states raises ValidationError
    with pytest.raises(ValidationError) as exc:
        StateModel(
            model_id="sm_invalid",
            model_revision=1,
            source_generation_ref={"generation_id": "gen_001"},
            history_cut={"point": 1, "cut_id": "cut_1"},
            scope="TEST",
            state_variables={},
            states={"S1": State("S1")},
            initial_states=["NON_EXISTENT"],
            transitions=[],
        )
    assert "UNKNOWN_INITIAL_STATE" in str(exc.value)


def test_model_update_does_not_mutate_accepted_predecessor():
    model_v1 = make_test_model()
    digest_v1 = model_v1.model_hash()

    # Create successor revision v2
    model_v2 = model_v1.create_successor(bounds=["max_depth_10"])

    assert model_v1.model_revision == 1
    assert model_v1.bounds == ()
    assert model_v1.model_hash() == digest_v1
    assert model_v2.model_revision == 2
    assert model_v2.bounds == ("max_depth_10",)
    assert model_v2.predecessor_revision_ref["digest"] == digest_v1
    assert model_v2.predecessor_revision_ref["revision"] == 1


def test_model_fidelity_assessment_and_schema():
    model = make_test_model()
    hcut = {"point": 10, "cut_id": "cut_test_01"}

    # 1. Full conformance -> QUALIFIED
    ev = [{"evidence_id": "ev_01", "type": "OBSERVATION"}]
    fid_qual = evaluate_model_fidelity(model, ev, hcut)
    assert fid_qual.result == "QUALIFIED"

    # Schema validation against executable_schema
    schema = executable_schema("model_fidelity_assessment")
    json_validate(instance=fid_qual.body(), schema=schema)

    # 2. Missing conformance -> INSUFFICIENT
    fid_insuff = evaluate_model_fidelity(model, [], hcut)
    assert fid_insuff.result == "INSUFFICIENT"
    json_validate(instance=fid_insuff.body(), schema=schema)

    # 3. Invalidated evidence -> INVALIDATED
    fid_inval = evaluate_model_fidelity(model, ev, hcut, is_invalidated=True)
    assert fid_inval.result == "INVALIDATED"
    json_validate(instance=fid_inval.body(), schema=schema)

    # 4. Model with bounds -> BOUNDED
    model_bounded = make_test_model(bounds=("state_limit_10",))
    fid_bound = evaluate_model_fidelity(model_bounded, ev, hcut)
    assert fid_bound.result == "BOUNDED"
    json_validate(instance=fid_bound.body(), schema=schema)

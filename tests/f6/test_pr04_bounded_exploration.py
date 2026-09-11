"""Targeted tests for PR-E4-04 / M31: Bounded Model Exploration Engine."""
import pytest
from bdb_audit.core.errors import ValidationError
from bdb_audit.evidence.models import Observation
from bdb_audit.deepen.state_model import State, Guard, Transition, ForbiddenState, StateModel
from bdb_audit.deepen.exploration import (
    ExplorationBounds,
    BoundedModelExplorer,
)


def make_tiny_model(with_cycle=False, with_forbidden=False):
    s0 = State("S0")
    s1 = State("S1")
    s2 = State("S2")
    s_bad = State("BAD")

    g = Guard("always", lambda v, c: True)

    t1 = Transition("t01", "S0", "S1", "GO_1", guards=(g,))
    t2 = Transition("t12", "S1", "S2", "GO_2", guards=(g,))
    transitions = [t1, t2]

    if with_cycle:
        # Cycle back from S2 to S0
        transitions.append(Transition("t20", "S2", "S0", "LOOP", guards=(g,)))

    forbidden = []
    if with_forbidden:
        transitions.append(Transition("t1_bad", "S1", "BAD", "GO_BAD", guards=(g,)))
        forbidden.append(
            ForbiddenState(forbidden_id="fs_bad", state_name="BAD", reason="Dangerous failure state")
        )

    states = {"S0": s0, "S1": s1, "S2": s2}
    if with_forbidden:
        states["BAD"] = s_bad

    return StateModel(
        model_id="sm_explore_01",
        model_revision=1,
        source_generation_ref={"generation_id": "gen_01"},
        history_cut={"cut_id": "cut_01", "point": 10},
        scope="TINY_SPACE",
        state_variables={},
        states=states,
        initial_states=["S0"],
        transitions=transitions,
        forbidden_states=forbidden,
    )


def test_complete_tiny_state_space():
    model = make_tiny_model(with_cycle=False)
    explorer = BoundedModelExplorer(bounds=ExplorationBounds(max_states=10, max_depth=5))
    res = explorer.explore(model)

    assert res.status == "EXHAUSTED_WITHIN_BOUND"
    assert res.states_visited == 3
    assert res.transitions_explored == 2
    assert res.forbidden_state_hit is None


def test_cycle_handling():
    model = make_tiny_model(with_cycle=True)
    explorer = BoundedModelExplorer(bounds=ExplorationBounds(max_states=10, max_depth=10))
    res = explorer.explore(model)

    # With cycle detection, terminates cleanly without infinite loop
    assert res.status == "EXHAUSTED_WITHIN_BOUND"
    assert res.states_visited == 3


def test_bound_reached_max_depth():
    # Long linear chain of 10 states
    states = {f"S{i}": State(f"S{i}") for i in range(10)}
    g = Guard("always", lambda v, c: True)
    transitions = [
        Transition(f"t{i}", f"S{i}", f"S{i+1}", f"STEP_{i}", guards=(g,))
        for i in range(9)
    ]
    model = StateModel(
        model_id="sm_chain",
        model_revision=1,
        source_generation_ref={"generation_id": "gen_01"},
        history_cut={"cut_id": "cut_01", "point": 1},
        scope="CHAIN",
        state_variables={},
        states=states,
        initial_states=["S0"],
        transitions=transitions,
    )

    explorer = BoundedModelExplorer(bounds=ExplorationBounds(max_depth=3, max_states=50))
    res = explorer.explore(model)

    assert res.status == "BOUND_REACHED"
    assert "depth" in res.termination_reason.lower()


def test_bound_reached_max_states():
    # Model with variable expanding state space
    s = State("LOOP")
    g = Guard("always", lambda v, c: True)
    t = Transition(
        "t_inc",
        "LOOP",
        "LOOP",
        "INC",
        guards=(g,),
        effect=lambda vars, ctx: {"c": vars.get("c", 0) + 1},
    )
    model = StateModel(
        model_id="sm_infinite",
        model_revision=1,
        source_generation_ref={"generation_id": "gen_01"},
        history_cut={"cut_id": "cut_01", "point": 1},
        scope="COUNTER",
        state_variables={"c": 0},
        states={"LOOP": s},
        initial_states=["LOOP"],
        transitions=[t],
    )

    explorer = BoundedModelExplorer(bounds=ExplorationBounds(max_states=5, max_depth=20))
    res = explorer.explore(model)

    assert res.status == "BOUND_REACHED"
    assert "states" in res.termination_reason.lower()


def test_forbidden_state_found_and_deterministic_replay():
    model = make_tiny_model(with_forbidden=True)
    explorer = BoundedModelExplorer(bounds=ExplorationBounds(max_states=10, max_depth=5))
    res = explorer.explore(model)

    assert res.status == "FORBIDDEN_STATE_FOUND"
    assert res.forbidden_state_hit == "fs_bad"
    assert len(res.counterexample_trace) == 2
    assert res.counterexample_trace[0][0] == "GO_1"
    assert res.counterexample_trace[1][0] == "GO_BAD"

    # Replay counterexample trace on the model directly: must hit ForbiddenState
    with pytest.raises(ValidationError) as exc:
        model.replay("S0", res.counterexample_trace)
    assert "FORBIDDEN_STATE_REACHED" in str(exc.value)


def test_invalid_model():
    explorer = BoundedModelExplorer()
    bad_model = object()  # Not a valid model
    res = explorer.explore(bad_model)
    assert res.status == "INVALID_MODEL"


def test_exploration_observation_conversion():
    model = make_tiny_model(with_forbidden=True)
    explorer = BoundedModelExplorer()
    res = explorer.explore(model)

    obs = explorer.to_observation(res)
    assert isinstance(obs, Observation)
    assert obs.observation_channel == "BOUNDED_MODEL_EXPLORATION"
    assert obs.raw_observation_ref["status"] == "FORBIDDEN_STATE_FOUND"
    # No finding shortcut
    assert not hasattr(obs, "finding_id")
    assert not hasattr(obs, "lifecycle_status")

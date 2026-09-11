"""Targeted tests for PR-E4-03 / M30: Property / Stateful Adapter Framework."""
import pytest
from bdb_audit.core.errors import ValidationError
from bdb_audit.evidence.models import Observation
from bdb_audit.deepen.state_model import State, Guard, Transition, StateModel
from bdb_audit.deepen.adapters import (
    AdapterCapability,
    PropertyTestAdapter,
    StatefulTestAdapter,
)


def make_sample_model():
    s_idle = State("IDLE")
    s_active = State("ACTIVE")
    s_done = State("DONE")
    g = Guard("always", lambda v, c: True)

    t1 = Transition("t_start", "IDLE", "ACTIVE", "START", guards=(g,))
    t2 = Transition("t_finish", "ACTIVE", "DONE", "FINISH", guards=(g,))
    t3 = Transition("t_reset", "DONE", "IDLE", "RESET", guards=(g,))

    return StateModel(
        model_id="sm_adapter_test",
        model_revision=1,
        source_generation_ref={"generation_id": "gen_01"},
        history_cut={"cut_id": "cut_01", "point": 5},
        scope="JOB_FLOW",
        state_variables={},
        states={"IDLE": s_idle, "ACTIVE": s_active, "DONE": s_done},
        initial_states=["IDLE"],
        transitions=[t1, t2, t3],
    )


class MockSUT:
    def __init__(self, buggy=False):
        self.state = "IDLE"
        self.buggy = buggy

    def reset(self):
        self.state = "IDLE"

    def step(self, event, context=None):
        if self.buggy and event == "FINISH":
            # Buggy SUT transitions to ERROR instead of DONE
            self.state = "ERROR"
            return self.state
        if self.state == "IDLE" and event == "START":
            self.state = "ACTIVE"
        elif self.state == "ACTIVE" and event == "FINISH":
            self.state = "DONE"
        elif self.state == "DONE" and event == "RESET":
            self.state = "IDLE"
        else:
            raise RuntimeError(f"Illegal action {event} from {self.state}")
        return self.state


def test_positive_property_adapter():
    cap = AdapterCapability(max_operations=50)
    adapter = PropertyTestAdapter(
        adapter_id="prop_adapter_01",
        target_ref={"target": "math_abs"},
        policy_ref={"policy_id": "pol_positivity"},
        capability=cap,
    )

    cleanup_called = []

    # Property: x*x >= 0
    res = adapter.run_property_test(
        seed=42,
        count=20,
        generator=lambda rng: rng.randint(-1000, 1000),
        property_fn=lambda x: x * x >= 0,
        cleanup_fn=lambda: cleanup_called.append(True),
    )

    assert res.passed is True
    assert res.cases_tested == 20
    assert res.failing_input is None
    assert res.cleanup_executed is True
    assert cleanup_called == [True]


def test_adversarial_property_adapter_and_shrinking():
    adapter = PropertyTestAdapter(
        adapter_id="prop_adapter_02",
        target_ref={"target": "even_check"},
        policy_ref={"policy_id": "pol_even"},
    )

    # Property: n is even (will fail on odd integers)
    res = adapter.run_property_test(
        seed=123,
        count=20,
        generator=lambda rng: rng.randint(5, 50),
        property_fn=lambda x: (x % 2) == 0,
    )

    assert res.passed is False
    assert res.failing_input is not None
    # Shrunk input should be minimal odd positive number
    assert res.shrunk_input is not None
    assert res.shrunk_input % 2 != 0


def test_property_adapter_capability_violation():
    cap = AdapterCapability(max_operations=10)
    adapter = PropertyTestAdapter(
        adapter_id="prop_adapter_03",
        target_ref={"target": "t"},
        policy_ref={"policy_id": "p"},
        capability=cap,
    )
    with pytest.raises(ValidationError) as exc:
        adapter.run_property_test(
            seed=1,
            count=15,  # exceeds max_operations 10
            generator=lambda rng: 1,
            property_fn=lambda x: True,
        )
    assert "CAPABILITY_LIMIT_EXCEEDED" in str(exc.value)


def test_stateful_adapter_positive():
    model = make_sample_model()
    adapter = StatefulTestAdapter(
        adapter_id="stateful_adapter_01",
        target_ref={"target": "job_manager"},
        state_model=model,
    )
    sut = MockSUT(buggy=False)
    seq = [("START", None), ("FINISH", None), ("RESET", None)]

    res = adapter.execute_stateful_test(
        seed=1,
        initial_state="IDLE",
        sequence=seq,
        system_under_test=sut,
    )

    assert res.passed is True
    assert res.steps_executed == 3
    assert res.final_state == "IDLE"
    assert res.failing_step is None
    assert res.cleanup_executed is True


def test_stateful_adapter_adversarial_divergence_and_shrinking():
    model = make_sample_model()
    adapter = StatefulTestAdapter(
        adapter_id="stateful_adapter_02",
        target_ref={"target": "job_manager"},
        state_model=model,
    )
    sut = MockSUT(buggy=True)
    seq = [("START", None), ("FINISH", None), ("RESET", None)]

    res = adapter.execute_stateful_test(
        seed=1,
        initial_state="IDLE",
        sequence=seq,
        system_under_test=sut,
    )

    assert res.passed is False
    assert res.failing_step == 1  # FINISH is at index 1
    assert res.failing_action[0] == "FINISH"
    assert len(res.shrunk_trace) > 0


def test_stateful_adapter_capability_unauthorized_command():
    model = make_sample_model()
    cap = AdapterCapability(allowed_commands=("START", "FINISH"))  # RESET not allowed
    adapter = StatefulTestAdapter(
        adapter_id="stateful_adapter_03",
        target_ref={"target": "job_manager"},
        state_model=model,
        capability=cap,
    )
    sut = MockSUT(buggy=False)
    seq = [("START", None), ("RESET", None)]

    with pytest.raises(ValidationError) as exc:
        adapter.execute_stateful_test(
            seed=1,
            initial_state="IDLE",
            sequence=seq,
            system_under_test=sut,
        )
    assert "CAPABILITY_UNAUTHORIZED_COMMAND" in str(exc.value)


def test_observation_emission_no_finding_shortcut():
    adapter = PropertyTestAdapter(
        adapter_id="prop_adapter_obs",
        target_ref={"target": "t"},
        policy_ref={"policy_id": "p"},
    )
    res = adapter.run_property_test(
        seed=1,
        count=5,
        generator=lambda rng: 3,
        property_fn=lambda x: x == 4,  # fails
    )
    assert res.passed is False

    obs = adapter.to_observation(res)
    assert isinstance(obs, Observation)
    assert obs.observation_channel == "PROPERTY_TEST_ADAPTER"
    assert obs.raw_observation_ref["passed"] is False
    # Verifying no finding authority bypass
    assert not hasattr(obs, "finding_id")
    assert not hasattr(obs, "lifecycle_status")

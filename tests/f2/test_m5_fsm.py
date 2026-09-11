import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.orchestration.fsm import legal_transition, project_states


def test_e0_and_lane_completion_gates():
    with pytest.raises(ValidationError, match="ILLEGAL_STATE_TRANSITION"):
        legal_transition("campaign", "GENESIS_ACCEPTED", "AUDIT_RUNNING")
    with pytest.raises(ValidationError, match="LANE_COMPLETION_REQUIRES_LANE_FACT"):
        legal_transition("lane", "WAITING_RESULT", "COMPLETION_ACCEPTED", event_kind="AttemptResult")
    assert legal_transition("lane", "COMPLETION_CANDIDATE", "COMPLETION_ACCEPTED")


def test_terminal_state_and_retry_are_immutable():
    facts = [
        {"aggregate": "attempt", "aggregate_id": "a", "from_state": "CREATED", "to_state": "STARTED"},
        {"aggregate": "attempt", "aggregate_id": "a", "from_state": "STARTED", "to_state": "RESULT_RECEIVED"},
        {"aggregate": "attempt", "aggregate_id": "a", "from_state": "RESULT_RECEIVED", "to_state": "RESULT_ACCEPTED"},
    ]
    states = project_states(facts)
    assert states[("attempt", "a")] == "RESULT_ACCEPTED"
    with pytest.raises(ValidationError, match="TERMINAL_STATE_IMMUTABLE"):
        project_states(facts + [{"aggregate": "attempt", "aggregate_id": "a",
                                "from_state": "RESULT_ACCEPTED", "to_state": "STARTED"}])
    with pytest.raises(ValidationError, match="RETRY_REUSES_ATTEMPT"):
        legal_transition("attempt", "CREATED", "STARTED", retry_of="a", attempt_id="a")


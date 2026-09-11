"""Fail-closed subset of the pinned TRANSITION_PROFILE_V1.

The module is deliberately a pure validator/projector.  It never stores a
mutable current state and therefore cannot become a second authority beside
the canonical accepted history.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError


class _State(str, Enum):
    def __str__(self):
        return self.value


class CampaignState(_State):
    CREATED = "CREATED"
    GENESIS_ACCEPTED = "GENESIS_ACCEPTED"
    E0_READY = "E0_READY"
    AUDIT_RUNNING = "AUDIT_RUNNING"
    E6_REQUIRED = "E6_REQUIRED"
    E6_RUNNING = "E6_RUNNING"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    CAMPAIGN_CONCLUDED = "CAMPAIGN_CONCLUDED"
    CLOSED = "CLOSED"


class StageRunState(_State):
    PLANNED = "PLANNED"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_FOR_REQUIRED_INPUT = "WAITING_FOR_REQUIRED_INPUT"
    COMPLETION_CANDIDATE = "COMPLETION_CANDIDATE"
    COMPLETION_ACCEPTED = "COMPLETION_ACCEPTED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class LaneRunState(_State):
    PLANNED = "PLANNED"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_RESULT = "WAITING_RESULT"
    COMPLETION_CANDIDATE = "COMPLETION_CANDIDATE"
    COMPLETION_ACCEPTED = "COMPLETION_ACCEPTED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class AttemptState(_State):
    CREATED = "CREATED"
    STARTED = "STARTED"
    RESULT_RECEIVED = "RESULT_RECEIVED"
    RESULT_ACCEPTED = "RESULT_ACCEPTED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


_EDGES = {
    "campaign": {
        ("CREATED", "GENESIS_ACCEPTED"),
        ("GENESIS_ACCEPTED", "E0_READY"),
        ("GENESIS_ACCEPTED", "BLOCKED"),
        ("GENESIS_ACCEPTED", "CANCELLED"),
        ("E0_READY", "AUDIT_RUNNING"),
        ("E0_READY", "BLOCKED"),
        ("E0_READY", "CANCELLED"),
        ("AUDIT_RUNNING", "AUDIT_RUNNING"),
        ("AUDIT_RUNNING", "BLOCKED"),
        ("AUDIT_RUNNING", "E6_REQUIRED"),
        ("AUDIT_RUNNING", "CAMPAIGN_CONCLUDED"),
        ("E6_REQUIRED", "E6_RUNNING"),
        ("E6_REQUIRED", "CAMPAIGN_CONCLUDED"),
        ("E6_RUNNING", "E6_REQUIRED"),
        ("E6_RUNNING", "AUDIT_RUNNING"),
        ("E6_RUNNING", "BLOCKED"),
        ("E6_RUNNING", "CAMPAIGN_CONCLUDED"),
        ("BLOCKED", "AUDIT_RUNNING"),
        ("BLOCKED", "CAMPAIGN_CONCLUDED"),
        ("CAMPAIGN_CONCLUDED", "CLOSED"),
    },
    "stage": {
        ("PLANNED", "READY"), ("PLANNED", "BLOCKED"), ("PLANNED", "CANCELLED"),
        ("READY", "RUNNING"), ("READY", "BLOCKED"), ("READY", "CANCELLED"),
        ("RUNNING", "WAITING_FOR_REQUIRED_INPUT"),
        ("WAITING_FOR_REQUIRED_INPUT", "RUNNING"),
        ("RUNNING", "COMPLETION_CANDIDATE"),
        ("WAITING_FOR_REQUIRED_INPUT", "COMPLETION_CANDIDATE"),
        ("RUNNING", "BLOCKED"), ("RUNNING", "CANCELLED"),
        ("WAITING_FOR_REQUIRED_INPUT", "BLOCKED"),
        ("WAITING_FOR_REQUIRED_INPUT", "CANCELLED"),
        ("COMPLETION_CANDIDATE", "COMPLETION_ACCEPTED"),
        ("COMPLETION_CANDIDATE", "RUNNING"),
        ("COMPLETION_CANDIDATE", "BLOCKED"),
    },
    "lane": {
        ("PLANNED", "READY"), ("PLANNED", "BLOCKED"), ("PLANNED", "CANCELLED"),
        ("READY", "RUNNING"), ("READY", "BLOCKED"), ("READY", "CANCELLED"),
        ("RUNNING", "WAITING_RESULT"), ("RUNNING", "COMPLETION_CANDIDATE"),
        ("RUNNING", "BLOCKED"), ("RUNNING", "CANCELLED"),
        ("WAITING_RESULT", "RUNNING"), ("WAITING_RESULT", "COMPLETION_CANDIDATE"),
        ("WAITING_RESULT", "BLOCKED"), ("WAITING_RESULT", "CANCELLED"),
        ("COMPLETION_CANDIDATE", "COMPLETION_ACCEPTED"),
        ("COMPLETION_CANDIDATE", "RUNNING"), ("COMPLETION_CANDIDATE", "BLOCKED"),
    },
    "attempt": {
        ("CREATED", "STARTED"), ("CREATED", "CANCELLED"), ("CREATED", "SUPERSEDED"),
        ("STARTED", "RESULT_RECEIVED"), ("STARTED", "FAILED"),
        ("STARTED", "BLOCKED"), ("STARTED", "CANCELLED"), ("STARTED", "SUPERSEDED"),
        ("RESULT_RECEIVED", "RESULT_ACCEPTED"), ("RESULT_RECEIVED", "FAILED"),
        ("RESULT_RECEIVED", "BLOCKED"), ("RESULT_RECEIVED", "SUPERSEDED"),
    },
}

_TERMINAL = {
    "campaign": {"CANCELLED", "CLOSED"},
    "stage": {"COMPLETION_ACCEPTED", "BLOCKED", "CANCELLED", "SUPERSEDED"},
    "lane": {"COMPLETION_ACCEPTED", "BLOCKED", "CANCELLED", "SUPERSEDED"},
    "attempt": {"RESULT_ACCEPTED", "FAILED", "BLOCKED", "CANCELLED", "SUPERSEDED"},
}


@dataclass(frozen=True)
class TransitionFact:
    aggregate: str
    aggregate_id: str
    from_state: str
    to_state: str
    transition_policy_ref: str
    input_history_cut: Mapping
    evidence_refs: tuple[Mapping, ...] = ()
    event_id: str | None = None

    def __post_init__(self):
        if self.aggregate not in _EDGES:
            raise ValidationError("UNKNOWN_FSM_AGGREGATE")
        legal_transition(self.aggregate, self.from_state, self.to_state)
        if not self.aggregate_id or not self.transition_policy_ref:
            raise ValidationError("TRANSITION_CONTEXT_REQUIRED")
        if not isinstance(self.input_history_cut, Mapping):
            raise ValidationError("TRANSITION_HISTORY_CUT_REQUIRED")
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))


def _value(value):
    return value.value if isinstance(value, Enum) else value


def legal_transition(aggregate: str, from_state, to_state, *, event_kind=None,
                     retry_of=None, attempt_id=None):
    aggregate = aggregate.lower()
    from_state, to_state = _value(from_state), _value(to_state)
    if aggregate not in _EDGES:
        raise ValidationError("UNKNOWN_FSM_AGGREGATE")
    if event_kind == "AttemptResult" and aggregate == "lane":
        raise ValidationError("LANE_COMPLETION_REQUIRES_LANE_FACT")
    if from_state in _TERMINAL[aggregate] and from_state != to_state:
        raise ValidationError("TERMINAL_STATE_IMMUTABLE")
    if (from_state, to_state) not in _EDGES[aggregate]:
        raise ValidationError("ILLEGAL_STATE_TRANSITION")
    if aggregate == "campaign" and from_state == "CREATED" and to_state != "GENESIS_ACCEPTED":
        raise ValidationError("GENESIS_GATE_REQUIRED")
    if aggregate == "stage" and from_state == "PLANNED" and to_state == "RUNNING":
        raise ValidationError("E0_READY_CANNOT_BE_SKIPPED")
    if aggregate == "lane" and from_state == "PLANNED" and to_state == "RUNNING":
        raise ValidationError("LANE_READY_CANNOT_BE_SKIPPED")
    if aggregate == "attempt" and retry_of is not None and attempt_id == retry_of:
        raise ValidationError("RETRY_REUSES_ATTEMPT")
    return True


def project_states(facts: Iterable[TransitionFact | Mapping], *, initial=None):
    """Derive current states from accepted transition facts in sequence order."""
    states = dict(initial or {"campaign": "CREATED"})
    seen_terminal = set()
    for fact in facts:
        if isinstance(fact, TransitionFact):
            aggregate, aggregate_id = fact.aggregate, fact.aggregate_id
            before, after = fact.from_state, fact.to_state
            payload = None
        else:
            payload = fact
            aggregate = str(fact.get("aggregate", "")).lower()
            aggregate_id = fact.get("aggregate_id") or fact.get("id")
            before, after = fact.get("from_state"), fact.get("to_state")
            if not aggregate_id or before is None or after is None:
                raise ValidationError("TRANSITION_FACT_INCOMPLETE")
            legal_transition(aggregate, before, after,
                             event_kind=fact.get("event_kind"),
                             retry_of=fact.get("retry_of"), attempt_id=fact.get("attempt_id"))
        key = (aggregate, aggregate_id)
        if key in seen_terminal:
            # Duplicate exact event is idempotent; any attempted rewrite is not.
            if states.get(key) == after:
                continue
            raise ValidationError("TERMINAL_STATE_IMMUTABLE")
        defaults = {"campaign": "CREATED", "stage": "PLANNED", "lane": "PLANNED", "attempt": "CREATED"}
        current = states.get(key, defaults[aggregate])
        if current != before:
            raise ValidationError("STALE_TRANSITION_PARENT")
        states[key] = after
        if after in _TERMINAL.get(aggregate, set()):
            seen_terminal.add(key)
    return states


__all__ = [
    "CampaignState", "StageRunState", "LaneRunState", "AttemptState",
    "TransitionFact", "legal_transition", "project_states",
]

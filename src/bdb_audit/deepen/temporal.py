"""Temporal Invariant Engine (WP-E4-02 / M29 / Data Contracts §72).

Implements:
- OrderingConstraint: before/after, must-eventually-follow, must-never-follow, strict-order, bounded-follow.
- TemporalInvariant: binding to StateModel and explicit HistoryCut.
- Evaluation over ordered traces with clear separation of expected rule vs observed sequence.
- Violations produce Observations / Evidence input, strictly NOT bypassing to Finding.
- Statuses: PROPOSED, MODEL_VERIFIED, IMPLEMENTATION_CONFORMANCE_QUALIFIED, VIOLATED, BLOCKED.
"""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence
from uuid import uuid4

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id
from ..evidence.models import Observation


VALID_RELATIONS = {
    "BEFORE",
    "AFTER",
    "MUST_EVENTUALLY_FOLLOW",
    "MUST_NEVER_FOLLOW",
    "STRICT_ORDER",
    "BOUNDED_FOLLOW",
}

VALID_STATUSES = {
    "PROPOSED",
    "MODEL_VERIFIED",
    "IMPLEMENTATION_CONFORMANCE_QUALIFIED",
    "VIOLATED",
    "BLOCKED",
}


@dataclass(frozen=True)
class OrderingConstraint:
    constraint_id: str
    relation: str  # BEFORE, AFTER, MUST_EVENTUALLY_FOLLOW, MUST_NEVER_FOLLOW, STRICT_ORDER, BOUNDED_FOLLOW
    event_a: str = ""
    event_b: str = ""
    sequence: tuple[str, ...] = ()
    max_steps: int | None = None
    description: str = ""

    def __post_init__(self):
        if self.relation not in VALID_RELATIONS:
            raise ValidationError("INVALID_RELATION", f"Unknown relation: {self.relation}")
        if self.relation == "STRICT_ORDER" and len(self.sequence) < 2:
            raise ValidationError("INVALID_SEQUENCE", "STRICT_ORDER requires at least 2 events")
        if self.relation in ("BEFORE", "AFTER", "MUST_EVENTUALLY_FOLLOW", "MUST_NEVER_FOLLOW"):
            if not self.event_a or not self.event_b:
                raise ValidationError("MISSING_EVENTS", f"{self.relation} requires event_a and event_b")
        if self.relation == "BOUNDED_FOLLOW":
            if not self.event_a or not self.event_b:
                raise ValidationError("MISSING_EVENTS", "BOUNDED_FOLLOW requires event_a and event_b")
            if self.max_steps is None or self.max_steps < 1:
                raise ValidationError("INVALID_BOUND", "BOUNDED_FOLLOW requires max_steps >= 1")

    def _extract_event(self, item: Any) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, dict) and "event" in item:
            return str(item["event"])
        return str(item)

    def evaluate(self, trace: Sequence[Any]) -> tuple[bool, str | None, dict[str, Any] | None]:
        events = [self._extract_event(it) for it in trace]

        if self.relation == "BEFORE":
            # event_a must occur before event_b. If event_b occurs, event_a must appear before it.
            # If event_b occurs without prior event_a -> VIOLATION.
            seen_a = False
            for idx, ev in enumerate(events):
                if ev == self.event_a:
                    seen_a = True
                elif ev == self.event_b:
                    if not seen_a:
                        return (
                            False,
                            f"Event '{self.event_b}' occurred at step {idx} before prerequisite '{self.event_a}'",
                            {"step": idx, "event": ev, "required_prerequisite": self.event_a},
                        )
            return True, None, None

        elif self.relation == "AFTER":
            # event_a must occur after event_b (synonymous with event_b before event_a)
            seen_b = False
            for idx, ev in enumerate(events):
                if ev == self.event_b:
                    seen_b = True
                elif ev == self.event_a:
                    if not seen_b:
                        return (
                            False,
                            f"Event '{self.event_a}' occurred at step {idx} before prerequisite '{self.event_b}'",
                            {"step": idx, "event": ev, "required_prerequisite": self.event_b},
                        )
            return True, None, None

        elif self.relation == "MUST_EVENTUALLY_FOLLOW":
            # Whenever event_a occurs, event_b must occur at some later step.
            for idx, ev in enumerate(events):
                if ev == self.event_a:
                    # Check if event_b occurs anywhere after idx
                    if not any(e == self.event_b for e in events[idx + 1 :]):
                        return (
                            False,
                            f"Event '{self.event_a}' at step {idx} was not eventually followed by '{self.event_b}'",
                            {"step": idx, "event": ev, "missing_followup": self.event_b},
                        )
            return True, None, None

        elif self.relation == "MUST_NEVER_FOLLOW":
            # Whenever event_a occurs, event_b must NEVER occur at any later step.
            for idx, ev in enumerate(events):
                if ev == self.event_a:
                    for later_idx in range(idx + 1, len(events)):
                        if events[later_idx] == self.event_b:
                            return (
                                False,
                                f"Forbidden followup '{self.event_b}' occurred at step {later_idx} after '{self.event_a}' at step {idx}",
                                {"trigger_step": idx, "violation_step": later_idx, "forbidden_event": self.event_b},
                            )
            return True, None, None

        elif self.relation == "STRICT_ORDER":
            # Sequence [s0, s1, ..., sn] must appear in order
            seq_idx = 0
            for idx, ev in enumerate(events):
                if ev == self.sequence[seq_idx]:
                    seq_idx += 1
                    if seq_idx == len(self.sequence):
                        break
            if seq_idx < len(self.sequence):
                return (
                    False,
                    f"Strict order not satisfied: expected '{self.sequence[seq_idx]}' at sequence position {seq_idx}",
                    {"missing_sequence_element": self.sequence[seq_idx], "matched_prefix_count": seq_idx},
                )
            return True, None, None

        elif self.relation == "BOUNDED_FOLLOW":
            # Whenever event_a occurs, event_b must occur within max_steps.
            assert self.max_steps is not None
            for idx, ev in enumerate(events):
                if ev == self.event_a:
                    window = events[idx + 1 : idx + 1 + self.max_steps]
                    if not any(e == self.event_b for e in window):
                        return (
                            False,
                            f"Event '{self.event_a}' at step {idx} was not followed by '{self.event_b}' within {self.max_steps} steps",
                            {"trigger_step": idx, "max_steps": self.max_steps, "required_event": self.event_b},
                        )
            return True, None, None

        return True, None, None

    def body(self) -> dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "relation": self.relation,
            "event_a": self.event_a,
            "event_b": self.event_b,
            "sequence": list(self.sequence),
            "max_steps": self.max_steps,
            "description": self.description,
        }


class TemporalInvariant:
    def __init__(
        self,
        invariant_id: str,
        revision: int,
        scope: str,
        state_model_ref: dict[str, Any],
        constraints: Sequence[OrderingConstraint],
        history_cut: dict[str, Any],
        status: str = "PROPOSED",
        assumptions: Sequence[str] = (),
        predecessor_ref: dict[str, Any] | None = None,
    ):
        if status not in VALID_STATUSES:
            raise ValidationError("INVALID_STATUS", f"Unknown temporal invariant status: {status}")
        self.invariant_id = invariant_id
        self.revision = int(revision)
        self.scope = scope
        self.state_model_ref = dict(state_model_ref)
        self.constraints = tuple(constraints)
        self.history_cut = dict(history_cut)
        self.status = status
        self.assumptions = tuple(assumptions)
        self.predecessor_ref = dict(predecessor_ref) if predecessor_ref else None

    def evaluate_trace(
        self, trace: Sequence[Any], history_cut: dict[str, Any] | None = None
    ) -> tuple[str, list[dict[str, Any]]]:
        if history_cut is not None and history_cut != self.history_cut:
            raise ValidationError(
                "STALE_HISTORY_CUT",
                f"Trace history cut {history_cut} does not match invariant cut {self.history_cut}",
            )

        violations = []
        for c in self.constraints:
            passed, reason, details = c.evaluate(trace)
            if not passed:
                violations.append(
                    {
                        "constraint_id": c.constraint_id,
                        "relation": c.relation,
                        "reason": reason,
                        "details": details,
                    }
                )

        if violations:
            return "VIOLATED", violations
        return "SATISFIED", []

    def create_observation_on_violation(
        self,
        violations: Sequence[dict[str, Any]],
        execution_descriptor_ref: Any = None,
        raw_observation_ref: Any = None,
        observation_channel: str = "TEMPORAL_INVARIANT_ENGINE",
        observed_at: str = "2026-09-11T12:00:00Z",
    ) -> Observation:
        """Create canonical Observation from temporal violation.

        Violation is an observation/evidence input, NEVER directly a finding.
        """
        obs_id = new_id("observation")
        raw_ref = raw_observation_ref or {
            "invariant_id": self.invariant_id,
            "revision": self.revision,
            "scope": self.scope,
            "state_model_ref": self.state_model_ref,
            "violations": list(violations),
        }
        exec_ref = execution_descriptor_ref or {
            "execution_descriptor_id": new_id("execution_descriptor"),
            "target": self.scope,
        }
        return Observation(
            observation_id=obs_id,
            execution_descriptor_ref=exec_ref,
            raw_observation_ref=raw_ref,
            observation_channel=observation_channel,
            observed_at=observed_at,
        )

    def body(self) -> dict[str, Any]:
        return {
            "invariant_id": self.invariant_id,
            "revision": self.revision,
            "scope": self.scope,
            "state_model_ref": dict(self.state_model_ref),
            "constraints": [c.body() for c in sorted(self.constraints, key=lambda x: x.constraint_id)],
            "history_cut": dict(self.history_cut),
            "status": self.status,
            "assumptions": list(self.assumptions),
            "predecessor_ref": dict(self.predecessor_ref) if self.predecessor_ref else None,
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()

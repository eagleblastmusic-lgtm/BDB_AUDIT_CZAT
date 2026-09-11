"""Bounded Model Exploration Engine (WP-E4-04 / M31 / §88).

Implements:
- Small state space systematic exploration with explicit limits.
- Bounded traversal: max_states, max_depth, max_transitions.
- Cycle detection to guarantee termination.
- Exact outcome classification:
  - EXHAUSTED_WITHIN_BOUND
  - BOUND_REACHED
  - FORBIDDEN_STATE_FOUND
  - INVALID_MODEL
- Replayable counterexample trace extraction when forbidden state is reached.
- Proof scoping: unencountered bug in bounded space is explicitly NOT global correctness proof.
"""
from collections import deque
from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence
from uuid import uuid4

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id
from ..evidence.models import Observation
from .state_model import StateModel, ForbiddenState


EXPLORATION_STATUSES = {
    "EXHAUSTED_WITHIN_BOUND",
    "BOUND_REACHED",
    "FORBIDDEN_STATE_FOUND",
    "INVALID_MODEL",
}


@dataclass(frozen=True)
class ExplorationBounds:
    max_states: int = 100
    max_depth: int = 20
    max_transitions: int = 500

    def body(self) -> dict[str, Any]:
        return {
            "max_states": self.max_states,
            "max_depth": self.max_depth,
            "max_transitions": self.max_transitions,
        }


@dataclass(frozen=True)
class ExplorationResult:
    result_id: str
    model_ref: dict[str, Any]
    status: str  # EXHAUSTED_WITHIN_BOUND, BOUND_REACHED, FORBIDDEN_STATE_FOUND, INVALID_MODEL
    states_visited: int
    transitions_explored: int
    max_depth_reached: int
    termination_reason: str
    counterexample_trace: tuple[tuple[str, Any], ...] = ()
    forbidden_state_hit: str | None = None
    bounds: ExplorationBounds = field(default_factory=ExplorationBounds)

    def body(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "model_ref": dict(self.model_ref),
            "status": self.status,
            "states_visited": self.states_visited,
            "transitions_explored": self.transitions_explored,
            "max_depth_reached": self.max_depth_reached,
            "termination_reason": self.termination_reason,
            "counterexample_trace": [list(x) for x in self.counterexample_trace],
            "forbidden_state_hit": self.forbidden_state_hit,
            "bounds": self.bounds.body(),
        }


class BoundedModelExplorer:
    def __init__(self, bounds: ExplorationBounds | None = None):
        self.bounds = bounds or ExplorationBounds()

    def explore(
        self,
        model: StateModel,
        initial_state: str | None = None,
        bounds: ExplorationBounds | None = None,
    ) -> ExplorationResult:
        active_bounds = bounds or self.bounds
        res_id = new_id("execution_result")
        model_ref = {
            "model_id": getattr(model, "model_id", "unknown"),
            "revision": getattr(model, "model_revision", 1),
            "digest": getattr(model, "model_hash", lambda: "none")(),
        }

        # Validate model structure
        if not hasattr(model, "states") or not hasattr(model, "transitions"):
            return ExplorationResult(
                result_id=res_id,
                model_ref=model_ref,
                status="INVALID_MODEL",
                states_visited=0,
                transitions_explored=0,
                max_depth_reached=0,
                termination_reason="Model lacks required states or transitions",
                bounds=active_bounds,
            )

        start_state = initial_state or (model.initial_states[0] if model.initial_states else None)
        if not start_state or start_state not in model.states:
            return ExplorationResult(
                result_id=res_id,
                model_ref=model_ref,
                status="INVALID_MODEL",
                states_visited=0,
                transitions_explored=0,
                max_depth_reached=0,
                termination_reason=f"Invalid start state: {start_state}",
                bounds=active_bounds,
            )

        # Check if initial state is forbidden
        for fs in model.forbidden_states:
            if fs.matches(start_state, model.state_variables):
                return ExplorationResult(
                    result_id=res_id,
                    model_ref=model_ref,
                    status="FORBIDDEN_STATE_FOUND",
                    states_visited=1,
                    transitions_explored=0,
                    max_depth_reached=0,
                    termination_reason=f"Initial state matches forbidden state {fs.forbidden_id}",
                    counterexample_trace=(),
                    forbidden_state_hit=fs.forbidden_id,
                    bounds=active_bounds,
                )

        # BFS queue: (state_name, state_vars, depth, trace_so_far)
        init_vars = dict(model.state_variables)
        queue = deque([(start_state, init_vars, 0, [])])
        
        # Visited configurations: (state_name, canonical tuple of vars)
        visited = {self._config_key(start_state, init_vars)}
        
        transitions_count = 0
        max_depth_seen = 0
        bound_hit_reason = None

        while queue:
            curr_state, curr_vars, depth, path = queue.popleft()
            max_depth_seen = max(max_depth_seen, depth)

            if len(visited) >= active_bounds.max_states:
                bound_hit_reason = f"Max states limit reached ({active_bounds.max_states})"
                break

            if depth >= active_bounds.max_depth:
                bound_hit_reason = f"Max depth limit reached ({active_bounds.max_depth})"
                continue  # bounded BFS: don't expand deeper

            # Get outgoing transitions
            available_transitions = [
                tr for tr in model.transitions if tr.source_state == curr_state
            ]

            for tr in available_transitions:
                transitions_count += 1
                if transitions_count > active_bounds.max_transitions:
                    bound_hit_reason = f"Max transitions limit reached ({active_bounds.max_transitions})"
                    break

                # Evaluate guards
                guards_ok = True
                for g in tr.guards:
                    if not g.evaluate(curr_vars, None):
                        guards_ok = False
                        break
                if not guards_ok:
                    continue

                # Compute next vars
                if tr.effect is not None:
                    next_vars = dict(tr.effect(dict(curr_vars), None))
                else:
                    next_vars = dict(curr_vars)

                next_state = tr.target_state
                next_path = path + [(tr.event, None)]

                # Check forbidden states
                for fs in model.forbidden_states:
                    if fs.matches(next_state, next_vars):
                        return ExplorationResult(
                            result_id=res_id,
                            model_ref=model_ref,
                            status="FORBIDDEN_STATE_FOUND",
                            states_visited=len(visited),
                            transitions_explored=transitions_count,
                            max_depth_reached=max(max_depth_seen, depth + 1),
                            termination_reason=f"Forbidden state {fs.forbidden_id} reached: {fs.reason}",
                            counterexample_trace=tuple(next_path),
                            forbidden_state_hit=fs.forbidden_id,
                            bounds=active_bounds,
                        )

                config_key = self._config_key(next_state, next_vars)
                if config_key not in visited:
                    visited.add(config_key)
                    queue.append((next_state, next_vars, depth + 1, next_path))

            if bound_hit_reason and transitions_count > active_bounds.max_transitions:
                break

        if bound_hit_reason:
            status = "BOUND_REACHED"
            reason = bound_hit_reason
        else:
            status = "EXHAUSTED_WITHIN_BOUND"
            reason = "State space fully explored within bounds"

        return ExplorationResult(
            result_id=res_id,
            model_ref=model_ref,
            status=status,
            states_visited=len(visited),
            transitions_explored=transitions_count,
            max_depth_reached=max_depth_seen,
            termination_reason=reason,
            bounds=active_bounds,
        )

    def _config_key(self, state: str, vars_dict: dict[str, Any]) -> tuple[str, tuple[tuple[str, Any], ...]]:
        sorted_vars = tuple(sorted((k, repr(v)) for k, v in vars_dict.items()))
        return (state, sorted_vars)

    def to_observation(
        self,
        result: ExplorationResult,
        execution_descriptor_ref: Any = None,
    ) -> Observation:
        exec_ref = execution_descriptor_ref or {
            "execution_descriptor_id": new_id("execution_descriptor"),
            "engine": "BOUNDED_MODEL_EXPLORER",
        }
        return Observation(
            observation_id=new_id("observation"),
            execution_descriptor_ref=exec_ref,
            raw_observation_ref=result.body(),
            observation_channel="BOUNDED_MODEL_EXPLORATION",
            observed_at="2026-09-11T12:00:00Z",
        )

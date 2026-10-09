"""Property and Stateful Adapter Framework (WP-E4-03 / M30 / Data Contracts §33, §71).

Implements:
- PropertyTestAdapter: generates/executes property-based workloads bound to policy/invariant sources.
- StatefulTestAdapter: generates/executes action sequences bound to M28 StateModel.
- AdapterCapability: strict capability limits (max operations, timeout, allowed commands).
- Deterministic seed identity and replayability.
- Derived trace shrinking / counterexample minimization.
- Cleanup guarantees even on failure.
- Output is strictly Observation/evidence input, never a direct finding shortcut.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import hashlib
import random
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id
from ..evidence.models import Observation
from .state_model import StateModel


@dataclass(frozen=True)
class AdapterCapability:
    max_operations: int = 100
    timeout_seconds: float = 10.0
    allowed_commands: tuple[str, ...] = ("ALL",)
    max_depth: int = 50
    deterministic_seed_required: bool = True

    def validate_operation_count(self, count: int) -> None:
        if count > self.max_operations:
            raise ValidationError(
                "CAPABILITY_LIMIT_EXCEEDED",
                f"Operation count {count} exceeds capability maximum {self.max_operations}",
            )

    def validate_command(self, command: str) -> None:
        if "ALL" not in self.allowed_commands and command not in self.allowed_commands:
            raise ValidationError(
                "CAPABILITY_UNAUTHORIZED_COMMAND",
                f"Command '{command}' not in allowed capability set {self.allowed_commands}",
            )


@dataclass(frozen=True)
class PropertyTestResult:
    result_id: str
    seed: int
    cases_tested: int
    passed: bool
    failing_input: Any | None = None
    shrunk_input: Any | None = None
    policy_ref: dict[str, Any] = field(default_factory=dict)
    cleanup_executed: bool = False

    def body(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "seed": self.seed,
            "cases_tested": self.cases_tested,
            "passed": self.passed,
            "failing_input": str(self.failing_input) if self.failing_input is not None else None,
            "shrunk_input": str(self.shrunk_input) if self.shrunk_input is not None else None,
            "policy_ref": dict(self.policy_ref),
            "cleanup_executed": self.cleanup_executed,
        }


@dataclass(frozen=True)
class StatefulTestResult:
    result_id: str
    seed: int
    initial_state: str
    final_state: str
    steps_executed: int
    passed: bool
    failing_step: int | None = None
    failing_action: tuple[str, Any] | None = None
    shrunk_trace: tuple[tuple[str, Any], ...] = ()
    state_model_ref: dict[str, Any] = field(default_factory=dict)
    cleanup_executed: bool = False

    def body(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "seed": self.seed,
            "initial_state": self.initial_state,
            "final_state": self.final_state,
            "steps_executed": self.steps_executed,
            "passed": self.passed,
            "failing_step": self.failing_step,
            "failing_action": list(self.failing_action) if self.failing_action else None,
            "shrunk_trace": [list(x) for x in self.shrunk_trace],
            "state_model_ref": dict(self.state_model_ref),
            "cleanup_executed": self.cleanup_executed,
        }


class PropertyTestAdapter:
    def __init__(
        self,
        adapter_id: str,
        target_ref: dict[str, Any],
        policy_ref: dict[str, Any],
        capability: AdapterCapability | None = None,
    ):
        self.adapter_id = adapter_id
        self.target_ref = dict(target_ref)
        self.policy_ref = dict(policy_ref)
        self.capability = capability or AdapterCapability()

    def run_property_test(
        self,
        seed: int,
        count: int,
        generator: Callable[[random.Random], Any],
        property_fn: Callable[[Any], bool],
        cleanup_fn: Callable[[], None] | None = None,
    ) -> PropertyTestResult:
        self.capability.validate_operation_count(count)
        if type(count) is not int or count <= 0:
            raise ValidationError(
                "PROPERTY_TEST_NO_CASES",
                "Property qualification requires at least one executed case",
            )
        rng = random.Random(seed)
        cleanup_done = False
        failure_observed = False
        failing_input: Any | None = None
        shrunk_input: Any | None = None
        cases_tested = 0

        try:
            for _ in range(count):
                cases_tested += 1
                inp = generator(rng)
                is_valid = property_fn(inp)
                if not is_valid:
                    # ``None`` is a legal generated value and therefore cannot
                    # double as the sentinel for "no counterexample observed".
                    failure_observed = True
                    failing_input = inp
                    shrunk_input = self._shrink_input(inp, property_fn)
                    break
        finally:
            if cleanup_fn is not None:
                cleanup_fn()
                cleanup_done = True
            else:
                cleanup_done = True

        return PropertyTestResult(
            result_id=new_id("execution_result"),
            seed=seed,
            cases_tested=cases_tested,
            passed=not failure_observed,
            failing_input=failing_input,
            shrunk_input=shrunk_input,
            policy_ref=self.policy_ref,
            cleanup_executed=cleanup_done,
        )

    def _shrink_input(self, failing_input: Any, property_fn: Callable[[Any], bool]) -> Any:
        """Derived minimization: simple deterministic binary/linear shrinking."""
        if isinstance(failing_input, int):
            curr = failing_input
            candidates = [0, curr // 2, curr - 1]
            for cand in candidates:
                if 0 <= cand < curr and not property_fn(cand):
                    return self._shrink_input(cand, property_fn)
            return curr
        elif isinstance(failing_input, list):
            curr = list(failing_input)
            for i in range(len(curr)):
                smaller = curr[:i] + curr[i + 1 :]
                if not property_fn(smaller):
                    return self._shrink_input(smaller, property_fn)
            return curr
        return failing_input

    def to_observation(
        self,
        result: PropertyTestResult,
        execution_descriptor_ref: Any = None,
    ) -> Observation:
        exec_ref = execution_descriptor_ref or {
            "execution_descriptor_id": new_id("execution_descriptor"),
            "adapter_id": self.adapter_id,
        }
        return Observation(
            observation_id=new_id("observation"),
            execution_descriptor_ref=exec_ref,
            raw_observation_ref=result.body(),
            observation_channel="PROPERTY_TEST_ADAPTER",
            observed_at="2026-09-11T12:00:00Z",
        )


class StatefulTestAdapter:
    def __init__(
        self,
        adapter_id: str,
        target_ref: dict[str, Any],
        state_model: StateModel,
        capability: AdapterCapability | None = None,
    ):
        self.adapter_id = adapter_id
        self.target_ref = dict(target_ref)
        self.state_model = state_model
        self.capability = capability or AdapterCapability()

    def generate_sequence(self, seed: int, length: int) -> list[tuple[str, Any]]:
        self.capability.validate_operation_count(length)
        rng = random.Random(seed)
        events = sorted({tr.event for tr in self.state_model.transitions})
        if not events:
            return []

        seq: list[tuple[str, Any]] = []
        for _ in range(length):
            ev = rng.choice(events)
            self.capability.validate_command(ev)
            seq.append((ev, None))
        return seq

    def execute_stateful_test(
        self,
        seed: int,
        initial_state: str,
        sequence: Sequence[tuple[str, Any]],
        system_under_test: Any,
        cleanup_fn: Callable[[], None] | None = None,
    ) -> StatefulTestResult:
        self.capability.validate_operation_count(len(sequence))
        cleanup_done = False
        current_state = initial_state
        steps_executed = 0
        passed = True
        failing_step = None
        failing_action = None
        shrunk_trace: list[tuple[str, Any]] = []

        try:
            for idx, (event, ctx) in enumerate(sequence):
                self.capability.validate_command(event)
                try:
                    # Step model to get expected legal transition
                    next_model_state, _ = self.state_model.step(current_state, event, context=ctx)
                    # Step system under test
                    sut_state = system_under_test.step(event, ctx)
                    steps_executed += 1

                    if sut_state != next_model_state:
                        # Divergence between SUT and StateModel
                        passed = False
                        failing_step = idx
                        failing_action = (event, ctx)
                        shrunk_trace = self._shrink_trace(
                            initial_state, sequence[: idx + 1], system_under_test
                        )
                        break
                    current_state = next_model_state

                except Exception:
                    passed = False
                    failing_step = idx
                    failing_action = (event, ctx)
                    shrunk_trace = self._shrink_trace(
                        initial_state, sequence[: idx + 1], system_under_test
                    )
                    break

        finally:
            if cleanup_fn is not None:
                cleanup_fn()
                cleanup_done = True
            else:
                cleanup_done = True

        model_ref = {
            "model_id": self.state_model.model_id,
            "revision": self.state_model.model_revision,
            "digest": self.state_model.model_hash(),
        }

        return StatefulTestResult(
            result_id=new_id("execution_result"),
            seed=seed,
            initial_state=initial_state,
            final_state=current_state,
            steps_executed=steps_executed,
            passed=passed,
            failing_step=failing_step,
            failing_action=failing_action,
            shrunk_trace=tuple(shrunk_trace),
            state_model_ref=model_ref,
            cleanup_executed=cleanup_done,
        )

    def _shrink_trace(
        self,
        initial_state: str,
        failing_prefix: Sequence[tuple[str, Any]],
        system_under_test: Any,
    ) -> list[tuple[str, Any]]:
        """Minimizes failing prefix by removing non-essential actions."""
        curr = list(failing_prefix)
        if len(curr) <= 1:
            return curr

        # Try 1-element removals
        for i in range(len(curr) - 1):  # keep last action which triggered failure
            candidate = curr[:i] + curr[i + 1 :]
            if self._reproduces_failure(initial_state, candidate, system_under_test):
                return self._shrink_trace(initial_state, candidate, system_under_test)

        return curr

    def _reproduces_failure(
        self,
        initial_state: str,
        trace: Sequence[tuple[str, Any]],
        system_under_test: Any,
    ) -> bool:
        if hasattr(system_under_test, "reset"):
            system_under_test.reset()
        st = initial_state
        for ev, ctx in trace:
            try:
                nxt_model, _ = self.state_model.step(st, ev, context=ctx)
                sut_st = system_under_test.step(ev, ctx)
                if sut_st != nxt_model:
                    return True
                st = nxt_model
            except Exception:
                return True
        return False

    def to_observation(
        self,
        result: StatefulTestResult,
        execution_descriptor_ref: Any = None,
    ) -> Observation:
        exec_ref = execution_descriptor_ref or {
            "execution_descriptor_id": new_id("execution_descriptor"),
            "adapter_id": self.adapter_id,
        }
        return Observation(
            observation_id=new_id("observation"),
            execution_descriptor_ref=exec_ref,
            raw_observation_ref=result.body(),
            observation_channel="STATEFUL_TEST_ADAPTER",
            observed_at="2026-09-11T12:00:00Z",
        )

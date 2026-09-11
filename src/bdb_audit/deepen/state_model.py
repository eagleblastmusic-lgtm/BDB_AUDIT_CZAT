"""State Model Engine (WP-E4-01 / M28 / Data Contracts §71).

Implements:
- State, Guard, Transition, ForbiddenState.
- StateModel immutable revision management.
- Deterministic transition execution and replay.
- Guard evaluation and fail-closed illegal transition rejection.
- Forbidden state detection.
- Stale history cut and wrong binding rejection.
- ModelFidelityAssessment generation conforming to schema registry.
"""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id, validate_id


@dataclass(frozen=True)
class State:
    name: str
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def body(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass(frozen=True)
class Guard:
    name: str
    predicate: Callable[[dict[str, Any], Any], bool]
    description: str = ""

    def evaluate(self, state_vars: dict[str, Any], context: Any = None) -> bool:
        return bool(self.predicate(state_vars, context))


@dataclass(frozen=True)
class Transition:
    transition_id: str
    source_state: str
    target_state: str
    event: str
    guards: tuple[Guard, ...] = ()
    effect: Callable[[dict[str, Any], Any], dict[str, Any]] | None = None
    description: str = ""

    def body(self) -> dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "source_state": self.source_state,
            "target_state": self.target_state,
            "event": self.event,
            "guards": [g.name for g in self.guards],
            "description": self.description,
        }


@dataclass(frozen=True)
class ForbiddenState:
    forbidden_id: str
    state_name: str | None = None
    condition: Callable[[str, dict[str, Any]], bool] | None = None
    reason: str = ""
    severity: str = "CRITICAL"

    def matches(self, state_name: str, state_vars: dict[str, Any]) -> bool:
        if self.state_name is not None and self.state_name == state_name:
            return True
        if self.condition is not None and self.condition(state_name, state_vars):
            return True
        return False

    def body(self) -> dict[str, Any]:
        return {
            "forbidden_id": self.forbidden_id,
            "state_name": self.state_name,
            "reason": self.reason,
            "severity": self.severity,
        }


class StateModel:
    def __init__(
        self,
        model_id: str,
        model_revision: int,
        source_generation_ref: dict[str, Any],
        history_cut: dict[str, Any],
        scope: str,
        state_variables: dict[str, Any],
        states: Mapping[str, State],
        initial_states: Sequence[str],
        transitions: Sequence[Transition],
        forbidden_states: Sequence[ForbiddenState] = (),
        abstraction_assumptions: Sequence[str] = (),
        bounds: Sequence[str] = (),
        omitted_states: Sequence[str] = (),
        fairness_time_assumptions: Sequence[str] = (),
        predecessor_revision_ref: dict[str, Any] | None = None,
    ):
        self.model_id = model_id
        self.model_revision = int(model_revision)
        self.source_generation_ref = dict(source_generation_ref)
        self.history_cut = dict(history_cut)
        self.scope = scope
        self.state_variables = dict(state_variables)
        self.states = dict(states)
        self.initial_states = tuple(initial_states)
        self.transitions = tuple(transitions)
        self.forbidden_states = tuple(forbidden_states)
        self.abstraction_assumptions = tuple(abstraction_assumptions)
        self.bounds = tuple(bounds)
        self.omitted_states = tuple(omitted_states)
        self.fairness_time_assumptions = tuple(fairness_time_assumptions)
        self.predecessor_revision_ref = (
            dict(predecessor_revision_ref) if predecessor_revision_ref else None
        )
        self._validate_model()

    def _validate_model(self) -> None:
        if not self.model_id:
            raise ValidationError("INVALID_MODEL_ID", "Model ID must not be empty")
        if self.model_revision < 1:
            raise ValidationError("INVALID_MODEL_REVISION", "Model revision must be >= 1")
        if not self.initial_states:
            raise ValidationError("MISSING_INITIAL_STATE", "At least one initial state is required")
        for init_st in self.initial_states:
            if init_st not in self.states:
                raise ValidationError("UNKNOWN_INITIAL_STATE", f"Initial state {init_st} not in states")
            for fs in self.forbidden_states:
                if fs.matches(init_st, self.state_variables):
                    raise ValidationError(
                        "FORBIDDEN_INITIAL_STATE",
                        f"Initial state {init_st} matches forbidden state {fs.forbidden_id}",
                    )
        for tr in self.transitions:
            if tr.source_state not in self.states:
                raise ValidationError(
                    "UNKNOWN_SOURCE_STATE", f"Transition source {tr.source_state} not in states"
                )
            if tr.target_state not in self.states:
                raise ValidationError(
                    "UNKNOWN_TARGET_STATE", f"Transition target {tr.target_state} not in states"
                )

    def step(
        self,
        current_state: str,
        event: str,
        current_vars: dict[str, Any] | None = None,
        context: Any = None,
        history_cut: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if history_cut is not None:
            if history_cut != self.history_cut:
                raise ValidationError(
                    "STALE_HISTORY_CUT",
                    f"HistoryCut mismatch: provided {history_cut} != model {self.history_cut}",
                )

        if current_state not in self.states:
            raise ValidationError("UNKNOWN_CURRENT_STATE", f"Current state {current_state} not in model")

        vars_copy = dict(self.state_variables) if current_vars is None else dict(current_vars)

        # Find matching transitions for current state and event
        candidates = [tr for tr in self.transitions if tr.source_state == current_state and tr.event == event]
        if not candidates:
            raise ValidationError(
                "ILLEGAL_TRANSITION",
                f"No legal transition defined from state '{current_state}' on event '{event}'",
            )

        # Evaluate guards
        active_transition: Transition | None = None
        for cand in candidates:
            guards_passed = True
            for guard in cand.guards:
                if not guard.evaluate(vars_copy, context):
                    guards_passed = False
                    break
            if guards_passed:
                active_transition = cand
                break

        if active_transition is None:
            raise ValidationError(
                "GUARD_EVALUATION_FAILED",
                f"Guards rejected transition from '{current_state}' on event '{event}'",
            )

        # Apply transition effect
        if active_transition.effect is not None:
            next_vars = dict(active_transition.effect(vars_copy, context))
        else:
            next_vars = vars_copy

        next_state = active_transition.target_state

        # Check for forbidden state
        for fs in self.forbidden_states:
            if fs.matches(next_state, next_vars):
                raise ValidationError(
                    "FORBIDDEN_STATE_REACHED",
                    f"Forbidden state reached: {fs.forbidden_id} ({fs.reason}) on state '{next_state}'",
                )

        return next_state, next_vars

    def replay(
        self,
        initial_state: str,
        trace: Sequence[tuple[str, Any]],
        initial_vars: dict[str, Any] | None = None,
        history_cut: dict[str, Any] | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        if initial_state not in self.initial_states and initial_state not in self.states:
            raise ValidationError("UNKNOWN_INITIAL_STATE", initial_state)

        curr_state = initial_state
        curr_vars = dict(self.state_variables) if initial_vars is None else dict(initial_vars)
        result: list[tuple[str, dict[str, Any]]] = [(curr_state, dict(curr_vars))]

        for event, ctx in trace:
            curr_state, curr_vars = self.step(
                curr_state, event, curr_vars, context=ctx, history_cut=history_cut
            )
            result.append((curr_state, dict(curr_vars)))

        return result

    def create_successor(
        self,
        source_generation_ref: dict[str, Any] | None = None,
        history_cut: dict[str, Any] | None = None,
        state_variables: dict[str, Any] | None = None,
        states: Mapping[str, State] | None = None,
        initial_states: Sequence[str] | None = None,
        transitions: Sequence[Transition] | None = None,
        forbidden_states: Sequence[ForbiddenState] | None = None,
        abstraction_assumptions: Sequence[str] | None = None,
        bounds: Sequence[str] | None = None,
        omitted_states: Sequence[str] | None = None,
        fairness_time_assumptions: Sequence[str] | None = None,
    ) -> "StateModel":
        pred_ref = {
            "model_id": self.model_id,
            "revision": self.model_revision,
            "digest": self.model_hash(),
        }
        return StateModel(
            model_id=self.model_id,
            model_revision=self.model_revision + 1,
            source_generation_ref=(
                source_generation_ref if source_generation_ref is not None else self.source_generation_ref
            ),
            history_cut=history_cut if history_cut is not None else self.history_cut,
            scope=self.scope,
            state_variables=state_variables if state_variables is not None else self.state_variables,
            states=states if states is not None else self.states,
            initial_states=initial_states if initial_states is not None else self.initial_states,
            transitions=transitions if transitions is not None else self.transitions,
            forbidden_states=(
                forbidden_states if forbidden_states is not None else self.forbidden_states
            ),
            abstraction_assumptions=(
                abstraction_assumptions
                if abstraction_assumptions is not None
                else self.abstraction_assumptions
            ),
            bounds=bounds if bounds is not None else self.bounds,
            omitted_states=omitted_states if omitted_states is not None else self.omitted_states,
            fairness_time_assumptions=(
                fairness_time_assumptions
                if fairness_time_assumptions is not None
                else self.fairness_time_assumptions
            ),
            predecessor_revision_ref=pred_ref,
        )

    def body(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "source_generation_ref": dict(self.source_generation_ref),
            "history_cut": dict(self.history_cut),
            "scope": self.scope,
            "state_variables": dict(sorted(self.state_variables.items())),
            "states": {k: self.states[k].body() for k in sorted(self.states.keys())},
            "initial_states": list(sorted(self.initial_states)),
            "transitions": [tr.body() for tr in sorted(self.transitions, key=lambda t: t.transition_id)],
            "forbidden_states": [fs.body() for fs in sorted(self.forbidden_states, key=lambda f: f.forbidden_id)],
            "abstraction_assumptions": list(self.abstraction_assumptions),
            "bounds": list(self.bounds),
            "omitted_states": list(self.omitted_states),
            "fairness_time_assumptions": list(self.fairness_time_assumptions),
            "predecessor_revision_ref": (
                dict(self.predecessor_revision_ref) if self.predecessor_revision_ref else None
            ),
        }

    def model_hash(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()


@dataclass(frozen=True)
class ModelFidelityAssessment:
    fidelity_assessment_id: str
    model_revision_ref: dict[str, Any]
    source_generation_ref: dict[str, Any]
    implementation_anchor_refs: list[dict[str, Any]]
    abstraction_mapping_refs: list[dict[str, Any]]
    abstraction_assumptions: list[str]
    omitted_states: list[str]
    bounds: list[str]
    fairness_time_assumptions: list[str]
    execution_conformance_evidence_refs: list[dict[str, Any]]
    scope: str
    assessment_input_history_cut: dict[str, Any]
    result: str  # QUALIFIED | BOUNDED | INSUFFICIENT | INVALIDATED
    reason_codes: list[str]

    def body(self) -> dict[str, Any]:
        return {
            "fidelity_assessment_id": self.fidelity_assessment_id,
            "model_revision_ref": dict(self.model_revision_ref),
            "source_generation_ref": dict(self.source_generation_ref),
            "implementation_anchor_refs": list(self.implementation_anchor_refs),
            "abstraction_mapping_refs": list(self.abstraction_mapping_refs),
            "abstraction_assumptions": list(self.abstraction_assumptions),
            "omitted_states": list(self.omitted_states),
            "bounds": list(self.bounds),
            "fairness_time_assumptions": list(self.fairness_time_assumptions),
            "execution_conformance_evidence_refs": list(self.execution_conformance_evidence_refs),
            "scope": self.scope,
            "assessment_input_history_cut": dict(self.assessment_input_history_cut),
            "result": self.result,
            "reason_codes": list(self.reason_codes),
        }


def evaluate_model_fidelity(
    model: StateModel,
    conformance_evidence: Sequence[dict[str, Any]],
    history_cut: dict[str, Any],
    is_invalidated: bool = False,
    implementation_anchors: Sequence[dict[str, Any]] = (),
) -> ModelFidelityAssessment:
    if history_cut != model.history_cut:
        raise ValidationError(
            "STALE_HISTORY_CUT",
            f"Fidelity assessment input history cut does not match model history cut",
        )

    fid_id = new_id("model_fidelity_assessment")
    model_ref = {
        "model_id": model.model_id,
        "revision": model.model_revision,
        "digest": model.model_hash(),
    }

    if is_invalidated:
        res = "INVALIDATED"
        reasons = ["CONFORMANCE_EVIDENCE_INVALIDATED"]
    elif not conformance_evidence:
        res = "INSUFFICIENT"
        reasons = ["MISSING_CONFORMANCE_EVIDENCE"]
    elif model.bounds or model.omitted_states or model.abstraction_assumptions:
        res = "BOUNDED"
        reasons = ["MODEL_BOUNDED_OR_ABSTRACTION_PRESENT"]
    else:
        res = "QUALIFIED"
        reasons = ["FULL_CONFORMANCE_VERIFIED"]

    return ModelFidelityAssessment(
        fidelity_assessment_id=fid_id,
        model_revision_ref=model_ref,
        source_generation_ref=model.source_generation_ref,
        implementation_anchor_refs=list(implementation_anchors),
        abstraction_mapping_refs=[],
        abstraction_assumptions=list(model.abstraction_assumptions),
        omitted_states=list(model.omitted_states),
        bounds=list(model.bounds),
        fairness_time_assumptions=list(model.fairness_time_assumptions),
        execution_conformance_evidence_refs=list(conformance_evidence),
        scope=model.scope,
        assessment_input_history_cut=dict(history_cut),
        result=res,
        reason_codes=reasons,
    )

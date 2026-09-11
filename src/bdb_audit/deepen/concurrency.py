"""Concurrency Schedule Engine (WP-E4-05 / M32 / §89).

Implements:
- SchedulePoint, InterleavingSeed, ConcurrencySchedule.
- Deterministic interleaving generation and replay.
- Idempotent duplicate replay and fail-closed conflicting duplicate rejection.
- Stale history cut rejection.
- Race observation emission to standard evidence pipeline (race != finding).
"""
from dataclasses import dataclass, field
import hashlib
import random
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id
from ..evidence.models import Observation


SCHEDULE_LOCATIONS = {
    "BEFORE_LOCK",
    "AFTER_LOCK",
    "BEFORE_READ",
    "AFTER_READ",
    "BEFORE_MUTATION",
    "AFTER_MUTATION",
    "BEFORE_WRITE",
    "AFTER_WRITE",
    "BEFORE_PUBLISH",
    "AFTER_PUBLISH",
    "YIELD",
}


@dataclass(frozen=True)
class SchedulePoint:
    point_id: str
    actor_id: str
    location: str
    step_index: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.location not in SCHEDULE_LOCATIONS:
            raise ValidationError("INVALID_SCHEDULE_POINT_LOCATION", f"Unknown location: {self.location}")
        if self.step_index < 0:
            raise ValidationError("INVALID_STEP_INDEX", "Step index must be non-negative")

    def body(self) -> dict[str, Any]:
        return {
            "point_id": self.point_id,
            "actor_id": self.actor_id,
            "location": self.location,
            "step_index": self.step_index,
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass(frozen=True)
class InterleavingSeed:
    seed_value: int
    salt: str = ""
    generator_version: str = "BDB-INTERLEAVING-v1"

    def body(self) -> dict[str, Any]:
        return {
            "seed_value": self.seed_value,
            "salt": self.salt,
            "generator_version": self.generator_version,
        }


@dataclass(frozen=True)
class ConcurrencySchedule:
    schedule_id: str
    seed: InterleavingSeed
    history_cut: dict[str, Any]
    participating_actors: tuple[str, ...]
    schedule_points: tuple[SchedulePoint, ...]

    def __post_init__(self):
        if not self.schedule_id:
            raise ValidationError("MISSING_SCHEDULE_ID", "Schedule ID required")
        if not self.participating_actors:
            raise ValidationError("MISSING_PARTICIPATING_ACTORS", "At least one actor required")
        actors_set = set(self.participating_actors)
        for sp in self.schedule_points:
            if sp.actor_id not in actors_set:
                raise ValidationError(
                    "UNKNOWN_ACTOR_IN_SCHEDULE",
                    f"SchedulePoint actor {sp.actor_id} not in participating actors",
                )

    def body(self) -> dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "seed": self.seed.body(),
            "history_cut": dict(self.history_cut),
            "participating_actors": list(sorted(self.participating_actors)),
            "schedule_points": [sp.body() for sp in self.schedule_points],
        }

    def digest(self) -> str:
        b = canonical_bytes(self.body())
        return hashlib.sha256(b).hexdigest()


@dataclass(frozen=True)
class ReplayResult:
    result_id: str
    schedule_id: str
    schedule_digest: str
    seed_value: int
    executed_points: int
    race_detected: bool
    final_output: Any
    trace_log: tuple[dict[str, Any], ...]

    def body(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "schedule_id": self.schedule_id,
            "schedule_digest": self.schedule_digest,
            "seed_value": self.seed_value,
            "executed_points": self.executed_points,
            "race_detected": self.race_detected,
            "final_output": str(self.final_output),
            "trace_log": list(self.trace_log),
        }


class ScheduleReplayEngine:
    def __init__(self):
        self._replay_cache: dict[str, ReplayResult] = {}

    def generate_schedule(
        self,
        seed: InterleavingSeed,
        actors: Sequence[str],
        locations_per_actor: Mapping[str, Sequence[str]],
        history_cut: dict[str, Any],
    ) -> ConcurrencySchedule:
        if not actors:
            raise ValidationError("EMPTY_ACTORS", "Actors sequence must not be empty")

        rng = random.Random(f"{seed.seed_value}:{seed.salt}:{seed.generator_version}")
        
        # Build queue of steps for each actor
        actor_queues: dict[str, list[tuple[str, int]]] = {}
        for act in actors:
            locs = locations_per_actor.get(act, ["BEFORE_MUTATION", "AFTER_MUTATION"])
            actor_queues[act] = [(loc, idx) for idx, loc in enumerate(locs)]

        interleaved_points: list[SchedulePoint] = []
        point_counter = 0

        while any(actor_queues.values()):
            # Select available actors
            active_acts = [act for act in actors if actor_queues[act]]
            chosen_act = rng.choice(active_acts)
            loc, step_idx = actor_queues[chosen_act].pop(0)

            interleaved_points.append(
                SchedulePoint(
                    point_id=f"sp_{point_counter:04d}",
                    actor_id=chosen_act,
                    location=loc,
                    step_index=step_idx,
                )
            )
            point_counter += 1

        sched_id = f"sched_{hashlib.sha256(str(seed.seed_value).encode()).hexdigest()[:12]}"
        return ConcurrencySchedule(
            schedule_id=sched_id,
            seed=seed,
            history_cut=history_cut,
            participating_actors=tuple(actors),
            schedule_points=tuple(interleaved_points),
        )

    def replay(
        self,
        schedule: ConcurrencySchedule,
        target_runner: Callable[[SchedulePoint], tuple[bool, Any]],
        history_cut: dict[str, Any] | None = None,
    ) -> ReplayResult:
        if history_cut is not None and history_cut != schedule.history_cut:
            raise ValidationError(
                "STALE_HISTORY_CUT",
                f"Replay cut {history_cut} != schedule cut {schedule.history_cut}",
            )

        sched_digest = schedule.digest()

        # Idempotency / conflict check
        if schedule.schedule_id in self._replay_cache:
            cached = self._replay_cache[schedule.schedule_id]
            if cached.schedule_digest != sched_digest:
                raise ValidationError(
                    "CONFLICTING_SCHEDULE_DUPLICATE",
                    f"Schedule {schedule.schedule_id} already registered with different digest",
                )
            return cached

        trace_log = []
        any_race = False
        final_val = None

        for sp in schedule.schedule_points:
            race_flag, out_val = target_runner(sp)
            trace_log.append(
                {
                    "point_id": sp.point_id,
                    "actor_id": sp.actor_id,
                    "location": sp.location,
                    "step_index": sp.step_index,
                    "output": str(out_val),
                }
            )
            if race_flag:
                any_race = True
            final_val = out_val

        result = ReplayResult(
            result_id=new_id("execution_result"),
            schedule_id=schedule.schedule_id,
            schedule_digest=sched_digest,
            seed_value=schedule.seed.seed_value,
            executed_points=len(schedule.schedule_points),
            race_detected=any_race,
            final_output=final_val,
            trace_log=tuple(trace_log),
        )
        self._replay_cache[schedule.schedule_id] = result
        return result

    def to_observation(
        self,
        result: ReplayResult,
        target_ref: dict[str, Any],
        execution_descriptor_ref: Any = None,
    ) -> Observation:
        exec_ref = execution_descriptor_ref or {
            "execution_descriptor_id": new_id("execution_descriptor"),
            "schedule_id": result.schedule_id,
        }
        return Observation(
            observation_id=new_id("observation"),
            execution_descriptor_ref=exec_ref,
            raw_observation_ref=result.body(),
            observation_channel="CONCURRENCY_SCHEDULE_ENGINE",
            observed_at="2026-09-11T12:00:00Z",
        )

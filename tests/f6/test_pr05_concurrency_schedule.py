"""Targeted tests for PR-E4-05 / M32: Concurrency Schedule Engine."""
import pytest
from bdb_audit.core.errors import ValidationError
from bdb_audit.evidence.models import Observation
from bdb_audit.deepen.concurrency import (
    SchedulePoint,
    InterleavingSeed,
    ConcurrencySchedule,
    ScheduleReplayEngine,
)


def test_two_operation_interleaving_and_deterministic_replay():
    engine = ScheduleReplayEngine()
    seed = InterleavingSeed(seed_value=42)
    cut = {"cut_id": "cut_01", "point": 10}

    sched1 = engine.generate_schedule(
        seed=seed,
        actors=["ACTOR_A", "ACTOR_B"],
        locations_per_actor={
            "ACTOR_A": ["BEFORE_READ", "BEFORE_WRITE"],
            "ACTOR_B": ["BEFORE_READ", "BEFORE_WRITE"],
        },
        history_cut=cut,
    )
    sched2 = engine.generate_schedule(
        seed=seed,
        actors=["ACTOR_A", "ACTOR_B"],
        locations_per_actor={
            "ACTOR_A": ["BEFORE_READ", "BEFORE_WRITE"],
            "ACTOR_B": ["BEFORE_READ", "BEFORE_WRITE"],
        },
        history_cut=cut,
    )

    assert sched1.schedule_points == sched2.schedule_points
    assert sched1.digest() == sched2.digest()
    assert len(sched1.schedule_points) == 4


def test_different_seed_different_schedule():
    engine = ScheduleReplayEngine()
    cut = {"cut_id": "cut_01", "point": 10}

    sched_a = engine.generate_schedule(
        seed=InterleavingSeed(seed_value=1),
        actors=["ACTOR_A", "ACTOR_B"],
        locations_per_actor={
            "ACTOR_A": ["BEFORE_READ", "BEFORE_WRITE"],
            "ACTOR_B": ["BEFORE_READ", "BEFORE_WRITE"],
        },
        history_cut=cut,
    )
    sched_b = engine.generate_schedule(
        seed=InterleavingSeed(seed_value=9999),
        actors=["ACTOR_A", "ACTOR_B"],
        locations_per_actor={
            "ACTOR_A": ["BEFORE_READ", "BEFORE_WRITE"],
            "ACTOR_B": ["BEFORE_READ", "BEFORE_WRITE"],
        },
        history_cut=cut,
    )

    # Different seeds should yield different digests
    assert sched_a.digest() != sched_b.digest()


def test_invalid_schedule_point_and_unknown_actor():
    with pytest.raises(ValidationError) as exc:
        SchedulePoint(
            point_id="p1",
            actor_id="ACTOR_A",
            location="INVALID_LOCATION",
            step_index=0,
        )
    assert "INVALID_SCHEDULE_POINT_LOCATION" in str(exc.value)

    # Schedule referencing an actor not in participating_actors
    sp = SchedulePoint(point_id="p1", actor_id="GHOST_ACTOR", location="BEFORE_LOCK", step_index=0)
    with pytest.raises(ValidationError) as exc:
        ConcurrencySchedule(
            schedule_id="s1",
            seed=InterleavingSeed(seed_value=1),
            history_cut={"cut_id": "c1"},
            participating_actors=("ACTOR_A",),
            schedule_points=(sp,),
        )
    assert "UNKNOWN_ACTOR_IN_SCHEDULE" in str(exc.value)


def test_synthetic_lost_update_race_fixture():
    # Model a shared counter with read/modify/write
    shared_counter = 0
    actor_local_reads = {}
    race_occurred = False

    def runner(sp: SchedulePoint):
        nonlocal shared_counter, race_occurred
        if sp.location == "BEFORE_READ":
            actor_local_reads[sp.actor_id] = shared_counter
            return False, shared_counter
        elif sp.location == "BEFORE_WRITE":
            # If both actors read 0 before either wrote, second write causes lost update
            val_to_write = actor_local_reads[sp.actor_id] + 1
            if shared_counter > 0 and actor_local_reads[sp.actor_id] == 0:
                # Race! Overwriting with stale base 0
                race_occurred = True
            shared_counter = val_to_write
            return race_occurred, shared_counter
        return False, shared_counter

    # Explicit interleaved schedule causing lost update:
    # A reads 0, B reads 0, A writes 1, B writes 1 -> lost update!
    sp_a_read = SchedulePoint("p1", "A", "BEFORE_READ", 0)
    sp_b_read = SchedulePoint("p2", "B", "BEFORE_READ", 0)
    sp_a_write = SchedulePoint("p3", "A", "BEFORE_WRITE", 1)
    sp_b_write = SchedulePoint("p4", "B", "BEFORE_WRITE", 1)

    sched_race = ConcurrencySchedule(
        schedule_id="sched_race_01",
        seed=InterleavingSeed(seed_value=100),
        history_cut={"cut_id": "c1"},
        participating_actors=("A", "B"),
        schedule_points=(sp_a_read, sp_b_read, sp_a_write, sp_b_write),
    )

    engine = ScheduleReplayEngine()
    res = engine.replay(sched_race, runner)

    assert res.race_detected is True
    assert shared_counter == 1  # Expected 2 without race, but lost update resulted in 1


def test_clean_control_fixture():
    # Clean sequential execution: A reads, A writes, B reads, B writes -> counter is 2
    shared_counter = 0
    actor_local_reads = {}
    race_occurred = False

    def runner(sp: SchedulePoint):
        nonlocal shared_counter, race_occurred
        if sp.location == "BEFORE_READ":
            actor_local_reads[sp.actor_id] = shared_counter
            return False, shared_counter
        elif sp.location == "BEFORE_WRITE":
            val_to_write = actor_local_reads[sp.actor_id] + 1
            if shared_counter > 0 and actor_local_reads[sp.actor_id] == 0:
                race_occurred = True
            shared_counter = val_to_write
            return race_occurred, shared_counter
        return False, shared_counter

    sp_a_read = SchedulePoint("p1", "A", "BEFORE_READ", 0)
    sp_a_write = SchedulePoint("p2", "A", "BEFORE_WRITE", 1)
    sp_b_read = SchedulePoint("p3", "B", "BEFORE_READ", 0)
    sp_b_write = SchedulePoint("p4", "B", "BEFORE_WRITE", 1)

    sched_clean = ConcurrencySchedule(
        schedule_id="sched_clean_01",
        seed=InterleavingSeed(seed_value=200),
        history_cut={"cut_id": "c1"},
        participating_actors=("A", "B"),
        schedule_points=(sp_a_read, sp_a_write, sp_b_read, sp_b_write),
    )

    engine = ScheduleReplayEngine()
    res = engine.replay(sched_clean, runner)

    assert res.race_detected is False
    assert shared_counter == 2


def test_idempotent_duplicate_and_conflicting_duplicate():
    engine = ScheduleReplayEngine()
    sp1 = SchedulePoint("p1", "A", "BEFORE_READ", 0)
    sched = ConcurrencySchedule(
        schedule_id="sched_dup",
        seed=InterleavingSeed(seed_value=1),
        history_cut={"cut_id": "c1"},
        participating_actors=("A",),
        schedule_points=(sp1,),
    )

    # First run
    res1 = engine.replay(sched, lambda sp: (False, "OK"))
    # Idempotent second run
    res2 = engine.replay(sched, lambda sp: (False, "OK"))
    assert res1 is res2

    # Conflicting duplicate: same schedule_id, different point
    sp2 = SchedulePoint("p2", "A", "AFTER_READ", 1)
    sched_conflict = ConcurrencySchedule(
        schedule_id="sched_dup",
        seed=InterleavingSeed(seed_value=1),
        history_cut={"cut_id": "c1"},
        participating_actors=("A",),
        schedule_points=(sp1, sp2),
    )

    with pytest.raises(ValidationError) as exc:
        engine.replay(sched_conflict, lambda sp: (False, "OK"))
    assert "CONFLICTING_SCHEDULE_DUPLICATE" in str(exc.value)


def test_stale_history_cut_rejected():
    engine = ScheduleReplayEngine()
    sp1 = SchedulePoint("p1", "A", "BEFORE_READ", 0)
    sched = ConcurrencySchedule(
        schedule_id="sched_cut",
        seed=InterleavingSeed(seed_value=1),
        history_cut={"cut_id": "c_valid", "point": 10},
        participating_actors=("A",),
        schedule_points=(sp1,),
    )

    with pytest.raises(ValidationError) as exc:
        engine.replay(sched, lambda sp: (False, "OK"), history_cut={"cut_id": "c_stale", "point": 5})
    assert "STALE_HISTORY_CUT" in str(exc.value)


def test_concurrency_observation_conversion():
    engine = ScheduleReplayEngine()
    sp1 = SchedulePoint("p1", "A", "BEFORE_READ", 0)
    sched = ConcurrencySchedule(
        schedule_id="sched_obs",
        seed=InterleavingSeed(seed_value=1),
        history_cut={"cut_id": "c1"},
        participating_actors=("A",),
        schedule_points=(sp1,),
    )
    res = engine.replay(sched, lambda sp: (True, "RACE_VALUE"))
    assert res.race_detected is True

    obs = engine.to_observation(res, target_ref={"target": "shared_resource"})
    assert isinstance(obs, Observation)
    assert obs.observation_channel == "CONCURRENCY_SCHEDULE_ENGINE"
    assert obs.raw_observation_ref["race_detected"] is True
    # Verifying no finding bypass
    assert not hasattr(obs, "finding_id")
    assert not hasattr(obs, "lifecycle_status")

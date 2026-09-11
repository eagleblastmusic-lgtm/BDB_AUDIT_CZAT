"""Targeted tests for PR-E4-07 / M34: Endurance Engine."""
import pytest
from bdb_audit.evidence.models import Observation
from bdb_audit.deepen.endurance import (
    MetricSnapshot,
    EnduranceProfile,
    EnduranceEngine,
)


def test_stable_resources_endurance():
    engine = EnduranceEngine()
    profile = EnduranceProfile(profile_id="p_stable", workload_rounds=5)

    # Simulated system with stable metrics
    def sampler(step: int) -> MetricSnapshot:
        return MetricSnapshot(
            timestamp_ms=1000 + step * 10,
            thread_count=4,
            resource_count=10,
            queue_depth=0,
            map_sizes={"cache": 5},
            pending_work=0,
            memory_bytes=100_000,
        )

    res = engine.run_endurance_test(
        workload_fn=lambda round_idx: None,
        sampler_fn=sampler,
        cleanup_fn=lambda: None,
        profile=profile,
    )

    assert res.classification == "STABLE"
    assert res.metrics_trend["resource_count_delta"] == 0
    assert res.metrics_trend["memory_growth_ratio"] == 0.0


def test_monotonic_synthetic_leak():
    engine = EnduranceEngine()
    profile = EnduranceProfile(profile_id="p_leak", workload_rounds=5)

    current_res = 10

    def workload(round_idx: int):
        nonlocal current_res
        current_res += 5  # Leaking resources every round

    def sampler(step: int) -> MetricSnapshot:
        return MetricSnapshot(
            timestamp_ms=1000 + step * 10,
            thread_count=4,
            resource_count=current_res,
            queue_depth=0,
            map_sizes={},
            pending_work=0,
            memory_bytes=100_000 + current_res * 1000,
        )

    # Cleanup fails to free resources
    res = engine.run_endurance_test(
        workload_fn=workload,
        sampler_fn=sampler,
        cleanup_fn=lambda: None,
        profile=profile,
    )

    assert res.classification == "RESOURCE_LEAK"
    assert res.metrics_trend["monotonic_leak_detected"] is True
    assert res.metrics_trend["resource_count_delta"] > 0


def test_temporary_spike_and_recovery_no_false_positive():
    engine = EnduranceEngine()
    profile = EnduranceProfile(profile_id="p_spike", workload_rounds=5)

    current_res = 10

    def workload(round_idx: int):
        nonlocal current_res
        current_res = 100  # Spike during execution

    def cleanup():
        nonlocal current_res
        current_res = 10  # Clean drop back to baseline

    def sampler(step: int) -> MetricSnapshot:
        return MetricSnapshot(
            timestamp_ms=1000 + step * 10,
            thread_count=4,
            resource_count=current_res,
            queue_depth=0,
            map_sizes={},
            pending_work=0,
            memory_bytes=100_000 if current_res == 10 else 500_000,
        )

    res = engine.run_endurance_test(
        workload_fn=workload,
        sampler_fn=sampler,
        cleanup_fn=cleanup,
        profile=profile,
    )

    # Proves no false positive: spike is recognized but successfully recovered!
    assert res.classification == "RECOVERED_SPIKE"
    assert res.metrics_trend["peak_resources"] == 100
    assert res.metrics_trend["resource_count_delta"] == 0


def test_queue_drain_vs_undrained():
    engine = EnduranceEngine()
    profile = EnduranceProfile(profile_id="p_drain", workload_rounds=3, require_drain=True)

    # 1. Undrained queue
    def sampler_undrained(step: int) -> MetricSnapshot:
        return MetricSnapshot(
            timestamp_ms=1000 + step,
            thread_count=2,
            resource_count=5,
            queue_depth=5,  # Stays > 0 after cleanup
            map_sizes={},
            pending_work=0,
            memory_bytes=50_000,
        )

    res_undrained = engine.run_endurance_test(
        workload_fn=lambda r: None,
        sampler_fn=sampler_undrained,
        profile=profile,
    )
    assert res_undrained.classification == "QUEUE_UNDRAINED"

    # 2. Successfully drained queue
    q = 0

    def workload(r):
        nonlocal q
        q = 10

    def cleanup():
        nonlocal q
        q = 0  # Drains to 0

    def sampler_drained(step: int) -> MetricSnapshot:
        return MetricSnapshot(
            timestamp_ms=1000 + step,
            thread_count=2,
            resource_count=5,
            queue_depth=q,
            map_sizes={},
            pending_work=0,
            memory_bytes=50_000,
        )

    res_drained = engine.run_endurance_test(
        workload_fn=workload,
        sampler_fn=sampler_drained,
        cleanup_fn=cleanup,
        profile=profile,
    )
    assert res_drained.classification in ("STABLE", "RECOVERED_SPIKE")
    assert res_drained.metrics_trend["final_queue_depth"] == 0


def test_endurance_observation_conversion():
    engine = EnduranceEngine()
    snap = MetricSnapshot(
        timestamp_ms=1000,
        thread_count=2,
        resource_count=5,
        queue_depth=0,
        map_sizes={},
        pending_work=0,
        memory_bytes=50_000,
    )
    res = engine.run_endurance_test(
        workload_fn=lambda r: None,
        sampler_fn=lambda step: snap,
    )
    obs = engine.to_observation(res, target_ref={"target": "worker_pool"})
    assert isinstance(obs, Observation)
    assert obs.observation_channel == "ENDURANCE_ENGINE"
    assert obs.raw_observation_ref["classification"] == "STABLE"
    assert not hasattr(obs, "finding_id")
    assert not hasattr(obs, "lifecycle_status")

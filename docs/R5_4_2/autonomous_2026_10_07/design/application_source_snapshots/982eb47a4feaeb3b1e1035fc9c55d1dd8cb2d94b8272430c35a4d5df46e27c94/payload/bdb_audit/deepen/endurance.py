"""Endurance and Resource Ownership Engine (WP-E4-07 / M34 / §91 / Data Contracts §74).

Implements:
- MetricSnapshot: thread count, resource count, queue depth, map sizes, pending work, memory.
- Trend calculation over repeated samples, distinguishing temporary spikes from monotonic leaks.
- Separation of raw metrics from derived endurance assessment.
- Verified drain and cleanup observation.
- Emission of canonical Observation without finding shortcut.
"""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id
from ..evidence.models import Observation


ENDURANCE_CLASSIFICATIONS = {
    "STABLE",
    "RECOVERED_SPIKE",
    "RESOURCE_LEAK",
    "QUEUE_UNDRAINED",
    "INSUFFICIENT_SAMPLES",
}


@dataclass(frozen=True)
class MetricSnapshot:
    timestamp_ms: int
    thread_count: int
    resource_count: int
    queue_depth: int
    map_sizes: dict[str, int]
    pending_work: int
    memory_bytes: int

    def body(self) -> dict[str, Any]:
        return {
            "timestamp_ms": self.timestamp_ms,
            "thread_count": self.thread_count,
            "resource_count": self.resource_count,
            "queue_depth": self.queue_depth,
            "map_sizes": dict(sorted(self.map_sizes.items())),
            "pending_work": self.pending_work,
            "memory_bytes": self.memory_bytes,
        }


@dataclass(frozen=True)
class EnduranceProfile:
    profile_id: str
    workload_rounds: int = 10
    max_allowed_memory_growth_ratio: float = 0.25
    max_allowed_resource_growth: int = 0
    require_drain: bool = True

    def body(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "workload_rounds": self.workload_rounds,
            "max_allowed_memory_growth_ratio": self.max_allowed_memory_growth_ratio,
            "max_allowed_resource_growth": self.max_allowed_resource_growth,
            "require_drain": self.require_drain,
        }


@dataclass(frozen=True)
class EnduranceAssessment:
    assessment_id: str
    baseline: MetricSnapshot
    samples: tuple[MetricSnapshot, ...]
    post_cleanup: MetricSnapshot
    classification: str  # from ENDURANCE_CLASSIFICATIONS
    metrics_trend: dict[str, Any]
    details: dict[str, Any] = field(default_factory=dict)

    def body(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "baseline": self.baseline.body(),
            "samples": [s.body() for s in self.samples],
            "post_cleanup": self.post_cleanup.body(),
            "classification": self.classification,
            "metrics_trend": dict(self.metrics_trend),
            "details": dict(self.details),
        }


class EnduranceEngine:
    def __init__(self, default_profile: EnduranceProfile | None = None):
        self.default_profile = default_profile or EnduranceProfile(profile_id="default_endurance")

    def run_endurance_test(
        self,
        workload_fn: Callable[[int], None],
        sampler_fn: Callable[[int], MetricSnapshot],
        cleanup_fn: Callable[[], None] | None = None,
        profile: EnduranceProfile | None = None,
    ) -> EnduranceAssessment:
        p = profile or self.default_profile
        res_id = new_id("execution_result")

        # 1. Baseline
        baseline = sampler_fn(0)

        # 2. Workload run with repeated sampling
        samples = []
        for r in range(1, p.workload_rounds + 1):
            workload_fn(r)
            snap = sampler_fn(r)
            samples.append(snap)

        # 3. Post-workload cleanup
        if cleanup_fn is not None:
            cleanup_fn()

        # 4. Post-cleanup sample
        post_cleanup = sampler_fn(p.workload_rounds + 1)

        # 5. Trend analysis
        if len(samples) < 2:
            return EnduranceAssessment(
                assessment_id=res_id,
                baseline=baseline,
                samples=tuple(samples),
                post_cleanup=post_cleanup,
                classification="INSUFFICIENT_SAMPLES",
                metrics_trend={},
                details={"reason": "Less than 2 workload samples"},
            )

        # Calculate memory delta and growth ratio
        mem_start = baseline.memory_bytes
        mem_end = post_cleanup.memory_bytes
        mem_delta = mem_end - mem_start
        mem_ratio = (mem_delta / max(1, mem_start)) if mem_start > 0 else 0.0

        # Max memory observed during workload
        peak_mem = max(s.memory_bytes for s in samples)
        peak_resources = max(s.resource_count for s in samples)

        res_delta = post_cleanup.resource_count - baseline.resource_count
        thread_delta = post_cleanup.thread_count - baseline.thread_count
        final_queue = post_cleanup.queue_depth
        final_pending = post_cleanup.pending_work

        # Check for monotonic leak across samples
        is_monotonic_leak = True
        for i in range(1, len(samples)):
            if samples[i].resource_count <= samples[i - 1].resource_count:
                is_monotonic_leak = False
                break

        trend_summary = {
            "baseline_memory": mem_start,
            "peak_memory": peak_mem,
            "post_cleanup_memory": mem_end,
            "memory_growth_ratio": mem_ratio,
            "resource_count_delta": res_delta,
            "thread_count_delta": thread_delta,
            "final_queue_depth": final_queue,
            "final_pending_work": final_pending,
            "peak_resources": peak_resources,
            "monotonic_leak_detected": is_monotonic_leak and res_delta > 0,
        }

        # Classification rules
        if p.require_drain and (final_queue > 0 or final_pending > 0):
            classification = "QUEUE_UNDRAINED"
        elif res_delta > p.max_allowed_resource_growth or thread_delta > 0 or mem_ratio > p.max_allowed_memory_growth_ratio:
            classification = "RESOURCE_LEAK"
        elif peak_resources > baseline.resource_count and res_delta <= p.max_allowed_resource_growth:
            # Temporary spike during execution, but cleanly recovered after cleanup!
            classification = "RECOVERED_SPIKE"
        else:
            classification = "STABLE"

        return EnduranceAssessment(
            assessment_id=res_id,
            baseline=baseline,
            samples=tuple(samples),
            post_cleanup=post_cleanup,
            classification=classification,
            metrics_trend=trend_summary,
        )

    def to_observation(
        self,
        assessment: EnduranceAssessment,
        target_ref: dict[str, Any],
        execution_descriptor_ref: Any = None,
    ) -> Observation:
        exec_ref = execution_descriptor_ref or {
            "execution_descriptor_id": new_id("execution_descriptor"),
            "target": target_ref,
        }
        return Observation(
            observation_id=new_id("observation"),
            execution_descriptor_ref=exec_ref,
            raw_observation_ref=assessment.body(),
            observation_channel="ENDURANCE_ENGINE",
            observed_at="2026-09-11T12:00:00Z",
        )

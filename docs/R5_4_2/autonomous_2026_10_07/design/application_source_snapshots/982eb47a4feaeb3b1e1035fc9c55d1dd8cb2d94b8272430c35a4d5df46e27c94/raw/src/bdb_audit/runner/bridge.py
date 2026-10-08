"""RU10 bridge from controlled tool execution into the existing execution DAG.

The bridge never fabricates observations. A caller must provide an explicit
normalizer to turn raw runner receipts into typed observation refs.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from ..execution.adapters import ExecutionRunOutput
from ..execution.models import ExecutionDescriptor
from .specs import ToolRunResult, ToolRunSpec
from .supervisor import ToolSupervisor

SpecFactory = Callable[[ExecutionDescriptor], ToolRunSpec]
ObservationNormalizer = Callable[[ToolRunResult], Sequence[dict[str, Any]]]


def make_execution_runner(
    supervisor: ToolSupervisor,
    spec_factory: SpecFactory,
    *,
    observation_normalizer: ObservationNormalizer | None = None,
) -> Callable[[ExecutionDescriptor], ExecutionRunOutput]:
    """Return an ExecutionAdapter-compatible runner callback.

    ``SUCCESS`` means only that the exact argv exited zero under the declared
    supervisor profile. Observation refs remain empty unless an explicit
    normalizer was supplied, so downstream evidence qualification cannot infer
    target truth from the process exit code alone.
    """

    def execute(descriptor: ExecutionDescriptor) -> ExecutionRunOutput:
        result = supervisor.run(spec_factory(descriptor))
        observations: Sequence[dict[str, Any]] = ()
        if observation_normalizer is not None and result.supervisor_status in {"SUCCESS", "TARGET_NONZERO"}:
            observations = tuple(observation_normalizer(result))
        status_map = {
            "SUCCESS": "SUCCESS",
            "TARGET_NONZERO": "FAILURE",
            "TIMEOUT": "TIMEOUT",
            "OUTPUT_LIMIT": "ERROR",
            "BLOCKED": "UNSUPPORTED",
            "EXECUTION_ERROR": "ERROR",
            "CLEANUP_FAILED": "ERROR",
        }
        return ExecutionRunOutput(
            exit_code=result.target_exit_code if result.target_exit_code is not None else 125,
            status=status_map[result.supervisor_status],
            raw_observations=observations,
            cleanup_status=result.cleanup_status,
            residual_cleared=result.cleanup_status == "CLEAN",
        )

    return execute


__all__ = ["make_execution_runner", "SpecFactory", "ObservationNormalizer"]

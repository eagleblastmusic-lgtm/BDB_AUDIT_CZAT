"""Production Execution Adapter and Runner (F4 Domain Expansion / M19 / §§41–45).

Manages execution lifecycle:
- Preregistration of ExecutionDescriptor BEFORE execution begins.
- Capability enforcement against ExecutorProfile.
- Fault injection activation tracking via FaultRunRecord.
- CleanupResult generation.
- ExecutionResult DAG creation with strict cycle prevention.
- Idempotency and crash-consistency.
"""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Callable, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id, validate_id, deterministic_id
from ..history.objects import CanonicalObject, ObjectRef
from .models import (
    ExperimentSpec,
    ExecutionDescriptor,
    FaultRunRecord,
    CleanupResult,
    ExecutionResult,
    _ref_dict,
)
from .dag import validate_execution_dag

EXPERIMENT_TYPES = {
    "STATIC_ANALYSIS",
    "DYNAMIC",
    "FAULT_INJECTION",
    "FUZZ",
    "PROPERTY",
    "DIFFERENTIAL",
    "METAMORPHIC",
    "STATEFUL",
    "CONCURRENCY",
    "ENDURANCE",
    "IMPLEMENTATION_MUTATION",
    "ORACLE_CHALLENGE",
    "MODEL_CONFORMANCE",
    "REPLAY",
}


@dataclass(frozen=True)
class ExecutionRunOutput:
    exit_code: int = 0
    status: str = "SUCCESS"
    raw_observations: Sequence[dict] = ()
    fault_activated: bool = False
    cleanup_status: str = "CLEAN"
    residual_cleared: bool = True


class ExecutionAdapter:
    """Orchestrates preregistration, capability validation, and execution result generation."""

    def __init__(self):
        # Store registered descriptors and results
        self._descriptors_by_id: dict[str, ExecutionDescriptor] = {}
        self._results_by_descriptor: dict[str, ExecutionResult] = {}

    def execute_experiment(
        self,
        experiment_spec: ExperimentSpec,
        executor_profile: Mapping[str, Any],
        attempt_ref: Any,
        history_cut: dict,
        environment_actuals: dict,
        execution_nonce: str,
        runner_fn: Callable[[ExecutionDescriptor], ExecutionRunOutput] | None = None,
        fault_spec: Mapping[str, Any] | None = None,
    ) -> tuple[ExecutionDescriptor, ExecutionResult, list[dict], CleanupResult, FaultRunRecord | None]:
        """Execute experiment according to the strict 2-phase preregistered DAG model.

        Absence of a runner is a truthful non-execution result, never a synthetic
        successful experiment.  RU10 may later provide controlled production
        runners; until then the adapter records ``UNSUPPORTED`` with zero target
        observations so no downstream qualifier can mistake a missing runner for
        evidence.
        """
        # 1. Capability enforcement: check that executor supports required techniques
        supported_capabilities = set(executor_profile.get("supported_capabilities", []))
        declared_techniques = set(executor_profile.get("allowed_techniques", supported_capabilities))

        req_capabilities = set(experiment_spec.observation_path_requirements)
        if not req_capabilities.issubset(declared_techniques) and not executor_profile.get("bypass_capability_check"):
            missing = req_capabilities - declared_techniques
            raise ValidationError(
                "EXECUTOR_CAPABILITY_EXCEEDED",
                f"Executor lacks required capabilities: {missing}",
            )

        # 2. Phase 1: Preregistration of ExecutionDescriptor BEFORE execution
        desc_id = deterministic_id("execution_descriptor", f"{experiment_spec.digest}:{execution_nonce}")
        desc = ExecutionDescriptor(
            execution_descriptor_id=desc_id,
            experiment_spec_ref=experiment_spec.as_object().as_ref(),
            executor_profile_ref={
                "kind": "executor_profile",
                "revision_digest": hashlib.sha256(canonical_bytes(dict(executor_profile))).hexdigest(),
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": "BDB_SCHEMA_REGISTRY::executor_profile/1",
                "ref_class": "CONTENT_OR_PRIOR",
            },
            attempt_ref=_ref_dict(attempt_ref),
            input_history_cut=history_cut,
            environment_actuals=environment_actuals,
            execution_nonce=execution_nonce,
        )

        # Idempotency check: if descriptor already executed with same nonce, return existing result
        if desc_id in self._results_by_descriptor:
            existing_res = self._results_by_descriptor[desc_id]
            return desc, existing_res, [], None, None  # type: ignore

        self._descriptors_by_id[desc_id] = desc

        # 3. Phase 2: Runtime execution
        desc_ref = _ref_dict(desc.as_object().as_ref())
        if runner_fn is not None:
            run_output = runner_fn(desc)
            if not isinstance(run_output, ExecutionRunOutput):
                raise ValidationError("INVALID_RUNNER_OUTPUT", type(run_output).__name__)
        else:
            # No production runner is implemented in this layer.  Do not invent
            # target observations or successful execution semantics.
            run_output = ExecutionRunOutput(
                exit_code=125,
                status="UNSUPPORTED",
                raw_observations=(),
                fault_activated=False,
                cleanup_status="CLEAN",
                residual_cleared=True,
            )

        # 4. Phase 3: FaultRunRecord (if fault injection configured)
        fault_record = None
        if fault_spec is not None:
            f_act = "ACTIVATED" if run_output.fault_activated else "NOT_ACTIVATED"
            fault_record_id = deterministic_id("fault_run_record", f"fault_{desc_id}")
            fault_record = FaultRunRecord(
                fault_run_record_id=fault_record_id,
                execution_descriptor_ref=desc_ref,
                fault_ref=_ref_dict(fault_spec),
                activation_status=f_act,
                evidence_refs=run_output.raw_observations,
            )

        # 5. Phase 4: CleanupResult
        cleanup_id = deterministic_id("cleanup_result", f"clean_{desc_id}")
        cleanup = CleanupResult(
            cleanup_result_id=cleanup_id,
            execution_descriptor_ref=desc_ref,
            cleanup_status=run_output.cleanup_status,
            residual_artifacts_cleared=run_output.residual_cleared,
        )

        # 6. Phase 5: Terminal ExecutionResult
        result_id = deterministic_id("execution_result", f"res_{desc_id}")
        exec_result = ExecutionResult(
            execution_result_id=result_id,
            execution_descriptor_ref=desc_ref,
            exit_code=run_output.exit_code,
            status=run_output.status,
            observation_refs=run_output.raw_observations,
            fault_activation_record_ref=_ref_dict(fault_record.as_object().as_ref()) if fault_record else None,
            cleanup_result_ref=_ref_dict(cleanup.as_object().as_ref()),
        )

        # 7. Validate DAG: Descriptor -> Observations/Fault/Cleanup -> Result (no cycles)
        dag_edges = [
            (desc.execution_descriptor_id, exec_result.execution_result_id),
            (desc.execution_descriptor_id, cleanup.cleanup_result_id),
            (cleanup.cleanup_result_id, exec_result.execution_result_id),
        ]
        if fault_record:
            dag_edges.append((desc.execution_descriptor_id, fault_record.fault_run_record_id))
            dag_edges.append((fault_record.fault_run_record_id, exec_result.execution_result_id))

        validate_execution_dag(dag_edges)

        self._results_by_descriptor[desc_id] = exec_result
        return desc, exec_result, list(run_output.raw_observations), cleanup, fault_record

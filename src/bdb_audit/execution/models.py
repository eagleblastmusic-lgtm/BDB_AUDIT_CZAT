"""R5.3.1 Experiment and Execution domain models (M19)."""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.hashing import DIGEST_PROFILE, object_digest
from ..core.ids import new_id, validate_id
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, ObjectRef


def _ref_dict(ref_or_obj: Any) -> dict:
    if isinstance(ref_or_obj, ObjectRef):
        return ref_or_obj.as_dict()
    if isinstance(ref_or_obj, CanonicalObject):
        return ref_or_obj.as_ref().as_dict()
    if isinstance(ref_or_obj, dict):
        return ref_or_obj
    raise ValidationError("INVALID_REFERENCE")


@dataclass(frozen=True)
class ExperimentSpec:
    hypothesis_revision_ref: Any
    invariant_revision_ref: Any
    coverage_obligation_refs: Sequence[Any]
    subject_baseline_ref: Any
    target_execution_variant_ref: Any
    environment_profile_ref: Any
    dependency_set_ref: Any
    harness_ref: Any
    fixture_refs: Sequence[Any]
    trigger: str
    expected_safe_behavior: str
    expected_buggy_behavior: str
    observation_path_requirements: Sequence[str]
    falsification_condition: str
    positive_controls: Sequence[str]
    negative_controls: Sequence[str]
    input_history_cut: dict
    experiment_id: str | None = None
    experiment_revision: str = "1"
    fault_ref: Any = None

    def __post_init__(self):
        if self.experiment_id is None:
            object.__setattr__(self, "experiment_id", new_id("experiment_spec"))
        elif self.experiment_id.startswith("experiment_spec_"):
            validate_id(self.experiment_id, "experiment_spec")

        object.__setattr__(
            self, "coverage_obligation_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.coverage_obligation_refs]))
        )
        object.__setattr__(
            self, "fixture_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.fixture_refs]))
        )

    def body(self) -> dict:
        data = {
            "experiment_id": self.experiment_id or "experiment_default",
            "experiment_revision": str(self.experiment_revision),
            "hypothesis_revision_ref": _ref_dict(self.hypothesis_revision_ref),
            "invariant_revision_ref": _ref_dict(self.invariant_revision_ref),
            "coverage_obligation_refs": list(self.coverage_obligation_refs),
            "subject_baseline_ref": _ref_dict(self.subject_baseline_ref),
            "target_execution_variant_ref": _ref_dict(self.target_execution_variant_ref),
            "environment_profile_ref": _ref_dict(self.environment_profile_ref),
            "dependency_set_ref": _ref_dict(self.dependency_set_ref),
            "harness_ref": _ref_dict(self.harness_ref),
            "fixture_refs": list(self.fixture_refs),
            "trigger": self.trigger,
            "expected_safe_behavior": self.expected_safe_behavior,
            "expected_buggy_behavior": self.expected_buggy_behavior,
            "observation_path_requirements": list(self.observation_path_requirements),
            "falsification_condition": self.falsification_condition,
            "positive_controls": list(self.positive_controls),
            "negative_controls": list(self.negative_controls),
            "input_history_cut": dict(self.input_history_cut),
        }
        if self.fault_ref is not None:
            data["fault_ref"] = _ref_dict(self.fault_ref)
        return data

    def as_object(self) -> CanonicalObject:
        lid = self.experiment_id if (self.experiment_id and self.experiment_id.startswith("experiment_spec_")) else None
        return CanonicalObject(
            "experiment_spec", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class ExecutionDescriptor:
    experiment_spec_ref: Any
    executor_profile_ref: Any
    attempt_ref: Any
    input_history_cut: dict
    environment_actuals: dict
    execution_nonce: str
    execution_descriptor_id: str | None = None

    def __post_init__(self):
        if self.execution_descriptor_id is None:
            object.__setattr__(self, "execution_descriptor_id", new_id("execution_descriptor"))
        elif self.execution_descriptor_id.startswith("execution_descriptor_"):
            validate_id(self.execution_descriptor_id, "execution_descriptor")

    def body(self) -> dict:
        return {
            "execution_descriptor_id": self.execution_descriptor_id or "descriptor_default",
            "experiment_spec_ref": _ref_dict(self.experiment_spec_ref),
            "executor_profile_ref": _ref_dict(self.executor_profile_ref),
            "attempt_ref": _ref_dict(self.attempt_ref),
            "input_history_cut": dict(self.input_history_cut),
            "environment_actuals": dict(self.environment_actuals),
            "execution_nonce": self.execution_nonce,
        }

    def as_object(self) -> CanonicalObject:
        lid = self.execution_descriptor_id if (self.execution_descriptor_id and self.execution_descriptor_id.startswith("execution_descriptor_")) else None
        return CanonicalObject(
            "execution_descriptor", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class FaultRunRecord:
    execution_descriptor_ref: Any
    fault_ref: Any
    activation_status: str = "ACTIVATED"
    evidence_refs: Sequence[Any] = ()
    fault_run_record_id: str | None = None

    def __post_init__(self):
        if self.fault_run_record_id is None:
            object.__setattr__(self, "fault_run_record_id", new_id("fault_run_record"))
        elif self.fault_run_record_id.startswith("fault_run_record_"):
            validate_id(self.fault_run_record_id, "fault_run_record")

        object.__setattr__(
            self, "evidence_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.evidence_refs]))
        )

    def body(self) -> dict:
        data = {
            "fault_run_record_id": self.fault_run_record_id or "fault_run_default",
            "execution_descriptor_ref": _ref_dict(self.execution_descriptor_ref),
            "fault_ref": _ref_dict(self.fault_ref),
            "activation_status": self.activation_status,
        }
        if self.evidence_refs:
            data["evidence_refs"] = list(self.evidence_refs)
        return data

    def as_object(self) -> CanonicalObject:
        lid = self.fault_run_record_id if (self.fault_run_record_id and self.fault_run_record_id.startswith("fault_run_record_")) else None
        return CanonicalObject(
            "fault_run_record", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class CleanupResult:
    execution_descriptor_ref: Any
    cleanup_status: str = "CLEAN"
    residual_artifacts_cleared: bool = True
    cleanup_result_id: str | None = None

    def __post_init__(self):
        if self.cleanup_result_id is None:
            object.__setattr__(self, "cleanup_result_id", new_id("cleanup_result"))
        elif self.cleanup_result_id.startswith("cleanup_result_"):
            validate_id(self.cleanup_result_id, "cleanup_result")

    def body(self) -> dict:
        return {
            "cleanup_result_id": self.cleanup_result_id or "cleanup_default",
            "execution_descriptor_ref": _ref_dict(self.execution_descriptor_ref),
            "cleanup_status": self.cleanup_status,
            "residual_artifacts_cleared": self.residual_artifacts_cleared,
        }

    def as_object(self) -> CanonicalObject:
        lid = self.cleanup_result_id if (self.cleanup_result_id and self.cleanup_result_id.startswith("cleanup_result_")) else None
        return CanonicalObject(
            "cleanup_result", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest


@dataclass(frozen=True)
class ExecutionResult:
    execution_descriptor_ref: Any
    exit_code: int = 0
    status: str = "SUCCESS"
    observation_refs: Sequence[Any] = ()
    fault_activation_record_ref: Any = None
    cleanup_result_ref: Any = None
    execution_result_id: str | None = None

    def __post_init__(self):
        if self.execution_result_id is None:
            object.__setattr__(self, "execution_result_id", new_id("execution_result"))
        elif self.execution_result_id.startswith("execution_result_"):
            validate_id(self.execution_result_id, "execution_result")

        object.__setattr__(
            self, "observation_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.observation_refs]))
        )

    def body(self) -> dict:
        data = {
            "execution_result_id": self.execution_result_id or "result_default",
            "execution_descriptor_ref": _ref_dict(self.execution_descriptor_ref),
            "exit_code": self.exit_code,
            "status": self.status,
            "observation_refs": list(self.observation_refs),
        }
        if self.fault_activation_record_ref is not None:
            data["fault_activation_record_ref"] = _ref_dict(self.fault_activation_record_ref)
        if self.cleanup_result_ref is not None:
            data["cleanup_result_ref"] = _ref_dict(self.cleanup_result_ref)
        return data

    def as_object(self) -> CanonicalObject:
        lid = self.execution_result_id if (self.execution_result_id and self.execution_result_id.startswith("execution_result_")) else None
        return CanonicalObject(
            "execution_result", self.body(), logical_id=lid
        )

    @property
    def digest(self) -> str:
        return self.as_object().digest

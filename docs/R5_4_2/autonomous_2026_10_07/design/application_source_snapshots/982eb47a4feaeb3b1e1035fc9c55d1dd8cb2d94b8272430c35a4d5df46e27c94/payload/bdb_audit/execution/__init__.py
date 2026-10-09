"""BDB Audit v2 Experiment and Execution module (M19)."""
from .models import (
    ExperimentSpec,
    ExecutionDescriptor,
    FaultRunRecord,
    CleanupResult,
    ExecutionResult,
)
from .dag import (
    validate_execution_dag,
    parse_edges,
)
from .adapters import (
    ExecutionAdapter,
    EXPERIMENT_TYPES,
    ExecutionRunOutput,
)
from .fuzzing import (
    FuzzerCapability,
    FuzzerCase,
    create_fuzzer_case,
    FuzzerExecutionRecord,
    FuzzerAdapter,
    DeterministicFuzzerAdapter,
    process_fuzz_result_through_pipeline,
    validate_no_direct_crash_to_finding,
)
from .differential import (
    SEMANTIC_RELATIONS,
    DifferentialPathConfig,
    DifferentialExecutionResult,
    compare_semantic_relation,
    DifferentialTestingFramework,
    process_differential_result_through_pipeline,
    validate_no_direct_diff_to_finding,
)
from .metamorphic import (
    MetamorphicTransformation,
    create_metamorphic_transformation,
    MetamorphicRelationSpec,
    MetamorphicExecutionRecord,
    check_metamorphic_relation,
    MetamorphicTestingFramework,
    process_metamorphic_result_through_pipeline,
    validate_no_direct_metamorphic_to_finding,
)

__all__ = [
    "ExperimentSpec",
    "ExecutionDescriptor",
    "FaultRunRecord",
    "CleanupResult",
    "ExecutionResult",
    "validate_execution_dag",
    "parse_edges",
    "ExecutionAdapter",
    "EXPERIMENT_TYPES",
    "ExecutionRunOutput",
    "FuzzerCapability",
    "FuzzerCase",
    "create_fuzzer_case",
    "FuzzerExecutionRecord",
    "FuzzerAdapter",
    "DeterministicFuzzerAdapter",
    "process_fuzz_result_through_pipeline",
    "validate_no_direct_crash_to_finding",
    "SEMANTIC_RELATIONS",
    "DifferentialPathConfig",
    "DifferentialExecutionResult",
    "compare_semantic_relation",
    "DifferentialTestingFramework",
    "process_differential_result_through_pipeline",
    "validate_no_direct_diff_to_finding",
    "MetamorphicTransformation",
    "create_metamorphic_transformation",
    "MetamorphicRelationSpec",
    "MetamorphicExecutionRecord",
    "check_metamorphic_relation",
    "MetamorphicTestingFramework",
    "process_metamorphic_result_through_pipeline",
    "validate_no_direct_metamorphic_to_finding",
]




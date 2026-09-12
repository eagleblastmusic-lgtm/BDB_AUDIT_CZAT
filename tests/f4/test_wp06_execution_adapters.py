"""Targeted tests for Work Package 6 (PR-F4-06): Experiment & Execution Adapters and DAG Acyclicity."""
import hashlib
import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id, deterministic_id
from bdb_audit.execution import (
    ExperimentSpec,
    ExecutionDescriptor,
    FaultRunRecord,
    CleanupResult,
    ExecutionResult,
    validate_execution_dag,
    ExecutionAdapter,
    EXPERIMENT_TYPES,
    ExecutionRunOutput,
)


def make_ref(kind: str, seed: str, logical_id: str | None = None) -> dict:
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": "CONTENT_OR_PRIOR",
        **({"logical_id": logical_id} if logical_id else {}),
    }


def make_test_experiment(exp_id: str, requirements: list[str] | None = None) -> ExperimentSpec:
    return ExperimentSpec(
        experiment_id=exp_id,
        experiment_revision="1",
        hypothesis_revision_ref=make_ref("hypothesis_revision", "hyp_1"),
        invariant_revision_ref=make_ref("invariant_revision", "inv_1"),
        coverage_obligation_refs=[make_ref("coverage_obligation", "ob_1")],
        subject_baseline_ref=make_ref("source_identity", "src_1"),
        target_execution_variant_ref=make_ref("variant", "v1"),
        environment_profile_ref=make_ref("environment_profile", "env_1"),
        dependency_set_ref=make_ref("dependency_set", "dep_1"),
        harness_ref=make_ref("harness", "pytest"),
        fixture_refs=[make_ref("fixture", "fix_1")],
        trigger="INVOKE_ENDPOINT",
        expected_safe_behavior="200 OK",
        expected_buggy_behavior="500 Internal Error",
        observation_path_requirements=requirements or ["HTTP_CLIENT", "LOG_INSPECTOR"],
        falsification_condition="status != 200",
        positive_controls=["test_happy_path"],
        negative_controls=["test_missing_param"],
        input_history_cut={"tag": "CUT_001"},
    )


def test_experiment_production_taxonomy():
    """Verify standard 14 normative experiment types are present."""
    expected = {
        "STATIC_ANALYSIS", "DYNAMIC", "FAULT_INJECTION", "FUZZ", "PROPERTY",
        "DIFFERENTIAL", "METAMORPHIC", "STATEFUL", "CONCURRENCY", "ENDURANCE",
        "IMPLEMENTATION_MUTATION", "ORACLE_CHALLENGE", "MODEL_CONFORMANCE", "REPLAY",
    }
    assert expected.issubset(EXPERIMENT_TYPES)


def test_two_phase_execution_and_dag_formation():
    """Verify preregistration before an explicit real runner and valid DAG formation."""
    adapter = ExecutionAdapter()
    exp_id = new_id("experiment_spec")
    spec = make_test_experiment(exp_id, requirements=["HTTP_CLIENT", "LOG_INSPECTOR"])

    executor_profile = {
        "executor_name": "pytest_local",
        "allowed_techniques": ["HTTP_CLIENT", "LOG_INSPECTOR", "FAULT_SIMULATOR"],
    }
    attempt_ref = make_ref("attempt", "att_1")
    history_cut = {"tag": "CUT_001", "commit_seq": 10}
    env_actuals = {"os": "windows", "python": "3.14"}

    seen = []

    def explicit_runner(desc):
        seen.append(desc.execution_descriptor_id)
        return ExecutionRunOutput(
            exit_code=0,
            status="SUCCESS",
            raw_observations=[make_ref("observation", "obs_explicit_runner")],
        )

    desc, res, obs, clean, fault = adapter.execute_experiment(
        experiment_spec=spec,
        executor_profile=executor_profile,
        attempt_ref=attempt_ref,
        history_cut=history_cut,
        environment_actuals=env_actuals,
        execution_nonce="nonce_12345",
        runner_fn=explicit_runner,
    )

    assert desc.as_object().kind == "execution_descriptor"
    assert res.as_object().kind == "execution_result"
    assert clean.as_object().kind == "cleanup_result"
    assert seen == [desc.execution_descriptor_id]
    assert res.exit_code == 0
    assert res.status == "SUCCESS"
    assert len(obs) == 1


def test_missing_runner_is_truthful_non_execution():
    adapter = ExecutionAdapter()
    spec = make_test_experiment(new_id("experiment_spec"), requirements=["HTTP_CLIENT"])
    desc, res, obs, clean, fault = adapter.execute_experiment(
        experiment_spec=spec,
        executor_profile={"allowed_techniques": ["HTTP_CLIENT"]},
        attempt_ref=make_ref("attempt", "no_runner"),
        history_cut={"tag": "CUT_001"},
        environment_actuals={"os": "windows"},
        execution_nonce="nonce_no_runner",
    )
    assert desc.as_object().kind == "execution_descriptor"
    assert res.status == "UNSUPPORTED"
    assert res.exit_code != 0
    assert obs == []
    assert fault is None
    assert clean.cleanup_status == "CLEAN"


def test_capability_enforcement_boundary():
    adapter = ExecutionAdapter()
    exp_id = new_id("experiment_spec")
    spec = make_test_experiment(exp_id, requirements=["CONCURRENCY_SANITIZER"])
    underprivileged_executor = {
        "executor_name": "simple_http",
        "allowed_techniques": ["HTTP_CLIENT"],
    }
    with pytest.raises(ValidationError, match="EXECUTOR_CAPABILITY_EXCEEDED"):
        adapter.execute_experiment(
            experiment_spec=spec,
            executor_profile=underprivileged_executor,
            attempt_ref=make_ref("attempt", "att_1"),
            history_cut={"tag": "CUT_001"},
            environment_actuals={"os": "windows"},
            execution_nonce="nonce_underprivileged",
        )


def test_fault_injection_activation_tracking():
    adapter = ExecutionAdapter()
    spec = make_test_experiment(new_id("experiment_spec"), requirements=["FAULT_SIMULATOR"])
    executor_profile = {"allowed_techniques": ["FAULT_SIMULATOR"]}

    fault_spec = {
        "fault_id": "fault_disk_full",
        "kind": "fault_spec",
        "revision_digest": hashlib.sha256(b"disk_full").hexdigest(),
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::fault_spec/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }

    def custom_runner(desc):
        return ExecutionRunOutput(
            exit_code=0,
            status="SUCCESS",
            raw_observations=[make_ref("observation", "obs_fault_1")],
            fault_activated=True,
            cleanup_status="CLEAN",
        )

    desc, res, obs, clean, fault = adapter.execute_experiment(
        experiment_spec=spec,
        executor_profile=executor_profile,
        attempt_ref=make_ref("attempt", "att_1"),
        history_cut={"tag": "CUT_001"},
        environment_actuals={"os": "windows"},
        execution_nonce="nonce_fault_activated",
        runner_fn=custom_runner,
        fault_spec=fault_spec,
    )

    assert fault is not None
    assert fault.activation_status == "ACTIVATED"
    assert res.fault_activation_record_ref is not None


def test_execution_dag_cycle_detection():
    valid_edges = [
        ("desc_1", "clean_1"),
        ("clean_1", "res_1"),
        ("desc_1", "res_1"),
    ]
    res_valid = validate_execution_dag(valid_edges)
    assert res_valid["result"] == "ACCEPT"

    cyclic_edges = [
        ("desc_1", "res_1"),
        ("res_1", "desc_1"),
    ]
    with pytest.raises(ValidationError, match="CONTENT_REFERENCE_CYCLE"):
        validate_execution_dag(cyclic_edges)


def test_idempotency_same_descriptor_and_nonce():
    adapter = ExecutionAdapter()
    spec = make_test_experiment(new_id("experiment_spec"), requirements=["BASIC"])
    executor_profile = {"allowed_techniques": ["BASIC"]}

    run_counter = [0]

    def counting_runner(desc):
        run_counter[0] += 1
        return ExecutionRunOutput(exit_code=0, status="SUCCESS")

    desc1, res1, _, _, _ = adapter.execute_experiment(
        experiment_spec=spec,
        executor_profile=executor_profile,
        attempt_ref=make_ref("attempt", "att_1"),
        history_cut={"tag": "CUT_001"},
        environment_actuals={"os": "windows"},
        execution_nonce="nonce_idempotent",
        runner_fn=counting_runner,
    )
    assert run_counter[0] == 1

    desc2, res2, _, _, _ = adapter.execute_experiment(
        experiment_spec=spec,
        executor_profile=executor_profile,
        attempt_ref=make_ref("attempt", "att_1"),
        history_cut={"tag": "CUT_001"},
        environment_actuals={"os": "windows"},
        execution_nonce="nonce_idempotent",
        runner_fn=counting_runner,
    )
    assert run_counter[0] == 1
    assert desc1.digest == desc2.digest
    assert res1.digest == res2.digest

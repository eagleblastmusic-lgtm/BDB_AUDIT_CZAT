"""Targeted unit and negative tests for PR-023 / M19 experiment and execution binding."""
import hashlib
import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id
from bdb_audit.core.registry import load_vectors
from bdb_audit.execution import (
    ExperimentSpec, ExecutionDescriptor, FaultRunRecord,
    CleanupResult, ExecutionResult, validate_execution_dag,
)
from bdb_audit.schemas.foundation import F3_KINDS, foundation_schema_bindings
from bdb_audit.schemas.identity import LayeredValidator


def ref(kind, seed, ref_class="CONTENT_OR_PRIOR", logical_id=None):
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
        **({"logical_id": logical_id} if logical_id else {}),
    }


def test_fr04_golden_vectors():
    vectors = load_vectors()["vectors"]
    by_id = {v["id"]: v for v in vectors}

    # FR04_FAULT_DAG_ACCEPT
    v_fault = by_id["FR04_FAULT_DAG_ACCEPT"]
    res_fault = validate_execution_dag(v_fault["input"]["edges"])
    assert res_fault["acyclic"] == v_fault["expected"]["acyclic"]
    assert res_fault["result"] == v_fault["expected"]["result"]

    # FR04_NOFAULT_DAG_ACCEPT
    v_nofault = by_id["FR04_NOFAULT_DAG_ACCEPT"]
    res_nofault = validate_execution_dag(v_nofault["input"]["edges"])
    assert res_nofault["acyclic"] == v_nofault["expected"]["acyclic"]
    assert res_nofault["result"] == v_nofault["expected"]["result"]

    # FR04_RESULT_BACKLINK_CYCLE_REJECT
    v_cycle = by_id["FR04_RESULT_BACKLINK_CYCLE_REJECT"]
    with pytest.raises(ValidationError, match=v_cycle["expected"]["error"]):
        validate_execution_dag(v_cycle["input"]["edges"])


def test_experiment_spec_and_execution_binding():
    cut = {"tag": "EMPTY_HISTORY"}
    h_ref = ref("hypothesis_revision", "hypo_1")
    inv_ref = ref("invariant_revision", "inv_1")
    ob_ref = ref("coverage_obligation", "ob_1")
    subj_ref = ref("source_generation", "gen_1")
    variant_ref = ref("external_profile_ref", "variant_1")
    env_ref = ref("external_profile_ref", "env_1")
    dep_ref = ref("external_profile_ref", "dep_1")
    harness_ref = ref("external_profile_ref", "harness_1")
    fix_ref = ref("compatibility_fixture_assessment", "fix_1")

    exp = ExperimentSpec(
        experiment_id=new_id("experiment_spec"),
        experiment_revision="1",
        hypothesis_revision_ref=h_ref,
        invariant_revision_ref=inv_ref,
        coverage_obligation_refs=[ob_ref],
        subject_baseline_ref=subj_ref,
        target_execution_variant_ref=variant_ref,
        environment_profile_ref=env_ref,
        dependency_set_ref=dep_ref,
        harness_ref=harness_ref,
        fixture_refs=[fix_ref],
        trigger="run_concurrency_test",
        expected_safe_behavior="Deterministic serialization with no race",
        expected_buggy_behavior="Concurrent writes cause partial state overwrite",
        observation_path_requirements=["stdout", "sqlite_journal"],
        falsification_condition="State hash != expected after 100 concurrent workers",
        positive_controls=["single_threaded_write"],
        negative_controls=["unauthenticated_write"],
        input_history_cut=cut,
    )
    assert len(exp.digest) == 64
    assert exp.as_object().kind == "experiment_spec"

    desc = ExecutionDescriptor(
        execution_descriptor_id=new_id("execution_descriptor"),
        experiment_spec_ref=exp.as_object().as_ref().as_dict(),
        executor_profile_ref=ref("executor_spec", "exec_1"),
        attempt_ref=ref("attempt", "att_1"),
        input_history_cut=cut,
        environment_actuals={"python_version": "3.14"},
        execution_nonce="nonce_12345",
    )
    assert len(desc.digest) == 64
    assert desc.as_object().kind == "execution_descriptor"

    cleanup = CleanupResult(
        cleanup_result_id=new_id("cleanup_result"),
        execution_descriptor_ref=desc.as_object().as_ref().as_dict(),
        cleanup_status="CLEAN",
        residual_artifacts_cleared=True,
    )
    assert len(cleanup.digest) == 64

    res = ExecutionResult(
        execution_result_id=new_id("execution_result"),
        execution_descriptor_ref=desc.as_object().as_ref().as_dict(),
        exit_code=0,
        status="SUCCESS",
        observation_refs=[ref("observation", "obs_1")],
        cleanup_result_ref=cleanup.as_object().as_ref().as_dict(),
    )
    assert len(res.digest) == 64


def test_m19_schemas_with_layered_validator():
    bindings = foundation_schema_bindings(kinds=F3_KINDS)
    validator = LayeredValidator(bindings=bindings)

    cut = {"tag": "EMPTY_HISTORY"}
    desc = ExecutionDescriptor(
        execution_descriptor_id=new_id("execution_descriptor"),
        experiment_spec_ref=ref("experiment_spec", "exp_1"),
        executor_profile_ref=ref("executor_spec", "exec_1"),
        attempt_ref=ref("attempt", "att_1"),
        input_history_cut=cut,
        environment_actuals={"node": "v20"},
        execution_nonce="nonce_9876",
    )
    val = validator.validate("execution_descriptor", canonical_bytes(desc.body()))
    assert val.revision_digest == desc.digest

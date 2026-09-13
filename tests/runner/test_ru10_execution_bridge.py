from __future__ import annotations

from pathlib import Path
import sys

from bdb_audit.execution.models import ExecutionDescriptor
from bdb_audit.runner.bridge import make_execution_runner
from bdb_audit.runner.specs import ToolRunSpec
from bdb_audit.runner.supervisor import ToolSupervisor


def _descriptor() -> ExecutionDescriptor:
    ref = {
        "kind": "reference_target",
        "revision_digest": "a" * 64,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::reference_target/1",
        "ref_class": "PINNED_INSTALLATION_REF",
    }
    return ExecutionDescriptor(
        experiment_spec_ref=ref,
        executor_profile_ref=ref,
        attempt_ref=ref,
        input_history_cut={"variant": "EMPTY_HISTORY_CUT"},
        environment_actuals={},
        execution_nonce="bridge-test",
        execution_descriptor_id="bridge-descriptor",
    )


def test_ru10_bridge_does_not_invent_observation_from_zero_exit(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()

    def spec_factory(_descriptor: ExecutionDescriptor) -> ToolRunSpec:
        return ToolRunSpec(
            run_id="bridge-zero",
            source_root=str(source),
            evidence_dir=str(tmp_path / "evidence"),
            argv=(sys.executable, "-c", "print('zero-exit-is-not-evidence')"),
        )

    output = make_execution_runner(ToolSupervisor(), spec_factory)(_descriptor())
    assert output.status == "SUCCESS"
    assert output.exit_code == 0
    assert output.raw_observations == ()


def test_ru10_bridge_only_uses_explicit_observation_normalizer(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    observation_ref = {
        "kind": "observation",
        "revision_digest": "b" * 64,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::observation/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }

    def spec_factory(_descriptor: ExecutionDescriptor) -> ToolRunSpec:
        return ToolRunSpec(
            run_id="bridge-normalized",
            source_root=str(source),
            evidence_dir=str(tmp_path / "evidence"),
            argv=(sys.executable, "-c", "print('raw')"),
        )

    output = make_execution_runner(
        ToolSupervisor(),
        spec_factory,
        observation_normalizer=lambda _result: (observation_ref,),
    )(_descriptor())
    assert output.raw_observations == (observation_ref,)


def test_ru10_bridge_maps_blocked_to_unsupported_without_observations(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()

    def spec_factory(_descriptor: ExecutionDescriptor) -> ToolRunSpec:
        return ToolRunSpec(
            run_id="bridge-blocked",
            source_root=str(source),
            evidence_dir=str(tmp_path / "evidence"),
            argv=(sys.executable, "-c", "print('must not run')"),
            require_network_isolation=True,
        )

    output = make_execution_runner(ToolSupervisor(), spec_factory)(_descriptor())
    assert output.status == "UNSUPPORTED"
    assert output.exit_code == 125
    assert output.raw_observations == ()

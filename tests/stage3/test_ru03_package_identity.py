from __future__ import annotations

from pathlib import Path

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS
from bdb_audit.workflow import packaging
from bdb_audit.workflow.packaging import prepare_e1_batch
from bdb_audit.workflow.source_target import ResolvedSource


def _store(tmp_path: Path) -> TransactionalHistoryStore:
    db = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(db, seed="ru03-d10")
    api.prepare_stage(db, "E1")
    for slot in E1_LANE_SLOTS:
        api.prepare_lane(db, "E1", slot=slot)
    return TransactionalHistoryStore(db)


def test_d10_material_prompt_change_changes_package_identity_without_reassigning(monkeypatch, tmp_path: Path) -> None:
    store = _store(tmp_path)
    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/ru03-d10",
        display_name="example/ru03-d10",
        ref="main",
        exact_commit_sha="e" * 40,
        exact_tree_sha="f" * 40,
    )

    first = prepare_e1_batch(store, tmp_path / "first", source)
    first_job = first.get_job("E1-A")

    original_builder = packaging._build_lane_prompt

    def changed_builder(*args, **kwargs):
        return original_builder(*args, **kwargs) + "\nMATERIAL PROMPT REVISION FOR D10 REGRESSION\n"

    monkeypatch.setattr(packaging, "_build_lane_prompt", changed_builder)
    changed = prepare_e1_batch(store, tmp_path / "changed", source)
    changed_job = changed.get_job("E1-A")

    assert changed_job.assignment_ref == first_job.assignment_ref
    assert changed_job.attempt_ref == first_job.attempt_ref
    assert changed_job.prompt_sha256 != first_job.prompt_sha256
    assert changed_job.package_digest != first_job.package_digest
    assert changed_job.package_zip_sha256 != first_job.package_zip_sha256

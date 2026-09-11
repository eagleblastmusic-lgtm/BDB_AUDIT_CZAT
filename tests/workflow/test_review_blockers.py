"""Comprehensive regression tests covering BDB Audit v2.0.3 review blockers.

Covers all 13 blocker items:
1. test_github_resolver_never_uses_cwd_fallback
2. test_moving_main_sha_blocks_reuse
3. test_missing_input_package_digest_rejected
4. test_missing_source_commit_sha_rejected
5. test_wrong_kind_or_version_rejected
6. test_empty_findings_do_not_fabricate_claim_supported
7. test_conflicting_replacement_result_rejected_against_accepted_lane
8. test_accepted_e1_results_visible_in_sqlite_after_reopen
9. test_stage_completion_is_accepted_history_fact_not_memory_flag
10. test_resume_reconstructs_exact_partial_state_and_completes_remaining
11. test_user_settings_serialization_preserves_new_fields
12. test_package_identity_digest_deterministic_and_binds_inputs
13. test_unsupported_executor_mode_needs_implementation
"""
from __future__ import annotations

import json
from pathlib import Path
import zipfile
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS
from bdb_audit.workflow.packaging import (
    E1Batch,
    compute_package_identity_digest,
    prepare_e1_batch,
)
from bdb_audit.workflow.platform import MockPlatformAdapter
from bdb_audit.workflow.inbox import E1ResultInbox
from bdb_audit.workflow.orchestrator import FullAuditOrchestrator
from bdb_audit.workflow.settings import SettingsManager, UserSettings
from bdb_audit.workflow.source_target import ResolvedSource, resolve_github_source


def _create_lane_zip(
    path: Path,
    batch: E1Batch,
    slot: str,
    override_manifest: dict | None = None,
    extra_files: dict[str, str] | None = None,
) -> Path:
    job = batch.get_job(slot)
    manifest = {
        "kind": "bdb_audit_lane_result",
        "version": "1",
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": slot,
        "source_commit_sha": batch.source_commit_sha,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "input_package_digest": job.package_digest,
        "history_cut": batch.frozen_history_cut,
        "findings": [
            {
                "finding_id": f"{slot}-01",
                "statement": f"Observed finding for {slot}",
                "claim_outcome": "SUPPORTED",
            }
        ],
    }
    if override_manifest:
        manifest.update(override_manifest)

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MANIFEST.json", json.dumps(manifest, indent=2))
        if extra_files:
            for name, content in extra_files.items():
                zf.writestr(name, content)
    return path


@pytest.fixture
def test_env(tmp_path: Path):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(
        store_path,
        seed="blocker_seed",
        target_repo="https://github.com/example/target-repo",
        commit_sha="a" * 40,
    )
    api.prepare_stage(store_path, "E1")
    for slot in E1_LANE_SLOTS:
        api.prepare_lane(store_path, "E1", slot=slot)

    store = TransactionalHistoryStore(store_path)
    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/target-repo",
        display_name="example/target-repo",
        ref="main",
        exact_commit_sha="a" * 40,
    )
    batch = prepare_e1_batch(store, tmp_path / "work", source)
    inbox = E1ResultInbox(store, batch)
    return store, batch, inbox, tmp_path, store_path


# 1. test_github_resolver_never_uses_cwd_fallback
def test_github_resolver_never_uses_cwd_fallback():
    """Querying an unknown/unresolvable GitHub repo must never fall back to local cwd git rev-parse."""
    with pytest.raises(ValidationError) as exc:
        resolve_github_source("https://github.com/nonexistent-org-9999/nonexistent-repo-9999", "main")
    assert "COULD_NOT_RESOLVE_EXACT_SHA" in str(exc.value)


# 2. test_moving_main_sha_blocks_reuse
def test_moving_main_sha_blocks_reuse(tmp_path: Path):
    """When a remote main branch moves to a new SHA, orchestrator halts fail-closed on mismatch or partitions store."""
    cfg_file = tmp_path / "settings.json"
    mgr = SettingsManager(config_path=cfg_file)
    mgr.settings.output_work_dir = str(tmp_path / "work")
    mgr.save()

    mock_platform = MockPlatformAdapter()
    orch = FullAuditOrchestrator(settings_mgr=mgr, platform_adapter=mock_platform)

    sha1 = "1" * 40
    sha2 = "2" * 40
    orch.resolved_source = ResolvedSource("github", "https://github.com/example/repo", "example/repo", "main", sha1)
    res1 = orch.initialize_campaign()
    store1 = Path(res1["store_path"])
    assert sha1[:12] in str(store1)

    # Moving SHA creates separate partitioned store path and halts if forced onto old store
    orch.resolved_source = ResolvedSource("github", "https://github.com/example/repo", "example/repo", "main", sha2)
    res2 = orch.initialize_campaign()
    store2 = Path(res2["store_path"])
    assert store1 != store2
    assert sha2[:12] in str(store2)

    # If an attacker points to store1 while declaring sha2, it halts fail-closed
    with pytest.raises(ValidationError) as exc:
        orch.initialize_campaign(store_path=store1)
    assert "SOURCE_IDENTITY_MISMATCH" in str(exc.value)


# 3. test_missing_input_package_digest_rejected
def test_missing_input_package_digest_rejected(test_env):
    store, batch, inbox, tmp, _ = test_env
    p = tmp / "missing_pkg_digest.zip"
    bad_manifest = {"input_package_digest": None}
    _create_lane_zip(p, batch, "E1-A", override_manifest=bad_manifest)

    slot, status, reason = inbox.ingest_zip(p)
    assert status == "REJECTED"
    assert "MISSING_INPUT_PACKAGE_DIGEST" in reason


# 4. test_missing_source_commit_sha_rejected
def test_missing_source_commit_sha_rejected(test_env):
    store, batch, inbox, tmp, _ = test_env
    p = tmp / "missing_sha.zip"
    bad_manifest = {"source_commit_sha": ""}
    _create_lane_zip(p, batch, "E1-A", override_manifest=bad_manifest)

    slot, status, reason = inbox.ingest_zip(p)
    assert status == "REJECTED"
    assert "MISSING_SOURCE_BINDING" in reason


# 5. test_wrong_kind_or_version_rejected
def test_wrong_kind_or_version_rejected(test_env):
    store, batch, inbox, tmp, _ = test_env
    p1 = tmp / "bad_kind.zip"
    _create_lane_zip(p1, batch, "E1-A", override_manifest={"kind": "wrong_contract"})
    _, status1, reason1 = inbox.ingest_zip(p1)
    assert status1 == "REJECTED"
    assert "INVALID_CONTRACT_KIND" in reason1

    p2 = tmp / "bad_version.zip"
    _create_lane_zip(p2, batch, "E1-A", override_manifest={"version": "99"})
    _, status2, reason2 = inbox.ingest_zip(p2)
    assert status2 == "REJECTED"
    assert "INVALID_CONTRACT_VERSION" in reason2


# 6. test_empty_findings_do_not_fabricate_claim_supported
def test_empty_findings_do_not_fabricate_claim_supported(test_env):
    """Clean audit with 0 vulnerabilities is valid and must NOT inject synthetic SUPPORTED claim."""
    store, batch, inbox, tmp, _ = test_env
    p = tmp / "clean_lane.zip"
    _create_lane_zip(p, batch, "E1-A", override_manifest={"findings": []})

    slot, status, reason = inbox.ingest_zip(p)
    assert status == "ACCEPTED"
    assert inbox.lane_statuses["E1-A"].findings_count == 0
    assert len(inbox.lane_statuses["E1-A"].findings) == 0


# 7. test_conflicting_replacement_result_rejected_against_accepted_lane
def test_conflicting_replacement_result_rejected_against_accepted_lane(test_env):
    """A conflicting different result submitted for an already accepted lane is rejected."""
    store, batch, inbox, tmp, _ = test_env
    p1 = tmp / "first_result.zip"
    _create_lane_zip(p1, batch, "E1-A", extra_files={"note.txt": "first submission"})
    slot1, status1, _ = inbox.ingest_zip(p1)
    assert status1 == "ACCEPTED"

    p2 = tmp / "conflicting_result.zip"
    _create_lane_zip(p2, batch, "E1-A", extra_files={"note.txt": "conflicting replacement"})
    slot2, status2, reason2 = inbox.ingest_zip(p2)
    assert status2 == "REJECTED"
    assert "CONFLICTING_RESULT" in reason2


# 8. test_accepted_e1_results_visible_in_sqlite_after_reopen
def test_accepted_e1_results_visible_in_sqlite_after_reopen(test_env):
    """Accepted lane completions are durable facts in SQLite and survive opening from scratch in a new inbox."""
    store, batch, inbox1, tmp, store_path = test_env
    p = tmp / "res_e1_a.zip"
    _create_lane_zip(p, batch, "E1-A")
    inbox1.ingest_zip(p)
    assert inbox1.lane_statuses["E1-A"].status == "ACCEPTED"

    # Open completely new store and inbox instances simulating process restart
    fresh_store = TransactionalHistoryStore(store_path)
    fresh_inbox = E1ResultInbox(fresh_store, batch)
    assert fresh_inbox.lane_statuses["E1-A"].status == "ACCEPTED"
    assert fresh_inbox.lane_statuses["E1-B"].status == "MISSING"


# 9. test_stage_completion_is_accepted_history_fact_not_memory_flag
def test_stage_completion_is_accepted_history_fact_not_memory_flag(test_env):
    """StageCompletion is written to SQLite immutable_objects and verified on fresh store inspection."""
    store, batch, inbox, tmp, store_path = test_env
    zips = [_create_lane_zip(tmp / f"{s}.zip", batch, s) for s in E1_LANE_SLOTS]
    summary = inbox.ingest_multiple_zips(zips)
    assert summary.stage_complete is True

    # Reopen fresh store and inspect directly via SQLite
    conn = TransactionalHistoryStore(store_path)._connect()
    try:
        rows = conn.execute("SELECT kind, digest, body FROM immutable_objects WHERE kind='stage_completion'").fetchall()
        assert len(rows) == 1
        doc = json.loads(rows[0][2].decode("utf-8"))
        assert doc["completion_predicate_result"] == "STAGE_COMPLETED"
    finally:
        conn.close()


# 10. test_resume_reconstructs_exact_partial_state_and_completes_remaining
def test_resume_reconstructs_exact_partial_state_and_completes_remaining(tmp_path: Path):
    """Resuming after 2/5 accepted lanes recovers 2/5 and allows completing the remaining 3/5."""
    cfg_file = tmp_path / "settings.json"
    mgr = SettingsManager(config_path=cfg_file)
    mgr.settings.output_work_dir = str(tmp_path / "work")
    mgr.save()

    orch1 = FullAuditOrchestrator(settings_mgr=mgr, platform_adapter=MockPlatformAdapter())
    orch1.resolved_source = ResolvedSource("github", "https://github.com/example/repo", "example/repo", "main", "c" * 40)
    init_res = orch1.initialize_campaign()
    batch1 = orch1.prepare_e1_orchestration()

    # Ingest only E1-A and E1-B
    zip_a = _create_lane_zip(tmp_path / "res_a.zip", batch1, "E1-A")
    zip_b = _create_lane_zip(tmp_path / "res_b.zip", batch1, "E1-B")
    orch1.import_results([zip_a, zip_b])

    # Restart orchestrator process and resume
    orch2 = FullAuditOrchestrator(settings_mgr=mgr, platform_adapter=MockPlatformAdapter())
    resumed = orch2.resume_campaign(init_res["store_path"])
    assert resumed["status"] == "SUCCESS"
    assert resumed["accepted_lanes_count"] == 2
    assert resumed["missing_lanes"] == ["E1-C", "E1-D", "E1-E"]
    assert resumed["stage_complete"] is False

    # Ingest remaining 3 lanes (E1-C, E1-D, E1-E)
    batch2 = orch2.e1_batch
    rem_zips = [_create_lane_zip(tmp_path / f"res_{s}.zip", batch2, s) for s in ("E1-C", "E1-D", "E1-E")]
    summary2 = orch2.import_results(rem_zips)
    assert summary2.accepted_count == 5
    assert summary2.stage_complete is True


# 11. test_user_settings_serialization_preserves_new_fields
def test_user_settings_serialization_preserves_new_fields(tmp_path: Path):
    """UserSettings serializes and roundtrips all declared fields cleanly."""
    cfg = tmp_path / "cfg.json"
    mgr = SettingsManager(config_path=cfg)
    mgr.settings.execution_mode = "ChatGPT / GitHub"
    mgr.settings.model = "Sol 5.6"
    mgr.settings.last_campaign_store = "C:/fake/path.sqlite"
    mgr.settings.output_work_dir = "C:/fake/work"
    mgr.settings.known_campaigns = [{"id": "c1", "store": "C:/fake/path.sqlite"}]
    mgr.save()

    loaded = SettingsManager(config_path=cfg)
    assert loaded.settings.execution_mode == "ChatGPT / GitHub"
    assert loaded.settings.model == "Sol 5.6"
    assert loaded.settings.last_campaign_store == "C:/fake/path.sqlite"
    assert loaded.settings.known_campaigns == [{"id": "c1", "store": "C:/fake/path.sqlite"}]


# 12. test_package_identity_digest_deterministic_and_binds_inputs
def test_package_identity_digest_deterministic_and_binds_inputs():
    """Package identity digest is deterministic and alters when any input parameter changes."""
    base_args = {
        "compiled_digest": "0" * 64,
        "executor_model": "Sol 5.6",
        "executor_profile": "ChatGPT / GitHub",
        "history_cut": {"campaign_id": "c1", "accepted_head_seq": 1, "accepted_head_hash": "a" * 64},
        "lane_slot": "E1-A",
        "source_commit_sha": "a" * 40,
        "source_location": "https://github.com/example/repo",
        "stage_id": "E1",
    }
    d1 = compute_package_identity_digest(**base_args)
    d2 = compute_package_identity_digest(**base_args)
    assert d1 == d2

    # Change compiled_digest
    args_compiled = dict(base_args, compiled_digest="2" * 64)
    assert compute_package_identity_digest(**args_compiled) != d1

    # Change model
    args_model = dict(base_args, executor_model="DifferentModel")
    assert compute_package_identity_digest(**args_model) != d1

    # Change commit
    args_commit = dict(base_args, source_commit_sha="b" * 40)
    assert compute_package_identity_digest(**args_commit) != d1

    # Change lane slot
    args_slot = dict(base_args, lane_slot="E1-B")
    assert compute_package_identity_digest(**args_slot) != d1


# 13. test_unsupported_executor_mode_needs_implementation
def test_unsupported_executor_mode_needs_implementation(tmp_path: Path):
    """Unsupported executor modes like Codex / Antigravity return NEEDS_IMPLEMENTATION and block."""
    cfg = tmp_path / "cfg.json"
    mgr = SettingsManager(config_path=cfg)
    mgr.settings.execution_mode = "Codex / Antigravity"
    mgr.save()

    orch = FullAuditOrchestrator(settings_mgr=mgr, platform_adapter=MockPlatformAdapter())
    report = orch.run_preflight()
    assert report.overall_status == "BLOCKED"
    exec_check = next(c for c in report.checks if c.check_name == "Executor profile")
    assert exec_check.status == "BLOCKED"
    assert "NEEDS_IMPLEMENTATION" in exec_check.details

    # Also prepare_e1_batch blocks with NEEDS_IMPLEMENTATION
    mock_store = TransactionalHistoryStore(tmp_path / "dummy.sqlite")
    mock_source = ResolvedSource("github", "https://github.com/example/repo", "example/repo", "main", "a" * 40)
    with pytest.raises(ValidationError) as exc:
        prepare_e1_batch(
            store=mock_store,
            output_dir=tmp_path,
            source_info=mock_source,
            execution_mode="Codex / Antigravity",
        )
    assert "NEEDS_IMPLEMENTATION" in str(exc.value)

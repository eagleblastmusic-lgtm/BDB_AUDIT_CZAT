"""Regression tests for conservative pre-E3 scope authority."""
from pathlib import Path

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.workflow.read_models import current_accepted_cut
from bdb_audit.workflow.scope_baseline import (
    ensure_pre_e3_scope_baseline,
)


def test_scope_baseline_is_conservative_and_idempotent(
    tmp_path: Path,
):
    store_path = tmp_path / "scope_baseline.sqlite"
    AuditOperationApi().create_campaign(
        store_path,
        seed="scope-baseline",
    )
    store = TransactionalHistoryStore(store_path)

    first = ensure_pre_e3_scope_baseline(store)
    first_head = store.head()
    assert first_head is not None
    assert first.already_present is False

    cut = current_accepted_cut(store)
    inventories = tuple(
        store.accepted_records("inventory_revision", cut)
    )
    scopes = tuple(
        store.accepted_records("scope_state_record", cut)
    )
    assert len(inventories) == 1
    assert len(scopes) == 1
    assert scopes[0]["body"]["state"] == "KNOWN_UNOBSERVED_SCOPE"
    assert scopes[0]["body"]["reason_codes"] == [
        "PRE_E3_DETAILED_INVENTORY_NOT_MATERIALIZED"
    ]
    assert inventories[0]["body"]["surface_refs"] == []
    assert inventories[0]["body"]["collector_profile_refs"] == []
    assert inventories[0]["body"]["scope_state_record_refs"]

    second = ensure_pre_e3_scope_baseline(store)
    second_head = store.head()
    assert second_head is not None
    assert second.already_present is True
    assert second.inventory_ref["revision_digest"] == (
        first.inventory_ref["revision_digest"]
    )
    assert second.scope_state_ref["revision_digest"] == (
        first.scope_state_ref["revision_digest"]
    )
    assert second_head.commit_seq == first_head.commit_seq
    assert second_head.commit_hash == first_head.commit_hash


def test_scope_baseline_augments_existing_inventory_without_losing_surfaces(
    tmp_path: Path,
):
    store_path = tmp_path / "scope_existing.sqlite"
    api = AuditOperationApi()
    api.create_campaign(
        store_path,
        seed="scope-existing",
    )
    api.prepare_stage(store_path, "E1")
    api.qualify_stage(store_path, "E1")

    store = TransactionalHistoryStore(store_path)
    before_cut = current_accepted_cut(store)
    before = tuple(
        store.accepted_records("inventory_revision", before_cut)
    )
    assert len(before) == 1
    original_surfaces = tuple(
        before[0]["body"].get("surface_refs", ())
    )
    assert original_surfaces
    assert not before[0]["body"].get(
        "scope_state_record_refs", ()
    )

    summary = ensure_pre_e3_scope_baseline(store)
    assert summary.already_present is False

    after_cut = current_accepted_cut(store)
    inventories = tuple(
        store.accepted_records("inventory_revision", after_cut)
    )
    assert len(inventories) == 2
    latest = max(
        inventories,
        key=lambda row: int(row.get("accepted_seq", 0)),
    )
    assert tuple(latest["body"]["surface_refs"]) == (
        original_surfaces
    )
    assert latest["body"]["scope_state_record_refs"]
    scopes = tuple(
        store.accepted_records("scope_state_record", after_cut)
    )
    assert len(scopes) == 1
    assert scopes[0]["body"]["state"] == "KNOWN_UNOBSERVED_SCOPE"


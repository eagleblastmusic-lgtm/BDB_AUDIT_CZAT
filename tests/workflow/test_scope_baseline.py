"""Regression tests for conservative pre-E3 scope authority."""
from pathlib import Path

from bdb_audit.coordinator import Coordinator
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.ids import deterministic_id
from bdb_audit.history.objects import CommandEnvelope
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.inventory.models import InventoryRevision, SurfaceKey, SurfaceRecord
from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS
from bdb_audit.workflow.assignments import _command_id
from bdb_audit.workflow.read_models import current_accepted_cut
from bdb_audit.workflow.inbox import E1ResultInbox
from bdb_audit.workflow.packaging import prepare_e1_batch
from bdb_audit.workflow.scope_baseline import (
    ensure_pre_e3_scope_baseline,
)
from bdb_audit.workflow.source_target import ResolvedSource


def _complete_e1_with_results(api, store_path: Path, tmp_path: Path) -> None:
    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/scope-baseline",
        display_name="example/scope-baseline",
        ref="main",
        exact_commit_sha="a" * 40,
    )
    api.create_campaign(
        store_path,
        seed="scope-existing",
        target_repo=source.location,
        commit_sha=source.exact_commit_sha,
    )
    api.prepare_stage(store_path, "E1")
    for slot in E1_LANE_SLOTS:
        api.prepare_lane(store_path, "E1", slot=slot)

    store = TransactionalHistoryStore(store_path)
    batch = prepare_e1_batch(
        store=store,
        output_dir=tmp_path / "work",
        source_info=source,
    )
    # Reuse the existing valid E1 result manifest builder from the manual-stage
    # transport tests; accepted inbox processing produces the inventory under test.
    from tests.workflow.test_manual_stage import _write_e1_result

    summary = E1ResultInbox(store, batch).ingest_multiple_zips(
        [
            _write_e1_result(
                tmp_path / f"e1_{slot}.zip",
                batch,
                slot,
            )
            for slot in E1_LANE_SLOTS
        ]
    )
    assert summary.stage_complete is True


def _seed_existing_inventory_with_surface(store: TransactionalHistoryStore) -> None:
    """Seed a real prior inventory record for the augmentation regression."""
    cut = current_accepted_cut(store)
    source_generation = store.accepted_records("source_generation", cut)[0]
    source_identity = store.accepted_records("source_identity", cut)[0]
    source_identity_ref = dict(source_identity["ref"])
    source_identity_ref["ref_class"] = "CONTENT_OR_PRIOR"
    source_identity_prior_ref = dict(source_identity["ref"])
    source_identity_prior_ref["ref_class"] = "PRIOR_ACCEPTED_ONLY"
    source_generation_ref = dict(source_generation["ref"])
    source_generation_ref["ref_class"] = "PRIOR_ACCEPTED_ONLY"

    surface_key = SurfaceKey(
        source_identity_ref=source_identity_ref,
        canonical_surface_category="HTTP_ROUTE",
        normalized_anchor_descriptor={"path": "README.md"},
    ).as_object()
    surface_key_ref = surface_key.as_ref(ref_class="CONTENT_OR_PRIOR").as_dict()
    surface_record = SurfaceRecord(
        surface_key=surface_key_ref,
        source_identity_ref=source_identity_prior_ref,
        surface_category="HTTP_ROUTE",
        anchor_descriptor={"path": "README.md"},
        surface_record_id=deterministic_id(
            "surface_record", "scope-baseline-existing-surface"
        ),
    ).as_object()
    inventory = InventoryRevision(
        inventory_id=deterministic_id(
            "inventory_revision", "scope-baseline-existing-inventory"
        ),
        inventory_revision="1",
        source_generation_ref=source_generation_ref,
        basis_history_cut=cut,
        surface_refs=(
            surface_record.as_ref(ref_class="CONTENT_OR_PRIOR").as_dict(),
        ),
    ).as_object()

    head = store.head()
    assert head is not None
    prior_commit = store.commits()[-1]
    command = CommandEnvelope(
        command_id=_command_id(
            "scope_baseline_existing_inventory:" + inventory.digest
        ),
        command_kind="RECORD_FOUNDATION_FACT",
        actor_ref=prior_commit["actor_ref"],
        expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
        governing_policy_ref=prior_commit["governing_policy_ref"],
        governing_spec_refs=tuple(prior_commit["governing_spec_refs"]),
        idempotency_scope=(
            "scope_baseline_existing_inventory:" + inventory.digest
        ),
        campaign_ref=head.campaign_id,
    )
    Coordinator(store).accept(
        command,
        immutable_objects=(surface_key, surface_record, inventory),
        expected_head=head,
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
    _complete_e1_with_results(api, store_path, tmp_path)

    store = TransactionalHistoryStore(store_path)
    _seed_existing_inventory_with_surface(store)
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
    assert latest["body"]["inventory_id"] == (
        before[0]["body"]["inventory_id"]
    )
    assert latest["body"]["inventory_revision"] == "2"
    assert tuple(latest["body"]["surface_refs"]) == (
        original_surfaces
    )
    assert latest["body"]["scope_state_record_refs"]
    scopes = tuple(
        store.accepted_records("scope_state_record", after_cut)
    )
    assert len(scopes) == 1
    assert scopes[0]["body"]["state"] == "KNOWN_UNOBSERVED_SCOPE"

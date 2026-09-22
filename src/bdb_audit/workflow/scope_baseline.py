"""Conservative pre-E3 scope authority bootstrap.

The external E1/E2 workflow can legitimately complete before domain collectors
have materialized a detailed InventoryRevision.  E3-GAP and post-E5 STOP still
need an accepted scope denominator, so this service records one explicit
KNOWN_UNOBSERVED_SCOPE rather than fabricating surfaces or coverage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..coordinator import Coordinator
from ..core.errors import ValidationError
from ..core.ids import deterministic_id
from ..history.objects import CommandEnvelope
from ..history.store import TransactionalHistoryStore
from ..inventory.models import InventoryRevision, ScopeStateRecord
from .assignments import _command_id, _current_cut


@dataclass(frozen=True)
class ScopeBaselineSummary:
    inventory_ref: dict[str, Any]
    scope_state_ref: dict[str, Any]
    accepted_commit_seq: int
    already_present: bool


def _with_ref_class(ref: dict[str, Any], ref_class: str) -> dict[str, Any]:
    result = dict(ref)
    result["ref_class"] = ref_class
    return result


def ensure_pre_e3_scope_baseline(
    store: TransactionalHistoryStore,
) -> ScopeBaselineSummary:
    """Ensure a fail-closed inventory exists before E3.

    This is deliberately a denominator bootstrap, not a claim of completed
    collection.  When no real inventory exists yet, the frozen source
    generation is represented by one KNOWN_UNOBSERVED_SCOPE.  Later collector
    runs may supersede it with richer immutable InventoryRevision objects.
    """
    cut, prior_commit = _current_cut(store)
    source_rows = tuple(
        store.accepted_records("source_generation", cut)
    )
    if not source_rows:
        raise ValidationError("SOURCE_GENERATION_REQUIRED")
    source = max(
        source_rows,
        key=lambda row: int(row.get("accepted_seq", 0)),
    )
    source_digest = source["ref"]["revision_digest"]

    inventories = [
        row
        for row in store.accepted_records(
            "inventory_revision", cut
        )
        if row["body"].get(
            "source_generation_ref", {}
        ).get("revision_digest")
        == source_digest
    ]
    if inventories:
        inventory = max(
            inventories,
            key=lambda row: int(row.get("accepted_seq", 0)),
        )
        scope_refs = inventory["body"].get(
            "scope_state_record_refs", []
        )
        if not scope_refs:
            raise ValidationError(
                "INVENTORY_SCOPE_DENOMINATOR_REQUIRED"
            )
        scope_ref = dict(scope_refs[0])
        return ScopeBaselineSummary(
            inventory_ref=_with_ref_class(
                inventory["ref"], "CONTENT_OR_PRIOR"
            ),
            scope_state_ref=scope_ref,
            accepted_commit_seq=int(
                inventory.get("accepted_seq", 0)
            ),
            already_present=True,
        )

    head = store.head()
    if head is None:
        raise ValidationError("CAMPAIGN_NOT_INITIALIZED")

    seed = (
        f"{head.campaign_id}:{source_digest}:"
        "pre-e3-scope-baseline"
    )
    scope = ScopeStateRecord(
        scope_key=f"source_generation:{source_digest}",
        state="KNOWN_UNOBSERVED_SCOPE",
        scope_state_input_history_cut=cut,
        basis_refs=(
            _with_ref_class(
                source["ref"], "CONTENT_OR_PRIOR"
            ),
        ),
        reason_codes=(
            "PRE_E3_DETAILED_INVENTORY_NOT_MATERIALIZED",
        ),
        scope_state_record_id=deterministic_id(
            "scope_state_record", seed
        ),
    )
    scope_obj = scope.as_object()

    inventory = InventoryRevision(
        inventory_id=deterministic_id(
            "inventory_revision", seed
        ),
        inventory_revision="1",
        source_generation_ref=_with_ref_class(
            source["ref"], "PRIOR_ACCEPTED_ONLY"
        ),
        basis_history_cut=cut,
        collector_profile_refs=(),
        assigned_input_refs=(),
        input_disposition_refs=(),
        surface_refs=(),
        scope_state_record_refs=(
            scope_obj.as_ref(
                ref_class="CONTENT_OR_PRIOR"
            ).as_dict(),
        ),
        manual_runtime_additions=(),
        unresolved_scope_refs=(),
    )
    inventory_obj = inventory.as_object()

    command = CommandEnvelope(
        command_id=_command_id(
            "pre_e3_scope_baseline:"
            + inventory_obj.digest
        ),
        command_kind="RECORD_FOUNDATION_FACT",
        actor_ref=prior_commit.get(
            "actor_ref", "installation-owner"
        ),
        expected_parent_head={
            "tag": "ACCEPTED_HEAD_REF",
            **head.as_dict(),
        },
        governing_policy_ref=prior_commit[
            "governing_policy_ref"
        ],
        governing_spec_refs=tuple(
            prior_commit.get("governing_spec_refs", ())
        ),
        idempotency_scope=(
            "pre_e3_scope_baseline:"
            + inventory_obj.digest
        ),
        campaign_ref=head.campaign_id,
    )
    accepted = Coordinator(store).accept(
        command,
        immutable_objects=[scope_obj, inventory_obj],
        expected_head=head,
    )
    return ScopeBaselineSummary(
        inventory_ref=inventory_obj.as_ref(
            ref_class="CONTENT_OR_PRIOR"
        ).as_dict(),
        scope_state_ref=scope_obj.as_ref(
            ref_class="CONTENT_OR_PRIOR"
        ).as_dict(),
        accepted_commit_seq=accepted.head.commit_seq,
        already_present=False,
    )


__all__ = [
    "ScopeBaselineSummary",
    "ensure_pre_e3_scope_baseline",
]

"""Data 8.3 prior accepted alias conflict: real durable store, no qualification."""
from dataclasses import replace
import sys
import uuid

from execution import ROOT, write, preserve


def main():
    preserve()
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from bdb_audit.core.errors import ValidationError
    from bdb_audit.history.objects import CanonicalObject
    from bdb_audit.history.store import TransactionalHistoryStore
    from tests.f2.helpers import bootstrap_fixture

    root = ROOT / "._nf02_current_audit/data" / ("alias-prior-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    profile, command, objects, parts = bootstrap_fixture()
    store = TransactionalHistoryStore(root / "history.sqlite")
    first = store.accept(command, immutable_objects=objects, bootstrap_profile=profile)
    original = parts["source_generation"]
    changed = dict(original.body)
    changed["source_generation_id"] = "conflicting_second_alias"
    conflicting = CanonicalObject("source_generation", changed)
    follow = replace(command, command_id="command_323e4567-e89b-42d3-a456-426614174000",
                     command_kind="RECORD_FOUNDATION_FACT", campaign_ref="campaign_fixture",
                     expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **first.head.as_dict()},
                     proposed_campaign_id=None, history_namespace_ref=None, bootstrap_profile_ref=None)
    before = (store.head(), store.commits())
    try:
        store.accept(follow, expected_head=first.head, immutable_objects=(conflicting,))
    except ValidationError as exc:
        assert "SOURCE_IDENTITY_CONFLICT" in str(exc), str(exc)
    else:
        raise AssertionError("Prior accepted identity acquired a second alias")
    assert (store.head(), store.commits()) == before
    assert store.receipt(follow.command_id) is None
    reopened = TransactionalHistoryStore(root / "history.sqlite")
    assert (reopened.head(), reopened.commits()) == before
    retry = reopened.accept(command, immutable_objects=objects, bootstrap_profile=profile)
    assert retry.head == first.head and retry.receipt.digest == first.receipt.digest
    write("design/source_instance_readback/diagnostics/" + root.name + ".json", {
        "retained_database": str(root / "history.sqlite"), "qualification": False})
    write("design/SOURCE_ALIAS_PRIOR_DURABILITY_CONTROLS.json", {
        "controls": [{"case": name, "result": "PASS"} for name in (
            "PRIOR_ACCEPTED_EXACT_IDENTITY_SECOND_ALIAS_REJECTED",
            "REJECTION_PRESERVES_HEAD_COMMITS_AND_RECEIPT",
            "REOPEN_RETAINS_ORIGINAL_HISTORY",
            "EXACT_BOOTSTRAP_RETRY_REUSES_ORIGINAL_RECEIPT")],
        "qualification": False, "successor_schema_binding": "NOT_PROVEN", "NF02": "OPEN"})
    print("4 prior-history alias durability controls PASS")


if __name__ == "__main__":
    main()

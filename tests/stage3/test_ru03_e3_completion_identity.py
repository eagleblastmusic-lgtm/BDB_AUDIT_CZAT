from __future__ import annotations

import hashlib

from bdb_audit.orchestration.e3 import (
    E3_LANE_SLOTS,
    create_e3_blind_attempt,
    execute_e3_blind_ensemble,
)
from bdb_audit.orchestration.e3_reveal import create_e3_blind_checkpoint


def _ref(kind: str, seed: str) -> dict[str, str]:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }


def _cut(seq: int = 7) -> dict[str, object]:
    return {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": "camp_ru03_d21",
        "accepted_head_seq": seq,
        "accepted_head_hash": hashlib.sha256(f"cut-{seq}".encode("utf-8")).hexdigest(),
        "governing_policy_ref": "BDB_POLICY_REGISTRY::governing_policy/1",
        "governing_spec_refs": ["BDB_SPEC_REGISTRY::e3_spec/1"],
    }


def _contexts(cut: dict[str, object]):
    executor_ref = _ref("executor_profile", "executor")
    delivery_ref = _ref("delivery_profile", "delivery")
    return {
        slot: create_e3_blind_attempt(
            lane_slot=slot,
            lane_run_ref=_ref("lane_run", f"lane-run-{slot}"),
            assigned_history_cut=cut,
            executor_profile_ref=executor_ref,
            delivery_profile_ref=delivery_ref,
            channel_inventory_ref=_ref(
                "registered_immutable_object",
                "ru03_e3_channel_inventory",
            ),
            nonce=f"ru03_{slot.lower().replace('-', '_')}",
        )
        for slot in E3_LANE_SLOTS
    }


def _execute(discoveries: dict[str, list[dict[str, object]]]):
    cut = _cut()
    result = execute_e3_blind_ensemble(
        source_generation_ref=_ref("source_generation", "source"),
        assigned_history_cut=cut,
        lane_contexts=_contexts(cut),
        lane_discoveries=discoveries,
    )
    return result, cut


def test_d21_same_count_changed_discovery_changes_blind_completion_and_checkpoint() -> None:
    first, first_cut = _execute(
        {
            "E3-X": [{"statement": "Authority boundary rejects stale grant", "severity": "HIGH"}],
            "E3-Y": [{"statement": "Recovery journal preserves committed state", "severity": "MEDIUM"}],
            "E3-Z": [],
        }
    )
    changed, changed_cut = _execute(
        {
            "E3-X": [{"statement": "Authority boundary accepts stale grant", "severity": "HIGH"}],
            "E3-Y": [{"statement": "Recovery journal preserves committed state", "severity": "MEDIUM"}],
            "E3-Z": [],
        }
    )

    assert first.total_discoveries == changed.total_discoveries == 2
    assert first.blind_completion_digest != changed.blind_completion_digest

    first_checkpoint = create_e3_blind_checkpoint(first, first_cut)
    changed_checkpoint = create_e3_blind_checkpoint(changed, changed_cut)
    assert first_checkpoint.sealed_findings_count == changed_checkpoint.sealed_findings_count == 2
    assert first_checkpoint.blind_completion_digest != changed_checkpoint.blind_completion_digest
    assert first_checkpoint.digest != changed_checkpoint.digest


def test_d21_discovery_order_does_not_change_completion_identity() -> None:
    first, first_cut = _execute(
        {
            "E3-X": [
                {"statement": "Discovery alpha", "severity": "HIGH"},
                {"statement": "Discovery beta", "severity": "LOW"},
            ],
            "E3-Y": [],
            "E3-Z": [],
        }
    )
    reordered, reordered_cut = _execute(
        {
            "E3-X": [
                {"statement": "Discovery beta", "severity": "LOW"},
                {"statement": "Discovery alpha", "severity": "HIGH"},
            ],
            "E3-Y": [],
            "E3-Z": [],
        }
    )

    assert first.total_discoveries == reordered.total_discoveries == 2
    assert first.blind_completion_digest == reordered.blind_completion_digest

    first_checkpoint = create_e3_blind_checkpoint(first, first_cut)
    reordered_checkpoint = create_e3_blind_checkpoint(reordered, reordered_cut)
    assert first_checkpoint.digest == reordered_checkpoint.digest
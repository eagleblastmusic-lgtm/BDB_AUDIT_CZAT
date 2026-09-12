"""Verified campaign read models derived only from accepted history.

RU04 / D07 boundary: immutable object-table presence is storage, never authority.
Every projected fact below is resolved through the canonical accepted commit
closure at one exact current HistoryCut.  Orphan, uncommitted, wrong-run, or
corrupted rows therefore cannot advance operational state.
"""
from __future__ import annotations

from typing import Any, Callable

from ..core.errors import ValidationError
from ..history.objects import HistoryCut
from ..history.store import TransactionalHistoryStore


CanonicalStage = Callable[[str], str]


def current_accepted_cut(store: TransactionalHistoryStore) -> dict[str, Any]:
    """Return and verify the exact current accepted cut, fail closed on drift."""
    head = store.head()
    if head is None or head.commit_seq < 1:
        raise ValidationError("CAMPAIGN_NOT_FOUND", "Campaign has no accepted head")
    commits = store.commits()
    if len(commits) < head.commit_seq:
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE", "Accepted head exceeds durable commit chain")
    last = commits[head.commit_seq - 1]
    if (
        last.get("campaign_id") != head.campaign_id
        or last.get("commit_seq") != head.commit_seq
    ):
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE", "Accepted head metadata disagrees with commit chain")
    cut = HistoryCut.accepted(
        head,
        last["governing_policy_ref"],
        last.get("governing_spec_refs", ()),
    ).as_dict()
    # resolve_accepted validates the complete prefix and exact cut identity.
    store.resolve_accepted(commits[0]["command_ref"], cut)
    return cut


def _accepted_object_count(store: TransactionalHistoryStore, cut: dict[str, Any]) -> int:
    """Count unique refs in a chain that has already been verified for ``cut``."""
    refs: set[tuple[str, str]] = set()
    limit = cut["accepted_head_seq"]
    for commit in store.commits():
        if commit["commit_seq"] > limit:
            break
        for ref in commit.get("immutable_object_refs", ()):
            kind = ref.get("kind")
            digest = ref.get("revision_digest")
            if isinstance(kind, str) and isinstance(digest, str):
                refs.add((kind, digest))
    return len(refs)


def campaign_source_identity(
    store: TransactionalHistoryStore,
    cut: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve source identity through accepted genesis -> generation -> identity."""
    cut = cut or current_accepted_cut(store)
    genesis_rows = store.accepted_records("campaign_genesis", cut)
    if len(genesis_rows) != 1:
        raise ValidationError(
            "CAMPAIGN_GENESIS_PROJECTION_INVALID",
            f"Expected exactly one accepted campaign_genesis, found {len(genesis_rows)}",
        )
    genesis = genesis_rows[0]["body"]
    source_generation_ref = genesis.get("source_generation_ref")
    if not isinstance(source_generation_ref, dict):
        raise ValidationError("SOURCE_GENERATION_REF_MISSING")
    generation = store.resolve_accepted(source_generation_ref, cut)["body"]
    source_identity_ref = generation.get("source_identity_ref")
    if not isinstance(source_identity_ref, dict):
        raise ValidationError("SOURCE_IDENTITY_REF_MISSING")
    identity = store.resolve_accepted(source_identity_ref, cut)["body"]
    repo_ref = identity.get("authorized_repository_or_snapshot_ref", {})
    return {
        "source_generation_id": generation.get("source_generation_id"),
        "source_generation_ref": dict(source_generation_ref),
        "source_identity_ref": dict(source_identity_ref),
        "authority_mode": identity.get("authority_mode"),
        "git_commit_object_id": identity.get("git_commit_object_id"),
        "git_tree_object_id": identity.get("git_tree_object_id"),
        "repository_authority_ref": dict(repo_ref) if isinstance(repo_ref, dict) else repo_ref,
        "completeness_state": identity.get("completeness_state"),
    }


def campaign_status(
    store: TransactionalHistoryStore,
    canonical_stage: CanonicalStage,
) -> dict[str, Any]:
    """Build operational status exclusively from accepted records on current cut."""
    cut = current_accepted_cut(store)
    head = store.head()
    if head is None:  # guarded by current_accepted_cut; keeps typing explicit.
        raise ValidationError("CAMPAIGN_NOT_FOUND")

    stage_rows = store.accepted_records("stage_spec", cut)
    stage_records: list[tuple[int, str]] = []
    for index, row in enumerate(stage_rows, start=1):
        doc = row["body"]
        stage_key = doc.get("stage_key") or doc.get("stage_id") or doc.get("key")
        ordinal = doc.get("stage_ordinal")
        if stage_key is None:
            raise ValidationError("STAGE_SPEC_PROJECTION_INVALID", "stage_spec missing stage_key")
        try:
            canonical_key = canonical_stage(str(stage_key))
        except ValidationError as exc:
            raise ValidationError("STAGE_SPEC_PROJECTION_INVALID", str(exc)) from exc
        if type(ordinal) is not int or ordinal < 1:
            ordinal = index
        stage_records.append((ordinal, canonical_key))
    stage_records.sort(key=lambda item: (item[0], item[1]))
    stages = [stage_key for _, stage_key in stage_records]
    if len(stages) != len(set(stages)):
        raise ValidationError("STAGE_SPEC_PROJECTION_INVALID", "Duplicate accepted stage key")

    lane_rows = store.accepted_records("lane_spec", cut)
    lanes: list[str] = []
    for row in lane_rows:
        doc = row["body"]
        lane_key = doc.get("lane_key") or doc.get("lane_id") or doc.get("slot")
        if not lane_key:
            raise ValidationError("LANE_SPEC_PROJECTION_INVALID", "lane_spec missing lane_key")
        lanes.append(str(lane_key))
    lanes.sort()
    if len(lanes) != len(set(lanes)):
        raise ValidationError("LANE_SPEC_PROJECTION_INVALID", "Duplicate accepted lane key")

    completion_rows = store.accepted_records("stage_completion", cut)
    stop_rows = store.accepted_records("stop_evaluation", cut)
    conclusion_rows = store.accepted_records("campaign_conclusion", cut)
    conclusion_rows = tuple(sorted(conclusion_rows, key=lambda row: row["accepted_seq"]))
    latest_conclusion = conclusion_rows[-1]["body"] if conclusion_rows else None
    termination_state = latest_conclusion.get("termination_state") if latest_conclusion else "OPEN"
    if termination_state not in {"OPEN", "COMPLETED", "COMPLETED_LIMITED"}:
        raise ValidationError("CAMPAIGN_CONCLUSION_PROJECTION_INVALID", str(termination_state))

    source = campaign_source_identity(store, cut)
    return {
        "status": "SUCCESS",
        "campaign_id": head.campaign_id,
        "accepted_head_seq": head.commit_seq,
        "accepted_head_hash": head.commit_hash,
        "current_stage": stages[-1] if stages else "GENESIS",
        "stages_prepared": stages,
        "lanes_prepared": lanes,
        "stage_completions_count": len(completion_rows),
        "stop_evaluations_count": len(stop_rows),
        "campaign_conclusions_count": len(conclusion_rows),
        "termination_state": termination_state,
        "campaign_completed": termination_state in {"COMPLETED", "COMPLETED_LIMITED"},
        "total_objects_count": _accepted_object_count(store, cut),
        "source_generation_id": source.get("source_generation_id"),
    }


__all__ = [
    "current_accepted_cut",
    "campaign_source_identity",
    "campaign_status",
]

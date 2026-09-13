"""Verified campaign read models derived only from accepted history.

RU04 / D07 / D22 boundary: immutable object-table presence is storage, never authority.
Every projected fact below is resolved through the canonical accepted commit
closure at one exact current HistoryCut. Orphan, uncommitted, wrong-run, wrong-stage,
wrong-campaign, or corrupted rows therefore cannot advance operational state.
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


class VerifiedCampaignReadModel:
    """Unified application-level read model projecting state strictly from accepted closure.

    Authority guarantee:
    1. Direct immutable_objects queries are forbidden for operational decisions.
    2. Projections are resolved on an exact, verified HistoryCut.
    3. Prepared state != completed state: presence of StageSpec or LaneSpec never marks
       a stage as completed.
    4. Exact stage/run binding: stage completions must resolve to an accepted StageSpec,
       verifying campaign identity and exact cut closure. Multiple conflicting completions
       for the same stage fail closed.
    5. Termination and readiness: only an accepted CampaignConclusion with COMPLETED or
       COMPLETED_LIMITED can mark the campaign finished.
    """

    def __init__(
        self,
        store: TransactionalHistoryStore,
        canonical_stage: CanonicalStage | None = None,
        cut: dict[str, Any] | None = None,
    ):
        self.store = store
        if canonical_stage is not None:
            self.canonical_stage = canonical_stage
        else:
            from ..coordinator.operations import _canonical_stage_key
            self.canonical_stage = _canonical_stage_key

        self.cut = cut or current_accepted_cut(store)
        self.head = store.head()
        if self.head is None:
            raise ValidationError("CAMPAIGN_NOT_FOUND")

    def project_status(self) -> dict[str, Any]:
        """Project operational status exclusively from accepted records on current cut."""
        cut = self.cut
        head = self.head

        # 1. Accepted StageSpecs
        stage_rows = self.store.accepted_records("stage_spec", cut)
        stage_records: list[tuple[int, str, dict[str, Any]]] = []
        spec_by_stage_key: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(stage_rows, start=1):
            doc = row["body"]
            stage_key = doc.get("stage_key") or doc.get("stage_id") or doc.get("key")
            ordinal = doc.get("stage_ordinal")
            if stage_key is None:
                raise ValidationError("STAGE_SPEC_PROJECTION_INVALID", "stage_spec missing stage_key")
            try:
                canonical_key = self.canonical_stage(str(stage_key))
            except ValidationError as exc:
                raise ValidationError("STAGE_SPEC_PROJECTION_INVALID", str(exc)) from exc
            if type(ordinal) is not int or ordinal < 1:
                ordinal = index
            if canonical_key in spec_by_stage_key:
                raise ValidationError("STAGE_SPEC_PROJECTION_INVALID", f"Duplicate accepted stage key {canonical_key}")
            spec_by_stage_key[canonical_key] = row
            stage_records.append((ordinal, canonical_key, row))

        stage_records.sort(key=lambda item: (item[0], item[1]))
        stages_prepared = [stage_key for _, stage_key, _ in stage_records]

        # 2. Accepted LaneSpecs
        lane_rows = self.store.accepted_records("lane_spec", cut)
        lanes_prepared: list[str] = []
        for row in lane_rows:
            doc = row["body"]
            lane_key = doc.get("lane_key") or doc.get("lane_id") or doc.get("slot")
            if not lane_key:
                raise ValidationError("LANE_SPEC_PROJECTION_INVALID", "lane_spec missing lane_key")
            lanes_prepared.append(str(lane_key))
        lanes_prepared.sort()
        if len(lanes_prepared) != len(set(lanes_prepared)):
            raise ValidationError("LANE_SPEC_PROJECTION_INVALID", "Duplicate accepted lane key")

        # 3. Accepted StageCompletions with exact stage binding and ambiguity rejection
        completion_rows = self.store.accepted_records("stage_completion", cut)
        completed_stages: list[str] = []
        completed_by_stage: dict[str, str] = {}  # stage_key -> completion_digest

        for row in completion_rows:
            doc = row["body"]
            if doc.get("completion_predicate_result") != "STAGE_COMPLETED":
                continue

            spec_ref = doc.get("stage_spec_ref")
            if not isinstance(spec_ref, dict):
                raise ValidationError("STAGE_COMPLETION_PROJECTION_INVALID", "Missing stage_spec_ref in stage_completion")

            # Resolve accepted stage_spec to verify campaign and cut binding
            spec_record = self.store.resolve_accepted(spec_ref, cut)
            spec_body = spec_record["body"]
            sk = spec_body.get("stage_key") or spec_body.get("stage_id")
            if not sk:
                raise ValidationError("STAGE_COMPLETION_PROJECTION_INVALID", "stage_spec has no stage_key")
            canonical_sk = self.canonical_stage(str(sk))

            if canonical_sk in completed_by_stage:
                existing_digest = completed_by_stage[canonical_sk]
                new_digest = row["ref"]["revision_digest"]
                if existing_digest != new_digest:
                    raise ValidationError(
                        "MULTIPLE_STAGE_COMPLETIONS",
                        f"Ambiguous conflicting completions for stage {canonical_sk}",
                    )
            else:
                completed_by_stage[canonical_sk] = row["ref"]["revision_digest"]
                completed_stages.append(canonical_sk)

        stage_order = {s: i for i, s in enumerate(("E1", "E2", "E3", "E4", "E5", "E6"))}
        completed_stages.sort(key=lambda s: stage_order.get(s, 99))

        # 4. Accepted StopEvaluations & CampaignConclusions
        stop_rows = self.store.accepted_records("stop_evaluation", cut)
        conclusion_rows = self.store.accepted_records("campaign_conclusion", cut)
        conclusion_rows = tuple(sorted(conclusion_rows, key=lambda row: row["accepted_seq"]))
        latest_conclusion = conclusion_rows[-1]["body"] if conclusion_rows else None
        termination_state = latest_conclusion.get("termination_state") if latest_conclusion else "OPEN"
        if termination_state not in {"OPEN", "COMPLETED", "COMPLETED_LIMITED"}:
            raise ValidationError("CAMPAIGN_CONCLUSION_PROJECTION_INVALID", str(termination_state))

        # 5. Determine current_stage rigorously:
        # If there are prepared stages, current_stage is the first prepared stage that is NOT completed.
        # If all prepared stages are completed and campaign is still OPEN, advance to next incomplete baseline stage.
        current_stage = "GENESIS"
        for st in stages_prepared:
            if st not in completed_by_stage:
                current_stage = st
                break
        else:
            if termination_state == "OPEN":
                next_stage = next((s for s in ("E1", "E2", "E3", "E4", "E5") if s not in completed_by_stage), None)
                current_stage = next_stage or (stages_prepared[-1] if stages_prepared else "GENESIS")
            elif stages_prepared:
                current_stage = stages_prepared[-1]

        source = campaign_source_identity(self.store, cut)

        return {
            "status": "SUCCESS",
            "campaign_id": head.campaign_id,
            "accepted_head_seq": head.commit_seq,
            "accepted_head_hash": head.commit_hash,
            "current_stage": current_stage,
            "stages_prepared": stages_prepared,
            "stages_completed": completed_stages,
            "lanes_prepared": lanes_prepared,
            "stage_completions_count": len(completion_rows),
            "stop_evaluations_count": len(stop_rows),
            "campaign_conclusions_count": len(conclusion_rows),
            "termination_state": termination_state,
            "campaign_completed": termination_state in {"COMPLETED", "COMPLETED_LIMITED"},
            "total_objects_count": _accepted_object_count(self.store, cut),
            "source_generation_id": source.get("source_generation_id"),
        }

    def project_source_identity(self) -> dict[str, Any]:
        return campaign_source_identity(self.store, self.cut)


def campaign_status(
    store: TransactionalHistoryStore,
    canonical_stage: CanonicalStage,
) -> dict[str, Any]:
    """Build operational status exclusively from accepted records on current cut."""
    model = VerifiedCampaignReadModel(store, canonical_stage=canonical_stage)
    return model.project_status()


__all__ = [
    "current_accepted_cut",
    "campaign_source_identity",
    "campaign_status",
    "VerifiedCampaignReadModel",
]

"""E2 blind checkpoint sealing.

The blind external lane results are useful only after they are durably frozen
before any controlled reveal.  This service accepts pre-reveal DiscoveryRecord
precursors and one Checkpoint per E2 blind lane in one atomic Coordinator
commit.  It does not perform reveal or adjudication.

Manual ChatGPT transport remains DECLARED isolation.  The accepted discovery
precursor therefore records ordering/provenance facts but does not, by itself,
upgrade a finding to verified blind-origin.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from ..coordinator import Coordinator
from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, CommandEnvelope
from ..history.store import TransactionalHistoryStore
from .assignments import _command_id, _current_cut, _external_ref
from .inbox import _same_ref, _with_ref_class
from .manual_stage import StageBatch, StageResultInbox


@dataclass(frozen=True)
class E2BlindCheckpointSummary:
    campaign_id: str
    stage_id: str
    phase_id: str
    checkpoint_input_history_cut: dict[str, Any]
    checkpoint_refs: dict[str, dict[str, Any]]
    discovery_refs: dict[str, tuple[dict[str, Any], ...]]
    already_sealed: bool
    accepted_commit_seq: int


def _fingerprint_finding(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _accepted_result_for_job(
    store: TransactionalHistoryStore,
    job,
    cut: dict[str, Any],
) -> dict[str, Any]:
    rows = [
        row
        for row in store.accepted_records("bdb_audit_lane_result", cut)
        if row["body"].get("stage_id") == job.stage_id
        and row["body"].get("phase_id") == job.phase_id
        and _same_ref(row["body"].get("assignment_ref"), job.assignment_ref)
    ]
    if len(rows) != 1:
        raise ValidationError(
            "E2_BLIND_RESULT_SET_INCOMPLETE",
            f"{job.lane_slot}: expected 1 accepted result, got {len(rows)}",
        )
    return rows[0]


class E2BlindCheckpointService:
    """Seal all E2 blind outputs on one exact accepted history cut."""

    def __init__(
        self,
        store: TransactionalHistoryStore,
        batch: StageBatch,
        inbox: StageResultInbox | None = None,
    ):
        if batch.stage_id != "E2" or batch.phase_id != "E2-BLIND":
            raise ValidationError(
                "E2_BLIND_BATCH_REQUIRED",
                f"{batch.stage_id}/{batch.phase_id}",
            )
        self.store = store
        self.batch = batch
        self.inbox = inbox
        self.coordinator = Coordinator(store)

    def _existing(
        self,
        cut: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        attempt_to_slot = {
            job.attempt_ref["revision_digest"]: slot
            for slot, job in self.batch.jobs.items()
        }
        found: dict[str, dict[str, Any]] = {}
        for row in self.store.accepted_records("checkpoint", cut):
            body = row["body"]
            if body.get("stage_id") != "E2" or body.get("phase_id") != "E2-BLIND":
                continue
            attempt = body.get("attempt_ref")
            if not isinstance(attempt, dict):
                continue
            slot = attempt_to_slot.get(attempt.get("revision_digest"))
            if slot is None:
                continue
            if slot in found and found[slot]["ref"]["revision_digest"] != row["ref"]["revision_digest"]:
                raise ValidationError("MULTIPLE_E2_BLIND_CHECKPOINTS", slot)
            found[slot] = row
        return found

    def seal(self) -> E2BlindCheckpointSummary:
        cut, prior_commit = _current_cut(self.store)

        if self.inbox is not None:
            self.inbox._load_accepted_state()
            missing = [
                slot
                for slot, state in self.inbox.lane_statuses.items()
                if state.status != "ACCEPTED"
            ]
            blocked = [
                slot
                for slot, state in self.inbox.lane_statuses.items()
                if state.status == "ACCEPTED"
                and state.completion_status != "LANE_COMPLETED"
            ]
            if missing or blocked:
                raise ValidationError(
                    "E2_BLIND_PHASE_NOT_COMPLETE",
                    f"missing={missing}; blocked={blocked}",
                )

        existing = self._existing(cut)
        if existing:
            if set(existing) != set(self.batch.jobs):
                raise ValidationError(
                    "PARTIAL_E2_BLIND_CHECKPOINT_SET",
                    ",".join(sorted(existing)),
                )
            checkpoint_refs = {
                slot: _with_ref_class(row["ref"], "CONTENT_OR_PRIOR")
                for slot, row in existing.items()
            }
            discovery_refs: dict[str, tuple[dict[str, Any], ...]] = {}
            for slot, row in existing.items():
                sealed = row["body"].get("sealed_output_refs", [])
                discovery_refs[slot] = tuple(
                    dict(ref)
                    for ref in sealed
                    if isinstance(ref, dict)
                    and ref.get("kind") == "discovery_record"
                )
            seqs = {row["accepted_seq"] for row in existing.values()}
            if len(seqs) != 1:
                raise ValidationError("E2_BLIND_CHECKPOINT_CUT_DIVERGENCE")
            return E2BlindCheckpointSummary(
                campaign_id=self.batch.campaign_id,
                stage_id="E2",
                phase_id="E2-BLIND",
                checkpoint_input_history_cut=dict(
                    next(iter(existing.values()))["body"]["checkpoint_input_history_cut"]
                ),
                checkpoint_refs=checkpoint_refs,
                discovery_refs=discovery_refs,
                already_sealed=True,
                accepted_commit_seq=next(iter(seqs)),
            )

        objects: list[CanonicalObject] = []
        checkpoint_objects: dict[str, CanonicalObject] = {}
        discovery_objects: dict[str, list[CanonicalObject]] = {}

        for slot in self.batch.lane_slots:
            job = self.batch.get_job(slot)
            result = _accepted_result_for_job(self.store, job, cut)
            assignment_record = self.store.resolve_accepted(job.assignment_ref, cut)
            assignment = assignment_record["body"]
            attempt_record = self.store.resolve_accepted(assignment["attempt_ref"], cut)
            lane_run_record = self.store.resolve_accepted(
                attempt_record["body"]["lane_run_ref"],
                cut,
            )
            stage_run_record = self.store.resolve_accepted(
                lane_run_record["body"]["stage_run_ref"],
                cut,
            )
            knowledge_record = self.store.resolve_accepted(
                assignment["knowledge_state_ref"],
                cut,
            )
            source_record = self.store.resolve_accepted(
                assignment["source_generation_ref"],
                cut,
            )

            discoveries: list[CanonicalObject] = []
            findings = result["body"].get("findings", [])
            for index, finding in enumerate(findings):
                if not isinstance(finding, dict):
                    raise ValidationError("INVALID_FINDING_STRUCTURE", slot)
                finding_digest = _fingerprint_finding(finding)
                discovery = CanonicalObject(
                    "discovery_record",
                    {
                        "discovery_id": (
                            f"disc_{slot}_{result['ref']['revision_digest'][:12]}_"
                            f"{index + 1}"
                        ),
                        "lane_run_ref": _with_ref_class(
                            lane_run_record["ref"],
                            "PRIOR_ACCEPTED_ONLY",
                        ),
                        "attempt_ref": _with_ref_class(
                            attempt_record["ref"],
                            "PRIOR_ACCEPTED_ONLY",
                        ),
                        "source_generation_ref": _with_ref_class(
                            source_record["ref"],
                            "PRIOR_ACCEPTED_ONLY",
                        ),
                        "discovery_input_history_cut": cut,
                        "knowledge_state_ref": _with_ref_class(
                            knowledge_record["ref"],
                            "PRIOR_ACCEPTED_ONLY",
                        ),
                        "method_ref": _external_ref(
                            "external_profile_ref",
                            f"e2_blind_external_{slot}",
                            "HISTORY_CONTEXT_BINDING",
                        ),
                        "producer_ref": prior_commit.get(
                            "actor_ref",
                            "installation-owner",
                        ),
                        "surface_location_refs": [],
                        "own_observation_refs": [],
                        "submission_finding_index": index,
                        "submission_finding_fingerprint": finding_digest,
                    },
                )
                discoveries.append(discovery)
                objects.append(discovery)
            discovery_objects[slot] = discoveries

            sealed_refs = canonical_reference_set(
                [
                    _with_ref_class(result["ref"], "CONTENT_OR_PRIOR"),
                    *[
                        item.as_ref(ref_class="CONTENT_OR_PRIOR").as_dict()
                        for item in discoveries
                    ],
                ]
            )
            checkpoint = CanonicalObject(
                "checkpoint",
                {
                    "checkpoint_id": (
                        "checkpoint_e2_blind_"
                        + hashlib.sha256(
                            (
                                slot
                                + ":"
                                + result["ref"]["revision_digest"]
                                + ":"
                                + str(cut["accepted_head_seq"])
                            ).encode("utf-8")
                        ).hexdigest()[:24]
                    ),
                    "stage_id": "E2",
                    "phase_id": "E2-BLIND",
                    "lane_slot": slot,
                    "stage_run_ref": _with_ref_class(
                        stage_run_record["ref"],
                        "PRIOR_ACCEPTED_ONLY",
                    ),
                    "lane_run_ref": _with_ref_class(
                        lane_run_record["ref"],
                        "PRIOR_ACCEPTED_ONLY",
                    ),
                    "attempt_ref": _with_ref_class(
                        attempt_record["ref"],
                        "PRIOR_ACCEPTED_ONLY",
                    ),
                    "source_generation_ref": _with_ref_class(
                        source_record["ref"],
                        "PRIOR_ACCEPTED_ONLY",
                    ),
                    "checkpoint_input_history_cut": cut,
                    "knowledge_state_ref": _with_ref_class(
                        knowledge_record["ref"],
                        "PRIOR_ACCEPTED_ONLY",
                    ),
                    "sealed_output_refs": sealed_refs,
                    "governing_policy_ref": prior_commit["governing_policy_ref"],
                },
            )
            checkpoint_objects[slot] = checkpoint
            objects.append(checkpoint)

        head = self.store.head()
        if head is None:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        seed = ":".join(
            sorted(obj.digest for obj in checkpoint_objects.values())
        )
        command = CommandEnvelope(
            command_id=_command_id("e2_blind_checkpoint:" + seed),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={
                "tag": "ACCEPTED_HEAD_REF",
                **head.as_dict(),
            },
            governing_policy_ref=prior_commit["governing_policy_ref"],
            governing_spec_refs=tuple(
                prior_commit.get("governing_spec_refs", ())
            ),
            idempotency_scope="e2_blind_checkpoint:" + seed,
            campaign_ref=head.campaign_id,
        )
        accepted = self.coordinator.accept(
            command,
            immutable_objects=objects,
            expected_head=head,
        )

        return E2BlindCheckpointSummary(
            campaign_id=self.batch.campaign_id,
            stage_id="E2",
            phase_id="E2-BLIND",
            checkpoint_input_history_cut=dict(cut),
            checkpoint_refs={
                slot: obj.as_ref(
                    ref_class="CONTENT_OR_PRIOR"
                ).as_dict()
                for slot, obj in checkpoint_objects.items()
            },
            discovery_refs={
                slot: tuple(
                    obj.as_ref(
                        ref_class="CONTENT_OR_PRIOR"
                    ).as_dict()
                    for obj in rows
                )
                for slot, rows in discovery_objects.items()
            },
            already_sealed=False,
            accepted_commit_seq=accepted.head.commit_seq,
        )


__all__ = [
    "E2BlindCheckpointSummary",
    "E2BlindCheckpointService",
]

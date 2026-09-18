"""Validation of accepted E3 gap-directed result proposals.

This service is deliberately non-authoritative about coverage.  It verifies that
external E3-GAP results stayed inside the accepted positive ViewManifest and
that every authorized gap target was addressed by at least one completed lane.
It also rejects attempts to relabel post-reveal findings as blind discoveries.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from ..coordinator import Coordinator
from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..history.objects import CanonicalObject, CommandEnvelope
from ..history.store import TransactionalHistoryStore
from .assignments import _command_id, _current_cut, _external_ref
from .inbox import _same_ref, _with_ref_class
from .manual_stage import StageBatch, StageResultInbox


_ALLOWED_TARGET_KINDS = {
    "coverage_obligation": "COVERAGE_OBLIGATION",
    "scope_state_record": "SCOPE_GAP",
}
_ALLOWED_STATUSES = {
    "EXPLORED",
    "BLOCKED",
    "NO_MATERIAL_DISCOVERY",
}


@dataclass(frozen=True)
class E3GapValidationSummary:
    campaign_id: str
    authorized_target_digests: tuple[str, ...]
    covered_target_digests: tuple[str, ...]
    result_refs: tuple[dict[str, Any], ...]
    discovery_refs: tuple[dict[str, Any], ...]
    findings_count: int
    accepted_commit_seq: int
    already_persisted: bool
    next_action: str


class E3GapResultValidationService:
    def __init__(
        self,
        store: TransactionalHistoryStore,
        batch: StageBatch,
        inbox: StageResultInbox | None = None,
    ):
        if (
            batch.stage_id != "E3"
            or batch.phase_id != "E3-GAP"
        ):
            raise ValidationError(
                "E3_GAP_BATCH_REQUIRED",
                f"{batch.stage_id}/{batch.phase_id}",
            )
        self.store = store
        self.batch = batch
        self.inbox = inbox
        self.coordinator = Coordinator(store)

    def _require_complete(self) -> None:
        if self.inbox is None:
            return
        self.inbox._load_accepted_state()
        states = tuple(
            self.inbox.lane_statuses.values()
        )
        if any(
            state.status != "ACCEPTED"
            or state.completion_status
            != "LANE_COMPLETED"
            for state in states
        ):
            raise ValidationError(
                "E3_GAP_PHASE_NOT_COMPLETE"
            )

    def _authorized_targets(
        self,
        cut: dict[str, Any],
    ) -> dict[str, str]:
        manifest_refs = {
            job.view_manifest_ref.get(
                "revision_digest"
            )
            for job in self.batch.jobs.values()
            if job.view_manifest_ref
        }
        manifest_refs.discard(None)
        if len(manifest_refs) != 1:
            raise ValidationError(
                "E3_GAP_VIEW_BINDING_REQUIRED"
            )
        digest = next(iter(manifest_refs))
        rows = [
            row
            for row in self.store.accepted_records(
                "view_manifest",
                cut,
            )
            if row["ref"]["revision_digest"] == digest
            and row["body"].get("phase_id")
            == "E3-GAP"
        ]
        if len(rows) != 1:
            raise ValidationError(
                "E3_GAP_VIEW_BINDING_REQUIRED"
            )
        manifest = rows[0]

        targets: dict[str, str] = {}
        for ref in manifest["body"].get(
            "allowed_artifact_refs",
            [],
        ):
            if not isinstance(ref, dict):
                continue
            kind = ref.get("kind")
            if kind not in _ALLOWED_TARGET_KINDS:
                continue
            ref_digest = ref.get(
                "revision_digest"
            )
            if not isinstance(
                ref_digest,
                str,
            ):
                continue
            targets[ref_digest] = (
                _ALLOWED_TARGET_KINDS[kind]
            )
        if not targets:
            raise ValidationError(
                "E3_GAP_TARGET_SET_EMPTY"
            )
        return targets

    def _accepted_results(
        self,
        cut: dict[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        result_rows = []
        for slot, job in self.batch.jobs.items():
            matches = [
                row
                for row in self.store.accepted_records(
                    "bdb_audit_lane_result",
                    cut,
                )
                if row["body"].get("stage_id")
                == "E3"
                and row["body"].get("phase_id")
                == "E3-GAP"
                and _same_ref(
                    row["body"].get(
                        "assignment_ref"
                    ),
                    job.assignment_ref,
                )
            ]
            if len(matches) != 1:
                raise ValidationError(
                    "E3_GAP_RESULT_SET_INCOMPLETE",
                    (
                        f"{slot}: expected 1 accepted "
                        f"result, got {len(matches)}"
                    ),
                )
            result_rows.append(matches[0])
        return tuple(result_rows)

    def _checkpoint_by_slot(
        self,
        cut: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        manifest_refs = {
            job.view_manifest_ref.get(
                "revision_digest"
            )
            for job in self.batch.jobs.values()
            if job.view_manifest_ref
        }
        manifest_refs.discard(None)
        if len(manifest_refs) != 1:
            raise ValidationError(
                "E3_GAP_VIEW_BINDING_REQUIRED"
            )
        manifest_digest = next(
            iter(manifest_refs)
        )
        manifests = [
            row
            for row in self.store.accepted_records(
                "view_manifest",
                cut,
            )
            if row["ref"]["revision_digest"]
            == manifest_digest
        ]
        if len(manifests) != 1:
            raise ValidationError(
                "E3_GAP_VIEW_BINDING_REQUIRED"
            )
        mapped: dict[
            str, dict[str, Any]
        ] = {}
        for ref in manifests[0]["body"].get(
            "checkpoint_refs",
            [],
        ):
            if not isinstance(ref, dict):
                continue
            checkpoint = self.store.resolve_accepted(
                ref,
                cut,
            )
            slot = checkpoint["body"].get(
                "lane_slot"
            )
            if (
                isinstance(slot, str)
                and slot in self.batch.jobs
            ):
                mapped[slot] = checkpoint
        missing = sorted(
            set(self.batch.jobs) - set(mapped)
        )
        if missing:
            raise ValidationError(
                "E3_GAP_CHECKPOINT_BINDING_INCOMPLETE",
                ",".join(missing),
            )
        return mapped

    def _persist_discoveries(
        self,
        *,
        cut: dict[str, Any],
        prior_commit: dict[str, Any],
        results: tuple[dict[str, Any], ...],
    ) -> tuple[
        tuple[dict[str, Any], ...],
        int,
        bool,
    ]:
        checkpoints = self._checkpoint_by_slot(
            cut
        )
        expected: dict[
            tuple[str, int],
            dict[str, Any],
        ] = {}
        result_by_assignment = {
            row["body"]["assignment_ref"][
                "revision_digest"
            ]: row
            for row in results
        }

        for slot, job in self.batch.jobs.items():
            result = result_by_assignment.get(
                job.assignment_ref[
                    "revision_digest"
                ]
            )
            if result is None:
                raise ValidationError(
                    "E3_GAP_RESULT_SET_INCOMPLETE",
                    slot,
                )
            findings = result["body"].get(
                "findings",
                [],
            )
            for index, finding in enumerate(
                findings
            ):
                fingerprint = hashlib.sha256(
                    canonical_bytes(finding)
                ).hexdigest()
                expected[(slot, index)] = {
                    "result": result,
                    "finding": finding,
                    "fingerprint": fingerprint,
                }

        if not expected:
            head = self.store.head()
            return (
                (),
                head.commit_seq if head else 0,
                True,
            )

        existing: dict[
            tuple[str, int],
            dict[str, Any],
        ] = {}
        result_digests = {
            row["ref"]["revision_digest"]
            for row in results
        }
        for row in self.store.accepted_records(
            "discovery_record",
            cut,
        ):
            body = row["body"]
            if (
                body.get("stage_id") != "E3"
                or body.get("phase_id")
                != "E3-GAP"
                or body.get(
                    "result_proposal_digest"
                )
                not in result_digests
            ):
                continue
            slot = body.get("lane_slot")
            index = body.get(
                "submission_finding_index"
            )
            if (
                not isinstance(slot, str)
                or not isinstance(index, int)
            ):
                raise ValidationError(
                    "E3_GAP_DISCOVERY_PROVENANCE_INVALID"
                )
            key = (slot, index)
            if key in existing:
                raise ValidationError(
                    "MULTIPLE_E3_GAP_DISCOVERY_RECORDS",
                    f"{slot}:{index}",
                )
            existing[key] = row

        if existing:
            if set(existing) != set(expected):
                raise ValidationError(
                    "PARTIAL_E3_GAP_DISCOVERY_SET"
                )
            for key, row in existing.items():
                if (
                    row["body"].get(
                        "submission_finding_fingerprint"
                    )
                    != expected[key][
                        "fingerprint"
                    ]
                ):
                    raise ValidationError(
                        "E3_GAP_DISCOVERY_FINGERPRINT_DRIFT",
                        f"{key[0]}:{key[1]}",
                    )
            seqs = {
                row["accepted_seq"]
                for row in existing.values()
            }
            if len(seqs) != 1:
                raise ValidationError(
                    "E3_GAP_DISCOVERY_COMMIT_DIVERGENCE"
                )
            return (
                tuple(
                    _with_ref_class(
                        row["ref"],
                        "CONTENT_OR_PRIOR",
                    )
                    for _, row in sorted(
                        existing.items()
                    )
                ),
                next(iter(seqs)),
                True,
            )

        objects: list[
            CanonicalObject
        ] = []
        for (slot, index), item in sorted(
            expected.items()
        ):
            job = self.batch.get_job(slot)
            assignment = self.store.resolve_accepted(
                job.assignment_ref,
                cut,
            )
            attempt = self.store.resolve_accepted(
                assignment["body"][
                    "attempt_ref"
                ],
                cut,
            )
            lane_run = self.store.resolve_accepted(
                attempt["body"][
                    "lane_run_ref"
                ],
                cut,
            )
            source = self.store.resolve_accepted(
                assignment["body"][
                    "source_generation_ref"
                ],
                cut,
            )
            if not job.authorized_knowledge_state_ref:
                raise ValidationError(
                    "E3_GAP_AUTHORIZED_KNOWLEDGE_REQUIRED",
                    slot,
                )
            knowledge = self.store.resolve_accepted(
                job.authorized_knowledge_state_ref,
                cut,
            )
            result = item["result"]
            discovery_id = (
                "disc_E3_GAP_"
                + slot
                + "_"
                + result["ref"][
                    "revision_digest"
                ][:12]
                + "_"
                + str(index + 1)
            )
            objects.append(
                CanonicalObject(
                    "discovery_record",
                    {
                        "discovery_id": (
                            discovery_id
                        ),
                        "lane_run_ref": (
                            _with_ref_class(
                                lane_run["ref"],
                                "PRIOR_ACCEPTED_ONLY",
                            )
                        ),
                        "attempt_ref": (
                            _with_ref_class(
                                attempt["ref"],
                                "PRIOR_ACCEPTED_ONLY",
                            )
                        ),
                        "source_generation_ref": (
                            _with_ref_class(
                                source["ref"],
                                "PRIOR_ACCEPTED_ONLY",
                            )
                        ),
                        "discovery_input_history_cut": (
                            cut
                        ),
                        "knowledge_state_ref": (
                            _with_ref_class(
                                knowledge["ref"],
                                "PRIOR_ACCEPTED_ONLY",
                            )
                        ),
                        "method_ref": _external_ref(
                            "external_profile_ref",
                            "e3_gap_directed_"
                            + slot,
                            "HISTORY_CONTEXT_BINDING",
                        ),
                        "producer_ref": (
                            prior_commit.get(
                                "actor_ref",
                                "installation-owner",
                            )
                        ),
                        "surface_location_refs": [],
                        "own_observation_refs": [],
                        "pre_reveal_checkpoint_ref": (
                            _with_ref_class(
                                checkpoints[
                                    slot
                                ]["ref"],
                                "CONTENT_OR_PRIOR",
                            )
                        ),
                        "stage_id": "E3",
                        "phase_id": "E3-GAP",
                        "lane_slot": slot,
                        "origin_classification": (
                            "POST_REVEAL_CONFIRMATION"
                        ),
                        "discovery_mode": (
                            "GAP_DIRECTED"
                        ),
                        "result_proposal_digest": (
                            result["ref"][
                                "revision_digest"
                            ]
                        ),
                        "submission_finding_index": (
                            index
                        ),
                        "submission_finding_fingerprint": (
                            item[
                                "fingerprint"
                            ]
                        ),
                    },
                )
            )

        head = self.store.head()
        if head is None:
            raise ValidationError(
                "CAMPAIGN_NOT_INITIALIZED"
            )
        seed = hashlib.sha256(
            canonical_bytes(
                [
                    obj.digest
                    for obj in objects
                ]
            )
        ).hexdigest()
        command = CommandEnvelope(
            command_id=_command_id(
                "e3_gap_discoveries:" + seed
            ),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get(
                "actor_ref",
                "installation-owner",
            ),
            expected_parent_head={
                "tag": "ACCEPTED_HEAD_REF",
                **head.as_dict(),
            },
            governing_policy_ref=prior_commit[
                "governing_policy_ref"
            ],
            governing_spec_refs=tuple(
                prior_commit.get(
                    "governing_spec_refs",
                    (),
                )
            ),
            idempotency_scope=(
                "e3_gap_discoveries:" + seed
            ),
            campaign_ref=head.campaign_id,
        )
        accepted = self.coordinator.accept(
            command,
            immutable_objects=objects,
            expected_head=head,
        )
        return (
            tuple(
                obj.as_ref(
                    ref_class="CONTENT_OR_PRIOR"
                ).as_dict()
                for obj in objects
            ),
            accepted.head.commit_seq,
            False,
        )

    def validate(
        self,
    ) -> E3GapValidationSummary:
        self._require_complete()
        cut, prior_commit = _current_cut(
            self.store
        )
        targets = self._authorized_targets(cut)
        results = self._accepted_results(cut)

        covered: set[str] = set()
        findings_count = 0

        for result in results:
            findings = result["body"].get(
                "findings",
                [],
            )
            if not isinstance(findings, list):
                raise ValidationError(
                    "INVALID_FINDING_STRUCTURE",
                    "E3-GAP",
                )
            for finding in findings:
                if not isinstance(finding, dict):
                    raise ValidationError(
                        "INVALID_FINDING_STRUCTURE",
                        "E3-GAP",
                    )
                if finding.get("classification") in {
                    "PRE_REVEAL_DISCOVERY",
                    "BLIND_NOVELTY",
                }:
                    raise ValidationError(
                        "POST_REVEAL_DISCOVERY_MISCLASSIFIED_AS_BLIND"
                    )
            findings_count += len(findings)

            outputs = result["body"].get(
                "outputs",
                {},
            )
            rows = (
                outputs.get(
                    "gap_target_results"
                )
                if isinstance(outputs, dict)
                else None
            )
            if not isinstance(rows, list):
                raise ValidationError(
                    "E3_GAP_TARGET_RESULTS_REQUIRED"
                )
            seen_in_result: set[str] = set()
            for row in rows:
                if not isinstance(row, dict):
                    raise ValidationError(
                        "E3_GAP_TARGET_RESULT_INVALID"
                    )
                target_digest = row.get(
                    "target_ref_digest"
                )
                if (
                    not isinstance(
                        target_digest,
                        str,
                    )
                    or target_digest
                    not in targets
                ):
                    raise ValidationError(
                        "E3_GAP_TARGET_OUTSIDE_AUTHORIZED_VIEW",
                        str(target_digest),
                    )
                if target_digest in seen_in_result:
                    raise ValidationError(
                        "E3_GAP_DUPLICATE_TARGET_RESULT",
                        target_digest,
                    )
                seen_in_result.add(
                    target_digest
                )
                if row.get("target_kind") != (
                    targets[target_digest]
                ):
                    raise ValidationError(
                        "E3_GAP_TARGET_KIND_MISMATCH",
                        target_digest,
                    )
                if row.get("status") not in (
                    _ALLOWED_STATUSES
                ):
                    raise ValidationError(
                        "E3_GAP_STATUS_INVALID",
                        target_digest,
                    )
                rationale = row.get(
                    "rationale",
                    "",
                )
                if not isinstance(rationale, str):
                    raise ValidationError(
                        "E3_GAP_RATIONALE_INVALID",
                        target_digest,
                    )
                indexes = row.get(
                    "discovery_indexes",
                    [],
                )
                if (
                    not isinstance(indexes, list)
                    or any(
                        not isinstance(index, int)
                        or isinstance(index, bool)
                        or index < 0
                        or index >= len(findings)
                        for index in indexes
                    )
                    or len(indexes)
                    != len(set(indexes))
                ):
                    raise ValidationError(
                        "E3_GAP_DISCOVERY_INDEX_INVALID",
                        target_digest,
                    )
                if (
                    row.get("status")
                    == "NO_MATERIAL_DISCOVERY"
                    and indexes
                ):
                    raise ValidationError(
                        "E3_GAP_NO_DISCOVERY_STATUS_CONFLICT",
                        target_digest,
                    )
                covered.add(target_digest)

        missing = sorted(
            set(targets) - covered
        )
        if missing:
            raise ValidationError(
                "E3_GAP_TARGET_SET_INCOMPLETE",
                ",".join(missing),
            )

        (
            discovery_refs,
            accepted_commit_seq,
            already_persisted,
        ) = self._persist_discoveries(
            cut=cut,
            prior_commit=prior_commit,
            results=results,
        )

        return E3GapValidationSummary(
            campaign_id=self.batch.campaign_id,
            authorized_target_digests=tuple(
                sorted(targets)
            ),
            covered_target_digests=tuple(
                sorted(covered)
            ),
            result_refs=tuple(
                _with_ref_class(
                    row["ref"],
                    "CONTENT_OR_PRIOR",
                )
                for row in results
            ),
            discovery_refs=discovery_refs,
            findings_count=findings_count,
            accepted_commit_seq=(
                accepted_commit_seq
            ),
            already_persisted=(
                already_persisted
            ),
            next_action=(
                "PREPARE_E3_CUMULATIVE_CORPUS_REVEAL"
            ),
        )


__all__ = [
    "E3GapResultValidationService",
    "E3GapValidationSummary",
]

"""Validation of late E3 cumulative-corpus comparison proposals.

The external cumulative phase may compare the campaign's own E3 discoveries
against the approved E1/E2 adjudicated corpus.  This validator enforces exact
coverage and view closure.  It does *not* turn NO_PRIOR_MATCH into a canonical
false-negative decision; that requires a separate relationship assessment over
an exact corpus snapshot and matching policy.

New findings produced after this reveal are persisted as post-reveal
DiscoveryRecords with the cumulative KnowledgeState.
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


_RELATIONS = {
    "MATCHED_PRIOR",
    "NO_PRIOR_MATCH",
    "CONFLICT",
    "INCONCLUSIVE",
}


@dataclass(frozen=True)
class E3CumulativeValidationSummary:
    campaign_id: str
    comparison_count: int
    matched_discovery_ids: tuple[str, ...]
    no_prior_match_discovery_ids: tuple[str, ...]
    post_reveal_discovery_refs: tuple[
        dict[str, Any], ...
    ]
    accepted_commit_seq: int
    already_persisted: bool
    next_action: str


class E3CumulativeResultValidationService:
    def __init__(
        self,
        store: TransactionalHistoryStore,
        batch: StageBatch,
        inbox: StageResultInbox | None = None,
    ):
        if (
            batch.stage_id != "E3"
            or batch.phase_id != "E3-CUMULATIVE"
        ):
            raise ValidationError(
                "E3_CUMULATIVE_BATCH_REQUIRED",
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
        if any(
            state.status != "ACCEPTED"
            or state.completion_status
            != "LANE_COMPLETED"
            for state in (
                self.inbox.lane_statuses.values()
            )
        ):
            raise ValidationError(
                "E3_CUMULATIVE_PHASE_NOT_COMPLETE"
            )

    def _view_manifest(
        self,
        cut: dict[str, Any],
    ) -> dict[str, Any]:
        digests = {
            job.view_manifest_ref.get(
                "revision_digest"
            )
            for job in self.batch.jobs.values()
            if job.view_manifest_ref
        }
        digests.discard(None)
        if len(digests) != 1:
            raise ValidationError(
                "E3_CUMULATIVE_VIEW_BINDING_REQUIRED"
            )
        digest = next(iter(digests))
        rows = [
            row
            for row in self.store.accepted_records(
                "view_manifest",
                cut,
            )
            if row["ref"]["revision_digest"]
            == digest
            and row["body"].get("phase_id")
            == "E3-CUMULATIVE"
        ]
        if len(rows) != 1:
            raise ValidationError(
                "E3_CUMULATIVE_VIEW_BINDING_REQUIRED"
            )
        return rows[0]

    def _authorized_claim_digests(
        self,
        manifest: dict[str, Any],
    ) -> set[str]:
        return {
            ref["revision_digest"]
            for ref in manifest["body"].get(
                "allowed_artifact_refs",
                [],
            )
            if isinstance(ref, dict)
            and ref.get("kind")
            == "finding_claim_revision"
            and isinstance(
                ref.get("revision_digest"),
                str,
            )
        }

    def _own_discoveries_by_lane(
        self,
        manifest: dict[str, Any],
        cut: dict[str, Any],
    ) -> dict[
        str, dict[str, dict[str, Any]]
    ]:
        allowed_discovery_digests = {
            ref["revision_digest"]
            for ref in manifest["body"].get(
                "allowed_artifact_refs",
                [],
            )
            if isinstance(ref, dict)
            and ref.get("kind")
            == "discovery_record"
            and isinstance(
                ref.get("revision_digest"),
                str,
            )
        }
        mapped: dict[
            str, dict[str, dict[str, Any]]
        ] = {
            slot: {}
            for slot in self.batch.jobs
        }
        for row in self.store.accepted_records(
            "discovery_record",
            cut,
        ):
            if row["ref"][
                "revision_digest"
            ] not in allowed_discovery_digests:
                continue
            body = row["body"]
            if (
                body.get("stage_id") != "E3"
                or body.get("phase_id")
                not in {"E3-BLIND", "E3-GAP"}
            ):
                continue
            slot = body.get("lane_slot")
            discovery_id = body.get(
                "discovery_id"
            )
            if (
                slot not in mapped
                or not isinstance(
                    discovery_id,
                    str,
                )
            ):
                continue
            if discovery_id in mapped[slot]:
                raise ValidationError(
                    "E3_CUMULATIVE_DUPLICATE_OWN_DISCOVERY_ID",
                    discovery_id,
                )
            mapped[slot][
                discovery_id
            ] = row
        return mapped

    def _accepted_results(
        self,
        cut: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        mapped: dict[
            str, dict[str, Any]
        ] = {}
        for slot, job in self.batch.jobs.items():
            rows = [
                row
                for row in self.store.accepted_records(
                    "bdb_audit_lane_result",
                    cut,
                )
                if row["body"].get("stage_id")
                == "E3"
                and row["body"].get("phase_id")
                == "E3-CUMULATIVE"
                and _same_ref(
                    row["body"].get(
                        "assignment_ref"
                    ),
                    job.assignment_ref,
                )
            ]
            if len(rows) != 1:
                raise ValidationError(
                    "E3_CUMULATIVE_RESULT_SET_INCOMPLETE",
                    (
                        f"{slot}: expected 1, "
                        f"got {len(rows)}"
                    ),
                )
            mapped[slot] = rows[0]
        return mapped

    def _checkpoint_by_slot(
        self,
        cut: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        mapped: dict[
            str, dict[str, Any]
        ] = {}
        for row in self.store.accepted_records(
            "checkpoint",
            cut,
        ):
            body = row["body"]
            if (
                body.get("stage_id") == "E3"
                and body.get("phase_id")
                == "E3-BLIND"
                and body.get("lane_slot")
                in self.batch.jobs
            ):
                mapped[
                    body["lane_slot"]
                ] = row
        missing = sorted(
            set(self.batch.jobs) - set(mapped)
        )
        if missing:
            raise ValidationError(
                "E3_BLIND_CHECKPOINT_REQUIRED",
                ",".join(missing),
            )
        return mapped

    def _persist_new_discoveries(
        self,
        *,
        cut: dict[str, Any],
        prior_commit: dict[str, Any],
        results: dict[
            str, dict[str, Any]
        ],
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
        for slot, result in results.items():
            findings = result["body"].get(
                "findings",
                [],
            )
            if not isinstance(findings, list):
                raise ValidationError(
                    "INVALID_FINDING_STRUCTURE",
                    "E3-CUMULATIVE",
                )
            for index, finding in enumerate(
                findings
            ):
                if not isinstance(finding, dict):
                    raise ValidationError(
                        "INVALID_FINDING_STRUCTURE",
                        "E3-CUMULATIVE",
                    )
                if finding.get(
                    "classification"
                ) in {
                    "PRE_REVEAL_DISCOVERY",
                    "BLIND_NOVELTY",
                }:
                    raise ValidationError(
                        "POST_REVEAL_DISCOVERY_MISCLASSIFIED_AS_BLIND"
                    )
                expected[(slot, index)] = {
                    "result": result,
                    "finding": finding,
                    "fingerprint": hashlib.sha256(
                        canonical_bytes(finding)
                    ).hexdigest(),
                }

        if not expected:
            head = self.store.head()
            return (
                (),
                head.commit_seq if head else 0,
                True,
            )

        result_digests = {
            row["ref"]["revision_digest"]
            for row in results.values()
        }
        existing: dict[
            tuple[str, int],
            dict[str, Any],
        ] = {}
        for row in self.store.accepted_records(
            "discovery_record",
            cut,
        ):
            body = row["body"]
            if (
                body.get("stage_id") != "E3"
                or body.get("phase_id")
                != "E3-CUMULATIVE"
                or body.get(
                    "result_proposal_digest"
                )
                not in result_digests
            ):
                continue
            key = (
                body.get("lane_slot"),
                body.get(
                    "submission_finding_index"
                ),
            )
            if (
                not isinstance(key[0], str)
                or not isinstance(key[1], int)
            ):
                raise ValidationError(
                    "E3_CUMULATIVE_DISCOVERY_PROVENANCE_INVALID"
                )
            if key in existing:
                raise ValidationError(
                    "MULTIPLE_E3_CUMULATIVE_DISCOVERY_RECORDS",
                    f"{key[0]}:{key[1]}",
                )
            existing[key] = row

        if existing:
            if set(existing) != set(expected):
                raise ValidationError(
                    "PARTIAL_E3_CUMULATIVE_DISCOVERY_SET"
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
                        "E3_CUMULATIVE_DISCOVERY_FINGERPRINT_DRIFT"
                    )
            seqs = {
                row["accepted_seq"]
                for row in existing.values()
            }
            if len(seqs) != 1:
                raise ValidationError(
                    "E3_CUMULATIVE_DISCOVERY_COMMIT_DIVERGENCE"
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
                    "E3_CUMULATIVE_AUTHORIZED_KNOWLEDGE_REQUIRED",
                    slot,
                )
            knowledge = self.store.resolve_accepted(
                job.authorized_knowledge_state_ref,
                cut,
            )
            result = item["result"]
            objects.append(
                CanonicalObject(
                    "discovery_record",
                    {
                        "discovery_id": (
                            "disc_E3_CUMULATIVE_"
                            + slot
                            + "_"
                            + result["ref"][
                                "revision_digest"
                            ][:12]
                            + "_"
                            + str(index + 1)
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
                            "e3_cumulative_"
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
                        "phase_id": (
                            "E3-CUMULATIVE"
                        ),
                        "lane_slot": slot,
                        "origin_classification": (
                            "POST_REVEAL_CONFIRMATION"
                        ),
                        "discovery_mode": (
                            "CUMULATIVE_CORPUS_ASSISTED"
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
                "e3_cumulative_discoveries:"
                + seed
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
                "e3_cumulative_discoveries:"
                + seed
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
    ) -> E3CumulativeValidationSummary:
        self._require_complete()
        cut, prior_commit = _current_cut(
            self.store
        )
        manifest = self._view_manifest(cut)
        prior_claims = (
            self._authorized_claim_digests(
                manifest
            )
        )
        own_by_lane = (
            self._own_discoveries_by_lane(
                manifest,
                cut,
            )
        )
        results = self._accepted_results(cut)

        matched_ids: set[str] = set()
        no_match_ids: set[str] = set()
        comparison_count = 0

        for slot, result in results.items():
            expected_ids = set(
                own_by_lane.get(
                    slot,
                    {},
                )
            )
            outputs = result["body"].get(
                "outputs",
                {},
            )
            rows = (
                outputs.get("corpus_matches")
                if isinstance(outputs, dict)
                else None
            )
            if not isinstance(rows, list):
                raise ValidationError(
                    "E3_CUMULATIVE_MATCHES_REQUIRED",
                    slot,
                )
            seen: set[str] = set()
            for row in rows:
                if not isinstance(row, dict):
                    raise ValidationError(
                        "E3_CUMULATIVE_MATCH_INVALID",
                        slot,
                    )
                discovery_id = row.get(
                    "discovery_id"
                )
                if (
                    not isinstance(
                        discovery_id,
                        str,
                    )
                    or discovery_id
                    not in expected_ids
                ):
                    raise ValidationError(
                        "E3_CUMULATIVE_UNKNOWN_DISCOVERY",
                        str(discovery_id),
                    )
                if discovery_id in seen:
                    raise ValidationError(
                        "E3_CUMULATIVE_DUPLICATE_DISCOVERY_MATCH",
                        discovery_id,
                    )
                seen.add(discovery_id)
                relation = row.get("relation")
                if relation not in _RELATIONS:
                    raise ValidationError(
                        "E3_CUMULATIVE_RELATION_INVALID",
                        discovery_id,
                    )
                digests = row.get(
                    "matched_prior_claim_revision_digests",
                    [],
                )
                if (
                    not isinstance(digests, list)
                    or any(
                        not isinstance(
                            digest,
                            str,
                        )
                        for digest in digests
                    )
                    or len(digests)
                    != len(set(digests))
                ):
                    raise ValidationError(
                        "E3_CUMULATIVE_MATCH_SET_INVALID",
                        discovery_id,
                    )
                outside = sorted(
                    set(digests) - prior_claims
                )
                if outside:
                    raise ValidationError(
                        "E3_CUMULATIVE_MATCH_OUTSIDE_AUTHORIZED_VIEW",
                        ",".join(outside),
                    )
                if (
                    relation == "NO_PRIOR_MATCH"
                    and digests
                ):
                    raise ValidationError(
                        "E3_CUMULATIVE_NO_MATCH_WITH_REFERENCES",
                        discovery_id,
                    )
                if (
                    relation
                    in {
                        "MATCHED_PRIOR",
                        "CONFLICT",
                    }
                    and not digests
                ):
                    raise ValidationError(
                        "E3_CUMULATIVE_MATCH_REFERENCE_REQUIRED",
                        discovery_id,
                    )
                rationale = row.get(
                    "rationale",
                    "",
                )
                if not isinstance(rationale, str):
                    raise ValidationError(
                        "E3_CUMULATIVE_RATIONALE_INVALID",
                        discovery_id,
                    )
                if relation == "NO_PRIOR_MATCH":
                    no_match_ids.add(
                        discovery_id
                    )
                elif relation in {
                    "MATCHED_PRIOR",
                    "CONFLICT",
                }:
                    matched_ids.add(
                        discovery_id
                    )
                comparison_count += 1

            missing = sorted(
                expected_ids - seen
            )
            extra = sorted(
                seen - expected_ids
            )
            if missing or extra:
                raise ValidationError(
                    "E3_CUMULATIVE_DISCOVERY_SET_INCOMPLETE",
                    (
                        f"{slot}: "
                        f"missing={missing}; "
                        f"extra={extra}"
                    ),
                )

        (
            discovery_refs,
            commit_seq,
            already_persisted,
        ) = self._persist_new_discoveries(
            cut=cut,
            prior_commit=prior_commit,
            results=results,
        )

        return E3CumulativeValidationSummary(
            campaign_id=self.batch.campaign_id,
            comparison_count=(
                comparison_count
            ),
            matched_discovery_ids=tuple(
                sorted(matched_ids)
            ),
            no_prior_match_discovery_ids=tuple(
                sorted(no_match_ids)
            ),
            post_reveal_discovery_refs=(
                discovery_refs
            ),
            accepted_commit_seq=(
                commit_seq
            ),
            already_persisted=(
                already_persisted
            ),
            next_action=(
                "PREPARE_OPTIONAL_E3_HOLDOUT_OR_FINALIZE"
            ),
        )


__all__ = [
    "E3CumulativeResultValidationService",
    "E3CumulativeValidationSummary",
]

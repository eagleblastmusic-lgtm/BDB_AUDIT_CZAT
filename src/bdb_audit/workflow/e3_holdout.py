"""Optional E3 external holdout reveal authorization.

A holdout may be revealed only after the campaign has produced its own E3
discovery and completed the cumulative comparison phase. The accepted
corpus_manifest must declare corpus_role=AUXILIARY_HOLDOUT.

The reveal is one-way: accepting the ViewManifest/Grant makes that holdout
potentially exposed and therefore CONSUMED for unseen-evaluation purposes.
Retries reconstruct the same authorization; a different holdout cannot silently
reuse the same E3-HOLDOUT phase/attempts.

The holdout remains auxiliary and never becomes the canonical predecessor.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from ..coordinator import Coordinator
from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, CommandEnvelope, HistoryCut
from ..history.store import TransactionalHistoryStore
from .assignments import _command_id, _current_cut
from .inbox import _same_ref, _with_ref_class
from .manual_stage import (
    StageAssignmentService,
    StageAuthorizedContext,
    StageIsolationProof,
    StageLaneDefinition,
)


_OWN_DISCOVERY_PHASES = {
    "E3-BLIND",
    "E3-GAP",
    "E3-CUMULATIVE",
}


def _phase_complete(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
    *,
    phase_id: str,
    lane_slots: Sequence[str],
) -> None:
    results = [
        row
        for row in store.accepted_records(
            "bdb_audit_lane_result",
            cut,
        )
        if row["body"].get("stage_id") == "E3"
        and row["body"].get("phase_id") == phase_id
        and row["body"].get("lane_slot") in lane_slots
    ]
    by_slot: dict[str, dict[str, Any]] = {}
    for row in results:
        slot = row["body"].get("lane_slot")
        if not isinstance(slot, str) or slot in by_slot:
            raise ValidationError(
                "E3_PHASE_RESULT_SET_AMBIGUOUS",
                f"{phase_id}:{slot}",
            )
        by_slot[slot] = row
    missing = sorted(set(lane_slots) - set(by_slot))
    if missing:
        raise ValidationError(
            "E3_CUMULATIVE_RESULT_SET_INCOMPLETE",
            ",".join(missing),
        )

    digests = {
        row["ref"]["revision_digest"]
        for row in by_slot.values()
    }
    completed: set[str] = set()
    for row in store.accepted_records(
        "lane_completion",
        cut,
    ):
        if (
            row["body"].get(
                "completion_predicate_result"
            )
            != "LANE_COMPLETED"
        ):
            continue
        for ref in row["body"].get(
            "required_output_refs",
            [],
        ):
            if (
                isinstance(ref, dict)
                and ref.get("kind")
                == "bdb_audit_lane_result"
                and ref.get("revision_digest") in digests
            ):
                completed.add(
                    ref["revision_digest"]
                )
    if completed != digests:
        raise ValidationError(
            "E3_CUMULATIVE_PHASE_NOT_COMPLETE"
        )


def _own_discovery_rows(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    rows = tuple(
        row
        for row in store.accepted_records(
            "discovery_record",
            cut,
        )
        if row["body"].get("stage_id") == "E3"
        and row["body"].get("phase_id")
        in _OWN_DISCOVERY_PHASES
    )
    if not rows:
        raise ValidationError(
            "E3_HOLDOUT_REQUIRES_OWN_DISCOVERY"
        )
    return rows


def _own_discovery_cards(
    rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    cards = []
    for row in sorted(
        rows,
        key=lambda item: item["ref"][
            "revision_digest"
        ],
    ):
        body = row["body"]
        cards.append(
            {
                "discovery_ref": _with_ref_class(
                    row["ref"],
                    "CONTENT_OR_PRIOR",
                ),
                "discovery_id": body.get(
                    "discovery_id"
                ),
                "originating_phase": body.get(
                    "phase_id"
                ),
                "originating_lane": body.get(
                    "lane_slot"
                ),
                "origin_classification": (
                    body.get(
                        "origin_classification"
                    )
                ),
                "finding_fingerprint": (
                    body.get(
                        "submission_finding_fingerprint"
                    )
                ),
            }
        )
    return cards


def build_e3_holdout_view(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
    holdout_corpus_manifest_ref: Mapping[
        str, Any
    ],
) -> tuple[
    bytes,
    tuple[dict[str, Any], ...],
    dict[str, Any],
]:
    holdout = store.resolve_accepted(
        dict(holdout_corpus_manifest_ref),
        cut,
    )
    if holdout["ref"]["kind"] != "corpus_manifest":
        raise ValidationError(
            "E3_HOLDOUT_CORPUS_MANIFEST_REQUIRED"
        )
    role = holdout["body"].get(
        "corpus_role"
    )
    if role != "AUXILIARY_HOLDOUT":
        raise ValidationError(
            "E3_HOLDOUT_ROLE_INVALID",
            str(role),
        )

    discoveries = _own_discovery_rows(
        store,
        cut,
    )
    cards = _own_discovery_cards(
        discoveries
    )
    payload = {
        "format": "BDB-E3-EXTERNAL-HOLDOUT-VIEW-1",
        "phase": "E3-HOLDOUT",
        "corpus_role": role,
        "holdout_corpus_manifest_ref": (
            _with_ref_class(
                holdout["ref"],
                "CONTENT_OR_PRIOR",
            )
        ),
        "holdout_manifest": dict(
            holdout["body"]
        ),
        "own_e3_discoveries": cards,
        "matching_rules": {
            "scope": (
                "MATCH_RELATIVE_TO_THIS_EXACT_HOLDOUT_MANIFEST"
            ),
            "text_absence_is_not_false_negative_proof": True,
            "ambiguous_similarity_result": "INCONCLUSIVE",
            "canonical_false_negative_requires_later_relationship_assessment": True,
        },
        "consumption_rule": (
            "ACCEPTED_GRANT_MAKES_HOLDOUT_CONSUMED_FOR_UNSEEN_EVALUATION"
        ),
    }
    allowed = [
        holdout,
        *discoveries,
    ]
    return (
        canonical_bytes(payload),
        tuple(allowed),
        holdout,
    )


class E3HoldoutAuthorizationService:
    def __init__(
        self,
        store: TransactionalHistoryStore,
        *,
        holdout_corpus_manifest_ref: Mapping[
            str, Any
        ],
        lane_definitions: Sequence[
            StageLaneDefinition
        ],
        all_stage_lane_slots: Sequence[str],
        executor_profile: str,
        model: str,
        isolation_proofs_by_slot: Mapping[
            str, StageIsolationProof
        ] | None = None,
    ):
        self.store = store
        self.holdout_corpus_manifest_ref = dict(
            holdout_corpus_manifest_ref
        )
        self.lane_definitions = tuple(
            lane_definitions
        )
        self.all_stage_lane_slots = tuple(
            all_stage_lane_slots
        )
        self.executor_profile = executor_profile
        self.model = model
        self.isolation_proofs_by_slot = dict(
            isolation_proofs_by_slot or {}
        )
        cut, _ = _current_cut(self.store)
        _, _, lanes = StageAssignmentService(
            self.store
        )._prerequisites(
            cut,
            "E3",
            tuple(
                definition.lane_slot
                for definition in self.lane_definitions
            ),
        )
        missing = sorted(
            definition.lane_slot
            for definition in self.lane_definitions
            if lanes[definition.lane_slot]["body"].get(
                "required_isolation_assurance",
                "DECLARED",
            )
            == "ENFORCED"
            and definition.lane_slot
            not in self.isolation_proofs_by_slot
        )
        if missing:
            raise ValidationError(
                "E3_HOLDOUT_ENFORCED_ISOLATION_PROOF_REQUIRED",
                ",".join(missing),
            )
        self.coordinator = Coordinator(store)

    def _existing(
        self,
        *,
        cut: dict[str, Any],
        assignments,
        holdout_digest: str,
        payload_sha256: str,
        context_members: dict[str, bytes],
        context_manifest: dict[str, str],
    ) -> StageAuthorizedContext | None:
        phase_manifests = [
            row
            for row in self.store.accepted_records(
                "view_manifest",
                cut,
            )
            if row["body"].get("phase_id")
            == "E3-HOLDOUT"
        ]
        matching = []
        other = []
        for row in phase_manifests:
            allowed = {
                ref.get("revision_digest")
                for ref in row["body"].get(
                    "allowed_artifact_refs",
                    [],
                )
                if isinstance(ref, dict)
                and ref.get("kind")
                == "corpus_manifest"
            }
            if holdout_digest in allowed:
                matching.append(row)
            else:
                other.append(row)
        if other:
            raise ValidationError(
                "E3_HOLDOUT_PHASE_ALREADY_CONSUMED"
            )
        if len(matching) > 1:
            raise ValidationError(
                "MULTIPLE_E3_HOLDOUT_VIEW_MANIFESTS"
            )
        if not matching:
            return None
        manifest = matching[0]
        if (
            manifest["body"].get(
                "payload_sha256"
            )
            != payload_sha256
        ):
            raise ValidationError(
                "E3_HOLDOUT_VIEW_DRIFT"
            )

        grants: dict[
            str, dict[str, Any]
        ] = {}
        states: dict[
            str, dict[str, Any]
        ] = {}
        for slot, assignment in (
            assignments.assignments.items()
        ):
            grant_rows = [
                row
                for row in self.store.accepted_records(
                    "grant_body",
                    cut,
                )
                if _same_ref(
                    row["body"].get(
                        "attempt_ref"
                    ),
                    assignment.attempt_ref,
                )
                and _same_ref(
                    row["body"].get(
                        "view_manifest_ref"
                    ),
                    manifest["ref"],
                )
            ]
            state_rows = [
                row
                for row in self.store.accepted_records(
                    "knowledge_state",
                    cut,
                )
                if _same_ref(
                    row["body"].get(
                        "attempt_ref"
                    ),
                    assignment.attempt_ref,
                )
                and any(
                    _same_ref(
                        ref,
                        manifest["ref"],
                    )
                    for ref in row["body"].get(
                        "allowed_view_refs",
                        [],
                    )
                    if isinstance(ref, dict)
                )
            ]
            if (
                len(grant_rows) != 1
                or len(state_rows) != 1
            ):
                raise ValidationError(
                    "PARTIAL_E3_HOLDOUT_AUTHORIZATION",
                    slot,
                )
            grants[slot] = _with_ref_class(
                grant_rows[0]["ref"],
                "CONTENT_OR_PRIOR",
            )
            states[slot] = _with_ref_class(
                state_rows[0]["ref"],
                "CONTENT_OR_PRIOR",
            )

        return StageAuthorizedContext(
            campaign_id=assignments.campaign_id,
            stage_id="E3",
            phase_id="E3-HOLDOUT",
            context_members=context_members,
            context_manifest=context_manifest,
            view_manifest_ref=_with_ref_class(
                manifest["ref"],
                "CONTENT_OR_PRIOR",
            ),
            grant_refs_by_slot=grants,
            knowledge_state_refs_by_slot=states,
            authorization_history_cut=dict(
                cut
            ),
            assignments=dict(
                assignments.assignments
            ),
            already_authorized=True,
        )

    def authorize(
        self,
    ) -> StageAuthorizedContext:
        pre_cut, _ = _current_cut(
            self.store
        )
        _phase_complete(
            self.store,
            pre_cut,
            phase_id="E3-CUMULATIVE",
            lane_slots=self.all_stage_lane_slots,
        )
        build_e3_holdout_view(
            self.store,
            pre_cut,
            self.holdout_corpus_manifest_ref,
        )

        assignments = StageAssignmentService(
            self.store
        ).prepare_phase_assignments(
            stage_id="E3",
            phase_id="E3-HOLDOUT",
            lane_definitions=(
                self.lane_definitions
            ),
            all_stage_lane_slots=(
                self.all_stage_lane_slots
            ),
            executor_profile=(
                self.executor_profile
            ),
            model=self.model,
            isolation_proofs_by_slot=(
                self.isolation_proofs_by_slot
            ),
        )

        cut, prior_commit = _current_cut(
            self.store
        )
        payload_raw, allowed_rows, holdout = (
            build_e3_holdout_view(
                self.store,
                cut,
                self.holdout_corpus_manifest_ref,
            )
        )
        payload_sha = hashlib.sha256(
            payload_raw
        ).hexdigest()
        context_members = {
            "E3_EXTERNAL_HOLDOUT_VIEW.json": (
                payload_raw
            )
        }
        context_manifest = {
            name: hashlib.sha256(
                raw
            ).hexdigest()
            for name, raw in sorted(
                context_members.items()
            )
        }
        holdout_digest = holdout["ref"][
            "revision_digest"
        ]

        existing = self._existing(
            cut=cut,
            assignments=assignments,
            holdout_digest=holdout_digest,
            payload_sha256=payload_sha,
            context_members=context_members,
            context_manifest=context_manifest,
        )
        if existing is not None:
            return existing

        policy = CanonicalObject(
            "projection_policy",
            {
                "policy_id": (
                    "E3_EXTERNAL_HOLDOUT_APPROVED_VIEW"
                ),
                "policy_revision": "1",
                "phase": "E3-HOLDOUT",
                "allowed_fields": {
                    "holdout_manifest": [
                        "corpus_role",
                        "exact_membership",
                        "descriptive_metadata",
                    ],
                    "own_discovery": [
                        "discovery_id",
                        "originating_phase",
                        "originating_lane",
                        "origin_classification",
                        "finding_fingerprint",
                    ],
                },
                "allowed_kinds": [
                    "holdout_manifest",
                    "own_discovery",
                ],
                "forbidden_kinds": [
                    "canonical_predecessor_reclassification",
                    "producer_identity",
                    "support_count",
                ],
                "reveal_support_count": False,
                "reveal_filenames": False,
                "matching_rules": {
                    "exact_corpus_manifest_digest": (
                        holdout_digest
                    ),
                    "text_absence_is_not_false_negative_proof": True,
                    "ambiguous_similarity_result": "INCONCLUSIVE",
                },
            },
        )
        allowed_refs = canonical_reference_set(
            [
                _with_ref_class(
                    row["ref"],
                    "CONTENT_OR_PRIOR",
                )
                for row in allowed_rows
            ]
        )
        manifest = CanonicalObject(
            "view_manifest",
            {
                "view_id": (
                    "view_e3_holdout_"
                    + payload_sha[:24]
                ),
                "phase_id": "E3-HOLDOUT",
                "projection_policy_ref": (
                    policy.as_ref(
                        ref_class="CONTENT_OR_PRIOR"
                    ).as_dict()
                ),
                "allowed_artifact_refs": (
                    allowed_refs
                ),
                "payload_manifest": (
                    context_manifest
                ),
                "payload_sha256": payload_sha,
                "allowed_view_classes": [
                    "AUXILIARY_HOLDOUT",
                    "E3_OWN_DISCOVERY_SUMMARY",
                ],
                "forbidden_knowledge_classes": [
                    "CANONICAL_PREDECESSOR_PROMOTION",
                ],
            },
        )

        objects: list[
            CanonicalObject
        ] = [
            policy,
            manifest,
        ]
        grants: dict[
            str, CanonicalObject
        ] = {}
        states: dict[
            str, CanonicalObject
        ] = {}
        for slot, assignment in (
            assignments.assignments.items()
        ):
            attempt = self.store.resolve_accepted(
                assignment.attempt_ref,
                cut,
            )
            initial = self.store.resolve_accepted(
                assignment.knowledge_state_ref,
                cut,
            )
            isolation = self.store.resolve_accepted(
                initial["body"][
                    "isolation_qualification_ref"
                ],
                cut,
            )
            grant = CanonicalObject(
                "grant_body",
                {
                    "attempt_ref": _with_ref_class(
                        attempt["ref"],
                        "CONTENT_OR_PRIOR",
                    ),
                    "grant_input_history_cut": cut,
                    "view_manifest_ref": (
                        manifest.as_ref(
                            ref_class="CONTENT_OR_PRIOR"
                        ).as_dict()
                    ),
                    "delivery_profile_ref": (
                        attempt["body"][
                            "delivery_profile_ref"
                        ]
                    ),
                    "forbidden_knowledge_policy_ref": (
                        "BDB_POLICY::E3_HOLDOUT_AUXILIARY_ONLY"
                    ),
                    "channel_class": (
                        "EXTERNAL_HOLDOUT_VIEW"
                    ),
                    "previous_knowledge_state_ref": (
                        _with_ref_class(
                            initial["ref"],
                            "PRIOR_ACCEPTED_ONLY",
                        )
                    ),
                },
            )
            exposure = CanonicalObject(
                "potential_exposure_record",
                {
                    "attempt_ref": _with_ref_class(
                        attempt["ref"],
                        "CONTENT_OR_PRIOR",
                    ),
                    "grant_ref": grant.as_ref(
                        ref_class="CONTENT_OR_PRIOR"
                    ).as_dict(),
                    "view_manifest_ref": (
                        manifest.as_ref(
                            ref_class="CONTENT_OR_PRIOR"
                        ).as_dict()
                    ),
                    "exposure_input_history_cut": (
                        cut
                    ),
                    "previous_knowledge_state_ref": (
                        _with_ref_class(
                            initial["ref"],
                            "PRIOR_ACCEPTED_ONLY",
                        )
                    ),
                },
            )
            state = CanonicalObject(
                "knowledge_state",
                {
                    "knowledge_state_id": (
                        "knowledge_E3_HOLDOUT_"
                        + slot
                        + "_"
                        + payload_sha[:12]
                    ),
                    "attempt_ref": _with_ref_class(
                        attempt["ref"],
                        "CONTENT_OR_PRIOR",
                    ),
                    "basis_history_cut": cut,
                    "isolation_qualification_ref": (
                        _with_ref_class(
                            isolation["ref"],
                            "CONTENT_OR_PRIOR",
                        )
                    ),
                    "allowed_view_refs": [
                        manifest.as_ref(
                            ref_class="CONTENT_OR_PRIOR"
                        ).as_dict()
                    ],
                    "contamination_assessment_refs": [],
                    "potential_exposure_refs": [
                        exposure.as_ref(
                            ref_class="CONTENT_OR_PRIOR"
                        ).as_dict()
                    ],
                    "previous_knowledge_state_ref": (
                        _with_ref_class(
                            initial["ref"],
                            "PRIOR_ACCEPTED_ONLY",
                        )
                    ),
                    "known_classes": [
                        "AUXILIARY_HOLDOUT",
                        "CONSUMED_EXTERNAL_HOLDOUT",
                    ],
                },
            )
            objects.extend(
                [
                    grant,
                    exposure,
                    state,
                ]
            )
            grants[slot] = grant
            states[slot] = state

        head = self.store.head()
        if head is None:
            raise ValidationError(
                "CAMPAIGN_NOT_INITIALIZED"
            )
        seed = hashlib.sha256(
            canonical_bytes(
                {
                    "holdout_digest": (
                        holdout_digest
                    ),
                    "payload_sha256": (
                        payload_sha
                    ),
                    "assignment_digests": sorted(
                        assignment.assignment_ref[
                            "revision_digest"
                        ]
                        for assignment in (
                            assignments.assignments.values()
                        )
                    ),
                }
            )
        ).hexdigest()
        command = CommandEnvelope(
            command_id=_command_id(
                "e3_holdout_authorization:"
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
                "e3_holdout_authorization:"
                + seed
            ),
            campaign_ref=head.campaign_id,
        )
        accepted = self.coordinator.accept(
            command,
            immutable_objects=objects,
            expected_head=head,
        )
        accepted_cut = HistoryCut.accepted(
            accepted.head,
            accepted.commit.governing_policy_ref,
            accepted.commit.governing_spec_refs,
        ).as_dict()

        return StageAuthorizedContext(
            campaign_id=assignments.campaign_id,
            stage_id="E3",
            phase_id="E3-HOLDOUT",
            context_members=context_members,
            context_manifest=context_manifest,
            view_manifest_ref=manifest.as_ref(
                ref_class="CONTENT_OR_PRIOR"
            ).as_dict(),
            grant_refs_by_slot={
                slot: obj.as_ref(
                    ref_class="CONTENT_OR_PRIOR"
                ).as_dict()
                for slot, obj in grants.items()
            },
            knowledge_state_refs_by_slot={
                slot: obj.as_ref(
                    ref_class="CONTENT_OR_PRIOR"
                ).as_dict()
                for slot, obj in states.items()
            },
            authorization_history_cut=(
                accepted_cut
            ),
            assignments=dict(
                assignments.assignments
            ),
            already_authorized=False,
        )


__all__ = [
    "E3HoldoutAuthorizationService",
    "build_e3_holdout_view",
]

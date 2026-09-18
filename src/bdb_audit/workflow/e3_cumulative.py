"""E3 cumulative E1/E2 corpus reveal authorization.

This phase executes only after the blind checkpoint and gap-directed discovery.
It creates a bounded approved view that combines:
- the current campaign's *own* E3 blind/gap discoveries; and
- accepted E1/E2 finding/adjudication/contradiction material.

The view intentionally excludes raw external reports, producer identity,
popularity/support counts and unrestricted evidence payloads.  The purpose is
late comparison and false-negative analysis, never retroactive blind-origin
promotion.

Every lane receives a fresh attempt and a fresh accepted isolation proof.
Grant, PotentialExposureRecord and successor KnowledgeState are accepted before
package publication.
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


_E3_OWN_PHASES = {
    "E3-BLIND",
    "E3-GAP",
}


def _accepted_gap_phase_complete(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
    lane_slots: Sequence[str],
) -> None:
    results = [
        row
        for row in store.accepted_records(
            "bdb_audit_lane_result",
            cut,
        )
        if row["body"].get("stage_id") == "E3"
        and row["body"].get("phase_id") == "E3-GAP"
        and row["body"].get("lane_slot") in lane_slots
    ]
    by_slot: dict[str, dict[str, Any]] = {}
    for row in results:
        slot = row["body"].get("lane_slot")
        if (
            not isinstance(slot, str)
            or slot in by_slot
        ):
            raise ValidationError(
                "E3_GAP_RESULT_SET_AMBIGUOUS",
                str(slot),
            )
        by_slot[slot] = row
    missing = sorted(
        set(lane_slots) - set(by_slot)
    )
    if missing:
        raise ValidationError(
            "E3_GAP_RESULT_SET_INCOMPLETE",
            ",".join(missing),
        )

    result_digests = {
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
                and ref.get("revision_digest")
                in result_digests
            ):
                completed.add(
                    ref["revision_digest"]
                )
    if completed != result_digests:
        raise ValidationError(
            "E3_GAP_PHASE_NOT_COMPLETE"
        )


def _finding_from_own_discovery(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
    discovery: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    body = discovery["body"]
    attempt = body.get("attempt_ref")
    index = body.get(
        "submission_finding_index"
    )
    if (
        not isinstance(attempt, dict)
        or not isinstance(index, int)
        or index < 0
    ):
        return None, None

    matches = [
        row
        for row in store.accepted_records(
            "bdb_audit_lane_result",
            cut,
        )
        if row["body"].get("stage_id") == "E3"
        and row["body"].get("phase_id")
        in _E3_OWN_PHASES
        and _same_ref(
            row["body"].get("attempt_ref"),
            attempt,
        )
    ]
    if len(matches) != 1:
        return None, None
    result = matches[0]
    findings = result["body"].get(
        "findings",
        [],
    )
    if (
        not isinstance(findings, list)
        or index >= len(findings)
        or not isinstance(findings[index], dict)
    ):
        return result, None
    return result, findings[index]


def _own_discovery_view(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    cards: list[dict[str, Any]] = []
    allowed: dict[
        tuple[str, str], dict[str, Any]
    ] = {}
    for row in store.accepted_records(
        "discovery_record",
        cut,
    ):
        body = row["body"]
        if (
            body.get("stage_id") != "E3"
            or body.get("phase_id")
            not in _E3_OWN_PHASES
        ):
            continue
        result, finding = (
            _finding_from_own_discovery(
                store,
                cut,
                row,
            )
        )
        card: dict[str, Any] = {
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
        if finding is not None:
            for key in (
                "statement",
                "claim",
                "mechanism",
                "location",
                "affected_component",
                "asserted_observable",
            ):
                value = finding.get(key)
                if isinstance(
                    value,
                    (
                        str,
                        int,
                        float,
                        bool,
                    ),
                ) or value is None:
                    if value is not None:
                        card[key] = value
        cards.append(card)
        allowed[
            (
                row["ref"]["kind"],
                row["ref"]["revision_digest"],
            )
        ] = row
        if result is not None:
            allowed[
                (
                    result["ref"]["kind"],
                    result["ref"][
                        "revision_digest"
                    ],
                )
            ] = result

    cards.sort(
        key=lambda item: (
            str(item.get("originating_lane")),
            str(item.get("discovery_id")),
        )
    )
    return (
        cards,
        [
            allowed[key]
            for key in sorted(allowed)
        ],
    )


def _prior_corpus_view(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    cards: list[dict[str, Any]] = []
    contradiction_cards: list[
        dict[str, Any]
    ] = []
    allowed: dict[
        tuple[str, str], dict[str, Any]
    ] = {}

    for decision in sorted(
        store.accepted_records(
            "finding_adjudication_decision",
            cut,
        ),
        key=lambda row: row["ref"][
            "revision_digest"
        ],
    ):
        body = decision["body"]
        claim = store.resolve_accepted(
            body["claim_revision_ref"],
            cut,
        )
        axis_outcomes: dict[
            str, str | None
        ] = {}
        for axis, field in (
            ("MECHANISM", "mechanism_assessment_ref"),
            ("REACHABILITY", "reachability_assessment_ref"),
            ("IMPACT", "impact_assessment_ref"),
            ("SEVERITY", "severity_assessment_ref"),
        ):
            assessment = (
                store.resolve_accepted(
                    body[field],
                    cut,
                )
            )
            axis_outcomes[axis] = (
                assessment["body"].get(
                    "epistemic_outcome"
                )
            )
            allowed[
                (
                    assessment["ref"]["kind"],
                    assessment["ref"][
                        "revision_digest"
                    ],
                )
            ] = assessment

        cards.append(
            {
                "claim_revision_ref": (
                    _with_ref_class(
                        claim["ref"],
                        "CONTENT_OR_PRIOR",
                    )
                ),
                "adjudication_decision_ref": (
                    _with_ref_class(
                        decision["ref"],
                        "CONTENT_OR_PRIOR",
                    )
                ),
                "statement": claim["body"].get(
                    "statement",
                    "",
                ),
                "scope_refs": claim["body"].get(
                    "scope_refs",
                    [],
                ),
                "violated_invariant_refs": (
                    claim["body"].get(
                        "violated_invariant_refs",
                        [],
                    )
                ),
                "lifecycle_status": body.get(
                    "lifecycle_status"
                ),
                "axis_outcomes": axis_outcomes,
            }
        )
        for row in (
            decision,
            claim,
        ):
            allowed[
                (
                    row["ref"]["kind"],
                    row["ref"][
                        "revision_digest"
                    ],
                )
            ] = row

    for contradiction in sorted(
        store.accepted_records(
            "contradiction_revision",
            cut,
        ),
        key=lambda row: row["ref"][
            "revision_digest"
        ],
    ):
        body = contradiction["body"]
        contradiction_cards.append(
            {
                "contradiction_revision_ref": (
                    _with_ref_class(
                        contradiction["ref"],
                        "CONTENT_OR_PRIOR",
                    )
                ),
                "status": body.get("status"),
                "scope": body.get(
                    "scope",
                    {},
                ),
                "claim_revision_digests": sorted(
                    ref["revision_digest"]
                    for ref in body.get(
                        "claim_revision_refs",
                        [],
                    )
                    if isinstance(ref, dict)
                    and isinstance(
                        ref.get(
                            "revision_digest"
                        ),
                        str,
                    )
                ),
            }
        )
        allowed[
            (
                contradiction["ref"]["kind"],
                contradiction["ref"][
                    "revision_digest"
                ],
            )
        ] = contradiction

    if not cards:
        raise ValidationError(
            "E3_CUMULATIVE_E1_E2_CORPUS_REQUIRED"
        )
    return (
        cards,
        contradiction_cards,
        [
            allowed[key]
            for key in sorted(allowed)
        ],
    )


def build_e3_cumulative_view(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
) -> tuple[
    bytes,
    tuple[dict[str, Any], ...],
]:
    own_cards, own_rows = (
        _own_discovery_view(
            store,
            cut,
        )
    )
    (
        prior_cards,
        contradictions,
        prior_rows,
    ) = _prior_corpus_view(
        store,
        cut,
    )

    merged: dict[
        tuple[str, str], dict[str, Any]
    ] = {}
    for row in (
        *own_rows,
        *prior_rows,
    ):
        merged[
            (
                row["ref"]["kind"],
                row["ref"][
                    "revision_digest"
                ],
            )
        ] = row

    payload = {
        "format": (
            "BDB-E3-CUMULATIVE-CORPUS-VIEW-1"
        ),
        "phase": "E3-CUMULATIVE",
        "blind_origin_rule": (
            "LATE_CONFIRMATION_NEVER_CHANGES_PRIOR_KNOWLEDGE_STATE"
        ),
        "own_e3_discoveries": own_cards,
        "prior_e1_e2_adjudicated_claims": (
            prior_cards
        ),
        "prior_contradictions": (
            contradictions
        ),
    }
    return (
        canonical_bytes(payload),
        tuple(
            merged[key]
            for key in sorted(merged)
        ),
    )


class E3CumulativeAuthorizationService:
    """Authorize a late cumulative E1/E2 reveal after E3 gap discovery."""

    def __init__(
        self,
        store: TransactionalHistoryStore,
        *,
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
        self.lane_definitions = tuple(
            lane_definitions
        )
        self.all_stage_lane_slots = tuple(
            all_stage_lane_slots
        )
        self.executor_profile = (
            executor_profile
        )
        self.model = model
        self.isolation_proofs_by_slot = dict(
            isolation_proofs_by_slot or {}
        )
        missing = sorted(
            definition.lane_slot
            for definition in self.lane_definitions
            if definition.lane_slot
            not in self.isolation_proofs_by_slot
        )
        if missing:
            raise ValidationError(
                "E3_CUMULATIVE_ENFORCED_ISOLATION_PROOF_REQUIRED",
                ",".join(missing),
            )
        self.coordinator = Coordinator(store)

    def _existing(
        self,
        *,
        cut: dict[str, Any],
        assignments,
        payload_sha256: str,
        context_members: dict[str, bytes],
        context_manifest: dict[str, str],
    ) -> StageAuthorizedContext | None:
        manifests = [
            row
            for row in self.store.accepted_records(
                "view_manifest",
                cut,
            )
            if row["body"].get("phase_id")
            == "E3-CUMULATIVE"
            and row["body"].get(
                "payload_sha256"
            )
            == payload_sha256
        ]
        if len(manifests) > 1:
            raise ValidationError(
                "MULTIPLE_E3_CUMULATIVE_VIEW_MANIFESTS"
            )
        if not manifests:
            return None
        manifest = manifests[0]

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
            knowledge_rows = [
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
                and row["body"].get(
                    "previous_knowledge_state_ref"
                )
                is not None
            ]
            if (
                len(grant_rows) != 1
                or len(knowledge_rows) != 1
            ):
                raise ValidationError(
                    "PARTIAL_E3_CUMULATIVE_AUTHORIZATION",
                    slot,
                )
            grants[slot] = _with_ref_class(
                grant_rows[0]["ref"],
                "CONTENT_OR_PRIOR",
            )
            states[slot] = _with_ref_class(
                knowledge_rows[0]["ref"],
                "CONTENT_OR_PRIOR",
            )

        return StageAuthorizedContext(
            campaign_id=assignments.campaign_id,
            stage_id="E3",
            phase_id="E3-CUMULATIVE",
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
        _accepted_gap_phase_complete(
            self.store,
            pre_cut,
            self.all_stage_lane_slots,
        )

        assignments = StageAssignmentService(
            self.store
        ).prepare_phase_assignments(
            stage_id="E3",
            phase_id="E3-CUMULATIVE",
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
        payload_raw, allowed_rows = (
            build_e3_cumulative_view(
                self.store,
                cut,
            )
        )
        payload_sha = hashlib.sha256(
            payload_raw
        ).hexdigest()
        context_members = {
            "E3_CUMULATIVE_CORPUS_VIEW.json": (
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

        existing = self._existing(
            cut=cut,
            assignments=assignments,
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
                    "E3_CUMULATIVE_E1_E2_CORPUS"
                ),
                "policy_revision": "1",
                "phase": "E3-CUMULATIVE",
                "allowed_fields": {
                    "own_discovery": [
                        "discovery_id",
                        "originating_phase",
                        "originating_lane",
                        "origin_classification",
                        "statement",
                        "claim",
                        "mechanism",
                        "location",
                        "affected_component",
                        "asserted_observable",
                    ],
                    "prior_claim": [
                        "statement",
                        "scope_refs",
                        "violated_invariant_refs",
                        "lifecycle_status",
                        "axis_outcomes",
                    ],
                    "contradiction": [
                        "status",
                        "scope",
                        "claim_revision_digests",
                    ],
                },
                "allowed_kinds": [
                    "own_discovery",
                    "prior_claim",
                    "contradiction",
                ],
                "forbidden_kinds": [
                    "raw_report",
                    "producer_identity",
                    "support_count",
                    "raw_evidence_payload",
                    "unapproved_auxiliary_corpus",
                ],
                "reveal_support_count": False,
                "reveal_filenames": False,
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
                    "view_e3_cumulative_"
                    + payload_sha[:24]
                ),
                "phase_id": (
                    "E3-CUMULATIVE"
                ),
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
                    "E3_OWN_DISCOVERY_SUMMARY",
                    "CUMULATIVE_E1_E2_CORPUS",
                ],
                "forbidden_knowledge_classes": [
                    "RAW_REPORT_PATHS",
                    "PRODUCER_IDENTITY",
                    "SUPPORT_COUNT",
                    "RAW_EVIDENCE_PAYLOADS",
                    "UNAPPROVED_AUXILIARY_CORPUS",
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
                        "BDB_POLICY::E3_CUMULATIVE_APPROVED_VIEW_ONLY"
                    ),
                    "channel_class": (
                        "CUMULATIVE_CORPUS_VIEW"
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
            knowledge = CanonicalObject(
                "knowledge_state",
                {
                    "knowledge_state_id": (
                        "knowledge_E3_CUMULATIVE_"
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
                        "E3_OWN_DISCOVERY_SUMMARY",
                        "CUMULATIVE_E1_E2_CORPUS",
                    ],
                },
            )
            objects.extend(
                [
                    grant,
                    exposure,
                    knowledge,
                ]
            )
            grants[slot] = grant
            states[slot] = knowledge

        head = self.store.head()
        if head is None:
            raise ValidationError(
                "CAMPAIGN_NOT_INITIALIZED"
            )
        seed = hashlib.sha256(
            canonical_bytes(
                {
                    "payload_sha256": payload_sha,
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
                "e3_cumulative_authorization:"
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
                "e3_cumulative_authorization:"
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
            phase_id="E3-CUMULATIVE",
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
    "E3CumulativeAuthorizationService",
    "build_e3_cumulative_view",
]

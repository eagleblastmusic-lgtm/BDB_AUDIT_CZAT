"""E3 positive gap-view authorization.

After E3-X/Y/Z blind results have been accepted and sealed in checkpoints, this
service creates a *positive* coverage/gap projection for fresh E3-GAP attempts.
It does not reveal prior finding corpora, producer identity, support counts or
raw evidence.  Grant and successor KnowledgeState are accepted before package
delivery.

The view is derived only from accepted inventory/coverage authority at one
history cut:
- open / blocked / stale / unassessed obligations;
- explicit unknown / unobserved / unsupported / provisional scope;
- exact materiality and target-scope bindings needed to direct exploration.

It is not a new coverage authority and cannot close or waive obligations.
"""
from __future__ import annotations

from dataclasses import dataclass
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
    PreparedStageAssignment,
    StageAssignmentService,
    StageAuthorizedContext,
    StageIsolationProof,
    StageLaneDefinition,
)


_GAP_SCOPE_STATES = {
    "KNOWN_UNOBSERVED_SCOPE",
    "UNSUPPORTED_SCOPE",
    "PROVISIONAL_SCOPE",
    "UNKNOWN_SCOPE",
    "COLLECTION_FAILED",
    "PARSING_FAILED",
}

_GAP_QUALIFICATION_STATUSES = {
    "UNASSESSED",
    "IN_PROGRESS",
    "BLOCKED",
    "STALE",
}


def _checkpoint_rows(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
    lane_slots: Sequence[str],
) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for row in store.accepted_records(
        "checkpoint",
        cut,
    ):
        body = row["body"]
        if (
            body.get("stage_id") != "E3"
            or body.get("phase_id") != "E3-BLIND"
        ):
            continue
        slot = body.get("lane_slot")
        if slot not in lane_slots:
            continue
        if (
            slot in found
            and found[slot]["ref"]["revision_digest"]
            != row["ref"]["revision_digest"]
        ):
            raise ValidationError(
                "MULTIPLE_E3_BLIND_CHECKPOINTS",
                str(slot),
            )
        found[str(slot)] = row
    missing = [
        slot for slot in lane_slots if slot not in found
    ]
    if missing:
        raise ValidationError(
            "E3_BLIND_CHECKPOINT_REQUIRED",
            ",".join(missing),
        )
    seqs = {
        row["accepted_seq"]
        for row in found.values()
    }
    if len(seqs) != 1:
        raise ValidationError(
            "E3_BLIND_CHECKPOINT_CUT_DIVERGENCE"
        )
    return found


def _qualification_by_obligation(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for row in store.accepted_records(
        "coverage_obligation_qualification",
        cut,
    ):
        ref = row["body"].get(
            "obligation_revision_ref"
        )
        if not isinstance(ref, dict):
            continue
        digest = ref.get("revision_digest")
        if not isinstance(digest, str):
            continue
        prior = mapped.get(digest)
        if prior is not None:
            # Multiple accepted qualification revisions for one immutable
            # obligation are ambiguous unless a separate canonical currentness
            # authority exists. Do not guess.
            raise ValidationError(
                "MULTIPLE_COVERAGE_QUALIFICATIONS_FOR_OBLIGATION",
                digest,
            )
        mapped[digest] = row
    return mapped


def build_e3_positive_gap_view(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
) -> tuple[
    bytes,
    tuple[dict[str, Any], ...],
]:
    """Build a bounded positive view from accepted coverage/scope authority."""
    obligations = tuple(
        store.accepted_records(
            "coverage_obligation",
            cut,
        )
    )
    scope_rows = tuple(
        store.accepted_records(
            "scope_state_record",
            cut,
        )
    )
    if not obligations and not scope_rows:
        raise ValidationError(
            "E3_GAP_AUTHORITY_REQUIRED",
            "No accepted coverage obligations or scope-state records",
        )

    qualifications = _qualification_by_obligation(
        store,
        cut,
    )
    materiality_by_digest = {
        row["ref"]["revision_digest"]: row
        for row in store.accepted_records(
            "materiality_assessment",
            cut,
        )
    }

    gap_obligations: list[dict[str, Any]] = []
    allowed_records: dict[
        tuple[str, str],
        dict[str, Any],
    ] = {}

    for obligation in sorted(
        obligations,
        key=lambda row: row["ref"]["revision_digest"],
    ):
        body = obligation["body"]
        digest = obligation["ref"]["revision_digest"]
        qualification = qualifications.get(digest)
        qualification_status = (
            qualification["body"].get(
                "qualification_status"
            )
            if qualification is not None
            else "UNASSESSED"
        )
        if qualification_status not in (
            _GAP_QUALIFICATION_STATUSES
        ):
            continue

        materiality_ref = body.get(
            "materiality_assessment_ref"
        )
        materiality = None
        if isinstance(materiality_ref, dict):
            materiality = materiality_by_digest.get(
                materiality_ref.get(
                    "revision_digest",
                    "",
                )
            )
        materiality_result = (
            materiality["body"].get("result")
            if materiality is not None
            else "UNKNOWN"
        )

        gap_obligations.append(
            {
                "obligation_revision_ref": (
                    _with_ref_class(
                        obligation["ref"],
                        "CONTENT_OR_PRIOR",
                    )
                ),
                "target_scope_or_surface_ref": (
                    body.get(
                        "target_scope_or_surface_ref"
                    )
                ),
                "scenario_class": body.get(
                    "scenario_class"
                ),
                "invariant_revision_ref": body.get(
                    "invariant_revision_ref"
                ),
                "qualification_status": (
                    qualification_status
                ),
                "substantive_outcome": (
                    qualification["body"].get(
                        "substantive_outcome"
                    )
                    if qualification is not None
                    else None
                ),
                "materiality_result": (
                    materiality_result
                ),
                "required_technique_or_capability_refs": (
                    body.get(
                        "required_technique_or_capability_refs",
                        [],
                    )
                ),
                "falsifier_or_control_requirements": (
                    body.get(
                        "falsifier_or_control_requirements",
                        [],
                    )
                ),
            }
        )
        allowed_records[
            (
                obligation["ref"]["kind"],
                obligation["ref"][
                    "revision_digest"
                ],
            )
        ] = obligation
        if qualification is not None:
            allowed_records[
                (
                    qualification["ref"]["kind"],
                    qualification["ref"][
                        "revision_digest"
                    ],
                )
            ] = qualification
        if materiality is not None:
            allowed_records[
                (
                    materiality["ref"]["kind"],
                    materiality["ref"][
                        "revision_digest"
                    ],
                )
            ] = materiality

    scope_gaps: list[dict[str, Any]] = []
    for row in sorted(
        scope_rows,
        key=lambda item: item["ref"][
            "revision_digest"
        ],
    ):
        body = row["body"]
        state = body.get("state")
        if state not in _GAP_SCOPE_STATES:
            continue
        scope_gaps.append(
            {
                "scope_state_record_ref": _with_ref_class(
                    row["ref"],
                    "CONTENT_OR_PRIOR",
                ),
                "scope_key": body.get("scope_key"),
                "state": state,
                "scope_ref": body.get("scope_ref"),
                "reason_codes": body.get(
                    "reason_codes",
                    [],
                ),
            }
        )
        allowed_records[
            (
                row["ref"]["kind"],
                row["ref"]["revision_digest"],
            )
        ] = row

    if not gap_obligations and not scope_gaps:
        raise ValidationError(
            "E3_NO_POSITIVE_GAPS_AVAILABLE"
        )

    payload = {
        "format": "BDB-E3-POSITIVE-GAP-VIEW-1",
        "phase": "E3-GAP",
        "authority_note": (
            "Projection only; does not close obligations or "
            "change scope authority"
        ),
        "open_or_blocked_obligations": (
            gap_obligations
        ),
        "explicit_scope_gaps": scope_gaps,
    }
    records = tuple(
        allowed_records[key]
        for key in sorted(allowed_records)
    )
    return canonical_bytes(payload), records


class E3PositiveGapAuthorizationService:
    """Authorize fresh E3-GAP attempts after sealed blind checkpoints."""

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
        missing_proofs = [
            definition.lane_slot
            for definition in self.lane_definitions
            if lanes[definition.lane_slot]["body"].get(
                "required_isolation_assurance",
                "DECLARED",
            )
            == "ENFORCED"
            and definition.lane_slot
            not in self.isolation_proofs_by_slot
        ]
        if missing_proofs:
            raise ValidationError(
                "E3_GAP_ENFORCED_ISOLATION_PROOF_REQUIRED",
                ",".join(sorted(missing_proofs)),
            )
        self.coordinator = Coordinator(store)

    def _existing_authorization(
        self,
        *,
        cut: dict[str, Any],
        assignments,
        payload_sha256: str,
        checkpoint_digests: tuple[str, ...],
        context_members: dict[str, bytes],
        context_manifest: dict[str, str],
    ) -> StageAuthorizedContext | None:
        manifests = []
        for row in self.store.accepted_records(
            "view_manifest",
            cut,
        ):
            body = row["body"]
            if (
                body.get("phase_id") != "E3-GAP"
                or body.get("payload_sha256")
                != payload_sha256
            ):
                continue
            observed = tuple(
                sorted(
                    ref["revision_digest"]
                    for ref in body.get(
                        "checkpoint_refs",
                        (),
                    )
                    if isinstance(ref, dict)
                    and isinstance(
                        ref.get(
                            "revision_digest"
                        ),
                        str,
                    )
                )
            )
            if observed == checkpoint_digests:
                manifests.append(row)

        if len(manifests) > 1:
            raise ValidationError(
                "MULTIPLE_E3_GAP_VIEW_MANIFESTS"
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
                    "PARTIAL_E3_GAP_AUTHORIZATION",
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
            phase_id="E3-GAP",
            context_members=context_members,
            context_manifest=context_manifest,
            view_manifest_ref=_with_ref_class(
                manifest["ref"],
                "CONTENT_OR_PRIOR",
            ),
            grant_refs_by_slot=grants,
            knowledge_state_refs_by_slot=states,
            authorization_history_cut=dict(cut),
            assignments=dict(
                assignments.assignments
            ),
            already_authorized=True,
        )

    def authorize(
        self,
    ) -> StageAuthorizedContext:
        pre_assignment_cut, _ = _current_cut(
            self.store
        )
        lane_slots = tuple(
            definition.lane_slot
            for definition in self.lane_definitions
        )
        checkpoints = _checkpoint_rows(
            self.store,
            pre_assignment_cut,
            self.all_stage_lane_slots,
        )

        assignments = StageAssignmentService(
            self.store
        ).prepare_phase_assignments(
            stage_id="E3",
            phase_id="E3-GAP",
            lane_definitions=self.lane_definitions,
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
            build_e3_positive_gap_view(
                self.store,
                cut,
            )
        )
        payload_sha = hashlib.sha256(
            payload_raw
        ).hexdigest()
        context_members = {
            "E3_POSITIVE_GAP_VIEW.json": (
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
        checkpoint_digests = tuple(
            sorted(
                row["ref"]["revision_digest"]
                for row in checkpoints.values()
            )
        )

        existing = self._existing_authorization(
            cut=cut,
            assignments=assignments,
            payload_sha256=payload_sha,
            checkpoint_digests=(
                checkpoint_digests
            ),
            context_members=context_members,
            context_manifest=context_manifest,
        )
        if existing is not None:
            return existing

        policy = CanonicalObject(
            "projection_policy",
            {
                "policy_id": (
                    "E3_POSITIVE_GAP_VIEW"
                ),
                "policy_revision": "1",
                "phase": "E3-GAP",
                "allowed_fields": {
                    "coverage_gap": [
                        "target_scope_or_surface_ref",
                        "scenario_class",
                        "invariant_revision_ref",
                        "qualification_status",
                        "substantive_outcome",
                        "materiality_result",
                        "required_technique_or_capability_refs",
                        "falsifier_or_control_requirements",
                    ],
                    "scope_gap": [
                        "scope_key",
                        "state",
                        "scope_ref",
                        "reason_codes",
                    ],
                },
                "allowed_kinds": [
                    "coverage_gap",
                    "scope_gap",
                ],
                "forbidden_kinds": [
                    "finding_claim",
                    "raw_report",
                    "prior_finding_corpus",
                    "producer_identity",
                    "support_count",
                    "severity_history",
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
        checkpoint_refs = canonical_reference_set(
            [
                _with_ref_class(
                    row["ref"],
                    "CONTENT_OR_PRIOR",
                )
                for row in checkpoints.values()
            ]
        )
        manifest = CanonicalObject(
            "view_manifest",
            {
                "view_id": (
                    "view_e3_gap_"
                    + payload_sha[:24]
                ),
                "phase_id": "E3-GAP",
                "projection_policy_ref": (
                    policy.as_ref(
                        ref_class="CONTENT_OR_PRIOR"
                    ).as_dict()
                ),
                "allowed_artifact_refs": (
                    allowed_refs
                ),
                "checkpoint_refs": checkpoint_refs,
                "payload_manifest": (
                    context_manifest
                ),
                "payload_sha256": payload_sha,
                "allowed_view_classes": [
                    "POSITIVE_COVERAGE_GAP_VIEW"
                ],
                "forbidden_knowledge_classes": [
                    "PRIOR_FINDING_CORPUS",
                    "RAW_REPORT_PATHS",
                    "PRODUCER_IDENTITY",
                    "SUPPORT_COUNT",
                    "SEVERITY_HISTORY",
                ],
            },
        )

        objects: list[CanonicalObject] = [
            policy,
            manifest,
        ]
        grants: dict[
            str, CanonicalObject
        ] = {}
        knowledge: dict[
            str, CanonicalObject
        ] = {}
        for slot, assignment in (
            assignments.assignments.items()
        ):
            attempt = self.store.resolve_accepted(
                assignment.attempt_ref,
                cut,
            )
            initial_knowledge = (
                self.store.resolve_accepted(
                    assignment.knowledge_state_ref,
                    cut,
                )
            )
            isolation = self.store.resolve_accepted(
                initial_knowledge["body"][
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
                        "BDB_POLICY::E3_POSITIVE_GAP_NO_FINDING_CORPUS"
                    ),
                    "channel_class": (
                        "CONTROLLED_POSITIVE_GAP_VIEW"
                    ),
                    "previous_knowledge_state_ref": (
                        _with_ref_class(
                            initial_knowledge["ref"],
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
                            initial_knowledge["ref"],
                            "PRIOR_ACCEPTED_ONLY",
                        )
                    ),
                },
            )
            next_knowledge = CanonicalObject(
                "knowledge_state",
                {
                    "knowledge_state_id": (
                        "knowledge_E3_GAP_"
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
                            initial_knowledge["ref"],
                            "PRIOR_ACCEPTED_ONLY",
                        )
                    ),
                    "known_classes": [
                        "POSITIVE_COVERAGE_GAP_VIEW"
                    ],
                },
            )
            objects.extend(
                [
                    grant,
                    exposure,
                    next_knowledge,
                ]
            )
            grants[slot] = grant
            knowledge[slot] = next_knowledge

        head = self.store.head()
        if head is None:
            raise ValidationError(
                "CAMPAIGN_NOT_INITIALIZED"
            )
        seed = hashlib.sha256(
            canonical_bytes(
                {
                    "payload_sha256": payload_sha,
                    "checkpoint_digests": list(
                        checkpoint_digests
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
                "e3_gap_authorization:" + seed
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
                "e3_gap_authorization:" + seed
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
            phase_id="E3-GAP",
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
                for slot, obj in knowledge.items()
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
    "E3PositiveGapAuthorizationService",
    "build_e3_positive_gap_view",
]
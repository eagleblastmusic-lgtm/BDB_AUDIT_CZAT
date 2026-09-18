"""Controlled E2 reveal authorization.

E2 blind outputs must already be sealed by accepted Checkpoints.  This module
then creates a deterministic positive claim-card view of accepted E1 results,
prepares fresh E2-REVEAL assignments, and accepts the ViewManifest, per-attempt
GrantBody, PotentialExposureRecord and successor KnowledgeState *before* any
context bytes are eligible for package delivery.

The revealed payload is positive/allowlisted.  It intentionally excludes raw
report paths, producer identity, support count, severity history and arbitrary
nested evidence payloads.
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
from .assignments import _command_id, _current_cut, _external_ref, _ref
from .inbox import _same_ref, _with_ref_class
from .manual_stage import (
    PreparedStageAssignment,
    StageAssignmentService,
    StageLaneDefinition,
)


_SAFE_CLAIM_FIELDS = (
    "finding_id",
    "statement",
    "claim",
    "mechanism",
    "location",
    "affected_component",
    "asserted_observable",
    "scope",
)


@dataclass(frozen=True)
class E2RevealAuthorization:
    campaign_id: str
    stage_id: str
    phase_id: str
    context_members: dict[str, bytes]
    context_manifest: dict[str, str]
    view_manifest_ref: dict[str, Any]
    grant_refs_by_slot: dict[str, dict[str, Any]]
    knowledge_state_refs_by_slot: dict[str, dict[str, Any]]
    authorization_history_cut: dict[str, Any]
    assignments: dict[str, PreparedStageAssignment]
    already_authorized: bool


def _safe_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list) and all(
        item is None or isinstance(item, (str, int, float, bool))
        for item in value
    ):
        return list(value)
    return None


def _claim_cards(
    records: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    cards: list[dict[str, Any]] = []
    for record in sorted(
        records,
        key=lambda row: row["ref"]["revision_digest"],
    ):
        findings = record["body"].get("findings", [])
        if not isinstance(findings, list):
            raise ValidationError("INVALID_FINDING_STRUCTURE", "E1")
        for index, finding in enumerate(findings):
            if not isinstance(finding, dict):
                raise ValidationError("INVALID_FINDING_STRUCTURE", "E1")
            fingerprint = hashlib.sha256(
                canonical_bytes(finding)
            ).hexdigest()
            card: dict[str, Any] = {
                "opaque_claim_view_id": hashlib.sha256(
                    canonical_bytes(
                        {
                            "result_digest": record["ref"]["revision_digest"],
                            "finding_index": index,
                            "finding_fingerprint": fingerprint,
                        }
                    )
                ).hexdigest(),
            }
            for field in _SAFE_CLAIM_FIELDS:
                if field not in finding:
                    continue
                value = _safe_scalar(finding[field])
                if value is not None:
                    card[field] = value
            cards.append(card)
    return tuple(
        sorted(
            cards,
            key=lambda item: item["opaque_claim_view_id"],
        )
    )


def build_e2_claim_view(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
) -> tuple[bytes, tuple[dict[str, Any], ...]]:
    """Build exact positive bytes from accepted E1 result proposals only."""
    records = tuple(
        row
        for row in store.accepted_records("bdb_audit_lane_result", cut)
        if row["body"].get("stage_id") == "E1"
    )
    if not records:
        raise ValidationError("E1_RESULT_CORPUS_REQUIRED")
    cards = _claim_cards(records)
    payload = {
        "format": "BDB-E2-POSITIVE-CLAIM-VIEW-1",
        "source_stage": "E1",
        "reveal_class": "MINIMAL_CLAIM_CARDS_NO_PROVENANCE",
        "claims": list(cards),
    }
    return canonical_bytes(payload), records


def _checkpoint_rows(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
    lane_slots: Sequence[str],
) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for row in store.accepted_records("checkpoint", cut):
        body = row["body"]
        if body.get("stage_id") != "E2" or body.get("phase_id") != "E2-BLIND":
            continue
        slot = body.get("lane_slot")
        if slot not in lane_slots:
            continue
        if slot in found and found[slot]["ref"]["revision_digest"] != row["ref"]["revision_digest"]:
            raise ValidationError("MULTIPLE_E2_BLIND_CHECKPOINTS", str(slot))
        found[str(slot)] = row
    missing = [slot for slot in lane_slots if slot not in found]
    if missing:
        raise ValidationError(
            "E2_BLIND_CHECKPOINT_REQUIRED",
            ",".join(missing),
        )
    seqs = {row["accepted_seq"] for row in found.values()}
    if len(seqs) != 1:
        raise ValidationError("E2_BLIND_CHECKPOINT_CUT_DIVERGENCE")
    return found


def _context_manifest(
    members: Mapping[str, bytes],
) -> dict[str, str]:
    return {
        name: hashlib.sha256(raw).hexdigest()
        for name, raw in sorted(members.items())
    }


class E2ControlledRevealService:
    """Authorize deterministic minimal E1 claim-card reveal to fresh E2 attempts."""

    def __init__(
        self,
        store: TransactionalHistoryStore,
        *,
        lane_definitions: Sequence[StageLaneDefinition],
        all_stage_lane_slots: Sequence[str],
        executor_profile: str,
        model: str,
    ):
        self.store = store
        self.lane_definitions = tuple(lane_definitions)
        self.all_stage_lane_slots = tuple(all_stage_lane_slots)
        self.executor_profile = executor_profile
        self.model = model
        self.coordinator = Coordinator(store)

    def _existing_authorization(
        self,
        *,
        cut: dict[str, Any],
        assignments,
        payload_sha256: str,
        checkpoint_digests: tuple[str, ...],
        context_manifest: dict[str, str],
        context_members: dict[str, bytes],
    ) -> E2RevealAuthorization | None:
        manifests = [
            row
            for row in self.store.accepted_records("view_manifest", cut)
            if row["body"].get("phase_id") == "E2-REVEAL"
            and row["body"].get("payload_sha256") == payload_sha256
            and tuple(row["body"].get("checkpoint_digests", ()))
            == checkpoint_digests
        ]
        if len(manifests) > 1:
            raise ValidationError("MULTIPLE_E2_REVEAL_VIEW_MANIFESTS")
        if not manifests:
            return None
        manifest = manifests[0]

        grant_refs: dict[str, dict[str, Any]] = {}
        knowledge_refs: dict[str, dict[str, Any]] = {}
        for slot, assignment in assignments.assignments.items():
            grants = [
                row
                for row in self.store.accepted_records("grant_body", cut)
                if _same_ref(
                    row["body"].get("attempt_ref"),
                    assignment.attempt_ref,
                )
                and _same_ref(
                    row["body"].get("view_manifest_ref"),
                    manifest["ref"],
                )
            ]
            if len(grants) != 1:
                raise ValidationError(
                    "PARTIAL_E2_REVEAL_AUTHORIZATION",
                    f"{slot}: grants={len(grants)}",
                )
            grant = grants[0]
            states = [
                row
                for row in self.store.accepted_records("knowledge_state", cut)
                if _same_ref(
                    row["body"].get("attempt_ref"),
                    assignment.attempt_ref,
                )
                and any(
                    _same_ref(ref, manifest["ref"])
                    for ref in row["body"].get("allowed_view_refs", [])
                    if isinstance(ref, dict)
                )
                and row["body"].get("previous_knowledge_state_ref") is not None
            ]
            if len(states) != 1:
                raise ValidationError(
                    "PARTIAL_E2_REVEAL_AUTHORIZATION",
                    f"{slot}: knowledge_states={len(states)}",
                )
            grant_refs[slot] = _with_ref_class(
                grant["ref"], "CONTENT_OR_PRIOR"
            )
            knowledge_refs[slot] = _with_ref_class(
                states[0]["ref"], "CONTENT_OR_PRIOR"
            )

        return E2RevealAuthorization(
            campaign_id=assignments.campaign_id,
            stage_id="E2",
            phase_id="E2-REVEAL",
            context_members=context_members,
            context_manifest=context_manifest,
            view_manifest_ref=_with_ref_class(
                manifest["ref"], "CONTENT_OR_PRIOR"
            ),
            grant_refs_by_slot=grant_refs,
            knowledge_state_refs_by_slot=knowledge_refs,
            authorization_history_cut=dict(cut),
            assignments=dict(assignments.assignments),
            already_authorized=True,
        )

    def authorize(self) -> E2RevealAuthorization:
        pre_assignment_cut, _ = _current_cut(self.store)
        lane_slots = tuple(
            definition.lane_slot
            for definition in self.lane_definitions
        )
        checkpoints = _checkpoint_rows(
            self.store,
            pre_assignment_cut,
            lane_slots,
        )

        assignments = StageAssignmentService(
            self.store
        ).prepare_phase_assignments(
            stage_id="E2",
            phase_id="E2-REVEAL",
            lane_definitions=self.lane_definitions,
            all_stage_lane_slots=self.all_stage_lane_slots,
            executor_profile=self.executor_profile,
            model=self.model,
        )

        cut, prior_commit = _current_cut(self.store)
        payload_raw, e1_results = build_e2_claim_view(
            self.store,
            cut,
        )
        payload_sha = hashlib.sha256(payload_raw).hexdigest()
        context_members = {
            "E1_CLAIM_VIEW.json": payload_raw,
        }
        context_manifest = _context_manifest(
            context_members
        )
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
            checkpoint_digests=checkpoint_digests,
            context_manifest=context_manifest,
            context_members=context_members,
        )
        if existing is not None:
            return existing

        policy = CanonicalObject(
            "projection_policy",
            {
                "policy_id": "E2_MINIMAL_CLAIM_CARD_REVEAL",
                "policy_revision": "1",
                "phase": "E2-REVEAL",
                "allowed_fields": {
                    "claim_card": list(_SAFE_CLAIM_FIELDS)
                    + ["opaque_claim_view_id"],
                },
                "allowed_kinds": ["claim_card"],
                "forbidden_kinds": [
                    "raw_report",
                    "producer_identity",
                    "support_count",
                    "severity_history",
                ],
                "reveal_support_count": False,
                "reveal_filenames": False,
            },
        )
        result_refs = canonical_reference_set(
            [
                _with_ref_class(
                    row["ref"], "CONTENT_OR_PRIOR"
                )
                for row in e1_results
            ]
        )
        checkpoint_refs = canonical_reference_set(
            [
                _with_ref_class(
                    row["ref"], "CONTENT_OR_PRIOR"
                )
                for row in checkpoints.values()
            ]
        )
        manifest = CanonicalObject(
            "view_manifest",
            {
                "view_id": (
                    "view_e2_reveal_"
                    + payload_sha[:24]
                ),
                "phase_id": "E2-REVEAL",
                "projection_policy_ref": policy.as_ref(
                    ref_class="CONTENT_OR_PRIOR"
                ).as_dict(),
                "allowed_artifact_refs": result_refs,
                "checkpoint_refs": checkpoint_refs,
                "payload_manifest": context_manifest,
                "payload_sha256": payload_sha,
                "allowed_view_classes": [
                    "MINIMAL_CLAIM_CARD"
                ],
                "forbidden_knowledge_classes": [
                    "PRODUCER_IDENTITY",
                    "SUPPORT_COUNT",
                    "SEVERITY_HISTORY",
                    "RAW_REPORT_PATHS",
                    "RAW_EVIDENCE_PAYLOADS",
                ],
            },
        )

        objects: list[CanonicalObject] = [
            policy,
            manifest,
        ]
        grants: dict[str, CanonicalObject] = {}
        new_knowledge: dict[str, CanonicalObject] = {}

        for slot, assignment in assignments.assignments.items():
            assignment_record = self.store.resolve_accepted(
                assignment.assignment_ref,
                cut,
            )
            attempt_record = self.store.resolve_accepted(
                assignment.attempt_ref,
                cut,
            )
            initial_knowledge = self.store.resolve_accepted(
                assignment.knowledge_state_ref,
                cut,
            )
            isolation = self.store.resolve_accepted(
                initial_knowledge["body"][
                    "isolation_qualification_ref"
                ],
                cut,
            )
            delivery_profile_ref = attempt_record["body"][
                "delivery_profile_ref"
            ]

            grant = CanonicalObject(
                "grant_body",
                {
                    "attempt_ref": _with_ref_class(
                        attempt_record["ref"],
                        "CONTENT_OR_PRIOR",
                    ),
                    "grant_input_history_cut": cut,
                    "view_manifest_ref": manifest.as_ref(
                        ref_class="CONTENT_OR_PRIOR"
                    ).as_dict(),
                    "delivery_profile_ref": delivery_profile_ref,
                    "forbidden_knowledge_policy_ref": (
                        "BDB_POLICY::E2_MINIMAL_CLAIM_VIEW_NO_PROVENANCE"
                    ),
                    "channel_class": "CONTROLLED_POSITIVE_VIEW",
                    "previous_knowledge_state_ref": _with_ref_class(
                        initial_knowledge["ref"],
                        "PRIOR_ACCEPTED_ONLY",
                    ),
                },
            )
            exposure = CanonicalObject(
                "potential_exposure_record",
                {
                    "attempt_ref": _with_ref_class(
                        attempt_record["ref"],
                        "CONTENT_OR_PRIOR",
                    ),
                    "grant_ref": grant.as_ref(
                        ref_class="CONTENT_OR_PRIOR"
                    ).as_dict(),
                    "view_manifest_ref": manifest.as_ref(
                        ref_class="CONTENT_OR_PRIOR"
                    ).as_dict(),
                    "exposure_input_history_cut": cut,
                    "previous_knowledge_state_ref": _with_ref_class(
                        initial_knowledge["ref"],
                        "PRIOR_ACCEPTED_ONLY",
                    ),
                },
            )
            knowledge = CanonicalObject(
                "knowledge_state",
                {
                    "knowledge_state_id": (
                        "knowledge_E2_REVEAL_"
                        + slot
                        + "_"
                        + payload_sha[:12]
                    ),
                    "attempt_ref": _with_ref_class(
                        attempt_record["ref"],
                        "CONTENT_OR_PRIOR",
                    ),
                    "basis_history_cut": cut,
                    "isolation_qualification_ref": _with_ref_class(
                        isolation["ref"],
                        "CONTENT_OR_PRIOR",
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
                    "previous_knowledge_state_ref": _with_ref_class(
                        initial_knowledge["ref"],
                        "PRIOR_ACCEPTED_ONLY",
                    ),
                    "known_classes": [
                        "E1_MINIMAL_CLAIM_CARD_VIEW"
                    ],
                },
            )
            objects.extend(
                [grant, exposure, knowledge]
            )
            grants[slot] = grant
            new_knowledge[slot] = knowledge

        head = self.store.head()
        if head is None:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        seed = hashlib.sha256(
            canonical_bytes(
                {
                    "payload_sha256": payload_sha,
                    "checkpoint_digests": checkpoint_digests,
                    "assignment_digests": sorted(
                        assignment.assignment_ref[
                            "revision_digest"
                        ]
                        for assignment in assignments.assignments.values()
                    ),
                }
            )
        ).hexdigest()
        command = CommandEnvelope(
            command_id=_command_id(
                "e2_reveal_authorization:" + seed
            ),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get(
                "actor_ref", "installation-owner"
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
                    "governing_spec_refs", ()
                )
            ),
            idempotency_scope=(
                "e2_reveal_authorization:" + seed
            ),
            campaign_ref=head.campaign_id,
        )
        accepted = self.coordinator.accept(
            command,
            immutable_objects=objects,
            expected_head=head,
        )
        authorization_cut = HistoryCut.accepted(
            accepted.head,
            accepted.commit.governing_policy_ref,
            accepted.commit.governing_spec_refs,
        ).as_dict()

        return E2RevealAuthorization(
            campaign_id=assignments.campaign_id,
            stage_id="E2",
            phase_id="E2-REVEAL",
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
                for slot, obj in new_knowledge.items()
            },
            authorization_history_cut=authorization_cut,
            assignments=dict(assignments.assignments),
            already_authorized=False,
        )


__all__ = [
    "E2RevealAuthorization",
    "E2ControlledRevealService",
    "build_e2_claim_view",
]

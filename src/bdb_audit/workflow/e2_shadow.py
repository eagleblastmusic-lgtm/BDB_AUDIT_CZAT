"""Independent E2 shadow-adjudicator authorization.

After the main E2 per-claim synthesis is accepted, this service creates a small
positive view for a fresh shadow attempt.  The view is deliberately bounded to
canonical claim/axis/decision state plus checkpoint provenance.  It does not
replay full raw reports or popularity metadata.

The shadow is a challenger, not a second truth authority.  Its result is an
accepted proposal that a later finalizer may translate into contradiction
obligations; it cannot overwrite the main adjudication decision.
"""
from __future__ import annotations

import hashlib
from typing import Any, Sequence

from ..coordinator import Coordinator
from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, CommandEnvelope, HistoryCut
from ..history.store import TransactionalHistoryStore
from .assignments import _command_id, _current_cut, _external_ref
from .inbox import _same_ref, _with_ref_class
from .manual_stage import (
    StageAssignmentService,
    StageAuthorizedContext,
    StageLaneDefinition,
)


def _main_adjudicator_ref() -> dict[str, Any]:
    return _external_ref(
        "actor_or_authority_ref",
        "trusted_coordinator_e2_main",
        "CONTENT_OR_PRIOR",
    )


def _main_decisions(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    expected_adjudicator = _main_adjudicator_ref()
    rows = tuple(
        row
        for row in store.accepted_records(
            "finding_adjudication_decision",
            cut,
        )
        if _same_ref(
            row["body"].get("adjudicator_ref"),
            expected_adjudicator,
        )
    )
    if not rows:
        raise ValidationError("E2_MAIN_SYNTHESIS_REQUIRED")
    return tuple(
        sorted(
            rows,
            key=lambda row: row["ref"]["revision_digest"],
        )
    )


def build_e2_shadow_view(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
) -> tuple[bytes, tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    decisions = _main_decisions(store, cut)
    checkpoints = tuple(
        sorted(
            (
                row
                for row in store.accepted_records(
                    "checkpoint",
                    cut,
                )
                if row["body"].get("stage_id") == "E2"
                and row["body"].get("phase_id") == "E2-BLIND"
            ),
            key=lambda row: row["ref"]["revision_digest"],
        )
    )
    if not checkpoints:
        raise ValidationError("E2_BLIND_CHECKPOINT_REQUIRED")

    sealed_discovery_digests = {
        ref["revision_digest"]
        for checkpoint in checkpoints
        for ref in checkpoint["body"].get(
            "sealed_output_refs",
            [],
        )
        if isinstance(ref, dict)
        and ref.get("kind") == "discovery_record"
    }

    claims = []
    for decision in decisions:
        body = decision["body"]
        claim = store.resolve_accepted(
            body["claim_revision_ref"],
            cut,
        )
        axes = {}
        axis_fields = {
            "MECHANISM": "mechanism_assessment_ref",
            "REACHABILITY": "reachability_assessment_ref",
            "IMPACT": "impact_assessment_ref",
            "SEVERITY": "severity_assessment_ref",
        }
        for axis, field in axis_fields.items():
            axis_record = store.resolve_accepted(
                body[field],
                cut,
            )
            axes[axis] = {
                "epistemic_outcome": axis_record[
                    "body"
                ].get("epistemic_outcome"),
                "method": axis_record["body"].get(
                    "method"
                ),
                "evidence_qualification_count": len(
                    axis_record["body"].get(
                        "evidence_qualification_refs",
                        [],
                    )
                ),
            }

        discovery_refs = [
            dict(ref)
            for ref in claim["body"].get(
                "discovery_relation_refs",
                [],
            )
            if isinstance(ref, dict)
        ]
        checkpointed = bool(discovery_refs) and all(
            ref.get("revision_digest")
            in sealed_discovery_digests
            for ref in discovery_refs
        )
        claims.append(
            {
                "claim_revision_ref": _with_ref_class(
                    claim["ref"],
                    "CONTENT_OR_PRIOR",
                ),
                "main_decision_ref": _with_ref_class(
                    decision["ref"],
                    "CONTENT_OR_PRIOR",
                ),
                "statement": claim["body"].get(
                    "statement",
                    "",
                ),
                "scope_refs": claim["body"].get(
                    "scope_refs",
                    [],
                ),
                "lifecycle_status": body.get(
                    "lifecycle_status",
                ),
                "axes": axes,
                "discovery_relation_refs": discovery_refs,
                "all_discovery_relations_sealed_pre_reveal": checkpointed,
                "decision_evidence_qualification_count": len(
                    body.get(
                        "evidence_qualification_refs",
                        [],
                    )
                ),
            }
        )

    payload = {
        "format": "BDB-E2-SHADOW-VIEW-1",
        "phase": "E2-SHADOW",
        "checker_scope": [
            "OVER_MERGING",
            "UNDER_MERGING",
            "SEVERITY_INFLATION",
            "FALSE_DISMISSAL",
            "ORIGIN_MISCLASSIFICATION",
            "EVIDENCE_OVERSTATING",
            "PREVIOUS_FALSE_NEGATIVE_MISCLASSIFICATION",
        ],
        "claims": claims,
    }
    return canonical_bytes(payload), decisions, checkpoints


class E2ShadowAuthorizationService:
    """Grant a bounded canonical E2 view to one fresh shadow attempt."""

    def __init__(
        self,
        store: TransactionalHistoryStore,
        *,
        lane_definition: StageLaneDefinition,
        all_stage_lane_slots: Sequence[str],
        executor_profile: str,
        model: str,
    ):
        self.store = store
        self.lane_definition = lane_definition
        self.all_stage_lane_slots = tuple(
            all_stage_lane_slots
        )
        self.executor_profile = executor_profile
        self.model = model
        self.coordinator = Coordinator(store)

    def authorize(self) -> StageAuthorizedContext:
        assignments = StageAssignmentService(
            self.store
        ).prepare_phase_assignments(
            stage_id="E2",
            phase_id="E2-SHADOW",
            lane_definitions=(self.lane_definition,),
            all_stage_lane_slots=self.all_stage_lane_slots,
            executor_profile=self.executor_profile,
            model=self.model,
        )

        cut, prior_commit = _current_cut(self.store)
        payload_raw, decisions, checkpoints = (
            build_e2_shadow_view(
                self.store,
                cut,
            )
        )
        payload_sha = hashlib.sha256(
            payload_raw
        ).hexdigest()
        context_members = {
            "E2_MAIN_ADJUDICATION_VIEW.json": (
                payload_raw
            )
        }
        context_manifest = {
            name: hashlib.sha256(raw).hexdigest()
            for name, raw in context_members.items()
        }

        manifests = [
            row
            for row in self.store.accepted_records(
                "view_manifest",
                cut,
            )
            if row["body"].get("phase_id")
            == "E2-SHADOW"
            and row["body"].get("payload_sha256")
            == payload_sha
        ]
        if len(manifests) > 1:
            raise ValidationError(
                "MULTIPLE_E2_SHADOW_VIEW_MANIFESTS"
            )
        if manifests:
            manifest = manifests[0]
            grant_refs: dict[str, dict[str, Any]] = {}
            knowledge_refs: dict[
                str, dict[str, Any]
            ] = {}
            for slot, assignment in (
                assignments.assignments.items()
            ):
                grants = [
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
                states = [
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
                if len(grants) != 1 or len(states) != 1:
                    raise ValidationError(
                        "PARTIAL_E2_SHADOW_AUTHORIZATION",
                        slot,
                    )
                grant_refs[slot] = (
                    _with_ref_class(
                        grants[0]["ref"],
                        "CONTENT_OR_PRIOR",
                    )
                )
                knowledge_refs[slot] = (
                    _with_ref_class(
                        states[0]["ref"],
                        "CONTENT_OR_PRIOR",
                    )
                )

            return StageAuthorizedContext(
                campaign_id=assignments.campaign_id,
                stage_id="E2",
                phase_id="E2-SHADOW",
                context_members=context_members,
                context_manifest=context_manifest,
                view_manifest_ref=_with_ref_class(
                    manifest["ref"],
                    "CONTENT_OR_PRIOR",
                ),
                grant_refs_by_slot=grant_refs,
                knowledge_state_refs_by_slot=knowledge_refs,
                authorization_history_cut=dict(cut),
                assignments=dict(
                    assignments.assignments
                ),
                already_authorized=True,
            )

        policy = CanonicalObject(
            "projection_policy",
            {
                "policy_id": (
                    "E2_INDEPENDENT_SHADOW_VIEW"
                ),
                "policy_revision": "1",
                "phase": "E2-SHADOW",
                "allowed_fields": {
                    "shadow_claim": [
                        "claim_revision_ref",
                        "main_decision_ref",
                        "statement",
                        "scope_refs",
                        "lifecycle_status",
                        "axes",
                        "discovery_relation_refs",
                        "all_discovery_relations_sealed_pre_reveal",
                        "decision_evidence_qualification_count",
                    ]
                },
                "allowed_kinds": [
                    "shadow_claim"
                ],
                "forbidden_kinds": [
                    "raw_report",
                    "producer_identity",
                    "support_count",
                    "prior_popularity",
                ],
                "reveal_support_count": False,
                "reveal_filenames": False,
            },
        )
        allowed_refs = canonical_reference_set(
            [
                *[
                    _with_ref_class(
                        row["ref"],
                        "CONTENT_OR_PRIOR",
                    )
                    for row in decisions
                ],
                *[
                    _with_ref_class(
                        row["ref"],
                        "CONTENT_OR_PRIOR",
                    )
                    for row in checkpoints
                ],
            ]
        )
        manifest = CanonicalObject(
            "view_manifest",
            {
                "view_id": (
                    "view_e2_shadow_"
                    + payload_sha[:24]
                ),
                "phase_id": "E2-SHADOW",
                "projection_policy_ref": (
                    policy.as_ref(
                        ref_class="CONTENT_OR_PRIOR"
                    ).as_dict()
                ),
                "allowed_artifact_refs": allowed_refs,
                "payload_manifest": context_manifest,
                "payload_sha256": payload_sha,
                "allowed_view_classes": [
                    "E2_MAIN_ADJUDICATION_SHADOW_VIEW"
                ],
                "forbidden_knowledge_classes": [
                    "RAW_REPORT_PATHS",
                    "PRODUCER_IDENTITY",
                    "SUPPORT_COUNT",
                    "PRIOR_POPULARITY",
                ],
            },
        )

        objects: list[CanonicalObject] = [
            policy,
            manifest,
        ]
        grants: dict[str, CanonicalObject] = {}
        knowledge: dict[str, CanonicalObject] = {}

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
                        "BDB_POLICY::E2_SHADOW_BOUNDED_VIEW"
                    ),
                    "channel_class": (
                        "CONTROLLED_SHADOW_VIEW"
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
                    "exposure_input_history_cut": cut,
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
                        "knowledge_E2_SHADOW_"
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
                        "E2_MAIN_ADJUDICATION_SHADOW_VIEW"
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
                "e2_shadow_authorization:" + seed
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
                "e2_shadow_authorization:" + seed
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
            stage_id="E2",
            phase_id="E2-SHADOW",
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
            authorization_history_cut=accepted_cut,
            assignments=dict(
                assignments.assignments
            ),
            already_authorized=False,
        )


__all__ = [
    "E2ShadowAuthorizationService",
    "build_e2_shadow_view",
]

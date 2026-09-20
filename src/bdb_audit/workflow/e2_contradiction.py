"""Grant-bound E2 contradiction-protocol view.

This phase runs only after an independent E2 shadow result has been accepted and
materialized as canonical ContradictionRevision objects.  The external
adjudicator receives a positive, bounded view of those exact contradiction
cases.  Raw reports, popularity/support counts and unrestricted resolver access
are not delivered.

The external result remains a proposal.  A later trusted coordinator service
validates exact case coverage, allowed basis refs and resolution enums before
accepting ContradictionResolutionDecision objects.
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
    StageLaneDefinition,
)


def _evidence_summary(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
    ref: Mapping[str, Any],
) -> dict[str, Any]:
    record = store.resolve_accepted(dict(ref), cut)
    body = record["body"]
    return {
        "evidence_qualification_ref": _with_ref_class(
            record["ref"],
            "CONTENT_OR_PRIOR",
        ),
        "result": body.get("result"),
        "reason_codes": body.get("reason_codes", []),
        "observation_count": len(
            body.get("observation_refs", [])
        ),
        "controls_count": len(
            body.get("controls_refs", [])
        ),
    }


def build_e2_contradiction_view(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
    contradiction_refs: Sequence[Mapping[str, Any]],
) -> tuple[
    bytes,
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
]:
    """Build an exact bounded view and return its accepted artifact closure."""
    if not contradiction_refs:
        raise ValidationError(
            "E2_CONTRADICTION_CASE_REQUIRED"
        )

    contradictions: list[dict[str, Any]] = []
    allowed_records: dict[
        tuple[str, str], dict[str, Any]
    ] = {}

    for supplied_ref in contradiction_refs:
        row = store.resolve_accepted(
            dict(supplied_ref),
            cut,
        )
        if row["ref"]["kind"] != "contradiction_revision":
            raise ValidationError(
                "E2_CONTRADICTION_REF_KIND_INVALID"
            )
        body = row["body"]
        if body.get("status") not in {
            "OPEN",
            "TESTING",
            "REOPENED",
        }:
            raise ValidationError(
                "E2_CONTRADICTION_CASE_NOT_OPEN",
                body.get("status", ""),
            )
        key = (
            row["ref"]["kind"],
            row["ref"]["revision_digest"],
        )
        allowed_records[key] = row

        claims = []
        for claim_ref in body.get(
            "claim_revision_refs",
            [],
        ):
            claim = store.resolve_accepted(
                claim_ref,
                cut,
            )
            allowed_records[
                (
                    claim["ref"]["kind"],
                    claim["ref"]["revision_digest"],
                )
            ] = claim
            claims.append(
                {
                    "claim_revision_ref": _with_ref_class(
                        claim["ref"],
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
                    "violated_invariant_refs": (
                        claim["body"].get(
                            "violated_invariant_refs",
                            [],
                        )
                    ),
                }
            )

        supporting = []
        for evidence_ref in body.get(
            "supporting_evidence_qualification_refs",
            [],
        ):
            evidence = store.resolve_accepted(
                evidence_ref,
                cut,
            )
            allowed_records[
                (
                    evidence["ref"]["kind"],
                    evidence["ref"][
                        "revision_digest"
                    ],
                )
            ] = evidence
            supporting.append(
                _evidence_summary(
                    store,
                    cut,
                    evidence_ref,
                )
            )

        opposing = []
        for evidence_ref in body.get(
            "opposing_evidence_qualification_refs",
            [],
        ):
            evidence = store.resolve_accepted(
                evidence_ref,
                cut,
            )
            allowed_records[
                (
                    evidence["ref"]["kind"],
                    evidence["ref"][
                        "revision_digest"
                    ],
                )
            ] = evidence
            opposing.append(
                _evidence_summary(
                    store,
                    cut,
                    evidence_ref,
                )
            )

        contradictions.append(
            {
                "contradiction_revision_ref": (
                    _with_ref_class(
                        row["ref"],
                        "CONTENT_OR_PRIOR",
                    )
                ),
                "contradiction_id": body.get(
                    "contradiction_id"
                ),
                "contradiction_revision": body.get(
                    "contradiction_revision"
                ),
                "status": body.get("status"),
                "scope": body.get("scope", {}),
                "positions": body.get(
                    "positions",
                    [],
                ),
                "claims": claims,
                "supporting_evidence": supporting,
                "opposing_evidence": opposing,
                "failure_assumption_differences": (
                    body.get(
                        "failure_assumption_differences",
                        [],
                    )
                ),
                "environment_input_model_differences": (
                    body.get(
                        "environment_input_model_differences",
                        [],
                    )
                ),
                "required_falsifier": body.get(
                    "required_falsifier"
                ),
            }
        )

    contradictions.sort(
        key=lambda item: item[
            "contradiction_revision_ref"
        ]["revision_digest"]
    )
    payload = {
        "format": (
            "BDB-E2-CONTRADICTION-PROTOCOL-VIEW-1"
        ),
        "phase": "E2-CONTRADICTION",
        "truth_rule": (
            "NO_MAJORITY_VOTE_AND_NO_SUPPORT_COUNT_TRUTH"
        ),
        "allowed_resolution_kinds": [
            "REFUTED",
            "SCOPES_SEPARATED",
            "HARNESS_INVALIDATED",
            "CONTRACT_CHANGED",
            "BLOCKED",
        ],
        "allowed_resulting_statuses": [
            "RESOLVED_SCOPED",
            "RESOLVED_FULL",
            "BLOCKED",
        ],
        "contradictions": contradictions,
    }
    records = tuple(
        allowed_records[key]
        for key in sorted(allowed_records)
    )
    return (
        canonical_bytes(payload),
        tuple(contradictions),
        records,
    )


class E2ContradictionAuthorizationService:
    """Authorize one fresh E2 contradiction adjudication attempt."""

    def __init__(
        self,
        store: TransactionalHistoryStore,
        *,
        contradiction_refs: Sequence[
            Mapping[str, Any]
        ],
        lane_definition: StageLaneDefinition,
        all_stage_lane_slots: Sequence[str],
        executor_profile: str,
        model: str,
    ):
        self.store = store
        self.contradiction_refs = tuple(
            dict(ref)
            for ref in contradiction_refs
        )
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
            phase_id="E2-CONTRADICTION",
            lane_definitions=(self.lane_definition,),
            all_stage_lane_slots=self.all_stage_lane_slots,
            executor_profile=self.executor_profile,
            model=self.model,
        )

        cut, prior_commit = _current_cut(
            self.store
        )
        payload_raw, _, allowed_records = (
            build_e2_contradiction_view(
                self.store,
                cut,
                self.contradiction_refs,
            )
        )
        payload_sha = hashlib.sha256(
            payload_raw
        ).hexdigest()
        context_members = {
            "E2_CONTRADICTION_CASES.json": (
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
            == "E2-CONTRADICTION"
            and row["body"].get(
                "payload_sha256"
            )
            == payload_sha
        ]
        if len(manifests) > 1:
            raise ValidationError(
                "MULTIPLE_E2_CONTRADICTION_VIEW_MANIFESTS"
            )
        if manifests:
            manifest = manifests[0]
            grant_refs: dict[
                str, dict[str, Any]
            ] = {}
            knowledge_refs: dict[
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
                    and row["body"].get(
                        "previous_knowledge_state_ref"
                    )
                    is not None
                ]
                if (
                    len(grant_rows) != 1
                    or len(state_rows) != 1
                ):
                    raise ValidationError(
                        "PARTIAL_E2_CONTRADICTION_AUTHORIZATION",
                        slot,
                    )
                grant_refs[slot] = _with_ref_class(
                    grant_rows[0]["ref"],
                    "CONTENT_OR_PRIOR",
                )
                knowledge_refs[slot] = (
                    _with_ref_class(
                        state_rows[0]["ref"],
                        "CONTENT_OR_PRIOR",
                    )
                )
            return StageAuthorizedContext(
                campaign_id=assignments.campaign_id,
                stage_id="E2",
                phase_id="E2-CONTRADICTION",
                context_members=context_members,
                context_manifest=context_manifest,
                view_manifest_ref=_with_ref_class(
                    manifest["ref"],
                    "CONTENT_OR_PRIOR",
                ),
                grant_refs_by_slot=grant_refs,
                knowledge_state_refs_by_slot=(
                    knowledge_refs
                ),
                authorization_history_cut=dict(
                    cut
                ),
                assignments=dict(
                    assignments.assignments
                ),
                already_authorized=True,
            )

        policy = CanonicalObject(
            "projection_policy",
            {
                "policy_id": (
                    "E2_CONTRADICTION_PROTOCOL_VIEW"
                ),
                "policy_revision": "1",
                "phase": "E2-CONTRADICTION",
                "allowed_fields": {
                    "contradiction_case": [
                        "contradiction_revision_ref",
                        "scope",
                        "positions",
                        "claims",
                        "supporting_evidence",
                        "opposing_evidence",
                        "failure_assumption_differences",
                        "environment_input_model_differences",
                        "required_falsifier",
                    ]
                },
                "allowed_kinds": [
                    "contradiction_case"
                ],
                "forbidden_kinds": [
                    "raw_report",
                    "producer_identity",
                    "support_count",
                    "prior_popularity",
                    "unapproved_resolver_target",
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
                for row in allowed_records
            ]
        )
        manifest = CanonicalObject(
            "view_manifest",
            {
                "view_id": (
                    "view_e2_contradiction_"
                    + payload_sha[:24]
                ),
                "phase_id": (
                    "E2-CONTRADICTION"
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
                    "E2_CONTRADICTION_PROTOCOL_VIEW"
                ],
                "forbidden_knowledge_classes": [
                    "RAW_REPORT_PATHS",
                    "PRODUCER_IDENTITY",
                    "SUPPORT_COUNT",
                    "PRIOR_POPULARITY",
                    "UNAPPROVED_RESOLVER_TARGETS",
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
                        "BDB_POLICY::E2_CONTRADICTION_BOUNDED_VIEW"
                    ),
                    "channel_class": (
                        "CONTROLLED_CONTRADICTION_VIEW"
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
                        "knowledge_E2_CONTRADICTION_"
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
                        "E2_CONTRADICTION_PROTOCOL_VIEW"
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
                "e2_contradiction_authorization:"
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
                "e2_contradiction_authorization:"
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
            stage_id="E2",
            phase_id="E2-CONTRADICTION",
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
    "E2ContradictionAuthorizationService",
    "build_e2_contradiction_view",
]

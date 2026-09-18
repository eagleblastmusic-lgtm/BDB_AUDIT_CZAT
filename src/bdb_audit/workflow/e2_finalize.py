"""E2 shadow validation and no-conflict stage finalization.

The independent shadow result is a challenger proposal.  A conflict never gets
silently averaged or majority-voted away: this service leaves E2 unfinished and
returns a contradiction-protocol requirement.  Only a complete shadow pass with
zero reported conflicts can produce the E2 StageCompletion.

StageCompletion is stage-local authority only; OPEN adjudication decisions stay
OPEN and remain visible to later coverage/STOP logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..coordinator import Coordinator
from ..core.errors import ValidationError
from ..core.ids import deterministic_id
from ..core.registry import canonical_reference_set
from ..history.objects import CommandEnvelope
from ..history.store import TransactionalHistoryStore
from ..stop.models import StageCompletion
from .assignments import _command_id, _current_cut
from .e2_shadow import _main_decisions
from .inbox import _same_ref, _with_ref_class
from .manual_stage import StageBatch, StageResultInbox


_CONFLICT_TYPES = {
    "OVER_MERGING",
    "UNDER_MERGING",
    "SEVERITY_INFLATION",
    "FALSE_DISMISSAL",
    "ORIGIN_MISCLASSIFICATION",
    "EVIDENCE_OVERSTATING",
    "PREVIOUS_FALSE_NEGATIVE_MISCLASSIFICATION",
}


@dataclass(frozen=True)
class E2FinalizationSummary:
    campaign_id: str
    stage_completed: bool
    stage_completion_ref: dict[str, Any] | None
    shadow_conflict_claim_digests: tuple[str, ...]
    shadow_result_ref: dict[str, Any]
    adjudication_decision_refs: tuple[dict[str, Any], ...]
    accepted_commit_seq: int
    already_finalized: bool
    next_action: str


class E2FinalizationService:
    def __init__(
        self,
        store: TransactionalHistoryStore,
        shadow_batch: StageBatch,
        shadow_inbox: StageResultInbox | None = None,
    ):
        if (
            shadow_batch.stage_id != "E2"
            or shadow_batch.phase_id != "E2-SHADOW"
        ):
            raise ValidationError(
                "E2_SHADOW_BATCH_REQUIRED",
                f"{shadow_batch.stage_id}/{shadow_batch.phase_id}",
            )
        self.store = store
        self.batch = shadow_batch
        self.inbox = shadow_inbox
        self.coordinator = Coordinator(store)

    def _shadow_result(
        self,
        cut: dict[str, Any],
    ) -> dict[str, Any]:
        if len(self.batch.jobs) != 1:
            raise ValidationError(
                "E2_SHADOW_SINGLE_LANE_REQUIRED"
            )
        job = next(iter(self.batch.jobs.values()))
        matches = [
            row
            for row in self.store.accepted_records(
                "bdb_audit_lane_result",
                cut,
            )
            if row["body"].get("stage_id") == "E2"
            and row["body"].get("phase_id") == "E2-SHADOW"
            and _same_ref(
                row["body"].get("assignment_ref"),
                job.assignment_ref,
            )
        ]
        if len(matches) != 1:
            raise ValidationError(
                "E2_SHADOW_RESULT_REQUIRED",
                str(len(matches)),
            )
        return matches[0]

    def _shadow_conflicts(
        self,
        result: dict[str, Any],
        decisions: tuple[dict[str, Any], ...],
    ) -> tuple[str, ...]:
        expected = {
            decision["body"]["claim_revision_ref"][
                "revision_digest"
            ]
            for decision in decisions
        }
        outputs = result["body"].get("outputs", {})
        checks = (
            outputs.get("shadow_checks")
            if isinstance(outputs, dict)
            else None
        )
        if not isinstance(checks, list):
            raise ValidationError(
                "E2_SHADOW_CHECKS_REQUIRED"
            )

        seen: set[str] = set()
        conflicts: list[str] = []
        for item in checks:
            if not isinstance(item, dict):
                raise ValidationError(
                    "E2_SHADOW_CHECK_INVALID"
                )
            claim_digest = item.get(
                "claim_revision_digest"
            )
            if (
                not isinstance(claim_digest, str)
                or claim_digest not in expected
            ):
                raise ValidationError(
                    "E2_SHADOW_UNKNOWN_CLAIM",
                    str(claim_digest),
                )
            if claim_digest in seen:
                raise ValidationError(
                    "E2_SHADOW_DUPLICATE_CHECK",
                    claim_digest,
                )
            seen.add(claim_digest)

            conflict = item.get("conflict")
            conflict_types = item.get(
                "conflict_types"
            )
            rationale = item.get("rationale", "")
            if not isinstance(conflict, bool):
                raise ValidationError(
                    "E2_SHADOW_CONFLICT_FLAG_INVALID",
                    claim_digest,
                )
            if (
                not isinstance(conflict_types, list)
                or any(
                    not isinstance(value, str)
                    or value not in _CONFLICT_TYPES
                    for value in conflict_types
                )
                or len(conflict_types)
                != len(set(conflict_types))
            ):
                raise ValidationError(
                    "E2_SHADOW_CONFLICT_TYPES_INVALID",
                    claim_digest,
                )
            if not isinstance(rationale, str):
                raise ValidationError(
                    "E2_SHADOW_RATIONALE_INVALID",
                    claim_digest,
                )
            if conflict and not conflict_types:
                raise ValidationError(
                    "E2_SHADOW_CONFLICT_TYPE_REQUIRED",
                    claim_digest,
                )
            if not conflict and conflict_types:
                raise ValidationError(
                    "E2_SHADOW_SPURIOUS_CONFLICT_TYPE",
                    claim_digest,
                )
            if conflict:
                conflicts.append(claim_digest)

        missing = sorted(expected - seen)
        if missing:
            raise ValidationError(
                "E2_SHADOW_CHECKS_INCOMPLETE",
                ",".join(missing),
            )
        return tuple(sorted(conflicts))

    def _all_e2_lane_completions(
        self,
        cut: dict[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        result_rows = [
            row
            for row in self.store.accepted_records(
                "bdb_audit_lane_result",
                cut,
            )
            if row["body"].get("stage_id") == "E2"
            and row["body"].get("phase_id")
            in {"E2-BLIND", "E2-REVEAL", "E2-SHADOW"}
        ]
        result_digests = {
            row["ref"]["revision_digest"]
            for row in result_rows
        }
        completions = []
        covered: set[str] = set()
        for row in self.store.accepted_records(
            "lane_completion",
            cut,
        ):
            outputs = row["body"].get(
                "required_output_refs",
                [],
            )
            matched = {
                ref["revision_digest"]
                for ref in outputs
                if isinstance(ref, dict)
                and ref.get("kind")
                == "bdb_audit_lane_result"
                and ref.get("revision_digest")
                in result_digests
            }
            if not matched:
                continue
            if (
                row["body"].get(
                    "completion_predicate_result"
                )
                != "LANE_COMPLETED"
            ):
                raise ValidationError(
                    "E2_LANE_COMPLETION_BLOCKED"
                )
            covered.update(matched)
            completions.append(row)

        if covered != result_digests:
            raise ValidationError(
                "E2_LANE_COMPLETION_SET_INCOMPLETE",
                (
                    f"missing="
                    f"{sorted(result_digests - covered)}"
                ),
            )
        return tuple(completions)

    def _existing_stage_completion(
        self,
        cut: dict[str, Any],
    ) -> dict[str, Any] | None:
        rows = []
        for row in self.store.accepted_records(
            "stage_completion",
            cut,
        ):
            spec = self.store.resolve_accepted(
                row["body"]["stage_spec_ref"],
                cut,
            )
            if (
                spec["body"].get("stage_key") == "E2"
                and row["body"].get(
                    "completion_predicate_result"
                )
                == "STAGE_COMPLETED"
            ):
                rows.append(row)
        if len(rows) > 1:
            raise ValidationError(
                "MULTIPLE_E2_STAGE_COMPLETIONS"
            )
        return rows[0] if rows else None

    def finalize(self) -> E2FinalizationSummary:
        if self.inbox is not None:
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
                    "E2_SHADOW_PHASE_NOT_COMPLETE"
                )

        cut, prior_commit = _current_cut(self.store)
        decisions = _main_decisions(
            self.store,
            cut,
        )
        shadow_result = self._shadow_result(cut)
        conflicts = self._shadow_conflicts(
            shadow_result,
            decisions,
        )

        decision_refs = tuple(
            canonical_reference_set(
                [
                    _with_ref_class(
                        row["ref"],
                        "CONTENT_OR_PRIOR",
                    )
                    for row in decisions
                ]
            )
        )
        shadow_ref = _with_ref_class(
            shadow_result["ref"],
            "CONTENT_OR_PRIOR",
        )

        existing = self._existing_stage_completion(
            cut
        )
        if existing is not None:
            return E2FinalizationSummary(
                campaign_id=self.batch.campaign_id,
                stage_completed=True,
                stage_completion_ref=_with_ref_class(
                    existing["ref"],
                    "CONTENT_OR_PRIOR",
                ),
                shadow_conflict_claim_digests=(),
                shadow_result_ref=shadow_ref,
                adjudication_decision_refs=decision_refs,
                accepted_commit_seq=existing[
                    "accepted_seq"
                ],
                already_finalized=True,
                next_action="PREPARE_E3",
            )

        if conflicts:
            return E2FinalizationSummary(
                campaign_id=self.batch.campaign_id,
                stage_completed=False,
                stage_completion_ref=None,
                shadow_conflict_claim_digests=conflicts,
                shadow_result_ref=shadow_ref,
                adjudication_decision_refs=decision_refs,
                accepted_commit_seq=self.store.head().commit_seq,
                already_finalized=False,
                next_action=(
                    "E2_CONTRADICTION_PROTOCOL_REQUIRED"
                ),
            )

        completions = (
            self._all_e2_lane_completions(cut)
        )
        job = next(iter(self.batch.jobs.values()))
        assignment = self.store.resolve_accepted(
            job.assignment_ref,
            cut,
        )
        attempt = self.store.resolve_accepted(
            assignment["body"]["attempt_ref"],
            cut,
        )
        lane_run = self.store.resolve_accepted(
            attempt["body"]["lane_run_ref"],
            cut,
        )
        stage_run = self.store.resolve_accepted(
            lane_run["body"]["stage_run_ref"],
            cut,
        )
        stage_spec = self.store.resolve_accepted(
            assignment["body"]["stage_spec_ref"],
            cut,
        )
        if stage_spec["body"].get(
            "stage_key"
        ) != "E2":
            raise ValidationError(
                "E2_STAGE_SPEC_BINDING_MISMATCH"
            )

        checkpoint_refs = [
            _with_ref_class(
                row["ref"],
                "CONTENT_OR_PRIOR",
            )
            for row in self.store.accepted_records(
                "checkpoint",
                cut,
            )
            if row["body"].get("stage_id") == "E2"
            and row["body"].get("phase_id")
            == "E2-BLIND"
        ]
        required_outputs = canonical_reference_set(
            [
                *decision_refs,
                *checkpoint_refs,
                shadow_ref,
            ]
        )
        completion_refs = canonical_reference_set(
            [
                _with_ref_class(
                    row["ref"],
                    "CONTENT_OR_PRIOR",
                )
                for row in completions
            ]
        )
        open_count = sum(
            1
            for row in decisions
            if row["body"].get(
                "lifecycle_status"
            )
            == "OPEN"
        )

        stage_completion = StageCompletion(
            stage_completion_id=deterministic_id(
                "stage_completion",
                "e2-final:"
                + ":".join(
                    ref["revision_digest"]
                    for ref in required_outputs
                ),
            ),
            stage_run_ref=_with_ref_class(
                stage_run["ref"],
                "CONTENT_OR_PRIOR",
            ),
            stage_spec_ref=_with_ref_class(
                stage_spec["ref"],
                "HISTORY_CONTEXT_BINDING",
            ),
            input_history_cut=cut,
            required_lane_slot_results=completion_refs,
            required_output_refs=required_outputs,
            mandatory_obligation_summary={
                "blind_phase_required": True,
                "controlled_reveal_required": True,
                "shadow_adjudicator_required": True,
                "shadow_conflicts": 0,
                "adjudication_decisions": len(
                    decisions
                ),
                "open_adjudication_decisions": (
                    open_count
                ),
            },
            unresolved_material_refs=[],
            unknown_blocked_summary={
                "unknown_surfaces_count": 0,
                "scope_note": (
                    "E2 stage completion is not "
                    "global STOP or release readiness"
                ),
            },
            completion_predicate_result=(
                "STAGE_COMPLETED"
            ),
        )
        stage_obj = stage_completion.as_object()

        head = self.store.head()
        if head is None:
            raise ValidationError(
                "CAMPAIGN_NOT_INITIALIZED"
            )
        command = CommandEnvelope(
            command_id=_command_id(
                "e2_stage_completion:"
                + stage_obj.digest
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
                "e2_stage_completion:"
                + stage_obj.digest
            ),
            campaign_ref=head.campaign_id,
        )
        accepted = self.coordinator.accept(
            command,
            immutable_objects=[stage_obj],
            expected_head=head,
        )

        return E2FinalizationSummary(
            campaign_id=self.batch.campaign_id,
            stage_completed=True,
            stage_completion_ref=stage_obj.as_ref(
                ref_class="CONTENT_OR_PRIOR"
            ).as_dict(),
            shadow_conflict_claim_digests=(),
            shadow_result_ref=shadow_ref,
            adjudication_decision_refs=decision_refs,
            accepted_commit_seq=accepted.head.commit_seq,
            already_finalized=False,
            next_action="PREPARE_E3",
        )


__all__ = [
    "E2FinalizationSummary",
    "E2FinalizationService",
]

"""Evidence-backed finalization for externally executed E3/E4 stages.

This module never fabricates audit results. StageCompletion is accepted only
after every required external phase has an accepted bdb_audit_lane_result and a
LANE_COMPLETED decision bound to that exact result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..coordinator import Coordinator
from ..core.errors import ValidationError
from ..core.ids import deterministic_id
from ..core.registry import canonical_reference_set
from ..history.objects import CommandEnvelope
from ..history.store import TransactionalHistoryStore
from ..stop.models import StageCompletion
from .assignments import _command_id, _current_cut
from .inbox import _with_ref_class


@dataclass(frozen=True)
class ExternalStageFinalizationSummary:
    campaign_id: str
    stage_id: str
    stage_completion_ref: dict[str, Any]
    accepted_commit_seq: int
    completed_phases: tuple[str, ...]
    required_lane_completions: int
    already_finalized: bool
    next_action: str


class ExternalStageFinalizationService:
    """Finalize one stage from accepted external phase results only."""

    def __init__(
        self,
        store: TransactionalHistoryStore,
        *,
        stage_id: str,
        required_phase_slots: Mapping[str, Sequence[str]],
        optional_phase_slots: Mapping[str, Sequence[str]] | None = None,
        next_action: str,
    ):
        self.store = store
        self.coordinator = Coordinator(store)
        self.stage_id = stage_id.upper()
        self.required_phase_slots = {
            phase: tuple(slots)
            for phase, slots in required_phase_slots.items()
        }
        self.optional_phase_slots = {
            phase: tuple(slots)
            for phase, slots in (optional_phase_slots or {}).items()
        }
        self.next_action = next_action

    def _stage_spec(self, cut: dict[str, Any]) -> dict[str, Any]:
        rows = [
            row
            for row in self.store.accepted_records("stage_spec", cut)
            if row["body"].get("stage_key") == self.stage_id
        ]
        if len(rows) != 1:
            raise ValidationError(
                "STAGE_FINALIZATION_SPEC_AMBIGUOUS",
                f"{self.stage_id}: expected 1 StageSpec, got {len(rows)}",
            )
        return rows[0]

    def _existing(
        self,
        cut: dict[str, Any],
        stage_spec: dict[str, Any],
    ) -> dict[str, Any] | None:
        digest = stage_spec["ref"]["revision_digest"]
        rows = [
            row
            for row in self.store.accepted_records("stage_completion", cut)
            if row["body"].get("stage_spec_ref", {}).get("revision_digest")
            == digest
        ]
        if len(rows) > 1:
            raise ValidationError(
                "MULTIPLE_STAGE_COMPLETIONS",
                self.stage_id,
            )
        return rows[0] if rows else None

    def _phase_is_present(
        self,
        cut: dict[str, Any],
        phase_id: str,
    ) -> bool:
        return any(
            row["body"].get("phase_id") == phase_id
            for row in self.store.accepted_records(
                "assignment_manifest", cut
            )
        ) or any(
            row["body"].get("stage_id") == self.stage_id
            and row["body"].get("phase_id") == phase_id
            for row in self.store.accepted_records(
                "bdb_audit_lane_result", cut
            )
        )

    def _phase_results(
        self,
        cut: dict[str, Any],
        phase_id: str,
        slots: Sequence[str],
    ) -> tuple[dict[str, Any], ...]:
        rows = [
            row
            for row in self.store.accepted_records(
                "bdb_audit_lane_result", cut
            )
            if row["body"].get("stage_id") == self.stage_id
            and row["body"].get("phase_id") == phase_id
        ]
        by_slot: dict[str, dict[str, Any]] = {}
        for row in rows:
            slot = row["body"].get("lane_slot")
            if slot not in slots:
                continue
            if slot in by_slot:
                raise ValidationError(
                    "MULTIPLE_STAGE_RESULTS_FOR_SLOT",
                    f"{self.stage_id}/{phase_id}/{slot}",
                )
            by_slot[str(slot)] = row
        missing = [slot for slot in slots if slot not in by_slot]
        if missing:
            raise ValidationError(
                "STAGE_PHASE_RESULT_SET_INCOMPLETE",
                f"{self.stage_id}/{phase_id}: {missing}",
            )
        return tuple(by_slot[slot] for slot in slots)

    def _completion_for_result(
        self,
        cut: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        digest = result["ref"]["revision_digest"]
        matches = []
        for row in self.store.accepted_records(
            "lane_completion", cut
        ):
            outputs = row["body"].get("required_output_refs", [])
            if any(
                isinstance(ref, dict)
                and ref.get("revision_digest") == digest
                for ref in outputs
            ):
                matches.append(row)
        if len(matches) != 1:
            raise ValidationError(
                "STAGE_LANE_COMPLETION_AMBIGUOUS",
                f"{digest}: expected 1 completion, got {len(matches)}",
            )
        if (
            matches[0]["body"].get("completion_predicate_result")
            != "LANE_COMPLETED"
        ):
            raise ValidationError(
                "STAGE_LANE_COMPLETION_BLOCKED",
                digest,
            )
        return matches[0]

    def _binding_from_result(
        self,
        cut: dict[str, Any],
        result: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        assignment_ref = result["body"].get("assignment_ref")
        if not isinstance(assignment_ref, dict):
            raise ValidationError("STAGE_RESULT_ASSIGNMENT_REF_REQUIRED")
        assignment = self.store.resolve_accepted(
            assignment_ref,
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
        return stage_run, stage_spec

    def validate_result(
        self,
        phase_id: str,
        slot: str,
        result: dict[str, Any],
    ) -> None:
        """Hook for stage-specific output-contract validation."""

    def finalize(self) -> ExternalStageFinalizationSummary:
        cut, prior_commit = _current_cut(self.store)
        stage_spec = self._stage_spec(cut)
        existing = self._existing(cut, stage_spec)
        if existing is not None:
            completed = list(self.required_phase_slots)
            completed.extend(
                phase
                for phase in self.optional_phase_slots
                if self._phase_is_present(cut, phase)
            )
            return ExternalStageFinalizationSummary(
                campaign_id=cut["campaign_id"],
                stage_id=self.stage_id,
                stage_completion_ref=_with_ref_class(
                    existing["ref"], "CONTENT_OR_PRIOR"
                ),
                accepted_commit_seq=int(existing["accepted_seq"]),
                completed_phases=tuple(completed),
                required_lane_completions=len(
                    existing["body"].get(
                        "required_lane_slot_results", []
                    )
                ),
                already_finalized=True,
                next_action=self.next_action,
            )

        phase_slots: list[tuple[str, tuple[str, ...]]] = list(
            self.required_phase_slots.items()
        )
        for phase, slots in self.optional_phase_slots.items():
            if self._phase_is_present(cut, phase):
                phase_slots.append((phase, slots))

        result_rows: list[dict[str, Any]] = []
        completion_rows: list[dict[str, Any]] = []
        stage_run_digests: set[str] = set()
        stage_run_ref: dict[str, Any] | None = None
        stage_spec_digest = stage_spec["ref"]["revision_digest"]

        for phase_id, slots in phase_slots:
            phase_results = self._phase_results(
                cut, phase_id, slots
            )
            for slot, result in zip(slots, phase_results):
                self.validate_result(phase_id, slot, result)
                completion = self._completion_for_result(
                    cut, result
                )
                stage_run, bound_spec = self._binding_from_result(
                    cut, result
                )
                if (
                    bound_spec["ref"]["revision_digest"]
                    != stage_spec_digest
                ):
                    raise ValidationError(
                        "STAGE_SPEC_BINDING_MISMATCH",
                        f"{self.stage_id}/{phase_id}/{slot}",
                    )
                stage_run_digests.add(
                    stage_run["ref"]["revision_digest"]
                )
                stage_run_ref = _with_ref_class(
                    stage_run["ref"], "CONTENT_OR_PRIOR"
                )
                result_rows.append(result)
                completion_rows.append(completion)

        if len(stage_run_digests) != 1 or stage_run_ref is None:
            raise ValidationError(
                "STAGE_RUN_BINDING_CONFLICT",
                self.stage_id,
            )

        extra_output_refs: list[dict[str, Any]] = []
        if self.stage_id == "E3":
            checkpoints = [
                row
                for row in self.store.accepted_records(
                    "checkpoint", cut
                )
                if row["body"].get("stage_id") == "E3"
                and row["body"].get("phase_id")
                == "E3-BLIND"
            ]
            if len(checkpoints) != 3:
                raise ValidationError(
                    "E3_BLIND_CHECKPOINT_SET_INCOMPLETE",
                    f"expected 3, got {len(checkpoints)}",
                )
            extra_output_refs.extend(
                _with_ref_class(
                    row["ref"], "CONTENT_OR_PRIOR"
                )
                for row in checkpoints
            )

        result_refs = canonical_reference_set(
            [
                _with_ref_class(
                    row["ref"], "CONTENT_OR_PRIOR"
                )
                for row in result_rows
            ]
        )
        completion_refs = canonical_reference_set(
            [
                _with_ref_class(
                    row["ref"], "CONTENT_OR_PRIOR"
                )
                for row in completion_rows
            ]
        )
        required_outputs = canonical_reference_set(
            [*result_refs, *extra_output_refs]
        )
        phase_names = tuple(phase for phase, _ in phase_slots)

        stage_completion = StageCompletion(
            stage_completion_id=deterministic_id(
                "stage_completion",
                (
                    self.stage_id.lower()
                    + "-external-final:"
                    + ":".join(
                        ref["revision_digest"]
                        for ref in required_outputs
                    )
                ),
            ),
            stage_run_ref=stage_run_ref,
            stage_spec_ref=_with_ref_class(
                stage_spec["ref"],
                "HISTORY_CONTEXT_BINDING",
            ),
            input_history_cut=cut,
            required_lane_slot_results=completion_refs,
            required_output_refs=required_outputs,
            mandatory_obligation_summary={
                "execution_mode": "EXTERNAL_EVIDENCE_BACKED",
                "required_phases": list(
                    self.required_phase_slots
                ),
                "completed_phases": list(phase_names),
                "completed_lane_results": len(result_refs),
            },
            unresolved_material_refs=[],
            unknown_blocked_summary={
                "unknown_surfaces_count": 0,
                "scope_note": (
                    f"{self.stage_id} completion proves only "
                    "the stage contract; it is not global STOP."
                ),
            },
            completion_predicate_result="STAGE_COMPLETED",
        )
        stage_obj = stage_completion.as_object()

        head = self.store.head()
        if head is None:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        command = CommandEnvelope(
            command_id=_command_id(
                f"{self.stage_id.lower()}_external_completion:"
                + stage_obj.digest
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
                prior_commit.get("governing_spec_refs", ())
            ),
            idempotency_scope=(
                f"{self.stage_id.lower()}_external_completion:"
                + stage_obj.digest
            ),
            campaign_ref=head.campaign_id,
        )
        accepted = self.coordinator.accept(
            command,
            immutable_objects=[stage_obj],
            expected_head=head,
        )
        return ExternalStageFinalizationSummary(
            campaign_id=cut["campaign_id"],
            stage_id=self.stage_id,
            stage_completion_ref=stage_obj.as_ref(
                ref_class="CONTENT_OR_PRIOR"
            ).as_dict(),
            accepted_commit_seq=accepted.head.commit_seq,
            completed_phases=phase_names,
            required_lane_completions=len(completion_refs),
            already_finalized=False,
            next_action=self.next_action,
        )


E4_REQUIRED_ASSESSMENTS: dict[str, frozenset[str]] = {
    "E4-MODEL": frozenset(
        {
            "STATE_MODEL",
            "MODEL_IMPLEMENTATION_CONFORMANCE",
            "TEMPORAL_INVARIANT",
            "PROPERTY_STATEFUL",
            "BOUNDED_EXPLORATION",
        }
    ),
    "E4-RESILIENCE": frozenset(
        {
            "FAULT_INJECTION",
            "CONCURRENCY",
            "CRASH_RECOVERY",
            "ENDURANCE",
        }
    ),
    "E4-CAUSAL": frozenset(
        {
            "CAUSAL_CHAIN",
            "SIBLING_ASSESSMENT",
        }
    ),
}
_E4_STATUSES = {
    "PASS",
    "FAIL",
    "NOT_APPLICABLE",
    "INCONCLUSIVE",
    "BLOCKED",
}


class E4FinalizationService(ExternalStageFinalizationService):
    """Validate the E4 external contract before accepting E4 completion."""

    def validate_result(
        self,
        phase_id: str,
        slot: str,
        result: dict[str, Any],
    ) -> None:
        if phase_id != "E4-DEEPEN":
            raise ValidationError(
                "UNSUPPORTED_E4_PHASE", phase_id
            )
        expected = E4_REQUIRED_ASSESSMENTS.get(slot)
        if expected is None:
            raise ValidationError("UNKNOWN_E4_LANE", slot)
        outputs = result["body"].get("outputs", {})
        assessments = outputs.get("e4_assessments")
        if not isinstance(assessments, list):
            raise ValidationError(
                "E4_ASSESSMENTS_REQUIRED", slot
            )
        by_kind: dict[str, dict[str, Any]] = {}
        for item in assessments:
            if not isinstance(item, dict):
                raise ValidationError(
                    "E4_ASSESSMENT_INVALID", slot
                )
            kind = item.get("assessment_kind")
            status = item.get("status")
            rationale = item.get("rationale")
            if (
                not isinstance(kind, str)
                or status not in _E4_STATUSES
                or not isinstance(rationale, str)
                or not rationale.strip()
            ):
                raise ValidationError(
                    "E4_ASSESSMENT_INVALID",
                    f"{slot}: {item}",
                )
            if kind in by_kind:
                raise ValidationError(
                    "E4_ASSESSMENT_DUPLICATE",
                    f"{slot}: {kind}",
                )
            by_kind[kind] = item

        missing = sorted(expected - set(by_kind))
        if missing:
            raise ValidationError(
                "E4_ASSESSMENT_SET_INCOMPLETE",
                f"{slot}: {missing}",
            )
        unresolved = sorted(
            kind
            for kind in expected
            if by_kind[kind]["status"]
            in {"INCONCLUSIVE", "BLOCKED"}
        )
        if unresolved:
            raise ValidationError(
                "E4_STAGE_UNRESOLVED",
                f"{slot}: {unresolved}",
            )


__all__ = [
    "ExternalStageFinalizationSummary",
    "ExternalStageFinalizationService",
    "E4FinalizationService",
    "E4_REQUIRED_ASSESSMENTS",
]

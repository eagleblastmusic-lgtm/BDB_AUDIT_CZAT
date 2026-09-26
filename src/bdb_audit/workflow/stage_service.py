"""Fail-closed facade for stage completion qualification.

Stage-specific runtimes own completion: they bind accepted execution results,
lane completions, outputs and pinned obligations before recording a
StageCompletion.  This generic facade has no such evidence inputs and must not
manufacture a successful completion from a stage key alone.
"""
from __future__ import annotations

from typing import Any, Sequence

from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from .read_models import campaign_status, current_accepted_cut


_STAGE_ORDER = ("E1", "E2", "E3", "E4", "E5")


class StageService:
    """Reject generic completion requests that lack accepted execution proof."""

    def __init__(self, store: TransactionalHistoryStore):
        self.store = store

    def qualify_and_complete_stage(
        self,
        stage_key: str,
        stage_results: Sequence[dict[str, Any]] = (),
        findings: Sequence[dict[str, Any]] = (),
        unknown_blocked_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Require a stage-specific evidence-backed completion path.

        The legacy parameters remain accepted for API compatibility, but
        arbitrary dictionaries are not accepted execution evidence.  E1-E4
        and E6 have stage-specific finalizers; E5 retains its explicit
        external challenger runtime gate.
        """
        head = self.store.head()
        if head is None:
            raise ValidationError("EMPTY_STORE", "Cannot complete a stage on an empty store")

        stage_key = str(stage_key).upper()
        if stage_key not in _STAGE_ORDER and stage_key != "E6":
            raise ValidationError("INVALID_STAGE_KEY", f"Unknown stage {stage_key}")

        cut = current_accepted_cut(self.store)
        status = campaign_status(self.store, lambda value: value.upper() if isinstance(value, str) else str(value))
        if stage_key in status["stages_completed"]:
            raise ValidationError(
                "STAGE_ALREADY_COMPLETED",
                f"Stage {stage_key} has already been completed in this campaign",
            )

        if stage_key in _STAGE_ORDER:
            index = _STAGE_ORDER.index(stage_key)
            if index > 0 and _STAGE_ORDER[index - 1] not in status["stages_completed"]:
                predecessor = _STAGE_ORDER[index - 1]
                raise ValidationError(
                    "PREDECESSOR_STAGE_NOT_COMPLETED",
                    f"Stage {predecessor} must be completed before qualifying {stage_key}",
                )
        elif "E5" not in status["stages_completed"]:
            raise ValidationError(
                "PREDECESSOR_STAGE_NOT_COMPLETED",
                "Stage E5 must be completed before qualifying E6",
            )

        specs = [
            row
            for row in self.store.accepted_records("stage_spec", cut)
            if row["body"].get("stage_key") == stage_key
        ]
        if not specs:
            raise ValidationError("STAGE_SPEC_NOT_FOUND", f"No accepted StageSpec found for {stage_key}")
        if stage_key != "E6" and len(specs) != 1:
            raise ValidationError("STAGE_SPEC_AMBIGUOUS", stage_key)

        if stage_key == "E5":
            raise ValidationError(
                "E5_EXTERNAL_CHALLENGER_RUNTIME_REQUIRED",
                (
                    "E5 completion requires real E5A external results, a frozen "
                    "CandidateAssuranceCase, and two externally executed E5B challenger results"
                ),
            )

        # These parameters contain untyped caller data; they cannot substitute
        # for accepted AssignmentManifest, Attempt, result and LaneCompletion
        # objects.  Stage-specific finalizers remain the only completion path.
        raise ValidationError(
            "STAGE_EXECUTION_EVIDENCE_REQUIRED",
            f"{stage_key} must be finalized from its accepted stage-specific execution results",
        )

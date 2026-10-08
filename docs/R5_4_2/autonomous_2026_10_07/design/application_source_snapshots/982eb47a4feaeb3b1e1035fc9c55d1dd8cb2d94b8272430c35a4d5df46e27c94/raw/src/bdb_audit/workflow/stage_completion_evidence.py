"""Small helpers for constructing canonical StageCompletion evidence."""
from __future__ import annotations

from typing import Any, Sequence

from ..core.errors import ValidationError
from ..history.authority_hooks import _stage_slot_key


def latest_required_lane_completions(
    store,
    *,
    stage_key: str,
    stage_spec: dict[str, Any],
    cut: dict[str, Any],
    candidates: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Return one latest accepted LaneCompletion for each required spec slot.

    Multiphase workflows can emit several completions for a logical lane slot.
    StageCompletion's slot contract is one-to-one, so the final canonical
    evidence points to the latest completion for each required slot. Phase
    outputs remain separately bound through StageCompletion.required_output_refs.
    """
    required = tuple(stage_spec["body"].get("required_lane_slots", ()))
    expected = {_stage_slot_key(stage_key, slot) for slot in required}
    selected: dict[str, dict[str, Any]] = {}

    for row in candidates:
        lane_spec = store.resolve_accepted(
            row["body"].get("lane_spec_ref"), cut
        )
        lane_key = lane_spec["body"].get("lane_key")
        if not isinstance(lane_key, str):
            raise ValidationError("STAGE_COMPLETION_LANE_KEY_REQUIRED")
        slot = _stage_slot_key(stage_key, lane_key)
        if slot not in expected:
            continue
        previous = selected.get(slot)
        if previous is None or row["accepted_seq"] > previous["accepted_seq"]:
            selected[slot] = row
        elif (
            row["accepted_seq"] == previous["accepted_seq"]
            and row["ref"]["revision_digest"]
            != previous["ref"]["revision_digest"]
        ):
            raise ValidationError(
                "STAGE_COMPLETION_LANE_COMPLETION_AMBIGUOUS",
                f"{stage_key}/{slot}",
            )

    if set(selected) != expected:
        raise ValidationError(
            "STAGE_COMPLETION_REQUIRED_LANE_SLOTS_MISMATCH",
            f"required={sorted(expected)}; observed={sorted(selected)}",
        )
    return tuple(
        selected[_stage_slot_key(stage_key, slot)]
        for slot in required
    )

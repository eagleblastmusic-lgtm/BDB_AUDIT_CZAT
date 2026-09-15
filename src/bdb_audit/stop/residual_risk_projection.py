"""M42/M44 authoritative residual-risk projection into StopInput."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from .models import Snapshot


def _current_risk_rows(store, cut) -> tuple[dict[str, Any], ...]:
    selected: dict[str, dict[str, Any]] = {}
    for row in store.accepted_records("residual_risk", cut):
        key = str(row["body"].get("risk_id") or row["ref"]["revision_digest"])
        prior = selected.get(key)
        if prior is None or int(row.get("accepted_seq", 0)) > int(prior.get("accepted_seq", 0)):
            selected[key] = row
    return tuple(
        selected[key]
        for key in sorted(selected)
        if selected[key]["body"].get("disposition") != "SUPERSEDED"
    )


def _risk_summary(rows: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "residual_risk_binding_verified": True,
        "accepted_residual_risk_count": 0,
        "blocking_residual_risk_count": 0,
        "unresolved_residual_risk_count": 0,
        "invalid_residual_risk_count": 0,
    }
    invalid_statuses = {"INVALIDATED", "CONTRADICTED", "STALE"}
    for row in rows:
        body = row["body"]
        disposition = body.get("disposition")
        status = body.get("status")
        blocking = bool(body.get("blocking_effect", False))
        approved = isinstance(body.get("owner_approval_ref"), dict)

        if status in invalid_statuses:
            summary["invalid_residual_risk_count"] += 1
        if blocking or disposition == "BLOCKED" or status in invalid_statuses:
            summary["blocking_residual_risk_count"] += 1
        elif (
            disposition == "ACCEPTED_RESIDUAL_RISK"
            and status == "VALID"
            and approved
        ):
            summary["accepted_residual_risk_count"] += 1
        else:
            summary["unresolved_residual_risk_count"] += 1
    return summary


def install_residual_risk_stop_projection(builder_cls) -> None:
    """Extend the canonical StopInput builder with current accepted risks."""
    original_descriptor = builder_cls.__dict__["build_from_store"]
    if getattr(original_descriptor, "_bdb_residual_risk_projection", False):
        return
    original = original_descriptor.__func__

    def build_from_store(cls, store, *args, **kwargs):
        from .input_builder import _derived_registered_ref

        stop_input = original(cls, store, *args, **kwargs)
        cut = dict(stop_input.input_history_cut)
        rows = _current_risk_rows(store, cut)
        risk_refs = [row["ref"] for row in rows]
        summary = dict(stop_input.unknown_blocked_summary)
        summary.update(_risk_summary(rows))

        snapshot_obj = getattr(stop_input, "_snapshot_obj", None)
        stop_input_snapshot_ref = stop_input.stop_input_snapshot_ref
        new_snapshot_obj = snapshot_obj
        if risk_refs and snapshot_obj is not None:
            snap_body = snapshot_obj.body
            projection_input_refs = [*snap_body.get("projection_input_refs", ()), *risk_refs]
            artifact_ref = _derived_registered_ref(
                "stop-input-snapshot",
                {
                    "input_history_cut": cut,
                    "projection_input_refs": projection_input_refs,
                },
            )
            snapshot = Snapshot(
                snapshot_id=snap_body.get("snapshot_id"),
                snapshot_type=snap_body.get("snapshot_type", "STOP_INPUT_STATE_CAPTURE"),
                as_of_head=cut,
                projection_code_revision="BDB_V2_SNAPSHOT_PROJECTION_3",
                projection_input_refs=projection_input_refs,
                snapshot_artifact_ref=artifact_ref,
            )
            new_snapshot_obj = snapshot.as_object()
            stop_input_snapshot_ref = snapshot.ref

        projected = replace(
            stop_input,
            residual_risk_refs=risk_refs,
            unknown_blocked_summary=summary,
            stop_input_snapshot_ref=stop_input_snapshot_ref,
        )
        if new_snapshot_obj is not None:
            object.__setattr__(projected, "_snapshot_obj", new_snapshot_obj)
        return projected

    wrapped = classmethod(build_from_store)
    setattr(wrapped.__func__, "_bdb_residual_risk_projection", True)
    setattr(builder_cls, "build_from_store", wrapped)


__all__ = ["install_residual_risk_stop_projection"]

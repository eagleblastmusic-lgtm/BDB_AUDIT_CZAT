"""M44 fail-closed residual-risk semantics for STOP and snapshot binding."""
from __future__ import annotations

from functools import wraps
from typing import Any

from ..core.errors import ValidationError
from .models import StopEvaluation


def _count(summary: dict[str, Any], key: str) -> int:
    value = summary.get(key, 0)
    return value if type(value) is int and value >= 0 else 0


def _body(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "body"):
        body = value.body
        return body() if callable(body) else body
    raise ValidationError("STOP_SNAPSHOT_BINDING_CONFLICT", "unsupported body")


def _validate_snapshot_with_residual_risk(stop_input: Any, snapshot: Any) -> None:
    input_body = _body(stop_input)
    snap_body = _body(snapshot)

    cut = input_body.get("input_history_cut", {})
    snap_head = snap_body.get("as_of_head", {})
    if (
        cut.get("campaign_id") != snap_head.get("campaign_id")
        or cut.get("accepted_head_seq") != snap_head.get("accepted_head_seq")
        or cut.get("accepted_head_hash") != snap_head.get("accepted_head_hash")
        or not cut.get("accepted_head_hash")
    ):
        raise ValidationError("STOP_SNAPSHOT_BINDING_CONFLICT", "as_of_head mismatch")

    direct_digests: set[str] = set()
    for field in (
        "source_generation_ref",
        "inventory_revision_ref",
        "mandatory_obligation_refs",
        "current_obligation_qualification_refs",
        "completed_stage_refs",
        "required_stage_spec_refs",
        "residual_risk_refs",
    ):
        value = input_body.get(field)
        if isinstance(value, dict) and isinstance(value.get("revision_digest"), str):
            direct_digests.add(value["revision_digest"])
        elif isinstance(value, (list, tuple)):
            direct_digests.update(
                item["revision_digest"]
                for item in value
                if isinstance(item, dict) and isinstance(item.get("revision_digest"), str)
            )

    snap_digests = {
        ref["revision_digest"]
        for ref in snap_body.get("projection_input_refs", ())
        if isinstance(ref, dict) and isinstance(ref.get("revision_digest"), str)
    }
    if snap_digests != direct_digests:
        raise ValidationError("STOP_SNAPSHOT_BINDING_CONFLICT", "projection_input_refs mismatch")


def install_residual_risk_evaluator(evaluator_module) -> None:
    """Patch the pure evaluator with §79 residual-risk decision semantics."""
    original = evaluator_module.evaluate_stop
    if getattr(original, "_bdb_residual_risk_evaluator", False):
        return

    @wraps(original)
    def evaluate_stop(stop_input, *args, **kwargs):
        summary = dict(stop_input.unknown_blocked_summary or {})
        ctx = stop_input.evaluation_context
        has_proof = "residual_risk_binding_verified" in summary
        if ctx in {"FINAL_POST_E5", "POST_E6"} and has_proof:
            stop_id = kwargs.get("stop_evaluation_id")
            if summary.get("residual_risk_binding_verified") is not True:
                return StopEvaluation(
                    stop_evaluation_id=stop_id,
                    stop_input_ref=stop_input.ref,
                    continuation_decision="BLOCKED",
                    assurance_level="INSUFFICIENT",
                    release_readiness="QUALIFICATION_BLOCKED",
                    reason_codes=("RESIDUAL_RISK_BINDING_UNVERIFIED",),
                )

            blocking = _count(summary, "blocking_residual_risk_count")
            unresolved = _count(summary, "unresolved_residual_risk_count")
            accepted = _count(summary, "accepted_residual_risk_count")

            if blocking:
                return StopEvaluation(
                    stop_evaluation_id=stop_id,
                    stop_input_ref=stop_input.ref,
                    continuation_decision="BLOCKED",
                    assurance_level="INSUFFICIENT",
                    release_readiness="TECHNICALLY_NOT_READY",
                    reason_codes=("BLOCKING_RESIDUAL_RISK",),
                )
            if unresolved:
                if kwargs.get("e6_plan_approved", False):
                    return StopEvaluation(
                        stop_evaluation_id=stop_id,
                        stop_input_ref=stop_input.ref,
                        continuation_decision="E6_REQUIRED",
                        assurance_level="BOUNDED",
                        release_readiness="QUALIFICATION_BLOCKED",
                        reason_codes=(
                            "UNRESOLVED_RESIDUAL_RISK",
                            "E6_REQUIRED_TO_RESOLVE_RESIDUAL_RISK",
                        ),
                    )
                return StopEvaluation(
                    stop_evaluation_id=stop_id,
                    stop_input_ref=stop_input.ref,
                    continuation_decision="BLOCKED",
                    assurance_level="INSUFFICIENT",
                    release_readiness="QUALIFICATION_BLOCKED",
                    reason_codes=("UNRESOLVED_RESIDUAL_RISK",),
                )

            if stop_input.residual_risk_refs and accepted != len(stop_input.residual_risk_refs):
                return StopEvaluation(
                    stop_evaluation_id=stop_id,
                    stop_input_ref=stop_input.ref,
                    continuation_decision="BLOCKED",
                    assurance_level="INSUFFICIENT",
                    release_readiness="QUALIFICATION_BLOCKED",
                    reason_codes=("RESIDUAL_RISK_ACCEPTANCE_INCOMPLETE",),
                )

        result = original(stop_input, *args, **kwargs)
        if (
            has_proof
            and result.continuation_decision == "PASS"
            and stop_input.residual_risk_refs
            and result.release_readiness != "READY_WITH_RESIDUAL_RISK"
        ):
            raise ValidationError("STOP_RESIDUAL_RISK_READINESS_MISMATCH")
        return result

    @wraps(evaluator_module.validate_stop_snapshot_binding)
    def validate_stop_snapshot_binding(stop_input, snapshot):
        input_body = _body(stop_input)
        if input_body.get("residual_risk_refs"):
            _validate_snapshot_with_residual_risk(stop_input, snapshot)
            return
        evaluator_module._bdb_original_stop_snapshot_binding(stop_input, snapshot)

    evaluator_module._bdb_original_stop_snapshot_binding = evaluator_module.validate_stop_snapshot_binding
    evaluate_stop._bdb_residual_risk_evaluator = True
    evaluator_module.evaluate_stop = evaluate_stop
    evaluator_module.validate_stop_snapshot_binding = validate_stop_snapshot_binding


__all__ = ["install_residual_risk_evaluator"]

"""Pure STOP evaluator over immutable StopInput (M24 / PR-027 / M44 / §103 / Data Contracts §76).

Normative decision axes:
- continuation_decision: PASS | CONTINUE_REQUIRED | E6_REQUIRED | BLOCKED
- assurance_level: ADEQUATE_FOR_DECLARED_SCOPE | BOUNDED | INSUFFICIENT
- release_readiness: READY | READY_WITH_RESIDUAL_RISK | TECHNICALLY_NOT_READY | QUALIFICATION_BLOCKED

Normative invariants:
- UNKNOWN/BLOCKED/insufficient/invalidated/contradicted state cannot silently become PASS.
- Qualification cardinality is not obligation coverage proof for authoritative inputs.
- Challenger cardinality is not exact-current-candidate binding proof for authoritative inputs.
- A decisive VIOLATION_CONFIRMED can still be a valid qualification outcome; defect/release
  disposition is a separate authority axis and is not inferred from coverage qualification alone.
- Pure/non-authoritative preview inputs remain backward-compatible when proof fields are absent;
  accepted StopInput objects are independently equality-checked by the history authority.
- Campaign termination is a separate CampaignConclusion decision.
"""
from __future__ import annotations

from typing import Any

from ..core.errors import ValidationError
from .models import StopInput, StopEvaluation


def _count(summary: dict[str, Any], key: str) -> int:
    value = summary.get(key, 0)
    return value if type(value) is int and value >= 0 else 0


def evaluate_stop(
    stop_input: StopInput,
    *,
    force_blocked: bool = False,
    blocker_reason: str | None = None,
    insufficient_data: bool | None = None,
    e6_plan_approved: bool = False,
    stop_evaluation_id: str | None = None,
) -> StopEvaluation:
    """Evaluate one immutable StopInput with fail-closed precedence."""
    ctx = stop_input.evaluation_context
    if insufficient_data is None:
        insufficient_data = ctx == "INTERMEDIATE"
    input_ref = stop_input.ref
    ub_summary = dict(stop_input.unknown_blocked_summary or {})

    if force_blocked or ub_summary.get("is_blocked", False):
        code = blocker_reason or "AUTHORITY_OR_ADMISSION_BLOCKED"
        return StopEvaluation(
            stop_evaluation_id=stop_evaluation_id,
            stop_input_ref=input_ref,
            continuation_decision="BLOCKED",
            assurance_level="INSUFFICIENT",
            release_readiness="QUALIFICATION_BLOCKED",
            reason_codes=(code,),
            blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
        )

    has_unknown_scope = (
        _count(ub_summary, "unknown_surfaces_count") > 0
        or bool(ub_summary.get("has_unknown_scope", False))
    )
    if has_unknown_scope and ctx in ("FINAL_POST_E5", "POST_E6"):
        if e6_plan_approved:
            return StopEvaluation(
                stop_evaluation_id=stop_evaluation_id,
                stop_input_ref=input_ref,
                continuation_decision="E6_REQUIRED",
                assurance_level="BOUNDED",
                release_readiness="QUALIFICATION_BLOCKED",
                reason_codes=("UNKNOWN_SURFACE_SCOPE", "E6_REQUIRED_TO_RESOLVE_SCOPE"),
                blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )
        return StopEvaluation(
            stop_evaluation_id=stop_evaluation_id,
            stop_input_ref=input_ref,
            continuation_decision="BLOCKED",
            assurance_level="INSUFFICIENT",
            release_readiness="QUALIFICATION_BLOCKED",
            reason_codes=("UNKNOWN_SURFACE_SCOPE",),
            blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
        )

    missing_stage_specs = _count(ub_summary, "missing_required_stage_specs_count")

    if ctx == "INTERMEDIATE":
        reasons: list[str] = []
        if stop_input.pending_required_stage_refs or missing_stage_specs:
            reasons.append("REQUIRED_STAGES_PENDING")
        if missing_stage_specs:
            reasons.append("REQUIRED_STAGE_SPECS_MISSING")
        if insufficient_data or ub_summary.get("insufficient_data", False):
            reasons.append("INSUFFICIENT_DATA")
        if stop_input.evidence_invalidation_refs:
            reasons.append("INVALIDATED_EVIDENCE_PENDING")
        if not reasons:
            reasons.append("INTERMEDIATE_STAGE_EVALUATION")
        return StopEvaluation(
            stop_evaluation_id=stop_evaluation_id,
            stop_input_ref=input_ref,
            continuation_decision="CONTINUE_REQUIRED",
            assurance_level="INSUFFICIENT",
            release_readiness="TECHNICALLY_NOT_READY",
            reason_codes=tuple(reasons),
            blocking_obligation_refs=(),
            remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
        )

    if ctx in ("FINAL_POST_E5", "POST_E6"):
        if stop_input.pending_required_stage_refs or missing_stage_specs:
            reasons = ["REQUIRED_STAGES_PENDING"]
            if missing_stage_specs:
                reasons.append("REQUIRED_STAGE_SPECS_MISSING")
            if insufficient_data:
                reasons.append("INSUFFICIENT_DATA")
            return StopEvaluation(
                stop_evaluation_id=stop_evaluation_id,
                stop_input_ref=input_ref,
                continuation_decision="CONTINUE_REQUIRED",
                assurance_level="INSUFFICIENT",
                release_readiness="TECHNICALLY_NOT_READY",
                reason_codes=tuple(reasons),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )

        failure_reasons: list[str] = []
        is_hard_blocked = False
        has_insufficient_material = bool(insufficient_data or ub_summary.get("insufficient_data", False))

        if stop_input.evidence_invalidation_refs:
            failure_reasons.extend(("UNRESOLVED_EVIDENCE_INVALIDATION", "INVALIDATED_EVIDENCE"))
            is_hard_blocked = True
        if stop_input.contradiction_refs:
            failure_reasons.append("OPEN_CONTRADICTION")
            is_hard_blocked = True

        if not stop_input.candidate_assurance_case_ref:
            failure_reasons.append("MISSING_CANDIDATE_ASSURANCE_CASE")
            is_hard_blocked = True
        if not stop_input.challenger_refs or len(stop_input.challenger_refs) != 2:
            failure_reasons.append("MISSING_REQUIRED_CHALLENGERS")
            is_hard_blocked = True
        elif ub_summary.get("challenger_binding_verified") is False:
            failure_reasons.append("CHALLENGER_BINDING_UNVERIFIED")
            is_hard_blocked = True

        challenger_blocked = _count(ub_summary, "challenger_blocked_count")
        challenger_counter = _count(ub_summary, "challenger_material_counterevidence_count")
        challenger_inconclusive = _count(ub_summary, "challenger_inconclusive_count")
        if challenger_blocked:
            failure_reasons.append("CHALLENGER_EXECUTION_BLOCKED")
            is_hard_blocked = True
        if challenger_counter:
            failure_reasons.append("MATERIAL_CHALLENGER_COUNTEREVIDENCE")
            is_hard_blocked = True
        if challenger_inconclusive:
            failure_reasons.append("CHALLENGER_INCONCLUSIVE")
            has_insufficient_material = True

        has_mandatory_obligations = bool(stop_input.mandatory_obligation_refs)
        has_unqualified_obligations = False
        if has_mandatory_obligations:
            if ub_summary.get("qualification_binding_verified") is False:
                has_unqualified_obligations = True
                failure_reasons.append("QUALIFICATION_BINDING_UNVERIFIED")
            if _count(ub_summary, "unqualified_mandatory_obligations_count") > 0:
                has_unqualified_obligations = True
            if not stop_input.current_obligation_qualification_refs:
                has_unqualified_obligations = True

        blocked_quals = _count(ub_summary, "blocked_qualification_count")
        stale_quals = _count(ub_summary, "stale_qualification_count")
        in_progress_quals = _count(ub_summary, "in_progress_qualification_count")
        inconclusive_quals = _count(ub_summary, "inconclusive_qualification_count")

        if blocked_quals:
            failure_reasons.append("BLOCKED_MANDATORY_QUALIFICATION")
            is_hard_blocked = True
        if stale_quals:
            failure_reasons.append("STALE_MANDATORY_QUALIFICATION")
            is_hard_blocked = True
        if in_progress_quals:
            failure_reasons.append("MANDATORY_QUALIFICATION_INCOMPLETE")
            has_insufficient_material = True
        if inconclusive_quals:
            failure_reasons.append("MANDATORY_QUALIFICATION_INCONCLUSIVE")
            has_insufficient_material = True
        if has_unqualified_obligations:
            failure_reasons.append("UNQUALIFIED_MANDATORY_OBLIGATIONS")
            has_insufficient_material = True
        if insufficient_data or ub_summary.get("insufficient_data", False):
            failure_reasons.append("INSUFFICIENT_DATA")

        seen_reasons: set[str] = set()
        deduped_reasons: list[str] = []
        for reason in failure_reasons:
            if reason not in seen_reasons:
                seen_reasons.add(reason)
                deduped_reasons.append(reason)

        if is_hard_blocked:
            return StopEvaluation(
                stop_evaluation_id=stop_evaluation_id,
                stop_input_ref=input_ref,
                continuation_decision="BLOCKED",
                assurance_level="INSUFFICIENT",
                release_readiness="QUALIFICATION_BLOCKED",
                reason_codes=tuple(deduped_reasons),
                blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )

        if has_insufficient_material:
            if e6_plan_approved:
                e6_reasons = list(deduped_reasons)
                if "INSUFFICIENT_DATA" in seen_reasons or in_progress_quals or inconclusive_quals or challenger_inconclusive:
                    e6_reasons.append("E6_REQUIRED_TO_ACQUIRE_DATA")
                if has_unqualified_obligations:
                    e6_reasons.extend(("E6_REQUIRED", "BOUNDED_ADDITIONAL_PLAN_APPROVED"))
                if ctx == "POST_E6":
                    e6_reasons.append("POST_E6_ADDITIONAL_ROUND_REQUIRED")
                final_reasons = tuple(dict.fromkeys(e6_reasons))
                return StopEvaluation(
                    stop_evaluation_id=stop_evaluation_id,
                    stop_input_ref=input_ref,
                    continuation_decision="E6_REQUIRED",
                    assurance_level="BOUNDED",
                    release_readiness="QUALIFICATION_BLOCKED",
                    reason_codes=final_reasons,
                    blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                    remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                )
            return StopEvaluation(
                stop_evaluation_id=stop_evaluation_id,
                stop_input_ref=input_ref,
                continuation_decision="BLOCKED",
                assurance_level="INSUFFICIENT",
                release_readiness="QUALIFICATION_BLOCKED",
                reason_codes=tuple(deduped_reasons),
                blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )

        if e6_plan_approved and ctx == "FINAL_POST_E5":
            return StopEvaluation(
                stop_evaluation_id=stop_evaluation_id,
                stop_input_ref=input_ref,
                continuation_decision="E6_REQUIRED",
                assurance_level="BOUNDED",
                release_readiness="QUALIFICATION_BLOCKED",
                reason_codes=("E6_REQUIRED", "BOUNDED_ADDITIONAL_PLAN_APPROVED"),
                blocking_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
                remaining_obligation_refs=tuple(stop_input.mandatory_obligation_refs),
            )

        release_readiness = "READY_WITH_RESIDUAL_RISK" if stop_input.residual_risk_refs else "READY"
        pass_code = "POST_E6_SATISFIED" if ctx == "POST_E6" else "ALL_REQUIREMENTS_SATISFIED"
        return StopEvaluation(
            stop_evaluation_id=stop_evaluation_id,
            stop_input_ref=input_ref,
            continuation_decision="PASS",
            assurance_level="ADEQUATE_FOR_DECLARED_SCOPE",
            release_readiness=release_readiness,
            reason_codes=(pass_code,),
            blocking_obligation_refs=(),
            remaining_obligation_refs=(),
        )

    raise ValidationError(f"UNKNOWN_EVALUATION_CONTEXT: {ctx}")


def validate_intermediate_stop(evaluation: StopEvaluation, context: str) -> None:
    """INTERMEDIATE context can never produce PASS or release readiness."""
    if context == "INTERMEDIATE":
        if evaluation.continuation_decision in ("PASS", "E6_REQUIRED"):
            raise ValidationError(
                f"INTERMEDIATE_CANNOT_PRODUCE_PASS: continuation_decision '{evaluation.continuation_decision}' is forbidden in INTERMEDIATE context."
            )
        if evaluation.release_readiness in ("READY", "READY_WITH_RESIDUAL_RISK"):
            raise ValidationError(
                f"INTERMEDIATE_CANNOT_PRODUCE_RELEASE_READINESS: release_readiness '{evaluation.release_readiness}' is forbidden in INTERMEDIATE context."
            )


def validate_stop_snapshot_binding(stop_input: Any, snapshot: Any) -> None:
    """Validate mechanical binding between StopInput and its backing Snapshot."""
    input_body = stop_input.body() if hasattr(stop_input, "body") and callable(stop_input.body) else (stop_input if isinstance(stop_input, dict) else stop_input.body)
    snap_body = snapshot.body() if hasattr(snapshot, "body") and callable(snapshot.body) else (snapshot if isinstance(snapshot, dict) else snapshot.body)

    cut = input_body.get("input_history_cut", {})
    snap_head = snap_body.get("as_of_head", {})
    cut_camp = cut.get("campaign_id")
    cut_seq = cut.get("accepted_head_seq") if cut.get("accepted_head_seq") is not None else cut.get("commit_seq")
    cut_hash = cut.get("accepted_head_hash") or cut.get("commit_hash")
    snap_camp = snap_head.get("campaign_id")
    snap_seq = snap_head.get("accepted_head_seq") if snap_head.get("accepted_head_seq") is not None else snap_head.get("commit_seq")
    snap_hash = snap_head.get("accepted_head_hash") or snap_head.get("commit_hash")

    if not cut_hash or not snap_hash or cut_camp != snap_camp or cut_seq != snap_seq or cut_hash != snap_hash:
        raise ValidationError("STOP_SNAPSHOT_BINDING_CONFLICT", "as_of_head mismatch")

    direct_digests = set()
    for field in (
        "source_generation_ref",
        "inventory_revision_ref",
        "mandatory_obligation_refs",
        "current_obligation_qualification_refs",
        "completed_stage_refs",
        "required_stage_spec_refs",
    ):
        val = input_body.get(field)
        if isinstance(val, dict) and "revision_digest" in val:
            direct_digests.add(val["revision_digest"])
        elif isinstance(val, (list, tuple)):
            for item in val:
                if isinstance(item, dict) and "revision_digest" in item:
                    direct_digests.add(item["revision_digest"])

    snap_digests = {
        r["revision_digest"]
        for r in snap_body.get("projection_input_refs", ())
        if isinstance(r, dict) and "revision_digest" in r
    }
    if snap_digests != direct_digests:
        raise ValidationError("STOP_SNAPSHOT_BINDING_CONFLICT", "projection_input_refs mismatch")

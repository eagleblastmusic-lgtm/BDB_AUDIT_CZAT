"""Authority validation for adaptive E6 StageSpec acceptance.

A stage whose ``stage_key`` is E6 is legal only when it is a deterministic
continuation of a prior accepted STOP result with ``E6_REQUIRED``.  The check
runs at the trusted Coordinator boundary against the durable accepted history
and cannot be satisfied by an in-memory model or object-table orphan.
"""
from __future__ import annotations

from typing import Any

from ..core.errors import ValidationError
from ..history.objects import AcceptedHead, CanonicalObject
from .authority import _accepted_index, _resolve
from .e6 import (
    POST_E6_STOP_OUTPUT,
    _contradiction_output,
    _identity_digest,
    _obligation_output,
    _reason_output,
    _ref_token,
    _transition_pin,
    parse_e6_relationship,
)
from .evaluator import evaluate_stop
from .models import StopEvaluation, StopInput


_ISOLATION_STRENGTH = {
    "UNKNOWN": 0,
    "RELAXED": 0,
    "DECLARED": 1,
    "ENFORCED": 2,
    "STRICT": 3,
}


def _accepted_ref(index: dict[tuple[str, str], dict[str, Any]], kind: str, digest: str) -> dict[str, Any]:
    membership = index.get((kind, digest))
    if membership is None:
        raise ValidationError("E6_REQUIRES_PRIOR_ACCEPTED_STOP", digest)
    return dict(membership["ref"])


def _current_trust_profile(index, con) -> dict[str, Any]:
    genesis_entries = [
        membership for (kind, _), membership in index.items() if kind == "campaign_genesis"
    ]
    if len(genesis_entries) != 1:
        raise ValidationError("E6_CAMPAIGN_GENESIS_REQUIRED")
    genesis = _resolve(dict(genesis_entries[0]["ref"]), index, con)
    trust_ref = genesis["body"].get("trust_profile_ref")
    if not isinstance(trust_ref, dict):
        raise ValidationError("E6_TRUST_PROFILE_REQUIRED")
    return trust_ref


def _baseline_isolation_level(index, con) -> str:
    rows: list[tuple[int, dict[str, Any]]] = []
    for (kind, _), membership in index.items():
        if kind != "isolation_qualification":
            continue
        row = _resolve(dict(membership["ref"]), index, con)
        rows.append((int(row["accepted_seq"]), row["body"]))
    if not rows:
        return "UNKNOWN"
    body = max(rows, key=lambda item: item[0])[1]
    return str(body.get("required_isolation_assurance") or body.get("result") or "UNKNOWN")


def _assert_stop_semantics(stop_evaluation: StopEvaluation, stop_input: StopInput) -> None:
    if stop_evaluation.stop_input_ref.get("revision_digest") != stop_input.as_object().digest:
        raise ValidationError("E6_STOP_INPUT_BINDING_MISMATCH")
    if stop_input.evaluation_context not in {"FINAL_POST_E5", "POST_E6"}:
        raise ValidationError("E6_ONLY_FROM_FINAL_STOP")

    recomputed = evaluate_stop(stop_input, e6_plan_approved=True)
    if (
        recomputed.continuation_decision != stop_evaluation.continuation_decision
        or recomputed.assurance_level != stop_evaluation.assurance_level
        or recomputed.release_readiness != stop_evaluation.release_readiness
        or tuple(recomputed.reason_codes) != tuple(stop_evaluation.reason_codes)
        or tuple(recomputed.blocking_obligation_refs) != tuple(stop_evaluation.blocking_obligation_refs)
        or tuple(recomputed.remaining_obligation_refs) != tuple(stop_evaluation.remaining_obligation_refs)
    ):
        raise ValidationError("E6_STOP_EVALUATION_SEMANTICS_MISMATCH")
    if stop_evaluation.continuation_decision != "E6_REQUIRED":
        raise ValidationError("E6_ONLY_FROM_E6_REQUIRED")


def validate_e6_stage_spec_accepted_authority(
    obj: CanonicalObject,
    *,
    current: AcceptedHead | None,
    con,
) -> None:
    """Validate one E6 StageSpec against the exact parent accepted history."""
    if obj.kind != "stage_spec" or obj.body.get("stage_key") != "E6":
        return
    if current is None:
        raise ValidationError("E6_REQUIRES_PRIOR_ACCEPTED_STOP")

    body = obj.body
    relation = parse_e6_relationship(body.get("stop_e6_relationship", ""))
    index = _accepted_index(current, con)

    stop_ref = _accepted_ref(index, "stop_evaluation", relation["stop"])
    stop_record = _resolve(stop_ref, index, con)
    stop_evaluation = StopEvaluation(**stop_record["body"])

    # Embedded StopInput refs created by the existing STOP contract may omit
    # optional logical_id.  Membership is therefore established by exact
    # accepted kind/digest/schema, then the accepted ref itself is used to
    # verify durable object bytes.
    stop_input_ref = dict(stop_evaluation.stop_input_ref)
    stop_input_digest = stop_input_ref.get("revision_digest")
    membership = index.get(("stop_input", stop_input_digest))
    if (
        membership is None
        or stop_input_ref.get("kind") != "stop_input"
        or membership["ref"].get("schema_revision_ref") != stop_input_ref.get("schema_revision_ref")
    ):
        raise ValidationError("E6_STOP_INPUT_REQUIRED")
    stop_input_record = _resolve(dict(membership["ref"]), index, con)
    stop_input = StopInput(**stop_input_record["body"])
    _assert_stop_semantics(stop_evaluation, stop_input)

    if relation["source"] != _identity_digest(stop_input.source_generation_ref):
        raise ValidationError("E6_SOURCE_GENERATION_MISMATCH")

    trust_ref = _current_trust_profile(index, con)
    if relation["trust"] != _identity_digest(trust_ref):
        raise ValidationError("E6_TRUST_PROFILE_MISMATCH")

    baseline_level = _baseline_isolation_level(index, con)
    proposed_level = relation["level"]
    if proposed_level not in _ISOLATION_STRENGTH:
        raise ValidationError("E6_ISOLATION_PROFILE_INVALID")
    if _ISOLATION_STRENGTH[proposed_level] < _ISOLATION_STRENGTH.get(baseline_level, 0):
        raise ValidationError("ISOLATION_REWRITE_FORBIDDEN")

    if body.get("stage_role") != "E6" or body.get("stage_ordinal") != 6:
        raise ValidationError("E6_CANONICAL_STAGE_SPEC_REQUIRED")
    if "E5" not in set(body.get("predecessor_requirements", ())):
        raise ValidationError("E6_PREDECESSOR_E5_REQUIRED")
    if not body.get("required_lane_slots"):
        raise ValidationError("E6_REQUIRED_LANE_MISSING")

    if body.get("coverage_obligation_policy_ref") != _ref_token(stop_input.governing_policy_ref):
        raise ValidationError("E6_GOVERNING_POLICY_MISMATCH")
    if body.get("transition_policy_ref") != _transition_pin(stop_input):
        raise ValidationError("E6_TRANSITION_POLICY_MISMATCH")

    outputs = set(body.get("required_stage_completion_outputs", ()))
    if POST_E6_STOP_OUTPUT not in outputs:
        raise ValidationError("E6_POST_STOP_REEVALUATION_REQUIRED")

    expected_obligations = {_obligation_output(ref) for ref in stop_evaluation.remaining_obligation_refs}
    actual_obligations = {item for item in outputs if str(item).startswith("E6_OBLIGATION:")}
    if actual_obligations != expected_obligations:
        raise ValidationError("DENOMINATOR_MANIPULATION_FORBIDDEN")

    expected_contradictions = {_contradiction_output(ref) for ref in stop_input.contradiction_refs}
    actual_contradictions = {item for item in outputs if str(item).startswith("E6_CONTRADICTION:")}
    if actual_contradictions != expected_contradictions:
        raise ValidationError("E6_CONTRADICTION_LAUNDERING_FORBIDDEN")

    expected_reasons = {_reason_output(str(reason)) for reason in stop_evaluation.reason_codes}
    actual_reasons = {item for item in outputs if str(item).startswith("E6_STOP_REASON:")}
    if actual_reasons != expected_reasons:
        raise ValidationError("E6_STOP_REASON_LAUNDERING_FORBIDDEN")

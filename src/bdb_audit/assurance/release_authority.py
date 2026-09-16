"""Accepted-history authority checks for canonical ReleaseQualification.

ReleaseQualification is a decision artifact, not a caller assertion.  Its
release-policy context must be derived from the exact accepted assessment cut.
For STOP_AXIS_MATERIALIZATION the exact policy and release result must also
remain identical to the accepted StopInput/StopEvaluation chain.
"""
from __future__ import annotations

from typing import Any

from ..core.errors import ValidationError
from ..history.objects import AcceptedHead, CanonicalObject
from ..stop.authority import _accepted_index, _history_context_ref, _resolve


def _require_typed_ref(body: dict[str, Any], field: str) -> dict[str, Any]:
    value = body.get(field)
    if not isinstance(value, dict) or not isinstance(value.get("revision_digest"), str):
        raise ValidationError("RELEASE_AUTHORITY_REFERENCE_REQUIRED", field)
    return value


def validate_release_qualification_accepted_authority(
    release_obj: CanonicalObject,
    *,
    current: AcceptedHead | None,
    con,
) -> None:
    """Fail closed before durability when release authority is not exact."""
    if release_obj.kind != "release_qualification":
        return
    if current is None:
        raise ValidationError("RELEASE_QUALIFICATION_REQUIRES_ACCEPTED_PARENT")

    body = release_obj.body
    basis_cut = body.get("release_assessment_basis_cut")
    if not isinstance(basis_cut, dict):
        raise ValidationError("RELEASE_ASSESSMENT_BASIS_CUT_REQUIRED")
    policy_token = basis_cut.get("governing_policy_ref")
    if not isinstance(policy_token, str) or not policy_token:
        raise ValidationError("RELEASE_POLICY_CONTEXT_REQUIRED")

    expected_policy_ref = _history_context_ref("policy_revision", policy_token)
    if body.get("release_policy_ref") != expected_policy_ref:
        raise ValidationError(
            "RELEASE_POLICY_BINDING_MISMATCH",
            "release_policy_ref must equal the policy context of release_assessment_basis_cut",
        )

    if body.get("assessment_basis") != "STOP_AXIS_MATERIALIZATION":
        return

    index = _accepted_index(current, con)
    stop_eval_ref = _require_typed_ref(body, "stop_evaluation_ref")
    stop_eval_record = _resolve(stop_eval_ref, index, con)
    stop_input_ref = stop_eval_record["body"].get("stop_input_ref")
    if not isinstance(stop_input_ref, dict) or not isinstance(stop_input_ref.get("revision_digest"), str):
        raise ValidationError("STOP_INPUT_REFERENCE_REQUIRED")
    stop_input_record = _resolve(stop_input_ref, index, con)

    if stop_input_record["body"].get("release_policy_ref") != expected_policy_ref:
        raise ValidationError(
            "DRIFT_DETECTED_MATERIALIZATION_INVALID",
            "STOP_AXIS_MATERIALIZATION cannot cross a release-policy context change",
        )

    expected_result = stop_eval_record["body"].get("release_readiness")
    if body.get("result") != expected_result:
        raise ValidationError(
            "RELEASE_STOP_AXIS_RESULT_MISMATCH",
            "STOP_AXIS_MATERIALIZATION must copy StopEvaluation.release_readiness exactly",
        )


__all__ = ["validate_release_qualification_accepted_authority"]

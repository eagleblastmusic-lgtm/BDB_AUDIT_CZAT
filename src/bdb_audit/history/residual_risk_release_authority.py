"""Refine M42 release authority without widening release policy.

For a fully COMPLETED campaign, STOP_AXIS_MATERIALIZATION must copy the exact
STOP release axis and preserve the release-policy context seen by STOP.  For
COMPLETED_LIMITED the baseline only permits non-READY results; this validator
therefore enforces exact risk propagation and policy provenance while leaving
the pre-existing limited-release selection to its release policy implementation.
"""
from __future__ import annotations

from functools import wraps
import hashlib

from ..core.errors import ValidationError


def _policy_ref_from_cut(cut) -> dict:
    if not isinstance(cut, dict):
        raise ValidationError("RELEASE_ASSESSMENT_BASIS_CUT_REQUIRED")
    token = cut.get("governing_policy_ref")
    if not isinstance(token, str) or not token:
        raise ValidationError("RELEASE_POLICY_CONTEXT_REQUIRED")
    normalized = token.lower()
    digest = (
        normalized
        if len(normalized) == 64 and all(ch in "0123456789abcdef" for ch in normalized)
        else hashlib.sha256(token.encode("utf-8")).hexdigest()
    )
    return {
        "kind": "policy_revision",
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::policy_revision/1",
        "ref_class": "HISTORY_CONTEXT_BINDING",
    }


def install_residual_risk_release_authority(authority_module) -> None:
    original = authority_module._validate_finalization_residual_risk_projection
    if getattr(original, "_bdb_release_risk_axis_refined", False):
        return

    @wraps(original)
    def validate(obj, *, current, con):
        body = obj.body
        if not (
            obj.kind == "release_qualification"
            and body.get("assessment_basis") == "STOP_AXIS_MATERIALIZATION"
        ):
            return original(obj, current=current, con=con)

        if current is None:
            raise ValidationError("PRIOR_ACCEPTED_REFERENCE_REQUIRED")

        # First retain the full residual-risk/finalization authority checks.
        active_rows, _current, index = authority_module._active_risk_rows(current, con)
        current_set = authority_module._digest_set(row["ref"] for row in active_rows)

        final_ref = body.get("final_assurance_case_ref")
        final_digest = final_ref.get("revision_digest") if isinstance(final_ref, dict) else None
        final_case = authority_module._accepted_body(
            "final_assurance_case", final_digest, index, con
        )
        final_set = authority_module._digest_set(final_case.get("residual_risk_refs", ()))
        if final_set != current_set:
            raise ValidationError("RESIDUAL_RISK_DRIFT_AFTER_STOP")
        if authority_module._digest_set(body.get("accepted_residual_risk_refs", ())) != final_set:
            raise ValidationError("FINALIZATION_RESIDUAL_RISK_MISMATCH")

        conclusion_ref = final_case.get("campaign_conclusion_ref")
        conclusion_digest = (
            conclusion_ref.get("revision_digest") if isinstance(conclusion_ref, dict) else None
        )
        conclusion = authority_module._accepted_body(
            "campaign_conclusion", conclusion_digest, index, con
        )

        stop_ref = body.get("stop_evaluation_ref")
        stop_digest = stop_ref.get("revision_digest") if isinstance(stop_ref, dict) else None
        stop_eval = authority_module._accepted_body("stop_evaluation", stop_digest, index, con)
        stop_readiness = stop_eval.get("release_readiness")
        result = body.get("result")

        # FRESH-02: release policy is semantic history context, not a caller
        # supplied label.  It must equal the exact policy represented by the
        # release assessment cut and, for STOP-axis materialization, the exact
        # policy frozen into the accepted StopInput used by StopEvaluation.
        expected_policy_ref = _policy_ref_from_cut(body.get("release_assessment_basis_cut"))
        if body.get("release_policy_ref") != expected_policy_ref:
            raise ValidationError("RELEASE_POLICY_BINDING_MISMATCH")

        stop_input_ref = stop_eval.get("stop_input_ref")
        stop_input_digest = (
            stop_input_ref.get("revision_digest") if isinstance(stop_input_ref, dict) else None
        )
        stop_input = authority_module._accepted_body(
            "stop_input", stop_input_digest, index, con
        )
        if stop_input.get("release_policy_ref") != expected_policy_ref:
            raise ValidationError("DRIFT_DETECTED_MATERIALIZATION_INVALID")

        if conclusion.get("termination_state") == "COMPLETED":
            if result != stop_readiness:
                raise ValidationError("FINALIZATION_BINDING_CONFLICT")
            if final_set and result != "READY_WITH_RESIDUAL_RISK":
                raise ValidationError("RESIDUAL_RISK_RELEASE_READINESS_MISMATCH")
            if not final_set and result == "READY_WITH_RESIDUAL_RISK":
                raise ValidationError("RESIDUAL_RISK_RELEASE_READINESS_MISMATCH")
        else:
            if result in {"READY", "READY_WITH_RESIDUAL_RISK"}:
                raise ValidationError("FINALIZATION_BINDING_CONFLICT")

    setattr(validate, "_bdb_release_risk_axis_refined", True)
    authority_module._validate_finalization_residual_risk_projection = validate


__all__ = ["install_residual_risk_release_authority"]

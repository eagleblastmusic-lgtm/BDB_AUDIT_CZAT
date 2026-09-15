"""Refine M42 release residual-risk consistency without widening release policy.

For a fully COMPLETED campaign, STOP_AXIS_MATERIALIZATION must copy the exact
STOP release axis.  For COMPLETED_LIMITED the baseline only permits non-READY
results; this M42 validator therefore enforces exact risk propagation and
forbids false READY while leaving the pre-existing limited-release selection to
its release policy implementation.
"""
from __future__ import annotations

from functools import wraps

from ..core.errors import ValidationError


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

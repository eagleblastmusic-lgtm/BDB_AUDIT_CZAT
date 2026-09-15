"""Full typed-identity resolver for residual-risk finalization.

StopEvaluation carries a digest-bearing StopInput ref, while accepted history
may additionally carry the StopInput logical_id. Finalization recovers the full
accepted ref from the canonical commit chain instead of treating a shortened
model ref as sufficient acceptance evidence.
"""
from __future__ import annotations

from functools import wraps

from ..core.errors import ValidationError
from ..stop.residual_risk_projection import _current_risk_rows


def _digest_set(refs) -> set[str]:
    return {
        ref.get("revision_digest")
        for ref in refs
        if isinstance(ref, dict) and isinstance(ref.get("revision_digest"), str)
    }


def install_full_identity_stop_lookup(finalization_module) -> None:
    original = finalization_module._stop_and_risks
    if getattr(original, "_bdb_full_stop_identity", False):
        return

    @wraps(original)
    def stop_and_risks(service, termination_state):
        cut = finalization_module.current_accepted_cut(service.store)
        stop_eval_record = service._latest(service.store.accepted_records("stop_evaluation", cut))
        if stop_eval_record is None:
            if termination_state == "COMPLETED":
                raise ValidationError("STOP_EVALUATION_REQUIRED")
            service.evaluate_stop_gate(evaluation_context="FINAL_POST_E5")
            cut = finalization_module.current_accepted_cut(service.store)
            stop_eval_record = service._latest(service.store.accepted_records("stop_evaluation", cut))
            if stop_eval_record is None:
                raise ValidationError("STOP_EVALUATION_REQUIRED")

        stop_input_ref = stop_eval_record["body"].get("stop_input_ref")
        stop_digest = stop_input_ref.get("revision_digest") if isinstance(stop_input_ref, dict) else None
        if not isinstance(stop_digest, str):
            raise ValidationError("FINALIZATION_STOP_INPUT_REQUIRED")

        matches = [
            row
            for row in service.store.accepted_records("stop_input", cut)
            if row["ref"].get("revision_digest") == stop_digest
        ]
        if len(matches) != 1:
            raise ValidationError("FINALIZATION_STOP_INPUT_IDENTITY_MISMATCH")
        stop_input_record = matches[0]
        stop_risk_refs = tuple(stop_input_record["body"].get("residual_risk_refs", ()))

        current_rows = _current_risk_rows(service.store, cut)
        current_risk_refs = tuple(row["ref"] for row in current_rows)
        if _digest_set(stop_risk_refs) != _digest_set(current_risk_refs):
            raise ValidationError(
                "RESIDUAL_RISK_DRIFT_AFTER_STOP",
                "Residual-risk authority changed after STOP; a fresh STOP evaluation is required",
            )
        prior_refs = finalization_module._prior_risk_refs(stop_risk_refs)
        return cut, stop_eval_record, prior_refs

    setattr(stop_and_risks, "_bdb_full_stop_identity", True)
    finalization_module._stop_and_risks = stop_and_risks


__all__ = ["install_full_identity_stop_lookup"]

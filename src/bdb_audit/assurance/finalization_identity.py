"""Full typed-identity resolver for residual-risk finalization.

StopEvaluation carries a digest-bearing StopInput ref, while accepted history
may additionally carry the StopInput logical_id. Finalization recovers the full
accepted ref from the canonical commit chain instead of treating a shortened
model ref as sufficient acceptance evidence.
"""
from __future__ import annotations

from functools import wraps

from ..core.errors import ValidationError


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

        (
            stop_input_record,
            source_generation_ref,
            candidate_ref,
            challenger_refs,
        ) = service._stop_input_basis(stop_eval_record, cut)
        stop_risk_refs = tuple(stop_input_record["body"].get("residual_risk_refs", ()))
        stop_release_policy_ref = stop_input_record["body"].get("release_policy_ref")
        if not isinstance(stop_release_policy_ref, dict):
            raise ValidationError(
                "RELEASE_POLICY_CONTEXT_REQUIRED",
                "Accepted StopInput must carry release_policy_ref",
            )

        # Residual risk equality is admitted by the shared store hook and is
        # checked again while materializing the finalization boundaries.
        prior_refs = finalization_module._prior_risk_refs(stop_risk_refs)
        return (
            cut,
            stop_eval_record,
            prior_refs,
            stop_release_policy_ref,
            source_generation_ref,
            candidate_ref,
            challenger_refs,
        )

    setattr(stop_and_risks, "_bdb_full_stop_identity", True)
    finalization_module._stop_and_risks = stop_and_risks


__all__ = ["install_full_identity_stop_lookup"]

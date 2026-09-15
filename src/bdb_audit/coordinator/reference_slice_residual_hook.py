"""Make the synthetic reference slice explicit about an empty residual-risk set.

The reference slice constructs its INTERMEDIATE StopInput directly rather than
through StopInputBuilder.  Its constructor already declares
``residual_risk_refs=[]``; this adapter adds the matching machine-readable zero
counters.  The durable store still independently proves that accepted history
really contains no current residual-risk revisions, so the adapter cannot hide
an accepted risk.
"""
from __future__ import annotations


def install_reference_slice_zero_risk_proof(reference_slice_module) -> None:
    original = reference_slice_module.StopInput
    if getattr(original, "_bdb_reference_slice_zero_risk_proof", False):
        return

    def stop_input_with_zero_risk_proof(*args, **kwargs):
        refs = kwargs.get("residual_risk_refs", ())
        if not refs:
            summary = dict(kwargs.get("unknown_blocked_summary") or {})
            expected = {
                "residual_risk_binding_verified": True,
                "accepted_residual_risk_count": 0,
                "blocking_residual_risk_count": 0,
                "unresolved_residual_risk_count": 0,
                "invalid_residual_risk_count": 0,
            }
            for key, value in expected.items():
                if key in summary and summary[key] != value:
                    raise ValueError(f"reference slice residual-risk proof conflict: {key}")
                summary[key] = value
            kwargs["unknown_blocked_summary"] = summary
        return original(*args, **kwargs)

    setattr(stop_input_with_zero_risk_proof, "_bdb_reference_slice_zero_risk_proof", True)
    setattr(reference_slice_module, "StopInput", stop_input_with_zero_risk_proof)


__all__ = ["install_reference_slice_zero_risk_proof"]

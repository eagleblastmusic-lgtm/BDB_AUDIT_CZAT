"""FRESH-02 regressions for canonical ReleaseQualification policy authority."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.history import authority_hooks
from bdb_audit.history.residual_risk_release_authority import (
    _policy_ref_from_cut,
    install_residual_risk_release_authority,
)


def _digest_set(refs) -> set[str]:
    return {
        ref.get("revision_digest")
        for ref in refs
        if isinstance(ref, dict) and isinstance(ref.get("revision_digest"), str)
    }


def _release_obj(*, basis: str, policy_ref: dict, cut: dict):
    return SimpleNamespace(
        kind="release_qualification",
        body={
            "assessment_basis": basis,
            "release_assessment_basis_cut": cut,
            "release_policy_ref": policy_ref,
            "final_assurance_case_ref": {"revision_digest": "final"},
            "stop_evaluation_ref": {"revision_digest": "stop"},
            "accepted_residual_risk_refs": [],
            "result": "READY",
        },
    )


def _fake_authority(*, stop_policy_ref: dict):
    def original(obj, *, current, con):
        return None

    def accepted_body(kind, digest, index, con):
        if kind == "final_assurance_case":
            return {
                "residual_risk_refs": [],
                "campaign_conclusion_ref": {"revision_digest": "conclusion"},
            }
        if kind == "campaign_conclusion":
            return {"termination_state": "COMPLETED"}
        if kind == "stop_evaluation":
            return {
                "release_readiness": "READY",
                "stop_input_ref": {"revision_digest": "stop-input"},
            }
        if kind == "stop_input":
            return {"release_policy_ref": stop_policy_ref}
        raise AssertionError(kind)

    module = SimpleNamespace(
        _validate_finalization_residual_risk_projection=original,
        _active_risk_rows=lambda current, con: ((), {}, object()),
        _digest_set=_digest_set,
        _accepted_body=accepted_body,
    )
    install_residual_risk_release_authority(module)
    return module


def test_history_package_installs_release_policy_authority_before_durability() -> None:
    assert getattr(
        authority_hooks._validate_finalization_residual_risk_projection,
        "_bdb_release_risk_axis_refined",
        False,
    ) is True


@pytest.mark.parametrize(
    "basis",
    ["STOP_AXIS_MATERIALIZATION", "FRESH_RELEASE_QUALIFICATION", "RELEASE_REASSESSMENT"],
)
def test_every_release_basis_rejects_forged_policy_binding(basis: str) -> None:
    cut = {"governing_policy_ref": "policy:accepted"}
    expected = _policy_ref_from_cut(cut)
    forged = dict(expected, revision_digest="1" * 64)
    module = _fake_authority(stop_policy_ref=expected)

    with pytest.raises(ValidationError, match="RELEASE_POLICY_BINDING_MISMATCH"):
        module._validate_finalization_residual_risk_projection(
            _release_obj(basis=basis, policy_ref=forged, cut=cut),
            current=object(),
            con=None,
        )


def test_stop_axis_rejects_policy_drift_even_when_release_ref_matches_current_cut() -> None:
    cut = {"governing_policy_ref": "policy:current"}
    expected = _policy_ref_from_cut(cut)
    stale_stop_policy = _policy_ref_from_cut({"governing_policy_ref": "policy:stale-stop"})
    module = _fake_authority(stop_policy_ref=stale_stop_policy)

    with pytest.raises(ValidationError, match="DRIFT_DETECTED_MATERIALIZATION_INVALID"):
        module._validate_finalization_residual_risk_projection(
            _release_obj(
                basis="STOP_AXIS_MATERIALIZATION",
                policy_ref=expected,
                cut=cut,
            ),
            current=object(),
            con=None,
        )


def test_stop_axis_accepts_exact_policy_binding_positive_control() -> None:
    cut = {"governing_policy_ref": "policy:accepted"}
    expected = _policy_ref_from_cut(cut)
    module = _fake_authority(stop_policy_ref=expected)

    assert module._validate_finalization_residual_risk_projection(
        _release_obj(
            basis="STOP_AXIS_MATERIALIZATION",
            policy_ref=expected,
            cut=cut,
        ),
        current=object(),
        con=None,
    ) is None

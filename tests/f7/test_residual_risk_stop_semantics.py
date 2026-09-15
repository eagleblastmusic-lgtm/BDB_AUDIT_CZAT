"""M44 STOP decision semantics for canonical residual-risk projections."""
from bdb_audit.stop.evaluator import evaluate_stop
from bdb_audit.stop.models import StopInput
from tests.f7.test_stop_authority_false_pass import _base, _ref


def _with_risk_summary(**overrides):
    data = _base()
    data["residual_risk_refs"] = [_ref("residual_risk", "f")]
    data["unknown_blocked_summary"].update(
        {
            "residual_risk_binding_verified": True,
            "accepted_residual_risk_count": 1,
            "blocking_residual_risk_count": 0,
            "unresolved_residual_risk_count": 0,
            "invalid_residual_risk_count": 0,
            **overrides,
        }
    )
    return data


def test_formally_accepted_nonblocking_risk_yields_ready_with_residual_risk() -> None:
    result = evaluate_stop(StopInput(**_with_risk_summary()), insufficient_data=False)
    assert result.continuation_decision == "PASS"
    assert result.assurance_level == "ADEQUATE_FOR_DECLARED_SCOPE"
    assert result.release_readiness == "READY_WITH_RESIDUAL_RISK"


def test_blocking_risk_cannot_pass() -> None:
    data = _with_risk_summary(
        accepted_residual_risk_count=0,
        blocking_residual_risk_count=1,
    )
    result = evaluate_stop(StopInput(**data), insufficient_data=False)
    assert result.continuation_decision == "BLOCKED"
    assert result.release_readiness == "TECHNICALLY_NOT_READY"
    assert "BLOCKING_RESIDUAL_RISK" in result.reason_codes


def test_invalid_or_stale_risk_authority_blocks_qualification() -> None:
    data = _with_risk_summary(
        accepted_residual_risk_count=0,
        invalid_residual_risk_count=1,
    )
    result = evaluate_stop(StopInput(**data), insufficient_data=False)
    assert result.continuation_decision == "BLOCKED"
    assert result.release_readiness == "QUALIFICATION_BLOCKED"
    assert "INVALID_RESIDUAL_RISK_AUTHORITY" in result.reason_codes


def test_unresolved_risk_requires_e6_when_plan_is_approved() -> None:
    data = _with_risk_summary(
        accepted_residual_risk_count=0,
        unresolved_residual_risk_count=1,
    )
    result = evaluate_stop(
        StopInput(**data),
        insufficient_data=False,
        e6_plan_approved=True,
    )
    assert result.continuation_decision == "E6_REQUIRED"
    assert result.release_readiness == "QUALIFICATION_BLOCKED"
    assert "E6_REQUIRED_TO_RESOLVE_RESIDUAL_RISK" in result.reason_codes


def test_unverified_risk_binding_is_fail_closed() -> None:
    data = _with_risk_summary(residual_risk_binding_verified=False)
    result = evaluate_stop(StopInput(**data), insufficient_data=False)
    assert result.continuation_decision == "BLOCKED"
    assert result.release_readiness == "QUALIFICATION_BLOCKED"
    assert "RESIDUAL_RISK_BINDING_UNVERIFIED" in result.reason_codes

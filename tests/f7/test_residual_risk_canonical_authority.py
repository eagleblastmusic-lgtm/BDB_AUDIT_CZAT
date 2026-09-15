"""Accepted-history authority regressions for M42/M44 residual risk."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from bdb_audit.assurance.residual_risk import ResidualRiskRecord, ResidualRiskService
from bdb_audit.coordinator.reference_slice import run_foundation_reference_slice
from bdb_audit.core.errors import ValidationError
from bdb_audit.coverage.models import ApprovalDecision
from bdb_audit.history.objects import CanonicalObject
from bdb_audit.stop.input_builder import StopInputBuilder
from bdb_audit.workflow.read_models import current_accepted_cut


def _actor_ref(seed: str) -> dict:
    return {
        "kind": "actor_or_authority_ref",
        "revision_digest": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_TARGET/actor_or_authority_ref",
        "ref_class": "PRIOR_ACCEPTED_ONLY",
    }


def _accept_approval(ctx, decision: str, suffix: str):
    store = ctx["store"]
    head = store.head()
    assert head is not None
    cut = current_accepted_cut(store)
    approval = ApprovalDecision(
        decision_id=f"approval_decision_00000000-0000-4000-8000-0000000000{suffix}",
        decision_type="RESIDUAL_RISK_OWNER_ACCEPTANCE",
        decision=decision,
        actor_ref=_actor_ref(f"actor-{suffix}"),
        actor_authority_ref=_actor_ref(f"authority-{suffix}"),
        input_history_cut=cut,
        reason_codes=(f"OWNER_{decision}",),
    )
    obj = approval.as_object()
    parent = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
    cmd = ctx["next_cmd"](parent)
    result = ctx["coordinator"].accept(cmd, immutable_objects=(obj,), expected_head=head)
    return obj, result.head


def _risk(approval_obj, *, disposition="ACCEPTED_RESIDUAL_RISK", blocking=False, revision="1"):
    return ResidualRiskRecord(
        risk_id="risk_network_timeout",
        risk_revision=revision,
        scope="network.timeout",
        description="Bounded timeout exposure under extreme load",
        materiality="MEDIUM",
        uncertainty_class="BOUNDED_EXCEPTION",
        reason_unresolved="Operational edge case remains after qualification",
        disposition=disposition,
        blocking_effect=blocking,
        owner_approval_ref=approval_obj.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
    )


def test_residual_risk_becomes_canonical_and_enters_stop_projection(tmp_path: Path) -> None:
    ctx = run_foundation_reference_slice(tmp_path / "risk-authority.sqlite", stop_at_seq=9)
    approval_obj, _ = _accept_approval(ctx, "APPROVED", "01")

    risk = _risk(approval_obj)
    accepted = ResidualRiskService.accept_record(ctx["store"], risk)
    assert accepted["status"] == "SUCCESS"

    cut = current_accepted_cut(ctx["store"])
    rows = ctx["store"].accepted_records("residual_risk", cut)
    assert len(rows) == 1
    assert rows[0]["ref"]["revision_digest"] == risk.digest()
    assert "history_cut" not in rows[0]["body"]
    assert "status" not in rows[0]["body"]
    assert "waiver_ref" not in rows[0]["body"]

    stop_input = StopInputBuilder.build_from_store(
        ctx["store"], evaluation_context="FINAL_POST_E5"
    )
    assert [ref["revision_digest"] for ref in stop_input.residual_risk_refs] == [risk.digest()]
    assert stop_input.unknown_blocked_summary["residual_risk_binding_verified"] is True
    assert stop_input.unknown_blocked_summary["accepted_residual_risk_count"] == 1
    assert stop_input.unknown_blocked_summary["blocking_residual_risk_count"] == 0
    assert stop_input.unknown_blocked_summary["unresolved_residual_risk_count"] == 0


def test_store_rejects_stop_input_that_omits_current_residual_risk_before_durability(tmp_path: Path) -> None:
    ctx = run_foundation_reference_slice(tmp_path / "risk-omission.sqlite", stop_at_seq=9)
    approval_obj, _ = _accept_approval(ctx, "APPROVED", "02")
    risk = _risk(approval_obj)
    ResidualRiskService.accept_record(ctx["store"], risk)

    stop_input = StopInputBuilder.build_from_store(
        ctx["store"], evaluation_context="FINAL_POST_E5"
    )
    forged_body = stop_input.body()
    forged_body["residual_risk_refs"] = []
    forged_summary = dict(forged_body["unknown_blocked_summary"])
    forged_summary["accepted_residual_risk_count"] = 0
    forged_body["unknown_blocked_summary"] = forged_summary
    forged = CanonicalObject("stop_input", forged_body, logical_id=stop_input.stop_input_id)

    head = ctx["store"].head()
    assert head is not None
    parent = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
    command = ctx["next_cmd"](parent)
    snapshot_obj = getattr(stop_input, "_snapshot_obj")

    with pytest.raises(ValidationError, match="STOP_CURRENT_PROJECTION_MISMATCH"):
        ctx["coordinator"].accept(
            command,
            immutable_objects=(snapshot_obj, forged),
            expected_head=head,
        )

    assert ctx["store"].head() == head
    assert ctx["store"].object_record(forged.digest) is None


def test_rejected_owner_decision_cannot_authorize_accepted_residual_risk(tmp_path: Path) -> None:
    ctx = run_foundation_reference_slice(tmp_path / "risk-rejected-approval.sqlite", stop_at_seq=9)
    approval_obj, head = _accept_approval(ctx, "REJECTED", "03")
    risk = _risk(approval_obj)

    with pytest.raises(ValidationError, match="RESIDUAL_RISK_APPROVAL_NOT_APPROVED"):
        ResidualRiskService.accept_record(ctx["store"], risk)

    assert ctx["store"].head() == head
    assert ctx["store"].object_record(risk.digest()) is None


def test_optional_service_input_cut_detects_stale_submission(tmp_path: Path) -> None:
    ctx = run_foundation_reference_slice(tmp_path / "risk-stale-submission.sqlite", stop_at_seq=9)
    approval_obj, _ = _accept_approval(ctx, "APPROVED", "04")
    stale_cut = ctx["head_cut"]
    risk = _risk(approval_obj)

    with pytest.raises(ValidationError, match="STALE_RESIDUAL_RISK_INPUT"):
        ResidualRiskService.accept_record(
            ctx["store"], risk, expected_input_history_cut=stale_cut
        )

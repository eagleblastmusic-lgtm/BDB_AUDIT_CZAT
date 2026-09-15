"""Targeted tests for Residual Risk Register (PR-E5-07 / M42)."""
import pytest
from bdb_audit.assurance.residual_risk import ResidualRiskRecord, ResidualRiskRegister
from bdb_audit.core.errors import ValidationError


def _cut(seq=10, digest="a" * 64):
    return {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": "CAMP-001",
        "accepted_head_seq": seq,
        "accepted_head_hash": digest,
        "governing_policy_ref": "pin:policy",
        "governing_spec_refs": ["pin:spec"],
    }


def _ref(kind, digest, ref_class="CONTENT_OR_PRIOR"):
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
    }


@pytest.fixture
def history_cut():
    return _cut()


@pytest.fixture
def approval_ref():
    return _ref("approval_decision", "a" * 64, "PRIOR_ACCEPTED_ONLY")


@pytest.fixture
def waiver_ref():
    return _ref("approval_decision", "b" * 64, "PRIOR_ACCEPTED_ONLY")


def test_valid_accepted_residual_risk(history_cut, approval_ref):
    rec = ResidualRiskRecord(
        risk_id="risk_001",
        risk_revision="rev_1",
        scope="network.timeout",
        description="Transient network timeout under extreme load",
        materiality="MEDIUM",
        uncertainty_class="BOUNDED_EXCEPTION",
        reason_unresolved="Acceptable operational edge case",
        disposition="ACCEPTED_RESIDUAL_RISK",
        blocking_effect=False,
        history_cut=history_cut,
        owner_approval_ref=approval_ref,
    )
    assert rec.disposition == "ACCEPTED_RESIDUAL_RISK"
    assert rec.status == "VALID"

    reg = ResidualRiskRegister(history_cut)
    reg.add_record(rec)
    assert len(reg.records) == 1


def test_unapproved_residual_risk_fail_closed(history_cut):
    with pytest.raises(ValidationError, match="RESIDUAL_RISK_REQUIRES_APPROVAL"):
        ResidualRiskRecord(
            risk_id="risk_unapproved",
            risk_revision="rev_1",
            scope="auth.bypass",
            description="High severity auth issue",
            materiality="CRITICAL",
            uncertainty_class="SECURITY_VULN",
            reason_unresolved="Unfixed",
            disposition="ACCEPTED_RESIDUAL_RISK",
            blocking_effect=True,
            history_cut=history_cut,
            owner_approval_ref=None,
        )


def test_unknown_scope_cannot_be_implicit_residual_risk(history_cut):
    with pytest.raises(ValidationError, match="RESIDUAL_RISK_REQUIRES_APPROVAL"):
        ResidualRiskRecord(
            risk_id="risk_unknown",
            risk_revision="rev_1",
            scope="unknown_subsystem",
            description="Unknown scope region",
            materiality="HIGH",
            uncertainty_class="UNKNOWN_SCOPE",
            reason_unresolved="Never analyzed",
            disposition="ACCEPTED_RESIDUAL_RISK",
            blocking_effect=True,
            history_cut=history_cut,
            owner_approval_ref=None,
        )


def test_stale_evidence_and_history_cut(history_cut, approval_ref):
    reg = ResidualRiskRegister(history_cut)
    stale_cut = _cut(8, "8" * 64)
    stale_rec = ResidualRiskRecord(
        risk_id="risk_stale",
        risk_revision="rev_1",
        scope="crypto.rng",
        description="RNG seed quality",
        materiality="LOW",
        uncertainty_class="STATISTICAL",
        reason_unresolved="Acceptable",
        disposition="ACCEPTED_RESIDUAL_RISK",
        blocking_effect=False,
        history_cut=stale_cut,
        owner_approval_ref=approval_ref,
    )
    with pytest.raises(ValidationError, match="STALE_RESIDUAL_RISK_INPUT"):
        reg.add_record(stale_rec)

    newer_cut = _cut(11, "d" * 64)
    assert reg.check_stale(newer_cut) is True
    assert reg.check_stale(history_cut) is False


def test_invalidated_waiver_and_evidence(history_cut, approval_ref, waiver_ref):
    reg = ResidualRiskRegister(history_cut)
    rec = ResidualRiskRecord(
        risk_id="risk_with_waiver",
        risk_revision="rev_1",
        scope="storage.wal",
        description="WAL sync frequency",
        materiality="MEDIUM",
        uncertainty_class="PERFORMANCE_TRADEOFF",
        reason_unresolved="Waived by security team",
        disposition="ACCEPTED_RESIDUAL_RISK",
        blocking_effect=False,
        history_cut=history_cut,
        evidence_refs=(_ref("registered_immutable_object", "c" * 64),),
        owner_approval_ref=approval_ref,
        waiver_ref=waiver_ref,
    )
    reg.add_record(rec)

    affected = reg.apply_invalidations({"b" * 64})
    assert affected == 1
    updated = reg.records["risk_with_waiver"]
    assert updated.status == "INVALIDATED"
    assert updated.disposition == "BLOCKED"
    assert updated.blocking_effect is True


def test_open_contradiction(history_cut, approval_ref):
    reg = ResidualRiskRegister(history_cut)
    rec = ResidualRiskRecord(
        risk_id="risk_contra",
        risk_revision="rev_1",
        scope="api.rate_limit",
        description="Rate limiting limits",
        materiality="LOW",
        uncertainty_class="BOUNDED",
        reason_unresolved="Accepted",
        disposition="ACCEPTED_RESIDUAL_RISK",
        blocking_effect=False,
        history_cut=history_cut,
        owner_approval_ref=approval_ref,
    )
    reg.add_record(rec)

    reg.apply_contradiction("risk_contra", {"reason": "Contradicted by DDoS benchmark"})
    updated = reg.records["risk_contra"]
    assert updated.status == "CONTRADICTED"
    assert updated.disposition == "BLOCKED"
    assert updated.blocking_effect is True


def test_deterministic_rebuild(history_cut, approval_ref):
    reg = ResidualRiskRegister(history_cut)
    rec = ResidualRiskRecord(
        risk_id="risk_det",
        risk_revision="rev_1",
        scope="det.test",
        description="Deterministic rebuild test",
        materiality="LOW",
        uncertainty_class="BOUNDED",
        reason_unresolved="Resolved",
        disposition="ACCEPTED_RESIDUAL_RISK",
        blocking_effect=False,
        history_cut=history_cut,
        owner_approval_ref=approval_ref,
    )
    reg.add_record(rec)

    canonical = reg.export_canonical()
    d1 = reg.digest()
    rebuilt = ResidualRiskRegister.rebuild(canonical)
    d2 = rebuilt.digest()

    assert d1 == d2
    assert len(rebuilt.records) == 1
    assert rebuilt.records["risk_det"].description == "Deterministic rebuild test"

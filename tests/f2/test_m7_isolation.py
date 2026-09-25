import hashlib
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.knowledge import (DiscoveryRecord, ExposureLedger, GrantAccepted,
                                 PotentialExposureRecord, blind_origin_eligible,
                                 classify_discovery)
from bdb_audit.orchestration.runs import IsolationQualification, LaneSpec, qualify_isolation


def ref(kind, seed):
    return {"kind": kind, "revision_digest": hashlib.sha256(seed.encode()).hexdigest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_TARGET/" + kind,
            "ref_class": "CONTENT_OR_PRIOR"}


def test_isolation_classes_do_not_fallback_to_enforced():
    attempt = ref("attempt", "a")
    cut = {"variant": "ACCEPTED_HISTORY_CUT", "accepted_head_seq": 1}
    executor = ref("executor_spec", "e")
    delivery = ref("delivery_spec", "d")
    inventory = ref("registered_immutable_object", "channels")
    witness = ref("raw_artifact_ref", "isolation-witness")

    q = qualify_isolation(
        attempt_ref=attempt,
        history_cut=cut,
        executor_profile_ref=executor,
        delivery_profile_ref=delivery,
        requested="ENFORCED",
        fresh_session_boundary=False,
        channel_inventory_ref=inventory,
    )
    assert q.isolation_class == "UNKNOWN"
    assert "FRESH_SESSION_BOUNDARY_NOT_ESTABLISHED" in q.reason_codes

    contaminated = qualify_isolation(
        attempt_ref=attempt,
        history_cut=cut,
        executor_profile_ref=executor,
        delivery_profile_ref=delivery,
        requested="ENFORCED",
        fresh_session_boundary=True,
        contaminated=True,
        channel_inventory_ref=inventory,
    )
    assert contaminated.isolation_class == "UNKNOWN"
    assert "CONTAMINATED_EXECUTION_CONTEXT" in contaminated.reason_codes

    incomplete = qualify_isolation(
        attempt_ref=attempt,
        history_cut=cut,
        executor_profile_ref=executor,
        delivery_profile_ref=delivery,
        requested="ENFORCED",
        fresh_session_boundary=True,
        channel_inventory_ref=inventory,
    )
    assert incomplete.isolation_class == "DECLARED"
    assert "ENFORCEMENT_WITNESSES_INCOMPLETE" in incomplete.reason_codes

    enforced = qualify_isolation(
        attempt_ref=attempt,
        history_cut=cut,
        executor_profile_ref=executor,
        delivery_profile_ref=delivery,
        requested="ENFORCED",
        fresh_session_boundary=True,
        channel_inventory_ref=inventory,
        enforcement_receipt_refs=(witness,),
        filesystem_boundary_evidence_refs=(witness,),
        network_boundary_evidence_refs=(witness,),
        tool_boundary_evidence_refs=(witness,),
        session_boundary_evidence_refs=(witness,),
    )
    assert enforced.isolation_class == "ENFORCED"
    assert enforced.required_isolation_assurance == "ENFORCED"

    declared = qualify_isolation(
        attempt_ref=attempt,
        history_cut=cut,
        executor_profile_ref=executor,
        delivery_profile_ref=delivery,
        channel_inventory_ref=inventory,
    )
    assert declared.isolation_class == "DECLARED"
    assert declared.required_isolation_assurance == "DECLARED"
    assert "DECLARED_ISOLATION_ONLY" in declared.reason_codes

    with pytest.raises(
        ValidationError,
        match="ISOLATION_CHANNEL_INVENTORY_REQUIRED",
    ):
        qualify_isolation(
            attempt_ref=attempt,
            history_cut=cut,
            executor_profile_ref=executor,
            delivery_profile_ref=delivery,
        )

    with pytest.raises(
        ValidationError,
        match="NO_FALSE_ENFORCED_FALLBACK",
    ):
        IsolationQualification(
            attempt_ref=attempt,
            assessment_input_history_cut=cut,
            executor_profile_ref=executor,
            delivery_profile_ref=delivery,
            isolation_class="ENFORCED",
            fresh_session_boundary=True,
            channel_inventory_ref=inventory,
            required_isolation_assurance="ENFORCED",
        )


def test_grant_exposure_is_monotonic_and_discovery_provenance():
    attempt, cut = ref("attempt", "a"), {"variant": "ACCEPTED_HISTORY_CUT", "accepted_head_seq": 2}
    view, delivery = ref("view_manifest", "v"), ref("delivery_spec", "d")
    ledger = ExposureLedger()
    grant = GrantAccepted(attempt, cut, view, delivery, "forbidden-policy", "CONTROLLED")
    with pytest.raises(ValidationError, match="GRANT_NOT_ACCEPTED"):
        ledger.accept_grant(grant)
    grant_ref = grant.as_object().ref
    exposure = PotentialExposureRecord(attempt, grant_ref.as_dict(), view, cut)
    ledger._grants[grant_ref.revision_digest] = grant
    with pytest.raises(ValidationError, match="GRANT_NOT_ACCEPTED"):
        ledger.record_potential_exposure(exposure)
    # No ACK or failed transport operation has a ledger method that removes it.
    assert classify_discovery(pre_reveal=False, isolation_class="UNKNOWN") == "POST_REVEAL_CONFIRMATION"
    assert classify_discovery(pre_reveal=True, isolation_class="UNKNOWN") == "UNKNOWN_ISOLATION_DISCOVERY"
    with pytest.raises(ValidationError, match="BLIND_ORIGIN_REQUIRES_ACCEPTED_PRECURSOR"):
        classify_discovery(pre_reveal=True, isolation_class="ENFORCED", accepted_precursor=False)


def test_lane_spec_keeps_isolation_and_knowledge_requirements_explicit():
    spec = LaneSpec("E3-A", "1", "E3", "gap hunt", "differential",
                    required_isolation_assurance="ENFORCED",
                    forbidden_knowledge_classes=("PRIOR_FINDING",))
    assert spec.required_isolation_assurance == "ENFORCED"
    with pytest.raises(ValidationError, match="LANE_SPEC_DUPLICATE"):
        LaneSpec("E3-B", "1", "E3", "x", "x", scope_selectors=("a", "a"))

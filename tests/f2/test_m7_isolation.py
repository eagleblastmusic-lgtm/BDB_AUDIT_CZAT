import hashlib
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.knowledge import (DiscoveryRecord, ExposureLedger, GrantAccepted,
                                 PotentialExposureRecord, blind_origin_eligible,
                                 classify_discovery)
from bdb_audit.orchestration.runs import LaneSpec, qualify_isolation


def ref(kind, seed):
    return {"kind": kind, "revision_digest": hashlib.sha256(seed.encode()).hexdigest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_TARGET/" + kind,
            "ref_class": "CONTENT_OR_PRIOR"}


def test_isolation_classes_do_not_fallback_to_enforced():
    q = qualify_isolation(attempt_ref=ref("attempt", "a"), history_cut={"variant": "ACCEPTED_HISTORY_CUT", "accepted_head_seq": 1},
                          executor_profile_ref=ref("executor_spec", "e"), delivery_profile_ref=ref("delivery_spec", "d"),
                          requested="ENFORCED", fresh_session_boundary=False)
    assert q.isolation_class == "UNKNOWN"
    contaminated = qualify_isolation(attempt_ref=ref("attempt", "a"), history_cut={"variant": "ACCEPTED_HISTORY_CUT", "accepted_head_seq": 1},
                                     executor_profile_ref=ref("executor_spec", "e"), delivery_profile_ref=ref("delivery_spec", "d"),
                                     requested="ENFORCED", fresh_session_boundary=True, contaminated=True)
    assert contaminated.isolation_class == "UNKNOWN"


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

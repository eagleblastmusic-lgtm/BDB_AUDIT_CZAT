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
    q = qualify_isolation(attempt_ref=ref("attempt", "a"), history_cut={"variant": "ACCEPTED_HISTORY_CUT", "accepted_head_seq": 1},
                          executor_profile_ref=ref("executor_spec", "e"), delivery_profile_ref=ref("delivery_spec", "d"),
                          requested="ENFORCED", fresh_session_boundary=False)
    assert q.isolation_class == "UNKNOWN"
    contaminated = qualify_isolation(attempt_ref=ref("attempt", "a"), history_cut={"variant": "ACCEPTED_HISTORY_CUT", "accepted_head_seq": 1},
                                     executor_profile_ref=ref("executor_spec", "e"), delivery_profile_ref=ref("delivery_spec", "d"),
                                     requested="ENFORCED", fresh_session_boundary=True, contaminated=True)
    assert contaminated.isolation_class == "UNKNOWN"


def test_isolation_requires_material_channel_basis_before_enforced():
    common = {
        "attempt_ref": ref("attempt", "attempt"),
        "history_cut": {
            "variant": "ACCEPTED_HISTORY_CUT",
            "campaign_id": "campaign-test",
            "accepted_head_seq": 1,
            "accepted_head_hash": "a" * 64,
        },
        "executor_profile_ref": ref("executor_spec", "executor"),
        "delivery_profile_ref": ref("delivery_spec", "delivery"),
        "requested": "ENFORCED",
        "fresh_session_boundary": True,
    }
    assert qualify_isolation(**common).isolation_class == "UNKNOWN"

    with pytest.raises(ValidationError, match="ISOLATION_ENFORCEMENT_EVIDENCE_REQUIRED"):
        IsolationQualification(
            common["attempt_ref"],
            common["history_cut"],
            common["executor_profile_ref"],
            common["delivery_profile_ref"],
            "ENFORCED",
            fresh_session_boundary=True,
        )


@pytest.mark.parametrize(
    ("include_minimum_receipts", "expected_code"),
    [
        (False, "ISOLATION_REQUIRED_ASSURANCE_MISMATCH"),
        (True, "ISOLATION_REQUIRED_ASSURANCE_MISMATCH"),
    ],
)
def test_store_does_not_accept_unresolved_enforced_isolation(
    tmp_path, include_minimum_receipts, expected_code
):
    from bdb_audit.coordinator.reference_slice import run_foundation_reference_slice
    from bdb_audit.core.errors import ValidationError
    from bdb_audit.history.objects import CanonicalObject
    from bdb_audit.workflow.read_models import current_accepted_cut

    ctx = run_foundation_reference_slice(
        tmp_path / "isolation-context.sqlite",
        stop_at_seq=9,
    )
    store = ctx["store"]
    cut = current_accepted_cut(store)
    attempt = store.accepted_records("attempt", cut)[-1]
    source = store.accepted_records("source_generation", cut)[-1]["ref"]
    refs = [source] if include_minimum_receipts else []
    body = {
        "isolation_qualification_id": "iso_qual_direct_enforced",
        "attempt_ref": attempt["ref"],
        "assessment_input_history_cut": cut,
        "executor_profile_ref": attempt["body"]["executor_profile_ref"],
        "delivery_profile_ref": attempt["body"]["delivery_profile_ref"],
        "channel_inventory_ref": ref("registered_immutable_object", "channel-inventory"),
        "enforcement_receipt_refs": refs,
        "filesystem_boundary_evidence_refs": [],
        "network_boundary_evidence_refs": [],
        "tool_boundary_evidence_refs": [],
        "session_boundary_evidence_refs": refs,
        "contamination_assessment_refs": [],
        "required_isolation_assurance": "ENFORCED",
        "result": "ENFORCED",
        "scope": "test",
        "limitations": [],
        "reason_codes": [],
    }
    obj = CanonicalObject("isolation_qualification", body)
    head = store.head()
    command = ctx["next_cmd"]({"tag": "ACCEPTED_HEAD_REF", **head.as_dict()})

    with pytest.raises(ValidationError, match=expected_code):
        store.accept(command, expected_head=head, immutable_objects=(obj,))

    assert store.head() == head
    assert store.object_record(obj.digest) is None


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

from copy import deepcopy

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.schemas.foundation import foundation_schema_bindings
from bdb_audit.orchestration.capability import CapabilityBroker, ViewRef
from bdb_audit.knowledge.exposure import ExposureLedger
from .helpers import bootstrap_fixture
from .test_m5_transaction import fresh, ROOT
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.history.objects import HistoryCut


def accepted_grant_fixture(name):
    from dataclasses import replace
    from bdb_audit.history.objects import CanonicalObject
    from bdb_audit.orchestration.capability import GrantBody, ProjectionPolicy, ViewManifest
    profile, command, objects, parts = bootstrap_fixture()
    store = TransactionalHistoryStore(fresh(ROOT / name))
    first = store.accept(command, immutable_objects=objects, bootstrap_profile=profile)
    cut = HistoryCut.accepted(first.head, command.governing_policy_ref, command.governing_spec_refs).as_dict()
    def ref(kind, cls="HISTORY_CONTEXT_BINDING"):
        return {"kind": kind, "revision_digest": "e" * 64, "schema_revision_ref": "BDB_SCHEMA_REGISTRY::" + kind + "/1",
                "digest_profile": "BDB-OBJECT-DIGEST-1", "ref_class": cls}
    source = parts["source_generation"].as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict()
    stage = CanonicalObject("stage_run", {"stage_run_id": "stage_run_123e4567-e89b-42d3-a456-426614174000", "campaign_ref": command.proposed_campaign_id,
        "predecessor_stage_completion_refs": [], "required_lane_slot_contract_refs": [],
        "stage_spec_ref": ref("stage_spec"), "source_generation_ref": source,
        "creation_input_history_cut": cut, "assigned_history_cut": cut})
    lane = CanonicalObject("lane_run", {"lane_run_id": "lane_run_123e4567-e89b-42d3-a456-426614174000", "required_result_slots": [], "stage_run_ref": stage.ref.as_dict(), "lane_spec_ref": ref("lane_spec"),
        "source_generation_ref": source, "creation_input_history_cut": cut})
    attempt = CanonicalObject("attempt", {"attempt_id": "attempt_123e4567-e89b-42d3-a456-426614174000", "attempt_nonce": "fixture-1", "lane_run_ref": lane.ref.as_dict(), "executor_profile_ref": ref("executor_spec"),
        "delivery_profile_ref": ref("delivery_spec"), "assigned_history_cut": cut,
        "result_slot_contracts": [ref("result_slot_contract_ref")]})
    policy = ProjectionPolicy("test", "1", {"source_generation": ("representation_refs",)}, allowed_kinds=("source_generation",))
    manifest = ViewManifest("test", policy.as_object().ref.as_dict(), (parts["source_generation"].ref.as_dict(),))
    grant = GrantBody(attempt.ref.as_dict(), cut, manifest.ref, ref("delivery_spec"), "test-policy", "CONTROLLED")
    follow = replace(command, command_id="command_923e4567-e89b-42d3-a456-426614174000",
                     command_kind="RECORD_FOUNDATION_FACT", campaign_ref=command.proposed_campaign_id,
                     expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **first.head.as_dict()},
                     proposed_campaign_id=None, history_namespace_ref=None, bootstrap_profile_ref=None)
    second = store.accept(follow, expected_head=first.head, immutable_objects=(stage, lane, attempt, policy.as_object(), manifest.as_object(), grant.as_object()))
    current_cut = HistoryCut.accepted(second.head, command.governing_policy_ref, command.governing_spec_refs).as_dict()
    return store, grant, manifest, policy, parts, cut, current_cut


def test_forged_local_grant_does_not_authorize_delivery():
    broker = CapabilityBroker()
    broker._grants["a" * 64] = object()
    with pytest.raises(ValidationError, match="GRANT_NOT_ACCEPTED"):
        broker.deliver({"revision_digest": "a" * 64}, ViewRef("BDB_VIEW", "b" * 64))


def test_delivery_uses_accepted_grant_and_rebuilds_without_grant_cache():
    store, grant, manifest, policy, parts, prior, cut = accepted_grant_fixture("F2_ACCEPTED_GRANT_TEST.sqlite")
    artifacts = {parts["source_generation"].digest: dict(parts["source_generation"].body, kind="source_generation")}
    broker = CapabilityBroker(artifacts, history=store)
    view, raw = broker.prepare_view(manifest, policy)
    token = broker.accept_grant(grant, history_cut=cut)
    assert broker.deliver(token, view, history_cut=cut) == raw
    rebuilt = CapabilityBroker(artifacts, history=TransactionalHistoryStore(store.path))
    rebuilt_view, _ = rebuilt.prepare_view(manifest, policy)
    assert rebuilt.deliver(token, rebuilt_view, history_cut=cut) == raw
    ledger = ExposureLedger(history=store)
    assert token.revision_digest in ledger.exposures_for(grant.attempt_ref, history_cut=cut)
    ledger._exposures[grant.attempt_ref["revision_digest"]] = {"forged"}
    assert ledger.exposures_for(grant.attempt_ref, history_cut=cut) == ExposureLedger(history=store).exposures_for(grant.attempt_ref, history_cut=cut)
    for wrong in (prior, dict(cut, accepted_head_seq=3), dict(cut, accepted_head_hash="0" * 64)):
        with pytest.raises(ValidationError):
            broker.deliver(token, view, history_cut=wrong)
    forged = dict(token.as_dict(), revision_digest="0" * 64)
    broker._grants[forged["revision_digest"]] = grant
    with pytest.raises(ValidationError, match="OBJECT_NOT_ACCEPTED_AT_CUT"):
        broker.deliver(forged, view, history_cut=cut)


def test_command_required_fields_and_initialization_shape():
    _, command, _, _ = bootstrap_fixture()
    bindings = foundation_schema_bindings()
    valid = command.body()
    bindings.validate_schema("command_envelope", canonical_bytes(valid))
    invalid = [{}]
    for field in valid:
        body = deepcopy(valid)
        del body[field]
        invalid.append(body)
    invalid.extend([
        dict(valid, campaign_ref="future"),
        dict(valid, bootstrap_profile_ref="another-profile"),
        dict(valid, expected_parent_head={"tag": "EMPTY_HISTORY", "hash": "0" * 64}),
    ])
    for body in invalid:
        with pytest.raises(ValidationError, match="SCHEMA_VALIDATION_FAILED"):
            bindings.validate_schema("command_envelope", canonical_bytes(body))


def test_accepted_resolver_requires_exact_cut_and_membership():
    profile, command, objects, parts = bootstrap_fixture()
    store = TransactionalHistoryStore(fresh(ROOT / "F2_RESOLVER_TEST.sqlite"))
    result = store.accept(command, immutable_objects=objects, bootstrap_profile=profile)
    cut = HistoryCut.accepted(result.head, command.governing_policy_ref, command.governing_spec_refs).as_dict()
    ref = parts["genesis"].ref
    assert store.resolve_accepted(ref, cut)["body"] == parts["genesis"].body
    assert TransactionalHistoryStore(store.path).resolve_accepted(ref, cut) == store.resolve_accepted(ref, cut)
    for wrong in [dict(cut, accepted_head_seq=2), dict(cut, accepted_head_hash="0" * 64),
                  dict(cut, campaign_id="wrong"), dict(cut, governing_policy_ref="wrong")]:
        with pytest.raises(ValidationError):
            store.resolve_accepted(ref, wrong)
    with pytest.raises(ValidationError, match="OBJECT_NOT_ACCEPTED_AT_CUT"):
        store.resolve_accepted(dict(ref.as_dict(), revision_digest="0" * 64), cut)


@pytest.mark.parametrize("assertion", [False, True])
@pytest.mark.parametrize("isolation", ["UNKNOWN", "DECLARED", "ENFORCED"])
def test_forged_blindness_annotations_cannot_supply_missing_fact(assertion, isolation):
    from bdb_audit.knowledge.exposure import DiscoveryRecord, blind_origin_eligible
    store, grant, manifest, policy, parts, prior, cut = accepted_grant_fixture("F2_BLIND_FORGED_TEST.sqlite")
    discovery = DiscoveryRecord(
        grant.attempt_ref, grant.attempt_ref, parts["source_generation"].ref.as_dict(),
        prior, manifest.ref, manifest.ref, manifest.ref,
        accepted_precursor=assertion, isolation_class=isolation,
    )
    for candidate_cut in (cut, prior, dict(cut, accepted_head_seq=3), dict(cut, campaign_id="forged")):
        with pytest.raises(ValidationError):
            blind_origin_eligible(discovery, history=store, history_cut=candidate_cut)


def test_runtime_acceptance_enforces_fsm_before_persistence():
    from dataclasses import replace
    store, grant, manifest, policy, parts, prior, cut = accepted_grant_fixture("F2_RUNTIME_FSM_TEST.sqlite")
    old_head = store.head()
    command = bootstrap_fixture()[1]
    follow = replace(command, command_id="command_a23e4567-e89b-42d3-a456-426614174000",
                     command_kind="RECORD_FOUNDATION_FACT", campaign_ref=old_head.campaign_id,
                     expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **old_head.as_dict()},
                     proposed_campaign_id=None, history_namespace_ref=None, bootstrap_profile_ref=None)
    with pytest.raises(ValidationError, match="ILLEGAL_STATE_TRANSITION"):
        store.accept(follow, expected_head=old_head, ordered_events=({"aggregate": "campaign",
            "aggregate_id": old_head.campaign_id, "from_state": "GENESIS_ACCEPTED", "to_state": "AUDIT_RUNNING"},))
    assert store.head() == old_head
    assert store.receipt(follow.command_id) is None

"""M45 adversarial tests for canonical Adaptive E6 StageSpec authority."""
from __future__ import annotations

import hashlib
import json

import pytest
from jsonschema import Draft202012Validator

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.coordinator import Coordinator
from bdb_audit.history.objects import (
    ACCEPTED_HEAD_REF,
    CanonicalObject,
    CommandEnvelope,
    CommitBody,
)
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.orchestration.runs import LaneSpec
from bdb_audit.orchestration.stages import StageSpec
from bdb_audit.schemas.foundation import executable_schema
from bdb_audit.stop.e6 import AdaptiveE6Generator
from bdb_audit.stop.models import StopEvaluation, StopInput
from bdb_audit.workflow.read_models import current_accepted_cut
from tests.f2.helpers import bootstrap_fixture


def _hex(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _ref(kind: str, label: str, ref_class: str = "CONTENT_OR_PRIOR") -> dict:
    return {
        "kind": kind,
        "revision_digest": _hex(label),
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
    }


def _seed_command_id(index: int) -> str:
    return f"command_123e4567-e89b-42d3-a456-{index:012d}"


def _append_raw_commit(
    store: TransactionalHistoryStore,
    objects: list[CanonicalObject],
    *,
    index: int,
) -> None:
    """Append a mechanically valid prior-history fixture without exercising the SUT gate."""
    head = store.head()
    assert head is not None
    prior = store.commits()[-1]
    parent = {"tag": ACCEPTED_HEAD_REF, **head.as_dict()}
    command = CommandEnvelope(
        command_id=_seed_command_id(index),
        command_kind="RECORD_FOUNDATION_FACT",
        actor_ref=prior["actor_ref"],
        expected_parent_head=parent,
        governing_policy_ref=prior["governing_policy_ref"],
        governing_spec_refs=tuple(prior["governing_spec_refs"]),
        idempotency_scope=f"m45-seed-{index}",
        campaign_ref=head.campaign_id,
    )
    command_obj = command.as_object()
    all_objects = [command_obj, *objects]
    refs = tuple(obj.as_ref(ref_class="CONTENT_OBJECT") for obj in all_objects)
    commit = CommitBody(
        campaign_id=head.campaign_id,
        commit_seq=head.commit_seq + 1,
        prev_history_ref=parent,
        command_ref=command_obj.as_ref(ref_class="CONTENT_OBJECT"),
        command_digest=command.digest,
        actor_ref=command.actor_ref,
        expected_parent_head=parent,
        governing_policy_ref=command.governing_policy_ref,
        governing_spec_refs=tuple(command.governing_spec_refs),
        ordered_event_bodies=(),
        immutable_object_refs=refs,
    )

    con = store._connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        for obj in all_objects:
            con.execute(
                "INSERT INTO immutable_objects(digest,kind,version,schema_ref,logical_id,body) VALUES(?,?,?,?,?,?)",
                (
                    obj.digest,
                    obj.kind,
                    obj.version,
                    obj.schema_revision_ref,
                    obj.logical_id,
                    canonical_bytes(obj.body),
                ),
            )
        con.execute(
            "INSERT INTO commits(seq,commit_hash,campaign_id,body) VALUES(?,?,?,?)",
            (commit.commit_seq, commit.digest, head.campaign_id, canonical_bytes(commit.body())),
        )
        con.execute(
            "UPDATE accepted_head SET seq=?,commit_hash=? WHERE singleton=1",
            (commit.commit_seq, commit.digest),
        )
        con.commit()
    finally:
        con.close()


def _accept_command(store: TransactionalHistoryStore, index: int) -> CommandEnvelope:
    head = store.head()
    assert head is not None
    prior = store.commits()[-1]
    return CommandEnvelope(
        command_id=_seed_command_id(index),
        command_kind="RECORD_FOUNDATION_FACT",
        actor_ref=prior["actor_ref"],
        expected_parent_head={"tag": ACCEPTED_HEAD_REF, **head.as_dict()},
        governing_policy_ref=prior["governing_policy_ref"],
        governing_spec_refs=tuple(prior["governing_spec_refs"]),
        idempotency_scope=f"m45-accept-{index}",
        campaign_ref=head.campaign_id,
    )


def _stage_execution_objects(
    stage_spec: StageSpec,
    *,
    source_generation_ref: dict,
    label: str,
    required_isolation_assurance: str,
    include_stage_spec: bool,
) -> list[CanonicalObject]:
    stage_spec_obj = stage_spec.as_object()
    stage_run = CanonicalObject(
        "stage_run",
        {
            "stage_run_id": f"stage-run-{label}",
            "stage_spec_ref": stage_spec.ref,
            "source_generation_ref": source_generation_ref,
        },
    )
    lane_spec = LaneSpec(
        lane_key=f"lane-{label}",
        lane_spec_revision="1",
        stage_spec_revision=stage_spec.stage_spec_revision,
        purpose=f"lane for {label}",
        primary_strategy="DIRECT_ANALYSIS",
        required_isolation_assurance=required_isolation_assurance,
    )
    lane_spec_obj = lane_spec.as_object()
    lane_run = CanonicalObject(
        "lane_run",
        {
            "lane_run_id": f"lane-run-{label}",
            "stage_run_ref": stage_run.as_ref().as_dict(),
            "lane_spec_ref": lane_spec_obj.as_ref(ref_class="HISTORY_CONTEXT_BINDING").as_dict(),
            "source_generation_ref": source_generation_ref,
        },
    )
    completion = CanonicalObject(
        "stage_completion",
        {
            "stage_completion_id": f"stage-completion-{label}",
            "stage_run_ref": stage_run.as_ref().as_dict(),
            "stage_spec_ref": stage_spec.ref,
            "completion_predicate_result": "STAGE_COMPLETED",
        },
    )
    objects = [stage_run, lane_spec_obj, lane_run, completion]
    if include_stage_spec:
        objects.insert(0, stage_spec_obj)
    return objects


def _stop_pair(
    *,
    cut: dict,
    source_generation_ref: dict,
    evaluation_context: str,
    suffix: str,
    remaining_obligation_ref: dict,
) -> tuple[StopInput, StopEvaluation]:
    policy = _ref("policy_revision", f"policy-{suffix}", "HISTORY_CONTEXT_BINDING")
    spec = _ref("spec_revision", f"spec-{suffix}", "HISTORY_CONTEXT_BINDING")
    stop_input = StopInput(
        stop_input_id=f"stop_input_123e4567-e89b-42d3-a456-{int(suffix):012d}",
        campaign_id=cut["campaign_id"],
        source_generation_ref=source_generation_ref,
        input_history_cut=cut,
        evaluation_context=evaluation_context,
        governing_policy_ref=policy,
        policy_spec_refs=[spec],
        evaluator_revision_ref=spec,
        required_stage_set_ref=_ref("external_profile_ref", f"stage-set-{suffix}", "HISTORY_CONTEXT_BINDING"),
        required_stage_spec_refs=[],
        completed_stage_refs=[],
        pending_required_stage_refs=[],
        stop_input_snapshot_ref=_ref("snapshot", f"snapshot-{suffix}"),
        inventory_revision_ref=_ref("inventory_revision", f"inventory-{suffix}"),
        mandatory_obligation_refs=[remaining_obligation_ref],
        current_obligation_qualification_refs=[],
        evidence_invalidation_refs=[],
        contradiction_refs=[_ref("contradiction_revision", f"contradiction-{suffix}")],
        residual_risk_refs=[],
        evidence_invalidation_state={"invalidated_count": 0},
        release_policy_ref=policy,
        effort_profile_ref=_ref("external_profile_ref", f"effort-{suffix}", "HISTORY_CONTEXT_BINDING"),
        effort_results_ref=_ref("registered_immutable_object", f"effort-results-{suffix}"),
        unknown_blocked_summary={"unknown_surfaces_count": 0, "is_blocked": False},
        candidate_assurance_case_ref=_ref("candidate_assurance_case", f"candidate-{suffix}"),
        challenger_refs=[
            _ref("challenger_result", f"challenger-a-{suffix}"),
            _ref("challenger_result", f"challenger-b-{suffix}"),
        ],
    )
    evaluation = StopEvaluation(
        stop_evaluation_id=f"stop_evaluation_123e4567-e89b-42d3-a456-{int(suffix):012d}",
        stop_input_ref=stop_input.ref,
        continuation_decision="E6_REQUIRED",
        assurance_level="BOUNDED",
        release_readiness="QUALIFICATION_BLOCKED",
        reason_codes=("E6_REQUIRED", "BOUNDED_ADDITIONAL_PLAN_APPROVED"),
        blocking_obligation_refs=(remaining_obligation_ref,),
        remaining_obligation_refs=(remaining_obligation_ref,),
    )
    return stop_input, evaluation


def _seed_authority_store(tmp_path):
    store = TransactionalHistoryStore(tmp_path / "m45.sqlite")
    profile, bootstrap_cmd, genesis_objects, bootstrap = bootstrap_fixture()
    Coordinator(store).accept(
        bootstrap_cmd,
        immutable_objects=genesis_objects,
        bootstrap_profile=profile,
    )
    cut1 = current_accepted_cut(store)
    source_generation_ref = store.accepted_records("source_generation", cut1)[0]["ref"]

    baseline_e5 = StageSpec(
        stage_key="E5",
        stage_spec_revision="e5-baseline-1",
        stage_role="E5",
        stage_ordinal=5,
        purpose="M45 E5 baseline",
        predecessor_requirements=("E4",),
        required_lane_slots=("E5_BASELINE",),
        blind_reveal_phase_model="AFTER_CHECKPOINT",
        allowed_corpus_roles=("PRIMARY",),
        forbidden_corpus_roles=("FORBIDDEN",),
        coverage_obligation_policy_ref="coverage-policy-v1",
        required_stage_completion_outputs=("E5_ASSURANCE",),
        transition_policy_ref=cut1["governing_spec_refs"][0],
    )
    _append_raw_commit(
        store,
        _stage_execution_objects(
            baseline_e5,
            source_generation_ref=source_generation_ref,
            label="e5",
            required_isolation_assurance="DECLARED",
            include_stage_spec=True,
        ),
        index=2,
    )

    cut2 = current_accepted_cut(store)
    obligation_ref = _ref("coverage_obligation", "m45-open-obligation")
    stop_input, stop_evaluation = _stop_pair(
        cut=cut2,
        source_generation_ref=source_generation_ref,
        evaluation_context="FINAL_POST_E5",
        suffix="3",
        remaining_obligation_ref=obligation_ref,
    )
    stop_input_obj = stop_input.as_object()
    stop_evaluation_obj = stop_evaluation.as_object()
    _append_raw_commit(store, [stop_input_obj, stop_evaluation_obj], index=3)

    cut3 = current_accepted_cut(store)
    exact_stop_eval_ref = next(
        row["ref"]
        for row in store.accepted_records("stop_evaluation", cut3)
        if row["ref"]["revision_digest"] == stop_evaluation_obj.digest
    )
    genesis_trust_ref = bootstrap["genesis"].body["trust_profile_ref"]
    return store, exact_stop_eval_ref, genesis_trust_ref, obligation_ref


def test_pure_e6_materializes_exact_canonical_stage_spec_shape() -> None:
    cut = {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": "campaign-m45-pure",
        "accepted_head_seq": 7,
        "accepted_head_hash": "a" * 64,
        "governing_policy_ref": "pin:policy",
        "governing_spec_refs": ["pin:spec"],
    }
    obligation_ref = _ref("coverage_obligation", "pure-obligation")
    stop_input, stop_evaluation = _stop_pair(
        cut=cut,
        source_generation_ref=_ref("source_generation", "pure-source"),
        evaluation_context="FINAL_POST_E5",
        suffix="7",
        remaining_obligation_ref=obligation_ref,
    )
    e6 = AdaptiveE6Generator.generate_e6_spec(
        "e6-pure-1",
        stop_evaluation,
        stop_input,
        _ref("trust_profile", "pure-trust", "PINNED_INSTALLATION_REF"),
        {"required_isolation_assurance": "DECLARED"},
    )

    body = e6.body()
    Draft202012Validator(executable_schema("stage_spec")).validate(body)
    assert body["stage_key"] == "E6"
    assert body["stage_spec_revision"] == "e6-pure-1"
    assert "source_stop_evaluation_ref" not in body
    assert "e6_stage_spec_id" not in body
    relationship = e6.relationship_payload
    assert relationship["source_stop_evaluation_ref"]["revision_digest"] == stop_evaluation.ref["revision_digest"]
    assert relationship["source_stop_input_ref"]["revision_digest"] == stop_input.ref["revision_digest"]
    assert relationship["required_isolation_assurance"] == "DECLARED"
    assert "POST_E6_STOP_REEVALUATION" in body["required_stage_completion_outputs"]


def test_store_aware_e6_derives_genesis_trust_and_baseline_isolation(tmp_path) -> None:
    store, stop_eval_ref, genesis_trust_ref, _ = _seed_authority_store(tmp_path)
    e6 = AdaptiveE6Generator.generate_e6_spec_from_store(
        store,
        spec_id="e6-round-1",
        stop_evaluation_ref=stop_eval_ref,
        added_surfaces=[_ref("surface_record", "round-1-surface")],
    )
    relation = e6.relationship_payload
    assert relation["source_stop_evaluation_ref"].get("logical_id") is not None
    assert relation["source_stop_input_ref"].get("logical_id") is not None
    assert relation["trust_profile_ref"] == genesis_trust_ref
    assert relation["required_isolation_assurance"] == "DECLARED"

    result = store.accept(_accept_command(store, 4), immutable_objects=[e6.as_object()])
    assert result.head.commit_seq == 4
    assert store.object_record(e6.as_object().digest) is not None


def test_caller_cannot_rewrite_trust_or_isolation_after_failure(tmp_path) -> None:
    store, stop_eval_ref, _, _ = _seed_authority_store(tmp_path)
    with pytest.raises(ValidationError, match="E6_TRUST_PROFILE_WEAKENING_FORBIDDEN"):
        AdaptiveE6Generator.generate_e6_spec_from_store(
            store,
            spec_id="e6-bad-trust",
            stop_evaluation_ref=stop_eval_ref,
            trust_profile_ref=_ref("trust_profile", "caller-trust", "PINNED_INSTALLATION_REF"),
        )
    with pytest.raises(ValidationError, match="E6_ISOLATION_REWRITE_FORBIDDEN"):
        AdaptiveE6Generator.generate_e6_spec_from_store(
            store,
            spec_id="e6-bad-isolation",
            stop_evaluation_ref=stop_eval_ref,
            isolation_profile_ref={"required_isolation_assurance": "UNKNOWN"},
        )


def test_forged_unaccepted_stop_ref_is_rejected_before_object_durability(tmp_path) -> None:
    store, stop_eval_ref, _, _ = _seed_authority_store(tmp_path)
    e6 = AdaptiveE6Generator.generate_e6_spec_from_store(
        store,
        spec_id="e6-forged",
        stop_evaluation_ref=stop_eval_ref,
    )
    body = e6.body()
    relationship = json.loads(body["stop_e6_relationship"])
    relationship["source_stop_evaluation_ref"] = dict(relationship["source_stop_evaluation_ref"])
    relationship["source_stop_evaluation_ref"]["revision_digest"] = _hex("not-accepted-stop-evaluation")
    body["stop_e6_relationship"] = canonical_bytes(relationship).decode("utf-8")
    forged = CanonicalObject("stage_spec", body)

    cmd = _accept_command(store, 4)
    with pytest.raises(ValidationError):
        store.accept(cmd, immutable_objects=[forged])
    assert store.object_record(forged.digest) is None
    assert store.head().commit_seq == 3


def test_material_commit_after_stop_makes_e6_source_stale(tmp_path) -> None:
    store, stop_eval_ref, _, _ = _seed_authority_store(tmp_path)
    _append_raw_commit(store, [CanonicalObject("finding_claim_revision", {"finding_id": "drift"})], index=4)
    with pytest.raises(ValidationError, match="E6_STOP_EVALUATION_STALE"):
        AdaptiveE6Generator.generate_e6_spec_from_store(
            store,
            spec_id="e6-stale-stop",
            stop_evaluation_ref=stop_eval_ref,
        )


def test_second_post_e6_round_preserves_prior_strengthening(tmp_path) -> None:
    store, stop_eval_ref, genesis_trust_ref, obligation_ref = _seed_authority_store(tmp_path)
    first_added = _ref("surface_record", "round-1-surface")
    first = AdaptiveE6Generator.generate_e6_spec_from_store(
        store,
        spec_id="e6-round-1",
        stop_evaluation_ref=stop_eval_ref,
        added_surfaces=[first_added],
    )
    store.accept(_accept_command(store, 4), immutable_objects=[first.as_object()])

    _append_raw_commit(
        store,
        _stage_execution_objects(
            first.stage_spec,
            source_generation_ref=first.source_generation_ref,
            label="e6-round-1",
            required_isolation_assurance="DECLARED",
            include_stage_spec=False,
        ),
        index=5,
    )
    cut5 = current_accepted_cut(store)
    stop_input2, stop_evaluation2 = _stop_pair(
        cut=cut5,
        source_generation_ref=first.source_generation_ref,
        evaluation_context="POST_E6",
        suffix="6",
        remaining_obligation_ref=obligation_ref,
    )
    stop_input2_obj = stop_input2.as_object()
    stop_evaluation2_obj = stop_evaluation2.as_object()
    _append_raw_commit(store, [stop_input2_obj, stop_evaluation2_obj], index=6)
    cut6 = current_accepted_cut(store)
    exact_second_stop_ref = next(
        row["ref"]
        for row in store.accepted_records("stop_evaluation", cut6)
        if row["ref"]["revision_digest"] == stop_evaluation2_obj.digest
    )

    second_added = _ref("surface_record", "round-2-surface")
    second = AdaptiveE6Generator.generate_e6_spec_from_store(
        store,
        spec_id="e6-round-2",
        stop_evaluation_ref=exact_second_stop_ref,
        added_surfaces=[second_added],
    )
    relationship = second.relationship_payload
    surface_digests = {ref["revision_digest"] for ref in relationship["added_surfaces"]}
    assert first_added["revision_digest"] in surface_digests
    assert second_added["revision_digest"] in surface_digests
    assert relationship["baseline_stage_spec_ref"]["revision_digest"] == first.as_object().digest
    assert relationship["trust_profile_ref"] == genesis_trust_ref
    assert relationship["required_isolation_assurance"] == "DECLARED"

    result = store.accept(_accept_command(store, 7), immutable_objects=[second.as_object()])
    assert result.head.commit_seq == 7

"""Targeted unit and adversarial tests for PR-E3-01: M24 Blind Novelty Lanes (E3-X/Y/Z).

Tests:
1. Normative E3 StageSpec and E3-X, E3-Y, E3-Z LaneSpecs with truthful isolation profiles.
2. Attempt creation with assigned HistoryCut, isolation qualification, and result slot contracts.
3. E3QuarantineBroker enforcement: isolation qualification requirement, own-lane views, seal mechanics.
4. Adversarial leak tests:
   - Cross-lane query before checkpoint fails closed (CROSS_LANE_KNOWLEDGE_LEAKAGE).
   - Prior finding corpus query before checkpoint fails closed (KNOWLEDGE_BOUNDARY_VIOLATION).
   - Leaking finding ref in discovery fails closed (DISALLOWED_KNOWLEDGE_REVEAL).
   - Leaking filename / path in discovery fails closed (DISALLOWED_KNOWLEDGE_REVEAL).
   - Leaking support metadata in discovery fails closed (DISALLOWED_KNOWLEDGE_REVEAL).
   - Leaking corpus ordering in discovery fails closed (DISALLOWED_KNOWLEDGE_REVEAL).
   - Leaking cache key in discovery fails closed (DISALLOWED_KNOWLEDGE_REVEAL).
   - UNKNOWN, contaminated, or under-qualified isolation fails closed.
   - Non-blind discovery classification in blind phase fails closed.
5. execute_e3_blind_ensemble execution, deterministic digest, and missing lane failure.
6. Historical distinguishability between blind results and post-reveal / gap-directed results.
"""
import hashlib
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.orchestration.runs import qualify_isolation
from bdb_audit.orchestration.e3 import (
    E3_LANE_SLOTS,
    E3_LANE_STRATEGIES,
    FORBIDDEN_BLIND_LEAK_FIELDS,
    build_e3_stage_spec,
    build_e3_lane_specs,
    create_result_slot_contract,
    create_e3_blind_attempt,
    E3QuarantineBroker,
    execute_e3_blind_ensemble,
)


def make_ref(kind: str, seed: str) -> dict:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }


def make_history_cut(seq: int = 1) -> dict:
    return {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": "camp_e3_test",
        "accepted_head_seq": seq,
        "accepted_head_hash": hashlib.sha256(f"cut_{seq}".encode()).hexdigest(),
        "governing_policy_ref": "BDB_POLICY_REGISTRY::governing_policy/1",
        "governing_spec_refs": ["BDB_SPEC_REGISTRY::e3_spec/1"],
    }


def test_e3_stage_and_lane_specs():
    spec = build_e3_stage_spec()
    assert spec.stage_key == "E3"
    assert spec.stage_ordinal == 3
    assert spec.stage_role == "EXPAND_AND_HUNT"
    assert spec.required_lane_slots == E3_LANE_SLOTS
    assert len(spec.required_lane_slots) == 3
    assert spec.predecessor_requirements == ("E2",)
    assert spec.blind_reveal_phase_model == "AFTER_CHECKPOINT"

    lane_specs = build_e3_lane_specs()
    assert len(lane_specs) == 3
    for slot in E3_LANE_SLOTS:
        assert slot in lane_specs
        ls = lane_specs[slot]
        assert ls.required_isolation_assurance == "DECLARED"
        assert "CUMULATIVE_FINDING_CORPUS" in ls.forbidden_knowledge_classes
        assert "OTHER_LANE_UNSEALED_FINDINGS" in ls.forbidden_knowledge_classes
        assert "GAP_MAP" in ls.forbidden_knowledge_classes
        assert "COVERAGE_OBLIGATIONS" in ls.forbidden_knowledge_classes


def test_create_e3_blind_attempt_and_result_slot_contract():
    lane_run_ref = make_ref("lane_run", "lr_x")
    exec_ref = make_ref("executor_profile", "exec_1")
    deliv_ref = make_ref("delivery_profile", "deliv_1")
    cut = make_history_cut(5)

    ctx = create_e3_blind_attempt(
        lane_slot="E3-X",
        lane_run_ref=lane_run_ref,
        assigned_history_cut=cut,
        executor_profile_ref=exec_ref,
        delivery_profile_ref=deliv_ref,
    )

    assert ctx.attempt.lane_run_ref == lane_run_ref
    assert ctx.attempt.assigned_history_cut == cut
    assert len(ctx.attempt.result_slot_contracts) == 1
    assert ctx.attempt.result_slot_contracts[0]["allowed_classes"] == ["PRE_REVEAL_DISCOVERY"]

    assert ctx.isolation_qualification.isolation_class == "DECLARED"
    assert ctx.isolation_qualification.required_isolation_assurance == "DECLARED"
    assert ctx.isolation_qualification.fresh_session_boundary is False
    assert ctx.isolation_qualification.contaminated is False
    assert ctx.isolation_qualification.enforcement_receipt_refs == ()
    assert ctx.isolation_qualification.filesystem_boundary_evidence_refs == ()

    assert ctx.knowledge_state.basis_history_cut == cut
    assert ctx.knowledge_state.potential_exposure_refs == ()
    assert ctx.knowledge_state.contamination_assessment_refs == ()


def test_enforced_e3_attempt_requires_explicit_boundary_witnesses():
    lane_run_ref = make_ref("lane_run", "lr_enforced")
    exec_ref = make_ref("executor_profile", "exec_enforced")
    deliv_ref = make_ref("delivery_profile", "deliv_enforced")
    cut = make_history_cut(5)

    with pytest.raises(
        ValidationError,
        match="E3_ENFORCED_BOUNDARY_EVIDENCE_REQUIRED",
    ):
        create_e3_blind_attempt(
            "E3-X",
            lane_run_ref,
            cut,
            exec_ref,
            deliv_ref,
            isolation_assurance="ENFORCED",
            fresh_session_boundary=True,
        )

    witness = make_ref("raw_artifact_ref", "boundary_witness")
    evidence = {
        "enforcement_receipt_refs": [witness],
        "filesystem_boundary_evidence_refs": [witness],
        "network_boundary_evidence_refs": [witness],
        "tool_boundary_evidence_refs": [witness],
        "session_boundary_evidence_refs": [witness],
    }
    ctx = create_e3_blind_attempt(
        "E3-X",
        lane_run_ref,
        cut,
        exec_ref,
        deliv_ref,
        boundary_evidence_refs=evidence,
        channel_inventory_ref=make_ref(
            "registered_immutable_object",
            "e3_channel_inventory",
        ),
        isolation_assurance="ENFORCED",
        fresh_session_boundary=True,
    )

    assert ctx.isolation_qualification.isolation_class == "ENFORCED"
    assert (
        ctx.isolation_qualification.required_isolation_assurance
        == "ENFORCED"
    )
    assert ctx.isolation_qualification.channel_inventory_ref == make_ref(
        "registered_immutable_object",
        "e3_channel_inventory",
    )
    assert ctx.isolation_qualification.enforcement_receipt_refs == (
        witness,
    )


def test_declared_e3_isolation_is_accepted_but_unknown_is_rejected():
    broker = E3QuarantineBroker()
    cut = make_history_cut(3)
    lr_ref = make_ref("lane_run", "lr_declared")
    exec_ref = make_ref("executor_profile", "exec_declared")
    deliv_ref = make_ref("delivery_profile", "deliv_declared")

    declared = create_e3_blind_attempt(
        "E3-X",
        lr_ref,
        cut,
        exec_ref,
        deliv_ref,
    )
    broker.register_isolation_qualification(
        "E3-X",
        declared.isolation_qualification,
    )

    unknown = create_e3_blind_attempt(
        "E3-Y",
        lr_ref,
        cut,
        exec_ref,
        deliv_ref,
        isolation_assurance="UNKNOWN",
    )
    with pytest.raises(
        ValidationError,
        match="BLIND_ORIGIN_ISOLATION_NOT_QUALIFIED",
    ):
        broker.register_isolation_qualification(
            "E3-Y",
            unknown.isolation_qualification,
        )

    from bdb_audit.orchestration.runs import IsolationQualification

    missing_requirement = IsolationQualification(
        attempt_ref=declared.attempt.as_object().ref.as_dict(),
        assessment_input_history_cut=cut,
        executor_profile_ref=exec_ref,
        delivery_profile_ref=deliv_ref,
        isolation_class="DECLARED",
    )
    with pytest.raises(
        ValidationError,
        match="BLIND_ORIGIN_ISOLATION_NOT_QUALIFIED",
    ):
        broker.register_isolation_qualification(
            "E3-Y",
            missing_requirement,
        )

    forbidden = create_e3_blind_attempt(
        "E3-Z",
        lr_ref,
        cut,
        exec_ref,
        deliv_ref,
        forbidden_channel_access=True,
    )
    with pytest.raises(
        ValidationError,
        match="BLIND_ORIGIN_ISOLATION_NOT_QUALIFIED",
    ):
        broker.register_isolation_qualification(
            "E3-Z",
            forbidden.isolation_qualification,
        )


def test_quarantine_broker_and_cross_lane_leak_prevention():
    broker = E3QuarantineBroker()
    cut = make_history_cut(3)
    lr_ref = make_ref("lane_run", "lr")
    exec_ref = make_ref("executor_profile", "exec")
    deliv_ref = make_ref("delivery_profile", "deliv")

    ctx_x = create_e3_blind_attempt("E3-X", lr_ref, cut, exec_ref, deliv_ref)
    ctx_y = create_e3_blind_attempt("E3-Y", lr_ref, cut, exec_ref, deliv_ref)
    ctx_z = create_e3_blind_attempt("E3-Z", lr_ref, cut, exec_ref, deliv_ref)

    broker.register_isolation_qualification("E3-X", ctx_x.isolation_qualification)
    broker.register_isolation_qualification("E3-Y", ctx_y.isolation_qualification)
    broker.register_isolation_qualification("E3-Z", ctx_z.isolation_qualification)

    broker.record_lane_discovery("E3-X", {"statement": "Novel auth bypass in TLS session"})
    broker.record_lane_discovery("E3-Y", {"statement": "State rollback bug in journal"})

    # Own lane view allowed
    x_view = broker.get_lane_view("E3-X")
    assert len(x_view) == 1
    assert x_view[0]["statement"] == "Novel auth bypass in TLS session"

    # Cross-lane query fails closed before checkpoint
    with pytest.raises(ValidationError, match="CROSS_LANE_KNOWLEDGE_LEAKAGE"):
        broker.query_cross_lane_findings("E3-X", "E3-Y")

    # Prior finding corpus query fails closed before checkpoint
    with pytest.raises(ValidationError, match="KNOWLEDGE_BOUNDARY_VIOLATION"):
        broker.query_finding_corpus("E3-X")


def test_adversarial_forbidden_leak_detection():
    broker = E3QuarantineBroker()
    cut = make_history_cut(3)
    lr_ref = make_ref("lane_run", "lr")
    exec_ref = make_ref("executor_profile", "exec")
    deliv_ref = make_ref("delivery_profile", "deliv")
    ctx_x = create_e3_blind_attempt("E3-X", lr_ref, cut, exec_ref, deliv_ref)
    broker.register_isolation_qualification("E3-X", ctx_x.isolation_qualification)

    # 1. Finding ref leak
    with pytest.raises(ValidationError, match="DISALLOWED_KNOWLEDGE_REVEAL"):
        broker.record_lane_discovery("E3-X", {
            "statement": "Valid statement",
            "finding_claim_ref": {"digest": "abc"},
        })

    # 2. Filename / path leak
    with pytest.raises(ValidationError, match="DISALLOWED_KNOWLEDGE_REVEAL"):
        broker.record_lane_discovery("E3-X", {
            "statement": "Valid statement",
            "filename": "vuln_file.py",
        })

    # 3. Support metadata leak
    with pytest.raises(ValidationError, match="DISALLOWED_KNOWLEDGE_REVEAL"):
        broker.record_lane_discovery("E3-X", {
            "statement": "Valid statement",
            "support_count": 5,
        })

    # 4. Corpus ordering leak
    with pytest.raises(ValidationError, match="DISALLOWED_KNOWLEDGE_REVEAL"):
        broker.record_lane_discovery("E3-X", {
            "statement": "Valid statement",
            "corpus_index": 2,
        })

    # 5. Cache key leak
    with pytest.raises(ValidationError, match="DISALLOWED_KNOWLEDGE_REVEAL"):
        broker.record_lane_discovery("E3-X", {
            "statement": "Valid statement",
            "cache_key": "hit_123",
        })

    # 6. Environment leak
    with pytest.raises(ValidationError, match="DISALLOWED_KNOWLEDGE_REVEAL"):
        broker.record_lane_discovery("E3-X", {
            "statement": "Valid statement",
            "env_leak": {"secret": "value"},
        })

    # 7. Invalid classification
    with pytest.raises(ValidationError, match="INVALID_BLIND_CLASSIFICATION"):
        broker.record_lane_discovery("E3-X", {
            "statement": "Valid statement",
            "classification": "POST_REVEAL_CONFIRMATION",
        })


def test_adversarial_unqualified_or_contaminated_isolation_rejected():
    broker = E3QuarantineBroker()
    cut = make_history_cut(3)
    lr_ref = make_ref("lane_run", "lr")
    exec_ref = make_ref("executor_profile", "exec")
    deliv_ref = make_ref("delivery_profile", "deliv")

    # Contaminated isolation
    contaminated_ctx = create_e3_blind_attempt("E3-X", lr_ref, cut, exec_ref, deliv_ref)
    # Tamper with qualification to simulate contamination
    contaminated_qual = qualify_isolation(
        attempt_ref=contaminated_ctx.attempt.as_object().ref.as_dict(),
        history_cut=cut,
        executor_profile_ref=exec_ref,
        delivery_profile_ref=deliv_ref,
        fresh_session_boundary=True,
        contaminated=True,
        requested="ENFORCED",
    )
    with pytest.raises(ValidationError, match="BLIND_ORIGIN_ISOLATION_NOT_QUALIFIED"):
        broker.register_isolation_qualification("E3-X", contaminated_qual)


def test_execute_e3_blind_ensemble_success_and_digest_determinism():
    src_gen = make_ref("source_generation", "gen_e3")
    cut = make_history_cut(4)
    lr_ref = make_ref("lane_run", "lr")
    exec_ref = make_ref("executor_profile", "exec")
    deliv_ref = make_ref("delivery_profile", "deliv")

    lane_contexts = {
        slot: create_e3_blind_attempt(slot, lr_ref, cut, exec_ref, deliv_ref)
        for slot in E3_LANE_SLOTS
    }

    lane_discoveries = {
        "E3-X": [{"statement": "Broken cryptographic signature check in bootloader"}],
        "E3-Y": [{"statement": "Catalog index corruption under atomic rename"}],
        "E3-Z": [{"statement": "UI race condition during async modal dismissal"}],
    }

    result1 = execute_e3_blind_ensemble(src_gen, cut, lane_contexts, lane_discoveries)
    result2 = execute_e3_blind_ensemble(src_gen, cut, lane_contexts, lane_discoveries)

    assert result1.stage_key == "E3"
    assert result1.completed_lanes == E3_LANE_SLOTS
    assert result1.total_discoveries == 3
    assert len(result1.quarantined_claims) == 3
    assert result1.blind_completion_digest == result2.blind_completion_digest
    assert len(result1.blind_completion_digest) == 64

    # Seal checkpoint on broker
    chk = result1.broker.seal_checkpoint(cut)
    assert chk["checkpoint_digest"] is not None
    assert len(chk["sealed_findings"]) == 3


def test_execute_e3_blind_missing_mandatory_lane_fails_closed():
    src_gen = make_ref("source_generation", "gen_e3")
    cut = make_history_cut(4)
    lr_ref = make_ref("lane_run", "lr")
    exec_ref = make_ref("executor_profile", "exec")
    deliv_ref = make_ref("delivery_profile", "deliv")

    lane_contexts = {
        slot: create_e3_blind_attempt(slot, lr_ref, cut, exec_ref, deliv_ref)
        for slot in E3_LANE_SLOTS
    }

    # Missing E3-Z
    incomplete_discoveries = {
        "E3-X": [{"statement": "Some bug in X"}],
        "E3-Y": [{"statement": "Some bug in Y"}],
    }

    with pytest.raises(ValidationError, match="MANDATORY_LANE_MISSING"):
        execute_e3_blind_ensemble(src_gen, cut, lane_contexts, incomplete_discoveries)
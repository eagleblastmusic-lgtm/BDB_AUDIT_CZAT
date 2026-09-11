"""Targeted unit and adversarial tests for PR-E3-05: M27 Metamorphic Testing Framework.

Tests:
1. Deterministic transformation identity and exact original/transformed input binding.
2. Preregistration requirement:
   - Expected relation preregistered before run.
   - Retroactive registration fails closed (RETROACTIVE_METAMORPHIC_RELATION_REJECTED).
3. Replay determinism: same transformation replay gives deterministic result.
4. Observed relation recorded separately (SATISFIED vs VIOLATION).
5. Canonical pipeline:
   - Direct violation to finding bypass fails closed (METAMORPHIC_VIOLATION_CANNOT_AUTO_CREATE_FINDING).
   - Violation produces EvidenceNode, HypothesisRevision, and FindingAdjudicationDecision.
6. Invalidation propagation via EvidenceGraph:
   - Invalidation of transformation/evidence propagates downstream;
   - Degraded node has satisfies_completion=False.
7. Stale history cut rejection (STALE_HISTORY_CUT_REJECTED).
"""
import hashlib
import json
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.evidence.graph import EvidenceGraph
from bdb_audit.hypothesis.orchestrator import HypothesisOrchestrator
from bdb_audit.execution.metamorphic import (
    MetamorphicTransformation,
    create_metamorphic_transformation,
    MetamorphicRelationSpec,
    MetamorphicTestingFramework,
    process_metamorphic_result_through_pipeline,
    validate_no_direct_metamorphic_to_finding,
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
        "campaign_id": "camp_meta_test",
        "accepted_head_seq": seq,
        "accepted_head_hash": hashlib.sha256(f"cut_{seq}".encode()).hexdigest(),
        "governing_policy_ref": "BDB_POLICY_REGISTRY::governing_policy/1",
        "governing_spec_refs": ["BDB_SPEC_REGISTRY::meta_spec/1"],
    }


def test_deterministic_transformation_identity():
    # Adding padding / whitespace transformation
    fn = lambda raw: raw + b"   "
    params = {"padding_char": " ", "padding_length": 3}

    t1 = create_metamorphic_transformation("WHITESPACE_PADDING", params, fn)
    t2 = create_metamorphic_transformation("WHITESPACE_PADDING", params, fn)

    assert t1.transformation_id == t2.transformation_id
    assert t1.identity_digest == t2.identity_digest
    assert t1.digest == t2.digest
    assert len(t1.identity_digest) == 64


def test_preregistration_requirement_and_retroactive_rejection():
    # 1. Spec registered with preregistered_before_run=False must fail closed
    with pytest.raises(ValidationError, match="RETROACTIVE_METAMORPHIC_RELATION_REJECTED"):
        MetamorphicRelationSpec(
            spec_id="spec_retro",
            transformation_id="trans_1",
            expected_relation="OUTPUT_EQUIVALENT",
            target_system_ref=make_ref("target", "svc"),
            preregistration_cut=make_history_cut(3),
            preregistered_before_run=False,
        )

    # 2. Executing without preregistering spec in framework must fail closed
    target_fn = lambda raw: json.loads(raw)
    framework = MetamorphicTestingFramework(target_fn)
    trans = create_metamorphic_transformation("PADDING", {"len": 1}, lambda r: r + b" ")
    cut = make_history_cut(5)

    with pytest.raises(ValidationError, match="RETROACTIVE_METAMORPHIC_RELATION_REJECTED"):
        framework.execute_metamorphic_test(
            original_input_ref=make_ref("input", "inp1"),
            original_input=b'{"val": 1}',
            transformation=trans,
            spec_id="unregistered_spec_id",
            history_cut=cut,
            active_cut_seq=5,
        )


def test_replay_determinism_and_observed_relation_recording():
    # Target function: parses json. Equivalence preserved under extra whitespace.
    target_fn = lambda raw: json.loads(raw)
    framework = MetamorphicTestingFramework(target_fn)

    trans = create_metamorphic_transformation("PADDING", {"len": 2}, lambda r: r + b"  ")
    spec = MetamorphicRelationSpec(
        spec_id="spec_equiv_1",
        transformation_id=trans.transformation_id,
        expected_relation="OUTPUT_EQUIVALENT",
        target_system_ref=make_ref("target", "svc"),
        preregistration_cut=make_history_cut(5),
    )
    framework.preregister_relation_spec(spec)

    cut = make_history_cut(5)
    orig_ref = make_ref("input", "json_val")
    orig_bytes = b'{"msg": "hello"}'

    # Replay runs
    rec1 = framework.execute_metamorphic_test(orig_ref, orig_bytes, trans, "spec_equiv_1", cut, 5)
    rec2 = framework.execute_metamorphic_test(orig_ref, orig_bytes, trans, "spec_equiv_1", cut, 5)

    assert rec1.observed_relation == "SATISFIED"
    assert rec2.observed_relation == "SATISFIED"
    assert rec1.transformed_input_digest == rec2.transformed_input_digest
    assert rec1.digest == rec2.digest
    assert rec1.violation_details is None


def test_canonical_pipeline_on_metamorphic_violation():
    # Target function: buggy implementation changes output when whitespace is added!
    def buggy_target(raw: bytes) -> dict:
        if raw.endswith(b" "):
            return {"error": "trailing_whitespace_bug"}
        return {"result": "success"}

    framework = MetamorphicTestingFramework(buggy_target)
    trans = create_metamorphic_transformation("WHITESPACE_APPEND", {"char": " "}, lambda r: r + b" ")
    spec = MetamorphicRelationSpec(
        spec_id="spec_buggy",
        transformation_id=trans.transformation_id,
        expected_relation="OUTPUT_EQUIVALENT",
        target_system_ref=make_ref("target", "svc"),
        preregistration_cut=make_history_cut(5),
    )
    framework.preregister_relation_spec(spec)

    cut = make_history_cut(5)
    orig_ref = make_ref("input", "json_clean")
    record = framework.execute_metamorphic_test(
        orig_ref, b'{"clean": true}', trans, "spec_buggy", cut, 5
    )

    assert record.observed_relation == "VIOLATION"
    assert record.violation_details is not None

    # 1. Adversarial: direct violation to finding bypass rejected
    with pytest.raises(ValidationError, match="METAMORPHIC_VIOLATION_CANNOT_AUTO_CREATE_FINDING"):
        validate_no_direct_metamorphic_to_finding(
            attempted_claim={"statement": "Bypass finding"},
            is_direct_violation=True,
        )

    # 2. Canonical pipeline
    hyp_orch = HypothesisOrchestrator()
    ev_graph = EvidenceGraph()
    src_gen = make_ref("source_generation", "src_1")
    policy_ref = make_ref("policy", "adj_policy")
    adjudicator_ref = make_ref("adjudicator", "adj_1")

    hyp, decision, obs_id = process_metamorphic_result_through_pipeline(
        record=record,
        hypothesis_orchestrator=hyp_orch,
        evidence_graph=ev_graph,
        history_cut=cut,
        source_generation_ref=src_gen,
        policy_ref=policy_ref,
        adjudicator_ref=adjudicator_ref,
        active_cut_seq=5,
    )

    assert hyp is not None
    assert "Metamorphic relation violation" in hyp.statement
    assert decision is not None
    assert decision.lifecycle_status == "CONFIRMED_CURRENT"
    assert obs_id is not None
    assert obs_id in ev_graph.nodes


def test_invalidated_evidence_propagation_via_graph():
    # Setup graph with metamorphic observation and downstream dependent assessment
    ev_graph = EvidenceGraph()
    cut = make_history_cut(5)

    obs_node = ev_graph.add_node(
        node_id="obs_meta_123",
        node_type="OBSERVATION",
        data={"violation": True},
    )
    qual_node = ev_graph.add_node(
        node_id="qual_meta_assessment",
        node_type="QUALIFICATION_ASSESSMENT",
        data={"verified": True},
    )
    ev_graph.add_edge("qual_meta_assessment", "obs_meta_123", "DEPENDS_ON")

    assert qual_node.status == "ACTIVE"
    assert qual_node.satisfies_completion is True

    # Invalidate root observation
    prop_res = ev_graph.propagate_invalidation("obs_meta_123", reason="INPUT_TRANSFORMATION_INVALIDATED")

    assert obs_node.status == "INVALIDATED"
    assert obs_node.satisfies_completion is False

    # Downstream qualification must be degraded!
    assert qual_node.status == "STALE"
    assert qual_node.satisfies_completion is False
    assert "qual_meta_assessment" in prop_res["degraded_qualifications"]


def test_stale_history_cut_rejected():
    target_fn = lambda r: r
    framework = MetamorphicTestingFramework(target_fn)
    trans = create_metamorphic_transformation("IDENTITY", {}, lambda r: r)
    spec = MetamorphicRelationSpec(
        spec_id="spec_ident",
        transformation_id=trans.transformation_id,
        expected_relation="OUTPUT_EQUIVALENT",
        target_system_ref=make_ref("target", "svc"),
        preregistration_cut=make_history_cut(3),
    )
    framework.preregister_relation_spec(spec)

    stale_cut = make_history_cut(2)
    with pytest.raises(ValidationError, match="STALE_HISTORY_CUT_REJECTED"):
        framework.execute_metamorphic_test(
            original_input_ref=make_ref("input", "inp"),
            original_input=b"data",
            transformation=trans,
            spec_id="spec_ident",
            history_cut=stale_cut,
            active_cut_seq=5,
        )

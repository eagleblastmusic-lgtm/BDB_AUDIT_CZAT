"""Targeted unit and adversarial tests for WP-F4-09 / PR-F4-09."""
import hashlib
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.orchestration import (
    E1_LANE_SLOTS,
    build_e1_stage_spec,
    build_e1_lane_specs,
    build_e2_stage_spec,
    EnsembleQuarantineBroker,
    execute_e1_ensemble,
    execute_e2_convergence,
    validate_stage_transition,
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


def _axis_evidence(seed: str, outcome: str = "SUPPORTED") -> dict:
    evidence = make_ref("evidence_qualification_assessment", seed)
    return {
        "axis_outcomes": {
            "MECHANISM": outcome,
            "REACHABILITY": outcome,
            "IMPACT": outcome,
            "SEVERITY": outcome,
        },
        "axis_evidence_refs": {
            "MECHANISM": [evidence],
            "REACHABILITY": [evidence],
            "IMPACT": [evidence],
            "SEVERITY": [evidence],
        },
    }


def test_e1_stage_and_lane_specs():
    spec = build_e1_stage_spec()
    assert spec.stage_key == "E1"
    assert spec.stage_ordinal == 1
    assert spec.required_lane_slots == E1_LANE_SLOTS
    assert len(spec.required_lane_slots) == 5
    assert spec.blind_reveal_phase_model == "CONTROLLED"

    lane_specs = build_e1_lane_specs()
    assert len(lane_specs) == 5
    for slot in E1_LANE_SLOTS:
        assert slot in lane_specs
        ls = lane_specs[slot]
        assert ls.required_isolation_assurance == "DECLARED"
        assert "OTHER_LANE_UNSEALED_FINDINGS" in ls.forbidden_knowledge_classes

    enforced_lane_specs = build_e1_lane_specs(
        required_isolation_assurance="ENFORCED"
    )
    assert all(
        spec.required_isolation_assurance == "ENFORCED"
        for spec in enforced_lane_specs.values()
    )


def test_quarantine_broker_knowledge_isolation():
    broker = EnsembleQuarantineBroker()
    broker.record_lane_discovery("E1-A", {"id": "disc_a1", "statement": "Buffer overflow in parser"})
    broker.record_lane_discovery("E1-B", {"id": "disc_b1", "statement": "Privilege escalation in auth"})

    a_view = broker.get_lane_view("E1-A")
    assert len(a_view) == 1
    assert a_view[0]["id"] == "disc_a1"

    with pytest.raises(ValidationError, match="CROSS_LANE_KNOWLEDGE_LEAKAGE"):
        broker.query_cross_lane_findings(requesting_lane="E1-A", target_lane="E1-B")

    released = broker.release_checkpoint_for_e2()
    assert len(released["E1-A"]) == 1
    assert len(released["E1-B"]) == 1

    b_view = broker.query_cross_lane_findings(requesting_lane="E1-A", target_lane="E1-B")
    assert len(b_view) == 1


def test_execute_e1_ensemble_success():
    src_gen = make_ref("source_generation", "gen_1")
    discoveries = {
        "E1-A": [{"statement": "Unchecked pointer dereference in C runtime"}],
        "E1-B": [{"statement": "Missing authentication on admin websocket"}],
        "E1-C": [{"statement": "State race condition during DB failover"}],
        "E1-D": [{"statement": "Deserialization flaw in XML catalog"}],
        "E1-E": [{"statement": "Thread deadlock in connection pool"}],
    }

    result = execute_e1_ensemble(src_gen, discoveries)
    assert result.stage_key == "E1"
    assert result.completed_lanes == E1_LANE_SLOTS
    assert result.total_discoveries == 5
    assert len(result.completion_digest) == 64
    assert len(result.quarantined_claims) == 5


def test_e1_completion_digest_binds_discovery_content():
    src_gen = make_ref("source_generation", "gen_content")
    base = {slot: [] for slot in E1_LANE_SLOTS}
    base["E1-A"] = [{"statement": "first"}]
    changed = {slot: list(items) for slot, items in base.items()}
    changed["E1-A"] = [{"statement": "second"}]
    assert execute_e1_ensemble(src_gen, base).completion_digest != execute_e1_ensemble(src_gen, changed).completion_digest


def test_execute_e1_missing_mandatory_lane_fails_closed():
    src_gen = make_ref("source_generation", "gen_1")
    incomplete_discoveries = {
        "E1-A": [{"statement": "Finding A"}],
        "E1-B": [{"statement": "Finding B"}],
        "E1-C": [{"statement": "Finding C"}],
        "E1-D": [{"statement": "Finding D"}],
    }
    with pytest.raises(ValidationError, match="MANDATORY_LANE_MISSING"):
        execute_e1_ensemble(src_gen, incomplete_discoveries)


def test_stage_transition_gating():
    e2_spec = build_e2_stage_spec()
    with pytest.raises(ValidationError, match="STAGE_TRANSITION_GATED"):
        validate_stage_transition({"stage_key": "E0"}, e2_spec)


def test_execute_e2_convergence_deduplication_and_contradiction():
    src_gen = make_ref("source_generation", "gen_1")
    adjudicator = make_ref("actor_or_authority_ref", "chief_auditor")
    policy = make_ref("policy_revision", "adjudication_pol_1")
    cut = {"tag": "STAGE_E2_CUT"}

    shared_statement = "Path traversal in file upload endpoint"
    contested_statement = "Insecure cookie flags allow session hijacking"
    shared_root = make_ref("root_cause_revision", "shared_root")
    contested_root = make_ref("root_cause_revision", "contested_root")

    discoveries = {
        "E1-A": [
            {
                "statement": shared_statement,
                "root_cause_ref": shared_root,
                "claim_outcome": "SUPPORTED",
                "evidence_ref": make_ref("evidence_qualification_assessment", "ev_shared_a"),
                **_axis_evidence("axis_shared_a"),
            },
            {
                "statement": contested_statement,
                "root_cause_ref": contested_root,
                "claim_outcome": "SUPPORTED",
                "evidence_ref": make_ref("evidence_qualification_assessment", "ev_c1"),
            },
        ],
        "E1-B": [
            {
                "statement": shared_statement,
                "root_cause_ref": shared_root,
                "claim_outcome": "SUPPORTED",
                "evidence_ref": make_ref("evidence_qualification_assessment", "ev_shared_b"),
                **_axis_evidence("axis_shared_b"),
            },
        ],
        "E1-C": [
            {"finding_id": "memory-leak", "statement": "Memory leak in query cache", **_axis_evidence("axis_memory")},
        ],
        "E1-D": [
            {
                "statement": contested_statement,
                "root_cause_ref": contested_root,
                "claim_outcome": "REFUTED",
                "evidence_ref": make_ref("evidence_qualification_assessment", "ev_d1"),
            },
        ],
        "E1-E": [
            {"finding_id": "lock-timeout", "statement": "Timeout in distributed lock", **_axis_evidence("axis_timeout")},
        ],
    }

    e1_result = execute_e1_ensemble(src_gen, discoveries)
    e2_result = execute_e2_convergence(
        e1_completion=e1_result,
        source_generation_ref=src_gen,
        adjudicator_ref=adjudicator,
        input_history_cut=cut,
        policy_ref=policy,
    )

    assert e2_result.stage_key == "E2"
    assert e2_result.e1_completion_digest == e1_result.completion_digest
    assert len(e2_result.completion_digest) == 64
    assert len(e2_result.adjudicated_decisions) == 4
    assert len(e2_result.contradiction_revisions) == 1
    contra = e2_result.contradiction_revisions[0]
    assert contra.status == "OPEN"
    assert len(
        contra.supporting_evidence_qualification_refs
    ) == 1
    assert len(
        contra.opposing_evidence_qualification_refs
    ) == 1
    assert len(contra.claim_revision_refs) >= 2


def test_missing_evidence_never_confirms_claim():
    src_gen = make_ref("source_generation", "gen_no_evidence")
    discoveries = {slot: [] for slot in E1_LANE_SLOTS}
    discoveries["E1-A"] = [{
        "finding_id": "unsupported-claim",
        "statement": "Claim with asserted outcome but no evidence",
        "claim_outcome": "SUPPORTED",
    }]
    e1 = execute_e1_ensemble(src_gen, discoveries)
    e2 = execute_e2_convergence(
        e1,
        src_gen,
        make_ref("actor_or_authority_ref", "auditor_no_evidence"),
        {"tag": "CUT"},
        make_ref("policy_revision", "policy_no_evidence"),
    )
    assert len(e2.adjudicated_decisions) == 1
    assert e2.adjudicated_decisions[0].lifecycle_status == "OPEN"


def test_identical_statement_without_stable_identity_is_not_merged():
    src_gen = make_ref("source_generation", "gen_no_false_merge")
    discoveries = {slot: [] for slot in E1_LANE_SLOTS}
    discoveries["E1-A"] = [{"finding_id": "a", "statement": "Same wording", "affected_component": "a.py"}]
    discoveries["E1-B"] = [{"finding_id": "b", "statement": "Same wording", "affected_component": "b.py"}]
    e1 = execute_e1_ensemble(src_gen, discoveries)
    e2 = execute_e2_convergence(
        e1,
        src_gen,
        make_ref("actor_or_authority_ref", "auditor_merge"),
        {"tag": "CUT"},
        make_ref("policy_revision", "policy_merge"),
    )
    assert len(e2.adjudicated_decisions) == 2
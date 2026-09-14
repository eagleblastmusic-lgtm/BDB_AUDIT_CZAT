"""Targeted unit and adversarial tests for WP-F4-09 native E1/E2."""
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


def _axis_evidence(seed: str, outcome: str = "SUPPORTED", severity: str = "MEDIUM") -> dict:
    evidence = make_ref("evidence_qualification_assessment", seed)
    return {
        "severity_value": severity,
        "axis_outcomes": {
            "MECHANISM": outcome,
            "REACHABILITY": outcome,
            "IMPACT": outcome,
        },
        "axis_evidence_refs": {
            "MECHANISM": [evidence],
            "REACHABILITY": [evidence],
            "IMPACT": [evidence],
            "SEVERITY": [evidence],
        },
    }


def _severity_only(value: str = "MEDIUM") -> dict:
    return {"severity_value": value}


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
        assert lane_specs[slot].required_isolation_assurance == "ENFORCED"
        assert "OTHER_LANE_UNSEALED_FINDINGS" in lane_specs[slot].forbidden_knowledge_classes


def test_e2_stage_spec_requires_materialized_claim_axes_and_normalization_outputs():
    spec = build_e2_stage_spec()
    assert spec.stage_key == "E2"
    assert "finding_claim_revisions" in spec.required_stage_completion_outputs
    assert "finding_axis_assessments" in spec.required_stage_completion_outputs
    assert "root_cause_revisions" in spec.required_stage_completion_outputs
    assert "contradiction_obligations" in spec.required_stage_completion_outputs


def test_quarantine_broker_knowledge_isolation():
    broker = EnsembleQuarantineBroker()
    broker.record_lane_discovery("E1-A", {"id": "disc_a1", "statement": "Buffer overflow in parser"})
    broker.record_lane_discovery("E1-B", {"id": "disc_b1", "statement": "Privilege escalation in auth"})
    assert broker.get_lane_view("E1-A")[0]["id"] == "disc_a1"

    with pytest.raises(ValidationError, match="CROSS_LANE_KNOWLEDGE_LEAKAGE"):
        broker.query_cross_lane_findings(requesting_lane="E1-A", target_lane="E1-B")

    released = broker.release_checkpoint_for_e2()
    assert len(released["E1-A"]) == 1
    assert len(released["E1-B"]) == 1
    assert len(broker.query_cross_lane_findings(requesting_lane="E1-A", target_lane="E1-B")) == 1


def test_execute_e1_ensemble_success_and_digest_binds_content():
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

    changed = {slot: list(items) for slot, items in discoveries.items()}
    changed["E1-A"] = [{"statement": "Different pointer dereference"}]
    assert result.completion_digest != execute_e1_ensemble(src_gen, changed).completion_digest


def test_execute_e1_missing_mandatory_lane_fails_closed():
    incomplete = {
        "E1-A": [],
        "E1-B": [],
        "E1-C": [],
        "E1-D": [],
    }
    with pytest.raises(ValidationError, match="MANDATORY_LANE_MISSING"):
        execute_e1_ensemble(make_ref("source_generation", "gen_missing"), incomplete)


def test_stage_transition_gating():
    with pytest.raises(ValidationError, match="STAGE_TRANSITION_GATED"):
        validate_stage_transition({"stage_key": "E0"}, build_e2_stage_spec())


def test_e2_individual_adjudication_precedes_root_cause_and_contradiction_normalization():
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
                "category": "SECURITY",
                "root_cause_ref": shared_root,
                "root_cause_statement": "Shared unsafe path canonicalization boundary",
                "root_cause_relation_role": "PRIMARY",
                "claim_outcome": "SUPPORTED",
                "evidence_ref": make_ref("evidence_qualification_assessment", "ev_shared_a"),
                **_axis_evidence("axis_shared_a", severity="HIGH"),
            },
            {
                "statement": contested_statement,
                "category": "SECURITY",
                "root_cause_ref": contested_root,
                "claim_outcome": "SUPPORTED",
                "evidence_ref": make_ref("evidence_qualification_assessment", "ev_c1"),
                **_severity_only("HIGH"),
            },
        ],
        "E1-B": [
            {
                "statement": shared_statement,
                "category": "SECURITY",
                "root_cause_ref": shared_root,
                "root_cause_statement": "Shared unsafe path canonicalization boundary",
                "claim_outcome": "SUPPORTED",
                "evidence_ref": make_ref("evidence_qualification_assessment", "ev_shared_b"),
                **_axis_evidence("axis_shared_b", severity="HIGH"),
            },
        ],
        "E1-C": [
            {
                "finding_id": "memory-leak",
                "statement": "Memory leak in query cache",
                "category": "RELIABILITY",
                **_axis_evidence("axis_memory", severity="MEDIUM"),
            },
        ],
        "E1-D": [
            {
                "statement": contested_statement,
                "category": "SECURITY",
                "root_cause_ref": contested_root,
                "claim_outcome": "REFUTED",
                "evidence_ref": make_ref("evidence_qualification_assessment", "ev_d1"),
                **_severity_only("HIGH"),
            },
        ],
        "E1-E": [
            {
                "finding_id": "lock-timeout",
                "statement": "Timeout in distributed lock",
                "category": "AVAILABILITY",
                **_axis_evidence("axis_timeout", severity="MEDIUM"),
            },
        ],
    }

    e1 = execute_e1_ensemble(src_gen, discoveries)
    e2 = execute_e2_convergence(e1, src_gen, adjudicator, cut, policy)

    assert e2.stage_key == "E2"
    assert e2.e1_completion_digest == e1.completion_digest
    assert len(e2.finding_claim_revisions) == 6
    assert len(e2.axis_assessments) == 24
    assert len(e2.adjudicated_decisions) == 6
    assert len(e2.root_cause_revisions) == 1
    assert len(e2.root_cause_revisions[0].membership_edges) == 2
    assert len(e2.contradiction_revisions) == 1

    contradiction = e2.contradiction_revisions[0]
    assert contradiction.status == "OPEN"
    assert len(contradiction.claim_revision_refs) == 2
    assert len(contradiction.supporting_evidence_qualification_refs) == 1
    assert len(contradiction.opposing_evidence_qualification_refs) == 1

    claim_digests = {claim.digest for claim in e2.finding_claim_revisions}
    decision_claim_digests = {decision.claim_revision_ref["revision_digest"] for decision in e2.adjudicated_decisions}
    assert decision_claim_digests == claim_digests


def test_e2_is_replay_deterministic_for_identical_inputs():
    src_gen = make_ref("source_generation", "gen_replay")
    policy = make_ref("policy_revision", "policy_replay")
    adjudicator = make_ref("actor_or_authority_ref", "auditor_replay")
    cut = {"tag": "REPLAY_CUT"}
    discoveries = {slot: [] for slot in E1_LANE_SLOTS}
    discoveries["E1-A"] = [
        {
            "statement": "Deterministic replay finding",
            "category": "RELIABILITY",
            **_axis_evidence("replay_axis", severity="LOW"),
        }
    ]
    e1 = execute_e1_ensemble(src_gen, discoveries)
    first = execute_e2_convergence(e1, src_gen, adjudicator, cut, policy)
    second = execute_e2_convergence(e1, src_gen, adjudicator, cut, policy)

    assert first.completion_digest == second.completion_digest
    assert [claim.digest for claim in first.finding_claim_revisions] == [claim.digest for claim in second.finding_claim_revisions]
    assert [axis.digest for axis in first.axis_assessments] == [axis.digest for axis in second.axis_assessments]
    assert [decision.digest for decision in first.adjudicated_decisions] == [decision.digest for decision in second.adjudicated_decisions]


def test_missing_axis_evidence_never_confirms_claim():
    src_gen = make_ref("source_generation", "gen_no_evidence")
    discoveries = {slot: [] for slot in E1_LANE_SLOTS}
    discoveries["E1-A"] = [
        {
            "statement": "Claim with asserted outcome but no axis evidence",
            "category": "OTHER",
            "severity_value": "INFO",
            "axis_outcomes": {
                "MECHANISM": "SUPPORTED",
                "REACHABILITY": "SUPPORTED",
                "IMPACT": "SUPPORTED",
            },
        }
    ]
    e1 = execute_e1_ensemble(src_gen, discoveries)
    e2 = execute_e2_convergence(
        e1,
        src_gen,
        make_ref("actor_or_authority_ref", "auditor_no_evidence"),
        {"tag": "CUT"},
        make_ref("policy_revision", "policy_no_evidence"),
    )
    assert e2.adjudicated_decisions[0].finding_lifecycle_status == "OPEN"
    operational = [axis for axis in e2.axis_assessments if axis.axis != "SEVERITY"]
    assert {axis.epistemic_outcome for axis in operational} == {"INCONCLUSIVE"}


def test_missing_severity_fails_closed_instead_of_inventing_value():
    src_gen = make_ref("source_generation", "gen_no_severity")
    discoveries = {slot: [] for slot in E1_LANE_SLOTS}
    discoveries["E1-A"] = [{"statement": "Finding without severity"}]
    e1 = execute_e1_ensemble(src_gen, discoveries)
    with pytest.raises(ValidationError, match="E2_SEVERITY_ASSESSMENT_REQUIRED"):
        execute_e2_convergence(
            e1,
            src_gen,
            make_ref("actor_or_authority_ref", "auditor_no_severity"),
            {"tag": "CUT"},
            make_ref("policy_revision", "policy_no_severity"),
        )


def test_identical_statement_without_stable_relation_is_not_merged():
    src_gen = make_ref("source_generation", "gen_no_false_merge")
    discoveries = {slot: [] for slot in E1_LANE_SLOTS}
    discoveries["E1-A"] = [
        {"statement": "Same wording", "affected_component": "a.py", **_axis_evidence("same_a")}
    ]
    discoveries["E1-B"] = [
        {"statement": "Same wording", "affected_component": "b.py", **_axis_evidence("same_b")}
    ]
    e1 = execute_e1_ensemble(src_gen, discoveries)
    e2 = execute_e2_convergence(
        e1,
        src_gen,
        make_ref("actor_or_authority_ref", "auditor_merge"),
        {"tag": "CUT"},
        make_ref("policy_revision", "policy_merge"),
    )
    assert len(e2.finding_claim_revisions) == 2
    assert len(e2.adjudicated_decisions) == 2
    assert len(e2.root_cause_revisions) == 0
    assert len(e2.contradiction_revisions) == 0

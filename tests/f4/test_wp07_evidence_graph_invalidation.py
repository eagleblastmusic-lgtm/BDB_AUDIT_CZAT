"""Targeted unit and adversarial tests for WP-F4-07 / PR-F4-07.

Tests:
1. Multidimensional independence assessment across 8 dimensions.
2. Adversarial shared parser/oracle rejection (cannot masquerade as independent).
3. Evidence DAG construction and acyclicity validation.
4. Fail-closed cycle detection in evidence graph.
5. Transitive invalidation propagation through evidence DAG.
6. Current support calculation with active vs degraded evidence.
7. Evidence contradiction detection.
"""
import hashlib
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id
from bdb_audit.evidence import (
    INDEPENDENCE_DIMENSIONS,
    EvidenceGraph,
    assess_multidimensional_independence,
    Observation,
    DependencyIndependenceAssessment,
    EvidenceApplicabilityAssessment,
    EvidenceQualificationAssessment,
    EvidenceInvalidation,
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


def test_multidimensional_independence_all_distinct():
    claim_ref = make_ref("finding_claim_revision", "claim_1")

    lane_a = {dim: [make_ref("dependency", f"lane_a_{dim}")] for dim in INDEPENDENCE_DIMENSIONS}
    lane_b = {dim: [make_ref("dependency", f"lane_b_{dim}")] for dim in INDEPENDENCE_DIMENSIONS}

    res = assess_multidimensional_independence(claim_ref, lane_a, lane_b)
    assert res["is_independent"] is True
    assert res["overall_result"] == "INDEPENDENT"
    assert len(res["failed_dimensions"]) == 0
    assert len(res["shared_dependencies"]) == 0
    for dim in INDEPENDENCE_DIMENSIONS:
        assert res["dimension_results"][dim] == "INDEPENDENT"


def test_adversarial_shared_oracle_or_parser_rejection():
    claim_ref = make_ref("finding_claim_revision", "claim_2")

    shared_oracle = make_ref("oracle", "shared_broken_oracle")
    shared_parser = make_ref("parser", "shared_parser_v1")

    lane_a = {
        "PROCESS_INDEPENDENCE": [make_ref("proc", "proc_1")],
        "INSTANCE_INDEPENDENCE": [make_ref("inst", "inst_1")],
        "IMPLEMENTATION_INDEPENDENCE": [make_ref("impl", "impl_1")],
        "STORAGE_READ_PATH_INDEPENDENCE": [make_ref("storage", "path_1")],
        "EXTERNAL_BOUNDARY_INDEPENDENCE": [make_ref("boundary", "b_1")],
        "ORACLE_INDEPENDENCE": [shared_oracle],
        "MODEL_AGENT_INDEPENDENCE": [make_ref("agent", "agent_1")],
        "HARNESS_INDEPENDENCE": [shared_parser],
    }

    # Lane B uses fresh process, instance, and agent, but shares Oracle & Parser
    lane_b = {
        "PROCESS_INDEPENDENCE": [make_ref("proc", "proc_2")],
        "INSTANCE_INDEPENDENCE": [make_ref("inst", "inst_2")],
        "IMPLEMENTATION_INDEPENDENCE": [make_ref("impl", "impl_2")],
        "STORAGE_READ_PATH_INDEPENDENCE": [make_ref("storage", "path_2")],
        "EXTERNAL_BOUNDARY_INDEPENDENCE": [make_ref("boundary", "b_2")],
        "ORACLE_INDEPENDENCE": [shared_oracle],  # SHARED!
        "MODEL_AGENT_INDEPENDENCE": [make_ref("agent", "agent_2")],
        "HARNESS_INDEPENDENCE": [shared_parser],  # SHARED!
    }

    res = assess_multidimensional_independence(claim_ref, lane_a, lane_b)
    assert res["is_independent"] is False
    assert res["overall_result"] == "SHARED_DEPENDENCY"
    assert "ORACLE_INDEPENDENCE" in res["failed_dimensions"]
    assert "HARNESS_INDEPENDENCE" in res["failed_dimensions"]
    assert len(res["shared_dependencies"]) == 2


def test_evidence_graph_acyclic_construction():
    graph = EvidenceGraph()

    # Add pipeline nodes
    graph.add_node("claim_1", "CLAIM")
    graph.add_node("hyp_1", "HYPOTHESIS")
    graph.add_node("exp_1", "EXPERIMENT")
    graph.add_node("exec_1", "EXECUTION")
    graph.add_node("obs_1", "OBSERVATION")
    graph.add_node("ind_1", "INDEPENDENCE_ASSESSMENT")
    graph.add_node("app_1", "APPLICABILITY_ASSESSMENT")
    graph.add_node("qual_1", "QUALIFICATION_ASSESSMENT", data={"result": "SUPPORTS", "claim_id": "claim_1"})

    # Wire DAG edges: child depends on parent
    graph.add_edge("exp_1", "hyp_1", "DEPENDS_ON")
    graph.add_edge("exec_1", "exp_1", "DEPENDS_ON")
    graph.add_edge("obs_1", "exec_1", "DEPENDS_ON")
    graph.add_edge("qual_1", "obs_1", "DEPENDS_ON")
    graph.add_edge("qual_1", "ind_1", "DEPENDS_ON")
    graph.add_edge("qual_1", "app_1", "DEPENDS_ON")
    graph.add_edge("qual_1", "claim_1", "SUPPORTS")

    assert len(graph.nodes) == 8
    assert graph.detect_cycles() == []

    # Support calculation
    support = graph.calculate_current_support("claim_1")
    assert support["effective_status"] == "SUPPORTED"
    assert support["active_support_count"] == 1
    assert "qual_1" in support["supporting_qualifications"]


def test_evidence_graph_cycle_detection_fail_closed():
    graph = EvidenceGraph()
    graph.add_node("node_a", "OBSERVATION")
    graph.add_node("node_b", "EXPERIMENT")
    graph.add_node("node_c", "HYPOTHESIS")

    graph.add_edge("node_a", "node_b", "DEPENDS_ON")
    graph.add_edge("node_b", "node_c", "DEPENDS_ON")

    # Closing a cycle must immediately raise ValidationError fail-closed
    with pytest.raises(ValidationError, match="EVIDENCE_GRAPH_CYCLE"):
        graph.add_edge("node_c", "node_a", "DEPENDS_ON")


def test_transitive_invalidation_propagation():
    graph = EvidenceGraph()

    # Root dependency
    graph.add_node("faulty_oracle", "ORACLE")
    graph.add_node("exec_1", "EXECUTION")
    graph.add_node("obs_1", "OBSERVATION")
    graph.add_node("qual_1", "QUALIFICATION_ASSESSMENT", data={"result": "SUPPORTS", "claim_id": "claim_1"})

    # Independent node
    graph.add_node("clean_oracle", "ORACLE")
    graph.add_node("exec_2", "EXECUTION")
    graph.add_node("obs_2", "OBSERVATION")
    graph.add_node("qual_2", "QUALIFICATION_ASSESSMENT", data={"result": "SUPPORTS", "claim_id": "claim_1"})

    # Edges
    graph.add_edge("exec_1", "faulty_oracle", "DEPENDS_ON")
    graph.add_edge("obs_1", "exec_1", "DEPENDS_ON")
    graph.add_edge("qual_1", "obs_1", "DEPENDS_ON")

    graph.add_edge("exec_2", "clean_oracle", "DEPENDS_ON")
    graph.add_edge("obs_2", "exec_2", "DEPENDS_ON")
    graph.add_edge("qual_2", "obs_2", "DEPENDS_ON")

    # Propagate invalidation from faulty_oracle
    inval_result = graph.propagate_invalidation("faulty_oracle", reason="FLAKY_ORACLE")

    assert inval_result["root_invalidations"] == ["faulty_oracle"]
    assert set(inval_result["transitive_invalidations"]) == {"exec_1", "obs_1", "qual_1"}
    assert inval_result["degraded_qualifications"] == ["qual_1"]

    # qual_1 must be STALE, satisfies_completion False
    q1_node = graph.get_node("qual_1")
    assert q1_node.status == "STALE"
    assert q1_node.satisfies_completion is False

    # qual_2 must remain unaffected
    q2_node = graph.get_node("qual_2")
    assert q2_node.status == "ACTIVE"
    assert q2_node.satisfies_completion is True

    # Current support should now only have qual_2
    support = graph.calculate_current_support("claim_1")
    assert support["effective_status"] == "SUPPORTED"
    assert support["supporting_qualifications"] == ["qual_2"]
    assert support["stale_or_invalid_qualifications"] == ["qual_1"]


def test_contradiction_detection_in_evidence_graph():
    graph = EvidenceGraph()
    graph.add_node("claim_alpha", "CLAIM")
    graph.add_node("qual_supporting", "QUALIFICATION_ASSESSMENT", data={"result": "SUPPORTS", "claim_id": "claim_alpha"})
    graph.add_node("qual_refuting", "QUALIFICATION_ASSESSMENT", data={"result": "REFUTES", "claim_id": "claim_alpha"})

    support = graph.calculate_current_support("claim_alpha")
    assert support["effective_status"] == "CONTRADICTED"
    assert support["active_support_count"] == 1
    assert support["active_refute_count"] == 1

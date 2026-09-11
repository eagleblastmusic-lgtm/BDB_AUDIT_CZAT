"""Targeted tests for Failure Interaction Graph (PR-E5-01 / M36)."""
import pytest
from bdb_audit.attack.interaction_graph import (
    FailureInteractionGraph,
    InteractionNode,
    InteractionEdge,
)
from bdb_audit.core.errors import ValidationError


@pytest.fixture
def history_cut():
    return {
        "campaign_id": "CAMP-001",
        "commit_seq": 10,
        "commit_hash": "a" * 64,
    }


@pytest.fixture
def provenance_ref():
    return {
        "kind": "stage_run",
        "revision_digest": "p" * 64,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stage_run/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }


def make_node(nid, nkind, history_cut, prov_ref, materiality="HIGH"):
    return InteractionNode(
        node_id=nid,
        node_kind=nkind,
        provenance_ref=prov_ref,
        accepted_history_binding=history_cut,
        supporting_refs=(
            {
                "kind": "observation",
                "revision_digest": f"obs_{nid}",
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": "BDB_SCHEMA_REGISTRY::observation/1",
                "ref_class": "CONTENT_OR_PRIOR",
            },
        ),
        history_cut=history_cut,
        materiality=materiality,
    )


def test_graph_single_and_pairwise(history_cut, provenance_ref):
    graph = FailureInteractionGraph(history_cut)

    n1 = make_node("fail_a", "FAILURE_MODE", history_cut, provenance_ref)
    n2 = make_node("fail_b", "FAILURE_MODE", history_cut, provenance_ref)
    graph.add_node(n1)
    graph.add_node(n2)

    # Pairwise edge
    edge = InteractionEdge(
        edge_id="edge_ab",
        source_nodes=("fail_a",),
        target_node="fail_b",
        relation="COMPOUND_TRIGGER",
        supporting_refs=(
            {
                "kind": "experiment_spec",
                "revision_digest": "exp_ab",
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": "BDB_SCHEMA_REGISTRY::experiment_spec/1",
                "ref_class": "CONTENT_OR_PRIOR",
            },
        ),
        provenance_ref=provenance_ref,
        history_cut=history_cut,
    )
    graph.add_edge(edge)

    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    assert edge.order == 2

    pairwise = graph.query_interactions(order=2)
    assert len(pairwise) == 1
    assert pairwise[0].edge_id == "edge_ab"


def test_higher_order_interaction(history_cut, provenance_ref):
    graph = FailureInteractionGraph(history_cut, max_interaction_order=4)

    n1 = make_node("f1", "FAILURE_MODE", history_cut, provenance_ref)
    n2 = make_node("f2", "FAILURE_MODE", history_cut, provenance_ref)
    n3 = make_node("f3", "FAILURE_MODE", history_cut, provenance_ref)
    n4 = make_node("rc1", "ROOT_CAUSE_FAMILY", history_cut, provenance_ref)

    for n in (n1, n2, n3, n4):
        graph.add_node(n)

    # 3-way interaction edge
    edge_3way = InteractionEdge(
        edge_id="edge_3way",
        source_nodes=("f1", "f2"),
        target_node="f3",
        relation="AMPLIFIES",
        supporting_refs=({"kind": "observation", "revision_digest": "obs_3w"},),
        provenance_ref=provenance_ref,
        history_cut=history_cut,
    )
    graph.add_edge(edge_3way)
    assert edge_3way.order == 3

    # 4-way interaction edge
    edge_4way = InteractionEdge(
        edge_id="edge_4way",
        source_nodes=("f1", "f2", "f3"),
        target_node="rc1",
        relation="CASCADE",
        supporting_refs=({"kind": "observation", "revision_digest": "obs_4w"},),
        provenance_ref=provenance_ref,
        history_cut=history_cut,
    )
    graph.add_edge(edge_4way)
    assert edge_4way.order == 4


def test_correlation_not_causation_unsupported_edge_rejected(history_cut, provenance_ref):
    """Fail-closed: edges cannot be established on correlation alone without supporting refs."""
    with pytest.raises(ValidationError, match="UNSUPPORTED_INTERACTION_EDGE"):
        InteractionEdge(
            edge_id="edge_unsupported",
            source_nodes=("f1",),
            target_node="f2",
            relation="COMPOUND_TRIGGER",
            supporting_refs=(),  # empty -> rejected!
            provenance_ref=provenance_ref,
            history_cut=history_cut,
        )


def test_stale_graph_input_rejection(history_cut, provenance_ref):
    graph = FailureInteractionGraph(history_cut)

    stale_cut = {
        "campaign_id": "CAMP-001",
        "commit_seq": 9,
        "commit_hash": "b" * 64,
    }
    stale_node = make_node("stale_node", "FAILURE_MODE", stale_cut, provenance_ref)

    with pytest.raises(ValidationError, match="STALE_GRAPH_INPUT"):
        graph.add_node(stale_node)

    # Also test check_stale against newer head
    newer_cut = {
        "campaign_id": "CAMP-001",
        "commit_seq": 11,
        "commit_hash": "c" * 64,
    }
    assert graph.check_stale(newer_cut) is True
    assert graph.check_stale(history_cut) is False


def test_invalidated_support_propagation(history_cut, provenance_ref):
    graph = FailureInteractionGraph(history_cut)
    n1 = make_node("f1", "FAILURE_MODE", history_cut, provenance_ref)
    n2 = make_node("f2", "FAILURE_MODE", history_cut, provenance_ref)
    graph.add_node(n1)
    graph.add_node(n2)

    edge = InteractionEdge(
        edge_id="edge_12",
        source_nodes=("f1",),
        target_node="f2",
        relation="EXACERBATES",
        supporting_refs=({"kind": "observation", "revision_digest": "obs_to_invalidate"},),
        provenance_ref=provenance_ref,
        history_cut=history_cut,
    )
    graph.add_edge(edge)

    assert edge.status == "VALID"
    affected = graph.apply_invalidations({"obs_to_invalidate"})
    assert affected >= 1
    assert graph.edges["edge_12"].status == "INVALIDATED"
    assert graph.edges["edge_12"].is_invalidated is True

    # Valid interactions query filters out invalidated
    assert len(graph.query_interactions(only_valid=True)) == 0
    assert len(graph.query_interactions(only_valid=False)) == 1


def test_contradicted_edge_handling(history_cut, provenance_ref):
    graph = FailureInteractionGraph(history_cut)
    n1 = make_node("f1", "FAILURE_MODE", history_cut, provenance_ref)
    n2 = make_node("f2", "FAILURE_MODE", history_cut, provenance_ref)
    graph.add_node(n1)
    graph.add_node(n2)

    edge = InteractionEdge(
        edge_id="edge_12",
        source_nodes=("f1",),
        target_node="f2",
        relation="CASCADE",
        supporting_refs=({"kind": "observation", "revision_digest": "obs_1"},),
        provenance_ref=provenance_ref,
        history_cut=history_cut,
    )
    graph.add_edge(edge)

    graph.apply_contradiction("edge_12", "Contradicted by experiment EXP-09")
    assert graph.edges["edge_12"].status == "CONTRADICTED"
    assert graph.edges["edge_12"].is_contradicted is True
    assert "EXP-09" in graph.edges["edge_12"].contradiction_reason


def test_interaction_explosion_boundedness(history_cut, provenance_ref):
    """Fail-closed: order exceeding limit or combinatorics explosion is bounded."""
    graph = FailureInteractionGraph(history_cut, max_interaction_order=3, max_combinations_bound=10)

    for i in range(10):
        graph.add_node(make_node(f"f{i}", "FAILURE_MODE", history_cut, provenance_ref))

    # Candidate combinations bounded by max_combinations_bound
    combos = graph.generate_candidate_combinations(target_order=2)
    assert len(combos) == 10  # bounded at 10 even though 10 choose 2 is 45!

    # Requesting order > max_interaction_order raises error
    with pytest.raises(ValidationError, match="INTERACTION_EXPLOSION_EXCEEDED"):
        graph.generate_candidate_combinations(target_order=4)

    # Adding edge exceeding max_interaction_order raises error
    with pytest.raises(ValidationError, match="INTERACTION_EXPLOSION_EXCEEDED"):
        edge_5way = InteractionEdge(
            edge_id="edge_5way",
            source_nodes=("f0", "f1", "f2", "f3"),
            target_node="f4",
            relation="COMPOUND_TRIGGER",
            supporting_refs=({"kind": "observation", "revision_digest": "obs_x"},),
            provenance_ref=provenance_ref,
            history_cut=history_cut,
        )
        graph.add_edge(edge_5way)


def test_deterministic_rebuild(history_cut, provenance_ref):
    graph = FailureInteractionGraph(history_cut)
    n1 = make_node("f1", "FAILURE_MODE", history_cut, provenance_ref)
    n2 = make_node("f2", "FAILURE_MODE", history_cut, provenance_ref)
    graph.add_node(n1)
    graph.add_node(n2)

    edge = InteractionEdge(
        edge_id="edge_12",
        source_nodes=("f1",),
        target_node="f2",
        relation="COMPOUND_TRIGGER",
        supporting_refs=({"kind": "observation", "revision_digest": "obs_1"},),
        provenance_ref=provenance_ref,
        history_cut=history_cut,
    )
    graph.add_edge(edge)

    canonical = graph.export_canonical()
    d1 = graph.digest()

    rebuilt = FailureInteractionGraph.rebuild(canonical)
    d2 = rebuilt.digest()

    assert d1 == d2
    assert len(rebuilt.nodes) == 2
    assert len(rebuilt.edges) == 1
    assert rebuilt.edges["edge_12"].relation == "COMPOUND_TRIGGER"

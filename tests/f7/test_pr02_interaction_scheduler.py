"""Targeted tests for Risk-Ranked Interaction Scheduler (PR-E5-02 / M37)."""
import pytest
from bdb_audit.attack.interaction_graph import (
    FailureInteractionGraph,
    InteractionNode,
)
from bdb_audit.attack.scheduler import (
    InteractionScheduler,
    InteractionCandidate,
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


def make_node(nid, nkind, history_cut, prov_ref, materiality="MEDIUM"):
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


def test_pairwise_and_deterministic_ranking(history_cut, provenance_ref):
    graph = FailureInteractionGraph(history_cut)
    # n1: CRITICAL, n2: HIGH, n3: LOW
    graph.add_node(make_node("node_a", "FAILURE_MODE", history_cut, provenance_ref, materiality="CRITICAL"))
    graph.add_node(make_node("node_b", "FAILURE_MODE", history_cut, provenance_ref, materiality="HIGH"))
    graph.add_node(make_node("node_c", "FAILURE_MODE", history_cut, provenance_ref, materiality="LOW"))

    scheduler = InteractionScheduler(graph, history_cut)
    pw = scheduler.schedule_pairwise()

    assert len(pw) == 3
    # Top ranked should be node_a (CRITICAL) + node_b (HIGH)
    assert pw[0].node_ids == ("node_a", "node_b")
    assert pw[0].order == 2
    # Verify ranking monotonicity
    assert pw[0].rank_score >= pw[1].rank_score >= pw[2].rank_score


def test_equal_priority_tie_handling(history_cut, provenance_ref):
    """Equal priority candidates must break ties deterministically via sorted node IDs."""
    graph = FailureInteractionGraph(history_cut)
    # Three identical nodes
    graph.add_node(make_node("n_z", "FAILURE_MODE", history_cut, provenance_ref, materiality="MEDIUM"))
    graph.add_node(make_node("n_a", "FAILURE_MODE", history_cut, provenance_ref, materiality="MEDIUM"))
    graph.add_node(make_node("n_m", "FAILURE_MODE", history_cut, provenance_ref, materiality="MEDIUM"))

    scheduler = InteractionScheduler(graph, history_cut)
    pw1 = scheduler.schedule_pairwise()
    pw2 = scheduler.schedule_pairwise()

    # Identical score among all pairs
    scores = [p.rank_score for p in pw1]
    assert len(set(scores)) == 1

    # Deterministic alphabetical ordering by tie_breaker_key
    keys = [p.tie_breaker_key for p in pw1]
    assert keys == sorted(keys)
    assert [p.candidate_id for p in pw1] == [p.candidate_id for p in pw2]


def test_selected_3way_and_4way(history_cut, provenance_ref):
    graph = FailureInteractionGraph(history_cut)
    for i, m in enumerate(["CRITICAL", "HIGH", "HIGH", "CRITICAL", "LOW"]):
        graph.add_node(make_node(f"node_{i}", "FAILURE_MODE", history_cut, provenance_ref, materiality=m))

    scheduler = InteractionScheduler(graph, history_cut, max_3way_budget=5, max_4way_budget=2)
    s3 = scheduler.schedule_selected_3way()
    s4 = scheduler.schedule_selected_4way()

    assert len(s3) > 0
    assert all(c.order == 3 for c in s3)
    # node_4 (LOW) should NOT be in selected 4-way candidates because 4-way restricts to CRITICAL/HIGH
    assert len(s4) == 1
    assert s4[0].order == 4
    assert "node_4" not in s4[0].node_ids


def test_bounded_scheduling(history_cut, provenance_ref):
    """Combinatorics must strictly respect budgets, never creating unbounded explosive powersets."""
    graph = FailureInteractionGraph(history_cut)
    for i in range(20):
        graph.add_node(make_node(f"n_{i:02d}", "FAILURE_MODE", history_cut, provenance_ref, materiality="MEDIUM"))

    # 20 choose 2 = 190. Set budget to 15.
    scheduler = InteractionScheduler(graph, history_cut, max_pairwise_budget=15)
    pw = scheduler.schedule_pairwise()
    assert len(pw) == 15


def test_stale_projection_rejection(history_cut, provenance_ref):
    graph = FailureInteractionGraph(history_cut)
    graph.add_node(make_node("n1", "FAILURE_MODE", history_cut, provenance_ref))

    stale_cut = {
        "campaign_id": "CAMP-001",
        "commit_seq": 9,
        "commit_hash": "different" * 4,
    }
    with pytest.raises(ValidationError, match="STALE_PROJECTION_INPUT"):
        InteractionScheduler(graph, stale_cut)


def test_unsupported_interaction_order():
    """Candidates with invalid order (>4 or <2) fail-closed."""
    with pytest.raises(ValidationError, match="UNSUPPORTED_INTERACTION_ORDER"):
        InteractionCandidate(
            candidate_id="c_bad",
            node_ids=("a", "b", "c", "d", "e"),
            order=5,
            materiality_score=5.0,
            risk_score=1.0,
            coverage_gap_weight=1.0,
            rank_score=5.0,
        )

    with pytest.raises(ValidationError, match="NODE_COUNT_MISMATCH"):
        InteractionCandidate(
            candidate_id="c_mismatch",
            node_ids=("a", "b"),
            order=3,
            materiality_score=3.0,
            risk_score=1.0,
            coverage_gap_weight=1.0,
            rank_score=3.0,
        )

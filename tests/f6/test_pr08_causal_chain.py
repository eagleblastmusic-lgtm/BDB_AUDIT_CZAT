"""Targeted tests for PR-E4-08 / M35: Causal Chain Engine."""
import pytest
from bdb_audit.core.errors import ValidationError
from bdb_audit.evidence.models import Observation
from bdb_audit.deepen.causal import (
    CausalEdge,
    CausalChainRecord,
    CausalChainEngine,
)


def test_fully_supported_causal_chain():
    engine = CausalChainEngine()

    # Step 1: External response trigger
    trigger = {"source": "EXTERNAL_HTTP", "event": "MALFORMED_HEADER"}

    # Path: PARSER -> CACHE -> CATALOG -> API -> FRONTEND
    path = ["PARSER", "CACHE", "CATALOG", "API", "FRONTEND"]

    # Supporting evidence for each edge
    ev1 = {"evidence_id": "ev_01", "type": "OBSERVATION"}
    ev2 = {"evidence_id": "ev_02", "type": "OBSERVATION"}
    ev3 = {"evidence_id": "ev_03", "type": "OBSERVATION"}
    ev4 = {"evidence_id": "ev_04", "type": "OBSERVATION"}

    edge1 = CausalEdge("PARSER", "CACHE", "TRANSITIONS_TO", (ev1,))
    edge2 = CausalEdge("CACHE", "CATALOG", "TRANSITIONS_TO", (ev2,))
    edge3 = CausalEdge("CATALOG", "API", "TRANSITIONS_TO", (ev3,))
    edge4 = CausalEdge("API", "FRONTEND", "CAUSES_IMPACT", (ev4,))

    chain = engine.build_causal_chain(
        chain_id="chain_01",
        scope="CATALOG_SYNC",
        trigger=trigger,
        path=path,
        state_transition_refs=[{"transition_id": "tr_01"}],
        observation_refs=[ev1, ev2, ev3, ev4],
        impact_ref={"impact": "STALE_CATALOG_RENDER"},
        edges=[edge1, edge2, edge3, edge4],
        root_cause_ref={"kind": "root_cause_revision", "id": "rc_01"},
    )

    assert chain.status == "VALID"
    assert len(chain.edges) == 4
    assert chain.digest() is not None


def test_missing_edge_support_rejected():
    # Attempting to create an edge with empty evidence raises ValidationError
    with pytest.raises(ValidationError) as exc:
        CausalEdge("A", "B", "TRANSITIONS_TO", support_evidence_refs=())
    assert "MISSING_EDGE_SUPPORT" in str(exc.value)


def test_contradicted_causal_edge():
    engine = CausalChainEngine()
    ev1 = {"evidence_id": "ev_01"}
    edge1 = CausalEdge("A", "B", "TRANSITIONS_TO", (ev1,))
    edge2 = CausalEdge(
        "B",
        "C",
        "CAUSES_IMPACT",
        (ev1,),
        is_contradicted=True,
        contradiction_reason="Independent experiment disproved causality",
    )

    chain = engine.build_causal_chain(
        chain_id="chain_contra",
        scope="S",
        trigger={"t": 1},
        path=["A", "B", "C"],
        state_transition_refs=[],
        observation_refs=[],
        impact_ref={"impact": "FAIL"},
        edges=[edge1, edge2],
    )

    assert chain.status == "CONTRADICTED"
    assert any("contradicted" in r.lower() for r in chain.reason_codes)


def test_invalidated_evidence_invalidates_chain():
    engine = CausalChainEngine()
    ev1 = {"evidence_id": "ev_valid"}
    ev_bad = {"evidence_id": "ev_invalidated_01"}

    edge1 = CausalEdge("A", "B", "TRANSITIONS_TO", (ev1,))
    edge2 = CausalEdge("B", "C", "CAUSES_IMPACT", (ev_bad,))

    chain = engine.build_causal_chain(
        chain_id="chain_inval",
        scope="S",
        trigger={"t": 1},
        path=["A", "B", "C"],
        state_transition_refs=[],
        observation_refs=[],
        impact_ref={"impact": "FAIL"},
        edges=[edge1, edge2],
        invalidated_evidence_ids={"ev_invalidated_01"},
    )

    assert chain.status == "INVALIDATED"
    assert any("is invalidated" in r.lower() for r in chain.reason_codes)


def test_second_root_cause_authority_rejected():
    engine = CausalChainEngine()
    ev = {"evidence_id": "ev_01"}
    edge = CausalEdge("A", "B", "CAUSES_IMPACT", (ev,))

    # Attempting to introduce an ad-hoc second root cause authority
    with pytest.raises(ValidationError) as exc:
        engine.build_causal_chain(
            chain_id="chain_sec_auth",
            scope="S",
            trigger={"t": 1},
            path=["A", "B"],
            state_transition_refs=[],
            observation_refs=[],
            impact_ref={},
            edges=[edge],
            root_cause_ref={"kind": "root_cause_membership_revision", "id": "second_auth_01"},
        )
    assert "SECOND_AUTHORITY_FOR_ROOT_CAUSE" in str(exc.value)


def test_deterministic_rebuild():
    engine = CausalChainEngine()
    ev = {"evidence_id": "ev_01"}
    edge = CausalEdge("A", "B", "CAUSES_IMPACT", (ev,))

    c1 = engine.build_causal_chain(
        chain_id="chain_det",
        scope="S",
        trigger={"t": 1},
        path=["A", "B"],
        state_transition_refs=[],
        observation_refs=[ev],
        impact_ref={"impact": "I"},
        edges=[edge],
    )
    c2 = engine.build_causal_chain(
        chain_id="chain_det",
        scope="S",
        trigger={"t": 1},
        path=["A", "B"],
        state_transition_refs=[],
        observation_refs=[ev],
        impact_ref={"impact": "I"},
        edges=[edge],
    )

    assert c1.digest() == c2.digest()


def test_causal_chain_observation_conversion():
    engine = CausalChainEngine()
    ev = {"evidence_id": "ev_01"}
    edge = CausalEdge("A", "B", "CAUSES_IMPACT", (ev,))
    chain = engine.build_causal_chain(
        chain_id="chain_obs",
        scope="S",
        trigger={"t": 1},
        path=["A", "B"],
        state_transition_refs=[],
        observation_refs=[ev],
        impact_ref={"impact": "I"},
        edges=[edge],
    )

    obs = engine.to_observation(chain)
    assert isinstance(obs, Observation)
    assert obs.observation_channel == "CAUSAL_CHAIN_ENGINE"
    assert obs.raw_observation_ref["chain_id"] == "chain_obs"
    assert not hasattr(obs, "finding_id")
    assert not hasattr(obs, "lifecycle_status")

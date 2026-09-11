"""Targeted unit and negative tests for PR-022 / M17/M18 gap and hypothesis minimum."""
import hashlib
import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id
from bdb_audit.hypothesis import (
    HypothesisRevision, DiscoveryOpportunity,
    build_opportunity_map, transition_hypothesis,
)
from bdb_audit.schemas.foundation import F3_KINDS, foundation_schema_bindings
from bdb_audit.schemas.identity import LayeredValidator


def ref(kind, seed, ref_class="CONTENT_OR_PRIOR", logical_id=None):
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
        **({"logical_id": logical_id} if logical_id else {}),
    }


def test_discovery_opportunity_map():
    surface = ref("surface_record", "surf_auth")
    ob_1 = ref("coverage_obligation", "ob_1")
    unknown = ref("typed_scope_ref", "unobserved_1")
    cut = {"tag": "EMPTY_HISTORY"}

    opps = build_opportunity_map(
        surfaces=[surface],
        unsatisfied_obligations=[ob_1],
        unknown_scopes=[unknown],
        current_history_cut=cut,
    )
    assert len(opps) == 1
    opp = opps[0]
    assert opp.gap_id == "gap_1"
    assert opp.materiality == "MATERIAL"
    assert opp.priority_score > 10.0
    assert opp.to_dict()["target_scope_ref"]["revision_digest"] == surface["revision_digest"]


def test_hypothesis_lifecycle_and_rejection_retention():
    cut = {"tag": "EMPTY_HISTORY"}
    src_gen = ref("source_generation", "gen_1")
    surface = ref("surface_record", "surf_auth")
    inv = ref("invariant_revision", "inv_auth")
    ob = ref("coverage_obligation", "ob_auth")
    discovery = ref("discovery_record", "disc_1")

    # Step 1: Propose hypothesis linked to discovery
    h_proposed = HypothesisRevision(
        hypothesis_id=new_id("hypothesis_revision"),
        hypothesis_revision="1",
        source_generation_ref=src_gen,
        statement="Missing bearer auth header causes 500 instead of 401",
        scope_refs=[surface],
        invariant_refs=[inv],
        obligation_refs=[ob],
        origin_discovery_ref=discovery,
        planning_mode="PREREGISTERED",
        status="PROPOSED",
        input_history_cut=cut,
    )
    assert h_proposed.status == "PROPOSED"
    assert len(h_proposed.digest) == 64

    # Step 2: Preregister
    h_prereg = transition_hypothesis(h_proposed, "PREREGISTERED")
    assert h_prereg.status == "PREREGISTERED"
    assert h_prereg.hypothesis_revision == "2"

    # Step 3: Testing
    h_testing = transition_hypothesis(h_prereg, "TESTING")
    assert h_testing.status == "TESTING"

    # Step 4: Rejection (rejected hypothesis is retained in history!)
    h_rejected = transition_hypothesis(h_testing, "REJECTED")
    assert h_rejected.status == "REJECTED"
    assert len(h_rejected.digest) == 64

    # Rejected hypothesis digest is immutable and distinct from earlier states
    history = [h_proposed.digest, h_prereg.digest, h_testing.digest, h_rejected.digest]
    assert len(history) == len(set(history))
    assert h_rejected.digest in history


def test_hypothesis_confirmation_flow():
    cut = {"tag": "EMPTY_HISTORY"}
    src_gen = ref("source_generation", "gen_1")

    h1 = HypothesisRevision(
        hypothesis_id=new_id("hypothesis_revision"),
        hypothesis_revision="1",
        source_generation_ref=src_gen,
        statement="Race condition on token refresh",
        status="PROPOSED",
        input_history_cut=cut,
    )
    h2 = transition_hypothesis(h1, "PREREGISTERED")
    h3 = transition_hypothesis(h2, "TESTING")
    h4 = transition_hypothesis(h3, "CONFIRMED")
    assert h4.status == "CONFIRMED"


def test_adversarial_hypothesis_rules():
    cut = {"tag": "EMPTY_HISTORY"}
    src_gen = ref("source_generation", "gen_1")

    h = HypothesisRevision(
        hypothesis_id=new_id("hypothesis_revision"),
        hypothesis_revision="1",
        source_generation_ref=src_gen,
        statement="Test hypothesis",
        planning_mode="EXPLORATORY",
        status="TESTING",
        input_history_cut=cut,
    )

    # Retroactive preregistration forbidden: cannot transition TESTING -> PREREGISTERED
    with pytest.raises(ValidationError, match="RETROACTIVE_PREREGISTRATION_FORBIDDEN"):
        transition_hypothesis(h, "PREREGISTERED")

    # Invalid status
    with pytest.raises(ValidationError, match="INVALID_HYPOTHESIS_STATUS"):
        HypothesisRevision(
            source_generation_ref=src_gen,
            statement="Bad status",
            status="NOT_A_STATUS",
            input_history_cut=cut,
        )


def test_hypothesis_schema_with_layered_validator():
    bindings = foundation_schema_bindings(kinds=F3_KINDS)
    validator = LayeredValidator(bindings=bindings)

    cut = {"tag": "EMPTY_HISTORY"}
    h = HypothesisRevision(
        hypothesis_id=new_id("hypothesis_revision"),
        hypothesis_revision="1",
        source_generation_ref=ref("source_generation", "g_1"),
        statement="Token validation bypass",
        status="PREREGISTERED",
        input_history_cut=cut,
    )
    val = validator.validate("hypothesis_revision", canonical_bytes(h.body()))
    assert val.revision_digest == h.digest

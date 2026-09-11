"""Targeted tests for Work Package 5 (PR-F4-05): Hypothesis Orchestration & Immutable Provenance."""
import hashlib
import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id, deterministic_id
from bdb_audit.hypothesis import (
    HypothesisRevision,
    HypothesisOrchestrator,
    HYPOTHESIS_STATUSES,
)


def make_ref(kind: str, seed: str, logical_id: str | None = None) -> dict:
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": "CONTENT_OR_PRIOR",
        **({"logical_id": logical_id} if logical_id else {}),
    }


def test_hypothesis_lifecycle_full_flow():
    """Verify standard hypothesis progression from proposal through confirmation."""
    orch = HypothesisOrchestrator()
    src_ref = make_ref("source_identity", "src_1")
    surf_ref = make_ref("surface_record", "surf_1")
    inv_ref = make_ref("invariant_revision", "inv_1")
    ob_ref = make_ref("coverage_obligation", "ob_1")
    cut1 = {"tag": "CUT_001", "commit_seq": 10}

    # 1. Propose
    hyp1 = orch.propose_hypothesis(
        statement="Auth bypass possible on POST /login with null password",
        scope_refs=[surf_ref],
        invariant_refs=[inv_ref],
        obligation_refs=[ob_ref],
        source_generation_ref=src_ref,
        history_cut=cut1,
    )
    assert hyp1.status == "PROPOSED"
    assert hyp1.hypothesis_revision == "1"

    # 2. Preregister before execution
    hyp2 = orch.transition(hyp1, "PREREGISTERED")
    assert hyp2.status == "PREREGISTERED"
    assert hyp2.hypothesis_revision == "2"

    # 3. Move to Testing
    hyp3 = orch.transition(hyp2, "TESTING")
    assert hyp3.status == "TESTING"
    assert hyp3.hypothesis_revision == "3"

    # 4. Confirm with experiment observation
    hyp4 = orch.transition(hyp3, "CONFIRMED")
    assert hyp4.status == "CONFIRMED"
    assert hyp4.hypothesis_revision == "4"

    # Verify history chain preserves all 4 revisions
    chain = orch.get_history_chain(hyp1.hypothesis_id)
    assert len(chain) == 4
    assert [h.status for h in chain] == ["PROPOSED", "PREREGISTERED", "TESTING", "CONFIRMED"]


def test_rejected_hypothesis_preserved_in_history():
    """Rejected hypothesis must remain permanently in history and not be silently dropped."""
    orch = HypothesisOrchestrator()
    src_ref = make_ref("source_identity", "src_1")
    surf_ref = make_ref("surface_record", "surf_1")
    inv_ref = make_ref("invariant_revision", "inv_1")
    ob_ref = make_ref("coverage_obligation", "ob_1")
    cut1 = {"tag": "CUT_001", "commit_seq": 10}

    hyp1 = orch.propose_hypothesis(
        statement="Speculative race condition in cache invalidation",
        scope_refs=[surf_ref],
        invariant_refs=[inv_ref],
        obligation_refs=[ob_ref],
        source_generation_ref=src_ref,
        history_cut=cut1,
    )
    hyp2 = orch.transition(hyp1, "TESTING")
    # Hypothesis refuted by experiment -> REJECTED
    hyp3 = orch.transition(hyp2, "REJECTED")

    chain = orch.get_history_chain(hyp1.hypothesis_id)
    assert len(chain) == 3
    assert chain[-1].status == "REJECTED"

    # Deletion attempt fails closed
    with pytest.raises(ValidationError, match="DELETION_FORBIDDEN"):
        orch.delete_hypothesis(hyp1.hypothesis_id)


def test_retroactive_rewrite_and_preregistration_forbidden():
    """Retroactive in-place rewrite and retroactive preregistration are strictly rejected."""
    orch = HypothesisOrchestrator()
    src_ref = make_ref("source_identity", "src_1")
    surf_ref = make_ref("surface_record", "surf_1")
    inv_ref = make_ref("invariant_revision", "inv_1")
    ob_ref = make_ref("coverage_obligation", "ob_1")
    cut1 = {"tag": "CUT_001", "commit_seq": 10}

    hyp1 = orch.propose_hypothesis(
        statement="Original statement",
        scope_refs=[surf_ref],
        invariant_refs=[inv_ref],
        obligation_refs=[ob_ref],
        source_generation_ref=src_ref,
        history_cut=cut1,
    )

    # Attempting to re-record revision 1 with modified statement raises RETROACTIVE_REWRITE_FORBIDDEN
    hyp1_modified = HypothesisRevision(
        hypothesis_id=hyp1.hypothesis_id,
        hypothesis_revision="1",
        source_generation_ref=src_ref,
        statement="Retroactively rewritten statement",
        scope_refs=[surf_ref],
        invariant_refs=[inv_ref],
        obligation_refs=[ob_ref],
        input_history_cut=cut1,
        status="PROPOSED",
    )
    with pytest.raises(ValidationError, match="RETROACTIVE_REWRITE_FORBIDDEN"):
        orch.record_revision(hyp1_modified)

    # Move to TESTING
    hyp2 = orch.transition(hyp1, "TESTING")
    # Attempting retroactive preregistration while in TESTING raises RETROACTIVE_PREREGISTRATION_FORBIDDEN
    with pytest.raises(ValidationError, match="RETROACTIVE_PREREGISTRATION_FORBIDDEN"):
        orch.transition(hyp2, "PREREGISTERED")


def test_gate_authority_exact_revision_binding_not_latest_shortcut():
    """Gate authority must bind exact revision digest, forbidding mutable latest-by-id shortcuts."""
    orch = HypothesisOrchestrator()
    src_ref = make_ref("source_identity", "src_1")
    surf_ref = make_ref("surface_record", "surf_1")
    inv_ref = make_ref("invariant_revision", "inv_1")
    ob_ref = make_ref("coverage_obligation", "ob_1")
    cut1 = {"tag": "CUT_001", "commit_seq": 10}

    hyp1 = orch.propose_hypothesis(
        statement="Flaky buffer overflow hypothesis",
        scope_refs=[surf_ref],
        invariant_refs=[inv_ref],
        obligation_refs=[ob_ref],
        source_generation_ref=src_ref,
        history_cut=cut1,
    )
    hyp2 = orch.transition(hyp1, "TESTING")
    hyp3 = orch.transition(hyp2, "CONFIRMED")

    # Evaluating gate against exact revision 1 ref: status is PROPOSED -> not satisfied
    eval_rev1 = orch.evaluate_gate_authority(hyp1.as_object().as_ref(), expected_status="CONFIRMED")
    assert eval_rev1["is_satisfied"] is False
    assert eval_rev1["status"] == "PROPOSED"

    # Evaluating gate against exact revision 3 ref: status is CONFIRMED -> satisfied
    eval_rev3 = orch.evaluate_gate_authority(hyp3.as_object().as_ref(), expected_status="CONFIRMED")
    assert eval_rev3["is_satisfied"] is True
    assert eval_rev3["status"] == "CONFIRMED"

    # Non-existent revision ref raises UNKNOWN_HYPOTHESIS_REVISION_REF
    fake_ref = make_ref("hypothesis_revision", "fake_seed")
    with pytest.raises(ValidationError, match="UNKNOWN_HYPOTHESIS_REVISION_REF"):
        orch.evaluate_gate_authority(fake_ref)

"""Targeted tests for Adaptive E6 Generator (PR-E5-11 / M45)."""
import pytest
from jsonschema import Draft202012Validator

from bdb_audit.core.errors import ValidationError
from bdb_audit.stop.e6 import AdaptiveE6Generator, AdaptiveE6Spec
from bdb_audit.stop.models import StopInput, StopEvaluation


def _ref(kind: str, digest_suffix: str, ref_class: str = "CONTENT_OR_PRIOR") -> dict:
    dig = (digest_suffix * 64)[:64]
    return {
        "kind": kind,
        "revision_digest": dig,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
    }


def _accepted_cut(seq: int, hash_char: str, campaign_id: str = "CAMP-001") -> dict:
    return {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": campaign_id,
        "accepted_head_seq": seq,
        "accepted_head_hash": hash_char * 64,
        "governing_policy_ref": "pin:initial_governing_policy_ref",
        "governing_spec_refs": ["pin:initial_transition_profile_ref"],
    }


@pytest.fixture
def base_stop_artifacts():
    hcut = _accepted_cut(25, "a")
    si = StopInput(
        campaign_id="CAMP-001",
        source_generation_ref=_ref("source_generation", "sg"),
        input_history_cut=hcut,
        evaluation_context="FINAL_POST_E5",
        governing_policy_ref=_ref("policy_revision", "p", "HISTORY_CONTEXT_BINDING"),
        policy_spec_refs=[_ref("spec_revision", "sp", "HISTORY_CONTEXT_BINDING")],
        evaluator_revision_ref=_ref("spec_revision", "ev", "HISTORY_CONTEXT_BINDING"),
        required_stage_set_ref=_ref("external_profile_ref", "stg", "HISTORY_CONTEXT_BINDING"),
        required_stage_spec_refs=[_ref("spec_revision", "sp", "HISTORY_CONTEXT_BINDING")],
        completed_stage_refs=[_ref("spec_revision", "sp", "HISTORY_CONTEXT_BINDING")],
        pending_required_stage_refs=[],
        stop_input_snapshot_ref=_ref("snapshot", "sn"),
        inventory_revision_ref=_ref("inventory_revision", "inv"),
        mandatory_obligation_refs=[
            _ref("coverage_obligation", "ob_race"),
            _ref("coverage_obligation", "ob_crash"),
        ],
        current_obligation_qualification_refs=[],
        evidence_invalidation_refs=[],
        contradiction_refs=[_ref("contradiction_revision", "contra_unresolved")],
        residual_risk_refs=[],
        evidence_invalidation_state={"invalidated_count": 0},
        release_policy_ref=_ref("policy_revision", "rp", "HISTORY_CONTEXT_BINDING"),
        effort_profile_ref=_ref("external_profile_ref", "eff", "HISTORY_CONTEXT_BINDING"),
        effort_results_ref={"rounds_executed": 5},
        unknown_blocked_summary={"unknown_surfaces_count": 0, "is_blocked": False},
        candidate_assurance_case_ref=_ref("candidate_assurance_case", "cac"),
        challenger_refs=[_ref("challenger_result", "cr1"), _ref("challenger_result", "cr2")],
    )

    ev_e6 = StopEvaluation(
        stop_input_ref=si.ref,
        continuation_decision="E6_REQUIRED",
        assurance_level="BOUNDED",
        release_readiness="QUALIFICATION_BLOCKED",
        reason_codes=("E6_REQUIRED",),
        blocking_obligation_refs=tuple(si.mandatory_obligation_refs),
        remaining_obligation_refs=tuple(si.mandatory_obligation_refs),
    )

    ev_pass = StopEvaluation(
        stop_input_ref=si.ref,
        continuation_decision="PASS",
        assurance_level="ADEQUATE_FOR_DECLARED_SCOPE",
        release_readiness="READY",
        reason_codes=("ALL_SATISFIED",),
    )

    trust_ref = _ref("trust_profile", "trust", "HISTORY_CONTEXT_BINDING")
    iso_ref = {"kind": "isolation_profile", "revision_digest": "iso_strict", "isolation_level": "STRICT"}

    return {
        "hcut": hcut,
        "stop_input": si,
        "ev_e6": ev_e6,
        "ev_pass": ev_pass,
        "trust_ref": trust_ref,
        "iso_ref": iso_ref,
    }


def test_valid_e6_generator_and_obligation_preservation(base_stop_artifacts):
    ctx = base_stop_artifacts
    e6_spec = AdaptiveE6Generator.generate_e6_spec(
        spec_id="e6_spec_01",
        stop_evaluation=ctx["ev_e6"],
        stop_input=ctx["stop_input"],
        trust_profile_ref=ctx["trust_ref"],
        isolation_profile_ref=ctx["iso_ref"],
    )

    assert e6_spec.e6_stage_spec_id == "e6_spec_01"
    assert e6_spec.e6_input_history_cut == ctx["hcut"]
    # Preserves all unresolved obligations
    assert len(e6_spec.inherited_unresolved_obligations) == 2
    digests = [r["revision_digest"] for r in e6_spec.inherited_unresolved_obligations]
    assert (_ref("coverage_obligation", "ob_race"))["revision_digest"] in digests
    assert (_ref("coverage_obligation", "ob_crash"))["revision_digest"] in digests
    # Preserves contradictions
    assert len(e6_spec.unresolved_contradictions) == 1


def test_e6_rejects_generation_from_non_e6_stop(base_stop_artifacts):
    """E6 generation fails closed if STOP was not E6_REQUIRED."""
    ctx = base_stop_artifacts
    with pytest.raises(ValidationError, match="E6_ONLY_FROM_E6_REQUIRED"):
        AdaptiveE6Generator.generate_e6_spec(
            spec_id="e6_bad",
            stop_evaluation=ctx["ev_pass"],
            stop_input=ctx["stop_input"],
            trust_profile_ref=ctx["trust_ref"],
            isolation_profile_ref=ctx["iso_ref"],
        )


def test_e6_strengthened_obligations(base_stop_artifacts):
    """E6 can add new surfaces, invariants, and obligations to strengthen scope."""
    ctx = base_stop_artifacts
    new_surface = _ref("surface_record", "surf_new_boundary")
    new_invariant = _ref("invariant_revision", "inv_new_temporal")
    new_obligation = _ref("coverage_obligation", "ob_new_composition")

    e6_spec = AdaptiveE6Generator.generate_e6_spec(
        spec_id="e6_strengthened",
        stop_evaluation=ctx["ev_e6"],
        stop_input=ctx["stop_input"],
        trust_profile_ref=ctx["trust_ref"],
        isolation_profile_ref=ctx["iso_ref"],
        added_surfaces=[new_surface],
        added_invariants=[new_invariant],
        added_obligations=[new_obligation],
    )

    assert len(e6_spec.added_surfaces) == 1
    assert len(e6_spec.added_invariants) == 1
    assert len(e6_spec.added_obligations) == 1
    assert len(e6_spec.inherited_unresolved_obligations) == 2


def test_denominator_manipulation_rejected(base_stop_artifacts):
    """Attempt to drop unresolved mandatory obligations to game the denominator fails closed."""
    ctx = base_stop_artifacts
    dropped_dig = (_ref("coverage_obligation", "ob_race"))["revision_digest"]

    with pytest.raises(ValidationError, match="DENOMINATOR_MANIPULATION_FORBIDDEN"):
        AdaptiveE6Generator.generate_e6_spec(
            spec_id="e6_game_denom",
            stop_evaluation=ctx["ev_e6"],
            stop_input=ctx["stop_input"],
            trust_profile_ref=ctx["trust_ref"],
            isolation_profile_ref=ctx["iso_ref"],
            attempted_dropped_obligation_digests={dropped_dig},
        )


def test_isolation_rewrite_rejected(base_stop_artifacts):
    """Attempt to weaken isolation after seeing test failures fails closed."""
    ctx = base_stop_artifacts
    weaker_isolation = {"kind": "isolation_profile", "revision_digest": "iso_weak", "isolation_level": "RELAXED"}

    with pytest.raises(ValidationError, match="ISOLATION_REWRITE_FORBIDDEN"):
        AdaptiveE6Generator.generate_e6_spec(
            spec_id="e6_weaken_iso",
            stop_evaluation=ctx["ev_e6"],
            stop_input=ctx["stop_input"],
            trust_profile_ref=ctx["trust_ref"],
            isolation_profile_ref=ctx["iso_ref"],
            proposed_isolation_profile_ref=weaker_isolation,
        )


def test_post_e6_return_to_stop_advances_canonical_accepted_head(base_stop_artifacts):
    prev_cut = _accepted_cut(25, "a")
    new_head_cut = _accepted_cut(28, "b")
    AdaptiveE6Generator.verify_post_e6_return_to_stop(new_head_cut, prev_cut)

    with pytest.raises(ValidationError, match="POST_E6_MUST_ADVANCE_HEAD"):
        AdaptiveE6Generator.verify_post_e6_return_to_stop(_accepted_cut(25, "a"), prev_cut)

    with pytest.raises(ValidationError, match="POST_E6_MUST_ADVANCE_HEAD"):
        AdaptiveE6Generator.verify_post_e6_return_to_stop(_accepted_cut(28, "a"), prev_cut)


def test_post_e6_return_rejects_legacy_noncanonical_cut() -> None:
    legacy_prev = {"campaign_id": "CAMP-001", "commit_seq": 25, "commit_hash": "a" * 64}
    canonical_new = _accepted_cut(28, "b")

    with pytest.raises(ValidationError, match="ACCEPTED_HISTORY_CUT_REQUIRED"):
        AdaptiveE6Generator.verify_post_e6_return_to_stop(canonical_new, legacy_prev)


def test_post_e6_return_rejects_cross_campaign_transition() -> None:
    prev_cut = _accepted_cut(25, "a", campaign_id="CAMP-001")
    other_campaign = _accepted_cut(28, "b", campaign_id="CAMP-002")

    with pytest.raises(ValidationError, match="POST_E6_CAMPAIGN_MISMATCH"):
        AdaptiveE6Generator.verify_post_e6_return_to_stop(other_campaign, prev_cut)

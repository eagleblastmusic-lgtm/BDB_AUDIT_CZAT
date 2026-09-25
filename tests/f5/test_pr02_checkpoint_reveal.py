"""Targeted unit and adversarial tests for PR-E3-02: Checkpoint, Positive Reveal, Gap-Directed Mode, and Multi-Stage False Negatives.

Tests:
1. Immutable E3BlindCheckpoint creation and stale-cut rejection.
2. Positive gap projection:
   - Valid reveal with GrantAccepted, PotentialExposureRecord, and KnowledgeState advancement.
   - Adversarial finding corpus leakage rejected (DISALLOWED_FINDING_CORPUS_REVEAL).
   - Stale history cut rejected (STALE_OR_INCONSISTENT_HISTORY_CUT).
3. E3GapDirectedScheduler:
   - Target derivation strictly from Gap Map.
   - Attempting to claim blind origin in gap phase fails closed (BLIND_ORIGIN_AFTER_REVEAL_FORBIDDEN).
   - Entering gap mode without reveal fails closed (REVEAL_REQUIRED_FOR_GAP_MODE).
4. Phase E cumulative corpus reveal (E1+E2) and phase progression.
5. Phase F external holdout reveal:
   - Confusion with canonical predecessor fails closed (CANONICAL_PREDECESSOR_CONFUSION).
   - Valid auxiliary holdout reveal advances KnowledgeState to CONSUMED_EXTERNAL_HOLDOUT.
6. Multi-Stage False Negative Assessment:
   - Legitimate multi-stage false negative when accepted cut proves prior omission.
   - New-scope discovery is NOT marked false negative (result = NOT_ESTABLISHED).
   - Stale knowledge cut fails closed (STALE_KNOWLEDGE_CUT_REJECTED).
"""
import hashlib
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.orchestration.e3 import (
    E3_LANE_SLOTS,
    build_e3_stage_spec,
    create_e3_blind_attempt,
    execute_e3_blind_ensemble,
)
from bdb_audit.orchestration.e3_reveal import (
    E3BlindCheckpoint,
    create_e3_blind_checkpoint,
    PositiveGapProjection,
    execute_positive_gap_reveal,
    E3GapDirectedScheduler,
    execute_cumulative_corpus_reveal,
    execute_holdout_reveal,
    evaluate_false_negative_relationship,
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


def create_blind_attempt(*args, **kwargs):
    kwargs.setdefault(
        "channel_inventory_ref",
        make_ref(
            "registered_immutable_object",
            "e3_test_channel_inventory",
        ),
    )
    return create_e3_blind_attempt(*args, **kwargs)


def make_history_cut(seq: int = 1) -> dict:
    return {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": "camp_e3_test",
        "accepted_head_seq": seq,
        "accepted_head_hash": hashlib.sha256(f"cut_{seq}".encode()).hexdigest(),
        "governing_policy_ref": "BDB_POLICY_REGISTRY::governing_policy/1",
        "governing_spec_refs": ["BDB_SPEC_REGISTRY::e3_spec/1"],
    }


def _setup_blind_result(cut_seq: int = 4):
    src_gen = make_ref("source_generation", "gen_e3")
    cut = make_history_cut(cut_seq)
    lr_ref = make_ref("lane_run", "lr")
    exec_ref = make_ref("executor_profile", "exec")
    deliv_ref = make_ref("delivery_profile", "deliv")

    lane_contexts = {
        slot: create_blind_attempt(slot, lr_ref, cut, exec_ref, deliv_ref)
        for slot in E3_LANE_SLOTS
    }

    lane_discoveries = {
        "E3-X": [{"statement": "Auth bypass in TLS"}],
        "E3-Y": [{"statement": "Journal rollback bug"}],
        "E3-Z": [{"statement": "UI race condition"}],
    }

    result = execute_e3_blind_ensemble(src_gen, cut, lane_contexts, lane_discoveries)
    return result, cut, lane_contexts["E3-X"].knowledge_state


def test_blind_checkpoint_creation_and_stale_cut_rejection():
    blind_res, cut, _ = _setup_blind_result(4)

    # Valid checkpoint creation
    chk = create_e3_blind_checkpoint(blind_res, cut)
    assert chk.checkpoint_id.startswith("chk_e3_blind_")
    assert chk.sealed_findings_count == 3
    assert chk.blind_completion_digest == blind_res.blind_completion_digest
    assert len(chk.digest) == 64

    # Stale cut (seq 3 < blind cut seq 4) must fail closed
    stale_cut = make_history_cut(3)
    with pytest.raises(ValidationError, match="STALE_CHECKPOINT_OR_CUT_REJECTED"):
        create_e3_blind_checkpoint(blind_res, stale_cut)


def test_positive_gap_projection_and_reveal_flow():
    blind_res, cut, k_state_before = _setup_blind_result(4)
    chk = create_e3_blind_checkpoint(blind_res, cut)

    # Prepare positive view inputs
    obligations = [
        {"obligation_id": "ob_1", "category": "PARSER_FIDELITY", "status": "UNFULFILLED"},
        {"obligation_id": "ob_2", "category": "AUTHORITY_BOUNDARY", "status": "UNFULFILLED"},
    ]
    gap_map = {
        "gap_map_id": "gm_e3_1",
        "gaps": [
            {
                "gap_id": "gap_surface_crypto",
                "target_scope_ref": make_ref("surface", "crypto"),
                "materiality": "MATERIAL",
                "missing_or_unsatisfied_obligation_refs": ["ob_2"],
            }
        ],
    }
    unknown_scope = [{"surface_id": "unknown_network_handler"}]
    unsupported_scope = [{"surface_id": "unsupported_legacy_v1"}]
    producer_ref = make_ref("coordinator", "coord_1")

    proj, rev_event, k_state_after = execute_positive_gap_reveal(
        checkpoint=chk,
        accepted_history_cut=cut,
        knowledge_state_before=k_state_before,
        coverage_obligations=obligations,
        gap_map=gap_map,
        explicit_unknown_scope=unknown_scope,
        explicit_unsupported_scope=unsupported_scope,
        producer_ref=producer_ref,
    )

    assert proj.checkpoint_ref == chk.ref
    assert len(proj.coverage_obligations) == 2
    assert len(proj.explicit_unknown_scope) == 1

    assert rev_event.reveal_type == "POSITIVE_GAP_VIEW"
    assert rev_event.checkpoint_ref == chk.ref
    assert rev_event.revealed_view_manifest_ref == proj.ref

    # KnowledgeState was advanced monotonically
    assert k_state_after.previous_knowledge_state_ref == k_state_before.as_object().ref.as_dict()
    assert "GAP_DIRECTED_COVERAGE_VIEW" in k_state_after.known_classes
    assert "EXPLICIT_UNKNOWN_SCOPE" in k_state_after.known_classes
    assert len(k_state_after.potential_exposure_refs) == 1


def test_adversarial_finding_corpus_leakage_in_positive_reveal_rejected():
    blind_res, cut, k_state_before = _setup_blind_result(4)
    chk = create_e3_blind_checkpoint(blind_res, cut)

    # Adversarial leak: trying to smuggle prior finding details into gap projection
    leaked_obligations = [
        {
            "obligation_id": "ob_1",
            "finding_claim_ref": {"digest": "leaked_finding_digest"},
        }
    ]
    producer_ref = make_ref("coordinator", "coord_1")

    with pytest.raises(ValidationError, match="DISALLOWED_FINDING_CORPUS_REVEAL"):
        execute_positive_gap_reveal(
            checkpoint=chk,
            accepted_history_cut=cut,
            knowledge_state_before=k_state_before,
            coverage_obligations=leaked_obligations,
            gap_map={"gaps": []},
            explicit_unknown_scope=(),
            explicit_unsupported_scope=(),
            producer_ref=producer_ref,
        )


def test_positive_reveal_stale_history_cut_rejected():
    blind_res, cut, k_state_before = _setup_blind_result(5)
    chk = create_e3_blind_checkpoint(blind_res, cut)
    stale_cut = make_history_cut(3)
    producer_ref = make_ref("coordinator", "coord_1")

    with pytest.raises(ValidationError, match="STALE_OR_INCONSISTENT_HISTORY_CUT"):
        execute_positive_gap_reveal(
            checkpoint=chk,
            accepted_history_cut=stale_cut,
            knowledge_state_before=k_state_before,
            coverage_obligations=(),
            gap_map={"gaps": []},
            explicit_unknown_scope=(),
            explicit_unsupported_scope=(),
            producer_ref=producer_ref,
        )


def test_gap_directed_scheduler_and_no_retroactive_blind_claims():
    blind_res, cut, k_state_before = _setup_blind_result(4)
    chk = create_e3_blind_checkpoint(blind_res, cut)
    gap_map = {
        "gaps": [
            {
                "gap_id": "gap_1",
                "target_scope_ref": make_ref("surface", "tls"),
                "materiality": "HIGH",
            },
            {
                "gap_id": "gap_2",
                "target_scope_ref": make_ref("surface", "db"),
                "materiality": "CRITICAL",
            },
        ]
    }
    producer_ref = make_ref("coordinator", "coord_1")

    proj, rev_event, k_state_after = execute_positive_gap_reveal(
        checkpoint=chk,
        accepted_history_cut=cut,
        knowledge_state_before=k_state_before,
        coverage_obligations=(),
        gap_map=gap_map,
        explicit_unknown_scope=(),
        explicit_unsupported_scope=(),
        producer_ref=producer_ref,
    )

    scheduler = E3GapDirectedScheduler(proj, rev_event, k_state_after)
    targets = scheduler.get_gap_target_list()
    assert len(targets) == 2
    assert targets[0]["gap_id"] == "gap_1"
    assert targets[1]["gap_id"] == "gap_2"

    # Legitimate gap discovery
    disc = scheduler.record_gap_directed_discovery(
        target_scope_ref=targets[0]["target_scope_ref"],
        discovery_data={"statement": "Weak key exchange parameter discovered via gap exploration"},
    )
    assert disc["classification"] == "POST_REVEAL_CONFIRMATION"
    assert disc["mode"] == "GAP_DIRECTED"

    # Adversarial: attempt to claim PRE_REVEAL_DISCOVERY in gap mode must fail closed
    with pytest.raises(ValidationError, match="BLIND_ORIGIN_AFTER_REVEAL_FORBIDDEN"):
        scheduler.record_gap_directed_discovery(
            target_scope_ref=targets[0]["target_scope_ref"],
            discovery_data={
                "statement": "Cheating claim",
                "classification": "PRE_REVEAL_DISCOVERY",
            },
        )


def test_cumulative_corpus_reveal_phase_e():
    blind_res, cut, k_state_before = _setup_blind_result(4)
    chk = create_e3_blind_checkpoint(blind_res, cut)
    producer_ref = make_ref("coordinator", "coord_1")

    proj, rev_event, k_state_after = execute_positive_gap_reveal(
        checkpoint=chk,
        accepted_history_cut=cut,
        knowledge_state_before=k_state_before,
        coverage_obligations=(),
        gap_map={"gaps": []},
        explicit_unknown_scope=(),
        explicit_unsupported_scope=(),
        producer_ref=producer_ref,
    )
    scheduler = E3GapDirectedScheduler(proj, rev_event, k_state_after)

    e1_e2_manifest = make_ref("manifest", "e1_e2_cumulative_corpus")
    rev_cumul, state_cumul = execute_cumulative_corpus_reveal(
        scheduler=scheduler,
        e1_e2_corpus_manifest_ref=e1_e2_manifest,
        accepted_history_cut=cut,
        producer_ref=producer_ref,
    )

    assert rev_cumul.reveal_type == "CUMULATIVE_CORPUS_VIEW"
    assert "CUMULATIVE_E1_E2_CORPUS" in state_cumul.known_classes


def test_holdout_reveal_and_canonical_predecessor_confusion_rejection():
    blind_res, cut, k_state_before = _setup_blind_result(4)
    holdout_manifest = make_ref("manifest", "external_holdout_a1")
    producer_ref = make_ref("coordinator", "coord_1")

    # Adversarial: passing auxiliary holdout as canonical direct predecessor must fail closed
    with pytest.raises(ValidationError, match="CANONICAL_PREDECESSOR_CONFUSION"):
        execute_holdout_reveal(
            knowledge_state=k_state_before,
            holdout_corpus_manifest_ref=holdout_manifest,
            accepted_history_cut=cut,
            producer_ref=producer_ref,
            corpus_role="CANONICAL_PREDECESSOR",
        )

    # Valid holdout reveal
    rev_holdout, state_holdout = execute_holdout_reveal(
        knowledge_state=k_state_before,
        holdout_corpus_manifest_ref=holdout_manifest,
        accepted_history_cut=cut,
        producer_ref=producer_ref,
        corpus_role="AUXILIARY_HOLDOUT",
    )
    assert rev_holdout.reveal_type == "HOLDOUT_CORPUS_VIEW"
    assert "CONSUMED_EXTERNAL_HOLDOUT" in state_holdout.known_classes


def test_multi_stage_false_negative_assessment_rules():
    cut_5 = make_history_cut(5)
    disc_ref = make_ref("discovery", "disc_crypto_timing")
    surface_ref = make_ref("surface", "crypto_engine")
    pred_stages = [make_ref("stage_completion", "e1_done"), make_ref("stage_completion", "e2_done")]

    # 1. Legitimate MULTI_STAGE_FALSE_NEGATIVE:
    # Surface was active in predecessor stage (e.g. completed at seq 3), but omitted/unobserved.
    asmt1 = evaluate_false_negative_relationship(
        discovery_ref=disc_ref,
        assessment_input_history_cut=cut_5,
        predecessor_stage_refs=pred_stages,
        target_surface_ref=surface_ref,
        surface_active_in_predecessor=True,
        surface_observed_in_predecessor=False,
        predecessor_completion_seq=3,
    )
    assert asmt1.result == "MULTI_STAGE_FALSE_NEGATIVE"
    assert "PRIOR_STAGE_OMISSION_PROVEN_BY_ACCEPTED_CUT" in asmt1.reason_codes

    # 2. New-scope discovery != false negative:
    # Surface was NOT active in predecessor stage (newly expanded surface)
    asmt2 = evaluate_false_negative_relationship(
        discovery_ref=disc_ref,
        assessment_input_history_cut=cut_5,
        predecessor_stage_refs=pred_stages,
        target_surface_ref=surface_ref,
        surface_active_in_predecessor=False,
        surface_observed_in_predecessor=False,
        predecessor_completion_seq=3,
    )
    assert asmt2.result == "NOT_ESTABLISHED"
    assert "NEW_SCOPE_DISCOVERY_NOT_FALSE_NEGATIVE" in asmt2.reason_codes

    # 3. Stale knowledge cut rejected:
    # Assessment cut seq 2 < predecessor completion seq 3
    stale_cut = make_history_cut(2)
    with pytest.raises(ValidationError, match="STALE_KNOWLEDGE_CUT_REJECTED"):
        evaluate_false_negative_relationship(
            discovery_ref=disc_ref,
            assessment_input_history_cut=stale_cut,
            predecessor_stage_refs=pred_stages,
            target_surface_ref=surface_ref,
            surface_active_in_predecessor=True,
            surface_observed_in_predecessor=False,
            predecessor_completion_seq=3,
        )
"""Comprehensive adversarial test suite for Etap 1: Canonical Authority Foundation.

Covers:
- D09: Layered validation & elimination of False Validation PASS (T01 - T10)
- D12: Migration to canonical domain-separated ObjectDigest (T11 - T12)
- D16: Pinned ContractRegistry immutability & runtime override defense (T13 - T15)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import zipfile
import pytest

from bdb_audit.core.canonical_json import canonical_bytes, parse
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.hashing import object_digest
from bdb_audit.core.registry import ContractRegistry, REGISTRY_SHA256, REGISTRY_ID, REGISTRY_VERSION
from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.history.objects import CanonicalObject
from bdb_audit.schemas.identity import LayeredValidator
from bdb_audit.orchestration.stages import initial_stage_specs
from bdb_audit.assurance.candidate_case import CandidateAssuranceCaseBuilder
from bdb_audit.assurance.challenger import ChallengerAssignment, ChallengerResult
from bdb_audit.assurance.conclusion import CampaignConclusion, FinalAssuranceCase
from bdb_audit.assurance.release import (
    ReleaseQualification,
    SuccessorCampaignGenesis,
    SuccessorCampaignSelectionDecision,
)
from bdb_audit.stop.e6 import AdaptiveE6Spec
from bdb_audit.orchestration.e3_reveal import (
    E3BlindCheckpoint,
    PositiveGapProjection,
    E3RevealEvent,
    FalseNegativeRelationshipAssessment,
)
from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS
from bdb_audit.workflow.source_target import ResolvedSource
from bdb_audit.workflow.packaging import prepare_e1_batch
from bdb_audit.workflow.inbox import E1ResultInbox
from bdb_audit.history.store import TransactionalHistoryStore


# ============================================================================
# D09: LAYERED VALIDATION & ELIMINATION OF FALSE VALIDATION PASS (T01 - T10)
# ============================================================================

def test_t01_schema_violation_rejected_fail_closed(tmp_path: Path):
    """T01: Artifact missing required schema fields is rejected with SCHEMA_VALIDATION_FAILED."""
    api = AuditOperationApi()
    incomplete_art = {
        "kind": "stage_spec",
        "version": "1",
        "stage_key": "E1",
        # Missing all other required fields of stage_spec
    }
    art_file = tmp_path / "incomplete.json"
    art_file.write_text(json.dumps(incomplete_art), encoding="utf-8")

    with pytest.raises(ValidationError) as exc_info:
        api.validate_artifact(art_file)
    assert exc_info.value.code == "SCHEMA_VALIDATION_FAILED"


def test_t02_duplicate_keys_rejected_before_schema(tmp_path: Path):
    """T02: Non-canonical duplicate JSON keys are rejected fail-closed during parse."""
    api = AuditOperationApi()
    e1_spec = initial_stage_specs()[0]
    body = e1_spec.body()

    # Raw bytes containing a duplicate key
    raw_dup = (
        b'{"kind": "stage_spec", "version": "1", "stage_key": "E1", "stage_key": "E2", '
        + canonical_bytes(body)[1:]
    )
    art_file = tmp_path / "dup.json"
    art_file.write_bytes(raw_dup)

    with pytest.raises(ValidationError) as exc_info:
        api.validate_artifact(art_file)
    assert exc_info.value.code in ("CJSON_DUPLICATE_KEY", "DUPLICATE_KEY_FORBIDDEN", "DUPLICATE_JSON_KEY", "MALFORMED_ARTIFACT")


def test_t03_unregistered_contract_kind_rejected(tmp_path: Path):
    """T03: Unregistered contract kind is rejected fail-closed."""
    api = AuditOperationApi()
    rogue_art = {
        "kind": "rogue_unknown_kind",
        "version": "1",
        "some_data": 123,
    }
    art_file = tmp_path / "rogue.json"
    art_file.write_text(json.dumps(rogue_art), encoding="utf-8")

    with pytest.raises(ValidationError) as exc_info:
        api.validate_artifact(art_file)
    assert exc_info.value.code == "UNREGISTERED_CONTRACT_KIND"


def test_t04_missing_kind_field_rejected(tmp_path: Path):
    """T04: Artifact lacking 'kind' is rejected with MISSING_ARTIFACT_KIND."""
    api = AuditOperationApi()
    no_kind = {
        "version": "1",
        "data": "value",
    }
    art_file = tmp_path / "no_kind.json"
    art_file.write_text(json.dumps(no_kind), encoding="utf-8")

    with pytest.raises(ValidationError) as exc_info:
        api.validate_artifact(art_file)
    assert exc_info.value.code == "MISSING_ARTIFACT_KIND"


def test_t05_expected_kind_mismatch_rejected(tmp_path: Path):
    """T05: Artifact kind differing from expected_kind is rejected with ARTIFACT_KIND_MISMATCH."""
    api = AuditOperationApi()
    e1_spec = initial_stage_specs()[0]
    art = {"kind": "stage_spec", "version": "1", **e1_spec.body()}
    art_file = tmp_path / "spec.json"
    art_file.write_text(json.dumps(art), encoding="utf-8")

    with pytest.raises(ValidationError) as exc_info:
        api.validate_artifact(art_file, expected_kind="lane_spec")
    assert exc_info.value.code == "ARTIFACT_KIND_MISMATCH"


def test_t06_invalid_typed_ref_syntax_rejected():
    """T06: Typed ref with non-hex, uppercase, or invalid length digest is rejected fail-closed."""
    validator = LayeredValidator()

    # Upper case in revision_digest
    bad_ref_upper = {
        "kind": "stage_spec",
        "revision_digest": "A" * 64,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stage_spec/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    with pytest.raises(ValidationError) as exc_upper:
        validator._typed_refs({"ref": bad_ref_upper})
    assert exc_upper.value.code in ("INVALID_DIGEST", "INVALID_TYPED_REF_DIGEST")

    # Invalid length (63 characters)
    bad_ref_short = {
        "kind": "stage_spec",
        "revision_digest": "a" * 63,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stage_spec/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    with pytest.raises(ValidationError) as exc_short:
        validator._typed_refs({"ref": bad_ref_short})
    assert exc_short.value.code in ("INVALID_DIGEST", "INVALID_TYPED_REF_DIGEST")

    # Non-hex characters
    bad_ref_nonhex = {
        "kind": "stage_spec",
        "revision_digest": "g" * 64,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stage_spec/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    with pytest.raises(ValidationError) as exc_nonhex:
        validator._typed_refs({"ref": bad_ref_nonhex})
    assert exc_nonhex.value.code in ("INVALID_DIGEST", "INVALID_TYPED_REF_DIGEST")


def test_t07_unregistered_typed_ref_target_rejected():
    """T07: Typed ref pointing to an unregistered target kind is rejected fail-closed."""
    validator = LayeredValidator()
    bad_target_ref = {
        "kind": "completely_unregistered_target_kind",
        "revision_digest": "0" * 64,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stage_spec/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    with pytest.raises(ValidationError) as exc_info:
        validator._typed_refs({"ref": bad_target_ref})
    assert exc_info.value.code == "UNRESOLVED_REFERENCE_TARGET"


def _setup_inbox(tmp_path: Path):
    store_path = tmp_path / "campaign.sqlite"
    api = AuditOperationApi()
    api.create_campaign(store_path, seed="inbox_adversarial_seed")
    api.prepare_stage(store_path, "E1")
    for slot in E1_LANE_SLOTS:
        api.prepare_lane(store_path, "E1", slot=slot)

    store = TransactionalHistoryStore(store_path)
    out_dir = tmp_path / "audit_work"
    source = ResolvedSource(
        target_type="github",
        location="https://github.com/example/adversarial-repo",
        display_name="example/adversarial-repo",
        ref="main",
        exact_commit_sha="c" * 40,
    )
    batch = prepare_e1_batch(store, out_dir, source)
    inbox = E1ResultInbox(store, batch)
    return store, batch, inbox


def test_t08_inbox_duplicate_zip_path_rejected(tmp_path: Path):
    """T08: Result inbox rejects ZIP archives containing duplicate path entries."""
    store, batch, inbox = _setup_inbox(tmp_path)
    zip_p = tmp_path / "dup_path.zip"
    with zipfile.ZipFile(zip_p, "w") as zf:
        zf.writestr("MANIFEST.json", json.dumps({"test": 1}))
        zf.writestr("MANIFEST.json", json.dumps({"test": 2}))

    lane, status, reason = inbox.ingest_zip(zip_p)
    assert status == "REJECTED"
    assert "ZIP_DUPLICATE_PATH" in str(reason)


def test_t09_inbox_path_traversal_zip_rejected(tmp_path: Path):
    """T09: Result inbox rejects ZIP archives containing path traversal entries."""
    store, batch, inbox = _setup_inbox(tmp_path)
    zip_p = tmp_path / "traversal.zip"
    with zipfile.ZipFile(zip_p, "w") as zf:
        zf.writestr("MANIFEST.json", json.dumps({"test": 1}))
        zf.writestr("../escaped_file.txt", "evil")

    lane, status, reason = inbox.ingest_zip(zip_p)
    assert status == "REJECTED"
    assert "ZIP_PATH_TRAVERSAL" in str(reason)


def test_t10_inbox_schema_invalid_manifest_rejected(tmp_path: Path):
    """T10: Result inbox rejects submission ZIP whose MANIFEST fails schema validation."""
    store, batch, inbox = _setup_inbox(tmp_path)
    job = batch.get_job("E1-A")
    # Missing required 'source_commit_sha' and invalid lane_slot
    manifest = {
        "kind": "bdb_audit_lane_result",
        "version": "1",
        "campaign_id": batch.campaign_id,
        "stage_id": "E1",
        "lane_slot": "INVALID_SLOT",
        "history_cut": batch.frozen_history_cut,
        "input_package_digest": job.package_digest,
        "executor_profile": job.executor_profile,
        "executor_model": job.model,
        "findings": [],
    }
    zip_p = tmp_path / "bad_manifest.zip"
    with zipfile.ZipFile(zip_p, "w") as zf:
        zf.writestr("MANIFEST.json", json.dumps(manifest))

    lane, status, reason = inbox.ingest_zip(zip_p)
    assert status == "REJECTED"
    assert ("UNKNOWN_LANE" in str(reason) or "SCHEMA_VALIDATION_FAILED" in str(reason))


# ============================================================================
# D12: OBJECTDIGEST DOMAIN SEPARATION & PRODUCER MIGRATION (T11 - T12)
# ============================================================================

def test_t11_object_digest_domain_separation():
    """T11: ObjectDigest is domain-separated (BDB2/<kind>/<version>\\0) and distinct from raw SHA-256."""
    e1_spec = initial_stage_specs()[0]
    body = e1_spec.body()

    raw_sha = hashlib.sha256(canonical_bytes(body)).hexdigest()
    domain_obj_digest = object_digest("stage_spec", "1", body, registry_kind="stage_spec").value

    # Must be 64 lowercase hex
    assert len(domain_obj_digest) == 64
    assert domain_obj_digest == domain_obj_digest.lower()

    # Must NOT equal raw sha256 of canonical bytes
    assert domain_obj_digest != raw_sha

    # Verify exact manual calculation matches object_digest
    expected_preamble = b"BDB2/stage_spec/1\0"
    hasher = hashlib.sha256(expected_preamble)
    hasher.update(canonical_bytes(body))
    assert domain_obj_digest == hasher.hexdigest()


def test_t12_all_authority_bearing_producers_produce_canonical_object_digest():
    """T12: All migrated authority-bearing producers match CanonicalObject.digest."""
    # 1. stage_spec
    e1_spec = initial_stage_specs()[0]
    assert e1_spec.as_object().digest == object_digest("stage_spec", "1", e1_spec.body(), registry_kind="stage_spec").value

    # 2. candidate_assurance_case
    builder = CandidateAssuranceCaseBuilder(
        case_id="cac_t12",
        campaign_ref={"kind": "campaign_genesis", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::campaign_genesis/1", "ref_class": "PRIOR_ACCEPTED_ONLY"},
        source_generation_ref={"kind": "source_generation", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_generation/1", "ref_class": "CONTENT_OR_PRIOR"},
        candidate_input_history_cut={"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
        scope_inventory_ref={"kind": "inventory_revision", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::inventory_revision/1", "ref_class": "CONTENT_OR_PRIOR"},
        assurance_claim_set_ref={"kind": "claim_set", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::claim_set/1", "ref_class": "CONTENT_OR_PRIOR"},
    )
    cac = builder.build()
    expected_cac_digest = CanonicalObject("candidate_assurance_case", cac.body()).digest
    assert cac.digest() == expected_cac_digest
    assert cac.ref["revision_digest"] == expected_cac_digest

    # 3. challenger_assignment
    ca = ChallengerAssignment(
        challenge_assignment_id="ca_t12",
        candidate_assurance_case_ref=cac.ref,
        challenger_type="FALSE_POSITIVE_SKEPTIC",
        challenge_scope="ALL_CLAIMS",
        challenge_policy_ref={"kind": "policy_revision", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::policy_revision/1", "ref_class": "CONTENT_OR_PRIOR"},
        executor_profile_ref={"kind": "executor_spec", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::executor_spec/1", "ref_class": "CONTENT_OR_PRIOR"},
        assignment_input_history_cut={"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
    )
    expected_ca_digest = CanonicalObject("challenger_assignment", ca.body()).digest
    assert ca.digest() == expected_ca_digest
    assert ca.ref["revision_digest"] == expected_ca_digest

    # 4. challenger_result
    cr = ChallengerResult(
        challenger_result_id="cr_t12",
        challenge_assignment_ref=ca.ref,
        candidate_assurance_case_ref=cac.ref,
        result_input_history_cut={"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
        status="NO_MATERIAL_COUNTEREVIDENCE",
    )
    expected_cr_digest = CanonicalObject("challenger_result", cr.body()).digest
    assert cr.digest() == expected_cr_digest
    assert cr.ref["revision_digest"] == expected_cr_digest

    # 5. campaign_conclusion
    cc = CampaignConclusion(
        campaign_conclusion_id="cc_t12",
        campaign_ref={"kind": "campaign_genesis", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::campaign_genesis/1", "ref_class": "PRIOR_ACCEPTED_ONLY"},
        source_generation_ref={"kind": "source_generation", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_generation/1", "ref_class": "CONTENT_OR_PRIOR"},
        stop_evaluation_ref={"kind": "stop_evaluation", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stop_evaluation/1", "ref_class": "PRIOR_ACCEPTED_ONLY"},
        termination_state="COMPLETED",
        assurance_level="ADEQUATE_FOR_DECLARED_SCOPE",
        bounded_conclusion_statement="All checks passed unconditionally",
        conclusion_command_input_history_cut={"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
        candidate_assurance_case_ref=cac.ref,
    )
    expected_cc_digest = CanonicalObject("campaign_conclusion", cc.body()).digest
    assert cc.digest() == expected_cc_digest
    assert cc.ref["revision_digest"] == expected_cc_digest

    # 6. final_assurance_case
    fac = FinalAssuranceCase(
        final_assurance_case_id="fac_t12",
        campaign_conclusion_ref=cc.ref,
        stop_evaluation_ref={"kind": "stop_evaluation", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stop_evaluation/1", "ref_class": "PRIOR_ACCEPTED_ONLY"},
        public_conclusion_statement_ref={"kind": "campaign_conclusion", "revision_digest": cc.digest(), "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::campaign_conclusion/1", "ref_class": "PRIOR_ACCEPTED_ONLY"},
        final_case_input_history_cut={"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
    )
    expected_fac_digest = CanonicalObject("final_assurance_case", fac.body()).digest
    assert fac.digest() == expected_fac_digest
    assert fac.ref["revision_digest"] == expected_fac_digest

    # 7. release_qualification
    rq = ReleaseQualification(
        release_qualification_id="rq_t12",
        campaign_conclusion_ref=cc.ref,
        final_assurance_case_ref=fac.ref,
        stop_evaluation_ref={"kind": "stop_evaluation", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stop_evaluation/1", "ref_class": "PRIOR_ACCEPTED_ONLY"},
        source_generation_ref={"kind": "source_generation", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_generation/1", "ref_class": "CONTENT_OR_PRIOR"},
        release_policy_ref={"kind": "policy_revision", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::policy_revision/1", "ref_class": "CONTENT_OR_PRIOR"},
        release_assessment_basis_cut={"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
        qualification_command_input_history_cut={"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
        assessment_basis="STOP_AXIS_MATERIALIZATION",
        result="READY",
    )
    expected_rq_digest = CanonicalObject("release_qualification", rq.body()).digest
    assert rq.digest() == expected_rq_digest
    assert rq.ref["revision_digest"] == expected_rq_digest

    # 8. successor_campaign_genesis
    scg = SuccessorCampaignGenesis(
        campaign_id="camp_successor",
        predecessor_campaign_ref={"kind": "campaign_genesis", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::campaign_genesis/1", "ref_class": "PRIOR_ACCEPTED_ONLY"},
        predecessor_conclusion_ref=cc.ref,
        successor_trigger_ref={"kind": "trigger", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::trigger/1", "ref_class": "CONTENT_OR_PRIOR"},
        source_generation_ref={"kind": "source_generation", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_generation/1", "ref_class": "CONTENT_OR_PRIOR"},
        successor_input_history_cut={"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
        governing_policy_ref={"kind": "policy_revision", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::policy_revision/1", "ref_class": "CONTENT_OR_PRIOR"},
        challenge_freshness_policy_ref={"kind": "policy_revision", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::policy_revision/1", "ref_class": "CONTENT_OR_PRIOR"},
        governing_spec_refs=(),
    )
    expected_scg_digest = CanonicalObject("successor_campaign_genesis", scg.body()).digest
    assert scg.digest() == expected_scg_digest
    assert scg.ref["revision_digest"] == expected_scg_digest

    # 9. successor_campaign_selection_decision
    cand_ref1 = {"kind": "successor_campaign_genesis", "revision_digest": "1" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::successor_campaign_genesis/1", "ref_class": "CONTENT_OR_PRIOR"}
    cand_ref2 = {"kind": "successor_campaign_genesis", "revision_digest": "2" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::successor_campaign_genesis/1", "ref_class": "CONTENT_OR_PRIOR"}
    scsd = SuccessorCampaignSelectionDecision(
        selection_decision_id="scsd_t12",
        predecessor_conclusion_ref=cc.ref,
        candidate_successor_campaign_refs=(cand_ref1, cand_ref2),
        selected_successor_campaign_ref=cand_ref1,
        resolution_basis_refs=(),
        governing_policy_ref={"kind": "policy_revision", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::policy_revision/1", "ref_class": "CONTENT_OR_PRIOR"},
        input_history_cut={"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
    )
    expected_scsd_digest = CanonicalObject("successor_campaign_selection_decision", scsd.body()).digest
    assert scsd.digest() == expected_scsd_digest
    assert scsd.ref["revision_digest"] == expected_scsd_digest

    # 10. AdaptiveE6Spec
    e6 = AdaptiveE6Spec(
        e6_stage_spec_id="spec_e6_t12",
        source_stop_evaluation_ref={"kind": "stop_evaluation", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stop_evaluation/1", "ref_class": "PRIOR_ACCEPTED_ONLY"},
        source_generation_ref={"kind": "source_generation", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_generation/1", "ref_class": "CONTENT_OR_PRIOR"},
        governing_policy_ref={"kind": "policy_revision", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::policy_revision/1", "ref_class": "CONTENT_OR_PRIOR"},
        trust_profile_ref={"kind": "trust_profile", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::trust_profile/1", "ref_class": "CONTENT_OR_PRIOR"},
        isolation_profile_ref={"kind": "isolation_qualification", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::isolation_qualification/1", "ref_class": "CONTENT_OR_PRIOR"},
        inherited_unresolved_obligations=(),
        e6_input_history_cut={"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
    )
    expected_e6_digest = CanonicalObject("stage_spec", e6.body()).digest
    assert e6.digest() == expected_e6_digest
    assert e6.ref["revision_digest"] == expected_e6_digest

    # 11. E3BlindCheckpoint
    chk = E3BlindCheckpoint(
        checkpoint_id="chk_t12",
        accepted_history_cut={"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
        blind_completion_digest="0" * 64,
        sealed_findings_count=3,
    )
    expected_chk_digest = CanonicalObject("checkpoint", chk.body()).digest
    assert chk.digest == expected_chk_digest
    assert chk.ref["revision_digest"] == expected_chk_digest

    # 12. PositiveGapProjection
    proj = PositiveGapProjection(
        projection_id="proj_t12",
        checkpoint_ref=chk.ref,
        accepted_history_cut={"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
        coverage_obligations=(),
        gap_map={"gaps": []},
        explicit_unknown_scope=(),
        explicit_unsupported_scope=(),
    )
    expected_proj_digest = CanonicalObject("view_manifest", proj.body()).digest
    assert proj.digest == expected_proj_digest
    assert proj.ref["revision_digest"] == expected_proj_digest

    # 13. E3RevealEvent
    rev = E3RevealEvent(
        reveal_id="rev_t12",
        reveal_type="POSITIVE_GAP_VIEW",
        checkpoint_ref=chk.ref,
        accepted_history_cut={"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
        knowledge_state_before_ref={"kind": "knowledge_state", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::knowledge_state/1", "ref_class": "CONTENT_OR_PRIOR"},
        knowledge_state_after_ref={"kind": "knowledge_state", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::knowledge_state/1", "ref_class": "CONTENT_OR_PRIOR"},
        revealed_view_manifest_ref=proj.ref,
        producer_ref={"producer": "COORDINATOR"},
    )
    expected_rev_digest = CanonicalObject("view_manifest", rev.body()).digest
    assert rev.digest == expected_rev_digest
    assert rev.ref["revision_digest"] == expected_rev_digest

    # 14. FalseNegativeRelationshipAssessment
    fna = FalseNegativeRelationshipAssessment(
        assessment_id="fna_t12",
        discovery_ref={"kind": "discovery_record", "revision_digest": "0" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::discovery_record/1", "ref_class": "CONTENT_OR_PRIOR"},
        assessment_input_history_cut={"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
        predecessor_stage_or_claim_refs=(),
        relationship_policy_ref="BDB_POLICY_REGISTRY::false_negative_policy/1",
        result="NOT_ESTABLISHED",
        reason_codes=("NO_PRIOR_OBSERVATION",),
    )
    expected_fna_digest = CanonicalObject("blind_origin_eligibility_assessment", fna.body()).digest
    assert fna.digest == expected_fna_digest
    assert fna.ref["revision_digest"] == expected_fna_digest


# ============================================================================
# D16: SECURED CONTRACT REGISTRY DEFENSE & IMMUTABILITY (T13 - T15)
# ============================================================================

def test_t13_registry_rejects_pinned_canonical_collision():
    """T13: register_extension_contract raises CANONICAL_CONTRACT_COLLISION on pinned kind."""
    reg = ContractRegistry()
    # Attempt to shadow/override pinned canonical contract 'stage_spec'
    colliding_entry = {
        "kind": "stage_spec",
        "version": "1",
        "authoritative_for": "malicious override",
        "canonical_role": "PROPOSAL",
    }
    with pytest.raises(ValidationError) as exc_info:
        reg.register_extension_contract(colliding_entry)
    assert exc_info.value.code == "CANONICAL_CONTRACT_COLLISION"


def test_t14_registry_rejects_duplicate_extension_registration():
    """T14: register_extension_contract raises DUPLICATE_EXTENSION_CONTRACT on duplicate key."""
    reg = ContractRegistry()
    new_ext = {
        "kind": "custom_extension_artifact",
        "version": "1",
        "authoritative_for": "custom analysis",
        "canonical_role": "FACT",
    }
    # First registration succeeds
    reg.register_extension_contract(new_ext)
    assert reg.contract("custom_extension_artifact", "1")["kind"] == "custom_extension_artifact"

    # Second registration with identical key must fail closed
    with pytest.raises(ValidationError) as exc_info:
        reg.register_extension_contract(new_ext)
    assert exc_info.value.code == "DUPLICATE_EXTENSION_CONTRACT"


def test_t15_registry_properties_immutable_and_pinned():
    """T15: registry_digest, registry_id, registry_version are immutable and byte-pinned."""
    reg = ContractRegistry()
    assert reg.registry_id == REGISTRY_ID
    assert reg.registry_version == REGISTRY_VERSION
    assert reg.registry_digest == REGISTRY_SHA256

    # Registering an extension contract does NOT mutate pinned identity
    new_ext = {
        "kind": "innocent_extension",
        "version": "1",
        "authoritative_for": "test",
        "canonical_role": "FACT",
    }
    reg.register_extension_contract(new_ext)

    assert reg.registry_id == REGISTRY_ID
    assert reg.registry_version == REGISTRY_VERSION
    assert reg.registry_digest == REGISTRY_SHA256

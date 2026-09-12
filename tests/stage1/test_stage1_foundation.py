"""Comprehensive adversarial test suite for Etap 1: Canonical Authority Foundation.

Covers:
- D09: Layered validation & elimination of False Validation PASS (10 mandatory negative controls + parse/inbox)
- D12: Migration to canonical domain-separated ObjectDigest & mechanical inventory test
- D16: Pinned ContractRegistry immutability & runtime override defense
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
from bdb_audit.orchestration.e3_gate import E3StageCompletionCandidate
from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS
from bdb_audit.workflow.source_target import ResolvedSource
from bdb_audit.workflow.packaging import prepare_e1_batch
from bdb_audit.workflow.inbox import E1ResultInbox
from bdb_audit.history.store import TransactionalHistoryStore


# ============================================================================
# D09: 10 MANDATORY NEGATIVE CONTROLS (CTRL 01 - CTRL 10)
# ============================================================================

def _make_sample_campaign_genesis(cid: str = "CAMP-CORRECT-100") -> dict:
    """Helper creating a schema-valid campaign_genesis body dictionary."""
    return {
        "kind": "campaign_genesis",
        "version": "1",
        "campaign_id": cid,
        "input_history_cut": {"campaign_id": cid, "commit_seq": 0, "commit_hash": "0" * 64},
        "bootstrap_admission_decision_ref": {
            "kind": "bootstrap_admission_decision",
            "revision_digest": "0" * 64,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::bootstrap_admission_decision/1",
            "ref_class": "PRIOR_ACCEPTED_ONLY",
        },
        "source_generation_ref": {
            "kind": "source_generation",
            "revision_digest": "0" * 64,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_generation/1",
            "ref_class": "CONTENT_OR_PRIOR",
        },
        "application_generation_ref": {
            "kind": "external_profile_ref",
            "revision_digest": "0" * 64,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::external_profile_ref/1",
            "ref_class": "PINNED_PROFILE_REF",
        },
        "protocol_policy_bundle_ref": {
            "kind": "external_profile_ref",
            "revision_digest": "0" * 64,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::external_profile_ref/1",
            "ref_class": "PINNED_PROFILE_REF",
        },
        "schema_set_ref": {
            "kind": "external_profile_ref",
            "revision_digest": "0" * 64,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::external_profile_ref/1",
            "ref_class": "PINNED_PROFILE_REF",
        },
        "owner_operator_authority_ref": {
            "kind": "external_profile_ref",
            "revision_digest": "0" * 64,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::external_profile_ref/1",
            "ref_class": "PINNED_INSTALLATION_REF",
        },
        "trust_profile_ref": {
            "kind": "external_profile_ref",
            "revision_digest": "0" * 64,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::external_profile_ref/1",
            "ref_class": "PINNED_INSTALLATION_REF",
        },
        "legacy_origin_refs": [],
    }


def test_d09_ctrl01_schema_valid_without_context_admissible_false():
    """Ctrl 01: Schema-valid artifact without context yields admissible == False and missing L5."""
    api = AuditOperationApi()
    e1_spec = initial_stage_specs()[0]
    art = {"kind": "stage_spec", "version": "1", **e1_spec.body()}

    res = api.validate_artifact(art)
    assert res["structural_validation"] == "PASS"
    assert res["status"] == "PASS"
    assert res["admissible"] is False
    assert res["admission_status"] == "NOT_ADMITTED"
    assert "L5" in res["missing_validation_layers"]


def test_d09_ctrl02_wrong_campaign_in_context_rejected():
    """Ctrl 02: Wrong campaign in context raises CAMPAIGN_BINDING_MISMATCH."""
    api = AuditOperationApi()
    art = _make_sample_campaign_genesis("CAMP-ACTUAL-100")

    with pytest.raises(ValidationError) as exc_info:
        api.validate_artifact(art, context={"campaign_id": "CAMP-WRONG-999"})
    assert exc_info.value.code == "CAMPAIGN_BINDING_MISMATCH"


def test_d09_ctrl03_wrong_source_generation_ref_rejected():
    """Ctrl 03: Wrong source generation ref in context raises SOURCE_BINDING_MISMATCH."""
    api = AuditOperationApi()
    art = _make_sample_campaign_genesis("CAMP-ACTUAL-100")

    with pytest.raises(ValidationError) as exc_info:
        api.validate_artifact(
            art,
            context={
                "campaign_id": "CAMP-ACTUAL-100",
                "source_generation_ref": {"revision_digest": "1" * 64},
            },
        )
    assert exc_info.value.code == "SOURCE_BINDING_MISMATCH"


def test_d09_ctrl04_stale_wrong_history_cut_rejected():
    """Ctrl 04: Stale or mismatched history cut raises STALE_HISTORY_CUT."""
    api = AuditOperationApi()
    art = _make_sample_campaign_genesis("CAMP-ACTUAL-100")

    with pytest.raises(ValidationError) as exc_info:
        api.validate_artifact(
            art,
            context={
                "campaign_id": "CAMP-ACTUAL-100",
                "history_cut": {"commit_seq": 999},  # Artifact has commit_seq: 0
            },
        )
    assert exc_info.value.code == "STALE_HISTORY_CUT"


def test_d09_ctrl05_wrong_policy_binding_rejected():
    """Ctrl 05: Wrong policy binding in context raises POLICY_BINDING_MISMATCH."""
    api = AuditOperationApi()
    art = {
        "kind": "challenger_assignment",
        "version": "1",
        "challenge_assignment_id": "ca_pol_ctrl",
        "candidate_assurance_case_ref": {
            "kind": "candidate_assurance_case",
            "revision_digest": "0" * 64,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::candidate_assurance_case/1",
            "ref_class": "CONTENT_OR_PRIOR",
        },
        "challenger_type": "FALSE_POSITIVE_SKEPTIC",
        "challenge_scope": "ALL_CLAIMS",
        "challenge_policy_ref": {
            "kind": "policy_revision",
            "revision_digest": "0" * 64,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::policy_revision/1",
            "ref_class": "CONTENT_OR_PRIOR",
        },
        "executor_profile_ref": {
            "kind": "executor_spec",
            "revision_digest": "0" * 64,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_SCHEMA_REGISTRY::executor_spec/1",
            "ref_class": "CONTENT_OR_PRIOR",
        },
        "assignment_input_history_cut": {"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
    }

    with pytest.raises(ValidationError) as exc_info:
        api.validate_artifact(
            art,
            context={
                "campaign_id": "c",
                "governing_policy_ref": {"revision_digest": "f" * 64},
            },
        )
    assert exc_info.value.code == "POLICY_BINDING_MISMATCH"


def test_d09_ctrl06_unresolved_typed_reference_rejected():
    """Ctrl 06: Unresolved typed reference target kind raises UNRESOLVED_REFERENCE_TARGET."""
    validator = LayeredValidator()
    bad_target_ref = {
        "kind": "completely_unregistered_ghost_kind",
        "revision_digest": "0" * 64,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stage_spec/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    with pytest.raises(ValidationError) as exc_info:
        validator._typed_refs({"ref": bad_target_ref})
    assert exc_info.value.code == "UNRESOLVED_REFERENCE_TARGET"


def test_d09_ctrl07_invalid_schema_revision_ref_syntax_or_mismatch():
    """Ctrl 07: Invalid schema_revision_ref raises INVALID_SCHEMA_REFERENCE or TYPED_REF_TARGET_MISMATCH."""
    validator = LayeredValidator()

    bad_syntax_ref = {
        "kind": "stage_spec",
        "revision_digest": "0" * 64,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "   ",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    with pytest.raises(ValidationError) as exc_syntax:
        validator._typed_refs({"ref": bad_syntax_ref})
    assert exc_syntax.value.code == "INVALID_SCHEMA_REFERENCE"

    mismatch_ref = {
        "kind": "stage_spec",
        "revision_digest": "0" * 64,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::other_incompatible_spec/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    with pytest.raises(ValidationError) as exc_mismatch:
        validator._typed_refs({"ref": mismatch_ref})
    assert exc_mismatch.value.code == "TYPED_REF_TARGET_MISMATCH"


def test_d09_ctrl08_valid_digest_pointing_to_incompatible_target_kind():
    """Ctrl 08: Digest pointing to incompatible target kind raises TYPED_REF_TARGET_MISMATCH or OBJECT_DIGEST_MISMATCH."""
    validator = LayeredValidator()
    e1_spec = initial_stage_specs()[0]
    raw = canonical_bytes(e1_spec.body())

    with pytest.raises(ValidationError) as exc_schema:
        validator.validate("stage_spec", raw, expected_schema_ref="BDB_SCHEMA_REGISTRY::wrong_schema/1")
    assert exc_schema.value.code == "TYPED_REF_TARGET_MISMATCH"

    with pytest.raises(ValidationError) as exc_digest:
        validator.validate("stage_spec", raw, expected_digest="0" * 64)
    assert exc_digest.value.code == "OBJECT_DIGEST_MISMATCH"


def test_d09_ctrl09_missing_required_validation_layers():
    """Ctrl 09: Missing contract-required validation layer is reported in missing_validation_layers."""
    api = AuditOperationApi()
    e1_spec = initial_stage_specs()[0]
    art = {"kind": "stage_spec", "version": "1", **e1_spec.body()}

    res = api.validate_artifact(art)
    assert "L5" in res["required_validation_layers"]
    assert "L5" not in res["executed_validation_layers"]
    assert "L5" in res["missing_validation_layers"]
    assert res["admissible"] is False
    assert res["admission_status"] == "NOT_ADMITTED"


def test_d09_ctrl10_structural_validation_pass_but_admission_false():
    """Ctrl 10: Caller context/labels cannot self-certify L5 admission."""
    api = AuditOperationApi()
    e1_spec = initial_stage_specs()[0]
    art = {"kind": "stage_spec", "version": "1", **e1_spec.body()}

    for context in (
        None,
        {},
        {"stage_key": "E1"},
        {"stage_key": "E1", "qualified_layers": ["L5"]},
        {"qualified_layers": ["L5", "L6", "L7"]},
    ):
        res = api.validate_artifact(art, context=context)
        assert res["status"] == "PASS"
        assert res["structural_validation"] == "PASS"
        assert res["admissible"] is False
        assert res["admission_status"] == "NOT_ADMITTED"
        assert "L5" in res["missing_validation_layers"]
        assert "L5" not in res["executed_validation_layers"]
        assert "L6" not in res["executed_validation_layers"]
        assert "L7" not in res["executed_validation_layers"]


# ============================================================================
# D09: PARSE, INTEGRITY & INBOX CONTROLS
# ============================================================================

def test_t01_schema_violation_rejected_fail_closed(tmp_path: Path):
    api = AuditOperationApi()
    incomplete_art = {"kind": "stage_spec", "version": "1", "stage_key": "E1"}
    art_file = tmp_path / "incomplete.json"
    art_file.write_text(json.dumps(incomplete_art), encoding="utf-8")
    with pytest.raises(ValidationError) as exc_info:
        api.validate_artifact(art_file)
    assert exc_info.value.code == "SCHEMA_VALIDATION_FAILED"


def test_t02_duplicate_keys_rejected_before_schema(tmp_path: Path):
    api = AuditOperationApi()
    e1_spec = initial_stage_specs()[0]
    body = e1_spec.body()
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
    api = AuditOperationApi()
    art_file = tmp_path / "rogue.json"
    art_file.write_text(json.dumps({"kind": "rogue_unknown_kind", "version": "1", "some_data": 123}), encoding="utf-8")
    with pytest.raises(ValidationError) as exc_info:
        api.validate_artifact(art_file)
    assert exc_info.value.code == "UNREGISTERED_CONTRACT_KIND"


def test_t04_missing_kind_field_rejected(tmp_path: Path):
    api = AuditOperationApi()
    art_file = tmp_path / "no_kind.json"
    art_file.write_text(json.dumps({"version": "1", "data": "value"}), encoding="utf-8")
    with pytest.raises(ValidationError) as exc_info:
        api.validate_artifact(art_file)
    assert exc_info.value.code == "MISSING_ARTIFACT_KIND"


def test_t05_expected_kind_mismatch_rejected(tmp_path: Path):
    api = AuditOperationApi()
    e1_spec = initial_stage_specs()[0]
    art = {"kind": "stage_spec", "version": "1", **e1_spec.body()}
    art_file = tmp_path / "spec.json"
    art_file.write_text(json.dumps(art), encoding="utf-8")
    with pytest.raises(ValidationError) as exc_info:
        api.validate_artifact(art_file, expected_kind="lane_spec")
    assert exc_info.value.code == "ARTIFACT_KIND_MISMATCH"


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
    store, batch, inbox = _setup_inbox(tmp_path)
    zip_p = tmp_path / "dup_path.zip"
    with zipfile.ZipFile(zip_p, "w") as zf:
        zf.writestr("MANIFEST.json", json.dumps({"test": 1}))
        zf.writestr("MANIFEST.json", json.dumps({"test": 2}))
    lane, status, reason = inbox.ingest_zip(zip_p)
    assert status == "REJECTED"
    assert "ZIP_DUPLICATE_PATH" in str(reason)


def test_t09_inbox_path_traversal_zip_rejected(tmp_path: Path):
    store, batch, inbox = _setup_inbox(tmp_path)
    zip_p = tmp_path / "traversal.zip"
    with zipfile.ZipFile(zip_p, "w") as zf:
        zf.writestr("MANIFEST.json", json.dumps({"test": 1}))
        zf.writestr("../escaped_file.txt", "evil")
    lane, status, reason = inbox.ingest_zip(zip_p)
    assert status == "REJECTED"
    assert "ZIP_PATH_TRAVERSAL" in str(reason)


def test_t10_inbox_schema_invalid_manifest_rejected(tmp_path: Path):
    store, batch, inbox = _setup_inbox(tmp_path)
    job = batch.get_job("E1-A")
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
# D12: OBJECTDIGEST DOMAIN SEPARATION & PRODUCER MIGRATION
# ============================================================================

def test_d12_object_digest_domain_separation():
    e1_spec = initial_stage_specs()[0]
    body = e1_spec.body()
    raw_sha = hashlib.sha256(canonical_bytes(body)).hexdigest()
    domain_obj_digest = object_digest("stage_spec", "1", body, registry_kind="stage_spec").value
    assert len(domain_obj_digest) == 64
    assert domain_obj_digest == domain_obj_digest.lower()
    assert domain_obj_digest != raw_sha
    expected_preamble = b"BDB2/stage_spec/1\0"
    hasher = hashlib.sha256(expected_preamble)
    hasher.update(canonical_bytes(body))
    assert domain_obj_digest == hasher.hexdigest()


def test_d12_all_authority_bearing_producers_produce_canonical_object_digest():
    e1_spec = initial_stage_specs()[0]
    assert e1_spec.as_object().digest == object_digest("stage_spec", "1", e1_spec.body(), registry_kind="stage_spec").value

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

    chk = E3BlindCheckpoint(
        checkpoint_id="chk_t12",
        accepted_history_cut={"campaign_id": "c", "commit_seq": 1, "commit_hash": "0" * 64},
        blind_completion_digest="0" * 64,
        sealed_findings_count=3,
    )
    expected_chk_digest = CanonicalObject("checkpoint", chk.body()).digest
    assert chk.digest == expected_chk_digest
    assert chk.ref["revision_digest"] == expected_chk_digest

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

    e3_cand = E3StageCompletionCandidate(
        stage_key="E3",
        stage_spec_digest="0" * 64,
        e2_completion_digest="0" * 64,
        blind_checkpoint_digest=chk.digest,
        positive_projection_digest=proj.digest,
        blind_discoveries_count=3,
        gap_discoveries_count=1,
        fuzzing_executions_count=5,
        differential_executions_count=5,
        metamorphic_executions_count=5,
        adjudicated_decisions_count=4,
        open_obligations_count=0,
        unknown_scope_count=0,
        unsupported_scope_count=0,
        multi_stage_false_negatives_count=0,
        completion_digest="0" * 64,
        gate_verdict="PASS",
    )
    expected_e3_digest = CanonicalObject("stage_completion", e3_cand.body()).digest
    assert e3_cand.digest == expected_e3_digest
    assert e3_cand.ref["revision_digest"] == expected_e3_digest


def test_d12_mechanical_inventory_classes_and_contracts():
    reg = ContractRegistry()
    wire_contracts = reg._contracts
    for key, contract in wire_contracts.items():
        sem = contract.get("identity_semantics", "")
        assert "BDB-OBJECT-DIGEST-1" in sem or "ObjectDigest" in sem, (
            f"Contract {key} must declare ObjectDigest in identity_semantics"
        )
        assert "schema_ref" in contract, f"Contract {key} must declare schema_ref"

    sample_kinds = [
        "stage_spec", "candidate_assurance_case", "challenger_assignment",
        "challenger_result", "campaign_conclusion", "final_assurance_case",
        "release_qualification", "successor_campaign_genesis",
        "stage_completion", "checkpoint", "view_manifest",
    ]
    for kind in sample_kinds:
        dummy_body = {"sample_field": "sample_value", "kind_test": kind}
        c_obj = CanonicalObject(kind, dummy_body)
        obj_dig = c_obj.digest
        assert len(obj_dig) == 64
        assert obj_dig == obj_dig.lower()
        raw_sha = hashlib.sha256(canonical_bytes(dummy_body)).hexdigest()
        assert obj_dig != raw_sha, f"Kind {kind} digest must be domain separated, not raw sha256"
        expected_hasher = hashlib.sha256(f"BDB2/{kind}/1\0".encode("utf-8"))
        expected_hasher.update(canonical_bytes(dummy_body))
        assert obj_dig == expected_hasher.hexdigest()
        t_ref = c_obj.ref.as_dict()
        assert t_ref["kind"] == kind
        assert t_ref["revision_digest"] == obj_dig
        assert t_ref["digest_profile"] == "BDB-OBJECT-DIGEST-1"
        assert t_ref["schema_revision_ref"] == reg.contract(kind, "1")["schema_ref"]
        assert t_ref["ref_class"] in reg.document["reference_class_semantics"]


# ============================================================================
# D16: SECURED CONTRACT REGISTRY DEFENSE & IMMUTABILITY
# ============================================================================

def test_d16_canonical_contract_collision():
    reg = ContractRegistry()
    colliding_entry = {
        "kind": "stage_spec",
        "version": "1",
        "authoritative_for": "malicious override",
        "canonical_role": "FACT",
        "validation_profile": "STRUCTURAL",
    }
    with pytest.raises(ValidationError) as exc_info:
        reg.register_extension_contract(colliding_entry)
    assert exc_info.value.code == "CANONICAL_CONTRACT_COLLISION"


def test_d16_duplicate_extension_registration():
    reg = ContractRegistry()
    new_ext = {
        "kind": "custom_extension_artifact",
        "version": "1",
        "authoritative_for": "custom analysis",
        "canonical_role": "FACT",
        "validation_profile": "STRUCTURAL",
    }
    reg.register_extension_contract(new_ext)
    assert reg.contract("custom_extension_artifact", "1")["kind"] == "custom_extension_artifact"
    with pytest.raises(ValidationError) as exc_info:
        reg.register_extension_contract(new_ext)
    assert exc_info.value.code == "DUPLICATE_EXTENSION_CONTRACT"


def test_d16_canonical_schema_collision():
    reg = ContractRegistry()
    canonical_schema = reg.contract("stage_spec", "1")["schema_ref"]
    colliding_schema_ext = {
        "kind": "custom_extension_shadow",
        "version": "1",
        "authoritative_for": "shadowing test",
        "canonical_role": "FACT",
        "validation_profile": "STRUCTURAL",
        "schema_ref": canonical_schema,
    }
    with pytest.raises(ValidationError) as exc_info:
        reg.register_extension_contract(colliding_schema_ext)
    assert exc_info.value.code == "CANONICAL_SCHEMA_COLLISION"


def test_d16_invalid_validation_profile():
    reg = ContractRegistry()
    no_profile_ext = {"kind": "ext_no_profile", "version": "1", "authoritative_for": "test", "canonical_role": "FACT"}
    with pytest.raises(ValidationError) as exc_none:
        reg.register_extension_contract(no_profile_ext)
    assert exc_none.value.code == "INVALID_VALIDATION_PROFILE"

    empty_profile_ext = {"kind": "ext_empty_profile", "version": "1", "authoritative_for": "test", "canonical_role": "FACT", "validation_profile": "   "}
    with pytest.raises(ValidationError) as exc_empty:
        reg.register_extension_contract(empty_profile_ext)
    assert exc_empty.value.code == "INVALID_VALIDATION_PROFILE"

    bogus_profile_ext = {"kind": "ext_bogus_profile", "version": "1", "authoritative_for": "test", "canonical_role": "FACT", "validation_profile": "NON_EXISTENT_PROFILE_BOGUS"}
    with pytest.raises(ValidationError) as exc_bogus:
        reg.register_extension_contract(bogus_profile_ext)
    assert exc_bogus.value.code == "INVALID_VALIDATION_PROFILE"


def test_d16_unauthorized_extension_roles():
    reg = ContractRegistry()
    trust_root_ext = {"kind": "ext_trust_root", "version": "1", "authoritative_for": "test", "canonical_role": "TRUST_ROOT", "validation_profile": "STRUCTURAL"}
    with pytest.raises(ValidationError) as exc_trust:
        reg.register_extension_contract(trust_root_ext)
    assert exc_trust.value.code == "UNAUTHORIZED_EXTENSION_ROLE"

    foundation_ext = {"kind": "ext_foundation", "version": "1", "authoritative_for": "test", "canonical_role": "CANONICAL_FOUNDATION", "validation_profile": "STRUCTURAL"}
    with pytest.raises(ValidationError) as exc_foundation:
        reg.register_extension_contract(foundation_ext)
    assert exc_foundation.value.code == "UNAUTHORIZED_EXTENSION_ROLE"


def test_d16_extension_without_schema_binding_fails_closed():
    reg = ContractRegistry()
    unbound_ext = {
        "kind": "unbound_extension_artifact",
        "version": "1",
        "authoritative_for": "test unbound",
        "canonical_role": "FACT",
        "validation_profile": "STRUCTURAL",
        "schema_ref": "BDB_SCHEMA_REGISTRY::unbound_custom/1",
    }
    reg.register_extension_contract(unbound_ext)
    validator = LayeredValidator(registry=reg)
    with pytest.raises(ValidationError) as exc_val:
        validator.validate("unbound_extension_artifact", b'{"test": 123}')
    assert exc_val.value.code == "SCHEMA_BYTES_NOT_BOUND"
    api = AuditOperationApi(registry=reg)
    with pytest.raises(ValidationError) as exc_api:
        api.validate_artifact({"kind": "unbound_extension_artifact", "version": "1", "test": 123})
    assert exc_api.value.code == "SCHEMA_BYTES_NOT_BOUND"


def test_d16_registry_properties_immutable_and_pinned():
    reg = ContractRegistry()
    assert reg.registry_id == REGISTRY_ID
    assert reg.registry_version == REGISTRY_VERSION
    assert reg.registry_digest == REGISTRY_SHA256
    new_ext = {
        "kind": "innocent_extension",
        "version": "1",
        "authoritative_for": "test",
        "canonical_role": "FACT",
        "validation_profile": "STRUCTURAL",
    }
    reg.register_extension_contract(new_ext)
    assert reg.registry_id == REGISTRY_ID
    assert reg.registry_version == REGISTRY_VERSION
    assert reg.registry_digest == REGISTRY_SHA256

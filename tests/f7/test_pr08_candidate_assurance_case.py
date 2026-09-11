"""Targeted tests for Candidate Assurance Case (PR-E5-08 / M43)."""
import pytest
from jsonschema import Draft202012Validator

from bdb_audit.assurance.candidate_case import (
    CandidateAssuranceCase,
    CandidateAssuranceCaseBuilder,
)
from bdb_audit.core.errors import ValidationError
from bdb_audit.schemas.foundation import executable_schema


@pytest.fixture
def base_context():
    hcut = {
        "campaign_id": "CAMP-001",
        "commit_seq": 15,
        "commit_hash": "a" * 64,
    }
    camp_ref = {
        "kind": "campaign_genesis",
        "revision_digest": "cg" * 32,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::campaign_genesis/1",
        "ref_class": "PRIOR_ACCEPTED_ONLY",
    }
    src_ref = {
        "kind": "source_generation",
        "revision_digest": "sg" * 32,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_generation/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    scope_ref = {
        "kind": "inventory_revision",
        "revision_digest": "inv" * 21 + "0",
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::inventory_revision/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    claim_set_ref = {
        "kind": "claim_set",
        "revision_digest": "cs" * 32,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::claim_set/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    return {
        "hcut": hcut,
        "camp_ref": camp_ref,
        "src_ref": src_ref,
        "scope_ref": scope_ref,
        "claim_set_ref": claim_set_ref,
    }


def test_valid_candidate_assurance_case_creation_and_schema(base_context):
    builder = CandidateAssuranceCaseBuilder(
        case_id="cac_001",
        campaign_ref=base_context["camp_ref"],
        source_generation_ref=base_context["src_ref"],
        candidate_input_history_cut=base_context["hcut"],
        scope_inventory_ref=base_context["scope_ref"],
        assurance_claim_set_ref=base_context["claim_set_ref"],
    )

    ob_ref = {
        "kind": "coverage_obligation",
        "revision_digest": "ob_1" + "0" * 60,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::coverage_obligation/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    qual_ref = {
        "kind": "coverage_obligation_qualification",
        "revision_digest": "qual_1" + "0" * 58,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::coverage_obligation_qualification/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    builder.add_coverage_obligation(ob_ref, qual_ref)

    finding_claim = {
        "kind": "finding_claim_revision",
        "revision_digest": "fc_1" + "0" * 60,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::finding_claim_revision/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    adjudication = {
        "kind": "finding_adjudication_decision",
        "revision_digest": "adj_1" + "0" * 59,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::finding_adjudication_decision/1",
        "ref_class": "CONTENT_OR_PRIOR",
    }
    builder.add_finding(finding_claim, adjudication)

    cac = builder.build()
    assert cac.candidate_assurance_case_id == "cac_001"
    assert len(cac.coverage_obligation_refs) == 1
    assert len(cac.finding_claim_revision_refs) == 1
    assert len(cac.finding_adjudication_refs) == 1

    # Validate against executable JSON schema
    schema = executable_schema("candidate_assurance_case")
    validator = Draft202012Validator(schema)
    validator.validate(cac.body())


def test_rejection_of_future_artifacts_in_candidate(base_context):
    """CandidateAssuranceCase cannot reference future challenger or STOP artifacts."""
    future_challenger_ref = {
        "kind": "challenger_result",  # FUTURE!
        "revision_digest": "cr" * 32,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::challenger_result/1",
        "ref_class": "PRIOR_ACCEPTED_ONLY",
    }

    builder = CandidateAssuranceCaseBuilder(
        case_id="cac_bad",
        campaign_ref=base_context["camp_ref"],
        source_generation_ref=base_context["src_ref"],
        candidate_input_history_cut=base_context["hcut"],
        scope_inventory_ref=base_context["scope_ref"],
        assurance_claim_set_ref=base_context["claim_set_ref"],
    )
    builder.add_evidence_qualification(future_challenger_ref)

    with pytest.raises(ValidationError, match="PREMATURE_FUTURE_REF"):
        builder.build()


def test_strict_sorting_of_ref_sets(base_context):
    builder = CandidateAssuranceCaseBuilder(
        case_id="cac_sorted",
        campaign_ref=base_context["camp_ref"],
        source_generation_ref=base_context["src_ref"],
        candidate_input_history_cut=base_context["hcut"],
        scope_inventory_ref=base_context["scope_ref"],
        assurance_claim_set_ref=base_context["claim_set_ref"],
    )

    # Add out of order
    builder.add_contradiction({"kind": "contradiction_revision", "revision_digest": "zzz"})
    builder.add_contradiction({"kind": "contradiction_revision", "revision_digest": "aaa"})
    builder.add_contradiction({"kind": "contradiction_revision", "revision_digest": "mmm"})

    cac = builder.build()
    digests = [r["revision_digest"] for r in cac.contradiction_refs]
    assert digests == ["aaa", "mmm", "zzz"]

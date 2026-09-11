"""Targeted unit and negative tests for PR-024 / M20 evidence qualification minimum."""
import hashlib
import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.ids import new_id
from bdb_audit.evidence import (
    Observation, DependencyIndependenceAssessment,
    EvidenceApplicabilityAssessment, EvidenceQualificationAssessment,
    EvidenceInvalidation, check_independence_claim,
    propagate_invalidation_to_qualifications,
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


def test_observation_creation():
    obs = Observation(
        observation_id=new_id("observation"),
        execution_descriptor_ref=ref("execution_descriptor", "desc_1"),
        raw_observation_ref=ref("raw_artifact_ref", "raw_1"),
        observation_channel="http_response",
        observed_at="2026-09-11T00:00:00Z",
    )
    assert len(obs.digest) == 64
    assert obs.as_object().kind == "observation"


def test_shared_oracle_independence_rejection():
    cut = {"tag": "EMPTY_HISTORY"}
    claim_ref = ref("finding_claim_revision", "claim_1")
    graph_ref = ref("dependency_graph_ref", "graph_1")
    policy_ref = ref("policy_revision", "pol_1")

    oracle_dep = ref("external_profile_ref", "oracle_shared")
    independent_dep = ref("external_profile_ref", "oracle_different")

    # Happy path: genuinely independent dependencies
    check_independence_claim([oracle_dep], [independent_dep])
    assessment_ok = DependencyIndependenceAssessment(
        assessment_id=new_id("dependency_independence_assessment"),
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=cut,
        dependency_graph_ref=graph_ref,
        independence_policy_ref=policy_ref,
        result="INDEPENDENT",
        observer_path_refs=[ref("observer_path", "p1"), ref("observer_path", "p2")],
        shared_dependency_refs=[oracle_dep],
        independent_dependency_refs=[independent_dep],
    )
    assert assessment_ok.result == "INDEPENDENT"

    # Adversarial test: shared oracle claimed as independent must be rejected
    with pytest.raises(ValidationError, match="SHARED_ORACLE_INDEPENDENCE_REJECTED"):
        DependencyIndependenceAssessment(
            assessment_id=new_id("dependency_independence_assessment"),
            claim_revision_ref=claim_ref,
            assessment_input_history_cut=cut,
            dependency_graph_ref=graph_ref,
            independence_policy_ref=policy_ref,
            result="INDEPENDENT",
            observer_path_refs=[ref("observer_path", "p1"), ref("observer_path", "p2")],
            shared_dependency_refs=[oracle_dep],
            independent_dependency_refs=[oracle_dep],  # Same oracle!
        )


def test_evidence_qualification_and_applicability():
    cut = {"tag": "EMPTY_HISTORY"}
    claim_ref = ref("finding_claim_revision", "claim_1")

    app = EvidenceApplicabilityAssessment(
        assessment_id=new_id("evidence_applicability_assessment"),
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=cut,
        dependency_set_ref=ref("dependency_graph_ref", "dep_1"),
        environment_ref=ref("environment_record", "env_1"),
        execution_variant_ref=ref("external_profile_ref", "var_1"),
        harness_ref=ref("external_profile_ref", "harn_1"),
        subject_baseline_ref=ref("source_generation", "gen_1"),
        status="ACTIVE",
    )
    assert len(app.digest) == 64

    ind = DependencyIndependenceAssessment(
        assessment_id=new_id("dependency_independence_assessment"),
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=cut,
        dependency_graph_ref=ref("dependency_graph_ref", "graph_1"),
        independence_policy_ref=ref("policy_revision", "pol_1"),
        result="INDEPENDENT",
    )

    obs = Observation(
        observation_id=new_id("observation"),
        execution_descriptor_ref=ref("execution_descriptor", "desc_1"),
        raw_observation_ref=ref("raw_artifact_ref", "raw_1"),
        observation_channel="channel_1",
        observed_at="2026-09-11T00:00:00Z",
    )

    qual = EvidenceQualificationAssessment(
        assessment_id=new_id("evidence_qualification_assessment"),
        claim_revision_ref=claim_ref,
        assessment_input_history_cut=cut,
        dependency_graph_ref=ref("dependency_graph_ref", "graph_1"),
        independence_assessment_ref=ind.as_object().as_ref().as_dict(),
        applicability_assessment_ref=app.as_object().as_ref().as_dict(),
        observation_refs=[obs.as_object().as_ref().as_dict()],
        result="SUPPORTS",
    )
    assert len(qual.digest) == 64
    assert qual.result == "SUPPORTS"


def test_invalidation_propagation():
    cut = {"tag": "EMPTY_HISTORY"}
    ev_ref = ref("evidence_qualification_assessment", "qual_broken_1")

    inval = EvidenceInvalidation(
        invalidation_id=new_id("evidence_invalidation"),
        affected_evidence_or_qualification_refs=[ev_ref],
        dependency_ref=ref("dependency_graph_ref", "faulty_harness"),
        invalidation_input_history_cut=cut,
        propagation_policy_ref=ref("policy_revision", "pol_1"),
        reason_codes=["HARNESS_FLAKINESS_CONFIRMED"],
    )
    assert len(inval.digest) == 64

    # Qualifications that rely on the invalidated evidence must be degraded
    prior_qualifications = [
        {
            "qualification_id": "qual_cov_1",
            "qualification_status": "QUALIFIED",
            "satisfies_completion": True,
            "evidence_qualification_refs": [ev_ref],
        },
        {
            "qualification_id": "qual_cov_2",
            "qualification_status": "QUALIFIED",
            "satisfies_completion": True,
            "evidence_qualification_refs": [ref("evidence_qualification_assessment", "qual_unrelated")],
        },
    ]

    updated = propagate_invalidation_to_qualifications(inval, prior_qualifications)
    assert len(updated) == 2

    # Affected qualification is now STALE and does not satisfy completion
    assert updated[0]["qualification_status"] == "STALE"
    assert updated[0]["satisfies_completion"] is False
    assert updated[0]["degraded_by_invalidation"] is True

    # Unaffected qualification remains QUALIFIED
    assert updated[1]["qualification_status"] == "QUALIFIED"
    assert updated[1]["satisfies_completion"] is True


def test_m20_schemas_with_layered_validator():
    bindings = foundation_schema_bindings(kinds=F3_KINDS)
    validator = LayeredValidator(bindings=bindings)

    cut = {"tag": "EMPTY_HISTORY"}
    inval = EvidenceInvalidation(
        invalidation_id=new_id("evidence_invalidation"),
        affected_evidence_or_qualification_refs=[ref("evidence_qualification_assessment", "q1")],
        dependency_ref=ref("dependency_graph_ref", "d1"),
        invalidation_input_history_cut=cut,
        propagation_policy_ref=ref("policy_revision", "p1"),
    )
    val = validator.validate("evidence_invalidation", canonical_bytes(inval.body()))
    assert val.revision_digest == inval.digest

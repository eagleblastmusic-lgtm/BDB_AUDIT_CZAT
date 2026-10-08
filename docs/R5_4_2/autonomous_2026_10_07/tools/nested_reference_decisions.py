"""OD-018: exact fields found by independent actual-body reference traversal."""

from __future__ import annotations

from execution import OUT, read


SCOPE_KINDS = "surface_record surface_key invariant_revision finding_claim_revision coverage_obligation scope_state_record".split()
SUMMARY_KINDS = "coverage_obligation coverage_obligation_qualification scope_state_record evidence_qualification_assessment evidence_applicability_assessment isolation_qualification contamination_assessment contradiction_revision residual_risk stage_run lane_run attempt stage_completion lane_completion cleanup_result source_drift_impact_assessment discovery_confirmation_assessment model_fidelity_assessment".split()
INVALIDATED_KINDS = "evidence_invalidation evidence_applicability_assessment evidence_qualification_assessment invariant_revision sound_claim model_fidelity_assessment".split()


def additions(nodes):
    by_kind = {node["kind"]: key for key, node in nodes.items()}
    result = {}
    finite_profiles = sorted(read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json"))

    def add(owner, field, representation, *, kinds=(), profiles=(), cardinality="1", ref_class="PRIOR_ACCEPTED_ONLY"):
        full = owner + "." + field
        assert full not in result, full
        result[full] = {"representation": representation, "allowed_keys": sorted(by_kind[k] for k in kinds),
                        "profile_contracts": list(profiles), "cardinality": cardinality, "ref_class": ref_class,
                        "delegated_decision_id": "OD-018"}

    scope_fields = {
        "approval_decision/1": "scope[]", "challenger_assignment/1": "challenge_scope[]",
        "contamination_assessment/1": "scope[]", "contradiction_resolution_decision/1": "resolved_scope[]",
        "contradiction_revision/1": "scope[]", "evidence_applicability_assessment/1": "validity_scope[]",
        "evidence_invalidation/1": "scope[]", "evidence_qualification_assessment/1": "support_scope[]",
        "finding_adjudication_decision/1": "scope[]", "finding_axis_assessment/1": "scope[]",
        "isolation_qualification/1": "scope[]", "materiality_assessment/1": "scope[]",
        "model_fidelity_assessment/1": "scope[]", "negative_evidence_record/1": "claim_scope[]",
        "obligation_applicability_decision/1": "scope[]", "root_cause_revision/1": "scope[]", "sound_claim/1": "scope[]",
    }
    for owner, field in scope_fields.items():
        add(owner, field, "TypedRef", kinds=SCOPE_KINDS, cardinality="1..65536")
    add("root_cause_revision/1", "membership_edges[].scope[]", "TypedRef", kinds=SCOPE_KINDS, cardinality="1..65536 per membership edge")
    for owner, field in (
        ("contradiction_revision/1", "positions[].claim_revision_ref"),
        ("scope_state_record/1", "scope_key.subject_ref"),
    ):
        add(owner, field, "TypedRef", kinds=["finding_claim_revision"] if owner.startswith("contradiction") else SCOPE_KINDS,
            cardinality="1 per present tagged branch/position")
    for owner, field in (
        ("scope_state_record/1", "scope_key.source_member.source_manifest_ref"),
        ("surface_key/1", "normalized_anchor_descriptor.registration_origin.source_manifest_ref"),
        ("surface_record/1", "anchor_descriptor.registration_origin.source_manifest_ref"),
        ("tool_execution_record/2", "tool_run.resource_limit_events[].input_ref.source_manifest_ref"),
    ):
        add(owner, field, "TypedRef", kinds=["source_manifest"], cardinality="1 per present nonnull source-member branch")
    for owner, field in (
        ("experiment_spec/1", "positive_controls[]"), ("experiment_spec/1", "negative_controls[]"),
        ("negative_evidence_record/1", "negative_controls[]"),
    ):
        add(owner, field, "TypedRef", kinds=["experiment_spec"], cardinality="0..65536")
    for field, purpose in {
        "clock_profile": "CLOCK_PROFILE_V1", "filesystem_profile": "FILESYSTEM_BOUNDARY_V2",
        "network_profile": "NETWORK_BOUNDARY_V2", "sandbox_profile": "SANDBOX_PROFILE_V1",
    }.items():
        add("environment_record/1", field, "ExternalProfileRef", profiles=[purpose], ref_class="PINNED_PROFILE_REF")
    for owner, field, purpose in (
        ("experiment_spec/1", "cleanup_spec", "CLEANUP_ASSESSMENT_V2"),
        ("experiment_spec/1", "seed_profile", "SEED_PROFILE_V1"),
        ("experiment_spec/1", "observation_path_requirements[].capture_profile_ref", "OBSERVATION_CAPTURE_V2"),
        ("contradiction_revision/1", "required_falsifier", "METHOD_QUALIFICATION_V1"),
    ):
        add(owner, field, "ExternalProfileRef", profiles=[purpose], ref_class="PINNED_PROFILE_REF",
            cardinality="1 per present requirement" if "[]" in field else "1")
    for owner, field in (("final_technical_report/2", "report_binding.report_as_of_head"),
                         ("transition_authorization_proposal/1", "proposal_parent_head")):
        add(owner, field, "AcceptedHead", ref_class="HISTORY_INPUT")
    for field in ("independent_safe_expected_result.output_raw_ref", "legacy_observed_result.output_raw_ref", "v2_observed_result.output_raw_ref"):
        add("compatibility_fixture_assessment/1", field, "RawRef", profiles=["RETAINED_OPAQUE_BYTES_V1"],
            cardinality="0..1; mandatory if material output is present", ref_class="CONTENT_OBJECT")
    add("snapshot_export_record/1", "projection_code_revision", "RawRef", profiles=["RETAINED_PRODUCER_CODE_V1"], ref_class="CONTENT_OBJECT")
    for field in ("dependency_profile_change.old_profile_ref", "dependency_profile_change.new_profile_ref"):
        add("source_drift_record/1", field, "ExternalProfileRef", profiles=finite_profiles,
            cardinality="1 if dependency_profile_change present", ref_class="PINNED_PROFILE_REF")
    add("snapshot/1", "projection_payload.objects[].ref", "TypedRef",
        kinds=["campaign_genesis", "stage_run", "lane_run", "attempt", "executor_spec", "delivery_spec", "isolation_baseline_profile", "observation", "inventory_revision", "scope_state_record", "coverage_obligation", "coverage_obligation_qualification", "obligation_applicability_decision", "approval_decision", "evidence_qualification_assessment", "evidence_applicability_assessment", "evidence_invalidation", "contradiction_revision", "effort_results", "stage_completion", "candidate_assurance_case", "challenger_result", "residual_risk", "finding_claim_revision", "finding_adjudication_decision"],
        cardinality="0..65536; equals complete purpose closure")
    add("snapshot/1", "projection_payload.transition_event_refs[]", "AcceptedEventRef", cardinality="0..65536", ref_class="HISTORY_INPUT")
    for field, kind in {"applicability_decision_refs": "obligation_applicability_decision", "obligation_refs": "coverage_obligation",
                        "qualification_refs": "coverage_obligation_qualification", "waiver_decision_refs": "approval_decision"}.items():
        add("stage_completion/1", "mandatory_obligation_summary." + field + "[]", "TypedRef", kinds=[kind], cardinality="0..65536; exact independently derived denominator projection")
    for owner in ("stage_completion/1", "stop_input/1"):
        for field, kinds in {"unknown_refs": SUMMARY_KINDS, "blocked_refs": SUMMARY_KINDS,
                             "invalidated_refs": INVALIDATED_KINDS, "unresolved_contradiction_refs": ["contradiction_revision"]}.items():
            add(owner, "unknown_blocked_summary." + field + "[]", "TypedRef", kinds=kinds, cardinality="0..65536; exact complete applicable status set")
    add("stop_input/1", "evidence_invalidation_state[]", "TypedRef", kinds=["evidence_invalidation"], cardinality="0..65536; equality with evidence_invalidation_refs")
    add("standalone_payload_manifest/1", "embedded_components[].raw_ref", "RawRef",
        profiles=["RETAINED_PRODUCER_CODE_V1", "BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1", "RETAINED_OPAQUE_BYTES_V1", "FIXTURE_INPUT_V1"],
        cardinality="1 per required component; profile constrained by exact component_role", ref_class="CONTENT_OBJECT")
    build_kinds = "source_generation source_manifest artifact_contract_registry schema_registry spec_revision policy_revision trust_profile installation_bootstrap_profile stage_spec lane_spec executor_spec delivery_spec projection_policy".split()
    for prefix in ("ordered_input_refs[]", "embedded_resource_refs[]"):
        add("build_manifest/1", prefix + ".object_ref", "TypedRef", kinds=build_kinds,
            cardinality="1 per CANONICAL entry", ref_class="PINNED_INSTALLATION_REF")
        add("build_manifest/1", prefix + ".profile_ref", "ExternalProfileRef", profiles=finite_profiles,
            cardinality="1 per PROFILE entry", ref_class="PINNED_PROFILE_REF")
        add("build_manifest/1", prefix + ".raw_ref", "RawRef",
            profiles=["RETAINED_PRODUCER_CODE_V1", "BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1", "RETAINED_OPAQUE_BYTES_V1", "FIXTURE_INPUT_V1"],
            cardinality="1 per RAW entry", ref_class="CONTENT_OBJECT")
    assert len(result) == 65, len(result)
    return result

"""Exact raw payload material refs; raw assertions never establish acceptance."""

from __future__ import annotations

import json

from exhaustive_reference_audit import normalized, references
from execution import OUT, digest, preserve, read, write


def decisions(contracts, own):
    by_kind = {node["kind"]: node["key"] for node in own["nodes"]}
    nodes = {node["key"]: node for node in own["nodes"]}
    table = {}

    def add(owner, field, representation, targets, ref_class=None):
        key = owner, normalized(field)
        assert key not in table, key
        if ref_class is None:
            ref_class = "PRIOR_ACCEPTED_ONLY" if representation == "TypedRef" else "HISTORY_INPUT" if representation in ("AcceptedHead", "AcceptedEventRef") else "CONTENT_OBJECT" if representation == "RawRef" else "PINNED_PROFILE_REF"
        table[key] = {"field": field, "representation": representation, "targets": targets, "ref_class": ref_class,
                      "assertion_authority": "NONE; independently resolve and compare exact retained/prior context before semantic acceptance"}

    # Exact copied canonical subbodies must not get a second independently
    # invented reference contract merely because their transport is raw.
    for profile, node_key, prefix in (
        ("SURFACE_COLLECTOR_RECORD_JSON_V1", "surface_collector_record/2", "collection_run."),
        ("TOOL_EXECUTION_RECORD_JSON_V1", "tool_execution_record/2", "tool_run."),
        ("FAULT_RUN_RECORD_JSON_V1", "fault_run_record/2", "fault_run."),
    ):
        for material in nodes[node_key]["resolved_own_material_refs"]:
            if material["field"].startswith(prefix) and not material["field"].endswith(".artifact_contract_ref"):
                field = material["field"][len(prefix):]
                targets = material.get("allowed_keys") or material.get("profile_contracts") or []
                add(profile, field, material["representation"], targets, material["ref_class"])
    profile_fields = {
        "capture_profile_ref": "OBSERVATION_CAPTURE_V2", "environment_profile_ref": "ENVIRONMENT_PROFILE_V2",
        "dependency_set_ref": "EXECUTION_DEPENDENCY_PLAN_V1", "harness_ref": "EXECUTION_HARNESS_V2",
        "seed_ref": "SEED_PROFILE_V1", "generator_profile_ref": "EXECUTION_RUNNER_V2",
        "observer_requirements[].capture_profile_ref": "OBSERVATION_CAPTURE_V2", "cleanup_spec": "CLEANUP_ASSESSMENT_V2",
        "producer_ref": "PRINCIPAL_AUTHORIZATION_V1", "expected_detector_or_observer": "OBSERVATION_CAPTURE_V2",
        "clean_target_ref": "EXECUTION_VARIANT_V2", "known_defective_target_ref": "EXECUTION_VARIANT_V2",
        "strong_oracle_ref": "EXECUTION_HARNESS_V2", "weakened_oracle_ref": "EXECUTION_HARNESS_V2",
        "duration_workload_profile_ref": "ENDURANCE_WORKLOAD_V1", "monitoring_path_refs[]": "OBSERVATION_CAPTURE_V2",
    }
    raw_fields = {
        "expected_value.raw_ref": "RETAINED_OPAQUE_BYTES_V1", "executable_ref": "RETAINED_OPAQUE_BYTES_V1",
        "fixture_refs[]": "FIXTURE_INPUT_V1", "command_spec": "EXECUTION_COMMAND_JSON_V1",
        "expected_observable": "CLEANUP_EXPECTED_OBSERVABLE_V1", "activation_predicate": "CLEANUP_EXPECTED_OBSERVABLE_V1",
        "artifact_raw_refs[]": "RETAINED_OPAQUE_BYTES_V1", "final_output_raw_ref": "RETAINED_OPAQUE_BYTES_V1",
    }
    typed_fields = {
        "working_directory.source_manifest_ref": ["source_manifest"], "transitions[].source_anchors[].source_manifest_ref": ["source_manifest"],
        "source_generation_ref": ["source_generation"], "variable_mappings[].source_anchors[].source_manifest_ref": ["source_manifest"],
        "transition_mappings[].source_anchors[].source_manifest_ref": ["source_manifest"], "snapshot_ref": ["snapshot"],
        "binding.campaign_ref": ["campaign_genesis", "successor_campaign_genesis"], "binding.source_generation_ref": ["source_generation"],
        "binding.final_assurance_case_ref": ["final_assurance_case"], "binding.stop_evaluation_ref": ["stop_evaluation"],
        "binding.campaign_conclusion_ref": ["campaign_conclusion"], "binding.release_qualification_ref": ["release_qualification"],
        "campaign_ref": ["campaign_genesis", "successor_campaign_genesis"], "conclusion_ref": ["campaign_conclusion"],
        "stop_evaluation_ref": ["stop_evaluation"], "scope_inventory_ref": ["inventory_revision"],
        "residual_risks[].risk_ref": ["residual_risk"], "limited_basis_refs[]": ["stage_completion", "coverage_obligation", "coverage_obligation_qualification", "evidence_invalidation", "contradiction_revision", "residual_risk", "stop_evaluation", "approval_decision"],
        "finding_or_claim_revision_ref": ["finding_claim_revision", "finding_adjudication_decision"],
        "subject_baseline_ref": ["source_generation"], "expected_invariant_ref": ["invariant_revision"],
        "target_claim_or_invariant_ref": ["finding_claim_revision", "invariant_revision"],
        "target_location.source_manifest_ref": ["source_manifest"], "positive_control_ref": ["experiment_spec"], "negative_control_ref": ["experiment_spec"],
        "model_revision_ref": ["state_model"], "invariant_revision_ref": ["invariant_revision"],
        "implementation_scope_refs[]": ["surface_record", "surface_key", "invariant_revision", "finding_claim_revision", "coverage_obligation", "scope_state_record"],
        "observation_refs[]": ["observation"], "impact_ref": ["finding_axis_assessment"],
        "scope[]": ["surface_record", "surface_key", "invariant_revision", "finding_claim_revision", "coverage_obligation", "scope_state_record"],
        "evidence_qualification_refs[]": ["evidence_qualification_assessment"], "environment_ref": ["environment_record"],
        "build_input_manifest_ref": ["build_manifest"], "build_environment_ref": ["environment_record"],
        "verification_refs[]": ["validation_result", "compatibility_gate_result", "artifact_hash_manifest"],
    }
    for owner, c in contracts.items():
        if "payload_grammar" not in c:
            continue
        paths, _ = references(c["payload_grammar"])
        for field, representations in paths.items():
            if (owner, normalized(field)) in table:
                continue
            if field in profile_fields and representations == {"ExternalProfileRef"}:
                add(owner, field, "ExternalProfileRef", [profile_fields[field]])
            elif field in raw_fields and representations == {"RawRef"}:
                add(owner, field, "RawRef", [raw_fields[field]])
            elif field in typed_fields and representations == {"TypedRef"}:
                add(owner, field, "TypedRef", [by_kind[k] for k in typed_fields[field]])
            elif representations in ({"AcceptedHead"}, {"AcceptedEventRef"}):
                add(owner, field, next(iter(representations)), [])
            elif (owner, field) == ("FINAL_TECHNICAL_REPORT_JSON_V1", "machine_objects[].ref"):
                add(owner, field, "TypedRef", sorted(key for key in nodes if not key.startswith(("final_technical_report/", "report_export_receipt/"))))
            elif (owner, field) == ("SNAPSHOT_EXPORT_V2", "payload.objects[].ref"):
                source = next(item for item in nodes["snapshot/1"]["resolved_own_material_refs"] if item["field"] == "projection_payload.objects[].ref")
                add(owner, field, "TypedRef", source["allowed_keys"])
    # Build receipts precede campaign initialization. Only field-specific
    # independently verified installation/build context may resolve these refs.
    for field in ("build_input_manifest_ref", "build_environment_ref", "verification_refs[]"):
        item = table["BUILD_PROVENANCE_RECEIPT_V1", normalized(field)]
        item["ref_class"] = "PINNED_INSTALLATION_REF"
        item["delegated_decision_id"] = "OD-027"
        if field == "verification_refs[]":
            item["targets"] = [by_kind["validation_result"]]
    return table


def main():
    preserve()
    cs = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
    table = decisions(cs, read(OUT / "OWN_REFERENCE_RESOLUTIONS.json"))
    pending = []
    refs = []
    for owner, c in cs.items():
        if "payload_grammar" not in c:
            continue
        paths, _ = references(c["payload_grammar"])
        for field, representations in paths.items():
            item = table.get((owner, normalized(field)))
            if item is None:
                pending.append({"owner": owner, "field": field, "representations": sorted(representations), "status": "OPEN"})
            else:
                refs.append({"owner": owner, **item})
    write("design/PAYLOAD_REFERENCE_CONTRACTS.json", {"material_refs": refs, "pending": pending,
        "profile_catalog_raw_digest": digest(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json"),
        "fixed_point_reached": False, "producer_and_cross_object_validation": "PENDING_EXECUTABLE_PREDICATE_PARITY",
        "claim": "Explicit raw payload material refs are context assertions, never canonical authority by themselves"})
    print(json.dumps({"raw_payload_material_refs": len(refs), "pending_raw_payload_refs": len(pending), "fixed_point_reached": False}))
    for item in pending:
        print(item)


if __name__ == "__main__":
    main()

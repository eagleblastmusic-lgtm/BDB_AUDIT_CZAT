"""Explicit reference purposes inside installed profile and raw payload bodies."""

from __future__ import annotations

import json

from exhaustive_reference_audit import references
from execution import OUT, digest, preserve, read, write


def decisions(contracts):
    result = {}

    def add(owner, field, representation, targets, prior="PINNED_PROFILE_REF"):
        key = (owner, field)
        assert key not in result, key
        result[key] = {"field": field, "representation": representation, "targets": targets,
                       "ref_class": prior, "same_commit": False,
                       "rule": "Exact full pin/ref and context, independently retained readback; no latest, equivalent bytes or caller trust"}

    profile_fields = {
        "path_profile_ref": "SOURCE_PATH_PROFILE_V1", "manifest_entry_profile_ref": "SOURCE_MANIFEST_ENTRY_PROFILE_V1",
        "authority_parameters[].authority_ref": "SOURCE_AUTHORITY_V1",
        "parameters.authorized_principal_refs[]": "PRINCIPAL_AUTHORIZATION_V1",
        "parameters.required_cleanup_profile_ref": "CLEANUP_ASSESSMENT_V2",
        "parameters.permitted_risk_acceptance_authority_refs[]": "PRINCIPAL_AUTHORIZATION_V1",
        "source_identity_profile_ref": "SOURCE_IDENTITY_V2", "network_profile_ref": "NETWORK_BOUNDARY_V2",
        "witness_profile_ref": "OBSERVATION_CAPTURE_V2", "filesystem_boundary_ref": "FILESYSTEM_BOUNDARY_V2",
        "network_boundary_ref": "NETWORK_BOUNDARY_V2", "tool_boundary_ref": "TOOL_BOUNDARY_V2",
        "os_profile_ref": "OS_ENVIRONMENT_V2", "runtime_profile_ref": "RUNTIME_ENVIRONMENT_V2",
        "filesystem_profile_ref": "FILESYSTEM_BOUNDARY_V2", "clock_profile_ref": "CLOCK_PROFILE_V1",
        "sandbox_profile_ref": "SANDBOX_PROFILE_V1", "external_service_profile_refs[]": "EXTERNAL_SERVICE_V2",
        "namespace_profile_ref": "BOOTSTRAP_NAMESPACE_V2", "authorizing_principal_ref": "PRINCIPAL_AUTHORIZATION_V1",
        "authority_profile_refs[]": "SOURCE_AUTHORITY_V1", "historical_parser_profile_refs[]": "LEGACY_SCHEMA_PIN_V2",
        "surface_key_profile_refs[]": "SURFACE_KEY_PROFILE_V2",
        "predecessor_contract_profile_ref": "LEGACY_SCHEMA_PIN_V2", "authorization_ref": "PRINCIPAL_AUTHORIZATION_V1",
        "predecessor_pin_profile_ref": "TRUSTED_PREDECESSOR_PIN_V2", "result_slot_contract_refs[]": "NF02_EXTERNAL_LANE_SLOT_V2",
        "completion_contract_ref": "LANE_COMPLETION_V1", "acceptance_contract_ref": "OBLIGATION_ACCEPTANCE_V2",
        "applicability_contract_ref": "OBLIGATION_APPLICABILITY_V2", "method_contract_ref": "METHOD_QUALIFICATION_V1",
        "method_contract_refs[]": "METHOD_QUALIFICATION_V1", "identity_profile_ref": "SOURCE_IDENTITY_V2",
        "raw_identifier_profile_ref": "LEGACY_SCHEMA_PIN_V2", "normalizer_ref": "NF02_RESULT_NORMALIZER_V2",
        "transport_ref": "NF02_RESULT_TRANSPORT_V2", "input_transport_ref": "NF02_PACKAGE_TRANSPORT_V2",
        "result_transport_ref": "NF02_RESULT_TRANSPORT_V2", "result_slot_ref": "NF02_EXTERNAL_LANE_SLOT_V2",
        "package_semantic_profile_ref": "NF02_PACKAGE_SEMANTIC_PROFILE_V1", "independence_contract_ref": "ORACLE_INDEPENDENCE_V2",
        "ground_truth_profile_ref": "CALIBRATION_GROUND_TRUTH_PROFILE_V1", "legacy_contract_ref": "LEGACY_SCHEMA_PIN_V2",
        "current_contract_ref": "EXACT_COMPATIBILITY_V2", "required_fixture_contract_refs[]": "COMPATIBILITY_FIXTURE_V2",
        "legacy_schema_pin_ref": "LEGACY_SCHEMA_PIN_V2", "current_observation_contract_ref": "OBSERVATION_CAPTURE_V2",
        "legacy_mapping_profile_ref": "LEGACY_OBSERVATION_MAPPING_V2", "json_report_profile_ref": "FINAL_TECHNICAL_REPORT_JSON_V1",
        "text_report_profile_ref": "FINAL_TECHNICAL_REPORT_TEXT_V1", "membership_profile_ref": "BUNDLE_MEMBERSHIP_V2",
        "transport_profile_ref": "NF02_PACKAGE_TRANSPORT_V2", "witness_authority_ref": "PRINCIPAL_AUTHORIZATION_V1",
        "dependency_plan_ref": "EXECUTION_DEPENDENCY_PLAN_V1", "settings_ref": "DETERMINISTIC_BUILD_SETTINGS_V2",
        "protocol_profile_ref": "NF02_PROTOCOL_PROFILE_V2", "serialization_profile_ref": "BDB_CJSON_1",
        "canonical_profile_ref": "BDB_CJSON_1", "bundle_profile_ref": "QUALIFIED_PROTOCOL_POLICY_BUNDLE_V2",
        "context_parameters_ref": "FULL_PATH_CONTEXT_PARAMETERS_V1", "recovery_contract_ref": "EXACT_DURABLE_RECOVERY_V1",
        "required_capture_profile_refs[]": "OBSERVATION_CAPTURE_V2", "allowed_endpoint_refs[]": "EXTERNAL_SERVICE_V2",
        "allowed_tool_refs[]": "EXECUTOR_TOOL_V2",
    }
    raw_fields = {
        "parser_code_ref": "RETAINED_PRODUCER_CODE_V1", "parser_dependency_code_refs[]": "RETAINED_PRODUCER_CODE_V1",
        "source_manifest_schema_raw_ref": "BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1",
        "application_build_provenance_raw_ref": "BUILD_PROVENANCE_RECEIPT_V1",
        "parameters.activation_check_refs[]": "CLEANUP_EXPECTED_OBSERVABLE_V1", "collector_revision_ref": "RETAINED_PRODUCER_CODE_V1",
        "capture_code_ref": "RETAINED_PRODUCER_CODE_V1", "required_checks[].expected_observable": "CLEANUP_EXPECTED_OBSERVABLE_V1",
        "normalizer_code_ref": "RETAINED_PRODUCER_CODE_V1",
        "runtime_code_ref": "RETAINED_OPAQUE_BYTES_V1", "browser_code_ref": "RETAINED_OPAQUE_BYTES_V1",
        "dependencies[].raw_ref": "RETAINED_OPAQUE_BYTES_V1", "command_spec_refs[]": "EXECUTION_COMMAND_JSON_V1",
        "runner_code_ref": "RETAINED_PRODUCER_CODE_V1", "harness_code_ref": "RETAINED_PRODUCER_CODE_V1",
        "tool_code_ref": "RETAINED_PRODUCER_CODE_V1", "implementation_raw_ref": "RETAINED_OPAQUE_BYTES_V1",
        "predecessor_raw_ref": "RETAINED_OPAQUE_BYTES_V1", "ground_truth_raw_ref": "RETAINED_OPAQUE_BYTES_V1",
        "fixture_input_ref": "FIXTURE_INPUT_V1", "independent_expected_ref": "RETAINED_OPAQUE_BYTES_V1",
        "original_schema_raw_ref": "BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1", "original_parser_code_ref": "RETAINED_PRODUCER_CODE_V1",
        "projection_code_ref": "RETAINED_PRODUCER_CODE_V1", "builder_code_ref": "RETAINED_PRODUCER_CODE_V1",
        "command_spec_ref": "EXECUTION_COMMAND_JSON_V1", "qualification_manifest_raw_ref": "RETAINED_OPAQUE_BYTES_V1",
        "qualification_record_raw_ref": "RETAINED_OPAQUE_BYTES_V1",
    }
    typed_fields = {
        "application_build_manifest_ref": "build_manifest",
        "parameters.required_control_refs[]": "experiment_spec", "parameters.stage_requirements[].stage_spec_ref": "stage_spec",
        "stage_spec_refs[]": "stage_spec", "required_control_experiment_refs[]": "experiment_spec",
        "entries[].governing_spec_ref": "spec_revision", "artifact_contract_registry_ref": "artifact_contract_registry",
        "schema_registry_ref": "schema_registry", "governing_policy_ref": "policy_revision",
        "transition_spec_ref": "spec_revision", "trust_profile_ref": "trust_profile",
    }
    contextual_sets = {
        ("SOURCE_ARCHIVE_V2", "transport_profile_ref"): ["SOURCE_ZIP_TRANSPORT_V1"],
        ("TOOL_CAPTURE_V2", "output_contract_refs[]"): ["RETAINED_OPAQUE_BYTES_V1", "OBSERVATION_CAPTURE_V2", "FIXTURE_INPUT_V1"],
        ("EXECUTION_RUNNER_V2", "dependency_profile_refs[]"): ["ENVIRONMENT_PROFILE_V2", "EXECUTION_DEPENDENCY_PLAN_V1", "TOOL_CAPTURE_V2"],
        ("EXECUTION_HARNESS_V2", "dependency_profile_refs[]"): ["ENVIRONMENT_PROFILE_V2", "OBSERVATION_CAPTURE_V2"],
        ("EXECUTOR_TOOL_V2", "dependency_profile_refs[]"): ["TOOL_CAPTURE_V2", "EXECUTION_DEPENDENCY_PLAN_V1"],
        ("FULL_PATH_CONTEXT_PARAMETERS_V1", "entries[].predicate_contract_ref"): [name for name, c in contracts.items() if c.get("purpose")],
        ("BUNDLE_MEMBERSHIP_V2", "member_contract_refs[]"): ["FINAL_TECHNICAL_REPORT_JSON_V1", "EXACT_DURABLE_RECOVERY_V1", "BUILD_RECIPE_V2", "HASH_MANIFEST_V2", "RETAINED_OPAQUE_BYTES_V1"],
        ("HANDOFF_TRANSPORT_V2", "required_member_contract_refs[]"): ["RETAINED_OPAQUE_BYTES_V1", "FIXTURE_INPUT_V1"],
    }
    for name, c in contracts.items():
        paths, _ = references(c["grammar"])
        for path, representations in paths.items():
            if path == "parser_profile_ref":
                add(name, path, "ExternalProfileRef", ["STRICT_JSON_CAPTURE_V1"])
            elif path == "payload_schema_ref":
                add(name, path, "RawRef", ["BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1"], "CONTENT_OBJECT")
            elif (name, path) in contextual_sets:
                add(name, path, "ExternalProfileRef", contextual_sets[name, path])
            elif path in profile_fields and representations == {"ExternalProfileRef"}:
                add(name, path, "ExternalProfileRef", [profile_fields[path]])
            elif path in raw_fields and representations == {"RawRef"}:
                add(name, path, "RawRef", [raw_fields[path]], "CONTENT_OBJECT")
            elif path in typed_fields and representations == {"TypedRef"}:
                add(name, path, "TypedRef", [typed_fields[path]],
                    "PINNED_INSTALLATION_REF" if name == "QUALIFIED_PROTOCOL_POLICY_BUNDLE_V2" or
                    (name, path) in {("INSTALLATION_FULL_PATH_PROFILE_V1", "application_build_manifest_ref"),
                                     ("FULL_PATH_CONTEXT_PARAMETERS_V1", "entries[].governing_spec_ref")}
                    else "PRIOR_ACCEPTED_ONLY")
    return result


def main():
    preserve()
    contracts = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
    table = decisions(contracts)
    pending = []
    material = []
    for owner, c in contracts.items():
        paths, _ = references(c["grammar"])
        for field, representations in paths.items():
            rule = table.get((owner, field))
            if rule is None:
                pending.append({"owner": owner, "field": field, "representations": sorted(representations), "status": "OPEN"})
            else:
                if rule["representation"] in ("ExternalProfileRef", "RawRef"):
                    assert set(rule["targets"]) <= set(contracts), rule
                material.append({"owner": owner, **rule})
    write("design/PROFILE_REFERENCE_CONTRACTS.json", {"material_refs": material, "pending": pending,
        "catalog_raw_digest": digest(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json"),
        "raw_payload_reference_review": "PENDING", "fixed_point_reached": False,
        "claim": "Explicit installed profile field purposes; does not infer payload or authority completion"})
    print(json.dumps({"installed_profile_material_refs": len(material), "pending_installed_profile_refs": len(pending), "fixed_point_reached": False}))
    for item in pending:
        print(item)


if __name__ == "__main__":
    main()

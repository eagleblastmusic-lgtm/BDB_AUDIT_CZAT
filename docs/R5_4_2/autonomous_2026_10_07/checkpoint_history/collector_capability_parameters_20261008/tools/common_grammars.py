"""Closed reusable design grammars; no candidate or production writes."""

from __future__ import annotations

import copy

from jsonschema import Draft202012Validator

from execution import BASE, OUT, preserve, read, write
from purpose_contracts import array, const, definitions, enum, number, object_schema, ref, typed


SOURCE_PATH_SHAPE = {"type": "string", "minLength": 1, "maxLength": 512,
                     "pattern": r"^(?!.*(?:^|/)\.{1,2}(?:/|$))[^/\\\x00]+(?:/[^/\\\x00]+)*$"}


def tagged(tag, variants):
    return {"oneOf": [object_schema({tag: const(name), **fields}) for name, fields in variants.items()]}


def catalog(keys):
    defs = definitions(keys)
    inherited = read(BASE / "candidate/schemas/assignment_package_binding__1.schema.json")["$defs"]
    for name in ("accepted_head_ref", "accepted_history_cut", "empty_history_cut", "history_cut", "finding", "result_payload", "member_path"):
        defs[name] = copy.deepcopy(inherited[name])
    for name in ("accepted_history_cut", "empty_history_cut"):
        defs[name]["properties"]["governing_policy_ref"] = typed("policy_revision")
        defs[name]["properties"]["governing_spec_refs"] = array(typed("spec_revision"), 1)
    defs.update({
        "text": {"type": "string", "minLength": 1, "maxLength": 65536},
        "digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "uint": number(), "revision": number(1), "safe_integer": number(-9007199254740991),
        "int32": number(-2147483648, 2147483647),
        "path": {"type": "string", "minLength": 1, "maxLength": 512,
                 "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9._-]+)*$",
                 "not": {"pattern": "(?:^|/)\\.{1,2}(?:/|$)"}},
    })
    defs["source_path"] = copy.deepcopy(SOURCE_PATH_SHAPE)
    defs["source_anchor"] = object_schema({"source_manifest_ref": typed("source_manifest"), "member_path": ref("source_path"), "start_byte": ref("uint"), "end_byte": ref("uint")})
    defs["surface_anchor"] = tagged("anchor_kind", {
        "STATIC": {"member_path": ref("source_path"), "byte_offset": ref("uint"), "entry_kind": ref("code"), "discriminator": ref("text")},
        "RUNTIME": {"method": ref("code"), "route_pattern": ref("text"), "registration_origin": ref("source_anchor"), "namespace": ref("code")},
    })
    defs["source_member"] = object_schema({"source_manifest_ref": typed("source_manifest"), "member_path": ref("source_path")})
    scope_kinds = "surface_record surface_key invariant_revision finding_claim_revision coverage_obligation scope_state_record".split()
    defs["scope_ref"] = {"allOf": [ref("typed_ref"), {"properties": {"kind": enum(scope_kinds)}}]}
    defs["scope_set"] = array(ref("scope_ref"), 1)
    defs["scope_key"] = tagged("scope_kind", {
        "CANONICAL_SUBJECT": {"subject_ref": ref("scope_ref")},
        "SOURCE_MEMBER": {"source_member": ref("source_member")},
    })
    defs["accepted_event_ref"] = object_schema({"accepting_commit_hash": ref("digest"), "ordinal": ref("uint")})
    defs["contradiction_position"] = object_schema({"claim_revision_ref": typed("finding_claim_revision"), "statement": ref("text")})
    defs["root_cause_membership"] = object_schema({"finding_claim_revision_ref": typed("finding_claim_revision"), "scope": ref("scope_set"), "relation_role": enum("SUPPORTS_CAUSE CONTRIBUTES_TO_CAUSE UNRESOLVED")})
    defs["observation_path_requirement"] = object_schema({"observation_kind": enum("START FINISH MEASUREMENT ACTIVATION CLEANUP RESET CHANNEL_CAPTURE EXTERNAL_WITNESS"), "capture_profile_ref": ref("external_profile_ref"), "required": {"type": "boolean"}})
    defs["layer_result"] = object_schema({"layer": enum("L1 L2 L3 L4 L5 L6 L7"), "result": enum("PASS FAIL BLOCKED"), "reason_codes": array(ref("code"))})
    defs["model_value"] = {"oneOf": [{"type": "boolean"}, ref("safe_integer"), ref("code")]}
    defs["model_state"] = object_schema({"values": array(ref("model_value"), 1)})
    # State variable order is a sequence, not a set. Equal values are legal.
    defs["model_state"]["properties"]["values"].pop("uniqueItems")
    defs["model_bound"] = tagged("bound", {
        "STATES": {"limit": number(0, 65536)}, "TRANSITIONS": {"limit": number(0, 65536)},
        "PATH_STEPS": {"limit": number(1, 65536)},
    })
    defs["rational"] = object_schema({"numerator": ref("safe_integer"), "denominator": number(1)})
    defs["lane_slot_result"] = object_schema({"slot_contract_ref": ref("external_profile_ref"), "lane_completion_ref": typed("lane_completion")})
    defs["mandatory_obligation_summary"] = object_schema({
        "obligation_refs": array(typed("coverage_obligation")), "qualification_refs": array(typed("coverage_obligation_qualification")),
        "applicability_decision_refs": array(typed("obligation_applicability_decision")), "waiver_decision_refs": array(typed("approval_decision")),
    })
    defs["compatibility_observation"] = object_schema({"outcome": enum("ACCEPT REJECT BLOCKED"), "output_raw_ref": {"oneOf": [ref("raw_ref"), {"type": "null"}]}})
    defs["changed_manifest_member"] = object_schema({"member_path": ref("source_path"), "change": enum("ADDED REMOVED MODIFIED TYPE_CHANGED")})
    defs["dependency_profile_change"] = object_schema({"old_profile_ref": ref("external_profile_ref"), "new_profile_ref": ref("external_profile_ref")})
    defs["transition_proposal"] = object_schema({"aggregate_kind": enum("CAMPAIGN STAGE_RUN LANE_RUN ATTEMPT"), "from_state": ref("code"), "to_state": ref("code"), "event_type": ref("code")})
    defs["component_entry"] = object_schema({"member_path": ref("path"), "raw_ref": ref("raw_ref"), "component_role": enum("CODE SCHEMA SPEC PROMPT FIXTURE")})
    defs["bundle_member"] = object_schema({"member_path": ref("path"), "raw_ref": ref("raw_ref")})
    defs["assigned_input"] = tagged("input_kind", {
        "SOURCE_MEMBER": {"source_member": ref("source_member")},
        "CANONICAL_ARTIFACT": {"artifact_ref": {"allOf": [ref("typed_ref"), {"properties": {"kind": enum("source_manifest legacy_raw_ref surface_collector_record")}}]}},
    })
    defs["expected_value"] = tagged("value_kind", {
        "INTEGER": {"value": ref("safe_integer")}, "BOOLEAN": {"value": {"type": "boolean"}},
        "TEXT": {"value": ref("text")}, "NULL": {},
        "RATIONAL": {"numerator": ref("safe_integer"), "denominator": number(1)}, "RAW": {"raw_ref": ref("raw_ref")},
    })
    defs["observable_selector"] = tagged("selector_kind", {
        "JSON_POINTER": {"pointer": {"type": "string", "maxLength": 65536, "pattern": "^(?:/(?:[^~/]|~[01])*)*$"}},
        "WHOLE_BYTES": {},
    })
    defs["cleanup_expected_observable"] = object_schema({"capture_profile_ref": ref("external_profile_ref"), "selector": ref("observable_selector"), "expected_value": ref("expected_value")})
    defs["cleanup_check"] = object_schema({"check_id": ref("code"), "observation_kind": enum("START FINISH MEASUREMENT ACTIVATION CLEANUP RESET CHANNEL_CAPTURE EXTERNAL_WITNESS"), "expected_observable": ref("raw_ref")})
    defs["cleanup_profile"] = object_schema({"profile_id": const("CLEANUP_ASSESSMENT_V2"), "descriptor_selection": const("EXACT_CLEANUP_SUBJECT_DESCRIPTOR"), "required_checks": array(ref("cleanup_check"), 1)})
    defs["tool_capture_profile"] = object_schema({"profile_id": const("TOOL_CAPTURE_V3"), "capture_code_ref": ref("raw_ref"), "experiment_selection": const("EXACT_DESCRIPTOR_EXPERIMENT"), "environment_selection": const("EXACT_PRIOR_DESCRIPTOR_ENVIRONMENT"), "output_contract_refs": array(ref("external_profile_ref"))})
    defs["build_input_ref"] = tagged("input_kind", {
        "CANONICAL": {"object_ref": ref("typed_ref")}, "RAW": {"raw_ref": ref("raw_ref")},
        "PROFILE": {"profile_ref": ref("external_profile_ref")},
    })
    defs["collector_disposition"] = object_schema({"input_ref": ref("source_member"), "disposition": enum("COLLECTED UNSUPPORTED EXCLUDED COLLECTION_FAILED PARSING_FAILED"), "reason_codes": array(ref("code")), "exclusion_decision_ref": typed("approval_decision")})
    defs["collector_disposition"]["required"].remove("exclusion_decision_ref")
    defs["collector_disposition"]["allOf"] = [{"if": {"properties": {"disposition": const("EXCLUDED")}}, "then": {"required": ["exclusion_decision_ref"]}, "else": {"not": {"required": ["exclusion_decision_ref"]}}}]
    defs["manual_addition"] = object_schema({"surface_key_ref": typed("surface_key"), "observation_ref": typed("observation")})
    defs["parse_error"] = object_schema({"input_ref": ref("source_member"), "reason_codes": array(ref("code")), "detail": ref("text")})
    defs["unsupported_capability"] = object_schema({"input_ref": ref("source_member"), "capability_id": ref("code"), "reason_codes": array(ref("code"))})
    defs["resource_limit_event"] = object_schema({"input_ref": {"oneOf": [ref("source_member"), {"type": "null"}]}, "resource": enum("CPU_TIME_US WALL_TIME_US MEMORY_BYTES OUTPUT_BYTES FILE_COUNT"), "limit": ref("uint"), "observed": {"oneOf": [ref("uint"), {"type": "null"}]}, "reason_codes": array(ref("code"))})
    defs["collection_run"] = object_schema({
        "collection_run_id": {"type": "string", "pattern": "^surface_collector_record_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"},
        "collector_profile_ref": ref("external_profile_ref"), "assigned_input_manifest_ref": typed("source_manifest"),
        "assigned_inputs": array(ref("source_member"), 1), "terminal_input_dispositions": array(ref("collector_disposition"), 1),
        "emitted_surface_refs": array(typed("surface_key")), "runtime_manual_additions": array(ref("manual_addition")),
        "parse_errors": array(ref("parse_error")), "unsupported_capabilities": array(ref("unsupported_capability")),
        "resource_limit_events": array(ref("resource_limit_event")), "completion_status": const("ACCOUNTED"),
    })
    # Captured diagnostic sequences preserve repetitions and original order.
    for name in ("parse_errors", "unsupported_capabilities", "resource_limit_events"):
        defs["collection_run"]["properties"][name].pop("uniqueItems")
    defs["tool_run"] = object_schema({
        "tool_run_id": {"type": "string", "pattern": "^tool_execution_record_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"},
        "tool_profile_ref": ref("external_profile_ref"), "execution_descriptor_ref": typed("execution_descriptor"),
        "command_spec_ref": ref("raw_ref"), "actual_command_hash": ref("digest"),
        "real_exit_code": {"oneOf": [ref("int32"), {"type": "null"}]},
        "input_refs": array({"allOf": [ref("typed_ref"), {"properties": {"kind": enum("experiment_spec source_generation")}}]}),
        "output_raw_refs": array(ref("raw_ref")), "environment_ref": typed("environment_record"),
        "started_observation_time": {"oneOf": [ref("uint"), {"type": "null"}]},
        "finished_observation_time": {"oneOf": [ref("uint"), {"type": "null"}]},
        "status": enum("EXITED BLOCKED HARNESS_FAILURE"), "resource_limit_events": array(ref("resource_limit_event")),
    })
    defs["tool_run"]["properties"]["resource_limit_events"].pop("uniqueItems")
    defs["tool_run"]["allOf"] = [
        {"if": {"properties": {"status": const("EXITED")}}, "then": {"properties": {"real_exit_code": ref("int32"), "started_observation_time": ref("uint"), "finished_observation_time": ref("uint")}}},
        {"if": {"properties": {"status": const("BLOCKED")}}, "then": {"properties": {name: {"type": "null"} for name in ("real_exit_code", "started_observation_time", "finished_observation_time")}}},
        {"if": {"properties": {"status": const("HARNESS_FAILURE")}}, "then": {"properties": {"real_exit_code": {"type": "null"}}}},
    ]
    defs["fault_run"] = object_schema({"fault_revision_ref": typed("fault_spec"), "execution_descriptor_ref": typed("execution_descriptor"), "activation_status": enum("ACTIVATED NOT_ACTIVATED PARTIALLY_ACTIVATED BLOCKED HARNESS_FAILURE"), "activation_evidence_refs": array(typed("observation"), 1), "scope": ref("scope_set"), "cleanup_result_ref": typed("cleanup_result")})
    defs["report_binding"] = object_schema({"campaign_ref": typed("campaign_genesis"), "source_generation_ref": typed("source_generation"), "final_assurance_case_ref": typed("final_assurance_case"), "stop_evaluation_ref": typed("stop_evaluation"), "campaign_conclusion_ref": typed("campaign_conclusion"), "release_qualification_ref": typed("release_qualification"), "report_as_of_head": ref("accepted_head_ref")})
    defs["report_binding"]["required"].remove("release_qualification_ref")
    registry = read(BASE / "candidate/BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json")
    channels = registry["profiles"]["ISOLATION_BASELINE_PROFILE_V1"]["channels"]
    defs["channel_rule"] = {"enum": channels}
    blocker_kinds = "coverage_obligation coverage_obligation_qualification scope_state_record evidence_qualification_assessment evidence_applicability_assessment isolation_qualification contamination_assessment contradiction_revision residual_risk stage_run lane_run attempt stage_completion lane_completion cleanup_result source_drift_impact_assessment discovery_confirmation_assessment model_fidelity_assessment".split()
    blockers = {"allOf": [ref("typed_ref"), {"properties": {"kind": enum(blocker_kinds)}}]}
    defs["unknown_blocked_summary"] = object_schema({"unknown_refs": array(blockers), "blocked_refs": array(blockers), "invalidated_refs": array({"allOf": [ref("typed_ref"), {"properties": {"kind": enum("evidence_invalidation evidence_applicability_assessment evidence_qualification_assessment invariant_revision sound_claim model_fidelity_assessment")}}]}), "unresolved_contradiction_refs": array(typed("contradiction_revision"))})
    defs["legacy_observation_locator"] = tagged("locator_kind", {
        "RAW_ROOT": {"json_pointer": {"type": "string", "maxLength": 65536, "pattern": "^(?:/(?:[^~/]|~[01])*)*$"}},
        "ZIP_MEMBER": {"member_path": ref("path"), "json_pointer": {"type": "string", "maxLength": 65536, "pattern": "^(?:/(?:[^~/]|~[01])*)*$"}},
    })
    defs["report_object"] = {"oneOf": [object_schema({
        "ref": typed(key.split("::", 1)[1].split("/")[0]), "body": {"$ref": key},
    }) for key in sorted(keys)]}
    defs["closed_purpose_payload"] = object_schema({"purpose": enum("STOP_INPUT COVERAGE_SUMMARY CHANNEL_INVENTORY RUN_STATE"), "objects": array(ref("report_object")), "transition_event_refs": array(ref("accepted_event_ref"))})
    defs["legacy_variant_stage_facts"] = object_schema({"variant": {"type": ["string", "null"], "minLength": 1, "maxLength": 65536}, "stage": {"type": ["string", "null"], "minLength": 1, "maxLength": 65536}})
    defs["raw_identifier_entry"] = object_schema({"identifier_kind": enum("ARCHIVE_NAME DECLARED_GIT_COMMIT DECLARED_GIT_TREE DECLARED_SOURCE_ID DECLARED_MANIFEST_RAW_DIGEST"), "value": ref("text")})
    defs["raw_identifier_assertions"] = object_schema({"claims": array(ref("raw_identifier_entry"))})
    defs["view_metadata"] = object_schema({})
    defs["collector_capability"] = object_schema({"profile_id": const("COLLECTOR_CAPABILITY_V2"), "collector_revision_ref": ref("raw_ref"), "supported_input_classes": array(enum("REGULAR_FILE SYMLINK SUBMODULE OTHER_ALLOWED"), 1), "command_selection": const("EXACT_DESCRIPTOR_RUNNER_COMMAND"), "source_identity_profile_ref": ref("external_profile_ref")})
    from event_grammars import add_definitions
    add_definitions(defs, keys)
    return defs


def main():
    preserve()
    keys = ["BDB_SCHEMA_REGISTRY::" + key for key in read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"].values()]
    defs = catalog(keys)
    Draft202012Validator.check_schema({"$defs": defs})
    vectors = [
        ("path", "src/main.py", True), ("path", "../main.py", False), ("path", "src/../main.py", False),
        ("path", "src\\main.py", False), ("path", "/main.py", False), ("path", "src//main.py", False),
        ("source_path", ".gitignore", True), ("source_path", ".github/workflows/test.yml", True),
        ("source_path", "src/żółć.py", True), ("source_path", "../main.py", False),
        ("source_path", "src/./main.py", False), ("source_path", "src//main.py", False),
        ("source_path", "src\\main.py", False), ("source_path", "src/\0main.py", False),
        ("path", ".gitignore", False),
        ("safe_integer", True, False), ("safe_integer", 9007199254740992, False),
        ("safe_integer", -9007199254740991, True), ("int32", 2147483648, False),
        ("accepted_event_ref", {"accepting_commit_hash": "0" * 64, "ordinal": 0}, True),
        ("accepted_event_ref", {"accepting_commit_hash": "0" * 64, "ordinal": 0, "trusted": True}, False),
        ("scope_key", {"scope_kind": "PATH", "path": "src/main.py"}, False),
        ("model_state", {"values": [True, True]}, True),
        ("observable_selector", {"selector_kind": "JSON_POINTER", "pointer": "/~0/~1"}, True),
        ("observable_selector", {"selector_kind": "JSON_POINTER", "pointer": "/~2"}, False),
        ("observable_selector", {"selector_kind": "EVAL", "expression": "True"}, False),
        ("expected_value", {"value_kind": "BOOLEAN", "value": 1}, False),
        ("expected_value", {"value_kind": "INTEGER", "value": True}, False),
    ]
    manifest_ref = {"kind": "source_manifest", "revision_digest": "a" * 64,
                    "digest_profile": "BDB-OBJECT-DIGEST-1",
                    "schema_revision_ref": {"kind": "schema", "revision_digest": "b" * 64}}
    for path, valid in ((".gitignore", True), (".github/workflows/test.yml", True),
                        ("src/żółć.py", True), ("../main.py", False),
                        ("src/./main.py", False), ("src//main.py", False),
                        ("src\\main.py", False), ("src/\0main.py", False)):
        member = {"source_manifest_ref": manifest_ref, "member_path": path}
        anchor = {**member, "start_byte": 0, "end_byte": 1}
        vectors.extend([
            ("changed_manifest_member", {"member_path": path, "change": "MODIFIED"}, valid),
            ("source_member", member, valid),
            ("source_anchor", anchor, valid),
            ("surface_anchor", {"anchor_kind": "STATIC", "member_path": path,
                                "byte_offset": 0, "entry_kind": "FUNCTION", "discriminator": "exact"}, valid),
            ("surface_anchor", {"anchor_kind": "RUNTIME", "method": "GET", "route_pattern": "/route",
                                "registration_origin": anchor, "namespace": "APP"}, valid),
        ])
    results = []
    for name, value, expected in vectors:
        schema = {"$defs": defs, "$ref": "#/$defs/" + name}
        actual = Draft202012Validator(schema).is_valid(value)
        assert actual == expected, (name, value, actual)
        results.append({"grammar": name, "input": value, "expected": "ACCEPT" if expected else "REJECT", "schema_result": "PASS", "canonical_runtime": "NOT_RUN"})
    write("design/COMMON_GRAMMARS.json", {"$schema": "https://json-schema.org/draft/2020-12/schema", "$defs": copy.deepcopy(defs), "authority": "DESIGN_ONLY_NOT_CANDIDATE"})
    write("design/COMMON_GRAMMAR_KNOWN_ANSWERS.json", {"vectors": results, "status": "PASS", "claim": "Draft syntax only; cross-object predicates and canonical mutation checks NOT_RUN"})
    print({"draft_grammars": len(defs), "known_answers": len(results), "status": "PASS"})


if __name__ == "__main__":
    main()

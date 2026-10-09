"""Explicit own-field reference decisions. Design output is not runtime authority.

There is no field-name-to-kind fallback. Every unresolved frontier entry must be
covered by a listed decision or an inherited executable declaration.
"""

from __future__ import annotations

import copy
import re
from collections import defaultdict

from execution import BASE, OUT, digest, preserve, read, write


def add_group(table, names, representation, *, profiles=(), targets=(), ref_class=None):
    for name in names.split():
        assert name not in table, name
        table[name] = {"representation": representation, "profile_contracts": list(profiles),
                       "allowed_keys": list(targets), "ref_class": ref_class}


def decisions():
    table = {}
    add_group(table, "full_path_context_parameters_ref", "ExternalProfileRef", profiles=("FULL_PATH_CONTEXT_PARAMETERS_V1",), ref_class="PINNED_INSTALLATION_REF")
    add_group(table, "transition_contract_ref", "ExternalProfileRef", profiles=("FULL_PATH_TRANSITION_TABLE_V2",), ref_class="PINNED_INSTALLATION_REF")
    add_group(table, "actor_ref actor_authority_ref owner_operator_authority_ref coordinator_authority_ref producer_ref adjudicator_ref issuer_or_channel_ref external_storage_or_witness_ref authorized_actor_or_capability_profile_ref",
              "AuthorityRef", profiles=("PRINCIPAL_AUTHORIZATION_V1",), ref_class="AUTHORIZED_ACTOR_REF")
    add_group(table, "repository_authority_ref snapshot_authority_ref authorized_repository_or_snapshot_ref",
              "SourceAuthorityRef", profiles=("SOURCE_AUTHORITY_V1",), ref_class="SOURCE_AUTHORITY_REF")
    add_group(table, "expected_parent_head prev_history_ref", "ParentHead", ref_class="HISTORY_INPUT")
    add_group(table, "accepted_head as_of_head export_as_of_head report_as_of_head", "AcceptedHead", ref_class="HISTORY_INPUT")
    add_group(table, "discovery_event_ref first_relevant_reveal_event_ref", "AcceptedEventRef", ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "admission_input_history_cut input_history_cut assigned_history_cut preregistration_input_history_cut assessment_input_history_cut detection_input_history_cut selection_input_history_cut applicability_cut",
              "HistoryCut", ref_class="HISTORY_INPUT")
    add_group(table, "history_namespace_ref allowed_history_namespace_ref", "ExternalProfileRef", profiles=("BOOTSTRAP_NAMESPACE_V2",), ref_class="PINNED_INSTALLATION_REF")
    add_group(table, "initial_serialization_profile_ref serialization_profile_ref", "ExternalProfileRef", profiles=("BDB_CJSON_1",), ref_class="PINNED_PROFILE_REF")
    add_group(table, "initial_source_identity_profile_ref source_identity_profile_ref identity_profile_ref", "ExternalProfileRef", profiles=("SOURCE_IDENTITY_V2",), ref_class="PINNED_PROFILE_REF")
    add_group(table, "predecessor_pin_ref", "ExternalProfileRef", profiles=("TRUSTED_PREDECESSOR_PIN_V2",), ref_class="PINNED_INSTALLATION_REF")
    add_group(table, "result_slot_contract_refs result_slot_contracts result_slot_contract_ref required_result_slots",
              "ExternalProfileRef", profiles=("NF02_EXTERNAL_LANE_SLOT_V2",), ref_class="HISTORY_CONTEXT_BINDING")
    add_group(table, "required_lane_slot_contract_refs", "ExternalProfileRef", profiles=("MANDATORY_LANE_SLOT_V1",), ref_class="HISTORY_CONTEXT_BINDING")
    add_group(table, "package_raw_ref", "RawRef", profiles=("NF02_PACKAGE_TRANSPORT_V2",), ref_class="CONTENT_OBJECT")
    add_group(table, "result_raw_ref", "RawRef", profiles=("NF02_RESULT_TRANSPORT_V2",), ref_class="CONTENT_OBJECT")
    add_group(table, "collector_raw_ref", "RawRef", profiles=("SURFACE_COLLECTOR_RECORD_JSON_V1",), ref_class="CONTENT_OBJECT")
    add_group(table, "tool_run_raw_ref", "RawRef", profiles=("TOOL_EXECUTION_RECORD_JSON_V1",), ref_class="CONTENT_OBJECT")
    add_group(table, "fault_run_raw_ref", "RawRef", profiles=("FAULT_RUN_RECORD_JSON_V1",), ref_class="CONTENT_OBJECT")
    add_group(table, "report_raw_ref report_artifact_ref", "RawRef", profiles=("FINAL_TECHNICAL_REPORT_JSON_V1", "FINAL_TECHNICAL_REPORT_TEXT_V1"), ref_class="CONTENT_OBJECT")
    add_group(table, "statement_raw_ref", "RawRef", profiles=("PUBLIC_CONCLUSION_RENDER_V1",), ref_class="CONTENT_OBJECT")
    add_group(table, "hash_manifest_artifact_ref", "RawRef", profiles=("HASH_MANIFEST_V2",), ref_class="CONTENT_OBJECT")
    add_group(table, "command_spec_ref", "RawRef", profiles=("EXECUTION_COMMAND_JSON_V1",), ref_class="CONTENT_OBJECT")
    add_group(table, "observation_raw_ref", "RawRef", profiles=("OBSERVATION_CAPTURE_V2",), ref_class="CONTENT_OBJECT")
    add_group(table, "fixture_raw_ref fixture_refs", "RawRef", profiles=("FIXTURE_INPUT_V1",), ref_class="CONTENT_OBJECT")
    add_group(table, "ground_truth_provenance_ref", "RawRef", profiles=("CALIBRATION_GROUND_TRUTH_PROFILE_V1",), ref_class="CONTENT_OBJECT")
    add_group(table, "model_artifact_ref", "RawRef", profiles=("MODEL_ARTIFACT_V1",), ref_class="CONTENT_OBJECT")
    add_group(table, "implementation_mapping_ref abstraction_mapping_refs", "RawRef", profiles=("IMPLEMENTATION_MAPPING_V1",), ref_class="CONTENT_OBJECT")
    add_group(table, "handoff_ref", "RawRef", profiles=("HANDOFF_TRANSPORT_V2",), ref_class="CONTENT_OBJECT")
    add_group(table, "legacy_observation_raw_ref", "RawRef", profiles=("LEGACY_OBSERVATION_RAW_V1",), ref_class="CONTENT_OBJECT")
    add_group(table, "projection_code_ref producer_revision_ref", "RawRef", profiles=("RETAINED_PRODUCER_CODE_V1",), ref_class="CONTENT_OBJECT")
    add_group(table, "representation_refs", "RawRef", profiles=("SOURCE_ARCHIVE_V2",), ref_class="CONTENT_OBJECT")
    add_group(table, "members[].raw_ref output_raw_refs", "RawRef", profiles=("RETAINED_OPAQUE_BYTES_V1",), ref_class="CONTENT_OBJECT")
    add_group(table, "bindings[].schema_raw_ref", "RawRef", profiles=("BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1",), ref_class="CONTENT_OBJECT")
    add_group(table, "assigned_input_ref assigned_input_refs", "AssignedInputV2", ref_class="CONTENT_OR_PRIOR")
    add_group(table, "protocol_policy_bundle_ref", "ExternalProfileRef", profiles=("QUALIFIED_PROTOCOL_POLICY_BUNDLE_V2",), ref_class="PINNED_INSTALLATION_REF")
    add_group(table, "capture_profile_ref", "ExternalProfileRef", profiles=("OBSERVATION_CAPTURE_V2",), ref_class="PINNED_PROFILE_REF")
    add_group(table, "projection_input_refs", "TypedRef", targets=("campaign_genesis/1", "stage_run/1", "lane_run/1", "attempt/1", "executor_spec/1", "delivery_spec/1", "isolation_baseline_profile/1", "observation/1", "inventory_revision/2", "scope_state_record/1", "coverage_obligation/1", "coverage_obligation_qualification/1", "obligation_applicability_decision/1", "approval_decision/1", "evidence_qualification_assessment/1", "evidence_applicability_assessment/1", "evidence_invalidation/1", "contradiction_revision/1", "effort_results/1", "stage_completion/1", "candidate_assurance_case/1", "challenger_result/1", "residual_risk/1", "finding_claim_revision/1", "finding_adjudication_decision/1"), ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "ordered_input_refs embedded_resource_refs", "BuildInputRef", ref_class="CONTENT_OBJECT")
    add_group(table, "allowed_member_refs", "MemberRef", ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "unresolved_scope_refs", "ScopeSet", targets=("scope_state_record/1", "surface_key/1", "surface_record/1", "coverage_obligation/1", "invariant_revision/1"), ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "mutation_oracle_challenge_refs", "TypedRef", targets=("experiment_spec/1", "execution_result/1"), ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "bundle_manifest_ref", "TypedRef", targets=("bundle_manifest/2",), ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "stage_run_ref", "TypedRef", targets=("stage_run/1",), ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "lane_run_ref", "TypedRef", targets=("lane_run/1",), ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "attempt_ref", "TypedRef", targets=("attempt/1",), ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "source_generation_ref", "TypedRef", targets=("source_generation/1",), ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "stage_spec_ref", "TypedRef", targets=("stage_spec/1",), ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "lane_spec_ref", "TypedRef", targets=("lane_spec/1",), ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "executor_profile_ref", "TypedRef", targets=("executor_spec/1",), ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "delivery_profile_ref", "TypedRef", targets=("delivery_spec/1",), ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "knowledge_state_ref", "TypedRef", targets=("knowledge_state/1",), ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "protocol_policy_ref governing_policy_ref", "TypedRef", targets=("policy_revision/1",), ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "schema_set_ref", "TypedRef", targets=("schema_registry/2",), ref_class="PINNED_INSTALLATION_REF")
    add_group(table, "source_identity_ref", "TypedRef", targets=("source_identity/1",), ref_class="PRIOR_ACCEPTED_ONLY")
    add_group(table, "snapshot_artifact_ref", "RawRef", profiles=("SNAPSHOT_EXPORT_V2",), ref_class="CONTENT_OBJECT")
    # Exact profile purposes. Similar names never authorize substituting one for another.
    profile_groups = {
        "KNOWLEDGE_POLICY_V2": "forbidden_knowledge_policy_ref consumer_knowledge_policy_ref",
        "BOOTSTRAP_ADMISSION_V2": "admission_policy_ref",
        "BUILD_RECIPE_V2": "builder_recipe_ref",
        "DETERMINISTIC_BUILD_SETTINGS_V2": "deterministic_settings_ref",
        "RUNTIME_ENVIRONMENT_V2": "toolchain_runtime_profile_ref runtime_profile_ref",
        "CLAIM_RELATIVE_ASSESSMENT_V1": "assessor_profile_ref assessment_policy_ref",
        "CLEANUP_ASSESSMENT_V2": "cleanup_spec_ref",
        "COMPATIBILITY_FIXTURE_V2": "fixture_contract_ref",
        "ORACLE_INDEPENDENCE_V2": "independence_policy_ref required_oracle_independence_predicate_ref",
        "ENVIRONMENT_PROFILE_V2": "environment_profile_ref",
        "QUALIFIED_TECHNIQUE_V2": "required_technique_or_capability_refs",
        "OBLIGATION_ACCEPTANCE_V2": "acceptance_predicate_ref",
        "OBLIGATION_APPLICABILITY_V2": "applicability_predicate_ref applicability_policy_ref",
        "DELIVERY_IDEMPOTENCY_V2": "idempotency_policy_ref",
        "PUBLIC_REDACTION_V2": "redaction_profile_ref",
        "DELIVERY_RETRY_V2": "retry_policy_ref",
        "DISCOVERY_CONFIRMATION_V1": "confirmation_policy_ref",
        "EXACT_SCOPED_MATCH_V1": "match_policy_ref",
        "CORPUS_RELATIVE_NOVELTY_V1": "novelty_policy_ref",
        "METHOD_QUALIFICATION_V1": "method_ref",
        "TOOL_CAPTURE_V2": "tool_profile_ref",
        "OBSERVED_EFFORT_V1": "effort_profile_ref budget_effort_profile_ref",
        "OS_ENVIRONMENT_V2": "os_profile_ref",
        "BROWSER_ENVIRONMENT_V2": "browser_profile_ref",
        "EXTERNAL_SERVICE_V2": "external_service_profile_refs",
        "EXECUTION_DEPENDENCY_PLAN_V1": "dependency_set_ref",
        "EXECUTION_VARIANT_V2": "execution_variant_ref target_variant_ref target_execution_variant_ref",
        "EXECUTION_HARNESS_V2": "harness_ref",
        "EXECUTION_RUNNER_V2": "runner_profile_ref",
        "EXECUTOR_TOOL_V2": "executor_tool_ref",
        "FILESYSTEM_BOUNDARY_V2": "filesystem_boundary_ref",
        "MODEL_AGENT_BOUNDARY_V2": "model_profile_ref",
        "NETWORK_BOUNDARY_V2": "network_boundary_ref",
        "TOOL_BOUNDARY_V2": "tool_boundary_ref",
        "PRIOR_FALSE_NEGATIVE_V1": "relationship_policy_ref",
        "FAULT_RUN_RECORD_JSON_V1": "fault_run_profile_ref",
        "QUALIFIED_ACTIVATION_V1": "activation_predicate_ref",
        "FINAL_TECHNICAL_REPORT_JSON_V1": "report_profile_ref report_contract_ref",
        "GATE_ELIGIBILITY_PROFILE_V1": "gate_policy_ref",
        "CAPABILITY_BOUNDARY_V2": "capability_profile_ref resolver_capability_profile_ref",
        "HANDOFF_TRANSPORT_V2": "contract_ref",
        "HISTORY_ANCHOR_V2": "anchor_profile_ref external_anchor_profile_ref",
        "RECOVERY_REFERENCE_PROFILE_V1": "recovery_pin_policy_ref",
        "LEGACY_EXPOSURE_RECONSTRUCTION_V2": "reconstruction_policy_ref",
        "LEGACY_SCHEMA_PIN_V2": "legacy_schema_ref legacy_profile_ref",
        "LEGACY_MECHANICAL_VALIDATION_V2": "mechanical_validation_policy_ref",
        "LEGACY_OBSERVATION_MAPPING_V2": "mapping_policy_ref",
        "LINEAGE_ADMISSION_V2": "selection_policy_ref",
        "PUBLIC_CONCLUSION_RENDER_V1": "render_profile_ref",
        "SNAPSHOT_PROJECTION_V2": "projection_profile_ref",
        "SOURCE_DRIFT_POLICY_V2": "drift_policy_ref",
        "SOURCE_RECONCILIATION_V2": "reconciliation_policy_ref",
        "NF02_PROTOCOL_PROFILE_V2": "protocol_profile_ref",
        "COVERAGE_OBLIGATION_POLICY_V2": "coverage_obligation_policy_ref",
        "TRANSITION_POLICY_V2": "transition_policy_ref",
        "FINITE_MODEL_FIDELITY_V1": "model_profile_ref",
        "CHALLENGER_FRESHNESS_V2": "challenger_freshness_profile_ref",
        "MANDATORY_STAGE_SET_V2": "required_stage_set_ref",
        "SURFACE_COLLECTOR_RECORD_JSON_V1": "collector_record_profile_ref",
        "COLLECTOR_ACCOUNTING_V1": "collector_profile_ref collector_profile_refs",
        "TOOL_EXECUTION_RECORD_JSON_V1": "tool_run_profile_ref",
        "QUALIFIED_VALIDATOR_V2": "validator_profile_ref",
        "EXACT_COMPATIBILITY_V2": "compatibility_rules_ref",
        "HASH_MANIFEST_V2": "hash_manifest_profile_ref",
        "BUNDLE_MEMBERSHIP_V2": "bundle_contract_ref",
        "EXPLORATION_POLICY_V2": "exploration_policy_ref",
        "LANE_COMPLETION_V1": "completion_predicate_ref",
        "POSITIVE_VIEW_PROJECTION_V2": "projection_policy_ref",
        "SOURCE_IDENTITY_V2": "profile_ref",
    }
    # model_profile_ref is purpose-dependent, and handled by exact overrides below.
    for profile, fields in profile_groups.items():
        if profile == "FINITE_MODEL_FIDELITY_V1":
            continue
        add_group(table, fields, "ExternalProfileRef", profiles=(profile,), ref_class="PINNED_PROFILE_REF")
    return table


OVERRIDES = {
    "input_disposition_record/2.assigned_input_ref.source_member.source_manifest_ref": {"representation": "TypedRef", "allowed_keys": ["source_manifest/1"], "ref_class": "PRIOR_ACCEPTED_ONLY", "cardinality": "0..1; SOURCE_MEMBER branch only"},
    "input_disposition_record/2.assigned_input_ref.artifact_ref": {"representation": "TypedRef", "allowed_keys": ["source_manifest/1", "legacy_raw_ref/1", "surface_collector_record/2"], "ref_class": "PRIOR_ACCEPTED_ONLY", "cardinality": "0..1; CANONICAL_ARTIFACT branch only"},
    "inventory_revision/2.assigned_input_refs[].source_member.source_manifest_ref": {"representation": "TypedRef", "allowed_keys": ["source_manifest/1"], "ref_class": "PRIOR_ACCEPTED_ONLY", "cardinality": "0..65536; SOURCE_MEMBER branches"},
    "inventory_revision/2.assigned_input_refs[].artifact_ref": {"representation": "TypedRef", "allowed_keys": ["source_manifest/1", "legacy_raw_ref/1", "surface_collector_record/2"], "ref_class": "PRIOR_ACCEPTED_ONLY", "cardinality": "0..65536; CANONICAL_ARTIFACT branches"},
    "stage_completion/1.required_lane_slot_results": {"representation": "LaneSlotResult", "allowed_keys": [], "ref_class": "PRIOR_ACCEPTED_ONLY", "cardinality": "1..65536"},
    "stage_completion/1.required_lane_slot_results[].lane_completion_ref": {"representation": "TypedRef", "allowed_keys": ["lane_completion/1"], "ref_class": "PRIOR_ACCEPTED_ONLY", "cardinality": "1..65536; exactly one per required slot"},
    "stage_completion/1.required_lane_slot_results[].slot_contract_ref": {"representation": "ExternalProfileRef", "profile_contracts": ["MANDATORY_LANE_SLOT_V1"], "ref_class": "HISTORY_CONTEXT_BINDING", "cardinality": "1..65536; exactly one per required slot"},
    "surface_collector_record/2.collection_run.collector_profile_ref": {"representation": "ExternalProfileRef", "profile_contracts": ["COLLECTOR_CAPABILITY_V2"], "ref_class": "PINNED_PROFILE_REF"},
    "inventory_revision/2.collector_profile_refs": {"representation": "ExternalProfileRef", "profile_contracts": ["COLLECTOR_CAPABILITY_V2"], "ref_class": "HISTORY_CONTEXT_BINDING"},
    "view_manifest/1.allowed_member_refs": {"representation": "RawRef", "profile_contracts": ["RETAINED_OPAQUE_BYTES_V1"], "ref_class": "CONTENT_OBJECT", "cardinality": "0..65536"},
    "command_receipt/1.result_object_refs": {"representation": "TypedRef", "allowed_keys": [], "ref_class": "POST_ACCEPTANCE_SIDECAR", "cardinality": "0..65536"},
    "build_manifest/1.application_source_generation_ref": {"representation": "TypedRef", "allowed_keys": ["source_generation/1"], "ref_class": "PINNED_INSTALLATION_REF", "delegated_decision_id": "OD-027"},
    "build_manifest/1.stage_lane_policy_refs": {"representation": "TypedRef", "allowed_keys": ["lane_spec/1", "policy_revision/1", "stage_spec/1"], "ref_class": "PINNED_INSTALLATION_REF", "delegated_decision_id": "OD-027"},
    "campaign_genesis/1.application_generation_ref": {"representation": "TypedRef", "allowed_keys": ["build_manifest/1"], "ref_class": "PINNED_INSTALLATION_REF", "delegated_decision_id": "OD-027"},
    "source_drift_impact_assessment/1.affected_evidence_qualification_refs": {"representation": "TypedRef", "allowed_keys": ["evidence_qualification_assessment/1"], "ref_class": "PRIOR_ACCEPTED_ONLY"},
    "source_drift_impact_assessment/1.affected_obligation_qualification_refs": {"representation": "TypedRef", "allowed_keys": ["coverage_obligation_qualification/1"], "ref_class": "PRIOR_ACCEPTED_ONLY"},
    "state_model/1.model_profile_ref": {"representation": "ExternalProfileRef", "profile_contracts": ["MODEL_ARTIFACT_V1"], "ref_class": "PINNED_PROFILE_REF"},
    "validation_result/1.contract_ref": {"representation": "ExternalProfileRef", "profile_contracts": ["QUALIFIED_VALIDATOR_V2"], "ref_class": "PINNED_PROFILE_REF"},
    "compatibility_gate_result/1.governing_policy_ref": {"representation": "ExternalProfileRef", "profile_contracts": ["COMPATIBILITY_GATE_V2"], "ref_class": "PINNED_PROFILE_REF"},
    "transition_authorization_proposal/1.governing_policy_ref": {"representation": "TypedRef", "allowed_keys": ["policy_revision/1"], "ref_class": "PRIOR_ACCEPTED_ONLY"},
    "source_identity/1.profile_ref": {"representation": "ExternalProfileRef", "profile_contracts": ["SOURCE_IDENTITY_V2"], "ref_class": "PINNED_PROFILE_REF"},
}


def cardinality(node, field):
    owner = field.split(".", 1)[0].removesuffix("[]")
    declaration = next(f for f in node["body"]["fields"] if f["field"] == owner)
    plural = declaration.get("array") or declaration.get("design_type", "").endswith("[]") or declaration.get("schema", {}).get("type") == "array"
    return "0..65536" if plural or "[]" in field else "0..1" if declaration["optional"] else "1"


def bounded_cardinality(node, field, previous):
    fallback = cardinality(node, field)
    if previous in (None, "EXACT_REGISTERED_FIELD_CARDINALITY"):
        return fallback
    match = re.match(r"^(\d+)(?:\.\.(\d+|N|\*|65536))?", previous)
    if not match:
        return fallback
    minimum = int(match[1])
    maximum = int(match[2]) if match[2] and match[2].isdigit() else 65536 if match[2] else minimum
    assert 0 <= minimum <= maximum <= 65536, (field, previous)
    suffix = previous[match.end():].strip()
    return (str(minimum) if minimum == maximum else f"{minimum}..{maximum}") + ("; " + suffix if suffix else "")


def main():
    preserve()
    graph = read(OUT / "REFERENCE_FRONTIER.json")
    table = decisions()
    nodes = {n["key"]: copy.deepcopy(n) for n in graph["nodes"]}
    from nested_reference_decisions import additions
    nested_decisions = additions(nodes) if (OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json").exists() else {}
    active_overrides = {**OVERRIDES, **nested_decisions}
    # A receipt enumerates the operation's returned immutable objects, including
    # a legal empty return set. It never invents acceptance authority itself.
    active_overrides["command_receipt/1.result_object_refs"]["allowed_keys"] = sorted(nodes)
    pending = []
    corrected = []
    edges = []
    profiles = defaultdict(list)
    for key, node in nodes.items():
        refs = {r["field"]: copy.deepcopy(r) for r in node["fresh_material_ref_frontier"]}
        if key == "command_envelope/1":
            obsolete = refs.pop("command_payload_ref", None)
            if obsolete:
                corrected.append({"id": key + ".command_payload_ref", "resolution": "OD-016 successor requires inline command_payload"})
            refs["command_payload.proposed_object_refs"] = {"field": "command_payload.proposed_object_refs", "allowed_keys": sorted(k for k in nodes if k.split("/")[0] not in ("command_envelope", "commit_body", "command_receipt")), "ref_class": "CONTENT_OBJECT", "cardinality": "0..65536"}
        if key == "commit_body/1":
            refs["immutable_object_refs"]["allowed_keys"] = sorted(k for k in nodes if k.split("/")[0] not in ("commit_body", "command_receipt"))
            refs["immutable_object_refs"]["cardinality"] = "1..65536"
        event_parent = "command_payload.events[]" if key == "command_envelope/1" else "ordered_event_bodies[]" if key == "commit_body/1" else None
        if event_parent:
            event_targets = {
                "artifact_ref": (sorted(k for k in nodes if k.split("/")[0] not in ("command_envelope", "commit_body", "command_receipt")), "CONTENT_OBJECT"),
                "target_ref": (sorted(nodes), "CONTENT_OR_PRIOR"),
                "result_ref": (sorted(k for k, n in nodes.items() if ((n.get("qualified_registry_row") or n.get("historical_proposal") or {}).get("canonical_role") in ("ASSESSMENT", "DECISION"))), "CONTENT_OR_PRIOR"),
                "aggregate_ref": (["campaign_genesis/1", "stage_run/1", "lane_run/1", "attempt/1"], "PRIOR_ACCEPTED_ONLY"),
                "basis_refs": (sorted(nodes), "PRIOR_ACCEPTED_ONLY"),
                "attempt_ref": (["attempt/1"], "PRIOR_ACCEPTED_ONLY"),
                "assignment_ref": (["assignment_manifest/1"], "PRIOR_ACCEPTED_ONLY"),
                "package_binding_ref": (["assignment_package_binding/1"], "PRIOR_ACCEPTED_ONLY"),
            }
            for field, (targets, ref_class) in event_targets.items():
                path = event_parent + "." + field
                refs[path] = {"field": path, "allowed_keys": targets, "ref_class": ref_class, "cardinality": "0..65536; exact event variant requires its declared fields"}
        renamed_nested = {
            "input_disposition_record/2": {"assigned_input_ref.source_manifest_ref": "assigned_input_ref.source_member.source_manifest_ref"},
            "inventory_revision/2": {"assigned_input_refs[].source_manifest_ref": "assigned_input_refs[].source_member.source_manifest_ref"},
        }
        for previous, current in renamed_nested.get(key, {}).items():
            if previous in refs:
                refs[current] = {**refs.pop(previous), "field": current}
                corrected.append({"id": key + "." + previous, "resolution": "Tagged SOURCE_MEMBER branch owns the source_member object", "current_field": current})
        if key == "source_drift_impact_assessment/1":
            bad = refs.pop("affected_qualification_refs", None)
            if bad:
                corrected.append({"id": key + ".affected_qualification_refs", "resolution": "REMOVE_NONBODY_REFERENCE; use the two exact §132 arrays", "previous": bad})
        # Every own ref and historical nested reference is represented; no lost edges.
        own_names = {f["field"] for f in node["body"]["fields"]}
        for issue in graph["reference_frontier"]:
            if issue["id"].startswith(key + "."):
                field = issue["id"][len(key) + 1:]
                if field.split(".", 1)[0].removesuffix("[]") in own_names:
                    refs.setdefault(field, {"field": field})
        for full, override in active_overrides.items():
            if full.startswith(key + "."):
                field = full[len(key) + 1:]
                refs[field] = {"field": field, **override}
        resolved = []
        for field, entry in refs.items():
            full = key + "." + field
            decision = active_overrides.get(full)
            # A HistoryCut is an inline authority-binding tuple, not a TypedRef
            # to a fabricated separately accepted history_cut object.
            if entry.get("allowed_keys") == ["history_cut/1"]:
                decision = {"representation": "HistoryCut", "ref_class": "HISTORY_INPUT"}
            if decision is None and not entry.get("allowed_keys"):
                if field.endswith(".artifact_contract_ref"):
                    parent_field = field.removesuffix(".artifact_contract_ref").removesuffix("[]")
                    parent = table.get(parent_field.rsplit(".", 1)[-1]) or table.get(parent_field)
                    assert parent and parent.get("profile_contracts"), (full, parent_field)
                    decision = {"representation": "ExternalProfileRef", "profile_contracts": parent["profile_contracts"], "ref_class": "PINNED_PROFILE_REF"}
                else:
                    decision = table.get(field.rsplit(".", 1)[-1]) or table.get(field)
            if decision is None and entry.get("allowed_keys"):
                decision = {"representation": "TypedRef", "allowed_keys": entry["allowed_keys"], "ref_class": entry["ref_class"]}
            if decision is None:
                pending.append({"id": full, "entry": entry})
                continue
            item = {"field": field, "cardinality": bounded_cardinality(node, field, entry.get("cardinality")), **copy.deepcopy(decision)}
            if full == "residual_risk/1.basis_refs":
                item["cardinality"] = "1..256"
            assert item["ref_class"], full
            assert set(item.get("allowed_keys", [])) <= set(nodes), full
            item["same_commit"] = item["ref_class"] in ("CONTENT_OBJECT", "CONTENT_OR_PRIOR")
            item["authority_rule"] = "Exact qualified context and verified durable dependencies; absent proof rejects without canonical mutation"
            resolved.append(item)
            for target in item.get("allowed_keys", []):
                edges.append({"from": key, "to": target, **item})
            for profile in item.get("profile_contracts", []):
                profiles[profile].append(full)
        node["resolved_own_material_refs"] = resolved
        node["schema_generation_ready"] = False
    write("OWN_REFERENCE_RESOLUTIONS.json", {
        "source_frontier_raw_digest": digest(OUT / "REFERENCE_FRONTIER.json"),
        "nodes": list(nodes.values()), "edges": edges, "profile_usage": dict(sorted(profiles.items())),
        "corrections": corrected, "pending": pending,
        "reference_frontier_reviewed": len(graph["reference_frontier"]),
        "semantic_fixed_point_reached": False,
        "remaining": "Closed nested body/profile grammars, temporal predicates and version propagation must be executed before qualification",
    })
    print({"own_reference_frontier_reviewed": len(graph["reference_frontier"]), "unresolved_reference_representations": len(pending),
           "finite_profile_purposes": len(profiles), "canonical_edges": len(edges)})
    for issue in pending:
        print(issue["id"])


if __name__ == "__main__":
    main()

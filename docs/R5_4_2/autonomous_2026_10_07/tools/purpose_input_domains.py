"""Closed finite evaluation-input representations for OD003 purpose contracts.

These are verification views, never caller-supplied authority or installation
instance backlinks. Complete cut/subject derivation is separately mandatory.
"""
from __future__ import annotations

from purpose_contracts import array, object_schema, ref

# Named direct inputs from the complete purpose contract sections. A star is
# a subject-selected complete output/material-fact domain, not an arbitrary
# algorithm or success fallback; the fixed predicate must independently derive
# the exact applicable set, including adverse/unknown facts.
ROOTS = {
    "STAGE": {
        "stage_runs": "stage_run", "stage_specs": "stage_spec", "lane_completions": "lane_completion",
        "required_outputs": "*", "inventory": "inventory_revision", "accounting": "input_disposition_record surface_collector_record scope_state_record",
        "obligations": "coverage_obligation", "qualifications": "coverage_obligation_qualification evidence_qualification_assessment evidence_applicability_assessment",
        "knowledge_isolation": "knowledge_state isolation_qualification contamination_assessment",
        "material_unresolved_facts": "*"},
    "LANE": {
        "lane_runs": "lane_run", "lane_specs": "lane_spec", "attempts": "attempt", "assignments": "assignment_manifest",
        "bindings": "assignment_package_binding", "admissions": "lane_result_admission_evidence", "results": "bdb_audit_lane_result",
        "knowledge": "knowledge_state", "outputs": "*", "isolation": "isolation_qualification", "contamination": "contamination_assessment"},
    "EXECUTOR": {
        "executors": "executor_spec", "planning_contexts": "assignment_manifest execution_descriptor",
        "sources": "source_generation", "environments": "environment_record", "knowledge": "knowledge_state",
        "isolation": "isolation_qualification isolation_baseline_profile", "channel_observations": "observation",
        "exposures": "potential_exposure_record holdout_exposure_assessment contamination_assessment"},
    "DELIVERY": {
        "assignments": "assignment_manifest", "bindings": "assignment_package_binding", "attempts": "attempt",
        "knowledge": "knowledge_state", "grants": "grant_body", "exposures": "potential_exposure_record", "delivery_specs": "delivery_spec"},
    "COLLECTOR": {
        "source_manifests": "source_manifest", "declared_surface_keys": "surface_key", "manual_observations": "observation",
        "capture_observations": "observation", "proposed_collectors": "surface_collector_record", "exclusion_decisions": "approval_decision scope_state_record"},
    "METHOD": {
        "experiments": "experiment_spec", "descriptors": "execution_descriptor", "observations": "observation",
        "executions": "execution_result", "control_executions": "execution_result", "cleanup": "cleanup_result",
        "fault_activation": "fault_run_record", "dependency_graphs": "evidence_dependency_graph",
        "applicability": "evidence_applicability_assessment", "independence": "dependency_independence_assessment",
        "model_fidelity": "model_fidelity_assessment", "qualified_basis": "evidence_qualification_assessment"},
    "CONFIRMATION": {
        "discoveries": "discovery_record", "evidence_qualifications": "evidence_qualification_assessment",
        "applicability": "evidence_applicability_assessment", "experiments": "experiment_spec",
        "observations": "observation", "contradictions": "contradiction_revision"},
    "MATCHING": {
        "subjects": "discovery_record finding_claim_revision", "corpora": "corpus_manifest", "eligible_members": "*",
        "invariants": "invariant_revision", "source_scope_facts": "source_generation scope_state_record surface_key surface_record",
        "prior_matching_assessments": "finding_defect_match_assessment"},
    "NOVELTY": {
        "matching_assessments": "discovery_corpus_match_assessment", "discoveries": "discovery_record", "corpora": "corpus_manifest"},
    "RELATIONSHIP": {
        "discoveries": "discovery_record", "confirmations": "discovery_confirmation_assessment", "prior_stage_completions": "stage_completion",
        "prior_claims": "finding_claim_revision", "prior_obligations": "coverage_obligation", "qualifications": "coverage_obligation_qualification evidence_qualification_assessment evidence_applicability_assessment",
        "missed_results": "bdb_audit_lane_result", "adjudications": "finding_adjudication_decision"},
    "ASSESSOR": {
        "assessments": "clean_control_assessment finding_axis_assessment finding_defect_match_assessment materiality_assessment",
        "subjects": "finding_claim_revision defect_unit negative_opportunity_unit surface_key surface_record invariant_revision scope_state_record",
        "observations": "observation", "qualified_evidence": "evidence_qualification_assessment evidence_applicability_assessment",
        "ground_truth_corpora": "corpus_manifest", "applicable_basis": "*", "materiality_policies": "policy_revision"},
    "MODEL": {
        "models": "state_model", "sources": "source_generation", "exploration_observations": "observation",
        "conformance_qualifications": "evidence_qualification_assessment model_fidelity_assessment"},
    "FAULT": {
        "fault_specs": "fault_spec", "descriptors": "execution_descriptor", "activation_observations": "observation",
        "cleanup_observations": "observation", "fault_runs": "fault_run_record", "cleanup_results": "cleanup_result"},
    "RELEASE": {
        "conclusions": "campaign_conclusion", "stop_evaluations": "stop_evaluation", "stop_inputs": "stop_input",
        "final_cases": "final_assurance_case", "sources": "source_generation", "findings": "finding_claim_revision finding_adjudication_decision",
        "risks": "residual_risk", "approvals": "approval_decision", "previous_qualifications": "release_qualification"},
    "EFFORT": {
        "stage_specs": "stage_spec", "stage_runs": "stage_run", "attempts": "attempt", "executions": "execution_result",
        "observations": "observation", "discoveries": "discovery_record", "root_causes": "root_cause_revision",
        "obligations": "coverage_obligation coverage_obligation_qualification", "challengers": "challenger_assignment challenger_result",
        "method_qualifications": "evidence_qualification_assessment"},
    "RECOVERY": {
        "commits": "commit_body", "immutable_objects": "*", "commands": "command_envelope", "anchors": "history_anchor_receipt"},
}

RAW_INPUTS = {"DELIVERY": ("bound_package_bytes",), "COLLECTOR": ("collector_capture_bytes",),
              "METHOD": ("observation_and_method_evidence_bytes",), "MODEL": ("model_bytes", "source_mapping_bytes"),
              "FAULT": ("planned_activation_check_bytes",), "RECOVERY": ("accepted_raw_bytes", "receipt_sidecar_bytes")}
PROFILE_INPUTS = {"EXECUTOR": ("dependency_runner_boundary_capture_profiles",), "COLLECTOR": ("collector_capability",),
                  "ASSESSOR": ("authenticated_assessor_principal",), "FAULT": ("activation_and_cleanup_capture_profiles",)}
EVENT_INPUTS = {"LANE": ("PRIOR_ACCEPTED_ATTEMPT_STARTED",), "DELIVERY": ("PRIOR_ACCEPTED_ATTEMPT_STARTED",),
                "RECOVERY": ("EXACT_ACCEPTED_CHAIN_EVENTS",)}


EXACT_SINGLE_ROOTS = {
    "STAGE": {"stage_runs", "stage_specs", "inventory"},
    "LANE": {"lane_runs", "lane_specs", "knowledge"},
    "EXECUTOR": {"executors", "planning_contexts", "sources", "environments", "knowledge"},
    "DELIVERY": {"assignments", "attempts", "knowledge", "delivery_specs"},
    "COLLECTOR": {"source_manifests", "proposed_collectors"},
    "METHOD": {"experiments", "descriptors"},
    "CONFIRMATION": {"discoveries"}, "MATCHING": {"subjects", "corpora"},
    "NOVELTY": {"discoveries", "corpora"}, "RELATIONSHIP": {"discoveries"},
    "ASSESSOR": {"assessments"}, "MODEL": {"models", "sources"},
    "FAULT": {"fault_specs", "descriptors"},
    "RELEASE": {"conclusions", "stop_evaluations", "stop_inputs"},
    "EFFORT": set(), "RECOVERY": set(),
}


def domain(purpose, schema_keys):
    from common_grammars import catalog
    common = catalog(schema_keys)
    names = {"typed_ref", "raw_ref", "external_profile_ref", "accepted_event_ref",
             "history_cut" if purpose == "RECOVERY" else "accepted_history_cut"}
    defs = {}
    def refs(value):
        if isinstance(value, dict):
            if "$ref" in value:
                yield value["$ref"].removeprefix("#/$defs/")
            for child in value.values():
                yield from refs(child)
        elif isinstance(value, list):
            for child in value:
                yield from refs(child)
    while names:
        name = names.pop()
        if name in defs:
            continue
        defs[name] = common[name]
        names.update(refs(common[name]))
    if purpose not in ROOTS:
        raise ValueError("UNKNOWN_PURPOSE_INPUT_DOMAIN")
    by_kind = {key.split("::", 1)[1].split("/", 1)[0]: key for key in schema_keys}
    if len(by_kind) != len(schema_keys):
        raise ValueError("AMBIGUOUS_PURPOSE_INPUT_WIRE_VERSION")
    fields, entries = {}, []
    for name, kinds in ROOTS[purpose].items():
        selected = sorted(schema_keys) if kinds == "*" else sorted(by_kind[kind] for kind in kinds.split())
        targets = [key.split("::", 1)[1].split("/", 1)[0] for key in selected]
        fields[name] = array({"allOf": [ref("typed_ref"), {"properties": {"kind": {"enum": targets}}}]})
        if name in EXACT_SINGLE_ROOTS[purpose]:
            fields[name].update(minItems=1, maxItems=1)
        elif (purpose, name) == ("RELEASE", "previous_qualifications"):
            fields[name].update(maxItems=1)
        entries.append({"field": name, "allowed_kind_versions": selected,
                        "selection": "COMPLETE_EXACT_SUBJECT_DERIVED_SET_AT_VERIFIED_CUT",
                        "cardinality": {"minItems": fields[name]["minItems"], "maxItems": fields[name]["maxItems"]},
                        "empty_means": "NO_SUCCESS_WAIVER; FIXED_ALGORITHM_DECIDES_REQUIRED_MISSING_OR_NOT_APPLICABLE"})
    for name in RAW_INPUTS.get(purpose, ()):
        fields[name] = array(ref("raw_ref"))
    for name in PROFILE_INPUTS.get(purpose, ()):
        fields[name] = array(ref("external_profile_ref"))
    for name in EVENT_INPUTS.get(purpose, ()):
        fields[name.lower()] = array(ref("accepted_event_ref"))
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$defs": defs,
              **object_schema({"input_history_cut": ref("history_cut" if purpose == "RECOVERY" else "accepted_history_cut"),
                               "inputs": object_schema(fields)})}
    return {"purpose": purpose, "input_schema": schema, "canonical_inputs": entries,
            "raw_input_fields": list(RAW_INPUTS.get(purpose, ())),
            "external_profile_input_fields": list(PROFILE_INPUTS.get(purpose, ())),
            "event_input_selectors": list(EVENT_INPUTS.get(purpose, ())),
            "source_section_selector": "EXACT_OD003_PURPOSE_HEADING_" + purpose,
            "status": "DRAFT_INPUT_VIEW_PENDING_PER_KIND_SELECTOR_AND_WITNESS_PARITY",
            "authority": "INDEPENDENT_COMPLETE_CUT_SUBJECT_RAW_PROFILE_DERIVATION_REQUIRED; CALLER_VIEWS_NOT_AUTHORITY",
            "runtime_api": "NOT_IMPLEMENTED_OR_QUALIFIED_BY_THIS_REPRESENTATION",
            "conditional_witness_rule": "FIXED_PURPOSE_ALGORITHM_REQUIRES_ALL_APPLICABLE_WITNESSES; EMPTY_INPUT_NEVER_PROVES_SUCCESS"}


WITNESSES = {
    "STAGE": "lane_completion inventory_revision input_disposition_record coverage_obligation_qualification evidence_qualification_assessment evidence_applicability_assessment isolation_qualification contamination_assessment",
    "LANE": "assignment_package_binding lane_result_admission_evidence bdb_audit_lane_result knowledge_state isolation_qualification contamination_assessment",
    "EXECUTOR": "observation isolation_qualification potential_exposure_record holdout_exposure_assessment contamination_assessment",
    "DELIVERY": "assignment_package_binding knowledge_state grant_body potential_exposure_record",
    "COLLECTOR": "observation source_manifest surface_key approval_decision scope_state_record",
    "METHOD": "observation execution_result cleanup_result fault_run_record evidence_dependency_graph evidence_applicability_assessment dependency_independence_assessment model_fidelity_assessment evidence_qualification_assessment",
    "CONFIRMATION": "evidence_qualification_assessment evidence_applicability_assessment observation contradiction_revision",
    "MATCHING": "corpus_manifest invariant_revision source_generation scope_state_record finding_defect_match_assessment",
    "NOVELTY": "discovery_corpus_match_assessment corpus_manifest",
    "RELATIONSHIP": "discovery_confirmation_assessment stage_completion coverage_obligation_qualification evidence_qualification_assessment evidence_applicability_assessment finding_adjudication_decision",
    "ASSESSOR": "observation evidence_qualification_assessment evidence_applicability_assessment corpus_manifest policy_revision",
    "MODEL": "observation evidence_qualification_assessment model_fidelity_assessment",
    "FAULT": "observation fault_run_record cleanup_result",
    "RELEASE": "campaign_conclusion stop_evaluation stop_input final_assurance_case finding_adjudication_decision residual_risk approval_decision release_qualification",
    "EFFORT": "stage_run execution_result observation discovery_record root_cause_revision coverage_obligation_qualification challenger_result evidence_qualification_assessment",
    "RECOVERY": "commit_body history_anchor_receipt",
}


def context_domains(purpose, contract, variant, schema_keys):
    view = contract.get("input_domain")
    if not isinstance(view, dict) or view.get("purpose") != purpose:
        raise ValueError("PURPOSE_INPUT_DOMAIN_MISSING_OR_WRONG")
    by_kind = {key.split("::", 1)[1].split("/", 1)[0]: key for key in schema_keys}
    inputs = sorted({key for row in view["canonical_inputs"] for key in row["allowed_kind_versions"]})
    witnesses = sorted(by_kind[kind] for kind in WITNESSES[purpose].split())
    outputs = contract["output_domain"]
    if purpose == "ASSESSOR":
        kind = variant["assessment_kind_version"].split("::", 1)[1].split("/", 1)[0]
        branches = contract["output_domain_by_context"]
        selected = [values for key, values in branches.items() if key.split(":", 1)[0] == kind]
        if not selected:
            raise ValueError("PURPOSE_ASSESSOR_OUTPUT_DOMAIN_MISSING")
        outputs = sorted({value for values in selected for value in values})
    if not set(inputs + witnesses) <= set(schema_keys):
        raise ValueError("PURPOSE_INPUT_DOMAIN_UNREGISTERED_KEY")
    return {"input_kind_versions": inputs, "required_witness_kinds": witnesses, "enum_values": sorted(outputs)}

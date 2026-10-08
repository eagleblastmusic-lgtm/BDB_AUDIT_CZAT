"""Closed design grammars for the sixteen delegated predicate families.

Output stays in design/: it is neither a candidate nor schema authority.
Cross-object meaning is the exact companion purpose-contract decision text.
"""

from __future__ import annotations

import copy
import json

from jsonschema import Draft202012Validator

from execution import BASE, OUT, digest, read, write

MAX = 9007199254740991
METHODS = "STATIC_ANALYSIS DYNAMIC FAULT_INJECTION FUZZ PROPERTY DIFFERENTIAL METAMORPHIC STATEFUL CONCURRENCY ENDURANCE IMPLEMENTATION_MUTATION ORACLE_CHALLENGE MODEL_CONFORMANCE REPLAY".split()
OBSERVATIONS = "START FINISH MEASUREMENT ACTIVATION CLEANUP RESET CHANNEL_CAPTURE EXTERNAL_WITNESS".split()
DIMENSIONS = "PROCESS_INDEPENDENCE INSTANCE_INDEPENDENCE IMPLEMENTATION_INDEPENDENCE STORAGE_READ_PATH_INDEPENDENCE EXTERNAL_BOUNDARY_INDEPENDENCE ORACLE_INDEPENDENCE MODEL_AGENT_INDEPENDENCE HARNESS_INDEPENDENCE".split()


def const(value):
    return {"const": value}


def enum(values):
    return {"enum": values.split() if isinstance(values, str) else values}


def array(item, minimum=0):
    return {"type": "array", "items": item, "minItems": minimum, "maxItems": 65536, "uniqueItems": True}


def object_schema(properties):
    return {"type": "object", "properties": properties, "required": sorted(properties), "additionalProperties": False}


def number(minimum=0, maximum=MAX):
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


def ref(name):
    return {"$ref": "#/$defs/" + name}


def typed(kind):
    return {"allOf": [ref("typed_ref"), {"properties": {"kind": const(kind)}}]}


def definitions(schema_keys):
    inherited = read(BASE / "candidate/schemas/assignment_manifest__1.schema.json")["$defs"]
    result = {name: copy.deepcopy(inherited[name]) for name in ("typed_ref", "schema_revision_ref", "external_profile_ref", "raw_ref")}
    result["typed_ref"]["properties"]["kind"]["enum"] = sorted({key.split("::")[1].split("/")[0] for key in schema_keys})
    result["code"] = {"type": "string", "pattern": "^[A-Z][A-Z0-9_]{0,127}$"}
    result["schema_key"] = enum(schema_keys)
    return result


def catalog(schema_keys):
    def kinds(*names):
        return sorted(k for k in schema_keys if k.split("::")[1].split("/")[0] in names)
    registry = read(BASE / "candidate/BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json")
    channels = [r["channel"] for r in registry["profiles"]["ISOLATION_BASELINE_PROFILE_V1"]["channels"]]
    items = {
        "STAGE": ("STAGE_COMPLETION_V1", {
            "spec_selection": const("EXACT_STAGE_RUN_REF"),
            "completion_output_kind_versions": array(enum(schema_keys)),
            "required_qualification_status": const("QUALIFIED"),
        }, "SATISFIED VIOLATED UNKNOWN BLOCKED"),
        "LANE": ("LANE_COMPLETION_V1", {
            "spec_selection": const("EXACT_LANE_RUN_REF"),
            "allowed_result_kind_versions": array(enum(kinds("bdb_audit_lane_result")), 1),
            "required_isolation_results": array(enum("ENFORCED DECLARED"), 1),
        }, "SATISFIED VIOLATED UNKNOWN BLOCKED"),
        "EXECUTOR": ("EXECUTOR_ELIGIBILITY_V1", {
            "required_capabilities": array(ref("code")),
            "required_channel_classes": array(enum(channels)),
            "executor_selection": const("EXACT_ASSIGNMENT_OR_DESCRIPTOR_CONTEXT"),
            "require_fresh_session": {"type": "boolean"},
        }, "ELIGIBLE INELIGIBLE UNKNOWN BLOCKED"),
        "DELIVERY": ("NF02_DELIVERY_AUTHORIZATION_V1", {
            "delivery_selection": const("EXACT_ASSIGNMENT_CONTEXT"), "require_binding": const(True),
            "require_started": const(True), "raw_source": const("DURABLE_RAW_VAULT"),
            "retry_mode": const("EXACT_AUTHORIZED_BYTES"),
        }, "ALLOW DENY UNKNOWN BLOCKED"),
        "COLLECTOR": ("COLLECTOR_ACCOUNTING_V1", {
            "assigned_input_policy": const("ALL_MANIFEST_MEMBERS"), "output_identity": const("PRIOR_SURFACE_KEYS"),
            "terminal_dispositions": const(sorted("COLLECTED UNSUPPORTED EXCLUDED COLLECTION_FAILED PARSING_FAILED".split())),
            "exclusion_decision_type": const("SCOPE_EXCLUSION"),
        }, "ACCOUNTED INCOMPLETE BLOCKED"),
        "METHOD": ("METHOD_QUALIFICATION_V2", {
            "method_type": enum(METHODS), "control_selection": const("EXACT_PRIOR_SUBJECT_EXPERIMENT_CONTROLS"),
            "required_observation_kinds": array(enum(OBSERVATIONS)),
            "required_independence_dimensions": array(enum(DIMENSIONS)),
        }, "QUALIFIED REFUTED INCONCLUSIVE BLOCKED"),
        "CONFIRMATION": ("DISCOVERY_CONFIRMATION_V1", {
            "permitted_modes": array(enum("PREREGISTERED EXPLORATORY LEGACY_IMPORTED"), 1),
            "require_current_applicability": const(True), "require_exact_discovery_scope": const(True),
        }, "CONFIRMED NOT_CONFIRMED INCONCLUSIVE BLOCKED"),
        "MATCHING": ("EXACT_SCOPED_MATCH_V1", {
            "candidate_policy": const("ALL_ELIGIBLE_MEMBERS"),
            "exact_match_rule": const("EXACT_SUBJECT_SCOPE_INVARIANT_AND_MECHANISM"),
            "unknown_overlap": const("INCONCLUSIVE"), "require_complete_corpus": const(True),
        }, "MATCH NO_MATCH PARTIAL INCONCLUSIVE"),
        "NOVELTY": ("CORPUS_RELATIVE_NOVELTY_V1", {
            "basis": const("EXACT_PINNED_CORPUS"), "missing_basis": const("INCONCLUSIVE"),
        }, "NOVEL PREVIOUSLY_KNOWN PARTIALLY_NOVEL INCONCLUSIVE"),
        "RELATIONSHIP": ("PRIOR_FALSE_NEGATIVE_V1", {
            "minimum_prior_stages": number(1), "scope_rule": const("EXACT_REQUIRED_APPLICABLE_SCOPE"),
            "unknown_rule": const("INCONCLUSIVE"),
        }, "PREVIOUS_FALSE_NEGATIVE MULTI_STAGE_FALSE_NEGATIVE NOT_ESTABLISHED INCONCLUSIVE"),
        "ASSESSOR": ("CLAIM_RELATIVE_ASSESSMENT_V1", {
            "assessment_kind_version": enum(kinds("finding_axis_assessment", "finding_defect_match_assessment", "clean_control_assessment", "materiality_assessment")),
            "authorized_principal_refs": array(ref("external_profile_ref"), 1),
            "require_current_applicability": const(True), "require_opposing_evidence_accounting": const(True),
        }, "CONTRACT_SELECTED_DOMAIN"),
        "MODEL": ("FINITE_MODEL_FIDELITY_V1", {
            "max_states": number(1, 65536), "max_transitions": number(0, 65536),
            "max_path_steps": number(1, 65536), "require_complete_mapping": const(True),
            "require_implementation_conformance": {"type": "boolean"},
        }, "QUALIFIED BOUNDED INSUFFICIENT INVALIDATED"),
        "FAULT": ("QUALIFIED_ACTIVATION_V1", {
            "activation_check_refs": array(ref("raw_ref"), 1),
            "required_cleanup_profile_ref": ref("external_profile_ref"), "require_all_targets": const(True),
        }, "ACTIVATED NOT_ACTIVATED PARTIALLY_ACTIVATED BLOCKED HARNESS_FAILURE"),
        "RELEASE": ("FINAL_CHAIN_RELEASE_V1", {
            "blocking_severity_values": array(enum("CRITICAL HIGH MEDIUM LOW INFO")),
            "permitted_risk_acceptance_authority_refs": array(ref("external_profile_ref")),
            "require_completed_pass": const(True), "require_adequate_declared_scope": const(True),
        }, "READY READY_WITH_RESIDUAL_RISK TECHNICALLY_NOT_READY QUALIFICATION_BLOCKED"),
        "EFFORT": ("OBSERVED_EFFORT_V2", {
            "stage_selection": const("EXACT_REQUIRED_STAGE_SET_AT_INPUT_CUT"),
            "stage_requirements": array(object_schema({
                "stage_ordinal": number(0, 65536), "minimum_rounds": number(1),
                "required_method_types": array(enum(METHODS)), "minimum_observed_work_units": number(),
                "work_unit": enum("EXECUTIONS SOURCE_MEMBERS OBSERVED_WORKLOAD_UNITS"),
            }), 1),
        }, "SATISFIED INSUFFICIENT_DATA BLOCKED"),
        "RECOVERY": ("EXACT_DURABLE_RECOVERY_V1", {
            "receipt_policy": const("RECONSTRUCT_FROM_ACCEPTED_COMMIT"),
            "raw_policy": const("READBACK_ALL_ACCEPTED_REFS"), "head_policy": const("EXACT_CHAIN"),
            "anchor_policy": enum("LOCAL EXTERNAL_REQUIRED"),
        }, "VERIFIED CORRUPT UNAVAILABLE"),
    }
    defs = definitions(schema_keys)
    result = {}
    for purpose, (algorithm, params, outputs) in items.items():
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
                  "$id": "BDB_DESIGN_PROFILE_SCHEMA::" + algorithm, "$defs": defs,
                  **object_schema({"profile_id": const(algorithm), "algorithm_id": const(algorithm), "parameters": object_schema(params)})}
        Draft202012Validator.check_schema(schema)
        result[purpose] = {"purpose": purpose, "algorithm_id": algorithm, "parameter_schema": schema,
                           "output_domain": outputs.split(), "runtime_status": "NOT_RUN",
                           "authority_status": "OWNER_DELEGATED_DESIGN_ONLY; NOT_QUALIFIED"}
        from purpose_input_domains import domain
        result[purpose]["input_domain"] = domain(purpose, schema_keys)
        result[purpose]["input_domain"]["source_heading"] = "## " + purpose + " — " + algorithm
        result[purpose]["input_domain"]["source_file"] = (OUT / "design/PURPOSE_PREDICATE_CONTRACTS.md").relative_to(BASE.parents[1]).as_posix()
        result[purpose]["input_domain"]["source_raw_digest"] = digest(OUT / "design/PURPOSE_PREDICATE_CONTRACTS.md")
        if purpose in ("METHOD", "EFFORT"):
            result[purpose]["analysis_profile_key"] = algorithm.removesuffix("_V2") + "_V1"
        if purpose == "ASSESSOR":
            result[purpose]["output_domain_by_context"] = {
                "finding_axis_assessment:SEVERITY": "CRITICAL HIGH MEDIUM LOW INFO".split(),
                "finding_axis_assessment:MECHANISM": "SUPPORTED REFUTED INCONCLUSIVE BLOCKED NOT_APPLICABLE".split(),
                "finding_axis_assessment:REACHABILITY": "SUPPORTED REFUTED INCONCLUSIVE BLOCKED NOT_APPLICABLE".split(),
                "finding_axis_assessment:IMPACT": "SUPPORTED REFUTED INCONCLUSIVE BLOCKED NOT_APPLICABLE".split(),
                "finding_defect_match_assessment": "MATCH NO_MATCH PARTIAL UNRESOLVED".split(),
                "clean_control_assessment": "TRUE_NEGATIVE FALSE_POSITIVE UNRESOLVED BLOCKED".split(),
                "materiality_assessment": "MATERIAL NON_MATERIAL UNKNOWN CONFLICTED".split(),
            }
            result[purpose]["output_domain"] = sorted({v for values in result[purpose]["output_domain_by_context"].values() for v in values})
    return result


def example(schema, defs):
    if "$ref" in schema:
        return example(defs[schema["$ref"].rsplit("/", 1)[1]], defs)
    if "const" in schema:
        return copy.deepcopy(schema["const"])
    if "enum" in schema:
        return schema["enum"][0]
    if "allOf" in schema:
        base = example(schema["allOf"][0], defs)
        for part in schema["allOf"][1:]:
            for field, rule in part.get("properties", {}).items():
                base[field] = example(rule, defs)
        return base
    if schema.get("type") == "object":
        return {name: example(schema["properties"][name], defs) for name in schema["required"]}
    if schema.get("type") == "array":
        return [example(schema["items"], defs) for _ in range(schema["minItems"])]
    if schema.get("type") == "integer":
        return schema["minimum"]
    if schema.get("type") == "boolean":
        return True
    if schema.get("type") == "string":
        pattern = schema.get("pattern", "")
        return "0" * 64 if "64" in pattern else "TEST" if "A-Z" in pattern else "TEST_PROFILE"
    raise ValueError(schema)


def main():
    inventory = read(OUT / "OWN_BODY_INVENTORY.json")
    version_path = OUT / "design/VERSION_IMPACT_PLAN.json"
    mapping = read(version_path)["mapping"] if version_path.exists() else {n["key"]: n["key"] for n in inventory["nodes"]}
    keys = sorted("BDB_SCHEMA_REGISTRY::" + mapping[n["key"]] for n in inventory["nodes"])
    contracts = catalog(keys)
    results = []
    for purpose, contract in contracts.items():
        schema = contract["parameter_schema"]
        validator = Draft202012Validator(schema)
        valid = example(schema, schema["$defs"])
        validator.validate(valid)
        mutations = []
        extra = copy.deepcopy(valid)
        extra["trusted"] = True
        mutations.append(("CALLER_TRUST_EXTRA_FIELD", extra))
        wrong = copy.deepcopy(valid)
        wrong["algorithm_id"] = "UNQUALIFIED_RUNTIME_PREDICATE"
        mutations.append(("UNKNOWN_ALGORITHM", wrong))
        for field in valid["parameters"]:
            missing = copy.deepcopy(valid)
            del missing["parameters"][field]
            mutations.append(("MISSING_PARAMETER_" + field, missing))
        for name, mutation in mutations:
            assert not validator.is_valid(mutation), (purpose, name)
            results.append({"purpose": purpose, "vector": name, "schema_outcome": "REJECT", "canonical_runtime_outcome": "NOT_RUN"})
        results.append({"purpose": purpose, "vector": "EXACT_PROFILE_GRAMMAR", "schema_outcome": "ACCEPT", "canonical_runtime_outcome": "NOT_RUN"})
        if purpose == "ASSESSOR":
            materiality_keys = [key for key in keys if key.startswith("BDB_SCHEMA_REGISTRY::materiality_assessment/")]
            assert len(materiality_keys) == 1
            selected = copy.deepcopy(valid)
            selected["parameters"]["assessment_kind_version"] = materiality_keys[0]
            validator.validate(selected)
            assert contract["output_domain_by_context"]["materiality_assessment"] == ["MATERIAL", "NON_MATERIAL", "UNKNOWN", "CONFLICTED"]
            results.append({"purpose": purpose, "vector": "EXACT_MATERIALITY_KIND_AND_OUTPUT_DOMAIN",
                            "input": selected, "schema_outcome": "ACCEPT", "canonical_runtime_outcome": "NOT_RUN"})
            wrong = copy.deepcopy(selected)
            wrong["parameters"]["assessment_kind_version"] = next(key for key in keys if key.startswith("BDB_SCHEMA_REGISTRY::source_manifest/"))
            assert not validator.is_valid(wrong)
            results.append({"purpose": purpose, "vector": "SOURCE_FACT_IS_NOT_ASSESSOR_TARGET",
                            "input": wrong, "schema_outcome": "REJECT", "canonical_runtime_outcome": "NOT_RUN"})
    write("design/PURPOSE_CONTRACT_GRAMMARS.json", contracts)
    write("design/PURPOSE_GRAMMAR_KNOWN_ANSWERS.json", {
        "design_text_raw_digest": digest(OUT / "design/PURPOSE_PREDICATE_CONTRACTS.md"),
        "contracts": len(contracts), "vectors": results,
        "claim": "Pure draft grammar known-answer checks only; no canonical state, runtime qualification or candidate authority",
    })
    print(json.dumps({"purpose_contracts": len(contracts), "draft_grammar_vectors_passed": len(results), "runtime_vectors": "NOT_RUN"}))


if __name__ == "__main__":
    main()

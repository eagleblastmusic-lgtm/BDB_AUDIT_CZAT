"""Draft external-profile contracts and a real transitive profile work queue.

No candidate is written. A syntactically closed profile is not automatically a
semantically qualified predicate. Unresolved obligations remain in the queue.
"""

from __future__ import annotations

import copy
import json
from collections import deque

from jsonschema import Draft202012Validator

from common_grammars import catalog as common_catalog
from execution import BASE, OUT, digest, preserve, read, write
from purpose_contracts import array, const, enum, number, object_schema, ref, typed


def build_catalog(keys):
    defs = common_catalog(keys)
    contracts = {}

    def add(name, fields, *, dependencies=(), rule, semantic_review="PENDING_CROSS_OBJECT_REVIEW", raw=False):
        assert name not in contracts, name
        schema = object_schema(fields if raw else {"profile_id": const(name), **fields})
        schema.update({"$schema": "https://json-schema.org/draft/2020-12/schema", "$defs": defs})
        payload = schema if raw else None
        if raw:
            schema = object_schema({"profile_id": const(name), "parser_profile_ref": ref("external_profile_ref"),
                                    "payload_schema_ref": ref("raw_ref"), "max_bytes": number(1, 67108864)})
            schema.update({"$schema": "https://json-schema.org/draft/2020-12/schema", "$defs": defs})
            dependencies = [*dependencies, "STRICT_JSON_CAPTURE_V1", "BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1"]
        contracts[name] = {"grammar": schema, "dependencies": sorted(set(dependencies)),
                           "rule": rule, "semantic_review": semantic_review,
                           "representation": "RETAINED_RAW_PAYLOAD" if raw else "INSTALLED_EXTERNAL_PROFILE",
                           "authority": "DESIGN_ONLY_NOT_QUALIFIED"}
        if payload is not None:
            contracts[name]["payload_grammar"] = payload
        return contracts[name]

    def common(name, definition, dependencies, rule, raw=False):
        body = copy.deepcopy(defs[definition])
        add(name, body["properties"], dependencies=dependencies, rule=rule, raw=raw)
        contracts[name]["payload_grammar" if raw else "grammar"]["required"] = body["required"]

    # The sixteen distinct algorithms retain their separate input/output domains.
    for purpose, item in read(OUT / "design/PURPOSE_CONTRACT_GRAMMARS.json").items():
        name = item.get("analysis_profile_key", item["algorithm_id"])
        contracts[name] = {"grammar": copy.deepcopy(item["parameter_schema"]), "dependencies": [],
                           "rule": "Exact " + purpose + " section of PURPOSE_PREDICATE_CONTRACTS.md",
                           "semantic_review": "DEFINED_BY_PURPOSE_DECISION; CROSS_OBJECT_EXECUTION_NOT_RUN",
                           "representation": "INSTALLED_PURPOSE_CONTRACT", "purpose": purpose,
                           "input_domain": item.get("input_domain"), "output_domain": item["output_domain"],
                           "authority": "DESIGN_ONLY_NOT_QUALIFIED"}
        if "output_domain_by_context" in item:
            contracts[name]["output_domain_by_context"] = copy.deepcopy(item["output_domain_by_context"])
        if name != item["algorithm_id"]:
            contracts[name]["wire_profile_id"] = item["algorithm_id"]

    for name, definition, dependencies, rule in (
        ("COLLECTOR_CAPABILITY_V2", "collector_capability", ["RETAINED_PRODUCER_CODE_V1", "SOURCE_IDENTITY_V2", "EXECUTION_RUNNER_V2"],
         "OD034: exact retained collector code defines the meaning and independent classification of the supported language/framework/input-class codes. Required sorted unique language and framework sets are explicit; empty framework set grants no framework capability. Unknown or unsupported classification is UNSUPPORTED, never automatic EXCLUDED_SCOPE or complete coverage. Select the prior descriptor runner command; source member accounting is a separate COLLECTOR_ACCOUNTING_V1 predicate. No future collector/run ref."),
        ("TOOL_CAPTURE_V2", "tool_capture_profile", ["RETAINED_PRODUCER_CODE_V1", "EXECUTION_COMMAND_JSON_V1", "RETAINED_OPAQUE_BYTES_V1"],
         "Select prior descriptor experiment; exact command, producer authorization, environment and capture code independently match actual invocation."),
        ("CLEANUP_ASSESSMENT_V2", "cleanup_profile", ["CLEANUP_EXPECTED_OBSERVABLE_V1", "OBSERVATION_CAPTURE_V2"],
         "Select exact cleanup subject descriptor. VERIFIED iff all preregistered checks have eligible independent capture equality. Failure FAILED, unavailable BLOCKED, unverifiable UNKNOWN."),
        ("SURFACE_COLLECTOR_RECORD_JSON_V1", "collection_run", ["COLLECTOR_CAPABILITY_V2", "COLLECTOR_ACCOUNTING_V1"],
         "Parse full immutable collection run, compare entire proposed semantic run; do not infer trustworthy collection from raw alone."),
        ("TOOL_EXECUTION_RECORD_JSON_V1", "tool_run", ["TOOL_CAPTURE_V2", "EXECUTION_COMMAND_JSON_V1", "RETAINED_OPAQUE_BYTES_V1"],
         "Exact full ToolRun equality after strict parsing, including nullable actual times/exit and all retained outputs; trusted capture remains conjunctive."),
        ("FAULT_RUN_RECORD_JSON_V1", "fault_run", ["QUALIFIED_ACTIVATION_V1", "CLEANUP_ASSESSMENT_V2"],
         "Exact full FaultRun equality; independently derive activation from planned fault, descriptor, observations and prior cleanup."),
        ("CLEANUP_EXPECTED_OBSERVABLE_V1", "cleanup_expected_observable", ["OBSERVATION_CAPTURE_V2", "RETAINED_OPAQUE_BYTES_V1"],
         "Strict JSON selector, typed exact value equality; no eval, tolerance, coercion or default success."),
    ):
        common(name, definition, dependencies, rule, raw=name.endswith("JSON_V1") or name == "CLEANUP_EXPECTED_OBSERVABLE_V1")
    contracts["TOOL_CAPTURE_V2"]["wire_profile_id"] = "TOOL_CAPTURE_V3"

    # Captured values have a finite domain, rather than an untyped JSON bag.
    add("OBSERVATION_CAPTURE_V2", {
        "capture_code_ref": ref("raw_ref"),
        "observation_kind": enum("START FINISH MEASUREMENT ACTIVATION CLEANUP RESET CHANNEL_CAPTURE EXTERNAL_WITNESS"),
        "value_contract": enum("INTEGER BOOLEAN TEXT NULL RATIONAL RAW"),
        "context_selection": const("EXACT_PRIOR_DESCRIPTOR_AND_PLANNED_OBSERVATION_PATH"),
    }, dependencies=["RETAINED_PRODUCER_CODE_V1", "RETAINED_OPAQUE_BYTES_V1"],
        rule="Capture trusted source values; actual retained raw conforms to expected_value grammar, with no synthetic success field. Exact descriptor, path, source and producer required.")

    add("EXECUTION_COMMAND_JSON_V1", {
        "executable_ref": ref("raw_ref"),
        "arguments": {"type": "array", "items": ref("text"), "minItems": 0, "maxItems": 65536},
        "environment": array(object_schema({"name": ref("code"), "value": ref("text")})),
        "working_directory": object_schema({"source_manifest_ref": typed("source_manifest"),
                                              "directory_path": {"oneOf": [const(""), ref("source_path")]}}),
    }, dependencies=["RETAINED_OPAQUE_BYTES_V1"], raw=True,
        rule="Executable retained and separately installation-authorized; arguments preserve order; environment sorted unique name; working directory resolves exact prior source_manifest under the source path profile, empty path denotes its exact root, no PATH lookup. Independently resolve authorized directory membership and platform-safe containment without normalization, outside-view symlink following or drive-relative escape; unsupported platform paths reject execution.")

    # Environment/boundary contracts prescribe a positive exact allowlist.
    for name, fields, deps, rule in (
        ("FILESYSTEM_BOUNDARY_V2", {"allowed_roots": array(ref("path")), "symlink_policy": const("DENY_OUTSIDE_EXACT_VIEW"), "default_access": const("DENY")}, [],
         "Resolve only retained authorized view bytes; actual denied traversal probes required, profile declaration does not establish ENFORCED."),
        ("NETWORK_BOUNDARY_V2", {"allowed_endpoint_refs": array(ref("external_profile_ref")), "default_access": const("DENY")}, ["EXTERNAL_SERVICE_V2"],
         "Only exact separately authorized endpoints; actual network controls and probes required. Unwitnessed isolation UNKNOWN."),
        ("TOOL_BOUNDARY_V2", {"allowed_tool_refs": array(ref("external_profile_ref")), "default_access": const("DENY")}, ["EXECUTOR_TOOL_V2"],
         "Exact tool and transitive data-source closure; no undeclared plugin/tool authority."),
        ("MODEL_AGENT_BOUNDARY_V2", {"model_identity": ref("text"), "session_policy": const("FRESH_CONTEXT_PER_ASSIGNMENT"), "memory_policy": const("NO_PRIOR_CAMPAIGN_CONTEXT")}, [],
         "Observed fresh session/control witness required; declaration alone cannot establish isolation."),
        ("OS_ENVIRONMENT_V2", {"system_name": ref("text"), "system_version": ref("text"), "architecture": ref("text")}, [],
         "Observed environment equals pinned exact OS tuple; text is identity description, not proof of enforcement."),
        ("RUNTIME_ENVIRONMENT_V2", {"runtime_code_ref": ref("raw_ref"), "version": ref("text"), "dependency_plan_ref": ref("external_profile_ref")}, ["RETAINED_OPAQUE_BYTES_V1", "EXECUTION_DEPENDENCY_PLAN_V1"],
         "Retained actual runtime bytes/version and complete dependency plan match preregistration and actual execution."),
        ("BROWSER_ENVIRONMENT_V2", {"browser_code_ref": ref("raw_ref"), "version": ref("text"), "network_profile_ref": ref("external_profile_ref")}, ["RETAINED_OPAQUE_BYTES_V1", "NETWORK_BOUNDARY_V2"],
         "Exact captured browser installation and constrained network; unavailable browser does not silently select another version."),
        ("EXTERNAL_SERVICE_V2", {"service_identity": ref("text"), "endpoint": ref("text"), "version": ref("text"), "witness_profile_ref": ref("external_profile_ref")}, ["OBSERVATION_CAPTURE_V2"],
         "Endpoint is an exact installation allowlist entry, not caller authorization; service/version capture and availability are independently witnessed."),
        ("CLOCK_PROFILE_V1", {"clock_kind": enum("MONOTONIC OBSERVED_UNIX_US"), "unit": const("MICROSECONDS"), "authority": const("INFORMATIONAL_NOT_HISTORY_ORDER")}, [],
         "Observed time never substitutes for accepted history order; failed capture is null/unknown, never invented."),
        ("SANDBOX_PROFILE_V1", {"filesystem_boundary_ref": ref("external_profile_ref"), "network_boundary_ref": ref("external_profile_ref"), "tool_boundary_ref": ref("external_profile_ref"), "default_access": const("DENY")}, ["FILESYSTEM_BOUNDARY_V2", "NETWORK_BOUNDARY_V2", "TOOL_BOUNDARY_V2"],
         "All boundary controls must be enforced and witnessed independently; no conjunct may be replaced by declaration."),
        ("SEED_PROFILE_V1", {"seed": number(), "algorithm": const("EXACT_PREREGISTERED_SEED"), "replay_rule": const("SAME_EXACT_SEED_AND_INPUTS")}, [],
         "Seed is preregistered experiment input; deterministic replay additionally binds runner, source, environment and fixtures."),
    ):
        add(name, fields, dependencies=deps, rule=rule)

    add("EXECUTION_DEPENDENCY_PLAN_V1", {
        "dependencies": array(object_schema({"dependency_id": ref("code"), "raw_ref": ref("raw_ref")})),
        "command_spec_refs": array(ref("raw_ref")), "resolution": const("OFFLINE_EXACT_BYTES_ONLY"),
    }, dependencies=["EXECUTION_COMMAND_JSON_V1", "RETAINED_OPAQUE_BYTES_V1"],
        rule="Complete preregistered dependency set sorted unique ID and exact commands; durable readback before invocation; no latest/network substitution.")
    add("ENVIRONMENT_PROFILE_V2", {
        **{field: ref("external_profile_ref") for field in ("os_profile_ref", "runtime_profile_ref", "filesystem_profile_ref", "network_profile_ref", "clock_profile_ref", "sandbox_profile_ref")},
        "external_service_profile_refs": array(ref("external_profile_ref")),
    }, dependencies=["OS_ENVIRONMENT_V2", "RUNTIME_ENVIRONMENT_V2", "FILESYSTEM_BOUNDARY_V2", "NETWORK_BOUNDARY_V2", "CLOCK_PROFILE_V1", "SANDBOX_PROFILE_V1", "EXTERNAL_SERVICE_V2"],
        rule="Exact six environment components and all required services; observed EnvironmentRecord must agree field-for-field; no missing component is treated as equivalent.")
    for name, code_field, dependencies, rule in (
        ("EXECUTION_RUNNER_V2", "runner_code_ref", ["ENVIRONMENT_PROFILE_V2", "EXECUTION_DEPENDENCY_PLAN_V1", "TOOL_CAPTURE_V2"], "Select prior preregistered descriptor/experiment; invoke only exact authorized command; all actual effects captured, no future result backlink."),
        ("EXECUTION_HARNESS_V2", "harness_code_ref", ["ENVIRONMENT_PROFILE_V2", "OBSERVATION_CAPTURE_V2"], "Exact harness bytes, environment, control/oracle boundaries and capture paths preregistered; independently qualify harness and oracle."),
        ("EXECUTOR_TOOL_V2", "tool_code_ref", ["TOOL_CAPTURE_V2", "EXECUTION_DEPENDENCY_PLAN_V1"], "Exact retained executable and complete dependency/capture contract; possession of profile does not grant invocation."),
    ):
        add(name, {code_field: ref("raw_ref"), "dependency_profile_refs": array(ref("external_profile_ref")),
                   "context_selection": const("EXACT_PRIOR_DESCRIPTOR_EXPERIMENT")},
            dependencies=["RETAINED_PRODUCER_CODE_V1", *dependencies], rule=rule)
    add("EXECUTION_VARIANT_V2", {"variant_id": ref("code"), "implementation_raw_ref": ref("raw_ref"),
                                  "source_selection": const("EXACT_PRIOR_SOURCE_GENERATION")},
        dependencies=["RETAINED_OPAQUE_BYTES_V1"],
        rule="Exact declared variant implementation; source identity and applicability independently established; no version label equivalence.")
    add_control_profiles(add, contracts, defs, keys)
    return contracts


def add_control_profiles(add, contracts, defs, keys):
    """Explicitly selected policies; none is a caller-supplied expression bag."""
    def profiles():
        return array(ref("external_profile_ref"))

    def typed_set(kinds, minimum=0):
        return array({"allOf": [ref("typed_ref"), {"properties": {"kind": enum(kinds)}}]}, minimum)

    rules = {
        "PRINCIPAL_AUTHORIZATION_V1": ({"principal_id": ref("code"), "role": enum("OWNER COORDINATOR VALIDATOR EXECUTOR COLLECTOR ASSESSOR EXPORTER WITNESS"),
                                        "permitted_operations": array(enum("INITIALIZE ACCEPT TRANSITION INGEST EXECUTE ASSESS APPROVE EXPORT ANCHOR"), 1),
                                        "namespace_profile_ref": ref("external_profile_ref"),
                                        "permitted_approval_purposes": array(enum("COVERAGE_OBLIGATION_WAIVER SCOPE_EXCLUSION RESIDUAL_RISK_ACCEPTANCE DESTRUCTIVE_ACTION LIVE_ACTION CONTINUATION_BUDGET LIMITED_CONCLUSION")),
                                        "approval_request_selection": const("EXACT_AUTHENTICATED_ACTION_AND_SCOPE")}, ["BOOTSTRAP_NAMESPACE_V2"],
                                       "OD-026 successor wire PRINCIPAL_AUTHORIZATION_V2. Exact principal/role/operation/namespace must be independently installed under trust root and matched to authenticated runtime principal at durable boundary. APPROVE additionally requires explicit purpose membership and exact authenticated requested action/scope equality. Empty purpose set grants no approval authority; general APPROVE, role name, body pin/token/producer name never implies an authority class. No future campaign scope pins in installation; accepted request selects exact prior scope under namespace and governing policy."),
        "SOURCE_AUTHORITY_V1": ({"authority_id": ref("code"), "authority_mode": enum("AUTHORIZED_GIT AUTHORIZED_SNAPSHOT"),
                                "repository_or_snapshot_identity": ref("text"), "authorizing_principal_ref": ref("external_profile_ref")}, ["PRINCIPAL_AUTHORIZATION_V1"],
                               "Only independently installation-authorized repository/snapshot identity can establish SourceIdentity; importing a manifest or path cannot self-authorize."),
        "SOURCE_IDENTITY_V2": ({"authority_profile_refs": profiles(), "surface_key_profile_refs": profiles(), "identity_algorithm": const("EXACT_MANIFEST_AND_AUTHORIZED_REPOSITORY_OR_SNAPSHOT"),
                               "path_profile_ref": ref("external_profile_ref"), "manifest_entry_profile_ref": ref("external_profile_ref"),
                               "authority_parameters": array(object_schema({"authority_ref": ref("external_profile_ref"),
                                   "authority_mode": enum("AUTHORIZED_GIT AUTHORIZED_SNAPSHOT"),
                                   "git_object_algorithm": enum("SHA1 SHA256 NONE")}), 1),
                               "submodule_policy": const("REQUIRE_EXACT_RESOLVED_MATERIALIZED_CONTENT"),
                               "lfs_policy": const("REQUIRE_EXACT_RESOLVED_MATERIALIZED_CONTENT"),
                               "symlink_policy": const("RETAIN_EXACT_TARGET_BYTES_NO_FOLLOW"),
                               "mode_policy": const("EXACT_RECONCILED_SOURCE_MODE"),
                               "incomplete_lfs_or_submodules": const("REJECT")}, ["SOURCE_AUTHORITY_V1", "SURFACE_KEY_PROFILE_V2", "SOURCE_PATH_PROFILE_V1", "SOURCE_MANIFEST_ENTRY_PROFILE_V1"],
                              "Retain complete exact source members, match authorized Git commit/tree or snapshot identity; validate every materialized member and all declared submodule/LFS content; names and hashes supplied in raw are assertions only."),
        "BOOTSTRAP_NAMESPACE_V2": ({"history_namespace_id": {"type": "string", "pattern": "^history_namespace_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"},
                                   "reuse": const("EMPTY_NAMESPACE_ONLY")}, [],
                                  "A new campaign initializes an empty separately authorized namespace. Existing namespace/history cannot become successor by installing a schema."),
        "BOOTSTRAP_ADMISSION_V2": ({"mode": const("EXACT_LEGACY_BYTES_OR_PROVED_NO_LEGACY"), "authority_mode": const("LOCAL_PINNED"),
                                   "historical_parser_profile_refs": profiles()}, ["LEGACY_SCHEMA_PIN_V2"],
                                  "Before genesis, exact preserved legacy bytes and current actual SourceGeneration are separate content inputs. Mechanical parsing, source equivalence and semantic admission require their complete independent predicates; absence requires proved empty legacy input, not fabricated history."),
        "TRUSTED_PREDECESSOR_PIN_V2": ({"predecessor_raw_ref": ref("raw_ref"), "predecessor_contract_profile_ref": ref("external_profile_ref"),
                                       "authorization_ref": ref("external_profile_ref")}, ["RETAINED_OPAQUE_BYTES_V1", "PRINCIPAL_AUTHORIZATION_V1", "LEGACY_SCHEMA_PIN_V2"],
                                      "Retain and independently authorize exact predecessor bytes with original contract. This pin neither reinterprets history nor creates prior accepted facts in the new campaign."),
        "LINEAGE_ADMISSION_V2": ({"selection": const("EXACT_AUTHORIZED_PREDECESSOR"), "branch_rule": const("ALL_CANDIDATES_DISCLOSED_EXPLICIT_SELECTION"),
                                 "predecessor_pin_profile_ref": ref("external_profile_ref")}, ["TRUSTED_PREDECESSOR_PIN_V2"],
                                "Select one exact authorized predecessor using all declared candidates and explicit accepted selection decision; conflicting/unverified lineage cannot be silently preferred by path/date/latest."),
        "EXACT_COMPATIBILITY_V2": ({"writer_revision": const("R5.4.2"), "writes": const("NEW_LEGALLY_INITIALIZED_CAMPAIGN_ONLY"),
                                   "historical_read": const("ORIGINAL_EXACT_CONTRACTS"), "aliases": const("FORBIDDEN"), "retroactive_authority": const("FORBIDDEN")}, [],
                                  "Historical exact schemas remain readers and forensic authority only for original campaigns; successor writer rejects old campaign before canonical mutation. No /1 conversion, fabricated binding or in-place upgrade."),
        "CHALLENGER_FRESHNESS_V2": ({"required_roles": const(["FALSE_NEGATIVE_HUNTER", "FALSE_POSITIVE_SKEPTIC"]),
                                   "candidate_change": const("RERUN_BOTH_AGAINST_EXACT_NEW_REVISION"), "scoped_reuse": const(False)}, [],
                                  "Both distinct required challenger roles reference the same exact accepted candidate revision, source and input cut. Any material candidate change invalidates reuse. Completed empty challenge is not inferred from absent results."),
        "MANDATORY_STAGE_SET_V2": ({"stage_spec_refs": typed_set("stage_spec", 1), "selection": const("ALL_POLICY_REQUIRED_STAGES")}, [],
                                  "Required exact StageSpecs are installation/prior-spec-selected complete set; caller cannot drop a stage, substitute a result for completion or include E6 without its independent trigger."),
        "MANDATORY_LANE_SLOT_V1": ({"slot_id": ref("code"), "lane_role": ref("code"), "result_slot_contract_refs": profiles(),
                                   "completion_contract_ref": ref("external_profile_ref")}, ["NF02_EXTERNAL_LANE_SLOT_V2", "LANE_COMPLETION_V1"],
                                    "OD-041: slot_id equals exact StageSpec.required_lane_slots member; StageRun pins completely and uniquely cover that set. lane_role equals exact LaneSpec.lane_key; result_slot_contract_refs equals LaneRun.required_result_slots full-ref set; completion_contract_ref equals LaneSpec.completion_predicate_ref. One eligible prior LaneCompletion for each required slot, with exact LaneRun/LaneSpec/StageRun/source/revision and prior cut; no reused completion/lane, aliases, omitted/duplicate/optional replacement or latest lookup. This slot binding never certifies full L7 result/completion eligibility."),
        "GATE_ELIGIBILITY_PROFILE_V1": ({"required_basis_kinds": array(enum(keys), 1), "unknown_behavior": const("BLOCKED"),
                                        "scope_selection": const("EXACT_CHECKPOINT_CONTEXT")}, [],
                                       "All original gate predicates remain conjunctive: current source, scope, knowledge, isolation, exact prior basis, required outputs and FSM eligibility. A kind list only constrains expected basis, never replaces semantic validation."),
        "TRANSITION_POLICY_V2": ({"governing_spec_selection": const("EXACT_ACCEPTED_SPEC_AT_INPUT_CUT"), "proposal_use": const("SINGLE_ACCEPTED_TRANSITION_AT_EXACT_PARENT"),
                                  "skip_states": const(False)}, [],
                                 "Use complete Data 14.1-14.2 and exact spec attempt tables; dedicated start/result/completion/finalization events enforce their guards. No generic transition bypass; stale parent rejects atomically."),
        "COVERAGE_OBLIGATION_POLICY_V2": ({"denominator": const("ALL_MATERIAL_APPLICABLE_INVENTORY_SUBJECTS"), "unknown_materiality": const("RETAIN_AS_REQUIRED"),
                                           "acceptance_contract_ref": ref("external_profile_ref"), "applicability_contract_ref": ref("external_profile_ref")}, ["OBLIGATION_ACCEPTANCE_V2", "OBLIGATION_APPLICABILITY_V2"],
                                          "Derive complete policy obligation key set from exact inventory, source, invariant, scenario and environment. Unknown/conflicted materiality or applicability cannot erase the denominator; exclusion needs separate authorized scoped decision."),
        "OBLIGATION_ACCEPTANCE_V2": ({"required_qualification": const("QUALIFIED"), "require_current_applicability": const(True),
                                     "require_all_controls": const(True), "require_oracle_independence": const(True)}, ["ORACLE_INDEPENDENCE_V2"],
                                    "Obligation covered iff every original exact technique/evidence/control/current applicability/independence predicate holds at selected cut. An accepted result's existence or producer-selected PASS does not prove coverage."),
        "OBLIGATION_APPLICABILITY_V2": ({"context_selection": const("EXACT_OBLIGATION_SOURCE_ENVIRONMENT_AND_CUT"),
                                        "scope_rule": const("EXACT_SCOPED_REFERENCE_MEMBERSHIP"), "unknown_behavior": const("UNKNOWN_NOT_INAPPLICABLE")}, [],
                                       "Applicable only for exact compatible source, scope, invariant, scenario and environment; prove policy inapplicability with separate authorized decision. Unsupported/stale inputs remain UNKNOWN/INVALIDATED, not N/A."),
        "ORACLE_INDEPENDENCE_V2": ({"required_dimensions": array(enum("PROCESS_INDEPENDENCE INSTANCE_INDEPENDENCE IMPLEMENTATION_INDEPENDENCE STORAGE_READ_PATH_INDEPENDENCE EXTERNAL_BOUNDARY_INDEPENDENCE ORACLE_INDEPENDENCE MODEL_AGENT_INDEPENDENCE HARNESS_INDEPENDENCE"), 1),
                                   "declaration_as_enforcement": const(False)}, [],
                                  "Every requested dimension needs prior applicable qualification and independently observed paths; shared producer/storage/model/harness must be disclosed. Unknown witness cannot become INDEPENDENT/ENFORCED."),
        "QUALIFIED_TECHNIQUE_V2": ({"method_contract_ref": ref("external_profile_ref"), "required_control_experiment_refs": typed_set("experiment_spec"),
                                   "context_selection": const("EXACT_OBLIGATION_CONTEXT")}, ["METHOD_QUALIFICATION_V1"],
                                  "Exact method capability and all controls independently qualified for this obligation/source/environment. Name similarity or one success gives no technique qualification."),
        "KNOWLEDGE_POLICY_V2": ({"allowed_corpus_roles": array(enum("CANONICAL_DIRECT_PREDECESSOR AUXILIARY_SAME_STAGE CUMULATIVE_HISTORY CLAIM_QUARANTINE_VIEW EXTERNAL_HOLDOUT CALIBRATION INFORMATIONAL")),
                                "forbidden_corpus_roles": array(enum("CANONICAL_DIRECT_PREDECESSOR AUXILIARY_SAME_STAGE CUMULATIVE_HISTORY CLAIM_QUARANTINE_VIEW EXTERNAL_HOLDOUT CALIBRATION INFORMATIONAL")),
                                "exposure_rule": const("ACCEPTED_GRANT_IS_POTENTIAL_EXPOSURE"), "transitive_resolver_rule": const("VIEW_LOCAL_ONLY")}, [],
                               "Allowed/forbidden roles must agree exact StageSpec and be disjoint; derive all prior potential/actual exposures, grants and member closure. Missing channel witness stays UNKNOWN. Caller-selected allowlist cannot waive original blind-origin/contamination rules."),
        "CAPABILITY_BOUNDARY_V2": ({"permitted_operations": array(enum("READ_VIEW DOWNLOAD_VIEW RESOLVE_VIEW_LOCAL")), "scope": const("EXACT_ACCEPTED_GRANT_AND_VIEW"),
                                  "secret_in_canonical_body": const(False)}, ["KNOWLEDGE_POLICY_V2"],
                                 "Unserialized runtime capability only enforces authenticated access to exact accepted grant/view. Possession or a matching digest cannot mint canonical producer authority; revoke terminal/stale context before external access."),
        "POSITIVE_VIEW_PROJECTION_V2": ({"membership": const("EXACT_ACCEPTED_ALLOWED_RAW_REFS"), "metadata": const("EMPTY_CLOSED_OBJECT"),
                                       "transitive_access": const("DENY_OUTSIDE_VIEW")}, ["RETAINED_OPAQUE_BYTES_V1", "KNOWLEDGE_POLICY_V2"],
                                      "Deliver only retained bytes of all and only accepted allowed member RawRefs. Empty metadata still undergoes knowledge preflight; no workspace replacement or resolver escape."),
        "PUBLIC_REDACTION_V2": ({"projection": const("EXACT_VIEW_MEMBERS_ONLY"), "metadata": const("EMPTY_CLOSED_OBJECT"),
                               "assurance_rewrite": const("FORBIDDEN")}, ["POSITIVE_VIEW_PROJECTION_V2"],
                              "Redaction cannot delete required canonical risk/blocker/status disclosure in a public conclusion/report. View delivery omits only explicitly forbidden content under prior policy; no assurance upgrade."),
        "DELIVERY_RETRY_V2": ({"retry": const("SAME_ACCEPTED_AUTHORIZATION_AND_RETAINED_BYTES"), "revalidate": const("EVERY_EXTERNAL_ACCESS")}, ["NF02_DELIVERY_AUTHORIZATION_V1"],
                              "Each retry revalidates current legal terminal/source/FSM context and exact binding/start. A changed package/recipient/context needs a new legal authorization, never replacement binding."),
        "DELIVERY_IDEMPOTENCY_V2": ({"key": const("EXACT_ASSIGNMENT_BINDING_AND_RECIPIENT"), "accepted_retry": const("ORIGINAL_ACCEPTED_FACT"),
                                    "different_bytes": const("REJECT")}, ["NF02_DELIVERY_AUTHORIZATION_V1"],
                                   "Same exact operation returns original authority; competing binding/result/source/slot rejects under CAS without mutation. External delivery retry never fabricates a second accepted fact."),
        "EXPLORATION_POLICY_V2": ({"planning_modes": array(enum("PREREGISTERED EXPLORATORY LEGACY_IMPORTED"), 1),
                                  "confirmation": const("SEPARATE_CURRENT_QUALIFIED_EVIDENCE"), "method_contract_refs": profiles()}, ["METHOD_QUALIFICATION_V1", "DISCOVERY_CONFIRMATION_V1"],
                                 "Exploratory discovery does not self-qualify evidence or establish novelty; exact preregistered/control/confirmation and knowledge predicates remain independently required."),
        "SOURCE_DRIFT_POLICY_V2": ({"comparison": const("EXACT_ACCEPTED_MANIFEST_DIFF"), "qualification_reuse": const("INDEPENDENT_CURRENT_APPLICABILITY_PROOF_ONLY"),
                                   "history_reinterpretation": const(False)}, ["SOURCE_IDENTITY_V2"],
                                  "Recompute full added/removed/modified/type-changed member diff and complete affected qualifications/obligations; any unproved reuse remains invalidated/unknown. A source label or unchanged HEAD does not prove unchanged bytes."),
        "SOURCE_RECONCILIATION_V2": ({"identity_profile_ref": ref("external_profile_ref"), "raw_identifier_profile_ref": ref("external_profile_ref"),
                                    "equality": const("EXACT_MATERIALIZED_SOURCE_BYTES")}, ["SOURCE_IDENTITY_V2", "LEGACY_SCHEMA_PIN_V2"],
                                   "Read all original identity assertions with exact pinned extraction paths and compare actual retained source bytes plus independent authority. Asserted Git/digest/archive names cannot establish equivalence."),
    }
    for name, (fields, dependencies, rule) in rules.items():
        add(name, fields, dependencies=dependencies, rule=rule)
    contracts["SOURCE_IDENTITY_V2"]["wire_profile_id"] = "SOURCE_IDENTITY_V3"
    contracts["SOURCE_IDENTITY_V2"]["grammar"]["properties"]["profile_id"] = const("SOURCE_IDENTITY_V3")
    parameters = contracts["SOURCE_IDENTITY_V2"]["grammar"]["properties"]["authority_parameters"]["items"]
    parameters["allOf"] = [{"if": {"properties": {"authority_mode": const("AUTHORIZED_GIT")}},
                            "then": {"properties": {"git_object_algorithm": enum("SHA1 SHA256")}},
                            "else": {"properties": {"git_object_algorithm": const("NONE")}}}]
    contracts["SOURCE_IDENTITY_V2"]["rule"] += (
        " OD-029: exactly one authority_parameters row per complete authority_profile_ref, sorted by exact ref identity; "
        "duplicates, extra/missing authority and mode mismatch reject. Git algorithm is selected by that exact independently "
        "authorized context, never inferred from caller IDs. Snapshot selects NONE. Resolve exact path/entry profiles; "
        "submodule/LFS required content, symlink original target bytes and modes are independently reconciled. "
        "Unsupported paths or unresolved source facts block completeness, never silently omit members.")
    from common_grammars import SOURCE_PATH_SHAPE
    add("SOURCE_PATH_PROFILE_V1", {"path_shape": const(SOURCE_PATH_SHAPE),
                                  "component_rule": const("NO_EMPTY_DOT_DOTDOT_COMPONENTS"),
                                  "separator": const("POSIX_SLASH"), "ordering": const("UTF8_BYTE_LEXICOGRAPHIC"),
                                  "duplicates": const("REJECT_CANONICAL_PATH_ALIAS"), "unsupported": const("REJECT_NO_OMISSION")},
        rule="OD-030 exact successor source-manifest path shape with original Unicode/dot-prefixed names and component semantics. No backslash/NUL/traversal/empty component or duplicate canonical path. No normalization that changes original source identity; unsupported path rejects completeness, never omission.")
    add("SOURCE_MANIFEST_ENTRY_PROFILE_V1", {"source_manifest_schema_raw_ref": ref("raw_ref"),
                                            "schema_key": const("source_manifest/2"),
                                            "entry_selection": const("EXACT_BOUND_SCHEMA_ENTRIES_ITEM"),
                                            "member_readback": const("ALL_DECLARED_SOURCE_MEMBERS_EXACT_BYTES_AND_TYPE_FACTS")},
        dependencies=["BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1"],
        rule="Retain and hash exact independently qualified source_manifest/2 schema bytes; require equality to bound schema and use its entries item. All actual members/types/modes/bytes reconciled under source authority; matching caller raw hash or entry schema alone is not source completeness.")
    add("SURFACE_KEY_PROFILE_V2", {
        "canonical_surface_category": ref("code"), "language": ref("code"), "runtime_class": ref("code"),
        "anchor_kind": enum("STATIC RUNTIME"), "normalizer_code_ref": ref("raw_ref"),
        "category_meaning": ref("text"), "source_selection": const("EXACT_SOURCE_IDENTITY_MANIFEST_AND_RAW_MEMBERS"),
        "ambiguity": const("PROVISIONAL_NO_MERGE"),
    }, dependencies=["RETAINED_PRODUCER_CODE_V1"],
        rule="Exact installed category/language/runtime profile uniquely selected from SourceIdentity's pinned profile list. Normalizer is retained authorized deterministic code with closed STATIC/RUNTIME output grammar. Recompute original byte offsets/source anchors from retained source; no mtime, transformed line number or collector-local ID. Conflicting tuple/meaning/normalization blocks STABLE identity. Unsupported or ambiguous normalization remains PROVISIONAL and unresolved inventory. Changed normalizer/meaning requires new profile/source context, never historical key reinterpretation.")

    add("STRICT_JSON_CAPTURE_V1", {"encoding": const("UTF8_STRICT"), "duplicate_keys": const("REJECT"),
                                  "floats": const("REJECT"), "lone_surrogates": const("REJECT"),
                                  "max_bytes": number(1, 67108864), "max_depth": number(1, 128)},
        rule="Read all exact bytes; no BOM, trailing data, duplicate keys, floats/nonfinite values, bool-as-integer or unpaired surrogate; safe integers only, finite closed selected schema. Quota violations reject without truncated evidence.")
    for name in ("RETAINED_OPAQUE_BYTES_V1", "RETAINED_PRODUCER_CODE_V1", "FIXTURE_INPUT_V1", "LEGACY_OBSERVATION_RAW_V1"):
        add(name, {"max_bytes": number(1, 134217728), "interpretation": const("EXACT_OPAQUE_BYTES_NO_ASSURANCE")},
            rule="Verify RawDigest and length, durable immutable readback and retention. Profile carries no truth/producer/acceptance authority; fixture/code/legacy meaning only from separate authorized exact consumer contract.")
    add("BDB_CJSON_1", {"canonical_profile": const("BDB-CJSON-1"), "object_digest_profile": const("BDB-OBJECT-DIGEST-1"),
                        "adr_raw_digest": const(digest(BASE / "candidate/ADR-006_CANONICAL_SERIALIZATION_AND_IDENTITY_PROFILE.md"))},
        rule="Exact unchanged ADR algorithm and integer/Unicode/key serialization; RawDigest is SHA256 exact bytes, ObjectDigest has exact wire kind/version domain. No profile self-hash or digest interchange.")
    inherited_schema_profile = read(BASE / "candidate/profiles/BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1.json")
    add("BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1", {k: const(v) for k, v in inherited_schema_profile.items() if k != "profile_id"},
        rule="Unchanged qualified executable-schema raw profile; exact offline schema RawDigest and dialect; any unbound bytes reject.",
        semantic_review="EXACT_INHERITED_PROFILE_BODY")
    contracts["BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1"]["inherited_exact_file"] = "profiles/BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1.json"

    # Inherited transport and normalizer algorithms have exact separate profiles.
    for name, filename, dependencies in (
        ("NF02_PACKAGE_TRANSPORT_V2", "NF02_INPUT_PACKAGE_TRANSPORT_V2", []),
        ("NF02_RESULT_TRANSPORT_V2", "NF02_RESULT_TRANSPORT_V2", []),
        ("NF02_RESULT_NORMALIZER_V2", "NF02_RESULT_NORMALIZER_V2", ["NF02_RESULT_TRANSPORT_V2"]),
        ("NF02_PACKAGE_SEMANTIC_PROFILE_V1", "NF02_PACKAGE_SEMANTIC_PROFILE_V1", ["BDB_CJSON_1", "NF02_PACKAGE_TRANSPORT_V2"]),
    ):
        body = read(BASE / "candidate/profiles" / (filename + ".json"))
        # Analysis name -> actual wire ID is explicit, not an acceptance alias.
        add(name, {k: const(v) for k, v in body.items() if k != "profile_id"}, dependencies=dependencies,
            rule="Exact unchanged inherited algorithm and transport limits; analysis label resolved to actual installed wire ID, not runtime fallback.",
            semantic_review="EXACT_INHERITED_PROFILE_BODY")
        contracts[name]["grammar"]["properties"]["profile_id"] = const(body["profile_id"])
        contracts[name]["inherited_exact_file"] = "profiles/" + filename + ".json"
        contracts[name]["wire_profile_id"] = body["profile_id"]

    result_key = next(k for k in keys if "::bdb_audit_lane_result/" in k)
    add("NF02_EXTERNAL_LANE_SLOT_V2", {"result_schema_key": const(result_key), "normalizer_ref": ref("external_profile_ref"),
                                      "transport_ref": ref("external_profile_ref"), "uniqueness": const("ONE_EXACT_ASSIGNMENT_AND_SLOT"),
                                      "empty_findings": const("NO_AUTOMATIC_ASSURANCE_PASS")},
        dependencies=["NF02_RESULT_NORMALIZER_V2", "NF02_RESULT_TRANSPORT_V2"],
        rule="Successor wire ID NF02_EXTERNAL_LANE_SLOT_V3 because exact result kind/version changed; all claims bind prior assignment/binding/attempt/source/slot; terminal retry only original exact accepted bytes.")
    contracts["NF02_EXTERNAL_LANE_SLOT_V2"]["wire_profile_id"] = "NF02_EXTERNAL_LANE_SLOT_V3"
    contracts["NF02_EXTERNAL_LANE_SLOT_V2"]["grammar"]["properties"]["profile_id"] = const("NF02_EXTERNAL_LANE_SLOT_V3")
    add("NF02_PROTOCOL_PROFILE_V2", {"foundation_revision": const("R5.4.2"),
                                    **{f: ref("external_profile_ref") for f in ("input_transport_ref", "result_transport_ref", "normalizer_ref", "result_slot_ref", "package_semantic_profile_ref")},
                                    "binding_before_start_and_delivery": const(True), "capability": const("RUNTIME_ONLY_NOT_CANONICAL_AUTHORITY")},
        dependencies=["NF02_PACKAGE_TRANSPORT_V2", "NF02_RESULT_TRANSPORT_V2", "NF02_RESULT_NORMALIZER_V2", "NF02_EXTERNAL_LANE_SLOT_V2", "NF02_PACKAGE_SEMANTIC_PROFILE_V1"],
        rule="Successor wire NF02_PROTOCOL_PROFILE_V3; complete exact profile bundle, independent of future installation/SchemaRegistry/spec digests; raw and object authority remain distinct.")
    contracts["NF02_PROTOCOL_PROFILE_V2"]["wire_profile_id"] = "NF02_PROTOCOL_PROFILE_V3"
    contracts["NF02_PROTOCOL_PROFILE_V2"]["grammar"]["properties"]["profile_id"] = const("NF02_PROTOCOL_PROFILE_V3")

    purpose_catalog = read(OUT / "design/PURPOSE_CONTRACT_GRAMMARS.json")
    purposes = list(purpose_catalog)
    method_values = purpose_catalog["METHOD"]["parameter_schema"]["properties"]["parameters"]["properties"]["method_type"]["enum"]
    assessor_values = purpose_catalog["ASSESSOR"]["parameter_schema"]["properties"]["parameters"]["properties"]["assessment_kind_version"]["enum"]
    shared_context = {
        "governing_spec_ref": typed("spec_revision"), "input_kind_versions": array(enum(keys)),
        "predicate_contract_ref": ref("external_profile_ref"), "required_witness_kinds": array(enum(keys)),
        "enum_values": array(ref("code")), "resource_bounds": array(object_schema({
            "resource": enum("CPU_TIME_US WALL_TIME_US MEMORY_BYTES OUTPUT_BYTES FILE_COUNT"), "limit": number()})),
    }
    from purpose_input_domains import context_domains
    variants = [(p, {"kind": "DEFAULT"}) for p in purposes if p not in ("METHOD", "ASSESSOR")]
    variants.extend(("METHOD", {"kind": "METHOD", "method_type": value}) for value in method_values)
    variants.extend(("ASSESSOR", {"kind": "ASSESSOR", "assessment_kind_version": value}) for value in assessor_values)
    context_entries = {"oneOf": []}
    for purpose, variant in variants:
        selected = context_domains(purpose, purpose_catalog[purpose], variant, keys)
        fields = {**shared_context, **{field: const(value) for field, value in selected.items()}}
        context_entries["oneOf"].append(object_schema({"purpose": const(purpose), "variant": const(variant), **fields}))
    add("FULL_PATH_CONTEXT_PARAMETERS_V1", {"entries": array(context_entries, 32)},
        dependencies=[c.get("analysis_profile_key", c["algorithm_id"]) for c in purpose_catalog.values()],
        rule="Successor wire FULL_PATH_CONTEXT_PARAMETERS_V2, OD036/037/038. Exactly one sorted unique dispatch row per exact governing spec/purpose/variant; complete 14 DEFAULT, 14 METHOD and four ASSESSOR variants per governing SpecRevision. Derive METHOD variant from the exact prior subject ExperimentSpec method_type and ASSESSOR variant from the actual registered assessment kind/version; no caller selector. Selected exact predicate parameters must equal that variant, with complete purpose input/witness/output/resource domains and mandatory prerequisites. Each governing_spec_ref is a field-specific PINNED_INSTALLATION_REF equal to the independently qualified exact initial_transition_profile_ref before empty-history initialization. At consumption require exact applicable governing spec. No fabricated pre-genesis acceptance, generic predicate or untyped expression.")
    contracts["FULL_PATH_CONTEXT_PARAMETERS_V1"]["wire_profile_id"] = "FULL_PATH_CONTEXT_PARAMETERS_V2"
    contracts["FULL_PATH_CONTEXT_PARAMETERS_V1"]["grammar"]["properties"]["profile_id"] = const("FULL_PATH_CONTEXT_PARAMETERS_V2")
    # Analysis labels select the successor wire contract, never runtime aliases.
    principal = contracts["PRINCIPAL_AUTHORIZATION_V1"]
    principal["wire_profile_id"] = "PRINCIPAL_AUTHORIZATION_V2"
    principal["grammar"]["properties"]["profile_id"] = const("PRINCIPAL_AUTHORIZATION_V2")
    add_finalization_profiles(add, defs, keys)
    from transition_contract import add_contract
    add_contract(add)
    from auxiliary_profile_contracts import add_contracts
    add_contracts(add)


def add_finalization_profiles(add, defs, keys):
    def target(kinds):
        return {"allOf": [ref("typed_ref"), {"properties": {"kind": enum(kinds)}}]}

    def profiles(minimum=0):
        return array(ref("external_profile_ref"), minimum)

    def sequence(item):
        return {"type": "array", "items": item, "minItems": 0, "maxItems": 65536}

    add("MODEL_ARTIFACT_V1", {
        "variables": array(object_schema({"name": ref("code"), "domain": array(ref("model_value"), 1)}), 1),
        "initial_states": array(ref("model_state"), 1), "transitions": array(object_schema({
            "transition_id": ref("code"), "from_state": ref("model_state"), "to_state": ref("model_state"),
            "source_anchors": array(ref("source_anchor"), 1)})),
        "forbidden_states": array(ref("model_state")), "abstraction_assumptions": sequence(ref("text")),
        "bounds": object_schema({"max_states": number(1, 65536), "max_transitions": number(0, 65536), "max_path_steps": number(1, 65536)}),
        "omitted_states": array(ref("model_state")), "fairness_assumptions": sequence(ref("text")), "time_assumptions": sequence(ref("text")),
    }, raw=True, rule="Exact finite declared state product <=65536, at most256 named variables, typed domain equality true!=1, explicit transitions only. Full bounded reachability and mapping/fidelity predicates remain separate; truncation never qualifies implementation.")
    add("IMPLEMENTATION_MAPPING_V1", {
        "source_generation_ref": target("source_generation"),
        "variable_mappings": array(object_schema({"name": ref("code"), "source_anchors": array(ref("source_anchor"), 1)}), 1),
        "transition_mappings": array(object_schema({"transition_id": ref("code"), "source_anchors": array(ref("source_anchor"), 1)})),
    }, raw=True, dependencies=["SOURCE_IDENTITY_V2", "MODEL_ARTIFACT_V1"],
        rule="Exactly one mapping per declared variable/transition, no unknown or duplicate symbols; complete prior manifest anchors and exact source match. Correspondence is not an equivalence/fidelity verdict.")
    add("CALIBRATION_GROUND_TRUTH_PROFILE_V1", {
        "ground_truth_raw_ref": ref("raw_ref"), "authorizing_principal_ref": ref("external_profile_ref"),
        "independence_contract_ref": ref("external_profile_ref"), "scope_selection": const("EXACT_DEFECT_OR_NEGATIVE_OPPORTUNITY_UNIT"),
    }, dependencies=["RETAINED_OPAQUE_BYTES_V1", "PRINCIPAL_AUTHORIZATION_V1", "ORACLE_INDEPENDENCE_V2"],
        rule="Retained prior independently authorized ground truth for exact unit/scope. Auditor output, majority, proposed match digest or self-created assessor pin cannot establish truth; every known bug/negative expectation independently qualified.")
    add("COMPATIBILITY_FIXTURE_V2", {"fixture_input_ref": ref("raw_ref"), "independent_expected_ref": ref("raw_ref"),
                                     "ground_truth_profile_ref": ref("external_profile_ref"),
                                     "legacy_contract_ref": ref("external_profile_ref"), "current_contract_ref": ref("external_profile_ref")},
        dependencies=["FIXTURE_INPUT_V1", "CALIBRATION_GROUND_TRUTH_PROFILE_V1", "LEGACY_SCHEMA_PIN_V2", "EXACT_COMPATIBILITY_V2"],
        rule="Exact fixture and independently established expected current correctness plus original legacy expectation. Retain both observations/error families; known legacy bugs do not become current correctness oracle.")
    add("COMPATIBILITY_GATE_V2", {"required_fixture_contract_refs": profiles(1), "qualification": const("ALL_DENOMINATOR_FIXTURES_QUALIFIED"),
                                  "preservation_axis": const("EXACT_LEGACY_OBSERVATION"), "correctness_axis": const("INDEPENDENT_EXPECTATION")},
        dependencies=["COMPATIBILITY_FIXTURE_V2"],
        rule="Complete required denominator; PASS only all applicable fixture qualifications and independent current correctness pass, preserving original observations separately. Missing/unqualified fixtures block, never disappear from counts.")

    extraction = object_schema({"field": enum("VARIANT STAGE ARCHIVE_NAME DECLARED_GIT_COMMIT DECLARED_GIT_TREE DECLARED_SOURCE_ID DECLARED_MANIFEST_RAW_DIGEST"),
                                "pointer": defs["observable_selector"]["oneOf"][0]["properties"]["pointer"]})
    add("LEGACY_SCHEMA_PIN_V2", {"original_schema_raw_ref": ref("raw_ref"), "original_parser_code_ref": ref("raw_ref"),
                                "extraction_paths": array(extraction), "variant_values": array(ref("text")), "stage_values": array(ref("text"))},
        dependencies=["BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1", "RETAINED_PRODUCER_CODE_V1"],
        rule="Exact original legacy schema/parser and finite source fields; strict pointer extraction, null only where absent legally. All original bytes preserved; unrecognized/nonconforming historical input forensic only, never current authority.")
    add("LEGACY_MECHANICAL_VALIDATION_V2", {"legacy_schema_pin_ref": ref("external_profile_ref"), "parser_selection": const("EXACT_ORIGINAL_PARSER"),
                                          "current_promotion": const("FORBIDDEN_WITHOUT_SEPARATE_ADMISSION")},
        dependencies=["LEGACY_SCHEMA_PIN_V2"],
        rule="Independently reread exact legacy raw, validate original grammar, extract exactly variant/stage or null. Mechanical VALID does not establish provenance, source equivalence or NF02 authority.")
    add("LEGACY_OBSERVATION_MAPPING_V2", {"legacy_schema_pin_ref": ref("external_profile_ref"), "locator_grammar": const("EXACT_RAW_ROOT_OR_ZIP_MEMBER_RFC6901"),
                                         "current_observation_contract_ref": ref("external_profile_ref")},
        dependencies=["LEGACY_SCHEMA_PIN_V2", "OBSERVATION_CAPTURE_V2", "LEGACY_OBSERVATION_RAW_V1"],
        rule="Exact retained raw locator and independently verified complete semantic equality for declared scope only; no fabricated capture chronology, producer or missing context.")
    add("LEGACY_EXPOSURE_RECONSTRUCTION_V2", {"legacy_mapping_profile_ref": ref("external_profile_ref"), "missing_witness": const("UNKNOWN"),
                                             "potential_exposure_rule": const("ALL_RECONSTRUCTABLE_PRIOR_DELIVERY_PATHS")},
        dependencies=["LEGACY_OBSERVATION_MAPPING_V2", "KNOWLEDGE_POLICY_V2"],
        rule="Enumerate all evidenced historical delivery/access paths; incomplete reconstruction remains unknown/possibly contaminated, never establishes clean blind origin.")

    add("SNAPSHOT_PROJECTION_V2", {"purpose": enum("STOP_INPUT COVERAGE_SUMMARY CHANNEL_INVENTORY RUN_STATE"),
                                  "selection": const("COMPLETE_MATERIAL_CLOSURE_OF_EXACT_INPUT_REFS_AT_CUT"), "projection_code_ref": ref("raw_ref")},
        dependencies=["RETAINED_PRODUCER_CODE_V1", "TRANSITION_POLICY_V2"],
        rule="Independently replay exact accepted input/event closure at represented head and compare complete ClosedPurposePayload. Snapshot never replaces history, omits blockers or invents state/enforcement.")
    add("SNAPSHOT_EXPORT_V2", {"snapshot_ref": target("snapshot"), "payload": ref("closed_purpose_payload")}, raw=True,
        dependencies=["SNAPSHOT_PROJECTION_V2"],
        rule="Retain exact canonical JSON projection and independently equal accepted snapshot/purpose/cut. No future export receipt or own raw digest in payload.")
    add("FINAL_TECHNICAL_REPORT_JSON_V1", {"binding": ref("report_binding"), "machine_objects": array(ref("report_object"), 1)}, raw=True,
        dependencies=["BDB_CJSON_1"],
        rule="Complete material typed closure of prior exact report binding, sorted exact refs; each body independently matches retained canonical object and exact qualified schema, all risks/statuses/limits disclosed. Bytes BDB-CJSON-1(payload)+LF.")
    add("FINAL_TECHNICAL_REPORT_TEXT_V1", {"json_report_profile_ref": ref("external_profile_ref"), "rendering": const("CANONICAL_JSON_WITH_FIXED_LABELS_AND_ESCAPING"),
                                          "new_narrative": const("FORBIDDEN")},
        dependencies=["FINAL_TECHNICAL_REPORT_JSON_V1"],
        rule="Exact UTF8 text is literal BDB AUDIT TECHNICAL REPORT + LF followed by canonical machine JSON + LF; no caller prose or hidden status transformation. It communicates the same full chain and no new assurance.")
    # The public payload is a deterministic projection, not a second conclusion.
    public = {
        "campaign_ref": target("campaign_genesis"), "source_generation_ref": target("source_generation"),
        "conclusion_ref": target("campaign_conclusion"), "stop_evaluation_ref": target("stop_evaluation"),
        "scope_inventory_ref": {"oneOf": [target("inventory_revision"), {"type": "null"}]},
        "termination_state": enum("COMPLETED COMPLETED_LIMITED"),
        "assurance_level": enum("ADEQUATE_FOR_DECLARED_SCOPE BOUNDED INSUFFICIENT"),
        "continuation_decision": enum("PASS CONTINUE_REQUIRED E6_REQUIRED BLOCKED"),
        "stop_release_assessment": enum("READY READY_WITH_RESIDUAL_RISK TECHNICALLY_NOT_READY QUALIFICATION_BLOCKED"),
        "residual_risks": array(object_schema({"risk_ref": target("residual_risk"), "description": ref("text"), "reason_unresolved": ref("text"),
                                               "disposition": ref("code"), "materiality": enum("MATERIAL NON_MATERIAL UNKNOWN CONFLICTED")})),
        "limited_basis_refs": array(ref("typed_ref")), "bounded_statement": ref("text"),
    }
    public["residual_risks"]["items"]["properties"]["disposition"] = enum("OPEN BOUNDED ACCEPTED_RESIDUAL_RISK BLOCKED UNKNOWN SUPERSEDED")
    add("PUBLIC_CONCLUSION_RENDER_V1", public, raw=True, dependencies=["BDB_CJSON_1"],
        rule="Raw bytes exactly BDB-CJSON-1(Render(prior accepted Conclusion->STOP->StopInput closure))+LF. All values copied from exact accepted sources; all applicable material/unknown risk entries included, full risk disposition enum constrained by risk schema. No future FinalCase/release ref. Null inventory only legal early limited conclusion. STOP release axis is an assessment, never release authorization. Limited/nonPASS cannot imply full PASS/READY.")

    add("BUNDLE_MEMBERSHIP_V2", {"bundle_type": enum("REPORT REPLAY RECOVERY STANDALONE"), "member_contract_refs": profiles(1),
                                "selection": const("COMPLETE_ROOT_OBJECT_RAW_SCHEMA_PROFILE_CLOSURE"),
                                "metadata_exclusions": const(["BUNDLE_MANIFEST.json", "ARTIFACT_HASHES.sha256"])},
        dependencies=["FINAL_TECHNICAL_REPORT_JSON_V1", "EXACT_DURABLE_RECOVERY_V1", "BUILD_RECIPE_V2", "HASH_MANIFEST_V2"],
        rule="Exact bundle type selects required root set: REPORT final chain/report, REPLAY exact intent/result/claim/invariant+observations, RECOVERY complete commit/object/raw/installed roots, STANDALONE build input/payload/qualified resources+final output. Independently complete closure, deterministic names objects/kind/digest.json, raw/digest, profiles/digest.json, schemas/digest.json; raw unchanged. ZIP raw digest outside metadata, no self-hash.")
    add("HASH_MANIFEST_V2", {"line_format": const("LOWERCASE_SHA256_TWO_SPACES_POSIX_PATH_LF"), "ordering": const("UTF8_PATH"),
                            "excluded_metadata": const(["BUNDLE_MANIFEST.json", "ARTIFACT_HASHES.sha256"])},
        dependencies=["RETAINED_OPAQUE_BYTES_V1"],
        rule="Actual retained hash file contains every authority-bearing member exact raw digest/path, sorted unique safe paths; exclude only own hash-list and embedded manifest metadata. External accepted BundleManifest verifies complete membership. No checksum substitutes for ZIP RawDigest.")
    add("SOURCE_ARCHIVE_V2", {"manifest_selection": const("EXACT_SOURCE_GENERATION_CONTENT_OR_PRIOR_MANIFEST"), "transport_profile_ref": ref("external_profile_ref"),
                             "all_members": const(True)}, dependencies=["SOURCE_ZIP_TRANSPORT_V1", "SOURCE_IDENTITY_V2"],
        rule="OD-031 exact source archive contains all and only actual exact source manifest material members plus declared parent-directory transport entries. The manifest is selected from SourceGeneration's complete exact ref; verified same-commit content is legal only where that ref class permits. Independently compare expanded original bytes/type/modes and complete LFS/submodules. No archive name, caller hash, member mode or same-commit object establishes source authority.")
    add("SOURCE_ZIP_TRANSPORT_V1", {"container": const("ZIP"), "path_profile_ref": ref("external_profile_ref"),
                                    "manifest_entry_profile_ref": ref("external_profile_ref"),
                                    "parser_code_ref": ref("raw_ref"), "parser_dependency_code_refs": array(ref("raw_ref"), 1),
                                    "parser_entrypoint": const("bdb_audit.source.archive.read_complete_source_archive"),
                                    "supported_entry_types": const(["REGULAR_FILE", "SYMLINK"]),
                                    "unsupported_source_types": const("REJECT_NO_COMPLETE_SOURCE"),
                                    "source_manifest_key": const("source_manifest/2"),
                                    "max_raw_bytes": number(1, 67108864), "max_expanded_bytes": number(1, 67108864),
                                    "max_central_bytes": number(1, 8388608), "max_member_bytes": number(1, 67108864),
                                    "max_ratio": number(1, 1000),
                                    "max_entries": number(1, 65536),
                                    "directory_entries": const("EXACT_DECLARED_MEMBER_PARENT_DIRECTORIES_ONLY"),
                                    "symlink_handling": const("READ_TARGET_BYTES_NO_FILESYSTEM_FOLLOW"),
                                    "encryption_duplicates_aliases": const("REJECT"),
                                    "member_validation": const("EXACT_MANIFEST_NAME_TYPE_MODE_LENGTH_RAW_DIGEST")},
        dependencies=["SOURCE_PATH_PROFILE_V1", "SOURCE_MANIFEST_ENTRY_PROFILE_V1", "RETAINED_PRODUCER_CODE_V1"],
        rule="Separate source representation transport; NF02 package transport remains unchanged. Strict ZIP complete retained bytes with central/local/name/length/CRC consistency and exact selected explicit quotas; reject encrypted/duplicate/NUL/alias/traversal/undeclared entries and malformed/trailing/unsupported container structures. No extraction follows symlinks; source type/mode/target are reconciled against independently verified source manifest/authority. Metadata directories have no source-fact authority. Unsupported transport rejects, never partial completeness. OD-033 independently retain exact parser entrypoint code and sorted unique complete transitive dependency code raw refs; current installed code and explicit Limits must match these pins. Path/entry profiles must equal SourceIdentity selection, not second schema authority. Only regular/symlink transport is supported here; unresolved or unsupported LFS/submodule/OTHER_ALLOWED rejects complete transport. Caller SourceMaterialization/completeness/hash equality is not trusted profile selection or canonical acceptance.")
    add("HANDOFF_TRANSPORT_V2", {"required_member_contract_refs": profiles(1), "transport_profile_ref": ref("external_profile_ref"),
                                "no_future_ref": const(True)}, dependencies=["NF02_PACKAGE_TRANSPORT_V2", "RETAINED_OPAQUE_BYTES_V1"],
        rule="Safe retained handoff ZIP complete exact declared required member/profile closure; receiving lane/context independently checked, no caller metadata establishes authority or allows cross-lane reuse.")
    add("HISTORY_ANCHOR_V2", {"witness_authority_ref": ref("external_profile_ref"), "anchor_mode": enum("LOCAL EXTERNAL_REQUIRED"),
                             "content": const("EXACT_ACCEPTED_HEAD_AND_COMPLETE_CHAIN_DIGEST")}, dependencies=["PRINCIPAL_AUTHORIZATION_V1"],
        rule="Independent authorized witness binds actual prior accepted head/chain; unavailable required witness blocks. Serialized receipt/principal name/hash cannot self-mint witness authority or replace verified history.")
    add("BUILD_RECIPE_V2", {"builder_code_ref": ref("raw_ref"), "command_spec_ref": ref("raw_ref"), "dependency_plan_ref": ref("external_profile_ref"),
                           "settings_ref": ref("external_profile_ref")},
        dependencies=["RETAINED_PRODUCER_CODE_V1", "EXECUTION_COMMAND_JSON_V1", "EXECUTION_DEPENDENCY_PLAN_V1", "DETERMINISTIC_BUILD_SETTINGS_V2"],
        rule="Exact independently authorized retained builder/command/dependency settings, source and full standalone input closure. Build output finalizes later; no future BuildManifest/output hash in its own preregistered inputs.")
    add("DETERMINISTIC_BUILD_SETTINGS_V2", {"member_order": const("UTF8_PATH"), "archive_time": const("1980-01-01T00:00:00"),
                                           "regular_file_mode": const("0644"), "comments": const("EMPTY"), "source_date_epoch": number()},
        rule="Deterministic resource/member settings, exact environment/dependencies and reproducibility checks; byte-identity claim requires actual repeat build equality, not just this declared profile.")
    add("QUALIFIED_PROTOCOL_POLICY_BUNDLE_V2", {
        **{f: target(k) for f, k in (("artifact_contract_registry_ref", "artifact_contract_registry"), ("schema_registry_ref", "schema_registry"),
                                    ("governing_policy_ref", "policy_revision"), ("transition_spec_ref", "spec_revision"), ("trust_profile_ref", "trust_profile"))},
        "protocol_profile_ref": ref("external_profile_ref"), "namespace_profile_ref": ref("external_profile_ref"),
        "serialization_profile_ref": ref("external_profile_ref"), "source_identity_profile_ref": ref("external_profile_ref"),
        "foundation_revision": const("R5.4.2"), "migration_boundary": const("NEW_CAMPAIGN_ONLY"),
    }, dependencies=["NF02_PROTOCOL_PROFILE_V2", "BOOTSTRAP_NAMESPACE_V2", "BDB_CJSON_1", "SOURCE_IDENTITY_V2"],
        rule="Exact complete installed roots bind qualified candidate; Spec references independent protocol only, never this future bundle. Successor Registry pins BDB_BOOTSTRAP_PRECEDENCE_V2 under OD-024: domain order retained, command ordered by actual inline content dependencies. After genesis campaign resolves its exact accepted pins, never latest installation.")
    backend = read(BASE / "candidate/profiles/BDB_R5_4_VALIDATOR_PROFILE_V1.json")["backend"]
    add("QUALIFIED_VALIDATOR_V2", {"backend": const(backend), "dialect": const("https://json-schema.org/draft/2020-12/schema"),
                                  "remote_resolution": const("FORBIDDEN"), "resolution": const("EXACT_BOUND_OFFLINE_DEPENDENCY_CLOSURE"),
                                  "layers": const(["L1", "L2", "L3", "L4", "L5", "L6", "L7"]), "canonical_profile_ref": ref("external_profile_ref")},
        dependencies=["BDB_CJSON_1", "BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1"],
        rule="Exact pinned backend and complete offline schema/semantic/producer/raw/reference/FSM validation. Structural PASS does not prove producer authority, retained bytes, chronology, truth or completion. Unknown schema/format/profile fail closed.")


def resolved_catalog(keys):
    """Build the complete catalog, including explicit reference dependencies."""
    contracts = build_catalog(keys)
    from profile_reference_contracts import decisions
    for (owner, _), reference in decisions(contracts).items():
        if reference["representation"] in ("ExternalProfileRef", "RawRef"):
            contracts[owner]["dependencies"] = sorted(set(contracts[owner]["dependencies"]) | set(reference["targets"]))
    from payload_reference_contracts import decisions as payload_decisions
    own = read(OUT / "OWN_REFERENCE_RESOLUTIONS.json")
    for (owner, _), reference in payload_decisions(contracts, own).items():
        if reference["representation"] in ("ExternalProfileRef", "RawRef"):
            contracts[owner]["dependencies"] = sorted(set(contracts[owner]["dependencies"]) | set(reference["targets"]))
    return contracts


def main():
    preserve()
    versions = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
    keys = sorted("BDB_SCHEMA_REGISTRY::" + key for key in versions.values())
    contracts = resolved_catalog(keys)
    usage = read(OUT / "OWN_REFERENCE_RESOLUTIONS.json")["profile_usage"]
    from auxiliary_profile_contracts import ROOTS
    roots = sorted(set(usage) | set(ROOTS) | {"FULL_PATH_CONTEXT_PARAMETERS_V1", "CLOCK_PROFILE_V1", "SANDBOX_PROFILE_V1", "SEED_PROFILE_V1"} |
                   {c.get("analysis_profile_key", c["algorithm_id"]) for c in read(OUT / "design/PURPOSE_CONTRACT_GRAMMARS.json").values()})
    queue = deque(roots)
    seen = set()
    traversal = []
    pending = []
    while queue:
        name = queue.popleft()
        if name in seen:
            continue
        seen.add(name)
        contract = contracts.get(name)
        traversal.append({"profile": name, "defined_grammar": contract is not None})
        if contract is None:
            pending.append({"profile": name, "status": "OPEN", "class": "E",
                            "problem": "Exact external profile grammar/semantic obligations require design; not an alias to arbitrary installed dictionary",
                            "consumers": usage.get(name, [])})
        else:
            # Common definitions are checked once; do not repeat their large
            # finite report union for every independent profile wrapper.
            Draft202012Validator.check_schema({k: v for k, v in contract["grammar"].items() if k != "$defs"})
            if "payload_grammar" in contract:
                Draft202012Validator.check_schema({k: v for k, v in contract["payload_grammar"].items() if k != "$defs"})
            queue.extend(contract["dependencies"])
    write("design/EXTERNAL_PROFILE_CONTRACTS.json", contracts)
    write("design/PROFILE_CLOSURE_FRONTIER.json", {
        "roots": roots, "traversal": traversal, "reachable_profiles": sorted(seen),
        "draft_contracts": len(contracts), "missing_profile_contracts": pending,
        "semantic_review_pending": sorted(k for k, v in contracts.items() if v["semantic_review"].startswith("PENDING")),
        "fixed_point_reached": False, "candidate_materialized": False,
        "inputs": {"own_reference_resolutions_raw_digest": digest(OUT / "OWN_REFERENCE_RESOLUTIONS.json"),
                   "common_grammar_raw_digest": digest(OUT / "design/COMMON_GRAMMARS.json")},
    })
    print(json.dumps({"reachable_profiles": len(seen), "draft_contracts": len(contracts), "pending_contracts": len(pending), "fixed_point_reached": False}))


if __name__ == "__main__":
    main()

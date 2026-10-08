"""Transitive mandatory method/build/finalization profiles named by owner package."""

from __future__ import annotations

from purpose_contracts import array, const, enum, number, object_schema, ref
from execution import BASE, read


ROOTS = "FULL_PATH_SEMANTIC_V1 CLAIM_SET_CLOSURE_V1 DEPENDENCY_CLOSURE_V1 FULL_FINALIZATION_PROFILE_V1 CHANNEL_CAPTURE_PROFILE_V1 REPORT_EXPORT_PROFILE_V1 INSTALLATION_FULL_PATH_PROFILE_V1 RECOVERY_REFERENCE_PROFILE_V1 REPLAY_CAPSULE_V1 IMPLEMENTATION_MUTATION_CASE_V1 ORACLE_CHALLENGE_CASE_V1 TEMPORAL_MODEL_CLAIM_V1 CAUSAL_CHAIN_V1 ENDURANCE_OBSERVATION_V1 BUILD_PROVENANCE_RECEIPT_V1".split()


def add_contracts(add):
    channels = [entry["channel"] for entry in read(BASE / "candidate/BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json")["profiles"]["ISOLATION_BASELINE_PROFILE_V1"]["channels"]]
    def typed(kinds):
        return {"allOf": [ref("typed_ref"), {"properties": {"kind": enum(kinds)}}]}

    for name, fields, deps, rule in (
        ("FULL_PATH_SEMANTIC_V1", {"layers": const(["L1", "L2", "L3", "L4", "L5", "L6", "L7"]), "missing_proof": const("REJECT_NO_CANONICAL_MUTATION")}, ["QUALIFIED_VALIDATOR_V2"],
         "Conjunction of applicable transport/integrity/schema/ref/history/producer/source/FSM/epistemic/finalization predicates. All own contract obligations execute before durable acceptance; layer omission cannot be replaced by PASS."),
        ("CLAIM_SET_CLOSURE_V1", {"selection": const("ALL_EXACT_UNSUPERSEDED_LINEAGE_TIPS_IN_SCOPE_OR_UNRESOLVED"), "fork_behavior": const("BLOCKED"), "rejected_claims": const("RETAIN_AND_ADJUDICATE_SEPARATELY")}, [],
         "At exact same campaign/source/inventory cut, derive every claim tip, unresolved applicability included; forks block deterministic selection. Claim set and candidate claim/adjudication arrays independently equal full derivation; no unaccepted claims or hand-picked subset."),
        ("DEPENDENCY_CLOSURE_V1", {"selection": const("ALL_ACCEPTED_OBSERVATION_DEPENDENCY_FACTS_AT_CUT"), "missing_capture": const("UNRESOLVED_NOT_INDEPENDENT")}, [],
         "Root observations and all exact accepted dependency facts completely disclose producer/storage/harness/oracle/common-cause paths. Planned dependency profile does not fabricate observed facts or independence; graph is a projection."),
        ("FULL_FINALIZATION_PROFILE_V1", {"no_omission": const("CANDIDATE_STOP_CONCLUSION_PUBLIC_FINAL_EXACT_APPLICABLE_RISK_SET"), "material_drift": const("FRESH_CANDIDATE_AND_BOTH_CHALLENGERS"), "waived_as_satisfied": const(False)}, ["CLAIM_SET_CLOSURE_V1", "CHALLENGER_FRESHNESS_V2", "FINAL_CHAIN_RELEASE_V1"],
         "All direct claim/obligation/adjudication/contradiction/evidence/risk arrays equality-bind accepted exhaustive state at their cuts. Wrapper-only commits do not alter audit basis. Full conclusion needs PASS/adequate/current candidate+both challenges; limited does not improve STOP or READY. Separate scoped approvals never qualify evidence or waive nonwaivable prerequisites."),
        ("CHANNEL_CAPTURE_PROFILE_V1", {"capture_code_ref": ref("raw_ref"), "channel": enum(channels), "capture_context": const("EXACT_ACCEPTED_EXECUTOR_DELIVERY_BASELINE_AND_VIEW")}, ["RETAINED_PRODUCER_CODE_V1", "OBSERVATION_CAPTURE_V2"],
         "Exact trusted actual channel capture and negative access probe under declared controls. Declarations/caller flags cannot establish ENFORCED; unavailable capture remains UNKNOWN. Channel domain must equal exact inherited ten-channel baseline at readback."),
        ("REPORT_EXPORT_PROFILE_V1", {"json_report_profile_ref": ref("external_profile_ref"), "text_report_profile_ref": ref("external_profile_ref"), "membership_profile_ref": ref("external_profile_ref")}, ["FINAL_TECHNICAL_REPORT_JSON_V1", "FINAL_TECHNICAL_REPORT_TEXT_V1", "BUNDLE_MEMBERSHIP_V2"],
         "After prior FinalCase, exact final chain and optional prior release fact produce deterministic retained report; external receipt outside raw preimage. Complete dependency disclosure and no assurance/status upgrade; export adapter cannot select workspace replacement."),
        ("INSTALLATION_FULL_PATH_PROFILE_V1", {"bundle_profile_ref": ref("external_profile_ref"), "context_parameters_ref": ref("external_profile_ref"), "qualification_manifest_raw_ref": ref("raw_ref"), "qualification_record_raw_ref": ref("raw_ref"), "application_build_manifest_ref": typed("build_manifest"), "application_build_provenance_raw_ref": ref("raw_ref"), "write_rule": const("EXACT_FRESH_Q1_SUCCESSOR_NEW_CAMPAIGN_ONLY")}, ["QUALIFIED_PROTOCOL_POLICY_BUNDLE_V2", "FULL_PATH_CONTEXT_PARAMETERS_V1", "RETAINED_OPAQUE_BYTES_V1", "BUILD_PROVENANCE_RECEIPT_V1"],
         "External installation governance record after candidate freeze/Q1, never an input inside that candidate's own digest. Exact qualified manifest/record/all roots/profiles/schema closures verified before campaign initialization; candidate profile contract grammar can be frozen without containing its future instance pin."),
        ("RECOVERY_REFERENCE_PROFILE_V1", {"recovery_contract_ref": ref("external_profile_ref"), "cache_authority": const("FORBIDDEN")}, ["EXACT_DURABLE_RECOVERY_V1"],
         "Complete accepted history and immutable retained raw reconstruct selectors; accepted atomic operation or none, full parent CAS. Original contracts for old campaign; never regeneration from workspace/UI/cache."),
    ):
        contract = add(name, fields, dependencies=deps, rule=rule)
        if name == "INSTALLATION_FULL_PATH_PROFILE_V1":
            contract["wire_profile_id"] = "INSTALLATION_FULL_PATH_PROFILE_V2"
            contract["grammar"]["properties"]["profile_id"] = const("INSTALLATION_FULL_PATH_PROFILE_V2")
            contract["rule"] += " OD-027: this external activation instance is created only after exact Q1, build and output verification; never part of candidate/build inputs. Independently pin and retain full application build manifest/source closure and external receipt/output bytes. No fabricated pre-genesis campaign acceptance, source/build alias, unverified producer, logical-ID/latest selection or same-commit pin replacement."
    capsule = add("REPLAY_CAPSULE_V1", {
        "finding_or_claim_revision_ref": typed("finding_claim_revision finding_adjudication_decision"),
        "subject_baseline_ref": typed("source_generation"), "environment_profile_ref": ref("external_profile_ref"),
        "dependency_set_ref": ref("external_profile_ref"), "harness_ref": ref("external_profile_ref"),
        "fixture_refs": array(ref("raw_ref")), "seed_ref": ref("external_profile_ref"),
        "generator_profile_ref": ref("external_profile_ref"), "command_spec": ref("raw_ref"),
        "expected_invariant_ref": typed("invariant_revision"), "expected_observable": ref("raw_ref"),
        "observer_requirements": array(ref("observation_path_requirement"), 1), "cleanup_spec": ref("external_profile_ref"),
        "producer_ref": ref("external_profile_ref"), "artifact_raw_refs": array(ref("raw_ref")),
    }, raw=True, dependencies=["ENVIRONMENT_PROFILE_V2", "EXECUTION_DEPENDENCY_PLAN_V1", "EXECUTION_HARNESS_V2", "FIXTURE_INPUT_V1", "SEED_PROFILE_V1", "EXECUTION_RUNNER_V2", "EXECUTION_COMMAND_JSON_V1", "CLEANUP_EXPECTED_OBSERVABLE_V1", "OBSERVATION_CAPTURE_V2", "CLEANUP_ASSESSMENT_V2", "PRINCIPAL_AUTHORIZATION_V1", "RETAINED_OPAQUE_BYTES_V1"],
        rule="Exact prior claim/source/intent and retained command/fixture/artifact dependencies; preregistered observer/cleanup context, authenticated invocation independently required. Seed optional only if exact method does not require it. No own bundle ZIP digest or future replay result in raw; reproducibility never proves independence.")
    capsule["payload_grammar"]["required"].remove("seed_ref")
    common = {
        "mutation_id": ref("code"), "mutation_revision": number(1),
        "target_claim_or_invariant_ref": typed("finding_claim_revision invariant_revision"),
        "target_location": ref("source_anchor"), "activation_predicate": ref("raw_ref"),
        "expected_detector_or_observer": ref("external_profile_ref"),
        "positive_control_ref": typed("experiment_spec"), "negative_control_ref": typed("experiment_spec"),
        "clean_target_ref": ref("external_profile_ref"), "known_defective_target_ref": ref("external_profile_ref"),
    }
    dependencies = ["CLEANUP_EXPECTED_OBSERVABLE_V1", "EXECUTION_VARIANT_V2", "EXECUTION_HARNESS_V2", "OBSERVATION_CAPTURE_V2"]
    add("IMPLEMENTATION_MUTATION_CASE_V1", {**common, "mutation_class": const("IMPLEMENTATION_MUTATION")}, raw=True,
        dependencies=dependencies,
        rule="Preregistered exact source anchor/mutated implementation, independently qualified clean/known-defective target and positive/negative controls. Trusted activation plus detector observation derives exact Data68 outcome; no activation/invalid capture gives respective non-success, not killed mutant. Input contains no future own result.")
    add("ORACLE_CHALLENGE_CASE_V1", {**common, "mutation_class": const("ORACLE_CHALLENGE"),
                                    "strong_oracle_ref": ref("external_profile_ref"), "weakened_oracle_ref": ref("external_profile_ref")}, raw=True,
        dependencies=dependencies,
        rule="All four exact clean/defective x strong/weakened executions and activation witnesses mandatory. Baseline miss takes precedence; active weakening losing known-defect detection gives WEAKENING_DETECTED; retained detection requires explicit remaining path to give REDUNDANT_OBSERVER_FOR_CASE. Clean pass alone is insufficient; independently derive Data68 outcome.")
    add("TEMPORAL_MODEL_CLAIM_V1", {"model_revision_ref": typed("state_model"), "invariant_revision_ref": typed("invariant_revision"),
                                   "implementation_scope_refs": array(ref("scope_ref"), 1), "assumptions": array(ref("text")), "bounds": array(ref("model_bound"), 1)}, raw=True,
        dependencies=["MODEL_ARTIFACT_V1", "FINITE_MODEL_FIDELITY_V1"],
        rule="Immutable exact model/invariant/source/scoped assumptions; complete equality with model and fidelity. MODEL_VERIFIED is not implementation coverage; required qualified conformance remains independently checked, no mutable temporal-status authority.")
    add("CAUSAL_CHAIN_V1", {"trigger": ref("text"), "state_transition_refs": array(ref("accepted_event_ref"), 1),
                           "observation_refs": array(typed("observation"), 1), "impact_ref": typed("finding_axis_assessment"),
                           "scope": ref("scope_set"), "evidence_qualification_refs": array(typed("evidence_qualification_assessment"), 1)}, raw=True,
        dependencies=["OBSERVATION_CAPTURE_V2"],
        rule="All exact prior accepted causal steps in compatible execution/environment/source scope, independently qualified observations/impact. Similarity of another chain transfers no proof, missing step remains unresolved.")
    add("ENDURANCE_OBSERVATION_V1", {"duration_workload_profile_ref": ref("external_profile_ref"), "environment_ref": typed("environment_record"),
                                     "resource_baselines": array(object_schema({"resource": enum("CPU_TIME_US WALL_TIME_US MEMORY_BYTES OUTPUT_BYTES FILE_COUNT"), "value": number()})),
                                     "monitoring_path_refs": array(ref("external_profile_ref"), 1), "stop_abort_reason": ref("code"),
                                     "observation_refs": array(typed("observation"), 1)}, raw=True,
        dependencies=["ENDURANCE_WORKLOAD_V1", "OBSERVATION_CAPTURE_V2"],
        rule="Exact planned workload and complete actual independently captured work/resource/observer coverage, all stop/abort conditions retained. Nominal wall-time alone cannot discharge endurance obligation.")
    add("ENDURANCE_WORKLOAD_V1", {"minimum_work_units": number(1), "work_unit": enum("EXECUTIONS SOURCE_MEMBERS OBSERVED_WORKLOAD_UNITS"),
                                  "minimum_observed_duration_us": number(), "required_capture_profile_refs": array(ref("external_profile_ref"), 1)},
        dependencies=["OBSERVATION_CAPTURE_V2", "CLOCK_PROFILE_V1"],
        rule="Positive exact preregistered workload and required independent metric/monitor captures. Derive units and captured duration without retry double counting; unavailable/incomplete capture remains INSUFFICIENT/BLOCKED, never nominal-duration success.")
    receipt = add("BUILD_PROVENANCE_RECEIPT_V1", {"build_input_manifest_ref": typed("build_manifest"), "final_output_raw_ref": ref("raw_ref"),
                                       "build_environment_ref": typed("environment_record"),
                                       "verification_refs": array(typed("validation_result"), 1)}, raw=True,
        dependencies=["RETAINED_OPAQUE_BYTES_V1", "BUILD_RECIPE_V2", "QUALIFIED_VALIDATOR_V2"],
        rule="OD-027 external build-time receipt only after final retained output and all independently captured required build checks, exact pre-build manifest/environment under qualified installation/build context, never fabricated campaign acceptance. Full output RawRef replaces bare digest/length/media aliases. Verification refs select exact independently authenticated build-context validation_result/2 with input_history_cut absent, not compatibility_gate_result or artifact_hash_manifest requiring campaign history/export. Require complete actual mandatory checks, producer authorization, retained target/profile/input/output bytes and independent derivation; a serialized PASS or one partial result grants no verification. Receipt/output outside embedded build input; no canonical release qualification.")
    receipt["wire_profile_id"] = "BUILD_PROVENANCE_RECEIPT_V2"
    receipt["grammar"]["properties"]["profile_id"] = const("BUILD_PROVENANCE_RECEIPT_V2")

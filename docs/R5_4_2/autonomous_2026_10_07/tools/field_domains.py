"""Explicit scalar/compound field decisions; unresolved fields remain a queue."""

from __future__ import annotations

from execution import BASE, OUT, preserve, read, write


def domain_table():
    result = {}

    def add(names, domain):
        for name in names.split():
            assert name not in result, name
            result[name] = domain

    add("abstraction_assumptions environment_input_model_differences failure_assumption_differences fairness_time_assumptions limitations", "Text[]")
    add("bounded_conclusion_statement builder_tool_version claim_statement description failure_assumption expected_buggy_behavior expected_safe_behavior falsification_condition mapping_rationale mechanism_candidate mechanism_statement multi_causal_condition rationale reason reason_unresolved requested_action statement trigger uncertainty_class", "Text")
    add("accepted_head_hash builder_tool_raw_digest", "Digest")
    add("accepted_head_seq", "Revision")
    add("created_at", "UInt")
    add("contradiction_revision corpus_revision environment_revision experiment_revision finding_claim_revision hypothesis_revision invariant_revision obligation_revision root_cause_revision", "Revision")
    add("fail_or_difference_count pass_count qualified_denominator unqualified_count", "UInt")
    add("known_legacy_bug", "Boolean")
    add("real_exit_code", "Int32OrNull")
    add("canonical_surface_category surface_category category checkpoint_family independent_expected_error_family legacy_observed_error_family origin policy_obligation_key scenario_class snapshot_type", "Code")
    add("reason_codes", "Code[]")
    add("challenge_scope claim_scope resolved_scope scope support_scope validity_scope", "ScopeSet")
    add("anchor_descriptor normalized_anchor_descriptor", "SurfaceAnchor")
    add("scope_key", "ScopeKey")
    add("bounds", "ModelBound[]")
    add("omitted_states", "ModelState[]")
    add("positions", "ContradictionPosition[]")
    add("observation_path_requirements", "ObservationPathRequirement[]")
    add("mandatory_obligation_summary", "MandatoryObligationSummary")
    add("unknown_blocked_summary", "UnknownBlockedSummary")
    add("changed_manifest_members", "ChangedManifestMember[]")
    add("dependency_profile_change", "DependencyProfileChange")
    add("allowed_next_transition", "TransitionProposal")
    add("proposal_parent_head", "AcceptedHead")
    add("independent_safe_expected_result legacy_observed_result v2_observed_result", "CompatibilityObservation")
    add("legacy_observation_locator", "LegacyObservationLocator")
    add("projection_code_revision", "RawRef(RETAINED_PRODUCER_CODE_V1)")
    add("required_falsifier", "ExternalProfileRef(METHOD_QUALIFICATION_V1)")
    add("cleanup_spec", "ExternalProfileRef(CLEANUP_ASSESSMENT_V2)")
    add("filesystem_profile", "ExternalProfileRef(FILESYSTEM_BOUNDARY_V2)")
    add("network_profile", "ExternalProfileRef(NETWORK_BOUNDARY_V2)")
    add("clock_profile", "ExternalProfileRef(CLOCK_OBSERVATION_V2)")
    add("sandbox_profile", "ExternalProfileRef(SANDBOX_BOUNDARY_V2)")
    add("seed_profile", "ExternalProfileRef(DETERMINISTIC_SEED_V2)")
    add("evidence_invalidation_state", "TypedRef(evidence_invalidation)[]")
    add("positive_controls", "TypedRef(experiment_spec)[]")
    add("negative_controls", "CONTEXT_SPECIFIC_CONTROL_REFS")
    add("invariant_logical_id", "ID(invariant_revision)")
    add("campaign_id", "ID(campaign_genesis)")
    return result


def main():
    preserve()
    registry = read(BASE / "candidate/BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json")
    enum_domains = registry["enum_domains"]
    own = read(OUT / "OWN_REFERENCE_RESOLUTIONS.json")
    domains = domain_table()
    enums = {k: enum_domains[k] for k in ("assurance_level", "continuation_decision", "termination_state", "epistemic_outcome")}
    enums.update({
        "release_readiness": enum_domains["release_readiness"],
        "severity_value": "CRITICAL HIGH MEDIUM LOW INFO".split(),
        "qualification_status": "UNASSESSED IN_PROGRESS QUALIFIED BLOCKED STALE".split(),
        "substantive_outcome": "NO_VIOLATION_OBSERVED VIOLATION_CONFIRMED INCONCLUSIVE".split(),
        "finding_lifecycle_status": enum_domains["finding_lifecycle"],
        "planning_mode": "PREREGISTERED EXPLORATORY LEGACY_IMPORTED".split(),
        "decision": "APPROVED REJECTED".split(),
        "execution_status": "EXECUTED INCOMPLETE BLOCKED HARNESS_FAILURE RESOURCE_BLOCKED".split(),
        "corpus_role": "CANONICAL_DIRECT_PREDECESSOR AUXILIARY_SAME_STAGE CUMULATIVE_HISTORY CLAIM_QUARANTINE_VIEW EXTERNAL_HOLDOUT CALIBRATION INFORMATIONAL".split(),
        "requested_corpus_role": "CANONICAL_DIRECT_PREDECESSOR AUXILIARY_SAME_STAGE CUMULATIVE_HISTORY CLAIM_QUARANTINE_VIEW EXTERNAL_HOLDOUT CALIBRATION INFORMATIONAL".split(),
        "disposition": "OPEN BOUNDED ACCEPTED_RESIDUAL_RISK BLOCKED UNKNOWN SUPERSEDED".split(),
        "completion_predicate_result": "SATISFIED VIOLATED UNKNOWN BLOCKED".split(),
        "ordering_semantics": ["EXACT_REFERENCE_SET"],
        "exposure_class": "UNSEEN POTENTIALLY_EXPOSED EXPOSED UNKNOWN".split(),
        "decision_type": "COVERAGE_OBLIGATION_WAIVER SCOPE_EXCLUSION RESIDUAL_RISK_ACCEPTANCE DESTRUCTIVE_ACTION LIVE_ACTION CONTINUATION_BUDGET LIMITED_CONCLUSION".split(),
        "expiry_or_single_use_policy": ["SINGLE_ACCEPTED_TRANSITION_AT_EXACT_PARENT"],
    })
    status_domains = {
        "contradiction_revision": "OPEN TESTING RESOLVED_SCOPED RESOLVED_FULL REOPENED BLOCKED".split(),
        "evidence_applicability_assessment": enum_domains["evidence_applicability"],
        "hypothesis_revision": "PROPOSED PREREGISTERED TESTING CONFIRMED REJECTED UNRESOLVED BLOCKED".split(),
        "invariant_revision": "ACTIVE SUPERSEDED RETIRED INVALIDATED".split(),
        "root_cause_revision": "ACTIVE SUPERSEDED RETIRED".split(),
        "sound_claim": "SOUND NOT_ESTABLISHED STALE INVALIDATED BLOCKED".split(),
    }
    fields = []
    pending = []
    for node in own["nodes"]:
        owned_refs = {r["field"].split(".", 1)[0].removesuffix("[]") for r in node["resolved_own_material_refs"]}
        for field in node["body"]["fields"]:
            name = field["field"]
            item = {"owner": node["key"], "field": name, "optional": field["optional"]}
            if "schema" in field:
                item.update(domain="EXACT_QUALIFIED_SCHEMA", schema=field["schema"])
            elif name in domains and name in owned_refs:
                # A nested material reference does not replace its enclosing
                # compound body's type. Preserve the explicitly designed
                # ScopeSet/summary/anchor/control grammar on every regeneration.
                domain = domains[name]
                if domain == "CONTEXT_SPECIFIC_CONTROL_REFS":
                    domain = "TypedRef(experiment_spec)[]" if node["kind"] == "experiment_spec" else "TypedRef(execution_result)[]"
                item.update(domain=domain, source="EXPLICIT_OWNING_COMPOUND_DOMAIN; nested references separately declared")
            elif name in owned_refs:
                item.update(domain="EXPLICIT_MATERIAL_REFERENCE", references=[r for r in node["resolved_own_material_refs"] if r["field"].split(".", 1)[0].removesuffix("[]") == name])
            elif field.get("design_type"):
                item.update(domain=field["design_type"], source="APPROVED_PROPOSAL; nested grammar closure remains checked separately")
            elif field.get("inline_enum"):
                item.update(domain="ENUM", values=field["inline_enum"])
            elif name in enums:
                item.update(domain="ENUM", values=enums[name])
            elif name == "status" and node["kind"] in status_domains:
                item.update(domain="ENUM", values=status_domains[node["kind"]])
            elif name == "result" and node["kind"] == "release_qualification":
                item.update(domain="ENUM", values=enum_domains["release_readiness"])
            elif name in domains:
                domain = domains[name]
                if domain == "CONTEXT_SPECIFIC_CONTROL_REFS":
                    domain = "TypedRef(experiment_spec)[]" if node["kind"] == "experiment_spec" else "TypedRef(execution_result)[]"
                item.update(domain=domain)
            elif name.endswith("_id"):
                # This only specifies logical ID syntax; it cannot select a ref,
                # canonical kind, schema, authority or a body field by convention.
                item.update(domain="ID(" + node["kind"] + ")", source="OD-005 exact owning wire kind")
            else:
                pending.append(item)
                item["domain"] = "UNRESOLVED"
            fields.append(item)
    write("design/OWN_FIELD_DOMAINS.json", {"fields": fields, "pending": pending, "status": "DESIGN_ONLY", "semantic_fixed_point_reached": False,
          "note": "Explicit domains do not imply all nested grammars, semantic validators or successor versions are complete"})
    print({"own_fields": len(fields), "unresolved_own_field_domains": len(pending)})
    for item in pending:
        print(item["owner"] + "." + item["field"])


if __name__ == "__main__":
    main()

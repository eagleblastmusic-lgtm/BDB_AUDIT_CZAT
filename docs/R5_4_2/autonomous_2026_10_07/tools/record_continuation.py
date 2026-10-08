"""Update persistent work state without claiming unexecuted acceptance gates."""

from __future__ import annotations

import re

from execution import OUT, ROOT, read, write


def main():
    path = OUT / "ISSUE_REGISTER.json"
    register = read(path)
    issues = {i["id"]: i for i in register["issues"]}
    profile_refs = read(OUT / "design/PROFILE_REFERENCE_CONTRACTS.json")
    payload_refs = read(OUT / "design/PAYLOAD_REFERENCE_CONTRACTS.json")
    issues["EXTERNAL_PROFILE_FIELD_TARGET_AND_SEMANTIC_PARITY"]["progress"] = (
        f'{len(read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json"))} draft profiles; '
        f'{len(profile_refs["material_refs"])} installed-profile and {len(payload_refs["material_refs"])} raw-payload paths declared. '
        'Semantic/producer/context review remains OPEN.')
    issues["CARDINALITY_CONDITIONAL_SCHEMA_PARITY"]["progress"] = "861 material paths with zero local multiplicity issues; 69 conditional/cross-object obligations remain explicit. 21 root-conditional grammar known answers PASS."
    issues["EXACT_BOUND_REPORT_FIXTURE"]["progress"] = "Report syntax fixture now resolves finite explicit DRAFT schemas offline, including missing-dependency and extra-field rejection. Exact qualified binding execution remains NOT_RUN; this issue stays OPEN until materialization/Q1."
    semantic_queue = read(OUT / "design/SEMANTIC_OBLIGATION_QUEUE.json")
    paragraph_count = sum(len(node["source_paragraphs"]) for node in semantic_queue["nodes"])
    issues["CANONICAL_CROSS_OBJECT_PREDICATE_COMPLETION"]["progress"] = (
        f'{len(semantic_queue["nodes"])} per-kind review entries retain {paragraph_count} source paragraphs. '
        'Empty type/profile queues are not accepted-instance chronology or semantic predicate parity.')
    for item in (
        {"id": "ROOT_CONDITIONAL_ASSERTIONS_DROPPED", "status": "RESOLVED", "class": "D", "problem": "Field-only schema reconstruction omitted original root conditionals/XOR and allowed partial HistoryCuts", "resolution": "OD-021 root assertion preservation and exact cut branches; 21 draft grammar KATs PASS. Canonical execution remains pending.", "evidence": ["design/CONDITIONAL_GRAMMAR_KNOWN_ANSWERS.json"]},
        {"id": "FULL_PATH_FSM_REPRESENTATION", "status": "RESOLVED", "class": "D", "problem": "Spec lacked one exact complete FSM table", "resolution": "OD-022 required transition_contract_ref and FULL_PATH_TRANSITION_TABLE_V2; guard runtime/parity execution remains pending.", "evidence": ["design/FULL_PATH_TRANSITION_TABLE.json"]},
        {"id": "INSTALLATION_FUTURE_METHOD_EFFORT_BACKLINKS", "status": "RESOLVED", "class": "D", "problem": "Initial policy context selected purpose profiles containing future experiment/stage facts", "resolution": "OD-023 METHOD_QUALIFICATION_V2 and OBSERVED_EFFORT_V2 select independent exact prior subject context without future fact pins.", "evidence": ["design/PURPOSE_CONTRACT_GRAMMARS.json", "design/PURPOSE_PREDICATE_CONTRACTS.md"]},
    ):
        if item["id"] not in issues:
            register["issues"].append(item)
    # Counts come from the current audits, not historic constants.
    cardinality = read(OUT / "design/CARDINALITY_AUDIT.json")
    conditional = read(OUT / "design/CONDITIONAL_GRAMMAR_KNOWN_ANSWERS.json")
    scope = read(OUT / "design/SCOPE_EXCLUSION_DESIGN_CONTROLS.json")
    bootstrap = read(OUT / "design/REGISTRY_BOOTSTRAP_SUCCESSOR_DELTA.json")
    build = read(OUT / "design/BUILD_INSTALLATION_CONTEXT_CONTROLS.json")
    source_controls = read(OUT / "design/SOURCE_IDENTITY_DESIGN_CONTROLS.json")
    source_instance = read(OUT / "design/source_instance_readback/READBACK.json")
    source_archive = read(OUT / "design/source_instance_readback/ARCHIVE_READBACK.json")
    for item in (
        {"id": "SOURCE_COMPLETENESS_OPEN_SCALAR", "status": "DESIGN_CORRECTION_PASS_TRUSTED_DERIVATION_OPEN", "class": "D",
         "decision": "OD-028", "problem": "SourceIdentity completeness_state accepted arbitrary strings",
         "resolution": "Finite COMPLETE_SOURCE/BOUNDED_SOURCE; neither declaration is independent completeness proof"},
        {"id": "SOURCE_PROFILE_MISSING_EXPLICIT_PARAMETERS", "status": "DESIGN_CORRECTION_PASS_RUNTIME_OPEN", "class": "D",
         "decision": "OD-029", "problem": "Data8.1 path/entry and source-type/algorithm parameters were implicit",
         "resolution": "Exact path/entry profile pins, closed source-type policies and authenticated-authority parameter mapping; actual trusted matching pending"},
        {"id": "SOURCE_MANIFEST_DOT_PREFIX_REJECTED", "status": "SUCCESSOR_SCHEMA_AND_REAL_MANIFEST_PASS_QUALIFICATION_OPEN", "class": "B",
         "decision": "OD-030", "problem": "Inherited /1 rejects three legitimate hidden source paths in real 499-member HEAD source",
         "resolution": "SourceManifest/2 exact canonical paths; historical /1 preserved; complete actual real manifest validates /2 with zero errors"},
        {"id": "SOURCE_ARCHIVE_PREGENESIS_AND_TRANSPORT_CONTEXT", "status": "DESIGN_AND_REAL_REGULAR_ARCHIVE_PASS_RUNTIME_OPEN", "class": "D",
         "decision": "OD-031", "problem": "Source archive imposed prior accepted manifest at first bootstrap and used NF02 transport instead of source semantics",
         "resolution": "Exact content-or-prior source manifest selection and separate source ZIP profile; retained real 499-member byte/mode readback PASS, special source-type/authority/durable tests pending"},
        {"id": "SOURCE_SYMLINK_ENCODING_SCHEMA_PARITY", "status": "SUCCESSOR_SCHEMA_AND_CONTROLLED_BRANCH_PASS_QUALIFICATION_OPEN", "class": "B",
         "decision": "OD-032", "problem": "Closed inherited entry grammar rejects current materializer's exact symlink target encoding field",
         "resolution": "SourceManifest/2 requires exact base64 encoding plus length/digest; 21 controlled branch/schema vectors PASS; original /1 preserved"},
        {"id": "SOURCE_ARCHIVE_EXACT_RUNTIME_RECONCILIATION", "status": "LOCAL_IMPLEMENTATION_PASS_INSTALLATION_AND_ADMISSION_OPEN", "class": "D",
         "decision": "OD-033", "problem": "Generic NF02 transport rejects legitimate source symlink/colon names and cannot stand in for qualified source reconciliation",
         "resolution": "Separate source-only original ZIP reconciliation; exact code/dependency/schema/profile and operational budget pins. 35 targeted regressions and real 499 regular members PASS; no source authority or activation"},
    ):
        if item["id"] not in issues:
            register["issues"].append({**item, "evidence": ["design/SOURCE_IDENTITY_DESIGN_CONTROLS.json", "design/SOURCE_IDENTITY_SEMANTIC_REVIEW.md", "design/source_instance_readback/READBACK.json"],
                                       "remaining": "Full trusted source/context/schema/profile/instance-DAG/durable parity and fresh qualification"})
    if "CANONICAL_KAHN_COMMAND_PRIORITY" not in issues:
        register["issues"].append({
            "id": "CANONICAL_KAHN_COMMAND_PRIORITY", "status": "OPEN_IMPLEMENTATION_REGRESSION", "class": "B",
            "problem": "Actual canonical_order adds command-first priority before normative typed tie-break and rejects normative independent-node sequence",
            "evidence": ["design/CLOSURE_TIEBREAK_RUNTIME_DIVERGENCE.json"],
            "remaining": "Successor implementation fix, targeted regression, all affected closure/history/build qualification evidence"})
    if "BUILD_CONTEXT_PREGENESIS_ACCEPTANCE_CONTRADICTION" not in issues:
        register["issues"].append({
            "id": "BUILD_CONTEXT_PREGENESIS_ACCEPTANCE_CONTRADICTION", "status": "DESIGN_CORRECTION_CONTROLS_PASS_RUNTIME_OPEN", "class": "D",
            "problem": "Application build source/config required prior campaign acceptance before first EMPTY_HISTORY initialization; receipt also allowed history-dependent compatibility/export witnesses",
            "decision": "OD-027", "evidence": ["design/BUILD_INSTALLATION_CONTEXT_REVIEW.md", "design/BUILD_INSTALLATION_CONTEXT_CONTROLS.json"],
            "remaining": "Complete actual source/build/input/output/qualification/activation closure and transitive backlink rejection; prove qualified running output and durable initialization"})
    issues["CARDINALITY_CONDITIONAL_SCHEMA_PARITY"]["progress"] = (
        f'{len(cardinality["results"])} material paths with {len(cardinality["issues"])} local multiplicity issues; '
        f'{len(cardinality["conditional_obligations"])} conditional/cross-object obligations remain explicit. '
        f'{len(conditional["vectors"])} draft conditional grammar controls PASS; no runtime gate advanced.')
    issues["COMMAND_PAYLOAD_BOOTSTRAP_PRECEDENCE_CYCLE"]["progress"] = (
        f'OD-024 V2 contract-order witness and {len(bootstrap["controls"])} exact Registry/installation-selection delta controls PASS. '
        'All domain precedence retained; V1 fallback/source drift/wrong activation reject. '
        'Normative candidate materialization, actual complete instance DAG and durable guards remain OPEN.')
    issues["SCOPE_STATE_EXCLUSION_CONDITIONAL_GRAMMAR"]["progress"] = (
        f'OD-026 contextual review plus {len(scope["controls"])} read-only model controls PASS; '
        'explicit PRINCIPAL_AUTHORIZATION_V2 purpose class and prior source-member scope-record chronology defined. '
        'Trusted replay, complete per-kind semantic parity and durable rejection/crash/race atomicity NOT_PROVEN.')
    if "SCOPE_EXCLUSION_CONTEXT_AND_AUTHORITY" not in issues:
        register["issues"].append({
            "id": "SCOPE_EXCLUSION_CONTEXT_AND_AUTHORITY", "status": "OPEN_RUNTIME_AND_PARITY", "class": "D",
            "problem": "Exclusion requires exact prior approved purpose/scope, proper human authority class and independent current applicability, not only decision-ref syntax",
            "decision": "OD-026", "evidence": ["design/SCOPE_EXCLUSION_SEMANTIC_REVIEW.md", "design/SCOPE_EXCLUSION_DESIGN_CONTROLS.json"],
            "remaining": "Complete all affected source paragraphs/profile dependencies; actual trusted replay and durable atomic operation controls before qualification"})
    issues["CARDINALITY_CONDITIONAL_SCHEMA_PARITY"]["current_counts"] = {
        "paths": len(cardinality["results"]), "local_issues": len(cardinality["issues"]),
        "conditional_obligations": len(cardinality["conditional_obligations"])}
    write("ISSUE_REGISTER.json", register)
    profile = read(OUT / "design/PROFILE_DESIGN_AUDIT.json")
    wire_count = sum(name != wire for name, wire in profile["wire_identities"].items())
    if "EXTERNAL_PROFILE_WIRE_IDENTITY_LEAK" in issues:
        issues["EXTERNAL_PROFILE_WIRE_IDENTITY_LEAK"]["current_verified_wire_mapping_count"] = wire_count
    if "EXTERNAL_PROFILE_WIRE_IDENTITY_LEAK" not in issues:
        register["issues"].append({
            "id": "EXTERNAL_PROFILE_WIRE_IDENTITY_LEAK", "status": "RESOLVED_GENERATOR_AND_DRAFT_CONTROLS", "class": "B",
            "problem": "Generic add() captured the last purpose item and assigned RECOVERY wire_profile_id to 99 unrelated external profiles; syntax-only fixture checks did not detect metadata mismatch",
            "resolution": "Remove generic captured-item mapping; explicit purpose/successor mappings only. All 124 metadata/grammar wire identities agree and are unique; exact eight delegated wire mappings checked. Recovery leak, implicit successor and duplicate identity regressions reject.",
            "evidence": ["tools/profile_contracts.py", "tools/profile_design_audit.py", "design/PROFILE_DESIGN_AUDIT.json"],
            "qualification": "NOT_RUN; generated candidate pins still pending"})
    # Preserve newly discovered issues as well as previously retained entries.
    write("ISSUE_REGISTER.json", register)
    refs = read(OUT / "design/EXHAUSTIVE_REFERENCE_AUDIT.json")
    write("CONTINUATION_PROGRESS.json", {
        "decision_register_through": max(re.findall(r"^## (OD-\d+)\b", (ROOT / "docs/R5_4_2/OWNER_DELEGATED_DECISION_REGISTER.md").read_text(encoding="utf-8"), re.MULTILINE)), "active_design_keys": len(read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]),
        "profiles": profile["profile_count"], "profile_grammar_vectors": len(profile["vectors"]),
        "declared_profile_cycles": len(profile["cyclic_profiles"]), "draft_fixture_pending": len(profile["fixture_pending"]),
        "actual_body_reference_paths": refs["actual_body_reference_paths"], "missing_reference_declarations": refs["missing_reference_declarations"],
        "cardinality": issues["CARDINALITY_CONDITIONAL_SCHEMA_PARITY"]["current_counts"],
        "fixed_point_reached": False, "qualified_fixture_execution": "NOT_RUN", "candidate_materialized": False,
        "conditional_grammar_controls": len(conditional["vectors"]),
        "scope_exclusion_design_controls": len(scope["controls"]), "bootstrap_integration_design_controls": len(bootstrap["controls"]),
        "profile_wire_identity_controls": len(profile["wire_identity_controls"]),
        "explicit_profile_wire_mappings": wire_count,
        "build_installation_context_controls": len(build["controls"]),
        "source_identity_design_controls": len(source_controls["controls"]),
        "actual_source_manifest_entries": source_instance["entry_count"],
        "actual_source_manifest_schema_errors": len(source_instance["successor_errors"]),
        "retained_actual_source_archive_members": len(source_archive["members"]),
        "source_entry_parity_controls": len(read(OUT / "design/SOURCE_ENTRY_PARITY_CONTROLS.json")["controls"]),
        "actual_source_parser_members": read(OUT / "design/source_instance_readback/SOURCE_PARSER_READBACK.json")["member_count"],
        "installed_profile_material_paths": len(profile_refs["material_refs"]), "raw_payload_material_paths": len(payload_refs["material_refs"]),
        "Q1": "NOT_STARTED", "Q2": "NOT_STARTED", "N5_N11": "NOT_STARTED", "NF02": "OPEN",
        "next_required_work": ["OD-024 bootstrap precedence V2 integration and actual-instance proof", "per-kind source/body/profile/predicate parity", "accepted-instance chronology/DAG", "all conditional reference predicates", "finite classification/policy context parity", "full candidate materialization and fresh Q1", "Q2 and N5-N11"]})


if __name__ == "__main__":
    main()

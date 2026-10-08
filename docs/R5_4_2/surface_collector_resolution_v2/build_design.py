"""Generate design-only V2 diagnostics; never change approved inputs or candidate bytes."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TASK = ROOT / "docs/R5_4_2"
OUT = TASK / "surface_collector_resolution_v2"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ref(field, keys, cardinality="1", cls="PRIOR_ACCEPTED_ONLY", representation=None):
    result = dict(field=field, allowed_keys=keys, cardinality=cardinality, ref_class=cls)
    if representation:
        result["representation"] = representation
    return result


def contract(key, role, body, refs, authority, predicates, alternatives):
    kind, version = key.split("/")
    return {
        "kind": kind,
        "version": version,
        "canonical_role": role,
        "lifecycle": "IMMUTABLE",
        "status": "PROPOSED_NOT_OWNER_APPROVED_NOT_NORMATIVE",
        "schema_key": "BDB_SCHEMA_REGISTRY::" + key,
        "identity": f"ObjectDigest({kind},{version},closed body) under unchanged ADR-006; RawDigest never substituted",
        "authoritative_for": authority,
        "producer_authority": "TRUSTED_COORDINATOR_ACCEPTANCE after independently verified producer/context/raw derivation; caller flags/tokens are not canonical evidence",
        "consumer_roles": ["COORDINATOR", "VALIDATOR", "STORE"],
        "reference_contract_mode": "EXPLICIT_COMPLETE",
        "validation_profile": "FULL_PATH_SEMANTIC_V1",
        "required_validation_layers": ["L1", "L2", "L3", "L4", "L5", "L6", "L7"],
        "body": body,
        "body_rule": "Closed recursively; all listed fields required except explicit ?; no own digest, future consumer, accepting head/event or secret",
        "material_refs": refs,
        "ordering_rules": "Typed/Raw/Profile sets sorted by BDB-CJSON-1(full ref) bytes, no duplicates; source member sets by UTF-8 path; diagnostic arrays preserve exact raw order",
        "uniqueness": "One accepted exact revision per immutable producer run ID and represented context/cut. Changed body under same ID conflicts. Exact retry returns original accepted object/receipt; CAS loser re-resolves, no replacement",
        "revision": "No implicit previous_revision_ref: a new run/reassessment/export has a new ID/context/cut. Historical fact never mutates; downstream refs explicitly select a revision, not latest-by-ID",
        "migration": "Fresh R5.4.2 campaign writes only after future exact qualification/activation. /1 history read under original schema and identity; no alias, conversion, inferred new RawRef or backfilled chronology",
        "cross_object_predicates": predicates,
        "alternatives_rejected": alternatives,
    }


def main():
    baseline = read(OUT / "PRESERVATION_BASELINE.json")
    for file, sha in baseline["protected_files"].items():
        if digest(ROOT / file) != sha:
            raise RuntimeError("CANDIDATE_DRIFT " + file)
    old_path = TASK / "R5_4_2_SEMANTIC_CLOSURE_GRAPH.json"
    old = read(old_path)
    graph = copy.deepcopy(old)
    original = {n["key"]: n for n in old["nodes"]}
    mapping = {f"{k}/1": f"{k}/2" for k in [
        "surface_collector_record", "input_disposition_record", "inventory_revision",
        "tool_execution_record", "fault_run_record", "cleanup_result", "final_technical_report",
        "bundle_manifest",
    ]}
    scalar_raw = ref("collector_raw_ref", [], cls="CONTENT_OBJECT", representation="RawRef, application/json, SURFACE_COLLECTOR_RECORD_JSON_V1")
    collector = contract(
        "surface_collector_record/2", "FACT",
        ["collector_raw_ref:RawRef", "collector_record_profile_ref:ExternalProfileRef", "collector_execution_ref:TypedRef", "collection_run:CollectionRunV2", "collector_record_input_history_cut:HistoryCut"],
        [scalar_raw,
         ref("collector_raw_ref.artifact_contract_ref", [], cls="PINNED_PROFILE_REF", representation="SURFACE_COLLECTOR_RECORD_JSON_V1"),
         ref("collector_record_profile_ref", [], cls="PINNED_PROFILE_REF", representation="SURFACE_COLLECTOR_RECORD_JSON_V1; equal to raw artifact contract pin"),
         ref("collector_execution_ref", ["tool_execution_record/2"]),
         ref("collection_run.collector_profile_ref", [], cls="PINNED_PROFILE_REF", representation="COLLECTOR_CAPABILITY_V1; exact prior installed capability entry"),
         ref("collection_run.assigned_input_manifest_ref", ["source_manifest/1"]),
         ref("collection_run.assigned_inputs[].source_manifest_ref", ["source_manifest/1"], "1..65536"),
         ref("collection_run.terminal_input_dispositions[].input_ref.source_manifest_ref", ["source_manifest/1"], "1..65536"),
         ref("collection_run.terminal_input_dispositions[].exclusion_decision_ref", ["approval_decision/1"], "0..65536 conditional EXCLUDED"),
         ref("collection_run.emitted_surface_refs", ["surface_key/1"], "0..65536"),
         ref("collection_run.runtime_manual_additions[].surface_key_ref", ["surface_key/1"], "0..65536"),
         ref("collection_run.runtime_manual_additions[].observation_ref", ["observation/1"], "0..65536"),
         ref("collection_run.parse_errors[].input_ref.source_manifest_ref", ["source_manifest/1"], "0..65536"),
         ref("collection_run.unsupported_capabilities[].input_ref.source_manifest_ref", ["source_manifest/1"], "0..65536"),
         ref("collection_run.resource_limit_events[].input_ref.source_manifest_ref", ["source_manifest/1"], "0..65536"),
         ref("collector_record_input_history_cut", ["history_cut/1"], cls="HISTORY_INPUT")],
        "Exact immutable collector representation plus independently derived accounting statement; not coverage, materiality, evidence qualification or assurance",
        ["Read durable raw; verify digest and length; strict pinned parser produces the entire CollectionRunV2; equality with proposed collection_run mandatory before any acceptance",
         "Prior trusted ToolExecutionRecord/2 must name the exact collector RawRef in its retained outputs, the same source/authorized ExperimentSpec, collector capability and actual captured invocation; capture output alone establishes no coverage. Raw payload has no backlink to this future tool record",
         "Input cut is the current verified expected parent and nonempty. Manifest, capability/profile authority, SurfaceKeys and manual witness observations are prior and source-bound at that cut",
         "assigned_inputs equals every exact entry path in assigned_input_manifest_ref; every member has exactly one terminal disposition; PROVISIONAL/missing/duplicate dispositions reject",
         "emitted_surface_refs intentionally refers to prior surface_key/1 identities in /2, never to future SurfaceRecord objects. SurfaceRecord provenance points backward to accepted collector/2 and its key must be a declared emitted/manual key",
         "Errors, unsupported capabilities and resource limit records are all retained, in raw order. ACCOUNTED proves accounting only, never successful collection or coverage",
         "EXCLUDED requires a prior authorized SCOPE_EXCLUSION ApprovalDecision in the capability-authorized context; a parser or collector cannot authorize exclusion",
         "Every referenced raw remains retrievable for replay/finalization/recovery. Missing/corrupt raw blocks authority consumption; independently verified identical bytes alone may restore availability",
         "Manual additions are captured before raw finalization, each bound to a prior observation and SurfaceKey; later additions require a new run/raw/accepted record and inventory revision"],
        ["Separate collection_run/1 duplicates typed semantic authority and adds a kind without eliminating normalization or ordering requirements",
         "Direct /1 RawDigest interpretation violates ADR-006 TypedRef ObjectDigest domain and rewrites historical identity",
         "Adding a RawRef to /1 changes its body without a version boundary",
         "SurfaceRecord↔collector typed backlinks create a future/self hash cycle; /2 uses prior SurfaceKey identities in the output enumeration"],
    )
    input_record = contract(
        "input_disposition_record/2", "FACT",
        ["input_disposition_record_id:ID", "assigned_input_ref:AssignedInputV2", "disposition:COLLECTED|UNSUPPORTED|EXCLUDED|COLLECTION_FAILED|PARSING_FAILED|PROVISIONAL", "collector_record_ref?:TypedRef", "disposition_input_history_cut:HistoryCut", "reason_codes:Code[]"],
        [ref("assigned_input_ref.source_manifest_ref", ["source_manifest/1"], "0..1 conditional SOURCE_MEMBER"),
         ref("assigned_input_ref.artifact_ref", ["source_manifest/1", "legacy_raw_ref/1", "surface_collector_record/2"], "0..1 conditional CANONICAL_ARTIFACT"),
         ref("collector_record_ref", ["surface_collector_record/2"], "0..1 required for SOURCE_MEMBER terminal facts"),
         ref("disposition_input_history_cut", ["history_cut/1"], cls="HISTORY_INPUT")],
        "Exact member or whole-artifact accounting fact; not current inventory authority",
        ["SOURCE_MEMBER terminal fact equals the unique matching input/disposition/reason-code entry derived from referenced prior collector/2; its assigned manifest and member path exactly match",
         "PROVISIONAL is interim only, has no terminal collector assertion, never meets complete Stage/STOP input accounting",
         "CANONICAL_ARTIFACT is the entire exact accepted artifact, not a file selected by display path; requires original applicable admission/accounting policy, not collector-member semantics",
         "Cut/context/raw must remain applicable; unsupported/excluded/failed is not coverage PASS"],
        ["Keeping /1 TypedRef-only assigned inputs loses source-member identity or mints one source manifest per file", "Using file paths without exact source manifest would launder replacement bytes"],
    )
    inv_old = original["inventory_revision/1"]
    inv_refs = []
    for r in inv_old["qualified_registry_row"]["material_refs"]:
        keys = []
        for edge in old["edges"]:
            if edge["from"] == "inventory_revision/1" and edge["field"] == r["field"]:
                keys.append(mapping.get(edge["to"], edge["to"]))
        if r["field"] != "assigned_input_refs":
            inv_refs.append(ref(r["field"], sorted(set(keys)), r["cardinality"], r["ref_class"], "exact original profile/HistoryCut" if not keys else None))
    inv_refs += [ref("assigned_input_refs[].source_manifest_ref", ["source_manifest/1"], "0..65536"),
                 ref("assigned_input_refs[].artifact_ref", ["source_manifest/1", "legacy_raw_ref/1", "surface_collector_record/2"], "0..65536"),
                 ref("collector_record_refs", ["surface_collector_record/2"], "1..65536")]
    inventory = contract(
        "inventory_revision/2", "FACT",
        ["inventory_id:ID", "inventory_revision:positive integer", "source_generation_ref:TypedRef", "collector_profile_refs:ExternalProfileRef[]", "assigned_input_refs:AssignedInputV2[]", "input_disposition_refs:TypedRef[]", "surface_refs:TypedRef[]", "scope_state_record_refs:TypedRef[]", "manual_runtime_additions:TypedRef[]", "unresolved_scope_refs:TypedRef[]", "basis_history_cut:HistoryCut", "collector_record_refs:TypedRef[]"],
        inv_refs,
        "Exact complete selected inventory/accounting revision, preserving denominator and unresolved scope",
        ["SourceGeneration materialized manifest matches every member input and all collector source/key contexts",
         "Member inputs equal union of all selected collectors' assigned member inputs; each has exactly one selected matching prior InputDispositionRecord/2; duplicate contradictory collector outcomes block rather than latest-wins",
         "Every declared emitted/manual SurfaceKey has a selected SurfaceRecord/1 with exact key/source and provenance to the producing collector/2; no output or diagnostic omission",
         "Manual additions must derive from captured collector declarations/witnesses; later additions require new immutable inventory revision and current applicability assessment",
         "All original Inventory/ScopeState/Stage/STOP accounting, exclusion, materiality, obligation and stale-cut predicates remain conjunctive"],
        ["Keep /1 body and invent per-file TypedRef identities", "Cache or UI selected inputs cannot establish denominator"],
    )
    cleanup = contract(
        "cleanup_result/2", "ASSESSMENT",
        ["cleanup_result_id:ID", "execution_descriptor_ref:TypedRef", "cleanup_observation_refs:TypedRef[]", "cleanup_spec_ref:ExternalProfileRef", "cleanup_input_history_cut:HistoryCut", "result:VERIFIED|FAILED|UNKNOWN|BLOCKED"],
        [ref("execution_descriptor_ref", ["execution_descriptor/1"]), ref("cleanup_observation_refs", ["observation/1"], "1..65536"), ref("cleanup_spec_ref", [], cls="PINNED_PROFILE_REF", representation="CLEANUP_ASSESSMENT_V1"), ref("cleanup_input_history_cut", ["history_cut/1"], cls="HISTORY_INPUT")],
        "Qualified cleanup predicate at a prior cut, independently assessed from retained observations; not raw observation itself",
        ["All required cleanup checks independently derive from retained raw observation paths and exact planned cleanup predicate; VERIFIED only if all PASS; any verified failure gives FAILED; missing witness UNKNOWN, execution blocked BLOCKED",
         "Descriptor and cleanup observations prior; no future ExecutionResult backlink; change of evidence/cut requires a new assessment, not a mutable result"],
        ["Old RAW_EVIDENCE label with no own RawRef is an incomplete identity boundary", "Duplicating raw already bound by Observation adds no authority; classify judgment ASSESSMENT in explicit successor"],
    )
    fault = contract(
        "fault_run_record/2", "FACT",
        ["fault_run_raw_ref:RawRef", "fault_run_profile_ref:ExternalProfileRef", "fault_run:FaultRunV2", "fault_run_input_history_cut:HistoryCut"],
        [ref("fault_run_raw_ref", [], cls="CONTENT_OBJECT", representation="FAULT_RUN_RECORD_JSON_V1"), ref("fault_run_raw_ref.artifact_contract_ref", [], cls="PINNED_PROFILE_REF", representation="FAULT_RUN_RECORD_JSON_V1"), ref("fault_run_profile_ref", [], cls="PINNED_PROFILE_REF", representation="FAULT_RUN_RECORD_JSON_V1"), ref("fault_run.fault_revision_ref", ["fault_spec/1"]), ref("fault_run.execution_descriptor_ref", ["execution_descriptor/1"]), ref("fault_run.activation_evidence_refs", ["observation/1"], "1..65536"), ref("fault_run.scope", ["surface_record/1", "invariant_revision/1", "scope_state_record/1"], "1..65536"), ref("fault_run.cleanup_result_ref", ["cleanup_result/2"]), ref("fault_run_input_history_cut", ["history_cut/1"], cls="HISTORY_INPUT")],
        "Exact raw-backed activation accounting; not evidence qualification or actual fault support without independent witnesses",
        ["Entire nested FaultRunV2 equals strict normalized exact raw JSON; activation status is independently checked against prior pinned FaultSpec/Descriptor and retained activation observations",
         "Status ACTIVATED|NOT_ACTIVATED|PARTIALLY_ACTIVATED|BLOCKED|HARNESS_FAILURE remains original domain; partial/missing activation never upgraded",
         "Descriptor→activation observations→cleanup assessment→FaultRun→ExecutionResult; no future ExecutionResult in evidence/cleanup dependencies"],
        ["Treat digest-less /1 body as raw bytes or secretly add a RawRef to /1", "Caller-proposed activation status cannot establish activation"],
    )
    tool = contract(
        "tool_execution_record/2", "FACT",
        ["tool_run_raw_ref:RawRef", "tool_run_profile_ref:ExternalProfileRef", "tool_run:ToolRunV2", "tool_run_input_history_cut:HistoryCut"],
        [ref("tool_run_raw_ref", [], cls="CONTENT_OBJECT", representation="TOOL_EXECUTION_RECORD_JSON_V1"), ref("tool_run_raw_ref.artifact_contract_ref", [], cls="PINNED_PROFILE_REF", representation="TOOL_EXECUTION_RECORD_JSON_V1"), ref("tool_run_profile_ref", [], cls="PINNED_PROFILE_REF", representation="TOOL_EXECUTION_RECORD_JSON_V1"), ref("tool_run.tool_profile_ref", [], cls="PINNED_PROFILE_REF", representation="TOOL_CAPTURE_V1"), ref("tool_run.execution_descriptor_ref", ["execution_descriptor/1"]), ref("tool_run.command_spec_ref", [], cls="CONTENT_OBJECT", representation="EXECUTION_COMMAND_JSON_V1; exact preregistered runner/dependency plan command RawRef"), ref("tool_run.command_spec_ref.artifact_contract_ref", [], cls="PINNED_PROFILE_REF", representation="EXECUTION_COMMAND_JSON_V1"), ref("tool_run.input_refs", ["experiment_spec/1", "source_generation/1"], "0..65536"), ref("tool_run.output_raw_refs", [], "0..65536", "CONTENT_OBJECT", "exact retained RawRefs"), ref("tool_run.output_raw_refs[].artifact_contract_ref", [], "0..65536", "PINNED_PROFILE_REF", "finite installed raw contracts"), ref("tool_run.environment_ref", ["environment_record/1"]), ref("tool_run_input_history_cut", ["history_cut/1"], cls="HISTORY_INPUT")],
        "Trusted captured exact execution/accounting; output remains observation/hypothesis input, not finding",
        ["Entire ToolRunV2 derives from exact retained raw under pinned capture profile; producer authorization at execution and acceptance independently checked against ExperimentSpec/Environment",
         "actual_command_hash equals exact retained command_spec_ref.raw_digest after independent readback and comparison to actual invocation captured under prior descriptor/runner/dependency-plan authorization; ExperimentSpec has no command_spec field and is not silently repurposed",
         "Real exit and all output/resource records retained; EXITED only verified exit capture, BLOCKED before execution, HARNESS_FAILURE trusted capture failure. Exit zero is not collection, evidence, cleanup or coverage proof"],
        ["Trust incoming producer/status/hash", "Repository-provided command is not authorization to execute"],
    )
    report = contract(
        "final_technical_report/2", "DERIVED_PROJECTION",
        ["report_raw_ref:RawRef", "report_profile_ref:ExternalProfileRef", "report_binding:ReportBindingV2", "report_input_history_cut:HistoryCut"],
        [ref("report_raw_ref", [], cls="CONTENT_OBJECT", representation="FINAL_TECHNICAL_REPORT_JSON_V1"), ref("report_raw_ref.artifact_contract_ref", [], cls="PINNED_PROFILE_REF", representation="FINAL_TECHNICAL_REPORT_JSON_V1"), ref("report_profile_ref", [], cls="PINNED_PROFILE_REF", representation="FINAL_TECHNICAL_REPORT_JSON_V1"), ref("report_binding.campaign_ref", ["campaign_genesis/1", "successor_campaign_genesis/1"]), ref("report_binding.source_generation_ref", ["source_generation/1"]), ref("report_binding.final_assurance_case_ref", ["final_assurance_case/1"]), ref("report_binding.stop_evaluation_ref", ["stop_evaluation/1"]), ref("report_binding.campaign_conclusion_ref", ["campaign_conclusion/1"]), ref("report_binding.release_qualification_ref", ["release_qualification/1"], "0..1"), ref("report_input_history_cut", ["history_cut/1"], cls="HISTORY_INPUT")],
        "Exact retained deterministic report at exact represented head; cannot create or upgrade conclusion",
        ["ReportBindingV2 is exactly Data §81 seven-field binding; optional release ref absent when not qualified; report_as_of_head equals report_input_history_cut head",
         "Raw JSON is exactly Render(prior final chain, report binding, pinned report profile). Complete risk/limited/claim/obligation/error disclosure required; independent byte and semantic equality checked; narration cannot upgrade confidence",
         "FinalCase→optional ReleaseQualification→report raw finalization→report descriptor→external ReportExportReceipt; neither raw nor descriptor contains own/future receipt/ref/digest"],
        ["Raw narrative alone has no typed semantic binding", "Treat EXPORT role as ObjectDigest or add RawRef silently to /1"],
    )
    bundle = contract(
        "bundle_manifest/2", "FACT",
        ["bundle_type:REPORT|REPLAY|RECOVERY|STANDALONE", "bundle_contract_ref:ExternalProfileRef", "root_refs:TypedRef[]", "members:BundleMemberV2[]", "source_generation_ref?:TypedRef", "campaign_ref?:TypedRef", "stage_run_ref?:TypedRef", "lane_run_ref?:TypedRef", "export_as_of_head:AcceptedHead"],
        [ref("bundle_contract_ref", [], cls="PINNED_PROFILE_REF", representation="BUNDLE_MEMBERSHIP_V2"), ref("root_refs", ["final_technical_report/2", "final_assurance_case/1", "campaign_conclusion/1", "stop_evaluation/1", "release_qualification/1", "experiment_spec/1", "execution_descriptor/1", "execution_result/1", "finding_claim_revision/1", "invariant_revision/1", "checkpoint/1", "commit_body/1", "build_manifest/1", "standalone_payload_manifest/1", "schema_registry/2", "artifact_contract_registry/1"], "1..65536"), ref("members[].raw_ref", [], "1..65536", "CONTENT_OBJECT", "exact retained RawRefs"), ref("members[].raw_ref.artifact_contract_ref", [], "1..65536", "PINNED_PROFILE_REF", "finite installed member transport profiles"), ref("source_generation_ref", ["source_generation/1"], "0..1"), ref("campaign_ref", ["campaign_genesis/1", "successor_campaign_genesis/1"], "0..1"), ref("stage_run_ref", ["stage_run/1"], "0..1"), ref("lane_run_ref", ["lane_run/1"], "0..1")],
        "Exact membership declaration; bundle ZIP identity remains separate RawDigest",
        ["BundleMemberV2={member_path:CanonicalPOSIXPath,raw_ref:RawRef}; path sorted unique; semantic member equality with exact finalized member bytes; no parallel array pairing discretion",
         "No own bundle ZIP digest. This fact precedes archive construction; raw bundle/header/hash list exclude self-hash cycles under original export rule. Membership never establishes contained-object qualification"],
        ["Raw EXPORT label with untyped paired path/hash arrays", "A semantic membership fact does not need to hash its future ZIP representation"],
    )
    proposals = {c["kind"] + "/" + c["version"]: c for c in [collector, input_record, inventory, cleanup, fault, tool, report, bundle]}
    write(OUT / "SUCCESSOR_CONTRACT_PROPOSALS.json", proposals)
    active_nodes = []
    for node in graph["nodes"]:
        key = node["key"]
        new = mapping.get(key, key)
        if new != key:
            node = copy.deepcopy(node)
            node.update(key=new, kind=new.split("/")[0], version="2", registered_in_r5_4_1=False, currently_bound=False, schema_key="BDB_SCHEMA_REGISTRY::" + new, proposed_contract=proposals[new], semantic_status="PROPOSED_SUCCESSOR_BOUNDARY_REQUIRES_V2_OWNER_APPROVAL")
            node["historical_predecessor_key"] = key
            node["qualified_registry_row"] = None
            node["proposed_material_ref_completion"] = []
        active_nodes.append(node)
    graph["nodes"] = active_nodes
    keys = {n["key"] for n in active_nodes}
    # Transform exact schema-context target sets, not historical references/bytes.
    for edge in graph["edges"]:
        edge["from"] = mapping.get(edge["from"], edge["from"])
        edge["to"] = mapping.get(edge["to"], edge["to"])
    graph["edges"] = [e for e in graph["edges"] if e["from"] not in proposals]
    external = []
    for key, c in proposals.items():
        for r in c["material_refs"]:
            for target in r["allowed_keys"]:
                graph["edges"].append(dict(from_=key, to=target, field=r["field"], cardinality=r["cardinality"], ref_class=r["ref_class"], source="V2_EXPLICIT_SUCCESSOR_PROPOSAL"))
                graph["edges"][-1]["from"] = graph["edges"][-1].pop("from_")
            if not r["allowed_keys"]:
                external.append({"from": key, **r})
    for k, targets in graph["exact_target_classes"].items():
        graph["exact_target_classes"][k] = [mapping.get(t, t) for t in targets]
    graph["exact_target_classes"]["collector_output_identity_ref"] = ["surface_key/1"]
    graph["historical_read_only_keys"] = sorted(mapping)
    graph["historical_graph_raw_digest"] = digest(old_path)
    graph["historical_owner_package_raw_digest"] = digest(TASK / "R5_4_2_OWNER_DECISION_PACKAGE.md")
    graph["V2_version_target_rules"] = mapping
    graph["V2_external_material_refs"] = external
    # Keep qualified rows as evidence, but explicitly expose the transformed
    # effective refs separately. Nothing in this graph installs these contracts.
    for node in active_nodes:
        source_key = node.get("historical_predecessor_key", node["key"])
        node["V2_effective_canonical_reference_edges"] = [e for e in graph["edges"] if e["from"] == node["key"]]
        if node.get("proposed_contract") and node["key"] not in proposals:
            for r in node["proposed_contract"].get("material_refs", []):
                r["allowed_keys"] = [mapping.get(t, t) for t in r.get("allowed_keys", [])]
        node["V2_body_readiness"] = "EXPLICIT_SUCCESSOR_PROPOSAL" if node["key"] in proposals else "INHERITED_APPROVED_DESIGN_REQUIRES_FIELD_LEVEL_READINESS_AUDIT"
        node["V2_source_selector"] = source_key
    materiality = next(n for n in active_nodes if n["key"] == "materiality_assessment/1")
    collector_source = original["surface_collector_record/1"]["normative_semantic_source"]
    materiality["normative_semantic_source"] = copy.deepcopy(collector_source)
    materiality["V2_source_selector"] = "Data §30 second fenced body beginning materiality_assessment_id; not §34 coverage body"
    successor = next(n for n in active_nodes if n["key"] == "successor_campaign_selection_decision/1")
    successor["V2_source_selector"] = "Data §14.5 explicit SuccessorCampaignSelectionDecision six-field prose; not RunManifest/Genesis body"
    legacy_equivalence = next(n for n in active_nodes if n["key"] == "legacy_observation_semantic_equivalence_assessment/1")
    legacy_equivalence["V2_source_selector"] = "Data §91 named LegacyObservationSemanticEquivalenceAssessment sub-body; not other assessments"
    graph["authority"] = "V2_DESIGN_ONLY_PENDING_NEW_OWNER_APPROVAL; V1 approval does not authorize these new decisions"
    graph["candidate_materialized"] = False
    graph["schemas_generated"] = 0
    graph["qualification_performed"] = False
    graph["schema"] = "BDB_R5_4_2_SEMANTIC_CLOSURE_ANALYSIS/2"
    # Full worklist expansion, including all old seeds and every new ref. This proves
    # graph reachability only, not that referenced prose supplies an exact body.
    queue = deque(sorted(keys))
    seen = set()
    log = []
    while queue:
        key = queue.popleft()
        if key in seen:
            continue
        seen.add(key)
        targets = sorted({e["to"] for e in graph["edges"] if e["from"] == key})
        if not set(targets) <= keys:
            raise RuntimeError("UNRESOLVED_TARGET " + key)
        queue.extend(t for t in targets if t not in seen)
        log.append({"expanded": key, "targets": targets})
    graph["V2_traversal_log"] = log
    graph["queue"] = list(queue)
    graph["V2_graph_reachability_fixed_point"] = seen == keys
    # A semantic fixed point must additionally pass explicit body/profile review.
    # Existing source-section pointers alone are not a machine-generatable body.
    graph["fixed_point_reached"] = False
    graph["gate"] = "SEMANTIC_CLOSURE_INCOMPLETE"
    graph["counts"] = {
        "reachable_active_schema_keys": len(keys),
        "historical_read_only_schema_keys": len(mapping),
        "registered_in_r5_4_1_active": sum(n["registered_in_r5_4_1"] for n in active_nodes),
        "proposed_not_registered_active": sum(not n["registered_in_r5_4_1"] for n in active_nodes),
        "currently_predecessor_schema_bound": sum(n["currently_bound"] for n in active_nodes),
        "missing_predecessor_bindings": sum(not n["currently_bound"] for n in active_nodes),
        "V2_exact_successor_boundary_proposals": len(proposals),
        "semantic_complete": None,
        "unresolved_abstract_canonical_edge_targets": 0,
        "unresolved_Class_D_purpose_contract_families": 16,
        "semantic_incomplete": "NOT_FULLY_ENUMERATED_BY_FIELD_LEVEL_BODY_AUDIT",
    }
    purposes = "STAGE LANE EXECUTOR DELIVERY COLLECTOR METHOD CONFIRMATION MATCHING NOVELTY RELATIONSHIP ASSESSOR MODEL FAULT RELEASE EFFORT RECOVERY".split()
    pending = [{"id": "V2_D_CONTEXT_" + purpose, "class": "D", "target": "FULL_PATH_CONTEXT_PARAMETERS_V1/" + purpose,
                "resolved_hypothetically": False,
                "reason": "PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name",
                "scope": "mandatory Q2–N11 exact purpose dependency; not permission to invent runtime predicates"} for purpose in purposes]
    graph["unresolved"] = pending
    graph["semantic_queue"] = [p["id"] for p in pending]
    graph["V2_profile_grammar_designs"] = {
        "file": "surface_collector_resolution_v2/ADDITIONAL_PROFILE_CONTRACT_PROPOSALS.md",
        "raw_digest": digest(OUT / "ADDITIONAL_PROFILE_CONTRACT_PROPOSALS.md"),
        "concrete_proposals": ["MODEL_ARTIFACT_V1 finite state/mapping grammar", "ClosedPurposePayload tagged snapshot closure", "CLEANUP_EXPECTED_OBSERVABLE_V1 strict selector/equality", "FINAL_TECHNICAL_REPORT_JSON_V1 and exact text labels", "BUNDLE_MEMBERSHIP_V2 complete root/membership closure", "EXECUTION_COMMAND_JSON_V1 exact planned command", "FULL_PATH_CONTEXT_PARAMETERS_V1 PurposeEntry wire template"],
        "not_complete": "The final item is a template, not the exact required per-purpose predicate contracts; no readiness is inferred",
    }
    vector_ids = [
        "SURFACE_COLLECTOR_EXACT_RAW_ACCEPT",
        "SURFACE_COLLECTOR_RAW_DIGEST_MISMATCH_REJECT",
        "SURFACE_COLLECTOR_RAW_MISSING_REJECT",
        "SURFACE_COLLECTOR_RAW_CORRUPT_REJECT",
        "SURFACE_COLLECTOR_SEMANTIC_MISMATCH_REJECT",
        "SURFACE_COLLECTOR_WRONG_PROFILE_REJECT",
        "SURFACE_COLLECTOR_WRONG_ASSIGNMENT_REJECT",
        "SURFACE_COLLECTOR_STALE_CUT_REJECT",
        "SURFACE_COLLECTOR_DUPLICATE_DISPOSITION_REJECT",
        "SURFACE_COLLECTOR_MISSING_TERMINAL_DISPOSITION_REJECT",
        "SURFACE_COLLECTOR_DROPPED_PARSE_ERROR_REJECT",
        "SURFACE_COLLECTOR_REPACK_IDENTITY_SEPARATION",
        "SURFACE_COLLECTOR_V1_V2_ALIAS_REJECT",
        "SURFACE_COLLECTOR_FUTURE_SURFACE_CYCLE_REJECT",
        "SURFACE_COLLECTOR_POST_FREEZE_MANUAL_ADDITION_REJECT",
        "SURFACE_COLLECTOR_UNAUTHORIZED_EXCLUSION_REJECT",
        "SURFACE_COLLECTOR_SELF_MINTED_CAPTURE_REJECT",
        "SURFACE_COLLECTOR_CROSS_CAMPAIGN_REJECT",
    ]
    graph["V2_vector_designs"] = [{
        "id": v, "kind": "surface_collector_record/2", "runtime_status": "NOT_RUN",
        "expected": "REJECT" if v.endswith("REJECT") else "ACCEPT" if v.endswith("ACCEPT") else "RAW_IDENTITY_DISTINCT; substitution REJECT",
        "canonical_mutation": "NONE_FOR_EVERY_REJECTION",
        "definition_source": "R5_4_2_SURFACE_COLLECTOR_CONTRACT_PROPOSAL.md §8",
        "before_after_snapshot": ["accepted_head", "commit_count", "event_sequence", "immutable_object_count", "command_index", "receipt_index", "binding_selector", "result_slot_selector", "accepted_raw_references"],
    } for v in vector_ids]
    graph["historical_verification"] = graph.pop("verification")
    graph["historical_verification_scope"] = "Original V1 design only; not fresh V2 verification and not authority for the V2 changed nodes"
    graph["caveat"] = "Empty graph queue does not establish semantic body/profile closure. Do not reuse prior 131-semantic-complete assertion. Exact V2 readiness diagnostics identify remaining work."
    write(TASK / "R5_4_2_SEMANTIC_CLOSURE_GRAPH_V2.json", graph)
    print(json.dumps(graph["counts"], indent=2))


if __name__ == "__main__":
    main()

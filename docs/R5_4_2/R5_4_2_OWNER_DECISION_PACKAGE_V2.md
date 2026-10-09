# R5.4.2 Owner Decision Package V2

DESIGN ONLY — NOT APPROVED — NOT READY FOR MATERIALIZATION.

This V2 package supersedes the earlier design package as the proposed materialization decision document. The earlier package and its owner approval remain exact historical evidence; they authorize neither new /2 contracts nor an unresolved semantic closure. No candidate, schemas, Registry, Golden or qualification records are created. Q1, Q2 and N5–N11 remain NOT_STARTED.

## Exact inheritance and authority boundary

The eight original owner-approved input artifacts, all current prior diagnostics, production source and R5.4.1 predecessor are unchanged. Complete before/after file pins are in surface_collector_resolution_v2/PRESERVATION_BASELINE.json and final verification. No new RawRef, digest domain or role is backfilled into historical collector/1. This proposal requires a new explicit owner decision after complete semantic closure; prior approval alone is insufficient.

## Recommended correction package

Approve the recommended raw-backed collector/2 FACT model, nested CollectionRun, strict parser/capability/capture authority, current HistoryCut, source-member accounting, prior SurfaceKey output identities and backward SurfaceRecord provenance. Risk assessment/acceptance, claim-set/public-statement models and their no-omission predicates remain the prior approved design; target versions change only explicitly as listed here.

Read R5_4_2_SURFACE_COLLECTOR_CONTRACT_PROPOSAL.md and surface_collector_resolution_v2/ADDITIONAL_PROFILE_CONTRACT_PROPOSALS.md together with the following exact contract inventory. The JSON design file supplies material-ref field/cardinality/class/allowed-version tuples; it is not an executable schema.

## Proposed successor contracts

### surface_collector_record/2

Role: FACT. Lifecycle: IMMUTABLE. Authority: Exact immutable collector representation plus independently derived accounting statement; not coverage, materiality, evidence qualification or assurance.

Closed body:

```text
collector_raw_ref:RawRef
collector_record_profile_ref:ExternalProfileRef
collector_execution_ref:TypedRef
collection_run:CollectionRunV2
collector_record_input_history_cut:HistoryCut
```

Material refs:

| Field | Exact target / external representation | Cardinality | Class |
| --- | --- | --- | --- |
| collector_raw_ref | RawRef, application/json, SURFACE_COLLECTOR_RECORD_JSON_V1 | 1 | CONTENT_OBJECT |
| collector_raw_ref.artifact_contract_ref | SURFACE_COLLECTOR_RECORD_JSON_V1 | 1 | PINNED_PROFILE_REF |
| collector_record_profile_ref | SURFACE_COLLECTOR_RECORD_JSON_V1; equal to raw artifact contract pin | 1 | PINNED_PROFILE_REF |
| collector_execution_ref | tool_execution_record/2 | 1 | PRIOR_ACCEPTED_ONLY |
| collection_run.collector_profile_ref | COLLECTOR_CAPABILITY_V1; exact prior installed capability entry | 1 | PINNED_PROFILE_REF |
| collection_run.assigned_input_manifest_ref | source_manifest/1 | 1 | PRIOR_ACCEPTED_ONLY |
| collection_run.assigned_inputs[].source_manifest_ref | source_manifest/1 | 1..65536 | PRIOR_ACCEPTED_ONLY |
| collection_run.terminal_input_dispositions[].input_ref.source_manifest_ref | source_manifest/1 | 1..65536 | PRIOR_ACCEPTED_ONLY |
| collection_run.terminal_input_dispositions[].exclusion_decision_ref | approval_decision/1 | 0..65536 conditional EXCLUDED | PRIOR_ACCEPTED_ONLY |
| collection_run.emitted_surface_refs | surface_key/1 | 0..65536 | PRIOR_ACCEPTED_ONLY |
| collection_run.runtime_manual_additions[].surface_key_ref | surface_key/1 | 0..65536 | PRIOR_ACCEPTED_ONLY |
| collection_run.runtime_manual_additions[].observation_ref | observation/1 | 0..65536 | PRIOR_ACCEPTED_ONLY |
| collection_run.parse_errors[].input_ref.source_manifest_ref | source_manifest/1 | 0..65536 | PRIOR_ACCEPTED_ONLY |
| collection_run.unsupported_capabilities[].input_ref.source_manifest_ref | source_manifest/1 | 0..65536 | PRIOR_ACCEPTED_ONLY |
| collection_run.resource_limit_events[].input_ref.source_manifest_ref | source_manifest/1 | 0..65536 | PRIOR_ACCEPTED_ONLY |
| collector_record_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |

TRUSTED_COORDINATOR_ACCEPTANCE after independently verified producer/context/raw derivation; caller flags/tokens are not canonical evidence

Typed/Raw/Profile sets sorted by BDB-CJSON-1(full ref) bytes, no duplicates; source member sets by UTF-8 path; diagnostic arrays preserve exact raw order

One accepted exact revision per immutable producer run ID and represented context/cut. Changed body under same ID conflicts. Exact retry returns original accepted object/receipt; CAS loser re-resolves, no replacement

No implicit previous_revision_ref: a new run/reassessment/export has a new ID/context/cut. Historical fact never mutates; downstream refs explicitly select a revision, not latest-by-ID

Fresh R5.4.2 campaign writes only after future exact qualification/activation. /1 history read under original schema and identity; no alias, conversion, inferred new RawRef or backfilled chronology

Predicates:

- Read durable raw; verify digest and length; strict pinned parser produces the entire CollectionRunV2; equality with proposed collection_run mandatory before any acceptance
- Prior trusted ToolExecutionRecord/2 must name the exact collector RawRef in its retained outputs, the same source/authorized ExperimentSpec, collector capability and actual captured invocation; capture output alone establishes no coverage. Raw payload has no backlink to this future tool record
- Input cut is the current verified expected parent and nonempty. Manifest, capability/profile authority, SurfaceKeys and manual witness observations are prior and source-bound at that cut
- assigned_inputs equals every exact entry path in assigned_input_manifest_ref; every member has exactly one terminal disposition; PROVISIONAL/missing/duplicate dispositions reject
- emitted_surface_refs intentionally refers to prior surface_key/1 identities in /2, never to future SurfaceRecord objects. SurfaceRecord provenance points backward to accepted collector/2 and its key must be a declared emitted/manual key
- Errors, unsupported capabilities and resource limit records are all retained, in raw order. ACCOUNTED proves accounting only, never successful collection or coverage
- EXCLUDED requires a prior authorized SCOPE_EXCLUSION ApprovalDecision in the capability-authorized context; a parser or collector cannot authorize exclusion
- Every referenced raw remains retrievable for replay/finalization/recovery. Missing/corrupt raw blocks authority consumption; independently verified identical bytes alone may restore availability
- Manual additions are captured before raw finalization, each bound to a prior observation and SurfaceKey; later additions require a new run/raw/accepted record and inventory revision

Rejected alternatives:

- Separate collection_run/1 duplicates typed semantic authority and adds a kind without eliminating normalization or ordering requirements
- Direct /1 RawDigest interpretation violates ADR-006 TypedRef ObjectDigest domain and rewrites historical identity
- Adding a RawRef to /1 changes its body without a version boundary
- SurfaceRecord↔collector typed backlinks create a future/self hash cycle; /2 uses prior SurfaceKey identities in the output enumeration

### input_disposition_record/2

Role: FACT. Lifecycle: IMMUTABLE. Authority: Exact member or whole-artifact accounting fact; not current inventory authority.

Closed body:

```text
input_disposition_record_id:ID
assigned_input_ref:AssignedInputV2
disposition:COLLECTED|UNSUPPORTED|EXCLUDED|COLLECTION_FAILED|PARSING_FAILED|PROVISIONAL
collector_record_ref?:TypedRef
disposition_input_history_cut:HistoryCut
reason_codes:Code[]
```

Material refs:

| Field | Exact target / external representation | Cardinality | Class |
| --- | --- | --- | --- |
| assigned_input_ref.source_manifest_ref | source_manifest/1 | 0..1 conditional SOURCE_MEMBER | PRIOR_ACCEPTED_ONLY |
| assigned_input_ref.artifact_ref | source_manifest/1, legacy_raw_ref/1, surface_collector_record/2 | 0..1 conditional CANONICAL_ARTIFACT | PRIOR_ACCEPTED_ONLY |
| collector_record_ref | surface_collector_record/2 | 0..1 required for SOURCE_MEMBER terminal facts | PRIOR_ACCEPTED_ONLY |
| disposition_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |

TRUSTED_COORDINATOR_ACCEPTANCE after independently verified producer/context/raw derivation; caller flags/tokens are not canonical evidence

Typed/Raw/Profile sets sorted by BDB-CJSON-1(full ref) bytes, no duplicates; source member sets by UTF-8 path; diagnostic arrays preserve exact raw order

One accepted exact revision per immutable producer run ID and represented context/cut. Changed body under same ID conflicts. Exact retry returns original accepted object/receipt; CAS loser re-resolves, no replacement

No implicit previous_revision_ref: a new run/reassessment/export has a new ID/context/cut. Historical fact never mutates; downstream refs explicitly select a revision, not latest-by-ID

Fresh R5.4.2 campaign writes only after future exact qualification/activation. /1 history read under original schema and identity; no alias, conversion, inferred new RawRef or backfilled chronology

Predicates:

- SOURCE_MEMBER terminal fact equals the unique matching input/disposition/reason-code entry derived from referenced prior collector/2; its assigned manifest and member path exactly match
- PROVISIONAL is interim only, has no terminal collector assertion, never meets complete Stage/STOP input accounting
- CANONICAL_ARTIFACT is the entire exact accepted artifact, not a file selected by display path; requires original applicable admission/accounting policy, not collector-member semantics
- Cut/context/raw must remain applicable; unsupported/excluded/failed is not coverage PASS

Rejected alternatives:

- Keeping /1 TypedRef-only assigned inputs loses source-member identity or mints one source manifest per file
- Using file paths without exact source manifest would launder replacement bytes

### inventory_revision/2

Role: FACT. Lifecycle: IMMUTABLE. Authority: Exact complete selected inventory/accounting revision, preserving denominator and unresolved scope.

Closed body:

```text
inventory_id:ID
inventory_revision:positive integer
source_generation_ref:TypedRef
collector_profile_refs:ExternalProfileRef[]
assigned_input_refs:AssignedInputV2[]
input_disposition_refs:TypedRef[]
surface_refs:TypedRef[]
scope_state_record_refs:TypedRef[]
manual_runtime_additions:TypedRef[]
unresolved_scope_refs:TypedRef[]
basis_history_cut:HistoryCut
collector_record_refs:TypedRef[]
```

Material refs:

| Field | Exact target / external representation | Cardinality | Class |
| --- | --- | --- | --- |
| source_generation_ref | source_generation/1 | 1 | PRIOR_ACCEPTED_ONLY |
| collector_profile_refs | exact original profile/HistoryCut | 0..* | HISTORY_CONTEXT_BINDING |
| input_disposition_refs | input_disposition_record/2 | 0..* | CONTENT_OR_PRIOR |
| surface_refs | surface_record/1 | 0..* | CONTENT_OR_PRIOR |
| scope_state_record_refs | scope_state_record/1 | 0..* | CONTENT_OR_PRIOR |
| manual_runtime_additions | surface_record/1 | 0..* | CONTENT_OR_PRIOR |
| unresolved_scope_refs | coverage_obligation/1, finding_claim_revision/1, invariant_revision/1, scope_state_record/1, surface_key/1, surface_record/1 | 0..* | CONTENT_OR_PRIOR |
| basis_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| assigned_input_refs[].source_manifest_ref | source_manifest/1 | 0..65536 | PRIOR_ACCEPTED_ONLY |
| assigned_input_refs[].artifact_ref | source_manifest/1, legacy_raw_ref/1, surface_collector_record/2 | 0..65536 | PRIOR_ACCEPTED_ONLY |
| collector_record_refs | surface_collector_record/2 | 1..65536 | PRIOR_ACCEPTED_ONLY |

TRUSTED_COORDINATOR_ACCEPTANCE after independently verified producer/context/raw derivation; caller flags/tokens are not canonical evidence

Typed/Raw/Profile sets sorted by BDB-CJSON-1(full ref) bytes, no duplicates; source member sets by UTF-8 path; diagnostic arrays preserve exact raw order

One accepted exact revision per immutable producer run ID and represented context/cut. Changed body under same ID conflicts. Exact retry returns original accepted object/receipt; CAS loser re-resolves, no replacement

No implicit previous_revision_ref: a new run/reassessment/export has a new ID/context/cut. Historical fact never mutates; downstream refs explicitly select a revision, not latest-by-ID

Fresh R5.4.2 campaign writes only after future exact qualification/activation. /1 history read under original schema and identity; no alias, conversion, inferred new RawRef or backfilled chronology

Predicates:

- SourceGeneration materialized manifest matches every member input and all collector source/key contexts
- Member inputs equal union of all selected collectors' assigned member inputs; each has exactly one selected matching prior InputDispositionRecord/2; duplicate contradictory collector outcomes block rather than latest-wins
- Every declared emitted/manual SurfaceKey has a selected SurfaceRecord/1 with exact key/source and provenance to the producing collector/2; no output or diagnostic omission
- Manual additions must derive from captured collector declarations/witnesses; later additions require new immutable inventory revision and current applicability assessment
- All original Inventory/ScopeState/Stage/STOP accounting, exclusion, materiality, obligation and stale-cut predicates remain conjunctive

Rejected alternatives:

- Keep /1 body and invent per-file TypedRef identities
- Cache or UI selected inputs cannot establish denominator

### cleanup_result/2

Role: ASSESSMENT. Lifecycle: IMMUTABLE. Authority: Qualified cleanup predicate at a prior cut, independently assessed from retained observations; not raw observation itself.

Closed body:

```text
cleanup_result_id:ID
execution_descriptor_ref:TypedRef
cleanup_observation_refs:TypedRef[]
cleanup_spec_ref:ExternalProfileRef
cleanup_input_history_cut:HistoryCut
result:VERIFIED|FAILED|UNKNOWN|BLOCKED
```

Material refs:

| Field | Exact target / external representation | Cardinality | Class |
| --- | --- | --- | --- |
| execution_descriptor_ref | execution_descriptor/1 | 1 | PRIOR_ACCEPTED_ONLY |
| cleanup_observation_refs | observation/1 | 1..65536 | PRIOR_ACCEPTED_ONLY |
| cleanup_spec_ref | CLEANUP_ASSESSMENT_V1 | 1 | PINNED_PROFILE_REF |
| cleanup_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |

TRUSTED_COORDINATOR_ACCEPTANCE after independently verified producer/context/raw derivation; caller flags/tokens are not canonical evidence

Typed/Raw/Profile sets sorted by BDB-CJSON-1(full ref) bytes, no duplicates; source member sets by UTF-8 path; diagnostic arrays preserve exact raw order

One accepted exact revision per immutable producer run ID and represented context/cut. Changed body under same ID conflicts. Exact retry returns original accepted object/receipt; CAS loser re-resolves, no replacement

No implicit previous_revision_ref: a new run/reassessment/export has a new ID/context/cut. Historical fact never mutates; downstream refs explicitly select a revision, not latest-by-ID

Fresh R5.4.2 campaign writes only after future exact qualification/activation. /1 history read under original schema and identity; no alias, conversion, inferred new RawRef or backfilled chronology

Predicates:

- All required cleanup checks independently derive from retained raw observation paths and exact planned cleanup predicate; VERIFIED only if all PASS; any verified failure gives FAILED; missing witness UNKNOWN, execution blocked BLOCKED
- Descriptor and cleanup observations prior; no future ExecutionResult backlink; change of evidence/cut requires a new assessment, not a mutable result

Rejected alternatives:

- Old RAW_EVIDENCE label with no own RawRef is an incomplete identity boundary
- Duplicating raw already bound by Observation adds no authority; classify judgment ASSESSMENT in explicit successor

### fault_run_record/2

Role: FACT. Lifecycle: IMMUTABLE. Authority: Exact raw-backed activation accounting; not evidence qualification or actual fault support without independent witnesses.

Closed body:

```text
fault_run_raw_ref:RawRef
fault_run_profile_ref:ExternalProfileRef
fault_run:FaultRunV2
fault_run_input_history_cut:HistoryCut
```

Material refs:

| Field | Exact target / external representation | Cardinality | Class |
| --- | --- | --- | --- |
| fault_run_raw_ref | FAULT_RUN_RECORD_JSON_V1 | 1 | CONTENT_OBJECT |
| fault_run_raw_ref.artifact_contract_ref | FAULT_RUN_RECORD_JSON_V1 | 1 | PINNED_PROFILE_REF |
| fault_run_profile_ref | FAULT_RUN_RECORD_JSON_V1 | 1 | PINNED_PROFILE_REF |
| fault_run.fault_revision_ref | fault_spec/1 | 1 | PRIOR_ACCEPTED_ONLY |
| fault_run.execution_descriptor_ref | execution_descriptor/1 | 1 | PRIOR_ACCEPTED_ONLY |
| fault_run.activation_evidence_refs | observation/1 | 1..65536 | PRIOR_ACCEPTED_ONLY |
| fault_run.scope | surface_record/1, invariant_revision/1, scope_state_record/1 | 1..65536 | PRIOR_ACCEPTED_ONLY |
| fault_run.cleanup_result_ref | cleanup_result/2 | 1 | PRIOR_ACCEPTED_ONLY |
| fault_run_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |

TRUSTED_COORDINATOR_ACCEPTANCE after independently verified producer/context/raw derivation; caller flags/tokens are not canonical evidence

Typed/Raw/Profile sets sorted by BDB-CJSON-1(full ref) bytes, no duplicates; source member sets by UTF-8 path; diagnostic arrays preserve exact raw order

One accepted exact revision per immutable producer run ID and represented context/cut. Changed body under same ID conflicts. Exact retry returns original accepted object/receipt; CAS loser re-resolves, no replacement

No implicit previous_revision_ref: a new run/reassessment/export has a new ID/context/cut. Historical fact never mutates; downstream refs explicitly select a revision, not latest-by-ID

Fresh R5.4.2 campaign writes only after future exact qualification/activation. /1 history read under original schema and identity; no alias, conversion, inferred new RawRef or backfilled chronology

Predicates:

- Entire nested FaultRunV2 equals strict normalized exact raw JSON; activation status is independently checked against prior pinned FaultSpec/Descriptor and retained activation observations
- Status ACTIVATED|NOT_ACTIVATED|PARTIALLY_ACTIVATED|BLOCKED|HARNESS_FAILURE remains original domain; partial/missing activation never upgraded
- Descriptor→activation observations→cleanup assessment→FaultRun→ExecutionResult; no future ExecutionResult in evidence/cleanup dependencies

Rejected alternatives:

- Treat digest-less /1 body as raw bytes or secretly add a RawRef to /1
- Caller-proposed activation status cannot establish activation

### tool_execution_record/2

Role: FACT. Lifecycle: IMMUTABLE. Authority: Trusted captured exact execution/accounting; output remains observation/hypothesis input, not finding.

Closed body:

```text
tool_run_raw_ref:RawRef
tool_run_profile_ref:ExternalProfileRef
tool_run:ToolRunV2
tool_run_input_history_cut:HistoryCut
```

Material refs:

| Field | Exact target / external representation | Cardinality | Class |
| --- | --- | --- | --- |
| tool_run_raw_ref | TOOL_EXECUTION_RECORD_JSON_V1 | 1 | CONTENT_OBJECT |
| tool_run_raw_ref.artifact_contract_ref | TOOL_EXECUTION_RECORD_JSON_V1 | 1 | PINNED_PROFILE_REF |
| tool_run_profile_ref | TOOL_EXECUTION_RECORD_JSON_V1 | 1 | PINNED_PROFILE_REF |
| tool_run.tool_profile_ref | TOOL_CAPTURE_V1 | 1 | PINNED_PROFILE_REF |
| tool_run.execution_descriptor_ref | execution_descriptor/1 | 1 | PRIOR_ACCEPTED_ONLY |
| tool_run.command_spec_ref | EXECUTION_COMMAND_JSON_V1; exact preregistered runner/dependency plan command RawRef | 1 | CONTENT_OBJECT |
| tool_run.command_spec_ref.artifact_contract_ref | EXECUTION_COMMAND_JSON_V1 | 1 | PINNED_PROFILE_REF |
| tool_run.input_refs | experiment_spec/1, source_generation/1 | 0..65536 | PRIOR_ACCEPTED_ONLY |
| tool_run.output_raw_refs | exact retained RawRefs | 0..65536 | CONTENT_OBJECT |
| tool_run.output_raw_refs[].artifact_contract_ref | finite installed raw contracts | 0..65536 | PINNED_PROFILE_REF |
| tool_run.environment_ref | environment_record/1 | 1 | PRIOR_ACCEPTED_ONLY |
| tool_run_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |

TRUSTED_COORDINATOR_ACCEPTANCE after independently verified producer/context/raw derivation; caller flags/tokens are not canonical evidence

Typed/Raw/Profile sets sorted by BDB-CJSON-1(full ref) bytes, no duplicates; source member sets by UTF-8 path; diagnostic arrays preserve exact raw order

One accepted exact revision per immutable producer run ID and represented context/cut. Changed body under same ID conflicts. Exact retry returns original accepted object/receipt; CAS loser re-resolves, no replacement

No implicit previous_revision_ref: a new run/reassessment/export has a new ID/context/cut. Historical fact never mutates; downstream refs explicitly select a revision, not latest-by-ID

Fresh R5.4.2 campaign writes only after future exact qualification/activation. /1 history read under original schema and identity; no alias, conversion, inferred new RawRef or backfilled chronology

Predicates:

- Entire ToolRunV2 derives from exact retained raw under pinned capture profile; producer authorization at execution and acceptance independently checked against ExperimentSpec/Environment
- actual_command_hash equals exact retained command_spec_ref.raw_digest after independent readback and comparison to actual invocation captured under prior descriptor/runner/dependency-plan authorization; ExperimentSpec has no command_spec field and is not silently repurposed
- Real exit and all output/resource records retained; EXITED only verified exit capture, BLOCKED before execution, HARNESS_FAILURE trusted capture failure. Exit zero is not collection, evidence, cleanup or coverage proof

Rejected alternatives:

- Trust incoming producer/status/hash
- Repository-provided command is not authorization to execute

### final_technical_report/2

Role: DERIVED_PROJECTION. Lifecycle: IMMUTABLE. Authority: Exact retained deterministic report at exact represented head; cannot create or upgrade conclusion.

Closed body:

```text
report_raw_ref:RawRef
report_profile_ref:ExternalProfileRef
report_binding:ReportBindingV2
report_input_history_cut:HistoryCut
```

Material refs:

| Field | Exact target / external representation | Cardinality | Class |
| --- | --- | --- | --- |
| report_raw_ref | FINAL_TECHNICAL_REPORT_JSON_V1 | 1 | CONTENT_OBJECT |
| report_raw_ref.artifact_contract_ref | FINAL_TECHNICAL_REPORT_JSON_V1 | 1 | PINNED_PROFILE_REF |
| report_profile_ref | FINAL_TECHNICAL_REPORT_JSON_V1 | 1 | PINNED_PROFILE_REF |
| report_binding.campaign_ref | campaign_genesis/1, successor_campaign_genesis/1 | 1 | PRIOR_ACCEPTED_ONLY |
| report_binding.source_generation_ref | source_generation/1 | 1 | PRIOR_ACCEPTED_ONLY |
| report_binding.final_assurance_case_ref | final_assurance_case/1 | 1 | PRIOR_ACCEPTED_ONLY |
| report_binding.stop_evaluation_ref | stop_evaluation/1 | 1 | PRIOR_ACCEPTED_ONLY |
| report_binding.campaign_conclusion_ref | campaign_conclusion/1 | 1 | PRIOR_ACCEPTED_ONLY |
| report_binding.release_qualification_ref | release_qualification/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| report_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |

TRUSTED_COORDINATOR_ACCEPTANCE after independently verified producer/context/raw derivation; caller flags/tokens are not canonical evidence

Typed/Raw/Profile sets sorted by BDB-CJSON-1(full ref) bytes, no duplicates; source member sets by UTF-8 path; diagnostic arrays preserve exact raw order

One accepted exact revision per immutable producer run ID and represented context/cut. Changed body under same ID conflicts. Exact retry returns original accepted object/receipt; CAS loser re-resolves, no replacement

No implicit previous_revision_ref: a new run/reassessment/export has a new ID/context/cut. Historical fact never mutates; downstream refs explicitly select a revision, not latest-by-ID

Fresh R5.4.2 campaign writes only after future exact qualification/activation. /1 history read under original schema and identity; no alias, conversion, inferred new RawRef or backfilled chronology

Predicates:

- ReportBindingV2 is exactly Data §81 seven-field binding; optional release ref absent when not qualified; report_as_of_head equals report_input_history_cut head
- Raw JSON is exactly Render(prior final chain, report binding, pinned report profile). Complete risk/limited/claim/obligation/error disclosure required; independent byte and semantic equality checked; narration cannot upgrade confidence
- FinalCase→optional ReleaseQualification→report raw finalization→report descriptor→external ReportExportReceipt; neither raw nor descriptor contains own/future receipt/ref/digest

Rejected alternatives:

- Raw narrative alone has no typed semantic binding
- Treat EXPORT role as ObjectDigest or add RawRef silently to /1

### bundle_manifest/2

Role: FACT. Lifecycle: IMMUTABLE. Authority: Exact membership declaration; bundle ZIP identity remains separate RawDigest.

Closed body:

```text
bundle_type:REPORT|REPLAY|RECOVERY|STANDALONE
bundle_contract_ref:ExternalProfileRef
root_refs:TypedRef[]
members:BundleMemberV2[]
source_generation_ref?:TypedRef
campaign_ref?:TypedRef
stage_run_ref?:TypedRef
lane_run_ref?:TypedRef
export_as_of_head:AcceptedHead
```

Material refs:

| Field | Exact target / external representation | Cardinality | Class |
| --- | --- | --- | --- |
| bundle_contract_ref | BUNDLE_MEMBERSHIP_V2 | 1 | PINNED_PROFILE_REF |
| root_refs | final_technical_report/2, final_assurance_case/1, campaign_conclusion/1, stop_evaluation/1, release_qualification/1, experiment_spec/1, execution_descriptor/1, execution_result/1, finding_claim_revision/1, invariant_revision/1, checkpoint/1, commit_body/1, build_manifest/1, standalone_payload_manifest/1, schema_registry/2, artifact_contract_registry/1 | 1..65536 | PRIOR_ACCEPTED_ONLY |
| members[].raw_ref | exact retained RawRefs | 1..65536 | CONTENT_OBJECT |
| members[].raw_ref.artifact_contract_ref | finite installed member transport profiles | 1..65536 | PINNED_PROFILE_REF |
| source_generation_ref | source_generation/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| campaign_ref | campaign_genesis/1, successor_campaign_genesis/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| stage_run_ref | stage_run/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| lane_run_ref | lane_run/1 | 0..1 | PRIOR_ACCEPTED_ONLY |

TRUSTED_COORDINATOR_ACCEPTANCE after independently verified producer/context/raw derivation; caller flags/tokens are not canonical evidence

Typed/Raw/Profile sets sorted by BDB-CJSON-1(full ref) bytes, no duplicates; source member sets by UTF-8 path; diagnostic arrays preserve exact raw order

One accepted exact revision per immutable producer run ID and represented context/cut. Changed body under same ID conflicts. Exact retry returns original accepted object/receipt; CAS loser re-resolves, no replacement

No implicit previous_revision_ref: a new run/reassessment/export has a new ID/context/cut. Historical fact never mutates; downstream refs explicitly select a revision, not latest-by-ID

Fresh R5.4.2 campaign writes only after future exact qualification/activation. /1 history read under original schema and identity; no alias, conversion, inferred new RawRef or backfilled chronology

Predicates:

- BundleMemberV2={member_path:CanonicalPOSIXPath,raw_ref:RawRef}; path sorted unique; semantic member equality with exact finalized member bytes; no parallel array pairing discretion
- No own bundle ZIP digest. This fact precedes archive construction; raw bundle/header/hash list exclude self-hash cycles under original export rule. Membership never establishes contained-object qualification

Rejected alternatives:

- Raw EXPORT label with untyped paired path/hash arrays
- A semantic membership fact does not need to hash its future ZIP representation

## Additional profile and body-source decisions

The new additional-profile proposal provides finite model/mapping grammar, exact snapshot closure payload, cleanup equality contract, actual command RawRef grammar, report JSON/text disclosure and complete bundle membership. These are architecture/body decisions, not runtime-generation authority. Materiality source selection uses Data §30, selection-decision body uses §14.5 prose, legacy semantic equivalence uses the named §91 sub-body. No body may be borrowed from a neighboring object simply because a full section contains both.

## Full-graph status and unresolved readiness

Canonical edge traversal expanded all 131 active schema keys. 102 retain registered predecessor keys, 29 are hypothetical proposed keys (21 previously proposed plus 8 explicit /2 successors). 39 predecessor schema bindings are available as historical evidence, 92 active keys have no predecessor binding. Historical read-only /1 keys are reported separately (8); they are not implicitly converted or new writers. Zero canonical edge targets fall outside the explicit finite active set.

These numbers prove graph membership only. The inherited assertion of 131 semantic-complete nodes is not reused. fixed_point_reached=false; the canonical traversal queue is empty, but the semantic-readiness queue has 16 purpose-contract family entries. Individual per-body/purpose review is still necessary; no zero semantic-gap count is asserted.

FULL_PATH_CONTEXT_PARAMETERS_V1 now has an explicit PurposeEntry wire proposal, but its predicate_contract_ref requires an actual versioned purpose contract. The earlier package does not provide exact per-purpose input/output/semantic predicates merely by naming that field. The remaining family inventory is:

- FULL_PATH_CONTEXT_PARAMETERS_V1/STAGE: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name
- FULL_PATH_CONTEXT_PARAMETERS_V1/LANE: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name
- FULL_PATH_CONTEXT_PARAMETERS_V1/EXECUTOR: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name
- FULL_PATH_CONTEXT_PARAMETERS_V1/DELIVERY: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name
- FULL_PATH_CONTEXT_PARAMETERS_V1/COLLECTOR: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name
- FULL_PATH_CONTEXT_PARAMETERS_V1/METHOD: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name
- FULL_PATH_CONTEXT_PARAMETERS_V1/CONFIRMATION: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name
- FULL_PATH_CONTEXT_PARAMETERS_V1/MATCHING: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name
- FULL_PATH_CONTEXT_PARAMETERS_V1/NOVELTY: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name
- FULL_PATH_CONTEXT_PARAMETERS_V1/RELATIONSHIP: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name
- FULL_PATH_CONTEXT_PARAMETERS_V1/ASSESSOR: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name
- FULL_PATH_CONTEXT_PARAMETERS_V1/MODEL: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name
- FULL_PATH_CONTEXT_PARAMETERS_V1/FAULT: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name
- FULL_PATH_CONTEXT_PARAMETERS_V1/RELEASE: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name
- FULL_PATH_CONTEXT_PARAMETERS_V1/EFFORT: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name
- FULL_PATH_CONTEXT_PARAMETERS_V1/RECOVERY: PurposeEntry wire template is proposed; its exact purpose-specific predicate_contract_ref closed contract is not specified by that template or by a profile name

Do not ask the owner to approve an unnamed checker as an implementation detail. A future complete V2 decision must concretely contain all necessary purpose/body/reference resolutions, then rerun semantic readiness and only then permit materialization. This file records the exact completed correction proposals and the unresolved boundary; it does not claim that the requested global pass is complete.

## Gates

Design and proposed vectors: NOT_RUN at runtime. R5.4.1 readback: 120 / 0 mismatch. Candidate/schemas/qualification/runtime: untouched. No request to start Q1/Q2/N5–N11.

Final gate: `SEMANTIC_CLOSURE_INCOMPLETE`.

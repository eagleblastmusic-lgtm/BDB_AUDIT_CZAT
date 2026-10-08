# R5.4.2 surface collector raw-boundary correction

DESIGN ONLY — new owner approval required. No candidate, schema, Registry, qualification or runtime modification. This proposal supplements and, for the conflicts listed here, replaces the previously approved design. Historical proposals, diagnostics and approval remain byte-for-byte unchanged. The exact machine-readable design is `surface_collector_resolution_v2/SUCCESSOR_CONTRACT_PROPOSALS.json`; this is a proposal, not an executable schema.

## 1. Executive recommendation and alternatives

Choose **Model A: `surface_collector_record/2`, FACT, immutable raw-backed semantic envelope**, with CollectionRun as its nested canonical semantic body (option A in task §10). The envelope records a verified captured execution/accounting statement; it does not assess materiality, coverage, finding truth, evidence qualification or assurance. Actual retained collector bytes remain RAW_EVIDENCE with RawDigest. The envelope has ObjectDigest under the existing ADR-006 algorithm. Neither label substitutes one digest domain for the other.

Model B would add `collection_run/1` without removing the need to bind exact raw, pin a parser, prove semantic equality and order downstream references. One envelope already supplies the exact typed authority those consumers need; a second kind adds a second selector and avoidable chronology. Model C fails: neither Registry `/1` nor Data §30 establishes a RawDigest-compatible TypedRef domain. ADR-006 and Data §192.1 prescribe ObjectDigest for canonical TypedRefs. Reading raw as a semantic typed revision, or adding a RawRef to `/1`, changes historical meaning. Reject both. No historical `/1` record is converted or retrospectively repaired.

## 2. Exact sources and conflict table

R5.4.1 manifest readback: 120 entries, zero mismatches. Source HEAD `b7051472909075bb4c83a9a510e298fcca2a6bd5`, tree `3bc05685293d2fade72735e43a2ccc96be26f3f7`. Full input hashes are in `surface_collector_resolution_v2/PRESERVATION_BASELINE.json`. Data §8/§28/§30/§45/§81/§84/§90/§134/§158/§192.1, full ADR-006, Architecture §14, the qualified Registry, approved graph and owner package are the sources; runtime is implementation evidence only.

| Property | Current /1 contract | Current narrative | Approved R5.4.2 intent | Conflict / V2 resolution |
| --- | --- | --- | --- | --- |
| Role | RAW_EVIDENCE | Collector execution/accounting | Roles cannot choose digest domain | Semantic envelope is FACT; raw bytes stay separate |
| Body | Schema deferred; no material refs | §30 lists eleven CollectionRun fields | Closed explicit raw-backed wrapper | No RawRef/body completion existed; add `/2`, preserve `/1` |
| Raw identity | No exact wrapper field | Exact raw provenance is required generally | Retained RawRef | Explicit collector_raw_ref |
| Semantic identity | Ambiguous RAW/EXPORT exception in row | ADR ObjectDigest for semantic revisions | ObjectDigest wrapper distinct from raw | Exact `surface_collector_record/2` digest domain |
| Interpretation | No pinned parser rule | Collector capability profile | Pinned profile, no overlay | SURFACE_COLLECTOR_RECORD_JSON_V1 and separate capability pin |
| Assigned input | Unspecified element shape | Every input accounted, not just surface count | Exact source/context refs | Manifest-bound member identity; versioned disposition/inventory |
| Emitted surfaces | Old graph targets SurfaceRecord | SurfaceRecord provenance can point to collector | No future/self/cyclic refs | `/2` enumerates prior SurfaceKey identities; SurfaceRecord follows collector |
| Manual additions | Unspecified element shape/timing | Runtime/manual additions disclosed | No mutable authority | Captured before raw freeze, exact prior observation witness; later new run |
| Completeness | completion_status undefined | One terminal disposition per assigned input | Fail closed | ACCOUNTED is terminal accounting, not successful collection/coverage |
| Errors/limits | Unspecified payloads/order | Failed/unsupported not scope exclusion | No omission laundering | Closed faithful raw arrays, preserved order, no truncation |
| History | No cut in §30 | Context/history governs accepted meaning | Prior-cut authority | Explicit current pre-acceptance cut, no first-commit sentinel |
| Producer | Trusted coordinator acceptance | Untrusted tool output is not finding | Durable producer boundary | Prior trusted ToolExecutionRecord/2 plus independent derivation |

## 3. Closed canonical envelope

Exactly five required fields, no others:

```text
collector_raw_ref: RawRef
collector_record_profile_ref: ExternalProfileRef
collector_execution_ref: TypedRef(tool_execution_record/2)
collection_run: CollectionRunV2
collector_record_input_history_cut: HistoryCut
```

No extra outer ID duplicates the run ID. The logical ID, when carried in the external typed envelope, equals `collection_run.collection_run_id`, using `surface_collector_record_<uuidv4-lowercase>`. This is an alias for display/idempotency, never authority selected by ID alone. A new execution has a new run ID. There is no mutable “current run”, replacement, hidden predecessor or automatic supersession. Exact retry reuses the accepted object/receipt; changed body under the same run ID conflicts. Concurrent acceptance uses full expected parent CAS.

`ObjectDigest = SHA256(ASCII("BDB2/surface_collector_record/2") + NUL + BDB-CJSON-1(entire five-field body))`. No algorithm/profile change to ADR-006. No own digest, own accepting head/event/commit, future consumer or secret in either raw or canonical body. Exact TypedRef includes the successor executable schema RawDigest; schemas remain unmaterialized in this design task.

`collector_raw_ref` has exactly `raw_digest`, `byte_length`, `media_type`, `artifact_contract_ref`. Digest is 64 lowercase hex SHA256 of exact retained bytes; length is their exact byte count; media type is `application/json`; artifact contract is the exact installed SURFACE_COLLECTOR_RECORD_JSON_V1 ExternalProfileRef. `collector_record_profile_ref` must equal that full profile ref. No path, filename, mtime, workspace copy or cached digest is authority.

## 4. Exact CollectionRunV2 body and element types

Exactly these eleven required fields:

```text
collection_run_id: ID(surface_collector_record)
collector_profile_ref: ExternalProfileRef(COLLECTOR_CAPABILITY_V1)
assigned_input_manifest_ref: TypedRef(source_manifest/1)
assigned_inputs: SourceMemberRef[]
terminal_input_dispositions: CollectorDisposition[]
emitted_surface_refs: TypedRef(surface_key/1)[]
runtime_manual_additions: ManualAddition[]
parse_errors: ParseError[]
unsupported_capabilities: UnsupportedCapability[]
resource_limit_events: ResourceLimitEvent[]
completion_status: ACCOUNTED
```

The target meaning of `emitted_surface_refs` is an explicit **new /2 decision**: source-bound SurfaceKey identities, not SurfaceRecord facts. This is not a reinterpretation of `/1`. Keys establish identity only and cannot prove discovery, collection, completeness or qualification. SurfaceRecord facts with collector provenance are accepted later. This removes both the typed cycle and the raw self-hash cycle; the raw collector output never contains its future wrapper or future surface record refs.

Closed element types (all fields required unless marked `?`; absence, not null, encodes `?`):

```text
SourceMemberRef = {
  source_manifest_ref: TypedRef(source_manifest/1),
  member_path: CanonicalPOSIXPath
}
CollectorDisposition = {
  input_ref: SourceMemberRef,
  disposition: COLLECTED|UNSUPPORTED|EXCLUDED|COLLECTION_FAILED|PARSING_FAILED,
  reason_codes: Code[],
  exclusion_decision_ref?: TypedRef(approval_decision/1)
}
ManualAddition = {
  surface_key_ref: TypedRef(surface_key/1),
  observation_ref: TypedRef(observation/1)
}
ParseError = {input_ref: SourceMemberRef, reason_codes: Code[], detail: Text}
UnsupportedCapability = {
  input_ref: SourceMemberRef, capability_id: Code, reason_codes: Code[]
}
ResourceLimitEvent = {
  input_ref: SourceMemberRef|null,
  resource: CPU_TIME_US|WALL_TIME_US|MEMORY_BYTES|OUTPUT_BYTES|FILE_COUNT,
  limit: UInt, observed: UInt|null, reason_codes: Code[]
}
```

`UInt` is integer 0..9007199254740991; `Code` is ASCII `[A-Z][A-Z0-9_]{0,127}`; `Text` is valid Unicode without lone surrogates, 0..65536 code points, no silent whitespace/Unicode normalization. CanonicalPOSIXPath is 1..4096 Unicode code points, relative slash-separated nonempty components; no leading/trailing slash, `.`, `..`, backslash, NUL, control code points U+0001..001F or U+007F. Comparison is exact UTF-8 bytes, never case folding. Paths must resolve to unique exact entries in the referenced manifest. No arbitrary extension dictionaries. Arrays have 0..65536 entries; assigned/disposition arrays have 1..65536. Resource failures exceeding any bound reject/quarantine; never truncate or omit.

`assigned_inputs` equals **all entries** of the exact assigned manifest, including unsupported entry types. A restricted source selection must have its own legally accepted exact manifest; a collector cannot silently shrink an existing assigned manifest. Every assigned entry gets exactly one terminal disposition. Output zero, exit zero, ACCOUNTED or N surfaces does not prove successful collection or a complete audit denominator. COLLECTED cannot coexist with a parse-error/failure for that input. UNSUPPORTED requires the corresponding unsupported record and remains unsupported scope. Resource failures remain explicit failed dispositions for affected inputs. EXCLUDED requires an exact prior authorized SCOPE_EXCLUSION ApprovalDecision; only EXCLUDED carries exclusion_decision_ref, and it must govern that exact input/scope. No collector-authorized exclusions.

Manual additions are part of the exact raw payload **before** its finalization. Each carries a prior accepted witness observation and prior SurfaceKey. They cannot be appended after raw freeze. Later manual work requires new raw/run/collector fact/inventory revision and rechecks stale downstream assurance. Witnesses may establish observation, not privileged acceptance or finding truth.

## 5. Parser, normalizer and capability profile

SURFACE_COLLECTOR_RECORD_JSON_V1 is a versioned design identity; its RawDigest is intentionally not invented before future materialization. Its interpretation is fully specified here, independently of Python:

1. Read exact durable RawRef, check digest and length. Raw quota: 1..67108864 bytes. Decode UTF-8 strictly, no BOM, surrogate or invalid encoding. One JSON value, no trailing non-whitespace, no duplicate keys at any depth, no nonfinite/float numeric values; only BDB safe integers. No ZIP, executable payload or network schema resolution.
2. Validate the exact closed eleven-field body and element definitions above. Resolve exact installed profile/capability pins and all prior refs. Resource safety/integrity failure precedes semantic checks.
3. Independently require complete manifest membership, exact source identity, authorized invocation, all terminal dispositions, errors/capability/limit consistency and manual witnesses. Missing/corrupt referenced raw fails closed. Capture authorization is established at the trusted durable producer boundary, never by serialized `trusted`, producer string or HMAC token in canonical evidence.
4. Sort assigned_inputs and terminal_input_dispositions by UTF-8 member_path with duplicate rejection; sort emitted_surface_refs by full BDB-CJSON-1 TypedRef bytes with duplicate rejection; sort manual additions by full key-ref bytes then full observation-ref bytes, reject duplicate pairs and duplicate manual key declarations. Reason-code arrays are sorted unique ASCII strings. Preserve parse_errors, unsupported_capabilities and resource_limit_events order and every record verbatim. No error filtering, deduplication, text normalization or inferred success.
5. The resulting full value is `NormalizeCollectorOutput(raw, exact profile)`. It must equal `collection_run` structurally and in BDB-CJSON-1 bytes. Equality does not independently prove real-world completeness; the producer/accounting/source predicates remain mandatory conjunctions.

COLLECTOR_CAPABILITY_V1 has a closed body `{profile_id, collector_revision_ref, supported_input_classes, authorized_command_spec_refs, source_identity_profile_ref}`: profile_id is literal COLLECTOR_CAPABILITY_V1; collector revision is retained RawRef; supported input classes are sorted unique `REGULAR_FILE|SYMLINK|SUBMODULE|OTHER_ALLOWED`; command specs are sorted prior ExperimentSpec/1 refs; source profile is exact ExternalProfileRef. The profile is installed under the authorized installation/trust boundary before the run, has no self digest, and cannot authorize arbitrary repository commands. Unsupported classes require UNSUPPORTED records. Required exact checker/capture/collector code raw dependencies are installed and qualified later; no runtime dict becomes authority.

## 6. Material references, timing and producer

Every material ref is explicit in the JSON proposal. Additional nested material inventory: `terminal_input_dispositions[].exclusion_decision_ref` is 0..65536 `approval_decision/1`, PRIOR_ACCEPTED_ONLY, mandatory exactly for EXCLUDED; all nested source member references are the same prior assigned manifest. Non-null resource event input refs obey the same rule. Raw artifact contract and parser/capability pins are PINNED_PROFILE_REF, immutable installed dependencies available before invocation and at acceptance. RawRef is CONTENT_OBJECT with retained raw reuse only for independently verified identical bytes. The HistoryCut is HISTORY_INPUT, exactly one verified current prior cut; EMPTY_HISTORY_CUT is forbidden.

Strict order:

```text
accepted source/manifest/capability/authorized ExperimentSpec
→ identity-only SurfaceKeys and prior manual observations
→ controlled collector execution
→ finalize and durably retain collector raw
→ finalize trusted tool capture raw and accept ToolExecutionRecord/2
→ verify current input cut + all retained bytes + normalization
→ accept SurfaceCollectorRecord/2
→ accept SurfaceRecord(s) with backward provenance
→ accept InputDispositionRecord/2 and ScopeStateRecord
→ accept InventoryRevision/2
→ original coverage/materiality/Stage/STOP/finalization predicates
```

SurfaceKeys contain source identity/anchor and no collector backlink. Tool capture contains the finalized collector RawRef but no future collector envelope ref. Collector raw does not contain its future ToolExecutionRecord ref; only the canonical envelope binds that prior capture. No same-commit future history authority. The /2 pipeline uses prior accepted semantic refs; a topological same-commit shortcut does not replace these prerequisites.

## 7. Consumer and compatibility mapping

The V2 graph contains every actual canonical inbound/outbound edge, including transitive consumers. Exact active schema context decides target versions; no bare kind or logical ID resolves a version.

| Consumer | Field | Old target | Proposed new target | Reference class | Version rule |
| --- | --- | --- | --- | --- | --- |
| SurfaceRecord/1 | provenance_refs | collector/1, observation/1, tool/1 | collector/2, observation/1, tool/2 | CONTENT_OR_PRIOR; collector provenance specifically prior | /1 collector read historical only; /2 collector new write |
| ScopeStateRecord/1 | basis_refs | collector/1, input disposition/1 and original finite basis | collector/2, input disposition/2 and corresponding finite basis | CONTENT_OR_PRIOR | Exact V2 target set; no alias |
| InventoryRevision/2 | assigned_input_refs | whole TypedRefs | AssignedInputV2 union | Nested refs prior | Versioned body change |
| InventoryRevision/2 | collector_record_refs | absent | collector/2 | PRIOR_ACCEPTED_ONLY | Required source accounting closure |
| InputDispositionRecord/2 | assigned_input_ref | whole TypedRef | AssignedInputV2 | Nested refs prior | Versioned member identity |
| InputDispositionRecord/2 | collector_record_ref | absent | collector/2 | PRIOR_ACCEPTED_ONLY | Mandatory member terminal basis |
| Collector/2 | emitted_surface_refs | SurfaceRecord/1 | SurfaceKey/1 | PRIOR_ACCEPTED_ONLY | Explicit new /2 output identity semantics |
| Collector/2 | collector_execution_ref | absent | tool/2 | PRIOR_ACCEPTED_ONLY | Exact raw/capture/context match |
| FaultRunRecord/2 | cleanup_result_ref | cleanup/1 | cleanup/2 | PRIOR_ACCEPTED_ONLY | Assessment, not raw/typed alias |
| ExecutionResult/1 | fault_activation_record_ref | fault/1 | fault/2 | Original class; prior when consumed | Exact qualified new context |
| All original inventory consumers | inventory refs | inventory/1 | inventory/2 | Original class, full applicability unchanged | New writes only; historical context keeps /1 |
| All original export/bundle consumers | report/bundle refs | report/1, bundle/1 | report/2, bundle/2 | Original prior/content contract, no future consumer | Exact V2 schema pins |

AssignedInputV2 is a closed tagged union: SOURCE_MEMBER has exactly `{input_type:"SOURCE_MEMBER", source_manifest_ref, member_path}`; CANONICAL_ARTIFACT has exactly `{input_type:"CANONICAL_ARTIFACT", artifact_ref}` where target is source_manifest/1, legally admitted legacy_raw_ref/1 or prior collector/2. A whole manifest is not a selected member. Collector SourceMemberRef uses no tag because only the one member representation is admitted. Inventory and InputDisposition exact cross-object rules distinguish these domains. No path-only identity, fabricated file object or retroactive legacy authority.

Other consumers whose bodies are unchanged retain their wire version only where their original contract already referenced the named kind and the new exact schema/context constrains its explicit version. Their historical schema pins remain unchanged. A body/digest-domain change always has an explicit successor key in this proposal, never an in-place rewrite. Future generation must verify this distinction; a newly discovered body change requires another owner decision, not an alias.

## 8. Retention, atomicity and negative vectors

All accepted raw and required nested raw dependencies stay retrievable for replay, recovery, completion, STOP and reporting for the full retained accepted-history lifetime. Scratch or workspace copies cannot substitute. Missing/corrupt raw blocks authority-consuming operations without altering accepted history. Restore only identical independently verified bytes with exact original digest/length/profile. Raw equality and source/accounting validation apply on direct store acceptance as well as workflows.

Design vectors (NOT_RUN; no runtime acceptance evidence):

| ID | Trigger and expected result |
| --- | --- |
| SURFACE_COLLECTOR_EXACT_RAW_ACCEPT | Exact retained raw, all prior pins/capture/input/member/witness predicates; ACCEPT |
| SURFACE_COLLECTOR_RAW_DIGEST_MISMATCH_REJECT | Wrong retained digest; REJECT |
| SURFACE_COLLECTOR_RAW_MISSING_REJECT | Absent raw; REJECT |
| SURFACE_COLLECTOR_RAW_CORRUPT_REJECT | Modified bytes or wrong length; REJECT |
| SURFACE_COLLECTOR_SEMANTIC_MISMATCH_REJECT | Change caller nested semantic value; REJECT |
| SURFACE_COLLECTOR_WRONG_PROFILE_REJECT | Correct-looking local/unbound profile or different exact parser pin; REJECT |
| SURFACE_COLLECTOR_WRONG_ASSIGNMENT_REJECT | Manifest/member/source/authorized invocation mismatch; REJECT |
| SURFACE_COLLECTOR_STALE_CUT_REJECT | Expected parent changed or prior capture not in cut; REJECT |
| SURFACE_COLLECTOR_DUPLICATE_DISPOSITION_REJECT | Two terminal records for one member; REJECT |
| SURFACE_COLLECTOR_MISSING_TERMINAL_DISPOSITION_REJECT | Remove one assigned member's terminal record; REJECT |
| SURFACE_COLLECTOR_DROPPED_PARSE_ERROR_REJECT | Raw retains an error but semantic proposal removes it; REJECT |
| SURFACE_COLLECTOR_REPACK_IDENTITY_SEPARATION | Different permitted JSON whitespace yields same normalized CollectionRun but different RawDigest; original envelope does not authorize substitute bytes; unsupported ZIP repack REJECT |
| SURFACE_COLLECTOR_V1_V2_ALIAS_REJECT | Resolve old /1 schema/body as /2; REJECT |
| SURFACE_COLLECTOR_FUTURE_SURFACE_CYCLE_REJECT | Envelope/raw contains future SurfaceRecord or own wrapper/raw digest; REJECT |
| SURFACE_COLLECTOR_POST_FREEZE_MANUAL_ADDITION_REJECT | Append manual surface only to canonical body; REJECT |
| SURFACE_COLLECTOR_UNAUTHORIZED_EXCLUSION_REJECT | Unsupported converted to excluded without prior decision; REJECT |
| SURFACE_COLLECTOR_SELF_MINTED_CAPTURE_REJECT | Caller trusted flag/hash substitutes for durable capture authorization; REJECT |
| SURFACE_COLLECTOR_CROSS_CAMPAIGN_REJECT | Matching IDs with wrong campaign/source/cut; REJECT |

Each negative canonical write requires REJECT + NO CANONICAL STATE MUTATION. Compare full accepted head, commit count, event sequence, immutable-object count, command index, receipt index, binding selector, result-slot selector and accepted raw refs. Planned later runtime work also includes exact retry, competing threads/processes, raw/canonical crash points and restart reconstruction; none run here.

## 9. Continuing closure and owner decision

The raw-boundary scan also proposes explicit successors for tool execution, fault-run, cleanup judgment, final report and bundle membership; member identity requires inventory/disposition successors. Their complete bodies/refs/predicates/alternatives are in the new JSON proposal and Owner Package V2. Observation/1 already has an approved explicit raw wrapper; LegacyRawRef/1 already has explicit exact raw identity fields and remains the historical/current reference contract, not raw-as-TypedRef reinterpretation. Hash-manifest/export receipts remain the separately approved raw-backed descriptors. The materiality source pointer is corrected from Data §34 to its actual body in §30 in the new analysis only.

The historical empty graph queue is not sufficient proof of semantic closure. The V2 report distinguishes graph reachability from body/profile readiness and never reuses the old “131 semantic-complete” assertion without an explicit audit. Owner must approve the exact successor role/body/identity/ref/profile/order/capture/manual/no-omission decisions in this proposal together with the consolidated V2 corrections. Prior approval remains historical evidence; it does not approve this delta.

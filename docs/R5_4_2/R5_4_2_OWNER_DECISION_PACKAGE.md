# R5.4.2 consolidated owner decision package

**PROPOSED — NOT APPROVED — NOT NORMATIVE/RUNTIME AUTHORITY.** No R5.4.2 candidate, schema, Registry, Golden Vector or qualification record is produced. Q2 and N5–N11 remain NOT_STARTED. Date: 2026-10-06.

Recommended decision: approve **one coherent design delta**, comprising the 21 proposed kinds and all explicit reference/body/profile/temporal completion decisions below. Approval authorizes subsequent candidate materialization only. It does not activate R5.4.1, authorize current overlay/schema authority, freeze independently, implement NF02, qualify runtime or close NF02.

The three original issues are resolved as recommended proposals: ResidualRisk=ASSESSMENT with immutable explicit revisions and separate existing ApprovalDecision; AssuranceClaimSet=complete immutable DERIVED_PROJECTION; PublicConclusionStatement=immutable raw-backed DERIVED_PROJECTION preceding FinalCase. Additional reachable gaps were not stopped at first discovery. They are included in this same approval package.


### Fresh qualified identity readback

| Identity | Exact value |
| --- | --- |
| normative_candidate_set_digest | `d11f751f729605f94bdd11dc033f700f895ee4f7091f2150424023fd4efcaf3b` |
| machine_candidate_set_digest | `640b76678b48d1902c16775c660709101f1a0708805b7608f822af7a0604f682` |
| manifest_raw_digest | `15415abd7d2601698c6ff664a93077213e81575272a213c4511f6082c9d8fdef` |
| registry_raw_digest | `1b9d17c46843a91053036f0370d4419dac87ce5978df61b0dc922e0e40237e2c` |
| golden_raw_digest | `4cebb462b647c69e6348546180900ac2a3c4806a5bf1716e5269b70ed94edb17` |
| schema_registry_object_digest | `de514548328391f271dac2f6b253b8d47ac8d6e5406e6e0781a2bfb18c9cbc1e` |
| qualification_record_raw_digest | `3a3754d4eebac944ad40c7a49cf6db882bbbde6c55c7f14784961dbfc4df8b90` |
| qualification_record_id | `BDB-AUTHOR-BASELINE-QUALIFICATION-R5_4_1-2026-10-06-001` |
| registry_id | `BDB-AUDIT-V2-ARTIFACT-CONTRACT-REGISTRY-R5-4-1` |
| golden_vector_set_id | `BDB-AUDIT-V2-FOUNDATION-GOLDEN-VECTORS-R5-4-1` |

## 1. Identity, schema and reference rules to approve


All new semantic bodies are closed (`additionalProperties=false` in future executable schemas). No unlisted authority field, capability secret, self-digest, future consumer, accepting head/event/receipt is permitted. TypedRef/RawRef/ExternalProfileRef/HistoryCut use Data §192.1 exactly; full reference identity includes kind, version via exact schema, revision digest/profile and schema revision. HistoryInput is nonempty verified prior cut; initialization sentinel only in original bootstrap contracts. Logical ID grammar follows Data §6: lowercase kind prefix plus underscore and canonical UUID; no display ID as selector.

For new contracts: body maximum 16 MiB UTF-8 canonical bytes, each text maximum 65536 Unicode code points (nonempty unless explicitly optional), arrays maximum 65536 members, IDs exact UUID grammar, integers bounded signed 64-bit except strictly positive revision numbers. No NaN/Infinity, duplicate JSON keys, unknown enum values, implicit normalization, or unbounded parser resources. Larger campaign closure must use a separately approved successor contract, not silently truncate. Existing bound contracts retain their exact constraints until a reviewed successor delta explicitly changes them. These bounds are proposed owner-visible semantics, not hidden generator choices.

Reference arrays are full-identity sorted sets with duplicate rejection. Raw/Profile tagged union arrays sort by tag + complete canonical value. `CommitBody.immutable_object_refs` retains original union-DAG topological sequence, never sorted set. Any optional field is absent when unavailable; no new nullable representation unless normative contract explicitly permits it. Every field without `?`/`optional` is required; arrays may be empty only when cardinality says 0. Prior typed refs must be accepted in the exact campaign/source/subject context at the represented cut. External profile fields are exact prior pins for the named purpose; no local overlay, latest-installed selection or caller-minted authority. Raw fields always re-read retained exact bytes and verify digest/length/profile.

FACT means recorded statement/intent, ASSESSMENT means qualified dimension at a cut, DECISION means authorized predicate/decision, DERIVED_PROJECTION means deterministic reproducible enumeration/communication. None can upgrade its source truth. Canonical semantic wrappers use ObjectDigest; actual raw observations, ZIPs, public bytes and text exports use RawDigest. The Registry role name by itself cannot select a digest domain. In particular raw/export files are not silently given an ObjectDigest just because a Registry row names their family; an accepted wrapper must have an explicit closed body/schema and raw reference. Proposed row identity clarification must be approved before generation.

Producer is the trusted coordinator acceptance boundary; projections are independently reproduced there, not accepted from caller checksum. Required validation is the conjunction of original named layer predicates plus applicable new semantic/finalization predicates, as listed in the graph; producer identity never implies evidence strength. Same-cut exact retry reuses original receipt; competing different immutable bodies for one represented tuple conflict by CAS, with **REJECT + NO CANONICAL STATE MUTATION**. Accepted revisions remain immutable. Only explicit predecessor fields create revision lineage; changed tuple/cut for a projection creates a new immutable entry. No hidden mutable current object or latest-by-ID authority. Fresh approved successor campaign only; preserve all old contracts/history/bytes and historical invalid objects for forensic display.


Every scalar enum written in a proposed body is closed; `profile enum` is a finite domain declared in the exact governing purpose profile before first use. It is not an arbitrary runtime extension. Text/scoped subject values never substitute for available exact refs. Common maximum constraints are explicitly proposed above. Cross-object predicates are mandatory semantic-validator checks in addition to future JSON Schema, not discretionary implementation checks.

Generic registered_immutable_object targets become finite active-closure sets in storage wrappers plus exact command-domain predicates, and explicit field-specific target sets elsewhere. Storage acceptance does not legalize an object just because it is on the finite list. CommitBody/CommandEnvelope/CommandReceipt/HistoryCut are not ordinary same-commit payload/output members; receipt remains post-acceptance sidecar. Stage/Lane required outputs must match pinned slots and complete predicates, and cannot require future STOP/Conclusion/FinalCase/ReleaseQualification/PublicStatement. Required closure includes registered RAW_EVIDENCE/EXPORT families and installation profile keys as contract dependencies; actual raw/export bytes remain RawDigest identities, not new campaign state authority.

The complete finite class→kind/version map, each class's actual owner-field cardinality/class and all explicit overrides are in `R5_4_2_SEMANTIC_CLOSURE_GRAPH.json`. CONTENT_OR_PRIOR allows earlier content only where exact owner contract allows it. PRIOR_ACCEPTED_ONLY always prohibits same-commit. HISTORY_INPUT always points backward. Profile refs cannot be semantic self-upgrades. CampaignRef is logical identity established by accepted Genesis/SuccessorGenesis, not a new campaign object. Blocker is a derived ledger (§178); limited basis uses exact underlying obligation/qualification/invalidation/contradiction/risk/STOP/approval/stage facts and requires the corresponding proved blocker, never vague residual-risk text.

## 2. Existing-contract completion decisions

- Correct successor FindingClaimRevision.discovery_relation_refs target set to the six exact provenance assessments (blind eligibility plus five new assessments), backward-only per Data §57. R5.4.1 row currently allows discovery_record, conflicting with the complete narrative section. Preserve that historical qualified row; explicitly correct the successor row/schema, with no alias or retroactive acceptance. Raw DiscoveryRecord cannot substitute for its later assessments.
- Make every schema-deferred material reference explicit before schema generation. Full original bodies/sections, proposed refs, profile/raw representations and exact normative field catalog are recorded per node in the graph. Names are not interpreted as implicit wire aliases. Preserve the separate legacy semantic-equivalence and mapping assessments, evidence applicability versus qualification, and obligation applicability versus waiver.
- Resolve dependency intent before execution as exact EXECUTION_DEPENDENCY_PLAN_V1 profile. Observed ObservationDependency→EvidenceDependencyGraph follows observations. Requiring the observed graph in first ExecutionDescriptor would make descriptor→observation→graph→descriptor cycle; it is forbidden. EvidenceApplicability/Qualification/Independence/Invalidation use the exact observed graph, not the planned list as proof.
- Reuse experiment_spec/execution_descriptor/execution_result/observation/evidence qualification for interaction (§70), causal/endurance and retained mutation/oracle raw records. Preserve two distinct §68 outcome enums and mandatory oracle 2×2 contrast, qualified activation and independent normalization. Raw method case/results cannot directly establish evidence/coverage. Replay is exact raw-backed bundle manifest + accepted descriptor/observations/current qualification; fresh executor alone proves no independence.
- Reuse invariant_revision for temporal invariant statement; exact model/raw formal specification and fidelity/conformance closure determine derived temporal status. No standalone mutable temporal status or proof transfer. Reuse build_manifest as §123 BuildInputManifest, with separately raw BUILD_PROVENANCE_RECEIPT; no final output self-hash or subject/application identity conflation.
- Existing snapshot is a reproducibility seal only. Channel inventory is a closed snapshot profile of all declared channels and exact prior capture facts with explicit UNKNOWN, never independent enforcement authority. Coverage summaries equality-bind exact obligations/qualifications/cut; effort uses its dedicated complete projection. Report receipt binds raw report/as_of_head/profile/producer after FinalCase; release/export checks keep their original independent gates.
- Source drift, requalification and recovery remain independent exact-cut facts/assessments. Successor campaign only when existing trigger/carry-forward/challenge predicates apply; release-specific changes cannot repair audit basis. No new in-place upgrade or fabricated predecessor qualification.

## 3. Residual-risk/finalization no-omission decisions

Approve the unchanged separate residual-risk proposal. At a represented cut, derive applicable active revision tips from accepted roots and exact predecessor edges. Material and unknown-materiality risk cannot be omitted. Accepted risk requires separate prior approved ApprovalDecision bound to exact assessed tuple and authorized actor/scope; approved risk status alone proves nothing. No new approval kind is needed because Data §157 expressly covers residual acceptance; successor decision_type RESIDUAL_RISK_ACCEPTANCE and exact related-risk/profile authorization must be explicit.

Candidate risk set and STOP risk set each equal the independently recomputed applicable set at their represented cut. A material difference requires fresh Candidate and both challenger roles; historical Candidate does not mutate. Conclusion risk set equals evaluated StopInput risk set after drift/applicability revalidation; PublicStatement and FinalCase equality-bind Conclusion risks, not a caller subset. Approved material residual risks can coexist with PASS only if every original mandatory applicable obligation and challenge/effort/scope predicate is satisfied and pinned policy permits their independent acceptance; READY_WITH_RESIDUAL_RISK additionally requires every release-material risk authorized under release policy. Waiver/risk does not convert an unsatisfied mandatory obligation into SATISFIED.

COMPLETED_LIMITED is condition-dependent authorized bounded/blocked termination, never PASS laundering. Residual risk is required in limited basis when an applicable residual risk contributes to the limitation; otherwise actual exact stage/obligation/unknown/blocker/STOP facts suffice. Early limited termination may legally omit candidate/challengers, but must retain exact non-PASS STOP, bounded/insufficient assurance and explicit basis. Material risk present in conclusion can never disappear from public/final envelope. History corruption permits only external diagnostic, never invented accepted StopEvaluation.

## 4. Proposed complete contracts

### assurance_claim_set/1
Role **DERIVED_PROJECTION**; lifecycle IMMUTABLE; authority: Exact, complete enumeration of accepted finding-claim revisions applicable to the pinned inventory/campaign/source/cut; no truth or assurance verdict
Basis: Data §50, §80; Architecture §31; previously undefined required target D1
**Exact proposed body**
```text
assurance_claim_set_id:ID
scope_inventory_ref:TypedRef
claim_refs:TypedRef[]
claim_set_input_history_cut:HistoryCut
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| scope_inventory_ref | inventory_revision/1 | 1 | PRIOR_ACCEPTED_ONLY |
| claim_refs | finding_claim_revision/1 | 0..65536 | PRIOR_ACCEPTED_ONLY |
| claim_set_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- Include all claim revisions on explicit unsuperseded accepted lineages intersecting inventory scope; include uncertain scope and rejected/unresolved claims, never filter by favorable adjudication.
- Candidate claim_refs equal this set and independently recomputed set; candidate inventory identical; represented cuts equal. Candidate may accept this earlier same-commit derived node; claims themselves must be prior accepted.
- Current adjudications, contradictions, qualifications, mandatory obligations and risks are independently closed in Candidate; absence of claim for unknown scope never reduces denominator.
- No predecessor field: enumeration at a new cut is a new immutable projection; represented tuple is unique, not a mutable current set.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** FACT/ASSESSMENT would misleadingly confer truth to enumeration; SOUND is single-claim qualification not set; snapshot is general capture; inline array removes frozen required reference and duplicates Candidate array.

### clean_control_assessment/1
Role **ASSESSMENT**; lifecycle IMMUTABLE; authority: Exact clean_control_assessment calibration input/assessment, never product completeness
Basis: Data §149 canonical calibration support; E5A calibration→Candidate (Architecture §31)
**Exact proposed body**
```text
assessment_id:ID
finding_claim_revision_ref?:TypedRef
finding_adjudication_ref?:TypedRef
negative_opportunity_ref:TypedRef
outcome:TRUE_NEGATIVE|FALSE_POSITIVE|UNRESOLVED|BLOCKED
rationale_refs:TypedRef[]
assessor_profile_ref:ExternalProfileRef
assessment_input_history_cut:HistoryCut
previous_revision_ref?:TypedRef
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| finding_claim_revision_ref | finding_claim_revision/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| finding_adjudication_ref | finding_adjudication_decision/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| negative_opportunity_ref | negative_opportunity_unit/1 | 1 | PRIOR_ACCEPTED_ONLY |
| rationale_refs | observation/1, evidence_qualification_assessment/1 | 1..65536 | PRIOR_ACCEPTED_ONLY |
| assessment_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| previous_revision_ref | clean_control_assessment/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| assessor_profile_ref | ExternalProfileRef (exact retained/pinned representation) | 1 | HISTORY_CONTEXT_BINDING |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- FALSE_POSITIVE requires independently demonstrated prohibited/false claim on exact clean opportunity; no result by majority/support count.
- Ground truth/assessor profile is an exact prior pin; raw support independently retained and parsed; current corpus/member source and scope equality required.
- Immutable revision and explicit predecessor; full denominator is all eligible units in pinned corpus; unqualified/missing units count unknown, never favorable exclusion.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** Finding claim is tested statement, not ground truth; raw auditor output cannot approve itself; generic corpus membership is not calibration truth or exposure assessment.

### corpus_member_candidate/1
Role **FACT**; lifecycle IMMUTABLE; authority: Exact immutable candidate for later consumer/role admission; no admission authority
Basis: Data §24–26 explicitly names immutable CORPUS_MEMBER_CANDIDATE; registered admission lacks executable reference contract
**Exact proposed body**
```text
member_candidate_id:ID
raw_or_object_revision_ref:MemberRef
producer_stage_ref?:TypedRef
producer_lane_ref?:TypedRef
source_generation_ref:TypedRef
mechanical_validation_assessment_ref?:TypedRef
source_reconciliation_assessment_ref?:TypedRef
historical_role:CorpusRole
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| raw_or_object_revision_ref | legacy_raw_ref/1, snapshot/1, finding_claim_revision/1, final_assurance_case/1 | 1 | CONTENT_OR_PRIOR |
| producer_stage_ref | stage_run/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| producer_lane_ref | lane_run/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| source_generation_ref | source_generation/1 | 1 | PRIOR_ACCEPTED_ONLY |
| mechanical_validation_assessment_ref | legacy_mechanical_validation_assessment/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| source_reconciliation_assessment_ref | source_reconciliation_assessment/1 | 0..1 | PRIOR_ACCEPTED_ONLY |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- MemberRef is exact TypedRef from listed set or durable RawRef under corpus-member transport profile; role is finite §25 enum.
- Source and producer bindings independently checked; candidate cannot contain later admission or CorpusManifest.
- Admission refers this candidate before manifest; new raw/member identity creates new immutable candidate, not an update.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** legacy_raw_ref cannot represent native members; CorpusManifest is aggregate accepted membership and would cycle with admission; raw alone lacks role/producer/source semantics.

### defect_unit/1
Role **FACT**; lifecycle IMMUTABLE; authority: Exact defect_unit calibration input/assessment, never product completeness
Basis: Data §149 canonical calibration support; E5A calibration→Candidate (Architecture §31)
**Exact proposed body**
```text
defect_unit_id:ID
corpus_revision_ref:TypedRef
defect_class:ground-truth profile enum
affected_scope_ref:TypedRef
activation_witness_ref:TypedRef
violated_invariant_ref?:TypedRef
ground_truth_provenance_ref:RawRef
assessment_input_history_cut:HistoryCut
previous_revision_ref?:TypedRef
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| corpus_revision_ref | corpus_manifest/1 | 1 | PRIOR_ACCEPTED_ONLY |
| affected_scope_ref | surface_record/1, invariant_revision/1, scope_state_record/1 | 1 | PRIOR_ACCEPTED_ONLY |
| activation_witness_ref | observation/1 | 1 | PRIOR_ACCEPTED_ONLY |
| violated_invariant_ref | invariant_revision/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| assessment_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| previous_revision_ref | defect_unit/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| ground_truth_provenance_ref | RawRef (exact retained/pinned representation) | 1 | CONTENT_OBJECT |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- Ground truth is independently installation/policy-pinned corpus issuer evidence with known-defect activation, not a claim minted from auditor output; no denominator based on detected findings.
- Ground truth/assessor profile is an exact prior pin; raw support independently retained and parsed; current corpus/member source and scope equality required.
- Immutable revision and explicit predecessor; full denominator is all eligible units in pinned corpus; unqualified/missing units count unknown, never favorable exclusion.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** Finding claim is tested statement, not ground truth; raw auditor output cannot approve itself; generic corpus membership is not calibration truth or exposure assessment.

### discovery_confirmation_assessment/1
Role **ASSESSMENT**; lifecycle IMMUTABLE; authority: Only the named discovery provenance dimension for exact accepted discovery and cut
Basis: Data §57 explicitly requires separate canonical assessments; missing Registry rows and FindingClaimRevision target mismatch
**Exact proposed body**
```text
assessment_id:ID
discovery_ref:TypedRef
assessment_input_history_cut:HistoryCut
previous_assessment_ref?:TypedRef
confirmation_policy_ref:ExternalProfileRef
confirmation_mode:PREREGISTERED|EXPLORATORY|LEGACY_IMPORTED
confirmation_evidence_refs:TypedRef[]
result:CONFIRMED|NOT_CONFIRMED|INCONCLUSIVE|BLOCKED
reason_codes:Code[]
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| discovery_ref | discovery_record/1 | 1 | PRIOR_ACCEPTED_ONLY |
| assessment_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| previous_assessment_ref | discovery_confirmation_assessment/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| confirmation_evidence_refs | evidence_qualification_assessment/1 | 0..65536 | PRIOR_ACCEPTED_ONLY |
| confirmation_policy_ref | ExternalProfileRef (exact retained/pinned representation) | 1 | HISTORY_CONTEXT_BINDING |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- CONFIRMED requires current qualified observation/evidence about the exact discovery; confirmation mode matches accepted experiment chronology; not finding adjudication.
- All profile refs HISTORY_CONTEXT_BINDING; all authority-bearing evidence/corpus refs PRIOR_ACCEPTED_ONLY; all refs backward, no modification of DiscoveryRecord.
- New dimension evidence/corpus/policy creates immutable successor with exact predecessor; no retroactive blind label; result domain is explicit proposed completion where §57 only said result.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** Generic ApprovalDecision is governance, not provenance assessment; DiscoveryRecord is prior observation and cannot contain future assessment; narrative label is not authority.

### discovery_corpus_match_assessment/1
Role **ASSESSMENT**; lifecycle IMMUTABLE; authority: Only the named discovery provenance dimension for exact accepted discovery and cut
Basis: Data §57 explicitly requires separate canonical assessments; missing Registry rows and FindingClaimRevision target mismatch
**Exact proposed body**
```text
assessment_id:ID
discovery_ref:TypedRef
assessment_input_history_cut:HistoryCut
previous_assessment_ref?:TypedRef
corpus_snapshot_ref:TypedRef
match_policy_ref:ExternalProfileRef
matched_prior_claim_refs:TypedRef[]
match_result:MATCH|NO_MATCH|PARTIAL|INCONCLUSIVE
reason_codes:Code[]
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| discovery_ref | discovery_record/1 | 1 | PRIOR_ACCEPTED_ONLY |
| assessment_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| previous_assessment_ref | discovery_corpus_match_assessment/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| corpus_snapshot_ref | corpus_manifest/1 | 1 | PRIOR_ACCEPTED_ONLY |
| matched_prior_claim_refs | finding_claim_revision/1 | 0..65536 | PRIOR_ACCEPTED_ONLY |
| match_policy_ref | ExternalProfileRef (exact retained/pinned representation) | 1 | HISTORY_CONTEXT_BINDING |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- Match set derived from every eligible exact corpus member under pinned matcher; incomplete corpus/search => INCONCLUSIVE; NO_MATCH requires complete declared search; not blind eligibility.
- All profile refs HISTORY_CONTEXT_BINDING; all authority-bearing evidence/corpus refs PRIOR_ACCEPTED_ONLY; all refs backward, no modification of DiscoveryRecord.
- New dimension evidence/corpus/policy creates immutable successor with exact predecessor; no retroactive blind label; result domain is explicit proposed completion where §57 only said result.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** Generic ApprovalDecision is governance, not provenance assessment; DiscoveryRecord is prior observation and cannot contain future assessment; narrative label is not authority.

### discovery_novelty_assessment/1
Role **ASSESSMENT**; lifecycle IMMUTABLE; authority: Only the named discovery provenance dimension for exact accepted discovery and cut
Basis: Data §57 explicitly requires separate canonical assessments; missing Registry rows and FindingClaimRevision target mismatch
**Exact proposed body**
```text
assessment_id:ID
discovery_ref:TypedRef
assessment_input_history_cut:HistoryCut
previous_assessment_ref?:TypedRef
corpus_match_assessment_ref:TypedRef
novelty_policy_ref:ExternalProfileRef
result:NOVEL|PREVIOUSLY_KNOWN|PARTIALLY_NOVEL|INCONCLUSIVE
reason_codes:Code[]
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| discovery_ref | discovery_record/1 | 1 | PRIOR_ACCEPTED_ONLY |
| assessment_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| previous_assessment_ref | discovery_novelty_assessment/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| corpus_match_assessment_ref | discovery_corpus_match_assessment/1 | 1 | PRIOR_ACCEPTED_ONLY |
| novelty_policy_ref | ExternalProfileRef (exact retained/pinned representation) | 1 | HISTORY_CONTEXT_BINDING |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- Same discovery and cut-applicable corpus matching; novelty is scoped relative to disclosed corpus only, not proof of universal novelty.
- All profile refs HISTORY_CONTEXT_BINDING; all authority-bearing evidence/corpus refs PRIOR_ACCEPTED_ONLY; all refs backward, no modification of DiscoveryRecord.
- New dimension evidence/corpus/policy creates immutable successor with exact predecessor; no retroactive blind label; result domain is explicit proposed completion where §57 only said result.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** Generic ApprovalDecision is governance, not provenance assessment; DiscoveryRecord is prior observation and cannot contain future assessment; narrative label is not authority.

### discovery_tool_origin_assessment/1
Role **ASSESSMENT**; lifecycle IMMUTABLE; authority: Only the named discovery provenance dimension for exact accepted discovery and cut
Basis: Data §57 explicitly requires separate canonical assessments; missing Registry rows and FindingClaimRevision target mismatch
**Exact proposed body**
```text
assessment_id:ID
discovery_ref:TypedRef
assessment_input_history_cut:HistoryCut
previous_assessment_ref?:TypedRef
producer_ref:AuthorityRef
method_ref:ExternalProfileRef
tool_profile_ref?:ExternalProfileRef
result:VERIFIED|INCONCLUSIVE|BLOCKED
reason_codes:Code[]
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| discovery_ref | discovery_record/1 | 1 | PRIOR_ACCEPTED_ONLY |
| assessment_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| previous_assessment_ref | discovery_tool_origin_assessment/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| producer_ref | AuthorityRef (exact retained/pinned representation) | 1 | AUTHORIZED_ACTOR_REF |
| method_ref | ExternalProfileRef (exact retained/pinned representation) | 1 | HISTORY_CONTEXT_BINDING |
| tool_profile_ref | ExternalProfileRef (exact retained/pinned representation) | 0..1 | HISTORY_CONTEXT_BINDING |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- Producer/method/tool refs match accepted DiscoveryRecord capture and installation-authorized producer; origin is provenance, never strength/independence.
- All profile refs HISTORY_CONTEXT_BINDING; all authority-bearing evidence/corpus refs PRIOR_ACCEPTED_ONLY; all refs backward, no modification of DiscoveryRecord.
- New dimension evidence/corpus/policy creates immutable successor with exact predecessor; no retroactive blind label; result domain is explicit proposed completion where §57 only said result.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** Generic ApprovalDecision is governance, not provenance assessment; DiscoveryRecord is prior observation and cannot contain future assessment; narrative label is not authority.

### effort_results/1
Role **DERIVED_PROJECTION**; lifecycle IMMUTABLE; authority: Exact replayable effort/saturation calculation inputs, never completeness or STOP authority
Basis: Data §75–76, §141–142; Architecture §32.2/32.5
**Exact proposed body**
```text
effort_results_id:ID
effort_input_history_cut:HistoryCut
effort_profile_ref:ExternalProfileRef
stage_completion_refs:TypedRef[]
execution_result_refs:TypedRef[]
metric_basis_refs:TypedRef[]
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| effort_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| effort_profile_ref | Exact named-purpose ExternalProfileRef; definition below | 1 | HISTORY_CONTEXT_BINDING |
| stage_completion_refs | stage_completion/1 | 0..65536 | PRIOR_ACCEPTED_ONLY |
| execution_result_refs | execution_result/1 | 0..65536 | PRIOR_ACCEPTED_ONLY |
| metric_basis_refs | observation/1, discovery_record/1, root_cause_revision/1, coverage_obligation_qualification/1, challenger_result/1 | 0..65536 | PRIOR_ACCEPTED_ONLY |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- Input sets equal complete applicable histories required by exact EFFORT_PROFILE_V1 at cut; no subset by favorable outcome.
- STOP independently recomputes rounds/method families/budget and saturation from accepted facts; missing duration/workload witness yields INSUFFICIENT_DATA, not zero/default PASS.
- Same profile and cut as StopInput; profiles cannot redefine effort in same commit. Numbers/thresholds remain explicit pinned campaign policy parameters, not universal BDB constants.
- New cut/profile means new immutable projection; deterministic set ordering; no summary scalars as authority.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** unconstrained generic object leaves mandatory effort_results_ref ambiguous; saturation alone is heuristic; snapshot seal alone does not enforce exhaustive effort basis.

### evidence_dependency_graph/1
Role **DERIVED_PROJECTION**; lifecycle IMMUTABLE; authority: Exact reproducible dependency traversal input identity; deleting exported graph cannot change qualification truth
Basis: Data §46–49, §92; Registry dependency_graph_ref/dependency_set_ref
**Exact proposed body**
```text
evidence_dependency_graph_id:ID
root_observation_refs:TypedRef[]
dependency_fact_refs:TypedRef[]
graph_input_history_cut:HistoryCut
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| root_observation_refs | observation/1 | 1..65536 | PRIOR_ACCEPTED_ONLY |
| dependency_fact_refs | observation_dependency/1 | 1..65536 | PRIOR_ACCEPTED_ONLY |
| graph_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- Facts equal full reachable active accepted observation-dependency lineage closure for roots at cut; omission/cycle/cross-context rejection.
- Consumers independently derive node/edge closure and required dependency identities; no hand-picked shared/independent subset.
- DependencyIndependenceAssessment claims must match this graph/root claim/failure assumption; invalidation propagates through exact dependency memberships.
- No stored redundant node/edge summary; explicit fact refs retain exact source authority; new root/cut means new projection.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** snapshot has no exact dependency schema; external graph bytes alone cannot bind accepted fact closure; no new mutable evidence graph authority.

### false_negative_relationship_assessment/1
Role **ASSESSMENT**; lifecycle IMMUTABLE; authority: Only the named discovery provenance dimension for exact accepted discovery and cut
Basis: Data §57 explicitly requires separate canonical assessments; missing Registry rows and FindingClaimRevision target mismatch
**Exact proposed body**
```text
assessment_id:ID
discovery_ref:TypedRef
assessment_input_history_cut:HistoryCut
previous_assessment_ref?:TypedRef
predecessor_stage_or_claim_refs:TypedRef[]
relationship_policy_ref:ExternalProfileRef
result:PREVIOUS_FALSE_NEGATIVE|MULTI_STAGE_FALSE_NEGATIVE|NOT_ESTABLISHED|INCONCLUSIVE
reason_codes:Code[]
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| discovery_ref | discovery_record/1 | 1 | PRIOR_ACCEPTED_ONLY |
| assessment_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| previous_assessment_ref | false_negative_relationship_assessment/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| predecessor_stage_or_claim_refs | stage_completion/1, finding_claim_revision/1 | 1..65536 | PRIOR_ACCEPTED_ONLY |
| relationship_policy_ref | ExternalProfileRef (exact retained/pinned representation) | 1 | HISTORY_CONTEXT_BINDING |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- Prior stage must demonstrably have required applicable obligation/scope and missed exact later-confirmed issue; lack of investigated scope cannot establish previous false negative.
- All profile refs HISTORY_CONTEXT_BINDING; all authority-bearing evidence/corpus refs PRIOR_ACCEPTED_ONLY; all refs backward, no modification of DiscoveryRecord.
- New dimension evidence/corpus/policy creates immutable successor with exact predecessor; no retroactive blind label; result domain is explicit proposed completion where §57 only said result.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** Generic ApprovalDecision is governance, not provenance assessment; DiscoveryRecord is prior observation and cannot contain future assessment; narrative label is not authority.

### fault_spec/1
Role **FACT**; lifecycle IMMUTABLE; authority: Immutable preregistered fault intent; never proof of activation
Basis: Data §41, §44–45; required crash/fault qualification paths
**Exact proposed body**
```text
fault_id:ID
fault_revision:positive integer
previous_fault_ref?:TypedRef
fault_class:profile enum
injection_point:bounded text
activation_predicate_ref:ExternalProfileRef
expected_observable:bounded text
safety_constraints:bounded text[]
cleanup_spec_ref:ExternalProfileRef
fault_input_history_cut:HistoryCut
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| previous_fault_ref | fault_spec/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| fault_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| activation_predicate_ref | Exact named-purpose ExternalProfileRef; definition below | 1 | HISTORY_CONTEXT_BINDING |
| cleanup_spec_ref | Exact named-purpose ExternalProfileRef; definition below | 1 | HISTORY_CONTEXT_BINDING |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- Descriptor experiment references exact prior fault revision; fault run uses same fault and descriptor; actual activation from retained witness only.
- No class transition or safety expansion without new revision; revision number increments along exact predecessor.
- Safety/destructive actions remain separately authorized ApprovalDecision; this intent grants no live authority.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** FaultRunRecord is later observation, cannot be own preregistration; generic method label cannot identify exact fault predicate.

### finding_defect_match_assessment/1
Role **ASSESSMENT**; lifecycle IMMUTABLE; authority: Exact finding_defect_match_assessment calibration input/assessment, never product completeness
Basis: Data §149 canonical calibration support; E5A calibration→Candidate (Architecture §31)
**Exact proposed body**
```text
assessment_id:ID
finding_claim_revision_ref:TypedRef
finding_adjudication_ref?:TypedRef
defect_unit_ref:TypedRef
match_result:MATCH|NO_MATCH|PARTIAL|UNRESOLVED
rationale_refs:TypedRef[]
assessor_profile_ref:ExternalProfileRef
assessment_input_history_cut:HistoryCut
previous_revision_ref?:TypedRef
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| finding_claim_revision_ref | finding_claim_revision/1 | 1 | PRIOR_ACCEPTED_ONLY |
| finding_adjudication_ref | finding_adjudication_decision/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| defect_unit_ref | defect_unit/1 | 1 | PRIOR_ACCEPTED_ONLY |
| rationale_refs | observation/1, evidence_qualification_assessment/1 | 1..65536 | PRIOR_ACCEPTED_ONLY |
| assessment_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| previous_revision_ref | finding_defect_match_assessment/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| assessor_profile_ref | ExternalProfileRef (exact retained/pinned representation) | 1 | HISTORY_CONTEXT_BINDING |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- Exact claim/adjudication pair and unit scope; unseeded real finding is not false positive merely absent from seeded units; partial match is not full detection.
- Ground truth/assessor profile is an exact prior pin; raw support independently retained and parsed; current corpus/member source and scope equality required.
- Immutable revision and explicit predecessor; full denominator is all eligible units in pinned corpus; unqualified/missing units count unknown, never favorable exclusion.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** Finding claim is tested statement, not ground truth; raw auditor output cannot approve itself; generic corpus membership is not calibration truth or exposure assessment.

### gate_decision/1
Role **DECISION**; lifecycle IMMUTABLE; authority: Exact cut-bound eligibility decision for proposed guarded transition/view; not owner approval or delivery proof
Basis: Data §87–88; checkpoint resume/reveal eligibility
**Exact proposed body**
```text
gate_decision_id:ID
campaign_id:CampaignID
stage_run_ref:TypedRef
attempt_ref:TypedRef
gate_policy_ref:ExternalProfileRef
input_history_cut:HistoryCut
checkpoint_ref:TypedRef
knowledge_state_ref:TypedRef
requested_view_ref:TypedRef
eligibility_result:ALLOW|DENY|UNKNOWN
reason_codes:Code[]
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| stage_run_ref | stage_run/1 | 1 | PRIOR_ACCEPTED_ONLY |
| attempt_ref | attempt/1 | 1 | PRIOR_ACCEPTED_ONLY |
| input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| checkpoint_ref | checkpoint/1 | 1 | PRIOR_ACCEPTED_ONLY |
| knowledge_state_ref | knowledge_state/1 | 1 | PRIOR_ACCEPTED_ONLY |
| requested_view_ref | view_manifest/1 | 1 | PRIOR_ACCEPTED_ONLY |
| gate_policy_ref | ExternalProfileRef (exact retained/pinned representation) | 1 | HISTORY_CONTEXT_BINDING |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- Policy is exact prior HISTORY_CONTEXT_BINDING; scope/campaign/stage/attempt/checkpoint/knowledge/view match; input head must remain current when consumed.
- ALLOW requires every original checkpoint/FSM/isolation/knowledge/positive-view predicate; UNKNOWN never authorizes exposure.
- GateDecision may be earlier content in the same atomic guarded-transition closure. Proposal has no independent issue/consume authority; its parent equals current command parent. A prior gate cannot authorize changed inputs: recompute gate on current cut and produce fresh decision when represented inputs/cut differ; full CAS revalidation applies.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** ApprovalDecision is human/governance authorization with different meaning; CommandReceipt is post-acceptance acknowledgment; neither replaces gate eligibility.

### handoff_validation_result/1
Role **ASSESSMENT**; lifecycle IMMUTABLE; authority: Exact transport/source/run/checkpoint/cut assessment of retained handoff; no reveal or knowledge authority
Basis: Data §86–88; checkpoint/handoff recovery admission
**Exact proposed body**
```text
handoff_validation_result_id:ID
handoff_ref:RawRef
contract_ref:ExternalProfileRef
transport_integrity_result:PASS|FAIL|UNKNOWN
schema_results:LayerResult[]
source_binding_result:PASS|FAIL|UNKNOWN
run_attempt_binding_result:PASS|FAIL|UNKNOWN
checkpoint_result:PASS|FAIL|UNKNOWN
history_cut_result:PASS|FAIL|UNKNOWN
overall_status:PASS|FAIL|BLOCKED
input_history_cut:HistoryCut
reason_codes:Code[]
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| handoff_ref | Exact RawRef | 1 | CONTENT_OBJECT |
| contract_ref | ExternalProfileRef (exact retained/pinned representation) | 1 | HISTORY_CONTEXT_BINDING |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- Trusted validator reads retained handoff bytes under exact prior transport/schema/context; all component PASS required for overall PASS.
- Embedded canonical references are checked against accepted campaign/source/attempt/cut independently; raw assertions alone cannot establish authority.
- Distinct raw or cut gives immutable new assessment; no claim of future transition or delivery acceptance.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** Generic ValidationResult lacks all named required binding axes; NF02 AdmissionEvidence establishes lane result provenance, not checkpoint handoff semantics.

### holdout_exposure_assessment/1
Role **ASSESSMENT**; lifecycle IMMUTABLE; authority: Exact holdout_exposure_assessment calibration input/assessment, never product completeness
Basis: Data §149 canonical calibration support; E5A calibration→Candidate (Architecture §31)
**Exact proposed body**
```text
assessment_id:ID
corpus_revision_ref:TypedRef
evaluator_or_executor_profile_ref:TypedRef
exposure_state:UNSEEN|POTENTIALLY_EXPOSED|EXPOSED|UNKNOWN
exposure_input_history_cut:HistoryCut
previous_assessment_ref?:TypedRef
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| corpus_revision_ref | corpus_manifest/1 | 1 | PRIOR_ACCEPTED_ONLY |
| evaluator_or_executor_profile_ref | executor_spec/1 | 1 | HISTORY_CONTEXT_BINDING |
| exposure_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| previous_assessment_ref | holdout_exposure_assessment/1 | 0..1 | PRIOR_ACCEPTED_ONLY |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- UNSEEN requires complete grant/potential-exposure/knowledge closure for exact evaluation path; after possible exposure never revert UNSEEN by new ID/session absent separately qualified isolation path.
- Ground truth/assessor profile is an exact prior pin; raw support independently retained and parsed; current corpus/member source and scope equality required.
- Immutable revision and explicit predecessor; full denominator is all eligible units in pinned corpus; unqualified/missing units count unknown, never favorable exclusion.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** Finding claim is tested statement, not ground truth; raw auditor output cannot approve itself; generic corpus membership is not calibration truth or exposure assessment.

### negative_opportunity_unit/1
Role **FACT**; lifecycle IMMUTABLE; authority: Exact negative_opportunity_unit calibration input/assessment, never product completeness
Basis: Data §149 canonical calibration support; E5A calibration→Candidate (Architecture §31)
**Exact proposed body**
```text
negative_opportunity_id:ID
corpus_revision_ref:TypedRef
benign_scenario_ref:TypedRef
prohibited_or_false_claim_scope:TypedRef[]
ground_truth_provenance_ref:RawRef
assessment_input_history_cut:HistoryCut
previous_revision_ref?:TypedRef
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| corpus_revision_ref | corpus_manifest/1 | 1 | PRIOR_ACCEPTED_ONLY |
| benign_scenario_ref | experiment_spec/1 | 1 | PRIOR_ACCEPTED_ONLY |
| prohibited_or_false_claim_scope | surface_record/1, invariant_revision/1, scope_state_record/1 | 1..65536 | PRIOR_ACCEPTED_ONLY |
| assessment_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| previous_revision_ref | negative_opportunity_unit/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| ground_truth_provenance_ref | RawRef (exact retained/pinned representation) | 1 | CONTENT_OBJECT |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- Independently pinned benign opportunity and exact prohibited claim scope; denominator includes each declared opportunity, not only reported negatives.
- Ground truth/assessor profile is an exact prior pin; raw support independently retained and parsed; current corpus/member source and scope equality required.
- Immutable revision and explicit predecessor; full denominator is all eligible units in pinned corpus; unqualified/missing units count unknown, never favorable exclusion.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** Finding claim is tested statement, not ground truth; raw auditor output cannot approve itself; generic corpus membership is not calibration truth or exposure assessment.

### observation_dependency/1
Role **FACT**; lifecycle IMMUTABLE; authority: Observed/declared exact dependency relationship of an observation path, not independence judgment
Basis: Data §33, §46, §49, §121; Architecture §22.1
**Exact proposed body**
```text
observation_dependency_id:ID
observation_ref:TypedRef
dependency_refs:DependencyRef[]
dependency_input_history_cut:HistoryCut
basis_observation_refs:TypedRef[]
previous_dependency_ref?:TypedRef
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| observation_ref | observation/1 | 1 | PRIOR_ACCEPTED_ONLY |
| dependency_refs | environment_record/1, execution_descriptor/1, source_generation/1 | 1..65536 | PRIOR_ACCEPTED_ONLY |
| basis_observation_refs | observation/1 | 1..65536 | PRIOR_ACCEPTED_ONLY |
| dependency_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| previous_dependency_ref | observation_dependency/1 | 0..1 | PRIOR_ACCEPTED_ONLY |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- DependencyRef is closed tagged union of the finite typed targets above, retained RawRef (fixture/module/observer bytes) or pinned ExternalProfileRef (harness/oracle/parser/cache/process profile); tags and full identity sorted, duplicate rejected.
- Each dependency is matched to exact ExecutionDescriptor/Environment and capture observations; unknown capture cannot assert absence of dependency; no future ExecutionResult.
- Dependency changes create explicit successor fact; all graph inputs remain reconstructible from these accepted facts.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** Raw declaration alone cannot replace canonical ObservationDependency facts explicitly required by §46; graph export is projection, not dependency fact; independence assessment has separate meaning.

### public_conclusion_statement/1
Role **DERIVED_PROJECTION**; lifecycle IMMUTABLE; authority: Retained exact public bytes communicating a prior canonical conclusion; no new assurance/release authorization
Basis: Data §76, §80, §81, §118–119; Architecture §§31–32; undefined target D2
**Exact proposed body**
```text
public_conclusion_statement_id:ID
campaign_conclusion_ref:TypedRef
statement_input_history_cut:HistoryCut
render_profile_ref:ExternalProfileRef
statement_raw_ref:RawRef
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| campaign_conclusion_ref | campaign_conclusion/1 | 1 | PRIOR_ACCEPTED_ONLY |
| statement_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| render_profile_ref | Exact named-purpose ExternalProfileRef; definition below | 1 | PINNED_PROFILE_REF |
| statement_raw_ref | Exact RawRef | 1 | CONTENT_OBJECT |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- Raw bytes equal deterministic public renderer of exact Conclusion→STOP→StopInput closure under proposed PUBLIC_CONCLUSION_RENDER_V1; validation independently reads retained bytes.
- Renderer discloses all exact residual-risk refs and bounded/limited state, exact scope/source, STOP axes and conclusion; no arbitrary caller narrative or PASS/READY synonym.
- Statement cut contains conclusion and its entire authority closure; acceptance rejects intervening audit-basis drift. FinalCase refers prior accepted statement for same exact conclusion.
- No FinalCase or ReleaseQualification future ref; STOP release axis labelled assessment only, release authorization not established here.
- One deterministic rendering per conclusion/profile; repacking/replacement raw conflicts; new public representation is new immutable projection, never conclusion revision.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** General report_export_receipt requires a final report with future FinalCase (§81), causing a cycle; RawRef alone lacks semantic prior-acceptance binding; FACT would create competing truth; EXPORT bytes stay raw while typed semantic wrapper uses ObjectDigest.

Unchanged separate complete recommendation: [Residual Risk proposal](R5_4_2_RESIDUAL_RISK_CONTRACT_DECISION_PROPOSAL.md). ASSESSMENT, immutable explicit revisions; existing approval_decision/1 remains separate authorized acceptance. Raw identity: `696dfeaf883462aed4c95b81820d95ad87cc7177ed6edf1bb99fd1f30888b66b`. Its historical SPEC_CONFLICT describes the previous scoped pass; this consolidated pass supersedes that analysis stop, not its proposed semantics.

### state_model/1
Role **FACT**; lifecycle IMMUTABLE; authority: Exact immutable model/mapping/assumption revision; no implementation proof
Basis: Data §71–72; mandatory E4 fidelity/conformance
**Exact proposed body**
```text
state_model_id:ID
model_revision:positive integer
previous_model_ref?:TypedRef
implementation_mapping_ref:RawRef
source_generation_ref:TypedRef
scope_refs:TypedRef[]
model_artifact_ref:RawRef
model_profile_ref:ExternalProfileRef
model_input_history_cut:HistoryCut
```
**Material references**
| Field | Target kind/version(s) | Cardinality | Class |
| --- | --- | --- | --- |
| previous_model_ref | state_model/1 | 0..1 | PRIOR_ACCEPTED_ONLY |
| source_generation_ref | source_generation/1 | 1 | PRIOR_ACCEPTED_ONLY |
| scope_refs | surface_record/1, invariant_revision/1, scope_state_record/1 | 1..65536 | PRIOR_ACCEPTED_ONLY |
| model_input_history_cut | history_cut/1 | 1 | HISTORY_INPUT |
| implementation_mapping_ref | Exact RawRef | 1 | CONTENT_OBJECT |
| model_artifact_ref | Exact RawRef | 1 | CONTENT_OBJECT |
| model_profile_ref | Exact named-purpose ExternalProfileRef; definition below | 1 | HISTORY_CONTEXT_BINDING |

All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:
- MODEL_ARTIFACT_V1 raw contract requires finite state variables/domains, transitions, initial/forbidden states, abstraction assumptions, bounds, omitted states and fairness/time assumptions (§71).
- Mapping raw contains closed map of model symbols to exact source anchors; profile supplies grammar and checker; all members exact retained bytes.
- Fidelity independently reads model/mapping and exact implementation anchors; MODEL_VERIFIED alone never qualifies implementation obligation.
- Scope/source/model changes create explicit new revision; no future fidelity reference.

Producer/validation/uniqueness/revision/consumer/migration: TRUSTED_COORDINATOR_ACCEPTANCE; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.

**Alternatives rejected:** ModelFidelityAssessment is later judgment about model, not model itself; raw bytes alone lack exact scope/source/revision binding.


## 4a. Explicit body completions for existing underspecified rows

### observation/1

Closed proposed body:

```text
observation_id:ID
execution_descriptor_ref:TypedRef
observation_raw_ref:RawRef
capture_profile_ref:ExternalProfileRef
observation_kind:START|FINISH|MEASUREMENT|ACTIVATION|CLEANUP|RESET|CHANNEL_CAPTURE|EXTERNAL_WITNESS
```

Descriptor prior accepted before controlled capture; exact raw/profile independently read. Kind describes observation category, not PASS or truth. Times only informational in retained raw; no future ExecutionResult. External witness capture also has declared descriptor/runner context.

### cleanup_result/1

Closed proposed body:

```text
cleanup_result_id:ID
execution_descriptor_ref:TypedRef
cleanup_observation_refs:TypedRef[]
cleanup_spec_ref:ExternalProfileRef
result:VERIFIED|FAILED|UNKNOWN|BLOCKED
```

Prior descriptor/capture observations and exact planned cleanup predicate; VERIFIED requires all required cleanup checks with retained evidence. Does not establish future ExecutionResult.

### snapshot/1

Closed proposed body:

```text
snapshot_id:ID
as_of_head:AcceptedHead
projection_profile_ref:ExternalProfileRef
projection_code_ref:RawRef
projection_input_refs:TypedRef[]
projection_payload:ClosedPurposePayload
```

Exact accepted cut and deterministic independently replayed payload of named STOP_INPUT/COVERAGE_SUMMARY/CHANNEL_INVENTORY/RUN_STATE purpose; stale mismatch rejects; profile defines required fields and derives all summaries from exact refs, never alternative head.

### validation_result/1

Closed proposed body:

```text
validation_id:ID
target_ref:TargetRef
contract_ref:ExternalProfileRef
validation_layers:LayerResult[]
overall_status:PASS|FAIL|BLOCKED
reason_codes:Code[]
validator_profile_ref:ExternalProfileRef
input_history_cut?:HistoryCut
```

TargetRef exact finite active typed key or retained RawRef; full applicable contract layers must PASS; cannot establish authenticity/truth outside checked predicates. Cut mandatory for history-dependent target; absent only installation/raw syntactic validation.

### report_export_receipt/1

Closed proposed body:

```text
report_artifact_ref:RawRef
report_as_of_head:AcceptedHead
report_contract_ref:ExternalProfileRef
producer_revision_ref:RawRef
```

External exact retained export metadata; raw bytes derived from accepted final chain. Receipt outside report raw preimage; it does not authorize campaign conclusion. Same raw/head/profile receipt retry is exact; substitution conflicts.

### artifact_hash_manifest/1

Closed proposed body:

```text
hash_manifest_artifact_ref:RawRef
bundle_manifest_ref:TypedRef
export_as_of_head:AcceptedHead
hash_manifest_profile_ref:ExternalProfileRef
```

Registered EXPORT family gets closed semantic descriptor pointing to actual ARTIFACT_HASHES.sha256 raw bytes; exact path/digest sorted raw list excludes itself, equality-checks full BundleManifest membership before semantic parsing. Descriptor ObjectDigest is distinct from raw list RawDigest; no new outcome authority. This descriptor interpretation is explicit proposed successor clarification, not existing bytes rewritten.

### standalone_payload_manifest/1

Closed proposed body:

```text
payload_manifest_id:ID
build_input_manifest_ref:TypedRef
embedded_components:ComponentEntry[]
runtime_profile_ref:ExternalProfileRef
```

ComponentEntry closed {member_path,raw_ref,component_role}; role CODE|SCHEMA|SPEC|PROMPT|FIXTURE; exact unique sorted paths and full declared build-input membership; no final distributed artifact hash in embedded body.

### isolation_baseline_profile/1

Closed proposed body:

```text
isolation_baseline_profile_id:ID
channels:ChannelRule[]
guarantee_boundary:bounded text
```

ChannelRule closed {channel,required_control,witness,unknown_handling}; channel domain is exact ten-channel Registry baseline, unknown_handling=UNKNOWN_NOT_ENFORCED; does not assert actual enforcement. Exact installation/profile pin precedes referring assessment.

These are owner decisions on previously schema-deferred bodies, not generator discretion. LayerResult is closed {layer:L1|L2|L3|L4|L5|L6|L7,result:PASS|FAIL|UNKNOWN,reason_codes:Code[]}; Handoff schema_results use closed {schema_key,schema_raw_digest,result:PASS|FAIL|UNKNOWN,reason_codes:Code[]}. Codes match `[A-Z][A-Z0-9_]{0,127}`. Component/Channel structures have only listed fields; no arbitrary extension dict.

Snapshot ClosedPurposePayload is discriminated {purpose,data}. STOP_INPUT data is {direct_input_refs,invalidated_refs,unknown_refs,blocked_refs}, exact sorted typed-ref sets independently derived at sealed cut, with direct_input_refs equal all direct authority refs in the consuming StopInput (profiles checked by cut). COVERAGE_SUMMARY data is {obligation_refs,qualification_refs,unresolved_obligation_refs}, with exact Candidate equality; counts are computed, never stored as authority. CHANNEL_INVENTORY data is {attempt_ref,executor_spec_ref,delivery_spec_ref,channels}; each entry is {channel,witness_refs,state}, exact ten-channel domain from predecessor Registry, state WITNESSED|DECLARED|UNKNOWN, witnesses exact prior observation/tool/execution refs. RUN_STATE data is {entity_states}; each entry {entity_ref,state} uses exact prior stage_run/lane_run/attempt/genesis ref and corresponding original closed FSM enum, deterministically replayed from accepted transitions. Each list is complete for its purpose and cut; unknown or duplicate element fails closed. None points forward to consuming StopInput or asserts independent enforcement/truth.

Other registered unbound bodies retain the exact complete Data section's field/enum list (included verbatim per node in graph), with all ref representations/types supplied by proposed material-ref completion and body-field catalog. Optional/cardinality/shape choices cannot be inferred later from Python producers. A contradictory qualified schema requires an explicit successor correction and vector, not retroactive legalization.


## 5. Exact external profile and raw-contract semantics

### FULL_PATH_SEMANTIC_V1

Offline L1 transport/resource, L2 raw integrity, L3 closed exact schema, L4 finite typed refs/history, L5 producer/source/FSM, L6 epistemic/applicability/isolation, L7 exhaustive obligations/finalization. All are conjunctions; missing proof rejects with no canonical mutation.

### PUBLIC_CONCLUSION_RENDER_V1

Canonical UTF-8 JSON with fields campaign_ref,source_generation_ref,conclusion_ref,stop_evaluation_ref,scope_inventory_ref nullable,termination_state,assurance_level,continuation_decision,stop_release_assessment,residual_risks,limited_basis_refs,bounded_statement. Risks include exact ref, description, reason_unresolved, disposition, materiality; redact only sensitive basis, never presence/status. No arbitrary narrative, release authorization, generated PASS alias or future FinalCase ref. Text rendering, if exported, is deterministic static-label rendering of this JSON.

### CLAIM_SET_CLOSURE_V1

C(c,inventory) = all exact unsuperseded claim-lineage tips accepted in same campaign/source, intersecting accepted inventory surface/scope or with unresolved applicability. Retain rejected/unknown claims; assess separately. Fork/conflicting tip blocks selection. Candidate set equals C and its current adjudication map at represented cut; omit missing adjudication only by marking unresolved, which blocks required finalization.

### DEPENDENCY_CLOSURE_V1

Full accepted observation dependency closure at represented cut, with exact tagged TypedRef/RawRef/ExternalProfileRef nodes, canonical sorting and explicit common-cause assumptions; no dependency assertion from missing capture.

### EFFORT_PROFILE_V1

Closed versioned policy with required stages, method-family identifiers, rounds/budget requirements per stage, exact counting predicate revisions and required metric witness classes. Values are explicit positive bounded campaign-policy inputs; absence => INSUFFICIENT_DATA. Source values derive pinned E0; no schema/backend default can choose values. EffortResults closure deterministically enumerates accepted stage/execution/metric facts, no saturation-as-completeness.

### FULL_FINALIZATION_PROFILE_V1

Exact risk equality Candidate/STOP/conclusion/public/final for represented applicable cuts; all claims/obligations/adjudications/contradictions/evidence closed. Material drift requires fresh candidate and both challengers; conclude/final/release guards retain §76/§80 precedence. Separate authorized approval never turns waived mandatory obligation into satisfied.

### CHANNEL_CAPTURE_PROFILE_V1

snapshot/1 is exact channel inventory projection of prior ExecutorSpec/DeliverySpec/isolation baseline and capture observations, with all ten baseline channels, witness/UNKNOWN per channel; accepted raw observations provide capture facts. Snapshots cannot assert enforcement by themselves.

### REPORT_EXPORT_PROFILE_V1

Final technical report after FinalCase; exact accepted closure and optional prior ReleaseQualification, deterministic disclosure/no-upgrade. report_export_receipt binds exact RawRef/as_of_head/profile/producer outside raw preimage; final bundle includes exact typed refs and RawDigest membership, excludes own hash manifest self entry.

### INSTALLATION_FULL_PATH_PROFILE_V1

New exact revision of installation_bootstrap_profile/1 retaining eight pins plus externally approved qualified full-path schema and profile closure. Namespace authorized before bootstrap, never runtime-generated from cwd. Finite active set includes all graph nodes, excludes historical schema_registry/1 and external governance documents from campaign writes.

### MODEL_ARTIFACT_V1

Closed finite model JSON: variable definitions and finite domains, transitions with typed source anchors, initial/forbidden predicates, abstraction assumptions,bounds,omitted states,fairness/time assumptions; exact raw checker/grammar profile. Mapping to prior source anchors validated independently; no implementation assurance from model proof alone.

### GATE_ELIGIBILITY_PROFILE_V1

GateDecision is pure policy/FSM/checkpoint/knowledge/positive-view eligibility on exact prior head; ALLOW only all conditions established, DENY for violated condition, UNKNOWN for unverified mandatory input. It grants no independent human approval or future authority.

### CALIBRATION_GROUND_TRUTH_PROFILE_V1

Exact retained corpus issuer evidence authorized before auditor execution through installation/policy trust boundary. Defect and benign units have complete known activation/scope/provenance; all units count in denominators; unknown units remain unqualified. No source of truth derived from tested auditor output or majority.

### FULL_PATH_CONTEXT_PARAMETERS_V1

Closed exact prior pin for named stage/lane/executor/delivery/collector/method/confirmation/matching/novelty/relationship/assessor/model/fault/release/effort/recovery contexts. Per-purpose entries carry finite input target set, deterministic predicate revision and bounds, required witness classes, enum domains, authorized issuer/scope and unknown handling. Campaign-selected numeric effort/method/resource values are data constrained by approved policy, not authority to rewrite predicates. Missing required entry forbids that path; no latest/generated equivalent or profile overlay. Runtime code/harness/fixture revisions are retained RawRefs, not self-issued trust identities.

### EXECUTION_DEPENDENCY_PLAN_V1

Exact pinned closed dependency list for ExperimentSpec/Environment/ExecutionDescriptor before execution: source/module RawRefs, harness/oracle/runner ExternalProfileRefs, fixture RawRefs and versioned resource bounds. It is planned context, not observed dependency facts or independence. Observed EvidenceDependencyGraph is constructed AFTER observations; mandatory pre-execution graph refs would create a cycle and are forbidden.

### RECOVERY_REFERENCE_PROFILE_V1

Canonical history + immutable raw vault reconstruct selectors. Atomic accepted closure/commit/head/receipt or none; CAS full expected head; external anchor only for declared profile; scratch/cache/projections not authority. Terminal-vs-delivery check serialized before external export.

### REPLAY_CAPSULE_V1

Basis: Data §65–66. Closed raw body fields: `finding_or_claim_revision_ref, subject_baseline_ref, environment_profile_ref, dependency_set_ref, harness_ref, fixture_refs, seed_ref optional, generator_profile_ref, command_spec, expected_invariant_ref, expected_observable, observer_requirements, cleanup_spec, producer_ref, artifact_raw_refs`. Exact immutable bundle RawRef + bundle_manifest/1; accepted descriptor and observation point to retained capsule. Current evidence/applicability/independence assessments, not capsule, establish replay support.

### IMPLEMENTATION_MUTATION_CASE_V1

Basis: Data §67–68. Closed raw body fields: `mutation_id, mutation_revision, target_claim_or_invariant_ref, target_location, activation_predicate, expected_detector_or_observer, positive_control_ref, negative_control_ref, clean_target_ref, known_defective_target_ref`. Preregistered experiment_spec/1 references exact case RawRef; execution_result/1 plus retained observation payload uses exact ImplementationMutationOutcome enum from §68; EvidenceQualification independently derives activation/detection and obligation effect.

### ORACLE_CHALLENGE_CASE_V1

Basis: Data §67–68; Architecture §31. Closed raw body fields: `mutation_id, mutation_revision, target_claim_or_invariant_ref, target_location, activation_predicate, expected_detector_or_observer, positive_control_ref, negative_control_ref, clean_target_ref, known_defective_target_ref, strong_oracle_ref, weakened_oracle_ref`. Preregistered experiment_spec/1 references exact case RawRef; retained observations bind all 4 clean/defective × strong/weakened execution descriptors, actual activation and exact §68 OracleChallengeOutcome. Validator recomputes outcome; clean PASS alone cannot establish WEAKENING_DETECTED.

### TEMPORAL_MODEL_CLAIM_V1

Basis: Data §72. Closed raw body fields: `model_revision_ref, invariant_revision_ref, implementation_scope_refs, assumptions, bounds`. Represent statement with existing invariant_revision/1 + exact retained formal specification RawRef. PROPOSED/MODEL_VERIFIED/IMPLEMENTATION_CONFORMANCE_QUALIFIED/VIOLATED/BLOCKED are derived states of exact execution/evidence/fidelity facts; no standalone status mutation.

### CAUSAL_CHAIN_V1

Basis: Data §73. Closed raw body fields: `trigger, state_transition_refs, observation_refs, impact_ref, scope, evidence_qualification_refs`. Typed traversal in raw observation or derived snapshot; each exact step is independently accepted provenance. No evidence transfer through similarity.

### ENDURANCE_OBSERVATION_V1

Basis: Data §74. Closed raw body fields: `duration_workload_profile_ref, environment_ref, resource_baselines, monitoring_path_refs, stop_abort_reason, observation_refs`. Existing execution_descriptor/result and retained observation payload; coverage requires workload and observer completeness, never nominal elapsed duration alone.

### BUILD_PROVENANCE_RECEIPT_V1

Basis: Data §123–124. Closed raw body fields: `build_input_manifest_ref, final_output_raw_ref, build_environment_ref, verification_refs`. External raw receipt binds existing build_manifest/1 as exact build-input identity; no output hash embedded in its own bytes; build/install governance validates full closure.

Every new profile has a semantic identity above but **no approved bytes/digest yet**. Future exact ExternalProfileRef is profile_id + RawDigest(frozen bytes), installed/pinned before use, with full interpreter/checker/renderer dependency closure. Existing 13 exact predecessor profiles are preserved in graph with raw hashes; successor cannot simply reuse pins whose Registry/schema/policy dependencies changed. Unknown profile purpose/entry fails closed. Arbitrary deployment secrets/actor identifiers/actual campaign numeric budgets are installation/campaign inputs constrained by these contracts, not unanswered choices about canonical meaning. They cannot redefine enum/predicate/ref classes.

## 6. Reference targets and vectors

| Class | Actual target kind/version(s) |
| --- | --- |
| typed_scope_ref | surface_record/1, surface_key/1, invariant_revision/1, finding_claim_revision/1, coverage_obligation/1, scope_state_record/1 |
| materiality_subject_ref | surface_record/1, surface_key/1, invariant_revision/1, scope_state_record/1 |
| residual_risk_ref | residual_risk/1 |
| assurance_claim_set_ref | assurance_claim_set/1 |
| public_conclusion_statement_ref | public_conclusion_statement/1 |
| finding_or_risk_ref | finding_claim_revision/1, finding_adjudication_decision/1, residual_risk/1 |
| limited_conclusion_basis_ref | stage_completion/1, coverage_obligation/1, coverage_obligation_qualification/1, evidence_invalidation/1, contradiction_revision/1, residual_risk/1, stop_evaluation/1, approval_decision/1 |
| dependency_graph_ref | evidence_dependency_graph/1 |
| scope_decision_ref | approval_decision/1 |
| control_ref | experiment_spec/1 |
| coverage_obligation_summary_ref | snapshot/1 |
| release_reassessment_input_ref | approval_decision/1, residual_risk/1, evidence_applicability_assessment/1, evidence_qualification_assessment/1, evidence_invalidation/1, source_drift_record/1, source_drift_impact_assessment/1, observation/1, environment_record/1, policy_revision/1 |
| application_generation_ref | build_manifest/1 |
| schema_set_ref | schema_registry/2 |
| protocol_policy_bundle_ref | Exact ExternalProfileRef to qualified protocol/policy bundle; no canonical invented bundle kind |
| campaign_ref | campaign_genesis/1, successor_campaign_genesis/1 |
| assigned_input_ref | source_manifest/1, legacy_raw_ref/1, surface_collector_record/1 |

Per-field class/cardinality/prior/same-commit rules are in exact graph edges/contracts; named noncanonical target representations are explicit in graph. Scope exclusion ApprovalDecision must be authorized SCOPE_EXCLUSION with exact scope related_ref; generic approval does not become obligation applicability. Control intent is exact experiment_spec; control execution/qualification is separately execution_result/evidence qualification.

Vector designs: 182 cases, including every requested CLAIM_SET/PUBLIC_CONCLUSION/RESIDUAL_RISK case and registered/schema/substitution/stale/basis/cross-campaign/CAS negatives for all 21 kinds. NOT EXECUTED; future canonical negatives compare `accepted_head, commit_count, event_sequence, immutable_object_count, command_index, receipt_index, binding_selector, result_slot_selector, accepted_raw_references` and require no mutation. Each new contract also needs positive retry, concurrent competing bodies and crash/restart reconstruction tests before runtime qualification. Current design static verification is not those tests.

## 7. Candidate materialization delta plan

| Future file/family | Decision | Reason |
| --- | --- | --- |
| BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md | CHANGE REQUIRED | 21 new exact contracts; all proposed body/ref completions; role-vs-digest clarification; finite targets; public order and risk no-omission. |
| BDB_AUDIT_V2_ARCHITECTURE_SPEC_R5_4.md | CHANGE REQUIRED | Dependency intent/observed distinction; corpus/discovery/calibration complete DAG; Conclusion→PublicStatement→FinalCase order and independent derivation. |
| BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json | CHANGE REQUIRED | 21 proposed rows, 110 exact active keys, target maps and explicit schema-deferred material refs; correct discovery_relation_refs mismatch; preserve role domains. |
| objects/schema_registry__2.json | CHANGE REQUIRED | 131 exact required keys with future frozen executable raw refs; no guessed digest or runtime-generated authority. |
| SCHEMA_ARTIFACT_CATALOG_R5_4.json + schemas/ | CHANGE REQUIRED | 92 currently missing bindings; executable bytes generated after owner decision; regenerate any of existing 39 whose approved exact semantics change. 39 existing bindings are evidence only, not automatic successor reuse. |
| BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json | CHANGE REQUIRED | Materialize proposed positive/negative vectors only later; retain previous expected failure intent; add closure/discovery/calibration/gate cases. |
| BDB_AUDIT_V2_TEST_AND_SELF_AUDIT_PLAN_R5_4.md | CHANGE REQUIRED | Mandatory semantic closure audit, 131-key schema parity, no-omission/false-public-pass tests and full crash/CAS/restart/old-campaign runtime families. |
| BDB_AUDIT_V2_IMPLEMENTATION_ROADMAP_R5_4.md | CHANGE REQUIRED | Q1/Q2 prerequisites now full declared path; M42–M44 include all new contracts and no premature NF02 closure. |
| BDB_Audit_vNext_Szczegolowy_Plan_Rozwoju.md + successor execution plan | CHANGE REQUIRED | Separate owner approval→materialization→fresh Q1→Q2→N5–N11 gates and contract-to-runtime dependencies. |
| INSTALLATION_PIN_BUNDLE_R5_4.json + objects/installation_bootstrap_profile__1.json + profiles/bootstrap | CHANGE REQUIRED | New authorized installation revision, namespace and full-path exact pins. Preserve eight pins and first-history command/union-DAG semantics; no in-place upgrade. |
| profiles/finalization + profiles/report_export + proposed external profiles | CHANGE REQUIRED | Freeze all semantic profile definitions, renderer and validator/code dependency identity; raw method/model/calibration profiles as declared in graph. |
| successor manifest/governance/readback/self-audit tooling | CHANGE REQUIRED | Transitively inventory all future files/profiles/schemas; external authorized fresh qualification record and immutable provenance, no self-certifying candidate. |
| ADR-006_CANONICAL_SERIALIZATION_AND_IDENTITY_PROFILE.md | NO CHANGE | BDB-CJSON-1/RawDigest/ObjectDigest algorithms retained; role alone does not select digest domain. Clarification belongs in Data/Registry row contracts. |
| BDB_AUDIT_V1_TO_V2_MIGRATION_AND_COMPATIBILITY.md | NO CHANGE | Existing exact old readers/new-campaign-only rule retained; successor documentation links fresh contracts, no retroactive binding or in-place semantic upgrade. |
| README_BDB_AUDIT_V2_DOCUMENTATION_R5_4.md | CHANGE REQUIRED | New successor navigation and assurance status; all predecessor documents retained unchanged. |
| production runtime/tests | NO CHANGE IN THIS TASK | Implementation and execution postponed to authorized later milestones; graph proposals cannot authorize runtime writes. |

## 8. Owner decision and entry gate

Approve all semantic models, exact bodies/enums/ref domains/chronology, no-omission/independent derivation, identity/finite constraints, the 21 proposed kinds, existing-contract corrections and external-profile models as **one consolidated delta**. Rejected alternatives and their reasons are part of this package. Approval is not a choice between vague models; the recommendations above are concrete. Any changed semantic choice requires recomputing the graph before materialization.

Graph fixed point under these proposals: **131 keys = 110 registered R5.4.1 + 21 proposed**. Currently bound: 39; missing executable bindings: 92. Queue empty; unresolved abstract targets/C/D zero in the proposed model. These claims apply to the explicit design graph, not the still-incomplete actual qualified Registry. No candidate directory/Q1/Q2/schema creation is permitted in this task.

Final gate: **READY_FOR_OWNER_APPROVAL** (design only).

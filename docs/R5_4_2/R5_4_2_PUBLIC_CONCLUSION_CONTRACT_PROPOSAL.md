# R5.4.2 Public Conclusion Statement contract proposal

**PROPOSED — NOT APPROVED — NOT NORMATIVE/RUNTIME AUTHORITY.** No R5.4.2 candidate, schema, Registry, Golden Vector or qualification record is produced. Q2 and N5–N11 remain NOT_STARTED. Date: 2026-10-06.

Recommend one dedicated canonical semantic wrapper `public_conclusion_statement/1`, **DERIVED_PROJECTION**, immutable, backed by exact retained public raw bytes. Wrapper ObjectDigest and public RawDigest are distinct. It communicates existing accepted conclusion; it establishes no new assurance or product release authority.

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


Data §81 final technical report already references FinalAssuranceCase. Reusing that report/receipt as the mandatory prior public statement would create FinalCase→report→FinalCase. General report export also lacks the restricted public renderer. RawRef alone cannot establish prior canonical semantic acceptance. FACT is inappropriate because statement creates no new truth. This selected model avoids all three alternatives.

Chronology: prior accepted CampaignConclusion (and its STOP/StopInput/candidate/challenger/risk/limited-basis closure) → durable deterministic public raw → accepted PublicConclusionStatement → later FinalAssuranceCase → later ReleaseQualification → optional later final technical report/export. Statement never references its future FinalCase, release decision or accepting head. No public release-ready authorization can be implied before ReleaseQualification; the STOP release axis is explicitly labelled assessment.

PUBLIC_CONCLUSION_RENDER_V1 uses closed canonical UTF-8 JSON. Fields are campaign_ref, source_generation_ref, conclusion_ref, stop_evaluation_ref, scope_inventory_ref (null only when legally absent for early limited conclusion), termination_state, assurance_level, continuation_decision, stop_release_assessment, residual_risks, limited_basis_refs and bounded_statement. Values come only from exact accepted chain. Risk entries disclose exact risk ref, description, reason_unresolved, disposition and materiality; every material/unknown applicable risk is present. Redaction may remove sensitive raw basis but never risk presence, state or limitation. A general caller-written prose field cannot bypass equality: bounded_statement is exactly accepted Conclusion.bounded_conclusion_statement. Any text view uses deterministic fixed labels and escaping of this exact JSON, not arbitrary marketing narrative.

Raw bytes must equal independent Render(exact conclusion, exact pinned renderer/profile). The raw artifact contract is the exact renderer profile; media type application/json, bounded UTF-8 closed body. Thus wrong conclusion, omitted risk, assurance upgrade, stale chain, or COMPLETED_LIMITED rendered as PASS/READY/full completion rejects. A malicious accepted bounded statement is itself rejected at Conclusion by finalization consistency; quoting an unchecked natural-language claim does not make it true. Unknown/non-PASS STOP forbids public full success and both READY states. Statement discloses campaign termination and qualified scope separately from product readiness.

FinalCase.public_conclusion_statement_ref is PRIOR_ACCEPTED_ONLY exactly this kind/version; Statement.conclusion_ref equals FinalCase.conclusion_ref; risks and STOP/assurance/source identities are strict equalities. Intervening material audit-basis change blocks statement/finalization and requires fresh lawful assurance closure/successor semantics; extra wrapper acceptance commits are not such a change. One exact renderer result per conclusion/profile is idempotent; different raw bytes cannot replace it.


All new semantic bodies are closed (`additionalProperties=false` in future executable schemas). No unlisted authority field, capability secret, self-digest, future consumer, accepting head/event/receipt is permitted. TypedRef/RawRef/ExternalProfileRef/HistoryCut use Data §192.1 exactly; full reference identity includes kind, version via exact schema, revision digest/profile and schema revision. HistoryInput is nonempty verified prior cut; initialization sentinel only in original bootstrap contracts. Logical ID grammar follows Data §6: lowercase kind prefix plus underscore and canonical UUID; no display ID as selector.

For new contracts: body maximum 16 MiB UTF-8 canonical bytes, each text maximum 65536 Unicode code points (nonempty unless explicitly optional), arrays maximum 65536 members, IDs exact UUID grammar, integers bounded signed 64-bit except strictly positive revision numbers. No NaN/Infinity, duplicate JSON keys, unknown enum values, implicit normalization, or unbounded parser resources. Larger campaign closure must use a separately approved successor contract, not silently truncate. Existing bound contracts retain their exact constraints until a reviewed successor delta explicitly changes them. These bounds are proposed owner-visible semantics, not hidden generator choices.

Reference arrays are full-identity sorted sets with duplicate rejection. Raw/Profile tagged union arrays sort by tag + complete canonical value. `CommitBody.immutable_object_refs` retains original union-DAG topological sequence, never sorted set. Any optional field is absent when unavailable; no new nullable representation unless normative contract explicitly permits it. Every field without `?`/`optional` is required; arrays may be empty only when cardinality says 0. Prior typed refs must be accepted in the exact campaign/source/subject context at the represented cut. External profile fields are exact prior pins for the named purpose; no local overlay, latest-installed selection or caller-minted authority. Raw fields always re-read retained exact bytes and verify digest/length/profile.

FACT means recorded statement/intent, ASSESSMENT means qualified dimension at a cut, DECISION means authorized predicate/decision, DERIVED_PROJECTION means deterministic reproducible enumeration/communication. None can upgrade its source truth. Canonical semantic wrappers use ObjectDigest; actual raw observations, ZIPs, public bytes and text exports use RawDigest. The Registry role name by itself cannot select a digest domain. In particular raw/export files are not silently given an ObjectDigest just because a Registry row names their family; an accepted wrapper must have an explicit closed body/schema and raw reference. Proposed row identity clarification must be approved before generation.

Producer is the trusted coordinator acceptance boundary; projections are independently reproduced there, not accepted from caller checksum. Required validation is the conjunction of original named layer predicates plus applicable new semantic/finalization predicates, as listed in the graph; producer identity never implies evidence strength. Same-cut exact retry reuses original receipt; competing different immutable bodies for one represented tuple conflict by CAS, with **REJECT + NO CANONICAL STATE MUTATION**. Accepted revisions remain immutable. Only explicit predecessor fields create revision lineage; changed tuple/cut for a projection creates a new immutable entry. No hidden mutable current object or latest-by-ID authority. Fresh approved successor campaign only; preserve all old contracts/history/bytes and historical invalid objects for forensic display.


Vector designs: PUBLIC_CONCLUSION_EXACT_ACCEPT, WRONG_CONCLUSION_REJECT, ASSURANCE_UPGRADE_REJECT, RESIDUAL_RISK_OMISSION_REJECT, LIMITED_AS_FULL_REJECT, STALE_CUT_REJECT (all names have PUBLIC_CONCLUSION prefix in graph). **NOT EXECUTED**; canonical negatives reject with all before/after canonical state fields unchanged.

Owner approves dedicated raw-backed projection, five-field body, closed renderer/disclosure constraints, exact temporal ordering and no-new-assurance/no-false-public-pass rule. Runtime renderer and schema generation remain later work.

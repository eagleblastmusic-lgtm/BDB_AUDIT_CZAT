# R5.4.2 Assurance Claim Set contract proposal

**PROPOSED — NOT APPROVED — NOT NORMATIVE/RUNTIME AUTHORITY.** No R5.4.2 candidate, schema, Registry, Golden Vector or qualification record is produced. Q2 and N5–N11 remain NOT_STARTED. Date: 2026-10-06.

Recommend one dedicated `assurance_claim_set/1`, **DERIVED_PROJECTION**, immutable. Data §80 requires a separate exact target but does not define it. SOUND (§147) is claim-relative qualification and cannot represent the complete enumeration; snapshot (§105) alone has no no-omission contract. FACT would confuse enumeration with truth, ASSESSMENT with assessed assurance. Removing the ref and embedding another array changes the frozen Candidate body and duplicates its existing claim array.

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


The universe is the accepted FindingClaimRevision lineage tips for the exact campaign/source and inventory at `claim_set_input_history_cut`. Explicit predecessor edges determine tips; a fork is a conflict, never a latest timestamp choice. Include all tips whose surface/scope intersects inventory and every tip whose applicability cannot be disproved under exact pinned policy. A rejected, unresolved or contradictory claim is still enumerated. Superseding a claim must preserve the underlying unresolved material matter in its new revision/risk/obligation accounting; revision cannot be used to delete adverse information. No free-standing generated assurance assertion or unanalyzed caller string becomes a claim.

This is an enumeration of authored claims, not completeness of coverage: Candidate must independently enumerate full inventory/mandatory obligations/current qualifications, all current adjudications for included claims, unresolved contradictions, qualified/applicable evidence and risk closure. An empty authored claim set is legal only as an enumeration; unknown/missing obligation support still blocks required assurance. A claim with no current adjudication remains visible and cannot be represented as a current favorable finding state. This interpretation is an explicit owner decision for the previously undefined term ASSURANCE CLAIM SET.

Candidate.scope_inventory_ref equals the set inventory; Candidate.finding_claim_revision_refs equals set.claim_refs and independently recomputed universe. Cuts are identical, with all source claim/authority facts accepted before represented cut. The set may be earlier same-commit content of Candidate under original CONTENT_OR_PRIOR; it cannot include same-commit new claims as prior facts. Earlier accepted set is reusable only for identical inventory/claim closure and represented cut. Accepted set/candidate commits alone do not change assessed subject basis; new material claim/scope/evidence/risk change requires new set/candidate and both challengers. No Candidate future ref or self-hash is stored.


All new semantic bodies are closed (`additionalProperties=false` in future executable schemas). No unlisted authority field, capability secret, self-digest, future consumer, accepting head/event/receipt is permitted. TypedRef/RawRef/ExternalProfileRef/HistoryCut use Data §192.1 exactly; full reference identity includes kind, version via exact schema, revision digest/profile and schema revision. HistoryInput is nonempty verified prior cut; initialization sentinel only in original bootstrap contracts. Logical ID grammar follows Data §6: lowercase kind prefix plus underscore and canonical UUID; no display ID as selector.

For new contracts: body maximum 16 MiB UTF-8 canonical bytes, each text maximum 65536 Unicode code points (nonempty unless explicitly optional), arrays maximum 65536 members, IDs exact UUID grammar, integers bounded signed 64-bit except strictly positive revision numbers. No NaN/Infinity, duplicate JSON keys, unknown enum values, implicit normalization, or unbounded parser resources. Larger campaign closure must use a separately approved successor contract, not silently truncate. Existing bound contracts retain their exact constraints until a reviewed successor delta explicitly changes them. These bounds are proposed owner-visible semantics, not hidden generator choices.

Reference arrays are full-identity sorted sets with duplicate rejection. Raw/Profile tagged union arrays sort by tag + complete canonical value. `CommitBody.immutable_object_refs` retains original union-DAG topological sequence, never sorted set. Any optional field is absent when unavailable; no new nullable representation unless normative contract explicitly permits it. Every field without `?`/`optional` is required; arrays may be empty only when cardinality says 0. Prior typed refs must be accepted in the exact campaign/source/subject context at the represented cut. External profile fields are exact prior pins for the named purpose; no local overlay, latest-installed selection or caller-minted authority. Raw fields always re-read retained exact bytes and verify digest/length/profile.

FACT means recorded statement/intent, ASSESSMENT means qualified dimension at a cut, DECISION means authorized predicate/decision, DERIVED_PROJECTION means deterministic reproducible enumeration/communication. None can upgrade its source truth. Canonical semantic wrappers use ObjectDigest; actual raw observations, ZIPs, public bytes and text exports use RawDigest. The Registry role name by itself cannot select a digest domain. In particular raw/export files are not silently given an ObjectDigest just because a Registry row names their family; an accepted wrapper must have an explicit closed body/schema and raw reference. Proposed row identity clarification must be approved before generation.

Producer is the trusted coordinator acceptance boundary; projections are independently reproduced there, not accepted from caller checksum. Required validation is the conjunction of original named layer predicates plus applicable new semantic/finalization predicates, as listed in the graph; producer identity never implies evidence strength. Same-cut exact retry reuses original receipt; competing different immutable bodies for one represented tuple conflict by CAS, with **REJECT + NO CANONICAL STATE MUTATION**. Accepted revisions remain immutable. Only explicit predecessor fields create revision lineage; changed tuple/cut for a projection creates a new immutable entry. No hidden mutable current object or latest-by-ID authority. Fresh approved successor campaign only; preserve all old contracts/history/bytes and historical invalid objects for forensic display.


Vector designs: CLAIM_SET_EXACT_ACCEPT, CLAIM_SET_OMISSION_REJECT, CLAIM_SET_STALE_CUT_REJECT, CLAIM_SET_DUPLICATE_REF_REJECT, CLAIM_SET_CROSS_CAMPAIGN_REJECT. Inputs/expected outcomes and all nine negative state-snapshot fields are in the graph; **NOT EXECUTED**. Every negative acceptance leaves canonical state unchanged.

Owner approves identity/role, four-field body, complete universe and Candidate equality rule, exact prior facts/earlier content chronology and finite constraints. No runtime or schema bytes are approved by this proposal.

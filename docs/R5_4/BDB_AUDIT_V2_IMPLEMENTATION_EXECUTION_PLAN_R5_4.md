# BDB Audit v2 — R5.4 successor normative candidate

Status: PENDING_EXACT_CANDIDATE_QUALIFICATION; not installed, not independent freeze, no runtime qualification.

Date: 2026-10-06. Predecessor R5.3.1 candidate set `087539f5a08a2441647aae1889ce51330b47740e559b394574da122bd6cfd15b`; predecessor R5.3 set `78de98f8163d2f0bf0ab94781b86bd8e5e0345411a4432669d91fdfc42671d56`.

This is a separate versioned successor. Owner approved the R5.4/NF02 design and new-campaign boundary. Predecessor references/status/reviews inside inherited history are provenance, not current qualification or runtime authority. The current normative file set is exactly the R5.4 manifest; prior source bytes remain untouched. Registered semantics, exact executable bindings, authenticated prior authority and every domain predicate are jointly required.

# BDB Audit v2 — Implementation Execution Plan / Work Breakdown

**Revision:** R5.3.1 execution derivative CORR-2 / 2026-09-10  
**Role:** executable work breakdown derived from the accepted R5.3 documentation; **not a competing normative architecture**  
**Primary source:** `BDB_AUDIT_V2_IMPLEMENTATION_ROADMAP.md`  
**Supporting sources:** `BDB_AUDIT_V2_TEST_AND_SELF_AUDIT_PLAN.md`, `BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS.md`, `BDB_AUDIT_V2_ARCHITECTURE_SPEC.md`, `ADR-006_CANONICAL_SERIALIZATION_AND_IDENTITY_PROFILE.md`, `BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY.json`, `BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json`

> **Authority rule:** this file schedules and decomposes implementation work. It MUST NOT redefine canonical kinds, enums, authority, history semantics, reference classes, lifecycle rules, STOP semantics, coverage semantics, or identity rules. On any conflict, the R5.3 normative corpus and pinned Registry/Golden Vectors win. A conflict is a blocker requiring correction of this execution plan or an explicit normative revision; it is never resolved ad hoc in code.

> **CORR-1 prerequisite rule:** the PR/M-slice order is the order of milestone completion, not permission to violate an earlier normative prerequisite. When a higher-authority R5.3 contract requires a prerequisite before an earlier runtime acceptance/gate, implement the minimum prerequisite in the earliest work package that needs it, without claiming the later M-slice complete. In particular, executable schema binding is **just-in-time before first runtime acceptance of each wire kind**; M10 is the completion/qualification slice for the foundation schema/identity layer, not the earliest point at which schema-binding code may exist. This correction does not reorder F0–F8 or M0–M50 and does not change normative bytes.

> **CORR-2 / R5.3.1 bootstrap-order rule:** after `F2-BOOTSTRAP-ORDER-002`, M5 canonical closure ordering uses the R5.3.1 normative correction: one Kahn sort over `typed same-commit content-ref edges ∪ exact active order-only precedence edges`. For first-history `INITIALIZE_CAMPAIGN_FROM_LEGACY`, exact pinned `BDB_BOOTSTRAP_PRECEDENCE_V1` is mandatory. It orders the bootstrap domain groups without adding `source_generation_ref` to `legacy_raw_ref`, without creating a second sort, and without changing the existing Kahn tie-break. The profile is ordering/cycle authority only; it never supplies referential integrity, authority or provenance. F2 acceptance remains blocked until exact R5.3.1 storage readback qualification is present.


---

# 0. Implementation objective

Build BDB Audit v2 in the exact order required by the R5.3 Roadmap:

```text
FREEZE LEGACY
→ QUALIFY FIXTURE GROUND TRUTH
→ EXTRACT MINIMAL ASSURANCE PRIMITIVES
→ PASS DUAL COMPATIBILITY
→ PROVE AUTHORITY / IDENTITY / HISTORY
→ BUILD FOUNDATION REFERENCE SLICE
→ PROVE FAILURE PATHS + STOP REFUSAL
→ EXPAND DOMAIN SUBSYSTEMS
→ E3 EXPAND
→ E4 DEEPEN
→ E5 ATTACK
→ SELF-AUDIT / RELEASE
```

The implementation strategy is:

```text
small contract
→ exact test vectors
→ minimal implementation
→ happy path
→ adversarial / failure path
→ milestone acceptance
→ only then expand scope
```

Optimization target before `FOUNDATION_REFERENCE_SLICE_GATE = PASS` is **falsifiability and correctness**, not throughput or UI polish.

---

# 1. Non-negotiable execution rules

1. One PR / work package has one primary semantic objective.
2. Every behavior-changing PR includes tests in the same PR.
3. No broad E4/E5, UI polish, plugin ecosystem, or performance rewrite before the Foundation Reference Slice gate.
4. No accepted-state mutation may bypass the Coordinator/Authority boundary.
5. No “latest by logical ID” may replace exact refs in gates, evidence qualification, STOP, history or release decisions.
6. No projection/report/cache/log becomes runtime authority.
7. No optimization may change canonical bytes, digests, ordering, failure codes or decision semantics without an explicit normative change.
8. Each phase F0–F8 ends with a `MilestoneAcceptance` tied to exact source/build/history inputs when the v2 history engine exists; before that, retain an equivalent qualification artifact with exact Git/source hashes.
9. A failure-path test that reveals a contract ambiguity blocks feature expansion. Do not patch around the ambiguity with a special case.
10. Real audits are forbidden before the production-use threshold in the Roadmap. Pre-threshold campaigns are synthetic qualification fixtures only.

---

# 2. Entry Gate B0 — author baseline storage qualification

**Purpose:** do not start implementation from an ambiguous documentation snapshot.

Before the first implementation PR:

- finish upload of all R5.3 support artifacts;
- verify exact R5.3 files by raw Drive readback and SHA-256;
- retain the exact R5.3 manifest;
- create the external immutable `AuthorBaselineQualificationRecord` only after readback PASS;
- record the normative candidate-set digest used by implementation;
- set implementation metadata to reference that exact baseline record/digest;
- keep `FOUNDATION_SPEC_BASELINE_FROZEN = NO` unless an independent freeze is performed later.

**B0 exit:**

```text
R5_3_DRIVE_READBACK = PASS
R5_3_MANIFEST_VERIFIED = PASS
AUTHOR_BASELINE_QUALIFICATION_RECORD = PRESENT
IMPLEMENTATION_BASELINE_DIGEST = PINNED
```

**B0 completion record — 2026-09-10:**

```text
B0_STATUS = PASS
NORMATIVE_CANDIDATE_SET_SHA256 = 78de98f8163d2f0bf0ab94781b86bd8e5e0345411a4432669d91fdfc42671d56
DRIVE_READBACK_NORMATIVE_FILES = 10/10 PASS
DRIVE_READBACK_SUPPLEMENTAL_ARTIFACTS = 4/4 PASS
DRIVE_READBACK_MISMATCH_COUNT = 0
AUTHOR_BASELINE_QUALIFICATION_RECORD_DRIVE_ID = 1cKuDK6GD0LW3t-O5LY-UZfXOHqKeNQtY
AUTHOR_BASELINE_QUALIFICATION_RECORD_SHA256 = de7c79c3a7ec3f3879d702993e60f882f01f66ecbc00c67e8084de84dc5f99a0
AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE = YES (derived external governance state)
INDEPENDENT_ASSURANCE = FALSE
FOUNDATION_SPEC_BASELINE_FROZEN = FALSE
```

This completion note is execution provenance only. It does not modify the R5.3 normative candidate set and does not claim independent freeze or release qualification.

No source code feature work before B0 PASS.

---

# 3. Repository operating model

Use the Roadmap branch model:

```text
main
└── stable / reference legacy line

bdb-v2
└── active v2 implementation
```

Retain/tag the exact v1.4.4 baseline as required by M0.

Recommended implementation directories, introduced only as needed:

```text
src/bdb_audit/
  coordinator/
  history/
  assurance/
  orchestration/
  knowledge/
  corpus/
  inventory/
  invariants/
  coverage/
  experiments/
  evidence/
  adjudication/
  stop/
  schemas/

tests/
  unit/
  property/
  schema/
  golden/
  compatibility/
  integration/
  adversarial/
  fault/
  reproducibility/

fixtures/
  legacy/
  foundation_reference/
  calibration/
```

Do not pre-create large implementations in every package at M4. Empty/minimal interfaces are preferable to speculative code.

---

# 4. PR Definition of Ready / Definition of Done

## Definition of Ready

A work package is ready only if:

- Roadmap M-slice and phase F are identified;
- normative contracts affected are listed;
- exact Registry kinds are known;
- relevant Golden Vectors are identified;
- expected failure behavior is known;
- dependency PRs/gates are PASS.

## Definition of Done

A work package is done only if:

- implementation is minimal for its declared objective;
- unit/schema/property tests pass where applicable;
- required compatibility/golden/adversarial tests pass;
- no new authority source is introduced;
- no normative status/enum/kind alias is invented;
- deterministic outputs remain deterministic;
- failure path is tested, not only the happy path;
- documentation/comments identify exact contract refs rather than paraphrasing new semantics;
- CI lane(s) required for the package pass;
- reviewer can explain how the package fails closed.

---

# 5. F0 — Legacy Freeze & Fixture Truth (M0–M1)

## WP-F0-01 / PR-001 — M0 Legacy Freeze

**Goal:** create immutable v1.4.4 reference truth.

Deliverables:

- frozen v1.4.4 application file;
- `legacy/v1_4_4/` reference directory;
- `LEGACY_BASELINE_MANIFEST.json`;
- SHA-256, size, Git blob/tree/commit, application/wrapper/protocol versions;
- retained legacy self-test output;
- exact legacy tag/pin.

Tests:

- raw digest re-read;
- tag resolves to exact expected tree/commit;
- reference copy differs from working implementation path;
- mutation of reference fixture detected.

Exit gate: Roadmap M0 Gate exactly.

**Execution status — 2026-09-10: PASS.**

Evidence:

- repository: `eagleblastmusic-lgtm/bdb-audit`;
- legacy line `main`: exact commit `446f11ce1622a49f5100cefead29a04d952d487e`, tree `35e83b7424795381240bd1520f412f6111c28c24`;
- active implementation branch `bdb-v2`: M0 commit `46ae26e2b91a2fd7a6e2bf2a164b90231f6a95d5`;
- frozen source blob: `37adeefe3bf91bb00f9ffa2d5c3d92aebce33bc2`;
- frozen source SHA-256: `d851511fc5cf06e205426e843d1f43ac72edb2adf95b786c39e016a49fbda841`;
- size: `1030677` bytes;
- legacy self-test: `PASS`, exit `0`, retained in `legacy/v1_4_4/LEGACY_SELF_TEST_OUTPUT.json`;
- baseline manifest: `legacy/v1_4_4/LEGACY_BASELINE_MANIFEST.json`;
- local verification: `4 passed` plus deliberate one-byte mutation detection `PASS`;
- current GitHub connector cannot create a tag ref; Roadmap M0 Gate permits `LEGACY_TAG_OR_EQUIVALENT_PIN`, therefore the immutable exact legacy commit SHA above is the operative equivalent pin. The requested tag name `bdb-audit-v1.4.4` is retained in the manifest and may be added later without altering baseline identity.

M0 Gate values:

```text
LEGACY_FILE_RAW_DIGEST_KNOWN = YES
LEGACY_SOURCE_REFERENCE_PINNED = YES
LEGACY_SELF_TEST_OUTPUT_RETAINED = YES
LEGACY_TAG_OR_EQUIVALENT_PIN = YES
LEGACY_COPY_IMMUTABLE = YES
```

## WP-F0-02 / PR-002 — M1 Compatibility Corpus

**Goal:** pin valid and invalid legacy fixtures and independent ground truth.

Deliverables:

- valid fixtures listed by Roadmap M1;
- invalid fixtures listed by Roadmap M1;
- fixture manifest with both `legacy_observed_*` and `independent_safe_expected_*`;
- classification of known legacy bugs and intentional v2 hardening.

Tests:

- every fixture has exact RawDigest;
- no fixture lacks an expectation basis;
- unresolved foundation expectation conflicts = 0;
- fixture identity is immutable.

Exit gate: M1 Gate.

**F0 milestone:** `MilestoneAcceptance(F0)` or pre-history equivalent qualification record.

---

# 6. F1 — Minimal Assurance Primitives & Dual Compatibility (M2–M3)

## WP-F1-01 / PR-003 — M2 Core errors/hash/CJSON/IDs

Implement:

```text
core/errors.py
core/hashing.py
core/canonical_json.py
core/ids.py
```

Required proof:

- ADR-006 canonical JSON rules;
- duplicate-key rejection;
- integer/decimal boundaries;
- RawDigest/ObjectDigest type separation;
- exact domain-separated kind/version digest;
- malformed typed IDs rejected.

Tests:

- unit + property + golden identity vectors;
- cross-process deterministic outputs;
- canonical bytes have no transport LF;
- transport RawDigest differs where expected without changing ObjectDigest semantics.

**Work-research adjudicated clarification P02 (correctness now; tuning after F3):**

- add explicit negative/golden cases for duplicate escaped keys, bool-vs-int53 boundaries, float tokens, surrogate handling, transport LF, and exact wire kind/version/domain;
- hashing paths must be bounded and have explicit buffer ownership; streaming/buffer tuning may not change canonical bytes or SHA-256 semantics;
- any performance implementation beyond these correctness/resource-bounded requirements remains behind `FOUNDATION_REFERENCE_SLICE_GATE = PASS`.

## WP-F1-02 / PR-004 — M2 ZIP safety + artifact hashes

Implement:

```text
assurance/zip_safety.py
assurance/artifact_hashes.py
```

Required proof:

- path traversal rejected;
- duplicate member policy enforced;
- member/size bounds;
- streaming for large members where required;
- exact raw hashes reproducible.

**Work-research adjudicated clarification P03:**

- enforce actual decompression ceilings, central-directory/input quotas and aggregate expanded-byte ceilings;
- include traversal, normalized-path collision, duplicate-member and symlink/special-file rejection fixtures;
- descriptor/file-handle ownership and cleanup are part of the negative-path proof;
- assert explicitly that SourceManifest semantic identity and ZIP `RawDigest` representation identity remain distinct.

## WP-F1-03 / PR-005 — M3 legacy assurance extraction

Port only mechanical primitives:

- legacy source identity readback;
- ledger/checkpoint prefix validation;
- F1/F2 validators;
- attestation/continuation validation;
- final legacy bundle validation;
- raw artifact integrity.

Constraint: legacy parsing does not establish v2 current-state authority.

## WP-F1-04 / PR-006 — M3 dual differential harness

Implement two simultaneous verdicts:

```text
preservation(v2, legacy_observed)
correctness(v2, independently_qualified_expected)
```

Tests:

- legacy bug preserved by v1 but rejected by v2 can be intentional hardening;
- v1=v2 does not imply correctness;
- unexplained preservation differences = 0 for required fixtures;
- all unsafe known fixtures rejected according to independent expectation.

**F1 exit:** both Roadmap M3 gates PASS.

---

# 7. F2 — Foundation Authority / Identity / Orchestration Minimum (M4–M13)

This is the highest-risk implementation phase. Do not parallelize modules that share authority/history semantics until the foundational interface is stable.

## WP-F2-01 / PR-007 — M4 minimal application skeleton

Create minimal package tree and CLI import path.

Acceptance:

```text
python -m bdb_audit --help
```

works and test runner loads. No broad domain features.

## WP-F2-02 / PR-008 — Registry + Golden Vector bootstrap

Load and validate the pinned:

```text
BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY.json
BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json
```

Implement fail-closed resolution for:

- registered kind/version;
- reference class semantics;
- explicit complete vs schema-bound contract mode;
- canonical role domain;
- ordering rules;
- dangling targets;
- forbidden aliases.

**Work-research adjudicated clarification P04 / CORR-1:**

- Data Contracts §184 applies to **every wire kind**: `EXPLICIT_COMPLETE` freezes material ref/cardinality/order semantics but is not an exemption from exact executable schema validation before first runtime acceptance;
- implement the minimal offline schema-binding/resolver substrate here, with pinned dialect/format behavior and validation-backend identity recorded in implementation/test evidence;
- before the first M5 runtime acceptance, bind exact executable schema bytes+digest for every wire kind reachable in that accepted M5 closure; later PRs must likewise bind any newly accepted kind just-in-time before its own first runtime acceptance;
- `SCHEMA_BYTES_NOT_BOUND` (or the exact normative equivalent) requires a negative test, and `R5N77_SCHEMA_BINDING_BOUNDARY` must prove that implementation may exist while acceptance remains forbidden until binding;
- PR numbering/order never authorizes acceptance of an unbound kind: PR-009 and later history work remain fail-closed until the required binding exists;
- this prerequisite work does **not** mark M10 complete. PR-016 remains the schema/identity completion and qualification slice.

This PR must not create runtime history yet.

## WP-F2-03 / PR-009 — M5 canonical objects + first-history bootstrap primitives

Implement minimal representations for:

- `CommandEnvelope`;
- `CommitBody`;
- `AcceptedHead`;
- `CommandReceipt`;
- `HistoryCut` / `EMPTY_HISTORY`;
- `InstallationBootstrapProfile`;
- `TrustedPredecessorSelectionDecision`;
- `BootstrapAdmissionDecision`;
- `CampaignGenesis`.

Required proof:

- first accepted commit is seq=1;
- `EMPTY_HISTORY` is legal only at initialization;
- no synthetic H0/zero hash;
- normal command policy/spec/actor authority comes from accepted/pinned context, never same-commit self-authorization;
- command/commit/receipt exact identity bindings are equal where required;
- source-authority and actor-authority bootstrap paths use the exact R5.3 typed reference classes;
- deterministic closure order uses the R5.3.1 union DAG: typed same-commit content-ref edges plus exact active `BDB_BOOTSTRAP_PRECEDENCE_V1` order-only edges for initialization; one Kahn/min-heap tie-break procedure only; no second independent sort order;
- `legacy_raw_ref` remains EXPLICIT_COMPLETE with only its history input; never add `source_generation_ref` merely to force ordering;
- required R5N-80 positive, non-global-scope and union-cycle vectors pass before M5 acceptance.

## WP-F2-04 / PR-010 — M5 transactional history adapter

Reference API:

```text
accept(command, expected_head)
→ validate
→ persist immutable closure
→ persist commit
→ persist receipt
→ atomically advance accepted head
```

Reference backend may be SQLite but semantics remain backend-independent.

Fault tests at every logical persistence boundary:

- crash before object durability;
- crash after object durability before commit;
- crash after commit before receipt;
- crash after receipt before head;
- ambiguous ACK retry;
- concurrent expected-head conflict.

Invariant: recovery exposes old or new complete accepted state, never a mixed state.

**Work-research adjudicated clarification P05:**

- the SQLite reference implementation keeps immutable closure + commit + durable receipt + accepted-head advance inside one explicit durable database transaction;
- required uniqueness/CAS constraints must be enforced at the storage boundary, not only in Python prechecks;
- ambiguous-ACK retry checks the durable receipt/idempotency identity before creating any new effect;
- expose named, deterministic **test-only** crash hooks at every logical persistence boundary so the fault suite can prove old-or-new atomic recovery;
- the initial correctness profile remains the simple durable profile; WAL/physical-layout tuning is benchmark work after F3, never a reason to weaken fsync/durability semantics.

## WP-F2-05 / PR-011 — M5 minimal FSM

Implement legal subset of `TRANSITION_PROFILE_V1` for:

- Campaign;
- StageRun;
- LaneRun;
- Attempt.

Required negative tests:

- skip E0;
- attempt result treated as lane completion;
- shortcut from planned to running;
- late result rewrites accepted completion;
- retry reuses same Attempt improperly.

Run the full M5 Gate after PR-011.

## WP-F2-06 / PR-012 — M6 StageSpec registry

Implement immutable StageSpec revisions and exact digest resolution.

Foundation minimum:

- bootstrap policy StageSpec;
- minimal E3 StageSpec;
- registry recognizes E1–E5 IDs without implementing full engines.

Tests: duplicate ordinal, cycle, missing predecessor, invalid artifact/reveal phase.

## WP-F2-07 / PR-013 — M7 LaneSpec / Attempt / isolation

Implement exact lane/attempt binding plus isolation qualification.

Required tests:

- fresh lane ID without controlled fresh session != ENFORCED;
- forbidden channel access degrades/rejects qualification;
- potential exposure monotonic after accepted grant;
- missing ACK does not restore blindness;
- restart without qualified fresh-session boundary does not reset knowledge;
- blind-origin qualification requires an accepted pre-reveal discovery precursor on an earlier permitted cut.

**CORR-1 prerequisite clarification:** because the normative M7 Gate itself requires accepted-grant/exposure/knowledge/discovery semantics before M8/M12 are complete, PR-013 may implement only the minimal accepted fact/fixture path needed to prove those M7 invariants. This is prerequisite proof, not completion of the M8 Capability Broker or M12 Knowledge/Exposure/Discovery Engine. Every wire kind accepted by this proof must already have its exact executable schema binding under P04/CORR-1.

Exit: M7 Gate.

## WP-F2-08 / PR-014 — M8 Capability Broker / positive views

Implement:

- ExecutorProfile;
- DeliveryProfile;
- ProjectionPolicy;
- ViewManifest;
- positive-view resolver;
- grant-before-delivery.

Do not hardcode SOL/Codex/etc. semantics into StageSpec.

Negative proof: raw refs or transitive resolver closure cannot leak forbidden artifacts.

## WP-F2-09 / PR-015 — M9 minimal deterministic prompt/package compiler

Function of pinned inputs only.

Required:

- compile twice => identical bytes;
- expected prompt/package SHA goldens;
- compiler has zero authority-write capability;
- forbidden raw artifact cannot be resolved through a view ref.

Exit: M9 Gate.

## WP-F2-10 / PR-016 — M10 executable schema/identity binding completion

Complete and qualify the foundation schema/identity layer. Bind every remaining foundation schema key required by the F2/F3 foundation path to exact executable schema bytes/digests before that kind's first runtime acceptance. Re-verify that schemas bound earlier as prerequisites remain byte/digest-identical and preserve the frozen semantics; do not silently rebind them.

Layered validator order:

1. parse / duplicate keys;
2. schema;
3. canonicalization/digest;
4. typed refs;
5. source/campaign scope;
6. policy/spec binding;
7. lifecycle/history cut;
8. evidence/applicability constraints when applicable.

Golden R5.3 vectors are mandatory CI inputs.

Additional P04 acceptance evidence:

- exact schema bytes/digest are pinned before first acceptance;
- resolver is offline/fail-closed;
- dialect and format-checker behavior are pinned;
- validation backend/version identity is captured in qualification evidence;
- reference `jsonschema` parity remains the development/test oracle for any later native validator experiment.

## WP-F2-11 / PR-017 — M11 Corpus Engine

Implement DirectPredecessor, HistoricalCorpus, AuxiliaryCorpus, ExternalHoldout.

Required gate:

```text
DIRECT_PREDECESSOR_SINGLE
AUXILIARY_MULTI_REPORT
CROSS_SOURCE_CORPUS_REJECTED
LEGACY_E2_ACCEPTED_AS_DIRECT_PREDECESSOR
```

## WP-F2-12 / PR-018 — M12 Knowledge / Exposure / Discovery

Implement accepted facts + derived views for grant/exposure/isolation/contamination/knowledge/discovery.

Required property: blind-origin claim requires accepted precursor on an earlier permitted cut; timestamps alone never establish blindness.

Exit: M12 Gate.

## WP-F2-13 / PR-019 — M13 Claim Quarantine / positive reveal

Implement allowlisted bytes, ViewRef namespace and restricted resolver.

Negative tests include hidden field absence in bytes, opaque ref non-resolution, metadata/filename non-leak and transitive closure non-leak.

**F2 exit:** authority/history, identity/schema, isolation and knowledge/discovery minimum are all stable enough to build the reference vertical slice.

---

# 8. F3 — Foundation Reference Slice & Bootstrap Proof (minimal M14–M23)

The goal is not feature completeness. The goal is a deterministic end-to-end proof of the entire foundation.

## WP-F3-01 / PR-020 — M14 minimal inventory accounting

Implement minimal `CollectionRun`, typed InputDisposition and ScopeState records, InventoryRevision and SurfaceRecord required for the synthetic repository.

Required proof:

- every assigned input terminally accounted;
- PROVISIONAL/PROVISIONAL_SCOPE never satisfy completion;
- unknown/unsupported/failed scope remains visible in denominator.

Exit: M14 Gate.

## WP-F3-02 / PR-021 — M15/M16 invariant + coverage obligation minimum

Implement:

- InvariantRevision;
- MaterialityAssessment;
- CoverageObligation;
- CoverageObligationQualification;
- authorized applicability/waiver decision path.

No global depth number is authority. D0–D5 is derived only.

Required tests: no auto-N/A, no auto-waiver, no artificial denominator improvement, invalidation degrades dependent obligation.

## WP-F3-03 / PR-022 — M17/M18 minimal gap + hypothesis linkage

Implement enough DiscoveryOpportunityMap/Gap logic and Hypothesis revision flow to drive one reference hypothesis.

Rejected hypotheses remain in accepted history.

## WP-F3-04 / PR-023 — M19 Experiment / Execution binding

Implement preregistered Experiment plus ExecutionDescriptor / activations / observations / cleanup / ExecutionResult DAG according to R5.3.

Required proof: no retroactive preregistration and no execution/result cycle.

## WP-F3-05 / PR-024 — M20 Evidence Qualification minimum

Implement:

- Observation;
- dependency graph;
- `EvidenceQualificationAssessment`;
- `EvidenceApplicabilityAssessment`;
- dependency-independence assessment;
- invalidation propagation.

Required proof: shared oracle/path cannot masquerade as independence.

## WP-F3-06 / PR-025 — M21/M22 minimal adjudication/contradiction

Implement the minimum finding path required by reference fixtures:

- FindingClaimRevision;
- FindingAxisAssessment;
- FindingAdjudicationDecision;
- RootCauseRevision where exercised;
- contradiction behavior where exercised.

No separate RootCause membership authority.

## WP-F3-07 / PR-026 — M23 derived contribution projection

Implement only derived contribution view. Prove deletion/rebuild does not alter canonical facts.

## WP-F3-08 / PR-027 — StageCompletion + intermediate STOP

Implement exact StageCompletion and StopInput/StopEvaluation binding for foundation reference flow.

Foundation happy path must end:

```text
E3 StageCompletion
→ StopEvaluation(INTERMEDIATE)
→ CONTINUE_REQUIRED
```

because E4/E5 requirements remain pending. It MUST NOT produce global PASS or release readiness.

## WP-F3-09 / PR-028 — Foundation Reference Slice E2 legacy → v2 E3

Build one synthetic end-to-end campaign:

```text
INSTALLATION_BOOTSTRAP_PROFILE_V1
→ INITIALIZE_CAMPAIGN_FROM_LEGACY @ EMPTY_HISTORY
→ SourceGeneration + legacy E2 raw + qualification/admission
→ CampaignGenesis in atomic seq=1
→ E3 StageRun/Lane/Attempt
→ controlled knowledge/discovery
→ checkpoint → controlled reveal
→ Hypothesis
→ preregistered Experiment
→ Observation / Evidence Qualification
→ CoverageObligation qualification
→ StageCompletion
→ StopEvaluation(INTERMEDIATE)=CONTINUE_REQUIRED
```

## WP-F3-10 / PR-029 — Mandatory F1–F7 adversarial failure suite

Exact required outcomes:

- F1 contaminated lane → `BLIND_SLOT_NOT_SATISFIED`;
- F2 missing/unknown material surface → `STAGE_COMPLETION_BLOCKED`;
- F3 shared broken oracle → required independence qualification rejected;
- F4 crash → one recovered accepted effect after idempotent retry;
- F5 stale predecessor → `BLOCKED_CANONICAL_ADMISSION`;
- F6 invalidated evidence → completion blocked until replacement qualification;
- F7 insufficient-data intermediate STOP → `CONTINUE_REQUIRED` with both `REQUIRED_STAGES_PENDING` and `INSUFFICIENT_DATA`.

## WP-F3-11 / PR-030 — FOUNDATION_REFERENCE_SLICE_GATE

Run full reference slice plus all required failure paths from clean storage multiple times.

Acceptance requires:

```text
DUAL_COMPATIBILITY_GATES = PASS
AUTHORITY_HISTORY_GATE = PASS
IDENTITY_SCHEMA_GATE = PASS
FOUNDATION_REFERENCE_SLICE_GATE = PASS
STOP_REFUSAL_PATH = PASS
```

Record `MilestoneAcceptance(F3)`.

**Hard rule:** no broad domain expansion before PR-030 PASS.

---

# 9. F4 — Domain Expansion after reference gate

Only after F3 PASS.

Expand M14–M23 from reference-minimum to production-intended scope:

- collector coverage;
- invariant categories;
- obligation policy library;
- Gap Engine;
- hypothesis orchestration;
- experiments/execution adapters;
- evidence graph/invalidation;
- finding/root-cause/contradiction engines;
- native E1/E2 orchestration;
- replay and successor semantics.

Each expanded contract must retain the same authority model proven by F3.

Exit requires domain-specific integration tests and no regression of Foundation Reference Slice.

---

# 10. F5 — E3 EXPAND (M24–M27)

Work packages:

- PR-E3-01: blind novelty lanes E3-X/Y/Z;
- PR-E3-02: checkpoint + gap-directed positive reveal;
- PR-E3-03: fuzzing adapter M25;
- PR-E3-04: differential testing M26;
- PR-E3-05: metamorphic testing M27;
- PR-E3-06: E3 Integration Gate.

Every E3 lane must preserve knowledge/reveal provenance proven by F3.

---

# 11. F6 — E4 DEEPEN (M28–M35)

Work packages:

- state model engine;
- temporal invariant engine;
- property/stateful adapter;
- bounded model exploration;
- concurrency schedule engine;
- crash/recovery engine;
- endurance engine;
- causal chain engine;
- E4 Integration Gate.

No E4 subsystem may create a second evidence oracle or state authority outside accepted-history/qualification contracts.

---

# 12. F7 — E5 ATTACK / STOP / E6 (M36–M45 + M45A)

Work packages:

- failure interaction graph;
- interaction scheduler;
- mutation framework;
- auditor calibration;
- final skeptic;
- false-negative hunter;
- residual risk projection;
- CandidateAssuranceCase at E5A;
- E5B challenger assignment/results and E5 StageCompletion;
- final StopInput/StopEvaluation;
- Adaptive E6 Generator;
- release lifecycle and successor assurance.

Temporal rule:

```text
E5A complete
→ CandidateAssuranceCase accepted
→ ChallengerAssignment accepted
→ ChallengerResult accepted
→ E5 StageCompletion accepted
→ FINAL_POST_E5 StopEvaluation
→ CampaignConclusion
→ FinalAssuranceCase
→ ReleaseQualification
```

Do not collapse these into one same-commit chain where a later actor would need knowledge of an unaccepted prior decision.

---

# 13. F8 — Build / CLI / UI / Self-Audit / Release (M46–M50)

Work packages:

- deterministic standalone build;
- CLI;
- interactive UI;
- release validator;
- self-audit v2;
- release qualification.

UI is a projection/operation surface, not an authority source.

Release branch must run all CI lanes:

```text
lint
typecheck
unit
compatibility
integration
property
adversarial
golden
build-reproducibility
```

---

# 14. CI and test cadence

## Fast PR lane

Run on every ordinary PR:

```text
lint
typecheck
unit
schema
selected property
golden impacted by changed contract
compatibility impacted by changed primitive
```

## Foundation gate lane

Run for F2/F3 authority changes:

```text
all golden vectors required by the current phase/implemented contract surface
all foundation properties required by the current phase/implemented contract surface
crash/fault injection where the current phase provides the relevant runtime path
history rebuild/projection rebuild
legacy differential harness
isolation/knowledge adversarial where the current phase provides the relevant runtime path
reference slice F1–F7 once the F3 reference-slice implementation exists
```

**CORR-1 applicability rule:** F2 must not claim PASS for a reference-slice check whose implementation is deliberately scheduled in F3. F2 qualification records such a later-only sublane as not yet applicable by phase, while still running every F2-defined gate and every foundation check whose required runtime path exists. From F3 PR-028/PR-029 onward, the reference-slice F1–F7 sublane becomes mandatory. This is a scheduling/applicability clarification, not a weakening of any existing gate.

## Release/full lane

Run complete test matrix including build reproducibility, calibration and long-running/stateful tests.

## Performance benchmark cadence — activated after F3

Performance evidence from Work research is split into three execution profiles so ordinary PRs do not inherit stress-test cost:

```text
CI_SMOKE
  small deterministic fixtures
  impacted microbench/parity checks
  short resource-bound regression checks

NIGHTLY_STANDARD
  multi-scale BM01–BM19 subsets
  larger histories/graphs/ZIPs
  crash/replay and memory/I-O telemetry
  cold/warm cache separation

QUALIFICATION_STRESS
  highest planned scales (including up to 10^6 objects where the benchmark defines it)
  large streaming artifacts / long replay
  p95/p99, RSS, disk amplification and repeated crash schedules
  raw samples + environment/fixture manifest retained as evidence
```

No benchmark threshold becomes a new semantic or release gate merely because Work proposed it. An optimization can be promoted only after canonical/failure-path parity and the existing §16 acceptance rule.

A CI timeout is not a PASS. Required-lane timeout = BLOCKED/FAIL according to policy.

---

# 15. Commit/PR sizing

Prefer:

```text
contract implementation
+ tests
+ fixtures required by that contract
```

Avoid:

```text
large refactor
+ new feature
+ migration
+ performance rewrite
+ UI changes
```

in the same PR.

Recommended PR review questions:

1. What exact R5.3 contract does this implement?
2. What new accepted fact/decision can this code create?
3. Can any projection/cache/log accidentally become authority?
4. Can any same-commit ref point forward or create a cycle?
5. Can any prior-only/history-context ref be supplied from the current closure?
6. What failure path proves fail-closed behavior?
7. Can retry create a second effect?
8. Does a source/policy/spec/schema change invalidate this result correctly?
9. Are canonical bytes/digests unchanged by refactoring?
10. What gate becomes eligible after this PR?

---

# 16. Performance Optimization Lane — deliberately separate from correctness

Performance work starts only after `FOUNDATION_REFERENCE_SLICE_GATE = PASS`, except for basic safety limits needed for correctness/resource-boundedness.

## 16.1 Baseline measurements before optimization

Capture reproducible benchmarks for:

- BDB-CJSON serialization throughput;
- ObjectDigest/RawDigest throughput;
- schema + typed-ref validation latency;
- accepted commit latency by closure size;
- crash/recovery/replay time;
- projection rebuild time;
- ZIP validation throughput and peak memory;
- corpus resolver/view construction latency;
- Inventory/Obligation scaling;
- evidence dependency/invalidation propagation;
- STOP input/evaluation latency;
- deterministic package/compiler time;
- cold-start and CLI startup time.

Benchmark fixtures must be versioned and pinned.

## 16.2 Optimization acceptance rule

Every optimization proposal must provide:

```text
baseline benchmark
changed benchmark
CPU/memory/I/O delta
correctness test delta
canonical output equivalence
failure-path equivalence
complexity/maintenance cost
rollback path
```

Mandatory invariant:

```text
same semantic inputs
→ same canonical bytes
→ same ObjectDigests
→ same decisions/reason codes
```

unless an explicit normative revision intentionally changes semantics.

## 16.3 Safe likely optimization targets

Prefer optimizations outside semantic authority first:

- streaming ZIP/hash readers;
- bounded incremental hashing;
- immutable-object cache keyed by exact digest;
- compiled/cached schema validators keyed by schema digest;
- projection caches keyed by exact accepted head;
- batched read-only resolver queries;
- efficient topological validation algorithms;
- incremental invalidation projection while retaining deterministic full rebuild oracle;
- prepared SQLite statements / WAL tuning if SQLite is selected as reference backend;
- bounded concurrency for independent read-only qualification work;
- lazy loading of large raw artifacts behind exact refs;
- deterministic memoization where cache key includes every semantic input.

Do **not** optimize by weakening validation layers, replacing exact refs with “latest”, skipping canonicalization, caching unbound current state, merging authority boundaries, or converting fail-closed errors to warnings.

---

# 17. How to use ChatGPT Work optimization research without creating a second architecture

External/Work research is an **optimization proposal generator**, not normative authority.

Work may:

- inspect the exact R5.3 package;
- research current Python/storage/schema/serialization/testing libraries;
- compare algorithms and measured performance characteristics;
- identify tools for fuzzing, property/stateful testing, model checking and profiling;
- propose implementation alternatives;
- produce benchmark plans and proof-of-concept recommendations.

Work MUST NOT:

- rewrite R5.3 authority semantics;
- change canonical kinds/enums/reference classes;
- remove validation for speed;
- change F0–F8 / M0–M50 ordering;
- treat a performance recommendation as accepted architecture;
- silently modify the normative R5.3 documentation.

Every Work proposal enters an `OPTIMIZATION_CANDIDATE_REGISTER` with one of:

```text
ACCEPT_FOR_BENCHMARK
REJECT_SEMANTIC_RISK
REJECT_NO_EVIDENCE
DEFER_UNTIL_F3
DEFER_UNTIL_PROFILING
ADOPT_AFTER_BENCHMARK
```

Only `ADOPT_AFTER_BENCHMARK` may become an optimization implementation task, and only if all correctness/golden/failure-path tests remain unchanged or intentionally versioned. Correctness work already required by R5.3 may proceed on its normative basis even when Work independently suggested the same mechanism; the Work suggestion itself does not create authority.

**Current research adjudication:** `BDB_V2_OPTIMIZATION_CANDIDATE_REGISTER_R5_3.csv` is the non-normative machine register for the 56 Work candidates. P02–P05 above are accepted only as additive correctness/resource-bounded clarifications; P01 is rejected in its original form because runtime/environment provenance does not belong inside `AuthorBaselineQualificationRecord`.

---

# 18. Recommended first implementation sequence

Do not start with E3/E4/E5 features. Execute in this exact practical order:

```text
B0  R5.3 storage qualification
↓
PR-001 Legacy Freeze
↓
PR-002 Compatibility Corpus
↓
PR-003 Core CJSON/hash/IDs
↓
PR-004 ZIP/artifact integrity
↓
PR-005 Legacy primitives
↓
PR-006 Dual differential harness
↓
PR-007 Minimal v2 skeleton
↓
PR-008 Registry + R5.3 Golden Vector loader + just-in-time schema-binding prerequisite
↓
PR-009 Bootstrap/history canonical objects
↓
PR-010 Transactional history backend + crash points
↓
PR-011 FSM minimum + M5 Gate
↓
PR-012 StageSpec
↓
PR-013 Lane/Attempt/isolation
↓
PR-014 Capability Broker / positive views
↓
PR-015 deterministic package compiler
↓
PR-016 executable schema/identity binding completion
↓
PR-017 Corpus
↓
PR-018 Knowledge/Exposure/Discovery
↓
PR-019 Claim Quarantine
↓
PR-020 Inventory minimum
↓
PR-021 Invariant/Coverage minimum
↓
PR-022 Gap/Hypothesis minimum
↓
PR-023 Experiment/Execution
↓
PR-024 Evidence Qualification
↓
PR-025 Finding/RootCause/Contradiction minimum
↓
PR-026 Contribution projection
↓
PR-027 StageCompletion/STOP minimum
↓
PR-028 end-to-end Foundation Reference Slice
↓
PR-029 F1–F7 failure-path qualification
↓
PR-030 FOUNDATION_REFERENCE_SLICE_GATE
```

Only after PR-030 PASS:

```text
Domain Expansion
→ native E1/E2
→ E3
→ E4
→ E5
→ STOP/E6/Release
→ Build/CLI/UI
```

---

# 19. Implementation stop conditions

Stop expansion and return to the relevant contract if any of these occur:

- two reasonable implementations produce different canonical bytes/digests;
- a required typed-ref target is ambiguous;
- same-commit ordering cannot be topologically proven;
- current-state authority can be derived from two independent stores;
- projection deletion changes reconstructed canonical state;
- legacy preservation and correctness cannot be separated;
- blindness depends on executor self-attestation;
- unknown/failed scope disappears from coverage denominator;
- shared oracle is accepted as independent evidence;
- invalidation does not propagate to dependent assurance;
- StageCompletion implies CampaignConclusion implicitly;
- intermediate STOP can return PASS/E6_REQUIRED contrary to policy;
- release qualification can remain READY after material drift without reassessment;
- optimization changes canonical output or decision semantics without a normative revision.

---

# 20. Success criterion for the execution plan

This execution plan succeeds when it preserves the Roadmap's central property:

> BDB v2 is built by proving small falsifiable assurance primitives and one complete Foundation Reference Slice before broad functionality is added.

The first major project success is **not** a polished UI or a full E5 run. It is:

```text
FOUNDATION_REFERENCE_SLICE_GATE = PASS
```

with deterministic happy path plus F1–F7 fail-closed behavior.

After that point, performance and capability expansion can proceed against a foundation that is already executable, measurable and regression-testable.

# R5.4 N1-N11 successor task packet (subordinate scheduling)

### N1 — approve normative delta

- **Objective:** approve A/D/E/H model; produce complete versioned R5.4 candidate and external governance evidence.
- **Dependencies:** this proposal, pinned predecessor corpus, explicit owner decisions L.
- **Files/components:** successor DC/ARCH/TEST/RP/EP, candidate manifest/readback/self-audit, profiles/Golden fixtures; predecessor files read-only.
- **Normative refs:** DC §§14–16,95–96,184–188, w szczególności §§187.1–187.2; governance records; A–J.
- **Outline:** implement normative wording only; freeze full ref/slot/transport/error/FSM/profile semantics before coding; preserve predecessor lineage; review all conflicts. Generate exact candidate manifest and external author qualification or independent freeze under existing governance.
- **Positive tests:** complete narrative/Registry/body parity, source hashes/readback, governance actor and record binds exact candidate.
- **Negative tests:** missing approval, modified predecessor, incomplete manifest, false self-qualification -> reject qualification.
- **Adversarial tests:** alternate alias/profile, ambiguous cut/version, copied qualification for different candidate.
- **Acceptance:** explicit owner approval and governance-qualified exact candidate; no SPEC_CONFLICT among proposed machine/narrative inputs. Author-only versus independent status explicit.
- **Rollback:** discard unapproved candidate artifacts; preserve predecessor and proposal.
- **Blast radius:** specification authority and all subsequent NF02 evidence; no runtime activation yet.

### N2 — freeze new Registry

- **Objective:** authoritative successor machine inventory, no extensions required for NF02.
- **Dependencies:** N1 approved semantics; candidate finalization iterates with N1 until exact consistent freeze.
- **Files/components:** successor ArtifactContractRegistry JSON, core Registry loader/packaged pin planning; full ref/validation/target-version map.
- **Normative refs:** REG/D.2–D.3; DC §§184–188; ADR unchanged.
- **Outline:** add complete three new kind rows and schema_registry/2, named validation profile, exact version resolution and output target wiring. Preserve inherited roles/classes/ordering. Do not absorb unrelated overlay without separate authorized semantics.
- **Positive tests:** Registry definition validation, exact registered key resolution, complete nested RawRef/profile fields.
- **Negative tests:** unknown role/ref/kind, duplicate key, alias, wrong schema key, omitted material ref -> reject.
- **Adversarial tests:** shadow/override via extension/local file; /1 fallback to /2; changed pinned bytes.
- **Acceptance:** exact frozen Registry digest, parity self-audit and machine vectors; no unregistered new ObjectDigest domain.
- **Rollback:** no runtime activation; supersede candidate through governance if bytes need change.
- **Blast radius:** every canonical resolver/schema generation/qualification depending on Registry; assess inherited evidence bindings.

### N3 — freeze exact executable schemas

- **Objective:** durable exact schema files/dependency/profile closure for first acceptance.
- **Dependencies:** N2 exact semantics and N1 candidate approval.
- **Files/components:** schemas/ frozen successor assets, existing schemas/binding.py substrate, schema/profile manifests, GV known-answer fixture bytes.
- **Normative refs:** DC §184; REG; D.3; existing offline backend rules.
- **Outline:** generate build-time candidates; review complete schemas for /1 inherited reachable objects and new /1-/2 rows; freeze `$id`, dialect, RawDigest/length and validator dependency identity. Materialize the finite result slot/finding/output and package transport schema specified in N1; no additionalProperties escape hatch. Verify executable behavior against exact known-answer fixtures already fixed in the approved Golden set; do not change its inputs or expected outcomes to match code.
- **Positive tests:** exact fixture validates, RawDigest/readback/dialect/parity, semantic checksum known answers and repack distinction.
- **Negative tests:** mutated/truncated schema, missing dependency, format/$ref/network resolution or duplicate fields -> reject acceptance.
- **Adversarial tests:** benign-looking schema with removed required ref; wrong root schema; unknown dynamic/remote references.
- **Acceptance:** all kinds reachable before first runtime acceptance have exact executable bytes and no semantic drift; fixture expected hashes independently checked. Schemas alone do not activate runtime. If any approved normative/Registry/Golden/profile bytes or semantics must change during N2/N3, invalidate the affected candidate qualification, return to N1, produce a new exact manifest/readback and external approval record before N4. Model approval is never a transferable approval for different candidate bytes.
- **Rollback:** replace unactivated candidate set through new exact manifest/governance, never silently overwrite pinned files.
- **Blast radius:** all affected validators/harness/GV and environment-sensitive dependency evidence.

### N4 — create/pin SchemaRegistry revision

- **Objective:** legal trusted activation for new campaigns.
- **Dependencies:** N1 governance, N2 Registry, N3 schema files/profiles.
- **Files/components:** schema_registry/2 asset/body, installation_bootstrap_profile/1 successor revision, bundle loader/bootstrap, Registry/schema resolver, build payload pins.
- **Normative refs:** DC §§14.6,95–96,184; D.3; R5N03/26/37/65/77/80.
- **Outline:** construct immutable binding set, compute canonical digest, external exact root schema pin/readback; authorized install retains old readers/pins; seq1 qualified bootstrap establishes R5.4 context using allowed initialization command. Resolve schema per campaign/cut.
- **Positive tests:** fresh legal bootstrap, schema-root first validation, exact new kinds accepted only after all bindings.
- **Negative tests:** unregistered kind, missing/wrong schema, unapproved bundle, old campaign current-set substitution -> reject without mutation.
- **Adversarial tests:** self-authorizing registry, malicious latest-installed set, same-commit semantic self-upgrade, bootstrap-union cycle.
- **Acceptance:** four schema vectors PASS plus inherited bootstrap/governance gates; exact installation pin -> campaign set chain demonstrated. No old-campaign writes enabled.
- **Rollback:** disable new campaign creation/writes; restore exact trusted installation artifacts; retain all created histories.
- **Blast radius:** bootstrap, all campaign authority/schema consumers, standalone build and package pin verification.

### N5 — implement AssignmentPackageBinding

- **Objective:** one immutable accepted raw authorization per exact assignment.
- **Dependencies:** N4 legal kinds/schemas; N2 contract freeze.
- **Files/components:** history objects/Store/authority_hooks/raw_artifacts, orchestration/FSM, coordinator operation contract; focused tests.
- **Normative refs:** REG D.2.1; E.1–E.2; DC history/CAS/ID rules.
- **Outline:** reuse canonical object/ref/transaction mechanisms; add binding acceptance operation and rebuildable exact selector; enforce prior A, current cut, raw/profile/source/knowledge validation, no prior start, idempotency and conflict. Avoid parallel mutable authority table.
- **Positive tests:** zero -> one B, durable reopen, original receipt exact retry.
- **Negative tests:** second B, wrong A/cut/source/profile, same-commit A or reused changed command ID -> reject without mutation.
- **Adversarial tests:** concurrent/process CAS, same logical ID different full ref, duplicate binding with same raw but new ID, generic Store bypass.
- **Acceptance:** binding vectors and all ref/uniqueness/atomicity invariants PASS; no canonical /1 reinterpretation.
- **Rollback:** block writes/delivery; retain accepted B and bytes; no deleting selector/history.
- **Blast radius:** history/ref validation/transactions; assess all dependent authority evidence.

### N6 — wire package creation/storage/binding

- **Objective:** exact package constructed from accepted context and frozen before delivery/start.
- **Dependencies:** N5; N3 transport/semantic checksum; N4 campaign activation.
- **Files/components:** workflow/packaging.py, manual_stage.py, assignments.py, package_resume.py, stage_resume.py, workflow/executors.py, raw vault, transition profile/operation adapter.
- **Normative refs:** E.3–E.5, ARCH delivery §44.3, existing grants/PotentialExposure/isolation.
- **Outline:** finalize package -> store -> B accept -> durable readback -> separate accepted STARTED -> adapter releases retained bytes. Batch/job fields become disposable projections of exact accepted refs. Resume may recover original package from vault even when workspace copy vanished. Delivery guard serializes/revalidates against terminal transitions.
- **Positive tests:** E1 and manual-stage flows, multiple result slots, exact retransmission, deleted workspace recreated from vault, package includes A not B/hash.
- **Negative tests:** delivery/start before B, wrong/repacked raw, semantic/profile/context mismatch, missing raw -> reject without mutation/disclosure.
- **Adversarial tests:** crash at each package/raw/B/start boundary; live workspace substitution; terminal/source race during delivery; ZIP/JSON malformed cases.
- **Acceptance:** real adapter has zero disclosure callbacks before guards; delivered bytes equal B RawRef; restart resumes accepted B rather than regenerating authority.
- **Rollback:** suspend delivery/write path; keep accepted packages/bindings/exposure; resume only with exact approved bytes.
- **Blast radius:** E1–E5 shared packaging/resume, executor delivery and knowledge exposure, standalone CLI/UI.

### N7 — wire admission/result validation

- **Objective:** accepted evidence and result derive exclusively from prior A/B and retained result raw.
- **Dependencies:** N6 authorized package path; N4 /2 schemas; N5 history invariants.
- **Files/components:** inbox.py, manual_stage.py, result_proposal.py, Store/authority_hooks, schemas assets, lane/stage completion and STOP/output consumers.
- **Normative refs:** D.2.2–D.2.3; E.2/E.6; existing result FSM/evidence qualification/L7.
- **Outline:** remove canonical token and redundant context/proposal checksum; authenticated ingestion derives E/2; later R/2 rederives payload; bind exact slot and unique package B. Check generic/direct Store paths as well as Inbox. Update allowed consumer versions without aliases or truth promotion.
- **Positive tests:** legitimate E1/manual results, evidence -> later result -> required outputs/completion; exact retry; replay after key rotation.
- **Negative tests:** no/wrong B, mismatched claims, no prior E, forged payload, terminal/wrong/closed slot -> reject without canonical mutation.
- **Adversarial tests:** copied/forged capability with valid command, ref identity laundering, altered findings after admission, raw deletion between commits, forged completion/STOP bypass.
- **Acceptance:** all result vectors PASS through production acceptance API and direct Store; result content equals exact raw normalization; Lane/StageCompletion still require their full predicates.
- **Rollback:** disable new intake/completion writes; retain all raw/E/R accepted state; do not downgrade to /1 acceptance.
- **Blast radius:** provenance consumers, authority/history, all stage result adapters, discovery/evidence/STOP and report.

### N8 — migration / fail-closed compatibility

- **Objective:** explicit historical read-only and new campaign boundary.
- **Dependencies:** N4 new initialization, N6/N7 lawful fresh execution.
- **Files/components:** campaign open/create, legacy/historical reader adapters, workflow resume, UI/CLI migration status, compatibility fixture/harness and report provenance.
- **Normative refs:** H; DC §96/initialization/successor rules; ARCH recovery.
- **Outline:** recognize exact historical schema sets and unqualified extension histories; preserve objects/raw and expose limited historical status; block new-contract writes. Offer/create legally bootstrapped new namespace only through authorized product action. No retro B or forced conclusion.
- **Positive tests:** old history readable with original identities; new legal R5.4 campaign works; separately valid existing successor rules preserved.
- **Negative tests:** old namespace schema auto-upgrade, retro binding, /1 -> /2 alias/backfill, nonempty genesis -> reject without mutation.
- **Adversarial tests:** migration with missing objects, forged original chronology, actor/source authority substitution and old evidence auto-qualification.
- **Acceptance:** no old campaign obtains new assurance by opening/installing; exact history bytes unchanged; compatibility claims scoped and tested.
- **Rollback:** disable migration writer/new campaign helper while retaining historical viewer; never reset campaign DB/history.
- **Blast radius:** application opening/resume, historical/legacy compatibility and assurance lineage; qualify affected harness paths.

### N9 — adversarial qualification

- **Objective:** prove frozen semantics and boundaries independently of friendly workflow tests.
- **Dependencies:** N5–N8 and exact N1–N4 inputs.
- **Files/components:** successor GV runner, targeted NF02 tests, existing transaction/crash/schema/parser/authority/harness tests, exact evidence manifest.
- **Normative refs:** J; TEST material contract positive/negative/adversarial rule; DC mutation/authority invariants.
- **Outline:** instantiate every vector with exact known-answer inputs; production API, direct Store and standalone paths; instrument external delivery; subprocess crashes/races; compare accepted-state snapshots. Reuse current tests when they cover property under new exact dependencies; add only missing regression vectors.
- **Positive tests:** legal exact binding/admission/result, identity separation, idempotency/restart.
- **Negative tests:** every J rejection proves zero canonical mutation; unsupported historical write/unsafe input.
- **Adversarial tests:** every extra J vector, parser quotas, secret/ref/schema spoofing, races and corruption.
- **Acceptance:** all frozen expected outcomes evidenced, zero silent skip, all required negative mutation/disclosure assertions pass. A harness/parser defect is repaired, not labeled external blocker.
- **Rollback:** stop qualification/activation claims; fix root cause and rerun targeted + affected mandatory broader gates; do not loosen vector expectation.
- **Blast radius:** fixtures/GV/harness/qualification verifier are assurance dependencies; assess every dependent evidence binding.

### N10 — full NF02 qualification

- **Objective:** qualify C1/C2 and remediation together on exact implemented state.
- **Dependencies:** N1–N9 PASS with exact authority/evidence pins; no unratified dependency on unrelated extension authority.
- **Files/components:** all affected source/tests/build, NF02 qualification artifact, phase/milestone verifiers, compatibility corpus, release validator and CI configuration.
- **Normative refs:** TEST full gates; RP/EP affected milestones and qualification closure; C authority hierarchy.
- **Outline:** targeted -> affected components -> required cross-cutting/full repository checks -> required milestone/phase verifier. Assess F0–F8 dependency evidence individually; changed Registry/schemas/GV/history/harness invalidate reuse on their affected paths. Reuse unaffected evidence only if all governing exact blobs/inputs/environment conditions still bind it. Run required broader gates, Ruff/Mypy/build/local validator, compatibility/clean-room/exact-source CI where governing release contract requires them. Preserve separate qualification scope labels.
- **Positive tests:** complete package/evidence/result raw chain across live/reopen; completion/STOP legal controls; manifest matches implemented/dependency blobs.
- **Negative tests:** missing mandatory subordinate gate, stale artifact, drifted fixture/schema/backend, false truth or release PASS -> qualification reject.
- **Adversarial tests:** independent re-audit original NF02 bypasses and new binding/schema/authority attacks against exact packaged runtime.
- **Acceptance:** no C1/C2 SPEC_CONFLICT, owner-approved activated normative corpus, every named mandatory NF02/subordinate gate PASS, no relevant drift afterward. N11 application gate remains separately required before claiming overall application qualification. Current 249 PASS is not substitute.
- **Rollback:** fail-closed disable affected writer/delivery; preserve histories; remediation loop until correct or genuine external blocker. No retrospective NF02 CLOSED.
- **Blast radius:** shared authority/identity/schema/qualification, all evidence consuming changed contracts and release packaging. Future commit only if separately authorized; then required terminal post-commit verifier checks intended committed state and transitive subordinate artifacts, otherwise run missing checks. No commit/push authority comes from this plan.

### N11 — complete application lifecycle qualification

- **Objective:** demonstrate a real application lifecycle, including retained raw and safe continuation after restart.
- **Dependencies:** N10; qualified packaged runtime, legal exact R5.4 bootstrap input and existing stage/report contracts; all lifecycle-used wire kinds legally registered. An unrelated residual_risk/other overlay cannot be accepted merely because local tests pass.
- **Files/components:** shipped application startup/open/create, campaign coordinator, all required E1–E5 stage services and adapters, vault/history recovery, report generator/export, standalone build/validator, application E2E evidence/phase verifier.
- **Normative refs:** user lifecycle below; TEST E1–E5/standalone/recovery/release/verification; ARCH campaign/flow/raw retention; RP/EP final application gates.
- **Outline:** run production application with fresh workspace and process, legal bootstrap (current allowed initial command requires qualified legacy input; do not fabricate an unspecified no-legacy profile), real delivery adapter and controlled external executor. Executor consumes delivered package and produces actual fixture audit result; do not mint result directly through Store or call an untrusted proposal a completed audit. Exercise all stages required by governing specs, including E6 when required. Report status reflects actual completion and assurance state.
- **Positive tests:** exact lifecycle below; source and standalone equivalent supported flows; multiple stage/lane progression and continuation with new legal assignment after reopen.
- **Negative tests:** missing/corrupt raw package, result, required evidence member, canonical object, schema/profile or history commit; stale/unregistered schema; reopening old campaign for new writes -> fail closed, no fabricated recovery/completion/report qualification.
- **Adversarial tests:** process termination at lifecycle boundaries, altered workspace copies, substitution just before delivery/intake, corrupt accepted bytes/DB dependency, concurrent terminal transition and resume; compare before/after identities and disclosure.
- **Acceptance:** actual start/stop/restart/reopen and continue trace, exact accepted head/objects/events/receipts recovered, package/result/evidence raw readback digests match, all required LaneCompletion/StageCompletion predicates and report gates evidenced. No unrun lifecycle check, mock-only delivery or missing raw can be labeled PASS. Required build/payload/startup/local versus release/clean-room/CI/phase evidence scopes explicit.
- **Rollback:** preserve qualification workspace/evidence, block affected writes/delivery, restore only verified exact objects; fix then rerun invalidated lifecycle/gates. No dropping corrupt history suffix.
- **Blast radius:** entire shipped application, standalone/runtime dependencies and assurance/report lifecycle; no next feature milestone implementation authorized.

Mandatory recorded lifecycle:

```text
fresh application start
 -> create/open legally initialized R5.4 campaign
 -> prepare audit
 -> create and accept assignment
 -> construct/freeze exact package bytes
 -> accept binding; durable readback; later accepted AttemptStarted
 -> deliver exact retained package through real adapter
 -> external executor consumes package and produces audit result
 -> ingest/retain raw result and accept evidence
 -> accept lane result under /2 contract
 -> LaneCompletion
 -> StageCompletion (and every further required stage)
 -> generate report with accurate assurance state
 -> close application/process
 -> restart fresh process
 -> reopen campaign
 -> recover exact accepted head/state/objects/events/receipts
 -> recover exact raw package/result and embedded evidence bytes
 -> continue audit using legal next attempt/assignment/stage
```

Evidence must identify source HEAD **plus dirty/source blob state when applicable**, normative/Registry/GV/schema/profile digests, dependency/backend/platform/runtime identity, fixture raw hashes, harness/verifier versions, exact commands/exit codes/results and artifact raw hash. An unchanged HEAD alone is insufficient. Terminal verification must bind intended implemented state and all mandatory subordinate checks; after any relevant change rerun only invalidated evidence plus explicitly mandatory gates.

Planned execution command families (not run in this documentation task): targeted `python -m pytest ...` existing `tests/workflow/test_nf02_*`, `test_inbox.py`, `test_manual_stage.py`, transaction/schema/process-fault tests and all new frozen-vector selectors; `python -m pytest` required full suite; `python -m ruff check ...`; `python -m mypy --config-file pyproject.toml`; existing `build/build_single_file.py` build interface; `python -m bdb_audit.release_validator_cli <exact artifact> --output <exact evidence>`; repository's governing milestone/phase verifiers and supported shipped application CLI/UI lifecycle. Resolve exact existing selectors/invocations from approved successor task packet, record them verbatim in execution evidence; do not invent a verifier command or silently bypass a mandatory gate when unavailable.

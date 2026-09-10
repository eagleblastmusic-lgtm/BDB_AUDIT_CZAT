# BDB AUDIT v2 — IMPLEMENTATION ROADMAP

**Status:** AUTHOR-FINAL R5.3 — final author qualification after zero-based re-audit; no additional Astra review scheduled
**Rewizja:** 2026-09-09 / R5.3 final author qualification candidate
**Self-audit:** `R5_3_AUTHOR_FINAL_REAUDIT_PASS`; report `BDB_AUDIT_V2_SELF_AUDIT_REPORT_R5_3_2026-09-09.md`; strict independent freeze is not claimed
**Dokument:** plan implementacji BDB Audit v2
**Powiązane dokumenty:**
- `BDB_Audit_vNext_Szczegolowy_Plan_Rozwoju.md`
- `BDB_AUDIT_V2_ARCHITECTURE_SPEC.md`
- `BDB_AUDIT_V1_TO_V2_MIGRATION_AND_COMPATIBILITY.md`
- `BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS.md`

**Cel:** określić jedną normatywną kolejność budowy BDB Audit v2, zależności między komponentami, foundation gates, failure-path proofs, wymagane testy oraz warunki przejścia z v1.4.4 do nowej generacji bez budowania szerokich subsystemów przed falsyfikacją authority/isolation/coverage/STOP.

---

# 1. Zasada nadrzędna realizacji

BDB Audit v2 nie może powstać jako jeden duży rewrite ani jako seria szerokich feature'ów budowanych na niezweryfikowanym foundation.

Normatywna kolejność jest **foundation-first i falsification-first**:

```text
FREEZE LEGACY
→ QUALIFY FIXTURE GROUND TRUTH
→ EXTRACT MINIMAL ASSURANCE PRIMITIVES
→ PASS PRESERVATION + CORRECTNESS GATES
→ CLOSE AUTHORITY / IDENTITY / HISTORY CONTRACTS
→ BUILD MINIMAL LEGACY E2 → V2 E3 REFERENCE SLICE
→ PROVE FAILURE PATHS + STOP REFUSAL
→ EXPAND DOMAIN SUBSYSTEMS
→ E3 EXPAND
→ E4 DEEPEN
→ E5 ATTACK
→ SELF-AUDIT / RELEASE
```

Każdy slice musi pozostawić repozytorium w stanie testowalnym. Implementacja nie może zwiększać zakresu tylko dlatego, że wcześniejszy fragment „już działa”.

Najważniejsza reguła roadmapy:

> **Nie implementuj szeroko mechanizmu, którego minimalna wersja nie przeszła wcześniej end-to-end happy path i przynajmniej jednego fail-closed path.**

# 2. Główne cele roadmapy

Roadmapa ma:

1. zachować exact historical E1/E2 bytes i kwalifikowane assurance primitives v1.4.4,
2. rozdzielić legacy behavior preservation od validator correctness,
3. zamrozić authority/identity/history przed szerokim domain modelem,
4. wymusić early reference slice `legacy E2 → v2 E3`,
5. wymusić failure-path proofs dla crash, stale input, contaminated lane, shared oracle, invalidated evidence i insufficient-data STOP,
6. utrzymywać jedną canonical accepted history zamiast wielu mutable ledger heads,
7. traktować Knowledge/Coverage/Contribution/Traceability jako projections lub typed facts zgodnie z Data Contracts,
8. utrzymać rollback i read-only legacy boundary,
9. rozdzielić stage completion, campaign conclusion i release qualification,
10. nie blokować deterministic standalone `.py`, ale nie optymalizować pod packaging przed poprawnością foundation.

# 3. Branch strategy

Rekomendowany model:

```text
main
└── stabilna / referencyjna linia legacy

bdb-v2
└── aktywna implementacja v2
```

Tag:

```text
bdb-audit-v1.4.4
```

musi wskazywać dokładnie zamrożony stan legacy.

Po zakończeniu:

```text
bdb-audit-v2.0.0
```

---

# 4. Jedna normatywna mapa faz realizacji

W tym dokumencie istnieje **jedna** normatywna mapa programu. Oznaczenia `M0…M50` w dalszych sekcjach są wyłącznie numerowanymi **implementation slices**, a nie drugą, konkurencyjną mapą milestone'ów.

```text
F0 — LEGACY FREEZE & FIXTURE TRUTH
     M0–M1

F1 — MINIMAL ASSURANCE PRIMITIVES & DUAL COMPATIBILITY
     M2–M3

F2 — FOUNDATION AUTHORITY / IDENTITY / ORCHESTRATION MINIMUM
     M4–M13

F3 — FOUNDATION REFERENCE SLICE & BOOTSTRAP PROOF
     minimalne części M14–M23 + reference gate

F4 — DOMAIN EXPANSION
     rozszerzenie inventory/obligations/evidence/findings/corpus

F5 — E3 EXPAND
     M24–M27

F6 — E4 DEEPEN
     M28–M35

F7 — E5 ATTACK / STOP / E6
     M36–M45

F8 — BUILD / CLI / SELF-AUDIT / RELEASE
     M46–M50 + release qualification
```

Przejście między fazami wymaga zapisanego `MilestoneAcceptance` na exact accepted history cut. Późniejsze sekcje P0/P1/P2 oraz dependency graph są widokami tej mapy, nie osobnym harmonogramem.

# 5. M0 — Legacy Freeze

## Cel

Utworzyć niezmienny punkt odniesienia dla v1.4.4.

## Zadania

### M0.1

Zamrozić:

```text
BDB_AUDIT_ASSISTANT_PA_v5.2_WRAPPERS_5.4-RC1_v1.4.4_ARCHIVE.py
```

### M0.2

Policzyć i zapisać:

```text
SHA-256
file size
Git blob/tree/commit
application version
wrapper release
protocol version
```

### M0.3

Utworzyć:

```text
legacy/v1_4_4/
```

### M0.4

Dodać:

```text
LEGACY_BASELINE_MANIFEST.json
```

### M0.5

Uruchomić aktualny self-test.

Zachować output.

### M0.6

Otagować repo:

```text
bdb-audit-v1.4.4
```

---

# 6. M0 Gate — Legacy Baseline

PASS tylko jeśli:

```text
LEGACY_FILE_RAW_DIGEST_KNOWN = YES
LEGACY_SOURCE_REFERENCE_PINNED = YES
LEGACY_SELF_TEST_OUTPUT_RETAINED = YES
LEGACY_TAG_OR_EQUIVALENT_PIN = YES
LEGACY_COPY_IMMUTABLE = YES
```

Gate potwierdza wyłącznie stabilny historyczny baseline. Nie potwierdza correctness zachowania v1.4.4.

Jeśli nie:

```text
STOP MIGRATION
```

# 7. M1 — Compatibility Corpus

Przed przepisywaniem validatorów należy stworzyć fixture corpus.

## Valid fixtures

Minimum:

```text
VALID_BASE_F1
VALID_BASE_FINAL
VALID_E2_F1
VALID_E2_F2
VALID_E2_FINAL
VALID_ATTESTATION
VALID_CONTINUATION_TICKET
VALID_PREVIOUS_PROMPT_BUNDLE
```

## Invalid fixtures

Minimum:

```text
WRONG_VARIANT
WRONG_SOURCE_SHA
WRONG_SOURCE_TREE
WRONG_RUN_ID
WRONG_AUDIT_ID
CONFLICTING_DUPLICATE
INVALID_HASH_MANIFEST
MISSING_SNAPSHOT
BROKEN_LEDGER_PREFIX
BAD_F1_CHECKPOINT
BAD_F2_CHECKPOINT
EARLY_REVEAL
SOURCE_GENERATION_MIX
SUBSTITUTE_F2
UNSAFE_ZIP_PATH
DUPLICATE_MEMBER
WRONG_ARTIFACT_FAMILY
```

---

# 8. Fixture manifest — preservation i correctness osobno

Każdy fixture ma zachować dwa niezależne oczekiwania:

```text
fixture_id
raw_artifact_ref / RawDigest
fixture_intent
legacy_observed_result
legacy_observed_error_family
independent_safe_expected_result
independent_expected_error_family
expectation_basis_ref
known_legacy_bug
intentional_v2_hardening
compatibility_exception_ref optional
```

`legacy_observed_result` nie może być automatycznie oracle dla `independent_safe_expected_result`.

# 9. M1 Gate — Fixture Ground Truth Ready

PASS tylko jeśli:

```text
REQUIRED_FIXTURE_BYTES_PINNED = YES
LEGACY_OBSERVED_OUTCOMES_RECORDED = YES
INDEPENDENT_SAFE_EXPECTATIONS_QUALIFIED = YES
KNOWN_LEGACY_BUGS_CLASSIFIED = YES
UNRESOLVED_EXPECTATION_CONFLICTS = 0 for foundation fixtures
```

Dopiero wtedy można używać corpus do dwóch różnych compatibility gates.

# 10. M2 — Extract Core Utilities

Pierwsza faktyczna modularizacja.

## Kolejność

### M2.1 — errors

```text
core/errors.py
```

### M2.2 — hashing

```text
core/hashing.py
```

### M2.3 — canonical JSON

```text
core/canonical_json.py
```

### M2.4 — IDs

```text
core/ids.py
```

### M2.5 — ZIP safety

```text
assurance/zip_safety.py
```

### M2.6 — artifact hashes

```text
assurance/artifact_hashes.py
```

---

# 11. M2 Tests

Dla każdego modułu:

- unit tests,
- legacy equivalence tests,
- malformed input tests.

Nie wprowadzać nowych stage features.

---

# 12. M3 — Extract Source / History / Checkpoint Assurance

Ekstrahować minimalne mechaniczne primitives potrzebne do foundation:

```text
legacy source identity parsing/readback
legacy ledger/checkpoint prefix validation
F1/F2 legacy validators
attestation / continuation validation
final legacy bundle validation
raw artifact integrity
```

Nie przenosić modelu „wiele ledgerów = wiele authority”. Legacy ledger parsing jest compatibility primitive. Native-v2 state będzie ustanawiany przez jedną canonical accepted history.

Każdy portowany primitive otrzymuje:

```text
legacy fixture
preservation expectation
independent correctness expectation
new implementation test
differential result
```

# 13. Dual differential harness

Harness daje **dwa** wyniki:

```text
legacy_observed = validate_with_v1(fixture)
v2_observed     = validate_with_v2(fixture)
preservation    = compare(v2_observed, legacy_observed)

safe_expected   = qualified_fixture_expectation(fixture)
correctness     = compare(v2_observed, safe_expected)
```

Wspólny PASS v1 i v2 nie dowodzi correctness, jeśli oba implementują tę samą lukę. Intentional hardening jest dopuszczalne tylko przez versioned compatibility decision.

# 14. M3 Gate — Dual Legacy Compatibility Foundation

Gate ma dwa niezależne wyniki:

```text
LEGACY_BEHAVIOR_PRESERVATION_GATE = PASS
VALIDATOR_CORRECTNESS_GATE = PASS
```

Minimalnie:

```text
UNEXPLAINED_REQUIRED_PRESERVATION_DIFFS = 0
KNOWN_SAFE_EXPECTATIONS_SATISFIED = 100%
KNOWN_UNSAFE_EXPECTATIONS_REJECTED = 100%
KNOWN_LEGACY_BUGS_MISCLASSIFIED_AS_SAFE = 0
```

Ten gate jest konieczny, ale **nie jest jeszcze wystarczający** do rozpoczęcia szerokiej implementacji domenowej.

# 15. M4 — Foundation Application Skeleton

Utworzyć minimalny szkielet potrzebny do przetestowania foundation, nie pełną platformę:

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
```

W tym momencie moduły mogą zawierać tylko minimalne interfejsy/reference implementations potrzebne vertical slice. Zakaz implementowania szerokich collectorów/E4/E5 „przy okazji”.

# 16. M4 Goal — compile, test, one authority boundary

Po M4:

```text
python -m bdb_audit --help
```

ma działać, test runner ma działać, a wszystkie materialne mutations domenowe muszą przechodzić przez jeden Coordinator/Authority interface. Nie jest wymagany pełny feature set.

# 17. M5 — Campaign + Canonical History Foundation

Zaimplementować minimalny `CampaignGenesis`, `HistoryCut`, `CommitBody`, `AcceptedHead`, `Receipt` i command/idempotency boundary, w tym exact `INSTALLATION_BOOTSTRAP_PROFILE_V1` oraz pierwszy atomic `INITIALIZE_CAMPAIGN_FROM_LEGACY` commit `seq=1`. Initialization CommandEnvelope używa `proposed_campaign_id/history_namespace_ref/bootstrap_profile_ref`, nie `campaign_ref`; CampaignGenesis wskazuje wcześniejszy BootstrapAdmissionDecision.

Wymagane properties:

```text
single accepted head
single coordinator writer profile
atomic commit closure
expected-head guard
idempotent command retry
ID reuse conflict detection
immutable object refs
rebuildable projections
```

Backend jest profilem implementacyjnym. SQLite może być reference backendem, ale roadmapa nie wiąże semantics z konkretnym storage product.

# 18. Transactional vault / canonical history adapter

Repository layer implementuje kontrakt:

```text
accept(command, expected_head)
→ validate refs/policy
→ persist immutable object closure
→ persist commit
→ persist receipt
→ atomically advance accepted head
```

Testy muszą wymuszać crash points przed i po każdym logicznym kroku. Po recovery widoczny jest wyłącznie stary albo nowy kompletny head — nigdy mieszanka.

# 19. Campaign / Stage / Lane / Attempt FSM minimum

Foundation reference implementuje **mały legalny podzbiór tego samego `TRANSITION_PROFILE_V1`**, nie osobny skrócony FSM:

```text
Campaign: CREATED → GENESIS_ACCEPTED → E0_READY → AUDIT_RUNNING
StageRun: PLANNED → READY → RUNNING → COMPLETION_CANDIDATE → COMPLETION_ACCEPTED
LaneRun:  PLANNED → READY → RUNNING → WAITING_RESULT/COMPLETION_CANDIDATE → COMPLETION_ACCEPTED
Attempt:  CREATED → STARTED → RESULT_RECEIVED → RESULT_ACCEPTED
```

Foundation może nie implementować wszystkich branchy, ale nie może dodawać shortcut edge omijającego E0, LaneCompletion albo Attempt states. Diagramy roadmapy są legalnymi paths, nie „abstrakcyjnymi strzałkami” dopuszczającymi skip. Retry execution tworzy nowy Attempt. Duplicate upload tego samego result slotu jest idempotentny; konfliktujący payload jest FAIL. Late result jest quarantined i nie mutuje zamkniętego StageCompletion.

# 19.1. Foundation Contract Registry + R5.3 golden vectors

Przed M5 załadować pinned `BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY.json` oraz wykonać `BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json`. Registry definiuje role/lifecycle wszystkich registered kinds oraz **pełną inline ref/cardinality/order closure wyłącznie dla `foundation_inline_reference_contract_kinds`**. Pozostałe kinds mają `SCHEMA_BOUND_BEFORE_FIRST_ACCEPTANCE` i są fail-closed do exact executable schema binding. Dangling ref target alias albo critical kind bez `EXPLICIT_COMPLETE` = reject/freeze blocker.

Golden vectors obejmują co najmniej FR-01–FR-14, w tym dependency-order-vs-sort-key, EMPTY_HISTORY, execution DAG, first release drift, E5A/candidate/E5B, second RootCause authority rejection, exact FSM subset i successor assurance.

# 19.2. Foundation freeze acceptance protocol

Independent `FOUNDATION_SPEC_BASELINE_READY` nie powoduje edycji reviewed corpus. Po PASS tworzy się zewnętrzny immutable `FoundationBaselineFreezeDecision` wskazujący exact candidate manifest digest i exact independent review digest. Jakakolwiek zmiana normative bytes po review wymaga nowego manifestu i nowego review.

## 19.2.1. R5.3 author-qualified implementation path

Dla bieżącego projektu owner zdecydował, że nie planuje kolejnego review Astry. R5.3 może otrzymać efektywne `AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE = YES` dopiero przez external `AuthorBaselineQualificationRecord` utworzony po finalnym author re-audit + exact manifest + byte-for-byte Drive readback; same candidate bytes pozostają `PENDING_EXTERNAL_QUALIFICATION_RECORD`. Ten status **nie jest** `FOUNDATION_SPEC_BASELINE_FROZEN`, nie jest independent assurance i nie może być przedstawiany jako spełnienie strict freeze/release gate. Pozwala rozpocząć implementację foundation pod jawnym owner-risk acceptance; każda wykryta sprzeczność spec w implementacji powoduje nową rewizję baseline zamiast cichego dostosowania kodu.

# 20. M5 Gate — Authority / Transaction / FSM Foundation

PASS tylko jeśli synthetic tests potwierdzają:

```text
ONE_ACCEPTED_HEAD = YES
CRASH_ATOMICITY = PASS
IDEMPOTENT_RETRY = PASS
CONCURRENT_EXPECTED_HEAD_CONFLICT = PASS
LATE_RESULT_CANNOT_REWRITE_COMPLETION = PASS
E0_READY_CANNOT_BE_SKIPPED = PASS
LANE_COMPLETION_IS_DISTINCT_FROM_ATTEMPT_RESULT = PASS
PROJECTIONS_REBUILD_IDENTICALLY = PASS
FIRST_BOOTSTRAP_SINGLE_ATOMIC_COMMIT = PASS
EMPTY_HISTORY_REJECTED_AFTER_SEQ1 = PASS
BLOCKED_ADMISSION_CANNOT_EMIT_GENESIS = PASS
```

# 21. M6 — StageSpec Registry + pinned revisions

Zaimplementować immutable StageSpec revisions i registry resolution po exact digest/ref.

Na foundation wystarczy StageSpec dla minimalnego v2 E3 reference flow oraz legacy-bootstrap policy. Pełne E1–E5 StageSpecs nie są warunkiem M6.

Każdy StageRun pinning obejmuje exact:

```text
stage_spec_revision
protocol/policy revision
schema set
source generation
```

# 22. Initial StageSpecs

```text
E1
E2
E3
E4
E5
```

Nie wszystkie muszą jeszcze mieć pełny engine.

Registry musi je rozpoznawać.

---

# 23. StageSpec Validation

Testy:

- duplicate ordinal,
- cycle,
- missing predecessor,
- invalid required artifact,
- invalid reveal phase.

---

# 24. M7 — LaneSpec / Attempt / Isolation Contract

Zaimplementować LaneSpec oraz Attempt binding z:

```text
required_isolation_assurance
allowed view classes
forbidden knowledge classes
executor capability requirements
assigned history cut
initial knowledge state
```

Foundation wymaga co najmniej jednego lane'a mogącego być realnie kwalifikowanym jako `ENFORCED` **albo** uczciwie odrzucającego tę kwalifikację jako niedostępną w danym backendzie.

# 25. Initial E1 lanes

```text
E1-A GENERAL
E1-B SECURITY
E1-C STATE_RECOVERY
E1-D DATA_CATALOG
E1-E FRONTEND_CONCURRENCY_ORACLE
```

---

# 26. Lane isolation tests

Testy obowiązkowe:

- nowy `lane_id` bez nowej kontrolowanej sesji nie daje ENFORCED,
- forbidden filesystem/tool/network access obniża/odrzuca isolation qualification,
- potential exposure jest monotoniczne po accepted grant,
- brak ACK nie przywraca blindness,
- contaminated discovery nie może zostać zakwalifikowane jako verified blind discovery,
- restart bez udowodnionej fresh-session boundary nie resetuje knowledge.

# 27. M7 Gate — Isolation Semantics

PASS jeśli:

```text
ENFORCED | DECLARED | UNKNOWN are mechanically distinct
CONTAMINATION is separate from isolation class
POTENTIAL_EXPOSURE_IS_MONOTONIC = PASS
BLIND_ORIGIN_REQUIRES_ACCEPTED_PRE_REVEAL_DISCOVERY = PASS
NO_FALSE_ENFORCED_FALLBACK = PASS
```

# 28. M8 — ExecutorSpec / DeliverySpec / Capability Broker

Oddzielić:

```text
StageSpec
LaneSpec
ExecutorProfile
DeliveryProfile
ProjectionPolicy
ViewManifest
```

Capability Broker musi dostarczać **positive views**: executor otrzymuje tylko graph bytes/refs jawnie dozwolone w danej fazie. Raw ref nie jest view ref.

Grant jest accepted przed delivery i od tej chwili liczy się jako potential exposure zgodnie z policy.

# 29. Existing executors

Adapters:

```text
SOL
CODEX
ANTIGRAVITY
```

Nie zaszywać ich zachowania w StageSpec.

---

# 30. Delivery model — grant before delivery

Każda metoda delivery implementuje wspólny kontrakt:

```text
prepare positive view
→ validate resolver closure
→ accept grant
→ advance potential exposure / knowledge state
→ perform delivery
→ record observed ACK/result if available
```

Błąd delivery po accepted grant nie cofa exposure. Resolver transitive leak powoduje fail-closed view rejection; jeśli bytes mogły zostać ujawnione, contamination/exposure jest aktualizowane konserwatywnie.

# 31. M9 — Minimal Prompt / Package Compiler for reference slice

Zaimplementować wyłącznie deterministyczny compiler potrzebny do foundation flow:

```text
StageSpec revision
LaneSpec revision
Executor/Delivery revisions
ProjectionPolicy/ViewManifest
HistoryCut
→ prompt/package bytes
```

Compiler nie podejmuje decyzji o authority, reveal eligibility ani STOP. Jego output jest funkcją pinned inputs.

Szeroką bibliotekę promptów E1–E5 można rozwijać dopiero po foundation reference gate.

# 32. Golden prompt tests

Każdy build promptu:

```text
expected SHA
```

Zmiana promptu bez świadomego update golden test = FAIL.

---

# 33. Determinism test

```text
compile twice
→ byte-identical outputs
```

---

# 34. M9 Gate — deterministic compilation

PASS jeśli:

```text
SAME_PINNED_INPUTS → SAME_BYTES
VIEW_REF_CANNOT_RESOLVE_RAW_FORBIDDEN_ARTIFACT = PASS
COMPILER_HAS_NO_POLICY_WRITE_AUTHORITY = PASS
PROMPT/PACKAGE_INPUT_REVISIONS_ARE_PINNED = PASS
```

# 35. M10 — Schema / Identity / Canonicalization Foundation

Przed foundation vertical slice zamrozić minimalne schema contracts dla:

```text
RawDigest / ObjectDigest
BDB-CJSON profile
TypedRef
SourceGeneration
CampaignGenesis / Commit / Receipt / HistoryCut
StageSpec / LaneSpec / Attempt
KnowledgeState / DiscoveryEvent
CoverageObligation
Experiment / Observation / EvidenceQualification
StageCompletion / StopEvaluation
LegacyImport/Admission assessments
```

Exact canonical serialization i identity profile wymagają dedykowanego ADR oraz golden vectors.

# 36. Initial schemas

Minimum:

```text
SOURCE_GENERATION
CAMPAIGN_MANIFEST
RUN_MANIFEST_V2
STAGE_STATUS_V2
KNOWLEDGE_STATE
CORPUS_MANIFEST
VALIDATION_RESULT
```

---

# 37. Layered validation

Każdy accepted object przechodzi warstwy:

```text
1. parse / duplicate-key rejection
2. schema revision
3. canonicalization / digest verification
4. typed referential integrity
5. source/campaign scope
6. policy/spec binding
7. lifecycle / history-cut legality
8. evidence/applicability constraints where relevant
```

Nie używać „current by logical ID” w gate, evidence qualification ani STOP.

# 38. M11 — Corpus Engine

Dodać:

```text
DirectPredecessor
HistoricalCorpus
AuxiliaryCorpus
ExternalHoldout
```

---

# 39. Legacy corpus adapter

Umożliwić:

```text
legacy E1 auxiliary reports
legacy E2 direct predecessor
```

bez konwersji bytes.

---

# 40. Corpus validation

Każdy member:

- hash,
- source generation,
- producer stage,
- validation level.

---

# 41. M11 Gate

PASS:

```text
DIRECT_PREDECESSOR_SINGLE = YES
AUXILIARY_MULTI_REPORT = YES
CROSS_SOURCE_CORPUS_REJECTED = YES
LEGACY_E2_ACCEPTED_AS_DIRECT_PREDECESSOR = YES
```

---

# 42. M12 — Knowledge / Exposure / Discovery Engine

Zamiast osobnego mutable Knowledge/Exposure derived view zaimplementować typed accepted facts i derived views dla:

```text
GrantAccepted
PotentialExposureRecorded
IsolationQualificationAccepted
ContaminationAssessmentAccepted
KnowledgeStateAdvanced
DiscoveryRecorded
```

Knowledge State jest attempt-bound snapshotem potencjalnie dostępnych informacji, nie dowodem psychologicznej wiedzy executora.

# 43. Exposure i discovery operations

Minimalne operations:

```text
accept_grant(view, attempt, history_cut)
record_potential_exposure(...)
qualify_isolation(...)
assess_contamination(...)
advance_knowledge_state(...)
record_discovery_pre_reveal(...)
```

`DiscoveryRecorded` musi wiązać exact Attempt + SourceGeneration + KnowledgeState/HistoryCut + method/producer + own observation refs. Confirmation, novelty, prior-corpus match i previous-false-negative classification są osobnymi późniejszymi decisions/views.

# 44. M12 Gate — knowledge/discovery provenance

PASS jeśli system potrafi mechanicznie odróżnić:

```text
PRE_REVEAL_DISCOVERY
POST_REVEAL_CONFIRMATION
REPORT_ASSISTED_VERIFICATION
CONTAMINATED_DISCOVERY
UNKNOWN_ISOLATION_DISCOVERY
```

oraz nie może stworzyć verified blind-origin claimu bez accepted precursor na wcześniejszym head.

# 45. M13 — Claim Quarantine / Positive Reveal Views

Implementacja nie polega na `del hidden_fields`.

Wymagane:

```text
ProjectionPolicy
ViewManifest
ViewRef namespace
restricted resolver
transitive-closure validation
```

Faza widzi wyłącznie allowlisted fields/objects. Producer identity, support count, prior severity, report filenames i raw evidence payload są ujawniane tylko wtedy, gdy policy na to pozwala.

# 46. Quarantine tests

Testy:

- ukryte pole nie jest obecne w bytes,
- opaque ref nie ujawnia raw artifact przez resolver,
- filename/hash metadata nie zdradza niedozwolonego corpus membership,
- Coverage/Invariant refs nie tworzą transitive leak do prior finding,
- po rejected delivery nie ma „cofnięcia” potential exposure,
- claim cards nie ujawniają support count przed właściwą fazą.

# 47. M14 — Surface Inventory minimum for reference slice

Najpierw implementować **input accounting**, dopiero potem szeroką bibliotekę collectorów.

Minimalny CollectionRun rozdziela dwie domeny. `InputDisposition`:

```text
COLLECTED
UNSUPPORTED
EXCLUDED
COLLECTION_FAILED
PARSING_FAILED
PROVISIONAL   # tylko intermediate
```

`ScopeState` osobno:

```text
KNOWN_SURFACE
KNOWN_UNOBSERVED_SCOPE
UNSUPPORTED_SCOPE
EXCLUDED_SCOPE
COLLECTION_FAILED
PARSING_FAILED
PROVISIONAL_SCOPE
UNKNOWN_SCOPE
```

`InputDisposition.PROVISIONAL` nie jest terminalnym accountingiem. `ScopeState.PROVISIONAL_SCOPE` jest odrębnym pośrednim stanem denominatora i również nie spełnia completion gate; wartości nie są aliasami ani cross-domain zamiennikami.

Foundation reference repo może mieć bardzo mały collector set, ale nie może udawać pełnego denominatora.

# 48. Collector contract

```text
collect(assigned_source_manifest, collector_profile)
→ CollectionRun(
    assigned_inputs,
    capability_manifest,
    surfaces,
    input_dispositions,
    warnings/errors
)
```

Exit code 0 ani liczba emitted surfaces nie oznacza kompletności.

# 49. Surface identity / revisions

Surface key/revision musi być source-bound i zgodny z pinned `SurfaceKeyProfile`. Manual/runtime additions mają jawne provenance. Późno odkryty subsystem tworzy nową InventoryRevision i może unieważnić wcześniejsze coverage/STOP projections.

# 50. M14 Gate — inventory uncertainty represented

PASS jeśli:

```text
ALL_ASSIGNED_INPUTS_TERMINALLY_ACCOUNTED = YES
UNSUPPORTED/FAILED_SCOPE_REMAINS_VISIBLE = YES
LATE_SURFACE_CREATES_NEW_INVENTORY_REVISION = PASS
OLD_COVERAGE_RECOMPUTES_ON_NEW_DENOMINATOR = PASS
```

# 51. M15 — Invariant Registry + Coverage Obligation minimum

Implementować invariant jako versioned scoped contract oraz first-class `CoverageObligation`:

```text
target scope/surface
× invariant revision
× scenario class
× environment profile
× required qualification
× acceptance predicate
× policy obligation key
```

Globalne `REQUIRED_EVIDENCE_DEPTH` nie jest authority.

# 52. Initial invariant categories

```text
authority
durability
state consistency
completeness
trust
identity
temporal ordering
concurrency
resource boundedness
recovery
evidence integrity
supply chain
```

---

# 53. M16 — Coverage Obligation Engine

Authority coverage stanowią exact `CoverageObligation` revisions i ich kwalifikacje.

Zaimplementować dwie odrębne osie:

```text
qualification_status = UNASSESSED | IN_PROGRESS | QUALIFIED | BLOCKED | STALE
substantive_outcome  = NO_VIOLATION_OBSERVED | VIOLATION_CONFIRMED | INCONCLUSIVE
```

N/A, waiver i contradiction są osobnymi accepted decisions/refs, nie dodatkowymi execution statuses.

`Coverage Obligation / derived Coverage View` może istnieć tylko jako derived export `as_of_head`.

# 54. Coverage denominator i D0–D5

Breadth jest raportowane względem konkretnej InventoryRevision **plus jawne unresolved/unsupported/unknown scope**.

D0–D5 pozostaje konserwatywnym widokiem prezentacyjnym derived z obligations. Nie wolno:

- podnieść całej surface do D4 jednym concurrency testem,
- nadać D5 przez nieaktywowaną mutację,
- usuwać blocked/unknown scope z denominatora,
- zachować wysokiego depth po invalidation jedynego supporting evidence.

# 55. Coverage tests

Testy:

- jedno D4-like evidence nie kwalifikuje unrelated obligations,
- N/A wymaga jawnej policy/materiality decision,
- `BLOCKED` i `WAIVED` nie liczą się jako PASS,
- late Surface rewizja przelicza derived breadth,
- invalidation evidence degraduje dependent obligation status/depth,
- artificial surface splitting nie zwiększa spełnionych obligations.

# 56. M17 — Gap Engine

Dodać:

```text
DiscoveryOpportunityMap
PriorityScore
```

---

# 57. Risk inputs

Minimum:

```text
external input
trust boundary
persistence
concurrency
privilege
irreversible effect
fan-out
low coverage
historical density
```

---

# 58. Exploration protection

Scheduler musi zachować:

```text
exploration budget
```

na low-coverage surfaces.

---

# 59. M18 — Hypothesis + Discovery linkage

Hypothesis jest nowym current-v2 objectem. Musi wskazywać origin refs, a gdy pochodzi z nowego discovery — exact `DiscoveryRecorded` precursor.

Statusy:

```text
PROPOSED
PREREGISTERED
TESTING
CONFIRMED
REJECTED
UNRESOLVED
BLOCKED
```

Rejected hypotheses pozostają w canonical history i nie są kasowane.

# 60. M19 — Experiment / Execution Binding

Experiment oddziela:

```text
SUBJECT_BASELINE
TARGET_EXECUTION_VARIANT
ENVIRONMENT
HARNESS
FIXTURE
DEPENDENCY_SET
```

Materialny experiment ma preregistration albo jawny `EXPLORATORY/LEGACY` planning mode. Wynik nie może po wykonaniu zostać retroaktywnie oznaczony jako preregistered.

# 61. Preregistration enforcement

Przed execution zaakceptować exact:

```text
hypothesis/invariant/obligation
safe behavior
buggy behavior
falsification condition
observation paths
required independence
positive/negative controls
fault/seed/fixture
environment/dependency/harness refs
```

Fuzz/property campaign prerejestruje generator/oracle/bounds, nie każdy input.

# 62. M20 — Evidence Qualification Engine

Evidence nie dostaje globalnego „independence level” jako całej prawdy. Zaimplementować:

```text
raw observations
observation dependency graph
claim-relative independence assessment
applicability assessment
invalidation propagation
```

Qualification odpowiada: od jakiego failure assumption/oracle/dependency dana observation path jest naprawdę niezależna dla konkretnego claimu.

# 63. Evidence independence / invalidation tests

Testy muszą wykrywać:

- dwa procesy używające tego samego błędnego parsera ≠ independent implementation,
- fresh instance ze wspólnym storage read path ≠ independent storage observation,
- external observer współdzielący oracle ≠ independent oracle,
- harness bug może invalidować evidence bez zmiany SourceGeneration,
- invalidation propaguje się do Finding support, Coverage Obligations, SOUND/Assurance Case i STOP inputs.

# 64. M21 — Finding / Root-Cause Adjudication Engine

Zaimplementować typed revisions i accepted decisions dla:

```text
FindingClaimRevision
FindingAdjudicationDecision
RootCauseRevision
FindingAxisAssessment
SeverityAssessment
Status/Origin/Scope assessments
```

Finding i RootCause zachowują osobne identity/lifecycle. `FindingClaimRevision` jest evidence-free; M/R/I/severity/lifecycle/support należą do późniejszego `FindingAdjudicationDecision`. Root Cause membership wskazuje FindingClaimRevision jednostronnie **wyłącznie przez `RootCauseRevision.membership_edges[]`**. Nie implementować independently accepted `RootCauseMembershipRevision`; backlink/index jest derived. Evidence jednego membera nie przechodzi automatycznie na rodzeństwo ani cały cluster.

Czytelne `FINDING_LEDGER`/`ROOT_CAUSE_LEDGER` mogą być derived exports `as_of_head`, nie mutable authority.

# 65. Finding three-axis status

Obowiązkowo:

```text
mechanism
reachability
impact
```

Każda oś używa wspólnego epistemic outcome `SUPPORTED|REFUTED|INCONCLUSIVE|BLOCKED|NOT_APPLICABLE`; method/reachability-mode jest oddzielnym typed field/ref. Nie używać jednego boolean `confirmed` ani axis-specific truth enumów, które nie potrafią wyrazić REFUTED/N/A.

---

# 66. M22 — Contradiction Engine

Dodać:

```text
ContradictionCase
ContradictionResolver
```

---

# 67. Majority vote forbidden

Test:

```text
3 support + 1 reject
```

nie może automatycznie rozstrzygnąć claimu.

---

# 68. M23 — Contribution Projection

Contribution nie jest osobnym mutable ledger authority. Jest derived view z accepted discovery/adjudication/root-cause facts.

Wyliczać co najmniej:

```text
UNIQUE_CONTRIBUTION
SUPPORT_COUNT
LEAVE_ONE_OUT_CONTRIBUTION
```

Nie interpretować reveal-order marginal contribution jako obiektywnej „wartości audytora”.

# 69. Foundation Reference Slice — pierwszy pełny end-to-end proof

Przed szeroką implementacją native E1/E2, collectorów, E4 i E5 zbudować minimalny synthetic flow:

```text
INSTALLATION_BOOTSTRAP_PROFILE_V1 pin
→ INITIALIZE_CAMPAIGN_FROM_LEGACY @ EMPTY_HISTORY
→ SourceGeneration + legacy E2 raw + assessments + BootstrapAdmissionDecision
→ v2 CampaignGenesis in the same atomic commit seq=1
→ E3 StageRun + isolated Attempt
→ source/knowledge binding
→ DiscoveryRecorded
→ checkpoint
→ controlled reveal
→ Hypothesis
→ preregistered Experiment
→ Observation + EvidenceQualification
→ one CoverageObligation qualification
→ StageCompletion
→ STOP evaluation
```

Happy path **nie może** kończyć się automatycznie globalnym PASS tylko dlatego, że jeden E3 stage się zakończył. Dla synthetic policy oczekiwany może być np. `CONTINUE_REQUIRED` z powodu niewykonanych E4/E5 obligations.

# 70. FOUNDATION_REFERENCE_SLICE_GATE

Gate przechodzi dopiero, gdy happy path oraz failure paths są deterministyczne.

Obowiązkowe failure cases i exact machine outcomes:

| Case | Expected machine outcome |
|---|---|
| F1 contaminated lane | `BLIND_SLOT_NOT_SATISFIED` |
| F2 missing/unknown material surface | `STAGE_COMPLETION_BLOCKED` |
| F3 shared broken oracle | `EVIDENCE_QUALIFICATION_REJECTED` dla wymaganej independence |
| F4 crash during canonical commit | `RECOVERED_SINGLE_ACCEPTED_COMMIT` po idempotentnym retry; dokładnie jeden accepted effect |
| F5 stale legacy predecessor bundle | `BLOCKED_CANONICAL_ADMISSION` |
| F6 evidence invalidated after acceptance | `STAGE_COMPLETION_BLOCKED` do czasu nowego qualified evidence |
| F7 insufficient-data STOP przed E4/E5 | `CONTINUE_REQUIRED` + reasons `REQUIRED_STAGES_PENDING` i `INSUFFICIENT_DATA`; post-E5 odpowiednio `E6_REQUIRED` albo `BLOCKED` według jawnego budget/feasibility input |

Każdy przypadek ma prowadzić do jednego jawnego fail-closed resultu dla dokładnie zdefiniowanych inputs, a nie do warning + kontynuacji.

Happy path foundation reference slice kończy E3 przez `StopEvaluation(evaluation_context=INTERMEDIATE) = CONTINUE_REQUIRED` z powodu pending E4/E5. Ten intermediate STOP **nie wymaga** Candidate Assurance Case ani challengerów i nie może zwrócić PASS/E6_REQUIRED. Candidate/challenger finalization wchodzi dopiero w F7 po E5 lub w odpowiednim post-E6 flow.

**To jest pierwszy główny checkpoint projektu.** Dopiero po jego PASS wolno szeroko rozwijać subsystemy.

# 71. Native E1/E2 orchestration — po foundation gate

Native E1/E2 orchestration nie jest prerequisite do pierwszego v2 E3 continuation. Po foundation gate można rozwinąć:

```text
E1 discovery ensemble
E2 blind F1/F2-like precursor semantics where policy requires
Claim Quarantine
individual adjudication
root-cause normalization
shadow adjudicator
```

Legacy E1/E2 pozostają immutable i służą do pierwszego mixed-generation bootstrapu.

# 72. Legacy E2 → v2 E3 bootstrap qualification

Testować trzy admission cases:

```text
A — pełny, jednoznaczny legacy E2
B — poprawny E2 + częściowo nieznane exposure
C — brak/konflikt artifactu wymaganego przez admission
```

A może zostać canonical predecessor przy spełnionych predicates.
B może przejść lineage admission z ograniczoną historyczną blind-origin strength.
C jest `BLOCKED` dla canonical bootstrapu.

Nie tworzyć retroaktywnie v2 E0/Knowledge/Coverage/preregistration dla historycznych etapów.

# 73. Bootstrap / Orchestration Gate

PASS jeśli:

```text
LEGACY_E2_SOURCE_RECONCILIATION = EXACT per pinned profile
CANONICAL_PREDECESSOR_ADMISSION = PASS
HISTORICAL_BYTES_UNCHANGED = PASS
LEGACY_EXPOSURE_LIMITS_PRESERVED = PASS
V2_E3_ATTEMPT_BINDINGS = PASS
NO_RETROACTIVE_V2_HISTORY = PASS
```

Native E1/E2 completeness może być dalszym subsystem goal; nie blokuje udowodnionego mixed-generation E3 continuation.

# 74. M24 — E3 Blind Novelty Lanes

Dodać:

```text
E3-X
E3-Y
E3-Z
```

Każdy blind.

---

# 75. E3 checkpoint

Po blind novelty:

```text
immutable checkpoint
```

---

# 76. E3 obligation/gap reveal

Po blind checkpoint E3 może otrzymać **positive projection** bieżących Coverage Obligations, Gap Map i jawnego unknown/unsupported scope. Nie ujawniać pełnego finding corpus przez przypadkowe refs, filenames lub support metadata.

# 77. E3 gap-directed mode

Scheduler generuje target list z Gap Engine.

---

# 78. E3 cumulative reveal

Po gap phase:

```text
E1 + E2 corpus
```

---

# 79. E3 holdout reveal

Na końcu:

```text
external A1/A2/A3 corpus
```

jeśli dostępny i dozwolony.

---

# 80. M25 — Fuzzing adapter

Dodać abstraction:

```text
FuzzerAdapter
```

Nie wiązać core z jednym fuzzerem.

---

# 81. Fuzz pipeline

```text
case
→ hypothesis
→ adjudication
```

Nie:

```text
crash → finding
```

---

# 82. M26 — Differential Testing

Framework:

```text
Path A
Path B
semantic relation
diff
```

---

# 83. M27 — Metamorphic Testing

Framework:

```text
input transformation
expected relation
observed relation
```

---

# 84. E3 Integration Gate

PASS jeśli E3:

- zachowuje blind discovery provenance przed reveal,
- potrafi przejść do gap-directed mode z positive views,
- nie myli auxiliary corpus z canonical predecessor,
- wykrywa/oznacza `MULTI_STAGE_FALSE_NEGATIVE` wyłącznie z właściwego history/knowledge cut,
- utrzymuje obligations dla krytycznych surfaces bez findings,
- nie podnosi coverage na podstawie samej liczby testów,
- nie może ukryć unknown/unsupported scope przed późniejszym STOP.

# 85. M28 — State Model Engine

Dodać:

```text
StateModel
State
Transition
Guard
ForbiddenState
```

---

# 86. M29 — Temporal Invariant Engine

Dodać:

```text
TemporalInvariant
OrderingConstraint
```

---

# 87. M30 — Property/Stateful Adapter

Zdefiniować interface:

```text
PropertyTestAdapter
StatefulTestAdapter
```

---

# 88. M31 — Bounded Model Exploration

Małe state spaces.

Nie próbować modelować całej aplikacji.

---

# 89. M32 — Concurrency Schedule Engine

Dodać:

```text
SchedulePoint
InterleavingSeed
Replay
```

---

# 90. M33 — Crash/Recovery Engine

Dodać:

```text
CrashPoint
Restart
RecoveryInvariant
```

---

# 91. M34 — Endurance Engine

Dodać metrics:

```text
thread count
resource count
queue depth
map sizes
pending work
memory trend
```

---

# 92. M35 — Causal Chain Engine

Dodać:

```text
trigger
path
state transition
observation
impact
```

---

# 93. E4 Integration Gate

PASS:

```text
root-cause family
state model
temporal invariant
property/stateful test
crash/recovery
concurrency schedule
causal chain
coverage update
```

na synthetic benchmarku.

---

# 94. M36 — Failure Interaction Graph

Dodać graph engine.

---

# 95. M37 — Interaction Scheduler

Risk-ranked:

```text
pairwise
selected 3-way
selected 4-way
```

---

# 96. M38 — Mutation Framework

Mutation Framework rozdziela:

```text
IMPLEMENTATION_MUTATION
ORACLE_MUTATION
SPEC/ASSUMPTION_MUTATION
```

Każda mutacja ma activation proof. `PASS` bez udowodnionej aktywacji nie jest `MUTANT_KILLED`.

Oracle mutation wymaga kontrastowego eksperymentu z known-defective target / control; samo osłabienie observera przy clean target nie dowodzi jakości oracle.

# 97. Mutation target policy

Statusy minimum:

```text
MUTANT_KILLED
MUTANT_SURVIVED
MUTATION_NOT_ACTIVATED
REDUNDANT_OBSERVER
HARNESS_FAILURE
INVALID_MUTATION
```

D5-like derived depth może korzystać tylko z applicable, activated i policy-relevant mutation obligations.

# 98. M39 — Auditor Calibration

Calibration corpus rozdziela:

```text
seeded known defects
clean controls
unseeded real findings
development corpus
calibration corpus
holdout corpus
```

Unseeded real finding nie jest automatycznie false positive. Calibration mierzy działanie BDB na znanym ground truth i nie jest dowodem kompletności realnego audytu.

# 99. M40 — Final Skeptic

Lane:

```text
E5-B1 FALSE_POSITIVE_SKEPTIC
```

---

# 100. M41 — False Negative Hunter capability

Zaimplementować i przetestować rolę/lane spec:

```text
E5-B2 FALSE_NEGATIVE_HUNTER
```

Na tym milestone **nie uruchamiać final challengera** przed CandidateAssuranceCase; execution należy do M43B.

---

# 101. M42 — Residual Risk Register / Projection

Residual Risk jest versioned assessment powiązanym z exact obligations, blockers, waivers, unknown scope i evidence applicability. Może mieć derived register/export, ale materialne acceptance/waiver decisions należą do canonical history.

# 102. M43 — Candidate Assurance Case (koniec E5A)

Po E1–E4 oraz wymaganych E5A attack/synthesis outputs powstaje **Candidate Assurance Case** na exact history cut. Nie wymaga jeszcze E5 StageCompletion ani STOP resultu.

# 102.1. M43B — E5B final challenger execution + E5 StageCompletion

Dopiero po candidate uruchomić obie baseline role:

```text
CandidateAssuranceCase
→ E5-B1 ChallengerAssignment → ChallengerResult
→ E5-B2 ChallengerAssignment → ChallengerResult
→ E5 StageCompletion
```

Oba results muszą wskazywać tę samą exact candidate revision. Każda materialna zmiana candidate unieważnia oba baseline results i wymaga ponownego wykonania obu ról; scoped reuse jest poza profilem V1.

# 103. M44 — STOP Gate Engine

STOP jest pure formal evaluation na exact HistoryCut, nie metryką saturation.

```text
continuation_decision = PASS | CONTINUE_REQUIRED | E6_REQUIRED | BLOCKED
assurance_level       = ADEQUATE_FOR_DECLARED_SCOPE | BOUNDED | INSUFFICIENT
release_readiness     = READY | READY_WITH_RESIDUAL_RISK | TECHNICALLY_NOT_READY | QUALIFICATION_BLOCKED
```

`termination_state = OPEN | COMPLETED | COMPLETED_LIMITED` zmienia dopiero osobny accepted CampaignConclusion. `COMPLETED_LIMITED` nie jest piątym wynikiem STOP i nie zamienia BLOCKED w PASS.

Input model rozróżnia co najmniej:

```text
UNKNOWN
BLOCKED
INSUFFICIENT_DATA
NOT_APPLICABLE
WAIVED
ACCEPTED_RESIDUAL_RISK
OPEN_CONTRADICTION
TESTING_CONTRADICTION
INVALIDATED_EVIDENCE
UNKNOWN_SURFACE_SCOPE
```

Audit termination, assurance strength i release readiness source są osobnymi decisions. STOP nie może pośrednio uznać source za release-ready tylko dlatego, że campaign może się zakończyć.

# 104. M45 — Adaptive E6 Generator

E6 może powstać tylko z jawnego STOP resultu. Dziedziczy governing source, policy, unresolved obligations i materiality.

E6 nie może:

- zmniejszyć wymagań, które spowodowały FAIL/BLOCKED,
- usunąć unknown scope przez zmianę denominatora,
- przedefiniować isolation po zobaczeniu resultu,
- uznać unresolved contradiction za PASS.

Może dodać nowe surfaces/invariants/obligations, ale wtedy wraca do globalnego STOP na nowym accepted head.

# 105. E5 / STOP Integration Gate

PASS jeśli:

```text
CandidateAssuranceCase precedes challengers
CandidateAssuranceCase precedes both baseline challenger assignments
Both ChallengerResults precede E5 StageCompletion
E5 StageCompletion precedes FINAL_POST_E5 StopEvaluation
StopEvaluation precedes CampaignConclusion; CampaignConclusion precedes FinalAssuranceCase
NO_ASSURANCE_CASE_STOP_CYCLE = PASS
UNKNOWN/BLOCKED cannot silently become PASS
INVALIDATION_REOPENS_DEPENDENT_STOP_INPUTS = PASS
E6_PRESERVES_OR_STRENGTHENS_OBLIGATIONS = PASS
```

# 105.1. M45A — Release lifecycle + successor assurance

Implementować trzy release basis: `STOP_AXIS_MATERIALIZATION`, `FRESH_RELEASE_QUALIFICATION` (pierwsza po release-only drift, bez predecessor) i `RELEASE_REASSESSMENT` (previous ref wymagany). Audit-basis invalidation nie jest release-only: tworzy successor campaign. Successor acceptance musi mieć backward predecessor/conclusion/trigger refs, current applicability selection przez typed `SuccessorCampaignSelectionDecision` i fail-closed branch-conflict handling.

Gate obejmuje drift przed pierwszą qualification, drift po qualification, S21/S22 oraz konkurencyjne successor proposal branches.

# 106. M46 — Standalone Build System

Dodać:

```text
build/build_single_file.py
```

---

# 107. Embedded payload

Pakować:

- modules,
- schemas,
- StageSpecs,
- LaneSpecs,
- templates.

---

# 108. Reproducible build gate

Dwa buildy:

```text
same input
→ same SHA
```

---

# 109. M47 — CLI

Komendy:

```text
campaign create
campaign status
stage prepare
lane prepare
validate
continue
self-test
build
```

---

# 110. M48 — Interactive UI

Dopiero po core API.

UI nie może zawierać własnej business logic.

---

# 111. M49 — Release Validator

Final standalone przechodzi:

- self-test,
- compatibility,
- build hash verification,
- embedded payload verification.

---

# 112. M50 — Self-Audit v2

Przed release wykonać audyt samego BDB v2.

Zakres:

```text
source integrity
artifact validators
gate bypass
schema bypass
cross-source mix
exposure leak
prompt compiler
campaign FSM
corpus contamination
```

---

# 113. Release blockers

v2.0.0 BLOCKED jeśli:

- compatibility FAIL,
- reveal bypass exists,
- cross-source evidence accepted,
- Stage FSM bypass,
- invalid artifact accepted,
- deterministic build FAIL,
- critical mutation survives,
- self-audit unresolved HIGH.

---

# 114. P0/P1/P2 implementation priority

Ta sekcja jest **widokiem** normatywnej mapy F0–F8, nie osobnym harmonogramem.

## P0 — foundation przed szerokimi feature'ami

```text
Legacy freeze + fixture truth
Dual compatibility gates
Canonical history / transactional authority
Identity + BDB-CJSON ADR + typed refs
Campaign/Stage/Lane/Attempt minimum
Isolation / Capability Broker / Knowledge / Discovery
Legacy admission A/B/C
Minimal Inventory + Invariant + Coverage Obligation
Minimal Experiment/Evidence/StageCompletion/STOP
Foundation Reference Slice + failure paths
```

## P1 — pełny audyt v2

```text
Corpus expansion
Claim Quarantine
Finding/RootCause/Contradiction
native E1/E2 orchestration
E3 gap-directed / holdout
replay / invalidation
```

## P2 — hyper-audit

```text
fuzzing
metamorphic / differential
stateful / temporal / model exploration
concurrency schedules
failure interactions
mutation / calibration
challengers / E6
```

# 115. Zakaz równoległego budowania wszystkiego

Nie rozpoczynać szerokiego E4/E5 ani UI polish przed `FOUNDATION_REFERENCE_SLICE_GATE = PASS`.

E5 może rozwijać się dopiero, gdy stabilne są:

```text
canonical history
identity/revisions
knowledge/discovery provenance
Coverage Obligations
Evidence Qualification + invalidation
Finding/RootCause/Contradiction
```

Brak tego gate'u oznacza, że kolejne moduły tylko powielają niezweryfikowane założenia foundation.

# 116. Dependency graph

```text
Legacy Freeze + Fixture Truth
        │
        ▼
Minimal Assurance Primitives
        │
        ▼
Dual Compatibility Gates
        │
        ▼
Trust / Authority / History
        │
        ▼
Identity / Typed Revisions / SourceGeneration
        │
        ▼
Campaign / Stage / Lane / Attempt minimum
        │
        ├────────► Isolation / Capability / Knowledge / Discovery
        │
        └────────► Legacy Admission
                         │
                         ▼
              Inventory / Invariant / Obligation minimum
                         │
                         ▼
             Experiment / Evidence Qualification minimum
                         │
                         ▼
                StageCompletion / STOP minimum
                         │
                         ▼
              FOUNDATION REFERENCE SLICE
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
       Domain Expansion          native E1/E2
             │                       │
             └───────────┬───────────┘
                         ▼
                    E3 → E4 → E5
                         │
                         ▼
                STOP / E6 / Release
```

# 117. Commit sizing

Każdy commit powinien:

- mieć jeden główny cel,
- dodawać testy,
- nie mieszać refactor + feature + migration,
- być możliwy do review niezależnie.

---

# 118. Commit message format

Przykład:

```text
MIG-006: extract F1 handoff validator
CORE-014: add canonical JSON serializer
CAM-003: reject cross-source stage transition
E3-005: add coverage reveal checkpoint
```

---

# 119. Pull request gate

Każdy PR:

```text
unit tests
compatibility tests
schema tests
self-test
```

Dla prompt/compiler:

```text
golden tests
```

---

# 120. CI lanes

Rekomendowane:

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

Nie wszystkie muszą działać na każdy mały commit z pełnym ciężarem, ale release branch musi przejść komplet.

---

# 121. Type checking

Nowy codebase powinien używać pełniejszych typów.

Minimalnie:

```text
mypy/pyright equivalent
```

Brak type safety w contracts zwiększa ryzyko błędów migracyjnych.

---

# 122. Static quality

Preferować:

- dataclasses/Pydantic-like typed models lub własne typed records,
- enums,
- explicit exceptions,
- pure validators,
- dependency injection.

---

# 123. No hidden global state

Ograniczyć:

```text
global DATA
```

Preferować:

```text
ApplicationContext
Registries
Repositories
```

jawnie przekazywane.

---

# 124. Clock injection

Do testowania timestamps:

```text
Clock interface
```

zamiast bezpośredniego `datetime.now()` w core.

---

# 125. Filesystem abstraction

Krytyczne writes:

```text
ArtifactStore
```

ułatwiające fault injection.

---

# 126. Hash authority tests

Każdy write:

```text
write
readback
hash
accept
```

---

# 127. Atomic accepted-commit helper

Zamiast projektować tylko atomic file write, foundation potrzebuje helper/service realizującego logiczną granicę accepted commit:

```text
immutable object closure
+ CommitBody
+ Receipt
+ AcceptedHead update
```

Reference backend może używać transakcji DB i osobnego content store, ale crash test musi wykazać all-or-nothing visibility. File-level temp+rename pozostaje pomocniczym primitive dla raw artifacts/exports, nie modelem authority całej campaign.

# 128. Failure injection hooks

Dodać od początku do:

- ArtifactStore,
- network adapters,
- clock,
- process runner.

Nie dopiero w E4.

---

# 129. Process runner abstraction

Wszystkie subprocess calls przez:

```text
CommandRunner
```

rejestrujący real exit code.

---

# 130. Network abstraction

Jeżeli application runtime pobiera remote source:

```text
SourceFetcher
```

z ograniczonym scope.

---

# 131. Security defaults

```text
network = deny except explicit source
destructive = deny
external state change = deny
```

---

# 132. Prompt injection boundary

Audited repository content nie może zmienić:

- specs,
- permissions,
- reveal policy,
- stage transitions.

---

# 133. Foundation completion milestone

Formalny foundation milestone przed feature completeness:

```text
V2_FOUNDATION_REFERENCE_READY
```

Wymaga jednocześnie:

```text
DUAL_COMPATIBILITY_GATES = PASS
AUTHORITY_HISTORY_GATE = PASS
IDENTITY_SCHEMA_GATE = PASS
FOUNDATION_REFERENCE_SLICE_GATE = PASS
STOP_REFUSAL_PATH = PASS
```

# 134. E3 bootstrap milestone

Formalny real/synthetic proof continuity:

```text
legacy E2 exact raw + admission
+
legacy E1 auxiliary corpus where admitted
+
v2 Campaign/Stage/Lane/Attempt
+
current bootstrap constitution
→ valid E3 start
```

To dowodzi continuity bez przepisywania historii. Osobno kwalifikuje lineage admission i historyczną exposure confidence.

# 135. E3 bootstrap blockers

- legacy E2 SourceGeneration reconciliation nie jest exact dla wymaganej roli,
- canonical predecessor admission jest BLOCKED/CONFLICT,
- wymagany raw F1/F2/final artifact jest missing/substitute,
- bootstrap policy/spec revision nie jest pinned,
- historyczne exposure jest niewystarczające do żądanego blind-origin claimu,
- v2 próbuje retroaktywnie utworzyć E0/Knowledge/Coverage history dla legacy etapu.

# 136. Historical lineage lock

Po imporcie legacy lineage:

```text
immutable
```

Nie pozwalać UI „poprawić” stage label.

---

# 137. Migration metadata

Każdy imported artifact:

```text
migration event
adapter version
original SHA
```

---

# 138. Developer documentation

Przy module creation dodawać:

- docstrings,
- invariants,
- error contracts,
- test references.

---

# 139. ADR process

ADR jest wymagany dla zmian foundation, w szczególności:

```text
canonical serialization profile (BDB-CJSON-1)
RawDigest vs ObjectDigest semantics
logical ID / revision model
SourceIdentity profile
storage authority / transaction profile
isolation assurance backend
STOP decision semantics
legacy admission predicates
standalone build/runtime closure
```

ADR nie powiela całych schemas. Wskazuje decyzję, alternatywy, trade-offs, migration impact i normatywny target contract.

# 140. No premature UI polish

Najpierw:

```text
correct core
```

Potem UX.

Nie odwrotnie.

---

# 141. Performance

Nie optymalizować przed correctness.

Ale walidatory ZIP muszą mieć:

- size limits,
- member count limits,
- streaming where needed.

---

# 142. Logging

Aplikacja ma structured internal logs do diagnostyki działania programu.

Nie mieszać ich z canonical accepted history ani z immutable raw observations/evidence. Diagnostic log może zawierać execution diagnostics, ale nie może ustanawiać lineage, evidence qualification, coverage lub STOP state.

# 143. Canonical history vs application log

Rozdzielić:

```text
CANONICAL ACCEPTED HISTORY
```

od:

```text
APPLICATION / DIAGNOSTIC LOG
```

`AUDIT_LEDGER.jsonl`, Coverage/Exposure/Contribution/Traceability exports mogą być derived views `as_of_head`; nie są niezależnymi mutable authority. Diagnostic log może być rotowany i nie uczestniczy w assurance decisions.

# 144. Recovery

Recovery zawsze zaczyna od canonical accepted head i immutable object closure. Projekcje/cache można przebudować.

Po crash:

- incomplete/unaccepted staging objects nie stają się history facts,
- receipt retry jest idempotentny,
- partial projection nie może wyprzedzić accepted head,
- dangling accepted ref jest corruption i fail-closed.

# 145. Resume

Resume wykorzystuje exact:

```text
campaign_id
accepted head
StageRun/LaneRun/Attempt projection as_of_head
pinned SourceGeneration
pinned policy/spec/schema refs
KnowledgeState/allowed view for pending attempt
```

Nie „odtwarza” execution przez zgadywanie z timestampów, filenames albo ostatniego log line.

# 146. Resume test

Obowiązkowe recovery/resume cases:

```text
crash before commit
crash after commit before client ACK
crash during projection rebuild
retry same command
conflicting retry payload
late result after attempt cancellation
resume with stale expected head
resume after evidence invalidation
```

Każdy ma jeden przewidywalny outcome.

# 147. Release candidate sequence

```text
v2.0.0-alpha.1
v2.0.0-alpha.2
v2.0.0-beta.1
v2.0.0-rc.1
v2.0.0
```

Każdy poziom ma większy gate.

---

# 148. Alpha gate

- compatibility core,
- Stage/Lane,
- corpus,
- exposure,
- surface/coverage.

---

# 149. Beta gate

- E1/E2 complete,
- E3 operational,
- prompt compiler,
- standalone build.

---

# 150. RC gate

- E4/E5,
- stop gate,
- self-audit,
- no unresolved HIGH.

---

# 151. Release gate

- reproducible build,
- compatibility PASS,
- full test suite,
- documentation complete,
- release manifest.

---

# 152. Documentation gate

Wymagane przed v2.0:

```text
Architecture
Migration
Data Contracts
Implementation Roadmap
Test/Self-Audit Plan
README
```

---

# 153. Release manifest

```text
RELEASE_MANIFEST.json
```

Pola:

```text
application_version
git_commit
source_tree
standalone_sha256
protocol_version
wrapper_release
schema_registry_hash
stage_spec_hash
lane_spec_hash
test_summary
compatibility_summary
```

---

# 154. Supply-chain checks

Release pipeline sprawdza:

- dependency pinning,
- workflow permissions,
- artifact hash,
- release provenance.

---

# 155. Rollback strategy

Jeśli v2 RC fails:

- v1.4.4 remains available,
- no legacy artifact mutation,
- no migration state destructive upgrade.

---

# 156. Data migration rollback

Importer tworzy refs.

Nie przenosi/usuwa originals.

Rollback = usunięcie v2 refs/state, originals intact.

---

# 157. Milestone acceptance record

Każda faza F0–F8 ma `MilestoneAcceptance` związany z exact HistoryCut/build/source refs:

```text
milestone_id
phase_id
accepted_history_cut
build_revision
required_gate_results[]
known_blockers[]
accepted_limitations[]
next_phase_allowed
```

Nie tworzyć dwóch równoległych milestone numbering systems. `M0…M50` są slice IDs; `F0…F8` są program phases.

# 158. Known limitations registry

Nie ukrywać braków.

Plik:

```text
KNOWN_LIMITATIONS.md
```

aktualizowany przy release candidates.

---

# 159. Risk register implementacji

Największe ryzyka:

1. utrata legacy semantics,
2. zbyt duży refactor na raz,
3. circular compatibility tests,
4. schema sprawl,
5. prompt compiler drift,
6. hidden cross-source mixing,
7. overcomplicated StageSpec,
8. premature E4/E5,
9. self-test false confidence.

---

# 160. Ryzyko circular compatibility

Największe ryzyko:

```text
v1 and v2 agree
→ conclusion: v2 is correct
```

Mitigacja:

```text
legacy-observed outcome
≠ independent safe expectation

PRESERVATION GATE
+
CORRECTNESS GATE
```

Known legacy bug musi mieć jawny fixture classification lub intentional-hardening decision.

# 161. Ryzyko schema / artifact sprawl

Nie każdy koncept wymaga osobnego mutable pliku/ledgera.

Preferować:

```text
canonical accepted facts + immutable objects
→ derived projections / exports
```

Nowy artifact family jest uzasadniony tylko, gdy potrzebuje własnego immutable contractu, transportu lub retention boundary. Inaczej powinien być typed fact albo derived view.

# 162. Ryzyko over-engineering

Przed dodaniem nowego engine/ledgera zapytać:

1. Czy ta informacja może być accepted factem w canonical history?
2. Czy potrzebny jest własny lifecycle/authority, czy wystarczy projection?
3. Czy mechanizm zwiększa faktyczną siłę assurance, czy tylko liczbę struktur?
4. Czy foundation reference flow lub adversarial scenario wymaga go teraz?

Jeśli nie — `DERIVE`, `DEFER` albo `REMOVE`.

# 163. Risk-based implementation order

Najpierw implementować rzeczy, których późniejsza zmiana byłaby najbardziej kosztowna i które wpływają na semantykę reszty:

```text
Trust boundary
→ Authority / Transaction / History
→ Identity / SourceGeneration / Typed Revisions
→ Attempt / Isolation / Knowledge / Discovery provenance
→ Legacy admission
→ Coverage Obligation semantics
→ Evidence applicability/independence
→ Stage/Campaign finalization
→ STOP
→ dopiero szerokie E3/E4/E5 capability
```

# 164. Minimal v2 threshold

Minimalny próg do rozpoczęcia **szerokiej** implementacji v2 (nie release) to:

```text
DUAL_COMPATIBILITY_GATES = PASS
AUTHORITY_HISTORY_GATE = PASS
IDENTITY_SCHEMA_GATE = PASS
FOUNDATION_REFERENCE_SLICE_GATE = PASS
STOP_REFUSAL_PATH = PASS
```

Nie wymaga finalizacji całych E4/E5 schemas ani UI.

# 165. First production-use threshold

Pierwsze użycie na realnym audycie wymaga dodatkowo:

- zakwalifikowanego rzeczywistego legacy bootstrapu albo native predecessor,
- stabilnych inventory/obligation/evidence contracts dla używanego scope,
- isolation backend odpowiadającego deklarowanej klasie,
- recovery/resume qualification,
- deterministic build/runtime profile,
- self-audit bez unresolved release-changing foundation finding.

# 166. No real audit before foundation gate

Nie używać v2 do produkcyjnego audytu tylko dlatego, że pojedyncze komendy działają. Synthetic/reference campaigns są dozwolone wcześniej, ale muszą być oznaczone jako qualification fixtures.

# 167. Reference synthetic repository

Stworzyć mały benchmark repo z:

- routes,
- persistence,
- parser,
- thread,
- known XSS sink,
- retry bug,
- clean controls.

Służy end-to-end tests.

---

# 168. Calibration benchmark

Oddzielny od compatibility corpus.

Ma znane synthetic defects.

---

# 169. Test data separation

```text
legacy fixtures
synthetic system benchmark
auditor calibration corpus
real audit corpus
```

muszą być oddzielone.

---

# 170. Release self-audit corpus

Self-audit v2 nie powinien znać wszystkich seeded defects w tej samej lane.

---

# 171. E2 shadow checker implementation

Nie pełny drugi E2.

Dedykowana rola:

- normalization,
- severity,
- origin,
- evidence linkage.

---

# 172. E5 challengers implementation

Muszą mieć różne allowed knowledge/task goals.

Nie łączyć w jeden prompt.

---

# 173. Saturation implementation

Saturation jest pomocniczym evidence o marginalnej wartości dalszego discovery, nie completeness proof i nie samodzielny STOP authority.

Konkretne wymagania typu liczba rounds, method families, budget czy novelty thresholds należą do versioned **EffortProfile/PolicyProfile**. Domyślna wartość może istnieć, ale nie jest wiecznym globalnym invariantem BDB.

# 174. Capture-recapture status

Optional informational.

Nigdy hard stop gate.

---

# 175. Coverage priority

Priorytetem jest poprawność `Coverage Obligation` + Inventory uncertainty semantics, nie efektowny D0–D5 dashboard. Derived depth może powstać po tym, jak obligations, invalidation i N/A/waiver semantics przejdą reference tests.

# 176. Invariant priority

Invariant Registry wcześniej niż property testing.

Powód:

> property test bez formalnego property registry traci traceability.

---

# 177. Experiment preregistration priority

Przed dużą liczbą dynamic tests.

---

# 178. Replay priority

Przed final HIGH claim support.

---

# 179. Evidence invalidation priority

Evidence invalidation jest P0/P1 boundary, bo bez niej raz zdobyte evidence mogłoby wiecznie utrzymywać Coverage/STOP mimo wykrycia błędu harnessu/oracle. Implementować propagację przed finalnym E5/STOP engine.

# 180. Remediation engine

Nie jest częścią pierwszego core E1–E5.

Implementować po final audit pipeline.

---

# 181. Requalification engine

Po Evidence Invalidation Graph.

---

# 182. Post-v2 roadmap

Po 2.0 można rozważyć:

- plugin architecture dla analyzerów,
- distributed lanes,
- web UI,
- richer graph visualization,
- remote execution workers.

Nie w 2.0 core.

---

# 183. Definition of Done — v2.0.0

BDB Audit v2.0.0 jest gotowe, gdy:

1. legacy v1.4.4 baseline i exact historical artifacts są zamrożone,
2. fixture corpus ma osobne legacy-observed i independent-safe expectations,
3. preservation gate PASS,
4. validator correctness gate PASS,
5. canonical accepted history/transaction/recovery PASS,
6. identity/serialization/typed-ref ADR i golden vectors PASS,
7. Campaign/Stage/Lane/Attempt lifecycle jest deterministic i idempotentny,
8. Knowledge/Isolation/Capability Broker/Discovery provenance działa fail-closed,
9. legacy E2 → v2 E3 admission A/B/C działa bez retroactive history,
10. Surface Inventory reprezentuje unsupported/failed/unknown scope,
11. Invariant + Coverage Obligation authority działa; D0–D5 jest tylko derived,
12. Experiment/Observation/Evidence Qualification i transitive invalidation działają,
13. Finding/RootCause/Contradiction semantics działają bez evidence inheritance shortcut,
14. foundation reference slice oraz wszystkie obowiązkowe failure paths PASS,
15. native E1/E2 albo udokumentowany mixed-generation flow działa zgodnie z release scope,
16. E3 blind/gap/holdout flow działa,
17. E4 model/state/temporal flow zawiera model-fidelity evidence,
18. E5 interaction/mutation/calibration/challengers działa,
19. oracle mutation wymaga activation + contrast,
20. Candidate Assurance Case → challengers → STOP → CampaignConclusion → Final Assurance Case jest acykliczne,
21. STOP rozróżnia unknown/blocked/insufficient/N/A/waived/invalidated,
22. Adaptive E6 nie może osłabić obligations,
23. CampaignConclusion i ReleaseQualification są osobnymi decyzjami,
24. standalone build ma zamknięty input/runtime contract i jest reproducible w zadeklarowanym profile,
25. recovery/resume/crash qualification PASS,
26. full self-test + self-audit nie mają unresolved release-changing finding,
27. dokumentacja i ADR baseline są spójne z implementacją.

# 184. Rekomendowana pierwsza sekwencja commitów

Pierwsze commity powinny być małe i foundation-oriented:

```text
MIG-001 freeze v1.4.4 exact reference
MIG-002 add legacy fixture bytes + legacy-observed outcomes
MIG-003 add independent safe expectations / known-legacy-bug registry
CORE-001 raw hashing + ZIP safety
CORE-002 legacy manifest/checkpoint parsers
COMPAT-001 dual preservation/correctness harness
COMPAT-002 pass dual foundation compatibility gates

FOUND-001 BDB-CJSON/RawDigest/ObjectDigest golden vectors
FOUND-002 typed refs + SourceGeneration identity
FOUND-003 canonical Commit/Receipt/AcceptedHead
FOUND-004 transactional vault + crash tests
FOUND-005 Campaign/Stage/Lane/Attempt minimum FSM
FOUND-006 isolation/knowledge/capability broker minimum
FOUND-007 legacy admission assessments A/B/C
FOUND-008 minimal inventory/invariant/coverage obligation
FOUND-009 minimal experiment/evidence qualification/invalidation
FOUND-010 StageCompletion + STOP minimum
REF-001 legacy E2 → v2 E3 reference happy path
REF-002 contaminated/missing-surface/shared-oracle failure paths
REF-003 crash/stale-bundle/invalidated-evidence/insufficient-STOP paths
```

Dopiero po `FOUNDATION_REFERENCE_SLICE_GATE = PASS` rozszerzać native E1/E2, collectors, E4/E5 i UI.

# 185. Najważniejszy checkpoint projektu

Najważniejszym checkpointem przed szerokim feature development jest:

```text
FOUNDATION_REFERENCE_SLICE_GATE = PASS
```

Obejmuje on wcześniejsze dual compatibility, authority/history, identity, isolation, minimal obligation/evidence semantics oraz happy/failure paths. Sam `LEGACY_COMPATIBILITY_GATE` nie wystarcza.

# 186. Drugi najważniejszy checkpoint

```text
LEGACY_E2_TO_V2_E3_BOOTSTRAP = PASS
```

Dowodzi, że nowa aplikacja rzeczywiście kontynuuje dotychczasowy audyt bez przepisywania historii i z jawnymi ograniczeniami legacy exposure/admission.

# 187. Trzeci najważniejszy checkpoint

```text
FINAL_STOP_REFUSAL_AND_INVALIDATION_SELF_TEST = PASS
```

BDB musi umieć odmówić zakończenia/assurance PASS przy unknown scope, insufficient data, unresolved contradiction lub invalidated evidence — nawet jeśli wszystkie wcześniejsze moduły technicznie „wykonały się”.

# 188. Finalna rekomendacja realizacyjna

Nie optymalizować roadmapy pod minimalną liczbę commitów ani maksymalną liczbę równoległych subsystemów.

Optymalizować ją pod:

```text
FOUNDATION FALSIFIABILITY
+
REVIEWABILITY
+
REGRESSION LOCALIZATION
+
INDEPENDENT CORRECTNESS CHECKS
+
FAIL-CLOSED CONTINUITY
```

Najlepszy proces:

```text
mały contract
→ test vectors
→ minimal implementation
→ happy path
→ adversarial/failure path
→ accepted milestone
→ dopiero rozszerzenie
```

Jeżeli foundation reference slice wykryje wadę authority, isolation, identity, coverage albo STOP, wracamy do odpowiedniego contract/ADR zamiast „obchodzić” problem kolejnym ledgerem lub wyjątkiem.

Docelowa kolejność pozostaje:

```text
FREEZE
→ QUALIFY
→ PROVE FOUNDATION
→ BOOTSTRAP
→ EXPAND
→ DEEPEN
→ ATTACK
→ SELF-AUDIT
→ RELEASE
```


# R5.3 final authority/identity gate

Before implementation baseline use, validator MUST prove: StopInput direct obligation/invalidation refs, Candidate direct coverage refs, current-commit CommandEnvelope binding, prior campaign binding for normal commands, HistoryCut governing-spec/schema domain separation, and receipt↔commit command equality. Current vector set: `BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json`.

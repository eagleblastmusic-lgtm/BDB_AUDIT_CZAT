# BDB Audit v2 R5.3 — Codex Task Context for F1

**Purpose:** task-scoped, non-normative convenience packet for Codex implementing the complete phase **F1 — Minimal Assurance Primitives & Dual Compatibility (M2–M3 / PR-003–PR-006)**.

This packet contains exact excerpts and exact machine-data subsets from the governing R5.3 sources needed for F1. It does **not** replace the full source documents and does not create new semantics.

If an exact full source document available in the repository/workspace conflicts with this packet, **the full R5.3 source document wins**. Do not silently reconcile a material conflict; report `SPEC_CONFLICT`.

## Source identities

All source bytes below were re-read from the qualified R5.3 Google Drive corpus before this packet was generated.

- `BDB_AUDIT_V2_IMPLEMENTATION_EXECUTION_PLAN_R5_3.md` — SHA-256 `7ec2de0ccfba3672a9a399af2b77f6fc5dfb42d87645e65206ca8bb5c8007d59` — subordinate execution decomposition.
- `BDB_AUDIT_V2_IMPLEMENTATION_ROADMAP.md` — SHA-256 `b127e249b8db0bd2f17c5e6f77ed3d2d342fc8fb187e3ec720de0b7bd1fac018` — normative phase/M-slice ordering and M2/M3 gates.
- `BDB_AUDIT_V2_TEST_AND_SELF_AUDIT_PLAN.md` — SHA-256 `abf92ea199d57c78eb25dc0ca41ed9267a9d20d79401b3c468c01c4e4371b598` — normative test/falsification requirements.
- `BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS.md` — SHA-256 `658f8866ca1a1330db9be582b13b47e87381de2208c53ee64ed9e47a8d3e15ee` — normative data/identity/reference contracts.
- `BDB_AUDIT_V1_TO_V2_MIGRATION_AND_COMPATIBILITY.md` — SHA-256 `d31fd0d84a4e5c14aced3eae3a67bc704ed5d75d9ca6a8a1ed6943100352358f` — normative legacy preservation/correctness semantics.
- `ADR-006_CANONICAL_SERIALIZATION_AND_IDENTITY_PROFILE.md` — SHA-256 `df7e40fc062f5fcc2309276cc6fd4b529c060fb4f5f24fe39484eb66c0153dfa` — normative BDB-CJSON-1 / digest / ID profile.
- `BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY.json` — SHA-256 `5a89cfe26d927c9bf2638ad1e656b4ed810544f8d35e3e0ddf1365cd54b7343c` — pinned machine registry.
- `BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json` — SHA-256 `7bee0013d179adc8eba14d07c2c3ea159de0b8e37be9a9f6dcd55969550b7772` — pinned golden vector set.
- `BDB_AUDIT_V2_AUTHOR_BASELINE_QUALIFICATION_R5_3.json` — SHA-256 `de7c79c3a7ec3f3879d702993e60f882f01f66ecbc00c67e8084de84dc5f99a0` — external governance evidence permitting implementation under author-only assurance.

---

# A. Execution Plan — global execution rules, DoR/DoD and complete F1 work packages

Source: `BDB_AUDIT_V2_IMPLEMENTATION_EXECUTION_PLAN_R5_3.md`.

```markdown
# 1. Non-negotiable execution rules

1. One PR / work package has one primary semantic objective.
2. Every behavior-changing PR includes tests in the same PR.
3. No broad E4/E5, UI polish, plugin ecosystem, or performance rewrite before the Foundation Reference Slice gate.
4. No accepted-state mutation may bypass the Coordinator/Authority boundary.
5. No “latest by logical ID” may replace exact refs in gates, evidence qualification, STOP, history or release decisions.
6. No projection/report/cache/log becomes runtime authority.
7. No optimization may change canonical bytes, digests, ordering, failure codes or decision semantics without an explicit normative change.
8. Each phase F0–F8 ends with a `MilestoneAcceptance` tied to exact source/build/history inputs when the v2 history engine exists; before that, retain an equivalent qualification artifact with exact Git/source hashes.
```

```markdown
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
```

```markdown
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
```

---

# B. Normative Roadmap — foundation-first ordering, M2, M3 and the dual compatibility gate

Source: `BDB_AUDIT_V2_IMPLEMENTATION_ROADMAP.md`.

```markdown
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
```

```markdown
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
```

---

# C. ADR-006 — canonical bytes, RawDigest/ObjectDigest, IDs, TypedRef and required vectors

Source: `ADR-006_CANONICAL_SERIALIZATION_AND_IDENTITY_PROFILE.md`.

```markdown
## 1. Decyzja

BDB Audit v2 używa profilu `BDB-CJSON-1` dla canonical semantic objects oraz dwóch nierównoważnych digest semantics: `RawDigest` i `ObjectDigest`.

Profil jest oparty na JSON Canonicalization Scheme (JCS) z dodatkowymi restrykcjami domenowymi BDB eliminującymi ambiguity w keys, numbers i identity-bearing values.

## 2. Canonical object bytes

`BDB-CJSON-1(object)` spełnia wszystkie warunki:

- UTF-8 bez BOM,
- brak insignificant whitespace,
- brak końcowego LF w canonical bytes,
- object keys wyłącznie ASCII zgodne z grammar schema,
- duplicate object keys odrzucone przed canonicalization,
- keys sortowane według JCS dla dopuszczonego ASCII subset,
- arrays zachowują kolejność; set-like fields mają jawny typed sort key i duplicate rejection; **wyjątek:** `CommitBody.immutable_object_refs[]` ma semantykę canonical topological sequence opisaną w §4 i nie jest set-like,
- string values: poprawny Unicode bez lone surrogates,
- brak cichej Unicode/whitespace normalization evidence text,
- integers tylko w zakresie `[-(2^53-1), 2^53-1]`,
- brak floating-point w identity-bearing canonical objects,
- ratios/pomiary: rational integer pair albo typed versioned canonical decimal string,
- `-0`, NaN, Infinity, exponent i `+` w canonical decimal są niedozwolone,
- identifiers, enum values, profile IDs i digest strings mają strict ASCII grammar.

Transport:

```text
canonical object bytes = BDB-CJSON-1(object)
.json bytes             = canonical object bytes + LF
.jsonl record           = canonical object bytes + LF
```

Transportowy LF nie należy do `ObjectDigest` preimage.

## 3. Digest semantics

Normatywny profile ID dla semantic-object digest to `BDB-OBJECT-DIGEST-1`. Zmiana preimage/domain-separation rules wymaga nowego profile ID; nie wolno zachować tej nazwy przy innym algorytmie.

```text
RawDigest(bytes) = SHA256(exact bytes)

ObjectDigest(kind, version, object) =
  SHA256(
    ASCII("BDB2/")
    + ASCII(kind)
    + ASCII("/")
    + ASCII(version)
    + NUL
    + BDB-CJSON-1(object_preimage)
  )
```

`kind` grammar:

```text
[a-z][a-z0-9_]{0,63}
```

`version` grammar:

```text
[1-9][0-9]{0,8}
```

Digest textual representation to dokładnie `64 lowercase hex`; UI może dodawać display prefix `sha256:`, ale prefix nie jest częścią raw digest value.

`RawDigest` i `ObjectDigest` nie mogą być porównywane jako ten sam typ identity. Dla zarejestrowanego semantic object parametr `kind` w `ObjectDigest(kind,version,body)` jest **dokładnie registry wire kind**. W szczególności CommandEnvelope używa `command_envelope`, a CommitBody używa `commit_body`; aliasy digest-domain `command` / `commit` są zabronione.

## 4. Self-reference

Canonical object body nie zawiera własnego `ObjectDigest`, własnego accepting commit/head/event ref ani własnego post-acceptance `HistoryCut` w swoim preimage. Digest/storage locator/acceptance provenance należą do zewnętrznego envelope/index/history position.

Referencje mają dwa odrębne porządki:

- history/acceptance context wskazuje wyłącznie **już istniejący input cut / prior accepted ref**; jedyny initialization sentinel to tagged `EMPTY_HISTORY`, bez synthetic hash/H0, legalny wyłącznie przed pierwszym accepted commit; first-history exception pozwala tylko na same-commit content refs uporządkowane przez canonical closure i zweryfikowane względem exact external `INSTALLATION_BOOTSTRAP_PROFILE_V1` pin;
- content-object ref może wskazać immutable object przygotowany wcześniej w tym samym atomic commit, jeżeli wszystkie nowe obiekty tworzą zwalidowany acykliczny hash DAG i ref prowadzi wyłącznie do wcześniejszego node w canonical topological commit closure.

`CommitBody.immutable_object_refs[]` jest normatywnie **sequence**. Canonical ordering procedure: zbudować graph nowych content refs, odrzucić duplicate/self/future/cycle, wykonać Kahn topological sort, a przy wielu zero-indegree nodes wybrać najmniejszy `(kind, logical_id_or_empty, revision_digest)`. Zapisana sequence MUSI być identyczna z wynikiem procedury i uczestniczy w commit preimage. Nie istnieje alternatywny lexical/set sort tej samej closure.

Niedozwolone są future-object refs, own-digest refs, własne accepting event/head/commit refs oraz post-acceptance cuts. Same-commit content dependency nie ustanawia history provenance; provenance nadal wynika dopiero z accepted commit/event position.

Raw artifact nie zawiera własnego `RawDigest`. Manifest embedded w artifact nie może zawierać finalnego hash całego artifactu, jeśli prowadziłoby to do self-reference. Snapshot/view/report/build output digest jest przechowywany w zewnętrznym RawRef/export receipt po utworzeniu finalnych bytes.

## 5. Logical ID i immutable revision

Lifecycle-bearing entity ma:

```text
logical_id
revision_no
previous_revision_ref | null
revision ObjectDigest
```

Logical ID w baseline ma postać:

```text
<kind>_<uuidv4-lowercase>
```

Canonical wire-kind namespace jest authority exact pinned ArtifactContractRegistry + SchemaRegistry binding, nie swobodna lista wpisana w ADR. Przykładowe **aktualne exact wire kinds** foundation obejmują `campaign_genesis`, `successor_campaign_genesis`, `stage_run`, `lane_run`, `attempt`, `invariant_revision`, `hypothesis_revision`, `experiment_spec`, `execution_descriptor`, `evidence_qualification_assessment`, `evidence_applicability_assessment`, `finding_claim_revision`, `root_cause_revision`, `discovery_record`, `coverage_obligation_qualification`, `finding_adjudication_decision` i `release_qualification`; lista jest jawnie niepełna i każdy użyty kind musi rozwiązywać się przez exact pinned Registry/SchemaRegistry. Ogólne etykiety domenowe takie jak `campaign`, `evidence`, `finding`, `decision`, `artifact` czy `execution_run` **nie są wire-kind aliases** i nie mogą być użyte w `ObjectDigest(kind,...)`, chyba że przyszła jawna rewizja Registry zarejestruje je jako odrębne kinds. Krótkie aliasy (`cmp_`, `stg_` itd.) są wyłącznie display/import aliases.

UUID nie jest authorization, ordering ani secrecy primitive.

Materialny gate/evidence/checkpoint/STOP reference zawsze wskazuje exact revision. Resolver „current by logical ID” jest dozwolony jako query/UI convenience, nie jako accepted decision input.

## 6. TypedRef

Canonical object ref zawiera co najmniej:

```text
kind
logical_id optional-by-type
revision_digest
digest_profile
schema_revision_ref
```

RawRef zawiera:

```text
raw_digest
byte_length
media_type
artifact_contract_ref
```

TypedRef do złego kind/digest profile albo bez exact revision jest fail-closed w authority-bearing relations.

## 7. Canonical decimal / rational

Canonical decimal string:

- brak exponent,
- brak `+`,
- brak zbędnych zer wiodących,
- brak końcowych zer po kropce,
- brak `-0`,
- zero = `0`.

Rational:

```text
numerator: integer
denominator: integer > 0
gcd(abs(numerator), denominator) = 1
zero = 0/1
```

Schema określa dokładnie, czy pole jest integer, rational czy canonical-decimal-string; executor nie wybiera reprezentacji ad hoc.

## 8. SourceIdentityProfile v1

SourceGeneration identity nie jest ZIP filename ani mtime. Foundation `source_identity/1` wiąże:

```text
authority_mode = AUTHORIZED_GIT | AUTHORIZED_SNAPSHOT
authorized_repository_id / snapshot_authority_id
git object algorithm + exact commit/tree IDs when applicable
materialized SourceManifest ObjectDigest
```

`SourceManifest` używa canonical POSIX relative paths i per-entry: entry type, relevant mode, exact byte length/content RawDigest lub symlink target/submodule object ID. Duplicate/colliding paths są rejected. Nierozwiązany required submodule/LFS content blokuje COMPLETE_SOURCE. Raw archive/capsule digest opisuje representation, nie semantic SourceGeneration.

Canonical Source identity = `ObjectDigest("source_identity", 1, SourceIdentityBody)`. Dwa importy są tym samym semantic source identity wtedy i tylko wtedy, gdy ten digest i pinned identity profile są równe; filename/archive name nie tworzą nowej identity. Logical `source_generation_id` nie może tworzyć drugiej konkurencyjnej identity dla tych samych exact source bytes/profile.

## 8.1. SurfaceKeyProfile v1

```text
SurfaceKey = ObjectDigest("surface_key", 1, {
  source_identity_ref,
  canonical_surface_category,
  normalized_anchor_descriptor
})
```

Static anchor: canonical repo path, zero-based byte offset w **oryginalnych raw file bytes**, entry kind i deterministic discriminator. Runtime anchor: method, normalized route pattern, registration origin i namespace. Niejednoznaczność daje `PROVISIONAL`; nie wolno heurystycznie scalać identity.

## 9. Versioning rule

Jakakolwiek zmiana powyższych reguł, która może zmienić canonical bytes lub `ObjectDigest`, wymaga nowego profilu (`BDB-CJSON-2` lub nowego digest profile). Nie wolno reinterpretować historycznych `BDB-CJSON-1` bytes nową implementacją.

## 10. Required golden and negative vectors before freeze

Normatywny R5.3 vector set: `BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json`; jego digest jest częścią exact R5.3 author-final candidate manifestu. Jeżeli kiedyś wykonywany jest strict independent review, verdict musi wiązać dokładnie ten manifest.

Foundation freeze wymaga vectors co najmniej dla:

- key ordering,
- duplicate keys,
- ASCII-key rejection,
- Unicode string values i lone surrogate rejection,
- integer bounds,
- float rejection,
- canonical decimal edge cases,
- rational normalization,
- arrays vs set-like fields,
- commit closure: dependency order przeciwny do typed lexical sort, independent siblings z deterministic tie-break, duplicate i cycle rejection,
- `EMPTY_HISTORY` first-commit vector + exact installation bootstrap pin + one-commit legacy admission/genesis closure + blocked-admission/no-genesis + reject po genesis,
- raw-vs-object digest type mismatch,
- self-digest / self-accepting-commit / post-head exclusion,
- typed-ref wrong-kind/wrong-revision rejection.

Vectors muszą być niezależnie sprawdzalne przez co najmniej dwie implementacje/reference procedures przed pierwszym persistence format freeze.

```

---

# D. Data & Artifact Contracts — common object rules, canonicalization, hashing, identity and referential integrity

Source: `BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS.md`.

```markdown
# 2. Wspólne zasady wszystkich artefaktów

Każdy identity-bearing JSON/JSONL record MUSI wskazywać exact schema revision i governing serialization profile.

Canonical **revision body** nie zawiera własnego digestu. Minimalny wspólny preimage dla lifecycle-bearing canonical object obejmuje:

```text
kind
schema_version
logical_id
revision_no
previous_revision_ref | null
payload / type-specific bindings
```

Po canonicalization storage/index tworzy zewnętrzny revision envelope:

```text
kind
logical_id optional-by-type
revision_digest            # dokładnie 64 lowercase hex
digest_profile = BDB-OBJECT-DIGEST-1
schema_revision_ref
storage_locator optional
accepted_commit_ref optional   # acceptance provenance, OUTSIDE object preimage
```

`revision_digest` ani commit, który akceptuje daną revision, **nie należą do jej własnego `ObjectDigest` preimage**. Display prefix `sha256:` jest wyłącznie UI i nie jest canonical digest value.

Canonical object body rozróżnia dwa rodzaje referencji:

- **history/acceptance refs** (`HistoryCut`, accepted event/head/commit provenance) wskazują wyłącznie **już zaakceptowany** input cut/ref sprzed accepting commit; jedynym wyjątkiem inicjalizacyjnym jest jawny tagged `EMPTY_HISTORY` opisany w §15.1/§15.4, który nie udaje wcześniejszego commitu;
- **content-object refs** mogą wskazywać immutable object przygotowany wcześniej w **tym samym atomic commit**, ale wyłącznie gdy cały zbiór nowych obiektów tworzy acykliczny DAG i referencja biegnie do wcześniejszego node w **jednej canonical topological sequence** commit closure.

Nigdy nie wolno wskazać własnego `ObjectDigest`/`RawDigest`, future objectu, własnego accepting event/head/commit ref ani własnego post-acceptance `HistoryCut`. Acceptance provenance jest nadawane przez zewnętrzny envelope/index i pozycję eventu w accepted commit. `CommitBody.immutable_object_refs[]` jest **ordered sequence**, nie set-like membership list: coordinator buduje dependency DAG, odrzuca duplicate/self/future/cyclic refs, wykonuje deterministic topological sort, a dla równoległych nodes stosuje tie-break `(kind, logical_id_or_empty, revision_digest)`. Dokładnie ta sequence uczestniczy w `CommitBody` bytes/hash; nie istnieje drugi niezależny canonical sort porządek dla tej samej closure.

Machine-readable `ArtifactContractRegistry.reference_class_semantics` jest normatywnym słownikiem klas referencji. Foundation używa dokładnie następujących znaczeń:

```text
CONTENT_OR_PRIOR         = prior accepted immutable object OR earlier same-commit content node; never self/future/history provenance
CONTENT_OBJECT           = content-closure reference validated by canonical topological order
PRIOR_ACCEPTED_ONLY      = exact backward ref accepted before current input cut; same-commit forbidden
HISTORY_INPUT            = prior accepted cut/head, albo tagged EMPTY_HISTORY[_CUT] tylko dla initialization; ordinary same-commit content forbidden
HISTORY_CONTEXT_BINDING  = policy/spec binding resolved from the represented prior cut, albo exact installation pin for EMPTY_HISTORY_CUT
PINNED_INSTALLATION_REF  = exact LOCAL_PINNED bootstrap trust-root ref
PINNED_PROFILE_REF       = exact governing profile pin; no latest/installed substitution
POST_ACCEPTANCE_SIDECAR  = post-acceptance reference outside accepting preimage/content DAG
GOVERNANCE_AUTHORITY_REF  = exact external/prior governance authority identity; never a profile alias or self-authorizing same-record ref
```

Każdy `*_history_cut` / `basis_history_cut` / `input_history_cut` w registry MUSI używać `HISTORY_INPUT`; nie wolno klasyfikować go jako zwykłe `CONTENT_OR_PRIOR`. Dla `HistoryCut` same `governing_policy_ref`/`governing_spec_refs[]` używają `HISTORY_CONTEXT_BINDING`, ponieważ ich legalność zależy od wariantu EMPTY versus ACCEPTED. `HistoryCut` nie używa `schema_set_ref` jako substytutu governing spec set: schema binding i governing spec revisions są odrębnymi domenami. Użyta `ref_class` nieobecna w pinned `reference_class_semantics` jest fail-closed `UNREGISTERED_REFERENCE_CLASS`.

Dla machine Registry wszystkie `material_refs` arrays mają domyślnie semantykę `CANONICAL_TYPED_REF_SORT_NO_DUPLICATES_UNLESS_FIELD_OVERRIDE`: są set-like, deterministycznie sortowane po pełnej typed-ref identity i odrzucają duplicates. Pole o rzeczywistej semantyce sekwencji MUSI mieć jawny `ordering_rules` override; `CommitBody.immutable_object_refs[]` używa canonical topological sequence i nie podlega default sort.

W zależności od typu body może wymagać również:

```text
campaign_id
source_generation_ref
created_by_actor_ref
input_history_cut
governing_policy_ref
governing_spec_refs[]
```

Pola obserwacyjne (`created_at`, wall-clock timestamps, filenames, paths) NIE ustanawiają ordering ani identity, o ile konkretny contract jawnie nie mówi inaczej.

Unknown mandatory field semantics, unknown schema revision albo dangling typed reference są fail-closed.

---

# 3. Canonical serialization

Normatywny profil canonical object serialization to `BDB-CJSON-1`; jego pełny **candidate normative contract** definiuje `ADR-006_CANONICAL_SERIALIZATION_AND_IDENTITY_PROFILE.md`; staje się `FROZEN` dopiero razem z zaakceptowanym foundation baseline po niezależnym review i wymaganych golden/negative vectors.

`BDB-CJSON-1` jest profilem JCS z dodatkowymi restrykcjami domenowymi BDB:

- canonical object bytes są UTF-8 bez BOM, bez whitespace i bez końcowego LF,
- **object keys są ASCII** i muszą spełniać grammar kontraktu danego schema; nie dopuszcza się dwóch implementacyjnych porządków Unicode keys,
- string values są poprawnym Unicode bez lone surrogates; BDB nie wykonuje cichej normalizacji Unicode ani whitespace evidence text,
- duplicate object keys są odrzucane przed canonicalization,
- arrays zachowują kolejność; pola o semantyce zbioru mają schema-defined typed sort key i duplicate rejection,
- integers mieszczą się w `[-(2^53-1), 2^53-1]`,
- floating-point jest niedozwolony w canonical identity-bearing objects,
- ratios/pomiary używają rational integer pairs albo jawnie typowanego, wersjonowanego decimal-string formatu,
- `-0`, NaN, Infinity, exponent/plus/ambiguous decimal forms są niedozwolone zgodnie z ADR,
- identifiers, enums i digest strings mają ścisłe ASCII grammar,
- self-digest field nie należy do własnego preimage.

Canonical transport:

```text
canonical object bytes = BDB-CJSON-1(object)
.json transport         = canonical object bytes + LF
.jsonl transport        = one canonical object + LF per record
```

Digest semantics:

```text
RawDigest(bytes) = SHA256(exact bytes)
ObjectDigest(kind, version, object) =
  SHA256("BDB2/" + kind + "/" + version + NUL + BDB-CJSON-1(object_preimage))
```

`kind` ma grammar `[a-z][a-z0-9_]{0,63}`; `version` to canonical decimal `[1-9][0-9]{0,8}` bez zer wiodących; digest string to dokładnie 64 lowercase hex. `RawDigest` i `ObjectDigest` nie są wymienne.

Raw historyczne/source/artifact bytes NIE są przepisywane do BDB-CJSON-1. Zmiana któregokolwiek z powyższych invariantów wymaga nowego serialization/digest profile, nie cichej zmiany `BDB-CJSON-1`.

---

# 4. Hashing

BDB używa co najmniej dwóch odrębnych digest semantics:

```text
RawDigest(bytes) = SHA256(exact stored bytes)
ObjectDigest(kind, version, object) =
  SHA256("BDB2/" + kind + "/" + version + NUL + BDB-CJSON-1(object_preimage))
```

`RawDigest` służy do integralności exact artifact bytes, legacy bundles, source members i eksportów.

`ObjectDigest` służy do immutable revisions canonical objects, policies, specs, assessments i facts.

Typed reference MUSI określać, którego digest semantics używa. Nie wolno porównywać `RawDigest` i `ObjectDigest` jako równoważnych identity.

Hash potwierdza zgodność bytes z wartością. Sam nie dowodzi authenticity, freshness, wykonania testu, kompletności historii ani braku full-host rollback.

---

# 5. Artifact identity

BDB rozdziela:

```text
LOGICAL IDENTITY
```

od:

```text
IMMUTABLE REVISION IDENTITY
```

Logical ID identyfikuje byt przez lifecycle (`campaign`, `finding`, `invariant`, `surface family`, `root cause`).

Materialna revision jest wskazywana przez exact `ObjectDigest` albo `RawDigest`.

Wymagane referencje do materialnych decyzji, checkpointów, evidence, policies i schemas MUSZĄ wskazywać exact revision. Resolver typu „current object by logical ID” nie może być używany w gate, STOP, qualification ani history replay.

Artifact identity dla raw file:

```text
artifact_logical_id
raw_digest
byte_length
artifact_contract_ref
```

Zmiana bytes = nowa artifact revision, nawet jeśli filename pozostaje ten sam.

---

# 6. Identifier policy

Domyślnie logical IDs są nieprzewidywalnymi, jednorazowo nadanymi typed identifiers (np. UUIDv4 w reference implementation). Nie mogą zawierać sekretów ani znaczenia, które później trzeba reinterpretować.

Canonical instance logical ID ma postać:

```text
<kind>_<uuidv4-lowercase>
```

Foundation kind registry jest **pinned przez SchemaRegistry**. Poniższa lista jest wyłącznie niepełnym minimalnym przykładem klas, nie zamkniętym allowlistem:

```text
campaign
stage_run
lane_run
attempt
artifact
invariant
hypothesis
experiment
execution_run
evidence
finding
root_cause
discovery
qualification
decision
```

Nowy canonical kind jest dozwolony wyłącznie, jeżeli istnieje w exact pinned SchemaRegistry/spec revision. Ten przykład nie może być użyty do odrzucenia innych zarejestrowanych foundation kinds, takich jak grant, knowledge_state, coverage_obligation, contradiction, challenger_result, release_qualification czy trust_profile.

Krótkie aliasy typu `cmp_`, `stg_`, `att_` mogą istnieć wyłącznie jako UI labels/import adapters; nie są canonical logical IDs. Surface jest wyjątkiem tam, gdzie policy wymaga deterministycznego `SurfaceKey` zamiast losowego instance ID.

Dla bytów wymagających stabilności między niezależnymi collectorami, np. Surface, logical key może być deterministycznie wyprowadzany wyłącznie z jawnego `SurfaceKeyProfile` i exact SourceGeneration. Nie wolno używać losowego offsetu parsera, mtime ani filename jako jedynej identity.

Identity profile jest pinned przez policy/spec revision.

---

# 7. Referential integrity

Canonical reference jest typowany i wskazuje exact revision:

```json
{
  "kind": "invariant",
  "logical_id": "invariant_<uuidv4-lowercase>",
  "revision_digest": "<64-lowercase-hex>",
  "digest_profile": "BDB-OBJECT-DIGEST-1",
  "schema_revision_ref": {"kind": "schema", "revision_digest": "<64-lowercase-hex>"}
}
```

Canonical digest fields nie zawierają prefixu `sha256:`.

Raw artifact reference zawiera analogicznie `raw_digest`, `byte_length` i artifact contract.

Cross-reference validator sprawdza:

- target istnieje w immutable object closure lub accepted history,
- typ targetu jest zgodny z polem,
- exact revision jest zgodna,
- SourceGeneration/campaign scope jest dozwolony,
- policy/spec revision dopuszcza tę relację,
```

---

# E. Test Plan — exact F1-relevant test obligations

Source: `BDB_AUDIT_V2_TEST_AND_SELF_AUDIT_PLAN.md`.

## Qualification order and unit-test baseline

```markdown
# 3. Warstwy testów

Normatywna kolejność kwalifikacji:

```text
UNIT / PROPERTY / SCHEMA / GOLDEN
        ↓
AUTHORITY + IDENTITY + TRANSACTION TESTS
        ↓
LEGACY PRESERVATION + CORRECTNESS
        ↓
FOUNDATION REFERENCE SLICE
        ↓
ADVERSARIAL + FAULT + BYPASS
        ↓
E1 / E2 / E3 / E4 / E5 END-TO-END
        ↓
SELF-AUDIT / CALIBRATION / HOLDOUT
        ↓
RELEASE QUALIFICATION
```

`FOUNDATION_REFERENCE_SLICE` jest wcześniejszym gate niż szerokie E3/E4/E5 development. Musi przejść happy path oraz wymagane failure paths.

---

# 4. Test taxonomy

BDB v2 powinno posiadać co najmniej następujące suite:

```text
tests/unit/
tests/schema/
tests/property/
tests/compatibility/
tests/integration/
tests/adversarial/
tests/golden/
tests/fuzz/
tests/fault/
tests/e2e/
tests/reproducibility/
tests/self_audit/
tests/fixtures/
```

---

# 5. Unit tests

Unit tests obejmują wszystkie czyste komponenty.

Minimum:

- hashing,
- canonical serialization,
- ID generation,
- ZIP path normalization,
- hash manifest parser,
- schema registry,
- source identity comparison,
- ledger sequence validation,
- raw-prefix validation,
- Stage FSM,
- Lane FSM,
- Campaign FSM,
- corpus membership,
- exposure transitions,
- coverage depth transitions,
- priority scoring,
- evidence status,
- finding status,
- stop gate predicates.

---

# 6. Unit test design

Każdy moduł powinien posiadać:

```text
happy path
boundary values
invalid values
empty input
duplicate input
cross-source input
unknown enum
malformed references
```

```

## Canonical serialization, hashing, ZIP safety and artifact-hash manifest

```markdown
# 7. Canonical serialization tests

Testujemy normatywny profil `BDB-CJSON-1` z golden vectors.

Wymagane properties:

```text
BDB-CJSON-1(parse(BDB-CJSON-1(x))) == BDB-CJSON-1(x)
ObjectDigest(kind, version, x) == SHA256("BDB2/" + kind + "/" + version + NUL + BDB-CJSON-1(preimage_without_revision_digest))
```

Obowiązkowe przypadki:

- różna kolejność object keys daje ten sam canonical bytes,
- arrays zachowują kolejność,
- duplicate keys są FAIL przed canonicalization,
- Unicode nie jest po cichu normalizowane,
- `-0`, NaN i Infinity są niedozwolone,
- identity-bearing decimals nie przechodzą przez binary floating point,
- self-digest field nie należy do własnego preimage,
- zmiana serialization profile zmienia pinned profile/revision, nie `BDB-CJSON-1` w miejscu.

Exact raw artifacts nie są przepisywane do CJSON tylko po to, aby policzyć `RawDigest`.

---

# 8. Hash tests

Test vectors obejmują osobno:

```text
RawDigest    = SHA256(exact bytes)
ObjectDigest(kind, version, object) = SHA256("BDB2/" + kind + "/" + version + NUL + BDB-CJSON-1(object_preimage))
```

Testować:

- empty bytes, ASCII, Unicode UTF-8, binary, large file,
- raw artifact o tej samej semantyce, ale innych bytes → różny `RawDigest`,
- canonical object o innej kolejności keys → ten sam `ObjectDigest`,
- typed ref używający złego digest semantics → FAIL,
- filename/path nie wpływa na identity, jeśli contract tego nie przewiduje,
- hash nie jest traktowany jako proof authenticity/freshness/execution.

---

# 9. ZIP safety tests

Minimum:

```text
absolute path
../ traversal
mixed slash
backslash path
duplicate name
duplicate basename
conflicting duplicate
huge member
too many members
zip bomb ratio
corrupted CRC
nested archive
```

Nie każdy nested ZIP musi być zabroniony, ale parser nie może niekontrolowanie go rozpakowywać.

---

# 10. Artifact hash manifest tests

Sprawdzić:

- sorted paths,
- unsorted paths,
- duplicate path,
- missing path,
- extra path,
- wrong hash,
- malformed line,
- no final LF,
- path normalization.

---
```

## Property-based testing rule

```markdown
# 13. Property-based testing

Property tests obejmują szczególnie:

- `BDB-CJSON-1`,
- typed refs i immutable revisions,
- accepted commit/head/receipt,
- command idempotency,
- aggregate FSM,
- Corpus Snapshot revisions,
- Knowledge State monotonic potential exposure,
- Surface/Scope inventory revisions,
- `CoverageObligation` qualification,
- evidence dependency/applicability graphs,
- transitive invalidation,
- STOP decision table.

Property tests nie mogą zakładać, że aktualna implementacja jest oracle; model/reference semantics muszą być niezależnie zapisane.

---

# 14. Ledger property tests

Sekcja zachowuje nazwę historyczną, ale native-v2 authority testuje `CANONICAL_ACCEPTED_HISTORY`, nie niezależny mutable ledger.

```

## Legacy preservation/correctness, semantic diff, compatibility gate and golden tests

```markdown
# 19. Legacy compatibility tests

Dla każdego frozen fixture uruchamiać **dwa niezależne assertions**:

```text
LEGACY_BEHAVIOR_PRESERVATION
legacy_observed_result ↔ v2_observed_result

VALIDATOR_CORRECTNESS
independent_safe_expected_result ↔ v2_observed_result
```

Recorded v1 behavior jest oracle preservation, ale nie correctness. Known legacy bug może być zachowany w preservation profile i jednocześnie jawnie odrzucony przez correctness/hardening policy.

---

# 20. Legacy valid corpus

Każdy valid artifact z compatibility corpus musi zostać zaakceptowany.

Nie wystarczy kilka przykładów.

---

# 21. Legacy invalid corpus

Każdy znany invalid artifact musi pozostać odrzucony.

Szczególnie:

- wrong source SHA,
- wrong source tree,
- ledger prefix break,
- substitute checkpoint,
- early reveal,
- wrong variant,
- conflicting duplicate.

---

# 22. Compatibility semantic diff

Preservation diff porównuje co najmniej:

- status,
- semantic error family,
- source/checkpoint/lineage semantics,
- legacy ledger-prefix semantics,
- wymagane artifact family.

Correctness diff porównuje niezależnie z qualified safe expectation.

Wspólny wynik v1 i v2 nie zamyka correctness, jeżeli oba korzystają z tego samego błędnego assumption/oracle.

---

# 23. Compatibility gate

Istnieją dwa odrębne release blockers:

```text
LEGACY_BEHAVIOR_PRESERVATION_GATE
VALIDATOR_CORRECTNESS_GATE
```

Dla corpus objętego wymaganiem:

```text
UNEXPLAINED_PRESERVATION_DIFFS = 0
KNOWN_SAFE_EXPECTATIONS_SATISFIED = 100%
KNOWN_UNSAFE_EXPECTATIONS_REJECTED = 100%
KNOWN_LEGACY_BUGS_NOT_MISCLASSIFIED_AS_SAFE = 100%
```

Celowe hardening difference wymaga versioned `COMPATIBILITY_EXCEPTION / INTENTIONAL_HARDENING_DECISION`.

---

# 24. Golden tests

Golden tests obejmują:

- prompt bytes,
- wrapper bytes,
- execution context,
- StageSpec compiled representation,
- LaneSpec compiled representation,
- previous-prompt bundle,
- report corpus manifest.

---

# 25. Golden prompt policy

Zmiana golden SHA wymaga jawnej decyzji.

Nie aktualizować snapshotów automatycznie bez review.

---

```

---

# F. Migration & Compatibility — read-only legacy boundary and two independent compatibility gates

Source: `BDB_AUDIT_V1_TO_V2_MIGRATION_AND_COMPATIBILITY.md`.

```markdown
# 2. Najważniejsza zasada

## NIE PRZEPISYWAĆ HISTORII

Historyczne artefakty audytu pozostają dokładnie tym, czym były w chwili ich utworzenia.

W szczególności historyczne E1/E2 zachowują:

- oryginalne variant IDs,
- oryginalne prompt/wrapper hashes,
- oryginalne F1/F2,
- oryginalne `AUDIT_LEDGER`, `RUN_MANIFEST`, `LINEAGE_MANIFEST`,
- oryginalne source SHA/tree i representation hashes,
- oryginalne report/bundle hashes,
- oryginalną kolejność i zawartość bytes.

BDB v2 NIE MOŻE modyfikować tych artefaktów „dla zgodności”.

Dodatkowo obowiązuje rozdział:

```text
HISTORICAL FACT
!=
CURRENT V2 INTERPRETATION
```

Jeżeli v2 stwierdza dziś, że historyczny artifact ma np. `EXPOSURE_CONFIDENCE=STRONG`, `CURRENT_EVIDENCE_APPLICABILITY=SCOPED` albo jest admissible jako canonical predecessor, są to **nowe decyzje v2** związane z exact raw bytes. Nie stają się retroaktywnie polami starego artifactu.

Zmiana interpretacji tworzy nową revision/assessment w canonical accepted history v2. Nigdy nie zmienia raw history.

---

# 3. Frozen legacy baseline

Migracja rozpoczyna się od zamrożenia referencyjnej wersji:

```text
LEGACY_APPLICATION = BDB Audit Assistant v1.4.4
GOVERNING_PROTOCOL = PA v5.2
WRAPPER_RELEASE = 5.4-RC1
```

Należy zachować:

- dokładny plik `.py` i jego RawDigest,
- source copy w `legacy/v1_4_4/`,
- exact fixtures i ich bytes/hashes,
- self-test outputs wraz z version/toolchain context,
- known-valid i known-invalid bundles,
- dokumentację legacy contract expectations,
- jawny registry znanych legacy bugs/quirks.

Freeze nie oznacza, że wszystkie zachowania v1 są poprawne. Oznacza tylko, że mamy stabilny punkt odniesienia do preservation.

---

# 4. Compatibility corpus

Przed ekstrakcją assurance core powstaje immutable:

```text
LEGACY_COMPATIBILITY_CORPUS/
```

Corpus ma dwa cele:

1. preservation — czy v2 rozpoznaje legacy semantics zgodnie z przyjętym kontraktem,
2. correctness — czy wynik jest zgodny z niezależnie uzasadnionym safe/invalid expectation.

## 4.1. Valid / expected-accept cases

Minimum:

- valid BASE F1,
- valid BASE final bundle,
- valid E2 F1,
- valid E2 F2,
- valid E2 final bundle,
- valid reveal attestation,
- valid continuation ticket,
- valid previous-prompt bundle.

## 4.2. Invalid / expected-reject cases

Minimum:

- wrong variant/source/run/audit identity,
- conflicting duplicate member,
- invalid hash manifest,
- missing retained snapshot,
- broken raw ledger prefix,
- malformed F1/F2 checkpoint,
- early reveal attestation,
- source-generation mix,
- substitute F2,
- unsafe ZIP path / duplicate ZIP name,
- wrong final artifact family,
- stale-but-internally-valid artifact względem pinned predecessor/head, jeżeli fixture kwalifikuje freshness semantics.

## 4.3. Fixture contract

Każdy fixture posiada co najmniej:

```text
fixture_id
raw_artifact_ref / RawDigest
fixture_intent
legacy_observed_result
legacy_observed_error_family
independent_safe_expected_result
independent_expected_error_family
expectation_basis_ref
known_legacy_bug = true|false
intentional_v2_hardening = true|false
compatibility_exception_ref optional
```

`legacy_observed_result` NIE jest automatycznie `independent_safe_expected_result`.

Expected correctness dla materialnych invariants musi pochodzić z jawnie kwalifikowanego oracle: specyfikacji artifact contract, manually adjudicated test vector, negative/positive control albo innego źródła niezależnego od obu validatorów. Fixture nagrany wyłącznie z v1 kwalifikuje preservation, nie correctness.

---

# 5. Dwa compatibility gates

BDB v2 nie może zostać uznane za bezpiecznego następcę v1.4.4 na podstawie jednego wyniku `same as v1`.

Obowiązują dwa odrębne gates.

## 5.1. LEGACY_BEHAVIOR_PRESERVATION_GATE

Sprawdza, czy dla fixtures oznaczonych jako wymagające preservation v2 zachowuje oczekiwane legacy semantics albo posiada zaakceptowany `COMPATIBILITY_EXCEPTION`.

Przykładowy warunek dla zamrożonego corpus:

```text
KNOWN_REQUIRED_PRESERVATION_CASES_MATCH = 100%
UNEXPLAINED_PRESERVATION_DIFFS = 0
```

## 5.2. VALIDATOR_CORRECTNESS_GATE

Sprawdza niezależnie, czy known-safe/known-invalid expectations są respektowane.

```text
KNOWN_SAFE_EXPECTATIONS_SATISFIED = 100%
KNOWN_UNSAFE_EXPECTATIONS_REJECTED = 100%
KNOWN_LEGACY_BUGS_NOT_MISCLASSIFIED_AS_SAFE = 100%
```

Jeżeli v2 celowo utwardza zachowanie w stosunku do v1, różnica może być poprawna, ale musi posiadać jawny:

```text
COMPATIBILITY_EXCEPTION / INTENTIONAL_HARDENING_DECISION
```

Nie wolno „naprawić” fixture ani przepisać expectation po zobaczeniu wyniku bez versioned adjudication.

---

# 6. Klasy kompatybilności

Klasa opisuje sposób użycia legacy artifactu. Nie zastępuje admission ani correctness assessment.

## BYTE_COMPATIBLE

v2 waliduje exact legacy bytes w tym samym contract profile i zachowuje wymagany wynik preservation.

## SEMANTICALLY_COMPATIBLE

v2 rozumie stary artifact i może utworzyć nową interpretację/reference, ale raw bytes pozostają authority własnej historycznej treści.

## READ_ONLY_COMPATIBLE

v2 może odczytać/zwalidować artifact, ale nie generuje nowych artifacts w tym starym formacie.

## INFORMATIONAL_ONLY

Artifact może być zachowany lub analizowany, ale nie spełnia wymagań canonical/auxiliary admission.

## UNSUPPORTED

Artifact nie jest wspierany; przyczyna i wpływ na migrację muszą być jawne.

Klasa compatibility nie implikuje `CURRENT_EVIDENCE_APPLICABILITY=ACTIVE` ani prawa do historycznego blind-origin claimu.

---

# 7. Co przenosimy z v1.4.4

Przenosimy kwalifikowane **assurance primitives**, a nie globalną semantykę monolitu.

## 7.1. Hash utilities

- SHA-256 exact bytes/files,
- readback validation,
- niezmienne test vectors.

## 7.2. ZIP safety

- absolute/`..`/backslash path rejection,
- duplicate member detection,
- resource/size limits,
- ZIP integrity checks.

## 7.3. Legacy artifact hash manifests

- parsing `ARTIFACT_HASHES.sha256`,
- membership/sorted order/per-member hash validation.

## 7.4. Source identity evidence

Zachowujemy wszystkie legacy source-binding fakty (commit/tree/readbacks/manifest bindings), ale **nowa v2 `SourceGeneration` identity jest obliczana według jednego normatywnego SourceIdentity profile z Data Contracts/ADR**.

Legacy SHA/tree nie są tracone. Importer tworzy `SourceReconciliationAssessment`, który wiąże legacy facts z current v2 SourceGeneration albo zwraca `CONFLICT` / `INSUFFICIENT_DATA`. Nie porównujemy tylko filename/ZIP hash.

## 7.5. Legacy ledger/checkpoint continuity

- JSONL parsing,
- sequence continuity,
- raw-byte/parsed prefix,
- retained snapshot/digest binding.

Są to primitives walidacji legacy. Nie tworzą drugiego mutable ledger authority w v2.

## 7.6. Reveal-gate mechanics

Zachowujemy mechanikę checkpoint-before-reveal, attestation/ticket/source consistency i no-substitute checkpoint. W v2 jest ona uogólniona do grant-before-delivery, Knowledge State i positive capability views.

## 7.7. Legacy result-bundle validation

Zachowujemy wymagane machine artifacts i historical F1/F2/final family rules tylko w legacy profile. Native-v2 stage/campaign finalization używa nowych kontraktów.

---

# 8. Co uogólniamy

Mechanizmy v1 zostają uogólnione dopiero po preservation+correctness qualification.

```

---

# G. Pinned Artifact Contract Registry — task-scoped exact machine subset

Source: `BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY.json`.

This is an exact subset copied from the pinned Registry. Omission from this convenience subset does **not** mean an omitted kind is invalid. If F1 needs a kind not shown here, resolve it from the exact full pinned Registry available to the implementation environment; do not invent aliases or a second registry.

```json
{
  "registry_id": "BDB-AUDIT-V2-ARTIFACT-CONTRACT-REGISTRY-R5-3-1",
  "registry_version": 3,
  "status": "AUTHOR_FINAL_R5_3_NOT_INDEPENDENTLY_FROZEN",
  "runtime_authority_statement": "This pinned registry constrains contract kinds and validation but is not accepted runtime state authority; CANONICAL_ACCEPTED_HISTORY remains runtime truth authority.",
  "registration_rule": "Every kind used by the author-qualified foundation/reference-slice must be registered. Every kind in foundation_inline_reference_contract_kinds must use EXPLICIT_COMPLETE typed-ref/cardinality semantics; material-ref array ordering is the pinned contract default CANONICAL_TYPED_REF_SORT_NO_DUPLICATES_UNLESS_FIELD_OVERRIDE unless a field-specific ordering_rules override exists. Other future kinds may be SCHEMA_BOUND_BEFORE_FIRST_ACCEPTANCE and are fail-closed until exact executable schema/ref binding exists; unknown runtime kind is UNREGISTERED_CONTRACT_KIND.",
  "object_digest_domain_rule": "For registered semantic objects, ObjectDigest(kind,version,body) MUST use the exact registry kind string. command_envelope and commit_body have no alternate command/commit digest-domain aliases.",
  "contract_defaults": {
    "reference_array_ordering": "CANONICAL_TYPED_REF_SORT_NO_DUPLICATES_UNLESS_FIELD_OVERRIDE",
    "sensitivity": "POLICY_DEFINED",
    "version_compatibility": "EXACT_VERSION_ONLY_UNLESS_EXPLICIT_ADAPTER"
  },
  "reference_class_semantics": {
    "AUTHORIZED_ACTOR_REF": "Exact actor identity whose authorizing capability/role is established by prior accepted or installation-pinned trust/policy context before the command it authorizes. Same-commit actor creation/role elevation cannot authorize that same command.",
    "CONTENT_OBJECT": "Reference to immutable content participating in the current content closure. Same-commit targets MUST be earlier nodes in the canonical topological sequence; prior accepted immutable objects are permitted only where the type-specific contract explicitly allows reuse.",
    "CONTENT_OR_PRIOR": "Typed immutable content reference may resolve either to a prior accepted object or to an earlier node in the same validated canonical topological content closure. It MUST NOT resolve to self/future content or to acceptance/history provenance.",
    "GOVERNANCE_AUTHORITY_REF": "Exact authority identity valid for foundation-governance decisions. It must be established independently of the record it authorizes (external authorized governance identity or prior accepted governance authority); same-record/same-commit self-authorization is forbidden. It is not a profile reference and does not create campaign runtime authority.",
    "HISTORY_CONTEXT_BINDING": "Semantic policy/spec/profile binding constrained by the exact HISTORY_INPUT of the referring object. For EMPTY_HISTORY/EMPTY_HISTORY_CUT it MUST equal the exact external INSTALLATION_BOOTSTRAP_PROFILE_V1 pin; for accepted history it MUST resolve from the exact prior accepted history/policy/spec/profile state represented by that input cut/head. It may be carried inside HistoryCut or copied into another object only under an equality constraint. Same-commit semantic self-upgrade/substitution is forbidden.",
    "HISTORY_INPUT": "History/acceptance input reference. It MUST resolve to the exact prior accepted cut/head, or to the tagged EMPTY_HISTORY/EMPTY_HISTORY_CUT only for the one initialization context. It is never an ordinary same-commit content reference.",
    "PINNED_INSTALLATION_REF": "Exact external LOCAL_PINNED installation trust-root reference used only by the initialization boundary. It is not mutable campaign state and cannot be silently replaced by current workspace state.",
    "PINNED_PROFILE_REF": "Exact profile pin whose bytes/digest or qualified logical binding is fixed by the governing accepted/pinned profile. Consumers may not substitute a different installed/latest profile.",
    "POST_ACCEPTANCE_SIDECAR": "Reference emitted only after the accepting commit/head identity exists and kept outside that commit/object preimage. It may point to the accepted commit/head/result objects but cannot participate in the pre-acceptance content DAG.",
    "PRIOR_ACCEPTED_ONLY": "Backward-only reference to an exact already accepted object/head before the current command input cut. Same-commit, self and future targets are forbidden.",
    "SOURCE_AUTHORITY_REF": "Exact repository/snapshot authority identity authorized by the pinned SourceIdentityProfile/trust boundary independently of the SourceIdentity/SourceGeneration object being created. A same-commit object cannot bootstrap its own repository/snapshot authority."
  },
  "contracts": [
    {
      "authoritative_for": "raw artifact digest manifest",
      "canonical_role": "EXPORT",
      "consumer_roles": [
        "COORDINATOR",
        "VALIDATOR"
      ],
      "identity_semantics": "BDB-CJSON-1 + BDB-OBJECT-DIGEST-1 unless RAW/EXPORT",
      "kind": "artifact_hash_manifest",
      "lifecycle": "IMMUTABLE",
      "material_refs": [],
      "ordering_rules": {},
      "producer_authority": "EXPORT_BUILDER",
      "reference_contract_mode": "SCHEMA_BOUND_BEFORE_FIRST_ACCEPTANCE",
      "required_validation_layers": [
        "L1",
        "L2",
        "L4",
        "L5"
      ],
      "schema_ref": "BDB_SCHEMA_REGISTRY::artifact_hash_manifest/1",
      "validation_profile": "DERIVED",
      "version": "1"
    },
    {
      "authoritative_for": "exact historical legacy artifact bytes",
      "canonical_role": "RAW_EVIDENCE",
      "consumer_roles": [
        "COORDINATOR",
        "VALIDATOR"
      ],
      "identity_semantics": "BDB-CJSON-1 + BDB-OBJECT-DIGEST-1 unless RAW/EXPORT",
      "kind": "legacy_raw_ref",
      "lifecycle": "IMMUTABLE",
      "material_refs": [
        {
          "allowed": [
            "history_cut"
          ],
          "cardinality": "1",
          "field": "import_input_history_cut",
          "ref_class": "HISTORY_INPUT"
        }
      ],
      "ordering_rules": {},
      "producer_authority": "TRUSTED_COORDINATOR_ACCEPTANCE",
      "reference_contract_mode": "EXPLICIT_COMPLETE",
      "required_validation_layers": [
        "L1",
        "L2",
        "L4",
        "L5"
      ],
      "schema_ref": "BDB_SCHEMA_REGISTRY::legacy_raw_ref/1",
      "validation_profile": "RAW",
      "version": "1"
    },
    {
      "authoritative_for": "canonical source identity body",
      "canonical_role": "FACT",
      "consumer_roles": [
        "COORDINATOR",
        "VALIDATOR"
      ],
      "identity_semantics": "BDB-CJSON-1 + BDB-OBJECT-DIGEST-1 unless RAW/EXPORT",
      "kind": "source_identity",
      "lifecycle": "IMMUTABLE",
      "material_refs": [
        {
          "allowed": [
            "repository_or_snapshot_authority_ref"
          ],
          "cardinality": "1",
          "field": "authorized_repository_or_snapshot_ref",
          "ref_class": "SOURCE_AUTHORITY_REF"
        },
        {
          "allowed": [
            "source_manifest"
          ],
          "cardinality": "1",
          "field": "materialized_source_manifest_ref",
          "ref_class": "CONTENT_OR_PRIOR"
        },
        {
          "allowed": [
            "source_identity_profile_pin"
          ],
          "cardinality": "1",
          "field": "profile_ref",
          "ref_class": "PINNED_PROFILE_REF"
        }
      ],
      "ordering_rules": {},
      "producer_authority": "TRUSTED_COORDINATOR_ACCEPTANCE",
      "reference_contract_mode": "EXPLICIT_COMPLETE",
      "required_validation_layers": [
        "L3",
        "L4",
        "L5"
      ],
      "schema_ref": "BDB_SCHEMA_REGISTRY::source_identity/1",
      "validation_profile": "STRUCTURAL",
      "version": "1"
    },
    {
      "authoritative_for": "materialized source membership/bytes semantics",
      "canonical_role": "FACT",
      "consumer_roles": [
        "COORDINATOR",
        "VALIDATOR"
      ],
      "identity_semantics": "BDB-CJSON-1 + BDB-OBJECT-DIGEST-1 unless RAW/EXPORT",
      "kind": "source_manifest",
      "lifecycle": "IMMUTABLE",
      "material_refs": [],
      "ordering_rules": {},
      "producer_authority": "TRUSTED_COORDINATOR_ACCEPTANCE",
      "reference_contract_mode": "SCHEMA_BOUND_BEFORE_FIRST_ACCEPTANCE",
      "required_validation_layers": [
        "L3",
        "L4",
        "L5"
      ],
      "schema_ref": "BDB_SCHEMA_REGISTRY::source_manifest/1",
      "validation_profile": "STRUCTURAL",
      "version": "1"
    }
  ]
}
```

---

# H. Pinned Golden Vectors — F1 identity subset

Source: `BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json`.

This is an exact subset of vectors directly relevant to F1 identity/hash semantics. It is not a replacement for the full vector set. If an implementation path touches a vector not included here, consult the exact full pinned vector set when available; do not fabricate an expected outcome.

```json
{
  "vector_set_id": "BDB-AUDIT-V2-FOUNDATION-GOLDEN-VECTORS-R5-3-1",
  "status": "AUTHOR_FINAL_R5_3_NOT_INDEPENDENTLY_FROZEN",
  "vectors": [
    {
      "domain": "canonical_identity",
      "expected": {
        "object_digest_sha256": "d3fb18e1fe2e935611c36791d4dc3838ba11d3b5de96616957c43f982c73bde9"
      },
      "id": "CJSON_OBJECT_DIGEST_ASCII_1",
      "input": {
        "canonical_utf8_hex": "7b2261223a312c2262223a2278227d",
        "kind": "test_object",
        "object": {
          "a": 1,
          "b": "x"
        },
        "preimage_hex": "424442322f746573745f6f626a6563742f31007b2261223a312c2262223a2278227d",
        "version": "1"
      },
      "title": "Simple independent ObjectDigest vector",
      "why": "ASCII-only fixture avoids Unicode serializer ambiguity and pins domain-separation bytes."
    },
    {
      "domain": "canonical_kind_identity",
      "expected": {
        "finding_kind": "finding_adjudication_decision",
        "obligation_applicability_kind": "obligation_applicability_decision",
        "result": "ACCEPT_ONLY_EXACT_KIND"
      },
      "id": "R5N19_CANONICAL_KIND_IDENTITY_PARITY",
      "input": {
        "canonical_data_contract_names": [
          "FINDING_ADJUDICATION_DECISION",
          "OBLIGATION_APPLICABILITY_DECISION"
        ]
      },
      "title": "Canonical narrative name and registry kind are identity-equivalent",
      "why": "ObjectDigest domain separation includes kind; a shortened/renamed alias would create a distinct identity."
    },
    {
      "domain": "canonical_identity",
      "expected": {
        "error": "OBJECT_DIGEST_KIND_REGISTRY_MISMATCH",
        "result": "REJECT"
      },
      "id": "R5N23_OBJECT_DIGEST_WIRE_KIND_EXACT",
      "input": {
        "digest_domain_kind": "command",
        "registry_kind": "command_envelope"
      },
      "title": "ObjectDigest domain kind equals exact Registry wire kind",
      "why": "Aliases such as command/commit would produce a second identity for the same body."
    },
    {
      "domain": "canonical_identity",
      "expected": {
        "error": "LEGACY_SHORT_KIND_ALIAS_FORBIDDEN",
        "result": "REJECT"
      },
      "id": "R5N28_EVIDENCE_SEMANTIC_NAME_NOT_IDENTITY_ALIAS",
      "input": {
        "attempted_wire_kind": "evidence_qualification",
        "canonical_wire_kind": "evidence_qualification_assessment",
        "semantic_class": "EvidenceQualificationAssessment"
      },
      "title": "Legacy short evidence kind is not an identity alias",
      "why": "Exact wire identity is normalized to evidence_qualification_assessment / evidence_applicability_assessment; old short kinds cannot remain alternate ObjectDigest domains."
    }
  ]
}
```

---

# I. F1 interpretation boundary

The packet intentionally does **not** authorize F2/M4 work.

For this task:

```text
F0 = qualified predecessor
F1 = current execution phase
M2 + M3 = internal F1 slices
PR-003 + PR-004 + PR-005 + PR-006 = internal F1 work packages
F2 / M4 = forbidden until F1 closeout PASS
```

The required terminal compatibility conditions are the Roadmap M3 gates:

```text
LEGACY_BEHAVIOR_PRESERVATION_GATE = PASS
VALIDATOR_CORRECTNESS_GATE = PASS

UNEXPLAINED_REQUIRED_PRESERVATION_DIFFS = 0
KNOWN_SAFE_EXPECTATIONS_SATISFIED = 100%
KNOWN_UNSAFE_EXPECTATIONS_REJECTED = 100%
KNOWN_LEGACY_BUGS_MISCLASSIFIED_AS_SAFE = 0
```

F1 is a correctness/falsifiability phase. Nonessential performance work remains deferred until after the Foundation Reference Slice gate.

# ADR-006 — Canonical Serialization & Identity Profile

**Status:** AUTHOR-FINAL R5.3 — final author identity qualification; no additional Astra review scheduled
**Rewizja:** 2026-09-09 / R5.3 final identity hardening candidate  
**Self-audit:** `R5_3_AUTHOR_FINAL_REAUDIT_PASS`; report `BDB_AUDIT_V2_SELF_AUDIT_REPORT_R5_3_2026-09-09.md`; strict independent freeze is not claimed
**Data:** 2026-09-09  
**Zakres:** BDB Audit v2 foundation identity / hashing / canonical serialization  
**Powiązane:** `BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS.md`, `BDB_AUDIT_V2_ARCHITECTURE_SPEC.md`, `README_BDB_AUDIT_V2_DOCUMENTATION.md`

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

## 11. Consequences

Korzyści:

- jednoznaczne content-addressed revisions,
- mniejsza zależność od języka/runtime,
- brak float/Unicode-key ambiguity w identity,
- jasne rozdzielenie exact raw history od semantic object identity.

Koszt:

- ostrzejsze schemas,
- konieczność canonical validation przed object acceptance,
- przyszła zmiana profilu wymaga jawnej migracji/upgrade zamiast cichej kompatybilności.


## R5.3 identity non-regression

`CommitBody.command_ref` is a current-commit content reference to exact `command_envelope`; a prior accepted command cannot be rebound into a new commit. `HistoryCut` binds exact governing **spec revisions** separately from schema identity; `schema_set_ref` is not a governing-spec alias. Derived coverage summaries never substitute identity-bearing Coverage Obligation revisions in StopInput or Candidate Assurance Case.

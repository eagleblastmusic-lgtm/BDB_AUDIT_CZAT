# R5.4.1 governance correction successor

Direct predecessor: failed exact R5.4. Only §187.2 and the corresponding §192.2 governance body are corrected; all NF02 runtime semantics are inherited. Inherited filenames identify inputs, not an in-place modification of R5.4.

# BDB Audit v2 — R5.4 successor normative candidate

Status: PENDING_EXACT_CANDIDATE_QUALIFICATION; not installed, not independent freeze, no runtime qualification.

Date: 2026-10-06. Predecessor R5.3.1 candidate set `087539f5a08a2441647aae1889ce51330b47740e559b394574da122bd6cfd15b`; predecessor R5.3 set `78de98f8163d2f0bf0ab94781b86bd8e5e0345411a4432669d91fdfc42671d56`.

This is a separate versioned successor. Owner approved the R5.4/NF02 design and new-campaign boundary. Predecessor references/status/reviews inside inherited history are provenance, not current qualification or runtime authority. The current normative file set is exactly the R5.4 manifest; prior source bytes remain untouched. Registered semantics, exact executable bindings, authenticated prior authority and every domain predicate are jointly required.

# BDB AUDIT v2 — DATA AND ARTIFACT CONTRACTS

**Status:** AUTHOR-HOTFIX R5.3.1 CANDIDATE — bootstrap-order correction; exact storage readback qualification pending; no additional Astra review scheduled
**Rewizja:** 2026-09-10 / R5.3.1 bootstrap-order correction candidate
**Self-audit:** `R5_3_1_AUTHOR_HOTFIX_REAUDIT_PASS`; report `BDB_AUDIT_V2_SELF_AUDIT_REPORT_R5_3_1_2026-09-10.md`; external readback qualification remains pending; strict independent freeze is not claimed
**Dokument:** kontrakty danych i artefaktów BDB Audit v2  
**Powiązane dokumenty:**
- `BDB_Audit_vNext_Szczegolowy_Plan_Rozwoju.md`
- `BDB_AUDIT_V2_ARCHITECTURE_SPEC.md`
- `BDB_AUDIT_V1_TO_V2_MIGRATION_AND_COMPATIBILITY.md`

**Cel:** zdefiniować jednoznaczne, machine-readable kontrakty authority, identity, immutable revisions, canonical history, knowledge/discovery provenance, inventory/coverage obligations, evidence, finalization, legacy admission, build provenance i walidację BDB Audit v2.

**Zasada nadrzędna:** istnieje jedna bieżąca `CANONICAL_ACCEPTED_HISTORY` dla campaign. Immutable raw artifacts i object revisions są jej content-bound inputs/outputs; ledgery, grafy, snapshots, summaries i raporty są projekcjami `as_of_head`, chyba że kontrakt jawnie określa historyczny raw artifact jako dowód własnych exact bytes.

---

# 1. Zasada nadrzędna

BDB Audit v2 rozróżnia trzy klasy danych:

1. **Canonical accepted facts/decisions** — zaakceptowane przez coordinatora w jednej historii commitów.
2. **Immutable objects/artifacts** — exact bytes lub canonical objects identyfikowane digestem i referencjonowane przez accepted facts.
3. **Derived projections/exports** — materializowane widoki stanu, które można usunąć i odtworzyć z accepted history + immutable objects.

Narracyjny Markdown nie ustanawia authority dla lineage, state transitions, coverage, evidence, exposure ani STOP. Historyczny legacy artifact pozostaje authority wyłącznie dla własnych exact bytes i zapisanej w nich historycznej treści.

Nie wolno utrzymywać kilku równoległych mutable heads typu `AUDIT_LEDGER`, `COVERAGE_LEDGER`, `state.json` i snapshot jako niezależnych źródeł aktualnego stanu.

---

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
  "kind": "invariant_revision",
  "logical_id": "invariant_revision_<uuidv4-lowercase>",
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
- target nie jest stale/invalidated tam, gdzie wymagany jest ACTIVE support.

Dangling, wrong-type, current-by-name i cross-source references są fail-closed.

---

# 8. Source generation contract

`SOURCE_GENERATION` jest canonical semantic object i oddziela tożsamość source od sposobu jego spakowania.

Minimalnie:

```text
source_generation_id
source_identity_ref
source_identity_profile_ref
repository_authority_ref lub snapshot_authority_ref
materialized_source_manifest_ref
parent_source_generation_ref optional
representation_refs[]
```

## 8.1. SourceIdentityProfile v1

Foundation profile definiuje co najmniej:

```text
profile_id = source_identity/1
authority_mode = AUTHORIZED_GIT | AUTHORIZED_SNAPSHOT
repository_id / snapshot_authority_id
git_object_algorithm optional
path_profile_ref
manifest_entry_profile_ref
submodule_policy
lfs_policy
symlink_policy
mode_policy
```

Dla `AUTHORIZED_GIT` wymagane są exact commit/tree object IDs zgodne z zadeklarowanym algorytmem i authorized repository. Dla snapshot-only używa się odrębnego authority mode; nie wolno udawać Git identity. Repository/snapshot authority ref ma klasę `SOURCE_AUTHORITY_REF`: jego autoryzacja musi wynikać z pinned SourceIdentityProfile/trust boundary niezależnie od tworzonego SourceIdentity/SourceGeneration; nowy same-commit object nie może sam ustanowić authority, które następnie legitymizuje jego własne source identity.

## 8.2. Materialized Source Manifest

`SOURCE_MANIFEST` jest canonical object z deterministycznie posortowanymi entries. Każdy `SourceManifestEntry` zawiera:

```text
repo_relative_posix_path
entry_type = REGULAR_FILE | SYMLINK | SUBMODULE | OTHER_ALLOWED
relevant_mode
byte_length optional-by-type
content_raw_digest optional-by-type
symlink_target optional-by-type
submodule_object_id optional-by-type
lfs_pointer_state optional-by-type
```

Path jest względny, POSIX, bez `.`/`..`, backslash, NUL i niecanonical aliases. Duplicate canonical paths są odrzucane. Nierozwiązany wymagany submodule albo LFS content blokuje `COMPLETE_SOURCE` zamiast być po cichu pomijany.

## 8.3. SourceIdentityBody

`SOURCE_IDENTITY` wiąże:

```text
profile_ref
authority_mode
authorized_repository_or_snapshot_ref
git_commit_object_id optional
git_tree_object_id optional
materialized_source_manifest_ref
completeness_state
```

Canonical Source identity = `ObjectDigest("source_identity", 1, SourceIdentityBody)`. Archive/ZIP `RawDigest` jest identity reprezentacji, nie SourceGeneration. Konflikt commit/tree/manifest tworzy `SOURCE_IDENTITY_CONFLICT`.

Dwa importy tych samych source bytes pod różnymi archive names są **tym samym source identity** wtedy i tylko wtedy, gdy exact profile i authority reconciliation dają ten sam `SourceIdentity ObjectDigest`. `source_generation_id` jest logicznym aliasem tej identity w vault/campaign namespace; validator wymusza one-to-one mapping alias → exact SourceIdentity i odrzuca dwa aktywne aliasy udające różne source generations dla tej samej exact identity bez jawnego import-alias relation. Remediation zmieniająca materialne source bytes tworzy nową SourceGeneration; evidence nie przenosi się bez requalification.

## 8.4. SurfaceKeyProfile v1 i SurfaceRecord

`SurfaceKey` jest source-bound i canonical. Foundation profile:

```text
SurfaceKey = ObjectDigest("surface_key", 1, SurfaceKeyBody)
SurfaceKeyBody:
  source_identity_ref
  canonical_surface_category
  normalized_anchor_descriptor
```

Static anchor descriptor zawiera co najmniej canonical repo path, **zero-based byte offset w oryginalnych raw file bytes**, entry kind i deterministic discriminator. Runtime anchor descriptor zawiera method, normalized route pattern, registration origin i namespace. Nie wolno używać line number po normalizacji, mtime ani collector-local ID jako stable identity.

Canonical `SURFACE_RECORD`:

```text
surface_key
source_identity_ref
surface_category
anchor_descriptor
provenance_refs[]
identity_state = STABLE | PROVISIONAL
```

`SurfaceRecord` nie zawiera backlinku do późniejszego `MaterialityAssessment`. Materiality jest osobnym accepted assessmentem wskazującym już istniejący surface/invariant/scope subject; dzięki temu nie powstaje cykl `subject ↔ assessment`. Ambiguous anchor/identity daje `PROVISIONAL`; nie wolno heurystycznie scalać dwóch surfaces.

---

# 9. Campaign manifest

`CAMPAIGN_GENESIS` jest immutable canonical object zaakceptowanym jako pierwszy domenowy commit campaign.

W baseline v2 `CAMPAIGN_GENESIS.input_history_cut` MUSI być dokładnie `EMPTY_HISTORY_CUT`. Normalny `CampaignGenesis` na istniejącym accepted history jest niedozwolony; continuation po concluded campaign używa odrębnego `SuccessorCampaignGenesis`.

Minimalnie:

```text
campaign_id
input_history_cut                         # EMPTY_HISTORY_CUT for first campaign genesis
bootstrap_admission_decision_ref          # exact earlier content ref in seq=1 bootstrap closure
source_generation_ref
application_generation_ref
protocol_policy_bundle_ref
schema_set_ref
trust_profile_ref
owner_operator_authority_ref
legacy_origin_refs[]
```

`owner_operator_authority_ref` w genesis MUSI być autoryzowany przez exact installation-pinned `TrustProfile`; nie może być same-commit obiektem nadającym authority samemu genesis. `protocol_policy_bundle_ref` i `schema_set_ref`, jeżeli materializowane w pierwszej closure, mogą wyłącznie deterministycznie składać exact policy/spec/schema/serialization pins z `INSTALLATION_BOOTSTRAP_PROFILE_V1`; nie mogą wprowadzać nowych semantyk obowiązujących ten sam first-history commit.

Nie przechowuje mutable `current_stage` ani własnego post-acceptance head jako authority. `bootstrap_admission_decision_ref` musi wskazywać wcześniejszy exact `BootstrapAdmissionDecision` o wyniku dopuszczającym genesis; `BLOCKED_CANONICAL_ADMISSION` zabrania `CampaignGenesisAccepted`. `CAMPAIGN_GENESIS` jest częścią pierwszego accepted domain commit; jego acceptance commit/head istnieje wyłącznie w zewnętrznym envelope/receipt/history position, dzięki czemu genesis nie tworzy self-reference. Aktualny campaign state jest projekcją accepted history.

Zmiana SourceGeneration nie jest aktualizacją Campaign Genesis — wymaga nowej campaign/requalification context.

## 9.1. TrustProfile contract

`TRUST_PROFILE` jest immutable canonical object przypiętym w Campaign Genesis:

```text
trust_profile_id
trust_profile_revision
coordinator_authority_ref
vault_protection_class
executor_write_boundary
history_anchor_mode
external_anchor_profile_ref optional
guarantees[]
explicit_non_guarantees[]
recovery_pin_policy_ref
```

`history_anchor_mode`:

```text
UNPINNED
LOCAL_PINNED
EXTERNALLY_PINNED_THROUGH
```

Baseline `LOCAL_PINNED` wymaga, aby active canonical vault był poza writable namespace executorów objętych deklarowaną izolacją. `EXTERNALLY_PINNED_THROUGH` dodatkowo wiąże `commit_seq` i `commit_hash` niezależnie zachowanym pinem/receipt.

`external_anchor_profile_ref` opisuje **mechanizm/konfigurację przyszłych kotwic**, a nie konkretny późniejszy pin. Konkretne accepted heady są kotwiczone dopiero przez późniejsze `HISTORY_ANCHOR_RECEIPT`; `TrustProfile` nie może referencjonować future receipt.

`TrustProfile` MUSI jawnie stwierdzać, że full-host rollback/restore obejmujący vault i wszystkie lokalne pins jest niewykrywalny bez niezależnej kotwicy. Sam SHA/signature umieszczony na tym samym całkowicie przejętym hoście nie podnosi gwarancji świeżości.

## 9.2. HistoryAnchorReceipt

Przy `EXTERNALLY_PINNED_THROUGH` canonical object `HISTORY_ANCHOR_RECEIPT` wiąże:

```text
anchor_receipt_id
campaign_ref
accepted_head_seq
accepted_head_hash
anchor_profile_ref
issuer_or_channel_ref
external_storage_or_witness_ref
anchor_observation_ref
created_at informational
```

Receipt musi być przechowywany poza rollback domain, przed którym ma chronić. Receipt znajdujący się wyłącznie w tym samym cofniętym vault/host nie stanowi niezależnej kotwicy.

---

# 10. StageSpec artifact

StageSpec jest immutable, policy-pinned object:

```text
stage_key
stage_spec_revision
stage_role
stage_ordinal
purpose
predecessor_requirements
required_lane_slots[]
optional_lane_slots[]
blind_reveal_phase_model
allowed_corpus_roles[]
forbidden_corpus_roles[]
coverage_obligation_policy_ref
required_stage_completion_outputs[]
transition_policy_ref
stop_e6_relationship
```

Zmiana semantyki po starcie nie reinterpretuję istniejącego StageRun; nowy run wskazuje nową exact StageSpec revision.

---

# 11. LaneSpec artifact

LaneSpec jest immutable revision:

```text
lane_key
lane_spec_revision
stage_spec_revision
purpose
primary_strategy
scope_selectors[]
exploration_policy_ref
allowed_view_classes[]
forbidden_knowledge_classes[]
required_isolation_assurance
required_outputs[]
executor_capability_requirements[]
budget_effort_profile_ref
completion_predicate_ref
```

`blindness_requirement` nie jest booleanem. Musi wskazywać wymagany isolation class i forbidden exposure classes.

---

# 12. ExecutorSpec

ExecutorSpec / ExecutorProfile revision wiąże:

```text
executor_profile_id
executor_profile_revision
executor_tool_ref
model_profile_ref optional
runtime_profile_ref
supported_capabilities[]
isolation_capabilities[]
filesystem_boundary_ref
network_boundary_ref
tool_boundary_ref
session_freshness contract
evidence collection capabilities
known limitations[]
```

Samo użycie innego modelu/toola nie ustanawia evidence independence ani blindness.

---

# 13. DeliverySpec

DeliverySpec / DeliveryProfile revision określa kontrolowany transport:

```text
delivery_profile_id
delivery_profile_revision
delivery_channel
grant_before_delivery_required
view_manifest_required
ack semantics
retry_policy_ref
idempotency_policy_ref
potential_exposure_point
redaction profile
resolver capabilities
```

`PotentialExposure` zaczyna się w momencie accepted grant zgodnie z policy, nie dopiero po dobrowolnym ACK executora.

---

# 14. Run manifest

Native v2 `RUN_MANIFEST` jest exportem/projection manifestem exact StageRun/LaneRun/Attempt cut, nie drugim state authority.

Minimalnie:

```text
campaign_id
stage_run_ref
lane_run_ref optional
attempt_ref optional
source_generation_ref
assigned_history_cut
stage_spec_ref
lane_spec_ref optional
executor_profile_ref optional
delivery_profile_ref optional
assignment_manifest_ref optional
knowledge_state_ref optional
protocol_policy_ref
schema_set_ref
export_as_of_head
```

Dla attempt-level manifestu używanego do execution `attempt_ref`, `assignment_manifest_ref` i `knowledge_state_ref` są obowiązkowe i muszą wskazywać ten sam exact assignment/Attempt. Manifest nie rozwiązuje „current knowledge by ID”.

Legacy `RUN_MANIFEST.json` jest walidowany w legacy contract profile i zachowuje własną historyczną semantykę.

## 14.1. Canonical StageRun / LaneRun / Attempt contracts

`RUN_MANIFEST` pozostaje projection. Authority tworzą immutable creation revisions + accepted transitions.

`STAGE_RUN` creation revision:

```text
stage_run_id
campaign_ref
stage_spec_ref
source_generation_ref
creation_input_history_cut
assigned_history_cut
predecessor_stage_completion_refs[]
required_lane_slot_contract_refs[]
successor_of_stage_run_ref optional
```

`LANE_RUN` creation revision:

```text
lane_run_id
stage_run_ref
lane_spec_ref
source_generation_ref
creation_input_history_cut
successor_of_lane_run_ref optional
required_result_slots[]
```

`successor_of_lane_run_ref`, jeżeli obecne, jest **backward-only** i wskazuje wcześniej accepted LaneRun, którego follow-up/reopen reprezentuje nowy run.

`ATTEMPT` creation revision:

```text
attempt_id
lane_run_ref
attempt_nonce
executor_profile_ref
delivery_profile_ref
assigned_history_cut
retry_of_attempt_ref optional
retry_reason_ref optional
result_slot_contracts[]
```

`retry_of_attempt_ref` jest backward-only. Retry execution zawsze tworzy nowy Attempt; nie mutuje poprzedniego Attempt ani jego terminalnego result slotu.

`AttemptCreated` **nie** zawiera `initial_knowledge_state_ref`, grantów ani assignment manifestu. Te obiekty powstają później i mogą wskazywać już istniejący Attempt; creation revision nie może przewidywać przyszłego KnowledgeState. Normatywny DAG inicjalizacji attemptu jest opisany w §14.3–14.4.

`campaign_ref` jest logical reference do campaign identity ustanowionej przez accepted `CampaignGenesis` albo `SuccessorCampaignGenesis`; nie istnieje osobny canonical `CAMPAIGN` object przechowujący lifecycle state. CampaignState pozostaje projekcją accepted transition facts.

Bieżący state każdego aggregate jest projection accepted transition facts. Retry execution tworzy nowy Attempt; retry tego samego upload/command jest idempotentny. Cancel/supersede/completion/late-result nie mutują creation revision. Late material result po completion wymaga quarantine + **successor/reopen flow** zgodnie z pinned StageSpec/policy; historyczny `StageCompletion` nigdy nie jest rewidowany ani mutowany.

## 14.2. Foundation FSM state enums

Canonical current-state projections używają pinned transition profile. Foundation enums:

```text
CampaignState =
  CREATED | GENESIS_ACCEPTED | E0_READY | AUDIT_RUNNING |
  E6_REQUIRED | E6_RUNNING | BLOCKED | CANCELLED |
  CAMPAIGN_CONCLUDED | CLOSED

StageRunState =
  PLANNED | READY | RUNNING | WAITING_FOR_REQUIRED_INPUT |
  COMPLETION_CANDIDATE | COMPLETION_ACCEPTED | BLOCKED | CANCELLED | SUPERSEDED

LaneRunState =
  PLANNED | READY | RUNNING | WAITING_RESULT | COMPLETION_CANDIDATE |
  COMPLETION_ACCEPTED | BLOCKED | CANCELLED | SUPERSEDED

AttemptState =
  CREATED | STARTED | RESULT_RECEIVED | RESULT_ACCEPTED |
  FAILED | BLOCKED | CANCELLED | SUPERSEDED
```

Każda zmiana state wymaga accepted transition fact z exact prior state/ref, governing transition policy i input HistoryCut. Nie ma mutable `state` row jako authority. Illegal, stale-parent i late transition są fail-closed.

Foundation `TRANSITION_PROFILE_V1` dopuszcza tylko jawnie wyliczone edges; StageSpec/LaneSpec może **zawężać**, lecz nie dodawać edge omijającego wymagany gate:

```text
Campaign:
CREATED → GENESIS_ACCEPTED
GENESIS_ACCEPTED → E0_READY | BLOCKED | CANCELLED
E0_READY → AUDIT_RUNNING | BLOCKED | CANCELLED
AUDIT_RUNNING -- intermediate StopEvaluation=CONTINUE_REQUIRED --> AUDIT_RUNNING   # accepted decision, no lifecycle transition
AUDIT_RUNNING -- intermediate StopEvaluation=BLOCKED --> BLOCKED
AUDIT_RUNNING -- final StopEvaluation=CONTINUE_REQUIRED --> AUDIT_RUNNING   # finalization precondition violation; ordinary work resumes
AUDIT_RUNNING -- final/post-E5 StopEvaluation=E6_REQUIRED --> E6_REQUIRED
AUDIT_RUNNING -- final StopEvaluation=PASS + accepted ConcludeCampaign --> CAMPAIGN_CONCLUDED
AUDIT_RUNNING -- final StopEvaluation=BLOCKED --> BLOCKED
AUDIT_RUNNING -- final StopEvaluation=BLOCKED + authorized limited ConcludeCampaign --> CAMPAIGN_CONCLUDED
E6_REQUIRED → E6_RUNNING | BLOCKED
E6_REQUIRED -- authorized `COMPLETED_LIMITED` conclusion --> CAMPAIGN_CONCLUDED
E6_RUNNING -- post-E6 StopEvaluation=E6_REQUIRED --> E6_REQUIRED
E6_RUNNING -- post-E6 StopEvaluation=PASS + accepted ConcludeCampaign --> CAMPAIGN_CONCLUDED
E6_RUNNING -- post-E6 StopEvaluation=BLOCKED --> BLOCKED
E6_RUNNING -- post-E6 StopEvaluation=BLOCKED + authorized limited ConcludeCampaign --> CAMPAIGN_CONCLUDED
BLOCKED -- accepted ResolveBlocker/ReopenCampaign with exact resolved_blocker_refs[] and unchanged SourceGeneration/pinned governing policy --> AUDIT_RUNNING
BLOCKED → CAMPAIGN_CONCLUDED only by authorized `COMPLETED_LIMITED`
CAMPAIGN_CONCLUDED → CLOSED
CANCELLED is an administrative terminal state; it does not imply CampaignConclusion, assurance sufficiency or ReleaseQualification and does not transition to CLOSED through the assurance-conclusion path.

StageRun:
PLANNED → READY | BLOCKED | CANCELLED
READY → RUNNING | BLOCKED | CANCELLED
RUNNING ↔ WAITING_FOR_REQUIRED_INPUT
RUNNING → COMPLETION_CANDIDATE | BLOCKED | CANCELLED
WAITING_FOR_REQUIRED_INPUT → COMPLETION_CANDIDATE | BLOCKED | CANCELLED
COMPLETION_CANDIDATE → COMPLETION_ACCEPTED | RUNNING | BLOCKED
PLANNED | READY | RUNNING | WAITING_FOR_REQUIRED_INPUT | COMPLETION_CANDIDATE → SUPERSEDED

LaneRun:
PLANNED → READY | BLOCKED | CANCELLED
READY → RUNNING | BLOCKED | CANCELLED
RUNNING → WAITING_RESULT | COMPLETION_CANDIDATE | BLOCKED | CANCELLED
WAITING_RESULT → RUNNING | COMPLETION_CANDIDATE | BLOCKED | CANCELLED
COMPLETION_CANDIDATE → COMPLETION_ACCEPTED | RUNNING | BLOCKED
PLANNED | READY | RUNNING | WAITING_RESULT | COMPLETION_CANDIDATE → SUPERSEDED

Attempt:
CREATED → STARTED | CANCELLED | SUPERSEDED
STARTED → RESULT_RECEIVED | FAILED | BLOCKED | CANCELLED | SUPERSEDED
RESULT_RECEIVED → RESULT_ACCEPTED | FAILED | BLOCKED | SUPERSEDED
```

`COMPLETION_ACCEPTED`, `RESULT_ACCEPTED`, `CANCELLED`, `SUPERSEDED`, `FAILED` i historyczne Stage/Lane/Attempt `BLOCKED` terminal states nie są mutowane. Reopen/follow-up tworzy successor run/attempt zgodnie z policy. Campaign `BLOCKED` **nie jest termination_state**: może pozostać blocked, zostać wznowiona przez accepted `ResolveBlocker/ReopenCampaign` po udokumentowanym usunięciu blockerów albo zostać zakończona przez jawny `COMPLETED_LIMITED` conclusion. Nie istnieje bezpośredni `BLOCKED → PASS`; po wznowieniu wymagany jest nowy StopEvaluation na nowym cut. Campaign `CANCELLED` jest administracyjnie terminalna i sama nie tworzy assurance conclusion/release qualification. Requalification po remediation jest **nowym cross-generation context/campaign**, nie stanem starej frozen-source campaign. `COMPLETED_LIMITED` jest `CampaignConclusion.termination_state`, a nie dodatkowym `CampaignState`.

`ordinary_stages_complete`, `candidate_assurance_ready`, `challenge_complete` i `latest_stop_evaluation_ref` są **derived readiness facts/views**, nie `CampaignState`. Intermediate STOP może być zaakceptowany po E1/E2/E3/E4 bez Candidate Assurance Case/challengers i służy wyłącznie do deterministycznego `CONTINUE_REQUIRED/BLOCKED` na bieżącym cut. Candidate/challenger prerequisites obowiązują dopiero dla final/post-E5 lub post-E6 evaluation, która może prowadzić do `PASS`, `E6_REQUIRED` albo campaign conclusion.

Dla `evaluation_context=INTERMEDIATE` release axis jest również fail-closed: `READY` i `READY_WITH_RESIDUAL_RISK` są zabronione. Jeżeli current evidence już potwierdza defect wykluczający release według pinned release policy, evaluator może zwrócić `TECHNICALLY_NOT_READY`; w przeciwnym razie, ponieważ final release prerequisites nie są jeszcze zamknięte, zwraca `QUALIFICATION_BLOCKED`.

## 14.3. GrantBody i initial KnowledgeState DAG

Po `AttemptCreated` coordinator może zaakceptować immutable `GRANT_BODY`:

```text
grant_id
attempt_ref
previous_knowledge_state_ref optional   # null dla initial delivery
grant_input_history_cut                 # accepted head PRZED command/commit
view_manifest_ref
delivery_profile_ref
capability_profile_ref optional
forbidden_knowledge_policy_ref
channel_class
```

`GrantAccepted` wskazuje istniejący Attempt i opcjonalnie poprzedni KS; nie zawiera future KnowledgeState/Assignment refs. Zgodnie z fail-closed exposure semantics zaakceptowany grant tworzy potencjalną exposure niezależnie od późniejszego ACK delivery.

Canonical `POTENTIAL_EXPOSURE_RECORD` może być zmaterializowany jako immutable object:

```text
exposure_id
attempt_ref
grant_ref
previous_knowledge_state_ref optional
view_manifest_ref
channel_class
exposure_input_history_cut              # prior accepted cut
```

Następnie może powstać initial/successor `KNOWLEDGE_STATE`. Jego `basis_history_cut` jest **input cutem sprzed accepting commit**, a nowe grant/exposure dependencies są reprezentowane przez exact object refs (`potential_exposure_refs[]`), nie przez próbę wskazania post-commit head. Dzięki temu Attempt→Grant→Exposure→KnowledgeState pozostaje acyklicznym content-hash DAG nawet wtedy, gdy wszystkie obiekty są akceptowane w jednym commicie w topologicznej kolejności. Attempt nie wskazuje w przód na KnowledgeState.

## 14.4. AssignmentManifest i AttemptStarted

Canonical `ASSIGNMENT_MANIFEST` powstaje **po** initial KnowledgeState:

```text
assignment_manifest_id
attempt_ref
source_generation_ref
assignment_input_history_cut
knowledge_state_ref
grant_refs[]
view_manifest_refs[]
executor_profile_ref
delivery_profile_ref
stage_spec_ref
lane_spec_ref
result_slot_contract_refs[]
```

Dopuszczalny porządek foundation jest jednokierunkowy:

```text
AttemptCreated object
→ GrantBody object
→ PotentialExposureRecord object
→ KnowledgeState object
→ AssignmentManifest object
→ accepted events in the same or later commit
→ AttemptStarted
```

`AttemptStarted` wymaga accepted `assignment_manifest_ref` dla tego samego Attempt i source/spec bindings. `AssignmentManifest` nie jest częścią `AttemptCreated` i nie może być retroaktywnie wbudowany w creation revision. Retry execution tworzy nowy Attempt i nowy DAG inicjalizacji.

## 14.5. Successor campaign po accepted conclusion

`CAMPAIGN_CONCLUDED` nie wraca do `AUDIT_RUNNING`. Materialny accepted trigger po conclusion (np. nowy subsystem, harness/oracle invalidation, source-generation drift wymagający ponownego assurance) może oznaczyć applicability poprzedniego assurance jako `STALE`, ale nie mutuje historycznego `CampaignConclusion`.

Nowe assurance powstaje przez **successor campaign**:

```text
SuccessorCampaignGenesis:
  campaign_id
  predecessor_campaign_ref
  predecessor_conclusion_ref
  successor_trigger_ref
  source_generation_ref
  successor_input_history_cut
  carried_forward_qualification_refs[]
  newly_required_obligation_refs[]
  challenge_freshness_policy_ref
  governing_policy_ref
  governing_spec_refs[]
```

Rules:

- predecessor/conclusion refs są backward exact refs; predecessor nie wskazuje future successor;
- stare StageCompletion/StopEvaluation/CampaignConclusion pozostają immutable;
- carried-forward evidence jest dopuszczalne tylko po current applicability/invalidation assessment;
- materialnie zmieniony Candidate Assurance Case wymaga nowych obu baseline challenger roles;
- `CurrentAssuranceSelection` jest derived z jednej accepted successor chain. Dwie konkurencyjne successor branches dla tego samego predecessor/context powodują `ASSURANCE_SUCCESSOR_CONFLICT` i fail-closed `STALE/BLOCKED` do accepted `SuccessorCampaignSelectionDecision`;
- `SuccessorCampaignSelectionDecision` ma exact `predecessor_conclusion_ref`, `candidate_successor_campaign_refs[]`, jeden `selected_successor_campaign_ref`, `resolution_basis_refs[]`, `governing_policy_ref` i `input_history_cut`; selected ref MUSI należeć do candidate set, wszystkie candidate refs muszą mieć ten sam predecessor/context, a decyzja nie usuwa/nie mutuje odrzuconych historycznych branches;
- przy kolejnej materialnej zmianie selection/policy powstaje nowa immutable selection decision; derived current selector wskazuje najnowszą applicable accepted decision dla exact branch set, nigdy „latest campaign by time”;
- release-only drift, który nie narusza audit assurance basis, może być obsłużony przez §80.1 bez successor campaign.

---

## 14.6. First-history bootstrap transaction

`EMPTY_HISTORY` nie jest pustym miejscem, w którym implementator sam wybiera initial policy/schema/trust. Pierwsza historia jest ustanawiana przez jeden jawny initialization protocol. Przed pierwszym accepted commit trusted installation posiada poza campaign history dokładnie jeden pinned `INSTALLATION_BOOTSTRAP_PROFILE_V1`, identyfikowany exact digestem/locator pinem należącym do `LOCAL_PINNED` trust boundary. Profil nie jest runtime current-state authority; jest zewnętrznym root-of-trust dla sprawdzenia pierwszego commitu i przypina co najmniej:

```text
initial_schema_registry_ref
initial_artifact_contract_registry_ref
initial_serialization_profile_ref
initial_governing_policy_ref
initial_transition_profile_ref
initial_trust_profile_ref
initial_source_identity_profile_ref
allowed_initial_command_kind = INITIALIZE_CAMPAIGN_FROM_LEGACY
allowed_history_namespace_ref
```

Pierwszy authority-changing command w legacy bootstrap używa:

```text
INITIALIZE_CAMPAIGN_FROM_LEGACY
expected_parent_head = EMPTY_HISTORY
bootstrap_profile_ref = exact INSTALLATION_BOOTSTRAP_PROFILE_V1 pin
```

W jednym atomic commit `commit_seq=1` coordinator może zaakceptować przygotowane wcześniej immutable content objects. External `INSTALLATION_BOOTSTRAP_PROFILE_V1` pins są validation contextem; same nie stają się same-commit dependencies przez fakt przypięcia. Dla domain nodes pierwszej initialization obowiązuje następujący canonical precedence:

```text
external installation pins / typed content prerequisites
→ command payload object optional (tylko gdy CommandEnvelope używa `command_payload_ref`)
→ CommandEnvelope
→ SourceGeneration / exact current target source object
→ LEGACY_RAW_REF
→ LegacyMechanicalValidationAssessment
→ SourceReconciliationAssessment
→ LineageAdmissionAssessment
→ LegacyExposureReconstructionAssessment optional
→ TrustedPredecessorSelectionDecision required for canonical-predecessor role
→ BootstrapAdmissionDecision
→ CampaignGenesis
→ ordered acceptance events
→ CommitBody(seq=1, EMPTY_HISTORY)
→ CommandReceipt sidecar / AcceptedHead(seq=1)
```

**R5.3.1 / `BDB_BOOTSTRAP_PRECEDENCE_V1`:** canonical `immutable_object_refs[]` order nie jest drugim sortem ani ręcznie zapisaną listą. Dla scope `command_kind=INITIALIZE_CAMPAIGN_FROM_LEGACY`, `commit_seq=1`, `expected_parent=EMPTY_HISTORY` graph wejściowy dla jednego algorytmu Kahn jest unionem: `(A)` wszystkich same-commit typed content-ref dependency edges wymaganych przez complete Registry/schema contracts oraz `(B)` exact order-only precedence edges wyprowadzonych wyłącznie z przypiętego machine profile `BDB_BOOTSTRAP_PRECEDENCE_V1`. Profile ma ordered kind groups od `command_envelope` do `campaign_genesis`; dla każdej pary obecnych grup `i<j` każdy node grupy `i` precedes każdy node grupy `j`. Wewnątrz tej samej grupy oraz dla nodes poza profilem działa normalny typed tie-break. Opcjonalna nieobecna grupa nie tworzy node ani edge.

Order-only precedence edge uczestniczy w cycle detection i canonical sequence/CommitBody identity, ale **nie jest material/content reference**. Nie tworzy reachability, authority, acceptance/history provenance, object identity ani nie spełnia required typed-ref cardinality. Nie wolno z niego wyprowadzać pola body. `LEGACY_RAW_REF` celowo pozostaje minimalnym raw reference bez `source_generation_ref`; bootstrapowe `source_generation → legacy_raw_ref` jest wyłącznie canonical ordering constraint. Command payload i SourceGeneration prerequisites nadal są porządkowane przez ich rzeczywiste typed refs. Unknown/unpinned precedence profile albo cycle w union DAG blokuje acceptance.

Każdy assessment/admission/genesis body ma `*_input_history_cut = EMPTY_HISTORY_CUT` oraz może wskazywać wyłącznie wcześniejsze objects tej same-commit closure albo immutable object/profile już przypięty przez `INSTALLATION_BOOTSTRAP_PROFILE_V1`. `EMPTY_HISTORY_CUT` nie oznacza, że te objects były wcześniej accepted facts; history provenance powstaje dopiero przez commit `seq=1`. Wymaganie „already accepted on input cut” nie dotyczy tej jedynej initialization closure — zastępuje je `BOOTSTRAP_SAME_COMMIT_CONTENT_REF` + union-DAG topological validation + exact bootstrap-profile pin.

`CampaignGenesis` w tym commicie MUSI wskazywać exact `BootstrapAdmissionDecision` dla requested canonical predecessor (albo jawnie zdefiniowany no-legacy bootstrap profile, jeśli taki profile zostanie kiedyś dodany); nie może zostać zaakceptowany wcześniej niż admission decision w closure. Jeśli admission result=`BLOCKED_CANONICAL_ADMISSION`, `CampaignGenesisAccepted` jest niedozwolony i pierwszy command nie może atomowo ustanowić pozornego legalnego campaign genesis.

Po accepted `seq=1`:

- `INSTALLATION_BOOTSTRAP_PROFILE_V1` pozostaje provenance/trust root pierwszego commitu, nie mutable campaign authority;
- current policy/schema/trust dla dalszych commandów wynikają z exact revisions zaakceptowanych/przypiętych w canonical history;
- `EMPTY_HISTORY`, `EMPTY_HISTORY_CUT` i `INITIALIZE_CAMPAIGN_FROM_LEGACY` są niedozwolone dla tego history namespace;
- retry identycznego initialization commandu zwraca ten sam receipt; różny initialization command po `seq=1` jest `EMPTY_HISTORY_AFTER_INITIALIZATION` / `INITIALIZATION_ALREADY_COMPLETED`.

Ten protocol jest jedynym baseline rozwiązaniem FR-03; zero hash, synthetic H0, fabricated pre-genesis history oraz acceptance assessments w osobnych pre-genesis heads są niedozwolone.

---

# 15. Audit ledger

Canonical authority nie jest zbiorem niezależnych ledger heads. BDB v2 posiada jedną `CANONICAL_ACCEPTED_HISTORY`. `AUDIT_LEDGER.jsonl` może być deterministycznym eksportem tej historii `as_of_head`, ale nie jest osobnym mutable source of truth.

## 15.1. CommandEnvelope

Każda authority-changing próba rozpoczyna się canonical `COMMAND_ENVELOPE`:

```text
command_id = command_<uuidv4-lowercase>
command_kind
campaign_ref optional-by-command-kind
proposed_campaign_id optional-by-command-kind
history_namespace_ref optional-by-command-kind
bootstrap_profile_ref optional-by-command-kind
actor_ref
expected_parent_head
governing_policy_ref
governing_spec_refs[]
command_payload_ref lub inline canonical payload
idempotency_scope
```

`expected_parent_head` jest tagged union:

```text
EMPTY_HISTORY
| ACCEPTED_HEAD_REF(commit_seq, commit_hash)
```

`EMPTY_HISTORY` jest dozwolone wyłącznie dla pierwszego accepted commit w nowym canonical history namespace. Nie posiada synthetic hash/H0 i po acceptance pierwszego commitu jest niedozwolone jako parent dla kolejnych commandów. Ponowne użycie jest fail-closed `EMPTY_HISTORY_AFTER_INITIALIZATION`.

Dla `command_kind=INITIALIZE_CAMPAIGN_FROM_LEGACY` obowiązuje odrębny initialization context: `campaign_ref` jest **zabronione** (campaign jeszcze nie istnieje), natomiast wymagane są `proposed_campaign_id`, `history_namespace_ref` i exact `bootstrap_profile_ref=INSTALLATION_BOOTSTRAP_PROFILE_V1`; `expected_parent_head=EMPTY_HISTORY`. Dla wszystkich post-genesis commandów `campaign_ref` jest wymagane i MUSI wskazywać prior accepted campaign identity z `expected_parent_head`; same-commit CampaignGenesis nie może być targetem zwykłego commandu. Initialization-only fields są zabronione, a expected parent jest exact accepted head. Dzięki temu pierwszy CommandEnvelope nie zawiera future ref do własnego CampaignGenesis.

`command_digest = ObjectDigest("command_envelope", 1, CommandEnvelopeBody)` i jest dokładnie `revision_digest` referenced `COMMAND_ENVELOPE`. Registry wire kind i ObjectDigest domain kind MUSZĄ być identyczne; alias `command` jest niedozwolony. Ten sam `command_id` z innym digestem = `ID_REUSE_CONFLICT`.

`CommitBody.command_ref` MUSI wskazywać exact `COMMAND_ENVELOPE` revision zaakceptowaną przez **ten sam commit** i obecną w `immutable_object_refs[]` canonical closure; prior-accepted command reuse w nowym CommitBody jest niedozwolony. `CommitBody.command_digest` MUSI być równy `ObjectDigest("command_envelope",1,CommandEnvelopeBody)` / revision digestowi referenced CommandEnvelope. Jeżeli CommitBody kopiuje `actor_ref`, `expected_parent_head`, `governing_policy_ref` albo `governing_spec_refs[]`, wartości MUSZĄ być identyczne z CommandEnvelope. Rozbieżność jest fail-closed `COMMAND_BINDING_CONFLICT`; nie istnieje równoległy `request_digest`.

`governing_policy_ref` i `governing_spec_refs[]` CommandEnvelope/CommitBody są **history-context bindings**, nie zwykłymi content refs. Dla normalnego commandu MUSZĄ wynikać z exact `expected_parent_head` / input history context; policy/spec revision zaakceptowana w tym samym commicie nie może walidować ani reinterpretować commandu, który ją wprowadza. Dla `EMPTY_HISTORY` wartości MUSZĄ odpowiadać external `INSTALLATION_BOOTSTRAP_PROFILE_V1` pins. Policy/spec upgrade staje się dostępny dopiero dla kolejnego commandu na nowym accepted head, chyba że osobny przyszły contract jawnie definiuje inną bezpieczną activation boundary.

`actor_ref` identyfikuje wykonawcę/żądającego, ale **nie ustanawia sam sobie authority**. Akceptacja commandu MUSI zweryfikować actor authority względem prior accepted `expected_parent_head` albo — wyłącznie dla `EMPTY_HISTORY` — exact `INSTALLATION_BOOTSTRAP_PROFILE_V1` trust root. Obiekt actor/authority utworzony w tym samym commicie nie może autoryzować commandu, który go akceptuje.

## 15.2. CommitBody i CommitHash

Canonical `CommitBody` obejmuje co najmniej:

```text
campaign_id
commit_seq
prev_history_ref = EMPTY_HISTORY | ACCEPTED_HEAD_REF(commit_seq, commit_hash)
command_ref
command_digest
actor_ref
expected_parent_head = EMPTY_HISTORY | ACCEPTED_HEAD_REF(commit_seq, commit_hash)
governing_policy_ref
governing_spec_refs[]
ordered_event_bodies[]
immutable_object_refs[]   # canonical topological sequence, NOT a set
```

Dla `commit_seq=1` oba parent bindings MUSZĄ być `EMPTY_HISTORY`; dla `commit_seq>1` oba MUSZĄ wskazywać ten sam exact prior accepted head i `EMPTY_HISTORY` jest odrzucane. Nie ma zero-hash ani synthetic H0.

`ordered_event_bodies[]` ma canonical order równy event ordinal `0..n-1`; duplicate ordinals i alternatywne sortowanie są niedozwolone. Event body nie zawiera własnego `(commit_hash, ordinal)`; pełny event ref powstaje dopiero po obliczeniu commit hash.

`immutable_object_refs[]` jest **canonical topological sequence**. Walidator: (1) buduje dependency edges z typed content refs między nowymi objectami, (2) dodaje wyłącznie jawne scope-bound **order-only precedence edges** z exact pinned ArtifactContractRegistry/profile, jeżeli dany command/commit scope dokładnie je aktywuje, (3) odrzuca dangling/self/future/duplicate oraz cycle w **union graph**, (4) wykonuje dokładnie jeden deterministic Kahn topological sort, (5) dla wielu aktualnie dostępnych nodes wybiera najmniejszy typed tie-break `(kind, logical_id_or_empty, revision_digest)`, (6) wymaga byte-for-byte equality zapisanej sequence z wynikiem sortu. Set-like sort key nie może zastąpić dependency order. Order-only precedence nie jest content refem i nie może spełnić referential-integrity/cardinality/authority/provenance requirement; służy wyłącznie canonical ordering/cycle detection. Baseline jedynym takim profilem jest `BDB_BOOTSTRAP_PRECEDENCE_V1` dla first-history initialization.

```text
commit_hash = ObjectDigest("commit_body", 1, CommitBody)
```

## 15.3. AcceptedHead

`ACCEPTED_HEAD`:

```text
campaign_id
commit_seq
commit_hash
```

Head update jest atomową częścią accepted commit. Mutable storage pointer może istnieć implementacyjnie, lecz jego semantyka jest dokładnie powyższa i po crash recovery musi wskazywać ostatni w pełni committed commit.

## 15.4. HistoryCut

`HISTORY_CUT` jest tagged immutable exact **value/reference**, nie osobnym state transition authority:

```text
HistoryCut =
  EMPTY_HISTORY_CUT { history_namespace_ref, governing_policy_ref, governing_spec_refs[] }
  | ACCEPTED_HISTORY_CUT { campaign_id, accepted_head_seq, accepted_head_hash, governing_policy_ref, governing_spec_refs[] }
```

`EMPTY_HISTORY_CUT` jest legalny tylko jako initialization/bootstrap input przed pierwszym accepted commit danego history namespace. Nie jest accepted factem, nie ma synthetic digestu i nie może być użyty jako cut dla evidence/STOP/StageCompletion po powstaniu pierwszego head. Pierwszy accepted commit ustanawia `accepted_head_seq=1`; wszystkie późniejsze cuts są `ACCEPTED_HISTORY_CUT`. W wariancie EMPTY `governing_policy_ref` MUSI równać się `initial_governing_policy_ref`, a baseline `governing_spec_refs[]` MUSI być dokładnie canonical one-element set zawierającym `initial_transition_profile_ref` z `INSTALLATION_BOOTSTRAP_PROFILE_V1`; przyszły bootstrap profile może rozszerzyć ten set wyłącznie przez nową wersję profile. Są to installation-pinned inputs, nie twierdzenie o prior accepted history. W wariancie ACCEPTED policy/spec bindings muszą dokładnie odpowiadać aktywnym revisions wynikającym z referenced accepted head; `schema_set_ref` nie jest aliasem governing spec refs.
HistoryCut value nie wymaga osobnej acceptance: wariant ACCEPTED jest deterministycznie konstruowany z exact accepted head + aktywnych policy/spec bindings, a wariant EMPTY z exact installation pins. Samo utworzenie/serializacja HistoryCut nie przesuwa head i nie tworzy nowego faktu historii.

Gate/qualification/discovery/STOP nie używają „latest” bez jawnego accepted cut.

## 15.5. CommandReceipt

Po accepted commit coordinator zwraca canonical **acceptance sidecar** `COMMAND_RECEIPT`:

```text
command_id
command_ref
result_object_refs[]
accepted_commit_ref
accepted_head
receipt_status = ACCEPTED
```

Receipt jest utrwalany atomowo z commit acceptance/head update, ale **nie jest eventem ani immutable-object ref w `CommitBody` tego samego commit**. `CommandReceipt.command_ref` MUSI równać się `accepted_commit_ref.command_ref`; receipt nie może wskazać innego wcześniejszego CommandEnvelope. `accepted_commit_ref` wskazuje exact accepted `CommitBody`/jego `commit_hash`; `accepted_head` wskazuje odrębny accepted-head tuple. Commit ref i head ref nie są tym samym target type. Jego `ObjectDigest` nie uczestniczy w `commit_hash`; dzięki temu `accepted_commit_ref`/`accepted_head` mogą wskazać już obliczony accepting commit bez cyklu `commit_hash ↔ receipt_digest`. Canonical history pozostaje authority; receipt jest content-addressed idempotency/acceptance proof sidecar.

Retry tego samego `command_id` + exact `command_ref.revision_digest` zwraca **ten sam persisted canonical receipt**; API/CLI może poza canonical receipt opisać transportową sytuację jako `ALREADY_ACCEPTED`, ale nie zmienia to receipt bytes/digest i nie tworzy drugiego commit/effect.

Commit acceptance atomowo zapewnia trwałość wszystkich wymaganych nowych immutable objects, CommitBody, receipt i head update. Crash recovery nie może ujawnić receipt dla niecommitted commit ani committed head bez odpowiadającego persisted receipt. Backend storage jest implementacyjnym profilem. SQLite może być reference implementation, ale kontrakt wymaga semantyki transakcyjnej, nie konkretnego produktu.

---

# 16. Ledger event types

Canonical history zapisuje typed facts/decisions, m.in.:

```text
CampaignGenesisAccepted
SuccessorCampaignGenesisAccepted
SuccessorCampaignSelectionDecisionAccepted
StageRunCreated
LaneRunCreated
AttemptCreated
AttemptStarted
ArtifactAccepted
CheckpointSealed
GateEvaluated
GrantAccepted
PotentialExposureRecorded
ContaminationAssessmentAccepted
IsolationQualificationAccepted
KnowledgeStateAdvanced
AssignmentManifestAccepted
DiscoveryRecorded
HypothesisAccepted
ExperimentPreregistered
ExecutionDescriptorAccepted
FaultRunRecordAccepted
ExecutionResultAccepted
ObservationAccepted
EvidenceQualificationAccepted
EvidenceApplicabilityAssessmentAccepted
EvidenceInvalidated
InventoryRevisionAccepted
MaterialityAssessmentAccepted
CoverageObligationCreated
CoverageObligationApplicabilityAccepted
CoverageObligationQualified
ApprovalDecisionAccepted
FindingClaimRevisionAccepted
FindingAxisAssessmentAccepted
FindingAdjudicationAccepted
RootCauseRevisionAccepted
ContradictionRevisionAccepted
ContradictionResolutionAccepted
LaneCompletionAccepted
StageCompletionAccepted
CandidateAssuranceCaseAccepted
ChallengerAssignmentAccepted
ChallengerResultAccepted
StopEvaluationAccepted
CampaignConclusionAccepted
ReleaseQualificationAccepted
LegacyRawRefAccepted
LegacyMechanicalValidationAssessmentAccepted
SourceReconciliationAssessmentAccepted
LineageAdmissionAssessmentAccepted
LegacyExposureReconstructionAssessmentAccepted
LegacyObservationSemanticEquivalenceAssessmentAccepted
LegacyObservationMappingAssessmentAccepted
BootstrapAdmissionAccepted
CompatibilityFixtureAssessmentAccepted
CompatibilityGateResultAccepted
```

`ArtifactAccepted` i `GateEvaluated` są **generic event envelopes**, nie osobnymi canonical object kinds. `ArtifactAccepted` niesie typed `artifact_ref` do registered kind/raw artifact contract; `GateEvaluated` niesie typed target/result ref do właściwego registered decision/assessment (np. `validation_result` lub `approval_decision`). Nie wolno interpretować nazwy eventu jako ukrytego drugiego schema kind.

Każdy event/fact ma exact input refs i governing policy/spec revisions. Event order wynika z accepted commit sequence, nie wall-clock timestampów.

Retry tego samego `command_id` + samego command digest zwraca ten sam receipt. Ten sam ID z innym digestem = `ID_REUSE_CONFLICT`.

---

# 17. Checkpoint base contract

Checkpoint jest immutable precursor record wiążącym exact HistoryCut i exact outputs przed dalszym reveal/transition.

Minimalnie:

```text
checkpoint_id
checkpoint_family
campaign_id
stage_run_ref
lane_run_ref optional
attempt_ref
source_generation_ref
checkpoint_input_history_cut
knowledge_state_ref
sealed_output_refs[]
governing_policy_ref
```

Checkpoint nie jest snapshotem całego mutable state i nie tworzy własnego head. Jego `ObjectDigest` i accepting commit provenance istnieją wyłącznie w zewnętrznym revision envelope/history event, nie w checkpoint body.

---

# 18. F1 checkpoint

Legacy F1 jest specjalnym `checkpoint_family=LEGACY_F1` walidowanym według pinned legacy contract. Native-v2 StageSpec może używać innych checkpoint families.

W current v2 reference do legacy F1 zawiera raw legacy ref, mechanical validation assessment, SourceReconciliationAssessment i exact legacy run/attempt bindings. Nie tworzy substitute F1.

---

# 19. F2 checkpoint

Analogicznie legacy F2 jest `checkpoint_family=LEGACY_F2`.

Oryginalny F2/handoff bytes pozostają authority historycznego checkpointu. Rekonstrukcja z final reportu lub narracji jest niedozwolona jako canonical F2.

Native v2 reveal gate może wymagać sealed checkpointu bez nazywania go F2, jeżeli StageSpec tak definiuje.

---

# 20. Snapshot digest record

Snapshot/digest record jest wyłącznie materializacją lub historycznym legacy artifactem.

Native snapshot MUSI zawierać:

Canonical `SNAPSHOT_EXPORT_RECORD` opisuje osobny raw snapshot artifact:

```text
snapshot_type
as_of_head
projection_code_revision
projection_input_refs
snapshot_artifact_ref   # RawRef; digest należy do external artifact envelope
```

Raw snapshot bytes nie zawierają własnego `RawDigest`. Usunięcie snapshotu nie może uniemożliwić odtworzenia current state z canonical history + immutable objects. Snapshot nie jest alternatywnym head.

---

# 21. Stage status

`STAGE_STATUS` jest projekcją aggregate FSM na exact HistoryCut.

Authority stanowią accepted transition facts i StageSpec revision.

Projection powinna zawierać:

```text
stage_run_ref
as_of_head
state
blocking_refs[]
required_slot_summary
stage_completion_ref optional
projection_revision
```

Nie wolno przyjmować gate na podstawie stale `STAGE_STATUS` bez porównania `as_of_head` z wymaganym cut.

---

# 22. Knowledge Exposure Ledger

`KNOWLEDGE_EXPOSURE_LEDGER.jsonl` może istnieć jako czytelny derived export. Authority stanowią accepted facts:

```text
GrantAccepted
PotentialExposureRecorded
DeliveryObserved optional
ContaminationAssessmentAccepted
IsolationQualificationAccepted
```

Minimalny **derived event-enriched exposure view** wiąże accepted `POTENTIAL_EXPOSURE_RECORD` z event position. Poniższy blok nie jest alternatywnym canonical body; `delivery_profile_ref` jest deterministycznie dereferencjonowany z accepted grant/delivery context, a `potential_exposure_effective_at` pochodzi z zewnętrznej accepted event position:

```text
exposure_ref
attempt_ref
grant_ref
channel_class
view_manifest_ref
exposure_input_history_cut
potential_exposure_effective_at = EXTERNAL_ACCEPTED_EVENT_POSITION
delivery_profile_ref
forbidden_knowledge_match optional
```

Brak ACK nie usuwa `PotentialExposure`. `potential_exposure_effective_at` nie jest body-carried head/hash; jego canonical wartość `EXTERNAL_ACCEPTED_EVENT_POSITION` oznacza, że exact effective order pochodzi z zewnętrznego `(accepting_commit_hash, ordinal)` eventu. Grant i PotentialExposure muszą być zaakceptowane w policy-defined order; object body nie może przewidzieć własnego accepting head.

Ledger nie twierdzi, że zna psychologiczny stan wiedzy executora; opisuje kontrolowane i potencjalne kanały.

### 22.1. ContaminationAssessment

Canonical `CONTAMINATION_ASSESSMENT`:

```text
contamination_assessment_id
attempt_ref
assessment_input_history_cut
forbidden_knowledge_policy_ref
channel_inventory_ref
potential_exposure_refs[]
forbidden_knowledge_match_refs[]
observation_or_channel_evidence_refs[]
result = CLEAN | CONTAMINATED | UNKNOWN | NOT_APPLICABLE
scope
limitations[]
reason_codes[]
```

`CLEAN` jest dozwolone tylko w granicach jawnie ocenionych kanałów/scope. Brak obserwacji forbidden content nie zmienia niekwalifikowanego kanału w `CLEAN`; niepełny channel inventory lub nieweryfikowalny capture daje `UNKNOWN`.

### 22.2. IsolationQualification

Canonical `ISOLATION_QUALIFICATION`:

```text
isolation_qualification_id
attempt_ref
assessment_input_history_cut
executor_profile_ref
delivery_profile_ref
channel_inventory_ref
enforcement_receipt_refs[]
filesystem_boundary_evidence_refs[]
network_boundary_evidence_refs[]
tool_boundary_evidence_refs[]
session_boundary_evidence_refs[]
contamination_assessment_refs[]
required_isolation_assurance
result = ENFORCED | DECLARED | UNKNOWN
scope
limitations[]
reason_codes[]
```

`ENFORCED` wymaga pozytywnej kwalifikacji wszystkich kanałów wymaganych przez pinned Executor/Lane policy. `DECLARED` oznacza udokumentowaną deklarację/configuration bez kompletnego enforcement proof. `UNKNOWN` obejmuje brakujące lub nieweryfikowalne kanały. `CONTAMINATED` pozostaje wynikiem osobnego `CONTAMINATION_ASSESSMENT`, nigdy czwartym poziomem isolation.

---

# 23. Knowledge State snapshot

Knowledge State jest **immutable canonical object revision**, attempt-bound i zaakceptowaną/referencjonowaną w canonical history. UI/read-model może ją deterministycznie projektować, ale `DiscoveryRecorded.knowledge_state_ref` nigdy nie wskazuje ephemeral recalculated view:

```text
knowledge_state_id
knowledge_state_revision
attempt_ref
previous_knowledge_state_ref optional
basis_history_cut
allowed_view_refs[]
potential_exposure_refs[]
contamination_assessment_refs[]
isolation_qualification_ref
```

Isolation assurance:

```text
ENFORCED
DECLARED
UNKNOWN
```

`CONTAMINATED` jest osobnym assessmentem dotyczącym forbidden exposure, nie czwartym poziomem izolacji.

`ENFORCED` wymaga evidence o rzeczywistym runner/session/fs/tool/network boundary zgodnie z ExecutorProfile. Brak takiej kwalifikacji oznacza DECLARED/UNKNOWN, nigdy tymczasowe ENFORCED.

---

# 24. Corpus manifest

CorpusManifest/Snapshot jest immutable zbiorem exact member revisions na exact current admission cut.

```text
corpus_id
corpus_revision
corpus_role
consumer_stage_run_ref
source_generation_ref
member_refs[]
member_admission_assessment_refs[]
exposure_class
ordering_semantics
basis_history_cut
```

Zmiana membera lub current admissibility tworzy nową revision. Corpus nie staje się alternatywną canonical lineage.

---

# 25. Corpus types

Normatywne role corpus obejmują co najmniej:

```text
CANONICAL_DIRECT_PREDECESSOR
AUXILIARY_SAME_STAGE
CUMULATIVE_HISTORY
CLAIM_QUARANTINE_VIEW
EXTERNAL_HOLDOUT
CALIBRATION
INFORMATIONAL
```

Role są rozłączne semantycznie. Holdout po ujawnieniu jest `CONSUMED` dla danego evaluator/profile i nie może wrócić do stanu unseen.

---

# 26. Corpus member contract

Immutable `CORPUS_MEMBER_CANDIDATE` opisuje przedmiot możliwego membership, ale **nie referencjonuje własnej późniejszej admission decision**:

```text
member_candidate_id
raw_or_object_revision_ref
producer_stage_ref optional
producer_lane_ref optional
source_generation_ref
mechanical_validation_assessment_ref optional
source_reconciliation_assessment_ref optional
historical_role
```

Consumer/role-specific admission jest osobnym canonical assessmentem:

```text
CORPUS_MEMBER_ADMISSION_ASSESSMENT:
  admission_assessment_id
  member_candidate_ref
  requested_corpus_role
  consumer_stage_run_ref
  consumer_knowledge_policy_ref
  input_history_cut
  exposure_or_knowledge_assessment_refs[]
  additional_admission_evidence_refs[]
  result = ADMITTED | ADMITTED_WITH_LIMIT | REJECTED | BLOCKED
  limitations[]
  reason_codes[]
```

`CorpusManifest.member_refs[]` wskazuje member candidates, a `member_admission_assessment_refs[]` exact assessments dla tej manifest revision. Assessment wskazuje candidate jednostronnie; candidate nie wskazuje assessmentu, więc graph pozostaje acykliczny. Membership nie przenosi automatycznie truth, evidence independence, coverage depth ani blind-origin statusu.

---

# 27. Claim quarantine

Claim Quarantine jest positive-view contract.

`QUARANTINED_CLAIM_VIEW` zawiera wyłącznie pola jawnie dozwolone przez `ProjectionPolicy`:

```text
view_id
projection_policy_ref
claim_view_items[]
resolver_capability_set
source_corpus_snapshot_ref
view_artifact_ref   # RawRef do dokładnie dostarczanych view bytes
```

Policy musi jawnie kontrolować m.in. filenames, hashes, producer/lane identity, severity, support count, prior corpus labels i resolvable evidence refs.

Raw view bytes nie zawierają własnego digestu; `view_artifact_ref` jest zewnętrznym RawRef/envelope. `ViewRef` nie może być użyty jako raw locator poza capability brokerem. Transitive resolver closure jest częścią walidacji view. Niedozwolony reachable artifact = `VIEW_REJECTED`; jeśli delivery mogło już nastąpić, zapisuje się PotentialExposure i contamination assessment.

---

# 28. Audit Surface Inventory

`AUDIT_SURFACE_INVENTORY` jest immutable revision i nie udaje kompletności collectora.

Minimalnie:

```text
inventory_id
inventory_revision
source_generation_ref
collector_profile_refs[]
assigned_input_refs[]
input_disposition_refs[]
surface_refs[]
scope_state_record_refs[]
manual_runtime_additions[]
unresolved_scope_refs[]
basis_history_cut
```

Dwa odrębne enumy są normatywne.

`InputDisposition` — rozlicza każdy assigned input:

```text
COLLECTED
UNSUPPORTED
EXCLUDED
COLLECTION_FAILED
PARSING_FAILED
PROVISIONAL
```

`PROVISIONAL` jest dozwolone wyłącznie w pośredniej inventory revision i **nie jest terminalnym rozliczeniem** AF-INV-1. StageCompletion/STOP wymagający complete input accounting nie może przejść, dopóki assigned input pozostaje `PROVISIONAL`. `UNSUPPORTED` i `EXCLUDED` są wynikami obsługi inputu; odpowiadający im wpływ na denominator jest zapisany osobno jako `UNSUPPORTED_SCOPE` / `EXCLUDED_SCOPE`.

`ScopeState` — opisuje denominator/current scope model i jest odrębną typed domain od `InputDisposition`:

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

`PROVISIONAL_SCOPE` oznacza pośredni, jeszcze nieustabilizowany wpis denominatora/scope modelu; nie jest aliasem `InputDisposition.PROVISIONAL`, nie może być zapisany w polu `input_disposition` i nie spełnia żadnego terminalnego scope/accounting gate. `UNKNOWN_SCOPE` reprezentuje materialnie nierozliczony obszar bez znanego kompletnego input mappingu. `EXCLUDED_SCOPE` wymaga accepted scope decision. Żaden FAILED/UNSUPPORTED/UNKNOWN/N/A stan nie jest coverage PASS.

Per-input i per-scope accounting są oddzielnymi immutable supporting facts, a nie alternatywnym current inventory authority:

```text
InputDispositionRecord:
  input_disposition_record_id
  assigned_input_ref
  disposition = COLLECTED | UNSUPPORTED | EXCLUDED | COLLECTION_FAILED | PARSING_FAILED | PROVISIONAL
  disposition_input_history_cut
  reason_codes[]

ScopeStateRecord:
  scope_state_record_id
  scope_key
  scope_ref optional
  state = KNOWN_SURFACE | KNOWN_UNOBSERVED_SCOPE | UNSUPPORTED_SCOPE | EXCLUDED_SCOPE | COLLECTION_FAILED | PARSING_FAILED | PROVISIONAL_SCOPE | UNKNOWN_SCOPE
  basis_refs[]
  scope_decision_ref optional-by-state
  scope_state_input_history_cut
  reason_codes[]
```

`InventoryRevision.input_disposition_refs[]` wskazuje wyłącznie exact `InputDispositionRecord`, a `scope_state_record_refs[]` wyłącznie exact `ScopeStateRecord`; nie istnieje wspólna target class pozwalająca zamienić assigned input, disposition i scope-state. Każdy `InputDispositionRecord.assigned_input_ref` MUSI należeć do `InventoryRevision.assigned_input_refs[]`; terminal-completeness validator wymaga dokładnie jednego current disposition record dla każdego assigned input. `ScopeStateRecord.scope_key` jest stabilnym kluczem denominatora; jeśli `scope_ref` istnieje, musi być z nim zgodny. `EXCLUDED_SCOPE` wymaga accepted `scope_decision_ref`; inne stany nie mogą używać decision ref jako sposobu obejścia evidence/accounting. Oba recordy wiążą prior `HistoryCut` i same nie ustanawiają „current inventory” bez wskazującej je accepted `InventoryRevision`.

`input_disposition_refs[]` i `scope_state_record_refs[]` są canonical sorted exact-ref sets z duplicate rejection. Dzięki temu jedna semantyczna InventoryRevision nie ma kilku ObjectDigestów wynikających z kolejności collectora.

Późno odkryty materialny subsystem tworzy nową inventory revision i może unieważnić wcześniejsze stage/STOP conclusions zależne od starego cut.

---

# 29. Surface categories

Surface category jest klasyfikacją pomocniczą, nie identity. Przykładowe categories:

```text
HTTP_ROUTE
STATE_MUTATION
NETWORK_EGRESS
PARSER
FILE_IO
PERSISTENCE
CACHE
SUBPROCESS
CONCURRENCY
TIMER_RETRY_WORKER
AUTHORITY
SECRET_CONFIG
DOM_SINK
EXTERNAL_CONTENT
CI_SUPPLY_CHAIN
TEST_ORACLE
ARTIFACT_PRODUCER
OTHER
```

Unknown category nie pozwala pominąć surface; używa się `OTHER` + jawnego description.

---

# 30. Surface collector record

Każdy collector posiada `CollectionRun`:

```text
collection_run_id
collector_profile_ref
assigned_input_manifest_ref
assigned_inputs[]
terminal_input_dispositions[]
emitted_surface_refs[]
runtime_manual_additions[]
parse_errors[]
unsupported_capabilities[]
resource_limit_events[]
completion_status
```

Każdy assigned input MUSI mieć terminal disposition. Exit code 0 lub „90 surfaces found” nie jest dowodem completeness.

Collector capability profile określa wspierane language/framework/input classes. Nieobsługiwany framework nie może zostać automatycznie przeklasyfikowany na `EXCLUDED_SCOPE` w celu podniesienia coverage.

Canonical `MATERIALITY_ASSESSMENT` dla surface/invariant/scope decision:

```text
materiality_assessment_id
subject_ref
assessment_input_history_cut
materiality_policy_ref
scope
supporting_fact_refs[]
result = MATERIAL | NON_MATERIAL | UNKNOWN | CONFLICTED
rationale
reason_codes[]
```

`UNKNOWN`/`CONFLICTED` nie mogą zostać potraktowane jak `NON_MATERIAL`. Zmiana materiality wymaga nowej assessment revision i nie przepisuje historycznego denominatora.

---

# 31. Invariant Registry

Invariant Registry przechowuje immutable invariant revisions:

```text
invariant_id
invariant_revision
invariant_input_history_cut
source_generation_ref
statement
target_scope_refs[]
category
origin
activation_policy_ref
status
```

`InvariantRevision` nie wskazuje późniejszego `MaterialityAssessment`. Jeżeli materiality dotyczy exact invariant revision, najpierw akceptowana jest invariant revision, następnie `MATERIALITY_ASSESSMENT.subject_ref` wskazuje tę revision. CoverageObligation, która opiera denominator na materialności invariant, wskazuje exact `materiality_assessment_ref`. `invariant_input_history_cut` wiąże `activation_policy_ref` z policy obowiązującą przed accepting commit; policy nie może aktywować samej siebie w tym samym commicie.

Status:

```text
ACTIVE
SUPERSEDED
RETIRED
INVALIDATED
```

Invariant nie zawiera globalnego `REQUIRED_EVIDENCE_DEPTH` jako authority. Konkretne wymagania testowe są reprezentowane przez Coverage Obligations.

---

# 32. Invariant categories

Kategorie invariantów są otwartą klasyfikacją policy, np.:

```text
AUTHORITY
DURABILITY
ATOMICITY
CONSISTENCY
COMPLETENESS
PARSING
RECOVERY
CONCURRENCY
RESOURCE_OWNERSHIP
SECURITY_BOUNDARY
PRIVACY
SUPPLY_CHAIN
RELEASE_ASSURANCE
```

Category nie zmienia statement ani scope exact invariant revision.

---

# 33. Traceability edges

Traceability Graph jest derived view accepted typed relations.

Przykładowe relation facts:

```text
SURFACE_IN_SCOPE_OF_INVARIANT
INVARIANT_REQUIRES_OBLIGATION
DISCOVERY_PROPOSES_HYPOTHESIS
HYPOTHESIS_TESTED_BY_EXPERIMENT
EXPERIMENT_PRODUCES_OBSERVATION
OBSERVATION_DEPENDS_ON
EVIDENCE_QUALIFIES_CLAIM
FINDING_VIOLATES_INVARIANT
ROOT_CAUSE_MEMBERSHIP
CONTRADICTION_APPLIES_TO_SCOPE
```

Graph traversal nie może tworzyć nowych semantic edges przez similarity. Każda materialna relacja ma accepted provenance albo jest deterministycznie derived z zaakceptowanych typed refs.

---

# 34. Coverage Ledger

`COVERAGE_LEDGER.jsonl` jest derived exportem. Authority coverage stanowią **Coverage Obligation revisions** i odrębne qualification/applicability/waiver decisions.

Stable target identity używa `CoverageObligationKey`:

```text
CoverageObligationKey = ObjectDigest("coverage_obligation_key", 1, {
  source_generation_ref,
  target_scope_or_surface_ref,
  invariant_logical_id,
  scenario_class,
  environment_profile_ref,
  policy_obligation_key
})
```

Exact wire kind `coverage_obligation_key` jest zarejestrowany w ArtifactContractRegistry; alias lub niezarejestrowany digest-domain kind jest niedozwolony.

Zmiana któregoś elementu target tuple tworzy nowy key/obligation z jawnym backward lineage relation; zmiana predicate/required qualification przy tym samym target key tworzy nową obligation revision. `obligation_id` jest logical handle powiązanym one-to-one z key w danym campaign namespace, nie arbitralnym sposobem zmiany denominatora.

`COVERAGE_OBLIGATION`:

```text
obligation_id
obligation_revision
obligation_input_history_cut
source_generation_ref
target_scope_or_surface_ref
invariant_revision_ref
scenario_class
environment_profile_ref
materiality_assessment_ref
required_technique_or_capability_refs[]
required_oracle_independence_predicate_ref
acceptance_predicate_ref
falsifier_or_control_requirements[]
applicability_predicate_ref
policy_obligation_key
governing_policy_ref
origin_ref
```

`obligation_input_history_cut` jest exact history inputem dla governing policy/profile/predicate bindings tej obligation revision. Same-commit content może dostarczyć earlier target/invariant refs zgodnie z canonical content DAG, ale policy/spec/profile semantics nie mogą zostać ustanowione przez ten sam commit, który tworzy obligation.
`materiality_assessment_ref` MUSI wskazywać exact, już accepted `MATERIALITY_ASSESSMENT` dla `invariant_revision_ref` albo target scope/surface, którego `result=MATERIAL` (chyba że pinned policy jawnie dopuszcza inną materiality class). Assessment nie jest kopiowany jako scalar `materiality` w obligation body; exact ref jest jedynym authority dla tej decyzji i eliminuje second representation.

`COVERAGE_OBLIGATION_QUALIFICATION` rozdziela **wykonanie/kwalifikację** od **substantive outcome**:

```text
qualification_id
obligation_revision_ref
input_history_cut
qualification_status
substantive_outcome optional
evidence_qualification_refs[]
applicability_decision_ref optional
waiver_decision_ref optional
contradiction_refs[]
reason_codes[]
```

Normatywne `qualification_status`:

```text
UNASSESSED
IN_PROGRESS
QUALIFIED
BLOCKED
STALE
```

Normatywne `substantive_outcome` (tylko gdy semantycznie dostępne):

```text
NO_VIOLATION_OBSERVED
VIOLATION_CONFIRMED
INCONCLUSIVE
```

`NOT_APPLICABLE` jest osobną accepted applicability decision; `WAIVED` osobną residual-risk/waiver decision; unresolved contradiction jest referencją/blocking condition, nie trzecią odmianą execution statusu.

Canonical `OBLIGATION_APPLICABILITY_DECISION`:

```text
applicability_decision_id
obligation_revision_ref
assessment_input_history_cut
applicability_policy_ref
scope
supporting_evidence_refs[]
result = APPLICABLE | NOT_APPLICABLE | UNKNOWN | CONFLICTED
reason_codes[]
```

Canonical waiver dla obligation jest `APPROVAL_DECISION` z:

```text
decision_type = COVERAGE_OBLIGATION_WAIVER
related_refs[] zawiera exact obligation_revision_ref
decision = APPROVED | REJECTED
```

Tylko `APPROVED` waiver może być wskazany przez `waiver_decision_ref`; nadal **nie spełnia** pierwotnego obowiązku ani nie zmienia go na N/A. `applicability_decision_ref` musi wskazywać exact `OBLIGATION_APPLICABILITY_DECISION`; generic ApprovalDecision nie może zastąpić applicability assessment.

**Kwalifikowany test może potwierdzić defekt i jednocześnie spełnić investigation obligation.** Dlatego `VIOLATION_CONFIRMED` nie oznacza qualification failure. `INCONCLUSIVE` nie spełnia requirement wymagającego decisive outcome.

Zmiana acceptance/applicability/required qualification predicate = nowa obligation revision. Zmiana target tuple tworzy nowy obligation z jawnym lineage.

---

# 35. Coverage depth enum

D0–D5 jest **derived presentation**, nie authority.

```text
D0 = brak kwalifikowanych obligations wykonawczych
D1 = kwalifikowane static obligations
D2 = kwalifikowane dynamic happy/negative obligations
D3 = kwalifikowane failure/fault obligations
D4 = kwalifikowane stateful/temporal/concurrency/adversarial obligations
D5 = wymagane compositional/mutation/replay obligations
```

Derived D dla surface/scopu może osiągnąć poziom tylko wtedy, gdy **wszystkie mandatory obligations wymagane przez pinned policy dla tego poziomu i scope** są odpowiednio qualified. Jeden test concurrency nie podnosi całej surface do D4.

`WAIVED`, `N/A`, `BLOCKED`, stale/invalidated support i nieaktywowana mutation nie podnoszą D.

---

# 36. Breadth summary

Coverage summary jest derived `as_of_head`:

```text
inventory_revision_ref
obligation_set_revision
mandatory_count
qualified_count
qualified_no_violation_observed_count
qualified_substantive_violation_count
qualified_inconclusive_count
blocked_count
stale_count
waived_count
not_applicable_count
known_unobserved_scope_count
unsupported_scope_count
unknown_scope_count
derived_depth_distribution
```

`qualified_*_count` jest breakdownem `qualification_status=QUALIFIED` po `substantive_outcome`; `VIOLATION_CONFIRMED` nadal liczy się do `qualified_count`, choć może blokować release policy. Breadth denominator jest jawnie związany z **known inventory + applicable mandatory obligations**, a unresolved/unsupported/unknown scope jest raportowany osobno. Nie wolno prezentować jednego procentu bez tych denominators.

Dzielenie jednego surface na wiele rekordów nie może zwiększyć weighted breadth; policy używa stabilnych scope/obligation keys.

---

# 37. Gap Map

Gap Map jest derived planning view z current inventory/obligations/evidence:

```text
gap_id
target_scope_ref
missing_or_unsatisfied_obligation_refs[]
unknown_scope_refs[]
materiality
priority_basis
current_history_cut
```

Gap Map nie może ręcznie nadpisać statusu obligation ani STOP.

---

# 38. Priority score record

Priority score jest wyłącznie scheduling heuristic.

Pola:

```text
target_scope_ref
risk_attributes
unsatisfied_obligation_refs[]
unknown_scope_penalty
historical_defect_density_optional
exploration_bonus
formula_profile_ref
derived_value
```

Split/merge powierzchni nie może sam zwiększać sumy risk weight. Exact weights i exploration ratio należą do pinned policy profile, nie do globalnego invariant BDB.

---

# 39. Hypothesis Ledger

Hypothesis jest immutable revision i nie jest findingiem.

```text
hypothesis_id
hypothesis_revision
source_generation_ref
statement
scope_refs[]
invariant_refs[]
obligation_refs[]
origin_discovery_ref optional
planning_mode
status
input_history_cut
```

Status:

```text
PROPOSED
PREREGISTERED
TESTING
CONFIRMED
REJECTED
UNRESOLVED
BLOCKED
```

Rejected hypotheses pozostają w canonical history. Zmiana statement/scope tworzy nową revision.

---

# 40. Hypothesis status

Status hypothesis nie koduje evidence independence ani finding truth. `CONFIRMED` oznacza jedynie, że hypothesis resolution została zaakceptowana według pinned policy i exact evidence refs; final finding assessment pozostaje osobnym kontraktem.

`PREREGISTERED` może zostać nadany tylko specowi zaakceptowanemu przed execution. Legacy/exploratory run nie może dostać go retroaktywnie.

---

# 41. ExperimentSpec

ExperimentSpec jest immutable revision zaakceptowaną przed materialnym execution, chyba że `planning_mode=EXPLORATORY`.

```text
experiment_id
experiment_revision
hypothesis_revision_ref
invariant_revision_ref
coverage_obligation_refs[]
subject_baseline_ref
target_execution_variant_ref
environment_profile_ref
dependency_set_ref
harness_ref
fixture_refs[]
trigger
expected_safe_behavior
expected_buggy_behavior
observation_path_requirements[]
falsification_condition
positive_controls[]
negative_controls[]
fault_ref optional
seed_profile
cleanup_spec
planning_mode
preregistration_input_history_cut optional
```

Dla fuzz/property campaigns prerejestruje się generator/oracle/bounds, nie każdy generated input.

---

# 42. Experiment type

Experiment type jest klasyfikacją metod, np.:

```text
STATIC_ANALYSIS
DYNAMIC
FAULT_INJECTION
FUZZ
PROPERTY
DIFFERENTIAL
METAMORPHIC
STATEFUL
CONCURRENCY
ENDURANCE
IMPLEMENTATION_MUTATION
ORACLE_CHALLENGE
MODEL_CONFORMANCE
REPLAY
```

Method type nie jest evidence strength ani independence level.

---

# 43. ExecutionDescriptor + ExperimentResult

Execution lifecycle rozdziela intent od resultu. Przed execution istnieje immutable `EXECUTION_DESCRIPTOR`:

```text
execution_descriptor_id
experiment_revision_ref
subject_baseline_ref
target_variant_ref
environment_ref
dependency_set_ref
harness_ref
fixture_refs[]
runner_profile_ref
execution_input_history_cut
```

Runtime records (`Observation`, `FaultRunRecord`, cleanup/reset) wskazują ten wcześniejszy descriptor. Po nich powstaje `EXECUTION_RESULT`:

```text
execution_result_id
execution_descriptor_ref
started_observation_ref
finished_observation_ref
real_exit_code
fault_activation_record_ref optional
raw_observation_refs[]
control_result_refs[]
cleanup_result_ref
reset_verification_ref optional
execution_status
```

`started_at/finished_at` pozostają informational w raw observations i nie ustanawiają history ordering. `ExecutionResult` wskazuje activation/cleanup/observations jednostronnie; żaden z tych records nie wskazuje future `ExecutionResult`. Result zostaje użyty dopiero po accepted observation/evidence qualification.

Execution status:

```text
EXECUTED
INCOMPLETE
BLOCKED
HARNESS_FAILURE
RESOURCE_BLOCKED
```

---

# 44. Fault Registry

Fault Registry przechowuje immutable FaultSpec revisions:

```text
fault_id
fault_revision
fault_class
injection_point
activation_predicate
expected_observable
safety_constraints
cleanup_spec
```

Fault injection bez dowodu activation nie spełnia obligation wymagającego danego fault class.

---

# 45. Fault Run Record

FaultRunRecord wiąże exact wcześniejszy execution intent i activation:

```text
fault_revision_ref
execution_descriptor_ref
activation_status
activation_evidence_refs[]
scope
cleanup_result_ref
```

`execution_descriptor_ref` nie może wskazywać `ExecutionResult`. `ExecutionResult.fault_activation_record_ref` może wskazać ten record, dzięki czemu graph pozostaje `ExecutionDescriptor → FaultRunRecord → ExecutionResult`, bez cycle.

Status:

```text
ACTIVATED
NOT_ACTIVATED
PARTIALLY_ACTIVATED
BLOCKED
HARNESS_FAILURE
```

---

# 46. Evidence Record

Evidence jest kwalifikowanym wsparciem **konkretnego claim revision**, nie samym plikiem.

Canonical facts rozdzielają:

1. `Observation` — co zaobserwowano,
2. `ObservationDependency` — od czego zależy ścieżka obserwacji,
3. `EvidenceQualificationAssessment` — jak observation wspiera/refutuje exact claim,
4. `EvidenceApplicabilityAssessment` — czy support jest aktualny dla subject/env/harness/dependencies.

Nazwy `EvidenceQualificationAssessment` / `EvidenceApplicabilityAssessment` są jednocześnie nazwami semantycznych klas oraz podstawą exact wire identity. Exact wire/ObjectDigest kinds są odpowiednio **`evidence_qualification_assessment`** i **`evidence_applicability_assessment`** zgodnie z ArtifactContractRegistry. Krótkie warianty `evidence_qualification` / `evidence_applicability` są historycznymi/starymi aliasami tekstowymi i są **zabronione jako wire/ObjectDigest kinds**.

Normatywny content DAG dla current support jest jednokierunkowy: `Observation/ObservationDependency + EvidenceApplicabilityAssessment + DependencyIndependenceAssessment → EvidenceQualificationAssessment → FindingAxisAssessment → FindingAdjudicationDecision`. `EvidenceQualificationAssessment.applicability_assessment_ref` wskazuje wcześniejszy/prior lub wcześniejszy same-commit `evidence_applicability_assessment`; applicability assessment nie wskazuje future qualification.

Minimalny qualification:

```text
evidence_qualification_id
claim_revision_ref
observation_refs[]
dependency_graph_ref
failure_assumption
independence_assessment_ref
qualification_result = SUPPORTS | REFUTES | INCONCLUSIVE | INVALID
support_scope
applicability_assessment_ref
controls_refs[]
input_history_cut
```

Nie istnieje globalne `independence_level` ważne dla wszystkich claimów. `EvidenceQualificationAssessment` **nie zawiera** Finding M/R/I/Severity assessment refs. Kierunek jest jednokierunkowy: Observation/Dependencies → EvidenceQualification → późniejszy `FindingAxisAssessment`; dzięki temu nie powstaje cykl qualification ↔ adjudication.

Canonical `DEPENDENCY_INDEPENDENCE_ASSESSMENT` wiąże independence z konkretnym claimem i failure assumption:

```text
independence_assessment_id
claim_revision_ref
assessment_input_history_cut
dependency_graph_ref
failure_assumption
observer_path_refs[]
shared_dependency_refs[]
independent_dependency_refs[]
independence_policy_ref
result = INDEPENDENT_FOR_CLAIM | PARTIALLY_INDEPENDENT | SHARED_DEPENDENCY | UNKNOWN | NOT_APPLICABLE
limitations[]
reason_codes[]
```

`EvidenceQualificationAssessment.independence_assessment_ref` oraz `IndependentReplayRecord.dependency_independence_assessment_ref` MUSZĄ wskazywać exact revision tego contractu odpowiednią dla tego samego claim/scope. Świeży executor/process bez analizy dependency graph nie ustanawia `INDEPENDENT_FOR_CLAIM`.

---

# 47. Evidence status

Evidence applicability jest osobną osią:

```text
ACTIVE
SCOPED
STALE
INVALIDATED
BLOCKED
CONFLICTED
```

Assessment wiąże:

```text
applicability_assessment_id
assessment_input_history_cut
previous_assessment_ref optional
status
subject_baseline_ref
execution_variant_ref
environment_ref
harness_ref
fixture_refs[]
dependency_set_ref
claim_revision_ref
validity_scope
reason
```

Zmiana source SHA nie jest jedynym powodem invalidation. Bug harnessu, oracle, fixture, dependency profile lub current claim revision może unieważnić support przy niezmienionym source.

---

# 48. Evidence independence enum

Nie używa się globalnego enumu E0–E3 jako authority independence.

Independence jest assessmentem względem **failure assumption** i może obejmować odrębne dimensions:

```text
PROCESS_INDEPENDENCE
INSTANCE_INDEPENDENCE
IMPLEMENTATION_INDEPENDENCE
STORAGE_READ_PATH_INDEPENDENCE
EXTERNAL_BOUNDARY_INDEPENDENCE
ORACLE_INDEPENDENCE
MODEL_AGENT_INDEPENDENCE
HARNESS_INDEPENDENCE
```

Assessment zapisuje wspólne dependencies i uzasadnia, które materialne common-cause failures są wykluczone, a które pozostają.

Fresh process/fresh instance/external observer nie podnoszą automatycznie evidence strength, jeśli współdzielą krytyczny parser/cache/oracle.

---

# 49. Evidence graph

Evidence Graph jest derived traversal accepted ObservationDependency + EvidenceQualification facts.

Node types mogą obejmować:

```text
OBSERVATION
PROCESS
INSTANCE
IMPLEMENTATION
STORAGE
PARSER
CACHE
HARNESS
FIXTURE
ORACLE
ENVIRONMENT
DEPENDENCY
EXTERNAL_BOUNDARY
```

Edges mają typed relation i exact revision refs. Current support dla claimu jest wyliczany z ACTIVE/SCOPED qualification assessments.

Usunięcie graph exportu nie może zmienić qualification outcome.

---

# 50. Finding Ledger

`FINDING_LEDGER.jsonl` jest derived exportem agregatu Finding. Canonical authority rozdziela **immutable FindingClaimRevision** od późniejszych **FindingAdjudicationDecision**.

Canonical `FINDING_CLAIM_REVISION` jest evidence-free:

```text
finding_id
finding_claim_revision
previous_finding_claim_revision_ref optional
source_generation_ref
claim_statement
scope_refs[]
category
violated_invariant_refs[]
discovery_relation_refs[]
limitations[]
```

Claim revision NIE zawiera severity/M-R-I assessment refs, `evidence_qualification_refs[]`, lifecycle status ani root-cause membership. Te relacje mogą powstać dopiero po utworzeniu claimu i dlatego nie mogą być jego future dependencies.

Current Finding view składa się z claim revision + najnowszej applicable `FindingAdjudicationDecision` + derived RootCause backlinks. Finding nie dziedziczy evidence z root-cause group tylko dlatego, że został z nią połączony.

---

# 51. Finding categories

Finding category jest klasyfikacją impact/domain:

```text
SECURITY
RELIABILITY
DATA_INTEGRITY
AVAILABILITY
PRIVACY
RELEASE_ASSURANCE
EVIDENCE_QUALITY
OTHER
```

Category nie jest severity.

---

# 52. Severity i FindingAxisAssessment

Severity jest osobnym, wersjonowanym canonical assessmentem. Wspólny envelope osi Finding adjudication (`SEVERITY`, `MECHANISM`, `REACHABILITY`, `IMPACT`) to `FINDING_AXIS_ASSESSMENT`:

```text
finding_axis_assessment_id
claim_revision_ref
axis = SEVERITY | MECHANISM | REACHABILITY | IMPACT
assessment_input_history_cut
assessment_policy_ref
scope
evidence_qualification_refs[]
epistemic_outcome optional-by-axis
method_or_characterization_refs[]
severity_value optional-by-axis
confidence = HIGH | MEDIUM | LOW | UNKNOWN
limitations[]
reason_codes[]
```

Dla `axis=SEVERITY` wymagane jest `severity_value = CRITICAL | HIGH | MEDIUM | LOW | INFO`; `epistemic_outcome` nie jest severity.

Dla `axis=MECHANISM|REACHABILITY|IMPACT` wymagane jest wspólne `epistemic_outcome`:

```text
SUPPORTED
REFUTED
INCONCLUSIVE
BLOCKED
NOT_APPLICABLE
```

Metoda/rodzaj dowodu jest oddzielony od wyniku epistemicznego. `SOURCE_REACHABLE`, `CONTROLLED_DYNAMIC`, `LIVE_REACHABLE`, fresh-instance/external-observer itp. są method/characterization facts/refs, **nie** alternatywną domeną truth status. Dzięki temu np. `REACHABILITY.epistemic_outcome=REFUTED` może być wykazane metodą `CONTROLLED_DYNAMIC` bez mapowania REFUTED na UNVERIFIED/BLOCKED.

Zmiana którejkolwiek osi tworzy nowy assessment i późniejszy `FindingAdjudicationDecision`; claim nie wskazuje assessmentu w przyszłość.

# 53. Mechanism epistemic outcome

Mechanism używa wspólnego `SUPPORTED|REFUTED|INCONCLUSIVE|BLOCKED|NOT_APPLICABLE`; mechanizm/trigger/causal-characterization jest oddzielnym typed detail, a nie truth enumem.

---

# 54. Reachability epistemic outcome

Reachability używa wspólnego `SUPPORTED|REFUTED|INCONCLUSIVE|BLOCKED|NOT_APPLICABLE`. Reachability mode/witness (`SOURCE_REACHABLE`, `CONTROLLED_DYNAMIC`, `LIVE_REACHABLE`) jest osobnym method/characterization field/ref.

---

# 55. Impact epistemic outcome

Impact używa wspólnego `SUPPORTED|REFUTED|INCONCLUSIVE|BLOCKED|NOT_APPLICABLE`. Independent observer, fresh instance, restart czy external boundary są atrybutami evidence path, nie impact truth status.

---

# 56. Finding lifecycle status

Normatywny `FindingLifecycle`:

```text
OPEN
CONFIRMED_CURRENT
REJECTED
SUPERSEDED
REMEDIATION_PENDING
STALE_FOR_CURRENT_SOURCE
FIXED_ON_NEW_SOURCE
PARTIALLY_FIXED
REOPENED
```

Lifecycle nie zastępuje Mechanism/Reachability/Impact assessments.

`RequalificationDisposition` jest osobnym wynikiem porównania starego findingu z nową SourceGeneration:

```text
FIXED
STILL_PRESENT
PARTIALLY_FIXED
REGRESSION
BLOCKED
```

Requalification disposition nie jest drugim FindingLifecycle. Accepted disposition może utworzyć successor FindingClaimRevision, jeżeli zmienia się source-bound claim, oraz odpowiedni FindingAdjudicationDecision z lifecycle (`FIXED_ON_NEW_SOURCE`, `PARTIALLY_FIXED`, `REOPENED` itd.) zgodnie z policy.

---

# 57. Finding origin classification

Discovery provenance jest first-class. Zanim późniejszy claim może otrzymać blind-origin label, musi istnieć accepted:

```text
DISCOVERY_RECORDED
```

z:

```text
discovery_id
lane_run_ref
attempt_ref
source_generation_ref
discovery_input_history_cut
knowledge_state_ref
method_ref
producer_ref
surface_location_refs[]
mechanism_candidate
own_observation_refs[]
pre_reveal_checkpoint_ref optional
```

Pre-reveal/blind-origin eligibility NIE jest self-attested booleanem ani polem własnego discovery body. Validator wylicza ją z zewnętrznego event ref `(accepting_commit_hash, ordinal)` dla `DiscoveryRecorded`: ten event musi poprzedzać pierwszy relevant reveal grant/potential exposure względem exact HistoryCut i pinned isolation policy. Discovery body nie może referencjonować przyszłego reveal eventu.

Canonical `BLIND_ORIGIN_ELIGIBILITY_ASSESSMENT` powstaje dopiero na późniejszym cut:

```text
eligibility_assessment_id
discovery_ref
evaluation_input_history_cut
discovery_event_ref
first_relevant_reveal_event_ref optional
isolation_qualification_ref
contamination_assessment_refs[]
forbidden_knowledge_policy_ref
result = ELIGIBLE | INELIGIBLE | UNKNOWN | NOT_APPLICABLE
reason_codes[]
```

Brak reveal może pozostawić `first_relevant_reveal_event_ref` puste; eligibility nadal wymaga kwalifikowanej isolation/contamination oceny. Późniejszy reveal nie mutuje DiscoveryRecord — tworzy nową assessment revision, jeżeli wpływa na klasyfikację.

Później powstają **osobne canonical assessment objects**, a nie pola dopisywane do DiscoveryRecord:

```text
DISCOVERY_CONFIRMATION_ASSESSMENT:
  assessment_id
  discovery_ref
  assessment_input_history_cut
  confirmation_policy_ref
  confirmation_mode
  confirmation_evidence_refs[]
  result
  reason_codes[]

DISCOVERY_CORPUS_MATCH_ASSESSMENT:
  assessment_id
  discovery_ref
  assessment_input_history_cut
  corpus_snapshot_ref
  match_policy_ref
  matched_prior_claim_refs[]
  match_result = MATCH | NO_MATCH | PARTIAL | INCONCLUSIVE
  reason_codes[]

DISCOVERY_NOVELTY_ASSESSMENT:
  assessment_id
  discovery_ref
  assessment_input_history_cut
  corpus_match_assessment_ref
  novelty_policy_ref
  result = NOVEL | PREVIOUSLY_KNOWN | PARTIALLY_NOVEL | INCONCLUSIVE
  reason_codes[]

FALSE_NEGATIVE_RELATIONSHIP_ASSESSMENT:
  assessment_id
  discovery_ref
  assessment_input_history_cut
  predecessor_stage_or_claim_refs[]
  relationship_policy_ref
  result = PREVIOUS_FALSE_NEGATIVE | MULTI_STAGE_FALSE_NEGATIVE | NOT_ESTABLISHED | INCONCLUSIVE
  reason_codes[]

DISCOVERY_TOOL_ORIGIN_ASSESSMENT:
  assessment_id
  discovery_ref
  assessment_input_history_cut
  producer_ref
  method_ref
  tool_profile_ref optional
  result
  reason_codes[]
```

Wszystkie refs są backward-only i wskazują exact accepted revisions/cuts. `FindingClaimRevision.discovery_relation_refs[]` może wskazywać wyłącznie te assessmenty (oraz blind-origin eligibility assessment), nie narracyjne labels.

Derived labels mogą obejmować:

```text
NEW_BLIND_DISCOVERY
PRE_REPORT_REDISCOVERY
REPORT_ASSISTED_VERIFICATION
PREVIOUS_FALSE_NEGATIVE
MULTI_STAGE_FALSE_NEGATIVE
```

ale nie są ręcznie nadpisywaną historyczną wartością.

---

# 58. Root Cause Ledger

Root Cause jest osobnym logical entity z **versioned membership**, nie merged super-finding.

```text
root_cause_id
root_cause_revision
source_generation_ref
mechanism_statement
membership_edges[]
predecessor_root_cause_refs[] optional
multi_causal_condition optional
scope
status
```

Normatywny `RootCauseLifecycle`:

```text
ACTIVE
SUPERSEDED
RETIRED
```

`source_generation_ref` jest obowiązkowym bindingiem RootCauseRevision. `predecessor_root_cause_refs[]`, jeśli obecne, są backward-only/prior-accepted. Membership edge jest structured value `{ finding_claim_revision_ref, relation_role, scope }`, gdzie finding ref jest exact typed ref. `membership_edges[]` ma jedno canonical ordering: rosnąco po tuple `(finding_claim_revision_ref, relation_role, BDB-CJSON-1(scope))`; exact duplicate całego tuple jest odrzucany. Dwa edges z tym samym finding ref są legalne wyłącznie, gdy różnią się relation role lub scope i dokładnie taka wielorelacyjność jest dozwolona przez pinned RootCause policy; w przeciwnym razie validator zwraca `ROOT_CAUSE_MEMBERSHIP_DUPLICATE_OR_AMBIGUOUS`. Kolejność wejściowa collectora/UI nie uczestniczy w semantyce. Merge/split/rename tworzą nowe root-cause revisions. Nowy/merged/split RootCause może wskazywać **wstecz** przez `predecessor_root_cause_refs[]`; predecessor nie wskazuje future successorów. `SUPERSEDED` starego logical RootCause jest accepted status revision, a mapowanie successorów jest wyprowadzane z backward predecessor refs. Split/merge nie kasuje findings. Evidence jednego findingu nie jest automatycznie przypisywane innym memberom.

---

# 59. Contribution Ledger

Contribution Ledger jest derived view z DiscoveryRecorded, MatchAssessment, Confirmation i current qualification.

Może raportować:

```text
UNIQUE_DISCOVERY
REDISCOVERY
SUPPORT
FALSE_POSITIVE
REJECTED_HYPOTHESIS
SOUND_CONTRIBUTION
COVERAGE_EXTENSION
```

`support_count`, `unique_at_time` i leave-one-out są analizami, nie truth authority. Contamination/invalidation może zmienić derived contribution bez przepisywania original DiscoveryRecord.

---

# 60. Contradiction Case

Canonical `CONTRADICTION_REVISION` (Contradiction Case) jest scoped i versioned:

```text
contradiction_id
contradiction_revision
predecessor_contradiction_revision_ref optional
claim_revision_refs[]
scope
positions[]
supporting_evidence_qualification_refs[]
opposing_evidence_qualification_refs[]
failure_assumption_differences[]
environment_input_model_differences[]
required_falsifier
status
resolution_decision_ref optional
```

`resolution_decision_ref` może wystąpić wyłącznie w **successor contradiction revision** i wskazuje już wcześniej zaakceptowany `CONTRADICTION_RESOLUTION_DECISION`. Resolution decision nigdy nie wskazuje future successor revision. Normatywny contract decyzji:

```text
resolution_decision_id
contradiction_prior_revision_ref
resolution_input_history_cut
resolved_scope
resolution_kind = REFUTED | SCOPES_SEPARATED | HARNESS_INVALIDATED | CONTRACT_CHANGED | BLOCKED
basis_refs[]
resulting_status = RESOLVED_SCOPED | RESOLVED_FULL | BLOCKED
```

DAG resolution:

```text
ContradictionRevision(N)
→ ContradictionResolutionDecision(N)
→ ContradictionRevision(N+1, predecessor=N, resolution_decision_ref=decision)
```

Reopen po nowym counterevidence tworzy successor `REOPENED` revision wskazującą predecessor + nowe evidence, bez przepisywania resolution decision. Resolution może dotyczyć tylko części scope.

Majority/support count nie rozstrzyga truth.

---

# 61. Contradiction status

Normatywny `ContradictionLifecycle`:

```text
OPEN
TESTING
RESOLVED_SCOPED
RESOLVED_FULL
REOPENED
BLOCKED
```

Resolution wiąże exact claim revisions i scope. `RESOLVED_SCOPED` nie rozstrzyga pozostałych scopes. Nowe materialne counterevidence tworzy successor `REOPENED` assessment/revision. Majority/support count nie stanowi resolution.

Materialna unresolved contradiction nie może zostać ukryta jako `UNKNOWN=LOW` ani przez zmianę statusu pracy na `TESTING`.

---

# 62. Adjudication Ledger

`ADJUDICATION_LEDGER.jsonl` jest derived exportem accepted adjudication decisions.

Canonical `FINDING_ADJUDICATION_DECISION` wiąże:

```text
decision_id
claim_revision_ref
previous_adjudication_decision_ref optional
scope
mechanism_assessment_ref
reachability_assessment_ref
impact_assessment_ref
severity_assessment_ref
finding_lifecycle_status
evidence_qualification_refs[]
knowledge_state_refs[]
corpus_snapshot_refs[]
adjudicator_ref
input_history_cut
reason_codes[]
```

EvidenceQualification/M-R-I/Severity assessments wskazują istniejący claim albo jego exact scope; claim body nie wskazuje ich z powrotem. `previous_adjudication_decision_ref` tworzy backward-only historię aktualizacji statusu/supportu. Adjudicator identity nie zastępuje evidence. Decision może zostać superseded/reopened przez nową decision revision, bez usuwania historii.

---

# 63. Previous-stage report corpus

Previous-stage corpus jest immutable CorpusSnapshot z rolami:

```text
CANONICAL_DIRECT_PREDECESSOR
AUXILIARY_SAME_STAGE
```

Canonical predecessor jest dokładnie jeden dla lineage, chyba że StageSpec jawnie definiuje inny model. Auxiliary reports nie stają się równoległymi predecessorami.

Każdy member ma current admission assessment.

---

# 64. External Holdout Corpus

External Holdout Corpus posiada lifecycle:

```text
UNSEEN
ASSIGNED
POTENTIALLY_EXPOSED
CONSUMED
RETIRED
```

dla konkretnego evaluator/executor profile. Po potential exposure nie może zostać użyty jako unseen holdout tego samego evaluation path.

---

# 65. Replay Capsule manifest

Replay Capsule jest immutable execution package:

```text
repro_capsule_id
finding_or_claim_revision_ref
subject_baseline_ref
environment_profile_ref
dependency_set_ref
harness_ref
fixture_refs[]
seed_ref optional
generator_profile_ref
command_spec
expected_invariant_ref
expected_observable
observer_requirements[]
cleanup_spec
producer_ref
artifact_raw_digests[]
```

Replayability nie implikuje independence. Capsule może reprodukować ten sam błędny oracle.

---

# 66. Independent Replay Record

Independent Replay Record zapisuje actual execution descriptor i qualification:

```text
repro_capsule_ref
replay_executor_ref
actual_subject_ref
actual_environment_ref
actual_harness_ref
actual_dependencies_ref
observation_refs[]
match_expected
dependency_independence_assessment_ref
status
```

Status:

```text
REPRODUCED
NOT_REPRODUCED
INCONCLUSIVE
BLOCKED
HARNESS_FAILURE
```

`REPRODUCED` nie podnosi automatycznie evidence strength; zależy od claim-relative independence assessment.

---

# 67. Mutation Case

Mutation jest oddzielona na co najmniej dwa kontrakty:

1. **ImplementationMutationCase** — czy detector/test łapie znane naruszenie implementacji.
2. **OracleChallengeCase** — czy osłabienie konkretnego obserwatora powoduje utratę wykrycia aktywowanego known-defective target.

Wspólne pola:

```text
mutation_id
mutation_revision
mutation_class
target_claim_or_invariant_ref
target_location
activation_predicate
expected_detector_or_observer
positive_control_ref
negative_control_ref
clean_target_ref
known_defective_target_ref optional
```

Specification mutation wymaga osobnego policy profile i nie może arbitralnie zmieniać kryterium PASS podczas kampanii.

---

# 68. Mutation Result

Implementation mutation i oracle challenge są dwoma odrębnymi kontraktami.

`ImplementationMutationOutcome`:

```text
MUTANT_KILLED
MUTANT_SURVIVED
MUTATION_NOT_ACTIVATED
INVALID_MUTATION
HARNESS_FAILURE
BLOCKED
```

`OracleChallengeOutcome`:

```text
WEAKENING_DETECTED
REDUNDANT_OBSERVER_FOR_CASE
MUTATION_NOT_ACTIVATED
INVALID_MUTATION
HARNESS_FAILURE
INCONCLUSIVE
BASELINE_ORACLE_MISSED_DEFECT
```

Oracle challenge wymaga activation witness i pełnego kontrastu 2×2:

```text
clean target × strong oracle
clean target × weakened oracle
known-defective target × strong oracle
known-defective target × weakened oracle
```

Interpretacja:

- strong oracle nie wykrywa known defect → `BASELINE_ORACLE_MISSED_DEFECT` (albo `HARNESS_FAILURE`, jeśli problem jest harnessowy),
- weakened oracle przepuszcza known defect przy poprawnym strong oracle i aktywnej mutation → `WEAKENING_DETECTED`,
- weakened oracle nadal wykrywa defect przy potwierdzonej activation i jawnie wskazanej pozostałej ścieżce → `REDUNDANT_OBSERVER_FOR_CASE`,
- brak activation → `MUTATION_NOT_ACTIVATED`,
- clean PASS po osłabieniu oracle nigdy sam nie daje `WEAKENING_DETECTED`.

Critical implementation `MUTANT_SURVIVED` albo niekwalifikowany oracle challenge może pozostawić obligation niespełniony i blokować odpowiedni STOP predicate.

---

# 69. Failure Interaction Graph

Failure Interaction Graph jest derived planning model, nie truth authority.

Nodes: exact failure/fault/root-cause revisions. Edges/hyperedges: accepted interaction hypotheses lub confirmed relations z scope.

Graph nie może automatycznie przenosić severity/evidence między nodes.

---

# 70. Interaction Test Case

Interaction Test Case jest preregistered ExperimentSpec z jawnie wybranym pairwise/N-way failure combination, activation predicates i expected safe/buggy outcome.

N-way coverage jest bounded przez policy/budget; brak wszystkich kombinacji pozostaje residual uncertainty.

---

# 71. State Model

State Model revision musi jawnie wskazywać:

```text
model_revision
implementation_mapping_ref
scope
state_variables
transitions
initial_states
forbidden_states
abstraction_assumptions[]
bounds[]
omitted_states[]
fairness_time_assumptions[]
```

Proof o modelu nie jest proofem implementacji bez osobnego ModelFidelityAssessment.

## 71.1. ModelFidelityAssessment

Canonical `MODEL_FIDELITY_ASSESSMENT` wiąże:

```text
fidelity_assessment_id
model_revision_ref
source_generation_ref
implementation_anchor_refs[]
abstraction_mapping_refs[]
abstraction_assumptions[]
omitted_states[]
bounds[]
fairness_time_assumptions[]
execution_conformance_evidence_refs[]
scope
assessment_input_history_cut
result = QUALIFIED | BOUNDED | INSUFFICIENT | INVALIDATED
reason_codes[]
```

Model proof może wspierać claim implementacyjny tylko w zakresie, w którym current fidelity assessment i required conformance evidence są kwalifikowane.

---

# 72. Temporal Invariant

Temporal Invariant revision wiąże exact StateModel + implementation scope i assumptions.

Status:

```text
PROPOSED
MODEL_VERIFIED
IMPLEMENTATION_CONFORMANCE_QUALIFIED
VIOLATED
BLOCKED
```

`MODEL_VERIFIED` sam nie podnosi implementation coverage obligation wymagającego conformance.

---

# 73. Causal Chain Record

Causal Chain Record wiąże exact steps:

```text
trigger
state_transition_refs[]
observation_refs[]
impact_ref
scope
evidence_qualification_refs[]
```

Łańcuch jest ważny tylko w granicach qualified execution/environment. Similarity do innego chainu nie transferuje proof.

---

# 74. Endurance Record

Endurance Record zawiera exact duration/workload profile, environment, resource baselines, monitoring path, stop/abort reason i observations.

Nominalny czas testu bez wykazanego workload/observer completeness nie kwalifikuje endurance obligation.

---

# 75. Saturation Record

Saturation Record jest derived heuristic i zawsze wskazuje:

```text
stage_run_ref
history_cut
effort_profile_ref
rounds_completed
method_family_coverage
new_root_cause_rate
new_material_finding_rate
coverage_obligation_delta
cross_lane_overlap
fuzz_novelty
mutation_survivors
challenger_yield
unknown_scope_summary
classification
metric_provenance_refs[]
```

Classification:

```text
LOW
MODERATE
STRONG
INSUFFICIENT_DATA
```

Konkretne wymagane liczby rounds/method families należą do pinned `EffortProfile`. Default może istnieć, ale nie jest globalnym invariantem.

Saturation nie dowodzi completeness i nigdy samodzielnie nie daje STOP PASS.

---

# 76. Stop Gate Result

STOP działa na immutable `StopInputSnapshot`/HistoryCut i zwraca cztery odrębne osie C12.

Stop input obejmuje co najmniej:

```text
campaign_id
source_generation_ref
input_history_cut
evaluation_context = INTERMEDIATE | FINAL_POST_E5 | POST_E6
governing_policy_ref
policy_spec_refs[]
evaluator_revision_ref
required_stage_set_ref
required_stage_spec_refs[]
completed_stage_refs[]
pending_required_stage_refs[]
stop_input_snapshot_ref
inventory_revision_ref
mandatory_obligation_refs[]
current_obligation_qualification_refs[]
evidence_invalidation_refs[]
contradiction_refs[]
residual_risk_refs[]
evidence_invalidation_state derived-equality-bound
candidate_assurance_case_ref optional-by-context
challenger_refs[] optional-by-context
challenger_freshness_profile_ref optional-by-context
release_policy_ref
effort_profile_ref
effort_results_ref
continuation_budget_authorization_ref
release_basis_refs[] optional-by-context
unknown_blocked_summary
```

`required_stage_spec_refs[]`, `completed_stage_refs[]` i `pending_required_stage_refs[]` są deterministyczną pochodną pinned stage planu na `input_history_cut`; equality validator odrzuca ręczne ukrycie pending stage. `mandatory_obligation_refs[]` jest canonical sorted set wszystkich mandatory applicable-or-unresolved Coverage Obligation revisions wynikających z pinned policy + exact inventory na tym cut; nie może być zastąpiony derived Coverage Summary. `current_obligation_qualification_refs[]` musi jednoznacznie mapować latest applicable qualification dla każdego referenced obligation albo jawnie wykazać brak qualification. `evidence_invalidation_refs[]` wiąże exact accepted invalidation facts; `evidence_invalidation_state` i `unknown_blocked_summary` są tylko deterministic equality-checked summaries i nie stanowią drugiej authority. `stop_input_snapshot_ref` jest wyłącznie sealed derived reproducibility aid: `Snapshot.as_of_head` MUSI odpowiadać `StopInput.input_history_cut`, a jego projection inputs muszą equality-bind direct StopInput refs; mismatch/stale snapshot jest `STOP_SNAPSHOT_BINDING_CONFLICT`. Snapshot nie zastępuje żadnego direct authority ref. `reason_codes[]` są akumulowane po wyznaczeniu primary `continuation_decision`, a nie przez first-match short-circuit.

`governing_policy_ref`, `policy_spec_refs[]`, `evaluator_revision_ref`, `required_stage_set_ref`, `required_stage_spec_refs[]`, `pending_required_stage_refs[]`, `challenger_freshness_profile_ref`, `release_policy_ref` i `effort_profile_ref` są semantic context bindings względem `input_history_cut`; żaden z nich nie może zostać wprowadzony jako same-commit semantic self-upgrade dla evaluation, którą współdefiniuje.

`StopEvaluation`:

```text
stop_evaluation_id
stop_input_ref
continuation_decision
assurance_level
release_readiness
reason_codes[]
blocking_obligation_refs[]
remaining_obligation_refs[]
```

`stop_input_ref` jest obowiązkowym exact ref do jednego accepted `StopInput`. `blocking_obligation_refs[] ⊆ remaining_obligation_refs[] ⊆ StopInput.mandatory_obligation_refs[]`; każda output obligation musi należeć do exact input set. Dla `PASS` oba output sets są puste. Dla nie-PASS reason/output consistency jest walidowana względem qualification/applicability state z referenced StopInput. `StopEvaluation` NIE kopiuje `input_history_cut`, `release_policy_ref`, evaluator/spec bindings ani stage closure jako drugiej authority reprezentacji; wszystkie inputs są dereferencjonowane przez exact `StopInput`. Dwie różne StopInput revisions na tym samym HistoryCut są różnymi evaluations i nie mogą współdzielić jednego assessmentu bez nowego `StopEvaluation`.

Normatywne enumy:

```text
continuation_decision = PASS | CONTINUE_REQUIRED | E6_REQUIRED | BLOCKED
assurance_level       = ADEQUATE_FOR_DECLARED_SCOPE | BOUNDED | INSUFFICIENT
release_readiness     = READY | READY_WITH_RESIDUAL_RISK | TECHNICALLY_NOT_READY | QUALIFICATION_BLOCKED
```

Context rules są fail-closed:

- `INTERMEDIATE`: używany przed ukończeniem zwykłych wymaganych E1–E5; `candidate_assurance_case_ref` i `challenger_refs[]` mogą być nieobecne. `PASS` i `E6_REQUIRED` są niedozwolone; normalnym wynikiem jest `CONTINUE_REQUIRED`, a authority/admission/resource failure może dać `BLOCKED`.
- `FINAL_POST_E5`: wymaga exact Candidate Assurance Case oraz wymaganych challenger results dla tej candidate revision. Może zwrócić `PASS`, `E6_REQUIRED` albo `BLOCKED`; `CONTINUE_REQUIRED` oznacza wyłącznie wykazany brak zwykłego wymaganego etapu i jest contract violation planu finalization, jeśli policy twierdzi, że E1–E5 są complete.
- `POST_E6`: wymaga aktualnej candidate/challenge closure zgodnej z pinned policy dla zmian po E6. Może zwrócić `PASS`, kolejne `E6_REQUIRED` albo `BLOCKED`.

`StopEvaluation.release_readiness` jest **pure release assessment axis** wyliczonym z exact referenced `StopInput` (w tym jego frozen input cut i pinned release profile); nie jest samo w sobie accepted product release authorization. Canonical `ReleaseQualification` później materializuje ten axis jako odrębną accepted decision i musi spełniać consistency rules z §80.1.

`termination_state = OPEN | COMPLETED | COMPLETED_LIMITED` jest osobną osią **campaign state**, materializowaną dopiero przez accepted `ConcludeCampaign`/`CampaignConclusion`; nie jest polem pure `StopEvaluation`.

Normatywna precedence:

1. authority/source/policy/admission/cut failure → `BLOCKED` + `INSUFFICIENT`,
2. niewykonalny/brak-budżetu material obligation → `BLOCKED`,
3. pending wymagane zwykłe etapy E1–E5 przy wykonalnej pracy → `CONTINUE_REQUIRED` + reason `REQUIRED_STAGES_PENDING`,
4. post-E5 wykonalne material gaps przy zatwierdzonym bounded plan → `E6_REQUIRED` + `BOUNDED`,
5. komplet mandatory applicable obligations + scope/challenge/effort prerequisites → `PASS` + `ADEQUATE_FOR_DECLARED_SCOPE`.

Nieznany wymagany input jest `INSUFFICIENT_DATA` i nie może wpaść do warunku 5 przez default/else. Pending E4/E5 po E3 = `CONTINUE_REQUIRED`, nie E6, i MUSI nieść reason `REQUIRED_STAGES_PENDING`. Jeżeli ten sam STOP ma jednocześnie niekompletny wymagany effort/input, `reason_codes[]` MUSI zawierać oba `REQUIRED_STAGES_PENDING` i `INSUFFICIENT_DATA`, zgodnie z reference F7.

Jeżeli warunek `BLOCKED` wynika z samej niemożności zweryfikowania canonical history/head, evaluator może zwrócić **zewnętrzny diagnostic result**, ale nie wolno udawać, że został on canonicalnie zaakceptowany w historii, której integralności właśnie nie można potwierdzić. `StopEvaluationAccepted` wymaga zweryfikowanego accepting head; po recovery/re-anchor można wykonać i zaakceptować evaluation ponownie.

Release axis jest odrębną osią, ale jej wartości podlegają fail-closed cross-axis consistency: `READY` ani `READY_WITH_RESIDUAL_RISK` NIE są legalne, jeżeli `continuation_decision != PASS` albo `assurance_level != ADEQUATE_FOR_DECLARED_SCOPE`. Zatem `CONTINUE_REQUIRED`, `E6_REQUIRED` i `BLOCKED` zawsze wykluczają oba READY-states. Znany nieakceptowalny defect → `TECHNICALLY_NOT_READY`; brak wystarczającej audit/release qualification lub nie-PASS assurance → `QUALIFICATION_BLOCKED`, chyba że exact release profile wymaga silniejszego `TECHNICALLY_NOT_READY`. `READY_WITH_RESIDUAL_RISK` dodatkowo wymaga, aby każdy materialny residual risk użyty do tej oceny był jawnie zaakceptowany według pinned release policy; brak/unknown acceptance nie może zostać domyślnie podniesiony do READY.

Canonical `ReleaseQualification.result in {READY, READY_WITH_RESIDUAL_RISK}` wymaga ponadto referenced `CampaignConclusion.termination_state=COMPLETED`, referenced `StopEvaluation.continuation_decision=PASS` oraz `assurance_level=ADEQUATE_FOR_DECLARED_SCOPE`. `COMPLETED_LIMITED`, non-PASS STOP albo bounded/insufficient assurance mogą być kwalifikowane tylko jako `TECHNICALLY_NOT_READY` lub `QUALIFICATION_BLOCKED`. Ta reguła nie scala osi C12 — definiuje minimalny consistency predicate zapobiegający false-ready.

---

# 77. Hard condition record

Hard condition nie używa prostego `pass: true/false` bez epistemic state.

```text
condition_id
policy_predicate_ref
required
evaluation_state
actual_refs[]
reason_codes[]
evidence_or_assessment_refs[]
```

`evaluation_state`:

```text
SATISFIED
VIOLATED
UNKNOWN
BLOCKED
INSUFFICIENT_DATA
NOT_APPLICABLE
WAIVED
TESTING_CONTRADICTION
INVALIDATED
```

Policy jawnie definiuje precedence. `UNKNOWN`, `WAIVED` i `NOT_APPLICABLE` nie są automatycznie SATISFIED; N/A/waiver wymagają osobnych accepted decisions.

Material unresolved contradiction, stale mandatory evidence, unknown mandatory scope lub incomplete required stage nie może zostać zinterpretowane jako „brak blockerów”.

---

# 78. Adaptive E6 Spec

Adaptive E6 StageSpec jest generowany wyłącznie z accepted STOP result i dziedziczy:

```text
campaign/source generation
governing policy baseline
trust profile
open mandatory obligations
unknown/blocked conditions
materiality rules
evidence qualification requirements
```

Może zawęzić **obszar dodatkowej pracy**, ale nie może obniżyć obowiązków ani zmienić materiality po to, aby uzyskać PASS.

Po E6 globalny STOP jest liczony ponownie na nowym exact cut.

---

# 79. Residual Risk Register

Residual Risk jest canonical assessment, nie tylko narracyjnym ledgerem.

```text
risk_id
risk_revision
scope
description
materiality
uncertainty_class
reason_unresolved
disposition
blocking_effect
related_obligation_refs[]
related_hypothesis_refs[]
evidence_refs[]
owner_approval_ref optional
```

Disposition:

```text
OPEN
BOUNDED
ACCEPTED_RESIDUAL_RISK
BLOCKED
UNKNOWN
SUPERSEDED
```

Acceptance residual risk nie zmienia evidence ani nie oznacza, że problem nie istnieje.

---

# 80. Campaign conclusion i Final Assurance Case

Finalization jest acykliczna i ma normatywny porządek:

```text
CANDIDATE_ASSURANCE_CASE
→ CHALLENGER_RESULT(s)
→ STOP_EVALUATION
→ CAMPAIGN_CONCLUSION
→ FINAL_ASSURANCE_CASE (public/conclusion envelope)
→ RELEASE_QUALIFICATION
```

Canonical `CANDIDATE_ASSURANCE_CASE` powstaje na exact pre-challenge cut i nie zawiera finalnego STOP/conclusion:

```text
candidate_assurance_case_id
campaign_ref
source_generation_ref
candidate_input_history_cut
scope_inventory_ref
coverage_obligation_refs[]
coverage_obligation_qualification_refs[]
coverage_obligation_summary_ref optional-derived
finding_claim_revision_refs[]
finding_adjudication_refs[]
contradiction_refs[]
evidence_qualification_refs[]
residual_risk_refs[]
assurance_claim_set_ref
```

Candidate nie zawiera challenger results ani przyszłego STOP ref. `coverage_obligation_refs[]` i `coverage_obligation_qualification_refs[]` są authority-bearing bindings; `coverage_obligation_summary_ref`, jeśli obecny, jest wyłącznie derived presentation i MUSI być equality-validated względem tych exact refs oraz `candidate_input_history_cut`. Summary nie może samodzielnie ustanowić coverage assurance.

Canonical `CHALLENGER_ASSIGNMENT` wiąże challengera z exact candidate revision. Candidate MUSI być już accepted na `assignment_input_history_cut`; assignment nie może zostać zaakceptowane atomowo z candidate, który dopiero tworzy:

```text
challenge_assignment_id
candidate_assurance_case_ref
challenger_type = FALSE_POSITIVE_SKEPTIC | FALSE_NEGATIVE_HUNTER | OTHER_POLICY_DEFINED
challenge_scope
challenge_policy_ref
executor_profile_ref
assignment_input_history_cut
forbidden_prior_result_refs[] optional
```

Canonical `CHALLENGER_RESULT` powstaje później i nigdy nie wskazuje future STOP/conclusion. `challenge_assignment_ref` oraz `candidate_assurance_case_ref` MUSZĄ być prior-accepted i widoczne na `result_input_history_cut`; wynik nie może być zaakceptowany w tym samym commicie co assignment, który rzekomo wykonał:

```text
challenger_result_id
challenge_assignment_ref
candidate_assurance_case_ref
result_input_history_cut
challenged_claim_or_scope_refs[]
counterclaim_refs[]
evidence_qualification_refs[]
status = NO_MATERIAL_COUNTEREVIDENCE | MATERIAL_COUNTEREVIDENCE_FOUND | INCONCLUSIVE | BLOCKED
reason_codes[]
```

Assignment/result MUSZĄ wskazywać tę samą exact Candidate revision. Materialne counterevidence nie mutuje candidate ani challenger result: tworzy nowe accepted claims/evidence i nową Candidate revision; w baseline R5.3 obie required challenger roles (skeptic + hunter) są wykonywane ponownie dla nowej exact revision. Scoped reuse wymaga przyszłego, osobno kwalifikowanego profile.

`CAMPAIGN_CONCLUSION` jest immutable accepted decision:

```text
campaign_conclusion_id
campaign_ref
source_generation_ref
candidate_assurance_case_ref optional-by-termination/context
stop_evaluation_ref
termination_state
assurance_level
bounded_conclusion_statement
residual_risk_refs[]
limited_conclusion_basis_refs[] optional-by-termination
conclusion_command_input_history_cut
```

`termination_state` może być `COMPLETED` tylko przy `continuation_decision=PASS`; wtedy `candidate_assurance_case_ref` i wymagane challengers są obowiązkowe. `COMPLETED_LIMITED` jest osobnym uprawnionym zakończeniem bounded/blocked work i nie zmienia STOP na PASS. Jeżeli limited termination następuje przed powstaniem final candidate/challenger closure, `candidate_assurance_case_ref` może być nieobecne, ale `limited_conclusion_basis_refs[]` MUSI wskazać exact StageCompletion/Blocker/ResidualRisk/StopEvaluation refs uzasadniające ograniczony zakres. `CampaignConclusion.assurance_level` MUSI być równe referenced `StopEvaluation.assurance_level`; conclusion nie może podnieść assurance ani zmienić continuation outcome. `CampaignConclusion.source_generation_ref` i `campaign_ref` MUSZĄ odpowiadać exact `StopInput` dereferencjonowanemu przez `stop_evaluation_ref`. Dla `COMPLETED`, `candidate_assurance_case_ref` MUSI być identyczne z `StopInput.candidate_assurance_case_ref`; nie wolno zakończyć kampanii na innym candidate niż ten faktycznie oceniony przez STOP. `conclusion_command_input_history_cut` MUSI już zawierać referenced `StopEvaluation` oraz wszystkie authority/basis refs użyte przez `ConcludeCampaign`; final STOP i conclusion nie mogą zostać sklejone jako same-commit content DAG.

Canonical `FINAL_ASSURANCE_CASE` ma minimalnie:

```text
final_assurance_case_id
campaign_conclusion_ref
candidate_assurance_case_ref optional-for-COMPLETED_LIMITED
challenger_result_refs[] optional-for-COMPLETED_LIMITED
limited_conclusion_basis_refs[] optional-for-COMPLETED_LIMITED
stop_evaluation_ref
residual_risk_refs[]
public_conclusion_statement_ref
final_case_input_history_cut
```

Jest publicznym/conclusion envelope wskazującym exact `CampaignConclusion`, StopEvaluation oraz — dla pełnego `COMPLETED` — candidate i challengers. `final_case_input_history_cut` MUSI już zawierać CampaignConclusion oraz wszystkie authority/basis refs tego envelope; FinalAssuranceCase jest późniejszym immutable envelope, a nie same-commit elementem ConcludeCampaign. `FinalAssuranceCase.stop_evaluation_ref` MUSI równać się `CampaignConclusion.stop_evaluation_ref`; dla pełnego `COMPLETED` jego `candidate_assurance_case_ref` MUSI równać się `CampaignConclusion.candidate_assurance_case_ref`, a challenger refs muszą być dokładnie challenger closure zaakceptowaną przez referenced StopInput/STOP. `residual_risk_refs[]` nie może usuwać materialnego residual risk obecnego w CampaignConclusion; equality/subset policy jest fail-closed zgodnie z finalization profile. Dla `COMPLETED_LIMITED` przed final candidate/challenge closure może zamiast nich wskazywać exact `limited_conclusion_basis_refs[]`; musi jawnie oznaczać bounded/insufficient assurance i nie może prezentować się jako pełny final challenge case. Nie jest wejściem do STOP i nie tworzy cyklu self-reference.

Materialna zmiana claimów/evidence/scope po challengerze wymaga nowej candidate revision oraz, w baseline R5.3, nowych obu required challenger results przed nowym STOP. ReleaseQualification jest późniejszą, odrębną decyzją względem exact SourceGeneration i release policy.

## 80.1. ReleaseQualification

Canonical `RELEASE_QUALIFICATION`:

```text
release_qualification_id
campaign_conclusion_ref
final_assurance_case_ref
stop_evaluation_ref
source_generation_ref
release_policy_ref
release_assessment_basis_cut
qualification_command_input_history_cut
assessment_basis = STOP_AXIS_MATERIALIZATION | FRESH_RELEASE_QUALIFICATION | RELEASE_REASSESSMENT
previous_release_qualification_ref optional-by-basis
release_reassessment_input_refs[] optional-by-basis
result
blocking_finding_or_risk_refs[]
accepted_residual_risk_refs[]
reason_codes[]
```

`result`:

```text
READY
READY_WITH_RESIDUAL_RISK
TECHNICALLY_NOT_READY
QUALIFICATION_BLOCKED
```

Audit `PASS` nie mapuje automatycznie na `READY`. `ReleaseQualification` zawsze wymaga accepted `FinalAssuranceCase` dla wskazanego `CampaignConclusion`. `ReleaseQualification.campaign_conclusion_ref` MUSI równać się `FinalAssuranceCase.campaign_conclusion_ref`, a `stop_evaluation_ref` MUSI równać się zarówno `FinalAssuranceCase.stop_evaluation_ref`, jak i `CampaignConclusion.stop_evaluation_ref`; `source_generation_ref` musi odpowiadać tej samej finalization chain. Mismatch jest `FINALIZATION_BINDING_CONFLICT`. `qualification_command_input_history_cut` MUSI zawierać CampaignConclusion, FinalAssuranceCase i wszystkie refs używane do acceptance tej qualification; wszystkie te authority/basis refs są `PRIOR_ACCEPTED_ONLY` względem qualification command i nie mogą być tworzone w tym samym commicie. `release_assessment_basis_cut` jest również `HISTORY_INPUT`: musi wskazywać prior accepted cut użyty do samej oceny release i nigdy nie może być same-commit content ref. Może być wcześniejszy niż `qualification_command_input_history_cut`, ale nie może zawierać future FinalAssuranceCase.

- `STOP_AXIS_MATERIALIZATION` jest dozwolone tylko wtedy, gdy od `StopEvaluation.stop_input_ref → StopInput.input_history_cut` do qualification command nie zaszła materialna zmiana release inputs/policy; `result` kopiuje `StopEvaluation.release_readiness` i `previous_release_qualification_ref` jest zabronione.
- `FRESH_RELEASE_QUALIFICATION` służy **pierwszej** qualification, gdy po STOP/conclusion zaszła release-specific materialna zmiana, ale current audit assurance basis nadal jest applicable. Nie wymaga fabricated predecessor; `previous_release_qualification_ref` jest zabronione, a wszystkie fresh inputs są exact refs.
- `RELEASE_REASSESSMENT` służy każdej kolejnej qualification i wymaga exact `previous_release_qualification_ref` oraz nowych inputs/policy.

Jeżeli zmiana narusza audit assurance basis (np. invaliduje decisive audit evidence albo ujawnia nowy materialny subsystem), release qualification nie może naprawić assurance: obowiązuje successor campaign z §14.5. Żaden wariant nie może chwilowo materializować znanego stale `READY` w celu stworzenia poprzednika.

---

# 81. Final technical report

Final technical report jest narracyjnym exportem exact machine state.

Musi wskazywać:

```text
campaign_ref
source_generation_ref
final_assurance_case_ref
stop_evaluation_ref
campaign_conclusion_ref
release_qualification_ref optional
report_as_of_head
```

Raw report bytes są osobnym export artifactem. Zewnętrzny `REPORT_EXPORT_RECEIPT` wiąże `report_artifact_ref` (RawRef), `report_as_of_head`, report contract/profile i producer revision; raport nie zawiera własnego `RawDigest`.

Każdy materialny statement musi być możliwy do prześledzenia do exact machine refs. Narracja nie może rozszerzać scope lub confidence.

---

# 82. Final Outcome

`FINAL_OUTCOME.json` jest **derived exportem**, nigdy dodatkowym outcome authority. Dotyczy campaign conclusion, nie każdego StageCompletion.

Minimalnie:

```text
campaign_id
source_generation_ref
campaign_conclusion_ref
stop_evaluation_ref
final_assurance_case_ref
release_qualification_ref optional
export_as_of_head
```

Opcjonalne copied summaries (`bounded_assurance_statement`, residual-risk summary, release label) są wyłącznie deterministycznymi projections wskazanych canonical refs. Nie istnieje osobne pole `technical_audit_outcome`, które mogłoby konkurować z `CampaignConclusion`/`StopEvaluation`.

E1/E2/E3/E4 generują `STAGE_COMPLETION_RECORD`, nie fake final outcome wymagający artefaktów E5.

---

# 83. Artifact Hash Manifest

`ARTIFACT_HASHES.sha256` jest raw export integrity manifestem. Dotyczy exact member bytes i nie zastępuje ObjectDigest/typed refs.

Reguły:

- manifest nie hash-uje sam siebie,
- wpisy są deterministic/sorted według contract profile,
- duplicate paths są niedozwolone,
- expected member set pochodzi z BundleManifest,
- verification wykonuje się przed parsowaniem semantycznym memberów.

---

# 84. Bundle manifest

BundleManifest jest immutable object opisującym exact bundle membership:

```text
bundle_type
bundle_contract_ref
member_paths[]
member_raw_digests[]
source_generation_ref optional
campaign_ref optional
stage_run_ref optional
lane_run_ref optional
export_as_of_head
```

Bundle `RawDigest` jest identity reprezentacji ZIP, nie semantic identity wszystkich contained objects.

---

# 85. Bundle types

Bundle types są versioned artifact contracts, np.:

```text
LEGACY_F1_HANDOFF
LEGACY_F2_HANDOFF
LEGACY_FINAL_RESULT
NATIVE_STAGE_PACKAGE
NATIVE_LANE_PACKAGE
CORPUS_VIEW_PACKAGE
REPLAY_CAPSULE
FINAL_CAMPAIGN_EXPORT
```

Nie należy wymuszać legacy naming na native-v2 stages.

---

# 86. Handoff Validation Result

Handoff Validation Result jest accepted assessment:

```text
handoff_ref
contract_ref
transport_integrity_result
schema_results[]
source_binding_result
run_attempt_binding_result
checkpoint_result
history_cut_result
overall_status
reason_codes[]
```

Validation result nie ustanawia knowledge exposure; reveal/grant jest osobną decyzją.

---

# 87. Attestation Contract

Gate Attestation/Decision wiąże exact cut i nie jest samoopisanym oświadczeniem executora.

```text
gate_decision_id
campaign_id
stage_run_ref
attempt_ref
gate_policy_ref
input_history_cut
checkpoint_ref
knowledge_state_ref
requested_view_ref
eligibility_result
reason_codes[]
```

Legacy `GATE_ATTESTATION` pozostaje obsługiwane w compatibility profile.

Attestation nie dowodzi total knowledge ani pełnej ochrony przed host rollback.

---

# 88. Continuation Ticket

Baseline R5 redukuje `ContinuationTicket` do canonical **transition authorization proposal**, które nie ma niezależnego current lifecycle. Body:

```text
ticket_id
campaign_id
stage_run_ref
lane_run_ref optional
attempt_ref
prior_checkpoint_or_handoff_ref
gate_decision_ref
allowed_next_transition
proposal_parent_head
governing_policy_ref
expiry_or_single_use_policy
authorized_actor_or_capability_profile_ref
```

Proposal może zostać przygotowane względem `proposal_parent_head`, ale staje się authority **wyłącznie atomowo w tym samym accepted command/commit co autoryzowana transition**. Acceptance validator ponownie sprawdza current expected parent/policy/source; sam wcześniejszy zapis proposal bytes nie przesuwa head i nie tworzy current authorization state. Retry tego samego commandu jest idempotentny, reuse w innym command/campaign/policy jest reject.

Jeżeli przyszły deployment wymaga trwałego offline/asynchronous human approval, musi użyć osobnego versioned authorization profile z jawnym issue/consume lifecycle; nie wolno po cichu rozluźnić baseline expected-head semantics.

---

# 89. Supply-chain records

Supply-chain records rozdzielają:

```text
AUDITED_SUBJECT_DEPENDENCIES
BDB_APPLICATION_DEPENDENCIES
BUILD_TOOLCHAIN_DEPENDENCIES
EXTERNAL_EXECUTOR_TOOL_DEPENDENCIES
```

Nie wolno mieszać dependency source badanego produktu z dependency samego audytora w jednym ambiguous manifest.

---

# 90. Legacy Artifact Reference

`LEGACY_RAW_REF` jest minimalnym current-v2 reference do immutable raw legacy bytes i **nie referencjonuje assessmentów, które same zależą od niego**:

```text
legacy_ref_id
raw_digest
byte_length
media_type
legacy_contract_hint optional
original_path informational
import_input_history_cut
```

Parsed stage/profile facts, mechanical validity, source reconciliation, lineage admission, exposure reconstruction i current evidence applicability są **osobnymi późniejszymi canonical assessments** referencjonującymi `legacy_ref`. Derived `LEGACY_IMPORT_VIEW` może je zestawić dla UI/exportu, ale nie jest authority i nie wraca jako pole do `LEGACY_RAW_REF`. Dzięki temu import graph jest acykliczny.

---

# 91. Legacy validation levels

Legacy validation/admission levels są dokładnie:

```text
L0_BYTES_PRESENT
L1_RAW_DIGEST_KNOWN
L2_STRUCTURALLY_PARSED
L3_INTERNAL_INTEGRITY_VALIDATED
L4_SOURCE_IDENTITY_EXACTLY_RECONCILED
L5_LINEAGE_ROLE_AND_TRUSTED_SELECTION_VALIDATED
```

Kryteria są kumulatywne i zdefiniowane normatywnie w Migration & Compatibility. `L5` NIE zawiera ogólnego twierdzenia o executor knowledge/blindness.

Exposure confidence jest osobną osią:

```text
EXACT
STRONG
PARTIAL
UNKNOWN
```

Canonical `BOOTSTRAP_ADMISSION_DECISION.result` używa dokładnie:

```text
CANONICAL_BOOTSTRAP_ADMITTED
CANONICAL_BOOTSTRAP_ADMITTED_WITH_EXPOSURE_LIMIT
BLOCKED_CANONICAL_ADMISSION
```

Canonical `TRUSTED_PREDECESSOR_SELECTION_DECISION` jest odrębną decision family, a nie aliasem generic `ApprovalDecision`. Dla canonical-predecessor role wiąże exact candidate set, selected legacy raw ref, current source/lineage assessments i installation-pinned predecessor pin:

```text
trusted_predecessor_selection_decision_id
selection_input_history_cut
candidate_legacy_refs[]
selected_legacy_ref optional-by-decision
source_reconciliation_assessment_ref
lineage_admission_assessment_ref
selection_policy_ref
predecessor_pin_ref
decision = SELECTED | REJECTED | CONFLICTED | INSUFFICIENT_DATA
reason_codes[]
```

`SELECTED` wymaga dokładnie jednego `selected_legacy_ref` należącego do candidate set oraz pin/assessment bindings dla tego samego predecessor. W bootstrap `seq=1` refs do legacy/assessment objects mogą wskazywać wyłącznie wcześniejsze nodes tej samej canonical closure; `predecessor_pin_ref` pochodzi z exact installation trust boundary. Generic `APPROVAL_DECISION` nie może zastąpić tego selection authority.

Canonical `BOOTSTRAP_ADMISSION_DECISION`:

```text
bootstrap_admission_decision_id
legacy_ref
requested_role
mechanical_validation_assessment_ref
source_reconciliation_assessment_ref
lineage_admission_assessment_ref
exposure_reconstruction_assessment_ref optional
trusted_predecessor_selection_ref optional-by-role
admission_policy_ref
admission_input_history_cut
result
limitations[]
reason_codes[]
```

Decision wiąże exact `LEGACY_RAW_REF`, `LegacyMechanicalValidationAssessment`, `SourceReconciliationAssessment`, lineage admission assessment, exposure reconstruction assessment, trusted predecessor selection i current v2 policy/history cut. Dla `requested_role=CANONICAL_PREDECESSOR` `trusted_predecessor_selection_ref` jest obowiązkowy, wskazuje `TrustedPredecessorSelectionDecision.decision=SELECTED`, a `selected_legacy_ref` oraz source/lineage assessment bindings MUSZĄ odpowiadać temu samemu `legacy_ref`. `predecessor_pin_ref` selection decision musi być autoryzowany przez exact `INSTALLATION_BOOTSTRAP_PROFILE_V1` lub jego przypięty governing policy/trust artifact; dowolny pin z bieżącego workspace jest niedozwolony. Po initialization wszystkie assessment refs muszą być już akceptowalne na `admission_input_history_cut`. Dla jedynego `commit_seq=1` bootstrapu obowiązuje §14.6: assessment refs mogą wskazywać wcześniejsze content objects tej samej zwalidowanej topologicznej closure przy `admission_input_history_cut=EMPTY_HISTORY_CUT`; nie są wówczas przedstawiane jako prior accepted facts. Decision nigdy nie może wskazywać future `CampaignGenesis`/`StageRun`; przeciwnie, `CampaignGenesis` wskazuje wcześniejszy `BootstrapAdmissionDecision`.

Canonical predecessor wymaga L5 + specific role policy + trusted predecessor pin/selection. Auxiliary role może mieć inny próg zgodnie z current admission policy.

Unknown exposure może blokować blind-origin claim bez blokowania samego lineage admission.

Canonical assessment objects:

```text
LegacyMechanicalValidationAssessment:
  assessment_id
  legacy_ref
  assessment_input_history_cut
  legacy_schema_ref
  legacy_profile_ref
  mechanical_validation_policy_ref
  parsed_legacy_variant_stage_facts
  integrity_check_results[]
  result = VALID | INVALID | INSUFFICIENT_DATA
  reason_codes[]

SourceReconciliationAssessment:
  assessment_id
  legacy_ref
  assessment_input_history_cut
  target_source_generation_ref
  identity_profile_ref
  reconciliation_policy_ref
  raw_identifiers
  normalized_identity_body_ref
  result = EXACT_MATCH | CONFLICT | INSUFFICIENT_DATA
  reason_codes[]

LineageAdmissionAssessment:
  assessment_id
  legacy_ref
  assessment_input_history_cut
  admission_policy_ref
  mechanical_validation_assessment_ref
  source_reconciliation_assessment_ref
  requested_role
  validation_level
  predecessor_pin_ref optional
  freshness_binding_refs[]
  result = ADMITTED | ADMITTED_WITH_LIMIT | BLOCKED
  reason_codes[]

LegacyExposureReconstructionAssessment:
  assessment_id
  legacy_ref
  assessment_input_history_cut
  reconstruction_policy_ref
  declared_scope
  controlled_exposure_fact_refs[]
  known_missing_channel_classes[]
  confidence = EXACT | STRONG | PARTIAL | UNKNOWN
  supporting_history_refs[]
  blind_origin_claim_scope
  limitations[]

LegacyObservationSemanticEquivalenceAssessment:
  assessment_id
  legacy_ref
  assessment_input_history_cut
  legacy_observation_locator
  legacy_observation_raw_ref optional
  target_source_generation_ref
  candidate_current_claim_or_obligation_refs[]
  mapping_policy_ref
  semantic_equivalence = EXACT | SCOPED | AMBIGUOUS | NONE
  limitations[]
  reason_codes[]
```

`LegacyObservationSemanticEquivalenceAssessment` odpowiada wyłącznie na pytanie o semantic equivalence pojedynczej/konkretnej historycznej observation względem current target scope. Nie jest aliasem §127 `LegacyObservationMappingAssessment`, który agreguje mapping coverage do current obligations/claims i ma odrębną domenę `MAPPED|PARTIAL|NOT_MAPPABLE|INSUFFICIENT_DATA`. Żaden z tych dwóch assessments nie kwalifikuje evidence samym mapowaniem. Jeżeli historyczna obserwacja ma być użyta jako current evidence, potrzebuje osobnego current `EvidenceQualificationAssessment` i `EvidenceApplicabilityAssessment` względem exact claim/source/environment/dependencies; `AMBIGUOUS/NONE` nie może zostać podniesione do evidence przez importer.

W bootstrap A/B/C current assessments są nowymi v2 objects i nigdy nie zmieniają legacy raw bytes.

---

# 92. Evidence Invalidation Graph

Evidence invalidation jest dependency-driven, nie tylko source-driven.

Canonical invalidation fact:

```text
invalidation_id
affected_evidence_or_qualification_refs[]
dependency_ref
reason
scope
invalidation_input_history_cut
propagation_policy_ref
```

`invalidation_input_history_cut` wskazuje wyłącznie stan badany **przed** acceptance invalidation. Moment, od którego invalidation obowiązuje, wynika z zewnętrznego accepted event position; nie jest wpisywany jako własny post-acceptance head w object body.

Propagation musi przeliczyć current support dla:

```text
Finding
Coverage Obligation qualification
SOUND
Candidate/Final Assurance Case
STOP input
Stage/Campaign completion eligibility
```

Przy nowym SourceGeneration stary evidence otrzymuje `EvidenceApplicability.status=STALE`; jeżeli finding view wymaga lifecycle oznaczenia, **osobno** może otrzymać `FindingLifecycle=STALE_FOR_CURRENT_SOURCE`. Te enumy nie są wymienne. Requalification tworzy nowe current assessments.

Invalidation harnessu/oracle/fixture może nastąpić przy tym samym source SHA.

---

# 93. Remediation Unit

Remediation Unit dotyczy **nowej SourceGeneration** i nie jest częścią same-source E1–E5 history.

```text
repair_unit_id
old_source_generation_ref
root_cause_ref
expected_fixed_property
regression_obligation_refs[]
negative_control_refs[]
sibling_test_refs[]
holdout_verification_plan_ref
```

Naprawa nie mutuje old finding/evidence.

---

# 94. Requalification Result

Requalification Result wiąże nową SourceGeneration z replay/new evidence:

```text
repair_unit_ref
new_source_generation_ref
replayed_capsule_refs[]
new_evidence_qualification_refs[]
finding_disposition
sibling_results[]
regression_results[]
supply_chain_result_ref
```

Disposition:

```text
FIXED
STILL_PRESENT
PARTIALLY_FIXED
REGRESSION
BLOCKED
```

---

# 95. Schema Registry — R5.4

`schema_registry/1` remains historical. New R5.4 campaigns pin exactly `schema_registry/2`, defined in §192 and the successor Registry. Each binding maps a registered semantic key to exact executable schema RawRef (bytes, SHA256, length, media type, exact artifact profile). Schema ID alone is insufficient; schema revision identity is RawDigest(exact executable bytes), distinct from ObjectDigest(schema_registry,2,body). A schema reference's `kind=schema` is a reference representation, not a registered ObjectDigest wire kind.

The campaign's accepted/pinned schema set never follows latest installed files. Missing mandatory entry or mutated bytes is fail-closed before first acceptance. This candidate binds a finite bootstrap/NF02 subset: all other registered keys remain unbound and acceptance is forbidden. No unspecified future subsystem schema is fabricated. Exact root schema bytes are externally pinned before validating SchemaRegistry; registry/profile may not self-authorize. §192 governs construction/install/readback and no in-place migration.

---

# 96. Versioning — R5.4

Optional additive schema field can be compatible only under its explicit contract. Changing required fields, predicates or meaning is breaking; the NF02 new kinds are assignment_package_binding/1, lane_result_admission_evidence/2, bdb_audit_lane_result/2 and schema_registry/2. AssignmentManifest/1 body and digest semantics remain unchanged. NF02 /1 result/evidence extensions are not legalized or aliased.

Canonical serialization/RawDigest/ObjectDigest remain ADR-006. Governing policy/spec/profile refs resolve from exact prior input cut (or authorized installation pins at EMPTY_HISTORY). Same-commit semantic self-upgrade remains forbidden. Existing runs/campaigns cannot auto-upgrade; for this revision, all new semantics require a new campaign/namespace with exact R5.4 installation pins. Old campaigns are historical/read-only with explicit limited assurance. No retro binding or new schema-install successor trigger. See §192 migration.

---

# 97. Required vs optional fields

Required/optional fields wynikają z exact schema revision i cross-artifact policy. Pole optional nie może być semantycznie mandatory „tylko w kodzie” bez jawnego conditional invariant.

Brak required field = schema failure. Brak optional field nie może zostać uzupełniony z ambient state bez jawnej derivation rule.

---

# 98. Extension namespace

Extension namespace jest dozwolony tylko tam, gdzie schema jawnie przewiduje:

```text
extensions: {
  "<namespace>": <typed object>
}
```

Extension nie może zmieniać semantics wymaganych core fields ani bypassować validator/gate.

---

# 99. Null policy

Null ma jednoznaczną semantykę per field. Nie wolno traktować zamiennie:

```text
missing
null
empty string
empty list
UNKNOWN
NOT_APPLICABLE
```

Identity-bearing canonical objects muszą rozróżniać te wartości.

---

# 100. Timestamp policy

Timestamp policy:

- authority ordering = accepted commit sequence/head,
- wall-clock timestamps są observation metadata,
- format: UTC RFC3339 z jawnie określoną precyzją,
- clock source/profile jest rejestrowany dla testów temporalnych,
- timestamp nie może sam ustanawiać „discovered before reveal”, freshness ani retry ordering.

Jeśli wymagana jest trusted time guarantee, potrzebny jest osobny clock/trust profile.

---

# 101. Path policy

Paths w raw bundles są relative POSIX-style zgodnie z artifact contract. Odrzuca się absolute paths, `..`, ambiguous separators, duplicate normalized names i niebezpieczne extraction targets.

Filesystem path nie jest globalnym artifact identity; identity opiera się na typed ref + digest.

---

# 102. Secret redaction

Secret redaction musi zachować evidence o obecności/rodzaju sekretu bez ujawniania secret value.

Raw secret bytes nie trafiają do narracyjnych raportów ani derived views. Jeżeli exact value jest konieczne do restricted evidence, artifact ma restricted sensitivity profile i nie jest dostępny zwykłym lane views.

---

# 103. Sensitive evidence

Sensitive evidence posiada classification/access policy:

```text
PUBLIC_WITHIN_CAMPAIGN
RESTRICTED
SECRET_VALUE_REDACTED
OPERATOR_ONLY
```

Capability broker egzekwuje view policy. Unauthorized resolver/traversal jest reveal violation i może contaminationować lane.

---

# 104. Append-only ledgers

Native v2 ma **jedną append-only canonical accepted history**.

Nazwane „ledgery”:

```text
KNOWLEDGE_EXPOSURE_LEDGER
FINDING_CHANGE_LEDGER
ROOT_CAUSE_NORMALIZATION_LEDGER
CONTRIBUTION_LEDGER
COVERAGE_LEDGER
BLOCKER_LEDGER
TRACEABILITY_GRAPH
```

są deterministic projections/exports z accepted facts, a nie równoległymi mutable heads.

Historyczne legacy ledgers zachowują własne exact bytes i są walidowane jako legacy artifacts.

---

# 105. Snapshot semantics

Snapshot semantics:

- snapshot jest disposable/materialized projection albo immutable historical artifact,
- native projection snapshot wskazuje `as_of_head`,
- snapshot MUSI wskazywać projector code/profile revision,
- stale snapshot nie może obsługiwać gate,
- usunięcie wszystkich native projections nie może zmienić odtwarzanego current outcome.

Restore starego snapshotu nie dowodzi, że jest latest accepted state.

---

# 106. Event sourcing preference

Native v2 używa:

```text
command
→ validate against expected head/spec
→ atomically accept immutable objects + commit + receipt + head
→ derive projections
```

Nie używa:

```text
mutate many JSON/ledger files
→ hope they agree
```

Backend-neutral contract wymaga single-writer lub równoważnej serializable/CAS semantics, atomicity, idempotency i crash recovery.

---

# 107. Artifact lifecycle

Rozróżnia się lifecycle:

**Canonical immutable object revision**
```text
PROPOSED_LOCAL
ACCEPTED
SUPERSEDED_BY_NEW_REVISION
INVALIDATED_AS_SUPPORT
```

**Raw artifact**
```text
RECEIVED
VALIDATED
ACCEPTED_REFERENCE
QUARANTINED
RETAINED
```

**Projection/export**
```text
MATERIALIZED
STALE
REBUILT
DISPOSABLE
```

Nie używać jednego wspólnego lifecycle do wszystkich klas danych.

---

# 108. Validation result contract

Validation Result contract:

```text
validation_id
target_ref
contract_ref
validation_layers[]
overall_status
reason_codes[]
validator_profile_ref
input_history_cut optional
```

`PASS` oznacza przejście wymaganych layers tego contractu. Nie ustanawia authenticity, current admission, knowledge exposure ani evidence truth, jeśli te nie są częścią target contract.

---

# 109. Error code policy

Error codes są stabilnymi semantic families. Human message może się zmieniać.

Przykładowe core families:

```text
SCHEMA_MISMATCH
RAW_DIGEST_MISMATCH
OBJECT_DIGEST_MISMATCH
DANGLING_REF
WRONG_REF_TYPE
SOURCE_IDENTITY_CONFLICT
STALE_HEAD
ID_REUSE_CONFLICT
COMMAND_BINDING_CONFLICT
STATE_CONFLICT
RESULT_CONFLICT
LATE_RESULT
VIEW_REJECTED
EVIDENCE_QUALIFICATION_REJECTED
RESOURCE_BLOCKED
CANONICAL_ADMISSION_BLOCKED
```

`CANONICAL_ADMISSION_BLOCKED` jest **error-code family**. Normatywny `BootstrapAdmissionDecision.result` dla tego przypadku pozostaje `BLOCKED_CANONICAL_ADMISSION`; result enum i error-code namespace nie są wymienne.

Accepted handling outcome dla wyniku dostarczonego po terminalnym/cancelled Attempt nazywa się dokładnie `QUARANTINED_LATE_RESULT`; `LATE_RESULT` pozostaje error-code family dla obsolete/illegal late transition. `RESULT_CONFLICT` oznacza różne bytes/result digest dla tego samego zamkniętego result slotu.

Design Closure reference scenarios używają także nazwanych machine outcomes. Nie tworzą jednego globalnego enumu; każdy należy do wskazanego namespace/contract:

```text
COLLECTION_INCOMPLETE            # CollectionRun failure/result family
BUNDLE_AUTHORITY_MISMATCH        # trust/import validation error family
WRONG_BINDING                    # typed/spec/source/policy binding error family
STALE_INPUT                      # stale head/predecessor/input family
INDEPENDENCE_REQUIREMENT_UNMET   # Evidence/Coverage qualification reason/outcome
INSUFFICIENT_DATA                # fail-closed assessment/STOP reason
MUTATION_NOT_ACTIVATED           # OracleChallenge status
E6_PLAN_REJECTED                 # E6 plan validation outcome
SELF_REFERENCE                   # identity/preimage validation error family
ROLLBACK_DETECTED                # external-anchor verification outcome
WRONG_SUBJECT                    # EvidenceApplicability/Execution binding outcome
CHALLENGE_STALE                  # challenger/candidate binding outcome
MODEL_ONLY                       # model-fidelity applicability classification
UNSUPPORTED_RUNTIME              # runtime qualification outcome
BUILD_NOT_REPRODUCIBLE           # build qualification outcome
```

Jeżeli scenario wymaga tych nazw, test nie może zastąpić ich innym lokalnym aliasem bez jawnego compatibility mappingu. `CONSUMED`, `SCOPED`, `STALE`, `INVALIDATED`, `REDUNDANT_OBSERVER_FOR_CASE` i podobne wartości pozostają we własnych już zdefiniowanych status enums.

Compatibility layer mapuje legacy error families bez wymogu literalnego tekstu.

---

# 110. Warning policy

Warning nigdy nie może ukrywać condition, która według pinned contract jest fail-closed.

Warnings są wyłącznie non-blocking observations. Każdy warning ma typed code, target ref i scope.

Jeżeli stan jest `UNKNOWN/BLOCKED/INSUFFICIENT_DATA`, używa się właściwego assessment/status, nie warningu.

---

# 111. Artifact family contracts

Artifact family contract określa:

```text
artifact_type
schema_ref
raw/canonical identity semantics
required validation layers
allowed producer roles
allowed consumer roles
sensitivity profile
bundle membership rules
stage/campaign cardinality
```

Legacy i native families są osobnymi contract revisions.

---

# 112. E1 required artifact family

E1 native required family wynika z E1 StageSpec i może obejmować discovery/inventory/obligation/checkpoint outputs.

Nie wymaga FINAL_OUTCOME ani FINAL_ASSURANCE_CASE.

Każdy required output wskazuje exact history cut i contract.

---

# 113. E2 required additions

E2 required additions obejmują zgodnie ze StageSpec m.in. blind precursor, controlled predecessor reveal, individual adjudication, root-cause/contradiction assessments i StageCompletion.

Legacy E2 F1/F2/final bundle są osobnym compatibility profile.

---

# 114. E3 required additions

E3 required additions obejmują native discovery provenance, gap-directed obligations, controlled corpus/holdout reveal i StageCompletion.

Pierwszy mixed-generation reference slice może używać minimalnego subsetu required przez foundation profile; nie oznacza pełnego production E3 completion.

---

# 115. E4 required additions

E4 required additions są policy-pinned i obejmują state/model/fidelity/temporal/conformance obligations także dla critical subsystems bez wcześniejszych findings.

Model proof bez fidelity/conformance assessment nie kwalifikuje implementation obligation.

---

# 116. E5 required additions

E5 required additions są normatywnie rozdzielone: **E5A** = interaction/mutation/oracle attack+synthesis outputs potrzebne do utworzenia immutable Candidate Assurance Case; **E5B** = wymagane challenger assignments/results dla exact candidate. `E5 StageCompletion` następuje dopiero po E5B. Global STOP/CampaignConclusion/FinalAssuranceCase/ReleaseQualification są późniejszymi campaign artifacts, nie prerequisites E5 StageCompletion.

Final CampaignConclusion powstaje dopiero po STOP i wymaganych challenger resolutions.

---

# 117. Final bundle integrity

Final campaign export integrity wymaga:

- exact BundleManifest,
- raw hash manifest,
- canonical refs do final accepted objects,
- `export_as_of_head`,
- consistency validator result,
- external release artifact digest.

Export ZIP może zostać odtworzony; authority conclusion pozostaje w canonical history.

---

# 118. Machine report consistency

Machine report consistency validator porównuje narracyjne/summary fields z exact current machine refs. Finding counts, release status, STOP reasons i residual risk nie mogą być ręcznie wpisane sprzecznie z projections.

Mismatch = final export invalid.

---

# 119. Narrative report constraints

Narrative reports:

- mogą streszczać,
- nie ustanawiają nowych finding/evidence/status facts,
- muszą wskazywać exact campaign/source/as_of_head,
- nie mogą rozszerzać bounded conclusion,
- nie mogą ukrywać UNKNOWN/BLOCKED/WAIVED/unsupported scope.

Narracja nie jest fallback authority przy konflikcie z canonical data.

---

# 120. Data retention

Retention policy rozróżnia:

```text
canonical history
immutable accepted objects
legacy raw artifacts
restricted evidence
disposable projections
temporary execution workspaces
```

Canonical history i accepted object closure są zachowywane zgodnie z campaign retention profile. Projections można odtworzyć. Secrets mogą podlegać restricted retention/rotation policy bez usuwania redagowanego evidence trail.

---

# 121. Provenance chain

Provenance chain dla materialnego claimu powinna pozwalać odtworzyć:

```text
SourceGeneration
→ Stage/Lane/Attempt
→ Knowledge/Discovery cut
→ Hypothesis
→ Experiment/Execution
→ Observation dependencies
→ Evidence qualification/applicability
→ Finding/Obligation
→ Stage/Campaign decision
```

Każdy hop jest typed exact revision ref.

---

# 122. Build-time vs runtime artifacts

Build-time artifacts i runtime campaign artifacts są odrębnymi domains.

Build-time:
- application source/resources,
- schemas/specs/prompts embedded,
- builder/toolchain,
- standalone output.

Runtime:
- campaign history,
- subject source,
- evidence,
- projections.

Nie wolno używać subject source SHA jako application build identity ani odwrotnie.

---

# 123. Build Manifest

`BUILD_INPUT_MANIFEST` zamyka wszystkie deklarowane build inputs **przed** wytworzeniem finalnego artifactu:

```text
application_source_generation_ref
builder_recipe_ref
builder_tool_raw_digest
builder_tool_version
ordered_input_refs[]
schema_set_ref
stage_lane_policy_refs[]
embedded_resource_refs[]
toolchain_runtime_profile_ref
deterministic_settings_ref
```

Jeżeli manifest jest embedded w output, nie zawiera finalnego hash outputu. Po zbudowaniu powstaje zewnętrzny `BUILD_PROVENANCE_RECEIPT`:

```text
build_input_manifest_ref
final_output_raw_digest
byte_length
media_type
build_environment_ref
verification_refs[]
```

Build NIE może brać niezadeklarowanych danych z cwd, mtime, hostname, aktualnego czasu, gitignored files ani network downloads. Jeśli timestamp jest osadzony, jest jawnie zadanym inputem.

---

# 124. Standalone payload manifest

„Standalone deterministic `.py`” w baseline oznacza:

- jeden dystrybuowany plik zawierający pełny kod aplikacji,
- wymagane schemas/specs/prompts i małe required self-test fixtures,
- brak network install przy starcie,
- brak implicit import z cwd/user site jako application code,
- jawnie zdefiniowaną granicę interpreter/stdlib/runtime profile.

Nie oznacza, że `.py` zawiera interpreter, OS ani wszystkie external audit tools.

`EMBEDDED_PAYLOAD_MANIFEST` identyfikuje embedded components. Zewnętrzny final `RawDigest` artefaktu release jest authority dla distributed bytes i nie jest self-referential field we własnym preimage.

---

# 125. Deterministic ZIP contract

Deterministic ZIP contract definiuje fixed ordering, normalized path syntax, fixed metadata/timestamps profile, compression profile i no-duplicate semantics.

Build/replay test musi wykazać byte-identical output dla tych samych exact inputs/profile. Jeżeli platform/library nie gwarantuje identyczności, scope deterministic claim musi być ograniczony.

---

# 126. Compatibility artifact contracts

Compatibility artifact contracts rozdzielają:

```text
LEGACY_BEHAVIOR_PRESERVATION
VALIDATOR_CORRECTNESS
CURRENT_ADMISSION
```

Historyczny parser/validator może zachowywać legacy contract, a current v2 hardening może celowo dawać inny correctness result z jawnie zaakceptowanym exception/hardening decision.

Canonical `COMPATIBILITY_FIXTURE_ASSESSMENT`:

```text
compatibility_fixture_assessment_id
fixture_raw_ref
fixture_contract_ref
assessment_input_history_cut
legacy_observed_result
legacy_observed_error_family optional
independent_safe_expected_result
independent_expected_error_family optional
expectation_basis_ref
known_legacy_bug
intentional_hardening_exception_ref optional
v2_observed_result
preservation_result = PASS | DIFFERENCE | UNQUALIFIED
correctness_result = PASS | FAIL | UNQUALIFIED
reason_codes[]
```

Canonical `COMPATIBILITY_GATE_RESULT` agreguje exact fixture assessment refs dla jednej pinned corpus/policy revision:

```text
compatibility_gate_result_id
gate_type = LEGACY_BEHAVIOR_PRESERVATION | VALIDATOR_CORRECTNESS
assessment_input_history_cut
compatibility_corpus_ref
governing_policy_ref
fixture_assessment_refs[]
qualified_denominator
pass_count
fail_or_difference_count
unqualified_count
result = PASS | FAIL | BLOCKED
reason_codes[]
```

`VALIDATOR_CORRECTNESS` nie może używać v1 outputu jako własnego ground truth. Known hardening exception może powodować preservation `DIFFERENCE` przy correctness `PASS`.

---

# 127. Migration-derived coverage

Legacy E1/E2 nie otrzymują retroaktywnego native-v2 `CoverageObligation`, `CoverageObligationQualification` ani historii kwalifikacji. Historyczne coverage ledgers pozostają wyłącznie legacy artifacts własnej epoki.

Current migration może utworzyć canonical `LEGACY_OBSERVATION_MAPPING_ASSESSMENT`:

```text
legacy_observation_mapping_assessment_id
legacy_ref
assessment_input_history_cut
legacy_observation_refs[]
current_obligation_revision_refs[]
current_claim_refs[] optional
mapping_policy_ref
mapping_rationale
result = MAPPED | PARTIAL | NOT_MAPPABLE | INSUFFICIENT_DATA
limitations[]
reason_codes[]
```

który mapuje historyczne observations/methods do **bieżących Coverage Obligations** bez retroaktywnego tworzenia native-v2 evidence history. Każdy mapped observation ref wymagający semantic-equivalence claim MUSI wskazywać właściwy `LegacyObservationSemanticEquivalenceAssessment`; `SCOPED` z tego assessmentu nie jest automatycznie `PARTIAL` mapping result.

Current obligation może otrzymać `qualification_status=QUALIFIED` wyłącznie przez nowy `CoverageObligationQualification`, gdy bieżące EvidenceQualification/Applicability oraz acceptance predicate są spełnione. W przeciwnym razie qualification ma odpowiednio `UNASSESSED`, `IN_PROGRESS`, `BLOCKED` albo `STALE`; evidence może **osobno** mieć applicability `SCOPED`. Nie istnieje status obligation `PASS` ani `SCOPED`.

Nie istnieje automatyczne „legacy D4”.

---

# 128. Migration-derived invariant

Invariant wyprowadzony dziś z legacy findingu ma:

```text
origin = DERIVED_FROM_LEGACY_*
creation_input_history_cut = ...
```

Nie twierdzi, że był formalnym historical E1/E2 invariant.

Jego materiality/activation jest current bootstrap/E0 decision.

---

# 129. Migration-derived exposure

Legacy exposure używa **jednego canonical contractu** `LegacyExposureReconstructionAssessment` z §91. Ta sekcja nie definiuje drugiego schema.

Derived `LEGACY_EXPOSURE_VIEW` może agregować wiele zaakceptowanych assessmentów dla operatora, ale nie jest authority i zawsze wskazuje exact assessment refs + `as_of_head`.

Nie tworzy retroaktywnego Knowledge State ani ENFORCED isolation dla historycznego executora.

---

# 130. Cross-source protection

Cross-source protection:

- claim/evidence/obligation refs domyślnie muszą mieć zgodny SourceGeneration,
- różna SourceGeneration = stale/not current unless requalification contract jawnie zezwala,
- representation changes bez source semantic change są rozstrzygane przez SourceIdentityProfile,
- dependencies/environment changes mogą ograniczyć applicability nawet bez source change.

---

# 131. Requalification cross-source exception

Requalification jest jedynym normalnym mechanizmem przeniesienia assurance na nową SourceGeneration.

Tworzy nowe executions/qualifications/dispositions, wskazując old evidence jako historical input. Nie zmienia old evidence statusu dla starego source; zmienia jego applicability względem current source.

---

# 132. Source drift records

Source drift record:

```text
old_source_generation_ref
new_source_generation_ref
detection_input_history_cut
drift_observation_refs[]
changed_manifest_members[]
dependency_profile_change optional
reason
```

Canonical `SOURCE_DRIFT_IMPACT_ASSESSMENT`:

```text
source_drift_impact_assessment_id
source_drift_record_ref
assessment_input_history_cut
drift_policy_ref
affected_stage_lane_attempt_refs[]
affected_evidence_qualification_refs[]
affected_obligation_qualification_refs[]
subject_relation = SUBJECT_SOURCE_CHANGED | NON_SUBJECT_PROFILE_CHANGED | MIXED | UNKNOWN
continuation_effect = BLOCK_CURRENT_RUN | REQUIRE_REQUALIFICATION | ALLOW_SCOPED_CONTINUATION | UNKNOWN
limitations[]
reason_codes[]
```

Assessment wskazuje już istniejący `SourceDriftRecord`; record nie wskazuje future assessment revision. Materializowany current drift view może zawierać derived `drift_impact_assessment_ref`, ale nie należy on do immutable `SOURCE_DRIFT_RECORD` preimage. Authority stanowi accepted assessment.

Drift w trakcie same-source E1–E5 campaign blokuje kontynuację current run, chyba że dotyczy wyłącznie jawnie external non-subject profile i policy to dopuszcza.

---

# 133. Environment record

EnvironmentRecord jest immutable revision:

```text
environment_id
environment_revision
os_profile_ref
runtime_profile_ref
browser_profile_ref optional
dependency_set_ref
filesystem_profile
network_profile
clock_profile
sandbox_profile
external_service_profile_refs[]
```

Evidence applicability wskazuje exact EnvironmentRecord; tekst typu „Windows 10” nie wystarcza dla materialnych różnic środowiska.

---

# 134. Tool execution record

ToolExecutionRecord:

```text
tool_run_id
tool_profile_ref
command_spec_ref
actual_command_hash
real_exit_code
input_refs[]
output_raw_refs[]
environment_ref
started_observation_time
finished_observation_time
status
resource_limit_events[]
```

`tool output` jest observation/hypothesis input, nie automatycznym findingiem. Tool command z audytowanego repo nie jest wykonywany automatycznie bez control-plane authorization.

---

# 135. Machine-generated hypothesis provenance

Machine-generated hypothesis provenance wiąże exact tool run + source/history cut + generated candidate.

Dodatkowo `DiscoveryRecorded` pozostaje wymagane, jeśli kandydat ma później uzyskać blind discovery provenance. Tool origin, human/model confirmation i corpus novelty są osobnymi relacjami.

---

# 136. Fuzzer finding contract

Fuzzer finding contract nie tworzy findingu z samego crashu.

Fuzzer output zapisuje:

```text
generator_ref
generator_profile_ref
seed_ref optional
input_artifact_ref
activation_observation_refs[]
path_observation_refs[]
crash_observation_ref optional
invariant_candidate_ref optional
minimization lineage
harness_ref
environment_ref
```

Następnie powstaje Hypothesis/Experiment/EvidenceQualification.

---

# 137. Property test failure contract

Property test failure analogicznie zapisuje exact property revision, generated case, shrink lineage, execution descriptor i raw observations.

Property engine/test harness może być wspólnym oracle; independence jest oceniane osobno względem claimu.

---

# 138. State model versioning

State model versioning:

- każda zmiana states/transitions/abstraction/bounds = nowa model revision,
- model revision wskazuje implementation mapping,
- proof results wskazują exact model revision,
- implementation changes/source changes wymagają nowego fidelity/conformance assessment.

Nie ma silent reuse proofu na zmienionym modelu.

---

# 139. Root cause normalization history

Root-cause normalization nie posiada własnego mutable ledger head.

Merge/split/rename/**membership** są authority wyłącznie przez nową accepted `RootCauseRevision` zawierającą `membership_edges[]` oraz — przy zmianie lineage — backward `predecessor_root_cause_refs[]`. Nie istnieje osobny canonical `RootCauseMembershipAccepted`, ponieważ tworzyłby drugie miejsce prawdy dla membership.

`RootCauseRevisionSuperseded` może być accepted transition/status fact wskazującym prior root-cause revision i jego późniejszy current lifecycle, ale nie niesie własnej konkurencyjnej listy members.

Derived `ROOT_CAUSE_NORMALIZATION_LEDGER.jsonl` oraz `ROOT_CAUSE_MEMBERSHIP` edges w Traceability Graph są projekcjami exact `RootCauseRevision.membership_edges[]` `as_of_head`.

Membership jest versioned i scoped; multi-causal finding może wymagać AND/OR/hyperedge semantics.

---

# 140. Finding update history

Finding changes nie są mutable update row. Rozdzielone są dwa rodzaje zmian:

1. zmiana **claim statement/scope/category/invariant binding** → nowa `FindingClaimRevision` z `previous_finding_claim_revision_ref`;
2. zmiana **M/R/I/severity/lifecycle/evidence support** przy tym samym claimie → nowa `FindingAdjudicationDecision` z `previous_adjudication_decision_ref`.

Evidence invalidation nie mutuje claimu. Powoduje nową applicability/adjudication decision na późniejszym cut. Derived `FINDING_CHANGE_LEDGER.jsonl` łączy obie historie jako export, ale nie jest authority.

---

# 141. Stop Gate reproducibility

STOP reproducibility wymaga exact accepted `StopInput`; ten object pinuje `StopInputSnapshot`, input HistoryCut, evaluator revision, governing/release policy/spec/profile bindings i stage/coverage/evidence closure. `StopEvaluation.stop_input_ref` MUSI wskazywać właśnie ten exact input.

Powtórne policzenie na tym samym `StopInput` i tym samym evaluator contract MUSI dać ten sam wynik.

Stale projection, inny current head albo nowa invalidation tworzą **nową** StopEvaluation; nie nadpisują starej.

---

# 142. Saturation calculation provenance

Każda saturation/effort metric przechowuje:

```text
metric_name
metric_profile_ref
formula_revision_ref
exact input refs[]
denominator
unknown_count
value
limitations
```

Konkretne thresholds/round counts są w pinned Effort/Stop Policy, nie w kodzie bez versioned config.

---

# 143. No magic aggregate score

Nie istnieje obowiązkowy globalny `AUDIT_SCORE`.

UI może prezentować derived indicators, ale:

- nie są STOP authority,
- nie maskują UNKNOWN/BLOCKED,
- mają formula/profile revision,
- nie są porównywane między campaign bez zgodnego denominator/profile.

---

# 144. Admissibility policy

Admissibility policy jest exact revision i określa osobno:

```text
artifact_admission_predicate_ref
corpus_admission_predicate_ref
evidence qualification requirements
legacy validation role requirements
source equality requirements
exposure_requirement_ref
isolation_requirement_ref
stage input cardinality
waiver/N/A authority
```

Nie używa prostego `minimum_evidence_level` jako zamiennika claim-relative assessment.

---

# 145. Blocked semantics

`BLOCKED` oznacza, że wymagany bezpieczny predicate/obligation/measurement nie może być obecnie rozstrzygnięty lub wykonany.

Nie jest:

```text
PASS
NO_FINDING
UNKNOWN
NOT_APPLICABLE
WAIVED
```

Każdy BLOCKED ma reason, materiality, safe-to-test/resolve assessment i wpływ na stage/STOP.

---

# 146. Unknown semantics

`UNKNOWN` oznacza brak wystarczającej kwalifikowanej informacji w exact scope.

Nie wolno:

- redukować UNKNOWN do LOW,
- liczyć UNKNOWN jako PASS,
- usuwać unknown scope z denominatora bez accepted scope decision.

STOP policy jawnie rozstrzyga, czy dany UNKNOWN powoduje CONTINUE, E6, BLOCKED albo bounded conclusion.

---

# 147. SOUND record

SOUND jest claim-relative derived qualification, nie globalnym „bezpieczne”.

`SOUND_CLAIM`:

```text
sound_claim_id
claim_revision_ref
scope
required_obligation_refs[]
current_qualified_support_refs[]
negative_control_refs[]
mutation/oracle_challenge_refs[]
limitations[]
applicability_cut
status
```

SOUND bez current mandatory obligation support jest invalid/stale. Invalidation propaguje do SOUND.

---

# 148. Negative Evidence Record

`NEGATIVE_EVIDENCE_RECORD` jest **derived projection/export**, nie osobnym current authority ani lifecycle. Powstaje deterministycznie z exact accepted `CoverageObligationQualification`, EvidenceQualification/Applicability, executions i controls na wskazanym `as_of_head`:

```text
as_of_head
coverage_obligation_qualification_ref
claim_scope
execution_refs[]
observation_qualification_refs[]
negative_controls[]
mutation/oracle_challenge_refs[]
unresolved_scope_refs[]
limitations[]
```

Nie może nadpisać substantive outcome ani qualification statusu źródłowych canonical decisions. Nie przechowuje jednego `coverage_depth` jako authority; derived D może być prezentowany osobno.

---

# 149. Auditor calibration record

Calibration ma jawny ground truth model.

Corpus rozróżnia:

```text
SEEDED_KNOWN_DEFECTS
CLEAN_CONTROLS
UNSEEDED_REAL_FINDINGS
DEVELOPMENT_CORPUS
CALIBRATION_CORPUS
HOLDOUT_CORPUS
```

CalibrationResult zawiera:

```text
corpus_revision
defect_units[]
negative_opportunity_units[]
finding_to_defect_match_assessments[]
unseeded_finding_dispositions[]
per_class_denominators
sensitivity optional
specificity optional
unknown_count
unresolved_count
effort_profile
holdout_exposure_state
```

Realny unseeded bug nie jest false positive tylko dlatego, że nie był seeded.

Canonical calibration support obejmuje dodatkowo:

```text
DEFECT_UNIT:
  defect_unit_id
  corpus_revision_ref
  defect_class
  affected_scope_ref
  activation_witness_ref
  violated_invariant_ref optional
  ground_truth_provenance_ref

NEGATIVE_OPPORTUNITY_UNIT:
  negative_opportunity_id
  corpus_revision_ref
  benign_scenario_ref
  prohibited_or_false_claim_scope
  ground_truth_provenance_ref

FINDING_DEFECT_MATCH_ASSESSMENT:
  finding_claim_revision_ref
  finding_adjudication_ref optional
  defect_unit_ref
  match_result = MATCH | NO_MATCH | PARTIAL | UNRESOLVED
  rationale_refs[]
  assessor_profile_ref

CLEAN_CONTROL_ASSESSMENT:
  finding_claim_revision_ref optional
  finding_adjudication_ref optional
  negative_opportunity_ref
  outcome = TRUE_NEGATIVE | FALSE_POSITIVE | UNRESOLVED | BLOCKED
  rationale_refs[]
  assessor_profile_ref

HOLDOUT_EXPOSURE_ASSESSMENT:
  corpus_revision_ref
  evaluator_or_executor_profile_ref
  exposure_state = UNSEEN | POTENTIALLY_EXPOSED | EXPOSED | UNKNOWN
  exposure_input_history_cut
```

Holdout po potential exposure nie może być ponownie traktowany jako unseen dla tego samego evaluation path. Calibration nie jest evidence o completeness realnego produktu.

---

# 150. Claim support count

Support count jest derived z qualified independent/non-independent confirmations.

Nie wpływa bezpośrednio na truth i nie może być majority vote.

Reportuje się razem z dependency overlap/independence, ponieważ 5 auditorów korzystających z tego samego broken oracle nie daje 5 niezależnych proofs.

---

# 151. Leave-one-out contribution

Leave-one-out/unique contribution jest derived analysis:

```text
producer_ref
producer_lane_ref optional
discovery refs
qualified unique mechanisms
support overlap
coverage obligation delta
leave_one_out_loss
history_cut
```

Służy ensemble/saturation planning. Nie zmienia original discovery history.

---

# 152. Artifact naming

Artifact naming jest human-facing i duplicate-safe, ale nie jest identity.

Filename MUSI być deterministic w contract, jeśli wchodzi do bundle hash. Renaming external storage nie może zmieniać semantic object identity, o ile raw bytes/member path contract pozostaje zgodny.

---

# 153. Folder layout final bundle

Final export folder layout jest częścią BundleContract, nie canonical state.

Przykładowo może zawierać:

```text
machine/
reports/
artifacts/
legacy/
views/
```

ale gate korzysta z BundleManifest + typed refs, nie z heurystyki folder name.

---

# 154. Bundle member path uniqueness

Bundle member paths po normalizacji MUSZĄ być unikalne. Duplicate raw path, case-fold collision na wspieranym extraction profile albo alias do tej samej extraction target = reject.

Path safety jest sprawdzane przed extraction/parsing.

---

# 155. Duplicate semantics

Duplicate semantics rozróżnia:

- ten sam logical ID + ten sam revision digest → idempotent same object,
- ten sam logical ID + inna revision → nowa revision/supersession rule,
- ten sam command ID + inny digest → conflict,
- ten sam bundle path + drugi member → reject,
- dwa różne raw artifacts o tej samej nazwie → różne artifacts po RawDigest.

---

# 156. Artifact ownership

Ownership:

```text
PRODUCER
PROPOSER
ACCEPTING_ACTOR
```

to różne role.

Executor/tool może być producer/proposer. Coordinator jest accepting actor dla canonical history. Human operator może mieć jawne authority do policy/scope/waiver decisions.

`producer_stage/lane` nie ustanawia trust.

---

# 157. Human approval events

Human approval jest canonical `ApprovalDecision`, nie luźnym JSON w folderze.

```text
approval_id
decision_type
scope
requested_action
actor_ref
actor_authority_ref
input_history_cut
related_refs[]
decision
reason
```

Waiver, scope exclusion, residual-risk acceptance i destructive/live action wymagają właściwej authority class.

---

# 158. Cleanup evidence

Cleanup Evidence wiąże experiment/execution i exact cleanup obligations.

`cleanup_result=PASS` wymaga observation path odpowiedniego do efektu. Brak cleanup evidence po destrukcyjnym/dynamic test może BLOCK dalszą pracę zależnie od policy.

---

# 159. Source integrity readback

Source Integrity Readback wskazuje actual subject baseline przed/po material execution:

```text
expected_source_generation_ref
observed_manifest_ref
observed_tree_ref optional
readback_method
result
```

Nie służy do „naprawy” source drift; drift jest osobnym blockerem/new source decision.

---

# 160. Mutation window records

Mutation Window Record oddziela:

```text
SUBJECT_BASELINE
EXECUTION_VARIANT
```

Mutation nie zmienia canonical SourceGeneration badanego produktu. ExecutionVariant opisuje chwilowo zmodyfikowany target, exact mutation ref, activation, cleanup i reset verification.

Evidence z mutant variant nie jest bezpośrednim evidence, że baseline ma defect; służy detector/oracle qualification zgodnie z experiment contract.

---

# 161. Supply-chain source distinction

Supply-chain source distinction musi być typowany:

```text
SUBJECT_SOURCE
BDB_APPLICATION_SOURCE
BUILD_TOOLCHAIN
EXECUTOR_TOOL
TEST_FIXTURE_SOURCE
```

Cross-reference validator nie pozwala użyć np. build dependency digest jako subject SourceGeneration identity.

---

# 162. Build provenance

Build provenance łączy:

```text
application source generation
builder_recipe_ref
builder_tool_ref
all declared input bytes
toolchain_runtime_profile_ref
deterministic settings
output RawDigest
independent rebuild result optional
```

Rebuild na innej niekwalifikowanej runtime może mieć odmienny wynik bez automatycznego stwierdzenia tampering; deterministic claim ma explicit platform scope.

---

# 163. Release outcome

Release qualification jest odrębną decision od audit termination.

Przykładowe outcome:

```text
TECHNICALLY_NOT_READY
QUALIFICATION_BLOCKED
READY_WITH_RESIDUAL_RISK
READY
```

Release decision wskazuje exact CampaignConclusion, SourceGeneration i product release policy. Audit STOP PASS nie może automatycznie ustawić `READY`.

---

# 164. Machine-readable report lineage

Machine-readable lineage report pokazuje exact:

```text
campaign
source generation
stage run revisions
canonical predecessor refs
auxiliary corpus refs
application generation per producer
policy/spec revisions
completion refs
```

Narracyjny diagram nie zastępuje tych refs.

---

# 165. Mixed-generation lineage

Mixed-generation lineage jest first-class:

```text
legacy E1 (application_generation=v1.4.4)
→ legacy E2 (application_generation=v1.4.4)
→ v2 E3 (application_generation=v2.x)
```

Każdy legacy edge wskazuje raw artifact + current admission assessment. Current protocol/policy upgrade działa od v2 bootstrap i nie jest retroaktywnie przypisywany historycznym runs.

---

# 166. Data contract testing

Data contract tests obejmują:

- golden BDB-CJSON-1 vectors,
- RawDigest/ObjectDigest distinction,
- typed ref valid/invalid cases,
- duplicate JSON keys,
- immutable revision identity,
- commit/head atomicity,
- idempotent commands,
- stale-head conflicts,
- schema compatibility,
- legacy admission fixtures.

---

# 167. Property tests dla kontraktów

Property tests kontraktów obejmują co najmniej:

- canonical encode/decode stability w dozwolonej domenie,
- reference closure,
- history chain continuity,
- command idempotency,
- projection rebuild equivalence,
- obligation invalidation propagation,
- FSM terminality/reopen rules,
- corpus role invariants.

---

# 168. Fuzzing schema parsers

Fuzzing parserów schemas/bundles obejmuje malformed JSON, duplicate keys, deep nesting, huge strings/arrays, Unicode edge cases, ZIP duplicates/path traversal, conflicting refs, hash manifest ambiguities i resource exhaustion.

Parser error nie może zmienić się w clean empty artifact.

---

# 169. Size limits

Size limits są częścią Runtime/Validator Resource Profile, nie magicznych globalnych constants.

Brak jawnych limitów dla untrusted external input = profile incomplete. Exceed = `RESOURCE_BLOCKED`/typed reject, nie partial success.

---

# 170. Resource limits walidatora

Validator Resource Profile obejmuje max object size, bundle size/member count, nesting depth, JSONL records, decompressed bytes, per-member size, recursion/graph traversal budget i time/memory constraints.

Partial validation po przekroczeniu limitu nie daje PASS.

---

# 171. Canonical hash manifest verification order

Verification order dla raw bundle:

```text
transport/read limits
→ ZIP/path/duplicate safety
→ BundleManifest parse under limits
→ raw member set
→ RawDigest verification
→ schema parse with duplicate-key rejection
→ typed refs/object digests
→ semantic/cross-artifact validation
```

Nie ufać manifestowi przed sprawdzeniem bezpiecznej składni i resource limits.

---

# 172. Fail-closed order

Fail-closed precedence:

1. resource/transport safety,
2. raw integrity,
3. schema,
4. typed reference closure,
5. source/policy/run binding,
6. authority/history cut,
7. exposure/knowledge eligibility,
8. evidence/obligation qualification,
9. stage/campaign gates.

Niższa warstwa failure nie może zostać przykryta przez wyższy-level warning.

---

# 173. Metadata-only reveal

Metadata-only reveal jest nadal **potential exposure**, jeśli metadata może przenosić semantykę.

View policy jawnie określa allowed:

```text
filenames
hashes
IDs
labels
counts
producer names
severity
dependency refs
resolver rights
```

Nie istnieje automatycznie „bezpieczna metadata”.

---

# 174. Claim quarantine storage

Claim Quarantine storage przechowuje raw claims w trusted vault, ale lane otrzymuje wyłącznie generated positive view.

Raw and view refs są odrębne. View resolver nie ma ambient dostępu do raw storage.

---

# 175. Corpus reveal hashes

Corpus reveal package wskazuje:

```text
source corpus snapshot ref
projection policy ref
view member refs
view RawDigests
grant decision ref
```

Hash view package nie dowodzi, że lane nie miał innych kanałów. Isolation qualification pozostaje osobnym assessment.

---

# 176. Stage completion artifact

Stage Completion jest immutable canonical decision na exact cut:

```text
stage_completion_id
stage_run_ref
stage_spec_ref
input_history_cut
required_lane_slot_results[]
required_output_refs[]
mandatory_obligation_summary
unresolved_material_refs[]
unknown_blocked_summary
completion_predicate_result
```

Nie zawiera globalnego STOP ani Final Assurance Case.

Materialny late result po completion nie mutuje tej decyzji; wymaga successor/reopen flow zgodnie z StageSpec/policy.

---

# 177. Lane completion artifact

Lane Completion:

```text
lane_completion_id
lane_run_ref
lane_spec_ref
input_history_cut
attempt_refs[]
final_knowledge_state_ref
required_output_refs[]
isolation_qualification_ref
contamination_assessment_refs[]
completion_predicate_result
```

Contribution summary jest derived i nie jest warunkiem truth.

---

# 178. Blocker record

`BLOCKER_LEDGER.jsonl` jest derived view z:

- unsatisfied mandatory obligations,
- BLOCKED/UNKNOWN assessments,
- invalidations,
- unresolved contradictions,
- admission/contract failures,
- resource blockers.

Canonical authority stanowią odpowiednie facts/decisions. Każdy blocker view wskazuje `as_of_head`.

---

# 179. Remediation separation

Remediation jest poza same-source audit stage progression. Stary source campaign może zostać concluded jako TECHNICALLY_NOT_READY; naprawa tworzy nową SourceGeneration i requalification.

Nie wolno użyć remediation result do retroaktywnego PASS old E5.

---

# 180. Audit vs qualification

Rozróżnia się co najmniej:

```text
AUDIT FINDING/CLAIM STATUS
STAGE COMPLETION
CAMPAIGN AUDIT TERMINATION
ASSURANCE CONCLUSION
PRODUCT RELEASE QUALIFICATION
```

Defekt może być CONFIRMED, campaign może poprawnie zakończyć audyt, a product release nadal być TECHNICALLY_NOT_READY.

---

# 181. Final consistency validator

Final Consistency Validator ma dwa jawne modes, żeby nie sprawdzać przyszłego objectu jak już zaakceptowanego faktu.

`PRE_CONCLUSION` działa na verified current head + proposed `ConcludeCampaign` command/body i sprawdza:

- canonical history chain/head i immutable object closure,
- schemas/object digests/source identity,
- Stage/Lane/Attempt FSM,
- predecessor/corpus admission,
- exposure/discovery cuts,
- obligation/evidence applicability,
- finding/root-cause/contradiction refs,
- wymagany candidate/challenger/STOP DAG dla danego termination context,
- residual risks oraz consistency proponowanego CampaignConclusion.

`POST_CONCLUSION_EXPORT` działa po accepted conclusion/final case/release decision i sprawdza:

- accepted `CampaignConclusion` against its StopEvaluation/context,
- `FinalAssuranceCase` closure i bounded/full-case rules,
- `ReleaseQualification` against FinalAssuranceCase, release policy i assessment basis,
- final report/bundle lineage, hashes i `as_of_head`.

Każdy mismatch jest fail-closed. PRE validator nie może udawać, że proponowany object jest już accepted; POST validator nie może używać proposed/stale bytes zamiast exact accepted refs. Nie wymaga E5 artifacts dla wcześniejszego StageCompletion.

---

# 182. Minimal machine authority set

Minimalny machine authority set dla **current native campaign**:

```text
CanonicalAcceptedHistory + AcceptedHead
ImmutableObjectStore closure
CampaignGenesis
SourceGeneration
Pinned Policy/Spec/Schema refs
Stage/Lane/Attempt accepted facts
Knowledge/Discovery accepted facts
Inventory/Invariant/CoverageObligation revisions
Observation/EvidenceQualification/Applicability facts
FindingClaimRevision + FindingAdjudication/RootCause/Contradiction decisions
StageCompletion records
Candidate Assurance Case + Challenger assignments/results when applicable
StopInput/StopEvaluation
CampaignConclusion
FinalAssuranceCase
ReleaseQualification optional
```

Nazwane ledgery/graphs/reports są derived exports.

Historyczne legacy raw artifacts są dodatkowym authority własnych exact bytes.

---

# 183. Dokumenty narracyjne

Dokumenty narracyjne nie są authority runtime state. Są versioned exports `as_of_head` i muszą wskazywać exact machine refs.

Jeżeli narracja jest sprzeczna z accepted facts, naprawia się narrację/export. Jeżeli accepted fact jest błędny, tworzy się superseding accepted decision — nie „poprawia” go tekst raportu.

---

# 184. Schema authority

Foundation contract authority składa się z:

1. niniejszej semantyki + zatwierdzonych ADR,
2. pinned semantic schema keys + `BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY.json`,
3. cross-artifact semantic validator rules,
4. pinned policy/spec revisions.

Na etapie **foundation freeze** `schema_ref` jest dokładnym, wersjonowanym semantic key kontraktu (`BDB_SCHEMA_REGISTRY::<kind>/<version>`). Nie twierdzimy jeszcze, że dla każdego przyszłego subsystemu istnieją finalne executable JSON Schema bytes. Przed **pierwszą runtime acceptance** danego wire kind implementacja MUSI związać semantic key z exact schema bytes + digest w accepted/pinned SchemaRegistry; brak takiego bindingu jest fail-closed `SCHEMA_BYTES_NOT_BOUND`. Związanie executable schema nie może zmienić zamrożonej semantyki bez nowej foundation revision.

`ArtifactContractRegistry` ma dwa jawne poziomy ref-closure:

- `EXPLICIT_COMPLETE` — dla krytycznych foundation kinds registry sam definiuje komplet materialnych typed refs, cardinalities, history-vs-content class oraz ordering potrzebny do freeze/reference-slice; ordering może obejmować osobny exact machine profile order-only precedence, ale taki profile nie rozszerza `material_refs` i nie może być interpretowany jako ukryta referencja;
- `SCHEMA_BOUND_BEFORE_FIRST_ACCEPTANCE` — dla pozostałych przyszłych rodzin registry jest semantycznym kind/role/lifecycle indexem; puste `material_refs` NIE oznacza „brak referencji”. Taki kind nie może zostać zaakceptowany runtime, dopóki exact executable schema/ref contract nie zostanie związany i zwalidowany.

Lista `foundation_inline_reference_contract_kinds` w registry wyznacza kinds, dla których `EXPLICIT_COMPLETE` jest obowiązkowe przed freeze. Conflict registry↔narrative/spec albo brak complete closure dla kind z tej listy blokuje freeze. Canonical kind używany przez foundation/reference-slice, a nieobecny w registry, jest fail-closed `UNREGISTERED_CONTRACT_KIND`.

Registry nie jest runtime state authority i nie może nadpisywać accepted history. JSON Schema sam nie definiuje trust modelu, transactionality, ordering, cross-source equality ani STOP precedence.

Conflict między tymi warstwami blokuje freeze contract bundle; README ranking nie legalizuje sprzeczności.

---

# 185. Cross-artifact rules

Cross-artifact rules obejmują m.in.:

- SourceGeneration equality/reconciliation,
- typed revision reference closure,
- commit chain/head monotonicity,
- object closure atomicity,
- command idempotency,
- FSM transitions/cardinality,
- gate/knowledge/discovery ordering,
- corpus role/admission,
- obligation/evidence applicability,
- invalidation propagation,
- candidate/challenger/STOP/finalization DAG,
- legacy raw/current assessment separation,
- build/runtime identity,
- **no-self-reference**: canonical object body nie zawiera własnego digestu, own accepting commit/head/event ref ani raw digest własnych bytes,
- duplicated convenience fields embedded alongside typed refs MUSZĄ być semantycznie równe referenced value albo validation fails,
- finalization copies (`assurance_level`, release assessment) nie mogą być sprzeczne z authoritative referenced evaluation.
- baseline `ReleaseQualification.result = referenced StopEvaluation.release_readiness` dla tego samego release policy/input cut; zmiana policy/input wymaga nowej release assessment, nie silent override.

Są versioned i testowane independent invalid fixtures.

---

# 186. Layered validation

Warstwy walidacji:

```text
L1 — transport/resource/ZIP safety
L2 — raw membership/RawDigest
L3 — schema + canonical object/ObjectDigest
L4 — typed referential integrity
L5 — source/policy/run/history-cut authority semantics
L6 — knowledge/corpus/evidence/obligation semantic qualification
L7 — stage/campaign/finalization contract
```

Wymagane layers zależą od ArtifactContract. `PASS` na L3 nie oznacza current admission ani authenticity.

---

# 187. Artifact contract registry

ArtifactContractRegistry wskazuje per typ:

```text
object_or_artifact_type
canonical_role = FACT | ASSESSMENT | DECISION | TRUST_ROOT | DERIVED_PROJECTION | RAW_EVIDENCE | EXPORT
schema_ref                         # frozen semantic schema key
identity_semantics
validation_profile / required_validation_layers
producer_authority
consumer/admission roles
lifecycle
reference_contract_mode = EXPLICIT_COMPLETE | SCHEMA_BOUND_BEFORE_FIRST_ACCEPTANCE
material_refs[]                    # required complete only for EXPLICIT_COMPLETE
ordering_rules                     # required complete when order is material
sensitivity                        # per-entry override albo registry default
version_compatibility              # per-entry override albo registry default
```

`DECISION` oznacza accepted scoped decision/authorization; `TRUST_ROOT` oznacza external pinned root potrzebny do bootstrapu i nigdy nie jest campaign runtime state authority.

`material_refs=[]` przy `EXPLICIT_COMPLETE` znaczy „ten contract nie ma materialnych refs”. `material_refs=[]` przy `SCHEMA_BOUND_BEFORE_FIRST_ACCEPTANCE` znaczy wyłącznie „field-level wiring nie jest dublowany w foundation registry”; przed pierwszą acceptance musi zostać związany exact executable schema/ref contract.

Registry posiada także typed `reference_target_classes` dla referencji, które nie są osobnymi canonical object kinds (np. accepted-head tag, raw artifact ref, history namespace pin). Każdy `allowed` target z `material_refs` MUSI rozwiązywać się do registered kind albo jawnej target class; dangling alias blokuje freeze.

`validation_profile` mapuje się deterministycznie na L1–L7. Epistemic/finalization contracts nie mogą pozostać tylko przy L3–L5, jeżeli ich własny kontrakt wymaga L6/L7.

To jawnie eliminuje niepewność, czy dany „ledger” jest authority czy tylko widokiem, bez fałszywego twierdzenia, że foundation registry zawiera już finalne executable schemas wszystkich przyszłych subsystemów.

---

## 187.1. Foundation baseline freeze decision — external governance record

Independent review MUST bind its verdict to exact candidate manifest bytes. Po `FOUNDATION_SPEC_BASELINE_READY` **nie edytuje się reviewed candidate bytes tylko po to, aby zmienić `PENDING/NO` na `PASS/YES`**. Taka edycja stworzyłaby nowy, nieprzejrzany corpus.

Efektywny freeze ustanawia osobny canonical immutable governance record `FOUNDATION_BASELINE_FREEZE_DECISION`, przechowywany poza reviewed candidate manifestem:

```text
foundation_freeze_decision_id
candidate_manifest_raw_digest
candidate_manifest_schema
independent_review_raw_digest
independent_review_verdict = FOUNDATION_SPEC_BASELINE_READY
reviewed_candidate_set_digest
baseline_id
governance_actor_ref
decision = FREEZE
reason_codes[]
created_at informational
```

Walidator freeze MUSI sprawdzić:

1. `candidate_manifest_raw_digest` wskazuje dokładnie manifest badany przez independent review,
2. `reviewed_candidate_set_digest` odpowiada exact ordered file/hash set z manifestu,
3. `independent_review_raw_digest` wskazuje immutable review bytes,
4. review deklaruje `FOUNDATION_SPEC_BASELINE_READY` dla tego samego manifestu,
5. nie istnieje późniejsza normatywna zmiana candidate bytes,
6. governance actor ma authority do freeze.

`FOUNDATION_SPEC_BASELINE_FROZEN` jest po independent review **derived governance state** z ważnego FreezeDecision + exact reviewed manifest, a nie mutable flagą wewnątrz reviewed README. Candidate README/manifest może historycznie pozostać `PENDING/NO`; nie jest to konflikt po powstaniu valid external FreezeDecision.

FreezeDecision nie jest runtime campaign history authority i nie może zmieniać żadnego accepted campaign fact.

## 187.2. Author baseline qualification — corrected external record/2

R5.4.1 owner-approved governance correction. This section and the exact executable
`governance/AuthorBaselineQualificationRecord__2.schema.json` define the ONE external
`AuthorBaselineQualificationRecord/2` body. §192.2 refers to this definition.
It is outside campaign history, NOT a canonical Registry kind or runtime capability.
The schema is a machine candidate artifact; instance records, readback, self-audit,
owner decisions and invalidations are external to both candidate-set preimages.

Required fields (closed schema; no aliases):

```text
record_type = AuthorBaselineQualificationRecord/2
status = VALID_AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE
author_baseline_qualification_id
normative_candidate_set_digest
machine_candidate_set_digest
candidate_manifest_raw_digest
candidate_manifest_schema = BDB_AUDIT_V2_R5_4_PACKAGE_MANIFEST/1
candidate_manifest_storage_id
self_audit_report_raw_digest
final_reaudit_register_storage_id
final_reaudit_register_raw_digest
readback_storage_provider = LOCAL_FILESYSTEM
readback_storage_id
readback_raw_digest
readback_verified_normative_file_count
readback_verified_machine_file_count
readback_verified_total_file_count
readback_mismatch_count = 0
readback_entries[] # group, file, stable_storage_id, expected_raw_digest,
                   # observed_raw_digest, byte_length, result=PASS
author_verdict = R5_4_AUTHOR_NORMATIVE_FINAL_SELF_AUDIT_PASS
owner_assurance_decision = IMPLEMENTATION_MAY_PROCEED_UNDER_AUTHOR_ONLY_ASSURANCE
governance_actor_ref
owner_decision_storage_id
owner_decision_raw_digest
registry_id
registry_raw_digest
artifact_contract_registry_ref
golden_vector_set_id
golden_vector_set_raw_digest
schema_registry_ref
qualification_scope
independent_assurance = false
foundation_spec_baseline_frozen = false
reason_codes[]
created_at # informational; never ordering/authority
```

The exact external contract descriptor `governance/GOVERNANCE_CONTRACT.json` pins
schema RawDigest, byte length, $id, dialect and dependency closure. Existing
SchemaRegistry/2 remains exclusively canonical runtime authority; it does not
register this external governance record. Author verdict is the single scalar
above, never an array or an alternative token. /1 historical records are unchanged.

The manifest /1 format is inherited; revision metadata is R5.4.1. Its
`normative_candidate_files` and `machine_candidate_files` arrays are the normative
and machine candidate entries respectively. Derive counts from these EXACT arrays:
normative count = len(normative_candidate_files); machine count = len(machine_candidate_files);
total count = normative count + machine count = len(readback_entries).
There are no universal numeric count constants. Unique (group,file) membership
must equal the manifest, with no duplicates, omitted/extra provenance files or
wrong group. expected/observed RawDigest and byte length must equal actual immutable
candidate bytes and manifest entries; stable_storage_id must resolve that exact file.
Both set digests use inherited sorted [{file,bytes,sha256}] CJSON SHA256 preimages.

self_audit_report_raw_digest == final_reaudit_register_raw_digest identifies the
same final external JSON author audit. Preserve its stable storage identity.
Readback digest/storage, Registry/Golden raw hashes and exact canonical root refs
must resolve consistently. No self-audit, qualification, invalidation or owner
decision instance may enter its own candidate-set preimage.

Fresh Q1 validates schema AND all semantic/hash/storage predicates, final audit
and readback for this manifest, and direct human owner authority accepting author-only
risk for this successor correction. Design approval alone is insufficient. In this
task the explicit correction-and-fresh-Q1 order authorizes the minimal successor
and a NEW record after successful checks; the prior explicit author-only risk
acceptance is retained as human provenance, never as a reused qualification PASS.
Any expanded delta requires a new decision. The invalid R5.4 record stays excluded
by its preserved external invalidation as NO_VALID_QUALIFICATION.

Effective AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE=YES is derived ONLY after all
checks pass; it is not a self-authenticating field in the record. Candidate pending
flags remain historical preparation metadata. No independent freeze, runtime PASS,
release qualification or NF02 closure follows. Q2 and N5–N11 remain separate tasks.

---

# 188. Contract evolution

Contract evolution:

```text
old artifact → parse/validate with pinned old adapter
current assessment → new immutable object
new artifact → new schema/contract
```

Nie wolno silent semantic auto-upgrade.

Breaking contract revision określa migration/admission behavior i nie zmienia znaczenia już accepted history facts.

---

# 189. Compatibility fixtures as contracts

Compatibility fixture jest contract vector z dwoma niezależnymi expectations:

```text
legacy_observed_result
independent_safe_expected_result
```

oraz known legacy bug/hardening/exception metadata.

Preservation i correctness są raportowane osobno. 100% zgodności z v1 nie dowodzi validator correctness, jeśli oba implementują ten sam błąd.

---

# 190. Definition of Done — Data Contracts

Data Contracts są gotowe do freeze, gdy co najmniej:

1. BDB-CJSON-1 + RawDigest/ObjectDigest mają golden/negative vectors.
2. Logical ID vs revision i typed refs są jednoznaczne.
3. SourceIdentity equality/reconciliation ma valid/conflict fixtures.
4. Canonical history ma atomic commit/head/idempotency/crash tests.
5. Projections można usunąć i odbudować bez zmiany gates.
6. Knowledge isolation/exposure/discovery mają exact cut i contamination tests.
7. Inventory rozlicza assigned inputs, unsupported/unknown scope i late surfaces.
8. Coverage Obligations są authority; D0–D5 jest derived.
9. Evidence independence/applicability są claim-relative i mają invalidation propagation.
10. Finding/root-cause/contradiction membership/reopen rules są versioned.
11. Oracle challenge ma activation + 2×2 contrast.
12. STOP ma complete precedence dla UNKNOWN/BLOCKED/INSUFFICIENT_DATA/N/A/WAIVER/INVALIDATED/contradictions.
13. StageCompletion ≠ CampaignConclusion ≠ ReleaseQualification.
14. Candidate→challengers→STOP→CampaignConclusion→FinalAssuranceCase jest acykliczne.
15. Legacy L0–L5, exposure confidence i cases A/B/C są jednoznaczne.
16. Preservation i validator correctness mają oddzielne compatibility fixtures/gates.
17. Build/runtime closure i standalone claim mają exact scope.
18. Final consistency/reference suite obejmuje happy path i foundation failure paths.

---

# 191. Finalna zasada

BDB Audit v2 powinno machine-readable odpowiedzieć co najmniej:

```text
Jaki exact SourceGeneration audytowano i pod jaką policy/spec revision?
Jaki accepted head/history cut obowiązywał decyzję?
Który executor/lane/attempt miał jakie kwalifikowane kanały i potential exposures?
Czy discovery zostało zaakceptowane przed reveal?
Jaki dokładny Coverage Obligation był testowany?
Jakie observations powstały i jakie mają wspólne dependencies/oracles?
Czy evidence jest ACTIVE i niezależne względem konkretnego failure assumption?
Która FindingClaimRevision i w jakim scope jest wspierana?
Które root-cause memberships/contradictions są current?
Jakie UNKNOWN/BLOCKED/WAIVED/unsupported scope pozostały?
Dlaczego StageCompletion przeszedł lub został zablokowany?
Dlaczego STOP zwrócił CONTINUE/E6/BLOCKED/PASS?
Czy CampaignConclusion różni się od Product Release Qualification?
Czy cały current state można odtworzyć po usunięciu projections?
```

Jeżeli odpowiedź wymaga zaufania do filename, UI, stale snapshotu, narracji albo drugiego mutable ledger head, kontrakt foundation jest niewystarczający.

To jest docelowa semantyka BDB Audit v2 Data & Artifact Contracts po Design Closure C01–C21. Na foundation baseline zamrażane są semantic wire-schema contracts/keys, BDB-CJSON-1 golden vectors i policy/profile semantics. Exact executable schema bytes + digest dla danego wire kind MUSZĄ zostać związane z tym zamrożonym semantic key i zwalidowane fail-closed **przed pierwszą runtime acceptance tego kindu**; nie jest wymagane fabrykowanie finalnych executable schema bytes dla każdego przyszłego subsystemu przed rozpoczęciem implementacji, ale implementacja nie może przez późniejszy schema binding zmienić zamrożonej semantyki bez nowej foundation revision.

---


# 192. R5.4 NF02 normative successor contract

### D.2. R5.4 canonical Registry contracts

Poniższe są normatywne complete rows tej R5.4 candidate; nie modyfikują R5.3. Każdy nowy row ma consumers COORDINATOR/VALIDATOR/STORE, lifecycle IMMUTABLE, exact version string, ObjectDigest według ADR-006. Generic object envelope/schema identity obowiązuje również gdy nie powtórzono go w domain body. Logical IDs zachowują dokładną gramatykę ADR §5: `<wire kind>_<uuidv4-lowercase>`. `binding_id` używa `assignment_package_binding_...`, `admission_evidence_id` używa `lane_result_admission_evidence_...`, `lane_result_id` używa `bdb_audit_lane_result_...`, a `schema_registry_id` używa `schema_registry_...`; nie dodaje się krótkich prefix aliases ani nowego algorytmu IDs.

| Pole kontraktu | assignment_package_binding/1 | lane_result_admission_evidence/2 | bdb_audit_lane_result/2 |
| --- | --- | --- | --- |
| kind | assignment_package_binding | lane_result_admission_evidence | bdb_audit_lane_result |
| version | 1 | 2 | 2 |
| canonical_role | FACT | FACT | FACT |
| lifecycle | IMMUTABLE, single binding per exact assignment | IMMUTABLE, one admitted raw per exact assignment/result slot | IMMUTABLE, one accepted payload per exact result slot |
| authoritative_for | exact raw package authorized for one exact accepted assignment | trusted admission of exact result raw for assignment, binding and slot; no truth qualification | exact normalized external result content and provenance for accepted slot; no truth qualification |
| producer_authority | TRUSTED_COORDINATOR_ACCEPTANCE | TRUSTED_COORDINATOR_ACCEPTANCE | TRUSTED_COORDINATOR_ACCEPTANCE |
| schema_ref | BDB_SCHEMA_REGISTRY::assignment_package_binding/1 | BDB_SCHEMA_REGISTRY::lane_result_admission_evidence/2 | BDB_SCHEMA_REGISTRY::bdb_audit_lane_result/2 |
| validation_profile | NF02_PROVENANCE | NF02_PROVENANCE | NF02_PROVENANCE |
| reference_contract_mode | EXPLICIT_COMPLETE | EXPLICIT_COMPLETE | EXPLICIT_COMPLETE |
| required_validation_layers | L1,L2,L3,L4,L5,L6 | L1,L2,L3,L4,L5,L6 | L1,L2,L3,L4,L5,L6 |
| ordering rules | no domain ref arrays; exact body canonicalization | no domain ref arrays; exact body canonicalization | payload findings sequence preserves transport order; object/map keys CJSON; typed reference sets use Registry default exact-ref order/duplicate rejection |
| first-acceptance rule | governing R5.4 Registry + exact schema binding; prior assignment; raw durable; no prior start/delivery | same schema authority; prior binding/assignment/STARTED; raw result durable; trusted rederivation | same schema authority; prior accepted evidence; exact rederived payload; correct open result slot/FSM |

Domain bodies are closed (`additionalProperties=false`). Forbidden copies/secret fields są odrzucane, nie ignorowane. Schemas definiują raw/TypedRef shapes i finite payload contract, a cross validators obsługują resolved authority i predicates.

#### D.2.1. assignment_package_binding/1

```text
binding_id
assignment_ref
binding_input_history_cut
package_raw_ref
```

| material_refs field | Cardinality | Target | Reference class | Additional constraint |
| --- | --- | --- | --- | --- |
| assignment_ref | 1 | assignment_manifest/1 | PRIOR_ACCEPTED_ONLY | exact prior accepted revision on binding input cut; same campaign namespace |
| binding_input_history_cut | 1 | history_cut | HISTORY_INPUT | exact command input/expected parent; non-EMPTY; includes assignment |
| package_raw_ref | 1 | raw_artifact_ref | CONTENT_OBJECT | exact durable raw content prerequisite; reuse prior retained raw explicitly allowed, never workspace path |
| package_raw_ref.artifact_contract_ref | 1 | external_profile_ref | PINNED_PROFILE_REF | exact NF02_INPUT_PACKAGE_TRANSPORT_V2 pin selected by governing R5.4 context, not package claim |

RawRef scalar constraints: lowercase SHA256 raw_digest, exact nonnegative byte_length (package ZIP nonempty), media_type=`application/zip`. Nested artifact contract pin is part of the complete material-ref inventory. Package context must equal resolved assignment context. At binding input cut the resolved Attempt MUST be CREATED, assignment eligible/active, source/lane/stage context lawful, and all grants/knowledge/isolation prerequisites valid; cancelled, superseded, failed, already started or completed execution cannot acquire a new binding. Full cross-object rules and uniqueness: E.1–E.4.

#### D.2.2. lane_result_admission_evidence/2

```text
admission_evidence_id
assignment_ref
package_binding_ref
result_slot_contract_ref
admission_input_history_cut
result_raw_ref
```

| material_refs field | Cardinality | Target | Reference class | Additional constraint |
| --- | --- | --- | --- | --- |
| assignment_ref | 1 | assignment_manifest/1 | PRIOR_ACCEPTED_ONLY | equal binding.assignment_ref; cannot select by logical ID |
| package_binding_ref | 1 | assignment_package_binding/1 | PRIOR_ACCEPTED_ONLY | unique binding accepted on admission cut, preceding AttemptStarted/delivery authorization |
| result_slot_contract_ref | 1 | result_slot_contract_ref | PINNED_PROFILE_REF | exact one of assignment.result_slot_contract_refs, active under assignment governing context |
| admission_input_history_cut | 1 | history_cut | HISTORY_INPUT | exact current command input, non-EMPTY, includes prior assignment, binding and accepted STARTED transition |
| result_raw_ref | 1 | raw_artifact_ref | CONTENT_OBJECT | exact result ZIP verified/retained atomically with accepted reference; explicit reuse of identical prior retained raw allowed |
| result_raw_ref.artifact_contract_ref | 1 | external_profile_ref | PINNED_PROFILE_REF | exact NF02_RESULT_TRANSPORT_V2 / slot transport pin |

Slot ref neredundant: assignment may declare more than one slot; evidence selects the one admitted slot, rather than inventing a global one-result-per-lane shortcut. NF02 supported external lane slot must be explicitly declared; an empty assignment slot set cannot admit a result. External raw carries exact assignment and package-binding claims; any claim mismatch rejects before evidence acceptance. No capability/token, result_proposal_digest, copied attempt/source/raw scalars or cached package checksum in accepted evidence.

#### D.2.3. bdb_audit_lane_result/2

```text
lane_result_id
admission_evidence_ref
result_input_history_cut
result_payload
```

| material_refs field | Cardinality | Target | Reference class | Additional constraint |
| --- | --- | --- | --- | --- |
| admission_evidence_ref | 1 | lane_result_admission_evidence/2 | PRIOR_ACCEPTED_ONLY | exact evidence accepted before result command input |
| result_input_history_cut | 1 | history_cut | HISTORY_INPUT | exact command input/expected parent, non-EMPTY; includes evidence and lawful result-received state |

`result_payload` is the deterministic domain payload `{findings: [...], outputs: {...}, notes: string|null}` from retained result raw and exact slot/normalizer. Required keys are present even when arrays/maps are empty; count is derived. Schemas/slot profile close finding and output shapes. NF02 payload embeds **no material TypedRef**: files/evidence paths address members of result_raw_ref, and finding/evidence qualification objects are accepted subsequently under their existing contracts. If a slot needs material canonical refs in a future result payload, that requires an explicit successor row/schema/vector delta; an untyped arbitrary dict is not permission to smuggle refs.

Transport assertion metadata is retained in raw. It is checked against accepted context but not copied into competing authority fields. Result payload must equal `Normalize(result_raw_ref, exact slot profile)` byte-for-byte after BDB-CJSON-1; body logical ID/ref/cut are assigned by the trusted acceptance operation. A checksum of caller-supplied proposal is insufficient. Attempt/slot uniqueness and completion gates cannot be bypassed by generic command.

`NF02_PROVENANCE=[L1,L2,L3,L4,L5,L6]` is a **new named validation profile**, explicitly added to R5.4 Registry, not a new canonical kind or role. It combines raw/container validation, digest, schema, references/history/source, authority/FSM and knowledge/isolation checks. L7 remains required in LaneCompletion/StageCompletion/STOP and any existing downstream profile; admission does not satisfy it automatically.

### D.3. SchemaRegistry successor contract and bootstrap

Define `schema_registry/2` as an additional **version of an existing canonical kind**, with:

```text
schema_registry_id
artifact_contract_registry_ref
serialization_profile_ref
validator_profile_ref
compatibility_rules_ref
bindings[] = { schema_key, schema_raw_ref, status }
```

Contract: FACT; IMMUTABLE; authoritative_for exact semantic-key -> executable bytes mapping under one exact ArtifactContractRegistry; producer_authority TRUSTED_COORDINATOR_ACCEPTANCE, with construction/install authorization from existing authorized foundation governance and LOCAL_PINNED root; schema_ref `BDB_SCHEMA_REGISTRY::schema_registry/2`; EXPLICIT_COMPLETE; NF02_PROVENANCE/L1–L6. Installation activation additionally enforces existing governance requirements; this FACT does not grant governance authority.

| material_refs | Cardinality | Target / class |
| --- | --- | --- |
| artifact_contract_registry_ref | 1 | artifact_contract_registry; PINNED_PROFILE_REF; approved exact successor revision |
| serialization_profile_ref | 1 | serialization_profile_pin; PINNED_PROFILE_REF; unchanged ADR-006 profile |
| validator_profile_ref | 1 | external_profile_ref; PINNED_PROFILE_REF; exact offline dialect/backend/formats/normalizer dependency profile |
| compatibility_rules_ref | 1 | external_profile_ref; PINNED_PROFILE_REF; R5.4 no-in-place-upgrade rule |
| bindings[].schema_raw_ref | 1 per binding, bindings 1..N | raw_artifact_ref; CONTENT_OBJECT; earlier durable content or explicitly reusable retained bytes |
| bindings[].schema_raw_ref.artifact_contract_ref | 1 per binding | external_profile_ref; PINNED_PROFILE_REF; exact executable JSON-schema raw contract |

Bindings sort by semantic key's UTF-8 bytes, with duplicate key rejection; all entries `status=ACTIVE`. Kind/version are derived exactly from key `BDB_SCHEMA_REGISTRY::<wire kind>/<version>`, must resolve to the approved Registry row and agree with executable schema identifier. `schema_id`, `artifact_or_object_type` and `schema_revision_digest` from Data §95 become derived accessors: the last is explicitly **RawDigest(schema bytes)**, not this SchemaRegistry's ObjectDigest. No new unregistered `json_schema` ObjectDigest domain is introduced. RawDigest validates exact executable bytes; **ObjectDigest(schema_registry,2,body)** identifies the canonical binding set. Normative JSON file's RawDigest and registered artifact_contract_registry object identity, if materialized, are recorded separately and must map deterministically.

Closed exact lifecycle (N1–N4), with separate semantic approval and runtime activation:

1. Owner approves R5.4 delta/model. Produce complete successor normative candidate, Registry/Golden, provenance manifest and self-audit. Preserve all predecessor bytes. Perform exact readback. Apply existing governance: author-qualified implementation baseline requires external authorized qualification record; independent foundation freeze requires independent READY plus exact external freeze decision. Do not relabel author-only as independent.
2. Freeze successor ArtifactContractRegistry exact bytes and digest; all three NF02 new kinds plus schema_registry/2, versions/profile/ref parity are known before schema production. No post-freeze runtime extension.
3. Generate executable schemas as **build-time candidates**, verify semantics/parity/fixtures, then freeze their exact files. Record RawDigest, byte_length, media type, `$id`, dialect and exact schema-dependency closure. Python may produce candidate bytes here; runtime Python dict is never binding authority.
4. Construct SchemaRegistry/2 over those exact raw refs and exact approved Registry/profile refs. Calculate its canonical ObjectDigest. Preserve raw schema bytes as installation content. Unknown kinds cannot obtain entries; every kind reachable by a first accepted closure has a bound exact schema, including bootstrap command/history/profile/schema-registry objects, not only NF02 rows.
5. Authorized installation operation pins exact SchemaRegistry/2 and exact R5.4 normative/Registry identities in a new exact **revision of installation_bootstrap_profile/1**. Preserve the eight existing material pins and allowed initialization command; do not change predecessor pin bytes or add actor self-authorization. Approval/readback record is outside candidate preimage.
6. Bootstrap verification has an explicit external schema root: the installed immutable bootstrap bundle supplies the exact executable schema for `schema_registry/2` (and bootstrap validation prerequisites) by raw digest **before** validating this registry. The registry may list that schema's raw ref; schema bytes do not contain the owning SchemaRegistry digest or future campaign head. Resolver validates these external pins first and resolves entries against them. A registry cannot validate or authorize itself from a caller-provided `$id`.
7. New history `seq=1`, EMPTY_HISTORY and existing `INITIALIZE_CAMPAIGN_FROM_LEGACY` use this exact installation profile, qualified admission chain and one existing union-DAG sort. Initial context establishes the exact schema/policy/spec set. Thereafter schema authority is resolved from that campaign's accepted/pinned context, never latest installed files.
8. Allow new runtime kinds only in this legally initialized R5.4 campaign when semantic registration, schema bytes/digest, exact SchemaRegistry binding, actor authority and all object predicates pass. Missing/changed schema rejects before canonical state mutation. A copy of SchemaRegistry JSON on disk is not activation.

No new generic schema-upgrade command is introduced. Installing an R5.4 bundle affects **new** campaigns only; old campaigns retain their exact old schema set. A future in-place transition would require a separately approved admission/activation decision, governing prior cut, old-policy validation, next-command boundary and in-flight run rules. None is currently specified here, so this task chooses **NO**.

## E. C2 — Package binding decision

### E.1. Minimality and uniqueness

Accepted **AssignmentPackageBinding/1** is the sole package authorization authority. Its four-field domain body is in D.2.1. RawRef already includes raw_digest and byte_length; separate package_raw_digest/package_size_bytes duplicate identity and are omitted. Attempt/source/executor/delivery refs are derived through exact assignment_ref. `package_manifest_ref|null` is omitted: embedded manifest is an untrusted transport member checked against assignment, not a second accepted package authority. Semantic checksum is derived from bound bytes under a pinned profile, so no stored duplicate checksum or package semantic object is required.

`binding_id` provides typed object identity under the existing ID grammar; it is not the unique-selector key. Selector key is **full exact assignment TypedRef identity** within canonical history namespace. Index is rebuildable, not authority. State at cut:

```text
0 accepted bindings: package not authorized; start/delivery/admission forbidden
1 accepted binding: only its exact retained raw bytes may be delivered
second nonidentical binding: CONFLICT / REJECT, no canonical state mutation
exact binding + exact command retry: same original acceptance/receipt, no new effects
```

Different binding_id, different input cut or different body for the same assignment is not exact retry, even if RawDigest happens to match. Return/use the existing binding rather than minting a second fact. A repeated request under a new command ID for an already exact bound fact must return original binding/receipt through the operation's idempotency resolution, without accepting another command/fact. Same command ID with changed digest is ID_REUSE_CONFLICT. Same expected parent competing transactions have one CAS winner; loser re-resolves accepted state and either returns exact existing result or conflicts. Different bytes cannot be selected by time, path, cache or latest ID.

Package replacement requires a new legal execution retry: new Attempt and accepted AssignmentManifest, with retry refs/reason under the existing FSM. Cancellation/supersession never erases old binding. There is no mutable binding revision or invalidation that authorizes different bytes for the old assignment.

### E.2. Cross-object equalities and validation context

`EqRef` compares complete authoritative typed identity (kind, logical ID when defined, revision_digest, digest profile and schema revision identity) following ADR/typed contract. Field reference class is validation metadata, not a license to change target identity. Resolving a ref includes accepted membership on the required cut, not just finding content in storage.

Let A = resolved binding.assignment_ref; B = unique accepted binding; E = evidence; R = result. Define **derived accessors**, not duplicate stored fields:

```text
B.attempt_ref := A.attempt_ref
B.source_generation_ref := A.source_generation_ref
E.attempt_ref := resolved E.assignment_ref.attempt_ref
E.source_generation_ref := resolved E.assignment_ref.source_generation_ref

EqRef(B.assignment_ref, E.assignment_ref)
EqRef(B.attempt_ref, A.attempt_ref, E.attempt_ref)
EqRef(B.source_generation_ref, A.source_generation_ref, E.source_generation_ref)
E.package_binding_ref resolves to unique accepted B on E.admission_input_history_cut
R.admission_evidence_ref resolves to exact prior accepted E on R.result_input_history_cut
RawDigest(ReadDurable(B.package_raw_ref)) == B.package_raw_ref.raw_digest
len(ReadDurable(B.package_raw_ref)) == B.package_raw_ref.byte_length
RawDigest(ReadDurable(E.result_raw_ref)) == E.result_raw_ref.raw_digest
len(ReadDurable(E.result_raw_ref)) == E.result_raw_ref.byte_length
E.result_slot_contract_ref is exact member of A.result_slot_contract_refs
R.result_payload == Normalize(ReadDurable(E.result_raw_ref), exact slot/normalizer)
```

Campaign, StageRun, LaneRun, lane/stage/spec/source, executor/delivery and knowledge/grant/view identities must resolve consistently through A -> Attempt -> LaneRun -> StageRun and A's exact refs, with matching campaign namespace and all preexisting equality rules. Claimed transport assignment/attempt/source/cut/profile/model/slot must match this resolved context. Caller claims cannot establish it. Allowed runtime executor model must be the one prescribed by the pinned executor profile; generic label equality with another untrusted claim is insufficient.

Three input cuts are distinct: assignment_input_history_cut freezes execution context; binding_input_history_cut is the later input containing accepted A; admission_input_history_cut includes B and STARTED; result_input_history_cut includes accepted E. Do not substitute the assignment cut for current admission cut or synthesize acceptance provenance inside any body. Governing profiles for assignment interpretation remain its pinned context; operation/FSM admission predicates derive from the exact current accepted command input under the same R5.4 campaign.

### E.3. Raw identity and optional semantic identity

Raw authorization is always exact bytes, independent of whether the application displays a semantic checksum. In R5.4 the existing package_digest concept is formally typed as **`PackageSemanticDigest` under external `NF02_PACKAGE_SEMANTIC_PROFILE_V1`**, distinct from RawDigest and ObjectDigest. It is not an invented registered kind. Existing helper outputs are pre-revision implementation checksums, not grandfathered normative package identity.

Freeze the following external profile/transport rule in R5.4:

1. Validate safe ZIP structure and every payload member against transport/assignment grants/views. Normalize member paths exactly according to the existing safe transport profile; reject collisions, duplicates, unsafe names/symlinks and quota violations. Manifest member is exactly `MANIFEST.json`.
2. Parse manifest with duplicate-key rejection and BDB-CJSON-1 compatible values. Manifest context contains exact accepted assignment_ref and its required derived claims. It contains no final ZIP RawDigest, binding ref, accepting commit or future STARTED ref. It may contain one tagged semantic checksum field.
3. Form `M` by removing only `package_semantic_digest` from the parsed manifest. Form `members[]` for **every other delivered member**, sorted by normalized path's UTF-8 bytes, with `{path, raw_digest, byte_length, media_type}`. Digest/length come from actual member bytes; media_type comes from a fixed mapping in the pinned transport profile, never MIME sniffing, host defaults or a caller claim. Embedded member list/count/hash assertions must exactly equal this computed set. A hash-list member may not introduce a dependency on MANIFEST's semantic checksum or the final ZIP hash; such a format is rejected at construction/validation.
4. Descriptor is `{profile_ref: exact external semantic profile pin, manifest: M, members: [...]}`. Semantic value is SHA256(BDB-CJSON-1(descriptor)). Tagged representation is `{profile_ref, digest}`; the expected profile comes from governing R5.4 transport/spec pins, never the manifest's choice. This is a profile-defined checksum, **not BDB-OBJECT-DIGEST-1**. Freeze profile bytes and known-answer vectors in N1–N3.
5. Insert computed tagged checksum in manifest, finalize ZIP, then compute RawDigest(final ZIP bytes). Validator independently rederives the semantic value from the **bound retained raw package**, checks embedded checksum and any result assertion. Canonical binding need not duplicate it.

Repacking identical members can yield same semantic value and different RawDigest. The second ZIP is still unauthorized for that assignment. Changing any delivered prompt/source/template/member or manifest context changes semantic identity; changing ZIP representation can change only raw identity. An external result's input_package_digest is only a checked assertion. Evidence validator derives expected package identity from B, not incoming result or cached job.

This checksum uses the existing CJSON serialization and SHA256 primitive; it does not change ObjectDigest/RawDigest algorithms, TypedRef equality or ADR-006. No new canonical descriptor object, bundle_manifest kind or package manifest authority is introduced.

### E.4. Generation, acceptance, FSM and delivery

Normative sequence, including persistence boundary:

1. Accept A with legal prior/pinned context; required grants, potential exposure and knowledge facts satisfy their existing DAG. A may be accepted in the legal Attempt/Knowledge closure; it is **prior accepted** to all later binding operations.
2. Construct package only from exact accepted A and exact assigned context. Building does not grant exposure access beyond those grants. Freeze prompt/templates/views/source members and validate package against that context; mutable workspace is an input staging source, never final authority.
3. Finalize package bytes, compute semantic checksum as above and final RawDigest. Persist immutable content-addressed bytes, verify digest/length and readable durability. Staging raw alone neither moves history nor authorizes delivery.
4. Construct B with current binding_input_history_cut containing A. `BIND_ASSIGNMENT_PACKAGE` operation authenticates existing actor, enforces uniqueness/FSM/source/profile/knowledge/package validation, CAS and atomic durable raw-reference/history acceptance. A remains immutable. Raw staging failures, partial commits and conflicts cannot yield accepted B without readable exact bytes.
5. Reopen/read retained B.package_raw_ref and verify exact raw identity after acceptance. Missing/corrupt bytes blocks start/delivery. Do not quietly regenerate a semantically similar ZIP or substitute workspace copy.
6. **AttemptStarted MUST be accepted after B, in a separate subsequent commit**. It requires prior accepted A/B, CREATED eligible Attempt, active lane/source/context and existing grants/isolation obligations. Its transition command payload names the exact package_binding_ref; that is PRIOR_ACCEPTED_ONLY, with current HISTORY_INPUT and governing FSM HISTORY_CONTEXT_BINDING. Use existing command_envelope and generic transition/event mechanism, not a new AttemptStarted object kind. No new FSM state is needed. R5.4 transition-profile revision adds the guard; prior profile bytes remain unchanged.
7. Only after this accepted transition may the delivery adapter expose package bytes to executor. It resolves B from accepted history and reads **those bytes from durable raw storage**, rechecking integrity and terminal/source authorization before release. A copy may be materialized atomically and rechecked; mutable pathname never selects content. Delivery profile must specify a serialized/revalidated authorization boundary so a concurrent terminal transition cannot enable a stale delivery request. Potential exposure remains conservative once delivery was possible.
8. Transport envelope outside the already-finalized package may carry binding_ref and authorized STARTED ref. Package itself does not contain them; no package rebuild after binding. Retransmission sends identical raw under the same assignment; re-execution/retry after terminal Attempt creates new Attempt/Assignment under existing retry rules.
9. External result transport asserts exact assignment/binding and slot. Trusted ingestion rederives context from A/B, validates actual raw and admitted slot, and accepts E atomically with retention. Illegal terminal result follows existing QUARANTINED_LATE_RESULT handling, not false accepted current result; adversarial rejection of a proposed canonical fact leaves canonical state unchanged.
10. Accept R in a later commit with PRIOR_ACCEPTED_ONLY evidence ref and legal RESULT_RECEIVED -> RESULT_ACCEPTED FSM effect. Evidence-only ingest may establish the ordinary received transition according to explicit R5.4 operation event profile; no result acceptance before evidence. LaneCompletion and StageCompletion remain distinct subsequent qualification decisions/facts with existing predicates.

Rejected alternatives for AttemptStarted: before binding cannot prove input was frozen/authorized; same commit cannot meet B's prior boundary and complicates durable readback before external effect. The chosen separate commit adds one explicit temporal boundary and uses existing accepted-history CAS.

### E.5. Bound versus actually delivered

B proves **which exact package bytes were authorized for this assignment**, not that an executor received/read/executed them. STARTED proves authorized lifecycle transition, not a fabricated delivery ACK. `DeliveryObserved` is an optional observation/projection in the existing architecture; no registered canonical `delivery_receipt` exists in the active 110-row Registry. `CommandReceipt` acknowledges canonical command acceptance; report_export_receipt concerns report export. Neither proves delivery.

NF02 minimum needs authorized package proof and enforced pre-delivery boundary. Do not add DeliveryReceipt kind. A delivery profile may retain ordinary adapter diagnostics or existing optional observations/ACK with explicit limited claim; canonical disclosure/exposure semantics remain the existing grant/PotentialExposure rules. A future requirement to prove actual receipt would need its own approved contract and vectors. Report/evidence must say “authorized package” unless actual delivery is separately evidenced.

### E.6. Capability and raw retention

Current private-key/HMAC capability issuance checks prior refs and raw derivation; durable key and token live in the remediation. That is an implementation enforcement primitive, not new semantic authority. In /2 the trusted Store operation either derives evidence itself from accepted A/B/raw or validates an authenticated call/capability scoped to exact campaign/assignment/B/slot/result raw/current authorization. A caller choosing command_kind or serializing trusted=true cannot mint it.

Capability/token must remain outside canonical body/digest and ordinary exported history. Expiry, replay, revocation and key rotation are runtime policy; accepted provenance survives process restart and key rotation through exact facts/raw. Canonical read/replay validates schema, accepted identities, raw and producer acceptance provenance, not possession of an old process token. New writes always recheck current actor/FSM authority. No secret is an accepted fact, and no evidence boolean establishes trust.

Accepted package/result raw and required embedded evidence members must remain retrievable for replay, completion, reopen and reporting. Corruption/missing-object discovery blocks authority-consuming actions without modifying past accepted bytes/head. Restore can use only independently verified identical raw bytes at the same digest; nonidentical rebuild is a new package for a new assignment. External rollback threats retain existing anchoring/backup qualification; process crashes alone do not qualify them.


## H. Migration semantics

| Existing material | Allowed interpretation/action | Forbidden claim/action |
| --- | --- | --- |
| Legal pre-NF02/R5.3 campaign history | Read-only historical replay under exact original pinned schemas/specs and retained bytes. Separate historical report with source/schema provenance. | R5.4 current assurance, latest-schema validation replacing historical semantics, retroactive binding/start chronology. |
| History containing unregistered NF02 /1 extensions | Preserve bytes and receipts for forensic/history display; explicitly unqualified/nonconforming for C1. Reader uses isolated historical decoding, never R5.4 accepting path. | Treat local extension as normative R5.3 legality or map /1 into /2. If legal replay cannot establish authority, expose that limitation instead of fabricating valid canonical state. |
| In-flight old Assignment / delivered old package | Stop old current execution for this migration boundary; create new R5.4 campaign, new Attempt/Assignment/package/binding before new delivery. Preserve old grants/exposure as historical context. | Add B after delivery and claim it preceded execution; reuse old STARTED transition as R5.4 authorization. |
| Old result/raw with missing retained closure | Historical integrity block; retain diagnostic identity. Identical byte restoration may repair availability only when independently verified. | Automatic backfill from mutable workspace, fabricated package relation, fabricated receipt or qualified new result. |
| Old results/evidence potentially useful in new audit | Treat as untrusted historical input, subject to existing explicit lineage/source/evidence applicability/knowledge admission assessment and new grants. Preserve actual historical chronology. | Automatic R5.4 result/slot satisfaction or blind-origin independence from old results. |
| New independent R5.4 campaign | New namespace/genesis using qualified existing bootstrap contract with exact R5.4 pins; new execution context. Existing source identity may be reused only through its legal exact authority contract. | A second normal genesis on nonempty old namespace or EMPTY_HISTORY reuse after seq=1. |
| Concluded predecessor with independently legal successor trigger | Existing SuccessorCampaignGenesis and branch-selection rules may apply if every predecessor/trigger requirement is separately met. | Invent “schema install” as a new allowed successor trigger, treat an unconcluded campaign as concluded, or bypass assurance branch resolution. |

**Mandatory default: new independent campaign**, not in-place migration or a newly invented successor trigger. Product may present explicit historical linkage, but that display does not assert assurance succession. No canonical migration kind is added. No automatic package binding backfill. Historical /1 bytes never get a new accepting input cut.

R5.4 installation retains historical readers and original pins. Its writer rejects attempts to open old campaign for new-contract writes with a stable compatibility error in STATE_CONFLICT family. Migration status/profile is explicit UI/CLI context; it is not a mutable canonical campaign state authority.


### 192.1. Executable schema and external profile representation

Canonical domain bodies exclude own kind/version/digest/acceptance provenance, carried in the external immutable-object envelope. TypedRef is closed: kind, optional logical_id, revision_digest, digest_profile=BDB-OBJECT-DIGEST-1, schema_revision_ref={kind:schema,revision_digest:RawDigest(executable schema bytes)}. Target kind/version and schema digest must resolve consistently to the Registry key; `schema` is not an ObjectDigest domain. ExternalProfileRef is {profile_id,revision_digest:RawDigest(exact profile JSON bytes)}. RawRef is {raw_digest,byte_length,media_type,artifact_contract_ref:ExternalProfileRef}. Reference-class annotations are Registry metadata, not fields admitted into closed identity-bearing refs.

HistoryCut keeps inherited value encoding: accepted cut fields campaign_id, accepted_head_seq, accepted_head_hash, governing_policy_ref, governing_spec_refs; initialization tagged EMPTY_HISTORY_CUT additionally identifies exact history_namespace_ref and has no accepted head/hash. Governing spec set at bootstrap remains the single exact initial_transition_profile_ref. No synthetic H0. Registered wire version/schema ref identifies domain schemas independently of body metadata.

Finite NF02 result payload is findings[], outputs{}, notes:string|null. Each finding has external finding_id, title, statement, evidence_member_paths[], reported_severity (BLOCKER/HIGH/MEDIUM/LOW/INFO/UNKNOWN). These are external claims, not M/R/I, finding adjudication or evidence qualification. Duplicate finding IDs reject. Order and Unicode text are preserved; no silent normalization. outputs may have only report/evidence/logs, each {member_paths:[]}; member paths are UTF-8 sorted unique and resolve inside retained result ZIP. No embedded material TypedRefs. notes is required even if null; findings/outputs remain required when empty. Changing this finite profile later requires an explicit breaking profile/schema revision.

External transport manifests are closed exact schemas in the schema catalog. Package manifest carries prior assignment and exact derived attempt/source/stage/lane/executor/delivery/input cut and declared slot refs, actual member records, transport profile and tagged semantic checksum. It never includes final package RawDigest, future binding or STARTED ref. Result manifest additionally names exact prior package binding and result slot, checked package semantic assertion and finite payload. Expected identities come from accepted binding/assignment and governing pins, never the manifest. Media types use the fixed pinned extension mapping, not host sniffing. ZIP members, quotas, metadata, raw digest and checksum restrictions are defined in frozen transport profiles and §192.

Executable schema validation is only L3: pure schema/hash self-audit does not prove history membership, actor authorization, durable storage, FSM/disclosure, evidence truth, LaneCompletion or StageCompletion. These require cross-object/runtime checks in N5-N11. Unknown/unbound mandatory schema, extra ref, secret token or alias rejects without canonical state mutation. Const schemas for the initial policy/spec/trust/ArtifactContractRegistry admit only those exact installation revisions, not arbitrary future /1 bodies. Broader schema binding must not change frozen semantics and still obey new-campaign boundary.

Binding/evidence/result acceptance uses the existing ArtifactAccepted envelope with exact artifact_ref. The pinned transition profile defines its NF02 effects: B/1 leaves Attempt CREATED; E/2 permits STARTED to RESULT_RECEIVED only after all admission predicates; R/2 permits RESULT_RECEIVED to RESULT_ACCEPTED only after its predicates. No new event alias or state is added. AttemptStarted remains the existing separate accepted transition. Initial spec_revision/1 executable schema explicitly marks protocol_profile_ref as PINNED_PROFILE_REF; deferred predecessor rows gain their exact body ref inventory from these frozen schemas, not a process-local lookup.

### 192.2. Successor governance and exact bytes

The normative set remains eight Markdown sources plus successor Registry and Golden Vectors. Unchanged Methodology/Migration/ADR bytes are carried exactly and identified as inherited normative inputs in the successor manifest; their historical status/header refers only to predecessor provenance. The machine set includes schema bytes, catalog, canonical initial objects, external profiles, bootstrap bundle and vector fixtures. Candidate identity is {normative_set_digest,machine_set_digest}, bound by exact external manifest RawDigest; each set uses the established sorted [{file,bytes,sha256}] canonical JSON SHA256 preimage. Manifest, self-audit/readback, source pins and governance evidence are external to both sets to avoid self-reference.

Design approval does not establish hash-bound candidate qualification or waive independent review. AuthorBaselineQualificationRecord/2 may derive AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE=YES only after zero-mismatch readback, exact final self-audit and explicit authorized owner acceptance of author-only implementation risk for the exact manifest and both sets. It retains independent_assurance=false and foundation_spec_baseline_frozen=false. The /1 historical record/token remains unchanged. Independent freeze uses the existing foundation_baseline_freeze_decision/1 only after a genuine independent READY review of exact manifest/machine closure. Prepared pending templates are neither valid qualification records nor canonical facts. No independent PASS or risk waiver is inferred from owner approval of these three design choices.

The external AuthorBaselineQualificationRecord/2 is defined exactly by §187.2 and its pinned external executable schema. All body/count/verdict predicates are the same single contract; no separate definition applies here. Independent foundation_baseline_freeze_decision/1 and its complete exact-manifest review requirements remain unchanged. Pending templates are not decisions.

Prepared installation bundle is CANDIDATE_PREPARED_NOT_INSTALLED. Runtime activation requires external hash-bound governance qualification, independently authenticated installation actor/trust root, exact schema-root verification and legal genesis. Installation must not write/upgrade old campaigns. The fixed candidate namespace is reserved, not an operating campaign; any other namespace requires its own exact externally authorized installation revision before first genesis. Current remediation runtime is not authority and must change later; N1-N4 do not implement or qualify it.

# BDB Audit v2 — R5.4 successor normative candidate

Status: PENDING_EXACT_CANDIDATE_QUALIFICATION; not installed, not independent freeze, no runtime qualification.

Date: 2026-10-06. Predecessor R5.3.1 candidate set `087539f5a08a2441647aae1889ce51330b47740e559b394574da122bd6cfd15b`; predecessor R5.3 set `78de98f8163d2f0bf0ab94781b86bd8e5e0345411a4432669d91fdfc42671d56`.

This is a separate versioned successor. Owner approved the R5.4/NF02 design and new-campaign boundary. Predecessor references/status/reviews inside inherited history are provenance, not current qualification or runtime authority. The current normative file set is exactly the R5.4 manifest; prior source bytes remain untouched. Registered semantics, exact executable bindings, authenticated prior authority and every domain predicate are jointly required.

# BDB AUDIT v2 — ARCHITECTURE SPEC

**Status:** AUTHOR-HOTFIX R5.3.1 CANDIDATE — bootstrap-order correction; exact storage readback qualification pending; no additional Astra review scheduled
**Rewizja:** 2026-09-10 / R5.3.1 bootstrap-order correction candidate
**Self-audit:** `R5_3_1_AUTHOR_HOTFIX_REAUDIT_PASS`; report `BDB_AUDIT_V2_SELF_AUDIT_REPORT_R5_3_1_2026-09-10.md`; external readback qualification remains pending; strict independent freeze is not claimed
**Dokument:** normatywna specyfikacja techniczna architektury BDB Audit v2  
**Powiązany dokument nadrzędny:** `BDB_Audit_vNext_Szczegolowy_Plan_Rozwoju.md`  
**Cel:** określić strukturę aplikacji, granice authority, model domenowy, transakcyjną historię, przepływy danych, izolację knowledge, coverage/evidence semantics, finalizację oraz migrację z BDB Audit Assistant v1.4.4 do BDB Audit v2  
**Zakres:** aplikacja lokalna, campaign/stage/lane orchestration, walidacja artefaktów, legacy compatibility, deterministic standalone build, reference implementation profile  
**Zasada nadrzędna:** jedna zaakceptowana historia i immutable revisions są źródłem aktualnego stanu; ledgery, grafy, raporty i summaries są projekcjami tej historii, chyba że kontrakt jawnie definiuje dany immutable artifact jako wejściowy dowód.

---

# 1. Cel architektury

BDB Audit v2 jest controlled rewrite istniejącego BDB Audit Assistant v1.4.4. Zachowuje sprawdzone mechaniczne assurance primitives, ale zmienia centralny model domenowy i sposób przechowywania decyzji.

Obecny model v1.4.4 można uprościć do:

```text
VARIANT
→ STEP
→ PROMPT
→ HANDOFF
→ VALIDATE
```

BDB Audit v2 ma realizować program assurance:

```text
CAMPAIGN
→ SOURCE GENERATION
→ STAGE / LANE / ATTEMPT
→ CONTROLLED KNOWLEDGE STATE
→ DISCOVERY
→ SURFACE / INVARIANT / COVERAGE OBLIGATION
→ HYPOTHESIS
→ EXPERIMENT / EXECUTION
→ OBSERVATION / EVIDENCE QUALIFICATION
→ FINDING / CONTRADICTION / ROOT CAUSE
→ STAGE COMPLETION
→ ASSURANCE CHALLENGE
→ STOP EVALUATION
→ CAMPAIGN CONCLUSION
```

Architektura MUSI zachować historyczne E1/E2 bytes i lineage, ale NIE MOŻE kopiować bezkrytycznie semantycznych ograniczeń v1.4.4 do nowego modelu.

Podstawowa zasada przebudowy:

> **Reuse mechanicznych primitives tam, gdzie ich kontrakt jest niezależnie kwalifikowany; rewrite orchestration, history/authority, knowledge, coverage i evidence semantics.**

---

# 2. Główne cele niefunkcjonalne

BDB Audit v2 MUSI być:

1. **Fail-closed** dla lineage, source identity, knowledge/reveal, authority, current-evidence applicability, stage completion i STOP.
2. **Single-authority** — brak równoległych mutable heads dla ledgerów, snapshots i `state.json`.
3. **Transactional** — accepted history, referenced immutable bytes, receipt i accepted head mają jedną logiczną granicę commit.
4. **Idempotent** — retry po niejednoznacznym ACK nie może mnożyć historii ani efektów domenowych.
5. **Source-generation strict** — evidence nie przechodzi na inną Source Generation bez jawnej rekwalifikacji.
6. **Policy/spec pinned** — run zawsze wiąże exact protocol/policy/schema/StageSpec/LaneSpec/ExecutorSpec/DeliverySpec revisions. Governing policy/spec/profile dla danego objectu musi być effective na jego exact input HistoryCut; revision wprowadzona w tym samym commicie nie może walidować samej siebie ani referring objectu.
7. **Exposure-aware** — engine kwalifikuje kontrolowane kanały i potential exposure, nie twierdzi, że zna pełny stan wiedzy modelu/człowieka.
8. **Discovery-provenance strict** — claim o blind discovery wymaga accepted precursor z exact history/knowledge cut sprzed reveal.
9. **Coverage-obligation driven** — authority coverage stanowią scoped obligations, nie ręczny poziom D0–D5.
10. **Evidence-qualification driven** — independence i applicability są relacjami względem konkretnego claimu i failure assumption.
11. **Corpus-aware** — direct predecessor, auxiliary corpus, cumulative corpus i holdout są różnymi rolami.
12. **Schema-driven** — stages/lanes/records są wersjonowane i nie zależą od przypadkowych nazw plików.
13. **Stage-extensible** bez rozbudowy `elif` w core.
14. **Executor-extensible** bez pakowania tool/model/delivery do centralnego `variant_id`.
15. **Auditable** — każda materialna decyzja ma odtwarzalne immutable inputs, policy revision i accepted history cut.
16. **Rebuildable** — projections można usunąć i odtworzyć bez zmiany decyzji.
17. **Backward-readable** — historyczne v1.4.4 artifacts są zachowane jako raw bytes + current import assessments.
18. **Deterministic where promised** — build, canonical objects, prompt templates i exports mają jawny deterministic profile.
19. **Standalone-capable** — modular source może zostać zbudowane do jednego `.py` bez ukrytych runtime downloads.
20. **Explicitly bounded** — system nie udaje wykrywania unknown unknowns, pełnej kompromitacji hosta ani niezależności, której nie potrafi wykazać.

---

# 3. Architektura wysokiego poziomu

```text
┌────────────────────────────────────────────────────────────────────┐
│                             USER / CLI                             │
└───────────────────────────────┬────────────────────────────────────┘
                                │ commands / explicit decisions
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                      APPLICATION / COORDINATOR                     │
│  authenticate actor • validate command • evaluate guards • accept  │
└───────────────┬───────────────────┬───────────────────┬────────────┘
                │                   │                   │
                ▼                   ▼                   ▼
┌──────────────────────┐  ┌──────────────────────┐  ┌────────────────────┐
│ TRANSITION SERVICE   │  │ ASSURANCE PRIMITIVES │  │ CAPABILITY BROKER  │
│ campaign/stage/lane  │  │ hash/zip/source      │  │ views/reveal/tools │
│ attempt/finalization │  │ legacy validation    │  │ isolation receipts │
└───────────┬──────────┘  └───────────┬──────────┘  └──────────┬─────────┘
            │                         │                        │
            └──────────────┬──────────┴──────────────┬─────────┘
                           ▼                         ▼
              ┌──────────────────────┐   ┌─────────────────────────┐
              │ CANONICAL HISTORY    │   │ IMMUTABLE OBJECT STORE  │
              │ accepted commits     │◄─►│ artifacts/evidence/spec │
              │ receipts / head      │   │ exact revisions         │
              └──────────┬───────────┘   └─────────────────────────┘
                         │
                         ▼
        ┌──────────────────────────────────────────────────────────┐
        │                    DERIVED SERVICES                      │
        │ Knowledge • Corpus • Inventory • Obligations • Evidence │
        │ Findings • Contradictions • Coverage • STOP • Reports   │
        └──────────────────────────┬───────────────────────────────┘
                                   │
                                   ▼
                 ┌─────────────────────────────────────┐
                 │ PROMPT / PACKAGE / EXPORT COMPILER  │
                 │ positive views + deterministic refs │
                 └─────────────────────────────────────┘
```

**Najważniejsza zmiana względem pierwotnej architektury:** `Storage Layer` nie jest pasywnym folderem obok wielu ledgerów. Foundation posiada **Canonical History Service** i immutable object closure. Pozostałe „ledgery” są albo canonical event/fact families w tej historii, albo derived exports z `as_of_head`.

---

# 4. Podział odpowiedzialności

## 4.1. Coordinator / Authority Core

Coordinator jest jedynym komponentem uprawnionym do ustanawiania accepted history dla lokalnego profilu BDB.

Odpowiada za:

- actor/permission validation,
- command envelope,
- expected-head / expected-revision guards,
- idempotency i command deduplication,
- accepted commit construction,
- immutable object reachability,
- receipt issuance,
- accepted-head update,
- crash/retry semantics,
- stage/campaign transition acceptance,
- admission/reveal/finalization decisions.

Executor może **proponować** wynik, ale jego `PASS`, timestamp, własny hash lub `status=CONFIRMED` nie ustanawia authority.

## 4.2. Assurance Primitives

Warstwa przejmująca kwalifikowane mechaniczne mechanizmy v1.4.4:

- SHA-256 exact bytes,
- deterministic ZIP profile,
- ZIP path/duplicate safety,
- raw artifact hash manifests,
- source identity readback,
- F1/F2 legacy checkpoint validation,
- raw-byte prefix validation legacy ledgers,
- retained snapshot/digest checks,
- continuation-ticket validation,
- bundle membership validation,
- legacy result validation.

Ta warstwa NIE jest authority semantycznej poprawności legacy zachowania. Preservation i correctness są osobnymi gates.

## 4.3. Transition / Orchestration Service

Jeden service implementacyjny obsługuje osobne aggregate FSM:

- Campaign,
- StageRun,
- LaneRun,
- Attempt,
- finalization lifecycle.

Odpowiada za:

- guards/effects,
- retry vs new attempt,
- cancel,
- duplicate/late result,
- successor run,
- reopen,
- canonical-result selection,
- E6 eligibility,
- stage completion.

Nie utrzymuje osobnego storage authority poza canonical history.

## 4.4. Knowledge / Corpus / Capability Broker

Odpowiada za:

- ENFORCED / DECLARED / UNKNOWN isolation profile,
- channel inventory,
- allowed-input views,
- grant-before-delivery,
- potential exposure,
- contamination assessments,
- immutable Knowledge State revisions,
- direct predecessor,
- auxiliary/cumulative/holdout corpus snapshots,
- positive projection policies,
- restricted resolver,
- Claim Quarantine.

## 4.5. Discovery / Inventory / Coverage Services

Odpowiadają za:

- Surface collectors i ich capability manifests,
- assigned-input accounting,
- inventory revisions,
- known-unobserved / unsupported / excluded scope,
- Invariant Registry,
- Coverage Obligation planning,
- obligation qualification,
- Gap Map,
- derived D0–D5 presentation,
- risk/priority scheduling,
- negative-space tracking.

`Coverage Ledger` jako osobny mutable authority NIE istnieje.

## 4.6. Experiment / Evidence / Adjudication Services

Odpowiadają za:

- hypotheses,
- preregistered experiment plans,
- execution descriptors,
- raw observations,
- observation dependency graph,
- claim-relative independence qualification,
- evidence applicability/invalidation,
- findings,
- root-cause membership,
- contradictions,
- contribution i support views,
- model-fidelity assessments,
- challenger outcomes.

Finding / Root Cause / Contradiction mogą współdzielić jeden adjudication service, ale zachowują osobne typy decyzji.

## 4.7. Prompt / Bundle / Export Compiler

Buduje deterministycznie:

- prompt templates + runtime view instances,
- execution contexts,
- Stage/Lane packages,
- previous-stage corpus packages,
- Claim Quarantine views,
- exports JSON/JSONL/ZIP/Markdown,
- standalone application payload.

Compiler NIE decyduje o policy ani reveal eligibility. Otrzymuje zaakceptowane, pinned inputs i wygenerowany capability view.

---

# 5. Docelowa struktura repozytorium

```text
bdb-audit/
│
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── LICENSE
│
├── src/
│   └── bdb_audit/
│       ├── coordinator/
│       │   ├── commands.py
│       │   ├── authority.py
│       │   ├── receipts.py
│       │   └── transactions.py
│       │
│       ├── assurance/
│       │   ├── hashing.py
│       │   ├── zip_safety.py
│       │   ├── source_identity.py
│       │   ├── legacy_handoff.py
│       │   ├── legacy_result.py
│       │   └── legacy_v1.py
│       │
│       ├── history/
│       │   ├── commit_model.py
│       │   ├── object_store.py
│       │   ├── vault.py
│       │   ├── projector.py
│       │   └── integrity.py
│       │
│       ├── orchestration/
│       │   ├── campaign.py
│       │   ├── stage.py
│       │   ├── lane.py
│       │   ├── attempt.py
│       │   ├── transition_service.py
│       │   └── finalization.py
│       │
│       ├── knowledge/
│       │   ├── isolation.py
│       │   ├── broker.py
│       │   ├── knowledge_state.py
│       │   ├── reveal.py
│       │   ├── projections.py
│       │   └── quarantine.py
│       │
│       ├── corpus/
│       │   ├── snapshot.py
│       │   ├── admission.py
│       │   ├── predecessor.py
│       │   └── holdout.py
│       │
│       ├── inventory/
│       │   ├── collectors.py
│       │   ├── surface.py
│       │   ├── scope.py
│       │   └── capability.py
│       │
│       ├── invariants/
│       │   ├── registry.py
│       │   └── obligations.py
│       │
│       ├── coverage/
│       │   ├── qualification.py
│       │   ├── derived_depth.py
│       │   ├── gap_engine.py
│       │   └── priority.py
│       │
│       ├── experiments/
│       │   ├── hypothesis.py
│       │   ├── spec.py
│       │   ├── execution.py
│       │   ├── observations.py
│       │   └── oracle_challenge.py
│       │
│       ├── evidence/
│       │   ├── dependencies.py
│       │   ├── independence.py
│       │   ├── applicability.py
│       │   ├── invalidation.py
│       │   └── replay.py
│       │
│       ├── adjudication/
│       │   ├── findings.py
│       │   ├── root_causes.py
│       │   ├── contradictions.py
│       │   └── contribution.py
│       │
│       ├── stages/
│       │   ├── e1.py
│       │   ├── e2.py
│       │   ├── e3.py
│       │   ├── e4.py
│       │   ├── e5.py
│       │   └── e6.py
│       │
│       ├── stop/
│       │   ├── input_snapshot.py
│       │   ├── evaluator.py
│       │   └── saturation.py
│       │
│       ├── schemas/
│       │   ├── registry.py
│       │   └── contracts/
│       │
│       ├── compiler/
│       │   ├── prompts.py
│       │   ├── packages.py
│       │   ├── exports.py
│       │   └── standalone.py
│       │
│       ├── security/
│       │   ├── permissions.py
│       │   ├── redaction.py
│       │   └── sandbox_profiles.py
│       │
│       └── cli/
│           └── main.py
│
├── specs/
│   ├── stages/
│   ├── lanes/
│   ├── executor_profiles/
│   ├── delivery_profiles/
│   ├── policy_profiles/
│   └── schema_sets/
│
├── legacy/
│   └── v1_4_4/
│
├── tests/
│   ├── unit/
│   ├── contracts/
│   ├── compatibility/
│   ├── adversarial/
│   ├── reference/
│   ├── property/
│   └── golden/
│
├── build/
│   └── build_single_file.py
│
└── dist/
    └── BDB_AUDIT_ASSISTANT_v2.x.x.py
```

Warstwy repozytorium są granicami odpowiedzialności, nie mikroserwisami. Baseline BDB pozostaje lokalną aplikacją z jednym coordinator/process authority profile.

---

# 6. Model domenowy

## 6.1. Campaign

Campaign reprezentuje jeden program audytu jednej frozen Source Generation.

Minimalne bindingi:

```text
campaign_id
campaign_genesis_revision
source_generation_ref
application_generation_ref
protocol_policy_bundle_ref
schema_set_ref
trust_profile_ref
owner/operator authority
status_projection
current_history_head
legacy_origin_optional
```

Invariant:

> Jedna campaign nie może zmienić subject Source Generation. Remediation na nowych bytes tworzy nową Source Generation i osobny requalification context/campaign.

## 6.2. SourceGeneration

SourceGeneration ma normalized identity niezależną od filename/ZIP representation.

Semantycznie wiąże:

```text
source_identity_profile
repository_id / snapshot authority
commit/tree when applicable
materialized source manifest revision
source manifest digest
representation refs optional
parent/source lineage optional
```

`branch`, mtime i archive filename są obserwacjami, nie authority.

Exact canonical identity profile jest normowany w Data & Artifact Contracts + dedykowanym ADR.


## 6.2.1. TrustProfile / history anchoring

Campaign pinning wskazuje exact `TrustProfile` revision. Baseline profile `LOCAL_PINNED` wymaga coordinator-owned vault poza writable namespace executora. Export/history anchoring ma poziom `UNPINNED`, `LOCAL_PINNED` albo `EXTERNALLY_PINNED_THROUGH(n,H)`.

Full-host rollback bez niezależnego nowszego pin/witness pozostaje poza gwarancją baseline. Podpis/witness jest opcjonalnym silniejszym profilem, nie automatycznym dowodem świeżości. Machine contract definiuje Data & Artifact Contracts.
## 6.3. StageSpec

StageSpec jest immutable revision, nie luźnym `stage_id`.

```text
stage_key
stage_spec_revision
ordinal / role
purpose
predecessor requirements
required lane slots
optional lane slots
blind/reveal phases
allowed corpora
forbidden corpora
coverage/obligation policy refs
required stage-completion outputs
transition policy
stop/e6 relationship
```

Zmiana semantyki StageSpec po uruchomieniu nie aktualizuje starego runu; tworzy nową revision.

## 6.4. StageRun

```text
stage_run_id
campaign_id
stage_spec_revision
source_generation_ref
creation_revision
assigned_history_cut
state_projection
attempt_refs                         # derived child projection
lane_run_refs                        # derived child projection
stage_completion_ref optional         # derived completion projection
successor_of_stage_run_ref optional   # backward lineage ref
```

Creation revision nie zawiera future child/completion refs; `attempt_refs`, `lane_run_refs` i `stage_completion_ref` są current-state projections. `successor_of_stage_run_ref` wskazuje wyłącznie istniejący predecessor run. `started_at`/`finished_at` są metadanymi obserwacyjnymi. Kolejność authority wynika z accepted commits.

## 6.5. LaneSpec

```text
lane_key
lane_spec_revision
stage_spec_revision
purpose
primary_strategy
scope selectors
wildcard/exploration policy
allowed input view classes
forbidden knowledge classes
required isolation assurance
required outputs
executor capability requirements
budget/effort profile
completion predicate
```

## 6.6. LaneRun

```text
lane_run_id
campaign_id
stage_run_id
lane_spec_revision
source_generation_ref
creation_revision
state_projection
attempt_refs
completion_ref optional
```

LaneRun nie ma jednego mutable `knowledge_state_id`; knowledge zmienia się w czasie i jest attempt-bound.

## 6.7. Attempt

Attempt jest jednorazowym wykonaniem lane assignment.

```text
attempt_id
attempt_creation_revision
lane_run_id
nonce
executor_profile_revision
delivery_profile_revision
assigned_history_cut
result_slots
terminal_state_projection
```

Attempt creation nie zawiera initial KnowledgeState ani AssignmentManifest. Capability/knowledge initialization jest osobnym, jednokierunkowym DAG:

```text
AttemptCreated object
→ GrantBody(previous KS or null)
→ PotentialExposureRecord
→ initial/successor KnowledgeState
→ AssignmentManifest
→ accepted events / AttemptStarted
```

`GrantBody`, Exposure, `KnowledgeState` i `AssignmentManifest` wskazują istniejący Attempt; Attempt creation nie wskazuje ich w przyszłość. Ich `*_input_history_cut` wskazuje prior accepted cut, natomiast same-commit dependencies są exact object refs. Dzięki temu obiekty mogą zostać zaakceptowane atomowo w jednym commicie w topologicznej kolejności bez post-head/self-reference. `AttemptStarted` wymaga accepted AssignmentManifest z exact knowledge/grant/source/spec bindings. Retry execution tworzy nowy Attempt. Retry uploadu tego samego rezultatu może być idempotentnym powtórzeniem tego samego command/result slot.

## 6.8. Logical identity i immutable revision

Dla bytów z lifecycle istnieją dwie warstwy:

```text
LOGICAL_ID
REVISION_DIGEST
```

Materialny claim/checkpoint/gate/evidence MUSI referencjonować exact revision, nie „current object by ID”.

## 6.9. HistoryCut

Każda decyzja wymagająca spójnego stanu posiada tagged `HistoryCut`:

```text
EMPTY_HISTORY_CUT(history_namespace, policy/spec refs)   # tylko initialization
| ACCEPTED_HISTORY_CUT(campaign_id, accepted_head_seq, accepted_head_hash, policy/spec refs)
```

Nie istnieje synthetic H0/zero hash. Pierwszy accepted commit ma seq=1; `EMPTY_HISTORY_CUT` jest odrzucany po initialization i nigdy nie jest evidence/STOP inputem. Gate, checkpoint, evidence qualification, stage completion i STOP działają na dokładnym accepted cut i nie odczytują mieszanki projections z różnych heads.

## 6.10. First accepted bootstrap transaction

`EMPTY_HISTORY_CUT` nie zezwala na dowolne bootstrap defaults. Baseline `LOCAL_PINNED` posiada przed utworzeniem campaign zewnętrzny exact pin `INSTALLATION_BOOTSTRAP_PROFILE_V1`, który należy do installation trust boundary, nie do mutable campaign state. Profil przypina initial SchemaRegistry, ArtifactContractRegistry, serialization profile, governing policy, transition profile, trust profile, allowed history namespace oraz source-identity profile; dopuszcza wyłącznie `INITIALIZE_CAMPAIGN_FROM_LEGACY` jako first-history command.

Pierwszy `commit_seq=1` jest jedną atomową initialization closure: Przed acceptance jego `CommandEnvelope` używa `proposed_campaign_id + history_namespace_ref + bootstrap_profile_ref`, a `campaign_ref` jest zabronione, ponieważ CampaignGenesis nie jest jeszcze accepted.

```text
external INSTALLATION_BOOTSTRAP_PROFILE_V1 pins / any typed content prerequisites
→ command payload object optional (when referenced by CommandEnvelope)
→ CommandEnvelope
→ SourceGeneration / exact current target source object
→ LEGACY_RAW_REF
→ LegacyMechanicalValidationAssessment
→ SourceReconciliationAssessment
→ LineageAdmissionAssessment
→ LegacyExposureReconstructionAssessment optional
→ TrustedPredecessorSelectionDecision
→ BootstrapAdmissionDecision
→ CampaignGenesis
→ CommitBody(seq=1, EMPTY_HISTORY)
→ Receipt + AcceptedHead(seq=1)
```

Generic ApprovalDecision nie jest aliasem TrustedPredecessorSelectionDecision; exact selection decision jest odrębnym wcześniejszym node bootstrap closure.

**R5.3.1 canonical-order correction:** lista powyżej jest wykonywana przez jeden algorytm Kahn na **union DAG**. Edge-set to `(A)` wszystkie normatywne same-commit typed content-ref dependencies oraz `(B)` jawne order-only precedence edges z exact pinned Registry profile `BDB_BOOTSTRAP_PRECEDENCE_V1`, wyłącznie dla `INITIALIZE_CAMPAIGN_FROM_LEGACY`, `commit_seq=1`, `EMPTY_HISTORY`. Profile nakłada grupowy porządek `command_envelope → source_generation → legacy_raw_ref → legacy_mechanical_validation_assessment → source_reconciliation_assessment → lineage_admission_assessment → legacy_exposure_reconstruction_assessment? → trusted_predecessor_selection_decision → bootstrap_admission_decision → campaign_genesis`; dla wielu nodes w grupie istniejący typed tie-break rozstrzyga kolejność wewnątrz grupy. Nieobecna opcjonalna grupa jest pomijana.

Order-only precedence edge uczestniczy w canonical ordering i cycle detection, ale **nie jest typed refem**: nie tworzy reachability, authority, history provenance ani referential-integrity satisfaction i nie może uzupełnić brakującego required `material_ref`. W szczególności `LEGACY_RAW_REF` pozostaje niezależnym raw reference bez `source_generation_ref`; relacja `source_generation → legacy_raw_ref` jest wyłącznie bootstrap-order constraint. Command payload i prerequisites SourceGeneration zachowują własne typed content refs i przez nie muszą wystąpić przed consumerem. `*_input_history_cut` pozostaje `EMPTY_HISTORY_CUT`; dopiero acceptance całego commit `seq=1` ustanawia history provenance. Jeśli union DAG ma cycle albo bootstrap profile nie jest exact pinned/current, acceptance jest fail-closed. Jeśli bootstrap admission jest blocked, `CampaignGenesisAccepted` nie może powstać.

Po `seq=1` `EMPTY_HISTORY`, `EMPTY_HISTORY_CUT` i initialization command są dla tego namespace niedozwolone. Current policy/schema/trust przechodzą na exact revisions przypięte/zaakceptowane przez canonical history. Retry identycznego initialization commandu jest idempotentny; konkurencyjny drugi initialization jest rejected.


---

# 7. Campaign State Machine

Campaign lifecycle rozdziela **postęp etapów**, **termination**, **assurance conclusion** i **release status audytowanego source**. Canonical authority objects dla tych granic to odpowiednio `StageCompletion`, `StopEvaluation`, `CampaignConclusion` i `ReleaseQualification`; nazwy opisowe nie tworzą alternatywnych outcome types.

Normatywny projection FSM rozdziela campaign lifecycle od finalization readiness:

```text
CREATED
→ GENESIS_ACCEPTED
   ├─ → E0_READY → AUDIT_RUNNING
   ├─ → BLOCKED
   └─ → CANCELLED
AUDIT_RUNNING
   ├─ intermediate StopEvaluation=CONTINUE_REQUIRED → AUDIT_RUNNING
   ├─ intermediate StopEvaluation=BLOCKED → BLOCKED
   ├─ final StopEvaluation=CONTINUE_REQUIRED → AUDIT_RUNNING (finalization precondition violation)
   ├─ final/post-E5 StopEvaluation=E6_REQUIRED → E6_REQUIRED → E6_RUNNING
   ├─ final StopEvaluation=PASS + ConcludeCampaign → CAMPAIGN_CONCLUDED
   ├─ final StopEvaluation=BLOCKED → BLOCKED
   └─ final StopEvaluation=BLOCKED + authorized COMPLETED_LIMITED conclusion → CAMPAIGN_CONCLUDED
E6_REQUIRED → E6_RUNNING | BLOCKED
E6_RUNNING
   ├─ post-E6 StopEvaluation=E6_REQUIRED → E6_REQUIRED
   ├─ post-E6 StopEvaluation=PASS + ConcludeCampaign → CAMPAIGN_CONCLUDED
   ├─ post-E6 StopEvaluation=BLOCKED → BLOCKED
   └─ post-E6 StopEvaluation=BLOCKED + authorized COMPLETED_LIMITED conclusion → CAMPAIGN_CONCLUDED
BLOCKED → AUDIT_RUNNING only przez accepted ResolveBlocker/ReopenCampaign
BLOCKED → CAMPAIGN_CONCLUDED only przez authorized COMPLETED_LIMITED conclusion
CAMPAIGN_CONCLUDED → CLOSED
CANCELLED = administrative terminal; bez assurance/release conclusion
```

Dodatkowe terminal/operacyjne stany:

```text
E6_REQUIRED
E6_RUNNING
BLOCKED
CANCELLED
CLOSED
```

`ordinary_stages_complete`, `candidate_assurance_ready`, `challenge_complete` i latest STOP są derived readiness facts, nie dodatkowymi CampaignState. Dzięki temu intermediate STOP po E1/E2/E3/E4 może poprawnie zwrócić `CONTINUE_REQUIRED` bez fikcyjnego Candidate Assurance Case i challengerów. Candidate/challenger closure staje się obowiązkowa dopiero dla final/post-E5 oraz odpowiedniego post-E6 STOP.

Nie używa się jednego enumu `AUDIT_COMPLETE` jako synonimu `RELEASE_READY`.

### Reguły

- E1→E3 bez E2 wymaga jawnego migration/bootstrap exception w pinned policy.
- Campaign conclusion nie zmienia historycznych StageCompletion.
- Materialne nowe evidence po conclusion nie mutuje conclusion i nie reopenuje `CAMPAIGN_CONCLUDED`; tworzy **successor campaign** z backward `predecessor_campaign_ref`, `predecessor_conclusion_ref` i exact `successor_trigger_ref`.
- Poprzednie assurance może stać się current-applicability `STALE`; nowy current assurance wymaga nowej successor conclusion. Konkurencyjne successor branches są fail-closed do accepted `SuccessorCampaignSelectionDecision`; derived `CurrentAssuranceSelection` nie może wybierać branch przez timestamp/latest-by-name.
- Source remediation nie „wznawia” tej samej source campaign; nowa SourceGeneration używa successor/new campaign lineage.

---

# 8. Stage State Machine

Każdy StageSpec definiuje własne subphases, ale rdzeń lifecycle jest wspólny:

```text
PLANNED
→ READY
→ RUNNING
→ WAITING_FOR_REQUIRED_INPUT
→ COMPLETION_CANDIDATE
→ COMPLETION_ACCEPTED
```

Terminalne alternatywy:

```text
BLOCKED
CANCELLED
SUPERSEDED
```

Materialny follow-up po `COMPLETION_ACCEPTED` tworzy successor/reopen StageRun flow; historyczny StageCompletion pozostaje immutable i nie otrzymuje „completion revision” zgodnie z StageSpec; nie dopisuje po cichu wyniku do zamkniętego cut.

Każde przejście definiuje:

```text
from_state
command_type
required exact revisions
required history cut
eligibility guards
effects / accepted events
terminality
```

### Retry / duplicate / late result

- ten sam `command_id` + ten sam `command_digest` → ten sam persisted receipt,
- ten sam `command_id` + inny `command_digest` → `ID_REUSE_CONFLICT`,
- ten sam `(attempt_id, result_slot)` + identyczny result hash → dedup,
- inny result hash dla zamkniętego slotu → `RESULT_CONFLICT`,
- wynik po terminalnym/cancelled Attempt → accepted handling outcome `QUARANTINED_LATE_RESULT` (`LATE_RESULT` pozostaje error-code family),
- late result nie zmienia StageCompletion bez nowego successor flow.

---

# 9. Lane isolation

Blindness jest właściwością kontrolowanych kanałów, nie deklaracją promptu.

Każdy Attempt ma:

```text
isolation_assurance = ENFORCED | DECLARED | UNKNOWN
channel_inventory
executor/session provenance
enforcement receipt optional
allowed capabilities
potential exposure refs
contamination assessments
```

## ENFORCED

Wymaga rzeczywistej kontroli co najmniej nad kanałami materialnymi dla danego execution profile:

- świeży kontekst/sesja,
- filesystem namespace,
- tool capabilities,
- network allowlist,
- brak dostępu do vault/history/other lanes,
- kontrolowany broker delivery,
- kontrola shared logs/cache/error metadata zgodnie z profilem.

## DECLARED

Dopuszczalne dla manualnych workflows. Operator/executor deklaruje dostępne kanały, ale system nie twierdzi, że je wymusił.

## UNKNOWN

Brak wystarczającego provenance. Taki attempt nie może kwalifikować verified blind-origin claims.

`CONTAMINATED` jest osobną oceną odnoszącą się do forbidden knowledge i momentu exposure; nie zastępuje klasy izolacji. Authority-bearing refs wskazują dokładnie canonical `CONTAMINATION_ASSESSMENT` i `ISOLATION_QUALIFICATION` z Data & Artifact Contracts; nie wolno zastępować ich inline booleanem ani deklaracją promptu.

## 9.1. ISOLATION_BASELINE_PROFILE_V1

Candidate foundation definiuje inspectable baseline channel matrix dla co najmniej: session/model memory, filesystem, report directories, logs/shell history, clipboard, network, tools/plugins, resolver traversal, filenames/hashes/metadata oraz cross-session state. Dla każdego channel class profile wskazuje control, witness/evidence, kryteria `ENFORCED`, kryteria `DECLARED`, unknown handling i forbidden-knowledge class. Brak witnessu dla materialnego channelu nie może dać `ENFORCED`. Profile nie twierdzi, że kontroluje pretraining/cały host poza zadeklarowanym trust boundary.

---

# 10. Knowledge State

Knowledge State jest immutable, attempt-bound representation **zarejestrowanych/potencjalnych exposures i dozwolonych views**.

Minimalnie:

```text
knowledge_state_revision
attempt_creation_ref
previous_knowledge_state_ref optional
accepted_input_cut
policy/view refs
exposure/grant refs
known contamination refs
```

Zasady:

1. Nowy lane/attempt ID nie usuwa wcześniejszej exposure tego samego wykonawcy, jeżeli execution profile nie ustanowił nowego kwalifikowanego kontekstu.
2. Potential exposure jest monotoniczne w ramach Attempt.
3. Grant zostaje uznany za potential exposure od accepted grant, **przed** fizycznym ACK delivery.
4. Brak ACK nie przywraca blindness.
5. KnowledgeState nie dowodzi wiedzy z pretrainingu ani nieobserwowalnej pamięci człowieka.
6. `NEW_BLIND_DISCOVERY` wymaga discovery accepted przed reveal i wymaganej klasy isolation assurance.

---

# 11. Direct predecessor vs cumulative corpus

## 11.1. Canonical Direct Predecessor

Formalne lineage zachowuje jeden canonical predecessor dla danego StageRun, o ile StageSpec/policy nie definiuje innej relacji.

```text
E1 canonical → E2 canonical → E3 canonical → E4 canonical → E5 canonical
```

Predecessor ref wskazuje exact artifact/import assessment + source/policy compatibility.

## 11.2. Historical / Auxiliary Corpus

Dodatkowe raporty z poprzedniego etapu są auxiliary corpus, nie alternatywnymi predecessorami.

## 11.3. Holdout

Holdout jest osobną rolą corpus z własnym exposure lifecycle. Po ujawnieniu nie może być ponownie deklarowany jako unseen dla tego samego evaluatora/profile.

## 11.4. Legacy role

Legacy artifact może być historycznym predecessor, auxiliary member albo informational material po admission. Te role nie zmieniają raw bytes ani nie nadają historycznemu evidence automatycznie native-v2 quality.

---

# 12. CorpusManifest / Corpus Snapshot

Corpus snapshot jest immutable, content-bound zbiorem exact member revisions oraz ich admissibility assessments.

Minimalny model:

```text
corpus_role
member refs[]
admissibility assessment refs[]
source generation binding
policy/protocol binding
exposure class
ordering semantics
```

Zmiana membera, jego revision lub current admissibility tworzy nowy Corpus Snapshot. Stary snapshot pozostaje historycznym faktem.

Corpus snapshot NIE może self-hashować własnego digestu w preimage. Exact canonical profile definiuje Data Contracts/ADR.

---

# 13. Claim Quarantine Engine

Claim Quarantine jest **positive-view systemem**, nie tylko usuwaniem kilku pól z reportu.

Dla każdej fazy istnieje `ProjectionPolicy` i `ViewManifest` określające dokładnie:

- allowed fields,
- opaque view references,
- dozwolony resolver closure,
- redacted provenance,
- filenames/labels allowed or hidden,
- whether evidence payload may be resolved,
- producer/lane visibility,
- severity/support-count visibility.

Capability broker dostarcza tylko bytes należące do zaakceptowanego view graph.

Zasada:

```text
RAW REF
≠
VIEW REF
```

ViewRef nie może zostać użyty jako locator do raw artifact poza brokerem.

Jeżeli transitive resolver ujawni niedozwolony artifact, delivery jest `VIEW_REJECTED`; jeśli treść została już potencjalnie ujawniona, Knowledge State i contamination muszą zostać zaktualizowane konserwatywnie.

---

# 14. Surface Inventory Engine

## 14.1. Collector model

Collector nie zwraca wyłącznie listy surfaces. Dla assigned input set zwraca także terminal disposition dla każdego inputu/capability domain.

```text
collect(assigned_source_manifest, collector_profile)
→ CollectionRun
```

`CollectionRun` obejmuje:

```text
assigned inputs
collector version/capabilities
parsed/collected inputs
unsupported inputs
excluded inputs
failed inputs
warnings/errors
runtime/manual additions
completion status
```

Exit code 0 nie oznacza kompletnego inventory.

## 14.2. Input dispositions i ScopeState

To są dwa różne kontrakty. Każdy assigned input otrzymuje `InputDisposition`:

```text
COLLECTED
UNSUPPORTED
EXCLUDED
COLLECTION_FAILED
PARSING_FAILED
PROVISIONAL
```

`PROVISIONAL` nie jest terminalnym disposition AF-INV-1; jest dozwolone tylko w pośredniej inventory revision. StageCompletion/STOP wymagający pełnego input accounting blokuje się, dopóki assigned input pozostaje `PROVISIONAL`. `UNSUPPORTED`/`EXCLUDED` opisują obsługę inputu, a `UNSUPPORTED_SCOPE`/`EXCLUDED_SCOPE` — wpływ na scope.

Inventory revision wyprowadza/utrwala odrębny `ScopeState`:

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

`ScopeState.PROVISIONAL_SCOPE` i `InputDisposition.PROVISIONAL` są różnymi typed enum values; pierwszy opisuje pośredni denominator/scope model, drugi pośrednie rozliczenie assigned inputu. Żaden nie może zastępować drugiego ani spełnić terminalnego accounting/completion gate.

`UNKNOWN_SCOPE` służy do jawnego reprezentowania materialnie nierozliczonego obszaru, który nie może zostać przypisany do konkretnego inputu. `EXCLUDED_SCOPE` wymaga zaakceptowanej scope decision. Żaden z tych stanów nie jest automatycznie coverage PASS.

## 14.3. SurfaceRecord

```text
surface logical key / revision
source generation ref
category
canonical anchor descriptor
entry point
trust boundary attributes
external input
persistence
concurrency
privilege
irreversible effect
fan-out
collector/manual/runtime provenance
risk attributes
```

Stable SurfaceKey profile jest wersjonowany per category/language/runtime. Niejednoznaczność identity daje `PROVISIONAL`, nie heurystyczny merge.

## 14.4. Inventory revision

Późno odkryty subsystem tworzy nową inventory revision. Wszystkie summaries/gates zależne od starszego scope muszą zostać ponownie ocenione na nowym cut.

Unknown unknowns poza zadeklarowanym universe pozostają granicą gwarancji systemu.

---

# 15. Invariant Registry

Invariant jest wersjonowanym, scoped contractem, a nie tylko etykietą findingu.

```text
invariant_id
invariant_revision
source/campaign applicability
scope selector
statement
risk/materiality policy refs
violation semantics
related surfaces
owner/authority
status/history refs
```

Zmiana treści, scope lub quantifier tworzy nową revision.

`REQUIRED_EVIDENCE_DEPTH` nie jest autorytatywnym polem. Wymagane testy wyrażają **Coverage Obligations**.

Krytyczne surfaces bez findings nadal muszą mieć materialne invariants/obligations.

---

# 16. Traceability Graph

Traceability Graph jest **derived projection** z typed accepted refs oraz jawnych semantic relations.

```text
SOURCE/SCOPE
→ SURFACE
→ INVARIANT
→ COVERAGE OBLIGATION
→ HYPOTHESIS / DISCOVERY
→ EXPERIMENT / EXECUTION
→ OBSERVATION
→ DEPENDENCY / INDEPENDENCE QUALIFICATION
→ FINDING / SOUND / REJECTED / UNRESOLVED
```

Graph nie może:

- ustanawiać nowego truth status przez similarity,
- automatycznie przenosić evidence między root-cause members,
- tworzyć current support z invalidated observation,
- nadpisywać canonical history.

Każdy export grafu wskazuje `as_of_head` i `projector_hash`.

---

# 17. Coverage Engine

## 17.1. Coverage Obligation jako authority

Coverage engine operuje na sparse graph obowiązków, nie na jednym scalar depth.

```text
CoverageObligation =
    target scope/surface
  × invariant revision
  × scenario class
  × environment profile
  × qualification requirement
  × acceptance predicate
  × policy obligation key
```

Status kwalifikacji i substantive outcome są **odrębnymi osiami**.

```text
qualification_status = UNASSESSED | IN_PROGRESS | QUALIFIED | BLOCKED | STALE
substantive_outcome  = NO_VIOLATION_OBSERVED | VIOLATION_CONFIRMED | INCONCLUSIVE
```

`NOT_APPLICABLE` i `WAIVED` są osobnymi accepted decisions; contradiction jest osobnym blocker/ref. Kwalifikowane `VIOLATION_CONFIRMED` może spełnić investigation obligation. `INCONCLUSIVE`, `WAIVED`, N/A, UNKNOWN i BLOCKED nie są decisive PASS.

## 17.2. Derived D0–D5

D0–D5 pozostaje konserwatywnym widokiem prezentacyjnym:

```text
D0 no qualified work
D1 static obligations
D2 dynamic happy/negative obligations
D3 fault/failure obligations
D4 stateful/temporal/concurrency/adversarial obligations
D5 selected compositional/mutation/replay obligations
```

D-level MUSI być wyliczany z applicable qualified obligations. Nie może być ręcznie ustawiany.

## 17.3. Breadth

Breadth jest liczone względem konkretnej inventory revision i obowiązków policy. Raportuje równolegle:

- known investigated scope,
- known unobserved scope,
- unsupported scope,
- excluded/waived scope,
- unresolved/provisional scope.

## 17.4. Anti-gaming

Coverage engine MUSI odrzucać:

- podniesienie całej surface jednym testem,
- D5 przez nieaktywną mutację,
- sztuczne split surfaces bez odpowiadającego policy weighting,
- zachowanie support po invalidation,
- usunięcie trudnego scope przez zmianę denominatora bez scope decision.

---

# 18. Gap Engine

Gap Engine jest derived plannerem.

Wejścia:

- current inventory revision,
- coverage obligations,
- current evidence qualifications,
- unresolved contradictions,
- unsupported/unknown scope,
- criticality/risk profile,
- required stages/lanes.

Wyjście:

```text
GapCandidate
scope
missing obligation / unresolved reason
risk rationale
recommended method families
blocking relationship
```

Gap Map nie jest authority STOP. STOP ocenia exact obligations i reasons bezpośrednio.

---

# 19. Priority Scheduler

Scheduler przydziela budżet według jawnej policy, uwzględniając m.in.:

- trust boundaries,
- privilege,
- persistence,
- concurrency,
- irreversible effects,
- fan-out,
- external inputs,
- low audit coverage,
- unsupported/unobserved scope,
- prior defect density,
- remaining obligations.

Risk score jest planning aid. Nie jest dowodem materiality ani severity.

Exploration budget jest policy-configurable; przykładowe proporcje nie są globalnym invariantem BDB.

---

# 20. Hypothesis / Discovery model

## 20.1. DiscoveryRecorded

Discovery jest first-class accepted fact, jeżeli jego provenance ma być używane do novelty/blindness metrics.

```text
discovery_id/revision
lane_run / attempt
source generation
knowledge state revision
accepted history cut
surface/location/mechanism candidate
producer/method
own observation refs
```

Discovery MUSI być accepted przed potential reveal, jeżeli później ma być klasyfikowane jako pre-reveal.

## 20.2. Hypothesis

Hypothesis jest falsyfikowalnym twierdzeniem/planem dalszego badania.

```text
hypothesis_id
hypothesis_revision
precursor discovery optional
claim/question
scope
invariant/obligation refs
falsification idea
state
```

Przykładowy lifecycle:

```text
PROPOSED
PREREGISTERED
TESTING
CONFIRMED
REJECTED
UNRESOLVED
BLOCKED
```

`TESTED` jako historyczny legacy value ma jawne mapowanie; nie jest automatycznie `CONFIRMED`.

## 20.3. Novelty i previous false negative

Oddzielne decyzje:

- exposure-at-discovery assessment,
- confirmation mode,
- prior-corpus match,
- novelty,
- false-negative relation,
- tool/producer origin.

Derived labels typu `NEW_BLIND_DISCOVERY` nie są ręcznie wpisywanym jednym enumem.

---

# 21. Experiment Engine

## 21.1. ExperimentSpec

Materialny eksperyment powinien zostać prerejestrowany przed execution, jeżeli claim ma korzystać z preregistration assurance.

```text
experiment_id
experiment_plan_revision
hypothesis/invariant/obligation refs
subject baseline ref
target execution variant
trigger
expected safe behavior
expected violation behavior
falsifier
controls
observation path requirements
environment/dependency/harness/fixture refs
fault/seed/generator profile
cleanup
planning_mode
```

`planning_mode` rozróżnia `PREREGISTERED`, `EXPLORATORY`, `LEGACY_IMPORTED` itd.

## 21.2. ExecutionDescriptor i execution facts

Execution intent jest odrębnym bytem od planu i od późniejszego resultu:

```text
ExecutionDescriptor:
  execution_descriptor_id
  experiment_plan_revision
  exact subject baseline
  exact executed variant
  runtime/environment/dependency set
  harness revision
  fixture refs
  runner/executor profile
  execution_input_history_cut
```

Runtime observations, `FaultActivationRecord`, cleanup/reset records wskazują wcześniejszy `ExecutionDescriptor`. Nie wskazują future `ExecutionResult`.

## 21.3. ExperimentResult / ExecutionResult

```text
ExecutionResult:
  execution_result_id
  execution_descriptor_ref
  start/end observation refs
  raw output refs
  fault_activation_record_ref optional
  cleanup_result_ref
  reset_verification_ref optional
```

Result jest zbiorem raw observations + execution facts i wskazuje je jednostronnie. `FaultRunRecord → ExecutionResult → FaultRunRecord` jest niedozwolonym cycle. Result nie nadaje sam sobie epistemic `SUPPORTED` ani coverage depth.

---

# 22. Evidence Engine

Evidence Engine rozdziela trzy warstwy:

```text
RAW OBSERVATION
→ DEPENDENCY / INDEPENDENCE QUALIFICATION
→ APPLICABILITY / CLAIM ASSESSMENT
```

## 22.1. Observation dependency graph

Każdy materialny observation path może wskazywać dependencies, np.:

- parser,
- deserializer,
- cache,
- DB abstraction,
- test harness,
- fixture generator,
- model/agent,
- network boundary,
- read path,
- environment.

## 22.2. Claim-relative independence

Independence odpowiada na pytanie:

> Jakie materialne failure assumptions dotyczące tego claimu ten observer rzeczywiście przełamuje?

Nie ma reguły „fresh process zawsze = mocniejszy evidence”. Dwa procesy używające tego samego wadliwego oracle mogą nadal być zależne.

## 22.3. Applicability

Evidence applicability jest relacją:

```text
EVIDENCE
× CLAIM REVISION
× SUBJECT BASELINE
× EXECUTION VARIANT
× ENVIRONMENT / DEPENDENCIES / HARNESS / FIXTURE
```

Current state może być m.in.:

```text
ACTIVE
SCOPED
STALE
INVALIDATED
BLOCKED
CONFLICTED
```

## 22.4. Transitive invalidation

Invalidation może być wymagana **bez zmiany SourceGeneration** — np. po wykryciu błędu harnessu, fixture, dependency, parsera lub shared oracle. Stały source SHA nie chroni evidence applicability przed takim downgrade.

Invalidation jednego decisive observation może unieważnić:

- qualification,
- finding support,
- coverage obligation result,
- SOUND,
- challenger result,
- STOP input.

Historyczny fakt, że wcześniejsza decyzja została zaakceptowana, pozostaje w canonical history; current projection pokazuje utratę supportu.

---

# 23. Replay Capsule

Replay Capsule wspiera reproducibility obserwacji, nie automatycznie correctness oracle.

Zawiera exact:

```text
subject baseline
execution variant
environment/dependencies
fixture/seed/generator
harness
command/action description
observation path
raw evidence refs
cleanup
expected qualification scope
```

Independent replay posiada własny execution/provenance i nie może dziedziczyć `independent=true` z pierwszego runu.

Replay conflict prowadzi do rekwalifikacji observation/evidence, nie do majority vote.

---

# 24. Finding model

Finding jest agregatem scoped claimu i późniejszych adjudication decisions, nie prostym rekordem „bug=true”.

Canonical `FindingClaimRevision` zawiera wyłącznie:

```text
finding_id / claim revision
claim statement + scope
category
violated invariant refs
origin/discovery relations
limitations
```

Nie zawiera evidence, M/R/I, severity, lifecycle ani RootCause backlinków. `EvidenceQualification` wskazuje już istniejący claim revision, a późniejsze canonical `FindingAxisAssessment` (`MECHANISM/REACHABILITY/IMPACT/SEVERITY`) wskazują exact EvidenceQualification refs. `FindingAdjudicationDecision` wiąże te axis assessment refs + lifecycle/support/counterevidence na exact input cut; kolejna adjudication revision wskazuje poprzednią tylko wstecz. RootCause revision również wskazuje FindingClaimRevision przez własne `membership_edges[]`, a backlink jest derived.

Metoda obserwacji nie jest wartością Impact. `fresh instance`, `independent observer`, `external boundary` należą do evidence qualification. Final statement nie może przekraczać qualified scope.

Finding history jest zapisywana jako accepted revisions/events w canonical history. `Finding Change Ledger` może być eksportem, nie drugim authority.

---

# 25. Root Cause model

Root Cause jest wersjonowanym modelem wyjaśnienia i grupowania findings.

```text
root_cause_id
root_cause_revision
mechanism description
membership_edges[]
causal roles / multi-causal condition
scope
repair relationship optional
confidence/limitations
```

Zasady:

- merge nie zmienia truth status individual findings,
- Finding body nie zawiera canonical backlinku do przyszłego RootCause; authority membership istnieje wyłącznie jako `RootCauseRevision.membership_edges[]` wskazujące exact FindingClaimRevision, bez osobnego `RootCauseMembershipAccepted`; backlink/graph edge jest derived,
- evidence membera nie staje się automatycznie evidence innych members,
- split/merge pozostawia historię; nowe root-cause revisions wskazują **wstecz** predecessor root causes, predecessor nie wskazuje future successors,
- multi-causal finding może używać AND/OR/hyperedge semantics,
- cross-source root-cause continuity jest osobnym mappingiem, nie automatyczną identity.

---

# 26. Contradiction Engine

Contradiction jest scope-aware relacją pomiędzy materialnymi claims/assessments.

Nie stosuje większości głosów.

Minimalny model rozdziela immutable contradiction revision od późniejszej resolution decision:

```text
ContradictionRevision:
  contradiction_id / revision
  predecessor_contradiction_revision_ref optional
  claim sides / revisions
  scope/environment relation
  support/counterevidence refs
  required falsifier / next obligation
  state
  resolution_decision_ref optional   # tylko backward ref w successor revision

ContradictionResolutionDecision:
  contradiction_prior_revision_ref
  resolution_input_history_cut
  resolution type / resolved scope
  basis refs
  resulting status
```

Resolution decision nie wskazuje future successor revision. Successor contradiction revision może później wskazać accepted resolution decision; reopen jest kolejną backward-linked revision. Resolution types mogą obejmować:

- refutation in same scope,
- scope split,
- harness/oracle invalidation,
- invariant revision,
- accepted limitation,
- unresolved/blocking.

`TESTING` i `BLOCKED` nadal oznaczają nierozstrzygnięte zobowiązanie; sama zmiana enumu z `OPEN` nie usuwa blocker semantics.

---

# 27. E1 architecture

E1 jest discovery ensemble:

```text
E1-A General Systems
E1-B Security / Trust / Authority
E1-C State / Persistence / Recovery
E1-D Data / Catalog / Parsing
E1-E Frontend / Concurrency / Resources / Oracle
+ machine-assisted / wildcard lanes
```

Każdy lane:

- ten sam Source Generation,
- własny LaneRun/Attempt,
- wymagany isolation profile,
- source-only lub inny jawnie dozwolony initial view,
- własne DiscoveryRecorded facts,
- brak dostępu do innych E1 findings przed dozwolonym reveal.

Po E1 powstaje immutable `StageCompletion` oraz derived ensemble/contribution views. `CONTRIBUTION_LEDGER` nie jest drugim źródłem prawdy.

E1 completion nie oznacza globalnego STOP PASS.

---

# 28. E2 architecture

E2 jest convergence/adjudication stage.

```text
BLIND / PRE-REPORT DISCOVERY
→ sealed precursor/checkpoint
→ allowed Claim Quarantine view
→ individual adjudication
→ controlled predecessor/auxiliary reveal
→ root-cause normalization
→ shadow review
→ contradiction resolution obligations
→ E2 StageCompletion
```

F1/F2 legacy semantics mogą być używane w migration profile, ale native v2 architecture wiąże ich funkcję z accepted history cut i capability grants.

E2 ma jeden canonical StageCompletion/output relationship, ale może zachować wiele lane findings i auxiliary reports.

---

# 29. E3 architecture

E3 jest outward-discovery stage.

```text
BLIND NOVELTY LANES
→ accepted discoveries/checkpoint
→ positive coverage/gap view reveal
→ GAP-DIRECTED SEARCH
→ cumulative corpus reveal
→ holdout reveal when policy allows
→ current obligation evaluation
→ E3 StageCompletion
```

Coverage reveal NIE oznacza raw `Coverage Ledger`; broker tworzy phase-specific view bez niedozwolonego transitive provenance.

E3 może zakończyć swój program pracy przy spełnionych StageSpec obligations, ale globalny STOP przed E4/E5 powinien dać `CONTINUE_REQUIRED` z `REQUIRED_STAGES_PENDING`, nie fikcyjny PASS.

---

# 30. E4 architecture

E4 pogłębia materialne invariants i root-cause families, ale nie jest ograniczone do wcześniejszych findings.

Moduły/capabilities:

```text
STATE MODEL
TEMPORAL INVARIANT
PROPERTY/STATEFUL TEST
BOUNDED MODEL EXPLORATION
CONCURRENCY SCHEDULE
CRASH POINT
RECOVERY / ENDURANCE
CAUSAL CHAIN
MODEL ↔ IMPLEMENTATION CONFORMANCE
```

Każdy model ma:

- mapping implementation events/state,
- abstraction assumptions,
- bounds,
- omitted states,
- fairness/time assumptions,
- conformance evidence.

Proof o modelu nie jest automatycznie proof o implementation.

Krytyczny subsystem bez findings może nadal mieć E4 obligations.

---

# 31. E5 architecture

E5 jest podzielone na dwie normatywne subphases rozdzielone immutable candidate:

```text
E5A — ATTACK / SYNTHESIS PRODUCTION
  FAILURE INTERACTION GRAPH
  PAIRWISE / SELECTED N-WAY TESTS
  IMPLEMENTATION MUTATION
  ORACLE MUTATION
  SPECIFICATION CHALLENGE
  AUDITOR CALIBRATION
        ↓
  CANDIDATE ASSURANCE CASE (exact immutable revision)
        ↓
E5B — FINAL CHALLENGE
  FALSE-POSITIVE SKEPTIC
  FALSE-NEGATIVE HUNTER
        ↓
  E5 StageCompletion
        ↓
  FINAL_POST_E5 STOP
```

Residual Risk Register jest current assessment/projection wejściowym candidate/STOP, nie artifactem pozwalającym odwrócić powyższą kolejność.

Oracle mutation używa kontrastowego protocol z known-defective target i activation witness. Normatywna kwalifikacja opiera się na macierzy **2×2**: clean/known-defective target × strong/weakened oracle. Sam PASS po usunięciu obserwacji na clean target nie dowodzi słabego oracle. Machine outcome taxonomy i exact controls są zdefiniowane w Data Contracts i testowane w Test & Self-Audit Plan.

Candidate Assurance Case wiąże exact FindingClaimRevision **oraz** odpowiadające current FindingAdjudicationDecision refs; claim bez pinned adjudication nie może być traktowany jako current finding state. Final challengers badają frozen candidate case. W baseline R5.3 materialna rewizja Candidate Assurance Case po challenge wymaga nowych **obu** required challenger roles (skeptic + hunter) dla nowej exact candidate revision; scoped reuse wymaga przyszłego, osobno kwalifikowanego profile. Challenger assignment jest immutable i wskazuje exact Candidate revision; ChallengerResult wskazuje assignment + tę samą candidate revision i nie zawiera STOP/conclusion refs. Materialne counterevidence tworzy nową candidate revision zamiast przepisywania starego resultu.

---

# 32. STOP Gate architecture

STOP jest pure evaluator nad immutable accepted `StopInput`, który pinuje `StopInputSnapshot`, HistoryCut, evaluator/policy/spec/profile bindings oraz stage/coverage/evidence closure. Każdy canonical `StopEvaluation` MUSI wskazywać exact `stop_input_ref`; nie mutuje facts ani nie kopiuje input bindings jako drugiej authority reprezentacji w celu uzyskania PASS.
StopInput pinuje **direct canonical mandatory obligation revisions + current qualification refs + exact evidence invalidation refs**; derived Coverage Summary ani scalar invalidation summary nie mogą zastąpić tych authority-bearing refs. StopInputSnapshot jest wyłącznie derived aid i musi equality-bind exact cut/direct refs. StopEvaluation obligation outputs są podzbiorami exact mandatory set. Finalization chain Conclusion→FinalCase→ReleaseQualification musi zachować exact STOP/candidate/source equality bindings.

## 32.1. Cztery normatywne osie

```text
continuation_decision:
  PASS | CONTINUE_REQUIRED | E6_REQUIRED | BLOCKED

termination_state:
  OPEN | COMPLETED | COMPLETED_LIMITED

assurance_level:
  ADEQUATE_FOR_DECLARED_SCOPE | BOUNDED | INSUFFICIENT

release_readiness:
  READY | READY_WITH_RESIDUAL_RISK | TECHNICALLY_NOT_READY | QUALIFICATION_BLOCKED
```

`continuation_decision` jest wynikiem STOP. `termination_state` zmienia osobny accepted `ConcludeCampaign` command. `release_readiness` jest odrębną product qualification. STOP PASS nie implikuje READY.
Dla `evaluation_context=INTERMEDIATE` release axis jest fail-closed: `READY` i `READY_WITH_RESIDUAL_RISK` są niedozwolone; jeśli current evidence już wykazuje defect wykluczający release, dozwolone jest `TECHNICALLY_NOT_READY`, w przeciwnym razie wynik release axis to `QUALIFICATION_BLOCKED`. Exact contract authority pozostaje w Data & Artifact Contracts.

## 32.2. Exact inputs

StopInput obejmuje exact revisions/cut m.in.:

- `stop_input_snapshot_ref`, pinned evaluator/policy revision,
- exact `required_stage_set` oraz required StageSpec refs,
- completed StageCompletion refs i jawny `pending_required_stage_refs[]`,
- current inventory/scope revision,
- applicable coverage obligations i ich qualification assessments,
- current evidence applicability/qualifications,
- unresolved contradictions,
- candidate assurance case revision **optional-by-evaluation-context**,
- challenger results związane z tą exact revision **optional-by-evaluation-context**,
- residual-risk/waiver decisions,
- effort/budget profile i wykonanie,
- saturation observations,
- legacy/admission limitations,
- current policy/spec refs,
- continuation/budget authorization.

## 32.3. Hard semantics / precedence

- authority/source/policy/admission/cut failure → `BLOCKED` + `INSUFFICIENT`,
- niewykonalny/brak-budżetu material obligation → `BLOCKED`,
- pending zwykłe etapy E1–E5 przy wykonalnej pracy → `CONTINUE_REQUIRED`,
- post-E5 wykonalne material gaps przy approved bounded plan → `E6_REQUIRED`,
- komplet mandatory applicable obligations + scope/challenge/effort prerequisites → `PASS` + `ADEQUATE_FOR_DECLARED_SCOPE`.

`UNKNOWN`, `WAIVED`, `BLOCKED`, `NOT_APPLICABLE`, `INVALIDATED` i unresolved material contradictions są rozliczane jawnie; żaden nie jest ukrytym PASS. Pending E4/E5 po E3 nie uruchamia E6 jako substytutu normalnego planu.

## 32.4. Release qualification

Release lifecycle rozróżnia `STOP_AXIS_MATERIALIZATION`, pierwszą `FRESH_RELEASE_QUALIFICATION` po release-specific drift oraz późniejsze `RELEASE_REASSESSMENT(previous_release_qualification_ref)`. Pierwsza fresh qualification po drift nie potrzebuje fabricated predecessor. Jeżeli drift narusza audit assurance basis, release layer nie może go naprawić — uruchamia successor campaign.

Znany nieakceptowalny material defect → `TECHNICALLY_NOT_READY`. Brak dowodu wymaganego przez release profile → `QUALIFICATION_BLOCKED`. Formalnie zaakceptowane residual risks mogą dać `READY_WITH_RESIDUAL_RISK`; ich akceptacja nie zmienia truth statusu findingu.

## 32.5. Saturation

Saturation jest sygnałem planistycznym, nie dowodem completeness. Policy/E0 definiuje `EffortProfile`; liczby rounds/method families/budgets są pinned profile values, nie globalnym invariantem architektury. Brak danych = `INSUFFICIENT_DATA`.

---

# 33. Adaptive E6

E6 powstaje tylko z jawnego STOP reason set i dziedziczy globalne constraints.

E6 MUSI:

- zachować tę samą Source Generation,
- zachować trust/policy root lub jawny upgrade bez osłabiania historycznego contract,
- dziedziczyć unresolved hard obligations,
- mieć ograniczony scope odpowiadający failed conditions,
- posiadać własny immutable StageSpec revision,
- wrócić do globalnego STOP po completion.

E6 NIE MOŻE:

- usunąć surface/invariant z scope, żeby uzyskać PASS,
- obniżyć required evidence qualification bez jawnego new policy profile i bounded conclusion,
- przekształcić UNKNOWN w PASS,
- przepisać wcześniejszego history cut.

Przykładowe generated aliases:

```text
E6_CONCURRENCY_GAP
E6_SECURITY_GAP
E6_UNRESOLVED_HIGH
E6_ORACLE_REPAIR
```

Alias jest prezentacją; authority stanowi StageSpec revision.

---

# 34. Legacy Compatibility Layer

Legacy layer ma trzy oddzielne zadania:

1. **raw preservation / parser safety**,
2. **mechanical legacy validation** zgodnie z pinned v1 semantics,
3. **current v2 import/admission assessment**.

Obsługuje:

- v1.4.4 variant IDs,
- legacy RUN_MANIFEST,
- legacy F1/F2 bundles,
- legacy LINEAGE_MANIFEST,
- legacy artifact names,
- legacy validators.

Nie przepisywać legacy artifacts do nowych schemas.

Current wrapper/import record wskazuje:

```text
raw artifact digest/ref
legacy schema/profile
mechanical validation level
source reconciliation
exposure confidence
current admissibility role
interpretation revision
limitations
```

Historyczne bytes są facts; current interpretation jest nową decyzją.

---

# 35. Historyczne E1/E2

Obecne:

```text
E1_SOL_BASE
E2_SOL_ITERACJA_1
```

pozostają immutable.

Native v2 może użyć ich jako canonical predecessor/auxiliary corpus po admission, ale nie może retrospektywnie twierdzić, że:

- historycznie wykonano E0 v2,
- historyczna blindness była ENFORCED bez dowodu,
- legacy D/coverage oznacza native Coverage Obligation qualification,
- legacy evidence posiada native v2 independence/applicability.

Bootstrap tworzy **current v2 constitution/inventory/obligations** od chwili upgrade, nie backdates tych records.

---

# 36. Variant model v2

Centralna abstrakcja `variant_id = audit_level + tool + plus_pliki` zostaje rozdzielona na:

```text
StageSpec revision
LaneSpec revision
ExecutorSpec revision
DeliverySpec revision
Policy bundle revision
```

Human-readable variant alias może być generowany dla ergonomii.

Jeżeli potrzebny jest compiled configuration identity, jest content digestem exact refs, a nie semantycznym źródłem authority.

---

# 37. ExecutorSpec

ExecutorSpec/ExecutorProfile określa capabilities i ograniczenia wykonania:

```text
executor_profile_id/revision
tool/model family
execution mode
session/context guarantees
filesystem capabilities
network capabilities
tool capabilities
vault access = forbidden/controlled
other-lane access
secret handling
external/destructive permissions
supported isolation assurance claims
runtime profile
```

Ta sama LaneSpec może być uruchamiana przez różne executory tylko wtedy, gdy spełniają wymagania lane/policy.

Nazwa modelu/toola nie dowodzi niezależności evidence.

---

# 38. DeliverySpec

DeliverySpec opisuje kanał i capability model:

```text
delivery_profile_id/revision
transport mode
broker enforcement capabilities
view format
required physical/logical handoffs
attestation/receipt behavior
clipboard/folder/manual limitations
resolver capabilities
```

Manual clipboard/folder może być wspierany, ale nie otrzymuje ENFORCED isolation, jeśli BDB nie kontroluje wszystkich materialnych kanałów odbiorcy.

---

# 39. Prompt Compiler

Prompt Compiler pracuje na pinned immutable inputs:

```text
protocol/policy revision
StageSpec revision
LaneSpec revision
ExecutorSpec revision
DeliverySpec revision
allowed ViewManifest
source identity ref
artifact/schema contracts
runtime parameters declared as inputs
```

Output rozdziela:

- immutable template/build artifact,
- runtime instance z jawnymi values/IDs/cuts.

Każdy output posiada exact digest i dependency manifest.

Compiler nie może sam rozszerzyć knowledge view ani zignorować broker policy.

---

# 40. Runtime patches

Nie wolno używać niekontrolowanych `.replace()` jako podstawowej semantyki compiler/runtime.

Preferowane:

```text
typed template AST/fragments
+ validated runtime inputs
+ explicit policy/view refs
→ deterministic rendering
```

Legacy patching może istnieć wyłącznie w compatibility boundary, z golden fixtures i niezmiennym historycznym output expectation.

---

# 41. Schema Registry

Każdy canonical machine object ma:

```text
kind / schema_id
schema_version
```

Registry wiąże exact pair z walidatorem i semantics version.

Zasady:

- unknown mandatory version → `UNSUPPORTED_CONTRACT`,
- `additionalProperties=false` poza wersjonowanym extension namespace,
- extension nie wpływa na gate bez jawnej policy support,
- schema upgrade nie interpretuje wstecz canonical history pod nowymi regułami,
- migration tworzy derived representation/equivalence assessment.

---

# 42. Canonical serialization

Exact canonicalization/identity contract, w tym `RawDigest`, `ObjectDigest`, `BDB-CJSON-1` i typed refs, jest normowany w `BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS.md` oraz ADR-006; Architecture nie definiuje alternatywnego profilu.

Architecture wymaga jedynie niezmiennych zasad:

1. exact raw bytes digest i canonical object digest to różne typy,
2. object preimage nie zawiera własnego digestu,
3. refs są typed i wskazują exact revision,
4. sequence vs set ordering jest określone przez schema,
5. duplicate keys / unsupported numeric forms są fail-closed,
6. canonicalization nie zmienia raw legacy/evidence bytes,
7. spec/policy/schema hashes są częścią run binding.

Architektura NIE utrzymuje własnego alternatywnego JSON canonicalization profile.

---

# 43. Storage model

## 43.1. Normatywne wymagania

BDB wymaga **Transactional Canonical History Vault**, który zapewnia:

- one accepted head per campaign,
- serialized/guarded writes,
- atomic acceptance of commit + mandatory immutable object closure + receipt + new head,
- content-addressed immutable object revisions,
- idempotent command receipts,
- expected-head/entity-revision guards,
- recovery po crashu,
- możliwość rebuild projections,
- integralność accepted history,
- brak zapisywalnego dostępu executorów do vault w LOCAL_PINNED profile.

Backend produktu nie jest częścią semantyki BDB.

## 43.2. Reference implementation

Dla lokalnego baseline **SQLite może być referencyjnym backendem**, ponieważ ułatwia pojedynczą transakcyjną granicę i single-writer semantics. Konkretne journal/synchronous ustawienia należą do reference implementation profile/ADR i kwalifikacji runtime, nie do wiecznego contractu architektury.

Alternatywny backend jest dopuszczalny, jeżeli przejdzie te same authority/crash/idempotency/reference scenarios.

## 43.3. File-first exports

ZIP/JSON/JSONL/Markdown pozostają ważnymi przenośnymi artifacts i audytowalnymi exportami.

Export MUSI wskazywać:

```text
as_of_head
projector/exporter revision
source/policy refs
export digest
pin/trust class
```

Export nie staje się current authority po skopiowaniu do folderu obok nowszego vault.

---

# 44. Transactionality

## 44.1. Command envelope

Każdy materialny write command zawiera co najmniej:

```text
command_id
command_digest
campaign_id
actor authority
expected accepted head / allowed proposal mode
expected entity revisions
attempt/nonce where applicable
immutable input refs
```

## 44.2. Accepted commit

Commit wiąże:

```text
format version
campaign
commit sequence
parent commit hash
command ID/command digest
policy bundle ref
ordered typed events/decisions
object revision refs
```

Receipt wskazuje commit. Commit nie self-referuje receipt w preimage.

Nowe immutable objects jednego commitu mogą wskazywać wcześniejsze obiekty **tego samego commit closure** wyłącznie przez exact content refs i wyłącznie w acyklicznej topologicznej kolejności. History/acceptance refs nadal mogą wskazywać tylko prior accepted cut; żaden object nie wskazuje własnego/future objectu ani własnego accepting head/event.

## 44.3. Atomic acceptance protocol

1. Ingest/validate candidate bytes poza krytyczną write transaction, z resource limits.
2. Rozpocznij authority write transaction.
3. Sprawdź current head, command dedup, entity revisions, permissions i attempt eligibility.
4. Zweryfikuj state-dependent guards ponownie na tym samym locked cut.
5. Utrwal wszystkie mandatory immutable object bytes/revisions potrzebne przez accepted decision.
6. Utrwal CommitBody/events, receipt i nowy accepted head w tej samej durability domain.
7. Commit.
8. Przy niejednoznacznym ACK po recovery sprawdź receipt po `command_id`; nie ponawiaj ślepo efektu.
9. Dopiero po accepted commit aktualizuj projections i wykonuj dozwolone delivery.

## 44.4. Crash semantics

- crash przed COMMIT → brak accepted mutation,
- crash po durable COMMIT przed ACK → receipt istnieje; retry zwraca ten sam outcome,
- stale/corrupted projection → rebuild,
- corrupted accepted history/object closure → `VAULT_INTEGRITY_BLOCKED`, nie „obcięcie do ostatniego dobrego pliku” i sukces,
- checkpoint/gate/reveal są odrębnymi accepted decisions, chyba że policy jawnie definiuje atomowy composite command z tym samym semantic cut.

## 44.5. External effects

Baseline audit effects mają być disposable/controlled. Canonical history transaction nie daje automatycznej atomowości z nieodwracalnym zewnętrznym systemem. Live/destructive integrations potrzebują osobnego protocolu i nie są domyślnym foundation profile.

---

# 45. Security boundary aplikacji

Trust model:

| Actor / component | Baseline trust |
|---|---|
| Coordinator program + pinned policy root | trusted within qualified release/runtime |
| Host/OS/storage runtime | TCB for local profile |
| Executor | untrusted producer |
| Audited repository | untrusted evidence |
| External tool | untrusted producer unless separately qualified |
| Imported bundle | untrusted parser input |
| Operator/reviewer | authorized decision actor, not automatic oracle |

Repo nie może:

- zmienić policy/spec refs,
- zwiększyć permissions,
- rozszerzyć network scope,
- wyłączyć gate,
- dostać vault write capability,
- sterować compilerem przez README/comments.

## 45.1. Hash/trust granice

SHA-256 zapewnia byte binding względem znanej wartości. Nie zapewnia:

- truth,
- freshness,
- execution proof,
- complete-history authenticity,
- full-host rollback detection.

Baseline `LOCAL_PINNED` wykrywa podmianę/stale/fork względem trusted current vault/head. Pełny rollback całego host+vault bez niezależnego pin/witness jest poza gwarancją i musi być jawnie raportowany jako limit.

Podpisy/witness mogą być opcjonalnym mocniejszym profilem, nie baseline magicznym rozwiązaniem.

---

# 46. Destructive action policy

Domyślnie:

```text
destructive_permissions = NONE
external_state_change = FORBIDDEN
```

Jeżeli eksperyment wymaga destrukcyjnego/live efektu, Stage/Lane/Experiment musi jawnie określić:

- target,
- authorization,
- ownership proof,
- sandbox/disposable boundary,
- rollback/cleanup,
- maximum blast radius,
- evidence of performed action.

Repo nie może samo podnieść tej policy.

---

# 47. Error model

Błędy są typowane i rozdzielają co najmniej:

```text
VALIDATION_ERROR
UNSUPPORTED_CONTRACT
WRONG_BINDING
STALE_INPUT
STATE_CONFLICT
RESULT_CONFLICT
ID_REUSE_CONFLICT
HISTORY_CONFLICT
VAULT_INTEGRITY_BLOCKED
RESOURCE_BLOCKED
VIEW_REJECTED
BLIND_SLOT_NOT_SATISFIED
EVIDENCE_QUALIFICATION_REJECTED
STAGE_COMPLETION_BLOCKED
ADMISSION_BLOCKED
POLICY_BLOCKED
```

Błąd parsera/validatora nie może zostać znormalizowany do „empty result / PASS”.

Każdy error posiada:

- stable code,
- human message,
- machine details,
- relevant refs/cut,
- retryability/classification.

---

# 48. Validation result model

Validator zwraca structured result:

```text
status = PASS | FAIL | BLOCKED | UNSUPPORTED
error_codes[]
warning_codes[]
validated refs[]
input digests[]
policy/schema refs
history cut optional
limitations[]
```

`PASS` walidatora oznacza spełnienie jego exact contractu, nie automatycznie truth artifactu ani release readiness.

Legacy preservation validator i independent correctness validator mają osobne result types/gates.

---

# 49. Testability

Core MUSI działać bez GUI/clipboard.

API powinno umożliwiać testy:

```python
receipt = coordinator.submit(command)
state = projector.rebuild(campaign, head=receipt.head)
qualification = evidence_service.qualify(...)
stop = stop_evaluator.evaluate(stop_input)
```

Najważniejsze foundation acceptance scenarios obejmują:

- crash przed/po commit,
- duplicate command,
- conflicting result slot,
- stale projection,
- fork/rollback relative to pin,
- contaminated lane,
- transitive reveal leak,
- missing/unsupported surface,
- shared oracle,
- invalidated decisive evidence,
- insufficient-data STOP,
- legacy admission A/B/C.

UI nie może mieć ukrytej semantyki, której nie ma core API.

---

# 50. CLI

Docelowe przykłady:

```text
bdb-audit campaign create
bdb-audit campaign status
bdb-audit campaign verify-history
bdb-audit stage plan
bdb-audit stage status
bdb-audit lane assign
bdb-audit attempt status
bdb-audit validate legacy-bundle.zip
bdb-audit import legacy-bundle.zip
bdb-audit reveal prepare
bdb-audit coverage obligations
bdb-audit evidence qualify
bdb-audit stop evaluate
bdb-audit export
bdb-audit self-test
bdb-audit build-standalone
```

Interaktywny mode jest wrapperem nad tym samym command/coordinator API.

---

# 51. Standalone build

Repo pozostaje modularne. Baseline distribution może być pojedynczym `.py` zawierającym:

- pełny kod aplikacji,
- schemas,
- policy/stage/lane templates potrzebne do baseline,
- prompt templates,
- małe wymagane self-test fixtures,
- embedded metadata/build manifest.

Standalone NIE oznacza:

- zawarcia OS/interpretera,
- automatycznego download dependencies,
- dowolnego importu z cwd,
- ukrytej zależności od lokalnego packera.

Baseline core powinien preferować stdlib lub jawnie vendored/pinned bytes. External tools pozostają explicit execution dependencies z runtime binding.

---

# 52. Reproducible build

Build closure obejmuje wszystkie materialne inputs:

```text
source/resource bytes
schemas/specs/templates
builder/recipe revision
toolchain identity
build/runtime dependency profile
ordering/canonicalization rules
fixed build configuration
```

Nie mogą przenikać niejawnie:

- cwd files,
- mtime,
- hostname,
- absolute workspace paths,
- wall-clock now,
- niezadeklarowane gitignored assets,
- unpinned network downloads.

Build manifest i output digest nie tworzą cyklu self-hash: final release digest jest zewnętrznym/sidecar receipt lub ma jawny zakres nieobejmujący własnego pola.

Reproducible build nie dowodzi correctness. Wymagana jest modular-vs-standalone parity na realnej validation/reference path.

---

# 53. Self-test architecture

Standalone `--self-test` jest wczesnym sanity layer, nie całym qualification suite.

Minimum:

- embedded payload integrity,
- schema registry,
- canonical vectors,
- source identity vectors,
- legacy valid/invalid F1/F2 fixtures,
- wrong source/spec/policy binding,
- accepted-head / command idempotency,
- duplicate/conflicting result slots,
- stale projection refusal,
- Knowledge State/reveal ordering,
- invalid view resolver traversal,
- obligation qualification downgrade after invalidation,
- STOP UNKNOWN/INSUFFICIENT_DATA cases,
- standalone loader isolation.

Pełne crash/fault/reference scenarios mogą wymagać zewnętrznej test suite i nie muszą mieścić się wszystkie w embedded self-test.

---

# 54. Migration strategy

Migration jest prowadzona w kolejności minimalizującej ryzyko utrwalenia złej semantyki.

## Phase 0 — Freeze legacy baseline

- exact v1.4.4 bytes,
- source/application version,
- legacy fixtures,
- known behavior matrix,
- known gaps/exceptions.

## Phase 1 — Independent compatibility expectations

Przygotować dwa wymiary:

```text
LEGACY_BEHAVIOR_EXPECTATION
SAFE/CORRECTNESS_EXPECTATION
```

Nie generować ground truth wyłącznie przez uruchomienie v1.

## Phase 2 — Extract narrowly scoped assurance primitives

Można przenieść raw hashing/ZIP safety itd., jeżeli ich contract nie zależy od jeszcze nierozstrzygniętego v2 identity modelu.

## Phase 3 — Foundation contracts

Zamrozić:

- trust/authority/history,
- canonical identity/revision,
- policy/spec binding,
- isolation/discovery/reveal,
- inventory/obligations,
- evidence qualification/applicability,
- stage/campaign finalization,
- legacy admission.

## Phase 4 — Minimal Foundation Reference Slice

Najwcześniejsza integracja ma przejść:

```text
legacy E2 admission
→ v2 E3 genesis
→ isolated lane
→ discovery
→ checkpoint/reveal
→ experiment/observation
→ evidence qualification
→ coverage obligation update
→ StageCompletion
→ STOP = CONTINUE_REQUIRED
```

oraz failure paths:

- contaminated lane,
- missing surface,
- shared oracle,
- crash in commit,
- stale legacy bundle,
- invalidated evidence,
- insufficient-data STOP.

## Phase 5 — Full stage engines

Dopiero po foundation slice rozwijać kompletne E1/E2/E3, następnie E4/E5/E6 capabilities.

---

# 55. Backward compatibility gate

Compatibility ma dwa niezależne gates.

## 55.1. Preservation Gate

Sprawdza, czy v2 prawidłowo odczytuje/odtwarza **legacy behavior** dla zamrożonego corpus.

Może raportować 100% known-valid/known-invalid zgodnie z v1 expectation, ale to nie jest correctness proof.

## 55.2. Independent Correctness Gate

Każdy materialny fixture posiada niezależnie uzasadnione safe/expected semantics oparte na normatywnym invariant/threat class.

Known legacy bug może dać:

```text
legacy expected = ACCEPT
safe expected   = REJECT
```

To nie jest „compatibility regression”, lecz jawna hardening exception.

## 55.3. Gate result

Raportuje osobno:

- preservation compatibility,
- correctness/safety qualification,
- intentional exceptions,
- uncovered threat classes.

Nie istnieje jeden procent, który dowodzi obu rzeczy.

---

# 56. Versioning

Oddzielić co najmniej:

```text
APPLICATION_GENERATION / RELEASE
PROTOCOL_POLICY_GENERATION
SCHEMA_SET_REVISION
STAGE_SPEC_REVISION
LANE_SPEC_REVISION
EXECUTOR_PROFILE_REVISION
DELIVERY_PROFILE_REVISION
IDENTITY/CANONICALIZATION_PROFILE
BUILD/RUNTIME_PROFILE
```

Semver/human labels nie zastępują exact revision digests.

Upgrade aplikacji nie interpretuje automatycznie starej historii według nowych reguł. Resume wymaga obsługi pinned semantics albo jawnego migration/interpretation step.

---

# 57. Definition of Done — Architecture

Architektura foundation może zostać uznana za gotową do szerokiej implementacji, gdy:

1. istnieje jeden normatywny authority/trust/history model,
2. accepted commit + immutable object closure + receipt + head mają jedną atomic semantics,
3. command retry/idempotency/crash behavior jest jednoznaczne,
4. logical identity i immutable revisions są zdefiniowane w Data Contracts/ADR,
5. runy pinują exact policy/spec/schema/runtime refs,
6. Lane isolation rozróżnia ENFORCED/DECLARED/UNKNOWN,
7. DiscoveryRecorded jest bound do exact Knowledge State/history cut,
8. reveal używa positive views i restricted resolver,
9. CorpusSnapshot rozróżnia predecessor/auxiliary/holdout role,
10. Surface Inventory raportuje known-unobserved/unsupported/failure scope,
11. Coverage Obligations są authority; D0–D5 jest derived,
12. evidence independence jest claim-relative,
13. evidence applicability/invalidation propaguje się do findings/coverage/STOP,
14. stage completion jest oddzielone od campaign conclusion/release qualification,
15. STOP używa immutable exact input cut i jawnej UNKNOWN/BLOCKED semantics,
16. E6 nie może osłabić globalnych obligations,
17. legacy E1/E2 bytes pozostają immutable,
18. legacy admission oddziela historical facts od current v2 interpretation,
19. preservation i correctness compatibility są osobnymi gates,
20. minimalny legacy E2→v2 E3 reference slice + failure paths ma jednoznaczne oczekiwane wyniki,
21. standalone/runtime boundary jest jawna,
22. projections są rebuildable i nie stanowią drugiego authority,
23. istnieje skoncentrowany consistency review updated corpus przed Foundation Spec Baseline Freeze.

Pełne schemas E4/E5, każdy collector i finalny packer nie muszą być ukończone, aby foundation semantics były zamrożone.

---

# 58. Kluczowe decyzje architektoniczne

## ADR-001 — Controlled rewrite

**Decyzja:** v2 jest controlled rewrite, nie dalszym rozwijaniem monolitu v1.4.4 ani greenfield bez lineage.

## ADR-002 — Reuse qualified assurance primitives

**Decyzja:** mechaniczne primitives z v1 są przenoszone tylko z zachowaniem/kwalifikacją kontraktu.

## ADR-003 — One canonical accepted history

**Decyzja:** jedna accepted commit history + immutable objects; ledgery/graphs/statusy są facts w tej historii albo derived projections.

## ADR-004 — Trusted coordinator / untrusted executor

**Decyzja:** executor nie ustanawia authority swoich wyników.

## ADR-005 — Logical identity + immutable revisions

**Decyzja:** current mutable ID nie może zastępować exact revision ref w evidence/gates.

## ADR-006 — Canonical Serialization & Identity Profile

**Decyzja:** exact byte/object identity jest normowana w Data Contracts + dedykowanym ADR. Architecture nie duplikuje canonicalization rules.

## ADR-007 — Knowledge isolation by controlled channels

**Decyzja:** ENFORCED/DECLARED/UNKNOWN + contamination, zamiast deklaracji „audytor nie widział”.

## ADR-008 — Positive reveal views

**Decyzja:** grant-before-delivery, opaque ViewRefs i restricted resolver zamiast blacklist-only redaction.

## ADR-009 — Coverage Obligations as authority

**Decyzja:** sparse scoped obligations; D0–D5 jako derived conservative view.

## ADR-010 — Claim-relative evidence independence

**Decyzja:** independence jest oceną dependencies względem claim/failure assumption.

## ADR-011 — Stage completion ≠ campaign conclusion ≠ release readiness

**Decyzja:** osobne lifecycle artifacts i acykliczna finalizacja.

## ADR-012 — Transactional vault contract, backend-neutral

**Decyzja:** normatywne są atomic history/object/receipt/head semantics. SQLite jest reference implementation, nie wiecznym backendem.

## ADR-013 — Direct predecessor ≠ cumulative corpus

**Decyzja:** formal lineage i broad challenge corpus są osobnymi relacjami.

## ADR-014 — Preservation ≠ correctness compatibility

**Decyzja:** legacy differential behavior i independent safe expectation są dwoma gates.

## ADR-015 — Modular source + standalone deterministic distribution

**Decyzja:** jeden `.py` może być release artifactem, ale runtime/toolchain boundary jest jawna.

## ADR-016 — Early foundation reference slice

**Decyzja:** najtrudniejsze authority/isolation/evidence/STOP interactions są integrowane przed pełnymi stage engines.

---

# 59. Najważniejsze zakazy implementacyjne

Nie wolno:

1. utrzymywać kilku niezależnych mutable ledger heads dla tego samego campaign state,
2. traktować `state.json`, Coverage Ledger lub report jako current authority ponad accepted history,
3. pozwalać executorowi bezpośrednio modyfikować vault/current head,
4. używać timestampu executora jako authority ordering,
5. nadawać blind origin bez accepted precursor i wymaganej isolation class,
6. „resetować” knowledge przez nowe ID bez nowego kwalifikowanego execution context,
7. ujawniać raw refs poprzez resolver poza ViewManifest capability,
8. traktować Surface Inventory jako dowód kompletności świata,
9. ręcznie ustawiać D0–D5 jako coverage authority,
10. podnosić coverage całej surface jednym testem o wąskim scope,
11. uznawać fresh instance za niezależny oracle bez dependency qualification,
12. przenosić evidence na nowy target/environment/harness bez applicability decision,
13. pozostawiać coverage/STOP support po invalidation decisive evidence,
14. używać majority vote do contradictions/root causes,
15. przenosić evidence jednego findingu na inne root-cause members przez samo grouping,
16. traktować proof o modelu jako automatyczny proof o implementation,
17. uznawać PASS osłabionego oracle na clean target za dowód słabości oracle,
18. generować E6 przez osłabienie globalnych obligations,
19. wymagać campaign Final Assurance Case/STOP do zwykłego E1/E2/E3 StageCompletion,
20. przepisywać historyczne legacy bytes lub retconować E0/knowledge/coverage,
21. utożsamiać 100% legacy differential compatibility z validator correctness,
22. budować core semantics przez niekontrolowane runtime `.replace()`,
23. ładować niezadeklarowany kod/dependency z cwd/network w standalone profile,
24. deklarować full-host rollback resistance bez niezależnego pin/witness,
25. dodawać backend-specific storage semantics do metodologicznego contractu, jeżeli nie są konieczne do gwarancji.

---

# 60. Finalny model

Docelowy BDB Audit v2 jest lokalnym assurance coordinator systemem, w którym:

```text
TRUST / POLICY ROOT
    ustala dozwolone granice i exact rules

COORDINATOR
    jest jedynym authority writer

CANONICAL ACCEPTED HISTORY + IMMUTABLE OBJECTS
    zachowują decisions, exact bytes i lineage

TRANSITION SERVICE
    pilnuje Campaign/Stage/Lane/Attempt lifecycle

CAPABILITY / KNOWLEDGE BROKER
    kontroluje views, reveal i isolation claims

INVENTORY + INVARIANT + OBLIGATION SERVICES
    pokazują known scope i materialne obowiązki zamiast fikcyjnego coverage scalar

EXPERIMENT / EVIDENCE SERVICES
    rozdzielają execution, observation, independence i applicability

ADJUDICATION
    utrzymuje scoped findings/root causes/contradictions bez majority truth

STOP EVALUATOR
    ocenia exact current cut i rozdziela termination, assurance, residual uncertainty oraz product readiness

COMPILER / EXPORTER
    tworzy deterministyczne prompts/packages/reports bez własnej authority
```

Architektura świadomie nie obiecuje:

- wykrycia wszystkich unknown unknowns,
- pełnej wiedzy o stanie poznawczym audytora,
- poprawności wspólnego nieznanego oracle/TCB,
- wykrycia pełnego rollbacku całego hosta bez niezależnej kotwicy,
- release readiness wyłącznie dlatego, że campaign się zakończyła.

To jest foundation architecture, do której muszą zostać dostosowane Data Contracts, Migration, Roadmap, Test Plan i README przed Foundation Spec Baseline Freeze.


---

## R5.3 strict governance freeze binding

Foundation candidate bytes pozostają immutable po independent review. `FOUNDATION_SPEC_BASELINE_FROZEN` po `FOUNDATION_SPEC_BASELINE_READY` jest wyprowadzane z zewnętrznego `FoundationBaselineFreezeDecision` wiążącego exact candidate manifest + exact independent review. Edycja reviewed README/manifest tworzy nowy candidate i wymaga ponownego review.

# 61. R5.4 NF02 exact package and schema authority

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


The prepared exact schemas/SchemaRegistry/installation objects are candidate assets, not a loaded mutable authority. All old campaign schemas stay pinned. The E1/manual/shared packaging and inbox adapters must later implement this pipeline; code generation dictionaries/extensions/overlays cannot establish legality. Result evidence stores enduring facts, not HMAC tokens. Exact payload provenance does not automatically qualify findings. Full reference/union-DAG/atomicity/isolation and later application lifecycle gates are preserved.

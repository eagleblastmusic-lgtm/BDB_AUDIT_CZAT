# BDB AUDIT — V1.4.4 → V2 MIGRATION AND COMPATIBILITY SPEC

**Status:** AUTHOR-FINAL R5.3 — final author qualification after zero-based re-audit; no additional Astra review scheduled
**Rewizja:** 2026-09-09 / R5.3 final author qualification candidate
**Self-audit:** `R5_3_AUTHOR_FINAL_REAUDIT_PASS`; report `BDB_AUDIT_V2_SELF_AUDIT_REPORT_R5_3_2026-09-09.md`; strict independent freeze is not claimed
**Zakres:** przejście z `BDB_AUDIT_ASSISTANT_PA_v5.2_WRAPPERS_5.4-RC1_v1.4.4_ARCHIVE.py` do BDB Audit v2  
**Powiązane dokumenty:**  
- `BDB_Audit_vNext_Szczegolowy_Plan_Rozwoju.md`  
- `BDB_AUDIT_V2_ARCHITECTURE_SPEC.md`

**Cel dokumentu:** określić, jak stworzyć BDB Audit v2 na podstawie obecnej aplikacji v1.4.4 bez utraty zweryfikowanych mechanizmów assurance, bez przepisywania historii E1/E2, bez utożsamiania preservation z correctness i bez fałszywego deklarowania backward compatibility. Historyczne bytes pozostają faktami historycznymi; każda bieżąca interpretacja, admission, exposure confidence i evidence applicability jest nową, wersjonowaną decyzją v2.

---

# 1. Decyzja migracyjna

BDB Audit v2 NIE jest:

1. prostą aktualizacją monolitu v1.4.4,
2. greenfield rewrite bez wykorzystania istniejących assurance primitives,
3. historycznym „przepisaniem” E1/E2 na nowe schematy,
4. próbą uznania zachowania v1 za automatyczny oracle poprawności v2.

BDB Audit v2 jest:

> **controlled rewrite z kwalifikowaną migracją assurance primitives, read-only legacy boundary, nową canonical history i nowym modelem domenowym.**

Model docelowy:

```text
LEGACY v1.4.4
│
├── exact historical bytes ──────────────┐
├── observed legacy behavior ────────────┤
├── assurance primitives ────────────────┤
└── legacy validation semantics ─────────┤
                                         ▼
                              QUALIFICATION BOUNDARY
                             ┌────────────┴────────────┐
                             ▼                         ▼
                   PRESERVATION GATE          CORRECTNESS GATE
                             │                         │
                             └────────────┬────────────┘
                                          ▼
                                   BDB AUDIT v2
```

Przenosimy **kontrakty i mechanizmy, które przeszły kwalifikację**, nie nazwę funkcji ani historyczny wynik tylko dlatego, że pochodzi z v1.4.4.

---

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

## 8.1. Handoff / checkpoint validator

Hard-coded expected filename/folder inference zastępuje versioned `HandoffContract` / stage-specific checkpoint contract związany z exact source, run/attempt, history cut i policy/spec revisions.

Legacy F1/F2 pozostają obsługiwane przez compatibility profile; native v2 nie udaje, że każdy etap musi mieć identyczny F1/F2 artifact family.

## 8.2. Artifact family

Legacy fixed families są mapowane do `ArtifactContractRegistry`. Native families są wersjonowane per stage/lane/finalization.

## 8.3. Reveal attestation

Semantyka reveal zostaje przeniesiona do Knowledge/Capability modelu:

```text
sealed precursor
→ gate evaluation on exact cut
→ accepted grant / potential exposure
→ delivery of positive view
```

Legacy attestation jest historical evidence o wykonaniu dawnej bramki, nie dowodem totalnej wiedzy wykonawcy.

---

# 9. Co przepisujemy

Następujące elementy nie powinny być kopiowane 1:1.

## 9.1. Stage menu

Hard-coded:

```text
BASE
ITERACJA_1
ITERACJA_2
```

zastąpić Stage Registry.

## 9.2. Variant selection

Obecne:

```text
audit_level + tool + plus_pliki
```

zastąpić:

```text
StageSpec
LaneSpec
ExecutorSpec
DeliverySpec
```

## 9.3. Prompt runtime patching

Zastąpić deterministycznym Prompt Compiler.

## 9.4. Direct-predecessor-only corpus logic

Zachować direct predecessor jako lineage, ale dodać osobny Historical Corpus Engine.

## 9.5. Global monolithic DATA

Zastąpić modularnymi spec files i build-time compilation.

---

# 10. Co pozostaje legacy-only

Nie wszystko musi istnieć jako first-class koncept v2.

Legacy-only mogą pozostać:

- stare nazwy folderów KROK,
- stare wariantowe aliasy,
- historyczne artifact naming quirks,
- compatibility-only schema aliases,
- legacy JSON field aliases.

Nowe audyty nie powinny być generowane w legacy modelu, jeśli nowy kontrakt już istnieje.

---

# 11. Legacy importer

BDB v2 posiada read-only `LegacyArtifactImporter`.

Importer:

- przyjmuje legacy bytes jako untrusted input,
- waliduje transport/path/hash/profile,
- NIE modyfikuje raw bytes,
- zapisuje immutable `LEGACY_RAW_REF`, a następnie osobne current-v2 assessments: `LegacyMechanicalValidationAssessment`, `SourceReconciliationAssessment`, `LineageAdmissionAssessment`, opcjonalny `LegacyExposureReconstructionAssessment`, `LegacyObservationSemanticEquivalenceAssessment` i `LegacyObservationMappingAssessment` oraz osobne current `EvidenceQualificationAssessment`/`EvidenceApplicabilityAssessment`,
- nie tworzy generic `LegacyImportAssessment` jako drugiego authority envelope i nie emituje retroaktywnych history events.

Derived current-v2 `LEGACY_IMPORT_VIEW` może zestawiać dla operatora:

```text
legacy_ref
raw_digest
byte_length
legacy_contract_hint
parsed_legacy_variant_stage_facts
mechanical_validation_assessment_ref
source_reconciliation_assessment_ref
lineage_admission_assessment_ref
exposure_reconstruction_assessment_ref optional
current_evidence_applicability_or_mapping_refs[]
import_input_history_cut
as_of_head
```

Ten view nie jest authority; authority pozostają exact typed refs/assessments z Data & Artifact Contracts. `legacy_stage`, `variant` i podobne pola są wyłącznie parsed historical facts, natomiast current admission/exposure/applicability są nowymi ocenami v2.

---

# 12. Legacy SourceGeneration reconciliation

Każdy legacy artifact używany do current v2 lineage/corpus musi zostać związany z dokładną v2 `SourceGeneration` przez `SourceReconciliationAssessment`.

Źródła evidence mogą obejmować:

- legacy checkpoint/RUN_MANIFEST/LINEAGE_MANIFEST,
- source-integrity readbacks,
- frozen repo commit/tree,
- materialized source manifest/capsule.

Normatywny wynik `SourceReconciliationAssessment`:

```text
EXACT_MATCH
CONFLICT
INSUFFICIENT_DATA
```

Canonical predecessor wymaga `EXACT_MATCH`. Ograniczona auxiliary/informational rola może zostać dopuszczona przez osobny `LineageAdmissionAssessment`, ale nie zmienia source identity z niepewnej na exact.

`CONFLICT` albo `INSUFFICIENT_DATA` blokują canonical predecessor role.

Artifact może pozostać historycznym/informational raw object, ale nie wejść do canonical bootstrapu.

---

# 13. Legacy direct predecessor admission

Legacy E2 może być canonical predecessor v2 E3 **bez konwersji jego bytes do formatu v2**, jeżeli przejdzie current admission.

Canonical predecessor reference obejmuje co najmniej:

```text
role = CANONICAL_PREDECESSOR
legacy_raw_ref
legacy_contract_profile
mechanical_validation_assessment
source_reconciliation_assessment
lineage_admission_assessment
exposure_confidence_assessment
current_policy/bootstrap_constitution_ref
trusted selection/pin ref
```

Nie wystarcza `artifact_sha256 + variant_id`.

Canonical selection jest bieżącą decyzją coordinatora/policy. Stary poprawny, ale niezgodny z pinned canonical predecessor artifact jest historyczny, lecz nie current canonical input.

## 13.1. First-history legacy bootstrap

Canonical admission pierwszego legacy E2 nie wymaga fikcyjnego pre-genesis head. Dla nowego history namespace baseline używa jednego `INITIALIZE_CAMPAIGN_FROM_LEGACY` command względem `EMPTY_HISTORY_CUT` i exact `INSTALLATION_BOOTSTRAP_PROFILE_V1`. Command niesie `proposed_campaign_id/history_namespace_ref`, nie future `campaign_ref`; genesis może być wskazany dopiero jako późniejszy content object/event w tej samej closure. W jego jednym atomic commit `seq=1` przygotowane content objects są uporządkowane:

```text
initial pinned profile objects
→ LEGACY_RAW_REF
→ LegacyMechanicalValidationAssessment
→ SourceReconciliationAssessment
→ LineageAdmissionAssessment
→ LegacyExposureReconstructionAssessment optional
→ TrustedPredecessorSelectionDecision
→ BootstrapAdmissionDecision
→ CampaignGenesis
```

Generic ApprovalDecision nie zastępuje TrustedPredecessorSelectionDecision; selection jest osobną canonical decision family z exact predecessor pin/assessment bindings.

Assessmenty nie są retconowane jako facts istniejące przed v2: do chwili acceptance są wyłącznie prepared immutable content objects. Ich `*_input_history_cut=EMPTY_HISTORY_CUT`; zależności w tej initialization transaction są exact same-commit content refs do wcześniejszych nodes. `BootstrapAdmissionDecision` nie może wskazywać future genesis, natomiast `CampaignGenesis` wskazuje wcześniejszą admission decision.

Jeśli wynik to `BLOCKED_CANONICAL_ADMISSION`, raw bytes oraz diagnostyczne prepared objects mogą zostać zachowane poza accepted campaign history zgodnie z forensic policy, ale pierwszy canonical commit nie może jednocześnie ogłosić poprawnego `CampaignGenesisAccepted`. Nie wolno naprawiać tego synthetic H0, zero hashem ani serią fikcyjnych pre-genesis accepted commits.


---

# 14. Auxiliary E1 corpus

Wiele historycznych E1 reports może zostać dopuszczonych jako auxiliary corpus bez stania się alternatywnymi direct predecessors.

Każdy member ma exact raw ref, mechanical/source assessment, current corpus-role admission i exposure class. Zmiana current admissibility tworzy nowy corpus snapshot; nie mutuje reportu.

Auxiliary membership nie transferuje automatycznie:

- evidence independence,
- coverage depth,
- finding truth,
- blind-origin classification.

---

# 15. Canonical lineage

Formalna lineage pozostaje jednoznaczna:

```text
legacy E1 canonical
→ legacy E2 canonical
→ v2 E3 canonical
→ v2 E4 canonical
→ v2 E5 canonical
```

Każde przejście wskazuje exact predecessor revision/import assessment, exact SourceGeneration i governing policy/spec generation. Corpus auxiliary/holdout pozostaje osobnym graph role i nie może zastąpić canonical predecessor.

---

# 16. Historyczne raporty pomocnicze

Raporty BASE, które nie były canonical direct predecessor, mogą wejść jako:

```text
AUXILIARY_SAME_STAGE_REPORT
```

Pod warunkiem:

- source SHA match,
- source tree match,
- stage match,
- artifact integrity,
- report provenance.

---

# 17. External audits

A1/A2/A3 i inne niezależne audyty nie należą do canonical lineage.

Typ:

```text
EXTERNAL_HOLDOUT_CORPUS_MEMBER
```

Mogą zostać ujawnione dopiero zgodnie z Knowledge Exposure Policy.

---

# 18. Knowledge exposure migration

Legacy v1.4.4 nie posiada native-v2 Knowledge State ani pełnego channel inventory. Dlatego v2 tworzy **current reconstruction assessment**, nigdy retroaktywny Exposure Ledger.

`LegacyExposureReconstruction` może używać wyłącznie faktów, które istnieją w historycznych bytes, np.:

- F1/F2 gates,
- reveal attestations,
- report delivery/reveal records,
- ledger ordering,
- stage status i continuation tickets.

Reconstruction zapisuje:

```text
raw_sources[]
reconstructed_controlled_exposures[]
known_missing_channels[]
exposure_confidence
blind_origin_claim_permitted = true|false|limited
assessment_history_cut
```

Nie wolno zgadywać pozaprotokołowych ekspozycji ani twierdzić, że historyczny executor miał `ENFORCED` isolation tylko dlatego, że prompt był blind.

---

# 19. Exposure confidence i historyczne blind-origin claims

Exposure reconstruction i isolation assurance są różnymi osiami.

Przykładowa confidence rekonstrukcji:

```text
EXACT
STRONG
PARTIAL
UNKNOWN
```

Historyczny blind-origin claim może być przyznany tylko w zakresie, który faktycznie wspierają historyczne records i policy. `UNKNOWN` pozaprotokołowej wiedzy **nie musi blokować lineage admission**, ale blokuje silne twierdzenie, że cały historyczny discovery był enforced-blind.

W mixed-generation campaign:

- lineage admission może być PASS,
- historyczna exposure confidence może być PARTIAL/UNKNOWN,
- nowe E3 lanes mają własny ENFORCED/DECLARED/UNKNOWN profile,
- novelty/false-negative classification nie dziedziczy silniejszej blindness niż udowodniona.

---

# 20. Legacy artifact immutability

Każdy legacy artifact pozostaje immutable exact bytes.

Dozwolone operacje v2:

```text
raw artifact
→ validate
→ store/reference exact bytes
→ accept current assessment
→ derive current views
```

Niedozwolone:

```text
raw artifact
→ rewrite into "equivalent v2 history"
```

Derived/current assessments mają własne identity/revisions. Usunięcie lub korekta current projection nie zmienia legacy raw authority.

---

# 21. Legacy raw authority i current authority

Legacy raw artifact jest authority **dla tego, co historycznie zapisano**.

Nie jest automatycznie authority dla:

- current v2 source equivalence,
- current evidence applicability,
- current blind-origin strength,
- current coverage obligations,
- validator correctness.

Jeżeli current v2 assessment jest sprzeczny z raw content, poprawia się assessment. Jeżeli nowa evidence dowodzi, że historyczny claim był błędny, historyczny report nadal pozostaje niezmieniony, a current adjudication zapisuje jego dzisiejszy status.

---

# 22. Migration phases — jedna mapa

Migracja używa jednej zależnościowej mapy, aby wcześnie zweryfikować fundament. Jej lokalne identyfikatory mają namespace `MG0…MG7`; `F0…F8` pozostają jedynymi program phases, a `M0…M50` jedynymi roadmap slice IDs. `MG*` nie jest `MilestoneAcceptance.phase_id`.

## MG0 — Freeze legacy baseline

- exact application/raw hashes,
- legacy source/tag/reference,
- self-tests,
- golden fixtures.

## MG1 — Qualify compatibility corpus

- valid/invalid fixtures,
- `legacy_observed_result`,
- `independent_safe_expected_result`,
- known-bug/hardening classifications.

## MG2 — Extract minimal assurance primitives

- raw hashing,
- ZIP safety,
- manifest parsing,
- legacy source/checkpoint parsers.

Ekstrakcja nie zmienia historycznej serializacji.

## MG3 — Build dual compatibility harness

Najpierw preservation diff, osobno correctness expectations. Osiągnąć foundation-level compatibility dla przenoszonych primitives.

## MG4 — Close v2 foundation contracts potrzebne bootstrapowi

Minimalnie:

- trust/authority/history boundary,
- SourceIdentity + typed revisions,
- Stage/Lane/Attempt creation semantics,
- Knowledge/grant/discovery cut,
- coverage obligation/evidence applicability inputs,
- stage vs campaign finalization,
- legacy admission A/B/C.

## MG5 — Minimal legacy E2 → v2 E3 reference slice

Zbudować wąski przepływ:

```text
legacy E2 admission
→ v2 campaign genesis
→ isolated E3 attempt
→ accepted pre-reveal discovery precursor
→ checkpoint
→ controlled reveal
→ assisted hypothesis/confirmation
→ one experiment/evidence qualification path
→ one coverage obligation
→ StageCompletion or refusal
→ STOP CONTINUE/BLOCKED decision
```

Happy path sam nie wystarcza; wymagane są foundation failure paths.

## MG6 — Expand native-v2 domain subsystems

Dopiero po reference slice rozszerzać collectors, corpus, findings, contradictions, E4/E5 adapters.

## MG7 — Full mixed-generation qualification

Uruchomić rzeczywisty legacy E1→E2→v2 E3 bootstrap na zatwierdzonym corpus i wykazać wszystkie current admission limits.

---

# 23. No-regression principle

No-regression oznacza zachowanie **jawnie zakwalifikowanych assurance properties**, nie identyczność każdego legacy rezultatu.

Regresją jest m.in.:

- akceptacja znanego invalid bundle,
- utrata raw-byte/hash/source/checkpoint binding,
- możliwość obejścia reveal gate,
- zmiana legacy raw bytes,
- osłabienie historycznej walidacji bez zaakceptowanej compatibility exception.

Nie jest regresją celowe odrzucenie legacy zachowania, które niezależny correctness oracle kwalifikuje jako unsafe, jeśli istnieje jawny hardening decision.

---

# 24. Differential validator harness

Harness generuje co najmniej dwa niezależne wyniki.

## 24.1. Preservation comparison

```text
legacy_observed = validate_with_v1(fixture)
v2_observed = validate_with_v2(fixture)
preservation_diff = compare(legacy_observed, v2_observed)
```

Porównywać m.in. PASS/FAIL, critical error family, legacy variant/source/checkpoint/ledger semantics.

## 24.2. Correctness qualification

```text
safe_expectation = qualified_fixture_expectation(fixture)
correctness = compare(v2_observed, safe_expectation)
```

Wspólny wynik v1 i v2 nie wystarcza, jeżeli oba dzielą tę samą lukę. Nie wolno używać nowego validatora jako jedynego oracle dla własnej poprawności.

---

# 25. Legacy error messages

Nie wymagamy byte-identical text errorów.

Wymagamy semantic-equivalence klasyfikacji.

Przykład:

v1:

```text
SOURCE_SHA_MISMATCH
```

v2:

```text
SOURCE_IDENTITY_SHA_MISMATCH
```

może być zaakceptowane, jeśli oba są mapowane do tego samego compatibility error code.

---

# 26. Error compatibility map

Powstaje:

```text
LEGACY_ERROR_MAP.json
```

Mapuje:

```text
v1 error
→
v2 canonical error
```

Pozwala testować semantics zamiast literalnych stringów.

---

# 27. Schema compatibility map

Analogicznie:

```text
LEGACY_SCHEMA_MAP.json
```

Przykład:

```text
BDB_RUN_MANIFEST_V1
→
LegacyRunManifestAdapter
```

---

# 28. Artifact-name compatibility

Validator legacy powinien rozpoznawać historyczne nazwy wymagane przez v1.4.4.

Nowe StageSpecs nie powinny używać ich tylko dlatego, że istnieją w legacy.

---

# 29. F1 migration rule

Legacy F1 jest walidowane według legacy contract.

Po walidacji v2 może utworzyć:

```text
V2_LEGACY_F1_REFERENCE.json
```

z:

```text
legacy_bundle_sha256
source_generation_id
audit_request_id
audit_attempt_id
ledger_snapshot_sha256
validation_result
```

Nie tworzy substitute F1.

---

# 30. F2 migration rule

Tak samo:

```text
V2_LEGACY_F2_REFERENCE.json
```

Nie rekonstruować F2 z reportu ani final bundle.

Tylko oryginalny F2/handoff może pełnić rolę F2 authority.

---

# 31. Final bundle migration

Legacy final bundle pozostaje legacy final bundle.

v2 tworzy reference:

```text
LEGACY_FINAL_RESULT_REFERENCE
```

i może wyciągnąć machine-readable facts.

Nie tworzyć „v2 final bundle” udającego historyczny E2.

---

# 32. Migration of findings

Historyczne findings mogą zostać znormalizowane w nowym corpus, ale:

- original finding ID zachować,
- original severity zachować,
- original report reference zachować.

Nowy normalized root cause jest osobnym bytem.

---

# 33. Finding provenance

Przykład:

```text
normalized_root_cause = RC-004

members:
  - legacy:E1-A/F-002
  - legacy:E1-C/F-004
  - legacy:E2/F1-002
```

Nie zamieniać oryginalnych finding IDs.

---

# 34. Severity migration

Jeżeli v2 uzna inną severity:

```text
ORIGINAL_SEVERITY
CURRENT_ADJUDICATED_SEVERITY
SEVERITY_CHANGE_REASON
```

Nie nadpisywać historycznego pola.

---

# 35. Status migration

Przykład:

```text
legacy finding lifecycle: CONFIRMED_CURRENT
v2 RequalificationDisposition: STILL_PRESENT
```

Oba fakty są zachowane.

---

# 36. Rejected legacy hypotheses

Jeżeli istnieją dowody historycznego odrzucenia, dodać do Hypothesis Ledger.

Przykład:

```text
literal localhost SSRF
→ REJECTED
```

Cel:

- zapobiegać resurrecting false positives.

---

# 37. SOUND migration

Historyczne SOUND claims mogą być importowane jako:

```text
LEGACY_SOUND_CLAIM
```

ale confidence jest ograniczone do source generation, metod i coverage dostępnych w tamtym audycie.

---

# 38. Coverage migration

Legacy E1/E2 nie posiadały native-v2 `Coverage Obligations`. Nie tworzymy retroaktywnego „v2 Coverage Ledger”.

Dozwolone jest current bootstrap assessment:

- jakie subsystemy/methods/scenarios historycznie widać w evidence,
- jakie current obligations można uznać za częściowo informowane,
- które obligations wymagają native-v2 wykonania.

Legacy depth/status **nie przenosi się automatycznie**.

```text
legacy observation
→ semantic-equivalence assessment (`EXACT|SCOPED|AMBIGUOUS|NONE`)
→ current obligation mapping (`MAPPED|PARTIAL|NOT_MAPPABLE|INSUFFICIENT_DATA`)
→ current EvidenceQualification / EvidenceApplicability
→ CoverageObligationQualification
```

Native-v2 obligation może otrzymać `qualification_status=QUALIFIED` tylko, gdy current acceptance predicate, applicability i independence są spełnione. W przeciwnym razie pozostaje `UNASSESSED`, `IN_PROGRESS`, `BLOCKED` albo `STALE`; `SCOPED` jest wartością evidence applicability/semantic-equivalence context, nie wire status obligation. `PASS` jest wynikiem odpowiedniego predicate/gate, nie status field obligation.

---

# 39. Invariant migration

Invariants wywnioskowane dziś z legacy findings są **current-v2 revisions** z provenance `DERIVED_FROM_LEGACY_*`.

Nie należy twierdzić, że były formalnie zarejestrowane w E1/E2. Mogą być użyte do bootstrap obligation planning, ale ich activation/materiality jest bieżącą decyzją E0/bootstrap policy.

---

# 40. Experiment migration

Historyczne reproducers/test runs mogą być zapisane jako `LEGACY_EXECUTION/OBSERVATION`.

Nie mogą otrzymać `PREREGISTERED`, jeżeli preregistration historycznie nie miała miejsca. Current v2 może:

- wykorzystać je jako exploratory evidence o ograniczonym scope,
- zaproponować z nich hypothesis,
- uruchomić nowy preregistered confirmation experiment.

---

# 41. Evidence migration

Legacy evidence nie jest mapowane przez prosty enum `E0–E3`.

Current v2 tworzy `EvidenceQualificationAssessment` względem konkretnego claimu, które opisuje:

- raw observation refs,
- execution subject/source,
- environment/harness/fixture/dependency set,
- observation path,
- wspólne dependencies/oracles,
- current applicability,
- independence qualification względem failure assumption.

`fresh instance` albo `external observer` samo w sobie nie podnosi siły evidence. Historyczna etykieta jest zachowana jako raw legacy value, a current qualification jest nową decyzją.

---

# 42. Migration of prompt lineage

Previous-prompt bundles zachowują oryginalne bytes.

v2 może je zweryfikować.

Nowy prompt compiler nie próbuje regenerować historycznego bundle i nazywać go identycznym artifactem.

---

# 43. Reproducibility of legacy prompt bundles

Jeżeli chcemy sprawdzić reproducibility:

- zbudować osobny candidate,
- porównać SHA,
- nie zastępować authority.

Authority = stored historical bundle.

---

# 44. Mixed-generation campaign

Wspierany jest przypadek:

```text
Source Generation = S (ta sama frozen generation)
legacy history:
  E1 = LEGACY
  E2 = LEGACY
current v2 campaign:
  genesis imports/adopts qualified E1/E2 refs
  E3 = NATIVE_V2
```

Nie oznacza to, że E1/E2 zostają „przekształcone” w native-v2 stages. Są historycznymi predecessor inputs do nowej campaign/genesis constitution.

---

# 45. Mixed-generation lineage manifest / projection

Machine-readable lineage musi odróżniać co najmniej:

```text
producer_application_generation
protocol/policy_generation
legacy_contract_profile
raw_artifact_revision
current_import/admission_revision
source_generation_ref
stage_role
```

Przykład prezentacyjny:

```text
E1: producer=v1.4.4, role=legacy historical
E2: producer=v1.4.4, role=canonical predecessor
E3: producer=v2.x, role=native current stage
```

Lineage export jest projekcją canonical v2 admission/history, nie konkurencyjnym mutable source of truth.

---

# 46. Protocol vs application vs source generation

Muszą pozostać rozdzielone:

```text
SOURCE GENERATION
APPLICATION GENERATION
PROTOCOL/POLICY GENERATION
STAGE/LANE SPEC REVISION
```

Legacy E2 i v2 E3 mogą dotyczyć tego samego source, ale native-v2 bootstrap musi przypiąć current protocol/policy/spec bundle. Jeżeli v2 wprowadza nową normatywną semantykę assurance, nie można jej ukryć jako „app-only change”.

---

# 47. Kiedy wymagany jest bump Protocol/Policy

Bump jest wymagany, gdy zmienia się znaczenie obowiązkowego kontraktu assurance, np.:

- reveal/isolation eligibility,
- mandatory artifact/assessment,
- F1/F2 legacy interpretation rules,
- lineage/admission authority,
- evidence applicability/independence semantics,
- STOP inputs/precedence,
- compatibility correctness contract.

Zmiana musi posiadać ADR/policy revision i stare runs pozostają związane z poprzednią semantyką.

---

# 48. App-only changes

App-only mogą pozostać zmiany, które nie modyfikują normatywnego wyniku przy tych samych pinned inputs, np.:

- reorganizacja modułów,
- UI/CLI,
- optymalizacja projections,
- zmiana backendu storage spełniającego ten sam authority/transaction contract,
- build tooling bez zmiany contract closure.

Jeżeli zmiana wpływa na canonical bytes, identity, admission, reveal, evidence lub STOP — nie jest tylko implementacyjna.

---

# 49. Normative changes i ADR

Materialne foundation decisions są utrwalane raz w normatywnym contract/policy + ADR, a pozostałe dokumenty referują tę semantykę.

Szczególnie identity/canonical serialization powinny posiadać dedykowany ADR/profile. Backend storage (np. SQLite) może być reference implementation, ale normatywny migration contract wymaga właściwości: atomic accepted commit, immutable object closure, idempotent receipts, monotonic head, crash recovery — nie jednej marki storage.

---

# 50. Legacy self-tests

Każdy istniejący self-test concept powinien otrzymać odpowiednik w v2.

Minimum:

- valid F1 accepted,
- wrong variant rejected,
- conflicting duplicate rejected,
- early reveal rejected,
- invalid final artifact rejected.

---

# 51. Golden fixture preservation

Legacy fixtures w repo muszą być immutable.

Jeżeli trzeba dodać nową wersję:

```text
fixture_v2
```

Nie nadpisywać starego.

---

# 52. Migration branches

Rekomendowana strategia:

```text
main
└── stable legacy/reference

bdb-v2
└── active v2 development
```

Po osiągnięciu compatibility + v2 readiness:

- merge v2 source,
- zachować legacy folder,
- tag v1.4.4,
- tag v2.0.0.

---

# 53. Version tags

Zalecane:

```text
bdb-audit-v1.4.4
bdb-audit-v2.0.0
```

Tag v1.4.4 powinien wskazywać dokładną zamrożoną wersję.

---

# 54. Build compatibility

Standalone v2 NIE musi być byte-compatible z v1.4.4.

Musi natomiast mieć jawny build/runtime closure:

- complete declared build inputs,
- deterministic application-byte profile,
- pinned interpreter/runtime support profile,
- brak ukrytego runtime download/install,
- loader behavior bez niejawnego importu z cwd,
- external release digest niezależny od self-referential embedded manifestu.

Build reproducibility nie jest correctness oracle dla validatora. Legacy validation compatibility i native-v2 build qualification są osobnymi gates.

---

# 55. Data directory / vault migration

Nie wykonujemy agresywnej in-place migracji legacy user state.

Preferowany model:

```text
legacy state = read-only source/reference
v2 vault/history = nowa authority domain
```

v2 może zaimportować exact legacy bytes i assessments, ale nie może nadać staremu mutable `state.json` rangi current v2 head. Aktywny vault ma własny trust/transaction profile; exporty i legacy directories są inputs/projections.

---

# 56. Rollback i restore

Dopóki v2 nie osiągnie kwalifikacji produkcyjnej:

- v1.4.4 pozostaje dostępne do legacy validation,
- historyczne E1/E2 pozostają możliwe do zweryfikowania legacy app,
- v2 nie nadpisuje legacy state/fixtures.

Restore v2 vault/history nie może automatycznie twierdzić, że przywrócony snapshot jest najnowszy. Freshness/rollback protection zależy od trusted local/external pin profile. Bez niezależnego nowszego pin system uczciwie ogranicza gwarancję.

---

# 57. Migration audit trail

Import/migration acceptance jest częścią canonical accepted history v2, a nie osobnym konkurencyjnym ledgerem.

Każda materialna operacja zapisuje np.:

```text
command/receipt ref
source raw artifact ref
adapter/application generation
policy/spec refs
mechanical validation assessment
source reconciliation assessment
admission result
created current references/revisions
accepted history cut
```

Timestamp jest obserwacją; ordering wynika z accepted commits.

---

# 58. Security / trust boundary

Legacy files są untrusted inputs.

Importer musi stosować:

- ZIP/path/hash/resource constraints,
- parser hardening,
- explicit contract versions,
- brak wykonania instrukcji z repo/artifactu,
- brak bezpośredniego zapisu executorów do trusted v2 vault.

Hash consistency nie dowodzi authenticity/freshness. Current canonical admission wymaga zaufanego selection/pin/receipt zgodnie z trust profile.

---

# 59. No semantic auto-upgrade

Niedozwolone:

```text
old artifact
→ silently rewrite/upgrade semantics
```

Dozwolone:

```text
old raw bytes
→ validate under pinned legacy profile
→ accept immutable raw reference
→ accept current assessment under pinned v2 policy
→ derive projections
```

Upgrade programu nie reinterpretowuje wcześniejszych accepted decisions bez nowej versioned assessment.

---

# 60. Derived/current records

Każda current-v2 interpretacja legacy posiada exact provenance i revision, np.:

```text
raw_source_refs[]
derivation/assessment_kind
derivation_tool_or_actor
policy/schema revision
input_history_cut
rule/algorithm version
result revision
```

Nie polegamy na wall-clock `derivation_time` jako authority ordering. Derived projection można odtworzyć; accepted semantic assessment pozostaje canonical history fact.

---

# 61. Canonical legacy authority

Reguła authority:

1. legacy raw bytes są authority tego, co historycznie zapisano;
2. current v2 admission/interpretation jest authority bieżącej decyzji v2 o tych bytes;
3. derived views nie mogą nadpisać żadnego z powyższych.

Jeżeli current assessment błędnie opisuje raw artifact, assessment jest korygowany nową revision/event. Raw bytes pozostają niezmienione.

---

# 62. Migration validation levels

Legacy admission używa jednej normatywnej, kumulatywnej taksonomii zgodnej z Data Contracts:

```text
L0_BYTES_PRESENT
L1_RAW_DIGEST_KNOWN
L2_STRUCTURALLY_PARSED
L3_INTERNAL_INTEGRITY_VALIDATED
L4_SOURCE_IDENTITY_EXACTLY_RECONCILED
L5_LINEAGE_ROLE_AND_TRUSTED_SELECTION_VALIDATED
```

## L0_BYTES_PRESENT

Exact bytes są dostępne w granicach limitów wejścia; nic więcej.

## L1_RAW_DIGEST_KNOWN

Exact bytes, byte length/media/representation identity i `RawDigest` są znane; operator wskazał importowany zestaw. Bieżący pin nie dowodzi historycznej autentyczności poza dostępną provenance.

## L2_STRUCTURALLY_PARSED

Rozpoznano exact legacy format/version; parser przeszedł bez silent fallback i odrzuca ambiguous/unsupported mandatory syntax.

## L3_INTERNAL_INTEGRITY_VALIDATED

Przeszedł wymagane dla rodziny legacy integrity/reference-closure checks: membership, hashes, ZIP/checkpoint/ledger relations, duplicate/conflict semantics.

## L4_SOURCE_IDENTITY_EXACTLY_RECONCILED

Current `SourceReconciliationAssessment` jednoznacznie wiąże legacy artifact z wymaganą v2 SourceGeneration/SourceIdentity zgodnie z pinned profile; brak heurystycznego „wygląda na ten sam kod”.

## L5_LINEAGE_ROLE_AND_TRUSTED_SELECTION_VALIDATED

Artifact przeszedł predecessor/attempt/run/source/pin/freshness bindings, canonical E2 selection i role-admission policy. Wymagane historyczne checkpoint/gate/F1/F2 records są zgodne z właściwym legacy profile; brakujących mandatory artifacts nie rekonstruuje się jako historycznych faktów.

**Exposure confidence jest osobną osią** (`EXACT / STRONG / PARTIAL / UNKNOWN`) i nie jest ukryta w L5. L5 canonical predecessor może istnieć przy ograniczonej historical exposure confidence; wtedy historyczne blind-origin claims pozostają odpowiednio ograniczone.

---

# 63. Corpus admissibility i bootstrap cases A/B/C

Role mają jawne predicates.

## Canonical predecessor

Wymaga co najmniej L5, exact/current source reconciliation zgodnego z policy oraz trusted canonical selection/pin. Exposure confidence jest oceniana oddzielnie.

## Auxiliary historical report

Zwykle wymaga L4 + role-specific integrity/admission. Nie musi mieć prawa do canonical lineage.

## Informational reference

Może być dopuszczony przy L2/L3, ale nie wspiera hard current obligations bez odrębnej evidence qualification.

## Bootstrap Case A — pełny jednoznaczny legacy E2

- L5 PASS,
- exact source reconciliation,
- predecessor/pin/freshness PASS,
- historyczne reveal facts wystarczające do deklarowanego exposure scope.

Wynik: `CANONICAL_BOOTSTRAP_ADMITTED`; historical blind-origin tylko w udowodnionym zakresie.

## Case B — poprawny E2, ale częściowo nieznane exposure

- L5 PASS dla lineage,
- source/predecessor PASS,
- exposure = PARTIAL/UNKNOWN poza zarejestrowanymi gates.

Wynik: `CANONICAL_BOOTSTRAP_ADMITTED_WITH_EXPOSURE_LIMIT`; nowe E3 może być uruchomione, ale nie wolno retrospektywnie przyznać silnego historycznego blind-origin.

## Case C — brak/konflikt artifactu wymaganego do canonical admission

Np. source reconciliation conflict, niezgodny pinned predecessor, brak required integrity member.

Wynik: `BLOCKED_CANONICAL_ADMISSION`. Raw bytes mogą pozostać informational/forensic. Nie odtwarzamy brakującego F2/E0 z narracyjnego raportu.

---

# 64. Migration blockers

Migrację nowej semantyki należy zatrzymać, jeżeli zachodzi którekolwiek z:

- nie można zamrozić referencyjnego v1.4.4 i corpus,
- preservation expectations nie są jawne,
- correctness expectations dla materialnych fixtures nie mają niezależnej podstawy,
- v2 akceptuje known-invalid fixture,
- known legacy bug jest traktowany jako safe tylko dlatego, że oba validatory go zachowują,
- SourceIdentity reconciliation jest niejednoznaczne dla canonical bootstrapu,
- raw ledger/checkpoint/source assurance primitive regresuje,
- reveal/isolation history jest retroaktywnie wymyślona,
- E1/E2 raw artifacts są modyfikowane,
- canonical predecessor nie ma L5/pin/source admission,
- mixed-generation flow tworzy fikcyjne historyczne E0/Coverage/Knowledge records,
- foundation reference slice nie ma jednoznacznego outcome dla wymaganych failure paths.

---

# 65. Definition of Done — Migration

Migracja foundation z v1.4.4 do v2 jest zakończona, gdy:

1. v1.4.4 i compatibility corpus są immutable/frozen.
2. Każdy materialny fixture ma legacy-observed oraz independent-safe expectation albo jawne `UNQUALIFIED`.
3. Preservation gate i correctness gate są odrębne i PASS dla required corpus.
4. Kwalifikowane assurance primitives działają modularnie bez zmiany legacy bytes.
5. Legacy E1/E2 są read-only compatible.
6. Current SourceIdentity reconciliation jest normatywna i testowalna.
7. Direct predecessor może wskazać legacy E2 tylko przez L5 admission + trusted selection/pin.
8. Auxiliary corpus ma role-specific admission i nie miesza się z lineage.
9. Exposure reconstruction ma confidence i nie udaje enforced isolation.
10. Coverage/invariant/experiment/evidence są bootstrapowane jako current-v2 interpretations, nie retro-history.
11. Mixed-generation lineage jest machine-readable i rozdziela source/app/policy/spec generations.
12. Case A/B/C legacy E2 → v2 E3 daje jednoznaczne rezultaty.
13. Minimalny reference slice i foundation failure paths mają projektowane, jednoznaczne outcomes.
14. Rollback do legacy validation pozostaje możliwy bez nadpisania legacy state.
15. Build/runtime compatibility boundary jest jawny.
16. Wszystkie compatibility exceptions/hardenings są versioned i uzasadnione.

---

# 66. Rekomendowana kolejność commitów migracyjnych

Przykładowa sekwencja zależnościowa:

```text
MIG-001 Freeze legacy v1.4.4 reference/tag/raw digest
MIG-002 Add immutable legacy fixtures + intent metadata
MIG-003 Add independent safe expectations / known-bug registry
MIG-004 Extract raw hashing + ZIP safety
MIG-005 Extract legacy manifest/checkpoint/ledger primitives
MIG-006 Build preservation harness
MIG-007 Build correctness gate
MIG-008 Reach qualified primitive compatibility baseline
MIG-009 Add v2 SourceIdentity/revision/trust contract
MIG-010 Add read-only importer + SourceReconciliationAssessment
MIG-011 Add lineage admission L0–L5 + exposure confidence
MIG-012 Add minimal campaign/stage/lane/attempt/history foundation
MIG-013 Add capability/knowledge/discovery cut minimum
MIG-014 Add one obligation + evidence qualification path
MIG-015 Implement cases A/B/C legacy E2 bootstrap
MIG-016 Run foundation reference slice + failure paths
MIG-017 Expand multi-report legacy corpus and mixed lineage
```

Każdy commit przechodzi odpowiedni subset self-tests. Nie implementujemy pełnego E4/E5 przed zweryfikowaniem bootstrap foundation.

---

# 67. Zakaz big-bang migration

Nie przenosić całego monolitu jednym commitem.

Dla każdego assurance primitive wymagamy:

```text
legacy contract / observed behavior
→ extracted implementation
→ preservation comparison
→ independent correctness expectation
→ accepted migration disposition
```

Dopiero potem można usunąć runtime dependency od starego monolitu. Domain subsystems, których v1 nie posiadał, nie potrzebują „differential equality”; potrzebują native-v2 contract + acceptance tests.

---

# 68. Temporary dual-run mode

`--legacy-compare` jest narzędziem migracyjnym, nie authority.

Może pokazywać:

- v1 observed result,
- v2 observed result,
- preservation diff,
- independent expected safe result,
- correctness diff,
- compatibility exception/hardening status.

Dual-run nie może sam oznaczyć `CORRECT`, jeśli oba validatory zwróciły ten sam wynik bez niezależnego oracle.

---

# 69. Compatibility report

Każdy kandydacki build v2 generuje machine-readable raport rozdzielający co najmniej:

```text
fixture_count
preservation_required_count
preservation_matched
preservation_differences[]
correctness_qualified_count
correctness_passed
correctness_failed[]
known_legacy_bugs[]
intentional_hardening[]
exceptions[]
unqualified_expectations[]
overall_preservation_status
overall_correctness_status
```

Jeden `overall_status` bez obu osi jest niewystarczający.

---

# 70. Release gate v2.0

v2.0.0 nie może zostać wydane jako bezpieczny następca, jeżeli:

```text
required_preservation_gate != PASS
OR
required_correctness_gate != PASS
OR
foundation_reference_gate != PASS
OR
legacy_bootstrap_A/B/C_contract != QUALIFIED
```

Nowe E3–E5 features nie kompensują regresji legacy assurance foundation. Jednocześnie release gate aplikacji nie jest tym samym co release readiness audytowanego source.

---

# 71. Najważniejszy trade-off

Nie zachowujemy:

> identycznej implementacji ani każdego historycznego błędnego zachowania.

Zachowujemy:

> exact history oraz jawnie zakwalifikowane assurance semantics, z osobną niezależną oceną correctness.

To pozwala zbudować prostszą i mocniejszą architekturę bez zamiany legacy w oracle własnej poprawności.

---

# 72. Końcowy model migracji

```text
                    LEGACY v1.4.4
                         │
          ┌──────────────┼────────────────┐
          │              │                │
    exact raw bytes   observed behavior   known legacy quirks
          │              │                │
          ▼              ▼                ▼
     IMMUTABLE      PRESERVATION      INDEPENDENT
     RAW REFS          GATE           CORRECTNESS GATE
          │              │                │
          └──────────────┴────────┬───────┘
                                  ▼
                       CURRENT V2 ADMISSION
                    source / lineage / exposure
                                  │
                                  ▼
                          BDB AUDIT v2 GENESIS
                                  │
                  ┌───────────────┼────────────────┐
                  ▼               ▼                ▼
             native E3+       new corpus       new evidence /
             orchestration      roles          obligations
```

Żaden blok current-v2 nie przepisuje legacy raw history.

---

# 73. Finalna decyzja

BDB Audit v2 ma rozpocząć życie jako nowa aplikacja z **udowodnioną, ograniczoną i machine-readable ciągłością** z v1.4.4.

Nie wystarczy:

> „przenieśliśmy funkcje”

ani:

> „v2 zwraca to samo co v1”.

Trzeba wykazać jednocześnie:

1. exact history nie została zmieniona,
2. wymagane legacy assurance semantics zostały zachowane albo jawnie utwardzone,
3. current validator correctness jest kwalifikowana niezależnie od legacy output,
4. source/lineage/exposure/admission są bieżącymi decyzjami związanymi z exact raw bytes,
5. legacy E2 → v2 E3 działa według jednoznacznego A/B/C contractu bez retroaktywnego E0/coverage/knowledge,
6. minimalny mixed-generation reference flow ma przewidywalne happy/failure outcomes.

Dopiero wtedy legacy może bezpiecznie pełnić rolę fundamentu dla native-v2 E3–E5.

---


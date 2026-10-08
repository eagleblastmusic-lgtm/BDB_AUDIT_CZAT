# BDB Audit vNext — szczegółowy plan rozwoju i docelowa architektura audytu

**Status dokumentu:** AUTHOR-HOTFIX R5.3.1 CANDIDATE — bootstrap-order correction; exact storage readback qualification pending; no additional Astra review scheduled
**Rewizja:** 2026-09-10 / R5.3.1 bootstrap-order correction candidate
**Self-audit:** `R5_3_1_AUTHOR_HOTFIX_REAUDIT_PASS`; report `BDB_AUDIT_V2_SELF_AUDIT_REPORT_R5_3_1_2026-09-10.md`; external readback qualification remains pending; strict independent freeze is not claimed
**Cel:** zaprojektowanie maksymalnie rygorystycznego, szerokiego, głębokiego i odpornego na false positives / false negatives procesu audytu technicznego BDB  
**Zakres:** audyt jednej zamrożonej generacji source, iteracyjne zwiększanie wiedzy E1→E5, a następnie osobna rekwalifikacja po naprawach  
**Założenie nadrzędne:** jakość audytu nie jest mierzona liczbą raportów ani liczbą findings, lecz stopniem redukcji niepewności, zakresem spełnionych obowiązków dowodowych, siłą i zastosowalnością evidence, niezależnością discovery oraz skutecznością falsyfikacji. Coverage nigdy nie dowodzi kompletności produktu, a STOP PASS nie oznacza automatycznie release readiness audytowanego source. R5.3 dodatkowo wymaga exact registry-wire-kind identity dla ObjectDigest, exact StopInput→StopEvaluation binding oraz history-context pinning policy/spec/profile bez same-commit semantic self-upgrade. R5.3.1 doprecyzowuje, że canonical commit-closure DAG może zawierać wyłącznie typed content-ref dependency edges oraz jawne, machine-readable, scope-bound order-only precedence edges z exact pinned Registry/profile; precedence edge wpływa na kolejność/cycle detection, ale nigdy nie tworzy referencji, authority ani provenance.

---

# 1. Cel przebudowy BDB Audit

Obecny model BDB ma bardzo mocny **proof engine**:

- zamrożony source,
- dokładne SHA/tree,
- F1/F2,
- blind gates,
- append-only ledger,
- provenance,
- adjudykację poprzednich findings,
- rozróżnienie rediscovery / report-assisted,
- negative controls,
- fault injection,
- rygorystyczne claim restraint.

Największą przestrzenią do ulepszenia jest **discovery engine**:

- lepsze wykrywanie wcześniejszych false negatives,
- większa szerokość systemowego discovery,
- jawne mierzenie powierzchni, których jeszcze nie przebadano,
- większa różnorodność niezależnych metod,
- systematyczne badanie root causes, siblings i causal chains,
- stateful / temporal / concurrency testing,
- fuzzing i property-based testing,
- adversarial composition,
- audytowanie jakości samych oracle i samego procesu audytowego.

Docelowy BDB ma więc odpowiadać jednocześnie na dwa pytania:

1. **Czy znalezione problemy są naprawdę udowodnione?**
2. **Jak mocne mamy podstawy, by uważać, że nie ominęliśmy dużej części materialnych problemów?**

---

# 2. Zasady nadrzędne

## 2.1. Jeden source generation na cały cykl E1–E5

Wszystkie etapy E1–E5 pracują na tej samej zamrożonej **Source Generation**. Formalna identity source nie może zależeć wyłącznie od nazwy brancha, ZIP-a ani przypadkowego locatora. Musi wiązać autoryzowane repository/snapshot authority z dokładnym content manifestem i — gdy źródłem jest Git — z właściwymi obiektami commit/tree.

W praktyce cykl zachowuje:

- exact source identity,
- commit/tree albo równoważny snapshot authority,
- exact source bytes/manifest,
- protocol/policy generation obowiązującą dany run,
- application generation wykonawcy,
- immutable history wszystkich zaakceptowanych decyzji.

Nie naprawia się audytowanego source pomiędzy E1 i E5. Dzięki temu można odróżnić previous false negative od regresji, mierzyć różnice discovery na identycznym target i utrzymywać czyste lineage.

```text
SOURCE GENERATION X
│
├── E1 — BASE / DISCOVER
├── E2 — ITERACJA 1 / VERIFY
├── E3 — ITERACJA 2 / EXPAND
├── E4 — ITERACJA 3 / DEEPEN
└── E5 — ITERACJA 4 / ATTACK
```

Dopiero po zakończeniu same-source campaign:

```text
FINAL AUDIT CORPUS
↓
REMEDIATION
↓
NEW SOURCE GENERATION
↓
REQUALIFICATION
```

Realnie ujawnione sekrety lub credentiale należy rotować operacyjnie natychmiast. Taka rotacja nie może jednak po cichu zmieniać frozen source używanego do porównań E1–E5.

## 2.2. Pięć etapów pełni pięć różnych funkcji epistemicznych

```text
E1 — DISCOVER
E2 — VERIFY
E3 — EXPAND
E4 — DEEPEN
E5 — ATTACK
```

Nie są to pięć coraz dłuższych code review. Każdy etap redukuje inną klasę niepewności. E6 jest adaptacyjne i uruchamiane wyłącznie przez jawny wynik STOP, a nie dlatego, że „warto zrobić jeszcze jeden raport”.

## 2.3. Jedna zaakceptowana historia, wiele widoków

BDB v2 nie może posiadać kilku równoległych, mutowalnych źródeł aktualnego stanu. Normatywna zasada foundation brzmi:

```text
TRUSTED COORDINATOR
→ CANONICAL ACCEPTED COMMIT HISTORY
→ IMMUTABLE OBJECT / ARTIFACT REVISIONS
→ DERIVED PROJECTIONS / EXPORTS
```

Executor proponuje materiał. Dopiero coordinator może go zwalidować i zaakceptować do historii. `PASS`, timestamp, nazwa pliku ani hash dostarczony przez executor nie ustanawiają authority.

Knowledge views, Coverage Ledger, Contribution Ledger, Traceability Graph, Blocker Ledger i podobne zestawienia są **projekcjami** zaakceptowanych faktów i decyzji. Mogą być eksportowane jako osobne pliki, ale nie mogą konkurować z canonical history jako drugi head systemu.

Historyczny artifact pozostaje authority własnych exact bytes. Bieżąca interpretacja tego artifactu jest nową, wersjonowaną decyzją; nie wolno przepisywać przeszłości.

## 2.4. Trust profile i granica gwarancji

Baseline profile nazywa się `LOCAL_PINNED`: zakłada lokalnego, zaufanego coordinatora i host/runtime należący do trusted computing base danego profilu. Audytowane repozytorium, executory, zewnętrzne narzędzia i importowane bundles są wejściami niezaufanymi.

SHA-256 dowodzi zgodności exact bytes ze znaną wartością. Nie dowodzi sam z siebie:

- prawdziwości treści,
- czasu powstania,
- wykonania testu,
- kompletności historii,
- braku rollbacku całego trusted store.

Silniejsze profile mogą używać niezależnych pins/receipts/witnesses. Baseline nie obiecuje wykrycia pełnego kompromisu lub pełnego restore hosta bez niezależnej kotwicy.

## 2.5. Identity i rewizje są jawne

Logical identity obiektu i identity jego exact rewizji są różnymi pojęciami. Campaign, finding czy invariant mogą zachowywać logical ID, ale każda materialna wersja musi posiadać content-bound immutable revision. Exact byte-level canonicalization i typed-reference profile są definiowane normatywnie w Data & Artifact Contracts oraz dedykowanym ADR; metodologia nie może utrzymywać własnego alternatywnego profilu serializacji.

---

# 3. Struktura całego programu

Docelowy model składa się z pięciu głównych etapów audytowych oraz dwóch warstw pomocniczych.

## E0 — Audit Constitution & Laboratory

Nie jest liczony jako etap audytu source.

Cel:

- zdefiniować reguły,
- przygotować laboratorium,
- przygotować modele coverage,
- przygotować mechanizmy bezpieczeństwa audytora,
- zamrozić reguły przed rozpoczęciem discovery.

## E1 — BASE / Discover & Map

Pytanie:

> Co jest popsute i jak wygląda cała powierzchnia systemu?

Dominujący cel:

- wysoki recall,
- szeroki baseline,
- mapa systemu,
- pierwsze invariants,
- pierwsze root causes.

## E2 — Iteracja 1 / Verify & Adjudicate

Pytanie:

> Czy BASE miało rację, czego BASE nie znalazło i co z poprzedniego corpus nadal się broni?

Dominujący cel:

- precision,
- evidence,
- falsyfikacja,
- adjudykacja,
- previous false-negative hunting.

## E3 — Iteracja 2 / Expand & Hunt

Pytanie:

> Co istnieje poza dotychczasowym finding corpus?

Dominujący cel:

- agresywne outward discovery,
- wykrywanie wieloetapowych false negatives,
- gap-directed discovery,
- niezależne nowe kanały discovery.

## E4 — Iteracja 3 / Deepen & Model

Pytanie:

> Jak głęboko sięga każdy root cause, jakie ma siblings, jakie stany i sekwencje są legalne/nielegalne?

Dominujący cel:

- root-cause families,
- state machines,
- temporal correctness,
- property testing,
- crash/recovery,
- causal-chain coverage.

## E5 — Iteracja 4 / Attack & Synthesize

Pytanie:

> Czy po połączeniu failure modes, zaatakowaniu oracle i próbie obalenia finalnego modelu zostało coś release-changing?

Dominujący cel:

- adversarial synthesis,
- interaction testing,
- mutation testing,
- final false-positive challenge,
- final false-negative hunt.

## E6 — tylko adaptacyjnie

Nie planować z góry.

E6 powstaje wyłącznie wtedy, gdy E5 STOP GATE wykaże, że:

- discovery nadal ma wysoką marginalną wartość,
- istotny subsystem ma zbyt małe coverage,
- istnieją unresolved material candidates,
- final challenger znajduje nową root-cause family,
- hard stop conditions nie są spełnione.

---

# 4. E0 — Audit Constitution & Laboratory

E0 ma zamrozić reguły campaign zanim wynik audytu zacznie wpływać na decyzje. Nie wolno po zobaczeniu findings osłabiać policy, zmieniać mianownika coverage ani redefiniować blindness tylko po to, aby uzyskać PASS.

## 4.1. Source authority, policy i trust

E0 zapisuje co najmniej:

- frozen Source Generation identity,
- repository/snapshot authority mode,
- exact source manifest i jego digest,
- application generation wykonawcy,
- protocol/policy bundle revision,
- schema/spec revisions,
- trust profile coordinatora/executorów,
- material environment profiles,
- initial scope i budget/effort profile,
- owner/operator authority dla jawnych decyzji scope/materiality.

Branch reference, wall-clock timestamp czy filename są informacyjne, jeżeli nie są częścią jawnego kontraktu identity.

## 4.2. Claim taxonomy — stan epistemiczny ≠ metoda obserwacji

Każdy materialny claim rozdziela: claim/scope, observation methods, shared dependencies/oracles oraz current applicability. Dla trzech osi meritum `MECHANISM`, `REACHABILITY`, `IMPACT` obowiązuje jedna epistemic taxonomy:

```text
SUPPORTED
REFUTED
INCONCLUSIVE
BLOCKED
NOT_APPLICABLE
```

Metoda nie jest truth statusem. `SOURCE_REACHABLE`, `CONTROLLED_DYNAMIC`, `LIVE_REACHABLE`, fresh instance, restart, independent/external observer itd. są osobnymi method/characterization facts. Przykład poprawnego rozdzielenia: `REACHABILITY=REFUTED` z metodą `CONTROLLED_DYNAMIC`. Nie wolno mapować REFUTED na UNVERIFIED/BLOCKED tylko dlatego, że schema nie ma właściwej wartości.

Mechanism opisuje, czy mechanizm wspierany/refutowany jest w danym scope; Reachability — czy osiągalność jest wspierana/refutowana; Impact — czy skutek jest wspierany/refutowany. Evidence qualification i applicability pozostają odrębne.

## 4.3. Severity, confidence, materiality i scope

Severity, confidence i materiality są rozdzielone. Final statement nie może przekraczać scope kwalifikowanego evidence.

Kategorie oddziaływania obejmują co najmniej:

- SECURITY,
- RELIABILITY,
- DATA_INTEGRITY,
- AVAILABILITY,
- PRIVACY,
- RELEASE_ASSURANCE,
- EVIDENCE_QUALITY.

Policy/E0 musi określić, kto i na jakiej podstawie może:

- klasyfikować materiality,
- przyjmować N/A,
- zatwierdzać jawny waiver,
- zmieniać scope.

UNKNOWN, BLOCKED i WAIVED nie są równoważne PASS i nie podnoszą coverage ani assurance.

---

# 5. Audit Surface Inventory — znany zakres z jawną niepewnością

Mechaniczny inventory jest kluczowy, ale **nie jest „prawdziwym mianownikiem” w sensie dowodu kompletności świata**. Collector może czegoś nie obsługiwać lub nie zauważyć. Dlatego BDB musi rozliczać zarówno znalezione surfaces, jak i granice samego procesu collection.

## 5.1. Inventory obejmuje powierzchnie oraz input accounting

Mechaniczne collectory powinny wykrywać m.in.:

- HTTP routes i state-changing endpoints,
- network egress i URL consumers,
- parsers oraz HTML/JSON/XML consumers,
- file reads/writes, persistence i caches,
- subprocess/process management,
- threads, async tasks, executors, locks i shared state,
- timers, retries i workers,
- authn/authz, secrets/config readers,
- DOM/iframe/external-content sinks,
- CI, dependencies, launchers, tests,
- diagnostic/artifact producers.

Równolegle każdy assigned input musi mieć `InputDisposition`. Terminalne dispositions to:

```text
COLLECTED
UNSUPPORTED
EXCLUDED
COLLECTION_FAILED
PARSING_FAILED
```

`PROVISIONAL` jest dozwolone wyłącznie jako stan pośredni i **nie spełnia terminal input accounting**. `ScopeState` jest osobną domeną (`KNOWN_UNOBSERVED_SCOPE`, `UNSUPPORTED_SCOPE`, `EXCLUDED_SCOPE`, `UNKNOWN_SCOPE` itd.); nie wolno wpisywać scope state do pola InputDisposition. Nie wolno traktować exit code collectora albo liczby wyemitowanych rekordów jako dowodu kompletności.

## 5.2. Surface record i stable identity

Surface posiada stabilny, source-bound key/revision zgodny z normatywnym identity profile. Filename, offset po normalizacji tekstu czy collector ID nie mogą być arbitralnym źródłem identity.

Surface record opisuje co najmniej:

```text
SURFACE_KEY / REVISION
CATEGORY
LOCATION / ANCHOR
ENTRY_POINT
EXTERNAL_INPUT
PERSISTENCE
CONCURRENCY
PRIVILEGE
IRREVERSIBLE_EFFECT
TRUST_BOUNDARY
FAN_OUT
RISK_ATTRIBUTES
COLLECTION_PROVENANCE
```

Manual additions i runtime-discovered surfaces są dozwolone, jeżeli mają jawne provenance i nie udają mechanicznej detekcji.

## 5.3. Inventory revisions i unknown scope

Późne odkrycie subsystemu tworzy nową inventory revision. Wcześniejsze coverage summaries oraz decyzje zależne od starego denominatora muszą zostać przeliczone na nowym cut historii.

Nieznany lub nieobsługiwany scope pozostaje jawny w assurance case. BDB może uczciwie raportować coverage **znanego, zinwentaryzowanego zakresu** wraz z niepewnością inventory; nie może obiecywać, że wszystkie unknown unknowns zostały mechanicznie wyeliminowane.

## 5.4. Inventory niezależne od findings

Surface istnieje niezależnie od tego, czy znaleziono w nim defect. Krytyczne obszary bez findings nadal generują obligations do E4/E5. To jest podstawa negative-space auditing.

---

# 6. System Invariant Registry i Coverage Obligations

BDB nie może opierać assurance wyłącznie na findings. Najpierw definiuje właściwości, których naruszenia ma potrafić wykryć.

Przykłady invariants pozostają takie jak:

```text
INV-STORE-01
Successful durable mutation implies durable state exists in the contractually defined store.

INV-REMOTE-01
Required local+remote operation must not report complete success when required remote effect failed.

INV-CAT-01
Published complete revision implies all required source runs are complete.

INV-AUTH-01
Unconfigured state must not gain authority from embedded fallback credentials.

INV-PROC-01
Destructive process termination requires ownership proof.

INV-FE-01
Obsolete generation must not mutate current frontend state.
```

Invariant Registry przechowuje wersjonowany, scoped kontrakt. Zamiast globalnego pola `REQUIRED_EVIDENCE_DEPTH`, materialne wymagania testowe są wyrażane jako osobne **Coverage Obligations**.

Coverage Obligation wiąże co najmniej:

```text
TARGET_SCOPE
INVARIANT_REVISION
SCENARIO_CLASS
ENVIRONMENT_PROFILE
REQUIRED_QUALIFICATION
ACCEPTANCE_PREDICATE
POLICY_OBLIGATION_KEY
```

Zmiana predicate/qualification tworzy nową revision obowiązku. Zmiana target tuple tworzy nowy obligation z jawnym lineage/supersedes mapping; support nie dziedziczy się automatycznie.

---

# 7. Traceability Graph — derived view kwalifikowanych relacji

Traceability pozostaje dwukierunkowe, ale graph nie jest niezależnym źródłem prawdy. Jest projekcją zaakceptowanych typed references i jawnych semantic relations.

```text
SURFACE / SCOPE
↓
INVARIANT
↓
COVERAGE OBLIGATION
↓
HYPOTHESIS
↓
EXPERIMENT PLAN / EXECUTION
↓
OBSERVATIONS + DEPENDENCIES
↓
EVIDENCE QUALIFICATION
↓
FINDING / SOUND / REJECTED / UNRESOLVED
```

BDB musi potrafić odpowiedzieć:

- jaki exact evidence path wspiera dany claim,
- które obligations nie są spełnione,
- które surfaces nie mają materialnych invariants,
- które claims współdzielą ten sam oracle/dependency,
- które wcześniejsze conclusions utraciły support po invalidation.

Graph nie może automatycznie dopisywać relacji przez podobieństwo tekstu lub ID. Każda materialna semantic relation ma mieć zaakceptowane provenance albo być jawnie derived z typowanych facts.

---

# 8. Coverage — obligations jako authority, D0–D5 jako konserwatywny widok

Coverage nie jest jedną liczbą i nie jest etykietą nadawaną całemu komponentowi przez audytora.

## 8.1. Authority coverage

Autorytatywną jednostką jest **Coverage Obligation** dla konkretnego:

```text
scope/surface
× invariant
× scenario class
× environment profile
× required evidence qualification
```

Coverage rozdziela **qualification status** od **substantive outcome**.

Qualification status:

```text
UNASSESSED | IN_PROGRESS | QUALIFIED | BLOCKED | STALE
```

Substantive outcome, gdy dostępny:

```text
NO_VIOLATION_OBSERVED | VIOLATION_CONFIRMED | INCONCLUSIVE
```

`NOT_APPLICABLE` i `WAIVED` są osobnymi accepted decisions, a unresolved contradiction osobnym blockerem. Kwalifikowany test może potwierdzić violation i nadal spełnić investigation obligation; `INCONCLUSIVE` nie spełnia decisive requirement. `BLOCKED`, `UNKNOWN`, waiver i N/A nie są wykonanym PASS.

## 8.2. Breadth

Breadth opisuje spełnienie obowiązków w **znanym inventory revision** oraz oddzielnie pokazuje unresolved/unsupported scope. Nie wolno usuwać problematycznych inputs z denominatora bez wersjonowanej scope decision.

## 8.3. D0–D5

D0–D5 może pozostać jako prezentacyjny skrót:

```text
D0 = brak kwalifikowanego badania
D1 = static
D2 = dynamic happy/negative
D3 = failure/fault
D4 = stateful/temporal/concurrency/adversarial
D5 = wybrane compositional/mutation/replay obligations
```

Ale poziom D jest **derived** z faktycznie spełnionych obligations. Nie wolno:

- podnieść całej surface do D4 jednym testem concurrency,
- przyznać D5 przez nieaktywną mutację,
- zwiększać breadth przez sztuczne rozbijanie surfaces,
- zachować wysokiego D po invalidation jedynego supporting evidence.

## 8.4. Risk policy

Risk profile określa, jakie obligations są wymagane dla materialnych klas. Konkretne minimalne poziomy lub liczby scenariuszy są **policy profile**, a nie wiecznym globalnym invariantem metodologii. Default może istnieć, ale campaign/E0 przypina exact policy revision.

## 8.5. Negative-space interpretation

`NO_FINDING` ma znaczenie tylko razem z:

- exact scope,
- spełnionymi obligations,
- observation/evidence qualifications,
- controls,
- unresolved scope,
- surviving material mutations/faults.

Brak findingu nigdy sam nie tworzy SOUND.

---

# 9. Negative-space auditing

Brak findingu nie jest dowodem bezpieczeństwa.

Wartość negative evidence zależy od exact obligation/scope, a nie od etykiety depth nad całym subsystemem. `NO_FINDING` jest użyteczne dopiero, gdy wiadomo:

- jaki inventory/scope revision badano,
- które Coverage Obligations były applicable,
- które z nich uzyskały kwalifikowany wynik,
- jakimi observation paths i controls,
- jakie dependencies/oracles współdzielono,
- jakie mutations/faults zostały rzeczywiście aktywowane,
- jaki unresolved/unsupported scope pozostał.

Przykład słabego wyniku:

```text
NO_FINDING
obligation = static review only
unknown runtime scope = present
```

Przykład mocniejszego negative evidence:

```text
NO_FINDING for exact claim/scope
required obligations = qualification_status=QUALIFIED + decisive substantive outcome required by obligation predicate
negative controls = PASS
activated mutation controls = killed as expected
independent observation path = qualified for relevant failure assumption
unresolved scope = explicitly bounded
```

Nawet taki wynik nie dowodzi globalnego braku defektów poza swoim scope.

---

# 10. Knowledge Isolation, Exposure i Discovery Provenance

BDB nie może twierdzić, że zna pełny stan poznawczy człowieka lub modelu. Może natomiast kwalifikować **kontrolowane kanały wejściowe wykonawcy**.

## 10.1. Klasy isolation assurance

Run/lane posiada jawny poziom:

```text
ENFORCED
DECLARED
UNKNOWN
```

oraz osobne contamination assessments.

**ENFORCED** wymaga świeżego kontekstu i realnie egzekwowanych granic: filesystem/tool/network/session allowlist, braku dostępu do trusted vault i innych lanes oraz brokera dozwolonych wejść. Sam nowy `lane_id`, prompt albo folder nie dowodzi izolacji.

**DECLARED** jest uczciwym, słabszym profilem dla manualnych workflows.

**UNKNOWN** nie uprawnia do verified blind-origin claims.

Potential exposure jest konserwatywne: jeżeli grant/reveal mógł udostępnić treść, późniejszy brak ACK nie przywraca blindness.

## 10.2. Knowledge State

Knowledge State jest immutable, attempt-bound snapshotem **zarejestrowanych/potencjalnych exposures i dozwolonych views**, nie dowodem całej wiedzy wykonawcy. Każdy reveal tworzy następną revision; reset ID nie cofa ekspozycji.

## 10.3. First-class Discovery Event

Discovery musi zostać utrwalone jako osobny accepted event przed reveal, jeśli później ma istnieć claim `NEW_BLIND_DISCOVERY` albo odpowiednik.

Discovery record wiąże:

```text
LANE_RUN / ATTEMPT
SOURCE GENERATION
EXACT KNOWLEDGE STATE / HISTORY CUT
METHOD / PRODUCER
SURFACE / LOCATION / MECHANISM CANDIDATE
OWN OBSERVATION REFS
```

Późniejsze confirmation, corpus matching, novelty, contribution i previous-false-negative classification są **osobnymi decyzjami**. Timestamp finalnego findingu nie może zastępować discovery ordering.

## 10.4. Origin jest wielowymiarowy

Nie wolno upychać wszystkich znaczeń w jednym enumie. Należy osobno przechowywać:

- exposure at discovery,
- producer/method origin,
- confirmation mode,
- match względem exact prior corpus revision,
- novelty classification,
- false-negative relationship.

Dzięki temu statusy w rodzaju `PRE_REPORT_REDISCOVERY`, `REPORT_ASSISTED_VERIFICATION`, `PREVIOUS_FALSE_NEGATIVE`, `MULTI_STAGE_FALSE_NEGATIVE` są derived labels z jawnych facts, nie ręcznie nadawaną historią.

---

# 11. Experiment Preregistration i execution binding

Przed materialnym eksperymentem należy zamrozić plan wystarczający do rozróżnienia safe/buggy outcome i falsyfikacji claimu.

```text
EXPERIMENT_ID / REVISION
HYPOTHESIS / INVARIANT / OBLIGATION
SUBJECT BASELINE
TARGET EXECUTION VARIANT
TRIGGER
EXPECTED_SAFE_BEHAVIOR
EXPECTED_BUGGY_BEHAVIOR
OBSERVATION PATHS / REQUIRED INDEPENDENCE
FALSIFICATION CONDITION
POSITIVE / NEGATIVE CONTROLS
FAULT / SEED / FIXTURE
ENVIRONMENT / DEPENDENCIES / HARNESS
CLEANUP
PLANNING_MODE
```

Preregistration jest skuteczne od accepted event. Exploratory/legacy execution nie może otrzymać fikcyjnego wcześniejszego statusu `PREREGISTERED`; zapisuje się właściwy `planning_mode` i ogranicza późniejszą siłę claimu.

Fuzz/property campaigns prerejestrują generator, oracle i zakres, nie każdy wygenerowany input.

---

# 12. Auditor Control-Plane Security i trust boundary

Repozytorium jest niezaufanym materiałem dowodowym, a nie źródłem instrukcji dla control plane.

## Zasady

- code/comments/README/testy repo są evidence, nie policy,
- executor nie zapisuje canonical accepted history bezpośrednio,
- coordinator jest jedyną stroną akceptującą mutations foundation,
- repo nie może zwiększyć permissions audytora,
- dozwolone inputs/views są wydawane przez capability-aware broker,
- raw secret values są redagowane i nie są potrzebne do dowodu obecności sekretu,
- destructive/live effects wymagają osobnego upoważnienia i nie są baseline metodą,
- network/tool/fs channels należą do modelu isolation,
- imported artifacts są parser inputs, nie trusted attestations,
- pełna kompromitacja trusted hosta jest poza gwarancją profilu lokalnego, o ile nie istnieje niezależny pin/witness.

Backend przechowywania historii ma spełniać wymagania transakcyjności, atomic acceptance, idempotency, monotonic accepted head i recoverability. **Metodologia nie normuje konkretnego produktu storage**. SQLite może być referencyjną implementacją lokalnego profilu, ale nie jest wieczną definicją BDB v2.

---

# 13. E1 — Discovery Ensemble

E1 powinno mieć kilka naprawdę ortogonalnych audytów, nie kilka kopii tego samego promptu.

## 13.1. E1-A — General Systems Audit

Szeroki baseline całego systemu.

## 13.2. E1-B — Security / Trust / Authority

Priorytet:

- localhost API,
- auth,
- Origin/Host,
- URL trust,
- XSS,
- SSRF,
- iframe/CSP,
- secrets,
- process authority,
- network boundaries.

## 13.3. E1-C — State / Persistence / Recovery

Priorytet:

- durability,
- atomicity,
- local/remote split,
- restart,
- crash,
- retry,
- stale state,
- sync,
- recovery.

## 13.4. E1-D — Data / Catalog / Parsing / Identity

Priorytet:

- parser assumptions,
- HTTP200 false-normal,
- pagination,
- termination,
- completeness,
- revision publication,
- cache poisoning,
- IDs,
- collisions,
- time normalization.

## 13.5. E1-E — Frontend / Concurrency / Resources / Oracle

Priorytet:

- stale async results,
- generation switching,
- event-loop blocking,
- threads,
- locks,
- queues,
- maps,
- SSE,
- storyboard,
- cancellation,
- test oracle weaknesses.

## 13.6. Wildcard budget

10–20% discovery budget każdego lane powinno być przeznaczone na:

> dowolny materialny failure mode niezależnie od przydzielonej taxonomy.

Chroni to przed tunnel vision.

---

# 14. Audit Strategy Manifest

Każdy E1 lane musi mieć formalnie inną strategię.

Przykład:

```text
LANE E1-B
PRIMARY_HEURISTIC = trust-boundary traversal
STARTING_POINTS = endpoints + network egress + HTML sinks
FAILURE_PRODUCERS = hostile input / hostile origin / authority mismatch
FORBIDDEN_DEPENDENCY = other E1 reports
```

Celem jest **realna orthogonality**, nie tylko inne nazwy raportów.

---

# 15. Machine-Assisted Discovery

BDB nie powinno polegać wyłącznie na reasoning audit.

Automatyczne narzędzia służą jako generatory hipotez.

Przykładowe lanes:

- static analysis,
- secret scanning,
- dependency scanning,
- type checking,
- lint/security rules,
- call graph,
- taint-like analysis,
- fuzzing,
- coverage instrumentation.

Zasada:

```text
SCANNER OUTPUT
≠
FINDING
```

Scanner output trafia do Hypothesis Ledger i musi zostać niezależnie potwierdzony albo odrzucony.

---

# 16. E1 stop condition

Nie kończyć tylko dlatego, że wykonano N raportów.

Start może wynosić np. 5 lane’ów.

Po nich oblicza się:

- new HIGH per lane,
- new MEDIUM per lane,
- new root-cause families,
- unique-only mechanisms,
- leave-one-out contribution,
- coverage delta,
- unresolved candidates.

Jeśli kolejne ortogonalne lane’y nadal znajdują dużo nowych root causes:

```text
E1_SATURATION = LOW
→ ADDITIONAL_E1_LANE
```

Jeśli dwa kolejne lane’y dostarczają głównie duplikaty:

```text
E1_SATURATION = STRONG
```

Overlap/capture-recapture może być wskaźnikiem pomocniczym, ale nigdy jedynym STOP criterion.

---

# 17. E2 — Verify & Adjudicate

E2 jest fazą konwergencji i nie powinno być pięcioma pełnymi kopiami tego samego audytu.

## 17.1. E2 blind phase

Lane otrzymuje tylko view dozwolony przez policy. Jeżeli wymagany jest verified blind-origin, executor musi spełniać odpowiedni isolation profile; manualny/UNKNOWN run może wykonać użyteczną analizę, ale nie otrzymuje silniejszej etykiety provenance.

Najpierw wykonywane są m.in.:

- własne discovery,
- previous-false-negative hunt bez semantic prior reports,
- dynamic tests,
- fault injection,
- negative controls.

Materialne discoveries wymagające późniejszej etykiety pre-reveal są utrwalane jako Discovery Events. Następnie powstają sealed checkpoints F1/F2 i gate decisions na jednym accepted history cut.

## 17.2. Reveal poprzedniego E1 corpus

Formalny lineage nadal ma **jednego canonical predecessor**. Pozostałe E1 reports są auxiliary corpus members.

Reveal nie polega na wrzuceniu folderu wykonawcy. Coordinator tworzy **positive View Manifest** określający dokładnie dozwolone bytes/fields/references. Grant jest zaakceptowany **przed delivery**, a Knowledge State konserwatywnie aktualizowany od momentu potencjalnego udostępnienia.

Raw provenance, support count i history mogą być ujawniane dopiero w fazie dozwolonej przez policy. Resolver nie może przez opaque ref otworzyć artefaktu spoza view closure.

---

# 18. Claim Quarantine i phase-specific projections

Claim Quarantine ogranicza popularity/anchoring bias, ale nie przywraca pełnej blindness. Widoczny mechanism/location sam w sobie może już wpływać na audytora.

Przed provenance reveal E2 może dostać wersjonowane claim cards z minimalnym dozwolonym view, np.:

```text
OPAQUE_CLAIM_VIEW_ID
LOCATION (jeśli dozwolone)
MECHANISM CANDIDATE
ASSERTED OBSERVABLE
OPAQUE EVIDENCE VIEW REFS
```

Ukryte pozostają — jeżeli policy tego wymaga — m.in.:

- producer identity,
- support count,
- severity history,
- prior popularity,
- raw report paths/names.

Redakcja top-level pola nie wystarcza. Filenames, hashes, resolver targets i evidence payloads również należą do transitive reveal policy. Opaque ref może prowadzić tylko do closure zatwierdzonego View Manifest.

Zasada pozostaje:

```text
TRUTH FIRST
POPULARITY LATER
```

ale mechanicznie jest egzekwowana przez positive projections/capabilities, nie przez prośbę w prompt.

---

# 19. Indywidualna adjudykacja przed merge

Każdy historical finding/claim jest adjudykowany osobno, na własnym scope i evidence. Root-cause grouping nie może przenosić evidence jednego membera na inny.

```text
E1-A/F01 → adjudicate
E1-B/F08 → adjudicate
E1-C/F03 → adjudicate
↓
versioned root-cause membership decisions
```

Finding pozostaje samodzielnym scoped claimem nawet po przypisaniu do wspólnego root cause. Merge/split jest nową, audytowalną decyzją i nie zmienia automatycznie truth status memberów.

---

# 20. Root-Cause Normalization — versioned membership, nie utrata findings

Root Cause służy organizacji mechanizmów, sibling search i remediation planning. Nie zastępuje indywidualnych findings.

Model musi wspierać:

- versioned membership,
- merge i split z rationale,
- findings o wielu przyczynach,
- causal roles/AND-OR zależnie od kontraktu,
- różne reachability/impact/severity przy wspólnym mechanizmie.

Nie wolno tworzyć union evidence i traktować go jako support każdego membera. Historyczne membership decyzje pozostają, a nowa wiedza tworzy kolejną revision. Canonical membership wskazuje Finding revisions; Finding nie wskazuje future RootCauseMembership. Merge/split używa backward predecessor refs, nie forward successor refs.

---

# 21. Independent Shadow Adjudicator

Po głównym E2 uruchamiany jest mały niezależny checker.

Nie robi pełnego repo audit.

Sprawdza:

- over-merging,
- under-merging,
- severity inflation,
- false dismissal,
- origin misclassification,
- evidence overstating,
- błędne classification previous-false-negative.

Wykryte konflikty trafiają do Contradiction Protocol.

---

# 22. Contradiction Protocol — scope-aware i reopenable

Nigdy nie stosować majority voting jako truth oracle.

Konflikt musi być opisany względem exact claims/scopes i może zakończyć się m.in. przez:

- refutation w tym samym scope,
- rozdzielenie scope/environment/input,
- obalenie harnessu/oracle,
- zmianę/rewizję invariant,
- pozostawienie UNRESOLVED/BLOCKED.

`TESTING` albo `BLOCKED` contradiction nadal reprezentuje nierozstrzygnięte zobowiązanie i musi wpływać na STOP zgodnie z policy. Mechaniczny falsifier nie zamyka konfliktu, jeżeli bada inną kwantyfikację lub inne środowisko.

Nowe material counterevidence po `RESOLVED` otwiera reevaluation zależnych claims, coverage qualifications i wcześniejszych STOP inputs; historia wcześniejszej decyzji nie jest usuwana. Resolution jest osobną accepted decision wskazującą prior contradiction revision; successor resolved/reopened revision może wskazywać ją lub predecessor wyłącznie wstecz. Resolution decision nie może referencjonować future successor revision.

---

# 23. E3 — Expand & Hunt

E3 ma największy budżet discovery i powinno łączyć niezależne novelty search z późniejszym gap-directed exploitation.

## 23.1. Faza A — Blind Novelty Search

Policy określa wymagane lanes. Przykładowe ortogonalne strategie:

- E3-X Security / authority / trust,
- E3-Y State / data / catalog / recovery,
- E3-Z Frontend / concurrency / resources / cross-layer.

Przed checkpointem lane nie ma dostępu do cumulative finding corpus. Jeżeli ma powstać verified blind-origin claim, run musi spełniać wymagany isolation profile i Discovery Event musi istnieć przed potential reveal.

## 23.2. Faza B — checkpoint

Powstaje sealed checkpoint związany z exact accepted cut i z wszystkimi precursor discoveries/hypotheses, które mają zachować pre-reveal provenance.

## 23.3. Faza C — neutralny coverage/gap view

Nie ujawnia się „całego Coverage Ledger”. Coordinator buduje **phase-specific derived view**, który może pokazywać np. niewypełnione obligations, scope uncertainty i priorytety, ale nie może transitively ujawniać prior finding corpus ponad dozwolony policy zakres.

Od tego momentu praca jest jawnie klasyfikowana jako coverage-assisted/gap-directed, a nie blind.

## 23.4. Faza D — Gap-Directed Discovery

Audyt atakuje m.in.:

- unresolved/unknown scope,
- materialne obligations bez kwalifikowanego supportu,
- wysokie risk weights,
- nieprzebadane causal chains,
- invalidated/stale evidence,
- critical no-finding subsystems.

## 23.5. Faza E — cumulative corpus reveal

Dalsze granty ujawniają E1/E2/auxiliary/rejected/SOUND/unresolved materiały wyłącznie przez approved views. Późniejsza confirmation nie może retroaktywnie dostać wcześniejszego Knowledge State.

## 23.6. Faza F — external holdout reveal

Po własnym discovery można ujawnić niezależne holdouts. `MULTI_STAGE_FALSE_NEGATIVE` jest relacją względem **wskazanego corpus snapshot i zasad matchowania**, nie stwierdzeniem, że żaden audytor nigdy nie rozważał podobnej hipotezy.

Holdout po ujawnieniu staje się `CONSUMED` i nie może być ponownie reklamowany jako unseen evaluation.

---

# 24. Audit Priority Score

Budżet E3 nie powinien być równy dla wszystkich plików, ale priority score nie jest authority coverage ani materiality.

Przykładowe risk attributes:

```text
EXTERNAL_INPUT
TRUST_BOUNDARY
PRIVILEGE
PERSISTENCE
CONCURRENCY
IRREVERSIBLE_EFFECT
FAN_OUT
WEAK_TEST_SUPPORT
UNFULFILLED_OBLIGATIONS
KNOWN_UNOBSERVED_SCOPE
HISTORICAL_DEFECT_DENSITY
```

Priority planner korzysta z accepted inventory/invariant/obligation revisions. Nie może zmniejszać denominatora ani uznawać surface za bezpieczne dlatego, że wcześniejszy scoring był niski.

Weights i thresholds są wersjonowanym policy profile.

---

# 25. Exploration vs Exploitation

Nie wolno dopuścić, aby obszary z dużą liczbą findings pochłonęły cały budżet.

E3 zachowuje jednocześnie:

- risk/obligation-directed exploitation,
- otwarte exploration dla weakly observed / unknown / cross-layer scope.

Dokładny podział budżetu jest przypiętym **EffortProfile**, a nie stałą metodologii. Default profile może proponować proporcję orientacyjną, ale campaign musi raportować rzeczywiste wykorzystanie i nie może traktować samego wyczerpania budżetu jako saturation proof.

---

# 26. Multi-Modal Discovery w E3

E3 powinno uruchamiać nowe kanały:

- fuzzing,
- property-based generation,
- differential testing,
- metamorphic testing,
- static tool hypotheses,
- dynamic instrumentation.

Każdy kanał ma własne provenance.

---

# 27. Fuzzing

Szczególnie dla:

- parserów,
- URL processing,
- query parameters,
- IDs,
- pagination,
- metadata,
- file/path handling.

Seed corpus:

- valid input,
- minimal input,
- malformed input,
- truncated input,
- login page,
- antibot page,
- duplicate records,
- extreme values,
- unusual Unicode,
- mixed encodings.

Crash/invariant violation trafia do Hypothesis Ledger.

---

# 28. Differential Testing

Porównywane są ścieżki, które powinny mieć równoważną semantykę:

```text
fresh build
vs
cache reload

sync
vs
async

incremental refresh
vs
full refresh

local state
vs
remote synchronized state
```

Różnica stanu staje się hipotezą wymagającą adjudykacji.

---

# 29. Metamorphic Testing

Stosowane wtedy, gdy trudno znać dokładny expected result, ale znamy relację między wynikami.

Przykłady:

- zmiana kolejności rekordów nie powinna zmieniać set-like result,
- duplicate nie powinien zwiększać liczby unikalnych entities,
- semantycznie równoważna reprezentacja daty nie powinna zmieniać identity,
- nieistotna kolejność inputów nie powinna zmieniać final revision.

---

# 30. E4 — Deepen & Model

E4 nie powinno analizować finding po findingu.

Najpierw findings są grupowane w root-cause families, np.:

```text
AUTHORITY
DURABILITY
STATE CONSISTENCY
CATALOG TERMINATION
REMOTE INPUT TRUST
IDENTITY
CONCURRENCY
RESOURCE MANAGEMENT
FRONTEND CONSISTENCY
EVIDENCE / ORACLE
```

E4 bada rodziny pionowo.

---

# 31. State Machines i model–implementation conformance

E4 modeluje materialne subsystemy i root-cause families, ale model nie jest automatycznie dowodem o implementacji.

Każdy State Model powinien jawnie określać:

- states i transitions,
- guards/effects,
- mapping obserwowanych implementation events → model events,
- abstraction assumptions,
- omitted/provisional states,
- bounds,
- environment assumptions,
- conformance evidence.

Critical subsystem bez findingów nadal otrzymuje obligations wynikające z risk/scope. E4 nie może ograniczyć się do rodzin wcześniej znalezionych błędów.

Wniosek z bounded exploration dotyczy tylko zdefiniowanego modelu, zakresu i bounds. Bez bridge qualification nie wolno przekształcić go w globalny claim o implementacji.

---

# 32. Temporal Invariants

Niektóre błędy zależą od kolejności.

Przykłady:

```text
commit before acknowledge
validate before connect
publish after completeness
cancel obsolete generation before applying new state
remote result before success acknowledgement
ownership proof before destructive process action
```

E4 ma badać kolejność, nie tylko wartości końcowe.

---

# 33. Property-Based / Stateful Testing

Generator tworzy sekwencje operacji.

Przykład favorites:

```text
local add
remote fail
sync
restart
remote remove
sync
```

Po każdej operacji sprawdzane są invariants.

Przykład catalog:

```text
fetch success
empty response
timeout
retry
cache import
restart
publish
query
```

Celem jest znalezienie sekwencji, której ręcznie nie przewidziano.

---

# 34. Bounded Model Exploration

Dla małych krytycznych modeli można systematycznie eksplorować wszystkie sekwencje do pewnej długości N.

Nie modelować całej aplikacji.

Nadaje się do:

- revision state,
- local/remote favorite state,
- sync state,
- generation switch,
- cache lifecycle,
- retry state.

---

# 35. Deterministic Fault Laboratory

Wspólna biblioteka faultów:

```text
DISK_FULL
PERMISSION_DENIED
PARTIAL_WRITE
HTTP_TIMEOUT
HTTP_200_INVALID_HTML
HTTP_PARTIAL_BODY
DNS_CHANGE
REDIRECT_CHANGE
CONNECTION_RESET
CLOCK_JUMP
STALE_CACHE
PROCESS_PORT_OCCUPIED
THREAD_STALL
RESTART
```

Każdy fault:

```text
FAULT_ID
INJECTION_POINT
SEED
CONTROL_RUN
FAULT_RUN
EXPECTED_INVARIANT
OBSERVED_STATE
CLEANUP
```

---

# 36. Concurrency Exploration

Nie polegać wyłącznie na „uruchom 100 razy”.

Dla krytycznych sekcji stosować bounded interleaving harness.

Punkty przełączeń np.:

```text
before lock
after lock
before mutation
after mutation
before callback
after callback
before publish
```

Reproducer musi zawierać seed/interleaving umożliwiający replay.

---

# 37. Crash-Point Enumeration

Dla operacji wielostopniowych:

```text
A
B
C
D
```

symulować crash:

```text
after A
after B
after C
```

Po restart:

- sprawdzić legalność stanu,
- brak false success,
- brak częściowo opublikowanej generacji,
- retry/recovery.

Szczególnie ważne dla:

- persistence,
- catalog publication,
- cache lifecycle,
- synchronization.

---

# 38. Endurance / Resource Ownership

Dla:

- SSE,
- thread maps,
- executors,
- caches,
- locks,
- storyboard states,
- scanner pools,

wykonać bounded endurance tests.

Obserwować:

- thread count,
- open resources,
- map size,
- queue depth,
- pending jobs,
- memory trend,
- stale callbacks.

Invariant:

```text
repeated connect/disconnect/failure/retry
must not create unbounded retained state
```

---

# 39. Causal-Chain Coverage

Nie wystarczy sprawdzić pojedyncze funkcje.

BDB ma ewidencjonować całe ciągi przyczynowe.

Przykład:

```text
external response
→ parser
→ raw cache
→ catalog state
→ revision publication
→ API
→ frontend
```

Każdy ważny chain otrzymuje:

```text
CHAIN_ID
START_SURFACE
END_EFFECT
INVARIANTS
TEST_DEPTH
FAILURE_POINTS
RESIDUAL_UNCERTAINTY
```

---

# 40. E5 — Attack & Synthesize

E5 nie jest kolejnym generalnym audytem.

Jego rolą jest atakowanie interakcji.

---

# 41. Failure Interaction Graph

Nodes = failure modes/root causes.

Edges = możliwość spotkania się na tej samej causal path.

Przykład:

```text
DNS decision
↔ redirect
↔ stream retry
↔ cached URL
```

albo:

```text
provider malformed page
↔ parser
↔ raw cache
↔ catalog completeness
↔ retry suppression
↔ frontend stale revision
```

Testować:

- pairwise,
- selected 3-way,
- wysokiego ryzyka 4-way,

a nie wszystkie kombinacje.

---

# 42. Mutation Testing

Mutation ma być invariant-targeted. Globalny mutation score jest co najwyżej metryką pomocniczą.

## 42.1. Implementation mutation

Mutation implementation musi posiadać exact execution variant identity: baseline, patch/resulting bytes, harness/environment/fixtures oraz activation witness.

Pytanie brzmi:

> Czy kwalifikowany oracle wykrywa aktywowane naruszenie invariant?

Statusy muszą rozróżniać co najmniej aktywowany mutant, mutant nieaktywowany, invalid mutation i harness failure.

## 42.2. Oracle mutation — kontrast 2×2

Samo usunięcie fresh readback i ponowny PASS na poprawnym systemie **nie dowodzi**, że oracle było słabe lub zbędne.

Ocena jakości oracle wymaga kontrastu co najmniej:

```text
CLEAN TARGET + STRONG ORACLE
CLEAN TARGET + MUTATED ORACLE
KNOWN-DEFECTIVE TARGET + STRONG ORACLE
KNOWN-DEFECTIVE TARGET + MUTATED ORACLE
```

oraz dowodu aktywacji znanego naruszenia.

Przykładowe wyniki:

- MUTANT_KILLED,
- MUTANT_SURVIVED,
- MUTATION_NOT_ACTIVATED,
- REDUNDANT_OBSERVER,
- HARNESS_FAILURE,
- INVALID_MUTATION,
- INCONCLUSIVE.

Dopiero utrata detekcji aktywowanego known violation wspiera wniosek o słabości usuniętego elementu oracle.

## 42.3. Specification mutation

Specification mutation musi posiadać zewnętrzne wobec mutowanej spec źródło oczekiwanego kontraktu. Sam fakt, że testy i zmieniona spec są ze sobą zgodne, nie jest dowodem poprawności.

---

# 43. Auditor Calibration

Calibration bada czułość procesu na kontrolowanym corpus; nie dowodzi kompletności audytu realnego produktu.

Corpus rozdziela:

```text
DEVELOPMENT CORPUS
CALIBRATION CORPUS
UNSEEN HOLDOUT
SEEDED KNOWN DEFECTS
SCOPED CLEAN CONTROLS
UNSEEDED REAL FINDINGS
```

Należy zdefiniować jednostkę defect/scenario i kwalifikowany matching finding→defect. Finding poza seed list nie jest automatycznie false positive — podlega niezależnej adjudykacji.

Raportuje się per-class denominators, unknown counts, wariancję między runs i effort/budget profile. Konkretny próg liczbowy lub minimalna liczba runs jest **policy/calibration profile** dobranym na podstawie corpus i kosztu FN/FP, a nie globalną stałą metodologii.

Ujawniony holdout jest `CONSUMED` i nie może być ponownie użyty jako niewidziany test porównawczy.

---

# 44. E5-B1 — False-Positive Skeptic

Osobny challenger.

Cel:

> obalić HIGH/MEDIUM, SOUND, severity i evidence.

Dla każdego findingu pyta:

- czy reproducer sam tworzy efekt?
- czy observer jest niezależny?
- czy reachability jest prawdziwa?
- czy istnieje alternatywne wyjaśnienie?
- czy impact jest zawyżony?
- czy dwa root causes błędnie scalono?
- czy severity ma właściwy zakres?

---

# 45. E5-B2 — False-Negative Hunter

Drugi niezależny challenger.

Cel:

> znaleźć jeden materialny/release-changing mechanizm, którego E1–E5-A nie znalazły.

Nie zajmuje się obalaniem istniejących findings.

Atakuje negative space.

To rozdziela dwa przeciwne biasy.

---

# 46. Replayable Evidence Capsules

Materialny dynamic finding powinien być możliwy do odtworzenia z kapsuły opisującej **exact execution**, a nie tylko source SHA.

Capsule wiąże co najmniej:

```text
SUBJECT SOURCE GENERATION
EXECUTION VARIANT
ENVIRONMENT PROFILE
DEPENDENCY SET
HARNESS / FIXTURE / SEED
COMMAND / INPUT
INVARIANT / CLAIM / OBLIGATION
OBSERVATION PATHS
RAW OBSERVATIONS / HASHES
CLEANUP
LIMITATIONS
```

Capsule jest narzędziem reprodukowalności obserwacji. Nie podnosi automatycznie independence ani nie przenosi applicability na inny source/environment.

---

# 47. Independent Replay

Dla HIGH i ważnych MEDIUM drugi executor może dostać kapsułę i oczekiwane observable bez interpretacji findingu.

Replay potwierdza, że obserwacja jest odtwarzalna w swoim execution context. Nie dowodzi sam z siebie poprawności wspólnego oracle, parsera czy expectation.

Jeżeli replay się nie odtwarza albo wymaga zmiany target context:

```text
REPRODUCIBILITY_CONFLICT
```

powstaje scoped contradiction i finding/evidence wymagają rekwalifikacji. Nie wolno zachować silniejszego current support wyłącznie dlatego, że historycznie był `CONFIRMED`.

---

# 48. Evidence Independence — claim-relative dependency qualification

Independence nie jest etykietą `E0–E3` nadawaną na podstawie liczby procesów lub restartu.

Dla konkretnego claimu zapisuje się observation path oraz materialne dependencies, np.:

- parser/deserializer,
- cache,
- DB abstraction/read path,
- harness,
- fixture generator,
- oracle implementation,
- environment,
- external boundary,
- model/agent/tool family.

Następnie kwalifikuje się, **które failure assumptions dana obserwacja faktycznie przełamuje**.

Dwa procesy używające tego samego błędnego deserializera nie tworzą dwóch niezależnych oracle. Fresh instance może być mocniejsze tylko dla odpowiedniej klasy założenia, np. pamięci procesu; nie ma uniwersalnej premii.

E0–E3 może pozostać jako derived presentation profile, ale gate używa claim-relative qualifications i exact evidence applicability.

---

# 49. Supply-Chain / Release Assurance Lane

Release readiness audytowanego produktu nie może oznaczać tylko runtime correctness. Osobny lane bada m.in.:

- dependency pinning i vulnerable dependencies,
- CI workflow permissions i dangerous workflow patterns,
- branch/release governance,
- provenance artifactów,
- reproducibility,
- artifact composition,
- signing/tagging, jeśli stanowi część rzeczywistego release modelu,
- build inputs i dependency/runtime drift.

Baseline może zaczynać się w E1, verification w E2/E3, a final challenge w E5.

## 49.1. Oddzielny build/runtime contract samego BDB

Supply-chain ocena subjectu nie może być mieszana z własnym build assurance BDB. Dla dystrybucji `standalone deterministic .py` BDB definiuje osobny contract:

- complete declared application build inputs,
- builder/recipe/toolchain identity,
- pinned/vendored dependencies albo jawnie external-tool boundary,
- restricted loader bez niejawnego importu z cwd,
- supported interpreter/stdlib/platform profile,
- deterministic payload rules,
- external final release digest bez self-reference cycle,
- modular ↔ standalone parity dla krytycznych ścieżek.

`Standalone` oznacza zamknięcie bytes aplikacji i jej wymaganych zasobów w deklarowanej granicy runtime. Nie oznacza automatycznie dołączenia interpretera, OS ani wszystkich opcjonalnych narzędzi. Konkretny packer i backend build są decyzją implementacyjną/ADR; metodologia wymaga zamknięcia wejść i jawnej granicy runtime, nie konkretnej technologii.

---

# 50. Canonical history i główne projekcje

BDB utrzymuje **jedną canonical accepted commit history**. Poszczególne ledgery pozostają nazwami domenowych facts lub eksportowanych widoków, a nie niezależnymi mutable heads.

## 50.1. Canonical Audit History — KEEP

Zawiera zaakceptowane events/decisions, exact immutable object revisions, command receipts, history cut i bindings source/policy/run/attempt.

## 50.2. Finding / Hypothesis facts — KEEP w historii

Finding i Hypothesis posiadają logical identity, revision history i osobne epistemic assessments. Statusów nie przepisuje się wstecz.

## 50.3. Coverage Ledger — DERIVE

Authority stanowią Coverage Obligations, evidence qualifications i scope decisions. `Coverage Ledger`, breadth i D0–D5 są projekcjami `as_of_head`.

## 50.4. Invariant Registry — KEEP jako versioned contracts

Invariant revisions są canonical objects związanymi z policy i obligations.

## 50.5. Contribution Ledger — DERIVE

Contribution wynika z Discovery Events, Knowledge States, corpus-match decisions i qualification statusów. Nie jest niezależnym źródłem autorstwa.

## 50.6. Knowledge/Exposure Ledger — MERGE + DERIVE

Grant, potential exposure, contamination i discovery facts trafiają do canonical history; czytelny ledger/Knowledge State jest projekcją lub immutable object wskazującym exact cut.

## 50.7. Root Cause / Contradiction / Blocker views

Membership, merge/split, contradiction resolution, waivers i invalidations są canonical decisions. Root Cause Ledger, Contradiction Ledger i Blocker Ledger mogą istnieć jako exports/views bez własnego authority head.

## 50.8. Traceability / Evidence graphs — DERIVE

Graph traversal i current support są wyliczane z typed refs i zaakceptowanych semantic relations. Graph database, distributed broker lub osobny event bus nie są wymagane w baseline local profile.

---

# 51. Contribution Metrics — derived i scope-bound

Contribution mierzy wartość discovery bez zamieniania popularności w prawdę.

Przydatne derived metrics:

```text
UNIQUE QUALIFIED DISCOVERY
SUPPORT COUNT
LEAVE-ONE-OUT CONTRIBUTION
CROSS-LANE OVERLAP
ROOT-CAUSE FAMILY CONTRIBUTION
```

Każda metryka musi wskazywać exact corpus revision, discovery cut, match/adjudication policy i current applicability. Późniejsze contamination, merge/split albo invalidation mogą zmienić bieżącą metrykę bez przepisywania historycznego Discovery Event.

Reveal order nie jest wiarygodnym substytutem niezależności ani realnej wartości audytora.

---

# 52. Evidence Applicability i transitive invalidation

Evidence jest historycznym faktem obserwacji, a jego **bieżąca zastosowalność** jest relacją:

```text
EVIDENCE
× CLAIM REVISION
× SUBJECT BASELINE
× EXECUTION VARIANT
× ENVIRONMENT
× HARNESS / FIXTURE / DEPENDENCY SET
```

Przykładowe effective states:

- ACTIVE,
- SCOPED,
- STALE,
- INVALIDATED,
- BLOCKED,
- CONFLICTED.

Zmiana source SHA jest tylko jednym z powodów utraty applicability. Invalidation może wynikać również z:

- błędu harnessu,
- złego independent readera,
- fixture corruption,
- dependency drift,
- nieaktywnej mutation,
- błędnego target binding.

Invalidation propaguje się transitively do wszystkich zależnych support paths, Coverage Obligations, SOUND/finding assessments, Final Assurance Case i STOP inputs. Historyczny record pozostaje nienaruszony; current support jest przeliczany na nowym accepted cut.

---

# 53. Assurance Case lifecycle — candidate przed STOP, conclusion po STOP

Nie wolno tworzyć cyklu:

```text
Final Assurance Case requires STOP
STOP requires Final Assurance Case
```

Docelowy porządek:

```text
E1–E4 StageCompletion + E5A attack/synthesis prerequisites complete
↓
CANDIDATE ASSURANCE CASE (immutable cut)
↓
E5B challenger assignments (skeptic + hunter)
↓
challenger results / adjudication for exact candidate
↓
E5 StageCompletion
↓
FINAL_POST_E5 STOP EVALUATION on exact input cut
↓
CAMPAIGN CONCLUSION
↓
FINAL ASSURANCE CASE
↓
RELEASE QUALIFICATION
```

`completed required stages` nie może oznaczać pełnego E5 przed candidate. E5 jest jawnie rozcięte na E5A (przed candidate) i E5B (po candidate); global STOP/conclusion/release nie są prerequisite E5 StageCompletion.

W baseline R5.3 materialna rewizja Candidate Assurance Case po challengerach wymaga nowych **obu** required challenger roles (skeptic + hunter) dla nowej exact candidate revision. Scoped reuse jest poza baseline i wymaga przyszłego, osobno kwalifikowanego profile.

Assurance Case wiąże:

- frozen source/policy/spec revisions,
- scope/inventory uncertainty,
- Coverage Obligations i evidence qualifications,
- findings/SOUND/contradictions,
- challengers,
- residual risks,
- explicit limitations.

Nie implikuje automatycznie release readiness produktu.

## 53.1. Successor assurance po CampaignConclusion

Accepted `CampaignConclusion` pozostaje immutable i nie wraca do AUDIT_RUNNING. Materialny późniejszy trigger może oznaczyć jego current applicability jako STALE, ale nowe assurance jest budowane w **successor campaign** z backward refs do predecessor campaign/conclusion i triggera. Carried-forward evidence wymaga current applicability; dwa konkurencyjne successor branches są fail-closed do accepted `SuccessorCampaignSelectionDecision` wiążącej exact candidate branch set i jednego selected successor; selector nie używa timestamp/latest-by-name. Release-only drift, który nie zmienia audit assurance basis, pozostaje w release qualification lifecycle.

---

# 54. Residual Risk Register

Nawet jeśli:

```text
UNRESOLVED_MATERIAL_FINDINGS = 0
```

może nadal istnieć niepewność.

Przykład:

| Area | Residual uncertainty | Status |
|---|---|---|
| live provider behavior | live dependency unavailable | BLOCKED |
| physical Windows process effect | destructive live test prohibited | BLOCKED |
| production DNS behavior | environment-specific | BOUNDED |
| external account sync | no authorized live account | BLOCKED |

Brak candidate ≠ brak niepewności.

---

# 55. STOP GATE — phase-aware decision, nie licznik findings

STOP jest czystą, wersjonowaną ewaluacją na **exact immutable input cut**. Nie może czytać „najświeższego pliku” ani dowolnej mutable projection.

## 55.1. Cztery normatywne osie C12

BDB rozdziela dokładnie:

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

`continuation_decision` jest wynikiem pure STOP evaluator. `termination_state` zmienia się dopiero przez osobny accepted `CampaignConclusion` command. `release_readiness` jest odrębną kwalifikacją produktu względem pinned release policy.

STOP ma pinned `evaluation_context`: `INTERMEDIATE`, `FINAL_POST_E5` albo `POST_E6`. Intermediate STOP jest dozwolony po wcześniejszych StageCompletion i nie wymaga Candidate Assurance Case/challengerów; nie może zwrócić PASS ani E6_REQUIRED, tylko `CONTINUE_REQUIRED` lub fail-closed `BLOCKED`. Candidate/challenger prerequisites obowiązują dla final/post-E5 i odpowiedniego post-E6 STOP.
W `INTERMEDIATE` release axis również pozostaje fail-closed: nie wolno zwrócić `READY` ani `READY_WITH_RESIDUAL_RISK`; bez zamkniętych release prerequisites wynik jest `QUALIFICATION_BLOCKED`, chyba że bieżący kwalifikowany defect już wymusza `TECHNICALLY_NOT_READY`.
`COMPLETED_LIMITED` może zakończyć trwale blocked campaign także przed final candidate/challenger closure, ale wymaga exact bounded-basis refs i nie może użyć pełnego `COMPLETED`/PASS semantics.

Audyt może zakończyć się poprawnie (`PASS` + `COMPLETED`) i jednocześnie wskazać `TECHNICALLY_NOT_READY` z powodu potwierdzonego nieakceptowalnego defektu. Operator może zakończyć niewykonalną pracę jako `COMPLETED_LIMITED`; nie może tym samym commandem zmienić `BLOCKED` w `PASS`.

## 55.2. Hard obligations

Wersjonowany policy profile definiuje obowiązkowy zbiór hard conditions. Typowe klasy obejmują:

- wymagane stages/lanes zakończone na aktualnym cut,
- brak niespełnionych material Coverage Obligations wymagających PASS/violation adjudication,
- brak unresolved material contradictions bez jawnego ograniczenia conclusion,
- wszystkie użyte evidence applicable i kwalifikowane,
- required replays/challengers/supply-chain checks zakończone,
- source/history/provenance integrity spełnione,
- unknown/unsupported scope potraktowane zgodnie z policy,
- residual risks/waivers jawnie zaakceptowane przez uprawnioną rolę.

`UNKNOWN`, `BLOCKED`, `TESTING`, `INSUFFICIENT_DATA` i `WAIVED` nie stają się PASS przez samą zmianę statusu.

## 55.3. Saturation i soft signals

Soft metrics, np. marginal discovery, coverage delta, challenger novelty czy fuzz novelty, są sygnałami planowania. Nie dowodzą completeness.

Aby saturation mogło wpływać na decyzję, input musi mieć jawny **EffortProfile** określający required rounds/method families/budget/controls. Konkretne liczby są policy/default profile, a nie globalnym invariantem BDB.

Brak wystarczających danych → `INSUFFICIENT_DATA`, nie „zero nowych findingów”.

## 55.4. Decision precedence

Normatywna kolejność, od pierwszego pasującego warunku:

| Priorytet | Warunek | continuation_decision | assurance_level / konsekwencja |
|---|---|---|---|
| 1 | authority/history integrity failure, source/policy conflict, brak wymaganego admission, nieweryfikowalny cut | `BLOCKED` | `INSUFFICIENT`; brak kwalifikowanego release |
| 2 | unmet material obligation, której nie wolno/nie można wykonać albo brak zatwierdzonego budżetu | `BLOCKED` | `BOUNDED` albo `INSUFFICIENT`; jawny blocker |
| 3 | wymagane zwykłe etapy przed globalnym post-E5 STOP nie są zakończone, a dalsza praca jest wykonalna | `CONTINUE_REQUIRED` | brak finalnego PASS; wykazać brakujące etapy |
| 4 | etapy zakończone, ale istnieją wykonalne material gaps / unresolved contradictions / niepełny challenge / insufficient effort | `E6_REQUIRED` | `BOUNDED`; tylko przy dozwolonym i finansowanym planie uzupełnienia |
| 5 | wszystkie mandatory applicable obligations, scope, challenges i effort prerequisites spełnione; brak material counterevidence bez resolution | `PASS` | `ADEQUATE_FOR_DECLARED_SCOPE`; release oceniany niezależnie |

Warunek 5 nie jest domyślnym `else`. Pending E4/E5 po E3 daje `CONTINUE_REQUIRED`, nie `E6_REQUIRED`.

`NOT_APPLICABLE` usuwa obligation z applicable set tylko po kwalifikowanej decyzji. `WAIVED` nie spełnia pierwotnej obligation. `ACCEPTED_RESIDUAL_RISK` toleruje znane ryzyko w zakresie uprawnień, lecz nie naprawia invalid evidence ani fałszywego claimu.

Znany nieakceptowalny defekt daje `TECHNICALLY_NOT_READY`. Brak wymaganej kwalifikacji release daje `QUALIFICATION_BLOCKED`. Tylko formalnie zaakceptowane residual risks zgodne z release profile mogą prowadzić do `READY_WITH_RESIDUAL_RISK`.

---

# 56. Adaptive E6 — rozszerzenie scope, nigdy osłabienie obowiązków

E6 uruchamia się tylko na podstawie jawnego STOP result i zaakceptowanego planu uzupełnienia.

E6 może:

- dodać targeted lanes,
- rozszerzyć inventory/scope,
- dodać invariants/obligations,
- wykonać brakujące experiments/replays,
- rozstrzygnąć konkretną contradiction.

E6 **nie może**:

- obniżyć globalnych hard obligations tylko po to, aby uzyskać PASS,
- przepisać wcześniejszych Discovery Events/Knowledge States,
- zmienić source generation,
- usunąć unresolved scope bez jawnej scope decision/waiver,
- retroaktywnie uznać wcześniejszych testów za silniejsze evidence.

Po E6 następuje ponowna STOP evaluation na nowym exact cut z odziedziczonymi global constraints.

---

# 57. Remediation po E5

Dopiero po zakończeniu audytu starego SHA rozpoczynają się naprawy.

Dla każdego root cause przed implementacją fixu powstaje:

```text
REPAIR_UNIT_ID
ROOT_CAUSE
EXPECTED_FIXED_PROPERTY
REGRESSION_TEST
NEGATIVE_CONTROL
SIBLING_TESTS
HOLDOUT_VERIFICATION
```

Najpierw definiujemy, jak udowodnimy naprawę.

Dopiero później implementowany jest fix.

---

# 58. Requalification na nowym SHA

Nowy source generation otrzymuje nowe:

- SHA,
- tree,
- snapshot,
- source capsule.

Stare evidence zostaje oznaczone:

```text
VALID_FOR_PREVIOUS_SOURCE
```

i nie jest automatycznie przenoszone.

Requalification ma:

1. odtworzyć wszystkie materialne repro capsules,
2. zapisać osobny `RequalificationDisposition`: `FIXED / STILL_PRESENT / PARTIALLY_FIXED / REGRESSION / BLOCKED`,
3. wykonać sibling tests,
4. sprawdzić nowe regresje,
5. ponownie wykonać critical SOUND,
6. uruchomić targeted mutation controls,
7. zweryfikować release/supply-chain state.

---

# 59. Klasyfikacja historii findings i discovery

Historia findingu nie może być jednym nadpisywanym polem origin/status.

Normatywny `FindingLifecycle` to:

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

`STILL_PRESENT`, `FIXED`, `PARTIALLY_FIXED`, `REGRESSION` i `BLOCKED` należą do osobnego `RequalificationDisposition`; nie tworzą drugiego FindingLifecycle.

Należy rozdzielić:

- discovery event i jego exact knowledge cut,
- producer/method origin,
- confirmation history,
- match względem exact corpus revision,
- novelty/previous-false-negative relationship,
- finding lifecycle,
- evidence applicability,
- root-cause membership revisions.

Derived labels mogą obejmować:

- PRE_REPORT_REDISCOVERY,
- REPORT_ASSISTED_VERIFICATION,
- PREVIOUS_FALSE_NEGATIVE,
- MULTI_STAGE_FALSE_NEGATIVE,
- NEW_BLIND_DISCOVERY,

ale tylko wtedy, gdy wszystkie prerequisites są udowodnione. UNKNOWN historical exposure lub brak precursor event ogranicza etykietę; nie można jej zgadywać wstecz.

---

# 60. Metryki jakości procesu

Nie tworzyć jednej sztucznej liczby typu „Audit Quality 98.7%”. Metryki są derived views `as_of` exact history cut i zawsze mają denominator/scope.

## Discovery

- qualified unique discoveries,
- new root-cause families per lane,
- previous/multi-stage false negatives względem exact corpus revisions,
- contamination/downgrade count.

## Precision / adjudication

- rejected hypotheses,
- confirmed false positives,
- reproducibility conflicts,
- reopened contradictions.

## Coverage

- fulfilled mandatory obligations / applicable obligations,
- blocked/unknown/waived obligations osobno,
- known-unobserved / unsupported scope,
- derived D distribution wyłącznie jako skrót prezentacyjny.

## Evidence

- claim-relative independence qualifications,
- replay reproducibility,
- applicability ACTIVE/SCOPED/STALE/INVALIDATED,
- number of claims depending on shared material oracle nodes.

## Oracle strength

- activated implementation mutations killed,
- contrastive oracle mutations killed/survived,
- invalid/non-activated mutants,
- surviving material mutation obligations.

## Saturation / effort

- marginal qualified discovery per declared effort unit,
- obligation delta,
- new family rate,
- challenger novelty,
- fuzz novelty,
- `INSUFFICIENT_DATA` count.

Metryki nie zastępują hard STOP obligations i nie dowodzą completeness produktu.

---

# 61. Discovery Saturation — pomocniczy sygnał przy jawnie określonym wysiłku

Overlap i marginal discovery są użyteczne do planowania, ale nie są estymatorem kompletności produktu o gwarantowanej poprawności.

Przykładowe sygnały:

```text
NEW_HIGH_RATE
NEW_MEDIUM_RATE
NEW_ROOT_CAUSE_FAMILY_RATE
UNIQUE_QUALIFIED_RATE
COVERAGE_OBLIGATION_DELTA
FUZZING_NOVELTY
MUTATION_SURVIVORS
CHALLENGER_NOVELTY
```

Każda metryka musi wskazywać:

- exact campaign/history cut,
- effort/budget denominator,
- method families,
- current evidence applicability,
- consumed holdouts,
- limitations.

Capture-recapture i zaawansowane probabilistyczne modele pozostają opcjonalnymi heurystykami. Nie mogą zamieniać `UNKNOWN_SCOPE` lub `INSUFFICIENT_DATA` w PASS.

---

# 62. Environment Matrix

Audyt powinien jawnie definiować środowiska materialne dla zachowania systemu.

Przykładowe osie:

| Dimension | Values |
|---|---|
| OS | supported Windows versions |
| runtime | supported Python versions |
| browser | supported Chrome versions |
| filesystem | writable / denied / partial failure |
| network | normal / timeout / reset / offline |
| DNS | stable / change |
| account | configured / unconfigured |
| cache | fresh / stale / corrupt |

Nie testować pełnego iloczynu kartezjańskiego.

Wybór ma być risk-based.

---

# 63. Mechanical readback, canonical history i package integrity

Każdy materialny gate/stage kończy się mechanicznym sprawdzeniem odpowiednim do swojego contractu:

- trusted accepted head / history cut,
- commit/receipt continuity i idempotency,
- immutable object/artifact revision hashes,
- source/policy/spec/run/attempt binding,
- F1/F2 ancestry/prefix constraints tam, gdzie dotyczą legacy/protocolu,
- checkpoint input cut i gate decision binding,
- no mixed source generation,
- view/grant/Knowledge State consistency,
- evidence execution/applicability references,
- artifact/export membership i `as_of_head`,
- readback finalnych machine-readable decisions.

Usunięcie lub uszkodzenie derived projection nie może zmieniać wyniku gate — projection ma być odtwarzalna z canonical history. Uszkodzenie authority/history nie jest naprawiane przez ciche cofnięcie do ostatniego czytelnego pliku; prowadzi do BLOCKED/recovery zgodnie z trust profile.

Protocol conformance pozostaje osobne od technical conclusion oraz subject release readiness.

---

# 64. Docelowa geometria całego systemu

```text
E0 — CONSTITUTION / FOUNDATION
│
├─ SOURCE + POLICY + TRUST PROFILE
├─ CANONICAL HISTORY / IDENTITY CONTRACT
├─ INVENTORY SCOPE + INVARIANTS
├─ COVERAGE OBLIGATIONS
├─ KNOWLEDGE / VIEW / DISCOVERY RULES
├─ EXPERIMENT / EVIDENCE CONTRACT
└─ CONTROL-PLANE SECURITY
│
▼
E1 — DISCOVER
│  diverse lanes + accepted Discovery Events
▼
E2 — VERIFY
│  blind checkpoint → controlled reveal → individual adjudication
▼
E3 — EXPAND
│  blind novelty → checkpoint → neutral gap view → gap-directed hunt → holdout
▼
E4 — DEEPEN
│  state/temporal/property/fault/concurrency/model work + implementation conformance
▼
E5A — ATTACK / SYNTHESIS
│  interactions + contrastive mutations + calibration
▼
CANDIDATE ASSURANCE CASE
▼
E5B — DUAL CHALLENGE
│  skeptic + hunter against exact candidate
▼
E5 STAGE COMPLETION
▼
STOP EVALUATION ON EXACT CUT
├─ CONTINUE_REQUIRED
├─ E6_REQUIRED → targeted E6 → STOP again
├─ BLOCKED / bounded conclusion
└─ PASS
     │
     ▼
CAMPAIGN CONCLUSION (`COMPLETED`)
     │
     ├─ `TECHNICALLY_NOT_READY` → remediation on new SourceGeneration
     ├─ `QUALIFICATION_BLOCKED` → brak release qualification
     └─ `READY` / `READY_WITH_RESIDUAL_RISK` → product release decision
          │
          ▼
     REQUALIFICATION AFTER ANY MATERIAL SOURCE CHANGE
```

Przez cały pipeline działa jeden foundation model:

```text
CANONICAL ACCEPTED HISTORY
+ IMMUTABLE REVISIONS
+ DERIVED VIEWS
```

Coverage, knowledge summaries, contribution, blockers i graphs są obliczane `as_of` wskazany history cut; nie mogą mieć własnego konkurencyjnego authority.

---

# 65. Co dokładnie zmienić względem obecnego BDB

## Priorytet FOUNDATION — przed nową semantyką v2

1. Ustalić trust profile i trusted coordinator boundary.
2. Wprowadzić jedną transactional accepted history, immutable revisions, idempotent receipts i monotonic accepted head.
3. Ustalić canonical identity/revision profile w Data Contracts + ADR; nie duplikować go w innych dokumentach.
4. Przypinać exact protocol/policy/spec/application revisions do runów.
5. Wprowadzić Knowledge Isolation profile: ENFORCED / DECLARED / UNKNOWN + contamination.
6. Dodać first-class Discovery Event i rozdzielić discovery/confirmation/matching/novelty.
7. Zastąpić blacklist/redaction modelem positive View Manifest + restricted resolver.
8. Rozszerzyć Surface Inventory o assigned-input accounting i unknown/unsupported scope.
9. Zastąpić scalar coverage modelem first-class Coverage Obligations; D0–D5 tylko derived.
10. Wprowadzić claim-relative evidence dependency qualification.
11. Oddzielić subject baseline, execution variant, environment, harness/fixture/dependencies i transitive invalidation.
12. Rozdzielić stage completion, campaign termination, assurance sufficiency i subject release readiness.
13. Ustalić acyclic finalization: candidate → challengers → STOP → conclusion.
14. Ustalić legacy E2 admission bez retcon E0 i bez przenoszenia nieudowodnionej blindness; pierwszy bootstrap ma być jednym exact `EMPTY_HISTORY` atomic commit z pinned installation bootstrap profile, admission przed CampaignGenesis i bez synthetic H0.
15. Oddzielić compatibility preservation od independent correctness.
16. Wprowadzić wczesny foundation reference slice z happy path i failure paths.

## Priorytet SUBSYSTEM — przed implementacją danego mechanizmu

17. Oracle mutation jako kontrast clean/known-defective z activation witness.
18. Versioned root-cause membership i scope-aware contradictions/reopen.
19. Model–implementation fidelity przed użyciem model proofs do assurance.
20. Closed build/runtime input model przed standalone claims.
21. Qualified calibration ground truth, holdout lifecycle i per-class metrics.

## Można bezpiecznie odłożyć

- rozbudowane probabilistic saturation/capture-recapture,
- pełne biblioteki fuzz/model adapters,
- distributed lanes / remote workers / graph DB,
- dokładny packer po minimalnym proof of feasibility,
- rozbudowane dashboardy contribution,
- pełny remediation engine po zamknięciu same-source pipeline, przy zachowaniu już teraz cross-source invalidation semantics.

---

# 66. Najważniejsze zasady, których nie wolno naruszyć

1. Nie mieszać source generations w jednej same-source campaign.
2. Nie naprawiać audytowanego source pomiędzy E1–E5.
3. Nie traktować executora ani jego bundle jako authority aktualnego stanu.
4. Nie utrzymywać kilku niezależnych mutable heads dla tych samych facts.
5. Nie ujawniać semantic prior corpus przed wymaganym sealed precursor/checkpoint.
6. Nie nazywać lane `ENFORCED blind`, jeśli kanały nie są realnie kontrolowane.
7. Nie przypisywać discovery do wcześniejszego Knowledge State po reveal.
8. Nie traktować scanner output jako finding.
9. Nie traktować większości głosów/support count jako prawdy.
10. Nie przenosić evidence na nowy source/context bez rekwalifikacji applicability.
11. Nie traktować `NO_FINDING` jako SOUND bez spełnionych obligations i jawnego scope uncertainty.
12. Nie przyznawać coverage depth przez pojedynczy test lub nieaktywną mutację.
13. Nie używać circular/shared oracle jako „niezależnego” evidence bez jawnej dependency qualification.
14. Nie kończyć audytu tylko dlatego, że osiągnięto E5.
15. Nie interpretować saturation jako dowodu kompletności.
16. Nie pozwalać E6 obniżać odziedziczonych obligations dla uzyskania PASS.
17. Nie scalać findings przed indywidualną adjudykacją ani nie dziedziczyć evidence przez root-cause membership.
18. Nie nadpisywać historycznych decisions; każda korekta jest nową revision/event.
19. Nie używać samego hash manifestu jako dowodu autentyczności/freshness bez właściwego trust binding.
20. Nie ujawniać realnych sekretów w raportach.
21. Nie wykonywać destrukcyjnych live effects bez jawnego upoważnienia.
22. Nie pozwalać treści repo sterować control plane audytora.
23. Nie utożsamiać STOP PASS z release READY.
24. Nie używać jednego procentu coverage jako finalnego dowodu jakości.

---

# 67. Dlaczego pięć etapów jest optymalne

Pięć etapów odpowiada pięciu różnym klasom problemu epistemicznego:

```text
E1 — DISCOVER
Co widzimy?

E2 — VERIFY
Czy to jest prawdą?

E3 — EXPAND
Czego nadal nie widzimy?

E4 — DEEPEN
Jak naprawdę działa mechanizm?

E5 — ATTACK
Czy cały model wytrzymuje próbę obalenia?
```

Dodatkowe obowiązkowe E6/E7 najczęściej powtarzałyby:

- discovery E3,
- depth E4,
- adversarial E5.

Dlatego lepiej zwiększać jakość **wewnątrz** etapów niż liczbę etapów.

E6 powinien być adaptacyjny i wynikać z konkretnego failu STOP GATE.

---

# 68. Najważniejszy końcowy cel BDB

Docelowy BDB nie powinien kończyć się zdaniem:

> „znaleźliśmy dużo błędów”.

Powinien być w stanie wykazać w granicach własnego trust/scope profile:

> „Zamroziliśmy exact Source Generation i policy. Wszystkie zaakceptowane decyzje należą do jednej odtwarzalnej historii. Zinwentaryzowaliśmy znany zakres wraz z unresolved/unsupported scope. Zdefiniowaliśmy invariants i konkretne Coverage Obligations. Discovery ma jawne Knowledge/Exposure provenance. Eksperymenty i evidence są związane z exact execution context, a independence jest kwalifikowane względem claimu. Invalidation przelicza bieżący support bez przepisywania historii. E4 bada modele wraz z conformance do implementacji, a E5 atakuje interactions i oracle kontrastowymi mutacjami. Final challengers badają candidate assurance case. STOP ocenia exact cut, a niewiedza pozostaje niewiedzą. Residual risks i granice gwarancji są jawne.”

To jest docelowy standard BDB Audit vNext.

---

# 69. Skrócona roadmapa implementacyjna

Pełna kolejność implementacji należy do `BDB_AUDIT_V2_IMPLEMENTATION_ROADMAP.md`. Ten dokument wymaga jednak następującej kolejności zależności metodologicznych.

## Faza A — freeze i niezależna compatibility foundation

- zamrozić v1.4.4 i exact legacy bytes,
- zbudować compatibility corpus,
- oddzielić preservation expectations od independent safe/correctness expectations,
- nie przenosić znanej luki v1 do v2 tylko po to, aby zachować „100% compatibility”.

## Faza B — Assurance Foundation

Przed szeroką nową semantyką zamknąć:

- trust/coordinator model,
- canonical history/transaction/identity/revisions,
- policy/spec bindings,
- isolation/discovery/view semantics,
- inventory scope accounting,
- Coverage Obligations,
- evidence dependency/applicability,
- podstawowe FSM/stage-finalization i STOP inputs,
- legacy admission E2→v2 E3.

Konkretna referencyjna implementacja storage (np. SQLite dla lokalnego profilu) jest decyzją Architecture/ADR i nie zmienia tych wymagań semantycznych.

## Faza C — wczesny foundation reference slice

Zanim powstanie wiele zależnych engines, wykonać minimalny syntetyczny przepływ:

```text
pinned installation bootstrap profile
→ EMPTY_HISTORY legacy E2 admission + CampaignGenesis in one atomic commit
→ v2 E3 stage
→ isolated lane
→ discovery
→ checkpoint
→ controlled reveal
→ experiment/evidence qualification
→ coverage obligation update
→ stage completion
→ STOP = CONTINUE_REQUIRED (`REQUIRED_STAGES_PENDING`)
```

oraz obowiązkowe failure paths:

- contaminated lane,
- missing surface,
- shared oracle,
- crash w commit,
- stale legacy bundle,
- invalidated evidence,
- insufficient-data STOP.

## Faza D — E1/E2/E3 capabilities

Dopiero po foundation slice rozwijać pełne ensembles, claim quarantine, multi-report adjudication, gap-directed E3, fuzzing/differential/metamorphic adapters.

## Faza E — E4/E5

Następnie:

- state/temporal/property/model work z fidelity bridge,
- deterministic fault/concurrency/crash/endurance,
- interaction graph,
- implementation/oracle/spec mutations,
- calibration,
- candidate assurance case po E5A,
- dual challengers E5B dla exact candidate,
- E5 StageCompletion → STOP → conclusion.

Szczegółowe schemas E4/E5 nie muszą być zamrożone przed pierwszym utility commit, o ile nie zmieniają foundation semantics.

---

# 70. Finalny model organizacyjny

Najbardziej efektywna architektura nie oznacza „więcej raportów = lepszy audyt”, ani „więcej ledgerów = więcej assurance”.

Docelowa organizacja łączy:

```text
RÓŻNORODNOŚĆ DISCOVERY
→ KONWERGENCJA I ADJUDYKACJA
→ SEARCH OF NEGATIVE SPACE
→ SYSTEMATIC DEPTH + MODEL FIDELITY
→ ADVERSARIAL FALSIFICATION
```

z jednym foundation:

```text
ONE CANONICAL ACCEPTED HISTORY
+ IMMUTABLE CONTENT-BOUND REVISIONS
+ QUALIFIED EVIDENCE/APPLICABILITY
+ COVERAGE OBLIGATIONS
+ DERIVED VIEWS
```

Organizacyjnie:

- Campaign/Stage/Lane mogą być jednym transition service z osobnymi FSM/policies, nie mikroserwisami,
- Finding/Root Cause/Contradiction mogą korzystać ze wspólnego adjudication service,
- Exposure/Finding Change/Root Cause ledgers są domenowymi event families lub exports, nie osobnymi heads,
- Contribution/Coverage/Traceability/Blockers są przede wszystkim derived views,
- Surface collectors, Prompt Compiler i Legacy Compatibility Layer zachowują odrębne funkcje, ale nie stają się policy authority.

To upraszcza system bez osłabienia auditability.

---

# 71. Minimalne wyniki każdego etapu — stage completion ≠ campaign conclusion

Każdy stage ma własny immutable `StageCompletion` związany z exact cut i wymaganym StageSpec. Nie każdy etap tworzy FINAL_OUTCOME całej campaign.

## E1

Wymagane zgodnie z StageSpec m.in.:

- source/policy/trust bindings,
- inventory/invariant/obligation revisions,
- required lane completions,
- accepted Discovery Events/Hypotheses/observations,
- current evidence/finding projections,
- Knowledge/Exposure facts i stage completion cut.

## E2

- F1/F2 sealed checkpoints zgodne z policy,
- canonical predecessor binding,
- auxiliary corpus snapshot,
- individual adjudication decisions,
- root-cause membership revisions,
- contradiction decisions,
- shadow challenge result,
- current obligations/evidence qualifications,
- E2 StageCompletion.

## E3

- blind/declared novelty lane results zgodnie z isolation profile,
- sealed checkpoint,
- controlled gap/coverage views,
- gap-directed/fuzz/differential/metamorphic results wymagane przez StageSpec,
- holdout match/adjudication decisions,
- updated inventory/obligations/evidence,
- E3 StageCompletion.

## E4

- state/model revisions,
- model–implementation fidelity assessments,
- temporal/property/fault/concurrency/crash/endurance results zgodnie z obligations,
- causal-chain/sibling assessments,
- E4 StageCompletion.

## E5

E5A outputs:

- interaction/combinatorial results,
- qualified implementation/oracle/spec mutation results,
- calibration result w swoim profilu.

Następnie powstaje frozen `CandidateAssuranceCase`. E5B outputs:

- E5-B1 skeptic result dla exact candidate,
- E5-B2 hunter result dla tej samej exact candidate,
- challenger/adjudication results,
- `E5 StageCompletion`.

Dopiero po E5 StageCompletion powstają campaign-level artifacts: final STOP evaluation, CampaignConclusion, FinalAssuranceCase i ReleaseQualification. Residual Risk assessments są wejściami/projekcjami odpowiednich decyzji, nie sposobem odwrócenia DAG.

STOP/campaign artifacts nie są wymagane do wcześniejszego StageCompletion, chyba że konkretny StageSpec wymaga lokalnego continuation check — wtedy jest to odrębny stage gate, nie final campaign verdict.

---

# 72. Migracja z obecnego BDB do BDB Audit vNext

Historyczne E1/E2 pozostają immutable i nie są retroaktywnie przepisywane tak, jakby posiadały mechanizmy v2.

Historyczna semantyka pozostaje:

```text
E1 = BASE / Etap 1
E2 = ITERACJA 1 / Etap 2
```

Direct lineage:

```text
E1_CANONICAL
↓
E2_CANONICAL
↓
V2 E3
```

Auxiliary E1 reports pozostają osobnym corpus, nigdy dodatkowymi direct predecessors.

## 72.1. Cztery warstwy migracyjnej prawdy

Należy rozdzielić:

1. **historical raw fact** — exact legacy bytes,
2. **mechanical admission assessment** — czy lineage/source/checkpoint contracts są wystarczająco udowodnione,
3. **reconstructed metadata/exposure confidence** — EXACT/STRONG/PARTIAL/UNKNOWN według jawnych kryteriów,
4. **current v2 interpretation/evidence admissibility** — nowa decyzja obowiązująca od protocol upgrade.

Nowa interpretacja ma własną identity/revision i nie nadpisuje legacy bytes.

## 72.2. Legacy admission

Mechanical levels (L0–L5 lub docelowy równoważny profil) muszą mieć normatywne, kumulatywne kryteria w Migration/Data Contracts. Canonical predecessor wymaga najwyższego uzgodnionego poziomu mechanicznego; auxiliary/hypothesis inputs mogą mieć słabsze admission zgodnie z policy.

UNKNOWN pozaprotokołowe exposure nie musi automatycznie blokować **mechanicznej kontynuacji lineage**, ale blokuje nieudowodniony historyczny blind-origin claim. Nowe E3 może być ENFORCED blind tylko na podstawie własnego, bieżącego isolation profile.

Nie wolno wymyślać, że historyczne E0/Surface/Coverage v2 zostały wykonane. Bootstrap tworzy je **teraz** jako current v2 foundation i zapisuje jawny protocol/policy upgrade.

## 72.3. Compatibility ma dwa gates

```text
LEGACY_BEHAVIOR_PRESERVATION
≠
VALIDATOR_CORRECTNESS / SAFE EXPECTATION
```

Fixture ma przechowywać legacy observed/expected behavior oraz niezależnie kwalifikowane safe outcome. Znana legacy luka może prowadzić do jawnego hardening exception; nie może zostać wymuszona w v2 przez differential equality.

## 72.4. Cases A/B/C

Migration contract musi dawać jednoznaczny wynik przynajmniej dla:

- **A:** pełny, jednoznaczny legacy E2 → canonical admission do v2 E3,
- **B:** mechanicznie poprawny E2 z nieznanym exposure → lineage admitted, history blind-origin ograniczony,
- **C:** brak/niejednoznaczny artifact wymagany do canonical admission → bootstrap canonical predecessor BLOCKED, choć raw archive można zachować.

To pozwala rozwijać BDB bez fałszowania provenance wcześniejszych etapów.

---

# 73. Finalna rekomendacja

BDB Audit vNext powinien być programem assurance badającym jednocześnie software i wiarygodność własnego procesu audytowego.

Największy wzrost jakości daje połączenie:

1. **jednej canonical accepted history i immutable revisions**,  
2. **jawnego trust/policy/source binding**,  
3. **Surface Inventory z unknown/unsupported scope**,  
4. **Invariant Registry + first-class Coverage Obligations**,  
5. **wielu ortogonalnych discovery lanes z kwalifikowanym isolation**,  
6. **first-class Discovery Events i controlled reveal views**,  
7. **claim-relative evidence independence i transitive invalidation**,  
8. **E2 adjudication przed root-cause merge**,  
9. **E3 negative-space hunt**,  
10. **E4 model-based depth z implementation-fidelity bridge**,  
11. **E5 adversarial/mutation work z kontrastowym oracle testing**,  
12. **acyklicznego Candidate Case → dual challengers → E5 StageCompletion → STOP → Conclusion**,  
13. **STOP traktującego niewiedzę jako niewiedzę, nie brak findingu**,  
14. **adaptacyjnego E6, które rozszerza pracę bez osłabiania obowiązków**.

Pięć głównych etapów pozostaje stałym szkieletem. E6 jest mechanizmem targeted continuation, a nie kolejnym obowiązkowym etapem. Szczegóły implementacyjne storage, runnera izolacyjnego, platform matrix czy calibration thresholds są kwalifikowane per profile i nie mogą zmieniać powyższych foundation semantics.

Ten dokument po rewizji C01–C21 stanowi metodologiczny baseline do propagacji w pozostałych specyfikacjach. Pełny baseline może zostać zamrożony dopiero po spójnym zaktualizowaniu wszystkich ośmiu dokumentów i niezależnym consistency/design review nowego corpus.

---



## R5.3 authority hardening note

Final author qualification binds coverage assurance directly to canonical Coverage Obligation revisions/qualification refs rather than derived summaries; STOP binds exact invalidation facts; a CommitBody accepts its CommandEnvelope in the same closure, while ordinary post-genesis commands may target only a prior accepted campaign. These are foundation invariants, not implementation preferences.

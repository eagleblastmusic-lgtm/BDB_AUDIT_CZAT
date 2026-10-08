# NF02 — aktualny stan i plan napraw

Data weryfikacji: 2026-10-02. Dyspozycja: **REMEDIATION_REQUIRED**.

## A. Wynik sprawdzenia poprzedniego planu

**Nie wszystkie wymagania poprzedniego zadania zostały wykonane. NF02 nie jest zamknięte.** Czat „Zweryfikuj NF02 i zaplanuj poprawki” zakończył się błędami systemowymi bez wymaganego raportu `NF02_CURRENT_STATE_AND_REMEDIATION_PLAN.md`. Jego `suites.log` zawiera błędy `tmp_path`/`PermissionError`; `suites_fixed.log` był pusty. Nie stanowią dowodu przejścia testów.

Obecna weryfikacja uzupełnia brakujący raport i wykonuje świeże testy na rzeczywistych niezacommitowanych poprawkach. Nie zmienia produkcyjnego kodu ani wcześniejszych raportów. Użytkownik doprecyzował zadanie jako sprawdzenie wykonania poprzedniego planu; wcześniejsze zadanie było audytem i planowaniem, bez implementacji.

| Wymaganie | Stan po tej weryfikacji |
|---|---|
| Tożsamość źródła, HEAD/tree/status i relacja do poprzedniego audytu | Wykonane; konieczne rozróżnienie dwóch checkoutów i HEAD od dirty worktree |
| Rekonstrukcja przepływu authority | Wykonana dla NF02 i jego aktualnych zmian |
| Sprawdzenie czterech wcześniejszych findings | Wykonane w opisanym niżej zakresie; żaden pełny verdict CLOSED nie jest uzasadniony |
| Równoważne ścieżki i kontrprzykłady | Potwierdzono publiczne wystawianie ticketu, rozbieżność raw/proposal, fałszywy package hash, późną utratę raw i regresję resume |
| Świeże suites NF02 i zależności | Wyniki w sekcji H i dołączonym rekordzie dowodowym |
| Pełna macierz ZIP/context/restart/concurrency | Nieukończona; pozostałe warianty jawnie wymieniono w sekcji I |
| Pełna kwalifikacja repo/build/standalone/exact-SHA | Nie wykonana; nie zgłoszono PASS |
| Raport z root causes, uporządkowanym planem i acceptance criteria | Uzupełniony tym dokumentem |
| Usunięcie nowych tymczasowych prób i zachowanie zastanych materiałów | Wynik kontroli końcowej w rekordzie dowodowym |

## B. Audytowane źródło

- Repozytorium zgodne z granicą `AGENTS.md`: `eagleblastmusic-lgtm/bdb-audit`, `C:\Projekty\Audyty\BDB Audit`.
- Branch poddany odczytowi/weryfikacji: `fix/nf02-lane-result-authority`.
- HEAD: `b7051472909075bb4c83a9a510e298fcca2a6bd5`.
- Committed tree: `3bc05685293d2fade72735e43a2ccc96be26f3f7`, zgodny z poprzednio audytowanym merge `a106bedca02d310bfb30d84d6ce65e5581f65ef5`.
- Comparison base: `f9cbd0f79e9814b97d4b1baa415fb02de602e27f`.
- **Testy tego raportu obejmują dirty worktree, a nie samo committed tree.** Zastane zmiany obejmują osiem plików: `history/authority_hooks.py`, `history/store.py`, `schemas/orchestration.py`, `workflow/inbox.py`, `workflow/manual_stage.py`, `workflow/package_resume.py`, `workflow/packaging.py` oraz `tests/workflow/test_nf02_synthetic_lane_result_authority.py` w odpowiednich katalogach `src/bdb_audit`/`tests`.
- Początkowy lokalny `main`: `dcd8bd6ef5f7e3f7b5803ade6843c6217f16f044`; nie zmieniano branchy/refów.
- Osobny checkout `C:\Projekty\Audyty\BDB_AUDIT_CZAT` ma remote `eagleblastmusic-lgtm/BDB_AUDIT_CZAT`, branch `fix/astra-remediation-candidate`, HEAD `33f6f06b35c2e041ad5ac90faf7fc07edb0dc5e6`. Nie zawiera aktualnych lokalnych poprawek NF02 ani dedykowanego testu. Nie należy przypisywać mu wyników z drugiego checkoutu.

Przed testami zapisano SHA-256 503 zastanych plików tracked oraz dokumentów NF02. Dowody wiążą dokładne bajty dirty worktree; HEAD sam nie identyfikuje badanego kodu.

Normatywne źródła pobrano lokalnie z `C:\Projekty\Audyty\BDB Audit - Context`. Dziesięć pozycji `normative_candidate_files` zgadza się bajtami, długością i SHA-256 z `BDB_AUDIT_V2_R5_3_1_MANIFEST_SHA256.json`. Przeczytano relewantne wymagania Data Contracts §§14.6, 15, 184–187 oraz Architecture §§41–45. Kontrola hashy pozostałych dokumentów nie oznacza pełnego audytu ich treści.

## C. Faktyczny model authority

```text
accepted assignment / attempt / source / input cut
    -> prepared package ZIP + cached semantic digest + cached raw SHA-256
    -> executor-authored result ZIP
    -> RawArtifactVault: raw ZIP oraz jego members
    -> Inbox: ZIP/JSON, context, findings, live package SHA-256
    -> caller-created canonical proposal + caller-created proposal digest
    -> public Store.issue_batch_ticket(campaign, stage, cut)
    -> public Store.issue_ingestion_capability(evidence, ticket)
    -> Coordinator.accept / Store.accept(INGEST_EXTERNAL_LANE_RESULT)
    -> schema checks + prior refs + raw read + manifest fields + HMAC
    -> accepted admission evidence
    -> Store.accept(RECORD_FOUNDATION_FACT)
    -> evidence/proposal digest equality + second raw read
    -> accepted bdb_audit_lane_result
    -> accepted LaneCompletion
    -> Inbox aggregate finalization -> StageCompletion
```

Zastane poprawki wprowadziły prywatny klucz i HMAC, ale obydwa interfejsy wystawiające uprawnienia pozostają publiczne. Ticket issuer sprawdza tylko istnienie `accepted_head_hash` w tabeli commits. Nie ustanawia oddzielnej autoryzacji zaufanego producenta i nie sprawdza całego tuple campaign/seq/hash/policy/spec. Następny issuer sprawdza wybrane manifest fields, references i raw ZIP, lecz podpisuje także przekazany przez callera `result_proposal_digest` oraz `package_zip_sha256` bez niezależnego odtworzenia tych wartości.

HMAC skutecznie blokuje dowolny losowy podpis i mutację już podpisanego payloadu. Nie blokuje uzyskania nowego podpisu poprzez dostępny issuer. Reguła Data Contracts §15.1, że deklarowany actor nie ustanawia własnej authority, pozostaje relewantna. Zakres kontrprzykładu to lokalny caller publicznego API, zgodnie z wcześniejszym zadaniem; nie wykazano zdalnego dostępu do tego API.

## D. Entry points i egzekwowane granice

| Punkt | Faktyczny wynik |
|---|---|
| `Coordinator.accept` | Deleguje do Store; nie ustanawia odrębnej tożsamości producenta |
| `TransactionalHistoryStore.accept` | Centralna transakcja, schema/ref/CAS/closure/FSM checks; obie akceptacje NF02 dochodzą do authority hooks |
| `issue_batch_ticket` | Publiczny issuer; odrzuca nieistniejący hash, akceptuje obce campaign/stage i niespójne seq przy istniejącym hash |
| `issue_ingestion_capability` | Wymaga ticketu, lecz caller może go uzyskać powyżej; nie odtwarza proposal ani exact package SHA |
| `E1ResultInbox` | Live package hash, ZIP/context checks, dwie akceptacje, completion; exact retry pokryty suite |
| `StageResultInbox` | Analogiczny import faz E2+; przygotowana partia ma ticket, odtworzona partia go traci |
| `load_e1_batch` | Wystawia ticket przy odtworzeniu E1 |
| `load_stage_phase_batch` | Odtwarza `StageBatch` bez ticketu; valid result po resume jest odrzucany |
| Replay/idempotency/CAS/recovery | Generyczne ścieżki nadal korzystają ze Store; wybrane suites wykonane, pełna macierz NF02 nie jest zamknięta |
| Export/share/snapshot/read models | Nie znaleziono równoległego writera omijającego Store w prześledzonym NF02 flow; pełnego audytu wszystkich formatów import/restore nie wykonano |
| Registry/SchemaBindings | Sprawdzają lokalnie wygenerowane exact bytes/digest, lecz nie wykazano wymaganego history/governance pin dla obu rozszerzeń NF02 |

## E. Cztery wcześniejsze findings

| ID | Aktualny status | Świeże ustalenie | Wpływ / severity |
|---|---|---|---|
| NF02-001 | **PARTIALLY_FIXED; defect CONFIRMED** | Losowe/no-ticket capability jest blokowane, lecz nowy ticket z publicznego issuer pozwala samodzielnie wystawić i zaakceptować evidence; zwykły Inbox następnie kończy wszystkie 5 lanes i E1 | Canonical evidence/result/LaneCompletion/StageCompletion; **BLOCKER** |
| NF02-002 | **PARTIALLY_FIXED** | Bezpośrednia podmiana live package ZIP jest wykrywana w testach E1/manual E2. Dolny publiczny issuer nadal podpisuje fikcyjny `package_zip_sha256` i taki evidence/result są akceptowane | Live Inbox wariant naprawiony, exact package binding w Store niezamknięty; **HIGH** |
| NF02-003 | **PARTIALLY_FIXED** | Usunięcie raw między evidence a result jest blokowane. Deterministyczne usunięcie po ostatniej walidacji, przed durability, nadal kończy się accepted result bez raw blobu | Re-read działa, atomic retention nie wykazane; **MEDIUM**, lokalny filesystem writer jako precondition |
| NF02-004 | **PARTIALLY_CONFIRMED; qualification OPEN** | Brak/wrong digest w lokalnym `SchemaBindings` fail closed. Oba kinds nadal pochodzą z hard-coded extension rows i runtime-generated schemas; pinned Registry nie zawiera tych rows, a odpowiednia history/pin ścieżka nie została wykazana | Runtime validation nie dowodzi governance legality; **MEDIUM**. Zmiana frozen baseline nie jest upoważniona |

Nie uznano wszystkich runtime-generated schemas za z definicji nielegalne. Wymóg accepted/pinned SchemaRegistry dopuszcza dwa sposoby ustanowienia authority; lokalne policzenie digestu nie wystarcza do wykazania któregoś z nich. Przed zamknięciem NF02-004 należy wskazać i zweryfikować exact authoritative pin/activation. Jeśli wymaga nowego semantic contract poza frozen Registry, potrzebna jest oddzielnie zatwierdzona revision: **SPEC_CHANGE_REQUIRED**. Nie edytowano frozen źródeł.

## F. Dodatkowe ustalenia

### NF02-C01 — Zmieniona propozycja nie musi wynikać z raw manifestu

**HIGH, CONFIRMED, IMPLEMENTATION_BUG / ARCHITECTURAL_GAP.** Publiczny issuer podpisuje evidence z digestem propozycji, której `findings[0].statement` różni się od raw `MANIFEST.json`. Evidence i result zostały przyjęte. Root cause: sprawdzanie zgodności wybranych manifest fields, następnie podpisanie caller-selected digestu zamiast canonical proposal odtworzonej przez trusted parser. To dodatkowy kontrprzykład podstawowego NF02-001, nie niezależna suma severity.

### NF02-C02 — Import prawidłowego wyniku po resume E2 jest blokowany

**HIGH, CONFIRMED, IMPLEMENTATION_BUG / TEST_GAP.** `workflow/stage_resume.py:load_stage_phase_batch` tworzy `StageBatch` bez `batch_ticket`. Jego domyślna wartość to `""`; `StageResultInbox` przekazuje ją do `issue_ingestion_capability`, która zwraca `UNAUTHORIZED_PRODUCER_AUTHORITY`. Probe utworzył prawidłową E2-BLIND, odtworzył ją z pakietów/accepted history, ponownie otworzył Store i otrzymał rejection prawidłowego ZIP. Accepted head/object/commit/receipt counts nie zmieniły się. E2 wykonano mechanicznie; wspólna ścieżka resume E3+ wymaga osobnych kontroli po poprawce.

### NF02-C03 — Ticket issuer nie wiąże całego HistoryCut

**MEDIUM, CONFIRMED, IMPLEMENTATION_BUG.** Issuer wystawił ticket dla obcego campaign, stage `E99` oraz `accepted_head_seq=999999`, gdy sam hash wskazywał istniejący commit. Ta próba sama nie zmieniła canonical state i nie dowodzi akceptacji obcego result. Wykazuje brak wymaganej walidacji na wejściu issuer; jest zależnością NF02-001.

### NF02-C04 — Regresja lint i rozwiązywania adnotacji

**LOW, CONFIRMED, IMPLEMENTATION_BUG.** `history/store.py` używa `Any` bez importu w dwóch metodach i ponownie importuje nieużyte `hmac`. Ruff zwraca F821 ×2 i F811 ×1. `typing.get_type_hints(TransactionalHistoryStore.issue_batch_ticket)` zwraca `NameError: name 'Any' is not defined` na CPython 3.14.4. Test na Python 3.12/3.13 nie był wykonywany; ryzyko eager annotation evaluation na tych wspieranych wersjach jest wnioskiem z kodu, nie świeżym wynikiem testu.

## G. Co istniejące testy rzeczywiście dowodzą

28 testów NF02 potwierdza wiele rejection paths, live package drift, usunięcie raw między dwiema akceptacjami, HMAC replay/mutation, lokalne schema bytes/digest checks oraz positive controls. Nie dowodzi zamknięcia authority issue:

- Test bez ticketu/ze sfałszowanym ticketem nie próbuje najpierw wywołać publicznego `issue_batch_ticket` z prawidłowym accepted cut.
- Test mutacji findings po podpisaniu nie próbuje uzyskać nowego podpisu dla zmienionej propozycji.
- Test wrong package claim nie sprawdza podpisania spójnej propozycji z fikcyjnym exact package ZIP hash przez issuer.
- T10 ma sekwencyjny exact retry/conflicting result/stale-head test. Nazwa „concurrent” nie jest dowodem dwóch konkurujących NF02 writers.
- Test raw deletion pomiędzy akceptacjami nie obejmuje interval po ostatnim raw read.
- Brak testu accepted import po odtworzeniu `StageBatch`.
- T5–T7 sprawdzają `SchemaBindings`; nie ustanawiają accepted/pinned activation dla nowych kinds.
- Helper atomowości porównuje head oraz counts commits/objects/receipts. Nie zapisuje osobno wszystkich wymaganych per-kind completion counts.

## H. Świeże dowody i polecenia

Środowisko: Windows 10 build 19045, CPython **3.14.4**, pytest **8.4.2**, Ruff **0.16.8**. Runtime schema dependency identity: jsonschema 4.25.1, attrs 26.1.0, referencing 0.37.0, jsonschema-specifications 2025.9.1, rpds-py 2026.6.3. Mypy **2.3.1** użyto z `.venv-f2/Scripts/python.exe` (również CPython 3.14.4).

Na tym hoście standardowe pytest temp directories mają błąd dostępu. Użyto tymczasowego pluginu `plancheck_tmp`, zastępującego wyłącznie `tmp_path`/`tmp_path_factory` zwykłymi unikalnymi katalogami w nowym scratch. `-p no:tmpdir` wyłącza niedziałający plugin tempdir; nie wyłącza żadnych testów ani walidatorów aplikacji. Nie zmieniano zastanego `._nf02_current_audit`.

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH='src;.;._nf02_plan_check_20261002'
python -m pytest -p no:tmpdir -p plancheck_tmp -q --tb=short tests/workflow/test_nf02_synthetic_lane_result_authority.py
```

**28 passed, 0 failed, 0 skipped, 0 reported warnings, 109.05 s.** Wynik dotyczy dirty worktree.

```powershell
python -m pytest -p no:tmpdir -p plancheck_tmp -q --tb=short tests/workflow/test_inbox.py tests/workflow/test_manual_stage.py tests/workflow/test_stage_finalize.py tests/workflow/test_review_blockers.py tests/stage3/test_ru03_result_roundtrip.py tests/stage3/test_ru03_authority_bindings.py tests/f2/test_m5_transaction.py tests/f2/test_m5_objects.py tests/f2/test_history_process_faults.py tests/f2/test_registry_schema.py tests/f7/test_f04_f05_direct_store_admission.py
```

Wynik affected suites: **152 passed, 1 failed, 0 skipped, 1 warning, 1616.33 s (26:56), exit 1**. Jedyny failure: `test_review_blockers.py::test_github_resolver_never_uses_cwd_fallback`. Systemowy `tempfile.TemporaryDirectory` powoduje `PermissionError` przy tworzeniu/cleanup tymczasowego bare repo. To blokada środowiska tego testu; nie potwierdzono regresji resolvera. Warning dotyczy celowo zduplikowanego member `report.txt` w teście rejection.

Najsilniejszy lokalny substytut: ponowiono **wyłącznie ten test**, z dodatkowym tymczasowym pluginem zastępującym jego `TemporaryDirectory` zwykłym katalogiem pod nowym scratch. Resolver, rzeczywiste Git commands oraz expected assertions pozostały bez zmian.

```powershell
python -m pytest -p no:tmpdir -p plancheck_tmp -p plancheck_source_tmp -q --tb=short tests/workflow/test_review_blockers.py::test_github_resolver_never_uses_cwd_fallback
```

**1 passed, 0 failed/skipped/reported warnings, 2.84 s, exit 0.** Ten substytut potwierdza fail-closed/no-CWD-fallback w dostępnych lokalnych warunkach; nie kwalifikuje realnego fetch poprawnego remote repository. Pierwotny run nadal ma exit 1 — nie zamieniono go narracyjnie w PASS i nie powtórzono pozostałych 152 zaliczonych tests.

```powershell
python -m pytest -p no:tmpdir -p plancheck_tmp -q -s --tb=short ._nf02_plan_check_20261002/test_plancheck_probes.py
```

Wynik końcowych sześciu tymczasowych probes: **6 passed, 0 failed, 0 skipped, 0 reported warnings, 66.82 s**. W tych próbach „passed” oznacza odtworzenie defektu, a nie przejście product acceptance gate. Wstępne nieudane wersje probe stage miały błędy samej próby: niepełny member evidence manifest oraz pominięcie aggregate finalization. Poprawiono wyłącznie tymczasową próbę; ostateczna próba stage odtworzyła StageCompletion (osobno 1 passed, 22.98 s; następnie część końcowego sześciotestowego runu). Produkcyjnego kodu nie zmieniono.

```powershell
python -m ruff check src build --output-format concise
.venv-f2/Scripts/python.exe -m mypy --config-file pyproject.toml
git diff --check
```

- Ruff: **FAIL, 3 errors** — `store.py:63` F811; `store.py:122` i `:136` F821.
- Mypy: **PASS, 48 source files**. Konfiguracja nie obejmuje bezpośrednio całego `history/store.py`; ten PASS nie obala Ruff ani `get_type_hints` failure.
- `git diff --check`: **FAIL** — zastany pusty wiersz EOF w `tests/workflow/test_nf02_synthetic_lane_result_authority.py:1431`.
- Normative manifest identities: **10/10 MATCH**; nie stanowi to product qualification.

Dokładne outputy, commands, źródło tymczasowych probes i raw source pins zostają w `docs/NF02_CURRENT_VERIFICATION_2026_10_02.json`. Tymczasowe wykonywalne probes oraz nowy scratch są usuwane przy closeout.

## I. Pozostała niepewność

Nie wykonano pełnego repo pytest, qualification verifiers F0–F8, standalone build/validator/self-test/clean-room rebuild, remote exact-SHA CI ani post-commit checks (nie utworzono commitu). Nie można użyć historycznego CI do kwalifikowania tych dirty zmian. Host i tool versions różnią się od exact CI profile (CPython 3.14.7/pytest 9.1.1/Ruff 0.16.7).

Pełna dedicated NF02 macierz cross-stage/attempt/source/model/campaign/knowledge/isolation/HistoryCut, rzeczywiste dwa konkurujące NF02 results, ambiguous ACK w obu akceptacjach oraz wszystkie trzy restart intervals pozostają niezamknięte. Generyczne Store fault/CAS tests nie zastępują dedykowanego NF02 qualification. Nie zbadano każdego offline restore/migration/import formatu.

Nie wykonano całej wymaganej macierzy ZIP (case/Unicode confusables, concatenation/trailing, malformed/overlapping central records, quotas/bombs, każda relacja manifest/member). Prześledzono shared ZIP safety i istniejące zależne testy; brak osobnych probes tych wszystkich wariantów jest jawną luką testową, nie potwierdzonym defektem dla każdej pozycji.

## J. Zalecana architektura remediation

**Kierunek rekomendowany:** Store/Coordinator odtwarza admission z owned verified raw bytes i exact prior accepted assignment/package authority. Caller nie dostarcza authority-bearing proposal digestu do podpisania. Reuse istniejących parserów/validators zamiast drugiej implementacji normalizacji. Musi istnieć jedna autorytatywna immutable definicja przypisanej paczki; bieżący cached `job` i live file nie mogą zostać drugim trust root.

| Opcja | Zalety | Ryzyka / warunki |
|---|---|---|
| A — trusted boundary sam wyprowadza proposal i admission | Usuwa caller-selected digest oraz potrzebę publicznego signing oracle; łatwiejszy audit | Trzeba ponownie użyć istniejących parserów E1/manual oraz jawnie zachować wszystkie normalizacje i prior-cut guards |
| B — capability dla rzeczywiście odrębnego trusted producer | Może zachować istniejący HMAC mechanizm | Zamknięty issuer musi mieć niezależną authorization/identity; sam prefix `_`, publiczny ticket, command kind czy imported Python object nie wystarczają. Nadal trzeba independently derive bytes/package/proposal |
| C — odrębny autoryzowany proces/service | Daje mocniejszy boundary dla lokalnego untrusted callera | Duży zakres oraz koszty IPC, recovery i qualification; nie jest najmniejszą uzasadnioną zmianą |

Frozen normative Registry/baseline nie wolno zmienić w tej naprawie. Exact schema pin/activation i extension authority należy najpierw ustanowić dopuszczonym mechanismem albo otrzymać nową normative revision. To oddzielny blocker kwalifikacji.

## K. Uporządkowany plan implementacji

| ID / priority | depends_on | Cel i minimalne pliki | Acceptance criteria / required failure paths | Blast radius |
|---|---|---|---|---|
| R0 / P0 | — | Rozstrzygnąć dokładny schema/extension authority dla NF02; wskazać dozwolony immutable pin, activation, compatibility. `core/registry.py`, `schemas/foundation.py`, `history/store.py`; normative corpus read-only | Oba kinds przed pierwszą acceptance mają exact authorized bytes/digest/ref contract. Brak/wrong/stale pin blokuje. Jeśli legalnego mechanizmu nie ma: SPEC_CHANGE_REQUIRED, bez baseline patch | HIGH |
| R1 / P0 | R0 dla wire changes | Usunąć nieautoryzowany public issuer; trusted boundary wyprowadza proposal z raw i assignment. `history/store.py`, `history/authority_hooks.py`, istniejące Inbox parsers | Public/general caller nie może wystawić admission przez legalną nazwę commandu, fresh ticket, mixed cut ani nowy podpis. Well-formed negatives zachowują head oraz wszystkie counters; legitimate E1/manual positive controls nadal kończą pracę | HIGH |
| R2 / P0 | R1 | Exact assigned package closure przy producer i consumer boundary; `workflow/packaging.py`, `package_resume.py`, `manual_stage.py`, `stage_resume.py`, Inbox oraz authority hook | Fake raw package hash, changed semantic package, changed cached job, deleted/replaced package i cross-assignment package są odrzucane; restart weryfikuje tę samą immutable authority | HIGH |
| R3 / P1 | R1, R2 | Durable raw retention/consumption integrity; `vault/raw_store.py`, Store i hook. Wybrać qualified durability/locking model zamiast kolejnego read jako obietnicy atomic retention | Raw deletion/mutation przed evidence, między akceptacjami i po final read nie daje accepted result bez jego mandatory raw closure; corruption po restart daje typed block. Jawnie określić host TCB limits | HIGH |
| R4 / P1 | R1 | Naprawić manual phase resume korzystając z finalnego mechanismu R1; `workflow/stage_resume.py` i transport tests | E2 i co najmniej reprezentatywne E3/E4 importują valid result po nowym Store/restart; stale/foreign/tampered packages odrzucane atomowo. Nie utrwalać public signing-oracle architecture samym dodaniem ticketu | MEDIUM |
| R5 / P2 | — | Poprawić brak importu `Any`, redundantny `hmac`, EOF; `history/store.py`, dedicated test file | Ruff PASS, `get_type_hints` działa, dotychczasowe zmiany zachowane; test importu na rzeczywiście wspieranych runtimes przy qualification | LOW |
| R6 / P0 gate | R0–R5 | Dodać trwałe testy brakujących właściwości, dedicated failure/recovery/concurrency matrix | Reprodukcje tego raportu stają się negative regressions; positive real import/finalization, exact retry, changed-body ID reuse, concurrent CAS i ambiguous ACK sprawdzone osobno | HIGH |
| R7 / final gate | R6 | Niezależna rekwalifikacja actual candidate i final closure report | Affected + cross-cutting/pełny suite, Ruff/Mypy, wymagane phase/verifiers, actual build/validator/standalone/clean-room, source/dependency/schema/fixture pins i końcowy drift check; exact committed post-commit evidence, gdy governing gate tego wymaga | HIGH |

Nie stosować silent backward reinterpretation ani blanket migration istniejących signed records. Stare accepted revisions zachowują bajty; ich applicability/requalification trzeba ocenić jawnie. Poprawka zmienia producer authority i schemas, więc unieważnia zależne evidence zgodnie z `AGENTS.md`. Rollback nie może ponownie autoryzować niezweryfikowanego starego wyniku; usunięcie lookupu/latest-head shortcuts nie może osłabić fail-closed.

## L. Wymagana macierz testów po naprawie

1. Authorized vs caller-selected producer: valid malformed oraz well-formed nieautoryzowane requests; fresh issuer, forged/replayed capability, same-commit authorization, changed proposal przed i po podpisaniu.
2. Exact context: campaign/stage/phase/lane/slot/attempt/assignment/source/model/profile/full HistoryCut/knowledge/isolation; oddzielne permutations i legal positive controls.
3. Bytes: assignment-time semantic/raw package, live replacement, cached metadata replacement, result manifest vs canonical proposal, evidence-file membership/digest/length.
4. Atomicity: accepted head oraz counts commits, receipts, immutable objects, lane results, LaneCompletion, StageCompletion dla każdej rejection.
5. Recovery: assignment→result, evidence→result, result→completion; E1 i manual stages; raw deletion/corruption we wszystkich materialnych intervals; valid resume i exact retry.
6. Command protocol: same ID/same body, same ID/changed body, current/stale head, concurrent competing evidence/results, durable commit z ambiguous ACK.
7. Registry: authorized absent/wrong/stale binding i extension collisions; exact bytes/digest/ref closure przed first acceptance; brak silent history reinterpretation.
8. Transport: pełna ZIP/JSON matrix wymieniona w sekcji I, quotas i dokładne typed outcomes; bez obchodzenia resource validation.
9. Downstream: result→LaneCompletion→StageCompletion, canonical cut/finalization/STOP i brak stale acceptance laundering.
10. Candidate qualification: wszystkie wymagane lokalne i exact-SHA gates; pojedynczy suite PASS nie oznacza closure.

## M. Końcowa ocena

**REMEDIATION_REQUIRED. NF02 closure gate: FAIL.** Publiczne issuer API oraz niezależnie zaakceptowana treść niepochodząca z raw są potwierdzonymi problemami. Live file hash i raw re-read są użytecznymi częściowymi poprawkami. Resume manual stages ma potwierdzoną regresję. R5.3 schema governance pozostaje otwartym warunkiem odbioru i może wymagać oddzielnej zatwierdzonej revision.

Nowy raport i rekord dowodowy są rezultatem obecnego zadania weryfikacyjnego. Nie należy przypisywać temu zadaniu naprawy produkcyjnego NF02, pełnego wykonania całej wcześniejszej macierzy ani kwalifikacji dirty source jako release candidate.

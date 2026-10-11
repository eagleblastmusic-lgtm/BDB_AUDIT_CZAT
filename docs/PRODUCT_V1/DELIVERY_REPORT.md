# BDB Audit PRODUCT-V1 — raport dostarczenia

2026-10-11. Status: **PRODUCT-V1_LIMITED_DELIVERED** — działające przygotowanie kampanii, lokalne kontrole, wznowienie i raport częściowy. Zewnętrzne przyjmowanie wyników: **BLOCKED**. NF02: **OPEN**. Pełny audyt E1–E6: **NOT_COMPLETED**. Nie nadano nowego PASS Q1/Q2 ani N5–N11.

## Tożsamość i zachowanie wejścia

- Repo/worktree: `C:\Projekty\Audyty\BDB Audit`.
- Gałąź: `product/bdb-audit-user-v1`.
- Commit implementacji, testów i kontrolowanego czyszczenia: **`c7797f751dfd1d621895caef2b6a7d2a0d55eda6`**. Kolejny lokalny commit zawiera wyłącznie ten raport i końcowy zapis inspekcji; nie zmienia testowanego kodu.
- Niezmieniony snapshot wejściowy: [`f23dbedccb6dca9d23f41830e282e814e550bca1`](https://github.com/eagleblastmusic-lgtm/BDB_AUDIT_CZAT/commit/f23dbedccb6dca9d23f41830e282e814e550bca1), gałąź `review/r5-4-2-current-snapshot`, remote `czat`. Potwierdzony `git ls-remote --heads czat review/r5-4-2-current-snapshot`.
- `main` zachowany na `dcd8bd6ef5f7e3f7b5803ade6843c6217f16f044`; brak merge/push/release, zmian PR #45, rebase, force-update i czyszczenia historii.
- Zastane untracked zachowane: osiem plików objętych ponowną kontrolą SHA256 oraz nietknięte katalogi NF02. Ich 119 tysięcy plików nie jest ponownie kwalifikowanych ani usuwanych. `ORIGINAL_WIP_PRESERVATION.json` rozróżnia exact file hashes od zachowania przestrzeni katalogów.

## Co działa dzisiaj

CLI `product preflight/start/status/resume/import/report` wykorzystuje istniejący orchestrator, source resolver, accepted history, E1 packaging i ReportBuilder. Preflight obsługuje lokalne repo oraz rzeczywisty GitHub ref. Start zamraża exact commit/tree i przygotowuje pięć paczek z assignment/attempt/cut oraz raw ZIP hashes. Nie nadpisuje istniejącego store. Resume w nowym procesie weryfikuje historię i oryginalne paczki; podmiana ZIP jest BLOCKED. Eksport chroni istniejący plik przez exclusive create i jawnie pokazuje NOT_COMPLETED.

TUI uruchamia się i pokazuje ograniczenie NF02. Istniejący runner wykonuje lokalne dokładne komendy, zachowuje stdout/stderr/receipt i jawnie pokazuje brak izolacji hosta/sieci. Wymaganie ENFORCED blokuje wykonanie. Naprawiono katalog tymczasowy Windows, pominięto metadane Git przy kopiowaniu źródła zgodnie z source_manifest i zapewniono UTF-8 także przy `python -I`.

Przyjęcie `bdb_audit_lane_result`/`lane_result_admission_evidence` jest wyłączone w centralnym Store, issuerze capability i obu produkcyjnych inboxach. Wynik jest odrzucany przed raw retention/transaction/completion. Caller, actor, ticket, self-grant i deklaracja izolacji nie odblokowują profilu. To ograniczenie produktu, **nie dowód naprawy ani kwalifikacji NF02**. Nie tworzono alternatywnej authority ani sztucznego wyniku AI.

## Rzeczywista demonstracja

`SMOKE_EVIDENCE.json` i `DEMO_AUDIT_REPORT.md` dokumentują rzeczywiste procesy standalone `-I` na utworzonym niewrażliwym repo Git:

- Exact target commit: `e6b1154bc1707c4230eca481c4904ded9c08130a`.
- Kampania: `campaign_4e0926d847dc7a55`.
- Pięć autentycznych paczek E1; kontrola dodawania `SUCCESS`; test jawnie zasianego błędu clamp `TARGET_NONZERO` z rzeczywistym stderr i niezerowym exit code.
- Nowy proces odtworzył kampanię/paczki. Odrzucenie importu i restart nie zmieniły bytes/history/dowodów kampanii.
- Raport częściowy zawiera dwa lokalne receipts oraz accepted cut. Ich integralność nie jest autoryzacją zewnętrznego audytora ani automatycznym związaniem kontroli z kampanią.

Największy legalny fragment zakończono eksportem częściowym. Przyjęcie zewnętrznego audytu zatrzymuje się na niezależnej authority instalacji/producenta i wymaganej kwalifikowanej aktywacji. Nie symulowano E2–E6 ani kompletnego uprawnionego zewnętrznego wykonania.

## Weryfikacja

**421 unikalnych przypadków ma końcowy wynik PASS w zadeklarowanym zakresie**, według `VERIFICATION.json`. To macierz przypadków z właściwymi ponowieniami, nie deklaracja jednego bezbłędnego przebiegu pełnego repo.

| Dowód | Rzeczywisty wynik |
|---|---|
| Pierwsza szersza seria: product, runner, stage2, F1/F2/F3, settings/platform, build/distribution i RU09 reports | 390 PASS, 6 FAIL, 25 ERROR; oryginalny log/XML zachowany |
| Naprawiona regresja testowego helpera i cała seria product po czyszczeniu | 15 PASS; `PRODUCT_POST_CLEANUP_TEST_RESULTS.xml` |
| Powtórzenie affected TemporaryDirectory, legacy corpus, process tree oraz build/clean environment z normalnym tokenem Windows | 38 PASS; `ENVIRONMENT_RETRY_TEST_RESULTS.xml` |
| Końcowy product + runner CLI/process tree + F2 CLI po poprawce UTF-8 | 21 PASS; `FINAL_CLI_TEST_RESULTS.xml` |
| Ruff | PASS `src build tests/product tools` |
| Mypy | PASS, 51 plików według `pyproject.toml` |
| Standalone build + release validator + exact payload + deep self-test | PASS; validator scope `LOCAL_ARTIFACT_VALIDATION` |
| Standalone rzeczywisty smoke oraz start/exit TUI | PASS |
| Diff check w kodzie/config; chronione ścieżki i WIP; odzyskanie | PASS |

Początkowe błędy Windows wynikały z ACL TemporaryDirectory ograniczonego tokena oraz niemożności zakończenia child procesu przez taskkill w tym tokenie. Kontrole powtórzono z normalnymi uprawnieniami bez zmiany oczekiwań. Testowy plugin `-p no:tmpdir -p tools.product_test_tmp` zastępuje wyłącznie katalogi fixture zwykłym mkdir; nie pomija testów, kontroli ani walidatorów. Początkowy błąd umieszczenia testowego kodu inbox w złym teście naprawiono i ponowiono cały produkt. Czasy w zachowanych logach są odczytami narzędzia, nie oceną efektywnego czasu pracy.

Komendy ze źródeł, PowerShell:

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = 'src'
.\.venv-f2\Scripts\python.exe -m pytest tests/product tests/runner tests/stage2 tests/f1 tests/f2 tests/f3 tests/workflow/test_settings.py tests/workflow/test_platform.py tests/f8/test_m46_build.py tests/f8/test_m46_standalone_clean_env.py tests/f8/test_runtime_build_input_closure.py tests/f8/test_distribution_provenance.py tests/f8/test_ru09_report_builder.py tests/f8/test_ru09_remediation_bundle.py tests/f8/test_ru09_cli.py -q -p no:tmpdir -p tools.product_test_tmp
.\.venv-f2\Scripts\python.exe -m pytest tests/runner/test_ru10_cli_and_process_tree.py::test_ru10_timeout_terminates_spawned_child_process_tree tests/f1/test_legacy.py tests/f8/test_m46_build.py tests/f8/test_m46_standalone_clean_env.py -q -p no:tmpdir -p tools.product_test_tmp
.\.venv-f2\Scripts\python.exe -m pytest tests/product tests/runner/test_ru10_cli_and_process_tree.py tests/f2/test_cli.py -q -p no:tmpdir -p tools.product_test_tmp
.\.venv-f2\Scripts\python.exe -m ruff check src build tests/product tools
.\.venv-f2\Scripts\python.exe -m mypy --config-file pyproject.toml
.\.venv-f2\Scripts\python.exe -c "from pathlib import Path; from build.build_single_file import build_standalone; print(build_standalone(Path('dist/BDB_AUDIT_ASSISTANT_v2.0.3_PRODUCT_V1.py')))"
.\.venv-f2\Scripts\python.exe -m bdb_audit.release_validator_cli dist/BDB_AUDIT_ASSISTANT_v2.0.3_PRODUCT_V1.py --output docs/PRODUCT_V1/RELEASE_VALIDATOR.json
.\.venv-f2\Scripts\python.exe -I dist/BDB_AUDIT_ASSISTANT_v2.0.3_PRODUCT_V1.py --verify-payload
.\.venv-f2\Scripts\python.exe -I dist/BDB_AUDIT_ASSISTANT_v2.0.3_PRODUCT_V1.py self-test --deep
.\.venv-f2\Scripts\python.exe tools/product_smoke.py --standalone dist/BDB_AUDIT_ASSISTANT_v2.0.3_PRODUCT_V1.py
.\.venv-f2\Scripts\python.exe tools/verify_product_cleanup.py
git diff --check -- src tests build pyproject.toml .gitignore tools
```

Full R5.4.2 Q1/Q2, independent clean-room rebuild i kwalifikacja exact release SHA nie były wykonywane. Validator zachowuje wymagane `NOT_RUN` dla niezależnego clean-room i jego optional compatibility lane; rzeczywiste testy corpus i izolowanego startu wykonano osobno. Nie wyłączono obowiązkowej kontroli, aby nadać Q1 PASS.

## Build i uruchomienie

Artefakt: `dist/BDB_AUDIT_ASSISTANT_v2.0.3_PRODUCT_V1.py`, **1 503 253 bajty**, SHA256 **`094065a8fc59efe7d1bba48343f842f480f8422fd21ee29c2117b15975a80ce5`**. Lokalnie dostępny plik jest ignorowany przez Git zgodnie z istniejącą polityką dist, odtwarzalny z komendy build. Windows x64, CPython 3.14; biblioteki runtime w pakiecie, bez pip/src podczas uruchomienia. Zachowano wersję bazową 2.0.3; profil PRODUCT-V1 jest jawny, nie jest nowym kwalifikowanym release.

```powershell
Set-Location 'C:\Projekty\Audyty\BDB Audit'
py -3.14 -I '.\dist\BDB_AUDIT_ASSISTANT_v2.0.3_PRODUCT_V1.py' product --help
```

Pełna instrukcja użytkownika: **`QUICKSTART_PL.md`**. Nowe repo/commit zaczyna się od `product preflight`, następnie `product start`; istniejące od `product resume`.

## Czyszczenie i odzyskiwanie

Usunięto tylko **2752 pliki / 262 233 104 bajty (około 250 MiB)** z 10 starych wygenerowanych kopii build_time_candidate. Każdy Git blob odczytano, zweryfikowano Git ID/SHA256 i porównano z raw worktree przed git rm. Representative `git restore` odtworzył trzy pliki do osobnego katalogu/indeksu i sprawdzono SHA256. Manifest wskazuje pinned snapshot oraz `archived_in_commit` dla oryginalnego REVIEW_SNAPSHOT_MANIFEST; nie edytuje oryginalnych manifestów ani dowodów.

Zachowano cztery zestawy buildów z aktywnymi referencjami, źródła normatywne, qualifications, checkpoint_history, normative_build_candidate, golden_build_candidate i build_schema_fixtures. Pozostałe grupy pozostają KEEP/NEEDS_REVIEW; sam rozmiar lub obecność duplikatu nie daje zgody na zniszczenie dowodu. Nie obiecuje się usunięcia całych 6,73 GB.

`CLEANUP_PLAN.md`, `CLEANUP_REMOVAL_MANIFEST.json`, `CLEANUP_REFERENCE_SCAN.json`, `CLEANUP_RESULT.json` zawierają selekcję, ścieżki, hashes, bytes, brak zależności produktu i procedurę odzyskania. Dodatkowo usunięto wyłącznie własne odtwarzalne katalogi fixture tego zadania (3039 plików / 20 984 512 bajtów), zachowując logi/XML i rzeczywiste kampanie/receipts smoke. Dane zastane NF02 nie były czyszczone.

Rozmiar commited tree wejścia: 7 083 918 754 bajty. Po samych usunięciach: 6 821 685 650 bajtów, przed dodaniem niewielkiego kodu i raportów produktu. `.git` pozostaje osobnym magazynem; `CLEANUP_RESULT.json` zawiera pomiar jego plików oraz `git count-objects -v`. Bloby oryginałów pozostają w historii. Nie obiecuje się mniejszego pełnego klonu ani odzyskania tych bajtów z object store.

Odzyskanie jednego pliku w gałęzi roboczej:

```powershell
git -c core.longpaths=true restore --source=f23dbedccb6dca9d23f41830e282e814e550bca1 --worktree -- 'DOKLADNA_SCIEZKA_Z_MANIFESTU'
```

Jeśli cofnięcie ma również wejść do indeksu/nowego commitu, użyj świadomie `--staged --worktree`. Formalną ścieżkę R5.4.2 uruchamiaj z osobnego checkoutu/worktree pinned snapshotu; nie jest częścią aktywnego profilu produktu. Historyczne gzip odzyskuje `docs/R5_4_2/restore_review_evidence.py`.

## Pozostała granica

Włączenie zewnętrznych wyników wymaga niezależnego source-of-authority instalacji/producenta, pełnego NF02 P0 dla rzeczywistego entrypointu i wymaganej kwalifikowanej aktywacji. Obecny profil nie ma prawdziwego przyjętego zewnętrznego wyniku. To jawna granica funkcjonalna; wszystkie niezależne prace produktu, bezpieczne czyszczenie, testy i instrukcje zostały wykonane. Nie wymaga kolejnej wielogodzinnej analizy przed użyciem przygotowania/lokalnych kontroli.

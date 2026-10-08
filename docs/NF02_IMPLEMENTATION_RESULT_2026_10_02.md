# NF02 — wynik wykonania planu naprawy (2026-10-02)

**Częściowa naprawa. Pełny gate NF02: FAIL. Normatywny odbiór: SPEC_CONFLICT.**

Repozytorium: `eagleblastmusic-lgtm/bdb-audit`,
`C:\Projekty\Audyty\BDB Audit`, zastana gałąź
`fix/nf02-lane-result-authority`, HEAD
`b7051472909075bb4c83a9a510e298fcca2a6bd5`.
Zmiany lokalne; bez commitu, pusha, PR, tagu lub zmiany remote refs.

## Wykonane zmiany

| Plik | Zmiana tego zadania |
|---|---|
| `src/bdb_audit/workflow/result_proposal.py` | Wspólny raw-to-proposal transform, limity ZIP, metadata członków, niezależna kontrola proposal digest/member evidence oraz kontekstu rzeczywistych package bytes. |
| `src/bdb_audit/workflow/inbox.py` | E1 korzysta z tej samej normalizacji, zachowując obsługę `FINDINGS.json`, liczby findings i źródłowych bytes. |
| `src/bdb_audit/workflow/manual_stage.py` | Manual stages korzystają ze wspólnej normalizacji; sprzeczny pełny HistoryCut lub dostarczone przez zewnętrzny manifest admission authority blokują import. |
| `src/bdb_audit/history/store.py` | Import `Any`, usunięcie redundantnego `hmac`; ticket wymaga pełnego istniejącego cut/campaign/stage/assignment context; issuer weryfikuje raw-derived proposal przed podpisaniem. |
| `src/bdb_audit/history/authority_hooks.py` | Consumer ponownie weryfikuje byte provenance, także przy poprawnym HMAC, i porównuje canonical result z odtworzoną propozycją. |
| `src/bdb_audit/workflow/stage_resume.py` | Po zweryfikowaniu paczek odtwarza ticket, umożliwiając import manual result po nowym Store/Batch. |
| `tests/workflow/test_nf02_synthetic_lane_result_authority.py` | Zachowane wcześniejsze regresje; legalne signed fixtures otrzymały rzeczywiste proposal/member/package bytes; foreign ticket jest odrzucany przy issuance; poprawiony EOF. |
| `tests/workflow/test_nf02_raw_derivation.py` | 22 nowe przypadki: wybrana przez caller treść, poprawny podpis błędnej treści, member metadata, package raw/context/source, pełny cut, legalne importy i restart E2/E3/E4 oraz uszkodzone/brakujące paczki. |

Zachowano osiem zastanych zmienionych plików. Zastane zmiany w
`schemas/orchestration.py`, `workflow/package_resume.py` i `workflow/packaging.py`
nie były edytowane w tym zadaniu. Nie zmieniono frozen Registry/Golden Vectors,
normatywnego corpus, author baseline record, frozen candidate ani legacy.

Podpis nie wystarcza do wykazania zgodności canonical result z raw ZIP.
Nowa kontrola odrzuca świeżo podpisywaną, zmienioną treść, nawet jeśli caller
przeliczy jej digest. Sprawdza też rzeczywisty ZIP paczki, jego kontekst i źródło.
**Ta kontrola zgodności nie ustanawia assignment-time package authority.**

## Weryfikacja

Środowisko: Windows x64, CPython 3.14.4, pytest 8.4.2, Ruff 0.16.8;
Mypy 2.3.1 z zastanego `.venv-f2`. Brak nowych production dependencies.
Uruchomiono checks lokalnego dirty worktree, nie exact committed release.

Ze względu na ograniczenia Windows `tmp_path`/`tmp_path_factory` używają
tymczasowego pluginu z normalnymi katalogami pod task-owned scratch. Wyłącznie
test `test_github_resolver_never_uses_cwd_fallback` otrzymał również lokalny
allocator `TemporaryDirectory`; resolver, real Git i assertions pozostały
bez zmian. Pełne źródło adapterów oraz logi zachowuje rekord JSON.

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH='src;.;._nf02_implementation_20261002'
python -u -m pytest -p no:tmpdir -p nf02_tmp -q --tb=short tests/workflow/test_nf02_raw_derivation.py tests/workflow/test_nf02_synthetic_lane_result_authority.py tests/workflow/test_inbox.py tests/workflow/test_manual_stage.py tests/workflow/test_stage_finalize.py tests/workflow/test_review_blockers.py tests/stage3/test_ru03_result_roundtrip.py tests/stage3/test_ru03_authority_bindings.py tests/f2/test_m5_transaction.py tests/f2/test_m5_objects.py tests/f2/test_history_process_faults.py tests/f2/test_registry_schema.py tests/f7/test_f04_f05_direct_store_admission.py
```

Wynik końcowy affected suite: **203 passed, 0 failed/skipped, 1 warning,
2344.03 s (39:04), exit 0**. Warning dotyczy celowo zduplikowanego
`report.txt` w `test_duplicate_path_archive_rejected`.

```powershell
python -m ruff check src build --output-format concise
.venv-f2/Scripts/python.exe -m mypy --config-file pyproject.toml
git diff --check
```

Ruff: **PASS**. Mypy: **PASS, 49 source files**. Diff check: **PASS**.
Ocena annotations obu publicznych metod Store została objęta testem.
Nie wykonano importu na Python 3.12/3.13 — lokalny runtime to 3.14.4.

Zbudowano osobny, tymczasowy artefakt przez istniejące
`build.build_single_file.build_standalone(output_path=task_owned_path)`:
**PASS**, 1 489 667 bytes,
SHA256 `6df04e9258d6c3549bd17b2ae0047f3b11cb84973f59be5423ebff7cf0d0f4c7`.
Frozen/release artifact nie został nadpisany.

```powershell
python -m bdb_audit.release_validator_cli ._nf02_implementation_20261002/BDB_NF02_LOCAL_REVIEW.py --output ._nf02_implementation_20261002/release-validator.json
python ._nf02_implementation_20261002/validate_review_owned_tmp.py
python -I ._nf02_implementation_20261002/BDB_NF02_LOCAL_REVIEW.py self-test --deep
python ._nf02_implementation_20261002/standalone_checks.py
```

Standalone miał `TEMP`/`TMP` skierowane do task-owned `runtime-temp`.
Standardowy release validator: **FAIL, exit 1**, `VALIDATOR_INTERNAL_ERROR`,
Windows `[WinError 5]` przy `TemporaryDirectory` w same-environment rebuild.
Pierwotnego wyniku nie zmieniono na PASS.

Najsilniejszy lokalny substytut zmienia wyłącznie allocator tego katalogu:
**PASS, exit 0, LOCAL_ARTIFACT_VALIDATION**; 392 payload files, exact digests,
runtime closure, Registry/Golden pins, isolated self-test i
same-environment rebuild identity PASS. Compatibility corpus i independent
clean-room nadal `NOT_RUN`.

Standalone `self-test --deep`: **PASS, exit 0**. Version, payload, capabilities
i help: **PASS, exit 0**. Standalone `build --json`: wymagane **exit 1** i
`DISTRIBUTION_CAPABILITY_UNAVAILABLE` — kontrola zachowania **PASS**.

## Status otwartych warunków

| Plan | Status |
|---|---|
| R0 | **BLOCKED / SPEC_CONFLICT** — brak zatwierdzonego NF02 schema/spec activation i normative role/reference contract. |
| R1 | **PARTIAL** — usunięty caller-selected proposal/member byte mismatch; public issuer/ticket pozostają API, a pełna producer authorization zależy od R0/R2. Nie deklarujemy zamknięcia całego signing-oracle finding. |
| R2 | **PARTIAL** — real raw package hash/context/source sprawdzane; nie ma niezależnego immutable assignment-time package pin. Caller może dostarczyć spójną samodzielnie skonstruowaną paczkę; samo sprawdzenie jej hash nie rozstrzyga authority. |
| R3 | **OPEN** — filesystem raw vault i SQLite history nie mają wspólnej qualified durability domain. |
| R4 | **LOCAL PASS** — restart i exact retry E2/E3/E4 oraz rejection uszkodzonych/brakujących paczek. E3/E4 fixtures syntetycznie seedują wcześniejsze etapy; to dowód transportu, nie pełnej kwalifikacji predecessor stages. |
| R5 | **PASS** — importy, annotations, Ruff i EOF. |
| R6 | **PARTIAL** — byte/context/restart regresje; pełna dedykowana concurrent CAS, ambiguous ACK, wszystkie restart intervals oraz cały transport matrix nie zostały zamknięte. |
| R7 | **PARTIAL** — affected/local artifact checks; brak pełnego pytest, wymaganych phase verifiers F0–F8, clean-room, exact-SHA CI i post-commit qualification. |

Na aktualnym kodzie wykonano także counterexample R3:

```powershell
python -u -m pytest -p no:tmpdir -p nf02_tmp -q -s --tb=short ._nf02_implementation_20261002/test_remaining_raw_retention.py
```

**1 passed, 16.40 s, exit 0 oznacza odtworzenie defektu.** Poprawnie zweryfikowany
result nadal commitował po usunięciu raw blobu w hooku
`before_object_durability`, po ostatnim odczycie. Nie jest to test odbioru PASS.
Nie dodano kolejnego read jako pozornej obietnicy atomic retention.
Host/storage TCB i qualified storage profile wymagają jawnego rozstrzygnięcia.

Exact conflict opisuje
`docs/NF02_IMPLEMENTATION_PLAN_2026_10_02.md`: Data Contracts §6/§184 wymagają
nowego kind w exact pinned SchemaRegistry/spec revision; §187 nie dopuszcza
obecnych hardcoded ról PROVENANCE/PROPOSAL. Istniejący byte-pinned overlay
zawiera tylko residual_risk. AGENTS.md zabrania modyfikacji frozen corpus.
Następny krok wymaga zatwierdzonej rewizji kontraktów, package authority,
raw-retention/compatibility profile oraz dopiero potem R6/R7 qualification.

## Integralność i closeout

Końcowa kontrola **501 source pins: zero drift po weryfikacji**;
**10/10 normative identities unchanged**. HEAD i main bez zmian.
Porównanie z poprzednim audytem wykazało dokładnie sześć edytowanych istniejących
plików wymienionych powyżej oraz dwa nowe pliki kodu/testów. Frozen legacy oraz
pozostałe zastane zmiany bez modyfikacji. Final diff check: **PASS**.
Cleanup nowego task-owned scratch: **COMPLETE**. Przed recursive cleanup
zweryfikowano exact absolute target i jego przynależność do workspace.
Usunięto również wyłącznie pusty katalog utworzony przez nieudany validator,
używając zatwierdzonego nonrecursive delete. Zastany `._nf02_current_audit/`
pozostawiono bez zmian. Tymczasowy executable, adapters i probes usunięto;
ich źródło/komendy/logi/hash artefaktu zachowuje rekord dowodowy.
Pełne evidence: `docs/NF02_IMPLEMENTATION_VERIFICATION_2026_10_02.json`.
Historyczne raporty z deklaracją CLOSED pozostają historyczne i nie kwalifikują
tych zmian. Aplikacji nie można jeszcze uznać za w pełni zgodną i zakwalifikowaną.

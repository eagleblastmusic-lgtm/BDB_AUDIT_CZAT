# Decyzja zakresu PRODUCT-V1

2026-10-11. Gałąź `product/bdb-audit-user-v1`, baza `f23dbedccb6dca9d23f41830e282e814e550bca1`.
Zdalny `czat/review/r5-4-2-current-snapshot` zweryfikowany przez `git ls-remote`; pozostaje niezmieniony. Zastane pliki untracked pozostają zachowane. Nie stwierdzono aktywnego procesu tego repo; zastany proces Python niezwiązany z repo pozostawiono bez interwencji; brak zmian tracked przed rozpoczęciem.

Istnieją: CLI/TUI, resolver exact Git commit/tree, preflight, SQLite accepted history, pięć paczek E1, resume, kontrolowany lokalny runner, raport częściowy. Brak udowodnionej niezależnej authority producenta wyników; publiczny issuer może wystawiać własne uprawnienia. Brak kwalifikowanej aktywacji następcy R5.4.2. Nie ma podstaw do deklarowania bezpiecznej pozytywnej akceptacji zewnętrznego wyniku nawet w predecessor.

Wybrany zakres: przygotowanie kampanii/paczek i kontrola dokładnego źródła, wznowienie i inspekcja accepted evidence; rzeczywiste lokalne kontrole przez istniejący runner oraz raport częściowy. Kontrole lokalne są dowodami wykonania komend, nie przyjętym wynikiem audytora ani Q1/Q2. Runner nie wymusza izolacji hosta/sieci, dlatego żądania wymagające ENFORCED pozostają BLOCKED.

NF02: OPEN. Przyjmowanie `lane_result_admission_evidence` i `bdb_audit_lane_result` jest wyłączone przed zapisem raw i w centralnym Store, również dla bezpośredniego caller API. Żaden flag/env/actor/ticket nie odblokowuje tej funkcji. Existing accepted history pozostaje czytelna. Q1/Q2 i N5-N11 pozostają zgodne z oryginalnymi dowodami; produkt nie nadaje im PASS.

Źródło autorytetu kampanii: istniejące accepted history/bootstrap i frozen Registry R5.3/R5.4.1, bez zmiany normatywnych bajtów. Organizacyjna decyzja PRODUCT-V1 upoważnia wyłącznie do ograniczonej użyteczności i blokowania ryzyka. Aktywacja importu wymaga niezależnego kontekstu instalacji/producenta, exact raw retention oraz complete NF02 P0 i wymaganej kwalifikacji Q1/Q2 na dokładnym kandydacie. To zewnętrzna granica tego zadania, nie powód do zatrzymania pozostałych funkcji.

Kolejność: blokada importu → CLI prepare/status/resume/report → regresje produkcyjnej blokady → rzeczywista mała kampania i lokalna kontrola → manifest odtwarzania/kontrolowane czyszczenie → build, lint, mypy, produktowe testy, instrukcja i raport.

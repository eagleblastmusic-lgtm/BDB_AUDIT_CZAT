# NF02 — plan i zakres wykonania (2026-10-02)

Repozytorium: `eagleblastmusic-lgtm/bdb-audit`; zastana gałąź
`fix/nf02-lane-result-authority`; HEAD `b7051472909075bb4c83a9a510e298fcca2a6bd5`.
Kontynuacja zastanych ośmiu zmienionych plików bez resetowania ich zawartości.
Dokumenty poprzednich audytów pozostają historycznymi dowodami.

## Kolejność

1. R5: poprawić import `Any`, powtórzony import `hmac` i EOF testów.
2. Niezależna część R1: odtwarzać canonical proposal z owned raw ZIP i
   accepted assignment; używać tej samej normalizacji w Inbox i Store.
   Przed podpisaniem i przy acceptance sprawdzać digest oraz member evidence.
   Sprawdzać pełny HistoryCut i istniejący stage/assignment przy wydawaniu ticketu.
3. Niezależna część R2: sprawdzać deklarowany raw package digest i kontekst
   faktycznych package bytes w vault. Ten test nie jest dowodem pierwotnej
   assignment-time identity paczki.
4. R4: odtworzyć ticket po zweryfikowanym wznowieniu manual phase, dopiero
   po zaostrzeniu issuera; testy restartów E2/E3/E4.
5. Trwałe regresje: caller-selected proposal, raw package hash, pełny cut,
   manifest/member evidence i positive controls/restart. Następnie affected
   workflow/history/Registry checks, Ruff, Mypy oraz kontrola końcowego diffu.

## Warunki wstrzymujące rozszerzenie implementacji

`SPEC_CONFLICT` dla R0 i autorytatywnej części R2: Data Contracts §6 (wiersz
226) dopuszcza nowy canonical kind wyłącznie w exact pinned
SchemaRegistry/spec revision; §184 (wiersze 5076–5087) wymaga exact bindingu
i blokuje konflikt warstw authority; §187 dopuszcza tylko zarejestrowane role.
Obecne hardcoded kontrakty NF02 używają PROVENANCE/PROPOSAL, których nie ma
w normative role domain. Żaden z obu kinds nie występuje w zamrożonej Registry
ani w istniejącym byte-pinned overlay (zawiera on tylko residual_risk).
Dynamiczne generowanie schematu i podpisanie caller body nie ustanawia
niezależnego normative pin ani authority.

AGENTS.md zabrania zmiany normatywnych R5.3 dokumentów i frozen candidate.
Potrzebna jest zatwierdzona rewizja definiująca NF02 schema/reference contract,
activation/compatibility oraz exact assigned package authority. Nie dopisujemy
samodzielnie nowej normatywnej rewizji, drugiego ledgera authority ani
cache-as-authority. Nie stosujemy migracji/reinterpretacji zapisanych revisions.

R3 wymaga rozstrzygnięcia i kwalifikacji wspólnej trwałości raw closure oraz
historii. Dodatkowy filesystem read nie usuwa wykazanego TOCTOU. Ten punkt
pozostaje otwarty; nie deklarujemy atomic raw retention.

## Odbiór

Lokalne regresje muszą wykazać typed rejection bez zmiany canonical counts/head
i działające legalne importy po restarcie. Pełny NF02/release gate pozostaje
BLOCKED do rozwiązania R0/R2/R3 oraz przejścia R6/R7 (w tym exact candidate,
wymaganych qualification/build/standalone i post-commit gates). Nie wykonujemy
commitu/pusha/PR ani nie deklarujemy aplikacji w pełni zakwalifikowanej.

Końcowe komendy, wyniki, zmienione pliki i ograniczenia zostaną zapisane w
`docs/NF02_IMPLEMENTATION_RESULT_2026_10_02.md`.

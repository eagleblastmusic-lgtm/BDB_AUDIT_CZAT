# NF02 — dalsza naprawa: trwałość raw closure

Kontynuacja lokalnej naprawy na zastanej gałęzi `fix/nf02-lane-result-authority`,
HEAD `b7051472909075bb4c83a9a510e298fcca2a6bd5`. Zachowujemy wcześniejsze zmiany.

## Podstawa i delta

Architecture §§43.1–44.4 i ADR-012 oraz Data Contracts §15.5 wymagają jednej
transakcji dla mandatory immutable bytes, commit, receipt i head. SQLite jest
dozwolonym profilem implementacyjnym. Poprzedni raport zbyt szeroko wiązał R3
z koniecznością nowej specyfikacji: fizyczną trwałość istniejących exact bytes
można poprawić bez zmiany wire schema ani zamrożonego corpus.

1. Zachować zweryfikowany snapshot ZIP wyniku i ZIP paczki w tym samym SQLite
   transaction, który przyjmuje admission evidence/result. Pliki vault są stagingiem.
2. Resolver i wznowienie muszą sprawdzać retained bytes, digest i długość.
   Uszkodzona lub niepełna accepted raw closure blokuje użycie; nie zastępujemy jej
   dobrym plikiem ze stagingu. Nie migracja ani reinterpretacja historycznych refs.
3. Udowodnić usunięcie pliku między walidacją a durability, rzeczywiste przerwanie
   procesu w każdej granicy obu commitów, exact retry po utracie ACK, korupcję,
   brak raw closure, restart i concurrent expected-head guards.
   Dodatkowe odtworzone finding: issuer podpisywał orphan AssignmentManifest oraz
   fałszywy schema identity. Rozwiązać assignment/attempt/source przez istniejący
   verified accepted index na jednym locked cut przed wydaniem capability.
4. Wykonać wymagane affected workflow/history checks, Ruff, Mypy, lokalny build,
   standalone self-test i kontrolę zakresu diffu. Dowody odnoszą się do dirty worktree.

## Granice odbioru

R0 i autorytatywna część R2 pozostają oddzielnymi konfliktami: Data Contracts
§6/§184 wymagają approved exact pinned SchemaRegistry/spec revision dla nowych
kinds; §187 nie rejestruje ról PROVENANCE/PROPOSAL. Brakuje approved NF02
activation oraz pierwotnego accepted package pin. Ta zmiana ich nie ustanawia.
Stara baza bez mandatory retained raw bytes jest blokowana jako niekompletna;
nie naprawiamy jej milcząco przez autoryzację bieżących plików.

Nie zmieniamy normative R5.3, baseline qualification, frozen candidate, legacy,
refs Git ani remote. Pełny NF02/release gate nie otrzymuje PASS z lokalnych testów.

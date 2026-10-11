# BDB Audit PRODUCT-V1 — uruchomienie na Windows

Produkt przygotowuje rzeczywistą kampanię, pięć paczek E1, wznawia zapisany stan i eksportuje raport częściowy. Wykonuje prawdziwe lokalne kontrole przez istniejący runner. **Przyjmowanie wyników zewnętrznych jest zablokowane: NF02 OPEN.** Pełny audyt E1–E6 ani Q1/Q2 nie są ukończone przez samo przygotowanie paczek.

## Uruchomienie dostarczonego pliku

Wymagane: Git i CPython 3.14 na Windows x64. Plik zawiera przypięte biblioteki runtime. Nie wymaga pip ani repo `src/` podczas działania. To lokalny build produktu, bez statusu kwalifikowanego release.

```powershell
Set-Location 'C:\Projekty\Audyty\BDB Audit'
$env:PYTHONUTF8 = '1'
$bdb = (Resolve-Path 'dist\BDB_AUDIT_ASSISTANT_v2.0.3_PRODUCT_V1.py').Path
py -3.14 -I $bdb product --help
py -3.14 -I $bdb ui
```

CLI ma pełny przepływ PRODUCT-V1. TUI zachowuje dotychczasowe menu i pokazuje blokadę NF02; dotychczasowe tryby Codex/Antigravity nie otrzymują automatycznie zaimplementowanego wykonawcy.

Alternatywna instalacja ze źródeł (sieć wymagana do pobrania przypiętych zależności):

```powershell
py -3.14 -m venv .venv-product
.\.venv-product\Scripts\python.exe -m pip install -r requirements-f2.lock
.\.venv-product\Scripts\python.exe -m pip install --no-deps -e .
.\.venv-product\Scripts\python.exe -m bdb_audit product --help
```

## Własna kampania

Zastąp ścieżkę repo własnym lokalnym repo Git. Ref jest rozwiązywany do prawdziwego commit i tree; niezapisane pliki nie stają się częścią wybranego commitu. Użyj nowego katalogu `work\moja-kampania` dla nowej kampanii.

```powershell
py -3.14 -I $bdb product preflight --repo 'C:\MojeRepo' --ref HEAD --store '.\work\moja-kampania\campaign.sqlite'
py -3.14 -I $bdb product start --repo 'C:\MojeRepo' --ref HEAD --store '.\work\moja-kampania\campaign.sqlite'
py -3.14 -I $bdb product status --store '.\work\moja-kampania\campaign.sqlite'
```

`READY_FOR_PREPARATION` oznacza poprawny preflight. `READY_FOR_REVIEW` oznacza przygotowane paczki, bez ukończonego audytu. Wynik wskazuje exact SHA/tree, assignment, attempt, cut, lokalizację każdego ZIP i jego raw SHA256. GitHub ref: `--target-type github --repo 'https://github.com/owner/repo.git' --ref main`; wymaga legalnego dostępu do sieci/repo, bez sekretów w URL. Przed wysłaniem paczek uprawnionemu wykonawcy udostępnij również źródło wskazanego dokładnego commitu. Sam ZIP zadania nie zapewnia dostępu do lokalnego repo.

## Rzeczywiste lokalne kontrole

Runner uruchamia dokładną komendę bez shell i zapisuje stdout/stderr oraz receipt. Używaj zaufanych poleceń na niewrażliwych danych. Nie wymusza izolacji sieci/hosta: `--require-network-isolation` lub `--require-host-filesystem-isolation` zatrzymuje taki przebieg jako BLOCKED.

Przed kontrolą zamroź pliki badanego commitu w osobnym katalogu. Nie przekazuj runnerowi całego checkoutu z niezapisanymi plikami, jeżeli raport ma dotyczyć exact SHA:

```powershell
git -C 'C:\MojeRepo' archive --format=zip --output='C:\Projekty\Audyty\BDB Audit\work\source.zip' EXACT_COMMIT_SHA
Expand-Archive -LiteralPath '.\work\source.zip' -DestinationPath '.\work\source'
$python = (Get-Command python).Source
py -3.14 -I $bdb tools run --source '.\work\source' --evidence '.\work\moja-kampania\checks-1' --run-id checks-1 --json -- $python -m unittest discover -v
py -3.14 -I $bdb tools results --evidence '.\work\moja-kampania\checks-1'
```

`SUCCESS` i exit 0 odnoszą się do wskazanej kontroli. `TARGET_NONZERO` oznacza niezerowy wynik celu; zajrzyj do stderr/stdout i nie nazywaj go PASS audytu. Receipt verification sprawdza integralność plików, nie autoryzację producenta, nie kompletność audytu ani automatyczne związanie lokalnej komendy z kampanią.

## Paczki, wyniki i bezpieczna blokada

Każdy ZIP zadania zawiera `MANIFEST.json`, `PACKAGE.json`, `PROMPT.txt` i kontrakt wyniku w prompt. Dotychczasowy format E1 to ZIP z root `MANIFEST.json`: `kind=bdb_audit_lane_result`, `version=1`, campaign/stage/lane, exact `source_commit_sha`, `input_package_digest`, `executor_profile`, `executor_model`, pełny `history_cut` z paczki i `findings[]`. Dalsze fazy mają własne obowiązkowe outputs z kontraktu zadania. Są to autentyczne formaty transportu, **bez prawa do akceptacji w PRODUCT-V1**.

Zachowaj otrzymany ZIP poza canonical history do późniejszej niezależnej autoryzacji. Nie zmieniaj deklaracji izolacji na ENFORCED i nie wystawiaj sobie grantów. Próba importu:

```powershell
py -3.14 -I $bdb product import --store '.\work\moja-kampania\campaign.sqlite' --zip '.\wynik.zip'
```

zwraca exit 2 i `PRODUCT_V1_EXTERNAL_INGESTION_BLOCKED`, przed czytaniem ZIP, zapisaniem raw i zmianą historii. Zablokowane są także E1/Stage inbox i centralny Store. Odbiór uprawnionego wyniku wymaga niezależnego source-of-authority instalacji, pełnej macierzy NF02 P0 i wymaganej kwalifikowanej aktywacji następcy. Decyzja organizacyjna PRODUCT-V1 tego nie zastępuje.

## Wznowienie, raport i dowody

```powershell
py -3.14 -I $bdb product resume --store '.\work\moja-kampania\campaign.sqlite'
py -3.14 -I $bdb product report --store '.\work\moja-kampania\campaign.sqlite' --output '.\work\moja-kampania\raport-1.md' --run-evidence '.\work\moja-kampania\checks-1'
```

Wznowienie sprawdza zapisane paczki i accepted history. Nie twórz ponownie kampanii w tym samym store; `start` odmawia nadpisania. Podmieniony/brakujący ZIP pozostaje BLOCKED. Raport zapisuje się tylko do nowego pliku, chroniąc istniejące eksporty i dowody. `report export/verify` i `evidence inspect/verify` pozostają dotychczasowymi komendami inspekcji istniejących accepted records; nie ustanawiają nowej authority.

Demonstracja tego dostarczenia: `DEMO_AUDIT_REPORT.md` i `SMOKE_EVIDENCE.json`. Mały rzeczywisty repo Git ma jawnie zasiany błąd clamp: kontrola dodawania przeszła, test clamp wykrył błąd. To rzeczywiste wykonania lokalne, bez symulowania AI. Kampania została wznowiona w nowym procesie, z potwierdzonym brakiem mutacji historii po odrzuceniu.

Powtórzenie demonstracji ze źródeł:

```powershell
.\.venv-f2\Scripts\python.exe tools\product_smoke.py
```

Odzyskanie usuniętych kopii: `CLEANUP_PLAN.md` i `CLEANUP_REMOVAL_MANIFEST.json`. Oryginały pozostają w commicie `f23dbedccb6dca9d23f41830e282e814e550bca1`. Nie wykonano push, merge, release ani przepisania historii.

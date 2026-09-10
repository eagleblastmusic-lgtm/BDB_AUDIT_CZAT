# F2 execution and evidence map

Start: `756e8684cbf23a511812065eeda74afb74f7636e`, bdb-v2. CORR-1 governs
prerequisite splitting; see PREFLIGHT_SPEC_RESOLUTION.md. No F3 work.

| Package | Implementation | Verification |
|---|---|---|
| PR-007 | Minimal module CLI, package metadata, Authority protocol | CLI help exit 0; test_cli.py: 1 passed |
| PR-008 | Exact Registry/golden loader, offline immutable schema bindings, pinned backend/formats; no runtime history | 28 substrate tests passed; affected F1/F2/compatibility suite before final narrow follow-up: 207 passed |
| PR-009 | Contract reconciliation only; no acceptance implementation | BLOCKED: F2-BOOTSTRAP-ORDER-002 |
| PR-010–PR-019 | Sequential original task scope | NOT_STARTED due to normative blocker |

No phase acceptance is claimed by this work log.

PR-007: `C:\Python314\python.exe -B -m bdb_audit --help` with
`PYTHONPATH=src`: exit 0. `.venv-f2\Scripts\python.exe -B -m pytest
tests/f2/test_cli.py -q -p no:cacheprovider --tb=short`: 1 passed.
Initial sandbox run could not use the existing Windows pytest temp directory;
the same test passed with authorized access. Local venv creation likewise
needed access to Windows temp for ensurepip. These were environment failures,
not behavioral regressions. No owner temp directories were cleaned.

PR-008 commands (local `.venv-f2\Scripts\python.exe -B`):

- `-m pytest tests/f2/test_registry_schema.py -q -p no:cacheprovider --tb=short`: 28 passed at final PR-008 state.
- `-m pytest tests/f1 tests/f2 tests/compatibility/test_legacy_baseline.py tests/compatibility/test_compatibility_corpus.py -q -p no:cacheprovider --tb=short`: 207 passed before the final localized reference-sort/error-code correction; one expected duplicate-ZIP fixture warning.

Backend: jsonschema 4.25.1, attrs 26.1.0, jsonschema-specifications 2025.9.1,
referencing 0.37.0, rpds-py 2026.6.3. Draft 2020-12; BDB-F2-FORMATS-1:
lowercase UUIDv4, UTC Z timestamps, lowercase SHA-256. No external schema
retrieval or dynamic schema references. These explicit reference-profile
restrictions are enforced at binding/validation and captured by backend_identity.
PR-008 test schemas only qualify the substrate; no M5 schema set or runtime
acceptance is claimed. Full phase golden qualification remains pending.

M5 reconciliation found F2-BOOTSTRAP-ORDER-002; see
BOOTSTRAP_ORDER_SPEC_CONFLICT.md and tests/f2/diagnose_bootstrap_order.py.
The diagnostic verifies exact source pins and proves incompatible required
relative orders. `-m pytest tests/f2/test_bootstrap_order_diagnostic.py -q
-p no:cacheprovider --tb=short`: 2 passed (diagnostic tests, not M5 gate).
The diagnostic process returns 2/SPEC_CONFLICT; PowerShell's implicit wrapper
initially surfaced native nonzero as tool exit 1. The subprocess test directly
verified exit 2 and NOT_RUN M5 status. No runtime acceptance was attempted.

Local semantic commits:

- PR-007: `19a0cb8` — minimal M4 CLI/Authority boundary and test.
- PR-008: `b18f9a4` — Registry/goldens + offline schema substrate and tests.

No F2 MilestoneAcceptance, full phase verifier or synthetic accepted HistoryCut
has been fabricated. Existing preflight diagnostic remains untracked and
unchanged. Main, frozen legacy/corpus, F0/F1 evidence and normative inputs
have not been modified. The only production dependency added is jsonschema
and its transitive reference backend, pinned in requirements-f2.lock.

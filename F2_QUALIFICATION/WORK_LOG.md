# F2 execution and evidence map

Start: `756e8684cbf23a511812065eeda74afb74f7636e`, bdb-v2. CORR-1 governs
prerequisite splitting; see PREFLIGHT_SPEC_RESOLUTION.md. No F3 work.

| Package | Implementation | Verification |
|---|---|---|
| PR-007 | Minimal module CLI, package metadata, Authority protocol | CLI help exit 0; test_cli.py: 1 passed |
| PR-008 | Registry/golden + schema substrate | Pending |
| PR-009–PR-019 | Sequential original task scope | Pending |

No phase acceptance is claimed by this work log.

PR-007: `C:\Python314\python.exe -B -m bdb_audit --help` with
`PYTHONPATH=src`: exit 0. `.venv-f2\Scripts\python.exe -B -m pytest
tests/f2/test_cli.py -q -p no:cacheprovider --tb=short`: 1 passed.
Initial sandbox run could not use the existing Windows pytest temp directory;
the same test passed with authorized access. Local venv creation likewise
needed access to Windows temp for ensurepip. These were environment failures,
not behavioral regressions. No owner temp directories were cleaned.

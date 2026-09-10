# F1 — Minimal Assurance Primitives & Dual Compatibility

Scope: M2–M3 / PR-003–PR-006. Parent: `5d2093076f7ef27ea68c69289ae6a5cf2f60b7ef` on `bdb-v2`.

This is pre-history synthetic qualification under the exact author baseline;
it does not freeze the foundation, admit legacy artifacts into v2 accepted
history, or qualify a release. F2/M4 is not implemented. The library can be
imported with `PYTHONPATH=src`; no production dependencies were introduced.

| Work package | Implementation | Verification |
|---|---|---|
| PR-003 | errors, CJSON, bounded SHA-256, separate digest value types, registered domains, typed IDs/reference checks | `tests/f1/test_core.py`: golden identities, independent generated integer-object oracle (200 cases), boundary/negative cases, process determinism |
| PR-004 | bounded ZIP input/central directory/member/aggregate/actual expansion; exact raw hash manifests | `tests/f1/test_zip.py`: traversal/collisions/special files, CRC, quotas, forged size+CRC, supported compression, ZIP64, handle cleanup, membership/hash failures |
| PR-005 | mechanical source/checkpoint/prefix/attestation/continuation/final validators; previous-prompt validation | `tests/f1/test_legacy.py`: all 25 M1 fixtures plus boundary, malformed, metadata, duplicate-basename and byte-snapshot tests |
| PR-006 | test-only dual differential harness with separately pinned independent expectations | `tests/f1/dual_support.py`: verdict, semantic error families, source/checkpoint/prefix/family projections; synthetic two-oracle falsification |

Historical payload metadata was mechanically extracted from frozen v1.4.4.
The extracted production module imports neither the frozen application nor
its UI. Legacy reports remain observations; none becomes runtime authority.
Historical bytes, M0/M1 inputs, F0 records and their verification code remain
unchanged. Schema-specific field grammar, executable schema binding and
accepted-history reference resolution remain outside F1; the identity value
objects are not a new wire schema or an acceptance API.

The normative `test_object` golden vector exercises the internal mathematical
domain-preimage routine. Public registered `object_digest` resolves exact
Registry kind/version and rejects unregistered aliases. The full pinned
Registry is shipped as exact bytes and verified on each lookup. Canonical
serialization never strips evidence text or silently removes envelope fields.

ZIP limits are explicit resource budgets. Archives are never extracted to the
filesystem; nested archives remain opaque bytes. Legacy validation owns one
immutable, bounded archive snapshot so its hash cannot drift from validated
content. Known duplicate/path errors are retained during legacy diagnostics;
any such error makes the validator fail. Identical basename copies preserve
the existing handoff policy, while conflicting copies fail.

## Source provenance

`inputs/` retains exact-byte copies of the task context, author qualification
and relevant complete R5.3 sources found in the local Downloads workspace.
Their source hashes match the context pins. The full Registry is in
`src/bdb_audit/core/artifact_contract_registry_r5_3.json`.

The locally available older Execution Plan has SHA-256
`04ca2fb261d213f3e01c303f889cb713748b3bd7b1e42619f0830f1ced42e070`,
whereas the task packet cites
`7ec2de0ccfba3672a9a399af2b77f6fc5dfb42d87645e65206ca8bb5c8007d59`.
The older F1 section agrees but omits later P02/P03 clarifications. It is not
substituted for the cited source. F1 follows the attached task requirements
including P02/P03. No material normative conflict was found.

## Reproduction and closeout

Before F1 staging, the original command passed at the exact qualified HEAD:

```powershell
C:\Python314\python.exe -B tests/compatibility/verify_f0.py
```

After staging intended F1 inputs, qualify, stage the resulting artifact, commit
locally and replay:

```powershell
C:\Python314\python.exe -B tests/f1/verify_f1.py --record
git add -- F1_QUALIFICATION/F1_MILESTONE_ACCEPTANCE.json
git commit -m "Implement F1 minimal assurance primitives and dual compatibility"
C:\Python314\python.exe -B tests/f1/verify_f1.py
git status --short
```

The F1 verifier runs the complete F1 tests, unchanged `verify_m1.py`, four
baseline tests and the frozen legacy self-test, and independently replays all
25 fixtures. Its descendant F0 regression verifies every original F0 blob/raw
pin and `main`, then runs the original regression commands. The original
`verify_f0.py` remains unchanged and intentionally requires the F0 HEAD itself.

Qualification contains exact command vectors, test counts, source/test Git
blobs and raw digests, parent/F0/baseline pins, and per-fixture dual outcomes.
It omits timing from deterministic replay. The containing commit binds the
record itself, avoiding a circular commit/digest preimage.

## Verification history and environment

Initial sandbox F0 run: 85 passed / 1 failed because the previous-prompt
self-test could not access temporary directories (`WinError 5`). The identical
command outside the sandbox passed: 86 M1 tests, 4 baseline tests and both
legacy self-tests. The unchanged F0 verifier passed again before staging.

During implementation the F1 suite progressed through 41, 53, 81, 85, 88 and
91 passing tests. Intermediate failures were a Windows ZIP-fixture writer
normalizing backslashes (corrected by mutating the ZIP wire bytes), sandbox
temporary-directory access, and missing extracted canonical payload metadata
(completed from exact frozen source). Final authoritative counts are in the
qualification artifact and are replayed after commit. Duplicate-name test
construction intentionally produces one standard-library warning.

Relevant suite commands executed:

```powershell
C:\Python314\python.exe -B -m pytest tests/f1/test_core.py -q -p no:cacheprovider
C:\Python314\python.exe -B -m pytest tests/f1 -q -p no:cacheprovider
C:\Python314\python.exe -B -m pytest tests/f1 -q -p no:cacheprovider --tb=short
```

Repository inspection used `Get-Location`, `git rev-parse --show-toplevel`,
`git branch --show-current`, `git rev-parse HEAD`, `git status --short`,
`git remote -v`, `git ls-files`, `git rev-parse main`, `git diff --stat`,
`Get-Content`, `Get-FileHash` and targeted `rg` searches. Read-only Python
diagnostics checked source SHA-256 pins, the golden preimage, legacy replay
errors and function dependencies. No reset, clean, push, merge, tag or remote
ref mutation was performed. Pre-existing untracked documents, AGENTS.md,
compatibility bytecode and inaccessible cache directories were left untouched.

During closeout the three pre-existing review documents disappeared from the
workspace. Work paused on the drift check; the owner explicitly confirmed
their deliberate removal and instructed F1 to continue. Those removals were
not performed or staged by this task. The first `git add` attempt was denied
by filesystem sandboxing (`.git/index.lock`); authorized local staging and
commit therefore use the escalated Git command path.

Final pre-qualification suite: **93 passed**, one expected duplicate-name
construction warning. The added ZIP64 test initially encoded the wrong EOCD
field indexes; corrected wire bytes pass the actual reader without weakening
its checks.

`git diff --cached --check` reports whitespace already present in the retained
normative source bytes (Markdown hard breaks and terminal blank lines). Those
identity-bearing copies are deliberately preserved. The check scoped to new
implementation/tests/qualification prose passes.

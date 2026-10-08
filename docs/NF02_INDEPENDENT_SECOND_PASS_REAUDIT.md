# NF02 INDEPENDENT SECOND-PASS RE-AUDIT

Audit date: 2026-09-28

## A. Audited identity

- **Repository requested:** `eagleblastmusic-lgtm/BDB_AUDIT_CZAT`.
- **Exact audited source:** merge commit `a106bedca02d310bfb30d84d6ce65e5581f65ef5`; Git tree `3bc05685293d2fade72735e43a2ccc96be26f3f7`.
- **Comparison base:** `f9cbd0f79e9814b97d4b1baa415fb02de602e27f`.
- **Candidate commits:** `850a181be92d6e32bc13d526e3bc6efae3d15764`, `b7051472909075bb4c83a9a510e298fcca2a6bd5`.
- **Local checkout:** `C:\Projekty\Audyty\BDB Audit`, branch `fix/nf02-lane-result-authority`, HEAD `b7051472909075bb4c83a9a510e298fcca2a6bd5`. Its tree equals the target merge tree. The exact merge source was independently materialized with `git archive`; its `src/` was used first on `PYTHONPATH` for tests and probes. A temporary adversarial pytest file was added only to that archive after identity verification.
- **Final workspace:** production checkout restored to the branch commit; only the audit plan and report are retained as untracked documentation. No `main`, legacy bytes, commits, merges, or remote refs were changed.
- **Environment:** Windows PowerShell; CPython 3.14.4, pytest 8.4.2, jsonschema 4.25.1. For the exact-source test run, `PYTHONPATH` pointed to the archive's `src` first. A temporary pytest plugin redirected `tmp_path` into the approved scratch directory because the default Windows temp path returned access denied. The exact-source clone attempt failed with Win32 error 5, so the byte-identical Git archive was used instead.

Identity commands included `git rev-parse HEAD`, `git status`, `git log -n 3 --oneline`, `git show --stat a106bedca02d310bfb30d84d6ce65e5581f65ef5`, and `git rev-parse 'a106bedca02d310bfb30d84d6ce65e5581f65ef5^{tree}'`. Target tree and local HEAD tree both resolved to `3bc05685293d2fade72735e43a2ccc96be26f3f7`.

## B. Independent architecture reconstruction

### Actual result-authority chain

```text
result ZIP bytes
  → E1ResultInbox.ingest_zip / StageResultInbox.ingest_zip
  → RawArtifactVault.put_bytes (exact ZIP and member bytes)
  → MANIFEST.json parse and workflow checks
  → canonical bdb_audit_lane_result proposal + result_proposal_digest
  → lane_result_admission_evidence accepted in its own INGEST_EXTERNAL_LANE_RESULT commit
  → bdb_audit_lane_result + DiscoveryRecord(s) + LaneCompletion accepted in RECORD_FOUNDATION_FACT
  → E1 stage finalizer / stage-specific finalizer
  → StageCompletion accepted after required lane/output validation
```

The normal E1 and manual-stage importers build the evidence and result proposal, but the final writer is `Coordinator.accept`, a pass-through to `TransactionalHistoryStore.accept`. The store's validation/hook layer is therefore the effective authority boundary. It runs schemas, semantic authority hooks, typed/prior-reference checks and expected-head/CAS checks before one SQLite commit transaction writes immutable objects, commit, receipt and accepted head.

For admission evidence, `authority_hooks.py::_validate_lane_result_admission_evidence` reads the raw digest from the store-adjacent vault, verifies the raw hash, ZIP, root manifest and matching campaign/stage/slot/source/package/executor strings, and checks the referenced accepted assignment's attempt, source-generation ref and assignment cut. The hook does not authenticate who constructed the evidence. `producer_authority = TRUSTED_INGESTION_BOUNDARY` exists as pinned-looking declarative extension metadata in `core/registry.py`, but no capability, signature, private token or store-side trusted-caller identity is checked. In `store.py`, lines 775–780 treat the caller-selected command string `INGEST_EXTERNAL_LANE_RESULT` as sufficient to admit evidence and require that this command contain evidence objects only.

For result consumption, `_validate_lane_result` resolves admission evidence and hashes the complete result body except `admission_evidence_ref`; matching material values and `result_proposal_digest` are checked. It does not re-read the raw bytes. As a result, a self-authored evidence object with a self-computed digest can pass, and a vault object removed after evidence acceptance does not prevent later result acceptance.

`PRIOR_ACCEPTED_ONLY` has executable effect for reference membership: a result cannot use a same-commit evidence object as an accepted prior object, and a valid evidence/result same-commit probe failed without changing accepted state. That proves ordering, not trusted issuance. The attacker can first accept self-authored evidence in a prior commit.

`LaneCompletion` is checked by `_validate_lane_completion` for exact lane/stage/source/attempt/knowledge/isolation context and required outputs. `StageCompletion` is checked by `_validate_stage_completion` against the accepted governing StageSpec, required lane slots, lane-completion facts, outputs, source generation and cuts. A completion without result evidence is rejected in the exercised manual-stage path. However, these protections consume accepted lane results; they do not distinguish the attacker-authored result admitted through the primary bypass.

### Context/proposal binding assessment

`result_proposal_digest` is SHA-256 over canonical bytes for every result body field except `admission_evidence_ref`; unknown body fields are covered if included in that body. The normal producer and validator use the same canonical JSON implementation. No digest omission or canonicalization collision was demonstrated. This digest only binds a proposal to the admission object that declares the digest; because a caller can write both objects and choose the digest, it does not prove trusted provenance.

The evidence validator verifies self-declared manifest strings against evidence fields and verifies some refs against assignment facts. It does not derive every context value from the authoritative refs. In a successful direct-store probe, accepted assignment/attempt/source-generation refs were real E1-A refs while the evidence and result claimed a different source SHA, input-package digest, executor profile and model; a matching ZIP manifest plus self-computed proposal digest was accepted. This is the cross-context laundering that the current checks leave open.

## C. Attack-surface inventory

| Path or component | Role and audit observation |
| --- | --- |
| `workflow/inbox.py:E1ResultInbox.ingest_zip` | Parses E1 result ZIP, stages exact bytes/members, creates proposal/evidence, and calls `_accept_result`; positive valid E1 and multi-lane flows pass. Does not verify assigned package ZIP hash/content against the live package file. |
| `workflow/inbox.py:E1ResultInbox._accept_result` | Accepts evidence under `INGEST_EXTERNAL_LANE_RESULT`, then result, discoveries and LaneCompletion under generic `RECORD_FOUNDATION_FACT`; normal consumption trusts prior evidence found by assignment ref and raw digest. |
| `workflow/manual_stage.py:StageResultInbox.ingest_zip` | Parallel parser/importer for manual E2/E3/E4 lanes; creates the same evidence/result pattern and uses separate evidence/result commits. It also compares the result manifest digest to the in-memory job digest without re-reading the assigned package ZIP at import. Selected E2/E3 manual flows passed. |
| `workflow/manual_stage.py:StageResultInbox._accept_result` | Same two-step evidence then result/completion authority sequence, forwarded to Coordinator/store. |
| `Coordinator.accept` | Thin unrestricted pass-through; does not authenticate callers or limit command capabilities. |
| `TransactionalHistoryStore.accept` | Actual durable boundary, callable directly; any caller can construct `CanonicalObject`/`CommandEnvelope`. Evidence authority is command-name-gated at lines 775–780. This is the successful middle-of-graph entry point. |
| `history/authority_hooks.py` evidence/result hooks | Validate the structural and semantic facts described above; reject unreferenced/missing raw bytes before evidence acceptance and reject changed result proposal under already accepted evidence. Do not authenticate the evidence producer; do not re-read vault bytes at result acceptance. |
| `RawArtifactVault` | Content-addressed paths, raw SHA-256 readback and collision checks work for bytes that are present. Evidence validation reads by digest; storage is outside the SQLite transaction and may be deleted between commits. |
| `lane_completion` and `stage_completion` hooks | Prevented the direct no-result completion attempt in the exercised test. Normal workflow constructs completion from result outputs; stage validation rechecks all required lane completions. Forged accepted lane results still satisfy these downstream consumers. |
| `history/replay.py` | Replay-verification records/capsules, not an alternate canonical-history restore/import API found for lane results. |
| migration, bundle, snapshot, bulk restore, recovery | Search found no alternate source path that hydrates accepted lane-result objects around `TransactionalHistoryStore.accept`. E1 resume performs package receipt validation at restart, but this does not undo live-session acceptance before restart. No direct DB restore path was demonstrated. |
| Registry/schema registration | The two NF02 kinds are hard-coded extension contracts and dynamically generated executable schemas. They are not in the pinned JSON contract Registry and no accepted/pinned SchemaRegistry record binds their exact executable schema bytes before acceptance. |
| Projections/read models | Consumers query accepted records; no projection was found to confer authority independently. The exploit writes the canonical history itself, so it does not rely on projection authority. |

Searches covered the requested identifiers and constructors, `Coordinator.accept`, Store acceptance, E1/manual-stage inboxes, replay, completion hooks, Registry/schema binding, vault, stage finalization and relevant tests.

## D. Adversarial test matrix

| ID | Attack | Path | Expected | Actual | Canonical mutation? | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | Direct lane result without evidence | Coordinator/store, generic command | Reject with no history change | Rejected by required evidence validation | No | Closed for this shape only |
| A2 | Self-construct valid evidence, choose `INGEST_EXTERNAL_LANE_RESULT`, then submit its result | Direct Coordinator/Store followed by E1 Inbox | No untrusted producer can mint admission | Evidence accepted; Inbox accepted result; five lane completions and StageCompletion accepted | **Yes; head advanced to stage complete** | **Confirmed BLOCKER** |
| A3 | Evidence via generic `RECORD_FOUNDATION_FACT` | Direct store | Reject atomically | `LANE_RESULT_ADMISSION_COMMAND_REQUIRED`; snapshot unchanged | No | Closed for this command name |
| A4 | Evidence and result in one commit with a valid ZIP | Direct store, same-commit refs | Reject because evidence is not prior | Rejected (`UNAUTHORIZED_PRODUCER_AUTHORITY` when using ingest command); unchanged state | No | Closed for tested composition |
| A5 | Reuse accepted E1-A evidence for E1-B | Direct store result path | Reject cross-assignment/lane reuse | Rejected; accepted head/counts unchanged | No | Closed for tested cross-lane reuse |
| A6 | Claim source/package/executor metadata inconsistent with actual accepted assignment refs | Direct self-authored evidence/result | Reject context laundering | Accepted with matching attacker ZIP manifest and self-computed digest | **Yes; result and downstream completion accepted** | **Confirmed under NF02-001** |
| A7 | Cross-stage, cross-attempt, cross-campaign or new-assignment reuse variants | Direct store | Reject exact context mismatch | Not all variants independently generated; source hooks were inspected. Cross-lane is tested; other variants remain untested | Not established | Untested variants |
| A8 | Change findings after legitimate evidence admission | Result hook under `RECORD_FOUNDATION_FACT` | Reject digest mismatch atomically | `RESULT_PROPOSAL_DIGEST_MISMATCH`; store snapshot unchanged | No | Closed for tested finding mutation |
| A9 | Replace each assigned E1 package ZIP while live batch remains active; submit result claiming in-memory original package digest | E1 Inbox | Reject changed assigned package | All five results accepted; raw ZIP SHA and current package-manifest digest differed from original receipt/job identity; stage completed | **Yes** | **Confirmed HIGH** |
| A10 | Remove result ZIP blob after evidence commit but before result commit | Normal E1 flow, instrumented between Coordinator accepts | Reject or fail closed at consumption | Inbox returned ACCEPTED; blob was missing; result, lane completion and StageCompletion accepted | **Yes** | **Confirmed MEDIUM** |
| A11 | Fake/nonexistent vault digest before evidence admission | Direct store evidence | Reject atomically | `RAW_ARTIFACT_NOT_FOUND`; snapshot unchanged | No | Closed for pre-admission absence |
| A12 | Exact result retry | Normal E1 Inbox | Idempotent result; no conflicting duplicate authority | Accepted as `EXACT_RETRY`; original history retained | No additional semantic authority | Positive control passed |
| A13 | Two concurrent evidence accepts with same expected head | Two threads/store calls | Exactly one CAS winner | One accepted, one `EXPECTED_HEAD_CONFLICT`; head advanced once | One expected evidence commit | CAS behavior passed; does not authenticate evidence |
| A14 | Direct LaneCompletion/StageCompletion with no accepted result | Manual E3 completion path | Reject and preserve head/history | `LANE_COMPLETION_EXECUTION_RESULT_REQUIRED`; state unchanged | No | Closed for tested no-result path |
| A15 | ZIP path traversal and duplicate member names | ZIP safety/parser tests | Reject malformed/ambiguous member structure | Existing workflow tests rejected them; duplicate-name test emits expected warning | No | Closed for tested ZIP cases |
| A16 | Duplicate JSON keys, duplicate root manifest, confusable/case-colliding names, trailing/concatenated ZIP, compression bomb, truncation and central-directory variants | ZIP/manifest parser | Fail closed without state mutation | Not fully fuzzed in this pass; canonical JSON parser rejects duplicate JSON keys by inspection, and `zip_safety` rejects tested duplicate member paths | Not established | Untested variants |
| A17 | Same command ID with changed body; stale accepted evidence after head drift; restart/recovery replay; retry after ambiguous ACK | Store/recovery | Conflict or exact idempotent replay only | Exact retry and CAS covered; these specific recovery/replay variants not executed | Not established | Untested variants |
| A18 | Registry/executable schema/pinned SchemaRegistry parity | Store construction and acceptance | New kind requires exact pinned schema-byte binding before first acceptance | Both kinds accepted using runtime-generated schema bindings although absent from pinned Registry and accepted SchemaRegistry binding | **Yes; conflicting kind was accepted** | **Confirmed MEDIUM normative defect** |

## E. Confirmed findings

### NF02-001 — Caller-selected command kind lets a caller self-mint trusted admission evidence and complete a stage

- **Severity:** BLOCKER
- **Affected source:** `src/bdb_audit/history/store.py:733–780`; `src/bdb_audit/coordinator/__init__.py:16–29`; `src/bdb_audit/history/authority_hooks.py:1029–1145`; `src/bdb_audit/workflow/inbox.py:427–459, 515–604, 630–734`.
- **Exact call path:** `Coordinator.accept` forwards to `TransactionalHistoryStore.accept`; caller provides `lane_result_admission_evidence` and sets `command_kind="INGEST_EXTERNAL_LANE_RESULT"`; store validates bytes/manifest/refs but treats command-name equality as producer authorization; evidence is durably accepted. A later ordinary `E1ResultInbox.ingest_zip` finds evidence by assignment ref + raw digest, accepts `bdb_audit_lane_result` and `LaneCompletion`, and after other lane imports accepts `StageCompletion`.
- **Preconditions:** Caller can call the local Coordinator or Store API; accepted campaign assignment facts are readable; caller can place its authored ZIP bytes in the adjacent RawArtifactVault. No privileged identity or secret is required by this path.
- **Attack / failure sequence:** Create a well-formed result ZIP and matching canonical result body; calculate `result_proposal_digest`; construct evidence with the real prior E1-A assignment, attempt and source-generation refs; call the store with the permitted ingest command name; then submit through the ordinary Inbox. The exact-target temporary adversarial test does this, imports the other four lane results, and asserts five lane results, five lane completions and one StageCompletion.
- **Expected authority invariant:** Only the trusted ingestion boundary can issue admission evidence; declarative producer metadata or a caller-supplied command string cannot self-authorize.
- **Observed behavior:** Evidence passes. The command kind is caller-controlled. No trusted caller capability, authenticated actor binding or unforgeable ingestion receipt is checked. `producer_authority` in the extension Registry is metadata, not an executable check. The later digest validates consistency between the caller's evidence and proposal, not the truth or trusted origin of either.
- **Canonical state impact:** Accepted history advances through a `bdb_audit_lane_result`, `LANE_COMPLETED` for every required E1 lane and `STAGE_COMPLETED`. This is the original NF02-equivalent bypass and directly defeats closure.
- **Minimal reproduction:** Test `test_second_pass_direct_store_can_self_mint_admission_and_accept_result` in the temporary exact-source test described in §G. It constructs evidence and uses `Coordinator.accept(..., command_kind="INGEST_EXTERNAL_LANE_RESULT")`, then ordinary E1 ZIP imports; assertion `summary.stage_complete is True` passes.
- **Test / command:** `python -m pytest -p no:tmpdir -p pytest_nf02_no_tmp_fixture -q --tb=short tests\workflow\test_nf02_second_pass_adversarial_tmp.py::test_second_pass_direct_store_can_self_mint_admission_and_accept_result` (the combined two-test file run passed; see §G).
- **Root cause:** The authority decision uses a caller-controlled command name as a proxy for a trusted producer. Evidence validity is checked for internal consistency, but issuance authority is not.
- **Why existing NF02 tests missed it:** `test_adversarial_bypass_b_fake_ingestion_receipt_via_generic_command` only tries `RECORD_FOUNDATION_FACT` and proves that command name is rejected. It never tries valid self-authored evidence under the one allowed command. Other tests prove malformed evidence fails or valid evidence from the normal Inbox works; neither tests the store boundary against a caller impersonating that workflow.
- **Remediation direction:** Enforce an unforgeable, store-verifiable trusted-ingestion capability at the durable authority boundary, or have the store itself derive the evidence from verified raw bytes and accepted assignment facts. Do not rely on the command kind or declarative `producer_authority`. Preserve exact prior-ref, CAS, and atomicity requirements.
- **Confidence:** High. Reproduced on the exact target tree, with canonical stage completion as the asserted outcome.

### NF02-002 — Live E1 intake does not bind the result to the assigned package ZIP bytes

- **Severity:** HIGH
- **Affected source:** `src/bdb_audit/workflow/packaging.py:32–63, 410–423`; `src/bdb_audit/workflow/inbox.py:313–378, 427–459`; package receipt/resume validation is separate from live import.
- **Exact call path:** `prepare_e1_batch` saves `package_zip_path` and `package_zip_sha256` on each `E1LaneJob`; `E1ResultInbox.ingest_zip` compares only incoming manifest `input_package_digest` with cached `job.package_digest`, then records the same cached digest in admission evidence. It does not re-read the assigned package ZIP or verify `job.package_zip_sha256` during import. Manual `StageResultInbox` likewise compares against `job.package_digest` at `manual_stage.py:1965–1966` without re-reading its assigned package ZIP.
- **Preconditions:** The assigned package file can be replaced while an in-memory E1 batch/manual stage remains active, such as by a concurrent workspace writer or buggy orchestration helper.
- **Attack / failure sequence:** Replace `PROMPT.txt` inside each assigned package ZIP after batch preparation, leaving the in-memory job and receipt unchanged. Submit syntactically valid result ZIPs with the cached original `input_package_digest`. The independent test changed each package ZIP's prompt bytes, confirmed its exact SHA-256 no longer matched the stored receipt, then imported all five results.
- **Expected authority invariant:** Result provenance must bind the exact immutable package bytes actually assigned and consumed, or reject package drift before canonical result acceptance.
- **Observed behavior:** All five results were accepted and E1 reached StageCompletion even though the assigned prompt bytes no longer matched the package ZIP hash captured at assignment. The Inbox accepted the cached semantic digest without reading the changed package.
- **Canonical state impact:** Five lane results and completions plus one StageCompletion became authoritative under package bytes different from the assignment-time package bytes.
- **Minimal reproduction:** `test_second_pass_live_package_replacement_is_accepted` in the temporary exact-source test. It rewrites each package ZIP's `PROMPT.txt`, checks `SHA256(current ZIP) != job.package_zip_sha256`, then imports result archives carrying the original cached digest.
- **Test / command:** `python -m pytest -p no:tmpdir -p pytest_nf02_no_tmp_fixture -q --tb=short tests\workflow\test_nf02_second_pass_adversarial_tmp.py::test_second_pass_live_package_replacement_is_accepted` (passed in the combined temporary probe run; see §G).
- **Root cause:** A stored package hash is treated as descriptive state; the live acceptance path does not compare it against the file or verify the exact assigned package contents.
- **Why existing NF02 tests missed it:** Wrong-package tests alter the incoming result's digest and compare it with an unchanged in-memory job. They do not mutate the assigned package after batch creation. Restart/package-resume validation does not cover a live batch that has already accepted results.
- **Remediation direction:** Bind assignment to immutable package bytes/content and verify that exact identity at ingestion/consumption, including manual-stage imports. Ensure replacement cannot race between the verification and the result commit.
- **Confidence:** High. A separate transient probe also recomputed package semantic identity after mutation; this retained test is the minimal ZIP-byte substitution reproduction.

### NF02-003 — Result consumption succeeds after its admitted raw ZIP has been deleted

- **Severity:** MEDIUM
- **Affected source:** `src/bdb_audit/history/authority_hooks.py:1029–1099` (raw read at evidence acceptance) and `1101–1145` (result validation); `src/bdb_audit/workflow/inbox.py:531–579` (separate commits).
- **Exact call path:** Evidence is accepted and raw bytes are read/verified. After the evidence commit returns, delete the digest blob. The subsequent `RECORD_FOUNDATION_FACT` result acceptance validates the evidence reference and proposal digest but does not read the vault again.
- **Preconditions:** The raw vault file is removed after the first accepted evidence commit and before result acceptance. This is a constrained deletion/cleanup race, not a remote unauthenticated primitive.
- **Attack / failure sequence:** Instrument `Coordinator.accept` to delete the evidence digest blob immediately after the `INGEST_EXTERNAL_LANE_RESULT` call succeeds; then allow `E1ResultInbox.ingest_zip` to continue. The Inbox returns `ACCEPTED` while the referenced ZIP is absent.
- **Expected authority invariant:** The exact verified bytes remain durable and are revalidated or protected through every authority transition that consumes their evidence.
- **Observed behavior:** Result acceptance succeeds with a missing vault object; no second raw read catches the deletion. A separate full-flow probe continued through lane/stage completion.
- **Canonical state impact:** The lane result (and in the full-flow probe completion) is accepted although its supposedly durable raw provenance is no longer available.
- **Minimal reproduction:** `test_second_pass_raw_vault_delete_after_evidence_does_not_block_result` in the temporary exact-source test.
- **Test / command:** `python -m pytest -p no:tmpdir -p pytest_nf02_no_tmp_fixture -q --tb=short tests\workflow\test_nf02_second_pass_adversarial_tmp.py::test_second_pass_raw_vault_delete_after_evidence_does_not_block_result` → `1 passed in 5.42s`.
- **Root cause:** Evidence and result are separate commits, but the raw-vault check occurs only on evidence admission; SQLite's transaction does not include or pin the external blob.
- **Why existing NF02 tests missed it:** The fake digest test removes/omits bytes before evidence acceptance. No existing test deletes bytes between evidence and result commits.
- **Remediation direction:** Revalidate digest, byte length and availability at result consumption and coordinate vault retention/deletion with acceptance so the raw object cannot disappear in the check-to-commit interval.
- **Confidence:** High for the demonstrated deletion interval; Medium for exploitation likelihood because it requires a concurrent/local deletion condition.

### NF02-004 — NF02 canonical kinds are accepted without the pinned SchemaRegistry binding required by R5.3

- **Severity:** MEDIUM
- **Affected source:** `src/bdb_audit/core/artifact_contract_registry_r5_3_1.json`; `src/bdb_audit/core/registry.py:34–111`; `src/bdb_audit/schemas/foundation.py:105–120`; `src/bdb_audit/history/store.py:54–66, 232–246, 733–744`.
- **Exact call path:** `ContractRegistry` adds the two NF02 kinds in `_extension_contracts`; `ALL_EXECUTABLE_KINDS` includes them and `foundation_schema_bindings()` generates runtime bindings; `TransactionalHistoryStore._check_schema_bindings` checks `self.schemas.require_bound(key)`. This checks the process-local generated map, not an accepted/pinned SchemaRegistry record containing the exact executable schema bytes+digest.
- **Preconditions:** None beyond using the normal store instance on this target. Its campaign fixture can accept the kinds without first accepting a SchemaRegistry binding for them.
- **Attack / failure sequence:** Submit either NF02 kind through normal acceptance while the active pinned JSON Registry has no contract row and the accepted history has no exact schema-byte binding for that kind. The in-memory extension contract and generated schema are enough for the store.
- **Expected authority invariant:** Per R5.3 Data & Artifact Contracts §§184 and 187, before first runtime acceptance each wire kind's semantic key must be bound to exact executable schema bytes and digest in accepted/pinned SchemaRegistry; absence is fail-closed.
- **Observed behavior:** The two new kinds are accepted from hard-coded extension metadata and generated executable schemas, without the required accepted Registry record. The extension contract itself declares `SCHEMA_BOUND_BEFORE_FIRST_ACCEPTANCE`, but the runtime check does not implement that accepted/pinned binding.
- **Canonical state impact:** An unpinned canonical kind/schema can enter accepted history. This is a normative schema/upgrade authority defect; it is separate from, and not the basis of, the BLOCKER direct-ingress finding.
- **Minimal reproduction:** Store construction with `ALL_EXECUTABLE_KINDS` supplies these generated bindings; the direct forged-evidence test accepts the kind without any accepted SchemaRegistry record. `rg` confirms neither kind exists in the pinned JSON Registry.
- **Test / command:** Fresh schema suites in §G passed but did not assert this normative runtime binding; this was established by source/accepted-history inspection and the direct-store acceptance probe.
- **Root cause:** Runtime extension contracts and generated schemas were introduced outside the pinned Registry/SchemaRegistry acceptance chain.
- **Why existing NF02 tests missed it:** The NF02 fixtures instantiate the normal Store, which auto-generates these schema bindings. Existing schema tests qualify the runtime schema map but do not require an accepted/pinned SchemaRegistry record before first acceptance of the new kinds.
- **Remediation direction:** Use the exact R5.3 SchemaRegistry mechanism and immutable accepted binding for these kinds before enabling runtime acceptance; if the contract source is ambiguous, resolve it normatively rather than editing the pinned baseline ad hoc.
- **Confidence:** High on source/contract mismatch; the active normative Data Contracts directly state the binding requirement.

## F. Existing-test critique

The original `tests/workflow/test_nf02_synthetic_lane_result_authority.py` contains 14 tests. It is materially useful: it rejects an unadmitted result, wrong package/source/executor claims, missing/fake vault digest, post-admission finding mutation, evidence under a generic command, cross-lane evidence reuse, and exact retry; it also has positive controls for one lane and all five E1 lanes through stage completion.

Its central blind spot is that the generic-command test assumes only a normal command should be attempted. It never has an untrusted caller choose `INGEST_EXTERNAL_LANE_RESULT`, construct matching evidence and submit a fully formed result through the durable boundary. The same-commit case asserts a generic `ValidationError` and uses only a minimal ZIP end-of-central-directory byte sequence; it proves that that malformed closure is rejected, not that valid ZIP content cannot self-authorize. The cross-lane test does cover one assignment boundary, and the finding mutation test covers a significant digest-bound field, but neither exercises all result fields or issuer authority.

Most negative tests use `_assert_atomicity`, which compares accepted head, commit count, immutable object count and receipt count. That is a good canonical-state assertion for those particular cases. Coverage still omits package replacement after assignment, raw deletion between the two commits, direct self-minted evidence under the permitted command, result-to-completion laundering from that evidence, broad context permutations, recovery/restart replay and concurrent competing results. The full-stage positive test uses the normal trusted setup path, so it cannot expose caller-controlled evidence issuance. The 14 tests do not establish schema pinning parity.

## G. Fresh execution evidence

All commands below used the exact `a106bed...` Git-archive source (`src` first on `PYTHONPATH`), CPython 3.14.4, pytest 8.4.2 and jsonschema 4.25.1. The `-p no:tmpdir -p pytest_nf02_no_tmp_fixture` options use a temporary pytest plugin solely to avoid denied default Windows temp paths; they do not alter product code or test assertions.

| Scope | Exact command | Result |
| --- | --- | --- |
| Dedicated original NF02 suite | `python -m pytest -p no:tmpdir -p pytest_nf02_no_tmp_fixture -q --tb=short tests\workflow\test_nf02_synthetic_lane_result_authority.py` | 14 passed in 50.68s |
| Inbox, stage finalization, authority binding, result roundtrip, history/store gates | `python -m pytest -p no:tmpdir -p pytest_nf02_no_tmp_fixture -q --tb=short tests\workflow\test_inbox.py tests\workflow\test_stage_finalize.py tests\stage3\test_ru03_authority_bindings.py tests\stage3\test_ru03_result_roundtrip.py tests\f2\test_history_process_faults.py tests\f7\test_f04_f05_direct_store_admission.py tests\f7\test_stop_authority_store_gate.py` | 59 passed; 1 expected duplicate ZIP-name warning in 267.57s |
| Relevant manual-stage and exact retry/completion flows | `python -m pytest -p no:tmpdir -p pytest_nf02_no_tmp_fixture -q --tb=short tests\workflow\test_manual_stage.py::test_e3_blind_checkpoint_and_stage_completion_require_accepted_results tests\workflow\test_manual_stage.py::test_e3_gap_result_validation_requires_authorized_target_coverage tests\workflow\test_manual_stage.py::test_e2_contradiction_resolution_uses_two_commit_dag_and_completes_e2 tests\workflow\test_manual_stage.py::test_e2_reveal_result_completion_uses_authorized_knowledge_state tests\workflow\test_manual_stage.py::test_phase_inbox_accepts_order_independent_results_without_stage_completion tests\workflow\test_manual_stage.py::test_exact_retry_is_idempotent tests\workflow\test_stage_finalize.py::test_e4_stage_completion_direct_admission_requires_exact_accepted_evidence` | 7 passed in 357.91s |
| Registry/schema tests | `python -m pytest -p no:tmpdir -p pytest_nf02_no_tmp_fixture -q --tb=short tests\f2\test_registry_schema.py tests\f2\test_m10_schema_identity.py` | 30 passed in 15.25s |
| Independent forged evidence, normal Inbox consumption and live package replacement | `python -m pytest -p no:tmpdir -p pytest_nf02_no_tmp_fixture -q --tb=short tests\workflow\test_nf02_second_pass_adversarial_tmp.py` | 2 passed in 44.03s. Test 1 self-minted evidence then completed E1 through the normal Inbox; test 2 replaced each assigned package prompt and still completed E1. |
| Independent raw-vault TOCTOU probe | `python -m pytest -p no:tmpdir -p pytest_nf02_no_tmp_fixture -q --tb=short tests\workflow\test_nf02_second_pass_adversarial_tmp.py::test_second_pass_raw_vault_delete_after_evidence_does_not_block_result` | 1 passed in 5.42s; evidence ZIP was deleted after evidence acceptance, yet result acceptance succeeded. |

The four existing test groups total **110 passed, 1 expected warning, 0 reported skips**. The three independent temporary attack tests add **3 passed**. The temporary tests were not added to the production checkout. No complete repository qualification run was performed; it was not needed to decide closure after the blocking counterexample was reproduced. Historical CI is not counted as fresh execution evidence.

## H. Residual risk

### Proven closed for the exact tested variants

- A result lacking admission evidence is rejected before canonical acceptance in the direct-result regression case.
- Evidence under generic `RECORD_FOUNDATION_FACT` is rejected and the dedicated regression checks unchanged accepted-state counters/head.
- Same-commit evidence/result composition is rejected in the tested case; prior-only ref semantics have executable enforcement.
- Reuse of E1-A evidence for E1-B is rejected.
- Changing findings after legitimate evidence admission is rejected by proposal digest mismatch.
- A nonexistent vault digest is rejected before evidence acceptance.
- Exact retry remains idempotent.
- Concurrent evidence commands sharing an expected head serialize by CAS: one commit wins and one conflicts.
- The tested direct LaneCompletion/StageCompletion attempt without an accepted result is rejected atomically.
- ZIP path traversal and duplicate member paths are rejected by exercised workflow coverage.
- Valid one-lane E1, five-lane E1, selected manual E2/E3/E4 paths and stage completion continue to pass.

These passing variants do not close the demonstrated trust-boundary defect.

### Confirmed open classes

- Any local caller able to submit to the Store can choose the allowed ingest command and self-mint evidence; that evidence can lead to lane and stage completion.
- Live replacement of assigned package bytes is not detected by E1/manual result import.
- Deleting raw result bytes after evidence commit does not block result acceptance.
- NF02 kinds lack the R5.3-required accepted/pinned executable SchemaRegistry binding before first runtime acceptance.

### Not established in this pass

- Full cross-stage, cross-attempt, source-generation, campaign and new-assignment permutation matrix beyond the successful mismatched source/package/executor claims and rejected E1-A-to-E1-B reuse.
- Every result-body mutation and every optional/unknown-field/canonicalization boundary, although the implementation hashes the full result body except the evidence ref and one findings mutation was rejected.
- Same command ID with changed body, stale evidence after head drift, ambiguous-ACK restart/recovery replay and concurrent competing result acceptance.
- Duplicate JSON key/root manifest, Unicode/case confusables, trailing/concatenated archives, decompression bombs, truncation and malformed central-directory fuzz. Duplicate JSON keys are rejected by the canonical parser by inspection; ZIP duplicate member/path checks passed selected tests.
- Every hypothetical host-level database restore or offline DB manipulation path; source search found no application-level restore path bypassing `Store.accept`.

### Assumptions and environment limits

- The direct attacker is a buggy or untrusted local caller of a public Python authority API, matching the original task threat model. The code does not impose a separate OS principal/remote boundary on this API.
- RawArtifactVault tampering/deletion requires local filesystem access; the deletion race is therefore constrained, while forged evidence needs only Store API access and caller-writable raw bytes.
- Tests ran on Windows only. Full repository qualification was not run. The test source was a Git archive whose tree hash was verified equal to the exact merge tree; temporary probes changed only the archive's test directory.

## I. Final NF02 disposition

# REOPEN_REQUIRED

The principal closure condition fails mechanically: an untrusted caller can select `INGEST_EXTERNAL_LANE_RESULT`, satisfy the self-consistency checks with a caller-authored ZIP/evidence/digest, and obtain canonical `bdb_audit_lane_result`, five `LANE_COMPLETED` records and `STAGE_COMPLETED`. Separate high/medium findings show package-byte substitution and raw-byte deletion after admission. The direct completion guard and passing regression suites do not protect against already accepted forged results. The previous closure conclusion is not supported by the exact target source.

Final status check: git status --short showed only these two untracked audit documents; no tracked diff remained and git diff --check returned no findings. Git emitted an access-denied warning for the ignored .codex-pytest-tmp/ directory; it was left untouched. HEAD/tree identity remained 7051472909075bb4c83a9a510e298fcca2a6bd5 / 3bc05685293d2fade72735e43a2ccc96be26f3f7.

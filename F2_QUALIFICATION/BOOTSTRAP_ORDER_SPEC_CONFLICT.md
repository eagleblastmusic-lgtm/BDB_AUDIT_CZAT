# F2-BOOTSTRAP-ORDER-002 — canonical bootstrap order

F2 is stopped before M5 acceptance. This is a normative content-order conflict,
not the old scheduling question. `F2-SCHEMA-ORDER-001` remains resolved by
CORR-1. No new schema/Registry exception is introduced.

## Exact opposing requirements

1. Data Contracts section 14.6, lines 823–842 requires the first canonical
   topological closure to contain CommandEnvelope → SourceGeneration →
   LEGACY_RAW_REF → assessments → selection → admission → genesis.
2. The exact Registry `global_invariants.initialization_bootstrap`, line 6309,
   repeats SourceGeneration → legacy raw in same-commit canonical content order.
3. The concrete pinned vector `FR03_BOOTSTRAP_SINGLE_COMMIT_ACCEPT` has
   `source_generation` before `legacy_raw_ref` in `input.closure` and expects
   ACCEPT. This report uses the actual vector input, not a reconstructed copy.
4. Data Contracts section 15.2, line 924 requires building the new-content DAG
   from typed content refs and executing Kahn with minimum
   `(kind, logical_id_or_empty, revision_digest)`. The stored sequence must
   equal that exact result byte for byte. ADR-006 section 4 likewise forbids
   an alternative canonical order.
5. Registry `contracts[kind=legacy_raw_ref]` is EXPLICIT_COMPLETE. Its ONLY
   material ref is `import_input_history_cut`, class HISTORY_INPUT, target
   `history_cut`. Data Contracts section 90, lines 3288–3302 agrees: the raw
   reference has no SourceGeneration content ref. Section 184 disallows
   silently expanding an EXPLICIT_COMPLETE ref contract via executable schema.

## Mechanical consequence

In a DAG constructed from those complete typed content refs, a new
`legacy_raw_ref` has no same-commit content dependencies. It is a zero-indegree
node from the beginning. `legacy_raw_ref` sorts before `source_generation`
on the first component of the mandated tie-break, regardless of IDs/digests.
Therefore Kahn cannot emit a new source_generation before that legacy node.
If source_generation has its own prerequisites it is emitted even later;
additional unrelated nodes do not change this forced relative order.

Thus the type-relative orders are incompatible:

```text
typed-content-only Kahn: legacy_raw_ref → source_generation
bootstrap contract:     source_generation → legacy_raw_ref
```

The graph is not cyclic. The problem is that two normative procedures demand
different canonical sequences, affecting CommitBody bytes and CommitHash.
Moving HistoryCut into the content DAG is forbidden. Adding an implicit
source→legacy precedence edge, adding a new raw-body ref, or changing the
tie-break would select new canonical semantics without an exact source rule.
Treating the bootstrap arrows as a non-ordering sketch would disregard the
Registry's explicit same-commit canonical-order invariant and the pinned
vector. None of these choices was implemented.

Required resolution is an authoritative definition of whether/how bootstrap
precedence edges augment the content-ref DAG, or a consistent revision of the
bootstrap ordering/Registry/vector contract. CORR-1 only resolves scheduling
and does not authorize changing these normative bytes.

## Reproduction

```powershell
.\.venv-f2\Scripts\python.exe -B tests/f2/diagnose_bootstrap_order.py
```

Expected diagnostic exit: **2**, `SPEC_CONFLICT`. This is not a failed product
test and not M5 PASS. It hashes the exact Registry, Data Contracts and Golden
Vectors, extracts the concrete vector and complete raw-ref contract, and
reports the forced relative-order contradiction. It creates no accepted
objects, synthetic H0, hashes of invented canonical objects, or runtime history.

`test_bootstrap_order_diagnostic.py` verifies reproducibility and that the
diagnostic command cannot be mistaken for a successful gate.

## Identities

| Exact source | SHA-256 |
|---|---|
| Data Contracts | `658f8866ca1a1330db9be582b13b47e87381de2208c53ee64ed9e47a8d3e15ee` |
| Registry | `5a89cfe26d927c9bf2638ad1e656b4ed810544f8d35e3e0ddf1365cd54b7343c` |
| Golden Vectors | `7bee0013d179adc8eba14d07c2c3ea159de0b8e37be9a9f6dcd55969550b7772` |
| ADR-006 | `df7e40fc062f5fcc2309276cc6fd4b529c060fb4f5f24fe39484eb66c0153dfa` |
| CORR-1 scheduling plan | `355a6359b3443c26a2ec1ef86f1118da3f32ab84f838ad8e8f0ef515947e4b04` |

## Scope status

PR-007 and PR-008 are implemented with tests and local commits. PR-009 contract
reconciliation found this blocker; PR-009 is not complete. PR-010–PR-019 have
not started. No M5/M7/M9/M11/M12 gate, quarantine qualification, full phase
golden qualification, F2 MilestoneAcceptance or qualification HistoryCut exists.
The diagnostic report is external non-authoritative evidence only.

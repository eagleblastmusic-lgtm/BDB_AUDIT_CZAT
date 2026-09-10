# M1 / PR-002 compatibility corpus

25 pinned fixtures: 8 valid, 17 invalid, no extras. No production code or M2
implementation. Raw payloads live under `raw/`, protected by repository `-text`.
The manifest records exact SHA-256, byte length, media type, relative path,
invocation context, observed legacy errors and separate independent expectations.

Run the complete acceptance check from the repository root:

```text
python -B tests/compatibility/verify_m1.py
```

This runs all compatibility tests and the exact frozen application's executable
self-test, then verifies retained `M1_QUALIFICATION.json` input hashes and gates.
Explicit pre-commit recording uses `--record` and writes commands, outputs, environment,
Git HEAD, exact qualification input hashes and the five gate values. It requires
working temporary-directory access for the original self-test. The tests disable
bytecode and pytest cache writes when run by this entrypoint.

`EXPECTATION_BASIS.md` records author-adjudicated positive/negative safety controls
before replay. `EXPECTATION_INPUTS.json` pins provenance and literal frozen
artifact-contract identities. These are test inputs, not new runtime policy.
The author qualification remains author-only; no independent foundation freeze
or independent human review is claimed.

## Replay routes

- BASE/E2 F1 and E2 F2: `validate_prior_handoff_bundle`, with the following
  consuming step and exact variant recorded in the manifest.
- BASE/E2 final: `validate_result_bundle` for the final step.
- Attestation and its three negative controls: `validate_attestation_bundle`.
- Continuation ticket: the original ticket-aware `validate_attestation_bundle`
  path with pinned `VALID_ATTESTATION` bytes. This qualifies ticket validation,
  not interactive payload delivery or UI persistence.
- Previous-prompt bundle: the original full `self_test`, injecting this fixture's
  bytes through `embedded_bytes` while preserving frozen expected metadata.
  Both byte-integrity and semantic checks must consume the injected fixture.

Independent tests inspect the material safety facts directly without calling
legacy validation: exact identities, retained raw prefixes, checkpoint sequence
and digest bindings, artifact families, transport hashes, reveal flags, ticket
bindings and predecessor prompt membership. Corpus semantic error labels are
separate from exact legacy error strings. There are no observed legacy-vs-safe
conflicts in these 25 controls; all bug/hardening flags are explicitly false.
This does not assert that legacy has no bugs outside this corpus.

## Scope and immutability

The source commit/tree identities consisting of `a`/`b` characters, audit IDs,
ledger and reports are deliberately synthetic. Positive controls qualify the
listed M1 artifact invariants, not factual findings, a real source checkout or
full audit conformance. Previous-prompt bytes are the exact frozen embedded
bundle; ZIP bytes are preserved rather than recompressed.

The builder refuses to overwrite an existing corpus. Tests reconstruct all 25
artifacts in memory and compare exact bytes with the pins. Do not update a fixture
or independent expectation to match a changed validator result. A future change
requires explicit versioned adjudication and a new qualification record. Tests
do not regenerate or update expected outcomes.

No commit is created by the acceptance script. The qualification binds the
working files by hashes in addition to the underlying Git HEAD. No remote action
is performed.

## F0 closeout

`F0_MILESTONE_ACCEPTANCE.json` is the pre-history equivalent of
`MilestoneAcceptance(F0)`. It binds the qualified parent commit, the complete
candidate Git object map (excluding the acceptance record itself), and exact
raw hashes of F0 inputs. The containing commit binds the acceptance record;
there is no circular requirement to put a commit's own SHA inside itself.
The record is author-qualified synthetic evidence and creates no runtime or
history authority.

After staging the completed M1/F0 inputs, `python -B
tests/compatibility/verify_f0.py --record` checks M0 identity and portability,
copy mutation detection, the full M1 verifier, baseline tests, and the unmodified
frozen executable self-test. Stage the generated acceptance record and commit.
After that commit, run:

```text
python -B tests/compatibility/verify_f0.py
```

The post-commit check verifies the exact commit subject and reruns all acceptance
commands without rewriting either qualification record. Run in an environment
with normal temporary-directory access; no temporary-directory adapter or
replacement legacy assertions are used. Unrelated untracked user files are
outside the acceptance subject and must not be staged.

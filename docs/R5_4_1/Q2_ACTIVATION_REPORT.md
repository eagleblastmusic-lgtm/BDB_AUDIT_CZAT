# Q2 / N5-N8 specification stop — 2026-10-06

Final gate: **SPEC_CONFLICT**. NF02 remains OPEN. AUTHOR_ONLY=YES; INDEPENDENT_FREEZE=FALSE. No Q2 activation or N5-N8 implementation was performed. N9-N11 were not started.

## Demonstrated conflict SC01

The exact qualified Data Contracts §95 (line 3554) states: “This candidate binds a finite bootstrap/NF02 subset: all other registered keys remain unbound and acceptance is forbidden.”

The qualified SchemaRegistry/2 has 39 canonical bindings and the catalog has 41 schemas including two transport schemas. Both `BDB_SCHEMA_REGISTRY::lane_completion/1` and `BDB_SCHEMA_REGISTRY::stage_completion/1` are absent from the bindings, executable catalog and machine manifest. Both kinds are registered, with mandatory L3-L7 checks, but semantic registration is insufficient for acceptance.

User section 21 requires the full accepted authority chain through LaneCompletion and StageCompletion. Qualified Roadmap N7 (line 2943) explicitly requires positive `evidence -> later result -> required outputs/completion` tests. Data §192 E.4 step 10 also identifies distinct subsequent qualification decisions. A negative unbound-schema rejection can preserve safety, but cannot evidence this required positive completion chain.

Creating new completion schemas, extending the exact SchemaRegistry, or selecting generated/old/fallback schema bytes would violate the requested exact qualified context. Roadmap N3 (line 2890) requires returning to N1 with a new manifest/readback and external approval when approved machine bytes change. Broader schema binding language in §192.1 does not make unqualified bytes part of the currently exact qualified set. This coding task explicitly forbids editing that candidate or qualification record. No local implementation repair can add the missing qualified authority while preserving its exact identity.

Required owner/specification action: resolve this acceptance scope conflict explicitly. A complete positive chain needs separately prepared and exact qualified schema/binding closure; alternatively, a narrower implementation contract must explicitly defer successful completion and change the governing N7 acceptance requirement. Neither change is inferred in this run.

## Verified identities

- `manifest_raw_digest`: `15415abd7d2601698c6ff664a93077213e81575272a213c4511f6082c9d8fdef`
- `normative_candidate_set_digest`: `d11f751f729605f94bdd11dc033f700f895ee4f7091f2150424023fd4efcaf3b`
- `machine_candidate_set_digest`: `640b76678b48d1902c16775c660709101f1a0708805b7608f822af7a0604f682`
- `registry_raw_digest`: `1b9d17c46843a91053036f0370d4419dac87ce5978df61b0dc922e0e40237e2c`
- `schema_registry_object_digest`: `de514548328391f271dac2f6b253b8d47ac8d6e5406e6e0781a2bfb18c9cbc1e`
- `golden_raw_digest`: `4cebb462b647c69e6348546180900ac2a3c4806a5bf1716e5269b70ed94edb17`
- `qualification_record_raw_digest`: `3a3754d4eebac944ad40c7a49cf6db882bbbde6c55c7f14784961dbfc4df8b90`

## Commands and preservation

`python docs/R5_4_1/tools/verify_candidate.py`: exit 0, 3.3196113 seconds, PASS_ARTIFACT_SELF_AUDIT_N1_N4_ONLY; 120 exact readbacks, zero drift. Runtime NOT_RUN. The verifier also checked source/protected tracked bytes, main and predecessor preservation. Warning: ignored `.codex-pytest-tmp/` cannot be read; this is not the specification blocker.

Independent hashlib manifest/set/Registry/SchemaRegistry/Golden/qualification comparisons: PASS. Static intersection of Registry keys with qualified bindings/catalog/manifest: completion keys registered, both unbound. This is a static diagnostic, not a runtime Golden vector outcome.

Source HEAD `b7051472909075bb4c83a9a510e298fcca2a6bd5`; tree `3bc05685293d2fade72735e43a2ccc96be26f3f7`; branch `fix/nf02-lane-result-authority`. Existing dirty NF02 source/tests were preserved. No source change, commit, push, checkout or ref mutation. Four external reports are the only task changes. Full source raw/blob pins, qualification identities and schema mappings are recorded in NF02_N5_N8_VERIFICATION.json.

## Gate limits

Q2 runtime activation: NOT_STARTED_SPEC_CONFLICT; no runtime activation identity. Required Q2 negative controls: NOT_RUN. N5-N8: NOT_STARTED. Crash/restart, concurrency, migration and canonical negative snapshots: NOT_RUN, no canonical operation attempted. Ruff/Mypy/affected and full pytest/build/artifact validator: NOT_RUN because implementation was stopped on normative conflict; no artifact digest. No runtime PASS, implementation readiness or NF02 closure is claimed.

The full narrative baseline read was not completed after the material conflict was demonstrated. This report does not represent a complete candidate audit. The fresh artifact verifier PASS cannot substitute for Q2 runtime evidence.

N9 entry requires resolved exact authority/scope, completed baseline reading, Q2 activation PASS, implemented N5-N8, and all mandatory implementation checks. See NF02_N5_N8_TEST_MATRIX.md for every runtime vector's explicit NOT_RUN status.

Final closeout: `git diff --check` exit 0; `git status --short` exit 0 (same ignored scratch warning); no frozen legacy paths in `git diff --name-only -- legacy/v1_4_4/`. Source and protected baseline hashes rechecked unchanged. The matrix separates 149 runtime vectors NOT_RUN from 18 external governance vectors executed PASS by the artifact verifier.

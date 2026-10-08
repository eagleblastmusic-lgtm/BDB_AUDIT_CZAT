# R5.4 artifact self-audit — N1–N4

Result: **PASS_ARTIFACT_SELF_AUDIT_N1_N4_ONLY**. No runtime qualification is claimed.

Manifest RawDigest: `d2f38cfad4a0d4e3ae96f179addb6fd7ad817250f4998968eb5a01487dd0e3cd`. Normative set: `9488a12d644f8ac17bba737af18f3bd1d6147a7051b94ead9c89923b626b2a02`. Machine set: `a2e094538948c02f78f07265a3a0abeab90b06c0d21a126294ce97f68b7d92ce`.

Local disk readback: 117 files (10 normative, 107 machine), zero mismatches. Readback RawDigest `a4c860f6eab7c5c23afd97aecabe22fac80deae12ab397f96d6bc6509e7b14d3`. Self-audit JSON RawDigest `958d5de0f24cc7a4d6f4b1a40693f7a19137236ceecffbf7bd236566af84cc00`.

- source/HEAD/tree/branch/main/predecessor/proposal and pre-existing worktree bytes unchanged
- complete disjoint manifest inventories, exact raw readback and both canonical set preimages
- all 110 predecessor rows exact; four additions only; roles/reference classes/order domains preserved
- 41 executable schemas meta-valid; exact bytes/digests/length/$id/dialect/local dependency closure; explicit ref parity
- validator backend installed versions: {'jsonschema': '4.25.1', 'attrs': '26.1.0', 'jsonschema-specifications': '2025.9.1', 'referencing': '0.37.0', 'rpds-py': '2026.6.3'}
- 55 full synthetic/root objects schema-valid and independent ObjectDigest/typed ref/profile identity checks
- 39 exact SchemaRegistry/2 bindings; external schema root and all eight installation pins; normative set pin; no installation performed
- full fixture typed-ref hash DAG acyclic; assignment/binding/evidence/result exact relation; distinct prior commits
- seven modeled immutable history closures/parent chain/receipts and NF02 PRIOR_ACCEPTED_ONLY boundaries consistent
- known-answer ObjectDigest preimages/raw ZIP hashes/transport schemas/member bytes/semantic checksum and repack raw separation
- 117 inherited exact +32 complete proposal IDs and adversarial variants; negative no-state-mutation; runtime NOT_RUN

Schema/meta/hash/fixture checks above are artifact checks. All 149 runtime vectors are NOT_RUN. Existing remediation test evidence is not reused as R5.4 runtime evidence. External qualification and actual installation remain pending.

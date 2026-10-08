# R5.4.1 fresh Q1 qualification

Final gate: **R5_4_1_AUTHOR_QUALIFIED_FOR_IMPLEMENTATION**.

Author-only assurance; independent_assurance=false; foundation_spec_baseline_frozen=false. Old invalid qualification remains NO_VALID_QUALIFICATION. New record has a new ID and exact digest. Owner authority is the direct correction/fresh-Q1 order with explicit prior author-only risk acceptance, scoped to the proven minimal successor delta. Q2 and N5–N11 are NOT_STARTED. Runtime tests/vectors NOT_RUN. NF02 closure is not claimed.

## Exact identities

```json
{
  "predecessor": {
    "invalid_qualification_raw_digest": "c63adbccf547428a4bbe27ed885c784546a8ef005615157b213791aea653b6fd",
    "invalidation_raw_digest": "ba9d28d536e5577c2f39e6c9fe55dbfd30416eab2afc52a14b57d9c1752d30cd",
    "machine_candidate_set_sha256": "a2e094538948c02f78f07265a3a0abeab90b06c0d21a126294ce97f68b7d92ce",
    "manifest_raw_digest": "d2f38cfad4a0d4e3ae96f179addb6fd7ad817250f4998968eb5a01487dd0e3cd",
    "normative_candidate_set_sha256": "9488a12d644f8ac17bba737af18f3bd1d6147a7051b94ead9c89923b626b2a02",
    "revision": "R5.4"
  },
  "manifest_raw_digest": "15415abd7d2601698c6ff664a93077213e81575272a213c4511f6082c9d8fdef",
  "normative_candidate_set_digest": "d11f751f729605f94bdd11dc033f700f895ee4f7091f2150424023fd4efcaf3b",
  "machine_candidate_set_digest": "640b76678b48d1902c16775c660709101f1a0708805b7608f822af7a0604f682",
  "registry_raw_digest": "1b9d17c46843a91053036f0370d4419dac87ce5978df61b0dc922e0e40237e2c",
  "golden_raw_digest": "4cebb462b647c69e6348546180900ac2a3c4806a5bf1716e5269b70ed94edb17",
  "schema_registry_object_digest": "de514548328391f271dac2f6b253b8d47ac8d6e5406e6e0781a2bfb18c9cbc1e",
  "governance_schema_raw_digest": "623dd1183213e8408a6155e2a3bf7cf5af4d006b9f6ca915e5502b321a988a24",
  "qualification_record_raw_digest": "3a3754d4eebac944ad40c7a49cf6db882bbbde6c55c7f14784961dbfc4df8b90",
  "readback_raw_digest": "387bd2ef77d3c3d57e9e571d30b27c8f3b7e92f5761c949e93bfcb72d971839e",
  "self_audit_raw_digest": "ea2b6487becdb3983d403da798f9b9d13cf956a68f9d122ca1880e8f88e3d962"
}
```

## Fresh checks

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
- entire R5.4 subtree (155 files), source and owner task unchanged; invalid prior qualification excluded
- minimal delta: 8 candidate files; all other candidate bytes exact; runtime Registry/SchemaRegistry/schema bytes unchanged
- one parsed closed external governance schema; narrative parity; one scalar verdict; manifest-derived explicit counts; no self-hash cycle
- 18 fresh governance vectors executed PASS; inherited 149 runtime vectors NOT_RUN

Readback: 10 normative + 110 machine = 120; zero mismatches. Manifest-derived counts; 18 executed external governance vectors PASS. All 149 inherited runtime vectors NOT_RUN.

Commands: `python docs/R5_4_1/tools/verify_candidate.py`, `python docs/R5_4_1/tools/finalize_delivery.py`, `python docs/R5_4_1/tools/qualify_exact_candidate.py` — PASS. `git diff --check` — exit 0. Full source/status/preservation pins are in evidence and R5_4_1_Q1_RESULT.json.

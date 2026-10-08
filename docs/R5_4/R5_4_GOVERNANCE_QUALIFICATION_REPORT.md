# R5.4 exact-candidate governance qualification — FAILED

Q1 gate: **R5_4_QUALIFICATION_FAILED**. Final task gate: **SPEC_CONFLICT**. Q2 and N5–N8 have not started.

All four user-pinned identities match. Structural/hash/schema self-audit and fresh readback passed, but those checks do not establish governance narrative parity. The exact candidate has two incompatible mandatory predicates for the same successor AuthorBaselineQualificationRecord/2. Owner author-only authorization was obtained explicitly and remains recorded; missing permission is not this blocker.

| Normative source | Requirement | Conflict |
|---|---|---|
| Data §187.2, line 5205 | `author_verdict = R5_4_N1_N4_AUTHOR_SELF_AUDIT_PASS`, expressly “successor governance record/2 only” | Cannot equal the different /2 token below |
| Data §192.2, line 5567 | `author_verdict=R5_4_AUTHOR_NORMATIVE_FINAL_SELF_AUDIT_PASS` | One scalar verdict cannot satisfy both |
| Data §187.2, line 5220 | `readback_verified_file_count` equals normative manifest file count | Required value 10 |
| Data §192.2, line 5567 | Same count includes all normative and machine entries | Required value 117 |

The §187.2 verdict line is already explicitly marked successor /2; it cannot be silently treated as historical record/1. No explicit reconciliation of these /2 requirements occurs in the frozen text. Choosing a preferred predicate or accepting an array/new field instead of the required scalar would silently redefine the contract. The instruction permits qualifying these exact bytes and forbids automatically correcting the candidate.

Normative set `9488a12d644f8ac17bba737af18f3bd1d6147a7051b94ead9c89923b626b2a02`; machine set `a2e094538948c02f78f07265a3a0abeab90b06c0d21a126294ce97f68b7d92ce`; manifest RawDigest `d2f38cfad4a0d4e3ae96f179addb6fd7ad817250f4998968eb5a01487dd0e3cd`; SchemaRegistry ObjectDigest `de514548328391f271dac2f6b253b8d47ac8d6e5406e6e0781a2bfb18c9cbc1e`. Candidate/Data raw SHA-256 `0294cf6c904d0a5aa5f1af36292739b494280bff0b9d16bf6d618d0e6f37d73d`. No drift.

Current HEAD `b7051472909075bb4c83a9a510e298fcca2a6bd5`, tree `3bc05685293d2fade72735e43a2ccc96be26f3f7`, branch `fix/nf02-lane-result-authority`. Source/predecessor pins remain unchanged. Full initial git commands are in `evidence/qualification/Q1_SOURCE_IDENTITY.json`.

## Fresh checks

- `python docs/R5_4/tools/verify_candidate.py` — exit 0, artifact self-audit only.
- `python docs/R5_4/tools/finalize_delivery.py` — exit 0, fresh evidence; candidate bytes not generated/edited.
- 117 candidate readbacks, zero mismatch; 41 schemas, 39 bindings; 149 vectors inventoried, runtime execution NOT_RUN.
- `python docs/R5_4/tools/qualify_exact_candidate.py` — final strict run exit 1; both normative conflicts detected before any new qualification record is written.
- Strict-check implementation was corrected to stop before record emission on these conflicts; the original record remains preserved and is invalidated externally. This repair does not change normative predicates.

## Correction of premature record

The initial author qualification was emitted before this parity check was complete. Its RawDigest `c63adbccf547428a4bbe27ed885c784546a8ef005615157b213791aea653b6fd` is preserved; its YES/PASS claim is invalid and must not be used. External validity assessment `evidence/qualification/AUTHOR_BASELINE_QUALIFICATION_R5_4_INVALIDATION.json`, RawDigest `ba9d28d536e5577c2f39e6c9fe55dbfd30416eab2afc52a14b57d9c1752d30cd`, records the rejection and effective NO_VALID_QUALIFICATION. Initial checks/report remain forensic evidence, not authority. No independent assurance, freeze, installation or campaign state change occurred.

## Required resolution

A separately authorized exact successor/correction must specify one /2 verdict token and reconcile total/normative/machine readback fields/counts consistently across §187.2, §192.2 and governance artifacts. This changes candidate bytes and therefore requires a new manifest/set identity and fresh Q1 qualification. This task does not silently amend the pinned candidate or assume authorization to revise it. The owner’s author-only decision does not itself resolve these contract predicates.

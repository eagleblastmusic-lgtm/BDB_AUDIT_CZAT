# M1 independent expectation adjudication

Scope: synthetic artifact safety controls, not real audit/release qualification.
Authority: CODEX_M1_PR002_CONTEXT_R5_3.md B (Roadmap 7-9), C (Migration 4.1-4.3), D (Test Plan 9, 10, 19-22). The original validators are preservation evidence only.
The fixture author manually adjudicates ACCEPT for consistent positive controls and REJECT for the specific violated property below. Error families here are corpus semantic labels, not new runtime codes or compatibility policy. Byte manifests are rebuilt after intentional semantic mutations except INVALID_HASH_MANIFEST. No expected result is copied from replay.
Literal legacy payload identities may be obtained from frozen embedded contracts; the safety rule is independently exact equality/membership, not whatever the validator accepts.

## VALID BASE F1

BASE checkpoint: matching source/run/audit identities, exact retained prefix, readback and digest bindings before canonical reveal.

Decision: ACCEPT; family: NONE. Positive control: self: consistent identities, bindings and required family. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## VALID BASE FINAL

BASE final family with F1 retention and no previous-report or F2 artifacts.

Decision: ACCEPT; family: NONE. Positive control: self: consistent identities, bindings and required family. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## VALID E2 F1

E2 F1 checkpoint with matching identities and retained prefix before previous-prompt reveal.

Decision: ACCEPT; family: NONE. Positive control: self: consistent identities, bindings and required family. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## VALID E2 F2

E2 F2 checkpoint retains the exact F1 prefix and F2 snapshot after previous-prompt reveal.

Decision: ACCEPT; family: NONE. Positive control: self: consistent identities, bindings and required family. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## VALID E2 FINAL

E2 final family retains both checkpoints, snapshots, final readback and predecessor lineage.

Decision: ACCEPT; family: NONE. Positive control: self: consistent identities, bindings and required family. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## VALID ATTESTATION

Transport-only attestation declares no early exposure, generation mix, or substitute checkpoint; payload identities match pinned canonical inputs.

Decision: ACCEPT; family: NONE. Positive control: self: consistent identities, bindings and required family. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## VALID CONTINUATION TICKET

Ticket binds the same variant, step, fallback, attestation state and exact prior-handoff identity.

Decision: ACCEPT; family: NONE. Positive control: VALID_ATTESTATION. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## VALID PREVIOUS PROMPT BUNDLE

Exact embedded predecessor prompt bytes, membership and consumer/predecessor identities; cross-step outer digest references agree.

Decision: ACCEPT; family: NONE. Positive control: self: consistent identities, bindings and required family. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## WRONG VARIANT

Change only RUN_MANIFEST.variant_id; checkpoint retains the positive control identity.

Decision: REJECT; family: VARIANT_IDENTITY. Positive control: VALID_BASE_F1. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## WRONG RUN ID

Change only RUN_MANIFEST.audit_attempt_id; checkpoint retains the positive control identity.

Decision: REJECT; family: RUN_IDENTITY. Positive control: VALID_BASE_F1. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## WRONG AUDIT ID

Change only RUN_MANIFEST.audit_request_id; checkpoint retains the positive control identity.

Decision: REJECT; family: AUDIT_IDENTITY. Positive control: VALID_BASE_F1. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## WRONG SOURCE SHA

Manifest source_sha contradicts checkpoint/readback; artifact hashes are recomputed.

Decision: REJECT; family: SOURCE_COMMIT_IDENTITY. Positive control: VALID_BASE_F1. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## WRONG SOURCE TREE

Manifest source_tree contradicts checkpoint/readback; artifact hashes are recomputed.

Decision: REJECT; family: SOURCE_TREE_IDENTITY. Positive control: VALID_BASE_F1. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## CONFLICTING DUPLICATE

Conflicting evidence copy of the root source readback.

Decision: REJECT; family: CONFLICTING_MEMBER. Positive control: VALID_BASE_F1. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## INVALID HASH MANIFEST

One manifest digest is all zero; payload bytes unchanged.

Decision: REJECT; family: ARTIFACT_HASH_IDENTITY. Positive control: VALID_BASE_F1. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## MISSING SNAPSHOT

Required retained F1 snapshot absent, with transport hashes otherwise consistent.

Decision: REJECT; family: RETAINED_SNAPSHOT_REQUIRED. Positive control: VALID_BASE_F1. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## BROKEN LEDGER PREFIX

Leading whitespace preserves parsed ledger records but breaks exact retained raw prefix; digest record updated.

Decision: REJECT; family: RAW_LEDGER_PREFIX. Positive control: VALID_BASE_F1. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## BAD F1 CHECKPOINT

Checkpoint declares sequence end 99 although retained ledger ends at 1 or 2; hashes consistent.

Decision: REJECT; family: CHECKPOINT_SEQUENCE_BINDING. Positive control: VALID_BASE_F1. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## BAD F2 CHECKPOINT

Checkpoint declares sequence end 99 although retained ledger ends at 1 or 2; hashes consistent.

Decision: REJECT; family: CHECKPOINT_SEQUENCE_BINDING. Positive control: VALID_E2_F2. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## EARLY REVEAL

Attestation explicitly declares staged_payload_semantics_exposed_before_attestation=true; all other positive-control facts unchanged.

Decision: REJECT; family: REVEAL_ORDER. Positive control: VALID_ATTESTATION. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## SOURCE GENERATION MIX

Attestation explicitly declares source_generations_mixed=true; all other positive-control facts unchanged.

Decision: REJECT; family: SOURCE_GENERATION_ISOLATION. Positive control: VALID_ATTESTATION. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## SUBSTITUTE F2

Attestation explicitly declares substitute_f2_created=true; all other positive-control facts unchanged.

Decision: REJECT; family: CHECKPOINT_NON_SUBSTITUTION. Positive control: VALID_ATTESTATION. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## UNSAFE ZIP PATH

Traversal member must be rejected without extraction.

Decision: REJECT; family: ZIP_PATH_SAFETY. Positive control: VALID_BASE_F1. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## DUPLICATE MEMBER

Two physically distinct ZIP entries have the same exact name and bytes.

Decision: REJECT; family: ZIP_MEMBER_UNIQUENESS. Positive control: VALID_BASE_F1. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

## WRONG ARTIFACT FAMILY

F1 handoff submitted where a final bundle is required; final report/outcome/readback are absent.

Decision: REJECT; family: FINAL_ARTIFACT_FAMILY. Positive control: VALID_BASE_FINAL. Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.

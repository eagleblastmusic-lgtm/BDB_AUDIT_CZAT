# Source authority branch parity

Full authoritative Data section 8, including 8.1–8.4, distinguishes authorized Git from authorized snapshot identity. SourceGeneration has exactly one repository/snapshot authority reference. The branch must agree with the exact SourceIdentity mode, in addition to complete reference equality. Equal authority digests do not make the two branches interchangeable.

The source-generation pre-durability validator now requires repository_authority_ref for AUTHORIZED_GIT and snapshot_authority_ref for AUTHORIZED_SNAPSHOT. Unknown modes and a missing matching branch reject with SOURCE_IDENTITY_CONFLICT. Existing schema XOR rejects both branches. Exact target resolution, manifest/profile/authority comparison and alias uniqueness remain required; none of these equalities authenticates an external source authority.

The coordinator previously selected snapshot identity for a campaign without a Git target but always emitted repository_authority_ref. Its generation producer now selects the corresponding branch. The shared F2 bootstrap fixture had the same contradiction and is corrected to snapshot_authority_ref. Original fixture and producer bytes are retained in checkpoint_history/source_authority_mode_20261008; the authorized delta pins their original and current bytes.

Controls cover a valid and a substituted branch for each mode, and durable snapshot branch substitution at bootstrap and against prior accepted identity. Rejected substitutions preserve head, commits and receipts, including reopening. These supplement manifest, profile and authority substitution tests; they do not replace independently installed profiles, actual trusted source readback, successor schema qualification or complete instance-DAG verification.

The initial strict-guard regression exposed the contradictory fixture and coordinator. Those failed runs are diagnostic evidence of the cause, never acceptance evidence. The previous 622-test broad run predates this branch repair. Fresh affected and broader runs are required, with exact changed inputs captured by the runtime harness. No candidate, installation, Q1/Q2 or NF02 gate is promoted by this correction.

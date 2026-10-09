# Data 8.3 source alias runtime review

The accepted source generation history and all same-closure source generation bodies are checked before durability. An alias binds one entire SourceIdentity reference, and an exact SourceIdentity target binds one alias. Reference class metadata is excluded from target identity. Representation changes do not authorize remapping. The current registered contracts provide no explicit import-alias relation.

The durable bootstrap regression supplies conflicting aliases for one exact identity, verifies SOURCE_IDENTITY_CONFLICT, verifies an empty head/history/receipt, and retries the valid closure successfully. Ten targeted regressions pass, including nested schema reference keys, exact schema substitution, and unchanged archive-independent alias behavior.

Structured schema_revision_ref values are encoded with existing canonical_bytes only for in-memory equality keys. Object bytes, hashes and persisted references remain unchanged. Existing type errors were repaired with annotations, narrowing, cast and setattr without changing runtime decisions.

The prior broad run design/source_instance_readback/runtime_runs/1791462923269077700.json exited zero with no input drift. It precedes the structured reference fix and is historical evidence for that implementation only. A new affected broad run is in progress. This review does not establish successor schema binding, trusted installation context, full per-kind semantic parity, candidate qualification, Q1/Q2, or N5â€“N11 completion.


Follow-up Data 192.1 integration: finalization reference sorting now uses the same full canonical schema key. Assurance projections use canonical schema bytes and include digest_profile in deduplication, instead of str(dict). Regression checks independently reordered schema mapping fields, full schema substitutions, digest profile substitutions, and order-independent finalization ref sets. Thirteen targeted regressions and mypy for both modified modules PASS. No wire serialization changed. The preliminary broad session 41440 was deliberately interrupted after the additional dependent repairs were identified; it is not terminal evidence. Replacement broad session 79166 is in progress.

Runtime evidence now snapshots the harness itself before execution, imported test helper/fixture files, pytest configuration and the entire source/build/test Python file inventory. Changed, removed or added relevant files invalidate terminal reuse. This protects diagnostic reproducibility and does not create runtime or qualification authority.


Four additional real SQLite controls establish the prior-history case: a second alias for a SourceIdentity already retained in accepted history rejects with SOURCE_IDENTITY_CONFLICT; head, commits and missing command receipt are unchanged; reopening retains the original history; exact original bootstrap retry returns the same original receipt. These supplement the same-closure transaction regression. Evidence: SOURCE_ALIAS_PRIOR_DURABILITY_CONTROLS.json. The controls use historical registered fixture schemas and establish the implemented guard, not successor installation qualification.


Further real SQLite probes found SourceGeneration could substitute manifest, identity profile or source authority while preserving its SourceIdentity ref. Each substitution was actually accepted at seq=2 in isolated diagnostic databases. The durable hook now resolves that exact SourceIdentity and compares all three complete references, excluding only Registry ref_class annotations. It reconstructs prior retained identity bytes and checks its full TypedRef. Nineteen focused regressions now PASS, including all three substitutions both in bootstrap content and against prior accepted identity, with unchanged head/commits/receipt after rejection. This equality guard does not infer independent source/profile authority, completeness or installation qualification. Those remain separate prerequisites.

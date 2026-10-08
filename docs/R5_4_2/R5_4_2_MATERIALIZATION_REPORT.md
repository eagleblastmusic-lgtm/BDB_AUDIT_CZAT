# R5.4.2 materialization report — fail-closed semantic preflight

Final gate: **SPEC_CONFLICT**. M1 stopped before candidate bytes; M2–M6 NOT_EXECUTED. Q2 and N5–N11 NOT_STARTED. NF02 OPEN. No PASS or qualification record emitted.

Owner approval is valid for its exact pinned scope. Full approved documents/graph/inventory parsed/read; eight approved input pins match. R5.4.1 exact readback: 120 entries, zero mismatch. Required git status/branch/HEAD/tree/log captured before mutations. Existing dirty runtime, legacy, main and all predecessor bytes retained. Source/protected full RawDigest pins are in fresh SELF_AUDIT; prior stop diagnostics copied byte-for-byte to materialization_attempts/2026-10-06-semantic-preflight/prior_diagnostics. The approved graph/owner package/proposals/reports are unchanged.

## Blocking approved-contract representation gap

Owner Decision Package line 34 requires: “an accepted wrapper must have an explicit closed body/schema and raw reference”. Lines 26 and §4a forbid unlisted fields and defer other unbound bodies to their exact normative Data section. `surface_collector_record/1` is registered RAW_EVIDENCE, unbound, and reached by `surface_record.provenance_refs`, `scope_state_record.basis_refs`, `inventory_revision.assigned_input_refs`, `input_disposition_record.assigned_input_ref`. These edges require exact typed registered targets.

Data §30 (lines 1462–1489) specifies CollectionRun fields but no RawRef or selected raw-backed wrapper body. The approved graph node has `qualified_registry_row.material_refs=[]`, `proposed_material_ref_completion=[]`, and no `schema_deferred_body_completion_decisions[surface_collector_record/1]`. Architecture §14.1 and Roadmap §§47–48 describe collector accounting, not this identity/retention/reference representation. The raw/typed wrapper distinction was made explicit for observation, report receipt and artifact hash manifest, but not this reachable collector target.

A generator would have to add a raw-reference field/material contract, redefine how CollectionRun body maps to an accepted wrapper, or change consumers from TypedRef to raw representation. Those affect canonical body/identity/authority/refs and are not delegated schema-formatting choices. No alternative is selected here. Task §4 requires STOP SPEC_CONFLICT when a new semantic decision is required. No local runtime schema or overlay is used to supply authority.

The previous design gate overstated semantic completeness: a finite graph queue is not proof of complete raw/typed body/profile semantics. Its 131=110+21 and 39/92 numbers remain exact graph enumeration/predecessor-binding counts, but semantic-complete=131 is not reconfirmed. Approval does not manufacture missing contract text. The approved source remains immutable evidence; this new stop diagnostic identifies the deficiency without rewriting it.

## Actual materialization/qualification numbers

Approved required schema keys: 131. Bound predecessor keys: 39; missing against predecessor: 92. Materialized R5.4.2 kinds/schemas/bindings: zero; no successor candidate exists. Full successor semantic/reference/profile closure NOT_PROVEN; no assertion of zero semantic gaps. Normative/machine candidate-set digests, Registry/SchemaRegistry/Golden successor identities and qualification digest: NOT_CREATED. The stop notice named CANDIDATE_MANIFEST is not a candidate identity. Successor readback NOT_RUN; empty notice entries do not constitute successful readback. R5.4.1 remains VALID AUTHOR-QUALIFIED PREDECESSOR; no successful successor qualification exists to supersede it for implementation.

## Verification / required decision

`python docs/R5_4_2/tools/materialization_preflight.py`: expected exit 2, SPEC_CONFLICT before candidate/qualification emission. `python -m ruff check docs/R5_4_2/tools/materialization_preflight.py`: PASS, exit 0. Exact environment/duration/tool digest/preservation evidence is in SELF_AUDIT. Runtime vectors NOT_RUN. Fresh complete Q1 NOT_RUN because semantic prerequisite failed; this preflight is not a complete Q1 qualifier. Q1 reachability predicate RUNTIME_SCHEMA_REACHABILITY_COMPLETE is unproven and cannot emit a PASS record.

Required owner design completion: exact `surface_collector_record/1` canonical/raw representation, closed body, raw-reference retention/profile identity, material refs/classes/cardinalities/history rules, and corresponding typed consumer bindings. Choosing the representation is outside this materialization instruction; other approved models are not reopened. A subsequent closure/parity review must establish that this completion introduces no further unresolved dependencies before materialization resumes.

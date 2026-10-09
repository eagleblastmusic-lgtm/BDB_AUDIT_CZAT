# BDB Audit v2 — R5.4.2 Optimized Execution Plan

**Revision:** OPT-1 / 2026-10-09  
**Purpose:** continue the existing autonomous NF02 closure from the published OD-038 checkpoint, remove duplicated analysis and avoid an indefinite semantic-review loop without weakening canonical assurance.  
**Execution branch:** `codex/r5-4-2-current-state-20261009` (checkpoint commit `bb3834f45181a2bac3dce07c04c3a9b9c1169285`)  
**Repository:** `eagleblastmusic-lgtm/BDB_AUDIT_CZAT`  
**Historical predecessor:** R5.4.1 author-qualified; older R5.3/R5.3.1 remains immutable.  
**Authority:** This is an **execution-plan optimization**, not a normative override and not a qualification certificate. Governing approved contracts, semantic invariants, registry/schema bindings, exact hashes, and the existing owner-delegated decisions remain authoritative. Where this plan differs from a genuinely normative prerequisite, retain that prerequisite and record the conflict; do not manufacture a PASS.

## 0. Verified starting state and what must NOT be repeated

From published `docs/R5_4_2/autonomous_2026_10_07/CONTINUATION_REPORT.md` and `RESUMED_WORK_CHECKPOINT.json`:

- Owner-delegated decisions through **OD-038** already exist. Do not reopen them unless an actual proof or source contradiction requires it.
- **131 active canonical schema keys**, **127 external profiles**, **69 conditional/cross-object obligations** in the inventory.
- **275 exact build-time schema inputs** already materialized/read back: 131 canonical-body, 127 external-profile and 17 raw-payload schemas. Also retained: candidate input for 131-key Registry and raw-backed 131-binding SchemaRegistry. These are **not** a frozen, qualified successor.
- Draft verification: **42 commands PASS, zero recorded input drift**; later application source snapshot: **8 targeted PASS + Ruff PASS**, with the wider follow-up verification not yet completed. Existing runtime records show **240 + 475 + 9 test PASS** over specified snapshots; they are **not** successor qualification evidence.
- Current semantic queue: **131 pending full-parity dispositions** (source paragraphs retained, not proof of semantic review). `fixed_point_reached=false`. Q1/Q2/N5–N11 NOT_STARTED as formal gates, NF02 OPEN.
- Open PR **#45** preserves this **unfinished checkpoint**. It is not merged into `main`. Its CI candidate-qualification job was cancelled and clean-room rebuild was skipped; neither is PASS.

**Rule:** Reuse exact retained data and evidence where its producer, bytes, full relevant inputs, tool version and environment requirements are still bound. Never regenerate or rerun a complete suite just because another unrelated diagnostic record was appended. Never reuse evidence if a relevant input changed or its binding cannot be established.

## 1. Optimize for the critical path rather than number of checks

**Priority 1:** the smallest complete set of **normatively required dependencies** for Q1/Q2 and NF02 runtime acceptance, not the smallest number that makes an artificial gate green.  
**Priority 2:** qualify N5–N10 with independent adversarial evidence.  
**Priority 3:** complete N11 end-to-end lifecycle as a **separately reported gate**; it remains part of the agreed final objective and must not be silently deleted.

Distinguish three independent concepts:

1. **Prepared candidate input** — exact draft file exists and passes syntax/integrity checks, **not** installed or qualified.
2. **Qualified foundation** — semantic/source/body/profile/predicate parity, mandatory reachability, schemas, negative fixtures, exact readback and governance pass.
3. **Qualified runtime** — implementation actually enforces authoritative producer, chronology, raw identity, admission and no-mutation rejection; attack tests pass.

No draft PASS is relabelled as any of (2) or (3).

## 2. Finite work packages from the OD-038 checkpoint

### OPT-0 — Pin the published checkpoint (one-time)

**Do:** Read active `CONTINUATION_REPORT.md`, `RESUMED_WORK_CHECKPOINT.json`, `ISSUE_REGISTER.json`, `OWNER_DELEGATED_DECISION_REGISTER.md`, `AUTHORIZED_IMPLEMENTATION_DELTA.json`, `DRAFT_VERIFICATION.json`, candidate input digests and PR #45 SHA. Record working branch/HEAD/tree/dirty files and protect unrelated changes. Establish the newest available local work as input; published PR is a checkpoint, not automatically the latest local edits.

**Do not:** restart semantic discovery from R5.3, replay all OD decisions, regenerate the 275 schemas without input drift, or re-import the ZIP as authority.

**Exit:** one accurate `ACTIVE_EXECUTION_STATE.md` with input identities, which results are reusable, which are stale, and the exact next command. No new spec claim.

### OPT-1 — Separate mandatory NF02/Q1 dependency closure from full-lifecycle backlog

**Do:** Generate a deterministic, evidence-backed **bidirectional graph** from the qualified Registry, proposed successor Registry/SchemaRegistry, actual schema refs, runtime acceptance consumers, producer/trust roots, external profiles, HistoryCut, transitive content/raw refs and required fixture dependencies. Seed at least:

- assignment / attempt / package-byte authority / immutable package binding;
- result-slot and independent admission evidence / lane result;
- lane/stage completions and applicable FSM/HistoryCut/producer gates;
- trusted raw durability, canonical event/command, Registry, exact SchemaRegistry pin and installer roots;
- the schema/profile dependencies that mandatory Q1, Q2, N9 and N10 actually require.

Classify each of the 131 kinds as:
- **A — changed/new:** own body/reference/role/producer/profile/predicate/identity/lifecycle changed;
- **B — impacted:** unchanged own contract but exact upstream/downstream binding, version, installation or guard affected;
- **C — proven unchanged:** byte-identical binding and no affected transitive authority dependency; may reuse **valid exact predecessor evidence** where allowed;
- **D — outside immediate NF02 critical path:** do not expand design merely because discoverable, **unless** it is a mandatory Q1/Q2 materialization/installation/qualification dependency.

Create `NF02_Q1_IMPACT_MATRIX.json`: one row per active key, classification, reason, exact refs, applicable reviews/vectors and evidence hash, reusable vs rerun status. **No kind simply disappears.** Mandatory full 131-key coverage, if established by governing Q1, remains mandatory; optimize how it is proven, not what it means. N11-only work goes to its explicit later lane without deleting requirements.

**Exit:** exhaustive 131-row disposition, no hidden/unclassified node, all required normative paths included and a measurable critical path.

### OPT-2 — Repair review persistence and the fixed-point gate

**Root issue found:** `tools/semantic_obligation_queue.py` currently hashes very broad shared dependencies for each review (all tools and broad implementation trees), and writes `fixed_point_reached: false` unconditionally. This creates needless invalidation and prevents the queue itself from expressing completion.

**Do:**

- Bind each review to its **actual minimal complete transitive semantic inputs** (source section, exact own schema/refs/role, governing profiles/predicates, relevant trusted producer/HistoryCut rules and test/verifier code); represent genuinely global contracts as shared dependency groups with declared outgoing edges.
- Propagate invalidation through **real dependency edges**, including changed shared serializer, validator, trust root, bootstrap order, Registry, profile dispatch, or schema semantics. Never under-invalidate.
- Keep review/paragraph approvals and evidence as content-addressed immutable historical records; only mark **CURRENT** when all declared exact dependencies and evidence hashes match.
- Calculate `fixed_point_reached` from an independently testable predicate; it may become true only if every mandatory node/conditional predicate has a justified reviewed or legally reusable disposition, no Class C/D unknowns or material graph contradictions remain, all required schemas/fixtures are bound, and final input drift is zero. **Do not replace a hardcoded false with a hardcoded true.**
- Add negative tests: relevant source change invalidates, shared canonical-contract change invalidates consumers, unbound proof invalidates, unrelated diagnostics/temporary workspace logs do not invalidate, repeated generation with unchanged inputs is idempotent.
- `NOT_APPLICABLE` is allowed only with exact source/role reasoning, not automatic escape from an obligation.

**Exit:** review-retention regression PASS; changed review inputs cause precise invalidation; stable reviewed nodes remain complete; fixed-point truth is reproducible and independently checked. This is a process fix, **not** an automatic semantic PASS.

### OPT-3 — Early non-authoritative candidate preflight (reuse existing 275 inputs)

**Do:** Do **not** wait until every narrative paragraph is reviewed before detecting mechanical build-time problems. Reuse the retained 275 schema drafts + Registry/SchemaRegistry build inputs, source/archive readback and existing Golden candidate drafts; run a reproducible **PRE-FREEZE preflight** in a disposable directory. Check:

- canonical kind/version exact coverage, schema bytes and digest mapping, no unspecified profile or raw-payload schema;
- valid offline schema resolution and finite variants; no schema-by-convention;
- dependency DAG, same-commit order, raw vs typed reference classes, exact pin consistency;
- missing normalizers, fixture generators, basic positive and negative checks;
- no circular output/build/qualification self-dependency.

Fix mechanical errors immediately and rerun **only impacted generators and dependent checks**. If a semantic choice is needed, route that specific issue to OPT-4; do not restart the full graph.

**Exit:** `PRE_FREEZE_CANDIDATE_PREFLIGHT.md` with a zero-missing-dependency build input set **or exact blockers**, source/digest inventory, and explicit `qualification=false`. No fabricated Q1.

### OPT-4 — Risk-prioritized semantic parity and real-instance authority proof

Work in this order, keeping one auditable disposition per kind:

1. **Critical NF02 chains:** accepted assignment/attempt; package raw bytes and immutable binding; producer authority; admission; result; lane/stage completion; schema installation and migration rejection.
2. **Shared authority substrate:** command/commit/HistoryCut, source/bootstrap roots, version installation, cross-object raw/typed binding, consistency of external profiles and predicates.
3. **All applicable remaining Q1-required kinds:** including changed/transitively affected and any remaining mandatory full-path obligations; reuse unchanged qualified proof only when source contract allows and every exact input remains valid.
4. **N11-only semantic gaps:** separately queued for later lifecycle qualification, unless Q1/Q2 already depends on them.

Resolve the **69 inventoried conditional obligations** by applicability and precise proof; count obligations CLOSED/NOT_APPLICABLE/WITH_EVIDENCE/OPEN, not merely a raw inventory size. Finish actual canonical-instance chronology/DAG (not profile-name topology alone), same-commit/prior-only boundaries, producer and trusted context authenticity, failure precedence, atomic no-mutation reject, and migration semantics. Prior `SPEC_CONFLICT`s and OD-001–OD-038 need not be reconsidered without actual new contradictory evidence.

For each kind: source proposition(s) → exact machine representation → intended producer/context → positive witness → one or more falsifying examples → verdict and dependency digests. Group identical inherited clauses in one shared verified rule **only where exact source semantics really coincide**. Do not require 15 irrelevant checks per kind; attach a precise N/A explanation where a dimension does not apply.

**Exit:** 131 complete, defensible dispositions (own review or authorized exact reuse), zero applicable unresolved source/body/profile/predicate gaps, zero required unbound schemas, passed negative fixtures and actual-instance authority proofs. If a blocker proves that fewer-than-131 scope would violate Q1, retain the mandatory wider scope — do not silently weaken it.

### OPT-5 — Materialize exact successor and execute fresh Q1

**Do:** Build successor normative and machine artefacts, 131-key Registry and exact SchemaRegistry, schema/profile/raw bytes, Golden/adversarial fixtures, approved change log and manifest identities from the stable candidate inputs. Run all *required* readbacks and full qualified Q1 verification on exact snapshots. Store separate evidence for normative/predicate/schema/fixture/reachability and independent governance.

**Efficiency:** the first full qualification run happens once the preflight and critical semantic queue are actually ready; if Q1 fails, locate the minimal failed dependency and re-run affected evidence plus all *mandated* transitive checks. Every changed Q1 input invalidates its qualification evidence; requalify before later activation.

**Exit:** real `R5_4_2_Q1_PASS` (or correctly versioned successor) with exact artifacts, complete source/binding hashes and zero omitted mandatory controls. **No Q1 PASS without executed mandatory fixtures/readback/semantic proof.**

### OPT-6 — Q2 independent activation/installation

**Do:** Independently pin Q1-qualified bytes and external authorization; verify actual build/source provenance, profile/trust/Registry/SchemaRegistry roots and the initialization DAG. Keep build-time candidate construction separate from campaign-history acceptance. Reject prior-campaign silent adoption, untrusted source and same-commit authority bootstrap.

**Exit:** `Q2_PASS` on exact installed version and new-campaign boundary, else no runtime canonical acceptance of successor kinds.

### OPT-7 — N5–N8 NF02 runtime enforcement

**Do:** Implement and verify exactly the qualified successor contracts: durable exact ZIP package binding, independently authenticated admission and result, accepted raw presence/readback, correct completion, schema pinning, idempotent retry vs conflicting retry, rejection atomicity, restart/concurrency and old-campaign fail-closed compatibility. Prefer minimal surgical changes to the previously tested NF02 runtime fixes; do not rewrite stable subsystems.

**Scheduling:** before Q2, targeted code/tests may be prepared in isolation only if explicitly permitted, but must not accept successor canonical writes or claim implementation qualification. After Q2, run component tests then required cross-cutting suites, Mypy, Ruff, standalone build and validator on the exact final source/environment evidence.

**Exit:** N5–N8 gates evidenced, no open authority bypass and no undocumented source/code drift.

### OPT-8 — N9 independent attack review, then N10 NF02 closure

**N9 minimum attacks:** forged caller-controlled result authority (`NF02-001`); byte-swapped package with unchanged semantic checksum (`NF02-002`); accepted-result raw disappearing before commit or after restart (`NF02-003`); absent/wrong pinned executable schema (`NF02-004`); wrong source/attempt/slot/cut; repackage changes RawDigest; stale/replayed producer evidence; same-commit shortcut; duplicate/concurrent grants or result submissions; negative no-mutation assertions; old `/1`/new `/2` laundering.

Use separate challenge generation/evidence review. Fix root causes, requalify any changed normative substrate or runtime evidence. No weakened test or fake PASS.

**N10 exit:** independent NF02 acceptance record only if N9 passed, required runtime/build/identity tests passed and all findings closed. **NF02_CLOSED** is distinct from full application lifecycle qualification; do not conflate the two.

### OPT-9 — N11 full application lifecycle as a separately measured gate

Run application startup → campaign initialization → stage/lane assignments → execution → STOP/conclusion → reporting/export → restart/recovery/resume on a valid qualified successor foundation. Cover failure cases and immutable history/provenance. Reuse qualifying proofs from earlier stages only where exact contract/evidence permits; N11-specific gaps are handled here. No fake application-wide PASS based on NF02 alone.

**Final desired state:** `NF02_CLOSED_AND_FULL_APPLICATION_LIFECYCLE_QUALIFIED`, meaning both independently evidenced N10 and N11, not one umbrella Boolean set from draft success.

## 3. Verification cadence (reduce redundant full reruns)

| Trigger | Minimum immediate check | When to run broad/full checks |
| --- | --- | --- |
| Editorial update, unrelated diagnostic log | Exact hash/identity relevance check; no unrelated suite | Never solely due to the log; preserve qualified binding |
| One kind/schema/profile/predicate changed | Focused grammar, reference, producer and negative tests + affected dependencies | Before semantic fixed point, Q1 and after materially shared changes |
| Common serializer, schema resolver, Registry/trust/HistoryCut/bootstrap changed | Focused tests + complete transitively affected authority closure | Required full Q1/runtime acceptance suite at their gates |
| Runtime N5–N8 code change | Targeted tests + affected integration and negative rejection suite | Mandatory runtime, build, mypy/Ruff/artifact validator before N9/N10 |
| Freeze/activation/release gate | Exact full preflight/readback, all specified qualification/negative evidence | Always at Q1/Q2/N10/N11 as required by governing contracts |

Never reuse a record because “the HEAD is unchanged”. Evidence binds exact relevant source, fixtures, tools, requirements, schemas, Registry, profiles, build inputs and runtime environment where required. A failure cannot be masked as a skipped check.

## 4. Progress reporting and anti-loop rules

Update **one** `ACTIVE_EXECUTION_STATE.md` after meaningful gate transitions (not after every passing trivial test). Track:

| Metric | Definition |
| --- | --- |
| `covered/131` | Kinds with evidenced current review or lawfully reusable qualified proof; an unreviewed item is not covered |
| `applicable_conditional_closed/total` | Cross-object obligations with evidence; N/A must be justified |
| `unbound_required_schemas` | Count must become 0 before Q1 |
| `actual_instance_DAG_and_guards` | PASS only on independently exercised valid/invalid instance paths |
| `draft_candidate_ready` | Mechanical prefreeze readiness, not Q1 |
| `Q1, Q2, N5, N6, N7, N8, N9, N10, N11` | Separate real gate states with exact evidence identifiers |
| `NF02` and `full_lifecycle` | Separate user-facing status |

If a review repeats twice without changing any actual input or eliminating a blocker: **diagnose loop source**, prune invalid global dependencies or bad regeneration, and proceed with a different proven method. **Do not stop work because of an artificial number of runs or timebox.** This is an escalation trigger, not a STOP condition.

A `usageLimited` label alone is **not** a STOP if the required shell, repository, tests and file tools actually work. An actual refused/unavailable required operation is documented precisely; continuing without required proof does not become a PASS. Ordinary solvable Class C/D and `SPEC_CONFLICT` findings return to the owner-delegated design queue, not interactive approval. Stop only for a genuinely irreducible owner choice, required external authority/unavailable resource, or fundamental contradiction — and preserve checkpoint.

## 5. Reuse, preservation and merge policy

- Do not modify frozen R5.3/R5.3.1/R5.4.1 bytes or historical evidence; new semantics get properly versioned successors.
- Keep existing R5.4.2 draft results as content-addressed evidence. Do not delete old checkpoints as an efficiency measure; mark them historical and avoid rereading them without need.
- Maintain a separate immutable decision register for any new OD decision; do not multiply near-identical master-plan files.
- No commit/push/merge unless explicitly authorized. PR #45 currently carries an **unfinished work snapshot**; cancelled/skipped CI is not a merge-ready green gate.
- If worktree contains changes newer than the published branch, compare and preserve them before updating anything. Never reset/discard uncommitted implementation.

## 6. Operational instruction for Codex

**Resume the current project from the freshest intact local checkpoint, reconciled with the published OD-038 GitHub snapshot. Apply OPT-0→OPT-9 in order, using local parallelism only where there are no normative dependency conflicts. First deliver the exact 131-kind impact matrix, fix review retention/fixed-point calculation and run a pre-freeze preflight against already prepared 275 schema inputs. Then complete risk-prioritized genuine semantic closure and qualify Q1/Q2, implement N5–N8, independently attack N9, qualify NF02 at N10, and separately qualify lifecycle at N11.**

**Do not restart 131 reviews from scratch; do not reopen OD-001–OD-038 without demonstrated contradiction; do not remove actual Q1/Q2 obligations; do not give a false `fixed_point_reached=true`; do not stop merely because a status string is `usageLimited`; do not commit/push/merge.** If proposed efficiency change conflicts with explicit governing semantics, retain the semantics and report the exact dependency. Prioritize passing real gates over accumulating design-only PASS counts.

## 7. Primary provenance (as inspected on 2026-10-09)

- Current snapshot: https://github.com/eagleblastmusic-lgtm/BDB_AUDIT_CZAT/tree/codex/r5-4-2-current-state-20261009
- PR #45: https://github.com/eagleblastmusic-lgtm/BDB_AUDIT_CZAT/pull/45
- Checkpoint: `docs/R5_4_2/autonomous_2026_10_07/RESUMED_WORK_CHECKPOINT.json`
- Work report: `docs/R5_4_2/autonomous_2026_10_07/CONTINUATION_REPORT.md`
- Queue generator: `docs/R5_4_2/autonomous_2026_10_07/tools/semantic_obligation_queue.py`
- Qualification-order rule: `docs/R5_4_2/autonomous_2026_10_07/design/CANDIDATE_QUALIFICATION_ORDER_REVIEW.md`
- Owner delegation: `docs/R5_4_2/OWNER_DELEGATED_DECISION_REGISTER.md`
- Normative execution source: `docs/R5_4/BDB_AUDIT_V2_IMPLEMENTATION_EXECUTION_PLAN_R5_4.md` and the exact inherited approved foundation.

# F2 preflight — unresolved execution-order conflict

This is a diagnostic report, not MilestoneAcceptance, runtime authority, a gate
PASS, or evidence that F2 was implemented. No runtime path or test bypass was
created. The attachment was read as navigation; conclusions below use the
hash-verified full sources and the user's mandatory sequencing requirement.

## Status

```text
F2_STATUS = SPEC_CONFLICT
F2_START_HEAD = 756e8684cbf23a511812065eeda74afb74f7636e
F2_FINAL_COMMIT = NONE
BRANCH = bdb-v2
PR007_M4 = NOT_STARTED
PR008_REGISTRY_GOLDEN = NOT_STARTED
PR009_M5_OBJECTS = NOT_STARTED
PR010_M5_TRANSACTION = NOT_STARTED
PR011_M5_FSM_GATE = BLOCKED
PR012_M6_STAGESPEC = NOT_STARTED
PR013_M7_ISOLATION_GATE = NOT_STARTED
PR014_M8_CAPABILITY_VIEWS = NOT_STARTED
PR015_M9_COMPILER_GATE = NOT_STARTED
PR016_M10_SCHEMA_IDENTITY = BLOCKED_BY_ORDER
PR017_M11_CORPUS_GATE = NOT_STARTED
PR018_M12_KNOWLEDGE_GATE = NOT_STARTED
PR019_M13_QUARANTINE = NOT_STARTED
M5_GATE = NOT_RUN
M7_GATE = NOT_RUN
M9_GATE = NOT_RUN
M11_GATE = NOT_RUN
M12_GATE = NOT_RUN
F0_REGRESSION = NOT_RERUN; prior input identities verified
F1_REGRESSION = NOT_RERUN; prior input identities verified
GOLDEN_VECTOR_QUALIFICATION = NOT_RUN
SCHEMA_BINDING_QUALIFICATION = NOT_RUN
CRASH_ATOMICITY_QUALIFICATION = NOT_RUN
PROJECTION_REBUILD = NOT_RUN
ISOLATION_KNOWLEDGE_ADVERSARIAL = NOT_RUN
F2_MILESTONE_ACCEPTANCE_ID = NONE
F2_MILESTONE_ACCEPTANCE_SHA256 = NONE
QUALIFICATION_HISTORY_CUT = NONE; no accepted history created
NEXT_PHASE_ALLOWED = NO
F3_STARTED = NO
SPEC_CONFLICTS = 1: F2-SCHEMA-ORDER-001
UNRESOLVED_BLOCKERS = 1: F2-SCHEMA-ORDER-001
```

## F2-SCHEMA-ORDER-001

This is a material ambiguity/conflict in the required execution order, not a
claim that JSON Schema and canonical history are intrinsically incompatible.

Exact clauses:

1. Data Contracts section 184, line 5072: before the first runtime acceptance
   of a wire kind, the implementation MUST bind its semantic key to exact
   executable schema bytes and digest in an accepted/pinned SchemaRegistry;
   absence is fail-closed `SCHEMA_BYTES_NOT_BOUND`.
2. The same section, lines 5074–5079: `EXPLICIT_COMPLETE` defines the complete
   material typed-reference/cardinality/history/content/order contract. It
   is not an exemption from executable schema validation.
3. Execution Plan PR-008/P04, lines 390–395: exact binding precedes reachable
   runtime acceptance, and PR numbering/order never authorizes unbound
   acceptance; PR-009 and later history work remain fail-closed.
4. Execution Plan PR-011, line 474: `Run the full M5 Gate after PR-011.`
   Roadmap section 20 requires actual successful synthetic acceptance,
   including first bootstrap in one atomic commit and one accepted head.
5. Execution Plan PR-016, lines 530–553 assigns executable schema/identity
   binding to PR-016. Section 18, lines 1055–1090 requires the exact practical
   order PR-009 → PR-010 → PR-011/M5 Gate → PR-012–PR-015 → PR-016.
   The user independently makes this practical order mandatory.
6. Execution Plan Definition of Ready, lines 164–171 requires dependency
   PRs/gates to be PASS. No explicit M5 gate deferral or early binding split
   was found in these governing work-package/sequence clauses.

The implementation at the required starting commit contains F1 primitives,
not executable schema bindings. `git ls-files '*schema*' '*AGENTS.md'`
returned only `AGENTS.md`; the F1 README explicitly leaves executable schema
binding and accepted-history resolution outside F1.

Consequently the literal required sequence cannot establish a legal M5 PASS
before implementing its schema-binding prerequisite. Treating the inline ref
contract as executable schema would violate section 184. Using test-only
acceptance would violate the task. Moving prerequisite binding earlier or
deferring the M5 gate could resolve the dependency, but needs an explicit
resolution of the mandated ordering rather than an undocumented exception.
Combining commits alone does not resolve the required gate/order boundary.

Required resolution: state whether the minimal M5 executable binding and
offline validator may be implemented before M5 acceptance, with PR-016
completing/qualifying the remaining F2 bindings; alternatively explicitly
revise the gate schedule. No normative bytes were edited to choose either.

### Exact Registry inspection

Each row below is version 1, mode `EXPLICIT_COMPLETE`, semantic schema key
`BDB_SCHEMA_REGISTRY::<kind>/1`:

```text
command_envelope
commit_body
command_receipt
history_cut
installation_bootstrap_profile
trusted_predecessor_selection_decision
bootstrap_admission_decision
campaign_genesis
```

The accepted M5 object/receipt paths require the corresponding exact executable
bindings before acceptance. HistoryCut remains a constructed value, and the
installation profile an external pin; this report does not invent separate
acceptance transitions for them. The bootstrap transitive object closure also
requires bindings for each accepted source/legacy/assessment kind it reaches.
No complete executable closure or schema/backend qualification is claimed.

The exact vector `R5N06_SCHEMA_BINDING_FAIL_CLOSED` was inspected from the pinned
JSON: null `exact_schema_digest`, mode `SCHEMA_BOUND_BEFORE_FIRST_ACCEPTANCE`,
expected `SCHEMA_BYTES_NOT_BOUND` / `REJECT_RUNTIME_ACCEPTANCE`. Inspection is
not execution or golden qualification.

## Source identities actually consulted

| Source | SHA-256 |
|---|---|
| Data Contracts | `658f8866ca1a1330db9be582b13b47e87381de2208c53ee64ed9e47a8d3e15ee` |
| Roadmap | `b127e249b8db0bd2f17c5e6f77ed3d2d342fc8fb187e3ec720de0b7bd1fac018` |
| ADR-006 | `df7e40fc062f5fcc2309276cc6fd4b529c060fb4f5f24fe39484eb66c0153dfa` |
| Registry | `5a89cfe26d927c9bf2638ad1e656b4ed810544f8d35e3e0ddf1365cd54b7343c` |
| Golden Vector set | `7bee0013d179adc8eba14d07c2c3ea159de0b8e37be9a9f6dcd55969550b7772` |
| Architecture | `af1e1a1c1c884d3b7f41dac196124221b0f137fe7034843ad616f9b3ac066a72` |
| Current Execution Plan | `7ec2de0ccfba3672a9a399af2b77f6fc5dfb42d87645e65206ca8bb5c8007d59` |
| Author baseline qualification | `de7c79c3a7ec3f3879d702993e60f882f01f66ecbc00c67e8084de84dc5f99a0` |
| Candidate manifest raw bytes | `13d72d879372741c472af2f55292b16c8ef1c2c2a853ae215eab45bb53feb400` |

Repo-bound sources were used under `F1_QUALIFICATION/inputs/`, with the Registry
under `src/bdb_audit/core/`. Exact outside-repository sources were found at:

```text
C:/Projekty/Audyty/BDB Audit - Context/01_EXECUTION/BDB_AUDIT_V2_IMPLEMENTATION_EXECUTION_PLAN_R5_3.md
C:/Projekty/Audyty/BDB Audit - Context/00_CURRENT_R5_3/01_NORMATIVE_BASELINE/BDB_AUDIT_V2_ARCHITECTURE_SPEC.md
C:/Projekty/Audyty/BDB Audit - Context/00_CURRENT_R5_3/02_QUALIFICATION_EVIDENCE/BDB_AUDIT_V2_R5_3_MANIFEST_SHA256.json
```

The stale Execution Plan was not substituted. Normative candidate-set pin
`78de98f8163d2f0bf0ab94781b86bd8e5e0345411a4432669d91fdfc42671d56`
was checked against the author qualification; all 10 candidate source byte
hashes matched the exact manifest. No duplicate source snapshots were created.

## Checks and preservation

Read the attachment and both actual AGENTS.md files. Neither was modified.

Entry commands and results:

```text
git branch --show-current
  bdb-v2
git rev-parse HEAD
  756e8684cbf23a511812065eeda74afb74f7636e
git status --short
  ?? tests/compatibility/__pycache__/
git diff --name-only d6ee6e3d6a935043bf899731212c3ec4eec9a773 756e8684cbf23a511812065eeda74afb74f7636e
  AGENTS.md
git remote -v
  origin https://github.com/eagleblastmusic-lgtm/bdb-audit.git (fetch/push)
git diff --quiet
  exit 0
git diff --cached --quiet
  exit 0
```

Git reported access-denied warnings for pre-existing `pytest-cache-files-1huzd8jx/`
and `pytest-cache-files-k6s3xvf8/`. Neither directory was touched; their contents
were not inspected. These warnings were not classified as repository drift.

`Get-FileHash -Algorithm SHA256` verified the exact F0/F1 records and the source
pins above. F1 acceptance ID was checked as `BDB-F1-M2-M3-R5_3-001`:

```text
F1 acceptance SHA256 = 28e22dc60262e6008f5088a30dfdf52b30c7dd5c96b925f19a2dcb910dc9d1c5
F0 acceptance SHA256 = ea8e17ae3a23bb2101afb2db19be2e0e99f238ecea51cc9de794e57a3b14b35c
```

A read-only Python check, invoked as `C:\Python314\python.exe -B -` with the
script passed on stdin, asserted the F1 record's subject raw and Git hashes,
F0 subject raw and Git hashes, the main ref, and every candidate manifest row:

```json
{"F1_subject_identity_count":30,"F0_raw_identity_count":39,"F0_git_identity_count":41,"normative_source_identity_count":10,"main_unchanged":true,"result":"PASS_IDENTITY_ONLY","behavior_tests_rerun":false}
```

`tests/f1/verify_f1.py` was read in full. Its post-commit mode requires
`HEAD^ == 5d2093076f7ef27ea68c69289ae6a5cf2f60b7ef` and compares exact subjects
and qualification bytes. It was not weakened or incorrectly run as an F2
descendant verifier. No behavioral regression PASS is claimed.

Local commits: NONE. Material additions: this diagnostic report only.
Executable implementation changes: NONE. Validator/backend identity: NONE;
no validator was installed or used. Final F2 verifier: NOT_CREATED/NOT_RUN;
no terminal qualification or replay counts exist.

The index remains clean. Main is unchanged at
`446f11ce1622a49f5100cefead29a04d952d487e`. Frozen legacy, corpus and F0/F1
acceptance/input evidence remain unchanged. The pre-existing untracked
`tests/compatibility/__pycache__/` was left untouched. This report is a new
untracked diagnostic, deliberately not an acceptance artifact.

No F3 work, push, merge, tag, reset, clean, remote-ref change or history rewrite
occurred. All required F2 gates remain unqualified.

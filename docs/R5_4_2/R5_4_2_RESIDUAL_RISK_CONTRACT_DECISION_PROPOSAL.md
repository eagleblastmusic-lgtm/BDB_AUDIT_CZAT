# R5.4.2 Residual Risk contract decision proposal

Date: 2026-10-06. **PROPOSED — NOT APPROVED — NOT RUNTIME AUTHORITY.** Task is normative contract design and reachability analysis only. No candidate, executable schemas, qualified bindings, activation, runtime implementation or new qualification record was created.

## A. Executive decision

Classification **B: existing semantics mostly defined; exact body/ref/revision/no-omission contract requires explicit owner decision**. §79 and Roadmap M42 determine a canonical versioned **ASSESSMENT**, not a new fact or bundled owner decision. Recommend one `residual_risk/1` with immutable revisions, exact subject, qualified basis and explicit input cut. Risk tolerance remains a separate authorized `approval_decision/1`; the assessment may refer to that decision but cannot authorize itself.

The proposed model is specified below for owner review. It is **not** inserted into the qualified Registry. With the proposal treated as a hypothetical graph node, analysis progressed beyond the prior 51 seeds and found two other class D defects. Therefore final gate is **SPEC_CONFLICT**, not READY_FOR_OWNER_APPROVAL. Design expansion for these other kinds stopped under task §25.

## B. Source/candidate identities

Repository: `eagleblastmusic-lgtm/bdb-audit`, `C:\Projekty\Audyty\BDB Audit`. Branch `fix/nf02-lane-result-authority`; HEAD `b7051472909075bb4c83a9a510e298fcca2a6bd5`; tree `3bc05685293d2fade72735e43a2ccc96be26f3f7`. Required status/branch/HEAD/tree/log commands were run before analysis. The ignored `.codex-pytest-tmp/` directory remains unreadable; this warning does not concern task input files or explain the specification conflict.

Fresh full predecessor readback: **120 candidate entries, zero mismatches**. Source and complete predecessor hashes are in the reachability JSON. Its `previous_diagnostic` preserves the prior 51/39/11/1 counts, exact seed paths and all 276 recorded edges rather than restarting from assumptions. All seven existing diagnostics were read; JSON documents were parsed completely, including readback rows, pins, graph rows/edges and abort statuses. No predecessor qualification is revoked or relabeled.

- `manifest_raw_digest`: `15415abd7d2601698c6ff664a93077213e81575272a213c4511f6082c9d8fdef`
- `normative_candidate_set_digest`: `d11f751f729605f94bdd11dc033f700f895ee4f7091f2150424023fd4efcaf3b`
- `machine_candidate_set_digest`: `640b76678b48d1902c16775c660709101f1a0708805b7608f822af7a0604f682`
- `registry_raw_digest`: `1b9d17c46843a91053036f0370d4419dac87ce5978df61b0dc922e0e40237e2c`
- `schema_registry_object_digest`: `de514548328391f271dac2f6b253b8d47ac8d6e5406e6e0781a2bfb18c9cbc1e`
- `golden_raw_digest`: `4cebb462b647c69e6348546180900ac2a3c4806a5bf1716e5269b70ed94edb17`
- `qualification_record_raw_digest`: `3a3754d4eebac944ad40c7a49cf6db882bbbde6c55c7f14784961dbfc4df8b90`

Existing authority remains VALID AUTHOR-QUALIFIED EXACT R5.4.1 CANDIDATE, insufficient for the full declared runtime path. R5.3/R5.3.1, failed R5.4 and its invalid premature record are distinct preserved historical artifacts. R5.4.2 still has no materialized candidate.

## C. Why residual_risk is required

Data §79 calls Residual Risk a canonical assessment and supplies a domain field/disposition list. Data §80 and Registry rows require applicable exact risk refs in CandidateAssuranceCase, StopInput, CampaignConclusion, FinalAssuranceCase and ReleaseQualification. Architecture §§31–33 and Roadmap M42–M44 place risk assessment before candidate/STOP and keep finalization acyclic. Methodology §§54–55 distinguishes residual uncertainty from absence of unresolved findings. Test Plan §118 requires every material known residual risk to remain explicit.

The nonempty material-risk branch is part of declared lifecycle sufficiency. A zero-risk execution does not eliminate it from reachability. A reference target class named `residual_risk_ref` is not a registered wire contract. Local overlay and code cannot legalize it.

Distinctions: FindingClaimRevision states a claim; unresolved finding is an epistemic/adjudication condition; Blocker Ledger is a derived view of unsatisfied obligations/assessments/invalidations (§178); risk assessment characterizes remaining exposure/uncertainty; owner acceptance is a separate decision; mitigation is supported by actual accepted execution/evidence; register and final summary are projections. None changes the truth/support of another merely by relabeling it.

## D. Existing normative consumer semantics

`RESIDUAL_RISK_NORMATIVE_USAGE_INVENTORY.json` records every match of the requested terms across the ten exact normative sources, including Registry/Golden JSON pointers, section/line, exact source text and consumer timing/cardinality/ref/layer data where explicitly stated. It contains 483 occurrences. Lexical/historical mentions are not automatically mandatory predicates; null per-occurrence timing/layers means the occurrence itself does not specify them. The following synthesis uses complete relevant sections and complete consumer rows, not the overlay.

| Source / consumer | Required meaning and chronology | Cardinality / checks |
| --- | --- | --- |
| Data §79 / risk producer; Roadmap M42 | Canonical versioned assessment of remaining risk; accepted risk does not change evidence or prove absence of the problem. | Existing corpus lacks complete subject/cut/ref/revision-selector semantics; B decision required. |
| Data §76 / StopInput; Architecture §32 | Exact accepted input cut; direct authority refs and equality-checked summaries; material unknown/blocked/stale evidence cannot disappear into default PASS. | `residual_risk_refs` 0..N, CONTENT_OR_PRIOR; frozen consumer layers L3–L7. |
| Data §80 / CandidateAssuranceCase; Architecture §31 | Exact pre-challenge cut, current obligations/evidence/risks; no future STOP/conclusion. Material candidate change requires both challengers again. | risk refs 0..N, CONTENT_OR_PRIOR; L3–L7. |
| Data §80 / CampaignConclusion | Prior accepted STOP and basis; same campaign/source/candidate/assurance; COMPLETED requires PASS; LIMITED is an explicit authorized termination. | risk refs 0..N PRIOR_ACCEPTED_ONLY; exact conclusion input cut; L3–L7. |
| Data §80 / FinalAssuranceCase | Later envelope after conclusion; cannot omit material conclusion risk; cannot promote LIMITED to full PASS. | risk refs 0..N PRIOR_ACCEPTED_ONLY; exact final input cut; L3–L7. |
| Data §§76,80.1 / ReleaseQualification | Non-PASS or bounded assurance excludes READY; READY_WITH_RESIDUAL_RISK requires explicit authorized risk acceptance under release policy. | accepted risk refs 0..N PRIOR_ACCEPTED_ONLY; earlier release assessment basis and qualification cut; L3–L7. |
| Data §157 / ApprovalDecision | Human approval has actor, authority, scope/requested_action, related refs and prior cut. Residual-risk acceptance needs the correct authority class. | Registry actor/authority PRIOR_ACCEPTED_ONLY; approval input HISTORY_INPUT; related refs CONTENT_OR_PRIOR; L3,L4,L5,L7. |
| Data §§48,76–80 / obligations and limited basis | Waiver/unknown/blocked do not satisfy an obligation. Risk assessment cannot erase an unsatisfied mandatory predicate. | Existing applicability/waiver decisions remain separate; no inferred N/A/PASS. |

Producer audit: the direct canonical constructor is `ResidualRiskRecord.as_object` (`assurance/residual_risk.py:166`); its service accepts through Coordinator (`:338`). Register invalidation/contradiction methods replace only projections and cannot create amended canonical authority. Attack/synthesis local risk registers do not become accepted facts automatically. Consumers include risk projection, candidate, STOP, finalization and release hooks. Current accepted-sequence selection and digest-only set comparisons are implementation evidence, not proposed normative equality rules.

## E. Historical overlay analysis

Overlay: `src/bdb_audit/core/artifact_contract_overlay_r5_3_3.json`. Its row is an implementation/design proposal only. No bytes or semantics were imported into authority.

| Overlay / historical body field | Normative support | Decision | Owner decision required |
| --- | --- | --- | --- |
| kind/version `residual_risk/1` | §79 canonical assessment; absent Registry row | KEEP proposed wire name/version | Register complete new row explicitly. |
| ASSESSMENT; IMMUTABLE | §79; M42 versioned assessment; general history immutability | KEEP | Approve complete contract, no novel role. |
| producer TRUSTED_COORDINATOR_ACCEPTANCE | Existing accepting-actor model | KEEP | No external producer self-authority. |
| FINALIZATION; L3,L4,L5,L7 | Overlay choice, not a complete §79 mandate | CHANGE to EPISTEMIC L3–L6; consumer completion/STOP keeps L7 | Approve named-profile choice; no L7 weakening downstream. |
| `risk_id` | §79 | KEEP as exact `residual_risk_<uuidv4-lowercase>` logical identity | Explicit lineage/campaign uniqueness. |
| `risk_revision` | §79 versioning, no exact selector contract | REMOVE stored revision label; exact ObjectDigest and predecessor chain identify revision | Amend §79 body explicitly, not silently reinterpret it. |
| `scope` string | §79; exact scope rules elsewhere | CHANGE to typed `subject_ref`; scope text derives from subject | Finite permitted subjects below. |
| `description` | §79 | KEEP risk statement | No truth promotion. |
| `materiality` scalar | §79; §§41/48 require exact MaterialityAssessment authority for applicable scope | CHANGE to `materiality_assessment_ref`; derived result | Explicit §79 amendment; no copied second authority. |
| `uncertainty_class`, `reason_unresolved` | §79; unknown/blocked must be explicit | KEEP bounded nonempty text | No default interpretation as NON_MATERIAL/PASS. |
| disposition | §79 six values | KEEP with mechanical predicates below | ACCEPTED label alone is insufficient. |
| `blocking_effect` boolean | §79; STOP predicates require exact policy/basis | REMOVE stored scalar; derive from pinned policy and accepted basis | Explicit body amendment and no-omission policy. |
| `related_obligation_refs`, `related_hypothesis_refs`, `evidence_refs` | §79 context/basis | CHANGE to one finite typed `basis_refs` union and typed subject | Complete target list, nonempty justified basis; no duplicated arrays. |
| `owner_approval_ref` | §79 optional; §157 actual authority | KEEP optional prior approval with exact scope/assessment checks | Define separate assessment → approval → acceptance-marked revision, no cycle. |
| missing input cut / predecessor | General history rules but not complete §79 body | ADD explicit cut and optional `supersedes_risk_ref` | Exact chronological/CAS selection, no latest risk_id. |
| generic registered-immutable evidence targets | Too broad without exact schema/profile | CHANGE to finite targets in H | No unrelated canonical reference smuggling. |

## F. Alternative canonical models

ASSESSMENT is recommended: assessed remaining risk and uncertainty on exact cut, with qualified basis and separate owner authorization. FACT would only attest receipt/existence of a statement and would lose the specified assessment meaning; reject it. DECISION would combine assessment with acceptance/waiver authority and could hide who accepted what; reject it as the primary risk kind. A derived register remains a projection over assessments/decisions, with no mutable authority head. A noncanonical-only model contradicts §79 and the exact consumer rows.

Existing corpus is insufficient for A: the added subject, cut, finite basis and explicit supersession/no-omission semantics materially close gaps. There is no need to claim equally preferred models remain unresolved: B permits a fully specified recommendation for owner approval. Approval of this proposal, not existing code, would authorize these changes.

## G. Recommended residual_risk/1 contract

Proposed closed domain body:

```text
risk_id
subject_ref
materiality_assessment_ref
description
uncertainty_class
reason_unresolved
disposition
assessment_input_history_cut
basis_refs[]
supersedes_risk_ref optional
owner_approval_ref optional
```

`risk_id` matches the canonical logical ID grammar and stays stable within one lineage. `assessment_input_history_cut` is the exact nonempty current command input/expected parent and establishes campaign/source/governing-policy context. No own digest, accepting head/event, profile fallback, secret/capability or producer boolean appears in body. Scope/materiality/blocking effect are derived, not duplicated. This is an explicit proposed replacement of §79's loose field list, not a claim that the existing bytes already define it.

The finite subject union is surface_record, surface_key, invariant_revision or coverage_obligation. A finding/root cause/hypothesis may supply accepted basis but is not substituted for the underlying scope subject. Campaign/stage-wide risks require an actual accepted scope/obligation in the declared inventory; no free campaign/stage string or undocumented broader subject union. This avoids extending MaterialityAssessment subject semantics outside the existing frozen surface/invariant/typed-scope model.

`materiality_assessment_ref` must be applicable to the exact subject; for a coverage obligation it must equal the obligation's accepted materiality assessment and resolve to its scoped invariant/surface. UNKNOWN/CONFLICTED are never NON_MATERIAL. Governing risk/STOP predicates derive from the policy/spec context carried by the input cut; no extra caller-selected policy creates authority.

Descriptions: 1–16384 Unicode characters; uncertainty_class: 1–256; reason_unresolved: 1–4096. Text is preserved exactly without silent normalization. basis_refs contains 1–256 exact refs. These finite caps are proposed schema constraints, not inherited numerical requirements. Six exact dispositions: OPEN, BOUNDED, ACCEPTED_RESIDUAL_RISK, BLOCKED, UNKNOWN, SUPERSEDED. No enum expands to a new assurance outcome.

First revision has no predecessor; root identity `(campaign namespace, full initial risk TypedRef)` is authority-bearing. Later revision names the unique unsuperseded exact prior tip; same risk_id/subject/campaign/source, valid lineage, prior membership and current CAS are required. Only one successor may supersede a tip. Changed assessment uses a new object/digest; no timestamp, revision label or latest-by-logical-ID selector establishes authority. Exact retry returns original accepted fact/receipt; changed retry or competing branch rejects without mutation. A rebuildable lineage index is not authority.

SUPERSEDED terminal disposition may remove a risk from the active set only with accepted applicable basis proving resolution or replacement; the lineage remains retained and replayable. Missing/corrupt/invalidated proof cannot justify removal. A replacement revision is selected by explicit accepted predecessor edges; an arbitrary later object is not a replacement. Source change uses existing new-source/successor rules, not a revision in an old source lineage.

Recommended row, **hypothetical only**:

```json
{
  "kind": "residual_risk",
  "version": "1",
  "canonical_role": "ASSESSMENT",
  "lifecycle": "IMMUTABLE",
  "authoritative_for": "Assessed remaining risk for exact accepted subject and accepted basis on exact input cut; does not authorize acceptance/waiver or establish finding truth",
  "producer_authority": "TRUSTED_COORDINATOR_ACCEPTANCE",
  "schema_ref": "BDB_SCHEMA_REGISTRY::residual_risk/1",
  "validation_profile": "EPISTEMIC",
  "reference_contract_mode": "EXPLICIT_COMPLETE",
  "required_validation_layers": [
    "L3",
    "L4",
    "L5",
    "L6"
  ],
  "identity_semantics": "BDB-CJSON-1 + BDB-OBJECT-DIGEST-1 unless RAW/EXPORT",
  "material_refs": [
    {
      "field": "subject_ref",
      "cardinality": "1",
      "allowed": [
        "surface_record",
        "surface_key",
        "invariant_revision",
        "coverage_obligation"
      ],
      "ref_class": "PRIOR_ACCEPTED_ONLY"
    },
    {
      "field": "assessment_input_history_cut",
      "cardinality": "1",
      "allowed": [
        "history_cut"
      ],
      "ref_class": "HISTORY_INPUT"
    },
    {
      "field": "materiality_assessment_ref",
      "cardinality": "1",
      "allowed": [
        "materiality_assessment"
      ],
      "ref_class": "PRIOR_ACCEPTED_ONLY"
    },
    {
      "field": "basis_refs",
      "cardinality": "1..N",
      "allowed": [
        "coverage_obligation",
        "coverage_obligation_qualification",
        "hypothesis_revision",
        "execution_result",
        "observation",
        "evidence_qualification_assessment",
        "evidence_applicability_assessment",
        "negative_evidence_record",
        "finding_adjudication_decision",
        "contradiction_revision",
        "contradiction_resolution_decision",
        "approval_decision"
      ],
      "ref_class": "PRIOR_ACCEPTED_ONLY"
    },
    {
      "field": "supersedes_risk_ref",
      "cardinality": "0..1",
      "allowed": [
        "residual_risk"
      ],
      "ref_class": "PRIOR_ACCEPTED_ONLY"
    },
    {
      "field": "owner_approval_ref",
      "cardinality": "0..1",
      "allowed": [
        "approval_decision"
      ],
      "ref_class": "PRIOR_ACCEPTED_ONLY"
    }
  ],
  "ordering_rules": {
    "basis_refs": "CANONICAL_TYPED_REF_SORT_NO_DUPLICATES_UNLESS_FIELD_OVERRIDE",
    "revision_chain": "One immutable root per risk_id/campaign; later revisions explicitly supersede exact prior tip, same subject and lineage; no latest-by-logical-ID authority",
    "risk_acceptance": "APPROVED approval_decision with authorized actor and exact prior assessment related_ref; no risk object self-authorizes"
  },
  "consumer_roles": [
    "COORDINATOR",
    "VALIDATOR"
  ]
}
```

## H. Material ref contract

| Field | Cardinality | Exact permitted target kinds | Class | Same-commit / order |
| --- | --- | --- | --- | --- |
| `subject_ref` | 1 | surface_record, surface_key, invariant_revision, coverage_obligation | PRIOR_ACCEPTED_ONLY | Prior accepted only; basis array canonical full TypedRef set sort, no duplicates |
| `assessment_input_history_cut` | 1 | history_cut | HISTORY_INPUT | Exact prior input; not ordinary content |
| `materiality_assessment_ref` | 1 | materiality_assessment | PRIOR_ACCEPTED_ONLY | Prior accepted only; basis array canonical full TypedRef set sort, no duplicates |
| `basis_refs` | 1..N | coverage_obligation, coverage_obligation_qualification, hypothesis_revision, execution_result, observation, evidence_qualification_assessment, evidence_applicability_assessment, negative_evidence_record, finding_adjudication_decision, contradiction_revision, contradiction_resolution_decision, approval_decision | PRIOR_ACCEPTED_ONLY | Prior accepted only; basis array canonical full TypedRef set sort, no duplicates |
| `supersedes_risk_ref` | 0..1 | residual_risk | PRIOR_ACCEPTED_ONLY | Prior accepted only; basis array canonical full TypedRef set sort, no duplicates |
| `owner_approval_ref` | 0..1 | approval_decision | PRIOR_ACCEPTED_ONLY | Prior accepted only; basis array canonical full TypedRef set sort, no duplicates |

All canonical refs resolve by full TypedRef identity and accepted membership on the risk input cut; source/campaign membership and evidence applicability/qualification are revalidated. At least one basis ref must explain the assessment, not merely satisfy array length. A failed/unavailable execution or UNKNOWN qualification can justify unresolved risk, but it cannot qualify positive truth/evidence or meet the original obligation. Mitigation/control proof is followed through exact accepted execution/evidence/qualification refs in basis; no extra unapproved mitigation object kind.

Future exact schema enforces a closed body (`additionalProperties=false`), required keys, canonical ID grammar, exact enums, finite subject/basis union, closed TypedRefs and inherited HistoryCut encoding. Schema annotation/material-ref inventory must equal the approved row. Normal canonical serialization and schema RawDigest identity apply. Schema checks ordering/duplicate identities and finite text/count bounds; semantic validator checks accepted membership, expected-parent/cut, source, qualified basis/materiality, lineage/CAS, applicable authority and all downstream no-omission/STOP predicates. No executable bytes are generated or frozen in this task.

## I. STOP / conclusion / final-case predicates

Define `R(c)` as the complete active risk set reconstructed from retained accepted lineage roots and unique explicit predecessor/supersession edges at exact cut c, constrained by declared source/scope and pinned policy. Every material applicable lineage must have a selected exact tip or a supported terminal resolution. Unknown materiality and unverifiable/missing history/basis cannot exclude a lineage. Risk set is empty only when this reconstruction proves zero applicable active risks, not from an absent cache/summary.

1. **Candidate:** its risk refs equal `R(candidate_input_history_cut)` for its declared scope. No material risk omission. Candidate is prior to challengers/STOP. Any material risk/basis/scope change after challenge requires new candidate and both baseline challengers again.
2. **StopInput:** risk refs equal `R(input_history_cut)` and are prior accepted even where consumer CONTENT_OR_PRIOR mechanically permits earlier same-commit content. This stricter proposed risk predicate ensures they are facts of the evaluation input cut. Summaries/snapshot equality derives from these exact refs and ordinary blocker/obligation/evidence state. For FINAL_POST_E5/POST_E6, candidate risk set must equal the evaluated set or a new candidate/challenge closure is required; no stale candidate excuse.
3. **PASS with risks:** permitted only if all existing mandatory applicable obligations/scope/challenge/effort/authority requirements independently pass AND each material remaining risk satisfies the pinned policy with a valid separately authorized approval. Acceptance does not resolve unsatisfied mandatory obligations, invalidate blockers, qualify stale evidence or hide UNKNOWN. Known accepted technical defects may still make release TECHNICALLY_NOT_READY. Policy-permitted accepted residual risks can yield READY_WITH_RESIDUAL_RISK only with PASS/ADEQUATE and all release predicates.
4. **Acceptance:** first accept assessment A; later accept existing ApprovalDecision with proposed `decision_type=RESIDUAL_RISK_ACCEPTANCE`, decision=APPROVED, exact A in related_refs, correct scope/requested_action, current authorized actor/authority and cut. Later B supersedes A and references that prior decision; assessed subject, materiality and basis/text remain identical apart from disposition/cut/lineage/approval metadata. Approval scope must cover this exact assessed tuple. Changed basis or applicable policy/authority cannot borrow A's approval. No risk → future approval cycle; no generic APPROVED decision, owner string or status boolean suffices. This exact decision-type/predicate use is part of the owner proposal; it is not taken from runtime code.
5. **Conclusion:** risk refs equal the exact evaluated StopInput risk set. Before acceptance, reconstruct current applicable risk/basis state; any material change after STOP requires a fresh applicable candidate/challenge/STOP chain, not substitution by a later risk. ConcludeCampaign input must contain prior STOP and authority/basis refs. COMPLETED requires PASS with matching source/candidate/assurance; COMPLETED_LIMITED is an authorized terminal choice preserving the actual non-PASS/bounded/insufficient outcome.
6. **Limited basis:** residual risk is condition-dependent, not mandatory for every LIMITED conclusion and not a substitute for an actual blocker/obligation. Where assessment of a known applicable risk is part of the justification, include its exact ref along with original blocker/unknown/evidence-failure authority. If LIMITED predates final candidate/challenge, retain exact limited_conclusion_basis_refs. Vague risk text cannot explain away missing evidence; no UNKNOWN→PASS laundering. An incomplete history cannot accept a canonical conclusion at all.
7. **Final case:** risk refs equal conclusion risk refs under the recommended strict no-omission policy. It is later than conclusion and preserves exact STOP/source/candidate/challenger equality. No summary may drop a risk or relabel LIMITED as completed adequate assurance. Release materialization preserves the approved applicable risk set and existing release-policy constraints.
8. **Staleness:** relevant basis invalidation, subject/source/scope/materiality/authority or policy change, new material risk or changed lineage tip makes an old assessment/STOP non-applicable for the current action. Mere unrelated history growth does not itself change risk truth, but the action still validates its exact current input cut and applicability. Never use “latest risk”.

Assessment, accepted statement, waiver, blocker and final summary remain distinct. No relaxation of knowledge/isolation, evidence applicability, source, history or STOP L7 is proposed.

## J. Golden/adversarial vectors

Design only: **NOT_EXECUTED**. Each negative attempted canonical acceptance must prove REJECT and NO CANONICAL STATE MUTATION: accepted head, commit count, event sequence, immutable object count, command/receipt indices, risk lineage selector, binding/result selectors and accepted raw refs unchanged. Scratch diagnostics are never authority.

| ID | Mutation / expected invariant |
| --- | --- |
| RESIDUAL_RISK_UNREGISTERED_REJECT | Qualified old Registry lacks row; schema/overlay cannot grant registration. |
| RESIDUAL_RISK_SCHEMA_NOT_BOUND_REJECT | Correct proposed kind with locally available schema but no exact approved binding; reject before durability. |
| RESIDUAL_RISK_WRONG_SUBJECT_REJECT | Subject kind outside finite union or mismatched exact subject/materiality/basis. |
| RESIDUAL_RISK_STALE_CUT_REJECT | Risk acceptance on stale expected parent or stale relevant basis/authority; unrelated history requires current acceptance cut. |
| RESIDUAL_RISK_MISSING_BASIS_REJECT | Empty/irrelevant, corrupt, unaccepted or future basis; matching text/checksum cannot substitute. |
| RESIDUAL_RISK_CROSS_CAMPAIGN_REJECT | Borrow risk/subject/approval/basis from another campaign/source context without legal admission. |
| RESIDUAL_RISK_UNAUTHORIZED_ACCEPTANCE_REJECT | ACCEPTED status without exact prior APPROVED decision; wrong type/related risk/scope/actor, copied decision or self/future approval. |
| RESIDUAL_RISK_OMITTED_FROM_STOP_REJECT | Exclude a material/unknown active lineage from exact reconstructed R(c), or supply zero-risk summary with nonempty R(c). |
| RESIDUAL_RISK_OMITTED_FROM_CONCLUSION_REJECT | Conclusion differs from evaluated exact risk set or risk/basis changes after STOP without reevaluation. |
| RESIDUAL_RISK_OMITTED_FROM_FINAL_CASE_REJECT | FinalCase removes risk present in exact prior conclusion or promotes LIMITED. |
| RESIDUAL_RISK_FALSE_PASS_REJECT | Risk acceptance used to suppress unsatisfied mandatory obligation, stale evidence, unresolved material contradiction or missing challenger. |
| RESIDUAL_RISK_EXACT_REVISION_ACCEPT | Legal exact prior subject/basis/materiality/cut, immutable lineage and correctly scoped separate approval; exact retry returns original acceptance. |
| RESIDUAL_RISK_COMPETING_REVISION_REJECT | Two different children of exact tip at same parent; deterministic CAS, one legal successor, no fork authority. |
| RESIDUAL_RISK_ARBITRARY_SUPERSEDED_REJECT | Remove active risk without accepted applicable resolution/replacement basis. |
| RESIDUAL_RISK_MATERIAL_REVISION_REQUIRES_RECHALLENGE | Basis/risk material change cannot reuse prior candidate/challengers/STOP for PASS. |

Positive and negative controls must use actual future acceptance boundaries, not local dict consistency alone. This task does not run N5–N11 tests.

## K. Full reachability fixed-point result

The previous inventory was resumed from its exact seeds/edges. Hypothetical risk node was expanded first through its finite subject/materiality/basis/predecessor/approval refs. Direct registered Registry dependencies then expanded, and the mandatory candidate/final-case content-ref frontier exposed class D below. No arbitrary target-class label was minted as a canonical kind; generic/pinned/raw/typed-union frontiers remain explicit.

Observed expanded inventory (partial, not final all-and-only closure): **68 nodes**; **67 actually registered**, plus **one proposed hypothetical risk row**; **39 bound**, **29 missing bindings**, **2 other semantically incomplete consumers**, **fixed_point_reached=false**. Actual qualified Registry still lacks risk; hypothetical unregistered count is zero only within the proposed graph. It is not a qualification assertion.

Final `registered=X`, `semantically_complete=X`, zero gaps and fixed point cannot be reported honestly. Task §25 requires stopping on the other C/D defects; the count of future schema work remains a lower bound. No arbitrary remaining Registry future family is recommended for binding.

## L. Remaining missing bindings

The original 11 gaps remain; proposal adds the risk row and reaches further already registered dependencies. No binding or schema was added. The complete currently observed list is:

- `BDB_SCHEMA_REGISTRY::residual_risk/1`
- `BDB_SCHEMA_REGISTRY::lane_completion/1`
- `BDB_SCHEMA_REGISTRY::stage_completion/1`
- `BDB_SCHEMA_REGISTRY::discovery_record/1`
- `BDB_SCHEMA_REGISTRY::candidate_assurance_case/1`
- `BDB_SCHEMA_REGISTRY::challenger_assignment/1`
- `BDB_SCHEMA_REGISTRY::challenger_result/1`
- `BDB_SCHEMA_REGISTRY::stop_input/1`
- `BDB_SCHEMA_REGISTRY::stop_evaluation/1`
- `BDB_SCHEMA_REGISTRY::campaign_conclusion/1`
- `BDB_SCHEMA_REGISTRY::final_assurance_case/1`
- `BDB_SCHEMA_REGISTRY::release_qualification/1`
- `BDB_SCHEMA_REGISTRY::surface_record/1`
- `BDB_SCHEMA_REGISTRY::surface_key/1`
- `BDB_SCHEMA_REGISTRY::invariant_revision/1`
- `BDB_SCHEMA_REGISTRY::coverage_obligation/1`
- `BDB_SCHEMA_REGISTRY::materiality_assessment/1`
- `BDB_SCHEMA_REGISTRY::coverage_obligation_qualification/1`
- `BDB_SCHEMA_REGISTRY::hypothesis_revision/1`
- `BDB_SCHEMA_REGISTRY::execution_result/1`
- `BDB_SCHEMA_REGISTRY::observation/1`
- `BDB_SCHEMA_REGISTRY::evidence_qualification_assessment/1`
- `BDB_SCHEMA_REGISTRY::evidence_applicability_assessment/1`
- `BDB_SCHEMA_REGISTRY::negative_evidence_record/1`
- `BDB_SCHEMA_REGISTRY::finding_adjudication_decision/1`
- `BDB_SCHEMA_REGISTRY::contradiction_revision/1`
- `BDB_SCHEMA_REGISTRY::contradiction_resolution_decision/1`
- `BDB_SCHEMA_REGISTRY::approval_decision/1`
- `BDB_SCHEMA_REGISTRY::checkpoint/1`

These 29 are not asserted to be purely A/B: candidate and final case also carry the class D field defects. Full narrative/schema parity and future exact profiles remain unqualified. Do not materialize this list before the semantic frontier is resolved and fixed point reached.

## M. Other semantic conflicts

**D1 — CandidateAssuranceCase/1.assurance_claim_set_ref.** Data §80 requires the field; Registry requires cardinality 1, CONTENT_OR_PRIOR, and describes its target class only as “exact assurance-claim-set reference”. No exact registered target kind, durable raw contract/representation, schema/profile or digest domain is selected. Normative Golden provides no target known answer. Production E5 synthesizes an external ref from a caller/body checksum (`workflow/e5_runtime.py:1502`); it is not an accepted canonical target/retained content proof. A schema alone must not silently decide whether this means a registered canonical content object, a durable raw set or another authority representation.

**D2 — FinalAssuranceCase/1.public_conclusion_statement_ref.** Data §80 requires the field; Registry requires cardinality 1, PRIOR_ACCEPTED_ONLY, while the target class says only “exact immutable public conclusion statement/export reference”. No exact accepted target representation/profile/digest contract is selected. Production finalization builds a synthetic target ref using SHA256(text) but labels it BDB-OBJECT-DIGEST-1 (`assurance/finalization_service.py:426`); that is not proof of prior acceptance, nor an authorized canonical ObjectDigest preimage. Choosing an existing export kind versus retained raw text needs explicit contract authority; the type-class label is not a new canonical kind.

These are consumer-contract completeness defects, **not automatically two unregistered canonical kinds**. No new assurance-claim-set or statement kind is proposed in this task. Exact class semantics are preserved; both defects are recorded with current Registry rows and normative/source evidence in the graph. Per §25, no opportunistic design expansion occurs.

## N. Owner decisions required

Approve one residual-risk package if accepted: (1) registered residual_risk/1 semantic assessment; (2) ASSESSMENT and EPISTEMIC validation; (3) immutable explicit lineage; (4) the exact minimal body replacing §79's loose list, including derived scope/materiality/blocking values; (5) finite subject/basis/materiality/prior refs; (6) risk set/no-omission/staleness and STOP/finalization predicates; (7) separate existing ApprovalDecision type/scope/chronology, with no status-based self-authority.

The proposed risk row can be reviewed now, but approving it alone does not establish complete runtime reachability. A **separately scoped** decision must determine the two class D target representations before restarting graph completion. No owner approval of code mechanics, candidate generation, schema installation or implementation is inferred. This document requests no immediate runtime action.

## O. Final gate

**SPEC_CONFLICT**. Risk contract recommendation is specified for review; another class D frontier prevents fixed-point completion and READY_FOR_OWNER_APPROVAL for the combined task. Candidate materialization, exact schema generation/binding, Q1, Q2 and N5–N11 remain NOT_STARTED. R5.4.1 validity and all protected predecessor/runtime bytes are preserved.

Closeout: fresh predecessor readback 120/0; source/protected hashes and all 144 R5.4.1 subtree files unchanged; five other prior abort diagnostics unchanged. Static proposal/domain/graph/inventory/section checks PASS. `git diff --check` exit 0; `git status --short` exit 0 with the pre-existing ignored scratch permission warning; no frozen legacy diff. No runtime vectors/tests executed, no candidate or qualification record emitted.

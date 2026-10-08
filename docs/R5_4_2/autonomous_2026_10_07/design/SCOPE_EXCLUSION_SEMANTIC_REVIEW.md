# Scope exclusion — source/body/context review

This is successor design under OD-026, not runtime authority or qualification.
Sources: full R5.3 Data sections 28, 156 and 157 in
`F1_QUALIFICATION/inputs/BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS.md`,
qualified R5.4.1 Data sections 28 and 157, and Data 15.4 for cut context.
OD-005, OD-011, OD-018 and OD-021 remain unchanged. Exact source digests
are recorded by the executable design controls and the semantic review queue.

## Scope identity and chronology

ScopeStateRecord is an immutable supporting fact. Only an accepted
InventoryRevision selects records for current accounting. EXCLUDED_SCOPE is
not coverage PASS, fulfilled obligation, N/A, source removal, or a conclusion.
UNKNOWN, FAILED, UNSUPPORTED and intermediate states remain explicitly
accounted. Exclusion never silently removes an assigned input or a mandatory
obligation from a denominator/completion gate.

For EXCLUDED_SCOPE, resolve the exact approval_decision/2 at the record's
verified accepted input cut. It must have been accepted at or before that cut,
strictly before this accepting commit, in the same campaign/namespace. An
approval in the current proposed closure cannot satisfy PRIOR_ACCEPTED_ONLY.
REJECTED decisions and other purposes cannot authorize exclusion.
Nonexcluded records forbid scope_decision_ref; their evidence/accounting
requirements do not disappear because no approval is needed.

Approval scope remains the existing sorted nonempty ScopeSet of prior exact
TypedRefs. Do not add raw member paths, source_manifest refs, text patterns,
future records, or a new ScopeKey wire form to ApprovalDecision. For a
CANONICAL_SUBJECT key, the approved prior subject must equal the complete
key subject reference, including exact executable schema binding. For a
SOURCE_MEMBER key, use a prior ScopeStateRecord with that exact stable key
in the approved ScopeSet. This preceding record can truthfully be UNKNOWN,
PROVISIONAL, KNOWN_UNOBSERVED or another supported state; it grants no
exclusion and is not promoted to current inventory authority by being named.
Sequence: prior manifest/member identity, prior scope record, human approval,
then new excluded record, then inventory selection. The approval cannot name
the new excluded record itself. The source manifest and member path must
independently resolve to the campaign's exact source at both applicable cuts.

A present scope_ref must independently resolve to the same exact scope_key.
Naming a previous ScopeStateRecord with an identical key is permitted;
merely sharing a logical ID, member path, category, or a source generation
name is insufficient. A consumer must not recursively collapse arbitrary
subject refs or invent aliases between a whole source member and a surface
within it. Every resolution retains schema pins, source applicability,
campaign identity and prior-visibility constraints. Missing/mismatched scope
proof rejects; omit an optional scope_ref rather than fabricate an alias.

Multiple subjects in a human decision are allowed only as the complete exact
authenticated request scope set. A consumer checks its one exact key against
that set; it cannot widen the decision's scope. Every other approved member
also requires prior accepted resolution and independent applicability.

## Appropriate authority and current applicability

PRINCIPAL_AUTHORIZATION_V1 had only general permitted_operations and could
not express the appropriate approval authority class required by Data 157.
Successor wire PRINCIPAL_AUTHORIZATION_V2 additionally requires
permitted_approval_purposes and
approval_request_selection=EXACT_AUTHENTICATED_ACTION_AND_SCOPE. The
analysis label V1 remains a navigation key, never an accepted runtime alias.
No canonical body is extended: ApprovalDecision/2 already selects exact
external actor and authority pins; all dependent external profile bytes/pins
are regenerated before materialization.

The accepting coordinator independently authenticates the human request;
actor_ref and actor_authority_ref are separately selected installed pins for
that same principal and exact namespace. The authority pin must permit
APPROVE and explicitly SCOPE_EXCLUSION. APPROVE without that purpose,
role name alone, possession of a serialized ref, and executor/tool output
are insufficient. Compare requested_action byte-for-byte and the complete
sorted scope set with the authenticated request, not a caller assertion.
All refs resolve through the exact trust/policy/spec context at the approval's
input cut. The coordinator still separately needs ACCEPT authority.

At consumption, verify the approval's authentic accepted provenance and
current applicability to this source, scope, campaign, governing policy and
spec set at the record's exact input cut. An old approval is neither globally
invalid nor automatically transferable: a changed context requires explicit
independent eligibility under the exact current bindings, with no latest
lookup or logical-ID substitution. In the design model, this prerequisite is
an independently supplied eligible-decision set bound to the complete exact
decision reference, input cut and scope key; production must derive it
from trusted replay and policy rather than accept such a set from callers.
Every required nonwaivable gate remains required. A favorable scope decision
cannot rewrite the input-accounting, evidence, isolation or STOP contracts.

## Output, failures and atomicity

The narrow authorization predicate yields ALLOW or REJECT, never scientific
PASS. Unknown, missing, stale or unavailable prerequisites yield REJECT for
acceptance; diagnostic reason codes do not create new canonical facts.
The draft evaluator is read-only. Canonical operation acceptance must also
validate exact parent, all refs, complete union DAG, producer/cut/policy
guards, sorted arrays and every consumer-specific gate in one transaction.
Any failed predicate must leave objects, events, commit, receipt and head
unchanged. Concurrent parent drift rejects before mutation. Read-only model
state equality cannot stand in for durable crash/race/reject atomicity tests.

## Remaining closure evidence

Executable design controls cover purpose/result/prior-only/exact scope,
schema/hash identity, separate actor/authority pins, exact authenticated
action/scope, installation profile purpose, cut mismatch and current
eligibility rejection. These are finite model controls with assumed trusted
snapshots, not accepted-history replay, installed qualification or runtime
acceptance evidence. Full per-kind review remains pending until every source
paragraph and dependency is bound to its implementation and durable guards.
SOURCE_MEMBER scope_ref projection beyond an exact prior scope record still
requires field-specific proof; no fallback projection is authorized here.

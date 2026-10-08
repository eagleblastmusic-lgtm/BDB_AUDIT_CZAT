# HistoryCut/2 contextual obligations — draft review

Source: qualified R5.4.1 Data section 15, especially 15.1–15.4; exact source digest is retained in the semantic queue. OD-021 already specifies the branch representation. This review does not reopen that decision or introduce a new tagged accepted branch: the inherited accepted tuple has no `kind` property. It is a value, not an independently accepted transition fact.

## Empty branch

Trigger: `kind=EMPTY_HISTORY_CUT`. Required fields are exactly kind, history_namespace_ref, governing_policy_ref and governing_spec_refs. campaign_id, accepted_head_seq and accepted_head_hash are forbidden. No synthetic head or zero digest may stand for the empty namespace.

Resolve the independently qualified exact installation_bootstrap_profile/1 before any command validation. Require the namespace ref to equal its allowed_history_namespace_ref, policy to equal its initial_governing_policy_ref, and the spec array to equal the one-element array containing its initial_transition_profile_ref. Compare complete references, including schema pins and object digests, not kind/logical ID alone. The successor profile continues to have a single initial_transition_profile_ref; no expanded initial spec set is inferred from the general 1..65536 array grammar.

Verify the namespace is empty at the atomic acceptance boundary and the consuming operation is the independently authorized initialization/bootstrap operation. Same-commit root materialization is legal only for bytes already authorized by qualified external installation pins. It does not satisfy a prior-history condition. Reject empty cuts used by ordinary post-genesis evidence, STOP or completion operations. Concurrent initialization is resolved through the exact empty-parent comparison at commit acceptance; serialization of this value cannot reserve a namespace or move its head.

## Accepted branch

Trigger: absence of kind and presence of the closed accepted tuple. Required fields are exactly campaign_id, accepted_head_seq, accepted_head_hash, governing_policy_ref and governing_spec_refs. kind and history_namespace_ref are forbidden. accepted_head_seq is a positive safe integer; the digest is the exact accepted commit hash.

Resolve that campaign/sequence/hash in canonical accepted history, within the consuming operation's independently resolved campaign and namespace. Reject absent, uncommitted, cross-campaign, future or mismatched hash/sequence bindings. Resolve active policy and transition-spec revisions by replay at that exact head. Require complete reference equality and exact sorted spec-set equality with that independently resolved context. A policy/spec introduced by the current accepting command cannot validate that command. SchemaRegistry is not a transition-spec substitute. The permitted exact successor families are policy_revision/2 and spec_revision/2 through qualified schema bindings; a kind string alone is insufficient.

A cut may name a historical accepted head. Whether a consumer requires the current parent, assignment cut, preregistration cut or another exact prior cut is a separate field-specific obligation; do not globally accept every historical cut as current and do not globally require every historical cut to equal the latest head. The consuming contract must select one exact cut and independently establish its temporal and source applicability. No caller-selected latest fallback exists.

## Failures, authority and mutation

Positive result requires both exact branch grammar and every branch/context prerequisite. Missing history, missing installation qualification, unresolved schema/profile, unknown active binding, insufficient evidence or blocked context cannot become a valid cut. Wrong-purpose schema/profile refs reject. There is no waiver, materiality exception or caller trust flag that can legalize a false cut. Failure rejects the consuming authority-changing operation with no new canonical objects, events, receipt or head effect; pre-existing canonical bytes remain unchanged. Building or reading a valid cut itself has no canonical mutation effect.

The input domain is an exact cut plus independently obtained installation or accepted-history context and the consumer's exact input-cut selection contract. The output domain is VALID or REJECT for cut validity; consumer scientific UNKNOWN/BLOCKED/INSUFFICIENT statuses are retained by that consumer and cannot authorize acceptance requiring VALID. The evaluator is the qualified coordinator/validator at the durable boundary, not the serialized cut producer. Exact reference schema binding must be verified before equality or replay can confer authority.

## Remaining evidence before closure

This is a contextual review, not a complete per-kind parity approval. Registry generation must preserve IMMUTABLE_VALUE semantics and the branch-specific installation/history distinction; executable reference validation must reject wrong successor schema bindings. Required tests include empty namespace reuse/race, wrong bootstrap namespace/policy/spec, extra initial spec, hybrid tuples, unknown/future/uncommitted head, cross-campaign head, old policy at a newer cut, policy introduced by the same command, wrong-purpose spec, historical cut accepted only for its declared consumer purpose, consumer stale-cut rejection, and reject atomicity. Accepted-instance chronology/DAG and durable guard proofs remain open. Do not mark the queue node reviewed solely from this document.

# Command closure: scoped source/body/reference review

This review continues OD-016/024; it does not introduce a new owner decision,
complete a semantic node, activate a successor, or qualify an accepted instance.
The governing sources are qualified Data 15.1–15.2, Data 2, the existing
COMMAND_EVENT_CONTRACT.md and explicit resolved command material-reference rows.

The successor command body has four closed command kinds and an inline closed
payload. The payload's proposed_object_refs names 128 declared eligible kinds;
command_envelope, commit_body and command_receipt are excluded by the field's
specialized enum, even though the shared typed_ref definition contains them.
Reading only that shared definition would incorrectly report a target-domain gap.
Proposed objects and artifact event refs are CONTENT_OBJECT, same_commit=true.
They therefore contribute dependency-to-command edges. Payload events must equal
the independently derived acceptance/transition event sequence, not a caller's
successful-looking list. Complete typed identity, source/schema/hash equality,
closure membership, duplicate rejection and authorized production remain required.

The command itself belongs to the commit closure and its exact digest/ref and
copied context must match the CommitBody. Its accepting commit and receipt remain
external to its inputs. Command-first is not a global ready-node tie-break or a
global CommitBody predicate. Current runtime corrections remove those two hidden
requirements. The installed predecessor bootstrap profile still contributes
scoped command-first order-only edges; the current store also retains a first-
commit command-first assertion. OD-024 V2 integration must remove or derive that
assertion from its exact selected profile. Removing profile edges alone is
insufficient. No independently installed V2 runtime selection is established here.

Initialization requires empty parent and independently qualified namespace and
bootstrap profile pins, forbids campaign_ref, and supplies a proposed campaign
identity. Ordinary commands require exact prior campaign/parent and forbid
initialization-only fields. Actor authorization is independently authenticated;
policy/spec bindings resolve the qualified context, including externally installed
initial context before campaign history. Caller strings and matching hashes never
install their own authority. InstallationRootPinned records independently authorized
bytes only at initialization; generic ArtifactAccepted cannot admit trust roots.

Transition aggregate/basis refs and AttemptStarted attempt/assignment/binding refs
are PRIOR_ACCEPTED_ONLY, same_commit=false. A generic same-commit fact or payload
event cannot supply that prior authorization. Gate target/result refs permit
CONTENT_OR_PRIOR only with the independently validated gate context; this does not
waive a target's own prior-only prerequisites. Ordinary same-commit payload refs
and prior transition authority must not be conflated when constructing the union DAG.

Remaining proof: exact actual successor bodies and refs; independently qualified
root/activation/source/build context under OD-027; active Registry/schema identity;
complete typed plus selected order-only instance DAG; deterministic event derivation;
actual trusted ingestion and authenticated actor dispatch; durable rejection,
retry/race/crash atomicity. Syntax and the current runtime ordering tests do not
prove these successor predicates. The semantic queue remains pending.

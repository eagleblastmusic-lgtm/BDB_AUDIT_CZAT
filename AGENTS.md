# AGENTS.md — BDB Audit v2 local implementation rules

## Repository boundary
- Work only in the local `eagleblastmusic-lgtm/bdb-audit` repository.
- `main` is the frozen legacy line. Do not modify, rewrite, reset, or force-update it.
- Active v2 work is on `bdb-v2` unless a task explicitly names another branch.
- Never edit files under `legacy/v1_4_4/` except when a task explicitly concerns preservation metadata and the normative plan authorizes that exact change. For normal implementation tasks, treat the frozen legacy bytes as immutable.
- Do not push, open a PR, merge, tag, or change remote refs unless the task explicitly asks for that action. Local edits and local tests are allowed.

## Authority and scope
- Priority order: correctness; safety and fail-closed behavior; normative compliance; repository and evidence integrity; required milestone qualification and gates; compute/allowance efficiency; wall-clock speed. Efficiency never overrides assurance; conflicting higher-priority requirements must be resolved, not bypassed.
- Implement only the task/milestone named in the current prompt. Do not start the next milestone “while you are here”.
- R5.3 normative semantics outrank convenience, legacy behavior, optimization ideas, and implementation shortcuts. Task-scoped CODEX context is navigation, not normative authority.
- Consult the exact authoritative R5.3 source(s) for missing semantics, ambiguity, wording-sensitive behavior, possible conflicts, explicit source references, machine contracts, Registry data, Golden Vectors, or required source identity. Read complete relevant sections and dependencies; do not reread all normative documents for every local change or scan historical archives without a task-relevant reason. Use scoped context for navigation and already-established requirements, never as a substitute for unresolved normative semantics.
- Legacy observed behavior is an oracle for preservation only, never automatically for correctness.
- Do not modify R5.3 normative documents, the author baseline qualification record, or the frozen candidate identity as part of coding tasks.
- If the task packet and a full normative source conflict, use the full normative source and report the conflict. Do not silently reconcile it.
- If a material ambiguity prevents a safe implementation, stop expansion and report `SPEC_CONFLICT` with the exact conflicting requirements. Do not patch around an ambiguity with an ad hoc special case.

## Engineering rules
- Keep changes minimal and task-scoped. Reuse existing mechanisms where they satisfy the contract.
- Do not add a production dependency unless the current task requires it and the prompt explicitly permits it.
- Never create a second authority, mutable head, cache-as-authority, or “latest by logical ID” shortcut for authority-bearing decisions.
- Preserve exact bytes and digests where the contract says they are identity-bearing.
- Do not weaken fail-closed behavior to make tests pass.
- Do not change error/decision semantics merely for performance.

## Verification
- Before editing, inspect `git status`, current branch, current HEAD, and relevant existing tests/instructions.
- Never discard unrelated local user changes. If they overlap the task, report the conflict rather than resetting them.
- Escalate by impact: targeted failure/change tests, affected component/work-package checks, cross-cutting checks where justified, required milestone qualification, then required post-commit verification. This is not a limit on runs; a narrow PASS never replaces a mandatory gate.
- Changes to canonical serialization, hashing, RawDigest/ObjectDigest, typed IDs/references, Registry, shared validators/schemas/configuration, fixtures, Golden Vectors, the compatibility harness or qualification verifier require assessment of all dependent evidence and broader verification of affected paths. Apply the same rule to authority, history and orchestration infrastructure.
- Reuse BDB verification only when the governing contract permits it and recorded evidence still binds the implementation/dependency blobs, exact raw hashes, fixtures, Registry, Golden Vectors, harness/verifier, schemas/configuration, qualification inputs and environment-sensitive execution conditions, each only where relevant/applicable to the evidence being reused. An unchanged HEAD alone is insufficient; uncertainty requires the appropriate rerun. Evidence is never runtime authority.
- A required post-commit phase verifier is terminal evidence only if it checks the intended committed state, transitively covers every mandatory subordinate check, validates the qualification artifact and required identity/drift conditions, and passes with no relevant input changing afterward. Otherwise run the missing checks; repeat covered checks only for a justified new uncertainty or an explicit contract requirement.
- Report exact commands and results. If a required check cannot run, say why and provide the strongest local substitute.
- Before finishing, inspect the diff for out-of-scope changes and accidental modifications to frozen legacy material.

## Final report
Return a concise implementation report containing: changed files, behavior implemented, tests/commands/results, acceptance-gate status, and any unresolved blockers or spec conflicts. Do not claim a gate PASS unless every named condition is evidenced.

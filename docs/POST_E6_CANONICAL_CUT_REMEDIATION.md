# Audyt 2.0 — POST_E6 canonical accepted-cut remediation

This remediation aligns the adaptive E6 return-to-STOP boundary with the canonical R5.3 accepted-history wire contract.

## Enforced invariants

- both pre-E6 and post-E6 cuts are canonical `ACCEPTED_HISTORY_CUT` values;
- legacy `{commit_seq, commit_hash}` dictionaries are not accepted as authority;
- POST_E6 stays in the same campaign;
- the post-E6 accepted head must have a strictly greater `accepted_head_seq` and a different `accepted_head_hash`;
- the next control point remains global STOP on that newer accepted head.

This document is descriptive only. Executable authority remains in the implementation, tests, pinned registry/contracts, and exact-SHA qualification evidence.

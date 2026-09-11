"""Evidence independence assessment and invalidation propagation engine (M20)."""
from typing import Any, Sequence, Set

from ..core.errors import ValidationError
from .models import EvidenceInvalidation


def check_independence_claim(
    shared_dependencies: Sequence[Any],
    claimed_independent: Sequence[Any],
) -> dict:
    """Verify that claimed independent dependencies do not overlap with shared dependencies.

    Roadmap §62–63:
    Two processes using the same faulty parser / oracle / storage read path
    CANNOT claim independence.
    """
    def extract_key(item: Any) -> str:
        if isinstance(item, dict):
            return item.get("revision_digest") or item.get("logical_id") or str(item)
        return str(item)

    shared_set = {extract_key(x) for x in shared_dependencies}
    independent_set = {extract_key(x) for x in claimed_independent}

    overlap = shared_set & independent_set
    if overlap:
        raise ValidationError(
            "SHARED_ORACLE_INDEPENDENCE_REJECTED",
            f"Claimed independent dependencies overlap with shared dependencies: {overlap}",
        )

    return {
        "result": "INDEPENDENT",
        "shared_dependencies": sorted(shared_set),
        "independent_dependencies": sorted(independent_set),
    }


def propagate_invalidation_to_qualifications(
    invalidation: EvidenceInvalidation,
    qualification_records: Sequence[dict],
) -> list[dict]:
    """Propagate invalidation to dependent coverage/evidence qualifications.

    Invalidated evidence degrades qualification status from QUALIFIED to STALE or BLOCKED.
    """
    invalidated_digests: Set[str] = set()
    for ref_dict in invalidation.affected_evidence_or_qualification_refs:
        if isinstance(ref_dict, dict) and "revision_digest" in ref_dict:
            invalidated_digests.add(ref_dict["revision_digest"])
        elif isinstance(ref_dict, str):
            invalidated_digests.add(ref_dict)

    updated = []
    for q in qualification_records:
        q_copy = dict(q)
        # Check if any evidence ref in q matches an invalidated digest
        ev_refs = q_copy.get("evidence_qualification_refs", [])
        ev_digests = {r.get("revision_digest") for r in ev_refs if isinstance(r, dict)}
        if ev_digests & invalidated_digests or q_copy.get("qualification_id") in invalidated_digests:
            q_copy["qualification_status"] = "STALE"
            q_copy["degraded_by_invalidation"] = True
            q_copy["satisfies_completion"] = False
        updated.append(q_copy)

    return updated

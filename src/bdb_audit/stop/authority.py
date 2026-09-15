"""Trusted STOP-input equality checks against canonical accepted history.

Every accepted-content ref used to justify authoritative STOP must occur in the
parent accepted commit chain. HISTORY_CONTEXT_BINDING refs remain governed by
their pinned semantic context contract and are not misclassified as content.
"""
from __future__ import annotations

import json
from typing import Any

from ..core.errors import ValidationError
from ..history.objects import ACCEPTED_HEAD_REF, EMPTY_HISTORY, AcceptedHead, CanonicalObject


_ACCEPTED_CONTENT_FIELDS = (
    "source_generation_ref",
    "inventory_revision_ref",
    "mandatory_obligation_refs",
    "current_obligation_qualification_refs",
    "evidence_invalidation_refs",
    "contradiction_refs",
    "candidate_assurance_case_ref",
    "challenger_refs",
    "completed_stage_refs",
)


def _iter_refs(value: Any):
    if isinstance(value, dict) and {"kind", "revision_digest", "schema_revision_ref"}.issubset(value):
        yield value
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_refs(child)


def _accepted_index(current: AcceptedHead, con) -> dict[tuple[str, str], dict[str, Any]]:
    previous: Any = EMPTY_HISTORY
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for stored_seq, digest, raw in con.execute(
        "SELECT seq,commit_hash,body FROM commits WHERE seq<=? ORDER BY seq", (current.commit_seq,)
    ):
        body = json.loads(raw)
        from ..history.store import _commit_from_body
        commit = _commit_from_body(body)
        if commit.digest != digest or body["commit_seq"] != stored_seq or body["prev_history_ref"] != previous:
            raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
        if body["campaign_id"] != current.campaign_id:
            raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
        previous = {"tag": ACCEPTED_HEAD_REF, "campaign_id": current.campaign_id,
                    "commit_seq": stored_seq, "commit_hash": digest}
        for ref in body.get("immutable_object_refs", ()):
            kind = ref.get("kind")
            revision_digest = ref.get("revision_digest")
            if isinstance(kind, str) and isinstance(revision_digest, str):
                index[(kind, revision_digest)] = {"ref": ref, "accepted_seq": stored_seq}
    if previous != {"tag": ACCEPTED_HEAD_REF, **current.as_dict()}:
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    return index


def _resolve(ref: dict[str, Any], index: dict[tuple[str, str], dict[str, Any]], con) -> dict[str, Any]:
    key = (ref.get("kind"), ref.get("revision_digest"))
    membership = index.get(key)
    if membership is None:
        raise ValidationError("STOP_INPUT_REFERENCE_NOT_ACCEPTED", str(key))
    accepted_ref = membership["ref"]
    for field in ("kind", "revision_digest", "schema_revision_ref", "logical_id", "digest_profile"):
        if accepted_ref.get(field) != ref.get(field):
            raise ValidationError("STOP_INPUT_REFERENCE_IDENTITY_MISMATCH", field)
    row = con.execute(
        "SELECT kind,version,schema_ref,logical_id,body FROM immutable_objects WHERE digest=?",
        (ref["revision_digest"],),
    ).fetchone()
    if row is None:
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    obj = CanonicalObject(row[0], json.loads(row[4]), row[2], row[3], row[1])
    if (obj.digest != ref["revision_digest"] or obj.kind != ref["kind"]
            or obj.schema_revision_ref != ref["schema_revision_ref"]
            or obj.logical_id != ref.get("logical_id")):
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    return {"body": obj.body, "accepted_seq": membership["accepted_seq"], "ref": accepted_ref}


def _summary_int(summary: dict[str, Any], key: str) -> int:
    value = summary.get(key)
    if type(value) is not int or value < 0:
        raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", key)
    return value


def validate_stop_input_accepted_authority(stop_obj: CanonicalObject, *, current: AcceptedHead | None, con) -> None:
    """Equality-check one prepared StopInput against its parent accepted cut."""
    if stop_obj.kind != "stop_input":
        return
    if current is None:
        raise ValidationError("STOP_INPUT_REQUIRES_ACCEPTED_PARENT")
    body = stop_obj.body
    cut = body.get("input_history_cut", {})
    if (cut.get("variant") != "ACCEPTED_HISTORY_CUT" or cut.get("campaign_id") != current.campaign_id
            or cut.get("accepted_head_seq") != current.commit_seq
            or cut.get("accepted_head_hash") != current.commit_hash):
        raise ValidationError("STOP_INPUT_CUT_MISMATCH")

    index = _accepted_index(current, con)
    resolved: dict[tuple[str, str], dict[str, Any]] = {}
    for field in _ACCEPTED_CONTENT_FIELDS:
        value = body.get(field)
        if value is None:
            continue
        for ref in _iter_refs(value):
            key = (ref["kind"], ref["revision_digest"])
            resolved[key] = _resolve(ref, index, con)

    invalidation_refs = [ref for ref in body.get("evidence_invalidation_refs", ()) if isinstance(ref, dict)]
    invalidation_state = body.get("evidence_invalidation_state")
    if not isinstance(invalidation_state, dict) or invalidation_state.get("invalidated_count") != len(invalidation_refs):
        raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", "evidence_invalidation_state")

    if body.get("evaluation_context") == "INTERMEDIATE":
        return

    mandatory_refs = [ref for ref in body.get("mandatory_obligation_refs", ()) if isinstance(ref, dict)]
    mandatory_digests = {ref.get("revision_digest") for ref in mandatory_refs}
    qualification_refs = [ref for ref in body.get("current_obligation_qualification_refs", ()) if isinstance(ref, dict)]
    qualification_by_obligation: dict[str, dict[str, Any]] = {}
    for ref in qualification_refs:
        row = resolved[(ref["kind"], ref["revision_digest"])]
        target = row["body"].get("obligation_revision_ref")
        target_digest = target.get("revision_digest") if isinstance(target, dict) else None
        if target_digest not in mandatory_digests:
            raise ValidationError("STOP_QUALIFICATION_OBLIGATION_MISMATCH")
        if target_digest in qualification_by_obligation:
            raise ValidationError("STOP_QUALIFICATION_BINDING_AMBIGUOUS")
        qualification_by_obligation[target_digest] = row

    expected: dict[str, Any] = {
        "qualification_binding_verified": set(qualification_by_obligation) == mandatory_digests,
        "unqualified_mandatory_obligations_count": len(mandatory_digests - set(qualification_by_obligation)),
        "blocked_qualification_count": 0,
        "stale_qualification_count": 0,
        "in_progress_qualification_count": 0,
        "inconclusive_qualification_count": 0,
        "violation_confirmed_count": 0,
    }
    for row in qualification_by_obligation.values():
        qbody = row["body"]
        status = qbody.get("qualification_status")
        outcome = qbody.get("substantive_outcome")
        if status != "QUALIFIED":
            expected["qualification_binding_verified"] = False
            expected["unqualified_mandatory_obligations_count"] += 1
        if status == "BLOCKED":
            expected["blocked_qualification_count"] += 1
        elif status == "STALE":
            expected["stale_qualification_count"] += 1
        elif status in {"UNASSESSED", "IN_PROGRESS"}:
            expected["in_progress_qualification_count"] += 1
        if outcome == "INCONCLUSIVE":
            expected["inconclusive_qualification_count"] += 1
        elif outcome == "VIOLATION_CONFIRMED":
            expected["violation_confirmed_count"] += 1

    candidate_ref = body.get("candidate_assurance_case_ref")
    candidate_digest = candidate_ref.get("revision_digest") if isinstance(candidate_ref, dict) else None
    challenger_refs = [ref for ref in body.get("challenger_refs", ()) if isinstance(ref, dict)]
    roles: set[str] = set()
    challenger_counts = {"challenger_blocked_count": 0, "challenger_inconclusive_count": 0,
                         "challenger_material_counterevidence_count": 0}
    for ref in challenger_refs:
        result_row = resolved[(ref["kind"], ref["revision_digest"])]
        result_body = result_row["body"]
        if result_body.get("candidate_assurance_case_ref", {}).get("revision_digest") != candidate_digest:
            raise ValidationError("STOP_CHALLENGER_CANDIDATE_MISMATCH")
        assignment_ref = result_body.get("challenge_assignment_ref")
        if not isinstance(assignment_ref, dict):
            raise ValidationError("STOP_CHALLENGER_ASSIGNMENT_MISSING")
        assignment_row = _resolve(assignment_ref, index, con)
        if assignment_row["body"].get("candidate_assurance_case_ref", {}).get("revision_digest") != candidate_digest:
            raise ValidationError("STOP_CHALLENGER_CANDIDATE_MISMATCH")
        role = assignment_row["body"].get("challenger_type")
        if role in {"FALSE_POSITIVE_SKEPTIC", "FALSE_NEGATIVE_HUNTER"}:
            if role in roles:
                raise ValidationError("STOP_CHALLENGER_ROLE_AMBIGUOUS")
            roles.add(role)
        status = result_body.get("status")
        if status == "BLOCKED":
            challenger_counts["challenger_blocked_count"] += 1
        elif status == "INCONCLUSIVE":
            challenger_counts["challenger_inconclusive_count"] += 1
        elif status == "MATERIAL_COUNTEREVIDENCE_FOUND":
            challenger_counts["challenger_material_counterevidence_count"] += 1
    expected["challenger_binding_verified"] = roles == {"FALSE_POSITIVE_SKEPTIC", "FALSE_NEGATIVE_HUNTER"}
    expected.update(challenger_counts)

    summary = body.get("unknown_blocked_summary")
    if not isinstance(summary, dict):
        raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", "unknown_blocked_summary")
    for key, value in expected.items():
        if isinstance(value, bool):
            if summary.get(key) is not value:
                raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", key)
        elif _summary_int(summary, key) != value:
            raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", key)

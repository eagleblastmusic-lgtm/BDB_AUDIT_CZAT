"""Trusted STOP-input equality checks against canonical accepted history.

Every accepted-content ref used to justify authoritative STOP must occur in the
parent accepted commit chain.  Final STOP additionally has to equal the current
accepted projection: stale-but-accepted refs, omitted blockers, cardinality-only
coverage and self-declared proof flags are not authority.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from ..core.canonical_json import canonical_bytes
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


def _digest_set(values: Iterable[dict[str, Any]]) -> set[str]:
    return {
        value.get("revision_digest")
        for value in values
        if isinstance(value, dict) and isinstance(value.get("revision_digest"), str)
    }


def _identity_digest(value: str) -> str:
    text = str(value)
    if len(text) == 64 and all(ch in "0123456789abcdef" for ch in text.lower()):
        return text.lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ref(
    kind: str,
    digest: str,
    ref_class: str,
    *,
    schema_ref: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": schema_ref or f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
    }


def _history_context_ref(kind: str, token: str) -> dict[str, Any]:
    return _ref(kind, _identity_digest(token), "HISTORY_CONTEXT_BINDING")


def _derived_profile_ref(label: str, payload: Any) -> dict[str, Any]:
    digest = hashlib.sha256(label.encode("utf-8") + b"\0" + canonical_bytes(payload)).hexdigest()
    return _ref(
        "external_profile_ref",
        digest,
        "HISTORY_CONTEXT_BINDING",
        schema_ref="BDB_TARGET/external_profile_ref",
    )


def _derived_registered_ref(label: str, payload: Any) -> dict[str, Any]:
    digest = hashlib.sha256(label.encode("utf-8") + b"\0" + canonical_bytes(payload)).hexdigest()
    return _ref(
        "registered_immutable_object",
        digest,
        "CONTENT_OR_PRIOR",
        schema_ref="BDB_TARGET/registered_immutable_object",
    )


def _accepted_index(current: AcceptedHead, con) -> dict[tuple[str, str], dict[str, Any]]:
    """Return first-acceptance membership for the verified parent chain."""
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
        previous = {
            "tag": ACCEPTED_HEAD_REF,
            "campaign_id": current.campaign_id,
            "commit_seq": stored_seq,
            "commit_hash": digest,
        }
        for accepted_ref in body.get("immutable_object_refs", ()):
            kind = accepted_ref.get("kind")
            revision_digest = accepted_ref.get("revision_digest")
            if isinstance(kind, str) and isinstance(revision_digest, str):
                index.setdefault(
                    (kind, revision_digest),
                    {"ref": accepted_ref, "accepted_seq": stored_seq},
                )
    if previous != {"tag": ACCEPTED_HEAD_REF, **current.as_dict()}:
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    return index


def _resolve(
    ref: dict[str, Any],
    index: dict[tuple[str, str], dict[str, Any]],
    con,
) -> dict[str, Any]:
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
    if (
        obj.digest != ref["revision_digest"]
        or obj.kind != ref["kind"]
        or obj.schema_revision_ref != ref["schema_revision_ref"]
        or obj.logical_id != ref.get("logical_id")
    ):
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    return {"body": obj.body, "accepted_seq": membership["accepted_seq"], "ref": accepted_ref}


def _records(kind: str, index: dict[tuple[str, str], dict[str, Any]], con) -> tuple[dict[str, Any], ...]:
    rows = []
    for (candidate_kind, _), membership in index.items():
        if candidate_kind == kind:
            rows.append(_resolve(membership["ref"], index, con))
    return tuple(sorted(rows, key=lambda row: (int(row["accepted_seq"]), row["ref"]["revision_digest"])))


def _latest(rows: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    values = tuple(rows)
    return max(values, key=lambda row: int(row["accepted_seq"])) if values else None


def _latest_by(rows: Iterable[dict[str, Any]], key_fn) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = key_fn(row)
        if not key:
            continue
        prior = selected.get(key)
        if prior is None or int(row["accepted_seq"]) > int(prior["accepted_seq"]):
            selected[key] = row
    return selected


def _summary_int(summary: dict[str, Any], key: str) -> int:
    value = summary.get(key)
    if type(value) is not int or value < 0:
        raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", key)
    return value


def _require_ref_digest(actual: Any, expected: dict[str, Any] | None, field: str) -> None:
    if expected is None:
        if actual is not None:
            raise ValidationError("STOP_CURRENT_PROJECTION_MISMATCH", field)
        return
    if not isinstance(actual, dict) or actual.get("revision_digest") != expected.get("revision_digest"):
        raise ValidationError("STOP_CURRENT_PROJECTION_MISMATCH", field)


def _require_digest_set(actual: Any, expected: Iterable[dict[str, Any]], field: str) -> None:
    actual_values = actual if isinstance(actual, (list, tuple)) else ()
    if _digest_set(actual_values) != _digest_set(expected):
        raise ValidationError("STOP_CURRENT_PROJECTION_MISMATCH", field)


def validate_stop_input_accepted_authority(
    stop_obj: CanonicalObject,
    *,
    current: AcceptedHead | None,
    con,
) -> None:
    """Equality-check one prepared StopInput against its parent accepted cut."""
    if stop_obj.kind != "stop_input":
        return
    if current is None:
        raise ValidationError("STOP_INPUT_REQUIRES_ACCEPTED_PARENT")

    body = stop_obj.body
    cut = body.get("input_history_cut", {})
    if (
        cut.get("variant") != "ACCEPTED_HISTORY_CUT"
        or cut.get("campaign_id") != current.campaign_id
        or cut.get("accepted_head_seq") != current.commit_seq
        or cut.get("accepted_head_hash") != current.commit_hash
    ):
        raise ValidationError("STOP_INPUT_CUT_MISMATCH")

    index = _accepted_index(current, con)
    resolved: dict[tuple[str, str], dict[str, Any]] = {}
    for field in _ACCEPTED_CONTENT_FIELDS:
        value = body.get(field)
        if value is None:
            continue
        for ref_value in _iter_refs(value):
            key = (ref_value["kind"], ref_value["revision_digest"])
            resolved[key] = _resolve(ref_value, index, con)

    invalidation_state = body.get("evidence_invalidation_state")
    if not isinstance(invalidation_state, dict):
        raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", "evidence_invalidation_state")

    # INTERMEDIATE can never PASS. Content membership and snapshot/cut checks are
    # still enforced, but final-state equality is intentionally deferred.
    if body.get("evaluation_context") == "INTERMEDIATE":
        invalidation_refs = [ref for ref in body.get("evidence_invalidation_refs", ()) if isinstance(ref, dict)]
        if invalidation_state.get("invalidated_count") != len(invalidation_refs):
            raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", "evidence_invalidation_state")
        return

    # ------------------------------------------------------------------
    # Source generation and current inventory must be exact current refs.
    # ------------------------------------------------------------------
    genesis_rows = _records("campaign_genesis", index, con)
    if len(genesis_rows) != 1:
        raise ValidationError("STOP_CURRENT_PROJECTION_MISMATCH", "campaign_genesis")
    genesis_source = genesis_rows[0]["body"].get("source_generation_ref")
    if not isinstance(genesis_source, dict):
        raise ValidationError("STOP_CURRENT_PROJECTION_MISMATCH", "source_generation_ref")
    _require_ref_digest(body.get("source_generation_ref"), genesis_source, "source_generation_ref")

    inventory_row = _latest(_records("inventory_revision", index, con))
    if inventory_row is None:
        raise ValidationError("STOP_CURRENT_PROJECTION_MISMATCH", "inventory_revision_ref")
    _require_ref_digest(body.get("inventory_revision_ref"), inventory_row["ref"], "inventory_revision_ref")

    # ------------------------------------------------------------------
    # Required stage plan and completions: no omitted or fabricated progress.
    # ------------------------------------------------------------------
    required_keys = {"E1", "E2", "E3", "E4", "E5"}
    if body.get("evaluation_context") == "POST_E6":
        required_keys.add("E6")
    current_specs = _latest_by(
        _records("stage_spec", index, con),
        lambda row: str(row["body"].get("stage_key") or ""),
    )
    selected_specs = {
        key: row for key, row in current_specs.items() if key in required_keys
    }
    missing_stage_keys = sorted(required_keys - set(selected_specs))
    expected_stage_spec_refs = [row["ref"] for _, row in sorted(selected_specs.items())]
    _require_digest_set(body.get("required_stage_spec_refs"), expected_stage_spec_refs, "required_stage_spec_refs")

    spec_key_by_digest = {
        row["ref"]["revision_digest"]: key for key, row in selected_specs.items()
    }
    completion_candidates: dict[str, list[dict[str, Any]]] = {}
    for row in _records("stage_completion", index, con):
        completion_body = row["body"]
        if completion_body.get("completion_predicate_result") != "STAGE_COMPLETED":
            continue
        spec_ref = completion_body.get("stage_spec_ref")
        spec_digest = spec_ref.get("revision_digest") if isinstance(spec_ref, dict) else None
        stage_key = spec_key_by_digest.get(spec_digest)
        if stage_key:
            completion_candidates.setdefault(stage_key, []).append(row)

    current_completions: dict[str, dict[str, Any]] = {}
    for stage_key, rows in completion_candidates.items():
        distinct = {row["ref"]["revision_digest"] for row in rows}
        if len(distinct) > 1:
            raise ValidationError("STOP_STAGE_COMPLETION_AMBIGUOUS", stage_key)
        current_completions[stage_key] = _latest(rows)  # type: ignore[assignment]

    expected_completion_refs = [row["ref"] for _, row in sorted(current_completions.items())]
    _require_digest_set(body.get("completed_stage_refs"), expected_completion_refs, "completed_stage_refs")
    expected_pending_refs = [
        row["ref"]
        for key, row in sorted(selected_specs.items())
        if key not in current_completions
    ]
    _require_digest_set(body.get("pending_required_stage_refs"), expected_pending_refs, "pending_required_stage_refs")

    required_stage_set_ref = _derived_profile_ref(
        "required-stage-set",
        {
            "required_stage_keys": sorted(required_keys),
            "accepted_stage_spec_digests": [
                ref["revision_digest"] for ref in body.get("required_stage_spec_refs", ())
            ],
            "missing_stage_keys": missing_stage_keys,
        },
    )
    if body.get("required_stage_set_ref") != required_stage_set_ref:
        raise ValidationError("STOP_CURRENT_PROJECTION_MISMATCH", "required_stage_set_ref")

    # ------------------------------------------------------------------
    # Mandatory obligation denominator and exact latest qualifications.
    # ------------------------------------------------------------------
    current_obligations = _latest_by(
        _records("coverage_obligation", index, con),
        lambda row: str(row["body"].get("obligation_id") or row["ref"]["revision_digest"]),
    )
    expected_obligation_refs = [row["ref"] for _, row in sorted(current_obligations.items())]
    _require_digest_set(body.get("mandatory_obligation_refs"), expected_obligation_refs, "mandatory_obligation_refs")
    mandatory_digests = _digest_set(expected_obligation_refs)

    latest_qualification_by_obligation: dict[str, dict[str, Any]] = {}
    for row in _records("coverage_obligation_qualification", index, con):
        target = row["body"].get("obligation_revision_ref")
        target_digest = target.get("revision_digest") if isinstance(target, dict) else None
        if target_digest not in mandatory_digests:
            continue
        prior = latest_qualification_by_obligation.get(target_digest)
        if prior is None or int(row["accepted_seq"]) > int(prior["accepted_seq"]):
            latest_qualification_by_obligation[target_digest] = row
    expected_qualification_refs = [
        row["ref"] for _, row in sorted(latest_qualification_by_obligation.items())
    ]
    _require_digest_set(
        body.get("current_obligation_qualification_refs"),
        expected_qualification_refs,
        "current_obligation_qualification_refs",
    )

    expected_summary: dict[str, Any] = {
        "missing_required_stage_specs_count": len(missing_stage_keys),
        "qualification_binding_verified": set(latest_qualification_by_obligation) == mandatory_digests,
        "unqualified_mandatory_obligations_count": len(
            mandatory_digests - set(latest_qualification_by_obligation)
        ),
        "blocked_qualification_count": 0,
        "stale_qualification_count": 0,
        "in_progress_qualification_count": 0,
        "inconclusive_qualification_count": 0,
        "violation_confirmed_count": 0,
    }
    for row in latest_qualification_by_obligation.values():
        qbody = row["body"]
        status = qbody.get("qualification_status")
        outcome = qbody.get("substantive_outcome")
        if status != "QUALIFIED":
            expected_summary["qualification_binding_verified"] = False
            expected_summary["unqualified_mandatory_obligations_count"] += 1
        if status == "BLOCKED":
            expected_summary["blocked_qualification_count"] += 1
        elif status == "STALE":
            expected_summary["stale_qualification_count"] += 1
        elif status in {"UNASSESSED", "IN_PROGRESS"}:
            expected_summary["in_progress_qualification_count"] += 1
        if outcome == "INCONCLUSIVE":
            expected_summary["inconclusive_qualification_count"] += 1
        elif outcome == "VIOLATION_CONFIRMED":
            expected_summary["violation_confirmed_count"] += 1

    # ------------------------------------------------------------------
    # Current CandidateAssuranceCase and latest accepted baseline challengers.
    # ------------------------------------------------------------------
    candidate_row = _latest(_records("candidate_assurance_case", index, con))
    candidate_ref = candidate_row["ref"] if candidate_row is not None else None
    _require_ref_digest(body.get("candidate_assurance_case_ref"), candidate_ref, "candidate_assurance_case_ref")
    candidate_digest = candidate_ref.get("revision_digest") if candidate_ref else None

    assignments = {
        row["ref"]["revision_digest"]: row
        for row in _records("challenger_assignment", index, con)
        if row["body"].get("candidate_assurance_case_ref", {}).get("revision_digest") == candidate_digest
    }
    roles = {"FALSE_POSITIVE_SKEPTIC", "FALSE_NEGATIVE_HUNTER"}
    latest_result_by_role: dict[str, dict[str, Any]] = {}
    for row in _records("challenger_result", index, con):
        result_body = row["body"]
        if result_body.get("candidate_assurance_case_ref", {}).get("revision_digest") != candidate_digest:
            continue
        assignment_ref = result_body.get("challenge_assignment_ref")
        assignment_digest = assignment_ref.get("revision_digest") if isinstance(assignment_ref, dict) else None
        assignment = assignments.get(assignment_digest)
        if assignment is None:
            continue
        role = assignment["body"].get("challenger_type")
        if role not in roles:
            continue
        prior = latest_result_by_role.get(role)
        if prior is None or int(row["accepted_seq"]) > int(prior["accepted_seq"]):
            latest_result_by_role[role] = row

    expected_challenger_refs = [row["ref"] for _, row in sorted(latest_result_by_role.items())]
    _require_digest_set(body.get("challenger_refs"), expected_challenger_refs, "challenger_refs")
    expected_summary["challenger_binding_verified"] = set(latest_result_by_role) == roles
    expected_summary.update(
        {
            "challenger_blocked_count": 0,
            "challenger_inconclusive_count": 0,
            "challenger_material_counterevidence_count": 0,
        }
    )
    for row in latest_result_by_role.values():
        status = row["body"].get("status")
        if status == "BLOCKED":
            expected_summary["challenger_blocked_count"] += 1
        elif status == "INCONCLUSIVE":
            expected_summary["challenger_inconclusive_count"] += 1
        elif status == "MATERIAL_COUNTEREVIDENCE_FOUND":
            expected_summary["challenger_material_counterevidence_count"] += 1

    # ------------------------------------------------------------------
    # Open contradictions and evidence invalidations cannot be omitted.
    # ------------------------------------------------------------------
    current_contradictions = _latest_by(
        _records("contradiction_revision", index, con),
        lambda row: str(row["body"].get("contradiction_id") or row["ref"]["revision_digest"]),
    )
    resolved_statuses = {"RESOLVED", "RESOLVED_SCOPED", "RESOLVED_FULL"}
    expected_contradiction_refs = [
        row["ref"]
        for _, row in sorted(current_contradictions.items())
        if row["body"].get("status") not in resolved_statuses
    ]
    _require_digest_set(body.get("contradiction_refs"), expected_contradiction_refs, "contradiction_refs")

    invalidation_rows = _records("evidence_invalidation", index, con)
    expected_invalidation_refs = [row["ref"] for row in invalidation_rows]
    _require_digest_set(body.get("evidence_invalidation_refs"), expected_invalidation_refs, "evidence_invalidation_refs")
    if invalidation_state.get("invalidated_count") != len(expected_invalidation_refs):
        raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", "evidence_invalidation_state")

    # ------------------------------------------------------------------
    # Pinned semantic context and deterministic derived effort identities.
    # ------------------------------------------------------------------
    governing_policy_ref = _history_context_ref("policy_revision", str(cut.get("governing_policy_ref")))
    if body.get("governing_policy_ref") != governing_policy_ref or body.get("release_policy_ref") != governing_policy_ref:
        raise ValidationError("STOP_CURRENT_PROJECTION_MISMATCH", "governing_policy_ref")

    spec_tokens = tuple(str(value) for value in cut.get("governing_spec_refs", ()))
    expected_policy_specs = [_history_context_ref("spec_revision", token) for token in spec_tokens]
    _require_digest_set(body.get("policy_spec_refs"), expected_policy_specs, "policy_spec_refs")
    if expected_policy_specs:
        if body.get("evaluator_revision_ref") != expected_policy_specs[0]:
            raise ValidationError("STOP_CURRENT_PROJECTION_MISMATCH", "evaluator_revision_ref")

    completed_stage_refs = list(body.get("completed_stage_refs", ()))
    expected_effort_profile = _derived_profile_ref(
        "effort-profile",
        {"input_history_cut": cut, "completed_stage_refs": completed_stage_refs},
    )
    expected_effort_results = _derived_registered_ref(
        "effort-results",
        {"input_history_cut": cut, "completed_stage_refs": completed_stage_refs},
    )
    if body.get("effort_profile_ref") != expected_effort_profile:
        raise ValidationError("STOP_CURRENT_PROJECTION_MISMATCH", "effort_profile_ref")
    if body.get("effort_results_ref") != expected_effort_results:
        raise ValidationError("STOP_CURRENT_PROJECTION_MISMATCH", "effort_results_ref")

    # ------------------------------------------------------------------
    # Derived summary equality. Scope caller input may only be more conservative.
    # ------------------------------------------------------------------
    summary = body.get("unknown_blocked_summary")
    if not isinstance(summary, dict):
        raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", "unknown_blocked_summary")
    for key, value in expected_summary.items():
        if isinstance(value, bool):
            if summary.get(key) is not value:
                raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", key)
        elif _summary_int(summary, key) != value:
            raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", key)

    unresolved_scope_digests = {
        ref_value.get("revision_digest")
        for ref_value in inventory_row["body"].get("unresolved_scope_refs", ())
        if isinstance(ref_value, dict) and ref_value.get("revision_digest")
    }
    current_scope_rows = _latest_by(
        _records("scope_state_record", index, con),
        lambda row: str(row["body"].get("scope_key") or row["ref"]["revision_digest"]),
    )
    unknown_states = {"UNKNOWN_SCOPE", "PROVISIONAL_SCOPE", "KNOWN_UNOBSERVED_SCOPE"}
    blocked_states = {"UNSUPPORTED_SCOPE", "COLLECTION_FAILED", "PARSING_FAILED"}
    unknown_scope_keys = {
        row["body"].get("scope_key")
        for row in current_scope_rows.values()
        if row["body"].get("state") in unknown_states
    }
    minimum_unknown = max(len(unresolved_scope_digests), len(unknown_scope_keys))
    minimum_blocked = sum(
        1 for row in current_scope_rows.values() if row["body"].get("state") in blocked_states
    )
    if _summary_int(summary, "unknown_surfaces_count") < minimum_unknown:
        raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", "unknown_surfaces_count")
    if _summary_int(summary, "blocked_scope_count") < minimum_blocked:
        raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", "blocked_scope_count")
    if minimum_blocked and summary.get("is_blocked") is not True:
        raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", "is_blocked")
    if _summary_int(summary, "unresolved_obligations_count") < expected_summary[
        "unqualified_mandatory_obligations_count"
    ]:
        raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", "unresolved_obligations_count")

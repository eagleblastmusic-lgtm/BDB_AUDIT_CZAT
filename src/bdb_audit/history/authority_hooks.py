"""Explicit trusted-history authority extensions.

The durable adapter keeps generic registry/reference mechanics in ``store.py``.
Domain-specific equality checks are installed here on the same pre-durability
validation methods. Installation is idempotent and occurs during package import,
which Python executes before either ``bdb_audit.history`` or
``bdb_audit.history.store`` can be returned to a caller.
"""
from __future__ import annotations

from functools import wraps
import hashlib
import json
from typing import Any

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from .objects import ACCEPTED_HEAD_REF, EMPTY_HISTORY, CanonicalObject


def _validate_overlay_prior_accepted(self, ref, *, consumer_kind, current, con) -> None:
    """Prove PRIOR_ACCEPTED_ONLY membership for byte-pinned overlay kinds."""
    kind = ref.get("kind")
    baseline_kinds = {
        row["kind"]
        for row in self.registry.document.get("contracts", ())
        if isinstance(row, dict) and isinstance(row.get("kind"), str)
    }
    canonical_kinds = set(getattr(self.registry, "canonical_contract_kinds", baseline_kinds))
    if hasattr(self.registry, "_extension_contracts"):
        canonical_kinds.update(k for k, _ in self.registry._extension_contracts.keys())
    if kind in baseline_kinds or kind not in canonical_kinds:
        return

    error_code = self._prior_accepted_error_code(consumer_kind)
    if current is None:
        raise ValidationError(error_code, kind or "")

    from .store import _commit_from_body

    previous = EMPTY_HISTORY
    found = False
    for stored_seq, digest, raw in con.execute(
        "SELECT seq,commit_hash,body FROM commits WHERE seq<=? ORDER BY seq",
        (current.commit_seq,),
    ):
        body = json.loads(raw)
        commit = _commit_from_body(body)
        if (
            commit.digest != digest
            or body["commit_seq"] != stored_seq
            or body["prev_history_ref"] != previous
            or body["campaign_id"] != current.campaign_id
        ):
            raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
        previous = {
            "tag": ACCEPTED_HEAD_REF,
            "campaign_id": current.campaign_id,
            "commit_seq": stored_seq,
            "commit_hash": digest,
        }
        if any(
            candidate.get("revision_digest") == ref.get("revision_digest")
            and candidate.get("kind") == kind
            and candidate.get("schema_revision_ref") == ref.get("schema_revision_ref")
            and candidate.get("logical_id") == ref.get("logical_id")
            and candidate.get("digest_profile") == ref.get("digest_profile")
            for candidate in body.get("immutable_object_refs", ())
        ):
            found = True

    if previous != {"tag": ACCEPTED_HEAD_REF, **current.as_dict()}:
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    if not found:
        raise ValidationError(error_code, ref.get("revision_digest", ""))

    row = con.execute(
        "SELECT kind,version,schema_ref,logical_id,body FROM immutable_objects WHERE digest=?",
        (ref.get("revision_digest"),),
    ).fetchone()
    if row is None:
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    obj = CanonicalObject(row[0], json.loads(row[4]), row[2], row[3], row[1])
    if (
        obj.digest != ref.get("revision_digest")
        or obj.kind != kind
        or obj.schema_revision_ref != ref.get("schema_revision_ref")
        or obj.logical_id != ref.get("logical_id")
    ):
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")


def _prior_approval_body(ref, con) -> dict:
    row = con.execute(
        "SELECT kind,body FROM immutable_objects WHERE digest=?",
        (ref.get("revision_digest"),),
    ).fetchone()
    if row is None or row[0] != "approval_decision":
        raise ValidationError("RESIDUAL_RISK_APPROVAL_NOT_ACCEPTED")
    return json.loads(row[1])


def _validate_residual_risk_authority(obj, *, con) -> None:
    """§79 owner acceptance is authority only when the prior decision is APPROVED."""
    body = obj.body
    owner_ref = body.get("owner_approval_ref")
    if body.get("disposition") == "ACCEPTED_RESIDUAL_RISK" and not isinstance(owner_ref, dict):
        raise ValidationError("RESIDUAL_RISK_REQUIRES_APPROVAL")
    if isinstance(owner_ref, dict):
        if _prior_approval_body(owner_ref, con).get("decision") != "APPROVED":
            raise ValidationError("RESIDUAL_RISK_APPROVAL_NOT_APPROVED")


def _digest_set(refs) -> set[str]:
    return {
        ref.get("revision_digest")
        for ref in refs
        if isinstance(ref, dict) and isinstance(ref.get("revision_digest"), str)
    }


def _active_risk_rows(current, con):
    if current is None:
        return (), {}, None
    from ..stop.authority import _accepted_index, _latest_by, _records

    index = _accepted_index(current, con)
    current_risks = _latest_by(
        _records("residual_risk", index, con),
        lambda row: str(row["body"].get("risk_id") or row["ref"]["revision_digest"]),
    )
    rows = tuple(
        current_risks[key]
        for key in sorted(current_risks)
        if current_risks[key]["body"].get("disposition") != "SUPERSEDED"
    )
    return rows, current_risks, index


def _accepted_body(kind: str, digest: str | None, index, con) -> dict:
    if not isinstance(digest, str) or index is None or (kind, digest) not in index:
        raise ValidationError("FINALIZATION_REFERENCE_NOT_PRIOR_ACCEPTED", f"{kind}:{digest}")
    row = con.execute(
        "SELECT kind,version,schema_ref,logical_id,body FROM immutable_objects WHERE digest=?",
        (digest,),
    ).fetchone()
    if row is None or row[0] != kind:
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    obj = CanonicalObject(row[0], json.loads(row[4]), row[2], row[3], row[1])
    if obj.digest != digest:
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    return obj.body


def _object_record(digest: str, con) -> dict | None:
    row = con.execute(
        "SELECT kind,version,schema_ref,logical_id,body FROM immutable_objects WHERE digest=?",
        (digest,),
    ).fetchone()
    if row is None:
        return None
    return {
        "kind": row[0],
        "version": row[1],
        "schema_revision_ref": row[2],
        "logical_id": row[3],
        "revision_digest": digest,
        "body": json.loads(row[4]),
    }


def _stop_risk_set(stop_eval_ref, index, con) -> set[str]:
    stop_eval_digest = stop_eval_ref.get("revision_digest") if isinstance(stop_eval_ref, dict) else None
    stop_eval = _accepted_body("stop_evaluation", stop_eval_digest, index, con)
    stop_input_ref = stop_eval.get("stop_input_ref")
    stop_input_digest = stop_input_ref.get("revision_digest") if isinstance(stop_input_ref, dict) else None
    stop_input = _accepted_body("stop_input", stop_input_digest, index, con)
    return _digest_set(stop_input.get("residual_risk_refs", ()))


def _ref_identity(ref):
    if not isinstance(ref, dict):
        return None
    return tuple(
        ref.get(field)
        for field in (
            "kind",
            "revision_digest",
            "digest_profile",
            "schema_revision_ref",
            "logical_id",
        )
    )


def _require_same_ref(actual, expected, field: str) -> None:
    if _ref_identity(actual) != _ref_identity(expected):
        raise ValidationError("FINALIZATION_BINDING_CONFLICT", field)


def _require_same_ref_set(actual, expected, field: str) -> None:
    if not isinstance(actual, (list, tuple)) or not isinstance(expected, (list, tuple)):
        raise ValidationError("FINALIZATION_BINDING_CONFLICT", field)
    actual_ids = [_ref_identity(ref) for ref in actual]
    expected_ids = [_ref_identity(ref) for ref in expected]
    if sorted(actual_ids) != sorted(expected_ids):
        raise ValidationError("FINALIZATION_BINDING_CONFLICT", field)


def _stop_basis(stop_eval_ref, index, con, current):
    stop_eval = _accepted_body(
        "stop_evaluation",
        stop_eval_ref.get("revision_digest") if isinstance(stop_eval_ref, dict) else None,
        index,
        con,
    )
    stop_input_ref = stop_eval.get("stop_input_ref")
    stop_input = _accepted_body(
        "stop_input",
        stop_input_ref.get("revision_digest") if isinstance(stop_input_ref, dict) else None,
        index,
        con,
    )
    stop_input_digest = (
        stop_input_ref.get("revision_digest")
        if isinstance(stop_input_ref, dict)
        else None
    )
    membership = index.get(("stop_input", stop_input_digest))
    if membership is None:
        raise ValidationError("FINALIZATION_REFERENCE_NOT_PRIOR_ACCEPTED", "stop_input")
    from ..stop.operation import _require_material_stop_basis_current

    commits = [
        json.loads(raw)
        for (raw,) in con.execute(
            "SELECT body FROM commits WHERE seq<=? ORDER BY seq",
            (current.commit_seq,),
        )
    ]
    _require_material_stop_basis_current(
        stop_input,
        campaign_id=current.campaign_id,
        head_seq=current.commit_seq,
        head_hash=current.commit_hash,
        commits=commits,
        authoritative=True,
        accepted_commit_seq=int(membership["accepted_seq"]),
        object_loader=lambda digest: _object_record(digest, con),
    )
    return stop_eval, stop_input


def _require_full_stop_pass(stop_eval: dict) -> None:
    if (
        stop_eval.get("continuation_decision") != "PASS"
        or stop_eval.get("assurance_level") != "ADEQUATE_FOR_DECLARED_SCOPE"
        or stop_eval.get("release_readiness")
        not in {"READY", "READY_WITH_RESIDUAL_RISK"}
    ):
        raise ValidationError("COMPLETED_REQUIRES_STOP_PASS")


def _resolve_finalization_ref(
    ref, *, kind, index, con, field, accepted_at_or_before=None
):
    if not isinstance(ref, dict) or ref.get("kind") != kind:
        raise ValidationError("FINALIZATION_CHALLENGER_MISMATCH", field)
    digest = ref.get("revision_digest")
    membership = index.get((kind, digest))
    if membership is None:
        raise ValidationError("FINALIZATION_REFERENCE_NOT_PRIOR_ACCEPTED", f"{kind}:{digest}")
    if (
        accepted_at_or_before is not None
        and int(membership.get("accepted_seq", 0)) > accepted_at_or_before
    ):
        raise ValidationError("FINALIZATION_REFERENCE_NOT_PRIOR_ACCEPTED", f"{kind}:{digest}")
    _require_same_ref(ref, membership.get("ref"), field)
    return _accepted_body(kind, digest, index, con)


def _validate_full_challenger_closure(stop_input, *, index, con) -> None:
    cut = stop_input.get("input_history_cut")
    cut_seq = cut.get("accepted_head_seq") if isinstance(cut, dict) else None
    if type(cut_seq) is not int or cut_seq < 1:
        raise ValidationError("FINALIZATION_CHALLENGER_MISMATCH", "input_history_cut")

    candidate_ref = stop_input.get("candidate_assurance_case_ref")
    _resolve_finalization_ref(
        candidate_ref,
        kind="candidate_assurance_case",
        index=index,
        con=con,
        field="candidate_assurance_case_ref",
        accepted_at_or_before=cut_seq,
    )
    candidates_at_cut = [
        (int(membership["accepted_seq"]), digest)
        for (kind, digest), membership in index.items()
        if kind == "candidate_assurance_case"
        and int(membership.get("accepted_seq", 0)) <= cut_seq
    ]
    if not candidates_at_cut:
        raise ValidationError("FINALIZATION_CANDIDATE_MISMATCH")
    latest_seq = max(seq for seq, _digest in candidates_at_cut)
    latest_candidates = {
        digest for seq, digest in candidates_at_cut if seq == latest_seq
    }
    if latest_candidates != {candidate_ref.get("revision_digest")}:
        raise ValidationError("FINALIZATION_CANDIDATE_MISMATCH")

    challenger_refs = stop_input.get("challenger_refs", ())
    required_roles = {"FALSE_POSITIVE_SKEPTIC", "FALSE_NEGATIVE_HUNTER"}
    if not isinstance(challenger_refs, (list, tuple)) or len(challenger_refs) != 2:
        raise ValidationError("FINALIZATION_CHALLENGER_MISMATCH", "challenger_refs")

    roles = set()
    assignment_digests = set()
    candidate_identity = _ref_identity(candidate_ref)
    for result_ref in challenger_refs:
        result = _resolve_finalization_ref(
            result_ref,
            kind="challenger_result",
            index=index,
            con=con,
            field="challenger_result_refs",
            accepted_at_or_before=cut_seq,
        )
        if _ref_identity(result.get("candidate_assurance_case_ref")) != candidate_identity:
            raise ValidationError("FINALIZATION_CHALLENGER_MISMATCH", "candidate_binding")
        assignment_ref = result.get("challenge_assignment_ref")
        assignment = _resolve_finalization_ref(
            assignment_ref,
            kind="challenger_assignment",
            index=index,
            con=con,
            field="challenge_assignment_ref",
            accepted_at_or_before=cut_seq,
        )
        if _ref_identity(assignment.get("candidate_assurance_case_ref")) != candidate_identity:
            raise ValidationError("FINALIZATION_CHALLENGER_MISMATCH", "assignment_candidate_binding")
        role = assignment.get("challenger_type")
        assignment_digest = assignment_ref.get("revision_digest")
        if role not in required_roles or role in roles or assignment_digest in assignment_digests:
            raise ValidationError("FINALIZATION_CHALLENGER_MISMATCH", "challenger_role_set")
        roles.add(role)
        assignment_digests.add(assignment_digest)

    if roles != required_roles:
        raise ValidationError("FINALIZATION_CHALLENGER_MISMATCH", "challenger_role_set")


def _validate_finalization_basis(obj, *, current, con) -> None:
    """Bind every finalization object to the exact accepted STOP closure."""
    from ..stop.authority import _accepted_index

    if current is None:
        raise ValidationError("PRIOR_ACCEPTED_REFERENCE_REQUIRED")
    index = _accepted_index(current, con)
    body = obj.body

    if obj.kind == "campaign_conclusion":
        stop_eval, stop_input = _stop_basis(body.get("stop_evaluation_ref"), index, con, current)
        _require_same_ref(
            body.get("source_generation_ref"),
            stop_input.get("source_generation_ref"),
            "source_generation_ref",
        )
        _require_same_ref(
            body.get("candidate_assurance_case_ref"),
            stop_input.get("candidate_assurance_case_ref"),
            "candidate_assurance_case_ref",
        )
        if body.get("termination_state") == "COMPLETED" and not isinstance(
            stop_input.get("candidate_assurance_case_ref"), dict
        ):
            raise ValidationError("FINALIZATION_CANDIDATE_MISMATCH")
        if body.get("termination_state") == "COMPLETED":
            _require_full_stop_pass(stop_eval)
            _validate_full_challenger_closure(stop_input, index=index, con=con)
        return

    if obj.kind == "final_assurance_case":
        conclusion_ref = body.get("campaign_conclusion_ref")
        conclusion = _accepted_body(
            "campaign_conclusion",
            conclusion_ref.get("revision_digest") if isinstance(conclusion_ref, dict) else None,
            index,
            con,
        )
        _require_same_ref(
            body.get("stop_evaluation_ref"),
            conclusion.get("stop_evaluation_ref"),
            "stop_evaluation_ref",
        )
        stop_eval, stop_input = _stop_basis(body.get("stop_evaluation_ref"), index, con, current)
        _require_same_ref(
            conclusion.get("source_generation_ref"),
            stop_input.get("source_generation_ref"),
            "source_generation_ref",
        )
        _require_same_ref(
            body.get("candidate_assurance_case_ref"),
            stop_input.get("candidate_assurance_case_ref"),
            "candidate_assurance_case_ref",
        )
        _require_same_ref(
            conclusion.get("candidate_assurance_case_ref"),
            stop_input.get("candidate_assurance_case_ref"),
            "candidate_assurance_case_ref",
        )
        _require_same_ref_set(
            body.get("challenger_result_refs", ()),
            stop_input.get("challenger_refs", ()),
            "challenger_result_refs",
        )
        if conclusion.get("termination_state") == "COMPLETED":
            if not isinstance(stop_input.get("candidate_assurance_case_ref"), dict):
                raise ValidationError("FINALIZATION_CANDIDATE_MISMATCH")
            _require_full_stop_pass(stop_eval)
            _validate_full_challenger_closure(stop_input, index=index, con=con)
            _require_same_ref_set(
                body.get("challenger_result_refs", ()),
                stop_input.get("challenger_refs", ()),
                "challenger_result_refs",
            )
        return

    if obj.kind == "release_qualification":
        final_ref = body.get("final_assurance_case_ref")
        final_case = _accepted_body(
            "final_assurance_case",
            final_ref.get("revision_digest") if isinstance(final_ref, dict) else None,
            index,
            con,
        )
        conclusion_ref = final_case.get("campaign_conclusion_ref")
        conclusion = _accepted_body(
            "campaign_conclusion",
            conclusion_ref.get("revision_digest") if isinstance(conclusion_ref, dict) else None,
            index,
            con,
        )
        _require_same_ref(
            body.get("campaign_conclusion_ref"), conclusion_ref,
            "campaign_conclusion_ref",
        )
        _require_same_ref(
            body.get("stop_evaluation_ref"), final_case.get("stop_evaluation_ref"),
            "stop_evaluation_ref",
        )
        _require_same_ref(
            body.get("stop_evaluation_ref"), conclusion.get("stop_evaluation_ref"),
            "stop_evaluation_ref",
        )
        _require_same_ref(
            body.get("source_generation_ref"), conclusion.get("source_generation_ref"),
            "source_generation_ref",
        )
        stop_eval, stop_input = _stop_basis(body.get("stop_evaluation_ref"), index, con, current)
        _require_same_ref(
            conclusion.get("source_generation_ref"),
            stop_input.get("source_generation_ref"),
            "source_generation_ref",
        )
        if conclusion.get("termination_state") == "COMPLETED":
            _require_full_stop_pass(stop_eval)
            _validate_full_challenger_closure(stop_input, index=index, con=con)
        return


def _validate_finding_claim_branch_unambiguity(
    claim_refs, *, current, con, content_objects=()
) -> None:
    """Fail closed at candidate/STOP consumers while claim-branch policy is open."""
    if not claim_refs:
        return
    accepted = _accepted_completion_records(
        "finding_claim_revision", current=current, con=con
    )
    revisions: dict[str, dict[str, Any]] = {
        row["ref"]["revision_digest"]: {
            "ref": row["ref"],
            "body": row["body"],
        }
        for row in accepted
    }
    for candidate in content_objects:
        if candidate.kind == "finding_claim_revision":
            revisions[candidate.digest] = {
                "ref": candidate.ref.as_dict(),
                "body": candidate.body,
            }

    selected_claim_ids: set[str] = set()
    for ref in claim_refs:
        target = _resolve_completion_object(
            ref,
            content_objects=content_objects,
            con=con,
            context="finding_claim_revision_refs",
        )
        if target.kind != "finding_claim_revision":
            raise ValidationError("FINDING_CLAIM_BRANCH_CONFLICT")
        claim_id = target.body.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            raise ValidationError("FINDING_CLAIM_BRANCH_CONFLICT")
        selected_claim_ids.add(claim_id)

    for claim_id in selected_claim_ids:
        claims = {
            digest: record
            for digest, record in revisions.items()
            if record["body"].get("claim_id") == claim_id
        }
        roots = [
            digest
            for digest, record in claims.items()
            if record["body"].get("previous_finding_claim_revision_ref") is None
        ]
        successors: dict[str, set[str]] = {}
        for digest, record in claims.items():
            previous = record["body"].get("previous_finding_claim_revision_ref")
            if previous is None:
                continue
            predecessor_digest = (
                previous.get("revision_digest")
                if isinstance(previous, dict)
                else None
            )
            if predecessor_digest not in claims:
                raise ValidationError("FINDING_CLAIM_BRANCH_CONFLICT")
            successors.setdefault(predecessor_digest, set()).add(digest)
        leaves = set(claims) - set(successors)
        if (
            len(roots) != 1
            or any(len(children) > 1 for children in successors.values())
            or len(leaves) != 1
        ):
            raise ValidationError("FINDING_CLAIM_BRANCH_CONFLICT")


def _validate_candidate_residual_risk_projection(
    obj, *, current, con, content_objects=()
) -> None:
    _validate_finding_claim_branch_unambiguity(
        obj.body.get("finding_claim_revision_refs", ()),
        current=current,
        con=con,
        content_objects=content_objects,
    )
    rows, _current, _index = _active_risk_rows(current, con)
    expected = _digest_set(row["ref"] for row in rows)
    if _digest_set(obj.body.get("residual_risk_refs", ())) != expected:
        raise ValidationError("CANDIDATE_RESIDUAL_RISK_PROJECTION_MISMATCH")


def _validate_stop_residual_risk_projection(
    obj, *, current, con, content_objects=()
) -> None:
    """Equality-check StopInput's residual-risk set against accepted history."""
    if current is None:
        raise ValidationError("STOP_INPUT_REQUIRES_ACCEPTED_PARENT")

    from ..stop.residual_risk_projection import _risk_summary

    active_rows, _current, _index = _active_risk_rows(current, con)
    expected_refs = [row["ref"] for row in active_rows]
    actual_refs = obj.body.get("residual_risk_refs", ())
    if _digest_set(actual_refs) != _digest_set(expected_refs):
        raise ValidationError("STOP_CURRENT_PROJECTION_MISMATCH", "residual_risk_refs")

    candidate_ref = obj.body.get("candidate_assurance_case_ref")
    if isinstance(candidate_ref, dict):
        candidate = _resolve_completion_object(
            candidate_ref,
            content_objects=content_objects,
            con=con,
            context="candidate_assurance_case_ref",
        )
        if candidate.kind != "candidate_assurance_case":
            raise ValidationError("FINDING_CLAIM_BRANCH_CONFLICT")
        _validate_finding_claim_branch_unambiguity(
            candidate.body.get("finding_claim_revision_refs", ()),
            current=current,
            con=con,
            content_objects=content_objects,
        )

    # Residual-risk readiness counters are final-STOP decision inputs.  An
    # INTERMEDIATE StopInput still has its exact risk denominator equality-
    # checked above, but it does not need to pretend that final readiness has
    # already been derived.
    if obj.body.get("evaluation_context") not in {"FINAL_POST_E5", "POST_E6"}:
        return

    expected_summary = _risk_summary(active_rows)
    actual_summary = obj.body.get("unknown_blocked_summary")
    if not isinstance(actual_summary, dict):
        raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", "unknown_blocked_summary")
    for key, expected in expected_summary.items():
        actual = actual_summary.get(key)
        if isinstance(expected, bool):
            if actual is not expected:
                raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", key)
        elif type(actual) is not int or actual != expected:
            raise ValidationError("STOP_DERIVED_SUMMARY_MISMATCH", key)


def _validate_finalization_residual_risk_projection(obj, *, current, con) -> None:
    if current is None:
        raise ValidationError("PRIOR_ACCEPTED_REFERENCE_REQUIRED")
    active_rows, _current, index = _active_risk_rows(current, con)
    current_set = _digest_set(row["ref"] for row in active_rows)
    body = obj.body

    if obj.kind == "campaign_conclusion":
        stop_set = _stop_risk_set(body.get("stop_evaluation_ref"), index, con)
        if stop_set != current_set:
            raise ValidationError("RESIDUAL_RISK_DRIFT_AFTER_STOP")
        if _digest_set(body.get("residual_risk_refs", ())) != stop_set:
            raise ValidationError("FINALIZATION_RESIDUAL_RISK_MISMATCH")
        return

    if obj.kind == "final_assurance_case":
        conclusion_ref = body.get("campaign_conclusion_ref")
        conclusion_digest = conclusion_ref.get("revision_digest") if isinstance(conclusion_ref, dict) else None
        conclusion = _accepted_body("campaign_conclusion", conclusion_digest, index, con)
        conclusion_set = _digest_set(conclusion.get("residual_risk_refs", ()))
        if conclusion_set != current_set:
            raise ValidationError("RESIDUAL_RISK_DRIFT_AFTER_STOP")
        if _digest_set(body.get("residual_risk_refs", ())) != conclusion_set:
            raise ValidationError("FINALIZATION_RESIDUAL_RISK_MISMATCH")
        return

    if obj.kind == "release_qualification" and body.get("assessment_basis") == "STOP_AXIS_MATERIALIZATION":
        final_ref = body.get("final_assurance_case_ref")
        final_digest = final_ref.get("revision_digest") if isinstance(final_ref, dict) else None
        final_case = _accepted_body("final_assurance_case", final_digest, index, con)
        final_set = _digest_set(final_case.get("residual_risk_refs", ()))
        if final_set != current_set:
            raise ValidationError("RESIDUAL_RISK_DRIFT_AFTER_STOP")
        actual = _digest_set(body.get("accepted_residual_risk_refs", ()))
        if actual != final_set:
            raise ValidationError("FINALIZATION_RESIDUAL_RISK_MISMATCH")
        stop_ref = body.get("stop_evaluation_ref")
        stop_digest = stop_ref.get("revision_digest") if isinstance(stop_ref, dict) else None
        stop_eval = _accepted_body("stop_evaluation", stop_digest, index, con)
        if body.get("result") != stop_eval.get("release_readiness"):
            raise ValidationError("FINALIZATION_BINDING_CONFLICT")
        if final_set and body.get("result") != "READY_WITH_RESIDUAL_RISK":
            raise ValidationError("RESIDUAL_RISK_RELEASE_READINESS_MISMATCH")
        if not final_set and body.get("result") == "READY_WITH_RESIDUAL_RISK":
            raise ValidationError("RESIDUAL_RISK_RELEASE_READINESS_MISMATCH")


def _validate_finding_claim_lineage(obj, *, con) -> None:
    """Keep immutable claim revisions on one exact logical Finding lineage."""
    body = obj.body
    revision = body.get("claim_revision")
    if not isinstance(revision, str) or not revision.isdecimal() or int(revision) < 1:
        raise ValidationError("FINDING_CLAIM_REVISION_INVALID")

    previous_ref = body.get("previous_finding_claim_revision_ref")
    if previous_ref is None:
        if revision != "1":
            raise ValidationError("FINDING_CLAIM_PREDECESSOR_REQUIRED")
        return

    row = con.execute(
        "SELECT kind,version,schema_ref,logical_id,body FROM immutable_objects WHERE digest=?",
        (previous_ref.get("revision_digest"),),
    ).fetchone()
    if row is None or row[0] != "finding_claim_revision":
        raise ValidationError("FINDING_CLAIM_PREDECESSOR_NOT_FOUND")
    predecessor = CanonicalObject(row[0], json.loads(row[4]), row[2], row[3], row[1])
    if predecessor.digest != previous_ref.get("revision_digest"):
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    previous_body = predecessor.body
    previous_revision = previous_body.get("claim_revision")
    if (
        not isinstance(previous_revision, str)
        or not previous_revision.isdecimal()
        or int(revision) != int(previous_revision) + 1
    ):
        raise ValidationError("FINDING_CLAIM_REVISION_SEQUENCE_MISMATCH")
    if body.get("claim_id") != previous_body.get("claim_id"):
        raise ValidationError("FINDING_CLAIM_IDENTITY_MISMATCH")
    if obj.logical_id != predecessor.logical_id:
        raise ValidationError("FINDING_CLAIM_IDENTITY_MISMATCH")


def _typed_ref_identity(ref):
    if not isinstance(ref, dict):
        return None
    return tuple(
        ref.get(field)
        for field in (
            "kind",
            "revision_digest",
            "digest_profile",
            "schema_revision_ref",
            "logical_id",
        )
    )


def _resolve_isolation_context_object(ref, *, content_objects, con):
    if not isinstance(ref, dict) or not isinstance(ref.get("revision_digest"), str):
        raise ValidationError("ISOLATION_ATTEMPT_CONTEXT_INVALID")
    target = next(
        (
            candidate
            for candidate in content_objects
            if candidate.digest == ref.get("revision_digest")
        ),
        None,
    )
    if target is None:
        row = con.execute(
            "SELECT kind,version,schema_ref,logical_id,body FROM immutable_objects WHERE digest=?",
            (ref["revision_digest"],),
        ).fetchone()
        if row is None:
            raise ValidationError("ISOLATION_ATTEMPT_CONTEXT_NOT_FOUND")
        target = CanonicalObject(row[0], json.loads(row[4]), row[2], row[3], row[1])
    if (
        target.digest != ref.get("revision_digest")
        or target.kind != ref.get("kind")
        or target.schema_revision_ref != ref.get("schema_revision_ref")
        or target.logical_id != ref.get("logical_id")
    ):
        raise ValidationError("ISOLATION_ATTEMPT_CONTEXT_IDENTITY_MISMATCH")
    return target


def _resolve_completion_object(ref, *, content_objects, con, context):
    """Resolve an exact completion dependency from this closure or history."""
    if not isinstance(ref, dict) or not isinstance(ref.get("revision_digest"), str):
        raise ValidationError("STAGE_COMPLETION_REFERENCE_INVALID", context)
    target = next(
        (candidate for candidate in content_objects if candidate.digest == ref.get("revision_digest")),
        None,
    )
    if target is None:
        row = con.execute(
            "SELECT kind,version,schema_ref,logical_id,body FROM immutable_objects WHERE digest=?",
            (ref["revision_digest"],),
        ).fetchone()
        if row is None:
            raise ValidationError("STAGE_COMPLETION_REFERENCE_NOT_FOUND", context)
        target = CanonicalObject(row[0], json.loads(row[4]), row[2], row[3], row[1])
    if (
        target.digest != ref.get("revision_digest")
        or target.kind != ref.get("kind")
        or target.schema_revision_ref != ref.get("schema_revision_ref")
        or target.logical_id != ref.get("logical_id")
    ):
        raise ValidationError("STAGE_COMPLETION_REFERENCE_IDENTITY_MISMATCH", context)
    return target


def _stage_slot_key(stage_key, lane_key):
    """Normalize supported StageSpec/LaneSpec slot spellings for equality."""
    value = str(lane_key).strip().lower()
    stage = str(stage_key).strip().lower()
    prefix = f"lane_{stage}_"
    if value.startswith(prefix):
        value = value[len(prefix):]
    elif value.startswith("lane_"):
        value = value[len("lane_"):]
    if value.startswith(f"{stage}-"):
        value = value[len(stage) + 1:]
    elif value.startswith(f"{stage}_"):
        value = value[len(stage) + 1:]
    return value


def _validate_native_stage_spec_authority(obj) -> None:
    stage_key = obj.body.get("stage_key")
    if stage_key not in {"E1", "E2", "E3", "E4", "E5"}:
        return
    from ..orchestration.stages import native_stage_spec

    revision = obj.body.get("stage_spec_revision")
    # The repository currently pins one executable native revision for E1-E5.
    # A caller-selected label is not authority to mint a fresh policy revision.
    if revision != "1":
        raise ValidationError("STAGE_SPEC_NOT_GOVERNING_NATIVE_REVISION")
    expected = native_stage_spec(stage_key, revision).body()
    if obj.body != expected:
        raise ValidationError(
            "STAGE_SPEC_NOT_GOVERNING_NATIVE_REVISION",
            f"{stage_key}/{revision} does not preserve the pinned native obligations",
        )


def _object_ref_digest(ref):
    return ref.get("revision_digest") if isinstance(ref, dict) else None


def _artifact_belongs_to_stage_run(target, stage_run, *, content_objects, con) -> bool:
    lane_ref = target.body.get("lane_run_ref")
    if not isinstance(lane_ref, dict):
        return False
    try:
        lane_run = _resolve_completion_object(
            lane_ref,
            content_objects=content_objects,
            con=con,
            context="stage_output.lane_run_ref",
        )
    except ValidationError:
        return False
    return (
        lane_run.kind == "lane_run"
        and _typed_ref_identity(lane_run.body.get("stage_run_ref"))
        == _typed_ref_identity(stage_run.ref.as_dict())
    )


def _validate_stage_output_obligations(
    stage_key,
    required_outputs,
    output_targets,
    *,
    stage_run,
    lane_output_digests,
    content_objects,
    con,
):
    """Require each named obligation to have its canonical accepted artifact."""
    outputs_by_kind = {}
    for target in output_targets:
        outputs_by_kind.setdefault(target.kind, []).append(target)

    def require(kind, name):
        matches = outputs_by_kind.get(kind, ())
        if not matches:
            raise ValidationError("STAGE_COMPLETION_REQUIRED_OUTPUT_MISSING", name)
        return matches

    expected = {
        "E1": {
            "discovery_records": ("discovery_record",),
            "stage_completion_digest": (),
        },
        "E2": {
            "adjudication_decisions": ("finding_adjudication_decision",),
            "contradiction_obligations": ("contradiction_revision",),
        },
        "E3": {
            "blind_checkpoint": ("checkpoint",),
            "gap_directed_records": ("discovery_record",),
            "stage_completion_digest": (),
        },
        "E4": {
            "e4_assessments": ("bdb_audit_lane_result",),
            "model_fidelity_assessment": ("model_fidelity_assessment",),
            "stage_completion_digest": (),
        },
        "E5": {
            "candidate_assurance_case": ("candidate_assurance_case",),
            "challenger_assignments": ("challenger_assignment",),
            "challenger_results": ("challenger_result",),
            "stage_completion_digest": (),
        },
    }
    if stage_key == "E6":
        # No Adaptive E6 execution runtime is qualified in this candidate.
        raise ValidationError("E6_EXECUTION_UNAVAILABLE")
    obligations = expected.get(stage_key)
    if obligations is None:
        raise ValidationError("STAGE_COMPLETION_OBLIGATION_UNRESOLVED", str(stage_key))

    for name in required_outputs:
        kinds = obligations.get(name)
        if kinds is None:
            raise ValidationError("STAGE_COMPLETION_OBLIGATION_UNRESOLVED", str(name))
        if not kinds:
            # The completion object's own ObjectDigest is this output; a
            # self-reference in required_output_refs would be impossible.
            continue
        targets = [target for kind in kinds for target in outputs_by_kind.get(kind, ())]
        if not targets:
            raise ValidationError("STAGE_COMPLETION_REQUIRED_OUTPUT_MISSING", name)

        if name == "discovery_records":
            if not any(
                _artifact_belongs_to_stage_run(
                    target, stage_run, content_objects=content_objects, con=con
                )
                for target in targets
            ):
                raise ValidationError("STAGE_COMPLETION_OUTPUT_BINDING_MISMATCH", name)
        elif name == "blind_checkpoint":
            if not any(
                _typed_ref_identity(target.body.get("stage_run_ref"))
                == _typed_ref_identity(stage_run.ref.as_dict())
                for target in targets
            ):
                raise ValidationError("STAGE_COMPLETION_OUTPUT_BINDING_MISMATCH", name)
        elif name == "gap_directed_records":
            checkpoints = {
                target.digest
                for target in outputs_by_kind.get("checkpoint", ())
                if _typed_ref_identity(target.body.get("stage_run_ref"))
                == _typed_ref_identity(stage_run.ref.as_dict())
            }
            if not any(
                _artifact_belongs_to_stage_run(
                    target, stage_run, content_objects=content_objects, con=con
                )
                and _object_ref_digest(target.body.get("pre_reveal_checkpoint_ref"))
                in checkpoints
                for target in targets
            ):
                raise ValidationError("STAGE_COMPLETION_OUTPUT_BINDING_MISMATCH", name)
        elif name == "e4_assessments":
            if not any(
                target.digest in lane_output_digests
                and target.body.get("stage_id") == "E4"
                and target.body.get("phase_id") == "E4-DEEPEN"
                and isinstance(target.body.get("outputs"), dict)
                and isinstance(target.body["outputs"].get("e4_assessments"), list)
                and bool(target.body["outputs"]["e4_assessments"])
                for target in targets
            ):
                raise ValidationError("STAGE_COMPLETION_OUTPUT_BINDING_MISMATCH", name)
        elif name == "model_fidelity_assessment":
            source_ref = stage_run.body.get("source_generation_ref")
            if not any(
                _typed_ref_identity(target.body.get("source_generation_ref"))
                == _typed_ref_identity(source_ref)
                for target in targets
            ):
                raise ValidationError("STAGE_COMPLETION_OUTPUT_BINDING_MISMATCH", name)

    if stage_key == "E5":
        candidates = outputs_by_kind.get("candidate_assurance_case", ())
        if len(candidates) != 1:
            raise ValidationError("STAGE_COMPLETION_OUTPUT_BINDING_MISMATCH", "candidate_assurance_case")
        candidate_digest = candidates[0].digest
        assignments = outputs_by_kind.get("challenger_assignment", ())
        roles = {
            target.body.get("challenger_type"): target.digest
            for target in assignments
            if _object_ref_digest(target.body.get("candidate_assurance_case_ref"))
            == candidate_digest
        }
        required_roles = {"FALSE_POSITIVE_SKEPTIC", "FALSE_NEGATIVE_HUNTER"}
        if set(roles) != required_roles or len(assignments) != len(required_roles):
            raise ValidationError("STAGE_COMPLETION_OUTPUT_BINDING_MISMATCH", "challenger_assignments")
        results = outputs_by_kind.get("challenger_result", ())
        result_assignments = {
            _object_ref_digest(target.body.get("challenge_assignment_ref"))
            for target in results
            if _object_ref_digest(target.body.get("candidate_assurance_case_ref"))
            == candidate_digest
        }
        if (
            len(results) != len(required_roles)
            or result_assignments != set(roles.values())
        ):
            raise ValidationError("STAGE_COMPLETION_OUTPUT_BINDING_MISMATCH", "challenger_results")


def _cut_seq(cut, *, context):
    if not isinstance(cut, dict) or cut.get("variant") != "ACCEPTED_HISTORY_CUT":
        raise ValidationError("STAGE_COMPLETION_HISTORY_CUT_INVALID", context)
    value = cut.get("accepted_head_seq")
    if type(value) is not int or value < 1:
        raise ValidationError("STAGE_COMPLETION_HISTORY_CUT_INVALID", context)
    return value


def _exact_lane_completion_cut_seq(
    cut, *, campaign_id, max_seq, con, context
):
    """Return a cut sequence only when its campaign and accepted head are exact."""
    from ..history.store import _commit_from_body

    cut_seq = _cut_seq(cut, context=context)
    if cut.get("campaign_id") != campaign_id or cut_seq > max_seq:
        raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")
    commit_row = con.execute(
        "SELECT commit_hash,body FROM commits WHERE seq=?", (cut_seq,)
    ).fetchone()
    if commit_row is None:
        raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")
    accepted_commit = _commit_from_body(json.loads(commit_row[1]))
    if (
        accepted_commit.campaign_id != campaign_id
        or accepted_commit.digest != commit_row[0]
        or cut.get("accepted_head_hash") != commit_row[0]
    ):
        raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")
    return cut_seq


_NON_OUTPUT_KINDS = frozenset(
    {
        "source_generation",
        "source_identity",
        "stage_spec",
        "stage_run",
        "lane_spec",
        "lane_run",
        "attempt",
        "executor_spec",
        "delivery_spec",
        "isolation_qualification",
        "knowledge_state",
        "lane_completion",
        "stage_completion",
        "lane_result_admission_evidence",
    }
)


def _accepted_completion_records(kind, *, current, con):
    if current is None:
        return ()
    from ..stop.authority import _accepted_index, _records

    return _records(kind, _accepted_index(current, con), con)


def _validate_lane_result_admission_evidence(obj, *, content_objects, current, con) -> None:
    body = obj.body
    raw_digest = body.get("raw_result_digest")
    if not isinstance(raw_digest, str) or len(raw_digest) != 64:
        raise ValidationError("INVALID_RAW_DIGEST")

    from pathlib import Path
    db_row = con.execute("PRAGMA database_list").fetchone()
    db_path = db_row[2] if db_row and len(db_row) > 2 else ""
    if not db_path:
        raise ValidationError("RAW_ARTIFACT_NOT_FOUND", raw_digest)
    vault_dir = Path(db_path).resolve().parent / "raw_vault"
    from ..vault.raw_store import RawArtifactVault
    vault = RawArtifactVault(vault_dir)
    try:
        raw_bytes = vault.read_bytes(raw_digest)
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("RAW_ARTIFACT_NOT_FOUND", str(exc)) from exc

    expected_len = body.get("raw_result_byte_length")
    if isinstance(expected_len, int) and len(raw_bytes) != expected_len:
        raise ValidationError("RAW_RESULT_BYTE_LENGTH_MISMATCH")

    from ..assurance.zip_safety import read_bytes as read_zip_bytes
    try:
        members = read_zip_bytes(raw_bytes)
    except Exception as exc:
        raise ValidationError("INVALID_ZIP", str(exc)) from exc

    if "MANIFEST.json" not in members:
        raise ValidationError("MISSING_MANIFEST")
    from ..core.canonical_json import parse
    try:
        manifest = parse(members["MANIFEST.json"])
    except Exception as exc:
        raise ValidationError("MALFORMED_MANIFEST", str(exc)) from exc
    if not isinstance(manifest, dict):
        raise ValidationError("MALFORMED_MANIFEST")

    if manifest.get("campaign_id") != body.get("campaign_id"):
        raise ValidationError("CAMPAIGN_BINDING_MISMATCH")
    if manifest.get("stage_id") != body.get("stage_id"):
        raise ValidationError("STAGE_BINDING_MISMATCH")
    if manifest.get("lane_slot") != body.get("lane_slot"):
        raise ValidationError("LANE_SLOT_BINDING_MISMATCH")
    if str(manifest.get("source_commit_sha", "")).lower() != str(body.get("source_commit_sha", "")).lower():
        raise ValidationError("SOURCE_COMMIT_MISMATCH")
    if manifest.get("input_package_digest") != body.get("input_package_digest"):
        raise ValidationError("PACKAGE_DIGEST_MISMATCH")
    if manifest.get("executor_profile") != body.get("executor_profile"):
        raise ValidationError("EXECUTOR_PROFILE_MISMATCH")
    if manifest.get("executor_model") != body.get("executor_model"):
        raise ValidationError("EXECUTOR_MODEL_MISMATCH")

    assignment = _resolve_completion_object(
        body.get("assignment_ref"),
        content_objects=content_objects,
        con=con,
        context="assignment_ref",
    )
    if assignment.kind != "assignment_manifest":
        raise ValidationError("ASSIGNMENT_REF_INVALID")
    if _typed_ref_identity(assignment.body.get("attempt_ref")) != _typed_ref_identity(body.get("attempt_ref")):
        raise ValidationError("ASSIGNMENT_ATTEMPT_BINDING_MISMATCH")
    if _typed_ref_identity(assignment.body.get("source_generation_ref")) != _typed_ref_identity(body.get("source_generation_ref")):
        raise ValidationError("ASSIGNMENT_SOURCE_BINDING_MISMATCH")
    if canonical_bytes(assignment.body.get("assignment_input_history_cut")) != canonical_bytes(body.get("history_cut")):
        raise ValidationError("ASSIGNMENT_CUT_MISMATCH")


def _validate_lane_result(obj, *, content_objects, current, con) -> None:
    body = obj.body
    admission_ref = body.get("admission_evidence_ref")
    if not isinstance(admission_ref, dict):
        raise ValidationError("ADMISSION_EVIDENCE_REF_REQUIRED")

    evidence_obj = _resolve_completion_object(
        admission_ref,
        content_objects=content_objects,
        con=con,
        context="admission_evidence_ref",
    )
    if evidence_obj.kind != "lane_result_admission_evidence":
        raise ValidationError("ADMISSION_EVIDENCE_KIND_MISMATCH")

    evidence = evidence_obj.body
    if body.get("campaign_id") != evidence.get("campaign_id"):
        raise ValidationError("RESULT_ADMISSION_EVIDENCE_MISMATCH", "campaign_id")
    if body.get("stage_id") != evidence.get("stage_id"):
        raise ValidationError("RESULT_ADMISSION_EVIDENCE_MISMATCH", "stage_id")
    if body.get("phase_id") != evidence.get("phase_id"):
        raise ValidationError("RESULT_ADMISSION_EVIDENCE_MISMATCH", "phase_id")
    if body.get("lane_slot") != evidence.get("lane_slot"):
        raise ValidationError("RESULT_ADMISSION_EVIDENCE_MISMATCH", "lane_slot")
    if str(body.get("source_commit_sha", "")).lower() != str(evidence.get("source_commit_sha", "")).lower():
        raise ValidationError("RESULT_ADMISSION_EVIDENCE_MISMATCH", "source_commit_sha")
    if canonical_bytes(body.get("history_cut")) != canonical_bytes(evidence.get("history_cut")):
        raise ValidationError("RESULT_ADMISSION_EVIDENCE_MISMATCH", "history_cut")
    if body.get("input_package_digest") != evidence.get("input_package_digest"):
        raise ValidationError("RESULT_ADMISSION_EVIDENCE_MISMATCH", "input_package_digest")
    if body.get("executor_profile") != evidence.get("executor_profile"):
        raise ValidationError("RESULT_ADMISSION_EVIDENCE_MISMATCH", "executor_profile")
    if body.get("executor_model") != evidence.get("executor_model"):
        raise ValidationError("RESULT_ADMISSION_EVIDENCE_MISMATCH", "executor_model")
    if body.get("assignment_ref") and _typed_ref_identity(body.get("assignment_ref")) != _typed_ref_identity(evidence.get("assignment_ref")):
        raise ValidationError("RESULT_ADMISSION_EVIDENCE_MISMATCH", "assignment_ref")
    if body.get("attempt_ref") and _typed_ref_identity(body.get("attempt_ref")) != _typed_ref_identity(evidence.get("attempt_ref")):
        raise ValidationError("RESULT_ADMISSION_EVIDENCE_MISMATCH", "attempt_ref")
    if body.get("raw_result_digest") and body.get("raw_result_digest") != evidence.get("raw_result_digest"):
        raise ValidationError("RESULT_ADMISSION_EVIDENCE_MISMATCH", "raw_result_digest")

    proposal_copy = {k: v for k, v in body.items() if k != "admission_evidence_ref"}
    calculated_digest = hashlib.sha256(canonical_bytes(proposal_copy)).hexdigest()
    if calculated_digest != evidence.get("result_proposal_digest"):
        raise ValidationError("RESULT_PROPOSAL_DIGEST_MISMATCH")


def _validate_lane_completion(obj, *, content_objects, con, current):
    body = obj.body
    if body.get("completion_predicate_result") != "LANE_COMPLETED":
        return
    attempt_refs = body.get("attempt_refs")
    output_refs = body.get("required_output_refs")
    if not attempt_refs or not output_refs:
        raise ValidationError("LANE_COMPLETION_EXECUTION_EVIDENCE_REQUIRED")
    lane_run = _resolve_completion_object(
        body.get("lane_run_ref"), content_objects=content_objects, con=con, context="lane_run_ref"
    )
    lane_spec = _resolve_completion_object(
        body.get("lane_spec_ref"), content_objects=content_objects, con=con, context="lane_spec_ref"
    )
    if lane_run.kind != "lane_run" or lane_spec.kind != "lane_spec":
        raise ValidationError("LANE_COMPLETION_CONTEXT_KIND_MISMATCH")
    if _typed_ref_identity(lane_run.body.get("lane_spec_ref")) != _typed_ref_identity(body.get("lane_spec_ref")):
        raise ValidationError("LANE_COMPLETION_CONTEXT_BINDING_MISMATCH", "lane_spec_ref")

    stage_run = _resolve_completion_object(
        lane_run.body.get("stage_run_ref"), content_objects=content_objects, con=con, context="stage_run_ref"
    )
    if stage_run.kind != "stage_run":
        raise ValidationError("LANE_COMPLETION_CONTEXT_KIND_MISMATCH", "stage_run_ref")
    if _typed_ref_identity(lane_run.body.get("source_generation_ref")) != _typed_ref_identity(
        stage_run.body.get("source_generation_ref")
    ):
        raise ValidationError("LANE_COMPLETION_SOURCE_BINDING_MISMATCH")
    lane_cut = _cut_seq(body.get("input_history_cut"), context="lane_completion")

    stage_spec = _resolve_completion_object(
        stage_run.body.get("stage_spec_ref"),
        content_objects=content_objects,
        con=con,
        context="stage_run.stage_spec_ref",
    )
    stage_key = stage_spec.body.get("stage_key")
    native_stage = stage_key in {"E1", "E2", "E3", "E4", "E5"}
    if native_stage and str(lane_spec.body.get("stage_spec_revision")) != str(
        stage_spec.body.get("stage_spec_revision")
    ):
        raise ValidationError("LANE_COMPLETION_STAGE_SPEC_REVISION_MISMATCH")

    lane_completion_record = None
    if native_stage:
        if current is None:
            raise ValidationError("LANE_COMPLETION_HISTORY_CUT_INVALID")
        from ..history.store import _commit_from_body

        input_cut = body.get("input_history_cut")
        if (
            not isinstance(input_cut, dict)
            or input_cut.get("campaign_id") != current.campaign_id
            or lane_cut > current.commit_seq
        ):
            raise ValidationError("LANE_COMPLETION_HISTORY_CUT_INVALID")
        cut_row = con.execute(
            "SELECT commit_hash,body FROM commits WHERE seq=?", (lane_cut,)
        ).fetchone()
        if cut_row is None:
            raise ValidationError("LANE_COMPLETION_HISTORY_CUT_INVALID")
        cut_commit = _commit_from_body(json.loads(cut_row[1]))
        if (
            cut_commit.campaign_id != current.campaign_id
            or cut_commit.digest != cut_row[0]
            or input_cut.get("accepted_head_hash") != cut_row[0]
        ):
            raise ValidationError("LANE_COMPLETION_HISTORY_CUT_INVALID")
        lane_completion_record = next(
            (
                row
                for row in _accepted_completion_records(
                    "lane_completion", current=current, con=con
                )
                if row.get("ref", {}).get("revision_digest") == obj.digest
            ),
            None,
        )
        if lane_completion_record is None:
            if lane_cut != current.commit_seq or cut_row[0] != current.commit_hash:
                raise ValidationError("LANE_COMPLETION_HISTORY_CUT_INVALID")
        elif int(lane_completion_record.get("accepted_seq", 0)) != lane_cut + 1:
            raise ValidationError("LANE_COMPLETION_HISTORY_CUT_INVALID")

    resolved_attempts = []
    for attempt_ref in attempt_refs:
        attempt = _resolve_completion_object(
            attempt_ref, content_objects=content_objects, con=con, context="attempt_refs"
        )
        if attempt.kind != "attempt" or _typed_ref_identity(attempt.body.get("lane_run_ref")) != _typed_ref_identity(
            body.get("lane_run_ref")
        ):
            raise ValidationError("LANE_COMPLETION_ATTEMPT_BINDING_MISMATCH")
        if _cut_seq(attempt.body.get("assigned_history_cut"), context="attempt") > lane_cut:
            raise ValidationError("LANE_COMPLETION_ATTEMPT_CUT_MISMATCH")
        resolved_attempts.append((attempt_ref, attempt))

    knowledge = _resolve_completion_object(
        body.get("final_knowledge_state_ref"),
        content_objects=content_objects,
        con=con,
        context="final_knowledge_state_ref",
    )
    if knowledge.kind != "knowledge_state":
        raise ValidationError("LANE_COMPLETION_KNOWLEDGE_KIND_MISMATCH")
    matching_attempt = next(
        (
            pair
            for pair in resolved_attempts
            if _typed_ref_identity(pair[0]) == _typed_ref_identity(knowledge.body.get("attempt_ref"))
        ),
        None,
    )
    if matching_attempt is None:
        raise ValidationError("LANE_COMPLETION_KNOWLEDGE_ATTEMPT_MISMATCH")

    isolation_ref = body.get("isolation_qualification_ref")
    isolation = _resolve_completion_object(
        isolation_ref, content_objects=content_objects, con=con, context="isolation_qualification_ref"
    )
    if isolation.kind != "isolation_qualification":
        raise ValidationError("LANE_COMPLETION_ISOLATION_KIND_MISMATCH")
    if _typed_ref_identity(knowledge.body.get("isolation_qualification_ref")) != _typed_ref_identity(isolation_ref):
        raise ValidationError("LANE_COMPLETION_ISOLATION_BINDING_MISMATCH")
    if _typed_ref_identity(isolation.body.get("attempt_ref")) != _typed_ref_identity(matching_attempt[0]):
        raise ValidationError("LANE_COMPLETION_ISOLATION_ATTEMPT_MISMATCH")
    ranks = {"UNKNOWN": 0, "DECLARED": 1, "ENFORCED": 2}
    required = lane_spec.body.get("required_isolation_assurance")
    actual = isolation.body.get("result")
    if required not in ranks or actual not in ranks or ranks[actual] < ranks[required]:
        raise ValidationError("LANE_COMPLETION_ISOLATION_INSUFFICIENT")
    if body.get("contamination_assessment_refs"):
        raise ValidationError("LANE_COMPLETION_CONTAMINATED")

    for output_ref in output_refs:
        target = _resolve_completion_object(
            output_ref, content_objects=content_objects, con=con, context="required_output_refs"
        )
        if target.kind in _NON_OUTPUT_KINDS:
            raise ValidationError("LANE_COMPLETION_OUTPUT_KIND_INVALID", target.kind)

    if not native_stage:
        return

    # Native completion must carry an accepted result proposal for the exact
    # assignment and final attempt. An output-shaped object alone is not
    # execution authority.
    assignments = _accepted_completion_records(
        "assignment_manifest", current=current, con=con
    )
    lane_assignment_records = [
        row
        for row in assignments
        if _typed_ref_identity(row.get("body", {}).get("lane_spec_ref"))
        == _typed_ref_identity(body.get("lane_spec_ref"))
        and _typed_ref_identity(row.get("body", {}).get("stage_spec_ref"))
        == _typed_ref_identity(stage_run.body.get("stage_spec_ref"))
        and _typed_ref_identity(row.get("body", {}).get("source_generation_ref"))
        == _typed_ref_identity(stage_run.body.get("source_generation_ref"))
    ]
    accepted_results = list(
        _accepted_completion_records(
            "bdb_audit_lane_result", current=current, con=con
        )
    )
    result_objects = [
        candidate
        for candidate in content_objects
        if candidate.kind == "bdb_audit_lane_result"
    ]
    assignments_by_attempt: dict[tuple, dict[str, Any]] = {}
    attempt_identities = {
        _typed_ref_identity(attempt_ref) for attempt_ref, _attempt in resolved_attempts
    }
    attempt_assignment_records = [
        row
        for row in assignments
        if _typed_ref_identity(row.get("body", {}).get("attempt_ref"))
        in attempt_identities
    ]
    if attempt_assignment_records and not lane_assignment_records:
        raise ValidationError("LANE_COMPLETION_ASSIGNMENT_BINDING_MISMATCH")
    for attempt_ref, attempt in resolved_attempts:
        matches = [
            row
            for row in assignments
            if _typed_ref_identity(row.get("body", {}).get("attempt_ref"))
            == _typed_ref_identity(attempt_ref)
            and _typed_ref_identity(row.get("body", {}).get("lane_spec_ref"))
            == _typed_ref_identity(body.get("lane_spec_ref"))
        ]
        if not matches:
            if lane_assignment_records or attempt_assignment_records:
                raise ValidationError("LANE_COMPLETION_ASSIGNMENT_REQUIRED")
            continue
        if len(matches) != 1:
            raise ValidationError("LANE_COMPLETION_ASSIGNMENT_AMBIGUOUS")
        assignment = matches[0]
        assignment_body = assignment["body"]
        if (
            _typed_ref_identity(assignment_body.get("source_generation_ref"))
            != _typed_ref_identity(stage_run.body.get("source_generation_ref"))
            or _typed_ref_identity(assignment_body.get("stage_spec_ref"))
            != _typed_ref_identity(stage_run.body.get("stage_spec_ref"))
        ):
            raise ValidationError("LANE_COMPLETION_ASSIGNMENT_BINDING_MISMATCH")
        assignments_by_attempt[_typed_ref_identity(attempt_ref)] = assignment

    output_targets = [
        _resolve_completion_object(
            output_ref,
            content_objects=content_objects,
            con=con,
            context="required_output_refs",
        )
        for output_ref in output_refs
    ]
    output_result_targets = [
        target
        for target in output_targets
        if target.kind == "bdb_audit_lane_result"
    ]
    if not output_result_targets:
        if lane_assignment_records or attempt_assignment_records:
            raise ValidationError("LANE_COMPLETION_EXECUTION_RESULT_REQUIRED")
        if current is None or not output_targets or any(
            target.kind != "discovery_record" for target in output_targets
        ):
            raise ValidationError("LANE_COMPLETION_EXECUTION_RESULT_REQUIRED")

        # Some direct, pre-manifest native producers use a canonical
        # discovery_record as the lane output. Admit that shape only when its
        # exact lane/attempt/source/knowledge provenance matches an accepted
        # execution descriptor and result on the same input cut.
        lane_run_identity = _typed_ref_identity(body.get("lane_run_ref"))
        attempt_by_identity = {
            _typed_ref_identity(attempt_ref): attempt
            for attempt_ref, attempt in resolved_attempts
        }
        accepted_discoveries = _accepted_completion_records(
            "discovery_record", current=current, con=con
        )
        accepted_knowledge = _accepted_completion_records(
            "knowledge_state", current=current, con=con
        )
        execution_descriptors = _accepted_completion_records(
            "execution_descriptor", current=current, con=con
        )
        execution_results = _accepted_completion_records(
            "execution_result", current=current, con=con
        )

        for target in output_targets:
            digest = target.digest
            accepted_match = any(
                row.get("ref", {}).get("revision_digest") == digest
                and _typed_ref_identity(row.get("ref"))
                == _typed_ref_identity(target.ref.as_dict())
                for row in accepted_discoveries
            )
            in_closure = any(
                candidate.digest == digest for candidate in content_objects
            )
            if not accepted_match and not in_closure:
                raise ValidationError("LANE_COMPLETION_OUTPUT_NOT_ACCEPTED")

            discovery = target.body
            attempt_identity = _typed_ref_identity(discovery.get("attempt_ref"))
            attempt = attempt_by_identity.get(attempt_identity)
            if (
                attempt is None
                or _typed_ref_identity(discovery.get("lane_run_ref"))
                != lane_run_identity
                or _typed_ref_identity(discovery.get("source_generation_ref"))
                != _typed_ref_identity(stage_run.body.get("source_generation_ref"))
            ):
                raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")

            discovery_cut = discovery.get("discovery_input_history_cut")
            discovery_cut_seq = _exact_lane_completion_cut_seq(
                discovery_cut,
                campaign_id=current.campaign_id,
                max_seq=lane_cut,
                con=con,
                context="discovery_record",
            )
            if discovery_cut_seq < _cut_seq(
                attempt.body.get("assigned_history_cut"), context="attempt"
            ):
                raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")
            if discovery.get("result_proposal_digest") is not None:
                raise ValidationError("LANE_COMPLETION_OUTPUT_RESULT_MISMATCH")

            knowledge_ref = discovery.get("knowledge_state_ref")
            knowledge = _resolve_completion_object(
                knowledge_ref,
                content_objects=content_objects,
                con=con,
                context="discovery_record.knowledge_state_ref",
            )
            knowledge_accepted = any(
                row.get("ref", {}).get("revision_digest")
                == knowledge.digest
                and _typed_ref_identity(row.get("ref"))
                == _typed_ref_identity(knowledge.ref.as_dict())
                for row in accepted_knowledge
            )
            knowledge_in_closure = any(
                candidate.digest == knowledge.digest
                for candidate in content_objects
            )
            if (
                knowledge.kind != "knowledge_state"
                or _typed_ref_identity(knowledge.body.get("attempt_ref"))
                != attempt_identity
                or (not knowledge_accepted and not knowledge_in_closure)
            ):
                raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")

            matching_execution_result = False
            for result in execution_results:
                if int(result.get("accepted_seq", 0)) > lane_cut:
                    continue
                descriptor = _resolve_completion_object(
                    result.get("body", {}).get("execution_descriptor_ref"),
                    content_objects=content_objects,
                    con=con,
                    context="execution_result.execution_descriptor_ref",
                )
                if descriptor.kind != "execution_descriptor":
                    continue
                descriptor_accepted = any(
                    row.get("ref", {}).get("revision_digest")
                    == descriptor.digest
                    and _typed_ref_identity(row.get("ref"))
                    == _typed_ref_identity(descriptor.ref.as_dict())
                    for row in execution_descriptors
                )
                if not descriptor_accepted:
                    continue
                if (
                    _typed_ref_identity(descriptor.body.get("attempt_ref"))
                    != attempt_identity
                    or canonical_bytes(
                        descriptor.body.get("input_history_cut")
                    )
                    != canonical_bytes(discovery_cut)
                ):
                    continue
                descriptor_cut_seq = _exact_lane_completion_cut_seq(
                    descriptor.body.get("input_history_cut"),
                    campaign_id=current.campaign_id,
                    max_seq=lane_cut,
                    con=con,
                    context="execution_descriptor",
                )
                if descriptor_cut_seq < _cut_seq(
                    attempt.body.get("assigned_history_cut"), context="attempt"
                ):
                    continue
                matching_execution_result = True
                break
            if not matching_execution_result:
                raise ValidationError("LANE_COMPLETION_EXECUTION_RESULT_REQUIRED")
        return

    # Every result used by the completion must itself be accepted (in the
    # parent history or this exact atomic closure) and bound to an assignment
    # for this lane, stage, and one of the declared attempts.
    used_result_attempt_by_digest: dict[str, tuple] = {}
    used_result_body_by_digest: dict[str, dict[str, Any]] = {}
    for target in output_result_targets:
        digest = target.digest
        accepted_match = next(
            (
                row
                for row in accepted_results
                if row.get("ref", {}).get("revision_digest") == digest
                and _typed_ref_identity(row.get("ref"))
                == _typed_ref_identity(target.ref.as_dict())
            ),
            None,
        )
        in_closure = any(candidate.digest == digest for candidate in result_objects)
        if accepted_match is None and not in_closure:
            raise ValidationError("LANE_COMPLETION_RESULT_NOT_ACCEPTED")
        if accepted_match is not None:
            result_seq = int(accepted_match.get("accepted_seq", 0))
            same_atomic_commit = (
                lane_completion_record is not None
                and result_seq
                == int(lane_completion_record.get("accepted_seq", 0))
                == lane_cut + 1
            )
            if result_seq > lane_cut and not same_atomic_commit:
                raise ValidationError("LANE_COMPLETION_RESULT_CUT_MISMATCH")
        elif lane_completion_record is not None or lane_cut != current.commit_seq:
            raise ValidationError("LANE_COMPLETION_RESULT_CUT_MISMATCH")

        result_body = target.body
        result_attempt_ref = result_body.get("attempt_ref")
        result_assignment_ref = result_body.get("assignment_ref")
        assignment = assignments_by_attempt.get(
            _typed_ref_identity(result_attempt_ref)
        )
        if (
            assignment is None
            or _typed_ref_identity(result_assignment_ref)
            != _typed_ref_identity(assignment.get("ref"))
            or result_body.get("stage_id") != stage_key
            or _stage_slot_key(stage_key, result_body.get("lane_slot"))
            != _stage_slot_key(stage_key, lane_spec.body.get("lane_key"))
            or result_body.get("campaign_id")
            != (current.campaign_id if current is not None else None)
            or canonical_bytes(result_body.get("history_cut"))
            != canonical_bytes(
                assignment["body"].get("assignment_input_history_cut")
            )
        ):
            raise ValidationError("LANE_COMPLETION_RESULT_PROVENANCE_MISMATCH")
        used_result_attempt_by_digest[digest] = _typed_ref_identity(
            result_attempt_ref
        )
        used_result_body_by_digest[digest] = result_body

    final_attempt_ref = matching_attempt[0]
    final_assignment = assignments_by_attempt.get(
        _typed_ref_identity(final_attempt_ref)
    )
    if final_assignment is None or not any(
        _typed_ref_identity(target.body.get("attempt_ref"))
        == _typed_ref_identity(final_attempt_ref)
        and _typed_ref_identity(target.body.get("assignment_ref"))
        == _typed_ref_identity(final_assignment.get("ref"))
        for target in output_result_targets
    ):
        raise ValidationError("LANE_COMPLETION_FINAL_ATTEMPT_RESULT_REQUIRED")

    attempt_identities = set(assignments_by_attempt)
    assignment_identities = {
        key: _typed_ref_identity(value.get("ref"))
        for key, value in assignments_by_attempt.items()
    }
    lane_run_identity = _typed_ref_identity(body.get("lane_run_ref"))
    accepted_knowledge = _accepted_completion_records(
        "knowledge_state", current=current, con=con
    )
    for target in output_targets:
        if target.kind == "bdb_audit_lane_result":
            continue
        out_body = target.body
        if target.kind == "discovery_record":
            if (
                _typed_ref_identity(out_body.get("lane_run_ref"))
                != lane_run_identity
                or _typed_ref_identity(out_body.get("attempt_ref"))
                not in attempt_identities
                or _typed_ref_identity(out_body.get("source_generation_ref"))
                != _typed_ref_identity(stage_run.body.get("source_generation_ref"))
                or (
                    out_body.get("stage_id") is not None
                    and out_body.get("stage_id") != stage_key
                )
            ):
                raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")
            result_digest = out_body.get("result_proposal_digest")
            discovery_attempt = _typed_ref_identity(out_body.get("attempt_ref"))
            if result_digest is not None:
                result_body = used_result_body_by_digest.get(result_digest)
                if (
                    result_body is None
                    or used_result_attempt_by_digest.get(result_digest)
                    != discovery_attempt
                    or (
                        out_body.get("phase_id") is not None
                        and result_body.get("phase_id") is not None
                        and out_body.get("phase_id")
                        != result_body.get("phase_id")
                    )
                ):
                    raise ValidationError("LANE_COMPLETION_OUTPUT_RESULT_MISMATCH")
            discovery_cut_seq = _exact_lane_completion_cut_seq(
                out_body.get("discovery_input_history_cut"),
                campaign_id=current.campaign_id,
                max_seq=lane_cut,
                con=con,
                context="discovery_record",
            )
            assignment = assignments_by_attempt.get(discovery_attempt)
            if assignment is None or discovery_cut_seq < int(
                assignment.get("accepted_seq", 0)
            ):
                raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")
            knowledge_ref = out_body.get("knowledge_state_ref")
            knowledge = _resolve_completion_object(
                knowledge_ref,
                content_objects=content_objects,
                con=con,
                context="discovery_record.knowledge_state_ref",
            )
            knowledge_record = next(
                (
                    row
                    for row in accepted_knowledge
                    if row.get("ref", {}).get("revision_digest")
                    == knowledge.digest
                    and _typed_ref_identity(row.get("ref"))
                    == _typed_ref_identity(knowledge.ref.as_dict())
                ),
                None,
            )
            if (
                knowledge.kind != "knowledge_state"
                or _typed_ref_identity(knowledge.body.get("attempt_ref"))
                != discovery_attempt
                or knowledge_record is None
                or int(knowledge_record.get("accepted_seq", 0))
                > discovery_cut_seq
            ):
                raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")
            slot = out_body.get("lane_slot")
            if slot is not None and _stage_slot_key(stage_key, slot) != _stage_slot_key(
                stage_key, lane_spec.body.get("lane_key")
            ):
                raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")
            continue

        bindings = 0
        if "lane_run_ref" in out_body:
            bindings += 1
            if _typed_ref_identity(out_body.get("lane_run_ref")) != lane_run_identity:
                raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")
        if "attempt_ref" in out_body:
            bindings += 1
            if _typed_ref_identity(out_body.get("attempt_ref")) not in attempt_identities:
                raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")
        if "assignment_ref" in out_body:
            bindings += 1
            if _typed_ref_identity(out_body.get("assignment_ref")) not in set(
                assignment_identities.values()
            ):
                raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")
        if "result_proposal_digest" in out_body:
            bindings += 1
            if out_body.get("result_proposal_digest") not in used_result_attempt_by_digest:
                raise ValidationError("LANE_COMPLETION_OUTPUT_RESULT_MISMATCH")
        if "source_generation_ref" in out_body and _typed_ref_identity(
            out_body.get("source_generation_ref")
        ) != _typed_ref_identity(stage_run.body.get("source_generation_ref")):
            raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")
        if "stage_id" in out_body and out_body.get("stage_id") != stage_key:
            raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")
        if "lane_slot" in out_body and _stage_slot_key(
            stage_key, out_body.get("lane_slot")
        ) != _stage_slot_key(stage_key, lane_spec.body.get("lane_key")):
            raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_MISMATCH")
        if bindings == 0:
            raise ValidationError("LANE_COMPLETION_OUTPUT_PROVENANCE_REQUIRED")


def _validate_e3_blind_checkpoint(obj, *, content_objects, current, con):
    body = obj.body
    if body.get("stage_id") != "E3" or body.get("phase_id") != "E3-BLIND":
        return
    if current is None:
        raise ValidationError("E3_BLIND_CHECKPOINT_REQUIRES_ACCEPTED_RESULT")

    from ..history.store import _commit_from_body
    from ..stop.authority import _accepted_index, _records

    index = _accepted_index(current, con)
    cut = body.get("checkpoint_input_history_cut")
    cut_seq = _cut_seq(cut, context="e3_blind_checkpoint")
    if cut.get("campaign_id") != current.campaign_id:
        raise ValidationError("E3_BLIND_CHECKPOINT_CUT_MISMATCH")
    cut_row = con.execute(
        "SELECT commit_hash,body FROM commits WHERE seq=?", (cut_seq,)
    ).fetchone()
    if cut_row is None:
        raise ValidationError("E3_BLIND_CHECKPOINT_CUT_MISMATCH")
    cut_commit = _commit_from_body(json.loads(cut_row[1]))
    if cut_commit.digest != cut_row[0] or cut.get("accepted_head_hash") != cut_row[0]:
        raise ValidationError("E3_BLIND_CHECKPOINT_CUT_MISMATCH")

    checkpoint_membership = index.get(("checkpoint", obj.digest))
    if checkpoint_membership is None:
        if cut_seq != current.commit_seq or cut_row[0] != current.commit_hash:
            raise ValidationError("E3_BLIND_CHECKPOINT_CUT_MISMATCH")
    elif int(checkpoint_membership.get("accepted_seq", 0)) != cut_seq + 1:
        raise ValidationError("E3_BLIND_CHECKPOINT_CUT_MISMATCH")

    stage_run = _resolve_completion_object(
        body.get("stage_run_ref"),
        content_objects=content_objects,
        con=con,
        context="checkpoint.stage_run_ref",
    )
    lane_run = _resolve_completion_object(
        body.get("lane_run_ref"),
        content_objects=content_objects,
        con=con,
        context="checkpoint.lane_run_ref",
    )
    attempt = _resolve_completion_object(
        body.get("attempt_ref"),
        content_objects=content_objects,
        con=con,
        context="checkpoint.attempt_ref",
    )
    source = _resolve_completion_object(
        body.get("source_generation_ref"),
        content_objects=content_objects,
        con=con,
        context="checkpoint.source_generation_ref",
    )
    knowledge = _resolve_completion_object(
        body.get("knowledge_state_ref"),
        content_objects=content_objects,
        con=con,
        context="checkpoint.knowledge_state_ref",
    )
    if (
        stage_run.kind != "stage_run"
        or lane_run.kind != "lane_run"
        or attempt.kind != "attempt"
        or source.kind != "source_generation"
        or knowledge.kind != "knowledge_state"
        or _typed_ref_identity(lane_run.body.get("stage_run_ref"))
        != _typed_ref_identity(body.get("stage_run_ref"))
        or _typed_ref_identity(attempt.body.get("lane_run_ref"))
        != _typed_ref_identity(body.get("lane_run_ref"))
        or _typed_ref_identity(lane_run.body.get("source_generation_ref"))
        != _typed_ref_identity(body.get("source_generation_ref"))
        or _typed_ref_identity(stage_run.body.get("source_generation_ref"))
        != _typed_ref_identity(body.get("source_generation_ref"))
        or _typed_ref_identity(knowledge.body.get("attempt_ref"))
        != _typed_ref_identity(body.get("attempt_ref"))
    ):
        raise ValidationError("E3_BLIND_CHECKPOINT_CONTEXT_BINDING_MISMATCH")

    stage_spec = _resolve_completion_object(
        stage_run.body.get("stage_spec_ref"),
        content_objects=content_objects,
        con=con,
        context="checkpoint.stage_spec_ref",
    )
    lane_spec = _resolve_completion_object(
        lane_run.body.get("lane_spec_ref"),
        content_objects=content_objects,
        con=con,
        context="checkpoint.lane_spec_ref",
    )
    if (
        stage_spec.kind != "stage_spec"
        or stage_spec.body.get("stage_key") != "E3"
        or lane_spec.kind != "lane_spec"
        or str(lane_spec.body.get("stage_spec_revision"))
        != str(stage_spec.body.get("stage_spec_revision"))
        or _stage_slot_key("E3", body.get("lane_slot"))
        != _stage_slot_key("E3", lane_spec.body.get("lane_key"))
    ):
        raise ValidationError("E3_BLIND_CHECKPOINT_CONTEXT_BINDING_MISMATCH")

    assignments = _records("assignment_manifest", index, con)
    matching_assignments = [
        row
        for row in assignments
        if _typed_ref_identity(row["body"].get("attempt_ref"))
        == _typed_ref_identity(body.get("attempt_ref"))
        and _typed_ref_identity(row["body"].get("lane_spec_ref"))
        == _typed_ref_identity(lane_run.body.get("lane_spec_ref"))
        and _typed_ref_identity(row["body"].get("stage_spec_ref"))
        == _typed_ref_identity(stage_run.body.get("stage_spec_ref"))
        and _typed_ref_identity(row["body"].get("source_generation_ref"))
        == _typed_ref_identity(body.get("source_generation_ref"))
    ]
    if len(matching_assignments) != 1:
        raise ValidationError("E3_BLIND_CHECKPOINT_ASSIGNMENT_MISMATCH")
    assignment = matching_assignments[0]
    if _typed_ref_identity(
        assignment["body"].get("knowledge_state_ref")
    ) != _typed_ref_identity(body.get("knowledge_state_ref")):
        raise ValidationError("E3_BLIND_CHECKPOINT_CONTEXT_BINDING_MISMATCH")

    result_rows = [
        row
        for row in _records("bdb_audit_lane_result", index, con)
        if row["body"].get("stage_id") == "E3"
        and row["body"].get("phase_id") == "E3-BLIND"
        and _typed_ref_identity(row["body"].get("assignment_ref"))
        == _typed_ref_identity(assignment["ref"])
        and _typed_ref_identity(row["body"].get("attempt_ref"))
        == _typed_ref_identity(body.get("attempt_ref"))
        and _stage_slot_key("E3", row["body"].get("lane_slot"))
        == _stage_slot_key("E3", lane_spec.body.get("lane_key"))
    ]
    if len(result_rows) != 1:
        raise ValidationError("E3_BLIND_CHECKPOINT_ACCEPTED_RESULT_REQUIRED")
    result = result_rows[0]
    result_digest = result["ref"]["revision_digest"]
    if (
        int(result.get("accepted_seq", 0)) > cut_seq
        or canonical_bytes(result["body"].get("history_cut"))
        != canonical_bytes(assignment["body"].get("assignment_input_history_cut"))
    ):
        raise ValidationError("E3_BLIND_CHECKPOINT_RESULT_BINDING_MISMATCH")

    sealed_refs = body.get("sealed_output_refs")
    if not isinstance(sealed_refs, (list, tuple)):
        raise ValidationError("E3_BLIND_CHECKPOINT_SEALED_OUTPUTS_INVALID")
    sealed_targets = [
        _resolve_completion_object(
            ref,
            content_objects=content_objects,
            con=con,
            context="checkpoint.sealed_output_refs",
        )
        for ref in sealed_refs
    ]
    sealed_digests = [target.digest for target in sealed_targets]
    if len(sealed_digests) != len(set(sealed_digests)) or result_digest not in sealed_digests:
        raise ValidationError("E3_BLIND_CHECKPOINT_SEALED_OUTPUTS_INVALID")

    discovery_records = list(_records("discovery_record", index, con))
    closure_discoveries = [
        candidate
        for candidate in content_objects
        if candidate.kind == "discovery_record"
    ]
    discoveries_by_digest = {
        row["ref"]["revision_digest"]: row["body"]
        for row in discovery_records
        if row["body"].get("result_proposal_digest") == result_digest
    }
    discoveries_by_digest.update(
        {
            candidate.digest: candidate.body
            for candidate in closure_discoveries
            if candidate.body.get("result_proposal_digest") == result_digest
        }
    )
    findings = result["body"].get("findings")
    if not isinstance(findings, list) or len(discoveries_by_digest) != len(findings):
        raise ValidationError("E3_BLIND_CHECKPOINT_DISCOVERY_RESULT_MISMATCH")
    expected_discovery_digests: set[str] = set()
    seen_indexes: set[int] = set()
    for digest, discovery in discoveries_by_digest.items():
        finding_index = discovery.get("submission_finding_index")
        if (
            type(finding_index) is not int
            or finding_index < 0
            or finding_index >= len(findings)
            or finding_index in seen_indexes
            or discovery.get("result_proposal_digest") != result_digest
            or discovery.get("stage_id") != "E3"
            or discovery.get("phase_id") != "E3-BLIND"
            or _stage_slot_key("E3", discovery.get("lane_slot"))
            != _stage_slot_key("E3", lane_spec.body.get("lane_key"))
            or _typed_ref_identity(discovery.get("lane_run_ref"))
            != _typed_ref_identity(body.get("lane_run_ref"))
            or _typed_ref_identity(discovery.get("attempt_ref"))
            != _typed_ref_identity(body.get("attempt_ref"))
            or _typed_ref_identity(discovery.get("source_generation_ref"))
            != _typed_ref_identity(body.get("source_generation_ref"))
            or _typed_ref_identity(discovery.get("knowledge_state_ref"))
            != _typed_ref_identity(body.get("knowledge_state_ref"))
            or canonical_bytes(discovery.get("discovery_input_history_cut"))
            != canonical_bytes(cut)
            or discovery.get("submission_finding_fingerprint")
            != hashlib.sha256(canonical_bytes(findings[finding_index])).hexdigest()
        ):
            raise ValidationError("E3_BLIND_CHECKPOINT_DISCOVERY_RESULT_MISMATCH")
        seen_indexes.add(finding_index)
        expected_discovery_digests.add(digest)
    if seen_indexes != set(range(len(findings))):
        raise ValidationError("E3_BLIND_CHECKPOINT_DISCOVERY_RESULT_MISMATCH")

    if set(sealed_digests) != {result_digest, *expected_discovery_digests}:
        raise ValidationError("E3_BLIND_CHECKPOINT_SEALED_OUTPUTS_INVALID")


def validate_e3_blind_checkpoint_provenance(checkpoint, *, current, con):
    """Revalidate an accepted checkpoint through the canonical authority path."""
    _validate_e3_blind_checkpoint(
        checkpoint,
        content_objects=(),
        current=current,
        con=con,
    )


def _validate_stage_completion(obj, *, content_objects, current, con):
    body = obj.body
    from ..stop.models import validate_stage_completion_body

    validate_stage_completion_body(body)
    if body.get("completion_predicate_result") != "STAGE_COMPLETED":
        return
    lane_refs = body.get("required_lane_slot_results")
    output_refs = body.get("required_output_refs")
    if not lane_refs or not output_refs:
        raise ValidationError("STAGE_COMPLETION_EXECUTION_EVIDENCE_REQUIRED")

    stage_run = _resolve_completion_object(
        body.get("stage_run_ref"), content_objects=content_objects, con=con, context="stage_run_ref"
    )
    stage_spec = _resolve_completion_object(
        body.get("stage_spec_ref"), content_objects=content_objects, con=con, context="stage_spec_ref"
    )
    if stage_run.kind != "stage_run" or stage_spec.kind != "stage_spec":
        raise ValidationError("STAGE_COMPLETION_CONTEXT_KIND_MISMATCH")
    if _typed_ref_identity(stage_run.body.get("stage_spec_ref")) != _typed_ref_identity(body.get("stage_spec_ref")):
        raise ValidationError("STAGE_COMPLETION_SPEC_BINDING_MISMATCH")

    if current is None:
        raise ValidationError("STAGE_COMPLETION_SPEC_NOT_PRIOR_ACCEPTED")
    from ..stop.authority import _accepted_index

    accepted = _accepted_index(current, con)
    stage_spec_digest = stage_spec.digest
    membership = accepted.get(("stage_spec", stage_spec_digest))
    if membership is None:
        raise ValidationError("STAGE_COMPLETION_SPEC_NOT_PRIOR_ACCEPTED")
    accepted_spec_ref = membership["ref"]
    if _typed_ref_identity(accepted_spec_ref) != _typed_ref_identity(body.get("stage_spec_ref")):
        raise ValidationError("STAGE_COMPLETION_SPEC_NOT_GOVERNING_REVISION")

    stage_key = stage_spec.body.get("stage_key")
    required_slots = stage_spec.body.get("required_lane_slots")
    required_outputs = stage_spec.body.get("required_stage_completion_outputs")
    if not isinstance(stage_key, str) or not required_slots or not required_outputs:
        raise ValidationError("STAGE_COMPLETION_SPEC_OBLIGATIONS_UNRESOLVED")
    if stage_key in {"E1", "E2", "E3", "E4", "E5"}:
        _validate_native_stage_spec_authority(stage_spec)
    elif stage_key == "E6":
        # Store-side E6 StageSpec admission is pinned to accepted STOP-derived
        # authority, but execution remains unavailable in this candidate.
        raise ValidationError("E6_EXECUTION_UNAVAILABLE")
    else:
        raise ValidationError("STAGE_COMPLETION_SPEC_NOT_GOVERNING_REVISION", stage_key)
    declared_outputs = body.get("mandatory_obligation_summary", {}).get(
        "required_stage_completion_outputs"
    )
    if declared_outputs != required_outputs:
        raise ValidationError("STAGE_COMPLETION_REQUIRED_OUTPUTS_MISMATCH")
    expected = {_stage_slot_key(stage_key, value) for value in required_slots}
    stage_cut = _cut_seq(body.get("input_history_cut"), context="stage_completion")

    observed = set()
    lane_output_digests = set()
    for lane_ref in lane_refs:
        lane_completion = _resolve_completion_object(
            lane_ref, content_objects=content_objects, con=con, context="required_lane_slot_results"
        )
        if lane_completion.kind != "lane_completion":
            raise ValidationError("STAGE_COMPLETION_LANE_KIND_MISMATCH")
        if lane_completion.body.get("completion_predicate_result") != "LANE_COMPLETED":
            raise ValidationError("STAGE_COMPLETION_LANE_NOT_COMPLETED")
        _validate_lane_completion(
            lane_completion,
            content_objects=content_objects,
            con=con,
            current=current,
        )
        if _typed_ref_identity(lane_completion.body.get("lane_run_ref")) is None:
            raise ValidationError("STAGE_COMPLETION_LANE_RUN_REQUIRED")
        lane_run = _resolve_completion_object(
            lane_completion.body["lane_run_ref"],
            content_objects=content_objects,
            con=con,
            context="lane_completion.lane_run_ref",
        )
        if lane_run.kind != "lane_run" or _typed_ref_identity(lane_run.body.get("stage_run_ref")) != _typed_ref_identity(
            body.get("stage_run_ref")
        ):
            raise ValidationError("STAGE_COMPLETION_LANE_STAGE_RUN_MISMATCH")
        if _typed_ref_identity(lane_run.body.get("source_generation_ref")) != _typed_ref_identity(
            stage_run.body.get("source_generation_ref")
        ):
            raise ValidationError("STAGE_COMPLETION_SOURCE_BINDING_MISMATCH")
        if _cut_seq(lane_completion.body.get("input_history_cut"), context="lane_completion") > stage_cut:
            raise ValidationError("STAGE_COMPLETION_LANE_CUT_MISMATCH")
        lane_spec = _resolve_completion_object(
            lane_completion.body.get("lane_spec_ref"),
            content_objects=content_objects,
            con=con,
            context="lane_completion.lane_spec_ref",
        )
        if lane_spec.kind != "lane_spec":
            raise ValidationError("STAGE_COMPLETION_LANE_SPEC_KIND_MISMATCH")
        if str(lane_spec.body.get("stage_spec_revision")) != str(
            stage_spec.body.get("stage_spec_revision")
        ):
            raise ValidationError("STAGE_COMPLETION_LANE_SPEC_REVISION_MISMATCH")
        lane_key = lane_spec.body.get("lane_key")
        if not isinstance(lane_key, str):
            raise ValidationError("STAGE_COMPLETION_LANE_KEY_REQUIRED")
        slot = _stage_slot_key(stage_key, lane_key)
        if slot not in expected:
            optional = {
                _stage_slot_key(stage_key, value)
                for value in stage_spec.body.get("optional_lane_slots", ())
            }
            if slot not in optional:
                raise ValidationError("STAGE_COMPLETION_UNEXPECTED_LANE_SLOT", lane_key)
        if slot in observed:
            raise ValidationError("STAGE_COMPLETION_DUPLICATE_LANE_SLOT", lane_key)
        observed.add(slot)
        lane_output_digests.update(
            ref.get("revision_digest")
            for ref in lane_completion.body.get("required_output_refs", ())
            if isinstance(ref, dict)
        )

    if observed != expected:
        raise ValidationError(
            "STAGE_COMPLETION_REQUIRED_LANE_SLOTS_MISMATCH",
            f"required={sorted(expected)}; observed={sorted(observed)}",
        )

    resolved_output_digests = set()
    resolved_output_targets = []
    for output_ref in output_refs:
        target = _resolve_completion_object(
            output_ref, content_objects=content_objects, con=con, context="required_output_refs"
        )
        if target.kind in _NON_OUTPUT_KINDS:
            raise ValidationError("STAGE_COMPLETION_OUTPUT_KIND_INVALID", target.kind)
        if target.digest in resolved_output_digests:
            raise ValidationError("STAGE_COMPLETION_DUPLICATE_OUTPUT_REF")
        resolved_output_digests.add(target.digest)
        resolved_output_targets.append(target)
    if not lane_output_digests.issubset(resolved_output_digests):
        raise ValidationError("STAGE_COMPLETION_LANE_OUTPUTS_OMITTED")
    _validate_stage_output_obligations(
        stage_key,
        required_outputs,
        resolved_output_targets,
        stage_run=stage_run,
        lane_output_digests=lane_output_digests,
        content_objects=content_objects,
        con=con,
    )


def _validate_isolation_qualification(obj, *, content_objects, con) -> None:
    """Validate attempt/profile bindings; fail closed on unresolved ENFORCED channels."""
    body = obj.body
    attempt = _resolve_isolation_context_object(
        body.get("attempt_ref"), content_objects=content_objects, con=con
    )
    if attempt.kind != "attempt":
        raise ValidationError("ISOLATION_ATTEMPT_CONTEXT_IDENTITY_MISMATCH")
    for field in ("executor_profile_ref", "delivery_profile_ref"):
        if _typed_ref_identity(body.get(field)) != _typed_ref_identity(attempt.body.get(field)):
            raise ValidationError("ISOLATION_ATTEMPT_PROFILE_MISMATCH", field)

    lane_run = _resolve_isolation_context_object(
        attempt.body.get("lane_run_ref"), content_objects=content_objects, con=con
    )
    if lane_run.kind != "lane_run":
        raise ValidationError("ISOLATION_ATTEMPT_CONTEXT_IDENTITY_MISMATCH")
    lane_spec = _resolve_isolation_context_object(
        lane_run.body.get("lane_spec_ref"), content_objects=content_objects, con=con
    )
    if lane_spec.kind != "lane_spec":
        raise ValidationError("ISOLATION_ATTEMPT_CONTEXT_IDENTITY_MISMATCH")
    if body.get("required_isolation_assurance") != lane_spec.body.get(
        "required_isolation_assurance"
    ):
        raise ValidationError("ISOLATION_REQUIRED_ASSURANCE_MISMATCH")

    if body.get("result") != "ENFORCED":
        return
    if (
        not isinstance(body.get("channel_inventory_ref"), dict)
        or not body.get("enforcement_receipt_refs")
        or not body.get("session_boundary_evidence_refs")
    ):
        raise ValidationError("ISOLATION_ENFORCEMENT_EVIDENCE_REQUIRED")

    # R5.3 requires a policy-derived witness for every material channel. The
    # pinned registry supplies channel names and prose witness descriptions,
    # but no executable mapping from those channels to evidence refs. Treat
    # unknown mappings as unverifiable instead of inferring a fixed five-list
    # quorum from the artifact's wire fields.
    raise ValidationError(
        "ISOLATION_MATERIAL_CHANNELS_UNRESOLVED",
        "Pinned channel inventory and executor/lane evidence mapping is not machine-resolvable",
    )


def install_domain_authority_hooks(store_cls) -> None:
    """Install fail-closed domain authority checks exactly once."""
    original_material = store_cls._validate_material_ref_contracts
    if getattr(original_material, "_bdb_domain_authority_hooks", False):
        return

    original_prior = store_cls._validate_prior_accepted_membership

    @wraps(original_prior)
    def validate_prior_accepted_membership(self, ref, *, consumer_kind, current, con):
        original_prior(self, ref, consumer_kind=consumer_kind, current=current, con=con)
        _validate_overlay_prior_accepted(
            self,
            ref,
            consumer_kind=consumer_kind,
            current=current,
            con=con,
        )

    @wraps(original_material)
    def validate_material_ref_contracts(
        self, obj, *, current, con, content_objects=()
    ):
        original_material(
            self,
            obj,
            current=current,
            con=con,
            content_objects=content_objects,
        )
        if obj.kind == "stage_spec" and obj.body.get("stage_key") in {"E1", "E2", "E3", "E4", "E5"}:
            _validate_native_stage_spec_authority(obj)
        elif obj.kind == "stage_spec" and obj.body.get("stage_key") == "E6":
            from ..stop.e6 import validate_adaptive_e6_stage_spec_authority

            validate_adaptive_e6_stage_spec_authority(obj, current=current, con=con)
        elif obj.kind == "residual_risk":
            _validate_residual_risk_authority(obj, con=con)
        elif obj.kind == "candidate_assurance_case":
            _validate_candidate_residual_risk_projection(
                obj,
                current=current,
                con=con,
                content_objects=content_objects,
            )
        elif obj.kind == "finding_claim_revision":
            _validate_finding_claim_lineage(obj, con=con)
        elif obj.kind == "isolation_qualification":
            _validate_isolation_qualification(
                obj, content_objects=content_objects, con=con
            )
        elif obj.kind == "lane_result_admission_evidence":
            _validate_lane_result_admission_evidence(
                obj, content_objects=content_objects, current=current, con=con
            )
        elif obj.kind == "bdb_audit_lane_result":
            _validate_lane_result(
                obj, content_objects=content_objects, current=current, con=con
            )
        elif obj.kind == "lane_completion":
            _validate_lane_completion(
                obj, content_objects=content_objects, con=con, current=current
            )
        elif obj.kind == "stage_completion":
            _validate_stage_completion(
                obj, content_objects=content_objects, current=current, con=con
            )
        elif obj.kind == "checkpoint":
            _validate_e3_blind_checkpoint(
                obj, content_objects=content_objects, current=current, con=con
            )
        elif obj.kind == "stop_input":
            _validate_stop_residual_risk_projection(
                obj,
                current=current,
                con=con,
                content_objects=content_objects,
            )
        elif obj.kind in {"campaign_conclusion", "final_assurance_case", "release_qualification"}:
            _validate_finalization_basis(obj, current=current, con=con)
            _validate_finalization_residual_risk_projection(obj, current=current, con=con)

    validate_prior_accepted_membership._bdb_overlay_prior_authority = True
    validate_material_ref_contracts._bdb_domain_authority_hooks = True
    store_cls._validate_prior_accepted_membership = validate_prior_accepted_membership
    store_cls._validate_material_ref_contracts = validate_material_ref_contracts


__all__ = ["install_domain_authority_hooks"]

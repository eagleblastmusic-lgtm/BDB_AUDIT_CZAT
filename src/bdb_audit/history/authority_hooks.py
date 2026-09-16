"""Explicit trusted-history authority extensions.

The durable adapter keeps generic registry/reference mechanics in ``store.py``.
Domain-specific equality checks are installed here on the same pre-durability
validation methods. Installation is idempotent and occurs during package import,
which Python executes before either ``bdb_audit.history`` or
``bdb_audit.history.store`` can be returned to a caller.
"""
from __future__ import annotations

from functools import wraps
import json

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


def _stop_risk_set(stop_eval_ref, index, con) -> set[str]:
    stop_eval_digest = stop_eval_ref.get("revision_digest") if isinstance(stop_eval_ref, dict) else None
    stop_eval = _accepted_body("stop_evaluation", stop_eval_digest, index, con)
    stop_input_ref = stop_eval.get("stop_input_ref")
    stop_input_digest = stop_input_ref.get("revision_digest") if isinstance(stop_input_ref, dict) else None
    stop_input = _accepted_body("stop_input", stop_input_digest, index, con)
    return _digest_set(stop_input.get("residual_risk_refs", ()))


def _validate_candidate_residual_risk_projection(obj, *, current, con) -> None:
    rows, _current, _index = _active_risk_rows(current, con)
    expected = _digest_set(row["ref"] for row in rows)
    if _digest_set(obj.body.get("residual_risk_refs", ())) != expected:
        raise ValidationError("CANDIDATE_RESIDUAL_RISK_PROJECTION_MISMATCH")


def _validate_stop_residual_risk_projection(obj, *, current, con) -> None:
    """Equality-check StopInput's residual-risk set against accepted history."""
    if current is None:
        raise ValidationError("STOP_INPUT_REQUIRES_ACCEPTED_PARENT")

    from ..stop.residual_risk_projection import _risk_summary

    active_rows, _current, _index = _active_risk_rows(current, con)
    expected_refs = [row["ref"] for row in active_rows]
    actual_refs = obj.body.get("residual_risk_refs", ())
    if _digest_set(actual_refs) != _digest_set(expected_refs):
        raise ValidationError("STOP_CURRENT_PROJECTION_MISMATCH", "residual_risk_refs")

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
    def validate_material_ref_contracts(self, obj, *, current, con):
        original_material(self, obj, current=current, con=con)
        if obj.kind == "stage_spec" and obj.body.get("stage_key") == "E6":
            from ..stop.e6 import validate_adaptive_e6_stage_spec_authority

            validate_adaptive_e6_stage_spec_authority(obj, current=current, con=con)
        elif obj.kind == "residual_risk":
            _validate_residual_risk_authority(obj, con=con)
        elif obj.kind == "candidate_assurance_case":
            _validate_candidate_residual_risk_projection(obj, current=current, con=con)
        elif obj.kind == "stop_input":
            _validate_stop_residual_risk_projection(obj, current=current, con=con)
        elif obj.kind in {"campaign_conclusion", "final_assurance_case", "release_qualification"}:
            _validate_finalization_residual_risk_projection(obj, current=current, con=con)

    validate_prior_accepted_membership._bdb_overlay_prior_authority = True
    validate_material_ref_contracts._bdb_domain_authority_hooks = True
    store_cls._validate_prior_accepted_membership = validate_prior_accepted_membership
    store_cls._validate_material_ref_contracts = validate_material_ref_contracts


__all__ = ["install_domain_authority_hooks"]

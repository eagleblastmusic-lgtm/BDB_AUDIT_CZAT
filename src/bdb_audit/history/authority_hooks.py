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


def _validate_stop_residual_risk_projection(obj, *, current, con) -> None:
    """Equality-check StopInput's residual-risk set against accepted history."""
    if current is None:
        raise ValidationError("STOP_INPUT_REQUIRES_ACCEPTED_PARENT")

    from ..stop.authority import _accepted_index, _digest_set, _latest_by, _records
    from ..stop.residual_risk_projection import _risk_summary

    index = _accepted_index(current, con)
    current_risks = _latest_by(
        _records("residual_risk", index, con),
        lambda row: str(row["body"].get("risk_id") or row["ref"]["revision_digest"]),
    )
    active_rows = tuple(
        current_risks[key]
        for key in sorted(current_risks)
        if current_risks[key]["body"].get("disposition") != "SUPERSEDED"
    )
    expected_refs = [row["ref"] for row in active_rows]
    actual_refs = obj.body.get("residual_risk_refs", ())
    if _digest_set(actual_refs) != _digest_set(expected_refs):
        raise ValidationError("STOP_CURRENT_PROJECTION_MISMATCH", "residual_risk_refs")

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
        elif obj.kind == "stop_input":
            _validate_stop_residual_risk_projection(obj, current=current, con=con)

    validate_prior_accepted_membership._bdb_overlay_prior_authority = True
    validate_material_ref_contracts._bdb_domain_authority_hooks = True
    store_cls._validate_prior_accepted_membership = validate_prior_accepted_membership
    store_cls._validate_material_ref_contracts = validate_material_ref_contracts


__all__ = ["install_domain_authority_hooks"]

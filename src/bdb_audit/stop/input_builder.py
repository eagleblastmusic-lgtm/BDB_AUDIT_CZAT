"""Deterministic StopInput Builder from Verified Accepted History (B02 / §103).

Constructs an immutable StopInput derived strictly from accepted history records,
never from unadmitted proposals, object-table orphans, fixed placeholder digests,
or in-memory caches.
"""
from __future__ import annotations

import hashlib
from typing import Any, Iterable, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from .models import StopInput


def _ref(kind: str, digest: str, ref_class: str = "CONTENT_OR_PRIOR", *, schema_ref: str | None = None) -> dict[str, Any]:
    return {
        "kind": kind,
        "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": schema_ref or f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
    }


def _latest(records: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    records = tuple(records)
    if not records:
        return None
    return max(records, key=lambda row: int(row.get("accepted_seq", 0)))


def _latest_by(records: Iterable[dict[str, Any]], key_fn) -> tuple[dict[str, Any], ...]:
    selected: dict[str, dict[str, Any]] = {}
    for row in records:
        key = key_fn(row)
        if not key:
            continue
        prior = selected.get(key)
        if prior is None or int(row.get("accepted_seq", 0)) > int(prior.get("accepted_seq", 0)):
            selected[key] = row
    return tuple(selected[key] for key in sorted(selected))


def _identity_digest(value: str) -> str:
    value = str(value)
    if len(value) == 64 and all(ch in "0123456789abcdef" for ch in value.lower()):
        return value.lower()
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _history_context_ref(kind: str, effective_token: str) -> dict[str, Any]:
    """Bind a typed context locator to an exact effective history pin.

    This is not an accepted-content claim: HISTORY_CONTEXT_BINDING records the
    exact semantic token already effective at the input history cut.
    """
    return _ref(kind, _identity_digest(effective_token), "HISTORY_CONTEXT_BINDING")


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


class StopInputBuilder:
    """Extracts one exact reproducible StopInput from one verified accepted cut."""

    @classmethod
    def build_from_store(
        cls,
        store: TransactionalHistoryStore,
        evaluation_context: str = "FINAL_POST_E5",
        candidate_assurance_case_ref: dict[str, Any] | None = None,
        challenger_refs: Sequence[dict[str, Any]] = (),
        unknown_blocked_summary: dict[str, Any] | None = None,
        e6_plan_approved: bool = False,
    ) -> StopInput:
        from ..workflow.read_models import campaign_source_identity, current_accepted_cut

        head = store.head()
        if head is None:
            raise ValidationError("EMPTY_STORE", "Cannot build StopInput on empty store")
        cut = current_accepted_cut(store)

        # Source authority is resolved through accepted genesis -> generation -> identity.
        source_projection = campaign_source_identity(store, cut)
        sg_ref = dict(source_projection["source_generation_ref"], ref_class="CONTENT_OR_PRIOR")
        store.resolve_accepted(sg_ref, cut)

        # Stage plan: one current revision per stage key, selected by acceptance time.
        stage_specs_all = store.accepted_records("stage_spec", cut)
        stage_specs = _latest_by(stage_specs_all, lambda row: str(row["body"].get("stage_key") or ""))
        if not stage_specs:
            raise ValidationError("STOP_REQUIRED_STAGE_SET_MISSING")

        required_keys = {"E1", "E2", "E3", "E4", "E5"}
        if evaluation_context == "POST_E6":
            required_keys.add("E6")
        required_specs = tuple(row for row in stage_specs if row["body"].get("stage_key") in required_keys)
        present_keys = {row["body"].get("stage_key") for row in required_specs}
        missing_spec_keys = sorted(required_keys - present_keys)
        if missing_spec_keys:
            raise ValidationError("STOP_REQUIRED_STAGE_SET_MISSING", ",".join(missing_spec_keys))

        required_stage_spec_refs = [dict(row["ref"], ref_class="HISTORY_CONTEXT_BINDING") for row in required_specs]
        spec_key_by_digest = {
            row["ref"]["revision_digest"]: row["body"].get("stage_key") for row in required_specs
        }

        # Current completion per required stage, bound to the exact selected spec revision.
        completions = store.accepted_records("stage_completion", cut)
        current_completions: dict[str, dict[str, Any]] = {}
        for row in completions:
            body = row["body"]
            if body.get("completion_predicate_result") != "STAGE_COMPLETED":
                continue
            spec_ref = body.get("stage_spec_ref")
            if not isinstance(spec_ref, dict):
                continue
            stage_key = spec_key_by_digest.get(spec_ref.get("revision_digest"))
            if not stage_key:
                continue
            prior = current_completions.get(stage_key)
            if prior is None or int(row["accepted_seq"]) > int(prior["accepted_seq"]):
                current_completions[stage_key] = row

        completed_stage_refs = [current_completions[key]["ref"] for key in sorted(current_completions)]
        pending_required_stage_refs = [
            dict(row["ref"], ref_class="HISTORY_CONTEXT_BINDING")
            for row in required_specs
            if row["body"].get("stage_key") not in current_completions
        ]

        # Current inventory is acceptance-time latest; absence is not replaced by a zero digest.
        inv_record = _latest(store.accepted_records("inventory_revision", cut))
        if inv_record is None:
            raise ValidationError("STOP_INVENTORY_REQUIRED")
        inv_ref = inv_record["ref"]

        # Current mandatory obligation revision per logical obligation id.
        obligation_rows = _latest_by(
            store.accepted_records("coverage_obligation", cut),
            lambda row: str(row["body"].get("obligation_id") or row["ref"]["revision_digest"]),
        )
        mandatory_obligation_refs = [row["ref"] for row in obligation_rows]
        mandatory_digests = {ref["revision_digest"] for ref in mandatory_obligation_refs}

        # Latest accepted qualification for each exact mandatory obligation revision.
        latest_qual_by_obligation: dict[str, dict[str, Any]] = {}
        for row in store.accepted_records("coverage_obligation_qualification", cut):
            target = row["body"].get("obligation_revision_ref")
            target_digest = target.get("revision_digest") if isinstance(target, dict) else None
            if target_digest not in mandatory_digests:
                continue
            prior = latest_qual_by_obligation.get(target_digest)
            if prior is None or int(row["accepted_seq"]) > int(prior["accepted_seq"]):
                latest_qual_by_obligation[target_digest] = row
        qualification_rows = tuple(latest_qual_by_obligation[d] for d in sorted(latest_qual_by_obligation))
        current_qualification_refs = [row["ref"] for row in qualification_rows]

        qualification_summary = {
            "unqualified_mandatory_obligations_count": len(mandatory_digests - set(latest_qual_by_obligation)),
            "blocked_qualification_count": 0,
            "stale_qualification_count": 0,
            "in_progress_qualification_count": 0,
            "inconclusive_qualification_count": 0,
            "violation_confirmed_count": 0,
        }
        for row in qualification_rows:
            body = row["body"]
            status = body.get("qualification_status")
            outcome = body.get("substantive_outcome")
            if status != "QUALIFIED":
                qualification_summary["unqualified_mandatory_obligations_count"] += 1
            if status == "BLOCKED":
                qualification_summary["blocked_qualification_count"] += 1
            elif status == "STALE":
                qualification_summary["stale_qualification_count"] += 1
            elif status in {"UNASSESSED", "IN_PROGRESS"}:
                qualification_summary["in_progress_qualification_count"] += 1
            if outcome == "INCONCLUSIVE":
                qualification_summary["inconclusive_qualification_count"] += 1
            elif outcome == "VIOLATION_CONFIRMED":
                qualification_summary["violation_confirmed_count"] += 1

        # Open contradiction set: current logical revision whose status is not resolved.
        contradiction_rows = _latest_by(
            store.accepted_records("contradiction_revision", cut),
            lambda row: str(row["body"].get("contradiction_id") or row["ref"]["revision_digest"]),
        )
        resolved_statuses = {"RESOLVED", "RESOLVED_SCOPED", "RESOLVED_FULL"}
        contradiction_refs = [
            row["ref"] for row in contradiction_rows if row["body"].get("status") not in resolved_statuses
        ]

        # Accepted invalidations are conservative blockers until a later canonical
        # remediation contract explicitly supersedes them.
        invalidation_records = store.accepted_records("evidence_invalidation", cut)

        # Current candidate is selected by accepted_seq, never digest order.
        candidate_record = _latest(store.accepted_records("candidate_assurance_case", cut))
        if candidate_assurance_case_ref is None and candidate_record is not None:
            candidate_assurance_case_ref = candidate_record["ref"]
        candidate_digest = (
            candidate_assurance_case_ref.get("revision_digest")
            if isinstance(candidate_assurance_case_ref, dict)
            else None
        )

        # Baseline challenger pair must bind the exact current candidate and an
        # accepted assignment of the corresponding role.
        challenger_summary = {
            "challenger_blocked_count": 0,
            "challenger_inconclusive_count": 0,
            "challenger_material_counterevidence_count": 0,
        }
        if not challenger_refs and candidate_digest:
            assignments = {
                row["ref"]["revision_digest"]: row
                for row in store.accepted_records("challenger_assignment", cut)
                if row["body"].get("candidate_assurance_case_ref", {}).get("revision_digest") == candidate_digest
            }
            latest_result_by_role: dict[str, dict[str, Any]] = {}
            for row in store.accepted_records("challenger_result", cut):
                body = row["body"]
                if body.get("candidate_assurance_case_ref", {}).get("revision_digest") != candidate_digest:
                    continue
                assignment_digest = body.get("challenge_assignment_ref", {}).get("revision_digest")
                assignment = assignments.get(assignment_digest)
                if assignment is None:
                    continue
                role = assignment["body"].get("challenger_type")
                if role not in {"FALSE_POSITIVE_SKEPTIC", "FALSE_NEGATIVE_HUNTER"}:
                    continue
                prior = latest_result_by_role.get(role)
                if prior is None or int(row["accepted_seq"]) > int(prior["accepted_seq"]):
                    latest_result_by_role[role] = row
            challenger_refs = [latest_result_by_role[role]["ref"] for role in sorted(latest_result_by_role)]
            for row in latest_result_by_role.values():
                status = row["body"].get("status")
                if status == "BLOCKED":
                    challenger_summary["challenger_blocked_count"] += 1
                elif status == "INCONCLUSIVE":
                    challenger_summary["challenger_inconclusive_count"] += 1
                elif status == "MATERIAL_COUNTEREVIDENCE_FOUND":
                    challenger_summary["challenger_material_counterevidence_count"] += 1

        # Scope denominator from accepted inventory/scope state, not caller optimism.
        unresolved_scope_digests = {
            ref.get("revision_digest")
            for ref in inv_record["body"].get("unresolved_scope_refs", ())
            if isinstance(ref, dict) and ref.get("revision_digest")
        }
        latest_scope_rows = _latest_by(
            store.accepted_records("scope_state_record", cut),
            lambda row: str(row["body"].get("scope_key") or row["ref"]["revision_digest"]),
        )
        unknown_states = {"UNKNOWN_SCOPE", "PROVISIONAL_SCOPE", "KNOWN_UNOBSERVED_SCOPE"}
        blocked_states = {"UNSUPPORTED_SCOPE", "COLLECTION_FAILED", "PARSING_FAILED"}
        unknown_scope_keys = {
            row["body"].get("scope_key") for row in latest_scope_rows if row["body"].get("state") in unknown_states
        }
        blocked_scope_count = sum(1 for row in latest_scope_rows if row["body"].get("state") in blocked_states)

        derived_summary: dict[str, Any] = {
            "unknown_surfaces_count": max(len(unresolved_scope_digests), len(unknown_scope_keys)),
            "is_blocked": blocked_scope_count > 0,
            "blocked_scope_count": blocked_scope_count,
            "unresolved_obligations_count": qualification_summary["unqualified_mandatory_obligations_count"],
            **qualification_summary,
            **challenger_summary,
        }
        # Explicit caller information may only make the result more conservative.
        if unknown_blocked_summary:
            for key, value in unknown_blocked_summary.items():
                if isinstance(value, bool):
                    derived_summary[key] = bool(derived_summary.get(key, False) or value)
                elif isinstance(value, int) and not isinstance(value, bool):
                    derived_summary[key] = max(int(derived_summary.get(key, 0)), value)
                elif key not in derived_summary:
                    derived_summary[key] = value

        # Context refs bind exact effective pins from the accepted cut, never fixed digests.
        policy_token = str(cut["governing_policy_ref"])
        governing_policy_ref = _history_context_ref("policy_revision", policy_token)
        spec_tokens = tuple(str(value) for value in cut.get("governing_spec_refs", ()))
        if not spec_tokens:
            raise ValidationError("STOP_GOVERNING_SPEC_REQUIRED")
        policy_spec_refs = [_history_context_ref("spec_revision", token) for token in spec_tokens]
        evaluator_revision_ref = policy_spec_refs[0]

        required_stage_set_ref = _derived_profile_ref(
            "required-stage-set",
            [ref["revision_digest"] for ref in required_stage_spec_refs],
        )
        effort_profile_ref = _derived_profile_ref(
            "effort-profile",
            {"input_history_cut": cut, "completed_stage_refs": completed_stage_refs},
        )
        effort_results_ref = _derived_registered_ref(
            "effort-results",
            {"input_history_cut": cut, "completed_stage_refs": completed_stage_refs},
        )

        # Snapshot is a derived aid. Its inputs are exact refs from this builder.
        from .models import Snapshot
        direct_refs = [
            sg_ref,
            inv_ref,
            *mandatory_obligation_refs,
            *current_qualification_refs,
            *completed_stage_refs,
            *required_stage_spec_refs,
        ]
        snapshot = Snapshot(
            snapshot_type="STOP_INPUT_STATE_CAPTURE",
            as_of_head=cut,
            projection_code_revision="BDB_V2_SNAPSHOT_PROJECTION_2",
            projection_input_refs=direct_refs,
            snapshot_artifact_ref=_derived_registered_ref(
                "stop-input-snapshot",
                {"input_history_cut": cut, "projection_input_refs": direct_refs},
            ),
        )
        snapshot_obj = snapshot.as_object()

        stop_input = StopInput(
            campaign_id=head.campaign_id,
            source_generation_ref=sg_ref,
            input_history_cut=cut,
            evaluation_context=evaluation_context,
            governing_policy_ref=governing_policy_ref,
            policy_spec_refs=policy_spec_refs,
            evaluator_revision_ref=evaluator_revision_ref,
            required_stage_set_ref=required_stage_set_ref,
            required_stage_spec_refs=required_stage_spec_refs,
            completed_stage_refs=completed_stage_refs,
            pending_required_stage_refs=pending_required_stage_refs,
            stop_input_snapshot_ref=snapshot.ref,
            inventory_revision_ref=inv_ref,
            mandatory_obligation_refs=mandatory_obligation_refs,
            current_obligation_qualification_refs=current_qualification_refs,
            evidence_invalidation_refs=[row["ref"] for row in invalidation_records],
            contradiction_refs=contradiction_refs,
            residual_risk_refs=(),
            evidence_invalidation_state={"invalidated_count": len(invalidation_records)},
            release_policy_ref=governing_policy_ref,
            effort_profile_ref=effort_profile_ref,
            effort_results_ref=effort_results_ref,
            unknown_blocked_summary=derived_summary,
            candidate_assurance_case_ref=candidate_assurance_case_ref,
            challenger_refs=challenger_refs,
        )
        object.__setattr__(stop_input, "_snapshot_obj", snapshot_obj)
        return stop_input

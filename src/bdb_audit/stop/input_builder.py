"""Deterministic StopInput Builder from Verified Accepted History (B02 / §103).

STOP input is projected only from canonical accepted history. Fixed placeholder
identities, digest-order "latest" selection, stale candidate/challenger reuse,
and object-table presence without accepted membership are not authority.
"""
from __future__ import annotations

import hashlib
from typing import Any, Iterable, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.registry import canonical_reference_set
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
    rows = tuple(records)
    return max(rows, key=lambda row: int(row.get("accepted_seq", 0))) if rows else None


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
    text = str(value)
    if len(text) == 64 and all(ch in "0123456789abcdef" for ch in text.lower()):
        return text.lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _history_context_ref(kind: str, effective_token: str) -> dict[str, Any]:
    return _ref(kind, _identity_digest(effective_token), "HISTORY_CONTEXT_BINDING")


def _derived_profile_ref(label: str, payload: Any) -> dict[str, Any]:
    digest = hashlib.sha256(label.encode("utf-8") + b"\0" + canonical_bytes(payload)).hexdigest()
    return _ref("external_profile_ref", digest, "HISTORY_CONTEXT_BINDING", schema_ref="BDB_TARGET/external_profile_ref")


def _derived_registered_ref(label: str, payload: Any) -> dict[str, Any]:
    digest = hashlib.sha256(label.encode("utf-8") + b"\0" + canonical_bytes(payload)).hexdigest()
    return _ref("registered_immutable_object", digest, "CONTENT_OR_PRIOR", schema_ref="BDB_TARGET/registered_immutable_object")


def _digest_set(refs: Sequence[dict[str, Any]]) -> set[str]:
    return {
        ref.get("revision_digest")
        for ref in refs
        if isinstance(ref, dict) and isinstance(ref.get("revision_digest"), str)
    }


class StopInputBuilder:
    """Extract one exact reproducible STOP snapshot from one accepted cut."""

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
        del e6_plan_approved  # Plan approval affects StopEvaluation, never the immutable input projection.
        from ..workflow.read_models import campaign_source_identity, current_accepted_cut

        head = store.head()
        if head is None:
            raise ValidationError("EMPTY_STORE", "Cannot build StopInput on empty store")
        cut = current_accepted_cut(store)

        source_projection = campaign_source_identity(store, cut)
        sg_ref = dict(source_projection["source_generation_ref"], ref_class="CONTENT_OR_PRIOR")
        store.resolve_accepted(sg_ref, cut)

        # One current StageSpec revision per stage key, selected by accepted_seq.
        stage_specs = _latest_by(
            store.accepted_records("stage_spec", cut),
            lambda row: str(row["body"].get("stage_key") or ""),
        )
        required_keys = {"E1", "E2", "E3", "E4", "E5"}
        if evaluation_context == "POST_E6":
            required_keys.add("E6")
        required_specs = tuple(row for row in stage_specs if row["body"].get("stage_key") in required_keys)
        present_keys = {row["body"].get("stage_key") for row in required_specs}
        missing_keys = sorted(required_keys - present_keys)

        # Missing required stage specs are STOP state, not a builder exception.
        # The final evaluator treats this count as required work still pending;
        # no fabricated StageSpec digest is introduced to fill the gap.
        required_stage_spec_refs = canonical_reference_set([
            dict(row["ref"], ref_class="HISTORY_CONTEXT_BINDING") for row in required_specs
        ])
        spec_key_by_digest = {row["ref"]["revision_digest"]: row["body"]["stage_key"] for row in required_specs}

        current_completions: dict[str, dict[str, Any]] = {}
        for row in store.accepted_records("stage_completion", cut):
            body = row["body"]
            if body.get("completion_predicate_result") != "STAGE_COMPLETED":
                continue
            spec_ref = body.get("stage_spec_ref")
            stage_key = spec_key_by_digest.get(spec_ref.get("revision_digest")) if isinstance(spec_ref, dict) else None
            if not stage_key:
                continue
            prior = current_completions.get(stage_key)
            if prior is None or int(row["accepted_seq"]) > int(prior["accepted_seq"]):
                current_completions[stage_key] = row
        completed_stage_refs = canonical_reference_set([
            current_completions[key]["ref"] for key in sorted(current_completions)
        ])
        pending_required_stage_refs = canonical_reference_set([
            dict(row["ref"], ref_class="HISTORY_CONTEXT_BINDING")
            for row in required_specs
            if row["body"]["stage_key"] not in current_completions
        ])

        inv_record = _latest(store.accepted_records("inventory_revision", cut))
        if inv_record is None:
            raise ValidationError("STOP_INVENTORY_REQUIRED")
        inv_ref = inv_record["ref"]

        # Current mandatory revision per logical obligation.
        obligation_rows = _latest_by(
            store.accepted_records("coverage_obligation", cut),
            lambda row: str(row["body"].get("obligation_id") or row["ref"]["revision_digest"]),
        )
        mandatory_obligation_refs = [row["ref"] for row in obligation_rows]
        mandatory_digests = _digest_set(mandatory_obligation_refs)

        # Exact latest qualification per exact obligation revision.
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

        qualification_summary: dict[str, Any] = {
            "qualification_binding_verified": set(latest_qual_by_obligation) == mandatory_digests,
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
                qualification_summary["qualification_binding_verified"] = False
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

        # Only current unresolved contradiction revisions enter STOP.
        contradiction_rows = _latest_by(
            store.accepted_records("contradiction_revision", cut),
            lambda row: str(row["body"].get("contradiction_id") or row["ref"]["revision_digest"]),
        )
        resolved_statuses = {"RESOLVED", "RESOLVED_SCOPED", "RESOLVED_FULL"}
        contradiction_refs = [row["ref"] for row in contradiction_rows if row["body"].get("status") not in resolved_statuses]
        invalidation_records = store.accepted_records("evidence_invalidation", cut)

        # Current CandidateAssuranceCase is acceptance-time latest. A supplied ref
        # is only an assertion to verify, never an override.
        candidate_record = _latest(
            store.accepted_records(
                "candidate_assurance_case", cut
            )
        )
        accepted_candidate_ref = (
            candidate_record["ref"]
            if candidate_record is not None
            else None
        )
        if candidate_assurance_case_ref is not None:
            supplied = candidate_assurance_case_ref.get(
                "revision_digest"
            )
            accepted = (
                accepted_candidate_ref.get("revision_digest")
                if accepted_candidate_ref
                else None
            )
            if supplied != accepted:
                raise ValidationError(
                    "STOP_CANDIDATE_BINDING_MISMATCH"
                )

        if candidate_record is not None:
            candidate_body = candidate_record["body"]
            candidate_cut = candidate_body.get(
                "candidate_input_history_cut"
            )
            if not isinstance(candidate_cut, dict):
                raise ValidationError(
                    "STOP_CANDIDATE_HISTORY_CUT_REQUIRED"
                )

            finding_refs = [
                ref
                for ref in candidate_body.get(
                    "finding_claim_revision_refs", ()
                )
                if isinstance(ref, dict)
            ]
            adjudication_refs = [
                ref
                for ref in candidate_body.get(
                    "finding_adjudication_refs", ()
                )
                if isinstance(ref, dict)
            ]
            finding_digests = _digest_set(finding_refs)
            if len(finding_digests) != len(finding_refs):
                raise ValidationError(
                    "STOP_CANDIDATE_FINDING_SET_INVALID"
                )

            candidate_adjudication_by_claim: dict[
                str, dict[str, Any]
            ] = {}
            for ref in adjudication_refs:
                row = store.resolve_accepted(
                    ref, candidate_cut
                )
                target = row["body"].get(
                    "claim_revision_ref", {}
                )
                target_digest = (
                    target.get("revision_digest")
                    if isinstance(target, dict)
                    else None
                )
                if (
                    not isinstance(target_digest, str)
                    or target_digest not in finding_digests
                    or target_digest
                    in candidate_adjudication_by_claim
                ):
                    raise ValidationError(
                        "STOP_CANDIDATE_FINDING_ADJUDICATION_MISMATCH"
                    )
                candidate_adjudication_by_claim[
                    target_digest
                ] = row

            if set(
                candidate_adjudication_by_claim
            ) != finding_digests:
                raise ValidationError(
                    "STOP_CANDIDATE_FINDING_ADJUDICATION_MISMATCH"
                )

            # The candidate must pin the latest applicable adjudication
            # for every included exact claim on its own frozen input cut.
            latest_by_claim: dict[str, dict[str, Any]] = {}
            for row in store.accepted_records(
                "finding_adjudication_decision",
                candidate_cut,
            ):
                target = row["body"].get(
                    "claim_revision_ref", {}
                )
                target_digest = (
                    target.get("revision_digest")
                    if isinstance(target, dict)
                    else None
                )
                if target_digest not in finding_digests:
                    continue
                prior = latest_by_claim.get(
                    str(target_digest)
                )
                if (
                    prior is None
                    or int(row["accepted_seq"])
                    > int(prior["accepted_seq"])
                ):
                    latest_by_claim[
                        str(target_digest)
                    ] = row

            for digest in finding_digests:
                pinned = candidate_adjudication_by_claim[
                    digest
                ]
                latest = latest_by_claim.get(digest)
                if (
                    latest is None
                    or pinned["ref"]["revision_digest"]
                    != latest["ref"]["revision_digest"]
                ):
                    raise ValidationError(
                        "STOP_CANDIDATE_STALE_FINDING_ADJUDICATION",
                        digest,
                    )

        candidate_assurance_case_ref = (
            accepted_candidate_ref
        )
        candidate_digest = (
            accepted_candidate_ref.get("revision_digest")
            if accepted_candidate_ref
            else None
        )

        roles = {"FALSE_POSITIVE_SKEPTIC", "FALSE_NEGATIVE_HUNTER"}
        latest_result_by_role: dict[str, dict[str, Any]] = {}
        if candidate_digest:
            assignments = {
                row["ref"]["revision_digest"]: row
                for row in store.accepted_records("challenger_assignment", cut)
                if row["body"].get("candidate_assurance_case_ref", {}).get("revision_digest") == candidate_digest
            }
            for row in store.accepted_records("challenger_result", cut):
                body = row["body"]
                if body.get("candidate_assurance_case_ref", {}).get("revision_digest") != candidate_digest:
                    continue
                assignment = assignments.get(body.get("challenge_assignment_ref", {}).get("revision_digest"))
                if assignment is None:
                    continue
                role = assignment["body"].get("challenger_type")
                if role not in roles:
                    continue
                prior = latest_result_by_role.get(role)
                if prior is None or int(row["accepted_seq"]) > int(prior["accepted_seq"]):
                    latest_result_by_role[role] = row
        derived_challenger_refs = [latest_result_by_role[role]["ref"] for role in sorted(latest_result_by_role)]
        if challenger_refs and _digest_set(challenger_refs) != _digest_set(derived_challenger_refs):
            raise ValidationError("STOP_CHALLENGER_BINDING_MISMATCH")
        challenger_refs = derived_challenger_refs

        challenger_summary: dict[str, Any] = {
            "challenger_binding_verified": set(latest_result_by_role) == roles,
            "challenger_blocked_count": 0,
            "challenger_inconclusive_count": 0,
            "challenger_material_counterevidence_count": 0,
        }
        for row in latest_result_by_role.values():
            status = row["body"].get("status")
            if status == "BLOCKED":
                challenger_summary["challenger_blocked_count"] += 1
            elif status == "INCONCLUSIVE":
                challenger_summary["challenger_inconclusive_count"] += 1
            elif status == "MATERIAL_COUNTEREVIDENCE_FOUND":
                challenger_summary["challenger_material_counterevidence_count"] += 1

        # Scope denominator from accepted inventory + current scope states.
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
            "missing_required_stage_specs_count": len(missing_keys),
            "unresolved_obligations_count": qualification_summary["unqualified_mandatory_obligations_count"],
            **qualification_summary,
            **challenger_summary,
        }

        # Caller input may only add conservative scope/data blockers. Derived
        # qualification/challenger/stage proof is immutable and cannot be
        # overwritten by the request that asks for STOP evaluation.
        if unknown_blocked_summary:
            conservative_bool_fields = {"is_blocked", "insufficient_data", "has_unknown_scope"}
            conservative_count_fields = {"unknown_surfaces_count"}
            for key, value in unknown_blocked_summary.items():
                if key in conservative_bool_fields:
                    derived_summary[key] = bool(derived_summary.get(key, False) or bool(value))
                elif key in conservative_count_fields:
                    if type(value) is not int or value < 0:
                        raise ValidationError("STOP_UNKNOWN_SUMMARY_INVALID", key)
                    derived_summary[key] = max(int(derived_summary.get(key, 0)), value)
                elif key in derived_summary:
                    if value != derived_summary[key]:
                        raise ValidationError("STOP_DERIVED_SUMMARY_OVERRIDE_FORBIDDEN", key)
                else:
                    derived_summary[key] = value

        policy_token = str(cut["governing_policy_ref"])
        governing_policy_ref = _history_context_ref("policy_revision", policy_token)
        spec_tokens = tuple(str(value) for value in cut.get("governing_spec_refs", ()))
        if not spec_tokens:
            raise ValidationError("STOP_GOVERNING_SPEC_REQUIRED")
        policy_spec_refs = [_history_context_ref("spec_revision", token) for token in spec_tokens]
        evaluator_revision_ref = policy_spec_refs[0]
        required_stage_set_ref = _derived_profile_ref(
            "required-stage-set",
            {
                "required_stage_keys": sorted(required_keys),
                "accepted_stage_spec_digests": [ref["revision_digest"] for ref in required_stage_spec_refs],
                "missing_stage_keys": missing_keys,
            },
        )
        effort_profile_ref = _derived_profile_ref("effort-profile", {"input_history_cut": cut, "completed_stage_refs": completed_stage_refs})
        effort_results_ref = _derived_registered_ref("effort-results", {"input_history_cut": cut, "completed_stage_refs": completed_stage_refs})

        from .models import Snapshot
        direct_refs = [sg_ref, inv_ref, *mandatory_obligation_refs, *current_qualification_refs, *completed_stage_refs, *required_stage_spec_refs]
        snapshot = Snapshot(
            snapshot_type="STOP_INPUT_STATE_CAPTURE",
            as_of_head=cut,
            projection_code_revision="BDB_V2_SNAPSHOT_PROJECTION_2",
            projection_input_refs=direct_refs,
            snapshot_artifact_ref=_derived_registered_ref("stop-input-snapshot", {"input_history_cut": cut, "projection_input_refs": direct_refs}),
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

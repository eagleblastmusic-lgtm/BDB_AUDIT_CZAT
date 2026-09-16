"""M42/M44 residual-risk binding across finalization boundaries.

A STOP verdict may be materialized into conclusion/release only when its exact
residual-risk set is still current.  Accepted residual risks are propagated
unchanged through CampaignConclusion, FinalAssuranceCase and
ReleaseQualification; post-STOP risk drift requires a fresh STOP evaluation.
"""
from __future__ import annotations

import hashlib
from functools import wraps
from typing import Any

from ..core.errors import ValidationError
from ..core.ids import new_id
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject
from ..workflow.read_models import current_accepted_cut
from ..stop.residual_risk_projection import _current_risk_rows
from .conclusion import CampaignConclusion, FinalAssuranceCase
from .release import ReleaseQualification


def _digest_set(refs) -> set[str]:
    return {
        ref.get("revision_digest")
        for ref in refs
        if isinstance(ref, dict) and isinstance(ref.get("revision_digest"), str)
    }


def _prior_risk_refs(refs) -> tuple[dict[str, Any], ...]:
    return tuple(
        canonical_reference_set(
            [dict(ref, ref_class="PRIOR_ACCEPTED_ONLY") for ref in refs]
        )
    )


def _stop_and_risks(service, termination_state):
    cut = current_accepted_cut(service.store)
    stop_eval_record = service._latest(service.store.accepted_records("stop_evaluation", cut))
    if stop_eval_record is None:
        if termination_state == "COMPLETED":
            raise ValidationError(
                "STOP_EVALUATION_REQUIRED",
                "Cannot conclude campaign without prior accepted stop_evaluation",
            )
        service.evaluate_stop_gate(evaluation_context="FINAL_POST_E5")
        cut = current_accepted_cut(service.store)
        stop_eval_record = service._latest(service.store.accepted_records("stop_evaluation", cut))
        if stop_eval_record is None:
            raise ValidationError("STOP_EVALUATION_REQUIRED")

    stop_input_ref = stop_eval_record["body"].get("stop_input_ref")
    if not isinstance(stop_input_ref, dict):
        raise ValidationError("FINALIZATION_STOP_INPUT_REQUIRED")
    stop_input_record = service.store.resolve_accepted(stop_input_ref, cut)
    stop_risk_refs = tuple(stop_input_record["body"].get("residual_risk_refs", ()))
    stop_release_policy_ref = stop_input_record["body"].get("release_policy_ref")
    if not isinstance(stop_release_policy_ref, dict):
        raise ValidationError(
            "RELEASE_POLICY_CONTEXT_REQUIRED",
            "Accepted StopInput must carry release_policy_ref",
        )

    current_rows = _current_risk_rows(service.store, cut)
    current_risk_refs = tuple(row["ref"] for row in current_rows)
    if _digest_set(stop_risk_refs) != _digest_set(current_risk_refs):
        raise ValidationError(
            "RESIDUAL_RISK_DRIFT_AFTER_STOP",
            "Residual-risk authority changed after STOP; a fresh STOP evaluation is required",
        )
    return cut, stop_eval_record, _prior_risk_refs(stop_risk_refs), stop_release_policy_ref


def _conclude_with_residual_risk(
    service,
    *,
    termination_state: str | None,
    bounded_statement: str,
    cut: dict[str, Any],
    stop_eval_record: dict[str, Any],
    residual_risk_refs: tuple[dict[str, Any], ...],
    stop_release_policy_ref: dict[str, Any],
) -> dict[str, Any]:
    stop_eval_body = stop_eval_record["body"]
    stop_eval_ref = dict(stop_eval_record["ref"], ref_class="PRIOR_ACCEPTED_ONLY")
    stop_digest = stop_eval_ref["revision_digest"]
    decision = stop_eval_body.get("continuation_decision")
    assurance = stop_eval_body.get("assurance_level")
    readiness = stop_eval_body.get("release_readiness")

    if termination_state is None:
        termination_state = (
            "COMPLETED"
            if decision == "PASS" and assurance == "ADEQUATE_FOR_DECLARED_SCOPE"
            else "COMPLETED_LIMITED"
        )
    if termination_state == "COMPLETED":
        if decision != "PASS":
            raise ValidationError("COMPLETED_REQUIRES_STOP_PASS")
        if assurance != "ADEQUATE_FOR_DECLARED_SCOPE":
            raise ValidationError("COMPLETED_REQUIRES_ADEQUATE_ASSURANCE")
        if residual_risk_refs and readiness != "READY_WITH_RESIDUAL_RISK":
            raise ValidationError("RESIDUAL_RISK_RELEASE_READINESS_MISMATCH")

    head = service.store.head()
    if head is None:
        raise ValidationError("EMPTY_STORE")
    camp_ref = {
        "kind": "campaign_ref",
        "revision_digest": hashlib.sha256(head.campaign_id.encode("utf-8")).hexdigest(),
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_TARGET/campaign_ref",
        "ref_class": "PRIOR_ACCEPTED_ONLY",
    }
    sg_record = service._latest(service.store.accepted_records("source_generation", cut))
    if sg_record is None:
        si_record = service._latest(service.store.accepted_records("source_identity", cut))
        if si_record is None:
            raise ValidationError("SOURCE_GENERATION_REQUIRED")
        sg_ref = dict(si_record["ref"], ref_class="PRIOR_ACCEPTED_ONLY")
    else:
        sg_ref = dict(sg_record["ref"], ref_class="PRIOR_ACCEPTED_ONLY")

    cac_record = service._latest(service.store.accepted_records("candidate_assurance_case", cut))
    cac_ref = dict(cac_record["ref"], ref_class="PRIOR_ACCEPTED_ONLY") if cac_record else None
    basis_refs: tuple[dict[str, Any], ...] = ()
    if termination_state == "COMPLETED_LIMITED":
        basis_refs = (stop_eval_ref,)

    # Boundary 1: conclusion consumes only prior accepted STOP + risks.
    existing_conclusion = service._matching_record(
        "campaign_conclusion",
        cut,
        lambda body: body.get("stop_evaluation_ref", {}).get("revision_digest") == stop_digest,
    )
    if existing_conclusion is not None:
        body = existing_conclusion["body"]
        if (
            body.get("termination_state") != termination_state
            or body.get("bounded_conclusion_statement") != bounded_statement
            or _digest_set(body.get("residual_risk_refs", ())) != _digest_set(residual_risk_refs)
        ):
            raise ValidationError("FINALIZATION_REPLAY_CONFLICT")
        concl_ref = dict(existing_conclusion["ref"], ref_class="PRIOR_ACCEPTED_ONLY")
        concl_digest = concl_ref["revision_digest"]
        conclusion_commit_seq = int(existing_conclusion["accepted_seq"])
    else:
        conclusion = CampaignConclusion(
            campaign_conclusion_id=new_id("campaign_conclusion"),
            campaign_ref=camp_ref,
            source_generation_ref=sg_ref,
            stop_evaluation_ref=stop_eval_ref,
            termination_state=termination_state,
            assurance_level=assurance,
            bounded_conclusion_statement=bounded_statement,
            conclusion_command_input_history_cut=cut,
            residual_risk_refs=residual_risk_refs,
            candidate_assurance_case_ref=cac_ref,
            limited_conclusion_basis_refs=basis_refs,
        )
        concl_obj = CanonicalObject(
            "campaign_conclusion", conclusion.body(), logical_id=conclusion.campaign_conclusion_id
        )
        conclusion_res = service._accept_one(concl_obj, "campaign_conclusion")
        concl_ref = dict(concl_obj.as_ref().as_dict(), ref_class="PRIOR_ACCEPTED_ONLY")
        concl_digest = concl_obj.digest
        conclusion_commit_seq = conclusion_res.head.commit_seq

    # Boundary 2: refresh; FinalAssuranceCase binds exact same risk set.
    final_case_cut = current_accepted_cut(service.store)
    existing_final = service._matching_record(
        "final_assurance_case",
        final_case_cut,
        lambda body: (
            body.get("campaign_conclusion_ref", {}).get("revision_digest") == concl_digest
            and body.get("stop_evaluation_ref", {}).get("revision_digest") == stop_digest
        ),
    )
    stmt_ref = {
        "kind": "public_conclusion_statement_ref",
        "revision_digest": hashlib.sha256(bounded_statement.encode("utf-8")).hexdigest(),
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": "BDB_TARGET/public_conclusion_statement_ref",
        "ref_class": "PRIOR_ACCEPTED_ONLY",
    }
    if existing_final is not None:
        body = existing_final["body"]
        if (
            body.get("public_conclusion_statement_ref", {}).get("revision_digest")
            != stmt_ref["revision_digest"]
            or _digest_set(body.get("residual_risk_refs", ())) != _digest_set(residual_risk_refs)
        ):
            raise ValidationError("FINALIZATION_REPLAY_CONFLICT")
        final_ref = dict(existing_final["ref"], ref_class="PRIOR_ACCEPTED_ONLY")
        final_digest = final_ref["revision_digest"]
        final_case_commit_seq = int(existing_final["accepted_seq"])
    else:
        final_case = FinalAssuranceCase(
            final_assurance_case_id=new_id("final_assurance_case"),
            campaign_conclusion_ref=concl_ref,
            stop_evaluation_ref=stop_eval_ref,
            public_conclusion_statement_ref=stmt_ref,
            final_case_input_history_cut=final_case_cut,
            residual_risk_refs=residual_risk_refs,
            candidate_assurance_case_ref=cac_ref,
            limited_conclusion_basis_refs=basis_refs,
        )
        final_obj = CanonicalObject(
            "final_assurance_case", final_case.body(), logical_id=final_case.final_assurance_case_id
        )
        final_res = service._accept_one(final_obj, "final_assurance_case")
        final_ref = dict(final_obj.as_ref().as_dict(), ref_class="PRIOR_ACCEPTED_ONLY")
        final_digest = final_obj.digest
        final_case_commit_seq = final_res.head.commit_seq

    # Boundary 3: refresh; release materialization exposes accepted risks and
    # must preserve the exact release-policy context frozen by STOP.
    qualification_cut = current_accepted_cut(service.store)
    qualification_policy_ref = service._policy_ref_from_cut(qualification_cut)
    if stop_release_policy_ref != qualification_policy_ref:
        raise ValidationError(
            "DRIFT_DETECTED_MATERIALIZATION_INVALID",
            "STOP_AXIS_MATERIALIZATION cannot cross a release-policy context change",
        )

    existing_qualification = service._matching_record(
        "release_qualification",
        qualification_cut,
        lambda body: (
            body.get("campaign_conclusion_ref", {}).get("revision_digest") == concl_digest
            and body.get("final_assurance_case_ref", {}).get("revision_digest") == final_digest
            and body.get("stop_evaluation_ref", {}).get("revision_digest") == stop_digest
            and body.get("assessment_basis") == "STOP_AXIS_MATERIALIZATION"
        ),
    )
    rel_result = readiness if termination_state == "COMPLETED" else "QUALIFICATION_BLOCKED"
    if existing_qualification is not None:
        body = existing_qualification["body"]
        if (
            body.get("result") != rel_result
            or _digest_set(body.get("accepted_residual_risk_refs", ()))
            != _digest_set(residual_risk_refs)
        ):
            raise ValidationError("FINALIZATION_REPLAY_CONFLICT")
        if body.get("release_policy_ref") != qualification_policy_ref:
            raise ValidationError(
                "RELEASE_POLICY_BINDING_MISMATCH",
                "Accepted release qualification does not bind the governing release policy",
            )
        rel_digest = existing_qualification["ref"]["revision_digest"]
        qualification_commit_seq = int(existing_qualification["accepted_seq"])
        final_head = service.store.head()
        assert final_head is not None
    else:
        rel_qual = ReleaseQualification(
            release_qualification_id=new_id("release_qualification"),
            campaign_conclusion_ref=concl_ref,
            final_assurance_case_ref=final_ref,
            stop_evaluation_ref=stop_eval_ref,
            source_generation_ref=sg_ref,
            release_policy_ref=qualification_policy_ref,
            release_assessment_basis_cut=qualification_cut,
            qualification_command_input_history_cut=qualification_cut,
            assessment_basis="STOP_AXIS_MATERIALIZATION",
            result=rel_result,
            accepted_residual_risk_refs=residual_risk_refs,
            reason_codes=("STOP_AXIS_MATERIALIZATION_QUALIFIED",),
        )
        rel_obj = CanonicalObject(
            "release_qualification", rel_qual.body(), logical_id=rel_qual.release_qualification_id
        )
        qualification_res = service._accept_one(rel_obj, "release_qualification")
        rel_digest = rel_obj.digest
        qualification_commit_seq = qualification_res.head.commit_seq
        final_head = qualification_res.head

    return {
        "status": "SUCCESS",
        "termination_state": termination_state,
        "assurance_level": assurance,
        "release_readiness": rel_result,
        "campaign_conclusion_digest": concl_digest,
        "final_assurance_case_digest": final_digest,
        "release_qualification_digest": rel_digest,
        "campaign_conclusion_commit_seq": conclusion_commit_seq,
        "final_assurance_case_commit_seq": final_case_commit_seq,
        "release_qualification_commit_seq": qualification_commit_seq,
        "commit_seq": final_head.commit_seq,
        "commit_hash": final_head.commit_hash,
    }


def install_residual_risk_finalization(finalization_cls) -> None:
    """Patch only the residual-risk path; zero-risk finalization stays unchanged."""
    original = finalization_cls.conclude_campaign
    if getattr(original, "_bdb_residual_risk_finalization", False):
        return

    @wraps(original)
    def conclude_campaign(
        self,
        termination_state: str | None = None,
        bounded_statement: str = "Campaign concluded via post-E5 finalization",
    ):
        cut, stop_eval_record, risk_refs, stop_release_policy_ref = _stop_and_risks(
            self, termination_state
        )
        if not risk_refs:
            return original(self, termination_state, bounded_statement)
        return _conclude_with_residual_risk(
            self,
            termination_state=termination_state,
            bounded_statement=bounded_statement,
            cut=cut,
            stop_eval_record=stop_eval_record,
            residual_risk_refs=risk_refs,
            stop_release_policy_ref=stop_release_policy_ref,
        )

    setattr(conclude_campaign, "_bdb_residual_risk_finalization", True)
    setattr(finalization_cls, "conclude_campaign", conclude_campaign)


__all__ = ["install_residual_risk_finalization"]

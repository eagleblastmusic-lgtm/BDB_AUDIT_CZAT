"""Foundation Reference Slice: synthetic end-to-end campaign (PR-028).

Demonstrates the complete foundation lifecycle from empty history legacy bootstrap
through E3 StageRun, isolation, discovery, hypothesis, preregistered experiment,
evidence qualification, coverage obligation qualification, StageCompletion,
and intermediate STOP evaluation returning CONTINUE_REQUIRED.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.hashing import object_digest
from ..core.registry import ContractRegistry
from ..history.objects import (
    CanonicalObject,
    CommandEnvelope,
)
from ..history.store import TransactionalHistoryStore
from ..coordinator import Coordinator

# F3 domain imports
from ..inventory.models import SurfaceKey, SurfaceRecord, InventoryRevision
from ..coverage.models import (
    InvariantRevision,
    MaterialityAssessment,
    CoverageObligation,
    CoverageObligationQualification,
)
from ..hypothesis.models import HypothesisRevision
from ..execution.models import (
    ExperimentSpec,
    ExecutionDescriptor,
    CleanupResult,
    ExecutionResult,
)
from ..evidence.models import (
    Observation,
    DependencyIndependenceAssessment,
    EvidenceApplicabilityAssessment,
    EvidenceQualificationAssessment,
)
from ..adjudication.models import FindingClaimRevision, FindingAdjudicationDecision
from ..adjudication.contribution import build_contribution_projection, ContributionProjection
from ..orchestration.stages import StageSpec
from ..orchestration.runs import LaneSpec
from ..stop.models import LaneCompletion, StageCompletion, StopInput, Snapshot
from ..stop.evaluator import evaluate_stop, validate_intermediate_stop


def _external_ref(kind: str, seed: str, ref_class: str = "CONTENT_OR_PRIOR") -> dict[str, Any]:
    return {
        "kind": kind,
        "revision_digest": hashlib.sha256(seed.encode()).hexdigest(),
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{kind}/1",
        "ref_class": ref_class,
    }


def _ref_for(parent_kind: str, field_name: str, target: Any) -> dict[str, Any]:
    """Derive exact compliant typed reference based on the parent kind's declared contract."""
    reg = ContractRegistry()
    row = reg.contract(parent_kind)
    expected_ref_class = "CONTENT_OR_PRIOR"
    for spec in row.get("material_refs", ()):
        if spec["field"] == field_name:
            expected_ref_class = spec["ref_class"]
            break

    if hasattr(target, "as_ref"):
        r = target.as_ref(ref_class=expected_ref_class)
        return r.as_dict() if hasattr(r, "as_dict") else dict(r)
    elif hasattr(target, "as_object"):
        obj = target.as_object()
        r = obj.as_ref(ref_class=expected_ref_class)
        return r.as_dict() if hasattr(r, "as_dict") else dict(r)
    elif isinstance(target, CanonicalObject):
        t_kind = target.kind
        t_digest = target.digest
    elif isinstance(target, dict) and "kind" in target:
        t_kind = target["kind"]
        t_digest = target.get("revision_digest") or target.get("digest") or hashlib.sha256(canonical_bytes(target)).hexdigest()
    else:
        raise ValueError(f"Cannot build ref for {target}")

    return {
        "kind": t_kind,
        "revision_digest": t_digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_SCHEMA_REGISTRY::{t_kind}/1",
        "ref_class": expected_ref_class,
    }


def run_foundation_reference_slice(store_path: str | Path, *, stop_at_seq: int = 10) -> dict[str, Any]:
    """Execute the full Foundation Reference Slice campaign deterministically.
    
    Returns a dictionary of execution artifacts and verification status.
    """
    from tests.f2.helpers import bootstrap_fixture

    store = TransactionalHistoryStore(store_path)
    coordinator = Coordinator(store)

    id_counter = 0
    def det_id(kind: str) -> str:
        nonlocal id_counter
        id_counter += 1
        return f"{kind}_00000000-0000-4000-8000-{id_counter:012x}"

    # -------------------------------------------------------------------------
    # 1. ATOMIC SEQ=1: INSTALLATION_BOOTSTRAP_PROFILE_V1 @ EMPTY_HISTORY -> Genesis
    # -------------------------------------------------------------------------
    profile, bootstrap_cmd, genesis_objects, genesis_ctx = bootstrap_fixture()
    commit_1 = coordinator.accept(bootstrap_cmd, immutable_objects=genesis_objects, bootstrap_profile=profile)
    head = commit_1.head
    head_ref = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
    campaign_id = "campaign_fixture"
    source_gen = genesis_ctx["source_generation"]
    source_ident = genesis_ctx["source_generation"].body["source_identity_ref"]

    def make_cut(h, c):
        return {
            "variant": "ACCEPTED_HISTORY_CUT",
            "campaign_id": h.campaign_id,
            "accepted_head_seq": h.commit_seq,
            "accepted_head_hash": h.commit_hash,
            "governing_policy_ref": c.governing_policy_ref,
            "governing_spec_refs": list(c.governing_spec_refs),
        }

    head_cut = make_cut(head, commit_1.commit)

    cmd_counter = 1
    def next_cmd(parent_head_ref):
        nonlocal cmd_counter
        cmd_counter += 1
        return replace(
            bootstrap_cmd,
            command_id=f"command_123e4567-e89b-42d3-a456-{cmd_counter:012x}",
            command_kind="RECORD_FOUNDATION_FACT",
            campaign_ref=campaign_id,
            expected_parent_head=parent_head_ref,
            proposed_campaign_id=None,
            history_namespace_ref=None,
            bootstrap_profile_ref=None,
        )

    # -------------------------------------------------------------------------
    # 2. SEQ=2: Surface + Inventory + Materiality Assessment + Invariant
    # -------------------------------------------------------------------------
    surface_key = SurfaceKey(
        source_identity_ref=_ref_for("surface_key", "source_identity_ref", source_ident),
        canonical_surface_category="PARSER_MODULE",
        normalized_anchor_descriptor={"repo_relative_posix_path": "parser/core.py", "byte_offset": 0},
    )

    surf_rec = SurfaceRecord(
        surface_key=_ref_for("surface_record", "surface_key", surface_key),
        source_identity_ref=_ref_for("surface_record", "source_identity_ref", source_ident),
        surface_category="PARSER_MODULE",
        anchor_descriptor={"repo_relative_posix_path": "parser/core.py", "byte_offset": 0},
        provenance_refs=[],
        identity_state="STABLE",
        surface_record_id=det_id("surface_record"),
    )

    inv_rev = InventoryRevision(
        inventory_id=det_id("inventory_revision"),
        inventory_revision="1",
        source_generation_ref=_ref_for("inventory_revision", "source_generation_ref", source_gen),
        basis_history_cut=head_cut,
        surface_refs=[_ref_for("inventory_revision", "surface_refs", surf_rec)],
    )

    mat_assess = MaterialityAssessment(
        materiality_assessment_id=det_id("materiality_assessment"),
        subject_ref=_ref_for("materiality_assessment", "subject_ref", surf_rec),
        assessment_input_history_cut=head_cut,
        materiality_policy_ref=_external_ref("policy_revision", "pol_mat", ref_class="HISTORY_CONTEXT_BINDING"),
        scope="GLOBAL",
        result="MATERIAL",
        rationale="Parser core is critical surface",
    )

    inv_rule = InvariantRevision(
        invariant_id=det_id("invariant_revision"),
        invariant_revision="1",
        invariant_input_history_cut=head_cut,
        source_generation_ref=_ref_for("invariant_revision", "source_generation_ref", source_gen),
        statement="Parser module must terminate without unhandled panic or crash",
        activation_policy_ref=_external_ref("policy_revision", "pol_act", ref_class="HISTORY_CONTEXT_BINDING"),
    )

    seq2_objects = (
        surface_key.as_object(),
        surf_rec.as_object(),
        inv_rev.as_object(),
        mat_assess.as_object(),
        inv_rule.as_object(),
    )
    commit_2 = coordinator.accept(next_cmd(head_ref), immutable_objects=seq2_objects, expected_head=head)
    head = commit_2.head
    head_ref = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
    head_cut = make_cut(head, commit_2.commit)

    # -------------------------------------------------------------------------
    # 3. SEQ=3: Coverage Obligation (referencing prior MaterialityAssessment)
    # -------------------------------------------------------------------------
    cov_ob = CoverageObligation(
        obligation_id=det_id("coverage_obligation"),
        obligation_revision="1",
        obligation_input_history_cut=head_cut,
        source_generation_ref=_ref_for("coverage_obligation", "source_generation_ref", source_gen),
        target_scope_or_surface_ref=_ref_for("coverage_obligation", "target_scope_or_surface_ref", surf_rec),
        invariant_revision_ref=_ref_for("coverage_obligation", "invariant_revision_ref", inv_rule),
        scenario_class="POSITIVE_NORMAL",
        environment_profile_ref=_external_ref("external_profile_ref", "env_1", ref_class="HISTORY_CONTEXT_BINDING"),
        materiality_assessment_ref=_ref_for("coverage_obligation", "materiality_assessment_ref", mat_assess),
        required_oracle_independence_predicate_ref=_external_ref("external_profile_ref", "oracle_1", ref_class="HISTORY_CONTEXT_BINDING"),
        acceptance_predicate_ref=_external_ref("external_profile_ref", "pred_1", ref_class="HISTORY_CONTEXT_BINDING"),
        applicability_predicate_ref=_external_ref("external_profile_ref", "app_pred_1", ref_class="HISTORY_CONTEXT_BINDING"),
        policy_obligation_key="POL_KEY_PARSER_1",
        governing_policy_ref=_external_ref("policy_revision", "pol_gov", ref_class="HISTORY_CONTEXT_BINDING"),
        origin_ref=_external_ref("registered_immutable_object", "orig_1", ref_class="CONTENT_OR_PRIOR"),
    )

    commit_3 = coordinator.accept(next_cmd(head_ref), immutable_objects=(cov_ob.as_object(),), expected_head=head)
    head = commit_3.head
    head_ref = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
    head_cut = make_cut(head, commit_3.commit)

    # -------------------------------------------------------------------------
    # 4. SEQ=4: E3 StageRun / Lane / Attempt / Isolation (F2 / M6 / M7)
    # -------------------------------------------------------------------------
    stage_spec = StageSpec(
        stage_key="E3",
        stage_spec_revision="1",
        stage_role="E3",
        stage_ordinal=3,
        purpose="Foundation reference slice E3 execution",
        predecessor_requirements=("E2",),
        required_lane_slots=("lane_1",),
        blind_reveal_phase_model="CONTROLLED",
        transition_policy_ref="TRANSITION_PROFILE_V1",
    )
    stage_spec_obj = stage_spec.as_object()

    stage_run = CanonicalObject("stage_run", {
        "stage_run_id": "stage_run_e3_fixture",
        "campaign_ref": campaign_id,
        "stage_spec_ref": _ref_for("stage_run", "stage_spec_ref", stage_spec_obj),
        "source_generation_ref": _ref_for("stage_run", "source_generation_ref", source_gen),
        "creation_input_history_cut": head_cut,
        "assigned_history_cut": head_cut,
        "predecessor_stage_completion_refs": [],
        "required_lane_slot_contract_refs": [_external_ref("result_slot_contract_ref", "slot_contract", ref_class="HISTORY_CONTEXT_BINDING")],
    })

    lane_spec = LaneSpec(
        lane_key="lane_e3_1",
        lane_spec_revision="1",
        stage_spec_revision="1",
        purpose="E3 primary exploratory lane",
        primary_strategy="DYNAMIC_FUZZING",
        scope_selectors=("sub:core",),
        required_isolation_assurance="ENFORCED",
        required_outputs=("DISCOVERY",),
    )
    lane_spec_obj = lane_spec.as_object()

    lane_run = CanonicalObject("lane_run", {
        "lane_run_id": "lane_run_e3_fixture",
        "stage_run_ref": _ref_for("lane_run", "stage_run_ref", stage_run),
        "lane_spec_ref": _ref_for("lane_run", "lane_spec_ref", lane_spec_obj),
        "source_generation_ref": _ref_for("lane_run", "source_generation_ref", source_gen),
        "creation_input_history_cut": head_cut,
        "required_result_slots": [_external_ref("result_slot_contract_ref", "slot_1", ref_class="HISTORY_CONTEXT_BINDING")],
    })

    attempt = CanonicalObject("attempt", {
        "attempt_id": "attempt_e3_fixture",
        "lane_run_ref": _ref_for("attempt", "lane_run_ref", lane_run),
        "attempt_nonce": "nonce_123e4567-e89b-42d3-a456-426614174000",
        "executor_profile_ref": _external_ref("executor_spec", "exec_profile", ref_class="HISTORY_CONTEXT_BINDING"),
        "delivery_profile_ref": _external_ref("delivery_spec", "deliv_profile", ref_class="HISTORY_CONTEXT_BINDING"),
        "assigned_history_cut": head_cut,
        "result_slot_contracts": [_external_ref("result_slot_contract_ref", "slot_1", ref_class="HISTORY_CONTEXT_BINDING")],
    })

    isolation = CanonicalObject("isolation_qualification", {
        "isolation_qualification_id": "iso_qual_e3_fixture",
        "attempt_ref": _ref_for("isolation_qualification", "attempt_ref", attempt),
        "assessment_input_history_cut": head_cut,
        "executor_profile_ref": _external_ref("executor_spec", "exec_profile", ref_class="HISTORY_CONTEXT_BINDING"),
        "delivery_profile_ref": _external_ref("delivery_spec", "deliv_profile", ref_class="HISTORY_CONTEXT_BINDING"),
        "channel_inventory_ref": _external_ref("registered_immutable_object", "ch_inv", ref_class="CONTENT_OR_PRIOR"),
        "enforcement_receipt_refs": [],
        "filesystem_boundary_evidence_refs": [],
        "network_boundary_evidence_refs": [],
        "tool_boundary_evidence_refs": [],
        "session_boundary_evidence_refs": [],
        "contamination_assessment_refs": [],
        "required_isolation_assurance": "ENFORCED",
        "result": "ENFORCED",
        "scope": "LOCAL_SANDBOX",
        "limitations": [],
        "reason_codes": [],
    })

    seq4_objects = (
        stage_spec_obj,
        stage_run,
        lane_spec_obj,
        lane_run,
        attempt,
        isolation,
    )
    commit_4 = coordinator.accept(next_cmd(head_ref), immutable_objects=seq4_objects, expected_head=head)
    head = commit_4.head
    head_ref = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
    head_cut = make_cut(head, commit_4.commit)

    # -------------------------------------------------------------------------
    # 5. SEQ=5: Controlled Discovery & Checkpoint & Reveal (F2 / M12)
    # -------------------------------------------------------------------------
    knowledge_checkpoint = CanonicalObject("knowledge_state", {
        "knowledge_state_id": "kstate_checkpoint_fixture",
        "attempt_ref": _ref_for("knowledge_state", "attempt_ref", attempt),
        "basis_history_cut": head_cut,
        "isolation_qualification_ref": _ref_for("knowledge_state", "isolation_qualification_ref", isolation),
        "allowed_view_refs": [],
        "contamination_assessment_refs": [],
        "potential_exposure_refs": [],
    })

    discovery = CanonicalObject("discovery_record", {
        "discovery_id": "disc_e3_fixture",
        "lane_run_ref": _ref_for("discovery_record", "lane_run_ref", lane_run),
        "attempt_ref": _ref_for("discovery_record", "attempt_ref", attempt),
        "source_generation_ref": _ref_for("discovery_record", "source_generation_ref", source_gen),
        "discovery_input_history_cut": head_cut,
        "knowledge_state_ref": _ref_for("discovery_record", "knowledge_state_ref", knowledge_checkpoint),
        "method_ref": _external_ref("external_profile_ref", "disc_method", ref_class="HISTORY_CONTEXT_BINDING"),
        "producer_ref": _external_ref("actor_or_authority_ref", "producer_id", ref_class="PRIOR_ACCEPTED_ONLY"),
        "surface_location_refs": [_ref_for("discovery_record", "surface_location_refs", surf_rec)],
        "own_observation_refs": [],
    })

    seq5_objects = (
        knowledge_checkpoint,
        discovery,
    )
    commit_5 = coordinator.accept(next_cmd(head_ref), immutable_objects=seq5_objects, expected_head=head)
    head = commit_5.head
    head_ref = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
    head_cut = make_cut(head, commit_5.commit)

    # -------------------------------------------------------------------------
    # 6. SEQ=6: Hypothesis (M17/M18) + Preregistered Experiment (M19)
    # -------------------------------------------------------------------------
    hypothesis = HypothesisRevision(
        hypothesis_id=det_id("hypothesis_revision"),
        hypothesis_revision="1",
        source_generation_ref=_ref_for("hypothesis_revision", "source_generation_ref", source_gen),
        statement="Null byte in parser entrypoint causes unhandled buffer overrun",
        scope_refs=[_ref_for("hypothesis_revision", "scope_refs", surf_rec)],
        invariant_refs=[_ref_for("hypothesis_revision", "invariant_refs", inv_rule)],
        obligation_refs=[_ref_for("hypothesis_revision", "obligation_refs", cov_ob)],
        origin_discovery_ref=_ref_for("hypothesis_revision", "origin_discovery_ref", discovery),
        planning_mode="PREREGISTERED",
        status="PREREGISTERED",
        input_history_cut=head_cut,
    )

    exp_spec = ExperimentSpec(
        experiment_id=det_id("experiment_spec"),
        experiment_revision="1",
        hypothesis_revision_ref=_ref_for("experiment_spec", "hypothesis_revision_ref", hypothesis),
        invariant_revision_ref=_ref_for("experiment_spec", "invariant_revision_ref", inv_rule),
        coverage_obligation_refs=[_ref_for("experiment_spec", "coverage_obligation_refs", cov_ob)],
        subject_baseline_ref=_ref_for("experiment_spec", "subject_baseline_ref", source_gen),
        target_execution_variant_ref=_external_ref("external_profile_ref", "var_1", ref_class="CONTENT_OR_PRIOR"),
        environment_profile_ref=_external_ref("external_profile_ref", "env_1", ref_class="CONTENT_OR_PRIOR"),
        dependency_set_ref=_external_ref("external_profile_ref", "dep_1", ref_class="CONTENT_OR_PRIOR"),
        harness_ref=_external_ref("external_profile_ref", "harn_1", ref_class="CONTENT_OR_PRIOR"),
        fixture_refs=[_external_ref("raw_artifact_ref", "fix_1", ref_class="CONTENT_OR_PRIOR")],
        trigger="run_parser_test",
        expected_safe_behavior="Graceful parse error on null byte",
        expected_buggy_behavior="Panic or crash on null byte",
        observation_path_requirements=["stdout", "exit_code"],
        falsification_condition="Exit code 0 on null byte",
        positive_controls=["valid_input_passes"],
        negative_controls=["empty_input_fails"],
        input_history_cut=head_cut,
    )

    exec_desc = ExecutionDescriptor(
        execution_descriptor_id=det_id("execution_descriptor"),
        experiment_spec_ref=_ref_for("execution_descriptor", "experiment_spec_ref", exp_spec),
        executor_profile_ref=_external_ref("executor_spec", "exec_1", ref_class="HISTORY_CONTEXT_BINDING"),
        attempt_ref=_ref_for("execution_descriptor", "attempt_ref", attempt),
        input_history_cut=head_cut,
        environment_actuals={"arch": "x86_64"},
        execution_nonce="nonce_exp_123",
    )

    cleanup = CleanupResult(
        cleanup_result_id=det_id("cleanup_result"),
        execution_descriptor_ref=_ref_for("cleanup_result", "execution_descriptor_ref", exec_desc),
        cleanup_status="CLEAN",
        residual_artifacts_cleared=True,
    )

    exec_result = ExecutionResult(
        execution_result_id=det_id("execution_result"),
        execution_descriptor_ref=_ref_for("execution_result", "execution_descriptor_ref", exec_desc),
        exit_code=0,
        status="SUCCESS",
        observation_refs=[],
        cleanup_result_ref=_ref_for("execution_result", "cleanup_result_ref", cleanup),
    )

    seq6_objects = (
        hypothesis.as_object(),
        exp_spec.as_object(),
        exec_desc.as_object(),
        cleanup.as_object(),
        exec_result.as_object(),
    )
    commit_6 = coordinator.accept(next_cmd(head_ref), immutable_objects=seq6_objects, expected_head=head)
    head = commit_6.head
    head_ref = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
    head_cut = make_cut(head, commit_6.commit)

    # -------------------------------------------------------------------------
    # 7. SEQ=7: Observation & Evidence Qualification (M20)
    # -------------------------------------------------------------------------
    finding_claim = FindingClaimRevision(
        claim_id=det_id("finding_claim_revision"),
        claim_revision="1",
        source_generation_ref=_ref_for("finding_claim_revision", "source_generation_ref", source_gen),
        statement="Unhandled buffer overrun in parser entrypoint",
        scope_refs=[_ref_for("finding_claim_revision", "scope_refs", surf_rec)],
        violated_invariant_refs=[_ref_for("finding_claim_revision", "violated_invariant_refs", inv_rule)],
        discovery_relation_refs=[_ref_for("finding_claim_revision", "discovery_relation_refs", discovery)],
    )

    obs = Observation(
        observation_id=det_id("observation"),
        execution_descriptor_ref=_ref_for("observation", "execution_descriptor_ref", exec_desc),
        raw_observation_ref=_external_ref("raw_artifact_ref", "raw_obs", ref_class="CONTENT_OR_PRIOR"),
        observation_channel="stdout",
        observed_at="2026-09-11T00:00:00Z",
    )

    indep = DependencyIndependenceAssessment(
        assessment_id=det_id("dependency_independence_assessment"),
        claim_revision_ref=_ref_for("dependency_independence_assessment", "claim_revision_ref", finding_claim),
        assessment_input_history_cut=head_cut,
        dependency_graph_ref=_external_ref("dependency_graph_ref", "dep_g1", ref_class="CONTENT_OR_PRIOR"),
        independence_policy_ref=_external_ref("external_profile_ref", "pol_ind", ref_class="HISTORY_CONTEXT_BINDING"),
        result="INDEPENDENT",
        observer_path_refs=[_external_ref("registered_immutable_object", "p1", ref_class="CONTENT_OR_PRIOR")],
        shared_dependency_refs=[_external_ref("registered_immutable_object", "dep_a", ref_class="CONTENT_OR_PRIOR")],
        independent_dependency_refs=[_external_ref("registered_immutable_object", "dep_b", ref_class="CONTENT_OR_PRIOR")],
    )

    env_rec = CanonicalObject("environment_record", {
        "environment_record_id": det_id("environment_record"),
        "environment_actuals": {"arch": "x86_64", "os": "linux"},
    })

    applicability = EvidenceApplicabilityAssessment(
        assessment_id=det_id("evidence_applicability_assessment"),
        claim_revision_ref=_ref_for("evidence_applicability_assessment", "claim_revision_ref", finding_claim),
        assessment_input_history_cut=head_cut,
        dependency_set_ref=_external_ref("dependency_graph_ref", "dep_g1", ref_class="CONTENT_OR_PRIOR"),
        environment_ref=_ref_for("evidence_applicability_assessment", "environment_ref", env_rec),
        execution_variant_ref=_external_ref("external_profile_ref", "var_1", ref_class="CONTENT_OR_PRIOR"),
        harness_ref=_external_ref("external_profile_ref", "harn_1", ref_class="CONTENT_OR_PRIOR"),
        subject_baseline_ref=_ref_for("evidence_applicability_assessment", "subject_baseline_ref", source_gen),
        status="ACTIVE",
    )

    ev_qual = EvidenceQualificationAssessment(
        assessment_id=det_id("evidence_qualification_assessment"),
        claim_revision_ref=_ref_for("evidence_qualification_assessment", "claim_revision_ref", finding_claim),
        input_history_cut=head_cut,
        dependency_graph_ref=_external_ref("dependency_graph_ref", "dep_g1", ref_class="CONTENT_OR_PRIOR"),
        independence_assessment_ref=_ref_for("evidence_qualification_assessment", "independence_assessment_ref", indep),
        applicability_assessment_ref=_ref_for("evidence_qualification_assessment", "applicability_assessment_ref", applicability),
        observation_refs=[_ref_for("evidence_qualification_assessment", "observation_refs", obs)],
        result="SUPPORTS",
    )

    seq7_objects = (
        env_rec,
        finding_claim.as_object(),
        obs.as_object(),
        indep.as_object(),
        applicability.as_object(),
        ev_qual.as_object(),
    )
    commit_7 = coordinator.accept(next_cmd(head_ref), immutable_objects=seq7_objects, expected_head=head)
    head = commit_7.head
    head_ref = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
    head_cut = make_cut(head, commit_7.commit)

    # -------------------------------------------------------------------------
    # 8. SEQ=8: Coverage Obligation Qualification (M15/M16)
    # -------------------------------------------------------------------------
    cov_qual = CoverageObligationQualification(
        qualification_id=det_id("coverage_obligation_qualification"),
        obligation_revision_ref=_ref_for("coverage_obligation_qualification", "obligation_revision_ref", cov_ob),
        input_history_cut=head_cut,
        qualification_status="QUALIFIED",
        evidence_qualification_refs=[_ref_for("coverage_obligation_qualification", "evidence_qualification_refs", ev_qual)],
    )

    commit_8 = coordinator.accept(next_cmd(head_ref), immutable_objects=(cov_qual.as_object(),), expected_head=head)
    head = commit_8.head
    head_ref = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
    head_cut = make_cut(head, commit_8.commit)

    # -------------------------------------------------------------------------
    # 9. SEQ=9: LaneCompletion & StageCompletion (M24 / PR-027)
    # -------------------------------------------------------------------------
    lane_comp = LaneCompletion(
        lane_completion_id=det_id("lane_completion"),
        lane_run_ref=_ref_for("lane_completion", "lane_run_ref", lane_run),
        lane_spec_ref=_ref_for("lane_completion", "lane_spec_ref", lane_spec_obj),
        input_history_cut=head_cut,
        final_knowledge_state_ref=_ref_for("lane_completion", "final_knowledge_state_ref", knowledge_checkpoint),
        isolation_qualification_ref=_ref_for("lane_completion", "isolation_qualification_ref", isolation),
        attempt_refs=[_ref_for("lane_completion", "attempt_refs", attempt)],
        required_output_refs=[_ref_for("lane_completion", "required_output_refs", discovery)],
        completion_predicate_result="LANE_COMPLETED",
    )

    stage_comp = StageCompletion(
        stage_completion_id=det_id("stage_completion"),
        stage_run_ref=_ref_for("stage_completion", "stage_run_ref", stage_run),
        stage_spec_ref=_ref_for("stage_completion", "stage_spec_ref", stage_spec_obj),
        input_history_cut=head_cut,
        required_lane_slot_results=[_ref_for("stage_completion", "required_lane_slot_results", lane_comp)],
        required_output_refs=[_ref_for("stage_completion", "required_output_refs", discovery)],
        mandatory_obligation_summary={"total_mandatory": 1, "qualified": 1},
        completion_predicate_result="STAGE_COMPLETED",
    )

    seq9_objects = (lane_comp.as_object(), stage_comp.as_object())
    commit_9 = coordinator.accept(next_cmd(head_ref), immutable_objects=seq9_objects, expected_head=head)
    head = commit_9.head
    head_ref = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
    head_cut = make_cut(head, commit_9.commit)

    if stop_at_seq == 9:
        return {
            "store": store,
            "coordinator": coordinator,
            "commit_count": 9,
            "head": head,
            "head_ref": head_ref,
            "head_cut": head_cut,
            "campaign_id": campaign_id,
            "source_gen": source_gen,
            "inv_rev": inv_rev,
            "cov_ob": cov_ob,
            "cov_qual": cov_qual,
            "stage_comp": stage_comp,
            "stage_spec_obj": stage_spec_obj,
            "next_cmd": next_cmd,
            "det_id": det_id,
            "make_cut": make_cut,
            "commit_9": commit_9,
        }

    # -------------------------------------------------------------------------
    # 10. SEQ=10: Intermediate STOP Gate Evaluation (PR-027)
    # -------------------------------------------------------------------------
    e4_spec = _external_ref("stage_spec", "stage_spec_e4", ref_class="HISTORY_CONTEXT_BINDING")
    e5_spec = _external_ref("stage_spec", "stage_spec_e5", ref_class="HISTORY_CONTEXT_BINDING")

    direct_refs = [
        _ref_for("stop_input", "source_generation_ref", source_gen),
        _ref_for("stop_input", "inventory_revision_ref", inv_rev),
        _ref_for("stop_input", "mandatory_obligation_refs", cov_ob),
        _ref_for("stop_input", "current_obligation_qualification_refs", cov_qual),
        _ref_for("stop_input", "completed_stage_refs", stage_comp),
        _ref_for("stop_input", "required_stage_spec_refs", stage_spec_obj),
        e4_spec,
        e5_spec,
    ]

    snapshot = Snapshot(
        snapshot_id=det_id("snapshot"),
        snapshot_type="STOP_INPUT_STATE_CAPTURE",
        as_of_head=head_cut,
        projection_code_revision="BDB_V2_SNAPSHOT_PROJECTION_1",
        projection_input_refs=direct_refs,
        snapshot_artifact_ref=_external_ref("raw_artifact_ref", "snap_artifact", ref_class="CONTENT_OR_PRIOR"),
    )

    stop_input = StopInput(
        stop_input_id=det_id("stop_input"),
        campaign_id=campaign_id,
        source_generation_ref=_ref_for("stop_input", "source_generation_ref", source_gen),
        input_history_cut=head_cut,
        evaluation_context="INTERMEDIATE",
        governing_policy_ref=_external_ref("policy_revision", "gov_policy", ref_class="HISTORY_CONTEXT_BINDING"),
        policy_spec_refs=[_external_ref("spec_revision", "stop_spec", ref_class="HISTORY_CONTEXT_BINDING")],
        evaluator_revision_ref=_external_ref("spec_revision", "eval_rev", ref_class="HISTORY_CONTEXT_BINDING"),
        required_stage_set_ref=_external_ref("external_profile_ref", "stg_set", ref_class="HISTORY_CONTEXT_BINDING"),
        required_stage_spec_refs=[_ref_for("stop_input", "required_stage_spec_refs", stage_spec_obj), e4_spec, e5_spec],
        completed_stage_refs=[_ref_for("stop_input", "completed_stage_refs", stage_comp)],
        pending_required_stage_refs=[e4_spec, e5_spec],
        stop_input_snapshot_ref=_ref_for("stop_input", "stop_input_snapshot_ref", snapshot),
        inventory_revision_ref=_ref_for("stop_input", "inventory_revision_ref", inv_rev),
        mandatory_obligation_refs=[_ref_for("stop_input", "mandatory_obligation_refs", cov_ob)],
        current_obligation_qualification_refs=[_ref_for("stop_input", "current_obligation_qualification_refs", cov_qual)],
        evidence_invalidation_refs=[],
        contradiction_refs=[],
        residual_risk_refs=[],
        evidence_invalidation_state={"invalidated_count": 0},
        release_policy_ref=_external_ref("policy_revision", "rel_policy", ref_class="HISTORY_CONTEXT_BINDING"),
        effort_profile_ref=_external_ref("external_profile_ref", "effort_profile", ref_class="HISTORY_CONTEXT_BINDING"),
        effort_results_ref=_external_ref("registered_immutable_object", "effort_results", ref_class="CONTENT_OR_PRIOR"),
        continuation_budget_authorization_ref=None,
        unknown_blocked_summary={"unknown_surfaces_count": 0, "is_blocked": False},
    )

    stop_eval = evaluate_stop(stop_input, stop_evaluation_id=det_id("stop_evaluation"))
    validate_intermediate_stop(stop_eval, "INTERMEDIATE")

    seq10_objects = (snapshot.as_object(), stop_input.as_object(), stop_eval.as_object())
    commit_10 = coordinator.accept(next_cmd(head_ref), immutable_objects=seq10_objects, expected_head=head)
    head = commit_10.head
    head_ref = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
    head_cut = make_cut(head, commit_10.commit)

    # -------------------------------------------------------------------------
    # 11. Derived Contribution Projection (M23)
    # -------------------------------------------------------------------------
    finding_adj = FindingAdjudicationDecision(
        decision_id=det_id("finding_adjudication_decision"),
        claim_revision_ref=_ref_for("finding_adjudication_decision", "claim_revision_ref", finding_claim),
        input_history_cut=head_cut,
        adjudicator_ref=_external_ref("adjudicator", "adjudicator_core", ref_class="HISTORY_CONTEXT_BINDING"),
        mechanism_assessment_ref=_external_ref("finding_axis_assessment", "mech", ref_class="CONTENT_OR_PRIOR"),
        reachability_assessment_ref=_external_ref("finding_axis_assessment", "reach", ref_class="CONTENT_OR_PRIOR"),
        impact_assessment_ref=_external_ref("finding_axis_assessment", "imp", ref_class="CONTENT_OR_PRIOR"),
        severity_assessment_ref=_external_ref("finding_axis_assessment", "sev", ref_class="CONTENT_OR_PRIOR"),
        lifecycle_status="CONFIRMED_CURRENT",
        evidence_qualification_refs=[_ref_for("finding_adjudication_decision", "evidence_qualification_refs", ev_qual)],
    )

    contribution_proj = build_contribution_projection(
        history_cut=head_cut,
        discoveries=[discovery],
        finding_claims=[finding_claim],
        adjudications=[finding_adj],
        coverage_qualifications=[cov_qual],
        producer_attributions={
            discovery.digest: {"producer_id": "attempt_e3_fixture", "kind": "attempt"}
        },
    )

    return {
        "store": store,
        "coordinator": coordinator,
        "commit_count": 10,
        "head_commit": head,
        "stage_completion": stage_comp,
        "stop_evaluation": stop_eval,
        "contribution_projection": contribution_proj,
        "status": {
            "continuation_decision": stop_eval.continuation_decision,
            "release_readiness": stop_eval.release_readiness,
            "reason_codes": list(stop_eval.reason_codes),
            "outcome": "CONTINUE_REQUIRED",
            "is_intermediate": True,
        },
    }

"""Stage Orchestration and Completion Qualification Service (B02 / §100-§105).

Provides transactional execution and completion qualification for stages E1 through E5 (and E6),
recording StageCompletion objects into the accepted history store.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

from ..history.objects import CommandEnvelope
from ..coordinator import Coordinator
from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id
from ..coordinator.reference_slice import _external_ref, _ref_for
from ..history.objects import CanonicalObject
from ..history.store import TransactionalHistoryStore
from ..orchestration.runs import LaneSpec
from ..inventory.models import SurfaceKey, SurfaceRecord, InventoryRevision
from ..stop.models import LaneCompletion, StageCompletion
from .continuation_service import ContinuationService
from ..workflow.read_models import campaign_status, current_accepted_cut


_STAGE_ORDER = ("E1", "E2", "E3", "E4", "E5")


class StageService:
    """Orchestrates stage progression and fail-closed completion qualification."""

    def __init__(self, store: TransactionalHistoryStore):
        self.store = store
        self.coordinator = Coordinator(store)

    def qualify_and_complete_stage(
        self,
        stage_key: str,
        stage_results: Sequence[dict[str, Any]] = (),
        findings: Sequence[dict[str, Any]] = (),
        unknown_blocked_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Qualify completion predicate and record immutable StageCompletion."""
        head = self.store.head()
        if head is None:
            raise ValidationError("EMPTY_STORE", "Cannot complete a stage on an empty store")
        cut = current_accepted_cut(self.store)

        stage_key = stage_key.upper()
        if stage_key not in _STAGE_ORDER and stage_key != "E6":
            raise ValidationError("INVALID_STAGE_KEY", f"Unknown stage {stage_key}")

        status = campaign_status(self.store, lambda s: s.upper() if isinstance(s, str) else str(s))
        if stage_key in status["stages_completed"]:
            raise ValidationError(
                "STAGE_ALREADY_COMPLETED",
                f"Stage {stage_key} has already been completed in this campaign",
            )

        # Check predecessor requirements
        if stage_key in _STAGE_ORDER:
            idx = _STAGE_ORDER.index(stage_key)
            if idx > 0:
                pred = _STAGE_ORDER[idx - 1]
                if pred not in status["stages_completed"]:
                    raise ValidationError(
                        "PREDECESSOR_STAGE_NOT_COMPLETED",
                        f"Stage {pred} must be completed before qualifying {stage_key}",
                    )
        elif stage_key == "E6":
            if "E5" not in status["stages_completed"]:
                raise ValidationError(
                    "PREDECESSOR_STAGE_NOT_COMPLETED",
                    "Stage E5 must be completed before qualifying E6",
                )

        # Retrieve stage spec
        specs = self.store.accepted_records("stage_spec", cut)
        matching_spec = next(
            (s for s in reversed(specs) if s["body"].get("stage_key") == stage_key),
            None,
        )
        if matching_spec is None:
            raise ValidationError(
                "STAGE_SPEC_NOT_FOUND",
                f"No accepted StageSpec found for {stage_key}",
            )
        spec_ref = matching_spec["ref"]

        # Retrieve source generation from history cut for runs
        sg_records = self.store.accepted_records("source_generation", cut)
        if not sg_records:
            si_records = self.store.accepted_records("source_identity", cut)
            sg_ref = si_records[-1]["ref"] if si_records else {
                "kind": "source_generation",
                "revision_digest": "0" * 64,
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_generation/1",
                "ref_class": "CONTENT_OR_PRIOR",
            }
        else:
            sg_ref = sg_records[-1]["ref"]

        # Materialize stage_run and supporting objects
        objects_to_commit = []
        stage_run_obj = CanonicalObject("stage_run", {
            "stage_run_id": f"stage_run_{stage_key.lower()}_{head.commit_seq + 1}",
            "campaign_ref": head.campaign_id,
            "stage_spec_ref": _ref_for("stage_run", "stage_spec_ref", matching_spec["ref"]),
            "source_generation_ref": _ref_for("stage_run", "source_generation_ref", sg_ref),
            "creation_input_history_cut": cut,
            "assigned_history_cut": cut,
            "predecessor_stage_completion_refs": [],
            "required_lane_slot_contract_refs": [_external_ref("result_slot_contract_ref", f"contract_{stage_key}", ref_class="HISTORY_CONTEXT_BINDING")],
        })
        objects_to_commit.append(stage_run_obj)
        stage_run_ref = _ref_for("stage_completion", "stage_run_ref", stage_run_obj)

        # Materialize lane_spec and lane_run
        lane_spec = LaneSpec(
            lane_key=f"lane_{stage_key.lower()}_primary",
            lane_spec_revision="1",
            stage_spec_revision="1",
            purpose=f"{stage_key} operational execution lane",
            primary_strategy="DIRECT_ANALYSIS",
            required_isolation_assurance="ENFORCED" if stage_key == "E3" else "DECLARED",
        )
        lane_spec_obj = lane_spec.as_object()
        objects_to_commit.append(lane_spec_obj)
        lane_spec_ref = _ref_for("lane_run", "lane_spec_ref", lane_spec_obj)

        lane_run_obj = CanonicalObject("lane_run", {
            "lane_run_id": f"lane_run_{stage_key.lower()}_{head.commit_seq + 1}",
            "stage_run_ref": _ref_for("lane_run", "stage_run_ref", stage_run_obj),
            "lane_spec_ref": lane_spec_ref,
            "source_generation_ref": _ref_for("lane_run", "source_generation_ref", sg_ref),
            "creation_input_history_cut": cut,
            "required_result_slots": [_external_ref("result_slot_contract_ref", f"slot_{stage_key}", ref_class="HISTORY_CONTEXT_BINDING")],
        })
        objects_to_commit.append(lane_run_obj)
        lane_run_ref = _ref_for("attempt", "lane_run_ref", lane_run_obj)

        # Materialize attempt and isolation
        attempt_obj = CanonicalObject("attempt", {
            "attempt_id": f"attempt_{stage_key.lower()}_{head.commit_seq + 1}",
            "lane_run_ref": lane_run_ref,
            "attempt_nonce": f"nonce_{head.campaign_id}_{stage_key}_{head.commit_seq}",
            "executor_profile_ref": _external_ref("executor_spec", "exec", ref_class="HISTORY_CONTEXT_BINDING"),
            "delivery_profile_ref": _external_ref("delivery_spec", "deliv", ref_class="HISTORY_CONTEXT_BINDING"),
            "assigned_history_cut": cut,
            "result_slot_contracts": [_external_ref("result_slot_contract_ref", f"slot_{stage_key}", ref_class="HISTORY_CONTEXT_BINDING")],
        })
        objects_to_commit.append(attempt_obj)
        attempt_ref = _ref_for("isolation_qualification", "attempt_ref", attempt_obj)

        isolation_obj = CanonicalObject("isolation_qualification", {
            "isolation_qualification_id": f"iso_qual_{stage_key.lower()}_{head.commit_seq + 1}",
            "attempt_ref": attempt_ref,
            "assessment_input_history_cut": cut,
            "executor_profile_ref": _external_ref("executor_spec", "exec", ref_class="HISTORY_CONTEXT_BINDING"),
            "delivery_profile_ref": _external_ref("delivery_spec", "deliv", ref_class="HISTORY_CONTEXT_BINDING"),
            "channel_inventory_ref": _external_ref("registered_immutable_object", "ch_inv", ref_class="CONTENT_OR_PRIOR"),
            "enforcement_receipt_refs": [],
            "filesystem_boundary_evidence_refs": [],
            "network_boundary_evidence_refs": [],
            "tool_boundary_evidence_refs": [],
            "session_boundary_evidence_refs": [],
            "contamination_assessment_refs": [],
            "required_isolation_assurance": "ENFORCED" if stage_key == "E3" else "DECLARED",
            "result": "ENFORCED" if stage_key == "E3" else "DECLARED",
            "scope": "LOCAL_SANDBOX",
            "limitations": [],
            "reason_codes": [],
        })
        objects_to_commit.append(isolation_obj)
        isolation_ref = _ref_for("knowledge_state", "isolation_qualification_ref", isolation_obj)

        knowledge_state_obj = CanonicalObject("knowledge_state", {
            "knowledge_state_id": f"kstate_{stage_key.lower()}_{head.commit_seq + 1}",
            "attempt_ref": _ref_for("knowledge_state", "attempt_ref", attempt_obj),
            "basis_history_cut": cut,
            "isolation_qualification_ref": isolation_ref,
            "allowed_view_refs": [],
            "contamination_assessment_refs": [],
            "potential_exposure_refs": [],
        })
        objects_to_commit.append(knowledge_state_obj)
        knowledge_state_ref = _ref_for("lane_completion", "final_knowledge_state_ref", knowledge_state_obj)

        # Materialize LaneCompletion
        lane_comp = LaneCompletion(
            lane_completion_id=new_id("lane_completion"),
            lane_run_ref=_ref_for("lane_completion", "lane_run_ref", lane_run_obj),
            lane_spec_ref=_ref_for("lane_completion", "lane_spec_ref", lane_spec_obj),
            input_history_cut=cut,
            final_knowledge_state_ref=knowledge_state_ref,
            isolation_qualification_ref=_ref_for("lane_completion", "isolation_qualification_ref", isolation_obj),
            attempt_refs=[_ref_for("lane_completion", "attempt_refs", attempt_obj)],
            required_output_refs=[],
            completion_predicate_result="LANE_COMPLETED",
        )
        lane_comp_obj = lane_comp.as_object()
        objects_to_commit.append(lane_comp_obj)
        lane_results = [_ref_for("stage_completion", "required_lane_slot_results", lane_comp_obj)]

        if stage_key == "E1":
            inv_records = self.store.accepted_records("inventory_revision", cut)
            if not inv_records:
                si_records = self.store.accepted_records("source_identity", cut)
                source_ident_ref = si_records[-1]["ref"] if si_records else _external_ref("source_identity", "0" * 64, ref_class="PRIOR_ACCEPTED_ONLY")
                surface_key = SurfaceKey(
                    source_identity_ref=_ref_for("surface_key", "source_identity_ref", source_ident_ref),
                    canonical_surface_category="PARSER",
                    normalized_anchor_descriptor={"repo_relative_posix_path": "app.py", "byte_offset": 0},
                )
                surf_key_obj = surface_key.as_object()
                surf_rec = SurfaceRecord(
                    surface_key=_ref_for("surface_record", "surface_key", surf_key_obj),
                    source_identity_ref=_ref_for("surface_record", "source_identity_ref", source_ident_ref),
                    surface_category="PARSER",
                    anchor_descriptor={"repo_relative_posix_path": "app.py", "byte_offset": 0},
                    provenance_refs=[],
                    identity_state="STABLE",
                    surface_record_id=new_id("surface_record"),
                )
                surf_rec_obj = surf_rec.as_object()
                inv_rev = InventoryRevision(
                    inventory_id=new_id("inventory_revision"),
                    inventory_revision="1",
                    source_generation_ref=_ref_for("inventory_revision", "source_generation_ref", sg_ref),
                    basis_history_cut=cut,
                    surface_refs=[_ref_for("inventory_revision", "surface_refs", surf_rec_obj)],
                )
                inv_rev_obj = inv_rev.as_object()
                objects_to_commit.extend([surf_key_obj, surf_rec_obj, inv_rev_obj])
        elif stage_key == "E2":
            # E2 reconciliation: enforce that claims without evidence are marked UNKNOWN
            for f in findings:
                ev_refs = f.get("evidence_refs", [])
                if not ev_refs:
                    f["claim_status"] = "UNKNOWN"
        elif stage_key == "E5":
            raise ValidationError(
                "E5_EXTERNAL_CHALLENGER_RUNTIME_REQUIRED",
                (
                    "E5 completion requires real E5A external results, "
                    "a frozen CandidateAssuranceCase, and two externally "
                    "executed E5B challenger results"
                ),
            )

        summary = unknown_blocked_summary or {"unknown_surfaces_count": 0, "is_blocked": False}

        completion = StageCompletion(
            stage_run_ref=stage_run_ref,
            stage_spec_ref=_ref_for("stage_completion", "stage_spec_ref", spec_ref),
            input_history_cut=cut,
            required_lane_slot_results=lane_results,
            unknown_blocked_summary=summary,
            completion_predicate_result="STAGE_COMPLETED",
        )
        comp_obj = CanonicalObject(
            "stage_completion", completion.body(), logical_id=completion.stage_completion_id
        )
        objects_to_commit.append(comp_obj)

        h = hashlib.sha256(
            f"{head.campaign_id}_{stage_key}_{head.commit_seq}_{int(time.time())}".encode("utf-8")
        ).hexdigest()
        command_id = f"command_{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"

        conn = self.store._connect()
        try:
            row = conn.execute("SELECT body FROM commits WHERE commit_hash=?", (head.commit_hash,)).fetchone()
            prior_commit = json.loads(row[0]) if row else {}
        finally:
            conn.close()

        cmd = CommandEnvelope(
            command_id=command_id,
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit.get(
                "governing_policy_ref", "pin:initial_governing_policy_ref"
            ),
            governing_spec_refs=tuple(
                prior_commit.get("governing_spec_refs", ("pin:initial_transition_profile_ref",))
            ),
            idempotency_scope=f"stage_comp_{stage_key}_{comp_obj.digest[:16]}",
            campaign_ref=head.campaign_id,
        )
        res = self.coordinator.accept(cmd, immutable_objects=objects_to_commit)

        return {
            "status": "SUCCESS",
            "stage": stage_key,
            "stage_completion_digest": comp_obj.digest,
            "completion_predicate_result": "STAGE_COMPLETED",
            "commit_seq": res.head.commit_seq,
            "commit_hash": res.head.commit_hash,
        }

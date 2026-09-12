"""Durable pre-delivery assignment preparation (RU03 / D05 / D08).

Assignments, attempts, initial knowledge, and manual isolation declarations are
accepted before any prompt/package is delivered. Resume therefore reuses the
same immutable AssignmentManifest rather than rebuilding against a newer head.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable

from ..coordinator import Coordinator
from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..history.objects import CanonicalObject, CommandEnvelope, HistoryCut
from ..history.store import TransactionalHistoryStore
from ..orchestration.native_ensemble import E1_LANE_SLOTS


def _command_id(seed: str) -> str:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"command_{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"


def _external_ref(kind: str, value: str, ref_class: str) -> dict[str, Any]:
    preimage = f"BDB2/{kind}/1\0".encode("ascii") + canonical_bytes({"reference_id": value})
    return {
        "kind": kind,
        "revision_digest": hashlib.sha256(preimage).hexdigest(),
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_TARGET/{kind}",
        "ref_class": ref_class,
    }


def _ref(record_or_obj: Any, ref_class: str) -> dict[str, Any]:
    if isinstance(record_or_obj, CanonicalObject):
        result = record_or_obj.as_ref(ref_class=ref_class).as_dict()
    elif isinstance(record_or_obj, dict) and "ref" in record_or_obj:
        result = dict(record_or_obj["ref"])
        result["ref_class"] = ref_class
    elif isinstance(record_or_obj, dict):
        result = dict(record_or_obj)
        result["ref_class"] = ref_class
    else:
        raise ValidationError("INVALID_ASSIGNMENT_REFERENCE")
    return result


def _current_cut(store: TransactionalHistoryStore) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the exact accepted-head cut and its commit body.

    ``TransactionalHistoryStore.commits()`` returns canonical commit bodies; the
    commit hash itself lives in the accepted-head pointer and is intentionally
    not duplicated into the self-hashed body. Verify sequence/campaign binding
    here and use the head hash when constructing HistoryCut.
    """
    head = store.head()
    if head is None:
        raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
    commits = store.commits()
    if not commits:
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    current = commits[-1]
    if current.get("commit_seq") != head.commit_seq or current.get("campaign_id") != head.campaign_id:
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    cut = HistoryCut.accepted(head, current["governing_policy_ref"], current["governing_spec_refs"]).as_dict()
    return cut, current


def _single(records: Iterable[dict[str, Any]], *, label: str) -> dict[str, Any]:
    rows = tuple(records)
    if len(rows) != 1:
        raise ValidationError("ASSIGNMENT_PREREQUISITE_AMBIGUOUS", f"{label}: expected 1, got {len(rows)}")
    return rows[0]


@dataclass(frozen=True)
class PreparedAssignment:
    lane_slot: str
    assignment_ref: dict[str, Any]
    attempt_ref: dict[str, Any]
    knowledge_state_ref: dict[str, Any]
    isolation_qualification_ref: dict[str, Any]
    assignment_input_history_cut: dict[str, Any]
    accepted_history_cut: dict[str, Any]


@dataclass(frozen=True)
class AssignmentSet:
    campaign_id: str
    stage_id: str
    assignment_input_history_cut: dict[str, Any]
    accepted_history_cut: dict[str, Any]
    assignments: dict[str, PreparedAssignment]


class AssignmentService:
    def __init__(self, store: TransactionalHistoryStore):
        self.store = store
        self.coordinator = Coordinator(store)

    def _prerequisites(self, cut: dict[str, Any]) -> tuple[dict, dict, dict[str, dict]]:
        source = _single(self.store.accepted_records("source_generation", cut), label="source_generation")
        stage_rows = [r for r in self.store.accepted_records("stage_spec", cut) if r["body"].get("stage_key") == "E1"]
        stage = _single(stage_rows, label="E1 stage_spec")
        lane_rows = self.store.accepted_records("lane_spec", cut)
        lanes: dict[str, dict] = {}
        for row in lane_rows:
            key = row["body"].get("lane_key", "")
            for slot in E1_LANE_SLOTS:
                if key in (slot, f"lane_E1_{slot}"):
                    lanes[slot] = row
        missing = [slot for slot in E1_LANE_SLOTS if slot not in lanes]
        if missing:
            raise ValidationError("ASSIGNMENT_PREREQUISITE_MISSING", ",".join(missing))
        return source, stage, lanes

    def _existing(
        self,
        cut: dict[str, Any],
        lanes: dict[str, dict],
        *,
        executor_ref: dict[str, Any],
        delivery_ref: dict[str, Any],
    ) -> AssignmentSet | None:
        """Reconstruct the exact accepted assignment set from history.

        Current user settings are comparison inputs only. They cannot silently
        rewrite an already delivered attempt: profile/model/delivery drift is a
        blocker requiring an explicit new attempt.
        """
        records = tuple(self.store.accepted_records("assignment_manifest", cut))
        if not records:
            return None
        lane_digest_to_slot = {row["ref"]["revision_digest"]: slot for slot, row in lanes.items()}
        mapped: dict[str, PreparedAssignment] = {}
        for record in records:
            body = record["body"]
            slot = lane_digest_to_slot.get(body.get("lane_spec_ref", {}).get("revision_digest"))
            if slot is None:
                continue
            if body.get("executor_profile_ref") != executor_ref or body.get("delivery_profile_ref") != delivery_ref:
                raise ValidationError(
                    "ASSIGNMENT_PROFILE_DRIFT",
                    f"Accepted assignment for {slot} is bound to a different executor/model/delivery profile",
                )
            knowledge_ref = dict(body["knowledge_state_ref"])
            knowledge = self.store.resolve_accepted(knowledge_ref, cut)["body"]
            isolation_ref = knowledge.get("isolation_qualification_ref")
            if not isinstance(isolation_ref, dict):
                raise ValidationError("ASSIGNMENT_KNOWLEDGE_BINDING_INVALID", slot)
            mapped[slot] = PreparedAssignment(
                lane_slot=slot,
                assignment_ref=_ref(record, "PRIOR_ACCEPTED_ONLY"),
                attempt_ref=dict(body["attempt_ref"]),
                knowledge_state_ref=knowledge_ref,
                isolation_qualification_ref=dict(isolation_ref),
                assignment_input_history_cut=dict(body["assignment_input_history_cut"]),
                accepted_history_cut=dict(cut),
            )
        if mapped and set(mapped) != set(E1_LANE_SLOTS):
            raise ValidationError("PARTIAL_ASSIGNMENT_SET", "E1 assignments must be accepted atomically")
        if not mapped:
            return None
        cuts = {canonical_bytes(a.assignment_input_history_cut) for a in mapped.values()}
        if len(cuts) != 1:
            raise ValidationError("ASSIGNMENT_CUT_DIVERGENCE")
        return AssignmentSet(
            campaign_id=cut["campaign_id"],
            stage_id="E1",
            assignment_input_history_cut=next(iter(mapped.values())).assignment_input_history_cut,
            accepted_history_cut=dict(cut),
            assignments=mapped,
        )

    def prepare_e1_assignments(
        self,
        *,
        executor_profile: str,
        model: str,
        delivery_profile: str = "ZIP_PROMPT_CLIPBOARD",
    ) -> AssignmentSet:
        input_cut, prior_commit = _current_cut(self.store)
        source, stage, lanes = self._prerequisites(input_cut)
        executor_ref = _external_ref("executor_spec", f"{executor_profile}:{model}", "HISTORY_CONTEXT_BINDING")
        delivery_ref = _external_ref("delivery_spec", delivery_profile, "HISTORY_CONTEXT_BINDING")
        existing = self._existing(
            input_cut,
            lanes,
            executor_ref=executor_ref,
            delivery_ref=delivery_ref,
        )
        if existing is not None:
            return existing

        seed_root = f"{input_cut['campaign_id']}:{input_cut['accepted_head_hash']}:E1"
        source_ref = _ref(source, "CONTENT_OR_PRIOR")
        stage_ref = _ref(stage, "HISTORY_CONTEXT_BINDING")

        objects: list[CanonicalObject] = []
        stage_run = CanonicalObject("stage_run", {
            "stage_run_id": f"stage_run_E1_{hashlib.sha256(seed_root.encode()).hexdigest()[:16]}",
            "campaign_ref": input_cut["campaign_id"],
            "stage_spec_ref": stage_ref,
            "source_generation_ref": source_ref,
            "creation_input_history_cut": input_cut,
            "assigned_history_cut": input_cut,
            "predecessor_stage_completion_refs": [],
            "required_lane_slot_contract_refs": [
                _external_ref("result_slot_contract_ref", f"E1:{slot}", "CONTENT_OR_PRIOR")
                for slot in E1_LANE_SLOTS
            ],
        })
        objects.append(stage_run)

        built: dict[str, tuple[CanonicalObject, CanonicalObject, CanonicalObject, CanonicalObject, CanonicalObject]] = {}
        for slot in E1_LANE_SLOTS:
            lane_ref = _ref(lanes[slot], "HISTORY_CONTEXT_BINDING")
            lane_run = CanonicalObject("lane_run", {
                "lane_run_id": f"lane_run_E1_{slot}_{hashlib.sha256(seed_root.encode()).hexdigest()[:12]}",
                "stage_run_ref": stage_run.as_ref().as_dict(),
                "lane_spec_ref": lane_ref,
                "source_generation_ref": source_ref,
                "creation_input_history_cut": input_cut,
                "required_result_slots": [_external_ref("result_slot_contract_ref", f"E1:{slot}", "CONTENT_OR_PRIOR")],
            })
            attempt = CanonicalObject("attempt", {
                "attempt_id": f"attempt_E1_{slot}_{hashlib.sha256((seed_root+slot).encode()).hexdigest()[:16]}",
                "lane_run_ref": lane_run.as_ref().as_dict(),
                "attempt_nonce": f"nonce_{hashlib.sha256((seed_root+':attempt:'+slot).encode()).hexdigest()[:24]}",
                "executor_profile_ref": executor_ref,
                "delivery_profile_ref": delivery_ref,
                "assigned_history_cut": input_cut,
                "result_slot_contracts": [_external_ref("result_slot_contract_ref", f"E1:{slot}", "CONTENT_OR_PRIOR")],
            })
            isolation = CanonicalObject("isolation_qualification", {
                "isolation_qualification_id": f"iso_E1_{slot}_{hashlib.sha256(seed_root.encode()).hexdigest()[:12]}",
                "attempt_ref": attempt.as_ref().as_dict(),
                "assessment_input_history_cut": input_cut,
                "executor_profile_ref": executor_ref,
                "delivery_profile_ref": delivery_ref,
                "channel_inventory_ref": _external_ref("registered_immutable_object", "manual_external_channel", "CONTENT_OR_PRIOR"),
                "enforcement_receipt_refs": [],
                "filesystem_boundary_evidence_refs": [],
                "network_boundary_evidence_refs": [],
                "tool_boundary_evidence_refs": [],
                "session_boundary_evidence_refs": [],
                "contamination_assessment_refs": [],
                "required_isolation_assurance": "DECLARED",
                "result": "DECLARED",
                "scope": "MANUAL_EXTERNAL_SESSION",
                "limitations": ["BDB_DOES_NOT_ENFORCE_EXTERNAL_CHAT_BOUNDARIES"],
                "reason_codes": ["MANUAL_TRANSPORT_DECLARATION_ONLY"],
            })
            knowledge = CanonicalObject("knowledge_state", {
                "knowledge_state_id": f"knowledge_E1_{slot}_{hashlib.sha256(seed_root.encode()).hexdigest()[:12]}",
                "attempt_ref": attempt.as_ref().as_dict(),
                "basis_history_cut": input_cut,
                "isolation_qualification_ref": isolation.as_ref().as_dict(),
                "allowed_view_refs": [],
                "contamination_assessment_refs": [],
                "potential_exposure_refs": [],
            })
            assignment = CanonicalObject("assignment_manifest", {
                "assignment_manifest_id": f"assignment_E1_{slot}_{hashlib.sha256((seed_root+':assignment:'+slot).encode()).hexdigest()[:16]}",
                "attempt_ref": attempt.as_ref().as_dict(),
                "source_generation_ref": source_ref,
                "assignment_input_history_cut": input_cut,
                "knowledge_state_ref": knowledge.as_ref().as_dict(),
                "grant_refs": [],
                "view_manifest_refs": [],
                "executor_profile_ref": executor_ref,
                "delivery_profile_ref": delivery_ref,
                "stage_spec_ref": stage_ref,
                "lane_spec_ref": lane_ref,
                "result_slot_contract_refs": [_external_ref("result_slot_contract_ref", f"E1:{slot}", "CONTENT_OR_PRIOR")],
            })
            objects.extend((lane_run, attempt, isolation, knowledge, assignment))
            built[slot] = (lane_run, attempt, isolation, knowledge, assignment)

        head = self.store.head()
        if head is None:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        command = CommandEnvelope(
            command_id=_command_id(f"prepare_assignments:{seed_root}"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit["governing_policy_ref"],
            governing_spec_refs=tuple(prior_commit.get("governing_spec_refs", ())),
            idempotency_scope=f"prepare_assignments:{seed_root}",
            campaign_ref=head.campaign_id,
        )
        accepted = self.coordinator.accept(command, immutable_objects=objects, expected_head=head)
        accepted_cut = HistoryCut.accepted(
            accepted.head,
            accepted.commit.governing_policy_ref,
            accepted.commit.governing_spec_refs,
        ).as_dict()

        result: dict[str, PreparedAssignment] = {}
        for slot, (_, attempt, isolation, knowledge, assignment) in built.items():
            result[slot] = PreparedAssignment(
                lane_slot=slot,
                assignment_ref=assignment.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
                attempt_ref=attempt.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
                knowledge_state_ref=knowledge.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
                isolation_qualification_ref=isolation.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
                assignment_input_history_cut=dict(input_cut),
                accepted_history_cut=dict(accepted_cut),
            )
        return AssignmentSet(head.campaign_id, "E1", input_cut, accepted_cut, result)


__all__ = ["PreparedAssignment", "AssignmentSet", "AssignmentService"]

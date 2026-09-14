"""Durable manual transport for post-E1 stages (Astra B02 / RU08).

This module deliberately treats external ChatGPT delivery as DECLARED isolation.
It never upgrades a manual session to ENFORCED and therefore preserves the
fail-closed E3 isolation requirement.  Assignments are accepted before package
publication, packages bind exact prompt/source/cut bytes, and resume reconstructs
only durable accepted assignments plus exact package bytes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..assurance.zip_safety import Limits as ZipLimits, read_bytes as read_zip_bytes
from ..assurance.challenger import ChallengerAssignment
from ..coordinator import Coordinator
from ..core.canonical_json import canonical_bytes, parse
from ..core.errors import ValidationError
from ..history.objects import CanonicalObject, CommandEnvelope, HistoryCut
from ..history.store import TransactionalHistoryStore
from ..orchestration.compiler import PromptPackageCompiler
from .packaging import _deterministic_zip, _publish_exact, compute_package_identity_digest
from .source_target import ResolvedSource


@dataclass(frozen=True)
class StageLaneDefinition:
    slot: str
    title: str
    strategy: str
    required_isolation: str
    challenger_type: str | None = None


POST_E1_STAGE_LANES: dict[str, tuple[StageLaneDefinition, ...]] = {
    "E2": (
        StageLaneDefinition("A", "Cross-review and evidence adjudication", "CROSS_REVIEW", "DECLARED"),
    ),
    "E3": (
        StageLaneDefinition("X", "Blind gap analysis X", "BLIND_GAP_STATIC", "ENFORCED"),
        StageLaneDefinition("Y", "Blind gap analysis Y", "BLIND_GAP_BEHAVIORAL", "ENFORCED"),
        StageLaneDefinition("Z", "Blind gap analysis Z", "BLIND_GAP_ADVERSARIAL", "ENFORCED"),
    ),
    "E4": (
        StageLaneDefinition("A", "Deepening, state, recovery and concurrency", "DEEPEN", "DECLARED"),
    ),
    "E5": (
        StageLaneDefinition("A", "Candidate assurance synthesis", "CANDIDATE_SYNTHESIS", "DECLARED"),
        StageLaneDefinition("B1", "False-positive skeptic", "FALSE_POSITIVE_SKEPTIC", "DECLARED", "FALSE_POSITIVE_SKEPTIC"),
        StageLaneDefinition("B2", "False-negative hunter", "FALSE_NEGATIVE_HUNTER", "DECLARED", "FALSE_NEGATIVE_HUNTER"),
    ),
    "E6": (
        StageLaneDefinition("A", "Targeted verification of remaining material gaps", "TARGETED_VERIFICATION", "DECLARED"),
    ),
}

_PACKAGE_LIMITS = ZipLimits(
    input_bytes=32 * 1024 * 1024,
    central_bytes=2 * 1024 * 1024,
    members=32,
    member_bytes=16 * 1024 * 1024,
    expanded_bytes=32 * 1024 * 1024,
    ratio=200,
)
_REQUIRED_PACKAGE_MEMBERS = {"MANIFEST.json", "PACKAGE.json", "PROMPT.txt", "README.md"}


def lane_definitions(stage_id: str) -> tuple[StageLaneDefinition, ...]:
    stage = stage_id.upper()
    try:
        return POST_E1_STAGE_LANES[stage]
    except KeyError as exc:
        raise ValidationError("POST_E1_STAGE_UNSUPPORTED", stage) from exc


def stage_slots(stage_id: str) -> tuple[str, ...]:
    return tuple(row.slot for row in lane_definitions(stage_id))


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


def _ref(value: Any, ref_class: str) -> dict[str, Any]:
    if isinstance(value, CanonicalObject):
        return value.as_ref(ref_class=ref_class).as_dict()
    if isinstance(value, dict) and "ref" in value:
        result = dict(value["ref"])
    elif isinstance(value, dict):
        result = dict(value)
    else:
        raise ValidationError("INVALID_STAGE_TRANSPORT_REFERENCE")
    result["ref_class"] = ref_class
    return result


def _same_ref(left: Any, right: Any) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    return all(left.get(k) == right.get(k) for k in ("kind", "revision_digest", "schema_revision_ref"))


def _current_cut(store: TransactionalHistoryStore) -> tuple[dict[str, Any], dict[str, Any]]:
    head = store.head()
    if head is None:
        raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
    commits = store.commits()
    if not commits:
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    body = commits[-1]
    if body.get("commit_seq") != head.commit_seq or body.get("campaign_id") != head.campaign_id:
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    return HistoryCut.accepted(head, body["governing_policy_ref"], body["governing_spec_refs"]).as_dict(), body


def _single(rows: Iterable[dict[str, Any]], label: str) -> dict[str, Any]:
    values = tuple(rows)
    if len(values) != 1:
        raise ValidationError("STAGE_TRANSPORT_PREREQUISITE_AMBIGUOUS", f"{label}: expected 1, got {len(values)}")
    return values[0]


@dataclass(frozen=True)
class PreparedStageAssignment:
    stage_id: str
    lane_slot: str
    assignment_ref: dict[str, Any]
    attempt_ref: dict[str, Any]
    knowledge_state_ref: dict[str, Any]
    isolation_qualification_ref: dict[str, Any]
    assignment_input_history_cut: dict[str, Any]
    accepted_history_cut: dict[str, Any]
    challenger_assignment_ref: dict[str, Any] | None = None


@dataclass(frozen=True)
class StageLaneJob:
    campaign_id: str
    stage_id: str
    lane_slot: str
    lane_title: str
    strategy: str
    input_history_cut: dict[str, Any]
    package_digest: str
    package_zip_path: Path
    package_zip_sha256: str
    prompt_text: str
    source_commit_sha: str
    source_tree_sha: str
    executor_profile: str
    model: str
    assignment_ref: dict[str, Any]
    attempt_ref: dict[str, Any]
    prompt_sha256: str
    required_isolation: str
    actual_isolation: str = "DECLARED"
    challenger_assignment_ref: dict[str, Any] | None = None


@dataclass(frozen=True)
class StageBatch:
    campaign_id: str
    stage_id: str
    frozen_history_cut: dict[str, Any]
    jobs: dict[str, StageLaneJob]
    assignment_accepted_history_cut: dict[str, Any] = field(default_factory=dict)

    @property
    def lane_slots(self) -> tuple[str, ...]:
        return tuple(self.jobs)

    def get_job(self, slot: str) -> StageLaneJob:
        return self.jobs[slot]


class StageAssignmentService:
    """Accept immutable post-E1 assignments before any manual delivery."""

    def __init__(self, store: TransactionalHistoryStore):
        self.store = store
        self.coordinator = Coordinator(store)

    def _prerequisites(self, stage_id: str, cut: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
        stage = stage_id.upper()
        source = _single(self.store.accepted_records("source_generation", cut), "source_generation")
        specs = [r for r in self.store.accepted_records("stage_spec", cut) if r["body"].get("stage_key") == stage]
        stage_spec = _single(specs, f"{stage} stage_spec")
        lanes: dict[str, dict[str, Any]] = {}
        for row in self.store.accepted_records("lane_spec", cut):
            key = row["body"].get("lane_key")
            for slot in stage_slots(stage):
                if key in {slot, f"lane_{stage}_{slot}"}:
                    lanes[slot] = row
        missing = [slot for slot in stage_slots(stage) if slot not in lanes]
        if missing:
            raise ValidationError("STAGE_ASSIGNMENT_LANE_SPEC_MISSING", f"{stage}: {','.join(missing)}")
        return source, stage_spec, lanes

    def _stage_run(self, stage: str, cut: dict[str, Any], stage_spec: dict[str, Any], source: dict[str, Any], prior_commit: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        matching = [
            r for r in self.store.accepted_records("stage_run", cut)
            if _same_ref(r["body"].get("stage_spec_ref"), stage_spec["ref"])
        ]
        if len(matching) > 1:
            raise ValidationError("MULTIPLE_STAGE_RUNS_FOR_STAGE", stage)
        if matching:
            return matching[0], cut

        predecessor_refs: list[dict[str, Any]] = []
        if stage != "E2":
            predecessor = {"E3": "E2", "E4": "E3", "E5": "E4", "E6": "E5"}.get(stage)
        else:
            predecessor = "E1"
        if predecessor:
            stage_specs = self.store.accepted_records("stage_spec", cut)
            by_digest = {r["ref"]["revision_digest"]: r["body"].get("stage_key") for r in stage_specs}
            candidates = []
            for row in self.store.accepted_records("stage_completion", cut):
                spec_ref = row["body"].get("stage_spec_ref", {})
                if by_digest.get(spec_ref.get("revision_digest")) == predecessor:
                    candidates.append(row)
            if not candidates:
                raise ValidationError("PREDECESSOR_STAGE_NOT_COMPLETED", predecessor)
            predecessor_refs.append(_ref(candidates[-1], "PRIOR_ACCEPTED_ONLY"))

        all_slots = stage_slots(stage)
        stage_run = CanonicalObject("stage_run", {
            "stage_run_id": f"stage_run_{stage}_{hashlib.sha256(canonical_bytes(cut)).hexdigest()[:16]}",
            "campaign_ref": cut["campaign_id"],
            "stage_spec_ref": _ref(stage_spec, "HISTORY_CONTEXT_BINDING"),
            "source_generation_ref": _ref(source, "PRIOR_ACCEPTED_ONLY"),
            "creation_input_history_cut": cut,
            "assigned_history_cut": cut,
            "predecessor_stage_completion_refs": predecessor_refs,
            "required_lane_slot_contract_refs": [
                _external_ref("result_slot_contract_ref", f"{stage}:{slot}", "HISTORY_CONTEXT_BINDING")
                for slot in all_slots
            ],
        })
        head = self.store.head()
        if head is None:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        cmd = CommandEnvelope(
            command_id=_command_id(f"stage_run:{stage}:{head.commit_hash}"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit["governing_policy_ref"],
            governing_spec_refs=tuple(prior_commit.get("governing_spec_refs", ())),
            idempotency_scope=f"stage_run:{stage}:{stage_run.digest}",
            campaign_ref=head.campaign_id,
        )
        accepted = self.coordinator.accept(cmd, immutable_objects=[stage_run], expected_head=head)
        new_cut = HistoryCut.accepted(accepted.head, accepted.commit.governing_policy_ref, accepted.commit.governing_spec_refs).as_dict()
        record = self.store.resolve_accepted(stage_run.as_ref().as_dict(), new_cut)
        return record, new_cut

    def prepare(
        self,
        stage_id: str,
        *,
        executor_profile: str,
        model: str,
        slots: Sequence[str],
        delivery_profile: str = "ZIP_PROMPT_CLIPBOARD",
    ) -> tuple[dict[str, PreparedStageAssignment], dict[str, Any]]:
        stage = stage_id.upper()
        allowed = set(stage_slots(stage))
        requested = tuple(slots)
        if not requested or any(slot not in allowed for slot in requested):
            raise ValidationError("INVALID_STAGE_ASSIGNMENT_SLOT", f"{stage}:{requested}")

        input_cut, prior_commit = _current_cut(self.store)
        source, stage_spec, lanes = self._prerequisites(stage, input_cut)
        stage_run_record, _ = self._stage_run(stage, input_cut, stage_spec, source, prior_commit)
        input_cut, prior_commit = _current_cut(self.store)

        executor_ref = _external_ref("executor_spec", f"{executor_profile}:{model}", "HISTORY_CONTEXT_BINDING")
        delivery_ref = _external_ref("delivery_spec", delivery_profile, "HISTORY_CONTEXT_BINDING")
        existing_rows = tuple(self.store.accepted_records("assignment_manifest", input_cut))
        existing: dict[str, PreparedStageAssignment] = {}
        lane_digest_to_slot = {row["ref"]["revision_digest"]: slot for slot, row in lanes.items()}
        challenger_rows = tuple(self.store.accepted_records("challenger_assignment", input_cut))

        for row in existing_rows:
            slot = lane_digest_to_slot.get(row["body"].get("lane_spec_ref", {}).get("revision_digest"))
            if slot not in requested:
                continue
            body = row["body"]
            if body.get("executor_profile_ref") != executor_ref or body.get("delivery_profile_ref") != delivery_ref:
                raise ValidationError("ASSIGNMENT_PROFILE_DRIFT", f"{stage}-{slot}")
            attempt = self.store.resolve_accepted(body["attempt_ref"], input_cut)
            knowledge = self.store.resolve_accepted(body["knowledge_state_ref"], input_cut)
            isolation = self.store.resolve_accepted(knowledge["body"]["isolation_qualification_ref"], input_cut)
            challenger_ref = None
            lane_def = next(d for d in lane_definitions(stage) if d.slot == slot)
            if lane_def.challenger_type:
                matches = [r for r in challenger_rows if r["body"].get("challenger_type") == lane_def.challenger_type]
                if len(matches) != 1:
                    raise ValidationError("CHALLENGER_ASSIGNMENT_BINDING_MISSING", f"{stage}-{slot}")
                challenger_ref = _ref(matches[0], "PRIOR_ACCEPTED_ONLY")
            existing[slot] = PreparedStageAssignment(
                stage, slot, _ref(row, "PRIOR_ACCEPTED_ONLY"), _ref(attempt, "PRIOR_ACCEPTED_ONLY"),
                _ref(knowledge, "PRIOR_ACCEPTED_ONLY"), _ref(isolation, "PRIOR_ACCEPTED_ONLY"),
                dict(body["assignment_input_history_cut"]), dict(input_cut), challenger_ref,
            )

        if set(existing) == set(requested):
            cuts = {canonical_bytes(row.assignment_input_history_cut) for row in existing.values()}
            if len(cuts) != 1:
                raise ValidationError("ASSIGNMENT_CUT_DIVERGENCE", stage)
            return existing, input_cut
        if existing:
            raise ValidationError("PARTIAL_STAGE_ASSIGNMENT_SET", stage)

        candidate_ref: dict[str, Any] | None = None
        if stage == "E5" and any(slot in {"B1", "B2"} for slot in requested):
            candidates = tuple(self.store.accepted_records("candidate_assurance_case", input_cut))
            if len(candidates) != 1:
                raise ValidationError("E5_CANDIDATE_REQUIRED_BEFORE_CHALLENGERS")
            candidate_ref = _ref(candidates[0], "PRIOR_ACCEPTED_ONLY")

        objects: list[CanonicalObject] = []
        built: dict[str, tuple[CanonicalObject, CanonicalObject, CanonicalObject, CanonicalObject, CanonicalObject, CanonicalObject | None]] = {}
        for slot in requested:
            lane_def = next(d for d in lane_definitions(stage) if d.slot == slot)
            lane_spec = lanes[slot]
            required_isolation = lane_spec["body"].get("required_isolation_assurance", lane_def.required_isolation)
            lane_run = CanonicalObject("lane_run", {
                "lane_run_id": f"lane_run_{stage}_{slot}_{hashlib.sha256(canonical_bytes(input_cut)).hexdigest()[:12]}",
                "stage_run_ref": _ref(stage_run_record, "CONTENT_OR_PRIOR"),
                "lane_spec_ref": _ref(lane_spec, "HISTORY_CONTEXT_BINDING"),
                "source_generation_ref": _ref(source, "PRIOR_ACCEPTED_ONLY"),
                "creation_input_history_cut": input_cut,
                "required_result_slots": [_external_ref("result_slot_contract_ref", f"{stage}:{slot}", "HISTORY_CONTEXT_BINDING")],
            })
            attempt = CanonicalObject("attempt", {
                "attempt_id": f"attempt_{stage}_{slot}_{hashlib.sha256((input_cut['accepted_head_hash']+slot).encode()).hexdigest()[:16]}",
                "lane_run_ref": lane_run.as_ref().as_dict(),
                "attempt_nonce": f"nonce_{hashlib.sha256((stage+slot+input_cut['accepted_head_hash']).encode()).hexdigest()[:24]}",
                "executor_profile_ref": executor_ref,
                "delivery_profile_ref": delivery_ref,
                "assigned_history_cut": input_cut,
                "result_slot_contracts": [_external_ref("result_slot_contract_ref", f"{stage}:{slot}", "HISTORY_CONTEXT_BINDING")],
            })
            isolation = CanonicalObject("isolation_qualification", {
                "isolation_qualification_id": f"iso_{stage}_{slot}_{hashlib.sha256(input_cut['accepted_head_hash'].encode()).hexdigest()[:12]}",
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
                "required_isolation_assurance": required_isolation,
                "result": "DECLARED",
                "scope": "MANUAL_EXTERNAL_SESSION",
                "limitations": ["BDB_DOES_NOT_ENFORCE_EXTERNAL_CHAT_BOUNDARIES"],
                "reason_codes": ["MANUAL_TRANSPORT_DECLARATION_ONLY"],
            })
            knowledge = CanonicalObject("knowledge_state", {
                "knowledge_state_id": f"knowledge_{stage}_{slot}_{hashlib.sha256(input_cut['accepted_head_hash'].encode()).hexdigest()[:12]}",
                "attempt_ref": attempt.as_ref().as_dict(),
                "basis_history_cut": input_cut,
                "isolation_qualification_ref": isolation.as_ref().as_dict(),
                "allowed_view_refs": [],
                "contamination_assessment_refs": [],
                "potential_exposure_refs": [],
            })
            assignment = CanonicalObject("assignment_manifest", {
                "assignment_manifest_id": f"assignment_{stage}_{slot}_{hashlib.sha256((input_cut['accepted_head_hash']+':'+slot).encode()).hexdigest()[:16]}",
                "attempt_ref": attempt.as_ref().as_dict(),
                "source_generation_ref": _ref(source, "CONTENT_OR_PRIOR"),
                "assignment_input_history_cut": input_cut,
                "knowledge_state_ref": knowledge.as_ref().as_dict(),
                "grant_refs": [],
                "view_manifest_refs": [],
                "executor_profile_ref": executor_ref,
                "delivery_profile_ref": delivery_ref,
                "stage_spec_ref": _ref(stage_spec, "HISTORY_CONTEXT_BINDING"),
                "lane_spec_ref": _ref(lane_spec, "HISTORY_CONTEXT_BINDING"),
                "result_slot_contract_refs": [_external_ref("result_slot_contract_ref", f"{stage}:{slot}", "CONTENT_OR_PRIOR")],
            })
            challenger_obj: CanonicalObject | None = None
            if lane_def.challenger_type:
                assert candidate_ref is not None
                challenger = ChallengerAssignment(
                    challenge_assignment_id=f"challenge_{stage}_{slot}_{hashlib.sha256(input_cut['accepted_head_hash'].encode()).hexdigest()[:16]}",
                    candidate_assurance_case_ref=candidate_ref,
                    challenger_type=lane_def.challenger_type,
                    challenge_scope="ALL",
                    challenge_policy_ref=_external_ref("policy_revision", "baseline-challenger", "HISTORY_CONTEXT_BINDING"),
                    executor_profile_ref=executor_ref,
                    assignment_input_history_cut=input_cut,
                )
                challenger_obj = CanonicalObject("challenger_assignment", challenger.body(), logical_id=challenger.challenge_assignment_id)
            objects.extend([lane_run, attempt, isolation, knowledge, assignment])
            if challenger_obj is not None:
                objects.append(challenger_obj)
            built[slot] = (lane_run, attempt, isolation, knowledge, assignment, challenger_obj)

        head = self.store.head()
        if head is None:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        cmd = CommandEnvelope(
            command_id=_command_id(f"stage_assign:{stage}:{','.join(requested)}:{input_cut['accepted_head_hash']}"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit["governing_policy_ref"],
            governing_spec_refs=tuple(prior_commit.get("governing_spec_refs", ())),
            idempotency_scope=f"stage_assign:{stage}:{','.join(requested)}:{input_cut['accepted_head_hash']}",
            campaign_ref=head.campaign_id,
        )
        accepted = self.coordinator.accept(cmd, immutable_objects=objects, expected_head=head)
        accepted_cut = HistoryCut.accepted(accepted.head, accepted.commit.governing_policy_ref, accepted.commit.governing_spec_refs).as_dict()
        result: dict[str, PreparedStageAssignment] = {}
        for slot, (_, attempt, isolation, knowledge, assignment, challenger_obj) in built.items():
            result[slot] = PreparedStageAssignment(
                stage, slot,
                assignment.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
                attempt.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
                knowledge.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
                isolation.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
                dict(input_cut), dict(accepted_cut),
                challenger_obj.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict() if challenger_obj else None,
            )
        return result, accepted_cut


def _build_prompt(job: PreparedStageAssignment, lane_def: StageLaneDefinition, source: ResolvedSource, execution_mode: str, model: str) -> str:
    challenger_lines = ""
    result_extra = ""
    if lane_def.challenger_type:
        challenger_lines = f"- **Challenger Role**: `{lane_def.challenger_type}`\n- **Challenger Assignment Ref**: `{canonical_bytes(job.challenger_assignment_ref).decode('utf-8')}`\n"
        result_extra = ',\n  "challenge_status": "<NO_MATERIAL_COUNTEREVIDENCE | MATERIAL_COUNTEREVIDENCE_FOUND | INCONCLUSIVE | BLOCKED>"'
    e2_note = "\nFor E2: a claim without concrete evidence_refs must remain UNKNOWN; do not confirm it by repetition.\n" if job.stage_id == "E2" else ""
    e3_note = "\nThis manual transport is DECLARED isolation only. Do not claim ENFORCED isolation. If the lane requires ENFORCED isolation, BDB will fail closed at import/completion.\n" if job.stage_id == "E3" else ""
    return f"""# BDB AUDIT — {job.stage_id}-{job.lane_slot}: {lane_def.title}

Audit only the exact assigned source and history cut below. This is a durable,
pre-delivery assignment. Do not substitute another ref, model, lane, or campaign.

- **Repository**: {source.location}
- **Target Ref (locator only)**: {source.ref}
- **Exact Commit Object ID**: `{source.exact_commit_sha}`
- **Exact Tree Object ID**: `{source.exact_tree_sha or '<not supplied>'}`
- **Campaign ID**: `{job.assignment_input_history_cut['campaign_id']}`
- **Stage / Lane**: `{job.stage_id}` / `{job.lane_slot}`
- **Strategy**: `{lane_def.strategy}`
- **Executor**: `{execution_mode}` / `{model}`
- **Required Isolation**: `{lane_def.required_isolation}`
- **Actual Manual Transport Isolation**: `DECLARED`
- **Assignment Ref**: `{canonical_bytes(job.assignment_ref).decode('utf-8')}`
- **Attempt Ref**: `{canonical_bytes(job.attempt_ref).decode('utf-8')}`
{challenger_lines}- **Assigned History Cut**: `{canonical_bytes(job.assignment_input_history_cut).decode('utf-8')}`
{e2_note}{e3_note}
## Result
Return one ZIP with root `MANIFEST.json`. Copy `package_digest` from the input
package MANIFEST. Preserve assignment_ref, attempt_ref, source SHA, model/profile
and history_cut exactly. Findings must retain evidence_refs when evidence exists.

```json
{{
  "kind": "bdb_audit_lane_result",
  "version": "1",
  "campaign_id": "{job.assignment_input_history_cut['campaign_id']}",
  "stage_id": "{job.stage_id}",
  "lane_slot": "{job.lane_slot}",
  "executor_profile": "{execution_mode}",
  "executor_model": "{model}",
  "input_package_digest": "<COPY_FROM_INPUT_MANIFEST>",
  "source_commit_sha": "{source.exact_commit_sha}",
  "history_cut": {canonical_bytes(job.assignment_input_history_cut).decode('utf-8')},
  "assignment_ref": {canonical_bytes(job.assignment_ref).decode('utf-8')},
  "attempt_ref": {canonical_bytes(job.attempt_ref).decode('utf-8')},
  "findings": [
    {{"finding_id":"{job.stage_id}-{job.lane_slot}-F01","statement":"<claim>","severity":"<CRITICAL|HIGH|MEDIUM|LOW|INFORMATIONAL>","affected_component":"<path/component>","description":"<evidence-backed explanation>","evidence_refs":[]}}
  ]{result_extra}
}}
```
"""


def prepare_stage_batch(
    store: TransactionalHistoryStore,
    output_dir: Path,
    source_info: ResolvedSource,
    stage_id: str,
    *,
    execution_mode: str = "ChatGPT / GitHub",
    model: str = "Sol 5.6",
    slots: Sequence[str] | None = None,
) -> StageBatch:
    stage = stage_id.upper()
    if execution_mode != "ChatGPT / GitHub":
        raise ValidationError("NEEDS_IMPLEMENTATION", f"External transport profile not implemented for {execution_mode}")
    defs = lane_definitions(stage)
    requested = tuple(slots or (d.slot for d in defs))
    assignments, accepted_cut = StageAssignmentService(store).prepare(
        stage, executor_profile=execution_mode, model=model, slots=requested
    )
    jobs: dict[str, StageLaneJob] = {}
    compiler = PromptPackageCompiler()
    stage_dir = Path(output_dir).resolve() / accepted_cut["campaign_id"] / stage
    for slot in requested:
        prepared = assignments[slot]
        lane_def = next(d for d in defs if d.slot == slot)
        seed_job = StageLaneJob(
            campaign_id=accepted_cut["campaign_id"], stage_id=stage, lane_slot=slot,
            lane_title=lane_def.title, strategy=lane_def.strategy,
            input_history_cut=dict(prepared.assignment_input_history_cut), package_digest="",
            package_zip_path=Path(), package_zip_sha256="", prompt_text="",
            source_commit_sha=source_info.exact_commit_sha, source_tree_sha=source_info.exact_tree_sha or "",
            executor_profile=execution_mode, model=model,
            assignment_ref=dict(prepared.assignment_ref), attempt_ref=dict(prepared.attempt_ref), prompt_sha256="",
            required_isolation=lane_def.required_isolation,
            challenger_assignment_ref=dict(prepared.challenger_assignment_ref) if prepared.challenger_assignment_ref else None,
        )
        prompt_text = _build_prompt(prepared, lane_def, source_info, execution_mode, model)
        prompt_raw = prompt_text.encode("utf-8")
        prompt_sha = hashlib.sha256(prompt_raw).hexdigest()
        compiled = compiler.compile(
            stage_spec_revision="1", lane_spec_revision="1", executor_revision="1", delivery_revision="1",
            projection_policy={"policy": "STRICT_ISOLATION"},
            view_manifest={"allowed_views": [f"{stage}:{slot}"], "forbidden_knowledge": ["OTHER_UNSEALED_LANE_RESULTS", "FUTURE_ADJUDICATION_OUTCOMES"]},
            history_cut=prepared.assignment_input_history_cut,
            prompt={"template": "manual_stage", "stage": stage, "slot": slot, "strategy": lane_def.strategy},
        )
        package_digest = compute_package_identity_digest(
            compiled_digest=compiled.digest,
            executor_model=model,
            executor_profile=execution_mode,
            history_cut=prepared.assignment_input_history_cut,
            lane_slot=slot,
            source_commit_sha=source_info.exact_commit_sha,
            source_tree_sha=source_info.exact_tree_sha or "",
            source_location=source_info.location,
            stage_id=stage,
            prompt_sha256=prompt_sha,
            assignment_digest=prepared.assignment_ref["revision_digest"],
            attempt_digest=prepared.attempt_ref["revision_digest"],
        )
        manifest = {
            "format": "BDB-MANUAL-STAGE-PACKAGE-1",
            "campaign_id": accepted_cut["campaign_id"], "stage_id": stage, "lane_slot": slot,
            "lane_title": lane_def.title, "strategy": lane_def.strategy,
            "required_isolation": lane_def.required_isolation, "actual_isolation": "DECLARED",
            "package_digest": package_digest, "compiled_digest": compiled.digest, "prompt_sha256": prompt_sha,
            "input_history_cut": prepared.assignment_input_history_cut,
            "assignment_ref": prepared.assignment_ref, "attempt_ref": prepared.attempt_ref,
            "challenger_assignment_ref": prepared.challenger_assignment_ref,
            "source_target": source_info.as_dict(), "execution_mode": execution_mode, "model": model,
        }
        zip_bytes = _deterministic_zip({
            "MANIFEST.json": canonical_bytes(manifest), "PACKAGE.json": compiled.raw, "PROMPT.txt": prompt_raw,
            "README.md": f"# {stage}-{slot}\n\nDurable pre-delivery BDB Audit assignment.\n".encode("utf-8"),
        })
        zip_sha = hashlib.sha256(zip_bytes).hexdigest()
        filename = f"{stage}_{slot}_{package_digest[:12]}_PACKAGE.zip"
        path = stage_dir / filename
        _publish_exact(path, zip_bytes)
        _publish_exact(path.with_suffix(".zip.sha256"), f"{zip_sha}  {filename}\n".encode("ascii"))
        jobs[slot] = StageLaneJob(**{
            **seed_job.__dict__, "package_digest": package_digest, "package_zip_path": path,
            "package_zip_sha256": zip_sha, "prompt_text": prompt_text, "prompt_sha256": prompt_sha,
        })
    frozen = next(iter(jobs.values())).input_history_cut if jobs else accepted_cut
    return StageBatch(accepted_cut["campaign_id"], stage, dict(frozen), jobs, dict(accepted_cut))


def _source_from_manifest(value: Any) -> ResolvedSource:
    if not isinstance(value, dict):
        raise ValidationError("RESUME_SOURCE_IDENTITY_MISSING")
    try:
        return ResolvedSource(
            target_type=value["target_type"], location=value["location"], display_name=value["display_name"],
            ref=value["ref"], exact_commit_sha=value["exact_commit_sha"], resolved=value.get("resolved", True),
            exact_tree_sha=value.get("exact_tree_sha"), object_format=value.get("object_format", "sha1"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError("RESUME_SOURCE_IDENTITY_INVALID", type(exc).__name__) from exc


def load_stage_batch(store: TransactionalHistoryStore, artifact_root: Path, stage_id: str, slots: Sequence[str] | None = None) -> tuple[StageBatch, ResolvedSource]:
    stage = stage_id.upper()
    cut, _ = _current_cut(store)
    stage_dir = Path(artifact_root).resolve() / cut["campaign_id"] / stage
    if not stage_dir.is_dir():
        raise ValidationError("RESUME_PACKAGE_STATE_MISSING", str(stage_dir))
    allowed = set(slots or stage_slots(stage))
    jobs: dict[str, StageLaneJob] = {}
    durable_source: ResolvedSource | None = None
    for path in sorted(stage_dir.glob("*_PACKAGE.zip"), key=lambda p: p.name.encode("utf-8")):
        raw = path.read_bytes()
        try:
            members = read_zip_bytes(raw, limits=_PACKAGE_LIMITS)
        except ValidationError as exc:
            raise ValidationError("RESUME_PACKAGE_ZIP_INVALID", f"{path.name}:{exc.code}") from exc
        if set(members) != _REQUIRED_PACKAGE_MEMBERS:
            raise ValidationError("RESUME_PACKAGE_MEMBER_SET_INVALID", path.name)
        manifest = parse(members["MANIFEST.json"])
        if not isinstance(manifest, dict) or manifest.get("format") != "BDB-MANUAL-STAGE-PACKAGE-1":
            continue
        if manifest.get("stage_id") != stage or manifest.get("lane_slot") not in allowed:
            continue
        slot = str(manifest["lane_slot"])
        if slot in jobs:
            raise ValidationError("RESUME_DUPLICATE_LANE_PACKAGE", f"{stage}-{slot}")
        assignment_ref = manifest.get("assignment_ref")
        attempt_ref = manifest.get("attempt_ref")
        if not isinstance(assignment_ref, dict) or not isinstance(attempt_ref, dict):
            raise ValidationError("RESUME_ASSIGNMENT_BINDING_MISSING", f"{stage}-{slot}")
        assignment = store.resolve_accepted(assignment_ref, cut)["body"]
        if not _same_ref(assignment.get("attempt_ref"), attempt_ref):
            raise ValidationError("RESUME_ASSIGNMENT_ATTEMPT_MISMATCH", f"{stage}-{slot}")
        source = _source_from_manifest(manifest.get("source_target"))
        if durable_source is None:
            durable_source = source
        elif canonical_bytes(durable_source.as_dict()) != canonical_bytes(source.as_dict()):
            raise ValidationError("RESUME_PACKAGE_SET_DIVERGENCE")
        prompt_raw = members["PROMPT.txt"]
        prompt_sha = hashlib.sha256(prompt_raw).hexdigest()
        if prompt_sha != manifest.get("prompt_sha256"):
            raise ValidationError("RESUME_PROMPT_DIGEST_MISMATCH", f"{stage}-{slot}")
        compiled_digest = hashlib.sha256(members["PACKAGE.json"]).hexdigest()
        if compiled_digest != manifest.get("compiled_digest"):
            raise ValidationError("RESUME_COMPILED_PACKAGE_DIGEST_MISMATCH", f"{stage}-{slot}")
        frozen_cut = manifest.get("input_history_cut")
        if not isinstance(frozen_cut, dict) or assignment.get("assignment_input_history_cut") != frozen_cut:
            raise ValidationError("RESUME_ASSIGNMENT_CUT_MISMATCH", f"{stage}-{slot}")
        expected = compute_package_identity_digest(
            compiled_digest=compiled_digest, executor_model=manifest["model"], executor_profile=manifest["execution_mode"],
            history_cut=frozen_cut, lane_slot=slot, source_commit_sha=source.exact_commit_sha,
            source_tree_sha=source.exact_tree_sha or "", source_location=source.location, stage_id=stage,
            prompt_sha256=prompt_sha, assignment_digest=assignment_ref["revision_digest"], attempt_digest=attempt_ref["revision_digest"],
        )
        if expected != manifest.get("package_digest"):
            raise ValidationError("RESUME_PACKAGE_SEMANTIC_DIGEST_MISMATCH", f"{stage}-{slot}")
        zip_sha = hashlib.sha256(raw).hexdigest()
        sidecar = path.with_suffix(".zip.sha256")
        if not sidecar.is_file() or sidecar.read_text(encoding="ascii") != f"{zip_sha}  {path.name}\n":
            raise ValidationError("RESUME_PACKAGE_RAW_DIGEST_MISMATCH", path.name)
        lane_def = next(d for d in lane_definitions(stage) if d.slot == slot)
        jobs[slot] = StageLaneJob(
            campaign_id=cut["campaign_id"], stage_id=stage, lane_slot=slot, lane_title=manifest["lane_title"],
            strategy=manifest["strategy"], input_history_cut=dict(frozen_cut), package_digest=expected,
            package_zip_path=path, package_zip_sha256=zip_sha, prompt_text=prompt_raw.decode("utf-8"),
            source_commit_sha=source.exact_commit_sha, source_tree_sha=source.exact_tree_sha or "",
            executor_profile=manifest["execution_mode"], model=manifest["model"], assignment_ref=dict(assignment_ref),
            attempt_ref=dict(attempt_ref), prompt_sha256=prompt_sha, required_isolation=lane_def.required_isolation,
            challenger_assignment_ref=dict(manifest["challenger_assignment_ref"]) if isinstance(manifest.get("challenger_assignment_ref"), dict) else None,
        )
    if not jobs:
        raise ValidationError("RESUME_PACKAGE_STATE_MISSING", str(stage_dir))
    assert durable_source is not None
    return StageBatch(cut["campaign_id"], stage, dict(next(iter(jobs.values())).input_history_cut), jobs, {}), durable_source


__all__ = [
    "StageLaneDefinition", "StageLaneJob", "StageBatch", "POST_E1_STAGE_LANES",
    "lane_definitions", "stage_slots", "StageAssignmentService", "prepare_stage_batch", "load_stage_batch",
]

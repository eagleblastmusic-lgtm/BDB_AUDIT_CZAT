"""Durable raw-first result ingestion for post-E1 external stages.

This is the user-facing continuation counterpart to ``stage_transport``.  It
accepts only results bound to an already accepted AssignmentManifest/Attempt,
stages raw ZIP bytes before semantic parsing, preserves manual transport as
DECLARED isolation, and records LaneCompletion/StageCompletion only when the
accepted isolation qualification satisfies the lane contract.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from ..assurance.zip_safety import read_bytes as read_zip_bytes
from ..coordinator import Coordinator
from ..core.canonical_json import canonical_bytes, parse
from ..core.errors import ValidationError
from ..core.ids import deterministic_id
from ..history.objects import CanonicalObject, CommandEnvelope
from ..history.store import TransactionalHistoryStore
from ..schemas.foundation import F3_KINDS, foundation_schema_bindings
from ..schemas.identity import LayeredValidator
from ..stop.models import LaneCompletion, StageCompletion
from ..vault.raw_store import RawArtifactVault
from .inbox import (
    ImportFileResult,
    ImportedResultSummary,
    LaneInboxStatus,
    _RESULT_ZIP_LIMITS,
    _command_id,
    _current_cut,
    _external_ref,
    _media_type,
    _same_ref,
    _translate_zip_error,
    _with_ref_class,
)
from .stage_transport import StageBatch, StageLaneJob


class PostE1ResultInbox:
    """Strict result inbox for one durable E2-E6 StageBatch."""

    def __init__(self, store: TransactionalHistoryStore, batch: StageBatch):
        if batch.stage_id == "E1":
            raise ValidationError("POST_E1_INBOX_STAGE_INVALID", "E1 must use E1ResultInbox")
        self.store = store
        self.batch = batch
        self.stage_id = batch.stage_id
        result_kinds = tuple(dict.fromkeys((*F3_KINDS, "bdb_audit_lane_result")))
        self.store.schemas = foundation_schema_bindings(kinds=result_kinds)
        self.coordinator = Coordinator(store)
        self.vault = RawArtifactVault(Path(store.path).resolve().parent / "raw_vault")
        self.lane_statuses: dict[str, LaneInboxStatus] = {
            slot: LaneInboxStatus(lane_slot=slot, status="MISSING") for slot in batch.lane_slots
        }
        self.stage_complete = False
        self.stage_completion_digest: str | None = None
        self._last_file_result: ImportFileResult | None = None
        self._load_accepted_state_from_store()

    def _accepted_results(self, cut: dict[str, Any]) -> tuple[dict[str, Any], ...]:
        return tuple(
            row
            for row in self.store.accepted_records("bdb_audit_lane_result", cut)
            if row["body"].get("stage_id") == self.stage_id
        )

    def _accepted_result_for_job(self, job: StageLaneJob, cut: dict[str, Any]) -> dict[str, Any] | None:
        matches = [
            row
            for row in self._accepted_results(cut)
            if _same_ref(row["body"].get("assignment_ref"), job.assignment_ref)
        ]
        if len(matches) > 1:
            raise ValidationError("MULTIPLE_RESULTS_FOR_ASSIGNMENT", f"{self.stage_id}-{job.lane_slot}")
        return matches[0] if matches else None

    def _stage_spec_ref(self, cut: dict[str, Any]) -> dict[str, Any]:
        if not self.batch.jobs:
            raise ValidationError("STAGE_BATCH_EMPTY", self.stage_id)
        first = next(iter(self.batch.jobs.values()))
        assignment = self.store.resolve_accepted(first.assignment_ref, cut)["body"]
        ref = assignment.get("stage_spec_ref")
        if not isinstance(ref, dict):
            raise ValidationError("STAGE_SPEC_BINDING_MISSING", self.stage_id)
        return ref

    def _load_accepted_state_from_store(self) -> None:
        cut, _ = _current_cut(self.store)
        proposal_rows = self._accepted_results(cut)
        completions = tuple(self.store.accepted_records("lane_completion", cut))
        for slot, job in self.batch.jobs.items():
            accepted = self._accepted_result_for_job(job, cut)
            if accepted is None:
                continue
            body = accepted["body"]
            findings = body.get("findings") if isinstance(body.get("findings"), list) else []
            lane_completion_id = None
            completion_status = None
            for completion in completions:
                outputs = completion["body"].get("required_output_refs", [])
                if any(
                    isinstance(ref, dict) and ref.get("revision_digest") == accepted["ref"]["revision_digest"]
                    for ref in outputs
                ):
                    lane_completion_id = completion["body"].get("lane_completion_id")
                    completion_status = completion["body"].get("completion_predicate_result")
                    break
            self.lane_statuses[slot] = LaneInboxStatus(
                lane_slot=slot,
                status="ACCEPTED",
                result_digest=body.get("raw_result_digest"),
                findings_count=len(findings),
                findings=[dict(item) for item in findings if isinstance(item, dict)],
                lane_completion_id=lane_completion_id,
                result_proposal_ref=dict(accepted["ref"]),
                completion_status=completion_status,
            )

        stage_spec = self._stage_spec_ref(cut)
        stage_rows = [
            row
            for row in self.store.accepted_records("stage_completion", cut)
            if _same_ref(row["body"].get("stage_spec_ref"), stage_spec)
        ]
        if len(stage_rows) > 1:
            raise ValidationError("MULTIPLE_STAGE_COMPLETIONS", self.stage_id)
        if stage_rows and stage_rows[0]["body"].get("completion_predicate_result") == "STAGE_COMPLETED":
            self.stage_complete = True
            self.stage_completion_digest = stage_rows[0]["ref"]["revision_digest"]

    def _record_file_result(
        self,
        path: Path,
        lane_slot: str,
        status: str,
        code: str,
        reason: str | None,
        raw_digest: str | None,
        next_action: str | None,
    ) -> tuple[str, str, str | None]:
        self._last_file_result = ImportFileResult(
            path=str(path),
            lane_slot=lane_slot,
            status=status,
            code=code,
            reason=reason,
            raw_digest=raw_digest,
            next_action=next_action,
        )
        return lane_slot, status, reason

    def _reject(
        self,
        path: Path,
        lane_slot: str,
        code: str,
        detail: str,
        raw_digest: str | None,
        next_action: str = "CORRECT_AND_REIMPORT",
    ) -> tuple[str, str, str | None]:
        reason = f"{code}: {detail}" if detail else code
        return self._record_file_result(path, lane_slot, "REJECTED", code, reason, raw_digest, next_action)

    def _read_and_stage(self, path: Path) -> tuple[bytes, str, dict[str, bytes], list[dict[str, Any]]]:
        raw = path.read_bytes()
        receipt = self.vault.put_bytes(raw, media_type="application/zip")
        try:
            members = read_zip_bytes(raw, limits=_RESULT_ZIP_LIMITS)
        except ValidationError as exc:
            raise _translate_zip_error(exc) from exc
        evidence_files: list[dict[str, Any]] = []
        for name, data in sorted(members.items(), key=lambda item: item[0].encode("utf-8")):
            member_receipt = self.vault.put_bytes(data, media_type=_media_type(name))
            evidence_files.append({
                "path": name,
                "raw_digest": member_receipt.raw_digest,
                "byte_length": member_receipt.byte_length,
                "media_type": member_receipt.media_type,
            })
        return raw, receipt.raw_digest, members, evidence_files

    def ingest_zip(self, zip_path: Path | str) -> tuple[str, str, str | None]:
        path = Path(zip_path).resolve()
        self._last_file_result = None
        if not path.is_file():
            return self._reject(path, "UNKNOWN", "FILE_NOT_FOUND", f"File does not exist: {path}", None)

        raw_digest: str | None = None
        try:
            try:
                raw, raw_digest, members, evidence_files = self._read_and_stage(path)
            except ValidationError as exc:
                code = getattr(exc, "code", "ZIP_INTEGRITY_FAILURE")
                if code in {"ZIP_OPEN_FAILURE", "ZIP_INTEGRITY_FAILURE"}:
                    return self._reject(path, "UNKNOWN", "INVALID_ZIP", "not a valid ZIP archive", raw_digest)
                return self._reject(path, "UNKNOWN", code, str(exc), raw_digest)

            if "MANIFEST.json" not in members:
                return self._reject(path, "UNKNOWN", "MISSING_MANIFEST", "Archive lacks root MANIFEST.json", raw_digest)
            try:
                manifest = parse(members["MANIFEST.json"])
            except ValidationError as exc:
                return self._reject(path, "UNKNOWN", "MALFORMED_MANIFEST", str(exc), raw_digest)
            if not isinstance(manifest, dict):
                return self._reject(path, "UNKNOWN", "MALFORMED_MANIFEST", "MANIFEST.json root must be an object", raw_digest)
            if manifest.get("kind") != "bdb_audit_lane_result" or str(manifest.get("version", "")) != "1":
                return self._reject(path, "UNKNOWN", "INVALID_RESULT_CONTRACT", "Expected bdb_audit_lane_result/1", raw_digest)
            if manifest.get("campaign_id") != self.batch.campaign_id:
                return self._reject(path, "UNKNOWN", "FOREIGN_CAMPAIGN", "Result belongs to another campaign", raw_digest, "SELECT_CORRECT_CAMPAIGN")
            if manifest.get("stage_id") != self.stage_id:
                return self._reject(path, "UNKNOWN", "WRONG_STAGE", f"Expected {self.stage_id}, got {manifest.get('stage_id')}", raw_digest)

            slot = manifest.get("lane_slot")
            if slot not in self.batch.jobs:
                return self._reject(path, "UNKNOWN", "UNKNOWN_LANE", f"Invalid lane slot '{slot}'", raw_digest)
            job = self.batch.get_job(str(slot))

            source_sha = manifest.get("source_commit_sha")
            if not isinstance(source_sha, str) or source_sha.lower() != job.source_commit_sha.lower():
                return self._reject(path, str(slot), "SOURCE_COMMIT_MISMATCH", "Result source commit differs from assignment", raw_digest)

            result_cut = manifest.get("history_cut")
            expected_cut = job.input_history_cut
            if not isinstance(result_cut, dict):
                return self._reject(path, str(slot), "MISSING_MANDATORY_FIELD", "Manifest missing history_cut", raw_digest)
            for key, expected_value in expected_cut.items():
                if result_cut.get(key) != expected_value:
                    return self._reject(path, str(slot), "STALE_CUT", f"Result history_cut differs on {key}", raw_digest)

            if manifest.get("input_package_digest") != job.package_digest:
                return self._reject(path, str(slot), "PACKAGE_DIGEST_MISMATCH", "Result is not bound to this input package", raw_digest)
            if manifest.get("executor_profile") != job.executor_profile:
                return self._reject(path, str(slot), "EXECUTOR_PROFILE_MISMATCH", "Executor profile differs from assignment", raw_digest)
            if manifest.get("executor_model") != job.model:
                return self._reject(path, str(slot), "EXECUTOR_MODEL_MISMATCH", "Executor model differs from assignment", raw_digest)
            if not _same_ref(manifest.get("assignment_ref"), job.assignment_ref):
                return self._reject(path, str(slot), "ASSIGNMENT_REF_MISMATCH", "Result is bound to another assignment", raw_digest)
            if not _same_ref(manifest.get("attempt_ref"), job.attempt_ref):
                return self._reject(path, str(slot), "ATTEMPT_REF_MISMATCH", "Result is bound to another attempt", raw_digest)

            findings = manifest.get("findings")
            if not isinstance(findings, list):
                return self._reject(path, str(slot), "INVALID_FINDING_STRUCTURE", "findings must be a list", raw_digest)
            if "findings_count" in manifest and manifest["findings_count"] != len(findings):
                return self._reject(path, str(slot), "FINDINGS_COUNT_MISMATCH", "findings_count does not equal findings length", raw_digest)
            for index, finding in enumerate(findings):
                if not isinstance(finding, dict):
                    return self._reject(path, str(slot), "INVALID_FINDING_STRUCTURE", f"finding {index} is not an object", raw_digest)
                if not finding.get("statement") or not (finding.get("finding_id") or finding.get("title")):
                    return self._reject(path, str(slot), "INVALID_FINDING_STRUCTURE", f"finding {index} lacks statement/id", raw_digest)

            canonical_proposal = dict(manifest)
            canonical_proposal["history_cut"] = dict(expected_cut)
            canonical_proposal["findings"] = findings
            canonical_proposal["findings_count"] = len(findings)
            canonical_proposal["assignment_ref"] = dict(job.assignment_ref)
            canonical_proposal["attempt_ref"] = dict(job.attempt_ref)
            canonical_proposal["raw_result_digest"] = raw_digest
            canonical_proposal["raw_result_byte_length"] = len(raw)
            canonical_proposal["evidence_files"] = evidence_files
            LayeredValidator(registry=self.store.registry).validate(
                "bdb_audit_lane_result", canonical_bytes(canonical_proposal)
            )

            cut, _ = _current_cut(self.store)
            existing = self._accepted_result_for_job(job, cut)
            if existing is not None:
                if existing["body"].get("raw_result_digest") == raw_digest:
                    self._load_accepted_state_from_store()
                    return self._record_file_result(path, str(slot), "ACCEPTED", "EXACT_RETRY", None, raw_digest, None)
                return self._reject(path, str(slot), "CONFLICTING_RESULT_REJECTED", "Assignment already has a different accepted result", raw_digest, "CREATE_NEW_ATTEMPT")

            try:
                self._accept_result(job, canonical_proposal, findings, raw_digest)
            except ValidationError as exc:
                if getattr(exc, "code", "") != "EXPECTED_HEAD_CONFLICT":
                    raise
                cut, _ = _current_cut(self.store)
                existing = self._accepted_result_for_job(job, cut)
                if existing is None:
                    raise
                if existing["body"].get("raw_result_digest") != raw_digest:
                    return self._reject(path, str(slot), "CONFLICTING_RESULT_REJECTED", "Concurrent different result won acceptance", raw_digest, "CREATE_NEW_ATTEMPT")

            self._load_accepted_state_from_store()
            self.lane_statuses[str(slot)].result_zip_path = path
            return self._record_file_result(path, str(slot), "ACCEPTED", "ACCEPTED", None, raw_digest, None)
        except ValidationError as exc:
            return self._reject(path, "UNKNOWN", getattr(exc, "code", "VALIDATION_ERROR"), str(exc), raw_digest)
        except Exception as exc:
            return self._reject(path, "UNKNOWN", "UNEXPECTED_INGESTION_ERROR", type(exc).__name__, raw_digest, "REVIEW_IMPORT_ERROR")

    def _accept_result(
        self,
        job: StageLaneJob,
        proposal_body: dict[str, Any],
        findings: list[dict[str, Any]],
        raw_digest: str,
    ) -> None:
        cut, prior_commit = _current_cut(self.store)
        assignment_record = self.store.resolve_accepted(job.assignment_ref, cut)
        assignment = assignment_record["body"]
        if not _same_ref(assignment.get("attempt_ref"), job.attempt_ref):
            raise ValidationError("ASSIGNMENT_ATTEMPT_BINDING_MISMATCH")

        attempt_record = self.store.resolve_accepted(assignment["attempt_ref"], cut)
        lane_run_record = self.store.resolve_accepted(attempt_record["body"]["lane_run_ref"], cut)
        knowledge_record = self.store.resolve_accepted(assignment["knowledge_state_ref"], cut)
        isolation_record = self.store.resolve_accepted(knowledge_record["body"]["isolation_qualification_ref"], cut)
        lane_spec_record = self.store.resolve_accepted(assignment["lane_spec_ref"], cut)
        source_record = self.store.resolve_accepted(assignment["source_generation_ref"], cut)

        required_assurance = lane_spec_record["body"].get("required_isolation_assurance", "UNKNOWN")
        actual_assurance = isolation_record["body"].get("result", "UNKNOWN")
        ranks = {"UNKNOWN": 0, "DECLARED": 1, "ENFORCED": 2}
        isolation_sufficient = ranks.get(actual_assurance, -1) >= ranks.get(required_assurance, 99)

        proposal = CanonicalObject("bdb_audit_lane_result", proposal_body)
        objects: list[CanonicalObject] = [proposal]
        discoveries: list[CanonicalObject] = []
        for index, _finding in enumerate(findings):
            discovery = CanonicalObject("discovery_record", {
                "discovery_id": f"disc_{self.stage_id}_{job.lane_slot}_{proposal.digest[:12]}_{index + 1}",
                "lane_run_ref": _with_ref_class(lane_run_record["ref"], "PRIOR_ACCEPTED_ONLY"),
                "attempt_ref": _with_ref_class(attempt_record["ref"], "PRIOR_ACCEPTED_ONLY"),
                "source_generation_ref": _with_ref_class(source_record["ref"], "PRIOR_ACCEPTED_ONLY"),
                "discovery_input_history_cut": cut,
                "knowledge_state_ref": _with_ref_class(knowledge_record["ref"], "PRIOR_ACCEPTED_ONLY"),
                "method_ref": _external_ref("external_profile_ref", f"manual_external_{self.stage_id.lower()}", "HISTORY_CONTEXT_BINDING"),
                "producer_ref": _external_ref("actor_or_authority_ref", f"external_auditor_{self.stage_id}_{job.lane_slot}", "PRIOR_ACCEPTED_ONLY"),
                "surface_location_refs": [],
                "own_observation_refs": [],
            })
            discoveries.append(discovery)
            objects.append(discovery)

        lane_completion = LaneCompletion(
            lane_completion_id=deterministic_id(
                "lane_completion",
                f"{assignment_record['ref']['revision_digest']}:{proposal.digest}",
            ),
            lane_run_ref=_with_ref_class(lane_run_record["ref"], "CONTENT_OR_PRIOR"),
            lane_spec_ref=_with_ref_class(lane_spec_record["ref"], "HISTORY_CONTEXT_BINDING"),
            input_history_cut=cut,
            final_knowledge_state_ref=_with_ref_class(knowledge_record["ref"], "CONTENT_OR_PRIOR"),
            isolation_qualification_ref=_with_ref_class(isolation_record["ref"], "CONTENT_OR_PRIOR"),
            attempt_refs=[_with_ref_class(attempt_record["ref"], "CONTENT_OR_PRIOR")],
            required_output_refs=[proposal.as_ref().as_dict(), *[d.as_ref().as_dict() for d in discoveries]],
            completion_predicate_result="LANE_COMPLETED" if isolation_sufficient else "LANE_COMPLETION_BLOCKED",
        )
        objects.append(lane_completion.as_object())

        head = self.store.head()
        if head is None:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        command = CommandEnvelope(
            command_id=_command_id(f"result:{assignment_record['ref']['revision_digest']}:{raw_digest}"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit["governing_policy_ref"],
            governing_spec_refs=tuple(prior_commit.get("governing_spec_refs", ())),
            idempotency_scope=f"result:{assignment_record['ref']['revision_digest']}:{raw_digest}",
            campaign_ref=head.campaign_id,
        )
        self.coordinator.accept(command, immutable_objects=objects, expected_head=head)

    def ingest_multiple_zips(self, zip_paths: Sequence[Path | str]) -> ImportedResultSummary:
        reports: list[ImportFileResult] = []
        for zip_path in zip_paths:
            self.ingest_zip(zip_path)
            if self._last_file_result is not None:
                reports.append(self._last_file_result)

        self._load_accepted_state_from_store()
        accepted = [slot for slot, state in self.lane_statuses.items() if state.status == "ACCEPTED"]
        missing = [slot for slot, state in self.lane_statuses.items() if state.status != "ACCEPTED"]
        error: str | None = None
        if len(accepted) == len(self.batch.lane_slots) and not self.stage_complete:
            blocked = [slot for slot, state in self.lane_statuses.items() if state.completion_status != "LANE_COMPLETED"]
            if blocked:
                error = "STAGE_COMPLETION_BLOCKED: " + ", ".join(blocked)
            else:
                try:
                    self._finalize_stage_completion()
                except ValidationError as exc:
                    error = str(exc)

        return ImportedResultSummary(
            campaign_id=self.batch.campaign_id,
            stage_id=self.stage_id,
            total_required_lanes=len(self.batch.lane_slots),
            accepted_count=len(accepted),
            missing_lanes=missing,
            lane_statuses=dict(self.lane_statuses),
            stage_complete=self.stage_complete,
            completion_digest=self.stage_completion_digest,
            error=error,
            file_results=reports,
        )

    def _finalize_stage_completion(self) -> None:
        cut, prior_commit = _current_cut(self.store)
        required_completion_refs: list[dict[str, Any]] = []
        proposal_refs: list[dict[str, Any]] = []
        stage_run_digests: set[str] = set()
        stage_run_ref: dict[str, Any] | None = None
        stage_spec_ref: dict[str, Any] | None = None

        lane_completions = tuple(self.store.accepted_records("lane_completion", cut))
        for slot, job in self.batch.jobs.items():
            proposal = self._accepted_result_for_job(job, cut)
            if proposal is None:
                raise ValidationError("STAGE_COMPLETION_BLOCKED", f"Missing accepted result {slot}")
            completion = next(
                (
                    row
                    for row in lane_completions
                    if any(
                        isinstance(ref, dict) and ref.get("revision_digest") == proposal["ref"]["revision_digest"]
                        for ref in row["body"].get("required_output_refs", [])
                    )
                ),
                None,
            )
            if completion is None or completion["body"].get("completion_predicate_result") != "LANE_COMPLETED":
                raise ValidationError("STAGE_COMPLETION_BLOCKED", f"Lane {slot} is not qualified complete")
            required_completion_refs.append(_with_ref_class(completion["ref"], "CONTENT_OR_PRIOR"))
            proposal_refs.append(_with_ref_class(proposal["ref"], "CONTENT_OR_PRIOR"))

            assignment = self.store.resolve_accepted(job.assignment_ref, cut)["body"]
            attempt = self.store.resolve_accepted(assignment["attempt_ref"], cut)["body"]
            lane_run = self.store.resolve_accepted(attempt["lane_run_ref"], cut)["body"]
            current_stage_run_ref = lane_run["stage_run_ref"]
            stage_run_digests.add(current_stage_run_ref["revision_digest"])
            stage_run_ref = _with_ref_class(current_stage_run_ref, "CONTENT_OR_PRIOR")
            stage_spec_ref = _with_ref_class(assignment["stage_spec_ref"], "HISTORY_CONTEXT_BINDING")

        if len(stage_run_digests) != 1 or stage_run_ref is None or stage_spec_ref is None:
            raise ValidationError("STAGE_RUN_BINDING_CONFLICT", self.stage_id)

        stage_completion = StageCompletion(
            stage_completion_id=deterministic_id(
                "stage_completion",
                f"{self.stage_id}:" + ":".join(sorted(ref["revision_digest"] for ref in required_completion_refs)),
            ),
            stage_run_ref=stage_run_ref,
            stage_spec_ref=stage_spec_ref,
            input_history_cut=cut,
            required_lane_slot_results=required_completion_refs,
            required_output_refs=proposal_refs,
            mandatory_obligation_summary={
                "required_lanes": len(self.batch.lane_slots),
                "completed_lanes": len(required_completion_refs),
            },
            unresolved_material_refs=[],
            unknown_blocked_summary={"unknown_surfaces_count": 0},
            completion_predicate_result="STAGE_COMPLETED",
        )
        stage_obj = stage_completion.as_object()
        head = self.store.head()
        if head is None:
            raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
        command = CommandEnvelope(
            command_id=_command_id("stage_completion:" + stage_obj.digest),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit["governing_policy_ref"],
            governing_spec_refs=tuple(prior_commit.get("governing_spec_refs", ())),
            idempotency_scope="stage_completion:" + stage_obj.digest,
            campaign_ref=head.campaign_id,
        )
        self.coordinator.accept(command, immutable_objects=[stage_obj], expected_head=head)
        self.stage_complete = True
        self.stage_completion_digest = stage_obj.digest
        self._load_accepted_state_from_store()


__all__ = ["PostE1ResultInbox"]

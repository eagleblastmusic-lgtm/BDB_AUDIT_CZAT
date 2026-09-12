"""Durable, raw-first E1 result ingestion (RU03 / D02/D05/D06/D08/D19/G02).

The inbox treats every external ZIP as hostile transport. Exact bytes are staged
in a content-addressed vault before parsing. Strong ZIP validation runs on one
owned immutable snapshot. Semantic proposal content is then bound to the exact
pre-delivery AssignmentManifest and Attempt and accepted through Coordinator.

Acceptance of a result is distinct from claiming stronger isolation than the
assignment actually had. Manual ChatGPT transport remains DECLARED unless a
separate enforcement profile provides receipts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any, Sequence

from ..assurance.zip_safety import Limits as ZipLimits, read_bytes as read_zip_bytes
from ..coordinator import Coordinator
from ..core.canonical_json import canonical_bytes, parse
from ..core.errors import ValidationError
from ..core.ids import deterministic_id
from ..history.objects import CanonicalObject, CommandEnvelope, HistoryCut
from ..history.store import TransactionalHistoryStore
from ..orchestration.native_ensemble import E1_LANE_SLOTS, E1CompletionResult, execute_e1_ensemble
from ..schemas.foundation import F3_KINDS, foundation_schema_bindings
from ..schemas.identity import LayeredValidator
from ..stop.models import LaneCompletion, StageCompletion
from ..vault.raw_store import RawArtifactVault
from .packaging import E1Batch, E1LaneJob

_RESULT_ZIP_LIMITS = ZipLimits(
    input_bytes=64 * 1024 * 1024,
    central_bytes=4 * 1024 * 1024,
    members=512,
    member_bytes=32 * 1024 * 1024,
    expanded_bytes=50 * 1024 * 1024,
    ratio=500,
)


@dataclass
class LaneInboxStatus:
    lane_slot: str
    status: str  # ACCEPTED | MISSING | REJECTED
    result_zip_path: Path | None = None
    result_digest: str | None = None
    findings_count: int = 0
    findings: list[dict[str, Any]] = field(default_factory=list)
    rejection_reason: str | None = None
    lane_completion_id: str | None = None
    result_proposal_ref: dict[str, Any] | None = None
    completion_status: str | None = None


@dataclass(frozen=True)
class ImportFileResult:
    path: str
    lane_slot: str
    status: str
    code: str
    reason: str | None
    raw_digest: str | None
    next_action: str | None


@dataclass
class ImportedResultSummary:
    campaign_id: str
    stage_id: str
    total_required_lanes: int
    accepted_count: int
    missing_lanes: list[str]
    lane_statuses: dict[str, LaneInboxStatus]
    stage_complete: bool = False
    completion_digest: str | None = None
    error: str | None = None
    file_results: list[ImportFileResult] = field(default_factory=list)


def _command_id(seed: str) -> str:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"command_{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"


def _external_ref(kind: str, value: str, ref_class: str = "CONTENT_OR_PRIOR") -> dict[str, Any]:
    preimage = f"BDB2/{kind}/1\0".encode("ascii") + canonical_bytes({"reference_id": value})
    return {
        "kind": kind,
        "revision_digest": hashlib.sha256(preimage).hexdigest(),
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_TARGET/{kind}",
        "ref_class": ref_class,
    }


def _with_ref_class(ref: dict[str, Any], ref_class: str) -> dict[str, Any]:
    result = dict(ref)
    result["ref_class"] = ref_class
    return result


def _same_ref(left: Any, right: Any) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    keys = ("kind", "revision_digest", "schema_revision_ref")
    return all(left.get(key) == right.get(key) for key in keys)


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
    return (
        HistoryCut.accepted(head, body["governing_policy_ref"], body["governing_spec_refs"]).as_dict(),
        body,
    )


def _media_type(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".json"):
        return "application/json"
    if lower.endswith((".md", ".txt", ".log")):
        return "text/plain"
    if lower.endswith(".xml"):
        return "application/xml"
    return "application/octet-stream"


def _translate_zip_error(exc: ValidationError) -> ValidationError:
    code = getattr(exc, "code", "ZIP_INTEGRITY_FAILURE")
    if code == "UNSAFE_ZIP_PATH":
        return ValidationError("ZIP_PATH_TRAVERSAL", str(exc))
    if code in {"DUPLICATE_ZIP_MEMBER_NAMES", "ZIP_NORMALIZED_PATH_COLLISION"}:
        return ValidationError("ZIP_DUPLICATE_PATH", str(exc))
    if code == "ZIP_RESOURCE_LIMIT":
        return ValidationError("ZIP_BOMB_LIMIT_EXCEEDED", str(exc))
    return exc


class E1ResultInbox:
    """Strict result staging, validation, durable acceptance, and restart recovery."""

    def __init__(self, store: TransactionalHistoryStore, e1_batch: E1Batch):
        self.store = store
        self.batch = e1_batch
        result_kinds = tuple(dict.fromkeys((*F3_KINDS, "bdb_audit_lane_result")))
        self.store.schemas = foundation_schema_bindings(kinds=result_kinds)
        self.coordinator = Coordinator(store)
        self.vault = RawArtifactVault(Path(store.path).resolve().parent / "raw_vault")
        self.lane_statuses: dict[str, LaneInboxStatus] = {
            slot: LaneInboxStatus(lane_slot=slot, status="MISSING") for slot in E1_LANE_SLOTS
        }
        self.stage_complete = False
        self.stage_completion_digest: str | None = None
        self.e1_completion_result: E1CompletionResult | None = None
        self._last_file_result: ImportFileResult | None = None
        self._load_accepted_state_from_store()

    def _accepted_results(self, cut: dict[str, Any]) -> tuple[dict[str, Any], ...]:
        return tuple(self.store.accepted_records("bdb_audit_lane_result", cut))

    def _accepted_result_for_job(self, job: E1LaneJob, cut: dict[str, Any]) -> dict[str, Any] | None:
        matches = [
            row for row in self._accepted_results(cut)
            if _same_ref(row["body"].get("assignment_ref"), job.assignment_ref)
        ]
        if len(matches) > 1:
            raise ValidationError("MULTIPLE_RESULTS_FOR_ASSIGNMENT")
        return matches[0] if matches else None

    def _load_accepted_state_from_store(self) -> None:
        """Rebuild state only from verified accepted closure at the current cut."""
        cut, _ = _current_cut(self.store)
        for slot, job in self.batch.jobs.items():
            accepted = self._accepted_result_for_job(job, cut)
            if accepted is None:
                continue
            body = accepted["body"]
            findings = body.get("findings") if isinstance(body.get("findings"), list) else []
            lane_completion_id = None
            completion_status = None
            for completion in self.store.accepted_records("lane_completion", cut):
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

        stage_rows = tuple(self.store.accepted_records("stage_completion", cut))
        completed = [row for row in stage_rows if row["body"].get("completion_predicate_result") == "STAGE_COMPLETED"]
        if len(completed) > 1:
            raise ValidationError("MULTIPLE_STAGE_COMPLETIONS")
        if completed:
            self.stage_complete = True
            self.stage_completion_digest = completed[0]["ref"]["revision_digest"]

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
            path=str(path), lane_slot=lane_slot, status=status, code=code,
            reason=reason, raw_digest=raw_digest, next_action=next_action,
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
        evidence: list[dict[str, Any]] = []
        for name, data in sorted(members.items(), key=lambda item: item[0].encode("utf-8")):
            member_receipt = self.vault.put_bytes(data, media_type=_media_type(name))
            evidence.append({
                "path": name,
                "raw_digest": member_receipt.raw_digest,
                "byte_length": member_receipt.byte_length,
                "media_type": member_receipt.media_type,
            })
        return raw, receipt.raw_digest, members, evidence

    def ingest_zip(self, zip_path: Path | str) -> tuple[str, str, str | None]:
        """Stage raw bytes, validate proposal, and accept one result idempotently."""
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
                return self._reject(path, "UNKNOWN", "MALFORMED_MANIFEST", f"Corrupted MANIFEST.json: {exc}", raw_digest)
            if not isinstance(manifest, dict):
                return self._reject(path, "UNKNOWN", "MALFORMED_MANIFEST", "MANIFEST.json root must be a JSON object", raw_digest)

            if manifest.get("kind") != "bdb_audit_lane_result":
                return self._reject(path, "UNKNOWN", "INVALID_CONTRACT_KIND", f"Manifest declares kind '{manifest.get('kind')}'", raw_digest)
            if str(manifest.get("version", "")) != "1":
                return self._reject(path, "UNKNOWN", "INVALID_CONTRACT_VERSION", "Expected version '1'", raw_digest)
            if not manifest.get("campaign_id"):
                return self._reject(path, "UNKNOWN", "MISSING_MANDATORY_FIELD", "Manifest missing campaign_id", raw_digest)
            if manifest.get("campaign_id") != self.batch.campaign_id:
                return self._reject(
                    path, "UNKNOWN", "FOREIGN_CAMPAIGN",
                    f"Manifest campaign_id '{manifest.get('campaign_id')}' does not match active campaign '{self.batch.campaign_id}'",
                    raw_digest, "SELECT_CORRECT_CAMPAIGN",
                )
            if manifest.get("stage_id") != "E1":
                return self._reject(path, "UNKNOWN", "WRONG_STAGE", f"Expected E1, got {manifest.get('stage_id')}", raw_digest)

            slot = manifest.get("lane_slot")
            if slot not in E1_LANE_SLOTS:
                return self._reject(path, "UNKNOWN", "UNKNOWN_LANE", f"Invalid lane slot '{slot}'", raw_digest)
            job = self.batch.get_job(slot)

            source_sha = manifest.get("source_commit_sha")
            if not source_sha:
                return self._reject(path, slot, "MISSING_SOURCE_BINDING", "Manifest missing source_commit_sha", raw_digest)
            if source_sha.lower() != job.source_commit_sha.lower():
                return self._reject(path, slot, "SOURCE_COMMIT_MISMATCH", "Result is bound to a different source commit", raw_digest)

            result_cut = manifest.get("history_cut")
            expected_cut = self.batch.frozen_history_cut
            if not isinstance(result_cut, dict):
                return self._reject(path, slot, "MISSING_MANDATORY_FIELD", "Manifest missing history_cut", raw_digest)
            if any(result_cut.get(key) != expected_cut.get(key) for key in ("campaign_id", "accepted_head_seq", "accepted_head_hash")):
                return self._reject(path, slot, "STALE_CUT", "Result does not match the assignment input cut", raw_digest)
            for key, expected_value in expected_cut.items():
                if key in result_cut and result_cut[key] != expected_value:
                    return self._reject(path, slot, "STALE_CUT", f"Result history_cut conflicts on {key}", raw_digest)

            package_digest = manifest.get("input_package_digest")
            if not package_digest:
                return self._reject(path, slot, "MISSING_INPUT_PACKAGE_DIGEST", "Manifest missing input_package_digest", raw_digest)
            if package_digest != job.package_digest:
                return self._reject(path, slot, "PACKAGE_DIGEST_MISMATCH", "Result is not bound to the semantic input package", raw_digest)

            if manifest.get("executor_profile") != job.executor_profile:
                return self._reject(path, slot, "EXECUTOR_PROFILE_MISMATCH", "Executor profile differs from assignment", raw_digest)
            if manifest.get("executor_model") != job.model:
                return self._reject(path, slot, "EXECUTOR_MODEL_MISMATCH", "Executor model differs from assignment", raw_digest)

            if manifest.get("assignment_ref") is not None and not _same_ref(manifest.get("assignment_ref"), job.assignment_ref):
                return self._reject(path, slot, "ASSIGNMENT_REF_MISMATCH", "Result is bound to another assignment", raw_digest)
            if manifest.get("attempt_ref") is not None and not _same_ref(manifest.get("attempt_ref"), job.attempt_ref):
                return self._reject(path, slot, "ATTEMPT_REF_MISMATCH", "Result is bound to another attempt", raw_digest)

            findings: list[dict[str, Any]]
            if "findings" in manifest:
                if not isinstance(manifest["findings"], list):
                    return self._reject(path, slot, "INVALID_FINDING_STRUCTURE", "findings must be a list", raw_digest)
                findings = manifest["findings"]
            elif "FINDINGS.json" in members:
                try:
                    parsed_findings = parse(members["FINDINGS.json"])
                except ValidationError as exc:
                    return self._reject(path, slot, "INVALID_FINDING_STRUCTURE", str(exc), raw_digest)
                if not isinstance(parsed_findings, list):
                    return self._reject(path, slot, "INVALID_FINDING_STRUCTURE", "FINDINGS.json must be a list", raw_digest)
                findings = parsed_findings
            else:
                return self._reject(path, slot, "MISSING_MANDATORY_FIELD", "Result must contain findings", raw_digest)

            if "findings_count" in manifest and manifest["findings_count"] != len(findings):
                return self._reject(path, slot, "FINDINGS_COUNT_MISMATCH", "findings_count does not equal findings length", raw_digest)
            for index, finding in enumerate(findings):
                if not isinstance(finding, dict):
                    return self._reject(path, slot, "INVALID_FINDING_STRUCTURE", f"finding {index} is not an object", raw_digest)
                if not finding.get("statement") or not (finding.get("finding_id") or finding.get("title")):
                    return self._reject(path, slot, "INVALID_FINDING_STRUCTURE", f"finding {index} lacks statement/id", raw_digest)

            canonical_proposal = dict(manifest)
            canonical_proposal["history_cut"] = dict(expected_cut)
            canonical_proposal["findings"] = findings
            canonical_proposal["findings_count"] = len(findings)
            canonical_proposal["assignment_ref"] = dict(job.assignment_ref)
            canonical_proposal["attempt_ref"] = dict(job.attempt_ref)
            canonical_proposal["raw_result_digest"] = raw_digest
            canonical_proposal["raw_result_byte_length"] = len(raw)
            canonical_proposal["evidence_files"] = evidence_files

            try:
                LayeredValidator(registry=self.store.registry).validate(
                    "bdb_audit_lane_result", canonical_bytes(canonical_proposal)
                )
            except ValidationError as exc:
                return self._reject(path, slot, "SCHEMA_VALIDATION_FAILED", str(exc), raw_digest)

            cut, _ = _current_cut(self.store)
            existing = self._accepted_result_for_job(job, cut)
            if existing is not None:
                if existing["body"].get("raw_result_digest") == raw_digest:
                    self._load_accepted_state_from_store()
                    return self._record_file_result(path, slot, "ACCEPTED", "EXACT_RETRY", None, raw_digest, None)
                return self._reject(
                    path, slot, "CONFLICTING_RESULT_REJECTED",
                    "This assignment already has a different accepted result; create an explicit new attempt",
                    raw_digest, "CREATE_NEW_ATTEMPT",
                )

            try:
                lane_completion_id = self._accept_result(
                    slot=slot, job=job, proposal_body=canonical_proposal,
                    findings=findings, raw_digest=raw_digest,
                )
            except ValidationError as exc:
                if getattr(exc, "code", "") != "EXPECTED_HEAD_CONFLICT":
                    raise
                cut, _ = _current_cut(self.store)
                existing = self._accepted_result_for_job(job, cut)
                if existing is not None:
                    if existing["body"].get("raw_result_digest") == raw_digest:
                        self._load_accepted_state_from_store()
                        return self._record_file_result(path, slot, "ACCEPTED", "EXACT_RETRY", None, raw_digest, None)
                    return self._reject(
                        path, slot, "CONFLICTING_RESULT_REJECTED",
                        "Concurrent different result won the assignment acceptance race",
                        raw_digest, "CREATE_NEW_ATTEMPT",
                    )
                lane_completion_id = self._accept_result(
                    slot=slot, job=job, proposal_body=canonical_proposal,
                    findings=findings, raw_digest=raw_digest,
                )

            self._load_accepted_state_from_store()
            self.lane_statuses[slot].result_zip_path = path
            self.lane_statuses[slot].lane_completion_id = lane_completion_id
            return self._record_file_result(path, slot, "ACCEPTED", "ACCEPTED", None, raw_digest, None)
        except ValidationError as exc:
            return self._reject(path, "UNKNOWN", getattr(exc, "code", "VALIDATION_ERROR"), str(exc), raw_digest)
        except Exception as exc:
            return self._reject(path, "UNKNOWN", "UNEXPECTED_INGESTION_ERROR", type(exc).__name__, raw_digest, "REVIEW_IMPORT_ERROR")

    def _accept_result(
        self,
        *,
        slot: str,
        job: E1LaneJob,
        proposal_body: dict[str, Any],
        findings: list[dict[str, Any]],
        raw_digest: str,
    ) -> str:
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

        # DiscoveryRecord and LaneCompletion are different consumers and their
        # canonical contracts require different ref classes for the same facts.
        lane_run_prior_ref = _with_ref_class(lane_run_record["ref"], "PRIOR_ACCEPTED_ONLY")
        attempt_prior_ref = _with_ref_class(attempt_record["ref"], "PRIOR_ACCEPTED_ONLY")
        knowledge_prior_ref = _with_ref_class(knowledge_record["ref"], "PRIOR_ACCEPTED_ONLY")
        source_prior_ref = _with_ref_class(source_record["ref"], "PRIOR_ACCEPTED_ONLY")

        lane_run_content_ref = _with_ref_class(lane_run_record["ref"], "CONTENT_OR_PRIOR")
        attempt_content_ref = _with_ref_class(attempt_record["ref"], "CONTENT_OR_PRIOR")
        knowledge_content_ref = _with_ref_class(knowledge_record["ref"], "CONTENT_OR_PRIOR")
        isolation_content_ref = _with_ref_class(isolation_record["ref"], "CONTENT_OR_PRIOR")
        lane_spec_ref = _with_ref_class(lane_spec_record["ref"], "HISTORY_CONTEXT_BINDING")

        required_assurance = lane_spec_record["body"].get("required_isolation_assurance", "UNKNOWN")
        actual_assurance = isolation_record["body"].get("result", "UNKNOWN")
        ranks = {"UNKNOWN": 0, "DECLARED": 1, "ENFORCED": 2}
        isolation_sufficient = ranks.get(actual_assurance, -1) >= ranks.get(required_assurance, 99)

        proposal = CanonicalObject("bdb_audit_lane_result", proposal_body)
        objects: list[CanonicalObject] = [proposal]
        discoveries: list[CanonicalObject] = []
        for index, _finding in enumerate(findings):
            discovery = CanonicalObject("discovery_record", {
                "discovery_id": f"disc_E1_{slot}_{proposal.digest[:12]}_{index + 1}",
                "lane_run_ref": lane_run_prior_ref,
                "attempt_ref": attempt_prior_ref,
                "source_generation_ref": source_prior_ref,
                "discovery_input_history_cut": cut,
                "knowledge_state_ref": knowledge_prior_ref,
                "method_ref": _external_ref("external_profile_ref", "manual_external_audit", "HISTORY_CONTEXT_BINDING"),
                "producer_ref": _external_ref("actor_or_authority_ref", f"external_auditor_{slot}", "PRIOR_ACCEPTED_ONLY"),
                "surface_location_refs": [],
                "own_observation_refs": [],
            })
            discoveries.append(discovery)
            objects.append(discovery)

        output_refs = [proposal.as_ref().as_dict(), *[discovery.as_ref().as_dict() for discovery in discoveries]]
        completion_result = "LANE_COMPLETED" if isolation_sufficient else "LANE_COMPLETION_BLOCKED"
        lane_completion_id = deterministic_id(
            "lane_completion",
            f"{assignment_record['ref']['revision_digest']}:{proposal.digest}",
        )
        lane_completion = LaneCompletion(
            lane_completion_id=lane_completion_id,
            lane_run_ref=lane_run_content_ref,
            lane_spec_ref=lane_spec_ref,
            input_history_cut=cut,
            final_knowledge_state_ref=knowledge_content_ref,
            isolation_qualification_ref=isolation_content_ref,
            attempt_refs=[attempt_content_ref],
            required_output_refs=output_refs,
            completion_predicate_result=completion_result,
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
        return lane_completion_id

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

        if len(accepted) == len(E1_LANE_SLOTS) and not self.stage_complete:
            blocked = [slot for slot, state in self.lane_statuses.items() if state.completion_status != "LANE_COMPLETED"]
            if blocked:
                error = "STAGE_COMPLETION_BLOCKED: " + ", ".join(blocked)
            else:
                try:
                    self._finalize_e1_stage_completion()
                except ValidationError as exc:
                    error = str(exc)

        return ImportedResultSummary(
            campaign_id=self.batch.campaign_id,
            stage_id="E1",
            total_required_lanes=len(E1_LANE_SLOTS),
            accepted_count=len(accepted),
            missing_lanes=missing,
            lane_statuses=dict(self.lane_statuses),
            stage_complete=self.stage_complete,
            completion_digest=self.stage_completion_digest,
            error=error,
            file_results=reports,
        )

    def _finalize_e1_stage_completion(self) -> None:
        cut, prior_commit = _current_cut(self.store)
        lane_completions = tuple(self.store.accepted_records("lane_completion", cut))
        proposal_rows = self._accepted_results(cut)

        completion_by_assignment: dict[str, dict[str, Any]] = {}
        for completion in lane_completions:
            outputs = completion["body"].get("required_output_refs", [])
            for proposal in proposal_rows:
                if any(
                    isinstance(ref, dict) and ref.get("revision_digest") == proposal["ref"]["revision_digest"]
                    for ref in outputs
                ):
                    assignment_digest = proposal["body"].get("assignment_ref", {}).get("revision_digest")
                    if assignment_digest:
                        completion_by_assignment[assignment_digest] = completion

        required_completion_refs: list[dict[str, Any]] = []
        proposal_refs: list[dict[str, Any]] = []
        stage_run_digests: set[str] = set()
        stage_run_ref: dict[str, Any] | None = None
        stage_spec_ref: dict[str, Any] | None = None
        lane_discoveries: dict[str, list[dict]] = {}

        for slot in E1_LANE_SLOTS:
            job = self.batch.get_job(slot)
            completion = completion_by_assignment.get(job.assignment_ref.get("revision_digest"))
            if completion is None or completion["body"].get("completion_predicate_result") != "LANE_COMPLETED":
                raise ValidationError("STAGE_COMPLETION_BLOCKED", f"Missing completed lane {slot}")
            required_completion_refs.append(_with_ref_class(completion["ref"], "CONTENT_OR_PRIOR"))

            proposal = self._accepted_result_for_job(job, cut)
            if proposal is None:
                raise ValidationError("STAGE_COMPLETION_BLOCKED", f"Missing accepted result {slot}")
            proposal_refs.append(_with_ref_class(proposal["ref"], "CONTENT_OR_PRIOR"))
            lane_discoveries[slot] = [dict(finding) for finding in proposal["body"].get("findings", []) if isinstance(finding, dict)]

            assignment = self.store.resolve_accepted(job.assignment_ref, cut)["body"]
            attempt = self.store.resolve_accepted(assignment["attempt_ref"], cut)["body"]
            lane_run = self.store.resolve_accepted(attempt["lane_run_ref"], cut)["body"]
            current_stage_run_ref = lane_run["stage_run_ref"]
            stage_run_digests.add(current_stage_run_ref["revision_digest"])
            stage_run_ref = _with_ref_class(current_stage_run_ref, "CONTENT_OR_PRIOR")
            stage_spec_ref = _with_ref_class(assignment["stage_spec_ref"], "HISTORY_CONTEXT_BINDING")

        if len(stage_run_digests) != 1 or stage_run_ref is None or stage_spec_ref is None:
            raise ValidationError("STAGE_RUN_BINDING_CONFLICT")

        stage_completion = StageCompletion(
            stage_completion_id=deterministic_id(
                "stage_completion",
                ":".join(sorted(ref["revision_digest"] for ref in required_completion_refs)),
            ),
            stage_run_ref=stage_run_ref,
            stage_spec_ref=stage_spec_ref,
            input_history_cut=cut,
            required_lane_slot_results=required_completion_refs,
            required_output_refs=proposal_refs,
            mandatory_obligation_summary={"required_lanes": len(E1_LANE_SLOTS), "completed_lanes": len(required_completion_refs)},
            unresolved_material_refs=[],
            unknown_blocked_summary={"unknown_surfaces_count": 0},
            completion_predicate_result="STAGE_COMPLETED",
        )
        stage_obj = stage_completion.as_object()

        first_assignment = self.store.resolve_accepted(self.batch.get_job("E1-A").assignment_ref, cut)["body"]
        source_ref = self.store.resolve_accepted(first_assignment["source_generation_ref"], cut)["ref"]
        self.e1_completion_result = execute_e1_ensemble(source_ref, lane_discoveries)

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


__all__ = ["LaneInboxStatus", "ImportFileResult", "ImportedResultSummary", "E1ResultInbox"]

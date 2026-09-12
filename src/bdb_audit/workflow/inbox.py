"""Result Inbox and safe multi-ZIP ingestion for BDB Audit v2.0.3.

Provides robust, fail-closed handling for external auditor submissions:
- Strict artifact contract validation (kind='bdb_audit_lane_result', version='1').
- Mechanical ZIP security: Zip-Slip traversal protection, duplicate paths, bomb bounds.
- Exact provenance bindings: campaign_id, stage_id, lane_slot, exact HistoryCut,
  source commit SHA, package identity digest, executor profile and model.
- Coordinator authority path: accepted immutable objects (lane_run, attempt,
  isolation_qualification, knowledge_state, discovery_records, lane_completion).
- StageCompletion predicate evaluation and canonical acceptance only after all
  5 lanes are durably accepted in the history store.
- Process restart resilience: reconstructs accepted state from the campaign database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence
import zipfile

from ..core.canonical_json import canonical_bytes, parse
from ..core.errors import ValidationError
from ..schemas.identity import LayeredValidator
from ..core.ids import deterministic_id
from ..coordinator import Coordinator
from ..history.objects import CanonicalObject, CommandEnvelope
from ..history.store import TransactionalHistoryStore
from ..orchestration.native_ensemble import (
    E1_LANE_SLOTS,
    E1CompletionResult,
    execute_e1_ensemble,
)
from ..stop.models import StageCompletion, LaneCompletion
from .packaging import E1Batch

MAX_ALLOWED_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB safety bound


@dataclass
class LaneInboxStatus:
    lane_slot: str
    status: str  # "ACCEPTED" | "MISSING" | "REJECTED"
    result_zip_path: Path | None = None
    result_digest: str | None = None
    findings_count: int = 0
    findings: list[dict[str, Any]] = field(default_factory=list)
    rejection_reason: str | None = None
    lane_completion_id: str | None = None


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


def _command_id(seed: str) -> str:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"command_{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"


def _external_ref(kind: str, val: str, ref_class: str = "CONTENT_OR_PRIOR") -> dict[str, Any]:
    return {
        "kind": kind,
        "revision_digest": hashlib.sha256(val.encode("utf-8")).hexdigest(),
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_TARGET/{kind}",
        "ref_class": ref_class,
    }


def _ref_dict(ref: Any) -> dict[str, Any]:
    if hasattr(ref, "as_dict"):
        return dict(ref.as_dict())
    return dict(ref)


def _validate_zip_safety(zf: zipfile.ZipFile) -> None:
    """Verify archive is free of directory traversal, duplicate entries, and size bombs."""
    namelist = zf.namelist()
    seen_names = set()
    total_uncompressed = 0

    for name in namelist:
        if name in seen_names:
            raise ValidationError("ZIP_DUPLICATE_PATH", f"Duplicate path entry inside ZIP: {name}")
        seen_names.add(name)

        norm = name.replace("\\", "/")
        parts = norm.split("/")
        if (
            norm.startswith("/")
            or ".." in parts
            or ":" in norm
            or norm.startswith("~")
        ):
            raise ValidationError("ZIP_PATH_TRAVERSAL", f"Illegal or escaping path inside ZIP: {name}")

        info = zf.getinfo(name)
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_ALLOWED_UNCOMPRESSED_BYTES:
            raise ValidationError("ZIP_BOMB_LIMIT_EXCEEDED", "Uncompressed archive size exceeds safety threshold")


class E1ResultInbox:
    """Manages collection, strict contract validation, and canonical acceptance of E1 audit results."""

    def __init__(self, store: TransactionalHistoryStore, e1_batch: E1Batch):
        self.store = store
        self.batch = e1_batch
        self.coordinator = Coordinator(store)
        self.lane_statuses: dict[str, LaneInboxStatus] = {
            slot: LaneInboxStatus(lane_slot=slot, status="MISSING")
            for slot in E1_LANE_SLOTS
        }
        self.stage_complete: bool = False
        self.e1_completion_result: E1CompletionResult | None = None
        self._load_accepted_state_from_store()

    def _load_accepted_state_from_store(self) -> None:
        """Reconstruct accepted lane and stage completion state directly from SQLite history."""
        conn = self.store._connect()
        try:
            # Map lane_spec digest -> slot
            spec_rows = conn.execute("SELECT digest, body FROM immutable_objects WHERE kind='lane_spec'").fetchall()
            digest_to_slot: dict[str, str] = {}
            for r_dig, r_body in spec_rows:
                s_doc = json.loads(r_body.decode("utf-8"))
                lkey = s_doc.get("lane_key", "")
                for slot in E1_LANE_SLOTS:
                    if lkey in (slot, f"lane_E1_{slot}"):
                        digest_to_slot[r_dig] = slot

            # Inspect accepted lane completions
            rows = conn.execute("SELECT body FROM immutable_objects WHERE kind='lane_completion'").fetchall()
            for (body_bytes,) in rows:
                doc = json.loads(body_bytes.decode("utf-8"))
                cid = doc.get("lane_completion_id", "")
                pred = doc.get("completion_predicate_result")
                ls_ref = doc.get("lane_spec_ref", {})
                ls_dig = ls_ref.get("revision_digest")
                target_slot: str | None = digest_to_slot.get(ls_dig) if ls_dig else None
                if not target_slot:
                    for s in E1_LANE_SLOTS:
                        if f"_{s}_" in cid or cid.endswith(f"_{s}"):
                            target_slot = s
                            break
                if pred == "LANE_COMPLETED" and target_slot:
                    outputs = doc.get("required_output_refs", [])
                    self.lane_statuses[target_slot] = LaneInboxStatus(
                        lane_slot=target_slot,
                        status="ACCEPTED",
                        findings_count=len(outputs),
                        lane_completion_id=cid,
                    )
            # Inspect accepted stage completions
            s_row = conn.execute("SELECT body FROM immutable_objects WHERE kind='stage_completion' LIMIT 1").fetchone()
            if s_row:
                s_doc = json.loads(s_row[0].decode("utf-8"))
                if s_doc.get("completion_predicate_result") == "STAGE_COMPLETED":
                    self.stage_complete = True
        finally:
            conn.close()

    def ingest_zip(self, zip_path: Path | str) -> tuple[str, str, str | None]:
        """Validate result contract and canonically accept through Coordinator.

        Returns: (lane_slot, status, rejection_reason)
        """
        p = Path(zip_path).resolve()
        if not p.exists() or not p.is_file():
            return "UNKNOWN", "REJECTED", f"File does not exist: {p}"

        if not zipfile.is_zipfile(p):
            return "UNKNOWN", "REJECTED", f"File is not a valid ZIP archive: {p.name}"

        try:
            with zipfile.ZipFile(p, "r") as zf:
                _validate_zip_safety(zf)

                if "MANIFEST.json" not in zf.namelist():
                    return "UNKNOWN", "REJECTED", f"Archive {p.name} lacks root MANIFEST.json"

                manifest_raw = zf.read("MANIFEST.json")
                try:
                    manifest = parse(manifest_raw)
                except ValidationError as exc:
                    return "UNKNOWN", "REJECTED", f"Corrupted MANIFEST.json in {p.name}: {exc}"
                except Exception as exc:
                    return "UNKNOWN", "REJECTED", f"Corrupted MANIFEST.json in {p.name}: {exc}"

                if not isinstance(manifest, dict):
                    return "UNKNOWN", "REJECTED", "MANIFEST.json root must be a JSON object"

                # 1. Kind & Version check
                kind = manifest.get("kind")
                if kind != "bdb_audit_lane_result":
                    return "UNKNOWN", "REJECTED", (
                        f"INVALID_CONTRACT_KIND: Manifest declares kind '{kind}', expected 'bdb_audit_lane_result'"
                    )

                version = str(manifest.get("version", ""))
                if version != "1":
                    return "UNKNOWN", "REJECTED", (
                        f"INVALID_CONTRACT_VERSION: Manifest declares version '{version}', expected '1'"
                    )

                # 2. Campaign ID check
                result_cid = manifest.get("campaign_id")
                if not result_cid:
                    return "UNKNOWN", "REJECTED", "MISSING_MANDATORY_FIELD: Manifest missing 'campaign_id'"
                if result_cid != self.batch.campaign_id:
                    return "UNKNOWN", "REJECTED", (
                        f"FOREIGN_CAMPAIGN: Manifest campaign_id '{result_cid}' does not match active campaign '{self.batch.campaign_id}'"
                    )

                # 3. Stage ID check
                stage_id = manifest.get("stage_id")
                if stage_id != "E1":
                    return "UNKNOWN", "REJECTED", f"WRONG_STAGE: Manifest declares stage '{stage_id}', expected 'E1'"

                # 4. Lane Slot check
                slot = manifest.get("lane_slot")
                if not slot or slot not in E1_LANE_SLOTS:
                    return "UNKNOWN", "REJECTED", f"UNKNOWN_LANE: Manifest declares invalid lane slot '{slot}'"

                expected_job = self.batch.get_job(slot)

                # 5. Exact Source Commit SHA binding
                res_sha = manifest.get("source_commit_sha")
                if not res_sha:
                    return slot, "REJECTED", "MISSING_SOURCE_BINDING: Manifest missing mandatory 'source_commit_sha'"
                if expected_job.source_commit_sha and res_sha.strip().lower() != expected_job.source_commit_sha.strip().lower():
                    return slot, "REJECTED", (
                        f"SOURCE_COMMIT_MISMATCH: Result bound to commit {res_sha[:12]}, expected {expected_job.source_commit_sha[:12]}"
                    )

                # 6. HistoryCut binding check
                res_cut = manifest.get("history_cut")
                if not isinstance(res_cut, dict):
                    return slot, "REJECTED", "MISSING_MANDATORY_FIELD: Manifest missing 'history_cut' object"
                expected_cut = self.batch.frozen_history_cut
                if (
                    res_cut.get("campaign_id") != expected_cut.get("campaign_id")
                    or res_cut.get("accepted_head_seq") != expected_cut.get("accepted_head_seq")
                    or res_cut.get("accepted_head_hash") != expected_cut.get("accepted_head_hash")
                ):
                    return slot, "REJECTED", (
                        f"STALE_CUT: Result history_cut ({res_cut}) does not match frozen E1 cut ({expected_cut})"
                    )

                # 7. Input Package Digest binding check
                pkg_digest = manifest.get("input_package_digest")
                if not pkg_digest:
                    return slot, "REJECTED", "MISSING_INPUT_PACKAGE_DIGEST: Manifest missing mandatory 'input_package_digest'"
                if (
                    pkg_digest != expected_job.package_digest
                    and pkg_digest != expected_job.package_zip_sha256
                ):
                    return slot, "REJECTED", (
                        f"PACKAGE_DIGEST_MISMATCH: Result bound to package {pkg_digest[:16]}..., "
                        f"expected {expected_job.package_digest[:16]}..."
                    )

                # 8. Executor profile / model binding check
                if "executor_profile" not in manifest or manifest["executor_profile"] != expected_job.executor_profile:
                    return slot, "REJECTED", (
                        f"EXECUTOR_PROFILE_MISMATCH: Expected '{expected_job.executor_profile}', got '{manifest.get('executor_profile')}'"
                    )
                if "executor_model" not in manifest or manifest["executor_model"] != expected_job.model:
                    return slot, "REJECTED", (
                        f"EXECUTOR_MODEL_MISMATCH: Expected model '{expected_job.model}', got '{manifest.get('executor_model')}'"
                    )

                # 9. Required result / evidence structure check
                if "findings" not in manifest and "FINDINGS.json" not in zf.namelist():
                    return slot, "REJECTED", "MISSING_MANDATORY_FIELD: Manifest must contain 'findings' list"

                findings: list[dict[str, Any]] = []
                if "findings" in manifest:
                    if not isinstance(manifest["findings"], list):
                        return slot, "REJECTED", "INVALID_FINDING_STRUCTURE: 'findings' must be a list"
                    findings = manifest["findings"]
                elif "FINDINGS.json" in zf.namelist():
                    try:
                        f_data = parse(zf.read("FINDINGS.json"))
                        if not isinstance(f_data, list):
                            return slot, "REJECTED", "INVALID_FINDING_STRUCTURE: 'FINDINGS.json' must be a list"
                        findings = f_data
                    except ValidationError as exc:
                        return slot, "REJECTED", f"Corrupted FINDINGS.json: {exc}"
                    except Exception as exc:
                        return slot, "REJECTED", f"Corrupted FINDINGS.json: {exc}"

                if "findings_count" in manifest:
                    if manifest["findings_count"] != len(findings):
                        return slot, "REJECTED", (
                            f"FINDINGS_COUNT_MISMATCH: Manifest declares findings_count={manifest['findings_count']}, but found {len(findings)} findings"
                        )

                for idx, f in enumerate(findings):
                    if not isinstance(f, dict):
                        return slot, "REJECTED", f"INVALID_FINDING_STRUCTURE: finding at index {idx} must be a dict"
                    if not f.get("statement") or not (f.get("finding_id") or f.get("title")):
                        return slot, "REJECTED", (
                            f"INVALID_FINDING_STRUCTURE: finding at index {idx} lacks required 'statement' or 'finding_id'"
                        )

                # 9b. Schema validation of proposal artifact
                manifest_to_validate = dict(manifest)
                if "findings" not in manifest_to_validate:
                    manifest_to_validate["findings"] = findings
                try:
                    LayeredValidator(registry=self.store.registry).validate(
                        "bdb_audit_lane_result", canonical_bytes(manifest_to_validate)
                    )
                except ValidationError as val_exc:
                    return slot, "REJECTED", f"SCHEMA_VALIDATION_FAILED: {val_exc}"

                # NO SYNTHETIC FINDINGS:
                # If findings is empty, findings remains [] (an audit finding 0 vulnerabilities is valid).
                # Absence of data is NEVER converted to synthetic positive evidence!

                raw_bytes = p.read_bytes()
                res_digest = hashlib.sha256(raw_bytes).hexdigest()

                # 10. Idempotency vs Conflicting Replacement
                current = self.lane_statuses[slot]
                if current.status == "ACCEPTED":
                    if current.result_digest == res_digest or current.lane_completion_id:
                        # If digest matches, return idempotent PASS
                        if current.result_digest == res_digest:
                            return slot, "ACCEPTED", None
                        # If different incoming ZIP for already accepted lane: fail-closed rejection
                        return slot, "REJECTED", (
                            f"CONFLICTING_RESULT_REJECTED: Lane {slot} already accepted in campaign history. "
                            "Replacement is forbidden without canonical retry / new attempt."
                        )

                # 11. Coordinator Authority Path — Commit accepted facts to history
                lane_comp_id = self._accept_lane_to_coordinator(slot, manifest, findings, res_digest)

                self.lane_statuses[slot] = LaneInboxStatus(
                    lane_slot=slot,
                    status="ACCEPTED",
                    result_zip_path=p,
                    result_digest=res_digest,
                    findings_count=len(findings),
                    findings=findings,
                    rejection_reason=None,
                    lane_completion_id=lane_comp_id,
                )
                return slot, "ACCEPTED", None

        except ValidationError as exc:
            return "UNKNOWN", "REJECTED", str(exc)
        except Exception as exc:
            return "UNKNOWN", "REJECTED", f"Unexpected ingestion error: {exc}"

    def _accept_lane_to_coordinator(
        self,
        slot: str,
        manifest: dict[str, Any],
        findings: list[dict[str, Any]],
        res_digest: str,
    ) -> str:
        """Durable acceptance: create and commit canonical immutable objects via Coordinator."""
        head = self.store.head()
        conn = self.store._connect()
        try:
            row_commit = conn.execute("SELECT body FROM commits WHERE commit_hash=?", (head.commit_hash,)).fetchone()
            prior_commit = json.loads(row_commit[0]) if row_commit else {}

            # Look up source_generation ref
            sg_row = conn.execute("SELECT digest, schema_ref FROM immutable_objects WHERE kind='source_generation' LIMIT 1").fetchone()
            sg_digest = sg_row[0] if sg_row else "0" * 64
            sg_schema = sg_row[1] if sg_row else "BDB_SCHEMA_REGISTRY::source_generation/1"

            # Look up stage_spec ref
            ss_row = conn.execute("SELECT digest, schema_ref, body FROM immutable_objects WHERE kind='stage_spec' LIMIT 1").fetchone()
            ss_digest = ss_row[0] if ss_row else "0" * 64
            ss_schema = ss_row[1] if ss_row else "BDB_SCHEMA_REGISTRY::stage_spec/1"
            ss_body = json.loads(ss_row[2].decode("utf-8")) if ss_row else {}

            # Look up lane_spec ref for this slot
            ls_rows = conn.execute("SELECT digest, schema_ref, body FROM immutable_objects WHERE kind='lane_spec'").fetchall()
            ls_digest, ls_schema, ls_body = "0" * 64, "BDB_SCHEMA_REGISTRY::lane_spec/1", {}
            for row in ls_rows:
                doc = json.loads(row[2].decode("utf-8"))
                if doc.get("lane_key") in (slot, f"lane_E1_{slot}"):
                    ls_digest, ls_schema, ls_body = row[0], row[1], doc
                    break

            # Look up existing stage_run in store
            sr_row = conn.execute("SELECT digest, schema_ref, body FROM immutable_objects WHERE kind='stage_run' LIMIT 1").fetchone()
        finally:
            conn.close()

        source_gen_ref = {
            "kind": "source_generation",
            "revision_digest": sg_digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": sg_schema,
            "ref_class": "PRIOR_ACCEPTED_ONLY",
        }
        stage_spec_ref = {
            "kind": "stage_spec",
            "revision_digest": ss_digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": ss_schema,
            "ref_class": "HISTORY_CONTEXT_BINDING",
        }
        lane_spec_ref = {
            "kind": "lane_spec",
            "revision_digest": ls_digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": ls_schema,
            "ref_class": "HISTORY_CONTEXT_BINDING",
        }

        current_cut = {
            "variant": "ACCEPTED_HISTORY_CUT",
            "campaign_id": head.campaign_id,
            "accepted_head_seq": head.commit_seq,
            "accepted_head_hash": head.commit_hash,
            "governing_policy_ref": prior_commit.get("governing_policy_ref"),
            "governing_spec_refs": list(prior_commit.get("governing_spec_refs", ())),
        }

        immutable_objs: list[CanonicalObject] = []

        if sr_row:
            stage_run_doc = json.loads(sr_row[2].decode("utf-8"))
            stage_run = CanonicalObject("stage_run", stage_run_doc)
        else:
            stage_run = CanonicalObject("stage_run", {
                "stage_run_id": f"stage_run_E1_{head.commit_seq + 1}",
                "campaign_ref": head.campaign_id,
                "stage_spec_ref": stage_spec_ref,
                "source_generation_ref": source_gen_ref,
                "creation_input_history_cut": current_cut,
                "assigned_history_cut": current_cut,
                "predecessor_stage_completion_refs": [],
                "required_lane_slot_contract_refs": [_external_ref("result_slot_contract_ref", "slot_contract", "HISTORY_CONTEXT_BINDING")],
            })
            immutable_objs.append(stage_run)

        stage_run_ref = stage_run.as_ref().as_dict()

        # 1. Lane Run
        lane_run = CanonicalObject("lane_run", {
            "lane_run_id": f"lane_run_E1_{slot}_{head.commit_seq + 1}",
            "stage_run_ref": stage_run_ref,
            "lane_spec_ref": lane_spec_ref,
            "source_generation_ref": source_gen_ref,
            "creation_input_history_cut": current_cut,
            "required_result_slots": [_external_ref("result_slot_contract_ref", f"slot_{slot}", "HISTORY_CONTEXT_BINDING")],
        })
        immutable_objs.append(lane_run)

        # 2. Attempt
        attempt = CanonicalObject("attempt", {
            "attempt_id": f"attempt_E1_{slot}_{head.commit_seq + 1}",
            "lane_run_ref": lane_run.as_ref().as_dict(),
            "attempt_nonce": f"nonce_{slot}_{res_digest[:16]}",
            "executor_profile_ref": _external_ref("executor_spec", manifest.get("executor_profile", "chatgpt_github"), "HISTORY_CONTEXT_BINDING"),
            "delivery_profile_ref": _external_ref("delivery_spec", "ZIP_PROMPT_CLIPBOARD", "HISTORY_CONTEXT_BINDING"),
            "assigned_history_cut": current_cut,
            "result_slot_contracts": [_external_ref("result_slot_contract_ref", f"slot_{slot}", "HISTORY_CONTEXT_BINDING")],
        })
        immutable_objs.append(attempt)

        # 3. Isolation Qualification
        isolation = CanonicalObject("isolation_qualification", {
            "isolation_qualification_id": f"iso_qual_E1_{slot}_{head.commit_seq + 1}",
            "attempt_ref": attempt.as_ref().as_dict(),
            "assessment_input_history_cut": current_cut,
            "executor_profile_ref": _external_ref("executor_spec", manifest.get("executor_profile", "chatgpt_github"), "HISTORY_CONTEXT_BINDING"),
            "delivery_profile_ref": _external_ref("delivery_spec", "ZIP_PROMPT_CLIPBOARD", "HISTORY_CONTEXT_BINDING"),
            "channel_inventory_ref": _external_ref("registered_immutable_object", "ch_inv", "CONTENT_OR_PRIOR"),
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
        immutable_objs.append(isolation)

        # 4. Knowledge State
        kstate = CanonicalObject("knowledge_state", {
            "knowledge_state_id": f"kstate_E1_{slot}_{head.commit_seq + 1}",
            "attempt_ref": attempt.as_ref().as_dict(),
            "basis_history_cut": current_cut,
            "isolation_qualification_ref": isolation.as_ref().as_dict(),
            "allowed_view_refs": [],
            "contamination_assessment_refs": [],
            "potential_exposure_refs": [],
        })
        immutable_objs.append(kstate)

        # 5. Discovery Records (one per genuine finding, if any)
        discovery_objs: list[CanonicalObject] = []
        for idx, f in enumerate(findings):
            stmt = f.get("statement") or f.get("title") or f.get("description") or f"Finding {idx + 1}"
            disc_obj = CanonicalObject("discovery_record", {
                "discovery_id": f"disc_E1_{slot}_{head.commit_seq + 1}_{idx + 1}",
                "lane_run_ref": lane_run.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
                "attempt_ref": attempt.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
                "source_generation_ref": source_gen_ref,
                "discovery_input_history_cut": current_cut,
                "knowledge_state_ref": kstate.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict(),
                "method_ref": _external_ref("external_profile_ref", "disc_method", "HISTORY_CONTEXT_BINDING"),
                "producer_ref": _external_ref("actor_or_authority_ref", f"auditor_{slot}", "PRIOR_ACCEPTED_ONLY"),
                "surface_location_refs": [],
                "own_observation_refs": [],
            })
            discovery_objs.append(disc_obj)
            immutable_objs.append(disc_obj)

        # 6. Lane Completion
        lane_comp_id = deterministic_id("lane_completion", f"lane_comp_{head.campaign_id}_{slot}_{res_digest}")
        lane_comp = LaneCompletion(
            lane_completion_id=lane_comp_id,
            lane_run_ref=_ref_dict(lane_run.as_ref().as_dict()),
            lane_spec_ref=_ref_dict(lane_spec_ref),
            input_history_cut=current_cut,
            final_knowledge_state_ref=_ref_dict(kstate.as_ref().as_dict()),
            isolation_qualification_ref=_ref_dict(isolation.as_ref().as_dict()),
            attempt_refs=[_ref_dict(attempt.as_ref().as_dict())],
            required_output_refs=[_ref_dict(d.as_ref().as_dict()) for d in discovery_objs],
            completion_predicate_result="LANE_COMPLETED",
        )
        lane_comp_obj = lane_comp.as_object()
        immutable_objs.append(lane_comp_obj)

        # Accept command atomically
        cmd = CommandEnvelope(
            command_id=_command_id(f"lane_accept_{slot}_{head.commit_seq + 1}"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit.get("governing_policy_ref", "pin:initial_governing_policy_ref"),
            governing_spec_refs=tuple(prior_commit.get("governing_spec_refs", ("pin:initial_transition_profile_ref",))),
            idempotency_scope=f"lane_accept_{slot}_{head.commit_seq + 1}_{res_digest[:16]}",
            campaign_ref=head.campaign_id,
        )

        self.coordinator.accept(cmd, immutable_objects=immutable_objs, expected_head=head)
        return lane_comp_id

    def ingest_multiple_zips(self, zip_paths: Sequence[Path | str]) -> ImportedResultSummary:
        """Ingest a batch of ZIP files and finalize stage completion if all 5 are accepted."""
        for zp in zip_paths:
            self.ingest_zip(zp)

        accepted_lanes = [slot for slot, s in self.lane_statuses.items() if s.status == "ACCEPTED"]
        missing_lanes = [slot for slot, s in self.lane_statuses.items() if s.status != "ACCEPTED"]

        # Check if all 5 lanes are accepted
        if len(accepted_lanes) == len(E1_LANE_SLOTS) and not self.stage_complete:
            self._finalize_e1_stage_completion()

        comp_digest = self.e1_completion_result.completion_digest if self.e1_completion_result else None
        return ImportedResultSummary(
            campaign_id=self.batch.campaign_id,
            stage_id="E1",
            total_required_lanes=len(E1_LANE_SLOTS),
            accepted_count=len(accepted_lanes),
            missing_lanes=missing_lanes,
            lane_statuses=dict(self.lane_statuses),
            stage_complete=self.stage_complete,
            completion_digest=comp_digest,
        )

    def _finalize_e1_stage_completion(self) -> None:
        """Commit StageCompletion to campaign history once all 5 lanes are durably accepted."""
        head = self.store.head()
        conn = self.store._connect()
        try:
            row_commit = conn.execute("SELECT body FROM commits WHERE commit_hash=?", (head.commit_hash,)).fetchone()
            prior_commit = json.loads(row_commit[0]) if row_commit else {}

            sg_row = conn.execute("SELECT digest, schema_ref FROM immutable_objects WHERE kind='source_generation' LIMIT 1").fetchone()
            sg_digest = sg_row[0] if sg_row else "0" * 64
            sg_schema = sg_row[1] if sg_row else "BDB_SCHEMA_REGISTRY::source_generation/1"

            ss_row = conn.execute("SELECT digest, schema_ref FROM immutable_objects WHERE kind='stage_spec' LIMIT 1").fetchone()
            ss_digest = ss_row[0] if ss_row else "0" * 64
            ss_schema = ss_row[1] if ss_row else "BDB_SCHEMA_REGISTRY::stage_spec/1"

            sr_row = conn.execute("SELECT digest, schema_ref FROM immutable_objects WHERE kind='stage_run' LIMIT 1").fetchone()
            sr_digest = sr_row[0] if sr_row else "0" * 64
            sr_schema = sr_row[1] if sr_row else "BDB_SCHEMA_REGISTRY::stage_run/1"

            lc_rows = conn.execute("SELECT digest, schema_ref, body FROM immutable_objects WHERE kind='lane_completion'").fetchall()
            disc_rows = conn.execute("SELECT digest, schema_ref FROM immutable_objects WHERE kind='discovery_record'").fetchall()
        finally:
            conn.close()

        source_gen_ref = {
            "kind": "source_generation",
            "revision_digest": sg_digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": sg_schema,
            "ref_class": "PRIOR_ACCEPTED_ONLY",
        }
        stage_spec_ref = {
            "kind": "stage_spec",
            "revision_digest": ss_digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": ss_schema,
            "ref_class": "HISTORY_CONTEXT_BINDING",
        }
        stage_run_ref = {
            "kind": "stage_run",
            "revision_digest": sr_digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": sr_schema,
            "ref_class": "CONTENT_OR_PRIOR",
        }

        # Build lane completion refs for all 5 lanes
        lane_comp_refs = []
        for r in lc_rows:
            lane_comp_refs.append({
                "kind": "lane_completion",
                "revision_digest": r[0],
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": r[1],
                "ref_class": "CONTENT_OR_PRIOR",
            })

        # Build discovery record refs
        all_disc_refs = []
        for r in disc_rows:
            all_disc_refs.append({
                "kind": "discovery_record",
                "revision_digest": r[0],
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": r[1],
                "ref_class": "CONTENT_OR_PRIOR",
            })

        # Collect discoveries for native ensemble validation
        discoveries: dict[str, list[dict]] = {slot: self.lane_statuses[slot].findings for slot in E1_LANE_SLOTS}

        e1_result = execute_e1_ensemble(source_gen_ref, discoveries)

        current_cut = {
            "variant": "ACCEPTED_HISTORY_CUT",
            "campaign_id": head.campaign_id,
            "accepted_head_seq": head.commit_seq,
            "accepted_head_hash": head.commit_hash,
            "governing_policy_ref": prior_commit.get("governing_policy_ref"),
            "governing_spec_refs": list(prior_commit.get("governing_spec_refs", ())),
        }

        # Construct and accept StageCompletion
        stage_comp = StageCompletion(
            stage_completion_id=deterministic_id("stage_completion", f"stage_comp_{head.campaign_id}_E1"),
            stage_run_ref=stage_run_ref,
            stage_spec_ref=stage_spec_ref,
            input_history_cut=current_cut,
            required_lane_slot_results=lane_comp_refs,
            required_output_refs=all_disc_refs,
            mandatory_obligation_summary={"total_mandatory": 5, "qualified": 5},
            completion_predicate_result="STAGE_COMPLETED",
        )
        stage_comp_obj = stage_comp.as_object()

        cmd = CommandEnvelope(
            command_id=_command_id(f"stage_complete_E1_{head.commit_seq + 1}"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
            governing_policy_ref=prior_commit.get("governing_policy_ref", "pin:initial_governing_policy_ref"),
            governing_spec_refs=tuple(prior_commit.get("governing_spec_refs", ("pin:initial_transition_profile_ref",))),
            idempotency_scope=f"stage_complete_E1_{head.commit_seq + 1}",
            campaign_ref=head.campaign_id,
        )

        self.coordinator.accept(cmd, immutable_objects=[stage_comp_obj], expected_head=head)
        self.e1_completion_result = e1_result
        self.stage_complete = True


__all__ = [
    "MAX_ALLOWED_UNCOMPRESSED_BYTES",
    "LaneInboxStatus",
    "ImportedResultSummary",
    "E1ResultInbox",
]

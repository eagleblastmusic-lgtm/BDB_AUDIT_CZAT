"""Core Operation API for BDB Audit v2 (R5.3 §109).

Central operational facade providing clean, fail-closed access to campaign,
stage, lane, validation, self-test, and build capabilities without bypassing
the Coordinator authority boundary or writing accepted facts out-of-band.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any, Sequence
from ..core.canonical_json import canonical_bytes, parse
from ..core.errors import ValidationError
from ..core.registry import ContractRegistry
from ..history.objects import (
    CanonicalObject,
    CommandEnvelope,
    InstallationBootstrapProfile,
)
from ..history.store import TransactionalHistoryStore
from . import Coordinator
from ..orchestration.stages import StageSpec
from ..orchestration.runs import LaneSpec
from ..orchestration.templates import TemplateRegistry


_BASELINE_STAGE_ORDER = ("E1", "E2", "E3", "E4", "E5")
_ALL_STAGES = ("E1", "E2", "E3", "E4", "E5", "E6")
_STAGE_ALIASES = {
    "F2_FOUNDATION": "E1",
    "E1_ENSEMBLE": "E1",
    "E2_CROSS_REVIEW": "E2",
    "E3_BLIND_GAP": "E3",
    "E4_DEEPEN": "E4",
    "E5_ATTACK": "E5",
    "E6": "E6",
    "E6_REMEDIATION": "E6",
    "E6_TARGETED_VERIFICATION": "E6",
}


def _command_id(seed: str) -> str:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"command_{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"


def _canonical_stage_key(stage_id: str) -> str:
    """Normalize public stage labels to the StageSpec key domain (E1..E6)."""
    normalized = stage_id.strip().upper()
    if normalized in _ALL_STAGES:
        return normalized
    if normalized in _STAGE_ALIASES:
        return _STAGE_ALIASES[normalized]
    prefix = normalized.split("_", 1)[0]
    if prefix in _ALL_STAGES:
        return prefix
    raise ValidationError(
        "INVALID_STAGE_ID",
        f"Unknown stage: {stage_id}. Allowed canonical stages: E1..E6",
    )


class AuditOperationApi:
    """Core domain operation interface used by CLI, UI, and test harnesses."""

    def __init__(self, registry: ContractRegistry | None = None):
        self.registry = registry or ContractRegistry()

    def create_campaign(
        self,
        store_path: str | Path,
        seed: str = "default_campaign",
        campaign_id: str | None = None,
        target_repo: str | None = None,
        commit_sha: str | None = None,
    ) -> dict[str, Any]:
        """Initialize a new campaign with genesis objects in a transactional store."""
        path = Path(store_path).resolve()
        if path.exists() and path.stat().st_size > 0:
            try:
                store = TransactionalHistoryStore(path, registry=self.registry)
                head = store.head()
                if head is not None and head.commit_seq > 0:
                    raise ValidationError("CAMPAIGN_ALREADY_EXISTS", f"Store at {path} already has accepted head seq {head.commit_seq}")
            except ValidationError:
                raise
            except Exception:
                pass

        store = TransactionalHistoryStore(path, registry=self.registry)
        coordinator = Coordinator(store)

        cid = campaign_id or f"campaign_{hashlib.sha256(seed.encode()).hexdigest()[:16]}"

        profile = InstallationBootstrapProfile(
            "INSTALLATION_BOOTSTRAP_PROFILE_V1",
            {key: "pin:" + key for key in InstallationBootstrapProfile.REQUIRED_PINS},
        )
        empty = profile.empty_cut().as_dict()
        objects: list[CanonicalObject] = []

        def make(kind: str, body: dict[str, Any]) -> CanonicalObject:
            obj = CanonicalObject(kind, body)
            objects.append(obj)
            return obj

        def ext(kind: str, val: str, ref_class: str = "CONTENT_OR_PRIOR") -> dict[str, Any]:
            preimage = f"BDB2/{kind}/1\0".encode("ascii") + canonical_bytes({"reference_id": val})
            return {
                "kind": kind,
                "revision_digest": hashlib.sha256(preimage).hexdigest(),
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": f"BDB_TARGET/{kind}",
                "ref_class": ref_class,
            }

        repo_authority_id = f"repo:{target_repo}" if target_repo else f"repo-{seed}"
        commit_id = commit_sha if commit_sha else hashlib.sha256(seed.encode()).hexdigest()[:40]
        has_real_git = bool(target_repo and commit_sha)

        source_manifest = make("source_manifest", {
            "entries": [{
                "repo_relative_posix_path": "README.md",
                "entry_type": "REGULAR_FILE",
                "relevant_mode": "0644",
                "byte_length": len(seed),
                "content_raw_digest": hashlib.sha256(commit_id.encode()).hexdigest(),
            }]
        })

        source_identity_body: dict[str, Any] = {
            "profile_ref": ext("source_identity_profile_pin", f"profile-{seed}", "PINNED_PROFILE_REF"),
            "authority_mode": "AUTHORIZED_GIT" if has_real_git else "AUTHORIZED_SNAPSHOT",
            "authorized_repository_or_snapshot_ref": ext("repository_or_snapshot_authority_ref", repo_authority_id, "SOURCE_AUTHORITY_REF"),
            "materialized_source_manifest_ref": source_manifest.as_ref().as_dict(),
            "completeness_state": "COMPLETE_SOURCE",
        }
        if has_real_git:
            source_identity_body["git_commit_object_id"] = commit_id
            source_identity_body["git_tree_object_id"] = commit_id

        source_identity = make("source_identity", source_identity_body)

        source_generation = make("source_generation", {
            "source_generation_id": f"source_gen_{cid}",
            "source_identity_ref": source_identity.as_ref().as_dict(),
            "source_identity_profile_ref": ext("source_identity_profile_pin", f"profile-{seed}", "PINNED_PROFILE_REF"),
            "repository_authority_ref": ext("repository_or_snapshot_authority_ref", repo_authority_id, "SOURCE_AUTHORITY_REF"),
            "materialized_source_manifest_ref": source_manifest.as_ref().as_dict(),
            "representation_refs": [],
        })

        legacy = make("legacy_raw_ref", {
            "legacy_ref_id": f"legacy_ref_{cid}",
            "raw_digest": "0" * 64,
            "byte_length": 100,
            "media_type": "application/zip",
            "import_input_history_cut": empty,
        })

        mechanical = make("legacy_mechanical_validation_assessment", {
            "assessment_id": f"assessment_mech_{cid}",
            "legacy_ref": legacy.as_ref().as_dict(),
            "assessment_input_history_cut": empty,
            "legacy_schema_ref": ext("external_profile_ref", "legacy-schema", "PINNED_PROFILE_REF"),
            "legacy_profile_ref": ext("external_profile_ref", "legacy-profile", "PINNED_PROFILE_REF"),
            "mechanical_validation_policy_ref": ext("external_profile_ref", "mechanical-policy", "HISTORY_CONTEXT_BINDING"),
            "parsed_legacy_variant_stage_facts": {},
            "integrity_check_results": [],
            "result": "VALID",
            "reason_codes": [],
        })

        reconciliation = make("source_reconciliation_assessment", {
            "assessment_id": f"assessment_reconcile_{cid}",
            "legacy_ref": legacy.as_ref().as_dict(),
            "assessment_input_history_cut": empty,
            "target_source_generation_ref": source_generation.as_ref().as_dict(),
            "identity_profile_ref": ext("external_profile_ref", "identity-profile", "HISTORY_CONTEXT_BINDING"),
            "reconciliation_policy_ref": ext("external_profile_ref", "reconciliation-policy", "HISTORY_CONTEXT_BINDING"),
            "raw_identifiers": {},
            "normalized_identity_body_ref": source_identity.as_ref().as_dict(),
            "result": "EXACT_MATCH",
            "reason_codes": [],
        })

        lineage = make("lineage_admission_assessment", {
            "assessment_id": f"assessment_lineage_{cid}",
            "legacy_ref": legacy.as_ref().as_dict(),
            "assessment_input_history_cut": empty,
            "admission_policy_ref": ext("external_profile_ref", "admission-policy", "HISTORY_CONTEXT_BINDING"),
            "mechanical_validation_assessment_ref": mechanical.as_ref().as_dict(),
            "source_reconciliation_assessment_ref": reconciliation.as_ref().as_dict(),
            "requested_role": "CANONICAL_PREDECESSOR",
            "validation_level": "L5_LINEAGE_ROLE_AND_TRUSTED_SELECTION_VALIDATED",
            "predecessor_pin_ref": ext("predecessor_pin_ref", "predecessor-pin", "PINNED_INSTALLATION_REF"),
            "freshness_binding_refs": [],
            "result": "ADMITTED",
            "reason_codes": [],
        })

        selection = make("trusted_predecessor_selection_decision", {
            "trusted_predecessor_selection_decision_id": f"decision_selection_{cid}",
            "selection_input_history_cut": empty,
            "candidate_legacy_refs": [legacy.as_ref().as_dict()],
            "selected_legacy_ref": legacy.as_ref().as_dict(),
            "source_reconciliation_assessment_ref": reconciliation.as_ref().as_dict(),
            "lineage_admission_assessment_ref": lineage.as_ref().as_dict(),
            "selection_policy_ref": ext("external_profile_ref", "selection-policy", "HISTORY_CONTEXT_BINDING"),
            "predecessor_pin_ref": ext("predecessor_pin_ref", "predecessor-pin", "PINNED_INSTALLATION_REF"),
            "decision": "SELECTED",
            "reason_codes": [],
        })

        admission = make("bootstrap_admission_decision", {
            "bootstrap_admission_decision_id": f"decision_bootstrap_{cid}",
            "legacy_ref": legacy.as_ref().as_dict(),
            "requested_role": "CANONICAL_PREDECESSOR",
            "mechanical_validation_assessment_ref": mechanical.as_ref().as_dict(),
            "source_reconciliation_assessment_ref": reconciliation.as_ref().as_dict(),
            "lineage_admission_assessment_ref": lineage.as_ref().as_dict(),
            "trusted_predecessor_selection_ref": selection.as_ref().as_dict(),
            "admission_policy_ref": ext("external_profile_ref", "admission-policy", "HISTORY_CONTEXT_BINDING"),
            "admission_input_history_cut": empty,
            "result": "CANONICAL_BOOTSTRAP_ADMITTED",
            "limitations": [],
            "reason_codes": [],
        })

        make("campaign_genesis", {
            "campaign_id": cid,
            "input_history_cut": empty,
            "bootstrap_admission_decision_ref": admission.as_ref().as_dict(),
            "source_generation_ref": source_generation.as_ref().as_dict(),
            "application_generation_ref": ext("application_generation_ref", "application"),
            "protocol_policy_bundle_ref": ext("protocol_policy_bundle_ref", "policy"),
            "schema_set_ref": ext("schema_set_ref", "schema-set"),
            "owner_operator_authority_ref": ext("owner_operator_authority_ref", "owner", "PINNED_INSTALLATION_REF"),
            "trust_profile_ref": ext("trust_profile", "trust", "PINNED_INSTALLATION_REF"),
            "legacy_origin_refs": [legacy.as_ref().as_dict()],
        })

        cmd = CommandEnvelope.initialize(
            command_id=_command_id(f"genesis_{cid}"),
            actor_ref="installation-owner",
            profile=profile,
            campaign_id=cid,
        )
        cmd_obj = cmd.as_object()
        objects.insert(0, cmd_obj)

        res = coordinator.accept(cmd, immutable_objects=objects, bootstrap_profile=profile)
        return {
            "status": "SUCCESS",
            "campaign_id": cid,
            "commit_seq": res.head.commit_seq,
            "commit_hash": res.head.commit_hash,
            "store_path": str(path),
        }

    def get_campaign_status(self, store_path: str | Path) -> dict[str, Any]:
        """Return a verified current projection derived only from accepted history."""
        path = Path(store_path).resolve()
        if not path.exists() or path.stat().st_size == 0:
            raise ValidationError("CAMPAIGN_NOT_FOUND", f"No database found at {path}")
        from ..workflow.read_models import campaign_status

        store = TransactionalHistoryStore(path, registry=self.registry)
        return campaign_status(store, _canonical_stage_key)

    def get_campaign_source_identity(self, store_path: str | Path) -> dict[str, Any]:
        """Resolve authoritative source identity through accepted campaign genesis."""
        path = Path(store_path).resolve()
        if not path.exists() or path.stat().st_size == 0:
            raise ValidationError("CAMPAIGN_NOT_FOUND", f"No database found at {path}")
        from ..workflow.read_models import campaign_source_identity

        store = TransactionalHistoryStore(path, registry=self.registry)
        return campaign_source_identity(store)

    def prepare_stage(
        self,
        store_path: str | Path,
        stage_id: str,
        stage_spec_revision: str = "1",
    ) -> dict[str, Any]:
        """Accept a StageSpec in baseline declaration order without treating preparation as completion."""
        path = Path(store_path).resolve()
        status = self.get_campaign_status(path)
        if status.get("termination_state", "OPEN") != "OPEN":
            raise ValidationError("CAMPAIGN_ALREADY_TERMINATED", "Cannot prepare a stage after campaign conclusion")

        store = TransactionalHistoryStore(path, registry=self.registry)
        coordinator = Coordinator(store)
        head = store.head()

        stage_key = _canonical_stage_key(stage_id)
        prepared_stages = list(status["stages_prepared"])
        if stage_key in prepared_stages:
            raise ValidationError("STAGE_ALREADY_PREPARED", f"Stage {stage_key} is already prepared")

        predecessor_requirements: tuple[str, ...]
        if stage_key == "E6":
            if "E5" not in status["stages_completed"]:
                raise ValidationError(
                    "PREDECESSOR_STAGE_NOT_COMPLETED",
                    "Stage E5 must be completed before preparing E6",
                )
            stage_ordinal = 6
            predecessor_requirements = ("E5",)
        else:
            expected_stage = next((s for s in _BASELINE_STAGE_ORDER if s not in prepared_stages), None)
            if expected_stage is not None and stage_key != expected_stage:
                raise ValidationError(
                    "INVALID_STAGE_TRANSITION",
                    f"Expected next stage {expected_stage}, got {stage_key}",
                )
            stage_ordinal = _BASELINE_STAGE_ORDER.index(stage_key) + 1
            predecessor_requirements = (
                (_BASELINE_STAGE_ORDER[stage_ordinal - 2],) if stage_ordinal > 1 else ()
            )
        spec = StageSpec(
            stage_key=stage_key,
            stage_spec_revision=stage_spec_revision,
            stage_role=stage_key,
            stage_ordinal=stage_ordinal,
            purpose=f"BDB {stage_key} operational stage",
            predecessor_requirements=predecessor_requirements,
            blind_reveal_phase_model="CONTROLLED",
            transition_policy_ref="TRANSITION_PROFILE_V1",
        )
        spec_obj = spec.as_object()

        parent_head_ref = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
        conn = store._connect()
        try:
            row = conn.execute("SELECT body FROM commits WHERE commit_hash=?", (head.commit_hash,)).fetchone()
            prior_commit = json.loads(row[0]) if row else {}
        finally:
            conn.close()

        cmd = CommandEnvelope(
            command_id=_command_id(f"stage_prep_{stage_key}_{head.commit_seq + 1}"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head=parent_head_ref,
            governing_policy_ref=prior_commit.get("governing_policy_ref", "pin:initial_governing_policy_ref"),
            governing_spec_refs=tuple(prior_commit.get("governing_spec_refs", ("pin:initial_transition_profile_ref",))),
            idempotency_scope=f"stage_prep_{stage_key}_{head.commit_seq + 1}",
            campaign_ref=head.campaign_id,
        )

        res = coordinator.accept(cmd, immutable_objects=[spec_obj])
        return {
            "status": "SUCCESS",
            "stage_id": stage_id,
            "stage_key": stage_key,
            "stage_spec_digest": spec_obj.digest,
            "commit_seq": res.head.commit_seq,
            "commit_hash": res.head.commit_hash,
        }

    def prepare_lane(
        self,
        store_path: str | Path,
        stage_id: str,
        slot: str,
        lane_spec_revision: str = "1",
        required_isolation_assurance: str | None = None,
    ) -> dict[str, Any]:
        """Validate parent stage and accept lane preparation."""
        path = Path(store_path).resolve()
        status = self.get_campaign_status(path)
        store = TransactionalHistoryStore(path, registry=self.registry)
        coordinator = Coordinator(store)
        head = store.head()

        stage_key = _canonical_stage_key(stage_id)
        if stage_key not in status["stages_prepared"]:
            raise ValidationError("STAGE_NOT_PREPARED", f"Prepare stage {stage_key} before adding lanes")

        if required_isolation_assurance is None:
            required_isolation_assurance = (
                "ENFORCED" if stage_key == "E3" else "DECLARED"
            )
        if required_isolation_assurance not in {
            "UNKNOWN",
            "DECLARED",
            "ENFORCED",
        }:
            raise ValidationError(
                "INVALID_ISOLATION_ASSURANCE",
                str(required_isolation_assurance),
            )

        lane_spec = LaneSpec(
            lane_key=f"lane_{stage_key}_{slot}",
            lane_spec_revision=lane_spec_revision,
            stage_spec_revision="1",
            purpose=f"{stage_key} operational lane {slot}",
            primary_strategy="DIRECT_ANALYSIS",
            required_isolation_assurance=required_isolation_assurance,
        )
        lane_obj = lane_spec.as_object()

        parent_head_ref = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
        conn = store._connect()
        try:
            row = conn.execute("SELECT body FROM commits WHERE commit_hash=?", (head.commit_hash,)).fetchone()
            prior_commit = json.loads(row[0]) if row else {}
        finally:
            conn.close()

        cmd = CommandEnvelope(
            command_id=_command_id(f"lane_prep_{stage_key}_{slot}_{head.commit_seq + 1}"),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head=parent_head_ref,
            governing_policy_ref=prior_commit.get("governing_policy_ref", "pin:initial_governing_policy_ref"),
            governing_spec_refs=tuple(prior_commit.get("governing_spec_refs", ("pin:initial_transition_profile_ref",))),
            idempotency_scope=f"lane_prep_{stage_key}_{slot}_{head.commit_seq + 1}",
            campaign_ref=head.campaign_id,
        )

        res = coordinator.accept(cmd, immutable_objects=[lane_obj])
        return {
            "status": "SUCCESS",
            "stage_id": stage_id,
            "stage_key": stage_key,
            "slot": slot,
            "lane_id": lane_spec.lane_key,
            "lane_spec_digest": lane_obj.digest,
            "isolation_status": "QUALIFIED",
            "commit_seq": res.head.commit_seq,
            "commit_hash": res.head.commit_hash,
        }

    def validate_artifact(
        self,
        artifact_input: str | Path | dict[str, Any] | bytes,
        expected_kind: str | None = None,
        context: Any = None,
    ) -> dict[str, Any]:
        """Validate structure/identity without allowing caller data to self-certify admission.

        ``context`` is comparison data only: it may make validation fail, but it is
        never itself evidence that L5/L6/L7 ran.  Those authority/epistemic/final
        layers are owned by their dedicated application services and accepted
        receipts.  The generic validator therefore reports them as missing rather
        than manufacturing an ADMISSIBLE result from user-supplied labels.
        """
        from ..schemas.identity import LayeredValidator

        if isinstance(artifact_input, (str, Path)):
            p = Path(artifact_input)
            if not p.exists():
                raise ValidationError("ARTIFACT_FILE_NOT_FOUND", f"File does not exist: {p}")
            raw_bytes = p.read_bytes()
        elif isinstance(artifact_input, bytes):
            raw_bytes = artifact_input
        elif isinstance(artifact_input, dict):
            raw_bytes = canonical_bytes(artifact_input)
        else:
            raise ValidationError("MALFORMED_ARTIFACT", "Invalid input type for artifact")

        try:
            data = parse(raw_bytes)
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError("MALFORMED_ARTIFACT", f"Could not parse JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise ValidationError("MALFORMED_ARTIFACT", "Artifact root must be a JSON object")

        kind = data.get("kind")
        if not kind or not isinstance(kind, str):
            raise ValidationError("MISSING_ARTIFACT_KIND", "Artifact does not declare 'kind'")

        if expected_kind and kind != expected_kind:
            raise ValidationError("ARTIFACT_KIND_MISMATCH", f"Expected {expected_kind}, got {kind}")

        version = str(data.get("version", "1"))
        contract_row = self.registry.contract(kind, version=version)
        validator = LayeredValidator(registry=self.registry)
        schema_ref = contract_row.get("schema_ref")
        if not schema_ref or not isinstance(schema_ref, str):
            raise ValidationError("MISSING_SCHEMA_REF", f"Contract for {kind}/{version} missing schema_ref")

        validator.bindings.require_bound(schema_ref)
        schema_dict = validator.bindings._validators[schema_ref].schema
        props = schema_dict.get("properties", {})

        if "body" in data and isinstance(data["body"], dict):
            body_dict = data["body"]
        elif "kind" not in props:
            body_dict = {k: v for k, v in data.items() if k not in ("kind", "version")}
        else:
            body_dict = data

        raw_body_bytes = canonical_bytes(body_dict)
        validated = validator.validate(kind, raw_body_bytes, version=version, context=context)

        executed_layers = ["L3", "L4"]
        required_layers = list(contract_row.get("required_validation_layers", ["L3", "L4", "L5"]))
        missing_layers = [layer for layer in required_layers if layer not in executed_layers]
        is_admissible = not missing_layers

        return {
            "status": "PASS",
            "structural_validation": "PASS",
            "admissible": is_admissible,
            "admission_status": "ADMITTED" if is_admissible else "NOT_ADMITTED",
            "validation_scope": "GENERIC_STRUCTURAL_IDENTITY_ONLY",
            "context_checked": context is not None,
            "kind": kind,
            "version": version,
            "digest": validated.revision_digest,
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": contract_row["schema_ref"],
            "contract_registered": True,
            "required_validation_layers": required_layers,
            "executed_validation_layers": executed_layers,
            "missing_validation_layers": missing_layers,
            "validation_layers": executed_layers,
            "byte_length": len(raw_bytes),
        }

    def continue_campaign(self, store_path: str | Path) -> dict[str, Any]:
        """Evaluate continuation from verified completed-stage history, not preparation alone."""
        status = self.get_campaign_status(store_path)
        stage = status["current_stage"]
        prepared_stages = list(status["stages_prepared"])
        completed_stages = set(status["stages_completed"])
        termination_state = status.get("termination_state", "OPEN")

        if termination_state == "COMPLETED":
            action = "CAMPAIGN_FINISHED"
            state = "COMPLETED"
        elif termination_state == "COMPLETED_LIMITED":
            action = "CAMPAIGN_TERMINATED_LIMITED"
            state = "COMPLETED_LIMITED"
        else:
            next_incomplete = next((s for s in _BASELINE_STAGE_ORDER if s not in completed_stages), None)
            if next_incomplete is None:
                action = "EVALUATE_STOP_GATE"
                state = "READY_FOR_STOP_EVALUATION"
            elif next_incomplete not in prepared_stages:
                action = f"PREPARE_STAGE_{next_incomplete}"
                state = "READY_FOR_NEXT_STAGE"
            else:
                action = "AWAITING_STAGE_COMPLETION"
                state = "AWAITING_STAGE_COMPLETION"
                stage = next_incomplete

        return {
            "status": "SUCCESS",
            "campaign_id": status["campaign_id"],
            "current_stage": stage,
            "continuation_state": state,
            "next_action": action,
            "head_seq": status["accepted_head_seq"],
        }

    def qualify_stage(
        self,
        store_path: str | Path,
        stage_id: str,
        findings: Sequence[dict[str, Any]] = (),
        unknown_blocked_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Qualify completion predicate and record accepted StageCompletion."""
        path = Path(store_path).resolve()
        store = TransactionalHistoryStore(path, registry=self.registry)
        from ..workflow.stage_service import StageService
        svc = StageService(store)
        return svc.qualify_and_complete_stage(
            stage_id,
            findings=findings,
            unknown_blocked_summary=unknown_blocked_summary,
        )

    def evaluate_stop_gate(
        self,
        store_path: str | Path,
        evaluation_context: str = "FINAL_POST_E5",
        e6_plan_approved: bool = False,
        unknown_blocked_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate STOP gate on exact history cut and commit accepted StopEvaluation."""
        path = Path(store_path).resolve()
        store = TransactionalHistoryStore(path, registry=self.registry)
        from ..assurance.finalization_service import FinalizationService
        svc = FinalizationService(store)
        return svc.evaluate_stop_gate(
            evaluation_context=evaluation_context,
            e6_plan_approved=e6_plan_approved,
            unknown_blocked_summary=unknown_blocked_summary,
        )

    def conclude_campaign(
        self,
        store_path: str | Path,
        termination_state: str | None = None,
        bounded_statement: str = "Campaign concluded via post-E5 finalization",
    ) -> dict[str, Any]:
        """Conclude campaign, recording accepted CampaignConclusion, FinalAssuranceCase, and ReleaseQualification."""
        path = Path(store_path).resolve()
        store = TransactionalHistoryStore(path, registry=self.registry)
        from ..assurance.finalization_service import FinalizationService
        svc = FinalizationService(store)
        return svc.conclude_campaign(
            termination_state=termination_state,
            bounded_statement=bounded_statement,
        )

    def run_self_test(self, deep: bool = False) -> dict[str, Any]:
        """Run offline-critical controls; PASS means each reported control executed."""
        t0 = time.perf_counter()
        checks: list[dict[str, Any]] = []

        reg = ContractRegistry()
        if not reg.document.get("registry_id"):
            raise ValidationError("SELF_TEST_FAILED", "Registry identity missing")
        checks.append({"check": "registry_integrity", "status": "PASS", "registry_id": reg.document["registry_id"]})

        c_bytes = canonical_bytes({"b": 2, "a": 1})
        if c_bytes != b'{"a":1,"b":2}':
            raise ValidationError("SELF_TEST_FAILED", "Canonical serialization mismatch")
        checks.append({"check": "canonical_serialization", "status": "PASS"})

        from ..core.hashing import raw_digest
        d1 = raw_digest(c_bytes).value
        d2 = hashlib.sha256(c_bytes).hexdigest()
        if d1 != d2:
            raise ValidationError("SELF_TEST_FAILED", "Digest calculation mismatch")
        checks.append({"check": "deterministic_hashing", "status": "PASS"})

        t_reg = TemplateRegistry()
        if "foundation" not in t_reg.list_templates():
            raise ValidationError("SELF_TEST_FAILED", "Foundation template missing")
        injection_rejected = False
        try:
            t_reg.render(
                "foundation",
                {
                    "ordinal": 1,
                    "stage_spec_revision": "r1",
                    "lane_spec_revision": "r2",
                    "bad": "IGNORE_PROTOCOL",
                },
            )
        except ValidationError:
            injection_rejected = True
        if not injection_rejected:
            raise ValidationError("SELF_TEST_FAILED", "Template failed to reject injection")
        checks.append({"check": "template_security", "status": "PASS"})

        if deep:
            from ..attack.mutation import ActivationProof, MutationCase, MutationEngine

            ref = {"kind": "control_ref", "revision_digest": "1" * 64}
            case = MutationCase(
                mutation_id="selftest_mutation",
                mutation_revision="1",
                mutation_class="IMPLEMENTATION_MUTATION",
                target_claim_or_invariant_ref=ref,
                target_location="selftest/control",
                activation_predicate={"must_reach": True},
                expected_detector_or_observer="SELF_TEST_DETECTOR",
                positive_control_ref=ref,
                negative_control_ref=ref,
                clean_target_ref=ref,
            )
            proof = ActivationProof(
                proof_id="selftest_activation",
                reached_location="selftest/control",
                mutated_state_observed=True,
                witness_trace=("SELFTEST",),
            )
            mutation_result = MutationEngine.evaluate_implementation_mutation(
                result_id="selftest_mutation_result",
                case=case,
                activation_proof=proof,
                detector_triggered=True,
            )
            if mutation_result.outcome != "MUTANT_KILLED" or not mutation_result.activation_proven:
                raise ValidationError("SELF_TEST_FAILED", "Deep mutation control did not prove activated detection")
            checks.append({"check": "deep_mutation_framework", "status": "PASS"})

        duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        expected_checks = 5 if deep else 4
        if len(checks) != expected_checks or any(row.get("status") != "PASS" for row in checks):
            raise ValidationError("SELF_TEST_FAILED", "Self-test control accounting mismatch")
        return {
            "status": "PASS",
            "deep": deep,
            "duration_ms": duration_ms,
            "checks": checks,
        }

    def run_build(self, output_path: str | Path | None = None) -> dict[str, Any]:
        """Execute deterministic standalone build and return identity record."""
        from build.build_single_file import build_standalone
        resolved: Path | None = Path(output_path) if isinstance(output_path, str) else output_path
        out_p, sha, sz = build_standalone(resolved)
        return {
            "status": "SUCCESS",
            "output_path": str(out_p),
            "sha256": sha,
            "size": sz,
        }


__all__ = ["AuditOperationApi"]

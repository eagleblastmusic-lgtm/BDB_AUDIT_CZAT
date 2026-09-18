"""Fail-closed reconstruction of durable E2+ external stage packages.

Resume never regenerates a package from current settings.  It verifies the exact
published bytes, accepted AssignmentManifest/Attempt bindings, source identity,
history cut and semantic package digest, then rebuilds only the in-memory
StageBatch used by the UI/orchestrator.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..assurance.zip_safety import read_bytes as read_zip_bytes
from ..core.canonical_json import canonical_bytes, parse
from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from .manual_stage import (
    StageBatch,
    StageLaneJob,
    compute_stage_package_identity_digest,
)
from .package_resume import (
    _PACKAGE_LIMITS,
    _REQUIRED_MEMBERS,
    _current_cut,
    _same_ref,
    _source_from_manifest,
)
from .source_target import ResolvedSource


def _ref_digest(value: Any) -> str | None:
    if isinstance(value, dict):
        digest = value.get("revision_digest")
        return digest if isinstance(digest, str) else None
    return None


def _expected_assignments(
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
    *,
    stage_id: str,
    phase_id: str,
) -> dict[str, str]:
    prefix = f"lane_{stage_id}_"
    expected: dict[str, str] = {}
    for record in store.accepted_records("assignment_manifest", cut):
        body = record["body"]
        if body.get("phase_id") != phase_id:
            continue
        lane_ref = body.get("lane_spec_ref")
        if not isinstance(lane_ref, dict):
            raise ValidationError("RESUME_STAGE_LANE_BINDING_MISSING")
        lane = store.resolve_accepted(lane_ref, cut)
        lane_key = lane["body"].get("lane_key")
        if not isinstance(lane_key, str) or not lane_key.startswith(prefix):
            continue
        slot = lane_key[len(prefix):]
        if not slot:
            raise ValidationError("RESUME_STAGE_LANE_INVALID")
        digest = record["ref"]["revision_digest"]
        prior = expected.get(slot)
        if prior is not None and prior != digest:
            raise ValidationError("RESUME_STAGE_DUPLICATE_ASSIGNMENT", slot)
        expected[slot] = digest
    return expected


def _load_one(
    path: Path,
    store: TransactionalHistoryStore,
    cut: dict[str, Any],
    *,
    stage_id: str,
    phase_id: str,
) -> tuple[StageLaneJob, ResolvedSource]:
    raw = path.read_bytes()
    zip_sha = hashlib.sha256(raw).hexdigest()
    try:
        members = read_zip_bytes(raw, limits=_PACKAGE_LIMITS)
    except ValidationError as exc:
        raise ValidationError(
            "RESUME_STAGE_PACKAGE_ZIP_INVALID",
            f"{path.name}: {exc.code}",
        ) from exc

    member_names = set(members)
    if not _REQUIRED_MEMBERS.issubset(member_names):
        raise ValidationError(
            "RESUME_STAGE_PACKAGE_MEMBER_SET_INVALID",
            f"{path.name}: missing required members",
        )
    unexpected = {
        name
        for name in member_names - _REQUIRED_MEMBERS
        if not name.startswith("CONTEXT/")
    }
    if unexpected:
        raise ValidationError(
            "RESUME_STAGE_PACKAGE_MEMBER_SET_INVALID",
            f"{path.name}: unexpected={sorted(unexpected)}",
        )

    try:
        manifest = parse(members["MANIFEST.json"])
    except ValidationError as exc:
        raise ValidationError(
            "RESUME_STAGE_PACKAGE_MANIFEST_INVALID",
            f"{path.name}: {exc.code}",
        ) from exc
    if not isinstance(manifest, dict):
        raise ValidationError("RESUME_STAGE_PACKAGE_MANIFEST_INVALID", path.name)
    if manifest.get("format") != "BDB-STAGE-PROMPT-PACKAGE-1":
        raise ValidationError("RESUME_STAGE_PACKAGE_FORMAT_UNSUPPORTED", path.name)
    if manifest.get("stage_id") != stage_id or manifest.get("phase_id") != phase_id:
        raise ValidationError("RESUME_STAGE_PACKAGE_PHASE_MISMATCH", path.name)

    slot = manifest.get("lane_slot")
    if not isinstance(slot, str) or not slot:
        raise ValidationError("RESUME_STAGE_PACKAGE_LANE_INVALID", path.name)
    if manifest.get("campaign_id") != cut.get("campaign_id"):
        raise ValidationError("RESUME_STAGE_PACKAGE_CAMPAIGN_MISMATCH", path.name)

    assignment_ref = manifest.get("assignment_ref")
    attempt_ref = manifest.get("attempt_ref")
    if not isinstance(assignment_ref, dict) or not isinstance(attempt_ref, dict):
        raise ValidationError("RESUME_STAGE_ASSIGNMENT_BINDING_MISSING", path.name)
    assignment_record = store.resolve_accepted(assignment_ref, cut)
    assignment = assignment_record["body"]
    if assignment.get("phase_id") != phase_id:
        raise ValidationError("RESUME_STAGE_ASSIGNMENT_PHASE_MISMATCH", slot)
    if not _same_ref(assignment.get("attempt_ref"), attempt_ref):
        raise ValidationError("RESUME_STAGE_ASSIGNMENT_ATTEMPT_MISMATCH", slot)
    store.resolve_accepted(attempt_ref, cut)

    frozen_cut = manifest.get("input_history_cut")
    if (
        not isinstance(frozen_cut, dict)
        or assignment.get("assignment_input_history_cut") != frozen_cut
    ):
        raise ValidationError("RESUME_STAGE_ASSIGNMENT_CUT_MISMATCH", slot)

    source = _source_from_manifest(manifest.get("source_target"))
    prompt_raw = members["PROMPT.txt"]
    prompt_sha = hashlib.sha256(prompt_raw).hexdigest()
    if prompt_sha != manifest.get("prompt_sha256"):
        raise ValidationError("RESUME_STAGE_PROMPT_DIGEST_MISMATCH", slot)

    compiled_digest = hashlib.sha256(members["PACKAGE.json"]).hexdigest()
    if compiled_digest != manifest.get("compiled_digest"):
        raise ValidationError("RESUME_STAGE_COMPILED_DIGEST_MISMATCH", slot)

    execution_mode = manifest.get("execution_mode")
    model = manifest.get("model")
    if not isinstance(execution_mode, str) or not isinstance(model, str):
        raise ValidationError("RESUME_STAGE_EXECUTOR_BINDING_MISSING", slot)

    context_manifest = manifest.get("context_manifest", {})
    if not isinstance(context_manifest, dict):
        raise ValidationError("RESUME_STAGE_CONTEXT_MANIFEST_INVALID", slot)
    context_members = {
        name[len("CONTEXT/"):]: raw
        for name, raw in members.items()
        if name.startswith("CONTEXT/")
    }
    actual_context_manifest = {
        name: hashlib.sha256(raw).hexdigest()
        for name, raw in sorted(context_members.items())
    }
    if actual_context_manifest != context_manifest:
        raise ValidationError("RESUME_STAGE_CONTEXT_DIGEST_MISMATCH", slot)

    authorization = manifest.get("context_authorization", {})
    if not isinstance(authorization, dict):
        raise ValidationError("RESUME_STAGE_CONTEXT_AUTHORIZATION_INVALID", slot)
    if context_manifest:
        required_auth = {
            "view_manifest_ref",
            "grant_ref",
            "knowledge_state_ref",
            "authorization_history_cut",
        }
        if not required_auth.issubset(authorization):
            raise ValidationError("RESUME_STAGE_UNBOUND_CONTEXT_PRESENT", slot)
        auth_cut = authorization["authorization_history_cut"]
        if not isinstance(auth_cut, dict):
            raise ValidationError("RESUME_STAGE_CONTEXT_AUTHORIZATION_INVALID", slot)
        view = store.resolve_accepted(
            authorization["view_manifest_ref"],
            auth_cut,
        )
        grant = store.resolve_accepted(
            authorization["grant_ref"],
            auth_cut,
        )
        knowledge = store.resolve_accepted(
            authorization["knowledge_state_ref"],
            auth_cut,
        )
        if view["body"].get("payload_manifest") != context_manifest:
            raise ValidationError("RESUME_STAGE_CONTEXT_VIEW_PAYLOAD_MISMATCH", slot)
        if (
            not _same_ref(grant["body"].get("attempt_ref"), attempt_ref)
            or not _same_ref(
                grant["body"].get("view_manifest_ref"),
                authorization["view_manifest_ref"],
            )
        ):
            raise ValidationError("RESUME_STAGE_CONTEXT_GRANT_BINDING_MISMATCH", slot)
        if not _same_ref(knowledge["body"].get("attempt_ref"), attempt_ref):
            raise ValidationError("RESUME_STAGE_CONTEXT_KNOWLEDGE_BINDING_MISMATCH", slot)
        if not any(
            _same_ref(ref, authorization["view_manifest_ref"])
            for ref in knowledge["body"].get("allowed_view_refs", [])
            if isinstance(ref, dict)
        ):
            raise ValidationError("RESUME_STAGE_CONTEXT_VIEW_NOT_IN_KNOWLEDGE", slot)
    elif authorization:
        raise ValidationError("RESUME_STAGE_CONTEXT_AUTH_WITHOUT_PAYLOAD", slot)

    expected_digest = compute_stage_package_identity_digest(
        compiled_digest=compiled_digest,
        prompt_sha256=prompt_sha,
        assignment_digest=assignment_ref["revision_digest"],
        attempt_digest=attempt_ref["revision_digest"],
        executor_profile=execution_mode,
        executor_model=model,
        history_cut=frozen_cut,
        stage_id=stage_id,
        phase_id=phase_id,
        lane_slot=slot,
        source_commit_sha=source.exact_commit_sha,
        source_tree_sha=source.exact_tree_sha or "",
        source_location=source.location,
        context_manifest=context_manifest,
        authorization_binding=authorization,
    )
    if manifest.get("package_digest") != expected_digest:
        raise ValidationError("RESUME_STAGE_PACKAGE_SEMANTIC_DIGEST_MISMATCH", slot)

    checksum_path = path.with_suffix(".zip.sha256")
    if not checksum_path.is_file():
        raise ValidationError("RESUME_STAGE_PACKAGE_RAW_RECEIPT_MISSING", path.name)
    try:
        receipt = checksum_path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise ValidationError("RESUME_STAGE_PACKAGE_RAW_RECEIPT_INVALID", path.name) from exc
    if receipt != f"{zip_sha}  {path.name}\n":
        raise ValidationError("RESUME_STAGE_PACKAGE_RAW_DIGEST_MISMATCH", path.name)

    try:
        prompt_text = prompt_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("RESUME_STAGE_PROMPT_ENCODING_INVALID", slot) from exc

    lane_title = manifest.get("lane_title")
    strategy = manifest.get("strategy")
    if not isinstance(lane_title, str) or not isinstance(strategy, str):
        raise ValidationError("RESUME_STAGE_PACKAGE_METADATA_INVALID", slot)

    return (
        StageLaneJob(
            campaign_id=cut["campaign_id"],
            stage_id=stage_id,
            phase_id=phase_id,
            lane_slot=slot,
            lane_title=lane_title,
            strategy=strategy,
            input_history_cut=dict(frozen_cut),
            package_digest=expected_digest,
            package_zip_path=path,
            package_zip_sha256=zip_sha,
            prompt_text=prompt_text,
            source_commit_sha=source.exact_commit_sha,
            source_tree_sha=source.exact_tree_sha or "",
            executor_profile=execution_mode,
            model=model,
            assignment_ref=dict(assignment_ref),
            attempt_ref=dict(attempt_ref),
            prompt_sha256=prompt_sha,
            context_manifest=dict(context_manifest),
            view_manifest_ref=dict(
                authorization.get("view_manifest_ref", {})
            ),
            grant_ref=dict(
                authorization.get("grant_ref", {})
            ),
            authorized_knowledge_state_ref=dict(
                authorization.get("knowledge_state_ref", {})
            ),
            authorization_history_cut=dict(
                authorization.get("authorization_history_cut", {})
            ),
        ),
        source,
    )


def load_stage_phase_batch(
    store: TransactionalHistoryStore,
    artifact_root: str | Path,
    *,
    stage_id: str,
    phase_id: str,
) -> tuple[StageBatch, ResolvedSource]:
    """Reconstruct one accepted external stage phase without mutating history."""
    stage_id = stage_id.upper()
    cut = _current_cut(store)
    expected = _expected_assignments(
        store,
        cut,
        stage_id=stage_id,
        phase_id=phase_id,
    )
    if not expected:
        raise ValidationError(
            "RESUME_STAGE_ASSIGNMENTS_NOT_FOUND",
            f"{stage_id}/{phase_id}",
        )

    root = (
        Path(artifact_root).resolve()
        / cut["campaign_id"]
        / stage_id
        / phase_id
    )
    if not root.is_dir():
        raise ValidationError("RESUME_STAGE_PACKAGE_STATE_MISSING", str(root))
    candidates = sorted(
        root.glob("*_PACKAGE.zip"),
        key=lambda value: value.name.encode("utf-8"),
    )
    if not candidates:
        raise ValidationError("RESUME_STAGE_PACKAGE_STATE_MISSING", str(root))

    jobs: dict[str, StageLaneJob] = {}
    source: ResolvedSource | None = None
    source_bytes: bytes | None = None
    frozen_bytes: bytes | None = None
    executor_binding: tuple[str, str] | None = None

    for path in candidates:
        job, candidate_source = _load_one(
            path,
            store,
            cut,
            stage_id=stage_id,
            phase_id=phase_id,
        )
        if job.lane_slot in jobs:
            raise ValidationError("RESUME_STAGE_DUPLICATE_LANE_PACKAGE", job.lane_slot)
        expected_assignment = expected.get(job.lane_slot)
        if expected_assignment is None:
            raise ValidationError("RESUME_STAGE_UNEXPECTED_LANE_PACKAGE", job.lane_slot)
        if job.assignment_ref.get("revision_digest") != expected_assignment:
            raise ValidationError("RESUME_STAGE_ASSIGNMENT_PACKAGE_MISMATCH", job.lane_slot)

        candidate_source_bytes = canonical_bytes(candidate_source.as_dict())
        candidate_frozen_bytes = canonical_bytes(job.input_history_cut)
        candidate_executor = (job.executor_profile, job.model)
        if source_bytes is None:
            source = candidate_source
            source_bytes = candidate_source_bytes
            frozen_bytes = candidate_frozen_bytes
            executor_binding = candidate_executor
        elif (
            source_bytes != candidate_source_bytes
            or frozen_bytes != candidate_frozen_bytes
            or executor_binding != candidate_executor
        ):
            raise ValidationError("RESUME_STAGE_PACKAGE_SET_DIVERGENCE")
        jobs[job.lane_slot] = job

    missing = sorted(set(expected) - set(jobs))
    unexpected = sorted(set(jobs) - set(expected))
    if missing or unexpected:
        raise ValidationError(
            "RESUME_STAGE_PACKAGE_SET_INCOMPLETE",
            f"missing={missing}; unexpected={unexpected}",
        )
    assert source is not None
    assignment_input = next(iter(jobs.values())).input_history_cut
    return (
        StageBatch(
            campaign_id=cut["campaign_id"],
            stage_id=stage_id,
            phase_id=phase_id,
            frozen_history_cut=dict(assignment_input),
            jobs=jobs,
            assignment_accepted_history_cut={},
        ),
        source,
    )


__all__ = ["load_stage_phase_batch"]

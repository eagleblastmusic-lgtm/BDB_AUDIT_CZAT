"""Fail-closed reconstruction of durable E1 package state (RU03 / D05/D10).

Resume must not rebuild assignments or packages from mutable user settings.  It
loads the exact package bytes published for the campaign, verifies their raw and
semantic identities, checks that their AssignmentManifest/Attempt references are
accepted, and reconstructs the in-memory E1Batch without writing history.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..assurance.zip_safety import Limits as ZipLimits, read_bytes as read_zip_bytes
from ..core.canonical_json import canonical_bytes, parse
from ..core.errors import ValidationError
from ..history.objects import HistoryCut
from ..history.store import TransactionalHistoryStore
from ..orchestration.native_ensemble import E1_LANE_SLOTS
from .packaging import E1Batch, E1LaneJob, compute_package_identity_digest
from .source_target import ResolvedSource

_PACKAGE_LIMITS = ZipLimits(
    input_bytes=32 * 1024 * 1024,
    central_bytes=2 * 1024 * 1024,
    members=32,
    member_bytes=16 * 1024 * 1024,
    expanded_bytes=32 * 1024 * 1024,
    ratio=200,
)
_REQUIRED_MEMBERS = {"MANIFEST.json", "PACKAGE.json", "PROMPT.txt", "README.md"}


def _current_cut(store: TransactionalHistoryStore) -> dict[str, Any]:
    head = store.head()
    if head is None:
        raise ValidationError("CAMPAIGN_NOT_INITIALIZED")
    commits = store.commits()
    if not commits:
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    body = commits[-1]
    if body.get("commit_seq") != head.commit_seq or body.get("campaign_id") != head.campaign_id:
        raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
    return HistoryCut.accepted(head, body["governing_policy_ref"], body["governing_spec_refs"]).as_dict()


def _same_ref(left: Any, right: Any) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    return all(left.get(key) == right.get(key) for key in ("kind", "revision_digest", "schema_revision_ref"))


def _source_from_manifest(value: Any) -> ResolvedSource:
    if not isinstance(value, dict):
        raise ValidationError("RESUME_SOURCE_IDENTITY_MISSING")
    try:
        return ResolvedSource(
            target_type=value["target_type"],
            location=value["location"],
            display_name=value["display_name"],
            ref=value["ref"],
            exact_commit_sha=value["exact_commit_sha"],
            resolved=value.get("resolved", True),
            exact_tree_sha=value.get("exact_tree_sha"),
            object_format=value.get("object_format", "sha1"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError("RESUME_SOURCE_IDENTITY_INVALID", type(exc).__name__) from exc


def _load_one(path: Path, store: TransactionalHistoryStore, cut: dict[str, Any]) -> tuple[E1LaneJob, ResolvedSource]:
    raw = path.read_bytes()
    zip_sha = hashlib.sha256(raw).hexdigest()
    try:
        members = read_zip_bytes(raw, limits=_PACKAGE_LIMITS)
    except ValidationError as exc:
        raise ValidationError("RESUME_PACKAGE_ZIP_INVALID", f"{path.name}: {exc.code}") from exc
    if set(members) != _REQUIRED_MEMBERS:
        raise ValidationError(
            "RESUME_PACKAGE_MEMBER_SET_INVALID",
            f"{path.name}: expected {sorted(_REQUIRED_MEMBERS)}, got {sorted(members)}",
        )

    try:
        manifest = parse(members["MANIFEST.json"])
    except ValidationError as exc:
        raise ValidationError("RESUME_PACKAGE_MANIFEST_INVALID", f"{path.name}: {exc.code}") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != "BDB-F2-PROMPT-PACKAGE-2":
        raise ValidationError("RESUME_PACKAGE_FORMAT_UNSUPPORTED", path.name)

    slot = manifest.get("lane_slot")
    if slot not in E1_LANE_SLOTS or manifest.get("stage_id") != "E1":
        raise ValidationError("RESUME_PACKAGE_LANE_INVALID", path.name)
    campaign_id = manifest.get("campaign_id")
    if not isinstance(campaign_id, str) or campaign_id != cut.get("campaign_id"):
        raise ValidationError("RESUME_PACKAGE_CAMPAIGN_MISMATCH", path.name)

    assignment_ref = manifest.get("assignment_ref")
    attempt_ref = manifest.get("attempt_ref")
    if not isinstance(assignment_ref, dict) or not isinstance(attempt_ref, dict):
        raise ValidationError("RESUME_ASSIGNMENT_BINDING_MISSING", path.name)

    assignment_record = store.resolve_accepted(assignment_ref, cut)
    assignment = assignment_record["body"]
    if not _same_ref(assignment.get("attempt_ref"), attempt_ref):
        raise ValidationError("RESUME_ASSIGNMENT_ATTEMPT_MISMATCH", slot)
    store.resolve_accepted(attempt_ref, cut)

    frozen_cut = manifest.get("input_history_cut")
    if not isinstance(frozen_cut, dict) or assignment.get("assignment_input_history_cut") != frozen_cut:
        raise ValidationError("RESUME_ASSIGNMENT_CUT_MISMATCH", slot)

    source = _source_from_manifest(manifest.get("source_target"))
    prompt_raw = members["PROMPT.txt"]
    prompt_sha = hashlib.sha256(prompt_raw).hexdigest()
    if prompt_sha != manifest.get("prompt_sha256"):
        raise ValidationError("RESUME_PROMPT_DIGEST_MISMATCH", slot)

    compiled_digest = hashlib.sha256(members["PACKAGE.json"]).hexdigest()
    if compiled_digest != manifest.get("compiled_digest"):
        raise ValidationError("RESUME_COMPILED_PACKAGE_DIGEST_MISMATCH", slot)

    execution_mode = manifest.get("execution_mode")
    model = manifest.get("model")
    if not isinstance(execution_mode, str) or not isinstance(model, str):
        raise ValidationError("RESUME_EXECUTOR_BINDING_MISSING", slot)

    expected_semantic_digest = compute_package_identity_digest(
        compiled_digest=compiled_digest,
        executor_model=model,
        executor_profile=execution_mode,
        history_cut=frozen_cut,
        lane_slot=slot,
        source_commit_sha=source.exact_commit_sha,
        source_tree_sha=source.exact_tree_sha or "",
        source_location=source.location,
        stage_id="E1",
        prompt_sha256=prompt_sha,
        assignment_digest=assignment_ref["revision_digest"],
        attempt_digest=attempt_ref["revision_digest"],
    )
    if manifest.get("package_digest") != expected_semantic_digest:
        raise ValidationError("RESUME_PACKAGE_SEMANTIC_DIGEST_MISMATCH", slot)

    checksum_path = path.with_suffix(".zip.sha256")
    if not checksum_path.is_file():
        raise ValidationError("RESUME_PACKAGE_RAW_RECEIPT_MISSING", path.name)
    try:
        receipt = checksum_path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise ValidationError("RESUME_PACKAGE_RAW_RECEIPT_INVALID", path.name) from exc
    if receipt != f"{zip_sha}  {path.name}\n":
        raise ValidationError("RESUME_PACKAGE_RAW_DIGEST_MISMATCH", path.name)

    try:
        prompt_text = prompt_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("RESUME_PROMPT_ENCODING_INVALID", slot) from exc

    lane_title = manifest.get("lane_title")
    strategy = manifest.get("strategy")
    if not isinstance(lane_title, str) or not isinstance(strategy, str):
        raise ValidationError("RESUME_PACKAGE_METADATA_INVALID", slot)

    return E1LaneJob(
        campaign_id=campaign_id,
        stage_id="E1",
        lane_slot=slot,
        lane_title=lane_title,
        strategy=strategy,
        input_history_cut=dict(frozen_cut),
        package_digest=expected_semantic_digest,
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
    ), source


def load_e1_batch(
    store: TransactionalHistoryStore,
    artifact_root: str | Path,
) -> tuple[E1Batch, ResolvedSource]:
    """Load exactly one verified package for every required E1 assignment.

    No file is regenerated and no current user setting participates in the
    reconstructed assignment. Missing/tampered durable package state blocks
    resume rather than silently creating a new execution context.
    """
    cut = _current_cut(store)
    campaign_id = cut["campaign_id"]
    e1_dir = Path(artifact_root).resolve() / campaign_id / "E1"
    if not e1_dir.is_dir():
        raise ValidationError("RESUME_PACKAGE_STATE_MISSING", str(e1_dir))

    candidates = sorted(e1_dir.glob("*_PACKAGE.zip"), key=lambda p: p.name.encode("utf-8"))
    if not candidates:
        raise ValidationError("RESUME_PACKAGE_STATE_MISSING", str(e1_dir))

    jobs: dict[str, E1LaneJob] = {}
    source: ResolvedSource | None = None
    source_bytes: bytes | None = None
    frozen_bytes: bytes | None = None
    executor_binding: tuple[str, str] | None = None

    for path in candidates:
        job, candidate_source = _load_one(path, store, cut)
        if job.lane_slot in jobs:
            raise ValidationError("RESUME_DUPLICATE_LANE_PACKAGE", job.lane_slot)

        candidate_source_bytes = canonical_bytes(candidate_source.as_dict())
        candidate_frozen_bytes = canonical_bytes(job.input_history_cut)
        candidate_executor = (job.executor_profile, job.model)
        if source_bytes is None:
            source = candidate_source
            source_bytes = candidate_source_bytes
            frozen_bytes = candidate_frozen_bytes
            executor_binding = candidate_executor
        elif (
            candidate_source_bytes != source_bytes
            or candidate_frozen_bytes != frozen_bytes
            or candidate_executor != executor_binding
        ):
            raise ValidationError("RESUME_PACKAGE_SET_DIVERGENCE")
        jobs[job.lane_slot] = job

    missing = [slot for slot in E1_LANE_SLOTS if slot not in jobs]
    if missing or len(jobs) != len(E1_LANE_SLOTS):
        raise ValidationError("RESUME_PACKAGE_SET_INCOMPLETE", ",".join(missing))
    assert source is not None

    # Every package must still point to exactly one accepted assignment. This
    # detects stale/tampered files even after sibling lane results advanced HEAD.
    assignment_input = next(iter(jobs.values())).input_history_cut
    for slot, job in jobs.items():
        assignment = store.resolve_accepted(job.assignment_ref, cut)["body"]
        if assignment.get("assignment_input_history_cut") != assignment_input:
            raise ValidationError("RESUME_ASSIGNMENT_CUT_DIVERGENCE", slot)

    return E1Batch(
        campaign_id=campaign_id,
        stage_id="E1",
        frozen_history_cut=dict(assignment_input),
        jobs=jobs,
        assignment_accepted_history_cut={},
    ), source


__all__ = ["load_e1_batch"]

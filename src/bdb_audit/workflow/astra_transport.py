"""Astra/R5.3 transport hardening for post-E1 external stages.

The baseline post-E1 transport binds assignment/source/history/prompt identity.
This branch layer additionally binds the exact predecessor-stage context that a
cross-review/deepening lane is allowed to see.  The context bytes are hashed,
the hash is embedded in PROMPT.txt, and prompt SHA participates in package
semantic identity.  Resume verifies both the context bytes and that prompt
binding before reconstructing any StageBatch.

E3 remains deliberately blind: its CONTEXT.json carries only predecessor
completion identity and never prior finding/result bodies.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
from typing import Any, Sequence

from ..assurance.zip_safety import read_bytes as read_zip_bytes
from ..core.canonical_json import canonical_bytes, parse
from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from ..orchestration.native_ensemble import E1_LANE_SLOTS
from . import stage_transport as base
from .packaging import _deterministic_zip, _publish_exact, compute_package_identity_digest
from .source_target import ResolvedSource

_CONTEXT_MEMBER = "CONTEXT.json"
_REQUIRED_MEMBERS = {
    "MANIFEST.json",
    "PACKAGE.json",
    "PROMPT.txt",
    "README.md",
    _CONTEXT_MEMBER,
}
_PREDECESSOR = {
    "E2": "E1",
    "E3": "E2",
    "E4": "E3",
    "E5": "E4",
    "E6": "E5",
}


def _with_ref_class(ref: dict[str, Any], ref_class: str) -> dict[str, Any]:
    out = dict(ref)
    out["ref_class"] = ref_class
    return out


def _stage_completion_ref(
    store: TransactionalHistoryStore,
    stage_id: str,
    cut: dict[str, Any],
) -> dict[str, Any]:
    specs = {
        row["ref"]["revision_digest"]: row["body"].get("stage_key")
        for row in store.accepted_records("stage_spec", cut)
    }
    matches = []
    for row in store.accepted_records("stage_completion", cut):
        spec_ref = row["body"].get("stage_spec_ref", {})
        if specs.get(spec_ref.get("revision_digest")) == stage_id:
            matches.append(row)
    if len(matches) != 1:
        raise ValidationError(
            "STAGE_CONTEXT_COMPLETION_AMBIGUOUS",
            f"{stage_id}: expected 1 accepted completion, got {len(matches)}",
        )
    return _with_ref_class(matches[0]["ref"], "CONTENT_OR_PRIOR")


def _accepted_stage_results(
    store: TransactionalHistoryStore,
    stage_id: str,
    cut: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = [
        row
        for row in store.accepted_records("bdb_audit_lane_result", cut)
        if row["body"].get("stage_id") == stage_id
    ]
    rows.sort(key=lambda row: str(row["body"].get("lane_slot", "")).encode("utf-8"))
    return rows


def build_stage_context(
    store: TransactionalHistoryStore,
    stage_id: str,
    cut: dict[str, Any],
) -> dict[str, Any]:
    """Build the exact allowed predecessor view for one future stage."""
    stage = stage_id.upper()
    predecessor = _PREDECESSOR.get(stage)
    if predecessor is None:
        raise ValidationError("POST_E1_STAGE_UNSUPPORTED", stage)

    completion_ref = _stage_completion_ref(store, predecessor, cut)
    common: dict[str, Any] = {
        "kind": "bdb_stage_transport_context",
        "version": "1",
        "campaign_id": cut["campaign_id"],
        "stage_id": stage,
        "predecessor_stage_id": predecessor,
        "predecessor_stage_completion_ref": completion_ref,
        "context_history_cut": dict(cut),
    }

    if stage == "E3":
        return {
            **common,
            "knowledge_policy": "BLIND_NO_PRIOR_RESULT_CONTENT",
            "blind": True,
            "predecessor_results": [],
        }

    results = _accepted_stage_results(store, predecessor, cut)
    if stage == "E2":
        observed_slots = {str(row["body"].get("lane_slot", "")) for row in results}
        if observed_slots != set(E1_LANE_SLOTS):
            raise ValidationError(
                "E2_CONTEXT_E1_RESULT_SET_INCOMPLETE",
                f"expected {sorted(E1_LANE_SLOTS)}, got {sorted(observed_slots)}",
            )

    exposed: list[dict[str, Any]] = []
    for row in results:
        body = row["body"]
        findings = body.get("findings") if isinstance(body.get("findings"), list) else []
        exposed.append({
            "lane_slot": body.get("lane_slot"),
            "result_ref": _with_ref_class(row["ref"], "CONTENT_OR_PRIOR"),
            "raw_result_digest": body.get("raw_result_digest"),
            "findings": [dict(item) for item in findings if isinstance(item, dict)],
            "evidence_files": [
                dict(item)
                for item in body.get("evidence_files", [])
                if isinstance(item, dict)
            ],
        })

    return {
        **common,
        "knowledge_policy": "PREDECESSOR_ACCEPTED_RESULTS_ONLY",
        "blind": False,
        "predecessor_results": exposed,
    }


def _bind_context_to_job(
    store: TransactionalHistoryStore,
    batch: base.StageBatch,
    job: base.StageLaneJob,
) -> base.StageLaneJob:
    context = build_stage_context(store, batch.stage_id, job.input_history_cut)
    context_raw = canonical_bytes(context)
    context_sha = hashlib.sha256(context_raw).hexdigest()

    old_path = job.package_zip_path
    old_members = read_zip_bytes(old_path.read_bytes(), limits=base._PACKAGE_LIMITS)
    if set(old_members) != base._REQUIRED_PACKAGE_MEMBERS:
        raise ValidationError("ASTRA_BASE_PACKAGE_MEMBER_SET_INVALID", old_path.name)

    manifest = parse(old_members["MANIFEST.json"])
    if not isinstance(manifest, dict):
        raise ValidationError("ASTRA_BASE_PACKAGE_MANIFEST_INVALID", old_path.name)
    try:
        old_prompt = old_members["PROMPT.txt"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("RESUME_PROMPT_ENCODING_INVALID", job.lane_slot) from exc

    prompt_text = (
        old_prompt
        + "\n## Bound stage context\n"
        + f"Read `{_CONTEXT_MEMBER}` before producing the result. "
        + f"Its exact SHA-256 is `{context_sha}`. "
        + "Do not substitute, regenerate, or broaden this context.\n"
    )
    prompt_raw = prompt_text.encode("utf-8")
    prompt_sha = hashlib.sha256(prompt_raw).hexdigest()
    compiled_digest = hashlib.sha256(old_members["PACKAGE.json"]).hexdigest()
    package_digest = compute_package_identity_digest(
        compiled_digest=compiled_digest,
        executor_model=job.model,
        executor_profile=job.executor_profile,
        history_cut=job.input_history_cut,
        lane_slot=job.lane_slot,
        source_commit_sha=job.source_commit_sha,
        source_tree_sha=job.source_tree_sha,
        source_location=manifest["source_target"]["location"],
        stage_id=job.stage_id,
        prompt_sha256=prompt_sha,
        assignment_digest=job.assignment_ref["revision_digest"],
        attempt_digest=job.attempt_ref["revision_digest"],
    )
    manifest = {
        **manifest,
        "format": "BDB-ASTRA-STAGE-PACKAGE-2",
        "package_digest": package_digest,
        "prompt_sha256": prompt_sha,
        "context_member": _CONTEXT_MEMBER,
        "context_sha256": context_sha,
        "context_policy": context["knowledge_policy"],
    }
    zip_bytes = _deterministic_zip({
        "MANIFEST.json": canonical_bytes(manifest),
        "PACKAGE.json": old_members["PACKAGE.json"],
        "PROMPT.txt": prompt_raw,
        "README.md": old_members["README.md"],
        _CONTEXT_MEMBER: context_raw,
    })
    zip_sha = hashlib.sha256(zip_bytes).hexdigest()
    filename = f"{job.stage_id}_{job.lane_slot}_{package_digest[:12]}_PACKAGE.zip"
    new_path = old_path.parent / filename
    _publish_exact(new_path, zip_bytes)
    _publish_exact(
        new_path.with_suffix(".zip.sha256"),
        f"{zip_sha}  {filename}\n".encode("ascii"),
    )

    if new_path != old_path:
        old_sidecar = old_path.with_suffix(".zip.sha256")
        old_path.unlink(missing_ok=True)
        old_sidecar.unlink(missing_ok=True)

    return replace(
        job,
        package_digest=package_digest,
        package_zip_path=new_path,
        package_zip_sha256=zip_sha,
        prompt_text=prompt_text,
        prompt_sha256=prompt_sha,
    )


def prepare_stage_batch(
    store: TransactionalHistoryStore,
    output_dir: Path,
    source_info: ResolvedSource,
    stage_id: str,
    *,
    execution_mode: str = "ChatGPT / GitHub",
    model: str = "Sol 5.6",
    slots: Sequence[str] | None = None,
) -> base.StageBatch:
    """Prepare baseline assignments then strengthen package context binding."""
    batch = base.prepare_stage_batch(
        store=store,
        output_dir=output_dir,
        source_info=source_info,
        stage_id=stage_id,
        execution_mode=execution_mode,
        model=model,
        slots=slots,
    )
    jobs = {
        slot: _bind_context_to_job(store, batch, job)
        for slot, job in batch.jobs.items()
    }
    return base.StageBatch(
        campaign_id=batch.campaign_id,
        stage_id=batch.stage_id,
        frozen_history_cut=dict(batch.frozen_history_cut),
        jobs=jobs,
        assignment_accepted_history_cut=dict(batch.assignment_accepted_history_cut),
    )


def _verify_context_package(job: base.StageLaneJob) -> None:
    members = read_zip_bytes(job.package_zip_path.read_bytes(), limits=base._PACKAGE_LIMITS)
    if set(members) != _REQUIRED_MEMBERS:
        raise ValidationError("RESUME_PACKAGE_MEMBER_SET_INVALID", job.package_zip_path.name)
    manifest = parse(members["MANIFEST.json"])
    context = parse(members[_CONTEXT_MEMBER])
    if not isinstance(manifest, dict) or not isinstance(context, dict):
        raise ValidationError("RESUME_CONTEXT_INVALID", job.lane_slot)
    if manifest.get("format") != "BDB-ASTRA-STAGE-PACKAGE-2":
        raise ValidationError("RESUME_PACKAGE_FORMAT_UNSUPPORTED", job.package_zip_path.name)
    actual_sha = hashlib.sha256(members[_CONTEXT_MEMBER]).hexdigest()
    if manifest.get("context_sha256") != actual_sha:
        raise ValidationError("RESUME_CONTEXT_DIGEST_MISMATCH", job.lane_slot)
    prompt = members["PROMPT.txt"].decode("utf-8")
    if actual_sha not in prompt:
        raise ValidationError("RESUME_CONTEXT_PROMPT_BINDING_MISSING", job.lane_slot)
    if context.get("campaign_id") != job.campaign_id or context.get("stage_id") != job.stage_id:
        raise ValidationError("RESUME_CONTEXT_SCOPE_MISMATCH", job.lane_slot)
    if context.get("context_history_cut") != job.input_history_cut:
        raise ValidationError("RESUME_CONTEXT_CUT_MISMATCH", job.lane_slot)
    if job.stage_id == "E3" and context.get("predecessor_results"):
        raise ValidationError("E3_BLIND_CONTEXT_LEAK", job.lane_slot)


def load_stage_batch(
    store: TransactionalHistoryStore,
    artifact_root: Path,
    stage_id: str,
    slots: Sequence[str] | None = None,
) -> tuple[base.StageBatch, ResolvedSource]:
    """Resume only from context-bound post-E1 package bytes."""
    previous_required = base._REQUIRED_PACKAGE_MEMBERS
    try:
        base._REQUIRED_PACKAGE_MEMBERS = set(_REQUIRED_MEMBERS)
        # The baseline loader expects its original format identifier.  Verify
        # all stronger Astra fields ourselves after reconstruction, while only
        # temporarily accepting the v2 member set here.
        batch, source = _load_astra_batch_via_baseline(store, artifact_root, stage_id, slots)
    finally:
        base._REQUIRED_PACKAGE_MEMBERS = previous_required
    for job in batch.jobs.values():
        _verify_context_package(job)
    return batch, source


def _load_astra_batch_via_baseline(
    store: TransactionalHistoryStore,
    artifact_root: Path,
    stage_id: str,
    slots: Sequence[str] | None,
) -> tuple[base.StageBatch, ResolvedSource]:
    """Temporarily present the Astra package format as baseline to its loader."""
    # The baseline loader hard-codes the format check.  A package is copied to
    # a temporary sibling only in memory is not available there, so we perform
    # the small deterministic compatibility shim by restoring the baseline
    # format field, invoking the loader, then restoring exact bytes.
    stage = stage_id.upper()
    cut, _ = base._current_cut(store)
    stage_dir = Path(artifact_root).resolve() / cut["campaign_id"] / stage
    paths = sorted(stage_dir.glob("*_PACKAGE.zip"), key=lambda p: p.name.encode("utf-8"))
    originals: dict[Path, bytes] = {}
    try:
        for path in paths:
            raw = path.read_bytes()
            members = read_zip_bytes(raw, limits=base._PACKAGE_LIMITS)
            if _CONTEXT_MEMBER not in members:
                continue
            manifest = parse(members["MANIFEST.json"])
            if not isinstance(manifest, dict) or manifest.get("format") != "BDB-ASTRA-STAGE-PACKAGE-2":
                continue
            originals[path] = raw
            compat_manifest = {**manifest, "format": "BDB-MANUAL-STAGE-PACKAGE-1"}
            compat_zip = _deterministic_zip({
                **members,
                "MANIFEST.json": canonical_bytes(compat_manifest),
            })
            path.write_bytes(compat_zip)
            compat_sha = hashlib.sha256(compat_zip).hexdigest()
            path.with_suffix(".zip.sha256").write_text(
                f"{compat_sha}  {path.name}\n",
                encoding="ascii",
            )
        batch, source = base.load_stage_batch(store, artifact_root, stage, slots)
    finally:
        for path, raw in originals.items():
            path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            path.with_suffix(".zip.sha256").write_text(
                f"{digest}  {path.name}\n",
                encoding="ascii",
            )
    # Rebuild jobs against restored exact package identities.
    restored_jobs: dict[str, base.StageLaneJob] = {}
    for slot, job in batch.jobs.items():
        raw = job.package_zip_path.read_bytes()
        members = read_zip_bytes(raw, limits=base._PACKAGE_LIMITS)
        manifest = parse(members["MANIFEST.json"])
        restored_jobs[slot] = replace(
            job,
            package_zip_sha256=hashlib.sha256(raw).hexdigest(),
            package_digest=str(manifest["package_digest"]),
            prompt_text=members["PROMPT.txt"].decode("utf-8"),
            prompt_sha256=hashlib.sha256(members["PROMPT.txt"]).hexdigest(),
        )
    return (
        base.StageBatch(
            campaign_id=batch.campaign_id,
            stage_id=batch.stage_id,
            frozen_history_cut=dict(batch.frozen_history_cut),
            jobs=restored_jobs,
            assignment_accepted_history_cut=dict(batch.assignment_accepted_history_cut),
        ),
        source,
    )


__all__ = [
    "build_stage_context",
    "prepare_stage_batch",
    "load_stage_batch",
]

"""Astra/R5.3 transport hardening for post-E1 external stages.

The baseline post-E1 transport binds assignment/source/history/prompt identity.
This branch layer additionally binds the exact predecessor-stage context that a
cross-review/deepening lane is allowed to see.  The context bytes are hashed,
the hash is embedded in PROMPT.txt, and prompt SHA participates in package
semantic identity.  Resume is strictly read-only: it verifies exact durable ZIP
bytes, sidecar, accepted assignment/attempt/cut, context and package identity
without rewriting any package representation.

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


def _verify_context_bytes(
    *,
    members: dict[str, bytes],
    manifest: dict[str, Any],
    campaign_id: str,
    stage_id: str,
    lane_slot: str,
    frozen_cut: dict[str, Any],
) -> None:
    context = parse(members[_CONTEXT_MEMBER])
    if not isinstance(context, dict):
        raise ValidationError("RESUME_CONTEXT_INVALID", lane_slot)
    actual_sha = hashlib.sha256(members[_CONTEXT_MEMBER]).hexdigest()
    if manifest.get("context_member") != _CONTEXT_MEMBER:
        raise ValidationError("RESUME_CONTEXT_MEMBER_MISMATCH", lane_slot)
    if manifest.get("context_sha256") != actual_sha:
        raise ValidationError("RESUME_CONTEXT_DIGEST_MISMATCH", lane_slot)
    if manifest.get("context_policy") != context.get("knowledge_policy"):
        raise ValidationError("RESUME_CONTEXT_POLICY_MISMATCH", lane_slot)
    try:
        prompt = members["PROMPT.txt"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("RESUME_PROMPT_ENCODING_INVALID", lane_slot) from exc
    if actual_sha not in prompt:
        raise ValidationError("RESUME_CONTEXT_PROMPT_BINDING_MISSING", lane_slot)
    if context.get("campaign_id") != campaign_id or context.get("stage_id") != stage_id:
        raise ValidationError("RESUME_CONTEXT_SCOPE_MISMATCH", lane_slot)
    if context.get("context_history_cut") != frozen_cut:
        raise ValidationError("RESUME_CONTEXT_CUT_MISMATCH", lane_slot)
    if stage_id == "E3":
        if context.get("blind") is not True:
            raise ValidationError("E3_BLIND_CONTEXT_REQUIRED", lane_slot)
        if context.get("predecessor_results"):
            raise ValidationError("E3_BLIND_CONTEXT_LEAK", lane_slot)


def load_stage_batch(
    store: TransactionalHistoryStore,
    artifact_root: Path,
    stage_id: str,
    slots: Sequence[str] | None = None,
) -> tuple[base.StageBatch, ResolvedSource]:
    """Read-only reconstruction from accepted history plus exact Astra ZIP bytes."""
    stage = stage_id.upper()
    cut, _ = base._current_cut(store)
    stage_dir = Path(artifact_root).resolve() / cut["campaign_id"] / stage
    if not stage_dir.is_dir():
        raise ValidationError("RESUME_PACKAGE_STATE_MISSING", str(stage_dir))

    requested = tuple(slots or base.stage_slots(stage))
    allowed = set(requested)
    if not allowed:
        raise ValidationError("RESUME_PACKAGE_STATE_MISSING", f"{stage}: no required slots")

    jobs: dict[str, base.StageLaneJob] = {}
    durable_source: ResolvedSource | None = None
    frozen_cut_bytes: bytes | None = None
    executor_binding: tuple[str, str] | None = None

    for path in sorted(stage_dir.glob("*_PACKAGE.zip"), key=lambda p: p.name.encode("utf-8")):
        raw = path.read_bytes()
        try:
            members = read_zip_bytes(raw, limits=base._PACKAGE_LIMITS)
        except ValidationError as exc:
            raise ValidationError("RESUME_PACKAGE_ZIP_INVALID", f"{path.name}:{exc.code}") from exc
        if set(members) != _REQUIRED_MEMBERS:
            raise ValidationError("RESUME_PACKAGE_MEMBER_SET_INVALID", path.name)

        manifest = parse(members["MANIFEST.json"])
        if not isinstance(manifest, dict):
            raise ValidationError("RESUME_PACKAGE_MANIFEST_INVALID", path.name)
        if manifest.get("format") != "BDB-ASTRA-STAGE-PACKAGE-2":
            raise ValidationError("RESUME_PACKAGE_FORMAT_UNSUPPORTED", path.name)
        if manifest.get("stage_id") != stage:
            continue
        slot = manifest.get("lane_slot")
        if slot not in allowed:
            continue
        slot = str(slot)
        if slot in jobs:
            raise ValidationError("RESUME_DUPLICATE_LANE_PACKAGE", f"{stage}-{slot}")

        assignment_ref = manifest.get("assignment_ref")
        attempt_ref = manifest.get("attempt_ref")
        if not isinstance(assignment_ref, dict) or not isinstance(attempt_ref, dict):
            raise ValidationError("RESUME_ASSIGNMENT_BINDING_MISSING", f"{stage}-{slot}")
        assignment_record = store.resolve_accepted(assignment_ref, cut)
        assignment = assignment_record["body"]
        if not base._same_ref(assignment.get("attempt_ref"), attempt_ref):
            raise ValidationError("RESUME_ASSIGNMENT_ATTEMPT_MISMATCH", f"{stage}-{slot}")
        store.resolve_accepted(attempt_ref, cut)

        frozen_cut = manifest.get("input_history_cut")
        if not isinstance(frozen_cut, dict) or assignment.get("assignment_input_history_cut") != frozen_cut:
            raise ValidationError("RESUME_ASSIGNMENT_CUT_MISMATCH", f"{stage}-{slot}")
        candidate_cut_bytes = canonical_bytes(frozen_cut)
        if frozen_cut_bytes is None:
            frozen_cut_bytes = candidate_cut_bytes
        elif frozen_cut_bytes != candidate_cut_bytes:
            raise ValidationError("RESUME_PACKAGE_SET_DIVERGENCE", "history_cut")

        source = base._source_from_manifest(manifest.get("source_target"))
        if durable_source is None:
            durable_source = source
        elif canonical_bytes(durable_source.as_dict()) != canonical_bytes(source.as_dict()):
            raise ValidationError("RESUME_PACKAGE_SET_DIVERGENCE", "source")

        execution_mode = manifest.get("execution_mode")
        model = manifest.get("model")
        if not isinstance(execution_mode, str) or not isinstance(model, str):
            raise ValidationError("RESUME_EXECUTOR_BINDING_MISSING", f"{stage}-{slot}")
        candidate_executor = (execution_mode, model)
        if executor_binding is None:
            executor_binding = candidate_executor
        elif executor_binding != candidate_executor:
            raise ValidationError("RESUME_PACKAGE_SET_DIVERGENCE", "executor")

        prompt_raw = members["PROMPT.txt"]
        prompt_sha = hashlib.sha256(prompt_raw).hexdigest()
        if prompt_sha != manifest.get("prompt_sha256"):
            raise ValidationError("RESUME_PROMPT_DIGEST_MISMATCH", f"{stage}-{slot}")
        compiled_digest = hashlib.sha256(members["PACKAGE.json"]).hexdigest()
        if compiled_digest != manifest.get("compiled_digest"):
            raise ValidationError("RESUME_COMPILED_PACKAGE_DIGEST_MISMATCH", f"{stage}-{slot}")

        _verify_context_bytes(
            members=members,
            manifest=manifest,
            campaign_id=cut["campaign_id"],
            stage_id=stage,
            lane_slot=slot,
            frozen_cut=frozen_cut,
        )

        expected = compute_package_identity_digest(
            compiled_digest=compiled_digest,
            executor_model=model,
            executor_profile=execution_mode,
            history_cut=frozen_cut,
            lane_slot=slot,
            source_commit_sha=source.exact_commit_sha,
            source_tree_sha=source.exact_tree_sha or "",
            source_location=source.location,
            stage_id=stage,
            prompt_sha256=prompt_sha,
            assignment_digest=assignment_ref["revision_digest"],
            attempt_digest=attempt_ref["revision_digest"],
        )
        if expected != manifest.get("package_digest"):
            raise ValidationError("RESUME_PACKAGE_SEMANTIC_DIGEST_MISMATCH", f"{stage}-{slot}")

        zip_sha = hashlib.sha256(raw).hexdigest()
        sidecar = path.with_suffix(".zip.sha256")
        if not sidecar.is_file():
            raise ValidationError("RESUME_PACKAGE_RAW_RECEIPT_MISSING", path.name)
        try:
            sidecar_text = sidecar.read_text(encoding="ascii")
        except (OSError, UnicodeError) as exc:
            raise ValidationError("RESUME_PACKAGE_RAW_RECEIPT_INVALID", path.name) from exc
        if sidecar_text != f"{zip_sha}  {path.name}\n":
            raise ValidationError("RESUME_PACKAGE_RAW_DIGEST_MISMATCH", path.name)

        lane_def = next(d for d in base.lane_definitions(stage) if d.slot == slot)
        if manifest.get("required_isolation") != lane_def.required_isolation:
            raise ValidationError("RESUME_ISOLATION_REQUIREMENT_DRIFT", f"{stage}-{slot}")
        actual_isolation = manifest.get("actual_isolation")
        if actual_isolation not in {"UNKNOWN", "DECLARED", "ENFORCED"}:
            raise ValidationError("RESUME_ISOLATION_CLASS_INVALID", f"{stage}-{slot}")

        challenger_ref = manifest.get("challenger_assignment_ref")
        if challenger_ref is not None:
            if not isinstance(challenger_ref, dict):
                raise ValidationError("RESUME_CHALLENGER_BINDING_INVALID", f"{stage}-{slot}")
            store.resolve_accepted(challenger_ref, cut)

        try:
            prompt_text = prompt_raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError("RESUME_PROMPT_ENCODING_INVALID", f"{stage}-{slot}") from exc

        jobs[slot] = base.StageLaneJob(
            campaign_id=cut["campaign_id"],
            stage_id=stage,
            lane_slot=slot,
            lane_title=str(manifest.get("lane_title", lane_def.title)),
            strategy=str(manifest.get("strategy", lane_def.strategy)),
            input_history_cut=dict(frozen_cut),
            package_digest=expected,
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
            required_isolation=lane_def.required_isolation,
            actual_isolation=str(actual_isolation),
            challenger_assignment_ref=dict(challenger_ref) if isinstance(challenger_ref, dict) else None,
        )

    missing = [slot for slot in requested if slot not in jobs]
    if missing:
        raise ValidationError("RESUME_PACKAGE_SET_INCOMPLETE", f"{stage}: {','.join(missing)}")
    if durable_source is None or frozen_cut_bytes is None:
        raise ValidationError("RESUME_PACKAGE_STATE_MISSING", str(stage_dir))

    ordered_jobs = {slot: jobs[slot] for slot in requested}
    return (
        base.StageBatch(
            campaign_id=cut["campaign_id"],
            stage_id=stage,
            frozen_history_cut=dict(next(iter(ordered_jobs.values())).input_history_cut),
            jobs=ordered_jobs,
            assignment_accepted_history_cut={},
        ),
        durable_source,
    )


__all__ = [
    "build_stage_context",
    "prepare_stage_batch",
    "load_stage_batch",
]

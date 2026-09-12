"""Deterministic package compiler for durable parallel E1 assignments (RU03).

A package is a transport representation of an already accepted AssignmentManifest.
All five E1 assignments are accepted before delivery and retain the exact same
assigned input HistoryCut.  Package semantic identity binds the exact prompt
bytes; ZIP RawDigest remains a separate representation identity.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from typing import Any
import zipfile

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from ..orchestration.compiler import PromptPackageCompiler
from ..orchestration.native_ensemble import E1_LANE_SLOTS, E1_LANE_STRATEGIES
from .assignments import AssignmentService, AssignmentSet
from .source_target import ResolvedSource

_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class E1LaneJob:
    """Prepared immutable transport for one already accepted E1 assignment."""
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
    source_commit_sha: str = ""
    executor_profile: str = "ChatGPT / GitHub"
    model: str = "Sol 5.6"
    assignment_ref: dict[str, Any] = field(default_factory=dict)
    attempt_ref: dict[str, Any] = field(default_factory=dict)
    prompt_sha256: str = ""
    source_tree_sha: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "stage_id": self.stage_id,
            "lane_slot": self.lane_slot,
            "lane_title": self.lane_title,
            "strategy": self.strategy,
            "input_history_cut": self.input_history_cut,
            "package_digest": self.package_digest,
            "package_zip_path": str(self.package_zip_path),
            "package_zip_sha256": self.package_zip_sha256,
            "prompt_sha256": self.prompt_sha256,
            "assignment_ref": dict(self.assignment_ref),
            "attempt_ref": dict(self.attempt_ref),
        }


@dataclass(frozen=True)
class E1Batch:
    """All E1 jobs bound to one pre-delivery assignment input cut."""
    campaign_id: str
    stage_id: str
    frozen_history_cut: dict[str, Any]
    jobs: dict[str, E1LaneJob]
    assignment_accepted_history_cut: dict[str, Any] = field(default_factory=dict)

    @property
    def lane_slots(self) -> tuple[str, ...]:
        return tuple(self.jobs.keys())

    def get_job(self, slot: str) -> E1LaneJob:
        return self.jobs[slot]

    @property
    def source_commit_sha(self) -> str:
        for job in self.jobs.values():
            if job.source_commit_sha:
                return job.source_commit_sha
        return ""

    @property
    def executor_profile(self) -> str:
        for job in self.jobs.values():
            if job.executor_profile:
                return job.executor_profile
        return ""

    @property
    def model(self) -> str:
        for job in self.jobs.values():
            if job.model:
                return job.model
        return ""


def _ref_json(ref: dict[str, Any]) -> str:
    return canonical_bytes(ref).decode("utf-8")


def _build_lane_prompt(
    campaign_id: str,
    lane_slot: str,
    lane_title: str,
    strategy: str,
    source: ResolvedSource,
    cut: dict[str, Any],
    assignment_ref: dict[str, Any],
    attempt_ref: dict[str, Any],
    execution_mode: str = "ChatGPT / GitHub",
    model: str = "Sol 5.6",
) -> str:
    """Render exact auditor instructions without a self-referential package digest.

    The result must copy ``package_digest`` from the package MANIFEST.  This lets
    the semantic package identity include the exact prompt bytes while avoiding
    a package-digest -> prompt -> package-digest cycle.
    """
    tree_line = source.exact_tree_sha or "<not supplied>"
    return f"""# BDB AUDIT v2.0.3 — AUDIT JOB: {lane_slot} ({lane_title.upper()})

You are acting as an independent expert auditor for **BDB Audit v2.0.3**.
Audit only the exact source and assignment below. Do not substitute a moving ref,
a different repository, a different model/profile, or another lane's context.

## 1. AUDIT TARGET & DURABLE ASSIGNMENT
- **Repository**: {source.location}
- **Target Ref (locator only)**: {source.ref}
- **Exact Commit Object ID**: `{source.exact_commit_sha}`
- **Exact Tree Object ID**: `{tree_line}`
- **Campaign ID**: `{campaign_id}`
- **Stage ID**: `E1`
- **Lane Slot**: `{lane_slot}`
- **Assigned Scope**: {lane_title}
- **Primary Strategy**: `{strategy}`
- **Executor Profile**: `{execution_mode}`
- **Executor Model**: `{model}`
- **Assignment Ref**: `{_ref_json(assignment_ref)}`
- **Attempt Ref**: `{_ref_json(attempt_ref)}`
- **Assigned History Cut**: Seq {cut.get('accepted_head_seq', 0)} ({cut.get('accepted_head_hash', 'unknown')[:16]}...)

## 2. AUDIT INSTRUCTIONS
1. Inspect the codebase at exact commit `{source.exact_commit_sha}`.
2. Stay within this lane's scope and use strategy `{strategy}`.
3. Identify genuine vulnerabilities, structural flaws, invariant violations, state inconsistencies, or concurrency/resource issues.
4. Preserve concrete evidence: affected paths, locations, observations, commands/tests when used, and limitations.
5. Do not claim ENFORCED isolation merely because this task was opened in a new chat. The assignment records manual transport as DECLARED unless BDB provides enforcement receipts.

## 3. MANDATORY RESULT FORMAT
Return one ZIP containing root `MANIFEST.json`. Copy `package_digest` exactly from
this input package's `MANIFEST.json`; do not invent or recompute it. Preserve the
exact assignment_ref and attempt_ref printed below.

```json
{{
  "kind": "bdb_audit_lane_result",
  "version": "1",
  "campaign_id": "{campaign_id}",
  "stage_id": "E1",
  "lane_slot": "{lane_slot}",
  "executor_profile": "{execution_mode}",
  "executor_model": "{model}",
  "input_package_digest": "<COPY package_digest FROM INPUT MANIFEST.json>",
  "source_commit_sha": "{source.exact_commit_sha}",
  "history_cut": {{
    "campaign_id": "{campaign_id}",
    "accepted_head_seq": {cut.get('accepted_head_seq', 0)},
    "accepted_head_hash": "{cut.get('accepted_head_hash', '')}"
  }},
  "assignment_ref": {_ref_json(assignment_ref)},
  "attempt_ref": {_ref_json(attempt_ref)},
  "findings_count": <number_of_findings>,
  "findings": [
    {{
      "finding_id": "{lane_slot}-F01",
      "statement": "<concise claim>",
      "severity": "<CRITICAL | HIGH | MEDIUM | LOW | INFORMATIONAL>",
      "affected_component": "<path/component>",
      "description": "<full explanation and evidence relationship>"
    }}
  ]
}}
```

Optional evidence members (for example `REPORT.md`, logs, test output, or minimal
fixtures) must be placed in the same ZIP and referenced by stable archive path.
The BDB inbox preserves the original ZIP bytes before semantic parsing.
"""


def compute_package_identity_digest(
    compiled_digest: str,
    executor_model: str,
    executor_profile: str,
    history_cut: dict[str, Any],
    lane_slot: str,
    source_commit_sha: str,
    source_location: str,
    stage_id: str = "E1",
    *,
    prompt_sha256: str = "",
    assignment_digest: str = "",
    attempt_digest: str = "",
    source_tree_sha: str = "",
) -> str:
    """Canonical semantic package identity.

    Optional keyword fields preserve the public helper's compatibility while
    production packaging always supplies them.  The transport ZIP RawDigest is
    intentionally not part of this preimage, avoiding representation self-reference.
    """
    body = {
        "compiled_digest": compiled_digest,
        "prompt_sha256": prompt_sha256,
        "assignment_digest": assignment_digest,
        "attempt_digest": attempt_digest,
        "executor_model": executor_model,
        "executor_profile": executor_profile,
        "history_cut": {
            "accepted_head_hash": history_cut.get("accepted_head_hash", ""),
            "accepted_head_seq": history_cut.get("accepted_head_seq", 0),
            "campaign_id": history_cut.get("campaign_id", ""),
        },
        "lane_slot": lane_slot,
        "source_commit_sha": source_commit_sha,
        "source_tree_sha": source_tree_sha,
        "source_location": source_location,
        "stage_id": stage_id,
    }
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _zip_member(name: str, data: bytes) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(filename=name, date_time=_FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    info.flag_bits = 0
    return info, data


def _deterministic_zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(members, key=lambda value: value.encode("utf-8")):
            info, data = _zip_member(name, members[name])
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return buffer.getvalue()


def _publish_exact(path: Path, raw: bytes) -> None:
    """Atomically publish immutable package bytes or verify an exact retry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValidationError("PACKAGE_PUBLICATION_CONFLICT", path.name)
        return
    fd, temp_name = tempfile.mkstemp(prefix=".bdb-package-", dir=str(path.parent))
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb", closefd=True) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except OSError as exc:
        raise ValidationError("PACKAGE_PUBLICATION_FAILED", type(exc).__name__) from exc
    finally:
        temp.unlink(missing_ok=True)


def _prepare_assignments(
    store: TransactionalHistoryStore,
    execution_mode: str,
    model: str,
) -> AssignmentSet:
    return AssignmentService(store).prepare_e1_assignments(
        executor_profile=execution_mode,
        model=model,
    )


def prepare_e1_batch(
    store: TransactionalHistoryStore,
    output_dir: Path,
    source_info: ResolvedSource,
    execution_mode: str = "ChatGPT / GitHub",
    model: str = "Sol 5.6",
) -> E1Batch:
    """Accept E1 assignments first, then deterministically compile their packages."""
    if execution_mode != "ChatGPT / GitHub":
        raise ValidationError(
            "NEEDS_IMPLEMENTATION",
            f"Execution mode '{execution_mode}' automated packaging is not supported in v2.0.3. "
            "Only 'ChatGPT / GitHub' is implemented in this transport profile.",
        )

    assignments = _prepare_assignments(store, execution_mode, model)
    frozen_cut = assignments.assignment_input_history_cut
    campaign_id = assignments.campaign_id
    e1_dir = Path(output_dir).resolve() / campaign_id / "E1"
    e1_dir.mkdir(parents=True, exist_ok=True)

    compiler = PromptPackageCompiler()
    jobs: dict[str, E1LaneJob] = {}

    for slot in E1_LANE_SLOTS:
        prepared = assignments.assignments[slot]
        lane_title, strategy = E1_LANE_STRATEGIES[slot]
        view_manifest = {
            "allowed_views": [slot],
            "forbidden_knowledge": ["OTHER_LANE_UNSEALED_FINDINGS", "FUTURE_ADJUDICATION_OUTCOMES"],
        }
        prompt_dict = {
            "template": "e1_ensemble",
            "slot": slot,
            "stage_spec_revision": "1",
            "lane_spec_revision": "1",
        }
        compiled = compiler.compile(
            stage_spec_revision="1",
            lane_spec_revision="1",
            executor_revision="1",
            delivery_revision="1",
            projection_policy={"policy": "STRICT_ISOLATION"},
            view_manifest=view_manifest,
            history_cut=frozen_cut,
            prompt=prompt_dict,
        )

        prompt_text = _build_lane_prompt(
            campaign_id=campaign_id,
            lane_slot=slot,
            lane_title=lane_title,
            strategy=strategy,
            source=source_info,
            cut=frozen_cut,
            assignment_ref=prepared.assignment_ref,
            attempt_ref=prepared.attempt_ref,
            execution_mode=execution_mode,
            model=model,
        )
        prompt_raw = prompt_text.encode("utf-8")
        prompt_sha = hashlib.sha256(prompt_raw).hexdigest()
        assignment_digest = prepared.assignment_ref["revision_digest"]
        attempt_digest = prepared.attempt_ref["revision_digest"]

        pkg_identity_digest = compute_package_identity_digest(
            compiled_digest=compiled.digest,
            executor_model=model,
            executor_profile=execution_mode,
            history_cut=frozen_cut,
            lane_slot=slot,
            source_commit_sha=source_info.exact_commit_sha,
            source_tree_sha=source_info.exact_tree_sha or "",
            source_location=source_info.location,
            stage_id="E1",
            prompt_sha256=prompt_sha,
            assignment_digest=assignment_digest,
            attempt_digest=attempt_digest,
        )

        manifest_data = {
            "format": "BDB-F2-PROMPT-PACKAGE-2",
            "campaign_id": campaign_id,
            "stage_id": "E1",
            "lane_slot": slot,
            "lane_title": lane_title,
            "strategy": strategy,
            "package_digest": pkg_identity_digest,
            "compiled_digest": compiled.digest,
            "prompt_sha256": prompt_sha,
            "input_history_cut": frozen_cut,
            "assignment_ref": prepared.assignment_ref,
            "attempt_ref": prepared.attempt_ref,
            "source_target": source_info.as_dict(),
            "execution_mode": execution_mode,
            "model": model,
        }
        manifest_raw = canonical_bytes(manifest_data)
        readme = (
            f"# Audit Package {slot}\n\n"
            "The AssignmentManifest was accepted before this package was published.\n"
            "Deliver PROMPT.txt and this exact ZIP representation to the assigned auditor.\n"
        ).encode("utf-8")
        zip_bytes = _deterministic_zip({
            "MANIFEST.json": manifest_raw,
            "PACKAGE.json": compiled.raw,
            "PROMPT.txt": prompt_raw,
            "README.md": readme,
        })
        zip_sha256 = hashlib.sha256(zip_bytes).hexdigest()

        clean_title = lane_title.replace(" ", "_").replace(",", "").replace("&", "AND")
        zip_filename = f"{slot}_{clean_title}_{pkg_identity_digest[:12]}_PACKAGE.zip"
        zip_path = e1_dir / zip_filename
        _publish_exact(zip_path, zip_bytes)
        receipt_path = zip_path.with_suffix(".zip.sha256")
        receipt_raw = f"{zip_sha256}  {zip_filename}\n".encode("ascii")
        _publish_exact(receipt_path, receipt_raw)

        jobs[slot] = E1LaneJob(
            campaign_id=campaign_id,
            stage_id="E1",
            lane_slot=slot,
            lane_title=lane_title,
            strategy=strategy,
            input_history_cut=dict(frozen_cut),
            package_digest=pkg_identity_digest,
            package_zip_path=zip_path,
            package_zip_sha256=zip_sha256,
            prompt_text=prompt_text,
            source_commit_sha=source_info.exact_commit_sha,
            source_tree_sha=source_info.exact_tree_sha or "",
            executor_profile=execution_mode,
            model=model,
            assignment_ref=dict(prepared.assignment_ref),
            attempt_ref=dict(prepared.attempt_ref),
            prompt_sha256=prompt_sha,
        )

    return E1Batch(
        campaign_id=campaign_id,
        stage_id="E1",
        frozen_history_cut=dict(frozen_cut),
        jobs=jobs,
        assignment_accepted_history_cut=dict(assignments.accepted_history_cut),
    )


__all__ = [
    "E1LaneJob",
    "E1Batch",
    "prepare_e1_batch",
    "compute_package_identity_digest",
]

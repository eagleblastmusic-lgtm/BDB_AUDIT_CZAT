"""Package and prompt compiler for parallel E1 audit lanes (R5.3 §27 / M9).

CRITICAL INVARIANT:
All required E1 lane packages MUST be prepared against the exact same accepted
HistoryCut / SourceGeneration state before any E1 result is imported.
Sequential UI display does not mutate the frozen input cut.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
import zipfile

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from ..orchestration.compiler import PromptPackageCompiler, CompiledPackage
from ..orchestration.native_ensemble import (
    E1_LANE_SLOTS,
    E1_LANE_STRATEGIES,
    build_e1_stage_spec,
    build_e1_lane_specs,
)
from .source_target import ResolvedSource


@dataclass(frozen=True)
class E1LaneJob:
    """A prepared, immutable audit job for one E1 lane."""
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
            "prompt_text": self.prompt_text,
        }


@dataclass(frozen=True)
class E1Batch:
    """Collection of all 5 parallel E1 lane jobs bound to a single frozen HistoryCut."""
    campaign_id: str
    stage_id: str
    frozen_history_cut: dict[str, Any]
    jobs: dict[str, E1LaneJob]  # Keyed by lane_slot: "E1-A" .. "E1-E"

    @property
    def lane_slots(self) -> tuple[str, ...]:
        return tuple(self.jobs.keys())

    def get_job(self, slot: str) -> E1LaneJob:
        return self.jobs[slot]

    @property
    def source_commit_sha(self) -> str:
        for j in self.jobs.values():
            if j.source_commit_sha:
                return j.source_commit_sha
        return ""

    @property
    def executor_profile(self) -> str:
        for j in self.jobs.values():
            if j.executor_profile:
                return j.executor_profile
        return ""

    @property
    def model(self) -> str:
        for j in self.jobs.values():
            if j.model:
                return j.model
        return ""


def _build_lane_prompt(
    campaign_id: str,
    lane_slot: str,
    lane_title: str,
    strategy: str,
    source: ResolvedSource,
    package_digest: str,
    cut: dict[str, Any],
    execution_mode: str = "ChatGPT / GitHub",
    model: str = "Sol 5.6",
) -> str:
    """Generate high-clarity prompt for external auditor session (ChatGPT / GitHub)."""
    return f"""# BDB AUDIT v2.0.3 — AUDIT JOB: {lane_slot} ({lane_title.upper()})

You are acting as an independent expert auditor for **BDB Audit v2.0.3**.
Your task is to conduct an in-depth audit of the specified target repository strictly adhering to your assigned lane scope and strategy.

## 1. AUDIT TARGET & IDENTITY
- **Repository**: {source.location}
- **Target Ref**: {source.ref}
- **Exact Commit SHA**: `{source.exact_commit_sha}`
- **Campaign ID**: `{campaign_id}`
- **Stage ID**: `E1`
- **Lane Slot**: `{lane_slot}`
- **Assigned Scope**: {lane_title}
- **Primary Strategy**: `{strategy}`
- **Input Package Digest**: `{package_digest}`
- **Bound History Cut**: Seq {cut.get('accepted_head_seq', 0)} ({cut.get('accepted_head_hash', 'unknown')[:16]}...)

## 2. AUDIT INSTRUCTIONS
1. Inspect the codebase at the exact commit SHA `{source.exact_commit_sha}`.
2. Focus strictly on your lane's domain:
   - Scope: {lane_title}
   - Methodology: {strategy}
3. Identify genuine vulnerabilities, structural flaws, invariant violations, state inconsistencies, or concurrency issues within your lane scope.
4. Provide concrete evidence, affected paths, line numbers, and impact assessments.

## 3. MANDATORY RESULT FORMAT (RE-IMPORTABLE ZIP)
When your audit is complete, you must package your findings into a single ZIP archive containing:

1. `MANIFEST.json` at the archive root with the following exact metadata:
```json
{{
  "kind": "bdb_audit_lane_result",
  "version": "1",
  "campaign_id": "{campaign_id}",
  "stage_id": "E1",
  "lane_slot": "{lane_slot}",
  "executor_profile": "{execution_mode}",
  "executor_model": "{model}",
  "input_package_digest": "{package_digest}",
  "source_commit_sha": "{source.exact_commit_sha}",
  "history_cut": {{
    "campaign_id": "{campaign_id}",
    "accepted_head_seq": {cut.get('accepted_head_seq', 0)},
    "accepted_head_hash": "{cut.get('accepted_head_hash', '')}"
  }},
  "findings_count": <number_of_findings>,
  "findings": [
    {{
      "finding_id": "{lane_slot}-F01",
      "statement": "<Concise finding description>",
      "severity": "<CRITICAL | HIGH | MEDIUM | LOW | INFORMATIONAL>",
      "affected_component": "<Component/file path>",
      "description": "<Detailed explanation of the issue>"
    }}
  ]
}}
```
2. Optional evidence files or detailed Markdown reports (e.g. `REPORT.md`).

Return the resulting ZIP file to BDB Audit via the result inbox.
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
) -> str:
    """Canonical package identity digest binding inputs deterministically."""
    body = {
        "compiled_digest": compiled_digest,
        "executor_model": executor_model,
        "executor_profile": executor_profile,
        "history_cut": {
            "accepted_head_hash": history_cut.get("accepted_head_hash", ""),
            "accepted_head_seq": history_cut.get("accepted_head_seq", 0),
            "campaign_id": history_cut.get("campaign_id", ""),
        },
        "lane_slot": lane_slot,
        "source_commit_sha": source_commit_sha,
        "source_location": source_location,
        "stage_id": stage_id,
    }
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def prepare_e1_batch(
    store: TransactionalHistoryStore,
    output_dir: Path,
    source_info: ResolvedSource,
    execution_mode: str = "ChatGPT / GitHub",
    model: str = "Sol 5.6",
) -> E1Batch:
    """Compile all 5 E1 packages simultaneously against the exact current accepted head.

    Guarantees that:
    1. E1-A, E1-B, E1-C, E1-D, and E1-E all share the exact same HistoryCut.
    2. No result from any lane can influence another lane package.
    """
    if execution_mode != "ChatGPT / GitHub":
        raise ValidationError(
            "NEEDS_IMPLEMENTATION",
            f"Execution mode '{execution_mode}' automated packaging is not supported in v2.0.3. "
            "Only 'ChatGPT / GitHub' is fully implemented in this version.",
        )

    head = store.head()
    if head is None:
        raise ValueError("Campaign store has no accepted head")

    conn = store._connect()
    try:
        row = conn.execute("SELECT body FROM commits WHERE commit_hash=?", (head.commit_hash,)).fetchone()
        prior_commit = json.loads(row[0]) if row else {}
    finally:
        conn.close()

    frozen_cut = {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": head.campaign_id,
        "accepted_head_seq": head.commit_seq,
        "accepted_head_hash": head.commit_hash,
        "governing_policy_ref": prior_commit.get("governing_policy_ref", "pin:initial_governing_policy_ref"),
        "governing_spec_refs": list(prior_commit.get("governing_spec_refs", ("pin:initial_transition_profile_ref",))),
    }

    e1_dir = output_dir / head.campaign_id / "E1"
    e1_dir.mkdir(parents=True, exist_ok=True)

    compiler = PromptPackageCompiler()
    jobs: dict[str, E1LaneJob] = {}

    for slot in E1_LANE_SLOTS:
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

        # Canonical compilation
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

        pkg_identity_digest = compute_package_identity_digest(
            compiled_digest=compiled.digest,
            executor_model=model,
            executor_profile=execution_mode,
            history_cut=frozen_cut,
            lane_slot=slot,
            source_commit_sha=source_info.exact_commit_sha,
            source_location=source_info.location,
            stage_id="E1",
        )

        prompt_text = _build_lane_prompt(
            campaign_id=head.campaign_id,
            lane_slot=slot,
            lane_title=lane_title,
            strategy=strategy,
            source=source_info,
            package_digest=pkg_identity_digest,
            cut=frozen_cut,
            execution_mode=execution_mode,
            model=model,
        )

        manifest_data = {
            "format": "BDB-F2-PROMPT-PACKAGE-1",
            "campaign_id": head.campaign_id,
            "stage_id": "E1",
            "lane_slot": slot,
            "lane_title": lane_title,
            "strategy": strategy,
            "package_digest": pkg_identity_digest,
            "compiled_digest": compiled.digest,
            "input_history_cut": frozen_cut,
            "source_target": source_info.as_dict(),
            "execution_mode": execution_mode,
            "model": model,
        }

        # Build ZIP archive
        clean_title = lane_title.replace(" ", "_").replace(",", "").replace("&", "AND")
        zip_filename = f"{slot}_{clean_title}_PACKAGE.zip"
        zip_path = e1_dir / zip_filename

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("MANIFEST.json", json.dumps(manifest_data, indent=2, ensure_ascii=False))
            zf.writestr("PROMPT.txt", prompt_text)
            zf.writestr("PACKAGE.json", compiled.raw)
            zf.writestr("README.md", f"# Audit Package {slot}\n\nDeliver PROMPT.txt and this ZIP to ChatGPT.\n")

        # External receipt / checksum (no self-referential digest inside ZIP)
        zip_bytes = zip_path.read_bytes()
        zip_sha256 = hashlib.sha256(zip_bytes).hexdigest()
        receipt_path = zip_path.with_suffix(".zip.sha256")
        receipt_path.write_text(f"{zip_sha256}  {zip_filename}\n", encoding="utf-8")

        jobs[slot] = E1LaneJob(
            campaign_id=head.campaign_id,
            stage_id="E1",
            lane_slot=slot,
            lane_title=lane_title,
            strategy=strategy,
            input_history_cut=frozen_cut,
            package_digest=pkg_identity_digest,
            package_zip_path=zip_path,
            package_zip_sha256=zip_sha256,
            prompt_text=prompt_text,
            source_commit_sha=source_info.exact_commit_sha,
            executor_profile=execution_mode,
            model=model,
        )

    return E1Batch(
        campaign_id=head.campaign_id,
        stage_id="E1",
        frozen_history_cut=frozen_cut,
        jobs=jobs,
    )


__all__ = [
    "E1LaneJob",
    "E1Batch",
    "prepare_e1_batch",
    "compute_package_identity_digest",
]

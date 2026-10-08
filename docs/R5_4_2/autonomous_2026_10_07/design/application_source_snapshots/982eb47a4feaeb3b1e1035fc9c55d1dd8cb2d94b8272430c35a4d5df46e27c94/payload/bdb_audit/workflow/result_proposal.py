"""One raw-to-proposal transform for Inbox and canonical admission checks.

This proves byte provenance, not auditor truth or the original package's
assignment-time authority. Those remain separate admission requirements.
"""
from __future__ import annotations

import hashlib
from typing import Any

from ..assurance.zip_safety import Limits as ZipLimits, read_bytes as read_zip_bytes
from ..core.canonical_json import canonical_bytes, parse
from ..core.errors import ValidationError

RESULT_ZIP_LIMITS = ZipLimits(
    input_bytes=64 * 1024 * 1024,
    central_bytes=4 * 1024 * 1024,
    members=512,
    member_bytes=32 * 1024 * 1024,
    expanded_bytes=50 * 1024 * 1024,
    ratio=500,
)


def media_type(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".json"):
        return "application/json"
    if lower.endswith((".md", ".txt", ".log")):
        return "text/plain"
    if lower.endswith(".xml"):
        return "application/xml"
    return "application/octet-stream"


def member_evidence(members: dict[str, bytes]) -> list[dict[str, Any]]:
    return [
        {"path": name, "raw_digest": hashlib.sha256(raw).hexdigest(),
         "byte_length": len(raw), "media_type": media_type(name)}
        for name, raw in sorted(members.items(), key=lambda item: item[0].encode("utf-8"))
    ]


def derive_result_proposal(
    raw: bytes, members: dict[str, bytes], *, history_cut: dict[str, Any],
    assignment_ref: dict[str, Any], attempt_ref: dict[str, Any],
) -> dict[str, Any]:
    if "MANIFEST.json" not in members:
        raise ValidationError("MISSING_MANIFEST")
    manifest = parse(members["MANIFEST.json"])
    if not isinstance(manifest, dict):
        raise ValidationError("MALFORMED_MANIFEST")
    if manifest.get("kind") != "bdb_audit_lane_result":
        raise ValidationError("INVALID_CONTRACT_KIND")
    if str(manifest.get("version", "")) != "1":
        raise ValidationError("INVALID_CONTRACT_VERSION")
    if manifest.get("campaign_id") != history_cut.get("campaign_id"):
        raise ValidationError("CAMPAIGN_BINDING_MISMATCH")
    result_cut = manifest.get("history_cut")
    if not isinstance(result_cut, dict):
        raise ValidationError("MISSING_MANDATORY_FIELD", "history_cut")
    required = ("campaign_id", "accepted_head_seq", "accepted_head_hash")
    if any(result_cut.get(key) != history_cut.get(key) for key in required):
        raise ValidationError("STALE_CUT")
    if any(value != history_cut.get(key) for key, value in result_cut.items()):
        raise ValidationError("STALE_CUT", "conflicting history context")
    if "admission_evidence_ref" in manifest:
        raise ValidationError("UNAUTHORIZED_PRODUCER_AUTHORITY", "External manifest supplies admission authority")

    if manifest.get("stage_id") == "E1":
        if "findings" in manifest:
            findings = manifest["findings"]
        elif "FINDINGS.json" in members:
            findings = parse(members["FINDINGS.json"])
        else:
            raise ValidationError("MISSING_MANDATORY_FIELD", "findings")
        if not isinstance(findings, list):
            raise ValidationError("INVALID_FINDING_STRUCTURE")
        if "findings_count" in manifest and manifest["findings_count"] != len(findings):
            raise ValidationError("FINDINGS_COUNT_MISMATCH")
        if any(not isinstance(f, dict) or not f.get("statement") or not (f.get("finding_id") or f.get("title")) for f in findings):
            raise ValidationError("INVALID_FINDING_STRUCTURE")
    else:
        findings = manifest.get("findings", [])
        if not isinstance(findings, list) or any(not isinstance(f, dict) for f in findings):
            raise ValidationError("INVALID_FINDING_STRUCTURE")
        if not isinstance(manifest.get("outputs", {}), dict):
            raise ValidationError("INVALID_OUTPUT_STRUCTURE")

    proposal = dict(manifest)
    proposal.update(
        history_cut=dict(history_cut), assignment_ref=dict(assignment_ref),
        attempt_ref=dict(attempt_ref), findings=findings,
        raw_result_digest=hashlib.sha256(raw).hexdigest(),
        raw_result_byte_length=len(raw), evidence_files=member_evidence(members),
    )
    if manifest.get("stage_id") == "E1":
        proposal["findings_count"] = len(findings)
    else:
        proposal["outputs"] = manifest.get("outputs", {})
    return proposal


def verify_admission_bytes(body: dict[str, Any], *, vault, assignment: dict[str, Any]) -> dict[str, Any]:
    """Check the claimed proposal/members against raw bytes and accepted cut."""
    raw = vault.read_bytes(body["raw_result_digest"])
    if len(raw) != body.get("raw_result_byte_length"):
        raise ValidationError("RAW_RESULT_BYTE_LENGTH_MISMATCH")
    members = read_zip_bytes(raw, limits=RESULT_ZIP_LIMITS)
    proposal = derive_result_proposal(
        raw, members, history_cut=assignment["assignment_input_history_cut"],
        assignment_ref=body["assignment_ref"], attempt_ref=body["attempt_ref"],
    )
    if hashlib.sha256(canonical_bytes(proposal)).hexdigest() != body.get("result_proposal_digest"):
        raise ValidationError("RESULT_PROPOSAL_DIGEST_MISMATCH")
    if body.get("evidence_files") != proposal["evidence_files"]:
        raise ValidationError("RESULT_MEMBER_EVIDENCE_MISMATCH")
    if body.get("phase_id") != assignment.get("phase_id") or proposal.get("phase_id") != assignment.get("phase_id"):
        raise ValidationError("PHASE_BINDING_MISMATCH")

    # Raw identity and context are necessary but do not establish the original
    # assignment-time package identity; see the unresolved R2 contract gate.
    package_raw = vault.read_bytes(body.get("package_zip_sha256", ""))
    package_members = read_zip_bytes(package_raw)
    package = parse(package_members.get("MANIFEST.json", b"null"))
    if not isinstance(package, dict):
        raise ValidationError("PACKAGE_MANIFEST_INVALID")
    for package_field, evidence_field in (
        ("campaign_id", "campaign_id"), ("stage_id", "stage_id"),
        ("phase_id", "phase_id"), ("lane_slot", "lane_slot"),
        ("package_digest", "input_package_digest"), ("execution_mode", "executor_profile"),
        ("model", "executor_model"), ("input_history_cut", "history_cut"),
    ):
        if package.get(package_field) != body.get(evidence_field):
            raise ValidationError("PACKAGE_CONTEXT_MISMATCH", package_field)
    from ..history.authority_hooks import _typed_ref_identity
    for field in ("assignment_ref", "attempt_ref"):
        if _typed_ref_identity(package.get(field)) != _typed_ref_identity(body.get(field)):
            raise ValidationError("PACKAGE_CONTEXT_MISMATCH", field)
    source = package.get("source_target")
    if not isinstance(source, dict) or str(source.get("exact_commit_sha", "")).lower() != str(body.get("source_commit_sha", "")).lower():
        raise ValidationError("PACKAGE_SOURCE_COMMIT_MISMATCH")
    return proposal

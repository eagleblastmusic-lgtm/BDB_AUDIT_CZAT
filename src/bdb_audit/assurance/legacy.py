"""Mechanical extraction from frozen v1.4.4 (M0 SHA d851511f...).

Migration §§2,7 / Roadmap M3. Historical validation reports do not establish
native-v2 accepted state. No runtime import of the frozen application or its UI.
"""
from pathlib import Path, PurePosixPath
import datetime as dt
import hashlib
import json
import re
import zipfile
from .zip_safety import read_zip, Limits, ArchiveInput, snapshot
from ..core.errors import ValidationError

APP_VERSION = "1.4.4"
DATA = {"wrapper_release": "5.4-RC1", "payloads": {
    "canonical_project_plan": {
        "name": "BDB_vNext_Project_Plan_v1.json",
        "sha256": "e78461a6fdfd83237d1fc65c8bddf551d00dc9b438610991d12d4b4d15706da6"},
    "canonical_audit_plan": {
        "name": "BDB_vNext_Audit_i_Plan_Nastepnej_Iteracji (1).md",
        "sha256": "f1cbd849140f25a22e80758067d8bf7d348cdd7ec76b877f58aef81397c3eb07"}}}


def validate_previous_prompt_bundle(path, *, consumer_variant_id,
                                    predecessor_variant_id, bundle_sha256, prompt_hashes):
    """Migration §4.1; exact external predecessor metadata, never fixture verdicts."""
    errors = []
    members = _read_handoff_members(path, errors)
    try:
        if sha256_file(path) != bundle_sha256:
            errors.append("PREVIOUS_PROMPT_BUNDLE_HASH_MISMATCH")
        manifest = json.loads(members["PREVIOUS_PROMPTS_MANIFEST.json"])
        if manifest["consumer_variant_id"] != consumer_variant_id:
            errors.append("PREVIOUS_PROMPT_CONSUMER_MISMATCH")
        if manifest["expected_predecessor_variant_id"] != predecessor_variant_id:
            errors.append("PREVIOUS_PROMPT_PREDECESSOR_MISMATCH")
        rows = manifest["prompt_files"]
        declared = {row["filename"]: row["sha256"] for row in rows}
        if len(declared) != len(rows) or declared != prompt_hashes:
            errors.append("PREVIOUS_PROMPT_DECLARATION_MISMATCH")
        if set(members) != {"PREVIOUS_PROMPTS_MANIFEST.json", *prompt_hashes}:
            errors.append("PREVIOUS_PROMPT_MEMBERSHIP_MISMATCH")
        for name, digest in prompt_hashes.items():
            if name not in members or sha256_bytes(members[name]) != digest:
                errors.append("PREVIOUS_PROMPT_HASH_MISMATCH: " + name)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        errors.append("PREVIOUS_PROMPT_INVALID: " + str(exc))
    return {"status": "FAIL" if errors else "PASS", "errors": errors}

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    if type(path) is ArchiveInput:
        return sha256_bytes(path.raw)
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_handoff(step: dict, variant: dict) -> str | None:
    folder = step["folder"].upper()
    if step["order"] <= 1:
        return None
    if "CANONICAL" in folder:
        return "F1_HANDOFF_BUNDLE.zip"
    if "PREVIOUS_PROMPT" in folder:
        return "POST_CANONICAL_HANDOFF_BUNDLE.zip" if variant["plus_pliki"] else "F1_HANDOFF_BUNDLE.zip"
    if "PREVIOUS_REPORT" in folder:
        return "F2_HANDOFF_BUNDLE.zip"
    return None


def expected_attestation(step: dict) -> str | None:
    folder = step["folder"].upper()
    if "CANONICAL" in folder:
        return "PRE_CANONICAL_REVEAL_GATE_PASS_ATTESTATION.zip"
    if "PREVIOUS_PROMPT" in folder:
        return "PRE_PREVIOUS_PROMPT_REVEAL_GATE_PASS_ATTESTATION.zip"
    if "PREVIOUS_REPORT" in folder:
        return "PRE_PREVIOUS_REPORT_REVEAL_GATE_PASS_ATTESTATION.zip"
    return None


def expected_manual_run_state(step: dict) -> str | None:
    """Return the wrapper-declared transport STOP state for a reveal fallback."""
    material = "\n".join(
        str(value)
        for value in (
            step.get("primary_instruction", ""),
            (step.get("primary_prompt") or {}).get("text", ""),
            step.get("fallback_instruction", ""),
            (step.get("fallback_prompt") or {}).get("text", ""),
        )
    )
    match = re.search(r"\bAWAITING_MANUAL_[A-Z0-9_]+\b", material)
    return match.group(0) if match else None


def attestation_json_basename(step: dict) -> str | None:
    name = expected_attestation(step)
    return name[:-4] + ".json" if name and name.lower().endswith(".zip") else None


def expected_staged_payload_metadata(variant: dict, step: dict) -> list[dict]:
    """Describe only the payload identity that the app can know before reveal."""
    folder = step["folder"].upper()
    if "CANONICAL" in folder:
        result = []
        for key in ("canonical_project_plan", "canonical_audit_plan"):
            item = DATA["payloads"][key]
            result.append({"filename": item["name"], "sha256": item["sha256"]})
        return result
    if "PREVIOUS_PROMPT" in folder:
        bundles = step.get("previous_prompt_bundles", [])
        if len(bundles) != 1:
            raise RuntimeError("Brak jednoznacznego previous-prompt bundle dla continuation ticket")
        item = bundles[0]
        return [{"filename": item["name"], "sha256": item["sha256"]}]
    if "PREVIOUS_REPORT" in folder:
        predecessor = variant.get("direct_predecessor_variant_id")
        if not predecessor:
            raise RuntimeError("Brak direct predecessor dla previous-report reveal")
        return [{
            "filename": "ACTUAL_DIRECT_PREDECESSOR_FINAL_BUNDLE.zip",
            "expected_predecessor_variant_id": predecessor,
            "sha256": None,
        }]
    return []


def _false_like(value: object) -> bool:
    if value is False or value == 0:
        return True
    if isinstance(value, str) and value.strip().upper() in {"NO", "FALSE", "0", "NONE", "NOT_CREATED"}:
        return True
    return False


def _true_like(value: object) -> bool:
    if value is True or value == 1:
        return True
    if isinstance(value, str) and value.strip().upper() in {"YES", "TRUE", "1", "PASS"}:
        return True
    return False


def _attestation_payload_rows(document: dict) -> list[dict]:
    for key in ("expected_next_payload_metadata", "expected_next_payloads", "expected_payloads"):
        value = document.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _read_handoff_members(path: Path, errors: list[str], *, member_limit=100*1024*1024) -> dict[str, bytes]:
    try:
        return read_zip(path, limits=Limits(member_bytes=member_limit), errors=errors)
    except (ValidationError, OSError) as exc:
        errors.append(str(exc) if isinstance(exc, ValidationError) else f"ZIP_OPEN_FAILURE: {exc}")
        return {}


def _handoff_by_basename(
    members: dict[str, bytes],
    errors: list[str],
    basename: str,
    warnings: list[str] | None = None,
) -> str | None:
    """Resolve one logical handoff artifact without false ambiguity.

    Root-level machine artifacts are authoritative when present.  Identical evidence/
    archival copies with the same basename are tolerated and reported as warnings.
    Conflicting duplicate bytes remain fail-closed.
    """
    rows = [name for name in members if PurePosixPath(name).name == basename]
    if not rows:
        return None

    root = basename if basename in members else None
    if root is not None:
        duplicates = [name for name in rows if name != root]
        if duplicates:
            root_raw = members[root]
            conflicting = [name for name in duplicates if members[name] != root_raw]
            if conflicting:
                errors.append(
                    f"CONFLICTING_DUPLICATE_HANDOFF_MEMBER: {basename}: {conflicting}"
                )
                return None
            if warnings is not None:
                warnings.append(
                    f"IDENTICAL_DUPLICATE_HANDOFF_MEMBER_IGNORED: {basename}: {duplicates}"
                )
        return root

    if len(rows) == 1:
        return rows[0]

    first_raw = members[rows[0]]
    if all(members[name] == first_raw for name in rows[1:]):
        selected = sorted(rows, key=lambda name: (len(PurePosixPath(name).parts), name))[0]
        if warnings is not None:
            warnings.append(
                f"IDENTICAL_DUPLICATE_HANDOFF_MEMBER_ACCEPTED: {basename}: selected={selected}"
            )
        return selected

    errors.append(f"AMBIGUOUS_HANDOFF_MEMBER: {basename}: {rows}")
    return None


def _doc_get_ci(document: dict, *keys: str) -> object | None:
    """Case-insensitive machine-key lookup with exact spelling preferred."""
    if not isinstance(document, dict):
        return None
    for key in keys:
        if key in document:
            return document[key]
    folded = {str(key).casefold(): value for key, value in document.items()}
    for key in keys:
        if key.casefold() in folded:
            return folded[key.casefold()]
    return None


def _validate_handoff_hash_manifest(members: dict[str, bytes], errors: list[str]) -> None:
    manifest_name = _handoff_by_basename(members, errors, "ARTIFACT_HASHES.sha256")
    if not manifest_name:
        errors.append("MISSING_HANDOFF_ARTIFACT_HASHES")
        return
    try:
        text = members[manifest_name].decode("utf-8")
        if text and not text.endswith("\n"):
            errors.append("HANDOFF_ARTIFACT_HASHES_MISSING_FINAL_LF")
        declared: dict[str, str] = {}
        order: list[str] = []
        for line in text.splitlines():
            match = re.fullmatch(r"([0-9a-f]{64})  ([^\\]+)", line)
            if not match:
                errors.append(f"INVALID_HANDOFF_HASH_LINE: {line[:160]}")
                continue
            digest, rel = match.groups()
            if rel in declared:
                errors.append(f"DUPLICATE_HANDOFF_HASH_PATH: {rel}")
            declared[rel] = digest
            order.append(rel)
        if order != sorted(order):
            errors.append("HANDOFF_HASH_PATHS_NOT_SORTED")
        expected = set(members) - {manifest_name}
        if set(declared) != expected:
            errors.append(
                "HANDOFF_HASH_MEMBERSHIP_MISMATCH: "
                f"missing={sorted(expected - set(declared))}, extra={sorted(set(declared) - expected)}"
            )
        for rel, digest in declared.items():
            raw = members.get(rel)
            if raw is not None and sha256_bytes(raw) != digest:
                errors.append(f"HANDOFF_HASH_MISMATCH: {rel}")
    except Exception as exc:
        errors.append(f"HANDOFF_HASH_VALIDATION_FAILURE: {exc}")


def _parse_json_object_member(members: dict[str, bytes], errors: list[str], basename: str, required: bool = True) -> tuple[str | None, dict]:
    name = _handoff_by_basename(members, errors, basename)
    if not name:
        if required:
            errors.append(f"MISSING_HANDOFF_MEMBER: {basename}")
        return None, {}
    try:
        value = json.loads(members[name].decode("utf-8"))
        if not isinstance(value, dict):
            errors.append(f"HANDOFF_JSON_NOT_OBJECT: {basename}")
            return name, {}
        return name, value
    except Exception as exc:
        errors.append(f"HANDOFF_JSON_PARSE_FAILURE: {basename}: {exc}")
        return name, {}


def _parse_jsonl_records(raw: bytes, label: str, errors: list[str]) -> list[dict]:
    records: list[dict] = []
    try:
        for idx, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                errors.append(f"{label}_RECORD_NOT_OBJECT: line={idx}")
                continue
            records.append(value)
    except Exception as exc:
        errors.append(f"{label}_JSONL_PARSE_FAILURE: {exc}")
    return records


def _validate_seq(records: list[dict], label: str, errors: list[str]) -> tuple[int | None, int | None]:
    if not records:
        errors.append(f"{label}_EMPTY")
        return None, None
    seqs = [row.get("seq") for row in records]
    if not all(isinstance(value, int) for value in seqs):
        errors.append(f"{label}_NON_INTEGER_SEQ")
        return None, None
    expected = list(range(seqs[0], seqs[0] + len(seqs)))
    if seqs != expected:
        errors.append(f"{label}_NON_CONTIGUOUS_SEQ: observed={seqs[:20]}")
    return seqs[0], seqs[-1]


def validate_prior_handoff_bundle(path: Path, variant: dict, step: dict) -> dict:
    """Validate the exact physical preceding handoff before any +PLIKI reveal.

    Canonical reveal gets a strict F1 gate. Later reveal handoffs receive the same
    ZIP/hash/variant/run/source/checkpoint/ledger-prefix treatment with their expected
    checkpoint family.  This is a launcher preflight; the wrapper/model must reverify.
    """
    errors: list[str] = []
    warnings: list[str] = []
    expected_name = expected_handoff(step, variant)
    if not expected_name:
        return {
            "schema": "BDB_PRIOR_HANDOFF_VALIDATION_V1",
            "status": "FAIL",
            "errors": ["STEP_HAS_NO_EXPECTED_PRIOR_HANDOFF"],
            "warnings": [],
        }

    members = _read_handoff_members(path, errors)
    if members:
        _validate_handoff_hash_manifest(members, errors)

    run_name, run = _parse_json_object_member(members, errors, "RUN_MANIFEST.json")
    checkpoint_kind = "F1" if expected_name == "F1_HANDOFF_BUNDLE.zip" else "F2" if expected_name == "F2_HANDOFF_BUNDLE.zip" else "F1"
    checkpoint_basename = "F1_SOURCE_CHECKPOINT.json" if checkpoint_kind == "F1" else None
    checkpoint_name: str | None = None
    checkpoint: dict = {}
    if checkpoint_kind == "F1":
        checkpoint_name, checkpoint = _parse_json_object_member(members, errors, checkpoint_basename)
    else:
        candidates = [
            name for name in members
            if "F2" in PurePosixPath(name).name.upper() and "CHECKPOINT" in PurePosixPath(name).name.upper()
        ]
        if len(candidates) != 1:
            errors.append(f"F2_CHECKPOINT_MEMBER_COUNT_INVALID: {candidates}")
        else:
            checkpoint_name = candidates[0]
            try:
                value = json.loads(members[checkpoint_name].decode("utf-8"))
                checkpoint = value if isinstance(value, dict) else {}
                if not checkpoint:
                    errors.append("F2_CHECKPOINT_INVALID")
            except Exception as exc:
                errors.append(f"F2_CHECKPOINT_PARSE_FAILURE: {exc}")

    for label, doc in (("RUN_MANIFEST", run), (f"{checkpoint_kind}_CHECKPOINT", checkpoint)):
        if doc and doc.get("variant_id") != variant["variant_id"]:
            errors.append(
                f"{label}_VARIANT_MISMATCH: expected={variant['variant_id']} actual={doc.get('variant_id')}"
            )

    # Gate state is a stage-level fact.  Resolve it from the dedicated
    # stage/final-status artifact first and treats absent duplicate copies in the
    # run manifest/checkpoint as absence, not contradiction.
    _, stage = _parse_json_object_member(members, errors, "STAGE_STATUS.json", required=False)
    _, final_status = _parse_json_object_member(
        members, errors, "F1_HANDOFF_FINAL_STATUS.json", required=False
    ) if checkpoint_kind == "F1" else (None, {})

    run_state = _doc_get_ci(run, "run_state") if run else None
    checkpoint_state = _doc_get_ci(checkpoint, "run_state") if checkpoint else None
    stage_state = _doc_get_ci(stage, "run_state") if stage else None
    final_state = _doc_get_ci(final_status, "run_state") if final_status else None
    resolved_run_state = stage_state or final_state or run_state or checkpoint_state

    if expected_name == "F1_HANDOFF_BUNDLE.zip" and "CANONICAL" in step["folder"].upper():
        required_state = "AWAITING_CANONICAL_REVEAL_AFTER_VALID_F1"
        if resolved_run_state != required_state:
            errors.append(
                f"F1_RUN_STATE_MISMATCH: expected={required_state} actual={resolved_run_state}"
            )
        for label, value in (
            ("STAGE_STATUS", stage_state),
            ("F1_HANDOFF_FINAL_STATUS", final_state),
            ("RUN_MANIFEST", run_state),
            ("F1_CHECKPOINT", checkpoint_state),
        ):
            if value is not None and value != required_state:
                errors.append(
                    f"F1_RUN_STATE_CONTRADICTION: {label}: expected={required_state} actual={value}"
                )

        flag_candidates = [
            ("STAGE_STATUS", _doc_get_ci(stage, "f1_written_and_read_back_before_reveal") if stage else None),
            ("F1_HANDOFF_FINAL_STATUS", _doc_get_ci(final_status, "f1_written_and_read_back_before_reveal") if final_status else None),
            ("F1_CHECKPOINT", _doc_get_ci(checkpoint, "f1_written_and_read_back_before_reveal") if checkpoint else None),
            ("RUN_MANIFEST", _doc_get_ci(run, "f1_written_and_read_back_before_reveal") if run else None),
        ]
        present_flags = [(label, value) for label, value in flag_candidates if value is not None]
        if not any(_true_like(value) for _, value in present_flags):
            errors.append(
                "F1_WRITTEN_AND_READ_BACK_BEFORE_REVEAL_NOT_YES: "
                + repr(present_flags)
            )
        for label, value in present_flags:
            if _false_like(value):
                errors.append(
                    f"F1_READBACK_FLAG_CONTRADICTION: {label}: actual={value}"
                )

    # Exact run identity continuity: accept manifest's explicit attempt/request IDs or
    # legacy run_id/audit_id aliases, but require exact agreement with checkpoint.
    if checkpoint:
        cp_request = checkpoint.get("audit_request_id", checkpoint.get("audit_id"))
        cp_attempt = checkpoint.get("audit_attempt_id", checkpoint.get("run_id"))
        run_request = run.get("audit_request_id", run.get("audit_id")) if run else None
        run_attempt = run.get("audit_attempt_id", run.get("run_id")) if run else None
        if not cp_request or not cp_attempt:
            errors.append("HANDOFF_MISSING_AUDIT_REQUEST_OR_ATTEMPT_ID")
        if run and (not run_request or not run_attempt):
            errors.append("RUN_MANIFEST_MISSING_AUDIT_REQUEST_OR_ATTEMPT_ID")
        if cp_request and run_request and cp_request != run_request:
            errors.append(f"AUDIT_REQUEST_ID_MISMATCH: checkpoint={cp_request} manifest={run_request}")
        if cp_attempt and run_attempt and cp_attempt != run_attempt:
            errors.append(f"AUDIT_ATTEMPT_ID_MISMATCH: checkpoint={cp_attempt} manifest={run_attempt}")

    # Frozen source identity must be present and internally consistent.
    cp_sha = checkpoint.get("source_sha") if checkpoint else None
    cp_tree = checkpoint.get("source_tree") if checkpoint else None
    resolved = run.get("resolved_source_identity") if isinstance(run.get("resolved_source_identity"), dict) else {} if run else {}
    run_sha = resolved.get("source_sha") if isinstance(resolved, dict) else None
    run_tree = resolved.get("source_tree") if isinstance(resolved, dict) else None
    if not cp_sha or not cp_tree:
        errors.append("CHECKPOINT_MISSING_FROZEN_SOURCE_IDENTITY")
    if run and (not run_sha or not run_tree):
        warnings.append("RUN_MANIFEST_HAS_NO_RESOLVED_SOURCE_IDENTITY_OBJECT")
    if cp_sha and run_sha and cp_sha != run_sha:
        errors.append(f"SOURCE_SHA_MISMATCH: checkpoint={cp_sha} manifest={run_sha}")
    if cp_tree and run_tree and cp_tree != run_tree:
        errors.append(f"SOURCE_TREE_MISMATCH: checkpoint={cp_tree} manifest={run_tree}")

    # Locate final ledger and exact retained checkpoint snapshot.
    ledger_candidates = [
        name for name in members
        if PurePosixPath(name).name in {"AUDIT_LEDGER.jsonl", "AUDIT_LEDGER.json"}
    ]
    if len(ledger_candidates) != 1:
        errors.append(f"AUDIT_LEDGER_MEMBER_COUNT_INVALID: {ledger_candidates}")
        ledger_name = None
    else:
        ledger_name = ledger_candidates[0]

    snapshot_candidates = [
        name for name in members
        if checkpoint_kind in PurePosixPath(name).name.upper()
        and "LEDGER" in PurePosixPath(name).name.upper()
        and "SNAPSHOT" in PurePosixPath(name).name.upper()
        and "DIGEST" not in PurePosixPath(name).name.upper()
        and PurePosixPath(name).suffix.lower() != ".sha256"
    ]
    if len(snapshot_candidates) != 1:
        errors.append(f"{checkpoint_kind}_SNAPSHOT_MEMBER_COUNT_INVALID: {snapshot_candidates}")
        snapshot_name = None
    else:
        snapshot_name = snapshot_candidates[0]

    snapshot_sha = checkpoint.get("retained_ledger_snapshot_sha256") if checkpoint else None
    if snapshot_name:
        actual_snapshot_sha = sha256_bytes(members[snapshot_name])
        if not snapshot_sha:
            errors.append("CHECKPOINT_MISSING_RETAINED_LEDGER_SNAPSHOT_SHA256")
        elif snapshot_sha != actual_snapshot_sha:
            errors.append(
                f"RETAINED_LEDGER_SNAPSHOT_HASH_MISMATCH: expected={snapshot_sha} actual={actual_snapshot_sha}"
            )
    else:
        actual_snapshot_sha = None

    if ledger_name and snapshot_name:
        if not members[ledger_name].startswith(members[snapshot_name]):
            errors.append(f"{checkpoint_kind}_LEDGER_RAW_PREFIX_MISMATCH")
        snap_records = _parse_jsonl_records(members[snapshot_name], f"{checkpoint_kind}_SNAPSHOT", errors)
        ledger_records = _parse_jsonl_records(members[ledger_name], "AUDIT_LEDGER", errors)
        _, snap_end = _validate_seq(snap_records, f"{checkpoint_kind}_SNAPSHOT", errors)
        _, ledger_end = _validate_seq(ledger_records, "AUDIT_LEDGER", errors)
        if snap_records and ledger_records and ledger_records[: len(snap_records)] != snap_records:
            errors.append(f"{checkpoint_kind}_LEDGER_PARSED_PREFIX_MISMATCH")
        declared_end = checkpoint.get("f1_ledger_sequence_end") if checkpoint_kind == "F1" else checkpoint.get("f2_ledger_sequence_end")
        if isinstance(declared_end, int) and snap_end != declared_end:
            errors.append(
                f"{checkpoint_kind}_DECLARED_SEQUENCE_END_MISMATCH: expected={declared_end} actual={snap_end}"
            )
    else:
        snap_end = ledger_end = None

    # A durable checkpoint handoff requires a machine digest record; when supplied it
    # must agree exactly with the raw checkpoint/ledger/snapshot bytes.
    digest_candidates = [
        name for name in members
        if checkpoint_kind in PurePosixPath(name).name.upper()
        and "DIGEST" in PurePosixPath(name).name.upper()
        and PurePosixPath(name).suffix.lower() == ".json"
    ]
    if not digest_candidates:
        errors.append(f"MISSING_{checkpoint_kind}_DIGEST_RECORD")
    else:
        for digest_name in digest_candidates:
            try:
                digest_doc = json.loads(members[digest_name].decode("utf-8"))
            except Exception:
                continue
            if not isinstance(digest_doc, dict):
                continue
            if checkpoint_name and digest_doc.get("checkpoint_sha256") and digest_doc["checkpoint_sha256"] != sha256_bytes(members[checkpoint_name]):
                errors.append(f"{checkpoint_kind}_DIGEST_CHECKPOINT_HASH_MISMATCH")
            if ledger_name and digest_doc.get("audit_ledger_sha256") and digest_doc["audit_ledger_sha256"] != sha256_bytes(members[ledger_name]):
                errors.append(f"{checkpoint_kind}_DIGEST_LEDGER_HASH_MISMATCH")
            if snapshot_name and digest_doc.get("retained_ledger_snapshot_sha256") and digest_doc["retained_ledger_snapshot_sha256"] != sha256_bytes(members[snapshot_name]):
                errors.append(f"{checkpoint_kind}_DIGEST_SNAPSHOT_HASH_MISMATCH")
            for key in ("ledger_prefix_continuity", "readback_byte_identity"):
                if key in digest_doc and str(digest_doc.get(key)).upper() != "PASS":
                    errors.append(f"{checkpoint_kind}_DIGEST_{key.upper()}_NOT_PASS")

    # F1 continuation additionally requires the recorded pre-F1 source-integrity
    # readback to exist and bind the same frozen source identity.
    if checkpoint_kind == "F1":
        preferred_readback = _handoff_by_basename(
            members, errors, "PRE_F1_SOURCE_INTEGRITY_READBACK.json", warnings
        )
        if preferred_readback:
            readback_candidates = [preferred_readback]
        else:
            readback_candidates = [
                name for name in members
                if "PRE_F1" in PurePosixPath(name).name.upper()
                and "READBACK" in PurePosixPath(name).name.upper()
                and PurePosixPath(name).suffix.lower() == ".json"
                and not name.lower().startswith("evidence/")
            ]
        if len(readback_candidates) != 1:
            errors.append(f"PRE_F1_SOURCE_READBACK_MEMBER_COUNT_INVALID: {readback_candidates}")
        else:
            try:
                readback = json.loads(members[readback_candidates[0]].decode("utf-8"))
                if not isinstance(readback, dict):
                    raise TypeError("readback root is not an object")
                status_value = str(readback.get("status", readback.get("source_integrity_readback", "PASS"))).upper()
                if status_value not in {"PASS", "YES", "TRUE"}:
                    errors.append(f"PRE_F1_SOURCE_READBACK_NOT_PASS: {status_value}")
                rb_sha = readback.get("source_sha", readback.get("pristine_head"))
                rb_tree = readback.get("source_tree", readback.get("pristine_tree"))
                if cp_sha and rb_sha and cp_sha != rb_sha:
                    errors.append(f"PRE_F1_SOURCE_READBACK_SHA_MISMATCH: checkpoint={cp_sha} readback={rb_sha}")
                if cp_tree and rb_tree and cp_tree != rb_tree:
                    errors.append(f"PRE_F1_SOURCE_READBACK_TREE_MISMATCH: checkpoint={cp_tree} readback={rb_tree}")
                if readback.get("identity_match") is False:
                    errors.append("PRE_F1_SOURCE_READBACK_IDENTITY_MATCH_FALSE")
                if str(readback.get("pristine_tracked_status", "CLEAN")).upper() not in {"CLEAN", ""}:
                    errors.append("PRE_F1_SOURCE_READBACK_TRACKED_STATE_NOT_CLEAN")
            except Exception as exc:
                errors.append(f"PRE_F1_SOURCE_READBACK_PARSE_FAILURE: {exc}")

    # Dedicated stage/final-status records are authoritative for the reveal gate.
    # Missing redundant fields in RUN_MANIFEST/F1 checkpoint are allowed; explicit
    # contradictory values are not.
    for label, status_doc in (("STAGE_STATUS", stage), ("F1_HANDOFF_FINAL_STATUS", final_status)):
        if not status_doc:
            continue
        status_variant = _doc_get_ci(status_doc, "variant_id")
        if status_variant is not None and status_variant != variant["variant_id"]:
            errors.append(f"{label}_VARIANT_MISMATCH")

    if stage and expected_name == "F1_HANDOFF_BUNDLE.zip":
        canonical_read = _doc_get_ci(stage, "canonical_read")
        if canonical_read is not None and not _false_like(canonical_read):
            errors.append(f"STAGE_STATUS_CANONICAL_READ_NOT_NO: {canonical_read}")
        f2_created = _doc_get_ci(stage, "f2_created")
        if f2_created is not None and not _false_like(f2_created):
            errors.append(f"STAGE_STATUS_F2_CREATED_NOT_NO: {f2_created}")
        prefix_status = _doc_get_ci(stage, "f1_ledger_prefix_continuity")
        if prefix_status is not None and str(prefix_status).upper() != "PASS":
            errors.append(f"STAGE_STATUS_F1_LEDGER_PREFIX_NOT_PASS: {prefix_status}")
        digest_status = _doc_get_ci(stage, "f1_checkpoint_digest_binding")
        if digest_status is not None and str(digest_status).upper() != "PASS":
            errors.append(f"STAGE_STATUS_F1_DIGEST_BINDING_NOT_PASS: {digest_status}")
        source_status = _doc_get_ci(stage, "pre_f1_source_integrity_readback")
        if source_status is not None and str(source_status).upper() != "PASS":
            errors.append(f"STAGE_STATUS_PRE_F1_SOURCE_READBACK_NOT_PASS: {source_status}")

    return {
        "schema": "BDB_PRIOR_HANDOFF_VALIDATION_V1",
        "status": "PASS" if not errors else "FAIL",
        "app_version": APP_VERSION,
        "expected_handoff_filename": expected_name,
        "variant_id": variant["variant_id"],
        "krok": step["order"],
        "zip_path": str(path),
        "zip_sha256": sha256_file(path),
        "member_count": len(members),
        "checkpoint_kind": checkpoint_kind,
        "audit_request_id": checkpoint.get("audit_request_id", checkpoint.get("audit_id")) if checkpoint else None,
        "audit_attempt_id": checkpoint.get("audit_attempt_id", checkpoint.get("run_id")) if checkpoint else None,
        "run_state": resolved_run_state,
        "run_state_source": (
            "STAGE_STATUS" if stage_state is not None else
            "F1_HANDOFF_FINAL_STATUS" if final_state is not None else
            "RUN_MANIFEST" if run_state is not None else
            "F1_CHECKPOINT" if checkpoint_state is not None else None
        ),
        "source_sha": cp_sha,
        "source_tree": cp_tree,
        "retained_snapshot_sha256": actual_snapshot_sha,
        "snapshot_sequence_end": snap_end,
        "ledger_sequence_end": ledger_end,
        "errors": errors,
        "warnings": warnings,
        "validated_at_local": dt.datetime.now().astimezone().isoformat(),
    }


def validate_attestation_bundle(
    path: Path,
    variant: dict,
    step: dict,
    ticket: dict | None = None,
) -> dict:
    """Fail-closed local validation before the app physically releases staged payloads."""
    errors: list[str] = []
    warnings: list[str] = []
    expected_zip_name = expected_attestation(step)
    expected_json_name = attestation_json_basename(step)
    expected_state = expected_manual_run_state(step)
    if not expected_zip_name or not expected_json_name or not expected_state:
        return {
            "schema": "BDB_GATE_ATTESTATION_VALIDATION_V1",
            "status": "FAIL",
            "errors": ["STEP_HAS_NO_RECOGNIZED_REVEAL_ATTESTATION_CONTRACT"],
            "warnings": [],
        }

    member_bytes: dict[str, bytes] = {}
    member_bytes = _read_handoff_members(path, errors, member_limit=32*1024*1024)

    by_base: dict[str, list[str]] = {}
    for name in member_bytes:
        by_base.setdefault(PurePosixPath(name).name, []).append(name)

    def unique_base(name: str) -> str | None:
        rows = by_base.get(name, [])
        if len(rows) > 1:
            errors.append(f"AMBIGUOUS_ATTESTATION_MEMBER: {name}")
            return None
        return rows[0] if rows else None

    att_name = unique_base(expected_json_name)
    if not att_name:
        errors.append(f"MISSING_EXPECTED_ATTESTATION_JSON: {expected_json_name}")
        attestation: dict = {}
    else:
        try:
            parsed = json.loads(member_bytes[att_name].decode("utf-8"))
            attestation = parsed if isinstance(parsed, dict) else {}
            if not isinstance(parsed, dict):
                errors.append("ATTESTATION_JSON_NOT_OBJECT")
        except Exception as exc:
            errors.append(f"ATTESTATION_JSON_PARSE_FAILURE: {exc}")
            attestation = {}

    hashes_name = unique_base("ARTIFACT_HASHES.sha256")
    if not hashes_name:
        errors.append("MISSING_ATTESTATION_HASH_MANIFEST")
    else:
        try:
            text = member_bytes[hashes_name].decode("utf-8")
            declarations: dict[str, str] = {}
            order: list[str] = []
            for line in text.splitlines():
                match = re.fullmatch(r"([0-9a-f]{64})  ([^\\]+)", line)
                if not match:
                    errors.append(f"INVALID_ATTESTATION_HASH_LINE: {line[:160]}")
                    continue
                digest, rel = match.groups()
                if rel in declarations:
                    errors.append(f"DUPLICATE_ATTESTATION_HASH_PATH: {rel}")
                declarations[rel] = digest
                order.append(rel)
            if order != sorted(order):
                errors.append("ATTESTATION_HASH_PATHS_NOT_SORTED")
            expected_paths = set(member_bytes) - {hashes_name}
            if set(declarations) != expected_paths:
                errors.append(
                    "ATTESTATION_HASH_MEMBERSHIP_MISMATCH: "
                    f"missing={sorted(expected_paths - set(declarations))}, "
                    f"extra={sorted(set(declarations) - expected_paths)}"
                )
            for rel, digest in declarations.items():
                raw = member_bytes.get(rel)
                if raw is not None and sha256_bytes(raw) != digest:
                    errors.append(f"ATTESTATION_HASH_MISMATCH: {rel}")
        except Exception as exc:
            errors.append(f"ATTESTATION_HASH_VALIDATION_FAILURE: {exc}")

    if attestation:
        if attestation.get("variant_id") != variant["variant_id"]:
            errors.append(
                f"ATTESTATION_VARIANT_MISMATCH: expected={variant['variant_id']} actual={attestation.get('variant_id')}"
            )
        if attestation.get("krok") != step["order"]:
            errors.append(f"ATTESTATION_KROK_MISMATCH: expected={step['order']} actual={attestation.get('krok')}")
        if str(attestation.get("delivery_mode", "")).upper() != "PRIMARY":
            errors.append("ATTESTATION_DELIVERY_MODE_NOT_PRIMARY")
        if str(attestation.get("gate_result", "")).upper() != "PASS":
            errors.append("ATTESTATION_GATE_RESULT_NOT_PASS")
        if attestation.get("run_state") != expected_state:
            errors.append(
                f"ATTESTATION_RUN_STATE_MISMATCH: expected={expected_state} actual={attestation.get('run_state')}"
            )
        if not _false_like(attestation.get("staged_payload_semantics_exposed_before_attestation", False)):
            errors.append("ATTESTATION_EARLY_STAGED_SEMANTICS_EXPOSURE")
        if "source_generations_mixed" in attestation and not _false_like(attestation.get("source_generations_mixed")):
            errors.append("ATTESTATION_SOURCE_GENERATIONS_MIXED")
        if "substitute_f2_created" in attestation and not _false_like(attestation.get("substitute_f2_created")):
            errors.append("ATTESTATION_SUBSTITUTE_F2_CREATED")
        for key in ("attestation_is_checkpoint", "attestation_is_audit_checkpoint", "attestation_is_f2"):
            if key in attestation and not _false_like(attestation.get(key)):
                errors.append(f"ATTESTATION_FORBIDDEN_FLAG_TRUE: {key}")

        expected_payloads = expected_staged_payload_metadata(variant, step)
        rows = _attestation_payload_rows(attestation)
        folder = step["folder"].upper()
        if "PREVIOUS_REPORT" in folder:
            predecessor = variant.get("direct_predecessor_variant_id")
            serialized = json.dumps(attestation, ensure_ascii=False, sort_keys=True)
            if predecessor and predecessor not in serialized:
                warnings.append(
                    "ATTESTATION_DOES_NOT_EXPLICITLY_NAME_DIRECT_PREDECESSOR; wrapper/model must re-check lineage before reveal"
                )
        elif expected_payloads:
            if not rows:
                errors.append("ATTESTATION_MISSING_EXPECTED_NEXT_PAYLOAD_METADATA")
            else:
                actual_map: dict[str, str | None] = {}
                for row in rows:
                    filename = row.get("filename")
                    digest = row.get("required_sha256", row.get("sha256"))
                    if isinstance(filename, str):
                        actual_map[filename] = digest if isinstance(digest, str) else None
                for expected in expected_payloads:
                    name = expected["filename"]
                    digest = expected.get("sha256")
                    if name not in actual_map:
                        errors.append(f"ATTESTATION_EXPECTED_PAYLOAD_MISSING: {name}")
                    elif digest and actual_map.get(name) != digest:
                        errors.append(
                            f"ATTESTATION_EXPECTED_PAYLOAD_HASH_MISMATCH: {name}: expected={digest} actual={actual_map.get(name)}"
                        )

    if ticket:
        if ticket.get("schema") != "BDB_CONTINUATION_TICKET_V1":
            errors.append("CONTINUATION_TICKET_SCHEMA_MISMATCH")
        if ticket.get("variant_id") != variant["variant_id"]:
            errors.append("CONTINUATION_TICKET_VARIANT_MISMATCH")
        if ticket.get("step_order") != step["order"]:
            errors.append("CONTINUATION_TICKET_STEP_MISMATCH")
        if ticket.get("expected_attestation_filename") != expected_zip_name:
            errors.append("CONTINUATION_TICKET_ATTESTATION_NAME_MISMATCH")
        if ticket.get("expected_run_state") != expected_state:
            errors.append("CONTINUATION_TICKET_RUN_STATE_MISMATCH")
        fallback_prompt = step.get("fallback_prompt") or {}
        if ticket.get("fallback_prompt_sha256") != fallback_prompt.get("sha256"):
            errors.append("CONTINUATION_TICKET_FALLBACK_PROMPT_MISMATCH")
        prior = ticket.get("prior_handoff_validation") if isinstance(ticket.get("prior_handoff_validation"), dict) else {}
        if prior:
            att_run_id = attestation.get("run_id", attestation.get("audit_attempt_id")) if attestation else None
            att_audit_id = attestation.get("audit_id", attestation.get("audit_request_id")) if attestation else None
            expected_run_id = prior.get("audit_attempt_id")
            expected_audit_id = prior.get("audit_request_id")
            if expected_run_id and att_run_id != expected_run_id:
                errors.append(f"ATTESTATION_RUN_ID_MISMATCH_WITH_PRIOR_HANDOFF: expected={expected_run_id} actual={att_run_id}")
            if expected_audit_id and att_audit_id != expected_audit_id:
                errors.append(f"ATTESTATION_AUDIT_ID_MISMATCH_WITH_PRIOR_HANDOFF: expected={expected_audit_id} actual={att_audit_id}")
            frozen = attestation.get("frozen_source_identity") if isinstance(attestation.get("frozen_source_identity"), dict) else {} if attestation else {}
            if prior.get("source_sha") and frozen.get("source_sha") and prior.get("source_sha") != frozen.get("source_sha"):
                errors.append("ATTESTATION_SOURCE_SHA_MISMATCH_WITH_PRIOR_HANDOFF")
            if prior.get("source_tree") and frozen.get("source_tree") and prior.get("source_tree") != frozen.get("source_tree"):
                errors.append("ATTESTATION_SOURCE_TREE_MISMATCH_WITH_PRIOR_HANDOFF")
            if ticket.get("prior_handoff_sha256") and prior.get("zip_sha256") and ticket.get("prior_handoff_sha256") != prior.get("zip_sha256"):
                errors.append("CONTINUATION_TICKET_PRIOR_HANDOFF_SHA_MISMATCH")

    return {
        "schema": "BDB_GATE_ATTESTATION_VALIDATION_V1",
        "status": "PASS" if not errors else "FAIL",
        "app_version": APP_VERSION,
        "variant_id": variant["variant_id"],
        "krok": step["order"],
        "expected_attestation_filename": expected_zip_name,
        "expected_run_state": expected_state,
        "zip_path": str(path),
        "zip_sha256": sha256_file(path),
        "member_count": len(member_bytes),
        "attestation_run_id": attestation.get("run_id", attestation.get("audit_attempt_id")) if attestation else None,
        "attestation_audit_id": attestation.get("audit_id", attestation.get("audit_request_id")) if attestation else None,
        "attestation_source_identity": attestation.get("frozen_source_identity") if attestation else None,
        "errors": errors,
        "warnings": warnings,
        "validated_at_local": dt.datetime.now().astimezone().isoformat(),
    }


def expected_artifact_family(variant: dict, step: dict) -> str:
    folder = step["folder"].upper()
    if "FULL_FIRST_PASS" in folder or "PREVIOUS_REPORT" in folder:
        return "FINAL_AUDIT_BUNDLE"
    if "CANONICAL" in folder:
        return "FINAL_AUDIT_BUNDLE" if variant["audit_level"] == "BASE" else "POST_CANONICAL_HANDOFF"
    if "PREVIOUS_PROMPT" in folder:
        return "F2_HANDOFF"
    return "F1_HANDOFF"


def collect_json_identities(value, found: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in {"variant_id", "current_variant_id", "audit_id", "direct_parent_variant_id"} and isinstance(child, str):
                found.add(child)
            collect_json_identities(child, found)
    elif isinstance(value, list):
        for child in value:
            collect_json_identities(child, found)


def iter_json_string_values(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from iter_json_string_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_json_string_values(child)
    elif isinstance(value, str):
        yield value


def json_has_key(value, expected_key: str) -> bool:
    if isinstance(value, dict):
        return expected_key in value or any(json_has_key(child, expected_key) for child in value.values())
    if isinstance(value, list):
        return any(json_has_key(child, expected_key) for child in value)
    return False


def validate_result_bundle(path: Path, variant: dict, step: dict, fallback: bool) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    prompt = step["fallback_prompt"] if fallback else step["primary_prompt"]
    expected_family = expected_artifact_family(variant, step)
    member_bytes: dict[str, bytes] = {}

    # A PRIMARY reveal-step may correctly end at the transport-only STOP rather
    # than with FINAL artifacts. Detect that artifact family before applying the
    # normal final/handoff validator.
    if not fallback and step.get("fallback_prompt"):
        expected_json = attestation_json_basename(step)
        try:
            probe_members = _read_handoff_members(path, errors)
            basenames = {PurePosixPath(name).name for name in probe_members}
            if expected_json and expected_json in basenames:
                att = validate_attestation_bundle(path, variant, step)
                return {
                    "schema": "BDB_AUDIT_RESULT_VALIDATION_V1",
                    "status": "PASS_INTERMEDIATE" if att["status"] == "PASS" else "FAIL",
                    "result_type": "PRE_REVEAL_GATE_ATTESTATION",
                    "continuation_required": att["status"] == "PASS",
                    "next_action": "FALLBACK_CONTINUATION" if att["status"] == "PASS" else "FIX_ATTESTATION_OR_RETRY_PRIMARY",
                    "app_version": APP_VERSION,
                    "wrapper_release": DATA["wrapper_release"],
                    "expected_variant_id": variant["variant_id"],
                    "expected_step_order": step["order"],
                    "expected_delivery_mode": "PRIMARY",
                    "expected_attestation_filename": expected_attestation(step),
                    "zip_path": str(path),
                    "zip_sha256": sha256_file(path),
                    "member_count": att.get("member_count"),
                    "errors": att["errors"],
                    "warnings": att["warnings"],
                    "attestation_validation": att,
                    "validated_at_local": dt.datetime.now().astimezone().isoformat(),
                }
        except zipfile.BadZipFile:
            pass

    member_bytes = _read_handoff_members(path, errors, member_limit=100*1024*1024)

    by_basename: dict[str, list[str]] = {}
    for name in member_bytes:
        by_basename.setdefault(PurePosixPath(name).name, []).append(name)

    def exact_member(basename: str) -> str | None:
        matches = by_basename.get(basename, [])
        if len(matches) > 1:
            errors.append(f"AMBIGUOUS_REQUIRED_MEMBER: {basename}")
            return None
        return matches[0] if matches else None

    parsed_json: dict[str, object] = {}
    for name, raw in member_bytes.items():
        if name.lower().endswith(".json"):
            try:
                parsed_json[name] = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                if "LEDGER" in PurePosixPath(name).name.upper():
                    try:
                        parsed_json[name] = [
                            json.loads(line)
                            for line in raw.decode("utf-8").splitlines()
                            if line.strip()
                        ]
                    except Exception as ledger_exc:
                        errors.append(f"JSON_OR_JSONL_PARSE_FAILURE: {name}: {ledger_exc}")
                else:
                    errors.append(f"JSON_PARSE_FAILURE: {name}: {exc}")

    required_common = [
        "RUN_MANIFEST.json",
        "ARTIFACT_HASHES.sha256",
        "ORACLE_INDEPENDENCE_RECORD.json",
    ]
    for basename in required_common:
        if not exact_member(basename):
            errors.append(f"MISSING_REQUIRED_MACHINE_ARTIFACT: {basename}")
    if not (exact_member("AUDIT_LEDGER.jsonl") or exact_member("AUDIT_LEDGER.json")):
        errors.append("MISSING_REQUIRED_MACHINE_ARTIFACT: AUDIT_LEDGER.jsonl|legacy-json")
    elif exact_member("AUDIT_LEDGER.json") and not exact_member("AUDIT_LEDGER.jsonl"):
        warnings.append(f"LEGACY_AUDIT_LEDGER_JSON_ACCEPTED_FOR_BACKWARD_COMPATIBILITY; app v{APP_VERSION} contract uses AUDIT_LEDGER.jsonl")

    if expected_family in {"F1_HANDOFF", "FINAL_AUDIT_BUNDLE"}:
        if not exact_member("F1_SOURCE_CHECKPOINT.json"):
            errors.append("MISSING_REQUIRED_MACHINE_ARTIFACT: F1_SOURCE_CHECKPOINT.json")
        f1_snapshots = [
            name for name in member_bytes
            if "F1" in PurePosixPath(name).name.upper()
            and "LEDGER" in PurePosixPath(name).name.upper()
            and "SNAPSHOT" in PurePosixPath(name).name.upper()
            and "DIGEST" not in PurePosixPath(name).name.upper()
            and PurePosixPath(name).suffix.lower() != ".sha256"
        ]
        if not f1_snapshots:
            errors.append("MISSING_F1_RETAINED_LEDGER_SNAPSHOT")
        if not any(
            "F1" in PurePosixPath(name).name.upper() and "DIGEST" in PurePosixPath(name).name.upper()
            for name in member_bytes
        ):
            errors.append("MISSING_F1_SNAPSHOT_DIGEST_RECORD")

    if expected_family == "F2_HANDOFF" or (
        expected_family == "FINAL_AUDIT_BUNDLE" and variant["audit_level"] != "BASE"
    ):
        if not any(
            "F2" in PurePosixPath(name).name.upper() and "CHECKPOINT" in PurePosixPath(name).name.upper()
            for name in member_bytes
        ):
            errors.append("MISSING_F2_CHECKPOINT")
        if not any(
            "F2" in PurePosixPath(name).name.upper()
            and "LEDGER" in PurePosixPath(name).name.upper()
            and "SNAPSHOT" in PurePosixPath(name).name.upper()
            and "DIGEST" not in PurePosixPath(name).name.upper()
            for name in member_bytes
        ):
            errors.append("MISSING_F2_RETAINED_LEDGER_SNAPSHOT")

    if expected_family == "FINAL_AUDIT_BUNDLE":
        for basename in (
            "FINAL_OUTCOME.json",
            "FINAL_TECHNICAL_AUDIT_REPORT.md",
            "FINAL_SOURCE_INTEGRITY_READBACK.json",
        ):
            if not exact_member(basename):
                errors.append(f"MISSING_REQUIRED_FINAL_ARTIFACT: {basename}")
        if variant["audit_level"] != "BASE" and not exact_member("LINEAGE_MANIFEST.json"):
            errors.append("MISSING_REQUIRED_FINAL_ARTIFACT: LINEAGE_MANIFEST.json")

    run_name = exact_member("RUN_MANIFEST.json")
    if run_name and run_name in parsed_json:
        run_manifest = parsed_json[run_name]
        identities: set[str] = set()
        collect_json_identities(run_manifest, identities)
        if variant["variant_id"] not in identities:
            errors.append(
                f"RUN_MANIFEST_VARIANT_MISMATCH: expected {variant['variant_id']}, found {sorted(identities)}"
            )
        values = set(iter_json_string_values(run_manifest))
        for expected, label in (
            (APP_VERSION, "APP_VERSION"),
            (DATA["wrapper_release"], "WRAPPER_RELEASE"),
            (prompt["sha256"], "PROMPT_SHA256"),
        ):
            if expected not in values:
                errors.append(f"RUN_MANIFEST_MISSING_EXPECTED_{label}: {expected}")
        if not (
            json_has_key(run_manifest, "execution_context_sha256")
            or json_has_key(run_manifest, "bdb_execution_context_sha256")
        ):
            errors.append("RUN_MANIFEST_MISSING_EXECUTION_CONTEXT_SHA256")

    hashes_name = exact_member("ARTIFACT_HASHES.sha256")
    if hashes_name:
        try:
            hash_text = member_bytes[hashes_name].decode("utf-8")
            if hash_text and not hash_text.endswith("\n"):
                errors.append("ARTIFACT_HASHES_MISSING_FINAL_LF")
            declarations: dict[str, str] = {}
            declaration_order: list[str] = []
            for line in hash_text.splitlines():
                match = re.fullmatch(r"([0-9a-f]{64})  ([^\\]+)", line)
                if not match:
                    errors.append(f"INVALID_ARTIFACT_HASH_LINE: {line[:160]}")
                    continue
                digest, rel = match.groups()
                if rel in declarations:
                    errors.append(f"DUPLICATE_ARTIFACT_HASH_PATH: {rel}")
                declarations[rel] = digest
                declaration_order.append(rel)
            if declaration_order != sorted(declaration_order):
                errors.append("ARTIFACT_HASH_PATHS_NOT_SORTED")
            expected_paths = set(member_bytes) - {hashes_name}
            if set(declarations) != expected_paths:
                errors.append(
                    "ARTIFACT_HASH_MEMBERSHIP_MISMATCH: "
                    f"missing={sorted(expected_paths - set(declarations))}, "
                    f"extra={sorted(set(declarations) - expected_paths)}"
                )
            for rel, digest in declarations.items():
                raw = member_bytes.get(rel)
                if raw is not None and sha256_bytes(raw) != digest:
                    errors.append(f"ARTIFACT_HASH_MISMATCH: {rel}")
        except Exception as exc:
            errors.append(f"ARTIFACT_HASH_VALIDATION_FAILURE: {exc}")

    ledger_name = exact_member("AUDIT_LEDGER.jsonl") or exact_member("AUDIT_LEDGER.json")
    if ledger_name:
        for checkpoint in ("F1", "F2"):
            snapshots = [
                name for name in member_bytes
                if checkpoint in PurePosixPath(name).name.upper()
                and "LEDGER" in PurePosixPath(name).name.upper()
                and "SNAPSHOT" in PurePosixPath(name).name.upper()
                and "DIGEST" not in PurePosixPath(name).name.upper()
            ]
            if snapshots and not member_bytes[ledger_name].startswith(member_bytes[snapshots[0]]):
                errors.append(f"{checkpoint}_LEDGER_RAW_PREFIX_MISMATCH")

    text_parts = []
    for name, raw in member_bytes.items():
        if len(raw) <= 8 * 1024 * 1024 and PurePosixPath(name).suffix.lower() in {
            ".md", ".txt", ".json", ".jsonl", ".ndjson"
        }:
            text_parts.append(raw.decode("utf-8", errors="replace"))
    combined_upper = "\n".join(text_parts).upper()

    if variant["audit_level"] == "BASE":
        forbidden_name_tokens = [
            name for name in member_bytes
            if "F2" in PurePosixPath(name).name.upper()
            or "PREVIOUS_REPORT" in PurePosixPath(name).name.upper()
            or "PREVIOUS_PROMPT" in PurePosixPath(name).name.upper()
        ]
        if forbidden_name_tokens:
            errors.append(f"BASE_FORBIDDEN_ARTIFACTS_PRESENT: {sorted(forbidden_name_tokens)}")
        for marker in (
            "NEXT-ITERATION TECHNICAL AUDIT REPORT",
            "F2_PRE_REPORT_CHECKPOINT",
            "PREVIOUS-REPORT REVEAL",
        ):
            if marker in combined_upper:
                errors.append(f"BASE_FORBIDDEN_PHASE_EVIDENCE: {marker}")
        if re.search(r"AUD-0*1", combined_upper) and "ADJUDIC" in combined_upper:
            errors.append("BASE_PREVIOUS_FINDING_ADJUDICATION_DETECTED")
        if "DOCS/GOVERNANCE" in combined_upper and (
            "CANONICAL REQUIREMENTS REVEALED" in combined_upper
            or "CANONICAL REVEAL" in combined_upper
        ):
            errors.append("BASE_SOURCE_NATIVE_DOC_SUBSTITUTED_AS_STAGED_CANONICAL")

    claimed_complete = bool(
        re.search(r"PROTOCOL[_ ]CONFORMANCE.{0,80}\bCOMPLETE\b", combined_upper, flags=re.S)
    )
    if claimed_complete and errors:
        errors.append("COMPLETE_CLAIM_INVALIDATED_BY_FAILED_MECHANICAL_OR_PROFILE_GATES")

    return {
        "schema": "BDB_AUDIT_RESULT_VALIDATION_V1",
        "status": "PASS" if not errors else "FAIL",
        "app_version": APP_VERSION,
        "wrapper_release": DATA["wrapper_release"],
        "expected_variant_id": variant["variant_id"],
        "expected_audit_profile": variant["profile"],
        "expected_step_order": step["order"],
        "expected_step_folder": step["folder"],
        "expected_delivery_mode": "FALLBACK" if fallback else "PRIMARY",
        "expected_prompt_filename": prompt["name"],
        "expected_prompt_sha256": prompt["sha256"],
        "expected_artifact_family": expected_family,
        "zip_path": str(path),
        "zip_sha256": sha256_file(path),
        "member_count": len(member_bytes),
        "errors": errors,
        "warnings": warnings,
        "validated_at_local": dt.datetime.now().astimezone().isoformat(),
    }


def _snapshot_validator(validate):
    from functools import wraps

    @wraps(validate)
    def bound(path, *args, **kwargs):
        try:
            owned = snapshot(path)
        except (OSError, ValidationError) as exc:
            return {"status": "FAIL", "errors": [str(exc) if isinstance(exc, ValidationError)
                                                   else "ZIP_OPEN_FAILURE: " + str(exc)], "warnings": []}
        return validate(owned, *args, **kwargs)
    return bound


validate_prior_handoff_bundle = _snapshot_validator(validate_prior_handoff_bundle)
validate_attestation_bundle = _snapshot_validator(validate_attestation_bundle)
validate_result_bundle = _snapshot_validator(validate_result_bundle)
validate_previous_prompt_bundle = _snapshot_validator(validate_previous_prompt_bundle)

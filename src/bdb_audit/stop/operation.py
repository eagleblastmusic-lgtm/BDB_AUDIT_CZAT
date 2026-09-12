"""Operational STOP gate entry point for CLI/UI surfaces.

This module keeps STOP evaluation in the domain layer. It can evaluate the
latest accepted ``stop_input`` in a campaign, or preview an explicitly supplied
STOP input artifact. Preview inputs are never promoted to accepted authority.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from .evaluator import evaluate_stop
from .models import StopInput


_METADATA_KEYS = {
    "kind",
    "version",
    "schema_revision_ref",
    "logical_id",
    "revision_digest",
    "digest_profile",
    "ref_class",
}


def _artifact_body(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise ValidationError("STOP_INPUT_FILE_NOT_FOUND", f"File does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationError("MALFORMED_STOP_INPUT", f"Could not parse STOP input JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("MALFORMED_STOP_INPUT", "STOP input root must be a JSON object")

    if data.get("kind") == "stop_input" and isinstance(data.get("body"), dict):
        return dict(data["body"])
    if data.get("kind") == "stop_input":
        return {key: value for key, value in data.items() if key not in _METADATA_KEYS}
    if "campaign_id" in data and "evaluation_context" in data:
        return dict(data)
    raise ValidationError(
        "STOP_INPUT_KIND_REQUIRED",
        "Expected a stop_input canonical object, stop_input body, or {kind: stop_input, body: ...} envelope",
    )


def _latest_accepted_stop_input(store: TransactionalHistoryStore) -> tuple[dict[str, Any], str, int] | None:
    """Return the newest stop_input referenced by an accepted commit along with commit seq."""
    conn = store._connect()
    try:
        rows = conn.execute("SELECT seq, body FROM commits ORDER BY seq DESC").fetchall()
    finally:
        conn.close()

    for seq, raw in rows:
        commit = json.loads(raw)
        refs = commit.get("immutable_object_refs", [])
        for ref in reversed(refs):
            if not isinstance(ref, dict) or ref.get("kind") != "stop_input":
                continue
            digest = ref.get("revision_digest")
            if not isinstance(digest, str):
                continue
            record = store.object_record(digest)
            if record and isinstance(record.get("body"), dict):
                return dict(record["body"]), digest, seq
    return None


def _require_current_campaign_cut(
    stop_input: StopInput,
    store: TransactionalHistoryStore,
    *,
    authoritative: bool = True,
    accepted_commit_seq: int | None = None,
) -> None:
    head = store.head()
    if head is None:
        raise ValidationError("CAMPAIGN_NOT_FOUND", "Campaign contains no accepted head")

    if stop_input.campaign_id != head.campaign_id:
        raise ValidationError(
            "STOP_INPUT_CAMPAIGN_MISMATCH",
            f"STOP input campaign {stop_input.campaign_id} does not match active campaign {head.campaign_id}",
        )

    cut = dict(stop_input.input_history_cut)
    cut_campaign = cut.get("campaign_id")
    cut_seq = cut.get("accepted_head_seq")
    if cut_seq is None:
        cut_seq = cut.get("commit_seq")
    cut_hash = cut.get("accepted_head_hash") or cut.get("commit_hash")

    if cut_campaign != head.campaign_id:
        raise ValidationError(
            "STOP_INPUT_CUT_MISMATCH",
            f"STOP input cut campaign {cut_campaign} does not match head {head.campaign_id}",
        )

    # For preview / non-authoritative inputs, cut must match the active campaign head exactly
    if not authoritative or accepted_commit_seq is None:
        if cut_seq != head.commit_seq or cut_hash != head.commit_hash:
            raise ValidationError(
                "STOP_INPUT_CUT_MISMATCH",
                "STOP input is stale or is not bound to the current accepted campaign head",
            )
        return

    # For accepted history stop_input: cut_seq cannot be greater than the commit where it was accepted
    if cut_seq > accepted_commit_seq:
        raise ValidationError(
            "STOP_INPUT_CUT_MISMATCH",
            f"Accepted STOP input cut {cut_seq} exceeds its acceptance commit {accepted_commit_seq}",
        )

    # If head has moved past cut_seq, verify no material audit drift occurred in intermediate commits.
    # Allowed intermediate commits are administrative: stop_input, stop_evaluation, campaign_conclusion,
    # final_assurance_case, release_qualification. Any stages, findings, or claims invalidate the cut.
    if cut_seq < head.commit_seq:
        administrative_kinds = {
            "command_envelope",
            "stop_input",
            "stop_evaluation",
            "campaign_conclusion",
            "final_assurance_case",
            "release_qualification",
            "successor_campaign_selection_decision",
        }
        for commit in store.commits():
            c_seq = commit.get("commit_seq", 0)
            if c_seq <= cut_seq or c_seq > head.commit_seq:
                continue
            refs = commit.get("immutable_object_refs", [])
            for ref in refs:
                kind = ref.get("kind") if isinstance(ref, dict) else None
                if kind and kind not in administrative_kinds:
                    raise ValidationError(
                        "STOP_INPUT_CUT_MISMATCH",
                        f"Material audit changes occurred after STOP input cut at commit seq {c_seq} (kind: {kind})",
                    )


def _next_action(decision: str, authoritative: bool) -> str:
    if not authoritative:
        return "ACCEPT_STOP_INPUT_BEFORE_AUTHORITATIVE_DECISION"
    return {
        "PASS": "COMPLETE_CAMPAIGN",
        "E6_REQUIRED": "PREPARE_E6",
        "CONTINUE_REQUIRED": "CONTINUE_REQUIRED_WORK",
        "BLOCKED": "RESOLVE_STOP_BLOCKERS",
    }.get(decision, "REVIEW_STOP_RESULT")


def evaluate_stop_gate(
    store_path: str | Path,
    *,
    stop_input_path: str | Path | None = None,
    e6_plan_approved: bool = False,
) -> dict[str, Any]:
    """Evaluate the STOP gate for a campaign without bypassing accepted authority.

    With no ``stop_input_path`` this function uses the newest accepted STOP input
    from campaign history. If none exists, it returns a fail-closed operational
    result instead of leaving the UI at an impossible next action.

    A supplied file is evaluated only as a preview. Its result is explicitly
    non-authoritative and cannot complete the campaign.
    """
    path = Path(store_path).resolve()
    if not path.exists() or path.stat().st_size == 0:
        raise ValidationError("CAMPAIGN_NOT_FOUND", f"No database found at {path}")

    store = TransactionalHistoryStore(path)
    head = store.head()
    if head is None:
        raise ValidationError("CAMPAIGN_NOT_FOUND", f"Store at {path} contains no accepted commits")

    authoritative = stop_input_path is None
    source = "accepted_history" if authoritative else "preview_file"
    input_digest: str | None = None

    accepted_seq: int | None = None
    if stop_input_path is None:
        accepted = _latest_accepted_stop_input(store)
        if accepted is None:
            return {
                "status": "SUCCESS",
                "evaluated": False,
                "authoritative": True,
                "input_source": "accepted_history",
                "campaign_id": head.campaign_id,
                "head_seq": head.commit_seq,
                "continuation_decision": "BLOCKED",
                "assurance_level": "INSUFFICIENT",
                "release_readiness": "QUALIFICATION_BLOCKED",
                "reason_codes": ["MISSING_ACCEPTED_STOP_INPUT"],
                "next_action": "PROVIDE_OR_ACCEPT_STOP_INPUT",
            }
        body, input_digest, accepted_seq = accepted
    else:
        body = _artifact_body(Path(stop_input_path).resolve())

    try:
        stop_input = StopInput(**body)
    except TypeError as exc:
        raise ValidationError("MALFORMED_STOP_INPUT", str(exc)) from exc

    _require_current_campaign_cut(
        stop_input,
        store,
        authoritative=authoritative,
        accepted_commit_seq=accepted_seq,
    )
    if input_digest is None:
        input_digest = stop_input.as_object().digest

    evaluation = evaluate_stop(stop_input, e6_plan_approved=e6_plan_approved)
    return {
        "status": "SUCCESS",
        "evaluated": True,
        "authoritative": authoritative,
        "input_source": source,
        "campaign_id": head.campaign_id,
        "head_seq": head.commit_seq,
        "stop_input_digest": input_digest,
        "continuation_decision": evaluation.continuation_decision,
        "assurance_level": evaluation.assurance_level,
        "release_readiness": evaluation.release_readiness,
        "reason_codes": list(evaluation.reason_codes),
        "blocking_obligation_refs": list(evaluation.blocking_obligation_refs),
        "remaining_obligation_refs": list(evaluation.remaining_obligation_refs),
        "next_action": _next_action(evaluation.continuation_decision, authoritative),
    }


__all__ = ["evaluate_stop_gate"]

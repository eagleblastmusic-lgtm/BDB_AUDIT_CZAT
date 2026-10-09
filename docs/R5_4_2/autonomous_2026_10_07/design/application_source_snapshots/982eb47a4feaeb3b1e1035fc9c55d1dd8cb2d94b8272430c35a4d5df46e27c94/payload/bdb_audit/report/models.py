"""Typed derived report model for RU09.

The model deliberately separates accepted facts from derived interpretations,
proposals, and explicit unknowns.  It is a deterministic export projection,
not a canonical accepted-history object.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Literal


ReportClassification = Literal["FACT", "INTERPRETATION", "PROPOSAL", "UNKNOWN"]
REPORT_MODEL_SCHEMA = "BDB-REPORT-MODEL-1"


def _canonical_json_bytes(value: object) -> bytes:
    """Deterministic derived-export encoding; not BDB ObjectDigest semantics."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class ReportItem:
    classification: ReportClassification
    record_kind: str
    source_ref: dict[str, Any] | None
    accepted_seq: int | None
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "record_kind": self.record_kind,
            "source_ref": deepcopy(self.source_ref),
            "accepted_seq": self.accepted_seq,
            "payload": deepcopy(self.payload),
        }

    @property
    def sort_key(self) -> tuple[int, str, str, str]:
        digest = ""
        if self.source_ref is not None:
            raw_digest = self.source_ref.get("revision_digest")
            if isinstance(raw_digest, str):
                digest = raw_digest
        return (self.accepted_seq or 0, self.record_kind, digest, self.classification)


@dataclass(frozen=True)
class ReportModel:
    campaign_id: str
    input_history_cut: dict[str, Any]
    source_identity: dict[str, Any]
    report_scope: Literal["PARTIAL", "BOUNDED", "FULL"]
    facts: tuple[ReportItem, ...]
    interpretations: tuple[ReportItem, ...]
    proposals: tuple[ReportItem, ...]
    unknowns: tuple[ReportItem, ...]
    schema_version: str = REPORT_MODEL_SCHEMA

    def digest_preimage(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "input_history_cut": deepcopy(self.input_history_cut),
            "source_identity": deepcopy(self.source_identity),
            "report_scope": self.report_scope,
            "facts": [item.as_dict() for item in self.facts],
            "interpretations": [item.as_dict() for item in self.interpretations],
            "proposals": [item.as_dict() for item in self.proposals],
            "unknowns": [item.as_dict() for item in self.unknowns],
        }

    @property
    def report_model_sha256(self) -> str:
        return hashlib.sha256(_canonical_json_bytes(self.digest_preimage())).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        body = self.digest_preimage()
        body["report_model_sha256"] = self.report_model_sha256
        return body


__all__ = [
    "REPORT_MODEL_SCHEMA",
    "ReportClassification",
    "ReportItem",
    "ReportModel",
]

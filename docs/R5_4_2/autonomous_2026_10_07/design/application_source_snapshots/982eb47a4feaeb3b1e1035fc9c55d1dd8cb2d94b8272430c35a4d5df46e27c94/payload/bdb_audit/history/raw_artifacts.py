"""Exact raw bytes in the history transaction's durability domain.

Digests in canonical objects select bytes. Table presence is storage, never
acceptance or producer authority. Filesystem vault entries are staging inputs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..core.errors import ValidationError
from ..vault.raw_store import RawArtifactVault
from .objects import CanonicalObject, ObjectRef


class AdmissionRawReader:
    """Read and retain one immutable snapshot for an admission's validation."""

    def __init__(self, con, *, require_retained: bool = False):
        self.con = con
        self.require_retained = require_retained
        self.verified: dict[str, bytes] = {}

    def read_bytes(self, digest: str) -> bytes:
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValidationError("INVALID_RAW_DIGEST")
        if digest in self.verified:
            return self.verified[digest]
        row = self.con.execute(
            "SELECT byte_length,body FROM immutable_raw_artifacts WHERE digest=?", (digest,),
        ).fetchone()
        if row is not None:
            raw = row[1]
            if type(raw) is not bytes or len(raw) != row[0] or hashlib.sha256(raw).hexdigest() != digest:
                raise ValidationError("VAULT_INTEGRITY_BLOCKED", "Corrupt retained raw artifact: " + digest)
        elif self.require_retained:
            raise ValidationError("VAULT_INTEGRITY_BLOCKED", "Missing retained raw artifact: " + digest)
        else:
            db = self.con.execute("PRAGMA database_list").fetchone()
            if not db or not db[2]:
                raise ValidationError("RAW_ARTIFACT_NOT_FOUND", digest)
            raw = RawArtifactVault(Path(db[2]).resolve().parent / "raw_vault").read_bytes(digest)
        self.verified[digest] = raw
        return raw


def persist_verified_raw(con, artifacts: dict[str, bytes]) -> None:
    """Persist only the bytes used by validation, inside the caller's transaction."""
    if not con.in_transaction:
        raise ValidationError("RAW_RETENTION_TRANSACTION_REQUIRED")
    for digest, raw in artifacts.items():
        if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != digest:
            raise ValidationError("VAULT_INTEGRITY_BLOCKED", "Invalid raw snapshot")
        row = con.execute(
            "SELECT byte_length,body FROM immutable_raw_artifacts WHERE digest=?", (digest,),
        ).fetchone()
        if row is not None:
            if row != (len(raw), raw):
                raise ValidationError("VAULT_INTEGRITY_BLOCKED", "Conflicting retained raw artifact: " + digest)
        else:
            con.execute(
                "INSERT INTO immutable_raw_artifacts(digest,byte_length,body) VALUES(?,?,?)",
                (digest, len(raw), raw),
            )


def retained_raw_for_object(con, obj: CanonicalObject) -> dict[str, bytes]:
    """Validate the raw closure selected by an exact accepted result/evidence."""
    if obj.kind not in {"lane_result_admission_evidence", "bdb_audit_lane_result"}:
        return {}
    evidence = obj
    if obj.kind == "bdb_audit_lane_result":
        ref = ObjectRef.from_dict(obj.body.get("admission_evidence_ref"))
        row = con.execute(
            "SELECT kind,version,schema_ref,logical_id,body FROM immutable_objects WHERE digest=?",
            (ref.revision_digest,),
        ).fetchone()
        if row is None:
            raise ValidationError("VAULT_INTEGRITY_BLOCKED", "Missing admission evidence")
        evidence = CanonicalObject(row[0], json.loads(row[4]), row[2], row[3], row[1])
        if evidence.kind != "lane_result_admission_evidence" or evidence.ref.as_dict(ref_class=ref.ref_class) != ref.as_dict():
            raise ValidationError("VAULT_INTEGRITY_BLOCKED", "Corrupt admission evidence")
        if obj.body.get("raw_result_digest") != evidence.body.get("raw_result_digest"):
            raise ValidationError("VAULT_INTEGRITY_BLOCKED", "Result/evidence raw identity conflict")
    reader = AdmissionRawReader(con, require_retained=True)
    raw = reader.read_bytes(evidence.body.get("raw_result_digest", ""))
    if len(raw) != evidence.body.get("raw_result_byte_length"):
        raise ValidationError("VAULT_INTEGRITY_BLOCKED", "Retained result length conflict")
    reader.read_bytes(evidence.body.get("package_zip_sha256", ""))
    return reader.verified

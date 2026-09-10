"""ADR-006 §3: exact bytes and exact wire kind/version domains."""
from dataclasses import dataclass
import hashlib
import re

from .canonical_json import canonical_bytes
from .errors import ValidationError

BUFFER_SIZE = 64 * 1024
DIGEST_PROFILE = "BDB-OBJECT-DIGEST-1"


def _digest(value):
    if type(value) is not str or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValidationError("INVALID_DIGEST")


@dataclass(frozen=True)
class RawDigest:
    value: str

    def __post_init__(self):
        _digest(self.value)


@dataclass(frozen=True)
class ObjectDigest:
    value: str

    def __post_init__(self):
        _digest(self.value)


def raw_digest(raw: bytes):
    if type(raw) is not bytes:
        raise ValidationError("RAW_BYTES_REQUIRED")
    return RawDigest(hashlib.sha256(raw).hexdigest())


def hash_stream(stream, *, max_bytes):
    """Borrow the stream; own each bounded immutable buffer; never close caller IO."""
    if type(max_bytes) is not int or max_bytes < 0:
        raise ValidationError("INVALID_BYTE_LIMIT")
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = stream.read(min(BUFFER_SIZE, max_bytes - total + 1))
        if type(chunk) is not bytes:
            raise ValidationError("RAW_BYTES_REQUIRED")
        total += len(chunk)
        if total > max_bytes:
            raise ValidationError("RAW_BYTE_LIMIT")
        if not chunk:
            return RawDigest(digest.hexdigest()), total
        digest.update(chunk)


def hash_file(path, *, max_bytes):
    with open(path, "rb") as stream:
        return hash_stream(stream, max_bytes=max_bytes)


def _domain_digest(kind, version, body, *, registry_kind):
    """Hash a schema-prepared preimage. Registry binding must be supplied exactly.

No field stripping: input envelopes must be separated by the schema caller.
The generic primitive also supports the normative test_object golden vector.
"""
    if kind != registry_kind:
        raise ValidationError("OBJECT_DIGEST_KIND_REGISTRY_MISMATCH")
    if type(kind) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", kind) is None:
        raise ValidationError("INVALID_WIRE_KIND")
    if type(version) is not str or re.fullmatch(r"[1-9][0-9]{0,8}", version) is None:
        raise ValidationError("INVALID_SCHEMA_VERSION")
    preamble = ("BDB2/" + kind + "/" + version).encode("ascii") + b"\0"
    digest = hashlib.sha256(preamble)
    digest.update(canonical_bytes(body))
    return digest.hexdigest()


def object_digest(kind, version, body, *, registry_kind):
    """Registered-object path; unregistered aliases cannot create identities."""
    from .ids import contract
    if kind != registry_kind:
        raise ValidationError("OBJECT_DIGEST_KIND_REGISTRY_MISMATCH")
    if kind in ("evidence_qualification", "evidence_applicability"):
        raise ValidationError("LEGACY_SHORT_KIND_ALIAS_FORBIDDEN")
    contract(registry_kind, version)
    if type(body) is not dict:
        raise ValidationError("OBJECT_BODY_REQUIRED")
    if {"revision_digest", "accepted_commit_ref", "accepting_commit_ref", "post_acceptance_history_cut"} & body.keys():
        raise ValidationError("OBJECT_SELF_REFERENCE_PREIMAGE")
    return ObjectDigest(_domain_digest(kind, version, body, registry_kind=registry_kind))

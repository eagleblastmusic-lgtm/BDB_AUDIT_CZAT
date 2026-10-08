"""ADR-006 §§5–6; syntactic identities only, never authority resolution."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4
from functools import lru_cache

from .errors import ValidationError
from .hashing import RawDigest, ObjectDigest, DIGEST_PROFILE

ACTIVE_REGISTRY_FILENAME = "artifact_contract_registry_r5_3_1.json"
REGISTRY_SHA256 = "3cd0945f2987499761281f51cadb48a5947ac8255e4af292f4837cbc843a2a8b"


@lru_cache(maxsize=1)
def _active_document():
    raw = Path(__file__).with_name(ACTIVE_REGISTRY_FILENAME).read_bytes()
    if hashlib.sha256(raw).hexdigest() != REGISTRY_SHA256:
        raise ValidationError("REGISTRY_PIN_MISMATCH")
    return json.loads(raw)


def active_registry_document():
    """Read the byte-pinned active registry once per process."""
    return _active_document()


_DEFAULT_REGISTRY = None


def _get_default_registry():
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        from .registry import ContractRegistry
        _DEFAULT_REGISTRY = ContractRegistry()
    return _DEFAULT_REGISTRY


def contract(kind, version="1"):
    for row in _active_document()["contracts"]:
        if row["kind"] == kind and row["version"] == version:
            return row
    return _get_default_registry().contract(kind, version)


def validate_id(value, kind):
    contract(kind)
    if type(value) is not str or re.fullmatch(
        re.escape(kind) + r"_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", value
    ) is None:
        raise ValidationError("INVALID_TYPED_ID")
    return value


def new_id(kind):
    contract(kind)
    return kind + "_" + str(uuid4())


def deterministic_id(kind, seed):
    contract(kind)
    seed_bytes = seed.encode("utf-8") if isinstance(seed, str) else bytes(seed)
    h = bytearray(hashlib.sha256(seed_bytes).digest()[:16])
    h[6] = (h[6] & 0x0F) | 0x40  # RFC 4122 version 4
    h[8] = (h[8] & 0x3F) | 0x80  # RFC 4122 variant
    import uuid
    return kind + "_" + str(uuid.UUID(bytes=bytes(h)))


@dataclass(frozen=True)
class TypedRef:
    kind: str
    revision_digest: ObjectDigest
    digest_profile: str
    schema_revision_ref: ObjectDigest
    logical_id: str | None = None

    def __post_init__(self):
        contract(self.kind)
        if type(self.revision_digest) is not ObjectDigest or type(self.schema_revision_ref) is not ObjectDigest:
            raise ValidationError("TYPED_REF_DIGEST_TYPE")
        if self.digest_profile != DIGEST_PROFILE:
            raise ValidationError("TYPED_REF_DIGEST_PROFILE")
        if self.logical_id is not None:
            validate_id(self.logical_id, self.kind)

    def require_target(self, *, kind, revision_digest, schema_revision_ref):
        if self.kind != kind or self.revision_digest != revision_digest or self.schema_revision_ref != schema_revision_ref:
            raise ValidationError("TYPED_REF_TARGET_MISMATCH")


@dataclass(frozen=True)
class RawRef:
    raw_digest: RawDigest
    byte_length: int
    media_type: str
    artifact_contract_ref: TypedRef

    def __post_init__(self):
        if type(self.raw_digest) is not RawDigest:
            raise ValidationError("RAW_REF_DIGEST_TYPE")
        if type(self.byte_length) is not int or self.byte_length < 0:
            raise ValidationError("RAW_REF_LENGTH")
        if type(self.media_type) is not str or not self.media_type or not self.media_type.isascii():
            raise ValidationError("RAW_REF_MEDIA_TYPE")
        if type(self.artifact_contract_ref) is not TypedRef:
            raise ValidationError("RAW_REF_CONTRACT")

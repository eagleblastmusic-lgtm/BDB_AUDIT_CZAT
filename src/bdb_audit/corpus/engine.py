"""Exact corpus membership and role validation (M11)."""
from dataclasses import dataclass, field
from typing import Iterable, Mapping
import hashlib

from ..core.errors import ValidationError
from ..core.hashing import RawDigest, raw_digest
from ..history.objects import CanonicalObject


_ROLES = {"DIRECT_PREDECESSOR", "HISTORICAL", "AUXILIARY", "EXTERNAL_HOLDOUT"}


@dataclass(frozen=True)
class CorpusMember:
    raw_digest: str | RawDigest
    source_generation_ref: Mapping
    producer_stage: str
    validation_level: str
    role: str
    raw_bytes: bytes | None = None
    locator: str | None = None

    def __post_init__(self):
        digest = self.raw_digest.value if isinstance(self.raw_digest, RawDigest) else self.raw_digest
        if type(digest) is not str or len(digest) != 64:
            raise ValidationError("RAW_DIGEST_REQUIRED")
        if self.raw_bytes is not None:
            if type(self.raw_bytes) is not bytes or hashlib.sha256(self.raw_bytes).hexdigest() != digest:
                raise ValidationError("RAW_DIGEST_MISMATCH")
        if not isinstance(self.source_generation_ref, Mapping) or not self.source_generation_ref.get("revision_digest"):
            raise ValidationError("SOURCE_GENERATION_REQUIRED")
        if self.role not in _ROLES:
            raise ValidationError("CORPUS_ROLE_INVALID")

    @property
    def digest(self):
        return self.raw_digest.value if isinstance(self.raw_digest, RawDigest) else self.raw_digest

    def as_dict(self):
        out = {"raw_digest": self.digest, "source_generation_ref": dict(self.source_generation_ref),
               "producer_stage": self.producer_stage, "validation_level": self.validation_level,
               "role": self.role}
        if self.locator is not None:
            out["locator"] = self.locator
        return out


@dataclass(frozen=True)
class DirectPredecessor:
    member: CorpusMember

    def __post_init__(self):
        if self.member.role != "DIRECT_PREDECESSOR":
            raise ValidationError("DIRECT_PREDECESSOR_ROLE_REQUIRED")


@dataclass(frozen=True)
class HistoricalCorpus:
    direct_predecessor: DirectPredecessor
    auxiliary: tuple[CorpusMember, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "auxiliary", tuple(self.auxiliary))
        if any(member.role != "AUXILIARY" for member in self.auxiliary):
            raise ValidationError("AUXILIARY_ROLE_REQUIRED")


@dataclass(frozen=True)
class AuxiliaryCorpus:
    members: tuple[CorpusMember, ...]

    def __post_init__(self):
        object.__setattr__(self, "members", tuple(self.members))
        if any(member.role != "AUXILIARY" for member in self.members):
            raise ValidationError("AUXILIARY_ROLE_REQUIRED")


@dataclass(frozen=True)
class ExternalHoldout:
    members: tuple[CorpusMember, ...]

    def __post_init__(self):
        object.__setattr__(self, "members", tuple(self.members))
        if any(member.role != "EXTERNAL_HOLDOUT" for member in self.members):
            raise ValidationError("HOLDOUT_ROLE_REQUIRED")


@dataclass(frozen=True)
class CorpusManifest:
    corpus_role: str
    members: tuple[CorpusMember, ...]
    source_generation_ref: Mapping

    def __post_init__(self):
        if self.corpus_role not in _ROLES:
            raise ValidationError("CORPUS_ROLE_INVALID")
        object.__setattr__(self, "members", tuple(self.members))
        if not isinstance(self.source_generation_ref, Mapping):
            raise ValidationError("SOURCE_GENERATION_REQUIRED")

    def body(self):
        return {"corpus_role": self.corpus_role,
                "members": [member.as_dict() for member in self.members],
                "source_generation_ref": dict(self.source_generation_ref)}

    def as_object(self):
        return CanonicalObject("corpus_manifest", self.body())


class CorpusEngine:
    def validate(self, *, direct_predecessors: Iterable[CorpusMember] = (), auxiliary: Iterable[CorpusMember] = (),
                 external_holdout: Iterable[CorpusMember] = (), source_generation_ref=None):
        direct = tuple(direct_predecessors)
        aux = tuple(auxiliary)
        holdout = tuple(external_holdout)
        if len(direct) != 1:
            raise ValidationError("DIRECT_PREDECESSOR_SINGLE")
        if direct[0].role != "DIRECT_PREDECESSOR":
            raise ValidationError("DIRECT_PREDECESSOR_ROLE_REQUIRED")
        if any(member.role != "AUXILIARY" for member in aux):
            raise ValidationError("AUXILIARY_ROLE_REQUIRED")
        if any(member.role != "EXTERNAL_HOLDOUT" for member in holdout):
            raise ValidationError("HOLDOUT_ROLE_REQUIRED")
        all_members = direct + aux + holdout
        source_digests = {member.source_generation_ref.get("revision_digest") for member in all_members}
        if source_generation_ref is not None:
            expected = source_generation_ref.get("revision_digest")
            if any(digest != expected for digest in source_digests):
                raise ValidationError("CROSS_SOURCE_CORPUS_REJECTED")
        elif len(source_digests) > 1:
            raise ValidationError("CROSS_SOURCE_CORPUS_REJECTED")
        return {
            "DIRECT_PREDECESSOR_SINGLE": "YES",
            "AUXILIARY_MULTI_REPORT": "YES",
            "CROSS_SOURCE_CORPUS_REJECTED": "YES",
            "LEGACY_E2_ACCEPTED_AS_DIRECT_PREDECESSOR": "YES",
        }

    def manifest(self, *, role, members, source_generation_ref):
        manifest = CorpusManifest(role, tuple(members), source_generation_ref)
        if role == "DIRECT_PREDECESSOR" and len(manifest.members) != 1:
            raise ValidationError("DIRECT_PREDECESSOR_SINGLE")
        if any(m.source_generation_ref.get("revision_digest") != source_generation_ref.get("revision_digest") for m in manifest.members):
            raise ValidationError("CROSS_SOURCE_CORPUS_REJECTED")
        return manifest


class LegacyCorpusAdapter:
    """Wrap legacy E1/E2 bytes without conversion or canonical rewriting."""
    @staticmethod
    def member(raw: bytes, *, source_generation_ref, producer_stage, validation_level,
               role, locator=None):
        if type(raw) is not bytes:
            raise ValidationError("RAW_BYTES_REQUIRED")
        return CorpusMember(raw_digest(raw), source_generation_ref, producer_stage,
                            validation_level, role, raw_bytes=raw, locator=locator)

    @classmethod
    def legacy_e2_direct_predecessor(cls, raw, *, source_generation_ref, locator=None):
        return DirectPredecessor(cls.member(raw, source_generation_ref=source_generation_ref,
                                            producer_stage="E2", validation_level="L5",
                                            role="DIRECT_PREDECESSOR", locator=locator))

    @classmethod
    def legacy_e1_auxiliary(cls, raw, *, source_generation_ref, locator=None):
        return cls.member(raw, source_generation_ref=source_generation_ref,
                          producer_stage="E1", validation_level="L3",
                          role="AUXILIARY", locator=locator)


__all__ = ["CorpusMember", "DirectPredecessor", "HistoricalCorpus", "AuxiliaryCorpus",
           "ExternalHoldout", "CorpusManifest", "CorpusEngine", "LegacyCorpusAdapter"]

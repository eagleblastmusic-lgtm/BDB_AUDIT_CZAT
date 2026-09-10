"""Test Plan §10: exact raw membership manifest, no archive self-hash."""
import re

from ..core.errors import ValidationError
from ..core.hashing import RawDigest, raw_digest
from .zip_safety import canonical_path


def parse_manifest(raw):
    if type(raw) is not bytes:
        raise ValidationError("RAW_BYTES_REQUIRED")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise ValidationError("INVALID_ARTIFACT_HASH_LINE") from exc
    if text and not text.endswith("\n"):
        raise ValidationError("ARTIFACT_HASHES_MISSING_FINAL_LF")
    declared = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\\]+)", line)
        if not match:
            raise ValidationError("INVALID_ARTIFACT_HASH_LINE")
        digest, path = match.groups()
        if canonical_path(path) != path:
            raise ValidationError("UNSAFE_ZIP_PATH", path)
        if path in declared:
            raise ValidationError("DUPLICATE_ARTIFACT_HASH_PATH", path)
        declared[path] = RawDigest(digest)
    if list(declared) != sorted(declared):
        raise ValidationError("ARTIFACT_HASH_PATHS_NOT_SORTED")
    return declared


def validate_manifest(raw, members):
    declared = parse_manifest(raw)
    if set(declared) != set(members):
        raise ValidationError("ARTIFACT_HASH_MEMBERSHIP_MISMATCH")
    for path, digest in declared.items():
        if digest != raw_digest(members[path]):
            raise ValidationError("ARTIFACT_HASH_MISMATCH", path)
    return declared

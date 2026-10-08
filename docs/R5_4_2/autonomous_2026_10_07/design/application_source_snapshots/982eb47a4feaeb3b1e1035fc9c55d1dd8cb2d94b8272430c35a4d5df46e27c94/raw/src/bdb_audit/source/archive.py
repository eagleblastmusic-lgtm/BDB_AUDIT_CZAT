"""Exact source ZIP reconciliation; this parser does not grant source authority.

The caller must independently select the qualified source/transport profiles and
verify the SourceMaterialization. No filesystem extraction or link following.
"""

import base64
import binascii
import hashlib
import io
import lzma
import re
import stat
import zipfile
import zlib

from ..assurance.zip_safety import Limits, _expanded, _metadata
from ..core.errors import ValidationError
from .materializer import SourceMaterialization, _canonical_path


SOURCE_LIMITS = Limits(input_bytes=67108864, expanded_bytes=67108864,
                       member_bytes=67108864, members=65536)


def read_complete_source_archive(raw: bytes, source: SourceMaterialization, *, limits: Limits = SOURCE_LIMITS) -> dict[str, bytes]:
    """Return exact reconciled members, without accepting an identity or object."""
    if type(raw) is not bytes:
        raise ValidationError("RAW_BYTES_REQUIRED")
    if source.completeness_state != "COMPLETE_SOURCE" or source.limitations:
        raise ValidationError("SOURCE_ARCHIVE_INCOMPLETE_SOURCE")
    if (limits.input_bytes > 67108864 or limits.expanded_bytes > 67108864 or limits.members > 65536
            or limits.central_bytes > 8388608 or limits.member_bytes > 67108864 or limits.ratio > 1000):
        raise ValidationError("SOURCE_ARCHIVE_UNSUPPORTED_LIMIT")
    if len(source.entries) > limits.members:
        raise ValidationError("ZIP_RESOURCE_LIMIT", "source member quota")
    if len(raw) > limits.input_bytes:
        raise ValidationError("ZIP_RESOURCE_LIMIT", "input quota")
    expected = {}
    parents: set[str] = set()
    for entry in source.entries:
        name = _canonical_path(entry["repo_relative_posix_path"].encode("utf-8", "strict"))
        if len(name) > 512 or name in expected:
            raise ValidationError("SOURCE_ARCHIVE_MANIFEST_PATH_CONFLICT")
        if entry["entry_type"] not in {"REGULAR_FILE", "SYMLINK"} or "lfs_pointer_state" in entry:
            raise ValidationError("SOURCE_ARCHIVE_UNSUPPORTED_ENTRY", name)
        if (type(entry.get("byte_length")) is not int or entry["byte_length"] < 0
                or type(entry.get("content_raw_digest")) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", entry["content_raw_digest"])):
            raise ValidationError("SOURCE_ARCHIVE_INVALID_MANIFEST_ENTRY", name)
        expected[name] = entry
        components = name.split("/")
        parents.update("/".join(components[:i]) for i in range(1, len(components)))
    if set(expected) & parents:
        raise ValidationError("SOURCE_ARCHIVE_MANIFEST_PATH_CONFLICT")
    count = _metadata(raw, limits)
    result = {}
    names = set()
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) != count:
                raise ValidationError("ZIP_INTEGRITY_FAILURE", "member count")
            for info in infos:
                if info.orig_filename != info.filename or info.flag_bits & 1:
                    raise ValidationError("SOURCE_ARCHIVE_INVALID_MEMBER")
                directory = info.is_dir()
                name = info.filename[:-1] if directory else info.filename
                _canonical_path(name.encode("utf-8", "strict"))
                if len(name) > 512 or name in names:
                    raise ValidationError("SOURCE_ARCHIVE_DUPLICATE_OR_UNSUPPORTED_PATH")
                names.add(name)
                mode = info.external_attr >> 16
                if directory:
                    if name not in parents or info.file_size or stat.S_IFMT(mode) not in {0, stat.S_IFDIR}:
                        raise ValidationError("SOURCE_ARCHIVE_UNDECLARED_DIRECTORY")
                elif name not in expected:
                    raise ValidationError("SOURCE_ARCHIVE_UNDECLARED_MEMBER")
                else:
                    entry = expected[name]
                    required_type = stat.S_IFLNK if entry["entry_type"] == "SYMLINK" else stat.S_IFREG
                    if info.create_system != 3 or mode != int(entry["relevant_mode"], 8) or stat.S_IFMT(mode) != required_type:
                        raise ValidationError("SOURCE_ARCHIVE_MODE_MISMATCH")
                if (info.file_size > limits.member_bytes or total + info.file_size > limits.expanded_bytes
                        or info.file_size > max(1, info.compress_size) * limits.ratio):
                    raise ValidationError("ZIP_RESOURCE_LIMIT", "expanded size or ratio")
                # Existing bounded decoder checks actual output length and CRC;
                # ZipFile.open checks original local/central metadata and overlap.
                with archive.open(info):
                    data = _expanded(raw, info, min(limits.member_bytes, limits.expanded_bytes - total,
                                                   max(1, info.compress_size) * limits.ratio))
                total += len(data)
                if directory:
                    if data:
                        raise ValidationError("SOURCE_ARCHIVE_UNDECLARED_DIRECTORY")
                    continue
                entry = expected[name]
                if len(data) != entry["byte_length"] or hashlib.sha256(data).hexdigest() != entry["content_raw_digest"]:
                    raise ValidationError("SOURCE_ARCHIVE_MEMBER_CONFLICT")
                if entry["entry_type"] == "SYMLINK":
                    target = base64.b64decode(entry["symlink_target"], validate=True)
                    if (entry.get("symlink_target_encoding") != "base64" or target != data
                            or base64.b64encode(target).decode("ascii") != entry["symlink_target"]):
                        raise ValidationError("SOURCE_ARCHIVE_SYMLINK_TARGET_CONFLICT")
                elif data.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
                    raise ValidationError("SOURCE_ARCHIVE_UNRESOLVED_LFS")
                result[name] = data
    except ValidationError:
        raise
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError,
            binascii.Error, UnicodeError, ValueError, KeyError, zlib.error, lzma.LZMAError) as exc:
        raise ValidationError("SOURCE_ARCHIVE_INVALID_REPRESENTATION", type(exc).__name__) from exc
    if set(result) != set(expected):
        raise ValidationError("SOURCE_ARCHIVE_MISSING_MEMBERS")
    return result

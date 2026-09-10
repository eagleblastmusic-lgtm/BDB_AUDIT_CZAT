"""F1 P03 / Test Plan §9: bounded ZIP input, metadata and decompression.

Limits are explicit resource budgets, not source identity. Members remain opaque
bytes, including nested archives. No filesystem extraction occurs.
"""
from dataclasses import dataclass
import io
from pathlib import PurePosixPath
import stat
import struct
import zipfile
import zlib
import bz2
import lzma

from ..core.errors import ValidationError


@dataclass(frozen=True)
class Limits:
    input_bytes: int = 256 * 1024 * 1024
    central_bytes: int = 8 * 1024 * 1024
    members: int = 4096
    member_bytes: int = 100 * 1024 * 1024
    expanded_bytes: int = 256 * 1024 * 1024
    ratio: int = 1000

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in vars(self).values()):
            raise ValidationError("ZIP_INVALID_LIMIT")


@dataclass(frozen=True)
class ArchiveInput:
    """One owned immutable representation used for validation AND RawDigest."""
    raw: bytes
    display_path: str

    def __str__(self):
        return self.display_path

    def is_file(self):
        return True


def snapshot(path, *, limits=Limits()):
    if type(path) is ArchiveInput:
        result = path
    else:
        with open(path, "rb") as stream:
            result = ArchiveInput(stream.read(limits.input_bytes + 1), str(path))
    if type(result.raw) is not bytes or len(result.raw) > limits.input_bytes:
        raise ValidationError("ZIP_RESOURCE_LIMIT", "input quota")
    return result


def canonical_path(name):
    if (type(name) is not str or not name or "\\" in name or "\0" in name
            or ":" in name or PurePosixPath(name).is_absolute()
            or any(part == ".." for part in name.split("/"))):
        raise ValidationError("UNSAFE_ZIP_PATH", repr(name))
    normalized = str(PurePosixPath(name))
    if normalized == ".":
        raise ValidationError("UNSAFE_ZIP_PATH", name)
    return normalized


def _metadata(raw, limits):
    # Inspect classic EOCD before ZipFile allocates its central-directory index.
    search_end = len(raw)
    while True:
        pos = raw.rfind(b"PK\x05\x06", max(0, len(raw) - 65557), search_end)
        if pos < 0:
            raise ValidationError("ZIP_OPEN_FAILURE", "missing EOCD")
        if pos + 22 <= len(raw) and pos + 22 + struct.unpack_from("<H", raw, pos+20)[0] == len(raw):
            break
        search_end = pos
    _, disk, cd_disk, disk_count, count, cd_size, cd_offset, comment = struct.unpack_from("<4s4H2LH", raw, pos)
    if pos + 22 + comment != len(raw):
        raise ValidationError("ZIP_OPEN_FAILURE", "invalid EOCD extent")
    if disk or cd_disk or disk_count != count:
        raise ValidationError("ZIP_OPEN_FAILURE", "split archive")
    central_end = pos
    if raw[pos-20:pos-16] == b"PK\x06\x07":
        _, zip_disk, zip_offset, disks = struct.unpack_from("<4sLQL", raw, pos-20)
        if zip_disk or disks != 1 or zip_offset + 56 > pos-20 or raw[zip_offset:zip_offset+4] != b"PK\x06\x06":
            raise ValidationError("ZIP_OPEN_FAILURE", "ZIP64 locator")
        _, record_size, _, _, disk, cd_disk, disk_count, count, cd_size, cd_offset = struct.unpack_from("<4sQ2H2L4Q", raw, zip_offset)
        if record_size + zip_offset + 12 != pos-20 or disk or cd_disk or disk_count != count:
            raise ValidationError("ZIP_OPEN_FAILURE", "ZIP64 EOCD")
        central_end = zip_offset
    if count > limits.members or cd_size > limits.central_bytes:
        raise ValidationError("ZIP_RESOURCE_LIMIT", "central directory quota")
    if cd_offset + cd_size > central_end:
        raise ValidationError("ZIP_OPEN_FAILURE", "central directory extent")
    return count


def _expanded(raw, info, ceiling):
    """Count actual output, independent of the untrusted declared file_size.

    ZipExtFile truncates output to that declaration; it cannot enforce this
    contract. Feed bounded input and cap every decompressor output allocation.
    """
    offset = info.header_offset
    if raw[offset:offset+4] != b"PK\x03\x04" or offset + 30 > len(raw):
        raise ValidationError("ZIP_INTEGRITY_FAILURE", "local header")
    name_len, extra_len = struct.unpack_from("<HH", raw, offset+26)
    start = offset + 30 + name_len + extra_len
    end = start + info.compress_size
    if end > len(raw):
        raise ValidationError("ZIP_INTEGRITY_FAILURE", "compressed extent")
    data = memoryview(raw)[start:end]
    method = info.compress_type
    decoder = None
    if method == zipfile.ZIP_DEFLATED:
        decoder = zlib.decompressobj(-15)
    elif method == zipfile.ZIP_BZIP2:
        decoder = bz2.BZ2Decompressor()
    elif method == zipfile.ZIP_LZMA:
        if len(data) < 9 or struct.unpack_from("<H", data, 2)[0] != 5:
            raise ValidationError("ZIP_INTEGRITY_FAILURE", "LZMA properties")
        prop = data[4]
        lc, rest = prop % 9, prop // 9
        lp, pb = rest % 5, rest // 5
        dictionary = struct.unpack_from("<L", data, 5)[0]
        if dictionary > 256 * 1024 * 1024:
            raise ValidationError("ZIP_RESOURCE_LIMIT", "LZMA dictionary")
        decoder = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[{
            "id": lzma.FILTER_LZMA1, "dict_size": dictionary, "lc": lc, "lp": lp, "pb": pb}])
        data = data[9:]
    elif method == getattr(zipfile, "ZIP_ZSTANDARD", 93):
        from compression import zstd
        decoder = zstd.ZstdDecompressor()
    elif method != zipfile.ZIP_STORED:
        raise ValidationError("ZIP_INTEGRITY_FAILURE", "unsupported compression")
    output = bytearray()
    position = 0
    pending = b""
    while True:
        limit = min(65536, ceiling - len(output) + 1)
        if decoder is None:
            chunk = data[position:position+limit]
            position += len(chunk)
        else:
            if method == zipfile.ZIP_DEFLATED and pending:
                compressed = pending
            elif method != zipfile.ZIP_DEFLATED and not decoder.needs_input:
                compressed = b""
            else:
                compressed = data[position:position+65536]
                position += len(compressed)
            chunk = decoder.decompress(compressed, max_length=limit)
            if method == zipfile.ZIP_DEFLATED:
                pending = decoder.unconsumed_tail
        if len(output) + len(chunk) > ceiling:
            raise ValidationError("ZIP_RESOURCE_LIMIT", "actual decompression")
        output.extend(chunk)
        if decoder is None:
            if position == len(data):
                break
        elif decoder.eof:
            if decoder.unused_data or position != len(data):
                raise ValidationError("ZIP_INTEGRITY_FAILURE", "trailing compressed data")
            break
        elif not chunk and position == len(data) and not pending:
            raise ValidationError("ZIP_INTEGRITY_FAILURE", "truncated compressed stream")
    if len(output) != info.file_size or zlib.crc32(output) != info.CRC:
        raise ValidationError("ZIP_INTEGRITY_FAILURE", "actual size or CRC")
    return bytes(output)


def read_bytes(raw, *, limits=Limits(), errors=None):
    if type(raw) is not bytes:
        raise ValidationError("RAW_BYTES_REQUIRED")
    if len(raw) > limits.input_bytes:
        raise ValidationError("ZIP_RESOURCE_LIMIT", "input quota")
    count = _metadata(raw, limits)
    result = {}
    total = 0
    names = set()
    normalized = set()
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) != count or len(infos) > limits.members:
                raise ValidationError("ZIP_RESOURCE_LIMIT", "member count")
            for info in infos:
                if info.orig_filename != info.filename:
                    raise ValidationError("UNSAFE_ZIP_PATH", "truncated filename")
                name = info.filename
                try:
                    key = canonical_path(name)
                except ValidationError as exc:
                    if errors is None:
                        raise
                    errors.append(str(exc))
                    continue
                if name in names:
                    if errors is None:
                        raise ValidationError("DUPLICATE_ZIP_MEMBER_NAMES")
                    errors.append("DUPLICATE_ZIP_MEMBER_NAMES")
                    continue
                if key in normalized:
                    raise ValidationError("ZIP_NORMALIZED_PATH_COLLISION", key)
                names.add(name)
                normalized.add(key)
                mode = info.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValidationError("ZIP_SPECIAL_FILE", name)
                if info.is_dir():
                    if info.file_size:
                        raise ValidationError("ZIP_OPEN_FAILURE", "nonempty directory")
                    continue
                if info.file_size > limits.member_bytes or total + info.file_size > limits.expanded_bytes:
                    raise ValidationError("ZIP_RESOURCE_LIMIT", "expanded size")
                if info.file_size > max(1, info.compress_size) * limits.ratio:
                    raise ValidationError("ZIP_RESOURCE_LIMIT", "compression ratio")
                # open() verifies local/central names, flags and overlap without
                # reading unbounded decompressed content.
                with archive.open(info) as member:
                    data = _expanded(raw, info, min(limits.member_bytes, limits.expanded_bytes-total,
                                                   max(1, info.compress_size)*limits.ratio))
                total += len(data)
                result[name] = data
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError, zlib.error, lzma.LZMAError) as exc:
        raise ValidationError("ZIP_INTEGRITY_FAILURE", str(exc)) from exc
    return result


def read_zip(path, *, limits=Limits(), errors=None):
    # Owned file is closed on success and every failure; no caller descriptor.
    return read_bytes(snapshot(path, limits=limits).raw, limits=limits, errors=errors)

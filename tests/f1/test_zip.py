import io
import stat
import struct
import zipfile

import pytest

from bdb_audit.assurance.zip_safety import *
from bdb_audit.assurance.artifact_hashes import *
from bdb_audit.core.hashing import object_digest, raw_digest


ZIP_METHODS = [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA]
if hasattr(zipfile, "ZIP_ZSTANDARD"):
    ZIP_METHODS.append(zipfile.ZIP_ZSTANDARD)


def archive(rows, compression=zipfile.ZIP_STORED):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=compression) as z:
        for name, data in rows:
            z.writestr(name, data)
    return out.getvalue()


@pytest.mark.parametrize("name", ["/a", "../a", "a/../../b", "a\\b", "C:/a", "//host/a"])
def test_paths(name):
    raw = archive([("a/b" if name == "a\\b" else name, b"x")])
    if name == "a\\b":
        raw = raw.replace(b"a/b", b"a\\b")
    with pytest.raises(ValidationError, match="UNSAFE_ZIP_PATH"):
        read_bytes(raw)


def test_duplicates_and_special():
    for names in [("a", "a"), ("a/b", "a/./b"), ("a/b", "a//b")]:
        with pytest.raises(ValidationError):
            read_bytes(archive([(n, b"x") for n in names]))
    for mode in [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR]:
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (mode | 0o777) << 16
        with pytest.raises(ValidationError, match="ZIP_SPECIAL_FILE"):
            read_bytes(archive([(info, b"target")]))


def test_quotas():
    raw = archive([("a", b"x"*10), ("b", b"y"*10)])
    assert len(read_bytes(raw, limits=Limits(member_bytes=10, expanded_bytes=20))) == 2
    for limits in [Limits(input_bytes=len(raw)-1), Limits(central_bytes=1), Limits(members=1), Limits(member_bytes=9), Limits(expanded_bytes=19)]:
        with pytest.raises(ValidationError, match="ZIP_RESOURCE_LIMIT"):
            read_bytes(raw, limits=limits)
    with pytest.raises(ValidationError, match="ZIP_RESOURCE_LIMIT"):
        read_bytes(archive([("a", b"x"*10000)], zipfile.ZIP_DEFLATED), limits=Limits(ratio=2))


def test_crc_and_nested():
    raw = bytearray(archive([("a", b"unique payload")]))
    raw[raw.index(b"unique payload")] ^= 1
    with pytest.raises(ValidationError, match="ZIP_INTEGRITY_FAILURE"):
        read_bytes(bytes(raw))
    nested = archive([("a", b"abc")])
    assert read_bytes(archive([("nested.zip", nested)])) == {"nested.zip": nested}


@pytest.mark.parametrize("method", ZIP_METHODS)
def test_actual_decompression_not_header(method):
    import zlib
    raw = archive([("a", b"x"*100000)], method)
    assert read_bytes(raw, limits=Limits(ratio=100000))["a"] == b"x"*100000
    forged = bytearray(raw)
    central = forged.index(b"PK\x01\x02")
    for crc_pos, length_pos in [(14,22), (central+16,central+24)]:
        struct.pack_into("<L", forged, crc_pos, zlib.crc32(b"x"))
        struct.pack_into("<L", forged, length_pos, 1)
    with pytest.raises(ValidationError, match="ZIP_RESOURCE_LIMIT"):
        read_bytes(bytes(forged), limits=Limits(member_bytes=100, expanded_bytes=100, ratio=100000))


def test_empty_and_zip64_metadata():
    assert read_bytes(archive([])) == {}
    raw = archive([("a", b"x")])
    end = raw.rfind(b"PK\x05\x06")
    fields = struct.unpack_from("<4s4H2LH", raw, end)
    zip64 = struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, 1, 1, fields[5], fields[6])
    locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, end, 1)
    eocd = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 65535, 65535, 0xffffffff, 0xffffffff, 0)
    extended = raw[:end] + zip64 + locator + eocd
    assert read_bytes(extended) == {"a": b"x"}
    with pytest.raises(ValidationError, match="ZIP_RESOURCE_LIMIT"):
        read_bytes(extended, limits=Limits(central_bytes=1))


def test_manifest_cases():
    a = raw_digest(b"a").value.encode() + b"  a\n"
    b = raw_digest(b"b").value.encode() + b"  b\n"
    assert validate_manifest(a+b, {"a":b"a", "b":b"b"})
    assert validate_manifest(b"", {}) == {}
    for raw, members in [(b+a, {"a":b"a","b":b"b"}), (a+a, {"a":b"a"}), (a, {}), (b"", {"a":b"a"}), (a, {"a":b"b"}), (b"bad\n", {}), (a[:-1], {"a":b"a"}), (a.replace(b"  a", b"  ./a"), {"./a":b"a"})]:
        with pytest.raises(ValidationError):
            validate_manifest(raw, members)


def test_representation_identity():
    rows = [("a", b"abc"), ("b", b"def")]
    first, second = archive(rows), archive(list(reversed(rows)))
    assert raw_digest(first) != raw_digest(second)
    # Independent canonical semantic membership, not a production SourceManifest schema.
    def semantic(raw):
        return {p: {"byte_length": len(v), "raw_digest": raw_digest(v).value} for p,v in read_bytes(raw).items()}
    assert object_digest("source_manifest", "1", semantic(first), registry_kind="source_manifest") == object_digest("source_manifest", "1", semantic(second), registry_kind="source_manifest")


def test_owned_handle_cleanup(tmp_path):
    path = tmp_path / "bad.zip"
    path.write_bytes(b"bad")
    with pytest.raises(ValidationError):
        read_zip(path)
    path.unlink()  # Windows refuses this while an owned file remains open.

import base64
from dataclasses import replace
import hashlib
import io
import zipfile

import pytest

from bdb_audit.assurance.zip_safety import Limits, read_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.source.archive import SOURCE_LIMITS, read_complete_source_archive
from bdb_audit.source.git_resolver import VerifiedGitIdentity
from bdb_audit.source.materializer import SourceMaterialization


def fixture(name="a/.hidden", data=b"original", symlink=False):
    entry = {"repo_relative_posix_path": name, "entry_type": "SYMLINK" if symlink else "REGULAR_FILE",
             "relevant_mode": "120000" if symlink else "100644", "byte_length": len(data),
             "content_raw_digest": hashlib.sha256(data).hexdigest()}
    if symlink:
        entry.update(symlink_target=base64.b64encode(data).decode("ascii"), symlink_target_encoding="base64")
    identity = VerifiedGitIdentity("CONTROLLED", "HEAD", "a" * 40, "b" * 40)
    return SourceMaterialization(identity, (entry,), "COMPLETE_SOURCE")


def archive(rows):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as writer:
        for name, data, mode in rows:
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = int(mode, 8) << 16
            writer.writestr(info, data)
    return output.getvalue()


@pytest.mark.parametrize("name", [".gitignore", "a/.hidden", "żółć.txt", "component:colon.txt"])
def test_exact_source_names_preserved(name):
    assert read_complete_source_archive(archive([(name, b"original", "100644")]), fixture(name)) == {name: b"original"}


def test_symlink_target_bytes_read_without_following_and_generic_transport_unchanged():
    data = b"../outside/\xff-target"
    raw = archive([("link", data, "120000")])
    assert read_complete_source_archive(raw, fixture("link", data, True)) == {"link": data}
    with pytest.raises(ValidationError, match="ZIP_SPECIAL_FILE"):
        read_bytes(raw)


@pytest.mark.parametrize("name", ["../a", "a/./b", "a//b", "/a", "a\\b"])
def test_alias_and_unsafe_source_paths_rejected(name):
    with pytest.raises(ValidationError):
        read_complete_source_archive(archive([(name, b"original", "100644")]), fixture())


@pytest.mark.parametrize("rows,code", [
    ([], "SOURCE_ARCHIVE_MISSING_MEMBERS"),
    ([("extra", b"original", "100644")], "SOURCE_ARCHIVE_UNDECLARED_MEMBER"),
    ([("a/.hidden", b"changed!", "100644")], "SOURCE_ARCHIVE_MEMBER_CONFLICT"),
    ([("a/.hidden", b"original", "100755")], "SOURCE_ARCHIVE_MODE_MISMATCH"),
    ([("other/", b"", "040755")], "SOURCE_ARCHIVE_UNDECLARED_DIRECTORY"),
    ([("a/", b"nonempty", "040755")], "SOURCE_ARCHIVE_UNDECLARED_DIRECTORY"),
    ([("a/.hidden", b"original", "100644"), ("a/.hidden", b"original", "100644")], "SOURCE_ARCHIVE_DUPLICATE_OR_UNSUPPORTED_PATH"),
])
def test_member_reconciliation_rejects(rows, code):
    with pytest.raises(ValidationError) as error:
        read_complete_source_archive(archive(rows), fixture())
    assert error.value.code == code


def test_declared_parent_metadata_is_not_source_member():
    raw = archive([("a/", b"", "040755"), ("a/.hidden", b"original", "100644")])
    assert read_complete_source_archive(raw, fixture()) == {"a/.hidden": b"original"}


@pytest.mark.parametrize("case", ["bounded", "limit", "bool_length", "lfs", "submodule", "target", "encoding", "noncanonical_base64"])
def test_fail_closed_source_and_target_controls(case):
    source = fixture("link", b"a", True)
    entry = source.entries[0]
    kwargs = {}
    if case == "bounded":
        source = replace(source, completeness_state="BOUNDED_SOURCE")
    elif case == "limit":
        kwargs["limits"] = Limits(input_bytes=1)
    elif case == "bool_length":
        entry["byte_length"] = True
    elif case == "lfs":
        entry["lfs_pointer_state"] = "POINTER_UNMATERIALIZED"
    elif case == "submodule":
        entry["entry_type"] = "SUBMODULE"
    elif case == "target":
        entry["symlink_target"] = "Yg=="
    elif case == "encoding":
        entry["symlink_target_encoding"] = "utf8"
    else:
        entry["symlink_target"] = "YR=="  # Same decoded byte, nonzero padding bits.
    with pytest.raises(ValidationError):
        read_complete_source_archive(archive([("link", b"a", "120000")]), source, **kwargs)


def test_pointer_without_manifest_marker_still_rejects():
    data = b"version https://git-lfs.github.com/spec/v1\nunknown"
    with pytest.raises(ValidationError, match="SOURCE_ARCHIVE_UNRESOLVED_LFS"):
        read_complete_source_archive(archive([("pointer", data, "100644")]), fixture("pointer", data))


def test_corrupt_original_payload_rejected_without_extraction():
    raw = archive([("a/.hidden", b"original", "100644")]).replace(b"original", b"corrupt!", 1)
    with pytest.raises(ValidationError, match="ZIP_INTEGRITY_FAILURE"):
        read_complete_source_archive(raw, fixture())


@pytest.mark.parametrize("field", ["input_bytes", "expanded_bytes", "central_bytes", "member_bytes", "members", "ratio"])
def test_supported_budget_caps_cannot_be_raised(field):
    limits = replace(SOURCE_LIMITS, **{field: getattr(SOURCE_LIMITS, field) + 1})
    with pytest.raises(ValidationError, match="SOURCE_ARCHIVE_UNSUPPORTED_LIMIT"):
        read_complete_source_archive(archive([("a/.hidden", b"original", "100644")]), fixture(), limits=limits)


def test_actual_member_budget_is_enforced():
    with pytest.raises(ValidationError, match="ZIP_RESOURCE_LIMIT"):
        read_complete_source_archive(archive([("a/.hidden", b"original", "100644")]), fixture(),
                                     limits=replace(SOURCE_LIMITS, member_bytes=1))

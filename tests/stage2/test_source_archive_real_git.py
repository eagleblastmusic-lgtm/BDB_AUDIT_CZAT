"""Reconcile actual Git trees/archives without mocked source responses."""

import base64
import hashlib
import io
import subprocess
import zipfile

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.source.archive import read_complete_source_archive
from bdb_audit.source.materializer import materialize_local_source
from bdb_audit.workflow.source_target import resolve_local_source


def git(repo, *args, data=None):
    return subprocess.run(
        ["git", "-C", str(repo), *args], input=data,
        capture_output=True, check=True,
    ).stdout


@pytest.fixture(params=["sha1", "sha256"])
def source_repo(tmp_path, request):
    repo = tmp_path / "source"
    repo.mkdir()
    git(repo, "init", "--object-format=" + request.param)
    git(repo, "config", "user.name", "Source contract fixture")
    git(repo, "config", "user.email", "source@example.invalid")
    return repo, request.param


def add_blob(repo, path, mode, raw):
    oid = git(repo, "hash-object", "-w", "--stdin", data=raw).decode("ascii").strip()
    git(repo, "update-index", "--add", "--cacheinfo", mode, oid, path)


def commit(repo):
    git(repo, "commit", "-m", "Exact source fixture")
    return git(repo, "rev-parse", "HEAD").decode("ascii").strip()


def test_real_git_archive_reconciles_paths_modes_symlink_and_exact_tree(source_repo):
    repo, algorithm = source_repo
    rows = {
        ".hidden": ("100644", b"hidden\r\n"),
        "nested/zażółć.bin": ("100644", b"\x00\xfforiginal"),
        "run": ("100755", b"executable\n"),
        "link": ("120000", b"../outside/\xff-target"),
    }
    for path, (mode, raw) in rows.items():
        add_blob(repo, path, mode, raw)
    head = commit(repo)
    source = materialize_local_source(repo, explicit_sha=head)
    descriptor = resolve_local_source(repo, explicit_sha=head)
    assert descriptor.object_format == source.identity.object_format == algorithm
    assert descriptor.exact_commit_sha == head
    assert len(head) == {"sha1": 40, "sha256": 64}[algorithm]
    assert descriptor.exact_tree_sha == source.identity.tree_object_id
    assert source.completeness_state == "COMPLETE_SOURCE"
    assert not source.limitations
    entries = {entry["repo_relative_posix_path"]: entry for entry in source.entries}
    assert set(entries) == set(rows)
    assert list(entries) == sorted(rows, key=lambda name: name.encode("utf-8"))
    for path, (mode, raw) in rows.items():
        assert entries[path]["relevant_mode"] == mode
        assert entries[path]["byte_length"] == len(raw)
        assert entries[path]["content_raw_digest"] == hashlib.sha256(raw).hexdigest()
    assert base64.b64decode(entries["link"]["symlink_target"], validate=True) == rows["link"][1]
    # Git's export metadata can omit the Unix creator/type bits. As in the
    # retained HEAD representation producer, bind transport metadata to the
    # independently read tree while preserving every exported byte and name.
    exported = git(repo, "archive", "--format=zip", head)
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(exported)) as reader, zipfile.ZipFile(output, "w") as writer:
        members = [info for info in reader.infolist() if not info.is_dir()]
        assert {info.filename for info in members} == set(rows)
        assert len(members) == len(rows)
        for info in members:
            raw = reader.read(info)
            assert raw == rows[info.filename][1]
            retained = zipfile.ZipInfo(info.filename)
            retained.create_system = 3
            retained.external_attr = int(entries[info.filename]["relevant_mode"], 8) << 16
            writer.writestr(retained, raw)
    assert read_complete_source_archive(output.getvalue(), source) == {path: raw for path, (_, raw) in rows.items()}


@pytest.mark.parametrize("entry_type", ["LFS", "SUBMODULE"])
def test_real_unresolved_source_member_cannot_be_omitted_or_promoted(source_repo, entry_type):
    repo, _ = source_repo
    add_blob(repo, "base", "100644", b"base")
    base = commit(repo)
    if entry_type == "LFS":
        raw = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"0" * 64 + b"\nsize 12\n"
        add_blob(repo, "unresolved", "100644", raw)
    else:
        git(repo, "update-index", "--add", "--cacheinfo", "160000", base, "unresolved")
    head = commit(repo)
    source = materialize_local_source(repo, explicit_sha=head)
    assert source.completeness_state == "BOUNDED_SOURCE"
    assert any(entry["repo_relative_posix_path"] == "unresolved" for entry in source.entries)
    assert any("UNMATERIALIZED_" + entry_type + ":unresolved" == reason for reason in source.limitations)
    with pytest.raises(ValidationError, match="SOURCE_ARCHIVE_INCOMPLETE_SOURCE"):
        read_complete_source_archive(git(repo, "archive", "--format=zip", head), source)

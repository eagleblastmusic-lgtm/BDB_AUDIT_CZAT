from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.source.git_resolver import resolve_local_repository, validate_repository_location
from bdb_audit.source.materializer import materialize_local_source


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "target"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "ru02@example.invalid")
    _git(repo, "config", "user.name", "RU02 Test")
    (repo / "alpha.txt").write_bytes(b"alpha\n")
    _git(repo, "add", "alpha.txt")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_d20_arbitrary_40hex_is_not_accepted_without_commit_object(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(ValidationError):
        resolve_local_repository(repo, explicit_sha="f" * 40)


def test_d20_annotated_tag_is_peeled_to_commit_and_tree(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    expected_commit = _git(repo, "rev-parse", "HEAD")
    expected_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    _git(repo, "tag", "-a", "v1", "-m", "annotated")
    tag_object = _git(repo, "rev-parse", "v1")
    assert tag_object != expected_commit

    resolved = resolve_local_repository(repo, ref="v1")
    assert resolved.commit_object_id == expected_commit
    assert resolved.tree_object_id == expected_tree
    assert resolved.commit_object_id != resolved.tree_object_id


def test_d01_materializer_builds_full_manifest_from_exact_tree(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "nested").mkdir()
    (repo / "nested" / "beta.bin").write_bytes(b"\x00\x01beta")
    _git(repo, "add", "nested/beta.bin")
    _git(repo, "commit", "-m", "second")

    materialized = materialize_local_source(repo)
    assert materialized.completeness_state == "COMPLETE_SOURCE"
    assert materialized.identity.commit_object_id == _git(repo, "rev-parse", "HEAD")
    assert materialized.identity.tree_object_id == _git(repo, "rev-parse", "HEAD^{tree}")

    entries = {entry["repo_relative_posix_path"]: entry for entry in materialized.entries}
    assert set(entries) == {"alpha.txt", "nested/beta.bin"}
    assert entries["alpha.txt"]["content_raw_digest"] == hashlib.sha256(b"alpha\n").hexdigest()
    assert entries["nested/beta.bin"]["content_raw_digest"] == hashlib.sha256(b"\x00\x01beta").hexdigest()
    assert list(entries) == sorted(entries, key=lambda p: p.encode("utf-8"))


def test_d01_unmaterialized_lfs_pointer_blocks_complete_source(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    pointer = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + b"0" * 64 + b"\nsize 123\n"
    )
    (repo / "large.dat").write_bytes(pointer)
    _git(repo, "add", "large.dat")
    _git(repo, "commit", "-m", "lfs pointer")

    materialized = materialize_local_source(repo)
    assert materialized.completeness_state != "COMPLETE_SOURCE"
    assert any(reason.startswith("UNMATERIALIZED_LFS:large.dat") for reason in materialized.limitations)


def test_d26_credential_bearing_urls_are_rejected_without_echoing_secret() -> None:
    for value in (
        "https://user:super-secret@example.com/owner/repo.git",
        "https://example.com/owner/repo.git?access_token=super-secret",
        "https://example.com/owner/repo.git?password=super-secret",
    ):
        with pytest.raises(ValidationError) as exc_info:
            validate_repository_location(value)
        assert exc_info.value.code == "CREDENTIALS_IN_SOURCE_URL"
        assert "super-secret" not in str(exc_info.value)

    assert validate_repository_location("https://github.com/owner/repo.git") == "https://github.com/owner/repo.git"

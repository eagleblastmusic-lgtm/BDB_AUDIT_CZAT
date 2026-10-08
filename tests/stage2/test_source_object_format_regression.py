from pathlib import Path

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.source import git_resolver


@pytest.mark.parametrize("object_format,commit_length,tree_length,code", [
    ("sha1", 40, 40, None), ("sha256", 64, 64, None),
    ("sha1", 64, 40, "INVALID_GIT_OBJECT_ID"),
    ("sha256", 40, 64, "INVALID_GIT_OBJECT_ID"),
    ("sha1", 40, 64, "INVALID_GIT_TREE_OBJECT_ID"),
    ("sha256", 64, 40, "INVALID_GIT_TREE_OBJECT_ID"),
    ("sha512", 64, 64, "INVALID_GIT_OBJECT_ID"),
    ("sha1", 41, 40, "INVALID_GIT_OBJECT_ID"),
])
def test_repository_algorithm_controls_exact_ids(monkeypatch, object_format, commit_length, tree_length, code):
    def run(repo, args):
        if args == ["rev-parse", "--show-object-format"]:
            return object_format
        if args[0] == "cat-file":
            return "commit"
        return "a" * (tree_length if args[-1].endswith("^{tree}") else commit_length)

    monkeypatch.setattr(git_resolver, "_run_git", run)
    if code is None:
        assert git_resolver._verify_commit(Path("unused"), "HEAD") == ("a" * commit_length, "a" * tree_length)
    else:
        with pytest.raises(ValidationError) as error:
            git_resolver._verify_commit(Path("unused"), "HEAD")
        assert error.value.code == code


@pytest.mark.parametrize("length", [41, 48, 63])
def test_intermediate_object_lengths_are_not_supported(length):
    assert not git_resolver._HEX_OBJECT.fullmatch("a" * length)


@pytest.mark.parametrize("object_format,commit_length,tree_length,valid", [
    ("sha1", 40, 40, True), ("sha256", 64, 64, True),
    ("sha1", 64, 40, False), ("sha256", 40, 64, False),
    ("sha1", 40, 64, False), ("sha256", 64, 40, False),
    ("sha1", 41, 40, False), ("sha512", 64, 64, False),
])
def test_workflow_descriptor_cannot_undo_verified_algorithm_shape(object_format, commit_length, tree_length, valid):
    from bdb_audit.workflow.source_target import ResolvedSource

    kwargs = dict(target_type="local", location="CONTROLLED", display_name="CONTROLLED", ref="HEAD",
                  exact_commit_sha="a" * commit_length, exact_tree_sha="b" * tree_length, object_format=object_format)
    if valid:
        assert ResolvedSource(**kwargs).object_format == object_format
    else:
        with pytest.raises(ValueError):
            ResolvedSource(**kwargs)

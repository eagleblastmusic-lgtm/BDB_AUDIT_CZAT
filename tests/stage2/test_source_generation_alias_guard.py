"""Source alias conflicts cannot be hidden by changed archive representations."""
import copy

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.history.authority_hooks import _check_source_generation_aliases


def body(alias="source_a", digest="a" * 64):
    return {"source_generation_id": alias, "source_identity_ref": {
        "kind": "source_identity", "revision_digest": digest,
        "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "source_schema_exact",
    }, "representation_refs": []}


def test_same_identity_and_alias_can_retain_another_archive_representation():
    old = body()
    changed = copy.deepcopy(old)
    changed["representation_refs"] = [{"raw_digest": "c" * 64}]
    changed["source_identity_ref"]["ref_class"] = "PRIOR_ACCEPTED_ONLY"
    _check_source_generation_aliases([old, changed])


@pytest.mark.parametrize("changed", [body(digest="b" * 64), body(alias="source_b")])
def test_identity_or_alias_remapping_is_a_conflict(changed):
    with pytest.raises(ValidationError, match="SOURCE_IDENTITY_CONFLICT"):
        _check_source_generation_aliases([body(), changed])


def test_schema_substitution_is_not_the_same_authoritative_identity():
    changed = body()
    changed["source_identity_ref"]["schema_revision_ref"] = "another_schema"
    with pytest.raises(ValidationError, match="SOURCE_IDENTITY_CONFLICT"):
        _check_source_generation_aliases([body(), changed])


def test_new_material_identity_can_have_its_own_new_generation_alias():
    _check_source_generation_aliases([body(), body(alias="source_b", digest="b" * 64)])


@pytest.mark.parametrize("mode,field,wrong_field", [
    ("AUTHORIZED_GIT", "repository_authority_ref", "snapshot_authority_ref"),
    ("AUTHORIZED_SNAPSHOT", "snapshot_authority_ref", "repository_authority_ref"),
])
def test_generation_authority_branch_agrees_with_exact_identity(mode, field, wrong_field):
    from bdb_audit.history.authority_hooks import _validate_source_generation_context
    from bdb_audit.history.objects import CanonicalObject
    from tests.f2.helpers import bootstrap_fixture

    _, _, objects, parts = bootstrap_fixture()
    identity_body = copy.deepcopy(dict(next(obj for obj in objects if obj.kind == "source_identity").body))
    identity_body["authority_mode"] = mode
    if mode == "AUTHORIZED_GIT":
        identity_body.update(git_commit_object_id="a" * 40, git_tree_object_id="b" * 40)
    identity = CanonicalObject("source_identity", identity_body)
    generation = copy.deepcopy(dict(parts["source_generation"].body))
    authority = generation.pop("snapshot_authority_ref")
    generation[field] = authority
    generation["source_identity_ref"] = identity.as_ref().as_dict()
    _validate_source_generation_context(CanonicalObject("source_generation", generation),
                                        con=None, content_objects=[identity])
    generation[wrong_field] = generation.pop(field)
    with pytest.raises(ValidationError, match="SOURCE_IDENTITY_CONFLICT"):
        _validate_source_generation_context(CanonicalObject("source_generation", generation),
                                            con=None, content_objects=[identity])


@pytest.mark.parametrize("changed", [{}, {"source_generation_id": "source_a", "source_identity_ref": None}])
def test_incomplete_binding_is_not_a_successful_alias_mapping(changed):
    with pytest.raises(ValidationError, match="SOURCE_IDENTITY_CONFLICT"):
        _check_source_generation_aliases([changed])


@pytest.mark.parametrize("schema", ["legacy_schema", {"kind": "schema_revision", "revision_digest": "b" * 64,
                                                   "schema_revision_ref": {"root": "installation"}}])
def test_typed_identity_is_hashable_and_compares_the_entire_schema_reference(schema):
    from bdb_audit.history.authority_hooks import _typed_ref_identity

    ref = body()["source_identity_ref"]
    ref["schema_revision_ref"] = schema
    identical = copy.deepcopy(ref)
    identical["ref_class"] = "PRIOR_ACCEPTED_ONLY"
    assert {_typed_ref_identity(ref): "target"}[_typed_ref_identity(identical)] == "target"
    changed = copy.deepcopy(ref)
    changed["schema_revision_ref"] = {"different": schema}
    assert _typed_ref_identity(changed) != _typed_ref_identity(ref)


def test_alias_conflict_in_bootstrap_closure_leaves_no_durable_history(tmp_path):
    from bdb_audit.history.objects import CanonicalObject
    from bdb_audit.history.store import TransactionalHistoryStore
    from tests.f2.helpers import bootstrap_fixture

    profile, command, objects, parts = bootstrap_fixture()
    original = parts["source_generation"]
    changed = dict(original.body)
    changed["source_generation_id"] = "second_alias"
    conflicting = CanonicalObject("source_generation", changed)
    store = TransactionalHistoryStore(tmp_path / "alias.sqlite")
    with pytest.raises(ValidationError, match="SOURCE_IDENTITY_CONFLICT"):
        store.accept(command, immutable_objects=(*objects, conflicting), bootstrap_profile=profile)
    assert store.head() is None
    assert store.commits() == []
    assert store.receipt(command.command_id) is None
    result = store.accept(command, immutable_objects=objects, bootstrap_profile=profile)
    assert result.head.commit_seq == 1


@pytest.mark.parametrize("helper", ["history", "projection"])
def test_complete_structured_schema_identity_ignores_mapping_insertion_order(helper):
    from bdb_audit.history.authority_hooks import _ref_identity as history_identity
    from bdb_audit.workflow.assurance_projection import _ref_identity as projection_identity

    identity = history_identity if helper == "history" else projection_identity
    ref = body()["source_identity_ref"]
    ref["schema_revision_ref"] = {"kind": "schema", "revision_digest": "b" * 64}
    reordered = copy.deepcopy(ref)
    reordered["schema_revision_ref"] = dict(reversed(list(ref["schema_revision_ref"].items())))
    assert identity(ref) == identity(reordered)
    assert {identity(ref): "retained"}[identity(reordered)] == "retained"
    substituted = copy.deepcopy(ref)
    substituted["schema_revision_ref"]["revision_digest"] = "c" * 64
    assert len(sorted([identity(ref), identity(substituted)])) == 2
    substituted = copy.deepcopy(ref)
    substituted["digest_profile"] = "OTHER"
    assert identity(ref) != identity(substituted)


def test_finalization_ref_sets_compare_complete_structured_schema_keys():
    from bdb_audit.history.authority_hooks import _require_same_ref_set

    first = body()["source_identity_ref"]
    first["schema_revision_ref"] = {"kind": "schema", "revision_digest": "b" * 64}
    second = copy.deepcopy(first)
    second["schema_revision_ref"]["revision_digest"] = "c" * 64
    _require_same_ref_set([first, second], [second, first], "inputs")
    with pytest.raises(ValidationError, match="FINALIZATION_BINDING_CONFLICT"):
        _require_same_ref_set([first, second], [first, first], "inputs")


@pytest.mark.parametrize("prior", [False, True])
@pytest.mark.parametrize("field", ["materialized_source_manifest_ref", "source_identity_profile_ref", "snapshot_authority_ref", "authority_mode"])
def test_generation_cannot_contradict_its_exact_identity_context(tmp_path, prior, field):
    from dataclasses import replace
    from bdb_audit.history.objects import CanonicalObject
    from bdb_audit.history.store import TransactionalHistoryStore
    from tests.f2.helpers import bootstrap_fixture

    profile, command, objects, parts = bootstrap_fixture()
    store = TransactionalHistoryStore(tmp_path / "context.sqlite")
    first = store.accept(command, immutable_objects=objects, bootstrap_profile=profile) if prior else None
    body_changed = copy.deepcopy(dict(parts["source_generation"].body))
    additional = []
    if field == "materialized_source_manifest_ref":
        manifest = next(obj for obj in objects if obj.kind == "source_manifest")
        other_body = copy.deepcopy(dict(manifest.body))
        other_body["entries"][0]["repo_relative_posix_path"] = "different.md"
        other = CanonicalObject("source_manifest", other_body)
        additional.append(other)
        body_changed[field] = other.as_ref().as_dict()
    elif field == "authority_mode":
        body_changed["repository_authority_ref"] = body_changed.pop("snapshot_authority_ref")
    else:
        body_changed[field]["revision_digest"] = "d" * 64
    additional.append(CanonicalObject("source_generation", body_changed))
    if prior:
        command = replace(command, command_id="command_323e4567-e89b-42d3-a456-426614174000",
                          command_kind="RECORD_FOUNDATION_FACT", campaign_ref="campaign_fixture",
                          expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **first.head.as_dict()},
                          proposed_campaign_id=None, history_namespace_ref=None, bootstrap_profile_ref=None)
    before = (store.head(), store.commits())
    with pytest.raises(ValidationError, match="SOURCE_IDENTITY_CONFLICT"):
        store.accept(command, expected_head=first.head if prior else None,
                     immutable_objects=tuple(additional) if prior else (*objects, *additional),
                     bootstrap_profile=None if prior else profile)
    assert (store.head(), store.commits()) == before
    assert store.receipt(command.command_id) is None
    assert (TransactionalHistoryStore(tmp_path / "context.sqlite").head(), store.commits()) == before

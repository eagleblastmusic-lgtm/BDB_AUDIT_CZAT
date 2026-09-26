import hashlib
import json
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.orchestration.capability import (CapabilityBroker, DeliveryProfile,
                                                GrantBody, ProjectionPolicy, ViewManifest)


def ref(kind, seed):
    return {"kind": kind, "revision_digest": hashlib.sha256(seed.encode()).hexdigest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_TARGET/" + kind,
            "ref_class": "CONTENT_OR_PRIOR"}


def test_positive_view_excludes_hidden_and_transitive_forbidden_bytes():
    root = ref("finding_claim_revision", "root")
    child = ref("observation", "child")
    artifacts = {
        root["revision_digest"]: {"kind": "finding_claim_revision", "safe": "claim", "secret": "prior finding",
                                  "observation_ref": child, "filename": "hidden.json"},
        child["revision_digest"]: {"kind": "observation", "value": "own", "raw_digest": "a" * 64},
    }
    policy = ProjectionPolicy("pre", "1", {
        "finding_claim_revision": ("safe", "observation_ref"),
        "observation": ("value",),
    }, allowed_kinds=("finding_claim_revision", "observation"))
    manifest = ViewManifest("view", {"kind": "projection_policy", "revision_digest": "p"},
                            (root, child), phase="PRE_REVEAL")
    broker = CapabilityBroker(artifacts)
    view_ref, raw = broker.prepare_view(manifest, policy)
    assert b"prior finding" not in raw and b"hidden.json" not in raw and b"raw_digest" not in raw
    assert broker.resolve_view(view_ref) == raw
    with pytest.raises(ValidationError, match="GRANT_NOT_ACCEPTED"):
        broker.deliver({"revision_digest": "b" * 64}, view_ref)

    no_child = ViewManifest("view2", manifest.projection_policy_ref, (root,))
    with pytest.raises(ValidationError, match="VIEW_TRANSITIVE_LEAK"):
        broker.prepare_view(no_child, policy)


def test_grant_is_accepted_before_delivery():
    attempt, view, delivery = ref("attempt", "a"), ref("view_manifest", "v"), ref("delivery_spec", "d")
    grant = GrantBody(attempt, {"variant": "ACCEPTED_HISTORY_CUT", "accepted_head_seq": 1}, view,
                     delivery, "forbidden", "CONTROLLED")
    broker = CapabilityBroker({"x": {"kind": "claim", "safe": 1}})
    # The delivery profile itself is an immutable proposal; the broker's
    # accepted grant token is the only path to delivery.
    with pytest.raises(ValidationError, match="GRANT_NOT_ACCEPTED"):
        broker.accept_grant(grant)


@pytest.mark.parametrize(
    ("nested_ref", "expected_error"),
    [
        ("cycle", "VIEW_REFERENCE_CYCLE"),
        ("unknown", "VIEW_TRANSITIVE_LEAK"),
    ],
)
def test_recursive_positive_view_rejects_nested_cycles_and_unknown_refs(
    nested_ref, expected_error
):
    root = ref("finding_claim_revision", "nested-root")
    child = ref("finding_claim_revision", "nested-child")
    unknown = ref("finding_claim_revision", "nested-unknown")
    root_key = root["revision_digest"]
    child_key = child["revision_digest"]
    unknown_key = unknown["revision_digest"]

    root_target = child if nested_ref == "cycle" else unknown
    artifact_map = {
        root_key: {
            "kind": "finding_claim_revision",
            "details": {"related_refs": [root_target]},
        },
        child_key: {
            "kind": "finding_claim_revision",
            "details": {"related_refs": [root]},
        },
    }
    if nested_ref == "unknown":
        artifact_map[unknown_key] = {
            "kind": "finding_claim_revision",
            "details": {"related_refs": []},
        }

    policy = ProjectionPolicy(
        "nested",
        "1",
        {
            "finding_claim_revision": ("details",),
            "finding_claim_revision.details": ("related_refs",),
        },
        allowed_kinds=("finding_claim_revision",),
    )
    manifest = ViewManifest(
        "nested-view",
        {"kind": "projection_policy", "revision_digest": "policy"},
        (root, child) if nested_ref == "cycle" else (root,),
        phase="PRE_REVEAL",
    )

    broker = CapabilityBroker(artifact_map)
    with pytest.raises(ValidationError, match=expected_error):
        broker.prepare_view(manifest, policy)

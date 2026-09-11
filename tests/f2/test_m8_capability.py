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

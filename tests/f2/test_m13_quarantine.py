import hashlib
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.knowledge.quarantine import ClaimQuarantine
from bdb_audit.orchestration.capability import ProjectionPolicy


def ref(kind, seed):
    return {"kind": kind, "revision_digest": hashlib.sha256(seed.encode()).hexdigest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_TARGET/" + kind,
            "ref_class": "CONTENT_OR_PRIOR"}


def test_quarantine_positive_bytes_and_opaque_namespace():
    root, child = ref("finding_claim_revision", "root"), ref("observation", "child")
    artifacts = {root["revision_digest"]: {"kind": "finding_claim_revision", "claim": "safe", "observation_ref": child,
                                            "prior_severity": "HIGH", "filename": "prior.json"},
                 child["revision_digest"]: {"kind": "observation", "value": "own", "raw_evidence": "secret"}}
    policy = ProjectionPolicy("claim", "1", {"finding_claim_revision": ("claim", "observation_ref"),
                                               "observation": ("value",)},
                              allowed_kinds=("finding_claim_revision", "observation"))
    q = ClaimQuarantine(artifacts=artifacts, policy=policy)
    view = q.reveal(root_ref=root, allowed_refs=(root["revision_digest"], child["revision_digest"]))
    assert b"prior_severity" not in view.raw and b"prior.json" not in view.raw and b"raw_evidence" not in view.raw
    assert q.resolve(view.view_ref) == view.raw
    with pytest.raises(ValidationError, match="OPAQUE_VIEW_REF"):
        q.resolve({"namespace": "BDB_VIEW", "view_digest": view.view_ref.view_digest})


def test_transitive_forbidden_ref_fails_closed():
    root, forbidden = ref("finding_claim_revision", "root2"), ref("legacy_raw_ref", "raw")
    policy = ProjectionPolicy("claim", "1", {"finding_claim_revision": ("forbidden_ref",)},
                              allowed_kinds=("finding_claim_revision",))
    q = ClaimQuarantine(artifacts={root["revision_digest"]: {"kind": "finding_claim_revision", "forbidden_ref": forbidden},
                                   forbidden["revision_digest"]: {"kind": "legacy_raw_ref", "raw": "secret"}}, policy=policy)
    with pytest.raises(ValidationError, match="VIEW_TRANSITIVE_LEAK"):
        q.reveal(root_ref=root, allowed_refs=(root["revision_digest"],))


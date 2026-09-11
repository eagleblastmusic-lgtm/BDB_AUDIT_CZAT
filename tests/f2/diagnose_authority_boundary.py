"""Reproduce F2 implementation blockers; never a milestone acceptance gate."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bdb_audit.orchestration.capability import (
    CapabilityBroker, GrantBody, ProjectionPolicy, ViewManifest,
)
from bdb_audit.knowledge.exposure import DiscoveryRecord, blind_origin_eligible
from bdb_audit.schemas.foundation import foundation_schema_bindings
from bdb_audit.core.errors import ValidationError


def diagnose():
    def ref(kind, digit):
        return {"kind": kind, "revision_digest": digit * 64,
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": "BDB_SCHEMA_REGISTRY::" + kind + "/1",
                "ref_class": "CONTENT_OR_PRIOR"}

    root = ref("observation", "a")
    policy = ProjectionPolicy("diagnostic", "1", {"observation": ("value",)},
                              allowed_kinds=("observation",))
    manifest = ViewManifest("diagnostic", policy.as_object().ref.as_dict(), (root,))
    broker = CapabilityBroker({root["revision_digest"]: {"kind": "observation", "value": "delivered"}})
    view, raw = broker.prepare_view(manifest, policy)
    cut = {"variant": "ACCEPTED_HISTORY_CUT", "campaign_id": "unverified",
           "accepted_head_seq": 1, "accepted_head_hash": "b" * 64,
           "governing_policy_ref": "unverified", "governing_spec_refs": ["unverified"]}
    grant = GrantBody(ref("attempt", "c"), cut, manifest.ref,
                      ref("delivery_spec", "d"), "unverified", "CONTROLLED")
    try:
        token = broker.accept_grant(grant)
        delivered_without_history = broker.deliver(token, view) == raw
    except ValidationError:
        delivered_without_history = False
    discovery = DiscoveryRecord(
        ref("lane_run", "e"), ref("attempt", "c"), ref("source_generation", "f"),
        cut, ref("knowledge_state", "a"), ref("external_profile_ref", "b"),
        ref("actor_or_authority_ref", "c"), accepted_precursor=True,
        isolation_class="ENFORCED",
    )
    try:
        blind_without_history = blind_origin_eligible(discovery, accepting_head_seq=2)
    except ValidationError:
        blind_without_history = False
    try:
        empty_command_schema_passes = foundation_schema_bindings().validate_schema(
            "command_envelope", b"{}") == {}
    except ValidationError:
        empty_command_schema_passes = False
    return {
        "diagnostic_id": "F2-IMPLEMENTATION-AUTHORITY-003",
        "status": "DEFECTS_REPRODUCED" if any((delivered_without_history, blind_without_history, empty_command_schema_passes)) else "ORIGINAL_REPRODUCERS_CLOSED_NOT_PHASE_QUALIFICATION",
        "history_store_created": False,
        "delivery_without_accepted_history": delivered_without_history,
        "blind_origin_from_caller_assertion": blind_without_history,
        "empty_command_passes_foundation_executable_schema": empty_command_schema_passes,
        "qualification_pass": False,
    }


if __name__ == "__main__":
    print(json.dumps(diagnose(), sort_keys=True))
    raise SystemExit(2)

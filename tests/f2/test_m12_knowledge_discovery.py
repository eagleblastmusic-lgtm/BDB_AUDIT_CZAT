import hashlib
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.knowledge import (DiscoveryRecord, KnowledgeState, blind_origin_eligible,
                                 classify_discovery)


def ref(kind, seed, cls="CONTENT_OR_PRIOR"):
    return {"kind": kind, "revision_digest": hashlib.sha256(seed.encode()).hexdigest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_TARGET/" + kind,
            "ref_class": cls}


def test_knowledge_state_is_attempt_bound_and_blind_origin_needs_earlier_cut():
    attempt = ref("attempt", "attempt")
    cut = {"variant": "ACCEPTED_HISTORY_CUT", "campaign_id": "c", "accepted_head_seq": 2,
           "accepted_head_hash": "a" * 64, "governing_policy_ref": "p", "governing_spec_refs": ["s"]}
    state = KnowledgeState(attempt, cut, ref("isolation_qualification", "iso"),
                           allowed_view_refs=(ref("view_manifest", "view"),), known_classes=("ALLOWED",))
    discovery = DiscoveryRecord(ref("lane_run", "lane"), attempt, ref("source_generation", "source"),
                                cut, state.as_object().ref.as_dict(), ref("external_profile_ref", "method", "HISTORY_CONTEXT_BINDING"),
                                ref("actor_or_authority_ref", "producer", "PRIOR_ACCEPTED_ONLY"),
                                classification="PRE_REVEAL_DISCOVERY", accepted_precursor=True,
                                isolation_class="ENFORCED")
    for seq in (2, 3):
        with pytest.raises(ValidationError, match="BLIND_ORIGIN_REQUIRES_ACCEPTED_PRECURSOR"):
            blind_origin_eligible(discovery, accepting_head_seq=seq)
    assert "classification" not in discovery.body()
    assert "accepted_precursor" not in discovery.body()


def test_provenance_classes_and_no_false_blind_claim():
    assert classify_discovery(pre_reveal=False, isolation_class="ENFORCED") == "POST_REVEAL_CONFIRMATION"
    assert classify_discovery(pre_reveal=True, isolation_class="ENFORCED", report_assisted=True) == "REPORT_ASSISTED_VERIFICATION"
    assert classify_discovery(pre_reveal=True, isolation_class="ENFORCED", contaminated=True) == "CONTAMINATED_DISCOVERY"
    assert classify_discovery(pre_reveal=True, isolation_class="UNKNOWN") == "UNKNOWN_ISOLATION_DISCOVERY"
    with pytest.raises(ValidationError, match="BLIND_ORIGIN_REQUIRES_ACCEPTED_PRECURSOR"):
        classify_discovery(pre_reveal=True, isolation_class="ENFORCED")

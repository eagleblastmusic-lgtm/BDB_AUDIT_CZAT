"""Focused regressions for the canonical POST_E6 accepted-history boundary."""
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.stop.e6 import AdaptiveE6Generator


def _cut(seq: int, digest_char: str, campaign: str = "campaign-post-e6") -> dict:
    return {
        "variant": "ACCEPTED_HISTORY_CUT",
        "campaign_id": campaign,
        "accepted_head_seq": seq,
        "accepted_head_hash": digest_char * 64,
        "governing_policy_ref": "pin:initial_governing_policy_ref",
        "governing_spec_refs": ["pin:initial_transition_profile_ref"],
    }


def test_post_e6_requires_strictly_newer_canonical_head() -> None:
    AdaptiveE6Generator.verify_post_e6_return_to_stop(_cut(31, "b"), _cut(30, "a"))

    with pytest.raises(ValidationError) as exc:
        AdaptiveE6Generator.verify_post_e6_return_to_stop(_cut(30, "a"), _cut(30, "a"))
    assert exc.value.code == "POST_E6_MUST_ADVANCE_HEAD"


def test_post_e6_rejects_legacy_cut_shape() -> None:
    with pytest.raises(ValidationError) as exc:
        AdaptiveE6Generator.verify_post_e6_return_to_stop(
            _cut(31, "b"),
            {"campaign_id": "campaign-post-e6", "commit_seq": 30, "commit_hash": "a" * 64},
        )
    assert exc.value.code == "ACCEPTED_HISTORY_CUT_REQUIRED"


def test_post_e6_rejects_campaign_switch() -> None:
    with pytest.raises(ValidationError) as exc:
        AdaptiveE6Generator.verify_post_e6_return_to_stop(
            _cut(31, "b", "campaign-other"),
            _cut(30, "a"),
        )
    assert exc.value.code == "POST_E6_CAMPAIGN_MISMATCH"

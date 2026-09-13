"""Tests for anti-false-PASS: Tampered builds, source drift, duplicate challenger, and lost evidence (RU13-A)."""
import hashlib
from pathlib import Path
import tempfile
import pytest

from bdb_audit.assurance.candidate_case import CandidateAssuranceCase
from bdb_audit.assurance.challenger import (
    ChallengerAssignment,
    ChallengerResult,
    E5ChallengerOrchestrator,
)
from bdb_audit.core.errors import ValidationError
from bdb_audit.release_validator import ReleaseValidator


def test_tampered_payload_fails_release_validator():
    """Bit-level tampering of standalone artifact payload triggers fail-closed error."""
    artifact = Path("dist/BDB_AUDIT_ASSISTANT_v2.0.3.py")
    if not artifact.exists():
        pytest.skip("Standalone artifact dist not present in source tree")

    original_text = artifact.read_text(encoding="utf-8")

    # Intentionally corrupt the payload digest
    tampered_text = original_text.replace(
        'PAYLOAD_RAW_DIGEST = "',
        'PAYLOAD_RAW_DIGEST = "tampered_digest_',
    )

    with tempfile.TemporaryDirectory() as td:
        tampered_artifact = Path(td) / "tampered_standalone.py"
        tampered_artifact.write_text(tampered_text, encoding="utf-8")

        validator = ReleaseValidator(tampered_artifact)
        with pytest.raises(ValidationError) as exc_info:
            validator.validate_all(check_reproducibility=False)
        assert "PAYLOAD_RAW_DIGEST_MISMATCH" in str(exc_info.value)


def _ref(kind: str, digest_suffix: str = "1", ref_class: str = "CONTENT_OR_PRIOR") -> dict:
    dig = (digest_suffix * 64)[:64]
    return {
        "kind": kind,
        "revision_digest": dig,
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_TARGET/{kind}",
        "ref_class": ref_class,
    }


def test_duplicate_challenger_assignment_is_rejected():
    """Reusing the same challenger assignment for both skeptic and hunter is strictly rejected."""
    cand_cut = {"campaign_id": "CAMP", "accepted_head_seq": 15, "accepted_head_hash": "a" * 64}
    assign_cut = {"campaign_id": "CAMP", "accepted_head_seq": 16, "accepted_head_hash": "b" * 64}
    result_cut = {"campaign_id": "CAMP", "accepted_head_seq": 17, "accepted_head_hash": "c" * 64}

    from bdb_audit.assurance.candidate_case import CandidateAssuranceCaseBuilder
    cac = CandidateAssuranceCaseBuilder(
        "cac1", _ref("cg", "1"), _ref("sg", "1"), cand_cut, _ref("inv", "1"), _ref("cs", "1")
    ).build()

    asgn = ChallengerAssignment(
        "a1", cac.ref, "FALSE_POSITIVE_SKEPTIC", "ALL", _ref("p", "1"), _ref("e", "1"), assign_cut
    )

    r1 = ChallengerResult("r1", asgn.ref, cac.ref, result_cut, "NO_MATERIAL_COUNTEREVIDENCE")
    r2 = ChallengerResult("r2", asgn.ref, cac.ref, result_cut, "NO_MATERIAL_COUNTEREVIDENCE")

    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(
        candidate=cac,
        skeptic_result=r1,
        hunter_result=r2,
        skeptic_assignment=asgn,
        hunter_assignment=asgn,
    )
    assert eligible is False
    assert "SAME_CHALLENGE_ASSIGNMENT" in reasons


def test_candidate_material_change_invalidates_prior_challengers():
    """Modifying candidate revision invalidates existing challenger results (no scoped reuse)."""
    cand_cut = {"campaign_id": "CAMP", "accepted_head_seq": 15, "accepted_head_hash": "a" * 64}
    result_cut = {"campaign_id": "CAMP", "accepted_head_seq": 16, "accepted_head_hash": "b" * 64}

    from bdb_audit.assurance.candidate_case import CandidateAssuranceCaseBuilder
    cac = CandidateAssuranceCaseBuilder(
        "cac1", _ref("cg", "1"), _ref("sg", "1"), cand_cut, _ref("inv", "1"), _ref("cs", "1")
    ).build()

    stale_ref = {"kind": "candidate_assurance_case", "revision_digest": "stale" * 12 + "0000"}
    r1 = ChallengerResult("r1", _ref("a", "1"), stale_ref, result_cut, "NO_MATERIAL_COUNTEREVIDENCE")
    r2 = ChallengerResult("r2", _ref("b", "1"), stale_ref, result_cut, "NO_MATERIAL_COUNTEREVIDENCE")

    eligible, reasons = E5ChallengerOrchestrator.validate_challenger_results_pair(cac, r1, r2)
    assert eligible is False
    assert "CHALLENGER_RESULTS_INVALIDATED_BY_CANDIDATE_CHANGE" in reasons

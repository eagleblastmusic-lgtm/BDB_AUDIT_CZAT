"""Test-only dual evaluation. M1 expectation bytes remain independent and pinned."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/compatibility"))
from corpus_support import CORPUS, load_legacy, selection, verify_identity, replay
from bdb_audit.assurance import legacy as v2

# EXPECTATION_BASIS.md properties mapped to implementation diagnostics. These
# are test labels, not a compatibility policy or runtime authority.
SAFETY_DIAGNOSTICS = {
    "VARIANT_IDENTITY": {"RUN_MANIFEST_VARIANT_MISMATCH"},
    "RUN_IDENTITY": {"AUDIT_ATTEMPT_ID_MISMATCH"},
    "AUDIT_IDENTITY": {"AUDIT_REQUEST_ID_MISMATCH"},
    "SOURCE_COMMIT_IDENTITY": {"SOURCE_SHA_MISMATCH"},
    "SOURCE_TREE_IDENTITY": {"SOURCE_TREE_MISMATCH"},
    "CONFLICTING_MEMBER": {"CONFLICTING_DUPLICATE_HANDOFF_MEMBER"},
    "ARTIFACT_HASH_IDENTITY": {"HANDOFF_HASH_MISMATCH"},
    "RETAINED_SNAPSHOT_REQUIRED": {"F1_SNAPSHOT_MEMBER_COUNT_INVALID", "F2_SNAPSHOT_MEMBER_COUNT_INVALID"},
    "RAW_LEDGER_PREFIX": {"F1_LEDGER_RAW_PREFIX_MISMATCH", "F2_LEDGER_RAW_PREFIX_MISMATCH"},
    "CHECKPOINT_SEQUENCE_BINDING": {"F1_DECLARED_SEQUENCE_END_MISMATCH", "F2_DECLARED_SEQUENCE_END_MISMATCH"},
    "REVEAL_ORDER": {"ATTESTATION_EARLY_STAGED_SEMANTICS_EXPOSURE"},
    "SOURCE_GENERATION_ISOLATION": {"ATTESTATION_SOURCE_GENERATIONS_MIXED"},
    "CHECKPOINT_NON_SUBSTITUTION": {"ATTESTATION_SUBSTITUTE_F2_CREATED"},
    "ZIP_PATH_SAFETY": {"UNSAFE_ZIP_PATH"},
    "ZIP_MEMBER_UNIQUENESS": {"DUPLICATE_ZIP_MEMBER_NAMES"},
    "FINAL_ARTIFACT_FAMILY": {"MISSING_REQUIRED_FINAL_ARTIFACT"},
}


def observe(module, row, frozen):
    call = row["legacy_call"]
    variant, step = selection(frozen, call["variant_id"], call["step_order"])
    path = CORPUS / row["path"]
    verify_identity(row, path.read_bytes())
    route = call["route"]
    if route == "prior":
        return module.validate_prior_handoff_bundle(path, variant, step)
    if route == "result":
        return module.validate_result_bundle(path, variant, step, False)
    if route == "attestation":
        return module.validate_attestation_bundle(path, variant, step)
    if route == "ticket":
        return module.validate_attestation_bundle(CORPUS / call["attestation_path"], variant, step, json.loads(path.read_bytes()))
    if route == "previous_prompt_self_test":
        if module is frozen:
            result = replay(frozen, row)
            return {"status": result["result"], "errors": result["errors"]}
        inputs = json.loads((CORPUS / "EXPECTATION_INPUTS.json").read_bytes())
        return module.validate_previous_prompt_bundle(path,
            consumer_variant_id=call["variant_id"],
            predecessor_variant_id=variant["direct_predecessor_variant_id"],
            bundle_sha256=inputs["previous_bundle_sha256"],
            prompt_hashes=inputs["previous_prompt_hashes"])
    raise AssertionError(route)


def semantic(result):
    # Exclude transport location and observation time, never identity/lineage.
    keys = ("status", "checkpoint_kind", "source_sha", "source_tree",
            "audit_request_id", "audit_attempt_id", "retained_snapshot_sha256",
            "snapshot_sequence_end", "ledger_sequence_end", "run_state", "run_state_source",
            "expected_artifact_family", "expected_prompt_sha256", "attestation_source_identity",
            "attestation_run_id", "attestation_audit_id", "expected_run_state")
    return {**{k: result[k] for k in keys if k in result},
            "error_families": sorted({e.split(":", 1)[0] for e in result["errors"]})}


def compare(observed, legacy_observed, safe_expected, *, known_bug=False, exception=None):
    """Two independent results. An exception must be an exact external decision.

    This test primitive never issues compatibility policy; required M1 has none.
    """
    same = observed == legacy_observed
    accepted = observed["status"] in ("PASS", "PASS_INTERMEDIATE")
    correct = accepted == (safe_expected == "ACCEPT")
    explained = bool(exception and exception.get("version") and exception.get("revision_digest")
                     and exception.get("legacy") == legacy_observed and exception.get("hardened") == observed)
    return {"preservation": same or explained, "correctness": correct,
            "unexplained_diff": int(not same and not explained),
            "bug_misclassified_safe": int(known_bug and accepted)}


def run_dual():
    manifest = json.loads((CORPUS / "manifest.json").read_bytes())
    assert manifest["unresolved_expectation_conflicts"] == []
    frozen = load_legacy()
    rows = []
    for row in manifest["fixtures"]:
        old = observe(frozen, row, frozen)
        new = observe(v2, row, frozen)
        assert old["status"] == row["legacy_observed_result"]
        assert semantic(old)["error_families"] == row["legacy_observed_error_family"]
        result = compare(semantic(new), semantic(old), row["independent_safe_expected_result"], known_bug=row["known_legacy_bug"])
        expected_family = row["independent_expected_error_family"]
        actual_families = set(semantic(new)["error_families"])
        result["correctness"] &= (not actual_families if expected_family == "NONE"
                                  else bool(actual_families & SAFETY_DIAGNOSTICS[expected_family]))
        rows.append({"fixture_id": row["fixture_id"], "expected": row["independent_safe_expected_result"],
                     "v1": semantic(old), "v2": semantic(new), **result})
    return rows

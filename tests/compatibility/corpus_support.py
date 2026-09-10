"""M1 test-only replay adapter. No v2 validator or production authority."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "LEGACY_COMPATIBILITY_CORPUS"
SOURCE = ROOT / "legacy/v1_4_4/BDB_AUDIT_ASSISTANT_PA_v5.2_WRAPPERS_5.4-RC1_v1.4.4_ARCHIVE.py"
SOURCE_SHA = "d851511fc5cf06e205426e843d1f43ac72edb2adf95b786c39e016a49fbda841"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_legacy():
    assert sha(SOURCE.read_bytes()) == SOURCE_SHA
    spec = importlib.util.spec_from_file_location("m1_frozen_legacy", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selection(legacy, variant_id, order):
    variant = next(v for v in legacy.DATA["variants"] if v["variant_id"] == variant_id)
    return variant, next(s for s in variant["steps"] if s["order"] == order)


def verify_identity(record, raw):
    if len(raw) != record["byte_length"] or sha(raw) != record["raw_digest"]:
        raise ValueError("FIXTURE_RAW_IDENTITY_MISMATCH")


def replay(legacy, row):
    path = CORPUS / row["path"]
    verify_identity(row, path.read_bytes())
    call = row["legacy_call"]
    variant, step = selection(legacy, call["variant_id"], call["step_order"])
    route = call["route"]
    if route == "prior":
        result = legacy.validate_prior_handoff_bundle(path, variant, step)
    elif route == "result":
        result = legacy.validate_result_bundle(path, variant, step, False)
    elif route == "attestation":
        result = legacy.validate_attestation_bundle(path, variant, step)
    elif route == "ticket":
        ticket = json.loads(path.read_bytes())
        att_path = CORPUS / call["attestation_path"]
        assert sha(att_path.read_bytes()) == call["attestation_raw_digest"]
        result = legacy.validate_attestation_bundle(att_path, variant, step, ticket)
    elif route == "previous_prompt_self_test":
        # Supply fixture bytes to the ORIGINAL full self-test, preserving the
        # frozen expected metadata. No copied/reimplemented legacy assertions.
        original = legacy.embedded_bytes
        item = step["previous_prompt_bundles"][0]
        supplied_count = 0
        def fixture_bytes(candidate):
            nonlocal supplied_count
            if candidate is item:
                supplied_count += 1
                supplied = dict(candidate, data_b64=base64.b64encode(path.read_bytes()).decode())
                return original(supplied)
            return original(candidate)
        legacy.embedded_bytes = fixture_bytes
        try:
            result = legacy.self_test(verbose=False)
        finally:
            legacy.embedded_bytes = original
        assert supplied_count >= 2, "Fixture must reach integrity and previous-prompt semantic checks"
    else:
        raise AssertionError(route)
    return {"result": result["status"], "errors": result["errors"],
            "error_families": sorted({e.split(":", 1)[0] for e in result["errors"]})}

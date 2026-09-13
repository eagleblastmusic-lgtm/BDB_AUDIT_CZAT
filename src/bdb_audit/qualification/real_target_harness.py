"""RU13-B independent v2.1 public-boundary qualification harness."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..coordinator.operations import AuditOperationApi
from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from .methodology_metrics import MethodologyMetrics
from .receipts import ActualRunReceipt, BenchmarkManifest
from .reference_corpus import PublicBoundaryCase, reference_corpus_digest, v21_reference_cases
from .reference_truth import v21_truth_manifests

_RESULT_SCHEMA = "RU13B-V21-QUALIFICATION-1"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _capture_cli(argv: list[str]) -> tuple[int, str, str]:
    # Lazy import prevents the qualification harness and CLI module from
    # becoming an import cycle when the CLI exposes qualification commands.
    from ..cli import run_cli

    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        rc = run_cli(argv)
    return rc, stdout.getvalue(), stderr.getvalue()


def _target_store(workspace: Path, case: PublicBoundaryCase) -> Path:
    root = workspace / case.case_id
    root.mkdir(parents=True, exist_ok=True)
    return root / "campaign.sqlite"


def _prepare_target(workspace: Path, case: PublicBoundaryCase) -> Path:
    store_path = _target_store(workspace, case)
    if store_path.exists():
        store_path.unlink()
    AuditOperationApi().create_campaign(
        store_path,
        seed=case.seed,
        target_repo="https://qualification.invalid/reference-target",
        commit_sha=case.target_sha,
    )
    if case.boundary == "CORRUPTED_HISTORY_STATUS":
        store = TransactionalHistoryStore(store_path)
        con = store._connect()
        try:
            row = con.execute("SELECT body FROM commits WHERE seq=1").fetchone()
            if row is None:
                raise ValidationError("REFERENCE_TARGET_SETUP_FAILED")
            body = json.loads(row[0])
            body["actor_ref"] = "ru13b-intentional-tamper"
            con.execute("UPDATE commits SET body=? WHERE seq=1", (canonical_bytes(body),))
        finally:
            con.close()
    return store_path


def _execute_case(workspace: Path, case: PublicBoundaryCase) -> tuple[str, ActualRunReceipt]:
    store_path = _prepare_target(workspace, case)
    output_dir = workspace / case.case_id / "full-report"

    if case.boundary == "AUDIT_STATUS":
        argv = ["audit", "status", "--store", str(store_path), "--json"]
    elif case.boundary == "CORRUPTED_HISTORY_STATUS":
        argv = ["audit", "status", "--store", str(store_path), "--json"]
    elif case.boundary == "FULL_ASSURANCE_REPORT":
        argv = [
            "report", "export", "--store", str(store_path),
            "--output", str(output_dir), "--format", "bundle", "--full-assurance", "--json",
        ]
    else:  # guarded by PublicBoundaryCase, retained as fail-closed defense
        raise ValidationError("REFERENCE_CASE_BOUNDARY_INVALID", case.boundary)

    rc, stdout, stderr = _capture_cli(argv)
    combined = (stdout + "\0" + stderr).encode("utf-8")
    raw_digest = hashlib.sha256(combined).hexdigest()

    if case.boundary == "AUDIT_STATUS":
        observed = "CLEAN" if rc == 0 else "UNKNOWN"
    elif case.boundary == "CORRUPTED_HISTORY_STATUS":
        observed = (
            "DEFECTIVE"
            if rc != 0 and "ACCEPTED_HISTORY_INTEGRITY_FAILURE" in stderr
            else "UNKNOWN"
        )
    else:
        # Before E1-E5/STOP/conclusion, a requested FULL assurance export must
        # refuse rather than manufacture a final result.
        observed = "BLOCKED" if rc != 0 else "CLEAN"

    receipt_status = "PASS" if observed != "UNKNOWN" else "UNKNOWN"
    receipt = ActualRunReceipt(
        receipt_id=f"run_{case.case_id}",
        benchmark_id=case.case_id,
        target_id=case.target_id,
        checker_id=f"public_boundary::{case.boundary}",
        execution_timestamp=_utc_timestamp(),
        exit_code=rc,
        status=receipt_status,
        raw_output_digest=raw_digest,
        evaluated_cases_count=1,
        passed_cases_count=1 if receipt_status == "PASS" else 0,
        failed_cases_count=0,
        unknown_cases_count=1 if receipt_status == "UNKNOWN" else 0,
        details={
            "observed_label": observed,
            "boundary": case.boundary,
            "case_revision": case.revision,
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        },
    )
    return observed, receipt


def score_reference_controls(
    manifests: Sequence[BenchmarkManifest],
    observed_results: Mapping[str, str],
) -> MethodologyMetrics:
    """Score clean/defective/blocked controls without hiding mismatches."""
    tp = fp = tn = fn = unsupported = unknown = 0
    anti_total = anti_passed = 0
    evaluated = 0
    mismatches: list[str] = []

    for manifest in manifests:
        observed = observed_results.get(manifest.target_id)
        if observed is None:
            mismatches.append(f"NOT_RUN:{manifest.target_id}")
            continue
        evaluated += 1
        expected = manifest.expected_label
        if expected == "CLEAN":
            if observed == "CLEAN":
                tn += 1
            else:
                fp += 1
                mismatches.append(f"CLEAN:{manifest.target_id}:{observed}")
        elif expected == "DEFECTIVE":
            anti_total += 1
            if observed == "DEFECTIVE":
                tp += 1
                anti_passed += 1
            else:
                fn += 1
                mismatches.append(f"DEFECTIVE:{manifest.target_id}:{observed}")
        elif expected == "BLOCKED":
            anti_total += 1
            if observed == "BLOCKED":
                anti_passed += 1
            else:
                unknown += 1
                mismatches.append(f"BLOCKED:{manifest.target_id}:{observed}")
        elif expected == "UNSUPPORTED":
            if observed == "UNSUPPORTED":
                unsupported += 1
            else:
                unknown += 1
                mismatches.append(f"UNSUPPORTED:{manifest.target_id}:{observed}")
        else:
            unknown += 1
            if observed != expected:
                mismatches.append(f"{expected}:{manifest.target_id}:{observed}")

    return MethodologyMetrics(
        total_targets=len(manifests),
        evaluated_targets=evaluated,
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
        unsupported_cases=unsupported,
        unknown_cases=unknown,
        anti_bypass_total=anti_total,
        anti_bypass_passed=anti_passed,
        denominator=len(manifests),
        scope_details={
            "scope": "RU13B_V21_PUBLIC_BOUNDARIES",
            "control_mismatches": mismatches,
        },
    )


def _receipt_dict(receipt: ActualRunReceipt) -> dict[str, Any]:
    return {
        "receipt_id": receipt.receipt_id,
        "benchmark_id": receipt.benchmark_id,
        "target_id": receipt.target_id,
        "checker_id": receipt.checker_id,
        "execution_timestamp": receipt.execution_timestamp,
        "exit_code": receipt.exit_code,
        "status": receipt.status,
        "raw_output_digest": receipt.raw_output_digest,
        "evaluated_cases_count": receipt.evaluated_cases_count,
        "passed_cases_count": receipt.passed_cases_count,
        "failed_cases_count": receipt.failed_cases_count,
        "unsupported_cases_count": receipt.unsupported_cases_count,
        "unknown_cases_count": receipt.unknown_cases_count,
        "execution_duration_ms": receipt.execution_duration_ms,
        "details": receipt.details,
        "receipt_digest": receipt.receipt_digest(),
    }


def _result_digest(body: Mapping[str, Any]) -> str:
    value = dict(body)
    value.pop("result_digest", None)
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def run_v21_reference_corpus(workspace: str | Path) -> dict[str, Any]:
    """Execute all public cases first, reveal the oracle partition second."""
    root = Path(workspace).resolve()
    root.mkdir(parents=True, exist_ok=True)
    cases = v21_reference_cases()
    observed: dict[str, str] = {}
    receipts: list[ActualRunReceipt] = []
    for case in cases:
        label, receipt = _execute_case(root, case)
        observed[case.target_id] = label
        receipts.append(receipt)

    # Truth is loaded only after actual observations exist.
    manifests = v21_truth_manifests()
    metrics = score_reference_controls(manifests, observed)
    body: dict[str, Any] = {
        "schema_version": _RESULT_SCHEMA,
        "status": "QUALIFIED" if metrics.is_methodology_qualified else "FAILED",
        "corpus_digest": reference_corpus_digest(cases),
        "case_count": len(cases),
        "observed_results": dict(sorted(observed.items())),
        "receipts": [_receipt_dict(receipt) for receipt in receipts],
        "truth_manifest_digests": [manifest.manifest_digest() for manifest in manifests],
        "metrics": metrics.to_dict(),
    }
    body["result_digest"] = _result_digest(body)
    return body


def _receipt_from_dict(body: Mapping[str, Any]) -> ActualRunReceipt:
    receipt = ActualRunReceipt(
        receipt_id=str(body.get("receipt_id", "")),
        benchmark_id=str(body.get("benchmark_id", "")),
        target_id=str(body.get("target_id", "")),
        checker_id=str(body.get("checker_id", "")),
        execution_timestamp=str(body.get("execution_timestamp", "")),
        exit_code=int(body.get("exit_code", 0)),
        status=str(body.get("status", "UNKNOWN")),
        raw_output_digest=str(body.get("raw_output_digest", "")),
        evaluated_cases_count=int(body.get("evaluated_cases_count", 0)),
        passed_cases_count=int(body.get("passed_cases_count", 0)),
        failed_cases_count=int(body.get("failed_cases_count", 0)),
        unsupported_cases_count=int(body.get("unsupported_cases_count", 0)),
        unknown_cases_count=int(body.get("unknown_cases_count", 0)),
        execution_duration_ms=int(body.get("execution_duration_ms", 0)),
        details=dict(body.get("details", {})),
    )
    if body.get("receipt_digest") != receipt.receipt_digest():
        raise ValidationError("REFERENCE_RECEIPT_DIGEST_MISMATCH", receipt.receipt_id)
    return receipt


def verify_v21_reference_result(result: Mapping[str, Any]) -> dict[str, Any]:
    if result.get("schema_version") != _RESULT_SCHEMA:
        raise ValidationError("REFERENCE_RESULT_SCHEMA_INVALID")
    if result.get("result_digest") != _result_digest(result):
        raise ValidationError("REFERENCE_RESULT_DIGEST_MISMATCH")
    if result.get("corpus_digest") != reference_corpus_digest():
        raise ValidationError("REFERENCE_CORPUS_DIGEST_MISMATCH")

    receipts_raw = result.get("receipts")
    if not isinstance(receipts_raw, list):
        raise ValidationError("REFERENCE_RECEIPTS_REQUIRED")
    receipts = [_receipt_from_dict(item) for item in receipts_raw if isinstance(item, dict)]
    if len(receipts) != len(v21_reference_cases()):
        raise ValidationError("REFERENCE_RECEIPT_DENOMINATOR_MISMATCH")

    observed = result.get("observed_results")
    if not isinstance(observed, dict):
        raise ValidationError("REFERENCE_OBSERVED_RESULTS_REQUIRED")
    manifests = v21_truth_manifests()
    expected_manifest_digests = [manifest.manifest_digest() for manifest in manifests]
    if result.get("truth_manifest_digests") != expected_manifest_digests:
        raise ValidationError("REFERENCE_TRUTH_PARTITION_MISMATCH")
    metrics = score_reference_controls(manifests, {str(k): str(v) for k, v in observed.items()})
    if result.get("metrics") != metrics.to_dict():
        raise ValidationError("REFERENCE_METRICS_MISMATCH")
    expected_status = "QUALIFIED" if metrics.is_methodology_qualified else "FAILED"
    if result.get("status") != expected_status:
        raise ValidationError("REFERENCE_STATUS_MISMATCH")
    return {
        "status": "PASS" if expected_status == "QUALIFIED" else "FAIL",
        "qualification_status": expected_status,
        "corpus_digest": result["corpus_digest"],
        "result_digest": result["result_digest"],
        "case_count": len(receipts),
        "metrics": metrics.to_dict(),
    }


__all__ = [
    "run_v21_reference_corpus",
    "verify_v21_reference_result",
    "score_reference_controls",
]

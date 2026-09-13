"""RU13-B oracle partition for the frozen v2.1 reference corpus.

Nothing in this module is passed to the public-boundary executor. The harness
loads it only after actual results have been collected.
"""
from __future__ import annotations

from .receipts import BenchmarkManifest
from .reference_corpus import v21_reference_cases

_EXPECTED = {
    "v21_clean_history": ("CLEAN", None),
    "v21_corrupt_history": ("DEFECTIVE", "DEFECT_ACCEPTED_HISTORY_TAMPER"),
    "v21_full_report_blocked": ("BLOCKED", "CONTROL_FULL_ASSURANCE_BEFORE_CLOSURE"),
}


def v21_truth_manifests() -> tuple[BenchmarkManifest, ...]:
    manifests: list[BenchmarkManifest] = []
    for case in v21_reference_cases():
        expected_label, defect_id = _EXPECTED[case.target_id]
        manifests.append(BenchmarkManifest(
            benchmark_id=case.case_id,
            target_id=case.target_id,
            target_sha=case.target_sha,
            expected_label=expected_label,
            defect_id=defect_id,
            split_membership="VALIDATION",
            domain_tags=("PUBLIC_BOUNDARY", "V2_1", case.boundary),
            metadata={"target_kind": "FROZEN_QUALIFICATION_RECIPE", "revision": case.revision},
        ))
    return tuple(manifests)


__all__ = ["v21_truth_manifests"]

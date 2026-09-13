"""RU13-C holdout oracle partition, never passed to public-boundary execution."""
from __future__ import annotations

from .holdout_corpus import holdout_cases
from .receipts import BenchmarkManifest

_EXPECTED = {
    "v21_holdout_clean": ("CLEAN", None),
    "v21_holdout_corrupt": ("DEFECTIVE", "HOLDOUT_ACCEPTED_HISTORY_TAMPER"),
    "v21_holdout_full_block": ("BLOCKED", "HOLDOUT_FULL_ASSURANCE_BEFORE_CLOSURE"),
}


def holdout_truth_manifests() -> tuple[BenchmarkManifest, ...]:
    result: list[BenchmarkManifest] = []
    for case in holdout_cases():
        label, defect_id = _EXPECTED[case.target_id]
        result.append(BenchmarkManifest(
            benchmark_id=case.case_id,
            target_id=case.target_id,
            target_sha=case.target_sha,
            expected_label=label,
            defect_id=defect_id,
            split_membership="HOLDOUT",
            domain_tags=("PUBLIC_BOUNDARY", "V2_1", "HOLDOUT", case.boundary),
            metadata={"target_kind": "FROZEN_HOLDOUT_RECIPE", "revision": case.revision},
        ))
    return tuple(result)


__all__ = ["holdout_truth_manifests"]

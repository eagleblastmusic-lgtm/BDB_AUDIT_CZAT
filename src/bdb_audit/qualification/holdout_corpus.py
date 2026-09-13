"""RU13-C holdout public-boundary corpus. Expected labels live elsewhere."""
from __future__ import annotations

import hashlib

from ..core.canonical_json import canonical_bytes
from .reference_corpus import PublicBoundaryCase


_HOLDOUT_CASES = (
    PublicBoundaryCase("ru13c_holdout_clean_v1", "v21_holdout_clean", "AUDIT_STATUS", "ru13c-clean", revision=2),
    PublicBoundaryCase("ru13c_holdout_corrupt_v1", "v21_holdout_corrupt", "CORRUPTED_HISTORY_STATUS", "ru13c-corrupt", revision=2),
    PublicBoundaryCase("ru13c_holdout_full_block_v1", "v21_holdout_full_block", "FULL_ASSURANCE_REPORT", "ru13c-blocked", revision=2),
)


def holdout_cases() -> tuple[PublicBoundaryCase, ...]:
    return _HOLDOUT_CASES


def holdout_corpus_digest(cases: tuple[PublicBoundaryCase, ...] | None = None) -> str:
    selected = _HOLDOUT_CASES if cases is None else cases
    body = {
        "corpus_id": "BDB-RU13C-HOLDOUT-CORPUS-1",
        "split": "HOLDOUT",
        "cases": [case.public_body() for case in selected],
    }
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


__all__ = ["holdout_cases", "holdout_corpus_digest"]

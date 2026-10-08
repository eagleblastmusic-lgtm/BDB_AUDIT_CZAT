"""RU13-B frozen public-boundary benchmark corpus without oracle labels."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError


@dataclass(frozen=True)
class PublicBoundaryCase:
    case_id: str
    target_id: str
    boundary: str
    seed: str
    revision: int = 1

    def __post_init__(self) -> None:
        if not self.case_id or not self.target_id or not self.seed:
            raise ValidationError("REFERENCE_CASE_IDENTITY_REQUIRED")
        if self.boundary not in {
            "AUDIT_STATUS",
            "CORRUPTED_HISTORY_STATUS",
            "FULL_ASSURANCE_REPORT",
        }:
            raise ValidationError("REFERENCE_CASE_BOUNDARY_INVALID", self.boundary)
        if type(self.revision) is not int or self.revision < 1:
            raise ValidationError("REFERENCE_CASE_REVISION_INVALID")

    def public_body(self) -> dict[str, Any]:
        """Executor-visible body. It deliberately contains no expected label."""
        return {
            "case_id": self.case_id,
            "target_id": self.target_id,
            "boundary": self.boundary,
            "seed": self.seed,
            "revision": self.revision,
        }

    @property
    def target_sha(self) -> str:
        # Existing BenchmarkManifest calls this field target_sha. For this
        # non-Git qualification target it is the frozen recipe revision digest
        # truncated to the 40-hex identity width accepted by that contract.
        return hashlib.sha256(canonical_bytes(self.public_body())).hexdigest()[:40]


_REFERENCE_CASES = (
    PublicBoundaryCase("ru13b_clean_status_v1", "v21_clean_history", "AUDIT_STATUS", "ru13b-clean"),
    PublicBoundaryCase(
        "ru13b_corrupt_history_v1",
        "v21_corrupt_history",
        "CORRUPTED_HISTORY_STATUS",
        "ru13b-defective",
    ),
    PublicBoundaryCase(
        "ru13b_full_report_blocked_v1",
        "v21_full_report_blocked",
        "FULL_ASSURANCE_REPORT",
        "ru13b-blocked",
    ),
)


def v21_reference_cases() -> tuple[PublicBoundaryCase, ...]:
    return _REFERENCE_CASES


def reference_corpus_digest(cases: tuple[PublicBoundaryCase, ...] | None = None) -> str:
    selected = _REFERENCE_CASES if cases is None else cases
    body = {
        "corpus_id": "BDB-RU13B-V21-REFERENCE-CORPUS-1",
        "cases": [case.public_body() for case in selected],
    }
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


__all__ = ["PublicBoundaryCase", "v21_reference_cases", "reference_corpus_digest"]

"""Production Gap Engine (F4 Domain Expansion / M17 / §§37–38).

Derives Gap Map and Priority Score Records strictly from accepted inventory,
materiality assessments, obligations, coverage qualifications, and evidence.
Guarantees rebuild-equivalence and dynamic reaction to invalidation, new surfaces,
and contradictions.
"""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id, validate_id, deterministic_id
from ..core.registry import canonical_reference_set
from ..history.objects import CanonicalObject, ObjectRef
from .models import (
    CoverageObligation,
    CoverageObligationQualification,
    MaterialityAssessment,
    _ref_dict,
)
from .engine import evaluate_coverage_qualification


@dataclass(frozen=True)
class GapRecord:
    gap_id: str
    target_scope_ref: Any
    missing_or_unsatisfied_obligation_refs: Sequence[Any]
    unknown_scope_refs: Sequence[Any]
    materiality: str
    priority_basis: dict
    current_history_cut: dict
    contradiction_refs: Sequence[Any] = ()

    def __post_init__(self):
        object.__setattr__(
            self,
            "missing_or_unsatisfied_obligation_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.missing_or_unsatisfied_obligation_refs])),
        )
        object.__setattr__(
            self,
            "unknown_scope_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.unknown_scope_refs])),
        )
        object.__setattr__(
            self,
            "contradiction_refs",
            tuple(canonical_reference_set([_ref_dict(r) for r in self.contradiction_refs])),
        )

    def body(self) -> dict:
        return {
            "gap_id": self.gap_id,
            "target_scope_ref": _ref_dict(self.target_scope_ref),
            "missing_or_unsatisfied_obligation_refs": list(self.missing_or_unsatisfied_obligation_refs),
            "unknown_scope_refs": list(self.unknown_scope_refs),
            "materiality": self.materiality,
            "priority_basis": dict(self.priority_basis),
            "current_history_cut": dict(self.current_history_cut),
            "contradiction_refs": list(self.contradiction_refs),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.body())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class GapMap:
    gap_map_id: str
    gaps: Sequence[GapRecord]
    current_history_cut: dict

    def body(self) -> dict:
        return {
            "gap_map_id": self.gap_map_id,
            "gaps": [g.body() for g in sorted(self.gaps, key=lambda x: x.gap_id)],
            "current_history_cut": dict(self.current_history_cut),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.body())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class GapEngine:
    """Computes the normative derived Gap Map from accepted domain facts."""

    @staticmethod
    def _ref_digest(r: Any) -> str:
        if isinstance(r, dict):
            return r.get("revision_digest") or r.get("logical_id") or str(r)
        if hasattr(r, "revision_digest"):
            return r.revision_digest
        if hasattr(r, "digest"):
            return r.digest
        return str(r)

    def compute_gap_map(
        self,
        inventory_surfaces: Sequence[Any],
        obligations: Sequence[CoverageObligation],
        qualifications: Sequence[CoverageObligationQualification],
        materiality_assessments: Sequence[MaterialityAssessment | Mapping[str, Any]] = (),
        scope_states: Sequence[Any] = (),
        contradictions: Sequence[Any] = (),
        invalidated_evidence_digests: Set[str] | None = None,
        history_cut: dict | None = None,
    ) -> GapMap:
        """Derive complete GapMap from accepted domain records."""
        cut = history_cut or {"tag": "EMPTY_HISTORY"}
        invalidated = invalidated_evidence_digests or set()

        # Map qualifications by obligation ref digest
        qual_by_ob: dict[str, CoverageObligationQualification] = {}
        for q in qualifications:
            ob_ref = q.obligation_revision_ref
            ob_d = self._ref_digest(ob_ref)
            qual_by_ob[ob_d] = q

        # Map materiality by subject ref digest
        mat_by_subject: dict[str, str] = {}
        for m in materiality_assessments:
            subj = m.subject_ref if isinstance(m, MaterialityAssessment) else m.get("subject_ref")
            res = m.result if isinstance(m, MaterialityAssessment) else m.get("result")
            mat_by_subject[self._ref_digest(subj)] = res or "MATERIAL"

        # Map contradictions by target scope digest
        contra_by_scope: dict[str, list[Any]] = {}
        for c in contradictions:
            c_scope = c.scope if hasattr(c, "scope") else c.get("scope")
            contra_by_scope.setdefault(self._ref_digest(c_scope), []).append(c)

        # Map obligations by target scope digest
        obs_by_scope: dict[str, list[CoverageObligation]] = {}
        for ob in obligations:
            tgt = ob.target_scope_or_surface_ref
            obs_by_scope.setdefault(self._ref_digest(tgt), []).append(ob)

        gaps: list[GapRecord] = []

        # 1. Evaluate gaps for known surfaces
        for surf in inventory_surfaces:
            surf_d = self._ref_digest(surf)
            surf_obs = obs_by_scope.get(surf_d, [])
            unsatisfied_obs = []

            for ob in surf_obs:
                ob_d = ob.digest
                q = qual_by_ob.get(ob_d)
                if q is None:
                    # Not yet qualified
                    unsatisfied_obs.append(ob.as_object().as_ref())
                else:
                    eval_res = evaluate_coverage_qualification(
                        ob, q, invalidated_evidence_digests=invalidated
                    )
                    if not eval_res["satisfies_completion"]:
                        unsatisfied_obs.append(ob.as_object().as_ref())

            mat = mat_by_subject.get(surf_d, "MATERIAL")
            scope_contras = contra_by_scope.get(surf_d, [])

            # Surface has gap if unsatisfied obligations exist or contradiction exists
            if unsatisfied_obs or scope_contras:
                # Calculate deterministic priority basis (integers only for CJSON)
                base_score = 10 if mat == "MATERIAL" else (5 if mat == "UNKNOWN" else 1)
                ob_penalty = len(unsatisfied_obs) * 2
                contra_penalty = len(scope_contras) * 10
                total_priority = base_score + ob_penalty + contra_penalty

                priority_basis = {
                    "base_materiality_score": base_score,
                    "unsatisfied_obligation_count": len(unsatisfied_obs),
                    "contradiction_count": len(scope_contras),
                    "derived_priority_score": total_priority,
                }

                gap_seed = f"{surf_d}:{canonical_bytes(cut).hex()}".encode("utf-8")
                gap_id = f"gap_{hashlib.sha256(gap_seed).hexdigest()[:16]}"

                gaps.append(
                    GapRecord(
                        gap_id=gap_id,
                        target_scope_ref=_ref_dict(surf),
                        missing_or_unsatisfied_obligation_refs=unsatisfied_obs,
                        unknown_scope_refs=[],
                        materiality=mat,
                        priority_basis=priority_basis,
                        current_history_cut=cut,
                        contradiction_refs=[
                            (c.as_object().as_ref() if hasattr(c, "as_object") else _ref_dict(c))
                            for c in scope_contras
                        ],
                    )
                )

        # 2. Evaluate gaps for failed, unsupported, or unknown scopes
        for s in scope_states:
            state = s.state if hasattr(s, "state") else s.get("state")
            if state in ("UNSUPPORTED_SCOPE", "COLLECTION_FAILED", "PARSING_FAILED", "UNKNOWN_SCOPE", "KNOWN_UNOBSERVED_SCOPE"):
                skey = s.scope_key if hasattr(s, "scope_key") else s.get("scope_key")
                s_ref = s.as_object().as_ref() if hasattr(s, "as_object") else _ref_dict(s)
                scope_contras = contra_by_scope.get(self._ref_digest(s_ref), [])

                unknown_penalty = 15 if state in ("COLLECTION_FAILED", "PARSING_FAILED") else 10
                contra_penalty = len(scope_contras) * 10
                total_priority = 10 + unknown_penalty + contra_penalty

                priority_basis = {
                    "scope_state": state,
                    "unknown_scope_penalty": unknown_penalty,
                    "contradiction_count": len(scope_contras),
                    "derived_priority_score": total_priority,
                }

                gap_seed = f"{skey}:{canonical_bytes(cut).hex()}".encode("utf-8")
                gap_id = f"gap_{hashlib.sha256(gap_seed).hexdigest()[:16]}"

                gaps.append(
                    GapRecord(
                        gap_id=gap_id,
                        target_scope_ref=s_ref,
                        missing_or_unsatisfied_obligation_refs=[],
                        unknown_scope_refs=[s_ref],
                        materiality="UNKNOWN",
                        priority_basis=priority_basis,
                        current_history_cut=cut,
                        contradiction_refs=[
                            (c.as_object().as_ref() if hasattr(c, "as_object") else _ref_dict(c))
                            for c in scope_contras
                        ],
                    )
                )

        # Build GapMap
        map_id = f"gap_map_{hashlib.sha256(canonical_bytes(cut)).hexdigest()[:16]}"
        return GapMap(gap_map_id=map_id, gaps=gaps, current_history_cut=cut)

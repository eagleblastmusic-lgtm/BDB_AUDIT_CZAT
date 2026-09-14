"""Fail-closed semantic bridge from durable external E2 results to R5.3 M21/M22 objects."""
from __future__ import annotations

from dataclasses import replace
import hashlib
from typing import Any, Mapping, Sequence

from ..adjudication import (
    FindingClaimRevision,
    FindingAxisAssessment,
    RootCauseRevision,
    ContradictionRevision,
    adjudicate_finding,
)
from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import deterministic_id
from ..history.objects import CanonicalObject
from ..history.store import TransactionalHistoryStore
from ..orchestration.native_ensemble import E1_LANE_SLOTS, E2CompletionResult, execute_e1_ensemble

_CONVERGENCE_SLOT = "E2-CONVERGENCE"
_ADJUDICATION_SLOT = "E2-ADJUDICATION"
_OPERATIONAL_AXES = ("MECHANISM", "REACHABILITY", "IMPACT")
_ALL_AXES = (*_OPERATIONAL_AXES, "SEVERITY")
_EPISTEMIC = {"SUPPORTED", "REFUTED", "INCONCLUSIVE", "BLOCKED", "NOT_APPLICABLE"}
_SEVERITY = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
_CONFIDENCE = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
_CATEGORIES = {
    "SECURITY", "RELIABILITY", "DATA_INTEGRITY", "AVAILABILITY", "PRIVACY",
    "RELEASE_ASSURANCE", "EVIDENCE_QUALITY", "OTHER",
}
_REF_FIELDS = {"kind", "revision_digest", "digest_profile", "schema_revision_ref", "ref_class"}


def _ref_with_class(ref: Mapping[str, Any], ref_class: str) -> dict[str, Any]:
    result = dict(ref)
    result["ref_class"] = ref_class
    return result


def _external_ref(kind: str, value: str, ref_class: str = "HISTORY_CONTEXT_BINDING") -> dict[str, Any]:
    preimage = f"BDB2/{kind}/1\0".encode("ascii") + canonical_bytes({"reference_id": value})
    return {
        "kind": kind,
        "revision_digest": hashlib.sha256(preimage).hexdigest(),
        "digest_profile": "BDB-OBJECT-DIGEST-1",
        "schema_revision_ref": f"BDB_TARGET/{kind}",
        "ref_class": ref_class,
    }


def _typed_ref(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping) and _REF_FIELDS.issubset(value):
        return dict(value)
    return None


def _typed_refs(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    refs = {_ref_key(ref): ref for item in values if (ref := _typed_ref(item)) is not None}
    return [refs[key] for key in sorted(refs)]


def _ref_key(ref: Mapping[str, Any]) -> bytes:
    return canonical_bytes(dict(ref))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    return sorted({str(item) for item in values if str(item)}, key=lambda item: item.encode("utf-8"))


def _mapping(value: Any, code: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValidationError(code)
    return dict(value)


def _stable_finding_key(lane_slot: str, result_digest: str, index: int) -> str:
    seed = canonical_bytes({"lane_slot": lane_slot, "result_digest": result_digest, "finding_index": index})
    return "e1f_" + hashlib.sha256(seed).hexdigest()[:32]


def _accepted_evidence_refs(
    store: TransactionalHistoryStore,
    cut: Mapping[str, Any],
    values: Any,
) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    for ref in _typed_refs(values):
        if ref.get("kind") != "evidence_qualification_assessment":
            continue
        try:
            record = store.resolve_accepted(ref, dict(cut))
        except ValidationError:
            continue
        accepted.append(_ref_with_class(record["ref"], "PRIOR_ACCEPTED_ONLY"))
    by_key = {_ref_key(ref): ref for ref in accepted}
    return [by_key[key] for key in sorted(by_key)]


def build_e2_predecessor_view(
    store: TransactionalHistoryStore,
    cut: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Freeze exact accepted E1 findings into a deterministic E2 input view."""
    rows = [
        row
        for row in store.accepted_records("bdb_audit_lane_result", dict(cut))
        if row["body"].get("stage_id") == "E1"
    ]
    by_lane: dict[str, list[dict[str, Any]]] = {slot: [] for slot in E1_LANE_SLOTS}
    for row in rows:
        slot = row["body"].get("lane_slot")
        if slot in by_lane:
            by_lane[str(slot)].append(row)
    for slot in E1_LANE_SLOTS:
        if len(by_lane[slot]) != 1:
            raise ValidationError("E2_PREDECESSOR_E1_RESULT_SET_INVALID", f"{slot}:{len(by_lane[slot])}")

    result: list[dict[str, Any]] = []
    for slot in E1_LANE_SLOTS:
        row = by_lane[slot][0]
        findings = row["body"].get("findings")
        if not isinstance(findings, list):
            raise ValidationError("E2_PREDECESSOR_FINDINGS_INVALID", slot)
        for index, finding in enumerate(findings):
            if not isinstance(finding, Mapping):
                raise ValidationError("E2_PREDECESSOR_FINDING_INVALID", f"{slot}:{index}")
            statement = str(finding.get("statement") or "").strip()
            if not statement:
                raise ValidationError("E2_PREDECESSOR_FINDING_STATEMENT_MISSING", f"{slot}:{index}")
            result.append(
                {
                    "finding_key": _stable_finding_key(slot, row["ref"]["revision_digest"], index),
                    "origin_lane_slot": slot,
                    "origin_result_ref": _ref_with_class(row["ref"], "PRIOR_ACCEPTED_ONLY"),
                    "origin_finding_index": index,
                    "finding_id": finding.get("finding_id") or finding.get("title"),
                    "statement": statement,
                    "original_finding": dict(finding),
                    "accepted_evidence_qualification_refs": _accepted_evidence_refs(
                        store, cut, finding.get("evidence_refs")
                    ),
                }
            )
    return tuple(result)


def predecessor_view_json(view: Sequence[Mapping[str, Any]]) -> str:
    return canonical_bytes(list(view)).decode("utf-8")


def _records_by_key(
    slot: str,
    records: Any,
    predecessor_view: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not isinstance(records, list):
        raise ValidationError("E2_RECORDS_REQUIRED", slot)
    expected = {str(row["finding_key"]): row for row in predecessor_view}
    actual: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ValidationError("E2_RECORD_INVALID", f"{slot}:{index}")
        key = str(record.get("finding_key") or "")
        if key not in expected:
            raise ValidationError("E2_RECORD_FOREIGN_FINDING_KEY", f"{slot}:{key}")
        if key in actual:
            raise ValidationError("E2_RECORD_DUPLICATE_FINDING_KEY", f"{slot}:{key}")
        if str(record.get("statement") or "").strip() != expected[key]["statement"]:
            raise ValidationError("E2_RECORD_STATEMENT_DRIFT", f"{slot}:{key}")
        actual[key] = dict(record)
    missing = sorted(set(expected) - set(actual))
    if missing:
        raise ValidationError("E2_RECORD_SET_INCOMPLETE", f"{slot}:{','.join(missing)}")
    return actual


def _validate_ref_list(value: Any, code: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError(code)
    refs = _typed_refs(value)
    if len(refs) != len(value):
        raise ValidationError(code)
    return refs


def validate_e2_lane_records(
    slot: str,
    records: Any,
    predecessor_view: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Validate lane-local semantic output without silently filling omitted fields."""
    indexed = _records_by_key(slot, records, predecessor_view)
    if slot == _CONVERGENCE_SLOT:
        for key, record in indexed.items():
            category = str(record.get("category") or "").upper()
            if category not in _CATEGORIES:
                raise ValidationError("E2_CATEGORY_REQUIRED", key)
            _validate_ref_list(record.get("scope_refs", []), "E2_SCOPE_REFS_INVALID")
            _validate_ref_list(record.get("violated_invariant_refs", []), "E2_INVARIANT_REFS_INVALID")
            _validate_ref_list(record.get("discovery_relation_refs", []), "E2_DISCOVERY_RELATION_REFS_INVALID")
            for field in ("limitations",):
                value = record.get(field, [])
                if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    raise ValidationError("E2_CONVERGENCE_STRING_LIST_INVALID", f"{key}:{field}")
            group = record.get("normalization_group_key")
            if group is not None:
                if not isinstance(group, str) or not group.strip():
                    raise ValidationError("E2_NORMALIZATION_GROUP_KEY_INVALID", key)
                if not str(record.get("root_cause_statement") or "").strip():
                    raise ValidationError("E2_ROOT_CAUSE_STATEMENT_REQUIRED", key)
                _mapping(record.get("root_cause_scope"), "E2_ROOT_CAUSE_SCOPE_INVALID")
                _mapping(record.get("root_cause_membership_scope"), "E2_ROOT_CAUSE_MEMBERSHIP_SCOPE_INVALID")
        return indexed

    if slot == _ADJUDICATION_SLOT:
        for key, record in indexed.items():
            axes = record.get("axes")
            if not isinstance(axes, Mapping) or set(axes) != set(_ALL_AXES):
                raise ValidationError("E2_FOUR_AXES_REQUIRED", key)
            for axis in _OPERATIONAL_AXES:
                assessment = axes.get(axis)
                if not isinstance(assessment, Mapping):
                    raise ValidationError("E2_AXIS_RECORD_INVALID", f"{key}:{axis}")
                outcome = str(assessment.get("epistemic_outcome") or "").upper()
                if outcome not in _EPISTEMIC:
                    raise ValidationError("E2_AXIS_OUTCOME_INVALID", f"{key}:{axis}")
                evidence = _validate_ref_list(
                    assessment.get("evidence_qualification_refs", []), "E2_AXIS_EVIDENCE_REFS_INVALID"
                )
                if outcome in {"SUPPORTED", "REFUTED"} and not evidence:
                    raise ValidationError("E2_AXIS_QUALIFIED_EVIDENCE_REQUIRED", f"{key}:{axis}")
                confidence = str(assessment.get("confidence") or "UNKNOWN").upper()
                if confidence not in _CONFIDENCE:
                    raise ValidationError("E2_AXIS_CONFIDENCE_INVALID", f"{key}:{axis}")
            severity = axes.get("SEVERITY")
            if not isinstance(severity, Mapping):
                raise ValidationError("E2_AXIS_RECORD_INVALID", f"{key}:SEVERITY")
            if str(severity.get("severity_value") or "").upper() not in _SEVERITY:
                raise ValidationError("E2_SEVERITY_VALUE_INVALID", key)
            if "epistemic_outcome" in severity:
                raise ValidationError("SEVERITY_EPISTEMIC_OUTCOME_FORBIDDEN", key)
            confidence = str(severity.get("confidence") or "UNKNOWN").upper()
            if confidence not in _CONFIDENCE:
                raise ValidationError("E2_AXIS_CONFIDENCE_INVALID", f"{key}:SEVERITY")

            position = str(record.get("claim_position") or "INCONCLUSIVE").upper()
            if position not in {"SUPPORTED", "REFUTED", "INCONCLUSIVE"}:
                raise ValidationError("E2_CLAIM_POSITION_INVALID", key)
            claim_evidence = _validate_ref_list(
                record.get("claim_evidence_qualification_refs", []), "E2_CLAIM_EVIDENCE_REFS_INVALID"
            )
            if position in {"SUPPORTED", "REFUTED"} and not claim_evidence:
                raise ValidationError("E2_CLAIM_QUALIFIED_EVIDENCE_REQUIRED", key)
            group = record.get("contradiction_group_key")
            if group is not None and (not isinstance(group, str) or not group.strip()):
                raise ValidationError("E2_CONTRADICTION_GROUP_KEY_INVALID", key)
        return indexed

    raise ValidationError("E2_LANE_SLOT_UNSUPPORTED", slot)


def _resolve_prior_ref(
    store: TransactionalHistoryStore,
    cut: Mapping[str, Any],
    ref: Mapping[str, Any],
    *,
    expected_kind: str | None = None,
    ref_class: str = "CONTENT_OR_PRIOR",
) -> dict[str, Any]:
    """Prove prior acceptance while preserving the owning field's wire ref class."""
    if expected_kind is not None and ref.get("kind") != expected_kind:
        raise ValidationError("E2_REFERENCE_KIND_INVALID", str(ref.get("kind")))
    try:
        row = store.resolve_accepted(dict(ref), dict(cut))
    except ValidationError as exc:
        raise ValidationError(
            "E2_REFERENCE_NOT_ACCEPTED_AT_ASSIGNED_CUT",
            f"{ref.get('kind')}:{ref.get('revision_digest')}",
        ) from exc
    return _ref_with_class(row["ref"], ref_class)


def _prior_refs(
    store: TransactionalHistoryStore,
    cut: Mapping[str, Any],
    value: Any,
    *,
    expected_kind: str | None = None,
    ref_class: str = "CONTENT_OR_PRIOR",
) -> list[dict[str, Any]]:
    refs = _validate_ref_list(value, "E2_REFERENCE_LIST_INVALID")
    resolved = [
        _resolve_prior_ref(store, cut, ref, expected_kind=expected_kind, ref_class=ref_class)
        for ref in refs
    ]
    by_key = {_ref_key(ref): ref for ref in resolved}
    return [by_key[key] for key in sorted(by_key)]


def _axis_from_record(
    store: TransactionalHistoryStore,
    cut: Mapping[str, Any],
    claim: FindingClaimRevision,
    policy_ref: Mapping[str, Any],
    finding_key: str,
    axis: str,
    raw: Mapping[str, Any],
) -> FindingAxisAssessment:
    evidence = _prior_refs(
        store,
        cut,
        raw.get("evidence_qualification_refs", []),
        expected_kind="evidence_qualification_assessment",
    )
    methods = _prior_refs(store, cut, raw.get("method_or_characterization_refs", []))
    common = dict(
        finding_axis_assessment_id=deterministic_id(
            "finding_axis_assessment", canonical_bytes([finding_key, axis, cut, policy_ref])
        ),
        claim_revision_ref=claim.as_object().as_ref().as_dict(),
        assessment_input_history_cut=dict(cut),
        assessment_policy_ref=dict(policy_ref),
        axis=axis,
        scope=_mapping(raw.get("scope"), "E2_AXIS_SCOPE_INVALID"),
        evidence_qualification_refs=evidence,
        method_or_characterization_refs=methods,
        confidence=str(raw.get("confidence") or "UNKNOWN").upper(),
        limitations=_string_list(raw.get("limitations")),
        reason_codes=_string_list(raw.get("reason_codes")),
    )
    if axis == "SEVERITY":
        return FindingAxisAssessment(**common, severity_value=str(raw["severity_value"]).upper())
    return FindingAxisAssessment(**common, epistemic_outcome=str(raw["epistemic_outcome"]).upper())


def _common_mapping(records: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    values = [_mapping(record.get(field), f"E2_{field.upper()}_INVALID") for record in records]
    if not values:
        return {}
    first = canonical_bytes(values[0])
    if any(canonical_bytes(value) != first for value in values[1:]):
        raise ValidationError("E2_GROUP_SCOPE_CONFLICT", field)
    return values[0]


def materialize_e2(
    store: TransactionalHistoryStore,
    *,
    frozen_cut: Mapping[str, Any],
    convergence_records: Any,
    adjudication_records: Any,
) -> E2CompletionResult:
    """Deterministically materialize R5.3 E2 objects from both frozen-view lane results."""
    view = build_e2_predecessor_view(store, frozen_cut)
    convergence = validate_e2_lane_records(_CONVERGENCE_SLOT, convergence_records, view)
    adjudication = validate_e2_lane_records(_ADJUDICATION_SLOT, adjudication_records, view)

    sources = tuple(store.accepted_records("source_generation", dict(frozen_cut)))
    if len(sources) != 1:
        raise ValidationError("E2_SOURCE_GENERATION_AMBIGUOUS", str(len(sources)))
    source_ref = _ref_with_class(sources[0]["ref"], "CONTENT_OR_PRIOR")

    policy_binding_seed = canonical_bytes({
        "stage": "E2",
        "profile": "R5.3_FOUR_AXIS_ASSESSMENT",
        "governing_policy_ref": frozen_cut.get("governing_policy_ref"),
    })
    policy_ref = _external_ref(
        "external_profile_ref",
        "E2_R5_3_FOUR_AXIS_" + hashlib.sha256(policy_binding_seed).hexdigest(),
        "HISTORY_CONTEXT_BINDING",
    )
    adjudicator_ref = _external_ref(
        "actor_or_authority_ref", "BDB_E2_DETERMINISTIC_ADJUDICATOR", "CONTENT_OR_PRIOR"
    )

    claims: list[FindingClaimRevision] = []
    axes: list[FindingAxisAssessment] = []
    decisions = []
    claim_by_key: dict[str, FindingClaimRevision] = {}
    convergence_by_key: dict[str, dict[str, Any]] = {}
    adjudication_by_key: dict[str, dict[str, Any]] = {}

    for predecessor in view:
        key = str(predecessor["finding_key"])
        conv = convergence[key]
        adj = adjudication[key]
        convergence_by_key[key] = conv
        adjudication_by_key[key] = adj
        claim = FindingClaimRevision(
            finding_id=deterministic_id("finding_claim_revision", key.encode("utf-8")),
            finding_claim_revision="1",
            source_generation_ref=source_ref,
            claim_statement=str(predecessor["statement"]),
            scope_refs=_prior_refs(store, frozen_cut, conv.get("scope_refs", [])),
            category=str(conv["category"]).upper(),
            violated_invariant_refs=_prior_refs(
                store, frozen_cut, conv.get("violated_invariant_refs", []), expected_kind="invariant_revision"
            ),
            discovery_relation_refs=_prior_refs(store, frozen_cut, conv.get("discovery_relation_refs", [])),
            limitations=_string_list(conv.get("limitations")),
        )
        axis_map = {
            axis: _axis_from_record(store, frozen_cut, claim, policy_ref, key, axis, adj["axes"][axis])
            for axis in _ALL_AXES
        }
        evidence = []
        for axis in _ALL_AXES:
            evidence.extend(axis_map[axis].evidence_qualification_refs)
        unique_evidence = {_ref_key(ref): ref for ref in evidence}
        decision = adjudicate_finding(
            claim=claim,
            mechanism=axis_map["MECHANISM"],
            reachability=axis_map["REACHABILITY"],
            impact=axis_map["IMPACT"],
            severity=axis_map["SEVERITY"],
            adjudicator_ref=adjudicator_ref,
            input_history_cut=dict(frozen_cut),
            evidence_refs=[unique_evidence[k] for k in sorted(unique_evidence)],
            scope=_mapping(conv.get("finding_scope"), "E2_FINDING_SCOPE_INVALID"),
            reason_codes=_string_list(adj.get("reason_codes")),
        )
        decision = replace(
            decision,
            decision_id=deterministic_id(
                "finding_adjudication_decision",
                canonical_bytes([key, claim.digest, [axis_map[a].digest for a in _ALL_AXES], frozen_cut]),
            ),
        )
        claims.append(claim)
        axes.extend(axis_map[axis] for axis in _ALL_AXES)
        decisions.append(decision)
        claim_by_key[key] = claim

    root_causes: list[RootCauseRevision] = []
    root_groups: dict[str, list[str]] = {}
    for key, record in convergence_by_key.items():
        group = record.get("normalization_group_key")
        if group is not None:
            root_groups.setdefault(str(group), []).append(key)
    for group in sorted(root_groups):
        keys = sorted(root_groups[group])
        records = [convergence_by_key[key] for key in keys]
        statements = {str(record.get("root_cause_statement") or "").strip() for record in records}
        if len(statements) != 1 or not next(iter(statements)):
            raise ValidationError("E2_ROOT_CAUSE_MECHANISM_CONFLICT", group)
        predecessor_refs = []
        for record in records:
            predecessor_refs.extend(
                _prior_refs(
                    store,
                    frozen_cut,
                    record.get("predecessor_root_cause_refs", []),
                    expected_kind="root_cause_revision",
                    ref_class="PRIOR_ACCEPTED_ONLY",
                )
            )
        predecessor_unique = {_ref_key(ref): ref for ref in predecessor_refs}
        edges = [
            {
                "finding_claim_revision_ref": claim_by_key[key].as_object().as_ref().as_dict(),
                "relation_role": str(convergence_by_key[key].get("root_cause_relation_role") or "CONTRIBUTING"),
                "scope": _mapping(
                    convergence_by_key[key].get("root_cause_membership_scope"),
                    "E2_ROOT_CAUSE_MEMBERSHIP_SCOPE_INVALID",
                ),
            }
            for key in keys
        ]
        root_causes.append(
            RootCauseRevision(
                root_cause_id=deterministic_id("root_cause_revision", canonical_bytes([group, keys])),
                root_cause_revision="1",
                source_generation_ref=source_ref,
                mechanism_statement=next(iter(statements)),
                membership_edges=edges,
                predecessor_root_cause_refs=[predecessor_unique[k] for k in sorted(predecessor_unique)],
                multi_causal_condition=records[0].get("multi_causal_condition"),
                scope=_common_mapping(records, "root_cause_scope"),
                status="ACTIVE",
            )
        )

    contradictions: list[ContradictionRevision] = []
    contradiction_groups: dict[str, list[str]] = {}
    for key, record in adjudication_by_key.items():
        group = record.get("contradiction_group_key")
        if group is not None:
            contradiction_groups.setdefault(str(group), []).append(key)
    for group in sorted(contradiction_groups):
        keys = sorted(contradiction_groups[group])
        if len(keys) < 2:
            raise ValidationError("E2_CONTRADICTION_REQUIRES_MULTIPLE_CLAIMS", group)
        records = [adjudication_by_key[key] for key in keys]
        positions = []
        supporting = []
        opposing = []
        for key, record in zip(keys, records):
            position = str(record.get("claim_position") or "INCONCLUSIVE").upper()
            if position not in {"SUPPORTED", "REFUTED"}:
                raise ValidationError("E2_CONTRADICTION_POSITION_MUST_BE_OPPOSING", f"{group}:{key}")
            evidence = _prior_refs(
                store,
                frozen_cut,
                record.get("claim_evidence_qualification_refs", []),
                expected_kind="evidence_qualification_assessment",
            )
            if not evidence:
                raise ValidationError("E2_CONTRADICTION_QUALIFIED_EVIDENCE_REQUIRED", f"{group}:{key}")
            positions.append(
                {
                    "claim_revision_ref": claim_by_key[key].as_object().as_ref().as_dict(),
                    "position": position,
                }
            )
            (supporting if position == "SUPPORTED" else opposing).extend(evidence)
        if not supporting or not opposing:
            raise ValidationError("E2_CONTRADICTION_REQUIRES_OPPOSING_POSITIONS", group)
        required_values = [record.get("required_falsifier") for record in records]
        if any(value is None for value in required_values):
            raise ValidationError("E2_CONTRADICTION_FALSIFIER_REQUIRED", group)
        first_falsifier = canonical_bytes(required_values[0])
        if any(canonical_bytes(value) != first_falsifier for value in required_values[1:]):
            raise ValidationError("E2_CONTRADICTION_FALSIFIER_CONFLICT", group)
        failure_diffs = [item for record in records for item in (record.get("failure_assumption_differences") or [])]
        environment_diffs = [item for record in records for item in (record.get("environment_input_model_differences") or [])]
        supporting_unique = {_ref_key(ref): ref for ref in supporting}
        opposing_unique = {_ref_key(ref): ref for ref in opposing}
        contradictions.append(
            ContradictionRevision(
                contradiction_id=deterministic_id("contradiction_revision", canonical_bytes([group, keys])),
                contradiction_revision="1",
                claim_revision_refs=[claim_by_key[key].as_object().as_ref().as_dict() for key in keys],
                scope=_common_mapping(records, "contradiction_scope"),
                positions=positions,
                supporting_evidence_qualification_refs=[supporting_unique[k] for k in sorted(supporting_unique)],
                opposing_evidence_qualification_refs=[opposing_unique[k] for k in sorted(opposing_unique)],
                failure_assumption_differences=failure_diffs,
                environment_input_model_differences=environment_diffs,
                required_falsifier=required_values[0],
                status="OPEN",
            )
        )

    lane_discoveries: dict[str, list[dict[str, Any]]] = {slot: [] for slot in E1_LANE_SLOTS}
    for row in view:
        lane_discoveries[str(row["origin_lane_slot"])].append(dict(row["original_finding"]))
    e1_result = execute_e1_ensemble(source_ref, lane_discoveries)
    body = {
        "stage_key": "E2",
        "e1_completion_digest": e1_result.completion_digest,
        "finding_claim_revision_digests": sorted(claim.digest for claim in claims),
        "axis_assessment_digests": sorted(axis.digest for axis in axes),
        "adjudication_decision_digests": sorted(decision.digest for decision in decisions),
        "root_cause_revision_digests": sorted(root.digest for root in root_causes),
        "contradiction_digests": sorted(contradiction.digest for contradiction in contradictions),
    }
    completion_digest = hashlib.sha256(canonical_bytes(body)).hexdigest()
    return E2CompletionResult(
        stage_key="E2",
        e1_completion_digest=e1_result.completion_digest,
        finding_claim_revisions=tuple(claims),
        axis_assessments=tuple(axes),
        adjudicated_decisions=tuple(decisions),
        root_cause_revisions=tuple(root_causes),
        contradiction_revisions=tuple(contradictions),
        completion_digest=completion_digest,
    )


def semantic_objects(result: E2CompletionResult) -> list[CanonicalObject]:
    return [
        *[claim.as_object() for claim in result.finding_claim_revisions],
        *[assessment.as_object() for assessment in result.axis_assessments],
        *[decision.as_object() for decision in result.adjudicated_decisions],
        *[root.as_object() for root in result.root_cause_revisions],
        *[contradiction.as_object() for contradiction in result.contradiction_revisions],
    ]


__all__ = [
    "build_e2_predecessor_view",
    "predecessor_view_json",
    "validate_e2_lane_records",
    "materialize_e2",
    "semantic_objects",
]

"""Immutable LaneSpec and Attempt creation revisions (M7)."""
from dataclasses import dataclass, field
from typing import Mapping

from ..core.errors import ValidationError
from ..history.objects import CanonicalObject, ObjectRef


_ISOLATION = {"ENFORCED", "DECLARED", "UNKNOWN"}


@dataclass(frozen=True)
class LaneSpec:
    lane_key: str
    lane_spec_revision: str
    stage_spec_revision: str
    purpose: str
    primary_strategy: str
    scope_selectors: tuple[str, ...] = ()
    exploration_policy_ref: str = ""
    allowed_view_classes: tuple[str, ...] = ()
    forbidden_knowledge_classes: tuple[str, ...] = ()
    required_isolation_assurance: str = "UNKNOWN"
    required_outputs: tuple[str, ...] = ()
    executor_capability_requirements: tuple[str, ...] = ()
    budget_effort_profile_ref: str = ""
    completion_predicate_ref: str = ""

    def __post_init__(self):
        if not self.lane_key or not self.lane_spec_revision or not self.stage_spec_revision:
            raise ValidationError("LANE_SPEC_CONTEXT_REQUIRED")
        if self.required_isolation_assurance not in _ISOLATION:
            raise ValidationError("ISOLATION_CLASS_INVALID")
        for name in ("scope_selectors", "allowed_view_classes", "forbidden_knowledge_classes",
                     "required_outputs", "executor_capability_requirements"):
            values = getattr(self, name)
            if type(values) not in (tuple, list) or len(set(values)) != len(values):
                raise ValidationError("LANE_SPEC_DUPLICATE", name)
            object.__setattr__(self, name, tuple(values))

    def body(self):
        return {"lane_key": self.lane_key, "lane_spec_revision": self.lane_spec_revision,
                "stage_spec_revision": self.stage_spec_revision, "purpose": self.purpose,
                "primary_strategy": self.primary_strategy, "scope_selectors": list(self.scope_selectors),
                "exploration_policy_ref": self.exploration_policy_ref,
                "allowed_view_classes": list(self.allowed_view_classes),
                "forbidden_knowledge_classes": list(self.forbidden_knowledge_classes),
                "required_isolation_assurance": self.required_isolation_assurance,
                "required_outputs": list(self.required_outputs),
                "executor_capability_requirements": list(self.executor_capability_requirements),
                "budget_effort_profile_ref": self.budget_effort_profile_ref,
                "completion_predicate_ref": self.completion_predicate_ref}

    def as_object(self):
        return CanonicalObject("lane_spec", self.body())

    @property
    def revision_digest(self):
        return self.as_object().digest


@dataclass(frozen=True)
class Attempt:
    attempt_id: str
    lane_run_ref: Mapping
    attempt_nonce: str
    executor_profile_ref: Mapping
    delivery_profile_ref: Mapping
    assigned_history_cut: Mapping
    retry_of_attempt_ref: Mapping | None = None
    retry_reason_ref: Mapping | None = None
    result_slot_contracts: tuple[Mapping, ...] = ()

    def __post_init__(self):
        if not self.attempt_id or not self.attempt_nonce:
            raise ValidationError("ATTEMPT_ID_REQUIRED")
        for name in ("lane_run_ref", "executor_profile_ref", "delivery_profile_ref", "assigned_history_cut"):
            if not isinstance(getattr(self, name), Mapping):
                raise ValidationError("ATTEMPT_BINDING_REQUIRED", name)
        if self.retry_of_attempt_ref is not None and (
                self.retry_of_attempt_ref.get("revision_digest") == self.revision_digest
                if hasattr(self, "revision_digest") else False):
            raise ValidationError("RETRY_REUSES_ATTEMPT")
        object.__setattr__(self, "result_slot_contracts", tuple(self.result_slot_contracts))

    def body(self):
        out = {"attempt_id": self.attempt_id, "lane_run_ref": dict(self.lane_run_ref),
               "attempt_nonce": self.attempt_nonce, "executor_profile_ref": dict(self.executor_profile_ref),
               "delivery_profile_ref": dict(self.delivery_profile_ref),
               "assigned_history_cut": dict(self.assigned_history_cut),
               "result_slot_contracts": [dict(v) for v in self.result_slot_contracts]}
        if self.retry_of_attempt_ref is not None:
            out["retry_of_attempt_ref"] = dict(self.retry_of_attempt_ref)
        if self.retry_reason_ref is not None:
            out["retry_reason_ref"] = dict(self.retry_reason_ref)
        return out

    def as_object(self):
        return CanonicalObject("attempt", self.body())

    @property
    def revision_digest(self):
        return self.as_object().digest


@dataclass(frozen=True)
class IsolationQualification:
    attempt_ref: Mapping
    assessment_input_history_cut: Mapping
    executor_profile_ref: Mapping
    delivery_profile_ref: Mapping
    isolation_class: str
    contaminated: bool = False
    fresh_session_boundary: bool = False
    forbidden_channel_access: bool = False
    evidence_refs: tuple[Mapping, ...] = ()
    channel_inventory_ref: Mapping | None = None
    enforcement_receipt_refs: tuple[Mapping, ...] = ()
    filesystem_boundary_evidence_refs: tuple[Mapping, ...] = ()
    network_boundary_evidence_refs: tuple[Mapping, ...] = ()
    tool_boundary_evidence_refs: tuple[Mapping, ...] = ()
    session_boundary_evidence_refs: tuple[Mapping, ...] = ()
    contamination_assessment_refs: tuple[Mapping, ...] = ()
    isolation_qualification_id: str = ""
    required_isolation_assurance: str = "UNKNOWN"
    scope: str = ""
    limitations: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self):
        if self.isolation_class not in _ISOLATION:
            raise ValidationError("ISOLATION_CLASS_INVALID")
        if self.required_isolation_assurance not in _ISOLATION:
            raise ValidationError("ISOLATION_CLASS_INVALID")
        if not isinstance(self.channel_inventory_ref, Mapping):
            raise ValidationError("ISOLATION_CHANNEL_INVENTORY_REQUIRED")

        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        witness_fields = (
            "enforcement_receipt_refs",
            "filesystem_boundary_evidence_refs",
            "network_boundary_evidence_refs",
            "tool_boundary_evidence_refs",
            "session_boundary_evidence_refs",
        )
        for name in (*witness_fields, "contamination_assessment_refs"):
            object.__setattr__(self, name, tuple(getattr(self, name)))

        if self.isolation_class == "ENFORCED":
            missing_witnesses = [
                name for name in witness_fields if not getattr(self, name)
            ]
            if (
                not self.fresh_session_boundary
                or self.forbidden_channel_access
                or self.contaminated
                or missing_witnesses
            ):
                raise ValidationError(
                    "NO_FALSE_ENFORCED_FALLBACK",
                    (
                        "ENFORCED isolation requires a fresh uncontaminated "
                        "boundary and witnesses for every explicit material "
                        f"channel group; missing={missing_witnesses}"
                    ),
                )

    def body(self):
        return {"attempt_ref": dict(self.attempt_ref), "assessment_input_history_cut": dict(self.assessment_input_history_cut),
                "executor_profile_ref": dict(self.executor_profile_ref), "delivery_profile_ref": dict(self.delivery_profile_ref),
                "isolation_qualification_id": self.isolation_qualification_id,
                "result": self.isolation_class,
                "required_isolation_assurance": self.required_isolation_assurance,
                "scope": self.scope, "limitations": list(self.limitations),
                "reason_codes": list(self.reason_codes),
                "channel_inventory_ref": dict(self.channel_inventory_ref) if self.channel_inventory_ref else None,
                "enforcement_receipt_refs": [dict(v) for v in self.enforcement_receipt_refs],
                "filesystem_boundary_evidence_refs": [dict(v) for v in self.filesystem_boundary_evidence_refs],
                "network_boundary_evidence_refs": [dict(v) for v in self.network_boundary_evidence_refs],
                "tool_boundary_evidence_refs": [dict(v) for v in self.tool_boundary_evidence_refs],
                "session_boundary_evidence_refs": [dict(v) for v in self.session_boundary_evidence_refs],
                "contamination_assessment_refs": [dict(v) for v in self.contamination_assessment_refs]}

    def as_object(self):
        return CanonicalObject("isolation_qualification", self.body())


def qualify_isolation(
    *,
    attempt_ref,
    history_cut,
    executor_profile_ref,
    delivery_profile_ref,
    fresh_session_boundary=False,
    forbidden_channel_access=False,
    contaminated=False,
    requested="DECLARED",
    evidence_refs=(),
    channel_inventory_ref=None,
    enforcement_receipt_refs=(),
    filesystem_boundary_evidence_refs=(),
    network_boundary_evidence_refs=(),
    tool_boundary_evidence_refs=(),
    session_boundary_evidence_refs=(),
    contamination_assessment_refs=(),
):
    """Return a truthful isolation qualification without false ENFORCED fallback."""
    if requested not in _ISOLATION:
        raise ValidationError("ISOLATION_CLASS_INVALID")
    if not isinstance(channel_inventory_ref, Mapping):
        raise ValidationError("ISOLATION_CHANNEL_INVENTORY_REQUIRED")

    witnesses = (
        tuple(enforcement_receipt_refs),
        tuple(filesystem_boundary_evidence_refs),
        tuple(network_boundary_evidence_refs),
        tuple(tool_boundary_evidence_refs),
        tuple(session_boundary_evidence_refs),
    )

    actual = requested
    limitations: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    if forbidden_channel_access:
        actual = "UNKNOWN"
        limitations = ("Known forbidden-channel access prevents isolation assurance",)
        reason_codes = ("FORBIDDEN_CHANNEL_ACCESS",)
    elif contaminated:
        actual = "UNKNOWN"
        limitations = ("Known contamination prevents isolation assurance",)
        reason_codes = ("CONTAMINATED_EXECUTION_CONTEXT",)
    elif requested == "ENFORCED":
        if not fresh_session_boundary:
            actual = "UNKNOWN"
            limitations = ("Fresh isolated session boundary is not established",)
            reason_codes = ("FRESH_SESSION_BOUNDARY_NOT_ESTABLISHED",)
        elif not all(witnesses):
            actual = "DECLARED"
            limitations = (
                "Isolation is declared but complete enforcement witnesses are unavailable",
            )
            reason_codes = ("ENFORCEMENT_WITNESSES_INCOMPLETE",)
    elif requested == "DECLARED":
        limitations = ("Isolation is declared; enforcement is not proven",)
        reason_codes = ("DECLARED_ISOLATION_ONLY",)

    return IsolationQualification(
        attempt_ref=attempt_ref,
        assessment_input_history_cut=history_cut,
        executor_profile_ref=executor_profile_ref,
        delivery_profile_ref=delivery_profile_ref,
        isolation_class=actual,
        contaminated=contaminated,
        fresh_session_boundary=fresh_session_boundary,
        forbidden_channel_access=forbidden_channel_access,
        evidence_refs=tuple(evidence_refs),
        channel_inventory_ref=channel_inventory_ref,
        enforcement_receipt_refs=witnesses[0],
        filesystem_boundary_evidence_refs=witnesses[1],
        network_boundary_evidence_refs=witnesses[2],
        tool_boundary_evidence_refs=witnesses[3],
        session_boundary_evidence_refs=witnesses[4],
        contamination_assessment_refs=tuple(contamination_assessment_refs),
        required_isolation_assurance=requested,
        limitations=limitations,
        reason_codes=reason_codes,
    )


__all__ = ["LaneSpec", "Attempt", "IsolationQualification", "qualify_isolation"]

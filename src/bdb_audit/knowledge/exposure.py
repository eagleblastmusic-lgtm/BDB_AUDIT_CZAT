"""M12 accepted fact helpers.

The ledger here is a deterministic projection helper.  It does not write an
accepted head; callers must submit the returned immutable objects through the
Coordinator/history adapter.
"""
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..history.objects import CanonicalObject


def _dict(value):
    if not isinstance(value, Mapping):
        raise ValidationError("TYPED_REF_REQUIRED")
    return dict(value)


def _head_seq(cut):
    if not isinstance(cut, Mapping):
        raise ValidationError("HISTORY_CUT_REQUIRED")
    if cut.get("variant") == "EMPTY_HISTORY_CUT":
        return 0
    if cut.get("variant") == "ACCEPTED_HISTORY_CUT" and type(cut.get("accepted_head_seq")) is int:
        return cut["accepted_head_seq"]
    raise ValidationError("HISTORY_CUT_INVALID")


@dataclass(frozen=True)
class GrantAccepted:
    attempt_ref: Mapping
    grant_input_history_cut: Mapping
    view_manifest_ref: Mapping
    delivery_profile_ref: Mapping
    forbidden_knowledge_policy_ref: str
    channel_class: str
    previous_knowledge_state_ref: Mapping | None = None
    capability_profile_ref: Mapping | None = None

    def body(self):
        out = {"attempt_ref": _dict(self.attempt_ref), "grant_input_history_cut": _dict(self.grant_input_history_cut),
               "view_manifest_ref": _dict(self.view_manifest_ref), "delivery_profile_ref": _dict(self.delivery_profile_ref),
               "forbidden_knowledge_policy_ref": self.forbidden_knowledge_policy_ref,
               "channel_class": self.channel_class}
        if self.previous_knowledge_state_ref is not None:
            out["previous_knowledge_state_ref"] = _dict(self.previous_knowledge_state_ref)
        if self.capability_profile_ref is not None:
            out["capability_profile_ref"] = _dict(self.capability_profile_ref)
        return out

    def as_object(self):
        return CanonicalObject("grant_body", self.body())

    @property
    def revision_digest(self):
        return self.as_object().digest


@dataclass(frozen=True)
class PotentialExposureRecord:
    attempt_ref: Mapping
    grant_ref: Mapping
    view_manifest_ref: Mapping
    exposure_input_history_cut: Mapping
    previous_knowledge_state_ref: Mapping | None = None

    def __post_init__(self):
        for name in ("attempt_ref", "grant_ref", "view_manifest_ref", "exposure_input_history_cut"):
            _dict(getattr(self, name))

    def body(self):
        out = {"attempt_ref": _dict(self.attempt_ref), "grant_ref": _dict(self.grant_ref),
               "view_manifest_ref": _dict(self.view_manifest_ref),
               "exposure_input_history_cut": _dict(self.exposure_input_history_cut)}
        if self.previous_knowledge_state_ref is not None:
            out["previous_knowledge_state_ref"] = _dict(self.previous_knowledge_state_ref)
        return out

    def as_object(self):
        return CanonicalObject("potential_exposure_record", self.body())


@dataclass(frozen=True)
class ContaminationAssessment:
    attempt_ref: Mapping
    assessment_input_history_cut: Mapping
    forbidden_knowledge_policy_ref: str
    channel_inventory_ref: Mapping
    potential_exposure_refs: tuple[Mapping, ...] = ()
    forbidden_knowledge_match_refs: tuple[Mapping, ...] = ()
    observation_or_channel_evidence_refs: tuple[Mapping, ...] = ()
    contaminated: bool = True

    def body(self):
        return {"attempt_ref": _dict(self.attempt_ref), "assessment_input_history_cut": _dict(self.assessment_input_history_cut),
                "forbidden_knowledge_policy_ref": self.forbidden_knowledge_policy_ref,
                "channel_inventory_ref": _dict(self.channel_inventory_ref),
                "potential_exposure_refs": [dict(v) for v in self.potential_exposure_refs],
                "forbidden_knowledge_match_refs": [dict(v) for v in self.forbidden_knowledge_match_refs],
                "observation_or_channel_evidence_refs": [dict(v) for v in self.observation_or_channel_evidence_refs],
                "contaminated": self.contaminated}

    def as_object(self):
        return CanonicalObject("contamination_assessment", self.body())


@dataclass(frozen=True)
class KnowledgeState:
    attempt_ref: Mapping
    basis_history_cut: Mapping
    isolation_qualification_ref: Mapping
    allowed_view_refs: tuple[Mapping, ...] = ()
    potential_exposure_refs: tuple[Mapping, ...] = ()
    contamination_assessment_refs: tuple[Mapping, ...] = ()
    previous_knowledge_state_ref: Mapping | None = None
    known_classes: tuple[str, ...] = ()

    def __post_init__(self):
        _dict(self.attempt_ref); _dict(self.basis_history_cut); _dict(self.isolation_qualification_ref)
        for name in ("allowed_view_refs", "potential_exposure_refs", "contamination_assessment_refs"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "known_classes", tuple(sorted(set(self.known_classes))))

    def body(self):
        out = {"attempt_ref": _dict(self.attempt_ref), "basis_history_cut": _dict(self.basis_history_cut),
               "isolation_qualification_ref": _dict(self.isolation_qualification_ref),
               "allowed_view_refs": [dict(v) for v in self.allowed_view_refs],
               "potential_exposure_refs": [dict(v) for v in self.potential_exposure_refs],
               "contamination_assessment_refs": [dict(v) for v in self.contamination_assessment_refs],
               "known_classes": list(self.known_classes)}
        if self.previous_knowledge_state_ref is not None:
            out["previous_knowledge_state_ref"] = _dict(self.previous_knowledge_state_ref)
        return out

    def as_object(self):
        return CanonicalObject("knowledge_state", self.body())

    @property
    def revision_digest(self):
        return self.as_object().digest


@dataclass(frozen=True)
class DiscoveryRecord:
    lane_run_ref: Mapping
    attempt_ref: Mapping
    source_generation_ref: Mapping
    discovery_input_history_cut: Mapping
    knowledge_state_ref: Mapping
    method_ref: Mapping
    producer_ref: Mapping
    own_observation_refs: tuple[Mapping, ...] = ()
    surface_location_refs: tuple[Mapping, ...] = ()
    pre_reveal_checkpoint_ref: Mapping | None = None
    classification: str = "PRE_REVEAL_DISCOVERY"
    accepted_precursor: bool = False
    isolation_class: str = "UNKNOWN"
    contaminated: bool = False
    report_assisted: bool = False

    def __post_init__(self):
        for name in ("lane_run_ref", "attempt_ref", "source_generation_ref", "discovery_input_history_cut",
                     "knowledge_state_ref", "method_ref", "producer_ref"):
            _dict(getattr(self, name))
        if self.classification not in {"PRE_REVEAL_DISCOVERY", "POST_REVEAL_CONFIRMATION",
                                       "REPORT_ASSISTED_VERIFICATION", "CONTAMINATED_DISCOVERY",
                                       "UNKNOWN_ISOLATION_DISCOVERY"}:
            raise ValidationError("DISCOVERY_CLASS_INVALID")
        # Construction is a proposal only. Caller annotations carry no
        # accepted provenance; eligibility resolves canonical history below.
        object.__setattr__(self, "own_observation_refs", tuple(self.own_observation_refs))
        object.__setattr__(self, "surface_location_refs", tuple(self.surface_location_refs))

    def body(self):
        out = {"lane_run_ref": _dict(self.lane_run_ref), "attempt_ref": _dict(self.attempt_ref),
               "source_generation_ref": _dict(self.source_generation_ref),
               "discovery_input_history_cut": _dict(self.discovery_input_history_cut),
               "knowledge_state_ref": _dict(self.knowledge_state_ref), "method_ref": _dict(self.method_ref),
               "producer_ref": _dict(self.producer_ref),
               "surface_location_refs": [dict(v) for v in self.surface_location_refs],
               "own_observation_refs": [dict(v) for v in self.own_observation_refs]}
        if self.pre_reveal_checkpoint_ref is not None:
            out["pre_reveal_checkpoint_ref"] = _dict(self.pre_reveal_checkpoint_ref)
        return out

    def as_object(self):
        return CanonicalObject("discovery_record", self.body())


class ExposureLedger:
    """Monotonic accepted-fact projection keyed by exact attempt ref."""
    def __init__(self, *, history=None):
        self._history = history
        self._grants = {}
        self._exposures = {}
        self._knowledge = {}

    def accept_grant(self, grant: GrantAccepted, *, history_cut=None):
        if self._history is None or history_cut is None:
            raise ValidationError("GRANT_NOT_ACCEPTED")
        self._history.resolve_accepted(grant.as_object().ref, history_cut, require_current=True)
        return grant.as_object().ref

    def record_potential_exposure(self, exposure: PotentialExposureRecord, *, history_cut=None):
        if self._history is None or history_cut is None:
            raise ValidationError("GRANT_NOT_ACCEPTED")
        grant = self._history.resolve_accepted(exposure.grant_ref, history_cut, require_current=True)
        self._history.resolve_accepted(exposure.as_object().ref, history_cut)
        if grant["ref"]["kind"] != "grant_body" or grant["body"]["attempt_ref"] != exposure.attempt_ref or grant["body"]["view_manifest_ref"] != exposure.view_manifest_ref:
            raise ValidationError("EXPOSURE_GRANT_BINDING_MISMATCH")
        attempt = exposure.attempt_ref.get("revision_digest")
        self._exposures.setdefault(attempt, set()).add(exposure.as_object().digest)
        return exposure.as_object().ref

    def exposures_for(self, attempt_ref, *, history_cut=None):
        if self._history is None or history_cut is None:
            raise ValidationError("ACCEPTED_HISTORY_CUT_REQUIRED")
        return frozenset(record["ref"]["revision_digest"]
                         for kind in ("grant_body", "potential_exposure_record")
                         for record in self._history.accepted_records(kind, history_cut)
                         if record["body"]["attempt_ref"] == attempt_ref)

    def advance(self, state: KnowledgeState, *, history_cut=None):
        if self._history is None or history_cut is None:
            raise ValidationError("ACCEPTED_HISTORY_CUT_REQUIRED")
        accepted = self._history.resolve_accepted(state.as_object().ref, history_cut, require_current=True)
        key = state.attempt_ref.get("revision_digest")
        if state.previous_knowledge_state_ref is not None:
            previous = self._history.resolve_accepted(state.previous_knowledge_state_ref, state.basis_history_cut)
            if previous["accepted_seq"] >= accepted["accepted_seq"] or previous["body"]["attempt_ref"] != state.attempt_ref:
                raise ValidationError("KNOWLEDGE_PREDECESSOR_NOT_PRIOR")
            before = {r.get("revision_digest") for r in previous["body"]["potential_exposure_refs"]}
            after = {r.get("revision_digest") for r in state.potential_exposure_refs}
            if not before <= after:
                raise ValidationError("KNOWLEDGE_EXPOSURE_NOT_MONOTONIC")
        self._knowledge[key] = state
        return state.as_object().ref


def advance_knowledge_state(*, attempt_ref, basis_history_cut, isolation_qualification_ref,
                            potential_exposure_refs=(), previous_knowledge_state_ref=None,
                            allowed_view_refs=(), contamination_assessment_refs=(), known_classes=(),
                            ledger=None):
    state = KnowledgeState(attempt_ref, basis_history_cut, isolation_qualification_ref,
                           tuple(allowed_view_refs), tuple(potential_exposure_refs),
                           tuple(contamination_assessment_refs), previous_knowledge_state_ref,
                           tuple(known_classes))
    if ledger is not None:
        ledger.advance(state)
    return state


def classify_discovery(*, pre_reveal, isolation_class, contaminated=False,
                       report_assisted=False, accepted_precursor=False):
    if contaminated:
        return "CONTAMINATED_DISCOVERY"
    if report_assisted:
        return "REPORT_ASSISTED_VERIFICATION"
    if not pre_reveal:
        return "POST_REVEAL_CONFIRMATION"
    if isolation_class != "ENFORCED":
        return "UNKNOWN_ISOLATION_DISCOVERY"
    if not accepted_precursor:
        raise ValidationError("BLIND_ORIGIN_REQUIRES_ACCEPTED_PRECURSOR")
    return "PRE_REVEAL_DISCOVERY"


def blind_origin_eligible(discovery: DiscoveryRecord, *, accepting_head_seq=None,
                          history=None, history_cut=None):
    if not isinstance(discovery, DiscoveryRecord):
        raise ValidationError("DISCOVERY_REQUIRED")
    if history is None or history_cut is None:
        raise ValidationError("BLIND_ORIGIN_REQUIRES_ACCEPTED_PRECURSOR")
    accepted = history.resolve_accepted(discovery.as_object().ref, history_cut, require_current=True)
    if accepted["accepted_seq"] >= history_cut["accepted_head_seq"]:
        raise ValidationError("BLIND_ORIGIN_REQUIRES_EARLIER_CUT")
    knowledge = history.resolve_accepted(discovery.knowledge_state_ref, discovery.discovery_input_history_cut)
    if knowledge["body"]["attempt_ref"] != discovery.attempt_ref:
        raise ValidationError("DISCOVERY_ATTEMPT_BINDING_MISMATCH")
    isolation = history.resolve_accepted(knowledge["body"]["isolation_qualification_ref"], discovery.discovery_input_history_cut)
    body = isolation["body"]
    if body.get("attempt_ref") != discovery.attempt_ref or body.get("result") != "ENFORCED":
        raise ValidationError("BLIND_ORIGIN_ISOLATION_NOT_QUALIFIED")
    # A label and fresh-session boolean do not constitute channel evidence.
    required = ("enforcement_receipt_refs", "filesystem_boundary_evidence_refs",
                "network_boundary_evidence_refs", "tool_boundary_evidence_refs", "session_boundary_evidence_refs")
    for field in required:
        if not body.get(field):
            raise ValidationError("BLIND_ORIGIN_ISOLATION_NOT_QUALIFIED")
        for ref in body[field]:
            history.resolve_accepted(ref, discovery.discovery_input_history_cut)
    if knowledge["body"].get("contamination_assessment_refs") or knowledge["body"].get("potential_exposure_refs"):
        raise ValidationError("BLIND_ORIGIN_EXPOSURE_NOT_QUALIFIED")
    events = [event for commit in history.commits()
              if commit["commit_seq"] == accepted["accepted_seq"]
              for event in commit["ordered_event_bodies"]]
    if not any(event.get("event_type") == "DiscoveryRecorded" and
               event.get("discovery_record_ref", {}).get("revision_digest") == discovery.as_object().digest
               for event in events):
        raise ValidationError("DISCOVERY_ACCEPTED_EVENT_REQUIRED")
    for record in history.accepted_records("grant_body", history_cut):
        if record["body"].get("attempt_ref") == discovery.attempt_ref and record["accepted_seq"] <= accepted["accepted_seq"]:
            # Until the pinned relevance policy proves a grant harmless, it
            # cannot be excluded from the pre-reveal provenance boundary.
            raise ValidationError("BLIND_ORIGIN_REVEAL_ORDER_NOT_QUALIFIED")
    return True


__all__ = ["GrantAccepted", "PotentialExposureRecord", "ContaminationAssessment", "KnowledgeState",
           "DiscoveryRecord", "ExposureLedger", "advance_knowledge_state", "classify_discovery",
           "blind_origin_eligible"]

"""Immutable StageSpec revisions and exact-digest resolution (M6)."""
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.hashing import object_digest
from ..history.objects import CanonicalObject


_STAGES = {"E1", "E2", "E3", "E4", "E5", "E6"}
_REVEAL_PHASES = {"NEVER", "CONTROLLED", "AFTER_CHECKPOINT", "ALWAYS"}


@dataclass(frozen=True)
class StageSpec:
    stage_key: str
    stage_spec_revision: str
    stage_role: str
    stage_ordinal: int
    purpose: str
    predecessor_requirements: tuple[str, ...] = ()
    required_lane_slots: tuple[str, ...] = ()
    optional_lane_slots: tuple[str, ...] = ()
    blind_reveal_phase_model: str = "CONTROLLED"
    allowed_corpus_roles: tuple[str, ...] = ()
    forbidden_corpus_roles: tuple[str, ...] = ()
    coverage_obligation_policy_ref: str = ""
    required_stage_completion_outputs: tuple[str, ...] = ()
    transition_policy_ref: str = ""
    stop_e6_relationship: str = "NONE"

    def __post_init__(self):
        if self.stage_key not in _STAGES:
            raise ValidationError("UNKNOWN_STAGE_KEY")
        if type(self.stage_ordinal) is not int or self.stage_ordinal < 1:
            raise ValidationError("STAGE_ORDINAL_INVALID")
        if not self.stage_spec_revision or not self.purpose:
            raise ValidationError("STAGE_SPEC_CONTEXT_REQUIRED")
        if self.blind_reveal_phase_model not in _REVEAL_PHASES:
            raise ValidationError("INVALID_REVEAL_PHASE")
        for seq_name, values in (("predecessor_requirements", self.predecessor_requirements),
                                 ("required_lane_slots", self.required_lane_slots),
                                 ("optional_lane_slots", self.optional_lane_slots),
                                 ("allowed_corpus_roles", self.allowed_corpus_roles),
                                 ("forbidden_corpus_roles", self.forbidden_corpus_roles),
                                 ("required_stage_completion_outputs", self.required_stage_completion_outputs)):
            if type(values) not in (tuple, list) or len(set(values)) != len(values):
                raise ValidationError("STAGE_SPEC_DUPLICATE", seq_name)
            object.__setattr__(self, seq_name, tuple(values))
        if set(self.required_lane_slots) & set(self.optional_lane_slots):
            raise ValidationError("STAGE_SLOT_DUPLICATE")

    def body(self):
        return {"stage_key": self.stage_key, "stage_spec_revision": self.stage_spec_revision,
                "stage_role": self.stage_role, "stage_ordinal": self.stage_ordinal,
                "purpose": self.purpose, "predecessor_requirements": list(self.predecessor_requirements),
                "required_lane_slots": list(self.required_lane_slots), "optional_lane_slots": list(self.optional_lane_slots),
                "blind_reveal_phase_model": self.blind_reveal_phase_model,
                "allowed_corpus_roles": list(self.allowed_corpus_roles),
                "forbidden_corpus_roles": list(self.forbidden_corpus_roles),
                "coverage_obligation_policy_ref": self.coverage_obligation_policy_ref,
                "required_stage_completion_outputs": list(self.required_stage_completion_outputs),
                "transition_policy_ref": self.transition_policy_ref,
                "stop_e6_relationship": self.stop_e6_relationship}

    def as_object(self):
        return CanonicalObject("stage_spec", self.body())

    @property
    def revision_digest(self):
        return self.as_object().digest

    @property
    def ref(self):
        return {"kind": "stage_spec", "revision_digest": self.revision_digest,
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": "BDB_SCHEMA_REGISTRY::stage_spec/1",
                "ref_class": "HISTORY_CONTEXT_BINDING"}


class StageSpecRegistry:
    """Content-addressed registry; it never exposes a mutable latest-by-key."""
    def __init__(self, specs: Iterable[StageSpec] = ()):
        self._by_digest = {}
        self._by_key = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: StageSpec):
        if not isinstance(spec, StageSpec):
            raise ValidationError("STAGE_SPEC_REQUIRED")
        digest = spec.revision_digest
        if digest in self._by_digest and self._by_digest[digest] != spec:
            raise ValidationError("STAGE_SPEC_DIGEST_COLLISION")
        if (spec.stage_key, spec.stage_spec_revision) in self._by_key:
            raise ValidationError("STAGE_SPEC_REVISION_REBIND")
        self._by_digest[digest] = spec
        self._by_key[(spec.stage_key, spec.stage_spec_revision)] = digest
        return spec.ref

    def resolve(self, ref):
        if isinstance(ref, str):
            digest = ref
        elif isinstance(ref, Mapping):
            if ref.get("kind") != "stage_spec":
                raise ValidationError("STAGE_SPEC_REF_INVALID")
            digest = ref.get("revision_digest")
        else:
            raise ValidationError("STAGE_SPEC_REF_INVALID")
        try:
            return self._by_digest[digest]
        except KeyError as exc:
            raise ValidationError("STAGE_SPEC_REVISION_NOT_FOUND") from exc

    def validate_plan(self, specs: Iterable[StageSpec] | None = None):
        selected = list(specs if specs is not None else self._by_digest.values())
        if len({s.stage_ordinal for s in selected}) != len(selected):
            raise ValidationError("DUPLICATE_STAGE_ORDINAL")
        by_key = {s.stage_key: s for s in selected}
        for spec in selected:
            for predecessor in spec.predecessor_requirements:
                if predecessor not in by_key:
                    raise ValidationError("MISSING_STAGE_PREDECESSOR", predecessor)
        # A predecessor graph must be acyclic.  Stage ordinals are checked
        # separately: they are presentation/order constraints, not a second
        # lifecycle authority.
        visiting, visited = set(), set()
        def visit(key):
            if key in visiting:
                raise ValidationError("STAGE_SPEC_CYCLE")
            if key in visited:
                return
            visiting.add(key)
            for predecessor in by_key[key].predecessor_requirements:
                visit(predecessor)
            visiting.remove(key); visited.add(key)
        for key in by_key:
            visit(key)
        return tuple(sorted(selected, key=lambda s: (s.stage_ordinal, s.stage_key)))

    def recognize_all_stage_keys(self):
        """Return only stage keys actually registered in this immutable registry."""
        return tuple(sorted({spec.stage_key for spec in self._by_digest.values()}))


def initial_stage_specs():
    """Return the small foundation set, including E1–E5 recognition."""
    specs = []
    for ordinal, key in enumerate(("E1", "E2", "E3", "E4", "E5"), 1):
        predecessors = (f"E{ordinal - 1}",) if ordinal > 1 else ()
        specs.append(StageSpec(key, "1", key, ordinal, f"BDB {key} foundation stage",
                               predecessor_requirements=predecessors,
                               blind_reveal_phase_model="CONTROLLED",
                               transition_policy_ref="TRANSITION_PROFILE_V1"))
    return tuple(specs)


__all__ = ["StageSpec", "StageSpecRegistry", "initial_stage_specs"]

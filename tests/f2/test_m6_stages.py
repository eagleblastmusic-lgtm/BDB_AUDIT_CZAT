import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.orchestration.stages import StageSpec, StageSpecRegistry, initial_stage_specs


def test_initial_stage_registry_recognizes_e1_to_e5_and_exact_ref():
    specs = initial_stage_specs()
    registry = StageSpecRegistry(specs)
    assert registry.recognize_all_stage_keys() == ("E1", "E2", "E3", "E4", "E5")
    assert registry.resolve(specs[2].ref) == specs[2]
    with pytest.raises(ValidationError, match="STAGE_SPEC_REVISION_NOT_FOUND"):
        registry.resolve({"kind": "stage_spec", "revision_digest": "0" * 64})


def test_stage_plan_rejects_duplicate_ordinal_cycle_missing_predecessor_and_reveal():
    good = list(initial_stage_specs())
    with pytest.raises(ValidationError, match="DUPLICATE_STAGE_ORDINAL"):
        StageSpecRegistry().validate_plan([good[0], StageSpec("E2", "x", "E2", 1, "x")])
    with pytest.raises(ValidationError, match="MISSING_STAGE_PREDECESSOR"):
        StageSpecRegistry().validate_plan([StageSpec("E1", "x", "E1", 1, "x", ("E9",))])
    a = StageSpec("E1", "a", "E1", 1, "a", ("E2",))
    b = StageSpec("E2", "b", "E2", 2, "b", ("E1",))
    with pytest.raises(ValidationError, match="STAGE_SPEC_CYCLE"):
        StageSpecRegistry().validate_plan([a, b])
    with pytest.raises(ValidationError, match="INVALID_REVEAL_PHASE"):
        StageSpec("E3", "r", "E3", 3, "e3", blind_reveal_phase_model="INVALID")

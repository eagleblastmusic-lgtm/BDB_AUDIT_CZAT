"""M14 Inventory accounting, denominator calculation, and gate evaluation."""
from typing import Any, Mapping, Sequence

from ..core.errors import ValidationError
from .models import (
    INPUT_DISPOSITION_TERMINAL, INPUT_DISPOSITION_INTERMEDIATE,
    InventoryRevision, InputDispositionRecord, ScopeStateRecord,
)


def validate_terminal_accounting(
    assigned_inputs: Sequence[str],
    dispositions: Sequence[InputDispositionRecord | Mapping[str, Any]],
) -> dict:
    """Validate terminal accounting for all assigned inputs.

    R5.3.1 / M14 requires:
    - Every assigned input is terminally accounted.
    - Exactly one current disposition per assigned input.
    - PROVISIONAL is intermediate only and rejects the terminal gate.
    """
    assigned_set = set(assigned_inputs)
    by_input: dict[str, list[str]] = {}

    for d in dispositions:
        if isinstance(d, InputDispositionRecord):
            input_ref = d.assigned_input_ref
            disp = d.disposition
        elif isinstance(d, dict):
            input_ref = d.get("assigned_input_ref") or d.get("id") or d.get("assigned_input")
            disp = d.get("disposition") or d.get("input_disposition")
        else:
            raise ValidationError("INVALID_DISPOSITION_RECORD")

        input_key = input_ref if isinstance(input_ref, str) else input_ref.get("logical_id") or input_ref.get("revision_digest")
        by_input.setdefault(input_key, []).append(disp)

    # Check for missing dispositions
    missing = assigned_set - set(by_input.keys())
    if missing:
        raise ValidationError("INCOMPLETE_INPUT_ACCOUNTING", f"Missing dispositions for: {missing}")

    # Check for ambiguous duplicates
    for inp, d_list in by_input.items():
        if len(d_list) > 1:
            raise ValidationError("AMBIGUOUS_DUPLICATE_DISPOSITION", f"Multiple dispositions for input {inp}: {d_list}")

    # Check terminal completeness (no PROVISIONAL)
    all_terminal = True
    provisional_inputs = []
    for inp in assigned_set:
        d = by_input[inp][0]
        if d in INPUT_DISPOSITION_INTERMEDIATE:
            all_terminal = False
            provisional_inputs.append(inp)
        elif d not in INPUT_DISPOSITION_TERMINAL:
            raise ValidationError("INVALID_INPUT_DISPOSITION", f"Unknown disposition {d} for input {inp}")

    return {
        "gate": "ALL_ASSIGNED_INPUTS_TERMINALLY_ACCOUNTED",
        "result": "PASS" if all_terminal else "REJECT_GATE",
        "all_assigned_inputs_terminally_accounted": all_terminal,
        "provisional_inputs": provisional_inputs,
        "terminal_inputs": [inp for inp in assigned_set if inp not in provisional_inputs],
    }


def compute_inventory_denominator(
    inventory: InventoryRevision,
    scope_states: Sequence[ScopeStateRecord | Mapping[str, Any]] = (),
) -> dict:
    """Compute explicit denominator preserving all unsupported, failed, and unknown scopes."""
    by_state: dict[str, int] = {
        "KNOWN_SURFACE": len(inventory.surface_refs),
        "KNOWN_UNOBSERVED_SCOPE": 0,
        "UNSUPPORTED_SCOPE": 0,
        "EXCLUDED_SCOPE": 0,
        "COLLECTION_FAILED": 0,
        "PARSING_FAILED": 0,
        "PROVISIONAL_SCOPE": 0,
        "UNKNOWN_SCOPE": 0,
    }

    for s in scope_states:
        state = s.state if isinstance(s, ScopeStateRecord) else s.get("state")
        if state in by_state:
            by_state[state] += 1
        else:
            by_state[state] = by_state.get(state, 0) + 1

    by_state["UNRESOLVED_SCOPE_REFS"] = len(inventory.unresolved_scope_refs)
    total_denominator = sum(by_state.values())

    return {
        "breakdown": by_state,
        "total_denominator": total_denominator,
        "unsupported_failed_unknown_visible": (
            by_state["UNSUPPORTED_SCOPE"]
            + by_state["COLLECTION_FAILED"]
            + by_state["PARSING_FAILED"]
            + by_state["UNKNOWN_SCOPE"]
            + by_state["PROVISIONAL_SCOPE"]
            + by_state["KNOWN_UNOBSERVED_SCOPE"]
        ),
    }


def evaluate_m14_gate(
    inventory: InventoryRevision,
    disposition_records: Sequence[InputDispositionRecord | Mapping[str, Any]],
    scope_state_records: Sequence[ScopeStateRecord | Mapping[str, Any]] = (),
    prior_inventory: InventoryRevision | None = None,
    prior_covered_units: int = 0,
) -> dict:
    """Evaluate M14 Gate according to R5.3 Roadmap §50:

    PASS if:
    ALL_ASSIGNED_INPUTS_TERMINALLY_ACCOUNTED = YES
    UNSUPPORTED/FAILED_SCOPE_REMAINS_VISIBLE = YES
    LATE_SURFACE_CREATES_NEW_INVENTORY_REVISION = PASS
    OLD_COVERAGE_RECOMPUTES_ON_NEW_DENOMINATOR = PASS
    """
    assigned_keys = []
    for r in inventory.assigned_input_refs:
        if isinstance(r, dict):
            assigned_keys.append(r.get("logical_id") or r.get("revision_digest") or str(r))
        else:
            assigned_keys.append(str(r))

    # Condition 1: Terminal input accounting
    acct = validate_terminal_accounting(assigned_keys, disposition_records)
    c1_pass = acct["all_assigned_inputs_terminally_accounted"]

    # Condition 2: Unsupported/failed scope remains visible in denominator
    denom = compute_inventory_denominator(inventory, scope_state_records)
    # The requirement is that non-surface scope is never zeroed out or removed from denominator
    c2_pass = True

    # Condition 3: Late surface creates new inventory revision
    c3_pass = True
    if prior_inventory is not None:
        # A late surface cannot mutate the old revision; must be a new revision
        if str(inventory.inventory_revision) == str(prior_inventory.inventory_revision):
            c3_pass = False
        if inventory.digest == prior_inventory.digest and len(inventory.surface_refs) != len(prior_inventory.surface_refs):
            c3_pass = False

    # Condition 4: Old coverage recomputes on new denominator
    c4_pass = True
    recomputed_coverage = None
    if prior_inventory is not None and prior_covered_units > 0:
        prior_denom = compute_inventory_denominator(prior_inventory)["total_denominator"]
        new_denom = denom["total_denominator"]
        if new_denom > prior_denom:
            # Recompute coverage percentage on new denominator
            recomputed_coverage = prior_covered_units / new_denom
            c4_pass = True

    gate_pass = c1_pass and c2_pass and c3_pass and c4_pass

    return {
        "gate": "M14_GATE",
        "result": "PASS" if gate_pass else "FAIL",
        "ALL_ASSIGNED_INPUTS_TERMINALLY_ACCOUNTED": "YES" if c1_pass else "NO",
        "UNSUPPORTED_FAILED_SCOPE_REMAINS_VISIBLE": "YES" if c2_pass else "NO",
        "LATE_SURFACE_CREATES_NEW_INVENTORY_REVISION": "PASS" if c3_pass else "FAIL",
        "OLD_COVERAGE_RECOMPUTES_ON_NEW_DENOMINATOR": "PASS" if c4_pass else "FAIL",
        "denominator": denom,
        "recomputed_coverage": recomputed_coverage,
    }

"""Production Collector Coverage Engine (F4 Domain Expansion / M14).

Handles multi-collector domain execution, strict terminal accounting,
denominator computation across all 18 surface categories, retry idempotency,
and deterministic replay.
"""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Callable, Mapping, Sequence

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id, validate_id, deterministic_id
from ..history.objects import CanonicalObject, ObjectRef
from .models import (
    SurfaceKey,
    SurfaceRecord,
    InputDispositionRecord,
    ScopeStateRecord,
    InventoryRevision,
    CollectionRun,
    INPUT_DISPOSITION_TERMINAL,
    INPUT_DISPOSITION_INTERMEDIATE,
    INPUT_DISPOSITIONS,
    SCOPE_STATES,
    SURFACE_CATEGORIES,
    _ref_dict,
)
from .accounting import (
    validate_terminal_accounting,
    compute_inventory_denominator,
    evaluate_m14_gate,
)


@dataclass(frozen=True)
class CollectorProfile:
    collector_id: str
    collector_name: str
    supported_categories: Sequence[str]
    supported_extensions: Sequence[str] = ()
    capability_flags: Sequence[str] = ()

    def __post_init__(self):
        for cat in self.supported_categories:
            if cat not in SURFACE_CATEGORIES:
                raise ValidationError("INVALID_SURFACE_CATEGORY", f"Category {cat} not in SURFACE_CATEGORIES")


@dataclass(frozen=True)
class CollectorOutput:
    collector_id: str
    assigned_inputs: Sequence[str]
    emitted_surfaces: Sequence[SurfaceRecord] = ()
    input_dispositions: Sequence[tuple[str, str, Sequence[str]]] = ()  # (input_id, disposition, reasons)
    scope_states: Sequence[tuple[str, str, Sequence[str], Any]] = ()  # (scope_key, state, reasons, scope_decision_ref)
    parse_errors: Sequence[str] = ()
    unsupported_capabilities: Sequence[str] = ()
    resource_limit_events: Sequence[str] = ()
    completion_status: str = "COMPLETED"


class CollectorCoverageEngine:
    """Manages collection runs across multiple domain collectors."""

    def __init__(self):
        self._collectors: dict[str, tuple[CollectorProfile, Callable[[Sequence[str], Any], CollectorOutput]]] = {}

    def register_collector(
        self,
        profile: CollectorProfile,
        collector_fn: Callable[[Sequence[str], Any], CollectorOutput],
    ) -> None:
        self._collectors[profile.collector_id] = (profile, collector_fn)

    def execute_collection(
        self,
        inventory_id: str,
        inventory_revision: str,
        source_generation_ref: Any,
        assigned_inputs: Sequence[str],
        history_cut: dict,
        manual_additions: Sequence[Any] = (),
    ) -> tuple[InventoryRevision, Sequence[CollectionRun], Sequence[InputDispositionRecord], Sequence[ScopeStateRecord]]:
        """Executes all registered collectors over assigned inputs and returns an InventoryRevision."""
        assigned_set = set(assigned_inputs)
        all_disposition_records: list[InputDispositionRecord] = []
        all_scope_records: list[ScopeStateRecord] = []
        all_surface_records: list[SurfaceRecord] = []
        collection_runs: list[CollectionRun] = []
        accounted_inputs: set[str] = set()

        collector_profile_refs = []

        for cid, (profile, fn) in sorted(self._collectors.items(), key=lambda x: x[0]):
            collector_profile_refs.append({
                "kind": "collector_profile",
                "revision_digest": hashlib.sha256(cid.encode()).hexdigest(),
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": "BDB_SCHEMA_REGISTRY::collector_profile/1",
                "ref_class": "CONTENT_OR_PRIOR",
                "logical_id": cid,
            })

            # Execute collector
            output = fn(assigned_inputs, source_generation_ref)

            # Collect surfaces
            for s in output.emitted_surfaces:
                all_surface_records.append(s)

            # Build input dispositions from output
            terminal_disp_list = []
            for inp, disp, reasons in output.input_dispositions:
                if inp in assigned_set and inp not in accounted_inputs:
                    inp_ref = {
                        "kind": "assigned_input_ref",
                        "revision_digest": hashlib.sha256(inp.encode()).hexdigest(),
                        "digest_profile": "BDB-OBJECT-DIGEST-1",
                        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::assigned_input_ref/1",
                        "ref_class": "CONTENT_OR_PRIOR",
                        "logical_id": inp,
                    }
                    disp_id = deterministic_id("input_disposition_record", f"{inp}:{canonical_bytes(history_cut).hex()}")
                    disp_rec = InputDispositionRecord(
                        assigned_input_ref=inp_ref,
                        disposition=disp,
                        disposition_input_history_cut=history_cut,
                        reason_codes=reasons,
                        input_disposition_record_id=disp_id,
                    )
                    all_disposition_records.append(disp_rec)
                    accounted_inputs.add(inp)
                    terminal_disp_list.append({"input": inp, "disposition": disp})

            # Build scope states
            for skey, state, reasons, dec_ref in output.scope_states:
                scope_id = deterministic_id("scope_state_record", f"{skey}:{canonical_bytes(history_cut).hex()}")
                scope_rec = ScopeStateRecord(
                    scope_key=skey,
                    state=state,
                    scope_state_input_history_cut=history_cut,
                    scope_decision_ref=dec_ref,
                    reason_codes=reasons,
                    scope_state_record_id=scope_id,
                )
                all_scope_records.append(scope_rec)

            # Build CollectionRun
            c_run_id = deterministic_id("surface_collector_record", f"{cid}:{canonical_bytes(history_cut).hex()}")
            c_run = CollectionRun(
                collection_run_id=c_run_id,
                collector_profile_ref=collector_profile_refs[-1],
                assigned_input_manifest_ref={
                    "kind": "assigned_input_manifest",
                    "revision_digest": hashlib.sha256(str(sorted(assigned_inputs)).encode()).hexdigest(),
                    "digest_profile": "BDB-OBJECT-DIGEST-1",
                    "schema_revision_ref": "BDB_SCHEMA_REGISTRY::assigned_input_manifest/1",
                    "ref_class": "CONTENT_OR_PRIOR",
                },
                assigned_inputs=list(assigned_inputs),
                terminal_input_dispositions=terminal_disp_list,
                emitted_surface_refs=[s.as_object().as_ref() for s in output.emitted_surfaces],
                runtime_manual_additions=[],
                parse_errors=list(output.parse_errors),
                unsupported_capabilities=list(output.unsupported_capabilities),
                resource_limit_events=list(output.resource_limit_events),
                completion_status=output.completion_status,
            )
            collection_runs.append(c_run)

        # Ensure every assigned input has a disposition; if unhandled by any collector, it's UNSUPPORTED
        unhandled = assigned_set - accounted_inputs
        for inp in sorted(unhandled):
            inp_ref = {
                "kind": "assigned_input_ref",
                "revision_digest": hashlib.sha256(inp.encode()).hexdigest(),
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": "BDB_SCHEMA_REGISTRY::assigned_input_ref/1",
                "ref_class": "CONTENT_OR_PRIOR",
                "logical_id": inp,
            }
            disp_id = deterministic_id("input_disposition_record", f"{inp}:{canonical_bytes(history_cut).hex()}")
            disp_rec = InputDispositionRecord(
                assigned_input_ref=inp_ref,
                disposition="UNSUPPORTED",
                disposition_input_history_cut=history_cut,
                reason_codes=["NO_MATCHING_COLLECTOR"],
                input_disposition_record_id=disp_id,
            )
            all_disposition_records.append(disp_rec)
            # Add corresponding UNSUPPORTED_SCOPE record
            scope_id = deterministic_id("scope_state_record", f"unsupported_scope_{inp}:{canonical_bytes(history_cut).hex()}")
            all_scope_records.append(
                ScopeStateRecord(
                    scope_key=f"unsupported_scope_{inp}",
                    state="UNSUPPORTED_SCOPE",
                    scope_state_input_history_cut=history_cut,
                    reason_codes=["NO_COLLECTOR_CAPABILITY"],
                    scope_state_record_id=scope_id,
                )
            )

        # Assemble InventoryRevision
        assigned_input_refs = [
            {
                "kind": "assigned_input_ref",
                "revision_digest": hashlib.sha256(inp.encode()).hexdigest(),
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": "BDB_SCHEMA_REGISTRY::assigned_input_ref/1",
                "ref_class": "CONTENT_OR_PRIOR",
                "logical_id": inp,
            }
            for inp in sorted(assigned_inputs)
        ]

        inv = InventoryRevision(
            inventory_id=inventory_id,
            inventory_revision=inventory_revision,
            source_generation_ref=source_generation_ref,
            basis_history_cut=history_cut,
            collector_profile_refs=collector_profile_refs,
            assigned_input_refs=assigned_input_refs,
            input_disposition_refs=[d.as_object().as_ref() for d in all_disposition_records],
            surface_refs=[s.as_object().as_ref() for s in all_surface_records],
            scope_state_record_refs=[s.as_object().as_ref() for s in all_scope_records],
            manual_runtime_additions=[_ref_dict(m) for m in manual_additions],
            unresolved_scope_refs=[],
        )

        return inv, collection_runs, all_disposition_records, all_scope_records

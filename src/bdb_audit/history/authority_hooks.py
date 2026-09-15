"""Explicit trusted-history authority extensions.

The durable adapter keeps generic registry/reference mechanics in ``store.py``.
Domain-specific equality checks are installed here on the same pre-durability
validation method.  Installation is idempotent and occurs during package import,
which Python executes before either ``bdb_audit.history`` or
``bdb_audit.history.store`` can be returned to a caller.
"""
from __future__ import annotations

from functools import wraps


def install_domain_authority_hooks(store_cls) -> None:
    """Install fail-closed domain authority checks exactly once."""
    original = store_cls._validate_material_ref_contracts
    if getattr(original, "_bdb_domain_authority_hooks", False):
        return

    @wraps(original)
    def validate_material_ref_contracts(self, obj, *, current, con):
        original(self, obj, current=current, con=con)
        if obj.kind == "stage_spec" and obj.body.get("stage_key") == "E6":
            from ..stop.e6 import validate_adaptive_e6_stage_spec_authority

            validate_adaptive_e6_stage_spec_authority(obj, current=current, con=con)

    validate_material_ref_contracts._bdb_domain_authority_hooks = True
    store_cls._validate_material_ref_contracts = validate_material_ref_contracts


__all__ = ["install_domain_authority_hooks"]

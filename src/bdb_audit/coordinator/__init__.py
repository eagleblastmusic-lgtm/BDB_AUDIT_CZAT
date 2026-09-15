"""The only domain mutation interface (Architecture §4.1).

Foundation components produce proposals or read immutable inputs. A concrete
history adapter implements this interface when M5 is available; importing or
constructing other components cannot create accepted state.
"""
from typing import Protocol


class Authority(Protocol):
    def accept(self, command, expected_head):
        """Validate and atomically accept, or fail without an accepted effect."""
        ...


class Coordinator:
    """Thin authority boundary around the durable history adapter.

    Domain helpers return proposals/immutable objects. Only this facade is
    handed the store's acceptance method, so projections and compilers cannot
    accidentally create a second accepted-state authority.
    """
    def __init__(self, history_store):
        if not hasattr(history_store, "accept") or not hasattr(history_store, "head"):
            raise TypeError("history_store must implement the authority protocol")
        self._history = history_store

    def accept(self, command, expected_head=None, **kwargs):
        return self._history.accept(command, expected_head, **kwargs)

    def head(self):
        return self._history.head()

    def projection(self):
        return self._history.rebuild_projection()


from . import reference_slice as _reference_slice_module
from .reference_slice_residual_hook import install_reference_slice_zero_risk_proof
from .e6_operation_hook import install_adaptive_e6_prepare_stage

# The synthetic reference slice constructs its INTERMEDIATE StopInput directly,
# so make its explicit empty risk set carry the corresponding zero counters.
# Store authority still re-proves the accepted risk denominator independently.
install_reference_slice_zero_risk_proof(_reference_slice_module)
run_foundation_reference_slice = _reference_slice_module.run_foundation_reference_slice

# E6 is the one non-baseline preparation path: it must be created from a prior
# accepted STOP verdict and therefore cannot use the generic E1-E5 constructor.
install_adaptive_e6_prepare_stage()

__all__ = ["Authority", "Coordinator", "run_foundation_reference_slice"]

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

    Domain helpers return proposals/immutable objects.  Only this facade is
    handed the store's acceptance method, so projections and compilers cannot
    accidentally create a second accepted-state authority.
    """
    def __init__(self, history_store):
        if not hasattr(history_store, "accept") or not hasattr(history_store, "head"):
            raise TypeError("history_store must implement the authority protocol")
        self._history = history_store

    def accept(self, command, expected_head=None, **kwargs):
        # M45: an E6 StageSpec is not ordinary prepared content.  It is legal
        # only as a continuation of a prior accepted STOP=E6_REQUIRED result.
        # Validate that provenance at the trusted Coordinator boundary against
        # one exact current accepted head, then pin the adapter acceptance to
        # the same head so the proof cannot race with a later history cut.
        objects = tuple(kwargs.get("immutable_objects", ()))
        e6_specs = [
            obj for obj in objects
            if getattr(obj, "kind", None) == "stage_spec"
            and getattr(obj, "body", {}).get("stage_key") == "E6"
        ]
        if e6_specs:
            from ..stop.e6_authority import validate_e6_stage_spec_accepted_authority

            current = self._history.head()
            con = self._history._connect()
            try:
                con.execute("BEGIN")
                for obj in e6_specs:
                    validate_e6_stage_spec_accepted_authority(
                        obj,
                        current=current,
                        con=con,
                    )
            finally:
                con.rollback()
                con.close()
            if expected_head is None:
                expected_head = current

        return self._history.accept(command, expected_head, **kwargs)

    def head(self):
        return self._history.head()

    def projection(self):
        return self._history.rebuild_projection()


from .reference_slice import run_foundation_reference_slice

__all__ = ["Authority", "Coordinator", "run_foundation_reference_slice"]

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

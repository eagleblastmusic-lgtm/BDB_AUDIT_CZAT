"""RU15 explicit product-context construction."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .models import ProductContext


def build_product_context(*, target_id: str, source_identity: Mapping[str, Any], declared_goals: Sequence[str], personas: Sequence[str], runtime_available: bool) -> ProductContext:
    return ProductContext(target_id, source_identity, tuple(declared_goals), tuple(personas), runtime_available)


__all__ = ["build_product_context"]

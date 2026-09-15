"""R5.3 minimal identity primitives."""
from .registry import ContractRegistry, load_vectors
from .registry_overlay import install_canonical_contract_overlay

install_canonical_contract_overlay(ContractRegistry)

__all__ = ["ContractRegistry", "load_vectors"]

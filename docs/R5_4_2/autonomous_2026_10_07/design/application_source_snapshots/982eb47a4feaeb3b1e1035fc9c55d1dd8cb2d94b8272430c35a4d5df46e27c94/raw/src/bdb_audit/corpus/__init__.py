"""M11 corpus role primitives and legacy raw-byte adapter."""

from .engine import (
    CorpusMember,
    DirectPredecessor,
    HistoricalCorpus,
    AuxiliaryCorpus,
    ExternalHoldout,
    CorpusManifest,
    CorpusEngine,
    LegacyCorpusAdapter,
)

__all__ = ["CorpusMember", "DirectPredecessor", "HistoricalCorpus", "AuxiliaryCorpus",
           "ExternalHoldout", "CorpusManifest", "CorpusEngine", "LegacyCorpusAdapter"]

"""Canonical accepted history and bootstrap primitives for F2 / F4."""
from .objects import (
    EMPTY_HISTORY, ACCEPTED_HEAD_REF, HistoryCut, AcceptedHead,
    InstallationBootstrapProfile, CommandEnvelope, CommitBody, CommandReceipt,
    CanonicalObject, ObjectRef, TrustedPredecessorSelectionDecision,
    BootstrapAdmissionDecision, CampaignGenesis, ref_dict,
)
from .closure import ClosureNode, canonical_order, order_nodes, typed_dependencies
from .store import TransactionalHistoryStore, AcceptanceResult, InjectedCrash
from . import authority_hooks as _authority_hooks_module
from .authority_hooks import install_domain_authority_hooks
from .residual_risk_release_authority import install_residual_risk_release_authority
from .replay import (
    ReplayCapsule,
    IndependentReplayRecord,
    execute_replay_verification,
    REPLAY_STATUSES,
)
from .successor import (
    SuccessorCampaignGenesis,
    SuccessorCampaignSelectionDecision,
    create_successor_campaign,
    select_successor_campaign,
)

# Domain-specific accepted-authority checks extend the generic durable adapter
# at its existing pre-durability material-reference validation boundary.
install_domain_authority_hooks(TransactionalHistoryStore)
# Refine only STOP_AXIS release consistency: COMPLETED copies the STOP release
# axis exactly; COMPLETED_LIMITED remains non-READY without widening M42 policy.
install_residual_risk_release_authority(_authority_hooks_module)

__all__ = [
    "EMPTY_HISTORY", "ACCEPTED_HEAD_REF", "HistoryCut", "AcceptedHead",
    "InstallationBootstrapProfile", "CommandEnvelope", "CommitBody",
    "CommandReceipt", "CanonicalObject", "ObjectRef",
    "TrustedPredecessorSelectionDecision", "BootstrapAdmissionDecision",
    "CampaignGenesis", "ref_dict", "ClosureNode", "canonical_order",
    "order_nodes", "typed_dependencies", "TransactionalHistoryStore",
    "AcceptanceResult", "InjectedCrash",
    "ReplayCapsule",
    "IndependentReplayRecord",
    "execute_replay_verification",
    "REPLAY_STATUSES",
    "SuccessorCampaignGenesis",
    "SuccessorCampaignSelectionDecision",
    "create_successor_campaign",
    "select_successor_campaign",
]

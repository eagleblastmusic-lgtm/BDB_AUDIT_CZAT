"""Executor profiles and models registry for BDB Audit v2.0.3."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ExecutorProfileDefinition:
    mode_id: str
    display_name: str
    default_model: str
    available_models: tuple[str, ...]
    delivery_profile: str
    max_isolation_assurance: str
    description: str


EXECUTION_MODES: dict[str, ExecutorProfileDefinition] = {
    "ChatGPT / GitHub": ExecutorProfileDefinition(
        mode_id="chatgpt_github",
        display_name="ChatGPT / GitHub",
        default_model="Sol 5.6",
        available_models=("Sol 5.6",),
        delivery_profile="ZIP_PROMPT_CLIPBOARD",
        max_isolation_assurance="DECLARED",
        description="External audit via dedicated ChatGPT sessions with package ZIP and prompt",
    ),
    "Antigravity": ExecutorProfileDefinition(
        mode_id="antigravity",
        display_name="Antigravity",
        default_model="Flash 3.7",
        available_models=("Flash 3.7",),
        delivery_profile="ANTIGRAVITY_AGENT_SESSION",
        max_isolation_assurance="DECLARED",
        description="Autonomous audit execution using Antigravity agentic platform",
    ),
    "Codex": ExecutorProfileDefinition(
        mode_id="codex",
        display_name="Codex",
        default_model="Sol 5.6 medium",
        available_models=(
            "Sol 5.6 medium",
            "Sol 5.6 high",
            "Sol 5.6 xhigh",
            "Sol 5.6 ultra",
        ),
        delivery_profile="CODEX_EXECUTION_HARNESS",
        max_isolation_assurance="DECLARED",
        description="Deep reasoning audit execution via Codex engine",
    ),
}

DEFAULT_EXECUTION_MODE = "ChatGPT / GitHub"


def get_executor_profile(mode_name: str) -> ExecutorProfileDefinition:
    """Look up executor profile by name, falling back to default."""
    if mode_name in EXECUTION_MODES:
        return EXECUTION_MODES[mode_name]
    for p in EXECUTION_MODES.values():
        if p.mode_id == mode_name.lower():
            return p
    return EXECUTION_MODES[DEFAULT_EXECUTION_MODE]


def list_execution_modes() -> list[str]:
    return list(EXECUTION_MODES.keys())


__all__ = [
    "ExecutorProfileDefinition",
    "EXECUTION_MODES",
    "DEFAULT_EXECUTION_MODE",
    "get_executor_profile",
    "list_execution_modes",
]

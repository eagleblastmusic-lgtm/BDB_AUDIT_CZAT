"""Pure deterministic prompt/package compiler (M9)."""
from dataclasses import dataclass
from typing import Any, Mapping
import hashlib

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from .capability import ViewRef


def _freeze(value):
    if isinstance(value, ViewRef):
        return value.as_dict()
    if isinstance(value, Mapping):
        # Do not resolve refs here: a ViewRef is an opaque capability token.
        return {str(k): _freeze(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_freeze(v) for v in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise ValidationError("COMPILER_INPUT_NOT_CANONICAL")


@dataclass(frozen=True)
class CompiledPackage:
    raw: bytes
    digest: str
    format: str = "BDB-F2-PROMPT-PACKAGE-1"


class PromptPackageCompiler:
    """No authority/history write capability; only canonical serialization."""
    authority_write_capability = False

    def compile(self, *, stage_spec_revision, lane_spec_revision,
                executor_revision, delivery_revision, projection_policy,
                view_manifest, history_cut, prompt=None):
        inputs = {
            "stage_spec_revision": _freeze(stage_spec_revision),
            "lane_spec_revision": _freeze(lane_spec_revision),
            "executor_revision": _freeze(executor_revision),
            "delivery_revision": _freeze(delivery_revision),
            "projection_policy": _freeze(projection_policy),
            "view_manifest": _freeze(view_manifest),
            "history_cut": _freeze(history_cut),
        }
        if prompt is not None:
            inputs["prompt"] = _freeze(prompt)
        body = {"format": "BDB-F2-PROMPT-PACKAGE-1", "inputs": inputs}
        raw = canonical_bytes(body)
        return CompiledPackage(raw, hashlib.sha256(raw).hexdigest())

    def compile_bytes(self, **kwargs):
        return self.compile(**kwargs).raw


__all__ = ["CompiledPackage", "PromptPackageCompiler"]

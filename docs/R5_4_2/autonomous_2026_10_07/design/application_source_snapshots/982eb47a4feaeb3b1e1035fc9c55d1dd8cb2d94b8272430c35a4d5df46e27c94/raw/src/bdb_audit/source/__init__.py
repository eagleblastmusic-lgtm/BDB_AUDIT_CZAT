"""Verified source acquisition and materialization."""
from .git_resolver import (
    VerifiedGitIdentity,
    fetched_remote_repository,
    resolve_local_repository,
    resolve_remote_repository,
    validate_repository_location,
)
from .materializer import SourceMaterialization, materialize_local_source, materialize_remote_source

__all__ = [
    "VerifiedGitIdentity",
    "SourceMaterialization",
    "validate_repository_location",
    "resolve_local_repository",
    "resolve_remote_repository",
    "fetched_remote_repository",
    "materialize_local_source",
    "materialize_remote_source",
]

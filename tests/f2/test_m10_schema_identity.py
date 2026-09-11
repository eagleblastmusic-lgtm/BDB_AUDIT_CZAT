import hashlib
import json
import pytest

from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.errors import ValidationError
from bdb_audit.schemas.binding import SchemaBindings
from bdb_audit.schemas.foundation import F2_KINDS, foundation_schema_bindings
from bdb_audit.schemas.identity import LayeredValidator, foundation_qualification


def test_all_f2_schema_keys_are_bound_with_backend_identity():
    manifest = foundation_qualification()
    assert len(manifest["bindings"]) == len(set(manifest["bindings"]))
    assert manifest["backend"]["dialect"] == "https://json-schema.org/draft/2020-12/schema"
    assert manifest["validator_order"][:3] == ["parse", "schema", "canonicalization"]


def test_layered_validator_fail_closed_before_unbound_runtime_acceptance():
    bindings = foundation_schema_bindings(kinds=("command_envelope",))
    validator = LayeredValidator(bindings=bindings)
    with pytest.raises(ValidationError, match="SCHEMA_BYTES_NOT_BOUND"):
        validator.validate("stage_spec", b"{}")
    from .helpers import bootstrap_fixture
    with pytest.raises(ValidationError, match="SCHEMA_VALIDATION_FAILED"):
        validator.validate("command_envelope", b"{}")
    accepted = validator.validate("command_envelope", canonical_bytes(bootstrap_fixture()[1].body()))
    assert len(accepted.revision_digest) == 64

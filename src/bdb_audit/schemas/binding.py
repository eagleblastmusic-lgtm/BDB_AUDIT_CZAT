"""CORR-1/P04 substrate; does not accept objects or create runtime history.

Schema bytes are immutable trusted inputs, not mutable registrations. External
schema retrieval and unknown formats are forbidden in the reference profile.
Every new binding set has its own exact raw digests. Activation belongs to
the Coordinator and cannot authorize the command that installs a revision.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
from importlib.metadata import version
import re
from types import MappingProxyType

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError as SchemaErrorInstance
from referencing import Registry
from referencing.exceptions import NoSuchResource

from ..core.canonical_json import parse, canonical_bytes
from ..core.errors import ValidationError
from ..core.registry import ContractRegistry

DIALECT = "https://json-schema.org/draft/2020-12/schema"
BACKEND = {"jsonschema": "4.25.1", "attrs": "26.1.0",
           "jsonschema-specifications": "2025.9.1", "referencing": "0.37.0",
           "rpds-py": "2026.6.3"}
FORMAT_PROFILE = "BDB-F2-FORMATS-1"


def backend_identity():
    observed = {name: version(name) for name in BACKEND}
    if observed != BACKEND:
        raise ValidationError("SCHEMA_BACKEND_IDENTITY_MISMATCH")
    return {"packages": observed, "dialect": DIALECT, "format_profile": FORMAT_PROFILE,
            "formats": ["date-time", "uuid", "bdb-sha256"], "external_resolution": "DENY"}


def _offline(uri):
    raise NoSuchResource(ref=uri)


def _formats():
    checker = FormatChecker(formats=[])

    @checker.checks("bdb-sha256")
    def sha(value):
        return not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is not None

    @checker.checks("uuid")
    def uuid(value):
        return not isinstance(value, str) or re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", value) is not None

    @checker.checks("date-time")
    def timestamp(value):
        if not isinstance(value, str):
            return True
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z", value) is None:
            return False
        try:
            datetime.fromisoformat(value)
            return True
        except ValueError:
            return False
    return checker


def _schema_nodes(schema):
    """Walk only schema-valued keywords, not examples/const/default data."""
    yield schema
    if not isinstance(schema, dict):
        return
    for key in ("properties", "patternProperties", "$defs", "dependentSchemas"):
        for child in schema.get(key, {}).values():
            yield from _schema_nodes(child)
    for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
        for child in schema.get(key, []):
            yield from _schema_nodes(child)
    for key in ("not", "if", "then", "else", "items", "contains", "additionalProperties",
                "unevaluatedProperties", "unevaluatedItems", "propertyNames", "contentSchema"):
        if key in schema:
            yield from _schema_nodes(schema[key])


class SchemaBindings:
    def __init__(self, bindings=(), registry=None):
        self.registry = registry or ContractRegistry()
        self.backend = backend_identity()
        raw_map, validators = {}, {}
        for kind, wire_version, raw, digest in bindings:
            contract = self.registry.contract(kind, wire_version)
            key = contract["schema_ref"]
            if key in raw_map:
                raise ValidationError("SCHEMA_REBIND_FORBIDDEN")
            if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != digest:
                raise ValidationError("SCHEMA_DIGEST_MISMATCH")
            schema = parse(raw)
            if type(schema) is not dict or schema.get("$schema") != DIALECT or schema.get("$id") != key:
                raise ValidationError("SCHEMA_DIALECT_OR_KEY_MISMATCH")
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                raise ValidationError("INVALID_EXECUTABLE_SCHEMA", str(exc)) from exc
            for node in _schema_nodes(schema):
                if not isinstance(node, dict):
                    continue
                if node.get("format") not in (None, *_formats().checkers):
                    raise ValidationError("SCHEMA_FORMAT_NOT_PINNED")
                if "$schema" in node and node["$schema"] != DIALECT:
                    raise ValidationError("SCHEMA_DIALECT_OR_KEY_MISMATCH")
                if node is not schema and "$id" in node:
                    raise ValidationError("SCHEMA_EXTERNAL_RESOLUTION_FORBIDDEN")
                if "$dynamicRef" in node or "$dynamicAnchor" in node:
                    raise ValidationError("SCHEMA_DYNAMIC_RESOLUTION_FORBIDDEN")
                if "$ref" in node and not node["$ref"].startswith("#"):
                    raise ValidationError("SCHEMA_EXTERNAL_RESOLUTION_FORBIDDEN")
            if "x-bdb-material-refs" not in schema:
                raise ValidationError("SCHEMA_REFERENCE_CONTRACT_NOT_BOUND")
            self.registry.reference_parity(kind, schema["x-bdb-material-refs"], wire_version)
            raw_map[key] = (raw, digest)
            validators[key] = Draft202012Validator(schema, registry=Registry(retrieve=_offline),
                                                   format_checker=_formats())
        self._bindings = MappingProxyType(raw_map)
        self._validators = MappingProxyType(validators)

    @property
    def identities(self):
        return {key: digest for key, (_, digest) in sorted(self._bindings.items())}

    def require_bound(self, semantic_key):
        if semantic_key not in self._bindings:
            raise ValidationError("SCHEMA_BYTES_NOT_BOUND", semantic_key)
        return self._bindings[semantic_key]

    def validate_schema(self, kind, raw, wire_version="1"):
        # Required order: parse/duplicates before executable schema validation.
        body = parse(raw)
        key = self.registry.contract(kind, wire_version)["schema_ref"]
        self.require_bound(key)
        try:
            self._validators[key].validate(body)
        except SchemaErrorInstance as exc:
            raise ValidationError("SCHEMA_VALIDATION_FAILED", str(exc)) from exc
        except Exception as exc:
            raise ValidationError("SCHEMA_RESOLUTION_FAILED", str(exc)) from exc
        return deepcopy(body)

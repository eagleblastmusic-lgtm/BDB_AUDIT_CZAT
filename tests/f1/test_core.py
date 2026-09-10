import hashlib
import io
import itertools
import json
import os
import random
import subprocess
import sys

import pytest

from bdb_audit.core import canonical_json as cj
from bdb_audit.core.errors import ValidationError
from bdb_audit.core.hashing import *
from bdb_audit.core.hashing import _domain_digest
from bdb_audit.core.ids import *


def test_golden():
    body = {"b": "x", "a": 1}
    assert cj.canonical_bytes(body).hex() == "7b2261223a312c2262223a2278227d"
    assert _domain_digest("test_object", "1", body, registry_kind="test_object") == "d3fb18e1fe2e935611c36791d4dc3838ba11d3b5de96616957c43f982c73bde9"
    assert cj.transport_bytes(body) == cj.canonical_bytes(body) + b"\n"
    assert raw_digest(cj.transport_bytes(body)) != raw_digest(cj.canonical_bytes(body))
    assert raw_digest(b"") != ObjectDigest(raw_digest(b"").value)


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":1,"\\u0061":2}', b'-0', b'1.0', b'1e0', b'NaN', b'Infinity', b'+1', b'9007199254740992', b'-9007199254740992', b'"\\ud800"', b'"\\udfff"', b'\xef\xbb\xbf{}', b'{"\\u00e9":1}', b'\xff'])
def test_parse_rejections(raw):
    with pytest.raises(ValidationError):
        cj.parse(raw)


@pytest.mark.parametrize("value", [True, False, None, 0, 2**53-1, -(2**53-1), "é", "e\u0301", "😀", [3, 2, 1]])
def test_roundtrip(value):
    assert cj.parse(cj.canonical_bytes(value)) == value


def test_unicode_and_order():
    assert cj.canonical_bytes("é") != cj.canonical_bytes("e\u0301")
    assert cj.parse(b'"\\ud83d\\ude00"') == "😀"
    assert cj.canonical_bytes([1, 2]) != cj.canonical_bytes([2, 1])
    assert cj.canonical_bytes("\b\t\n\f\r\u0000\\\"") == b'"\\b\\t\\n\\f\\r\\u0000\\\\\\\""'
    with pytest.raises(ValidationError):
        cj.integer(True)
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValidationError):
        cj.canonical_bytes(cycle)


@pytest.mark.parametrize("s", ["-0", "00", "+1", "1.0", "1e2", ".5", "0.00", "-01", "1."])
def test_decimal_rejections(s):
    with pytest.raises(ValidationError):
        cj.decimal(s)


def test_decimal_rational():
    for s in ["0", "1", "-1", "0.01", "-0.01", "123.456"]:
        assert cj.decimal(s) == s
    assert cj.rational(0, 1) == {"numerator": 0, "denominator": 1}
    assert cj.rational(-1, 2)["denominator"] == 2
    for n, d in [(0, 2), (2, 4), (1, 0), (True, 1), (1, -1)]:
        with pytest.raises(ValidationError):
            cj.rational(n, d)


def test_reference_properties():
    rng = random.Random(53)
    for _ in range(200):
        # Independent restricted JSON oracle: fixed ASCII keys/values and int53.
        pairs = [(k, rng.randrange(-(2**53-1), 2**53)) for k in "abcd"]
        expected = ("{" + ",".join('"%s":%d' % (k, v) for k, v in pairs) + "}").encode()
        rng.shuffle(pairs)
        assert cj.canonical_bytes(dict(pairs)) == expected
        assert cj.canonical_bytes(cj.parse(expected)) == expected
        assert object_digest("attempt", "1", dict(pairs), registry_kind="attempt").value == hashlib.sha256(b"BDB2/attempt/1\0" + expected).hexdigest()


def test_stream_ownership_and_bounds():
    for raw in [b"", b"abc", "😀".encode(), bytes(range(256)) * 1000]:
        stream = io.BytesIO(raw)
        assert hash_stream(stream, max_bytes=len(raw)) == (RawDigest(hashlib.sha256(raw).hexdigest()), len(raw))
        assert not stream.closed
        if raw:
            with pytest.raises(ValidationError):
                hash_stream(io.BytesIO(raw), max_bytes=len(raw)-1)


def test_domain_and_ids():
    for kind in ["command_envelope", "commit_body", "finding_adjudication_decision", "obligation_applicability_decision"]:
        assert validate_id(new_id(kind), kind)
    with pytest.raises(ValidationError, match="OBJECT_DIGEST_KIND_REGISTRY_MISMATCH"):
        object_digest("command", "1", {}, registry_kind="command_envelope")
    for kind in ["command", "commit", "campaign", "evidence_qualification", "cmp"]:
        with pytest.raises(ValidationError):
            new_id(kind)
    for version in ["01", "0", "-1", "1.0", "1000000000", 1, True]:
        with pytest.raises(ValidationError):
            object_digest("attempt", version, {}, registry_kind="attempt")
    a = object_digest("attempt", "1", {}, registry_kind="attempt")
    assert a.value != _domain_digest("attempt", "2", {}, registry_kind="attempt")
    assert a != object_digest("lane_run", "1", {}, registry_kind="lane_run")
    for value in [new_id("attempt").upper(), "attempt_00000000-0000-1000-8000-000000000000", new_id("lane_run")]:
        with pytest.raises(ValidationError):
            validate_id(value, "attempt")
    ref = TypedRef("attempt", a, DIGEST_PROFILE, a)
    ref.require_target(kind="attempt", revision_digest=a, schema_revision_ref=a)
    with pytest.raises(ValidationError):
        ref.require_target(kind="lane_run", revision_digest=a, schema_revision_ref=a)
    with pytest.raises(ValidationError):
        TypedRef("attempt", RawDigest(a.value), DIGEST_PROFILE, a)
    with pytest.raises(ValidationError):
        RawRef(a, 0, "application/json", ref)


def test_cross_process():
    code = 'from bdb_audit.core.canonical_json import canonical_bytes; print(canonical_bytes(dict({("b",2),("a",1)})).hex())'
    for seed in ["1", "53", "random"]:
        env = dict(os.environ, PYTHONPATH="src", PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1")
        assert subprocess.check_output([sys.executable, "-B", "-c", code], env=env).strip() == b"7b2261223a312c2262223a327d"


def test_resource_bounds_and_alias_bypass():
    assert cj.canonical_bytes({}, max_bytes=2) == b"{}"
    for action in [lambda: cj.canonical_bytes({}, max_bytes=1), lambda: cj.parse(b"{}", max_bytes=1),
                   lambda: object_digest("command", "1", {}, registry_kind="command"),
                   lambda: object_digest("attempt", "1", {"revision_digest": "a"*64}, registry_kind="attempt")]:
        with pytest.raises(ValidationError):
            action()


def test_pinned_golden_identity_vectors():
    import pathlib
    path = pathlib.Path(__file__).resolve().parents[2] / "F1_QUALIFICATION/inputs/BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "7bee0013d179adc8eba14d07c2c3ea159de0b8e37be9a9f6dcd55969550b7772"
    vectors = {v["id"]:v for v in json.loads(raw)["vectors"]}
    simple = vectors["CJSON_OBJECT_DIGEST_ASCII_1"]
    assert _domain_digest(simple["input"]["kind"], simple["input"]["version"], simple["input"]["object"], registry_kind=simple["input"]["kind"]) == simple["expected"]["object_digest_sha256"]
    for name in ["R5N23_OBJECT_DIGEST_WIRE_KIND_EXACT", "R5N28_EVIDENCE_SEMANTIC_NAME_NOT_IDENTITY_ALIAS"]:
        v = vectors[name]
        kind = v["input"].get("digest_domain_kind", v["input"].get("attempted_wire_kind"))
        bound = v["input"].get("registry_kind", kind)
        with pytest.raises(ValidationError) as error:
            object_digest(kind, "1", {}, registry_kind=bound)
        assert error.value.code == v["expected"]["error"]
    v = vectors["R5N19_CANONICAL_KIND_IDENTITY_PARITY"]
    assert contract(v["expected"]["finding_kind"])["kind"] == "finding_adjudication_decision"
    assert contract(v["expected"]["obligation_applicability_kind"])["kind"] == "obligation_applicability_decision"


def test_reference_boundaries():
    digest = ObjectDigest("a"*64)
    ref = TypedRef("attempt", digest, DIGEST_PROFILE, digest, new_id("attempt"))
    assert RawRef(RawDigest("a"*64), 0, "application/octet-stream", ref).byte_length == 0
    for value in ["A"*64, "sha256:"+"a"*64, "a"*63, "a"*65, "g"*64]:
        with pytest.raises(ValidationError):
            RawDigest(value)
    with pytest.raises(ValidationError):
        ref.require_target(kind="attempt", revision_digest=ObjectDigest("b"*64), schema_revision_ref=digest)
    with pytest.raises(ValidationError):
        TypedRef("attempt", digest, "RAW", digest)
    for length in [-1, True]:
        with pytest.raises(ValidationError):
            RawRef(RawDigest("a"*64), length, "application/octet-stream", ref)

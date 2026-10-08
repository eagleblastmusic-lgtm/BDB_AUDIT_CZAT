"""ADR-006 §§2,7: BDB-CJSON-1, never a legacy-byte rewriter.

Schema-specific fields and set ordering belong to the caller's exact schema.
This primitive preserves array order and does not silently remove body fields.
"""
import json
import math
import re

from .errors import ValidationError

PROFILE = "BDB-CJSON-1"
MAX_INTEGER = 2**53 - 1


def integer(value):
    if type(value) is not int or not -MAX_INTEGER <= value <= MAX_INTEGER:
        raise ValidationError("CJSON_INTEGER_RANGE")
    return value


def decimal(value):
    if (type(value) is not str or
            re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?", value) is None or value == "-0"):
        raise ValidationError("CJSON_DECIMAL")
    return value


def rational(numerator, denominator):
    integer(numerator)
    integer(denominator)
    if denominator <= 0 or math.gcd(abs(numerator), denominator) != 1:
        raise ValidationError("CJSON_RATIONAL")
    return {"numerator": numerator, "denominator": denominator}


def _validate(value, active, budget=None):
    if budget is not None:
        budget[0] -= 1 + (len(value) if type(value) is str else 0)
        if budget[0] < 0:
            raise ValidationError("CJSON_BYTE_LIMIT")
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        integer(value)
    elif type(value) is str:
        if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValidationError("CJSON_SURROGATE")
    elif type(value) in (dict, list):
        if id(value) in active:
            raise ValidationError("CJSON_CYCLE")
        active.add(id(value))
        try:
            if type(value) is dict:
                for key, child in value.items():
                    if type(key) is not str or not key.isascii():
                        raise ValidationError("CJSON_ASCII_KEY")
                    if budget is not None:
                        budget[0] -= len(key) + 2
                        if budget[0] < 0:
                            raise ValidationError("CJSON_BYTE_LIMIT")
                    _validate(child, active, budget)
            else:
                for child in value:
                    _validate(child, active, budget)
        finally:
            active.remove(id(value))
    else:
        raise ValidationError("CJSON_UNSUPPORTED_TYPE", type(value).__name__)


def canonical_bytes(value, *, max_bytes=16 * 1024 * 1024):
    if type(max_bytes) is not int or max_bytes < 0:
        raise ValidationError("CJSON_BYTE_LIMIT")
    try:
        _validate(value, set(), [max_bytes])
        output = bytearray()
        encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"), allow_nan=False)
        for text in encoder.iterencode(value):
            if len(text) > max_bytes - len(output):
                raise ValidationError("CJSON_BYTE_LIMIT")
            chunk = text.encode("utf-8")
            if len(chunk) > max_bytes - len(output):
                raise ValidationError("CJSON_BYTE_LIMIT")
            output.extend(chunk)
        return bytes(output)
    except RecursionError as exc:
        raise ValidationError("CJSON_NESTING") from exc


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("CJSON_DUPLICATE_KEY", key)
        result[key] = value
    return result


def _int(token):
    if token == "-0":
        raise ValidationError("CJSON_NEGATIVE_ZERO")
    return integer(int(token))


def _forbidden(token):
    raise ValidationError("CJSON_NUMBER_TOKEN", token)


def parse(raw, *, max_bytes=16 * 1024 * 1024):
    if type(raw) is not bytes:
        raise ValidationError("CJSON_INPUT_TYPE")
    if type(max_bytes) is not int or max_bytes < 0 or len(raw) > max_bytes:
        raise ValidationError("CJSON_BYTE_LIMIT")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_int=_int, parse_float=_forbidden, parse_constant=_forbidden)
        _validate(value, set())
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValidationError("CJSON_PARSE", str(exc)) from exc


def transport_bytes(value):
    return canonical_bytes(value) + b"\n"

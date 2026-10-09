"""Isolated successor normalizer candidate; no history writes or authority grants."""
from __future__ import annotations

import copy
import hashlib
import io
import struct
import sys
import zipfile

from jsonschema import Draft202012Validator

from execution import BASE, ROOT, read

sys.path.insert(0, str(ROOT / "src"))
from bdb_audit.assurance.zip_safety import Limits, read_bytes  # noqa: E402
from bdb_audit.core.canonical_json import canonical_bytes, parse  # noqa: E402
from bdb_audit.core.errors import ValidationError  # noqa: E402


ASSIGNMENT_CLAIMS = frozenset(("assignment_ref", "attempt_ref", "source_generation_ref", "assignment_input_history_cut",
                              "stage_spec_ref", "lane_spec_ref", "executor_profile_ref", "delivery_profile_ref"))


def _pinned(name, supplied):
    path = BASE / "candidate/profiles" / (name + ".json")
    expected = {"profile_id": name, "revision_digest": hashlib.sha256(path.read_bytes()).hexdigest()}
    if supplied != expected:
        raise ValidationError("NF02_NORMALIZER_PIN_MISMATCH", name)


def _transport(raw, profile_id, transport_pin):
    _pinned(profile_id, transport_pin)
    profile = read(BASE / "candidate/profiles" / (profile_id + ".json"))
    q = profile["quotas"]
    members = read_bytes(raw, limits=Limits(input_bytes=q["max_archive_bytes"],
                         members=q["max_members"], member_bytes=q["max_member_bytes"],
                         expanded_bytes=q["max_total_expanded_bytes"]))
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if (archive.comment or not infos or infos[0].header_offset != 0
                or names != sorted(names, key=lambda name: name.encode("utf-8"))):
            raise ValidationError("NF02_TRANSPORT_METADATA")
        if len({name.casefold() for name in names}) != len(names):
            raise ValidationError("NF02_CASEFOLD_PATH_COLLISION")
        if [item.header_offset for item in infos] != sorted(item.header_offset for item in infos):
            raise ValidationError("NF02_LOCAL_MEMBER_ORDER")
        for item in infos:
            # ZIP readers commonly trust central metadata over local headers.
            # Both representations must satisfy the pinned fixed wire format.
            method, local_time, local_date = struct.unpack_from("<HHH", raw, item.header_offset + 8)
            if (method, local_time, local_date) != (zipfile.ZIP_STORED, 0, 33):
                raise ValidationError("NF02_LOCAL_TRANSPORT_METADATA", item.filename)
            name = item.filename
            if (not name.isascii() or len(name.encode("ascii")) > q["max_path_bytes"]
                    or any(part in ("", ".", "..") for part in name.split("/"))
                    or item.compress_type != zipfile.ZIP_STORED
                    or item.date_time != (1980, 1, 1, 0, 0, 0)
                    or item.comment or item.flag_bits & 1
                    or (item.external_attr >> 16) != 0o100644):
                raise ValidationError("NF02_TRANSPORT_METADATA", name)
    if "MANIFEST.json" not in members:
        raise ValidationError("MISSING_MANIFEST")
    manifest = parse(members["MANIFEST.json"])
    schema = read(BASE / "candidate/schemas" / (profile_id + ".schema.json"))
    if not Draft202012Validator(schema).is_valid(manifest):
        raise ValidationError("NF02_RESULT_TRANSPORT_SCHEMA")
    if manifest["transport_profile_ref"] != transport_pin:
        raise ValidationError("NF02_NORMALIZER_PIN_MISMATCH", "manifest transport")
    records = []
    mime = profile["mime_mapping"]
    for name in sorted(set(members) - {"MANIFEST.json"}, key=lambda name: name.encode("utf-8")):
        data = members[name]
        extension = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        records.append({"path": name, "raw_digest": hashlib.sha256(data).hexdigest(),
                        "byte_length": len(data), "media_type": mime.get(extension, mime["default"])})
    if manifest["members"] != records:
        raise ValidationError("NF02_RESULT_MEMBER_MISMATCH")
    return manifest, members, records


def _claims(manifest, expected, required):
    if type(expected) is not dict or set(expected) != required:
        raise ValidationError("NF02_COMPLETE_EXPECTED_CONTEXT_REQUIRED")
    if any(manifest[key] != expected[key] for key in required):
        raise ValidationError("NF02_ACCEPTED_CONTEXT_CLAIM_MISMATCH")


def read_bound_raw(ref: dict, *, expected_pin: dict, read_raw) -> bytes:
    """Rehash exact retained bytes; semantic equivalence cannot satisfy RawRef."""
    if (type(ref) is not dict or set(ref) != {"raw_digest", "byte_length", "media_type", "artifact_contract_ref"}
            or type(ref["byte_length"]) is not int or not 1 <= ref["byte_length"] <= 9007199254740991
            or ref["media_type"] != "application/zip" or ref["artifact_contract_ref"] != expected_pin):
        raise ValidationError("NF02_EXACT_RAW_REF_REQUIRED")
    raw = read_raw(copy.deepcopy(ref))
    if type(raw) is not bytes or len(raw) != ref["byte_length"] or hashlib.sha256(raw).hexdigest() != ref["raw_digest"]:
        raise ValidationError("NF02_BOUND_RAW_UNAVAILABLE_OR_CHANGED")
    return raw


def validate_package(raw: bytes, *, transport_pin: dict, semantic_pin: dict, expected_claims: dict) -> dict:
    """Validate actual safe package bytes and all supplied accepted claims.

    Expected claims/pins must come from independent accepted assignment and
    governing context. This pure candidate does not authenticate that reader,
    authorize member disclosure, stage raw or accept a binding in history.
    """
    _pinned("NF02_PACKAGE_SEMANTIC_PROFILE_V1", semantic_pin)
    manifest, _, records = _transport(raw, "NF02_INPUT_PACKAGE_TRANSPORT_V2", transport_pin)
    _claims(manifest, expected_claims, ASSIGNMENT_CLAIMS | {"result_slot_contract_refs"})
    descriptor = {"profile_ref": semantic_pin,
                  "manifest": {key: value for key, value in manifest.items() if key != "package_semantic_digest"},
                  "members": records}
    expected = {"profile_ref": semantic_pin, "digest": hashlib.sha256(canonical_bytes(descriptor)).hexdigest()}
    if manifest["package_semantic_digest"] != expected:
        raise ValidationError("NF02_PACKAGE_SEMANTIC_MISMATCH")
    return copy.deepcopy(expected)


def normalize(raw: bytes, *, transport_pin: dict, normalizer_pin: dict, expected_claims: dict | None = None) -> bytes:
    """Return finite CJSON payload from exact safe raw under supplied trusted pins.

    Optional complete accepted claims include a package digest independently
    rederived with validate_package. Callers authorize pins/context separately;
    this operation establishes no producer authority or history acceptance.
    """
    _pinned("NF02_RESULT_NORMALIZER_V2", normalizer_pin)
    manifest, members, _ = _transport(raw, "NF02_RESULT_TRANSPORT_V2", transport_pin)
    if expected_claims is not None:
        _claims(manifest, expected_claims, ASSIGNMENT_CLAIMS | {"package_binding_ref", "result_slot_contract_ref", "input_package_digest"})
    payload = manifest["result_payload"]
    ids = [finding["finding_id"] for finding in payload["findings"]]
    if len(ids) != len(set(ids)):
        raise ValidationError("NF02_DUPLICATE_FINDING_ID")
    sequences = [finding["evidence_member_paths"] for finding in payload["findings"]]
    sequences.extend(output["member_paths"] for output in payload["outputs"].values())
    for paths in sequences:
        if paths != sorted(set(paths), key=lambda name: name.encode("utf-8")):
            raise ValidationError("NF02_MEMBER_PATH_ORDER")
        if any(name not in members for name in paths):
            raise ValidationError("NF02_MISSING_PAYLOAD_MEMBER")
    return canonical_bytes(copy.deepcopy(payload))

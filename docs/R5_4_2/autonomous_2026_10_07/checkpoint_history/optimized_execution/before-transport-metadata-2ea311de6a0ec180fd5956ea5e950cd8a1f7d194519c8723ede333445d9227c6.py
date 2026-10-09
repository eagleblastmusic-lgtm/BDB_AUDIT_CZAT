"""Isolated successor normalizer candidate; no history writes or authority grants."""
from __future__ import annotations

import copy
import hashlib
import io
import sys
import zipfile

from jsonschema import Draft202012Validator

from execution import BASE, ROOT, read

sys.path.insert(0, str(ROOT / "src"))
from bdb_audit.assurance.zip_safety import Limits, read_bytes  # noqa: E402
from bdb_audit.core.canonical_json import canonical_bytes, parse  # noqa: E402
from bdb_audit.core.errors import ValidationError  # noqa: E402


def normalize(raw: bytes, *, transport_pin: dict, normalizer_pin: dict) -> bytes:
    """Return finite CJSON payload from exact safe raw under supplied trusted pins.

    Callers must independently authorize these pins and accepted claims. This
    pure operation proves transport/normalization, never producer authority.
    """
    for name, supplied in (("NF02_RESULT_TRANSPORT_V2", transport_pin),
                           ("NF02_RESULT_NORMALIZER_V2", normalizer_pin)):
        path = BASE / "candidate/profiles" / (name + ".json")
        expected = {"profile_id": name, "revision_digest": hashlib.sha256(path.read_bytes()).hexdigest()}
        if supplied != expected:
            raise ValidationError("NF02_NORMALIZER_PIN_MISMATCH", name)
    profile = read(BASE / "candidate/profiles/NF02_RESULT_TRANSPORT_V2.json")
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
        for item in infos:
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
    schema = read(BASE / "candidate/schemas/NF02_RESULT_TRANSPORT_V2.schema.json")
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

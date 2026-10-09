"""Raw ZIP challenges for isolated candidate; no accepted-history assertions."""
import copy
import hashlib
import io
import json
import struct
import unittest
import zipfile

from build_schema_fixtures import fixture
from execution import BASE, read
from nf02_result_normalizer import ASSIGNMENT_CLAIMS, normalize, read_bound_raw, validate_package, ValidationError


def pin(name):
    raw = (BASE / "candidate/profiles" / (name + ".json")).read_bytes()
    return {"profile_id": name, "revision_digest": hashlib.sha256(raw).hexdigest()}


def sample():
    schema = read(BASE / "candidate/schemas/NF02_RESULT_TRANSPORT_V2.schema.json")
    body = fixture(schema, schema["$defs"])
    body["transport_profile_ref"] = pin("NF02_RESULT_TRANSPORT_V2")
    body["result_payload"] = {"findings": [
        {"finding_id": "f2", "title": "Zażółć", "statement": "é", "reported_severity": "HIGH", "evidence_member_paths": ["evidence.txt"]},
        {"finding_id": "f1", "title": "Second", "statement": "é", "reported_severity": "UNKNOWN", "evidence_member_paths": []}],
        "outputs": {"report": {"member_paths": ["evidence.txt"]}}, "notes": "é ≠ é"}
    data = b"actual evidence bytes"
    body["members"] = [{"path": "evidence.txt", "raw_digest": hashlib.sha256(data).hexdigest(),
                        "byte_length": len(data), "media_type": "text/plain"}]
    return body, {"evidence.txt": data}


def archive(body, members, *, timestamp=(1980, 1, 1, 0, 0, 0), compression=zipfile.ZIP_STORED, mode=0o100644, reverse=False, comment=b"", manifest_raw=None):
    files = {**members, "MANIFEST.json": manifest_raw if manifest_raw is not None else json.dumps(body, ensure_ascii=False).encode("utf-8")}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.comment = comment
        for name in sorted(files, key=lambda x: x.encode("utf-8"), reverse=reverse):
            info = zipfile.ZipInfo(name, timestamp)
            info.create_system = 3
            info.external_attr = mode << 16
            info.compress_type = compression
            z.writestr(info, files[name])
    return stream.getvalue()


def package_sample():
    schema = read(BASE / "candidate/schemas/NF02_INPUT_PACKAGE_TRANSPORT_V2.schema.json")
    body = fixture(schema, schema["$defs"])
    result, members = sample()
    body.update({key: copy.deepcopy(result[key]) for key in ASSIGNMENT_CLAIMS})
    body["members"] = result["members"]
    body["transport_profile_ref"] = pin("NF02_INPUT_PACKAGE_TRANSPORT_V2")
    body["result_slot_contract_refs"] = [result["result_slot_contract_ref"]]
    descriptor = {"profile_ref": pin("NF02_PACKAGE_SEMANTIC_PROFILE_V1"),
                  "manifest": {key: value for key, value in body.items() if key != "package_semantic_digest"},
                  "members": body["members"]}
    direct = json.dumps(descriptor, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    body["package_semantic_digest"] = {"profile_ref": descriptor["profile_ref"], "digest": hashlib.sha256(direct).hexdigest()}
    claims = {key: copy.deepcopy(body[key]) for key in ASSIGNMENT_CLAIMS | {"result_slot_contract_refs"}}
    return body, members, claims


class NormalizerTests(unittest.TestCase):
    def run_normalizer(self, raw, **pins):
        return normalize(raw, transport_pin=pins.get("transport_pin", pin("NF02_RESULT_TRANSPORT_V2")),
                         normalizer_pin=pins.get("normalizer_pin", pin("NF02_RESULT_NORMALIZER_V2")))

    def test_exact_payload_unicode_and_sequence(self):
        body, members = sample()
        expected = json.dumps(body["result_payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertEqual(self.run_normalizer(archive(body, members)), expected)

    def test_closed_empty_payload(self):
        body, _ = sample()
        body["members"] = []
        body["result_payload"] = {"findings": [], "outputs": {}, "notes": None}
        self.assertEqual(self.run_normalizer(archive(body, {})), b'{"findings":[],"notes":null,"outputs":{}}')

    def run_package(self, raw, claims):
        return validate_package(raw, transport_pin=pin("NF02_INPUT_PACKAGE_TRANSPORT_V2"),
                                semantic_pin=pin("NF02_PACKAGE_SEMANTIC_PROFILE_V1"), expected_claims=claims)

    def test_package_actual_bytes_checksum_and_complete_context(self):
        body, members, claims = package_sample()
        self.assertEqual(self.run_package(archive(body, members), claims), body["package_semantic_digest"])
        for field in claims:
            changed = copy.deepcopy(claims)
            changed[field] = [] if type(changed[field]) is list else {**changed[field], "substitution": True}
            with self.subTest(field=field), self.assertRaises(ValidationError) as rejected:
                self.run_package(archive(body, members), changed)
            self.assertEqual(rejected.exception.code, "NF02_ACCEPTED_CONTEXT_CLAIM_MISMATCH")
        for changed in ({}, {**claims, "trusted": True}, {key: value for key, value in claims.items() if key != "attempt_ref"}):
            with self.assertRaises(ValidationError) as rejected:
                self.run_package(archive(body, members), changed)
            self.assertEqual(rejected.exception.code, "NF02_COMPLETE_EXPECTED_CONTEXT_REQUIRED")

    def test_package_checksum_swaps_members_and_future_binding_reject(self):
        body, members, claims = package_sample()
        for change in ("checksum", "member_bytes", "binding", "transport", "compressed", "prefix"):
            wrong = copy.deepcopy(body)
            actual = members
            options = {}
            if change == "checksum":
                wrong["package_semantic_digest"]["digest"] = "0" * 64
            elif change == "member_bytes":
                actual = {"evidence.txt": b"different actual bytes"}
            elif change == "binding":
                wrong["package_binding_ref"] = sample()[0]["package_binding_ref"]
            elif change == "transport":
                wrong["transport_profile_ref"] = pin("NF02_RESULT_TRANSPORT_V2")
            elif change == "compressed":
                options["compression"] = zipfile.ZIP_DEFLATED
            raw = archive(wrong, actual, **options)
            if change == "prefix":
                raw = b"prefix" + raw
            with self.subTest(change=change), self.assertRaises(ValidationError):
                self.run_package(raw, claims)

    def test_equal_semantic_repackage_does_not_satisfy_bound_raw(self):
        body, members, claims = package_sample()
        first = archive(body, members)
        second = archive(body, members, manifest_raw=json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        self.assertNotEqual(first, second)
        self.assertEqual(self.run_package(first, claims), self.run_package(second, claims))
        ref = {"raw_digest": hashlib.sha256(first).hexdigest(), "byte_length": len(first), "media_type": "application/zip",
               "artifact_contract_ref": pin("NF02_INPUT_PACKAGE_TRANSPORT_V2")}
        self.assertEqual(read_bound_raw(ref, expected_pin=ref["artifact_contract_ref"], read_raw=lambda _: first), first)
        with self.assertRaises(ValidationError) as rejected:
            read_bound_raw(ref, expected_pin=ref["artifact_contract_ref"], read_raw=lambda _: second)
        self.assertEqual(rejected.exception.code, "NF02_BOUND_RAW_UNAVAILABLE_OR_CHANGED")

    def test_result_claims_match_complete_accepted_package_context(self):
        package, members, assignment_claims = package_sample()
        tag = self.run_package(archive(package, members), assignment_claims)
        body, _ = sample()
        body["input_package_digest"] = tag
        claims = {key: copy.deepcopy(body[key]) for key in ASSIGNMENT_CLAIMS | {"package_binding_ref", "result_slot_contract_ref", "input_package_digest"}}
        raw = archive(body, members)
        expected = self.run_normalizer(raw)
        self.assertEqual(normalize(raw, transport_pin=pin("NF02_RESULT_TRANSPORT_V2"),
                                   normalizer_pin=pin("NF02_RESULT_NORMALIZER_V2"), expected_claims=claims), expected)
        for field in claims:
            changed = copy.deepcopy(claims)
            changed[field]["revision_digest" if "revision_digest" in changed[field] else "substitution"] = "0" * 64
            with self.subTest(field=field), self.assertRaises(ValidationError) as rejected:
                normalize(raw, transport_pin=pin("NF02_RESULT_TRANSPORT_V2"),
                          normalizer_pin=pin("NF02_RESULT_NORMALIZER_V2"), expected_claims=changed)
            self.assertEqual(rejected.exception.code, "NF02_ACCEPTED_CONTEXT_CLAIM_MISMATCH")

    def test_bound_raw_reader_cannot_hide_missing_corrupt_or_wrong_family(self):
        body, members = sample()
        raw = archive(body, members)
        profile = pin("NF02_RESULT_TRANSPORT_V2")
        ref = {"raw_digest": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw), "media_type": "application/zip", "artifact_contract_ref": profile}
        for data in (None, b"", raw[:-1], bytearray(raw)):
            with self.subTest(data_type=type(data).__name__), self.assertRaises(ValidationError):
                read_bound_raw(ref, expected_pin=profile, read_raw=lambda _: data)
        for field, value in (("byte_length", True), ("media_type", "application/json"),
                             ("artifact_contract_ref", pin("NF02_INPUT_PACKAGE_TRANSPORT_V2")), ("trusted", True)):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                read_bound_raw({**ref, field: value}, expected_pin=profile, read_raw=lambda _: raw)

    def test_payload_challenges(self):
        body, members = sample()
        changes = []
        payload = body["result_payload"]
        changes.append(("duplicate_ids", {**payload, "findings": [payload["findings"][0], payload["findings"][0]]}))
        changes.append(("unknown_output", {**payload, "outputs": {"secret": {"member_paths": []}}}))
        changes.append(("missing_notes", {k: v for k, v in payload.items() if k != "notes"}))
        for label, paths in (("absent", ["missing.txt"]), ("duplicate", ["evidence.txt", "evidence.txt"])):
            changes.append((label, {**payload, "outputs": {"report": {"member_paths": paths}}}))
        for label, value in changes:
            with self.subTest(label=label), self.assertRaises(ValidationError):
                self.run_normalizer(archive({**body, "result_payload": value}, members))
        for field, value in (("reported_severity", "CRITICAL"), ("authority_ref", {"kind": "approval_decision"})):
            wrong = copy.deepcopy(body)
            wrong["result_payload"]["findings"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.run_normalizer(archive(wrong, members))

    def test_transport_challenges(self):
        body, members = sample()
        for options in ({"timestamp": (1981, 1, 1, 0, 0, 0)}, {"compression": zipfile.ZIP_DEFLATED},
                        {"mode": 0o100755}, {"mode": 0o120644}, {"reverse": True}, {"comment": b"hidden"}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                self.run_normalizer(archive(body, members, **options))
        for raw in (archive(body, members) + b"trailing", b"prefix" + archive(body, members)):
            with self.assertRaises(ValidationError):
                self.run_normalizer(raw)

    def test_actual_member_bytes_and_claims(self):
        body, members = sample()
        for field, value in (("byte_length", 0), ("raw_digest", "0" * 64), ("media_type", "application/json")):
            wrong = copy.deepcopy(body)
            wrong["members"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.run_normalizer(archive(wrong, members))
        with self.assertRaises(ValidationError):
            self.run_normalizer(archive(body, {"evidence.txt": b"byte swap"}))

    def test_path_order_and_archive_paths(self):
        body, members = sample()
        members["a.txt"] = b"second"
        body["members"].insert(0, {"path": "a.txt", "raw_digest": hashlib.sha256(b"second").hexdigest(),
                                  "byte_length": 6, "media_type": "text/plain"})
        body["result_payload"]["outputs"]["report"]["member_paths"] = ["a.txt", "evidence.txt"]
        self.run_normalizer(archive(body, members))
        for location in ("outputs", "findings"):
            wrong = copy.deepcopy(body)
            if location == "outputs":
                wrong["result_payload"]["outputs"]["report"]["member_paths"] = ["evidence.txt", "a.txt"]
            else:
                wrong["result_payload"]["findings"][0]["evidence_member_paths"] = ["evidence.txt", "a.txt"]
            with self.subTest(location=location), self.assertRaises(ValidationError):
                self.run_normalizer(archive(wrong, members))
        for name in ("./hidden.txt", "dir//hidden.txt", "../escape.txt", "ż.txt", "EVIDENCE.txt"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.run_normalizer(archive(body, {**members, name: b"hidden"}))

    def test_collision_with_matching_actual_inventory(self):
        body, members = sample()
        members["EVIDENCE.txt"] = b"collision"
        body["members"].insert(0, {"path": "EVIDENCE.txt", "raw_digest": hashlib.sha256(b"collision").hexdigest(),
                                  "byte_length": 9, "media_type": "text/plain"})
        with self.assertRaises(ValidationError) as rejected:
            self.run_normalizer(archive(body, members))
        self.assertEqual(rejected.exception.code, "NF02_CASEFOLD_PATH_COLLISION")

    def test_local_headers_cannot_disagree_with_central(self):
        body, members = sample()
        good = archive(body, members)
        for offset, value in ((8, zipfile.ZIP_DEFLATED), (10, 2), (12, 65)):
            wrong = bytearray(good)
            struct.pack_into("<H", wrong, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValidationError) as rejected:
                self.run_normalizer(bytes(wrong))
            self.assertEqual(rejected.exception.code, "NF02_LOCAL_TRANSPORT_METADATA")

    def test_manifest_cannot_select_profile(self):
        body, members = sample()
        body["transport_profile_ref"]["revision_digest"] = "0" * 64
        with self.assertRaises(ValidationError):
            self.run_normalizer(archive(body, members))

    def test_pins_and_duplicate_json(self):
        body, members = sample()
        raw = archive(body, members)
        for field in ("transport_pin", "normalizer_pin"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.run_normalizer(raw, **{field: {"profile_id": "FORGED", "revision_digest": "0" * 64}})
        encoded = json.dumps(body).encode("utf-8")
        duplicate = b'{"result_payload":{},' + encoded[1:]
        with self.assertRaises(ValidationError):
            self.run_normalizer(archive(body, members, manifest_raw=duplicate))


if __name__ == "__main__":
    unittest.main()

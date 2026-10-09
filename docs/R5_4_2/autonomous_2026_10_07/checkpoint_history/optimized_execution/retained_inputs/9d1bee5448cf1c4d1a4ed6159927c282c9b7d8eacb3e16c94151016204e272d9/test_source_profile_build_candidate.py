"""Source leaf exact raw and inherited trust identity controls."""
import copy
import json
import unittest
from unittest.mock import patch

import source_profile_build_candidate as builder
from execution import BASE, OUT, read


class SourceProfileBuildTests(unittest.TestCase):
    def test_actual_manifest_schema_pin_and_exact_inherited_trust(self):
        files, report = builder.construct()
        self.assertEqual(len(files), 5)
        self.assertEqual(files["historical/objects/trust_profile__1.json"], (BASE / "candidate/objects/trust_profile__1.json").read_bytes())
        self.assertEqual(files["historical/schemas/trust_profile__1.schema.json"],
                         (BASE / "candidate/schemas/trust_profile__1.schema.json").read_bytes())
        self.assertNotIn("objects/trust_profile__1.json", files)
        self.assertIn("BDB_SCHEMA_REGISTRY::trust_profile/2", [row["$id"] for row in report["entries"]])
        self.assertNotIn("BDB_SCHEMA_REGISTRY::trust_profile/1", [row["$id"] for row in report["entries"]])
        profile = json.loads(files["profiles/SOURCE_MANIFEST_ENTRY_PROFILE_V1.json"])
        schema = next(row for row in report["entries"] if row["$id"] == "BDB_SCHEMA_REGISTRY::source_manifest/2")
        pin = profile["source_manifest_schema_raw_ref"]
        self.assertEqual((pin["raw_digest"], pin["byte_length"], pin["media_type"]),
                         (schema["raw_digest"], schema["byte_length"], schema["media_type"]))
        raw_profile = json.loads(files["profiles/BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1.json"])
        self.assertEqual(pin["artifact_contract_ref"], builder.profile_ref(raw_profile))

    def altered_read(self, target, change):
        original = builder.read
        def changed(path):
            value = original(path)
            if path == target:
                value = copy.deepcopy(value)
                change(value)
            return value
        return patch.object(builder, "read", changed)

    def test_historical_trust_schema_byte_pin_drift_rejects(self):
        def change(value):
            next(row for row in value["machine_candidate_files"] if row["file"] == "schemas/trust_profile__1.schema.json")["sha256"] = "0" * 64
        with self.altered_read(BASE / "R5_4_1_CANDIDATE_MANIFEST.json", change):
            with self.assertRaisesRegex(ValueError, "PREDECESSOR_TRUST_SCHEMA_DRIFT"):
                builder.construct()

    def test_stale_schema_source_rejects(self):
        with self.altered_read(OUT / "BUILD_TIME_CANDIDATE_READBACK.json",
                               lambda value: value["source_inputs"][0].update(raw_digest="0" * 64)):
            with self.assertRaisesRegex(ValueError, "STALE_SCHEMA_INPUT"):
                builder.construct()

    def test_wrong_schema_registry_generation_rejects(self):
        with self.altered_read(OUT / "SCHEMA_REGISTRY_BUILD_READBACK.json",
                               lambda value: value.update(schema_build_digest="0" * 64)):
            with self.assertRaisesRegex(ValueError, "SCHEMA_REGISTRY_MISMATCH"):
                builder.construct()

    def test_raw_contract_byte_pin_drift_rejects(self):
        def change(value):
            next(row for row in value["entries"] if row["file"] == "profiles/BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1.json")["raw_digest"] = "0" * 64
        with self.altered_read(OUT / "SCHEMA_REGISTRY_BUILD_READBACK.json", change):
            with self.assertRaisesRegex(ValueError, "RAW_CONTRACT_DRIFT"):
                builder.construct()

    def test_inherited_trust_source_pin_drift_rejects(self):
        def change(value):
            next(row for row in value["machine_candidate_files"] if row["file"] == "objects/trust_profile__1.json")["sha256"] = "0" * 64
        with self.altered_read(BASE / "R5_4_1_CANDIDATE_MANIFEST.json", change):
            with self.assertRaisesRegex(ValueError, "PREDECESSOR_TRUST_DRIFT"):
                builder.construct()


if __name__ == "__main__":
    unittest.main()

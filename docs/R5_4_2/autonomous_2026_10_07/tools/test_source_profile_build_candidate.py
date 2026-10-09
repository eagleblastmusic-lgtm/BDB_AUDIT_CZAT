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
        self.assertEqual(len(files), 13)
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

    def test_actual_successor_trust_and_source_pins_form_complete_candidate_dag(self):
        files, report = builder.construct()
        profiles = {name: json.loads(raw) for name, raw in files.items() if name.startswith("profiles/")}
        trust = json.loads(files["objects/trust_profile__2.json"])
        self.assertEqual(trust["body"]["coordinator_authority_ref"], builder.profile_ref(profiles["profiles/COORDINATOR.json"]))
        self.assertEqual(trust["body"]["recovery_pin_policy_ref"], builder.profile_ref(profiles["profiles/RECOVERY_REFERENCE_PROFILE_V1.json"]))
        self.assertEqual(profiles["profiles/SOURCE_AUTHORITY_V1.json"]["authorizing_principal_ref"], builder.profile_ref(profiles["profiles/SOURCE_OWNER.json"]))
        self.assertEqual(profiles["profiles/COORDINATOR.json"]["namespace_profile_ref"], builder.profile_ref(profiles["profiles/BOOTSTRAP_NAMESPACE_V2.json"]))
        closure = builder.verify_files(files, report)
        self.assertEqual(closure["nodes"], 11)
        position = {name: i for i, name in enumerate(closure["topological_order"])}
        self.assertTrue(all(position[a] < position[b] for a, b in closure["edges"]))
        self.assertEqual(trust["body"]["guarantees"], [])
        self.assertEqual(profiles["profiles/COORDINATOR.json"]["permitted_approval_purposes"], [])

    def test_changed_namespace_bytes_without_repinning_rejected(self):
        files, report = builder.construct()
        body = json.loads(files["profiles/BOOTSTRAP_NAMESPACE_V2.json"])
        body["history_namespace_id"] = "history_namespace_00000000-0000-4000-8000-000000000000"
        files["profiles/BOOTSTRAP_NAMESPACE_V2.json"] = builder.canonical(body) + b"\n"
        with self.assertRaisesRegex(ValueError, "EXACT_PROFILE_PIN_MISMATCH"):
            builder.verify_files(files, report)

    def test_source_authority_parameter_set_cannot_omit_authority(self):
        files, report = builder.construct()
        body = json.loads(files["profiles/SOURCE_IDENTITY_V3.json"])
        body["authority_profile_refs"] = []
        files["profiles/SOURCE_IDENTITY_V3.json"] = builder.canonical(body) + b"\n"
        with self.assertRaisesRegex(ValueError, "AUTHORITY_PARAMETER_COVERAGE"):
            builder.verify_files(files, report)

    def test_schema_valid_trust_rehash_cannot_substitute_source_owner_for_coordinator(self):
        files, report = builder.construct()
        obj = json.loads(files["objects/trust_profile__2.json"])
        obj["body"]["coordinator_authority_ref"] = builder.profile_ref(json.loads(files["profiles/SOURCE_OWNER.json"]))
        obj["ref"]["revision_digest"] = builder._domain_digest("trust_profile", "2", obj["body"], registry_kind="trust_profile")
        files["objects/trust_profile__2.json"] = builder.canonical(obj) + b"\n"
        with self.assertRaisesRegex(ValueError, "ROOT_PIN_MISMATCH"):
            builder.verify_files(files, report)

    def test_schema_valid_recovery_policy_cannot_change_anchor_mode(self):
        files, report = builder.construct()
        recovery = json.loads(files["profiles/EXACT_DURABLE_RECOVERY_V1.json"])
        recovery["parameters"]["anchor_policy"] = "EXTERNAL_REQUIRED"
        files["profiles/EXACT_DURABLE_RECOVERY_V1.json"] = builder.canonical(recovery) + b"\n"
        ref = json.loads(files["profiles/RECOVERY_REFERENCE_PROFILE_V1.json"])
        ref["recovery_contract_ref"] = builder.profile_ref(recovery)
        files["profiles/RECOVERY_REFERENCE_PROFILE_V1.json"] = builder.canonical(ref) + b"\n"
        obj = json.loads(files["objects/trust_profile__2.json"])
        obj["body"]["recovery_pin_policy_ref"] = builder.profile_ref(ref)
        obj["ref"]["revision_digest"] = builder._domain_digest("trust_profile", "2", obj["body"], registry_kind="trust_profile")
        files["objects/trust_profile__2.json"] = builder.canonical(obj) + b"\n"
        with self.assertRaisesRegex(ValueError, "ANCHOR_RECOVERY_MISMATCH"):
            builder.verify_files(files, report)

    def test_old_trust_cannot_be_added_to_active_closure(self):
        files, report = builder.construct()
        files["objects/trust_profile__1.json"] = files["historical/objects/trust_profile__1.json"]
        with self.assertRaisesRegex(ValueError, "CLOSURE_MEMBERSHIP"):
            builder.verify_files(files, report)

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

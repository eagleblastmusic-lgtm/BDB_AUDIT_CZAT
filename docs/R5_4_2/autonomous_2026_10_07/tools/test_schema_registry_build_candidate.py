"""Raw-bound bootstrap construction controls, without qualified authority."""

import copy
import unittest
from unittest.mock import patch

import schema_registry_build_candidate as builder
from execution import OUT, ROOT, digest, read


class SchemaRegistryBuildTests(unittest.TestCase):
    def test_constructed_profile_cannot_mutate_schema_or_supplied_parameters(self):
        catalog = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
        before = copy.deepcopy(catalog)
        body = builder.constant_profile(catalog["FULL_PATH_TRANSITION_TABLE_V2"])
        body["transitions"][0]["from_state"] = "MUTATED"
        self.assertEqual(catalog, before)
        supplied = {"parameters": {"spec_selection": "EXACT_LANE_RUN_REF",
            "allowed_result_kind_versions": ["BDB_SCHEMA_REGISTRY::bdb_audit_lane_result/3"],
            "required_isolation_results": ["ENFORCED"], "output_bindings": []}}
        before = copy.deepcopy(supplied)
        body = builder.constant_profile(catalog["LANE_COMPLETION_V1"], supplied)
        body["parameters"]["required_isolation_results"] = ["DECLARED"]
        self.assertEqual(supplied, before)

    def test_complete_exact_raw_binding_set(self):
        files, root, report = builder.construct()
        bindings = files["objects/schema_registry__2.json"]["body"]["bindings"]
        self.assertEqual(len(bindings), 131)
        keys = [binding["schema_key"] for binding in bindings]
        self.assertEqual(keys, sorted(set(keys), key=lambda key: key.encode("utf-8")))
        expected = {entry["$id"]: entry for entry in report["entries"] if entry["file"].startswith("schemas/")}
        self.assertEqual(set(keys), set(expected))
        for binding in bindings:
            entry = expected[binding["schema_key"]]
            self.assertEqual(binding["schema_raw_ref"]["raw_digest"], digest(ROOT / report["directory"] / entry["file"]))
            self.assertEqual(binding["schema_raw_ref"]["byte_length"], entry["byte_length"])
        self.assertEqual(root["$id"], "BDB_SCHEMA_REGISTRY::schema_registry/2")

    def test_exact_profile_dispatch_not_inherited_fallback(self):
        files, _, _ = builder.construct()
        body = files["objects/schema_registry__2.json"]["body"]
        for field, name in (("serialization_profile_ref", "BDB_CJSON_1"),
                            ("validator_profile_ref", "QUALIFIED_VALIDATOR_V2"),
                            ("compatibility_rules_ref", "EXACT_COMPATIBILITY_V2")):
            self.assertEqual(body[field], builder.profile_ref(files["profiles/" + name + ".json"]))

    def test_stale_schema_input_rejects(self):
        original = builder.read

        def changed(path):
            value = original(path)
            if path == OUT / "BUILD_TIME_CANDIDATE_READBACK.json":
                value = copy.deepcopy(value)
                value["source_inputs"][0]["raw_digest"] = "0" * 64
            return value
        with patch.object(builder, "read", changed):
            with self.assertRaisesRegex(ValueError, "STALE_BUILD_CANDIDATE_INPUT"):
                builder.construct()

    def test_external_root_identity_substitution_rejects(self):
        original = builder.read

        def changed(path):
            value = original(path)
            if path == OUT / "BUILD_TIME_CANDIDATE_READBACK.json":
                value = copy.deepcopy(value)
                entry = next(entry for entry in value["entries"] if entry["$id"] == "BDB_SCHEMA_REGISTRY::schema_registry/2")
                entry["$id"] = "BDB_SCHEMA_REGISTRY::caller_schema/1"
            return value
        with patch.object(builder, "read", changed):
            with self.assertRaisesRegex(ValueError, "BUILD_CANDIDATE_SCHEMA_IDENTITY_DRIFT"):
                builder.construct()

    def test_profile_constant_substitution_rejects(self):
        contract = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")["EXACT_COMPATIBILITY_V2"]
        with self.assertRaisesRegex(ValueError, "PROFILE_CONSTANT_PARAMETER_CONFLICT"):
            builder.constant_profile(contract, {"writes": "ANY_OLD_CAMPAIGN"})

    def test_missing_validator_normalizer_rejects(self):
        contract = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")["QUALIFIED_VALIDATOR_V2"]
        with self.assertRaisesRegex(ValueError, "UNSUPPLIED_PROFILE_PARAMETER"):
            builder.constant_profile(contract)

    def test_undeclared_root_kind_rejects(self):
        with self.assertRaisesRegex(ValueError, "UNDECLARED_BUILD_ROOT_KIND"):
            builder.candidate_object("caller_authority", "1", {}, "0" * 64)


if __name__ == "__main__":
    unittest.main()

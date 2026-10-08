"""Exact protocol-root construction and substitution regressions."""
import copy
import unittest
from unittest.mock import patch

import initial_protocol_build_candidate as builder
from execution import OUT, read


class InitialProtocolBuildTests(unittest.TestCase):
    def test_complete_seven_profiles_and_exact_specification(self):
        files, reference, report = builder.construct()
        self.assertEqual(len(files), 8)
        self.assertEqual(reference["kind"], "spec_revision")
        entry = next(row for row in report["entries"] if row["$id"] == "BDB_SCHEMA_REGISTRY::spec_revision/2")
        self.assertEqual(reference["schema_revision_ref"]["revision_digest"], entry["raw_digest"])
        profiles = {body["profile_id"]: body for name, body in files.items() if name.startswith("profiles/")}
        self.assertEqual(len(profiles), 7)
        catalog = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
        for owner, fields in builder.SELECTIONS.items():
            body = profiles[catalog[owner].get("wire_profile_id", owner)]
            for field, target in fields.items():
                target_body = profiles[catalog[target].get("wire_profile_id", target)]
                self.assertEqual(body[field], builder.profile_ref(target_body))
        spec = files["objects/spec_revision__2.json"]["body"]
        self.assertEqual(spec["protocol_profile_ref"], builder.profile_ref(profiles["NF02_PROTOCOL_PROFILE_V3"]))
        self.assertEqual(spec["transition_contract_ref"], builder.profile_ref(profiles["FULL_PATH_TRANSITION_TABLE_V2"]))

    def test_actual_build_dependency_closure_and_substitutions(self):
        files, _, report = builder.construct()
        closure = builder.verify_files(files, report)
        self.assertEqual(closure["nodes"], 8)
        self.assertEqual(closure["topological_order"][-1], "spec_revision/2")
        for case in ("missing", "extra", "profile_pin", "object_pin", "schema_pin", "spec_dependency"):
            with self.subTest(case=case):
                altered = copy.deepcopy(files)
                obj = altered["objects/spec_revision__2.json"]
                if case == "missing":
                    altered.pop("profiles/NF02_RESULT_NORMALIZER_V2.json")
                elif case == "extra":
                    altered["profiles/UNDECLARED.json"] = {}
                elif case == "profile_pin":
                    altered["profiles/NF02_PROTOCOL_PROFILE_V3.json"]["normalizer_ref"]["revision_digest"] = "0" * 64
                elif case == "object_pin":
                    obj["ref"]["revision_digest"] = "0" * 64
                elif case == "schema_pin":
                    obj["ref"]["schema_revision_ref"]["revision_digest"] = "0" * 64
                else:
                    obj["body"]["protocol_profile_ref"]["revision_digest"] = "0" * 64
                    obj["ref"]["revision_digest"] = builder._domain_digest(
                        "spec_revision", "2", obj["body"], registry_kind="spec_revision")
                with self.assertRaisesRegex(ValueError, "INITIAL_"):
                    builder.verify_files(altered, report)

    def test_stale_build_source_rejects(self):
        original = builder.read
        def changed(path):
            value = original(path)
            if path == OUT / "BUILD_TIME_CANDIDATE_READBACK.json":
                value = copy.deepcopy(value)
                value["source_inputs"][0]["raw_digest"] = "0" * 64
            return value
        with patch.object(builder, "read", changed):
            with self.assertRaisesRegex(ValueError, "STALE_BUILD_INPUT"):
                builder.construct()

    def test_wrong_dependency_contract_rejects(self):
        original = builder.read
        def changed(path):
            value = original(path)
            if path == OUT / "design/PROFILE_REFERENCE_CONTRACTS.json":
                value = copy.deepcopy(value)
                row = next(row for row in value["material_refs"] if row["owner"] == "NF02_PROTOCOL_PROFILE_V2")
                row["same_commit"] = True
            return value
        with patch.object(builder, "read", changed):
            with self.assertRaisesRegex(ValueError, "REFERENCE_CONTRACT_MISMATCH"):
                builder.construct()


if __name__ == "__main__":
    unittest.main()

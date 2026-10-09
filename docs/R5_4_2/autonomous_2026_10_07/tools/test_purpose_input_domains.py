"""Closed purpose input views are syntax, not trusted evaluation proof."""
import copy
import unittest

from jsonschema import Draft202012Validator

from execution import OUT, read
from profile_design_audit import fixture
from purpose_input_domains import ROOTS, domain


class PurposeInputDomainTests(unittest.TestCase):
    def setUp(self):
        mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
        self.keys = sorted("BDB_SCHEMA_REGISTRY::" + key for key in mapping.values())

    def test_all_sixteen_closed_views_have_exact_registered_wire_targets(self):
        purposes = read(OUT / "design/PURPOSE_CONTRACT_GRAMMARS.json")
        self.assertEqual(set(ROOTS), set(purposes))
        for purpose in purposes:
            with self.subTest(purpose=purpose):
                view = domain(purpose, self.keys)
                schema = view["input_schema"]
                Draft202012Validator.check_schema(schema)
                body = fixture(schema, schema["$defs"])
                validator = Draft202012Validator(schema)
                self.assertTrue(validator.is_valid(body))
                self.assertFalse(validator.is_valid({**body, "trusted": True}))
                for row in view["canonical_inputs"]:
                    self.assertTrue(set(row["allowed_kind_versions"]) <= set(self.keys))
                    altered = copy.deepcopy(body)
                    altered["inputs"].pop(row["field"])
                    self.assertFalse(validator.is_valid(altered))
                self.assertIn("PENDING", view["status"])

    def test_exact_stage_identity_roots_cannot_be_empty_or_ambiguous(self):
        schema = domain("STAGE", self.keys)["input_schema"]
        body = fixture(schema, schema["$defs"])
        for field in ("stage_runs", "stage_specs", "inventory"):
            for count in (0, 2):
                altered = copy.deepcopy(body)
                original = altered["inputs"][field][0]
                altered["inputs"][field] = [copy.deepcopy(original) for _ in range(count)]
                if count == 2:
                    altered["inputs"][field][1]["revision_digest"] = "0" * 64
                self.assertFalse(Draft202012Validator(schema).is_valid(altered))

    def test_wrong_purpose_input_kind_cannot_enter_stage_run_field(self):
        view = domain("STAGE", self.keys)
        schema = view["input_schema"]
        body = fixture(schema, schema["$defs"])
        root = fixture(schema["$defs"]["typed_ref"], schema["$defs"])
        root["kind"] = "assignment_manifest"
        body["inputs"]["stage_runs"] = [root]
        self.assertFalse(Draft202012Validator(schema).is_valid(body))
        root["kind"] = "stage_run"
        self.assertTrue(Draft202012Validator(schema).is_valid(body))

    def test_empty_cut_is_not_an_ordinary_purpose_input(self):
        recovery = domain("RECOVERY", self.keys)["input_schema"]
        empty = fixture(recovery["$defs"]["empty_history_cut"], recovery["$defs"])
        for purpose in ROOTS:
            schema = domain(purpose, self.keys)["input_schema"]
            body = fixture(schema, schema["$defs"])
            body["input_history_cut"] = empty
            self.assertEqual(Draft202012Validator(schema).is_valid(body), purpose == "RECOVERY")

    def test_unknown_purpose_and_ambiguous_wire_version_reject(self):
        with self.assertRaisesRegex(ValueError, "UNKNOWN_PURPOSE_INPUT_DOMAIN"):
            domain("CALLER_CHECKER", self.keys)
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS_PURPOSE_INPUT_WIRE_VERSION"):
            domain("STAGE", self.keys + ["BDB_SCHEMA_REGISTRY::stage_run/999"])


if __name__ == "__main__":
    unittest.main()

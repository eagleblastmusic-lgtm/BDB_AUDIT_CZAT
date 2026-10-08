"""Normative draft must preserve exact inputs and select explicit successors."""

import copy
import unittest

from execution import BASE, OUT, read
from normative_build_candidate import INHERITED, active_reference_contracts, construct, exact_report_file


class NormativeBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files, cls.inherited = construct()
        cls.mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
        cls.catalog = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")

    def test_exact_eight_markdown_plus_registry_and_golden(self):
        self.assertEqual(len(self.files), 10)
        self.assertEqual(sum(name.endswith(".md") for name in self.files), 8)

    def test_unchanged_inherited_normative_bytes(self):
        self.assertEqual(set(self.inherited), INHERITED)
        for name in self.inherited:
            self.assertEqual(self.files[name], (BASE / "candidate" / name).read_bytes())

    def test_changed_wire_versions_are_explicit(self):
        references = [{"field": "manifest", "allowed_keys": ["source_manifest/1"],
                       "profile_contracts": ["SOURCE_IDENTITY_V2"]}]
        original = copy.deepcopy(references)
        active = active_reference_contracts(references, self.mapping, self.catalog)
        self.assertEqual(active[0]["allowed_keys"], ["source_manifest/2"])
        self.assertEqual(active[0]["profile_contracts"], ["SOURCE_IDENTITY_V3"])
        self.assertEqual(references, original)

    def test_unregistered_target_cannot_become_active(self):
        with self.assertRaisesRegex(ValueError, "NORMATIVE_REFERENCE_TARGET_NOT_IN_ACTIVE_CLOSURE"):
            active_reference_contracts([{"allowed_keys": ["unknown/1"]}], self.mapping, self.catalog)

    def test_unqualified_profile_alias_has_no_fallback(self):
        with self.assertRaisesRegex(ValueError, "NORMATIVE_REFERENCE_PROFILE_NOT_DECLARED"):
            active_reference_contracts([{"profile_contracts": ["undeclared"]}], self.mapping, self.catalog)

    def test_registry_and_golden_bytes_equal_separate_readback(self):
        registry = read(OUT / "REGISTRY_BUILD_CANDIDATE_READBACK.json")
        golden = read(OUT / "GOLDEN_BUILD_CANDIDATE_READBACK.json")
        from execution import ROOT
        self.assertEqual(self.files["BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4_2.json"],
                         exact_report_file(registry, OUT).read_bytes())
        self.assertEqual(self.files["BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4_2.json"],
                         exact_report_file(golden, ROOT).read_bytes())

    def test_changed_source_raw_pin_is_rejected(self):
        report = read(OUT / "REGISTRY_BUILD_CANDIDATE_READBACK.json")
        report["raw_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "NORMATIVE_BUILD_SOURCE_RAW_DRIFT"):
            exact_report_file(report, OUT)


if __name__ == "__main__":
    unittest.main()

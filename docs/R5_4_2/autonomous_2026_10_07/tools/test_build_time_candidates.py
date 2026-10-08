"""Build candidate closure/readback regressions; no qualification claims."""

import copy
import unittest
import uuid

from build_time_candidates import descriptors, verify_readback
from execution import ROOT, canonical


class BuildCandidateTests(unittest.TestCase):
    def setUp(self):
        self.directory = ROOT / "._nf02_current_audit" / "build_candidate_controls" / str(uuid.uuid4())
        self.directory.mkdir(parents=True)
        self.files = {"schemas/test.schema.json": {"$id": "BDB_SCHEMA_REGISTRY::test/1",
                      "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}}
        self.entries = descriptors(self.files)
        self.path = self.directory / "schemas/test.schema.json"
        self.path.parent.mkdir()
        self.path.write_bytes(canonical(self.files["schemas/test.schema.json"]) + b"\n")

    def test_exact_readback(self):
        self.assertEqual(verify_readback(self.directory, self.entries), 1)

    def test_raw_substitution(self):
        self.path.write_bytes(self.path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "BUILD_CANDIDATE_RAW_DRIFT"):
            verify_readback(self.directory, self.entries)

    def test_missing_schema(self):
        changed = copy.deepcopy(self.entries)
        changed[0]["file"] = "schemas/missing.schema.json"
        with self.assertRaisesRegex(ValueError, "BUILD_CANDIDATE_INVENTORY_DRIFT"):
            verify_readback(self.directory, changed)

    def test_extra_unbound_schema(self):
        (self.directory / "extra.json").write_bytes(b"{}\n")
        with self.assertRaisesRegex(ValueError, "BUILD_CANDIDATE_INVENTORY_DRIFT"):
            verify_readback(self.directory, self.entries)

    def test_duplicate_manifest_entry(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_BUILD_CANDIDATE_ENTRY"):
            verify_readback(self.directory, self.entries * 2)

    def test_schema_identity_substitution(self):
        changed = copy.deepcopy(self.entries)
        changed[0]["$id"] = "BDB_SCHEMA_REGISTRY::wrong/1"
        with self.assertRaisesRegex(ValueError, "BUILD_CANDIDATE_SCHEMA_IDENTITY_DRIFT"):
            verify_readback(self.directory, changed)

    def test_missing_offline_dependency(self):
        changed = copy.deepcopy(self.files)
        changed["schemas/test.schema.json"]["$ref"] = "BDB_SCHEMA_REGISTRY::missing/1"
        with self.assertRaisesRegex(ValueError, "UNBOUND_OFFLINE_SCHEMA_DEPENDENCY"):
            descriptors(changed)

    def test_transitive_dependency_closure_and_cycle(self):
        files = {name + ".json": {"$id": name, "$schema": self.files["schemas/test.schema.json"]["$schema"],
                 "$ref": reference} for name, reference in (("A", "B"), ("B", "C"), ("C", "B"))}
        result = descriptors(files)
        self.assertEqual([item["$id"] for item in result[0]["dependency_closure"]], ["B", "C"])
        self.assertEqual([item["$id"] for item in result[1]["dependency_closure"]], ["B", "C"])
        files["C.json"]["description"] = "different retained dependency bytes"
        changed = descriptors(files)
        self.assertNotEqual(result[0]["dependency_closure"], changed[0]["dependency_closure"])


if __name__ == "__main__":
    unittest.main()

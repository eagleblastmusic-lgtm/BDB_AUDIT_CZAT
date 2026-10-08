"""Adversarial regression controls for exact fixture evidence bindings."""

from __future__ import annotations

import copy
import unittest

from referencing import Registry, Resource

from build_schema_fixtures import replay


class FixtureEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "BDB_TEST::root",
                       "type": "object", "properties": {"required": {"type": "integer"}},
                       "required": ["required"], "additionalProperties": False}
        self.entry = {"$id": self.schema["$id"], "raw_digest": "a" * 64, "dependency_closure": []}
        self.vector = {"id": "test", "schema_id": self.schema["$id"], "schema_raw_digest": "a" * 64,
                       "dependency_closure": [], "input": {"required": 1}, "expected": "ACCEPT"}
        self.registry = Registry()

    def test_positive_and_truthful_negative(self):
        replay(self.vector, self.schema, self.entry, self.registry)
        self.vector.update(input={}, expected="REJECT")
        replay(self.vector, self.schema, self.entry, self.registry)

    def test_inverted_known_answer_is_rejected(self):
        self.vector["expected"] = "REJECT"
        with self.assertRaisesRegex(ValueError, "BUILD_SCHEMA_FIXTURE_MISMATCH"):
            replay(self.vector, self.schema, self.entry, self.registry)

    def test_stale_schema_pin_is_rejected(self):
        self.vector["schema_raw_digest"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "FIXTURE_SCHEMA_BINDING_DRIFT"):
            replay(self.vector, self.schema, self.entry, self.registry)

    def test_stale_transitive_dependency_is_rejected(self):
        self.entry["dependency_closure"] = [{"$id": "BDB_TEST::dependency", "raw_digest": "c" * 64}]
        self.vector["dependency_closure"] = copy.deepcopy(self.entry["dependency_closure"])
        self.vector["dependency_closure"][0]["raw_digest"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "FIXTURE_DEPENDENCY_BINDING_DRIFT"):
            replay(self.vector, self.schema, self.entry, self.registry)

    def test_unrecognized_expectation_cannot_become_rejection(self):
        self.vector["expected"] = "UNKNOWN"
        with self.assertRaisesRegex(ValueError, "FIXTURE_EXPECTATION_UNKNOWN"):
            replay(self.vector, self.schema, self.entry, self.registry)

    def test_missing_offline_dependency_has_no_fallback(self):
        dependency = {"$schema": self.schema["$schema"], "$id": "BDB_TEST::dependency", "const": 1}
        schema = {"$schema": self.schema["$schema"], "$id": self.schema["$id"], "$ref": dependency["$id"]}
        self.vector["input"] = 1
        registry = Registry().with_resource(dependency["$id"], Resource.from_contents(dependency))
        replay(self.vector, schema, self.entry, registry)
        from referencing.exceptions import Unresolvable
        with self.assertRaises(Unresolvable):
            replay(self.vector, schema, self.entry, self.registry)


if __name__ == "__main__":
    unittest.main()

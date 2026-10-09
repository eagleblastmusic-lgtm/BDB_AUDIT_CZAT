"""Reject Golden expectation changes, lost inputs and fabricated qualification."""

import copy
import unittest

from golden_build_candidate import construct, verify_structure


class GoldenBuildTests(unittest.TestCase):
    def setUp(self):
        self.predecessor = {"vectors": [{"id": "OLD", "input": {"a": 1}, "expected": {"x": "REJECT"}}]}
        self.fixtures = {"schema_build_digest": "b" * 64, "vectors": [
            {"id": "fixture", "schema_id": "BDB_SCHEMA_REGISTRY::example/2", "schema_raw_digest": "a" * 64,
             "dependency_closure": [], "input": {"a": 1}, "expected": "ACCEPT", "expectation_basis": "SCHEMA_ONLY"}]}
        self.report = {"vectors_replayed": 1, "schema_build_digest": "b" * 64, "raw_digest": "c" * 64}
        self.body = construct(self.predecessor, self.fixtures, self.report, [], {})

    def check(self):
        verify_structure(self.body, self.predecessor, self.fixtures, self.report)

    def test_exact_inheritance_and_raw_bound_fixture(self):
        self.check()
        self.assertEqual(self.body["vectors"][0], self.predecessor["vectors"][0])

    def test_inherited_negative_cannot_become_positive(self):
        self.body["vectors"][0]["expected"]["x"] = "ACCEPT"
        with self.assertRaisesRegex(ValueError, "INHERITED_GOLDEN_EXPECTATIONS_CHANGED"):
            self.check()

    def test_favorable_subset_is_rejected(self):
        self.body["vectors"].pop()
        with self.assertRaisesRegex(ValueError, "GOLDEN_FIXTURE_OMISSION"):
            self.check()

    def test_input_swap_with_old_expectation_is_rejected(self):
        self.fixtures["vectors"][0]["input"]["a"] = 2
        with self.assertRaisesRegex(ValueError, "GOLDEN_FIXTURE_INPUT_DRIFT"):
            self.check()

    def test_individual_expectation_flip_is_rejected(self):
        self.body["vectors"][1]["expected"]["schema_result"] = "REJECT"
        with self.assertRaisesRegex(ValueError, "GOLDEN_FIXTURE_EXPECTATION_DRIFT"):
            self.check()

    def test_draft_syntax_cannot_become_qualification(self):
        self.body["qualification"] = True
        with self.assertRaisesRegex(ValueError, "GOLDEN_BUILD_QUALIFICATION_LAUNDERING"):
            self.check()

    def test_unregistered_canonical_design_target_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "GOLDEN_DESIGN_TARGET_NOT_IN_ACTIVE_CLOSURE"):
            construct(self.predecessor, self.fixtures, self.report, [{"id": "attack", "kind": "unknown/1"}], {})

    def test_duplicate_fixture_denominator_is_rejected(self):
        self.fixtures["vectors"].append(copy.deepcopy(self.fixtures["vectors"][0]))
        self.report["vectors_replayed"] = 2
        with self.assertRaisesRegex(ValueError, "BUILD_GOLDEN_FIXTURE_DENOMINATOR_DRIFT"):
            construct(self.predecessor, self.fixtures, self.report, [], {})


if __name__ == "__main__":
    unittest.main()

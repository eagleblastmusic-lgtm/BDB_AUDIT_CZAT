"""Exact source selection and finite Registry-build parity controls."""

import copy
import unittest
from unittest.mock import patch

import registry_build_candidate as builder
from execution import OUT, read
from semantic_inventory import approved_specific_row


class RegistryBuildTests(unittest.TestCase):
    def test_residual_exact_approved_row(self):
        selected = approved_specific_row("residual_risk/1")
        self.assertEqual(selected["row"]["validation_profile"], "EPISTEMIC")
        self.assertEqual(selected["row"]["required_validation_layers"], ["L3", "L4", "L5", "L6"])
        registry, pending = builder.construct()
        self.assertEqual(pending, [])
        row = next(row for row in registry["contracts"] if row["kind"] == "residual_risk")
        self.assertEqual(row["validation_profile"], "EPISTEMIC")
        self.assertEqual(row["required_validation_layers"], selected["row"]["required_validation_layers"])

    def test_complete_finite_successor_keys(self):
        registry, _ = builder.construct()
        mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
        self.assertEqual({row["schema_ref"] for row in registry["contracts"]},
                         {"BDB_SCHEMA_REGISTRY::" + key for key in mapping.values()})
        self.assertEqual(len(registry["contracts"]), len(mapping))

    def test_raw_producer_requirements_retained(self):
        registry, _ = builder.construct()
        row = next(row for row in registry["contracts"] if row["kind"] == "surface_collector_record")
        self.assertEqual(row["producer_authority"], "TRUSTED_COORDINATOR_ACCEPTANCE")
        self.assertIn("independently verified producer/context/raw derivation", row["producer_authority_requirements"])

    def mutated_read(self, file, mutate):
        original = builder.read

        def changed(path):
            value = original(path)
            if path == OUT / file:
                value = copy.deepcopy(value)
                mutate(value)
            return value
        return patch.object(builder, "read", changed)

    def test_review_queue_is_not_a_registry_build_authority(self):
        report = read(OUT / "REGISTRY_BUILD_CANDIDATE_READBACK.json")
        expected = read(OUT / report["file"])
        original = builder.read
        def without_queue(path):
            if path == OUT / "design/SEMANTIC_OBLIGATION_QUEUE.json":
                raise AssertionError("Review metadata must not enter Registry construction")
            return original(path)
        with patch.object(builder, "read", without_queue):
            actual, pending = builder.construct()
        self.assertEqual(pending, [])
        self.assertEqual(actual, expected)

    def test_duplicate_successor_key_rejected(self):
        def mutate(value):
            value["mapping"]["approval_decision/1"] = value["mapping"]["attempt/1"]
        with self.mutated_read("design/VERSION_IMPACT_PLAN.json", mutate):
            with self.assertRaisesRegex(ValueError, "SUCCESSOR_REGISTRY_KEY_PARITY"):
                builder.construct()

    def test_unknown_reference_class_rejected(self):
        def mutate(value):
            value["nodes"][0]["resolved_own_material_refs"][0]["ref_class"] = "CALLER_AUTHORIZED"
        with self.mutated_read("OWN_REFERENCE_RESOLUTIONS.json", mutate):
            with self.assertRaisesRegex(ValueError, "UNDECLARED_REFERENCE_CLASS"):
                builder.construct()

    def test_wrong_generic_residual_label_is_not_authority(self):
        def mutate(value):
            node = next(node for node in value["nodes"] if node["key"] == "residual_risk/1")
            node["historical_proposal"]["validation_profile"] = "STRUCTURAL"
            node["historical_proposal"]["validation_layers"] = ["L3"]
        with self.mutated_read("OWN_REFERENCE_RESOLUTIONS.json", mutate):
            registry, pending = builder.construct()
        self.assertEqual(pending, [])
        row = next(row for row in registry["contracts"] if row["kind"] == "residual_risk")
        self.assertEqual(row["validation_profile"], "EPISTEMIC")
        self.assertEqual(row["required_validation_layers"], ["L3", "L4", "L5", "L6"])


if __name__ == "__main__":
    unittest.main()

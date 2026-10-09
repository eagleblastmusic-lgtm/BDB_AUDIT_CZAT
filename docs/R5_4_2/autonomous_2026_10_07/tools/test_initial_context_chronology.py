"""Regression for the installed initial-context reference classification.

These controls do not confer trust or qualification on a profile instance.
"""
import copy
import unittest

from execution import OUT, read
from profile_reference_contracts import decisions


def check_initial_context(contracts, table):
    profile = contracts["FULL_PATH_CONTEXT_PARAMETERS_V1"]
    if profile.get("wire_profile_id") != "FULL_PATH_CONTEXT_PARAMETERS_V2":
        raise ValueError("INITIAL_CONTEXT_WIRE_ID")
    rule = table["FULL_PATH_CONTEXT_PARAMETERS_V1", "entries[].governing_spec_ref"]
    if (rule["representation"], rule["targets"], rule["ref_class"], rule["same_commit"]) != (
            "TypedRef", ["spec_revision"], "PINNED_INSTALLATION_REF", False):
        raise ValueError("INITIAL_CONTEXT_PREGENESIS_DEPENDENCY")
    for key in (("MANDATORY_STAGE_SET_V2", "stage_spec_refs[]"),
                ("QUALIFIED_TECHNIQUE_V2", "required_control_experiment_refs[]")):
        if table[key]["ref_class"] != "PRIOR_ACCEPTED_ONLY" or table[key]["same_commit"]:
            raise ValueError("ORDINARY_PRIOR_REFERENCE_WEAKENED")


class InitialContextChronologyTests(unittest.TestCase):
    def setUp(self):
        self.contracts = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
        self.table = decisions(self.contracts)

    def test_installed_initial_context_and_ordinary_prior_refs(self):
        check_initial_context(self.contracts, self.table)

    def test_predecessor_prior_requirement_cannot_bootstrap_empty_history(self):
        table = copy.deepcopy(self.table)
        table["FULL_PATH_CONTEXT_PARAMETERS_V1", "entries[].governing_spec_ref"]["ref_class"] = "PRIOR_ACCEPTED_ONLY"
        with self.assertRaisesRegex(ValueError, "PREGENESIS_DEPENDENCY"):
            check_initial_context(self.contracts, table)

    def test_same_commit_or_wrong_target_cannot_replace_independent_pin(self):
        for field, value in (("same_commit", True), ("targets", ["stage_spec"]),
                             ("representation", "ExternalProfileRef")):
            with self.subTest(field=field):
                table = copy.deepcopy(self.table)
                table["FULL_PATH_CONTEXT_PARAMETERS_V1", "entries[].governing_spec_ref"][field] = value
                with self.assertRaisesRegex(ValueError, "PREGENESIS_DEPENDENCY"):
                    check_initial_context(self.contracts, table)

    def test_ordinary_prior_reference_waiver_rejects(self):
        table = copy.deepcopy(self.table)
        table["MANDATORY_STAGE_SET_V2", "stage_spec_refs[]"]["ref_class"] = "PINNED_INSTALLATION_REF"
        with self.assertRaisesRegex(ValueError, "ORDINARY_PRIOR_REFERENCE_WEAKENED"):
            check_initial_context(self.contracts, table)

    def test_spec_initialization_agrees_with_successor_registry_precedence(self):
        schema = read(OUT / "design/body_grammars/spec_revision__2.json")
        self.assertEqual(schema["properties"]["initialization"]["const"],
                         "INITIALIZE_CAMPAIGN_FROM_LEGACY; EMPTY_HISTORY; one union-Kahn; BDB_BOOTSTRAP_PRECEDENCE_V2 exact scope only")
        delta = read(OUT / "design/REGISTRY_BOOTSTRAP_SUCCESSOR_DELTA.json")
        self.assertIn("BDB_BOOTSTRAP_PRECEDENCE_V2",
                      delta["replacement_fragments"]["order_only_precedence_profiles"])

    def test_old_wire_identity_rejects(self):
        contracts = copy.deepcopy(self.contracts)
        contracts["FULL_PATH_CONTEXT_PARAMETERS_V1"]["wire_profile_id"] = "FULL_PATH_CONTEXT_PARAMETERS_V1"
        with self.assertRaisesRegex(ValueError, "INITIAL_CONTEXT_WIRE_ID"):
            check_initial_context(contracts, self.table)


if __name__ == "__main__":
    unittest.main()

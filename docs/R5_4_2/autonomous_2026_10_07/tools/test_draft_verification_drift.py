"""Real input mutations must be visible to the draft verification snapshot."""

import unittest
import uuid
from unittest.mock import patch

import verify_design
from execution import OUT


class DraftVerificationDriftTests(unittest.TestCase):
    def setUp(self):
        self.root = OUT / "test_draft_verification_drift" / uuid.uuid4().hex
        self.tools = self.root / "tools"
        self.tools.mkdir(parents=True)
        (self.root / "docs/R5_4_2").mkdir(parents=True)
        (self.root / "docs/R5_4_2/OWNER_DELEGATED_DECISION_REGISTER.md").write_bytes(b"owner")
        for directory in ("src", "build", "tests"):
            (self.root / directory).mkdir()
        self.patches = [patch.object(verify_design, "ROOT", self.root), patch.object(verify_design, "OUT", self.root)]
        for context in self.patches:
            context.start()
        self.addCleanup(lambda: [context.stop() for context in reversed(self.patches)])

    def test_tool_mutation_changes_actual_pin(self):
        path = self.tools / "verifier.py"
        path.write_bytes(b"original")
        before = verify_design.verification_inputs()
        path.write_bytes(b"modified")
        self.assertNotEqual(before["tools/verifier.py"], verify_design.verification_inputs()["tools/verifier.py"])

    def test_new_import_or_fixture_is_inventory_drift(self):
        before = verify_design.verification_inputs()
        for name in ("src/new_dependency.py", "tests/fixture.json", "build/resource.bin"):
            (self.root / name).write_bytes(b"new")
        self.assertEqual(set(verify_design.verification_inputs()) - set(before),
                         {"src/new_dependency.py", "tests/fixture.json", "build/resource.bin"})

    def test_actual_semantic_model_mutation_is_bound(self):
        for name in ("OWN_REFERENCE_RESOLUTIONS.json", "design/EXTERNAL_PROFILE_CONTRACTS.json",
                     "design/body_grammars/spec_revision__2.json"):
            with self.subTest(name=name):
                path = self.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"original")
                before = verify_design.verification_inputs()
                path.write_bytes(b"modified")
                self.assertNotEqual(before[name], verify_design.verification_inputs()[name])

    def test_body_schema_addition_and_removal_change_inventory(self):
        directory = self.root / "design/body_grammars"
        directory.mkdir(parents=True)
        before = verify_design.verification_inputs()
        path = directory / "new_contract__1.json"
        path.write_bytes(b"new")
        after = verify_design.verification_inputs()
        self.assertEqual(set(after) - set(before), {"design/body_grammars/new_contract__1.json"})
        path.unlink()
        self.assertEqual(verify_design.verification_inputs(), before)

    def test_missing_dependency_cannot_keep_old_snapshot(self):
        path = self.root / "tests/fixture.json"
        path.write_bytes(b"retained")
        before = verify_design.verification_inputs()
        path.unlink()
        self.assertEqual(set(before) - set(verify_design.verification_inputs()), {"tests/fixture.json"})


if __name__ == "__main__":
    unittest.main()

"""Regression controls for preservation and invalidation of review evidence."""

import copy
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

import semantic_obligation_queue as queue
from execution import ROOT, digest
from semantic_obligation_queue import retain_review


class ReviewRetentionTests(unittest.TestCase):
    def test_named_section_keeps_nested_dependencies_and_stops_at_peer(self):
        text = "## Start\nbody\n### Nested\ndependency\n## Next\nunrelated"
        self.assertEqual(queue.named_section(text, "## Start"), "## Start\nbody\n### Nested\ndependency")
        with self.assertRaises(AssertionError):
            queue.named_section(text, "## Missing")

    def test_all_approved_proposals_retain_bound_nonempty_prose(self):
        graph = queue.read(queue.OUT / "OWN_REFERENCE_RESOLUTIONS.json")
        keys = [node["key"] for node in graph["nodes"] if not node.get("source_section")]
        self.assertEqual(len(keys), 21)
        for key in keys:
            sources, approval = queue.proposal_sources(key)
            self.assertTrue(sources, key)
            self.assertIn("materialization", approval["scope"])
            for source in sources:
                self.assertEqual(digest(ROOT / source["file"]), source["raw_digest"])
                self.assertTrue(source["complete_section_text"].strip(), key)

    def setUp(self):
        self.current = {"review_input_digest": "current", "review": "PENDING",
                        "source_paragraphs": [{"paragraph_ordinal": 0, "text_sha256": "text", "review": "PENDING"}]}
        self.previous = copy.deepcopy(self.current)
        self.proof = {"file": "docs/R5_4_2/autonomous_2026_10_07/tools/test_semantic_queue_retention.py",
                      "raw_digest": digest(Path(__file__))}
        self.previous.update(review="SEMANTIC_PARITY_REVIEWED", review_evidence=[self.proof])
        self.previous["source_paragraphs"][0].update(review="REVIEWED", review_notes="exact source")

    def test_unchanged_inputs_retain_review_without_aliasing(self):
        result = retain_review(self.current, self.previous)
        self.assertEqual(result["review"], "SEMANTIC_PARITY_REVIEWED")
        self.assertEqual(result["source_paragraphs"][0]["review"], "REVIEWED")
        result["review_evidence"].append("new")
        self.assertEqual(self.previous["review_evidence"], [self.proof])

    def test_changed_dependency_invalidates_node_and_paragraph(self):
        self.current["review_input_digest"] = "changed"
        result = retain_review(self.current, self.previous)
        self.assertEqual(result["review"], "PENDING")
        self.assertEqual(result["source_paragraphs"][0]["review"], "PENDING")
        self.assertEqual(result["invalidated_review"]["review_evidence"], [self.proof])
        self.assertEqual(result["invalidated_review"]["source_paragraphs"][0]["review"], "REVIEWED")

    def test_unbound_old_review_is_not_promoted(self):
        del self.previous["review_input_digest"]
        self.assertEqual(retain_review(self.current, self.previous)["review"], "PENDING")

    def test_changed_paragraph_cannot_inherit_status(self):
        self.current["source_paragraphs"][0]["text_sha256"] = "changed"
        self.assertEqual(retain_review(self.current, self.previous)["source_paragraphs"][0]["review"], "PENDING")

    def test_invalidation_history_survives_next_regeneration(self):
        self.current["review_input_digest"] = "changed"
        result = retain_review(self.current, self.previous)
        regenerated = retain_review(copy.deepcopy(self.current), result)
        self.assertEqual(regenerated["invalidated_review"], result["invalidated_review"])

    def test_changed_exact_evidence_invalidates_unchanged_model(self):
        self.previous["review_evidence"][0]["raw_digest"] = "0" * 64
        self.assertEqual(retain_review(self.current, self.previous)["review"], "PENDING")

    def test_missing_or_unstructured_evidence_cannot_retain_review(self):
        for proofs in ([], ["unbound-claim"], [{"file": "missing-proof", "raw_digest": "0" * 64}]):
            previous = copy.deepcopy(self.previous)
            previous["review_evidence"] = proofs
            self.assertEqual(retain_review(copy.deepcopy(self.current), previous)["review"], "PENDING")

    def test_new_diagnostics_do_not_hide_real_implementation_drift(self):
        root = ROOT / "._nf02_current_audit/data" / ("review-inputs-" + uuid.uuid4().hex)
        (root / "src").mkdir(parents=True)
        source = root / "src/subject.py"
        source.write_bytes(b"before")
        def fixture_digest(path):
            return hashlib.sha256(path.read_bytes() if path.is_file() else str(path).encode()).hexdigest()
        with patch.object(queue, "ROOT", root), patch.object(queue, "OUT", root), patch.object(queue, "digest", fixture_digest):
            before = queue.review_dependencies()
            run = root / "design/source_instance_readback/runtime_runs/new.json"
            run.parent.mkdir(parents=True)
            run.write_bytes(b"new diagnostic")
            self.assertEqual(queue.review_dependencies(), before)
            source.write_bytes(b"after")
            self.assertNotEqual(queue.review_dependencies(), before)

    def test_common_body_semantics_document_is_a_review_dependency(self):
        root = ROOT / "._nf02_current_audit/data" / ("review-semantics-" + uuid.uuid4().hex)
        document = root / "design/COMMON_BODY_GRAMMARS.md"
        document.parent.mkdir(parents=True)
        document.write_bytes(b"before")
        def fixture_digest(path):
            return hashlib.sha256(path.read_bytes() if path.is_file() else str(path).encode()).hexdigest()
        with patch.object(queue, "ROOT", root), patch.object(queue, "OUT", root), patch.object(queue, "digest", fixture_digest):
            before = queue.review_dependencies()
            document.write_bytes(b"changed semantics with identical code")
            self.assertNotEqual(queue.review_dependencies(), before)


if __name__ == "__main__":
    unittest.main()

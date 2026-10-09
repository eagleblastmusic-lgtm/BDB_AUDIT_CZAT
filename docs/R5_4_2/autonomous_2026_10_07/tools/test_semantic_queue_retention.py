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
                      "raw_digest": digest(Path(__file__)),
                      "inputs": {"docs/R5_4_2/autonomous_2026_10_07/tools/test_semantic_queue_retention.py": digest(Path(__file__))}}
        self.proof["inputs"].update({name: digest(ROOT / name) for name in queue.SHARED_RUNTIME_INPUTS if (ROOT / name).is_file()})
        self.proof["inputs"].update(queue.local_python_input_closure(self.proof["inputs"]))
        self.previous.update(review="SEMANTIC_PARITY_REVIEWED", review_evidence=[self.proof])
        self.previous["source_paragraphs"][0].update(review="REVIEWED", review_notes="exact source")

    def test_fixed_point_requires_complete_bound_closure(self):
        rows = []
        for index in range(131):
            row = copy.deepcopy(self.previous)
            row.update(source_key=str(index), review_dimensions=["producer_authority"],
                       dimension_reviews={"producer_authority": {"verdict": "PASS", "source_reason": "exact source"}})
            rows.append(row)
        closure = {name: {"verdict": "PASS", "review_evidence": [copy.deepcopy(self.proof)],
                          "review_input_digests": {row["source_key"]: row["review_input_digest"] for row in rows}}
                   for name in ("graph_complete", "conditional_obligations_closed", "schemas_bound",
                                "fixtures_bound", "zero_input_drift", "no_material_contradictions")}
        self.assertFalse(queue.fixed_point_status(rows, closure)["reached"])
        self.assertTrue(queue.fixed_point_status(rows, closure, required_obligations=[])["reached"])
        with patch.object(queue, "evidence_is_bound", side_effect=[True, False]):
            drifted = queue.fixed_point_status(rows, closure, required_obligations=[])
        self.assertIn("EVIDENCE_INPUT_DRIFT_DURING_FIXED_POINT", drifted["failures"])
        obligation = {"owner": "0", "field": "required_ref", "declared": "1 per branch"}
        obligation_id = hashlib.sha256(queue.canonical(obligation)).hexdigest()
        self.assertFalse(queue.fixed_point_status(rows, closure, required_obligations=[obligation])["reached"])
        disposition = {"id": obligation_id, "owner": "0", "review_input_digest": "current",
                       "disposition": "CLOSED", "source_reason": "Exact conditional source and executed witness",
                       "review_evidence": [copy.deepcopy(self.proof)]}
        closure["conditional_obligations_closed"]["obligations"] = [disposition]
        self.assertTrue(queue.fixed_point_status(rows, closure, required_obligations=[obligation])["reached"])
        for field, value in (("disposition", "CLOSED_LOCAL_BRANCH_CARDINALITY"),
                             ("source_reason", ""), ("review_input_digest", "stale"),
                             ("owner", "unknown"), ("review_evidence", [])):
            changed = copy.deepcopy(closure)
            changed["conditional_obligations_closed"]["obligations"][0][field] = value
            self.assertFalse(queue.fixed_point_status(rows, changed, required_obligations=[obligation])["reached"])
        duplicate = copy.deepcopy(closure)
        duplicate["conditional_obligations_closed"]["obligations"].append(copy.deepcopy(disposition))
        self.assertFalse(queue.fixed_point_status(rows, duplicate, required_obligations=[obligation])["reached"])
        self.assertFalse(queue.fixed_point_status(rows, closure, {"wrong/1"}, [obligation])["reached"])
        stale = copy.deepcopy(closure)
        stale["zero_input_drift"]["review_input_digests"]["0"] = "stale"
        self.assertFalse(queue.fixed_point_status(rows, stale, required_obligations=[obligation])["reached"])
        self.assertFalse(queue.fixed_point_status(rows, {}, required_obligations=[obligation])["reached"])
        self.assertFalse(queue.fixed_point_status(rows[:-1], closure, required_obligations=[obligation])["reached"])
        closure["schemas_bound"]["review_evidence"][0]["raw_digest"] = "0" * 64
        self.assertFalse(queue.fixed_point_status(rows, closure, required_obligations=[obligation])["reached"])

    def test_conditional_inventory_cannot_omit_graph_obligations(self):
        graph = {"nodes": [{"key": "subject/1", "resolved_own_material_refs": [
            {"field": "branch.ref", "cardinality": "1 per branch"},
            {"field": "ordinary_ref", "cardinality": "1"}]}]}
        mapping = {"subject/1": "subject/2"}
        declared = [{"owner": "subject/1", "design_key": "subject/2", "field": "branch.ref",
                     "declared": "1 per branch", "status": "REQUIRES_EXPLICIT_CONDITION_OR_SEMANTIC_PREDICATE"}]
        self.assertEqual(queue.conditional_inventory(graph, mapping, declared), declared)
        for wrong in ([], declared + declared, [{**declared[0], "field": "unknown"}]):
            with self.assertRaisesRegex(ValueError, "CONDITIONAL_INVENTORY_GRAPH_MISMATCH"):
                queue.conditional_inventory(graph, mapping, wrong)

    def test_fixed_point_rejects_pending_paragraph_and_unjustified_na(self):
        row = copy.deepcopy(self.previous)
        row.update(source_key="test/1", review_dimensions=["producer_authority"],
                   dimension_reviews={"producer_authority": {"verdict": "NOT_APPLICABLE"}})
        failures = queue.fixed_point_status([row], {})["failures"]
        self.assertIn("INCOMPLETE_DIMENSIONS:test/1", failures)
        row["source_paragraphs"][0]["review"] = "PENDING"
        self.assertIn("PENDING_PARAGRAPHS:test/1", queue.fixed_point_status([row], {})["failures"])

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

    def test_nested_dimension_or_paragraph_evidence_invalidates_full_review(self):
        for scope in ("dimension", "paragraph"):
            previous = copy.deepcopy(self.previous)
            evidence = copy.deepcopy(self.proof)
            evidence["raw_digest"] = "0" * 64
            if scope == "dimension":
                previous["dimension_reviews"] = {"cut_visibility": {"verdict": "PASS", "source_reason": "exact source",
                                                                    "review_evidence": [evidence]}}
            else:
                previous["source_paragraphs"][0]["review_evidence"] = [evidence]
            with self.subTest(scope=scope):
                self.assertFalse(queue.evidence_is_bound(previous))
                self.assertEqual(retain_review(copy.deepcopy(self.current), previous)["review"], "PENDING")

    def test_bound_partial_dimension_survives_other_review_dependency_change(self):
        previous = copy.deepcopy(self.previous)
        previous["review"] = "PENDING"
        dimension = {"verdict": "PARTIAL_WITH_EVIDENCE", "source_reason": "Pure exact-byte witness; consumer applicability remains open",
                     "review_evidence": [copy.deepcopy(self.proof)]}
        previous["dimension_reviews"] = {"raw_derivation": dimension}
        current = copy.deepcopy(self.current) | {"review_input_digest": "changed consumer context"}
        result = retain_review(copy.deepcopy(current), previous)
        self.assertEqual(result["review"], "PENDING")
        self.assertEqual(result.get("dimension_reviews", {}).get("raw_derivation", {}).get("review_evidence"), dimension["review_evidence"])
        for change in ("proof", "input", "malformed_inputs", "full_verdict"):
            altered = copy.deepcopy(previous)
            item = altered["dimension_reviews"]["raw_derivation"]
            if change == "proof":
                item["review_evidence"][0]["raw_digest"] = "0" * 64
            elif change == "input":
                item["review_evidence"][0]["inputs"][self.proof["file"]] = "0" * 64
            elif change == "malformed_inputs":
                item["review_evidence"][0]["inputs"] = "unbound-inputs"
            else:
                item["verdict"] = "PASS"
            with self.subTest(change=change):
                self.assertNotIn("raw_derivation", retain_review(copy.deepcopy(current), altered).get("dimension_reviews", {}))

    def test_fixed_point_cannot_ignore_nested_proof_input_drift(self):
        rows = [copy.deepcopy(self.previous) | {"source_key": str(index), "review_dimensions": ["cut_visibility"],
                 "dimension_reviews": {"cut_visibility": {"verdict": "PASS", "source_reason": "exact source"}}}
                for index in range(131)]
        closure = {name: {"verdict": "PASS", "review_evidence": [copy.deepcopy(self.proof)],
                          "review_input_digests": {row["source_key"]: row["review_input_digest"] for row in rows}}
                   for name in ("graph_complete", "conditional_obligations_closed", "schemas_bound",
                                "fixtures_bound", "zero_input_drift", "no_material_contradictions")}
        self.assertTrue(queue.fixed_point_status(rows, closure, required_obligations=[])["reached"])
        dimension_proof = copy.deepcopy(self.proof)
        dimension_proof["inputs"]["docs/R5_4_2/autonomous_2026_10_07/tools/test_semantic_queue_retention.py"] = "0" * 64
        rows[0]["dimension_reviews"]["cut_visibility"]["review_evidence"] = [dimension_proof]
        self.assertIn("UNREVIEWED_OR_UNBOUND:0", queue.fixed_point_status(rows, closure, required_obligations=[])["failures"])

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

    def test_runtime_proof_inputs_invalidate_without_unrelated_log_invalidation(self):
        root = ROOT / "._nf02_current_audit/data" / ("review-inputs-" + uuid.uuid4().hex)
        root.mkdir(parents=True)
        source = root / "subject.py"
        source.write_bytes(b"before")
        proof = root / "proof.json"
        proof.write_bytes(b"exact proof")
        record = {"review": "SEMANTIC_PARITY_REVIEWED", "review_evidence": [{
            "file": "proof.json", "raw_digest": digest(proof), "inputs": {"subject.py": digest(source)}}]}
        with patch.object(queue, "ROOT", root):
            self.assertTrue(queue.evidence_is_bound(record))
            (root / "unrelated.log").write_bytes(b"diagnostic")
            self.assertTrue(queue.evidence_is_bound(record))
            source.write_bytes(b"after")
            self.assertFalse(queue.evidence_is_bound(record))

    def test_full_review_without_execution_input_manifest_is_unbound(self):
        previous = copy.deepcopy(self.previous)
        del previous["review_evidence"][0]["inputs"]
        self.assertFalse(queue.evidence_is_bound(previous))

    def test_full_review_cannot_omit_existing_shared_canonical_input(self):
        previous = copy.deepcopy(self.previous)
        del previous["review_evidence"][0]["inputs"]["src/bdb_audit/core/canonical_json.py"]
        self.assertFalse(queue.evidence_is_bound(previous))

    def test_full_review_cannot_omit_imported_local_validator(self):
        root = ROOT / "._nf02_current_audit/data" / ("review-imports-" + uuid.uuid4().hex)
        root.mkdir(parents=True)
        subject = root / "subject.py"
        helper = root / "helper.py"
        proof = root / "proof.json"
        subject.write_text("import helper\n", encoding="utf-8")
        helper.write_text("VALUE = 1\n", encoding="utf-8")
        proof.write_bytes(b"bound execution proof")
        record = {"review": "SEMANTIC_PARITY_REVIEWED", "review_evidence": [{
            "file": "proof.json", "raw_digest": digest(proof), "inputs": {"subject.py": digest(subject)}}]}
        with patch.object(queue, "ROOT", root):
            self.assertFalse(queue.evidence_is_bound(record))
            record["review_evidence"][0]["inputs"]["helper.py"] = digest(helper)
            self.assertTrue(queue.evidence_is_bound(record))
            helper.write_text("VALUE = 2\n", encoding="utf-8")
            self.assertFalse(queue.evidence_is_bound(record))

    def test_shared_contract_changes_invalidate_model_consumers(self):
        root = ROOT / "._nf02_current_audit/data" / ("review-semantics-" + uuid.uuid4().hex)
        document = root / "design/COMMON_BODY_GRAMMARS.md"
        document.parent.mkdir(parents=True)
        document.write_bytes(b"before")
        body = root / "design/body_grammars/test__1.json"
        body.parent.mkdir()
        body.write_bytes(b"{}")
        node = {"key": "test/1", "resolved_own_material_refs": []}
        model = {"profile_references": {"material_refs": []}, "payload_references": {"material_refs": []},
                 "field_domains": {"fields": []}, "semantic_tools": {}}
        def fixture_digest(path):
            return hashlib.sha256(path.read_bytes() if path.is_file() else str(path).encode()).hexdigest()
        with patch.object(queue, "ROOT", root), patch.object(queue, "OUT", root), patch.object(queue, "digest", fixture_digest):
            before = queue.scoped_review_dependencies(node, {"nodes": [node]}, {"test/1": "test/1"}, {}, model)
            (root / "unrelated.log").write_bytes(b"diagnostic")
            self.assertEqual(queue.scoped_review_dependencies(node, {"nodes": [node]}, {"test/1": "test/1"}, {}, model), before)
            model["field_domains"]["fields"].append({"owner": "test/1", "field": "required", "domain": "EXACT"})
            self.assertNotEqual(queue.scoped_review_dependencies(node, {"nodes": [node]}, {"test/1": "test/1"}, {}, model), before)
            model["field_domains"]["fields"].clear()
            body.write_bytes(b'{"required":["field"]}')
            self.assertNotEqual(queue.scoped_review_dependencies(node, {"nodes": [node]}, {"test/1": "test/1"}, {}, model), before)
            body.write_bytes(b"{}")
            document.write_bytes(b"changed semantics with identical code")
            self.assertNotEqual(queue.scoped_review_dependencies(node, {"nodes": [node]}, {"test/1": "test/1"}, {}, model), before)

    def test_declared_profile_edges_invalidate_only_consumers(self):
        root = ROOT / "._nf02_current_audit/data" / ("review-profiles-" + uuid.uuid4().hex)
        body = root / "design/body_grammars/test__1.json"
        body.parent.mkdir(parents=True)
        body.write_bytes(b"{}")
        node = {"key": "test/1", "resolved_own_material_refs": [{"profile_contracts": ["FIRST"]}]}
        profiles = {"FIRST": {"dependencies": ["SECOND"]}, "SECOND": {"dependencies": [], "rule": "before"},
                    "UNRELATED": {"dependencies": [], "rule": "before"}}
        model = {"profile_references": {"material_refs": []}, "payload_references": {"material_refs": []},
                 "field_domains": {"fields": []}, "semantic_tools": {}}
        def fixture_digest(path):
            return hashlib.sha256(path.read_bytes() if path.is_file() else str(path).encode()).hexdigest()
        with patch.object(queue, "ROOT", root), patch.object(queue, "OUT", root), patch.object(queue, "digest", fixture_digest):
            before = queue.scoped_review_dependencies(node, {"nodes": [node]}, {"test/1": "test/1"}, profiles, model)
            profiles["UNRELATED"]["rule"] = "after"
            self.assertEqual(queue.scoped_review_dependencies(node, {"nodes": [node]}, {"test/1": "test/1"}, profiles, model), before)
            profiles["SECOND"]["rule"] = "after"
            self.assertNotEqual(queue.scoped_review_dependencies(node, {"nodes": [node]}, {"test/1": "test/1"}, profiles, model), before)
            profiles["FIRST"]["dependencies"] = ["MISSING"]
            with self.assertRaisesRegex(ValueError, "UNCLASSIFIED_PROFILE_DEPENDENCY"):
                queue.scoped_review_dependencies(node, {"nodes": [node]}, {"test/1": "test/1"}, profiles, model)

    def test_tool_import_closure_ignores_unimported_diagnostics(self):
        root = ROOT / "._nf02_current_audit/data" / ("review-tools-" + uuid.uuid4().hex)
        tools = root / "tools"
        tools.mkdir(parents=True)
        (tools / "consumer.py").write_text("import shared\n", encoding="utf-8")
        (tools / "shared.py").write_text("VALUE = 1\n", encoding="utf-8")
        diagnostic = tools / "report.py"
        diagnostic.write_text("REPORT = 1\n", encoding="utf-8")
        with patch.object(queue, "OUT", root):
            before = queue.semantic_tool_closure(["consumer"])
            self.assertEqual(set(before), {"consumer", "shared"})
            diagnostic.write_text("REPORT = 2\n", encoding="utf-8")
            self.assertEqual(queue.semantic_tool_closure(["consumer"]), before)
            (tools / "shared.py").write_text("VALUE = 2\n", encoding="utf-8")
            self.assertNotEqual(queue.semantic_tool_closure(["consumer"]), before)

    def test_static_source_mapping_survives_process_change_without_full_promotion(self):
        previous = copy.deepcopy(self.previous)
        previous["review"] = "PENDING"
        previous["source_paragraphs"][0].update(review="SOURCE_REQUIREMENT_MAPPED_OPEN_PROOFS", review_evidence=[copy.deepcopy(self.proof)])
        current = copy.deepcopy(self.current)
        current["review_input_digest"] = "changed process"
        result = retain_review(current, previous)
        self.assertEqual(result["review"], "PENDING")
        self.assertEqual(result["source_paragraphs"][0]["review"], "SOURCE_REQUIREMENT_MAPPED_OPEN_PROOFS")
        regenerated = retain_review(copy.deepcopy(self.current) | {"review_input_digest": "changed process"}, result)
        self.assertEqual(regenerated["source_paragraphs"], result["source_paragraphs"])
        current = copy.deepcopy(self.current)
        current["review_input_digest"] = "changed process"
        current["source_paragraphs"][0]["text_sha256"] = "changed source"
        self.assertEqual(retain_review(current, previous)["source_paragraphs"][0]["review"], "PENDING")


if __name__ == "__main__":
    unittest.main()

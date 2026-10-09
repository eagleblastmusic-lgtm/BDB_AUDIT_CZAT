"""Exact candidate refs and adversarial dispatch; never canonical acceptance."""
import copy
import hashlib
import json
import unittest

from execution import OUT, ROOT, read
from build_schema_fixtures import offline_catalog
from schema_registry_build_candidate import construct
from successor_reference_candidate import CandidateReferenceDispatch, ReferenceRejected
from test_nf02_result_normalizer import ASSIGNMENT_CLAIMS, archive, package_sample, pin, sample, ValidationError


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = read(OUT / "REGISTRY_BUILD_CANDIDATE_READBACK.json")
        cls.registry = read(OUT / report["file"])
        files, _, _ = construct()
        cls.schemas = files["objects/schema_registry__2.json"]["body"]
        cls.dispatch = CandidateReferenceDispatch(cls.registry, cls.schemas, identity_fields={
            "assignment_package_binding": "binding_id", "trust_profile": "trust_profile_id"})
        cls.by_key = {entry["schema_key"]: entry for entry in cls.schemas["bindings"]}
        cls.build = read(OUT / "BUILD_TIME_CANDIDATE_READBACK.json")
        cls.schema_catalog, cls.offline = offline_catalog(cls.build)
        fixture_report = read(OUT / "BUILD_SCHEMA_FIXTURE_READBACK.json")
        vectors = read(ROOT / fixture_report["file"])["vectors"]
        cls.positive = {vector["schema_id"]: vector["input"] for vector in vectors
                        if vector["id"].endswith("::EXACT_STRUCTURAL_INSTANCE")}
        cls.entries = {entry["$id"]: entry for entry in cls.build["entries"]}

    def reference(self, kind="assignment_package_binding", *, logical=False):
        row = next(row for row in self.registry["contracts"] if row["kind"] == kind)
        value = {"kind": kind, "revision_digest": "a" * 64, "digest_profile": "BDB-OBJECT-DIGEST-1",
                 "schema_revision_ref": {"kind": "schema", "revision_digest": self.by_key[row["schema_ref"]]["schema_raw_ref"]["raw_digest"]}}
        if logical:
            value["logical_id"] = kind + "_00000000-0000-4000-8000-000000000001"
        return value

    def test_all_131_actual_active_schema_bindings(self):
        self.assertEqual(len(self.registry["contracts"]), 131)
        for row in self.registry["contracts"]:
            value = self.reference(row["kind"])
            self.assertEqual(self.dispatch.validate(value), value)

    def object_sample(self, kind="assignment_package_binding"):
        row = next(row for row in self.registry["contracts"] if row["kind"] == kind)
        body = copy.deepcopy(self.positive[row["schema_ref"]])
        encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        # Independent direct domain preimage, without the production hash helper.
        digest = hashlib.sha256(("BDB2/" + kind + "/" + row["version"]).encode("ascii") + b"\0" + encoded).hexdigest()
        ref = self.reference(kind)
        ref["revision_digest"] = digest
        schema_raw = (ROOT / self.build["directory"] / self.entries[row["schema_ref"]]["file"]).read_bytes()
        return ref, encoded, schema_raw, body

    def chronology_sample(self, *, raw_witness=None, package_mutator=None, result_mutator=None):
        """Exact candidate bodies/commits; explicitly unqualified history input.

        Root authority, union-DAG closure, full FSM and durable Store behavior
        are outside this reader fixture's claim. No content becomes accepted
        history and no gate is promoted by its locally assigned sequences.
        """
        objects, heads, commits = {}, {}, {}
        policy = self.object_sample("policy_revision")[0]
        spec = self.object_sample("spec_revision")[0]
        campaign = self.object_sample("campaign_genesis")[0]

        def encoded(kind, body):
            version = next(row["version"] for row in self.registry["contracts"] if row["kind"] == kind)
            raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ref = self.reference(kind)
            ref["revision_digest"] = hashlib.sha256(("BDB2/" + kind + "/" + version).encode() + b"\0" + raw).hexdigest()
            schema = self.object_sample(kind)[2]
            self.dispatch.validate_object(ref, raw, schema, offline_registry=self.offline)
            return ref, raw, schema

        def add(kind, seq, changes, label=None):
            body = self.object_sample(kind)[3]
            body.update(copy.deepcopy(changes))
            ref, raw, schema = encoded(kind, body)
            objects[label or kind] = {"ref": ref, "body_raw": raw, "schema_raw": schema, "accepted_seq": seq}
            return ref

        def head(seq, new_kinds, events):
            if raw_witness is not None:
                events = [{"event_type": "ArtifactAccepted", "artifact_ref": objects[k]["ref"]} for k in new_kinds]
                if not new_kinds:
                    events = copy.deepcopy(starts)
                    events = [item["event"] for item in events]
                for before, after in raw_witness.get("transitions", {}).get(seq, []):
                    events.append({"event_type": "StateTransitionAccepted", "aggregate_kind": "ATTEMPT",
                                   "aggregate_ref": attempt, "from_state": before, "to_state": after, "basis_refs": [attempt]})
                for before, after in raw_witness.get("lane_transitions", {}).get(seq, []):
                    events.append({"event_type": "StateTransitionAccepted", "aggregate_kind": "LANE_RUN",
                                   "aggregate_ref": lane, "from_state": before, "to_state": after, "basis_refs": [lane]})
            parent = "EMPTY_HISTORY" if seq == 1 else {"campaign_id": "chronology-campaign", "commit_seq": seq - 1, "commit_hash": heads[seq - 1]["accepted_head_hash"]}
            command = self.object_sample("command_envelope")[3]
            command.update(command_id=f"chronology-command-{seq}", expected_parent_head=parent,
                           governing_policy_ref=policy, governing_spec_refs=[spec],
                           command_payload={"proposed_object_refs": self.dispatch.reference_set([objects[k]["ref"] for k in new_kinds]), "events": events})
            if raw_witness is not None and "actor_ref" in raw_witness:
                command["actor_ref"] = copy.deepcopy(raw_witness["actor_ref"])
            if seq == 1:
                command["proposed_campaign_id"] = "chronology-campaign"
                if raw_witness is not None and "namespace_pin" in raw_witness:
                    command["history_namespace_ref"] = copy.deepcopy(raw_witness["namespace_pin"])
            if seq > 1:
                command.update(command_kind="TRANSITION" if not new_kinds else
                               "INGEST_EXTERNAL_LANE_RESULT" if "lane_result_admission_evidence" in new_kinds else "ACCEPT_ARTIFACTS",
                               campaign_ref=campaign)
                for key in ("bootstrap_profile_ref", "history_namespace_ref", "proposed_campaign_id"):
                    command.pop(key, None)
            if raw_witness is not None and seq in raw_witness.get("command_kinds", {}):
                command["command_kind"] = raw_witness["command_kinds"][seq]
            command_ref, command_raw, command_schema = encoded("command_envelope", command)
            objects[f"command_{seq}"] = {"ref": command_ref, "body_raw": command_raw, "schema_raw": command_schema, "accepted_seq": seq}
            body = self.object_sample("commit_body")[3]
            body.update(commit_seq=seq, campaign_id="chronology-campaign", expected_parent_head=parent,
                        prev_history_ref=parent, governing_policy_ref=policy, governing_spec_refs=[spec],
                        actor_ref=command["actor_ref"], command_ref=command_ref, command_digest=command_ref["revision_digest"],
                        immutable_object_refs=[objects[k]["ref"] for k in new_kinds] + [command_ref], ordered_event_bodies=events)
            ref, raw, schema_raw = encoded("commit_body", body)
            commits[seq] = raw
            if raw_witness is not None:
                raw_witness.setdefault("commit_records", []).append({"ref": ref, "body_raw": raw, "schema_raw": schema_raw, "accepted_seq": seq})
            heads[seq] = {"campaign_id": "chronology-campaign", "accepted_head_seq": seq,
                          "accepted_head_hash": ref["revision_digest"], "governing_policy_ref": policy, "governing_spec_refs": [spec]}

        initial_kinds = []
        scope_changes = raw_witness.get("scope_changes", {}) if raw_witness is not None else {}
        roots = {}
        if raw_witness is not None:
            for kind in ("source_generation", "stage_spec", "lane_spec", "executor_spec", "delivery_spec"):
                roots[kind] = add(kind, 1, scope_changes.get(kind, {}))
                initial_kinds.append(kind)
            if raw_witness.get("with_grant"):
                roots["view_manifest"] = add("view_manifest", 1, {})
                initial_kinds.append("view_manifest")
            campaign = add("campaign_genesis", 1, {"campaign_id": "chronology-campaign",
                                                   "source_generation_ref": roots["source_generation"], **scope_changes.get("campaign", {})})
            initial_kinds.append("campaign_genesis")
            raw_witness["campaign_ref"] = campaign
        head(1, initial_kinds, [{"event_type": "ArtifactAccepted", "artifact_ref": campaign}])
        slot = {"profile_id": "NF02_EXTERNAL_LANE_SLOT_V3", "revision_digest": "b" * 64}
        if raw_witness is not None:
            report = read(OUT / "INITIAL_PROTOCOL_BUILD_READBACK.json")
            slot_raw = raw_witness.get("slot_raw", (ROOT / report["directory"] / "profiles/NF02_EXTERNAL_LANE_SLOT_V3.json").read_bytes())
            slot = {"profile_id": "NF02_EXTERNAL_LANE_SLOT_V3", "revision_digest": hashlib.sha256(slot_raw).hexdigest()}
            raw_witness.update(slot_raw=slot_raw, slot_pin=slot, raws={})
        attempt_fields = {"assigned_history_cut": heads[1], "result_slot_contracts": [slot]}
        assignment_fields = {"assignment_input_history_cut": heads[1], "result_slot_contract_refs": [slot]}
        second_kinds = []
        if raw_witness is not None:
            stage = add("stage_run", 2, {"campaign_ref": campaign, "source_generation_ref": roots["source_generation"],
                                         "stage_spec_ref": roots["stage_spec"], "creation_input_history_cut": heads[1],
                                         "assigned_history_cut": heads[1], **scope_changes.get("stage", {})})
            lane = add("lane_run", 2, {"stage_run_ref": stage, "source_generation_ref": roots["source_generation"],
                                       "lane_spec_ref": roots["lane_spec"], "required_result_slots": [slot],
                                       "creation_input_history_cut": heads[1], **scope_changes.get("lane", {})})
            second_kinds.extend(("stage_run", "lane_run"))
            attempt_fields.update(lane_run_ref=lane, executor_profile_ref=roots["executor_spec"], delivery_profile_ref=roots["delivery_spec"])
        attempt = add("attempt", 2, {**attempt_fields, **scope_changes.get("attempt", {})})
        if raw_witness is not None:
            second_kinds.append("attempt")
            knowledge_fields = {}
            if raw_witness.get("with_grant"):
                grant = add("grant_body", 2, {"attempt_ref": attempt, "previous_knowledge_state_ref": None,
                                              "grant_input_history_cut": heads[1], "view_manifest_ref": roots["view_manifest"],
                                              "delivery_profile_ref": roots["delivery_spec"], **scope_changes.get("grant", {})})
                exposure = add("potential_exposure_record", 2, {"attempt_ref": attempt, "grant_ref": grant,
                                                                  "view_manifest_ref": roots["view_manifest"], "exposure_input_history_cut": heads[1],
                                                                  **scope_changes.get("exposure", {})})
                second_kinds.append("grant_body")
                knowledge_fields.update(potential_exposure_refs=[exposure], allowed_view_refs=[roots["view_manifest"]])
                assignment_fields.update(grant_refs=[grant], view_manifest_refs=[roots["view_manifest"]])
            isolation = add("isolation_qualification", 2, {"attempt_ref": attempt, "assessment_input_history_cut": heads[1],
                                                           "executor_profile_ref": roots["executor_spec"], "delivery_profile_ref": roots["delivery_spec"],
                                                           "result": "DECLARED", **scope_changes.get("isolation", {})})
            second_kinds.append("isolation_qualification")
            if raw_witness.get("with_grant") and not raw_witness.get("omit_exposure_event"):
                second_kinds.append("potential_exposure_record")
            if raw_witness.get("contamination_result") is not None:
                assessment = add("contamination_assessment", 2, {"attempt_ref": attempt,
                    "assessment_input_history_cut": heads[1], "result": raw_witness["contamination_result"]})
                second_kinds.append("contamination_assessment")
                knowledge_fields["contamination_assessment_refs"] = [assessment]
            knowledge = add("knowledge_state", 2, {"attempt_ref": attempt, "basis_history_cut": heads[1],
                                                  "isolation_qualification_ref": isolation, **knowledge_fields, **scope_changes.get("knowledge", {})})
            second_kinds.append("knowledge_state")
            if raw_witness.get("exposure_after_knowledge"):
                second_kinds.remove("potential_exposure_record")
                second_kinds.append("potential_exposure_record")
            assignment_fields.update(knowledge_state_ref=knowledge, source_generation_ref=roots["source_generation"],
                                     stage_spec_ref=roots["stage_spec"], lane_spec_ref=roots["lane_spec"],
                                     executor_profile_ref=roots["executor_spec"], delivery_profile_ref=roots["delivery_spec"])
        else:
            second_kinds.append("attempt")
        assignment = add("assignment_manifest", 2, {**assignment_fields, "attempt_ref": attempt, **scope_changes.get("assignment", {})})
        second_kinds.append("assignment_manifest")
        head(2, second_kinds, [{"event_type": "ArtifactAccepted", "artifact_ref": assignment}])
        binding_fields = {"binding_input_history_cut": heads[2], "assignment_ref": assignment}
        if raw_witness is not None:
            assignment_body = json.loads(objects["assignment_manifest"]["body_raw"])
            package_body, package_members, _ = package_sample()
            claims = {key: copy.deepcopy(assignment_body[key]) for key in ASSIGNMENT_CLAIMS - {"assignment_ref"}}
            claims["assignment_ref"] = assignment
            package_body.update(copy.deepcopy(claims), result_slot_contract_refs=[slot])
            if package_mutator:
                package_mutator(package_body)
            semantic_pin = pin("NF02_PACKAGE_SEMANTIC_PROFILE_V1")
            descriptor = {"profile_ref": semantic_pin,
                          "manifest": {key: value for key, value in package_body.items() if key != "package_semantic_digest"},
                          "members": package_body["members"]}
            package_tag = {"profile_ref": semantic_pin, "digest": hashlib.sha256(json.dumps(descriptor, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
            package_body["package_semantic_digest"] = package_tag
            package_raw = archive(package_body, package_members)
            package_ref = {"raw_digest": hashlib.sha256(package_raw).hexdigest(), "byte_length": len(package_raw),
                           "media_type": "application/zip", "artifact_contract_ref": pin("NF02_INPUT_PACKAGE_TRANSPORT_V2")}
            binding_fields["package_raw_ref"] = package_ref
            raw_witness["raws"][package_ref["raw_digest"]] = package_raw
        binding = add("assignment_package_binding", 3, binding_fields)
        binding_kinds = ["assignment_package_binding"]
        if raw_witness is not None and raw_witness.get("second_binding"):
            other = copy.deepcopy(json.loads(objects["assignment_package_binding"]["body_raw"]))
            other["binding_id"] = "assignment_package_binding_00000000-0000-4000-8000-000000000077"
            ref, raw, schema_raw = encoded("assignment_package_binding", other)
            objects["conflicting_binding"] = {"ref": ref, "body_raw": raw, "schema_raw": schema_raw, "accepted_seq": 3}
            binding_kinds.append("conflicting_binding")
        head(3, binding_kinds, [{"event_type": "ArtifactAccepted", "artifact_ref": binding}])
        event = {"event_type": "AttemptStarted", "attempt_ref": attempt, "assignment_ref": assignment, "package_binding_ref": binding}
        starts = [{"commit_seq": 4, "event": event}]
        head(4, [], [event])
        evidence_fields = {"admission_input_history_cut": heads[4], "assignment_ref": assignment,
                           "package_binding_ref": binding, "result_slot_contract_ref": slot}
        if raw_witness is not None:
            result_manifest, result_members = sample()
            result_manifest.update(copy.deepcopy(claims), package_binding_ref=binding, result_slot_contract_ref=slot, input_package_digest=package_tag)
            if result_mutator:
                result_mutator(result_manifest)
            result_raw = archive(result_manifest, result_members)
            result_raw_ref = {"raw_digest": hashlib.sha256(result_raw).hexdigest(), "byte_length": len(result_raw),
                              "media_type": "application/zip", "artifact_contract_ref": pin("NF02_RESULT_TRANSPORT_V2")}
            evidence_fields["result_raw_ref"] = result_raw_ref
            raw_witness["raws"][result_raw_ref["raw_digest"]] = result_raw
        evidence = add("lane_result_admission_evidence", 5, evidence_fields)
        head(5, ["lane_result_admission_evidence"], [{"event_type": "ArtifactAccepted", "artifact_ref": evidence}])
        result = self.object_sample("bdb_audit_lane_result")[3]
        result.update(admission_evidence_ref=evidence, result_input_history_cut=heads[5])
        if raw_witness is not None:
            result["result_payload"] = copy.deepcopy(result_manifest["result_payload"])
            if raw_witness.get("prior_result"):
                add("bdb_audit_lane_result", 6, result)
                sixth_kinds = ["bdb_audit_lane_result"]
                if raw_witness.get("later_knowledge"):
                    value = copy.deepcopy(json.loads(objects["knowledge_state"]["body_raw"]))
                    value.update(knowledge_state_id="knowledge_state_00000000-0000-4000-8000-000000000099",
                                 previous_knowledge_state_ref=objects["knowledge_state"]["ref"], basis_history_cut=heads[5])
                    add("knowledge_state", 6, value, "later_knowledge")
                    sixth_kinds.append("later_knowledge")
                head(6, sixth_kinds, [])
                result["result_input_history_cut"] = heads[6]
                result["lane_result_id"] = "bdb_audit_lane_result_00000000-0000-4000-8000-000000000078"
        result_ref, result_body_raw, result_schema_raw = encoded("bdb_audit_lane_result", result)
        if raw_witness is not None:
            raw_witness.update(result_ref=result_ref, result_body_raw=result_body_raw, result_schema_raw=result_schema_raw)

        def read_context(campaign_id, seq):
            return copy.deepcopy(heads.get(seq)) if campaign_id == "chronology-campaign" else None

        def read_accepted(ref, cut):
            item = next((item for item in objects.values() if item["ref"] == ref), None)
            return copy.deepcopy(item) if item and item["ref"] == ref else None

        def read_starts(ref, cut):
            return copy.deepcopy(starts)

        context = {"campaign_id": "chronology-campaign", "current_parent": copy.deepcopy(heads[max(heads)]),
                   "read_context": read_context, "read_accepted": read_accepted, "read_starts": read_starts,
                   "offline_registry": self.offline}
        return result, context, objects, heads, starts, commits

    def raw_readback_sample(self, **changes):
        witness = changes.pop("raw_witness", {})
        _, context, objects, heads, starts, commits = self.chronology_sample(raw_witness=witness, **changes)
        parameters = {**context, "slot_pin": witness["slot_pin"], "slot_raw": witness["slot_raw"], "campaign_ref": witness["campaign_ref"],
                      "package_transport_pin": pin("NF02_INPUT_PACKAGE_TRANSPORT_V2"),
                      "semantic_pin": pin("NF02_PACKAGE_SEMANTIC_PROFILE_V1"),
                      "read_raw": lambda ref: witness["raws"].get(ref["raw_digest"]),
                      "read_history": lambda cut: copy.deepcopy(witness["commit_records"][:cut["accepted_head_seq"]])}
        return witness, parameters, (objects, heads, starts, commits)

    def readback(self, witness, parameters):
        return self.dispatch.nf02_readback(witness["result_ref"], witness["result_body_raw"], witness["result_schema_raw"], **parameters)

    def test_joined_nf02_context_actual_raw_and_payload(self):
        witness, parameters, history = self.raw_readback_sample()
        before = copy.deepcopy(history)
        result = self.readback(witness, parameters)
        self.assertEqual(result["verified_sequence"], [2, 3, 4, 5])
        self.assertEqual(result["result_payload"]["notes"], sample()[0]["result_payload"]["notes"])
        self.assertEqual(history, before)

    def test_joined_result_claims_cannot_choose_context(self):
        for field in ASSIGNMENT_CLAIMS | {"package_binding_ref", "result_slot_contract_ref", "input_package_digest"}:
            def substitute(body):
                value = body[field]
                key = "accepted_head_hash" if field == "assignment_input_history_cut" else ("digest" if field == "input_package_digest" else "revision_digest")
                body[field] = {**value, key: "0" * 64}
            witness, parameters, _ = self.raw_readback_sample(result_mutator=substitute)
            with self.subTest(field=field), self.assertRaises(ValidationError) as rejected:
                self.readback(witness, parameters)
            self.assertEqual(rejected.exception.code, "NF02_ACCEPTED_CONTEXT_CLAIM_MISMATCH")

    def test_joined_package_claims_cannot_choose_assignment(self):
        witness, parameters, _ = self.raw_readback_sample(package_mutator=lambda body: body["assignment_ref"].update(revision_digest="0" * 64))
        with self.assertRaises(ValidationError) as rejected:
            self.readback(witness, parameters)
        self.assertEqual(rejected.exception.code, "NF02_ACCEPTED_CONTEXT_CLAIM_MISMATCH")

    def test_joined_missing_or_swapped_bound_raw_rejects(self):
        for kind in ("assignment_package_binding", "lane_result_admission_evidence"):
            for corrupt in (False, True):
                witness, parameters, history = self.raw_readback_sample()
                body = json.loads(history[0][kind]["body_raw"])
                ref = body["package_raw_ref" if kind == "assignment_package_binding" else "result_raw_ref"]
                if corrupt:
                    witness["raws"][ref["raw_digest"]] = b"byte substitution"
                else:
                    witness["raws"].pop(ref["raw_digest"])
                with self.subTest(kind=kind, corrupt=corrupt), self.assertRaises(ValidationError) as rejected:
                    self.readback(witness, parameters)
                self.assertEqual(rejected.exception.code, "NF02_BOUND_RAW_UNAVAILABLE_OR_CHANGED")

    def test_joined_caller_payload_not_derived_from_raw_rejects(self):
        witness, parameters, _ = self.raw_readback_sample()
        body = json.loads(witness["result_body_raw"])
        body["result_payload"]["notes"] = "caller-invented payload"
        raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        witness["result_body_raw"] = raw
        witness["result_ref"]["revision_digest"] = hashlib.sha256(b"BDB2/bdb_audit_lane_result/3\0" + raw).hexdigest()
        with self.assertRaisesRegex(ReferenceRejected, "NF02_PAYLOAD_NOT_DERIVED_FROM_BOUND_RAW"):
            self.readback(witness, parameters)

    def test_joined_slot_pins_do_not_permit_other_schema_or_normalizer(self):
        report = read(OUT / "INITIAL_PROTOCOL_BUILD_READBACK.json")
        slot = read(ROOT / report["directory"] / "profiles/NF02_EXTERNAL_LANE_SLOT_V3.json")
        for field, value in (("result_schema_key", "BDB_SCHEMA_REGISTRY::bdb_audit_lane_result/2"),
                             ("normalizer_ref", {"profile_id": "NF02_RESULT_NORMALIZER_V2", "revision_digest": "0" * 64}),
                             ("trusted", True)):
            changed = {**slot, field: value}
            witness, parameters, _ = self.raw_readback_sample(raw_witness={"slot_raw": json.dumps(changed).encode()})
            with self.subTest(field=field), self.assertRaises((ReferenceRejected, ValidationError)):
                self.readback(witness, parameters)
        witness, parameters, _ = self.raw_readback_sample()
        with self.assertRaisesRegex(ReferenceRejected, "SLOT_BYTE_SUBSTITUTION"):
            self.readback(witness, {**parameters, "slot_raw": parameters["slot_raw"] + b" "})

    def test_matching_package_and_result_cannot_echo_wrong_run_source(self):
        for subject in ("assignment", "stage", "lane"):
            witness, parameters, _ = self.raw_readback_sample(raw_witness={"scope_changes": {
                subject: {"source_generation_ref": self.reference("source_generation")}}})
            with self.subTest(subject=subject), self.assertRaisesRegex(ReferenceRejected, "NF02_RUN_SOURCE_CONFLICT"):
                self.readback(witness, parameters)

    def test_stage_and_lane_spec_substitution_rejects(self):
        for subject, field, target in (("stage", "stage_spec_ref", "stage_spec"), ("lane", "lane_spec_ref", "lane_spec")):
            witness, parameters, _ = self.raw_readback_sample(raw_witness={"scope_changes": {
                subject: {field: self.reference(target)}}})
            with self.subTest(subject=subject), self.assertRaisesRegex(ReferenceRejected, "NF02_RUN_SPEC_CONFLICT"):
                self.readback(witness, parameters)

    def test_executor_delivery_and_knowledge_cannot_select_another_attempt_context(self):
        for subject, field, target, reason in (("attempt", "executor_profile_ref", "executor_spec", "NF02_ATTEMPT_PROFILE_CONFLICT"),
                                              ("attempt", "delivery_profile_ref", "delivery_spec", "NF02_ATTEMPT_PROFILE_CONFLICT"),
                                              ("knowledge", "attempt_ref", "attempt", "NF02_KNOWLEDGE_ATTEMPT_CONFLICT")):
            witness, parameters, _ = self.raw_readback_sample(raw_witness={"scope_changes": {subject: {field: self.reference(target)}}})
            with self.subTest(field=field), self.assertRaisesRegex(ReferenceRejected, reason):
                self.readback(witness, parameters)

    def test_stage_campaign_and_genesis_namespace_must_match_context(self):
        witness, parameters, _ = self.raw_readback_sample(raw_witness={"scope_changes": {
            "stage": {"campaign_ref": self.reference("campaign_genesis")}}})
        with self.assertRaisesRegex(ReferenceRejected, "NF02_ACTIVE_CAMPAIGN_CONFLICT"):
            self.readback(witness, parameters)
        witness, parameters, _ = self.raw_readback_sample(raw_witness={"scope_changes": {"campaign": {"campaign_id": "other-namespace"}}})
        with self.assertRaisesRegex(ReferenceRejected, "NF02_CAMPAIGN_NAMESPACE_CONFLICT"):
            self.readback(witness, parameters)

    def test_scope_dependencies_need_exact_prior_membership(self):
        for kind in ("source_generation", "stage_spec", "lane_spec", "executor_spec", "delivery_spec", "stage_run", "lane_run", "knowledge_state", "campaign_genesis"):
            witness, parameters, history = self.raw_readback_sample()
            history[0][kind]["accepted_seq"] = 3
            with self.subTest(kind=kind), self.assertRaisesRegex(ReferenceRejected, "OBJECT_NOT_PRIOR_ON_CUT"):
                self.readback(witness, parameters)

    def test_assignment_material_schema_binding_cannot_be_laundered_through_zip_claims(self):
        ref = self.reference("source_generation")
        ref["schema_revision_ref"]["revision_digest"] = "0" * 64
        witness, parameters, _ = self.raw_readback_sample(raw_witness={"scope_changes": {"assignment": {"source_generation_ref": ref}}})
        with self.assertRaisesRegex(ReferenceRejected, "EXACT_TYPED_SCHEMA_BINDING_REQUIRED"):
            self.readback(witness, parameters)

    def test_joined_initial_grant_exposure_and_declared_isolation_context(self):
        witness, parameters, history = self.raw_readback_sample(raw_witness={"with_grant": True})
        before = copy.deepcopy(history)
        self.readback(witness, parameters)
        isolation = json.loads(history[0]["isolation_qualification"]["body_raw"])
        self.assertEqual(isolation["result"], "DECLARED")
        self.assertEqual(history, before)

    def test_matching_raw_claims_cannot_replace_frozen_campaign_source(self):
        wrong = self.reference("source_generation")
        witness, parameters, _ = self.raw_readback_sample(raw_witness={"scope_changes": {"campaign": {"source_generation_ref": wrong}}})
        with self.assertRaisesRegex(ReferenceRejected, "NF02_CAMPAIGN_FROZEN_SOURCE_CONFLICT"):
            self.readback(witness, parameters)

    def test_knowledge_inventory_rejects_omitted_accepted_exposure(self):
        witness, parameters, history = self.raw_readback_sample(raw_witness={"with_grant": True,
            "scope_changes": {"knowledge": {"potential_exposure_refs": []}}})
        before = copy.deepcopy(history)
        with self.assertRaisesRegex(ReferenceRejected, "NF02_KNOWLEDGE_EXPOSURE_INVENTORY_CONFLICT"):
            self.readback(witness, parameters)
        self.assertEqual(history, before)

    def test_knowledge_inventory_cannot_include_later_same_commit_exposure(self):
        witness, parameters, history = self.raw_readback_sample(raw_witness={"with_grant": True,
            "exposure_after_knowledge": True})
        before = copy.deepcopy(history)
        with self.assertRaisesRegex(ReferenceRejected, "NF02_KNOWLEDGE_EXPOSURE_INVENTORY_CONFLICT"):
            self.readback(witness, parameters)
        self.assertEqual(history, before)

    def test_accepted_grant_without_materialized_exposure_is_not_nf02_readiness(self):
        witness, parameters, history = self.raw_readback_sample(raw_witness={"with_grant": True,
            "omit_exposure_event": True, "scope_changes": {"knowledge": {"potential_exposure_refs": []}}})
        before = copy.deepcopy(history)
        with self.assertRaisesRegex(ReferenceRejected, "NF02_GRANT_EXPOSURE_ACCOUNTING_UNAVAILABLE"):
            self.readback(witness, parameters)
        self.assertEqual(history, before)

    def test_wrong_isolation_attempt_or_profiles_reject(self):
        for field, kind, reason in (("attempt_ref", "attempt", "NF02_ISOLATION_ATTEMPT_CONFLICT"),
                                    ("executor_profile_ref", "executor_spec", "NF02_ISOLATION_PROFILE_CONFLICT"),
                                    ("delivery_profile_ref", "delivery_spec", "NF02_ISOLATION_PROFILE_CONFLICT")):
            witness, parameters, _ = self.raw_readback_sample(raw_witness={"scope_changes": {"isolation": {field: self.reference(kind)}}})
            with self.subTest(field=field), self.assertRaisesRegex(ReferenceRejected, reason):
                self.readback(witness, parameters)

    def test_exposure_must_match_actual_grant_attempt_view_and_channel(self):
        for changes, reason in (({"attempt_ref": self.reference("attempt")}, "NF02_EXPOSURE_ATTEMPT_CONFLICT"),
                                ({"view_manifest_ref": self.reference("view_manifest")}, "NF02_EXPOSURE_GRANT_VIEW_OR_CHANNEL_CONFLICT"),
                                ({"channel_class": "different-channel"}, "NF02_EXPOSURE_GRANT_VIEW_OR_CHANNEL_CONFLICT")):
            witness, parameters, history = self.raw_readback_sample(raw_witness={"with_grant": True, "scope_changes": {"exposure": changes}})
            before = copy.deepcopy(history)
            with self.subTest(changes=tuple(changes)), self.assertRaisesRegex(ReferenceRejected, reason):
                self.readback(witness, parameters)
            self.assertEqual(history, before)

    def test_initial_grant_cannot_claim_a_missing_knowledge_predecessor(self):
        previous = self.reference("knowledge_state")
        witness, parameters, _ = self.raw_readback_sample(raw_witness={"with_grant": True,
            "scope_changes": {"grant": {"previous_knowledge_state_ref": previous}}})
        with self.assertRaisesRegex(ReferenceRejected, "INITIAL_GRANT_REQUIRES_NULL_PREDECESSOR"):
            self.readback(witness, parameters)

    def test_knowledge_view_members_require_prior_exact_readback(self):
        witness, parameters, _ = self.raw_readback_sample(raw_witness={"scope_changes": {
            "knowledge": {"allowed_view_refs": [self.reference("view_manifest")]}}})
        with self.assertRaisesRegex(ReferenceRejected, "ACCEPTED_OBJECT_RECORD_REQUIRED"):
            self.readback(witness, parameters)

    def test_same_commit_context_profiles_cannot_replace_assignment_input_profiles(self):
        witness, parameters, history = self.raw_readback_sample()
        history[0]["executor_spec"]["accepted_seq"] = 2
        with self.assertRaisesRegex(ReferenceRejected, "OBJECT_NOT_PRIOR_ON_CUT"):
            self.readback(witness, parameters)

    def test_successor_trust_profile_represents_complete_source_body(self):
        from jsonschema import Draft202012Validator
        ref, raw, schema_raw, body = self.object_sample("trust_profile")
        self.assertEqual(self.dispatch._schemas["trust_profile"][0], "2")
        schema = json.loads(schema_raw)
        expected = {"trust_profile_id", "trust_profile_revision", "coordinator_authority_ref", "vault_protection_class",
                    "executor_write_boundary", "history_anchor_mode", "external_anchor_profile_ref", "guarantees",
                    "explicit_non_guarantees", "recovery_pin_policy_ref"}
        self.assertEqual(set(schema["properties"]), expected)
        self.dispatch.validate_object(ref, raw, schema_raw, offline_registry=self.offline)
        validator = Draft202012Validator(schema, registry=self.offline)
        for field in schema["required"]:
            changed = copy.deepcopy(body); changed.pop(field)
            with self.subTest(missing=field):
                self.assertFalse(validator.is_valid(changed))
        for changes in ({"history_anchor_mode": "FAKE_TRUSTED"}, {"explicit_non_guarantees": []},
                        {"explicit_non_guarantees": ["claimed complete rollback assurance"]},
                        {"history_anchor_mode": "EXTERNALLY_PINNED_THROUGH"}, {"caller_trusted": True}):
            with self.subTest(changes=changes):
                self.assertFalse(validator.is_valid({**body, **changes}))
        external = {**body, "history_anchor_mode": "EXTERNALLY_PINNED_THROUGH",
                    "external_anchor_profile_ref": {"profile_id": "HISTORY_ANCHOR_V2", "revision_digest": "1" * 64}}
        self.assertTrue(validator.is_valid(external))
        old = read(ROOT / "docs/R5_4_1/candidate/schemas/trust_profile__1.schema.json")
        self.assertFalse(Draft202012Validator(old).is_valid(body))
        self.assertFalse(validator.is_valid(old["const"]))

    def principal_sample(self, **changes):
        from profile_design_audit import fixture
        schema = self.schema_catalog["BDB_EXTERNAL_PROFILE_SCHEMA::PRINCIPAL_AUTHORIZATION_V2"]
        body = fixture(schema, schema["$defs"])
        namespace = {"profile_id": "BOOTSTRAP_NAMESPACE_V2", "revision_digest": "1" * 64}
        body.update(principal_id="ISOLATED_COORDINATOR", role="COORDINATOR", permitted_operations=["INGEST"],
                    namespace_profile_ref=namespace, **changes)
        raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        actor = {"profile_id": "PRINCIPAL_AUTHORIZATION_V2", "revision_digest": hashlib.sha256(raw).hexdigest()}
        entry = next(e for e in self.build["entries"] if e["$id"] == schema["$id"])
        schema_raw = (ROOT / self.build["directory"] / entry["file"]).read_bytes()
        context = {"expected_actor_pin": actor, "expected_schema_digest": entry["raw_digest"],
                   "authenticated_principal_id": "ISOLATED_COORDINATOR", "expected_namespace_pin": namespace,
                   "required_operation": "INGEST", "required_role": "COORDINATOR", "offline_registry": self.offline}
        return actor, raw, schema_raw, context

    def test_principal_comparison_binds_independent_identity_operation_namespace_and_schema(self):
        actor, raw, schema, context = self.principal_sample()
        self.assertEqual(self.dispatch.principal_context(actor, raw, schema, **context)["operation"], "INGEST")
        for changes, reason in (({"expected_actor_pin": {**actor, "revision_digest": "0" * 64}}, "ACTOR_NOT_INDEPENDENTLY_INSTALLED"),
                                ({"expected_schema_digest": "0" * 64}, "PRINCIPAL_SCHEMA_PIN_REQUIRED"),
                                ({"authenticated_principal_id": "CALLER_LABEL"}, "AUTHENTICATED_PRINCIPAL_OR_ROLE_CONFLICT"),
                                ({"required_role": "OWNER"}, "AUTHENTICATED_PRINCIPAL_OR_ROLE_CONFLICT"),
                                ({"expected_namespace_pin": {**context["expected_namespace_pin"], "revision_digest": "0" * 64}}, "PRINCIPAL_NAMESPACE_CONFLICT"),
                                ({"required_operation": "ACCEPT"}, "PRINCIPAL_OPERATION_NOT_AUTHORIZED"),
                                ({"required_operation": "APPROVE"}, "PRINCIPAL_OPERATION_NOT_AUTHORIZED")):
            with self.subTest(changes=changes), self.assertRaisesRegex(ReferenceRejected, reason):
                self.dispatch.principal_context(actor, raw, schema, **{**context, **changes})
        with self.assertRaisesRegex(ReferenceRejected, "PRINCIPAL_RAW_IDENTITY_CONFLICT"):
            self.dispatch.principal_context(actor, raw+b" ", schema, **context)
        with self.assertRaisesRegex(ReferenceRejected, "EXACT_PRINCIPAL_PROFILE_PIN_REQUIRED"):
            self.dispatch.principal_context({**actor, "trusted": True}, raw, schema, **context)

    def ingestion_mac_sample(self):
        _, _, history = self.raw_readback_sample()
        evidence = copy.deepcopy(history[0]["lane_result_admission_evidence"])
        protocol = read(OUT / "INITIAL_PROTOCOL_BUILD_READBACK.json")
        raw = (ROOT / protocol["directory"] / "profiles/NF02_PROTOCOL_PROFILE_V3.json").read_bytes()
        context = {"campaign_ref": history[0]["campaign_genesis"]["ref"],
                   "actor_ref": {"profile_id": "ISOLATED_TEST_INGESTOR", "revision_digest": hashlib.sha256(b"unqualified test principal").hexdigest()},
                   "trust_profile_ref": self.object_sample("trust_profile")[0],
                   "schema_registry_ref": self.object_sample("schema_registry")[0],
                   "protocol_profile_ref": {"profile_id": "NF02_PROTOCOL_PROFILE_V3", "revision_digest": hashlib.sha256(raw).hexdigest()},
                   "operation": "INGEST_EXTERNAL_LANE_RESULT"}
        return b"isolated-test-key-never-authority-1", evidence, context

    def mac(self, key, evidence, context):
        return self.dispatch.nf02_ingestion_mac(key, evidence["ref"], evidence["body_raw"], evidence["schema_raw"],
                                               authority_context=context, offline_registry=self.offline)

    def check_mac(self, value, key, evidence, context):
        return self.dispatch.verify_nf02_ingestion_mac(value, key, evidence["ref"], evidence["body_raw"], evidence["schema_raw"],
                                                      authority_context=context, offline_registry=self.offline)

    def replace_evidence_body(self, evidence, body):
        changed = copy.deepcopy(evidence)
        raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        changed["body_raw"] = raw
        changed["ref"]["revision_digest"] = hashlib.sha256(b"BDB2/lane_result_admission_evidence/3\0" + raw).hexdigest()
        return changed

    def test_existing_mac_is_not_successor_binding_slot_or_raw_authority(self):
        from bdb_audit.history.authority_hooks import compute_ingestion_capability
        key, evidence, _ = self.ingestion_mac_sample()
        body = json.loads(evidence["body_raw"])
        old = compute_ingestion_capability(key, body)
        for field, inner in (("package_binding_ref", "revision_digest"), ("result_slot_contract_ref", "revision_digest"),
                             ("result_raw_ref", "raw_digest"), ("admission_input_history_cut", "accepted_head_hash")):
            changed = copy.deepcopy(body)
            changed[field][inner] = "0" * 64
            self.assertEqual(compute_ingestion_capability(key, changed), old, field)
        # This documents a breaking boundary, not a predecessor regression:
        # the old closed admission contract never accepted this successor body.

    def test_successor_mac_covers_every_evidence_field(self):
        key, evidence, context = self.ingestion_mac_sample()
        capability = self.mac(key, evidence, context)
        self.assertIsNone(self.check_mac(capability, key, evidence, context))
        body = json.loads(evidence["body_raw"])
        for field in body:
            changed = copy.deepcopy(body)
            if field == "admission_evidence_id":
                changed[field] = "lane_result_admission_evidence_00000000-0000-4000-8000-000000000099"
            else:
                inner = "accepted_head_hash" if "cut" in field else ("raw_digest" if field == "result_raw_ref" else "revision_digest")
                changed[field][inner] = "0" * 64
            swapped = self.replace_evidence_body(evidence, changed)
            with self.subTest(field=field):
                self.assertNotEqual(self.mac(key, swapped, context), capability)
                with self.assertRaisesRegex(ReferenceRejected, "NF02_INGESTION_CAPABILITY_MISMATCH"):
                    self.check_mac(capability, key, swapped, context)

    def test_successor_mac_covers_each_root_actor_and_protocol_binding(self):
        key, evidence, context = self.ingestion_mac_sample()
        capability = self.mac(key, evidence, context)
        for field in set(context) - {"operation"}:
            changed = copy.deepcopy(context)
            changed[field]["revision_digest"] = "0" * 64
            with self.subTest(field=field), self.assertRaisesRegex(ReferenceRejected, "NF02_INGESTION_CAPABILITY_MISMATCH"):
                self.check_mac(capability, key, evidence, changed)

    def test_legacy_token_wrong_key_and_self_asserted_flags_do_not_authorize(self):
        from bdb_audit.history.authority_hooks import compute_ingestion_capability
        key, evidence, context = self.ingestion_mac_sample()
        capability = self.mac(key, evidence, context)
        for token in (None, "", "0" * 64, compute_ingestion_capability(key, json.loads(evidence["body_raw"]))):
            with self.subTest(token_type=type(token).__name__), self.assertRaises(ReferenceRejected):
                self.check_mac(token, key, evidence, context)
        with self.assertRaisesRegex(ReferenceRejected, "NF02_INGESTION_CAPABILITY_MISMATCH"):
            self.check_mac(capability, b"another-isolated-test-key-32bytes!", evidence, context)
        for changed in ({**context, "trusted": True}, {**context, "operation": "ACCEPT_ARTIFACTS"}, {}):
            with self.assertRaisesRegex(ReferenceRejected, "CLOSED_NF02_ISSUER_CONTEXT_REQUIRED"):
                self.mac(key, evidence, changed)

    def test_capability_and_secret_cannot_enter_closed_admission_body(self):
        key, evidence, context = self.ingestion_mac_sample()
        body = json.loads(evidence["body_raw"])
        for field in ("ingestion_capability", "secret", "trusted"):
            changed = self.replace_evidence_body(evidence, {**body, field: "caller-data"})
            with self.subTest(field=field), self.assertRaisesRegex(ReferenceRejected, "OBJECT_SCHEMA_OR_OFFLINE_RESOLUTION_FAILED"):
                self.mac(key, changed, context)
        with self.assertRaisesRegex(ReferenceRejected, "NF02_PRIVATE_MAC_KEY_REQUIRED"):
            self.mac(b"short", evidence, context)

    def test_transient_key_rotation_does_not_change_readback_facts(self):
        witness, parameters, history = self.raw_readback_sample()
        before = copy.deepcopy(history)
        first = self.readback(witness, parameters)
        key, evidence, context = self.ingestion_mac_sample()
        rotated = b"rotated-isolated-test-key-never-authority-2"
        original_mac = self.mac(key, evidence, context)
        rotated_mac = self.mac(rotated, evidence, context)
        self.assertNotEqual(original_mac, rotated_mac)
        self.assertIsNone(self.check_mac(rotated_mac, rotated, evidence, context))
        with self.assertRaisesRegex(ReferenceRejected, "NF02_INGESTION_CAPABILITY_MISMATCH"):
            self.check_mac(original_mac, rotated, evidence, context)
        second = self.readback(witness, parameters)
        self.assertEqual(first, second)
        self.assertEqual(history, before)

    def operation_sample(self, **changes):
        witness, parameters, history = self.raw_readback_sample(**changes)
        context = {key: parameters[key] for key in ("campaign_id", "current_parent", "read_context", "read_accepted", "read_starts", "offline_registry")}
        derived = self.dispatch.nf02_chronology(json.loads(witness["result_body_raw"]), **context)
        protocol = read(OUT / "INITIAL_PROTOCOL_BUILD_READBACK.json")
        raw = (ROOT / protocol["directory"] / "profiles/FULL_PATH_TRANSITION_TABLE_V2.json").read_bytes()
        context.pop("read_starts")
        context.update(read_history=lambda cut: copy.deepcopy(witness["commit_records"]), transition_raw=raw,
                       transition_pin={"profile_id": "FULL_PATH_TRANSITION_TABLE_V2", "revision_digest": hashlib.sha256(raw).hexdigest()})
        return derived, context, witness, history

    def admission_sample(self, **changes):
        witness, parameters, history = self.raw_readback_sample(**changes)
        evidence = copy.deepcopy(history[0]["lane_result_admission_evidence"])
        parameters["current_parent"] = copy.deepcopy(history[1][4])
        protocol = read(OUT / "INITIAL_PROTOCOL_BUILD_READBACK.json")
        raw = (ROOT / protocol["directory"] / "profiles/FULL_PATH_TRANSITION_TABLE_V2.json").read_bytes()
        parameters.update(read_history=lambda cut: copy.deepcopy(witness["commit_records"][:cut["accepted_head_seq"]]),
                          transition_raw=raw, transition_pin={"profile_id": "FULL_PATH_TRANSITION_TABLE_V2", "revision_digest": hashlib.sha256(raw).hexdigest()})
        def prior_only(ref, cut):
            # No proposed E or future R is provided as an accepted fact.
            if ref["kind"] in {"lane_result_admission_evidence", "bdb_audit_lane_result"}:
                return None
            return copy.deepcopy(next((r for r in history[0].values() if r["ref"] == ref and r["accepted_seq"] <= cut["accepted_head_seq"]), None))
        parameters["read_accepted"] = prior_only
        return evidence, parameters, witness, history

    def result_preflight_sample(self, **changes):
        witness, parameters, history = self.raw_readback_sample(**changes)
        protocol = read(OUT / "INITIAL_PROTOCOL_BUILD_READBACK.json")
        raw = (ROOT / protocol["directory"] / "profiles/FULL_PATH_TRANSITION_TABLE_V2.json").read_bytes()
        parameters.update(transition_raw=raw, transition_pin={
            "profile_id": "FULL_PATH_TRANSITION_TABLE_V2", "revision_digest": hashlib.sha256(raw).hexdigest()})
        return witness, parameters, history

    def lane_completion_sample(self, *, later_knowledge=False, changes=None, lane_transitions=None,
                               isolation_result="ENFORCED", contamination_result=None,
                               required_outputs=None, predicate_mutator=None, result_mutator=None,
                               include_isolation_output=False):
        if lane_transitions is None:
            lane_transitions = {3: [("PLANNED", "READY")], 4: [("READY", "RUNNING")],
                                6: [("RUNNING", "COMPLETION_CANDIDATE")]}
        protocol = read(OUT / "INITIAL_PROTOCOL_BUILD_READBACK.json")
        predicate_raw = (ROOT / protocol["directory"] / "profiles/LANE_COMPLETION_V2.json").read_bytes()
        if predicate_mutator:
            predicate = json.loads(predicate_raw)
            predicate_mutator(predicate)
            predicate_raw = json.dumps(predicate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        predicate_pin = {"profile_id": "LANE_COMPLETION_V2", "revision_digest": hashlib.sha256(predicate_raw).hexdigest()}
        witness, parameters, history = self.raw_readback_sample(result_mutator=result_mutator, raw_witness={
            "with_grant": True, "prior_result": True, "later_knowledge": later_knowledge,
            "contamination_result": contamination_result,
            "lane_transitions": lane_transitions, "scope_changes": {
                "lane_spec": {"completion_predicate_ref": predicate_pin, "required_isolation_assurance": "ENFORCED",
                              "required_outputs": ["NF02_RESULT", "REPORT"] if required_outputs is None else required_outputs},
                "isolation": {"result": isolation_result}}})
        objects = history[0]
        lane = json.loads(objects["lane_run"]["body_raw"])
        body = self.object_sample("lane_completion")[3]
        body.update(lane_run_ref=objects["lane_run"]["ref"], lane_spec_ref=lane["lane_spec_ref"],
            input_history_cut=parameters["current_parent"], attempt_refs=[objects["attempt"]["ref"]],
            final_knowledge_state_ref=objects["knowledge_state"]["ref"],
            isolation_qualification_ref=objects["isolation_qualification"]["ref"],
            required_output_refs=[objects["bdb_audit_lane_result"]["ref"]],
            contamination_assessment_refs=[objects["contamination_assessment"]["ref"]] if contamination_result is not None else [],
            completion_predicate_result="SATISFIED")
        if include_isolation_output:
            body["required_output_refs"].append(objects["isolation_qualification"]["ref"])
        body.update(changes or {})
        raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        version = next(row["version"] for row in self.registry["contracts"] if row["kind"] == "lane_completion")
        ref = self.reference("lane_completion")
        ref["revision_digest"] = hashlib.sha256(("BDB2/lane_completion/" + version).encode() + b"\0" + raw).hexdigest()
        context = {key: parameters[key] for key in (
            "campaign_id", "current_parent", "read_context", "read_accepted", "read_history", "offline_registry")}
        transition_raw = (ROOT / protocol["directory"] / "profiles/FULL_PATH_TRANSITION_TABLE_V2.json").read_bytes()
        context.update(transition_raw=transition_raw, transition_pin={
            "profile_id": "FULL_PATH_TRANSITION_TABLE_V2", "revision_digest": hashlib.sha256(transition_raw).hexdigest()})
        schema_entry = next(entry for entry in self.build["entries"] if entry["$id"] == "BDB_EXTERNAL_PROFILE_SCHEMA::LANE_COMPLETION_V2")
        context.update(predicate_pin=predicate_pin, predicate_raw=predicate_raw,
            predicate_schema_raw=(ROOT / self.build["directory"] / schema_entry["file"]).read_bytes(),
            predicate_schema_digest=schema_entry["raw_digest"])
        context.update(read_raw=parameters["read_raw"], read_starts=parameters["read_starts"],
            slot_instances={json.dumps(witness["slot_pin"], sort_keys=True, separators=(",", ":")).encode(): witness["slot_raw"]},
            package_transport_pin=parameters["package_transport_pin"], semantic_pin=parameters["semantic_pin"])
        return ref, raw, self.object_sample("lane_completion")[2], context, history

    def test_nf02_lane_completion_exact_context_is_only_partial_l7(self):
        ref, raw, schema, context, history = self.lane_completion_sample()
        before = copy.deepcopy(history)
        result = self.dispatch.nf02_lane_completion_context(ref, raw, schema, **context)
        self.assertEqual(result["verified_result_slots"], 1)
        self.assertEqual(result["verified_raw_result_count"], 1)
        self.assertEqual(result["lane_state"], "COMPLETION_CANDIDATE")
        self.assertEqual(result["verified_output_names"], ["NF02_RESULT", "REPORT"])
        self.assertEqual(result["full_lane_predicate"], "NOT_EVALUATED")
        self.assertFalse(result["qualification"])
        self.assertEqual(history, before)

    def test_nf02_lane_completion_required_output_names_have_no_alias_or_default(self):
        for name in ("report", "UNBOUND_OUTPUT"):
            ref, raw, schema, context, history = self.lane_completion_sample(required_outputs=[name])
            before = copy.deepcopy(history)
            with self.subTest(name=name), self.assertRaisesRegex(ReferenceRejected, "NF02_COMPLETION_UNKNOWN_REQUIRED_OUTPUT_BINDING"):
                self.dispatch.nf02_lane_completion_context(ref, raw, schema, **context)
            self.assertEqual(history, before)

    def test_nf02_lane_completion_rehashed_duplicate_output_binding_rejects(self):
        def duplicate(profile):
            bindings = profile["parameters"]["output_bindings"]
            bindings.append({"output_name": bindings[0]["output_name"],
                             "representation": "NF02_PAYLOAD_GROUP", "output_group": "report"})
        ref, raw, schema, context, history = self.lane_completion_sample(predicate_mutator=duplicate)
        before = copy.deepcopy(history)
        with self.assertRaisesRegex(ReferenceRejected, "NF02_COMPLETION_OUTPUT_BINDING_ORDER_OR_DUPLICATE"):
            self.dispatch.nf02_lane_completion_context(ref, raw, schema, **context)
        self.assertEqual(history, before)

    def test_nf02_lane_completion_required_report_group_requires_actual_members(self):
        def remove_report(manifest):
            manifest["result_payload"]["outputs"]["report"]["member_paths"] = []
        ref, raw, schema, context, history = self.lane_completion_sample(result_mutator=remove_report)
        before = copy.deepcopy(history)
        with self.assertRaisesRegex(ReferenceRejected, "NF02_COMPLETION_REQUIRED_RAW_OUTPUT_GROUP_MISSING"):
            self.dispatch.nf02_lane_completion_context(ref, raw, schema, **context)
        self.assertEqual(history, before)

    def test_nf02_lane_completion_scoped_output_requires_complete_accepted_inventory(self):
        def scoped(profile):
            profile["parameters"]["output_bindings"].insert(0, {
                "output_name": "ISOLATION", "representation": "CANONICAL_SCOPED_SET",
                "schema_key": "BDB_SCHEMA_REGISTRY::isolation_qualification/2", "scope_binding": "DIRECT_ATTEMPT_REF"})
        for included in (True, False):
            ref, raw, schema, context, history = self.lane_completion_sample(predicate_mutator=scoped,
                required_outputs=["ISOLATION", "NF02_RESULT", "REPORT"], include_isolation_output=included)
            before = copy.deepcopy(history)
            with self.subTest(included=included):
                if included:
                    result = self.dispatch.nf02_lane_completion_context(ref, raw, schema, **context)
                    self.assertFalse(result["qualification"])
                    self.assertIn("ISOLATION", result["verified_output_names"])
                else:
                    with self.assertRaisesRegex(ReferenceRejected, "NF02_COMPLETION_REQUIRED_SCOPED_OUTPUT_INVENTORY_CONFLICT"):
                        self.dispatch.nf02_lane_completion_context(ref, raw, schema, **context)
            self.assertEqual(history, before)

    def test_nf02_lane_completion_missing_output_cannot_claim_satisfied(self):
        ref, raw, schema, context, history = self.lane_completion_sample(changes={"required_output_refs": []})
        before = copy.deepcopy(history)
        with self.assertRaisesRegex(ReferenceRejected, "NF02_COMPLETION_RESULT_SLOT_INVENTORY_CONFLICT"):
            self.dispatch.nf02_lane_completion_context(ref, raw, schema, **context)
        self.assertEqual(history, before)

    def test_nf02_lane_completion_rejects_stale_final_knowledge(self):
        ref, raw, schema, context, history = self.lane_completion_sample(later_knowledge=True)
        before = copy.deepcopy(history)
        with self.assertRaisesRegex(ReferenceRejected, "NF02_COMPLETION_REQUIRES_CURRENT_KNOWLEDGE"):
            self.dispatch.nf02_lane_completion_context(ref, raw, schema, **context)
        self.assertEqual(history, before)

    def test_nf02_lane_completion_rejects_spec_and_isolation_substitution(self):
        for changes, reason in (({"lane_spec_ref": self.reference("lane_spec")}, "NF02_COMPLETION_LANE_SPEC_CONFLICT"),
                                ({"isolation_qualification_ref": self.reference("isolation_qualification")}, "NF02_COMPLETION_KNOWLEDGE_ISOLATION_CONFLICT")):
            ref, raw, schema, context, history = self.lane_completion_sample(changes=changes)
            before = copy.deepcopy(history)
            with self.subTest(field=next(iter(changes))), self.assertRaisesRegex(ReferenceRejected, reason):
                self.dispatch.nf02_lane_completion_context(ref, raw, schema, **context)
            self.assertEqual(history, before)

    def test_nf02_lane_completion_requires_history_derived_completion_candidate(self):
        for transitions, reason in (({}, "NF02_COMPLETION_LANE_NOT_ELIGIBLE"),
                ({3: [("PLANNED", "RUNNING")]}, "NF02_COMPLETION_ILLEGAL_OR_STALE_LANE_STATE"),
                ({3: [("PLANNED", "READY")], 4: [("READY", "RUNNING")],
                  6: [("RUNNING", "COMPLETION_CANDIDATE"), ("COMPLETION_CANDIDATE", "SUPERSEDED")]}, "NF02_COMPLETION_LANE_NOT_ELIGIBLE"),
                ({3: [("PLANNED", "COMPLETION_ACCEPTED")]}, "NF02_COMPLETION_GENERIC_TRANSITION_BYPASS")):
            ref, raw, schema, context, history = self.lane_completion_sample(lane_transitions=transitions)
            before = copy.deepcopy(history)
            with self.subTest(transitions=transitions), self.assertRaisesRegex(ReferenceRejected, reason):
                self.dispatch.nf02_lane_completion_context(ref, raw, schema, **context)
            self.assertEqual(history, before)

    def test_nf02_lane_completion_transition_profile_bytes_must_match_pin(self):
        ref, raw, schema, context, history = self.lane_completion_sample()
        before = copy.deepcopy(history)
        context["transition_raw"] += b" "
        with self.assertRaisesRegex(ReferenceRejected, "NF02_COMPLETION_TRANSITION_PIN_REQUIRED"):
            self.dispatch.nf02_lane_completion_context(ref, raw, schema, **context)
        self.assertEqual(history, before)

    def test_nf02_lane_completion_declared_isolation_cannot_meet_enforced_policy(self):
        ref, raw, schema, context, history = self.lane_completion_sample(isolation_result="DECLARED")
        before = copy.deepcopy(history)
        with self.assertRaisesRegex(ReferenceRejected, "NF02_COMPLETION_ISOLATION_POLICY_NOT_SATISFIED"):
            self.dispatch.nf02_lane_completion_context(ref, raw, schema, **context)
        self.assertEqual(history, before)

    def test_nf02_lane_completion_predicate_raw_and_schema_must_match_pins(self):
        ref, raw, schema, context, history = self.lane_completion_sample()
        before = copy.deepcopy(history)
        for field, reason in (("predicate_raw", "NF02_COMPLETION_EXACT_PREDICATE_PIN_REQUIRED"),
                              ("predicate_schema_raw", "NF02_COMPLETION_PREDICATE_SCHEMA_PIN_REQUIRED")):
            with self.subTest(field=field), self.assertRaisesRegex(ReferenceRejected, reason):
                self.dispatch.nf02_lane_completion_context(ref, raw, schema, **{**context, field: context[field] + b" "})
        self.assertEqual(history, before)

    def test_nf02_lane_completion_accepted_result_still_requires_actual_raw(self):
        ref, raw, schema, context, history = self.lane_completion_sample()
        before = copy.deepcopy(history)
        with self.assertRaisesRegex(ValidationError, "NF02_BOUND_RAW_UNAVAILABLE_OR_CHANGED"):
            self.dispatch.nf02_lane_completion_context(ref, raw, schema, **{**context, "read_raw": lambda _: None})
        self.assertEqual(history, before)

    def test_nf02_lane_completion_slot_readback_set_cannot_omit_or_swap(self):
        ref, raw, schema, context, history = self.lane_completion_sample()
        before = copy.deepcopy(history)
        with self.assertRaisesRegex(ReferenceRejected, "NF02_COMPLETION_EXACT_SLOT_READBACK_SET_REQUIRED"):
            self.dispatch.nf02_lane_completion_context(ref, raw, schema, **{**context, "slot_instances": {}})
        changed = {key: value + b" " for key, value in context["slot_instances"].items()}
        with self.assertRaisesRegex(ReferenceRejected, "SLOT_BYTE_SUBSTITUTION"):
            self.dispatch.nf02_lane_completion_context(ref, raw, schema, **{**context, "slot_instances": changed})
        self.assertEqual(history, before)

    def test_nf02_lane_completion_known_contamination_assessment_cannot_be_omitted(self):
        ref, raw, schema, context, history = self.lane_completion_sample(contamination_result="CLEAN",
            changes={"contamination_assessment_refs": []})
        before = copy.deepcopy(history)
        with self.assertRaisesRegex(ReferenceRejected, "NF02_COMPLETION_KNOWLEDGE_CONTAMINATION_OMITTED"):
            self.dispatch.nf02_lane_completion_context(ref, raw, schema, **context)
        self.assertEqual(history, before)

    def test_nf02_lane_completion_contamination_status_is_not_an_automatic_waiver(self):
        for status in ("CLEAN", "CONTAMINATED", "UNKNOWN", "NOT_APPLICABLE"):
            ref, raw, schema, context, history = self.lane_completion_sample(contamination_result=status)
            before = copy.deepcopy(history)
            with self.subTest(status=status):
                if status == "CLEAN":
                    result = self.dispatch.nf02_lane_completion_context(ref, raw, schema, **context)
                    self.assertFalse(result["qualification"])
                else:
                    with self.assertRaisesRegex(ReferenceRejected, "NF02_COMPLETION_CONTAMINATION_NOT_CLEAN_OR_NA_AUTHORITY_UNAVAILABLE"):
                        self.dispatch.nf02_lane_completion_context(ref, raw, schema, **context)
            self.assertEqual(history, before)

    def result_preflight(self, witness, parameters):
        return self.dispatch.nf02_result_preflight(witness["result_ref"], witness["result_body_raw"],
            witness["result_schema_raw"], **parameters)

    def test_result_preflight_joins_actual_raw_to_received_attempt(self):
        witness, parameters, history = self.result_preflight_sample(raw_witness={"with_grant": True})
        before = copy.deepcopy(history)
        result = self.result_preflight(witness, parameters)
        self.assertEqual(result["attempt_state"], "RESULT_RECEIVED")
        self.assertEqual(result["proposed_result_ref"], witness["result_ref"])
        self.assertIsNone(result["accepted_result_ref"])
        self.assertFalse(result["qualification"])
        self.assertEqual(history, before)

    def test_result_preflight_rejects_terminal_attempt_after_admission(self):
        for terminal in ("BLOCKED", "FAILED", "SUPERSEDED"):
            witness, parameters, history = self.result_preflight_sample(raw_witness={
                "transitions": {5: [("RESULT_RECEIVED", terminal)]}})
            before = copy.deepcopy(history)
            with self.subTest(terminal=terminal), self.assertRaisesRegex(ReferenceRejected, "NF02_RESULT_SLOT_NOT_OPEN"):
                self.result_preflight(witness, parameters)
            self.assertEqual(history, before)

    def test_result_preflight_rejects_second_result_in_same_slot(self):
        witness, parameters, history = self.result_preflight_sample(raw_witness={"prior_result": True})
        before = copy.deepcopy(history)
        with self.assertRaisesRegex(ReferenceRejected, "NF02_RESULT_SLOT_NOT_OPEN"):
            self.result_preflight(witness, parameters)
        self.assertEqual(history, before)

    def test_result_preflight_rejects_missing_raw_and_transition_byte_swap(self):
        witness, parameters, history = self.result_preflight_sample()
        before = copy.deepcopy(history)
        with self.assertRaisesRegex(ReferenceRejected, "NF02_TRANSITION_PIN_REQUIRED"):
            self.result_preflight(witness, {**parameters, "transition_raw": parameters["transition_raw"] + b" "})
        witness["raws"].clear()
        with self.assertRaisesRegex(ValidationError, "NF02_BOUND_RAW_UNAVAILABLE_OR_CHANGED"):
            self.result_preflight(witness, parameters)
        self.assertEqual(history, before)

    def admission(self, evidence, parameters):
        return self.dispatch.nf02_admission_preflight(evidence["ref"], evidence["body_raw"], evidence["schema_raw"], **parameters)

    def issuer_sample(self, *, admission_changes=None):
        """Actual build bytes as isolated expected pins; never installation authority."""
        source = read(OUT / "SOURCE_PROFILE_BUILD_READBACK.json")
        folder = ROOT / source["directory"]
        actor_raw = (folder / "profiles/COORDINATOR.json").read_bytes()
        namespace_raw = (folder / "profiles/BOOTSTRAP_NAMESPACE_V2.json").read_bytes()
        actor = {"profile_id": "PRINCIPAL_AUTHORIZATION_V2", "revision_digest": hashlib.sha256(actor_raw).hexdigest()}
        namespace = {"profile_id": "BOOTSTRAP_NAMESPACE_V2", "revision_digest": hashlib.sha256(namespace_raw).hexdigest()}
        trust = read(folder / "objects/trust_profile__2.json")
        sr = read(OUT / "SCHEMA_REGISTRY_BUILD_READBACK.json")
        root = read(ROOT / sr["directory"] / "objects/schema_registry__2.json")["ref"]
        protocol = read(OUT / "INITIAL_PROTOCOL_BUILD_READBACK.json")
        protocol_raw = (ROOT / protocol["directory"] / "profiles/NF02_PROTOCOL_PROFILE_V3.json").read_bytes()
        evidence, parameters, witness, history = self.admission_sample(raw_witness={
            "actor_ref": actor, "namespace_pin": namespace,
            "scope_changes": {"campaign": {"trust_profile_ref": trust["ref"], "schema_set_ref": root}},
            **(admission_changes or {})})
        def schema(key):
            return (ROOT / self.build["directory"] / self.entries[key]["file"]).read_bytes()
        actor_schema = schema("BDB_EXTERNAL_PROFILE_SCHEMA::PRINCIPAL_AUTHORIZATION_V2")
        protocol_schema = schema("BDB_EXTERNAL_PROFILE_SCHEMA::NF02_PROTOCOL_PROFILE_V3")
        parameters.update(trust_record={"ref": trust["ref"], "body_raw": json.dumps(
            trust["body"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(),
            "schema_raw": schema("BDB_SCHEMA_REGISTRY::trust_profile/2")},
            expected_issuer_context={"campaign_ref": witness["campaign_ref"], "actor_ref": actor,
                "trust_profile_ref": trust["ref"], "schema_registry_ref": root,
                "protocol_profile_ref": {"profile_id": "NF02_PROTOCOL_PROFILE_V3", "revision_digest": hashlib.sha256(protocol_raw).hexdigest()},
                "operation": "INGEST_EXTERNAL_LANE_RESULT"},
            actor_ref=actor, actor_raw=actor_raw, actor_schema_raw=actor_schema,
            actor_schema_digest=hashlib.sha256(actor_schema).hexdigest(),
            authenticated_principal_id=json.loads(actor_raw)["principal_id"], namespace_pin=namespace,
            protocol_raw=protocol_raw, protocol_schema_raw=protocol_schema,
            protocol_schema_digest=hashlib.sha256(protocol_schema).hexdigest())
        return evidence, parameters, witness, history

    def issuer(self, evidence, parameters):
        return self.dispatch.nf02_issuer_preflight(evidence["ref"], evidence["body_raw"], evidence["schema_raw"], **parameters)

    def test_joined_issuer_actual_trust_principal_history_and_raw_without_capability_or_write(self):
        evidence, parameters, witness, history = self.issuer_sample()
        before = copy.deepcopy((witness, history))
        result = self.issuer(evidence, parameters)
        self.assertEqual(result["attempt_state"], "STARTED")
        self.assertEqual(result["issuer_comparison"]["operation"], "INGEST")
        self.assertIsNone(result["accepted_evidence_ref"])
        self.assertIsNone(result["capability"])
        self.assertFalse(result["qualification"])
        self.assertFalse(result["installed_authority_proven"])
        self.assertEqual((witness, history), before)

    def test_joined_issuer_rejects_independent_context_substitution(self):
        evidence, parameters, _, _ = self.issuer_sample()
        for field, value, reason in (
            ("authenticated_principal_id", "FORGED_COORDINATOR", "AUTHENTICATED_PRINCIPAL_OR_ROLE_CONFLICT"),
            ("actor_raw", parameters["actor_raw"] + b" ", "PRINCIPAL_RAW_IDENTITY_CONFLICT"),
            ("protocol_raw", parameters["protocol_raw"] + b" ", "PROTOCOL_RAW_CONFLICT"),
            ("protocol_schema_digest", "0" * 64, "PROTOCOL_SCHEMA_PIN_REQUIRED"),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(ReferenceRejected, reason):
                self.issuer(evidence, {**parameters, field: value})
        for field, kind, reason in (("campaign_ref", "campaign_genesis", "ISSUER_CAMPAIGN_CONFLICT"),
                                    ("schema_registry_ref", "schema_registry", "ISSUER_SCHEMA_REGISTRY_CONFLICT")):
            context = {**parameters["expected_issuer_context"], field: self.reference(kind)}
            with self.subTest(field=field), self.assertRaisesRegex(ReferenceRejected, reason):
                self.issuer(evidence, {**parameters, "expected_issuer_context": context})

    def test_joined_issuer_rehashed_principal_cannot_escape_history_namespace(self):
        evidence, parameters, _, _ = self.issuer_sample()
        wrong = {"profile_id": "BOOTSTRAP_NAMESPACE_V2", "revision_digest": "0" * 64}
        actor = json.loads(parameters["actor_raw"])
        actor["namespace_profile_ref"] = wrong
        actor_raw = json.dumps(actor, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        pin = {"profile_id": actor["profile_id"], "revision_digest": hashlib.sha256(actor_raw).hexdigest()}
        trust = json.loads(parameters["trust_record"]["body_raw"])
        trust["coordinator_authority_ref"] = pin
        trust_raw = json.dumps(trust, sort_keys=True, separators=(",", ":")).encode()
        ref = copy.deepcopy(parameters["trust_record"]["ref"])
        ref["revision_digest"] = hashlib.sha256(b"BDB2/trust_profile/2\0" + trust_raw).hexdigest()
        # Even a correctly rehashed trust/principal tuple cannot replace the
        # already accepted campaign installation root.
        changed = {**parameters, "actor_ref": pin, "actor_raw": actor_raw, "namespace_pin": wrong,
                   "trust_record": {**parameters["trust_record"], "ref": ref, "body_raw": trust_raw},
                   "expected_issuer_context": {**parameters["expected_issuer_context"], "actor_ref": pin, "trust_profile_ref": ref}}
        with self.assertRaisesRegex(ReferenceRejected, "CAMPAIGN_INSTALLATION_ROOT_CONFLICT"):
            self.issuer(evidence, changed)

    def test_joined_issuer_protocol_hash_does_not_authorize_other_slot(self):
        evidence, parameters, _, _ = self.issuer_sample()
        protocol = json.loads(parameters["protocol_raw"])
        protocol["result_slot_ref"]["revision_digest"] = "0" * 64
        raw = json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()
        changed = {**parameters, "protocol_raw": raw, "expected_issuer_context": {
            **parameters["expected_issuer_context"], "protocol_profile_ref": {
                "profile_id": protocol["profile_id"], "revision_digest": hashlib.sha256(raw).hexdigest()}}}
        with self.assertRaisesRegex(ReferenceRejected, "PROTOCOL_SELECTION_CONFLICT"):
            self.issuer(evidence, changed)

    def test_joined_issuer_must_match_actual_first_history_namespace(self):
        evidence, parameters, _, _ = self.issuer_sample(admission_changes={
            "namespace_pin": {"profile_id": "BOOTSTRAP_NAMESPACE_V2", "revision_digest": "0" * 64}})
        with self.assertRaisesRegex(ReferenceRejected, "ISSUER_HISTORY_NAMESPACE_CONFLICT"):
            self.issuer(evidence, parameters)

    def test_joined_issuer_rejects_closed_attempt_and_missing_raw_without_mutation(self):
        for changes, reason in (({"transitions": {4: [("STARTED", "CANCELLED")]}}, "RESULT_SLOT_NOT_OPEN"),
                                ({}, "NF02_BOUND_RAW_UNAVAILABLE_OR_CHANGED")):
            evidence, parameters, witness, history = self.issuer_sample(admission_changes=changes)
            if not changes:
                parameters["read_raw"] = lambda ref: None
            before = copy.deepcopy((witness, history))
            with self.subTest(reason=reason), self.assertRaisesRegex((ReferenceRejected, ValidationError), reason):
                self.issuer(evidence, parameters)
            self.assertEqual((witness, history), before)

    def stage_slot_sample(self, *, spec_changes=None, lane_changes=None, completion_changes=None, slot_changes=None,
                          duplicate_slot_identity=False, reuse_completion=False, future_lane_cut=False):
        """Exact candidate slot bodies and prior reader facts; no qualified STAGE claim."""
        records, profiles = {}, {}
        def add(kind, seq, changes):
            ref, _, schema, body = self.object_sample(kind)
            body.update(copy.deepcopy(changes))
            raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            version = next(row["version"] for row in self.registry["contracts"] if row["kind"] == kind)
            ref["revision_digest"] = hashlib.sha256(f"BDB2/{kind}/{version}\0".encode() + raw).hexdigest()
            self.dispatch.validate_object(ref, raw, schema, offline_registry=self.offline)
            records[json.dumps(ref, sort_keys=True)] = {"ref": ref, "body_raw": raw, "schema_raw": schema, "accepted_seq": seq}
            return ref, body
        policy, spec_root = self.reference("policy_revision"), self.reference("spec_revision")
        def cut(seq):
            return {"campaign_id": "stage-slot-campaign", "accepted_head_seq": seq,
                    "accepted_head_hash": f"{seq:064x}", "governing_policy_ref": policy, "governing_spec_refs": [spec_root]}
        source, _ = add("source_generation", 1, {})
        campaign, _ = add("campaign_genesis", 1, {"campaign_id": "stage-slot-campaign", "source_generation_ref": source})
        spec, spec_body = add("stage_spec", 1, {"required_lane_slots": ["REQUIRED_SLOT"],
            "optional_lane_slots": ["OPTIONAL_SLOT"], "stage_spec_revision": 1, **(spec_changes or {})})
        lane_spec, lane_spec_body = add("lane_spec", 1, {"lane_key": "REQUIRED_LANE", "stage_spec_revision": 1})
        result_slots = [self.object_sample("attempt")[3]["result_slot_contracts"][0]]
        slot = {"profile_id": "MANDATORY_LANE_SLOT_V1", "slot_id": "REQUIRED_SLOT", "lane_role": "REQUIRED_LANE",
                "result_slot_contract_refs": result_slots, "completion_contract_ref": lane_spec_body["completion_predicate_ref"],
                **(slot_changes or {})}
        raw = json.dumps(slot, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        slot_pin = {"profile_id": slot["profile_id"], "revision_digest": hashlib.sha256(raw).hexdigest()}
        profiles[slot_pin["revision_digest"]] = raw
        slot_pins = [slot_pin]
        if duplicate_slot_identity or reuse_completion:
            other = {**slot, "slot_id": "SECOND_SLOT" if reuse_completion else slot["slot_id"],
                     "lane_role": "REQUIRED_LANE" if reuse_completion else "OTHER_ROLE"}
            other_raw = json.dumps(other, sort_keys=True, separators=(",", ":")).encode()+b"\n"
            other_pin = {"profile_id": other["profile_id"], "revision_digest": hashlib.sha256(other_raw).hexdigest()}
            profiles[other_pin["revision_digest"]] = other_raw
            slot_pins.append(other_pin)
            if reuse_completion:
                spec, spec_body = add("stage_spec", 1, {**spec_body, "required_lane_slots": ["REQUIRED_SLOT", "SECOND_SLOT"]})
        stage, _ = add("stage_run", 2, {"campaign_ref": campaign, "source_generation_ref": source,
            "stage_spec_ref": spec, "creation_input_history_cut": cut(1), "assigned_history_cut": cut(1),
            "required_lane_slot_contract_refs": slot_pins})
        lane, _ = add("lane_run", 2, {"stage_run_ref": stage, "source_generation_ref": source,
            "lane_spec_ref": lane_spec, "creation_input_history_cut": cut(1), "required_result_slots": result_slots,
            **(lane_changes or {})})
        lane_completion, _ = add("lane_completion", 3, {"lane_run_ref": lane, "lane_spec_ref": lane_spec,
            "input_history_cut": cut(3 if future_lane_cut else 2), "completion_predicate_result": "SATISFIED", **(completion_changes or {})})
        target, body = add("stage_completion", 4, {"stage_run_ref": stage, "stage_spec_ref": spec,
            "input_history_cut": cut(3), "required_lane_slot_results": [{"slot_contract_ref": pin,
                                                                        "lane_completion_ref": lane_completion} for pin in slot_pins]})
        record = records[json.dumps(target, sort_keys=True)]
        schema = (ROOT / self.build["directory"] / self.entries["BDB_EXTERNAL_PROFILE_SCHEMA::MANDATORY_LANE_SLOT_V1"]["file"]).read_bytes()
        context = {"campaign_id": "stage-slot-campaign", "current_parent": cut(3),
            "read_context": lambda campaign, seq: cut(seq),
            "read_accepted": lambda ref, at: copy.deepcopy(records.get(json.dumps(ref, sort_keys=True))),
            "read_profile": lambda pin: profiles.get(pin["revision_digest"]),
            "slot_schema_raw": schema, "slot_schema_digest": hashlib.sha256(schema).hexdigest(), "offline_registry": self.offline}
        return record, context, records, profiles, body, spec_body

    def stage_slots(self, record, context):
        return self.dispatch.stage_slot_bindings(record["ref"], record["body_raw"], record["schema_raw"], **context)

    def test_stage_slots_exact_required_binding_is_partial_not_stage_qualification(self):
        record, context, records, profiles, _, _ = self.stage_slot_sample()
        before = copy.deepcopy((records, profiles))
        result = self.stage_slots(record, context)
        self.assertEqual(result["required_slot_count"], 1)
        self.assertEqual(result["full_stage_predicate"], "NOT_EVALUATED")
        self.assertFalse(result["qualification"])
        self.assertEqual((records, profiles), before)

    def test_stage_slots_omitted_required_or_optional_replacement_reject(self):
        for changes in ({"spec_changes": {"required_lane_slots": ["REQUIRED_SLOT", "MISSING_SLOT"]}},
                        {"slot_changes": {"slot_id": "OPTIONAL_SLOT"}}):
            record, context, records, profiles, _, _ = self.stage_slot_sample(**changes)
            before = copy.deepcopy((records, profiles))
            with self.subTest(changes=changes), self.assertRaisesRegex(ReferenceRejected, "REQUIRED_SPEC_SET_CONFLICT"):
                self.stage_slots(record, context)
            self.assertEqual((records, profiles), before)

    def test_stage_slots_wrong_lane_source_role_contract_or_future_cut_reject(self):
        cases = (({"lane_changes": {"stage_run_ref": self.reference("stage_run")}}, "LANE_CONTEXT_CONFLICT"),
                 ({"lane_changes": {"source_generation_ref": self.reference("source_generation")}}, "LANE_CONTEXT_CONFLICT"),
                 ({"slot_changes": {"lane_role": "OTHER_LANE"}}, "LANE_CONTRACT_CONFLICT"),
                 ({"lane_changes": {"required_result_slots": []}}, "LANE_CONTRACT_CONFLICT"),
                 ({"completion_changes": {"completion_predicate_result": "UNKNOWN"}}, "LANE_NOT_SATISFIED"))
        for changes, reason in cases:
            record, context, records, profiles, _, _ = self.stage_slot_sample(**changes)
            before = copy.deepcopy((records, profiles))
            with self.subTest(reason=reason), self.assertRaisesRegex(ReferenceRejected, reason):
                self.stage_slots(record, context)
            self.assertEqual((records, profiles), before)

    def test_stage_slots_raw_and_schema_exact_pins_required(self):
        record, context, _, profiles, _, _ = self.stage_slot_sample()
        for changes, reason in (({"read_profile": lambda pin: None}, "RAW_UNAVAILABLE_OR_CHANGED"),
                                ({"read_profile": lambda pin: profiles[pin["revision_digest"]]+b" "}, "RAW_UNAVAILABLE_OR_CHANGED"),
                                ({"slot_schema_digest": "0"*64}, "SCHEMA_PIN_REQUIRED")):
            with self.subTest(reason=reason), self.assertRaisesRegex(ReferenceRejected, reason):
                self.stage_slots(record, {**context, **changes})

    def test_stage_slots_duplicate_semantic_slot_reuse_and_future_completion_input_reject(self):
        for changes, reason in (({"duplicate_slot_identity": True}, "DUPLICATE_IDENTITY"),
                                ({"reuse_completion": True}, "REUSED_LANE_COMPLETION"),
                                ({"future_lane_cut": True}, "LANE_COMPLETION_REQUIRES_PRIOR_INPUT")):
            record, context, records, profiles, _, _ = self.stage_slot_sample(**changes)
            before = copy.deepcopy((records, profiles))
            with self.subTest(reason=reason), self.assertRaisesRegex(ReferenceRejected, reason):
                self.stage_slots(record, context)
            self.assertEqual((records, profiles), before)

    def test_first_admission_preflight_never_fabricates_accepted_evidence(self):
        evidence, parameters, witness, history = self.admission_sample(raw_witness={"with_grant": True})
        before = copy.deepcopy((witness, history))
        result = self.admission(evidence, parameters)
        self.assertIsNone(result["accepted_evidence_ref"])
        self.assertEqual(result["proposed_evidence_ref"], evidence["ref"])
        self.assertEqual(result["prior_sequence"], [2, 3, 4])
        self.assertEqual(result["attempt_state"], "STARTED")
        self.assertEqual(result["result_payload"], sample()[0]["result_payload"])
        self.assertEqual((witness, history), before)

    def test_first_admission_requires_current_cut_and_prior_start(self):
        evidence, parameters, _, history = self.admission_sample()
        with self.assertRaisesRegex(ReferenceRejected, "CURRENT_COMMAND_PARENT_REQUIRED"):
            self.admission(evidence, {**parameters, "current_parent": history[1][3]})
        with self.assertRaisesRegex(ReferenceRejected, "ONE_PRIOR_STARTED_TRANSITION_REQUIRED"):
            self.admission(evidence, {**parameters, "read_starts": lambda ref, cut: []})

    def test_first_admission_rejects_terminal_attempt_and_missing_raw(self):
        evidence, parameters, _, _ = self.admission_sample(raw_witness={"transitions": {4: [("STARTED", "CANCELLED")]}})
        with self.assertRaisesRegex(ReferenceRejected, "NF02_RESULT_SLOT_NOT_OPEN"):
            self.admission(evidence, parameters)
        evidence, parameters, witness, history = self.admission_sample()
        before = copy.deepcopy((witness, history))
        with self.assertRaises(ValidationError):
            self.admission(evidence, {**parameters, "read_raw": lambda ref: None})
        self.assertEqual((witness, history), before)

    def test_first_admission_checks_transport_claims_without_future_evidence(self):
        evidence, parameters, _, _ = self.admission_sample(result_mutator=lambda manifest: manifest.update(source_generation_ref=self.reference("source_generation")))
        with self.assertRaisesRegex(ValidationError, "ACCEPTED_CONTEXT_CLAIM_MISMATCH"):
            self.admission(evidence, parameters)

    def test_prefix_command_eligibility_separates_facts_and_transitions(self):
        for seq, kind, reason in ((4, "ACCEPT_ARTIFACTS", "EMPTY_FACT_COMMAND_REQUIRES_TRANSITION"),
                                  (3, "TRANSITION", "TRANSITION_COMMAND_CANNOT_ACCEPT_FACTS")):
            derived, context, _, _ = self.operation_sample(raw_witness={"command_kinds": {seq: kind}})
            with self.subTest(seq=seq), self.assertRaisesRegex(ReferenceRejected, reason):
                self.dispatch.nf02_operation_state(derived, **context)

    def test_ingest_command_cannot_accept_unrelated_fact_closure(self):
        derived, context, _, _ = self.operation_sample(raw_witness={"command_kinds": {3: "INGEST_EXTERNAL_LANE_RESULT"}})
        with self.assertRaisesRegex(ReferenceRejected, "INGEST_COMMAND_REQUIRES_ADMISSION_FACT"):
            self.dispatch.nf02_operation_state(derived, **context)

    def test_nf02_state_replay_matches_exact_prefix_without_mutation(self):
        derived, context, witness, history = self.operation_sample()
        before = copy.deepcopy((witness, history))
        actual = self.dispatch.nf02_operation_state(derived, **context)
        self.assertEqual(actual["attempt_state"], "RESULT_RECEIVED")
        self.assertEqual(actual["accepted_result_refs"], [])
        self.assertEqual(actual["binding_ref"], derived["binding_ref"])
        self.assertEqual((witness, history), before)

    def test_nf02_terminal_attempt_after_start_cannot_admit_result(self):
        for terminal in ("FAILED", "BLOCKED", "CANCELLED", "SUPERSEDED"):
            derived, context, witness, history = self.operation_sample(raw_witness={"transitions": {4: [("STARTED", terminal)]}})
            before = copy.deepcopy((witness, history))
            with self.subTest(terminal=terminal), self.assertRaisesRegex(ReferenceRejected, "NF02_ILLEGAL_OR_STALE_ATTEMPT_STATE"):
                self.dispatch.nf02_operation_state(derived, **context)
            self.assertEqual((witness, history), before)

    def test_nf02_terminal_attempt_after_binding_cannot_start(self):
        for terminal in ("CANCELLED", "SUPERSEDED"):
            derived, context, _, _ = self.operation_sample(raw_witness={"transitions": {3: [("CREATED", terminal)]}})
            with self.subTest(terminal=terminal), self.assertRaisesRegex(ReferenceRejected, "NF02_ILLEGAL_OR_STALE_ATTEMPT_STATE"):
                self.dispatch.nf02_operation_state(derived, **context)

    def test_nf02_second_binding_same_assignment_and_raw_is_conflict(self):
        derived, context, witness, history = self.operation_sample(raw_witness={"second_binding": True})
        before = copy.deepcopy((witness, history))
        with self.assertRaisesRegex(ReferenceRejected, "NF02_ASSIGNMENT_BINDING_CONFLICT"):
            self.dispatch.nf02_operation_state(derived, **context)
        self.assertEqual((witness, history), before)

    def test_nf02_existing_result_closes_attempt_slot(self):
        derived, context, _, _ = self.operation_sample(raw_witness={"prior_result": True})
        with self.assertRaisesRegex(ReferenceRejected, "NF02_RESULT_SLOT_NOT_OPEN"):
            self.dispatch.nf02_operation_state(derived, **context)

    def test_nf02_prefix_omission_order_and_cut_substitution_reject(self):
        derived, context, witness, _ = self.operation_sample()
        for records in (witness["commit_records"][:-1], list(reversed(witness["commit_records"]))):
            with self.subTest(count=len(records)), self.assertRaises(ReferenceRejected):
                self.dispatch.nf02_operation_state(derived, **{**context, "read_history": lambda cut: records})
        records = copy.deepcopy(witness["commit_records"])
        records[2]["ref"]["revision_digest"] = "0" * 64
        with self.assertRaisesRegex(ReferenceRejected, "OBJECT_DOMAIN_DIGEST_MISMATCH"):
            self.dispatch.nf02_operation_state(derived, **{**context, "read_history": lambda cut: records})

    def test_nf02_generic_transition_cannot_create_result_authority(self):
        for transition in (("STARTED", "RESULT_RECEIVED"), ("RESULT_RECEIVED", "RESULT_ACCEPTED")):
            derived, context, _, _ = self.operation_sample(raw_witness={"transitions": {4: [transition]}})
            with self.subTest(transition=transition), self.assertRaisesRegex(ReferenceRejected, "NF02_GENERIC_TRANSITION_BYPASS"):
                self.dispatch.nf02_operation_state(derived, **context)

    def test_nf02_replay_rejects_stale_state_and_terminal_reopen(self):
        for transitions in ([("CREATED", "CANCELLED")], [("STARTED", "FAILED"), ("FAILED", "STARTED")]):
            derived, context, _, _ = self.operation_sample(raw_witness={"transitions": {4: transitions}})
            with self.subTest(transitions=transitions), self.assertRaises(ReferenceRejected):
                self.dispatch.nf02_operation_state(derived, **context)

    def test_nf02_state_replay_requires_exact_pinned_transition_profile(self):
        derived, context, _, _ = self.operation_sample()
        with self.assertRaisesRegex(ReferenceRejected, "NF02_TRANSITION_PIN_REQUIRED"):
            self.dispatch.nf02_operation_state(derived, **{**context, "transition_raw": context["transition_raw"] + b" "})
        profile = json.loads(context["transition_raw"])
        profile["transitions"].append({"aggregate_kind": "ATTEMPT", "from_state": "FAILED", "to_state": "STARTED", "guard": "ATTEMPT_START"})
        raw = json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
        with self.assertRaisesRegex(ReferenceRejected, "EXACT_NORMATIVE_TRANSITION_TABLE_REQUIRED"):
            self.dispatch.nf02_operation_state(derived, **{**context, "transition_raw": raw,
                "transition_pin": {**context["transition_pin"], "revision_digest": hashlib.sha256(raw).hexdigest()}})

    def test_nf02_hash_valid_commit_cannot_contradict_its_command(self):
        for field in ("ordered_event_bodies", "actor_ref"):
            derived, context, witness, history = self.operation_sample()
            record = witness["commit_records"][-1]
            body = json.loads(record["body_raw"])
            if field == "ordered_event_bodies":
                body[field][0]["artifact_ref"] = copy.deepcopy(derived["assignment_ref"])
            else:
                body[field]["revision_digest"] = "0" * 64
            raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            version = self.dispatch._schemas["commit_body"][0]
            record["body_raw"] = raw
            record["ref"]["revision_digest"] = hashlib.sha256(f"BDB2/commit_body/{version}\0".encode() + raw).hexdigest()
            history[1][5]["accepted_head_hash"] = record["ref"]["revision_digest"]
            context["current_parent"] = copy.deepcopy(history[1][5])
            # Both the body/schema/domain hash and reader cut are now coherent;
            # rejection must check the separately retained exact command.
            expected = "NF02_COMMIT_PAYLOAD_CONFLICT" if field == "ordered_event_bodies" else "NF02_COMMIT_COMMAND_CONTEXT_CONFLICT"
            with self.subTest(field=field), self.assertRaisesRegex(ReferenceRejected, expected):
                self.dispatch.nf02_operation_state(derived, **context)

    def grant_guard_sample(self, *, later=False):
        witness, parameters, history = self.raw_readback_sample(raw_witness={"with_grant": True})
        grant = json.loads(history[0]["grant_body"]["body_raw"])
        if later:
            grant.update(grant_input_history_cut=history[1][2], previous_knowledge_state_ref=history[0]["knowledge_state"]["ref"])
        context = {key: parameters[key] for key in ("campaign_id", "read_context", "read_accepted", "read_history", "offline_registry")}
        return grant, context, witness, history

    def test_initial_grant_status_comes_from_history_not_null(self):
        grant, context, _, history = self.grant_guard_sample()
        self.assertTrue(self.dispatch.grant_predecessor(grant, **context)["initial"])
        grant["previous_knowledge_state_ref"] = history[0]["knowledge_state"]["ref"]
        with self.assertRaisesRegex(ReferenceRejected, "INITIAL_GRANT_REQUIRES_NULL_PREDECESSOR"):
            self.dispatch.grant_predecessor(grant, **context)

    def test_later_grant_requires_exact_prior_current_knowledge(self):
        grant, context, _, history = self.grant_guard_sample(later=True)
        result = self.dispatch.grant_predecessor(grant, **context)
        self.assertFalse(result["initial"])
        self.assertEqual(result["previous_knowledge_state_ref"], history[0]["knowledge_state"]["ref"])
        for wrong in (None, self.reference("knowledge_state")):
            grant["previous_knowledge_state_ref"] = wrong
            with self.subTest(wrong=wrong), self.assertRaisesRegex(ReferenceRejected, "LATER_GRANT_REQUIRES_EXACT_CURRENT_KNOWLEDGE"):
                self.dispatch.grant_predecessor(grant, **context)

    def test_grant_history_cannot_omit_or_forge_prior_inventory(self):
        grant, context, witness, history = self.grant_guard_sample(later=True)
        before = copy.deepcopy((witness, history))
        for records in (witness["commit_records"][:1], list(reversed(witness["commit_records"][:2]))):
            with self.subTest(count=len(records)), self.assertRaises(ReferenceRejected):
                self.dispatch.grant_predecessor(grant, **{**context, "read_history": lambda cut: records})
        with self.assertRaisesRegex(ReferenceRejected, "ACCEPTED_OBJECT_RECORD_REQUIRED"):
            self.dispatch.grant_predecessor(grant, **{**context, "read_accepted": lambda ref, cut: None})
        self.assertEqual((witness, history), before)

    def test_knowledge_predecessor_is_history_derived_and_exposure_monotonic(self):
        _, context, _, history = self.grant_guard_sample(later=True)
        knowledge = json.loads(history[0]["knowledge_state"]["body_raw"])
        self.assertTrue(self.dispatch.knowledge_predecessor(knowledge, **context)["initial"])
        knowledge.update(basis_history_cut=history[1][2], previous_knowledge_state_ref=history[0]["knowledge_state"]["ref"])
        self.assertFalse(self.dispatch.knowledge_predecessor(knowledge, **context)["initial"])
        knowledge["potential_exposure_refs"] = []
        with self.assertRaisesRegex(ReferenceRejected, "KNOWLEDGE_EXPOSURE_NOT_MONOTONIC"):
            self.dispatch.knowledge_predecessor(knowledge, **context)

    def test_knowledge_predecessor_cannot_reset_or_select_another_revision(self):
        _, context, _, history = self.grant_guard_sample(later=True)
        knowledge = json.loads(history[0]["knowledge_state"]["body_raw"])
        knowledge["basis_history_cut"] = history[1][2]
        for previous in (None, self.reference("knowledge_state")):
            knowledge["previous_knowledge_state_ref"] = previous
            with self.subTest(previous=previous), self.assertRaisesRegex(ReferenceRejected, "KNOWLEDGE_REQUIRES_EXACT_CURRENT_PREDECESSOR"):
                self.dispatch.knowledge_predecessor(knowledge, **context)
        knowledge["basis_history_cut"] = history[1][1]
        with self.assertRaisesRegex(ReferenceRejected, "INITIAL_KNOWLEDGE_REQUIRES_NO_PREDECESSOR"):
            self.dispatch.knowledge_predecessor(knowledge, **context)

    def initial_grant_sample(self):
        ref, _, schema, body = self.object_sample("grant_body")
        for field, allowed, _, _ in self.dispatch._material["grant_body"]:
            if field != "previous_knowledge_state_ref":
                body[field] = self.reference(allowed[0].split("/")[0])
        raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ref["revision_digest"] = hashlib.sha256(b"BDB2/grant_body/2\0" + raw).hexdigest()
        self.dispatch.validate_object(ref, raw, schema, offline_registry=self.offline)
        return body, schema

    def test_exact_initial_grant_null_is_not_a_typed_edge(self):
        body, schema = self.initial_grant_sample()
        edges = self.dispatch.material_references("grant_body", body, schema_raw=schema, offline_registry=self.offline)
        self.assertEqual(body["previous_knowledge_state_ref"], None)
        self.assertNotIn("previous_knowledge_state_ref", [e["field"] for e in edges])
        self.assertIn("attempt_ref", [e["field"] for e in edges])

    def test_optional_cardinality_does_not_authorize_null_without_exact_schema(self):
        body, schema = self.initial_grant_sample()
        for supplied in (None, schema + b" "):
            with self.assertRaisesRegex(ReferenceRejected, "EXACT_NULLABLE_OWN_SCHEMA_REQUIRED"):
                self.dispatch.material_references("grant_body", body, schema_raw=supplied, offline_registry=self.offline)
        body["attempt_ref"] = None
        with self.assertRaisesRegex(ReferenceRejected, "NULL_NOT_PERMITTED_BY_EXACT_BODY_SCHEMA"):
            self.dispatch.material_references("grant_body", body, schema_raw=schema, offline_registry=self.offline)

    def assignment_dag_sample(self, *, same_commit_retry=False):
        """Concrete transaction bytes; prior reader facts remain unqualified.

        This isolates body-derived same-commit edges, not authenticating a
        complete earlier campaign or granting production/installation authority.
        """
        prior_records, content = {}, {}

        def prior(kind):
            if kind not in prior_records:
                ref, raw, schema, body = self.object_sample(kind)
                if kind == "campaign_genesis":
                    body["campaign_id"] = "dag-campaign"
                    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
                    ref["revision_digest"] = hashlib.sha256(b"BDB2/campaign_genesis/2\0" + raw).hexdigest()
                prior_records[kind] = {"ref": ref, "body_raw": raw, "schema_raw": schema, "accepted_seq": 1}
            return copy.deepcopy(prior_records[kind]["ref"])

        cut = {"campaign_id": "dag-campaign", "accepted_head_seq": 1, "accepted_head_hash": "1" * 64,
               "governing_policy_ref": prior("policy_revision"), "governing_spec_refs": [prior("spec_revision")]}

        def substitute(value):
            if isinstance(value, dict):
                if {"kind", "revision_digest", "digest_profile", "schema_revision_ref"} <= value.keys():
                    return prior(value["kind"])
                if {"campaign_id", "accepted_head_seq", "accepted_head_hash"} <= value.keys():
                    return copy.deepcopy(cut)
                return {k: substitute(v) for k, v in value.items()}
            if isinstance(value, list):
                return [substitute(v) for v in value]
            return value

        def add(kind, changes, alias=None):
            ref, _, schema, body = self.object_sample(kind)
            body = copy.deepcopy(changes) if kind == "command_envelope" else substitute(body)
            body.update(copy.deepcopy(changes))
            raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            version = self.dispatch._schemas[kind][0]
            ref["revision_digest"] = hashlib.sha256(f"BDB2/{kind}/{version}\0".encode() + raw).hexdigest()
            self.dispatch.validate_object(ref, raw, schema, offline_registry=self.offline)
            content[alias or kind] = {"ref": ref, "body_raw": raw, "schema_raw": schema}
            return ref

        attempt_changes = {"assigned_history_cut": cut}
        if same_commit_retry:
            old = add("attempt", {"assigned_history_cut": cut, "attempt_id": "attempt_00000000-0000-4000-8000-000000000081"}, alias="prior_attempt_in_current_transaction")
            attempt_changes.update(retry_of_attempt_ref=old, retry_reason_ref=prior("execution_result"))
        attempt = add("attempt", attempt_changes)
        view, delivery = prior("view_manifest"), prior("delivery_spec")
        grant = add("grant_body", {"attempt_ref": attempt, "previous_knowledge_state_ref": None,
                                  "view_manifest_ref": view, "delivery_profile_ref": delivery, "grant_input_history_cut": cut})
        exposure = add("potential_exposure_record", {"attempt_ref": attempt, "grant_ref": grant,
                                                     "view_manifest_ref": view, "exposure_input_history_cut": cut})
        knowledge = add("knowledge_state", {"attempt_ref": attempt, "potential_exposure_refs": [exposure],
                                             "allowed_view_refs": [view], "basis_history_cut": cut})
        assignment = add("assignment_manifest", {"attempt_ref": attempt, "grant_refs": [grant],
                                                  "view_manifest_refs": [view], "knowledge_state_ref": knowledge,
                                                  "assignment_input_history_cut": cut, "delivery_profile_ref": delivery})
        proposed = [r["ref"] for r in content.values()]
        parent = {"campaign_id": "dag-campaign", "commit_seq": 1, "commit_hash": cut["accepted_head_hash"]}
        command = self.object_sample("command_envelope")[3]
        for key in ("bootstrap_profile_ref", "history_namespace_ref", "proposed_campaign_id"):
            command.pop(key, None)
        command.update(command_kind="ACCEPT_ARTIFACTS", command_id="dag-command-2", campaign_ref=prior("campaign_genesis"),
                       expected_parent_head=parent, governing_policy_ref=cut["governing_policy_ref"], governing_spec_refs=cut["governing_spec_refs"],
                       command_payload={"proposed_object_refs": self.dispatch.reference_set(proposed), "events": [{"event_type": "ArtifactAccepted", "artifact_ref": ref} for ref in proposed]})
        command_ref = add("command_envelope", command)
        proposed.append(command_ref)

        def read_content(ref):
            return copy.deepcopy(next((r for r in content.values() if r["ref"] == ref), None))

        def read_accepted(ref, at):
            return copy.deepcopy(next((r for r in prior_records.values() if r["ref"] == ref), None))

        parameters = {"read_content": read_content, "input_cut": cut, "read_context": lambda campaign, seq: copy.deepcopy(cut),
                      "campaign_id": "dag-campaign", "read_accepted": read_accepted, "installation_refs": [],
                      "command_kind": "ACCEPT_ARTIFACTS", "commit_seq": 2, "expected_parent": parent, "offline_registry": self.offline}
        return proposed, parameters, content, prior_records

    def test_actual_initial_assignment_transaction_has_body_derived_union_dag(self):
        proposed, parameters, content, prior = self.assignment_dag_sample()
        before = copy.deepcopy((content, prior))
        result = self.dispatch.union_closure(proposed, **parameters)
        self.assertEqual(result["node_count"], 6)
        self.assertEqual([r["kind"] for r in result["ordered_refs"]],
                         ["attempt", "grant_body", "potential_exposure_record", "knowledge_state", "assignment_manifest", "command_envelope"])
        self.assertGreaterEqual(len(result["typed_edges"]), 9)
        self.assertEqual((content, prior), before)

    def test_initial_assignment_non_topological_or_missing_content_rejects(self):
        proposed, parameters, _, _ = self.assignment_dag_sample()
        for sequence in (list(reversed(proposed)), proposed[1:] + proposed[:1]):
            with self.assertRaises(ReferenceRejected):
                self.dispatch.union_closure(sequence, **parameters)
        with self.assertRaises(ReferenceRejected):
            self.dispatch.union_closure([r for r in proposed if r["kind"] != "grant_body"], **parameters)

    def test_same_commit_retry_cannot_satisfy_prior_only_even_in_order(self):
        proposed, parameters, _, _ = self.assignment_dag_sample(same_commit_retry=True)
        with self.assertRaisesRegex(ReferenceRejected, "PRIOR_OR_INSTALLED_REF_IN_CURRENT_CLOSURE"):
            self.dispatch.union_closure(proposed, **parameters)

    def test_initial_assignment_content_storage_is_not_prior_membership(self):
        proposed, parameters, _, _ = self.assignment_dag_sample()
        with self.assertRaisesRegex(ReferenceRejected, "ACCEPTED_OBJECT_RECORD_REQUIRED"):
            self.dispatch.union_closure(proposed, **{**parameters, "read_accepted": lambda ref, cut: None})

    def replace_dag_command(self, proposed, content, mutate):
        record = content["command_envelope"]
        old = copy.deepcopy(record["ref"])
        index = proposed.index(old)
        body = json.loads(record["body_raw"])
        mutate(body)
        raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        record["body_raw"] = raw
        record["ref"]["revision_digest"] = hashlib.sha256(b"BDB2/command_envelope/2\0" + raw).hexdigest()
        proposed[index] = copy.deepcopy(record["ref"])

    def test_actual_union_cannot_omit_unclaimed_fact_or_reorder_artifact_events(self):
        proposed, parameters, content, _ = self.assignment_dag_sample()
        self.replace_dag_command(proposed, content, lambda body: body["command_payload"]["events"].reverse())
        with self.assertRaisesRegex(ReferenceRejected, "DETERMINISTIC_ARTIFACT_EVENT_ORDER_REQUIRED"):
            self.dispatch.union_closure(proposed, **parameters)
        proposed, parameters, content, _ = self.assignment_dag_sample()
        def omit(body):
            body["command_payload"]["proposed_object_refs"].pop()
            body["command_payload"]["events"].pop()
        self.replace_dag_command(proposed, content, omit)
        with self.assertRaisesRegex(ReferenceRejected, "COMPLETE_EXACT_COMMAND_CONTENT_REQUIRED"):
            self.dispatch.union_closure(proposed, **parameters)

    def test_union_scope_cannot_be_selected_independently_of_command(self):
        proposed, parameters, _, _ = self.assignment_dag_sample()
        with self.assertRaisesRegex(ReferenceRejected, "UNION_SCOPE_MUST_EQUAL_EXACT_COMMAND"):
            self.dispatch.union_closure(proposed, **{**parameters, "command_kind": "TRANSITION"})

    def test_command_proposed_ref_set_order_is_distinct_from_union_sequence(self):
        proposed, parameters, content, _ = self.assignment_dag_sample()
        body = json.loads(content["command_envelope"]["body_raw"])
        self.assertEqual(body["command_payload"]["proposed_object_refs"], self.dispatch.reference_set(proposed[:-1]))
        self.assertNotEqual(body["command_payload"]["proposed_object_refs"], proposed[:-1])
        self.dispatch.union_closure(proposed, **parameters)
        self.replace_dag_command(proposed, content, lambda body: body["command_payload"]["proposed_object_refs"].reverse())
        with self.assertRaisesRegex(ReferenceRejected, "COMPLETE_EXACT_COMMAND_CONTENT_REQUIRED"):
            self.dispatch.union_closure(proposed, **parameters)

    def test_actual_body_edges_and_adversarial_order_only_edges_form_rejected_union_cycle(self):
        proposed, parameters, _, _ = self.assignment_dag_sample()
        registry = copy.deepcopy(self.registry)
        profile = registry["order_only_precedence_profiles"]["BDB_BOOTSTRAP_PRECEDENCE_V2"]
        # Unqualified adversarial metadata; never a proposed legal V2 scope.
        # The real body hashes still form an acyclic Attempt->...->Command DAG.
        profile["scope"] = {"command_kind": "ACCEPT_ARTIFACTS", "commit_seq": 2, "expected_parent": parameters["expected_parent"]}
        profile["ordered_kind_groups"] = [["command_envelope"], ["attempt"]]
        challenge = CandidateReferenceDispatch(registry, self.schemas)
        with self.assertRaisesRegex(ReferenceRejected, "CURRENT_CONTENT_UNION_ORDER_REJECTED"):
            challenge.union_closure(proposed, **parameters)

    def test_exact_nf02_instance_chronology_without_activation(self):
        result, context, objects, heads, starts, commits = self.chronology_sample()
        before = copy.deepcopy((result, objects, heads, starts, commits))
        derived = self.dispatch.nf02_chronology(result, **context)
        self.assertEqual(derived["sequence"], [2, 3, 4, 5])
        self.assertEqual(before, (result, objects, heads, starts, commits))

    def test_cut_cannot_select_wrong_hash_campaign_policy_or_current_parent(self):
        result, context, _, heads, _, _ = self.chronology_sample()
        for field, value in (("accepted_head_hash", "0" * 64), ("campaign_id", "another-campaign"),
                             ("governing_policy_ref", self.reference("policy_revision")),
                             ("governing_spec_refs", [self.reference("schema_registry")]),
                             ("accepted_head_seq", True), ("kind", "EMPTY_HISTORY_CUT")):
            changed = copy.deepcopy(result)
            changed["result_input_history_cut"][field] = value
            with self.subTest(field=field), self.assertRaises(ReferenceRejected):
                self.dispatch.nf02_chronology(changed, **context)
        with self.assertRaisesRegex(ReferenceRejected, "CURRENT_COMMAND_PARENT_REQUIRED"):
            self.dispatch.nf02_chronology(result, **{**context, "current_parent": heads[4]})

    def test_content_presence_cannot_replace_prior_membership(self):
        for kind in ("assignment_manifest", "assignment_package_binding", "attempt", "lane_result_admission_evidence"):
            result, context, objects, _, _, _ = self.chronology_sample()
            objects[kind]["accepted_seq"] = 6
            with self.subTest(kind=kind), self.assertRaisesRegex(ReferenceRejected, "OBJECT_NOT_PRIOR_ON_CUT"):
                self.dispatch.nf02_chronology(result, **context)

    def test_started_requires_distinct_later_commit_and_exact_event(self):
        for change in ("same_commit", "late", "duplicate", "missing", "extra", "assignment_swap", "binding_swap", "attempt_swap"):
            result, context, _, _, starts, _ = self.chronology_sample()
            if change == "same_commit":
                starts[0]["commit_seq"] = 3
            elif change == "late":
                starts[0]["commit_seq"] = 5
            elif change == "duplicate":
                starts.append(copy.deepcopy(starts[0]))
            elif change == "missing":
                starts.clear()
            elif change == "extra":
                starts[0]["event"]["trusted"] = True
            else:
                field = {"assignment_swap": "assignment_ref", "binding_swap": "package_binding_ref", "attempt_swap": "attempt_ref"}[change]
                starts[0]["event"][field]["revision_digest"] = "0" * 64
            with self.subTest(change=change), self.assertRaises(ReferenceRejected):
                self.dispatch.nf02_chronology(result, **context)

    def test_prior_reader_cannot_substitute_body_schema_or_full_reference(self):
        for change in ("body", "schema", "reference", "unaccepted"):
            result, context, objects, _, _, _ = self.chronology_sample()
            evidence = objects["lane_result_admission_evidence"]
            if change == "body":
                body = json.loads(evidence["body_raw"])
                body["admission_evidence_id"] = "lane_result_admission_evidence_00000000-0000-4000-8000-000000000099"
                evidence["body_raw"] = json.dumps(body).encode()
            elif change == "schema":
                evidence["schema_raw"] += b" "
            elif change == "reference":
                evidence["ref"]["logical_id"] = "lane_result_admission_evidence_00000000-0000-4000-8000-000000000099"
            else:
                objects.pop("lane_result_admission_evidence")
            with self.subTest(change=change), self.assertRaises(ReferenceRejected):
                self.dispatch.nf02_chronology(result, **context)

    def test_all_131_actual_body_schema_and_domain_identities(self):
        for row in self.registry["contracts"]:
            with self.subTest(kind=row["kind"]):
                ref, raw, schema_raw, body = self.object_sample(row["kind"])
                self.assertEqual(self.dispatch.validate_object(ref, raw, schema_raw, offline_registry=self.offline), body)

    def test_body_bytes_schema_bytes_and_logical_id_substitution(self):
        ref, raw, schema_raw, body = self.object_sample()
        for changed_ref, changed_body, changed_schema in (
            ({**ref, "revision_digest": "0" * 64}, raw, schema_raw),
            (ref, raw, schema_raw + b" "),
            (ref, json.dumps({**body, "trusted": True}).encode(), schema_raw),
            ({**ref, "logical_id": "assignment_package_binding_00000000-0000-4000-8000-000000000099"}, raw, schema_raw),
        ):
            with self.assertRaises(ReferenceRejected):
                self.dispatch.validate_object(changed_ref, changed_body, changed_schema, offline_registry=self.offline)
        ref["logical_id"] = body["binding_id"]
        self.assertEqual(self.dispatch.validate_object(ref, raw, schema_raw, offline_registry=self.offline), body)

    def test_logical_id_requires_explicit_bound_identity_field(self):
        ref, raw, schema_raw, body = self.object_sample()
        ref["logical_id"] = body["binding_id"]
        unbound = CandidateReferenceDispatch(self.registry, self.schemas)
        with self.assertRaisesRegex(ReferenceRejected, "OWN_LOGICAL_ID_FIELD_NOT_BOUND"):
            unbound.validate_object(ref, raw, schema_raw, offline_registry=self.offline)
        wrong = CandidateReferenceDispatch(self.registry, self.schemas, identity_fields={"assignment_package_binding": "notes"})
        with self.assertRaisesRegex(ReferenceRejected, "OWN_LOGICAL_ID_FIELD_NOT_BOUND"):
            wrong.validate_object(ref, raw, schema_raw, offline_registry=self.offline)

    def test_nf02_prior_only_fields_are_registry_metadata(self):
        for kind, fields in (("assignment_package_binding", {"assignment_ref": "assignment_manifest"}),
                             ("lane_result_admission_evidence", {"assignment_ref": "assignment_manifest", "package_binding_ref": "assignment_package_binding"}),
                             ("bdb_audit_lane_result", {"admission_evidence_ref": "lane_result_admission_evidence"})):
            body = {field: self.reference(target) for field, target in fields.items()}
            refs = self.dispatch.material_references(kind, body)
            self.assertEqual({item["field"] for item in refs}, set(fields))
            for item in refs:
                self.assertEqual(item["ref_class"], "PRIOR_ACCEPTED_ONLY")
                self.assertFalse(item["same_commit"])
                self.assertNotIn("ref_class", item["reference"])
            changed = copy.deepcopy(body)
            changed[next(iter(fields))] = self.reference("attempt")
            with self.subTest(kind=kind), self.assertRaises(ReferenceRejected):
                self.dispatch.material_references(kind, changed)

    def test_old_or_caller_annotated_schema_identity_rejects(self):
        value = self.reference()
        for change in ({"schema_revision_ref": "BDB_SCHEMA_REGISTRY::assignment_package_binding/1"},
                       {"schema_revision_ref": {"kind": "schema", "revision_digest": "0" * 64}},
                       {"schema_revision_ref": {"kind": "schema", "revision_digest": value["schema_revision_ref"]["revision_digest"], "version": "2"}},
                       {"ref_class": "PRIOR_ACCEPTED_ONLY"}, {"trusted": True}, {"digest_profile": "RAW-SHA256"},
                       {"kind": "schema"}, {"kind": "binding"}, {"revision_digest": "A" * 64}):
            with self.subTest(change=change), self.assertRaises(ReferenceRejected):
                self.dispatch.validate({**value, **change})

    def test_cross_kind_schema_swap(self):
        value = self.reference()
        value["schema_revision_ref"] = self.reference("assignment_manifest")["schema_revision_ref"]
        with self.assertRaises(ReferenceRejected):
            self.dispatch.validate(value)

    def test_complete_identity_and_set_order(self):
        first = self.reference(logical=True)
        second = self.reference(logical=True)
        second["logical_id"] = second["logical_id"][:-1] + "2"
        self.assertFalse(self.dispatch.exact_equal(first, second))
        self.assertEqual(self.dispatch.reference_set([second, first]), [first, second])
        with self.assertRaises(ReferenceRejected):
            self.dispatch.reference_set([first, copy.deepcopy(first)])
        self.assertEqual(self.dispatch.validate(first), first)
        copy_out = self.dispatch.validate(first)
        copy_out["schema_revision_ref"]["revision_digest"] = "0" * 64
        self.assertEqual(self.dispatch.validate(first), first)

    def test_logical_kind_uuid_and_nullable_alias_reject(self):
        value = self.reference(logical=True)
        for logical in (None, "binding_00000000-0000-4000-8000-000000000001", value["logical_id"].replace("4000", "1000"), value["logical_id"].upper()):
            with self.subTest(logical=logical), self.assertRaises(ReferenceRejected):
                self.dispatch.validate({**value, "logical_id": logical})

    def test_exact_registry_coverage_and_no_inactive_binding(self):
        for mutation in ("omitted", "duplicate", "inactive", "wrong_key"):
            schemas = copy.deepcopy(self.schemas)
            if mutation == "omitted":
                schemas["bindings"].pop()
            elif mutation == "duplicate":
                schemas["bindings"].append(copy.deepcopy(schemas["bindings"][0]))
            elif mutation == "inactive":
                schemas["bindings"][0]["status"] = "RETIRED"
            else:
                schemas["bindings"][0]["schema_key"] = "BDB_SCHEMA_REGISTRY::unknown/1"
            with self.subTest(mutation=mutation), self.assertRaises(ReferenceRejected):
                CandidateReferenceDispatch(self.registry, schemas)


if __name__ == "__main__":
    unittest.main()

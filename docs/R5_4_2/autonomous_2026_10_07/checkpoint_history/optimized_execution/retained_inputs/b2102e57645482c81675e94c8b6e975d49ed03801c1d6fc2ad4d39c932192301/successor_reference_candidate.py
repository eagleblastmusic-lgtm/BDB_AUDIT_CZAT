"""Isolated exact successor TypedRef dispatch; no activation/history authority."""
from __future__ import annotations

import copy
import hashlib
import hmac
import sys
from types import MappingProxyType

from jsonschema import Draft202012Validator
from referencing import Registry
from referencing.exceptions import NoSuchResource
import re

from execution import ROOT, canonical
from bootstrap_instance_design import DraftOrderingContext, values
from transition_contract import GUARDS, table
from nf02_result_normalizer import ASSIGNMENT_CLAIMS, normalize, read_bound_raw, validate_package

sys.path.insert(0, str(ROOT / "src"))
from bdb_audit.core.canonical_json import parse  # noqa: E402
from bdb_audit.core.hashing import _domain_digest  # noqa: E402
from bdb_audit.history.closure import ClosureNode, canonical_order  # noqa: E402

DIGEST = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[a-z][a-z0-9_]{0,63}_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")


class ReferenceRejected(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise ReferenceRejected(reason)


class CandidateReferenceDispatch:
    """Use a supplied exact candidate binding set as a read-only test input.

    This establishes syntactic identity/dispatch, not independent qualification,
    accepted membership, actor authority, provenance or campaign eligibility.
    Runtime integration must obtain these roots from qualified installation.
    """
    def __init__(self, registry, schema_registry, *, identity_fields=None):
        rows = registry["contracts"]
        by_kind = {}
        for row in rows:
            kind = row["kind"]
            require(kind not in by_kind, "DUPLICATE_ACTIVE_KIND")
            require(row["schema_ref"] == "BDB_SCHEMA_REGISTRY::" + kind + "/" + row["version"], "REGISTRY_SCHEMA_KEY_MISMATCH")
            by_kind[kind] = copy.deepcopy(row)
        bindings = schema_registry["bindings"]
        keys = [binding["schema_key"] for binding in bindings]
        require(keys == sorted(set(keys), key=lambda key: key.encode("utf-8")), "SCHEMA_BINDING_ORDER_OR_DUPLICATE")
        by_key = {binding["schema_key"]: binding for binding in bindings}
        require(set(by_key) == {row["schema_ref"] for row in rows}, "SCHEMA_BINDING_COVERAGE")
        self._schemas = {}
        for kind, row in by_kind.items():
            binding = by_key[row["schema_ref"]]
            require(binding["status"] == "ACTIVE", "INACTIVE_SCHEMA_BINDING")
            raw = binding["schema_raw_ref"]
            require(type(raw["raw_digest"]) is str and DIGEST.fullmatch(raw["raw_digest"]), "INVALID_SCHEMA_RAW_DIGEST")
            self._schemas[kind] = (row["version"], raw["raw_digest"])
        self._schemas = MappingProxyType(self._schemas)
        self._schema_registry_digest = _domain_digest("schema_registry", "2", schema_registry,
                                                      registry_kind="schema_registry")
        self._identity_fields = MappingProxyType(copy.deepcopy(identity_fields or {}))
        self._ordering = DraftOrderingContext(by_kind, copy.deepcopy(registry["order_only_precedence_profiles"]["BDB_BOOTSTRAP_PRECEDENCE_V2"]))
        self._material = MappingProxyType({kind: tuple((rule["field"], tuple(rule["allowed_keys"]),
                                                       rule["ref_class"], rule["same_commit"])
                                                      for rule in row["material_refs"] if rule["representation"] == "TypedRef")
                                           for kind, row in by_kind.items()})

    def validate(self, value):
        require(type(value) is dict, "TYPED_REF_REQUIRED")
        required = {"kind", "revision_digest", "digest_profile", "schema_revision_ref"}
        require(required <= value.keys() and set(value) <= required | {"logical_id"}, "TYPED_REF_CLOSED_SHAPE")
        kind = value["kind"]
        require(type(kind) is str and kind in self._schemas, "UNKNOWN_ACTIVE_TYPED_KIND")
        require(type(value["revision_digest"]) is str and DIGEST.fullmatch(value["revision_digest"]), "INVALID_OBJECT_DIGEST")
        require(type(value["digest_profile"]) is str and value["digest_profile"] == "BDB-OBJECT-DIGEST-1", "WRONG_OBJECT_DIGEST_PROFILE")
        schema = value["schema_revision_ref"]
        require(type(schema) is dict and set(schema) == {"kind", "revision_digest"}, "CLOSED_SCHEMA_RAW_REF_REQUIRED")
        require(type(schema["kind"]) is str and schema["kind"] == "schema", "SCHEMA_RAW_DOMAIN_REQUIRED")
        require(type(schema["revision_digest"]) is str and DIGEST.fullmatch(schema["revision_digest"]), "INVALID_SCHEMA_RAW_DIGEST")
        require(schema["revision_digest"] == self._schemas[kind][1], "EXACT_TYPED_SCHEMA_BINDING_REQUIRED")
        if "logical_id" in value:
            logical = value["logical_id"]
            require(type(logical) is str and ID.fullmatch(logical) and logical.startswith(kind + "_"), "LOGICAL_ID_KIND_OR_UUID_MISMATCH")
        return copy.deepcopy(value)

    def validate_object(self, value, body_raw, schema_raw, *, offline_registry=None):
        ref = self.validate(value)
        require(type(body_raw) is bytes and type(schema_raw) is bytes, "EXACT_OBJECT_AND_SCHEMA_BYTES_REQUIRED")
        require(hashlib.sha256(schema_raw).hexdigest() == ref["schema_revision_ref"]["revision_digest"], "SCHEMA_BYTE_SUBSTITUTION")
        body = parse(body_raw)
        schema = parse(schema_raw)
        kind = ref["kind"]
        version = self._schemas[kind][0]
        require(schema["$id"] == "BDB_SCHEMA_REGISTRY::" + kind + "/" + version, "EXECUTABLE_SCHEMA_DISPATCH_MISMATCH")
        if offline_registry is None:
            def deny(uri):
                raise NoSuchResource(ref=uri)
            offline_registry = Registry(retrieve=deny)
        try:
            Draft202012Validator(schema, registry=offline_registry).validate(body)
        except Exception as error:
            raise ReferenceRejected("OBJECT_SCHEMA_OR_OFFLINE_RESOLUTION_FAILED") from error
        require(_domain_digest(kind, version, body, registry_kind=kind) == ref["revision_digest"], "OBJECT_DOMAIN_DIGEST_MISMATCH")
        if "logical_id" in ref:
            field = self._identity_fields.get(kind)
            require(type(field) is str and field in schema.get("required", [])
                    and field in schema.get("properties", {}), "OWN_LOGICAL_ID_FIELD_NOT_BOUND")
            require(body.get(field) == ref["logical_id"], "OBJECT_LOGICAL_ID_MISMATCH")
        return copy.deepcopy(body)

    def material_references(self, kind, body, *, schema_raw=None, offline_registry=None):
        """Check declared present TypedRef paths; never infer refs from shape.

        Body/schema cardinality, conditional presence, cut membership and
        producer rules are separate conjuncts, not established by this method.
        """
        require(kind in self._material, "UNKNOWN_ACTIVE_TYPED_KIND")
        result = []
        for field, allowed, ref_class, same_commit in self._material[kind]:
            for value in values(body, field.replace("[]", "").split(".")):
                if value is None:
                    # Nullable initial sentinels are not object references.
                    # Optional cardinality alone never authorizes null: the
                    # exact own schema must validate the entire represented body.
                    require(type(schema_raw) is bytes and hashlib.sha256(schema_raw).hexdigest() == self._schemas[kind][1],
                            "EXACT_NULLABLE_OWN_SCHEMA_REQUIRED")
                    schema = parse(schema_raw)
                    require(schema["$id"] == "BDB_SCHEMA_REGISTRY::" + kind + "/" + self._schemas[kind][0], "EXECUTABLE_SCHEMA_DISPATCH_MISMATCH")
                    try:
                        def deny(uri):
                            raise NoSuchResource(ref=uri)
                        Draft202012Validator(schema, registry=offline_registry or Registry(retrieve=deny)).validate(body)
                    except Exception as error:
                        raise ReferenceRejected("NULL_NOT_PERMITTED_BY_EXACT_BODY_SCHEMA") from error
                    continue
                ref = self.validate(value)
                target = ref["kind"] + "/" + self._schemas[ref["kind"]][0]
                require(target in allowed, "MATERIAL_REFERENCE_TARGET_OR_VERSION")
                result.append({"field": field, "reference": ref, "ref_class": ref_class,
                               "same_commit": same_commit})
        return result

    def union_closure(self, proposed, *, read_content, input_cut, read_context, campaign_id,
                      read_accepted, installation_refs, command_kind, commit_seq,
                      expected_parent, offline_registry=None):
        """Exact body-derived same-commit DAG, using the existing union Kahn sort.

        Installation pins and prior readers must be authenticated separately.
        This checks declared TypedRef edges and exact ordered content, not
        producer eligibility, complete external/raw resolver closure or writes.
        """
        require(type(proposed) is list and proposed, "NONEMPTY_CURRENT_CONTENT_CLOSURE_REQUIRED")
        refs = self.reference_set(proposed)
        # Different optional header presentations cannot duplicate one body.
        require(len({(r["kind"], r["revision_digest"]) for r in refs}) == len(refs), "DUPLICATE_OBJECT_BODY_IDENTITY")
        pins = self.reference_set(installation_refs)
        if input_cut is not None:
            self.accepted_cut(input_cut, campaign_id=campaign_id, read_context=read_context)
            require(type(commit_seq) is int and commit_seq == input_cut["accepted_head_seq"] + 1
                    and expected_parent == {"campaign_id": campaign_id, "commit_seq": input_cut["accepted_head_seq"],
                                            "commit_hash": input_cut["accepted_head_hash"]}, "CLOSURE_CURRENT_COMMAND_INPUT_REQUIRED")
        else:
            require(command_kind == "INITIALIZE_CAMPAIGN_FROM_LEGACY" and type(commit_seq) is int
                    and commit_seq == 1 and expected_parent == "EMPTY_HISTORY", "CLOSURE_INITIALIZATION_SCOPE_REQUIRED")
        by_ref = {self.identity_key(r): canonical(r).hex() for r in refs}
        nodes, edges, commands = [], set(), []
        for ref in refs:
            record = read_content(copy.deepcopy(ref))
            require(type(record) is dict and set(record) == {"ref", "body_raw", "schema_raw"}
                    and self.exact_equal(record["ref"], ref), "EXACT_CURRENT_CONTENT_RECORD_REQUIRED")
            body = self.validate_object(ref, record["body_raw"], record["schema_raw"], offline_registry=offline_registry)
            if ref["kind"] == "command_envelope":
                commands.append((ref, body))
            node_id, deps = by_ref[self.identity_key(ref)], set()
            for rule in self.material_references(ref["kind"], body, schema_raw=record["schema_raw"], offline_registry=offline_registry):
                target = rule["reference"]
                current = by_ref.get(self.identity_key(target))
                if rule["ref_class"] == "PINNED_INSTALLATION_REF" or (input_cut is None and rule["ref_class"] == "HISTORY_CONTEXT_BINDING"):
                    # A byte-identical root copy in this transaction cannot
                    # confer its own authority. The independent external pin
                    # must already match; this is not a content/prior edge.
                    require(target in pins, "INDEPENDENT_EXACT_INSTALLATION_PIN_REQUIRED")
                elif current is not None:
                    require(rule["same_commit"] and rule["ref_class"] in {"CONTENT_OBJECT", "CONTENT_OR_PRIOR"},
                            "PRIOR_OR_INSTALLED_REF_IN_CURRENT_CLOSURE")
                    require(current != node_id, "SELF_CONTENT_REFERENCE")
                    deps.add(current)
                    edges.add((current, node_id))
                elif rule["ref_class"] == "CONTENT_OBJECT":
                    raise ReferenceRejected("MISSING_REQUIRED_CURRENT_CONTENT")
                else:
                    require(input_cut is not None, "PRIOR_REF_CANNOT_BOOTSTRAP_EMPTY_HISTORY")
                    self.prior_object(target, input_cut, read_accepted=read_accepted, offline_registry=offline_registry)
            nodes.append(ClosureNode(node_id, ref["kind"], ref.get("logical_id", ""), ref["revision_digest"], tuple(sorted(deps))))
        require(len(commands) == 1 and commands[0][1]["command_kind"] == command_kind
                and commands[0][1]["expected_parent_head"] == expected_parent, "UNION_SCOPE_MUST_EQUAL_EXACT_COMMAND")
        command_ref, command = commands[0]
        facts = [ref for ref in proposed if not self.exact_equal(ref, command_ref)]
        require(command["command_payload"]["proposed_object_refs"] == self.reference_set(facts),
                "COMPLETE_EXACT_COMMAND_CONTENT_REQUIRED")
        events = command["command_payload"]["events"]
        artifacts = [event["artifact_ref"] for event in events if "artifact_ref" in event]
        require(artifacts == facts and all("artifact_ref" in event for event in events[:len(facts)]),
                "DETERMINISTIC_ARTIFACT_EVENT_ORDER_REQUIRED")
        if input_cut is None:
            require(command["proposed_campaign_id"] == campaign_id, "UNION_INITIAL_CAMPAIGN_NAMESPACE_CONFLICT")
        else:
            require(command["governing_policy_ref"] == input_cut["governing_policy_ref"]
                    and command["governing_spec_refs"] == input_cut["governing_spec_refs"], "UNION_COMMAND_GOVERNING_CONTEXT_CONFLICT")
            campaign, _ = self.prior_object(command["campaign_ref"], input_cut, read_accepted=read_accepted, offline_registry=offline_registry)
            require(campaign["campaign_id"] == campaign_id, "UNION_COMMAND_CAMPAIGN_NAMESPACE_CONFLICT")
        expected = [by_ref[self.identity_key(r)] for r in proposed]
        try:
            ordered = canonical_order(nodes, command_kind=command_kind, commit_seq=commit_seq,
                                      expected_parent=expected_parent, profile_name="BDB_BOOTSTRAP_PRECEDENCE_V2",
                                      expected=expected, registry=self._ordering)
        except Exception as error:
            raise ReferenceRejected("CURRENT_CONTENT_UNION_ORDER_REJECTED") from error
        return {"ordered_refs": copy.deepcopy(proposed), "typed_edges": sorted(edges), "node_count": len(ordered)}

    def identity_key(self, value):
        ref = self.validate(value)
        return (ref["kind"], ref.get("logical_id", ""), ref["revision_digest"], ref["digest_profile"], canonical(ref["schema_revision_ref"]))

    def exact_equal(self, first, second):
        return self.validate(first) == self.validate(second)

    def reference_set(self, values):
        refs = [self.validate(value) for value in values]
        ordered = sorted(refs, key=self.identity_key)
        keys = [self.identity_key(value) for value in ordered]
        require(len(keys) == len(set(keys)), "DUPLICATE_EXACT_TYPED_IDENTITY")
        return ordered

    def accepted_cut(self, cut, *, read_context, campaign_id, current_parent=None):
        """Compare a represented cut with an independently supplied history reader.

        The reader must come from qualified accepted history in runtime. Tests
        supply immutable unqualified snapshots; this method cannot establish
        installation/actor authority or turn content storage into membership.
        """
        keys = {"campaign_id", "accepted_head_seq", "accepted_head_hash",
                "governing_policy_ref", "governing_spec_refs"}
        require(type(cut) is dict and set(cut) == keys, "CLOSED_ACCEPTED_CUT_REQUIRED")
        require(cut["campaign_id"] == campaign_id, "CROSS_CAMPAIGN_CUT")
        seq = cut["accepted_head_seq"]
        require(type(seq) is int and 1 <= seq <= 9007199254740991, "INVALID_ACCEPTED_CUT_SEQUENCE")
        require(type(cut["accepted_head_hash"]) is str and DIGEST.fullmatch(cut["accepted_head_hash"]), "INVALID_ACCEPTED_CUT_HASH")
        policy = self.validate(cut["governing_policy_ref"])
        require(policy["kind"] == "policy_revision", "CUT_POLICY_TARGET")
        specs = cut["governing_spec_refs"]
        require(type(specs) is list and specs and all(self.validate(ref)["kind"] == "spec_revision" for ref in specs), "CUT_SPEC_TARGET")
        require(specs == self.reference_set(specs), "CUT_SPEC_SET_ORDER")
        expected = read_context(campaign_id, seq)
        require(type(expected) is dict and cut == expected, "ACCEPTED_CUT_CONTEXT_MISMATCH")
        if current_parent is not None:
            require(cut == current_parent, "CURRENT_COMMAND_PARENT_REQUIRED")
        return copy.deepcopy(cut)

    def prior_object(self, ref, cut, *, read_accepted, offline_registry=None, include_schema=False):
        """Verify exact bytes and membership supplied by the accepted reader."""
        ref = self.validate(ref)
        record = read_accepted(copy.deepcopy(ref), copy.deepcopy(cut))
        require(type(record) is dict and set(record) == {"ref", "body_raw", "schema_raw", "accepted_seq"}, "ACCEPTED_OBJECT_RECORD_REQUIRED")
        require(self.exact_equal(record["ref"], ref), "ACCEPTED_FULL_REFERENCE_MISMATCH")
        seq = record["accepted_seq"]
        require(type(seq) is int and 1 <= seq <= cut["accepted_head_seq"], "OBJECT_NOT_PRIOR_ON_CUT")
        body = self.validate_object(ref, record["body_raw"], record["schema_raw"], offline_registry=offline_registry)
        return (body, seq, record["schema_raw"]) if include_schema else (body, seq)

    def nf02_chronology(self, result, *, campaign_id, current_parent, read_context,
                        read_accepted, read_starts, offline_registry=None):
        """Exercise Data 192 E.2/E.4 chronology on exact candidate instances.

        Requires a schema-validated result body. Returns derived context for
        later raw/producer/FSM/knowledge predicates; does not assert those
        predicates, durable acceptance, authorization or application readiness.
        No callback has a write role and no successor activation occurs.
        """
        def cut(value, parent=None):
            return self.accepted_cut(value, read_context=read_context, campaign_id=campaign_id, current_parent=parent)

        def prior(ref, value):
            return self.prior_object(ref, value, read_accepted=read_accepted, offline_registry=offline_registry)

        result_cut = cut(result["result_input_history_cut"], current_parent)
        evidence_ref = self.validate(result["admission_evidence_ref"])
        require(evidence_ref["kind"] == "lane_result_admission_evidence", "RESULT_EVIDENCE_TARGET")
        evidence, evidence_seq = prior(evidence_ref, result_cut)
        admission_cut = cut(evidence["admission_input_history_cut"])
        require(admission_cut["accepted_head_seq"] + 1 == evidence_seq, "EVIDENCE_COMMAND_INPUT_CUT")
        derived = self._nf02_bound_execution(evidence_ref, evidence, admission_cut,
                                            read_context=read_context, read_accepted=read_accepted,
                                            read_starts=read_starts, campaign_id=campaign_id, offline_registry=offline_registry)
        require(derived["sequence"][-1] < evidence_seq <= result_cut["accepted_head_seq"], "NF02_DISTINCT_COMMIT_CHRONOLOGY")
        derived["sequence"].append(evidence_seq)
        return derived

    def _nf02_bound_execution(self, evidence_ref, evidence, admission_cut, *, read_context,
                              read_accepted, read_starts, campaign_id, offline_registry=None):
        """Resolve earlier A/B/STARTED without asserting acceptance of E.

        Callers first validate the exact E body/schema and its governing cut.
        This shared read-only path serves proposal checks and historical replay.
        """
        def cut(value):
            return self.accepted_cut(value, read_context=read_context, campaign_id=campaign_id)

        def prior(ref, value):
            return self.prior_object(ref, value, read_accepted=read_accepted, offline_registry=offline_registry)

        binding_ref = self.validate(evidence["package_binding_ref"])
        require(binding_ref["kind"] == "assignment_package_binding", "EVIDENCE_BINDING_TARGET")
        binding, binding_seq = prior(binding_ref, admission_cut)
        binding_cut = cut(binding["binding_input_history_cut"])
        require(binding_cut["accepted_head_seq"] + 1 == binding_seq, "BINDING_COMMAND_INPUT_CUT")
        require(self.exact_equal(binding["assignment_ref"], evidence["assignment_ref"]), "NF02_ASSIGNMENT_IDENTITY_CONFLICT")
        assignment_ref = self.validate(binding["assignment_ref"])
        require(assignment_ref["kind"] == "assignment_manifest", "BINDING_ASSIGNMENT_TARGET")
        assignment, assignment_seq = prior(assignment_ref, binding_cut)
        require(evidence["result_slot_contract_ref"] in assignment["result_slot_contract_refs"], "NF02_SLOT_NOT_DECLARED")
        attempt_ref = self.validate(assignment["attempt_ref"])
        require(attempt_ref["kind"] == "attempt", "ASSIGNMENT_ATTEMPT_TARGET")
        attempt, _ = prior(attempt_ref, binding_cut)
        require(evidence["result_slot_contract_ref"] in attempt["result_slot_contracts"], "NF02_SLOT_NOT_ASSIGNED_TO_ATTEMPT")
        starts = read_starts(copy.deepcopy(attempt_ref), copy.deepcopy(admission_cut))
        require(type(starts) is list and len(starts) == 1, "ONE_PRIOR_STARTED_TRANSITION_REQUIRED")
        started = starts[0]
        require(type(started) is dict and set(started) == {"commit_seq", "event"}, "STARTED_RECORD_REQUIRED")
        event = started["event"]
        require(type(event) is dict and set(event) == {"event_type", "attempt_ref", "assignment_ref", "package_binding_ref"}
                and event["event_type"] == "AttemptStarted", "CLOSED_STARTED_EVENT_REQUIRED")
        require(type(started["commit_seq"]) is int and binding_seq < started["commit_seq"] <= admission_cut["accepted_head_seq"], "BINDING_MUST_PRECEDE_STARTED")
        require(self.exact_equal(event["attempt_ref"], attempt_ref)
                and self.exact_equal(event["assignment_ref"], assignment_ref)
                and self.exact_equal(event["package_binding_ref"], binding_ref), "STARTED_EXACT_CONTEXT_REQUIRED")
        require(assignment_seq < binding_seq < started["commit_seq"] <= admission_cut["accepted_head_seq"], "NF02_DISTINCT_COMMIT_CHRONOLOGY")
        return {"assignment": assignment, "binding": binding, "attempt": attempt, "evidence": evidence,
                "assignment_ref": assignment_ref, "binding_ref": binding_ref, "evidence_ref": evidence_ref,
                "sequence": [assignment_seq, binding_seq, started["commit_seq"]]}

    def nf02_assignment_scope(self, derived, *, campaign_ref, campaign_id, read_context,
                             read_accepted, read_history, offline_registry=None):
        """Data 192 E.2 exact run/source/spec/executor/delivery identities.

        Qualified reader/actor/source eligibility, full FSM, grant/exposure and
        isolation semantics remain independent required predicates.
        """
        assignment, attempt = derived["assignment"], derived["attempt"]
        cut = self.accepted_cut(derived["binding"]["binding_input_history_cut"],
                                read_context=read_context, campaign_id=campaign_id)

        def prior_record(ref, at=None):
            return self.prior_object(ref, cut if at is None else at, read_accepted=read_accepted,
                                     offline_registry=offline_registry, include_schema=True)

        def prior(ref, at=None):
            return prior_record(ref, at)[0]

        def own_input(value, seq):
            represented = self.accepted_cut(value, read_context=read_context, campaign_id=campaign_id)
            require(represented["accepted_head_seq"] + 1 == seq, "NF02_CONTEXT_OWN_COMMAND_INPUT_REQUIRED")
            return represented

        self.material_references("assignment_manifest", assignment)
        campaign_ref = self.validate(campaign_ref)
        require(campaign_ref["kind"] in ("campaign_genesis", "successor_campaign_genesis"), "NF02_CAMPAIGN_TARGET")
        lane = prior(attempt["lane_run_ref"])
        require(attempt["lane_run_ref"]["kind"] == "lane_run", "NF02_LANE_RUN_TARGET")
        stage = prior(lane["stage_run_ref"])
        require(lane["stage_run_ref"]["kind"] == "stage_run", "NF02_STAGE_RUN_TARGET")
        require(self.exact_equal(stage["campaign_ref"], campaign_ref), "NF02_ACTIVE_CAMPAIGN_CONFLICT")
        campaign = prior(campaign_ref)
        require(campaign["campaign_id"] == campaign_id, "NF02_CAMPAIGN_NAMESPACE_CONFLICT")
        assignment_cut = own_input(assignment["assignment_input_history_cut"], derived["sequence"][0])
        require(self.exact_equal(assignment["source_generation_ref"], lane["source_generation_ref"])
                and self.exact_equal(assignment["source_generation_ref"], stage["source_generation_ref"]), "NF02_RUN_SOURCE_CONFLICT")
        require(self.exact_equal(campaign["source_generation_ref"], assignment["source_generation_ref"]), "NF02_CAMPAIGN_FROZEN_SOURCE_CONFLICT")
        require(self.exact_equal(assignment["lane_spec_ref"], lane["lane_spec_ref"])
                and self.exact_equal(assignment["stage_spec_ref"], stage["stage_spec_ref"]), "NF02_RUN_SPEC_CONFLICT")
        require(self.exact_equal(assignment["executor_profile_ref"], attempt["executor_profile_ref"])
                and self.exact_equal(assignment["delivery_profile_ref"], attempt["delivery_profile_ref"]), "NF02_ATTEMPT_PROFILE_CONFLICT")
        prior(assignment["source_generation_ref"])
        for field in ("lane_spec_ref", "stage_spec_ref", "executor_profile_ref", "delivery_profile_ref"):
            prior(assignment[field], assignment_cut)
        knowledge, knowledge_seq, knowledge_schema = prior_record(assignment["knowledge_state_ref"])
        self.material_references("knowledge_state", knowledge, schema_raw=knowledge_schema, offline_registry=offline_registry)
        knowledge_cut = own_input(knowledge["basis_history_cut"], knowledge_seq)
        require(self.exact_equal(knowledge["attempt_ref"], assignment["attempt_ref"]), "NF02_KNOWLEDGE_ATTEMPT_CONFLICT")

        def same_attempt(body, reason):
            require(self.exact_equal(body["attempt_ref"], assignment["attempt_ref"]), reason)

        self.knowledge_predecessor(knowledge, campaign_id=campaign_id, read_context=read_context,
                                   read_accepted=read_accepted, read_history=read_history, offline_registry=offline_registry)
        previous = knowledge.get("previous_knowledge_state_ref")
        if previous is not None:
            same_attempt(prior(previous, knowledge_cut), "NF02_PREVIOUS_KNOWLEDGE_ATTEMPT_CONFLICT")
        isolation, isolation_seq, _ = prior_record(knowledge["isolation_qualification_ref"])
        own_input(isolation["assessment_input_history_cut"], isolation_seq)
        same_attempt(isolation, "NF02_ISOLATION_ATTEMPT_CONFLICT")
        require(self.exact_equal(isolation["executor_profile_ref"], assignment["executor_profile_ref"])
                and self.exact_equal(isolation["delivery_profile_ref"], assignment["delivery_profile_ref"]), "NF02_ISOLATION_PROFILE_CONFLICT")

        def grant_context(ref):
            grant, seq, schema = prior_record(ref)
            self.material_references("grant_body", grant, schema_raw=schema, offline_registry=offline_registry)
            at = own_input(grant["grant_input_history_cut"], seq)
            same_attempt(grant, "NF02_GRANT_CONTEXT_CONFLICT")
            require(self.exact_equal(grant["delivery_profile_ref"], assignment["delivery_profile_ref"]), "NF02_GRANT_CONTEXT_CONFLICT")
            self.grant_predecessor(grant, campaign_id=campaign_id, read_context=read_context,
                                   read_accepted=read_accepted, read_history=read_history, offline_registry=offline_registry)
            if grant["previous_knowledge_state_ref"] is not None:
                same_attempt(prior(grant["previous_knowledge_state_ref"], at), "NF02_GRANT_PREVIOUS_KNOWLEDGE_CONFLICT")
            prior(grant["view_manifest_ref"])
            return grant

        for ref in assignment["grant_refs"]:
            grant_context(ref)
        for ref in knowledge["potential_exposure_refs"]:
            exposure, seq, schema = prior_record(ref)
            self.material_references("potential_exposure_record", exposure, schema_raw=schema, offline_registry=offline_registry)
            own_input(exposure["exposure_input_history_cut"], seq)
            same_attempt(exposure, "NF02_EXPOSURE_ATTEMPT_CONFLICT")
            grant = grant_context(exposure["grant_ref"])
            require(self.exact_equal(exposure["view_manifest_ref"], grant["view_manifest_ref"])
                    and exposure["channel_class"] == grant["channel_class"], "NF02_EXPOSURE_GRANT_VIEW_OR_CHANNEL_CONFLICT")
            if "previous_knowledge_state_ref" in exposure:
                require(exposure["previous_knowledge_state_ref"] == grant["previous_knowledge_state_ref"], "NF02_EXPOSURE_PREVIOUS_KNOWLEDGE_CONFLICT")
        for ref in knowledge["contamination_assessment_refs"]:
            assessment, seq, _ = prior_record(ref)
            own_input(assessment["assessment_input_history_cut"], seq)
            same_attempt(assessment, "NF02_CONTAMINATION_ATTEMPT_CONFLICT")
        for ref in knowledge["allowed_view_refs"]:
            prior(ref)
        for ref in assignment["view_manifest_refs"]:
            prior(ref)
        inventory = self.knowledge_exposure_inventory(assignment["knowledge_state_ref"], knowledge,
            campaign_id=campaign_id, read_context=read_context, read_accepted=read_accepted,
            read_history=read_history, offline_registry=offline_registry)
        return {"lane_run_ref": copy.deepcopy(attempt["lane_run_ref"]), "stage_run_ref": copy.deepcopy(lane["stage_run_ref"]),
                "campaign_ref": campaign_ref, "source_generation_ref": copy.deepcopy(assignment["source_generation_ref"]),
                "knowledge_inventory": inventory}

    def principal_context(self, actor_ref, actor_raw, schema_raw, *, expected_actor_pin, expected_schema_digest,
                          authenticated_principal_id, expected_namespace_pin, required_operation, required_role,
                          offline_registry=None):
        """Compare actual principal bytes to independently installed/authenticated inputs.

        Expected pins and authenticated identity are runtime trust-boundary
        inputs, never derived from the proposed command/profile. This isolated
        comparison neither authenticates that boundary nor qualifies a producer.
        Approval purposes/actions/scopes use a separate required guard; this
        primitive cannot authorize APPROVE or infer it from a general role.
        """
        def pin(value, family):
            require(type(value) is dict and set(value) == {"profile_id", "revision_digest"}
                    and value["profile_id"] == family and type(value["revision_digest"]) is str
                    and DIGEST.fullmatch(value["revision_digest"]), "EXACT_PRINCIPAL_PROFILE_PIN_REQUIRED")
        pin(expected_actor_pin, "PRINCIPAL_AUTHORIZATION_V2")
        pin(actor_ref, "PRINCIPAL_AUTHORIZATION_V2")
        pin(expected_namespace_pin, "BOOTSTRAP_NAMESPACE_V2")
        require(actor_ref == expected_actor_pin, "ACTOR_NOT_INDEPENDENTLY_INSTALLED")
        require(type(actor_raw) is bytes and hashlib.sha256(actor_raw).hexdigest() == expected_actor_pin["revision_digest"],
                "PRINCIPAL_RAW_IDENTITY_CONFLICT")
        require(type(schema_raw) is bytes and type(expected_schema_digest) is str and DIGEST.fullmatch(expected_schema_digest)
                and hashlib.sha256(schema_raw).hexdigest() == expected_schema_digest, "PRINCIPAL_SCHEMA_PIN_REQUIRED")
        schema, body = parse(schema_raw), parse(actor_raw)
        require(schema.get("$id") == "BDB_EXTERNAL_PROFILE_SCHEMA::PRINCIPAL_AUTHORIZATION_V2", "PRINCIPAL_SCHEMA_FAMILY_CONFLICT")
        require(Draft202012Validator(schema, registry=offline_registry or Registry()).is_valid(body), "CLOSED_PRINCIPAL_BODY_REQUIRED")
        require(required_operation in {"INITIALIZE", "ACCEPT", "TRANSITION", "INGEST"}
                and required_operation in body["permitted_operations"], "PRINCIPAL_OPERATION_NOT_AUTHORIZED")
        require(type(authenticated_principal_id) is str and authenticated_principal_id
                and body["principal_id"] == authenticated_principal_id and body["role"] == required_role,
                "AUTHENTICATED_PRINCIPAL_OR_ROLE_CONFLICT")
        require(body["namespace_profile_ref"] == expected_namespace_pin, "PRINCIPAL_NAMESPACE_CONFLICT")
        return {"actor_ref": copy.deepcopy(actor_ref), "principal_id": body["principal_id"], "role": body["role"],
                "operation": required_operation, "namespace_profile_ref": copy.deepcopy(expected_namespace_pin)}

    def nf02_lane_completion_context(self, completion_ref, body_raw, schema_raw, *, campaign_id,
                                      current_parent, read_context, read_accepted, read_history,
                                      transition_pin, transition_raw, predicate_pin, predicate_raw,
                                      predicate_schema_raw, predicate_schema_digest, read_raw, read_starts,
                                      slot_instances, package_transport_pin, semantic_pin, offline_registry=None):
        """Check exact NF02 lane output/current-knowledge bindings, without L7.

        Restricted to NF02 slots. Qualified producer/history, per-result raw/FSM
        proof, all relevant Attempt inventory, required non-result outputs,
        purpose policy and isolation truth remain independent requirements.
        No SATISFIED token can turn this projection into full completion.
        """
        require(self.validate(completion_ref)["kind"] == "lane_completion", "NF02_LANE_COMPLETION_TARGET")
        body = self.validate_object(completion_ref, body_raw, schema_raw, offline_registry=offline_registry)
        cut = self.accepted_cut(body["input_history_cut"], campaign_id=campaign_id,
                                read_context=read_context, current_parent=current_parent)
        prefix = self.accepted_prefix(cut, campaign_id=campaign_id, read_context=read_context,
            read_accepted=read_accepted, read_history=read_history, offline_registry=offline_registry)
        require(type(transition_pin) is dict and set(transition_pin) == {"profile_id", "revision_digest"}
                and transition_pin["profile_id"] == "FULL_PATH_TRANSITION_TABLE_V2"
                and type(transition_raw) is bytes
                and hashlib.sha256(transition_raw).hexdigest() == transition_pin["revision_digest"],
                "NF02_COMPLETION_TRANSITION_PIN_REQUIRED")
        profile = parse(transition_raw)
        require(profile["transitions"] == table()[0] and profile["guard_contracts"] == GUARDS,
                "EXACT_NORMATIVE_TRANSITION_TABLE_REQUIRED")
        edges = {(row["from_state"], row["to_state"]) for row in profile["transitions"] if row["aggregate_kind"] == "LANE_RUN"}
        state = None
        for _, commit, input_cut, facts in prefix:
            by_ref = {self.identity_key(ref): fact for ref, fact in facts}
            for event in commit["ordered_event_bodies"]:
                if "artifact_ref" in event:
                    ref = event["artifact_ref"]
                    fact = by_ref[self.identity_key(ref)]
                    if ref == body["lane_run_ref"]:
                        require(state is None, "NF02_COMPLETION_ONE_LANE_CREATION_REQUIRED")
                        state = "PLANNED"
                    elif ref["kind"] == "lane_completion" and fact["lane_run_ref"] == body["lane_run_ref"]:
                        require(state == "COMPLETION_CANDIDATE" and fact["input_history_cut"] == input_cut,
                                "NF02_COMPLETION_ACCEPTED_SELECTOR_CONFLICT")
                        state = "COMPLETION_ACCEPTED"
                elif event["event_type"] == "StateTransitionAccepted" and event["aggregate_ref"] == body["lane_run_ref"]:
                    require(event["aggregate_kind"] == "LANE_RUN" and event["to_state"] != "COMPLETION_ACCEPTED",
                            "NF02_COMPLETION_GENERIC_TRANSITION_BYPASS")
                    require(state == event["from_state"] and (state, event["to_state"]) in edges,
                            "NF02_COMPLETION_ILLEGAL_OR_STALE_LANE_STATE")
                    self.prior_object(body["lane_run_ref"], input_cut, read_accepted=read_accepted, offline_registry=offline_registry)
                    for ref in event["basis_refs"]:
                        self.prior_object(ref, input_cut, read_accepted=read_accepted, offline_registry=offline_registry)
                    state = event["to_state"]
        require(state == "COMPLETION_CANDIDATE", "NF02_COMPLETION_LANE_NOT_ELIGIBLE")

        def prior(ref):
            return self.prior_object(ref, cut, read_accepted=read_accepted, offline_registry=offline_registry)

        lane, _ = prior(body["lane_run_ref"])
        require(lane["lane_spec_ref"] == body["lane_spec_ref"], "NF02_COMPLETION_LANE_SPEC_CONFLICT")
        lane_spec, _ = prior(body["lane_spec_ref"])
        require(type(predicate_pin) is dict and set(predicate_pin) == {"profile_id", "revision_digest"}
                and predicate_pin["profile_id"] == "LANE_COMPLETION_V1"
                and predicate_pin == lane_spec["completion_predicate_ref"]
                and type(predicate_raw) is bytes
                and hashlib.sha256(predicate_raw).hexdigest() == predicate_pin["revision_digest"],
                "NF02_COMPLETION_EXACT_PREDICATE_PIN_REQUIRED")
        require(type(predicate_schema_raw) is bytes and type(predicate_schema_digest) is str
                and DIGEST.fullmatch(predicate_schema_digest)
                and hashlib.sha256(predicate_schema_raw).hexdigest() == predicate_schema_digest,
                "NF02_COMPLETION_PREDICATE_SCHEMA_PIN_REQUIRED")
        predicate, predicate_schema = parse(predicate_raw), parse(predicate_schema_raw)
        require(predicate_schema.get("$id") == "BDB_EXTERNAL_PROFILE_SCHEMA::LANE_COMPLETION_V1"
                and Draft202012Validator(predicate_schema, registry=offline_registry or Registry()).is_valid(predicate),
                "NF02_COMPLETION_CLOSED_PREDICATE_REQUIRED")
        parameters = predicate["parameters"]
        stage, _ = prior(lane["stage_run_ref"])
        campaign, _ = prior(stage["campaign_ref"])
        require(campaign["campaign_id"] == campaign_id
                and campaign["source_generation_ref"] == stage["source_generation_ref"] == lane["source_generation_ref"],
                "NF02_COMPLETION_CAMPAIGN_SOURCE_CONFLICT")
        slots = lane["required_result_slots"]
        require(slots and all(ref["profile_id"] == "NF02_EXTERNAL_LANE_SLOT_V3" for ref in slots),
                "NF02_COMPLETION_EXPLICIT_SLOT_SCOPE_REQUIRED")
        require(len({canonical(ref) for ref in slots}) == len(slots), "NF02_COMPLETION_DUPLICATE_REQUIRED_SLOT")
        require(type(slot_instances) is dict and set(slot_instances) == {canonical(ref) for ref in slots},
                "NF02_COMPLETION_EXACT_SLOT_READBACK_SET_REQUIRED")
        attempts = self.reference_set(body["attempt_refs"])
        for ref in attempts:
            attempt, _ = prior(ref)
            require(attempt["lane_run_ref"] == body["lane_run_ref"], "NF02_COMPLETION_ATTEMPT_LANE_CONFLICT")
        knowledge, _ = prior(body["final_knowledge_state_ref"])
        require(knowledge["attempt_ref"] in attempts, "NF02_COMPLETION_KNOWLEDGE_ATTEMPT_CONFLICT")
        states = [ref for _, _, _, facts in prefix for ref, fact in facts
                  if ref["kind"] == "knowledge_state" and fact["attempt_ref"] == knowledge["attempt_ref"]]
        require(states and states[-1] == body["final_knowledge_state_ref"], "NF02_COMPLETION_REQUIRES_CURRENT_KNOWLEDGE")
        self.knowledge_predecessor(knowledge, campaign_id=campaign_id, read_context=read_context,
            read_accepted=read_accepted, read_history=read_history, offline_registry=offline_registry)
        self.knowledge_exposure_inventory(body["final_knowledge_state_ref"], knowledge,
            campaign_id=campaign_id, read_context=read_context, read_accepted=read_accepted,
            read_history=read_history, offline_registry=offline_registry)
        require(body["isolation_qualification_ref"] == knowledge["isolation_qualification_ref"],
                "NF02_COMPLETION_KNOWLEDGE_ISOLATION_CONFLICT")
        isolation, _ = prior(body["isolation_qualification_ref"])
        require(isolation["attempt_ref"] == knowledge["attempt_ref"], "NF02_COMPLETION_ISOLATION_ATTEMPT_CONFLICT")
        require(isolation["result"] in parameters["required_isolation_results"]
                and lane_spec["required_isolation_assurance"] in {"ENFORCED", "DECLARED"}
                and (lane_spec["required_isolation_assurance"] != "ENFORCED" or isolation["result"] == "ENFORCED"),
                "NF02_COMPLETION_ISOLATION_POLICY_NOT_SATISFIED")
        represented_contamination = {self.identity_key(ref) for ref in self.reference_set(body["contamination_assessment_refs"])}
        require({self.identity_key(ref) for ref in self.reference_set(knowledge["contamination_assessment_refs"])}
                <= represented_contamination, "NF02_COMPLETION_KNOWLEDGE_CONTAMINATION_OMITTED")
        for ref in body["contamination_assessment_refs"]:
            assessment, _ = prior(ref)
            require(assessment["attempt_ref"] in attempts, "NF02_COMPLETION_CONTAMINATION_ATTEMPT_CONFLICT")
            require(assessment["result"] == "CLEAN", "NF02_COMPLETION_CONTAMINATION_NOT_CLEAN_OR_NA_AUTHORITY_UNAVAILABLE")
        accepted_facts = {self.identity_key(ref) for _, _, _, facts in prefix for ref, _ in facts}
        represented = []
        for ref in self.reference_set(body["required_output_refs"]):
            output, seq = prior(ref)
            require(self.identity_key(ref) in accepted_facts, "NF02_COMPLETION_OUTPUT_ACCEPTED_MEMBERSHIP_REQUIRED")
            if ref["kind"] != "bdb_audit_lane_result":
                continue
            require("BDB_SCHEMA_REGISTRY::bdb_audit_lane_result/" + self._schemas["bdb_audit_lane_result"][0]
                    in parameters["allowed_result_kind_versions"], "NF02_COMPLETION_RESULT_KIND_NOT_PERMITTED")
            own_cut = self.accepted_cut(output["result_input_history_cut"], campaign_id=campaign_id, read_context=read_context)
            require(own_cut["accepted_head_seq"] + 1 == seq, "NF02_COMPLETION_RESULT_OWN_INPUT_REQUIRED")
            evidence, _ = self.prior_object(output["admission_evidence_ref"], own_cut,
                read_accepted=read_accepted, offline_registry=offline_registry)
            assignment, _ = self.prior_object(evidence["assignment_ref"], own_cut,
                read_accepted=read_accepted, offline_registry=offline_registry)
            require(assignment["attempt_ref"] in attempts and assignment["source_generation_ref"] == lane["source_generation_ref"]
                    and assignment["lane_spec_ref"] == body["lane_spec_ref"], "NF02_COMPLETION_RESULT_CONTEXT_CONFLICT")
            slot_key = canonical(evidence["result_slot_contract_ref"])
            require(slot_key in slot_instances, "NF02_COMPLETION_RESULT_SLOT_INVENTORY_CONFLICT")
            record = read_accepted(copy.deepcopy(ref), copy.deepcopy(cut))
            require(type(record) is dict and set(record) == {"ref", "body_raw", "schema_raw", "accepted_seq"}
                    and record["ref"] == ref and record["accepted_seq"] == seq,
                    "NF02_COMPLETION_RESULT_EXACT_READBACK_REQUIRED")
            self.nf02_result_preflight(ref, record["body_raw"], record["schema_raw"],
                slot_pin=evidence["result_slot_contract_ref"], slot_raw=slot_instances[slot_key],
                campaign_ref=stage["campaign_ref"], package_transport_pin=package_transport_pin,
                semantic_pin=semantic_pin, read_raw=read_raw, read_starts=read_starts, read_history=read_history,
                campaign_id=campaign_id, current_parent=own_cut, read_context=read_context, read_accepted=read_accepted,
                transition_pin=transition_pin, transition_raw=transition_raw, offline_registry=offline_registry)
            represented.append(slot_key)
        require(len(represented) == len(set(represented)) and set(represented) == {canonical(ref) for ref in slots},
                "NF02_COMPLETION_RESULT_SLOT_INVENTORY_CONFLICT")
        return {"verified_result_slots": len(represented), "final_knowledge_state_ref": body["final_knowledge_state_ref"],
                "lane_state": state, "verified_raw_result_count": len(represented),
                "full_lane_predicate": "NOT_EVALUATED", "qualification": False}

    def stage_slot_bindings(self, completion_ref, body_raw, schema_raw, *, campaign_id, current_parent,
                            read_context, read_accepted, read_profile, slot_schema_raw, slot_schema_digest,
                            offline_registry=None):
        """Exact mandatory-slot projection; not the whole STAGE/L7 predicate.

        Prior accepted StageRun/Spec and LaneCompletions require authenticated
        history/producer guards. This checks their complete slot/context joins;
        it cannot establish investigation, output, FSM, isolation or truth by
        reading a SATISFIED token. No canonical write occurs.
        """
        require(self.validate(completion_ref)["kind"] == "stage_completion", "STAGE_COMPLETION_TARGET_REQUIRED")
        body = self.validate_object(completion_ref, body_raw, schema_raw, offline_registry=offline_registry)
        cut = self.accepted_cut(body["input_history_cut"], campaign_id=campaign_id,
                                current_parent=current_parent, read_context=read_context)
        def prior(ref):
            return self.prior_object(ref, cut, read_accepted=read_accepted, offline_registry=offline_registry)
        stage, _ = prior(body["stage_run_ref"])
        spec, _ = prior(body["stage_spec_ref"])
        require(stage["stage_spec_ref"] == body["stage_spec_ref"], "STAGE_SLOT_SPEC_CONTEXT_CONFLICT")
        campaign, _ = prior(stage["campaign_ref"])
        require(campaign["campaign_id"] == campaign_id and campaign["source_generation_ref"] == stage["source_generation_ref"],
                "STAGE_SLOT_CAMPAIGN_SOURCE_CONFLICT")
        require(type(slot_schema_raw) is bytes and type(slot_schema_digest) is str and DIGEST.fullmatch(slot_schema_digest)
                and hashlib.sha256(slot_schema_raw).hexdigest() == slot_schema_digest, "STAGE_SLOT_SCHEMA_PIN_REQUIRED")
        slot_schema = parse(slot_schema_raw)
        require(slot_schema.get("$id") == "BDB_EXTERNAL_PROFILE_SCHEMA::MANDATORY_LANE_SLOT_V1",
                "STAGE_SLOT_SCHEMA_FAMILY_CONFLICT")
        slots, ids = {}, set()
        for pin in stage["required_lane_slot_contract_refs"]:
            raw = read_profile(copy.deepcopy(pin))
            require(type(raw) is bytes and hashlib.sha256(raw).hexdigest() == pin["revision_digest"], "STAGE_SLOT_RAW_UNAVAILABLE_OR_CHANGED")
            slot = parse(raw)
            require(pin["profile_id"] == "MANDATORY_LANE_SLOT_V1"
                    and Draft202012Validator(slot_schema, registry=offline_registry or Registry()).is_valid(slot),
                    "STAGE_SLOT_CLOSED_PROFILE_REQUIRED")
            require(slot["slot_id"] not in ids and canonical(pin) not in slots, "STAGE_SLOT_DUPLICATE_IDENTITY")
            ids.add(slot["slot_id"])
            slots[canonical(pin)] = slot
        require(ids == set(spec["required_lane_slots"]) and len(ids) == len(spec["required_lane_slots"]),
                "STAGE_SLOT_REQUIRED_SPEC_SET_CONFLICT")
        rows = body["required_lane_slot_results"]
        require(len(rows) == len(slots) and {canonical(row["slot_contract_ref"]) for row in rows} == set(slots),
                "STAGE_SLOT_EXACTLY_ONE_PER_REQUIRED_SLOT")
        seen_lanes, seen_completions = set(), set()
        for row in rows:
            slot = slots[canonical(row["slot_contract_ref"])]
            completion, accepted_seq = prior(row["lane_completion_ref"])
            lane, _ = prior(completion["lane_run_ref"])
            lane_spec, _ = prior(completion["lane_spec_ref"])
            lane_cut = self.accepted_cut(completion["input_history_cut"], campaign_id=campaign_id, read_context=read_context)
            require(lane_cut["accepted_head_seq"] < accepted_seq, "STAGE_SLOT_LANE_COMPLETION_REQUIRES_PRIOR_INPUT")
            require(completion["completion_predicate_result"] == "SATISFIED", "STAGE_SLOT_LANE_NOT_SATISFIED")
            require(lane["stage_run_ref"] == body["stage_run_ref"]
                    and lane["source_generation_ref"] == stage["source_generation_ref"]
                    and lane["lane_spec_ref"] == completion["lane_spec_ref"]
                    and lane_spec["stage_spec_revision"] == spec["stage_spec_revision"], "STAGE_SLOT_LANE_CONTEXT_CONFLICT")
            require(slot["lane_role"] == lane_spec["lane_key"]
                    and slot["completion_contract_ref"] == lane_spec["completion_predicate_ref"]
                    and sorted(map(canonical, slot["result_slot_contract_refs"])) == sorted(map(canonical, lane["required_result_slots"])),
                    "STAGE_SLOT_LANE_CONTRACT_CONFLICT")
            key, completion_key = self.identity_key(completion["lane_run_ref"]), self.identity_key(row["lane_completion_ref"])
            require(key not in seen_lanes and completion_key not in seen_completions, "STAGE_SLOT_REUSED_LANE_COMPLETION")
            seen_lanes.add(key)
            seen_completions.add(completion_key)
        return {"required_slot_count": len(slots), "verified_lane_completion_refs": copy.deepcopy(
                    [row["lane_completion_ref"] for row in rows]), "full_stage_predicate": "NOT_EVALUATED", "qualification": False}

    def nf02_ingestion_mac(self, secret, evidence_ref, body_raw, schema_raw, *, authority_context, offline_registry=None):
        """Prepare the successor's transient MAC primitive, never canonical data.

        The eventual issuer must authenticate actor/installation, independently
        derive the entire context/body and enforce current eligibility before
        issuing this value. Computing a MAC does not authorize that issuer.
        Accepted replay relies on history provenance, not this transient secret.
        The predecessor MAC remains untouched and cannot bind successor fields.
        """
        require(type(secret) is bytes and len(secret) >= 32, "NF02_PRIVATE_MAC_KEY_REQUIRED")
        require(self.validate(evidence_ref)["kind"] == "lane_result_admission_evidence", "NF02_ADMISSION_TARGET")
        self.validate_object(evidence_ref, body_raw, schema_raw, offline_registry=offline_registry)
        fields = {"campaign_ref", "actor_ref", "trust_profile_ref", "schema_registry_ref", "protocol_profile_ref", "operation"}
        require(type(authority_context) is dict and set(authority_context) == fields
                and authority_context["operation"] == "INGEST_EXTERNAL_LANE_RESULT", "CLOSED_NF02_ISSUER_CONTEXT_REQUIRED")
        for field, kinds in (("campaign_ref", ("campaign_genesis", "successor_campaign_genesis")),
                             ("trust_profile_ref", ("trust_profile",)), ("schema_registry_ref", ("schema_registry",))):
            require(self.validate(authority_context[field])["kind"] in kinds, "NF02_ISSUER_CONTEXT_TARGET")
        for field in ("actor_ref", "protocol_profile_ref"):
            value = authority_context[field]
            require(type(value) is dict and set(value) == {"profile_id", "revision_digest"}
                    and type(value["profile_id"]) is str and value["profile_id"]
                    and type(value["revision_digest"]) is str and DIGEST.fullmatch(value["revision_digest"]), "CLOSED_NF02_ISSUER_PROFILE_REQUIRED")
        require(authority_context["protocol_profile_ref"]["profile_id"] == "NF02_PROTOCOL_PROFILE_V3", "ACTIVE_NF02_ISSUER_PROTOCOL_REQUIRED")
        # Full body identity binds assignment, binding, selected slot, current
        # admission cut and exact RawRef. Domain separation prevents old-token
        # reuse; root/actor/operation context cannot be dropped from the MAC.
        payload = {"evidence_ref": self.validate(evidence_ref), "authority_context": copy.deepcopy(authority_context)}
        return hmac.new(secret, b"BDB/NF02_ADMISSION_CAPABILITY/3\0" + canonical(payload), hashlib.sha256).hexdigest()

    def verify_nf02_ingestion_mac(self, capability, secret, evidence_ref, body_raw, schema_raw, **context):
        require(type(capability) is str and DIGEST.fullmatch(capability), "NF02_INGESTION_CAPABILITY_REQUIRED")
        expected = self.nf02_ingestion_mac(secret, evidence_ref, body_raw, schema_raw, **context)
        require(hmac.compare_digest(capability, expected), "NF02_INGESTION_CAPABILITY_MISMATCH")
        return None

    def accepted_prefix(self, value, *, campaign_id, read_context, read_accepted, read_history, offline_registry=None):
        """Read complete commit/command/fact membership, with no write authority.

        Verifies exact bytes, chain, cuts and command/event membership. Qualified
        roots, complete purpose guards, instance DAG and atomic storage remain
        independent requirements; a locally supplied prefix is not governance.
        """
        cut = self.accepted_cut(value, campaign_id=campaign_id, read_context=read_context)
        records = read_history(copy.deepcopy(cut))
        require(type(records) is list and len(records) == cut["accepted_head_seq"], "COMPLETE_ACCEPTED_PREFIX_REQUIRED")
        previous = "EMPTY_HISTORY"

        def prior(ref, at):
            return self.prior_object(ref, at, read_accepted=read_accepted, offline_registry=offline_registry)

        checked, seen = [], set()
        for seq, record in enumerate(records, 1):
            require(type(record) is dict and set(record) == {"ref", "body_raw", "schema_raw", "accepted_seq"}
                    and type(record["accepted_seq"]) is int and record["accepted_seq"] == seq, "ORDERED_ACCEPTED_COMMIT_RECORD_REQUIRED")
            require(self.validate(record["ref"])["kind"] == "commit_body", "ACCEPTED_COMMIT_TARGET_REQUIRED")
            body = self.validate_object(record["ref"], record["body_raw"], record["schema_raw"], offline_registry=offline_registry)
            require(body["commit_seq"] == seq and body["campaign_id"] == campaign_id
                    and body["expected_parent_head"] == previous and body["prev_history_ref"] == previous,
                    "NF02_ACCEPTED_PREFIX_CHAIN_CONFLICT")
            at = self.accepted_cut(read_context(campaign_id, seq), campaign_id=campaign_id, read_context=read_context)
            require(at["accepted_head_hash"] == record["ref"]["revision_digest"]
                    and body["governing_policy_ref"] == at["governing_policy_ref"]
                    and body["governing_spec_refs"] == at["governing_spec_refs"], "NF02_PREFIX_CUT_CONFLICT")
            input_cut = None if seq == 1 else read_context(campaign_id, seq - 1)
            command, command_seq = prior(body["command_ref"], at)
            require(body["command_ref"]["kind"] == "command_envelope" and command_seq == seq
                    and body["command_digest"] == body["command_ref"]["revision_digest"]
                    and all(command[field] == body[field] for field in
                            ("expected_parent_head", "actor_ref", "governing_policy_ref", "governing_spec_refs")),
                    "NF02_COMMIT_COMMAND_CONTEXT_CONFLICT")
            if seq == 1:
                require(command["command_kind"] == "INITIALIZE_CAMPAIGN_FROM_LEGACY"
                        and command["proposed_campaign_id"] == campaign_id, "NF02_INITIAL_COMMAND_NAMESPACE_CONFLICT")
            else:
                require(command["command_kind"] != "INITIALIZE_CAMPAIGN_FROM_LEGACY", "NF02_SECOND_INITIALIZATION_FORBIDDEN")
                campaign, _ = prior(command["campaign_ref"], input_cut)
                require(campaign["campaign_id"] == campaign_id, "NF02_COMMAND_CAMPAIGN_NAMESPACE_CONFLICT")
            proposed = command["command_payload"]["proposed_object_refs"]
            immutable = body["immutable_object_refs"]
            require(immutable and immutable[-1] == body["command_ref"]
                    and proposed == self.reference_set(proposed)
                    and self.reference_set(immutable[:-1]) == self.reference_set(proposed)
                    and command["command_payload"]["events"] == body["ordered_event_bodies"], "NF02_COMMIT_PAYLOAD_CONFLICT")
            if command["command_kind"] == "TRANSITION":
                require(not proposed, "TRANSITION_COMMAND_CANNOT_ACCEPT_FACTS")
            elif not proposed:
                require(False, "EMPTY_FACT_COMMAND_REQUIRES_TRANSITION")
            if command["command_kind"] == "INGEST_EXTERNAL_LANE_RESULT":
                require(any(ref["kind"] == "lane_result_admission_evidence" for ref in proposed)
                        and not any(ref["kind"] == "bdb_audit_lane_result" for ref in proposed),
                        "INGEST_COMMAND_REQUIRES_ADMISSION_FACT")
            event_refs = [event["artifact_ref"] for event in body["ordered_event_bodies"] if "artifact_ref" in event]
            require(self.reference_set(event_refs) == self.reference_set(proposed), "ONE_ACCEPTANCE_EVENT_PER_NEW_FACT_REQUIRED")
            require(event_refs == immutable[:-1] and all("artifact_ref" in event for event in
                    body["ordered_event_bodies"][:len(event_refs)]), "ACCEPTED_FACT_EVENT_ORDER_CONFLICT")
            facts = []
            for ref in event_refs:
                fact, accepted_seq = prior(ref, at)
                key = self.identity_key(ref)
                require(accepted_seq == seq and key not in seen, "NF02_EVENT_NEW_FACT_MEMBERSHIP_REQUIRED")
                seen.add(key)
                facts.append((copy.deepcopy(ref), fact))
            checked.append((seq, body, input_cut, facts))
            previous = {"campaign_id": campaign_id, "commit_seq": seq, "commit_hash": record["ref"]["revision_digest"]}
        return checked

    def grant_predecessor(self, grant, *, campaign_id, read_context, read_accepted, read_history, offline_registry=None):
        """OD-025 derives initial/later from the complete accepted input prefix.

        Requires an independently authenticated history reader and a separately
        validated exact grant body. This is a read-only guard, not acceptance or
        a concurrency claim. Null has no role in choosing the branch.
        """
        cut = self.accepted_cut(grant["grant_input_history_cut"], campaign_id=campaign_id, read_context=read_context)
        prefix = self.accepted_prefix(cut, campaign_id=campaign_id, read_context=read_context,
                                      read_accepted=read_accepted, read_history=read_history, offline_registry=offline_registry)
        grants, states = [], []
        for seq, _, _, facts in prefix:
            for ref, body in facts:
                if ref["kind"] in {"grant_body", "knowledge_state"} and self.exact_equal(body["attempt_ref"], grant["attempt_ref"]):
                    (grants if ref["kind"] == "grant_body" else states).append((seq, ref))
        if not grants and not states:
            require(grant["previous_knowledge_state_ref"] is None, "INITIAL_GRANT_REQUIRES_NULL_PREDECESSOR")
            return {"initial": True, "previous_knowledge_state_ref": None, "input_cut": cut}
        require(states, "LATER_GRANT_REQUIRES_PRIOR_KNOWLEDGE")
        latest_seq = max(seq for seq, _ in states)
        latest = [ref for seq, ref in states if seq == latest_seq]
        require(len(latest) == 1 and grant["previous_knowledge_state_ref"] == latest[0], "LATER_GRANT_REQUIRES_EXACT_CURRENT_KNOWLEDGE")
        require(not grants or max(seq for seq, _ in grants) <= latest_seq, "LATER_GRANT_REQUIRES_UPDATED_KNOWLEDGE")
        return {"initial": False, "previous_knowledge_state_ref": copy.deepcopy(latest[0]), "input_cut": cut}

    def knowledge_predecessor(self, knowledge, *, campaign_id, read_context, read_accepted, read_history, offline_registry=None):
        """Derive exact prior state and preserve accepted exposure monotonically.

        A separately validated KnowledgeState body and independently trusted
        prefix reader are prerequisites. This does not qualify channel/isolation
        claims or replace complete current grant/exposure derivation.
        """
        cut = self.accepted_cut(knowledge["basis_history_cut"], campaign_id=campaign_id, read_context=read_context)
        prefix = self.accepted_prefix(cut, campaign_id=campaign_id, read_context=read_context,
                                      read_accepted=read_accepted, read_history=read_history, offline_registry=offline_registry)
        states = [(seq, ref, body) for seq, _, _, facts in prefix for ref, body in facts
                  if ref["kind"] == "knowledge_state" and self.exact_equal(body["attempt_ref"], knowledge["attempt_ref"])]
        previous = knowledge.get("previous_knowledge_state_ref")
        if not states:
            require(previous is None, "INITIAL_KNOWLEDGE_REQUIRES_NO_PREDECESSOR")
            return {"initial": True, "previous_knowledge_state_ref": None}
        latest_seq = max(seq for seq, _, _ in states)
        latest = [(ref, body) for seq, ref, body in states if seq == latest_seq]
        require(len(latest) == 1 and previous == latest[0][0], "KNOWLEDGE_REQUIRES_EXACT_CURRENT_PREDECESSOR")
        before = {self.identity_key(ref) for ref in self.reference_set(latest[0][1]["potential_exposure_refs"])}
        after = {self.identity_key(ref) for ref in self.reference_set(knowledge["potential_exposure_refs"])}
        require(before <= after, "KNOWLEDGE_EXPOSURE_NOT_MONOTONIC")
        return {"initial": False, "previous_knowledge_state_ref": copy.deepcopy(latest[0][0])}

    def knowledge_exposure_inventory(self, knowledge_ref, knowledge, *, campaign_id, read_context,
                                     read_accepted, read_history, offline_registry=None):
        """Account for accepted facts before this exact KnowledgeState position.

        Same-commit preceding facts count; later facts cannot justify this state.
        Missing materialized exposure for an accepted grant makes this isolated
        NF02 readiness check fail closed. It does not forbid canonical grants
        without optional exposure objects, authenticate the reader, evaluate
        isolation/channel policy or prove the state current at a later result.
        """
        basis = self.accepted_cut(knowledge["basis_history_cut"], campaign_id=campaign_id, read_context=read_context)
        at = read_context(campaign_id, basis["accepted_head_seq"] + 1)
        prefix = self.accepted_prefix(at, campaign_id=campaign_id, read_context=read_context,
            read_accepted=read_accepted, read_history=read_history, offline_registry=offline_registry)
        grants, exposures = {}, {}
        found = False
        for _, _, _, facts in prefix:
            for ref, body in facts:
                if self.exact_equal(ref, knowledge_ref):
                    require(body == knowledge, "NF02_KNOWLEDGE_EXACT_BODY_REQUIRED")
                    found = True
                    break
                if ref["kind"] not in {"grant_body", "potential_exposure_record"}:
                    continue
                if not self.exact_equal(body["attempt_ref"], knowledge["attempt_ref"]):
                    continue
                if ref["kind"] == "grant_body":
                    grants[self.identity_key(ref)] = body
                else:
                    grant_key = self.identity_key(body["grant_ref"])
                    require(grant_key in grants, "NF02_EXPOSURE_REQUIRES_PRECEDING_ACCEPTED_GRANT")
                    grant = grants[grant_key]
                    require(self.exact_equal(body["view_manifest_ref"], grant["view_manifest_ref"])
                            and body["channel_class"] == grant["channel_class"], "NF02_EXPOSURE_GRANT_VIEW_OR_CHANNEL_CONFLICT")
                    exposures[self.identity_key(ref)] = grant_key
            if found:
                break
        require(found, "NF02_KNOWLEDGE_ACCEPTED_POSITION_REQUIRED")
        represented = {self.identity_key(ref) for ref in self.reference_set(knowledge["potential_exposure_refs"])}
        require(represented == set(exposures), "NF02_KNOWLEDGE_EXPOSURE_INVENTORY_CONFLICT")
        require(set(exposures.values()) == set(grants), "NF02_GRANT_EXPOSURE_ACCOUNTING_UNAVAILABLE")
        return {"accepted_grants": len(grants), "accepted_exposures": len(exposures),
                "scope": "EXACT_KNOWLEDGE_POSITION_ONLY", "qualification": False}

    def nf02_operation_state(self, derived, *, campaign_id, current_parent, read_context,
                             read_accepted, read_history, transition_pin, transition_raw,
                             offline_registry=None, operation="ACCEPT_RESULT"):
        """Replay the exact prefix for NF02 Attempt state and selector uniqueness.

        Readers and the transition pin require independent installation/history
        authentication. This predicate checks prefix/command/event identity and
        NF02 state effects; it does not qualify producers, all purpose-specific
        transition guards, other aggregate states, union-DAG or durable CAS.
        """
        cut = self.accepted_cut(current_parent, campaign_id=campaign_id, read_context=read_context)
        require(operation in {"ADMIT_RESULT", "ACCEPT_RESULT"}, "EXPLICIT_NF02_OPERATION_REQUIRED")
        require(type(transition_raw) is bytes and type(transition_pin) is dict
                and set(transition_pin) == {"profile_id", "revision_digest"}
                and transition_pin["profile_id"] == "FULL_PATH_TRANSITION_TABLE_V2"
                and hashlib.sha256(transition_raw).hexdigest() == transition_pin["revision_digest"], "NF02_TRANSITION_PIN_REQUIRED")
        profile = parse(transition_raw)
        require(profile["transitions"] == table()[0] and profile["guard_contracts"] == GUARDS,
                "EXACT_NORMATIVE_TRANSITION_TABLE_REQUIRED")
        edges = {(r["from_state"], r["to_state"]) for r in profile["transitions"] if r["aggregate_kind"] == "ATTEMPT"}
        records = self.accepted_prefix(cut, campaign_id=campaign_id, read_context=read_context,
                                       read_accepted=read_accepted, read_history=read_history, offline_registry=offline_registry)
        state, bindings, admissions, results = None, [], [], []
        attempt_ref, assignment_ref = derived["assignment"]["attempt_ref"], derived["assignment_ref"]
        slot = derived["evidence"]["result_slot_contract_ref"]
        def prior(ref, at):
            return self.prior_object(ref, at, read_accepted=read_accepted, offline_registry=offline_registry)

        def move(before, after):
            nonlocal state
            require(state == before and (before, after) in edges, "NF02_ILLEGAL_OR_STALE_ATTEMPT_STATE")
            state = after

        for seq, body, input_cut, facts in records:
            at = self.accepted_cut(read_context(campaign_id, seq), campaign_id=campaign_id, read_context=read_context)
            for event in body["ordered_event_bodies"]:
                if "artifact_ref" in event:
                    ref = event["artifact_ref"]
                    fact, accepted_seq = prior(ref, at)
                    require(accepted_seq == seq, "NF02_EVENT_NEW_FACT_MEMBERSHIP_REQUIRED")
                    if self.exact_equal(ref, attempt_ref):
                        require(state is None, "ONE_ATTEMPT_CREATION_REQUIRED")
                        state = "CREATED"
                    elif ref["kind"] == "assignment_package_binding" and self.exact_equal(fact["assignment_ref"], assignment_ref):
                        require(not bindings, "NF02_ASSIGNMENT_BINDING_CONFLICT")
                        require(state == "CREATED" and input_cut == fact["binding_input_history_cut"], "NF02_BINDING_REQUIRES_CREATED_INPUT")
                        _, assignment_seq = prior(assignment_ref, input_cut)
                        require(assignment_seq < seq, "NF02_BINDING_REQUIRES_PRIOR_ASSIGNMENT")
                        bindings.append(copy.deepcopy(ref))
                    elif ref["kind"] == "lane_result_admission_evidence":
                        assignment, _ = prior(fact["assignment_ref"], input_cut)
                        if self.exact_equal(assignment["attempt_ref"], attempt_ref):
                            require(fact["admission_input_history_cut"] == input_cut, "NF02_ADMISSION_SELECTOR_OR_CUT_CONFLICT")
                            binding, binding_seq = prior(fact["package_binding_ref"], input_cut)
                            require(binding_seq < seq and binding["assignment_ref"] == fact["assignment_ref"], "NF02_ADMISSION_REQUIRES_PRIOR_BINDING")
                            move("STARTED", "RESULT_RECEIVED")
                            if fact["result_slot_contract_ref"] == slot:
                                require(not admissions and fact["package_binding_ref"] in bindings, "NF02_ADMISSION_SELECTOR_OR_CUT_CONFLICT")
                                admissions.append(copy.deepcopy(ref))
                    elif ref["kind"] == "bdb_audit_lane_result":
                        evidence, _ = prior(fact["admission_evidence_ref"], input_cut)
                        assignment, _ = prior(evidence["assignment_ref"], input_cut)
                        if self.exact_equal(assignment["attempt_ref"], attempt_ref):
                            require(fact["result_input_history_cut"] == input_cut, "NF02_RESULT_SELECTOR_OR_CUT_CONFLICT")
                            move("RESULT_RECEIVED", "RESULT_ACCEPTED")
                            if evidence["result_slot_contract_ref"] == slot:
                                require(not results and fact["admission_evidence_ref"] in admissions, "NF02_RESULT_SELECTOR_OR_CUT_CONFLICT")
                                results.append(copy.deepcopy(ref))
                elif event["event_type"] == "AttemptStarted" and self.exact_equal(event["attempt_ref"], attempt_ref):
                    require(event["assignment_ref"] == assignment_ref and event["package_binding_ref"] in bindings,
                            "NF02_STARTED_SELECTOR_CONFLICT")
                    _, binding_seq = prior(event["package_binding_ref"], input_cut)
                    require(binding_seq < seq, "NF02_STARTED_REQUIRES_PRIOR_BINDING")
                    move("CREATED", "STARTED")
                elif event["event_type"] == "StateTransitionAccepted" and self.exact_equal(event["aggregate_ref"], attempt_ref):
                    require(event["aggregate_kind"] == "ATTEMPT" and event["to_state"] not in
                            {"STARTED", "RESULT_RECEIVED", "RESULT_ACCEPTED"}, "NF02_GENERIC_TRANSITION_BYPASS")
                    prior(attempt_ref, input_cut)
                    for ref in event["basis_refs"]:
                        prior(ref, input_cut)
                    move(event["from_state"], event["to_state"])
        expected_admissions = [] if operation == "ADMIT_RESULT" else [derived["evidence_ref"]]
        expected_state = "STARTED" if operation == "ADMIT_RESULT" else "RESULT_RECEIVED"
        require(bindings == [derived["binding_ref"]] and admissions == expected_admissions, "NF02_EXACT_ACCEPTED_SELECTOR_REQUIRED")
        require(state == expected_state and not results, "NF02_RESULT_SLOT_NOT_OPEN")
        return {"attempt_state": state, "binding_ref": bindings[0], "admission_evidence_ref": admissions[0] if admissions else None,
                "accepted_result_refs": results, "input_cut": cut}

    def nf02_readback(self, result_ref, body_raw, schema_raw, *, slot_pin, slot_raw, campaign_ref,
                      package_transport_pin, semantic_pin, read_raw, read_history, **history_context):
        """Join exact instance chronology to actual retained package/result bytes.

        Governing slot/transport/semantic pins and read-only history/raw readers
        must be independently authenticated by the eventual qualified caller.
        This isolated evaluator has no activation, write, durability, disclosure
        authorization, scientific qualification or full FSM claim.
        """
        require(self.validate(result_ref)["kind"] == "bdb_audit_lane_result", "NF02_RESULT_TARGET")
        result = self.validate_object(result_ref, body_raw, schema_raw,
                                      offline_registry=history_context.get("offline_registry"))
        derived = self.nf02_chronology(result, **history_context)
        scope_context = {key: value for key, value in history_context.items() if key != "current_parent" and key != "read_starts"}
        scope_context["read_history"] = read_history
        raw = self._nf02_raw_derivation(derived, slot_pin=slot_pin, slot_raw=slot_raw, campaign_ref=campaign_ref,
                                        package_transport_pin=package_transport_pin, semantic_pin=semantic_pin,
                                        read_raw=read_raw, scope_context=scope_context)
        require(canonical(result["result_payload"]) == raw["payload_bytes"], "NF02_PAYLOAD_NOT_DERIVED_FROM_BOUND_RAW")
        return {"result_payload": copy.deepcopy(result["result_payload"]), "package_semantic_digest": raw["package_semantic_digest"],
                "verified_sequence": derived["sequence"], "scope": raw["scope"]}

    def nf02_result_preflight(self, result_ref, body_raw, schema_raw, *, transition_pin,
                              transition_raw, **readback_context):
        """Join proposed R/raw readback to current exact Attempt/slot replay.

        Prior admission remains a distinct accepted fact. This does not prove
        producer authentication, isolation, atomic storage or L7 completion,
        mint capabilities, install contracts or accept a successor write.
        """
        result = self.validate_object(result_ref, body_raw, schema_raw,
            offline_registry=readback_context.get("offline_registry"))
        history_context = {key: readback_context[key] for key in (
            "campaign_id", "current_parent", "read_context", "read_accepted", "read_starts")}
        history_context["offline_registry"] = readback_context.get("offline_registry")
        derived = self.nf02_chronology(result, **history_context)
        history_context.pop("read_starts")
        state = self.nf02_operation_state(derived, read_history=readback_context["read_history"],
            transition_pin=transition_pin, transition_raw=transition_raw,
            operation="ACCEPT_RESULT", **history_context)
        readback = self.nf02_readback(result_ref, body_raw, schema_raw, **readback_context)
        return {**readback, "proposed_result_ref": self.validate(result_ref), "accepted_result_ref": None,
                "attempt_state": state["attempt_state"], "qualification": False}

    def nf02_admission_preflight(self, evidence_ref, body_raw, schema_raw, *, slot_pin, slot_raw,
                                 campaign_ref, package_transport_pin, semantic_pin, read_raw,
                                 campaign_id, current_parent, read_context, read_accepted, read_starts,
                                 read_history, transition_pin, transition_raw, offline_registry=None):
        """Check a proposed E against the current prefix without inventing membership.

        This read-only preparation has no actor/installer authentication,
        transient capability issuance, durable raw retention or canonical write.
        A qualified runtime issuer must independently enforce those conjuncts
        and the remaining purpose/knowledge/isolation/delivery guards atomically.
        """
        require(self.validate(evidence_ref)["kind"] == "lane_result_admission_evidence", "NF02_ADMISSION_TARGET")
        evidence = self.validate_object(evidence_ref, body_raw, schema_raw, offline_registry=offline_registry)
        cut = self.accepted_cut(evidence["admission_input_history_cut"], campaign_id=campaign_id,
                                read_context=read_context, current_parent=current_parent)
        scope_context = {"campaign_id": campaign_id, "read_context": read_context,
                         "read_accepted": read_accepted, "offline_registry": offline_registry}
        derived = self._nf02_bound_execution(evidence_ref, evidence, cut, read_starts=read_starts, **scope_context)
        state = self.nf02_operation_state(derived, current_parent=current_parent, read_history=read_history,
                                          transition_pin=transition_pin, transition_raw=transition_raw,
                                          operation="ADMIT_RESULT", **scope_context)
        scope_context["read_history"] = read_history
        raw = self._nf02_raw_derivation(derived, slot_pin=slot_pin, slot_raw=slot_raw, campaign_ref=campaign_ref,
                                        package_transport_pin=package_transport_pin, semantic_pin=semantic_pin,
                                        read_raw=read_raw, scope_context=scope_context)
        return {"proposed_evidence_ref": self.validate(evidence_ref), "accepted_evidence_ref": None,
                "result_payload": parse(raw["payload_bytes"]), "package_semantic_digest": raw["package_semantic_digest"],
                "prior_sequence": derived["sequence"], "attempt_state": state["attempt_state"], "scope": raw["scope"]}

    def nf02_issuer_preflight(self, evidence_ref, body_raw, schema_raw, *, trust_record,
                              expected_issuer_context, actor_ref, actor_raw, actor_schema_raw,
                              actor_schema_digest, authenticated_principal_id, namespace_pin,
                              protocol_raw, protocol_schema_raw, protocol_schema_digest,
                              **admission_context):
        """Join proposed admission checks to exact independently expected issuer inputs.

        The trusted caller supplies installation pins and authenticated identity
        from outside the proposal. These comparisons never authenticate that
        caller or mint an installation. No capability, raw retention or write is
        performed; the qualified runtime must serialize these guards with them.
        """
        fields = {"campaign_ref", "actor_ref", "trust_profile_ref", "schema_registry_ref",
                  "protocol_profile_ref", "operation"}
        require(type(expected_issuer_context) is dict and set(expected_issuer_context) == fields
                and expected_issuer_context["operation"] == "INGEST_EXTERNAL_LANE_RESULT",
                "CLOSED_NF02_ISSUER_CONTEXT_REQUIRED")
        require(type(trust_record) is dict and set(trust_record) == {"ref", "body_raw", "schema_raw"}
                and self.exact_equal(trust_record["ref"], expected_issuer_context["trust_profile_ref"])
                and self.validate(trust_record["ref"])["kind"] == "trust_profile", "EXACT_INSTALLED_TRUST_RECORD_REQUIRED")
        offline = admission_context.get("offline_registry")
        trust = self.validate_object(trust_record["ref"], trust_record["body_raw"], trust_record["schema_raw"],
                                     offline_registry=offline)
        require(actor_ref == trust["coordinator_authority_ref"] == expected_issuer_context["actor_ref"],
                "NF02_ISSUER_NOT_TRUST_COORDINATOR")
        root = self.validate(expected_issuer_context["schema_registry_ref"])
        require(root["kind"] == "schema_registry" and root["revision_digest"] == self._schema_registry_digest,
                "NF02_ISSUER_SCHEMA_REGISTRY_CONFLICT")
        require(expected_issuer_context["campaign_ref"] == admission_context["campaign_ref"],
                "NF02_ISSUER_CAMPAIGN_CONFLICT")
        campaign, _ = self.prior_object(admission_context["campaign_ref"], admission_context["current_parent"],
            read_accepted=admission_context["read_accepted"], offline_registry=offline)
        require(campaign["trust_profile_ref"] == expected_issuer_context["trust_profile_ref"]
                and campaign["schema_set_ref"] == root, "NF02_CAMPAIGN_INSTALLATION_ROOT_CONFLICT")
        protocol_pin = expected_issuer_context["protocol_profile_ref"]
        require(type(protocol_pin) is dict and set(protocol_pin) == {"profile_id", "revision_digest"}
                and protocol_pin["profile_id"] == "NF02_PROTOCOL_PROFILE_V3"
                and type(protocol_raw) is bytes and hashlib.sha256(protocol_raw).hexdigest() == protocol_pin["revision_digest"],
                "NF02_ISSUER_PROTOCOL_RAW_CONFLICT")
        require(type(protocol_schema_raw) is bytes and type(protocol_schema_digest) is str
                and DIGEST.fullmatch(protocol_schema_digest)
                and hashlib.sha256(protocol_schema_raw).hexdigest() == protocol_schema_digest,
                "NF02_ISSUER_PROTOCOL_SCHEMA_PIN_REQUIRED")
        protocol, protocol_schema = parse(protocol_raw), parse(protocol_schema_raw)
        require(protocol_schema.get("$id") == "BDB_EXTERNAL_PROFILE_SCHEMA::NF02_PROTOCOL_PROFILE_V3"
                and Draft202012Validator(protocol_schema, registry=offline or Registry()).is_valid(protocol),
                "NF02_ISSUER_CLOSED_PROTOCOL_REQUIRED")
        slot = parse(admission_context["slot_raw"])
        require(protocol["result_slot_ref"] == admission_context["slot_pin"]
                and protocol["input_transport_ref"] == admission_context["package_transport_pin"]
                and protocol["package_semantic_profile_ref"] == admission_context["semantic_pin"]
                and protocol["normalizer_ref"] == slot["normalizer_ref"]
                and protocol["result_transport_ref"] == slot["transport_ref"], "NF02_ISSUER_PROTOCOL_SELECTION_CONFLICT")
        principal = self.principal_context(actor_ref, actor_raw, actor_schema_raw,
            expected_actor_pin=trust["coordinator_authority_ref"], expected_schema_digest=actor_schema_digest,
            authenticated_principal_id=authenticated_principal_id, expected_namespace_pin=namespace_pin,
            required_operation="INGEST", required_role="COORDINATOR", offline_registry=offline)
        cut = admission_context["current_parent"]
        prefix = self.accepted_prefix(cut, **{name: admission_context[name] for name in
            ("campaign_id", "read_context", "read_accepted", "read_history")}, offline_registry=offline)
        first_commit = prefix[0][1]
        first_cut = admission_context["read_context"](admission_context["campaign_id"], 1)
        initial_command, _ = self.prior_object(first_commit["command_ref"], first_cut,
            read_accepted=admission_context["read_accepted"], offline_registry=offline)
        require(initial_command["history_namespace_ref"] == namespace_pin, "NF02_ISSUER_HISTORY_NAMESPACE_CONFLICT")
        result = self.nf02_admission_preflight(evidence_ref, body_raw, schema_raw, **admission_context)
        return {**result, "issuer_comparison": principal,
                "issuer_context": copy.deepcopy(expected_issuer_context), "capability": None,
                "qualification": False, "installed_authority_proven": False}

    def _nf02_raw_derivation(self, derived, *, slot_pin, slot_raw, campaign_ref,
                             package_transport_pin, semantic_pin, read_raw, scope_context):
        """Common exact slot/package/result readback, not acceptance authority."""
        scope = self.nf02_assignment_scope(derived, campaign_ref=campaign_ref, **scope_context)
        evidence = derived["evidence"]
        require(type(slot_raw) is bytes and type(slot_pin) is dict
                and set(slot_pin) == {"profile_id", "revision_digest"}
                and slot_pin == evidence["result_slot_contract_ref"], "GOVERNING_SLOT_IDENTITY_REQUIRED")
        require(hashlib.sha256(slot_raw).hexdigest() == slot_pin["revision_digest"], "SLOT_BYTE_SUBSTITUTION")
        slot = parse(slot_raw)
        fields = {"profile_id", "result_schema_key", "transport_ref", "normalizer_ref", "empty_findings", "uniqueness"}
        require(type(slot) is dict and set(slot) == fields
                and slot["profile_id"] == slot_pin["profile_id"] == "NF02_EXTERNAL_LANE_SLOT_V3"
                and slot["result_schema_key"] == "BDB_SCHEMA_REGISTRY::bdb_audit_lane_result/" + self._schemas["bdb_audit_lane_result"][0]
                and slot["empty_findings"] == "NO_AUTOMATIC_ASSURANCE_PASS"
                and slot["uniqueness"] == "ONE_EXACT_ASSIGNMENT_AND_SLOT", "CLOSED_ACTIVE_NF02_SLOT_REQUIRED")
        assignment = derived["assignment"]
        claims = {key: copy.deepcopy(assignment[key]) for key in ASSIGNMENT_CLAIMS - {"assignment_ref"}}
        claims["assignment_ref"] = derived["assignment_ref"]
        package_raw = read_bound_raw(derived["binding"]["package_raw_ref"], expected_pin=package_transport_pin, read_raw=read_raw)
        package_digest = validate_package(package_raw, transport_pin=package_transport_pin, semantic_pin=semantic_pin,
                                          expected_claims={**claims, "result_slot_contract_refs": assignment["result_slot_contract_refs"]})
        result_raw = read_bound_raw(evidence["result_raw_ref"], expected_pin=slot["transport_ref"], read_raw=read_raw)
        expected = normalize(result_raw, transport_pin=slot["transport_ref"], normalizer_pin=slot["normalizer_ref"],
                             expected_claims={**claims, "package_binding_ref": derived["binding_ref"],
                                              "result_slot_contract_ref": slot_pin, "input_package_digest": package_digest})
        return {"payload_bytes": expected, "package_semantic_digest": package_digest, "scope": scope}

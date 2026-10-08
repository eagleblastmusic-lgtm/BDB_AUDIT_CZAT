"""Synthetic normative fixtures, not runtime acceptance/legacy qualification.

Every prerequisite has real canonical bytes, an exact schema identity and a
registered ObjectDigest. Authority/legacy-validation premises are explicitly
model inputs; the fixture is never an operating or qualified campaign.
"""
import copy
import heapq


def materialize(g, reg, profiles, schemas, roots):
    objs = []
    commits = []
    receipts = []
    objects_by_name = {}
    profile_pin = g.profile_pin
    campaign = g.named_id("campaign_genesis", 1)
    actor = "SYNTHETIC_EXTERNALLY_AUTHENTICATED_INSTALLATION_ACTOR"
    policy = roots["policy_revision"]["ref"]
    specs = [roots["spec_revision"]["ref"]]
    ext = profile_pin(profiles["NF02_PROTOCOL_PROFILE_V2"])
    source_pin = profile_pin(profiles["BDB_R5_4_SOURCE_IDENTITY_PIN_V1"])
    namespace = profile_pin(profiles["BDB_R5_4_BOOTSTRAP_NAMESPACE_PIN_V1"])
    empty = {"kind": "EMPTY_HISTORY_CUT", "history_namespace_ref": namespace,
             "governing_policy_ref": policy, "governing_spec_refs": specs}

    def add(name, kind, body, id_field=None, version="1"):
        obj = g.typed_object(kind, version, body, schemas, body.get(id_field) if id_field else None)
        objects_by_name[name] = obj
        objs.append(obj)
        return obj["ref"]

    def cut():
        if not commits:
            return copy.deepcopy(empty)
        return {"campaign_id": campaign, "accepted_head_seq": len(commits),
                "accepted_head_hash": commits[-1]["ref"]["revision_digest"],
                "governing_policy_ref": policy, "governing_spec_refs": specs}

    def ordered(new, bootstrap):
        by_digest = {o["ref"]["revision_digest"]: o for o in new}
        edges = set()

        def refs(value):
            if isinstance(value, dict):
                if "kind" in value and "revision_digest" in value and value.get("digest_profile") == g.OBJECT_PROFILE:
                    yield value
                else:
                    for v in value.values():
                        yield from refs(v)
            elif isinstance(value, list):
                for v in value:
                    yield from refs(v)

        for obj in new:
            for ref in refs(obj["body"]):
                target = ref["revision_digest"]
                if target in by_digest:
                    edges.add((target, obj["ref"]["revision_digest"]))
        if bootstrap:
            groups = reg["order_only_precedence_profiles"]["BDB_BOOTSTRAP_PRECEDENCE_V1"]["ordered_kind_groups"]
            ranks = {kind: i for i, group in enumerate(groups) for kind in group}
            for a in new:
                for b in new:
                    if a["kind"] in ranks and b["kind"] in ranks and ranks[a["kind"]] < ranks[b["kind"]]:
                        edges.add((a["ref"]["revision_digest"], b["ref"]["revision_digest"]))
        incoming = {d: 0 for d in by_digest}
        children = {d: [] for d in by_digest}
        for a, b in edges:
            incoming[b] += 1; children[a].append(b)
        def key(d):
            obj = by_digest[d]
            return obj["kind"], obj["ref"].get("logical_id", ""), d
        heap = [key(d) for d in by_digest if incoming[d] == 0]
        heapq.heapify(heap)
        result = []
        while heap:
            _, _, d = heapq.heappop(heap)
            result.append(by_digest[d]["ref"])
            for c in children[d]:
                incoming[c] -= 1
                if incoming[c] == 0: heapq.heappush(heap, key(c))
        if len(result) != len(new): raise ValueError("FIXTURE_CONTENT_REFERENCE_CYCLE")
        return result

    def commit(new, command_kind, events, payload=None):
        seq = len(commits) + 1
        parent = "EMPTY_HISTORY" if seq == 1 else {"campaign_id": campaign, "commit_seq": seq-1, "commit_hash": commits[-1]["ref"]["revision_digest"]}
        body = {"command_id": g.named_id("command_envelope", seq), "command_kind": command_kind,
                "actor_ref": actor, "expected_parent_head": parent,
                "governing_policy_ref": policy, "governing_spec_refs": specs,
                "idempotency_scope": "SYNTHETIC_NORMATIVE_FIXTURE_ONLY",
                "command_payload": payload or {"fixture_operation": command_kind}}
        if seq == 1:
            body.update({"proposed_campaign_id": campaign, "history_namespace_ref": namespace,
                         "bootstrap_profile_ref": roots["installation_bootstrap_profile"]["ref"]})
        else: body["campaign_ref"] = campaign
        cmd = g.typed_object("command_envelope", 1, body, schemas)
        cmds = ordered([cmd, *new], seq == 1)
        cb = {"campaign_id": campaign, "commit_seq": seq, "prev_history_ref": parent,
              "command_ref": cmd["ref"], "command_digest": cmd["ref"]["revision_digest"],
              "actor_ref": actor, "expected_parent_head": parent, "governing_policy_ref": policy,
              "governing_spec_refs": specs, "ordered_event_bodies": events, "immutable_object_refs": cmds}
        co = g.typed_object("commit_body", 1, cb, schemas)
        commits.append(co)
        receipt_body = {"command_id": body["command_id"], "command_digest": cmd["ref"]["revision_digest"],
                        "command_ref": cmd["ref"], "accepted_commit_ref": co["ref"],
                        "accepted_head": {"campaign_id": campaign, "commit_seq": seq, "commit_hash": co["ref"]["revision_digest"]},
                        "result_object_refs": [o["ref"] for o in new]}
        receipts.append(g.typed_object("command_receipt", 1, receipt_body, schemas))
        objs.append(cmd)
        return co

    # Explicit independently-pinned synthetic source/legacy validation premise.
    model_profile = {"profile_id": "NF02_SYNTHETIC_VALIDATION_PREMISES_V1",
                     "scope": "NORMATIVE_MODEL_ONLY_NOT_PRODUCTION_TRUST",
                     "source_authority": "independently authorized snapshot premise",
                     "legacy_mechanical_validation": "L5 canonical-predecessor admission premise; not a measured legacy validator result",
                     "actor_authority": "independently authenticated prior installation actor premise"}
    g.json_file(g.CANDIDATE / "fixtures/SYNTHETIC_VALIDATION_PREMISES.json", model_profile)
    model_pin = profile_pin(model_profile)
    source = b"Frozen synthetic source fixture.\n"
    g.write(g.CANDIDATE / "fixtures/SOURCE.txt", source)
    source_manifest = add("source_manifest", "source_manifest", {"entries": [
        {"repo_relative_posix_path": "SOURCE.txt", "entry_type": "REGULAR_FILE", "relevant_mode": "100644", "byte_length": len(source), "content_raw_digest": g.digest(source)}]})
    source_identity = add("source_identity", "source_identity", {"profile_ref": source_pin, "authority_mode": "AUTHORIZED_SNAPSHOT",
        "authorized_repository_or_snapshot_ref": model_pin, "materialized_source_manifest_ref": source_manifest, "completeness_state": "COMPLETE_SOURCE"})
    source_generation = add("source_generation", "source_generation", {"source_generation_id": g.named_id("source_generation", 1),
        "source_identity_ref": source_identity, "source_identity_profile_ref": source_pin, "snapshot_authority_ref": model_pin,
        "materialized_source_manifest_ref": source_manifest, "representation_refs": []}, "source_generation_id")
    legacy_bytes = g.cjson({"scope": "synthetic modeled legacy-validation premise only", "source_raw_digest": g.digest(source)}) + b"\n"
    g.write(g.CANDIDATE / "fixtures/LEGACY_MODEL_INPUT.json", legacy_bytes)
    legacy = add("legacy", "legacy_raw_ref", {"legacy_ref_id": g.named_id("legacy_raw_ref", 1),
        "raw_digest": g.digest(legacy_bytes), "byte_length": len(legacy_bytes), "media_type": "application/json", "import_input_history_cut": empty}, "legacy_ref_id")
    mechanical = add("mechanical", "legacy_mechanical_validation_assessment", {"assessment_id": g.named_id("legacy_mechanical_validation_assessment", 1),
        "legacy_ref": legacy, "assessment_input_history_cut": empty, "legacy_schema_ref": model_pin, "legacy_profile_ref": model_pin,
        "mechanical_validation_policy_ref": model_pin, "parsed_legacy_variant_stage_facts": {"modeled_validation_level": "L5"},
        "integrity_check_results": ["MODEL_PREMISE_NOT_MEASURED_RUNTIME_PASS"], "result": "VALID", "reason_codes": ["SYNTHETIC_MODEL_PREMISE"]}, "assessment_id")
    reconciliation = add("reconciliation", "source_reconciliation_assessment", {"assessment_id": g.named_id("source_reconciliation_assessment", 1),
        "legacy_ref": legacy, "assessment_input_history_cut": empty, "target_source_generation_ref": source_generation,
        "identity_profile_ref": source_pin, "reconciliation_policy_ref": model_pin,
        "raw_identifiers": {"raw_source_digest": g.digest(source)}, "normalized_identity_body_ref": source_identity,
        "result": "EXACT_MATCH", "reason_codes": ["SYNTHETIC_MODEL_PREMISE"]}, "assessment_id")
    lineage = add("lineage", "lineage_admission_assessment", {"assessment_id": g.named_id("lineage_admission_assessment", 1),
        "legacy_ref": legacy, "assessment_input_history_cut": empty, "admission_policy_ref": model_pin,
        "mechanical_validation_assessment_ref": mechanical, "source_reconciliation_assessment_ref": reconciliation,
        "requested_role": "CANONICAL_PREDECESSOR", "validation_level": "L5", "freshness_binding_refs": [], "result": "ADMITTED_WITH_LIMIT", "reason_codes": ["UNKNOWN_LEGACY_EXPOSURE"]}, "assessment_id")
    exposure_reconstruction = add("exposure_reconstruction", "legacy_exposure_reconstruction_assessment", {"assessment_id": g.named_id("legacy_exposure_reconstruction_assessment", 1),
        "legacy_ref": legacy, "assessment_input_history_cut": empty, "reconstruction_policy_ref": model_pin,
        "declared_scope": "Synthetic modeled legacy only", "controlled_exposure_fact_refs": [], "known_missing_channel_classes": ["UNCONTROLLED_LEGACY_CHANNELS"],
        "confidence": "UNKNOWN", "supporting_history_refs": [], "blind_origin_claim_scope": "NONE", "limitations": ["NO_BLIND_ORIGIN_OR_INDEPENDENT_ASSURANCE"]}, "assessment_id")
    selection = add("selection", "trusted_predecessor_selection_decision", {"trusted_predecessor_selection_decision_id": g.named_id("trusted_predecessor_selection_decision", 1),
        "selection_input_history_cut": empty, "candidate_legacy_refs": [legacy], "source_reconciliation_assessment_ref": reconciliation,
        "lineage_admission_assessment_ref": lineage, "selection_policy_ref": model_pin, "predecessor_pin_ref": model_pin,
        "selected_legacy_ref": legacy, "decision": "SELECTED", "reason_codes": ["SYNTHETIC_INSTALLATION_AUTHORITY_PREMISE"]}, "trusted_predecessor_selection_decision_id")
    admission = add("bootstrap_admission", "bootstrap_admission_decision", {"bootstrap_admission_decision_id": g.named_id("bootstrap_admission_decision", 1),
        "legacy_ref": legacy, "requested_role": "CANONICAL_PREDECESSOR", "mechanical_validation_assessment_ref": mechanical,
        "source_reconciliation_assessment_ref": reconciliation, "lineage_admission_assessment_ref": lineage,
        "admission_policy_ref": model_pin, "admission_input_history_cut": empty,
        "trusted_predecessor_selection_ref": selection, "exposure_reconstruction_assessment_ref": exposure_reconstruction,
        "result": "CANONICAL_BOOTSTRAP_ADMITTED_WITH_EXPOSURE_LIMIT", "limitations": ["NO_BLIND_ORIGIN_ASSURANCE"], "reason_codes": ["SYNTHETIC_MODEL_PREMISE"]}, "bootstrap_admission_decision_id")
    genesis = add("genesis", "campaign_genesis", {"campaign_id": campaign, "input_history_cut": empty,
        "bootstrap_admission_decision_ref": admission, "source_generation_ref": source_generation,
        "application_generation_ref": model_pin, "protocol_policy_bundle_ref": profile_pin(profiles["BDB_R5_4_PROTOCOL_POLICY_BUNDLE_V1"]), "schema_set_ref": roots["schema_registry"]["ref"],
        "owner_operator_authority_ref": actor, "trust_profile_ref": roots["trust_profile"]["ref"], "legacy_origin_refs": [legacy]}, "campaign_id")
    commit(list(objs), "INITIALIZE_CAMPAIGN_FROM_LEGACY", [{"event_type": "CampaignGenesisAccepted", "campaign_id": campaign}])

    start = len(objs)
    stage = add("stage_spec", "stage_spec", {"stage_key": "E1", "stage_spec_revision": 1, "stage_role": "SYNTHETIC_EXTERNAL_AUDIT", "stage_ordinal": 1,
        "purpose": "NF02 provenance fixture; no assurance claim", "predecessor_requirements": [], "required_lane_slots": ["SYNTHETIC_LANE"], "optional_lane_slots": [],
        "blind_reveal_phase_model": "NO_BLIND_ORIGIN_CLAIM", "allowed_corpus_roles": ["SOURCE_ONLY"], "forbidden_corpus_roles": ["UNASSIGNED"],
        "coverage_obligation_policy_ref": ext, "required_stage_completion_outputs": ["EXTERNAL_RESULT"], "transition_policy_ref": ext, "stop_e6_relationship": "UNCHANGED_FAIL_CLOSED"})
    lane = add("lane_spec", "lane_spec", {"lane_key": "SYNTHETIC_LANE", "lane_spec_revision": 1, "stage_spec_revision": 1,
        "purpose": "NF02 provenance fixture", "primary_strategy": "REVIEW_ASSIGNED_SOURCE", "scope_selectors": ["SOURCE_ONLY"], "exploration_policy_ref": ext,
        "allowed_view_classes": ["SOURCE_ONLY"], "forbidden_knowledge_classes": ["UNASSIGNED"], "required_isolation_assurance": "DECLARED",
        "required_outputs": ["EXTERNAL_RESULT"], "executor_capability_requirements": ["READ_EXACT_PACKAGE"], "budget_effort_profile_ref": ext, "completion_predicate_ref": ext})
    executor = add("executor_spec", "executor_spec", {"executor_profile_id": "NF02_MODEL_EXECUTOR", "executor_profile_revision": 1,
        "executor_tool_ref": model_pin, "runtime_profile_ref": model_pin, "supported_capabilities": ["READ_EXACT_PACKAGE"], "isolation_capabilities": ["DECLARED"],
        "filesystem_boundary_ref": model_pin, "network_boundary_ref": model_pin, "tool_boundary_ref": model_pin,
        "session_freshness_contract": "MODEL_FRESH_SESSION_PREMISE", "evidence_collection_capabilities": ["PACKAGE_MEMBER_PATHS"], "known_limitations": ["NOT_ENFORCED; NO_INDEPENDENCE_CLAIM"]})
    delivery = add("delivery_spec", "delivery_spec", {"delivery_profile_id": "NF02_MODEL_DELIVERY", "delivery_profile_revision": 1,
        "delivery_channel": "CONTROLLED_PACKAGE_MODEL", "grant_before_delivery_required": True, "view_manifest_required": True,
        "ack_semantics": "OPTIONAL_OBSERVATION_NOT_AUTHORITY", "retry_policy_ref": ext, "idempotency_policy_ref": ext,
        "potential_exposure_point": "ACCEPTED_GRANT", "redaction_profile_ref": ext, "resolver_capabilities": ["BOUND_RAW_ONLY"]})
    projection = add("projection_policy", "projection_policy", {"projection_policy_id": "NF02_MODEL_POSITIVE_VIEW", "allowed_view_classes": ["SOURCE_ONLY"],
        "forbidden_knowledge_classes": ["UNASSIGNED"], "metadata_policy": "ALLOW_SOURCE_ONLY", "resolver_policy": "NO_UNASSIGNED_LOOKUP"})
    commit(objs[start:], "RECORD_FOUNDATION_FACT", [{"event_type": "CampaignTransition", "from_state": "GENESIS_ACCEPTED", "to_state": "E0_READY"},
        {"event_type": "CampaignTransition", "from_state": "E0_READY", "to_state": "AUDIT_RUNNING"}])
    assignment_cut = cut()
    start = len(objs)
    stage_run = add("stage_run", "stage_run", {"stage_run_id": g.named_id("stage_run", 1), "campaign_ref": campaign, "stage_spec_ref": stage,
        "source_generation_ref": source_generation, "creation_input_history_cut": assignment_cut, "assigned_history_cut": assignment_cut,
        "predecessor_stage_completion_refs": [], "required_lane_slot_contract_refs": [profile_pin(profiles["NF02_EXTERNAL_LANE_SLOT_V2"])]}, "stage_run_id")
    lane_run = add("lane_run", "lane_run", {"lane_run_id": g.named_id("lane_run", 1), "stage_run_ref": stage_run, "lane_spec_ref": lane,
        "source_generation_ref": source_generation, "creation_input_history_cut": assignment_cut, "required_result_slots": [profile_pin(profiles["NF02_EXTERNAL_LANE_SLOT_V2"])]}, "lane_run_id")
    attempt = add("attempt", "attempt", {"attempt_id": g.named_id("attempt", 1), "lane_run_ref": lane_run, "attempt_nonce": "SYNTHETIC_ATTEMPT_NONCE_1",
        "executor_profile_ref": executor, "delivery_profile_ref": delivery, "assigned_history_cut": assignment_cut,
        "result_slot_contracts": [profile_pin(profiles["NF02_EXTERNAL_LANE_SLOT_V2"])]}, "attempt_id")
    source_raw_ref = {"raw_digest": g.digest(source), "byte_length": len(source), "media_type": "text/plain", "artifact_contract_ref": model_pin}
    view = add("view", "view_manifest", {"view_id": "NF02_MODEL_SOURCE_VIEW", "projection_policy_ref": projection,
        "allowed_member_refs": [source_raw_ref], "metadata_projection": {"scope": "SOURCE_ONLY"},
        "resolver_capability_profile_ref": ext, "forbidden_knowledge_policy_ref": ext})
    grant = add("grant", "grant_body", {"grant_id": g.named_id("grant_body", 1), "attempt_ref": attempt,
        "grant_input_history_cut": assignment_cut, "view_manifest_ref": view, "delivery_profile_ref": delivery,
        "forbidden_knowledge_policy_ref": ext, "channel_class": "CONTROLLED_PACKAGE"}, "grant_id")
    exposure = add("potential_exposure", "potential_exposure_record", {"exposure_id": g.named_id("potential_exposure_record", 1), "attempt_ref": attempt,
        "grant_ref": grant, "view_manifest_ref": view, "channel_class": "CONTROLLED_PACKAGE", "exposure_input_history_cut": assignment_cut}, "exposure_id")
    isolation = add("isolation", "isolation_qualification", {"isolation_qualification_id": g.named_id("isolation_qualification", 1), "attempt_ref": attempt,
        "assessment_input_history_cut": assignment_cut, "executor_profile_ref": executor, "delivery_profile_ref": delivery, "channel_inventory_ref": view,
        "enforcement_receipt_refs": [], "filesystem_boundary_evidence_refs": [], "network_boundary_evidence_refs": [], "tool_boundary_evidence_refs": [], "session_boundary_evidence_refs": [],
        "contamination_assessment_refs": [], "required_isolation_assurance": "DECLARED", "result": "DECLARED", "scope": {"view": "SOURCE_ONLY"},
        "limitations": ["NO_ENFORCEMENT_OR_BLINDNESS_CLAIM"], "reason_codes": ["MODEL_DECLARED_ONLY"]}, "isolation_qualification_id")
    knowledge = add("knowledge", "knowledge_state", {"knowledge_state_id": g.named_id("knowledge_state", 1), "knowledge_state_revision": 1,
        "attempt_ref": attempt, "basis_history_cut": assignment_cut, "allowed_view_refs": [view], "potential_exposure_refs": [exposure],
        "contamination_assessment_refs": [], "isolation_qualification_ref": isolation}, "knowledge_state_id")
    assignment_body = {"assignment_manifest_id": g.named_id("assignment_manifest", 1), "attempt_ref": attempt, "source_generation_ref": source_generation,
        "assignment_input_history_cut": assignment_cut, "knowledge_state_ref": knowledge, "grant_refs": [grant], "view_manifest_refs": [view],
        "executor_profile_ref": executor, "delivery_profile_ref": delivery, "stage_spec_ref": stage, "lane_spec_ref": lane,
        "result_slot_contract_refs": [profile_pin(profiles["NF02_EXTERNAL_LANE_SLOT_V2"])]}
    assignment_ref = add("assignment", "assignment_manifest", assignment_body, "assignment_manifest_id")
    commit(objs[start:], "RECORD_FOUNDATION_FACT", [{"event_type": "AssignmentManifestAccepted", "assignment_ref": assignment_ref}])

    context = {"assignment_ref": assignment_ref, "attempt_ref": attempt, "source_generation_ref": source_generation,
               "assignment_input_history_cut": assignment_cut, "stage_spec_ref": stage, "lane_spec_ref": lane,
               "executor_profile_ref": executor, "delivery_profile_ref": delivery}
    members = {"PROMPT.md": b"Audit only the exact assigned source.\n", "SOURCE.txt": source}
    package_manifest = {**context, "transport_profile_ref": profile_pin(profiles["NF02_INPUT_PACKAGE_TRANSPORT_V2"]),
                        "result_slot_contract_refs": assignment_body["result_slot_contract_refs"], "members": g.member_records(members, profiles)}
    descriptor = {"profile_ref": profile_pin(profiles["NF02_PACKAGE_SEMANTIC_PROFILE_V1"]), "manifest": copy.deepcopy(package_manifest), "members": g.member_records(members, profiles)}
    semantic = {"profile_ref": descriptor["profile_ref"], "digest": g.digest(g.cjson(descriptor))}
    package_manifest["package_semantic_digest"] = semantic
    members["MANIFEST.json"] = g.cjson(package_manifest) + b"\n"
    package = g.zip_bytes(members)
    g.write(g.CANDIDATE / "fixtures/input_package.zip", package)
    package_raw = {"raw_digest": g.digest(package), "byte_length": len(package), "media_type": "application/zip",
                   "artifact_contract_ref": profile_pin(profiles["NF02_INPUT_PACKAGE_TRANSPORT_V2"])}
    binding_cut = cut()
    binding_body = {"binding_id": g.named_id("assignment_package_binding", 1), "assignment_ref": assignment_ref,
                    "binding_input_history_cut": binding_cut, "package_raw_ref": package_raw}
    binding_ref = add("binding", "assignment_package_binding", binding_body, "binding_id")
    commit([objects_by_name["binding"]], "BIND_ASSIGNMENT_PACKAGE", [{"event_type": "ArtifactAccepted", "artifact_ref": binding_ref}])
    start_cut = cut()
    commit([], "RECORD_FOUNDATION_FACT", [{"event_type": "AttemptStarted", "attempt_ref": attempt, "package_binding_ref": binding_ref}],
           {"operation": "AttemptStarted", "attempt_ref": attempt, "package_binding_ref": binding_ref, "input_history_cut": start_cut})
    admission_cut = cut()
    payload = {"findings": [{"finding_id": "external_finding_1", "title": "Synthetic finding", "statement": "This fixture asserts no evidence truth.",
                           "evidence_member_paths": ["REPORT.md"], "reported_severity": "UNKNOWN"}],
               "outputs": {"report": {"member_paths": ["REPORT.md"]}}, "notes": None}
    result_members = {"REPORT.md": b"Synthetic audit result; unqualified evidence.\n"}
    result_manifest = {**context, "transport_profile_ref": profile_pin(profiles["NF02_RESULT_TRANSPORT_V2"]), "package_binding_ref": binding_ref,
                       "result_slot_contract_ref": profile_pin(profiles["NF02_EXTERNAL_LANE_SLOT_V2"]), "input_package_digest": semantic,
                       "members": g.member_records(result_members, profiles), "result_payload": payload}
    result_members["MANIFEST.json"] = g.cjson(result_manifest) + b"\n"
    result_raw = g.zip_bytes(result_members)
    g.write(g.CANDIDATE / "fixtures/audit_result.zip", result_raw)
    evidence_body = {"admission_evidence_id": g.named_id("lane_result_admission_evidence", 1), "assignment_ref": assignment_ref,
                     "package_binding_ref": binding_ref, "result_slot_contract_ref": result_manifest["result_slot_contract_ref"],
                     "admission_input_history_cut": admission_cut, "result_raw_ref": {"raw_digest": g.digest(result_raw), "byte_length": len(result_raw),
                        "media_type": "application/zip", "artifact_contract_ref": profile_pin(profiles["NF02_RESULT_TRANSPORT_V2"])}}
    evidence_ref = add("evidence", "lane_result_admission_evidence", evidence_body, "admission_evidence_id", "2")
    commit([objects_by_name["evidence"]], "INGEST_EXTERNAL_LANE_RESULT", [{"event_type": "ArtifactAccepted", "artifact_ref": evidence_ref}])
    result_cut = cut()
    result_body = {"lane_result_id": g.named_id("bdb_audit_lane_result", 1), "admission_evidence_ref": evidence_ref,
                   "result_input_history_cut": result_cut, "result_payload": payload}
    result_ref = add("result", "bdb_audit_lane_result", result_body, "lane_result_id", "2")
    commit([objects_by_name["result"]], "RECORD_FOUNDATION_FACT", [{"event_type": "ArtifactAccepted", "artifact_ref": result_ref}])
    wrong = g.zip_bytes(members, timestamp=(1980, 1, 2, 0, 0, 0))
    g.write(g.CANDIDATE / "fixtures/repacked_input_package.zip", wrong)
    fixture = {"scope": "NORMATIVE_SYNTHETIC_MODEL_FIXTURE_NOT_ACCEPTED_RUNTIME_HISTORY",
               "validation_premises_ref": model_pin, "external_installation_roots": [o["ref"] for o in roots.values()],
               "assignment": objects_by_name["assignment"], "binding": objects_by_name["binding"],
               "evidence": objects_by_name["evidence"], "result": objects_by_name["result"],
               "package_manifest": package_manifest, "package_semantic_descriptor": descriptor, "result_manifest": result_manifest,
               "objects": objs, "commits": commits, "receipts": receipts,
               "cuts": {"assignment_input": assignment_cut, "binding_input": binding_cut, "start_input": start_cut,
                        "admission_input": admission_cut, "result_input": result_cut, "final_model_head": cut()},
               "runtime_result": "NOT_RUN; modeled legacy/actor/source premises are not measured execution evidence"}
    g.json_file(g.CANDIDATE / "fixtures/NF02_OBJECT_FIXTURE_R5_4.json", fixture)
    known = {"schema": "BDB_R5_4_NF02_KNOWN_ANSWERS/1", "canonical_body_utf8_hex": {}, "object_digest_preimage_hex": {}, "object_digests": {},
             "raw_package_digest": g.digest(package), "raw_result_digest": g.digest(result_raw), "raw_repacked_package_digest": g.digest(wrong),
             "package_semantic_digest": semantic, "scope": "serialization/hash/schema/model normalization witnesses only; not runtime authority or qualification"}
    for name, obj in [(name, fixture[name]) for name in ["assignment", "binding", "evidence", "result"]] + [("schema_registry", roots["schema_registry"])]:
        known["canonical_body_utf8_hex"][name] = g.cjson(obj["body"]).hex()
        known["object_digest_preimage_hex"][name] = (f"BDB2/{obj['kind']}/{obj['version']}".encode() + b"\0" + g.cjson(obj["body"])).hex()
        known["object_digests"][name] = obj["ref"]["revision_digest"]
    g.json_file(g.CANDIDATE / "fixtures/NF02_KNOWN_ANSWERS_R5_4.json", known)
    return fixture, known

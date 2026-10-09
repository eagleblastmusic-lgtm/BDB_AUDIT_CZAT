"""Compile supported closed own-body designs; never invent an unknown type.

Unresolved compounds remain explicit work items. These are draft grammar checks,
not candidate materialization, qualification or canonical execution evidence.
"""

from __future__ import annotations

import copy
import re

from jsonschema import Draft202012Validator

from common_grammars import SOURCE_PATH_SHAPE, catalog
from execution import BASE, OUT, preserve, read, write
from purpose_contracts import array, enum, object_schema, ref, typed


NAMES = {
    "Text": "text", "bounded text": "text", "Code": "code", "Digest": "digest", "RawDigest": "digest",
    "UInt": "uint", "Revision": "revision", "positive integer": "revision", "Int32": "int32",
    "HistoryCut": "history_cut", "AcceptedHead": "accepted_head_ref", "RawRef": "raw_ref",
    "ExternalProfileRef": "external_profile_ref", "AuthorityRef": "external_profile_ref", "SourceAuthorityRef": "external_profile_ref",
    "AcceptedEventRef": "accepted_event_ref", "ScopeSet": "scope_set", "ScopeKey": "scope_key",
    "SurfaceAnchor": "surface_anchor", "ModelBound": "model_bound", "ModelState": "model_state",
    "ContradictionPosition": "contradiction_position", "ObservationPathRequirement": "observation_path_requirement",
    "MandatoryObligationSummary": "mandatory_obligation_summary", "ChangedManifestMember": "changed_manifest_member",
    "DependencyProfileChange": "dependency_profile_change", "TransitionProposal": "transition_proposal",
    "CompatibilityObservation": "compatibility_observation", "AssignedInputV2": "assigned_input",
    "BundleMemberV2": "bundle_member", "ComponentEntry": "component_entry", "LayerResult": "layer_result",
    "BuildInputRef": "build_input_ref", "CollectionRunV2": "collection_run", "ToolRunV2": "tool_run",
    "FaultRunV2": "fault_run", "ReportBindingV2": "report_binding", "ChannelRule": "channel_rule",
    "UnknownBlockedSummary": "unknown_blocked_summary",
    "LaneSlotResult": "lane_slot_result",
    "LegacyObservationLocator": "legacy_observation_locator", "ClosedPurposePayload": "closed_purpose_payload",
}


def domain_schema(domain, owner):
    if domain.endswith("[]"):
        item = domain_schema(domain[:-2], owner)
        return array(item) if item else None
    if domain in NAMES:
        return ref(NAMES[domain])
    if domain == "CorpusRole":
        return enum("CANONICAL_DIRECT_PREDECESSOR AUXILIARY_SAME_STAGE CUMULATIVE_HISTORY CLAIM_QUARANTINE_VIEW EXTERNAL_HOLDOUT CALIBRATION INFORMATIONAL")
    if domain in ("profile enum", "ground-truth profile enum"):
        # The finite value set comes from an exact qualified profile selected
        # through authoritative context; syntax alone cannot admit a class.
        return ref("code")
    if domain.startswith("ExternalProfileRef("):
        return ref("external_profile_ref")
    if domain.startswith("RawRef("):
        return ref("raw_ref")
    if domain.startswith("TypedRef("):
        return typed(domain[9:-1])
    if domain in ("TypedRef", "TargetRef"):
        return ref("typed_ref")
    if domain in ("ID", "CampaignID") or domain.startswith("ID("):
        kind = domain[3:-1] if domain.startswith("ID(") else "campaign_genesis" if domain == "CampaignID" else owner.split("/")[0]
        return {"type": "string", "pattern": "^" + re.escape(kind) + "_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"}
    if domain == "Boolean":
        return {"type": "boolean"}
    if domain == "Int32OrNull":
        return {"oneOf": [ref("int32"), {"type": "null"}]}
    if "|" in domain and all(re.fullmatch("[A-Z][A-Z0-9_]*", v) for v in domain.split("|")):
        return enum(domain.split("|"))
    return None


def reference_schema(item):
    representation = item["representation"]
    if representation == "TypedRef":
        targets = sorted({k.split("/")[0] for k in item["allowed_keys"]})
        schema = {"allOf": [ref("typed_ref"), {"properties": {"kind": enum(targets)}}]}
    elif representation == "ParentHead":
        schema = {"oneOf": [ref("accepted_head_ref"), {"const": "EMPTY_HISTORY"}]}
    elif representation in NAMES:
        schema = ref(NAMES[representation])
    else:
        return None
    # The original own-field array declaration, not only 0..1 semantics, picks
    # array representation. Cardinality itself is applied by the caller.
    return schema


def schema_obligations(schema, keys):
    issues = []

    def walk(value, path):
        if isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, path + "/" + str(index))
        elif isinstance(value, dict):
            if "$ref" in value:
                target = value["$ref"]
                if target.startswith("#/"):
                    current = schema
                    try:
                        for part in target[2:].split("/"):
                            current = current[part.replace("~1", "/").replace("~0", "~")]
                    except (KeyError, TypeError):
                        issues.append({"path": path, "problem": "MISSING_LOCAL_SCHEMA_TARGET", "target": target})
                elif target not in keys:
                    issues.append({"path": path, "problem": "UNQUALIFIED_EXTERNAL_SCHEMA_TARGET", "target": target})
            if value.get("type") == "object" and value.get("additionalProperties") is not False and "const" not in value and "enum" not in value:
                issues.append({"path": path, "problem": "OPEN_OBJECT_BODY_REPRESENTATION"})
            for name, child in value.items():
                walk(child, path + "/" + name)

    walk(schema, "")
    return issues


def main():
    preserve()
    own = read(OUT / "OWN_REFERENCE_RESOLUTIONS.json")
    domains = read(OUT / "design/OWN_FIELD_DOMAINS.json")
    mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
    keys = ["BDB_SCHEMA_REGISTRY::" + k for k in mapping.values()]
    defs = catalog(keys)
    Draft202012Validator.check_schema({"$defs": defs})
    fields_by_owner = {}
    for field in domains["fields"]:
        fields_by_owner.setdefault(field["owner"], {})[field["field"]] = field
    frontier = []
    compiled = []
    for node in own["nodes"]:
        key = node["key"]
        target_key = mapping[key]
        if key == target_key and node["body"]["selector"] == "EXACT_QUALIFIED_EXECUTABLE_BODY":
            schema = read(BASE / "candidate/schemas" / (key.replace("/", "__") + ".schema.json"))
            compiled.append({"source_key": key, "design_key": target_key, "mode": "EXACT_INHERITED_BYTES_PENDING_PARITY"})
            continue
        properties = {}
        required = []
        missing = []
        for declaration in node["body"]["fields"]:
            name = declaration["field"]
            if key == "command_envelope/1" and name == "command_payload_ref":
                continue
            field = fields_by_owner[key][name]
            if field["domain"] == "EXACT_QUALIFIED_SCHEMA":
                schema = copy.deepcopy(field["schema"])
                closed_replacements = {
                    ("legacy_mechanical_validation_assessment/1", "parsed_legacy_variant_stage_facts"): "legacy_variant_stage_facts",
                    ("source_reconciliation_assessment/1", "raw_identifiers"): "raw_identifier_assertions",
                    ("view_manifest/1", "metadata_projection"): "view_metadata",
                    ("command_envelope/1", "command_payload"): "command_payload",
                    ("contamination_assessment/1", "scope"): "scope_set",
                    ("isolation_qualification/1", "scope"): "scope_set",
                }
                if (key, name) in closed_replacements:
                    schema = ref(closed_replacements[key, name])
                refs = [r for r in node["resolved_own_material_refs"] if r["field"] == name]
                if refs:
                    replacement = reference_schema(refs[0])
                    if replacement:
                        schema = array(replacement) if schema.get("type") == "array" else replacement
                if key == "command_envelope/1" and name == "command_kind":
                    from event_grammars import COMMAND_KINDS
                    schema = enum(COMMAND_KINDS)
                if key == "source_identity/1" and name == "completeness_state":
                    schema = enum("COMPLETE_SOURCE BOUNDED_SOURCE")
                if key == "source_manifest/1" and name == "entries":
                    schema["items"]["properties"]["repo_relative_posix_path"] = copy.deepcopy(SOURCE_PATH_SHAPE)
                    item = schema["items"]
                    item["properties"]["symlink_target_encoding"] = {"const": "base64"}
                    item["allOf"].append({
                        "if": {"properties": {"entry_type": {"const": "SYMLINK"}}, "required": ["entry_type"]},
                        "then": {"required": ["symlink_target_encoding", "byte_length", "content_raw_digest"]},
                        "else": {"not": {"required": ["symlink_target_encoding"]}},
                    })
                if key == "commit_body/1" and name == "ordered_event_bodies":
                    schema = array(ref("event_body"), 1)
                    schema.pop("uniqueItems")
            elif field["domain"] == "ENUM":
                schema = enum(field["values"])
            elif field["domain"] == "EXPLICIT_MATERIAL_REFERENCE":
                direct = [r for r in field["references"] if r["field"] == name]
                schema = reference_schema(direct[0]) if direct else None
                if schema and (declaration.get("array") or declaration.get("design_type", "").endswith("[]")):
                    schema = array(schema)
                if schema is None and declaration.get("design_type"):
                    schema = domain_schema(declaration["design_type"], key)
                if key == "root_cause_revision/1" and name == "membership_edges":
                    schema = array(ref("root_cause_membership"))
            else:
                schema = domain_schema(field["domain"], key)
            if schema is None:
                missing.append({"owner": key, "field": name, "domain": field["domain"], "status": "OPEN"})
                continue
            if key == "policy_revision/1":
                successor_literals = {"profile": "FULL_PATH_R5_4_2_POLICY_V2", "revision": 2}
                if name in successor_literals:
                    schema = {"const": successor_literals[name]}
            if key == "spec_revision/1":
                if name == "protocol_profile_ref":
                    schema = ref("external_profile_ref")
                elif name == "initialization":
                    # OD-024 applies to the executable SpecRevision as well as Registry.
                    previous = schema["const"]
                    assert previous == "INITIALIZE_CAMPAIGN_FROM_LEGACY; EMPTY_HISTORY; one union-Kahn; BDB_BOOTSTRAP_PRECEDENCE_V1 exact scope only"
                    schema = {"const": "INITIALIZE_CAMPAIGN_FROM_LEGACY; EMPTY_HISTORY; one union-Kahn; BDB_BOOTSTRAP_PRECEDENCE_V2 exact scope only"}
                elif name == "artifact_acceptance_transition_effects":
                    previous = schema["const"]
                    schema = {"const": {mapping[k]: value for k, value in previous.items()}}
                elif name == "profile":
                    schema = {"const": "FULL_PATH_R5_4_2_TRANSITION_PROFILE_V2"}
                elif name == "revision":
                    schema = {"const": 2}
            direct_refs = [item for item in node["resolved_own_material_refs"] if item["field"] in (name, name + "[]")]
            if schema.get("type") == "array" and direct_refs:
                bounds = re.match(r"^(\d+)\.\.(\d+)(?:\b|;|$)", direct_refs[0]["cardinality"])
                if bounds:
                    schema["minItems"], schema["maxItems"] = int(bounds[1]), int(bounds[2])
            if key == "residual_risk/1":
                if name == "basis_refs":
                    schema.update({"minItems": 1, "maxItems": 256})
                elif name in ("description", "reason_unresolved", "uncertainty_class"):
                    schema = {"type": "string", "minLength": 1, "maxLength": {"description": 16384, "reason_unresolved": 4096, "uncertainty_class": 256}[name]}
            properties[name] = schema
            if key == "grant_body/1" and name == "previous_knowledge_state_ref":
                properties[name] = {"oneOf": [{"type": "null"}, schema]}
            if not declaration["optional"]:
                required.append(name)
        if missing:
            frontier.extend(missing)
            continue
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "BDB_DESIGN_SCHEMA::" + target_key,
                  "$defs": defs, **object_schema(properties)}
        schema["required"] = sorted(required)
        # Data 9 and 192.D.2 specify these variants, rather than arbitrary
        # HistoryCut. Exact parent/membership and chronology remain L4+ checks.
        if key == "campaign_genesis/1":
            schema["properties"]["input_history_cut"] = ref("empty_history_cut")
        nf02_cuts = {
            "assignment_package_binding/1": "binding_input_history_cut",
            "lane_result_admission_evidence/2": "admission_input_history_cut",
            "bdb_audit_lane_result/2": "result_input_history_cut",
        }
        if key in nf02_cuts:
            schema["properties"][nf02_cuts[key]] = ref("accepted_history_cut")
        if key == "assignment_package_binding/1":
            package_raw = copy.deepcopy(defs["raw_ref"])
            package_raw["properties"]["byte_length"]["minimum"] = 1
            package_raw["properties"]["media_type"] = {"const": "application/zip"}
            package_pin = copy.deepcopy(defs["external_profile_ref"])
            package_pin["properties"]["profile_id"] = {"const": "NF02_INPUT_PACKAGE_TRANSPORT_V2"}
            package_raw["properties"]["artifact_contract_ref"] = package_pin
            schema["properties"]["package_raw_ref"] = package_raw
        # Field extraction does not carry root assertions. Preserve qualified
        # conditional/XOR rules separately; never flatten them into optional
        # properties. Only OD-016 explicitly replaces command root semantics.
        if node["body"]["selector"] == "EXACT_QUALIFIED_EXECUTABLE_BODY" and key != "command_envelope/1":
            inherited = read(BASE / "candidate/schemas" / (key.replace("/", "__") + ".schema.json"))
            for keyword in ("oneOf", "allOf", "anyOf", "not", "if", "then", "else", "dependentRequired", "dependentSchemas", "minProperties", "maxProperties"):
                if keyword in inherited:
                    schema[keyword] = copy.deepcopy(inherited[keyword])
        if key == "trust_profile/1":
            # Required explicit limitation is wire data, never a freshness proof.
            schema["properties"]["explicit_non_guarantees"].update(
                minItems=1, contains={"const": "FULL_HOST_ROLLBACK_UNDETECTABLE_WITHOUT_INDEPENDENT_ANCHOR"}, minContains=1)
            schema["allOf"] = [{"if": {"properties": {"history_anchor_mode": {"const": "EXTERNALLY_PINNED_THROUGH"}},
                                      "required": ["history_anchor_mode"]},
                                "then": {"required": ["external_anchor_profile_ref"]}}]
        if key == "history_cut/1":
            # A cut is exactly one closed empty/accepted tuple, not the union
            # of their optional fields. The common tuple enforces separation.
            schema["allOf"] = [ref("history_cut")]
        if key == "standalone_payload_manifest/1":
            # OD-039 completes OD-018's role-specific raw contract. Keep this
            # refinement local: unrelated common-definition bytes stay exact.
            role_profiles = {
                "CODE": "RETAINED_PRODUCER_CODE_V1",
                "SCHEMA": "BDB_EXECUTABLE_JSON_SCHEMA_RAW_V1",
                "SPEC": "RETAINED_OPAQUE_BYTES_V1",
                "PROMPT": "RETAINED_OPAQUE_BYTES_V1",
                "FIXTURE": "FIXTURE_INPUT_V1",
            }
            schema["$defs"] = copy.deepcopy(defs)
            branches = []
            for role, profile in sorted(role_profiles.items()):
                branch = copy.deepcopy(defs["component_entry"])
                branch["properties"]["component_role"] = {"const": role}
                raw_schema = copy.deepcopy(defs["raw_ref"])
                pin_schema = copy.deepcopy(defs["external_profile_ref"])
                pin_schema["properties"]["profile_id"] = {"const": profile}
                raw_schema["properties"]["artifact_contract_ref"] = pin_schema
                branch["properties"]["raw_ref"] = raw_schema
                branches.append(branch)
            schema["$defs"]["component_entry"] = {"oneOf": branches}
        if key == "source_identity/1":
            # Data 8.1 and OD029: snapshot identity cannot assert Git identity.
            # Exact Git algorithm/authority and original objects are still
            # checked independently, not established by branch syntax.
            schema["else"] = {"not": {"anyOf": [
                {"required": [field]} for field in ("git_commit_object_id", "git_tree_object_id")
            ]}}
        if key == "input_disposition_record/2":
            schema["allOf"] = [{
                "if": {"properties": {"assigned_input_ref": {"properties": {"input_kind": {"const": "SOURCE_MEMBER"}}, "required": ["input_kind"]},
                                      "disposition": {"not": {"const": "PROVISIONAL"}}}},
                "then": {"required": ["collector_record_ref"]}
            }]
        if key == "scope_state_record/1":
            schema["allOf"] = [{
                "if": {"properties": {"state": {"const": "EXCLUDED_SCOPE"}}, "required": ["state"]},
                "then": {"required": ["scope_decision_ref"]},
                "else": {"not": {"required": ["scope_decision_ref"]}}
            }]
        if key == "command_envelope/1":
            schema["required"] = sorted(set(schema["required"]) | {"command_payload"})
            schema["allOf"] = [{
                "if": {"properties": {"command_kind": {"const": "INITIALIZE_CAMPAIGN_FROM_LEGACY"}}},
                "then": {"required": ["proposed_campaign_id", "history_namespace_ref", "bootstrap_profile_ref"], "not": {"required": ["campaign_ref"]}, "properties": {"expected_parent_head": {"const": "EMPTY_HISTORY"}}},
                "else": {"required": ["campaign_ref"], "properties": {"expected_parent_head": ref("accepted_head_ref")}, "not": {"anyOf": [{"required": [field]} for field in ("proposed_campaign_id", "history_namespace_ref", "bootstrap_profile_ref")]}}
            }]
        if key == "contradiction_revision/1":
            # Complete Data 60: a resolution decision belongs only to a
            # successor with an exact prior predecessor, never the first case.
            schema.setdefault("allOf", []).append({
                "if": {"required": ["resolution_decision_ref"]},
                "then": {"required": ["predecessor_contradiction_revision_ref"],
                         "properties": {"contradiction_revision": {"minimum": 2}}},
            })
        # Common definitions are identical and checked once above. Meta-check
        # each own body separately rather than repeating the entire catalog.
        Draft202012Validator.check_schema({k: v for k, v in schema.items() if k != "$defs"})
        obligations = schema_obligations(schema, keys)
        if obligations:
            frontier.extend({"owner": key, "field": i["path"], "domain": i["problem"], **i, "status": "OPEN"} for i in obligations)
            continue
        write("design/body_grammars/" + target_key.replace("/", "__") + ".json", schema)
        compiled.append({"source_key": key, "design_key": target_key, "mode": "CLOSED_DRAFT_META_VALID; SEMANTIC_PREDICATES_PENDING"})
    write("design/BODY_GRAMMAR_FRONTIER.json", {"compiled": compiled, "pending": frontier,
          "semantic_fixed_point_reached": False, "candidate_materialized": False,
          "remaining": "Nested domains, conditional/cardinality/ordering/material-ref obligations and profile closure are not inferred from draft schema meta-validity"})
    print({"draft_compilable_or_inherited": len(compiled), "pending_own_compound_fields": len(frontier)})
    for field in frontier:
        print(field["owner"] + "." + field["field"] + ": " + field["domain"])


if __name__ == "__main__":
    main()

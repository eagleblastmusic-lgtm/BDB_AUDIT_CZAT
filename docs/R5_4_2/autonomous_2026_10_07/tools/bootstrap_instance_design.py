"""Body-derived OD024/027 instance ordering fixture, never installation authority.

This binds actual retained source inputs and concrete draft body/schema digests.
External installation pins remain explicit unqualified fixture inputs. It cannot
admit a campaign, qualify roots or substitute for durable Store execution.
"""

import copy
import sys

from jsonschema import Draft202012Validator

from execution import BASE, OUT, ROOT, digest, preserve, read, write
from profile_design_audit import fixture

sys.path.insert(0, str(ROOT / "src"))

from bdb_audit.core.errors import ValidationError  # noqa: E402
from bdb_audit.core.hashing import _domain_digest  # noqa: E402
from bdb_audit.core.registry import ContractRegistry  # noqa: E402
from bdb_audit.history.closure import ClosureNode, canonical_order  # noqa: E402


def values(value, path):
    if not path:
        return value if isinstance(value, list) else [value]
    if isinstance(value, list):
        return [child for item in value for child in values(item, path)]
    if not isinstance(value, dict) or path[0] not in value:
        return []
    return values(value[path[0]], path[1:])


class DraftOrderingContext:
    """Read-only test context; deliberately cannot create a runtime Registry."""

    precedence_profile = ContractRegistry.precedence_profile
    active_precedence_profile = ContractRegistry.active_precedence_profile
    order_only_edges = ContractRegistry.order_only_edges

    def __init__(self, contracts, profile):
        self.contracts = contracts
        self._doc = {"order_only_precedence_profiles": {"BDB_BOOTSTRAP_PRECEDENCE_V2": profile}}

    def contract(self, kind):
        if kind not in self.contracts:
            raise ValidationError("UNREGISTERED_CONTRACT_KIND")
        return self.contracts[kind]


def main():
    preserve()
    mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
    own = {node["key"].split("/")[0]: node for node in read(OUT / "OWN_REFERENCE_RESOLUTIONS.json")["nodes"]}
    profile = read(OUT / "design/BOOTSTRAP_PRECEDENCE_SUCCESSOR.json")["profile"]
    context = DraftOrderingContext(own, profile)
    schemas, schema_paths = {}, {}

    def schema(kind):
        if kind not in schemas:
            active = mapping[own[kind]["key"]]
            path = OUT / "design/body_grammars" / (active.replace("/", "__") + ".json")
            if not path.exists():
                path = BASE / "candidate/schemas" / (active.replace("/", "__") + ".schema.json")
            schema_paths[kind] = path
            schemas[kind] = read(path)
        return schemas[kind]

    def placeholder_ref(kind):
        s = schema(kind)
        return {"kind": kind, "revision_digest": digest(schema_paths[kind]),
                "digest_profile": "BDB-OBJECT-DIGEST-1",
                "schema_revision_ref": {"kind": "schema", "revision_digest": digest(schema_paths[kind])}}

    def external(name):
        # Exact retained grammar bytes identify this fixture input; they are
        # explicitly not a qualified/instantiated installed profile revision.
        return {"profile_id": name, "revision_digest": digest(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")}

    roots = {kind: placeholder_ref(kind) for kind in
             ("build_manifest", "schema_registry", "trust_profile", "policy_revision", "spec_revision", "installation_bootstrap_profile")}
    cut = {"kind": "EMPTY_HISTORY_CUT", "history_namespace_ref": external("BOOTSTRAP_NAMESPACE_V2"),
           "governing_policy_ref": roots["policy_revision"], "governing_spec_refs": [roots["spec_revision"]]}
    bodies, refs = {}, {}

    def add(kind, overrides):
        s = schema(kind)
        body = fixture(s, s.get("$defs", {}))
        # Optional branches must be explicit; generic grammar fixtures cannot
        # silently supply requested role/selection/bootstrap witness semantics.
        body.update(overrides)
        errors = [error.message for error in Draft202012Validator(s).iter_errors(body)]
        assert not errors, (kind, errors)
        active = mapping[own[kind]["key"]]
        version = active.split("/")[1]
        hashed = _domain_digest(kind, version, body, registry_kind=kind)
        bodies[kind] = body
        refs[kind] = {"kind": kind, "revision_digest": hashed, "digest_profile": "BDB-OBJECT-DIGEST-1",
                      "schema_revision_ref": {"kind": "schema", "revision_digest": digest(schema_paths[kind])}}
        return refs[kind]

    source_folder = OUT / "design/source_instance_readback"
    retained = read(source_folder / "READBACK.json")
    manifest_path = source_folder / "source_manifest_body.json"
    assert digest(manifest_path) == retained["body_raw_digest"]
    manifest = read(manifest_path)
    add("source_manifest", manifest)
    identity = retained["identity"]
    add("source_identity", {"authority_mode": "AUTHORIZED_GIT", "completeness_state": "COMPLETE_SOURCE",
        "authorized_repository_or_snapshot_ref": external("SOURCE_AUTHORITY_V1"),
        "profile_ref": external("SOURCE_IDENTITY_V3"),
        "git_commit_object_id": identity["commit_object_id"], "git_tree_object_id": identity["tree_object_id"],
        "materialized_source_manifest_ref": refs["source_manifest"]})
    archive = source_folder / "source_head_representation.zip"
    add("source_generation", {"repository_authority_ref": external("SOURCE_AUTHORITY_V1"),
        "materialized_source_manifest_ref": refs["source_manifest"], "source_identity_ref": refs["source_identity"],
        "source_identity_profile_ref": external("SOURCE_IDENTITY_V3"),
        "representation_refs": [{"raw_digest": digest(archive), "byte_length": archive.stat().st_size,
            "media_type": "application/zip", "artifact_contract_ref": external("SOURCE_ARCHIVE_V2")} ]})
    # Assessments below are explicit hypothetical fixtures, not assertions that
    # this actual HEAD has a qualified legacy predecessor or admitted lineage.
    add("legacy_raw_ref", {"import_input_history_cut": cut})
    add("legacy_mechanical_validation_assessment", {"assessment_input_history_cut": cut,
        "legacy_ref": refs["legacy_raw_ref"], "result": "VALID"})
    add("source_reconciliation_assessment", {"assessment_input_history_cut": cut,
        "legacy_ref": refs["legacy_raw_ref"], "target_source_generation_ref": refs["source_generation"],
        "normalized_identity_body_ref": refs["source_identity"], "result": "EXACT_MATCH"})
    add("lineage_admission_assessment", {"assessment_input_history_cut": cut, "legacy_ref": refs["legacy_raw_ref"],
        "mechanical_validation_assessment_ref": refs["legacy_mechanical_validation_assessment"],
        "source_reconciliation_assessment_ref": refs["source_reconciliation_assessment"], "result": "ADMITTED",
        "requested_role": "CANONICAL_PREDECESSOR"})
    add("trusted_predecessor_selection_decision", {"selection_input_history_cut": cut,
        "candidate_legacy_refs": [refs["legacy_raw_ref"]], "selected_legacy_ref": refs["legacy_raw_ref"],
        "lineage_admission_assessment_ref": refs["lineage_admission_assessment"],
        "source_reconciliation_assessment_ref": refs["source_reconciliation_assessment"], "decision": "SELECTED"})
    add("bootstrap_admission_decision", {"admission_input_history_cut": cut, "legacy_ref": refs["legacy_raw_ref"],
        "mechanical_validation_assessment_ref": refs["legacy_mechanical_validation_assessment"],
        "lineage_admission_assessment_ref": refs["lineage_admission_assessment"],
        "source_reconciliation_assessment_ref": refs["source_reconciliation_assessment"],
        "trusted_predecessor_selection_ref": refs["trusted_predecessor_selection_decision"],
        "requested_role": "CANONICAL_PREDECESSOR", "result": "CANONICAL_BOOTSTRAP_ADMITTED"})
    add("campaign_genesis", {"input_history_cut": cut, "application_generation_ref": roots["build_manifest"],
        "schema_set_ref": roots["schema_registry"], "trust_profile_ref": roots["trust_profile"],
        "source_generation_ref": refs["source_generation"], "bootstrap_admission_decision_ref": refs["bootstrap_admission_decision"],
        "legacy_origin_refs": [refs["legacy_raw_ref"]]})
    proposed = sorted(refs.values(), key=lambda item: (item["kind"], item.get("logical_id", ""), item["revision_digest"]))
    def prepare(records, identities):
        result, edges = [], set()
        for kind, body in records.items():
            deps = set()
            for rule in own[kind]["resolved_own_material_refs"]:
                if rule["representation"] != "TypedRef":
                    continue
                for target in values(body, rule["field"].replace("[]", "").split(".")):
                    name = target["kind"]
                    if name in identities and target == identities[name]:
                        assert rule["same_commit"], ("PRIOR_OR_INSTALLED_TARGET_IN_CURRENT_CLOSURE", kind, rule["field"])
                        deps.add(name)
                    elif target not in roots.values():
                        raise AssertionError(("UNRESOLVED_OR_FULL_REF_SUBSTITUTION", kind, rule["field"]))
            edges.update((dep, kind) for dep in deps)
            result.append(ClosureNode(kind, kind, body.get(kind + "_id", ""), identities[kind]["revision_digest"], tuple(sorted(deps))))
        return result, edges

    scope = {"command_kind": "INITIALIZE_CAMPAIGN_FROM_LEGACY", "commit_seq": 1,
             "expected_parent": "EMPTY_HISTORY", "profile_name": "BDB_BOOTSTRAP_PRECEDENCE_V2", "registry": context}
    domain_nodes, _ = prepare(bodies, refs)
    domain_order = canonical_order(domain_nodes, **scope)
    named_events = {key.split("/")[0]: event for event, key in read(OUT / "design/EVENT_TARGET_TABLE.json")["named_targets"].items()}
    events = [{"event_type": named_events.get(kind, "ArtifactAccepted"), "artifact_ref": refs[kind]} for kind in domain_order]
    add("command_envelope", {"command_kind": "INITIALIZE_CAMPAIGN_FROM_LEGACY", "expected_parent_head": "EMPTY_HISTORY",
        "bootstrap_profile_ref": roots["installation_bootstrap_profile"], "history_namespace_ref": cut["history_namespace_ref"],
        "proposed_campaign_id": bodies["campaign_genesis"]["campaign_id"], "governing_policy_ref": cut["governing_policy_ref"],
        "governing_spec_refs": cut["governing_spec_refs"], "command_payload": {"proposed_object_refs": proposed, "events": events}})
    nodes, typed = prepare(bodies, refs)
    ordered = canonical_order(nodes, **scope)
    assert canonical_order(list(reversed(nodes)), **scope) == ordered
    assert ordered[-1] == "command_envelope"
    assert ordered.index("source_manifest") < ordered.index("source_identity") < ordered.index("source_generation")
    assert ordered.index("bootstrap_admission_decision") < ordered.index("campaign_genesis")
    controls = [{"case": name, "result": "PASS"} for name in
                ("COMPLETE_BODY_SCHEMA_READBACK", "BODY_DERIVED_TYPED_EDGES", "INPUT_ORDER_INVARIANCE",
                 "REAL_SOURCE_MANIFEST_BEFORE_IDENTITY_GENERATION", "ADMISSION_BEFORE_GENESIS", "CONTENT_BEFORE_COMMAND")]
    changed = copy.deepcopy(bodies)
    changed["campaign_genesis"]["source_generation_ref"]["schema_revision_ref"]["revision_digest"] = "0" * 64
    try:
        prepare(changed, refs)
    except AssertionError as error:
        assert error.args[0][0] == "UNRESOLVED_OR_FULL_REF_SUBSTITUTION"
    else:
        raise AssertionError("Schema-ref substitution accepted")
    controls.append({"case": "SCHEMA_REF_SUBSTITUTION", "result": "PASS"})
    command_first = [node if node.kind != "source_generation" else
                     ClosureNode(node.node_id, node.kind, node.logical_id, node.revision_digest,
                                 node.depends_on + ("command_envelope",)) for node in nodes]
    try:
        canonical_order(command_first, **scope)
    except ValidationError as error:
        assert error.code == "CONTENT_REFERENCE_CYCLE"
    else:
        raise AssertionError("Command-first cycle accepted")
    controls.append({"case": "COMMAND_FIRST_UNION_CYCLE", "result": "PASS"})
    write("design/BOOTSTRAP_INSTANCE_ORDERING_FIXTURE.json", {
        "bodies": bodies, "refs": refs, "typed_edges": sorted(typed),
        "order_only_edges": sorted(context.order_only_edges(nodes, **{k: v for k, v in scope.items() if k != "registry"})),
        "canonical_order": ordered, "external_fixture_roots": roots, "controls": controls,
        "schema_inputs": {p.relative_to(ROOT).as_posix(): digest(p) for p in schema_paths.values()},
        "source_manifest_raw_digest": digest(manifest_path), "source_archive_raw_digest": digest(archive),
        "qualified_external_context": False, "accepted_instance_DAG": "NOT_PROVEN", "qualification": False,
        "events": "BODY_ORDER_DERIVED_FIXTURE_NOT_TRUSTED_ACCEPTANCE", "NF02": "OPEN",
        "remaining": ["Concrete complete installed root/profile/build/raw dependency bodies", "Independent trusted context qualification",
                      "Actual mechanically derived assessments and complete events", "Durable initialization/retry/crash/race guards"]})
    print(f"PASS {len(controls)} body-derived instance-order controls; unqualified external context explicitly unresolved")


if __name__ == "__main__":
    main()

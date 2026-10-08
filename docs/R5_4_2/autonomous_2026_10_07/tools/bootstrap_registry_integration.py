"""OD-024 exact Registry delta and installation-selection draft controls.

The generated fragment is a materialization input, never a candidate Registry.
It cannot mint a qualification or establish actual accepted-instance guards.
"""

import copy
import hashlib

from bootstrap_precedence_design import precedence
from execution import BASE, OUT, ROOT, canonical, digest, preserve, read, write


PROFILE = "BDB_BOOTSTRAP_PRECEDENCE_V2"
PREDECESSOR = "BDB_BOOTSTRAP_PRECEDENCE_V1"


def integration(old, successor):
    require(successor["source_registry_raw_digest"] == digest(BASE / "candidate/BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json"), "SOURCE_DRIFT")
    require(canonical(old) == canonical(read(BASE / "candidate/BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json")), "SOURCE_BODY_DRIFT")
    require(successor["profile_id"] == PROFILE and successor["predecessor_profile_id"] == PREDECESSOR, "PROFILE_ID")
    original = old["order_only_precedence_profiles"][PREDECESSOR]
    selected = successor["profile"]
    require(selected == {**original, "ordered_kind_groups": original["ordered_kind_groups"][1:]}, "DELTA_SCOPE")
    # Four explicit machine locations are affected. No global text replacement,
    # Registry rows, material refs, schemas or historical IDs are rewritten.
    result = copy.deepcopy(old)
    del result["order_only_precedence_profiles"][PREDECESSOR]
    result["order_only_precedence_profiles"][PROFILE] = copy.deepcopy(selected)
    result["global_invariants"]["initialization_bootstrap"] = (
        "seq=1 only: exact independently qualified INSTALLATION_BOOTSTRAP_PROFILE_V1 pin; EMPTY_HISTORY history input; "
        "BDB_BOOTSTRAP_PRECEDENCE_V2 imposes machine-readable order-only domain-group precedence SourceGeneration→legacy raw→mechanical→source reconciliation→lineage→optional exposure→selection→bootstrap admission→CampaignGenesis. "
        "CommandEnvelope/2 follows its actual inline payload content dependencies, not command-first order-only edges. "
        "Authenticate command against external installation pins before acceptance; dependency order supplies no authority or prior provenance. "
        "All typed-ref edges remain mandatory; one union graph Kahn sort must be acyclic; blocked admission forbids genesis; no synthetic H0 or V1 fallback.")
    install = result["profiles"]["INSTALLATION_BOOTSTRAP_PROFILE_V1"]
    install["order_only_precedence_profile_ref"] = PROFILE
    install["source_rule"] = (
        "actual target SourceGeneration is command content input validated under pinned source identity profile; "
        "BDB_BOOTSTRAP_PRECEDENCE_V2 orders SourceGeneration before every bootstrap legacy_raw_ref and later bootstrap assessment/admission/genesis domain group without adding raw-object references; "
        "CommandEnvelope/2 is ordered only by its actual content dependencies. The exact qualified installation's initial_artifact_contract_registry_ref selects this embedded Registry profile.")
    require(result["contracts"] == old["contracts"], "OUT_OF_SCOPE_CONTRACT_CHANGE")
    return result


class Reject(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Reject(reason)


def select(registry, independently_pinned_digest, scope):
    # The digest input models an independently qualified installation pin.
    # Runtime must resolve that pin itself, never accept a caller's digest.
    actual = hashlib.sha256(b"BDB2/artifact_contract_registry/1\0" + canonical(registry)).hexdigest()
    require(actual == independently_pinned_digest, "REGISTRY_PIN")
    name = registry["profiles"]["INSTALLATION_BOOTSTRAP_PROFILE_V1"]["order_only_precedence_profile_ref"]
    require(name == PROFILE and set(registry["order_only_precedence_profiles"]) == {PROFILE}, "PRECEDENCE_PIN")
    profile = registry["order_only_precedence_profiles"][name]
    require(canonical(profile["scope"]) == canonical(scope), "ACTIVATION_SCOPE")
    return profile


def main():
    preserve()
    path = BASE / "candidate/BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json"
    old = read(path)
    successor = read(OUT / "design/BOOTSTRAP_PRECEDENCE_SUCCESSOR.json")
    current = integration(old, successor)
    model_pin = hashlib.sha256(b"BDB2/artifact_contract_registry/1\0" + canonical(current)).hexdigest()
    selected = select(current, model_pin, successor["profile"]["scope"])
    assert selected == successor["profile"]
    assert precedence(selected, [g[0] for g in selected["ordered_kind_groups"]]) == precedence(old["order_only_precedence_profiles"][PREDECESSOR], [g[0] for g in selected["ordered_kind_groups"]])
    controls = [{"case": "EXACT_EMBEDDED_PROFILE_AND_INSTALLATION_SELECTION", "result": "PASS"},
                {"case": "ALL_DOMAIN_PRECEDENCE_RETAINED", "result": "PASS"},
                {"case": "CONTRACT_ROWS_AND_MATERIAL_REFS_UNCHANGED", "result": "PASS"}]

    def reject(name, operation, expected):
        try:
            operation()
        except Reject as error:
            assert str(error) == expected, (name, error)
        else:
            raise AssertionError(name)
        controls.append({"case": name, "result": "PASS", "expected_reject": expected})

    reject("UNPINNED_REGISTRY", lambda: select(current, "0" * 64, selected["scope"]), "REGISTRY_PIN")
    for field, value in (("command_kind", "OTHER_COMMAND"), ("commit_seq", 2), ("expected_parent", "ACCEPTED_HEAD")):
        reject("WRONG_SCOPE_" + field, lambda f=field, v=value: select(current, model_pin, {**selected["scope"], f: v}), "ACTIVATION_SCOPE")
    reject("BOOLEAN_SEQUENCE_COERCION", lambda: select(current, model_pin, {**selected["scope"], "commit_seq": True}), "ACTIVATION_SCOPE")
    reject("EXTRA_SCOPE_FIELD", lambda: select(current, model_pin, {**selected["scope"], "trusted": True}), "ACTIVATION_SCOPE")
    changed = copy.deepcopy(current)
    changed["profiles"]["INSTALLATION_BOOTSTRAP_PROFILE_V1"]["order_only_precedence_profile_ref"] = PREDECESSOR
    reject("REGISTRY_PROFILE_SUBSTITUTION", lambda: select(changed, model_pin, selected["scope"]), "REGISTRY_PIN")
    changed_pin = hashlib.sha256(b"BDB2/artifact_contract_registry/1\0" + canonical(changed)).hexdigest()
    reject("V1_FALLBACK_EVEN_WITH_MATCHING_MODEL_DIGEST", lambda: select(changed, changed_pin, selected["scope"]), "PRECEDENCE_PIN")
    changed_successor = copy.deepcopy(successor)
    changed_successor["profile"]["ordered_kind_groups"].pop()
    reject("DOMAIN_GROUP_OMISSION", lambda: integration(old, changed_successor), "DELTA_SCOPE")
    changed_successor = copy.deepcopy(successor)
    changed_successor["source_registry_raw_digest"] = "0" * 64
    reject("PREDECESSOR_SOURCE_DRIFT", lambda: integration(old, changed_successor), "SOURCE_DRIFT")
    changed_old = copy.deepcopy(old)
    changed_old["global_invariants"]["initialization_bootstrap"] = "caller mutation"
    reject("PREDECESSOR_BODY_DRIFT", lambda: integration(changed_old, successor), "SOURCE_BODY_DRIFT")
    write("design/REGISTRY_BOOTSTRAP_SUCCESSOR_DELTA.json", {
        "decision": "OD-024", "source_registry_raw_digest": digest(path),
        "replacement_fragments": {"order_only_precedence_profiles": current["order_only_precedence_profiles"],
                                  "global_invariants.initialization_bootstrap": current["global_invariants"]["initialization_bootstrap"],
                                  "profiles.INSTALLATION_BOOTSTRAP_PROFILE_V1": current["profiles"]["INSTALLATION_BOOTSTRAP_PROFILE_V1"]},
        "normative_replacement_requirements": {
            "Data_14_6": "Versioned V2 domain-only order; remove CommandEnvelope-before-domain arrow; append command after its complete actual payload closure. Retain authorization-before-acceptance, all typed edges, initial cut pin equality, admission guards and atomic initialization.",
            "Data_15_2": "Active successor local precedence profile is BDB_BOOTSTRAP_PRECEDENCE_V2 under exact installed Registry; no V1 fallback; union Kahn/tie-break/byte equality unchanged.",
            "Architecture_6_10": "Same V2 domain-only precedence and content-before-command chronology, with exact qualification/installation boundary unchanged."},
        "normative_source_digests": {p.relative_to(ROOT).as_posix(): digest(p) for p in [BASE / "candidate/BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md", BASE / "candidate/BDB_AUDIT_V2_ARCHITECTURE_SPEC_R5_4.md"]},
        "controls": controls, "status": "DESIGN_DELTA_VERIFIED_NOT_MATERIALIZED", "candidate_registry_identity": "NOT_CREATED",
        "qualification": False, "accepted_instance_DAG": "NOT_PROVEN", "durable_guard_execution": "NOT_RUN"})
    print(f"OD-024 exact Registry/installation-selection design controls PASS: {len(controls)}; instance/qualification NOT_PROVEN")


if __name__ == "__main__":
    main()

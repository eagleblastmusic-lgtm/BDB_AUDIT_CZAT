"""Small exact-reference bootstrap fixture for F2 gate tests."""
import hashlib
from bdb_audit.history.objects import (CanonicalObject, CommandEnvelope,
                                       InstallationBootstrapProfile)


def bootstrap_fixture():
    profile = InstallationBootstrapProfile(
        "INSTALLATION_BOOTSTRAP_PROFILE_V1",
        {key: "pin:" + key for key in InstallationBootstrapProfile.REQUIRED_PINS},
    )
    empty = profile.empty_cut().as_dict()
    objects = []

    def make(kind, body):
        obj = CanonicalObject(kind, body)
        objects.append(obj)
        return obj

    def ref(obj, ref_class="CONTENT_OR_PRIOR"):
        return obj.as_ref(ref_class=ref_class).as_dict()

    def external(kind, seed, ref_class="CONTENT_OR_PRIOR"):
        return {
            "kind": kind,
            "revision_digest": hashlib.sha256(seed.encode()).hexdigest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1",
            "schema_revision_ref": "BDB_TARGET/" + kind,
            "ref_class": ref_class,
        }

    source_manifest = make("source_manifest", {
        "entries": [
            {
                "repo_relative_posix_path": "README.md",
                "entry_type": "REGULAR_FILE",
                "relevant_mode": "0644",
                "byte_length": 10,
                "content_raw_digest": "0" * 64,
            }
        ]
    })
    source_identity = make("source_identity", {
        "profile_ref": external("source_identity_profile_pin", "source-profile", "PINNED_PROFILE_REF"),
        "authority_mode": "AUTHORIZED_SNAPSHOT",
        "authorized_repository_or_snapshot_ref": external("repository_or_snapshot_authority_ref", "repo", "SOURCE_AUTHORITY_REF"),
        "materialized_source_manifest_ref": ref(source_manifest),
        "completeness_state": "COMPLETE_SOURCE",
    })
    source_generation = make("source_generation", {
        "source_generation_id": "source_gen_fixture",
        "source_identity_ref": ref(source_identity),
        "source_identity_profile_ref": external("source_identity_profile_pin", "source-profile", "PINNED_PROFILE_REF"),
        "repository_authority_ref": external("repository_or_snapshot_authority_ref", "repo", "SOURCE_AUTHORITY_REF"),
        "materialized_source_manifest_ref": ref(source_manifest),
        "representation_refs": [],
    })
    legacy = make("legacy_raw_ref", {
        "legacy_ref_id": "legacy_ref_fixture",
        "raw_digest": "0" * 64,
        "byte_length": 100,
        "media_type": "application/zip",
        "import_input_history_cut": empty,
    })
    mechanical = make("legacy_mechanical_validation_assessment", {
        "assessment_id": "assessment_mech_fixture",
        "legacy_ref": ref(legacy),
        "assessment_input_history_cut": empty,
        "legacy_schema_ref": external("external_profile_ref", "legacy-schema", "PINNED_PROFILE_REF"),
        "legacy_profile_ref": external("external_profile_ref", "legacy-profile", "PINNED_PROFILE_REF"),
        "mechanical_validation_policy_ref": external("external_profile_ref", "mechanical-policy", "HISTORY_CONTEXT_BINDING"),
        "parsed_legacy_variant_stage_facts": {},
        "integrity_check_results": [],
        "result": "VALID",
        "reason_codes": [],
    })
    reconciliation = make("source_reconciliation_assessment", {
        "assessment_id": "assessment_reconcile_fixture",
        "legacy_ref": ref(legacy),
        "assessment_input_history_cut": empty,
        "target_source_generation_ref": ref(source_generation),
        "identity_profile_ref": external("external_profile_ref", "identity-profile", "HISTORY_CONTEXT_BINDING"),
        "reconciliation_policy_ref": external("external_profile_ref", "reconciliation-policy", "HISTORY_CONTEXT_BINDING"),
        "raw_identifiers": {},
        "normalized_identity_body_ref": ref(source_identity),
        "result": "EXACT_MATCH",
        "reason_codes": [],
    })
    lineage = make("lineage_admission_assessment", {
        "assessment_id": "assessment_lineage_fixture",
        "legacy_ref": ref(legacy),
        "assessment_input_history_cut": empty,
        "admission_policy_ref": external("external_profile_ref", "admission-policy", "HISTORY_CONTEXT_BINDING"),
        "mechanical_validation_assessment_ref": ref(mechanical),
        "source_reconciliation_assessment_ref": ref(reconciliation),
        "requested_role": "CANONICAL_PREDECESSOR",
        "validation_level": "L5_LINEAGE_ROLE_AND_TRUSTED_SELECTION_VALIDATED",
        "predecessor_pin_ref": external("predecessor_pin_ref", "predecessor-pin", "PINNED_INSTALLATION_REF"),
        "freshness_binding_refs": [],
        "result": "ADMITTED",
        "reason_codes": [],
    })
    selection = make("trusted_predecessor_selection_decision", {
        "trusted_predecessor_selection_decision_id": "decision_selection_fixture",
        "selection_input_history_cut": empty,
        "candidate_legacy_refs": [ref(legacy)],
        "selected_legacy_ref": ref(legacy),
        "source_reconciliation_assessment_ref": ref(reconciliation),
        "lineage_admission_assessment_ref": ref(lineage),
        "selection_policy_ref": external("external_profile_ref", "selection-policy", "HISTORY_CONTEXT_BINDING"),
        "predecessor_pin_ref": external("predecessor_pin_ref", "predecessor-pin", "PINNED_INSTALLATION_REF"),
        "decision": "SELECTED",
        "reason_codes": [],
    })
    admission = make("bootstrap_admission_decision", {
        "bootstrap_admission_decision_id": "decision_bootstrap_fixture",
        "legacy_ref": ref(legacy),
        "requested_role": "CANONICAL_PREDECESSOR",
        "mechanical_validation_assessment_ref": ref(mechanical),
        "source_reconciliation_assessment_ref": ref(reconciliation),
        "lineage_admission_assessment_ref": ref(lineage),
        "trusted_predecessor_selection_ref": ref(selection),
        "admission_policy_ref": external("external_profile_ref", "admission-policy", "HISTORY_CONTEXT_BINDING"),
        "admission_input_history_cut": empty,
        "result": "CANONICAL_BOOTSTRAP_ADMITTED",
        "limitations": [],
        "reason_codes": [],
    })
    command = CommandEnvelope.initialize(
        command_id="command_123e4567-e89b-42d3-a456-426614174000",
        actor_ref="installation-owner", profile=profile, campaign_id="campaign_fixture",
    )
    genesis = make("campaign_genesis", {
        "campaign_id": "campaign_fixture",
        "input_history_cut": empty,
        "bootstrap_admission_decision_ref": ref(admission),
        "source_generation_ref": ref(source_generation),
        "application_generation_ref": external("application_generation_ref", "application"),
        "protocol_policy_bundle_ref": external("protocol_policy_bundle_ref", "policy"),
        "schema_set_ref": external("schema_set_ref", "schema-set"),
        "owner_operator_authority_ref": external("owner_operator_authority_ref", "owner", "PINNED_INSTALLATION_REF"),
        "trust_profile_ref": external("trust_profile", "trust", "PINNED_INSTALLATION_REF"),
        "legacy_origin_refs": [ref(legacy)],
    })
    command_object = command.as_object()
    objects.insert(0, command_object)
    return profile, command, tuple(objects), {
        "source_generation": source_generation, "legacy": legacy,
        "mechanical": mechanical, "reconciliation": reconciliation,
        "lineage": lineage, "selection": selection, "admission": admission,
        "genesis": genesis,
    }

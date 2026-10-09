# Application build context and first-history chronology

OD-027 successor design. Full normative dependencies: Data sections 2, 9,
14.6, 122 and 123; the unchanged R5.3 source is retained in
F1_QUALIFICATION/inputs/BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS.md.
Qualified R5.4.1 sections provide the exact predecessor body/ref context.
This document is not a qualified installation or acceptance record.

## Contradiction and minimum correction

OD-010 correctly separates application source from audited target source and
maps CampaignGenesis.application_generation_ref to BuildManifest. However,
the draft retained PRIOR_ACCEPTED_ONLY for BuildManifest's application source
and stage/lane/policy configuration. A first campaign has no accepted input
history. The application's source, configuration and build precede that first
campaign by definition (Data 122–123). A build can be independently verified
outside campaign history; it cannot acquire fabricated pre-genesis acceptance.

The successor uses PINNED_INSTALLATION_REF for these exact build-time inputs
and CampaignGenesis.application_generation_ref. The refs remain exact
SourceGeneration, StageSpec/LaneSpec/PolicyRevision and BuildManifest refs;
there is no hash-domain, field or target-kind change. Existing planned /2
successors suffice. Retained bytes and executable schema bindings must be
independently verified before build-input freeze and again before activation.
Do not treat ordinary campaign prior refs as installation refs or allow a
same-commit caller object to authorize its own build/source context.

The producer/acceptance distinction remains: the authenticated external build
pipeline establishes build provenance under installation controls; a campaign
coordinator cannot manufacture that provenance by accepting a wrapper.
Canonical campaign history is still the only authority for campaign facts.
Installed application bytes/configuration/source are immutable external
inputs with separately verified provenance, not a second campaign head.

## Avoid activation/build/candidate hash cycles

INSTALLATION_FULL_PATH_PROFILE_V2 is the explicit external activation record.
It preserves bundle/context/Q1 manifest/Q1 record pins and additionally binds
application_build_manifest_ref and application_build_provenance_raw_ref.
The latter resolves the explicit BUILD_PROVENANCE_RECEIPT_V2 transport
(V1 analysis label, never a runtime alias);
strict readback binds the exact BuildManifest, final output RawRef, actual
build environment and all independent verification refs. Required full source,
inputs, profiles, schemas/resources, recipe/toolchain/settings and retained
producer code are read from that exact manifest, never discovered from cwd.

Receipt environment and verification refs are field-specific installation/
build context, not prior campaign facts. EnvironmentRecord has no required
campaign cut; verification_refs are narrowed to exact validation_result/2
produced by independently authenticated build checks with input_history_cut
absent. CompatibilityGateResult requires a campaign assessment cut, and
ArtifactHashManifest requires an export head, so neither can establish
pre-campaign build verification. All actual mandatory checks and independently
derived results remain required; a serialized PASS/one partial check cannot
substitute. Campaign validation results cannot be laundered into this context.

The V2 activation instance is constructed after candidate Q1, complete build,
external receipt and actual output verification. Its grammar is qualification
input; its future deployment instance is not. No activation instance or Q1
record bytes may occur in its own candidate, BuildManifest ordered inputs,
embedded resources, source closure, recipe or environment dependency closure.
This exclusion is transitive and must be checked against actual instances,
not just profile names. InstallationBootstrapProfile's independent exact
root fields remain unchanged; do not add the future application/output/
activation pin to an embedded build-time bootstrap root.

The initial command is authenticated using the separately qualified roots and
this independently installed application context before canonical mutation.
Genesis.application_generation_ref must exactly equal the activation record's
application_build_manifest_ref. Missing qualification, receipt, actual output,
trusted builder proof or full transitive input bytes rejects; merely matching
a manifest digest is insufficient. The standalone running output must equal
the pinned verified bytes/context. No reusing a qualification under changed
inputs, new-profile same-commit replacement or latest-installation lookup.

## Boundaries and remaining proof

Runtime subject SourceGeneration remains the exact audited target. It may have
the same bytes as application source but is not substituted for it. For a
successor campaign, derive application provenance through its exact declared
predecessor/context contracts; SuccessorCampaignGenesis has no application
generation field, so this decision does not invent one or imply adoption of a
new latest installation. Historical readers/campaigns retain original pins.

The design contract controls reproduce the prior-history contradiction,
verify field-specific corrected classes and the closed V2 activation grammar,
and reject omission/wrong type/wrong wire ID. Full actual instance closure,
independent build/qualification/output readback and durable bootstrap guards
remain unproven until executable materialization and qualification. No node
is marked semantically complete solely from these controls.

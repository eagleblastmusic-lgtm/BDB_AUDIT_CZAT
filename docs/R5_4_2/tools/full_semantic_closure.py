"""Read-only predecessor analysis; writes ONLY R5_4_2 design diagnostics.

Not a registry, schema generator, qualification verifier, or runtime resolver.
The proposal tables below are human design decisions, not inferred authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs/R5_4_2"
BASE = ROOT / "docs/R5_4_1/candidate"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


old = read(OUT / "R5_4_2_RUNTIME_SCHEMA_REACHABILITY.json")
if "full_pass_predecessor_diagnostic" in old:
    old = old["full_pass_predecessor_diagnostic"]
registry = read(BASE / "BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json")
rows = {f"{r['kind']}/{r['version']}": r for r in registry["contracts"]}
bound = {
    b["schema_key"].split("::")[1]
    for b in read(BASE / "objects/schema_registry__2.json")["body"]["bindings"]
}
inventory = read(OUT / "RESIDUAL_RISK_NORMATIVE_USAGE_INVENTORY.json")
manifest = read(ROOT / "docs/R5_4_1/R5_4_1_CANDIDATE_MANIFEST.json")
candidate_entries = (
    manifest["normative_candidate_files"] + manifest["machine_candidate_files"]
)
assert len(candidate_entries) == 120
for entry in candidate_entries:
    path = BASE / entry["file"]
    assert path.stat().st_size == entry["bytes"] and digest(path) == entry["sha256"], (
        "CANDIDATE_DRIFT"
    )
qualification = read(ROOT / "docs/R5_4_1/AUTHOR_BASELINE_QUALIFICATION_R5_4_1.json")
qualified_readback = {}
for category in ("normative", "machine"):
    preimage = sorted(
        [
            {k: e[k] for k in ("file", "bytes", "sha256")}
            for e in manifest[category + "_candidate_files"]
        ],
        key=lambda e: e["file"],
    )
    actual = hashlib.sha256(
        json.dumps(
            preimage, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    assert (
        actual
        == manifest[category + "_candidate_set_sha256"]
        == qualification[category + "_candidate_set_digest"]
    ), "CANDIDATE_DRIFT"
    qualified_readback[category + "_candidate_set_digest"] = actual
schema_object = read(BASE / "objects/schema_registry__2.json")
schema_object_digest = hashlib.sha256(
    b"BDB2/schema_registry/2\0"
    + json.dumps(
        schema_object["body"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
).hexdigest()
assert (
    schema_object_digest
    == old["predecessor"]["qualified_identities"]["schema_registry_object_digest"]
), "CANDIDATE_DRIFT"
for label, path, field in (
    (
        "manifest_raw_digest",
        ROOT / "docs/R5_4_1/R5_4_1_CANDIDATE_MANIFEST.json",
        "candidate_manifest_raw_digest",
    ),
    (
        "registry_raw_digest",
        BASE / "BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json",
        "registry_raw_digest",
    ),
    (
        "golden_raw_digest",
        BASE / "BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json",
        "golden_vector_set_raw_digest",
    ),
):
    qualified_readback[label] = digest(path)
    assert qualified_readback[label] == qualification[field], "CANDIDATE_DRIFT"
qualified_readback.update(
    schema_registry_object_digest=schema_object_digest,
    qualification_record_raw_digest=digest(
        ROOT / "docs/R5_4_1/AUTHOR_BASELINE_QUALIFICATION_R5_4_1.json"
    ),
    qualification_record_id=qualification["author_baseline_qualification_id"],
    registry_id=qualification["registry_id"],
    golden_vector_set_id=qualification["golden_vector_set_id"],
)

# Preserve the entire old graph and inventory; never regenerate their source evidence.
preservation = []
for group in (
    "source_raw_pins",
    "protected_tracked_pins",
    "r5_4_1_entire_subtree_raw_pins",
):
    for name, expected in old["source"][group].items():
        path = (
            ROOT / name
            if group != "r5_4_1_entire_subtree_raw_pins"
            else ROOT / "docs/R5_4_1" / name
        )
        preservation.append(
            {
                "file": str(path.relative_to(ROOT)),
                "expected": expected,
                "actual": digest(path),
            }
        )
assert all(p["expected"] == p["actual"] for p in preservation), "CANDIDATE_DRIFT"

data_file = BASE / "BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md"
data = data_file.read_text(encoding="utf-8-sig")
sections = {}
for match in re.finditer(r"(?ms)^# (\d+)\. (.*?)(?=^# \d+\. |\Z)", data):
    sections[int(match[1])] = match[0]
# Read every normative document and machine artifact, including all profile inputs.
input_pins = {
    str(p.relative_to(ROOT)): digest(p) for p in BASE.rglob("*") if p.is_file()
}
texts = {p.name: p.read_text(encoding="utf-8-sig") for p in BASE.glob("*.md")}


def keys(*names):
    return [n if "/" in n else n + "/1" for n in names]


def ref(field, targets, card="1", cls="PRIOR_ACCEPTED_ONLY"):
    return {
        "field": field,
        "allowed_keys": keys(*targets),
        "cardinality": card,
        "ref_class": cls,
    }


common = {
    "status": "HYPOTHETICAL_OWNER_PROPOSAL_NOT_AUTHORITY",
    "lifecycle": "IMMUTABLE",
    "producer_authority": "TRUSTED_COORDINATOR_ACCEPTANCE",
    "reference_contract_mode": "EXPLICIT_COMPLETE",
    "identity": "BDB-CJSON-1; ObjectDigest BDB2/<kind>/1 NUL canonical body; exact schema RawDigest in external TypedRef",
    "validation_layers": ["L1", "L2", "L3", "L4", "L5", "L6", "L7"],
    "validation_profile": "FULL_PATH_SEMANTIC_V1 (proposed composition of existing layers)",
    "body_rule": "Closed body; all listed fields required unless marked optional; no secret, self digest or accepting provenance. See owner package for types/limits.",
    "uniqueness": "One exact body per full logical lineage + represented input cut; different competing body rejects; exact command retry returns original accepted receipt. No mutable replacement.",
    "revision": "Only bodies explicitly listing a predecessor form revision lineages: exact predecessor of same kind, ID, campaign/source and subject; one successor by CAS. Projection/member bodies without predecessor are new immutable entries for changed represented tuple/cut; no hidden predecessor field or timestamp/latest-by-ID selector.",
    "migration": "Fresh approved successor campaign only; old bytes/readers retain original contracts; no fabricated chronology or in-place schema upgrade.",
    "consumers": ["COORDINATOR", "VALIDATOR"],
}

proposals = {}


def propose(kind, role, body, refs, basis, authority, predicates, alternatives):
    key = kind + "/1"
    proposals[key] = dict(
        common,
        kind=kind,
        version="1",
        canonical_role=role,
        body=body,
        material_refs=refs,
        normative_basis=basis,
        authoritative_for=authority,
        cross_object_predicates=predicates,
        alternatives_rejected=alternatives,
        schema_key="BDB_SCHEMA_REGISTRY::" + key,
    )


risk = old["hypothetical_registry_rows"][0]
proposals["residual_risk/1"] = dict(
    common,
    **{k: v for k, v in risk.items() if k not in common},
    design_artifact="R5_4_2_RESIDUAL_RISK_CONTRACT_DECISION_PROPOSAL.md",
    design_raw_digest=digest(
        OUT / "R5_4_2_RESIDUAL_RISK_CONTRACT_DECISION_PROPOSAL.md"
    ),
    semantic_change_in_this_pass=False,
)

propose(
    "assurance_claim_set",
    "DERIVED_PROJECTION",
    [
        "assurance_claim_set_id:ID",
        "scope_inventory_ref:TypedRef",
        "claim_refs:TypedRef[]",
        "claim_set_input_history_cut:HistoryCut",
    ],
    [
        ref("scope_inventory_ref", ["inventory_revision"]),
        ref("claim_refs", ["finding_claim_revision"], "0..65536"),
        ref("claim_set_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
    ],
    ["Data §50, §80; Architecture §31; previously undefined required target D1"],
    "Exact, complete enumeration of accepted finding-claim revisions applicable to the pinned inventory/campaign/source/cut; no truth or assurance verdict",
    [
        "Include all claim revisions on explicit unsuperseded accepted lineages intersecting inventory scope; include uncertain scope and rejected/unresolved claims, never filter by favorable adjudication.",
        "Candidate claim_refs equal this set and independently recomputed set; candidate inventory identical; represented cuts equal. Candidate may accept this earlier same-commit derived node; claims themselves must be prior accepted.",
        "Current adjudications, contradictions, qualifications, mandatory obligations and risks are independently closed in Candidate; absence of claim for unknown scope never reduces denominator.",
        "No predecessor field: enumeration at a new cut is a new immutable projection; represented tuple is unique, not a mutable current set.",
    ],
    [
        "FACT/ASSESSMENT would misleadingly confer truth to enumeration; SOUND is single-claim qualification not set; snapshot is general capture; inline array removes frozen required reference and duplicates Candidate array."
    ],
)

propose(
    "public_conclusion_statement",
    "DERIVED_PROJECTION",
    [
        "public_conclusion_statement_id:ID",
        "campaign_conclusion_ref:TypedRef",
        "statement_input_history_cut:HistoryCut",
        "render_profile_ref:ExternalProfileRef",
        "statement_raw_ref:RawRef",
    ],
    [
        ref("campaign_conclusion_ref", ["campaign_conclusion"]),
        ref("statement_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
        ref("render_profile_ref", [], "1", "PINNED_PROFILE_REF"),
        ref("statement_raw_ref", [], "1", "CONTENT_OBJECT"),
    ],
    ["Data §76, §80, §81, §118–119; Architecture §§31–32; undefined target D2"],
    "Retained exact public bytes communicating a prior canonical conclusion; no new assurance/release authorization",
    [
        "Raw bytes equal deterministic public renderer of exact Conclusion→STOP→StopInput closure under proposed PUBLIC_CONCLUSION_RENDER_V1; validation independently reads retained bytes.",
        "Renderer discloses all exact residual-risk refs and bounded/limited state, exact scope/source, STOP axes and conclusion; no arbitrary caller narrative or PASS/READY synonym.",
        "Statement cut contains conclusion and its entire authority closure; acceptance rejects intervening audit-basis drift. FinalCase refers prior accepted statement for same exact conclusion.",
        "No FinalCase or ReleaseQualification future ref; STOP release axis labelled assessment only, release authorization not established here.",
        "One deterministic rendering per conclusion/profile; repacking/replacement raw conflicts; new public representation is new immutable projection, never conclusion revision.",
    ],
    [
        "General report_export_receipt requires a final report with future FinalCase (§81), causing a cycle; RawRef alone lacks semantic prior-acceptance binding; FACT would create competing truth; EXPORT bytes stay raw while typed semantic wrapper uses ObjectDigest."
    ],
)

propose(
    "observation_dependency",
    "FACT",
    [
        "observation_dependency_id:ID",
        "observation_ref:TypedRef",
        "dependency_refs:DependencyRef[]",
        "dependency_input_history_cut:HistoryCut",
        "basis_observation_refs:TypedRef[]",
        "previous_dependency_ref?:TypedRef",
    ],
    [
        ref("observation_ref", ["observation"]),
        ref(
            "dependency_refs",
            ["environment_record", "execution_descriptor", "source_generation"],
            "1..65536",
        ),
        ref("basis_observation_refs", ["observation"], "1..65536"),
        ref("dependency_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
        ref("previous_dependency_ref", ["observation_dependency"], "0..1"),
    ],
    ["Data §33, §46, §49, §121; Architecture §22.1"],
    "Observed/declared exact dependency relationship of an observation path, not independence judgment",
    [
        "DependencyRef is closed tagged union of the finite typed targets above, retained RawRef (fixture/module/observer bytes) or pinned ExternalProfileRef (harness/oracle/parser/cache/process profile); tags and full identity sorted, duplicate rejected.",
        "Each dependency is matched to exact ExecutionDescriptor/Environment and capture observations; unknown capture cannot assert absence of dependency; no future ExecutionResult.",
        "Dependency changes create explicit successor fact; all graph inputs remain reconstructible from these accepted facts.",
    ],
    [
        "Raw declaration alone cannot replace canonical ObservationDependency facts explicitly required by §46; graph export is projection, not dependency fact; independence assessment has separate meaning."
    ],
)

propose(
    "evidence_dependency_graph",
    "DERIVED_PROJECTION",
    [
        "evidence_dependency_graph_id:ID",
        "root_observation_refs:TypedRef[]",
        "dependency_fact_refs:TypedRef[]",
        "graph_input_history_cut:HistoryCut",
    ],
    [
        ref("root_observation_refs", ["observation"], "1..65536"),
        ref("dependency_fact_refs", ["observation_dependency"], "1..65536"),
        ref("graph_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
    ],
    ["Data §46–49, §92; Registry dependency_graph_ref/dependency_set_ref"],
    "Exact reproducible dependency traversal input identity; deleting exported graph cannot change qualification truth",
    [
        "Facts equal full reachable active accepted observation-dependency lineage closure for roots at cut; omission/cycle/cross-context rejection.",
        "Consumers independently derive node/edge closure and required dependency identities; no hand-picked shared/independent subset.",
        "DependencyIndependenceAssessment claims must match this graph/root claim/failure assumption; invalidation propagates through exact dependency memberships.",
        "No stored redundant node/edge summary; explicit fact refs retain exact source authority; new root/cut means new projection.",
    ],
    [
        "snapshot has no exact dependency schema; external graph bytes alone cannot bind accepted fact closure; no new mutable evidence graph authority."
    ],
)

propose(
    "corpus_member_candidate",
    "FACT",
    [
        "member_candidate_id:ID",
        "raw_or_object_revision_ref:MemberRef",
        "producer_stage_ref?:TypedRef",
        "producer_lane_ref?:TypedRef",
        "source_generation_ref:TypedRef",
        "mechanical_validation_assessment_ref?:TypedRef",
        "source_reconciliation_assessment_ref?:TypedRef",
        "historical_role:CorpusRole",
    ],
    [
        ref(
            "raw_or_object_revision_ref",
            [
                "legacy_raw_ref",
                "snapshot",
                "finding_claim_revision",
                "final_assurance_case",
            ],
            "1",
            "CONTENT_OR_PRIOR",
        ),
        ref("producer_stage_ref", ["stage_run"], "0..1"),
        ref("producer_lane_ref", ["lane_run"], "0..1"),
        ref("source_generation_ref", ["source_generation"]),
        ref(
            "mechanical_validation_assessment_ref",
            ["legacy_mechanical_validation_assessment"],
            "0..1",
        ),
        ref(
            "source_reconciliation_assessment_ref",
            ["source_reconciliation_assessment"],
            "0..1",
        ),
    ],
    [
        "Data §24–26 explicitly names immutable CORPUS_MEMBER_CANDIDATE; registered admission lacks executable reference contract"
    ],
    "Exact immutable candidate for later consumer/role admission; no admission authority",
    [
        "MemberRef is exact TypedRef from listed set or durable RawRef under corpus-member transport profile; role is finite §25 enum.",
        "Source and producer bindings independently checked; candidate cannot contain later admission or CorpusManifest.",
        "Admission refers this candidate before manifest; new raw/member identity creates new immutable candidate, not an update.",
    ],
    [
        "legacy_raw_ref cannot represent native members; CorpusManifest is aggregate accepted membership and would cycle with admission; raw alone lacks role/producer/source semantics."
    ],
)

propose(
    "effort_results",
    "DERIVED_PROJECTION",
    [
        "effort_results_id:ID",
        "effort_input_history_cut:HistoryCut",
        "effort_profile_ref:ExternalProfileRef",
        "stage_completion_refs:TypedRef[]",
        "execution_result_refs:TypedRef[]",
        "metric_basis_refs:TypedRef[]",
    ],
    [
        ref("effort_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
        ref("effort_profile_ref", [], "1", "HISTORY_CONTEXT_BINDING"),
        ref("stage_completion_refs", ["stage_completion"], "0..65536"),
        ref("execution_result_refs", ["execution_result"], "0..65536"),
        ref(
            "metric_basis_refs",
            [
                "observation",
                "discovery_record",
                "root_cause_revision",
                "coverage_obligation_qualification",
                "challenger_result",
            ],
            "0..65536",
        ),
    ],
    ["Data §75–76, §141–142; Architecture §32.2/32.5"],
    "Exact replayable effort/saturation calculation inputs, never completeness or STOP authority",
    [
        "Input sets equal complete applicable histories required by exact EFFORT_PROFILE_V1 at cut; no subset by favorable outcome.",
        "STOP independently recomputes rounds/method families/budget and saturation from accepted facts; missing duration/workload witness yields INSUFFICIENT_DATA, not zero/default PASS.",
        "Same profile and cut as StopInput; profiles cannot redefine effort in same commit. Numbers/thresholds remain explicit pinned campaign policy parameters, not universal BDB constants.",
        "New cut/profile means new immutable projection; deterministic set ordering; no summary scalars as authority.",
    ],
    [
        "unconstrained generic object leaves mandatory effort_results_ref ambiguous; saturation alone is heuristic; snapshot seal alone does not enforce exhaustive effort basis."
    ],
)

propose(
    "fault_spec",
    "FACT",
    [
        "fault_id:ID",
        "fault_revision:positive integer",
        "previous_fault_ref?:TypedRef",
        "fault_class:profile enum",
        "injection_point:bounded text",
        "activation_predicate_ref:ExternalProfileRef",
        "expected_observable:bounded text",
        "safety_constraints:bounded text[]",
        "cleanup_spec_ref:ExternalProfileRef",
        "fault_input_history_cut:HistoryCut",
    ],
    [
        ref("previous_fault_ref", ["fault_spec"], "0..1"),
        ref("fault_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
        ref("activation_predicate_ref", [], "1", "HISTORY_CONTEXT_BINDING"),
        ref("cleanup_spec_ref", [], "1", "HISTORY_CONTEXT_BINDING"),
    ],
    ["Data §41, §44–45; required crash/fault qualification paths"],
    "Immutable preregistered fault intent; never proof of activation",
    [
        "Descriptor experiment references exact prior fault revision; fault run uses same fault and descriptor; actual activation from retained witness only.",
        "No class transition or safety expansion without new revision; revision number increments along exact predecessor.",
        "Safety/destructive actions remain separately authorized ApprovalDecision; this intent grants no live authority.",
    ],
    [
        "FaultRunRecord is later observation, cannot be own preregistration; generic method label cannot identify exact fault predicate."
    ],
)

propose(
    "state_model",
    "FACT",
    [
        "state_model_id:ID",
        "model_revision:positive integer",
        "previous_model_ref?:TypedRef",
        "implementation_mapping_ref:RawRef",
        "source_generation_ref:TypedRef",
        "scope_refs:TypedRef[]",
        "model_artifact_ref:RawRef",
        "model_profile_ref:ExternalProfileRef",
        "model_input_history_cut:HistoryCut",
    ],
    [
        ref("previous_model_ref", ["state_model"], "0..1"),
        ref("source_generation_ref", ["source_generation"]),
        ref(
            "scope_refs",
            ["surface_record", "invariant_revision", "scope_state_record"],
            "1..65536",
        ),
        ref("model_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
        ref("implementation_mapping_ref", [], "1", "CONTENT_OBJECT"),
        ref("model_artifact_ref", [], "1", "CONTENT_OBJECT"),
        ref("model_profile_ref", [], "1", "HISTORY_CONTEXT_BINDING"),
    ],
    ["Data §71–72; mandatory E4 fidelity/conformance"],
    "Exact immutable model/mapping/assumption revision; no implementation proof",
    [
        "MODEL_ARTIFACT_V1 raw contract requires finite state variables/domains, transitions, initial/forbidden states, abstraction assumptions, bounds, omitted states and fairness/time assumptions (§71).",
        "Mapping raw contains closed map of model symbols to exact source anchors; profile supplies grammar and checker; all members exact retained bytes.",
        "Fidelity independently reads model/mapping and exact implementation anchors; MODEL_VERIFIED alone never qualifies implementation obligation.",
        "Scope/source/model changes create explicit new revision; no future fidelity reference.",
    ],
    [
        "ModelFidelityAssessment is later judgment about model, not model itself; raw bytes alone lack exact scope/source/revision binding."
    ],
)

# Other method artifacts have an explicit raw representation; they do not acquire
# a canonical truth role merely because a narrative names a Record/Case.
discovery_targets = keys(
    "blind_origin_eligibility_assessment",
    "discovery_confirmation_assessment",
    "discovery_corpus_match_assessment",
    "discovery_novelty_assessment",
    "false_negative_relationship_assessment",
    "discovery_tool_origin_assessment",
)
propose(
    "gate_decision",
    "DECISION",
    [
        "gate_decision_id:ID",
        "campaign_id:CampaignID",
        "stage_run_ref:TypedRef",
        "attempt_ref:TypedRef",
        "gate_policy_ref:ExternalProfileRef",
        "input_history_cut:HistoryCut",
        "checkpoint_ref:TypedRef",
        "knowledge_state_ref:TypedRef",
        "requested_view_ref:TypedRef",
        "eligibility_result:ALLOW|DENY|UNKNOWN",
        "reason_codes:Code[]",
    ],
    [
        ref("stage_run_ref", ["stage_run"]),
        ref("attempt_ref", ["attempt"]),
        ref("input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
        ref("checkpoint_ref", ["checkpoint"]),
        ref("knowledge_state_ref", ["knowledge_state"]),
        ref("requested_view_ref", ["view_manifest"]),
    ],
    ["Data §87–88; checkpoint resume/reveal eligibility"],
    "Exact cut-bound eligibility decision for proposed guarded transition/view; not owner approval or delivery proof",
    [
        "Policy is exact prior HISTORY_CONTEXT_BINDING; scope/campaign/stage/attempt/checkpoint/knowledge/view match; input head must remain current when consumed.",
        "ALLOW requires every original checkpoint/FSM/isolation/knowledge/positive-view predicate; UNKNOWN never authorizes exposure.",
        "GateDecision may be earlier content in the same atomic guarded-transition closure. Proposal has no independent issue/consume authority; its parent equals current command parent. A prior gate cannot authorize changed inputs: recompute gate on current cut and produce fresh decision when represented inputs/cut differ; full CAS revalidation applies.",
    ],
    [
        "ApprovalDecision is human/governance authorization with different meaning; CommandReceipt is post-acceptance acknowledgment; neither replaces gate eligibility."
    ],
)
propose(
    "handoff_validation_result",
    "ASSESSMENT",
    [
        "handoff_validation_result_id:ID",
        "handoff_ref:RawRef",
        "contract_ref:ExternalProfileRef",
        "transport_integrity_result:PASS|FAIL|UNKNOWN",
        "schema_results:LayerResult[]",
        "source_binding_result:PASS|FAIL|UNKNOWN",
        "run_attempt_binding_result:PASS|FAIL|UNKNOWN",
        "checkpoint_result:PASS|FAIL|UNKNOWN",
        "history_cut_result:PASS|FAIL|UNKNOWN",
        "overall_status:PASS|FAIL|BLOCKED",
        "input_history_cut:HistoryCut",
        "reason_codes:Code[]",
    ],
    [
        ref("input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
        ref("handoff_ref", [], "1", "CONTENT_OBJECT"),
    ],
    ["Data §86–88; checkpoint/handoff recovery admission"],
    "Exact transport/source/run/checkpoint/cut assessment of retained handoff; no reveal or knowledge authority",
    [
        "Trusted validator reads retained handoff bytes under exact prior transport/schema/context; all component PASS required for overall PASS.",
        "Embedded canonical references are checked against accepted campaign/source/attempt/cut independently; raw assertions alone cannot establish authority.",
        "Distinct raw or cut gives immutable new assessment; no claim of future transition or delivery acceptance.",
    ],
    [
        "Generic ValidationResult lacks all named required binding axes; NF02 AdmissionEvidence establishes lane result provenance, not checkpoint handoff semantics."
    ],
)
for kind, body, extra_refs, predicates in [
    (
        "discovery_confirmation_assessment",
        [
            "confirmation_policy_ref:ExternalProfileRef",
            "confirmation_mode:PREREGISTERED|EXPLORATORY|LEGACY_IMPORTED",
            "confirmation_evidence_refs:TypedRef[]",
            "result:CONFIRMED|NOT_CONFIRMED|INCONCLUSIVE|BLOCKED",
        ],
        [
            ref(
                "confirmation_evidence_refs",
                ["evidence_qualification_assessment"],
                "0..65536",
            )
        ],
        [
            "CONFIRMED requires current qualified observation/evidence about the exact discovery; confirmation mode matches accepted experiment chronology; not finding adjudication."
        ],
    ),
    (
        "discovery_corpus_match_assessment",
        [
            "corpus_snapshot_ref:TypedRef",
            "match_policy_ref:ExternalProfileRef",
            "matched_prior_claim_refs:TypedRef[]",
            "match_result:MATCH|NO_MATCH|PARTIAL|INCONCLUSIVE",
        ],
        [
            ref("corpus_snapshot_ref", ["corpus_manifest"]),
            ref("matched_prior_claim_refs", ["finding_claim_revision"], "0..65536"),
        ],
        [
            "Match set derived from every eligible exact corpus member under pinned matcher; incomplete corpus/search => INCONCLUSIVE; NO_MATCH requires complete declared search; not blind eligibility."
        ],
    ),
    (
        "discovery_novelty_assessment",
        [
            "corpus_match_assessment_ref:TypedRef",
            "novelty_policy_ref:ExternalProfileRef",
            "result:NOVEL|PREVIOUSLY_KNOWN|PARTIALLY_NOVEL|INCONCLUSIVE",
        ],
        [ref("corpus_match_assessment_ref", ["discovery_corpus_match_assessment"])],
        [
            "Same discovery and cut-applicable corpus matching; novelty is scoped relative to disclosed corpus only, not proof of universal novelty."
        ],
    ),
    (
        "false_negative_relationship_assessment",
        [
            "predecessor_stage_or_claim_refs:TypedRef[]",
            "relationship_policy_ref:ExternalProfileRef",
            "result:PREVIOUS_FALSE_NEGATIVE|MULTI_STAGE_FALSE_NEGATIVE|NOT_ESTABLISHED|INCONCLUSIVE",
        ],
        [
            ref(
                "predecessor_stage_or_claim_refs",
                ["stage_completion", "finding_claim_revision"],
                "1..65536",
            )
        ],
        [
            "Prior stage must demonstrably have required applicable obligation/scope and missed exact later-confirmed issue; lack of investigated scope cannot establish previous false negative."
        ],
    ),
    (
        "discovery_tool_origin_assessment",
        [
            "producer_ref:AuthorityRef",
            "method_ref:ExternalProfileRef",
            "tool_profile_ref?:ExternalProfileRef",
            "result:VERIFIED|INCONCLUSIVE|BLOCKED",
        ],
        [],
        [
            "Producer/method/tool refs match accepted DiscoveryRecord capture and installation-authorized producer; origin is provenance, never strength/independence."
        ],
    ),
]:
    propose(
        kind,
        "ASSESSMENT",
        [
            "assessment_id:ID",
            "discovery_ref:TypedRef",
            "assessment_input_history_cut:HistoryCut",
            "previous_assessment_ref?:TypedRef",
        ]
        + body
        + ["reason_codes:Code[]"],
        [
            ref("discovery_ref", ["discovery_record"]),
            ref("assessment_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
            ref("previous_assessment_ref", [kind], "0..1"),
        ]
        + extra_refs,
        [
            "Data §57 explicitly requires separate canonical assessments; missing Registry rows and FindingClaimRevision target mismatch"
        ],
        "Only the named discovery provenance dimension for exact accepted discovery and cut",
        predicates
        + [
            "All profile refs HISTORY_CONTEXT_BINDING; all authority-bearing evidence/corpus refs PRIOR_ACCEPTED_ONLY; all refs backward, no modification of DiscoveryRecord.",
            "New dimension evidence/corpus/policy creates immutable successor with exact predecessor; no retroactive blind label; result domain is explicit proposed completion where §57 only said result.",
        ],
        [
            "Generic ApprovalDecision is governance, not provenance assessment; DiscoveryRecord is prior observation and cannot contain future assessment; narrative label is not authority."
        ],
    )

for kind, role, body, refs_, predicates in [
    (
        "defect_unit",
        "FACT",
        [
            "defect_unit_id:ID",
            "corpus_revision_ref:TypedRef",
            "defect_class:ground-truth profile enum",
            "affected_scope_ref:TypedRef",
            "activation_witness_ref:TypedRef",
            "violated_invariant_ref?:TypedRef",
            "ground_truth_provenance_ref:RawRef",
        ],
        [
            ref("corpus_revision_ref", ["corpus_manifest"]),
            ref(
                "affected_scope_ref",
                ["surface_record", "invariant_revision", "scope_state_record"],
            ),
            ref("activation_witness_ref", ["observation"]),
            ref("violated_invariant_ref", ["invariant_revision"], "0..1"),
        ],
        [
            "Ground truth is independently installation/policy-pinned corpus issuer evidence with known-defect activation, not a claim minted from auditor output; no denominator based on detected findings."
        ],
    ),
    (
        "negative_opportunity_unit",
        "FACT",
        [
            "negative_opportunity_id:ID",
            "corpus_revision_ref:TypedRef",
            "benign_scenario_ref:TypedRef",
            "prohibited_or_false_claim_scope:TypedRef[]",
            "ground_truth_provenance_ref:RawRef",
        ],
        [
            ref("corpus_revision_ref", ["corpus_manifest"]),
            ref("benign_scenario_ref", ["experiment_spec"]),
            ref(
                "prohibited_or_false_claim_scope",
                ["surface_record", "invariant_revision", "scope_state_record"],
                "1..65536",
            ),
        ],
        [
            "Independently pinned benign opportunity and exact prohibited claim scope; denominator includes each declared opportunity, not only reported negatives."
        ],
    ),
    (
        "finding_defect_match_assessment",
        "ASSESSMENT",
        [
            "assessment_id:ID",
            "finding_claim_revision_ref:TypedRef",
            "finding_adjudication_ref?:TypedRef",
            "defect_unit_ref:TypedRef",
            "match_result:MATCH|NO_MATCH|PARTIAL|UNRESOLVED",
            "rationale_refs:TypedRef[]",
            "assessor_profile_ref:ExternalProfileRef",
        ],
        [
            ref("finding_claim_revision_ref", ["finding_claim_revision"]),
            ref("finding_adjudication_ref", ["finding_adjudication_decision"], "0..1"),
            ref("defect_unit_ref", ["defect_unit"]),
            ref(
                "rationale_refs",
                ["observation", "evidence_qualification_assessment"],
                "1..65536",
            ),
        ],
        [
            "Exact claim/adjudication pair and unit scope; unseeded real finding is not false positive merely absent from seeded units; partial match is not full detection."
        ],
    ),
    (
        "clean_control_assessment",
        "ASSESSMENT",
        [
            "assessment_id:ID",
            "finding_claim_revision_ref?:TypedRef",
            "finding_adjudication_ref?:TypedRef",
            "negative_opportunity_ref:TypedRef",
            "outcome:TRUE_NEGATIVE|FALSE_POSITIVE|UNRESOLVED|BLOCKED",
            "rationale_refs:TypedRef[]",
            "assessor_profile_ref:ExternalProfileRef",
        ],
        [
            ref("finding_claim_revision_ref", ["finding_claim_revision"], "0..1"),
            ref("finding_adjudication_ref", ["finding_adjudication_decision"], "0..1"),
            ref("negative_opportunity_ref", ["negative_opportunity_unit"]),
            ref(
                "rationale_refs",
                ["observation", "evidence_qualification_assessment"],
                "1..65536",
            ),
        ],
        [
            "FALSE_POSITIVE requires independently demonstrated prohibited/false claim on exact clean opportunity; no result by majority/support count."
        ],
    ),
    (
        "holdout_exposure_assessment",
        "ASSESSMENT",
        [
            "assessment_id:ID",
            "corpus_revision_ref:TypedRef",
            "evaluator_or_executor_profile_ref:TypedRef",
            "exposure_state:UNSEEN|POTENTIALLY_EXPOSED|EXPOSED|UNKNOWN",
            "exposure_input_history_cut:HistoryCut",
            "previous_assessment_ref?:TypedRef",
        ],
        [
            ref("corpus_revision_ref", ["corpus_manifest"]),
            ref(
                "evaluator_or_executor_profile_ref",
                ["executor_spec"],
                "1",
                "HISTORY_CONTEXT_BINDING",
            ),
            ref("exposure_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
            ref("previous_assessment_ref", ["holdout_exposure_assessment"], "0..1"),
        ],
        [
            "UNSEEN requires complete grant/potential-exposure/knowledge closure for exact evaluation path; after possible exposure never revert UNSEEN by new ID/session absent separately qualified isolation path."
        ],
    ),
]:
    if kind != "holdout_exposure_assessment":
        body += [
            "assessment_input_history_cut:HistoryCut",
            "previous_revision_ref?:TypedRef",
        ]
        refs_ += [
            ref("assessment_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
            ref("previous_revision_ref", [kind], "0..1"),
        ]
    propose(
        kind,
        role,
        body,
        refs_,
        [
            "Data §149 canonical calibration support; E5A calibration→Candidate (Architecture §31)"
        ],
        "Exact " + kind + " calibration input/assessment, never product completeness",
        predicates
        + [
            "Ground truth/assessor profile is an exact prior pin; raw support independently retained and parsed; current corpus/member source and scope equality required.",
            "Immutable revision and explicit predecessor; full denominator is all eligible units in pinned corpus; unqualified/missing units count unknown, never favorable exclusion.",
        ],
        [
            "Finding claim is tested statement, not ground truth; raw auditor output cannot approve itself; generic corpus membership is not calibration truth or exposure assessment."
        ],
    )

raw_designs = {
    "REPLAY_CAPSULE_V1": {
        "basis": "Data §65–66",
        "fields": [
            "finding_or_claim_revision_ref",
            "subject_baseline_ref",
            "environment_profile_ref",
            "dependency_set_ref",
            "harness_ref",
            "fixture_refs",
            "seed_ref optional",
            "generator_profile_ref",
            "command_spec",
            "expected_invariant_ref",
            "expected_observable",
            "observer_requirements",
            "cleanup_spec",
            "producer_ref",
            "artifact_raw_refs",
        ],
        "rule": "Exact immutable bundle RawRef + bundle_manifest/1; accepted descriptor and observation point to retained capsule. Current evidence/applicability/independence assessments, not capsule, establish replay support.",
    },
    "IMPLEMENTATION_MUTATION_CASE_V1": {
        "basis": "Data §67–68",
        "fields": [
            "mutation_id",
            "mutation_revision",
            "target_claim_or_invariant_ref",
            "target_location",
            "activation_predicate",
            "expected_detector_or_observer",
            "positive_control_ref",
            "negative_control_ref",
            "clean_target_ref",
            "known_defective_target_ref",
        ],
        "rule": "Preregistered experiment_spec/1 references exact case RawRef; execution_result/1 plus retained observation payload uses exact ImplementationMutationOutcome enum from §68; EvidenceQualification independently derives activation/detection and obligation effect.",
    },
    "ORACLE_CHALLENGE_CASE_V1": {
        "basis": "Data §67–68; Architecture §31",
        "fields": [
            "mutation_id",
            "mutation_revision",
            "target_claim_or_invariant_ref",
            "target_location",
            "activation_predicate",
            "expected_detector_or_observer",
            "positive_control_ref",
            "negative_control_ref",
            "clean_target_ref",
            "known_defective_target_ref",
            "strong_oracle_ref",
            "weakened_oracle_ref",
        ],
        "rule": "Preregistered experiment_spec/1 references exact case RawRef; retained observations bind all 4 clean/defective × strong/weakened execution descriptors, actual activation and exact §68 OracleChallengeOutcome. Validator recomputes outcome; clean PASS alone cannot establish WEAKENING_DETECTED.",
    },
    "TEMPORAL_MODEL_CLAIM_V1": {
        "basis": "Data §72",
        "fields": [
            "model_revision_ref",
            "invariant_revision_ref",
            "implementation_scope_refs",
            "assumptions",
            "bounds",
        ],
        "rule": "Represent statement with existing invariant_revision/1 + exact retained formal specification RawRef. PROPOSED/MODEL_VERIFIED/IMPLEMENTATION_CONFORMANCE_QUALIFIED/VIOLATED/BLOCKED are derived states of exact execution/evidence/fidelity facts; no standalone status mutation.",
    },
    "CAUSAL_CHAIN_V1": {
        "basis": "Data §73",
        "fields": [
            "trigger",
            "state_transition_refs",
            "observation_refs",
            "impact_ref",
            "scope",
            "evidence_qualification_refs",
        ],
        "rule": "Typed traversal in raw observation or derived snapshot; each exact step is independently accepted provenance. No evidence transfer through similarity.",
    },
    "ENDURANCE_OBSERVATION_V1": {
        "basis": "Data §74",
        "fields": [
            "duration_workload_profile_ref",
            "environment_ref",
            "resource_baselines",
            "monitoring_path_refs",
            "stop_abort_reason",
            "observation_refs",
        ],
        "rule": "Existing execution_descriptor/result and retained observation payload; coverage requires workload and observer completeness, never nominal elapsed duration alone.",
    },
    "BUILD_PROVENANCE_RECEIPT_V1": {
        "basis": "Data §123–124",
        "fields": [
            "build_input_manifest_ref",
            "final_output_raw_ref",
            "build_environment_ref",
            "verification_refs",
        ],
        "rule": "External raw receipt binds existing build_manifest/1 as exact build-input identity; no output hash embedded in its own bytes; build/install governance validates full closure.",
    },
}

scope_keys = keys(
    "surface_record",
    "surface_key",
    "invariant_revision",
    "finding_claim_revision",
    "coverage_obligation",
    "scope_state_record",
)
classes = {
    "typed_scope_ref": scope_keys,
    "materiality_subject_ref": keys(
        "surface_record", "surface_key", "invariant_revision", "scope_state_record"
    ),
    "residual_risk_ref": keys("residual_risk"),
    "assurance_claim_set_ref": keys("assurance_claim_set"),
    "public_conclusion_statement_ref": keys("public_conclusion_statement"),
    "finding_or_risk_ref": keys(
        "finding_claim_revision", "finding_adjudication_decision", "residual_risk"
    ),
    "limited_conclusion_basis_ref": keys(
        "stage_completion",
        "coverage_obligation",
        "coverage_obligation_qualification",
        "evidence_invalidation",
        "contradiction_revision",
        "residual_risk",
        "stop_evaluation",
        "approval_decision",
    ),
    "dependency_graph_ref": keys("evidence_dependency_graph"),
    "scope_decision_ref": keys("approval_decision"),
    "control_ref": keys("experiment_spec"),
    "coverage_obligation_summary_ref": keys("snapshot"),
    "release_reassessment_input_ref": keys(
        "approval_decision",
        "residual_risk",
        "evidence_applicability_assessment",
        "evidence_qualification_assessment",
        "evidence_invalidation",
        "source_drift_record",
        "source_drift_impact_assessment",
        "observation",
        "environment_record",
        "policy_revision",
    ),
    "application_generation_ref": keys("build_manifest"),
    "schema_set_ref": keys("schema_registry/2"),
    "protocol_policy_bundle_ref": [],
    "campaign_ref": keys("campaign_genesis", "successor_campaign_genesis"),
    "assigned_input_ref": keys(
        "source_manifest", "legacy_raw_ref", "surface_collector_record"
    ),
}
terminal = {
    "history_namespace_ref": "Exact namespace pin in installation root; not a new object",
    "EMPTY_HISTORY": "Tagged initial parent only",
    "EMPTY_HISTORY_CUT": "Tagged initial cut only",
    "accepted_head_ref": "Exact campaign + seq + CommitHash tuple read from verified history",
    "accepted_history_cut": "Closed accepted HistoryCut under §15.4",
    "accepted_event_ref": "Exact accepted CommitHash/ordinal/type; prior history only",
    "actor_or_authority_ref": "Exact installation-authorized principal/role/scope revision in prior TrustProfile; no self-issued actor object",
    "owner_operator_authority_ref": "Exact installation-authorized owner principal/scope from TrustProfile",
    "repository_or_snapshot_authority_ref": "Externally authorized repository/snapshot identity checked under SOURCE_IDENTITY_PIN; not workspace path",
    "predecessor_pin_ref": "Exact external installation/trust predecessor identity/freshness pin",
    "serialization_profile_pin": "Exact BDB-CJSON-1 external profile RawDigest from installation",
    "source_identity_profile_pin": "Exact source identity ExternalProfileRef from installation",
    "result_slot_contract_ref": "Exact NF02_EXTERNAL_LANE_SLOT_V2 ExternalProfileRef; active stage/lane/attempt tuple",
    "external_profile_ref": "Closed ExternalProfileRef; finite profile definitions in external_profiles",
    "raw_artifact_ref": "Closed RawRef + exact retained bytes + finite transport profile; no path authority",
    "candidate_manifest_raw_digest": "RawDigest of retained external reviewed manifest bytes",
    "review_raw_digest": "RawDigest of retained external review bytes",
    "PRIOR_ACCEPTED_ONLY": "Reference-class marker, not a target kind",
}

# Exact decisions for every existing generic material-ref field. General storage
# wrappers are narrowed later to the finite reachable set, never all installed kinds.
overrides = {
    ("approval_decision", "related_refs"): keys(
        "residual_risk",
        "coverage_obligation",
        "scope_state_record",
        "stage_spec",
        "stop_evaluation",
        "source_generation",
        "experiment_spec",
    ),
    ("attempt", "retry_reason_ref"): keys(
        "execution_result",
        "observation",
        "contamination_assessment",
        "isolation_qualification",
        "checkpoint",
    ),
    ("contamination_assessment", "channel_inventory_ref"): keys("snapshot"),
    ("isolation_qualification", "channel_inventory_ref"): keys("snapshot"),
    ("contradiction_resolution_decision", "basis_refs"): keys(
        "evidence_qualification_assessment",
        "evidence_applicability_assessment",
        "finding_axis_assessment",
        "experiment_spec",
        "execution_result",
        "observation",
        "policy_revision",
        "spec_revision",
    ),
    ("coverage_obligation", "origin_ref"): keys(
        "inventory_revision",
        "invariant_revision",
        "hypothesis_revision",
        "discovery_record",
        "finding_claim_revision",
        "stop_evaluation",
    ),
    ("finding_axis_assessment", "method_or_characterization_refs"): keys(
        "experiment_spec",
        "execution_result",
        "observation",
        "model_fidelity_assessment",
    ),
    ("lineage_admission_assessment", "freshness_binding_refs"): keys(
        "legacy_mechanical_validation_assessment",
        "source_reconciliation_assessment",
        "history_anchor_receipt",
    ),
    ("materiality_assessment", "supporting_fact_refs"): keys(
        "surface_record",
        "invariant_revision",
        "inventory_revision",
        "observation",
        "finding_claim_revision",
    ),
    ("scope_state_record", "basis_refs"): keys(
        "input_disposition_record",
        "surface_record",
        "surface_collector_record",
        "observation",
        "source_manifest",
    ),
    ("stop_input", "effort_results_ref"): keys("effort_results"),
    ("stop_input", "release_basis_refs"): classes["release_reassessment_input_ref"],
    ("successor_campaign_selection_decision", "resolution_basis_refs"): keys(
        "approval_decision",
        "evidence_invalidation",
        "source_drift_record",
        "inventory_revision",
        "finding_adjudication_decision",
    ),
    ("surface_record", "provenance_refs"): keys(
        "surface_collector_record", "observation", "tool_execution_record"
    ),
    ("finding_claim_revision", "discovery_relation_refs"): discovery_targets,
    ("dependency_independence_assessment", "observer_path_refs"): keys(
        "observation", "observation_dependency", "execution_descriptor"
    ),
    ("dependency_independence_assessment", "shared_dependency_refs"): keys(
        "observation_dependency"
    ),
    ("dependency_independence_assessment", "independent_dependency_refs"): keys(
        "observation_dependency"
    ),
}
for kind in ("contamination_assessment", "isolation_qualification"):
    for r in rows[kind + "/1"]["material_refs"]:
        if (
            r["allowed"] == ["registered_immutable_object"]
            and (kind, r["field"]) not in overrides
        ):
            overrides[kind, r["field"]] = keys(
                "observation", "tool_execution_record", "execution_result"
            )
for field in ("controlled_exposure_fact_refs", "supporting_history_refs"):
    overrides["legacy_exposure_reconstruction_assessment", field] = keys(
        "potential_exposure_record",
        "grant_body",
        "knowledge_state",
        "observation",
        "legacy_raw_ref",
    )

# Supplement schema-deferred rows with refs specified by complete Data sections.
# These are proposed explicit completion deltas; not alterations to qualified rows.
supplements = {}


def supplement(kind, refs):
    supplements[kind + "/1"] = refs


supplement(
    "hypothesis_revision",
    [
        ref("source_generation_ref", ["source_generation"]),
        ref("scope_refs", scope_keys, "0..65536", "CONTENT_OR_PRIOR"),
        ref("invariant_refs", ["invariant_revision"], "0..65536", "CONTENT_OR_PRIOR"),
        ref("obligation_refs", ["coverage_obligation"], "0..65536", "CONTENT_OR_PRIOR"),
        ref("origin_discovery_ref", ["discovery_record"], "0..1"),
        ref("input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
    ],
)
supplement(
    "experiment_spec",
    [
        ref("hypothesis_revision_ref", ["hypothesis_revision"]),
        ref("invariant_revision_ref", ["invariant_revision"]),
        ref("coverage_obligation_refs", ["coverage_obligation"], "0..65536"),
        ref("subject_baseline_ref", ["source_generation"]),
        ref("dependency_set_ref", [], "1", "HISTORY_CONTEXT_BINDING"),
        ref("fault_ref", ["fault_spec"], "0..1"),
    ],
)
supplement(
    "execution_descriptor",
    [
        ref("experiment_revision_ref", ["experiment_spec"]),
        ref("subject_baseline_ref", ["source_generation"]),
        ref("environment_ref", ["environment_record"]),
        ref("dependency_set_ref", [], "1", "HISTORY_CONTEXT_BINDING"),
        ref("execution_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
    ],
)
supplement(
    "environment_record",
    [ref("dependency_set_ref", [], "1", "HISTORY_CONTEXT_BINDING")],
)
supplement(
    "execution_result",
    [
        ref("started_observation_ref", ["observation"]),
        ref("finished_observation_ref", ["observation"]),
        ref("raw_observation_refs", ["observation"], "0..65536"),
        ref("control_result_refs", ["execution_result"], "0..65536"),
        ref("reset_verification_ref", ["observation"], "0..1"),
    ],
)
supplement(
    "fault_run_record",
    [
        ref("fault_revision_ref", ["fault_spec"]),
        ref("activation_evidence_refs", ["observation"], "1..65536"),
        ref("cleanup_result_ref", ["cleanup_result"]),
    ],
)
supplement(
    "corpus_manifest",
    [
        ref("consumer_stage_run_ref", ["stage_run"]),
        ref("source_generation_ref", ["source_generation"]),
        ref("member_refs", ["corpus_member_candidate"], "0..65536", "CONTENT_OR_PRIOR"),
        ref(
            "member_admission_assessment_refs",
            ["corpus_member_admission_assessment"],
            "0..65536",
            "CONTENT_OR_PRIOR",
        ),
        ref("basis_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
    ],
)
supplement(
    "corpus_member_admission_assessment",
    [
        ref("member_candidate_ref", ["corpus_member_candidate"]),
        ref("consumer_stage_run_ref", ["stage_run"]),
        ref(
            "exposure_or_knowledge_assessment_refs",
            ["isolation_qualification", "contamination_assessment", "knowledge_state"],
            "0..65536",
        ),
        ref(
            "additional_admission_evidence_refs",
            ["bootstrap_admission_decision", "evidence_qualification_assessment"],
            "0..65536",
        ),
        ref("input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
    ],
)
supplement(
    "model_fidelity_assessment",
    [
        ref("model_revision_ref", ["state_model"]),
        ref("source_generation_ref", ["source_generation"]),
        ref(
            "implementation_anchor_refs",
            ["surface_record", "invariant_revision"],
            "1..65536",
        ),
        ref(
            "execution_conformance_evidence_refs",
            ["evidence_qualification_assessment"],
            "1..65536",
        ),
        ref("assessment_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
    ],
)
supplement(
    "negative_evidence_record",
    [
        ref(
            "coverage_obligation_qualification_ref",
            ["coverage_obligation_qualification"],
        ),
        ref("execution_refs", ["execution_result"], "0..65536"),
        ref(
            "observation_qualification_refs",
            ["evidence_qualification_assessment"],
            "0..65536",
        ),
    ],
)
supplement(
    "sound_claim",
    [
        ref("claim_revision_ref", ["finding_claim_revision"]),
        ref("required_obligation_refs", ["coverage_obligation"], "1..65536"),
        ref(
            "current_qualified_support_refs",
            ["evidence_qualification_assessment"],
            "1..65536",
        ),
    ],
)
supplement(
    "source_drift_record",
    [
        ref("old_source_generation_ref", ["source_generation"]),
        ref("new_source_generation_ref", ["source_generation"]),
    ],
)
supplement(
    "source_drift_impact_assessment",
    [
        ref("source_drift_record_ref", ["source_drift_record"]),
        ref(
            "affected_qualification_refs",
            ["evidence_qualification_assessment", "evidence_applicability_assessment"],
            "0..65536",
        ),
    ],
)
supplement(
    "compatibility_fixture_assessment",
    [
        ref("fixture_raw_ref", [], "1", "CONTENT_OBJECT"),
        ref(
            "expectation_basis_ref",
            [
                "clean_control_assessment",
                "defect_unit",
                "evidence_qualification_assessment",
            ],
        ),
        ref("intentional_hardening_exception_ref", ["approval_decision"], "0..1"),
        ref("assessment_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
    ],
)
supplement(
    "compatibility_gate_result",
    [
        ref(
            "fixture_assessment_refs", ["compatibility_fixture_assessment"], "1..65536"
        ),
        ref("compatibility_corpus_ref", ["corpus_manifest"]),
        ref("assessment_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
    ],
)
supplement(
    "legacy_observation_mapping_assessment",
    [
        ref("legacy_ref", ["legacy_raw_ref"]),
        ref(
            "legacy_observation_refs",
            ["legacy_observation_semantic_equivalence_assessment"],
            "0..65536",
        ),
        ref("current_obligation_revision_refs", ["coverage_obligation"], "0..65536"),
        ref("current_claim_refs", ["finding_claim_revision"], "0..65536"),
        ref("assessment_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
    ],
)
supplement(
    "legacy_observation_semantic_equivalence_assessment",
    [
        ref("legacy_ref", ["legacy_raw_ref"]),
        ref("target_source_generation_ref", ["source_generation"]),
        ref(
            "candidate_current_claim_or_obligation_refs",
            ["finding_claim_revision", "coverage_obligation"],
            "0..65536",
        ),
        ref("assessment_input_history_cut", ["history_cut"], "1", "HISTORY_INPUT"),
    ],
)
supplement(
    "final_technical_report",
    [
        ref("final_assurance_case_ref", ["final_assurance_case"]),
        ref("stop_evaluation_ref", ["stop_evaluation"]),
        ref("campaign_conclusion_ref", ["campaign_conclusion"]),
        ref("release_qualification_ref", ["release_qualification"], "0..1"),
    ],
)
supplement(
    "snapshot_export_record",
    [
        ref(
            "projection_input_refs",
            [
                "inventory_revision",
                "coverage_obligation",
                "coverage_obligation_qualification",
                "finding_claim_revision",
                "finding_adjudication_decision",
                "residual_risk",
            ],
            "0..65536",
        )
    ],
)
supplement(
    "report_export_receipt", [ref("report_artifact_ref", [], "1", "CONTENT_OBJECT")]
)
supplement(
    "tool_execution_record",
    [
        ref("environment_ref", ["environment_record"]),
        ref("input_refs", ["experiment_spec", "source_generation"], "0..65536"),
    ],
)
supplement(
    "build_manifest",
    [ref("schema_set_ref", ["schema_registry/2"], "1", "PINNED_INSTALLATION_REF")],
)
supplement(
    "standalone_payload_manifest",
    [
        ref(
            "build_input_manifest_ref",
            ["build_manifest"],
            "1",
            "PINNED_INSTALLATION_REF",
        )
    ],
)
supplement(
    "history_anchor_receipt",
    [
        ref("campaign_ref", ["campaign_genesis", "successor_campaign_genesis"]),
        ref("anchor_observation_ref", ["observation"]),
    ],
)
supplement(
    "transition_authorization_proposal",
    [
        ref("stage_run_ref", ["stage_run"]),
        ref("lane_run_ref", ["lane_run"], "0..1"),
        ref("attempt_ref", ["attempt"]),
        ref(
            "prior_checkpoint_or_handoff_ref",
            ["checkpoint", "handoff_validation_result"],
        ),
        ref("gate_decision_ref", ["gate_decision"], "1", "CONTENT_OR_PRIOR"),
    ],
)

section_map = {
    "approval_decision": 157,
    "artifact_contract_registry": 187,
    "assignment_manifest": 14,
    "assignment_package_binding": 192,
    "attempt": 14,
    "bdb_audit_lane_result": 192,
    "blind_origin_eligibility_assessment": 57,
    "bootstrap_admission_decision": 91,
    "build_manifest": 123,
    "bundle_manifest": 84,
    "campaign_conclusion": 80,
    "campaign_genesis": 9,
    "candidate_assurance_case": 80,
    "challenger_assignment": 80,
    "challenger_result": 80,
    "checkpoint": 17,
    "cleanup_result": 158,
    "command_envelope": 15,
    "command_receipt": 15,
    "commit_body": 15,
    "contamination_assessment": 22,
    "contradiction_resolution_decision": 60,
    "contradiction_revision": 60,
    "corpus_manifest": 24,
    "corpus_member_admission_assessment": 26,
    "coverage_obligation": 34,
    "coverage_obligation_key": 34,
    "coverage_obligation_qualification": 34,
    "delivery_spec": 13,
    "dependency_independence_assessment": 46,
    "discovery_record": 57,
    "environment_record": 133,
    "evidence_applicability_assessment": 47,
    "evidence_invalidation": 92,
    "evidence_qualification_assessment": 46,
    "execution_descriptor": 43,
    "execution_result": 43,
    "executor_spec": 12,
    "experiment_spec": 41,
    "fault_run_record": 45,
    "final_assurance_case": 80,
    "final_technical_report": 81,
    "finding_adjudication_decision": 62,
    "finding_axis_assessment": 52,
    "finding_claim_revision": 50,
    "grant_body": 14,
    "history_anchor_receipt": 9,
    "history_cut": 15,
    "hypothesis_revision": 39,
    "input_disposition_record": 28,
    "installation_bootstrap_profile": 14,
    "invariant_revision": 31,
    "inventory_revision": 28,
    "isolation_baseline_profile": 22,
    "isolation_qualification": 22,
    "knowledge_state": 23,
    "lane_completion": 177,
    "lane_result_admission_evidence": 192,
    "lane_run": 14,
    "lane_spec": 11,
    "legacy_exposure_reconstruction_assessment": 91,
    "legacy_mechanical_validation_assessment": 91,
    "legacy_observation_mapping_assessment": 127,
    "legacy_observation_semantic_equivalence_assessment": 91,
    "legacy_raw_ref": 90,
    "lineage_admission_assessment": 91,
    "materiality_assessment": 34,
    "model_fidelity_assessment": 71,
    "negative_evidence_record": 148,
    "obligation_applicability_decision": 34,
    "observation": 46,
    "policy_revision": 184,
    "potential_exposure_record": 22,
    "projection_policy": 27,
    "release_qualification": 80,
    "report_export_receipt": 81,
    "root_cause_revision": 58,
    "run_manifest": 14,
    "schema_registry": 192,
    "scope_state_record": 28,
    "snapshot": 105,
    "snapshot_export_record": 20,
    "sound_claim": 147,
    "source_drift_impact_assessment": 132,
    "source_drift_record": 132,
    "source_generation": 8,
    "source_identity": 8,
    "source_manifest": 8,
    "source_reconciliation_assessment": 91,
    "spec_revision": 184,
    "stage_completion": 176,
    "stage_run": 14,
    "stage_spec": 10,
    "standalone_payload_manifest": 124,
    "stop_evaluation": 76,
    "stop_input": 76,
    "successor_campaign_genesis": 14,
    "successor_campaign_selection_decision": 14,
    "surface_collector_record": 30,
    "surface_key": 8,
    "surface_record": 8,
    "tool_execution_record": 134,
    "transition_authorization_proposal": 88,
    "trust_profile": 9,
    "trusted_predecessor_selection_decision": 91,
    "validation_result": 108,
    "view_manifest": 27,
    "artifact_hash_manifest": 83,
    "compatibility_fixture_assessment": 126,
    "compatibility_gate_result": 126,
}

# Existing seeds retained, plus mandatory lifecycle/recovery/report method roots.
seeds = {
    x["kind"] + "/" + str(x["version"]): "; ".join(x["why_reachable"])
    for x in old["reachable_kinds"]
}
for key, why in {
    "corpus_manifest/1": "E2/E3 controlled predecessor/holdout membership (§24–26)",
    "model_fidelity_assessment/1": "E4 mandatory model→implementation conformance (§115)",
    "experiment_spec/1": "Fault/CAS/crash, mutation/oracle and endurance qualification intent (§41/§116)",
    "snapshot_export_record/1": "Recovery/reproducibility; no snapshot-as-head (§20/§105)",
    "history_anchor_receipt/1": "Recovery under declared optional externally pinned branch (§9.2); no fabricated freshness",
    "transition_authorization_proposal/1": "Checkpoint resume guarded transition (§88)",
    "successor_campaign_selection_decision/1": "Post-finalization material drift and conflicting successor branch (§14.5)",
    "final_technical_report/1": "Mandatory final reporting (§81)",
    "report_export_receipt/1": "Exact export raw binding (§81)",
    "bundle_manifest/1": "Final export membership (§84/§117)",
    "artifact_hash_manifest/1": "Final raw integrity (§83/§117)",
    "standalone_payload_manifest/1": "Mandatory standalone artifact (§124)",
    "legacy_observation_mapping_assessment/1": "Native/legacy migration qualification branch (§127)",
    "sound_claim/1": "SOUND current support invalidation consumer (§147/§92)",
    "compatibility_fixture_assessment/1": "N8 exact historical readers and release compatibility (§126)",
    "compatibility_gate_result/1": "N11 release compatibility decision (§126)",
    "blind_origin_eligibility_assessment/1": "Required blind provenance when claiming blind origin (§57); positive/failure branch",
    "coverage_obligation_key/1": "Exact ObjectDigest identity prerequisite for every CoverageObligation (§34)",
    "isolation_baseline_profile/1": "Exact baseline channel context for isolation qualification (§22)",
    "run_manifest/1": "Pinned run reporting/materialization (§14), never FSM authority",
    "validation_result/1": "Final consistency/handoff/export validation (§108/§117/§181)",
    "finding_defect_match_assessment/1": "Mandatory E5A auditor calibration exact claim-to-unit support (§149)",
    "holdout_exposure_assessment/1": "E3/E5 holdout non-reuse and calibration leakage checks (§149)",
}.items():
    seeds[key] = why

wrapper_fields = {
    ("command_envelope", "command_payload_ref"),
    ("commit_body", "immutable_object_refs"),
    ("command_receipt", "result_object_refs"),
    ("checkpoint", "sealed_output_refs"),
    ("lane_completion", "required_output_refs"),
    ("stage_completion", "required_output_refs"),
    ("stage_completion", "unresolved_material_refs"),
}
queue = deque(sorted(seeds))
visited = set()
edges = []
unresolved = []
external = []
logs = []


def resolve(key, f):
    if "allowed_keys" in f:
        return f["allowed_keys"]
    kind = key.split("/")[0]
    if (kind, f["field"]) in overrides:
        return overrides[kind, f["field"]]
    if (kind, f["field"]) in wrapper_fields:
        return []  # concrete finite output set finalized after domain closure
    result = []
    for target in f.get("allowed", []):
        if target == "registered_immutable_object":
            selected = overrides.get((kind, f["field"]))
            if selected is None:
                unresolved.append({"key": key, "field": f["field"], "target": target})
            else:
                result += selected
        elif target in classes:
            result += classes[target]
        elif target in terminal:
            external.append(
                {"from": key, **f, "target": target, "representation": terminal[target]}
            )
        else:
            versions = f.get("allowed_versions") or (
                ["2"]
                if target
                in [
                    "schema_registry",
                    "lane_result_admission_evidence",
                    "bdb_audit_lane_result",
                ]
                else ["1"]
            )
            for version in versions:
                t = target + "/" + str(version)
                if t not in rows and t not in proposals:
                    unresolved.append({"key": key, "field": f["field"], "target": t})
                else:
                    result.append(t)
    return sorted(set(result))


while queue:
    key = queue.popleft()
    if key in visited:
        continue
    visited.add(key)
    row = proposals.get(key, rows.get(key))
    if row is None:
        unresolved.append({"key": key, "issue": "No semantic contract"})
        continue
    refs = row.get("material_refs", []) + supplements.get(key, [])
    discovered = []
    for f in refs:
        for target in resolve(key, f):
            edge = {
                "from": key,
                "to": target,
                "field": f["field"],
                "cardinality": f.get("cardinality", "1"),
                "ref_class": f.get("ref_class"),
                "source": "HYPOTHETICAL_COMPLETE_CONTRACT"
                if key in proposals or f in supplements.get(key, [])
                else "QUALIFIED_REGISTRY_WITH_PROPOSED_FINITE_TARGET_MAPPING",
            }
            edges.append(edge)
            if target not in visited:
                queue.append(target)
                discovered.append(target)
    logs.append(
        {
            "expanded": key,
            "new_targets": sorted(set(discovered)),
            "queue_after": list(queue),
        }
    )

assert not unresolved, unresolved
assert set(proposals) <= visited, "Proposed unrelated kind"
for kind, field in sorted(wrapper_fields):
    key = kind + "/1"
    if key in visited:
        for target in sorted(
            visited
            - {
                "commit_body/1",
                "command_receipt/1",
                "command_envelope/1",
                "history_cut/1",
            }
        ):
            # Storage can carry only active finite contract closure. Completion
            # further restricts outputs to exact StageSpec/LaneSpec slots.
            edges.append(
                {
                    "from": key,
                    "to": target,
                    "field": field,
                    "ref_class": next(
                        f["ref_class"]
                        for f in rows[key]["material_refs"]
                        if f["field"] == field
                    ),
                    "cardinality": "EXACT_REGISTERED_FIELD_CARDINALITY",
                    "source": "FINITE_ACTIVE_CLOSURE; not authority to bypass domain/FSM/producer predicates",
                }
            )

profiles = []
for p in (BASE / "profiles").glob("*.json"):
    v = read(p)
    profiles.append(
        {
            "profile_file": str(p.relative_to(ROOT)),
            "raw_digest": digest(p),
            "semantic_definition": v,
            "status": "QUALIFIED_PREDECESSOR_EXACT_BYTES_RETAINED_AS_EVIDENCE; successor pins must be regenerated",
        }
    )
profile_designs = {
    "FULL_PATH_SEMANTIC_V1": "Offline L1 transport/resource, L2 raw integrity, L3 closed exact schema, L4 finite typed refs/history, L5 producer/source/FSM, L6 epistemic/applicability/isolation, L7 exhaustive obligations/finalization. All are conjunctions; missing proof rejects with no canonical mutation.",
    "PUBLIC_CONCLUSION_RENDER_V1": "Canonical UTF-8 JSON with fields campaign_ref,source_generation_ref,conclusion_ref,stop_evaluation_ref,scope_inventory_ref nullable,termination_state,assurance_level,continuation_decision,stop_release_assessment,residual_risks,limited_basis_refs,bounded_statement. Risks include exact ref, description, reason_unresolved, disposition, materiality; redact only sensitive basis, never presence/status. No arbitrary narrative, release authorization, generated PASS alias or future FinalCase ref. Text rendering, if exported, is deterministic static-label rendering of this JSON.",
    "CLAIM_SET_CLOSURE_V1": "C(c,inventory) = all exact unsuperseded claim-lineage tips accepted in same campaign/source, intersecting accepted inventory surface/scope or with unresolved applicability. Retain rejected/unknown claims; assess separately. Fork/conflicting tip blocks selection. Candidate set equals C and its current adjudication map at represented cut; omit missing adjudication only by marking unresolved, which blocks required finalization.",
    "DEPENDENCY_CLOSURE_V1": "Full accepted observation dependency closure at represented cut, with exact tagged TypedRef/RawRef/ExternalProfileRef nodes, canonical sorting and explicit common-cause assumptions; no dependency assertion from missing capture.",
    "EFFORT_PROFILE_V1": "Closed versioned policy with required stages, method-family identifiers, rounds/budget requirements per stage, exact counting predicate revisions and required metric witness classes. Values are explicit positive bounded campaign-policy inputs; absence => INSUFFICIENT_DATA. Source values derive pinned E0; no schema/backend default can choose values. EffortResults closure deterministically enumerates accepted stage/execution/metric facts, no saturation-as-completeness.",
    "FULL_FINALIZATION_PROFILE_V1": "Exact risk equality Candidate/STOP/conclusion/public/final for represented applicable cuts; all claims/obligations/adjudications/contradictions/evidence closed. Material drift requires fresh candidate and both challengers; conclude/final/release guards retain §76/§80 precedence. Separate authorized approval never turns waived mandatory obligation into satisfied.",
    "CHANNEL_CAPTURE_PROFILE_V1": "snapshot/1 is exact channel inventory projection of prior ExecutorSpec/DeliverySpec/isolation baseline and capture observations, with all ten baseline channels, witness/UNKNOWN per channel; accepted raw observations provide capture facts. Snapshots cannot assert enforcement by themselves.",
    "REPORT_EXPORT_PROFILE_V1": "Final technical report after FinalCase; exact accepted closure and optional prior ReleaseQualification, deterministic disclosure/no-upgrade. report_export_receipt binds exact RawRef/as_of_head/profile/producer outside raw preimage; final bundle includes exact typed refs and RawDigest membership, excludes own hash manifest self entry.",
    "INSTALLATION_FULL_PATH_PROFILE_V1": "New exact revision of installation_bootstrap_profile/1 retaining eight pins plus externally approved qualified full-path schema and profile closure. Namespace authorized before bootstrap, never runtime-generated from cwd. Finite active set includes all graph nodes, excludes historical schema_registry/1 and external governance documents from campaign writes.",
    "MODEL_ARTIFACT_V1": "Closed finite model JSON: variable definitions and finite domains, transitions with typed source anchors, initial/forbidden predicates, abstraction assumptions,bounds,omitted states,fairness/time assumptions; exact raw checker/grammar profile. Mapping to prior source anchors validated independently; no implementation assurance from model proof alone.",
    "GATE_ELIGIBILITY_PROFILE_V1": "GateDecision is pure policy/FSM/checkpoint/knowledge/positive-view eligibility on exact prior head; ALLOW only all conditions established, DENY for violated condition, UNKNOWN for unverified mandatory input. It grants no independent human approval or future authority.",
    "CALIBRATION_GROUND_TRUTH_PROFILE_V1": "Exact retained corpus issuer evidence authorized before auditor execution through installation/policy trust boundary. Defect and benign units have complete known activation/scope/provenance; all units count in denominators; unknown units remain unqualified. No source of truth derived from tested auditor output or majority.",
    "FULL_PATH_CONTEXT_PARAMETERS_V1": "Closed exact prior pin for named stage/lane/executor/delivery/collector/method/confirmation/matching/novelty/relationship/assessor/model/fault/release/effort/recovery contexts. Per-purpose entries carry finite input target set, deterministic predicate revision and bounds, required witness classes, enum domains, authorized issuer/scope and unknown handling. Campaign-selected numeric effort/method/resource values are data constrained by approved policy, not authority to rewrite predicates. Missing required entry forbids that path; no latest/generated equivalent or profile overlay. Runtime code/harness/fixture revisions are retained RawRefs, not self-issued trust identities.",
    "EXECUTION_DEPENDENCY_PLAN_V1": "Exact pinned closed dependency list for ExperimentSpec/Environment/ExecutionDescriptor before execution: source/module RawRefs, harness/oracle/runner ExternalProfileRefs, fixture RawRefs and versioned resource bounds. It is planned context, not observed dependency facts or independence. Observed EvidenceDependencyGraph is constructed AFTER observations; mandatory pre-execution graph refs would create a cycle and are forbidden.",
    "RECOVERY_REFERENCE_PROFILE_V1": "Canonical history + immutable raw vault reconstruct selectors. Atomic accepted closure/commit/head/receipt or none; CAS full expected head; external anchor only for declared profile; scratch/cache/projections not authority. Terminal-vs-delivery check serialized before external export.",
}
for name, spec in profile_designs.items():
    profiles.append(
        {
            "profile_id": name,
            "status": "PROPOSED_SEMANTIC_DEFINITION_NO_BYTES_NO_RAWDIGEST",
            "definition": spec,
            "identity_rule": "ExternalProfileRef(profile_id, RawDigest of future frozen bytes); exact pin from qualified successor context; no local overlay/latest/fallback",
        }
    )
for name, spec in raw_designs.items():
    profiles.append(
        {
            "profile_id": name,
            **spec,
            "status": "PROPOSED_RAW_CONTRACT_NOT_CANONICAL_KIND",
            "identity_rule": "RawRef exact bytes with ExternalProfileRef; references independently parsed under pinned closed contract; caller assertions never authority",
        }
    )

# Audit reference field names in complete normative body blocks, including
# schema-deferred rows. Each has a finite actual representation, not just a token.
field_catalog = {}
raw_fields = set(
    "abstraction_mapping_refs build_environment_ref embedded_resource_refs fixture_raw_ref legacy_observation_raw_ref output_raw_refs snapshot_artifact_ref view_artifact_ref ordered_input_refs".split()
)
event_fields = set(
    "discovery_event_ref first_relevant_reveal_event_ref exposure_ref".split()
)
authority_fields = set(
    "authorized_actor_or_capability_profile_ref coordinator_authority_ref governance_actor_ref issuer_or_channel_ref external_storage_or_witness_ref producer_ref".split()
)
concrete_fields = {
    "affected_evidence_qualification_refs": keys(
        "evidence_qualification_assessment", "evidence_applicability_assessment"
    ),
    "affected_obligation_qualification_refs": keys("coverage_obligation_qualification"),
    "affected_stage_lane_attempt_refs": keys("stage_run", "lane_run", "attempt"),
    "application_source_generation_ref": keys("build_manifest"),
    "assigned_input_manifest_ref": keys("source_manifest"),
    "assignment_manifest_ref": keys("assignment_manifest"),
    "compatibility_corpus_ref": keys("corpus_manifest"),
    "confirmation_evidence_refs": keys("evidence_qualification_assessment"),
    "corpus_match_assessment_ref": keys("discovery_corpus_match_assessment"),
    "corpus_snapshot_ref": keys("corpus_manifest"),
    "discovery_ref": keys("discovery_record"),
    "drift_observation_refs": keys("observation"),
    "emitted_surface_refs": keys("surface_record"),
    "expectation_basis_ref": keys(
        "clean_control_assessment", "defect_unit", "evidence_qualification_assessment"
    ),
    "fixture_assessment_refs": keys("compatibility_fixture_assessment"),
    "intentional_hardening_exception_ref": keys("approval_decision"),
    "matched_prior_claim_refs": keys("finding_claim_revision"),
    "negative_control_refs": keys("experiment_spec", "execution_result"),
    "oracle_challenge_refs": keys(
        "experiment_spec", "execution_result", "evidence_qualification_assessment"
    ),
    "predecessor_stage_or_claim_refs": keys(
        "stage_completion", "finding_claim_revision"
    ),
    "resolved_blocker_refs": classes["limited_conclusion_basis_ref"],
    "schema_registry_ref": keys("schema_registry/2"),
    "source_corpus_snapshot_ref": keys("corpus_manifest"),
    "stage_lane_policy_refs": keys("stage_spec", "lane_spec", "policy_revision"),
    "verification_refs": keys("validation_result", "compatibility_gate_result"),
}
ignored = {"material_refs"}
global_fields = {}
for key in visited:
    for f in (proposals.get(key, rows.get(key)) or {}).get(
        "material_refs", []
    ) + supplements.get(key, []):
        global_fields.setdefault(f["field"], []).append({"owner": key, "contract": f})
profile_fields = set(
    "anchor_profile_ref browser_profile_ref budget_effort_profile_ref builder_recipe_ref bundle_contract_ref collector_profile_ref command_spec_ref completion_predicate_ref confirmation_policy_ref consumer_knowledge_policy_ref coverage_obligation_policy_ref deterministic_settings_ref drift_policy_ref executor_tool_ref exploration_policy_ref external_anchor_profile_ref external_service_profile_refs filesystem_boundary_ref fixture_contract_ref idempotency_policy_ref manifest_entry_profile_ref mapping_policy_ref match_policy_ref network_boundary_ref novelty_policy_ref os_profile_ref path_profile_ref projection_policy_ref protocol_policy_ref recovery_pin_policy_ref relationship_policy_ref retry_policy_ref runner_profile_ref runtime_profile_ref target_execution_variant_ref target_variant_ref tool_boundary_ref tool_profile_ref toolchain_runtime_profile_ref transition_policy_ref capability_profile_ref".split()
)
profile_fields.add("contract_ref")
concrete_fields["target_ref"] = sorted(visited)
concrete_fields["normalized_identity_body_ref"] = keys("source_identity")
concrete_fields["build_input_manifest_ref"] = keys("build_manifest")
special_fields = {
    "schema_ref": "Exact semantic schema key plus bound RawDigest(schema bytes); never latest installed schema",
    "schema_raw_ref": "Exact executable schema RawRef",
    "accepted_commit_ref": "Prior accepted CommitHash; or POST_ACCEPTANCE_SIDECAR receipt only",
    "prev_history_ref": "Exact verified parent head or EMPTY_HISTORY only initialization",
    "implementation_mapping_ref": "Exact retained model-mapping RawRef; current model/source checked",
}
for node_key in sorted(visited & rows.keys()):
    section = sections.get(section_map.get(node_key.split("/")[0]), "")
    row_refs = rows[node_key]["material_refs"] + supplements.get(node_key, [])
    byfield = {f["field"]: f for f in row_refs}
    for block in re.findall(r"```text\n(.*?)```", section, re.S):
        for field in sorted(
            set(re.findall(r"\b[a-z][a-z0-9_]*(?:_ref|_refs)\b", block))
        ):
            if field in ignored:
                continue
            token = (node_key, field)
            if field in byfield:
                f = byfield[field]
                representation = {
                    "allowed_keys": resolve(node_key, f),
                    "ref_class": f["ref_class"],
                    "cardinality": f.get("cardinality"),
                    "basis": "qualified material-ref row or explicit proposed completion",
                }
                if not representation["allowed_keys"]:
                    representation["external_representation"] = (
                        "RawRef/ExternalProfileRef/history/authority per field context; see owner package"
                    )
            elif field in concrete_fields:
                representation = {
                    "allowed_keys": concrete_fields[field],
                    "ref_class": "PRIOR_ACCEPTED_ONLY",
                    "cardinality": "0..65536 if plural; 1 otherwise; optional only where normative body explicitly says optional",
                    "basis": "proposed exact finite representation for schema-deferred normative body field",
                }
            elif field in raw_fields:
                representation = {
                    "allowed_keys": [],
                    "external_representation": "Exact retained RawRef; ordered_input_refs is finite union of retained RawRef and installation-pinned TypedRef build inputs in declared order",
                    "ref_class": "CONTENT_OBJECT",
                    "cardinality": "per normative body; closed finite array max 65536",
                }
            elif field in event_fields:
                representation = {
                    "allowed_keys": [],
                    "external_representation": terminal["accepted_event_ref"],
                    "ref_class": "PRIOR_ACCEPTED_ONLY",
                    "cardinality": "per normative body",
                }
            elif field in authority_fields:
                representation = {
                    "allowed_keys": [],
                    "external_representation": "Exact prior installation/trust-authorized principal, scope and authority revision; capability remains outside canonical body",
                    "ref_class": "AUTHORIZED_ACTOR_REF",
                    "cardinality": "per normative body",
                }
            elif field in global_fields:
                representation = {
                    "defined_by_exact_owner_contracts": global_fields[field],
                    "note": "This complete source section contains several bodies. Field belongs to listed body/owner, not every node citing section; no generic name-based authority.",
                    "allowed_keys": [],
                }
            elif field in special_fields:
                representation = {
                    "allowed_keys": [],
                    "external_representation": special_fields[field],
                    "ref_class": "EXACT_OWNER_FIELD_RULE",
                    "cardinality": "per normative body",
                }
            elif field in profile_fields:
                representation = {
                    "allowed_keys": [],
                    "external_representation": "ExternalProfileRef to exact purpose entry of FULL_PATH_CONTEXT_PARAMETERS_V1; entry meaning fixed by named normative field, not arbitrary profile alias",
                    "ref_class": "HISTORY_CONTEXT_BINDING",
                    "cardinality": "per normative body; nullable only explicit optional",
                }
            else:
                raise AssertionError(
                    ("UNRESOLVED_NORMATIVE_REF_FIELD", node_key, field)
                )
            field_catalog[node_key + "." + field] = representation

assert all(t in visited for f in field_catalog.values() for t in f["allowed_keys"])

# Concrete owner decisions for rows whose narrative gives meaning but not a
# closed body. Other bodies use the exact field/enum lists in their pinned full
# Data section; do not let schema generation invent these missing bodies.
body_completions = {
    "observation/1": {
        "body": [
            "observation_id:ID",
            "execution_descriptor_ref:TypedRef",
            "observation_raw_ref:RawRef",
            "capture_profile_ref:ExternalProfileRef",
            "observation_kind:START|FINISH|MEASUREMENT|ACTIVATION|CLEANUP|RESET|CHANNEL_CAPTURE|EXTERNAL_WITNESS",
        ],
        "predicate": "Descriptor prior accepted before controlled capture; exact raw/profile independently read. Kind describes observation category, not PASS or truth. Times only informational in retained raw; no future ExecutionResult. External witness capture also has declared descriptor/runner context.",
    },
    "cleanup_result/1": {
        "body": [
            "cleanup_result_id:ID",
            "execution_descriptor_ref:TypedRef",
            "cleanup_observation_refs:TypedRef[]",
            "cleanup_spec_ref:ExternalProfileRef",
            "result:VERIFIED|FAILED|UNKNOWN|BLOCKED",
        ],
        "predicate": "Prior descriptor/capture observations and exact planned cleanup predicate; VERIFIED requires all required cleanup checks with retained evidence. Does not establish future ExecutionResult.",
    },
    "snapshot/1": {
        "body": [
            "snapshot_id:ID",
            "as_of_head:AcceptedHead",
            "projection_profile_ref:ExternalProfileRef",
            "projection_code_ref:RawRef",
            "projection_input_refs:TypedRef[]",
            "projection_payload:ClosedPurposePayload",
        ],
        "predicate": "Exact accepted cut and deterministic independently replayed payload of named STOP_INPUT/COVERAGE_SUMMARY/CHANNEL_INVENTORY/RUN_STATE purpose; stale mismatch rejects; profile defines required fields and derives all summaries from exact refs, never alternative head.",
    },
    "validation_result/1": {
        "body": [
            "validation_id:ID",
            "target_ref:TargetRef",
            "contract_ref:ExternalProfileRef",
            "validation_layers:LayerResult[]",
            "overall_status:PASS|FAIL|BLOCKED",
            "reason_codes:Code[]",
            "validator_profile_ref:ExternalProfileRef",
            "input_history_cut?:HistoryCut",
        ],
        "predicate": "TargetRef exact finite active typed key or retained RawRef; full applicable contract layers must PASS; cannot establish authenticity/truth outside checked predicates. Cut mandatory for history-dependent target; absent only installation/raw syntactic validation.",
    },
    "report_export_receipt/1": {
        "body": [
            "report_artifact_ref:RawRef",
            "report_as_of_head:AcceptedHead",
            "report_contract_ref:ExternalProfileRef",
            "producer_revision_ref:RawRef",
        ],
        "predicate": "External exact retained export metadata; raw bytes derived from accepted final chain. Receipt outside report raw preimage; it does not authorize campaign conclusion. Same raw/head/profile receipt retry is exact; substitution conflicts.",
    },
    "artifact_hash_manifest/1": {
        "body": [
            "hash_manifest_artifact_ref:RawRef",
            "bundle_manifest_ref:TypedRef",
            "export_as_of_head:AcceptedHead",
            "hash_manifest_profile_ref:ExternalProfileRef",
        ],
        "predicate": "Registered EXPORT family gets closed semantic descriptor pointing to actual ARTIFACT_HASHES.sha256 raw bytes; exact path/digest sorted raw list excludes itself, equality-checks full BundleManifest membership before semantic parsing. Descriptor ObjectDigest is distinct from raw list RawDigest; no new outcome authority. This descriptor interpretation is explicit proposed successor clarification, not existing bytes rewritten.",
    },
    "standalone_payload_manifest/1": {
        "body": [
            "payload_manifest_id:ID",
            "build_input_manifest_ref:TypedRef",
            "embedded_components:ComponentEntry[]",
            "runtime_profile_ref:ExternalProfileRef",
        ],
        "predicate": "ComponentEntry closed {member_path,raw_ref,component_role}; role CODE|SCHEMA|SPEC|PROMPT|FIXTURE; exact unique sorted paths and full declared build-input membership; no final distributed artifact hash in embedded body.",
    },
    "isolation_baseline_profile/1": {
        "body": [
            "isolation_baseline_profile_id:ID",
            "channels:ChannelRule[]",
            "guarantee_boundary:bounded text",
        ],
        "predicate": "ChannelRule closed {channel,required_control,witness,unknown_handling}; channel domain is exact ten-channel Registry baseline, unknown_handling=UNKNOWN_NOT_ENFORCED; does not assert actual enforcement. Exact installation/profile pin precedes referring assessment.",
    },
}
for key, decision in body_completions.items():
    decision["status"] = "PROPOSED_EXPLICIT_BODY_COMPLETION_NOT_AUTHORITY"
    decision["identity_rule"] = (
        "Explicit ObjectDigest semantic descriptor/wrapper vs RawDigest retained raw; accepted/export authority limited by original role. No implicit raw-role identity conversion."
    )

snapshot_fields = [
    "accepted_head",
    "commit_count",
    "event_sequence",
    "immutable_object_count",
    "command_index",
    "receipt_index",
    "binding_selector",
    "result_slot_selector",
    "accepted_raw_references",
]
vectors = []
mandatory_vectors = {
    "CLAIM_SET_EXACT_ACCEPT": (
        "assurance_claim_set/1",
        "ACCEPT",
        "Complete independently derived set and exact cut",
    ),
    "CLAIM_SET_OMISSION_REJECT": (
        "assurance_claim_set/1",
        "REJECT",
        "Remove one rejected/unresolved applicable claim; recompute set",
    ),
    "CLAIM_SET_STALE_CUT_REJECT": (
        "assurance_claim_set/1",
        "REJECT",
        "Change accepted scope/claim basis before Candidate uses old set",
    ),
    "CLAIM_SET_DUPLICATE_REF_REJECT": (
        "assurance_claim_set/1",
        "REJECT",
        "Duplicate full exact claim ref",
    ),
    "CLAIM_SET_CROSS_CAMPAIGN_REJECT": (
        "assurance_claim_set/1",
        "REJECT",
        "Insert matching logical ID from another accepted campaign",
    ),
    "PUBLIC_CONCLUSION_EXACT_ACCEPT": (
        "public_conclusion_statement/1",
        "ACCEPT",
        "Exact renderer output for same prior conclusion and closure",
    ),
    "PUBLIC_CONCLUSION_WRONG_CONCLUSION_REJECT": (
        "public_conclusion_statement/1",
        "REJECT",
        "Valid bytes derived from another exact conclusion",
    ),
    "PUBLIC_CONCLUSION_ASSURANCE_UPGRADE_REJECT": (
        "public_conclusion_statement/1",
        "REJECT",
        "Replace BOUNDED/INSUFFICIENT with adequate assurance",
    ),
    "PUBLIC_CONCLUSION_RESIDUAL_RISK_OMISSION_REJECT": (
        "public_conclusion_statement/1",
        "REJECT",
        "Remove one material risk disclosure",
    ),
    "PUBLIC_CONCLUSION_LIMITED_AS_FULL_REJECT": (
        "public_conclusion_statement/1",
        "REJECT",
        "COMPLETED_LIMITED rendered as PASS/READY/full complete",
    ),
    "PUBLIC_CONCLUSION_STALE_CUT_REJECT": (
        "public_conclusion_statement/1",
        "REJECT",
        "Intervening audit basis change at statement acceptance",
    ),
    "RESIDUAL_RISK_EXACT_REVISION_ACCEPT": (
        "residual_risk/1",
        "ACCEPT",
        "Prior accepted exact subject/basis, explicit authorized revision",
    ),
    "RESIDUAL_RISK_FALSE_PASS_REJECT": (
        "residual_risk/1",
        "REJECT",
        "OPEN/UNKNOWN risk or waiver hides unsatisfied mandatory obligation at STOP",
    ),
    "RESIDUAL_RISK_UNAUTHORIZED_ACCEPTANCE_REJECT": (
        "residual_risk/1",
        "REJECT",
        "Self-accepted status or borrowed approval for different assessed tuple",
    ),
}
for name, (kind, outcome, trigger) in mandatory_vectors.items():
    vectors.append(
        {
            "id": name,
            "kind": kind,
            "trigger": trigger,
            "expected": outcome,
            "canonical_mutation": "NONE"
            if outcome == "REJECT"
            else "ONE_COMPLETE_ACCEPTED_OPERATION",
            "before_after_snapshot": snapshot_fields,
            "execution_status": "DESIGN_ONLY_NOT_EXECUTED",
        }
    )
for key in sorted(proposals):
    for suffix, trigger in [
        (
            "EXACT_ACCEPT",
            "Exact legal immutable body, complete independent derivation and current input cut",
        ),
        ("UNREGISTERED_REJECT", "Attempt acceptance without approved row"),
        (
            "SCHEMA_NOT_BOUND_REJECT",
            "Locally available schema without exact qualified binding",
        ),
        (
            "WRONG_SUBJECT_REJECT",
            "Alter exact subject/producer/source/profile relation",
        ),
        ("STALE_CUT_REJECT", "Alter expected parent or use materially stale basis"),
        ("MISSING_BASIS_REJECT", "Omit required retained witness/authority closure"),
        ("CROSS_CAMPAIGN_REJECT", "Reuse exact bytes with wrong campaign/source"),
        (
            "CONFLICT_REJECT",
            "Different body for same unique represented tuple; race by CAS",
        ),
    ]:
        vectors.append(
            {
                "id": key.split("/")[0].upper() + "_" + suffix,
                "kind": key,
                "trigger": trigger,
                "expected": "ACCEPT" if suffix == "EXACT_ACCEPT" else "REJECT",
                "canonical_mutation": "ONE_COMPLETE_ACCEPTED_OPERATION"
                if suffix == "EXACT_ACCEPT"
                else "NONE",
                "before_after_snapshot": snapshot_fields,
                "execution_status": "DESIGN_ONLY_NOT_EXECUTED",
            }
        )

delta_plan = [
    {
        "file": "BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md",
        "decision": "CHANGE REQUIRED",
        "reason": "21 new exact contracts; all proposed body/ref completions; role-vs-digest clarification; finite targets; public order and risk no-omission.",
    },
    {
        "file": "BDB_AUDIT_V2_ARCHITECTURE_SPEC_R5_4.md",
        "decision": "CHANGE REQUIRED",
        "reason": "Dependency intent/observed distinction; corpus/discovery/calibration complete DAG; Conclusion→PublicStatement→FinalCase order and independent derivation.",
    },
    {
        "file": "BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json",
        "decision": "CHANGE REQUIRED",
        "reason": "21 proposed rows, 110 exact active keys, target maps and explicit schema-deferred material refs; correct discovery_relation_refs mismatch; preserve role domains.",
    },
    {
        "file": "objects/schema_registry__2.json",
        "decision": "CHANGE REQUIRED",
        "reason": "131 exact required keys with future frozen executable raw refs; no guessed digest or runtime-generated authority.",
    },
    {
        "file": "SCHEMA_ARTIFACT_CATALOG_R5_4.json + schemas/",
        "decision": "CHANGE REQUIRED",
        "reason": "92 currently missing bindings; executable bytes generated after owner decision; regenerate any of existing 39 whose approved exact semantics change. 39 existing bindings are evidence only, not automatic successor reuse.",
    },
    {
        "file": "BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json",
        "decision": "CHANGE REQUIRED",
        "reason": "Materialize proposed positive/negative vectors only later; retain previous expected failure intent; add closure/discovery/calibration/gate cases.",
    },
    {
        "file": "BDB_AUDIT_V2_TEST_AND_SELF_AUDIT_PLAN_R5_4.md",
        "decision": "CHANGE REQUIRED",
        "reason": "Mandatory semantic closure audit, 131-key schema parity, no-omission/false-public-pass tests and full crash/CAS/restart/old-campaign runtime families.",
    },
    {
        "file": "BDB_AUDIT_V2_IMPLEMENTATION_ROADMAP_R5_4.md",
        "decision": "CHANGE REQUIRED",
        "reason": "Q1/Q2 prerequisites now full declared path; M42–M44 include all new contracts and no premature NF02 closure.",
    },
    {
        "file": "BDB_Audit_vNext_Szczegolowy_Plan_Rozwoju.md + successor execution plan",
        "decision": "CHANGE REQUIRED",
        "reason": "Separate owner approval→materialization→fresh Q1→Q2→N5–N11 gates and contract-to-runtime dependencies.",
    },
    {
        "file": "INSTALLATION_PIN_BUNDLE_R5_4.json + objects/installation_bootstrap_profile__1.json + profiles/bootstrap",
        "decision": "CHANGE REQUIRED",
        "reason": "New authorized installation revision, namespace and full-path exact pins. Preserve eight pins and first-history command/union-DAG semantics; no in-place upgrade.",
    },
    {
        "file": "profiles/finalization + profiles/report_export + proposed external profiles",
        "decision": "CHANGE REQUIRED",
        "reason": "Freeze all semantic profile definitions, renderer and validator/code dependency identity; raw method/model/calibration profiles as declared in graph.",
    },
    {
        "file": "successor manifest/governance/readback/self-audit tooling",
        "decision": "CHANGE REQUIRED",
        "reason": "Transitively inventory all future files/profiles/schemas; external authorized fresh qualification record and immutable provenance, no self-certifying candidate.",
    },
    {
        "file": "ADR-006_CANONICAL_SERIALIZATION_AND_IDENTITY_PROFILE.md",
        "decision": "NO CHANGE",
        "reason": "BDB-CJSON-1/RawDigest/ObjectDigest algorithms retained; role alone does not select digest domain. Clarification belongs in Data/Registry row contracts.",
    },
    {
        "file": "BDB_AUDIT_V1_TO_V2_MIGRATION_AND_COMPATIBILITY.md",
        "decision": "NO CHANGE",
        "reason": "Existing exact old readers/new-campaign-only rule retained; successor documentation links fresh contracts, no retroactive binding or in-place semantic upgrade.",
    },
    {
        "file": "README_BDB_AUDIT_V2_DOCUMENTATION_R5_4.md",
        "decision": "CHANGE REQUIRED",
        "reason": "New successor navigation and assurance status; all predecessor documents retained unchanged.",
    },
    {
        "file": "production runtime/tests",
        "decision": "NO CHANGE IN THIS TASK",
        "reason": "Implementation and execution postponed to authorized later milestones; graph proposals cannot authorize runtime writes.",
    },
]

nodes = []
for key in sorted(visited):
    kind, version = key.split("/")
    r = proposals.get(key, rows.get(key))
    sec = section_map.get(kind)
    nodes.append(
        {
            "key": key,
            "kind": kind,
            "version": version,
            "registered_in_r5_4_1": key in rows,
            "schema_key": "BDB_SCHEMA_REGISTRY::" + key,
            "currently_bound": key in bound,
            "semantic_status": "COMPLETE_DESIGN_PENDING_OWNER_APPROVAL"
            if key in proposals or key in supplements
            else "EXISTING_CONTRACT_WITH_PROPOSED_EXACT_TARGET_MAPPING",
            "qualified_registry_row": rows.get(key),
            "proposed_contract": proposals.get(key),
            "proposed_material_ref_completion": supplements.get(key, []),
            "normative_semantic_source": {
                "file": str(data_file.relative_to(ROOT)),
                "section": sec,
                "raw_digest": digest(data_file),
                "complete_section_text": sections.get(sec),
            }
            if sec
            else None,
            "reachability_witness": seeds.get(key)
            or next(
                (
                    e
                    for e in edges
                    if e["to"] == key
                    and e["source"]
                    != "FINITE_ACTIVE_CLOSURE; not authority to bypass domain/FSM/producer predicates"
                ),
                None,
            ),
        }
    )

counts = {
    "reachable_canonical_kinds": len(visited),
    "registered_in_r5_4_1": len(visited & rows.keys()),
    "new_proposed_canonical_kinds": len(visited & proposals.keys()),
    "currently_schema_bound": len(visited & bound),
    "missing_executable_bindings": len(visited - bound),
    "semantic_complete_design": len(visited),
    "semantic_incomplete_design": 0,
    "unresolved_abstract_ref_targets": 0,
    "unresolved_Class_C": 0,
    "unresolved_Class_D": 0,
}

graph = {
    "schema": "BDB_R5_4_2_SEMANTIC_CLOSURE_ANALYSIS/1",
    "authority": "DESIGN_ONLY_PENDING_OWNER_APPROVAL",
    "gate": "READY_FOR_OWNER_APPROVAL",
    "source": old["source"],
    "fresh_qualified_identity_readback": qualified_readback,
    "predecessor": old["predecessor"],
    "readback": {
        "candidate_entries": 120,
        "mismatches": 0,
        "preservation_pins_checked": len(preservation),
        "input_pins": input_pins,
    },
    "inventory": {
        "file": "RESIDUAL_RISK_NORMATIVE_USAGE_INVENTORY.json",
        "raw_digest": digest(OUT / "RESIDUAL_RISK_NORMATIVE_USAGE_INVENTORY.json"),
        "occurrences": 483,
        "reuse": "unchanged complete inventory",
    },
    "counts": counts,
    "fixed_point_reached": True,
    "queue": list(queue),
    "nodes": nodes,
    "edges": edges,
    "traversal_log": logs,
    "exact_target_classes": classes,
    "noncanonical_reference_representations": terminal,
    "resolved_external_edges": external,
    "field_target_overrides": [
        {"kind": k, "field": f, "targets": v} for (k, f), v in sorted(overrides.items())
    ],
    "external_profiles": profiles,
    "unresolved": unresolved,
    "excluded_registered_keys": sorted(rows.keys() - visited),
    "normative_body_reference_field_catalog": field_catalog,
    "schema_deferred_body_completion_decisions": body_completions,
    "vector_designs": vectors,
    "normative_delta_plan": delta_plan,
    "scope_boundary": "Mandatory runtime/finalization/recovery/report/release including declared failure/legacy/external-anchor branches. External governance records and schema_registry/1 are read-only predecessor evidence, not fresh campaign writes.",
    "preserved_old_edges": {
        "previous_diagnostic": old["previous_diagnostic"],
        "new_registry_edges": old["new_registry_edges"],
        "unexpanded_frontier": old["unexpanded_target_class_frontier"],
    },
    "candidate_materialized": False,
    "schemas_generated": 0,
    "runtime_modified": False,
    "qualification_performed": False,
    "remaining_work": [
        "owner semantic approval",
        "successor normative/machine materialization",
        "exact schema generation/binding",
        "fresh Q1",
        "Q2 runtime activation",
        "N5–N11 implementation and independent runtime qualification",
    ],
    "caveat": "Fixed point of the explicitly proposed contracts and finite approved-profile model, not approval, executable parity or runtime qualification. Future owner model changes require recomputing closure.",
}
dump(OUT / "R5_4_2_SEMANTIC_CLOSURE_GRAPH.json", graph)
reach = dict(
    old,
    gate="READY_FOR_OWNER_APPROVAL",
    analysis_status="FULL_HYPOTHETICAL_SEMANTIC_CLOSURE_PENDING_OWNER_APPROVAL",
    full_pass_predecessor_diagnostic=old,
    counts=counts,
    fixed_point_reached=True,
    remaining_queue=[],
    unexpanded_target_class_frontier=[],
    stop_frontier=[],
    semantically_incomplete_kinds=[],
    reachable_kinds=[
        {
            "kind": n["kind"],
            "version": n["version"],
            "semantic_status": n["semantic_status"],
            "current_binding_status": "BOUND" if n["currently_bound"] else "MISSING",
            "schema_ref": n["schema_key"],
        }
        for n in nodes
    ],
    schema_keys_required=[n["schema_key"] for n in nodes],
    bindings_missing_in_r5_4_1=[
        n["schema_key"] for n in nodes if not n["currently_bound"]
    ],
    unregistered_reachable_kinds_actual=sorted(proposals),
    unregistered_reachable_kinds=[],
    unregistered_list_context="Hypothetical proposal graph resolves missing kinds; qualified R5.4.1 Registry still lacks every proposed kind.",
    full_semantic_closure_graph="R5_4_2_SEMANTIC_CLOSURE_GRAPH.json",
)
dump(OUT / "R5_4_2_RUNTIME_SCHEMA_REACHABILITY.json", reach)
print(json.dumps(counts, indent=2))
print("EXCLUDED", sorted(rows.keys() - visited))
print("NEW", sorted(proposals))

banner = "**PROPOSED — NOT APPROVED — NOT NORMATIVE/RUNTIME AUTHORITY.** No R5.4.2 candidate, schema, Registry, Golden Vector or qualification record is produced. Q2 and N5–N11 remain NOT_STARTED. Date: 2026-10-06."
common_text = """
All new semantic bodies are closed (`additionalProperties=false` in future executable schemas). No unlisted authority field, capability secret, self-digest, future consumer, accepting head/event/receipt is permitted. TypedRef/RawRef/ExternalProfileRef/HistoryCut use Data §192.1 exactly; full reference identity includes kind, version via exact schema, revision digest/profile and schema revision. HistoryInput is nonempty verified prior cut; initialization sentinel only in original bootstrap contracts. Logical ID grammar follows Data §6: lowercase kind prefix plus underscore and canonical UUID; no display ID as selector.

For new contracts: body maximum 16 MiB UTF-8 canonical bytes, each text maximum 65536 Unicode code points (nonempty unless explicitly optional), arrays maximum 65536 members, IDs exact UUID grammar, integers bounded signed 64-bit except strictly positive revision numbers. No NaN/Infinity, duplicate JSON keys, unknown enum values, implicit normalization, or unbounded parser resources. Larger campaign closure must use a separately approved successor contract, not silently truncate. Existing bound contracts retain their exact constraints until a reviewed successor delta explicitly changes them. These bounds are proposed owner-visible semantics, not hidden generator choices.

Reference arrays are full-identity sorted sets with duplicate rejection. Raw/Profile tagged union arrays sort by tag + complete canonical value. `CommitBody.immutable_object_refs` retains original union-DAG topological sequence, never sorted set. Any optional field is absent when unavailable; no new nullable representation unless normative contract explicitly permits it. Every field without `?`/`optional` is required; arrays may be empty only when cardinality says 0. Prior typed refs must be accepted in the exact campaign/source/subject context at the represented cut. External profile fields are exact prior pins for the named purpose; no local overlay, latest-installed selection or caller-minted authority. Raw fields always re-read retained exact bytes and verify digest/length/profile.

FACT means recorded statement/intent, ASSESSMENT means qualified dimension at a cut, DECISION means authorized predicate/decision, DERIVED_PROJECTION means deterministic reproducible enumeration/communication. None can upgrade its source truth. Canonical semantic wrappers use ObjectDigest; actual raw observations, ZIPs, public bytes and text exports use RawDigest. The Registry role name by itself cannot select a digest domain. In particular raw/export files are not silently given an ObjectDigest just because a Registry row names their family; an accepted wrapper must have an explicit closed body/schema and raw reference. Proposed row identity clarification must be approved before generation.

Producer is the trusted coordinator acceptance boundary; projections are independently reproduced there, not accepted from caller checksum. Required validation is the conjunction of original named layer predicates plus applicable new semantic/finalization predicates, as listed in the graph; producer identity never implies evidence strength. Same-cut exact retry reuses original receipt; competing different immutable bodies for one represented tuple conflict by CAS, with **REJECT + NO CANONICAL STATE MUTATION**. Accepted revisions remain immutable. Only explicit predecessor fields create revision lineage; changed tuple/cut for a projection creates a new immutable entry. No hidden mutable current object or latest-by-ID authority. Fresh approved successor campaign only; preserve all old contracts/history/bytes and historical invalid objects for forensic display.
"""


def write_md(name, text):
    (OUT / name).write_text(text.strip() + "\n", encoding="utf-8")


def proposal_detail(key):
    p = proposals[key]
    if key == "residual_risk/1":
        return (
            "Unchanged separate complete recommendation: [Residual Risk proposal](R5_4_2_RESIDUAL_RISK_CONTRACT_DECISION_PROPOSAL.md). ASSESSMENT, immutable explicit revisions; existing approval_decision/1 remains separate authorized acceptance. Raw identity: `"
            + p["design_raw_digest"]
            + "`. Its historical SPEC_CONFLICT describes the previous scoped pass; this consolidated pass supersedes that analysis stop, not its proposed semantics.\n"
        )
    lines = [
        f"### {key}",
        f"Role **{p['canonical_role']}**; lifecycle IMMUTABLE; authority: {p['authoritative_for']}",
        "Basis: " + "; ".join(p["normative_basis"]),
        "**Exact proposed body**",
        "```text",
    ]
    lines += p["body"]
    lines += [
        "```",
        "**Material references**",
        "| Field | Target kind/version(s) | Cardinality | Class |",
        "| --- | --- | --- | --- |",
    ]
    for f in p["material_refs"]:
        targets = f.get("allowed_keys") or []
        external = (
            "Exact RawRef"
            if f["ref_class"] == "CONTENT_OBJECT"
            else (
                "HistoryCut"
                if f["ref_class"] == "HISTORY_INPUT"
                else "Exact named-purpose ExternalProfileRef; definition below"
            )
        )
        lines.append(
            "| "
            + f["field"]
            + " | "
            + (", ".join(targets) if targets else external)
            + " | "
            + f["cardinality"]
            + " | "
            + f["ref_class"]
            + " |"
        )
    # Body profile/raw/principal fields are material too, even when the core
    # traversal does not create canonical-object edges for them.
    listed = {f["field"] for f in p["material_refs"]}
    for b in p["body"]:
        field = b.split(":")[0].rstrip("?")
        if field not in listed and any(
            t in b for t in ("ExternalProfileRef", "RawRef", "AuthorityRef")
        ):
            cls = (
                "CONTENT_OBJECT"
                if "RawRef" in b
                else (
                    "AUTHORIZED_ACTOR_REF"
                    if "AuthorityRef" in b
                    else "HISTORY_CONTEXT_BINDING"
                )
            )
            lines.append(
                "| "
                + field
                + " | "
                + b.split(":", 1)[1]
                + " (exact retained/pinned representation) | "
                + ("0..1" if "?" in b else "1")
                + " | "
                + cls
                + " |"
            )
    lines += [
        "",
        "All prior-only fields prohibit same-commit; content fields permit earlier verified durable raw content or exact retained reuse. Profile fields prohibit same-commit semantic self-upgrade. Predicate checks:",
    ]
    lines += ["- " + x for x in p["cross_object_predicates"]]
    lines += [
        "",
        "Producer/validation/uniqueness/revision/consumer/migration: "
        + common["producer_authority"]
        + "; FULL_PATH_SEMANTIC_V1 with applicable original layers; exact immutable tuple and CAS/idempotency rules above; COORDINATOR/VALIDATOR and referenced downstream consumers. No silent version alias.",
        "",
        "**Alternatives rejected:** " + " ".join(p["alternatives_rejected"]),
        "",
    ]
    return "\n".join(lines)


claim_text = f"""# R5.4.2 Assurance Claim Set contract proposal

{banner}

Recommend one dedicated `assurance_claim_set/1`, **DERIVED_PROJECTION**, immutable. Data §80 requires a separate exact target but does not define it. SOUND (§147) is claim-relative qualification and cannot represent the complete enumeration; snapshot (§105) alone has no no-omission contract. FACT would confuse enumeration with truth, ASSESSMENT with assessed assurance. Removing the ref and embedding another array changes the frozen Candidate body and duplicates its existing claim array.

{proposal_detail("assurance_claim_set/1")}

The universe is the accepted FindingClaimRevision lineage tips for the exact campaign/source and inventory at `claim_set_input_history_cut`. Explicit predecessor edges determine tips; a fork is a conflict, never a latest timestamp choice. Include all tips whose surface/scope intersects inventory and every tip whose applicability cannot be disproved under exact pinned policy. A rejected, unresolved or contradictory claim is still enumerated. Superseding a claim must preserve the underlying unresolved material matter in its new revision/risk/obligation accounting; revision cannot be used to delete adverse information. No free-standing generated assurance assertion or unanalyzed caller string becomes a claim.

This is an enumeration of authored claims, not completeness of coverage: Candidate must independently enumerate full inventory/mandatory obligations/current qualifications, all current adjudications for included claims, unresolved contradictions, qualified/applicable evidence and risk closure. An empty authored claim set is legal only as an enumeration; unknown/missing obligation support still blocks required assurance. A claim with no current adjudication remains visible and cannot be represented as a current favorable finding state. This interpretation is an explicit owner decision for the previously undefined term ASSURANCE CLAIM SET.

Candidate.scope_inventory_ref equals the set inventory; Candidate.finding_claim_revision_refs equals set.claim_refs and independently recomputed universe. Cuts are identical, with all source claim/authority facts accepted before represented cut. The set may be earlier same-commit content of Candidate under original CONTENT_OR_PRIOR; it cannot include same-commit new claims as prior facts. Earlier accepted set is reusable only for identical inventory/claim closure and represented cut. Accepted set/candidate commits alone do not change assessed subject basis; new material claim/scope/evidence/risk change requires new set/candidate and both challengers. No Candidate future ref or self-hash is stored.

{common_text}

Vector designs: CLAIM_SET_EXACT_ACCEPT, CLAIM_SET_OMISSION_REJECT, CLAIM_SET_STALE_CUT_REJECT, CLAIM_SET_DUPLICATE_REF_REJECT, CLAIM_SET_CROSS_CAMPAIGN_REJECT. Inputs/expected outcomes and all nine negative state-snapshot fields are in the graph; **NOT EXECUTED**. Every negative acceptance leaves canonical state unchanged.

Owner approves identity/role, four-field body, complete universe and Candidate equality rule, exact prior facts/earlier content chronology and finite constraints. No runtime or schema bytes are approved by this proposal.
"""
write_md("R5_4_2_ASSURANCE_CLAIM_SET_CONTRACT_PROPOSAL.md", claim_text)

public_text = f"""# R5.4.2 Public Conclusion Statement contract proposal

{banner}

Recommend one dedicated canonical semantic wrapper `public_conclusion_statement/1`, **DERIVED_PROJECTION**, immutable, backed by exact retained public raw bytes. Wrapper ObjectDigest and public RawDigest are distinct. It communicates existing accepted conclusion; it establishes no new assurance or product release authority.

{proposal_detail("public_conclusion_statement/1")}

Data §81 final technical report already references FinalAssuranceCase. Reusing that report/receipt as the mandatory prior public statement would create FinalCase→report→FinalCase. General report export also lacks the restricted public renderer. RawRef alone cannot establish prior canonical semantic acceptance. FACT is inappropriate because statement creates no new truth. This selected model avoids all three alternatives.

Chronology: prior accepted CampaignConclusion (and its STOP/StopInput/candidate/challenger/risk/limited-basis closure) → durable deterministic public raw → accepted PublicConclusionStatement → later FinalAssuranceCase → later ReleaseQualification → optional later final technical report/export. Statement never references its future FinalCase, release decision or accepting head. No public release-ready authorization can be implied before ReleaseQualification; the STOP release axis is explicitly labelled assessment.

PUBLIC_CONCLUSION_RENDER_V1 uses closed canonical UTF-8 JSON. Fields are campaign_ref, source_generation_ref, conclusion_ref, stop_evaluation_ref, scope_inventory_ref (null only when legally absent for early limited conclusion), termination_state, assurance_level, continuation_decision, stop_release_assessment, residual_risks, limited_basis_refs and bounded_statement. Values come only from exact accepted chain. Risk entries disclose exact risk ref, description, reason_unresolved, disposition and materiality; every material/unknown applicable risk is present. Redaction may remove sensitive raw basis but never risk presence, state or limitation. A general caller-written prose field cannot bypass equality: bounded_statement is exactly accepted Conclusion.bounded_conclusion_statement. Any text view uses deterministic fixed labels and escaping of this exact JSON, not arbitrary marketing narrative.

Raw bytes must equal independent Render(exact conclusion, exact pinned renderer/profile). The raw artifact contract is the exact renderer profile; media type application/json, bounded UTF-8 closed body. Thus wrong conclusion, omitted risk, assurance upgrade, stale chain, or COMPLETED_LIMITED rendered as PASS/READY/full completion rejects. A malicious accepted bounded statement is itself rejected at Conclusion by finalization consistency; quoting an unchecked natural-language claim does not make it true. Unknown/non-PASS STOP forbids public full success and both READY states. Statement discloses campaign termination and qualified scope separately from product readiness.

FinalCase.public_conclusion_statement_ref is PRIOR_ACCEPTED_ONLY exactly this kind/version; Statement.conclusion_ref equals FinalCase.conclusion_ref; risks and STOP/assurance/source identities are strict equalities. Intervening material audit-basis change blocks statement/finalization and requires fresh lawful assurance closure/successor semantics; extra wrapper acceptance commits are not such a change. One exact renderer result per conclusion/profile is idempotent; different raw bytes cannot replace it.

{common_text}

Vector designs: PUBLIC_CONCLUSION_EXACT_ACCEPT, WRONG_CONCLUSION_REJECT, ASSURANCE_UPGRADE_REJECT, RESIDUAL_RISK_OMISSION_REJECT, LIMITED_AS_FULL_REJECT, STALE_CUT_REJECT (all names have PUBLIC_CONCLUSION prefix in graph). **NOT EXECUTED**; canonical negatives reject with all before/after canonical state fields unchanged.

Owner approves dedicated raw-backed projection, five-field body, closed renderer/disclosure constraints, exact temporal ordering and no-new-assurance/no-false-public-pass rule. Runtime renderer and schema generation remain later work.
"""
write_md("R5_4_2_PUBLIC_CONCLUSION_CONTRACT_PROPOSAL.md", public_text)

owner = f"""# R5.4.2 consolidated owner decision package

{banner}

Recommended decision: approve **one coherent design delta**, comprising the 21 proposed kinds and all explicit reference/body/profile/temporal completion decisions below. Approval authorizes subsequent candidate materialization only. It does not activate R5.4.1, authorize current overlay/schema authority, freeze independently, implement NF02, qualify runtime or close NF02.

The three original issues are resolved as recommended proposals: ResidualRisk=ASSESSMENT with immutable explicit revisions and separate existing ApprovalDecision; AssuranceClaimSet=complete immutable DERIVED_PROJECTION; PublicConclusionStatement=immutable raw-backed DERIVED_PROJECTION preceding FinalCase. Additional reachable gaps were not stopped at first discovery. They are included in this same approval package.

## 1. Identity, schema and reference rules to approve

{common_text}

Every scalar enum written in a proposed body is closed; `profile enum` is a finite domain declared in the exact governing purpose profile before first use. It is not an arbitrary runtime extension. Text/scoped subject values never substitute for available exact refs. Common maximum constraints are explicitly proposed above. Cross-object predicates are mandatory semantic-validator checks in addition to future JSON Schema, not discretionary implementation checks.

Generic registered_immutable_object targets become finite active-closure sets in storage wrappers plus exact command-domain predicates, and explicit field-specific target sets elsewhere. Storage acceptance does not legalize an object just because it is on the finite list. CommitBody/CommandEnvelope/CommandReceipt/HistoryCut are not ordinary same-commit payload/output members; receipt remains post-acceptance sidecar. Stage/Lane required outputs must match pinned slots and complete predicates, and cannot require future STOP/Conclusion/FinalCase/ReleaseQualification/PublicStatement. Required closure includes registered RAW_EVIDENCE/EXPORT families and installation profile keys as contract dependencies; actual raw/export bytes remain RawDigest identities, not new campaign state authority.

The complete finite class→kind/version map, each class's actual owner-field cardinality/class and all explicit overrides are in `R5_4_2_SEMANTIC_CLOSURE_GRAPH.json`. CONTENT_OR_PRIOR allows earlier content only where exact owner contract allows it. PRIOR_ACCEPTED_ONLY always prohibits same-commit. HISTORY_INPUT always points backward. Profile refs cannot be semantic self-upgrades. CampaignRef is logical identity established by accepted Genesis/SuccessorGenesis, not a new campaign object. Blocker is a derived ledger (§178); limited basis uses exact underlying obligation/qualification/invalidation/contradiction/risk/STOP/approval/stage facts and requires the corresponding proved blocker, never vague residual-risk text.

## 2. Existing-contract completion decisions

- Correct successor FindingClaimRevision.discovery_relation_refs target set to the six exact provenance assessments (blind eligibility plus five new assessments), backward-only per Data §57. R5.4.1 row currently allows discovery_record, conflicting with the complete narrative section. Preserve that historical qualified row; explicitly correct the successor row/schema, with no alias or retroactive acceptance. Raw DiscoveryRecord cannot substitute for its later assessments.
- Make every schema-deferred material reference explicit before schema generation. Full original bodies/sections, proposed refs, profile/raw representations and exact normative field catalog are recorded per node in the graph. Names are not interpreted as implicit wire aliases. Preserve the separate legacy semantic-equivalence and mapping assessments, evidence applicability versus qualification, and obligation applicability versus waiver.
- Resolve dependency intent before execution as exact EXECUTION_DEPENDENCY_PLAN_V1 profile. Observed ObservationDependency→EvidenceDependencyGraph follows observations. Requiring the observed graph in first ExecutionDescriptor would make descriptor→observation→graph→descriptor cycle; it is forbidden. EvidenceApplicability/Qualification/Independence/Invalidation use the exact observed graph, not the planned list as proof.
- Reuse experiment_spec/execution_descriptor/execution_result/observation/evidence qualification for interaction (§70), causal/endurance and retained mutation/oracle raw records. Preserve two distinct §68 outcome enums and mandatory oracle 2×2 contrast, qualified activation and independent normalization. Raw method case/results cannot directly establish evidence/coverage. Replay is exact raw-backed bundle manifest + accepted descriptor/observations/current qualification; fresh executor alone proves no independence.
- Reuse invariant_revision for temporal invariant statement; exact model/raw formal specification and fidelity/conformance closure determine derived temporal status. No standalone mutable temporal status or proof transfer. Reuse build_manifest as §123 BuildInputManifest, with separately raw BUILD_PROVENANCE_RECEIPT; no final output self-hash or subject/application identity conflation.
- Existing snapshot is a reproducibility seal only. Channel inventory is a closed snapshot profile of all declared channels and exact prior capture facts with explicit UNKNOWN, never independent enforcement authority. Coverage summaries equality-bind exact obligations/qualifications/cut; effort uses its dedicated complete projection. Report receipt binds raw report/as_of_head/profile/producer after FinalCase; release/export checks keep their original independent gates.
- Source drift, requalification and recovery remain independent exact-cut facts/assessments. Successor campaign only when existing trigger/carry-forward/challenge predicates apply; release-specific changes cannot repair audit basis. No new in-place upgrade or fabricated predecessor qualification.

## 3. Residual-risk/finalization no-omission decisions

Approve the unchanged separate residual-risk proposal. At a represented cut, derive applicable active revision tips from accepted roots and exact predecessor edges. Material and unknown-materiality risk cannot be omitted. Accepted risk requires separate prior approved ApprovalDecision bound to exact assessed tuple and authorized actor/scope; approved risk status alone proves nothing. No new approval kind is needed because Data §157 expressly covers residual acceptance; successor decision_type RESIDUAL_RISK_ACCEPTANCE and exact related-risk/profile authorization must be explicit.

Candidate risk set and STOP risk set each equal the independently recomputed applicable set at their represented cut. A material difference requires fresh Candidate and both challenger roles; historical Candidate does not mutate. Conclusion risk set equals evaluated StopInput risk set after drift/applicability revalidation; PublicStatement and FinalCase equality-bind Conclusion risks, not a caller subset. Approved material residual risks can coexist with PASS only if every original mandatory applicable obligation and challenge/effort/scope predicate is satisfied and pinned policy permits their independent acceptance; READY_WITH_RESIDUAL_RISK additionally requires every release-material risk authorized under release policy. Waiver/risk does not convert an unsatisfied mandatory obligation into SATISFIED.

COMPLETED_LIMITED is condition-dependent authorized bounded/blocked termination, never PASS laundering. Residual risk is required in limited basis when an applicable residual risk contributes to the limitation; otherwise actual exact stage/obligation/unknown/blocker/STOP facts suffice. Early limited termination may legally omit candidate/challengers, but must retain exact non-PASS STOP, bounded/insufficient assurance and explicit basis. Material risk present in conclusion can never disappear from public/final envelope. History corruption permits only external diagnostic, never invented accepted StopEvaluation.

## 4. Proposed complete contracts

"""
for key in sorted(proposals):
    owner += proposal_detail(key) + "\n"
owner += "\n## 4a. Explicit body completions for existing underspecified rows\n\n"
for key, d in body_completions.items():
    owner += (
        f"### {key}\n\nClosed proposed body:\n\n```text\n"
        + "\n".join(d["body"])
        + f"\n```\n\n{d['predicate']}\n\n"
    )
owner += """These are owner decisions on previously schema-deferred bodies, not generator discretion. LayerResult is closed {layer:L1|L2|L3|L4|L5|L6|L7,result:PASS|FAIL|UNKNOWN,reason_codes:Code[]}; Handoff schema_results use closed {schema_key,schema_raw_digest,result:PASS|FAIL|UNKNOWN,reason_codes:Code[]}. Codes match `[A-Z][A-Z0-9_]{0,127}`. Component/Channel structures have only listed fields; no arbitrary extension dict.

Snapshot ClosedPurposePayload is discriminated {purpose,data}. STOP_INPUT data is {direct_input_refs,invalidated_refs,unknown_refs,blocked_refs}, exact sorted typed-ref sets independently derived at sealed cut, with direct_input_refs equal all direct authority refs in the consuming StopInput (profiles checked by cut). COVERAGE_SUMMARY data is {obligation_refs,qualification_refs,unresolved_obligation_refs}, with exact Candidate equality; counts are computed, never stored as authority. CHANNEL_INVENTORY data is {attempt_ref,executor_spec_ref,delivery_spec_ref,channels}; each entry is {channel,witness_refs,state}, exact ten-channel domain from predecessor Registry, state WITNESSED|DECLARED|UNKNOWN, witnesses exact prior observation/tool/execution refs. RUN_STATE data is {entity_states}; each entry {entity_ref,state} uses exact prior stage_run/lane_run/attempt/genesis ref and corresponding original closed FSM enum, deterministically replayed from accepted transitions. Each list is complete for its purpose and cut; unknown or duplicate element fails closed. None points forward to consuming StopInput or asserts independent enforcement/truth.

Other registered unbound bodies retain the exact complete Data section's field/enum list (included verbatim per node in graph), with all ref representations/types supplied by proposed material-ref completion and body-field catalog. Optional/cardinality/shape choices cannot be inferred later from Python producers. A contradictory qualified schema requires an explicit successor correction and vector, not retroactive legalization.

"""
owner += "\n## 5. Exact external profile and raw-contract semantics\n\n"
for name, spec in profile_designs.items():
    owner += f"### {name}\n\n{spec}\n\n"
for name, spec in raw_designs.items():
    owner += f"### {name}\n\nBasis: {spec['basis']}. Closed raw body fields: `{', '.join(spec['fields'])}`. {spec['rule']}\n\n"
owner += """Every new profile has a semantic identity above but **no approved bytes/digest yet**. Future exact ExternalProfileRef is profile_id + RawDigest(frozen bytes), installed/pinned before use, with full interpreter/checker/renderer dependency closure. Existing 13 exact predecessor profiles are preserved in graph with raw hashes; successor cannot simply reuse pins whose Registry/schema/policy dependencies changed. Unknown profile purpose/entry fails closed. Arbitrary deployment secrets/actor identifiers/actual campaign numeric budgets are installation/campaign inputs constrained by these contracts, not unanswered choices about canonical meaning. They cannot redefine enum/predicate/ref classes.

## 6. Reference targets and vectors

"""
owner += "| Class | Actual target kind/version(s) |\n| --- | --- |\n"
for name, targets in classes.items():
    owner += (
        "| "
        + name
        + " | "
        + (
            ", ".join(targets)
            if targets
            else "Exact ExternalProfileRef to qualified protocol/policy bundle; no canonical invented bundle kind"
        )
        + " |\n"
    )
owner += "\nPer-field class/cardinality/prior/same-commit rules are in exact graph edges/contracts; named noncanonical target representations are explicit in graph. Scope exclusion ApprovalDecision must be authorized SCOPE_EXCLUSION with exact scope related_ref; generic approval does not become obligation applicability. Control intent is exact experiment_spec; control execution/qualification is separately execution_result/evidence qualification.\n\n"
owner += f"Vector designs: {len(vectors)} cases, including every requested CLAIM_SET/PUBLIC_CONCLUSION/RESIDUAL_RISK case and registered/schema/substitution/stale/basis/cross-campaign/CAS negatives for all 21 kinds. NOT EXECUTED; future canonical negatives compare `{', '.join(snapshot_fields)}` and require no mutation. Each new contract also needs positive retry, concurrent competing bodies and crash/restart reconstruction tests before runtime qualification. Current design static verification is not those tests.\n"
owner += "\n## 7. Candidate materialization delta plan\n\n| Future file/family | Decision | Reason |\n| --- | --- | --- |\n"
for d in delta_plan:
    owner += f"| {d['file']} | {d['decision']} | {d['reason']} |\n"
owner += f"""\n## 8. Owner decision and entry gate

Approve all semantic models, exact bodies/enums/ref domains/chronology, no-omission/independent derivation, identity/finite constraints, the 21 proposed kinds, existing-contract corrections and external-profile models as **one consolidated delta**. Rejected alternatives and their reasons are part of this package. Approval is not a choice between vague models; the recommendations above are concrete. Any changed semantic choice requires recomputing the graph before materialization.

Graph fixed point under these proposals: **{counts["reachable_canonical_kinds"]} keys = {counts["registered_in_r5_4_1"]} registered R5.4.1 + {counts["new_proposed_canonical_kinds"]} proposed**. Currently bound: {counts["currently_schema_bound"]}; missing executable bindings: {counts["missing_executable_bindings"]}. Queue empty; unresolved abstract targets/C/D zero in the proposed model. These claims apply to the explicit design graph, not the still-incomplete actual qualified Registry. No candidate directory/Q1/Q2/schema creation is permitted in this task.

Final gate: **READY_FOR_OWNER_APPROVAL** (design only).
"""
identity_table = (
    "\n### Fresh qualified identity readback\n\n| Identity | Exact value |\n| --- | --- |\n"
    + "".join(f"| {k} | `{v}` |\n" for k, v in qualified_readback.items())
)
owner = owner.replace(
    "## 1. Identity, schema and reference rules to approve",
    identity_table + "\n## 1. Identity, schema and reference rules to approve",
    1,
)
write_md("R5_4_2_OWNER_DECISION_PACKAGE.md", owner)

report = f"""# R5.4.2 full semantic closure report

{banner}

## A. Executive decision

**READY_FOR_OWNER_APPROVAL**, for the explicit hypothetical design graph. Expanded pass resolves 21 proposed canonical kinds and finite representations/profiles; it is not approval or runtime evidence. R5.4.1 remains a valid AUTHOR-QUALIFIED EXACT CANDIDATE, insufficient for the full declared path. No existing qualification is invalidated.

## B. Source and candidate identities

Repository `eagleblastmusic-lgtm/bdb-audit`, local `C:\\Projekty\\Audyty\\BDB Audit`. Required git status/branch/HEAD/tree/log commands executed before changes and at fresh inspect. Branch `{old["source"]["branch"]}`, HEAD `{old["source"]["head"]}`, tree `{old["source"]["tree"]}`. Main remains frozen. Existing dirty NF02 code/tests and scratch directories retained; ignored `.codex-pytest-tmp` permission warning does not affect task inputs.

Qualified identity fields, source raw pins and preserved protected byte pins are inherited exactly in graph `predecessor`/`source`, not copied from older R5.4. Fresh candidate manifest readback verifies all 120 entries' byte length and RawDigest; zero mismatches. All 144 predecessor subtree files and {len(preservation)} combined preservation pins checked. Actual current candidate manifest remains pre-Q1 construction manifest; valid external qualification, not its stale construction status, establishes R5.4.1 authority.

## C. Evidence reused and traversal

Read all existing R5_4_2 diagnostics completely; original abort notice named CANDIDATE_MANIFEST is NOT a materialized candidate. Reused unchanged 483-occurrence inventory (RawDigest `{digest(OUT / "RESIDUAL_RISK_NORMATIVE_USAGE_INVENTORY.json")}`), prior 51/39/11/1 seed graph and 276 edges, later 68-node frontier and proposed risk row. Earlier diagnostics and residual proposal remain historical records; only current closure/reachability diagnostics supersede the prior stop. Machine graph retains full prior diagnostics and edges, full source sections and exact profile bytes/hashes as evidence.

Pass starts with prior nodes plus mandatory lifecycle/recovery/report/release roots; breadth-first expands exact Registry refs, complete normative body references, identity prerequisites and proposed refs. C/D defects become explicit proposed rows or concrete raw/profile/existing-kind representations, then traversal continues. Generic storage wrappers are scoped to finite active closure and never independently authorize kinds. The normative body reference catalog is audited without generic profile fallback for unknown field names. Queue/traversal log and per-node reachability witnesses are recorded.

## D. New semantic contracts and corrections

"""
for key in sorted(proposals):
    report += (
        f"- `{key}` — {proposals[key]['canonical_role']}; "
        + (
            "unchanged separate risk design"
            if key == "residual_risk/1"
            else "; ".join(proposals[key]["normative_basis"])
        )
        + ".\n"
    )
report += """
Complete proposed bodies/refs/roles/authority/layers/uniqueness/revision/migration/alternatives are in Owner Decision Package and graph. Dedicated claim-set/public proposals are separate requested artifacts. Additional mandatory discovery and calibration rows come from explicit canonical body lists in Data §§57/149; corpus candidate from §26; Gate/Handoff from §§86–88. No production overlay or Python producer defines normative meaning.

FindingClaimRevision row/narrative conflict is surfaced explicitly: Registry allows DiscoveryRecord in discovery_relation_refs; complete Data §57 requires six later assessments. Successor must correct row/schema, retaining old bytes. Planned dependency set versus observed graph is separated to eliminate a first-execution future-reference cycle. Scope/materiality/finding/risk/limited/release targets are finite. Blocker remains derived, no invented blocker authority. New model/fault objects are immutable prior intent, not proof; existing approval remains separate authorized decision.

## E. Mandatory temporal closure

Qualified bootstrap and original union-DAG rules → accepted assignments → immutable raw packages → Binding → later STARTED → guarded delivery → retained result → AdmissionEvidence/2 → later Result/2 → separately qualified LaneCompletion/StageCompletion.

Prior execution intent/environment/planned dependency profiles → observations/cleanup/fault witnesses → observed dependency facts/graph → current applicability/independence → EvidenceQualification → FindingAxis/Adjudication/ObligationQualification → complete claim/risk/effort projections → Candidate → both ChallengerAssignments → later ChallengerResults → E5 StageCompletion → StopInput/StopEvaluation → later Conclusion → PublicStatement → later FinalCase → later ReleaseQualification → reports/export validation. No edge to own future consumer, self digest or accepting provenance. Same-commit content only under exact allowed class; prior refs stay prior. E6 inherits original obligations/policy/source/knowledge constraints and returns to fresh candidate/challenge/STOP closure. Material post-final drift requires existing lawful successor predicates; no release laundering.

## F. Fixed-point result

"""
report += (
    "```text\n"
    + "\n".join(f"{k} = {v}" for k, v in counts.items())
    + "\nfixed_point_reached = true\nunexplored_queue = []\n```\n"
)
report += """
Counts include the finite registered contract dependencies for mandatory raw/export/installation families, not an assertion that every export file is an accepted ObjectDigest object. Four excluded Registry keys are external author/foundation governance records, external Golden set and historical schema_registry/1; they remain exact preserved read-only authority/evidence dependencies rather than fresh campaign acceptance targets. All 110 other registered keys have a concrete in-scope traversal witness. 21 new keys exist only in hypothetical analysis. No reachable kind obtains authority from the design graph itself.

## G. Profiles and remaining machine work

Exact predecessor profiles are read and hash-pinned. Proposed full-path/finalization/claim-set/dependency/effort/channel/model/gate/calibration/public/report/recovery/profile parameter contracts are explicitly specified in owner package. Raw replay/mutation/oracle/temporal/causal/endurance/build receipt representations do not create competing canonical truth. Their exact future executable contracts and profile/code dependency bytes must be frozen in successor. Numeric campaign policy values remain explicit governed inputs, not hidden default semantics.

Missing executable binding keys (exact list also in graph/reachability):

"""
report += (
    "\n".join("- `BDB_SCHEMA_REGISTRY::" + key + "`" for key in sorted(visited - bound))
    + "\n"
)
report += """
These 92 missing bindings comprise 71 existing registered keys and 21 proposed keys. Existing 39 bindings are qualified R5.4.1 evidence; changes to approved target/body semantics require new exact successor schemas and pins, not blind reuse. Class A/B machine work remains after approval; Class E profiles have proposed semantic models but no generated/frozen bytes. No real Class C/D defect disappears from R5.4.1 merely because a hypothetical node is complete.

## H. Verification and limits

Command `python docs/R5_4_2/tools/full_semantic_closure.py` performs read-only predecessor verification and generates ONLY design diagnostics/documents. Commands, exact Python/environment version, structural checks, durations and final byte preservation are recorded in graph verification at closeout. Vector designs were not executed; no pytest/runtime crash/CAS/independent adversarial/Q1/Q2 claim is made. Runtime source is unchanged. Fixed point is conditional on owner approving these specific models; a semantic change requires another traversal. Static graph checks cannot prove future schema parity or implementation correctness.

## I. Owner decision / next conditions

Owner approves one consolidated semantic package, including 21 proposed rows, existing ref/body corrections, exact profile semantics and no-omission/temporal rules. Only then materialize R5.4.2, bind every reachable schema, perform fresh readback/self-audit/external author qualification and later Q2/N5–N11. R5.4.1 assurance remains AUTHOR_ONLY=YES, INDEPENDENT_FREEZE=FALSE. NF02 stays OPEN.

Final gate: **READY_FOR_OWNER_APPROVAL**.
"""
report = report.replace(
    "## C. Evidence reused and traversal",
    identity_table + "\n## C. Evidence reused and traversal",
    1,
)
write_md("R5_4_2_FULL_SEMANTIC_CLOSURE_REPORT.md", report)
closure = f"""# R5.4.2 schema closure diagnostic — full semantic design pass

{banner}

Gate **READY_FOR_OWNER_APPROVAL** for the complete hypothetical owner design. Previous SPEC_CONFLICT diagnostics were partial and remain preserved in graph history. R5.4.1 remains valid author-qualified predecessor; actual schema sufficiency has not changed.

Reachable keys: **131 = 110 qualified Registry keys + 21 proposed canonical kinds**. Currently bound: **39**; missing executable bindings: **92** (71 registered + 21 proposed). Proposed semantic-complete: 131; unresolved abstract targets/Class C/Class D: zero; queue empty; fixed_point_reached=true. None of the 21 rows exists in qualified Registry yet.

Full source identities, 120-file/zero-mismatch readback, prior graph reuse, full inventory, profile semantics, exact reference maps, extra canonical discovery/calibration/corpus/gate/recovery contracts, vector designs and future delta plan: `R5_4_2_FULL_SEMANTIC_CLOSURE_REPORT.md`, `R5_4_2_SEMANTIC_CLOSURE_GRAPH.json` and `R5_4_2_OWNER_DECISION_PACKAGE.md`. The residual-risk proposal is retained unchanged and referenced; claim-set and public-statement proposals are separate requested artifacts.

No candidate, schema, binding, Registry, Golden Vector, Q1, Q2, runtime implementation or runtime qualification was produced. Design vectors NOT_EXECUTED. Schema-bound status is read directly from exact predecessor SchemaRegistry/2; proposed profiles have semantic definitions but no approved raw bytes/digests. Owner approval and later machine/executable parity are required before any activation.
"""
write_md("R5_4_2_SCHEMA_CLOSURE_REPORT.md", closure)

"""Preserve source obligations as explicit, nonqualified semantic work items.

Inventory is deliberately not approval: every source paragraph is retained,
including ones without modal words. Pattern discovery cannot establish parity.
"""

from __future__ import annotations

import copy
import hashlib
import re
import sys

from execution import OUT, ROOT, canonical, digest, preserve, read, write


REVIEW_FIELDS = ("review", "review_evidence", "review_notes", "dimension_reviews")


def evidence_is_bound(previous):
    reviewed = not previous.get("review", "PENDING").startswith("PENDING") or any(
        not paragraph.get("review", "PENDING").startswith("PENDING")
        for paragraph in previous.get("source_paragraphs", ()))
    proofs = previous.get("review_evidence", [])
    if not proofs:
        return not reviewed
    if not isinstance(proofs, list):
        return False
    for proof in proofs:
        if not isinstance(proof, dict) or not isinstance(proof.get("file"), str):
            return False
        path = (ROOT / proof["file"]).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
            return False
        if digest(path) != proof.get("raw_digest"):
            return False
    return True


def retain_review(record, previous):
    """Retain a review only against identical, explicitly bound inputs.

    Old unbound reviews remain pending. An invalidated review is retained as
    historical data, never as current closure evidence.
    """
    if not previous:
        return record
    same = previous.get("review_input_digest") == record["review_input_digest"] and evidence_is_bound(previous)
    if same:
        for field in REVIEW_FIELDS:
            if field in previous:
                record[field] = copy.deepcopy(previous[field])
        old_paragraphs = {p["paragraph_ordinal"]: p for p in previous["source_paragraphs"]}
        for paragraph in record["source_paragraphs"]:
            old = old_paragraphs.get(paragraph["paragraph_ordinal"], {})
            if old.get("text_sha256") == paragraph["text_sha256"]:
                for field in REVIEW_FIELDS:
                    if field in old:
                        paragraph[field] = copy.deepcopy(old[field])
    elif any(previous.get(f) for f in REVIEW_FIELDS if f != "review") or not previous.get("review", "PENDING").startswith("PENDING"):
        record["invalidated_review"] = {f: copy.deepcopy(previous[f]) for f in REVIEW_FIELDS if f in previous}
        record["invalidated_review"]["review_input_digest"] = previous.get("review_input_digest")
        record["invalidated_review"]["reason"] = "REVIEW_INPUT_OR_EXACT_EVIDENCE_CHANGED_OR_UNBOUND"
        record["invalidated_review"]["source_paragraphs"] = copy.deepcopy(previous["source_paragraphs"])
    if "invalidated_review" in previous and "invalidated_review" not in record:
        record["invalidated_review"] = copy.deepcopy(previous["invalidated_review"])
    return record


def review_dependencies():
    # Conservative complete design binding. No dependency is inferred from
    # the review's own claims. Output audits and the queue are not authority.
    names = ["OWN_REFERENCE_RESOLUTIONS.json", "design/VERSION_IMPACT_PLAN.json",
             "design/OWN_FIELD_DOMAINS.json", "design/COMMON_BODY_GRAMMARS.md", "design/COMMON_GRAMMARS.json",
             "design/EXTERNAL_PROFILE_CONTRACTS.json", "design/PURPOSE_CONTRACT_GRAMMARS.json",
             "design/PROFILE_REFERENCE_CONTRACTS.json", "design/PAYLOAD_REFERENCE_CONTRACTS.json",
             "design/FULL_PATH_TRANSITION_TABLE.json", "design/COMMAND_EVENT_CONTRACT.md",
             "design/PURPOSE_PREDICATE_CONTRACTS.md", "design/HISTORY_CUT_SEMANTIC_REVIEW.md",
             "design/BOOTSTRAP_PRECEDENCE_SUCCESSOR.json", "design/REGISTRY_BOOTSTRAP_SUCCESSOR_DELTA.json",
             "design/BOOTSTRAP_INSTANCE_ORDERING_FIXTURE.json",
             "design/SCOPE_EXCLUSION_SEMANTIC_REVIEW.md", "design/BUILD_INSTALLATION_CONTEXT_REVIEW.md",
             "design/BUILD_INPUT_CLOSURE_SEMANTIC_REVIEW.md",
             "design/SOURCE_ALIAS_AUTHORITY_SEMANTIC_REVIEW.md",
             "design/SOURCE_ALIAS_PRIOR_DURABILITY_CONTROLS.json",
             "design/RUNTIME_EVIDENCE_DRIFT_CONTROLS.json",
             "design/COMMAND_CLOSURE_SEMANTIC_REVIEW.md", "design/SOURCE_IDENTITY_SEMANTIC_REVIEW.md",
             "design/source_instance_readback/READBACK.json", "design/source_instance_readback/ARCHIVE_READBACK.json",
             "design/source_instance_readback/source_manifest_body.json", "design/source_instance_readback/source_head_representation.zip",
             "design/SOURCE_ENTRY_PARITY_CONTROLS.json",
             "design/source_instance_readback/SOURCE_PARSER_READBACK.json"]
    names.extend(p.relative_to(OUT).as_posix() for p in sorted((OUT / "tools").glob("*.py")))
    result = {name: digest(OUT / name) for name in names}
    # A new diagnostic run does not change the model. Actual code, Registry,
    # schema resources and fixtures do. Supporting run records are pinned
    # explicitly in each review's review_evidence and checked on retention.
    for base in ("src", "build", "tests"):
        for path in sorted((ROOT / base).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                result["implementation/" + path.relative_to(ROOT).as_posix()] = digest(path)
    for name in ("requirements-f2.lock", "pyproject.toml", "pytest.ini", "setup.cfg", "conftest.py"):
        if (ROOT / name).is_file():
            result["implementation/" + name] = digest(ROOT / name)
    result["execution_environment"] = hashlib.sha256(canonical({"python": sys.version, "platform": sys.platform})).hexdigest()
    return result


def named_section(text, heading):
    match = re.search(r"^" + re.escape(heading) + r"\s*$", text, re.MULTILINE)
    if match is None:
        raise AssertionError(("APPROVED_PROPOSAL_SECTION_MISSING", heading))
    level = len(heading.split(" ", 1)[0])
    following = re.search(r"^#{1," + str(level) + r"} ", text[match.end():], re.MULTILINE)
    end = match.end() + following.start() if following else len(text)
    return text[match.start():end].strip()


def proposal_sources(key):
    """Retain approved prose, not only the graph's condensed contract row."""
    approval_path = ROOT / "docs/R5_4_2/OWNER_R5_4_2_SEMANTIC_CLOSURE_APPROVAL.json"
    approval = read(approval_path)
    assert approval["decision"] == "APPROVED_FOR_VERSIONED_SUCCESSOR_MATERIALIZATION"
    approved = {entry["file"]: entry for entry in approval["approved_artifacts"]}
    package = "docs/R5_4_2/R5_4_2_OWNER_DECISION_PACKAGE.md"
    separate = {
        "assurance_claim_set/1": "docs/R5_4_2/R5_4_2_ASSURANCE_CLAIM_SET_CONTRACT_PROPOSAL.md",
        "public_conclusion_statement/1": "docs/R5_4_2/R5_4_2_PUBLIC_CONCLUSION_CONTRACT_PROPOSAL.md",
        "residual_risk/1": "docs/R5_4_2/R5_4_2_RESIDUAL_RISK_CONTRACT_DECISION_PROPOSAL.md",
    }
    sources = []
    for name in dict.fromkeys([package, *([separate[key]] if key in separate else [])]):
        entry = approved[name]
        path = ROOT / name
        assert digest(path) == entry["raw_digest"] and path.stat().st_size == entry["bytes"], ("OWNER_PROPOSAL_DRIFT", name)
        text = path.read_text(encoding="utf-8-sig")
        if name == package:
            sections = ["## 1. Identity, schema and reference rules to approve"]
            if key == "residual_risk/1":
                sections.append("## 3. Residual-risk/finalization no-omission decisions")
            else:
                sections.append("### " + key)
            for section in sections:
                sources.append({"file": name, "section": section, "raw_digest": entry["raw_digest"],
                                "complete_section_text": named_section(text, section)})
        else:
            sources.append({"file": name, "section": "COMPLETE_APPROVED_PROPOSAL", "raw_digest": entry["raw_digest"],
                            "complete_section_text": text})
    return sources, {"file": approval_path.relative_to(ROOT).as_posix(), "raw_digest": digest(approval_path),
                     "decision": approval["decision"], "scope": "Semantic model/materialization approval only; no runtime activation"}


def main():
    preserve()
    previous_path = OUT / "design/SEMANTIC_OBLIGATION_QUEUE.json"
    previous_queue = read(previous_path) if previous_path.exists() else {"nodes": []}
    previous = {n["source_key"]: n for n in previous_queue["nodes"]}
    dependencies = review_dependencies()
    graph = read(OUT / "OWN_REFERENCE_RESOLUTIONS.json")
    mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
    records = []
    for node in graph["nodes"]:
        source = node.get("source_section") or {}
        sources, authorization = ([source], None) if source else proposal_sources(node["key"])
        if not source:
            source = sources[0]
        obligations = []
        for item in sources:
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", item.get("complete_section_text", "")) if p.strip()]
            for text in paragraphs:
                obligations.append({"paragraph_ordinal": len(obligations), "text": text, "review": "PENDING",
                                    "source_file": item["file"], "source_section": item["section"],
                                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
        inherited = (node.get("approved_specific_registry_row") or {}).get("row") or node.get("qualified_registry_row") or node.get("historical_proposal") or {}
        record = {"source_key": node["key"], "design_key": mapping[node["key"]],
                        "canonical_role": inherited.get("canonical_role"),
                        "producer_authority": inherited.get("producer_authority"),
                        "validation_profile": inherited.get("validation_profile"),
                        "normative_source": {k: source[k] for k in ("file", "section", "raw_digest") if k in source},
                        "source_paragraphs": obligations,
                        "approved_proposal_contract": node.get("historical_proposal"),
                        "actual_material_refs": node["resolved_own_material_refs"],
                        "review": "PENDING_EXACT_SOURCE_BODY_PROFILE_PREDICATE_PARITY",
                        "review_dimensions": ["producer_authority", "reference_targets", "reference_cardinality", "reference_ordering",
                                              "cut_visibility", "campaign_source_scope", "purpose_dispatch", "raw_derivation",
                                              "fsm_eligibility", "uniqueness_retry_conflict", "revision_supersession",
                                              "consumer_applicability", "no_omission", "failure_precedence", "migration"]}
        if authorization is not None:
            record["semantic_model_authorization"] = authorization
            record["supplemental_source_sections"] = [{k: value for k, value in item.items() if k != "complete_section_text"}
                                                       for item in sources[1:]]
        body_path = OUT / "design/body_grammars" / (record["design_key"].replace("/", "__") + ".json")
        if not body_path.exists():
            from execution import BASE
            body_path = BASE / "candidate/schemas" / (node["key"].replace("/", "__") + ".schema.json")
        inputs = {"record": record, "body_digest": digest(body_path), "dependencies": dependencies,
                  "source_digest": digest(ROOT / source["file"]) if source.get("file") else None,
                  "owner_decisions_digest": digest(ROOT / "docs/R5_4_2/OWNER_DELEGATED_DECISION_REGISTER.md")}
        record["review_input_digest"] = hashlib.sha256(canonical(inputs)).hexdigest()
        records.append(retain_review(record, previous.get(node["key"])))
    write("design/SEMANTIC_OBLIGATION_QUEUE.json", {
        "inventory_digest": hashlib.sha256(canonical(records)).hexdigest(), "nodes": records,
        "pending_nodes": [r["design_key"] for r in records if r["review"] != "SEMANTIC_PARITY_REVIEWED"], "fixed_point_reached": False,
        "claim": "Review queue; source retention is not semantic parity, qualification or canonical execution evidence"})
    print({"review_nodes": len(records), "source_paragraphs_retained": sum(len(r["source_paragraphs"]) for r in records),
           "fixed_point_reached": False})


if __name__ == "__main__":
    main()

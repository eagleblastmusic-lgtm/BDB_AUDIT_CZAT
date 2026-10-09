"""Preserve source obligations as explicit, nonqualified semantic work items.

Inventory is deliberately not approval: every source paragraph is retained,
including ones without modal words. Pattern discovery cannot establish parity.
"""

from __future__ import annotations

import ast
import copy
from functools import lru_cache
import hashlib
import json
import re
import sys

from execution import OUT, ROOT, canonical, digest, preserve, read, write


SHARED_RUNTIME_INPUTS = (
    "src/bdb_audit/core/canonical_json.py", "src/bdb_audit/core/hashing.py",
    "src/bdb_audit/core/registry.py", "src/bdb_audit/core/ids.py",
    "src/bdb_audit/schemas/binding.py", "src/bdb_audit/schemas/bootstrap.py",
    "src/bdb_audit/history/objects.py", "src/bdb_audit/history/closure.py",
    "src/bdb_audit/history/store.py", "src/bdb_audit/history/authority_hooks.py",
    "requirements-f2.lock", "pyproject.toml",
)

REVIEW_FIELDS = ("review", "review_evidence", "review_notes", "dimension_reviews", "retention_scope")


@lru_cache(maxsize=512)
def python_import_requests(raw):
    requests = []
    for item in ast.walk(ast.parse(raw)):
        if isinstance(item, ast.Import):
            requests.extend((alias.name, 0, ()) for alias in item.names)
        elif isinstance(item, ast.ImportFrom):
            requests.append((item.module or "", item.level,
                             tuple(alias.name for alias in item.names if alias.name != "*")))
    return tuple(requests)


def local_python_input_closure(names):
    """Necessary local import closure, without importing or executing subjects.

    Dynamic dispatch and non-code inputs still need explicit proof manifests;
    this rejects omission of statically visible code dependencies.
    """
    root = ROOT.resolve()
    pending = [(ROOT / name).resolve() for name in names if name.endswith(".py")]
    found = {}
    resolved = set()

    def include_module(path):
        if path in resolved:
            return
        resolved.add(path)
        for candidate in (path.with_suffix(".py"), path / "__init__.py"):
            if candidate.is_file() and candidate.resolve().is_relative_to(root):
                pending.append(candidate.resolve())

    while pending:
        path = pending.pop()
        name = path.relative_to(root).as_posix()
        if name in found:
            continue
        raw = path.read_bytes()
        found[name] = hashlib.sha256(raw).hexdigest()
        parent = path.parent
        while parent.is_relative_to(root) and parent != root:
            initializer = parent / "__init__.py"
            if initializer.is_file():
                pending.append(initializer.resolve())
            parent = parent.parent
        for module, level, aliases in python_import_requests(raw):
            if level:
                base = path.parent
                for _ in range(level - 1):
                    base = base.parent
                bases = (base,)
            else:
                bases = (path.parent, ROOT / "src", ROOT)
            for base in bases:
                target = base.joinpath(*module.split("."))
                include_module(target)
                for alias in aliases:
                    include_module(target / alias)
    return found


def declared_review_evidence(previous):
    """Include every explicit proof, including dimension/paragraph witnesses.

    A parent proof does not supersede a separately declared dependency. Bare
    dimension/source verdicts remain covered by the parent review's proof;
    once a child declares evidence its exact bytes must also remain current.
    """
    dimensions = previous.get("dimension_reviews", {})
    paragraphs = previous.get("source_paragraphs", [])
    if not isinstance(dimensions, dict) or not isinstance(paragraphs, list):
        return None
    result = []
    for group in (previous, *dimensions.values(), *paragraphs):
        if not isinstance(group, dict) or not isinstance(group.get("review_evidence", []), list):
            return None
        result.extend(group.get("review_evidence", []))
    return result


def evidence_is_bound(previous):
    reviewed = not previous.get("review", "PENDING").startswith("PENDING") or any(
        not paragraph.get("review", "PENDING").startswith("PENDING")
        for paragraph in previous.get("source_paragraphs", ()))
    proofs = declared_review_evidence(previous)
    if proofs is None:
        return False
    if reviewed and not previous.get("review_evidence"):
        return False
    if not proofs:
        return not reviewed
    if not isinstance(proofs, list):
        return False
    bound_inputs = set()
    for proof in proofs:
        if not isinstance(proof, dict) or not isinstance(proof.get("file"), str):
            return False
        path = (ROOT / proof["file"]).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
            return False
        if digest(path) != proof.get("raw_digest"):
            return False
        inputs = proof.get("inputs", {})
        if previous.get("review") == "SEMANTIC_PARITY_REVIEWED" and not inputs:
            return False
        if not isinstance(inputs, dict):
            return False
        bound_inputs.update(inputs)
        for name, expected in inputs.items():
            if not isinstance(name, str):
                return False
            dependency = (ROOT / name).resolve()
            if not dependency.is_relative_to(ROOT.resolve()) or not dependency.is_file() or digest(dependency) != expected:
                return False
    if previous.get("review") == "SEMANTIC_PARITY_REVIEWED":
        required = {name for name in SHARED_RUNTIME_INPUTS if (ROOT / name).is_file()}
        if not required.issubset(bound_inputs):
            return False
        if not set(local_python_input_closure(bound_inputs)).issubset(bound_inputs):
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
    if not same:
        # A narrow primitive witness can stay useful while its consumer's full
        # applicability changes. Retain only explicitly partial, independently
        # bound evidence; PASS/N/A dimensions never cross a changed review.
        for name, dimension in previous.get("dimension_reviews", {}).items():
            if not isinstance(dimension, dict):
                continue
            proofs = dimension.get("review_evidence", [])
            if (dimension.get("verdict") != "PARTIAL_WITH_EVIDENCE" or not dimension.get("source_reason")
                    or not proofs or not isinstance(proofs, list)
                    or any(not isinstance(proof, dict) or not isinstance(proof.get("inputs"), dict)
                           or not proof["inputs"] for proof in proofs)):
                continue
            inputs = {key: value for proof in proofs for key, value in proof["inputs"].items()}
            if (evidence_is_bound({"review": "PARTIAL_DIMENSION_REVIEWED", "review_evidence": proofs})
                    and set(local_python_input_closure(inputs)).issubset(inputs)):
                partial = copy.deepcopy(dimension)
                partial["retention_scope"] = "EXACT_BOUND_WITNESS_ONLY; CONSUMER_APPLICABILITY_AND_FULL_PARITY_PENDING"
                record.setdefault("dimension_reviews", {})[name] = partial
    # Static source interpretation has a narrower contract than model/runtime
    # parity. Preserve exact text/evidence as explicitly partial interpretation;
    # never inherit complete review or complete dimensions across changed inputs.
    historical = previous.get("invalidated_review", previous)
    paragraphs = {p["paragraph_ordinal"]: p for p in historical.get("source_paragraphs", [])}
    for paragraph in record.get("source_paragraphs", []):
        old = paragraphs.get(paragraph["paragraph_ordinal"], {})
        if (paragraph.get("review", "PENDING") == "PENDING"
            and old.get("review") == "SOURCE_REQUIREMENT_MAPPED_OPEN_PROOFS"
            and all(old.get(field) == paragraph.get(field) for field in ("text_sha256", "source_file", "source_section"))
            and old.get("review_evidence") and evidence_is_bound(old)):
            for field in REVIEW_FIELDS:
                if field in old and field != "dimension_reviews":
                    paragraph[field] = copy.deepcopy(old[field])
            paragraph["retention_scope"] = "EXACT_SOURCE_INTERPRETATION_ONLY; MODEL_AND_RUNTIME_PARITY_PENDING"
    for paragraph in record.get("source_paragraphs", []):
        if paragraph.get("review") == "SOURCE_REQUIREMENT_MAPPED_OPEN_PROOFS":
            paragraph["retention_scope"] = "EXACT_SOURCE_INTERPRETATION_ONLY; MODEL_AND_RUNTIME_PARITY_PENDING"
    if not record.get("review_evidence"):
        proofs = {}
        for paragraph in record.get("source_paragraphs", []):
            for proof in paragraph.get("review_evidence", []):
                proofs[canonical(proof)] = proof
        if proofs:
            record["review_evidence"] = [copy.deepcopy(proofs[key]) for key in sorted(proofs)]
    return record


def semantic_tool_closure(seeds):
    """Bind local imported generator code, not every diagnostic entry point."""
    pending = list(seeds)
    result = {}
    while pending:
        name = pending.pop()
        if name in result:
            continue
        path = OUT / "tools" / (name + ".py")
        if not path.is_file():
            raise ValueError("MISSING_SEMANTIC_TOOL:" + name)
        result[name] = digest(path)
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for item in ast.walk(tree):
            imports = ([item.module] if isinstance(item, ast.ImportFrom) and item.module
                       else [alias.name for alias in item.names] if isinstance(item, ast.Import) else [])
            pending.extend(module for module in imports
                           if (OUT / "tools" / (module + ".py")).is_file())
    return result


def scoped_review_dependencies(node, graph, mapping, profiles, model_inputs):
    """Exact transitive model slices plus explicitly declared shared contracts.

    Runtime proofs bind their own source/fixture/verifier inputs independently.
    No diagnostic report or broad source/test directory is a semantic input.
    Registry target-domain changes remain genuinely global: all schemas embed
    that finite domain. Shared authority documents retain conservative edges.
    """
    file_cache = model_inputs.get("file_digests", {})
    def exact_file(path):
        name = path.relative_to(ROOT).as_posix()
        if name not in file_cache:
            file_cache[name] = digest(path)
        return file_cache[name]
    node_hashes = model_inputs.get("node_hashes", {})
    profile_hashes = model_inputs.get("profile_hashes", {})
    field_hashes = model_inputs.get("field_domain_hashes")
    if field_hashes is None:
        fields_by_owner = {}
        for field in model_inputs["field_domains"]["fields"]:
            fields_by_owner.setdefault(field["owner"], []).append(field)
        field_hashes = {key: hashlib.sha256(canonical(fields)).hexdigest() for key, fields in fields_by_owner.items()}
    by_key = {item["key"]: item for item in graph["nodes"]}
    inverse = {value: key for key, value in mapping.items()}
    pending = [node["key"]]
    reachable = {}
    profile_names = set()
    while pending:
        key = pending.pop()
        if key in reachable:
            continue
        if key not in by_key:
            raise ValueError("UNCLASSIFIED_CANONICAL_DEPENDENCY:" + key)
        item = by_key[key]
        reachable[key] = item
        for ref in item["resolved_own_material_refs"]:
            pending.extend(inverse.get(target, target) for target in ref.get("allowed_keys", []))
            profile_names.update(ref.get("profile_contracts", []))
        profile = (item.get("qualified_registry_row") or item.get("historical_proposal") or {}).get("validation_profile")
        if profile in profiles:
            profile_names.add(profile)
    by_wire = {value.get("wire_profile_id", name): name for name, value in profiles.items()}
    profile_refs = model_inputs["profile_references"]["material_refs"]
    payload_refs = model_inputs["payload_references"]["material_refs"]
    selected_profiles = {}
    pending_profiles = list(profile_names)
    while pending_profiles:
        name = pending_profiles.pop()
        name = by_wire.get(name, name)
        if name in selected_profiles:
            continue
        if name not in profiles:
            raise ValueError("UNCLASSIFIED_PROFILE_DEPENDENCY:" + name)
        selected_profiles[name] = profiles[name]
        pending_profiles.extend(profiles[name].get("dependencies", []))
        for ref in profile_refs + payload_refs:
            if ref["owner"] == name:
                pending_profiles.extend(target for target in ref.get("targets", [])
                                        if target in profiles or target in by_wire)
    source_bindings = {}
    body_bindings = {}
    from execution import BASE
    for key, item in reachable.items():
        path = OUT / "design/body_grammars" / (mapping[key].replace("/", "__") + ".json")
        if not path.is_file():
            path = BASE / "candidate/schemas" / (key.replace("/", "__") + ".schema.json")
        body_bindings[key] = exact_file(path)
        source = item.get("source_section")
        if source and source.get("file"):
            source_bindings[source["file"]] = exact_file(ROOT / source["file"])
    shared_names = (
        "design/COMMON_BODY_GRAMMARS.md", "design/COMMON_GRAMMARS.json",
        "design/PURPOSE_CONTRACT_GRAMMARS.json", "design/PURPOSE_PREDICATE_CONTRACTS.md",
        "design/FULL_PATH_TRANSITION_TABLE.json", "design/COMMAND_EVENT_CONTRACT.md",
        "design/HISTORY_CUT_SEMANTIC_REVIEW.md", "design/BOOTSTRAP_PRECEDENCE_SUCCESSOR.json",
        "design/REGISTRY_BOOTSTRAP_SUCCESSOR_DELTA.json", "design/BUILD_INSTALLATION_CONTEXT_REVIEW.md",
        "design/BUILD_INPUT_CLOSURE_SEMANTIC_REVIEW.md", "design/COMMAND_CLOSURE_SEMANTIC_REVIEW.md",
        "design/SOURCE_IDENTITY_SEMANTIC_REVIEW.md", "design/SOURCE_ALIAS_AUTHORITY_SEMANTIC_REVIEW.md",
        "design/SCOPE_EXCLUSION_SEMANTIC_REVIEW.md")
    return {
        "binding_version": 2,
        "transitive_canonical_nodes": {key: node_hashes[key] if key in node_hashes else hashlib.sha256(canonical(value)).hexdigest() for key, value in reachable.items()},
        "transitive_body_bytes": body_bindings,
        "normative_source_bytes": source_bindings,
        "finite_registry_domain": mapping,
        "transitive_profiles": {name: profile_hashes[name] if name in profile_hashes else hashlib.sha256(canonical(value)).hexdigest() for name, value in selected_profiles.items()},
        "profile_reference_edges": [ref for ref in profile_refs if ref["owner"] in selected_profiles],
        "payload_reference_edges": [ref for ref in payload_refs if ref["owner"] in selected_profiles],
        "field_domains": {key: field_hashes[key] for key in reachable if key in field_hashes},
        "shared_authority_contracts": {name: exact_file(OUT / name) for name in shared_names},
        "semantic_generator_import_closure": model_inputs["semantic_tools"],
        "execution_environment": {"python": sys.version, "platform": sys.platform},
        "dependencies_complete_for": "STATIC_SOURCE_BODY_PROFILE_MODEL_ONLY; runtime proofs require exact input manifests",
    }


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


def conditional_inventory(graph, mapping, declared):
    expected = []
    for node in graph["nodes"]:
        for material in node["resolved_own_material_refs"]:
            if material["cardinality"] not in ("1", "0..1", "0..65536", "1..65536", "2..65536", "1..256"):
                expected.append({"owner": node["key"], "design_key": mapping[node["key"]],
                                 "field": material["field"], "declared": material["cardinality"],
                                 "status": "REQUIRES_EXPLICIT_CONDITION_OR_SEMANTIC_PREDICATE"})
    if sorted(map(canonical, expected)) != sorted(map(canonical, declared)):
        raise ValueError("CONDITIONAL_INVENTORY_GRAPH_MISMATCH")
    return expected


def fixed_point_status(records, closure, required_keys=None, required_obligations=None):
    """Check explicit closure proofs; missing declarations fail closed.

    A reviewed label alone cannot establish coverage or conditional closure.
    The caller must supply independently produced graph/schema/fixture/drift
    evidence, with exact files checked by evidence_is_bound.
    """
    failures = []
    bound_groups = {}

    def bound(record):
        group = {"review": record["review"], "review_evidence": declared_review_evidence(record)}
        key = canonical(group)
        if key not in bound_groups:
            bound_groups[key] = (group, evidence_is_bound(group))
        return bound_groups[key][1]
    if len(records) != 131 or len({r.get("source_key") for r in records}) != 131:
        failures.append("INCOMPLETE_OR_DUPLICATE_COVERAGE")
    if required_keys is not None and {r.get("source_key") for r in records} != set(required_keys):
        failures.append("REQUIRED_KEY_SET_MISMATCH")
    current_inputs = {r.get("source_key"): r.get("review_input_digest") for r in records}
    for record in records:
        if record.get("review") != "SEMANTIC_PARITY_REVIEWED" or not bound(record):
            failures.append("UNREVIEWED_OR_UNBOUND:" + str(record.get("source_key")))
        if any(p.get("review") != "REVIEWED" for p in record.get("source_paragraphs", [])):
            failures.append("PENDING_PARAGRAPHS:" + str(record.get("source_key")))
        dimensions = record.get("dimension_reviews", {})
        if not isinstance(dimensions, dict) or any(
            not isinstance(dimensions.get(name), dict)
            or dimensions[name].get("verdict") not in ("PASS", "NOT_APPLICABLE")
            or not dimensions[name].get("source_reason")
            for name in record.get("review_dimensions", [])
        ):
            failures.append("INCOMPLETE_DIMENSIONS:" + str(record.get("source_key")))
    required = ("graph_complete", "conditional_obligations_closed", "schemas_bound",
                "fixtures_bound", "zero_input_drift", "no_material_contradictions")
    for name in required:
        proof = closure.get(name, {})
        if not isinstance(proof, dict) or proof.get("verdict") != "PASS" or not proof.get("review_evidence"):
            failures.append("MISSING_CLOSURE_PROOF:" + name)
        elif proof.get("review_input_digests") != current_inputs:
            failures.append("STALE_CLOSURE_INPUTS:" + name)
        elif not bound({**proof, "review": "SEMANTIC_PARITY_REVIEWED"}):
            failures.append("UNBOUND_CLOSURE_PROOF:" + name)
    # A bound aggregate PASS cannot hide omitted or merely shape-reviewed
    # conditional obligations. Check the exact inventoried dispositions.
    if required_obligations is None:
        failures.append("MISSING_CONDITIONAL_INVENTORY")
    else:
        expected = {hashlib.sha256(canonical(item)).hexdigest(): item for item in required_obligations}
        if len(expected) != len(required_obligations):
            failures.append("DUPLICATE_CONDITIONAL_INVENTORY")
        conditional_proof = closure.get("conditional_obligations_closed", {})
        declarations = conditional_proof.get("obligations", []) if isinstance(conditional_proof, dict) else None
        if not isinstance(declarations, list) or any(not isinstance(item, dict) for item in declarations):
            failures.append("INVALID_CONDITIONAL_DISPOSITIONS")
        elif (len(declarations) != len(expected)
              or {item.get("id") for item in declarations} != set(expected)):
            failures.append("INCOMPLETE_OR_DUPLICATE_CONDITIONAL_DISPOSITIONS")
        else:
            for item in declarations:
                obligation = expected[item["id"]]
                owner = obligation["owner"]
                if (item.get("owner") != owner or owner not in current_inputs
                    or item.get("review_input_digest") != current_inputs[owner]
                    or item.get("disposition") not in ("CLOSED", "NOT_APPLICABLE")
                    or not item.get("source_reason")
                    or not item.get("review_evidence")
                    or not bound({**item, "review": "CONDITIONAL_REVIEWED"})):
                    failures.append("UNRESOLVED_OR_UNBOUND_CONDITIONAL:" + item["id"])
    # Share a genuinely identical proof group within this invocation, then
    # reread exact bytes/import closure. Never cache validity across executions.
    if any(was_bound and not evidence_is_bound(group) for group, was_bound in bound_groups.values()):
        failures.append("EVIDENCE_INPUT_DRIFT_DURING_FIXED_POINT")
    return {"reached": not failures, "failures": failures}


def main():
    preserve()
    previous_path = OUT / "design/SEMANTIC_OBLIGATION_QUEUE.json"
    previous_queue = read(previous_path) if previous_path.exists() else {"nodes": []}
    if previous_path.exists():
        raw = previous_path.read_bytes()
        historical = OUT / "checkpoint_history/semantic_reviews" / (hashlib.sha256(raw).hexdigest() + ".json")
        historical.parent.mkdir(parents=True, exist_ok=True)
        if historical.exists() and historical.read_bytes() != raw:
            raise ValueError("IMMUTABLE_REVIEW_HISTORY_DRIFT")
        if not historical.exists():
            historical.write_bytes(raw)
    previous = {n["source_key"]: n for n in previous_queue["nodes"]}
    binding_paths = ("OWN_REFERENCE_RESOLUTIONS.json", "design/VERSION_IMPACT_PLAN.json",
                     "design/EXTERNAL_PROFILE_CONTRACTS.json", "design/PROFILE_REFERENCE_CONTRACTS.json",
                     "design/PAYLOAD_REFERENCE_CONTRACTS.json", "design/OWN_FIELD_DOMAINS.json",
                     "design/CARDINALITY_AUDIT.json")
    file_cache = {(OUT / name).relative_to(ROOT).as_posix(): digest(OUT / name) for name in binding_paths}
    graph = read(OUT / "OWN_REFERENCE_RESOLUTIONS.json")
    mapping = read(OUT / "design/VERSION_IMPACT_PLAN.json")["mapping"]
    profiles = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
    model_inputs = {
        "profile_references": read(OUT / "design/PROFILE_REFERENCE_CONTRACTS.json"),
        "payload_references": read(OUT / "design/PAYLOAD_REFERENCE_CONTRACTS.json"),
        "field_domains": read(OUT / "design/OWN_FIELD_DOMAINS.json"),
        "semantic_tools": semantic_tool_closure(("semantic_inventory", "reference_resolution", "version_impact",
                                                "body_grammar_frontier", "profile_contracts", "purpose_contracts",
                                                "common_grammars", "event_grammars", "transition_contract")),
    }
    model_inputs["file_digests"] = file_cache
    model_inputs["node_hashes"] = {node["key"]: hashlib.sha256(canonical(node)).hexdigest() for node in graph["nodes"]}
    fields_by_owner = {}
    for field in model_inputs["field_domains"]["fields"]:
        fields_by_owner.setdefault(field["owner"], []).append(field)
    model_inputs["field_domain_hashes"] = {key: hashlib.sha256(canonical(fields)).hexdigest() for key, fields in fields_by_owner.items()}
    model_inputs["profile_hashes"] = {name: hashlib.sha256(canonical(value)).hexdigest() for name, value in profiles.items()}
    records = []
    for node in graph["nodes"]:
        dependencies = scoped_review_dependencies(node, graph, mapping, profiles, model_inputs)
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
        record["review_dependency_bindings"] = dependencies
        records.append(retain_review(record, previous.get(node["key"])))
    drift = [name for name, expected in file_cache.items() if digest(ROOT / name) != expected]
    if drift:
        raise ValueError("SEMANTIC_REVIEW_INPUT_DRIFT:" + repr(drift))
    closure_path = OUT / "design/SEMANTIC_CLOSURE_PROOFS.json"
    closure = read(closure_path) if closure_path.exists() else {}
    required_obligations = conditional_inventory(
        graph, mapping, read(OUT / "design/CARDINALITY_AUDIT.json")["conditional_obligations"])
    fixed_point = fixed_point_status(records, closure, [node["key"] for node in graph["nodes"]], required_obligations)
    write("design/SEMANTIC_OBLIGATION_QUEUE.json", json.loads(canonical({
        "inventory_digest": hashlib.sha256(canonical(records)).hexdigest(), "nodes": records,
        "pending_nodes": [r["design_key"] for r in records if r["review"] != "SEMANTIC_PARITY_REVIEWED"], "fixed_point_reached": fixed_point["reached"], "fixed_point_failures": fixed_point["failures"],
        "claim": "Review queue; source retention is not semantic parity, qualification or canonical execution evidence"})))
    print({"review_nodes": len(records), "source_paragraphs_retained": sum(len(r["source_paragraphs"]) for r in records),
           "fixed_point_reached": fixed_point["reached"]})


if __name__ == "__main__":
    main()

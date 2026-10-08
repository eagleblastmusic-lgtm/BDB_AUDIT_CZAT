"""Record fresh draft verification commands, exit codes, inputs and durations.

This deliberately cannot emit a qualification record or promote a gate.
"""

from __future__ import annotations

import importlib.metadata
import subprocess
import sys
import time

from execution import OUT, ROOT, digest, git, preserve, read, write


def verification_inputs():
    paths = set((OUT / "tools").glob("*.py"))
    for directory in ("src", "build", "tests"):
        paths.update(path for path in (ROOT / directory).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    paths.update(ROOT / name for name in ("requirements-f2.lock", "pyproject.toml", "pytest.ini", "setup.cfg", "conftest.py")
                 if (ROOT / name).is_file())
    paths.update((OUT / "design/body_grammars").glob("*.json"))
    for name in ("OWN_REFERENCE_RESOLUTIONS.json", "design/VERSION_IMPACT_PLAN.json",
                 "design/OWN_FIELD_DOMAINS.json", "design/COMMON_GRAMMARS.json",
                 "design/EXTERNAL_PROFILE_CONTRACTS.json", "design/PROFILE_REFERENCE_CONTRACTS.json",
                 "design/PAYLOAD_REFERENCE_CONTRACTS.json", "design/PURPOSE_CONTRACT_GRAMMARS.json",
                 "design/FULL_PATH_TRANSITION_TABLE.json", "design/COMMON_BODY_GRAMMARS.md",
                 "design/PURPOSE_PREDICATE_CONTRACTS.md", "design/COMMAND_EVENT_CONTRACT.md"):
        if (OUT / name).is_file():
            paths.add(OUT / name)
    paths.add(ROOT / "docs/R5_4_2/OWNER_DELEGATED_DECISION_REGISTER.md")
    approval = ROOT / "docs/R5_4_2/OWNER_R5_4_2_SEMANTIC_CLOSURE_APPROVAL.json"
    if approval.is_file():
        paths.add(approval)
    return {path.relative_to(ROOT).as_posix(): digest(path) for path in sorted(paths)}


def main():
    preserve()
    inputs_before = verification_inputs()
    baseline = read(OUT / "PRESERVATION_BASELINE.json")
    production_drift = [name for name, expected in baseline["initial_implementation_files"].items() if digest(ROOT / name) != expected]
    delta_path = OUT / "AUTHORIZED_IMPLEMENTATION_DELTA.json"
    delta = read(delta_path) if delta_path.exists() else {"files": {}}
    assert set(production_drift) == set(delta["files"]), production_drift
    assert all(digest(ROOT / name) == entry["current_raw_digest"] and baseline["initial_implementation_files"][name] == entry["baseline_raw_digest"] for name, entry in delta["files"].items())
    assert all(name not in baseline["initial_implementation_files"] and digest(ROOT / name) == entry["current_raw_digest"]
               for name, entry in delta.get("new_files", {}).items())
    commands = []
    for name in ("execution", "test_design_runtime_environment", "test_runtime_evidence_drift", "test_semantic_queue_retention", "verify_generated_design", "bootstrap_precedence_design", "bootstrap_registry_integration", "build_context_design", "bootstrap_instance_design", "closure_tiebreak_audit", "source_identity_design", "source_alias_durable_controls", "source_entry_parity", "scope_exclusion_design", "cardinality_audit", "conditional_grammar_audit", "material_path_audit", "exhaustive_reference_audit", "profile_design_audit", "semantic_obligation_queue"):
        commands.append([sys.executable, str(OUT / "tools" / (name + ".py"))])
    commands.extend([[sys.executable, "-m", "ruff", "check", str(OUT / "tools")], ["git", "diff", "--check"]])
    commands.append([sys.executable, str(OUT / "tools/test_initial_context_chronology.py")])
    commands.insert(5, [sys.executable, str(OUT / "tools/test_build_time_candidates.py")])
    commands.insert(6, [sys.executable, str(OUT / "tools/registry_build_candidate.py")])
    commands.insert(7, [sys.executable, str(OUT / "tools/test_registry_build_candidate.py")])
    commands.insert(8, [sys.executable, str(OUT / "tools/build_time_candidates.py")])
    commands.insert(9, [sys.executable, str(OUT / "tools/schema_registry_build_candidate.py")])
    commands.insert(10, [sys.executable, str(OUT / "tools/test_schema_registry_build_candidate.py")])
    commands.insert(11, [sys.executable, str(OUT / "tools/build_schema_fixtures.py")])
    commands.insert(12, [sys.executable, str(OUT / "tools/test_build_schema_fixtures.py")])
    commands.insert(13, [sys.executable, str(OUT / "tools/test_draft_verification_drift.py")])
    commands.insert(14, [sys.executable, str(OUT / "tools/golden_build_candidate.py")])
    commands.insert(15, [sys.executable, str(OUT / "tools/test_golden_build_candidate.py")])
    commands.insert(16, [sys.executable, str(OUT / "tools/normative_build_candidate.py")])
    commands.insert(17, [sys.executable, str(OUT / "tools/test_normative_build_candidate.py")])
    commands.insert(11, [sys.executable, str(OUT / "tools/initial_protocol_build_candidate.py")])
    commands.insert(12, [sys.executable, str(OUT / "tools/test_initial_protocol_build_candidate.py")])
    commands.append([sys.executable, str(OUT / "tools/purpose_dispatch_design.py")])
    commands.insert(11, [sys.executable, str(OUT / "tools/source_profile_build_candidate.py")])
    commands.insert(12, [sys.executable, str(OUT / "tools/test_source_profile_build_candidate.py")])
    commands.append([sys.executable, str(OUT / "tools/test_purpose_input_domains.py")])
    commands.append([sys.executable, str(OUT / "tools/application_source_snapshot.py")])
    commands.append([sys.executable, str(OUT / "tools/test_application_source_snapshot.py")])
    results = []
    for command in commands:
        started = time.monotonic()
        result = subprocess.run(command, cwd=ROOT, capture_output=True, encoding="utf-8", errors="strict")
        entry = {"argv": command, "exit_code": result.returncode, "duration_seconds": round(time.monotonic() - started, 6),
                 "result": "PASS" if result.returncode == 0 else "FAIL", "stdout": result.stdout, "stderr": result.stderr}
        results.append(entry)
        print(entry["result"], " ".join(command), flush=True)
        if result.returncode:
            break
    inputs_after = verification_inputs()
    changed = sorted(name for name in inputs_before.keys() | inputs_after.keys()
                     if inputs_before.get(name) != inputs_after.get(name))
    write("DRAFT_VERIFICATION.json", {
        "source_HEAD": git("rev-parse", "HEAD"), "source_tree": git("rev-parse", "HEAD^{tree}"),
        "python": sys.version, "packages": {name: importlib.metadata.version(name) for name in ("jsonschema", "referencing", "ruff")},
        "commands": results, "production_files_verified_unchanged": len(baseline["initial_implementation_files"]) - len(production_drift),
        "authorized_implementation_delta": delta,
        "production_mismatches": production_drift,
        "preservation_baseline_raw_digest": digest(OUT / "PRESERVATION_BASELINE.json"),
        "tool_inputs": {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted((OUT / "tools").glob("*.py"))},
        "verification_inputs_before": inputs_before, "verification_inputs_after": inputs_after,
        "verification_input_drift": changed,
        "owner_delegated_decision_register_raw_digest": digest(ROOT / "docs/R5_4_2/OWNER_DELEGATED_DECISION_REGISTER.md"),
        "design_outputs": {p.relative_to(OUT).as_posix(): digest(p) for p in sorted((OUT / "design").rglob("*")) if p.is_file()},
        "qualification": False, "candidate_materialized": False, "Q1": "NOT_STARTED", "Q2": "NOT_STARTED", "N5_N11": "NOT_STARTED",
        "NF02": "OPEN", "unexecuted_required_gates": ["semantic predicate parity", "qualified schema fixture execution", "Q1", "Q2", "N5-N11", "required runtime pytest", "mypy", "build", "artifact validator"],
        "repository_status": git("status", "--short")})
    assert all(r["exit_code"] == 0 for r in results), "Draft verification failed; no qualification record emitted"
    assert not changed, ("DRAFT_VERIFICATION_INPUT_DRIFT", changed)


if __name__ == "__main__":
    main()

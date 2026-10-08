"""Record an exact normative qualification conflict; never activate or patch it."""
from datetime import datetime, timezone
import json
import shutil
import subprocess

from qualify_exact_candidate import governance_contract_conflicts
from verify_candidate import C, E, REPO, ROOT, canonical, read, run, sha


def main():
    manifest, entries, checks, catalog, sr = run()
    conflicts = governance_contract_conflicts(manifest)
    assert len(conflicts) == 2
    folder = E / 'qualification'
    initial_report = ROOT / 'R5_4_GOVERNANCE_QUALIFICATION_REPORT.md'
    archived_report = folder / 'INITIAL_PREMATURE_QUALIFICATION_REPORT_NOT_VALID.md'
    assert not archived_report.exists()
    shutil.copyfile(initial_report, archived_report)
    record = folder / 'AUTHOR_BASELINE_QUALIFICATION_R5_4.json'
    record_raw = sha(record.read_bytes())
    failed_command = subprocess.run(['python', 'docs/R5_4/tools/qualify_exact_candidate.py'], cwd=REPO,
                                    capture_output=True, text=True, encoding='utf-8')
    assert failed_command.returncode == 1 and 'R5_4_AUTHOR_VERDICT_CONTRACT_CONFLICT' in failed_command.stdout
    pin = read(E / 'R5_4_SOURCE_PREDECESSOR_PINS.json')
    candidate = {
        'normative_candidate_set_sha256': manifest['normative_candidate_set_sha256'],
        'machine_candidate_set_sha256': manifest['machine_candidate_set_sha256'],
        'manifest_raw_digest': sha((E / 'BDB_AUDIT_V2_R5_4_MANIFEST_SHA256.json').read_bytes()),
        'schema_registry_object_digest': sr['ref']['revision_digest']}
    assessment = {
        'record_type': 'EXTERNAL_QUALIFICATION_VALIDITY_ASSESSMENT', 'created_at': datetime.now(timezone.utc).isoformat(),
        'qualification_gate': 'R5_4_QUALIFICATION_FAILED', 'final_gate': 'SPEC_CONFLICT',
        'qualification_record_storage_id': str(record), 'qualification_record_raw_digest': record_raw,
        'qualification_record_valid': False, 'derived_author_qualified_implementation_baseline': 'NO_VALID_QUALIFICATION',
        'candidate_identity': candidate, 'candidate_drift': False, 'conflicts': conflicts,
        'owner_author_only_authorization': 'VALID_AND_PRESERVED; cannot reconcile conflicting normative predicates',
        'failure_cause': 'Premature record creation after structural checks without complete governance narrative parity; strict follow-up invalidates its qualification claim.',
        'previous_record_and_checks': 'Preserved as forensic evidence only. Neither their PASS/YES flags nor filename may authorize activation.',
        'activation': 'NOT_RUN', 'N5_N8': 'NOT_STARTED', 'runtime_tests': 'NOT_RUN',
        'source_head': pin['head'], 'source_tree': pin['tree'], 'source_branch': pin['branch'],
        'strict_check_command': {'command': 'python docs/R5_4/tools/qualify_exact_candidate.py',
                                 'exit_code': failed_command.returncode, 'stdout': failed_command.stdout, 'stderr': failed_command.stderr},
        'checker_raw_digest': sha((ROOT / 'tools/qualify_exact_candidate.py').read_bytes()),
        'normative_correction_required': 'Owner-authorized successor exact candidate/governance delta must reconcile §187.2 and §192.2, then new identities and full fresh Q1. Do not edit or activate this exact subject.'}
    invalidation = folder / 'AUTHOR_BASELINE_QUALIFICATION_R5_4_INVALIDATION.json'
    assert not invalidation.exists()
    invalidation.write_bytes(canonical(assessment) + b'\n')
    invalidation_raw = sha(invalidation.read_bytes())
    report = '# R5.4 exact-candidate governance qualification — FAILED\n\n'
    report += 'Q1 gate: **R5_4_QUALIFICATION_FAILED**. Final task gate: **SPEC_CONFLICT**. Q2 and N5–N8 have not started.\n\n'
    report += 'All four user-pinned identities match. Structural/hash/schema self-audit and fresh readback passed, but those checks do not establish governance narrative parity. The exact candidate has two incompatible mandatory predicates for the same successor AuthorBaselineQualificationRecord/2. Owner author-only authorization was obtained explicitly and remains recorded; missing permission is not this blocker.\n\n'
    report += '| Normative source | Requirement | Conflict |\n|---|---|---|\n'
    report += '| Data §187.2, line 5205 | `author_verdict = R5_4_N1_N4_AUTHOR_SELF_AUDIT_PASS`, expressly “successor governance record/2 only” | Cannot equal the different /2 token below |\n'
    report += '| Data §192.2, line 5567 | `author_verdict=R5_4_AUTHOR_NORMATIVE_FINAL_SELF_AUDIT_PASS` | One scalar verdict cannot satisfy both |\n'
    report += '| Data §187.2, line 5220 | `readback_verified_file_count` equals normative manifest file count | Required value 10 |\n'
    report += '| Data §192.2, line 5567 | Same count includes all normative and machine entries | Required value 117 |\n\n'
    report += 'The §187.2 verdict line is already explicitly marked successor /2; it cannot be silently treated as historical record/1. No explicit reconciliation of these /2 requirements occurs in the frozen text. Choosing a preferred predicate or accepting an array/new field instead of the required scalar would silently redefine the contract. The instruction permits qualifying these exact bytes and forbids automatically correcting the candidate.\n\n'
    report += f'Normative set `{candidate["normative_candidate_set_sha256"]}`; machine set `{candidate["machine_candidate_set_sha256"]}`; manifest RawDigest `{candidate["manifest_raw_digest"]}`; SchemaRegistry ObjectDigest `{candidate["schema_registry_object_digest"]}`. Candidate/Data raw SHA-256 `{sha((C / "BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md").read_bytes())}`. No drift.\n\n'
    report += f'Current HEAD `{pin["head"]}`, tree `{pin["tree"]}`, branch `{pin["branch"]}`. Source/predecessor pins remain unchanged. Full initial git commands are in `evidence/qualification/Q1_SOURCE_IDENTITY.json`.\n\n'
    report += '## Fresh checks\n\n'
    report += '- `python docs/R5_4/tools/verify_candidate.py` — exit 0, artifact self-audit only.\n'
    report += '- `python docs/R5_4/tools/finalize_delivery.py` — exit 0, fresh evidence; candidate bytes not generated/edited.\n'
    report += '- 117 candidate readbacks, zero mismatch; 41 schemas, 39 bindings; 149 vectors inventoried, runtime execution NOT_RUN.\n'
    report += '- `python docs/R5_4/tools/qualify_exact_candidate.py` — final strict run exit 1; both normative conflicts detected before any new qualification record is written.\n'
    report += '- Strict-check implementation was corrected to stop before record emission on these conflicts; the original record remains preserved and is invalidated externally. This repair does not change normative predicates.\n\n'
    report += f'## Correction of premature record\n\nThe initial author qualification was emitted before this parity check was complete. Its RawDigest `{record_raw}` is preserved; its YES/PASS claim is invalid and must not be used. External validity assessment `evidence/qualification/AUTHOR_BASELINE_QUALIFICATION_R5_4_INVALIDATION.json`, RawDigest `{invalidation_raw}`, records the rejection and effective NO_VALID_QUALIFICATION. Initial checks/report remain forensic evidence, not authority. No independent assurance, freeze, installation or campaign state change occurred.\n\n'
    report += '## Required resolution\n\nA separately authorized exact successor/correction must specify one /2 verdict token and reconcile total/normative/machine readback fields/counts consistently across §187.2, §192.2 and governance artifacts. This changes candidate bytes and therefore requires a new manifest/set identity and fresh Q1 qualification. This task does not silently amend the pinned candidate or assume authorization to revise it. The owner’s author-only decision does not itself resolve these contract predicates.\n'
    initial_report.write_text(report, encoding='utf-8')
    activation_report = '# R5.4 activation — NOT RUN\n\n'
    activation_report += 'No exact R5.4 authority was installed/activated. Q1 failed with SPEC_CONFLICT; both permissible prerequisite gates remain unsatisfied. Candidate installation bundle remains byte-identical CANDIDATE_PREPARED_NOT_INSTALLED. No “latest”, overlay, generated schema or /1→/2 fallback was used.\n\n'
    activation_report += f'Candidate identities: `{candidate["normative_candidate_set_sha256"]}`, `{candidate["machine_candidate_set_sha256"]}`, manifest `{candidate["manifest_raw_digest"]}`. Invalid attempted qualification record `{record_raw}` is rejected by validity assessment `{invalidation_raw}`. Activation identity: null.\n\n'
    activation_report += 'Old/new campaign activation isolation tests: NOT_RUN because no activation occurred. Runtime and existing campaigns were untouched. Resume only after a legal exact-candidate qualification; consult R5_4_GOVERNANCE_QUALIFICATION_REPORT.md.\n'
    (ROOT / 'R5_4_ACTIVATION_REPORT.md').write_text(activation_report, encoding='utf-8')
    vectors = read(E / 'R5_4_GOLDEN_VECTOR_INVENTORY.json')['vectors']
    verification = {
        'schema': 'BDB_NF02_N5_N8_VERIFICATION/1', 'date': '2026-10-06', 'final_gate': 'SPEC_CONFLICT',
        'qualification_gate': 'R5_4_QUALIFICATION_FAILED', 'source_identity': {'head': pin['head'], 'tree': pin['tree'], 'branch': pin['branch']},
        'candidate_identity': candidate, 'attempted_qualification_record_raw_digest': record_raw,
        'qualification_validity_assessment_raw_digest': invalidation_raw,
        'effective_qualification_record_identity': None, 'activation_identity': None,
        'implementation_status': 'NOT_STARTED_MANDATORY_Q1_STOP', 'changed_runtime_files': [],
        'contract_mapping': 'Approved B/1 E/2 R/2 mapping remains in the candidate; no runtime mapping implemented or tested.',
        'checks': checks, 'conflicts': conflicts,
        'golden_vector_outcomes': [{'id': vector['id'], 'origin': vector['origin'], 'expected': vector['expected'], 'actual': 'NOT_RUN'} for vector in vectors],
        'N5_N8_runtime_tests': 'NOT_RUN', 'affected_regression_suites': 'NOT_RUN', 'full_pytest': 'NOT_RUN',
        'Ruff': 'NOT_RUN_NO_RUNTIME_IMPLEMENTATION', 'Mypy': 'NOT_RUN_NO_RUNTIME_IMPLEMENTATION',
        'build': 'NOT_RUN_NO_RUNTIME_IMPLEMENTATION', 'artifact_validator': 'NOT_RUN_NO_RUNTIME_IMPLEMENTATION',
        'fresh_commands': assessment['strict_check_command'],
        'remaining_risks': ['Frozen governance text cannot admit one /2 record satisfying both mandatory tokens/counts.',
                            'Initial record/technical PASS claims require the explicit invalidity assessment, not unqualified reuse.',
                            'Current remediation still differs from approved R5.4; no runtime qualification or closure.'],
        'N9_entry_conditions': ['Legal exact governance qualification', 'Authenticated exact activation', 'Complete N5-N8 implementation',
                                'All 32 scenarios and affected/full required verification gates passing'],
        'N9_entry_conditions_met': False, 'NF02_closed': False}
    (ROOT / 'NF02_N5_N8_VERIFICATION.json').write_bytes(canonical(verification) + b'\n')
    implementation_report = '# NF02 N5–N8 implementation — NOT STARTED\n\nFinal gate: **SPEC_CONFLICT**. Q1 gate: **R5_4_QUALIFICATION_FAILED**.\n\n'
    implementation_report += f'Source HEAD `{pin["head"]}`, tree `{pin["tree"]}`, branch `{pin["branch"]}`. Exact candidate identity, attempted record identity/invalidation and detailed commands/outcomes are in `NF02_N5_N8_VERIFICATION.json` and the governance report. Effective qualification identity: null; activation identity: null.\n\n'
    implementation_report += 'Changed files in this task: external Q1 qualification/owner decision/source/readback/self-audit evidence, task-specific qualification tools and these reports. No runtime/test/build/candidate/predecessor files were edited. Fresh `finalize_delivery.py` refreshed external N1–N4 evidence as expressly requested; immutable qualification snapshots preserve those exact bytes. Original local remediation edits were preserved.\n\n'
    implementation_report += 'Contract mapping pending: N5 B/1 unique exact assignment/raw authorization; N6 durable package→prior binding→separate STARTED→retained-byte delivery; N7 exact E/2 and Normalize(Q) R/2; N8 new-campaign boundary and historical-only /1. None was implemented because Q1 must precede implementation.\n\n'
    implementation_report += 'All 32 NF02 runtime scenarios, affected Inbox/manual-stage/finalize/history/authority/result/durability/crash/schema/CAS/STOP suites, full `python -m pytest`, Ruff, Mypy, build and artifact validator: NOT_RUN. Their Golden expectations were not changed. No previous 249-test evidence is claimed for R5.4.\n\n'
    implementation_report += 'Remaining blocker is the exact §187.2/§192.2 governance conflict, not a coding/test/environment failure. Candidate correction requires explicit authorized revised bytes/new identities, forbidden to perform automatically in this task. N9 entry conditions are unmet. N9–N11 and NF02 closure are not claimed.\n'
    (ROOT / 'NF02_N5_N8_IMPLEMENTATION_REPORT.md').write_text(implementation_report, encoding='utf-8')
    diff = subprocess.run(['git', 'diff', '--check'], cwd=REPO, capture_output=True, text=True, encoding='utf-8')
    assert diff.returncode == 0
    print(json.dumps({'final_gate': 'SPEC_CONFLICT', 'qualification_gate': 'R5_4_QUALIFICATION_FAILED',
                      'invalid_attempted_record_raw_digest': record_raw, 'validity_assessment_raw_digest': invalidation_raw,
                      'activation': 'NOT_RUN', 'runtime_changes': 0, 'candidate_drift': False,
                      'git_diff_check_exit_code': diff.returncode}, indent=2))


if __name__ == '__main__':
    main()

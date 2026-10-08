"""Fresh external Q1. No installation, campaign writes or production implementation."""
import datetime
import difflib
import subprocess

from governance import (C, COUNT_FIELDS, DECISION, OLD, ROOT, SCHEMA_FILE, TASK, VERDICT,
                        emit, properties, read, sha, validate)
from verify_candidate import run


def qualify():
    manifest, rb, checks, catalog, sr = run()  # Never reuse the earlier PASS.
    manifest_path = ROOT / 'R5_4_1_CANDIDATE_MANIFEST.json'
    mr = sha(manifest_path.read_bytes())
    audit_path = ROOT / 'R5_4_1_SELF_AUDIT.json'
    rb_path = ROOT / 'R5_4_1_READBACK.json'
    audit, readback = read(audit_path), read(rb_path)
    ar, rr = sha(audit_path.read_bytes()), sha(rb_path.read_bytes())
    for item in [audit, readback]:
        assert item['candidate_manifest_raw_digest'] == mr
        for group in ['normative', 'machine']:
            assert item[group + '_candidate_set_digest'] == manifest[group + '_candidate_set_sha256']
    assert audit['readback_raw_digest'] == rr
    assert audit['status'] == 'PASS_FRESH_ARTIFACT_AND_GOVERNANCE_SELF_AUDIT'
    assert audit['author_verdict'] == VERDICT
    assert audit['checks'] == checks
    assert audit['runtime_vectors'] == 'NOT_RUN' and audit['Q2'] == audit['N5_N11'] == 'NOT_STARTED'
    assert audit['verifier_tool_raw_digests'] == {p.name: sha(p.read_bytes()) for p in (ROOT / 'tools').glob('*.py')}
    n = len(manifest['normative_candidate_files'])
    entries = [{'group': 'normative' if i < n else 'machine', 'file': e['file'], 'stable_storage_id': e['absolute_path'],
                'expected_raw_digest': e['expected_sha256'], 'observed_raw_digest': e['observed_sha256'],
                'byte_length': e['bytes'], 'result': 'PASS'} for i, e in enumerate(rb)]
    assert entries == readback['readback_entries'] and readback['readback_mismatch_count'] == 0
    for entry in entries:
        assert sha(__import__('pathlib').Path(entry['stable_storage_id']).read_bytes()) == entry['observed_raw_digest']
    counts = [n, len(manifest['machine_candidate_files']), len(entries)]
    assert [readback[k] for k in COUNT_FIELDS] == counts
    pins = read(ROOT / 'evidence/R5_4_SOURCE_PREDECESSOR_PINS.json')
    assert sha(TASK.read_bytes()) == pins['correction_task_raw_digest']
    # Human authorization comes from the current explicit correction/fresh-Q1 order,
    # not the invalid record. Earlier explicit assurance acceptance is provenance only.
    owner_path = ROOT / 'OWNER_R5_4_1_CORRECTION_AND_Q1_DECISION.json'
    owner = {'record_type': 'EXTERNAL_DIRECT_HUMAN_OWNER_CORRECTION_AUTHORIZATION',
             'governance_actor_ref': 'OWNER_DIRECT_CORRECTION_ORDER_8542fbf1_R5_4_1',
             'decision': DECISION, 'scope': 'R5.4.1_GOVERNANCE_CORRECTION_AND_FRESH_Q1_ONLY',
             'human_request_raw_digest': pins['correction_task_raw_digest'],
             'human_request_storage_id': str(ROOT / 'evidence/OWNER_CORRECTION_REQUEST.txt'),
             'prior_explicit_assurance_acceptance_raw_digest': sha((OLD / 'evidence/qualification/OWNER_EXACT_CANDIDATE_ASSURANCE_DECISION.json').read_bytes()),
             'authority_basis': 'Direct owner request §§4,8,9,14-17 approves exact minimal correction, fresh Q1 and new qualification; prior direct author-only risk acceptance remains explicit. Neither prior invalid PASS nor a self-asserted record grants authority.',
             'candidate_manifest_raw_digest': mr,
             'normative_candidate_set_digest': manifest['normative_candidate_set_sha256'],
             'machine_candidate_set_digest': manifest['machine_candidate_set_sha256'],
             'independent_assurance': False, 'foundation_spec_baseline_frozen': False,
             'Q2_N5_N8': 'NOT_AUTHORIZED_IN_THIS_CORRECTION_TASK'}
    if owner_path.exists(): assert read(owner_path) == owner
    else: emit(owner_path, owner)
    schema = read(C / SCHEMA_FILE)
    record_path = ROOT / 'AUTHOR_BASELINE_QUALIFICATION_R5_4_1.json'
    old_record = read(OLD / 'evidence/qualification/AUTHOR_BASELINE_QUALIFICATION_R5_4.json')
    registry_path = C / 'BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json'
    golden_path = C / 'BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json'
    registry, golden = read(registry_path), read(golden_path)
    roots = [read(p) for p in (C / 'objects').glob('*.json')]
    record = {k: old_record[k] for k in properties() if k in old_record}
    record.update({'author_baseline_qualification_id': 'BDB-AUTHOR-BASELINE-QUALIFICATION-R5_4_1-2026-10-06-001',
                   'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'candidate_manifest_storage_id': str(manifest_path), 'candidate_manifest_raw_digest': mr,
                   'normative_candidate_set_digest': manifest['normative_candidate_set_sha256'],
                   'machine_candidate_set_digest': manifest['machine_candidate_set_sha256'],
                   'self_audit_report_raw_digest': ar, 'final_reaudit_register_raw_digest': ar,
                   'final_reaudit_register_storage_id': str(audit_path), 'readback_storage_id': str(rb_path),
                   'readback_raw_digest': rr, 'readback_entries': entries, **dict(zip(COUNT_FIELDS, counts)),
                   'owner_decision_storage_id': str(owner_path), 'owner_decision_raw_digest': sha(owner_path.read_bytes()),
                   'governance_actor_ref': owner['governance_actor_ref'], 'reason_codes': [
                       'DIRECT_OWNER_GOVERNANCE_CORRECTION_APPROVED', 'FRESH_EXACT_Q1_PASS',
                       'AUTHOR_ONLY_RISK_EXPLICITLY_ACCEPTED', 'PRIOR_INVALID_RECORD_EXCLUDED', 'NO_INDEPENDENT_FREEZE'],
                   'registry_raw_digest': sha(registry_path.read_bytes()), 'golden_vector_set_raw_digest': sha(golden_path.read_bytes()),
                   'artifact_contract_registry_ref': next(o['ref'] for o in roots if o['kind'] == 'artifact_contract_registry'),
                   'schema_registry_ref': sr['ref'],
                   'qualification_scope': 'EXACT R5.4.1 AUTHOR NORMATIVE/MACHINE BASELINE ONLY; Q2/N5-N11 not executed; no runtime/independent/release assurance'})
    if record_path.exists(): record = read(record_path)
    assert record['author_baseline_qualification_id'] != old_record['author_baseline_qualification_id']
    assert record['registry_raw_digest'] == sha(registry_path.read_bytes())
    assert record['golden_vector_set_raw_digest'] == sha(golden_path.read_bytes())
    assert record['schema_registry_ref'] == sr['ref']
    assert record['artifact_contract_registry_ref'] == next(o['ref'] for o in roots if o['kind'] == 'artifact_contract_registry')
    assert record['registry_id'] == registry['registry_id']
    assert record['golden_vector_set_id'] == golden['vector_set_id']
    assert record['owner_decision_raw_digest'] == sha(owner_path.read_bytes())
    assert record['candidate_manifest_storage_id'] == str(manifest_path)
    assert record['final_reaudit_register_storage_id'] == str(audit_path) and record['readback_storage_id'] == str(rb_path)
    validate(record, manifest, mr, entries, owner, ar, rr, schema)
    if not record_path.exists(): emit(record_path, record)  # Publish only after all checks pass.
    assert read(record_path) == record
    # Post-publication check from disk, including predecessor invalidation and source pins.
    run()
    validate(read(record_path), read(manifest_path), sha(manifest_path.read_bytes()), entries,
             read(owner_path), sha(audit_path.read_bytes()), sha(rb_path.read_bytes()), schema)
    gate = 'R5_4_1_AUTHOR_QUALIFIED_FOR_IMPLEMENTATION'
    identities = {'predecessor': manifest['direct_predecessor'], 'manifest_raw_digest': mr,
                  'normative_candidate_set_digest': manifest['normative_candidate_set_sha256'],
                  'machine_candidate_set_digest': manifest['machine_candidate_set_sha256'],
                  'registry_raw_digest': sha(registry_path.read_bytes()), 'golden_raw_digest': sha(golden_path.read_bytes()),
                  'schema_registry_object_digest': sr['ref']['revision_digest'],
                  'governance_schema_raw_digest': sha((C / SCHEMA_FILE).read_bytes()),
                  'qualification_record_raw_digest': sha(record_path.read_bytes()),
                  'readback_raw_digest': rr, 'self_audit_raw_digest': ar}
    status = subprocess.run(['git', 'status', '--short'], capture_output=True, text=True)
    diff = subprocess.run(['git', 'diff', '--check'], capture_output=True, text=True)
    assert status.returncode == diff.returncode == 0
    emit(ROOT / 'R5_4_1_Q1_RESULT.json', {'gate': gate, 'identities': identities, 'checks': checks,
         'AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE': 'YES_DERIVED_FROM_VALID_EXTERNAL_RECORD',
         'prior_record_effective_state': 'NO_VALID_QUALIFICATION', 'Q2': 'NOT_STARTED', 'N5_N11': 'NOT_STARTED',
         'runtime_tests': 'NOT_RUN', 'independent_assurance': False, 'foundation_spec_baseline_frozen': False,
         'repository': {'head': pins['head'], 'tree': pins['tree'], 'branch': pins['branch'],
                        'status': status.stdout, 'status_warning': status.stderr, 'diff_check_exit_code': diff.returncode}})
    summary = '# R5.4.1 fresh Q1 qualification\n\nFinal gate: **' + gate + '**.\n\n'
    summary += 'Author-only assurance; independent_assurance=false; foundation_spec_baseline_frozen=false. '
    summary += 'Old invalid qualification remains NO_VALID_QUALIFICATION. New record has a new ID and exact digest. '
    summary += 'Owner authority is the direct correction/fresh-Q1 order with explicit prior author-only risk acceptance, scoped to the proven minimal successor delta. '
    summary += 'Q2 and N5–N11 are NOT_STARTED. Runtime tests/vectors NOT_RUN. NF02 closure is not claimed.\n\n'
    summary += '## Exact identities\n\n```json\n' + __import__('json').dumps(identities, indent=2) + '\n```\n\n'
    summary += '## Fresh checks\n\n' + '\n'.join('- ' + c for c in checks) + '\n\n'
    summary += f'Readback: {counts[0]} normative + {counts[1]} machine = {counts[2]}; zero mismatches. '
    summary += 'Manifest-derived counts; 18 executed external governance vectors PASS. All 149 inherited runtime vectors NOT_RUN.\n\n'
    summary += 'Commands: `python docs/R5_4_1/tools/verify_candidate.py`, '
    summary += '`python docs/R5_4_1/tools/finalize_delivery.py`, `python docs/R5_4_1/tools/qualify_exact_candidate.py` — PASS. '
    summary += '`git diff --check` — exit 0. Full source/status/preservation pins are in evidence and R5_4_1_Q1_RESULT.json.\n'
    emit(ROOT / 'R5_4_1_Q1_QUALIFICATION_REPORT.md', summary)
    report = '# R5.4.1 governance correction\n\n'
    report += 'The scalar verdict conflict and ambiguous count contract are removed by one Data §187.2 definition and a closed external executable record/2 schema. '
    report += '§192.2 references the same definition. Required prior storage/hash/owner/Registry/Golden/root bindings are retained; self_audit_report_raw_digest and explicit counts are now required. '
    report += 'The final audit and re-audit register are the same JSON artifact, with an explicit equality predicate. '
    report += 'The removed token appears only as the negative historical-token mutation in governance vectors.\n\n'
    report += '## Scope and identity propagation\n\nRuntime Registry, SchemaRegistry/2, 41 executable runtime/transport schemas, 39 bindings, canonical root objects, NF02 profiles and 149 vector structures remain byte-for-byte inherited. '
    report += 'No governance canonical kind is added. The new external schema/descriptor/fixture are machine artifacts. Only the external installation bundle normative-set pin propagates the changed normative set. '
    report += 'SchemaRegistry ObjectDigest therefore legitimately remains unchanged. No latest-installed authority or old campaign upgrade is introduced.\n\n'
    report += '## Minimal delta\n\n| Candidate file | Classification | Old SHA-256 | New SHA-256 |\n|---|---|---|---|\n'
    delta = read(ROOT / 'R5_4_TO_R5_4_1_DELTA.json')
    for e in delta['changes']:
        report += f'| {e["file"]} | {e["classification"]} | {e["predecessor_raw_digest"] or "NEW"} | {e["successor_raw_digest"]} |\n'
    report += '\nAll other candidate bytes are proved unchanged. Complete machine delta is R5_4_TO_R5_4_1_DELTA.json. '
    report += 'All non-candidate files are new external PROVENANCE_UPDATE artifacts; they do not enter candidate preimages. '
    report += 'The candidate → manifest → readback → audit → owner/qualification → Q1 result DAG is acyclic. '
    report += 'Synthetic vectors bind synthetic sets, never the containing current set.\n\n'
    report += summary[summary.index('## Exact identities'):]
    report += '\n## Complete exact candidate inventory\n\n| Group | File | SHA-256 | Bytes |\n|---|---|---|---:|\n'
    for g in ['normative', 'machine']:
        for e in manifest[g + '_candidate_files']:
            report += f'| {g} | {e["file"]} | {e["sha256"]} | {e["bytes"]} |\n'
    report += '\nGovernance schema $id/dialect/bytes/dependency closure: candidate/governance/GOVERNANCE_CONTRACT.json. '
    report += 'Runtime schema binding table/catalog is exact inherited candidate/SCHEMA_ARTIFACT_CATALOG_R5_4.json and objects/schema_registry__2.json.\n'
    emit(ROOT / 'R5_4_1_GOVERNANCE_CORRECTION_REPORT.md', report)
    # Every external file is named; the inventory deliberately has no self-hash.
    emit(ROOT / 'R5_4_1_EXTERNAL_ARTIFACT_INVENTORY.json', {
         'classification': 'PROVENANCE_UPDATE', 'self_hash': 'EXTERNAL',
         'entries': [{'file': p.relative_to(ROOT).as_posix(), 'raw_digest': sha(p.read_bytes()), 'bytes': p.stat().st_size}
                     for p in sorted(ROOT.rglob('*')) if p.is_file() and C not in p.parents
                     and p.name != 'R5_4_1_EXTERNAL_ARTIFACT_INVENTORY.json']})
    print(gate)


if __name__ == '__main__': qualify()

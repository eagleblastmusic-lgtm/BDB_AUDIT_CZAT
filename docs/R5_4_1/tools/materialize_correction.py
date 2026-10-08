"""Reproducible, successor-only governance correction. Never edit its predecessor."""
import copy
import shutil

from governance import C, COUNT_FIELDS, DECISION, OLD, ROOT, SCHEMA_FILE, TASK, VERDICT, canonical, emit, properties, read, sha


CONTRACT = '''## 187.2. Author baseline qualification — corrected external record/2

R5.4.1 owner-approved governance correction. This section and the exact executable
`governance/AuthorBaselineQualificationRecord__2.schema.json` define the ONE external
`AuthorBaselineQualificationRecord/2` body. §192.2 refers to this definition.
It is outside campaign history, NOT a canonical Registry kind or runtime capability.
The schema is a machine candidate artifact; instance records, readback, self-audit,
owner decisions and invalidations are external to both candidate-set preimages.

Required fields (closed schema; no aliases):

```text
record_type = AuthorBaselineQualificationRecord/2
status = VALID_AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE
author_baseline_qualification_id
normative_candidate_set_digest
machine_candidate_set_digest
candidate_manifest_raw_digest
candidate_manifest_schema = BDB_AUDIT_V2_R5_4_PACKAGE_MANIFEST/1
candidate_manifest_storage_id
self_audit_report_raw_digest
final_reaudit_register_storage_id
final_reaudit_register_raw_digest
readback_storage_provider = LOCAL_FILESYSTEM
readback_storage_id
readback_raw_digest
readback_verified_normative_file_count
readback_verified_machine_file_count
readback_verified_total_file_count
readback_mismatch_count = 0
readback_entries[] # group, file, stable_storage_id, expected_raw_digest,
                   # observed_raw_digest, byte_length, result=PASS
author_verdict = R5_4_AUTHOR_NORMATIVE_FINAL_SELF_AUDIT_PASS
owner_assurance_decision = IMPLEMENTATION_MAY_PROCEED_UNDER_AUTHOR_ONLY_ASSURANCE
governance_actor_ref
owner_decision_storage_id
owner_decision_raw_digest
registry_id
registry_raw_digest
artifact_contract_registry_ref
golden_vector_set_id
golden_vector_set_raw_digest
schema_registry_ref
qualification_scope
independent_assurance = false
foundation_spec_baseline_frozen = false
reason_codes[]
created_at # informational; never ordering/authority
```

The exact external contract descriptor `governance/GOVERNANCE_CONTRACT.json` pins
schema RawDigest, byte length, $id, dialect and dependency closure. Existing
SchemaRegistry/2 remains exclusively canonical runtime authority; it does not
register this external governance record. Author verdict is the single scalar
above, never an array or an alternative token. /1 historical records are unchanged.

The manifest /1 format is inherited; revision metadata is R5.4.1. Its
`normative_candidate_files` and `machine_candidate_files` arrays are the normative
and machine candidate entries respectively. Derive counts from these EXACT arrays:
normative count = len(normative_candidate_files); machine count = len(machine_candidate_files);
total count = normative count + machine count = len(readback_entries).
There are no universal numeric count constants. Unique (group,file) membership
must equal the manifest, with no duplicates, omitted/extra provenance files or
wrong group. expected/observed RawDigest and byte length must equal actual immutable
candidate bytes and manifest entries; stable_storage_id must resolve that exact file.
Both set digests use inherited sorted [{file,bytes,sha256}] CJSON SHA256 preimages.

self_audit_report_raw_digest == final_reaudit_register_raw_digest identifies the
same final external JSON author audit. Preserve its stable storage identity.
Readback digest/storage, Registry/Golden raw hashes and exact canonical root refs
must resolve consistently. No self-audit, qualification, invalidation or owner
decision instance may enter its own candidate-set preimage.

Fresh Q1 validates schema AND all semantic/hash/storage predicates, final audit
and readback for this manifest, and direct human owner authority accepting author-only
risk for this successor correction. Design approval alone is insufficient. In this
task the explicit correction-and-fresh-Q1 order authorizes the minimal successor
and a NEW record after successful checks; the prior explicit author-only risk
acceptance is retained as human provenance, never as a reused qualification PASS.
Any expanded delta requires a new decision. The invalid R5.4 record stays excluded
by its preserved external invalidation as NO_VALID_QUALIFICATION.

Effective AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE=YES is derived ONLY after all
checks pass; it is not a self-authenticating field in the record. Candidate pending
flags remain historical preparation metadata. No independent freeze, runtime PASS,
release qualification or NF02 closure follows. Q2 and N5–N11 remain separate tasks.

'''


def main():
    assert not (ROOT / 'AUTHOR_BASELINE_QUALIFICATION_R5_4_1.json').exists(), 'qualified successor immutable'
    old_manifest = read(OLD / 'evidence/BDB_AUDIT_V2_R5_4_MANIFEST_SHA256.json')
    pins_path = ROOT / 'evidence/R5_4_SOURCE_PREDECESSOR_PINS.json'
    if not pins_path.exists():
        pins = read(OLD / 'evidence/R5_4_SOURCE_PREDECESSOR_PINS.json')
        pins['r5_4_subtree_raw_pins'] = {p.relative_to(OLD).as_posix(): sha(p.read_bytes())
                                       for p in sorted(OLD.rglob('*')) if p.is_file()}
        pins['correction_task_raw_digest'] = sha(TASK.read_bytes())
        emit(pins_path, pins)
        (ROOT / 'evidence/OWNER_CORRECTION_REQUEST.txt').write_bytes(TASK.read_bytes())
    if not C.exists(): shutil.copytree(OLD / 'candidate', C)
    data_path = C / 'BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md'
    old_data = (OLD / 'candidate' / data_path.name).read_text(encoding='utf-8')
    start = old_data.index('## 187.2.')
    end = old_data.index('---\n\n# 188.', start)
    data = old_data[:start] + CONTRACT + old_data[end:]
    start = data.index('The external AuthorBaselineQualificationRecord/2 has required')
    end = data.index('\n\nPrepared installation bundle', start)
    data = data[:start] + ('The external AuthorBaselineQualificationRecord/2 is defined exactly by §187.2 and its '
           'pinned external executable schema. All body/count/verdict predicates are the same single contract; '
           'no separate definition applies here. Independent foundation_baseline_freeze_decision/1 and '
           'its complete exact-manifest review requirements remain unchanged. Pending templates are not decisions.') + data[end:]
    header = '# R5.4.1 governance correction successor\n\nDirect predecessor: failed exact R5.4. '
    header += 'Only §187.2 and the corresponding §192.2 governance body are corrected; all NF02 runtime semantics are inherited. '
    header += 'Inherited filenames identify inputs, not an in-place modification of R5.4.\n\n'
    emit(data_path, header + data)
    test_name = 'BDB_AUDIT_V2_TEST_AND_SELF_AUDIT_PLAN_R5_4.md'
    emit(C / test_name, (OLD / 'candidate' / test_name).read_text(encoding='utf-8') +
         '\n\n## R5.4.1 external governance qualification\n\n'
         'Apply Data §187.2 and pinned governance schema only. Execute every GOVERNANCE_R5_4_1 vector '
         'with manifest-derived normative/machine/total counts, exact storage and hash parity, owner authority '
         'and invalid prior-record exclusion. Negative cases REJECT with no derived qualification state mutation. '
         'Schema validation alone is insufficient. Runtime Golden execution stays NOT_RUN; Q2/N5–N11 are outside correction scope.\n')
    name = 'README_BDB_AUDIT_V2_DOCUMENTATION_R5_4.md'
    emit(C / name, '# R5.4.1 successor governance index\n\n'
         'Direct failed R5.4 predecessor is pinned in the external R5.4.1 manifest. '
         'Inherited filenames/Registry/profile IDs stay exact where semantics are unchanged. '
         'Data §187.2 is the sole external record/2 definition; governance/GOVERNANCE_CONTRACT.json pins its executable schema. '
         'The governance schema is outside canonical SchemaRegistry bindings. Qualification instances are external. '
         'Only fresh exact Q1 can derive author qualification. Pending flags below describe preparation.\n\n' +
         (OLD / 'candidate' / name).read_text(encoding='utf-8'))
    props = properties()
    schema = {'$schema': 'https://json-schema.org/draft/2020-12/schema',
              '$id': 'urn:bdb:external-governance:AuthorBaselineQualificationRecord:2:R5.4.1',
              'type': 'object', 'additionalProperties': False, 'required': sorted(props), 'properties': props,
              '$defs': read(C / 'schemas/schema_registry__2.schema.json')['$defs']}
    schema_raw = emit(C / SCHEMA_FILE, schema)
    emit(C / 'governance/GOVERNANCE_CONTRACT.json', {
        'contract': 'AuthorBaselineQualificationRecord/2', 'revision': 'R5.4.1',
        'scope': 'EXTERNAL_GOVERNANCE_NOT_CANONICAL_RUNTIME', 'normative_authority': 'Data §187.2',
        'schema_file': SCHEMA_FILE, 'raw_digest': schema_raw, 'byte_length': (C / SCHEMA_FILE).stat().st_size,
        '$id': schema['$id'], 'dialect': schema['$schema'], 'dependency_closure': [], 'local_definitions_inlined': True,
        'author_verdict': VERDICT, 'count_fields': COUNT_FIELDS,
        'count_source': ['manifest.normative_candidate_files', 'manifest.machine_candidate_files'],
        'self_audit_digest_equality': ['self_audit_report_raw_digest', 'final_reaudit_register_raw_digest']})
    old_record = read(OLD / 'evidence/qualification/AUTHOR_BASELINE_QUALIFICATION_R5_4.json')
    record = {k: copy.deepcopy(old_record[k]) for k in props if k in old_record}
    record.update({'author_baseline_qualification_id': 'SYNTHETIC_GOVERNANCE_VECTOR_ONLY',
                   'self_audit_report_raw_digest': 'a'*64, 'final_reaudit_register_raw_digest': 'a'*64,
                   'reason_codes': ['SYNTHETIC_NON_AUTHORITY_PREMISE']})
    manifest = {'schema': old_manifest['schema']}
    entries = []
    for g, count in [('normative', 2), ('machine', 3)]:
        manifest[g + '_candidate_files'] = []
        for i in range(count):
            raw = f'SYNTHETIC {g} {i}'.encode()
            item = {'file': f'{g}_{i}.txt', 'bytes': len(raw), 'sha256': sha(raw)}
            manifest[g + '_candidate_files'].append(item)
            entries.append({'group': g, 'file': item['file'], 'stable_storage_id': 'SYNTHETIC_ONLY/' + item['file'],
                            'expected_raw_digest': item['sha256'], 'observed_raw_digest': item['sha256'],
                            'byte_length': item['bytes'], 'result': 'PASS'})
        digest = sha(canonical(manifest[g + '_candidate_files']))
        manifest[g + '_candidate_set_sha256'] = digest
        record[g + '_candidate_set_digest'] = digest
    mr = sha(canonical(manifest) + b'\n')
    record.update(dict(zip(COUNT_FIELDS, [2, 3, 5])))
    record.update({'candidate_manifest_raw_digest': mr, 'readback_entries': entries})
    owner = {'decision': DECISION, 'governance_actor_ref': record['governance_actor_ref'],
             'candidate_manifest_raw_digest': mr, 'normative_candidate_set_digest': record['normative_candidate_set_digest'],
             'machine_candidate_set_digest': record['machine_candidate_set_digest'],
             'scope': 'R5.4.1_GOVERNANCE_CORRECTION_AND_FRESH_Q1_ONLY'}
    mutations = ['none', 'old_token', 'token_array', 'legacy_count', 'normative_count', 'machine_count',
                 'total_count', 'duplicate', 'omitted', 'extra', 'wrong_group', 'raw_mismatch', 'wrong_manifest',
                 'wrong_machine_set', 'wrong_audit', 'unauthorized_owner', 'independent_claim', 'invalid_prior']
    cases = [{'id': 'GOVERNANCE_R5_4_1_' + m.upper() + ('_ACCEPT' if m == 'none' else '_REJECT'),
              'mutation': m, 'expected': 'ACCEPT' if m == 'none' else 'REJECT',
              'negative_derived_state_mutation': 'NONE'} for m in mutations]
    fixture_hash = emit(C / 'governance/GOVERNANCE_VECTOR_FIXTURE.json', {
        'scope': 'SYNTHETIC_SCHEMA_AND_SEMANTIC_GOVERNANCE_ONLY_NOT_ACTUAL_OWNER_AUTHORITY',
        'manifest': manifest, 'manifest_raw': mr, 'record': record, 'entries': entries, 'owner': owner,
        'audit_raw': 'a'*64, 'readback_raw': record['readback_raw_digest'], 'cases': cases})
    golden_name = 'BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json'
    golden = read(OLD / 'candidate' / golden_name)
    golden['governance_correction_revision'] = 'R5.4.1'
    golden['vectors'] += [{'id': case['id'], 'scope': 'EXTERNAL_GOVERNANCE',
                          'input': {'fixture_file': 'governance/GOVERNANCE_VECTOR_FIXTURE.json',
                                    'fixture_raw_digest': fixture_hash, 'mutation': case['mutation']},
                          'expected': {'result': case['expected'], 'negative_derived_state_mutation': 'NONE'}} for case in cases]
    emit(C / golden_name, golden)
    manifest = copy.deepcopy(old_manifest)
    manifest.update({'revision': 'R5.4.1', 'candidate_status': 'R5_4_1_PENDING_FRESH_Q1',
                     'direct_predecessor': {'revision': 'R5.4',
                         'normative_candidate_set_sha256': old_manifest['normative_candidate_set_sha256'],
                         'machine_candidate_set_sha256': old_manifest['machine_candidate_set_sha256'],
                         'manifest_raw_digest': sha((OLD / 'evidence/BDB_AUDIT_V2_R5_4_MANIFEST_SHA256.json').read_bytes()),
                         'invalid_qualification_raw_digest': sha((OLD / 'evidence/qualification/AUTHOR_BASELINE_QUALIFICATION_R5_4.json').read_bytes()),
                         'invalidation_raw_digest': sha((OLD / 'evidence/qualification/AUTHOR_BASELINE_QUALIFICATION_R5_4_INVALIDATION.json').read_bytes())}})
    inherited_keys = [k for k in manifest if k.startswith('predecessor_')]
    manifest['inherited_r5_3_provenance'] = {k: manifest.pop(k) for k in inherited_keys}
    manifest['predecessor_manifest_raw_digest'] = manifest['direct_predecessor']['manifest_raw_digest']
    manifest['predecessor_normative_candidate_set_digest'] = old_manifest['normative_candidate_set_sha256']
    manifest['predecessor_machine_candidate_set_digest'] = old_manifest['machine_candidate_set_sha256']
    manifest['scope'] = 'R5.4.1 governance-only correction and fresh Q1; Q2/N5-N11 not authorized by this task'
    norm_names = {e['file'] for e in old_manifest['normative_candidate_files']}
    def inventory(group):
        files = sorted((p for p in C.rglob('*') if p.is_file() and ((p.relative_to(C).as_posix() in norm_names) == (group == 'normative'))),
                       key=lambda p: p.relative_to(C).as_posix())
        result = [{'file': p.relative_to(C).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes()),
                   'role': 'normative' if group == 'normative' else 'machine_activation_or_vector_fixture'} for p in files]
        manifest[group + '_candidate_files'] = result
        manifest[group + '_candidate_set_sha256'] = sha(canonical([{k: e[k] for k in ['file', 'bytes', 'sha256']} for e in result]))
    inventory('normative')
    bundle = read(C / 'INSTALLATION_PIN_BUNDLE_R5_4.json')
    bundle['governing_normative_candidate_set_sha256'] = manifest['normative_candidate_set_sha256']
    emit(C / 'INSTALLATION_PIN_BUNDLE_R5_4.json', bundle)
    inventory('machine')
    emit(ROOT / 'R5_4_1_CANDIDATE_MANIFEST.json', manifest)
    changes = []
    for group in ['normative', 'machine']:
        for e in manifest[group + '_candidate_files']:
            old_path = OLD / 'candidate' / e['file']
            old_hash = sha(old_path.read_bytes()) if old_path.exists() else None
            if old_hash == e['sha256']: continue
            category = ('HASH_PROPAGATION' if 'INSTALLATION_PIN' in e['file'] else
                        'GOLDEN_PROPAGATION' if 'GOLDEN' in e['file'] or 'VECTOR_FIXTURE' in e['file'] else
                        'SCHEMA_PROPAGATION' if e['file'].startswith('governance/') else 'GOVERNANCE_CONFLICT_CORRECTION')
            changes.append({'file': 'candidate/' + e['file'], 'group': group, 'classification': category,
                            'predecessor_raw_digest': old_hash, 'successor_raw_digest': e['sha256'],
                            'why': 'Sole external record/2 definition and its schema/vector closure; NF02 runtime contract unchanged.'})
    emit(ROOT / 'R5_4_TO_R5_4_1_DELTA.json', {'scope': 'ALL_CHANGED_CANDIDATE_FILES', 'changes': changes,
         'unchanged_candidate_files': [e['file'] for g in ['normative', 'machine'] for e in manifest[g + '_candidate_files']
                                      if 'candidate/' + e['file'] not in {c['file'] for c in changes}],
         'external_artifacts_classification': 'PROVENANCE_UPDATE',
         'external_artifacts': 'Every non-candidate file under docs/R5_4_1 is a new correction tool, manifest, audit, readback or external governance/provenance report; excludes candidate preimages.'})
    # Adapt the full predecessor artifact verifier, retaining all NF02 checks.
    verifier = (OLD / 'tools/verify_candidate.py').read_text(encoding='utf-8')
    verifier = verifier.replace('E / "BDB_AUDIT_V2_R5_4_MANIFEST_SHA256.json"', 'ROOT / "R5_4_1_CANDIDATE_MANIFEST.json"')
    verifier = verifier.replace("if 'docs/R5_4/' not in s", "if 'docs/R5_4/' not in s and 'docs/R5_4_1/' not in s")
    verifier = verifier.replace("additions = vectors['vectors'][117:]", "additions = vectors['vectors'][117:149]")
    verifier = verifier.replace('    return manifest, readback, checks, catalog, sr',
                                '    from parity import check_governance\n    checks.extend(check_governance(manifest))\n    return manifest, readback, checks, catalog, sr')
    emit(ROOT / 'tools/verify_candidate.py', verifier)
    print('R5.4.1 successor materialized; predecessor untouched; Q1 pending')


if __name__ == '__main__': main()

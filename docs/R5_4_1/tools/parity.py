"""Fresh parsed parity, strict predecessor preservation and minimal-delta checks."""
import difflib

import jsonschema

from governance import C, COUNT_FIELDS, OLD, ROOT, SCHEMA_FILE, TASK, VERDICT, canonical, read, sha, vector_run


def check_governance(manifest):
    pins = read(ROOT / 'evidence/R5_4_SOURCE_PREDECESSOR_PINS.json')
    actual_old = {p.relative_to(OLD).as_posix(): sha(p.read_bytes()) for p in OLD.rglob('*') if p.is_file()}
    assert actual_old == pins['r5_4_subtree_raw_pins'], 'entire R5.4 forensic subtree preservation'
    assert sha(TASK.read_bytes()) == pins['correction_task_raw_digest']
    assert (ROOT / 'evidence/OWNER_CORRECTION_REQUEST.txt').read_bytes() == TASK.read_bytes()
    previous = read(OLD / 'evidence/BDB_AUDIT_V2_R5_4_MANIFEST_SHA256.json')
    assert manifest['direct_predecessor']['manifest_raw_digest'] == sha((OLD / 'evidence/BDB_AUDIT_V2_R5_4_MANIFEST_SHA256.json').read_bytes())
    for group in ['normative', 'machine']:
        assert manifest['direct_predecessor'][group + '_candidate_set_sha256'] == previous[group + '_candidate_set_sha256']
        names = [x['file'] for x in manifest[group + '_candidate_files']]
        assert names == sorted(set(names))
    invalid = read(OLD / 'evidence/qualification/AUTHOR_BASELINE_QUALIFICATION_R5_4_INVALIDATION.json')
    assert invalid['qualification_record_valid'] is False
    assert invalid['derived_author_qualified_implementation_baseline'] == 'NO_VALID_QUALIFICATION'
    assert invalid['qualification_record_raw_digest'] == manifest['direct_predecessor']['invalid_qualification_raw_digest']
    assert sha((OLD / 'evidence/qualification/AUTHOR_BASELINE_QUALIFICATION_R5_4_INVALIDATION.json').read_bytes()) == manifest['direct_predecessor']['invalidation_raw_digest']
    allowed = {'BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md',
               'BDB_AUDIT_V2_TEST_AND_SELF_AUDIT_PLAN_R5_4.md', 'README_BDB_AUDIT_V2_DOCUMENTATION_R5_4.md',
               'BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json', 'INSTALLATION_PIN_BUNDLE_R5_4.json'}
    changed = []
    for entry in manifest['normative_candidate_files'] + manifest['machine_candidate_files']:
        old_path = OLD / 'candidate' / entry['file']
        if old_path.exists() and old_path.read_bytes() == (C / entry['file']).read_bytes(): continue
        assert entry['file'] in allowed or entry['file'].startswith('governance/'), entry['file']
        changed.append(entry['file'])
    old_bundle = read(OLD / 'candidate/INSTALLATION_PIN_BUNDLE_R5_4.json')
    new_bundle = read(C / 'INSTALLATION_PIN_BUNDLE_R5_4.json')
    old_bundle['governing_normative_candidate_set_sha256'] = manifest['normative_candidate_set_sha256']
    assert old_bundle == new_bundle, 'only normative set pin propagation permitted'
    old_data = (OLD / 'candidate/BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md').read_text(encoding='utf-8')
    data = (C / 'BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md').read_text(encoding='utf-8')
    # Exact unchanged regions checked separately; no normative change hidden in a broad diff.
    assert old_data[:old_data.index('## 187.2.')] in data
    assert old_data[old_data.index('---\n\n# 188.'):old_data.index('The external AuthorBaselineQualificationRecord/2 has required')] in data
    assert old_data[old_data.index('\n\nPrepared installation bundle'):] == data[data.index('\n\nPrepared installation bundle'):]
    descriptor = read(C / 'governance/GOVERNANCE_CONTRACT.json')
    schema = read(C / SCHEMA_FILE)
    raw = (C / SCHEMA_FILE).read_bytes()
    assert raw == canonical(schema) + b'\n'
    assert descriptor['raw_digest'] == sha(raw) and descriptor['byte_length'] == len(raw)
    assert descriptor['$id'] == schema['$id'] and descriptor['dialect'] == schema['$schema']
    assert descriptor['dependency_closure'] == []
    assert descriptor['author_verdict'] == schema['properties']['author_verdict']['const'] == VERDICT
    assert descriptor['count_fields'] == COUNT_FIELDS
    assert set(schema['required']) == set(schema['properties'])
    assert schema['additionalProperties'] is False
    forbidden = ['readback_verified_file_count', 'readback_verified_normative_count', 'readback_verified_machine_count']
    assert not set(forbidden) & set(schema['properties'])
    for field in COUNT_FIELDS:
        assert schema['properties'][field] == {'type': 'integer', 'minimum': 0}
        assert field in data
    jsonschema.Draft202012Validator.check_schema(schema)
    # Search every narrative source, and parse each machine file (except intentional malformed adversarial bytes).
    findings = []
    for path in sorted(C.rglob('*')):
        if path.suffix == '.md':
            text = path.read_text(encoding='utf-8')
            assert 'R5_4_N1_N4_AUTHOR_SELF_AUDIT_PASS' not in text, path
            assert not any(field in text for field in forbidden), path
            if 'AuthorBaselineQualificationRecord/2' in text:
                findings.append(path.relative_to(C).as_posix())
                if path.name.startswith('BDB_AUDIT_V2_DATA'):
                    assert text.count('author_verdict = ' + VERDICT) == 1
        elif path.suffix == '.json':
            if path.name == 'duplicate_manifest_keys.json':
                try: read(path)
                except AssertionError: pass
                else: raise AssertionError('intentional duplicate-key fixture no longer rejects')
            else: read(path)
    golden = read(C / 'BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json')
    old_golden = read(OLD / 'candidate/BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json')
    assert golden['vectors'][:len(old_golden['vectors'])] == old_golden['vectors']
    fixture = read(C / 'governance/GOVERNANCE_VECTOR_FIXTURE.json')
    new_vectors = golden['vectors'][len(old_golden['vectors']):]
    assert {v['id'] for v in new_vectors} == {v['id'] for v in fixture['cases']}
    assert len(new_vectors) == len(fixture['cases'])
    for v in new_vectors:
        assert v['input']['fixture_raw_digest'] == sha((C / v['input']['fixture_file']).read_bytes())
        case = next(c for c in fixture['cases'] if c['id'] == v['id'])
        assert v['input']['mutation'] == case['mutation'] and v['expected']['result'] == case['expected']
        assert v['expected']['negative_derived_state_mutation'] == 'NONE'
    outcomes = vector_run(schema)
    delta = read(ROOT / 'R5_4_TO_R5_4_1_DELTA.json')
    assert {d['file'].removeprefix('candidate/') for d in delta['changes']} == set(changed)
    for d in delta['changes']:
        assert d['classification'] in {'GOVERNANCE_CONFLICT_CORRECTION', 'HASH_PROPAGATION', 'SCHEMA_PROPAGATION', 'GOLDEN_PROPAGATION', 'PROVENANCE_UPDATE'}
        assert sha((ROOT / d['file']).read_bytes()) == d['successor_raw_digest']
    return [f'entire R5.4 subtree ({len(actual_old)} files), source and owner task unchanged; invalid prior qualification excluded',
            f'minimal delta: {len(changed)} candidate files; all other candidate bytes exact; runtime Registry/SchemaRegistry/schema bytes unchanged',
            'one parsed closed external governance schema; narrative parity; one scalar verdict; manifest-derived explicit counts; no self-hash cycle',
            f'{len(outcomes)} fresh governance vectors executed PASS; inherited {len(old_golden["vectors"])} runtime vectors NOT_RUN']

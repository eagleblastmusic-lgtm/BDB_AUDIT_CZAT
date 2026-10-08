"""External governance validation only; never campaign/runtime authority."""
import copy
import hashlib
import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
C = ROOT / 'candidate'
OLD = ROOT.parent / 'R5_4'
VERDICT = 'R5_4_AUTHOR_NORMATIVE_FINAL_SELF_AUDIT_PASS'
DECISION = 'IMPLEMENTATION_MAY_PROCEED_UNDER_AUTHOR_ONLY_ASSURANCE'
COUNT_FIELDS = ['readback_verified_normative_file_count', 'readback_verified_machine_file_count',
                'readback_verified_total_file_count']
SCHEMA_FILE = 'governance/AuthorBaselineQualificationRecord__2.schema.json'
TASK = Path('C:/Users/Skarabeusz/.codex/attachments/8542fbf1-c386-452a-b0b3-77593b930ec7/Wklejony tekst.txt')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def unique(pairs):
    result = {}
    for key, value in pairs:
        assert key not in result, ('duplicate JSON key', key)
        result[key] = value
    return result


def read(path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def emit(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value.encode('utf-8') if isinstance(value, str) else canonical(value) + b'\n'
    path.write_bytes(raw)
    assert path.read_bytes() == raw
    return sha(raw)


def properties():
    text = {'type': 'string', 'minLength': 1}
    digest = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
    props = {k: text for k in ['author_baseline_qualification_id', 'candidate_manifest_storage_id',
             'final_reaudit_register_storage_id', 'readback_storage_id', 'governance_actor_ref',
             'owner_decision_storage_id', 'registry_id', 'golden_vector_set_id', 'qualification_scope', 'created_at']}
    props.update({k: digest for k in ['normative_candidate_set_digest', 'machine_candidate_set_digest',
                  'candidate_manifest_raw_digest', 'self_audit_report_raw_digest', 'final_reaudit_register_raw_digest',
                  'readback_raw_digest', 'owner_decision_raw_digest', 'registry_raw_digest', 'golden_vector_set_raw_digest']})
    props.update({k: {'const': v} for k, v in {
        'record_type': 'AuthorBaselineQualificationRecord/2', 'author_verdict': VERDICT,
        'candidate_manifest_schema': 'BDB_AUDIT_V2_R5_4_PACKAGE_MANIFEST/1',
        'owner_assurance_decision': DECISION, 'readback_storage_provider': 'LOCAL_FILESYSTEM',
        'readback_mismatch_count': 0, 'independent_assurance': False, 'foundation_spec_baseline_frozen': False,
        'status': 'VALID_AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE'}.items()})
    props.update({k: {'type': 'integer', 'minimum': 0} for k in COUNT_FIELDS})
    props['reason_codes'] = {'type': 'array', 'minItems': 1, 'uniqueItems': True, 'items': text}
    entry = {'group': {'enum': ['normative', 'machine']}, 'file': text, 'stable_storage_id': text,
             'expected_raw_digest': digest, 'observed_raw_digest': digest, 'byte_length': {'type': 'integer', 'minimum': 0},
             'result': {'const': 'PASS'}}
    props['readback_entries'] = {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                                'required': list(entry), 'properties': entry}}
    for key in ['artifact_contract_registry_ref', 'schema_registry_ref']:
        schema = read(OLD / 'candidate/schemas/schema_registry__2.schema.json')
        # Exact inherited typed-ref definition, not arbitrary self-asserted trust.
        props[key] = {'allOf': [{'$ref': '#/$defs/typed_ref'},
                      {'properties': {'kind': {'const': key.removesuffix('_ref')}}}]}
    return props


def validate(record, manifest, manifest_raw, entries, owner, audit_raw, readback_raw, schema):
    jsonschema.Draft202012Validator(schema).validate(record)
    assert record['candidate_manifest_raw_digest'] == manifest_raw
    for group in ['normative', 'machine']:
        assert record[group + '_candidate_set_digest'] == manifest[group + '_candidate_set_sha256']
    counts = [len(manifest['normative_candidate_files']), len(manifest['machine_candidate_files'])]
    counts.append(sum(counts))
    assert [record[k] for k in COUNT_FIELDS] == counts
    assert len(record['readback_entries']) == counts[-1]
    expected = {(e['group'], e['file']): e for e in entries}
    actual = {(e['group'], e['file']): e for e in record['readback_entries']}
    assert len(expected) == len(entries) == len(actual) == len(record['readback_entries'])
    assert actual == expected
    manifest_entries = {(g, e['file']): e for g in ['normative', 'machine'] for e in manifest[g + '_candidate_files']}
    assert set(actual) == set(manifest_entries)
    for key, entry in actual.items():
        target = manifest_entries[key]
        assert entry['expected_raw_digest'] == entry['observed_raw_digest'] == target['sha256']
        assert entry['byte_length'] == target['bytes']
    assert record['self_audit_report_raw_digest'] == record['final_reaudit_register_raw_digest'] == audit_raw
    assert record['readback_raw_digest'] == readback_raw
    assert owner['decision'] == DECISION and owner['governance_actor_ref'] == record['governance_actor_ref']
    assert owner['candidate_manifest_raw_digest'] == manifest_raw
    assert owner['normative_candidate_set_digest'] == record['normative_candidate_set_digest']
    assert owner['machine_candidate_set_digest'] == record['machine_candidate_set_digest']
    assert owner['scope'] == 'R5.4.1_GOVERNANCE_CORRECTION_AND_FRESH_Q1_ONLY'
    return True


def vector_run(schema):
    fixture = read(C / 'governance/GOVERNANCE_VECTOR_FIXTURE.json')
    outcomes = []
    for vector in fixture['cases']:
        record = copy.deepcopy(fixture['record'])
        owner = copy.deepcopy(fixture['owner'])
        mutation = vector['mutation']
        if mutation == 'old_token': record['author_verdict'] = 'R5_4_N1_N4_AUTHOR_SELF_AUDIT_PASS'
        elif mutation == 'token_array': record['author_verdict'] = [VERDICT]
        elif mutation == 'legacy_count': record['readback_verified_file_count'] = len(record['readback_entries'])
        elif mutation == 'normative_count': record[COUNT_FIELDS[0]] += 1
        elif mutation == 'machine_count': record[COUNT_FIELDS[1]] += 1
        elif mutation == 'total_count': record[COUNT_FIELDS[2]] += 1
        elif mutation == 'duplicate': record['readback_entries'][-1] = record['readback_entries'][0]
        elif mutation == 'omitted': record['readback_entries'].pop()
        elif mutation == 'extra': record['readback_entries'].append(dict(record['readback_entries'][0], file='external_qualification.json'))
        elif mutation == 'wrong_group': record['readback_entries'][0]['group'] = 'machine'
        elif mutation == 'raw_mismatch': record['readback_entries'][0]['observed_raw_digest'] = '0'*64
        elif mutation == 'wrong_manifest': record['candidate_manifest_raw_digest'] = '0'*64
        elif mutation == 'wrong_machine_set': record['machine_candidate_set_digest'] = '0'*64
        elif mutation == 'wrong_audit': record['self_audit_report_raw_digest'] = '0'*64
        elif mutation == 'unauthorized_owner': owner['decision'] = 'NOT_AUTHORIZED'
        elif mutation == 'independent_claim': record['independent_assurance'] = True
        elif mutation == 'invalid_prior': record = read(OLD / 'evidence/qualification/AUTHOR_BASELINE_QUALIFICATION_R5_4.json')
        elif mutation != 'none': raise AssertionError(mutation)
        state = {}  # Derived qualification state is published only after every predicate succeeds.
        try:
            validate(record, fixture['manifest'], fixture['manifest_raw'], fixture['entries'], owner,
                     fixture['audit_raw'], fixture['readback_raw'], schema)
            state['qualified'] = True
            result = 'ACCEPT'
        except (AssertionError, jsonschema.ValidationError):
            result = 'REJECT'
        assert result == vector['expected'], vector['id']
        assert result == 'ACCEPT' or state == {}, vector['id']
        outcomes.append({'id': vector['id'], 'result': result, 'derived_state_mutation': 'YES' if state else 'NONE'})
    return outcomes

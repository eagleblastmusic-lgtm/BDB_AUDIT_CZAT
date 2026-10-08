"""Independent disk artifact self-audit; never a production acceptance runner."""
import hashlib
import importlib.metadata
import io
import json
import pathlib
import re
import subprocess
import zipfile

import jsonschema

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
CONTEXT = REPO.parent / "BDB Audit - Context"
C = ROOT / "candidate"
E = ROOT / "evidence"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AssertionError("duplicate JSON key: " + key)
        result[key] = value
    return result


def read(path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=REPO, text=True, encoding="utf-8").strip()


def walk(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def run():
    checks = []
    manifest = read(ROOT / "R5_4_1_CANDIDATE_MANIFEST.json")
    pins = read(E / "R5_4_SOURCE_PREDECESSOR_PINS.json")
    for command, field in [(('rev-parse', 'HEAD'), 'head'), (('rev-parse', 'HEAD^{tree}'), 'tree'),
                           (('branch', '--show-current'), 'branch'), (('rev-parse', 'main'), 'main')]:
        assert git(*command) == pins[field], field
    for key, directory in [('predecessor_context_raw_pins', CONTEXT), ('source_pins', REPO), ('protected_tracked_pins', REPO)]:
        for name, expected in pins[key].items():
            assert sha((directory / name).read_bytes()) == expected, (key, name)
    assert sha((REPO / 'docs/NF02_NORMATIVE_CONTRACT_DECISION_PROPOSAL.md').read_bytes()) == pins['proposal_raw_digest']
    before = set(pins['worktree_status_before'])
    current = set(git('status', '--short').splitlines())
    assert {s for s in current if 'docs/R5_4/' not in s and 'docs/R5_4_1/' not in s} == {s for s in before if 'docs/R5_4/' not in s and 'docs/R5_4_1/' not in s}, (before, current)
    checks.append('source/HEAD/tree/branch/main/predecessor/proposal and pre-existing worktree bytes unchanged')
    readback = []
    for group in ['normative', 'machine']:
        entries = manifest[group + '_candidate_files']
        triples = []
        for item in entries:
            raw = (C / item['file']).read_bytes()
            actual = sha(raw)
            assert actual == item['sha256'] and len(raw) == item['bytes'], item['file']
            triples.append({k: item[k] for k in ['file', 'bytes', 'sha256']})
            readback.append({'file': item['file'], 'absolute_path': str(C / item['file']), 'bytes': len(raw),
                             'expected_sha256': item['sha256'], 'observed_sha256': actual, 'match': True})
        assert sha(canonical(sorted(triples, key=lambda x: x['file']))) == manifest[group + '_candidate_set_sha256']
    assert len(manifest['normative_candidate_files']) == 10
    listed = {x['file'] for x in manifest['normative_candidate_files'] + manifest['machine_candidate_files']}
    assert listed == {p.relative_to(C).as_posix() for p in C.rglob('*') if p.is_file()}
    checks.append('complete disjoint manifest inventories, exact raw readback and both canonical set preimages')
    base = read(CONTEXT / 'BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY.json')
    registry = read(C / 'BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json')
    rows = {(x['kind'], x['version']): x for x in registry['contracts']}
    assert all(rows[(x['kind'], x['version'])] == x for x in base['contracts'])
    new = {('assignment_package_binding', '1'), ('lane_result_admission_evidence', '2'),
           ('bdb_audit_lane_result', '2'), ('schema_registry', '2')}
    assert set(rows) - {(r['kind'], r['version']) for r in base['contracts']} == new
    assert len(rows) == len(registry['contracts']) == 114
    for key in ['canonical_role_domain', 'reference_class_semantics', 'reference_target_classes', 'order_only_precedence_profiles']:
        assert registry[key] == base[key], key
    assert registry['validation_layer_profiles']['NF02_PROVENANCE'] == ['L1', 'L2', 'L3', 'L4', 'L5', 'L6']
    for kind in ['lane_result_admission_evidence', 'bdb_audit_lane_result']:
        assert (kind, '1') not in rows
    checks.append('all 110 predecessor rows exact; four additions only; roles/reference classes/order domains preserved')
    catalog = read(C / 'SCHEMA_ARTIFACT_CATALOG_R5_4.json')['artifacts']
    schemas = {}
    schema_hashes = {}
    for item in catalog:
        raw = (C / item['file']).read_bytes()
        schema = read(C / item['file'])
        assert raw == canonical(schema) + b'\n'
        assert sha(raw) == item['raw_digest'] and len(raw) == item['byte_length']
        assert schema['$id'] == item['$id'] == item['schema_key']
        assert schema['$schema'] == item['dialect'] == 'https://json-schema.org/draft/2020-12/schema'
        assert item['dependency_closure'] == [] and item['local_definitions_inlined']
        for node in walk(schema):
            if '$ref' in node:
                assert node['$ref'].startswith('#/'), node['$ref']
                target = schema
                for segment in node['$ref'][2:].split('/'):
                    target = target[segment.replace('~1', '/').replace('~0', '~')]
        jsonschema.Draft202012Validator.check_schema(schema)
        schemas[item['schema_key']] = schema
        schema_hashes[item['schema_key']] = item['raw_digest']
        if item['scope'] == 'CANONICAL_WIRE':
            kind, version = item['schema_key'].split('::', 1)[1].rsplit('/', 1)
            row = rows[(kind, version)]
            assert row['schema_ref'] == item['schema_key']
            if row['reference_contract_mode'] == 'EXPLICIT_COMPLETE':
                assert schema['x-bdb-material-refs'] == row['material_refs'], (kind, version)
    assert len(schemas) == len(catalog) == 41
    spec_refs = schemas['BDB_SCHEMA_REGISTRY::spec_revision/1']['x-bdb-material-refs']
    assert any(ref['field'] == 'protocol_profile_ref' and ref['ref_class'] == 'PINNED_PROFILE_REF' for ref in spec_refs)
    checks.append('41 executable schemas meta-valid; exact bytes/digests/length/$id/dialect/local dependency closure; explicit ref parity')
    profiles = {p.stem: read(p) for p in (C / 'profiles').glob('*.json')}
    backend = profiles['BDB_R5_4_VALIDATOR_PROFILE_V1']
    assert all(importlib.metadata.version(name) == version for name, version in backend['backend'].items())
    checks.append('validator backend installed versions: ' + str({n: importlib.metadata.version(n) for n in ['jsonschema', 'attrs', 'jsonschema-specifications', 'referencing', 'rpds-py']}))
    roots = [read(p) for p in (C / 'objects').glob('*.json')]
    fixture = read(C / 'fixtures/NF02_OBJECT_FIXTURE_R5_4.json')
    all_objects = roots + fixture['objects'] + fixture['commits'] + fixture['receipts']
    object_index = {obj['ref']['revision_digest']: obj for obj in all_objects}
    for obj in all_objects:
        key = f"BDB_SCHEMA_REGISTRY::{obj['kind']}/{obj['version']}"
        errors = list(jsonschema.Draft202012Validator(schemas[key]).iter_errors(obj['body']))
        assert not errors, (obj['kind'], [(list(err.path), err.message) for err in errors[:5]])
        assert sha(f"BDB2/{obj['kind']}/{obj['version']}".encode('ascii') + b'\0' + canonical(obj['body'])) == obj['ref']['revision_digest'], obj['kind']
        assert obj['ref']['kind'] == obj['kind']
        assert obj['ref']['schema_revision_ref']['revision_digest'] == schema_hashes[key]
        for node in walk(obj['body']):
            if 'profile_id' in node and set(node) == {'profile_id', 'revision_digest'}:
                matches = list((C / 'profiles').glob(node['profile_id'] + '.json'))
                if node['profile_id'] == 'NF02_SYNTHETIC_VALIDATION_PREMISES_V1':
                    matches = [C / 'fixtures/SYNTHETIC_VALIDATION_PREMISES.json']
                assert len(matches) == 1 and sha(matches[0].read_bytes()) == node['revision_digest'], node
            if 'schema_revision_ref' in node and 'revision_digest' in node and node['kind'] != 'schema':
                assert node['revision_digest'] in object_index, node
                assert object_index[node['revision_digest']]['ref'] == node, node
    checks.append(f'{len(all_objects)} full synthetic/root objects schema-valid and independent ObjectDigest/typed ref/profile identity checks')
    sr = next(o for o in roots if o['kind'] == 'schema_registry')
    bindings = sr['body']['bindings']
    assert len(bindings) == len({b['schema_key'] for b in bindings}) == 39
    assert {b['schema_key'] for b in bindings} == {i['schema_key'] for i in catalog if i['scope'] == 'CANONICAL_WIRE'}
    for binding in bindings:
        item = next(i for i in catalog if i['schema_key'] == binding['schema_key'])
        assert binding['status'] == 'ACTIVE'
        assert binding['schema_raw_ref']['raw_digest'] == item['raw_digest']
        assert binding['schema_raw_ref']['byte_length'] == item['byte_length']
    bundle = read(C / 'INSTALLATION_PIN_BUNDLE_R5_4.json')
    install = next(o for o in roots if o['kind'] == 'installation_bootstrap_profile')
    for key, ref in bundle['initial_pins'].items():
        assert install['body'][key] == ref
    assert bundle['governing_normative_candidate_set_sha256'] == manifest['normative_candidate_set_sha256']
    assert bundle['external_schema_root']['raw_digest'] == schema_hashes['BDB_SCHEMA_REGISTRY::schema_registry/2']
    assert set(bundle['bootstrap_executable_schema_keys']) <= set(schema_hashes)
    assert bundle['activation_status'] == 'CANDIDATE_PREPARED_NOT_INSTALLED'
    checks.append('39 exact SchemaRegistry/2 bindings; external schema root and all eight installation pins; normative set pin; no installation performed')
    # Hash dependency DAG is checked independently, ignoring schema RawDigests.
    visiting, done = set(), set()
    def visit(digest):
        assert digest not in visiting, ('object hash cycle', digest)
        if digest in done:
            return
        visiting.add(digest)
        for node in walk(object_index[digest]['body']):
            if 'schema_revision_ref' in node and 'revision_digest' in node:
                visit(node['revision_digest'])
        visiting.remove(digest)
        done.add(digest)
    for digest in object_index:
        visit(digest)
    b = fixture['binding']['body']
    a = fixture['assignment']['ref']
    e = fixture['evidence']['body']
    r = fixture['result']['body']
    assert b['assignment_ref'] == e['assignment_ref'] == a
    assert e['package_binding_ref'] == fixture['binding']['ref']
    assert r['admission_evidence_ref'] == fixture['evidence']['ref']
    assert b['binding_input_history_cut']['accepted_head_seq'] < fixture['cuts']['start_input']['accepted_head_seq']
    assert e['admission_input_history_cut']['accepted_head_seq'] < r['result_input_history_cut']['accepted_head_seq']
    for seq, name in [(4, 'binding'), (6, 'evidence'), (7, 'result')]:
        assert fixture['commits'][seq-1]['body']['ordered_event_bodies'] == [
            {'event_type': 'ArtifactAccepted', 'artifact_ref': fixture[name]['ref']}]
    checks.append('full fixture typed-ref hash DAG acyclic; assignment/binding/evidence/result exact relation; distinct prior commits')
    accepted = {obj['ref']['revision_digest'] for obj in roots}
    prior_head = None
    for seq, commit in enumerate(fixture['commits'], 1):
        body = commit['body']
        assert body['commit_seq'] == seq
        expected_parent = 'EMPTY_HISTORY' if seq == 1 else {
            'campaign_id': body['campaign_id'], 'commit_seq': seq-1, 'commit_hash': prior_head}
        assert body['prev_history_ref'] == body['expected_parent_head'] == expected_parent
        closure = {ref['revision_digest'] for ref in body['immutable_object_refs']}
        assert not closure & accepted
        for ref in body['immutable_object_refs']:
            obj = object_index[ref['revision_digest']]
            if obj['kind'] == 'assignment_package_binding':
                assert obj['body']['assignment_ref']['revision_digest'] in accepted
            if obj['kind'] == 'lane_result_admission_evidence':
                assert obj['body']['package_binding_ref']['revision_digest'] in accepted
            if obj['kind'] == 'bdb_audit_lane_result':
                assert obj['body']['admission_evidence_ref']['revision_digest'] in accepted
        receipt = fixture['receipts'][seq-1]['body']
        assert receipt['accepted_commit_ref'] == commit['ref']
        assert receipt['command_ref'] == body['command_ref']
        accepted |= closure
        prior_head = commit['ref']['revision_digest']
    checks.append('seven modeled immutable history closures/parent chain/receipts and NF02 PRIOR_ACCEPTED_ONLY boundaries consistent')
    known = read(C / 'fixtures/NF02_KNOWN_ANSWERS_R5_4.json')
    for label in ['assignment', 'binding', 'evidence', 'result', 'schema_registry']:
        obj = sr if label == 'schema_registry' else fixture[label]
        preimage = f"BDB2/{obj['kind']}/{obj['version']}".encode('ascii') + b'\0' + canonical(obj['body'])
        assert known['canonical_body_utf8_hex'][label] == canonical(obj['body']).hex()
        assert known['object_digest_preimage_hex'][label] == preimage.hex()
        assert known['object_digests'][label] == sha(preimage)
    for file, raw_key, manifest_key, schema_key in [
        ('input_package.zip', 'raw_package_digest', 'package_manifest', 'NF02_INPUT_PACKAGE_TRANSPORT_V2'),
        ('audit_result.zip', 'raw_result_digest', 'result_manifest', 'NF02_RESULT_TRANSPORT_V2')]:
        raw = (C / 'fixtures' / file).read_bytes()
        assert sha(raw) == known[raw_key]
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            assert names == sorted(set(names), key=lambda s: s.encode('utf-8'))
            assert all(i.compress_type == zipfile.ZIP_STORED and i.date_time == (1980, 1, 1, 0, 0, 0) for i in archive.infolist())
            body = json.loads(archive.read('MANIFEST.json'), object_pairs_hook=unique)
            assert body == fixture[manifest_key]
            jsonschema.Draft202012Validator(schemas['BDB_PROFILE_SCHEMA::' + schema_key]).validate(body)
            records = fixture['package_semantic_descriptor']['members'] if file == 'input_package.zip' else body['members']
            for member in records:
                data = archive.read(member['path'])
                assert sha(data) == member['raw_digest'] and len(data) == member['byte_length']
    assert sha(canonical(fixture['package_semantic_descriptor'])) == known['package_semantic_digest']['digest']
    assert sha((C / 'fixtures/repacked_input_package.zip').read_bytes()) == known['raw_repacked_package_digest'] != known['raw_package_digest']
    with zipfile.ZipFile(C / 'fixtures/input_package.zip') as first, zipfile.ZipFile(C / 'fixtures/repacked_input_package.zip') as second:
        assert first.namelist() == second.namelist()
        assert all(first.read(name) == second.read(name) for name in first.namelist())
    checks.append('known-answer ObjectDigest preimages/raw ZIP hashes/transport schemas/member bytes/semantic checksum and repack raw separation')
    vectors = read(C / 'BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json')
    old = read(CONTEXT / 'BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json')
    assert vectors['vectors'][:117] == old['vectors']
    expected_ids = set(re.findall(r'^\| (NF02_[A-Z0-9_]+) \|', (REPO / 'docs/NF02_NORMATIVE_CONTRACT_DECISION_PROPOSAL.md').read_text(encoding='utf-8'), re.M))
    additions = vectors['vectors'][117:149]
    assert len(additions) == len(expected_ids) == 32
    assert {v['id'] for v in additions} == expected_ids
    for vector in additions:
        assert vector['input']['fixture_ref']['raw_digest'] == sha((C / vector['input']['fixture_ref']['file']).read_bytes())
        if vector['expected']['result'] == 'REJECT':
            assert vector['expected']['canonical_state_mutation'] == 'NONE'
        scenario_ref = vector['input']['scenario_ref']
        raw = (C / scenario_ref['file']).read_bytes()
        assert sha(raw) == scenario_ref['raw_digest'] and len(raw) == scenario_ref['byte_length']
        scenario = read(C / scenario_ref['file'])
        assert scenario['vector_id'] == vector['id']
        assert scenario['operation'] == vector['input']['operation']
        assert scenario['mutation'] == vector['input']['mutation']
        assert scenario['mandatory_variants'] == vector['input']['variants']
        assert scenario['scope'] == 'FROZEN_INPUT_AND_RUNNER_INSTRUCTIONS_NOT_EXECUTED'
        for node in walk(scenario['parameters']):
            if set(node) == {'file', 'raw_digest', 'byte_length'}:
                data = (C / node['file']).read_bytes()
                assert sha(data) == node['raw_digest'] and len(data) == node['byte_length']
    assert vectors['runtime_execution_status'] == 'NOT_RUN_N5_N11_NOT_IMPLEMENTED'
    checks.append('117 inherited exact +32 complete proposal IDs and adversarial variants; negative no-state-mutation; runtime NOT_RUN')
    from parity import check_governance
    checks.extend(check_governance(manifest))
    return manifest, readback, checks, catalog, sr


if __name__ == '__main__':
    manifest, readback, checks, catalog, sr = run()
    print(json.dumps({'status': 'PASS_ARTIFACT_SELF_AUDIT_N1_N4_ONLY', 'checks': checks,
                      'readback_count': len(readback), 'runtime': 'NOT_RUN'}, ensure_ascii=False, indent=2))


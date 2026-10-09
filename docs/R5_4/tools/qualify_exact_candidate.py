"""Exact candidate qualification under the owner's explicit author-only decision.

This task-specific governance script neither generates candidate bytes nor
installs runtime authority. Source pins must still match before implementation.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

from verify_candidate import C, E, REPO, ROOT, canonical, read, run, sha


def governance_contract_conflicts(manifest):
    text = (C / 'BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md').read_text(encoding='utf-8')
    section187 = text.split('## 187.2.', 1)[1].split('# 188.', 1)[0]
    section192 = text.split('### 192.2.', 1)[1]
    errors = []
    if ('author_verdict = R5_4_N1_N4_AUTHOR_SELF_AUDIT_PASS' in section187
            and 'author_verdict=R5_4_AUTHOR_NORMATIVE_FINAL_SELF_AUDIT_PASS' in section192):
        errors.append({'code': 'R5_4_AUTHOR_VERDICT_CONTRACT_CONFLICT',
                       'section_187_2': 'R5_4_N1_N4_AUTHOR_SELF_AUDIT_PASS; explicitly successor governance record/2 only',
                       'section_192_2': 'R5_4_AUTHOR_NORMATIVE_FINAL_SELF_AUDIT_PASS; AuthorBaselineQualificationRecord/2'})
    if ('równa się liczbie normatywnych candidate files' in section187
            and 'readback_verified_file_count (all normative plus machine entries)' in section192):
        errors.append({'code': 'R5_4_READBACK_COUNT_CONTRACT_CONFLICT',
                       'section_187_2_required': len(manifest['normative_candidate_files']),
                       'section_192_2_required': len(manifest['normative_candidate_files']) + len(manifest['machine_candidate_files'])})
    return errors


def main():
    manifest, entries, checks, catalog, schema_registry = run()
    expected = {
        'normative_candidate_set_sha256': '9488a12d644f8ac17bba737af18f3bd1d6147a7051b94ead9c89923b626b2a02',
        'machine_candidate_set_sha256': 'a2e094538948c02f78f07265a3a0abeab90b06c0d21a126294ce97f68b7d92ce'}
    assert all(manifest[key] == value for key, value in expected.items()), 'R5_4_CANDIDATE_IDENTITY_MISMATCH'
    manifest_raw = sha((E / 'BDB_AUDIT_V2_R5_4_MANIFEST_SHA256.json').read_bytes())
    assert manifest_raw == 'd2f38cfad4a0d4e3ae96f179addb6fd7ad817250f4998968eb5a01487dd0e3cd'
    assert schema_registry['ref']['revision_digest'] == 'de514548328391f271dac2f6b253b8d47ac8d6e5406e6e0781a2bfb18c9cbc1e'
    conflicts = governance_contract_conflicts(manifest)
    if conflicts:
        print(json.dumps({'qualification_gate': 'R5_4_QUALIFICATION_FAILED', 'final_gate': 'SPEC_CONFLICT',
                          'candidate_drift': False, 'conflicts': conflicts,
                          'activation_authorized_by_qualification': False}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    evidence = E / 'qualification'
    evidence.mkdir(exist_ok=True)
    def write(name, obj):
        path = evidence / name
        raw = canonical(obj) + b'\n' if not isinstance(obj, str) else obj.encode('utf-8')
        if path.exists():
            raise RuntimeError('IMMUTABLE_QUALIFICATION_EVIDENCE_ALREADY_EXISTS: ' + name)
        path.write_bytes(raw)
        return sha(raw)
    snapshot = {}
    for filename in ['R5_4_READBACK.json', 'R5_4_SELF_AUDIT.json', 'BDB_AUDIT_V2_SELF_AUDIT_REPORT_R5_4.md']:
        destination = evidence / filename
        if destination.exists():
            assert destination.read_bytes() == (E / filename).read_bytes(), 'QUALIFICATION_SNAPSHOT_DRIFT'
        else:
            shutil.copyfile(E / filename, destination)
        snapshot[filename] = sha(destination.read_bytes())
    readback = read(evidence / 'R5_4_READBACK.json')
    audit = read(evidence / 'R5_4_SELF_AUDIT.json')
    assert audit['readback_raw_digest'] == snapshot['R5_4_READBACK.json']
    assert audit['candidate_manifest_raw_digest'] == readback['candidate_manifest_raw_digest'] == manifest_raw
    assert readback['readback_mismatch_count'] == 0
    governance = read(E / 'GOVERNANCE_PREPARATION_R5_4.json')
    assert governance['self_audit_raw_digest'] == snapshot['R5_4_SELF_AUDIT.json']
    assert governance['readback_raw_digest'] == snapshot['R5_4_READBACK.json']
    corpus = []
    for path in sorted(C.rglob('*')):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if path.relative_to(C).as_posix() == 'fixtures/adversarial/duplicate_manifest_keys.json':
            try:
                read(path)
            except AssertionError as exc:
                assert str(exc) == 'duplicate JSON key: assignment_ref'
            else:
                raise AssertionError('ADVERSARIAL_DUPLICATE_KEY_INPUT_NOT_REJECTED')
        elif path.suffix == '.json':
            read(path)
        elif path.suffix in {'.md', '.txt'}:
            raw.decode('utf-8-sig')
        corpus.append({'file': path.relative_to(C).as_posix(), 'raw_digest': sha(raw), 'byte_length': len(raw)})
    data = (C / 'BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md').read_text(encoding='utf-8')
    architecture = (C / 'BDB_AUDIT_V2_ARCHITECTURE_SPEC_R5_4.md').read_text(encoding='utf-8')
    proposal = (REPO / 'docs/NF02_NORMATIVE_CONTRACT_DECISION_PROPOSAL.md').read_text(encoding='utf-8')
    shapes = {
        ('assignment_package_binding', '1'): ['binding_id', 'assignment_ref', 'binding_input_history_cut', 'package_raw_ref'],
        ('lane_result_admission_evidence', '2'): ['admission_evidence_id', 'assignment_ref', 'package_binding_ref', 'result_slot_contract_ref', 'admission_input_history_cut', 'result_raw_ref'],
        ('bdb_audit_lane_result', '2'): ['lane_result_id', 'admission_evidence_ref', 'result_input_history_cut', 'result_payload'],
        ('schema_registry', '2'): ['schema_registry_id', 'artifact_contract_registry_ref', 'serialization_profile_ref', 'validator_profile_ref', 'compatibility_rules_ref', 'bindings']}
    registry = read(C / 'BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json')
    for (kind, version), fields in shapes.items():
        schema = read(C / f'schemas/{kind}__{version}.schema.json')
        row = next(r for r in registry['contracts'] if (r['kind'], r['version']) == (kind, version))
        assert schema['required'] == fields and set(schema['properties']) == set(fields) and schema['additionalProperties'] is False
        assert all(field in data and field in architecture and field in proposal for field in fields)
        assert row['canonical_role'] == 'FACT' and row['validation_profile'] == 'NF02_PROVENANCE'
        assert row['producer_authority'] == 'TRUSTED_COORDINATOR_ACCEPTANCE'
    checks += ['Four approved closed canonical body shapes match narrative/Registry/schema.',
               'Whole candidate byte inventory reread; JSON strict parsing and text UTF-8 decoding.',
               'Fresh readback/self-audit/governance hash chain verified and copied into immutable qualification snapshot.']
    source = read(E / 'R5_4_SOURCE_PREDECESSOR_PINS.json')
    commands = [['git', 'status', '--short'], ['git', 'branch', '--show-current'], ['git', 'rev-parse', 'HEAD'],
                ['git', 'rev-parse', 'HEAD^{tree}'], ['git', 'log', '-n', '10', '--oneline'], ['git', 'diff', '--check']]
    source_snapshot = []
    for command in commands:
        result = subprocess.run(command, cwd=REPO, capture_output=True, text=True, encoding='utf-8')
        assert result.returncode == 0
        source_snapshot.append({'command': command, 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
    write('Q1_SOURCE_IDENTITY.json', {'head': source['head'], 'tree': source['tree'], 'branch': source['branch'], 'commands': source_snapshot})
    approval = {'record_type': 'EXTERNAL_OWNER_EXACT_CANDIDATE_ASSURANCE_DECISION',
                'date': '2026-10-06', 'governance_actor_ref': 'OWNER_EXPLICIT_CHAT_AUTHORIZATION_R5_4_2026_10_06',
                'trusted_evidence': 'Direct human reply to the exact-manifest author-only assurance question in this task',
                'owner_reply_verbatim': 'Akceptuję author-only assurance i upoważniam qualification record, aktywację oraz N5–N8.',
                'candidate_manifest_raw_digest': manifest_raw, **expected,
                'owner_assurance_decision': 'IMPLEMENTATION_MAY_PROCEED_UNDER_AUTHOR_ONLY_ASSURANCE',
                'authorized_scope': ['EXACT_QUALIFICATION_RECORD', 'Q2_ACTIVATION', 'N5', 'N6', 'N7', 'N8'],
                'independent_review_or_freeze': 'NOT_CLAIMED', 'NF02_closure': 'NOT_AUTHORIZED_BY_THIS_DECISION'}
    owner_hash = write('OWNER_EXACT_CANDIDATE_ASSURANCE_DECISION.json', approval)
    record = read(E / 'AUTHOR_BASELINE_QUALIFICATION_R5_4.template.json')
    record.update({'status': 'VALID_AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE',
                   'author_baseline_qualification_id': 'BDB-AUTHOR-BASELINE-QUALIFICATION-R5_4-2026-10-06-001',
                   'created_at': datetime.now(timezone.utc).isoformat(),
                   'governance_actor_ref': approval['governance_actor_ref'], 'owner_assurance_decision': approval['owner_assurance_decision'],
                   'author_verdict': 'R5_4_AUTHOR_NORMATIVE_FINAL_SELF_AUDIT_PASS',
                   'owner_decision_raw_digest': owner_hash, 'owner_decision_storage_id': str(evidence / 'OWNER_EXACT_CANDIDATE_ASSURANCE_DECISION.json'),
                   'effective_derived_state': {'AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE': 'YES'},
                   'final_reaudit_register_storage_id': str(evidence / 'R5_4_SELF_AUDIT.json'),
                   'final_reaudit_register_raw_digest': snapshot['R5_4_SELF_AUDIT.json'],
                   'readback_raw_digest': snapshot['R5_4_READBACK.json'], 'readback_storage_id': str(evidence / 'R5_4_READBACK.json'),
                   'registry_id': registry['registry_id'], 'registry_raw_digest': sha((C / 'BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json').read_bytes()),
                   'artifact_contract_registry_ref': schema_registry['body']['artifact_contract_registry_ref'],
                   'schema_registry_ref': schema_registry['ref'],
                   'golden_vector_set_id': read(C / 'BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json')['vector_set_id'],
                   'golden_vector_set_raw_digest': sha((C / 'BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_4.json').read_bytes()),
                   'qualification_scope': 'EXACT NORMATIVE/MACHINE IMPLEMENTATION BASELINE ONLY; no production acceptance, NF02 closure or independent assurance',
                   'note': 'Owner explicitly authorizes author-only assurance for the exact manifest. Frozen candidate bytes/README flags remain unchanged. Independent freeze is false.'})
    record_hash = write('AUTHOR_BASELINE_QUALIFICATION_R5_4.json', record)
    assert record['readback_verified_file_count'] == len(entries) == 117
    result_hash = write('Q1_QUALIFICATION_CHECKS.json', {'gate': 'R5_4_AUTHOR_QUALIFIED_FOR_IMPLEMENTATION',
                        'candidate_manifest_raw_digest': manifest_raw, **expected, 'checks': checks, 'corpus_inventory': corpus,
                        'qualification_record_raw_digest': record_hash, 'source_pins_verified_before_implementation': True,
                        'independent_assurance': False, 'runtime_tests': 'NOT_RUN'})
    report = '# R5.4 exact-candidate governance qualification\n\nGate: **R5_4_AUTHOR_QUALIFIED_FOR_IMPLEMENTATION**.\n\n'
    report += f'Exact manifest RawDigest `{manifest_raw}`; normative set `{expected["normative_candidate_set_sha256"]}`; machine set `{expected["machine_candidate_set_sha256"]}`; SchemaRegistry/2 ObjectDigest `{schema_registry["ref"]["revision_digest"]}`. All match the user-pinned subject.\n\n'
    report += f'Fresh required commands `python docs/R5_4/tools/verify_candidate.py` and `python docs/R5_4/tools/finalize_delivery.py` both exited 0. 117 readbacks, zero mismatches; 41 schemas and 39 canonical bindings. Candidate bytes were not regenerated or edited. Source/predecessor pins matched before implementation. Q1 source commands are captured in `evidence/qualification/Q1_SOURCE_IDENTITY.json`.\n\n'
    report += f'Owner explicitly accepted author-only assurance via direct reply. Immutable owner decision RawDigest `{owner_hash}`. Qualification record `evidence/qualification/AUTHOR_BASELINE_QUALIFICATION_R5_4.json`, RawDigest `{record_hash}`. Check record RawDigest `{result_hash}`. Fresh self-audit/readback snapshots are retained under `evidence/qualification/`; later implementation does not rewrite them.\n\n'
    report += '\n'.join('- ' + check for check in checks) + '\n\n'
    report += 'AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE=YES is externally derived. INDEPENDENT_ASSURANCE=false; FOUNDATION_SPEC_BASELINE_FROZEN=false. No independent verdict or runtime PASS. Q2 remains a separate authenticated exact installation step, before N5–N8 acceptance. All original candidate status flags remain historical and unchanged.\n'
    (ROOT / 'R5_4_GOVERNANCE_QUALIFICATION_REPORT.md').write_text(report, encoding='utf-8')
    print(json.dumps({'gate': 'R5_4_AUTHOR_QUALIFIED_FOR_IMPLEMENTATION', 'qualification_record_raw_digest': record_hash,
                      'owner_decision_raw_digest': owner_hash, 'candidate_drift': False, 'runtime': 'NOT_RUN'}, indent=2))


if __name__ == '__main__':
    main()

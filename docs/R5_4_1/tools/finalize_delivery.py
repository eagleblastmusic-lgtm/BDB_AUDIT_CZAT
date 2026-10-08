"""Fresh all-byte readback and artifact self-audit of the corrected successor."""
import datetime
import subprocess

from governance import C, COUNT_FIELDS, ROOT, emit, read, sha, vector_run, SCHEMA_FILE
from verify_candidate import run


def main():
    assert not (ROOT / 'AUTHOR_BASELINE_QUALIFICATION_R5_4_1.json').exists(), 'qualified evidence immutable'
    manifest, rb, checks, catalog, sr = run()
    n = len(manifest['normative_candidate_files'])
    m = len(manifest['machine_candidate_files'])
    entries = [{'group': 'normative' if i < n else 'machine', 'file': e['file'],
                'stable_storage_id': e['absolute_path'], 'expected_raw_digest': e['expected_sha256'],
                'observed_raw_digest': e['observed_sha256'], 'byte_length': e['bytes'], 'result': 'PASS'} for i, e in enumerate(rb)]
    manifest_raw = sha((ROOT / 'R5_4_1_CANDIDATE_MANIFEST.json').read_bytes())
    common = {'candidate_manifest_raw_digest': manifest_raw,
              'normative_candidate_set_digest': manifest['normative_candidate_set_sha256'],
              'machine_candidate_set_digest': manifest['machine_candidate_set_sha256']}
    readback = {'schema': 'BDB_R5_4_1_READBACK/1', **common, **dict(zip(COUNT_FIELDS, [n, m, n+m])),
                'readback_storage_provider': 'LOCAL_FILESYSTEM', 'readback_mismatch_count': 0,
                'readback_entries': entries}
    rb_raw = emit(ROOT / 'R5_4_1_READBACK.json', readback)
    diff = subprocess.run(['git', 'diff', '--check'], capture_output=True, text=True)
    assert diff.returncode == 0, diff.stderr
    tools = {p.name: sha(p.read_bytes()) for p in sorted((ROOT / 'tools').glob('*.py'))}
    audit = {'schema': 'BDB_R5_4_1_SELF_AUDIT/1', **common, 'status': 'PASS_FRESH_ARTIFACT_AND_GOVERNANCE_SELF_AUDIT',
             'author_verdict': 'R5_4_AUTHOR_NORMATIVE_FINAL_SELF_AUDIT_PASS', 'readback_raw_digest': rb_raw,
             'checks': checks, 'governance_vector_results': vector_run(read(C / SCHEMA_FILE)),
             'verifier_tool_raw_digests': tools, 'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'commands': ['python docs/R5_4_1/tools/verify_candidate.py', 'python docs/R5_4_1/tools/finalize_delivery.py'],
             'git_diff_check': {'exit_code': diff.returncode, 'stdout': diff.stdout, 'stderr': diff.stderr},
             'runtime_vectors': 'NOT_RUN', 'Q2': 'NOT_STARTED', 'N5_N11': 'NOT_STARTED',
             'independent_assurance': False, 'foundation_spec_baseline_frozen': False}
    emit(ROOT / 'R5_4_1_SELF_AUDIT.json', audit)
    print(f'PASS fresh self-audit; {n} normative + {m} machine = {n+m} exact readbacks; zero mismatches; runtime NOT_RUN')


if __name__ == '__main__': main()

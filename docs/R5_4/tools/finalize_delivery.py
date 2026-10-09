"""Produce truthful external N1-N4 evidence after frozen-candidate readback."""
import datetime
import json
import pathlib
import subprocess

from verify_candidate import C, E, REPO, ROOT, canonical, read, run, sha


def emit(name, value):
    path = E / name
    raw = (canonical(value) + b'\n') if not isinstance(value, str) else value.encode('utf-8')
    path.write_bytes(raw)
    return sha(raw)


def main():
    manifest, readback, checks, catalog, sr = run()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    manifest_file = E / 'BDB_AUDIT_V2_R5_4_MANIFEST_SHA256.json'
    manifest_raw = sha(manifest_file.read_bytes())
    pins = read(E / 'R5_4_SOURCE_PREDECESSOR_PINS.json')
    status = subprocess.run(['git', 'status', '--short'], cwd=REPO, capture_output=True, text=True, encoding='utf-8')
    diff = subprocess.run(['git', 'diff', '--check'], cwd=REPO, capture_output=True, text=True, encoding='utf-8')
    assert status.returncode == 0 and diff.returncode == 0
    hardbreaks = 0
    for path in ROOT.rglob('*'):
        if path.is_file() and path.suffix in {'.md', '.json', '.py'}:
            for line in path.read_text(encoding='utf-8-sig').splitlines():
                assert not line.startswith(('<<<<<<<', '=======', '>>>>>>>')), str(path)
                if line.rstrip() != line:
                    assert path.suffix == '.md' and line.endswith('  ') and '\t' not in line[len(line.rstrip()):], str(path)
                    hardbreaks += 1
    log = subprocess.check_output(['git', 'log', '-n', '10', '--oneline'], cwd=REPO, text=True, encoding='utf-8')
    tools = {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in sorted((ROOT / 'tools').glob('*.py'))}
    n = len(manifest['normative_candidate_files'])
    m = len(manifest['machine_candidate_files'])
    owner_raw = emit('OWNER_DESIGN_APPROVAL_R5_4.json', {
        'record_type': 'EXTERNAL_OWNER_DESIGN_APPROVAL', 'date': '2026-10-06', 'authority': 'DIRECT_HUMAN_USER_MESSAGE_IN_THIS_TASK',
        'approved_proposal_raw_digest': pins['proposal_raw_digest'],
        'decisions': ['NEW FOUNDATION REVISION REQUIRED: R5.4; preserve R5.3/R5.3.1 bytes',
                      'assignment_package_binding/1 sole authority for exact immutable package of exact prior accepted assignment',
                      'NEW_CAMPAIGN_ONLY: no in-place upgrade, retrospective binding or /1 to /2 mapping'],
        'execution_authorized': 'N1-N4 CANDIDATE PREPARATION ONLY',
        'exact_generated_candidate_qualification': 'NOT_GRANTED_BY_DESIGN_APPROVAL',
        'author_only_risk_waiver': 'NOT_INFERRED', 'runtime_implementation': 'N5-N11_NOT_AUTHORIZED_IN_THIS_TASK'})
    rb = {'schema': 'BDB_R5_4_STORAGE_READBACK/1', 'created_at': now, 'readback_storage_provider': 'LOCAL_FILESYSTEM',
          'candidate_manifest_raw_digest': manifest_raw, 'normative_candidate_set_digest': manifest['normative_candidate_set_sha256'],
          'machine_candidate_set_digest': manifest['machine_candidate_set_sha256'],
          'readback_verified_file_count': n+m, 'readback_verified_normative_count': n, 'readback_verified_machine_count': m,
          'readback_mismatch_count': 0, 'scope': 'LOCAL EXACT BYTES ONLY; no Drive upload/readback or independent assurance',
          'readback_entries': [{'group': 'normative' if i < n else 'machine', 'file': item['file'],
                              'stable_storage_id': item['absolute_path'], 'expected_raw_digest': item['expected_sha256'],
                              'observed_raw_digest': item['observed_sha256'], 'byte_length': item['bytes'], 'result': 'PASS'}
                              for i,item in enumerate(readback)]}
    rb_raw = emit('R5_4_READBACK.json', rb)
    audit = {'schema': 'BDB_R5_4_ARTIFACT_SELF_AUDIT/1', 'created_at': now, 'status': 'PASS_ARTIFACT_SELF_AUDIT_N1_N4_ONLY',
             'candidate_manifest_raw_digest': manifest_raw, 'normative_candidate_set_digest': manifest['normative_candidate_set_sha256'],
             'machine_candidate_set_digest': manifest['machine_candidate_set_sha256'], 'readback_raw_digest': rb_raw,
             'checks': checks, 'commands': [{'command': 'python docs/R5_4/tools/verify_candidate.py', 'result': 'PASS_ARTIFACT_ONLY'},
                                           {'command': 'git diff --check', 'exit_code': diff.returncode, 'stdout': diff.stdout, 'stderr': diff.stderr}],
             'tool_raw_digests': tools, 'runtime_tests': 'NOT_RUN', 'N5_N11': 'NOT_IMPLEMENTED',
             'text_check': {'conflict_markers': 0, 'unintended_trailing_whitespace': 0, 'preserved_markdown_hardbreaks': hardbreaks},
             'independent_assurance': False, 'author_qualified_implementation_baseline': 'PENDING_EXTERNAL_QUALIFICATION_RECORD',
             'foundation_spec_baseline_frozen': False,
             'limitations': ['Schema validation proves neither producer authority nor history acceptance.',
                            'Synthetic model premises do not qualify legacy/source/executor/trust enforcement.',
                            'Design vectors are expectations; production/adversarial qualification N9-N10 and E2E N11 remain required.',
                            'Prepared installation is not an activated/installed authority.',
                            'Remaining unbound Registry keys reject at runtime; this SchemaRegistry freezes the initial bootstrap/NF02 subset.']}
    audit_raw = emit('R5_4_SELF_AUDIT.json', audit)
    emit('BDB_AUDIT_V2_SELF_AUDIT_REPORT_R5_4.md', '# R5.4 artifact self-audit — N1–N4\n\n'
         + 'Result: **PASS_ARTIFACT_SELF_AUDIT_N1_N4_ONLY**. No runtime qualification is claimed.\n\n'
         + f'Manifest RawDigest: `{manifest_raw}`. Normative set: `{manifest["normative_candidate_set_sha256"]}`. Machine set: `{manifest["machine_candidate_set_sha256"]}`.\n\n'
         + f'Local disk readback: {n+m} files ({n} normative, {m} machine), zero mismatches. Readback RawDigest `{rb_raw}`. Self-audit JSON RawDigest `{audit_raw}`.\n\n'
         + '\n'.join('- '+check for check in checks) + '\n\n'
         + 'Schema/meta/hash/fixture checks above are artifact checks. All 149 runtime vectors are NOT_RUN. Existing remediation test evidence is not reused as R5.4 runtime evidence. External qualification and actual installation remain pending.\n')
    common = {'candidate_manifest_schema': manifest['schema'], 'candidate_manifest_storage_id': str(manifest_file),
              'candidate_manifest_raw_digest': manifest_raw, 'normative_candidate_set_digest': manifest['normative_candidate_set_sha256'],
              'machine_candidate_set_digest': manifest['machine_candidate_set_sha256']}
    emit('AUTHOR_BASELINE_QUALIFICATION_R5_4.template.json', {
        'record_type': 'AuthorBaselineQualificationRecord/2', 'status': 'TEMPLATE_PENDING_AUTHORIZED_EXACT_CANDIDATE_DECISION',
        'author_baseline_qualification_id': 'BDB-AUTHOR-BASELINE-QUALIFICATION-R5_4-PENDING',
        'created_at': None, 'governance_actor_ref': None, 'owner_assurance_decision': None, 'author_verdict': None,
        **common, 'final_reaudit_register_storage_id': str(E / 'R5_4_SELF_AUDIT.json'), 'final_reaudit_register_raw_digest': audit_raw,
        'readback_storage_provider': 'LOCAL_FILESYSTEM', 'readback_verified_file_count': n+m,
        'readback_verified_normative_count': n, 'readback_verified_machine_count': m, 'readback_mismatch_count': 0,
        'readback_entries': rb['readback_entries'], 'independent_assurance': False, 'foundation_spec_baseline_frozen': False,
        'effective_derived_state': {'AUTHOR_QUALIFIED_IMPLEMENTATION_BASELINE': None},
        'note': 'Not a valid qualification record; missing authorized exact-candidate risk decision/actor/verdict. Never enables implementation or runtime activation.'})
    emit('FOUNDATION_BASELINE_FREEZE_DECISION_R5_4.template.json', {
        'record_type': 'foundation_baseline_freeze_decision/1', 'status': 'TEMPLATE_PENDING_GENUINE_INDEPENDENT_REVIEW',
        'foundation_freeze_decision_id': None, 'baseline_id': 'BDB-AUDIT-V2-R5_4',
        'candidate_manifest_raw_digest': manifest_raw, 'candidate_manifest_schema': manifest['schema'],
        'reviewed_candidate_set_digest': manifest['normative_candidate_set_sha256'],
        'independent_review_raw_digest': None, 'independent_review_verdict': None, 'reason_codes': [],
        'decision': None, 'governance_actor_ref': None, 'created_at': None,
        'note': 'No freeze decision or independent assurance. Exact manifest binds machine closure; review must cover both sets.'})
    emit('GOVERNANCE_PREPARATION_R5_4.json', {
        'status': 'EXACT_CANDIDATE_PREPARED_FOR_QUALIFICATION', **common, 'owner_design_approval_raw_digest': owner_raw,
        'readback_raw_digest': rb_raw, 'self_audit_raw_digest': audit_raw,
        'author_qualified_implementation_baseline': 'PENDING_EXTERNAL_QUALIFICATION_RECORD',
        'foundation_spec_baseline_frozen': False, 'independent_assurance': False,
        'installation_status': 'CANDIDATE_PREPARED_NOT_INSTALLED',
        'next_governance_step': 'Review exact immutable manifest and both sets. Either genuine independent review/freeze under inherited governance, or explicit owner author-only risk decision and completed record/2. Neither is inferred here.',
        'hash_dependency_order': ['candidate bytes', 'manifest', 'readback', 'artifact self-audit', 'external qualification decision', 'authenticated installation', 'new campaign genesis'],
        'source_identity_checked_again_before_activation': True})
    binding_table = {'schema_registry_object_ref': sr['ref'], 'schema_registry_body_file': 'objects/schema_registry__2.json',
                     'installation_bundle': 'INSTALLATION_PIN_BUNDLE_R5_4.json',
                     'bindings': [{**b, 'file': next(x['file'] for x in catalog if x['schema_key'] == b['schema_key']),
                                    '$id': next(x['$id'] for x in catalog if x['schema_key'] == b['schema_key']),
                                    'dialect': next(x['dialect'] for x in catalog if x['schema_key'] == b['schema_key'])} for b in sr['body']['bindings']],
                     'unbound_registered_keys': sorted(r['schema_ref'] for r in read(C / 'BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY_R5_4.json')['contracts']
                                                      if r['schema_ref'] not in {b['schema_key'] for b in sr['body']['bindings']}),
                     'unbound_acceptance': 'FORBIDDEN', 'runtime_installation_status': 'NOT_INSTALLED'}
    emit('R5_4_SCHEMA_BINDING_TABLE.json', binding_table)
    emit('R5_4_SCHEMA_BINDING_TABLE.md', '# Exact SchemaRegistry/2 candidate binding table\n\n'
         + f'ObjectDigest: `{sr["ref"]["revision_digest"]}`. 39 exact ACTIVE bindings in candidate; installation NOT_INSTALLED. All remaining registered keys fail closed.\n\n'
         + '| Semantic schema key / executable $id | File | RawDigest | Bytes |\n|---|---|---|---:|\n'
         + '\n'.join(f'| `{b["schema_key"]}` | `{b["file"]}` | `{b["schema_raw_ref"]["raw_digest"]}` | {b["schema_raw_ref"]["byte_length"]} |' for b in binding_table['bindings'])
         + '\n\nAll use draft2020-12, inline local definitions only and no external schema dependencies. Two external ZIP manifest schemas are catalog-pinned profile schemas, not extra canonical kinds.\n')
    delta = [
        ('N5', 'src/bdb_audit/core/registry.py; schemas/binding.py; schemas/orchestration.py; history/store.py; history/authority_hooks.py',
         'Current /1 NF02 extension rows use PROVENANCE/PROPOSAL and bypass normative Registry legality.',
         'Load exact R5.4 Registry/SchemaRegistry pins; no NF02 overlay. Implement FACT binding/1 unique-by-exact-assignment acceptance, prior-only refs, exact retry/CAS, raw/history atomicity; leave historical /1 read-only.'),
        ('N6', 'src/bdb_audit/workflow/packaging.py; workflow/assignments.py; workflow/package_resume.py; workflow/manual_stage.py; execution/adapters.py; history/raw_artifacts.py',
         'Current package metadata/job context does not establish accepted immutable package authorization.',
         'Finalize exact profiled package after accepted A; store durable raw; accept B in its own commit; separate later STARTED; deliver only reverified retained raw. Semantic checksum stays distinct from ZIP RawDigest. No retrospective B or DeliveryReceipt.'),
        ('N7', 'src/bdb_audit/workflow/result_proposal.py; history/authority_hooks.py; history/raw_artifacts.py; workflow result intake/normalization/completion consumers',
         'Current /1 evidence copies attempt/source/history and compares result/package self-claims; /1 result bodies and security metadata differ from closed R5.4 bodies.',
         'Construct exact E/2 from authenticated operation using prior A/B and frozen result slot; derive package context from B/A; retain result raw. In a later commit construct R/2 as exact Normalize(Q); enforce all ref/schema/profile equality and slot uniqueness. Runtime capabilities may enforce calls but are absent from canonical bodies and replay.'),
        ('N8', 'src/bdb_audit/core/registry.py; schemas/binding.py; schemas/bootstrap.py; history/store.py; workflow campaign open/create/bootstrap and version selectors',
         'Current process-generated schema/extension paths and legacy/current context selectors are not the prepared R5.4 installed authority.',
         'Authenticated qualified initial pins and legal genesis only for new campaigns; verify frozen executable bytes/digests offline before first acceptance. No latest-installed fallback, generic upgrade, old campaign write, /1→/2 mapping or retcon. Existing campaigns retain their own schema sets/read-only historical NF02 display. Missing/corrupt authority fails closed.')]
    emit('R5_4_RUNTIME_DELTA_N5_N8.json', {'scope': 'FUTURE_WORK_NOT_IMPLEMENTED', 'source_head': pins['head'],
         'source_pins_file': 'R5_4_SOURCE_PREDECESSOR_PINS.json', 'approved_contract_outranks_current_runtime': True,
         'differences': [{'task': t, 'components': c, 'current_difference': d, 'required_change': r} for t,c,d,r in delta],
         'other_scope': 'residual_risk overlay and application completion/report schema qualification are not legalized by NF02 N1-N4; required dependent lawful authority must be established before later gates',
         'runtime_tests': 'NOT_RUN'})
    emit('R5_4_RUNTIME_DELTA_N5_N8.md', '# Required future runtime delta\n\nApproved R5.4 bytes govern later implementation. No runtime files were edited by N1–N4.\n\n'
         + '\n\n'.join(f'## {t}\n\nComponents: `{c}`.\n\nObserved difference: {d}\n\nRequired change: {r}' for t,c,d,r in delta)
         + '\n\nN9 adversarial qualification, N10 complete NF02 qualification and N11 full application start/create/package/delivery/result/completions/report/restart/recovery/continue with corruption and missing-object paths remain mandatory and NOT_RUN.\n')
    report = '# R5.4 N1–N4 delivery and exact candidate identity\n\n'
    report += 'Final gate: **R5_4_NORMATIVE_CANDIDATE_READY_FOR_QUALIFICATION**. The approved C1/C2 contract model is materialized. Exact-byte governance qualification and actual installation remain pending. NF02 closure and N5–N11 execution are not claimed.\n\n'
    report += f'CURRENT_HEAD `{pins["head"]}`; CURRENT_TREE `{pins["tree"]}`; CURRENT_BRANCH `{pins["branch"]}`; preserved main `{pins["main"]}`.\n\n'
    report += f'R5.3.1 predecessor set `{pins["predecessor_candidate_set_digest"]}`; R5.3 predecessor set `{pins["predecessor_r5_3_set_digest"]}`. Predecessor manifest RawDigest `{manifest["predecessor_manifest_raw_digest"]}`; predecessor author record `{manifest["predecessor_author_qualification_raw_digest"]}`. All {len(pins["predecessor_context_raw_pins"])} Context files and {len(pins["source_pins"])} execution-source pins plus {len(pins["protected_tracked_pins"])} protected tracked pins were rehashed unchanged. Full exact predecessor/source identities: `R5_4_SOURCE_PREDECESSOR_PINS.json`.\n\n'
    report += f'R5.4 normative candidate-set SHA-256 `{manifest["normative_candidate_set_sha256"]}`. Machine candidate-set SHA-256 `{manifest["machine_candidate_set_sha256"]}`. Exact manifest RawDigest `{manifest_raw}`. Both sets use the inherited sorted `{{file,bytes,sha256}}` CJSON SHA-256 preimage; the external manifest binds both, without a self-hash cycle.\n\n'
    report += '## Registry and bindings\n\n110 predecessor contract rows unchanged; four additions: `assignment_package_binding/1`, `lane_result_admission_evidence/2`, `bdb_audit_lane_result/2`, `schema_registry/2`. Registry ID `BDB-AUDIT-V2-ARTIFACT-CONTRACT-REGISTRY-R5-4-1`, version 5. New `NF02_PROVENANCE=L1–L6`, activation/command profile constraints and explicit versioned consumer rules. Existing roles, reference classes and order-only domains unchanged; no aliases, PROVENANCE/PROPOSAL role, canonical capability or DeliveryReceipt. Full row/profile delta: `R5_4_REGISTRY_DELTA.json`.\n\n'
    report += f'41 exact executable schemas: 39 canonical wire schemas and two external manifest schemas. SchemaRegistry/2 ObjectDigest `{sr["ref"]["revision_digest"]}`. Every binding RawDigest/length/$id/dialect/dependency closure is in `R5_4_SCHEMA_BINDING_TABLE.json`, its Markdown table and candidate `SCHEMA_ARTIFACT_CATALOG_R5_4.json`. External schema root is pinned before registry validation; installation body preserves eight exact pins, and external bundle also binds this normative set/protocol-policy bundle. Unbound keys are listed explicitly and reject. No runtime authority is inferred from candidate status.\n\n'
    report += '## Golden inventory and self-audit\n\n149 Golden vectors: 117 byte-equivalent inherited vector structures and 32 new mandatory NF02 IDs, every proposal ID and variant. The successor Golden JSON binds full synthetic object/commit/cut fixtures, exact raw ZIPs, known-answer canonical preimages/hashes and 32 scenario files with concrete mutation parameters/fault boundaries, plus five adversarial byte files. Full inventory: `R5_4_GOLDEN_VECTOR_INVENTORY.json`. Negative expectations require REJECT and no canonical state mutation; mixed race/crash/replay vectors specify their stricter winner/atomicity/unauthorized-write behavior. All runtime executions NOT_RUN.\n\n'
    report += f'Artifact self-audit PASS; {n+m} local readbacks, zero mismatches; {len(checks)} recorded check groups. Evidence: `R5_4_SELF_AUDIT.json`, `R5_4_READBACK.json`, `BDB_AUDIT_V2_SELF_AUDIT_REPORT_R5_4.md`. Backend versions are frozen and checked. Source, predecessor and legacy protected bytes unchanged. No production tests reused as R5.4 evidence.\n\n'
    report += '## Governance and implementation boundary\n\n`OWNER_DESIGN_APPROVAL_R5_4.json` records the three actual owner decisions. `GOVERNANCE_PREPARATION_R5_4.json` binds manifest/readback/self-audit. Both qualification/freeze `.template.json` files remain pending with null actor/verdict/decision; they are not valid qualification decisions. Explicit exact-candidate author risk acceptance or genuine independent qualification is required under the successor/inherited governance before installation. No additional owner design decision is hidden in the prepared candidate. N1–N4 deliver preparation; N5–N8 differences are in `R5_4_RUNTIME_DELTA_N5_N8.md/json`. N9–N11 remain required.\n\n'
    report += '## Exact normative and machine file inventory\n\nEvery file below is newly created under `docs/R5_4/candidate/`; inherited normative inputs have exact predecessor bytes. Governance/evidence/tool files are external to the candidate-set preimages.\n\n| Group | Candidate-relative file | SHA-256 | Bytes |\n|---|---|---|---:|\n'
    for group in ['normative', 'machine']:
        for item in manifest[group + '_candidate_files']:
            report += f'| {group} | `{item["file"]}` | `{item["sha256"]}` | {item["bytes"]} |\n'
    report += '\nSupplemental subordinate execution plan: `../BDB_AUDIT_V2_IMPLEMENTATION_EXECUTION_PLAN_R5_4.md`, SHA-256 `' + sha((ROOT / 'BDB_AUDIT_V2_IMPLEMENTATION_EXECUTION_PLAN_R5_4.md').read_bytes()) + '`. It schedules N1–N11 and is external to the ten-file normative set.\n\n'
    report += '## Repository and exact verification commands\n\n`python docs/R5_4/tools/materialize_candidate.py` — materialized frozen candidate inputs only.\n\n`python docs/R5_4/tools/verify_candidate.py` — PASS_ARTIFACT_SELF_AUDIT_N1_N4_ONLY.\n\n`python docs/R5_4/tools/finalize_delivery.py` — repeated final disk verification and produced external evidence.\n\n`git diff --check` — exit 0. New text files additionally checked for unresolved conflict markers and unintended trailing whitespace; inherited Markdown two-space hardbreaks intentionally preserved. No commit/push/PR/tag/ref changes.\n\nWORKTREE_STATUS (existing remediation changes preserved; only new R5_4 subtree added):\n\n```text\n' + status.stdout + '```\n\nStatus warning (exit 0; no task-relevant files unreadable):\n\n```text\n' + status.stderr + '```\n\n`git log -n 10 --oneline`:\n\n```text\n' + log + '```\n'
    emit('R5_4_N1_N4_DELIVERY_REPORT.md', report)
    emit('R5_4_REPOSITORY_FINAL_CHECK.json', {'head': pins['head'], 'tree': pins['tree'], 'branch': pins['branch'],
         'status_exit_code': status.returncode, 'status': status.stdout, 'warning': status.stderr,
         'git_diff_check': {'exit_code': diff.returncode, 'stdout': diff.stdout, 'stderr': diff.stderr},
         'new_task_path': 'docs/R5_4/', 'runtime_source_drift': 'NONE', 'log_last_10': log})
    print(json.dumps({'gate': 'R5_4_NORMATIVE_CANDIDATE_READY_FOR_QUALIFICATION',
                      'normative_candidate_set_sha256': manifest['normative_candidate_set_sha256'],
                      'machine_candidate_set_sha256': manifest['machine_candidate_set_sha256'],
                      'manifest_raw_digest': manifest_raw, 'readback_count': n+m, 'mismatches': 0,
                      'schemas': len(catalog), 'bindings': len(sr['body']['bindings']), 'runtime': 'NOT_RUN'}, indent=2))


if __name__ == '__main__':
    main()

"""Frozen adversarial inputs/instructions, not a production fault runner."""
import copy
import json


def materialize(g, fixture, known, ids):
    directory = g.CANDIDATE / 'fixtures/adversarial'
    package = (g.CANDIDATE / 'fixtures/input_package.zip').read_bytes()
    result = (g.CANDIDATE / 'fixtures/audit_result.zip').read_bytes()
    schema = (g.CANDIDATE / 'schemas/assignment_package_binding__1.schema.json').read_bytes()
    artifacts = {}
    def asset(name, raw):
        file = 'fixtures/adversarial/' + name
        g.write(g.CANDIDATE / file, raw)
        ref = {'file': file, 'raw_digest': g.digest(raw), 'byte_length': len(raw)}
        artifacts[name] = ref
        return ref
    asset('schema_byte_substitution.json', schema.replace(b'"type":"object"', b'"type":"string"', 1))
    asset('package_truncated.zip', package[:-13])
    asset('result_truncated.zip', result[:-13])
    asset('package_trailing.zip', package + b'TRAILING')
    asset('duplicate_manifest_keys.json', b'{"assignment_ref":null,"assignment_ref":null}\n')
    refs = {name: fixture[name]['ref'] for name in ['assignment', 'binding', 'evidence', 'result']}
    different_ref = copy.deepcopy(refs['assignment'])
    different_ref['revision_digest'] = refs['binding']['revision_digest']
    parameters = {
        'REMOVE_GOVERNING_REGISTRY_ROW': {'kind': 'assignment_package_binding', 'version': '1', 'keep_exact_schema_bytes': True},
        'REMOVE_SCHEMA_BINDING': {'schema_key': 'BDB_SCHEMA_REGISTRY::assignment_package_binding/1'},
        'FLIP_BOUND_SCHEMA_BYTE': {'replacement_bytes_ref': artifacts['schema_byte_substitution.json'], 'keep_original_binding': True},
        'NONE': {},
        'EXISTING_BINDING_DIFFERENT_RAW': {'existing_binding_ref': refs['binding'], 'new_package_file': 'fixtures/repacked_input_package.zip', 'new_binding_id': g.named_id('assignment_package_binding', 2), 'also_test_same_raw_different_id_or_cut': True},
        'EXACT_COMMAND_AND_BODY_AFTER_AMBIGUOUS_ACK': {'exact_binding': fixture['binding'], 'original_command': next(o for o in fixture['objects'] if o['ref'] == fixture['commits'][3]['body']['command_ref']), 'acknowledgment_fault': 'DROP_AFTER_DURABLE_COMMIT_BEFORE_REPLY', 'restart_before_retry': True},
        'REPLACE_WITH_REPACKED_PACKAGE_RAW': {'bound_raw_digest': known['raw_package_digest'], 'candidate_file': 'fixtures/repacked_input_package.zip', 'candidate_raw_digest': known['raw_repacked_package_digest'], 'semantic_digest': known['package_semantic_digest'], 'workspace_positive_control': 'DELETE_OR_REPLACE_WORKSPACE_COPY_AND_RECONSTRUCT_ONLY_FROM_BOUND_RAW'},
        'CHANGE_RESULT_PACKAGE_SEMANTIC_ASSERTION': {'manifest_path': '/input_package_digest/digest', 'replacement': known['raw_package_digest'], 'recompute_result_raw_digest': True},
        'CHANGE_PACKAGE_ASSIGNMENT_EXACT_REF': {'manifest_path': '/assignment_ref', 'replacement': different_ref, 'recompute_semantic_and_raw': True},
        'CHANGE_PACKAGE_ATTEMPT_EXACT_REF': {'manifest_path': '/attempt_ref/revision_digest', 'replacement': refs['assignment']['revision_digest'], 'recompute_semantic_and_raw': True},
        'CHANGE_PACKAGE_SOURCE_EXACT_REF': {'manifest_path': '/source_generation_ref/revision_digest', 'replacement': refs['assignment']['revision_digest'], 'recompute_semantic_and_raw': True},
        'REMOVE_PRIOR_ACCEPTED_BINDING': {'content_binding': fixture['binding'], 'remove_from_accepted_membership': True, 'retain_valid_raw_and_checksums': True},
        'CHANGE_EXACT_BINDING_REF': {'body_path': '/package_binding_ref/revision_digest', 'replacement': refs['assignment']['revision_digest'], 'recompute_object_digest': True},
        'SET_PRIOR_DELIVERY_OR_STARTED': {'attempt_state': 'STARTED', 'executor_disclosure_callbacks_before_command': 1},
        'ASSIGNMENT_IN_CURRENT_CLOSURE_NOT_PRIOR': {'assignment': fixture['assignment'], 'move_from_prior_history_into_proposed_closure': True},
        'MISSING_OR_SAME_COMMIT_BINDING': {'binding': fixture['binding'], 'cases': ['ABSENT', 'IN_PROPOSED_CLOSURE_ONLY']},
        'REMOVE_PRIOR_BINDING_OR_STARTED': {'delivery_file': 'fixtures/input_package.zip', 'missing_prerequisites': ['PRIOR_BINDING', 'STARTED'], 'expected_disclosure_callbacks': 0},
        'INSERT_OWN_FINAL_RAW_HASH_OR_FORWARD_BINDING_REF': {'extra_manifest_fields': {'package_raw_digest': known['raw_package_digest'], 'package_binding_ref': refs['binding']}, 'recompute_semantic_and_raw': True},
        'CALLER_SUPPLIED_UNPINNED_ROOT_OR_SAME_COMMIT_UPGRADE': {'untrusted_schema_root_file': artifacts['schema_byte_substitution.json'], 'governing_set_replacement': 'UNAUTHORIZED_CALLER_CONTEXT', 'cases': ['CALLER_ROOT', 'SAME_COMMIT_UPGRADE', 'LATEST_INSTALLED_ON_OLD_CAMPAIGN']},
        'UNKNOWN_ROLE_ALIAS_VERSION_OR_REFERENCE_CLASS': {'role_candidates': ['PROVENANCE', 'PROPOSAL'], 'wire_kind_candidate': 'LaneResult', 'version_candidate': '1', 'reference_class_candidate': 'UNREGISTERED_REF'},
        'CALLER_SELECTED_INGEST_COMMAND_WITHOUT_AUTHENTICATED_PRODUCER': {'command_kind': 'INGEST_EXTERNAL_LANE_RESULT', 'authenticated_actor': False, 'forgery_fields': {'trusted': True, 'capability_token': 'FORGED_UNAUTHENTICATED_STRING'}, 'other_assignment': different_ref},
        'ROTATE_RUNTIME_SECRET_REPLAY_FACTS_THEN_UNAUTHORIZED_WRITE': {'new_key_bytes_hex': '4e4630325f4e45575f52554e54494d455f534543524554', 'replay_exact_facts_first': True, 'next_write_actor_authenticated': False, 'serialized_capability_fields': []},
        'EVIDENCE_IN_CURRENT_CLOSURE_NOT_PRIOR': {'evidence': fixture['evidence'], 'move_from_prior_history_into_proposed_closure': True},
        'CHANGE_FINDING_STATEMENT_AFTER_EVIDENCE': {'body_path': '/result_payload/findings/0/statement', 'replacement': 'Forged statement after accepted evidence', 'recompute_object_digest': True, 'keep_result_raw': True},
        'CLOSED_SLOT_WITH_DIFFERENT_RAW_OR_WRONG_SLOT': {'closed_result_ref': refs['result'], 'replacement_raw_ref': artifacts['result_truncated.zip'], 'slot_variants': ['OTHER_PIN', 'OMITTED_REQUIRED_SLOT']},
        'REMOVE_OR_FLIP_PACKAGE_RESULT_SCHEMA_OR_CANONICAL_BYTES': {'targets': ['PACKAGE_RAW', 'RESULT_RAW', 'BOUND_SCHEMA_RAW', 'CANONICAL_REFERENCE_TARGET'], 'faults': ['DELETE', 'XOR_FIRST_BYTE_01'], 'phases': ['START', 'EVIDENCE', 'RESULT', 'COMPLETION', 'REOPEN'], 'restore_rule': 'INDEPENDENTLY_VERIFY_EXACT_ORIGINAL_BYTES_NO_AUTHORITY_REWRITE'},
        'TWO_DIFFERENT_CANDIDATES_SAME_PARENT': {'parent_cut': fixture['cuts']['binding_input'], 'first_binding': fixture['binding'], 'second_binding_id': g.named_id('assignment_package_binding', 2), 'barrier': 'AFTER_VALIDATION_BEFORE_PARENT_CAS', 'workers': 2, 'repeat_modes': ['THREAD', 'PROCESS']},
        'KILL_PROCESS_AT_EACH_PERSISTENCE_BOUNDARY': {'operations': ['ACCEPT_BINDING', 'ACCEPT_EVIDENCE', 'ACCEPT_RESULT'], 'boundaries': ['RAW_STAGING', 'ACCEPTED_RAW_REF', 'IMMUTABLE_OBJECT', 'EVENT', 'COMMIT', 'HEAD', 'RECEIPT'], 'fault': 'PROCESS_DEATH', 'restart': True, 'forbid_partial_authority_and_delivery': True},
        'OLD_R5_3_CONTEXT_OR_RETROACTIVE_V1_ALIAS': {'foundation_context': 'R5.3.1', 'attempt_state': 'STARTED', 'submitted_versions': ['lane_result_admission_evidence/1', 'bdb_audit_lane_result/1', 'assignment_package_binding/1'], 'forbid_mapping_to_v2': True},
        'UNSAFE_ZIP_OR_DUPLICATE_JSON_KEYS': {'concrete_inputs': list(artifacts.values()), 'member_paths': ['../SOURCE.txt', 'A.txt', 'a.txt', 'e\u0301.txt', '\u00e9.txt'], 'duplicate_member': 'MANIFEST.json', 'symlink_mode': '120777', 'extra_manifest_field': {'trusted': True}, 'quota_rule': 'PINNED_MAXIMUM_PLUS_ONE; no OS allocation of expansion bomb required'},
    }
    out = {}
    for name, operation, mutation, variants in ids:
        prefix = 3 if operation in {'accept_binding', 'accept_binding_race'} else 4 if operation == 'start_attempt' else 6 if operation == 'accept_result' else 5
        if operation in {'retry_binding', 'replay_then_write', 'consume_authority', 'binding_evidence_result_persistence'}:
            prefix = 7
        scenario = {'schema': 'BDB_R5_4_ADVERSARIAL_SCENARIO/1', 'vector_id': name,
                    'scope': 'FROZEN_INPUT_AND_RUNNER_INSTRUCTIONS_NOT_EXECUTED',
                    'fixture_file': 'fixtures/NF02_OBJECT_FIXTURE_R5_4.json',
                    'model_prefix_commit_seq': prefix, 'snapshot_timing': 'AFTER_ALL_SETUP_AND_BEFORE_TARGET_OPERATION',
                    'operation': operation, 'mutation': mutation, 'parameters': parameters[mutation],
                    'mandatory_variants': variants,
                    'derived_bytes_rule': 'Apply the explicit JSON pointer replacement to the full fixture body/manifest; preserve all other fields. Recompute canonical ObjectDigest and ZIP RawDigest only when specified. Fixed ZIP metadata and semantic algorithm are the frozen profiles. Mutation never changes trusted governing pins implicitly.',
                    'execution_contract': 'N9 production runner must execute every variant and compare all eight canonical snapshot fields. Faults/setup are test inputs, not approved runtime authority.'}
        raw = g.cjson(scenario) + b'\n'
        out[name] = asset(name + '.json', raw)
    return out

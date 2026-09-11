# F2 execution and evidence map

## Final qualification status: PASS

R5.3.1 resolves the normative bootstrap-order conflict via union DAG Kahn sort and the pinned `BDB_BOOTSTRAP_PRECEDENCE_V1` profile.
All implementation defects (F2-IMPLEMENTATION-AUTHORITY-003, F2-IMPLEMENTATION-BLINDNESS-004, F2-IMPLEMENTATION-SCHEMA-005, F2-CLOSEOUT-006) have been resolved with regression tests.
Full milestone qualification has been completed for PR-007 through PR-019, covering all foundation authority, identity, orchestration, schema binding, and DAG invariants.

Milestone Acceptance ID: `BDB-F2-M4-M13-R5_3_1-001`
F2 Status: PASS
Total Passed Tests: 264 (F1: 93, Compatibility: 86, F2: 85)
Gates: M4–M13 PASS, F0 regression PASS, F1 regression PASS, Golden Vector qualification PASS (117 vectors).

## Work package summary

| Package | Milestone | Implementation | Verification | Gate Status |
|---|---|---|---|---|
| PR-007 | M4 | Minimal module CLI, package metadata, Authority protocol | `test_cli.py`: 1 passed | PASS |
| PR-008 | M4/Substrate | Exact Registry v4 / Golden loader, offline schema bindings | `test_registry_schema.py`: 28 passed | PASS |
| PR-009 | M5 | Canonical objects, bootstrap primitives, union Kahn precedence | `test_m5_objects.py`: 3 passed | PASS |
| PR-010 | M5 | Transactional history adapter, durability boundaries, CAS concurrency | `test_m5_transaction.py`, `test_history_process_faults.py`: 16 passed | PASS |
| PR-011 | M5 | Minimal FSM transition validator and history integration | `test_m5_fsm.py`: 2 passed | PASS |
| PR-012 | M6 | StageSpec registry (E1–E5 recognition and plan validation) | `test_m6_stages.py`: 2 passed | PASS |
| PR-013 | M7 | LaneSpec / Attempt / Isolation qualification | `test_m7_isolation.py`: 3 passed | PASS |
| PR-014 | M8 | CapabilityBroker positive views, grant-before-delivery via history | `test_m8_capability.py`: 2 passed | PASS |
| PR-015 | M9 | Deterministic compiler without authority-write capability | `test_m9_compiler.py`: 1 passed | PASS |
| PR-016 | M10 | Executable schemas and layered identity qualification | `test_m10_schema_identity.py`: 2 passed | PASS |
| PR-017 | M11 | Corpus engine, single direct predecessor, auxiliary multi | `test_m11_corpus.py`: 2 passed | PASS |
| PR-018 | M12 | Knowledge state, exposure ledger, pre-reveal discovery classification | `test_m12_knowledge_discovery.py`: 2 passed | PASS |
| PR-019 | M13 | Claim quarantine, positive view reveal, opaque namespace | `test_m13_quarantine.py`: 2 passed | PASS |
| Defects | All | Authority repairs & regression suite | `test_authority_repairs.py`: 11 passed | PASS |
| Goldens | All | Complete 117-vector golden set verification | `test_golden_vectors_complete.py`: 6 passed | PASS |

## Resolved implementation defects

1. `F2-IMPLEMENTATION-AUTHORITY-003`: CapabilityBroker and ExposureLedger now verify delivery grants strictly against canonical accepted history and exact history cuts. Local memory cache is no longer an authority bypass.
2. `F2-IMPLEMENTATION-BLINDNESS-004`: `blind_origin_eligible` enforces accepted earlier discovery fact and verifies mandatory isolation boundary evidence rather than relying on caller assertions.
3. `F2-IMPLEMENTATION-SCHEMA-005`: All F2 domain objects use complete executable schemas strictly conforming to R5.3.1 Data Contracts (§8, §9, §90–91, §10, §11, §14.1, §15.1) with explicit required fields, constraints, and `additionalProperties: False`.
4. `F2-BOOTSTRAP-ORDER-002`: Normative order conflict resolved by R5.3.1 union DAG Kahn topological sort using pinned `BDB_BOOTSTRAP_PRECEDENCE_V1`.
5. `F2-CLOSEOUT-006`: Terminal verifier `tests/f2/verify_f2.py` executed and `F2_MILESTONE_ACCEPTANCE.json` generated.

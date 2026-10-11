# BDB Audit PRODUCT-V1 — raport częściowy

Audyt E1-E6: **NOT_COMPLETED**. NF02: **OPEN**. Import wyników: **BLOCKED**.

NF02 OPEN: brak niezależnie autoryzowanego producenta i kwalifikowanej aktywacji. Zachowaj ZIP poza historią. Przygotowanie paczek, lokalne kontrole i raport częściowy są dostępne; E1-E6 nie jest ukończone.

Lokalne komendy dowodzą wyłącznie wykonania wskazanych kontroli. Integralność receipt nie ustanawia autoryzacji producenta ani związania z kampanią. Nie są kwalifikacją ani wynikiem zewnętrznego audytora.

```json
{
  "campaign": {
    "status": "READY_FOR_REVIEW",
    "store_path": "C:\\Projekty\\Audyty\\BDB Audit\\.product-smoke\\9f371932992d4a369260043f7e93bb3b\\work\\campaign.sqlite",
    "campaign_id": "campaign_4e0926d847dc7a55",
    "accepted_history_cut": {
      "variant": "ACCEPTED_HISTORY_CUT",
      "governing_policy_ref": "pin:initial_governing_policy_ref",
      "governing_spec_refs": [
        "pin:initial_transition_profile_ref"
      ],
      "campaign_id": "campaign_4e0926d847dc7a55",
      "accepted_head_seq": 8,
      "accepted_head_hash": "d1d9a29945193f4340fb25fdab8966c8b5afe2509aee294b7d8ced452c6012b5"
    },
    "workflow": {
      "status": "SUCCESS",
      "campaign_id": "campaign_4e0926d847dc7a55",
      "store_path": "C:\\Projekty\\Audyty\\BDB Audit\\.product-smoke\\9f371932992d4a369260043f7e93bb3b\\work\\campaign.sqlite",
      "current_stage": "E1",
      "current_phase": null,
      "active_inbox": "E1",
      "accepted_lanes_count": 0,
      "total_required_lanes": 5,
      "missing_lanes": [
        "E1-A",
        "E1-B",
        "E1-C",
        "E1-D",
        "E1-E"
      ],
      "stage_complete": false,
      "phase_complete": false,
      "source_commit_sha": "e6b1154bc1707c4230eca481c4904ded9c08130a",
      "source_tree_sha": "80ea5443b921f9471962a4a002ca3d9dd0b73346",
      "executor_profile": "ChatGPT / GitHub",
      "executor_model": "Sol 5.6"
    },
    "profile": "PRODUCT-V1_PREPARATION_AND_LOCAL_CHECKS",
    "external_ingestion": "BLOCKED",
    "nf02": "OPEN",
    "audit_completion": "NOT_COMPLETED",
    "qualification": "NO_NEW_Q1_Q2_CLAIM",
    "isolation": "DECLARED; host/network runner NOT_ENFORCED",
    "next_action": "NF02 OPEN: brak niezależnie autoryzowanego producenta i kwalifikowanej aktywacji. Zachowaj ZIP poza historią. Przygotowanie paczek, lokalne kontrole i raport częściowy są dostępne; E1-E6 nie jest ukończone.",
    "packages": [
      {
        "campaign_id": "campaign_4e0926d847dc7a55",
        "stage_id": "E1",
        "lane_slot": "E1-A",
        "lane_title": "General Systems & Architecture",
        "strategy": "STRUCTURAL_ENUMERATION",
        "input_history_cut": {
          "accepted_head_hash": "86fce091173b8f09e5ed1d71bc8adaa57bd20b46b3a76cc2ea81fdcec650085c",
          "accepted_head_seq": 7,
          "campaign_id": "campaign_4e0926d847dc7a55",
          "governing_policy_ref": "pin:initial_governing_policy_ref",
          "governing_spec_refs": [
            "pin:initial_transition_profile_ref"
          ],
          "variant": "ACCEPTED_HISTORY_CUT"
        },
        "package_digest": "5db6e6064b2b4d32f3ea4bf553dbdfdeb3d2087befe56717c48ac9825f087147",
        "package_zip_path": "C:\\Projekty\\Audyty\\BDB Audit\\.product-smoke\\9f371932992d4a369260043f7e93bb3b\\work\\artifacts\\campaign_4e0926d847dc7a55\\E1\\E1-A_General_Systems_AND_Architecture_5db6e6064b2b_PACKAGE.zip",
        "package_zip_sha256": "b32498f4c4561d7e0d48032c8d877e0d23b78ac0f5f45e4268c0b46d4925ab68",
        "prompt_sha256": "33c2d41f6fb6e447a9304b4d4cab121ce76839487b5c080f349df0d6d67fd76d",
        "assignment_ref": {
          "digest_profile": "BDB-OBJECT-DIGEST-1",
          "kind": "assignment_manifest",
          "ref_class": "PRIOR_ACCEPTED_ONLY",
          "revision_digest": "4b18c1b7d850492ae628ead0c5fe963d94ea237f0ae2a13ac379968d98010787",
          "schema_revision_ref": "BDB_SCHEMA_REGISTRY::assignment_manifest/1"
        },
        "attempt_ref": {
          "digest_profile": "BDB-OBJECT-DIGEST-1",
          "kind": "attempt",
          "ref_class": "PRIOR_ACCEPTED_ONLY",
          "revision_digest": "0549f4b4e9510bf65528de5bb2c39c1a1a541b21352af4ccadb588ed4e77840a",
          "schema_revision_ref": "BDB_SCHEMA_REGISTRY::attempt/1"
        }
      },
      {
        "campaign_id": "campaign_4e0926d847dc7a55",
        "stage_id": "E1",
        "lane_slot": "E1-B",
        "lane_title": "Security, Trust & Authority",
        "strategy": "AUTHORITY_BOUNDARY_ANALYSIS",
        "input_history_cut": {
          "accepted_head_hash": "86fce091173b8f09e5ed1d71bc8adaa57bd20b46b3a76cc2ea81fdcec650085c",
          "accepted_head_seq": 7,
          "campaign_id": "campaign_4e0926d847dc7a55",
          "governing_policy_ref": "pin:initial_governing_policy_ref",
          "governing_spec_refs": [
            "pin:initial_transition_profile_ref"
          ],
          "variant": "ACCEPTED_HISTORY_CUT"
        },
        "package_digest": "fd904c3a08883005a92f2a890e5c7171c03f3f7c83ac89e2dbfcb74997f4bc2b",
        "package_zip_path": "C:\\Projekty\\Audyty\\BDB Audit\\.product-smoke\\9f371932992d4a369260043f7e93bb3b\\work\\artifacts\\campaign_4e0926d847dc7a55\\E1\\E1-B_Security_Trust_AND_Authority_fd904c3a0888_PACKAGE.zip",
        "package_zip_sha256": "c8aefe9ec2126ac28bb74ee19f2550240102622b0b0ba51a1ba1d525ef2b98da",
        "prompt_sha256": "f763baa51f751bd1d26fd4751777b79abf3090e5384198faaca6cb71b4ec17f2",
        "assignment_ref": {
          "digest_profile": "BDB-OBJECT-DIGEST-1",
          "kind": "assignment_manifest",
          "ref_class": "PRIOR_ACCEPTED_ONLY",
          "revision_digest": "74df5d0efffbba794caefd8d9c12e7ff1ea26a0c1ccd5af2cf203c2bdc503ca9",
          "schema_revision_ref": "BDB_SCHEMA_REGISTRY::assignment_manifest/1"
        },
        "attempt_ref": {
          "digest_profile": "BDB-OBJECT-DIGEST-1",
          "kind": "attempt",
          "ref_class": "PRIOR_ACCEPTED_ONLY",
          "revision_digest": "a225e00807be4e1965d44f184339f85d4133ee101eb30adbfa60d095e2314ffb",
          "schema_revision_ref": "BDB_SCHEMA_REGISTRY::attempt/1"
        }
      },
      {
        "campaign_id": "campaign_4e0926d847dc7a55",
        "stage_id": "E1",
        "lane_slot": "E1-C",
        "lane_title": "State, Persistence & Recovery",
        "strategy": "STATE_MUTATION_TRACE",
        "input_history_cut": {
          "accepted_head_hash": "86fce091173b8f09e5ed1d71bc8adaa57bd20b46b3a76cc2ea81fdcec650085c",
          "accepted_head_seq": 7,
          "campaign_id": "campaign_4e0926d847dc7a55",
          "governing_policy_ref": "pin:initial_governing_policy_ref",
          "governing_spec_refs": [
            "pin:initial_transition_profile_ref"
          ],
          "variant": "ACCEPTED_HISTORY_CUT"
        },
        "package_digest": "4fabdd0bc7dc17cfe1e7fe7ab77ff699c6806d77217dda1eaf382f31585c289b",
        "package_zip_path": "C:\\Projekty\\Audyty\\BDB Audit\\.product-smoke\\9f371932992d4a369260043f7e93bb3b\\work\\artifacts\\campaign_4e0926d847dc7a55\\E1\\E1-C_State_Persistence_AND_Recovery_4fabdd0bc7dc_PACKAGE.zip",
        "package_zip_sha256": "1159e1253dcde3fa3ba36543b82ee26ad346795ff3be37b13c7550eef3970a88",
        "prompt_sha256": "8e3de3bed4e35db1ba094ac90fb855161375b32096d0d3eb14b16a634f9b8713",
        "assignment_ref": {
          "digest_profile": "BDB-OBJECT-DIGEST-1",
          "kind": "assignment_manifest",
          "ref_class": "PRIOR_ACCEPTED_ONLY",
          "revision_digest": "96962b490322fb4f8a9fd43dd7ac3e4a4af58b4b0e9684774357b4e513715da9",
          "schema_revision_ref": "BDB_SCHEMA_REGISTRY::assignment_manifest/1"
        },
        "attempt_ref": {
          "digest_profile": "BDB-OBJECT-DIGEST-1",
          "kind": "attempt",
          "ref_class": "PRIOR_ACCEPTED_ONLY",
          "revision_digest": "86111d1e787738ba03e08d96865687336d01ced72d5fd870ced6ed9db5ba7d8c",
          "schema_revision_ref": "BDB_SCHEMA_REGISTRY::attempt/1"
        }
      },
      {
        "campaign_id": "campaign_4e0926d847dc7a55",
        "stage_id": "E1",
        "lane_slot": "E1-D",
        "lane_title": "Data, Catalog & Parsing",
        "strategy": "INPUT_PARSER_DIFFERENTIAL",
        "input_history_cut": {
          "accepted_head_hash": "86fce091173b8f09e5ed1d71bc8adaa57bd20b46b3a76cc2ea81fdcec650085c",
          "accepted_head_seq": 7,
          "campaign_id": "campaign_4e0926d847dc7a55",
          "governing_policy_ref": "pin:initial_governing_policy_ref",
          "governing_spec_refs": [
            "pin:initial_transition_profile_ref"
          ],
          "variant": "ACCEPTED_HISTORY_CUT"
        },
        "package_digest": "39be882c0790145d34980f9a593e91ebbcb178bf5f75d138a89bbc43fcaa5a36",
        "package_zip_path": "C:\\Projekty\\Audyty\\BDB Audit\\.product-smoke\\9f371932992d4a369260043f7e93bb3b\\work\\artifacts\\campaign_4e0926d847dc7a55\\E1\\E1-D_Data_Catalog_AND_Parsing_39be882c0790_PACKAGE.zip",
        "package_zip_sha256": "8eea9f8fddffa95b189c917d00b602e6c4b003c284409bddcf7a5e765c03777e",
        "prompt_sha256": "28b390ffedd204b499d98acdffd4d4dc3ed0646b15d870d5dc154c0542088a75",
        "assignment_ref": {
          "digest_profile": "BDB-OBJECT-DIGEST-1",
          "kind": "assignment_manifest",
          "ref_class": "PRIOR_ACCEPTED_ONLY",
          "revision_digest": "7d0aa61c5866be21e1caec9b54f5b4f50662128edd58cde6400e540f718466b9",
          "schema_revision_ref": "BDB_SCHEMA_REGISTRY::assignment_manifest/1"
        },
        "attempt_ref": {
          "digest_profile": "BDB-OBJECT-DIGEST-1",
          "kind": "attempt",
          "ref_class": "PRIOR_ACCEPTED_ONLY",
          "revision_digest": "e18d65a603f9019680a8757ddba75ca0f544cfa9b163693dc97a30ba0efdd5d0",
          "schema_revision_ref": "BDB_SCHEMA_REGISTRY::attempt/1"
        }
      },
      {
        "campaign_id": "campaign_4e0926d847dc7a55",
        "stage_id": "E1",
        "lane_slot": "E1-E",
        "lane_title": "Concurrency, Resources & Oracles",
        "strategy": "INTERACTION_CONCURRENCY_ANALYSIS",
        "input_history_cut": {
          "accepted_head_hash": "86fce091173b8f09e5ed1d71bc8adaa57bd20b46b3a76cc2ea81fdcec650085c",
          "accepted_head_seq": 7,
          "campaign_id": "campaign_4e0926d847dc7a55",
          "governing_policy_ref": "pin:initial_governing_policy_ref",
          "governing_spec_refs": [
            "pin:initial_transition_profile_ref"
          ],
          "variant": "ACCEPTED_HISTORY_CUT"
        },
        "package_digest": "09c7cecaeeed19f03d44e1510343586db0df9908e1f8b0803fd5fce0aae735a6",
        "package_zip_path": "C:\\Projekty\\Audyty\\BDB Audit\\.product-smoke\\9f371932992d4a369260043f7e93bb3b\\work\\artifacts\\campaign_4e0926d847dc7a55\\E1\\E1-E_Concurrency_Resources_AND_Oracles_09c7cecaeeed_PACKAGE.zip",
        "package_zip_sha256": "a38597af7d1a18d9f0e706fc1672507da8d421f4475992468557893b481a7ffc",
        "prompt_sha256": "f2c064933e988761945ba4f36c7c91d441ff3c4b01c0d040b0955b358ef50cf5",
        "assignment_ref": {
          "digest_profile": "BDB-OBJECT-DIGEST-1",
          "kind": "assignment_manifest",
          "ref_class": "PRIOR_ACCEPTED_ONLY",
          "revision_digest": "6cdd558b3a355451d073f06db42892cd961282a3fc000dfca93358dc88752e1c",
          "schema_revision_ref": "BDB_SCHEMA_REGISTRY::assignment_manifest/1"
        },
        "attempt_ref": {
          "digest_profile": "BDB-OBJECT-DIGEST-1",
          "kind": "attempt",
          "ref_class": "PRIOR_ACCEPTED_ONLY",
          "revision_digest": "a8abad317747c3c049926d6c0cfc72441613252415f2f0581d7dae4a47f36ad0",
          "schema_revision_ref": "BDB_SCHEMA_REGISTRY::attempt/1"
        }
      }
    ],
    "action": "product.status"
  },
  "local_runs": [
    {
      "path": "C:\\Projekty\\Audyty\\BDB Audit\\.product-smoke\\9f371932992d4a369260043f7e93bb3b\\checks-pass",
      "verification": {
        "status": "PASS",
        "run_id": "sum-control",
        "spec_digest": "681ecd31f41b41d5eda89da685e5398cdc95033b1cd9aa57739d25ca164b605f",
        "receipt_digest": "13dccebf8988724350c8680ebe144ed427352877eda2d6490bec2a01a09b776c",
        "supervisor_status": "SUCCESS",
        "cleanup_status": "CLEAN",
        "stdout_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "stderr_sha256": "1a52ff93b2b7c8bc576900f70c9062f5baedb573cf55507ec33070c999cd9b12"
      },
      "authority": "LOCAL_RECEIPT_INTEGRITY_ONLY; NOT_ACCEPTED_AUDITOR_RESULT"
    },
    {
      "path": "C:\\Projekty\\Audyty\\BDB Audit\\.product-smoke\\9f371932992d4a369260043f7e93bb3b\\checks-detected-defect",
      "verification": {
        "status": "PASS",
        "run_id": "clamp-defect",
        "spec_digest": "c861ef122732be024c9dceb57d490448a01122e72467893adc09f966e7fb2767",
        "receipt_digest": "f6af8e58f545b2a57dd91db178dfa239b281a477b3ce3fc7ca16c7e0ca1f8b36",
        "supervisor_status": "TARGET_NONZERO",
        "cleanup_status": "CLEAN",
        "stdout_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "stderr_sha256": "86dbd554b22ab8a700e65b9b6d41e51f8dfead986002afd1898d41ee4a96f99e"
      },
      "authority": "LOCAL_RECEIPT_INTEGRITY_ONLY; NOT_ACCEPTED_AUDITOR_RESULT"
    }
  ]
}
```

# BDB Audit Report

Campaign: `campaign_4e0926d847dc7a55`  
Scope: **PARTIAL**  
Report model SHA-256: `1952eb64fb675be14a9bdb238a7cabb871afc10ae5d70580ed8283c3a3e8156d`  
Accepted head: `d1d9a29945193f4340fb25fdab8966c8b5afe2509aee294b7d8ced452c6012b5`  
Source identity: `{"authority_mode": "AUTHORIZED_GIT", "completeness_state": "COMPLETE_SOURCE", "git_commit_object_id": "e6b1154bc1707c4230eca481c4904ded9c08130a", "git_tree_object_id": "e6b1154bc1707c4230eca481c4904ded9c08130a", "repository_authority_ref": {"digest_profile": "BDB-OBJECT-DIGEST-1", "kind": "repository_or_snapshot_authority_ref", "ref_class": "SOURCE_AUTHORITY_REF", "revision_digest": "710300bb1628efbb16b813861dafc8e666c63c9828536ba4b21d24deb309c8f2", "schema_revision_ref": "BDB_TARGET/repository_or_snapshot_authority_ref"}, "source_generation_id": "source_gen_campaign_4e0926d847dc7a55", "source_generation_ref": {"digest_profile": "BDB-OBJECT-DIGEST-1", "kind": "source_generation", "ref_class": "CONTENT_OR_PRIOR", "revision_digest": "5ef7832efff307a10e84f3796e59f43c9001993cad2101cdd368074befdf2324", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_generation/1"}, "source_identity_ref": {"digest_profile": "BDB-OBJECT-DIGEST-1", "kind": "source_identity", "ref_class": "CONTENT_OR_PRIOR", "revision_digest": "9ca733a7acf6f2d039b14b83e5ce0b7dc1ffd05dad8051b3ba9ac5415e52a8f2", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_identity/1"}}`

All entries below are explicitly classified as accepted FACT, derived INTERPRETATION, PROPOSAL, or UNKNOWN.

## Accepted facts

### campaign_genesis — 70bcb3a819813cc6a9379f27f02d4b03513b9b6d88b9fe057fea0ae51857eec4

Classification: **FACT**  
Accepted seq: `1`

```json
{
  "application_generation_ref": {
    "digest_profile": "BDB-OBJECT-DIGEST-1",
    "kind": "application_generation_ref",
    "ref_class": "CONTENT_OR_PRIOR",
    "revision_digest": "585cb81b525f0247625351d572f2ec063819e4349a616e00f68a2c8b4753f75e",
    "schema_revision_ref": "BDB_TARGET/application_generation_ref"
  },
  "bootstrap_admission_decision_ref": {
    "digest_profile": "BDB-OBJECT-DIGEST-1",
    "kind": "bootstrap_admission_decision",
    "ref_class": "CONTENT_OR_PRIOR",
    "revision_digest": "5b0fba6c83a8f1908bfabcbd4f0d42952f2ccafbb99a3e2861967a432381c637",
    "schema_revision_ref": "BDB_SCHEMA_REGISTRY::bootstrap_admission_decision/1"
  },
  "campaign_id": "campaign_4e0926d847dc7a55",
  "input_history_cut": {
    "governing_policy_ref": "pin:initial_governing_policy_ref",
    "governing_spec_refs": [
      "pin:initial_transition_profile_ref"
    ],
    "history_namespace_ref": "pin:allowed_history_namespace_ref",
    "variant": "EMPTY_HISTORY_CUT"
  },
  "legacy_origin_refs": [
    {
      "digest_profile": "BDB-OBJECT-DIGEST-1",
      "kind": "legacy_raw_ref",
      "ref_class": "CONTENT_OR_PRIOR",
      "revision_digest": "0ebcb747e7874b456e4f2a21a99612bf943273cdb201c286476543627fc69d08",
      "schema_revision_ref": "BDB_SCHEMA_REGISTRY::legacy_raw_ref/1"
    }
  ],
  "owner_operator_authority_ref": {
    "digest_profile": "BDB-OBJECT-DIGEST-1",
    "kind": "owner_operator_authority_ref",
    "ref_class": "PINNED_INSTALLATION_REF",
    "revision_digest": "9bf5e5adb755633c31c2432ab6b69438562fb2e98cf94a3b0e7e0b1a97a767af",
    "schema_revision_ref": "BDB_TARGET/owner_operator_authority_ref"
  },
  "protocol_policy_bundle_ref": {
    "digest_profile": "BDB-OBJECT-DIGEST-1",
    "kind": "protocol_policy_bundle_ref",
    "ref_class": "CONTENT_OR_PRIOR",
    "revision_digest": "f49a29e94fd58012fc3a826da68ec5bec641430512eb9fc9ab46a7d80fae2a16",
    "schema_revision_ref": "BDB_TARGET/protocol_policy_bundle_ref"
  },
  "schema_set_ref": {
    "digest_profile": "BDB-OBJECT-DIGEST-1",
    "kind": "schema_set_ref",
    "ref_class": "CONTENT_OR_PRIOR",
    "revision_digest": "41f51ea63e5a5095ae2df817782f37491e0b783c1763ddbe66ac5b71c3da264e",
    "schema_revision_ref": "BDB_TARGET/schema_set_ref"
  },
  "source_generation_ref": {
    "digest_profile": "BDB-OBJECT-DIGEST-1",
    "kind": "source_generation",
    "ref_class": "CONTENT_OR_PRIOR",
    "revision_digest": "5ef7832efff307a10e84f3796e59f43c9001993cad2101cdd368074befdf2324",
    "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_generation/1"
  },
  "trust_profile_ref": {
    "digest_profile": "BDB-OBJECT-DIGEST-1",
    "kind": "trust_profile",
    "ref_class": "PINNED_INSTALLATION_REF",
    "revision_digest": "92d99e5aa0b98af7d5326a22be20fff7a69c1b188de35e8a2b1ae66366593077",
    "schema_revision_ref": "BDB_TARGET/trust_profile"
  }
}
```

### source_generation — 5ef7832efff307a10e84f3796e59f43c9001993cad2101cdd368074befdf2324

Classification: **FACT**  
Accepted seq: `1`

```json
{
  "materialized_source_manifest_ref": {
    "digest_profile": "BDB-OBJECT-DIGEST-1",
    "kind": "source_manifest",
    "ref_class": "CONTENT_OR_PRIOR",
    "revision_digest": "17dc48f499c103c20a5d2e330b013f167cccf01b94cc8737cc471b3ec9775fbb",
    "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_manifest/1"
  },
  "repository_authority_ref": {
    "digest_profile": "BDB-OBJECT-DIGEST-1",
    "kind": "repository_or_snapshot_authority_ref",
    "ref_class": "SOURCE_AUTHORITY_REF",
    "revision_digest": "710300bb1628efbb16b813861dafc8e666c63c9828536ba4b21d24deb309c8f2",
    "schema_revision_ref": "BDB_TARGET/repository_or_snapshot_authority_ref"
  },
  "representation_refs": [],
  "source_generation_id": "source_gen_campaign_4e0926d847dc7a55",
  "source_identity_profile_ref": {
    "digest_profile": "BDB-OBJECT-DIGEST-1",
    "kind": "source_identity_profile_pin",
    "ref_class": "PINNED_PROFILE_REF",
    "revision_digest": "52f03b90cf62ba9fc66cb95793519f7822b799b95acc1072c3b4f4fba55c62fd",
    "schema_revision_ref": "BDB_TARGET/source_identity_profile_pin"
  },
  "source_identity_ref": {
    "digest_profile": "BDB-OBJECT-DIGEST-1",
    "kind": "source_identity",
    "ref_class": "CONTENT_OR_PRIOR",
    "revision_digest": "9ca733a7acf6f2d039b14b83e5ce0b7dc1ffd05dad8051b3ba9ac5415e52a8f2",
    "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_identity/1"
  }
}
```

### source_identity — 9ca733a7acf6f2d039b14b83e5ce0b7dc1ffd05dad8051b3ba9ac5415e52a8f2

Classification: **FACT**  
Accepted seq: `1`

```json
{
  "authority_mode": "AUTHORIZED_GIT",
  "authorized_repository_or_snapshot_ref": {
    "digest_profile": "BDB-OBJECT-DIGEST-1",
    "kind": "repository_or_snapshot_authority_ref",
    "ref_class": "SOURCE_AUTHORITY_REF",
    "revision_digest": "710300bb1628efbb16b813861dafc8e666c63c9828536ba4b21d24deb309c8f2",
    "schema_revision_ref": "BDB_TARGET/repository_or_snapshot_authority_ref"
  },
  "completeness_state": "COMPLETE_SOURCE",
  "git_commit_object_id": "e6b1154bc1707c4230eca481c4904ded9c08130a",
  "git_tree_object_id": "e6b1154bc1707c4230eca481c4904ded9c08130a",
  "materialized_source_manifest_ref": {
    "digest_profile": "BDB-OBJECT-DIGEST-1",
    "kind": "source_manifest",
    "ref_class": "CONTENT_OR_PRIOR",
    "revision_digest": "17dc48f499c103c20a5d2e330b013f167cccf01b94cc8737cc471b3ec9775fbb",
    "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_manifest/1"
  },
  "profile_ref": {
    "digest_profile": "BDB-OBJECT-DIGEST-1",
    "kind": "source_identity_profile_pin",
    "ref_class": "PINNED_PROFILE_REF",
    "revision_digest": "52f03b90cf62ba9fc66cb95793519f7822b799b95acc1072c3b4f4fba55c62fd",
    "schema_revision_ref": "BDB_TARGET/source_identity_profile_pin"
  }
}
```

## Interpretations

NOT_ASSESSED

## Proposals

NOT_ASSESSED

## Unknowns / blockers

NOT_ASSESSED

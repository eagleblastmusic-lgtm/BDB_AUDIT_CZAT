# NF02 — Normative Contract Decision Proposal

Data: 2026-10-06. Status: propozycja decyzji właściciela, nie zatwierdzona specyfikacja ani evidence wykonania przyszłych gates.

Repozytorium: `eagleblastmusic-lgtm/bdb-audit`, lokalnie `C:\Projekty\Audyty\BDB Audit`.

## A. Executive decision

**C1: NEW FOUNDATION REVISION REQUIRED.** Rekomendowana rewizja: **R5.4 candidate**, wyprowadzona z exact aktywnego korpusu R5.3.1 z zachowaniem provenance R5.3. Runtime extension, overlay, schema wygenerowane w Pythonie i sam executable-schema binding nie ustanawiają legality nowego wire kind. R5.4 ma zarejestrować pełne kontrakty NF02, otrzymać własny manifest, kwalifikację/governance oraz exact przypięty SchemaRegistry. R5.3 i R5.3.1 pozostają byte-for-byte historycznymi candidate/baseline artifacts.

**C2: osobny `assignment_package_binding/1`, immutable FACT, accepted po AssignmentManifest i przed AttemptStarted oraz dostawą.** Wiąże jeden exact prior accepted assignment z jednym exact RawRef do finalnych, durable package bytes. AssignmentManifest/1 nie zmienia body ani identity. Wynik wiąże prior accepted admission evidence, które wiąże assignment, jego jedyny accepted binding i exact result raw artifact.

Proponowana kolejność:

```text
Attempt / grants / PotentialExposure / KnowledgeState
  -> accepted AssignmentManifest/1
  -> construct and finalize package bytes
  -> durable immutable raw package
  -> accepted AssignmentPackageBinding/1
  -> accepted AttemptStarted, separate later commit
  -> delivery of those exact retained bytes
  -> external execution
  -> accepted LaneResultAdmissionEvidence/2
  -> accepted bdb_audit_lane_result/2
  -> ordinary LaneCompletion / StageCompletion qualification
```

Wersje `/2` dla obu dotychczas nielegalnych kinds zapobiegają przypisaniu nowego znaczenia istniejącym historycznym objects `/1`. `/1` nie otrzymuje retrospective legality ani aliasu do `/2`. Nowa SchemaRegistry używa `schema_registry/2`, ponieważ jej complete executable-binding body i acceptance predicates będą jawnie utrwalone; starsza `/1` pozostaje historyczna. Nie dodaje się canonical capability, DeliveryReceipt, package-manifest authority ani nowych reference classes lub canonical roles.

Existing campaign **nie może** przejść na R5.4 schema set w ramach tej delty. Rekomendowana granica to **nowa campaign i nowy history namespace**, z nowymi assignments, packages i wykonaniami. Odczyt starej historii nie daje R5.4 assurance.

Gate bieżącej implementacji pozostaje **`NF02 = SPEC_CONFLICT`**. Gate tego dokumentu: **`READY_FOR_OWNER_APPROVAL`**. Dopiero approval -> versioned normative corpus -> pinned machine contracts -> implementacja -> wymagane qualification może rozwiązać implementation gate.

## B. Current source identity

### B.1. Pin przed analizą

Wykonano poniższe komendy w `C:\Projekty\Audyty\BDB Audit`, bez checkout/reset/stash/commit:

```powershell
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
git log -n 10 --oneline
```

```text
CURRENT_HEAD   = b7051472909075bb4c83a9a510e298fcca2a6bd5
CURRENT_TREE   = 3bc05685293d2fade72735e43a2ccc96be26f3f7
CURRENT_BRANCH = fix/nf02-lane-result-authority
WORKTREE_STATUS = DIRTY; zastana remediation i reports, zachowane
MAIN_REF       = dcd8bd6ef5f7e3f7b5803ade6843c6217f16f044
ORIGIN         = https://github.com/eagleblastmusic-lgtm/bdb-audit.git
```

CWD rozmowy `BDB_AUDIT_CZAT` jest osobnym repozytorium. Nie jest source authority tego zadania; żaden jego plik nie został zmieniony. Zadanie kontynuuje istniejącą wskazaną gałąź NF02, nie przełącza jej na bdb-v2 i nie dotyka main.

Zastany pełny short status:

```text
 M src/bdb_audit/history/authority_hooks.py
 M src/bdb_audit/history/store.py
 M src/bdb_audit/schemas/orchestration.py
 M src/bdb_audit/stop/authority.py
 M src/bdb_audit/workflow/inbox.py
 M src/bdb_audit/workflow/manual_stage.py
 M src/bdb_audit/workflow/package_resume.py
 M src/bdb_audit/workflow/packaging.py
 M src/bdb_audit/workflow/stage_resume.py
 M tests/workflow/test_nf02_synthetic_lane_result_authority.py
?? ._nf02_current_audit/
?? ._nf02_raw_durability_20261002/
?? NF02_CURRENT_STATE_AND_REMEDIATION_PLAN.md
?? docs/NF02_CURRENT_VERIFICATION_2026_10_02.json
?? docs/NF02_IMPLEMENTATION_PLAN_2026_10_02.md
?? docs/NF02_IMPLEMENTATION_RESULT_2026_10_02.md
?? docs/NF02_IMPLEMENTATION_VERIFICATION_2026_10_02.json
?? docs/NF02_INDEPENDENT_SECOND_PASS_REAUDIT.md
?? docs/NF02_RAW_DURABILITY_PLAN_2026_10_02.md
?? docs/NF02_RAW_DURABILITY_VERIFICATION_2026_10_02.json
?? docs/NF02_REMEDIATION_AND_CLOSURE_REPORT.md
?? docs/NF02_SECOND_PASS_REMEDIATION_PLAN.md
?? docs/NF02_THIRD_PASS_REMEDIATION_AND_REAUDIT.md
?? src/bdb_audit/history/raw_artifacts.py
?? src/bdb_audit/workflow/result_proposal.py
?? tests/workflow/nf02_raw_crash_worker.py
?? tests/workflow/test_nf02_raw_derivation.py
?? tests/workflow/test_nf02_raw_durability.py
```

`git status` zakończył się exit 0, ale ostrzegł o odmowie odczytu ignored `.codex-pytest-tmp/`. Nie kwalifikuje to zawartości tego scratch directory; katalog pozostawiono bez zmian. HEAD/tree nie identyfikują dirty source; poniższe raw hashes oraz readback 504 source pins stanowią dodatkowy pin odczytanego stanu.

```text
b705147 test: accept fail-closed schema rejection for unadmitted lane results
850a181 fix: authenticate external lane result admission
f9cbd0f fix: close canonical completion and provenance bypasses
ae5dbf9 fix: close canonical completion and provenance bypasses
52e60e9 Merge pull request #42 from eagleblastmusic-lgtm/fix/astra-remediation-candidate
33f6f06 Merge remote-tracking branch 'origin/main' into fix/astra-remediation-candidate
3fa508e Merge pull request #41 from eagleblastmusic-lgtm/fix/e1-reference-isolation-honesty
e3deeea fix: enforce canonical audit completion and stop authority
93c8059 Merge updated main into PR #41
1e67cb2 Merge PR #40: Make E3 isolation qualification truthful by executor profile
```

### B.2. Authority source readback

Przeczytano całe wskazane aktualne źródła MD oraz kompletne machine contracts; JSON evidence sparsowano w całości, przeanalizowano inputs, commands, logi końcowe, scope i exclusions. Źródła normatywne znajdują się w `C:\Projekty\Audyty\BDB Audit - Context`. Stare kopie w F1_QUALIFICATION nie zastępują aktywnego korpusu.

Żądany execution plan bez suffixu nie istnieje w aktywnym Context. Aktualnym dokumentem jest **`BDB_AUDIT_V2_IMPLEMENTATION_EXECUTION_PLAN_R5_3_CORR2.md`**, jawnie podporządkowany normatywnemu corpus; przeczytano tę wersję. Nie domyślano się brakującego pliku ani nie użyto historycznej kopii jako aktualnej.

| Źródło | SHA256 exact raw bytes |
| --- | --- |
| BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS.md | `ea2fed8089f46e8ad065e4cae0583926fe719028967077fb16bb85141fc0fa1a` |
| BDB_AUDIT_V2_ARCHITECTURE_SPEC.md | `9ad023f90cb44cc0a1e6beee2b918222f959d1483f42d7015066db2061accd14` |
| ADR-006_CANONICAL_SERIALIZATION_AND_IDENTITY_PROFILE.md | `38cb55d9ce15d1ec3b51b46b6d50312f140fe9a549561990558ace24a8e69d6b` |
| BDB_AUDIT_V2_ARTIFACT_CONTRACT_REGISTRY.json | `3cd0945f2987499761281f51cadb48a5947ac8255e4af292f4837cbc843a2a8b` |
| BDB_AUDIT_V2_FOUNDATION_GOLDEN_VECTORS_R5_3.json | `1beeedd979c06816480cc5adc144fd3470a7379630e6ed8d4a4770c5448c48e7` |
| BDB_AUDIT_V2_TEST_AND_SELF_AUDIT_PLAN.md | `1f335f470370eb8d047889d057f855b6ddc45caae6aeb9365a6f7533f07ee05f` |
| BDB_AUDIT_V2_IMPLEMENTATION_ROADMAP.md | `3311790ef9ed4221fd46ff3ced7473e5896531b28d3f95b71d948dcc45cf6046` |
| BDB_AUDIT_V2_IMPLEMENTATION_EXECUTION_PLAN_R5_3_CORR2.md | `aef5471b826aae843244f1da7c8eaecf311afa9d8580e29c010874c204b19bcc` |
| docs/NF02_INDEPENDENT_SECOND_PASS_REAUDIT.md | `50ef546ec72065f6cbe690418cab21f8504979f1e086ee71c156e9e8800e8bc0` |
| docs/NF02_RAW_DURABILITY_VERIFICATION_2026_10_02.json | `7b5d4b2b0bfcb717a8c9d3507a6039e08adef1d9d66fa5465882f46d97247a77` |

Aktywny Registry ma `registry_id=BDB-AUDIT-V2-ARTIFACT-CONTRACT-REGISTRY-R5-3-2`, registry_version 4, 110 contracts; Golden ma 117 vectors i `vector_set_id=BDB-AUDIT-V2-FOUNDATION-GOLDEN-VECTORS-R5-3-2`. Nazwa R5_3 pliku nie usuwa hotfix R5.3.1. Zachować `BDB_BOOTSTRAP_PRECEDENCE_V1` i wszystkie jego scope restrictions.

Provenance aktywnego candidate: normative candidate set digest `087539f5a08a2441647aae1889ce51330b47740e559b394574da122bd6cfd15b`, manifest raw digest `eecbdffb9666248a30601000ad7048b0c39bd83c45b9959aa80804ab025bb8b5`, external author qualification record raw digest `4bb0da6a8bcb4ef0bc931bef5178f30120618e85ef727d72633a410fb4fbdb2c`. Poprzedni R5.3 set digest: `78de98f8163d2f0bf0ab94781b86bd8e5e0345411a4432669d91fdfc42671d56`. Potwierdzenie w `F2_QUALIFICATION/PREFLIGHT_R5_3_1_RESOLUTION.md` nie jest niezależnym foundation freeze ani runtime authority. R5.4 musi wskazać te predecessor identities, nie nadpisać ich.

### B.3. Świeży inventory source i granica evidence

Odczytano NF02 constructors, Registry loader/extension/overlay, wszystkie schemas/binding paths, Store admission/raw persistence/hooks, E1/manual-stage packaging/intake, proposal derivation, resume i downstream completion/STOP consumers. AST inventory E1/manual assignment/intake wykazał dwie nowe rodziny emitowanych canonical objects; pozostałe emitowane rodziny to już zarejestrowane `stage_run`, `lane_run`, `attempt`, `isolation_qualification`, `knowledge_state`, `assignment_manifest`, `discovery_record` i completion families. Nie utożsamiono nowych nazw helperów z nowymi canonical kinds.

| NF02 source | SHA256 |
| --- | --- |
| src/bdb_audit/core/registry.py | `1da10c55484fa8f7ce16885e62cd023d052bcb529ca76dbf85fdf9202e73ffd7` |
| src/bdb_audit/core/registry_overlay.py | `1a13df00d29a216f0c08f19ffb2355dd7ef77bafc7ce24756cdcbd57bbc91301` |
| src/bdb_audit/schemas/foundation.py | `7da4c11cd57f6f26771ba342a7f9f5a5d28b68e3ee5e962d7731494e02424b13` |
| src/bdb_audit/schemas/orchestration.py | `7f2a0f17a80ea138ddce1d424b40ff54e9a19fed757ec76bcdda56495e12cec8` |
| src/bdb_audit/schemas/binding.py | `7c607ba7b3d11964d08e35bfdf9b7b26d6f1169e236b3ac1f5f1cab466361f68` |
| src/bdb_audit/history/store.py | `36ae2685715b6de1b4ef64178f10743288d2b31e1fc3e6ff4c0d48cbe1d9dd03` |
| src/bdb_audit/history/authority_hooks.py | `82d82474df2e3e457274319eeaab6a66cac71b1039ba51ee8e2421b090043730` |
| src/bdb_audit/history/raw_artifacts.py | `9751d00ba9b53a0802568a917e9cc7ea0fe0f9f89440fb70ab8b3d308ffebbe7` |
| src/bdb_audit/workflow/assignments.py | `948e3cabf3f9bbec481a24b791793f8ea970c7e2ceb3ac708df78686905b54a6` |
| src/bdb_audit/workflow/packaging.py | `4b7a0184bde561344c76ae01256952200effcc149fae7219c4d6e533c55fc0d2` |
| src/bdb_audit/workflow/inbox.py | `00d5a8d71d4d76883af47424a1d1e66ff41581584572a0f4419aedc2869ddaed` |
| src/bdb_audit/workflow/manual_stage.py | `4ca2af3db009709071f94addf5d1c668432b2901cda4e010c354d1492225da86` |
| src/bdb_audit/workflow/result_proposal.py | `dfddb937a4fe5cab349355f1d49b066a856a03d6838fa38117ae4a78c590a26a` |
| src/bdb_audit/workflow/package_resume.py | `18ce40b5e89a4f1cc5ed99f7875bbbb380ddb1fff2e6c377f71cd120cdef5e18` |
| src/bdb_audit/workflow/stage_resume.py | `2441362046cf63fa27ca1c9e1da4acbdcad85d067e0251e6180be7759a90064f` |
| src/bdb_audit/stop/authority.py | `92b35adb2d0f1b263acb60f7917f9432b5a9caae061bb3bcdfd4e6a3e04addaf` |

Świeży readback wszystkich **504** `tested_inputs.source_pins` durability record: **0 drift**. Record ma datę wewnętrzną 2026-10-05 mimo filename 2026_10_02. Zawiera 249 tests PASS (81+59+19+55+35), Ruff PASS, Mypy 49 files PASS oraz dodatkowy check raw_artifacts.py PASS, build i końcowy LOCAL_ARTIFACT_VALIDATION PASS. Artifact: SHA256 `0a51ce0f154e3c616513f12daf8d4cf1bee5cc9663bcfe154bb6a021afc131bb`, 1,492,515 bytes. Log wcześniejszego validator FAIL/WinError 5 nie jest terminal evidence; terminal record opisuje późniejszy poprawny lokalny run.

To jest evidence wcześniejszego wykonania, świeżo sprawdzone względem source pins, **nie nowy test run tego zadania**. Record jawnie wyklucza normative activation, immutable assignment-time package authority, full repository pytest, F0–F8 qualification, clean-room rebuild, exact-SHA CI, post-commit verification i complete GUI/E1–E5 campaign. Process-death durability nie stanowi host/storage rollback qualification. Nie wyprowadza się z tych PASS ani C1/C2 legality, ani NF02 CLOSED.

## C. R5.3 constraints

Poniższe ograniczenia pozostają wymaganiami R5.4; proponowana delta dodaje brakujące authority, nie usuwa predecessor invariants.

| Authority | Ograniczenie i konsekwencja |
| --- | --- |
| Data Contracts §§2–7; ADR-006 | RawDigest = SHA256 exact bytes. ObjectDigest = SHA256(`BDB2/` + exact wire kind + `/` + version + NUL + BDB-CJSON-1 body). Nie ma aliasów wire kind, self digest, accepting commit/head lub own event position w body. Exact TypedRef nie redukuje się do logical ID ani samego revision_digest. |
| Data §§14.1–14.6, 15–16; Registry reference_class_semantics | PRIOR_ACCEPTED_ONLY musi być accepted na input cut, nie earlier same commit. HISTORY_INPUT to prior cut, nie bieżący commit. HISTORY_CONTEXT_BINDING nie może ustanowić własnego governing context. Bootstrap exception jest tylko exact first-history scope. |
| Data §14.6, §15.2; ADR; R5N80 | Jeden Kahn sort union DAG typed refs + exact aktywne bootstrap order-only edges. Tie-break `(kind, logical_id_or_empty, revision_digest)`. Order-only edge nie daje material ref ani authority. NF02 nie potrzebuje nowego order-only profile. |
| Data §§95–96, 184–188; execution CORR2 WP-F2-02/P04 | Registered semantic kind/key + exact executable schema bytes/digest + accepted/pinned SchemaRegistry binding **przed pierwszą acceptance**, również dla EXPLICIT_COMPLETE. Binding nie zmienia frozen semantics bez nowej foundation revision. |
| Registry canonical_role_domain | Legalne role: FACT, ASSESSMENT, DECISION, TRUST_ROOT, DERIVED_PROJECTION, RAW_EVIDENCE, EXPORT. PROVENANCE i PROPOSAL nie są legalnymi nowymi rolami. |
| Data §187; R5N02/04/15–19/23/25/29 | Complete body/Registry ref parity; registered allowed target i ref class; exact kind/version/hash domain. Schema bindings nie legalizują brakującego kind. |
| Data AssignmentManifest/Attempt/Knowledge/grant sections; Architecture §§6.7, 6.9–6.10, 41–44 | Accepted assignment i grants poprzedzają wykonanie/delivery. Potential exposure pozostaje konserwatywne bez ACK. Nowe binding nie usuwa exposure lub isolation obligations. |
| Data §96; §15.1; R5N26/30/37/65/78–79 | Run nie ma semantic auto-upgrade. Governing spec refs nie są aliasem schema_set_ref. Actor/source authority istnieje wcześniej lub jest installation-pinned; caller-selected command nie samopotwierdza authority. |
| Data §§107–109; Architecture §44.3, recovery/standalone sections | Raw lifecycle, immutable accepted fact i export/projection lifecycle są odrębne. Canonical acceptance trwała/atomiczna przed external effect; corruption fail-closed bez cofania/truncating historii. |
| Data §§187.1–187.2; test plan governance | Candidate nie self-attestuje kwalifikacji lub freeze. Manifest/readback i upoważniony external record ustanawiają status poza zahashowanymi candidate bytes. Author-only qualification nie jest independent freeze. |

Obecne extension semantics są w konflikcie z tymi ograniczeniami. Nie przyjmujemy ich jako interpretacji R5.3. Nowe wskazane niżej predicates są **proponowaną decyzją R5.4**, a nie twierdzeniem, że R5.3 już zawiera ten model.

## D. C1 — Registry / SchemaRegistry decision

### D.1. Pełny NF02 contract inventory

| Obserwowany element | Klasyfikacja | Rozstrzygnięcie |
| --- | --- | --- |
| lane_result_admission_evidence/1; bdb_audit_lane_result/1 w core/registry.py i constructors intake | Canonical semantic contract: ObjectDigest, accepted history, downstream authority | Brak obu kinds w pinned R5.3.1 Registry. Wbudowany extension nie wystarcza. R5.4 rejestruje jawne /2 według D.2; historical /1 nie reinterpretować. |
| PROVENANCE; PROPOSAL | Próba nowych canonical roles | Odrzucić. Accepted admission/result to FACT o admission/odebranej treści, nie evidence truth. Unaccepted proposal pozostaje lokalnym kandydatem, nie canonical role. |
| TRUSTED_INGESTION_BOUNDARY; AUDITOR_EXTERNAL | Declarative producer metadata nowych extensions | Nie ustanawia authority. Reuse istniejącego TRUSTED_COORDINATOR_ACCEPTANCE z wykonawczym sprawdzeniem prior actor authority i trusted derivation. External auditor jest producentem untrusted raw, nie canonical accepting authority. |
| assignment_ref, attempt_ref, source_generation_ref, admission_evidence_ref; użycie PRIOR_ACCEPTED_ONLY | Canonical refs; klasy już legalne | Zachować exact identity i prior boundary. Usunąć redundant body copies w /2; dołożyć package_binding_ref. Nie dodawać lokalnych ref classes. |
| schema keys BDB_SCHEMA_REGISTRY::lane_result_admission_evidence/1 oraz ::bdb_audit_lane_result/1 | Canonical schema identity wymagająca normative kind | Python-generated dict/schema bytes oraz process-local SchemaBindings nie ustanawiają accepted SchemaRegistry. Nie kwalifikować tych /1 jako R5.3. |
| DERIVED profile i L1/L2/L4/L5 dla accepted provenance | Semantics walidacji mające znaczenie authority | Nie obejmuje complete structural/history/knowledge checks. Nowy jawny NF02_PROVENANCE profile L1–L6. Stage predicates pozostają L7 w completion gates. |
| INGEST_EXTERNAL_LANE_RESULT | Nowy canonical command-kind token w CommandEnvelope | Zamrozić command contract R5.4: restricted producer, closure evidence-only, atomic retained raw, exact refs. String jest selektorem operacji, nie upoważnieniem. |
| RECORD_FOUNDATION_FACT | Istniejący generic command; NF02 acceptance gate | Nie nowy kind. Nie może bypassować binding/evidence/producer predicates. Result admission może używać tego commandu dopiero pod exact R5.4 operation/profile contract. |
| ingestion_capability w canonical evidence; HMAC key, batch_ticket, issue_ingestion_capability | Token/key/call capability to runtime security; serialized evidence field jest obecnie canonical semantic delta | Usunąć secret/token z /2 body. Zachować authenticated runtime channel lub capability poza canonical preimage. Durable replay bazuje na zaakceptowanych facts i raw, nie HMAC-key self-attestation. |
| RawArtifactVault, AdmissionRawReader, immutable_raw_artifacts, retained raw/SQLite transaction | Runtime persistence implementation | Nie nowe canonical kinds/roles. Contract obejmuje exact RawRef, retention, atomicity i verification; table/key/cache/path nie jest authority. |
| raw_result_digest, raw_result_byte_length, package_zip_sha256 | Exact raw identity, ale obecnie rozproszone scalars | Zastąpić jednym RawRef dla każdego raw object. RawRef niesie raw_digest, byte_length, media_type, artifact_contract_ref. Same cached SHA nie jest fact autoryzującym package. |
| input_package_digest / package_digest i compute_package_identity_digest / compute_stage_package_identity_digest | Semantic checksum wykorzystywany w provenance, zatem wymaga zamrożonego profilu, nie nowego object kind | Obecne różne helper preimages nie definiują normative authority. W R5.4 jawny external semantic profile, derived z bound raw; E.3 definiuje odrębność od RawDigest. |
| result_proposal_digest = SHA256(canonical proposal bez evidence ref) | Runtime integrity aid; obecnie serialized duplication | /2 nie potrzebuje drugiej canonical digest authority. Cała result payload musi być rederived z retained raw pod pinned normalizer i porównana byte-for-byte canonicalnie. Helper może pozostać internal checksum. |
| campaign_id/stage_id/phase_id/lane_slot/source_commit_sha/source_tree_sha/history_cut/executor_profile/executor_model, optional assignment/attempt copies | Context scalars częściowo wyprowadzalne, część external claims | Authority wyprowadzać z accepted refs. External claims sprawdzać, nie akceptować jako kontekst. Oddzielić assignment execution cut od binding/admission/result input cut. Runtime labels/path nie stają się canonical authority. |
| findings, outputs, findings_count, notes, evidence_files | Treść untrusted result / derived inventory | Treść jest canonical semantic payload po deterministic derivation; count i member hashes wyprowadzać. Findings nie auto-QUALIFIED. Evidence files resolve przez result raw, nie host pathname. |
| result output ref z completion/STOP; exact typed-reference identity hardening | Istniejący canonical consumer contract | Wymaga explicit /2 allowed-version wiring, zachowania L7/STOP/evidence qualification. Nie legalizować result przez completion lub truth flag. |
| accepted head/index, replay, command_index, resume job/batch records | Runtime/read-model mechanisms, część implementuje history contract | Index/cache może być przebudowany z accepted history; nie druga authority ani latest logical-ID selector. Resume musi odczytać binding i vault. |

Nie ma w odczytanym NF02 nowego canonical DeliveryReceipt, package binding ani canonical capability kind. Emitowane wcześniej zarejestrowane assignment/run/knowledge/discovery/completion objects nie wymagają kolejnych aliases. `artifact_contract_overlay_r5_3_3.json` (SHA256 `cdb3d3a934c4364e6c98a1a973d23e099921d184a3bdd9278def4fc418255de2`) dodaje **residual_risk/1**, poza NF02. Nie jest normative approval. Nie włączać go milcząco do C1 delty; N10/N11 muszą mieć osobne legalne governing contract dla ścieżki, która go używa, albo wykluczyć tę ścieżkę z claim i pozostawić odpowiedni gate niespełniony. Lokalny source overlay nie może ratyfikować sam siebie.

### D.2. Proposed ArtifactContractRegistry rows

Poniższe są complete proposed rows, nie wpisy zastosowane do R5.3. Każdy nowy row ma consumers COORDINATOR/VALIDATOR/STORE, lifecycle IMMUTABLE, exact version string, ObjectDigest według ADR-006. Generic object envelope/schema identity obowiązuje również gdy nie powtórzono go w domain body. Logical IDs zachowują dokładną gramatykę ADR §5: `<wire kind>_<uuidv4-lowercase>`. `binding_id` używa `assignment_package_binding_...`, `admission_evidence_id` używa `lane_result_admission_evidence_...`, `lane_result_id` używa `bdb_audit_lane_result_...`, a `schema_registry_id` używa `schema_registry_...`; nie dodaje się krótkich prefix aliases ani nowego algorytmu IDs.

| Pole kontraktu | assignment_package_binding/1 | lane_result_admission_evidence/2 | bdb_audit_lane_result/2 |
| --- | --- | --- | --- |
| kind | assignment_package_binding | lane_result_admission_evidence | bdb_audit_lane_result |
| version | 1 | 2 | 2 |
| canonical_role | FACT | FACT | FACT |
| lifecycle | IMMUTABLE, single binding per exact assignment | IMMUTABLE, one admitted raw per exact assignment/result slot | IMMUTABLE, one accepted payload per exact result slot |
| authoritative_for | exact raw package authorized for one exact accepted assignment | trusted admission of exact result raw for assignment, binding and slot; no truth qualification | exact normalized external result content and provenance for accepted slot; no truth qualification |
| producer_authority | TRUSTED_COORDINATOR_ACCEPTANCE | TRUSTED_COORDINATOR_ACCEPTANCE | TRUSTED_COORDINATOR_ACCEPTANCE |
| schema_ref | BDB_SCHEMA_REGISTRY::assignment_package_binding/1 | BDB_SCHEMA_REGISTRY::lane_result_admission_evidence/2 | BDB_SCHEMA_REGISTRY::bdb_audit_lane_result/2 |
| validation_profile | NF02_PROVENANCE | NF02_PROVENANCE | NF02_PROVENANCE |
| reference_contract_mode | EXPLICIT_COMPLETE | EXPLICIT_COMPLETE | EXPLICIT_COMPLETE |
| required_validation_layers | L1,L2,L3,L4,L5,L6 | L1,L2,L3,L4,L5,L6 | L1,L2,L3,L4,L5,L6 |
| ordering rules | no domain ref arrays; exact body canonicalization | no domain ref arrays; exact body canonicalization | payload findings sequence preserves transport order; object/map keys CJSON; typed reference sets use Registry default exact-ref order/duplicate rejection |
| first-acceptance rule | governing R5.4 Registry + exact schema binding; prior assignment; raw durable; no prior start/delivery | same schema authority; prior binding/assignment/STARTED; raw result durable; trusted rederivation | same schema authority; prior accepted evidence; exact rederived payload; correct open result slot/FSM |

Domain bodies are closed (`additionalProperties=false`). Forbidden copies/secret fields są odrzucane, nie ignorowane. Schemas definiują raw/TypedRef shapes i finite payload contract, a cross validators obsługują resolved authority i predicates.

#### D.2.1. assignment_package_binding/1

```text
binding_id
assignment_ref
binding_input_history_cut
package_raw_ref
```

| material_refs field | Cardinality | Target | Reference class | Additional constraint |
| --- | --- | --- | --- | --- |
| assignment_ref | 1 | assignment_manifest/1 | PRIOR_ACCEPTED_ONLY | exact prior accepted revision on binding input cut; same campaign namespace |
| binding_input_history_cut | 1 | history_cut | HISTORY_INPUT | exact command input/expected parent; non-EMPTY; includes assignment |
| package_raw_ref | 1 | raw_artifact_ref | CONTENT_OBJECT | exact durable raw content prerequisite; reuse prior retained raw explicitly allowed, never workspace path |
| package_raw_ref.artifact_contract_ref | 1 | external_profile_ref | PINNED_PROFILE_REF | exact NF02_INPUT_PACKAGE_TRANSPORT_V2 pin selected by governing R5.4 context, not package claim |

RawRef scalar constraints: lowercase SHA256 raw_digest, exact nonnegative byte_length (package ZIP nonempty), media_type=`application/zip`. Nested artifact contract pin is part of the complete material-ref inventory. Package context must equal resolved assignment context. At binding input cut the resolved Attempt MUST be CREATED, assignment eligible/active, source/lane/stage context lawful, and all grants/knowledge/isolation prerequisites valid; cancelled, superseded, failed, already started or completed execution cannot acquire a new binding. Full cross-object rules and uniqueness: E.1–E.4.

#### D.2.2. lane_result_admission_evidence/2

```text
admission_evidence_id
assignment_ref
package_binding_ref
result_slot_contract_ref
admission_input_history_cut
result_raw_ref
```

| material_refs field | Cardinality | Target | Reference class | Additional constraint |
| --- | --- | --- | --- | --- |
| assignment_ref | 1 | assignment_manifest/1 | PRIOR_ACCEPTED_ONLY | equal binding.assignment_ref; cannot select by logical ID |
| package_binding_ref | 1 | assignment_package_binding/1 | PRIOR_ACCEPTED_ONLY | unique binding accepted on admission cut, preceding AttemptStarted/delivery authorization |
| result_slot_contract_ref | 1 | result_slot_contract_ref | PINNED_PROFILE_REF | exact one of assignment.result_slot_contract_refs, active under assignment governing context |
| admission_input_history_cut | 1 | history_cut | HISTORY_INPUT | exact current command input, non-EMPTY, includes prior assignment, binding and accepted STARTED transition |
| result_raw_ref | 1 | raw_artifact_ref | CONTENT_OBJECT | exact result ZIP verified/retained atomically with accepted reference; explicit reuse of identical prior retained raw allowed |
| result_raw_ref.artifact_contract_ref | 1 | external_profile_ref | PINNED_PROFILE_REF | exact NF02_RESULT_TRANSPORT_V2 / slot transport pin |

Slot ref neredundant: assignment may declare more than one slot; evidence selects the one admitted slot, rather than inventing a global one-result-per-lane shortcut. NF02 supported external lane slot must be explicitly declared; an empty assignment slot set cannot admit a result. External raw carries exact assignment and package-binding claims; any claim mismatch rejects before evidence acceptance. No capability/token, result_proposal_digest, copied attempt/source/raw scalars or cached package checksum in accepted evidence.

#### D.2.3. bdb_audit_lane_result/2

```text
lane_result_id
admission_evidence_ref
result_input_history_cut
result_payload
```

| material_refs field | Cardinality | Target | Reference class | Additional constraint |
| --- | --- | --- | --- | --- |
| admission_evidence_ref | 1 | lane_result_admission_evidence/2 | PRIOR_ACCEPTED_ONLY | exact evidence accepted before result command input |
| result_input_history_cut | 1 | history_cut | HISTORY_INPUT | exact command input/expected parent, non-EMPTY; includes evidence and lawful result-received state |

`result_payload` is the deterministic domain payload `{findings: [...], outputs: {...}, notes: string|null}` from retained result raw and exact slot/normalizer. Required keys are present even when arrays/maps are empty; count is derived. Schemas/slot profile close finding and output shapes. NF02 payload embeds **no material TypedRef**: files/evidence paths address members of result_raw_ref, and finding/evidence qualification objects are accepted subsequently under their existing contracts. If a slot needs material canonical refs in a future result payload, that requires an explicit successor row/schema/vector delta; an untyped arbitrary dict is not permission to smuggle refs.

Transport assertion metadata is retained in raw. It is checked against accepted context but not copied into competing authority fields. Result payload must equal `Normalize(result_raw_ref, exact slot profile)` byte-for-byte after BDB-CJSON-1; body logical ID/ref/cut are assigned by the trusted acceptance operation. A checksum of caller-supplied proposal is insufficient. Attempt/slot uniqueness and completion gates cannot be bypassed by generic command.

`NF02_PROVENANCE=[L1,L2,L3,L4,L5,L6]` is a **new named validation profile**, explicitly added to R5.4 Registry, not a new canonical kind or role. It combines raw/container validation, digest, schema, references/history/source, authority/FSM and knowledge/isolation checks. L7 remains required in LaneCompletion/StageCompletion/STOP and any existing downstream profile; admission does not satisfy it automatically.

### D.3. SchemaRegistry successor contract and bootstrap

Propose `schema_registry/2` as an additional **version of an existing canonical kind**, with:

```text
schema_registry_id
artifact_contract_registry_ref
serialization_profile_ref
validator_profile_ref
compatibility_rules_ref
bindings[] = { schema_key, schema_raw_ref, status }
```

Contract: FACT; IMMUTABLE; authoritative_for exact semantic-key -> executable bytes mapping under one exact ArtifactContractRegistry; producer_authority TRUSTED_COORDINATOR_ACCEPTANCE, with construction/install authorization from existing authorized foundation governance and LOCAL_PINNED root; schema_ref `BDB_SCHEMA_REGISTRY::schema_registry/2`; EXPLICIT_COMPLETE; NF02_PROVENANCE/L1–L6. Installation activation additionally enforces existing governance requirements; this FACT does not grant governance authority.

| material_refs | Cardinality | Target / class |
| --- | --- | --- |
| artifact_contract_registry_ref | 1 | artifact_contract_registry; PINNED_PROFILE_REF; approved exact successor revision |
| serialization_profile_ref | 1 | serialization_profile_pin; PINNED_PROFILE_REF; unchanged ADR-006 profile |
| validator_profile_ref | 1 | external_profile_ref; PINNED_PROFILE_REF; exact offline dialect/backend/formats/normalizer dependency profile |
| compatibility_rules_ref | 1 | external_profile_ref; PINNED_PROFILE_REF; R5.4 no-in-place-upgrade rule |
| bindings[].schema_raw_ref | 1 per binding, bindings 1..N | raw_artifact_ref; CONTENT_OBJECT; earlier durable content or explicitly reusable retained bytes |
| bindings[].schema_raw_ref.artifact_contract_ref | 1 per binding | external_profile_ref; PINNED_PROFILE_REF; exact executable JSON-schema raw contract |

Bindings sort by semantic key's UTF-8 bytes, with duplicate key rejection; all entries `status=ACTIVE`. Kind/version are derived exactly from key `BDB_SCHEMA_REGISTRY::<wire kind>/<version>`, must resolve to the approved Registry row and agree with executable schema identifier. `schema_id`, `artifact_or_object_type` and `schema_revision_digest` from Data §95 become derived accessors: the last is explicitly **RawDigest(schema bytes)**, not this SchemaRegistry's ObjectDigest. No new unregistered `json_schema` ObjectDigest domain is introduced. RawDigest validates exact executable bytes; **ObjectDigest(schema_registry,2,body)** identifies the canonical binding set. Normative JSON file's RawDigest and registered artifact_contract_registry object identity, if materialized, are recorded separately and must map deterministically.

Closed exact lifecycle (N1–N4), with separate semantic approval and runtime activation:

1. Owner approves R5.4 delta/model. Produce complete successor normative candidate, Registry/Golden, provenance manifest and self-audit. Preserve all predecessor bytes. Perform exact readback. Apply existing governance: author-qualified implementation baseline requires external authorized qualification record; independent foundation freeze requires independent READY plus exact external freeze decision. Do not relabel author-only as independent.
2. Freeze successor ArtifactContractRegistry exact bytes and digest; all three NF02 new kinds plus schema_registry/2, versions/profile/ref parity are known before schema production. No post-freeze runtime extension.
3. Generate executable schemas as **build-time candidates**, verify semantics/parity/fixtures, then freeze their exact files. Record RawDigest, byte_length, media type, `$id`, dialect and exact schema-dependency closure. Python may produce candidate bytes here; runtime Python dict is never binding authority.
4. Construct SchemaRegistry/2 over those exact raw refs and exact approved Registry/profile refs. Calculate its canonical ObjectDigest. Preserve raw schema bytes as installation content. Unknown kinds cannot obtain entries; every kind reachable by a first accepted closure has a bound exact schema, including bootstrap command/history/profile/schema-registry objects, not only NF02 rows.
5. Authorized installation operation pins exact SchemaRegistry/2 and exact R5.4 normative/Registry identities in a new exact **revision of installation_bootstrap_profile/1**. Preserve the eight existing material pins and allowed initialization command; do not change predecessor pin bytes or add actor self-authorization. Approval/readback record is outside candidate preimage.
6. Bootstrap verification has an explicit external schema root: the installed immutable bootstrap bundle supplies the exact executable schema for `schema_registry/2` (and bootstrap validation prerequisites) by raw digest **before** validating this registry. The registry may list that schema's raw ref; schema bytes do not contain the owning SchemaRegistry digest or future campaign head. Resolver validates these external pins first and resolves entries against them. A registry cannot validate or authorize itself from a caller-provided `$id`.
7. New history `seq=1`, EMPTY_HISTORY and existing `INITIALIZE_CAMPAIGN_FROM_LEGACY` use this exact installation profile, qualified admission chain and one existing union-DAG sort. Initial context establishes the exact schema/policy/spec set. Thereafter schema authority is resolved from that campaign's accepted/pinned context, never latest installed files.
8. Allow new runtime kinds only in this legally initialized R5.4 campaign when semantic registration, schema bytes/digest, exact SchemaRegistry binding, actor authority and all object predicates pass. Missing/changed schema rejects before canonical state mutation. A copy of SchemaRegistry JSON on disk is not activation.

No new generic schema-upgrade command is introduced. Installing an R5.4 bundle affects **new** campaigns only; old campaigns retain their exact old schema set. A future in-place transition would require a separately approved admission/activation decision, governing prior cut, old-policy validation, next-command boundary and in-flight run rules. None is currently specified here, so this task chooses **NO**.

## E. C2 — Package binding decision

### E.1. Minimality and uniqueness

Accepted **AssignmentPackageBinding/1** is the sole package authorization authority. Its four-field domain body is in D.2.1. RawRef already includes raw_digest and byte_length; separate package_raw_digest/package_size_bytes duplicate identity and are omitted. Attempt/source/executor/delivery refs are derived through exact assignment_ref. `package_manifest_ref|null` is omitted: embedded manifest is an untrusted transport member checked against assignment, not a second accepted package authority. Semantic checksum is derived from bound bytes under a pinned profile, so no stored duplicate checksum or package semantic object is required.

`binding_id` provides typed object identity under the existing ID grammar; it is not the unique-selector key. Selector key is **full exact assignment TypedRef identity** within canonical history namespace. Index is rebuildable, not authority. State at cut:

```text
0 accepted bindings: package not authorized; start/delivery/admission forbidden
1 accepted binding: only its exact retained raw bytes may be delivered
second nonidentical binding: CONFLICT / REJECT, no canonical state mutation
exact binding + exact command retry: same original acceptance/receipt, no new effects
```

Different binding_id, different input cut or different body for the same assignment is not exact retry, even if RawDigest happens to match. Return/use the existing binding rather than minting a second fact. A repeated request under a new command ID for an already exact bound fact must return original binding/receipt through the operation's idempotency resolution, without accepting another command/fact. Same command ID with changed digest is ID_REUSE_CONFLICT. Same expected parent competing transactions have one CAS winner; loser re-resolves accepted state and either returns exact existing result or conflicts. Different bytes cannot be selected by time, path, cache or latest ID.

Package replacement requires a new legal execution retry: new Attempt and accepted AssignmentManifest, with retry refs/reason under the existing FSM. Cancellation/supersession never erases old binding. There is no mutable binding revision or invalidation that authorizes different bytes for the old assignment.

### E.2. Cross-object equalities and validation context

`EqRef` compares complete authoritative typed identity (kind, logical ID when defined, revision_digest, digest profile and schema revision identity) following ADR/typed contract. Field reference class is validation metadata, not a license to change target identity. Resolving a ref includes accepted membership on the required cut, not just finding content in storage.

Let A = resolved binding.assignment_ref; B = unique accepted binding; E = evidence; R = result. Define **derived accessors**, not duplicate stored fields:

```text
B.attempt_ref := A.attempt_ref
B.source_generation_ref := A.source_generation_ref
E.attempt_ref := resolved E.assignment_ref.attempt_ref
E.source_generation_ref := resolved E.assignment_ref.source_generation_ref

EqRef(B.assignment_ref, E.assignment_ref)
EqRef(B.attempt_ref, A.attempt_ref, E.attempt_ref)
EqRef(B.source_generation_ref, A.source_generation_ref, E.source_generation_ref)
E.package_binding_ref resolves to unique accepted B on E.admission_input_history_cut
R.admission_evidence_ref resolves to exact prior accepted E on R.result_input_history_cut
RawDigest(ReadDurable(B.package_raw_ref)) == B.package_raw_ref.raw_digest
len(ReadDurable(B.package_raw_ref)) == B.package_raw_ref.byte_length
RawDigest(ReadDurable(E.result_raw_ref)) == E.result_raw_ref.raw_digest
len(ReadDurable(E.result_raw_ref)) == E.result_raw_ref.byte_length
E.result_slot_contract_ref is exact member of A.result_slot_contract_refs
R.result_payload == Normalize(ReadDurable(E.result_raw_ref), exact slot/normalizer)
```

Campaign, StageRun, LaneRun, lane/stage/spec/source, executor/delivery and knowledge/grant/view identities must resolve consistently through A -> Attempt -> LaneRun -> StageRun and A's exact refs, with matching campaign namespace and all preexisting equality rules. Claimed transport assignment/attempt/source/cut/profile/model/slot must match this resolved context. Caller claims cannot establish it. Allowed runtime executor model must be the one prescribed by the pinned executor profile; generic label equality with another untrusted claim is insufficient.

Three input cuts are distinct: assignment_input_history_cut freezes execution context; binding_input_history_cut is the later input containing accepted A; admission_input_history_cut includes B and STARTED; result_input_history_cut includes accepted E. Do not substitute the assignment cut for current admission cut or synthesize acceptance provenance inside any body. Governing profiles for assignment interpretation remain its pinned context; operation/FSM admission predicates derive from the exact current accepted command input under the same R5.4 campaign.

### E.3. Raw identity and optional semantic identity

Raw authorization is always exact bytes, independent of whether the application displays a semantic checksum. In R5.4 the existing package_digest concept is formally typed as **`PackageSemanticDigest` under external `NF02_PACKAGE_SEMANTIC_PROFILE_V1`**, distinct from RawDigest and ObjectDigest. It is not an invented registered kind. Existing helper outputs are pre-revision implementation checksums, not grandfathered normative package identity.

Freeze the following external profile/transport rule in R5.4:

1. Validate safe ZIP structure and every payload member against transport/assignment grants/views. Normalize member paths exactly according to the existing safe transport profile; reject collisions, duplicates, unsafe names/symlinks and quota violations. Manifest member is exactly `MANIFEST.json`.
2. Parse manifest with duplicate-key rejection and BDB-CJSON-1 compatible values. Manifest context contains exact accepted assignment_ref and its required derived claims. It contains no final ZIP RawDigest, binding ref, accepting commit or future STARTED ref. It may contain one tagged semantic checksum field.
3. Form `M` by removing only `package_semantic_digest` from the parsed manifest. Form `members[]` for **every other delivered member**, sorted by normalized path's UTF-8 bytes, with `{path, raw_digest, byte_length, media_type}`. Digest/length come from actual member bytes; media_type comes from a fixed mapping in the pinned transport profile, never MIME sniffing, host defaults or a caller claim. Embedded member list/count/hash assertions must exactly equal this computed set. A hash-list member may not introduce a dependency on MANIFEST's semantic checksum or the final ZIP hash; such a format is rejected at construction/validation.
4. Descriptor is `{profile_ref: exact external semantic profile pin, manifest: M, members: [...]}`. Semantic value is SHA256(BDB-CJSON-1(descriptor)). Tagged representation is `{profile_ref, digest}`; the expected profile comes from governing R5.4 transport/spec pins, never the manifest's choice. This is a profile-defined checksum, **not BDB-OBJECT-DIGEST-1**. Freeze profile bytes and known-answer vectors in N1–N3.
5. Insert computed tagged checksum in manifest, finalize ZIP, then compute RawDigest(final ZIP bytes). Validator independently rederives the semantic value from the **bound retained raw package**, checks embedded checksum and any result assertion. Canonical binding need not duplicate it.

Repacking identical members can yield same semantic value and different RawDigest. The second ZIP is still unauthorized for that assignment. Changing any delivered prompt/source/template/member or manifest context changes semantic identity; changing ZIP representation can change only raw identity. An external result's input_package_digest is only a checked assertion. Evidence validator derives expected package identity from B, not incoming result or cached job.

This checksum uses the existing CJSON serialization and SHA256 primitive; it does not change ObjectDigest/RawDigest algorithms, TypedRef equality or ADR-006. No new canonical descriptor object, bundle_manifest kind or package manifest authority is introduced.

### E.4. Generation, acceptance, FSM and delivery

Normative sequence, including persistence boundary:

1. Accept A with legal prior/pinned context; required grants, potential exposure and knowledge facts satisfy their existing DAG. A may be accepted in the legal Attempt/Knowledge closure; it is **prior accepted** to all later binding operations.
2. Construct package only from exact accepted A and exact assigned context. Building does not grant exposure access beyond those grants. Freeze prompt/templates/views/source members and validate package against that context; mutable workspace is an input staging source, never final authority.
3. Finalize package bytes, compute semantic checksum as above and final RawDigest. Persist immutable content-addressed bytes, verify digest/length and readable durability. Staging raw alone neither moves history nor authorizes delivery.
4. Construct B with current binding_input_history_cut containing A. `BIND_ASSIGNMENT_PACKAGE` operation authenticates existing actor, enforces uniqueness/FSM/source/profile/knowledge/package validation, CAS and atomic durable raw-reference/history acceptance. A remains immutable. Raw staging failures, partial commits and conflicts cannot yield accepted B without readable exact bytes.
5. Reopen/read retained B.package_raw_ref and verify exact raw identity after acceptance. Missing/corrupt bytes blocks start/delivery. Do not quietly regenerate a semantically similar ZIP or substitute workspace copy.
6. **AttemptStarted MUST be accepted after B, in a separate subsequent commit**. It requires prior accepted A/B, CREATED eligible Attempt, active lane/source/context and existing grants/isolation obligations. Its transition command payload names the exact package_binding_ref; that is PRIOR_ACCEPTED_ONLY, with current HISTORY_INPUT and governing FSM HISTORY_CONTEXT_BINDING. Use existing command_envelope and generic transition/event mechanism, not a new AttemptStarted object kind. No new FSM state is needed. R5.4 transition-profile revision adds the guard; prior profile bytes remain unchanged.
7. Only after this accepted transition may the delivery adapter expose package bytes to executor. It resolves B from accepted history and reads **those bytes from durable raw storage**, rechecking integrity and terminal/source authorization before release. A copy may be materialized atomically and rechecked; mutable pathname never selects content. Delivery profile must specify a serialized/revalidated authorization boundary so a concurrent terminal transition cannot enable a stale delivery request. Potential exposure remains conservative once delivery was possible.
8. Transport envelope outside the already-finalized package may carry binding_ref and authorized STARTED ref. Package itself does not contain them; no package rebuild after binding. Retransmission sends identical raw under the same assignment; re-execution/retry after terminal Attempt creates new Attempt/Assignment under existing retry rules.
9. External result transport asserts exact assignment/binding and slot. Trusted ingestion rederives context from A/B, validates actual raw and admitted slot, and accepts E atomically with retention. Illegal terminal result follows existing QUARANTINED_LATE_RESULT handling, not false accepted current result; adversarial rejection of a proposed canonical fact leaves canonical state unchanged.
10. Accept R in a later commit with PRIOR_ACCEPTED_ONLY evidence ref and legal RESULT_RECEIVED -> RESULT_ACCEPTED FSM effect. Evidence-only ingest may establish the ordinary received transition according to explicit R5.4 operation event profile; no result acceptance before evidence. LaneCompletion and StageCompletion remain distinct subsequent qualification decisions/facts with existing predicates.

Rejected alternatives for AttemptStarted: before binding cannot prove input was frozen/authorized; same commit cannot meet B's prior boundary and complicates durable readback before external effect. The chosen separate commit adds one explicit temporal boundary and uses existing accepted-history CAS.

### E.5. Bound versus actually delivered

B proves **which exact package bytes were authorized for this assignment**, not that an executor received/read/executed them. STARTED proves authorized lifecycle transition, not a fabricated delivery ACK. `DeliveryObserved` is an optional observation/projection in the existing architecture; no registered canonical `delivery_receipt` exists in the active 110-row Registry. `CommandReceipt` acknowledges canonical command acceptance; report_export_receipt concerns report export. Neither proves delivery.

NF02 minimum needs authorized package proof and enforced pre-delivery boundary. Do not add DeliveryReceipt kind. A delivery profile may retain ordinary adapter diagnostics or existing optional observations/ACK with explicit limited claim; canonical disclosure/exposure semantics remain the existing grant/PotentialExposure rules. A future requirement to prove actual receipt would need its own approved contract and vectors. Report/evidence must say “authorized package” unless actual delivery is separately evidenced.

### E.6. Capability and raw retention

Current private-key/HMAC capability issuance checks prior refs and raw derivation; durable key and token live in the remediation. That is an implementation enforcement primitive, not new semantic authority. In /2 the trusted Store operation either derives evidence itself from accepted A/B/raw or validates an authenticated call/capability scoped to exact campaign/assignment/B/slot/result raw/current authorization. A caller choosing command_kind or serializing trusted=true cannot mint it.

Capability/token must remain outside canonical body/digest and ordinary exported history. Expiry, replay, revocation and key rotation are runtime policy; accepted provenance survives process restart and key rotation through exact facts/raw. Canonical read/replay validates schema, accepted identities, raw and producer acceptance provenance, not possession of an old process token. New writes always recheck current actor/FSM authority. No secret is an accepted fact, and no evidence boolean establishes trust.

Accepted package/result raw and required embedded evidence members must remain retrievable for replay, completion, reopen and reporting. Corruption/missing-object discovery blocks authority-consuming actions without modifying past accepted bytes/head. Restore can use only independently verified identical raw bytes at the same digest; nonidentical rebuild is a new package for a new assignment. External rollback threats retain existing anchoring/backup qualification; process crashes alone do not qualify them.

## F. Alternatives considered

| Model | Feasible variant | Evaluation / decision |
| --- | --- | --- |
| A — assignment_manifest/2 with input_package_ref | Package built first without final assignment identity, then assignment binds RawRef | Can be acyclic only if package does not contain the final assignment digest. It replaces assignment creation/closure and every consumer/schema, or needs a new package context/preassignment identity. Exact “this assignment” in package becomes weaker/indirect. If package contains final assignment identity, A -> package -> A creates an impossible hash cycle. Breaking assignment migration and package ordering are avoidable. Reject for NF02. |
| B — separate immutable binding | Prior accepted Assignment/1 -> final package -> binding -> start/delivery | Acyclic, exact raw authorization, preserves assignment history, package can include exact A ref, idempotent freeze/retry and single accepted selector. Additional fact/commit is justified by missing temporal authority. **Select.** |
| C — one canonical closure with Assignment and package | Package may refer earlier assignment whose body does not refer package | Topological acceptance is possible for a carefully unilateral closure, but accepted assignment would not precede package construction. It still needs a fact linking raw package back to assignment and would require weakening PRIOR_ACCEPTED_ONLY to content semantics. If assignment also directly binds package, cycle returns. Omitting package->assignment would reduce exact package provenance. Reject as unnecessary bootstrap-like exception outside bootstrap scope. |
| Executable-schema binding only | Add local schema bytes while preserving unregistered kinds | Does not establish semantic kind/role legality. Explicitly violates §§184–188. Reject. |
| Retain extension/overlay as a “foundation addendum” | Byte-pin extension file in source | Pins implementation bytes, not authorized normative revision or campaign activation. Would create a second authority. Reject. |
| Reuse final bundle_manifest/1 for assignment input authorization | Bind export membership manifest | Existing EXPORT authoritative_for final bundle is not assignment delivery authorization. Repurposing changes its meaning and still leaves temporal uniqueness/binding gap. Reject. |
| Canonical capability / new delivery receipt | Serialize secret or trusted flag; add delivery kind | Capability is not enduring provenance; receipt expands NF02 beyond exact authorized package minimum. Reject. |

Backward compatibility is explicit historical readability, not transparent acceptance of old wire bodies as new contracts. Version `/2` does not alias `/1`; new campaign must produce lawful new facts.

## G. Reference / DAG analysis

Arrows below mean prerequisite -> dependent object/event; refs in a dependent object point backward.

```text
prior/pinned campaign, source, stage/lane, executor/delivery, slot profiles
      -> Attempt -> grants/exposure -> KnowledgeState -> Assignment/1 [accept H_a]
Assignment/1 -> package manifest + member bytes -> final ZIP raw
(Assignment/1, final ZIP raw, input H_b) -> Binding/1 [accept H_b+1]
Binding/1 -> AttemptStarted [accept later H_s]
Binding/1 + STARTED authorization -> delivery -> external execution -> raw result
(Assignment/1, Binding/1, raw result, slot, input H_e) -> Evidence/2 [accept H_e+1]
(Evidence/2, derived payload, input H_r) -> Result/2 [accept H_r+1]
Result/2 -> LaneCompletion -> StageCompletion -> report / later assurance gates
```

A's body has no B/package/raw forward ref. Package contains A but neither B nor its own final RawDigest. B references prior A and already finalized raw, not own accepted commit. Evidence references prior A/B and independent result raw; it contains no R ref. R references prior E. Slots/profiles are accepted/pinned prerequisites, not new objects authorizing their own consumers. Thus every dependency moves forward in construction time; no edge returns from a prerequisite to the new object's final digest. Hash fixed point is unnecessary.

All NF02 material refs/classes are enumerated in D.2/D.3. HISTORY_INPUT is prior history value, not an object in the accepting closure. Derived attempt/source/profile accessors do not add material refs or a second authority. Command actor uses existing AUTHORIZED_ACTOR_REF/prior authority; source uses existing SOURCE_AUTHORITY_REF. Bootstrap initial pins remain PINNED_INSTALLATION_REF. Same-commit CONTENT_OR_PRIOR is unchanged in the existing Attempt/Knowledge/Assignment closure; **binding.assignment_ref is PRIOR_ACCEPTED_ONLY** and cannot reuse that exception.

The binding's raw ref uses CONTENT_OBJECT for immutable content prerequisite with explicit retained-content reuse permission. “Prior retained raw” does not mean prior accepted canonical fact; the accepted B creates ACCEPTED_REFERENCE and retention obligation. Nested raw contract/profile pins are PINNED_PROFILE_REF. Normal command policy/spec/FSM context remains HISTORY_CONTEXT_BINDING. CommandReceipt/event positions are existing POST_ACCEPTANCE_SIDECAR, excluded from object preimages. No new unknown ref-class tokens.

Registry forward-target resolution must allow the registered NF02 kinds as registered_immutable_object targets where existing generic output refs legitimately consume them, with exact allowed versions. Complete named ref contracts still restrict targets. No global lexical ordering change, fake content refs or new bootstrap precedence groups.

## H. Migration semantics

| Existing material | Allowed interpretation/action | Forbidden claim/action |
| --- | --- | --- |
| Legal pre-NF02/R5.3 campaign history | Read-only historical replay under exact original pinned schemas/specs and retained bytes. Separate historical report with source/schema provenance. | R5.4 current assurance, latest-schema validation replacing historical semantics, retroactive binding/start chronology. |
| History containing unregistered NF02 /1 extensions | Preserve bytes and receipts for forensic/history display; explicitly unqualified/nonconforming for C1. Reader uses isolated historical decoding, never R5.4 accepting path. | Treat local extension as normative R5.3 legality or map /1 into /2. If legal replay cannot establish authority, expose that limitation instead of fabricating valid canonical state. |
| In-flight old Assignment / delivered old package | Stop old current execution for this migration boundary; create new R5.4 campaign, new Attempt/Assignment/package/binding before new delivery. Preserve old grants/exposure as historical context. | Add B after delivery and claim it preceded execution; reuse old STARTED transition as R5.4 authorization. |
| Old result/raw with missing retained closure | Historical integrity block; retain diagnostic identity. Identical byte restoration may repair availability only when independently verified. | Automatic backfill from mutable workspace, fabricated package relation, fabricated receipt or qualified new result. |
| Old results/evidence potentially useful in new audit | Treat as untrusted historical input, subject to existing explicit lineage/source/evidence applicability/knowledge admission assessment and new grants. Preserve actual historical chronology. | Automatic R5.4 result/slot satisfaction or blind-origin independence from old results. |
| New independent R5.4 campaign | New namespace/genesis using qualified existing bootstrap contract with exact R5.4 pins; new execution context. Existing source identity may be reused only through its legal exact authority contract. | A second normal genesis on nonempty old namespace or EMPTY_HISTORY reuse after seq=1. |
| Concluded predecessor with independently legal successor trigger | Existing SuccessorCampaignGenesis and branch-selection rules may apply if every predecessor/trigger requirement is separately met. | Invent “schema install” as a new allowed successor trigger, treat an unconcluded campaign as concluded, or bypass assurance branch resolution. |

**Mandatory default: new independent campaign**, not in-place migration or a newly invented successor trigger. Product may present explicit historical linkage, but that display does not assert assurance succession. No canonical migration kind is added. No automatic package binding backfill. Historical /1 bytes never get a new accepting input cut.

R5.4 installation retains historical readers and original pins. Its writer rejects attempts to open old campaign for new-contract writes with a stable compatibility error in STATE_CONFLICT family. Migration status/profile is explicit UI/CLI context; it is not a mutable canonical campaign state authority.

## I. Proposed normative files to revise

All CHANGE REQUIRED entries mean **new versioned successor files/records**, not edits to predecessor corpus. Candidate filenames should be unambiguous (`..._R5_4...` or a separate immutable R5_4 candidate directory); manifest identifies each exact file, including unchanged carried-forward bytes. Proposed public ID: BDB_AUDIT_V2_FOUNDATION_R5_4; no hashes are invented before bytes exist.

| Artifact | Decision | Why / exact contract impact |
| --- | --- | --- |
| DATA_AND_ARTIFACT_CONTRACTS | CHANGE REQUIRED | Add the complete bodies/refs/predicates in D/E; SchemaRegistry/2; typed semantic checksum profile; exact one-package selector; prior start boundary; raw retention; /1 historical-only and no in-place migration. Amend assignment section by adding downstream binding relationship without altering assignment_manifest/1 body/digest. §§14–16,95–96,107–109,184–188 retain invariants. Define stable binding conflict/pre-delivery compatibility reasons within existing error families. |
| ARCHITECTURE_SPEC | CHANGE REQUIRED | Add raw package freeze -> B -> later STARTED -> delivery pipeline, trusted admission derivation, replay/retention and authorization versus delivery distinction; historical reader/new campaign boundary. Update §§6.7,6.9–6.10,41–44 and recovery/standalone paths. Keep one history authority and no runtime latest-schema selector. |
| ARTIFACT_CONTRACT_REGISTRY | CHANGE REQUIRED | Three new kinds/versions per D.2, schema_registry/2 complete row, NF02_PROVENANCE profile, explicit target-version/ref parity and relevant completion output wiring. No new role domain, ref class, capability kind or aliases. Exact successor registry ID/version and normative_basis. Binding/ingest/transition command contracts remain command_envelope payload/profile semantics, not separate digest kinds. |
| TEST_AND_SELF_AUDIT_PLAN | CHANGE REQUIRED | Add J vectors and N9–N11 exact gates, mutation snapshots, live/restart/raw integrity, migration/schema root/capability adversarial coverage; explicit evidence-scope exclusions, E1–E5 application path and artifact/clean-room qualification. Preserve all existing mandatory checks and source/evidence traceability. |
| IMPLEMENTATION_ROADMAP | CHANGE REQUIRED | Insert ordered normative-resolution/activation and NF02/lifecycle qualification gates, dependencies and affected assurance closure. Do not advance milestone merely for local tests or fold next features into NF02. Preserve qualification order and DoD. |
| IMPLEMENTATION_EXECUTION_PLAN | CHANGE REQUIRED, scheduling only | Successor task packet contains N1–N11 and mapping to existing M5/M8/M9/M10, orchestration, delivery and qualification components. Not a new normative authority; still subordinate to approved complete sources. |
| ADR-006 | NO CHANGE to identity semantics | Exact registered kind domains, existing CJSON/RawDigest/ObjectDigest/TypedRef/DAG algorithms and `<wire kind>_<uuidv4-lowercase>` IDs suffice. Successor schemas enforce this existing grammar for new registered kinds; semantic checksum is external profile checksum, not new ObjectDigest algorithm. Carry exact predecessor ADR bytes with provenance. No artificial version churn. |
| FOUNDATION_GOLDEN_VECTORS | CHANGE REQUIRED | New R5_4 file/set containing 117 exact inherited vectors plus J. Preserve historical expectation labels as predecessor tests; add R5.4 activation/current-label cases, not silently rewrite an old vector. Fixture hashes and expected canonical preimages must be computed/frozen in N1–N3. |
| SchemaRegistry + executable schemas | CHANGE REQUIRED | Exact new SchemaRegistry/2 revision and frozen files for all reachable first-acceptance kinds; raw schema digest/length/$id closure; bootstrap root pin and offline backend profile. Changing required refs/body/predicates is breaking, not optional /1 patch. |
| Installation bootstrap / transition / transport / slot / normalizer external profiles | CHANGE REQUIRED, exact successor revisions | Same existing canonical profile kinds/root shape where unchanged. Pin R5.4 schema/Registry, add start guard and finite deterministic transport/payload/semantic checksum rules; version breaking transport/slot contracts explicitly. Existing campaign cannot silently consume them. |
| Candidate manifest, qualification/governance records, documentation index | CHANGE REQUIRED for successor provenance/activation | New candidate set/manifest with predecessor hashes, exact readback, external authorized qualification/freeze records as applicable; index points at successor when approved. Do not update predecessor author qualification, frozen identity or normative bytes. |
| Methodology and V1 migration corpus | NO semantic CHANGE for NF02 | Existing knowledge, truth/evidence, isolation, successor and bootstrap constraints are preserved. Carry unchanged exact sources in candidate manifest; explicit NF02 campaign compatibility boundary lives in the successor contracts. |

N1 must establish corpus self-audit parity across narrative/Registry/profiles/Golden; a remaining conflict blocks approval/freeze. This proposal supplies exact model decisions but is not the complete produced R5.4 candidate bundle, executable schemas or approval record.

## J. Golden / adversarial vectors

Each R5.4 vector uses the existing uniform `{id, domain, input, expected, title, why}` shape. Freeze exact serialized inputs/expected preimages/raw blobs in the successor vector set. Table is the normative fixture design; no runtime PASS is claimed here.

Shared fixture: legally initialized R5.4 campaign with exact Registry/SchemaRegistry/profiles, prior A/Attempt/source/slot, finalized safe package P and retained raw, deterministic result Q. Fixture identities are computed from frozen bytes in N1–N3, never fabricated zero hashes. Each negative test snapshots **accepted head, commits, event sequence, immutable accepted objects, command/receipt index, binding/slot selector and accepted raw retention refs** before/after. Every negative expected outcome is **REJECT + NO CANONICAL STATE MUTATION**, including when called directly through Coordinator/Store. Local quarantine/log/staging content is permitted only outside canonical authority and cannot satisfy a ref/gate.

| ID | Input/change | Expected |
| --- | --- | --- |
| NF02_SCHEMA_UNREGISTERED_KIND_REJECT | Exact local schema present, kind absent from governing Registry | REJECT unregistered-kind family; no canonical mutation |
| NF02_SCHEMA_BYTES_NOT_BOUND_REJECT | Kind/key registered; no accepted/pinned executable-byte binding | REJECT SCHEMA_BYTES_NOT_BOUND; no canonical mutation |
| NF02_SCHEMA_WRONG_DIGEST_REJECT | Schema file bytes differ from pinned RawDigest/length | REJECT schema/digest mismatch; no canonical mutation |
| NF02_SCHEMA_EXACT_BINDING_ACCEPT | Kind/version/key and exact schema bytes, set root and campaign context all match | ACCEPT; same identities on replay; no runtime-generated alternative |
| NF02_PACKAGE_BINDING_ACCEPT | Prior A; exact valid durable P; no binding/start | ACCEPT one B; exact raw retrievable after reopen |
| NF02_PACKAGE_BINDING_SECOND_CONFLICT_REJECT | Existing B for A; different P or B body/ID/cut | REJECT CONFLICT in STATE_CONFLICT family; no canonical mutation |
| NF02_PACKAGE_BINDING_EXACT_RETRY | Original exact command/body repeated, including after ambiguous ACK/restart | Original receipt/B; zero additional canonical effects; durable raw reverified |
| NF02_PACKAGE_RAW_SUBSTITUTION_REJECT | Replace delivery/intake candidate bytes with different ZIP, even same semantic members | REJECT candidate/substitution; no canonical mutation; B and authoritative P remain unchanged. Deleted/changed disposable workspace may instead be ignored and delivery reconstructed from original retained P. |
| NF02_PACKAGE_SEMANTIC_MISMATCH_REJECT | Claimed manifest/result semantic checksum differs from rederived bound P; or wrong profile tag | REJECT package semantic mismatch; no canonical mutation |
| NF02_PACKAGE_WRONG_ASSIGNMENT_REJECT | Package or evidence names another exact assignment, or same logical ID different revision | REJECT wrong binding; no canonical mutation |
| NF02_PACKAGE_WRONG_ATTEMPT_REJECT | Package/result derived attempt claim differs from A.attempt_ref | REJECT wrong binding; no canonical mutation |
| NF02_PACKAGE_WRONG_SOURCE_REJECT | Different source generation/revision/tree or authority pin despite matching selfclaims | REJECT source/binding conflict; no canonical mutation |
| NF02_RESULT_WITHOUT_PACKAGE_BINDING_REJECT | Raw result submitted for A with zero accepted B | REJECT missing binding, even valid result checksum/capability; no canonical mutation |
| NF02_RESULT_WRONG_PACKAGE_BINDING_REJECT | E names another B/campaign/assignment or same logical ID wrong revision/schema identity | REJECT wrong exact binding; no canonical mutation |
| NF02_PACKAGE_BINDING_AFTER_DELIVERY_REJECT | Attempt already STARTED under old path or harness proves disclosure before proposed B | REJECT pre-delivery invariant; no canonical mutation; cannot launder previous execution. Complement with zero disclosure before B in delivery adapter test. |

Additional mandatory adversarial/positive pairs needed to prove this chosen model:

| ID | Fixture / expected condition |
| --- | --- |
| NF02_BINDING_SAME_COMMIT_ASSIGNMENT_REJECT | A in proposed binding closure -> REJECT + no canonical mutation; prior accepted A positive control. |
| NF02_START_WITHOUT_PRIOR_BINDING_REJECT | Missing or same-commit B -> REJECT + no canonical mutation; separate prior B -> accept transition. |
| NF02_DELIVERY_BEFORE_BINDING_REJECT | Adapter attempts export/share/open executor bytes before B/STARTED -> REJECT, zero disclosure and no canonical mutation; accepted prerequisites -> deliver exact P. |
| NF02_PACKAGE_SELF_HASH_REJECT | Manifest contains final ZIP raw hash or forward binding/start identity -> REJECT + no canonical mutation; manifest with prior A and profile checksum accepts. |
| NF02_PACKAGE_REPACK_IDENTITY_SEPARATION | Same manifest/members, different ZIP metadata: semantic checksum equal, raw digest unequal; second binding/candidate substitution -> REJECT + no canonical mutation. |
| NF02_SCHEMA_ROOT_SELF_AUTHORIZATION_REJECT | Caller provides arbitrary registry/root/schema to validate itself, same-commit context upgrade, or latest installed set on old campaign -> REJECT + no canonical mutation. Exact external installation pin positive control. |
| NF02_ROLE_OR_ALIAS_REJECT | PROVENANCE/PROPOSAL, wire alias, version fallback, unknown ref class -> REJECT + no canonical mutation; exact FACT/kind/version/ref classes accept. |
| NF02_CAPABILITY_FORGERY_REJECT | Caller-chosen ingest command, trusted=true, copied/forged/out-of-scope/replayed runtime capability -> REJECT + no canonical mutation; authenticated rederived operation accepts. |
| NF02_SECRET_ROTATION_HISTORY_REPLAY | Accepted facts/raw replay after legitimate key rotation/restart without serialized token; new unauthorized write -> REJECT + no canonical mutation. |
| NF02_EVIDENCE_SAME_COMMIT_RESULT_REJECT | R references evidence in its accepting closure -> REJECT + no canonical mutation; prior E positive control. |
| NF02_RESULT_PAYLOAD_MUTATION_REJECT | Change findings/output/member evidence after E, caller recomputes checksum -> REJECT + no canonical mutation; exact Normalize(Q) accepts. |
| NF02_RESULT_SLOT_CONFLICT_REJECT | Another raw result for closed exact A/slot, wrong slot or omitted required slot -> REJECT + no canonical mutation; exact original retry idempotent. |
| NF02_PACKAGE_RESULT_RAW_MISSING_OR_CORRUPT_REJECT | Remove/corrupt authoritative package/result/required schema or canonical ref target before start, evidence, result, completion or reopen -> REJECT + no canonical mutation; exact independently verified byte restoration restores availability only. |
| NF02_CONCURRENT_BINDING_CAS | Two simultaneous candidates same parent: one winner; different loser -> REJECT + no canonical mutation beyond winner; exact loser retry returns existing fact. Repeat across processes. |
| NF02_RAW_HISTORY_CRASH_ATOMICITY | Process death at each raw/reference/object/event/commit/head/receipt persistence boundary -> either complete durable accepted closure or no canonical change; never partial authority/delivery. Include binding, evidence, result and restart. |
| NF02_OLD_CAMPAIGN_WRITE_REJECT | R5.3 campaign, /1 evidence or retroactive B after old execution -> REJECT + no canonical mutation; historical display limited, new R5.4 campaign positive control. |
| NF02_PACKAGE_ZIP_JSON_ADVERSARIAL_REJECT | Duplicate keys/members, traversal/case/normalized collisions, bomb/quotas, symlink, truncated/concatenated ZIP, forbidden extra manifest context -> REJECT + no canonical mutation; valid finite package accepts. |

Negative “after delivery” fixture alone cannot prove a hidden external side effect never happened. Qualification must additionally instrument the real adapter and assert zero access/export callbacks before accepted guards. Binding is an authorization fact, not self-attested delivery evidence.

## K. Ordered implementation plan

All tasks below are **future work after required owner approval**, not changes performed now. Normative refs shorthand: DC=successor Data contracts retaining C, ARCH=successor Architecture, REG=D rows, GV=J, TEST=successor test plan, RP=successor Roadmap, EP=successor scheduling packet. Rollback never deletes/reinterprets accepted history: before activation discard unpublished candidate/build; after activation stop new writes/delivery and restore exact approved artifacts or start a new legal campaign. Old schema writer is never rollback for a campaign already using R5.4.

### N1 — approve normative delta

- **Objective:** approve A/D/E/H model; produce complete versioned R5.4 candidate and external governance evidence.
- **Dependencies:** this proposal, pinned predecessor corpus, explicit owner decisions L.
- **Files/components:** successor DC/ARCH/TEST/RP/EP, candidate manifest/readback/self-audit, profiles/Golden fixtures; predecessor files read-only.
- **Normative refs:** DC §§14–16,95–96,184–188, w szczególności §§187.1–187.2; governance records; A–J.
- **Outline:** implement normative wording only; freeze full ref/slot/transport/error/FSM/profile semantics before coding; preserve predecessor lineage; review all conflicts. Generate exact candidate manifest and external author qualification or independent freeze under existing governance.
- **Positive tests:** complete narrative/Registry/body parity, source hashes/readback, governance actor and record binds exact candidate.
- **Negative tests:** missing approval, modified predecessor, incomplete manifest, false self-qualification -> reject qualification.
- **Adversarial tests:** alternate alias/profile, ambiguous cut/version, copied qualification for different candidate.
- **Acceptance:** explicit owner approval and governance-qualified exact candidate; no SPEC_CONFLICT among proposed machine/narrative inputs. Author-only versus independent status explicit.
- **Rollback:** discard unapproved candidate artifacts; preserve predecessor and proposal.
- **Blast radius:** specification authority and all subsequent NF02 evidence; no runtime activation yet.

### N2 — freeze new Registry

- **Objective:** authoritative successor machine inventory, no extensions required for NF02.
- **Dependencies:** N1 approved semantics; candidate finalization iterates with N1 until exact consistent freeze.
- **Files/components:** successor ArtifactContractRegistry JSON, core Registry loader/packaged pin planning; full ref/validation/target-version map.
- **Normative refs:** REG/D.2–D.3; DC §§184–188; ADR unchanged.
- **Outline:** add complete three new kind rows and schema_registry/2, named validation profile, exact version resolution and output target wiring. Preserve inherited roles/classes/ordering. Do not absorb unrelated overlay without separate authorized semantics.
- **Positive tests:** Registry definition validation, exact registered key resolution, complete nested RawRef/profile fields.
- **Negative tests:** unknown role/ref/kind, duplicate key, alias, wrong schema key, omitted material ref -> reject.
- **Adversarial tests:** shadow/override via extension/local file; /1 fallback to /2; changed pinned bytes.
- **Acceptance:** exact frozen Registry digest, parity self-audit and machine vectors; no unregistered new ObjectDigest domain.
- **Rollback:** no runtime activation; supersede candidate through governance if bytes need change.
- **Blast radius:** every canonical resolver/schema generation/qualification depending on Registry; assess inherited evidence bindings.

### N3 — freeze exact executable schemas

- **Objective:** durable exact schema files/dependency/profile closure for first acceptance.
- **Dependencies:** N2 exact semantics and N1 candidate approval.
- **Files/components:** schemas/ frozen successor assets, existing schemas/binding.py substrate, schema/profile manifests, GV known-answer fixture bytes.
- **Normative refs:** DC §184; REG; D.3; existing offline backend rules.
- **Outline:** generate build-time candidates; review complete schemas for /1 inherited reachable objects and new /1-/2 rows; freeze `$id`, dialect, RawDigest/length and validator dependency identity. Materialize the finite result slot/finding/output and package transport schema specified in N1; no additionalProperties escape hatch. Verify executable behavior against exact known-answer fixtures already fixed in the approved Golden set; do not change its inputs or expected outcomes to match code.
- **Positive tests:** exact fixture validates, RawDigest/readback/dialect/parity, semantic checksum known answers and repack distinction.
- **Negative tests:** mutated/truncated schema, missing dependency, format/$ref/network resolution or duplicate fields -> reject acceptance.
- **Adversarial tests:** benign-looking schema with removed required ref; wrong root schema; unknown dynamic/remote references.
- **Acceptance:** all kinds reachable before first runtime acceptance have exact executable bytes and no semantic drift; fixture expected hashes independently checked. Schemas alone do not activate runtime. If any approved normative/Registry/Golden/profile bytes or semantics must change during N2/N3, invalidate the affected candidate qualification, return to N1, produce a new exact manifest/readback and external approval record before N4. Model approval is never a transferable approval for different candidate bytes.
- **Rollback:** replace unactivated candidate set through new exact manifest/governance, never silently overwrite pinned files.
- **Blast radius:** all affected validators/harness/GV and environment-sensitive dependency evidence.

### N4 — create/pin SchemaRegistry revision

- **Objective:** legal trusted activation for new campaigns.
- **Dependencies:** N1 governance, N2 Registry, N3 schema files/profiles.
- **Files/components:** schema_registry/2 asset/body, installation_bootstrap_profile/1 successor revision, bundle loader/bootstrap, Registry/schema resolver, build payload pins.
- **Normative refs:** DC §§14.6,95–96,184; D.3; R5N03/26/37/65/77/80.
- **Outline:** construct immutable binding set, compute canonical digest, external exact root schema pin/readback; authorized install retains old readers/pins; seq1 qualified bootstrap establishes R5.4 context using allowed initialization command. Resolve schema per campaign/cut.
- **Positive tests:** fresh legal bootstrap, schema-root first validation, exact new kinds accepted only after all bindings.
- **Negative tests:** unregistered kind, missing/wrong schema, unapproved bundle, old campaign current-set substitution -> reject without mutation.
- **Adversarial tests:** self-authorizing registry, malicious latest-installed set, same-commit semantic self-upgrade, bootstrap-union cycle.
- **Acceptance:** four schema vectors PASS plus inherited bootstrap/governance gates; exact installation pin -> campaign set chain demonstrated. No old-campaign writes enabled.
- **Rollback:** disable new campaign creation/writes; restore exact trusted installation artifacts; retain all created histories.
- **Blast radius:** bootstrap, all campaign authority/schema consumers, standalone build and package pin verification.

### N5 — implement AssignmentPackageBinding

- **Objective:** one immutable accepted raw authorization per exact assignment.
- **Dependencies:** N4 legal kinds/schemas; N2 contract freeze.
- **Files/components:** history objects/Store/authority_hooks/raw_artifacts, orchestration/FSM, coordinator operation contract; focused tests.
- **Normative refs:** REG D.2.1; E.1–E.2; DC history/CAS/ID rules.
- **Outline:** reuse canonical object/ref/transaction mechanisms; add binding acceptance operation and rebuildable exact selector; enforce prior A, current cut, raw/profile/source/knowledge validation, no prior start, idempotency and conflict. Avoid parallel mutable authority table.
- **Positive tests:** zero -> one B, durable reopen, original receipt exact retry.
- **Negative tests:** second B, wrong A/cut/source/profile, same-commit A or reused changed command ID -> reject without mutation.
- **Adversarial tests:** concurrent/process CAS, same logical ID different full ref, duplicate binding with same raw but new ID, generic Store bypass.
- **Acceptance:** binding vectors and all ref/uniqueness/atomicity invariants PASS; no canonical /1 reinterpretation.
- **Rollback:** block writes/delivery; retain accepted B and bytes; no deleting selector/history.
- **Blast radius:** history/ref validation/transactions; assess all dependent authority evidence.

### N6 — wire package creation/storage/binding

- **Objective:** exact package constructed from accepted context and frozen before delivery/start.
- **Dependencies:** N5; N3 transport/semantic checksum; N4 campaign activation.
- **Files/components:** workflow/packaging.py, manual_stage.py, assignments.py, package_resume.py, stage_resume.py, workflow/executors.py, raw vault, transition profile/operation adapter.
- **Normative refs:** E.3–E.5, ARCH delivery §44.3, existing grants/PotentialExposure/isolation.
- **Outline:** finalize package -> store -> B accept -> durable readback -> separate accepted STARTED -> adapter releases retained bytes. Batch/job fields become disposable projections of exact accepted refs. Resume may recover original package from vault even when workspace copy vanished. Delivery guard serializes/revalidates against terminal transitions.
- **Positive tests:** E1 and manual-stage flows, multiple result slots, exact retransmission, deleted workspace recreated from vault, package includes A not B/hash.
- **Negative tests:** delivery/start before B, wrong/repacked raw, semantic/profile/context mismatch, missing raw -> reject without mutation/disclosure.
- **Adversarial tests:** crash at each package/raw/B/start boundary; live workspace substitution; terminal/source race during delivery; ZIP/JSON malformed cases.
- **Acceptance:** real adapter has zero disclosure callbacks before guards; delivered bytes equal B RawRef; restart resumes accepted B rather than regenerating authority.
- **Rollback:** suspend delivery/write path; keep accepted packages/bindings/exposure; resume only with exact approved bytes.
- **Blast radius:** E1–E5 shared packaging/resume, executor delivery and knowledge exposure, standalone CLI/UI.

### N7 — wire admission/result validation

- **Objective:** accepted evidence and result derive exclusively from prior A/B and retained result raw.
- **Dependencies:** N6 authorized package path; N4 /2 schemas; N5 history invariants.
- **Files/components:** inbox.py, manual_stage.py, result_proposal.py, Store/authority_hooks, schemas assets, lane/stage completion and STOP/output consumers.
- **Normative refs:** D.2.2–D.2.3; E.2/E.6; existing result FSM/evidence qualification/L7.
- **Outline:** remove canonical token and redundant context/proposal checksum; authenticated ingestion derives E/2; later R/2 rederives payload; bind exact slot and unique package B. Check generic/direct Store paths as well as Inbox. Update allowed consumer versions without aliases or truth promotion.
- **Positive tests:** legitimate E1/manual results, evidence -> later result -> required outputs/completion; exact retry; replay after key rotation.
- **Negative tests:** no/wrong B, mismatched claims, no prior E, forged payload, terminal/wrong/closed slot -> reject without canonical mutation.
- **Adversarial tests:** copied/forged capability with valid command, ref identity laundering, altered findings after admission, raw deletion between commits, forged completion/STOP bypass.
- **Acceptance:** all result vectors PASS through production acceptance API and direct Store; result content equals exact raw normalization; Lane/StageCompletion still require their full predicates.
- **Rollback:** disable new intake/completion writes; retain all raw/E/R accepted state; do not downgrade to /1 acceptance.
- **Blast radius:** provenance consumers, authority/history, all stage result adapters, discovery/evidence/STOP and report.

### N8 — migration / fail-closed compatibility

- **Objective:** explicit historical read-only and new campaign boundary.
- **Dependencies:** N4 new initialization, N6/N7 lawful fresh execution.
- **Files/components:** campaign open/create, legacy/historical reader adapters, workflow resume, UI/CLI migration status, compatibility fixture/harness and report provenance.
- **Normative refs:** H; DC §96/initialization/successor rules; ARCH recovery.
- **Outline:** recognize exact historical schema sets and unqualified extension histories; preserve objects/raw and expose limited historical status; block new-contract writes. Offer/create legally bootstrapped new namespace only through authorized product action. No retro B or forced conclusion.
- **Positive tests:** old history readable with original identities; new legal R5.4 campaign works; separately valid existing successor rules preserved.
- **Negative tests:** old namespace schema auto-upgrade, retro binding, /1 -> /2 alias/backfill, nonempty genesis -> reject without mutation.
- **Adversarial tests:** migration with missing objects, forged original chronology, actor/source authority substitution and old evidence auto-qualification.
- **Acceptance:** no old campaign obtains new assurance by opening/installing; exact history bytes unchanged; compatibility claims scoped and tested.
- **Rollback:** disable migration writer/new campaign helper while retaining historical viewer; never reset campaign DB/history.
- **Blast radius:** application opening/resume, historical/legacy compatibility and assurance lineage; qualify affected harness paths.

### N9 — adversarial qualification

- **Objective:** prove frozen semantics and boundaries independently of friendly workflow tests.
- **Dependencies:** N5–N8 and exact N1–N4 inputs.
- **Files/components:** successor GV runner, targeted NF02 tests, existing transaction/crash/schema/parser/authority/harness tests, exact evidence manifest.
- **Normative refs:** J; TEST material contract positive/negative/adversarial rule; DC mutation/authority invariants.
- **Outline:** instantiate every vector with exact known-answer inputs; production API, direct Store and standalone paths; instrument external delivery; subprocess crashes/races; compare accepted-state snapshots. Reuse current tests when they cover property under new exact dependencies; add only missing regression vectors.
- **Positive tests:** legal exact binding/admission/result, identity separation, idempotency/restart.
- **Negative tests:** every J rejection proves zero canonical mutation; unsupported historical write/unsafe input.
- **Adversarial tests:** every extra J vector, parser quotas, secret/ref/schema spoofing, races and corruption.
- **Acceptance:** all frozen expected outcomes evidenced, zero silent skip, all required negative mutation/disclosure assertions pass. A harness/parser defect is repaired, not labeled external blocker.
- **Rollback:** stop qualification/activation claims; fix root cause and rerun targeted + affected mandatory broader gates; do not loosen vector expectation.
- **Blast radius:** fixtures/GV/harness/qualification verifier are assurance dependencies; assess every dependent evidence binding.

### N10 — full NF02 qualification

- **Objective:** qualify C1/C2 and remediation together on exact implemented state.
- **Dependencies:** N1–N9 PASS with exact authority/evidence pins; no unratified dependency on unrelated extension authority.
- **Files/components:** all affected source/tests/build, NF02 qualification artifact, phase/milestone verifiers, compatibility corpus, release validator and CI configuration.
- **Normative refs:** TEST full gates; RP/EP affected milestones and qualification closure; C authority hierarchy.
- **Outline:** targeted -> affected components -> required cross-cutting/full repository checks -> required milestone/phase verifier. Assess F0–F8 dependency evidence individually; changed Registry/schemas/GV/history/harness invalidate reuse on their affected paths. Reuse unaffected evidence only if all governing exact blobs/inputs/environment conditions still bind it. Run required broader gates, Ruff/Mypy/build/local validator, compatibility/clean-room/exact-source CI where governing release contract requires them. Preserve separate qualification scope labels.
- **Positive tests:** complete package/evidence/result raw chain across live/reopen; completion/STOP legal controls; manifest matches implemented/dependency blobs.
- **Negative tests:** missing mandatory subordinate gate, stale artifact, drifted fixture/schema/backend, false truth or release PASS -> qualification reject.
- **Adversarial tests:** independent re-audit original NF02 bypasses and new binding/schema/authority attacks against exact packaged runtime.
- **Acceptance:** no C1/C2 SPEC_CONFLICT, owner-approved activated normative corpus, every named mandatory NF02/subordinate gate PASS, no relevant drift afterward. N11 application gate remains separately required before claiming overall application qualification. Current 249 PASS is not substitute.
- **Rollback:** fail-closed disable affected writer/delivery; preserve histories; remediation loop until correct or genuine external blocker. No retrospective NF02 CLOSED.
- **Blast radius:** shared authority/identity/schema/qualification, all evidence consuming changed contracts and release packaging. Future commit only if separately authorized; then required terminal post-commit verifier checks intended committed state and transitive subordinate artifacts, otherwise run missing checks. No commit/push authority comes from this plan.

### N11 — complete application lifecycle qualification

- **Objective:** demonstrate a real application lifecycle, including retained raw and safe continuation after restart.
- **Dependencies:** N10; qualified packaged runtime, legal exact R5.4 bootstrap input and existing stage/report contracts; all lifecycle-used wire kinds legally registered. An unrelated residual_risk/other overlay cannot be accepted merely because local tests pass.
- **Files/components:** shipped application startup/open/create, campaign coordinator, all required E1–E5 stage services and adapters, vault/history recovery, report generator/export, standalone build/validator, application E2E evidence/phase verifier.
- **Normative refs:** user lifecycle below; TEST E1–E5/standalone/recovery/release/verification; ARCH campaign/flow/raw retention; RP/EP final application gates.
- **Outline:** run production application with fresh workspace and process, legal bootstrap (current allowed initial command requires qualified legacy input; do not fabricate an unspecified no-legacy profile), real delivery adapter and controlled external executor. Executor consumes delivered package and produces actual fixture audit result; do not mint result directly through Store or call an untrusted proposal a completed audit. Exercise all stages required by governing specs, including E6 when required. Report status reflects actual completion and assurance state.
- **Positive tests:** exact lifecycle below; source and standalone equivalent supported flows; multiple stage/lane progression and continuation with new legal assignment after reopen.
- **Negative tests:** missing/corrupt raw package, result, required evidence member, canonical object, schema/profile or history commit; stale/unregistered schema; reopening old campaign for new writes -> fail closed, no fabricated recovery/completion/report qualification.
- **Adversarial tests:** process termination at lifecycle boundaries, altered workspace copies, substitution just before delivery/intake, corrupt accepted bytes/DB dependency, concurrent terminal transition and resume; compare before/after identities and disclosure.
- **Acceptance:** actual start/stop/restart/reopen and continue trace, exact accepted head/objects/events/receipts recovered, package/result/evidence raw readback digests match, all required LaneCompletion/StageCompletion predicates and report gates evidenced. No unrun lifecycle check, mock-only delivery or missing raw can be labeled PASS. Required build/payload/startup/local versus release/clean-room/CI/phase evidence scopes explicit.
- **Rollback:** preserve qualification workspace/evidence, block affected writes/delivery, restore only verified exact objects; fix then rerun invalidated lifecycle/gates. No dropping corrupt history suffix.
- **Blast radius:** entire shipped application, standalone/runtime dependencies and assurance/report lifecycle; no next feature milestone implementation authorized.

Mandatory recorded lifecycle:

```text
fresh application start
 -> create/open legally initialized R5.4 campaign
 -> prepare audit
 -> create and accept assignment
 -> construct/freeze exact package bytes
 -> accept binding; durable readback; later accepted AttemptStarted
 -> deliver exact retained package through real adapter
 -> external executor consumes package and produces audit result
 -> ingest/retain raw result and accept evidence
 -> accept lane result under /2 contract
 -> LaneCompletion
 -> StageCompletion (and every further required stage)
 -> generate report with accurate assurance state
 -> close application/process
 -> restart fresh process
 -> reopen campaign
 -> recover exact accepted head/state/objects/events/receipts
 -> recover exact raw package/result and embedded evidence bytes
 -> continue audit using legal next attempt/assignment/stage
```

Evidence must identify source HEAD **plus dirty/source blob state when applicable**, normative/Registry/GV/schema/profile digests, dependency/backend/platform/runtime identity, fixture raw hashes, harness/verifier versions, exact commands/exit codes/results and artifact raw hash. An unchanged HEAD alone is insufficient. Terminal verification must bind intended implemented state and all mandatory subordinate checks; after any relevant change rerun only invalidated evidence plus explicitly mandatory gates.

Planned execution command families (not run in this documentation task): targeted `python -m pytest ...` existing `tests/workflow/test_nf02_*`, `test_inbox.py`, `test_manual_stage.py`, transaction/schema/process-fault tests and all new frozen-vector selectors; `python -m pytest` required full suite; `python -m ruff check ...`; `python -m mypy --config-file pyproject.toml`; existing `build/build_single_file.py` build interface; `python -m bdb_audit.release_validator_cli <exact artifact> --output <exact evidence>`; repository's governing milestone/phase verifiers and supported shipped application CLI/UI lifecycle. Resolve exact existing selectors/invocations from approved successor task packet, record them verbatim in execution evidence; do not invent a verifier command or silently bypass a mandatory gate when unavailable.

## L. Owner decisions required

The model is complete enough for approval. Existing R5.3 cannot authorize the following new semantics by inference, so owner must explicitly decide:

1. **Approve successor foundation R5.4**, preserving R5.3/R5.3.1 identities, new exact kinds/versions/contracts/profile/schema-root lifecycle in D, followed by the existing external qualification/governance process. Recommendation: approve. Owner approval of this proposal alone is not the produced candidate's hash-bound qualification/freeze.
2. **Approve B as the exact package authorization fact**, minimal RawRef body, semantic checksum profile, separate post-binding STARTED and pre-delivery/result boundaries, no canonical secret or actual-delivery receipt requirement. Recommendation: approve E as a whole. The existence/timing/uniqueness of this new fact is a design decision absent from predecessor, not derivable from green tests.
3. **Approve new-campaign migration boundary**, historical-only old campaigns and unqualified /1 records, no retrospective bindings or in-place schema upgrade. Recommendation: approve H. Continued old execution or in-place migration would require a different separately complete contract and vectors, not a local compatibility shortcut.

No owner choice is needed for reusing legal FACT/producer/ref classes, retaining exact hashing/serialization, preserving predecessor bytes, normal CAS/idempotency, or rejecting self-reference/aliases; those follow existing invariants. Governance actor authorization and candidate readback must later be evidenced through the established process, not invented here. No permission/production action is requested as part of writing this proposal.

## M. Final gate

```text
READY_FOR_OWNER_APPROVAL
```

This value qualifies the **decision proposal only**. No unresolved model-level cycle or unspecified migration/activation boundary remains in the recommendation. R5.4 candidate/executable schemas/SchemaRegistry approval and N1–N11 implementation/qualification remain future required work. **Current NF02 remains SPEC_CONFLICT; no CLOSED claim.**

Scope of this task: one new proposal document; runtime/source/test/build/legacy/predecessor corpus unchanged; no commit, push or remote-ref operation. Documentation verification covers section/contract/vector/plan completeness, source/predecessor raw-hash readback and final diff/status review. It does not claim future runtime qualification PASS.

Końcowa weryfikacja tego zadania (2026-10-06):

| Dokładna komenda / read-only check | Wynik |
| --- | --- |
| `git rev-parse HEAD`, `git rev-parse 'HEAD^{tree}'`, `git branch --show-current`, `git rev-parse main` | Exit 0; identities identyczne z B.1. |
| `git status --short` | Exit 0; względem initial status jedynie nowy `docs/NF02_NORMATIVE_CONTRACT_DECISION_PROPOSAL.md`; zastane zmiany zachowane. Ten sam warning ignored scratch permission. |
| `git diff --check` | Exit 0, brak whitespace errors w tracked diff. Nowy untracked dokument dodatkowo sprawdzono osobno. |
| `git diff --name-only -- legacy/v1_4_4/` | Exit 0, pusty wynik; legacy raw hashes także bez drift. |
| Pełny read-only script poniżej, uruchomiony w repo przez `python -` | Exit 0 / PASS; 504 source pins, 26 document pins, A–M, N1–N11, 11 pól każdego tasku i 15 required vector IDs; 0 drift/mismatch/braków, status delta wyłącznie ten dokument, fences zbilansowane, brak trailing whitespace. |

Dokładna końcowa komenda readback/completeness (PowerShell, workdir repo):

```powershell
@'
import sys, pathlib, json, hashlib, re, subprocess
sys.stdout.reconfigure(encoding='utf-8')
root = pathlib.Path('.')
proposal = root / 'docs/NF02_NORMATIVE_CONTRACT_DECISION_PROPOSAL.md'
text = proposal.read_text(encoding='utf-8')
record = json.loads((root / 'docs/NF02_RAW_DURABILITY_VERIFICATION_2026_10_02.json').read_text(encoding='utf-8-sig'))
drift = [n for n, h in record['tested_inputs']['source_pins'].items()
         if not (root / n).exists() or hashlib.sha256((root / n).read_bytes()).hexdigest() != h]
context = pathlib.Path(r'C:\Projekty\Audyty\BDB Audit - Context')
pins = re.findall(r'\| ((?:src/bdb_audit/|BDB_AUDIT_V2_|ADR-006|docs/NF02_)[^|]+?) \| `([a-f0-9]{64})` \|', text)
wrong_pins = []
for name, expected in pins:
    path = root / name if name.startswith(('src/', 'docs/')) else context / name
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        wrong_pins.append(name)
missing_sections = [chr(i) for i in range(65, 78) if not re.search(r'^## ' + chr(i) + r'\.', text, re.M)]
missing_tasks = []
missing_task_fields = {}
fields = ['Objective', 'Dependencies', 'Files/components', 'Normative refs', 'Outline',
          'Positive tests', 'Negative tests', 'Adversarial tests', 'Acceptance', 'Rollback', 'Blast radius']
for i in range(1, 12):
    match = re.search(r'^### N' + str(i) + r' —.*?(?=^### N\d+ —|^## L\.)', text, re.M | re.S)
    if not match:
        missing_tasks.append(i)
    else:
        missing = [field for field in fields if '**' + field + ':' not in match[0]]
        if missing:
            missing_task_fields[i] = missing
vectors = ['SCHEMA_UNREGISTERED_KIND_REJECT', 'SCHEMA_BYTES_NOT_BOUND_REJECT', 'SCHEMA_WRONG_DIGEST_REJECT',
           'SCHEMA_EXACT_BINDING_ACCEPT', 'PACKAGE_BINDING_ACCEPT', 'PACKAGE_BINDING_SECOND_CONFLICT_REJECT',
           'PACKAGE_BINDING_EXACT_RETRY', 'PACKAGE_RAW_SUBSTITUTION_REJECT', 'PACKAGE_SEMANTIC_MISMATCH_REJECT',
           'PACKAGE_WRONG_ASSIGNMENT_REJECT', 'PACKAGE_WRONG_ATTEMPT_REJECT', 'PACKAGE_WRONG_SOURCE_REJECT',
           'RESULT_WITHOUT_PACKAGE_BINDING_REJECT', 'RESULT_WRONG_PACKAGE_BINDING_REJECT', 'PACKAGE_BINDING_AFTER_DELIVERY_REJECT']
missing_vectors = [v for v in vectors if not re.search(r'^\| NF02_' + v + r' \|', text, re.M)]
initial = re.search(r'^`{3}text\n( M src/bdb_audit/history/authority_hooks.py.*?)\n`{3}', text, re.M | re.S).group(1).splitlines()
status = subprocess.run(['git', 'status', '--short'], capture_output=True, text=True, check=True)
expected_status = set(initial) | {'?? docs/NF02_NORMATIVE_CONTRACT_DECISION_PROPOSAL.md'}
status_delta = sorted(set(status.stdout.splitlines()) ^ expected_status)
whitespace_lines = [i for i, line in enumerate(text.splitlines(), 1) if line.rstrip() != line]
errors = {'source_drift': drift, 'pin_mismatches': wrong_pins, 'missing_sections': missing_sections,
          'missing_tasks': missing_tasks, 'missing_task_fields': missing_task_fields,
          'missing_vectors': missing_vectors, 'unexpected_status_delta': status_delta,
          'trailing_whitespace_lines': whitespace_lines}
result = {'source_pins_checked': len(record['tested_inputs']['source_pins']),
          'document_pins_checked': len(pins), 'fences_balanced': len(re.findall(r'^`{3}[^\n]*$', text, re.M)) % 2 == 0,
          'errors': errors}
result['status'] = 'PASS' if not any(errors.values()) and result['fences_balanced'] else 'FAIL'
print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(0 if result['status'] == 'PASS' else 1)
'@ | python -
```

Script jest checkiem dokumentacji, nie production phase verifier. Wynik dotyczy kompletności i integralności dokumentacji. Nie uruchamiano ani nie przypisano PASS przyszłym runtime gates; jedynym gate propozycji pozostaje wartość w M.
